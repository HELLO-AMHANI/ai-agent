# =============================================================
# app.py — AMHANi ENTERPRISE · Streamlit Interface
# DIAGNOSIS FIX:
#   - Refresh logs out: tokens only in session_state (wiped on
#     refresh). FIX: auth.try_restore_from_cookies() restores
#     session from browser cookies before any auth check.
#   - Wrong chat history: previous broken app was saving messages
#     with null user_id. FIX: strict validation before save/load,
#     plus load ONLY after confirmed user_id.
#   - history_loaded flag wrong placement: was initialised before
#     user_id was known. FIX: moved entirely into post-login block.
#   - st.switch_page on logout crashed on Streamlit Cloud.
#     FIX: replaced with _safe_rerun().
#   - Reasoning expander crashed on 3-tuple steps.
#     FIX: defensive step unpacking.
# =============================================================

import os
import streamlit as st
from dotenv import load_dotenv
load_dotenv()

# ── Page config — MUST be first Streamlit call ────────────────
st.set_page_config(
    page_title="CONSULTAMHANi",
    page_icon="✦",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ── Imports after set_page_config ────────────────────────────
from agent import run_agent, sync_memory, llm
from auth import (
    render_auth_ui,
    is_logged_in,
    check_subscription,
    get_user_email,
    get_user_id,
    logout,
    try_restore_from_cookies,
)
from limiter import (
    is_limited,
    increment_usage,
    remaining,
    get_visitor_id,
    FREE_LIMIT,
)
from memory_store import load_memory, extract_and_save_facts
from payments import create_subscription_link
from chat_store import save_message, load_messages, clear_chat


# ════════════════════════════════════════════════════════════════
# STYLES
# ════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@600&family=Cormorant+Garamond:wght@300;400;600&family=Montserrat:wght@300;400;500;600&display=swap');

html, body, [class*="css"] { font-family: 'Montserrat', sans-serif; }
.stApp { background: #080807; color: #FAFAF7; }

.amhani-header {
    text-align: center; padding: 2.5rem 0 1.2rem;
    border-bottom: 1px solid rgba(201,168,76,0.15); margin-bottom: 1.5rem;
}
.amhani-wordmark {
    font-family: 'Cinzel', serif; font-size: 2rem; font-weight: 600;
    letter-spacing: 0.25em;
    background: linear-gradient(135deg, #E8C97A, #C9A84C, #8B6914);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.amhani-sub {
    font-size: 0.58rem; letter-spacing: 0.42em;
    color: rgba(201,168,76,0.4); text-transform: uppercase; margin-top: 4px;
}
.user-bubble {
    background: rgba(201,168,76,0.08); border: 1px solid rgba(201,168,76,0.2);
    border-radius: 12px 12px 2px 12px; padding: 0.9rem 1.2rem;
    margin: 0.5rem 0 0.5rem 2rem; font-size: 0.88rem; color: #FAFAF7; line-height: 1.7;
}
.agent-bubble {
    background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px 12px 12px 2px; padding: 0.9rem 1.2rem;
    margin: 0.5rem 2rem 0.5rem 0; font-size: 0.88rem; color: #FAFAF7; line-height: 1.8;
    white-space: pre-wrap;
}
.agent-label {
    font-size: 0.55rem; letter-spacing: 0.28em; color: #C9A84C;
    text-transform: uppercase; margin-bottom: 0.3rem; font-weight: 600;
}
.usage-dots { display: flex; gap: 8px; justify-content: center; margin-bottom: 1.2rem; }
.dot-active { width:10px; height:10px; border-radius:50%; background:#C9A84C; display:inline-block; }
.dot-used   { width:10px; height:10px; border-radius:50%; background:#8B6914; opacity:0.35; display:inline-block; }
.dot-warn   { width:10px; height:10px; border-radius:50%; background:#c94c4c; display:inline-block; }
.plan-badge {
    display: inline-block; font-size: 0.58rem; letter-spacing: 0.18em;
    text-transform: uppercase; font-weight: 700; padding: 2px 8px;
    border-radius: 3px; margin-left: 8px; vertical-align: middle;
}
.badge-pro  { background: linear-gradient(135deg,#E8C97A,#C9A84C); color:#080807; }
.badge-free { background: rgba(201,168,76,0.1); color:#C9A84C; border:1px solid rgba(201,168,76,0.3); }
.paywall-card {
    background: rgba(201,168,76,0.05); border: 1px solid rgba(201,168,76,0.3);
    border-radius: 8px; padding: 2.5rem 2rem; text-align: center; margin: 1.5rem 0;
}
.paywall-title { font-family:'Cinzel',serif; font-size:1.5rem; color:#C9A84C; letter-spacing:0.18em; margin-bottom:0.6rem; }
.paywall-body  { font-size:0.82rem; color:rgba(250,250,247,0.55); line-height:1.8; margin-bottom:1.5rem; }
.paywall-price { font-size:0.78rem; color:rgba(250,250,247,0.35); margin-top:0.8rem; }
div[data-testid="stTextInput"] input,
div[data-testid="stTextArea"] textarea {
    background: #161610 !important; border: 1px solid rgba(201,168,76,0.2) !important;
    color: #FAFAF7 !important; border-radius: 3px !important;
}
div[data-testid="stTextInput"] input:focus,
div[data-testid="stTextArea"] textarea:focus {
    border-color: rgba(201,168,76,0.55) !important; box-shadow: none !important;
}
.stButton > button {
    background: linear-gradient(135deg,#E8C97A,#C9A84C) !important;
    color: #080807 !important; font-weight: 600 !important; border: none !important;
    border-radius: 3px !important; letter-spacing: 0.1em !important; font-size: 0.75rem !important;
}
.stButton > button:hover { opacity: 0.88 !important; }
hr { border-color: rgba(201,168,76,0.12) !important; }
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════
def _safe_rerun():
    try:
        st.rerun()
    except AttributeError:
        st.experimental_rerun()


def render_response_content(content: str) -> None:
    """Render plain text or base64 chart — defined at top so always available."""
    if "CHART_BASE64:" in content:
        parts = content.split("CHART_BASE64:", 1)
        if parts[0].strip():
            st.markdown(
                f'<div class="agent-bubble">{parts[0].strip()}</div>',
                unsafe_allow_html=True,
            )
        st.markdown(
            f'<img src="data:image/png;base64,{parts[1].strip()}" '
            f'style="width:100%;border-radius:6px;margin-top:8px;" />',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="agent-bubble">{content}</div>',
            unsafe_allow_html=True,
        )


# ════════════════════════════════════════════════════════════════
# SESSION RESTORE — run before any auth check
# FIX: This is what keeps users logged in after a page refresh.
# Reads the refresh_token from cookies and restores the session.
# ════════════════════════════════════════════════════════════════
try_restore_from_cookies()


# ════════════════════════════════════════════════════════════════
# SAFE DEFAULTS — before auth gate
# ════════════════════════════════════════════════════════════════
if "visitor_id"    not in st.session_state:
    st.session_state.visitor_id    = get_visitor_id()
if "is_subscriber" not in st.session_state:
    st.session_state.is_subscriber = False


# ════════════════════════════════════════════════════════════════
# AUTH GATE
# ════════════════════════════════════════════════════════════════
if not is_logged_in():
    st.markdown(
        '<div class="amhani-header">'
        '<div class="amhani-wordmark">CONSULTAMHANi</div>'
        '<div class="amhani-sub">by AMHANi Enterprise</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    render_auth_ui()
    st.stop()


# ════════════════════════════════════════════════════════════════
# POST-LOGIN — user_id is confirmed valid from here downward
# ════════════════════════════════════════════════════════════════
user_email = get_user_email()
user_id    = get_user_id()          # guaranteed non-empty here
is_sub     = check_subscription(user_id)
st.session_state.is_subscriber = is_sub


# ── Load chat history from Supabase ONCE per session ──────────
# history_loaded is per-session (cleared on refresh/logout).
# After restore_from_cookies re-establishes the session, this
# loads the correct history for the confirmed user_id.
if not st.session_state.get("history_loaded"):
    raw_msgs = load_messages(user_id, limit=100)
    # Validate: only accept messages with valid role and non-empty content
    st.session_state.messages = [
        m for m in raw_msgs
        if m.get("role") in ("user", "assistant")
        and (m.get("content") or "").strip()
    ]
    st.session_state.history_loaded = True


# ════════════════════════════════════════════════════════════════
# SIDEBAR
# ════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown(
        '<p style="font-size:0.62rem;letter-spacing:0.22em;'
        'color:rgba(201,168,76,0.45);text-transform:uppercase;font-weight:600;">'
        'Options</p>',
        unsafe_allow_html=True,
    )
    if st.button("Clear Chat History"):
        clear_chat(user_id)
        st.session_state.messages       = []
        st.session_state.history_loaded = True
        _safe_rerun()


# ════════════════════════════════════════════════════════════════
# HEADER
# ════════════════════════════════════════════════════════════════
st.markdown(
    '<div class="amhani-header">'
    '<div class="amhani-wordmark">CONSULTAMHANi</div>'
    '<div class="amhani-sub">by AMHANi Enterprise · AI Financial Intelligence</div>'
    '</div>',
    unsafe_allow_html=True,
)


# ════════════════════════════════════════════════════════════════
# ACCOUNT BAR
# ════════════════════════════════════════════════════════════════
badge = (
    '<span class="plan-badge badge-pro">PRO ✦</span>'
    if is_sub else
    '<span class="plan-badge badge-free">FREE</span>'
)
col_email, col_logout = st.columns([5, 1])
with col_email:
    st.markdown(
        f'<span style="font-size:0.72rem;color:rgba(250,250,247,0.38);">'
        f'{user_email}</span>{badge}',
        unsafe_allow_html=True,
    )
with col_logout:
    if st.button("Exit", key="logout_btn"):
        logout()
        # Clear all session data on explicit logout
        for k in ("messages", "history_loaded", "is_subscriber", "_pending_memory"):
            st.session_state.pop(k, None)
        _safe_rerun()

st.divider()


# ════════════════════════════════════════════════════════════════
# USAGE DOTS (free users only)
# ════════════════════════════════════════════════════════════════
if not is_sub:
    used      = FREE_LIMIT - remaining(st.session_state.visitor_id)
    dots_html = '<div class="usage-dots">'
    for i in range(FREE_LIMIT):
        if i < used:
            cls = "dot-warn" if (used == FREE_LIMIT - 1 and i == FREE_LIMIT - 2) else "dot-used"
        else:
            cls = "dot-active"
        dots_html += f'<span class="{cls}"></span>'
    dots_html += "</div>"
    st.markdown(dots_html, unsafe_allow_html=True)

    if remaining(st.session_state.visitor_id) == 1:
        st.warning("⚠️ You've reached today's consultation limit. Subscribe for unlimited access.")


# ════════════════════════════════════════════════════════════════
# CHAT HISTORY DISPLAY
# ════════════════════════════════════════════════════════════════
for msg in st.session_state.get("messages", []):
    content = (msg.get("content") or "").strip()
    if not content:
        continue
    if msg["role"] == "user":
        st.markdown(
            f'<div class="user-bubble">{content}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown('<div class="agent-label">✦ AMHANi</div>', unsafe_allow_html=True)
        render_response_content(content)


# ════════════════════════════════════════════════════════════════
# PAYWALL
# ════════════════════════════════════════════════════════════════
if not is_sub and is_limited(st.session_state.visitor_id):
    st.markdown(
        '<div class="paywall-card">'
        '<div class="paywall-title">CONSULTAMHANi</div>'
        '<p class="paywall-body">'
        "You've used today's free consultations.<br/>"
        "Subscribe for unlimited financial intelligence — 24/7."
        "</p></div>",
        unsafe_allow_html=True,
    )
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        if st.button("✦  Subscribe — ₦9,999 / month", use_container_width=True):
            link = create_subscription_link(user_email, user_id)
            if link:
                st.markdown(
                    f'<meta http-equiv="refresh" content="0;url={link}">',
                    unsafe_allow_html=True,
                )
            else:
                st.error("Could not create payment link. Try again.")
    st.markdown(
        '<p class="paywall-price">Unlimited · Real-time data · AI-powered analysis</p>',
        unsafe_allow_html=True,
    )
    st.stop()


# ════════════════════════════════════════════════════════════════
# WELCOME (only when history is empty)
# ════════════════════════════════════════════════════════════════
if not st.session_state.get("messages"):
    greeting = (
        "Welcome back to **CONSULTAMHANi** ✦\n\n"
        if is_sub else
        "Welcome to **CONSULTAMHANi** ✦\n\n"
    )
    greeting += (
        "I'm AMHANi, your financial intelligence agent. I can help with:\n\n"
        "- 📈 Real-time stock prices & charts\n"
        "- 💱 Currency conversion (USD ↔ NGN and more)\n"
        "- 🪙 Crypto prices & 4-hour level analysis\n"
        "- 🧮 Financial calculations (ROI, loans, compound interest, break-even)\n"
        "- 📊 Data analysis & market research\n"
        "- 💡 Investment insights & business advisory\n"
        "- 🖥️ Python-powered financial calculations\n\n"
        "What would you like to explore today?"
    )
    st.markdown('<div class="agent-label">✦ AMHANi</div>', unsafe_allow_html=True)
    render_response_content(greeting)


# ════════════════════════════════════════════════════════════════
# DEFERRED MEMORY SAVE — non-blocking, runs on next natural rerun
# ════════════════════════════════════════════════════════════════
if st.session_state.get("_pending_memory"):
    pending = st.session_state.pop("_pending_memory")
    try:
        extract_and_save_facts(
            pending["user_id"],
            pending["conversation"],
            llm,
        )
    except Exception:
        pass  # Memory errors must never disrupt the chat UI


# ════════════════════════════════════════════════════════════════
# CHAT INPUT
# ════════════════════════════════════════════════════════════════
question = st.chat_input("Ask AMHANi anything financial...")

if question:
    question = question.strip()
    if not question:
        st.stop()

    # Display user message
    st.markdown(
        f'<div class="user-bubble">{question}</div>',
        unsafe_allow_html=True,
    )

    # Save to session + Supabase (user_id validated above)
    st.session_state.messages.append({"role": "user", "content": question})
    if user_id:
        save_message(user_id, "user", question)

    # Increment free usage
    if not is_sub:
        increment_usage(st.session_state.visitor_id)

    # Build short-term memory from confirmed pairs only
    history = sync_memory(st.session_state.messages[:-1])

    # Long-term memory (capped to avoid prompt bloat)
    long_term = ""
    if user_id:
        raw = load_memory(user_id)
        long_term = raw[:400] if raw else ""

    # Run agent
    with st.spinner("AMHANi is thinking..."):
        result = run_agent(
            question,
            long_term_context=long_term,
            chat_history=history,
        )

    answer = result.get("output", "I encountered an issue. Please try again.")
    steps  = result.get("intermediate_steps", [])

    # Reasoning expander — steps are 3-tuples: (name, input, result)
    if steps:
        label = f"🧠 Reasoning — {len(steps)} step{'s' if len(steps) > 1 else ''}"
        with st.expander(label, expanded=False):
            for i, step in enumerate(steps):
                # Defensive unpacking — steps must be 3-tuple
                name  = step[0] if len(step) > 0 else "unknown"
                inp   = step[1] if len(step) > 1 else ""
                obs   = step[2] if len(step) > 2 else ""
                st.markdown(f"**Step {i + 1} — `{name}`**")
                st.code(str(inp)[:400], language="text")
                st.caption(f"Result: {str(obs)[:500]}")
                if i < len(steps) - 1:
                    st.divider()

    # Render answer
    st.markdown('<div class="agent-label">✦ AMHANi</div>', unsafe_allow_html=True)
    render_response_content(answer)

    # Save answer to session + Supabase
    st.session_state.messages.append({"role": "assistant", "content": answer})
    if user_id:
        save_message(user_id, "assistant", answer)

    # Queue background memory extraction
    if user_id:
        st.session_state["_pending_memory"] = {
            "user_id":      user_id,
            "conversation": f"User: {question}\nAgent: {answer}",
        }

    # No st.rerun() — Streamlit reruns naturally after state mutation
