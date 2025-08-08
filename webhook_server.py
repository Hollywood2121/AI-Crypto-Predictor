# webhook_server.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv
import os
import smtplib
import ssl
import random
from typing import Dict, Any

# ---------- Config ----------
load_dotenv()

APP_NAME = "AI Crypto Backend"
APP_VERSION = "1.0.0"

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8501")

SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")

# ---------- App ----------
app = FastAPI(title=APP_NAME, version=APP_VERSION)

# CORS for Streamlit frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "*"],  # keep "*" while iterating; you can remove it later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- In-memory store (OK for demo; use Redis/DB in prod) ----------
otp_store: Dict[str, str] = {}

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

# ---------- Routes ----------
@app.get("/")
def root():
    return {"status": "ok", "app": APP_NAME, "version": APP_VERSION}

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.post("/send-otp")
def send_otp(req: EmailRequest):
    email = req.email.strip().lower()
    otp = f"{random.randint(100000, 999999)}"
    otp_store[email] = otp

    subject = "Your OTP Code"
    body = f"Your login OTP is: {otp}\n\nThis code expires in 10 minutes."

    result = send_email(email, subject, body)
    if result.get("success"):
        return {"success": True, "message": "OTP sent"}
    else:
        # Bubble up the reason to the frontend for easier debugging
        return {"success": False, "message": result.get("message", "Send failed")}

@app.post("/verify-otp")
def verify_otp(req: OTPVerifyRequest):
    email = req.email.strip().lower()
    otp = req.otp.strip()

    if not otp or len(otp) != 6 or not otp.isdigit():
        return {"authenticated": False, "message": "Invalid OTP format"}

    if otp_store.get(email) == otp:
        # Optional: remove it after use (one-time)
        otp_store.pop(email, None)
        return {"authenticated": True, "pro": False}
    return {"authenticated": False, "message": "Incorrect or expired OTP"}

from datetime import datetime

@app.get("/predict")
def predict(email: str):
    """
    Simple mock data so the Streamlit UI can render something after login.
    Replace later with your real model/data feed.
    """
    email = email.strip().lower()
    coins = [
        {"symbol": "BTC", "price": 67231.12, "change": 1.24},
        {"symbol": "ETH", "price": 3243.55, "change": -0.54},
        {"symbol": "SOL", "price": 118.02, "change": 4.10},
        {"symbol": "ADA", "price": 0.46, "change": 0.92},
        {"symbol": "XRP", "price": 0.57, "change": -1.21},
    ]
    return {
        "email": email,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "coins": coins
    }

@app.get("/version")
def version():
    """
    Returns the current backend version and build timestamp.
    Useful for confirming deploys.
    """
    return {
        "version": "1.0.0",
        "build_time": datetime.utcnow().isoformat() + "Z",
        "status": "Backend is running!"
    }
