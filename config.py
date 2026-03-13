# config.py — CONSULTAMHANi | Universal Secrets Loader
# Works on localhost (.env) AND Streamlit Cloud (st.secrets)

import os
from dotenv import load_dotenv

load_dotenv()


def get_secret(key: str, default: str = "") -> str:
    """
    Reads secrets in this order:
    1. Streamlit Cloud st.secrets
    2. Local .env via os.getenv
    3. Default value
    """
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.getenv(key, default)


# ── All secrets ───────────────────────────────────────────────────────────────
OPENAI_API_KEY        = get_secret("OPENAI_API_KEY")
OPENAI_MODEL          = get_secret("OPENAI_MODEL", "gpt-5-mini")
AGENT_NAME            = get_secret("AGENT_NAME", "AMHANi")

SUPABASE_URL          = get_secret("SUPABASE_URL")
SUPABASE_ANON_KEY     = get_secret("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_KEY  = get_secret("SUPABASE_SERVICE_KEY")

PAYSTACK_SECRET_KEY   = get_secret("PAYSTACK_SECRET_KEY")
PAYSTACK_PUBLIC_KEY   = get_secret("PAYSTACK_PUBLIC_KEY")
PAYSTACK_PLAN_CODE    = get_secret("PAYSTACK_PLAN_CODE")
PAYSTACK_CALLBACK_URL = get_secret(
    "PAYSTACK_CALLBACK_URL", "https://consultamhani.streamlit.app"
)

ADMIN_PASSWORD        = get_secret("ADMIN_PASSWORD", "Osirenoya1$")
COOKIE_SECRET         = get_secret("COOKIE_SECRET", "amhani-financial-intelligence-platform-2024")
APP_URL               = get_secret("APP_URL", "https://consultamhani.streamlit.app")

SERPAPI_API_KEY       = get_secret("SERPAPI_API_KEY")
ALPHAVANTAGE_API_KEY  = get_secret("ALPHAVANTAGE_API_KEY")
EXCHANGERATE_API_KEY  = get_secret("EXCHANGERATE_API_KEY")
