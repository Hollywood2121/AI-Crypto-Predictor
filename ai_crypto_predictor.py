import streamlit as st
import requests
import os
from dotenv import load_dotenv
import json

load_dotenv()

API_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# ----- Streamlit Config -----
st.set_page_config(page_title="AI Crypto Predictor", layout="wide")

# ----- Theming -----
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Roboto&display=swap');
    html, body, [class*="css"]  {
        font-family: 'Roboto', sans-serif;
        transition: background-color 0.5s ease;
    }
    .darkmode {
        background: linear-gradient(135deg, #1f1f1f, #121212);
        color: white;
    }
    .lightmode {
        background: linear-gradient(135deg, #f9f9f9, #e6e6e6);
        color: black;
    }
    .glass-card {
        background: rgba(255, 255, 255, 0.1);
        border-radius: 16px;
        padding: 1.5rem;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.2);
        box-shadow: 0 8px 32px 0 rgba(0,0,0,0.1);
        margin-bottom: 1rem;
    }
    .metric-container {
        display: flex;
        flex-wrap: wrap;
        gap: 1rem;
    }
    </style>
""", unsafe_allow_html=True)

# ----- Theme Switcher -----
mode = st.sidebar.radio("Choose Theme", ["🌙 Dark", "☀️ Light"])
if mode == "🌙 Dark":
    st.markdown("<div class='darkmode'>", unsafe_allow_html=True)
else:
    st.markdown("<div class='lightmode'>", unsafe_allow_html=True)

# ----- Session State Init -----
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user_email = None
    st.session_state.pro = False

# ----- Login Flow -----
def login():
    st.title("🔐 Secure Login")
    with st.container():
        email = st.text_input("Enter your email")
        if st.button("📩 Send OTP"):
            try:
                r = requests.post(f"{API_URL}/send-otp", json={"email": email})
                if r.ok:
                    st.session_state.user_email = email
                    st.success("✅ OTP sent to your email inbox!")
                else:
                    st.error("❌ Failed to send OTP. Please double-check your email or server setup.")
            except Exception as e:
                st.error("❌ Error while sending OTP.")
                st.exception(e)

    if st.session_state.user_email:
        otp = st.text_input("Enter the OTP sent to your email")
        if st.button("🔓 Verify OTP"):
            try:
                r = requests.post(f"{API_URL}/verify-otp", json={"email": st.session_state.user_email, "otp": otp})
                if r.ok and r.json().get("authenticated"):
                    st.session_state.authenticated = True
                    st.session_state.pro = r.json().get("pro", False)
                    st.success("🎉 Logged in successfully!")
                    st.rerun()

                else:
                    st.error("❌ Invalid OTP or expired")
            except Exception as e:
                st.error("❌ Error while verifying OTP")
                st.exception(e)

# ----- Dashboard -----
def dashboard():
    st.title("📊 AI Crypto Market Dashboard")
    st.markdown("### Welcome back, **{}**".format(st.session_state.user_email))

    try:
        r = requests.get(f"{API_URL}/predict?email={st.session_state.user_email}")
        if r.ok:
            data = r.json()
            st.subheader("Top Trending Cryptos")
            with st.container():
                for coin in data["coins"]:
                    with st.container():
                        st.markdown(f"""
                            <div class='glass-card'>
                                <h4>{coin['symbol']}</h4>
                                <p>💲 {coin['price']:.2f} | 📈 {coin['change']}%</p>
                            </div>
                        """, unsafe_allow_html=True)
            if not st.session_state.pro:
                st.warning("You're currently on the free plan. Upgrade to Pro to unlock all coins and time intervals!")
                if st.button("🚀 Upgrade to Pro"):
                    checkout = requests.post(f"{API_URL}/create-checkout-session", json={"email": st.session_state.user_email})
                    if checkout.ok:
                        url = checkout.json().get("checkout_url")
                        st.markdown(f"[💳 Proceed to Payment]({url})")
        else:
            st.error("Backend returned an error. Check backend status.")
    except Exception as e:
        st.error("❌ Failed to connect to prediction server.")
        st.exception(e)

# ----- Route -----
if not st.session_state.authenticated:
    login()
else:
    dashboard()

# ----- Close theme wrapper -----
st.markdown("</div>", unsafe_allow_html=True)
