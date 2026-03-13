# auth.py — CONSULTAMHANi | Supabase Authentication

import streamlit as st
from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY


# ── Supabase client ───────────────────────────────────────────────────────────
def get_supabase() -> Client:
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise RuntimeError(
            "Supabase credentials missing. "
            "Add SUPABASE_URL and SUPABASE_ANON_KEY to your secrets."
        )
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


# ── Session helpers ───────────────────────────────────────────────────────────
def init_auth_state():
    for k, v in {
        "user":          None,
        "access_token":  None,
        "is_subscriber": False,
        "auth_view":     "login",
    }.items():
        if k not in st.session_state:
            st.session_state[k] = v


def is_logged_in() -> bool:
    return st.session_state.get("user") is not None


def get_user_email() -> str:
    user = st.session_state.get("user")
    return user.email if user else ""


def logout():
    try:
        get_supabase().auth.sign_out()
    except Exception:
        pass
    for k in ["user", "access_token", "is_subscriber", "messages", "executor"]:
        st.session_state[k] = None if k != "messages" else []
    st.session_state.is_subscriber = False


def check_subscription(user_id: str) -> bool:
    try:
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            return False
        sb     = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        result = (
            sb.table("subscribers")
            .select("status")
            .eq("user_id", user_id)
            .eq("status", "active")
            .execute()
        )
        return len(result.data) > 0
    except Exception:
        return False


# ── Shared CSS ────────────────────────────────────────────────────────────────
AUTH_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600;0,700;1,300&family=Cinzel:wght@400;600;700&family=Montserrat:wght@200;300;400;500;600&display=swap');

.auth-header {
    text-align: center;
    padding: 2rem 1rem 1.5rem;
    border-bottom: 1px solid rgba(201,168,76,0.2);
    margin-bottom: 2rem;
}
.auth-logo {
    font-family: 'Cinzel', serif;
    font-size: 2.2rem;
    font-weight: 700;
    letter-spacing: 0.2em;
    background: linear-gradient(135deg, #E8C97A 0%, #C9A84C 55%, #8B6914 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    display: block;
    margin-bottom: 0.25rem;
}
.auth-tagline {
    font-family: 'Cormorant Garamond', serif;
    font-size: 0.95rem;
    font-style: italic;
    color: rgba(250,250,247,0.45);
    margin-top: 0.5rem;
    letter-spacing: 0.04em;
}
.auth-enterprise {
    font-size: 0.55rem;
    letter-spacing: 0.38em;
    text-transform: uppercase;
    color: rgba(201,168,76,0.35);
    margin-top: 0.4rem;
    display: block;
}
.auth-form-title {
    font-family: 'Cormorant Garamond', serif;
    font-size: 1.5rem;
    font-weight: 600;
    color: #C9A84C;
    text-align: center;
    margin-bottom: 0.5rem;
    letter-spacing: 0.04em;
}
.auth-hint {
    font-size: 0.75rem;
    color: rgba(250,250,247,0.38);
    text-align: center;
    line-height: 1.7;
    margin-bottom: 1.2rem;
    font-weight: 300;
}
</style>
"""


# ── Auth UI ───────────────────────────────────────────────────────────────────
def render_auth_ui():
    init_auth_state()
    st.markdown(AUTH_CSS, unsafe_allow_html=True)

    try:
        supabase = get_supabase()
    except RuntimeError as e:
        st.error(str(e))
        st.stop()

    # Brand header
    st.markdown("""
    <div class="auth-header">
        <span class="auth-logo">CONSULTAMHANi</span>
        <p class="auth-tagline">AI-Powered Financial Intelligence</p>
        <span class="auth-enterprise">AMHANi Enterprise · Financial Consulting & Advisory</span>
    </div>
    """, unsafe_allow_html=True)

    # Tab buttons
    col1, col2 = st.columns(2)
    with col1:
        if st.button("LOG IN", use_container_width=True, key="tab_login"):
            st.session_state.auth_view = "login"
            st.rerun()
    with col2:
        if st.button("SIGN UP", use_container_width=True, key="tab_signup"):
            st.session_state.auth_view = "signup"
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # ── LOGIN ─────────────────────────────────────────────────────────────────
    if st.session_state.auth_view == "login":
        st.markdown('<div class="auth-form-title">Welcome Back</div>', unsafe_allow_html=True)
        st.markdown('<div class="auth-hint">Log in to access your financial assistant</div>', unsafe_allow_html=True)

        email    = st.text_input("Email address", key="login_email", placeholder="you@example.com")
        password = st.text_input("Password",      key="login_password", placeholder="Your password", type="password")

        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("LOG IN TO CONSULTAMHANi", use_container_width=True, key="do_login"):
            if not email or not password:
                st.error("Please enter your email and password.")
            else:
                with st.spinner("Authenticating..."):
                    try:
                        res = supabase.auth.sign_in_with_password({
                            "email":    email.strip(),
                            "password": password,
                        })
                        st.session_state.user          = res.user
                        st.session_state.access_token  = res.session.access_token
                        st.session_state.is_subscriber = check_subscription(res.user.id)
                        st.rerun()
                    except Exception as e:
                        msg = str(e).lower()
                        if "invalid" in msg or "credentials" in msg or "email" in msg and "password" in msg:
                            st.error("Incorrect email or password. Please try again.")
                        elif "confirm" in msg or "verify" in msg:
                            st.error("Please verify your email first. Check your inbox.")
                        elif "rate" in msg:
                            st.error("Too many attempts. Please wait a moment and try again.")
                        else:
                            st.error(f"Login error: {e}")

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Forgot your password?", key="go_reset"):
            st.session_state.auth_view = "reset"
            st.rerun()

    # ── SIGNUP ────────────────────────────────────────────────────────────────
    elif st.session_state.auth_view == "signup":
        st.markdown('<div class="auth-form-title">Create Account</div>', unsafe_allow_html=True)
        st.markdown("""
        <div class="auth-hint">
            Start with 5 free consultations — no card required.<br>
            Upgrade to unlimited access for ₦29,999/month.
        </div>
        """, unsafe_allow_html=True)

        email    = st.text_input("Email address",    key="signup_email",    placeholder="you@example.com")
        password = st.text_input("Password",         key="signup_password", placeholder="Minimum 8 characters", type="password")
        confirm  = st.text_input("Confirm password", key="signup_confirm",  placeholder="Repeat your password",  type="password")

        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("CREATE MY ACCOUNT", use_container_width=True, key="do_signup"):
            if not email or not password or not confirm:
                st.error("Please fill in all fields.")
            elif password != confirm:
                st.error("Passwords do not match.")
            elif len(password) < 8:
                st.error("Password must be at least 8 characters.")
            else:
                with st.spinner("Creating your account..."):
                    try:
                        res = supabase.auth.sign_up({
                            "email":    email.strip(),
                            "password": password,
                        })
                        if res.user:
                            st.success("Account created! Check your email to verify, then log in.")
                            st.session_state.auth_view = "login"
                            st.rerun()
                        else:
                            st.error("Signup failed. Please try again.")
                    except Exception as e:
                        msg = str(e).lower()
                        if "already" in msg or "registered" in msg or "exists" in msg:
                            st.error("An account with this email already exists. Please log in.")
                        else:
                            st.error(f"Signup error: {e}")

    # ── PASSWORD RESET ────────────────────────────────────────────────────────
    elif st.session_state.auth_view == "reset":
        st.markdown('<div class="auth-form-title">Reset Password</div>', unsafe_allow_html=True)
        st.markdown('<div class="auth-hint">We\'ll send a reset link to your email</div>', unsafe_allow_html=True)

        email = st.text_input("Email address", key="reset_email", placeholder="you@example.com")

        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("SEND RESET LINK", use_container_width=True, key="do_reset"):
            if not email:
                st.error("Please enter your email address.")
            else:
                try:
                    supabase.auth.reset_password_email(email.strip())
                    st.success("Reset link sent. Check your email inbox.")
                    st.session_state.auth_view = "login"
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("← Back to login", key="back_login"):
            st.session_state.auth_view = "login"
            st.rerun()

    return is_logged_in()
