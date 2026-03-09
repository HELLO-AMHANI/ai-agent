# app.py — AMHANi | CONSULTAMHANi | Phase 4
import os
import streamlit as st
from dotenv import load_dotenv
from limiter import get_usage, increment_usage, is_limited, remaining, FREE_LIMIT
from auth import init_auth_state, is_logged_in, get_user_email, logout, render_auth_ui, check_subscription
from payments import create_subscription_link, get_subscription_status

load_dotenv()

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CONSULTAMHANi",
    page_icon="✦",
    layout="centered",
    initial_sidebar_state="collapsed",
)

BRAND_NAME      = "AMHANi"
INTERFACE_TITLE = "CONSULTAMHANi"
AGENT_NAME      = os.getenv("AGENT_NAME", "AMHANi")
APP_URL         = os.getenv("APP_URL", "http://localhost:8501")

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@300;400;600;700&family=Montserrat:wght@300;400;500;600&display=swap');

:root {
    --gold:       #C9A84C;
    --gold-light: #E8C97A;
    --gold-dim:   #8B6914;
    --white:      #FAFAF7;
    --off-white:  #F0EDE4;
    --black:      #0A0A08;
    --surface:    #111109;
    --surface-2:  #1A1A14;
    --border:     rgba(201,168,76,0.25);
    --red:        #C0392B;
    --green:      #27AE60;
}

html, body, [class*="css"] { font-family:'Montserrat',sans-serif; background-color:var(--black) !important; color:var(--white) !important; }
.stApp { background:linear-gradient(160deg,#0A0A08 0%,#111109 50%,#0D0D0A 100%); }
#MainMenu, footer, header { visibility:hidden; }
.block-container { padding-top:2rem; padding-bottom:2rem; max-width:780px; }

/* Header */
.amhani-header { text-align:center; padding:2.5rem 1rem 1.5rem; border-bottom:1px solid var(--border); margin-bottom:2rem; }
.amhani-wordmark { font-family:'Cormorant Garamond',serif; font-size:3.6rem; font-weight:700; letter-spacing:0.18em; background:linear-gradient(135deg,var(--gold-light) 0%,var(--gold) 50%,var(--gold-dim) 100%); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; margin:0; line-height:1; }
.amhani-sub { font-size:0.65rem; font-weight:500; letter-spacing:0.42em; color:var(--gold-dim); text-transform:uppercase; margin-top:0.5rem; }
.amhani-tagline { font-family:'Cormorant Garamond',serif; font-size:1.05rem; font-weight:300; color:rgba(250,250,247,0.55); margin-top:1rem; font-style:italic; }

/* Account bar */
.account-bar { display:flex; align-items:center; justify-content:space-between; background:var(--surface-2); border:1px solid var(--border); border-radius:6px; padding:0.55rem 1rem; margin-bottom:1.2rem; font-size:0.72rem; }
.account-email { color:rgba(250,250,247,0.5); letter-spacing:0.04em; }
.account-badge { font-size:0.62rem; letter-spacing:0.15em; text-transform:uppercase; font-weight:600; padding:0.2rem 0.6rem; border-radius:20px; }
.badge-pro { background:rgba(201,168,76,0.15); color:var(--gold); border:1px solid rgba(201,168,76,0.3); }
.badge-free { background:rgba(250,250,247,0.05); color:rgba(250,250,247,0.35); border:1px solid rgba(250,250,247,0.1); }

/* Usage bar */
.usage-bar-wrap { display:flex; align-items:center; justify-content:space-between; background:var(--surface-2); border:1px solid var(--border); border-radius:6px; padding:0.6rem 1rem; margin-bottom:1.5rem; font-size:0.72rem; letter-spacing:0.08em; color:var(--gold); text-transform:uppercase; }
.usage-dots { display:flex; gap:6px; }
.dot { width:10px; height:10px; border-radius:50%; border:1px solid var(--gold-dim); background:transparent; }
.dot.used { background:var(--gold); border-color:var(--gold); }
.dot.warn { background:var(--red); border-color:var(--red); }

/* Chat */
.msg-wrap { display:flex; flex-direction:column; gap:1rem; margin-bottom:1.5rem; }
.msg { display:flex; flex-direction:column; max-width:88%; }
.msg.user  { align-self:flex-end;  align-items:flex-end; }
.msg.agent { align-self:flex-start; align-items:flex-start; }
.msg-label { font-size:0.6rem; letter-spacing:0.2em; text-transform:uppercase; margin-bottom:0.3rem; font-weight:600; }
.msg.user  .msg-label { color:var(--gold-dim); }
.msg.agent .msg-label { color:var(--gold); }
.msg-bubble { padding:0.85rem 1.1rem; border-radius:8px; font-size:0.88rem; line-height:1.65; font-weight:300; }
.msg.user  .msg-bubble { background:var(--surface-2); border:1px solid var(--border); color:var(--off-white); border-bottom-right-radius:2px; }
.msg.agent .msg-bubble { background:linear-gradient(135deg,rgba(201,168,76,0.08) 0%,rgba(201,168,76,0.03) 100%); border:1px solid rgba(201,168,76,0.35); color:var(--white); border-bottom-left-radius:2px; }

/* Input */
.stTextInput>div>div>input { background:var(--surface-2) !important; border:1px solid var(--border) !important; border-radius:8px !important; color:var(--white) !important; font-family:'Montserrat',sans-serif !important; font-size:0.88rem !important; padding:0.75rem 1rem !important; font-weight:300 !important; }
.stTextInput>div>div>input:focus { border-color:var(--gold) !important; box-shadow:0 0 0 1px rgba(201,168,76,0.3) !important; }
.stTextInput>div>div>input::placeholder { color:rgba(250,250,247,0.25) !important; }

/* Buttons */
.stButton>button { background:linear-gradient(135deg,var(--gold-light) 0%,var(--gold) 100%) !important; color:var(--black) !important; border:none !important; border-radius:6px !important; font-family:'Montserrat',sans-serif !important; font-weight:600 !important; font-size:0.75rem !important; letter-spacing:0.15em !important; text-transform:uppercase !important; padding:0.6rem 1.5rem !important; }
.stButton>button:hover { opacity:0.88 !important; }

/* Paywall */
.paywall-card { background:var(--surface-2); border:1px solid var(--gold); border-radius:12px; padding:2.5rem 2rem 2rem; text-align:center; margin-top:1rem; }
.paywall-title { font-family:'Cormorant Garamond',serif; font-size:2rem; font-weight:600; color:var(--gold-light); margin-bottom:0.5rem; }
.paywall-body { font-size:0.82rem; color:rgba(250,250,247,0.6); line-height:1.8; font-weight:300; margin-bottom:1.5rem; }
.paywall-stats { display:flex; justify-content:center; gap:2rem; margin-bottom:1.5rem; }
.paywall-stat-num { font-family:'Cormorant Garamond',serif; font-size:1.8rem; color:var(--gold); font-weight:700; }
.paywall-stat-label { font-size:0.62rem; letter-spacing:0.15em; text-transform:uppercase; color:rgba(250,250,247,0.4); }
.paywall-price { font-family:'Cormorant Garamond',serif; font-size:2.8rem; font-weight:700; color:var(--gold); }
.paywall-period { font-size:0.7rem; color:var(--gold-dim); letter-spacing:0.15em; text-transform:uppercase; margin-bottom:1.5rem; }
.paywall-perks { text-align:left; background:rgba(201,168,76,0.05); border-radius:8px; padding:1rem 1.2rem; margin-bottom:1.5rem; }
.paywall-perk { font-size:0.78rem; color:rgba(250,250,247,0.7); line-height:2; }
.paywall-perk::before { content:"✦ "; color:var(--gold); }

/* Plan status card */
.plan-card { background:var(--surface-2); border:1px solid rgba(39,174,96,0.3); border-radius:8px; padding:1rem 1.2rem; margin-bottom:1.2rem; display:flex; align-items:center; justify-content:space-between; }
.plan-active { font-size:0.72rem; letter-spacing:0.12em; text-transform:uppercase; color:#2ECC71; font-weight:600; }

/* Warning */
.warn-banner { background:rgba(192,57,43,0.12); border:1px solid rgba(192,57,43,0.4); border-radius:6px; padding:0.6rem 1rem; margin-bottom:1rem; font-size:0.75rem; color:#E74C3C; text-align:center; letter-spacing:0.05em; }

.gold-divider { border:none; border-top:1px solid var(--border); margin:1.5rem 0; }
::-webkit-scrollbar { width:4px; }
::-webkit-scrollbar-track { background:var(--black); }
::-webkit-scrollbar-thumb { background:var(--gold-dim); border-radius:2px; }
</style>
""", unsafe_allow_html=True)


# ── Session state init ────────────────────────────────────────────────────────
init_auth_state()

session_defaults = {
    "messages":   [],
    "executor":   None,
    "ip":         None,
    "session_q":  0,
}
for k, v in session_defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── Visitor ID (for free-tier tracking) ───────────────────────────────────────
if st.session_state.ip is None:
    import uuid
    try:
        from streamlit_cookies_manager import EncryptedCookieManager
        cookies = EncryptedCookieManager(
            prefix="amhani_",
            password=os.getenv("COOKIE_SECRET", "amhani-secret"),
        )
        if not cookies.ready():
            st.stop()
        if "visitor_id" not in cookies:
            cookies["visitor_id"] = str(uuid.uuid4())
            cookies.save()
        st.session_state.ip = cookies["visitor_id"]
    except Exception:
        if "visitor_id" not in st.session_state:
            st.session_state["visitor_id"] = str(uuid.uuid4())
        st.session_state.ip = st.session_state["visitor_id"]

VISITOR_ID = st.session_state.ip


# ── Load agent ─────────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def load_agent():
    from agent import build_agent
    return build_agent(agent_name=AGENT_NAME, verbose=False)


# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="amhani-header">
    <p class="amhani-wordmark">{BRAND_NAME}</p>
    <p class="amhani-sub">Financial Intelligence</p>
    <p class="amhani-tagline">Your personal AI-powered financial research consultant</p>
</div>
""", unsafe_allow_html=True)


# ── Step 4: Auth gate — show login/signup if not logged in ────────────────────
if not is_logged_in():
    render_auth_ui()
    st.stop()


# ── Step 5: Subscriber check — logged-in users ───────────────────────────────
user        = st.session_state.user
user_email  = get_user_email()
subscribed  = st.session_state.is_subscriber

# Re-verify subscription status on each session load (catches cancellations)
if subscribed is False:
    live_status = get_subscription_status(user_email)
    if live_status == "active":
        st.session_state.is_subscriber = True
        subscribed = True


# ── Account bar (Step 6) ───────────────────────────────────────────────────────
badge_class = "badge-pro"  if subscribed else "badge-free"
badge_label = "PRO ✦"      if subscribed else "FREE"
short_email = user_email[:28] + "..." if len(user_email) > 28 else user_email

col_bar, col_logout = st.columns([5, 1])
with col_bar:
    st.markdown(f"""
    <div class="account-bar">
        <span class="account-email">{short_email}</span>
        <span class="account-badge {badge_class}">{badge_label}</span>
    </div>
    """, unsafe_allow_html=True)
with col_logout:
    if st.button("EXIT", key="logout_btn"):
        logout()
        st.rerun()


# ── Load agent on first run ────────────────────────────────────────────────────
if st.session_state.executor is None:
    with st.spinner("Initialising CONSULTAMHANi..."):
        try:
            st.session_state.executor = load_agent()
        except RuntimeError as e:
            st.error(f"Startup error: {e}")
            st.stop()


# ── Step 5: Usage tracking (free users only) ──────────────────────────────────
if not subscribed:
    visitor_remaining = remaining(VISITOR_ID)
    visitor_limited   = is_limited(VISITOR_ID)
    visitor_used      = FREE_LIMIT - visitor_remaining

    dots_html = "".join(
        f'<div class="dot {"used" if i < visitor_used else ""}"></div>'
        for i in range(FREE_LIMIT)
    )
    label_color = "color:#E74C3C;" if visitor_remaining <= 1 else ""
    st.markdown(f"""
    <div class="usage-bar-wrap">
        <span style="{label_color}">Free consultations remaining: <strong>{visitor_remaining}</strong></span>
        <div class="usage-dots">{dots_html}</div>
    </div>
    """, unsafe_allow_html=True)

    if visitor_remaining == 1:
        st.markdown("""
        <div class="warn-banner">
            ⚠ &nbsp; Last free consultation. Subscribe for unlimited access.
        </div>
        """, unsafe_allow_html=True)
else:
    # Step 6: Show active plan status for subscribers
    st.markdown(f"""
    <div class="plan-card">
        <span style="font-size:0.78rem; color:rgba(250,250,247,0.6);">
            CONSULTAMHANi — Monthly Plan
        </span>
        <span class="plan-active">● Active</span>
    </div>
    """, unsafe_allow_html=True)


# ── Chat history ───────────────────────────────────────────────────────────────
if st.session_state.messages:
    msgs_html = '<div class="msg-wrap">'
    for msg in st.session_state.messages:
        role  = msg["role"]
        label = "You" if role == "user" else INTERFACE_TITLE
        msgs_html += f"""
        <div class="msg {role}">
            <div class="msg-label">{label}</div>
            <div class="msg-bubble">{msg["content"]}</div>
        </div>"""
    msgs_html += "</div>"
    st.markdown(msgs_html, unsafe_allow_html=True)
    st.markdown('<hr class="gold-divider">', unsafe_allow_html=True)


# ── Paywall (free users who hit limit) ────────────────────────────────────────
if not subscribed and is_limited(VISITOR_ID):
    topics = [m["content"][:40] + "..." for m in st.session_state.messages if m["role"] == "user"]
    topics_str = " · ".join(topics[:3]) if topics else "stocks, markets, financial data"

    st.markdown(f"""
    <div class="paywall-card">
        <div class="paywall-title">You've Found Your Edge</div>
        <div class="paywall-body">
            You explored: <em style="color:var(--gold-dim)">{topics_str}</em><br><br>
            Subscribe to {INTERFACE_TITLE} for unlimited real-time financial intelligence.
        </div>
        <div class="paywall-stats">
            <div class="paywall-stat">
                <div class="paywall-stat-num">{FREE_LIMIT}</div>
                <div class="paywall-stat-label">Used</div>
            </div>
            <div class="paywall-stat">
                <div class="paywall-stat-num">∞</div>
                <div class="paywall-stat-label">With Pro</div>
            </div>
            <div class="paywall-stat">
                <div class="paywall-stat-num">24/7</div>
                <div class="paywall-stat-label">Always On</div>
            </div>
        </div>
        <div class="paywall-price">₦ 29,999</div>
        <div class="paywall-period">per month &nbsp;·&nbsp; cancel anytime</div>
        <div class="paywall-perks">
            <div class="paywall-perk">Unlimited financial consultations</div>
            <div class="paywall-perk">Real-time stock price lookups</div>
            <div class="paywall-perk">Market research & news analysis</div>
            <div class="paywall-perk">P/E ratio & financial calculators</div>
            <div class="paywall-perk">Priority response speed</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("SUBSCRIBE TO CONSULTAMHANi", use_container_width=True, key="subscribe_btn"):
            with st.spinner("Redirecting to payment..."):
                try:
                    pay_url = create_subscription_link(user_email, user.id)
                    st.markdown(
                        f'<meta http-equiv="refresh" content="0; url={pay_url}">',
                        unsafe_allow_html=True,
                    )
                    st.info(f"If not redirected, [click here]({pay_url})")
                except Exception as e:
                    st.error(f"Payment error: {e}")
    st.stop()


# ── Input ──────────────────────────────────────────────────────────────────────
col_input, col_btn = st.columns([5, 1])

with col_input:
    user_input = st.text_input(
        label="input",
        label_visibility="collapsed",
        placeholder="Ask about stocks, markets, financial analysis...",
        key="chat_input",
    )

with col_btn:
    send = st.button("ASK", use_container_width=True)


# ── Run agent ──────────────────────────────────────────────────────────────────
if send and user_input.strip():
    question = user_input.strip()
    st.session_state.messages.append({"role": "user", "content": question})

    with st.spinner("Analysing..."):
        try:
            result   = st.session_state.executor.invoke({"input": question})
            response = result.get("output", "Unable to generate a response. Please try again.")
        except Exception as e:
            response = f"An error occurred: {e}"

    st.session_state.messages.append({"role": "agent", "content": response})

    # Only increment for free users
    if not subscribed:
        increment_usage(VISITOR_ID)

    st.session_state.session_q += 1
    st.rerun()


# ── Welcome state ──────────────────────────────────────────────────────────────
if not st.session_state.messages:
    greeting = "Welcome back" if subscribed else "What would you like to explore?"
    st.markdown(f"""
    <div style="text-align:center; padding:3rem 1rem; color:rgba(250,250,247,0.3);">
        <div style="font-family:'Cormorant Garamond',serif; font-size:1.3rem; margin-bottom:0.75rem; color:rgba(201,168,76,0.5);">
            {greeting}
        </div>
        <div style="font-size:0.78rem; line-height:2.2; letter-spacing:0.04em;">
            "Get me the stock price of TSLA"<br>
            "What is the P/E ratio for a stock at $200 with EPS of 10"<br>
            "Search for latest news on Apple earnings"<br>
            "Compare AAPL and MSFT market caps"
        </div>
    </div>
    """, unsafe_allow_html=True)


# ── Footer ──────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center; padding:2rem 0 0.5rem; border-top:1px solid rgba(201,168,76,0.12); margin-top:2rem;">
    <span style="font-size:0.62rem; letter-spacing:0.25em; text-transform:uppercase; color:rgba(201,168,76,0.35);">
        AMHANi &nbsp;·&nbsp; #CONSULTAMHANi &nbsp;·&nbsp; Financial Intelligence
    </span>
</div>
""", unsafe_allow_html=True)
