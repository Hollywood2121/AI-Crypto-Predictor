import streamlit as st
import requests
import os
import time
from dotenv import load_dotenv


load_dotenv()

# Constants
API_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="AI Crypto Predictor", layout="wide")

# --- Custom CSS for Robinhood-style Dark UI ---
st.markdown("""
    <style>
        .main { background-color: #0f1115; color: white; }
        .stButton > button {
            background-color: #00c853;
            color: white;
            border-radius: 10px;
            padding: 0.6em 1.2em;
            font-size: 16px;
        }
        .block-container { padding-top: 2rem; }
    </style>
""", unsafe_allow_html=True)

# --- Sidebar Theme Toggle ---
theme = st.sidebar.radio("Choose Theme", ["🌙 Dark", "☀️ Light"])
if theme == "☀️ Light":
    st.markdown("""
        <style>
        .main { background-color: #f5f5f5; color: black; }
        </style>
    """, unsafe_allow_html=True)

# --- Session State Init ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user_email = None
    st.session_state.pro = False

# --- Login Form ---
def login():
    st.title("🔐 Login or Sign Up")
    email = st.text_input("Enter your email")
    if st.button("Send OTP"):
        r = requests.post(f"{API_URL}/send-otp", json={"email": email})
        if r.ok:
            st.session_state.user_email = email
            st.success("OTP sent to your email.")

    otp = st.text_input("Enter OTP")
    if st.button("Verify OTP"):
        r = requests.post(f"{API_URL}/verify-otp", json={"email": email, "otp": otp})
        if r.ok and r.json().get("authenticated"):
            st.session_state.authenticated = True
            st.session_state.user_email = email
            st.session_state.pro = r.json().get("pro", False)
            st.experimental_rerun()
        else:
            st.error("Invalid OTP")

# --- Main Dashboard ---
def dashboard():
    st.title("📊 Crypto Market Dashboard")
    st.write(f"Welcome, {st.session_state.user_email}")

    # Fetch predictions
    try:
        resp = requests.get(f"{API_URL}/predict?email={st.session_state.user_email}")
        data = resp.json()

        st.subheader("Top Trending Coins")
        for coin in data["coins"]:
            st.metric(label=coin["symbol"], value=f"${coin['price']:.2f}", delta=f"{coin['change']}%")

        if not st.session_state.pro:
            st.warning("You're on the free plan. Upgrade to Pro to unlock full features.")
            if st.button("Upgrade to Pro"):
                # Fetch Stripe Checkout URL
                resp = requests.post(f"{API_URL}/create-checkout-session", json={"email": st.session_state.user_email})
                checkout_url = resp.json().get("checkout_url")
                st.markdown(f"[Click here to complete upgrade]({checkout_url})")

    except Exception as e:
        st.error("Failed to fetch data. Is the backend running?")
        st.exception(e)

# --- App Flow ---
if not st.session_state.authenticated:
    login()
else:
    dashboard()
