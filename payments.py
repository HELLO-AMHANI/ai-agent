# payments.py — AMHANi | Phase 4: Paystack Integration
import os
import hmac
import hashlib
import json
import requests
from dotenv import load_dotenv

load_dotenv()

PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY", "")
PAYSTACK_PUBLIC = os.getenv("PAYSTACK_PUBLIC_KEY", "")
PLAN_CODE       = os.getenv("PAYSTACK_PLAN_CODE", "")
BASE_URL        = "https://api.paystack.co"

HEADERS = {
    "Authorization": f"Bearer {PAYSTACK_SECRET}",
    "Content-Type":  "application/json",
}


# ── Step 2: Initialise a subscription payment ─────────────────────────────────
def create_subscription_link(email: str, user_id: str) -> str:
    """
    Creates a Paystack payment initialisation for a subscription plan.
    Returns the payment authorisation URL to redirect the user to.
    """
    payload = {
        "email":    email,
        "plan":     PLAN_CODE,
        "amount":   999900,           # ₦9,999 in kobo (Paystack uses kobo)
        "currency": "NGN",
        "metadata": {
            "user_id":    user_id,
            "product":    "CONSULTAMHANi",
            "cancel_action": os.getenv("APP_URL", "http://localhost:8501"),
        },
        "callback_url": os.getenv("PAYSTACK_CALLBACK_URL", "http://localhost:8501"),
    }

    try:
        response = requests.post(
            f"{BASE_URL}/transaction/initialize",
            headers=HEADERS,
            json=payload,
            timeout=10,
        )
        data = response.json()
        if data.get("status"):
            return data["data"]["authorization_url"]
        else:
            raise RuntimeError(f"Paystack error: {data.get('message', 'Unknown error')}")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Network error contacting Paystack: {e}")


# ── Step 3: Verify a transaction by reference ─────────────────────────────────
def verify_transaction(reference: str) -> dict:
    """
    Verify a completed Paystack transaction.
    Returns the transaction data dict or raises on failure.
    """
    try:
        response = requests.get(
            f"{BASE_URL}/transaction/verify/{reference}",
            headers=HEADERS,
            timeout=10,
        )
        data = response.json()
        if data.get("status") and data["data"]["status"] == "success":
            return data["data"]
        else:
            raise RuntimeError(f"Transaction not successful: {data.get('message')}")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Network error verifying transaction: {e}")


# ── Step 3: Webhook signature verification ────────────────────────────────────
def verify_webhook_signature(payload_bytes: bytes, signature: str) -> bool:
    """
    Verify that a webhook came from Paystack.
    Paystack signs with HMAC-SHA512 using your secret key.
    """
    expected = hmac.new(
        PAYSTACK_SECRET.encode("utf-8"),
        payload_bytes,
        hashlib.sha512,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


# ── Step 3: Process incoming webhook ─────────────────────────────────────────
def process_webhook(payload_bytes: bytes, signature: str) -> dict:
    """
    Validates and processes a Paystack webhook.
    Returns a result dict: { "action": str, "user_id": str, "email": str }
    Call this from your webhook endpoint (Flask/FastAPI in production).
    """
    if not verify_webhook_signature(payload_bytes, signature):
        raise PermissionError("Invalid webhook signature — possible spoofed request.")

    event = json.loads(payload_bytes)
    event_type = event.get("event", "")
    data       = event.get("data", {})

    # Subscription created / charge success → activate user
    if event_type in ("subscription.create", "charge.success"):
        metadata = data.get("metadata", {})
        return {
            "action":  "activate",
            "user_id": metadata.get("user_id", ""),
            "email":   data.get("customer", {}).get("email", ""),
            "plan":    data.get("plan", {}).get("plan_code", ""),
            "raw":     event,
        }

    # Subscription disabled / not renewed → deactivate user
    if event_type in ("subscription.disable", "invoice.update"):
        metadata = data.get("metadata", {})
        return {
            "action":  "deactivate",
            "user_id": metadata.get("user_id", ""),
            "email":   data.get("customer", {}).get("email", ""),
            "raw":     event,
        }

    return {"action": "ignore", "raw": event}


# ── Step 6: Fetch subscription status from Paystack ──────────────────────────
def get_subscription_status(email: str) -> str:
    """
    Check if an email has an active Paystack subscription.
    Returns 'active', 'inactive', or 'not_found'.
    """
    try:
        response = requests.get(
            f"{BASE_URL}/subscription?email={email}",
            headers=HEADERS,
            timeout=10,
        )
        data = response.json()
        subscriptions = data.get("data", [])
        for sub in subscriptions:
            if sub.get("status") == "active" and sub.get("plan", {}).get("plan_code") == PLAN_CODE:
                return "active"
        return "inactive"
    except Exception:
        return "not_found"


# ── Step 6: Cancel a subscription ────────────────────────────────────────────
def cancel_subscription(subscription_code: str, email_token: str) -> bool:
    """
    Cancel a Paystack subscription.
    subscription_code and email_token come from the subscription object.
    """
    try:
        response = requests.post(
            f"{BASE_URL}/subscription/disable",
            headers=HEADERS,
            json={
                "code":         subscription_code,
                "token":        email_token,
            },
            timeout=10,
        )
        return response.json().get("status", False)
    except Exception:
        return False
