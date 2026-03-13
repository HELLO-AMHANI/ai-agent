# admin.py — AMHANi | Admin Dashboard
# All secrets loaded from config.py (works locally AND on Streamlit Cloud)

import time
import streamlit as st
from config import ADMIN_PASSWORD, SUPABASE_URL, SUPABASE_SERVICE_KEY, PAYSTACK_PLAN_CODE
from limiter import get_all_stats, reset_ip, FREE_LIMIT

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AMHANi Admin",
    page_icon="⚙",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@600;700&family=Montserrat:wght@300;400;500;600&display=swap');
html, body, [class*="css"] { font-family:'Montserrat',sans-serif; background:#0A0A08 !important; color:#FAFAF7 !important; }
.stApp { background:#0A0A08; }
#MainMenu, footer, header { visibility:hidden; }
.admin-header { border-bottom:1px solid rgba(201,168,76,0.25); padding-bottom:1rem; margin-bottom:2rem; }
.admin-title { font-family:'Cormorant Garamond',serif; font-size:2rem; font-weight:700; color:#C9A84C; letter-spacing:0.15em; }
.admin-sub { font-size:0.62rem; letter-spacing:0.3em; text-transform:uppercase; color:#8B6914; margin-top:0.3rem; }
.section-label { font-size:0.6rem; letter-spacing:0.28em; text-transform:uppercase; color:#8B6914; margin-bottom:1rem; margin-top:1.5rem; border-bottom:1px solid rgba(201,168,76,0.1); padding-bottom:0.5rem; }
.metric-card { background:#1A1A14; border:1px solid rgba(201,168,76,0.2); border-radius:8px; padding:1.5rem; text-align:center; }
.metric-num { font-family:'Cormorant Garamond',serif; font-size:2.5rem; font-weight:700; color:#E8C97A; }
.metric-label { font-size:0.6rem; letter-spacing:0.2em; text-transform:uppercase; color:rgba(250,250,247,0.4); margin-top:0.3rem; }
.metric-card.green { border-color:rgba(39,174,96,0.3); }
.metric-card.green .metric-num { color:#2ECC71; }
.stTextInput>div>div>input { background:#1A1A14 !important; border:1px solid rgba(201,168,76,0.25) !important; border-radius:6px !important; color:#FAFAF7 !important; font-family:'Montserrat',sans-serif !important; }
.stButton>button { background:linear-gradient(135deg,#E8C97A,#C9A84C) !important; color:#0A0A08 !important; border:none !important; border-radius:6px !important; font-weight:600 !important; font-size:0.72rem !important; letter-spacing:0.12em !important; text-transform:uppercase !important; }
</style>
""", unsafe_allow_html=True)


# ── Password gate ─────────────────────────────────────────────────────────────
if "admin_auth" not in st.session_state:
    st.session_state.admin_auth = False

if not st.session_state.admin_auth:
    st.markdown("""
    <div style="max-width:360px; margin:8rem auto; text-align:center;">
        <div style="font-family:'Cormorant Garamond',serif; font-size:2.2rem; color:#C9A84C; letter-spacing:0.18em; margin-bottom:0.3rem;">AMHANi</div>
        <div style="font-size:0.55rem; letter-spacing:0.4em; color:#8B6914; text-transform:uppercase; margin-bottom:0.3rem;">Enterprise</div>
        <div style="font-size:0.58rem; letter-spacing:0.28em; color:rgba(250,250,247,0.25); text-transform:uppercase; margin-bottom:2rem;">Admin Access</div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        pwd = st.text_input("Password", type="password", key="admin_pwd", placeholder="Enter admin password")
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("ENTER", use_container_width=True):
            if pwd == ADMIN_PASSWORD:
                st.session_state.admin_auth = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    st.stop()


# ── Dashboard ──────────────────────────────────────────────────────────────────
st.markdown("""
<div class="admin-header">
    <div class="admin-title">AMHANi Admin</div>
    <div class="admin-sub">CONSULTAMHANi · Analytics & Subscriber Dashboard</div>
</div>
""", unsafe_allow_html=True)


# ── Pull subscriber data from Supabase ────────────────────────────────────────
def get_subscriber_data() -> dict:
    try:
        from supabase import create_client
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            return {"total": 0, "active": 0, "mrr": 0, "rows": []}
        sb     = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        result = sb.table("subscribers").select("*").order("created_at", desc=True).execute()
        rows   = result.data or []
        active = sum(1 for r in rows if r.get("status") == "active")
        return {
            "total":  len(rows),
            "active": active,
            "mrr":    active * 9999,
            "rows":   rows,
        }
    except Exception as e:
        return {"total": 0, "active": 0, "mrr": 0, "rows": [], "error": str(e)}


stats   = get_all_stats()
sub_data = get_subscriber_data()

# ── Section 1: Revenue ────────────────────────────────────────────────────────
st.markdown('<div class="section-label">Revenue & Subscribers</div>', unsafe_allow_html=True)

c1, c2, c3 = st.columns(3)
with c1:
    st.markdown(f"""
    <div class="metric-card green">
        <div class="metric-num">{sub_data['active']}</div>
        <div class="metric-label">Active Subscribers</div>
    </div>""", unsafe_allow_html=True)
with c2:
    st.markdown(f"""
    <div class="metric-card green">
        <div class="metric-num">₦{sub_data['mrr']:,}</div>
        <div class="metric-label">Monthly Revenue (MRR)</div>
    </div>""", unsafe_allow_html=True)
with c3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-num">{sub_data['total']}</div>
        <div class="metric-label">Total Signups</div>
    </div>""", unsafe_allow_html=True)

# ── Section 2: Usage Funnel ───────────────────────────────────────────────────
st.markdown('<div class="section-label">Usage & Conversion Funnel</div>', unsafe_allow_html=True)

c4, c5, c6, c7 = st.columns(4)
with c4:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-num">{stats['total_visitors']}</div>
        <div class="metric-label">Total Visitors</div>
    </div>""", unsafe_allow_html=True)
with c5:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-num">{stats['total_questions']}</div>
        <div class="metric-label">Questions Asked</div>
    </div>""", unsafe_allow_html=True)
with c6:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-num">{stats['hit_paywall']}</div>
        <div class="metric-label">Hit Paywall</div>
    </div>""", unsafe_allow_html=True)
with c7:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-num">{stats['conversion_rate']}</div>
        <div class="metric-label">Paywall Rate</div>
    </div>""", unsafe_allow_html=True)

# ── Section 3: Subscriber list ────────────────────────────────────────────────
st.markdown('<div class="section-label">Subscriber List</div>', unsafe_allow_html=True)

if sub_data.get("error"):
    st.warning(f"Could not load subscriber list: {sub_data['error']}")
elif not sub_data["rows"]:
    st.markdown("<span style='font-size:0.8rem; color:rgba(250,250,247,0.3);'>No subscribers yet. Share #CONSULTAMHANi to drive sign-ups.</span>", unsafe_allow_html=True)
else:
    for sub in sub_data["rows"]:
        status     = sub.get("status", "unknown")
        email      = sub.get("email", "N/A")
        created    = sub.get("created_at", "")[:10]
        status_col = "#2ECC71" if status == "active" else "#E74C3C"
        col_a, col_b, col_c = st.columns([3, 2, 2])
        with col_a:
            st.markdown(f"<span style='font-size:0.78rem; color:rgba(250,250,247,0.75);'>{email}</span>", unsafe_allow_html=True)
        with col_b:
            st.markdown(f"<span style='font-size:0.72rem; color:{status_col}; text-transform:uppercase; letter-spacing:0.1em;'>● {status}</span>", unsafe_allow_html=True)
        with col_c:
            st.markdown(f"<span style='font-size:0.72rem; color:rgba(250,250,247,0.35);'>Joined {created}</span>", unsafe_allow_html=True)

# ── Section 4: Visitor log ────────────────────────────────────────────────────
st.markdown('<div class="section-label">Free Visitor Log</div>', unsafe_allow_html=True)

raw = stats.get("raw", {})
if not raw:
    st.markdown("<span style='font-size:0.8rem; color:rgba(250,250,247,0.3);'>No visitor data yet.</span>", unsafe_allow_html=True)
else:
    for visitor_id, record in sorted(raw.items(), key=lambda x: x[1].get("last_seen", 0), reverse=True):
        count     = record.get("count", 0)
        last_seen = record.get("last_seen", 0)
        hit_wall  = count >= FREE_LIMIT
        time_str  = time.strftime("%Y-%m-%d %H:%M", time.localtime(last_seen)) if last_seen else "N/A"
        status    = "🔴 Hit Paywall" if hit_wall else f"🟡 {count}/{FREE_LIMIT} used"
        short_id  = visitor_id[:16] + "..."

        col_a, col_b, col_c, col_d = st.columns([3, 2, 2, 1])
        with col_a:
            st.markdown(f"<span style='font-size:0.72rem; color:rgba(250,250,247,0.4); font-family:monospace;'>{short_id}</span>", unsafe_allow_html=True)
        with col_b:
            st.markdown(f"<span style='font-size:0.72rem; color:rgba(250,250,247,0.5);'>{time_str}</span>", unsafe_allow_html=True)
        with col_c:
            st.markdown(f"<span style='font-size:0.72rem;'>{status}</span>", unsafe_allow_html=True)
        with col_d:
            if st.button("Reset", key=f"reset_{visitor_id}"):
                reset_ip(visitor_id)
                st.rerun()

# ── Controls ──────────────────────────────────────────────────────────────────
st.markdown("<br>", unsafe_allow_html=True)
col_r, col_l, _ = st.columns([1, 1, 4])
with col_r:
    if st.button("REFRESH", use_container_width=True):
        st.rerun()
with col_l:
    if st.button("LOG OUT", use_container_width=True):
        st.session_state.admin_auth = False
        st.rerun()

st.markdown("""
<div style="text-align:center; padding:2rem 0 0.5rem; border-top:1px solid rgba(201,168,76,0.08); margin-top:2rem;">
    <span style="font-size:0.58rem; letter-spacing:0.22em; text-transform:uppercase; color:rgba(201,168,76,0.2);">
        AMHANi Enterprise Admin &nbsp;·&nbsp; Internal Use Only
    </span>
</div>
""", unsafe_allow_html=True)
