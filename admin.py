# =============================================================
# admin.py — CONSULTAMHANi | Admin Dashboard
# Run: streamlit run admin.py --server.port 8502
#
# NVIDIA FIX 3 — WHY ADMIN SHOWED 0 USERS:
#
#   Problem A: 'subscribers' table only holds PAID users.
#   The two accounts that exist are free auth signups stored
#   in Supabase auth.users — not in the subscribers table.
#   The admin never read auth.users, so it always showed 0.
#   FIX: get_auth_users() calls sb.auth.admin.list_users()
#   using the service key. Now ALL registered accounts appear
#   in a dedicated "Registered Users" section regardless of
#   whether they have paid.
#
#   Problem B: visitor_sessions table may not exist in Supabase.
#   limiter.py upserts silently fail if the table is missing.
#   No visitor data ever accumulates → "No visitor data yet."
#   FIX: check_supabase_setup() probes each table and surfaces
#   exact error messages. If visitor_sessions is missing, the
#   admin shows the SQL needed to create it.
#
#   Problem C (prev patch): for loop indentation bug — entire
#   visitor display block was outside the loop. KEPT FIXED.
# =============================================================

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
    --gold:#C9A84C; --gold-light:#E8C97A; --gold-dim:#8B6914;
    --white:#FAFAF7; --black:#080807; --surface:#0F0F0C; --surface-2:#161610;
    --border:rgba(201,168,76,0.2); --green:#2ECC71; --red:#E74C3C;
}
html,body,[class*="css"]{ font-family:'Montserrat',sans-serif; background:var(--black)!important; color:var(--white)!important; }
.stApp{ background:var(--black)!important; }
#MainMenu,footer,header{ visibility:hidden; }

.admin-header{ border-bottom:1px solid var(--border); padding-bottom:1.2rem; margin-bottom:2rem; }
.admin-logo{ font-family:'Cinzel',serif; font-size:1.6rem; font-weight:700; color:var(--gold); letter-spacing:0.18em; }
.admin-sub{ font-size:0.58rem; letter-spacing:0.32em; text-transform:uppercase; color:var(--gold-dim); margin-top:0.3rem; }

.sec-label{ font-size:0.58rem; letter-spacing:0.3em; text-transform:uppercase; color:var(--gold-dim);
    margin-bottom:0.8rem; margin-top:1.8rem; padding-bottom:0.4rem; border-bottom:1px solid rgba(201,168,76,0.08); }

.mcard{ background:var(--surface-2); border:1px solid var(--border); border-radius:8px; padding:1.4rem; text-align:center; }
.mcard.green{ border-color:rgba(39,174,96,0.28); }
.mnum{ font-family:'Cormorant Garamond',serif; font-size:2.4rem; font-weight:700; color:var(--gold-light); line-height:1; }
.mcard.green .mnum{ color:var(--green); }
.mlabel{ font-size:0.58rem; letter-spacing:0.2em; text-transform:uppercase; color:rgba(250,250,247,0.35); margin-top:0.4rem; }

.stTextInput>div>div>input{ background:var(--surface-2)!important; border:1px solid var(--border)!important;
    border-radius:6px!important; color:var(--white)!important; padding:0.65rem 1rem!important; }
.stButton>button{ background:linear-gradient(135deg,var(--gold-light),var(--gold))!important;
    color:var(--black)!important; border:none!important; border-radius:5px!important;
    font-weight:700!important; font-size:0.68rem!important; letter-spacing:0.15em!important; text-transform:uppercase!important; }

.sub-email{ font-size:0.8rem; color:rgba(250,250,247,0.75); }
.sub-status-active{ font-size:0.65rem; color:var(--green); font-weight:600; letter-spacing:0.12em; text-transform:uppercase; }
.sub-status-inactive{ font-size:0.65rem; color:var(--red); font-weight:600; letter-spacing:0.12em; text-transform:uppercase; }
.sub-date{ font-size:0.68rem; color:rgba(250,250,247,0.3); }

.setup-ok  { color:#2ECC71; font-size:0.75rem; }
.setup-fail{ color:#E74C3C; font-size:0.75rem; }
</style>
""", unsafe_allow_html=True)


# ── Password gate ─────────────────────────────────────────────
if "admin_auth" not in st.session_state:
    st.session_state.admin_auth = False

if not st.session_state.admin_auth:
    st.markdown("""
    <div style="max-width:340px;margin:7rem auto;text-align:center;">
        <div style="font-family:'Cinzel',serif;font-size:1.8rem;color:#C9A84C;letter-spacing:0.2em;margin-bottom:0.3rem;">CONSULTAMHANi</div>
        <div style="font-size:0.55rem;letter-spacing:0.38em;color:#8B6914;text-transform:uppercase;margin-bottom:2.5rem;">Admin Panel · AMHANi Enterprise</div>
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


# ── Dashboard header ──────────────────────────────────────────
st.markdown("""
<div class="admin-header">
    <div class="admin-logo">CONSULTAMHANi</div>
    <div class="admin-sub">Admin Dashboard · AMHANi Enterprise</div>
</div>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════
# DATA LOADERS
# ════════════════════════════════════════════════════════════════

def _sb_client():
    """Return a Supabase client or None with a clear error message."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return None, "SUPABASE_URL or SUPABASE_SERVICE_KEY is not set in environment variables."
    try:
        from supabase import create_client
        return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY), None
    except Exception as e:
        return None, str(e)


def check_supabase_setup() -> dict:
    """
    Probe Supabase: is it reachable? Do the required tables exist?
    Returns a status dict so the admin can show useful diagnostics.
    """
    result = {
        "connected":         False,
        "visitor_sessions":  False,
        "subscribers":       False,
        "auth_ok":           False,
        "error":             None,
    }
    sb, err = _sb_client()
    if sb is None:
        result["error"] = err
        return result

    result["connected"] = True

    # Check visitor_sessions
    try:
        sb.table("visitor_sessions").select("visitor_id").limit(1).execute()
        result["visitor_sessions"] = True
    except Exception as e:
        result["visitor_sessions"] = False

    # Check subscribers
    try:
        sb.table("subscribers").select("id").limit(1).execute()
        result["subscribers"] = True
    except Exception as e:
        result["subscribers"] = False

    # Check auth admin access
    try:
        sb.auth.admin.list_users()
        result["auth_ok"] = True
    except Exception as e:
        result["auth_ok"] = False

    return result


def get_auth_users() -> dict:
    """
    Load ALL registered users from Supabase Auth (auth.users).
    This is the table that holds free signups, not just paid subscribers.
    Requires SUPABASE_SERVICE_KEY (service role — not the anon key).
    """
    sb, err = _sb_client()
    if sb is None:
        return {"rows": [], "error": err}
    try:
        # list_users() returns a list of GoTrueUser objects
        response = sb.auth.admin.list_users()
        rows = []
        for u in (response or []):
            def _g(attr, default=""):
                """Safe attribute getter for GoTrueUser."""
                v = getattr(u, attr, None)
                if v is None and isinstance(u, dict):
                    v = u.get(attr)
                return str(v)[:19].replace("T", " ") if v else default

            email    = getattr(u, "email", None) or (u.get("email") if isinstance(u, dict) else "N/A")
            uid      = getattr(u, "id",    None) or (u.get("id")    if isinstance(u, dict) else "")
            created  = _g("created_at",        "—")
            last_in  = _g("last_sign_in_at",   "—")
            conf_at  = getattr(u, "email_confirmed_at", None)
            confirmed = bool(conf_at)

            rows.append({
                "id":        str(uid)[:8] + "…" if uid else "—",
                "email":     email or "N/A",
                "created":   created,
                "last_in":   last_in,
                "confirmed": confirmed,
            })
        return {"rows": rows}
    except Exception as e:
        return {"rows": [], "error": str(e)}


def get_sub_data() -> dict:
    """Load paid subscribers from the subscribers table."""
    sb, err = _sb_client()
    if sb is None:
        return {"total": 0, "active": 0, "mrr": 0, "rows": [], "error": err}
    try:
        result = sb.table("subscribers").select("*").order("created_at", desc=True).execute()
        rows   = result.data or []
        active = sum(1 for r in rows if r.get("status") == "active")
        return {"total": len(rows), "active": active, "mrr": active * 29999, "rows": rows}
    except Exception as e:
        return {"total": 0, "active": 0, "mrr": 0, "rows": [], "error": str(e)}


# ── Load all data ─────────────────────────────────────────────
setup     = check_supabase_setup()
stats     = get_all_stats()
sub_data  = get_sub_data()
auth_data = get_auth_users()


# ════════════════════════════════════════════════════════════════
# SUPABASE SETUP STATUS
# (shown at top so you immediately see what's broken)
# ════════════════════════════════════════════════════════════════
st.markdown('<div class="sec-label">Supabase Connection Status</div>', unsafe_allow_html=True)

if not setup["connected"]:
    st.error(f"⚠️ Supabase not connected: {setup['error']}")
    st.info("Add SUPABASE_URL and SUPABASE_SERVICE_KEY to your Streamlit Cloud secrets or .env file.")
else:
    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        st.markdown(
            '<span class="setup-ok">✔ Supabase connected</span>'
            if setup["connected"] else
            '<span class="setup-fail">✘ Supabase unreachable</span>',
            unsafe_allow_html=True,
        )
    with col_b:
        st.markdown(
            '<span class="setup-ok">✔ visitor_sessions table exists</span>'
            if setup["visitor_sessions"] else
            '<span class="setup-fail">✘ visitor_sessions table MISSING</span>',
            unsafe_allow_html=True,
        )
    with col_c:
        st.markdown(
            '<span class="setup-ok">✔ subscribers table exists</span>'
            if setup["subscribers"] else
            '<span class="setup-fail">✘ subscribers table MISSING</span>',
            unsafe_allow_html=True,
        )
    with col_d:
        st.markdown(
            '<span class="setup-ok">✔ Auth admin API accessible</span>'
            if setup["auth_ok"] else
            '<span class="setup-fail">✘ Auth admin API blocked (check service key)</span>',
            unsafe_allow_html=True,
        )

    # Show SQL if visitor_sessions is missing
    if not setup["visitor_sessions"]:
        st.warning(
            "**visitor_sessions table not found.** "
            "limiter.py silently drops all visitor data without it. "
            "Run this SQL once in your Supabase project → SQL Editor:"
        )
        st.code("""
-- Run in Supabase SQL Editor (Database → SQL Editor → New Query)
CREATE TABLE IF NOT EXISTS visitor_sessions (
    visitor_id TEXT        PRIMARY KEY,
    count      INTEGER     NOT NULL DEFAULT 0,
    first_seen TIMESTAMPTZ,
    last_seen  TIMESTAMPTZ
);

-- Optional: auto-expire rows older than 30 days (keeps table clean)
-- You can set this up via pg_cron or a scheduled function later.
        """.strip(), language="sql")

    if not setup["subscribers"]:
        st.warning(
            "**subscribers table not found.** "
            "Paystack webhooks cannot record paid users. "
            "Run this SQL:"
        )
        st.code("""
CREATE TABLE IF NOT EXISTS subscribers (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID        REFERENCES auth.users(id),
    email      TEXT        NOT NULL,
    status     TEXT        NOT NULL DEFAULT 'inactive',
    plan_code  TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
        """.strip(), language="sql")


# ════════════════════════════════════════════════════════════════
# REVENUE METRICS
# ════════════════════════════════════════════════════════════════
st.markdown('<div class="sec-label">Revenue & Paid Subscribers</div>', unsafe_allow_html=True)
c1, c2, c3 = st.columns(3)
with c1:
    st.markdown(f'<div class="mcard green"><div class="mnum">{sub_data["active"]}</div><div class="mlabel">Active Subscribers</div></div>', unsafe_allow_html=True)
with c2:
    st.markdown(f'<div class="mcard green"><div class="mnum">₦{sub_data["mrr"]:,}</div><div class="mlabel">Monthly Revenue (MRR)</div></div>', unsafe_allow_html=True)
with c3:
    st.markdown(f'<div class="mcard"><div class="mnum">{sub_data["total"]}</div><div class="mlabel">Total Paid Signups</div></div>', unsafe_allow_html=True)

if sub_data.get("error"):
    st.caption(f"subscribers table error: {sub_data['error']}")


# ════════════════════════════════════════════════════════════════
# FUNNEL METRICS
# ════════════════════════════════════════════════════════════════
st.markdown('<div class="sec-label">Usage & Conversion Funnel</div>', unsafe_allow_html=True)
c4, c5, c6, c7 = st.columns(4)
with c4:
    st.markdown(f'<div class="mcard"><div class="mnum">{stats["total_visitors"]}</div><div class="mlabel">Total Visitors</div></div>', unsafe_allow_html=True)
with c5:
    st.markdown(f'<div class="mcard"><div class="mnum">{stats["total_questions"]}</div><div class="mlabel">Questions Asked</div></div>', unsafe_allow_html=True)
with c6:
    st.markdown(f'<div class="mcard"><div class="mnum">{stats["hit_paywall"]}</div><div class="mlabel">Hit Paywall</div></div>', unsafe_allow_html=True)
with c7:
    conversion_rate = (
        f'{round((stats["hit_paywall"] / stats["total_visitors"]) * 100)}%'
        if stats["total_visitors"] > 0 else "0%"
    )
    st.markdown(f'<div class="mcard"><div class="mnum">{conversion_rate}</div><div class="mlabel">Paywall Rate</div></div>', unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════
# ALL REGISTERED USERS (auth.users)
# THIS is where the two accounts you know about will appear.
# ════════════════════════════════════════════════════════════════
st.markdown('<div class="sec-label">All Registered Accounts (auth.users)</div>', unsafe_allow_html=True)

if auth_data.get("error"):
    st.warning(f"Could not load auth users: {auth_data['error']}")
    st.caption("Make sure SUPABASE_SERVICE_KEY is the service role key (not the anon key).")
elif not auth_data["rows"]:
    st.markdown(
        "<span style='font-size:0.8rem;color:rgba(250,250,247,0.28);'>"
        "No registered accounts found.</span>",
        unsafe_allow_html=True,
    )
else:
    # Header row
    h1, h2, h3, h4, h5 = st.columns([3, 2, 2, 1, 1])
    for col, label in zip(
        [h1, h2, h3, h4, h5],
        ["Email", "Registered", "Last Sign-in", "Verified", "Plan"],
    ):
        col.markdown(
            f'<span style="font-size:0.6rem;letter-spacing:0.15em;'
            f'text-transform:uppercase;color:rgba(201,168,76,0.45);">{label}</span>',
            unsafe_allow_html=True,
        )
    st.markdown(
        '<hr style="border-color:rgba(201,168,76,0.1);margin:4px 0 8px;">',
        unsafe_allow_html=True,
    )

    # Build a set of paid subscriber emails for fast lookup
    paid_emails = {
        r.get("email", "").lower()
        for r in (sub_data.get("rows") or [])
        if r.get("status") == "active"
    }

    for row in auth_data["rows"]:
        email   = row["email"]
        is_paid = email.lower() in paid_emails
        plan    = "PRO ✦" if is_paid else "Free"
        plan_color = "#C9A84C" if is_paid else "rgba(250,250,247,0.3)"
        verified_icon = "✔" if row["confirmed"] else "✘"
        verified_color = "#2ECC71" if row["confirmed"] else "#E74C3C"

        c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 1, 1])
        with c1:
            st.markdown(
                f'<span class="sub-email">{email}</span>',
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                f'<span style="font-size:0.7rem;color:rgba(250,250,247,0.4);">'
                f'{row["created"]}</span>',
                unsafe_allow_html=True,
            )
        with c3:
            st.markdown(
                f'<span style="font-size:0.7rem;color:rgba(250,250,247,0.4);">'
                f'{row["last_in"]}</span>',
                unsafe_allow_html=True,
            )
        with c4:
            st.markdown(
                f'<span style="color:{verified_color};font-size:0.8rem;">'
                f'{verified_icon}</span>',
                unsafe_allow_html=True,
            )
        with c5:
            st.markdown(
                f'<span style="color:{plan_color};font-size:0.68rem;">{plan}</span>',
                unsafe_allow_html=True,
            )

    st.markdown(
        f'<span style="font-size:0.65rem;color:rgba(250,250,247,0.25);">'
        f'{len(auth_data["rows"])} account(s) total</span>',
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════════════
# PAID SUBSCRIBER LIST (subscribers table)
# ════════════════════════════════════════════════════════════════
st.markdown('<div class="sec-label">Paid Subscriber Records (subscribers table)</div>', unsafe_allow_html=True)

if not sub_data["rows"]:
    st.markdown(
        "<span style='font-size:0.8rem;color:rgba(250,250,247,0.28);'>"
        "No paid subscribers yet — free accounts appear in Registered Accounts above.</span>",
        unsafe_allow_html=True,
    )
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


# ════════════════════════════════════════════════════════════════
# FREE VISITOR LOG (visitor_sessions table)
# ════════════════════════════════════════════════════════════════
st.markdown('<div class="sec-label">Free Visitor Log (visitor_sessions table)</div>', unsafe_allow_html=True)

raw = stats.get("visitors", {})
if not raw:
    if not setup["visitor_sessions"]:
        st.markdown(
            "<span style='font-size:0.8rem;color:rgba(250,250,247,0.28);'>"
            "visitor_sessions table missing — see setup SQL above to create it.</span>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<span style='font-size:0.8rem;color:rgba(250,250,247,0.28);'>"
            "No visitor sessions yet. Data appears here after users interact with the app.</span>",
            unsafe_allow_html=True,
        )
else:
    for vid, record in sorted(
        raw.items(),
        key=lambda x: x[1].get("last_seen", ""),
        reverse=True,
    ):
        count = record.get("count", 0)
        ls    = record.get("last_seen", "")
        hit   = count >= FREE_LIMIT

        # datetime formatting — INSIDE the loop (indentation fix from prev patch)
        try:
            from datetime import datetime as _dt
            tstr = _dt.fromisoformat(ls).strftime("%Y-%m-%d %H:%M") if ls else "N/A"
        except Exception:
            tstr = str(ls)[:16] if ls else "N/A"

        status   = "🔴 Hit Paywall" if hit else f"🟡 {count}/{FREE_LIMIT} used"
        short_id = vid[:18] + "…"

        ca, cb, cc, cd = st.columns([3, 2, 2, 1])
        with ca:
            st.markdown(
                f'<span style="font-size:0.68rem;color:rgba(250,250,247,0.3);'
                f'font-family:monospace;">{short_id}</span>',
                unsafe_allow_html=True,
            )
        with cb:
            st.markdown(
                f'<span style="font-size:0.7rem;color:rgba(250,250,247,0.4);">{tstr}</span>',
                unsafe_allow_html=True,
            )
        with cc:
            st.markdown(
                f'<span style="font-size:0.72rem;">{status}</span>',
                unsafe_allow_html=True,
            )
        with cd:
            if st.button("Reset", key=f"r_{vid}"):
                reset_ip(vid)
                st.rerun()


# ════════════════════════════════════════════════════════════════
# CONTROLS
# ════════════════════════════════════════════════════════════════
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
<div style="text-align:center;padding:2rem 0 0.5rem;border-top:1px solid rgba(201,168,76,0.07);margin-top:2rem;">
    <span style="font-size:0.55rem;letter-spacing:0.25em;text-transform:uppercase;color:rgba(201,168,76,0.2);">
        CONSULTAMHANi Admin · AMHANi Enterprise · Internal Use Only
    </span>
</div>
""", unsafe_allow_html=True)
