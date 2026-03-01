# app.py — AMHANi | CONSULTAMHANi Interface
import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ── Page config (must be first Streamlit call) ──────────────────────────────
st.set_page_config(
    page_title="CONSULTAMHANi",
    page_icon="✦",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ── Brand constants ──────────────────────────────────────────────────────────
BRAND_NAME       = "AMHANi"
INTERFACE_TITLE  = "CONSULTAMHANi"
FREE_LIMIT       = 5
AGENT_NAME       = os.getenv("AGENT_NAME", "AMHANi")

# ── Gold & White theme ───────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@300;400;600;700&family=Montserrat:wght@300;400;500;600&display=swap');

:root {
    --gold:        #C9A84C;
    --gold-light:  #E8C97A;
    --gold-dim:    #8B6914;
    --white:       #FAFAF7;
    --off-white:   #F0EDE4;
    --black:       #0A0A08;
    --surface:     #111109;
    --surface-2:   #1A1A14;
    --border:      rgba(201, 168, 76, 0.25);
}

html, body, [class*="css"] {
    font-family: 'Montserrat', sans-serif;
    background-color: var(--black) !important;
    color: var(--white) !important;
}

.stApp {
    background: linear-gradient(160deg, #0A0A08 0%, #111109 50%, #0D0D0A 100%);
}

#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 2rem; padding-bottom: 2rem; max-width: 780px; }

.amhani-header {
    text-align: center;
    padding: 3rem 1rem 1.5rem;
    border-bottom: 1px solid var(--border);
    margin-bottom: 2rem;
}

.amhani-wordmark {
    font-family: 'Cormorant Garamond', serif;
    font-size: 3.6rem;
    font-weight: 700;
    letter-spacing: 0.18em;
    background: linear-gradient(135deg, var(--gold-light) 0%, var(--gold) 50%, var(--gold-dim) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin: 0;
    line-height: 1;
}

.amhani-sub {
    font-size: 0.65rem;
    font-weight: 500;
    letter-spacing: 0.42em;
    color: var(--gold-dim);
    text-transform: uppercase;
    margin-top: 0.5rem;
}

.amhani-tagline {
    font-family: 'Cormorant Garamond', serif;
    font-size: 1.05rem;
    font-weight: 300;
    color: rgba(250, 250, 247, 0.55);
    margin-top: 1rem;
    font-style: italic;
}

.usage-bar-wrap {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0.6rem 1rem;
    margin-bottom: 1.5rem;
    font-size: 0.72rem;
    letter-spacing: 0.08em;
    color: var(--gold);
    text-transform: uppercase;
}

.usage-dots { display: flex; gap: 6px; }
.dot { width: 10px; height: 10px; border-radius: 50%; border: 1px solid var(--gold-dim); background: transparent; }
.dot.used { background: var(--gold); border-color: var(--gold); }

.msg-wrap { display: flex; flex-direction: column; gap: 1rem; margin-bottom: 1.5rem; }
.msg { display: flex; flex-direction: column; max-width: 88%; }
.msg.user  { align-self: flex-end;  align-items: flex-end; }
.msg.agent { align-self: flex-start; align-items: flex-start; }

.msg-label { font-size: 0.6rem; letter-spacing: 0.2em; text-transform: uppercase; margin-bottom: 0.3rem; font-weight: 600; }
.msg.user  .msg-label { color: var(--gold-dim); }
.msg.agent .msg-label { color: var(--gold); }

.msg-bubble { padding: 0.85rem 1.1rem; border-radius: 8px; font-size: 0.88rem; line-height: 1.65; font-weight: 300; }
.msg.user  .msg-bubble { background: var(--surface-2); border: 1px solid var(--border); color: var(--off-white); border-bottom-right-radius: 2px; }
.msg.agent .msg-bubble { background: linear-gradient(135deg, rgba(201,168,76,0.08) 0%, rgba(201,168,76,0.03) 100%); border: 1px solid rgba(201,168,76,0.35); color: var(--white); border-bottom-left-radius: 2px; }

.stTextInput > div > div > input {
    background: var(--surface-2) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    color: var(--white) !important;
    font-family: 'Montserrat', sans-serif !important;
    font-size: 0.88rem !important;
    padding: 0.75rem 1rem !important;
    font-weight: 300 !important;
}
.stTextInput > div > div > input:focus { border-color: var(--gold) !important; box-shadow: 0 0 0 1px rgba(201,168,76,0.3) !important; }
.stTextInput > div > div > input::placeholder { color: rgba(250,250,247,0.25) !important; }

.stButton > button {
    background: linear-gradient(135deg, var(--gold-light) 0%, var(--gold) 100%) !important;
    color: var(--black) !important;
    border: none !important;
    border-radius: 6px !important;
    font-family: 'Montserrat', sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.75rem !important;
    letter-spacing: 0.15em !important;
    text-transform: uppercase !important;
    padding: 0.6rem 1.5rem !important;
}
.stButton > button:hover { opacity: 0.88 !important; }

.paywall-card { background: var(--surface-2); border: 1px solid var(--gold); border-radius: 10px; padding: 2rem 2rem 1.5rem; text-align: center; margin-top: 1rem; }
.paywall-title { font-family: 'Cormorant Garamond', serif; font-size: 1.8rem; font-weight: 600; color: var(--gold-light); margin-bottom: 0.5rem; }
.paywall-body { font-size: 0.82rem; color: rgba(250,250,247,0.6); line-height: 1.7; font-weight: 300; margin-bottom: 1.5rem; }
.paywall-price { font-family: 'Cormorant Garamond', serif; font-size: 2.4rem; font-weight: 700; color: var(--gold); margin-bottom: 0.2rem; }
.paywall-period { font-size: 0.7rem; color: var(--gold-dim); letter-spacing: 0.15em; text-transform: uppercase; margin-bottom: 1.5rem; }

.gold-divider { border: none; border-top: 1px solid var(--border); margin: 1.5rem 0; }
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: var(--black); }
::-webkit-scrollbar-thumb { background: var(--gold-dim); border-radius: 2px; }
</style>
""", unsafe_allow_html=True)

# ── Session state init ────────────────────────────────────────────────────────
if "messages"     not in st.session_state: st.session_state.messages     = []
if "usage_count"  not in st.session_state: st.session_state.usage_count  = 0
if "subscribed"   not in st.session_state: st.session_state.subscribed   = False
if "executor"     not in st.session_state: st.session_state.executor     = None

# ── Load agent (cached across reruns) ────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def load_agent():
    from agent import build_agent
    return build_agent(agent_name=AGENT_NAME, verbose=False)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="amhani-header">
    <p class="amhani-wordmark">{BRAND_NAME}</p>
    <p class="amhani-sub">Financial Intelligence</p>
    <p class="amhani-tagline">Your personal AI-powered financial research consultant</p>
</div>
""", unsafe_allow_html=True)

# ── Load agent on first run ───────────────────────────────────────────────────
if st.session_state.executor is None:
    with st.spinner("Initialising CONSULTAMHANi..."):
        try:
            st.session_state.executor = load_agent()
        except RuntimeError as e:
            st.error(f"Startup error: {e}")
            st.stop()

# ── Usage indicator ───────────────────────────────────────────────────────────
if not st.session_state.subscribed:
    used      = st.session_state.usage_count
    remaining = max(0, FREE_LIMIT - used)
    dots_html = "".join(
        f'<div class="dot{"" if i >= used else " used"}"></div>'
        for i in range(FREE_LIMIT)
    )
    st.markdown(f"""
    <div class="usage-bar-wrap">
        <span>Free consultations remaining: <strong>{remaining}</strong></span>
        <div class="usage-dots">{dots_html}</div>
    </div>
    """, unsafe_allow_html=True)

# ── Chat history ──────────────────────────────────────────────────────────────
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

# ── Paywall ───────────────────────────────────────────────────────────────────
if not st.session_state.subscribed and st.session_state.usage_count >= FREE_LIMIT:
    st.markdown(f"""
    <div class="paywall-card">
        <div class="paywall-title">Unlock Full Access</div>
        <div class="paywall-body">
            You've used your {FREE_LIMIT} complimentary consultations.<br>
            Subscribe to {INTERFACE_TITLE} for unlimited real-time financial intelligence —
            stock analysis, market research, P/E ratios, and more.
        </div>
        <div class="paywall-price">₦ 9,999</div>
        <div class="paywall-period">per month &nbsp;·&nbsp; cancel anytime</div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("SUBSCRIBE NOW", use_container_width=True):
            # Replace with your actual Stripe payment link in Phase 4
            st.info("Stripe payment link — add in Phase 4.")
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
    st.session_state.usage_count += 1
    st.rerun()

# ── Welcome state ──────────────────────────────────────────────────────────────
if not st.session_state.messages:
    st.markdown("""
    <div style="text-align:center; padding: 3rem 1rem; color: rgba(250,250,247,0.3);">
        <div style="font-family:'Cormorant Garamond',serif; font-size:1.3rem; margin-bottom:0.75rem; color:rgba(201,168,76,0.5);">
            What would you like to explore?
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
<div style="text-align:center; padding: 2rem 0 0.5rem; border-top: 1px solid rgba(201,168,76,0.12); margin-top:2rem;">
    <span style="font-size:0.62rem; letter-spacing:0.25em; text-transform:uppercase; color:rgba(201,168,76,0.35);">
        AMHANi &nbsp;·&nbsp; #CONSULTAMHANi &nbsp;·&nbsp; Financial Intelligence
    </span>
</div>
""", unsafe_allow_html=True)
