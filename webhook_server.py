from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv
from datetime import datetime, timezone
from typing import Dict, Any, List, Literal, Optional, Tuple
from apscheduler.schedulers.background import BackgroundScheduler
from collections import deque
from sqlmodel import SQLModel, Field, Session, create_engine, select
import os, smtplib, ssl, random, requests, time, math

# ---------- Config ----------
load_dotenv()

APP_NAME = "AI Crypto Backend"
APP_VERSION = "1.5.3"

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8501")
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")  # optional

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

# ---------- Database (Postgres via psycopg v3) ----------
DEFAULT_DB_URL = "sqlite:///./data/app.db"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DB_URL)

def _normalize_db_url(url: str) -> str:
    # Convert postgres:// → postgresql+psycopg:// for SQLAlchemy v2 + psycopg v3
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://") and not url.startswith("postgresql+psycopg://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url

DATABASE_URL = _normalize_db_url(DATABASE_URL)

if DATABASE_URL.startswith("sqlite"):
    db_path = DATABASE_URL.replace("sqlite:///", "")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

class User(SQLModel, table=True):
    email: str = Field(primary_key=True)
    is_pro: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Alert(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(foreign_key="user.email", index=True)
    symbol: str
    direction: str  # store as plain string in DB (UP/DOWN)
    percent: float
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

def get_session() -> Session:
    return Session(engine)

# ---------- App ----------
app = FastAPI(title=APP_NAME, version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "https://ai-crypto-frontend-8rmwtc8eqtxsasgmhbv8d6.streamlit.app", "*"],
    allow_credentials=True,
    allow_methods=["GET","POST","DELETE","OPTIONS"],
    allow_headers=["*"],
)

# ---------- In-memory runtime ----------
otp_store: Dict[str, str] = {}
last_otp_sent_at: Dict[str, float] = {}
prices_cache: Dict[str, Any] = {"ts": 0.0, "data": [], "stale": True, "error": None}
last_prices: Dict[str, float] = {}
last_triggered_at: Dict[str, float] = {}
price_history: Dict[str, deque[Tuple[float, float]]] = {sym: deque(maxlen=1440) for sym in SYMBOLS}

# ---------- Models (requests) ----------
class EmailRequest(BaseModel):
    email: EmailStr

class OTPVerifyRequest(BaseModel):
    email: EmailStr
    otp: str

class AlertCreate(BaseModel):
    email: EmailStr
    symbol: Literal["BTC","ETH","SOL","ADA","XRP","BNB","DOGE","AVAX","MATIC","LTC"]
    direction: Literal["UP","DOWN"]
    percent: float

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

def percent_move(old: float, new: float) -> float:
    if old <= 0: return 0.0
    return (new - old) / old * 100.0

def _headers():
    h = {"Accept": "application/json"}
    if COINGECKO_API_KEY:
        h["x-cg-pro-api-key"] = COINGECKO_API_KEY
    return h

def _refresh_prices_once() -> bool:
    ids = ",".join(COIN_IDS)
    params = {"ids": ids, "vs_currencies": "usd", "include_24hr_change": "true"}
    try:
        r = requests.get(COINGECKO_URL, params=params, headers=_headers(), timeout=15)
        if r.status_code == 429:
            retry_after = r.headers.get("Retry-After")
            msg = f"429 Too Many Requests. Retry-After={retry_after}"
            prices_cache["error"], prices_cache["stale"] = msg, True
            print(msg)
            return False
        r.raise_for_status()
        raw = r.json()

        data = []
        for cid, payload in raw.items():
            price = float(payload.get("usd", 0.0))
            change = float(payload.get("usd_24h_change", 0.0))
            sym = ID_TO_SYMBOL.get(cid, cid.upper())
            direction = "UP" if change >= 0 else "DOWN"
            conf = 1 / (1 + math.exp(-abs(change) / 6))
            confidence = round(conf * 100, 1)
            data.append({"symbol": sym, "price": price, "change": change, "prediction": direction, "confidence": confidence})

        now = time.time()
        prices_cache.update({"ts": now, "data": data, "stale": False, "error": None})
        for c in data:
            sym, price = c["symbol"], float(c["price"])
            price_history[sym].append((now, price))
            last_prices[sym] = price
        return True
    except Exception as e:
        prices_cache["error"], prices_cache["stale"] = str(e), True
        print("refresh error:", e)
        return False

def get_window_change(sym: str, minutes: int, current_price: float) -> float:
    if minutes <= 0: return 0.0
    cutoff = time.time() - (minutes * 60)
    hist = price_history.get(sym, deque())
    base = None
    for ts, p in hist:
        if ts >= cutoff:
            base = p
            break
    if base is None:
        base = hist[0][1] if hist else current_price
    return percent_move(base, current_price)

def scheduled_refresh():
    _refresh_prices_once()

def all_alerts(session: Session) -> List["Alert"]:
    return session.exec(select(Alert)).all()

def ensure_user(session: Session, email: str) -> None:
    if not session.get(User, email):
        session.add(User(email=email, is_pro=False))
        session.commit()

def check_alerts_and_notify():
    try:
        if not prices_cache["data"]:
            _refresh_prices_once()
        coins = prices_cache["data"]
        sym_to_price = {c["symbol"]: float(c["price"]) for c in coins}

        with get_session() as session:
            records = all_alerts(session)
            for a in records:
                sym = a.symbol
                if sym not in sym_to_price: continue
                now_p = sym_to_price[sym]
                prev_p = last_prices.get(sym, now_p)
                mv = percent_move(prev_p, now_p)
                hit = (a.direction == "UP" and mv >= a.percent) or (a.direction == "DOWN" and mv <= -a.percent)
                if hit:
                    key = f"{a.email}:{sym}:{a.direction}:{a.percent:.2f}"
                    last = last_triggered_at.get(key, 0.0)
                    if time.time() - last >= 30*60:
                        subject = f"[Alert] {sym} moved {mv:+.2f}% ({a.direction} {a.percent}%)"
                        body = (f"Symbol: {sym}\nDirection: {a.direction}\nThreshold: {a.percent}%\n"
                                f"Move since last minute: {mv:+.2f}%\nCurrent price: ${now_p:,.2f}\n\nTime (UTC): {utcnow_iso()}")
                        send_email(a.email, subject, body)
                        last_triggered_at[key] = time.time()
        for sym, p in sym_to_price.items():
            last_prices[sym] = p
    except Exception as e:
        print("check_alerts_and_notify error:", e)

# ---------- Routes ----------
@app.get("/")
def root():
    return {"status": "ok", "app": APP_NAME, "version": APP_VERSION}

@app.get("/version")
def version():
    return {"version": APP_VERSION, "build_time": utcnow_iso(), "stale": prices_cache["stale"],
            "last_ts": prices_cache["ts"], "last_error": prices_cache["error"], "status": "Backend is running!"}

@app.post("/send-otp")
def send_otp(req: EmailRequest):
    email = req.email.strip().lower()
    now = time.time()
    if now - last_otp_sent_at.get(email, 0) < 60:
        return {"success": False, "message": "Please wait 60s before requesting another OTP."}
    last_otp_sent_at[email] = now
    otp = f"{random.randint(100000, 999999)}"
    otp_store[email] = otp
    result = send_email(email, "Your OTP Code", f"Your login OTP is: {otp}\n\nThis code expires in 10 minutes.")
    return {"success": True, "message": "OTP sent"} if result.get("success") else {"success": False, "message": result.get("message", "Send failed")}

@app.post("/verify-otp")
def verify_otp(req: OTPVerifyRequest):
    email, otp = req.email.strip().lower(), req.otp.strip()
    if not otp or len(otp) != 6 or not otp.isdigit():
        return {"authenticated": False, "message": "Invalid OTP format"}
    if otp_store.get(email) == otp:
        otp_store.pop(email, None)
        with get_session() as session:
            ensure_user(session, email)
        return {"authenticated": True, "pro": False}
    return {"authenticated": False, "message": "Incorrect or expired OTP"}

@app.get("/predict")
def predict(email: str, window: Literal["15m","1h","12h","24h"]="24h"):
    email = email.strip().lower()
    if not prices_cache["data"]:
        _refresh_prices_once()
    coins, ts, stale, err = prices_cache["data"], prices_cache["ts"], prices_cache["stale"], prices_cache["error"]
    try:
        minutes = WINDOW_MINUTES.get(window, 1440)
        enriched = []
        for c in coins:
            sym, price = c["symbol"], float(c["price"])
            win_change = get_window_change(sym, minutes, price)
            enriched.append({"symbol": sym, "price": price, "change": win_change,
                             "prediction": c["prediction"], "confidence": c["confidence"]})
        return {"email": email, "timestamp": utcnow_iso(), "window": window, "stale": stale,
                "coins": enriched, "backend_ts": ts, "backend_error": err}
    except Exception as e:
        return {"error": str(e), "timestamp": utcnow_iso(), "window": window,
                "stale": stale, "backend_ts": ts, "backend_error": err}

# ----- Alerts (persisted) -----
@app.get("/alerts")
def list_alerts(email: EmailStr):
    e = email.strip().lower()
    with get_session() as session:
        rows = session.exec(select(Alert).where(Alert.email == e)).all()
        return {"email": e, "alerts": [{"symbol": r.symbol, "direction": r.direction, "percent": r.percent} for r in rows]}

@app.post("/alerts")
def create_alert(alert: AlertCreate):
    e = alert.email.strip().lower()
    with get_session() as session:
        ensure_user(session, e)
        existing = session.exec(
            select(Alert).where(
                (Alert.email == e) &
                (Alert.symbol == alert.symbol) &
                (Alert.direction == alert.direction) &
                (Alert.percent == float(alert.percent))
            )
        ).first()
        if not existing:
            session.add(Alert(email=e, symbol=alert.symbol, direction=alert.direction, percent=float(alert.percent)))
            session.commit()
        rows = session.exec(select(Alert).where(Alert.email == e)).all()
        return {"success": True, "alerts": [{"symbol": r.symbol, "direction": r.direction, "percent": r.percent} for r in rows]}

@app.get("/alerts/add")
def create_alert_get(
    email: EmailStr = Query(...),
    symbol: Literal["BTC","ETH","SOL","ADA","XRP","BNB","DOGE","AVAX","MATIC","LTC"] = Query(...),
    direction: Literal["UP","DOWN"] = Query(...),
    percent: float = Query(...)
):
    e = email.strip().lower()
    with get_session() as session:
        ensure_user(session, e)
        existing = session.exec(
            select(Alert).where(
                (Alert.email == e) &
                (Alert.symbol == symbol) &
                (Alert.direction == direction) &
                (Alert.percent == float(percent))
            )
        ).first()
        if not existing:
            session.add(Alert(email=e, symbol=symbol, direction=direction, percent=float(percent)))
            session.commit()
        rows = session.exec(select(Alert).where(Alert.email == e)).all()
        return {"success": True, "alerts": [{"symbol": r.symbol, "direction": r.direction, "percent": r.percent} for r in rows]}

@app.delete("/alerts")
def delete_alert(email: EmailStr, symbol: str, direction: str, percent: float):
    e = email.strip().lower()
    with get_session() as session:
        rows = session.exec(
            select(Alert).where(
                (Alert.email == e) &
                (Alert.symbol == symbol) &
                (Alert.direction == direction) &
                (Alert.percent == float(percent))
            )
        ).all()
        for r in rows:
            session.delete(r)
        session.commit()
        rows = session.exec(select(Alert).where(Alert.email == e)).all()
        return {"success": True, "alerts": [{"symbol": r.symbol, "direction": r.direction, "percent": r.percent} for r in rows]}

# ---------- Lifecycle ----------
scheduler: Optional[BackgroundScheduler] = None

@app.on_event("startup")
def on_start():
    SQLModel.metadata.create_all(engine)
    global scheduler
    _refresh_prices_once()  # prime cache
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(scheduled_refresh, "interval", seconds=30, max_instances=1)
    scheduler.add_job(check_alerts_and_notify, "interval", seconds=60, max_instances=1)
    scheduler.start()
    print("🚀 DB ready. Schedulers started (30s refresh, 60s alerts).")

@app.on_event("shutdown")
def on_stop():
    global scheduler
    if scheduler:
        scheduler.shutdown(wait=False)
        print("⏹️ Schedulers stopped.")
