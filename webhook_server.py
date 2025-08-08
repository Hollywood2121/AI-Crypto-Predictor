from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import smtplib
import ssl
import random

load_dotenv()

app = FastAPI()

# --- CORS ---
origins = [
    os.getenv("FRONTEND_URL", "http://localhost:8501"),
    "*"
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- TEMP STORAGE ---
otp_store = {}

# --- MODELS ---
class EmailRequest(BaseModel):
    email: str

class OTPVerifyRequest(BaseModel):
    email: str
    otp: str

# --- ROUTES ---
@app.get("/")
def root():
    return {"status": "Backend is running!"}

@app.post("/send-otp")
def send_otp(data: EmailRequest):
    email = data.email.strip().lower()
    otp = str(random.randint(100000, 999999))
    otp_store[email] = otp

    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")

    if not all([smtp_server, smtp_port, smtp_user, smtp_pass]):
        return {"success": False, "message": "SMTP configuration incomplete"}

    message = f"Subject: Your OTP Code\n\nYour login OTP is: {otp}"

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls(context=context)
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, email, message)
        print(f"✅ OTP sent to {email}")
        return {"success": True, "message": "OTP sent"}
    except Exception as e:
        print("Email send error:", e)
        return {"success": False, "message": str(e)}

@app.post("/verify-otp")
def verify_otp(data: OTPVerifyRequest):
    email = data.email.strip().lower()
    if otp_store.get(email) == data.otp:
        return {"authenticated": True, "pro": False}
    return {"authenticated": False}

@app.get("/predict")
def predict(email: str):
    """
    Mock crypto prediction data.
    Replace with AI model output later.
    """
    email = email.strip().lower()
    coins = [
        {"symbol": "BTC", "price": 67231.12, "change": 1.24},
        {"symbol": "ETH", "price": 3243.55, "change": -0.54},
        {"symbol": "SOL", "price": 118.02, "change": 4.10},
        {"symbol": "ADA", "price": 0.46, "change": 0.92},
        {"symbol": "XRP", "price": 0.57, "change": -1.21},
    ]
    return {"email": email, "coins": coins}

@app.get("/alerts")
def alerts():
    """
    Example alerts endpoint for price changes.
    """
    alerts_data = [
        {"symbol": "BTC", "alert": "Price crossed $67,000 🚀"},
        {"symbol": "SOL", "alert": "Up 4% in last 24h 📈"}
    ]
    return {"alerts": alerts_data}
