# =============================================================
# tools.py — AMHANi ENTERPRISE v5
#
# API SOURCE CHANGES:
#
#   STOCK PRICES — FMP replaced by Polygon.io
#     Why Polygon.io over FMP:
#       - Free tier: unlimited daily calls (FMP caps at 250/day)
#       - Rate limit: 5 req/min on free (enough for a chat agent)
#       - Zero IP blocking on cloud servers (FMP and Yahoo both
#         throttle Streamlit Cloud's shared egress IPs)
#       - Covers US equities, crypto, forex, options, indices
#       - Sub-second response times via CDN edge nodes
#       - No credit card required for free plan
#     Signup: polygon.io → free plan
#     Secret: POLYGON_API_KEY
#
#   NIGERIAN MARKET — NGNMarket replaced by NGX Pulse
#     Key in Streamlit secrets / .env: X_API_KEY
#     Implemented with both header styles:
#       "X-Api-Key": key  (primary)
#       "Authorization": f"Bearer {key}"  (fallback header style)
#     Endpoints tried in order until one returns data.
#
#   ALL OTHER TOOLS — unchanged from v4
#     yfinance remains as universal fallback
#     Binance REST for crypto 4H (no key needed)
#     Yahoo Finance direct HTTP for index 4H
# =============================================================

import io
import os
import sys
import json
import math
import time
import base64
import traceback
import threading
import concurrent.futures
import urllib.parse
import requests
from datetime import datetime

import yfinance as yf
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from langchain.tools import tool


# ── API key accessors ─────────────────────────────────────────
_POLYGON_KEY = lambda: os.getenv("POLYGON_API_KEY", "")
_NGX_KEY     = lambda: os.getenv("X_API_KEY", "")       # NGX Pulse


# ══════════════════════════════════════════════════════════════
# TTL CACHE
# ══════════════════════════════════════════════════════════════
class _TTLCache:
    def __init__(self):
        self._d = {}
        self._l = threading.Lock()

    def get(self, k):
        with self._l:
            e = self._d.get(k)
            if e:
                v, ts, ttl = e
                if time.time() - ts < ttl:
                    return v
                del self._d[k]
        return None

    def set(self, k, v, ttl=60):
        with self._l:
            self._d[k] = (v, time.time(), ttl)


_cache      = _TTLCache()
_TTL_STOCK  = 60
_TTL_CRYPTO = 60
_TTL_FX     = 300
_TTL_4H     = 240
_TTL_NEWS   = 600


# ══════════════════════════════════════════════════════════════
# HTTP HELPERS
# ══════════════════════════════════════════════════════════════
def _http_get(url: str, params: dict = None,
              headers: dict = None, timeout: int = 12):
    """GET with timeout → parsed JSON or None."""
    try:
        r = requests.get(url, params=params or {},
                         headers=headers or {}, timeout=timeout)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def _yf_fetch(ticker: str, interval: str = "1d",
              period: str = "2d", timeout_sec: int = 12) -> pd.DataFrame:
    """yfinance call with hard timeout — never hangs on cloud."""
    def _f():
        return yf.Ticker(ticker).history(interval=interval, period=period)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(_f).result(timeout=timeout_sec)
    except Exception:
        return pd.DataFrame()


def _yf_direct_1h(ticker: str) -> pd.DataFrame:
    """
    Direct HTTP to Yahoo Finance v8 chart API — no yfinance library.
    Avoids ThreadPoolExecutor stall for intraday data on cloud IPs.
    """
    try:
        safe = urllib.parse.quote(ticker, safe="")
        r = requests.get(
            f"https://query2.finance.yahoo.com/v8/finance/chart/{safe}",
            params={"interval": "1h", "range": "7d",
                    "includePrePost": "false"},
            headers={"User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
            )},
            timeout=15,
        )
        if r.status_code != 200:
            return pd.DataFrame()
        data   = r.json()
        result = (data.get("chart") or {}).get("result")
        if not result:
            return pd.DataFrame()
        row = result[0]
        ts  = row.get("timestamp", [])
        q   = (row.get("indicators") or {}).get("quote", [{}])[0]
        if not ts or not q:
            return pd.DataFrame()
        df = pd.DataFrame({
            "Open":   q.get("open",   [None] * len(ts)),
            "High":   q.get("high",   [None] * len(ts)),
            "Low":    q.get("low",    [None] * len(ts)),
            "Close":  q.get("close",  [None] * len(ts)),
            "Volume": q.get("volume", [0]    * len(ts)),
        }, index=pd.to_datetime(ts, unit="s", utc=True))
        return df.dropna(subset=["Close"])
    except Exception:
        return pd.DataFrame()


# ══════════════════════════════════════════════════════════════
# 1. STOCK PRICE — Polygon.io primary, yfinance fallback
# ══════════════════════════════════════════════════════════════
@tool
def get_stock_price(ticker: str) -> str:
    """
    Get current stock price, change %, high, low, volume.
    Input: any ticker — 'AAPL', 'TSLA', 'NVDA', 'DANGOTE.LG'
    Sources: Polygon.io (primary) → Yahoo Finance fast_info → YF history
    """
    ticker    = ticker.upper().strip()
    cache_key = f"stock_{ticker}"
    cached    = _cache.get(cache_key)
    if cached:
        return cached + "\n📋 cached (< 60s)"

    poly_key = _POLYGON_KEY()

    # ── Method 1: Polygon.io snapshot (best on cloud IPs) ────
    if poly_key:
        try:
            data = _http_get(
                f"https://api.polygon.io/v2/snapshot/locale/us/markets"
                f"/stocks/tickers/{ticker}",
                params={"apiKey": poly_key},
            )
            snap = (data or {}).get("ticker", {})
            day  = snap.get("day", {})
            prev = snap.get("prevDay", {})
            price = day.get("c") or snap.get("lastTrade", {}).get("p")
            if price and price > 0:
                prev_c = prev.get("c") or price
                chg    = price - prev_c
                pct    = (chg / prev_c * 100) if prev_c else 0
                arrow  = "▲" if chg >= 0 else "▼"
                result = (
                    f"📈 {ticker}\n"
                    f"Price:    ${price:,.2f}\n"
                    f"Change:   {arrow} {chg:+.2f} ({pct:+.2f}%)\n"
                    f"Day High: ${day.get('h', price):,.2f}\n"
                    f"Day Low:  ${day.get('l', price):,.2f}\n"
                    f"Volume:   {day.get('v', 0):,.0f}\n"
                    f"Source:   Polygon.io (live)"
                )
                _cache.set(cache_key, result, _TTL_STOCK)
                return result
        except Exception:
            pass

    # ── Method 2: yfinance fast_info ─────────────────────────
    try:
        fi    = yf.Ticker(ticker).fast_info
        price = fi.last_price
        prev  = fi.previous_close or price
        if price and price == price and price > 0:
            chg   = price - prev
            pct   = (chg / prev * 100) if prev else 0
            arrow = "▲" if chg >= 0 else "▼"
            result = (
                f"📈 {ticker}\n"
                f"Price:    ${price:,.2f}\n"
                f"Change:   {arrow} {chg:+.2f} ({pct:+.2f}%)\n"
                f"Day High: ${fi.day_high:,.2f}\n"
                f"Day Low:  ${fi.day_low:,.2f}\n"
                f"Source:   Yahoo Finance (live)"
            )
            _cache.set(cache_key, result, _TTL_STOCK)
            return result
    except Exception:
        pass

    # ── Method 3: yfinance history ────────────────────────────
    try:
        h = _yf_fetch(ticker, period="2d")
        if not h.empty and len(h) >= 1:
            c1 = h["Close"].iloc[-1]
            c2 = h["Close"].iloc[-2] if len(h) > 1 else c1
            if c1 == c1 and c1 > 0:
                chg   = c1 - c2
                pct   = (chg / c2 * 100) if c2 else 0
                arrow = "▲" if chg >= 0 else "▼"
                result = (
                    f"📈 {ticker}\n"
                    f"Price:    ${c1:,.2f}\n"
                    f"Change:   {arrow} {chg:+.2f} ({pct:+.2f}%)\n"
                    f"Day High: ${h['High'].iloc[-1]:,.2f}\n"
                    f"Day Low:  ${h['Low'].iloc[-1]:,.2f}\n"
                    f"Source:   Yahoo Finance (delayed)"
                )
                _cache.set(cache_key, result, _TTL_STOCK)
                return result
    except Exception:
        pass

    return (
        f"⚠️ {ticker}: price unavailable from all sources.\n"
        f"Ensure POLYGON_API_KEY is in Streamlit secrets (polygon.io free plan).\n"
        f"Fallback: visit finance.yahoo.com/quote/{ticker}"
    )


# ══════════════════════════════════════════════════════════════
# 2. CURRENCY CONVERTER
# ══════════════════════════════════════════════════════════════
@tool
def convert_currency(input: str) -> str:
    """
    Convert between currencies using live rates.
    Format: 'amount, FROM, TO'
    Examples: '1500, USD, NGN'  |  '50000, NGN, USD'  |  '200, GBP, EUR'
    """
    try:
        parts = [p.strip() for p in input.split(",")]
        if len(parts) < 3:
            return "Format: 'amount, FROM, TO'  e.g. '1500, USD, NGN'"
        amount = float(parts[0])
        frm    = parts[1].upper()
        to     = parts[2].upper()
        ck     = f"fx_{frm}_{to}"
        rate   = _cache.get(ck)

        if not rate:
            data = _http_get(f"https://open.er-api.com/v6/latest/{frm}")
            if data and data.get("result") == "success":
                rate = (data.get("rates") or {}).get(to)
                if rate:
                    _cache.set(ck, rate, _TTL_FX)

        if not rate:
            data = _http_get(
                f"https://api.frankfurter.app/latest?from={frm}&to={to}"
            )
            if data:
                rate = (data.get("rates") or {}).get(to)
                if rate:
                    _cache.set(ck, rate, _TTL_FX)

        if not rate:
            h = _yf_fetch(f"{frm}{to}=X", period="2d")
            if not h.empty:
                r = h["Close"].iloc[-1]
                if r == r and r > 0:
                    rate = float(r)
                    _cache.set(ck, rate, _TTL_FX)

        if not rate:
            ngn = {"USD": 1620, "GBP": 2050, "EUR": 1750,
                   "CAD": 1190, "AUD": 1040}
            if to == "NGN" and frm in ngn:
                return (f"💱 {amount:,.2f} {frm} ≈ ₦{amount*ngn[frm]:,.2f}\n"
                        f"⚠️ Estimated — live APIs unavailable")
            if frm == "NGN" and to in ngn:
                return (f"💱 ₦{amount:,.2f} ≈ {amount/ngn[to]:,.4f} {to}\n"
                        f"⚠️ Estimated — live APIs unavailable")
            return f"⚠️ Could not fetch {frm}→{to} rate. Try again shortly."

        return (
            f"💱 Currency Conversion\n"
            f"{amount:,.2f} {frm} = {amount * rate:,.2f} {to}\n"
            f"Rate: 1 {frm} = {rate:,.6f} {to}"
        )
    except Exception as e:
        return f"Conversion error: {e}"


# ══════════════════════════════════════════════════════════════
# 3. CRYPTO PRICE
# ══════════════════════════════════════════════════════════════
_CG_IDS = {
    "BTC": "bitcoin", "ETH": "ethereum", "BNB": "binancecoin",
    "SOL": "solana",  "ADA": "cardano",  "XRP": "ripple",
    "DOGE": "dogecoin", "DOT": "polkadot", "MATIC": "matic-network",
    "LINK": "chainlink", "AVAX": "avalanche-2", "SHIB": "shiba-inu",
}

@tool
def get_crypto_price(input: str = "BTC,ETH") -> str:
    """
    Get live crypto prices. Supports 4H technical analysis.
    Input: 'BTC'  |  'BTC,ETH,SOL'  |  'BTC,4h'  |  'ETH,4h'
    """
    try:
        want_4h = "4h" in input.lower()
        raw     = input.lower().replace("4h", "").replace("4hour", "")
        coins   = [c.strip().upper() for c in raw.split(",") if c.strip()]
        if not coins:
            coins = ["BTC"]

        ck     = f"crypto_{'_'.join(sorted(coins))}"
        cached = _cache.get(ck)
        out    = cached.split("\n") if cached else ["── Crypto Prices ──"]

        if not cached:
            cg_ids  = [_CG_IDS.get(c, c.lower()) for c in coins]
            fetched = False
            data    = _http_get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={
                    "ids":                 ",".join(cg_ids),
                    "vs_currencies":       "usd",
                    "include_24hr_change": "true",
                },
            )
            if data and not data.get("error"):
                for coin, cg_id in zip(coins, cg_ids):
                    e     = data.get(cg_id, {})
                    price = e.get("usd")
                    chg   = e.get("usd_24h_change", 0) or 0
                    if price:
                        arrow = "▲" if chg >= 0 else "▼"
                        out.append(
                            f"{coin}: ${price:>12,.2f}  {arrow} {chg:+.2f}% (24h)"
                        )
                        fetched = True

            if not fetched:
                for coin in coins:
                    h = _yf_fetch(f"{coin}-USD", period="2d")
                    if not h.empty and h["Close"].iloc[-1] == h["Close"].iloc[-1]:
                        p   = h["Close"].iloc[-1]
                        pv  = h["Close"].iloc[-2] if len(h) > 1 else p
                        chg = p - pv
                        pct = (chg / pv * 100) if pv else 0
                        out.append(
                            f"{coin}: ${p:>12,.2f}  "
                            f"{'▲' if chg>=0 else '▼'} {pct:+.2f}%"
                        )
                    else:
                        out.append(f"{coin}: temporarily unavailable")

            _cache.set(ck, "\n".join(out), _TTL_CRYPTO)

        if want_4h:
            for coin in coins:
                out.append("")
                out.append(_fetch_4h_levels(f"{coin}-USD", coin))

        return "\n".join(out)
    except Exception as e:
        return f"Crypto error: {e}"


# ══════════════════════════════════════════════════════════════
# 4H INFRASTRUCTURE
# ══════════════════════════════════════════════════════════════
_CRYPTO_BASES = {
    "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE",
    "DOT", "MATIC", "AVAX", "LINK", "LTC", "UNI", "ATOM",
    "FIL", "TRX", "SHIB", "ARB", "OP", "APT",
}

def _is_crypto(ticker: str) -> bool:
    clean = ticker.upper().replace("-USD", "").replace("-USDT", "").strip()
    return clean in _CRYPTO_BASES or (
        ticker.upper().endswith("-USD") and not ticker.startswith("^")
    )


def _binance_4h(coin_ticker: str) -> list:
    """Real 4H OHLCV from Binance public klines — no auth required."""
    raw    = coin_ticker.upper().replace("-USD","").replace("-USDT","").strip()
    symbol = raw + "USDT"
    for url in [
        "https://api.binance.com/api/v3/klines",
        "https://api1.binance.com/api/v3/klines",
    ]:
        try:
            r = requests.get(url, params={"symbol": symbol,
                             "interval": "4h", "limit": 10},
                             headers={"User-Agent": "Mozilla/5.0"},
                             timeout=12)
            if r.status_code != 200:
                continue
            data = r.json()
            if isinstance(data, list) and len(data) >= 2:
                return [{"open": float(k[1]), "high": float(k[2]),
                         "low":  float(k[3]), "close": float(k[4]),
                         "vol":  float(k[5])} for k in data]
        except Exception:
            continue
    return []


def _format_4h(candles: list, name: str, source: str) -> str:
    if len(candles) < 2:
        return f"⚠️ Not enough 4H candles for {name}."
    curr = candles[-1]; prev = candles[-2]
    c    = curr["close"]
    mid  = (curr["high"] + curr["low"]) / 2
    rng  = curr["high"] - curr["low"]
    return (
        f"── {name} 4H Analysis ──\n"
        f"Close:   {c:,.2f}  ({'▲' if c>prev['close'] else '▼'} vs prev)\n"
        f"Open:    {curr['open']:,.2f}\n"
        f"High:    {curr['high']:,.2f}   "
        f"R1: {curr['high']+rng*0.382:,.2f}   R2: {curr['high']+rng*0.618:,.2f}\n"
        f"Low:     {curr['low']:,.2f}   "
        f"S1: {curr['low']-rng*0.382:,.2f}   S2: {curr['low']-rng*0.618:,.2f}\n"
        f"Mid:     {mid:,.2f}   Bias: {'Bullish ▲' if c>mid else 'Bearish ▼'}\n"
        f"Prev 4H: {prev['close']:,.2f}   Vol: {curr['vol']:,.0f}\n"
        f"Source: {source}"
    )


def _df_to_4h_candles(h: pd.DataFrame) -> list:
    h   = h.dropna(subset=["Close"])
    bars = h[["Open","High","Low","Close","Volume"]].values
    out  = []
    for i in range(0, len(bars) - 3, 4):
        chunk = bars[i:i+4]
        if len(chunk) == 4:
            out.append({
                "open":  float(chunk[0][0]),
                "high":  float(chunk[:,1].max()),
                "low":   float(chunk[:,2].min()),
                "close": float(chunk[-1][3]),
                "vol":   float(chunk[:,4].sum()),
            })
    return out


def _fetch_4h_levels(ticker: str, display_name: str) -> str:
    """
    4-path waterfall:
      1. Binance klines  — crypto, real 4H, always works on cloud
      2. YF direct HTTP  — indices/stocks, bypasses yfinance stall
      3. yfinance lib    — local dev fallback
      4. ETF map         — DIA/SPY/QQQ when futures time out
    """
    ck     = f"4h_{ticker}"
    cached = _cache.get(ck)
    if cached:
        return cached

    # Path 1 — Binance (crypto only)
    if _is_crypto(ticker):
        candles = _binance_4h(ticker)
        if len(candles) >= 2:
            result = _format_4h(candles, display_name,
                                 "Binance API — real 4H klines (live)")
            _cache.set(ck, result, _TTL_4H)
            return result

    # Path 2 — Yahoo Finance direct HTTP
    h = _yf_direct_1h(ticker)
    if h is None or h.empty or len(h) < 4:
        h = None

    # Path 3 — yfinance library
    if h is None:
        h = _yf_fetch(ticker, interval="1h", period="7d", timeout_sec=15)
        if h is None or h.empty or len(h) < 4:
            h = None

    # Path 4 — ETF fallback map
    _fallback = {
        "^DJI":["YM=F","DIA"], "^GSPC":["ES=F","SPY"],
        "^IXIC":["NQ=F","QQQ"], "^VIX":["VIXY"],
        "YM=F":["DIA"], "ES=F":["SPY"], "NQ=F":["QQQ"],
        "GC=F":["GLD","IAU"], "CL=F":["USO","XLE"],
        "RTY=F":["IWM"], "ZN=F":["TLT"],
    }
    if h is None:
        for alt in _fallback.get(ticker.upper(), []):
            ha = _yf_direct_1h(alt)
            if ha is not None and not ha.empty and len(ha) >= 4:
                h = ha
                display_name = f"{display_name} (via {alt})"
                break
            ha = _yf_fetch(alt, interval="1h", period="7d", timeout_sec=15)
            if ha is not None and not ha.empty and len(ha) >= 4:
                h = ha
                display_name = f"{display_name} (via {alt})"
                break

    if h is None or h.empty or len(h) < 4:
        return (
            f"⚠️ 4H data unavailable for {display_name}.\n"
            f"Try: 'BTC 4h' · 'ETH 4h' · 'US30 4h' · 'SPX 4h'"
        )

    candles = _df_to_4h_candles(h)
    if len(candles) < 2:
        return f"⚠️ Not enough 4H candles for {display_name}."
    result = _format_4h(candles, display_name,
                         f"Yahoo Finance 1H→4H ({len(candles)} candles)")
    _cache.set(ck, result, _TTL_4H)
    return result


# ══════════════════════════════════════════════════════════════
# 4. INDEX 4H
# ══════════════════════════════════════════════════════════════
@tool
def get_index_4h(input: str) -> str:
    """
    4-hour technical analysis for major indices.
    Input: 'US30' | 'SPX' | 'NAS100' | 'NASDAQ' | 'Dow' | 'GOLD' | 'OIL'
    Examples: 'US30 4h'  |  'SPX 4h'  |  'GOLD'
    """
    mapping = {
        "US30":("YM=F","US30/Dow"), "DOW":("YM=F","US30/Dow"),
        "DJI":("YM=F","US30/Dow"), "DOWJONES":("YM=F","US30/Dow"),
        "SPX":("ES=F","SPX/S&P500"), "SP500":("ES=F","SPX/S&P500"),
        "NAS":("NQ=F","NAS100"), "NAS100":("NQ=F","NAS100"),
        "NASDAQ":("NQ=F","NAS100"), "NDX":("NQ=F","NAS100"),
        "GOLD":("GC=F","Gold/XAU"), "XAUUSD":("GC=F","Gold/XAU"),
        "OIL":("CL=F","Crude/WTI"), "USOIL":("CL=F","Crude/WTI"),
        "GER40":("^GDAXI","GER40/DAX"), "DAX":("^GDAXI","GER40/DAX"),
    }
    clean        = input.strip().upper().replace(" ","").replace("/","").replace("4H","")
    ticker, name = mapping.get(clean, (None, None))
    if not ticker:
        ticker = input.strip().upper().replace("4H","").strip()
        name   = ticker
    return _fetch_4h_levels(ticker, name)


# ══════════════════════════════════════════════════════════════
# 5. NGX MARKET — Nigerian equities via NGX Pulse
# ══════════════════════════════════════════════════════════════
@tool
def get_ngx_market(input: str = "overview") -> str:
    """
    Nigerian Exchange (NGX) live market data via NGX Pulse API.
    Input:
      'overview'      → market summary + top movers
      'GTCO'          → specific NGX stock quote
      'DANGOTE'       → specific NGX stock quote
      'ZENITH'        → specific NGX stock quote
      'top gainers'   → today's biggest NGX gainers
      'top losers'    → today's biggest NGX losers
      'indices'       → NGX All-Share Index and sectoral indices
    API key: X_API_KEY in Streamlit secrets / .env
    """
    inp  = input.strip()
    ck   = f"ngx_{inp.lower()}"
    cached = _cache.get(ck)
    if cached:
        return cached

    key = _NGX_KEY()
    # NGX Pulse supports both header styles — try both
    headers_options = [
        {"X-Api-Key": key, "Accept": "application/json"},
        {"Authorization": f"Bearer {key}", "Accept": "application/json"},
        {"Authorization": key, "Accept": "application/json"},
    ]

    # ── Base URLs to try (NGX Pulse API patterns) ─────────────
    BASE = "https://api.ngxpulse.com"
    BASES = [BASE, "https://ngxpulse.com/api", "https://data.ngxpulse.com"]

    inp_lower = inp.lower()
    is_overview = inp_lower in ("overview", "market", "indices", "")
    is_gainers  = "gainer" in inp_lower
    is_losers   = "loser"  in inp_lower

    if key:
        for base in BASES:
            for hdrs in headers_options:
                try:
                    # Specific stock lookup
                    if not is_overview and not is_gainers and not is_losers:
                        sym = inp.upper()
                        for ep in [
                            f"{base}/stocks/{sym}",
                            f"{base}/quote/{sym}",
                            f"{base}/v1/stocks/{sym}",
                            f"{base}/v1/quotes/{sym}",
                            f"{base}/market/stocks/{sym}",
                        ]:
                            data = _http_get(ep, headers=hdrs)
                            if not data:
                                continue
                            # Normalise different field name styles
                            price  = (data.get("price") or data.get("close")
                                      or data.get("lastPrice") or data.get("last") or 0)
                            chg    = (data.get("change") or data.get("priceChange") or 0)
                            pct    = (data.get("changePercent") or data.get("pct_change")
                                      or data.get("percentChange") or 0)
                            vol    = (data.get("volume") or data.get("tradeVolume") or 0)
                            name_  = (data.get("name") or data.get("companyName") or sym)
                            arrow  = "▲" if float(chg) >= 0 else "▼"
                            result = (
                                f"📈 {sym} — {name_} (NGX)\n"
                                f"Price:  ₦{float(price):,.2f}\n"
                                f"Change: {arrow} ₦{float(chg):+.2f} ({float(pct):+.2f}%)\n"
                                f"Volume: {int(vol):,}\n"
                                f"Source: NGX Pulse API (live)"
                            )
                            _cache.set(ck, result, _TTL_STOCK)
                            return result

                    # Market overview / gainers / losers
                    else:
                        ep_map = {
                            True:  [f"{base}/market/gainers",
                                    f"{base}/v1/market/gainers",
                                    f"{base}/gainers"],
                            "loser": [f"{base}/market/losers",
                                      f"{base}/v1/market/losers",
                                      f"{base}/losers"],
                            "overview": [f"{base}/market/overview",
                                         f"{base}/v1/market/overview",
                                         f"{base}/market",
                                         f"{base}/overview"],
                        }
                        if is_gainers:
                            endpoints = ep_map[True]
                        elif is_losers:
                            endpoints = ep_map["loser"]
                        else:
                            endpoints = ep_map["overview"]

                        for ep in endpoints:
                            data = _http_get(ep, headers=hdrs)
                            if not data:
                                continue
                            stocks = (data if isinstance(data, list)
                                      else data.get("data") or data.get("stocks")
                                      or data.get("results") or [])
                            if not stocks:
                                continue
                            label  = ("Gainers" if is_gainers else
                                      "Losers" if is_losers else "Overview")
                            out    = [f"── NGX Market {label} ──"]
                            for s in stocks[:12]:
                                sym_  = (s.get("symbol") or s.get("ticker") or "")
                                pr    = (s.get("price") or s.get("close") or
                                         s.get("lastPrice") or 0)
                                pc    = (s.get("changePercent") or s.get("pct_change")
                                         or s.get("percentChange") or 0)
                                ar    = "▲" if float(pc) >= 0 else "▼"
                                out.append(
                                    f"{sym_:12} ₦{float(pr):>10,.2f}  {ar} {float(pc):+.2f}%"
                                )
                            if len(out) > 1:
                                result = "\n".join(out)
                                _cache.set(ck, result, _TTL_STOCK)
                                return result
                except Exception:
                    continue

    # ── Fallback: yfinance .LG / .LA suffix for NGX ───────────
    if not is_overview and not is_gainers and not is_losers:
        sym_yf = inp.upper()
        for suffix in [".LG", ".LA"]:
            h = _yf_fetch(f"{sym_yf}{suffix}", period="2d")
            if not h.empty and len(h) >= 1:
                p = h["Close"].iloc[-1]
                if p == p and p > 0:
                    pv  = h["Close"].iloc[-2] if len(h) > 1 else p
                    chg = p - pv
                    pct = (chg / pv * 100) if pv else 0
                    result = (
                        f"📈 {sym_yf} (NGX)\n"
                        f"Price:  ₦{p:,.2f}\n"
                        f"Change: {'▲' if chg>=0 else '▼'} ₦{chg:+.2f} ({pct:+.2f}%)\n"
                        f"Source: Yahoo Finance ({sym_yf}{suffix})"
                    )
                    _cache.set(ck, result, _TTL_STOCK)
                    return result

    key_status = "configured ✓" if key else "NOT SET ✗"
    return (
        f"⚠️ NGX market data unavailable.\n"
        f"X_API_KEY status: {key_status}\n"
        f"If key is set, NGX Pulse API may be temporarily down.\n"
        f"Fallback: try 'GTCO.LG' or 'DANGOTE.LG' via get_stock_price."
    )


# ══════════════════════════════════════════════════════════════
# 6. STOCK FINANCIALS — Polygon.io (replaces FMP)
# ══════════════════════════════════════════════════════════════
@tool
def get_stock_financials(input: str) -> str:
    """
    Detailed financial data: income statement, key ratios, EPS.
    Input: ticker e.g. 'AAPL'  'TSLA'  'NVDA'
    Optional: 'AAPL, quarterly' for quarterly breakdown
    Source: Polygon.io financials API (POLYGON_API_KEY required)
    """
    parts   = [p.strip() for p in input.split(",")]
    ticker  = parts[0].upper()
    period  = "quarterly" if len(parts) > 1 and "q" in parts[1].lower() else "annual"
    ck      = f"fin_{ticker}_{period}"
    cached  = _cache.get(ck)
    if cached:
        return cached

    poly_key = _POLYGON_KEY()
    if not poly_key:
        return (
            f"⚠️ POLYGON_API_KEY not set.\n"
            f"Sign up free at polygon.io → add POLYGON_API_KEY to Streamlit secrets."
        )

    try:
        # Polygon financials endpoint
        data = _http_get(
            f"https://api.polygon.io/vX/reference/financials",
            params={
                "ticker":         ticker,
                "timeframe":      "quarterly" if period == "quarterly" else "annual",
                "limit":          2,
                "apiKey":         poly_key,
            },
        )
        results = (data or {}).get("results", [])
        if not results:
            return f"⚠️ No financial data found for {ticker} on Polygon.io."

        out = [f"── {ticker} Financials ({period.title()}) ──"]
        for i, r in enumerate(results[:2]):
            fp   = r.get("fiscal_period", "")
            fy   = r.get("fiscal_year", "")
            inc  = r.get("financials", {}).get("income_statement", {})
            bal  = r.get("financials", {}).get("balance_sheet", {})
            cf   = r.get("financials", {}).get("cash_flow_statement", {})

            rev  = (inc.get("revenues") or {}).get("value", 0)
            ni   = (inc.get("net_income_loss") or {}).get("value", 0)
            eps  = (inc.get("basic_earnings_per_share") or {}).get("value", 0)
            op   = (inc.get("operating_income_loss") or {}).get("value", 0)
            gp   = (inc.get("gross_profit") or {}).get("value", 0)
            ta   = (bal.get("assets") or {}).get("value", 0)
            tl   = (bal.get("liabilities") or {}).get("value", 0)
            fcf  = (cf.get("net_cash_flow") or {}).get("value", 0)

            gm   = (gp / rev * 100)  if rev else 0
            nm   = (ni / rev * 100)  if rev else 0
            de   = (tl / (ta - tl))  if (ta - tl) > 0 else 0

            label = f"{'Latest' if i==0 else 'Prior'} {fp} {fy}"
            out.append(
                f"\n{label}\n"
                f"Revenue:      ${rev/1e9:.2f}B\n"
                f"Gross Profit: ${gp/1e9:.2f}B  (Margin: {gm:.1f}%)\n"
                f"Op. Income:   ${op/1e9:.2f}B\n"
                f"Net Income:   ${ni/1e9:.2f}B  (Margin: {nm:.1f}%)\n"
                f"EPS (Basic):  ${eps:.2f}\n"
                f"Total Assets: ${ta/1e9:.2f}B\n"
                f"D/E Ratio:    {de:.2f}\n"
                f"Net Cash Flow:${fcf/1e9:.2f}B"
            )

        result = "\n".join(out) + "\nSource: Polygon.io Financials API"
        _cache.set(ck, result, 3600)
        return result

    except Exception as e:
        return f"Financials error for {ticker}: {e}"


# ══════════════════════════════════════════════════════════════
# 7. INSIDER TRADES — Polygon.io (replaces D2V/FMP)
# ══════════════════════════════════════════════════════════════
@tool
def get_insider_trades(ticker: str) -> str:
    """
    Recent SEC insider trades (Form 4) via Polygon.io.
    Shows insider name, role, buy/sell, shares, price, value.
    Input: US stock ticker e.g. 'AAPL'  'TSLA'  'NVDA'
    Source: Polygon.io (POLYGON_API_KEY) → SEC EDGAR fallback
    """
    ticker = ticker.upper().strip()
    ck     = f"insider_{ticker}"
    cached = _cache.get(ck)
    if cached:
        return cached

    poly_key = _POLYGON_KEY()

    # ── Method 1: Polygon.io insider transactions ─────────────
    if poly_key:
        try:
            data = _http_get(
                "https://api.polygon.io/vX/reference/tickers/"
                f"{ticker}/insider-transactions",
                params={"apiKey": poly_key, "limit": 10},
            )
            trades = (data or {}).get("results", [])
            if trades:
                out = [f"── {ticker} Insider Trades (SEC Form 4) ──"]
                for t in trades[:8]:
                    name_   = t.get("filer_name", "Unknown")
                    role    = t.get("filer_relation", "")
                    tx_type = t.get("transaction_type", "")
                    shares  = abs(t.get("shares", 0) or 0)
                    price   = t.get("share_price", 0) or 0
                    date_   = t.get("filed_date", "")
                    value   = shares * price
                    is_buy  = "A" in str(tx_type) or "buy" in str(tx_type).lower()
                    side    = "BUY  🟢" if is_buy else "SELL 🔴"
                    out.append(
                        f"{side}  {name_} ({role})\n"
                        f"       {shares:,.0f} shares @ ${price:,.2f}"
                        f" = ${value:,.0f}  [{date_}]"
                    )
                result = "\n".join(out)
                _cache.set(ck, result, _TTL_NEWS)
                return result
        except Exception:
            pass

    # ── Method 2: SEC EDGAR public search (no key) ────────────
    try:
        hdrs = {"User-Agent": "AMHANi Enterprise contact@amhanienterprise.com"}
        data = _http_get(
            "https://efts.sec.gov/LATEST/search-index"
            f"?q=%22{ticker}%22&forms=4&dateRange=custom"
            "&startdt=2024-01-01&_source=file_date,display_names",
            headers=hdrs,
        )
        hits = (data or {}).get("hits", {}).get("hits", [])
        if hits:
            out = [f"── {ticker} Insider Filings (SEC EDGAR) ──"]
            for h in hits[:6]:
                src = h.get("_source", {})
                out.append(
                    f"Filed: {src.get('file_date','')}  "
                    f"Filer: {src.get('display_names','')}"
                )
            result = "\n".join(out)
            _cache.set(ck, result, _TTL_NEWS)
            return result
    except Exception:
        pass

    key_status = "configured ✓" if poly_key else "NOT SET — sign up free at polygon.io"
    return (
        f"⚠️ Insider data unavailable for {ticker}.\n"
        f"POLYGON_API_KEY: {key_status}\n"
        f"SEC EDGAR direct: sec.gov/cgi-bin/browse-edgar?action=getcompany&type=4"
    )


# ══════════════════════════════════════════════════════════════
# 8. P/E RATIO
# ══════════════════════════════════════════════════════════════
@tool
def calculate_pe_ratio(input: str) -> str:
    """P/E ratio calculator. Format: 'price, eps'  e.g. '150, 10.5'"""
    try:
        p = input.replace(";", ",").split(",")
        if len(p) < 2:
            return "Format: 'price, eps'"
        price, eps = float(p[0]), float(p[1])
        if eps == 0:
            return "EPS cannot be zero."
        pe = price / eps
        return (
            f"P/E: {pe:.2f}  |  ${price:.2f} / ${eps:.2f}\n"
            f"{'Undervalued (<15)' if pe<15 else 'Fairly valued (15-25)' if pe<25 else 'Premium/Growth (25-40)' if pe<40 else 'Highly speculative (>40)'}"
        )
    except Exception as e:
        return f"Error: {e}"


# ══════════════════════════════════════════════════════════════
# 9. PYTHON EXECUTOR
# ══════════════════════════════════════════════════════════════
@tool
def execute_python(code: str) -> str:
    """Execute Python code. Use print() for output. pd, math, json available."""
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
# 10. FINANCIAL DATA ANALYSER
# ══════════════════════════════════════════════════════════════
@tool
def analyse_financial_data(input: str) -> str:
    """Analyse JSON financial data. Input: '[{"month":"Jan","revenue":50000},...]'"""
    try:
        df  = pd.DataFrame(json.loads(input))
        out = [f"📊 {df.shape[0]}r × {df.shape[1]}c — {', '.join(df.columns)}"]
        num = df.select_dtypes(include="number")
        if not num.empty:
            out.append(num.describe().round(2).to_string())
        lower = {c.lower(): c for c in df.columns}
        if "revenue" in lower and "expenses" in lower:
            df["__p"] = df[lower["revenue"]] - df[lower["expenses"]]
            out.append(
                f"Profit: ₦{df['__p'].sum():,.2f}  "
                f"Margin: {(df['__p'].sum()/df[lower['revenue']].sum())*100:.1f}%"
            )
        return "\n".join(out)
    except Exception as e:
        return f"Analysis error: {e}"


# ══════════════════════════════════════════════════════════════
# 11. STOCK CHART
# ══════════════════════════════════════════════════════════════
@tool
def generate_stock_chart(input: str) -> str:
    """Gold-themed price chart. Input: 'TICKER' or 'TICKER, period' (1mo 3mo 6mo 1y)"""
    try:
        parts  = [p.strip() for p in input.split(",")]
        ticker = parts[0].upper()
        period = parts[1] if len(parts) > 1 else "3mo"
        hist   = _yf_fetch(ticker, period=period, timeout_sec=20)
        if hist.empty:
            return f"No chart data for {ticker}"
        fig, (a1, a2) = plt.subplots(
            2, 1, figsize=(10, 6),
            gridspec_kw={"height_ratios": [3, 1]},
            facecolor="#0F0F0C",
        )
        fig.suptitle(f"{ticker}  ·  {period.upper()}", color="#C9A84C",
                     fontsize=13, fontweight="bold", y=0.99)
        a1.plot(hist.index, hist["Close"], color="#C9A84C", linewidth=1.8)
        a1.fill_between(hist.index, hist["Close"], hist["Close"].min(),
                        alpha=0.07, color="#C9A84C")
        a1.set_facecolor("#0F0F0C"); a1.tick_params(colors="#666", labelsize=8)
        for s in a1.spines.values(): s.set_edgecolor("#2a2a20")
        a2.bar(hist.index, hist["Volume"], color="#C9A84C", alpha=0.3, width=1)
        a2.set_facecolor("#0F0F0C"); a2.tick_params(colors="#666", labelsize=7)
        for s in a2.spines.values(): s.set_edgecolor("#2a2a20")
        plt.tight_layout(rect=[0, 0, 1, 0.97])
        buf = io.BytesIO()
        plt.savefig(buf, format="png", bbox_inches="tight",
                    dpi=130, facecolor="#0F0F0C")
        plt.close(fig); buf.seek(0)
        return f"CHART_BASE64:{base64.b64encode(buf.read()).decode()}"
    except Exception as e:
        return f"Chart error: {e}"


# ══════════════════════════════════════════════════════════════
# 12. FINANCIAL CALCULATOR
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
        parts = [x.strip() for x in input.split(",")]
        calc  = parts[0].lower().replace(" ", "_")
        if calc == "compound_interest":
            P, r, n = float(parts[1]), float(parts[2]), float(parts[3])
            A = P * (1 + r) ** n
            return (f"💰 ₦{P:,.2f} @ {r*100:.1f}%/yr × {n:.0f}yrs\n"
                    f"Final: ₦{A:,.2f}  Gain: ₦{A-P:,.2f} ({((A-P)/P)*100:.1f}%)")
        elif calc == "loan_payment":
            P, r_a, y = float(parts[1]), float(parts[2]), float(parts[3])
            r = r_a / 12; n = y * 12
            m = P * r * (1+r)**n / ((1+r)**n - 1) if r > 0 else P / n
            return f"🏦 Monthly: ₦{m:,.2f}  Total: ₦{m*n:,.2f}  Interest: ₦{m*n-P:,.2f}"
        elif calc == "roi":
            g, c = float(parts[1]), float(parts[2])
            return f"📈 ROI: {((g-c)/c)*100:.2f}%  Profit: ₦{g-c:,.2f}"
        elif calc == "break_even":
            f_, p, v = float(parts[1]), float(parts[2]), float(parts[3])
            m = p - v
            if m <= 0: return "Price must exceed variable cost."
            return f"⚖️ Break-Even: {f_/m:,.0f} units  Revenue: ₦{(f_/m)*p:,.2f}"
        elif calc == "inflation_adjust":
            a, r, y = float(parts[1]), float(parts[2]), float(parts[3])
            real = a / (1 + r) ** y
            return f"📉 Real: ₦{real:,.2f}  Lost: ₦{a-real:,.2f} ({((a-real)/a)*100:.1f}%)"
        elif calc == "future_value":
            pv, r, y = float(parts[1]), float(parts[2]), float(parts[3])
            return f"🔭 Future: ₦{pv*(1+r)**y:,.2f}"
        elif calc == "payback_period":
            i, cf = float(parts[1]), float(parts[2])
            return f"⏱️ Payback: {i/cf:.2f} years"
        else:
            return ("Types: compound_interest, loan_payment, roi, "
                    "break_even, inflation_adjust, future_value, payback_period")
    except Exception as e:
        return f"Calculator error: {e}"


# ══════════════════════════════════════════════════════════════
# 13. MARKET OVERVIEW
# ══════════════════════════════════════════════════════════════
@tool
def get_market_overview(input: str = "all") -> str:
    """Global indices snapshot. Input: 'all'"""
    ck = f"mkt_{input}"
    c  = _cache.get(ck)
    if c:
        return c + "\n📋 cached"
    try:
        out = ["── Global Indices ──"]
        for name, sym in [
            ("S&P 500",   "^GSPC"), ("Dow Jones", "^DJI"),
            ("NASDAQ",    "^IXIC"), ("VIX",       "^VIX"),
        ]:
            h = _yf_fetch(sym, period="2d")
            if len(h) >= 2:
                c1, c2 = h["Close"].iloc[-1], h["Close"].iloc[-2]
                if c1 == c1 and c2 == c2 and c2 != 0:
                    chg = c1 - c2; pct = (chg / c2) * 100
                    out.append(
                        f"{name:12} {c1:>12,.2f}  "
                        f"{'▲' if chg>=0 else '▼'} {pct:+.2f}%"
                    )
                else:
                    out.append(f"{name:12}  unavailable")
            else:
                out.append(f"{name:12}  unavailable")
        r = "\n".join(out)
        _cache.set(ck, r, _TTL_STOCK)
        return r
    except Exception as e:
        return f"Overview error: {e}"


# ══════════════════════════════════════════════════════════════
# 14. TASK PLANNER
# ══════════════════════════════════════════════════════════════
@tool
def plan_task(goal: str) -> str:
    """Break complex goals into steps. Use FIRST for multi-step requests."""
    return (
        f"📋 Plan: {goal}\n\n"
        "1 — Identify objective and inputs\n"
        "2 — Select tools and data sources\n"
        "3 — Gather live data\n"
        "4 — Calculate / analyse\n"
        "5 — Validate and cross-check\n"
        "6 — Deliver clear recommendation\n\nExecuting now..."
    )


# ══════════════════════════════════════════════════════════════
# EXPORT
# ══════════════════════════════════════════════════════════════
amhani_tools = [
    get_stock_price,
    convert_currency,
    get_crypto_price,
    get_index_4h,
    get_ngx_market,           # replaces get_ngn_market (NGX Pulse)
    get_stock_financials,     # now uses Polygon.io (replaces FMP)
    get_insider_trades,       # now uses Polygon.io (replaces D2V/FMP)
    calculate_pe_ratio,
    execute_python,
    analyse_financial_data,
    generate_stock_chart,
    financial_calculator,
    get_market_overview,
    plan_task,
]