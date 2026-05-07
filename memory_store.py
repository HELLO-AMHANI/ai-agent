# =============================================================
# memory_store.py — AMHANi ENTERPRISE
#
# ROOT CAUSE OF "SyntaxError" ON IMPORT:
#   The old version had this at the TOP of the file:
#       from supabase import create_client     ← LINE 6
#       from dotenv import load_dotenv
#       load_dotenv()
#
#   When Streamlit Cloud cold-starts, it imports all .py files
#   before the environment and network are ready. The top-level
#   `from supabase import create_client` fails and Streamlit
#   reports it as "SyntaxError" in its UI (it's actually ImportError).
#
# FIX:
#   Zero top-level third-party imports.
#   `from supabase import create_client` moved INSIDE _get_db().
#   By the time _get_db() is first called the environment is ready.
# =============================================================

import os
import json
from datetime import datetime

_sb_mem = None


def _get_db():
    global _sb_mem
    if _sb_mem is not None:
        return _sb_mem
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    if not url or not key:
        return None
    if not url.startswith("https://") or ".supabase.co" not in url:
        return None
    try:
        from supabase import create_client
        _sb_mem = create_client(url, key)
        return _sb_mem
    except Exception as e:
        print(f"[memory_store] client init error: {e}")
        return None


def save_memory(user_id: str, memory_type: str, content: str) -> None:
    if not user_id or not memory_type or not content:
        return
    try:
        db = _get_db()
        if not db:
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
    if not user_id:
        return ""
    try:
        db = _get_db()
        if not db:
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
        lines = ["── Client context ──"]
        for row in result.data:
            lines.append(f"[{row['memory_type']}] {row['content']}")
        return "\n".join(lines)
    except Exception as e:
        print(f"[memory_store] load error: {e}")
        return ""


def extract_and_save_facts(user_id: str, conversation: str, llm) -> None:
    if not user_id or not conversation or not conversation.strip():
        return
    try:
        prompt = (
            "Extract important financial facts about the USER from this conversation.\n"
            "Return ONLY a valid JSON array. Example:\n"
            '[{"type":"portfolio","fact":"holds AAPL and TSLA"}]\n'
            "Return [] if nothing worth remembering.\n"
            "JSON only — no markdown, no backticks.\n\n"
            f"Conversation:\n{conversation[:1500]}"
        )
        response = llm.invoke(prompt)
        raw = (response.content or "").strip()
        if "```" in raw:
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else parts[0]
            if raw.strip().startswith("json"):
                raw = raw.strip()[4:]
        facts = json.loads(raw.strip())
        for fact in facts:
            if (isinstance(fact, dict) and
                    fact.get("type") and fact.get("fact")):
                save_memory(user_id, str(fact["type"]), str(fact["fact"]))
    except Exception as e:
        print(f"[memory_store] extract error: {e}")


def clear_memory(user_id: str) -> None:
    if not user_id:
        return
    try:
        db = _get_db()
        if db:
            db.table("agent_memory").delete().eq("user_id", user_id).execute()
    except Exception as e:
        print(f"[memory_store] clear error: {e}")
