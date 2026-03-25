# =============================================================
# chat_store.py — AMHANi ENTERPRISE
# Persistent full chat log per user via Supabase.
# FIX: Added strict user_id validation before every save/load
# to prevent messages being saved with null user_id (which
# caused wrong messages appearing after re-login).
# =============================================================

import os
from datetime import datetime
from supabase import create_client
from dotenv import load_dotenv
load_dotenv()

_sb = None

def _db():
    global _sb
    if not _sb:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if url and key:
            _sb = create_client(url, key)
    return _sb


def save_message(user_id: str, role: str, content: str) -> None:
    """
    Save a single message to Supabase chat_logs.
    Guards: user_id must be non-empty, content must be non-empty,
    role must be 'user' or 'assistant'.
    """
    # Strict validation — prevents null/garbage rows in DB
    if not user_id or not user_id.strip():
        return
    if not content or not content.strip():
        return
    if role not in ("user", "assistant"):
        return
    try:
        db = _db()
        if not db:
            return
        db.table("chat_logs").insert({
            "user_id":    user_id.strip(),
            "role":       role,
            "content":    content.strip(),
            "created_at": datetime.utcnow().isoformat(),
        }).execute()
    except Exception as e:
        print(f"[chat_store] save error: {e}")


def load_messages(user_id: str, limit: int = 100) -> list:
    """
    Load the last N messages for a specific user.
    Returns list of {"role": ..., "content": ...} dicts.
    Filters out any rows with empty content (data integrity guard).
    """
    if not user_id or not user_id.strip():
        return []
    try:
        db = _db()
        if not db:
            return []
        result = (
            db.table("chat_logs")
            .select("role, content")
            .eq("user_id", user_id.strip())
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        )
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
    """Delete all chat messages for a user."""
    if not user_id or not user_id.strip():
        return
    try:
        db = _db()
        if db:
            db.table("chat_logs").delete().eq("user_id", user_id.strip()).execute()
    except Exception as e:
        print(f"[chat_store] clear error: {e}")
