# =============================================================
# chat_store.py — AMHANi ENTERPRISE
# NVIDIA FIX: Same lazy-init pattern as auth.py.
# Previous version also called create_client() at module level.
# =============================================================

import os
import time
from datetime import datetime

_sb_chat = None

def _get_db():
    global _sb_chat
    if _sb_chat is not None:
        return _sb_chat
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    if not url or not key or ".supabase.co" not in url:
        return None
    try:
        from supabase import create_client
        _sb_chat = create_client(url, key)
        return _sb_chat
    except Exception as e:
        print(f"[chat_store] client error: {e}")
        return None


def _retry(fn, attempts=3):
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            last = e
            err = str(e).lower()
            is_net = any(x in err for x in ["errno -2","connection","timeout","socket","network"])
            if not is_net:
                break
            if i < attempts - 1:
                time.sleep(1.0 * (i + 1))
    raise last if last else Exception("unknown error")


def save_message(user_id: str, role: str, content: str) -> None:
    if not user_id or not user_id.strip():
        return
    if not content or not content.strip():
        return
    if role not in ("user", "assistant"):
        return
    try:
        db = _get_db()
        if not db:
            return
        _retry(lambda: db.table("chat_logs").insert({
            "user_id":    user_id.strip(),
            "role":       role,
            "content":    content.strip(),
            "created_at": datetime.utcnow().isoformat(),
        }).execute())
    except Exception as e:
        print(f"[chat_store] save error: {e}")


def load_messages(user_id: str, limit: int = 100) -> list:
    if not user_id or not user_id.strip():
        return []
    try:
        db = _get_db()
        if not db:
            return []
        result = _retry(lambda: (
            db.table("chat_logs")
            .select("role, content")
            .eq("user_id", user_id.strip())
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        ))
        return [
            {"role": r["role"], "content": r["content"]}
            for r in result.data
            if r.get("role") in ("user", "assistant")
            and (r.get("content") or "").strip()
        ]
    except Exception as e:
        print(f"[chat_store] load error: {e}")
        return []


def clear_chat(user_id: str) -> None:
    if not user_id or not user_id.strip():
        return
    try:
        db = _get_db()
        if db:
            _retry(lambda: db.table("chat_logs").delete().eq("user_id", user_id.strip()).execute())
    except Exception as e:
        print(f"[chat_store] clear error: {e}")
