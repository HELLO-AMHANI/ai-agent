# =============================================================
# limiter.py — AMHANi ENTERPRISE
# NVIDIA FIX:
#   - usage_data.json is a LOCAL file. Streamlit Cloud runs
#     app.py and admin.py in SEPARATE containers with SEPARATE
#     filesystems. They can never share a JSON file.
#   - FIX: Moved visitor tracking to Supabase visitor_sessions
#     table. Both app.py and admin.py read from the same DB.
#   - JSON fallback kept for local development (no Supabase needed).
#   - 24h reset logic preserved exactly.
# =============================================================

import json
import os
import uuid
from datetime import datetime, timedelta

import streamlit as st

# ── Config ────────────────────────────────────────────────────
FREE_LIMIT  = 5
RESET_HOURS = 24
DATA_FILE   = "usage_data.json"   # local fallback only

# ── Supabase client (optional — gracefully degrades to JSON) ──
_sb_limiter = None

def _get_supabase():
    global _sb_limiter
    if _sb_limiter is None:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if url and key:
            try:
                from supabase import create_client
                _sb_limiter = create_client(url, key)
            except Exception:
                pass
    return _sb_limiter


# ════════════════════════════════════════════════════════════════
# SUPABASE BACKEND  (used on Streamlit Cloud)
# ════════════════════════════════════════════════════════════════

def _sb_get_record(visitor_id: str) -> dict:
    """Load visitor record from Supabase."""
    try:
        db = _get_supabase()
        if not db:
            return None
        r = (
            db.table("visitor_sessions")
            .select("*")
            .eq("visitor_id", visitor_id)
            .limit(1)
            .execute()
        )
        if r.data:
            return r.data[0]
    except Exception:
        pass
    return None


def _sb_upsert_record(visitor_id: str, record: dict) -> None:
    """Write visitor record to Supabase."""
    try:
        db = _get_supabase()
        if not db:
            return
        db.table("visitor_sessions").upsert({
            "visitor_id":  visitor_id,
            "count":       record.get("count", 0),
            "first_seen":  record.get("first_seen"),
            "last_seen":   record.get("last_seen"),
        }).execute()
    except Exception:
        pass


def _sb_delete_record(visitor_id: str) -> None:
    try:
        db = _get_supabase()
        if db:
            db.table("visitor_sessions").delete().eq("visitor_id", visitor_id).execute()
    except Exception:
        pass


def _sb_all_records() -> dict:
    """Return all visitor records as a dict keyed by visitor_id."""
    try:
        db = _get_supabase()
        if not db:
            return {}
        r = db.table("visitor_sessions").select("*").execute()
        return {row["visitor_id"]: row for row in (r.data or [])}
    except Exception:
        return {}


# ════════════════════════════════════════════════════════════════
# JSON FALLBACK BACKEND  (local dev without Supabase)
# ════════════════════════════════════════════════════════════════

def _json_load() -> dict:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _json_save(data: dict) -> None:
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════
# UNIFIED RECORD HELPERS  (routes to Supabase or JSON)
# ════════════════════════════════════════════════════════════════

def _get_record(visitor_id: str) -> dict:
    """Get usage record, checking 24h reset window."""
    use_supabase = _get_supabase() is not None

    if use_supabase:
        row = _sb_get_record(visitor_id)
        if row is None:
            return {"count": 0, "first_seen": None, "last_seen": None}
        record = {
            "count":      row.get("count", 0),
            "first_seen": row.get("first_seen"),
            "last_seen":  row.get("last_seen"),
        }
    else:
        data   = _json_load()
        record = data.get(visitor_id)
        if record is None:
            return {"count": 0, "first_seen": None, "last_seen": None}

    # 24h reset check
    first_seen = record.get("first_seen")
    if first_seen:
        try:
            first   = datetime.fromisoformat(first_seen)
            elapsed = datetime.utcnow() - first
            if elapsed.total_seconds() >= RESET_HOURS * 3600:
                return {"count": 0, "first_seen": None, "last_seen": None}
        except Exception:
            return {"count": 0, "first_seen": None, "last_seen": None}

    return record


def _save_record(visitor_id: str, record: dict) -> None:
    if _get_supabase() is not None:
        _sb_upsert_record(visitor_id, record)
    else:
        data = _json_load()
        data[visitor_id] = record
        _json_save(data)


# ════════════════════════════════════════════════════════════════
# VISITOR ID
# ════════════════════════════════════════════════════════════════

def get_visitor_id() -> str:
    if "visitor_id" not in st.session_state:
        st.session_state["visitor_id"] = str(uuid.uuid4())
    return st.session_state["visitor_id"]


# ════════════════════════════════════════════════════════════════
# PUBLIC API
# ════════════════════════════════════════════════════════════════

def get_usage(visitor_id: str) -> int:
    return _get_record(visitor_id).get("count", 0)


def increment_usage(visitor_id: str) -> None:
    record = _get_record(visitor_id)
    now    = datetime.utcnow().isoformat()
    record["count"] += 1
    record["last_seen"] = now
    if not record.get("first_seen"):
        record["first_seen"] = now
    _save_record(visitor_id, record)


def is_limited(visitor_id: str) -> bool:
    return get_usage(visitor_id) >= FREE_LIMIT


def remaining(visitor_id: str) -> int:
    return max(0, FREE_LIMIT - get_usage(visitor_id))


def reset_ip(visitor_id: str) -> None:
    if _get_supabase() is not None:
        _sb_delete_record(visitor_id)
    else:
        data = _json_load()
        data.pop(visitor_id, None)
        _json_save(data)


def get_all_stats() -> dict:
    """
    Aggregate stats for admin dashboard.
    Now reads from Supabase so admin sees live data
    regardless of which server is running app.py.
    """
    if _get_supabase() is not None:
        data = _sb_all_records()
    else:
        data = _json_load()

    now   = datetime.utcnow()
    today = now.date()

    total_visitors = len(data)
    total_q        = 0
    hit_paywall    = 0
    active_today   = 0
    active_now     = 0   # active in last 30 minutes

    for row in data.values():
        count     = row.get("count", 0)
        last_seen = row.get("last_seen")
        first_seen= row.get("first_seen")

        total_q += count
        if count >= FREE_LIMIT:
            hit_paywall += 1

        if last_seen:
            try:
                ls = datetime.fromisoformat(last_seen)
                if ls.date() == today:
                    active_today += 1
                if (now - ls).total_seconds() < 1800:   # 30 min
                    active_now += 1
            except Exception:
                pass

    return {
        "total_visitors": total_visitors,
        "total_questions": total_q,
        "hit_paywall":     hit_paywall,
        "active_today":    active_today,
        "active_now":      active_now,
        "visitors":        data,
    }
