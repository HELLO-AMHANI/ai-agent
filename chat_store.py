# =============================================================
# chat_store.py — AMHANi ENTERPRISE
# Persistent chat log per user via Supabase
# STATUS: No changes needed — this file was already correct
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
    try:
        db = _db()
        if not db or not user_id:
            return
        db.table("chat_logs").insert({
            "user_id":    user_id,
            "role":       role,
            "content":    content,
            "created_at": datetime.utcnow().isoformat(),
        }).execute()
    except Exception as e:
        print(f"[chat_store] save error: {e}")


def load_messages(user_id: str, limit: int = 100) -> list:
    try:
        db = _db()
        if not db or not user_id:
            return []
        result = (
            db.table("chat_logs")
            .select("role, content")
            .eq("user_id", user_id)
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        )
        return [{"role": r["role"], "content": r["content"]} for r in result.data]
    except Exception as e:
        print(f"[chat_store] load error: {e}")
        return []


def clear_chat(user_id: str) -> None:
    try:
        db = _db()
        if db and user_id:
            db.table("chat_logs").delete().eq("user_id", user_id).execute()
    except Exception as e:
        print(f"[chat_store] clear error: {e}")
