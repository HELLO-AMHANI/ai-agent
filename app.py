# =============================================================
# app.py — AMHANi ENTERPRISE · Streamlit Interface
#
# SCROLL BUTTON — DEFINITIVE FIX (analysis of all 4 attempts):
#
#   Approach 1: <a> in st.markdown → page navigation. FAIL.
#   Approach 2: <button> blast-all-containers in st.markdown →
#     buttons appear but scrollTop has no effect. Streamlit's
#     HTML is inside a React-managed div; html/body have
#     overflow:hidden; window.scrollTo() is a no-op. FAIL.
#   Approach 3 (doc uploaded by user): components.html() +
#     window.parent.document → CORRECT INSIGHT. components.html()
#     renders inside an iframe. window.parent.document is the
#     real Streamlit DOM. Buttons injected into parentDoc.body
#     float correctly and can scroll the real container.
#     Had a race condition but the right architecture.
#   Approach 4 (user's second snippet): components.html() but
#     document.querySelector() without window.parent → queries
#     the iframe's own empty DOM, finds nothing, falls back to
#     documentElement which is not scrollable. FAIL.
#
#   FINAL SOLUTION: components.html() iframe + window.parent
#   ----------------------------------------------------------
#   - Script runs inside the components.html iframe
#   - window.parent.document targets the actual Streamlit page
#   - Style + button elements injected into parentDoc.body
#   - Guard IDs prevent double-injection on Streamlit reruns
#   - getContainer() queries parentDoc (not local doc) and
#     picks the element with the largest scrollHeight
#   - MutationObserver on the real container for auto-scroll
#     and "New message ↓" badge when user has scrolled up
#   - Retry loop (up to 20 × 300ms) waits for Streamlit paint
# =============================================================

import os
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
load_dotenv()

# ── Page config — MUST be the very first Streamlit call ───────
st.set_page_config(
    page_title="CONSULTAMHANi",
    page_icon="✦",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ── All other imports after set_page_config ───────────────────
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
# SCROLL BUTTONS — injected via iframe into parent Streamlit DOM
#
# WHY components.html() + window.parent works:
#   Streamlit serves everything on the same origin. The iframe
#   created by components.html() has allow-same-origin so
#   window.parent.document is accessible without CORS errors.
#   Buttons injected into parentDoc.body sit at the top of the
#   real page stacking context, so position:fixed works correctly
#   and scrollTop on the real scroll container has full effect.
#
# WHY height=0 / scrolling=False:
#   The iframe contributes zero visual space. All visible output
#   (buttons, badge) lives in the parent document, not the iframe.
# ════════════════════════════════════════════════════════════════
components.html("""
<!DOCTYPE html>
<html>
<head>
<style>
  html,body{ margin:0;padding:0;width:0;height:0;overflow:hidden;background:transparent; }
</style>
</head>
<body>
<script>
(function(){

  // ── Access the real Streamlit page, not this iframe ──────
  var P   = window.parent;
  var doc = P.document;

  // ── Inject styles into parent <head> once ────────────────
  // Guard ID prevents re-injection on every Streamlit rerun.
  if (!doc.getElementById("amhani-scroll-style")) {
    var s = doc.createElement("style");
    s.id  = "amhani-scroll-style";
    s.textContent = `
      .amhani-btn {
        position:fixed; right:1.2rem;
        width:42px; height:42px; border-radius:50%;
        background:linear-gradient(135deg,#E8C97A,#C9A84C);
        color:#080807; border:none; cursor:pointer;
        font-size:1.35rem; font-weight:700;
        display:none; align-items:center; justify-content:center;
        z-index:999999; padding:0; line-height:1;
        box-shadow:0 3px 14px rgba(201,168,76,0.45);
        transition:transform .15s,box-shadow .15s;
      }
      .amhani-btn:hover{
        transform:scale(1.12);
        box-shadow:0 5px 20px rgba(201,168,76,0.6);
      }
      #amhani-top{ bottom:5.5rem; }
      #amhani-bot{ bottom:1.2rem; }
      #amhani-badge{
        position:fixed; right:1.2rem; bottom:7.8rem;
        background:#C9A84C; color:#080807;
        padding:5px 12px; border-radius:20px;
        font-size:0.72rem; font-weight:600; font-family:sans-serif;
        display:none; cursor:pointer; z-index:999999;
        box-shadow:0 2px 10px rgba(201,168,76,0.4);
      }
    `;
    doc.head.appendChild(s);
  }

  // ── Inject buttons into parent <body> once ───────────────
  if (!doc.getElementById("amhani-top")) {
    ["amhani-top","amhani-bot"].forEach(function(id,i){
      var b   = doc.createElement("button");
      b.id    = id;
      b.className = "amhani-btn";
      b.innerHTML = i===0 ? "&#8679;" : "&#8681;";
      b.title     = i===0 ? "Scroll to top" : "Scroll to bottom";
      doc.body.appendChild(b);
    });
    var badge = doc.createElement("div");
    badge.id  = "amhani-badge";
    badge.innerHTML = "New message &#8681;";
    doc.body.appendChild(badge);
  }

  // ── Find the real scrollable container in parent DOM ─────
  // Queries parentDoc, NOT the iframe's own document.
  // Picks the element with the largest scrollable area.
  // This is the single most important fix vs approach 4.
  function getContainer(){
    var selectors = [
      "[data-testid='stAppViewContainer']",
      "[data-testid='stMainBlockContainer']",
      "section.main",
      ".main"
    ];
    for(var i=0;i<selectors.length;i++){
      var el = doc.querySelector(selectors[i]);
      if(el && el.scrollHeight > el.clientHeight + 10) return el;
    }
    // Fallback: scan all divs, return the tallest scrollable one
    var best=null, bestH=0;
    doc.querySelectorAll("div").forEach(function(d){
      if(d.scrollHeight > d.clientHeight && d.scrollHeight > bestH){
        bestH = d.scrollHeight; best = d;
      }
    });
    return best;
  }

  // ── Wire everything up once container is available ────────
  function init(){
    var container = getContainer();
    if(!container){ return false; }

    var btnTop = doc.getElementById("amhani-top");
    var btnBot = doc.getElementById("amhani-bot");
    var badge  = doc.getElementById("amhani-badge");
    var userUp = false;

    function toBottom(){
      container.scrollTo({top:container.scrollHeight, behavior:"smooth"});
    }
    function toTop(){
      container.scrollTo({top:0, behavior:"smooth"});
    }

    btnTop.onclick = toTop;
    btnBot.onclick = toBottom;
    badge.onclick  = function(){
      toBottom();
      badge.style.display = "none";
      userUp = false;
    };

    // Show/hide buttons based on scroll position
    container.addEventListener("scroll", function(){
      var fromBot = container.scrollHeight - container.scrollTop - container.clientHeight;
      var atBot   = fromBot < 60;
      userUp      = !atBot;
      btnTop.style.display = container.scrollTop > 200 ? "flex" : "none";
      btnBot.style.display = !atBot ? "flex" : "none";
      if(atBot) badge.style.display = "none";
    });

    // Auto-scroll on new messages; show badge if user scrolled up
    var observer = new MutationObserver(function(){
      if(!userUp){
        toBottom();
      } else {
        badge.style.display = "block";
      }
    });
    observer.observe(container, {childList:true, subtree:true});

    // Scroll to bottom on initial load
    P.setTimeout(toBottom, 600);
    return true;
  }

  // ── Retry until Streamlit has finished painting ───────────
  var tries = 0;
  function tryInit(){
    tries++;
    if(init()) return;           // success
    if(tries < 20) P.setTimeout(tryInit, 300);  // retry up to 20×
  }
  P.setTimeout(tryInit, 400);

})();
</script>
</body>
</html>
""", height=0, scrolling=False)


# ════════════════════════════════════════════════════════════════
# GLOBAL STYLES
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
    margin: 0.5rem 2rem 0.5rem 0; font-size: 0.88rem; color: #FAFAF7;
    line-height: 1.8; white-space: pre-wrap;
}
.agent-label {
    font-size: 0.55rem; letter-spacing: 0.28em; color: #C9A84C;
    text-transform: uppercase; margin-bottom: 0.3rem; font-weight: 600;
}
.usage-dots { display:flex; gap:8px; justify-content:center; margin-bottom:1.2rem; }
.dot-active { width:10px;height:10px;border-radius:50%;background:#C9A84C;display:inline-block; }
.dot-used   { width:10px;height:10px;border-radius:50%;background:#8B6914;opacity:0.35;display:inline-block; }
.dot-warn   { width:10px;height:10px;border-radius:50%;background:#c94c4c;display:inline-block; }

.plan-badge {
    display:inline-block; font-size:0.58rem; letter-spacing:0.18em;
    text-transform:uppercase; font-weight:700; padding:2px 8px;
    border-radius:3px; margin-left:8px; vertical-align:middle;
}
.badge-pro  { background:linear-gradient(135deg,#E8C97A,#C9A84C); color:#080807; }
.badge-free { background:rgba(201,168,76,0.1); color:#C9A84C; border:1px solid rgba(201,168,76,0.3); }

.paywall-card {
    background:rgba(201,168,76,0.05); border:1px solid rgba(201,168,76,0.3);
    border-radius:8px; padding:2.5rem 2rem; text-align:center; margin:1.5rem 0;
}
.paywall-title { font-family:'Cinzel',serif; font-size:1.5rem; color:#C9A84C; letter-spacing:0.18em; margin-bottom:0.6rem; }
.paywall-body  { font-size:0.82rem; color:rgba(250,250,247,0.55); line-height:1.8; margin-bottom:1.5rem; }
.paywall-price { font-size:0.78rem; color:rgba(250,250,247,0.35); margin-top:0.8rem; }

div[data-testid="stTextInput"] input,
div[data-testid="stTextArea"] textarea {
    background:#161610 !important; border:1px solid rgba(201,168,76,0.2) !important;
    color:#FAFAF7 !important; border-radius:3px !important;
}
div[data-testid="stTextInput"] input:focus,
div[data-testid="stTextArea"] textarea:focus {
    border-color:rgba(201,168,76,0.55) !important; box-shadow:none !important;
}
.stButton > button {
    background:linear-gradient(135deg,#E8C97A,#C9A84C) !important;
    color:#080807 !important; font-weight:600 !important;
    border:none !important; border-radius:3px !important;
    letter-spacing:0.1em !important; font-size:0.75rem !important;
}
.stButton > button:hover { opacity:0.88 !important; }
hr { border-color:rgba(201,168,76,0.12) !important; }
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
# SESSION RESTORE
# ════════════════════════════════════════════════════════════════
try_restore_from_cookies()

if "visitor_id" not in st.session_state:
    st.session_state.visitor_id = get_visitor_id()
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
# POST-LOGIN SETUP
# ════════════════════════════════════════════════════════════════
user_email = get_user_email()
user_id    = get_user_id()
is_sub     = check_subscription(user_id)
st.session_state.is_subscriber = is_sub

if not st.session_state.get("history_loaded"):
    raw_msgs = load_messages(user_id, limit=100)
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
        for key in list(st.session_state.keys()):
            del st.session_state[key]
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
        st.markdown(f'<div class="user-bubble">{content}</div>', unsafe_allow_html=True)
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
        if st.button("\u2746  Subscribe \u2014 \u20a69,999 / month", use_container_width=True):
            link = create_subscription_link(user_email, user_id)
            if link:
                st.markdown(
                    f'<meta http-equiv="refresh" content="0;url={link}">',
                    unsafe_allow_html=True,
                )
            else:
                st.error("Could not create payment link. Try again.")
    st.markdown(
        '<p class="paywall-price">Unlimited \u00b7 Real-time data \u00b7 AI-powered analysis</p>',
        unsafe_allow_html=True,
    )
    st.stop()


# ════════════════════════════════════════════════════════════════
# WELCOME MESSAGE
# ════════════════════════════════════════════════════════════════
if not st.session_state.get("messages"):
    greeting = (
        "Welcome back to **CONSULTAMHANi** \u2746\n\n"
        if is_sub else
        "Welcome to **CONSULTAMHANi** \u2746\n\n"
    )
    greeting += (
        "I'm AMHANi, your financial intelligence agent. I can help with:\n\n"
        "- \U0001f4c8 Real-time stock prices & charts\n"
        "- \U0001f4b1 Currency conversion (USD \u2194 NGN and more)\n"
        "- \U0001fa99 Crypto prices & 4-hour level analysis\n"
        "- \U0001f4ca US30, SPX, NAS100 4-hour technical analysis\n"
        "- \U0001f9ee Financial calculations (ROI, loans, compound interest, break-even)\n"
        "- \U0001f4ca Data analysis & market research\n"
        "- \U0001f4a1 Investment insights & business advisory\n"
        "- \U0001f5a5 Python-powered financial calculations\n\n"
        "What would you like to explore today?"
    )
    st.markdown('<div class="agent-label">\u2746 AMHANi</div>', unsafe_allow_html=True)
    render_response_content(greeting)


# ════════════════════════════════════════════════════════════════
# DEFERRED MEMORY SAVE
# ════════════════════════════════════════════════════════════════
if st.session_state.get("_pending_memory"):
    pending = st.session_state.pop("_pending_memory")
    try:
        extract_and_save_facts(pending["user_id"], pending["conversation"], llm)
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════
# CHAT INPUT
# ════════════════════════════════════════════════════════════════
question = st.chat_input("Ask AMHANi anything financial...")

if question:
    question = question.strip()
    if not question:
        st.stop()

    st.markdown(f'<div class="user-bubble">{question}</div>', unsafe_allow_html=True)

    st.session_state.messages.append({"role": "user", "content": question})
    if user_id:
        save_message(user_id, "user", question)

    if not is_sub:
        increment_usage(st.session_state.visitor_id)

    history   = sync_memory(st.session_state.messages[:-1])
    long_term = ""
    if user_id:
        raw       = load_memory(user_id)
        long_term = raw[:400] if raw else ""

    with st.spinner("AMHANi is thinking..."):
        result = run_agent(question, long_term_context=long_term, chat_history=history)

    answer = result.get("output", "I encountered an issue. Please try again.")
    steps  = result.get("intermediate_steps", [])

    if steps:
        label = f"\U0001f9e0 Reasoning \u2014 {len(steps)} step{'s' if len(steps) > 1 else ''}"
        with st.expander(label, expanded=False):
            for i, step in enumerate(steps):
                name = step[0] if len(step) > 0 else "unknown"
                inp  = step[1] if len(step) > 1 else ""
                obs  = step[2] if len(step) > 2 else ""
                st.markdown(f"**Step {i + 1} \u2014 `{name}`**")
                st.code(str(inp)[:400], language="text")
                st.caption(f"Result: {str(obs)[:500]}")
                if i < len(steps) - 1:
                    st.divider()

    st.markdown('<div class="agent-label">\u2746 AMHANi</div>', unsafe_allow_html=True)
    render_response_content(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
    if user_id:
        save_message(user_id, "assistant", answer)

    if user_id:
        st.session_state["_pending_memory"] = {
            "user_id":      user_id,
            "conversation": f"User: {question}\nAgent: {answer}",
        }
