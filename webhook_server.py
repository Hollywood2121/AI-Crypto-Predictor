from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv
from datetime import datetime, timezone
from typing import Dict, Any, List, Literal, Optional, Tuple
from apscheduler.schedulers.background import BackgroundScheduler
from collections import deque
import os, smtplib, ssl, random, requests, time, math

# ---------- Config ----------
load_dotenv()

APP_NAME = "AI Crypto Backend"
APP_VERSION = "1.4.0"

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8501")
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
COIN_IDS = [
    "bitcoin","ethereum","solana","cardano","ripple",
    "binancecoin","dogecoin","avalanche-2","polygon","litecoin",
]
ID_TO_SYMBOL = {
    "bitcoin":"BTC","ethereum":"ETH","solana":"SOL","cardano":"ADA","ripple":"XRP",
    "binancecoin":"BNB","dogecoin":"DOGE","avalanche-2":"AVAX","polygon":"MATIC","litecoin":"LTC",
}
SYMBOLS = list(ID_TO_SYMBOL.values())

WINDOW_MINUTES = {"15m": 15, "1h": 60, "12h": 720, "24h": 1440}

# ---------- App ----------
app = FastAPI(title=APP_NAME, version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "*"],  # tighten later
    allow_credentials=True,
    allow_methods=["GET","POST","DELETE","OPTIONS"],
    allow_headers=["*"],
)

# ---------- In‑memory stores ----------
otp_store: Dict[str, str] = {}
last_otp_sent_at: Dict[str, float] = {}
prices_cache: Dict[str, Any] = {"ts": 0.0, "data": []}  # cached list of coin dicts
last_prices: Dict[str, float] = {}  # symbol -> last price seen by scheduler
alerts_by_email: Dict[str, List[Dict[str, Any]]] = {}  # email -> list of alert dicts
last_triggered_at: Dict[str, float] = {}  # alert_key -> epoch seconds (cooldown)

# per‑symbol minute snapshots for up to 24h: deque[(ts, price)]
price_history: Dict[str, deque[Tuple[float, float]]] = {sym: deque(maxlen=1440) for sym in SYMBOLS}

# ---------- Models ----------
class EmailRequest(BaseModel):
    email: EmailStr

class OTPVerifyRequest(BaseModel):
    email: EmailStr
    otp: str

class AlertCreate(BaseModel):
    email: EmailStr
    symbol: Literal["BTC","ETH","SOL","ADA","XRP","BNB","DOGE","AVAX","MATIC","LTC"]
    direction: Literal["UP","DOWN"]
    percent: float  # e.g., 1.0, 2.0, 5.0, 10.0

# ---------- Helpers ----------
def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def smtp_ready() -> bool:
    return all([SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASS])

def send_email(to_email: str, subject: str, body: str) -> Dict[str, Any]:
    if not smtp_ready():
        return {"success": False, "message": "SMTP configuration incomplete"}
    msg = f"Subject: {subject}\n\n{body}"
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=20) as server:
            server.starttls(context=context)
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, to_email, msg)
        print(f"✅ Email sent to {to_email}")
        return {"success": True}
    except Exception as e:
        print("Email send error:", e)
        return {"success": False, "message": str(e)}

def rate_limited(email: str, window_sec: int = 60) -> bool:
    now = time.time()
    last = last_otp_sent_at.get(email, 0)
    if now - last < window_sec:
        return True
    last_otp_sent_at[email] = now
    return False

def fetch_live_prices() -> List[Dict[str, Any]]:
    """Fetch live prices + 24h change (USD) from CoinGecko, with 10s cache."""
    now = time.time()
    if now - prices_cache["ts"] < 10 and prices_cache["data"]:
        return prices_cache["data"]

    ids = ",".join(COIN_IDS)
    params = {"ids": ids, "vs_currencies": "usd", "include_24hr_change": "true"}
    r = requests.get(COINGECKO_URL, params=params, timeout=15)
    r.raise_for_status()
    raw = r.json()

    data = []
    for cid, payload in raw.items():
        price = float(payload.get("usd", 0.0))
        change = float(payload.get("usd_24h_change", 0.0))
        sym = ID_TO_SYMBOL.get(cid, cid.upper())

        # dummy AI signal: confidence increases with absolute change
        direction = "UP" if change >= 0 else "DOWN"
        conf = 1 / (1 + math.exp(-abs(change) / 6))
        confidence = round(conf * 100, 1)

        data.append({
            "symbol": sym,
            "price": price,
            "change": change,
            "prediction": direction,
            "confidence": confidence
        })

    prices_cache["ts"] = now
    prices_cache["data"] = data
    return data

def percent_move(old: float, new: float) -> float:
    if old <= 0:
        return 0.0
    return (new - old) / old * 100.0

def get_change_for_window(sym: str, minutes: int, current_price: float) -> float:
    """Return % change between current and price ~minutes ago using price_history."""
    if minutes <= 0:
        return 0.0
    cutoff = time.time() - (minutes * 60)
    hist = price_history.get(sym, deque())
    base_price = None
    # find the oldest sample newer than cutoff, else fall back to oldest available
    for ts, p in hist:
        if ts >= cutoff:
            base_price = p
            break
    if base_price is None:
        # Not enough history; fall back to earliest record, or 0 change if empty
        if hist:
            base_price = hist[0][1]
        else:
            return 0.0
    return percent_move(base_price, current_price)

def sample_prices_into_history():
    """Called every minute: snapshot current prices into price_history and update last_prices."""
    try:
        coins = fetch_live_prices()
        now = time.time()
        for c in coins:
            sym = c["symbol"]
            price = float(c["price"])
            price_history[sym].append((now, price))
            last_prices[sym] = price
    except Exception as e:
        print("sample_prices_into_history error:", e)

def check_alerts_and_notify():
    """Runs every 60s: compare last minute to current minute and trigger threshold alerts."""
    try:
        coins = fetch_live_prices()
        sym_to_price = {c["symbol"]: float(c["price"]) for c in coins}

        for email, alerts in alerts_by_email.items():
            for a in alerts:
                sym = a["symbol"]
                if sym not in sym_to_price:
                    continue
                price_now = sym_to_price[sym]
                price_prev = last_prices.get(sym, price_now)
                move = percent_move(price_prev, price_now)  # positive if up

                hit = (a["direction"] == "UP" and move >= a["percent"]) or \
                      (a["direction"] == "DOWN" and move <= -a["percent"])

                if hit:
                    key = f"{email}:{sym}:{a['direction']}:{a['percent']:.2f}"
                    last = last_triggered_at.get(key, 0.0)
                    # cooldown: 30 minutes
                    if time.time() - last >= 30*60:
                        subject = f"[Alert] {sym} moved {move:+.2f}% ({a['direction']} {a['percent']}%)"
                        body = (
                            f"Symbol: {sym}\n"
                            f"Direction: {a['direction']}\n"
                            f"Threshold: {a['percent']}%\n"
                            f"Move since last minute: {move:+.2f}%\n"
                            f"Current price: ${price_now:,.2f}\n\n"
                            f"Time (UTC): {utcnow_iso()}"
                        )
                        send_email(email, subject, body)
                        last_triggered_at[key] = time.time()

        # update last prices AFTER processing
        for sym, p in sym_to_price.items():
            last_prices[sym] = p

    except Exception as e:
        print("check_alerts_and_notify error:", e)

# ---------- Routes ----------
@app.get("/")
def root():
    return {"status": "ok", "app": APP_NAME, "version": APP_VERSION}

@app.get("/healthz")
def healthz():
    return {"ok": True, "time": utcnow_iso()}

@app.post("/send-otp")
def send_otp(req: EmailRequest):
    email = req.email.strip().lower()
    if rate_limited(email):
        return {"success": False, "message": "Please wait 60s before requesting another OTP."}
    otp = f"{random.randint(100000, 999999)}"
    otp_store[email] = otp
    subject = "Your OTP Code"
    body = f"Your login OTP is: {otp}\n\nThis code expires in 10 minutes."
    result = send_email(email, subject, body)
    if result.get("success"):
        return {"success": True, "message": "OTP sent"}
    else:
        return {"success": False, "message": result.get("message", "Send failed")}

@app.post("/verify-otp")
def verify_otp(req: OTPVerifyRequest):
    email = req.email.strip().lower()
    otp = req.otp.strip()
    if not otp or len(otp) != 6 or not otp.isdigit():
        return {"authenticated": False, "message": "Invalid OTP format"}
    if otp_store.get(email) == otp:
        otp_store.pop(email, None)
        return {"authenticated": True, "pro": False}
    return {"authenticated": False, "message": "Incorrect or expired OTP"}

@app.get("/predict")
def predict(email: str, window: Literal["15m","1h","12h","24h"]="24h"):
    """
    Live data + time-windowed change + dummy AI signal + timestamp.
    window: 15m | 1h | 12h | 24h
    """
    email = email.strip().lower()
    try:
        coins = fetch_live_prices()
        minutes = WINDOW_MINUTES.get(window, 1440)
        # Recompute change per selected window using our history
        enriched = []
        for c in coins:
            sym = c["symbol"]
            price = float(c["price"])
            win_change = get_change_for_window(sym, minutes, price)
            enriched.append({
                "symbol": sym,
                "price": price,
                "change": win_change,
                "prediction": c["prediction"],
                "confidence": c["confidence"]
            })
        return {"email": email, "timestamp": utcnow_iso(), "window": window, "coins": enriched}
    except Exception as e:
        return {"error": str(e), "timestamp": utcnow_iso(), "window": window}

# ----- Alerts API -----
@app.get("/alerts")
def list_alerts(email: EmailStr):
    return {"email": email, "alerts": alerts_by_email.get(email.lower(), [])}

@app.post("/alerts")
def create_alert(alert: AlertCreate):
    email = alert.email.strip().lower()
    entry = {"symbol": alert.symbol, "direction": alert.direction, "percent": float(alert.percent)}
    alerts_by_email.setdefault(email, [])
    if entry not in alerts_by_email[email]:
        alerts_by_email[email].append(entry)
    return {"success": True, "alerts": alerts_by_email[email]}

# ---- GET fallback to add alerts if POST is blocked or old code is running
@app.get("/alerts/add")
def create_alert_get(
    email: EmailStr = Query(...),
    symbol: Literal["BTC","ETH","SOL","ADA","XRP","BNB","DOGE","AVAX","MATIC","LTC"] = Query(...),
    direction: Literal["UP","DOWN"] = Query(...),
    percent: float = Query(...)
):
    e = email.strip().lower()
    entry = {"symbol": symbol, "direction": direction, "percent": float(percent)}
    alerts_by_email.setdefault(e, [])
    if entry not in alerts_by_email[e]:
        alerts_by_email[e].append(entry)
    return {"success": True, "alerts": alerts_by_email[e]}

@app.delete("/alerts")
def delete_alert(email: EmailStr, symbol: str, direction: str, percent: float):
    email = email.strip().lower()
    items = alerts_by_email.get(email, [])
    new_items = [a for a in items if not (a["symbol"] == symbol and a["direction"] == direction and float(a["percent"]) == float(percent))]
    alerts_by_email[email] = new_items
    return {"success": True, "alerts": new_items}

# ---------- Scheduler ----------
scheduler: Optional[BackgroundScheduler] = None

@app.on_event("startup")
def on_start():
    global scheduler
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(sample_prices_into_history, "interval", seconds=60, max_instances=1)
    scheduler.add_job(check_alerts_and_notify, "interval", seconds=60, max_instances=1)
    scheduler.start()
    print("📈 History sampler + 🔔 Alert scheduler started.")

@app.on_event("shutdown")
def on_stop():
    global scheduler
    if scheduler:
        scheduler.shutdown(wait=False)
        print("⏹️ Schedulers stopped.")

@app.get("/version")
def version():
    return {"version": APP_VERSION, "build_time": utcnow_iso(), "status": "Backend is running!"}
