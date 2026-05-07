# =============================================================
# auth.py — AMHANi ENTERPRISE
# NVIDIA COMPLETE FIX:
#
# ROOT CAUSE OF "[Errno -2] Name or service not known":
#
#   The previous auth.py created the Supabase client at MODULE
#   IMPORT TIME with two top-level calls:
#
#       supabase     = create_client(_URL, _ANON)
#       supabase_svc = create_client(_URL, _SVC)
#
#   This executes the instant Python imports the file — BEFORE
#   Streamlit has finished loading its secrets into os.environ.
#   On Streamlit Cloud cold-start (which happens after inactivity),
#   the secrets injection is asynchronous. If auth.py imports
#   before secrets are ready, _URL = "" and the client is created
#   with an empty hostname. Every subsequent network call does:
#       socket.getaddrinfo("", 443) → [Errno -2] Name or service not known
#
# WHY IT HAPPENS "WITHOUT TOUCHING ANYTHING":
#   Streamlit Cloud free tier hibernates containers after ~15 min
#   idle. On the next visit, the container cold-starts from scratch.
#   The race condition between secrets loading and module import
#   fires intermittently — sometimes secrets win, sometimes not.
#   This is why the error appears randomly without any code change.
#
# FIX — THREE LAYERS:
#   1. LAZY INIT: Supabase clients created on first USE, not import.
#      By the time the user clicks "Sign In", Streamlit has fully
#      loaded secrets. The client is then created with valid values.
#
#   2. VALIDATION: Before creating the client, validate that the URL
#      looks like a real Supabase URL. Fail fast with a clear message
#      instead of a confusing DNS error.
#
#   3. RETRY: Network calls wrapped with exponential backoff retry.
#      Streamlit Cloud occasionally has transient DNS blips on
#      cold-start. One retry after 1 second resolves most cases.
# =============================================================

import os
import time
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ── Constants ─────────────────────────────────────────────────
_COOKIE_SECRET = os.getenv("COOKIE_SECRET", "amhani-secret-change-me-in-production")

# ── LAZY client cache ─────────────────────────────────────────
# DO NOT call create_client() here at module level.
# These are populated on first use by _get_client() and _get_svc_client().
_supabase_cache     = None
_supabase_svc_cache = None


def _validate_url(url: str) -> bool:
    """Return True only if url looks like a real Supabase project URL."""
    if not url:
        return False
    url = url.strip()
    return (
        url.startswith("https://") and
        ".supabase.co" in url and
        len(url) > 30
    )


def _get_client():
    """
    Return the anon Supabase client, creating it lazily on first call.
    By the time this is called (user interaction), secrets are loaded.
    """
    global _supabase_cache
    if _supabase_cache is not None:
        return _supabase_cache

    url  = os.getenv("SUPABASE_URL", "").strip()
    anon = os.getenv("SUPABASE_ANON_KEY", "").strip()

    if not _validate_url(url):
        return None
    if not anon:
        return None

    try:
        from supabase import create_client
        _supabase_cache = create_client(url, anon)
        return _supabase_cache
    except Exception as e:
        print(f"[auth] failed to create anon client: {e}")
        return None


def _get_svc_client():
    """
    Return the service-role Supabase client, created lazily.
    Used for admin operations (subscription checks, etc.)
    """
    global _supabase_svc_cache
    if _supabase_svc_cache is not None:
        return _supabase_svc_cache

    url = os.getenv("SUPABASE_URL", "").strip()
    svc = os.getenv("SUPABASE_SERVICE_KEY", "").strip()

    if not _validate_url(url):
        return None
    if not svc:
        return None

    try:
        from supabase import create_client
        _supabase_svc_cache = create_client(url, svc)
        return _supabase_svc_cache
    except Exception as e:
        print(f"[auth] failed to create service client: {e}")
        return None


def _retry(fn, attempts: int = 3, delay: float = 1.2):
    """
    Call fn() with exponential backoff retry.
    Handles transient DNS/network errors on Streamlit Cloud cold-start.
    Returns (result, error_string).
    """
    last_err = None
    for i in range(attempts):
        try:
            return fn(), None
        except Exception as e:
            last_err = e
            err_str  = str(e).lower()
            # Only retry on network errors, not auth errors
            is_network = any(x in err_str for x in [
                "errno -2", "name or service", "connection", "timeout",
                "network", "socket", "refused", "reset", "ssl",
            ])
            if not is_network:
                # Auth error (wrong password etc) — don't retry
                return None, last_err
            if i < attempts - 1:
                time.sleep(delay * (i + 1))  # 1.2s, 2.4s
    return None, last_err


# ════════════════════════════════════════════════════════════════
# COOKIE MANAGER
# ════════════════════════════════════════════════════════════════
def _get_cookies():
    try:
        from streamlit_cookies_manager import EncryptedCookieManager
        return EncryptedCookieManager(prefix="amhani_", password=_COOKIE_SECRET)
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════
# SESSION MANAGEMENT
# ════════════════════════════════════════════════════════════════
def _store_session(session) -> None:
    st.session_state["access_token"]  = session.access_token
    st.session_state["refresh_token"] = session.refresh_token
    st.session_state["user_id"]       = session.user.id
    st.session_state["user_email"]    = session.user.email

    try:
        cookies = _get_cookies()
        if cookies and cookies.ready():
            cookies["access_token"]   = session.access_token
            cookies["refresh_token"]  = session.refresh_token
            cookies["user_id"]        = session.user.id
            cookies["user_email"]     = session.user.email
            cookies["token_saved_at"] = str(int(time.time()))
            cookies.save()
    except Exception as e:
        print(f"[auth] cookie save error: {e}")


def try_restore_from_cookies() -> bool:
    """Restore session from browser cookies on page refresh."""
    if st.session_state.get("access_token") and st.session_state.get("user_id"):
        return True

    try:
        cookies = _get_cookies()
        if not cookies:
            return False
        if not cookies.ready():
            st.stop()

        refresh_token = cookies.get("refresh_token", "")
        saved_at      = cookies.get("token_saved_at", "0")

        if not refresh_token:
            return False

        # Check token age — Supabase refresh tokens valid 7 days
        try:
            age = time.time() - float(saved_at)
            if age > 6 * 24 * 3600:
                for k in ("access_token","refresh_token","user_id","user_email","token_saved_at"):
                    cookies[k] = ""
                cookies.save()
                return False
        except Exception:
            pass

        sb = _get_client()
        if not sb:
            return False

        result, err = _retry(lambda: sb.auth.refresh_session(refresh_token), attempts=2)
        if result and result.session:
            _store_session(result.session)
            return True

    except Exception as e:
        print(f"[auth] restore error: {e}")

    return False


# ════════════════════════════════════════════════════════════════
# SESSION HELPERS
# ════════════════════════════════════════════════════════════════
def is_logged_in() -> bool:
    return bool(
        st.session_state.get("access_token") and
        st.session_state.get("user_id")
    )

def get_user_email() -> str:
    return st.session_state.get("user_email", "")

def get_user_id() -> str:
    return st.session_state.get("user_id", "")


def logout() -> None:
    try:
        sb = _get_client()
        if sb:
            sb.auth.sign_out()
    except Exception:
        pass

    for key in ("access_token","refresh_token","user_id","user_email"):
        st.session_state.pop(key, None)

    try:
        cookies = _get_cookies()
        if cookies and cookies.ready():
            for k in ("access_token","refresh_token","user_id","user_email","token_saved_at"):
                if k in cookies:
                    cookies[k] = ""
            cookies.save()
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════
# SUBSCRIPTION CHECK
# ════════════════════════════════════════════════════════════════
def check_subscription(user_id: str) -> bool:
    if not user_id:
        return False
    sb = _get_svc_client()
    if not sb:
        return False
    try:
        result = (
            sb.table("subscribers")
            .select("status")
            .eq("user_id", user_id)
            .eq("status", "active")
            .limit(1)
            .execute()
        )
        return bool(result.data)
    except Exception:
        return False


# ════════════════════════════════════════════════════════════════
# ENVIRONMENT DIAGNOSTIC — shown in UI when config is broken
# ════════════════════════════════════════════════════════════════
def _show_config_error() -> None:
    """
    Show a clear, actionable error when Supabase env vars are missing.
    Much better than showing a raw DNS error to the user.
    """
    url = os.getenv("SUPABASE_URL", "")
    st.error(
        "⚠️  **Configuration Error — Supabase not connected**\n\n"
        "AMHANi cannot reach its database. This usually means the app just "
        "woke up from sleep and secrets haven't loaded yet — **refresh the page** "
        "and try again.\n\n"
        "If the error persists, check your Streamlit Cloud secrets:\n"
        "- `SUPABASE_URL` — must start with `https://` and contain `.supabase.co`\n"
        "- `SUPABASE_ANON_KEY` — your project's anon/public key\n"
        "- `SUPABASE_SERVICE_KEY` — your project's service role key\n\n"
        f"Current URL detected: `{'(empty)' if not url else url[:40] + '...'}`"
    )


# ════════════════════════════════════════════════════════════════
# AUTH UI
# ════════════════════════════════════════════════════════════════
def render_auth_ui() -> None:
    sb = _get_client()

    if not sb:
        _show_config_error()
        # Show a retry button — on Streamlit Cloud, refreshing after
        # cold-start is enough for secrets to load properly
        if st.button("🔄  Refresh & Retry", use_container_width=True):
            _safe_rerun()
        return

    # Styles
    st.markdown("""
    <style>
    .auth-title {
        font-family:'Cinzel',serif; font-size:1.1rem;
        letter-spacing:0.22em; color:#C9A84C;
        text-align:center; margin-bottom:0.3rem;
    }
    .auth-sub {
        font-size:0.65rem; letter-spacing:0.28em;
        color:rgba(201,168,76,0.4); text-align:center;
        text-transform:uppercase; margin-bottom:1.5rem;
    }
    div[data-testid="stTextInput"] input {
        background:#161610 !important;
        border:1px solid rgba(201,168,76,0.2) !important;
        color:#FAFAF7 !important; border-radius:3px !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<p class="auth-title">CONSULTAMHANi</p>', unsafe_allow_html=True)
    st.markdown('<p class="auth-sub">Access your financial intelligence</p>', unsafe_allow_html=True)

    tab_login, tab_signup, tab_reset = st.tabs(["Sign In", "Create Account", "Reset Password"])

    # ── Sign In ──────────────────────────────────────────────
    with tab_login:
        email_in = st.text_input("Email",    key="login_email",    placeholder="you@example.com")
        pass_in  = st.text_input("Password", key="login_password", type="password", placeholder="••••••••")
        if st.button("Sign In ✦", key="login_btn", use_container_width=True):
            if not email_in or not pass_in:
                st.error("Enter both email and password.")
            else:
                with st.spinner("Signing in..."):
                    result, err = _retry(
                        lambda: sb.auth.sign_in_with_password(
                            {"email": email_in.strip(), "password": pass_in}
                        ),
                        attempts=3,
                        delay=1.2,
                    )
                if err:
                    err_str = str(err).lower()
                    if any(x in err_str for x in ["errno -2","name or service","connection","network","socket"]):
                        st.error(
                            "🌐 **Network error reaching Supabase.** "
                            "This happens when the app wakes from sleep. "
                            "Please **refresh the page** and try again."
                        )
                    elif "invalid" in err_str or "credentials" in err_str:
                        st.error("Incorrect email or password.")
                    elif "confirm" in err_str or "verified" in err_str:
                        st.warning("Please verify your email before signing in.")
                    elif "rate" in err_str or "429" in err_str:
                        st.error("Too many attempts. Wait 60 seconds and try again.")
                    else:
                        st.error(f"Sign-in failed: {err}")
                elif result and result.session:
                    _store_session(result.session)
                    st.success("Welcome back!")
                    _safe_rerun()
                else:
                    st.error("Sign-in failed. Please try again.")

    # ── Sign Up ──────────────────────────────────────────────
    with tab_signup:
        email_up = st.text_input("Email",            key="signup_email",    placeholder="you@example.com")
        pass_up  = st.text_input("Password",         key="signup_password", type="password", placeholder="min 6 characters")
        pass_up2 = st.text_input("Confirm Password", key="signup_confirm",  type="password", placeholder="repeat password")
        if st.button("Create Account ✦", key="signup_btn", use_container_width=True):
            if not email_up or not pass_up:
                st.error("Email and password are required.")
            elif pass_up != pass_up2:
                st.error("Passwords do not match.")
            elif len(pass_up) < 6:
                st.error("Password must be at least 6 characters.")
            else:
                with st.spinner("Creating account..."):
                    result, err = _retry(
                        lambda: sb.auth.sign_up(
                            {"email": email_up.strip(), "password": pass_up}
                        ),
                        attempts=3,
                        delay=1.2,
                    )
                if err:
                    err_str = str(err).lower()
                    if any(x in err_str for x in ["errno -2","network","socket","connection"]):
                        st.error("🌐 Network error. Please refresh the page and try again.")
                    elif "already" in err_str or "registered" in err_str:
                        st.error("Account already exists with this email. Sign in instead.")
                    else:
                        st.error(f"Sign-up failed: {err}")
                else:
                    st.success("Account created! Check your email to verify, then sign in.")

    # ── Password Reset ────────────────────────────────────────
    with tab_reset:
        email_rst = st.text_input("Email", key="reset_email", placeholder="you@example.com")
        redirect  = os.getenv("APP_URL", "http://localhost:8501")
        if st.button("Send Reset Link ✦", key="reset_btn", use_container_width=True):
            if not email_rst:
                st.error("Enter your email address.")
            else:
                with st.spinner("Sending reset email..."):
                    result, err = _retry(
                        lambda: sb.auth.reset_password_email(
                            email_rst.strip(),
                            options={"redirect_to": redirect},
                        ),
                        attempts=2,
                        delay=1.0,
                    )
                if err:
                    st.error(f"Could not send reset email. Check your connection and try again.")
                else:
                    st.success("Reset email sent. Check your inbox.")


def _safe_rerun():
    try:
        st.rerun()
    except AttributeError:
        st.experimental_rerun()
