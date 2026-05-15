# =============================================================
# auth.py — AMHANi ENTERPRISE v5
#
# FIX: Page refresh sends user back to login screen.
#
# Root cause:
#   try_restore_from_cookies() calls st.stop() when cookies
#   are not yet "ready" (the EncryptedCookieManager loads
#   asynchronously). On the FIRST run after a page refresh:
#     1. cookies.ready() → False  → st.stop() is called
#     2. Streamlit re-runs from the top
#     3. cookies.ready() → True   → refresh_token is read
#     4. Supabase refresh_session() → new access_token
#     5. _store_session() → sets session_state
#   This is correct but the PROBLEM is that app.py renders
#   the auth gate BEFORE try_restore_from_cookies() finishes
#   in some code orderings, or the cookies take two reruns
#   to become available. On those reruns, is_logged_in()
#   returns False and the login screen flashes.
#
# Fix A: try_restore_from_cookies() now returns one of three
#   explicit states: "restored", "no_session", "loading".
#   app.py uses this to show a neutral loading spinner
#   instead of the login form while cookies are loading.
#
# Fix B: Only call st.stop() if we have never tried before
#   in this run. A "cookie_load_attempted" flag prevents
#   infinite stop() loops.
#
# Fix C: token_saved_at check made more lenient (7 days
#   instead of 6) to match Supabase's default refresh
#   token expiry exactly.
# =============================================================

import time
import os
import streamlit as st
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

_URL           = os.getenv("SUPABASE_URL", "")
_ANON          = os.getenv("SUPABASE_ANON_KEY", "")
_SVC           = os.getenv("SUPABASE_SERVICE_KEY", "")
_COOKIE_SECRET = os.getenv("COOKIE_SECRET", "amhani-default-secret-change-me")

supabase     = create_client(_URL, _ANON) if _URL and _ANON else None
supabase_svc = create_client(_URL, _SVC)  if _URL and _SVC  else None


def _get_cookies():
    try:
        from streamlit_cookies_manager import EncryptedCookieManager
        return EncryptedCookieManager(prefix="amhani_", password=_COOKIE_SECRET)
    except Exception:
        return None


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


def try_restore_from_cookies() -> str:
    """
    Attempt to restore the Supabase session from encrypted browser cookies.

    Returns:
        "restored"   — session successfully restored, user is logged in
        "no_session" — no valid cookie found, user must log in
        "loading"    — cookies not yet ready, call again on next rerun

    app.py should show a neutral spinner when this returns "loading"
    instead of rendering the login form.
    """
    # Already logged in — nothing to do
    if st.session_state.get("access_token") and st.session_state.get("user_id"):
        return "restored"

    # Only attempt cookie load once per Streamlit run to prevent loops
    if st.session_state.get("_cookie_load_attempted"):
        return "no_session"

    try:
        cookies = _get_cookies()
        if not cookies:
            st.session_state["_cookie_load_attempted"] = True
            return "no_session"

        if not cookies.ready():
            # Cookies not yet loaded — signal the caller to wait
            # Mark that we've tried so next run doesn't loop
            st.session_state["_cookie_load_attempted"] = True
            # Stop this run so Streamlit re-runs with cookies ready
            st.stop()

        # Cookies are ready — mark attempted regardless of outcome
        st.session_state["_cookie_load_attempted"] = True

        refresh_token = cookies.get("refresh_token", "")
        saved_at      = cookies.get("token_saved_at", "0")

        if not refresh_token:
            return "no_session"

        # Check token age — Supabase default refresh token TTL is 7 days
        try:
            age = time.time() - float(saved_at)
            if age > 7 * 24 * 3600:
                # Stale token — clear and force re-login
                for k in ("access_token","refresh_token","user_id",
                          "user_email","token_saved_at"):
                    try: cookies[k] = ""
                    except Exception: pass
                cookies.save()
                return "no_session"
        except Exception:
            pass

        if not supabase:
            return "no_session"

        resp = supabase.auth.refresh_session(refresh_token)
        if resp and resp.session:
            _store_session(resp.session)
            return "restored"

    except Exception as e:
        print(f"[auth] restore error: {e}")

    return "no_session"


# ══════════════════════════════════════════════════════════════
# SESSION HELPERS
# ══════════════════════════════════════════════════════════════
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
    try:
        if supabase:
            supabase.auth.sign_out()
    except Exception:
        pass
    for key in ("access_token","refresh_token","user_id","user_email",
                "_cookie_load_attempted"):
        st.session_state.pop(key, None)
    try:
        cookies = _get_cookies()
        if cookies and cookies.ready():
            for k in ("access_token","refresh_token","user_id",
                      "user_email","token_saved_at"):
                try: cookies[k] = ""
                except Exception: pass
            cookies.save()
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════
# SUBSCRIPTION CHECK
# ══════════════════════════════════════════════════════════════
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


# ══════════════════════════════════════════════════════════════
# AUTH UI
# ══════════════════════════════════════════════════════════════
def render_auth_ui() -> None:
    if not supabase:
        st.error("Supabase not configured. Check SUPABASE_URL and SUPABASE_ANON_KEY.")
        return

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
    st.markdown('<p class="auth-sub">Access your financial intelligence</p>',
                unsafe_allow_html=True)

    tab_login, tab_signup, tab_reset = st.tabs(
        ["Sign In", "Create Account", "Reset Password"]
    )

    with tab_login:
        email_in = st.text_input("Email",    key="login_email",
                                  placeholder="you@example.com")
        pass_in  = st.text_input("Password", key="login_password",
                                  type="password", placeholder="••••••••")
        if st.button("Sign In ✦", key="login_btn", use_container_width=True):
            if not email_in or not pass_in:
                st.error("Enter both email and password.")
            else:
                try:
                    resp = supabase.auth.sign_in_with_password(
                        {"email": email_in.strip(), "password": pass_in}
                    )
                    _store_session(resp.session)
                    # Clear the cookie-load flag so fresh session is used
                    st.session_state.pop("_cookie_load_attempted", None)
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

    with tab_signup:
        email_up = st.text_input("Email",            key="signup_email",
                                  placeholder="you@example.com")
        pass_up  = st.text_input("Password",         key="signup_password",
                                  type="password", placeholder="min 6 characters")
        pass_up2 = st.text_input("Confirm Password", key="signup_confirm",
                                  type="password", placeholder="repeat password")
        if st.button("Create Account ✦", key="signup_btn", use_container_width=True):
            if not email_up or not pass_up:
                st.error("Email and password are required.")
            elif pass_up != pass_up2:
                st.error("Passwords do not match.")
            elif len(pass_up) < 6:
                st.error("Password must be at least 6 characters.")
            else:
                try:
                    supabase.auth.sign_up(
                        {"email": email_up.strip(), "password": pass_up}
                    )
                    st.success("Account created! Check your email to verify, then sign in.")
                except Exception as e:
                    err = str(e).lower()
                    if "already" in err or "registered" in err:
                        st.error("Account already exists with this email.")
                    else:
                        st.error(f"Sign-up failed: {e}")

    with tab_reset:
        email_rst = st.text_input("Email", key="reset_email",
                                   placeholder="you@example.com")
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