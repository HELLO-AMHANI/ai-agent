# admin.py — AMHANi | Phase 3: Admin Analytics View
# Run with: streamlit run admin.py
# Protect this with a password before deploying publicly

import os
import streamlit as st
from dotenv import load_dotenv
from limiter import get_all_stats, reset_ip, FREE_LIMIT

load_dotenv()

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AMHANi Admin",
    page_icon="⚙",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Admin password gate ───────────────────────────────────────────────────────
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "amhani-admin-2024")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@600;700&family=Montserrat:wght@300;400;500;600&display=swap');
html, body, [class*="css"] { font-family:'Montserrat',sans-serif; background:#0A0A08 !important; color:#FAFAF7 !important; }
.stApp { background:#0A0A08; }
#MainMenu, footer, header { visibility:hidden; }
.admin-header { border-bottom:1px solid rgba(201,168,76,0.25); padding-bottom:1rem; margin-bottom:2rem; }
.admin-title { font-family:'Cormorant Garamond',serif; font-size:2rem; font-weight:700; color:#C9A84C; letter-spacing:0.15em; }
.admin-sub { font-size:0.65rem; letter-spacing:0.3em; text-transform:uppercase; color:#8B6914; margin-top:0.2rem; }
.metric-card { background:#1A1A14; border:1px solid rgba(201,168,76,0.2); border-radius:8px; padding:1.5rem; text-align:center; }
.metric-num { font-family:'Cormorant Garamond',serif; font-size:2.5rem; font-weight:700; color:#E8C97A; }
.metric-label { font-size:0.65rem; letter-spacing:0.2em; text-transform:uppercase; color:rgba(250,250,247,0.4); margin-top:0.3rem; }
.stTextInput>div>div>input { background:#1A1A14 !important; border:1px solid rgba(201,168,76,0.25) !important; border-radius:6px !important; color:#FAFAF7 !important; font-family:'Montserrat',sans-serif !important; }
.stButton>button { background:linear-gradient(135deg,#E8C97A,#C9A84C) !important; color:#0A0A08 !important; border:none !important; border-radius:6px !important; font-weight:600 !important; font-size:0.75rem !important; letter-spacing:0.12em !important; text-transform:uppercase !important; }
.visitor-row { background:#111109; border:1px solid rgba(201,168,76,0.1); border-radius:6px; padding:0.6rem 1rem; margin-bottom:0.4rem; display:flex; justify-content:space-between; align-items:center; font-size:0.78rem; }
</style>
""", unsafe_allow_html=True)

# ── Password gate ─────────────────────────────────────────────────────────────
if "admin_auth" not in st.session_state:
    st.session_state.admin_auth = False

if not st.session_state.admin_auth:
    st.markdown("""
    <div style="max-width:360px; margin:8rem auto; text-align:center;">
        <div style="font-family:'Cormorant Garamond',serif; font-size:2rem; color:#C9A84C; letter-spacing:0.15em; margin-bottom:0.5rem;">AMHANi</div>
        <div style="font-size:0.62rem; letter-spacing:0.3em; color:#8B6914; text-transform:uppercase; margin-bottom:2rem;">Admin Access</div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        pwd = st.text_input("Password", type="password", key="admin_pwd")
        if st.button("ENTER", use_container_width=True):
            if pwd == ADMIN_PASSWORD:
                st.session_state.admin_auth = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    st.stop()

# ── Admin dashboard ───────────────────────────────────────────────────────────
st.markdown("""
<div class="admin-header">
    <div class="admin-title">AMHANi Admin</div>
    <div class="admin-sub">CONSULTAMHANi · Analytics Dashboard</div>
</div>
""", unsafe_allow_html=True)

# Load stats
stats = get_all_stats()

# ── Metric cards (Step 5) ─────────────────────────────────────────────────────
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-num">{stats['total_visitors']}</div>
        <div class="metric-label">Total Visitors</div>
    </div>""", unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-num">{stats['total_questions']}</div>
        <div class="metric-label">Questions Asked</div>
    </div>""", unsafe_allow_html=True)

with col3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-num">{stats['hit_paywall']}</div>
        <div class="metric-label">Hit Paywall</div>
    </div>""", unsafe_allow_html=True)

with col4:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-num">{stats['conversion_rate']}</div>
        <div class="metric-label">Paywall Rate</div>
    </div>""", unsafe_allow_html=True)

with col5:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-num">{stats['active_today']}</div>
        <div class="metric-label">Active Today</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Visitor breakdown ─────────────────────────────────────────────────────────
st.markdown("""
<div style="font-size:0.65rem; letter-spacing:0.25em; text-transform:uppercase; color:#8B6914; margin-bottom:1rem;">
    Visitor Log
</div>
""", unsafe_allow_html=True)

raw = stats.get("raw", {})

if not raw:
    st.markdown("""
    <div style="text-align:center; padding:2rem; color:rgba(250,250,247,0.3); font-size:0.82rem;">
        No visitors yet. Share #CONSULTAMHANi to get traffic.
    </div>
    """, unsafe_allow_html=True)
else:
    import time
    for visitor_id, record in sorted(raw.items(), key=lambda x: x[1].get("last_seen", 0), reverse=True):
        count     = record.get("count", 0)
        last_seen = record.get("last_seen", 0)
        hit_wall  = count >= FREE_LIMIT
        time_str  = time.strftime("%Y-%m-%d %H:%M", time.localtime(last_seen)) if last_seen else "N/A"
        status    = "🔴 Hit Paywall" if hit_wall else f"🟡 {count}/{FREE_LIMIT} used"
        short_id  = visitor_id[:16] + "..."

        col_a, col_b, col_c, col_d = st.columns([3, 2, 2, 1])
        with col_a:
            st.markdown(f"<span style='font-size:0.75rem; color:rgba(250,250,247,0.5); font-family:monospace;'>{short_id}</span>", unsafe_allow_html=True)
        with col_b:
            st.markdown(f"<span style='font-size:0.75rem; color:rgba(250,250,247,0.6);'>{time_str}</span>", unsafe_allow_html=True)
        with col_c:
            st.markdown(f"<span style='font-size:0.75rem;'>{status}</span>", unsafe_allow_html=True)
        with col_d:
            if st.button("Reset", key=f"reset_{visitor_id}"):
                reset_ip(visitor_id)
                st.success("Reset.")
                st.rerun()

# ── Refresh & logout ──────────────────────────────────────────────────────────
st.markdown("<br>", unsafe_allow_html=True)
col_r, col_l, col_empty = st.columns([1, 1, 4])
with col_r:
    if st.button("REFRESH DATA", use_container_width=True):
        st.rerun()
with col_l:
    if st.button("LOG OUT", use_container_width=True):
        st.session_state.admin_auth = False
        st.rerun()

st.markdown("""
<div style="text-align:center; padding:2rem 0 0.5rem; border-top:1px solid rgba(201,168,76,0.1); margin-top:2rem;">
    <span style="font-size:0.6rem; letter-spacing:0.2em; text-transform:uppercase; color:rgba(201,168,76,0.3);">
        AMHANi Admin &nbsp;·&nbsp; Internal Use Only
    </span>
</div>
""", unsafe_allow_html=True)
