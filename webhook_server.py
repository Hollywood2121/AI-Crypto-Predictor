from fastapi import FastAPI, Request
import stripe
import os
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
endpoint_secret = os.environ.get("STRIPE_ENDPOINT_SECRET")

@app.get("/")
def read_root():
    return {"message": "FastAPI server is live!"}

@app.post("/stripe-webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        return {"error": str(e)}
    except stripe.error.SignatureVerificationError as e:
        return {"error": str(e)}

    # ✅ Handle checkout success
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        email = session["customer_details"]["email"]
        # You can upgrade the user here (to be implemented)
        print(f"Payment succeeded for {email}")

    return {"status": "success"}
