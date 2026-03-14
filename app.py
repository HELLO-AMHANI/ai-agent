# app.py — CONSULTAMHANi | Main Application
# Secrets via config.py — works locally AND on Streamlit Cloud

import uuid
import streamlit as st

from config import AGENT_NAME, COOKIE_SECRET
from limiter import increment_usage, is_limited, remaining, FREE_LIMIT
from auth import (
    init_auth_state, is_logged_in, get_user_email,
    logout, render_auth_ui, check_subscription,
)
from payments import create_subscription_link, get_subscription_status

# ── Page config — MUST be first Streamlit call ────────────────────────────────
st.set_page_config(
    page_title="CONSULTAMHANi",
    page_icon="✦",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ══════════════════════════════════════════════════════════════════════════════
# GLOBAL STYLES
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600;0,700;1,300&family=Cinzel:wght@400;600;700&family=Montserrat:wght@200;300;400;500;600&display=swap');

:root {
    --gold:        #C9A84C;
    --gold-light:  #E8C97A;
    --gold-dim:    #8B6914;
    --gold-faint:  rgba(201,168,76,0.07);
    --white:       #FAFAF7;
    --off-white:   #F0EDE4;
    --black:       #080807;
    --surface:     #0F0F0C;
    --surface-2:   #161610;
    --surface-3:   #1D1D16;
    --border:      rgba(201,168,76,0.22);
    --border-soft: rgba(201,168,76,0.1);
    --muted:       rgba(250,250,247,0.45);
    --dim:         rgba(250,250,247,0.22);
    --red:         #C0392B;
    --green:       #27AE60;
}

html, body, [class*="css"] {
    font-family: 'Montserrat', sans-serif !important;
    background: var(--black) !important;
    color: var(--white) !important;
}
.stApp {
    background: linear-gradient(160deg,#080807 0%,#0F0F0C 55%,#0A0A08 100%) !important;
}
#MainMenu, footer, header { visibility: hidden !important; }
.block-container { padding: 1.5rem 1.5rem 3rem !important; max-width: 760px !important; }

/* Inputs */
.stTextInput > div > div > input {
    background: var(--surface-2) !important;
    border: 1px solid var(--border) !important;
    border-radius: 6px !important;
    color: var(--white) !important;
    font-family: 'Montserrat', sans-serif !important;
    font-size: 0.875rem !important;
    padding: 0.7rem 1rem !important;
    font-weight: 300 !important;
    transition: border-color 0.2s !important;
}
.stTextInput > div > div > input:focus {
    border-color: var(--gold) !important;
    box-shadow: 0 0 0 2px rgba(201,168,76,0.15) !important;
    outline: none !important;
}
.stTextInput > div > div > input::placeholder { color: var(--dim) !important; }
label[data-testid="stWidgetLabel"] {
    font-size: 0.62rem !important;
    letter-spacing: 0.22em !important;
    text-transform: uppercase !important;
    color: var(--gold-dim) !important;
    font-weight: 600 !important;
    font-family: 'Montserrat', sans-serif !important;
}

/* Buttons */
.stButton > button {
    background: linear-gradient(135deg,var(--gold-light) 0%,var(--gold) 100%) !important;
    color: var(--black) !important;
    border: none !important;
    border-radius: 5px !important;
    font-family: 'Montserrat', sans-serif !important;
    font-weight: 700 !important;
    font-size: 0.7rem !important;
    letter-spacing: 0.18em !important;
    text-transform: uppercase !important;
    padding: 0.65rem 1.5rem !important;
    transition: opacity 0.2s, transform 0.15s !important;
    width: 100% !important;
}
.stButton > button:hover { opacity: 0.88 !important; transform: translateY(-1px) !important; }
.stButton > button:active { transform: translateY(0) !important; }

.stSpinner > div { border-top-color: var(--gold) !important; }
.stAlert { background: var(--surface-2) !important; border-radius: 6px !important; font-size: 0.82rem !important; font-family: 'Montserrat', sans-serif !important; font-weight: 300 !important; }
::-webkit-scrollbar { width: 3px; }
::-webkit-scrollbar-track { background: var(--black); }
::-webkit-scrollbar-thumb { background: var(--gold-dim); border-radius: 2px; }

/* Header */
.c-header {
    text-align: center; padding: 2.5rem 1rem 2rem;
    border-bottom: 1px solid var(--border-soft); margin-bottom: 1.8rem;
    position: relative;
}
.c-header::before {
    content: ''; position: absolute; top: 0; left: 50%; transform: translateX(-50%);
    width: 1px; height: 24px; background: linear-gradient(to bottom, transparent, var(--gold-dim));
}
.c-logo {
    font-family: 'Cinzel', serif; font-size: clamp(1.6rem, 5vw, 2.6rem); font-weight: 700;
    letter-spacing: 0.15em;
    background: linear-gradient(135deg,var(--gold-light) 0%,var(--gold) 50%,var(--gold-dim) 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
    display: block; line-height: 1; margin-bottom: 0.5rem;
}
.c-tagline {
    font-family: 'Cormorant Garamond', serif; font-size: 1rem;
    font-style: italic; font-weight: 300; color: var(--muted); margin-bottom: 0.4rem;
}
.c-enterprise { font-size: 0.52rem; letter-spacing: 0.38em; text-transform: uppercase; color: rgba(201,168,76,0.28); }

/* Account bar */
.acct-bar {
    display: flex; align-items: center; justify-content: space-between;
    background: var(--surface-2); border: 1px solid var(--border-soft);
    border-radius: 6px; padding: 0.55rem 1rem; margin-bottom: 1.2rem; font-size: 0.72rem;
}
.acct-email { color: var(--muted); }
.acct-badge { font-size: 0.58rem; letter-spacing: 0.16em; text-transform: uppercase; font-weight: 700; padding: 0.18rem 0.65rem; border-radius: 20px; }
.badge-pro  { background: rgba(201,168,76,0.12); color: var(--gold); border: 1px solid rgba(201,168,76,0.28); }
.badge-free { background: rgba(250,250,247,0.04); color: var(--dim); border: 1px solid rgba(250,250,247,0.08); }

/* Usage bar */
.usage-bar {
    display: flex; align-items: center; justify-content: space-between;
    background: var(--surface-2); border: 1px solid var(--border-soft);
    border-radius: 6px; padding: 0.6rem 1rem; margin-bottom: 1.2rem;
    font-size: 0.68rem; letter-spacing: 0.1em; text-transform: uppercase; color: var(--gold);
}
.usage-dots { display: flex; gap: 5px; align-items: center; }
.udot { width: 9px; height: 9px; border-radius: 50%; border: 1px solid var(--gold-dim); background: transparent; }
.udot.filled { background: var(--gold); border-color: var(--gold); }
.udot.warn   { background: var(--red);  border-color: var(--red); }

/* Plan badge */
.plan-badge {
    display: flex; align-items: center; justify-content: space-between;
    background: rgba(39,174,96,0.05); border: 1px solid rgba(39,174,96,0.22);
    border-radius: 6px; padding: 0.6rem 1rem; margin-bottom: 1.2rem;
    font-size: 0.68rem; letter-spacing: 0.1em; text-transform: uppercase;
}
.plan-label { color: var(--muted); }
.plan-status { color: #2ECC71; font-weight: 700; }

/* Warning */
.warn-bar {
    background: rgba(192,57,43,0.1); border: 1px solid rgba(192,57,43,0.35);
    border-radius: 6px; padding: 0.6rem 1rem; margin-bottom: 1rem;
    font-size: 0.72rem; color: #E74C3C; text-align: center; letter-spacing: 0.06em;
}

/* Chat */
.chat-wrap { display: flex; flex-direction: column; gap: 1.2rem; margin-bottom: 1.5rem; }
.chat-msg { display: flex; flex-direction: column; max-width: 90%; }
.chat-msg.user  { align-self: flex-end;  align-items: flex-end; }
.chat-msg.agent { align-self: flex-start; align-items: flex-start; }
.chat-label { font-size: 0.55rem; letter-spacing: 0.22em; text-transform: uppercase; margin-bottom: 0.3rem; font-weight: 700; }
.chat-msg.user  .chat-label { color: var(--gold-dim); }
.chat-msg.agent .chat-label { color: var(--gold); }
.chat-bubble { padding: 0.8rem 1.1rem; border-radius: 10px; font-size: 0.875rem; line-height: 1.7; font-weight: 300; }
.chat-msg.user .chat-bubble {
    background: var(--surface-2); border: 1px solid var(--border-soft);
    color: var(--off-white); border-bottom-right-radius: 3px;
}
.chat-msg.agent .chat-bubble {
    background: linear-gradient(135deg, rgba(201,168,76,0.09), rgba(201,168,76,0.03));
    border: 1px solid rgba(201,168,76,0.28); color: var(--white); border-bottom-left-radius: 3px;
}
.gold-line { border: none; border-top: 1px solid var(--border-soft); margin: 1.5rem 0; }

/* Paywall */
.paywall {
    background: var(--surface-2); border: 1px solid var(--gold);
    border-radius: 12px; padding: 2.5rem 2rem 2rem; text-align: center;
    margin-top: 0.5rem; position: relative; overflow: hidden;
}
.paywall::before {
    content: ''; position: absolute; top: -60px; left: 50%; transform: translateX(-50%);
    width: 300px; height: 300px;
    background: radial-gradient(ellipse, rgba(201,168,76,0.06), transparent 70%);
    pointer-events: none;
}
.paywall-icon  { font-size: 1.4rem; margin-bottom: 0.8rem; color: var(--gold); opacity: 0.6; }
.paywall-title { font-family: 'Cormorant Garamond', serif; font-size: 1.9rem; font-weight: 600; color: var(--gold-light); margin-bottom: 0.6rem; }
.paywall-topics { font-size: 0.75rem; color: var(--gold-dim); font-style: italic; margin-bottom: 1.2rem; }
.paywall-body  { font-size: 0.82rem; color: var(--muted); line-height: 1.85; font-weight: 300; margin-bottom: 1.8rem; max-width: 380px; margin-left: auto; margin-right: auto; }
.paywall-stats { display: flex; justify-content: center; gap: 2.5rem; margin-bottom: 2rem; padding: 1.2rem 0; border-top: 1px solid var(--border-soft); border-bottom: 1px solid var(--border-soft); }
.pstat-num   { font-family: 'Cormorant Garamond', serif; font-size: 2rem; color: var(--gold); font-weight: 700; display: block; line-height: 1; }
.pstat-label { font-size: 0.6rem; letter-spacing: 0.16em; text-transform: uppercase; color: var(--dim); margin-top: 0.3rem; display: block; }
.paywall-price  { font-family: 'Cormorant Garamond', serif; font-size: 3rem; font-weight: 700; color: var(--gold); line-height: 1; margin-bottom: 0.3rem; }
.paywall-period { font-size: 0.65rem; color: var(--gold-dim); letter-spacing: 0.18em; text-transform: uppercase; margin-bottom: 1.8rem; }
.paywall-perks  { text-align: left; background: rgba(201,168,76,0.04); border: 1px solid var(--border-soft); border-radius: 8px; padding: 1rem 1.2rem; margin-bottom: 1.8rem; }
.perk           { font-size: 0.78rem; color: rgba(250,250,247,0.68); line-height: 2.1; font-weight: 300; }
.perk::before   { content: "✦ "; color: var(--gold); font-size: 0.65rem; }
.paywall-note   { font-size: 0.6rem; color: var(--dim); letter-spacing: 0.12em; margin-top: 0.8rem; text-transform: uppercase; }

/* Welcome */
.welcome-wrap  { text-align: center; padding: 3.5rem 1rem 2rem; }
.welcome-title { font-family: 'Cormorant Garamond', serif; font-size: 1.25rem; font-style: italic; color: rgba(201,168,76,0.45); margin-bottom: 1.2rem; }
.welcome-chip  { display: inline-block; background: var(--surface-2); border: 1px solid var(--border-soft); border-radius: 20px; padding: 0.3rem 0.9rem; margin: 0.2rem; font-size: 0.72rem; color: var(--muted); }

/* Footer */
.c-footer { text-align: center; padding: 2rem 0 0.5rem; border-top: 1px solid rgba(201,168,76,0.08); margin-top: 2.5rem; }
.c-footer span { font-size: 0.58rem; letter-spacing: 0.28em; text-transform: uppercase; color: rgba(201,168,76,0.28); }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════════════════════════════════════════
init_auth_state()

for k, v in {"messages": [], "executor": None, "ip": None, "session_q": 0}.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── Visitor ID ────────────────────────────────────────────────────────────────
if st.session_state.ip is None:
    try:
        from streamlit_cookies_manager import EncryptedCookieManager
        cookies = EncryptedCookieManager(prefix="cmhani_", password=COOKIE_SECRET)
        if not cookies.ready():
            st.stop()
        if "vid" not in cookies:
            cookies["vid"] = str(uuid.uuid4())
            cookies.save()
        st.session_state.ip = cookies["vid"]
    except Exception:
        if "vid" not in st.session_state:
            st.session_state["vid"] = str(uuid.uuid4())
        st.session_state.ip = st.session_state["vid"]

VISITOR_ID = st.session_state.ip


# ── Load agent ────────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def load_agent():
    from agent import build_agent
    return build_agent(agent_name=AGENT_NAME, verbose=False)


# ══════════════════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<div class="c-header">
    <span class="c-logo">CONSULTAMHANi</span>
    <p class="c-tagline">AI-Powered Financial Intelligence</p>
    <span class="c-enterprise">AMHANi Enterprise · Financial Consulting & Advisory</span>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# AUTH GATE
# ══════════════════════════════════════════════════════════════════════════════
if not is_logged_in():
    render_auth_ui()
    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# SUBSCRIBER CHECK
# ══════════════════════════════════════════════════════════════════════════════
user       = st.session_state.user
user_email = get_user_email()
subscribed = st.session_state.is_subscriber

if not subscribed:
    if get_subscription_status(user_email) == "active":
        st.session_state.is_subscriber = True
        subscribed = True


# ══════════════════════════════════════════════════════════════════════════════
# ACCOUNT BAR
# ══════════════════════════════════════════════════════════════════════════════
badge_class = "badge-pro"  if subscribed else "badge-free"
badge_label = "PRO ✦"      if subscribed else "FREE"
short_email = user_email[:26] + "..." if len(user_email) > 26 else user_email

col_bar, col_logout = st.columns([5, 1])
with col_bar:
    st.markdown(f"""
    <div class="acct-bar">
        <span class="acct-email">{short_email}</span>
        <span class="acct-badge {badge_class}">{badge_label}</span>
    </div>
    """, unsafe_allow_html=True)
with col_logout:
    if st.button("EXIT", key="logout_btn"):
        logout()
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# INIT AGENT
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.executor is None:
    with st.spinner("Starting CONSULTAMHANi..."):
        try:
            st.session_state.executor = load_agent()
        except Exception as e:
            st.error(f"Agent failed to start: {e}")
            st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# USAGE / PLAN STATUS
# ══════════════════════════════════════════════════════════════════════════════
if not subscribed:
    v_remaining = remaining(VISITOR_ID)
    v_used      = FREE_LIMIT - v_remaining

    dots = ""
    for i in range(FREE_LIMIT):
        if i < v_used:
            css = "udot warn" if v_remaining == 0 and i == FREE_LIMIT - 1 else "udot filled"
        else:
            css = "udot"
        dots += f'<div class="{css}"></div>'

    warn_style = "color:#E74C3C;" if v_remaining <= 1 else ""
    st.markdown(f"""
    <div class="usage-bar">
        <span style="{warn_style}">Free consultations left: <strong>{v_remaining}</strong></span>
        <div class="usage-dots">{dots}</div>
    </div>
    """, unsafe_allow_html=True)

    if v_remaining == 1:
        st.markdown('<div class="warn-bar">⚠ &nbsp; Last free consultation — subscribe to continue after this.</div>', unsafe_allow_html=True)
else:
    st.markdown("""
    <div class="plan-badge">
        <span class="plan-label">CONSULTAMHANi · Monthly Plan</span>
        <span class="plan-status">● Active</span>
    </div>
    """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# CHAT HISTORY
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.messages:
    html = '<div class="chat-wrap">'
    for msg in st.session_state.messages:
        role  = msg["role"]
        label = "You" if role == "user" else "CONSULTAMHANi"
        html += f"""
        <div class="chat-msg {role}">
            <div class="chat-label">{label}</div>
            <div class="chat-bubble">{msg["content"]}</div>
        </div>"""
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)
    st.markdown('<hr class="gold-line">', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAYWALL
# ══════════════════════════════════════════════════════════════════════════════
if not subscribed and is_limited(VISITOR_ID):
    topics     = [m["content"][:38] + "…" for m in st.session_state.messages if m["role"] == "user"]
    topics_str = " · ".join(topics[:3]) if topics else "stocks, markets & financial data"

    st.markdown(f"""
    <div class="paywall">
        <div class="paywall-icon">✦</div>
        <div class="paywall-title">Unlock Full Access</div>
        <div class="paywall-topics">You explored: {topics_str}</div>
        <div class="paywall-body">
            You've used your {FREE_LIMIT} complimentary consultations.<br>
            Subscribe for unlimited AI-powered financial intelligence — 24/7.
        </div>
        <div class="paywall-stats">
            <div><span class="pstat-num">{FREE_LIMIT}</span><span class="pstat-label">Used</span></div>
            <div><span class="pstat-num">∞</span><span class="pstat-label">With Pro</span></div>
            <div><span class="pstat-num">24/7</span><span class="pstat-label">Always On</span></div>
        </div>
        <div class="paywall-price">₦29,999</div>
        <div class="paywall-period">per month · cancel anytime</div>
        <div class="paywall-perks">
            <div class="perk">Unlimited financial consultations</div>
            <div class="perk">Real-time stock price lookups</div>
            <div class="perk">Market research & news analysis</div>
            <div class="perk">P/E ratio & financial calculators</div>
            <div class="perk">Investment insights & advisory</div>
            <div class="perk">Priority response speed</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        if st.button("SUBSCRIBE TO CONSULTAMHANi ✦", use_container_width=True, key="sub_btn"):
            with st.spinner("Connecting to payment..."):
                try:
                    pay_url = create_subscription_link(user_email, user.id)
                    st.markdown(f'<meta http-equiv="refresh" content="0; url={pay_url}">', unsafe_allow_html=True)
                    st.info(f"Not redirected? [Click here to pay]({pay_url})")
                except Exception as e:
                    st.error(f"Payment error: {e}")

    st.markdown('<p class="paywall-note">Secured by Paystack · ₦29,999/month · Cancel anytime</p>', unsafe_allow_html=True)
    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# INPUT
# ══════════════════════════════════════════════════════════════════════════════
col_input, col_btn = st.columns([5, 1])
with col_input:
    user_input = st.text_input(
        label="question",
        label_visibility="collapsed",
        placeholder="Ask about stocks, markets, financial analysis…",
        key="chat_input",
    )
with col_btn:
    send = st.button("ASK ✦", use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# RUN AGENT
# ══════════════════════════════════════════════════════════════════════════════
if send and user_input.strip():
    question = user_input.strip()
    st.session_state.messages.append({"role": "user", "content": question})

    with st.spinner("Analysing…"):
        try:
            response = st.session_state.executor.invoke(question)
        except Exception as e:
            response = f"An error occurred: {e}"

    st.session_state.messages.append({"role": "agent", "content": response})

    if not subscribed:
        increment_usage(VISITOR_ID)

    st.session_state.session_q += 1
    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# WELCOME STATE
# ══════════════════════════════════════════════════════════════════════════════
if not st.session_state.messages:
    greeting = "Welcome back to CONSULTAMHANi" if subscribed else "What would you like to explore today?"
    st.markdown(f"""
    <div class="welcome-wrap">
        <div class="welcome-title">{greeting}</div>
        <div>
            <span class="welcome-chip">"Get stock price for TSLA"</span>
            <span class="welcome-chip">"P/E ratio: price $200, EPS $10"</span>
            <span class="welcome-chip">"Latest Apple earnings news"</span>
            <span class="welcome-chip">"Compare AAPL vs MSFT"</span>
            <span class="welcome-chip">"What is market capitalisation?"</span>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# FOOTER
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<div class="c-footer">
    <span>CONSULTAMHANi &nbsp;·&nbsp; AMHANi Enterprise &nbsp;·&nbsp; #CONSULTAMHANi</span>
</div>
""", unsafe_allow_html=True)
