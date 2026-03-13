# config.py
import os
from dotenv import load_dotenv
load_dotenv()

def get_secret(key: str, default: str = "") -> str:
    # Try Streamlit secrets first
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    # Fall back to environment variable
    return os.getenv(key, default)


OPENAI_API_KEY        = get_secret("OPENAI_API_KEY")
OPENAI_MODEL          = get_secret("OPENAI_MODEL", "gpt-5-mini")
AGENT_NAME            = get_secret("AGENT_NAME", "AMHANi")
SUPABASE_URL          = get_secret("SUPABASE_URL")
SUPABASE_ANON_KEY     = get_secret("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_KEY  = get_secret("SUPABASE_SERVICE_KEY")
PAYSTACK_SECRET_KEY   = get_secret("PAYSTACK_SECRET_KEY")
PAYSTACK_PUBLIC_KEY   = get_secret("PAYSTACK_PUBLIC_KEY")
PAYSTACK_PLAN_CODE    = get_secret("PAYSTACK_PLAN_CODE")
PAYSTACK_CALLBACK_URL = get_secret("PAYSTACK_CALLBACK_URL", "https://consultamhani.streamlit.app")
ADMIN_PASSWORD        = get_secret("ADMIN_PASSWORD", "amhani-admin")
COOKIE_SECRET         = get_secret("COOKIE_SECRET", "amhani-secret")
APP_URL               = get_secret("APP_URL", "https://consultamhani.streamlit.app")
ALPHAVANTAGE_API_KEY  = get_secret("LG1ZR4IFQRRZ9YLM")
EXCHANGERATE_API_KEY  = get_secret("8ce3eafc103ad2db2f54cbd1")
SERPAPI_API_KEY       = get_secret("aa4a651dc89c13fa4228f6e45bf33b0999586dc6da56811d2da9854f2f4687c7")
