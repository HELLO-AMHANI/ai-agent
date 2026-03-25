# =============================================================
# memory_store.py — AMHANi ENTERPRISE
# Long-term fact memory per user via Supabase agent_memory table.
# Different from chat_store.py:
#   chat_store  = full message history (every message saved)
#   memory_store = extracted facts only (preferences, portfolio,
#                  goals — distilled by LLM silently)
# =============================================================

import os
import json
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


def save_memory(user_id: str, memory_type: str, content: str) -> None:
    """Persist a single fact about a user."""
    try:
        db = _db()
        if not db or not user_id:
            return
        db.table("agent_memory").upsert({
            "user_id":     user_id,
            "memory_type": memory_type,
            "content":     content,
            "updated_at":  datetime.utcnow().isoformat(),
        }).execute()
    except Exception as e:
        print(f"[memory_store] save error: {e}")


def load_memory(user_id: str) -> str:
    """
    Return all stored facts for a user as a formatted string.
    Returns empty string if no facts stored yet.
    """
    try:
        db = _db()
        if not db or not user_id:
            return ""
        result = (
            db.table("agent_memory")
            .select("memory_type, content")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .limit(20)
            .execute()
        )
        if not result.data:
            return ""
        lines = ["── What I know about this client ──"]
        for row in result.data:
            lines.append(f"[{row['memory_type']}] {row['content']}")
        return "\n".join(lines)
    except Exception as e:
        print(f"[memory_store] load error: {e}")
        return ""


def extract_and_save_facts(user_id: str, conversation: str, llm) -> None:
    """
    Silently extract memorable financial facts from a conversation
    and save them to Supabase for future sessions.
    Runs as a deferred background task — errors are swallowed.
    """
    if not user_id or not conversation.strip():
        return
    try:
        prompt = (
            "Extract important financial facts about the USER from this conversation.\n"
            "Return ONLY a valid JSON array. Example:\n"
            '[{"type":"portfolio","fact":"holds AAPL and TSLA"},'
            '{"type":"goal","fact":"wants to retire in 10 years"},'
            '{"type":"preference","fact":"prefers low-risk investments"}]\n'
            "Return [] if nothing worth remembering.\n"
            "JSON only — no explanation, no markdown.\n\n"
            f"Conversation:\n{conversation[:1500]}"
        )
        response = llm.invoke(prompt)
        raw = (response.content or "").strip()

        # Strip markdown fences if model adds them
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        facts = json.loads(raw.strip())
        for f in facts:
            if isinstance(f, dict) and "type" in f and "fact" in f:
                save_memory(user_id, str(f["type"]), str(f["fact"]))

    except Exception as e:
        print(f"[memory_store] extract error: {e}")


def clear_memory(user_id: str) -> None:
    """Delete all stored facts for a user. Used by admin."""
    try:
        db = _db()
        if db and user_id:
            db.table("agent_memory").delete().eq("user_id", user_id).execute()
    except Exception as e:
        print(f"[memory_store] clear error: {e}")
