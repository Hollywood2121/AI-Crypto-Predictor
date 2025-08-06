import streamlit as st

st.set_page_config(page_title="AI Crypto Predictor", layout="wide")

st.title("🚀 AI Crypto Predictor")
st.markdown("Welcome to your AI-powered crypto forecasting app!")

if st.button("Test Button"):
    st.success("Button clicked — Streamlit is working!")
git add ai_crypto_predictor.py
git commit -m "Add basic Streamlit UI to test deployment"
git push origin main
