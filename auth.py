# =============================================================
# auth.py — AMHANi ENTERPRISE
# DIAGNOSIS FIX: Session lost on refresh because tokens were
# only in st.session_state (wiped on reload).
# FIX: Persist tokens in encrypted browser cookies via
# streamlit-cookies-manager so session survives refresh.
# =============================================================

import os
import streamlit as st
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

# ── Supabase clients ──────────────────────────────────────────
_URL      = os.getenv("SUPABASE_URL", "")
_ANON     = os.getenv("SUPABASE_ANON_KEY", "")
_SVC      = os.getenv("SUPABASE_SERVICE_KEY", "")
_COOKIE_SECRET = os.getenv("COOKIE_SECRET", "amhani-default-secret-change-me")

supabase     = create_client(_URL, _ANON) if _URL and _ANON else None
supabase_svc = create_client(_URL, _SVC)  if _URL and _SVC  else None


# ── Cookie manager — persists session across browser refreshes ─
def _get_cookies():
    """Return cookie manager. Import is lazy to avoid top-level Streamlit calls."""
    try:
        from streamlit_cookies_manager import EncryptedCookieManager
        cookies = EncryptedCookieManager(
            prefix="amhani_",
            password=_COOKIE_SECRET,
        )
        return cookies
    except Exception:
        return None


# ── Store session in state AND cookies ────────────────────────
def _store_session(session) -> None:
    """Save all session tokens to both st.session_state and browser cookies."""
    st.session_state["access_token"]  = session.access_token
    st.session_state["refresh_token"] = session.refresh_token
    st.session_state["user_id"]       = session.user.id
    st.session_state["user_email"]    = session.user.email

    # Also persist in cookies so refresh doesn't log out
    try:
        cookies = _get_cookies()
        if cookies and cookies.ready():
            cookies["access_token"]  = session.access_token
            cookies["refresh_token"] = session.refresh_token
            cookies["user_id"]       = session.user.id
            cookies["user_email"]    = session.user.email
            cookies.save()
    except Exception:
        pass  # Cookie save failure should never block login


# ── Try restoring session from cookies on page refresh ────────
def try_restore_from_cookies() -> bool:
    """
    Called once at app startup.
    If browser cookies have a valid refresh_token, restore the session
    so the user does not get logged out on page refresh.
    Returns True if session was restored.
    """
    # Already in session state — no need to restore
    if st.session_state.get("access_token") and st.session_state.get("user_id"):
        return True

    try:
        cookies = _get_cookies()
        if not cookies:
            return False

        # Wait for cookies to load
        if not cookies.ready():
            st.stop()  # Streamlit will re-run once cookies are ready

        refresh_token = cookies.get("refresh_token", "")
        if not refresh_token:
            return False

        # Use the refresh token to get a new session from Supabase
        if not supabase:
            return False

        resp = supabase.auth.refresh_session(refresh_token)
        if resp and resp.session:
            _store_session(resp.session)
            return True

    except Exception:
        pass  # Expired or invalid token — user needs to log in again

    return False


# ════════════════════════════════════════════════════════════════
# SESSION HELPERS
# ════════════════════════════════════════════════════════════════

def is_logged_in() -> bool:
    return bool(
        st.session_state.get("access_token")
        and st.session_state.get("user_id")
    )


def get_user_email() -> str:
    return st.session_state.get("user_email", "")


def get_user_id() -> str:
    return st.session_state.get("user_id", "")


def logout() -> None:
    """Clear session from state AND cookies."""
    try:
        if supabase:
            supabase.auth.sign_out()
    except Exception:
        pass

    for key in ("access_token", "refresh_token", "user_id", "user_email"):
        st.session_state.pop(key, None)

    # Clear cookies
    try:
        cookies = _get_cookies()
        if cookies and cookies.ready():
            for key in ("access_token", "refresh_token", "user_id", "user_email"):
                if key in cookies:
                    cookies[key] = ""
            cookies.save()
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════
# SUBSCRIPTION CHECK
# ════════════════════════════════════════════════════════════════

def check_subscription(user_id: str) -> bool:
    if not user_id or not supabase_svc:
        return False
    try:
        result = (
            supabase_svc.table("subscribers")
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
# AUTH UI
# ════════════════════════════════════════════════════════════════

def render_auth_ui() -> None:
    if not supabase:
        st.error("Supabase not configured. Check SUPABASE_URL and SUPABASE_ANON_KEY in .env")
        return

    st.markdown("""
    <style>
    .auth-title {
        font-family: 'Cinzel', serif; font-size: 1.1rem;
        letter-spacing: 0.22em; color: #C9A84C;
        text-align: center; margin-bottom: 0.3rem;
    }
    .auth-sub {
        font-size: 0.65rem; letter-spacing: 0.28em;
        color: rgba(201,168,76,0.4); text-align: center;
        text-transform: uppercase; margin-bottom: 1.5rem;
    }
    div[data-testid="stTextInput"] input {
        background: #161610 !important;
        border: 1px solid rgba(201,168,76,0.2) !important;
        color: #FAFAF7 !important; border-radius: 3px !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<p class="auth-title">CONSULTAMHANi</p>', unsafe_allow_html=True)
    st.markdown('<p class="auth-sub">Access your financial intelligence</p>', unsafe_allow_html=True)

    tab_login, tab_signup, tab_reset = st.tabs(["Sign In", "Create Account", "Reset Password"])

    # ── Sign In ───────────────────────────────────────────────
    with tab_login:
        email_in = st.text_input("Email",    key="login_email",    placeholder="you@example.com")
        pass_in  = st.text_input("Password", key="login_password", type="password", placeholder="••••••••")
        if st.button("Sign In ✦", key="login_btn", use_container_width=True):
            if not email_in or not pass_in:
                st.error("Enter both email and password.")
            else:
                try:
                    resp = supabase.auth.sign_in_with_password(
                        {"email": email_in.strip(), "password": pass_in}
                    )
                    _store_session(resp.session)
                    st.success("Welcome back!")
                    _safe_rerun()
                except Exception as e:
                    err = str(e).lower()
                    if "invalid" in err or "credentials" in err:
                        st.error("Incorrect email or password.")
                    elif "confirm" in err or "verified" in err:
                        st.warning("Please verify your email before signing in.")
                    else:
                        st.error(f"Sign-in failed: {e}")

    # ── Sign Up ───────────────────────────────────────────────
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
                try:
                    supabase.auth.sign_up({"email": email_up.strip(), "password": pass_up})
                    st.success("Account created! Check your email to verify, then sign in.")
                except Exception as e:
                    err = str(e).lower()
                    if "already" in err or "registered" in err:
                        st.error("Account already exists with this email.")
                    else:
                        st.error(f"Sign-up failed: {e}")

    # ── Password Reset ────────────────────────────────────────
    with tab_reset:
        email_rst = st.text_input("Email", key="reset_email", placeholder="you@example.com")
        redirect  = os.getenv("APP_URL", "http://localhost:8501")
        if st.button("Send Reset Link ✦", key="reset_btn", use_container_width=True):
            if not email_rst:
                st.error("Enter your email address.")
            else:
                try:
                    supabase.auth.reset_password_email(
                        email_rst.strip(),
                        options={"redirect_to": redirect},
                    )
                    st.success("Reset email sent. Check your inbox.")
                except Exception as e:
                    st.error(f"Could not send reset email: {e}")


def _safe_rerun():
    try:
        st.rerun()
    except AttributeError:
        st.experimental_rerun()
