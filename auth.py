# auth.py — AMHANi | Phase 4: Supabase Authentication
# All secrets loaded from config.py (works locally AND on Streamlit Cloud)

import streamlit as st
from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY


# ── Supabase client ───────────────────────────────────────────────────────────
def get_supabase() -> Client:
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise RuntimeError(
            "Supabase credentials missing.\n"
            "Locally: add SUPABASE_URL and SUPABASE_ANON_KEY to .env\n"
            "Streamlit Cloud: add them in App Settings → Secrets."
        )
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


# ── Session state helpers ─────────────────────────────────────────────────────
def init_auth_state():
    defaults = {
        "user":          None,
        "access_token":  None,
        "is_subscriber": False,
        "auth_view":     "login",  # login | signup | reset
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def is_logged_in() -> bool:
    return st.session_state.get("user") is not None


def get_user_email() -> str:
    user = st.session_state.get("user")
    return user.email if user else ""


def logout():
    try:
        supabase = get_supabase()
        supabase.auth.sign_out()
    except Exception:
        pass
    st.session_state.user          = None
    st.session_state.access_token  = None
    st.session_state.is_subscriber = False
    st.session_state.messages      = []


# ── Subscriber check ──────────────────────────────────────────────────────────
def check_subscription(user_id: str) -> bool:
    """
    Query the subscribers table in Supabase.
    Returns True if the user has an active subscription.
    """
    try:
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            return False
        supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        result = (
            supabase.table("subscribers")
            .select("status")
            .eq("user_id", user_id)
            .eq("status", "active")
            .execute()
        )
        return len(result.data) > 0
    except Exception:
        return False


# ── Auth UI styling ───────────────────────────────────────────────────────────
AUTH_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@300;400;600;700&family=Montserrat:wght@300;400;500;600&display=swap');

.auth-wrap {
    max-width: 420px;
    margin: 2rem auto;
}
.auth-wordmark {
    font-family: 'Cormorant Garamond', serif;
    font-size: 3rem;
    font-weight: 700;
    letter-spacing: 0.18em;
    background: linear-gradient(135deg, #E8C97A 0%, #C9A84C 50%, #8B6914 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    text-align: center;
    display: block;
    margin-bottom: 0.2rem;
}
.auth-sub {
    text-align: center;
    font-size: 0.58rem;
    letter-spacing: 0.4em;
    text-transform: uppercase;
    color: #8B6914;
    margin-bottom: 0.4rem;
    display: block;
}
.auth-enterprise {
    text-align: center;
    font-size: 0.62rem;
    letter-spacing: 0.3em;
    text-transform: uppercase;
    color: rgba(250,250,247,0.3);
    margin-bottom: 2.5rem;
    display: block;
}
.auth-form-title {
    font-family: 'Cormorant Garamond', serif;
    font-size: 1.4rem;
    font-weight: 600;
    color: #C9A84C;
    text-align: center;
    margin-bottom: 1.5rem;
}
.auth-hint {
    font-size: 0.72rem;
    color: rgba(250,250,247,0.4);
    text-align: center;
    line-height: 1.7;
    margin-bottom: 1rem;
}
</style>
"""


# ── Auth UI ───────────────────────────────────────────────────────────────────
def render_auth_ui():
    """
    Renders the full login / signup / reset UI.
    Returns True if user successfully authenticated.
    """
    init_auth_state()
    st.markdown(AUTH_CSS, unsafe_allow_html=True)

    try:
        supabase = get_supabase()
    except RuntimeError as e:
        st.error(str(e))
        st.stop()

    # Brand header
    st.markdown("""
    <div class="auth-wrap">
        <span class="auth-wordmark">AMHANi</span>
        <span class="auth-sub">CONSULTAMHANi</span>
        <span class="auth-enterprise">AMHANi Enterprise · Financial Intelligence</span>
    </div>
    """, unsafe_allow_html=True)

    # Tab selector
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

        email    = st.text_input("Email",    key="login_email",    placeholder="you@example.com")
        password = st.text_input("Password", key="login_password", placeholder="••••••••", type="password")

        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("LOG IN TO AMHANi", use_container_width=True, key="do_login"):
            if not email or not password:
                st.error("Please enter your email and password.")
            else:
                with st.spinner("Authenticating..."):
                    try:
                        response = supabase.auth.sign_in_with_password({
                            "email":    email,
                            "password": password,
                        })
                        st.session_state.user          = response.user
                        st.session_state.access_token  = response.session.access_token
                        st.session_state.is_subscriber = check_subscription(response.user.id)
                        st.rerun()
                    except Exception as e:
                        err = str(e).lower()
                        if "invalid" in err or "credentials" in err:
                            st.error("Incorrect email or password. Please try again.")
                        elif "email" in err and "confirm" in err:
                            st.error("Please verify your email address first. Check your inbox.")
                        else:
                            st.error(f"Login failed: {e}")

        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("Forgot password?", key="go_reset"):
            st.session_state.auth_view = "reset"
            st.rerun()

    # ── SIGNUP ────────────────────────────────────────────────────────────────
    elif st.session_state.auth_view == "signup":
        st.markdown('<div class="auth-form-title">Create Your Account</div>', unsafe_allow_html=True)
        st.markdown("""
        <div class="auth-hint">
            Start with 5 free consultations.<br>
            Upgrade anytime for unlimited access.
        </div>
        """, unsafe_allow_html=True)

        email    = st.text_input("Email",            key="signup_email",    placeholder="you@example.com")
        password = st.text_input("Password",         key="signup_password", placeholder="Minimum 8 characters", type="password")
        confirm  = st.text_input("Confirm Password", key="signup_confirm",  placeholder="Repeat your password",  type="password")

        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("CREATE ACCOUNT", use_container_width=True, key="do_signup"):
            if not email or not password or not confirm:
                st.error("Please fill in all fields.")
            elif password != confirm:
                st.error("Passwords do not match.")
            elif len(password) < 8:
                st.error("Password must be at least 8 characters.")
            else:
                with st.spinner("Creating your account..."):
                    try:
                        response = supabase.auth.sign_up({
                            "email":    email,
                            "password": password,
                        })
                        if response.user:
                            st.success("Account created! Check your email to verify, then log in.")
                            st.session_state.auth_view = "login"
                            st.rerun()
                        else:
                            st.error("Signup failed. Please try again.")
                    except Exception as e:
                        err = str(e).lower()
                        if "already" in err or "registered" in err:
                            st.error("An account with this email already exists. Please log in.")
                        else:
                            st.error(f"Signup error: {e}")

    # ── PASSWORD RESET ────────────────────────────────────────────────────────
    elif st.session_state.auth_view == "reset":
        st.markdown('<div class="auth-form-title">Reset Password</div>', unsafe_allow_html=True)

        email = st.text_input("Email", key="reset_email", placeholder="you@example.com")

        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("SEND RESET LINK", use_container_width=True, key="do_reset"):
            if not email:
                st.error("Please enter your email address.")
            else:
                try:
                    supabase.auth.reset_password_email(email)
                    st.success("Reset link sent. Check your email.")
                    st.session_state.auth_view = "login"
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("← Back to Login", key="back_login"):
            st.session_state.auth_view = "login"
            st.rerun()

    return is_logged_in()
