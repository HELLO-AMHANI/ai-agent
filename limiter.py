# limiter.py — CONSULTAMHANi | Usage Rate Limiter

import json
import time
from pathlib import Path

LIMIT_FILE   = Path("usage_data.json")
FREE_LIMIT   = 5
RESET_HOURS  = 24


def _load() -> dict:
    if LIMIT_FILE.exists():
        try:
            with open(LIMIT_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def _save(data: dict) -> None:
    try:
        with open(LIMIT_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except IOError:
        pass


def _now() -> float:
    return time.time()


def _reset_seconds() -> float:
    return RESET_HOURS * 3600


def get_usage(ip: str) -> dict:
    data   = _load()
    record = data.get(ip)
    now    = _now()
    if record is None:
        return {"count": 0, "first_seen": now, "last_seen": now}
    elapsed = now - record.get("first_seen", now)
    if elapsed >= _reset_seconds():
        return {"count": 0, "first_seen": now, "last_seen": now}
    return record


def increment_usage(ip: str) -> int:
    data   = _load()
    record = get_usage(ip)
    now    = _now()
    record["count"]    += 1
    record["last_seen"] = now
    if record["count"] == 1:
        record["first_seen"] = now
    data[ip] = record
    _save(data)
    return record["count"]


def is_limited(ip: str) -> bool:
    return get_usage(ip)["count"] >= FREE_LIMIT


def remaining(ip: str) -> int:
    return max(0, FREE_LIMIT - get_usage(ip)["count"])


def reset_ip(ip: str) -> None:
    data = _load()
    if ip in data:
        del data[ip]
        _save(data)


def get_all_stats() -> dict:
    data         = _load()
    total_ips    = len(data)
    total_q      = sum(r.get("count", 0) for r in data.values())
    hit_paywall  = sum(1 for r in data.values() if r.get("count", 0) >= FREE_LIMIT)
    active_today = sum(
        1 for r in data.values()
        if _now() - r.get("last_seen", 0) < 86400
    )
    return {
        "total_visitors":  total_ips,
        "total_questions": total_q,
        "hit_paywall":     hit_paywall,
        "active_today":    active_today,
        "conversion_rate": f"{(hit_paywall / total_ips * 100):.1f}%" if total_ips else "0%",
        "avg_questions":   f"{(total_q / total_ips):.1f}" if total_ips else "0",
        "raw":             data,
    }
