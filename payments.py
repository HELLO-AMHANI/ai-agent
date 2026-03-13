# payments.py — CONSULTAMHANi | Paystack Payment Integration

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

BASE_URL       = "https://api.paystack.co"
PRICE_KOBO     = 2999900   # ₦29,999 in kobo
PRICE_DISPLAY  = "₦29,999"

HEADERS = {
    "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
    "Content-Type":  "application/json",
}


def create_subscription_link(email: str, user_id: str) -> str:
    """
    Initialise a Paystack subscription payment.
    Returns the payment authorisation URL.
    """
    if not PAYSTACK_SECRET_KEY:
        raise RuntimeError(
            "PAYSTACK_SECRET_KEY is missing. "
            "Add it to your secrets."
        )
    payload = {
        "email":        email,
        "plan":         PAYSTACK_PLAN_CODE,
        "amount":       PRICE_KOBO,
        "currency":     "NGN",
        "metadata": {
            "user_id":       user_id,
            "product":       "CONSULTAMHANi",
            "cancel_action": PAYSTACK_CALLBACK_URL,
        },
        "callback_url": PAYSTACK_CALLBACK_URL,
    }
    try:
        res  = requests.post(
            f"{BASE_URL}/transaction/initialize",
            headers=HEADERS, json=payload, timeout=10,
        )
        data = res.json()
        if data.get("status"):
            return data["data"]["authorization_url"]
        raise RuntimeError(f"Paystack: {data.get('message', 'Unknown error')}")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Network error: {e}")


def verify_transaction(reference: str) -> dict:
    """Verify a completed Paystack transaction by reference."""
    try:
        res  = requests.get(
            f"{BASE_URL}/transaction/verify/{reference}",
            headers=HEADERS, timeout=10,
        )
        data = res.json()
        if data.get("status") and data["data"]["status"] == "success":
            return data["data"]
        raise RuntimeError(f"Not successful: {data.get('message')}")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Network error: {e}")


def verify_webhook_signature(payload_bytes: bytes, signature: str) -> bool:
    """Verify a Paystack webhook using HMAC-SHA512."""
    expected = hmac.new(
        PAYSTACK_SECRET_KEY.encode("utf-8"),
        payload_bytes,
        hashlib.sha512,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def process_webhook(payload_bytes: bytes, signature: str) -> dict:
    """Process a validated Paystack webhook event."""
    if not verify_webhook_signature(payload_bytes, signature):
        raise PermissionError("Invalid webhook signature.")
    event      = json.loads(payload_bytes)
    event_type = event.get("event", "")
    data       = event.get("data", {})
    if event_type in ("subscription.create", "charge.success"):
        meta = data.get("metadata", {})
        return {
            "action":  "activate",
            "user_id": meta.get("user_id", ""),
            "email":   data.get("customer", {}).get("email", ""),
            "raw":     event,
        }
    if event_type in ("subscription.disable", "invoice.update"):
        meta = data.get("metadata", {})
        return {
            "action":  "deactivate",
            "user_id": meta.get("user_id", ""),
            "email":   data.get("customer", {}).get("email", ""),
            "raw":     event,
        }
    return {"action": "ignore", "raw": event}


def get_subscription_status(email: str) -> str:
    """Check if an email has an active CONSULTAMHANi subscription."""
    try:
        res  = requests.get(
            f"{BASE_URL}/subscription?email={email}",
            headers=HEADERS, timeout=10,
        )
        data = res.json()
        for sub in data.get("data", []):
            if (sub.get("status") == "active" and
                    sub.get("plan", {}).get("plan_code") == PAYSTACK_PLAN_CODE):
                return "active"
        return "inactive"
    except Exception:
        return "not_found"


def cancel_subscription(subscription_code: str, email_token: str) -> bool:
    """Cancel a Paystack subscription."""
    try:
        res = requests.post(
            f"{BASE_URL}/subscription/disable",
            headers=HEADERS,
            json={"code": subscription_code, "token": email_token},
            timeout=10,
        )
        return res.json().get("status", False)
    except Exception:
        return False
