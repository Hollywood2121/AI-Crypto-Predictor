# AI Crypto Predictor

An AI-powered web app for crypto market predictions with:
- User login and account creation
- Free and Pro plans (via Stripe)
- Two-Factor Authentication (2FA) via email
- Slack and Telegram alerts
- Streamlit dashboard
- FastAPI webhook server

---

## 🚀 Features
- 🔐 User authentication and 2FA
- 💸 Stripe payment integration for Pro plan
- 📬 Email-based OTP for login & password reset
- 📈 AI-powered predictions for top trending cryptos
- 🔁 Retraining option + confidence tracking
- 📊 Streamlit dashboard with accuracy graphs

---

## 📁 Project Structure
```
/ai-crypto-predictor/
├── ai_crypto_predictor.py       # Streamlit UI
├── webhook_server.py            # FastAPI webhook backend
├── requirements.txt             # All dependencies
├── .env                         # Secrets file (excluded from Git)
├── Procfile                     # Render deployment command
```

---

## ⚙️ Environment Variables (.env)
```
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASS=your_app_password

STRIPE_SECRET_KEY=sk_test_xxx
STRIPE_PRICE_ID_PRO=price_xxx
STRIPE_SUCCESS_URL=https://yourdomain.com/success
STRIPE_CANCEL_URL=https://yourdomain.com/cancel
STRIPE_ENDPOINT_SECRET=whsec_xxx
```

---

## 💻 Run Locally
```bash
pip install -r requirements.txt
python ai_crypto_predictor.py     # Launch Streamlit dashboard
uvicorn webhook_server:app --reload --port 8000  # Start FastAPI backend
```

---

## 🐳 Docker Support

### Dockerfile
```Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY . .

RUN pip install --upgrade pip && \
    pip install -r requirements.txt

EXPOSE 8000

CMD ["uvicorn", "webhook_server:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Build & Run
```bash
docker build -t crypto-predictor .
docker run -d -p 8000:8000 --env-file .env crypto-predictor
```

---

## 🌐 Deploy on Render (FastAPI backend)
1. Create new web service
2. Use `uvicorn webhook_server:app --host 0.0.0.0 --port 8000` as start command
3. Add `.env` variables under Environment tab
4. Set up Stripe webhook pointing to `/stripe-webhook`

## 🚀 Deploy on Streamlit Cloud
1. Connect GitHub repo
2. Set app file to `ai_crypto_predictor.py`
3. Paste `.env` values in Streamlit → Settings → Secrets

---

## ✅ Stripe Webhook Event
Ensure your Stripe dashboard sends `checkout.session.completed` events to:
```
https://your-backend.onrender.com/stripe-webhook
```

---

## 📬 Credits
Built with ❤️ using Streamlit, FastAPI, Stripe, and Python ML libraries.
# AI-Crypto-Predictor
