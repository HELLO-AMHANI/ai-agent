\# =============================================================
# memory_store.py — AMHANi ENTERPRISE
# NVIDIA FIX: Lazy Supabase init + network retry.
# =============================================================

import os
import json
import time
from datetime import datetime

_sb_mem = None

def _get_db():
    global _sb_mem
    if _sb_mem is not None:
        return _sb_mem
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    if not url or not key or ".supabase.co" not in url:
        return None
    try:
        from supabase import create_client
        _sb_mem = create_client(url, key)
        return _sb_mem
    except Exception as e:
        print(f"[memory_store] client error: {e}")
        return None


def _retry(fn, attempts=2):
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
                time.sleep(1.2)
    raise last if last else Exception("unknown")


def save_memory(user_id: str, memory_type: str, content: str) -> None:
    try:
        db = _get_db()
        if not db or not user_id:
            return
        _retry(lambda: db.table("agent_memory").upsert({
            "user_id":     user_id,
            "memory_type": memory_type,
            "content":     content,
            "updated_at":  datetime.utcnow().isoformat(),
        }).execute())
    except Exception as e:
        print(f"[memory_store] save error: {e}")


def load_memory(user_id: str) -> str:
    try:
        db = _get_db()
        if not db or not user_id:
            return ""
        result = _retry(lambda: (
            db.table("agent_memory")
            .select("memory_type, content")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .limit(20)
            .execute()
        ))
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
    if not user_id or not conversation.strip():
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
        db = _get_db()
        if db and user_id:
            db.table("agent_memory").delete().eq("user_id", user_id).execute()
    except Exception as e:
        print(f"[memory_store] clear error: {e}")
