# =============================================================
# memory_store.py — AMHANi ENTERPRISE
# Long-term persistent memory via Supabase
# FILE 1 OF 7 — NEW FILE (create fresh, nothing to replace)
# =============================================================

import os
import json
from datetime import datetime

from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

# ── Supabase client ───────────────────────────────────────────
_supabase = None

def get_supabase():
    """Lazy-load Supabase client so missing env vars don't crash on import."""
    global _supabase
    if _supabase is None:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if url and key:
            _supabase = create_client(url, key)
    return _supabase


# ── Save a memory fact ────────────────────────────────────────
def save_memory(user_id: str, memory_type: str, content: str) -> None:
    """Persist a single memory fact for a user."""
    try:
        db = get_supabase()
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


# ── Load all memory facts for a user ─────────────────────────
def load_memory(user_id: str) -> str:
    """Return all stored memory facts for a user as a formatted string."""
    try:
        db = get_supabase()
        if not db or not user_id:
            return ""

        result = (
            db.table("agent_memory")
            .select("memory_type, content, updated_at")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .limit(20)
            .execute()
        )

        if not result.data:
            return ""

        lines = ["── What I already know about this client ──"]
        for row in result.data:
            lines.append(f"[{row['memory_type']}] {row['content']}")
        return "\n".join(lines)

    except Exception as e:
        print(f"[memory_store] load error: {e}")
        return ""


# ── Extract and save facts silently after each chat ───────────
def extract_and_save_facts(user_id: str, conversation: str, llm) -> None:
    """
    Use the LLM to quietly extract memorable financial facts
    from a conversation and save them to Supabase.
    Runs silently — errors are swallowed so chat is never disrupted.
    """
    if not user_id or not conversation.strip():
        return
    try:
        prompt = (
            "Extract important financial facts about the USER (not generic advice) "
            "from the conversation below.\n"
            "Return ONLY a valid JSON array. Example:\n"
            '[{"type":"portfolio","fact":"user holds AAPL and TSLA stocks"},'
            '{"type":"goal","fact":"user wants to retire in 10 years"},'
            '{"type":"preference","fact":"user prefers low-risk investments"}]\n'
            "Return [] if nothing worth remembering.\n"
            "No explanation. JSON only.\n\n"
            f"Conversation:\n{conversation}"
        )
        response = llm.invoke(prompt)
        raw = response.content.strip()

        # Strip markdown code fences if model adds them
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


# ── Clear all memory for a user ───────────────────────────────
def clear_memory(user_id: str) -> None:
    """Delete all stored memory for a user. Used by admin."""
    try:
        db = get_supabase()
        if not db or not user_id:
            return
        db.table("agent_memory").delete().eq("user_id", user_id).execute()
    except Exception as e:
        print(f"[memory_store] clear error: {e}")
