# =============================================================
# tools.py — AMHANi ENTERPRISE
# DIAGNOSIS FIX:
#   - Rate limiting: No cache existed — every call hit Yahoo cold.
#     FIX: Module-level TTL cache (60s stocks, 60s crypto, 300s FX).
#   - Crypto NaN: yfinance returns NaN for crypto fast_info on
#     Streamlit Cloud. FIX: CoinGecko free API as primary for crypto.
#   - Duplicate convert_currency: Second definition overwrote first.
#     FIX: Single definition using ExchangeRate-API as primary.
#   - time/requests imported inside functions: fragile.
#     FIX: All imports at top.
# =============================================================

import io
import sys
import json
import math
import time
import base64
import traceback
import threading
import requests
from datetime import datetime

import yfinance as yf
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from langchain.tools import tool


# ══════════════════════════════════════════════════════════════
# TTL CACHE — prevents rate limiting by reusing recent results
# ══════════════════════════════════════════════════════════════
class _TTLCache:
    """Thread-safe cache with per-entry TTL."""
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

# TTL constants (seconds)
_TTL_STOCK  = 60    # 1 minute
_TTL_CRYPTO = 60    # 1 minute
_TTL_FX     = 300   # 5 minutes


# ══════════════════════════════════════════════════════════════
# 1. STOCK PRICE
# ══════════════════════════════════════════════════════════════
@tool
def get_stock_price(ticker: str) -> str:
    """
    Get current stock price for a ticker symbol.
    Uses cache to prevent rate limiting. Falls back across methods.
    Input: ticker e.g. 'AAPL', 'TSLA', 'DANGOTE.LG'
    """
    ticker = ticker.upper().strip()
    cache_key = f"stock_{ticker}"

    # Return cached result if fresh
    cached = _cache.get(cache_key)
    if cached:
        return cached + "\n📋 Source: cached (< 60s old)"

    # Method 1 — yfinance fast_info
    try:
        fi    = yf.Ticker(ticker).fast_info
        price = fi.last_price
        prev  = fi.previous_close or price
        # NaN check: NaN != NaN in Python
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

    # Method 2 — yfinance history
    try:
        hist = yf.Ticker(ticker).history(period="2d")
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

    return (
        f"⚠️ {ticker} price temporarily unavailable — Yahoo Finance rate limit reached.\n"
        f"Please try again in 60 seconds or visit finance.yahoo.com/quote/{ticker}"
    )


# ══════════════════════════════════════════════════════════════
# 2. CURRENCY CONVERTER
# ══════════════════════════════════════════════════════════════
@tool
def convert_currency(input: str) -> str:
    """
    Convert between currencies using live exchange rates.
    Input format: 'amount, FROM, TO'
    Examples: '1500, USD, NGN'  or  '50000, NGN, USD'
    Supported: USD, NGN, GBP, EUR, JPY, CAD, AUD, CNY, ZAR, GHS, KES, and more.
    """
    try:
        parts  = [p.strip() for p in input.split(",")]
        if len(parts) < 3:
            return "Format: 'amount, FROM, TO'  e.g. '1500, USD, NGN'"
        amount = float(parts[0])
        frm    = parts[1].upper()
        to     = parts[2].upper()

        cache_key = f"fx_{frm}_{to}"
        cached_rate = _cache.get(cache_key)

        if cached_rate:
            converted = amount * cached_rate
            return (
                f"💱 Currency Conversion\n"
                f"{amount:,.2f} {frm} = {converted:,.2f} {to}\n"
                f"Rate: 1 {frm} = {cached_rate:,.4f} {to}\n"
                f"📋 Source: cached rate (< 5 min old)"
            )

        # Method 1 — ExchangeRate-API (free, no key, generous limits)
        try:
            url  = f"https://open.er-api.com/v6/latest/{frm}"
            resp = requests.get(url, timeout=8)
            data = resp.json()
            if data.get("result") == "success":
                rate = data["rates"].get(to)
                if rate:
                    _cache.set(cache_key, rate, _TTL_FX)
                    converted = amount * rate
                    return (
                        f"💱 Currency Conversion\n"
                        f"{amount:,.2f} {frm} = {converted:,.2f} {to}\n"
                        f"Rate: 1 {frm} = {rate:,.4f} {to}\n"
                        f"Source: ExchangeRate-API (live)"
                    )
        except Exception:
            pass

        # Method 2 — Frankfurter API (free European Central Bank data)
        try:
            url  = f"https://api.frankfurter.app/latest?from={frm}&to={to}"
            resp = requests.get(url, timeout=8)
            data = resp.json()
            rate = data.get("rates", {}).get(to)
            if rate:
                _cache.set(cache_key, rate, _TTL_FX)
                converted = amount * rate
                return (
                    f"💱 Currency Conversion\n"
                    f"{amount:,.2f} {frm} = {converted:,.2f} {to}\n"
                    f"Rate: 1 {frm} = {rate:,.4f} {to}\n"
                    f"Source: Frankfurter/ECB (live)"
                )
        except Exception:
            pass

        # Method 3 — yfinance forex fallback
        try:
            pair = f"{frm}{to}=X"
            hist = yf.Ticker(pair).history(period="2d")
            if not hist.empty:
                rate = hist["Close"].iloc[-1]
                if rate and rate == rate:  # NaN check
                    _cache.set(cache_key, rate, _TTL_FX)
                    converted = amount * rate
                    return (
                        f"💱 Currency Conversion\n"
                        f"{amount:,.2f} {frm} = {converted:,.2f} {to}\n"
                        f"Rate: 1 {frm} = {rate:,.4f} {to}\n"
                        f"Source: Yahoo Finance (delayed)"
                    )
        except Exception:
            pass

        # Method 4 — hardcoded NGN rates (last resort)
        ngn_rates = {
            "USD": 1620, "GBP": 2050, "EUR": 1750,
            "CAD": 1190, "AUD": 1040, "ZAR": 88,
        }
        if to == "NGN" and frm in ngn_rates:
            rate = ngn_rates[frm]
            return (
                f"💱 Currency Conversion (estimated)\n"
                f"{amount:,.2f} {frm} ≈ ₦{amount * rate:,.2f}\n"
                f"Rate used: ₦{rate:,.0f} per {frm}\n"
                f"⚠️ All live APIs unavailable — this is an approximate rate."
            )
        elif frm == "NGN" and to in ngn_rates:
            rate = ngn_rates[to]
            return (
                f"💱 Currency Conversion (estimated)\n"
                f"₦{amount:,.2f} ≈ {amount / rate:,.4f} {to}\n"
                f"Rate used: ₦{rate:,.0f} per {to}\n"
                f"⚠️ All live APIs unavailable — this is an approximate rate."
            )

        return (
            f"⚠️ Could not fetch {frm}→{to} rate from any available source.\n"
            f"All live data APIs are temporarily rate-limited. Try again in 5 minutes."
        )

    except IndexError:
        return "Format: 'amount, FROM, TO'  e.g. '1500, USD, NGN'"
    except Exception as e:
        return f"Conversion error: {e}"


# ══════════════════════════════════════════════════════════════
# 3. CRYPTO PRICE — CoinGecko as primary (much better free tier)
# ══════════════════════════════════════════════════════════════

# Map common symbols to CoinGecko IDs
_COINGECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "BNB": "binancecoin",
    "SOL": "solana",
    "ADA": "cardano",
    "XRP": "ripple",
    "DOGE": "dogecoin",
    "DOT": "polkadot",
    "MATIC": "matic-network",
    "LINK": "chainlink",
}

@tool
def get_crypto_price(input: str = "BTC,ETH") -> str:
    """
    Get live crypto prices using CoinGecko API (primary) with yfinance fallback.
    Input: comma-separated symbols e.g. 'BTC,ETH,BNB'
    For 4-hour BTC level analysis: 'BTC,4h'
    Examples: 'BTC'  'BTC,ETH'  'BTC,ETH,BNB'  'BTC,4h'
    """
    try:
        want_4h = "4h" in input.lower()
        raw     = input.lower().replace("4h", "").replace("4hour", "")
        coins   = [c.strip().upper() for c in raw.split(",") if c.strip()]
        if not coins:
            coins = ["BTC"]

        out = ["── Crypto Prices ──"]

        # Check cache first
        cache_key = f"crypto_{'_'.join(sorted(coins))}"
        cached = _cache.get(cache_key)
        if cached:
            out = cached.split("\n") if isinstance(cached, str) else [cached]
        else:
            # Method 1 — CoinGecko (no API key, generous rate limits)
            cg_ids = [_COINGECKO_IDS.get(c, c.lower()) for c in coins]
            fetched_from_cg = False
            try:
                url  = (
                    "https://api.coingecko.com/api/v3/simple/price"
                    f"?ids={','.join(cg_ids)}"
                    "&vs_currencies=usd"
                    "&include_24hr_change=true"
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
                            fetched_from_cg = True
                        else:
                            out.append(f"{coin}: not found in CoinGecko")
            except Exception:
                pass

            # Method 2 — yfinance fallback for any coin CoinGecko missed
            if not fetched_from_cg:
                for coin in coins:
                    sym = f"{coin}-USD"
                    price_line = None

                    # fast_info with NaN guard
                    try:
                        fi    = yf.Ticker(sym).fast_info
                        price = fi.last_price
                        prev  = fi.previous_close
                        if price and price == price and prev and prev == prev and price > 0:
                            chg   = price - prev
                            pct   = (chg / prev * 100) if prev else 0
                            arrow = "▲" if chg >= 0 else "▼"
                            price_line = f"{coin}: ${price:>12,.2f}  {arrow} {pct:+.2f}%"
                    except Exception:
                        pass

                    # history fallback
                    if not price_line:
                        try:
                            h = yf.Ticker(sym).history(period="2d")
                            if not h.empty and len(h) >= 1:
                                p  = h["Close"].iloc[-1]
                                pv = h["Close"].iloc[-2] if len(h) > 1 else p
                                if p == p and pv == pv and p > 0:
                                    chg   = p - pv
                                    pct   = (chg / pv * 100) if pv else 0
                                    arrow = "▲" if chg >= 0 else "▼"
                                    price_line = f"{coin}: ${p:>12,.2f}  {arrow} {pct:+.2f}%"
                        except Exception:
                            pass

                    out.append(price_line or f"{coin}: temporarily unavailable")

            # Cache the price lines
            _cache.set(cache_key, "\n".join(out), _TTL_CRYPTO)

        # 4-hour BTC analysis (always fresh — not cached)
        if want_4h and "BTC" in coins:
            try:
                hist = yf.Ticker("BTC-USD").history(interval="1h", period="2d")
                if not hist.empty and len(hist) >= 4:
                    recent = hist.tail(4)
                    high4h = recent["High"].max()
                    low4h  = recent["Low"].min()
                    close  = recent["Close"].iloc[-1]
                    mid    = (high4h + low4h) / 2
                    bias   = "Bullish" if close > mid else "Bearish"
                    side   = "above" if close > mid else "below"
                    r1     = high4h + (high4h - low4h) * 0.382
                    s1     = low4h  - (high4h - low4h) * 0.382
                    out.append(f"\n── BTC 4-Hour Levels ──")
                    out.append(f"Current:    ${close:,.2f}")
                    out.append(f"4H High:    ${high4h:,.2f}")
                    out.append(f"4H Low:     ${low4h:,.2f}")
                    out.append(f"Midpoint:   ${mid:,.2f}")
                    out.append(f"R1 (est):   ${r1:,.2f}")
                    out.append(f"S1 (est):   ${s1:,.2f}")
                    out.append(f"Bias:       {bias} — price {side} midpoint")
            except Exception:
                out.append("\n⚠️ 4H level data temporarily unavailable")

        return "\n".join(out)

    except Exception as e:
        return f"Crypto data error: {e}"


# ══════════════════════════════════════════════════════════════
# 4. P/E RATIO
# ══════════════════════════════════════════════════════════════
@tool
def calculate_pe_ratio(input: str) -> str:
    """
    Calculate the Price-to-Earnings (P/E) ratio.
    Input format: 'price, eps'  e.g. '150, 10.5'
    """
    try:
        parts = input.replace(";", ",").split(",")
        if len(parts) < 2:
            return "Format: 'price, eps'  e.g. '150, 10.5'"
        price = float(parts[0].strip())
        eps   = float(parts[1].strip())
        if eps == 0:
            return "EPS cannot be zero — P/E ratio undefined."
        pe = price / eps
        verdict = (
            "Potentially undervalued"  if pe < 15 else
            "Fairly valued"            if pe < 25 else
            "Premium / Growth stock"   if pe < 40 else
            "Highly speculative"
        )
        return (
            f"P/E Ratio:   {pe:.2f}\n"
            f"Price:       ${price:.2f}\n"
            f"EPS:         ${eps:.2f}\n"
            f"Assessment:  {verdict}"
        )
    except Exception as e:
        return f"Error: {e}. Format: 'price, eps'"


# ══════════════════════════════════════════════════════════════
# 5. PYTHON CODE EXECUTOR
# ══════════════════════════════════════════════════════════════
@tool
def execute_python(code: str) -> str:
    """
    Write AND execute Python code to solve financial problems.
    Available: pandas (pd), json, math, datetime.
    Always use print() — output is captured and returned.
    """
    old_stdout = sys.stdout
    sys.stdout = buffer = io.StringIO()
    try:
        namespace = {"pd": pd, "json": json, "math": math, "datetime": datetime}
        exec(compile(code, "<amhani>", "exec"), namespace)
        result = buffer.getvalue() or "Executed. No print() output."
    except Exception:
        result = f"Error:\n{traceback.format_exc()}"
    finally:
        sys.stdout = old_stdout
    return result[:4000]


# ══════════════════════════════════════════════════════════════
# 6. FINANCIAL DATA ANALYSER
# ══════════════════════════════════════════════════════════════
@tool
def analyse_financial_data(input: str) -> str:
    """
    Analyse financial data as a JSON string.
    Input: '[{"month":"Jan","revenue":50000,"expenses":30000}, ...]'
    Returns: summary stats, growth, profit analysis.
    """
    try:
        df  = pd.DataFrame(json.loads(input))
        out = [f"📊 {df.shape[0]} rows × {df.shape[1]} cols — {', '.join(df.columns)}"]
        num = df.select_dtypes(include="number")
        if not num.empty:
            out.append(num.describe().round(2).to_string())
            for col in num.columns:
                if len(df) > 1 and df[col].iloc[0] != 0:
                    g = ((df[col].iloc[-1] - df[col].iloc[0]) / abs(df[col].iloc[0])) * 100
                    out.append(f"{col}: {g:+.1f}%")
        lower = {c.lower(): c for c in df.columns}
        if "revenue" in lower and "expenses" in lower:
            df["__p"] = df[lower["revenue"]] - df[lower["expenses"]]
            total  = df["__p"].sum()
            margin = (total / df[lower["revenue"]].sum()) * 100
            out.append(f"Profit: ₦{total:,.2f}  Margin: {margin:.1f}%")
        return "\n".join(out)
    except Exception as e:
        return f"Analysis error: {e}"


# ══════════════════════════════════════════════════════════════
# 7. STOCK CHART
# ══════════════════════════════════════════════════════════════
@tool
def generate_stock_chart(input: str) -> str:
    """
    Generate a gold-themed stock chart.
    Input: 'TICKER' or 'TICKER, period'  (periods: 1mo 3mo 6mo 1y 2y)
    Example: 'AAPL, 6mo'
    """
    try:
        parts  = [p.strip() for p in input.split(",")]
        ticker = parts[0].upper()
        period = parts[1] if len(parts) > 1 else "3mo"
        hist   = yf.Ticker(ticker).history(period=period)
        if hist.empty:
            return f"No chart data for {ticker}"

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6),
                                        gridspec_kw={"height_ratios": [3, 1]},
                                        facecolor="#0F0F0C")
        fig.suptitle(f"{ticker}  ·  {period.upper()}", color="#C9A84C",
                     fontsize=13, fontweight="bold", y=0.99)
        ax1.plot(hist.index, hist["Close"], color="#C9A84C", linewidth=1.8)
        ax1.fill_between(hist.index, hist["Close"], hist["Close"].min(),
                         alpha=0.07, color="#C9A84C")
        ax1.set_facecolor("#0F0F0C")
        ax1.tick_params(colors="#666", labelsize=8)
        ax1.set_ylabel("Price (USD)", color="#888", fontsize=8)
        for s in ax1.spines.values(): s.set_edgecolor("#2a2a20")
        ax2.bar(hist.index, hist["Volume"], color="#C9A84C", alpha=0.3, width=1)
        ax2.set_facecolor("#0F0F0C")
        ax2.tick_params(colors="#666", labelsize=7)
        ax2.set_ylabel("Volume", color="#888", fontsize=8)
        for s in ax2.spines.values(): s.set_edgecolor("#2a2a20")
        plt.tight_layout(rect=[0, 0, 1, 0.97])
        buf = io.BytesIO()
        plt.savefig(buf, format="png", bbox_inches="tight", dpi=130, facecolor="#0F0F0C")
        plt.close(fig)
        buf.seek(0)
        return f"CHART_BASE64:{base64.b64encode(buf.read()).decode()}"
    except Exception as e:
        return f"Chart error: {e}"


# ══════════════════════════════════════════════════════════════
# 8. FINANCIAL CALCULATOR
# ══════════════════════════════════════════════════════════════
@tool
def financial_calculator(input: str) -> str:
    """
    Financial calculations.
    Format: 'TYPE, param1, param2, ...'
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
            return (f"💰 Compound Interest\nPrincipal: ₦{P:,.2f}\n"
                    f"Rate: {r*100:.1f}%/yr  Years: {n:.0f}\n"
                    f"Final: ₦{A:,.2f}  Gain: ₦{A-P:,.2f} ({((A-P)/P)*100:.1f}%)")
        elif calc == "loan_payment":
            P, r_a, y = float(parts[1]), float(parts[2]), float(parts[3])
            r = r_a / 12; n = y * 12
            m = P * r * (1+r)**n / ((1+r)**n - 1) if r > 0 else P / n
            return (f"🏦 Loan\nPrincipal: ₦{P:,.2f}  Rate: {r_a*100:.1f}%/yr\n"
                    f"Monthly: ₦{m:,.2f}  Total: ₦{m*n:,.2f}  Interest: ₦{m*n-P:,.2f}")
        elif calc == "roi":
            g, c = float(parts[1]), float(parts[2])
            roi = ((g - c) / c) * 100
            return f"📈 ROI: {roi:.2f}%  Profit: ₦{g-c:,.2f}  (₦{c:,.2f} → ₦{g:,.2f})"
        elif calc == "break_even":
            f_, p, v = float(parts[1]), float(parts[2]), float(parts[3])
            m = p - v
            if m <= 0: return "Price must exceed variable cost."
            u = f_ / m
            return (f"⚖️ Break-Even\nUnits: {u:,.0f}  Revenue: ₦{u*p:,.2f}\n"
                    f"Fixed: ₦{f_:,.2f}  Margin/Unit: ₦{m:,.2f}")
        elif calc == "inflation_adjust":
            a, r, y = float(parts[1]), float(parts[2]), float(parts[3])
            real = a / (1 + r) ** y
            return (f"📉 Inflation\nNominal: ₦{a:,.2f}  Real: ₦{real:,.2f}\n"
                    f"Lost: ₦{a-real:,.2f} ({((a-real)/a)*100:.1f}%) over {y:.0f} yrs")
        elif calc == "future_value":
            pv, r, y = float(parts[1]), float(parts[2]), float(parts[3])
            return f"🔭 Future Value: ₦{pv * (1+r)**y:,.2f}  (₦{pv:,.2f} @ {r*100:.1f}%/yr × {y:.0f}yrs)"
        elif calc == "payback_period":
            i, cf = float(parts[1]), float(parts[2])
            return f"⏱️ Payback: {i/cf:.2f} years  (₦{i:,.2f} ÷ ₦{cf:,.2f}/yr)"
        else:
            return (f"Unknown: '{calc}'. Supported: compound_interest, loan_payment, "
                    f"roi, break_even, inflation_adjust, future_value, payback_period")
    except IndexError:
        return "Not enough parameters. Example: 'compound_interest, 500000, 0.15, 5'"
    except Exception as e:
        return f"Calculator error: {e}"


# ══════════════════════════════════════════════════════════════
# 9. MARKET OVERVIEW
# ══════════════════════════════════════════════════════════════
@tool
def get_market_overview(input: str = "all") -> str:
    """
    Live snapshot of global indices.
    Input: 'all' or 'indices'
    For crypto use get_crypto_price instead.
    """
    cache_key = f"market_{input}"
    cached = _cache.get(cache_key)
    if cached:
        return cached + "\n📋 Source: cached (< 60s old)"

    try:
        out = []
        indices = {
            "S&P 500":   "^GSPC",
            "Dow Jones": "^DJI",
            "NASDAQ":    "^IXIC",
            "VIX":       "^VIX",
        }
        out.append("── Global Indices ──")
        for name, sym in indices.items():
            try:
                h = yf.Ticker(sym).history(period="2d")
                if len(h) >= 2:
                    c1, c2 = h["Close"].iloc[-1], h["Close"].iloc[-2]
                    if c1 == c1 and c2 == c2 and c2 != 0:
                        chg   = c1 - c2
                        pct   = (chg / c2) * 100
                        arrow = "▲" if chg >= 0 else "▼"
                        out.append(f"{name:12} {c1:>12,.2f}  {arrow} {pct:+.2f}%")
                    else:
                        out.append(f"{name:12}  data unavailable")
                else:
                    out.append(f"{name:12}  insufficient data")
            except Exception:
                out.append(f"{name:12}  unavailable")

        result = "\n".join(out)
        _cache.set(cache_key, result, _TTL_STOCK)
        return result

    except Exception as e:
        return f"Market overview error: {e}"


# ══════════════════════════════════════════════════════════════
# 10. TASK PLANNER
# ══════════════════════════════════════════════════════════════
@tool
def plan_task(goal: str) -> str:
    """
    Break a complex financial goal into a step-by-step plan.
    Use FIRST for multi-step requests.
    """
    return (
        f"📋 Plan: {goal}\n\n"
        "Step 1 — Identify objective and required inputs\n"
        "Step 2 — Determine tools and data sources needed\n"
        "Step 3 — Gather data (prices, rates, financials)\n"
        "Step 4 — Calculate or analyse\n"
        "Step 5 — Validate results\n"
        "Step 6 — Deliver clear recommendation\n\n"
        "Executing now..."
    )


# ══════════════════════════════════════════════════════════════
# EXPORT
# ══════════════════════════════════════════════════════════════
amhani_tools = [
    get_stock_price,
    convert_currency,
    get_crypto_price,
    calculate_pe_ratio,
    execute_python,
    analyse_financial_data,
    generate_stock_chart,
    financial_calculator,
    get_market_overview,
    plan_task,
]
