# limiter.py — AMHANi | Phase 3: Persistent IP-Based Rate Limiter
import json
import os
import time
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
LIMIT_FILE   = Path("usage_data.json")   # persists between restarts
FREE_LIMIT   = 5                          # free questions per IP
RESET_HOURS  = 24                         # reset window in hours


# ── Internal helpers ──────────────────────────────────────────────────────────
def _load() -> dict:
    """Load usage data from disk. Returns empty dict if file missing."""
    if LIMIT_FILE.exists():
        try:
            with open(LIMIT_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def _save(data: dict) -> None:
    """Persist usage data to disk."""
    with open(LIMIT_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _now() -> float:
    return time.time()


def _reset_window_seconds() -> float:
    return RESET_HOURS * 3600


# ── Public API ────────────────────────────────────────────────────────────────
def get_usage(ip: str) -> dict:
    """
    Return usage record for an IP.
    Schema: { "count": int, "first_seen": float, "last_seen": float }
    Auto-resets if the reset window has passed.
    """
    data   = _load()
    record = data.get(ip)
    now    = _now()

    if record is None:
        # First visit
        return {"count": 0, "first_seen": now, "last_seen": now}

    elapsed = now - record.get("first_seen", now)
    if elapsed >= _reset_window_seconds():
        # Window expired — treat as fresh visitor
        return {"count": 0, "first_seen": now, "last_seen": now}

    return record


def increment_usage(ip: str) -> int:
    """
    Increment the question count for an IP.
    Returns the NEW count after incrementing.
    """
    data   = _load()
    record = get_usage(ip)       # handles reset logic
    now    = _now()

    record["count"]     += 1
    record["last_seen"]  = now

    if record["count"] == 1:
        record["first_seen"] = now   # anchor the window on first question

    data[ip] = record
    _save(data)
    return record["count"]


def is_limited(ip: str) -> bool:
    """Returns True if this IP has hit or exceeded the free limit."""
    return get_usage(ip)["count"] >= FREE_LIMIT


def remaining(ip: str) -> int:
    """Returns how many free questions this IP still has."""
    used = get_usage(ip)["count"]
    return max(0, FREE_LIMIT - used)


def reset_ip(ip: str) -> None:
    """Manually reset a specific IP (admin use)."""
    data = _load()
    if ip in data:
        del data[ip]
        _save(data)


# ── Analytics ─────────────────────────────────────────────────────────────────
def get_all_stats() -> dict:
    """
    Returns aggregate stats for the admin view.
    """
    data          = _load()
    total_ips     = len(data)
    total_q       = sum(r.get("count", 0) for r in data.values())
    hit_paywall   = sum(1 for r in data.values() if r.get("count", 0) >= FREE_LIMIT)
    active_today  = sum(
        1 for r in data.values()
        if _now() - r.get("last_seen", 0) < 86400
    )

    return {
        "total_visitors":     total_ips,
        "total_questions":    total_q,
        "hit_paywall":        hit_paywall,
        "active_today":       active_today,
        "conversion_rate":    f"{(hit_paywall / total_ips * 100):.1f}%" if total_ips else "0%",
        "avg_questions":      f"{(total_q / total_ips):.1f}" if total_ips else "0",
        "raw":                data,
    }
