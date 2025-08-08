# webhook_server.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv
from datetime import datetime, timedelta
from typing import Dict, Any, List
import os, smtplib, ssl, random, requests, time

# ---------- Config ----------
load_dotenv()

APP_NAME = "AI Crypto Backend"
APP_VERSION = "1.1.0"

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8501")
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")

# CoinGecko (no key needed)
COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
COIN_IDS = [
    "bitcoin", "ethereum", "solana", "cardano", "ripple",
    "binancecoin", "dogecoin", "avalanche-2", "polygon", "litecoin",
]  # add/remove freely
ID_TO_SYMBOL = {
    "bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL", "cardano": "ADA",
    "ripple": "XRP", "binancecoin": "BNB", "dogecoin": "DOGE",
    "avalanche-2": "AVAX", "polygon": "MATIC", "litecoin": "LTC",
}

# ---------- App ----------
app = FastAPI(title=APP_NAME, version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "*"],  # tighten later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- In‑memory stores ----------
otp_store: Dict[str, str] = {}
last_otp_sent_at: Dict[str, float] = {}   # email -> epoch seconds
prices_cache: Dict[str, Any] = {"ts": 0.0, "data": []}  # naive cache

# ---------- Models ----------
class EmailRequest(BaseModel):
    email: EmailStr

class OTPVerifyRequest(BaseModel):
    email: EmailStr
    otp: str

# ---------- Helpers ----------
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
    """Limit OTP to once per minute per email."""
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
    params = {
        "ids": ids,
        "vs_currencies": "usd",
        "include_24hr_change": "true",
    }
    r = requests.get(COINGECKO_URL, params=params, timeout=15)
    r.raise_for_status()
    raw = r.json()

    data = []
    for cid, payload in raw.items():
        price = float(payload.get("usd", 0.0))
        change = float(payload.get("usd_24h_change", 0.0))
        data.append({
            "symbol": ID_TO_SYMBOL.get(cid, cid.upper()),
            "price": price,
            "change": change,
        })

    # cache
    prices_cache["ts"] = now
    prices_cache["data"] = data
    return data

# ---------- Routes ----------
@app.get("/")
def root():
    return {"status": "ok", "app": APP_NAME, "version": APP_VERSION}

@app.get("/healthz")
def healthz():
    return {"ok": True, "time": datetime.utcnow().isoformat() + "Z"}

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
        otp_store.pop(email, None)  # one-time
        return {"authenticated": True, "pro": False}
    return {"authenticated": False, "message": "Incorrect or expired OTP"}

@app.get("/predict")
def predict(email: str):
    """
    Live data from CoinGecko (USD price + 24h change) with a 10s cache.
    """
    email = email.strip().lower()
    try:
        coins = fetch_live_prices()
        return {
            "email": email,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "coins": coins
        }
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.utcnow().isoformat() + "Z"}

@app.get("/version")
def version():
    return {
        "version": APP_VERSION,
        "build_time": datetime.utcnow().isoformat() + "Z",
        "status": "Backend is running!"
    }
