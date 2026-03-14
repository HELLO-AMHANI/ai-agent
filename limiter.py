# =============================================================
# limiter.py — AMHANi ENTERPRISE · Usage Limiting
# FILE 5 OF 7 — FULL REPLACEMENT
# Delete everything in your existing limiter.py and paste this.
# =============================================================

import json
import os
import uuid
from datetime import datetime, timedelta

import streamlit as st

# ── Config ────────────────────────────────────────────────────
FREE_LIMIT   = 5          # free questions before paywall
RESET_HOURS  = 24         # hours before count resets
DATA_FILE    = "usage_data.json"


# ── Persistence helpers ───────────────────────────────────────

def _load() -> dict:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _save(data: dict) -> None:
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        print(f"[limiter] save error: {e}")


# ── Visitor ID ────────────────────────────────────────────────

def get_visitor_id() -> str:
    """
    Return a stable visitor UUID for this browser session.
    Stored in st.session_state so it persists across Streamlit reruns
    within the same browser tab.
    """
    if "visitor_id" not in st.session_state:
        st.session_state["visitor_id"] = str(uuid.uuid4())
    return st.session_state["visitor_id"]


# ── Usage record helpers ──────────────────────────────────────

def _get_record(visitor_id: str) -> dict:
    data   = _load()
    record = data.get(visitor_id, {"count": 0, "first_seen": None, "last_seen": None})

    # Auto-reset if window has elapsed
    if record.get("first_seen"):
        first = datetime.fromisoformat(record["first_seen"])
        if datetime.utcnow() - first > timedelta(hours=RESET_HOURS):
            record = {"count": 0, "first_seen": None, "last_seen": None}

    return record


def _save_record(visitor_id: str, record: dict) -> None:
    data = _load()
    data[visitor_id] = record
    _save(data)


# ── Public API ────────────────────────────────────────────────

def get_usage(visitor_id: str) -> int:
    """Return number of questions used by this visitor."""
    return _get_record(visitor_id).get("count", 0)


def increment_usage(visitor_id: str) -> None:
    """Increment the question count for this visitor."""
    record = _get_record(visitor_id)
    now    = datetime.utcnow().isoformat()

    record["count"] += 1
    record["last_seen"] = now
    if not record.get("first_seen"):
        record["first_seen"] = now

    _save_record(visitor_id, record)


def is_limited(visitor_id: str) -> bool:
    """Return True if this visitor has used all free questions."""
    return get_usage(visitor_id) >= FREE_LIMIT


def remaining(visitor_id: str) -> int:
    """Return number of free questions remaining for this visitor."""
    return max(0, FREE_LIMIT - get_usage(visitor_id))


def reset_ip(visitor_id: str) -> None:
    """Reset usage count for a visitor (admin use)."""
    data = _load()
    if visitor_id in data:
        del data[visitor_id]
        _save(data)


def get_all_stats() -> dict:
    """Return aggregated stats for the admin dashboard."""
    data           = _load()
    total_visitors = len(data)
    total_q        = sum(r.get("count", 0) for r in data.values())
    hit_paywall    = sum(1 for r in data.values() if r.get("count", 0) >= FREE_LIMIT)

    # Active today
    today = datetime.utcnow().date()
    active_today = sum(
        1 for r in data.values()
        if r.get("last_seen") and
        datetime.fromisoformat(r["last_seen"]).date() == today
    )

    return {
        "total_visitors": total_visitors,
        "total_questions": total_q,
        "hit_paywall": hit_paywall,
        "active_today": active_today,
        "visitors": data,
    }
