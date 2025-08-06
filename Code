# AI Crypto Market Predictor (w/ Accounts, Plans, 2FA, Stripe, Email Reset, and Charts)

import smtplib
from email.mime.text import MIMEText
from fastapi import FastAPI, Request, Header
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI()

# === Email OTP Delivery ===
def send_email_otp(recipient_email, otp):
    try:
        smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
        smtp_port = int(os.environ.get("SMTP_PORT", 587))
        smtp_user = os.environ.get("SMTP_USER")
        smtp_pass = os.environ.get("SMTP_PASS")

        msg = MIMEText(f"Your 2FA code is: {otp}")
        msg["Subject"] = "Your Crypto Predictor 2FA Code"
        msg["From"] = smtp_user
        msg["To"] = recipient_email

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, recipient_email, msg.as_string())
    except Exception as e:
        print(f"[ERROR] Email send failed: {e}")

# === Stripe Setup with Real Checkout Session and Webhook Support ===
import stripe

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")

STRIPE_PRICE_ID_PRO = os.environ.get("STRIPE_PRICE_ID_PRO", "price_abc123")
STRIPE_SUCCESS_URL = os.environ.get("STRIPE_SUCCESS_URL", "https://yourdomain.com/success")
STRIPE_CANCEL_URL = os.environ.get("STRIPE_CANCEL_URL", "https://yourdomain.com/cancel")
STRIPE_ENDPOINT_SECRET = os.environ.get("STRIPE_ENDPOINT_SECRET", "whsec_example")

def stripe_checkout_link(plan):
    if plan != "pro":
        return ""
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                'price': STRIPE_PRICE_ID_PRO,
                'quantity': 1,
            }],
            mode="subscription",
            success_url=STRIPE_SUCCESS_URL,
            cancel_url=STRIPE_CANCEL_URL,
        )
        return session.url
    except Exception as e:
        print(f"[ERROR] Stripe session creation failed: {e}")
        return ""

def upgrade_user_to_pro(email):
    try:
        conn = sqlite3.connect("signals.db")
        c = conn.cursor()
        c.execute("UPDATE users SET plan='pro' WHERE email=?", (email,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[ERROR] Failed to upgrade user: {e}")

@app.post("/stripe-webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    payload = await request.body()
    sig_header = stripe_signature
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_ENDPOINT_SECRET
        )
        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            customer_email = session.get('customer_email')
            if customer_email:
                upgrade_user_to_pro(customer_email)
        return JSONResponse({"status": "success"})
    except Exception as e:
        print(f"[ERROR] Stripe webhook error: {e}")
        return JSONResponse(status_code=400, content={"error": str(e)})

# === Coin List Fetching ===
def fetch_top_coins(limit=100):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page={limit}&page=1"
        response = requests.get(url)
        if response.status_code == 200:
            return [coin["id"] for coin in response.json()]
        else:
            print("[ERROR] Failed to fetch coin list from CoinGecko")
            return []
    except Exception as e:
        print(f"[ERROR] CoinGecko API error: {e}")
        return []

# === Updated Dashboard Start ===
# (dashboard logic remains unchanged)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
