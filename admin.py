# admin.py — CONSULTAMHANi | Admin Dashboard
# Run: streamlit run admin.py --server.port 8502

import time
import streamlit as st
from config import ADMIN_PASSWORD, SUPABASE_URL, SUPABASE_SERVICE_KEY, PAYSTACK_PLAN_CODE
from limiter import get_all_stats, reset_ip, FREE_LIMIT

st.set_page_config(
    page_title="CONSULTAMHANi Admin",
    page_icon="⚙",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@600;700&family=Cinzel:wght@600;700&family=Montserrat:wght@300;400;500;600&display=swap');

:root {
    --gold: #C9A84C; --gold-light: #E8C97A; --gold-dim: #8B6914;
    --white: #FAFAF7; --black: #080807;
    --surface: #0F0F0C; --surface-2: #161610;
    --border: rgba(201,168,76,0.2); --muted: rgba(250,250,247,0.45);
    --green: #2ECC71; --red: #E74C3C;
}
html, body, [class*="css"] { font-family:'Montserrat',sans-serif; background:var(--black) !important; color:var(--white) !important; }
.stApp { background:var(--black) !important; }
#MainMenu, footer, header { visibility:hidden; }

.admin-header { border-bottom:1px solid var(--border); padding-bottom:1.2rem; margin-bottom:2rem; }
.admin-logo { font-family:'Cinzel',serif; font-size:1.6rem; font-weight:700; color:var(--gold); letter-spacing:0.18em; }
.admin-sub { font-size:0.58rem; letter-spacing:0.32em; text-transform:uppercase; color:var(--gold-dim); margin-top:0.3rem; }

.sec-label { font-size:0.58rem; letter-spacing:0.3em; text-transform:uppercase; color:var(--gold-dim); margin-bottom:0.8rem; margin-top:1.8rem; padding-bottom:0.4rem; border-bottom:1px solid rgba(201,168,76,0.08); }

.mcard { background:var(--surface-2); border:1px solid var(--border); border-radius:8px; padding:1.4rem; text-align:center; }
.mcard.green { border-color:rgba(39,174,96,0.28); }
.mnum { font-family:'Cormorant Garamond',serif; font-size:2.4rem; font-weight:700; color:var(--gold-light); line-height:1; }
.mcard.green .mnum { color:var(--green); }
.mlabel { font-size:0.58rem; letter-spacing:0.2em; text-transform:uppercase; color:rgba(250,250,247,0.35); margin-top:0.4rem; }

.stTextInput>div>div>input { background:var(--surface-2) !important; border:1px solid var(--border) !important; border-radius:6px !important; color:var(--white) !important; font-family:'Montserrat',sans-serif !important; padding:0.65rem 1rem !important; }
.stButton>button { background:linear-gradient(135deg,var(--gold-light),var(--gold)) !important; color:var(--black) !important; border:none !important; border-radius:5px !important; font-weight:700 !important; font-size:0.68rem !important; letter-spacing:0.15em !important; text-transform:uppercase !important; }

.sub-row { display:flex; align-items:center; justify-content:space-between; padding:0.65rem 0; border-bottom:1px solid rgba(201,168,76,0.06); }
.sub-email { font-size:0.8rem; color:rgba(250,250,247,0.75); }
.sub-status-active { font-size:0.65rem; color:var(--green); font-weight:600; letter-spacing:0.12em; text-transform:uppercase; }
.sub-status-inactive { font-size:0.65rem; color:var(--red); font-weight:600; letter-spacing:0.12em; text-transform:uppercase; }
.sub-date { font-size:0.68rem; color:rgba(250,250,247,0.3); }

.vrow { display:flex; align-items:center; gap:1rem; padding:0.5rem 0; border-bottom:1px solid rgba(201,168,76,0.05); font-size:0.72rem; }
.vid { color:rgba(250,250,247,0.3); font-family:monospace; font-size:0.65rem; flex:2; }
.vtime { color:rgba(250,250,247,0.4); flex:2; }
.vstatus { flex:2; }
</style>
""", unsafe_allow_html=True)


# ── Password gate ─────────────────────────────────────────────────────────────
if "admin_auth" not in st.session_state:
    st.session_state.admin_auth = False

if not st.session_state.admin_auth:
    st.markdown("""
    <div style="max-width:340px; margin:7rem auto; text-align:center;">
        <div style="font-family:'Cinzel',serif; font-size:1.8rem; color:#C9A84C; letter-spacing:0.2em; margin-bottom:0.3rem;">CONSULTAMHANi</div>
        <div style="font-size:0.55rem; letter-spacing:0.38em; color:#8B6914; text-transform:uppercase; margin-bottom:2.5rem;">Admin Panel · AMHANi Enterprise</div>
    </div>
    """, unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        pwd = st.text_input("Admin password", type="password", key="apwd", placeholder="Enter password")
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("ENTER DASHBOARD", use_container_width=True):
            if pwd == ADMIN_PASSWORD:
                st.session_state.admin_auth = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    st.stop()


# ── Dashboard header ──────────────────────────────────────────────────────────
st.markdown("""
<div class="admin-header">
    <div class="admin-logo">CONSULTAMHANi</div>
    <div class="admin-sub">Admin Dashboard · AMHANi Enterprise</div>
</div>
""", unsafe_allow_html=True)


# ── Load data ─────────────────────────────────────────────────────────────────
def get_sub_data() -> dict:
    try:
        from supabase import create_client
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            return {"total": 0, "active": 0, "mrr": 0, "rows": [], "error": "Missing Supabase credentials"}
        sb     = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        result = sb.table("subscribers").select("*").order("created_at", desc=True).execute()
        rows   = result.data or []
        active = sum(1 for r in rows if r.get("status") == "active")
        return {"total": len(rows), "active": active, "mrr": active * 29999, "rows": rows}
    except Exception as e:
        return {"total": 0, "active": 0, "mrr": 0, "rows": [], "error": str(e)}


stats    = get_all_stats()
sub_data = get_sub_data()


# ── Revenue metrics ───────────────────────────────────────────────────────────
st.markdown('<div class="sec-label">Revenue & Subscribers</div>', unsafe_allow_html=True)
c1, c2, c3 = st.columns(3)
with c1:
    st.markdown(f'<div class="mcard green"><div class="mnum">{sub_data["active"]}</div><div class="mlabel">Active Subscribers</div></div>', unsafe_allow_html=True)
with c2:
    st.markdown(f'<div class="mcard green"><div class="mnum">₦{sub_data["mrr"]:,}</div><div class="mlabel">Monthly Revenue (MRR)</div></div>', unsafe_allow_html=True)
with c3:
    st.markdown(f'<div class="mcard"><div class="mnum">{sub_data["total"]}</div><div class="mlabel">Total Signups</div></div>', unsafe_allow_html=True)


# ── Funnel metrics ────────────────────────────────────────────────────────────
st.markdown('<div class="sec-label">Usage & Conversion Funnel</div>', unsafe_allow_html=True)
c4, c5, c6, c7 = st.columns(4)
with c4:
    st.markdown(f'<div class="mcard"><div class="mnum">{stats["total_visitors"]}</div><div class="mlabel">Total Visitors</div></div>', unsafe_allow_html=True)
with c5:
    st.markdown(f'<div class="mcard"><div class="mnum">{stats["total_questions"]}</div><div class="mlabel">Questions Asked</div></div>', unsafe_allow_html=True)
with c6:
    st.markdown(f'<div class="mcard"><div class="mnum">{stats["hit_paywall"]}</div><div class="mlabel">Hit Paywall</div></div>', unsafe_allow_html=True)
with c7:
    st.markdown(f'<div class="mcard"><div class="mnum">{stats["conversion_rate"]}</div><div class="mlabel">Paywall Rate</div></div>', unsafe_allow_html=True)


# ── Subscriber list ───────────────────────────────────────────────────────────
st.markdown('<div class="sec-label">Subscriber List</div>', unsafe_allow_html=True)

if sub_data.get("error"):
    st.warning(f"Could not load subscribers: {sub_data['error']}")
elif not sub_data["rows"]:
    st.markdown("<span style='font-size:0.8rem; color:rgba(250,250,247,0.28);'>No subscribers yet — share #CONSULTAMHANi to drive sign-ups.</span>", unsafe_allow_html=True)
else:
    for sub in sub_data["rows"]:
        status  = sub.get("status", "unknown")
        email   = sub.get("email", "N/A")
        created = sub.get("created_at", "")[:10]
        s_class = "sub-status-active" if status == "active" else "sub-status-inactive"
        s_icon  = "●" if status == "active" else "○"
        ca, cb, cc = st.columns([3, 2, 2])
        with ca:
            st.markdown(f'<span class="sub-email">{email}</span>', unsafe_allow_html=True)
        with cb:
            st.markdown(f'<span class="{s_class}">{s_icon} {status}</span>', unsafe_allow_html=True)
        with cc:
            st.markdown(f'<span class="sub-date">Joined {created}</span>', unsafe_allow_html=True)


# ── Visitor log ───────────────────────────────────────────────────────────────
st.markdown('<div class="sec-label">Free Visitor Log</div>', unsafe_allow_html=True)

raw = stats.get("raw", {})
if not raw:
    st.markdown("<span style='font-size:0.8rem; color:rgba(250,250,247,0.28);'>No visitor data yet.</span>", unsafe_allow_html=True)
else:
    for vid, record in sorted(raw.items(), key=lambda x: x[1].get("last_seen", 0), reverse=True):
        count    = record.get("count", 0)
        ls       = record.get("last_seen", 0)
        hit      = count >= FREE_LIMIT
        tstr     = time.strftime("%Y-%m-%d %H:%M", time.localtime(ls)) if ls else "N/A"
        status   = "🔴 Hit Paywall" if hit else f"🟡 {count}/{FREE_LIMIT} used"
        short_id = vid[:18] + "…"
        ca, cb, cc, cd = st.columns([3, 2, 2, 1])
        with ca:
            st.markdown(f'<span style="font-size:0.68rem; color:rgba(250,250,247,0.3); font-family:monospace;">{short_id}</span>', unsafe_allow_html=True)
        with cb:
            st.markdown(f'<span style="font-size:0.7rem; color:rgba(250,250,247,0.4);">{tstr}</span>', unsafe_allow_html=True)
        with cc:
            st.markdown(f'<span style="font-size:0.72rem;">{status}</span>', unsafe_allow_html=True)
        with cd:
            if st.button("Reset", key=f"r_{vid}"):
                reset_ip(vid)
                st.rerun()


# ── Controls ──────────────────────────────────────────────────────────────────
st.markdown("<br>", unsafe_allow_html=True)
cr, cl, _ = st.columns([1, 1, 4])
with cr:
    if st.button("REFRESH", use_container_width=True):
        st.rerun()
with cl:
    if st.button("LOG OUT", use_container_width=True):
        st.session_state.admin_auth = False
        st.rerun()

st.markdown("""
<div style="text-align:center; padding:2rem 0 0.5rem; border-top:1px solid rgba(201,168,76,0.07); margin-top:2rem;">
    <span style="font-size:0.55rem; letter-spacing:0.25em; text-transform:uppercase; color:rgba(201,168,76,0.2);">
        CONSULTAMHANi Admin · AMHANi Enterprise · Internal Use Only
    </span>
</div>
""", unsafe_allow_html=True)
