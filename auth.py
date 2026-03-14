# =============================================================
# auth.py — AMHANi ENTERPRISE · Authentication
# FILE 4 OF 7 — FULL REPLACEMENT
# Delete everything in your existing auth.py and paste this.
# =============================================================

import os
import streamlit as st
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

# ── Supabase clients ──────────────────────────────────────────
_SUPABASE_URL      = os.getenv("SUPABASE_URL", "")
_SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
_SUPABASE_SVC_KEY  = os.getenv("SUPABASE_SERVICE_KEY", "")

supabase      = create_client(_SUPABASE_URL, _SUPABASE_ANON_KEY)  if _SUPABASE_URL and _SUPABASE_ANON_KEY else None
supabase_svc  = create_client(_SUPABASE_URL, _SUPABASE_SVC_KEY)   if _SUPABASE_URL and _SUPABASE_SVC_KEY  else None


# ════════════════════════════════════════════════════════════════
# SESSION HELPERS
# ════════════════════════════════════════════════════════════════

def is_logged_in() -> bool:
    """Return True if a user session is active."""
    return bool(
        st.session_state.get("access_token")
        and st.session_state.get("user_id")
    )


def get_user_email() -> str:
    """Return the current user's email or empty string."""
    return st.session_state.get("user_email", "")


def get_user_id() -> str:
    """Return the current user's UUID or empty string."""
    return st.session_state.get("user_id", "")


def logout() -> None:
    """Clear all session state and sign out from Supabase."""
    try:
        if supabase:
            supabase.auth.sign_out()
    except Exception:
        pass
    for key in ("access_token", "refresh_token", "user_id", "user_email"):
        st.session_state.pop(key, None)


def _store_session(session) -> None:
    """Persist Supabase session tokens and user info in Streamlit state."""
    st.session_state["access_token"]  = session.access_token
    st.session_state["refresh_token"] = session.refresh_token
    st.session_state["user_id"]       = session.user.id
    st.session_state["user_email"]    = session.user.email


# ════════════════════════════════════════════════════════════════
# SUBSCRIPTION CHECK
# ════════════════════════════════════════════════════════════════

def check_subscription(user_id: str) -> bool:
    """
    Return True if the user has an active subscription in the
    'subscribers' table (uses service key for elevated access).
    """
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
    except Exception as e:
        print(f"[auth] subscription check error: {e}")
        return False


# ════════════════════════════════════════════════════════════════
# AUTH UI
# ════════════════════════════════════════════════════════════════

def render_auth_ui() -> None:
    """
    Render a branded login / sign-up / password-reset UI.
    On success, stores session in st.session_state and triggers rerun.
    """
    if not supabase:
        st.error(
            "Supabase is not configured. "
            "Check SUPABASE_URL and SUPABASE_ANON_KEY in your .env file."
        )
        return

    # ── Styles ────────────────────────────────────────────────
    st.markdown("""
    <style>
    .auth-title {
        font-family: 'Cinzel', serif;
        font-size: 1.1rem; letter-spacing: 0.22em;
        color: #C9A84C; text-align: center;
        margin-bottom: 0.3rem;
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
    div[data-testid="stTextInput"] input:focus {
        border-color: rgba(201,168,76,0.6) !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<p class="auth-title">CONSULTAMHANi</p>', unsafe_allow_html=True)
    st.markdown('<p class="auth-sub">Access your financial intelligence</p>', unsafe_allow_html=True)

    tab_login, tab_signup, tab_reset = st.tabs(["Sign In", "Create Account", "Reset Password"])

    # ── Sign In ───────────────────────────────────────────────
    with tab_login:
        email_in    = st.text_input("Email",    key="login_email",    placeholder="you@example.com")
        password_in = st.text_input("Password", key="login_password", type="password", placeholder="••••••••")

        if st.button("Sign In ✦", key="login_btn", use_container_width=True):
            if not email_in or not password_in:
                st.error("Please enter both email and password.")
            else:
                try:
                    resp = supabase.auth.sign_in_with_password(
                        {"email": email_in.strip(), "password": password_in}
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
                    supabase.auth.sign_up(
                        {"email": email_up.strip(), "password": pass_up}
                    )
                    st.success(
                        "Account created! Check your email for a verification "
                        "link, then sign in."
                    )
                except Exception as e:
                    err = str(e).lower()
                    if "already" in err or "registered" in err:
                        st.error("An account with this email already exists.")
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
                    st.success("Password reset email sent. Check your inbox.")
                except Exception as e:
                    st.error(f"Could not send reset email: {e}")


# ════════════════════════════════════════════════════════════════
# SAFE RERUN — compatible with all Streamlit versions
# ════════════════════════════════════════════════════════════════

def _safe_rerun() -> None:
    try:
        st.rerun()
    except AttributeError:
        st.experimental_rerun()
