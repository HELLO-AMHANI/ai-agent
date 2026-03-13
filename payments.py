# payments.py — AMHANi | Phase 4: Paystack Integration
# All secrets loaded from config.py (works locally AND on Streamlit Cloud)

import hmac
import hashlib
import json
import requests
from config import (
    PAYSTACK_SECRET_KEY,
    PAYSTACK_PUBLIC_KEY,
    PAYSTACK_PLAN_CODE,
    PAYSTACK_CALLBACK_URL,
)

BASE_URL = "https://api.paystack.co"

HEADERS = {
    "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
    "Content-Type":  "application/json",
}


# ── Initialise a subscription payment ────────────────────────────────────────
def create_subscription_link(email: str, user_id: str) -> str:
    """
    Creates a Paystack subscription payment link.
    Returns the authorisation URL to redirect the user to.
    """
    if not PAYSTACK_SECRET_KEY:
        raise RuntimeError(
            "PAYSTACK_SECRET_KEY is missing.\n"
            "Locally: add it to .env\n"
            "Streamlit Cloud: add it in App Settings → Secrets."
        )

    payload = {
        "email":        email,
        "plan":         PAYSTACK_PLAN_CODE,
        "amount":       999900,   # ₦9,999 in kobo
        "currency":     "NGN",
        "metadata": {
            "user_id":       user_id,
            "product":       "CONSULTAMHANi",
            "cancel_action": PAYSTACK_CALLBACK_URL,
        },
        "callback_url": PAYSTACK_CALLBACK_URL,
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


# ── Verify a transaction by reference ────────────────────────────────────────
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


# ── Webhook signature verification ───────────────────────────────────────────
def verify_webhook_signature(payload_bytes: bytes, signature: str) -> bool:
    """
    Verify that a webhook came from Paystack.
    Uses HMAC-SHA512 with your secret key.
    """
    expected = hmac.new(
        PAYSTACK_SECRET_KEY.encode("utf-8"),
        payload_bytes,
        hashlib.sha512,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


# ── Process incoming webhook ──────────────────────────────────────────────────
def process_webhook(payload_bytes: bytes, signature: str) -> dict:
    """
    Validates and processes a Paystack webhook event.
    Returns: { "action": str, "user_id": str, "email": str }
    """
    if not verify_webhook_signature(payload_bytes, signature):
        raise PermissionError("Invalid webhook signature — possible spoofed request.")

    event      = json.loads(payload_bytes)
    event_type = event.get("event", "")
    data       = event.get("data", {})

    if event_type in ("subscription.create", "charge.success"):
        metadata = data.get("metadata", {})
        return {
            "action":  "activate",
            "user_id": metadata.get("user_id", ""),
            "email":   data.get("customer", {}).get("email", ""),
            "plan":    data.get("plan", {}).get("plan_code", ""),
            "raw":     event,
        }

    if event_type in ("subscription.disable", "invoice.update"):
        metadata = data.get("metadata", {})
        return {
            "action":  "deactivate",
            "user_id": metadata.get("user_id", ""),
            "email":   data.get("customer", {}).get("email", ""),
            "raw":     event,
        }

    return {"action": "ignore", "raw": event}


# ── Fetch subscription status from Paystack ───────────────────────────────────
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
        data          = response.json()
        subscriptions = data.get("data", [])
        for sub in subscriptions:
            if sub.get("status") == "active" and sub.get("plan", {}).get("plan_code") == PAYSTACK_PLAN_CODE:
                return "active"
        return "inactive"
    except Exception:
        return "not_found"


# ── Cancel a subscription ─────────────────────────────────────────────────────
def cancel_subscription(subscription_code: str, email_token: str) -> bool:
    """Cancel a Paystack subscription by code and email token."""
    try:
        response = requests.post(
            f"{BASE_URL}/subscription/disable",
            headers=HEADERS,
            json={"code": subscription_code, "token": email_token},
            timeout=10,
        )
        return response.json().get("status", False)
    except Exception:
        return False
