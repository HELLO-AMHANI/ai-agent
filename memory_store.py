# memory_store.py — AMHANi ENTERPRISE
import os, json
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

from supabase import create_client

_supabase = None

def get_supabase():
    global _supabase
    if _supabase is None:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if url and key:
            _supabase = create_client(url, key)
    return _supabase

def save_memory(user_id: str, memory_type: str, content: str) -> None:
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

def load_memory(user_id: str) -> str:
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
        lines = ["── Prior client context ──"]
        for row in result.data:
            lines.append(f"[{row['memory_type']}] {row['content']}")
        return "\n".join(lines)
    except Exception as e:
        print(f"[memory_store] load error: {e}")
        return ""

def extract_and_save_facts(user_id: str, conversation: str, llm) -> None:
    if not user_id or not conversation.strip():
        return
    try:
        prompt = (
            "Extract important financial facts about the USER from this conversation.\n"
            "Return ONLY a valid JSON array. Example:\n"
            '[{"type":"portfolio","fact":"user holds AAPL stocks"},{"type":"goal","fact":"user wants to retire in 10 years"}]\n'
            "Return [] if nothing worth remembering. JSON only, no explanation.\n\n"
            f"Conversation:\n{conversation}"
        )
        response = llm.invoke(prompt)
        raw = response.content.strip()
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
    try:
        db = get_supabase()
        if not db or not user_id:
            return
        db.table("agent_memory").delete().eq("user_id", user_id).execute()
    except Exception as e:
        print(f"[memory_store] clear error: {e}")
