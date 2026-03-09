# auth.py — AMHANi | Phase 4: Supabase Authentication
import os
import streamlit as st
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# ── Supabase client ───────────────────────────────────────────────────────────
def get_supabase() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        raise RuntimeError(
            "Supabase credentials missing. Add SUPABASE_URL and SUPABASE_ANON_KEY to .env"
        )
    return create_client(url, key)


# ── Session state helpers ─────────────────────────────────────────────────────
def init_auth_state():
    defaults = {
        "user":         None,   # Supabase user object
        "access_token": None,
        "is_subscriber": False,
        "auth_view":    "login", # login | signup | reset
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


# ── Subscriber check (Step 5) ─────────────────────────────────────────────────
def check_subscription(user_id: str) -> bool:
    """
    Query the subscribers table in Supabase.
    Returns True if user has an active subscription.
    """
    try:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY")   # service key bypasses RLS
        if not url or not key:
            return False
        supabase = create_client(url, key)
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


# ── Auth UI ───────────────────────────────────────────────────────────────────
AUTH_CSS = """
<style>
.auth-card {
    max-width: 420px;
    margin: 3rem auto;
    background: #1A1A14;
    border: 1px solid rgba(201,168,76,0.3);
    border-radius: 12px;
    padding: 2.5rem 2rem;
    text-align: center;
}
.auth-wordmark {
    font-family: 'Cormorant Garamond', serif;
    font-size: 2.8rem;
    font-weight: 700;
    letter-spacing: 0.18em;
    background: linear-gradient(135deg, #E8C97A 0%, #C9A84C 50%, #8B6914 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 0.3rem;
}
.auth-sub {
    font-size: 0.6rem;
    letter-spacing: 0.35em;
    text-transform: uppercase;
    color: #8B6914;
    margin-bottom: 2rem;
}
.auth-tab-row {
    display: flex;
    gap: 0;
    margin-bottom: 1.8rem;
    border: 1px solid rgba(201,168,76,0.2);
    border-radius: 6px;
    overflow: hidden;
}
.auth-tab {
    flex: 1;
    padding: 0.5rem;
    font-size: 0.7rem;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    font-weight: 600;
    cursor: pointer;
    background: transparent;
    color: rgba(250,250,247,0.4);
}
.auth-tab.active {
    background: rgba(201,168,76,0.15);
    color: #C9A84C;
}
.auth-divider {
    font-size: 0.65rem;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: rgba(250,250,247,0.2);
    margin: 1rem 0;
}
</style>
"""


def render_auth_ui():
    """
    Renders the full login / signup / reset UI.
    Returns True if user successfully authenticated.
    """
    init_auth_state()
    st.markdown(AUTH_CSS, unsafe_allow_html=True)
    supabase = get_supabase()

    st.markdown("""
    <div class="auth-card">
        <div class="auth-wordmark">AMHANi</div>
        <div class="auth-sub">Financial Intelligence</div>
    </div>
    """, unsafe_allow_html=True)

    # ── Tab selector ──────────────────────────────────────────────────────────
    col1, col2 = st.columns(2)
    with col1:
        if st.button("LOG IN", use_container_width=True, key="tab_login"):
            st.session_state.auth_view = "login"
    with col2:
        if st.button("SIGN UP", use_container_width=True, key="tab_signup"):
            st.session_state.auth_view = "signup"

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Login form ────────────────────────────────────────────────────────────
    if st.session_state.auth_view == "login":
        st.markdown("""
        <div style='text-align:center; font-family:"Cormorant Garamond",serif; font-size:1.3rem; color:#C9A84C; margin-bottom:1rem;'>
            Welcome Back
        </div>""", unsafe_allow_html=True)

        email    = st.text_input("Email",    key="login_email",    placeholder="you@example.com")
        password = st.text_input("Password", key="login_password", placeholder="••••••••", type="password")

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
                        st.success("Welcome back.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Login failed: {e}")

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Forgot password?", key="go_reset"):
            st.session_state.auth_view = "reset"
            st.rerun()

    # ── Signup form ───────────────────────────────────────────────────────────
    elif st.session_state.auth_view == "signup":
        st.markdown("""
        <div style='text-align:center; font-family:"Cormorant Garamond",serif; font-size:1.3rem; color:#C9A84C; margin-bottom:1rem;'>
            Create Your Account
        </div>""", unsafe_allow_html=True)

        email    = st.text_input("Email",            key="signup_email",    placeholder="you@example.com")
        password = st.text_input("Password",         key="signup_password", placeholder="min 8 characters", type="password")
        confirm  = st.text_input("Confirm Password", key="signup_confirm",  placeholder="repeat password",   type="password")

        st.markdown("""
        <div style='font-size:0.72rem; color:rgba(250,250,247,0.4); text-align:center; margin:0.5rem 0 1rem; line-height:1.6;'>
            Start with 5 free consultations.<br>
            Upgrade anytime for unlimited access.
        </div>""", unsafe_allow_html=True)

        if st.button("CREATE ACCOUNT", use_container_width=True, key="do_signup"):
            if not email or not password:
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
                        st.error(f"Signup error: {e}")

    # ── Password reset ────────────────────────────────────────────────────────
    elif st.session_state.auth_view == "reset":
        st.markdown("""
        <div style='text-align:center; font-family:"Cormorant Garamond",serif; font-size:1.3rem; color:#C9A84C; margin-bottom:1rem;'>
            Reset Password
        </div>""", unsafe_allow_html=True)

        email = st.text_input("Email", key="reset_email", placeholder="you@example.com")

        if st.button("SEND RESET LINK", use_container_width=True, key="do_reset"):
            if not email:
                st.error("Enter your email address.")
            else:
                try:
                    supabase.auth.reset_password_email(email)
                    st.success("Reset link sent. Check your email.")
                    st.session_state.auth_view = "login"
                except Exception as e:
                    st.error(f"Error: {e}")

        if st.button("← Back to Login", key="back_login"):
            st.session_state.auth_view = "login"
            st.rerun()

    return is_logged_in()
