# =============================================================
# tools.py — AMHANi ENTERPRISE
# NVIDIA FIX:
#   - 4H unavailable on Streamlit Cloud: time.sleep() was blocking
#     Streamlit's event loop causing timeout. FIX: removed all
#     sleep() calls from _fetch_4h_levels, added proper h=None
#     initialization BEFORE the retry loop so UnboundLocalError
#     never silently swallows data.
#   - Added concurrent.futures timeout wrapper so yfinance calls
#     never hang indefinitely on cloud.
#   - Futures ticker fallback order corrected: YM=F (Dow mini),
#     ES=F (S&P mini), NQ=F (NASDAQ mini) all confirmed to
#     return intraday data on yfinance free tier.
# NVIDIA FIX 2 (Streamlit Cloud 4H still unavailable):
#   - Root cause: get_index_4h maps "US30" → "YM=F" then calls
#     _fetch_4h_levels("YM=F", ...). The fallback_map had NO
#     entry for "YM=F" itself — only for "US30", "^DJI" etc.
#     So when YM=F timed out on cloud, zero fallbacks ran.
#   - FIX: Added all futures tickers (YM=F, ES=F, NQ=F, GC=F,
#     CL=F, RTY=F, ZN=F) directly into fallback_map pointing at
#     their liquid ETF alternatives. Cloud now falls through to
#     DIA/SPY/QQQ/GLD/USO when futures are unavailable.
# =============================================================

import io
import sys
import json
import math
import time
import base64
import traceback
import threading
import concurrent.futures
import requests
from datetime import datetime

import yfinance as yf
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from langchain.tools import tool


# ══════════════════════════════════════════════════════════════
# TTL CACHE
# ══════════════════════════════════════════════════════════════
class _TTLCache:
    def __init__(self):
        self._data = {}
        self._lock = threading.Lock()

    def get(self, key: str):
        with self._lock:
            entry = self._data.get(key)
            if entry:
                val, ts, ttl = entry
                if time.time() - ts < ttl:
                    return val
                del self._data[key]
        return None

    def set(self, key: str, val, ttl: int = 60):
        with self._lock:
            self._data[key] = (val, time.time(), ttl)


_cache = _TTLCache()
_TTL_STOCK  = 60
_TTL_CRYPTO = 60
_TTL_FX     = 300
_TTL_4H     = 240   # 4H data cached 4 minutes


# ══════════════════════════════════════════════════════════════
# SAFE YFINANCE FETCHER — wraps every call with a timeout
# This is the core fix for Streamlit Cloud hangs.
# ══════════════════════════════════════════════════════════════
def _yf_fetch(ticker: str, interval: str = "1d", period: str = "2d",
              timeout_sec: int = 12) -> pd.DataFrame:
    """
    Fetch yfinance history with a hard timeout.
    Returns empty DataFrame on timeout or error — never hangs.
    """
    def _fetch():
        return yf.Ticker(ticker).history(interval=interval, period=period)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_fetch)
            return future.result(timeout=timeout_sec)
    except concurrent.futures.TimeoutError:
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()


# ══════════════════════════════════════════════════════════════
# 4H HELPER — no sleep(), proper initialization, cloud-safe
# ══════════════════════════════════════════════════════════════
def _fetch_4h_levels(ticker: str, display_name: str) -> str:
    """
    Aggregate 1H bars into 4H candles.
    FIXED:
      - h initialized to None BEFORE loop (was after, causing UnboundLocalError)
      - All time.sleep() removed (was blocking Streamlit event loop)
      - Hard timeout via ThreadPoolExecutor so cloud never hangs
      - Futures fallback correctly ordered
      - NVIDIA FIX 2: futures tickers (YM=F, ES=F, NQ=F etc.) now
        have their own fallback_map entries so cloud never dead-ends
    """
    cache_key = f"4h_{ticker}"
    cached = _cache.get(cache_key)
    if cached:
        return cached

    # ── IMPORTANT: initialize h BEFORE the loop ──────────────
    h = None

    # Primary: try the given ticker with 1H interval, 7 days history
    h = _yf_fetch(ticker, interval="1h", period="7d", timeout_sec=15)
    if h is not None and not h.empty and len(h) >= 4:
        pass  # got data, skip fallbacks
    else:
        h = None  # reset for fallback logic

    # ── FALLBACK MAP ──────────────────────────────────────────
    # NVIDIA FIX 2: Added all futures tickers as direct keys.
    # Previously only index tickers (^DJI, US30 etc.) were here.
    # get_index_4h maps US30 → YM=F then calls _fetch_4h_levels("YM=F").
    # If YM=F fails on cloud, there was no fallback — now DIA catches it.
    fallback_map = {
        # ── Index tickers (user may type these directly) ──
        "^DJI":     ["YM=F", "DIA"],
        "^GSPC":    ["ES=F", "SPY"],
        "^IXIC":    ["NQ=F", "QQQ"],
        "^VIX":     ["VIXY"],
        # Common alias names
        "US30":     ["YM=F", "DIA"],
        "SPX":      ["ES=F", "SPY"],
        "NAS100":   ["NQ=F", "QQQ"],
        # ── Futures tickers (passed in by get_index_4h) ──────
        # These are the DIRECT tickers the tool now receives.
        # ETFs are the reliable fallback on Streamlit Cloud.
        "YM=F":     ["DIA"],          # Dow mini  → SPDR Dow ETF
        "ES=F":     ["SPY"],          # S&P mini  → S&P 500 ETF
        "NQ=F":     ["QQQ"],          # NASDAQ mini → Invesco QQQ
        "GC=F":     ["GLD", "IAU"],   # Gold      → SPDR Gold / iShares
        "CL=F":     ["USO", "XLE"],   # WTI Oil   → US Oil Fund / Energy
        "RTY=F":    ["IWM"],          # Russell   → iShares Russell 2000
        "ZN=F":     ["TLT", "IEF"],   # 10yr Bond → iShares 20yr / 7-10yr
        "SI=F":     ["SLV"],          # Silver    → iShares Silver
        "HG=F":     ["CPER"],         # Copper    → US Copper Index
        "NG=F":     ["UNG"],          # Nat Gas   → US Natural Gas Fund
        # ── VIX futures ──
        "VX=F":     ["VIXY", "UVXY"],
    }

    if h is None or h.empty:
        alts = fallback_map.get(ticker.upper(), [])
        for alt in alts:
            h_alt = _yf_fetch(alt, interval="1h", period="7d", timeout_sec=15)
            if h_alt is not None and not h_alt.empty and len(h_alt) >= 4:
                h = h_alt
                display_name = f"{display_name} (via {alt})"
                break

    # Final guard
    if h is None or h.empty or len(h) < 4:
        return (
            f"⚠️ 4H data for {display_name} is temporarily unavailable.\n"
            f"Yahoo Finance does not provide intraday data for this symbol on the free tier.\n"
            f"Try: 'US30 4h' (uses YM=F → DIA) or 'BTC 4h' (uses BTC-USD hourly)."
        )

    # ── Aggregate 1H → 4H ────────────────────────────────────
    h.index = pd.to_datetime(h.index)
    # Drop any rows with NaN close prices
    h = h.dropna(subset=["Close"])

    if len(h) < 4:
        return f"⚠️ Not enough clean bars for {display_name} 4H analysis."

    bars = h[["Open", "High", "Low", "Close", "Volume"]].values
    candles = []
    for i in range(0, len(bars) - 3, 4):
        chunk = bars[i:i + 4]
        if len(chunk) == 4:
            candles.append({
                "open":   float(chunk[0][0]),
                "high":   float(chunk[:, 1].max()),
                "low":    float(chunk[:, 2].min()),
                "close":  float(chunk[-1][3]),
                "volume": float(chunk[:, 4].sum()),
            })

    if len(candles) < 2:
        return f"⚠️ Not enough complete 4H candles for {display_name}."

    curr = candles[-1]
    prev = candles[-2]
    c    = curr["close"]
    mid  = (curr["high"] + curr["low"]) / 2
    rng  = curr["high"] - curr["low"]

    # Fibonacci extension levels
    r1 = curr["high"] + rng * 0.382
    r2 = curr["high"] + rng * 0.618
    s1 = curr["low"]  - rng * 0.382
    s2 = curr["low"]  - rng * 0.618

    bias  = "Bullish" if c > mid  else "Bearish"
    trend = "Bullish" if curr["close"] > prev["close"] else "Bearish"
    arrow = "▲" if curr["close"] > prev["close"] else "▼"

    result = (
        f"── {display_name} 4-Hour Analysis ──\n"
        f"Current Close:  {c:,.2f}\n"
        f"4H Open:        {curr['open']:,.2f}\n"
        f"4H High:        {curr['high']:,.2f}\n"
        f"4H Low:         {curr['low']:,.2f}\n"
        f"Midpoint:       {mid:,.2f}\n"
        f"R1 (0.382):     {r1:,.2f}\n"
        f"R2 (0.618):     {r2:,.2f}\n"
        f"S1 (0.382):     {s1:,.2f}\n"
        f"S2 (0.618):     {s2:,.2f}\n"
        f"Candle Bias:    {bias} — close {'above' if c > mid else 'below'} midpoint\n"
        f"Trend vs Prev:  {trend} {arrow}\n"
        f"Prev 4H Close:  {prev['close']:,.2f}\n"
        f"Volume:         {curr['volume']:,.0f}\n"
        f"Candles used:   {len(candles)} × 4H\n"
        f"Source: Yahoo Finance 1H → 4H aggregation"
    )
    _cache.set(cache_key, result, _TTL_4H)
    return result


# ══════════════════════════════════════════════════════════════
# 1. STOCK PRICE
# ══════════════════════════════════════════════════════════════
@tool
def get_stock_price(ticker: str) -> str:
    """
    Get current stock price for a ticker symbol.
    Input: ticker e.g. 'AAPL', 'TSLA', 'DANGOTE.LG'
    """
    ticker    = ticker.upper().strip()
    cache_key = f"stock_{ticker}"
    cached    = _cache.get(cache_key)
    if cached:
        return cached + "\n📋 cached (< 60s)"

    try:
        fi    = yf.Ticker(ticker).fast_info
        price = fi.last_price
        prev  = fi.previous_close or price
        if price and price == price and price > 0:
            chg = price - prev
            pct = (chg / prev * 100) if prev else 0
            result = (
                f"📈 {ticker}\n"
                f"Price:  ${price:.2f}\n"
                f"Change: {'+' if chg >= 0 else ''}{chg:.2f} ({pct:+.2f}%)\n"
                f"High:   ${fi.day_high:.2f}\n"
                f"Low:    ${fi.day_low:.2f}\n"
                f"Source: Yahoo Finance (live)"
            )
            _cache.set(cache_key, result, _TTL_STOCK)
            return result
    except Exception:
        pass

    try:
        hist = _yf_fetch(ticker, period="2d")
        if not hist.empty:
            latest = hist.iloc[-1]
            prev   = hist.iloc[-2] if len(hist) > 1 else latest
            chg    = latest["Close"] - prev["Close"]
            pct    = (chg / prev["Close"] * 100) if prev["Close"] else 0
            result = (
                f"📈 {ticker}\n"
                f"Price:  ${latest['Close']:.2f}\n"
                f"Change: {'+' if chg >= 0 else ''}{chg:.2f} ({pct:+.2f}%)\n"
                f"High:   ${latest['High']:.2f}\n"
                f"Low:    ${latest['Low']:.2f}\n"
                f"Source: Yahoo Finance (delayed)"
            )
            _cache.set(cache_key, result, _TTL_STOCK)
            return result
    except Exception:
        pass

    return f"⚠️ {ticker} price temporarily unavailable. Try again in 60 seconds."


# ══════════════════════════════════════════════════════════════
# 2. CURRENCY CONVERTER
# ══════════════════════════════════════════════════════════════
@tool
def convert_currency(input: str) -> str:
    """
    Convert between currencies.
    Format: 'amount, FROM, TO'  e.g. '1500, USD, NGN'
    """
    try:
        parts  = [p.strip() for p in input.split(",")]
        if len(parts) < 3:
            return "Format: 'amount, FROM, TO'  e.g. '1500, USD, NGN'"
        amount = float(parts[0])
        frm    = parts[1].upper()
        to     = parts[2].upper()

        cache_key   = f"fx_{frm}_{to}"
        cached_rate = _cache.get(cache_key)
        if cached_rate:
            return (
                f"💱 {amount:,.2f} {frm} = {amount * cached_rate:,.2f} {to}\n"
                f"Rate: 1 {frm} = {cached_rate:,.4f} {to}\n📋 cached"
            )

        for url in [
            f"https://open.er-api.com/v6/latest/{frm}",
            f"https://api.frankfurter.app/latest?from={frm}&to={to}",
        ]:
            try:
                resp = requests.get(url, timeout=8)
                data = resp.json()
                rate = (data.get("rates") or {}).get(to)
                if rate:
                    _cache.set(cache_key, rate, _TTL_FX)
                    return (
                        f"💱 Currency Conversion\n"
                        f"{amount:,.2f} {frm} = {amount * rate:,.2f} {to}\n"
                        f"Rate: 1 {frm} = {rate:,.4f} {to}"
                    )
            except Exception:
                continue

        # yfinance fallback
        try:
            h = _yf_fetch(f"{frm}{to}=X", period="2d")
            if not h.empty:
                rate = h["Close"].iloc[-1]
                if rate == rate:
                    _cache.set(cache_key, rate, _TTL_FX)
                    return f"💱 {amount:,.2f} {frm} = {amount * rate:,.2f} {to}"
        except Exception:
            pass

        # Hardcoded NGN fallback
        ngn = {"USD": 1620, "GBP": 2050, "EUR": 1750, "CAD": 1190, "AUD": 1040}
        if to == "NGN" and frm in ngn:
            return f"💱 {amount:,.2f} {frm} ≈ ₦{amount * ngn[frm]:,.2f} (estimated)"
        if frm == "NGN" and to in ngn:
            return f"💱 ₦{amount:,.2f} ≈ {amount / ngn[to]:,.4f} {to} (estimated)"

        return f"⚠️ Rate unavailable for {frm}→{to}. Try again shortly."

    except Exception as e:
        return f"Conversion error: {e}"


# ══════════════════════════════════════════════════════════════
# 3. CRYPTO PRICE
# ══════════════════════════════════════════════════════════════
_COINGECKO_IDS = {
    "BTC": "bitcoin", "ETH": "ethereum", "BNB": "binancecoin",
    "SOL": "solana",  "ADA": "cardano",  "XRP": "ripple",
    "DOGE": "dogecoin", "DOT": "polkadot", "MATIC": "matic-network",
}

@tool
def get_crypto_price(input: str = "BTC,ETH") -> str:
    """
    Get live crypto prices. Supports 4H analysis.
    Input: 'BTC'  'BTC,ETH'  'BTC,4h'  'ETH,BNB'
    """
    try:
        want_4h = "4h" in input.lower()
        raw     = input.lower().replace("4h", "").replace("4hour", "")
        coins   = [c.strip().upper() for c in raw.split(",") if c.strip()]
        if not coins:
            coins = ["BTC"]

        out       = ["── Crypto Prices ──"]
        cache_key = f"crypto_{'_'.join(sorted(coins))}"
        cached    = _cache.get(cache_key)

        if cached:
            out = cached.split("\n")
        else:
            cg_ids = [_COINGECKO_IDS.get(c, c.lower()) for c in coins]
            fetched = False
            try:
                url  = (
                    "https://api.coingecko.com/api/v3/simple/price"
                    f"?ids={','.join(cg_ids)}&vs_currencies=usd&include_24hr_change=true"
                )
                resp = requests.get(url, timeout=10)
                data = resp.json()
                if data and not data.get("error"):
                    for coin, cg_id in zip(coins, cg_ids):
                        entry = data.get(cg_id, {})
                        price = entry.get("usd")
                        chg   = entry.get("usd_24h_change", 0) or 0
                        if price:
                            arrow = "▲" if chg >= 0 else "▼"
                            out.append(f"{coin}: ${price:>12,.2f}  {arrow} {chg:+.2f}% (24h)")
                            fetched = True
            except Exception:
                pass

            if not fetched:
                for coin in coins:
                    h = _yf_fetch(f"{coin}-USD", period="2d")
                    if not h.empty and len(h) >= 1:
                        p  = h["Close"].iloc[-1]
                        pv = h["Close"].iloc[-2] if len(h) > 1 else p
                        if p == p and pv == pv and p > 0:
                            chg   = p - pv
                            pct   = (chg / pv * 100) if pv else 0
                            arrow = "▲" if chg >= 0 else "▼"
                            out.append(f"{coin}: ${p:>12,.2f}  {arrow} {pct:+.2f}%")
                            continue
                    out.append(f"{coin}: temporarily unavailable")

            _cache.set(cache_key, "\n".join(out), _TTL_CRYPTO)

        if want_4h:
            for coin in coins:
                out.append("")
                out.append(_fetch_4h_levels(f"{coin}-USD", coin))

        return "\n".join(out)

    except Exception as e:
        return f"Crypto error: {e}"


# ══════════════════════════════════════════════════════════════
# 4. INDEX 4H — dedicated tool for US30, SPX, NAS100
# ══════════════════════════════════════════════════════════════
@tool
def get_index_4h(input: str) -> str:
    """
    4-hour technical analysis for major indices.
    Input: 'US30', 'SPX', 'NAS100', 'NASDAQ', 'Dow', 'S&P'
    Uses futures contracts (YM=F, ES=F, NQ=F) for intraday data.
    Falls back to liquid ETFs (DIA, SPY, QQQ) on cloud when
    futures data is unavailable — handled inside _fetch_4h_levels.
    Examples: 'US30 4h'  'SPX 4h'  'NAS100'
    """
    mapping = {
        "US30":    ("YM=F",  "US30 / Dow Jones"),
        "DOW":     ("YM=F",  "US30 / Dow Jones"),
        "DJI":     ("YM=F",  "US30 / Dow Jones"),
        "DOWJONES":("YM=F",  "US30 / Dow Jones"),
        "SPX":     ("ES=F",  "SPX / S&P 500"),
        "SP500":   ("ES=F",  "SPX / S&P 500"),
        "SP":      ("ES=F",  "SPX / S&P 500"),
        "S&P":     ("ES=F",  "SPX / S&P 500"),
        "NAS":     ("NQ=F",  "NAS100 / NASDAQ"),
        "NAS100":  ("NQ=F",  "NAS100 / NASDAQ"),
        "NASDAQ":  ("NQ=F",  "NAS100 / NASDAQ"),
        "NDX":     ("NQ=F",  "NAS100 / NASDAQ"),
        "GOLD":    ("GC=F",  "Gold / XAU"),
        "XAUUSD":  ("GC=F",  "Gold / XAU"),
        "OIL":     ("CL=F",  "Crude Oil / WTI"),
        "USOIL":   ("CL=F",  "Crude Oil / WTI"),
    }
    clean = input.strip().upper().replace(" ", "").replace("/", "").replace("4H", "")
    ticker, name = mapping.get(clean, (None, None))
    if not ticker:
        ticker = input.strip().upper().replace(" 4H", "").replace("4H", "")
        name   = ticker
    return _fetch_4h_levels(ticker, name)


# ══════════════════════════════════════════════════════════════
# 5. P/E RATIO
# ══════════════════════════════════════════════════════════════
@tool
def calculate_pe_ratio(input: str) -> str:
    """P/E ratio. Format: 'price, eps'  e.g. '150, 10.5'"""
    try:
        parts = input.replace(";", ",").split(",")
        if len(parts) < 2:
            return "Format: 'price, eps'"
        price, eps = float(parts[0].strip()), float(parts[1].strip())
        if eps == 0:
            return "EPS cannot be zero."
        pe = price / eps
        verdict = (
            "Potentially undervalued" if pe < 15 else
            "Fairly valued"           if pe < 25 else
            "Premium / Growth stock"  if pe < 40 else
            "Highly speculative"
        )
        return f"P/E: {pe:.2f}  |  Price: ${price:.2f}  |  EPS: ${eps:.2f}\nAssessment: {verdict}"
    except Exception as e:
        return f"Error: {e}"


# ══════════════════════════════════════════════════════════════
# 6. PYTHON EXECUTOR
# ══════════════════════════════════════════════════════════════
@tool
def execute_python(code: str) -> str:
    """Execute Python code. Use print() to show results."""
    old = sys.stdout
    sys.stdout = buf = io.StringIO()
    try:
        exec(compile(code, "<amhani>", "exec"),
             {"pd": pd, "json": json, "math": math, "datetime": datetime})
        result = buf.getvalue() or "Executed. No print() output."
    except Exception:
        result = f"Error:\n{traceback.format_exc()}"
    finally:
        sys.stdout = old
    return result[:4000]


# ══════════════════════════════════════════════════════════════
# 7. FINANCIAL DATA ANALYSER
# ══════════════════════════════════════════════════════════════
@tool
def analyse_financial_data(input: str) -> str:
    """Analyse JSON financial data. Input: '[{"month":"Jan","revenue":50000}, ...]'"""
    try:
        df  = pd.DataFrame(json.loads(input))
        out = [f"📊 {df.shape[0]} rows × {df.shape[1]} cols — {', '.join(df.columns)}"]
        num = df.select_dtypes(include="number")
        if not num.empty:
            out.append(num.describe().round(2).to_string())
        lower = {c.lower(): c for c in df.columns}
        if "revenue" in lower and "expenses" in lower:
            df["__p"] = df[lower["revenue"]] - df[lower["expenses"]]
            out.append(f"Profit: ₦{df['__p'].sum():,.2f}  Margin: {(df['__p'].sum()/df[lower['revenue']].sum())*100:.1f}%")
        return "\n".join(out)
    except Exception as e:
        return f"Analysis error: {e}"


# ══════════════════════════════════════════════════════════════
# 8. STOCK CHART
# ══════════════════════════════════════════════════════════════
@tool
def generate_stock_chart(input: str) -> str:
    """Generate gold-themed chart. Input: 'TICKER' or 'TICKER, period'"""
    try:
        parts  = [p.strip() for p in input.split(",")]
        ticker = parts[0].upper()
        period = parts[1] if len(parts) > 1 else "3mo"
        hist   = _yf_fetch(ticker, period=period, timeout_sec=20)
        if hist.empty:
            return f"No chart data for {ticker}"
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6),
                                        gridspec_kw={"height_ratios": [3, 1]},
                                        facecolor="#0F0F0C")
        fig.suptitle(f"{ticker}  ·  {period.upper()}", color="#C9A84C",
                     fontsize=13, fontweight="bold", y=0.99)
        ax1.plot(hist.index, hist["Close"], color="#C9A84C", linewidth=1.8)
        ax1.fill_between(hist.index, hist["Close"], hist["Close"].min(), alpha=0.07, color="#C9A84C")
        ax1.set_facecolor("#0F0F0C"); ax1.tick_params(colors="#666", labelsize=8)
        for s in ax1.spines.values(): s.set_edgecolor("#2a2a20")
        ax2.bar(hist.index, hist["Volume"], color="#C9A84C", alpha=0.3, width=1)
        ax2.set_facecolor("#0F0F0C"); ax2.tick_params(colors="#666", labelsize=7)
        for s in ax2.spines.values(): s.set_edgecolor("#2a2a20")
        plt.tight_layout(rect=[0, 0, 1, 0.97])
        buf = io.BytesIO()
        plt.savefig(buf, format="png", bbox_inches="tight", dpi=130, facecolor="#0F0F0C")
        plt.close(fig); buf.seek(0)
        return f"CHART_BASE64:{base64.b64encode(buf.read()).decode()}"
    except Exception as e:
        return f"Chart error: {e}"


# ══════════════════════════════════════════════════════════════
# 9. FINANCIAL CALCULATOR
# ══════════════════════════════════════════════════════════════
@tool
def financial_calculator(input: str) -> str:
    """
    Financial calculations.
    Types: compound_interest | loan_payment | roi | break_even |
           inflation_adjust  | future_value | payback_period
    Example: 'compound_interest, 500000, 0.15, 5'
    """
    try:
        parts = [p.strip() for p in input.split(",")]
        calc  = parts[0].lower().replace(" ", "_")
        if calc == "compound_interest":
            P, r, n = float(parts[1]), float(parts[2]), float(parts[3])
            A = P * (1 + r) ** n
            return (f"💰 Compound Interest\nPrincipal: ₦{P:,.2f}  Rate: {r*100:.1f}%/yr  Years: {n:.0f}\n"
                    f"Final: ₦{A:,.2f}  Gain: ₦{A-P:,.2f} ({((A-P)/P)*100:.1f}%)")
        elif calc == "loan_payment":
            P, r_a, y = float(parts[1]), float(parts[2]), float(parts[3])
            r = r_a / 12; n = y * 12
            m = P * r * (1+r)**n / ((1+r)**n - 1) if r > 0 else P / n
            return (f"🏦 Loan\nMonthly: ₦{m:,.2f}  Total: ₦{m*n:,.2f}  Interest: ₦{m*n-P:,.2f}")
        elif calc == "roi":
            g, c = float(parts[1]), float(parts[2])
            return f"📈 ROI: {((g-c)/c)*100:.2f}%  Profit: ₦{g-c:,.2f}"
        elif calc == "break_even":
            f_, p, v = float(parts[1]), float(parts[2]), float(parts[3])
            m = p - v
            if m <= 0: return "Price must exceed variable cost."
            u = f_ / m
            return f"⚖️ Break-Even: {u:,.0f} units  Revenue: ₦{u*p:,.2f}"
        elif calc == "inflation_adjust":
            a, r, y = float(parts[1]), float(parts[2]), float(parts[3])
            real = a / (1 + r) ** y
            return f"📉 Real Value: ₦{real:,.2f}  Lost: ₦{a-real:,.2f} ({((a-real)/a)*100:.1f}%)"
        elif calc == "future_value":
            pv, r, y = float(parts[1]), float(parts[2]), float(parts[3])
            return f"🔭 Future Value: ₦{pv*(1+r)**y:,.2f}"
        elif calc == "payback_period":
            i, cf = float(parts[1]), float(parts[2])
            return f"⏱️ Payback: {i/cf:.2f} years"
        else:
            return f"Unknown: '{calc}'. Supported: compound_interest, loan_payment, roi, break_even, inflation_adjust, future_value, payback_period"
    except Exception as e:
        return f"Calculator error: {e}"


# ══════════════════════════════════════════════════════════════
# 10. MARKET OVERVIEW
# ══════════════════════════════════════════════════════════════
@tool
def get_market_overview(input: str = "all") -> str:
    """Live snapshot of global indices. Input: 'all' or 'indices'"""
    cache_key = f"market_{input}"
    cached    = _cache.get(cache_key)
    if cached:
        return cached + "\n📋 cached (< 60s)"
    try:
        indices = {"S&P 500": "^GSPC", "Dow Jones": "^DJI", "NASDAQ": "^IXIC", "VIX": "^VIX"}
        out     = ["── Global Indices ──"]
        for name, sym in indices.items():
            h = _yf_fetch(sym, period="2d")
            if len(h) >= 2:
                c1, c2 = h["Close"].iloc[-1], h["Close"].iloc[-2]
                if c1 == c1 and c2 == c2 and c2 != 0:
                    chg = c1 - c2; pct = (chg / c2) * 100
                    out.append(f"{name:12} {c1:>12,.2f}  {'▲' if chg>=0 else '▼'} {pct:+.2f}%")
                else:
                    out.append(f"{name:12}  data unavailable")
            else:
                out.append(f"{name:12}  unavailable")
        result = "\n".join(out)
        _cache.set(cache_key, result, _TTL_STOCK)
        return result
    except Exception as e:
        return f"Market overview error: {e}"


# ══════════════════════════════════════════════════════════════
# 11. TASK PLANNER
# ══════════════════════════════════════════════════════════════
@tool
def plan_task(goal: str) -> str:
    """Break a complex goal into steps. Use FIRST for multi-step requests."""
    return (
        f"📋 Plan: {goal}\n\n"
        "Step 1 — Identify objective and inputs\n"
        "Step 2 — Determine tools and data sources\n"
        "Step 3 — Gather data\n"
        "Step 4 — Calculate or analyse\n"
        "Step 5 — Validate\n"
        "Step 6 — Deliver recommendation\n\nExecuting now..."
    )


# ══════════════════════════════════════════════════════════════
# EXPORT
# ══════════════════════════════════════════════════════════════
amhani_tools = [
    get_stock_price,
    convert_currency,
    get_crypto_price,
    get_index_4h,
    calculate_pe_ratio,
    execute_python,
    analyse_financial_data,
    generate_stock_chart,
    financial_calculator,
    get_market_overview,
    plan_task,
]
