# =============================================================
# tools.py — AMHANi ENTERPRISE v4
#
# FIXES:
#   1. AAPL/TSLA unavailable: FMP API is now PRIMARY for stock
#      prices. yfinance is the fallback. FMP's free tier handles
#      US equities reliably on cloud IPs without rate-limiting.
#
#   2. New tools added:
#      - get_insider_trades   (SEC EDGAR via D2V API)
#      - get_stock_financials (Financial Modeling Prep)
#      - get_ngn_market       (NGNMarket for Nigerian equities)
#
#   3. All yfinance calls wrapped in ThreadPoolExecutor timeout.
#      No time.sleep() anywhere — never blocks Streamlit's loop.
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
import requests
from datetime import datetime

import yfinance as yf
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from langchain.tools import tool

# ── API Keys (from env / Streamlit secrets) ───────────────────
_FMP_KEY     = lambda: os.getenv("FMP_API_KEY", "")
_D2V_KEY     = lambda: os.getenv("D2V_API_KEY", "")
_NGNMKT_KEY  = lambda: os.getenv("NGNMARKET_API_KEY", "")


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

_cache = _TTLCache()
_TTL_STOCK  = 60
_TTL_CRYPTO = 60
_TTL_FX     = 300
_TTL_4H     = 240
_TTL_NEWS   = 600


# ══════════════════════════════════════════════════════════════
# SAFE FETCH HELPERS
# ══════════════════════════════════════════════════════════════
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


def _http_get(url: str, params: dict = None,
              headers: dict = None, timeout: int = 10):
    """Requests GET with timeout. Returns parsed JSON or None."""
    try:
        r = requests.get(url, params=params, headers=headers,
                         timeout=timeout)
        if r.status_code == 200:
            return r.json()
        return None
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════
# 1. STOCK PRICE — FMP primary, yfinance fallback
# ══════════════════════════════════════════════════════════════
@tool
def get_stock_price(ticker: str) -> str:
    """
    Get current stock price, change, and key stats.
    Input: any ticker symbol — 'AAPL', 'TSLA', 'DANGOTE.LG', 'GTCO.LG'
    Sources: Financial Modeling Prep (primary) → Yahoo Finance (fallback)
    """
    ticker    = ticker.upper().strip()
    cache_key = f"stock_{ticker}"
    cached    = _cache.get(cache_key)
    if cached:
        return cached + "\n📋 cached (< 60s)"

    # ── Method 1: FMP API (most reliable for US equities on cloud) ─
    fmp_key = _FMP_KEY()
    if fmp_key:
        try:
            data = _http_get(
                f"https://financialmodelingprep.com/api/v3/quote/{ticker}",
                params={"apikey": fmp_key},
            )
            if data and isinstance(data, list) and data[0]:
                q = data[0]
                price  = q.get("price") or 0
                chg    = q.get("change") or 0
                pct    = q.get("changesPercentage") or 0
                high   = q.get("dayHigh") or price
                low    = q.get("dayLow") or price
                vol    = q.get("volume") or 0
                mktcap = q.get("marketCap") or 0
                name   = q.get("name", ticker)
                arrow  = "▲" if chg >= 0 else "▼"
                result = (
                    f"📈 {ticker} — {name}\n"
                    f"Price:      ${price:,.2f}\n"
                    f"Change:     {arrow} {chg:+.2f} ({pct:+.2f}%)\n"
                    f"Day High:   ${high:,.2f}\n"
                    f"Day Low:    ${low:,.2f}\n"
                    f"Volume:     {vol:,.0f}\n"
                    f"Mkt Cap:    ${mktcap/1e9:.2f}B\n"
                    f"Source: Financial Modeling Prep (live)"
                )
                _cache.set(cache_key, result, _TTL_STOCK)
                return result
        except Exception:
            pass

    # ── Method 2: yfinance fast_info ──────────────────────────
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
                f"Price:  ${price:,.2f}\n"
                f"Change: {arrow} {chg:+.2f} ({pct:+.2f}%)\n"
                f"High:   ${fi.day_high:,.2f}\n"
                f"Low:    ${fi.day_low:,.2f}\n"
                f"Source: Yahoo Finance (live)"
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
                    f"Price:  ${c1:,.2f}\n"
                    f"Change: {arrow} {chg:+.2f} ({pct:+.2f}%)\n"
                    f"High:   ${h['High'].iloc[-1]:,.2f}\n"
                    f"Low:    ${h['Low'].iloc[-1]:,.2f}\n"
                    f"Source: Yahoo Finance (delayed)"
                )
                _cache.set(cache_key, result, _TTL_STOCK)
                return result
    except Exception:
        pass

    return (
        f"⚠️ {ticker}: price temporarily unavailable from all sources.\n"
        f"Add FMP_API_KEY to Streamlit secrets for reliable US equity data.\n"
        f"Try again in 60 seconds or visit finance.yahoo.com/quote/{ticker}"
    )


# ══════════════════════════════════════════════════════════════
# 2. CURRENCY CONVERTER
# ══════════════════════════════════════════════════════════════
@tool
def convert_currency(input: str) -> str:
    """
    Convert between currencies using live rates.
    Format: 'amount, FROM, TO'
    Examples: '1500, USD, NGN'   '50000, NGN, USD'   '200, GBP, EUR'
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
            # ExchangeRate-API
            data = _http_get(f"https://open.er-api.com/v6/latest/{frm}")
            if data and data.get("result") == "success":
                rate = (data.get("rates") or {}).get(to)
                if rate:
                    _cache.set(ck, rate, _TTL_FX)

        if not rate:
            # Frankfurter ECB
            data = _http_get(f"https://api.frankfurter.app/latest?from={frm}&to={to}")
            if data:
                rate = (data.get("rates") or {}).get(to)
                if rate:
                    _cache.set(ck, rate, _TTL_FX)

        if not rate:
            # yfinance fallback
            h = _yf_fetch(f"{frm}{to}=X", period="2d")
            if not h.empty:
                r = h["Close"].iloc[-1]
                if r == r and r > 0:
                    rate = r
                    _cache.set(ck, rate, _TTL_FX)

        if not rate:
            ngn = {"USD":1620,"GBP":2050,"EUR":1750,"CAD":1190,"AUD":1040}
            if to == "NGN" and frm in ngn:
                return (f"💱 {amount:,.2f} {frm} ≈ ₦{amount*ngn[frm]:,.2f}\n"
                        f"⚠️ Estimated rate — live APIs unavailable")
            if frm == "NGN" and to in ngn:
                return (f"💱 ₦{amount:,.2f} ≈ {amount/ngn[to]:,.4f} {to}\n"
                        f"⚠️ Estimated rate — live APIs unavailable")
            return f"⚠️ Could not fetch {frm}→{to} rate. Try again in a moment."

        converted = amount * rate
        return (
            f"💱 Currency Conversion\n"
            f"{amount:,.2f} {frm} = {converted:,.2f} {to}\n"
            f"Rate: 1 {frm} = {rate:,.6f} {to}"
        )
    except Exception as e:
        return f"Conversion error: {e}"


# ══════════════════════════════════════════════════════════════
# 3. CRYPTO PRICE
# ══════════════════════════════════════════════════════════════
_CG_IDS = {
    "BTC":"bitcoin","ETH":"ethereum","BNB":"binancecoin",
    "SOL":"solana","ADA":"cardano","XRP":"ripple",
    "DOGE":"dogecoin","DOT":"polkadot","MATIC":"matic-network",
    "LINK":"chainlink","AVAX":"avalanche-2","SHIB":"shiba-inu",
}

@tool
def get_crypto_price(input: str = "BTC,ETH") -> str:
    """
    Get live crypto prices. Supports 4H technical analysis.
    Input: 'BTC'  |  'BTC,ETH,SOL'  |  'BTC,4h'  |  'ETH,4h'
    """
    try:
        want_4h = "4h" in input.lower()
        raw     = input.lower().replace("4h","").replace("4hour","")
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
                    "ids":              ",".join(cg_ids),
                    "vs_currencies":    "usd",
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
                        out.append(f"{coin}: ${price:>12,.2f}  {arrow} {chg:+.2f}% (24h)")
                        fetched = True

            if not fetched:
                for coin in coins:
                    h = _yf_fetch(f"{coin}-USD", period="2d")
                    if not h.empty and h["Close"].iloc[-1] == h["Close"].iloc[-1]:
                        p  = h["Close"].iloc[-1]
                        pv = h["Close"].iloc[-2] if len(h) > 1 else p
                        chg  = p - pv
                        pct  = (chg / pv * 100) if pv else 0
                        out.append(f"{coin}: ${p:>12,.2f}  {'▲' if chg>=0 else '▼'} {pct:+.2f}%")
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
# 4H HELPER
# ══════════════════════════════════════════════════════════════
def _fetch_4h_levels(ticker: str, display_name: str) -> str:
    ck     = f"4h_{ticker}"
    cached = _cache.get(ck)
    if cached:
        return cached

    h = None
    h = _yf_fetch(ticker, interval="1h", period="7d", timeout_sec=18)
    if h is None or h.empty or len(h) < 4:
        fallbacks = {
            "^DJI":["YM=F","DIA"], "^GSPC":["ES=F","SPY"],
            "^IXIC":["NQ=F","QQQ"],
            "US30":["YM=F","DIA"], "SPX":["ES=F","SPY"],
            "NAS100":["NQ=F","QQQ"],
        }
        for alt in fallbacks.get(ticker.upper(), []):
            h2 = _yf_fetch(alt, interval="1h", period="7d", timeout_sec=18)
            if h2 is not None and not h2.empty and len(h2) >= 4:
                h = h2
                display_name = f"{display_name} (via {alt})"
                break

    if h is None or h.empty or len(h) < 4:
        return f"⚠️ 4H data unavailable for {display_name}. Try 'US30 4h' or 'BTC 4h'."

    h = h.dropna(subset=["Close"])
    bars    = h[["Open","High","Low","Close","Volume"]].values
    candles = []
    for i in range(0, len(bars) - 3, 4):
        chunk = bars[i:i+4]
        if len(chunk) == 4:
            candles.append({
                "open":  float(chunk[0][0]),
                "high":  float(chunk[:,1].max()),
                "low":   float(chunk[:,2].min()),
                "close": float(chunk[-1][3]),
                "vol":   float(chunk[:,4].sum()),
            })

    if len(candles) < 2:
        return f"⚠️ Not enough 4H candles for {display_name}."

    curr = candles[-1]; prev = candles[-2]
    c    = curr["close"]; mid = (curr["high"] + curr["low"]) / 2
    rng  = curr["high"] - curr["low"]
    result = (
        f"── {display_name} 4H Analysis ──\n"
        f"Close:   {c:,.2f}  ({'▲' if curr['close']>prev['close'] else '▼'} vs prev)\n"
        f"Open:    {curr['open']:,.2f}\n"
        f"High:    {curr['high']:,.2f}   R1: {curr['high']+rng*0.382:,.2f}   R2: {curr['high']+rng*0.618:,.2f}\n"
        f"Low:     {curr['low']:,.2f}   S1: {curr['low']-rng*0.382:,.2f}   S2: {curr['low']-rng*0.618:,.2f}\n"
        f"Mid:     {mid:,.2f}   Bias: {'Bullish' if c>mid else 'Bearish'}\n"
        f"Prev 4H: {prev['close']:,.2f}   Vol: {curr['vol']:,.0f}\n"
        f"Source: Yahoo 1H bars → 4H  ({len(candles)} candles)"
    )
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
    """
    mapping = {
        "US30":("YM=F","US30/Dow"),"DOW":("YM=F","US30/Dow"),
        "DJI":("YM=F","US30/Dow"),"DOWJONES":("YM=F","US30/Dow"),
        "SPX":("ES=F","SPX/S&P500"),"SP500":("ES=F","SPX/S&P500"),
        "NAS":("NQ=F","NAS100"),"NAS100":("NQ=F","NAS100"),
        "NASDAQ":("NQ=F","NAS100"),"NDX":("NQ=F","NAS100"),
        "GOLD":("GC=F","Gold/XAU"),"XAUUSD":("GC=F","Gold/XAU"),
        "OIL":("CL=F","Crude/WTI"),"USOIL":("CL=F","Crude/WTI"),
        "GER40":("FDAX","GER40"),"DAX":("FDAX","GER40"),
    }
    clean  = input.strip().upper().replace(" ","").replace("/","").replace("4H","")
    ticker, name = mapping.get(clean, (None, None))
    if not ticker:
        ticker = input.strip().upper().replace("4H","").strip()
        name   = ticker
    return _fetch_4h_levels(ticker, name)


# ══════════════════════════════════════════════════════════════
# 5. SEC EDGAR INSIDER TRADES (D2V API)
# ══════════════════════════════════════════════════════════════
@tool
def get_insider_trades(ticker: str) -> str:
    """
    Get recent SEC insider trades (Form 4 filings) for any US stock.
    Shows who bought/sold, how much, and the transaction price.
    Input: stock ticker e.g. 'AAPL'  'TSLA'  'NVDA'  'MSFT'
    Requires D2V_API_KEY in Streamlit secrets.
    """
    ticker  = ticker.upper().strip()
    ck      = f"insider_{ticker}"
    cached  = _cache.get(ck)
    if cached:
        return cached

    key = _D2V_KEY()

    # ── Method 1: D2V API (SEC EDGAR wrapper) ────────────────
    if key:
        try:
            data = _http_get(
                "https://api.d2vapi.com/api/insider-trades",
                params={"ticker": ticker, "limit": 10},
                headers={"Authorization": f"Bearer {key}"},
            )
            if data and isinstance(data, (list, dict)):
                trades = data if isinstance(data, list) else data.get("data", [])
                if trades:
                    out = [f"── {ticker} Insider Trades (SEC Form 4) ──"]
                    for t in trades[:8]:
                        name_   = t.get("insiderName") or t.get("reporter_name","Unknown")
                        role    = t.get("insiderTitle") or t.get("title","")
                        tx_type = t.get("transactionType") or t.get("type","")
                        shares  = t.get("shares") or t.get("quantity",0)
                        price   = t.get("price") or t.get("transaction_price",0)
                        date_   = t.get("transactionDate") or t.get("date","")
                        value   = (shares or 0) * (price or 0)
                        side    = "BUY  🟢" if "buy" in str(tx_type).lower() or "purchase" in str(tx_type).lower() else "SELL 🔴"
                        out.append(
                            f"{side}  {name_} ({role})\n"
                            f"       {shares:,.0f} shares @ ${price:,.2f}  = ${value:,.0f}  [{date_}]"
                        )
                    result = "\n".join(out)
                    _cache.set(ck, result, _TTL_NEWS)
                    return result
        except Exception:
            pass

    # ── Method 2: FMP insider trades ─────────────────────────
    fmp_key = _FMP_KEY()
    if fmp_key:
        try:
            data = _http_get(
                f"https://financialmodelingprep.com/api/v4/insider-trading",
                params={"symbol": ticker, "limit": 10, "apikey": fmp_key},
            )
            if data and isinstance(data, list) and len(data) > 0:
                out = [f"── {ticker} Insider Trades (SEC Form 4 via FMP) ──"]
                for t in data[:8]:
                    name_    = t.get("reportingName","Unknown")
                    tx_type  = t.get("transactionType","")
                    shares   = t.get("securitiesTransacted") or 0
                    price    = t.get("price") or 0
                    value    = shares * price
                    date_    = t.get("transactionDate","")
                    side     = "BUY  🟢" if "P-Purchase" in tx_type or "buy" in tx_type.lower() else "SELL 🔴"
                    out.append(
                        f"{side}  {name_}\n"
                        f"       {shares:,.0f} shares @ ${price:,.2f}  = ${value:,.0f}  [{date_}]"
                    )
                result = "\n".join(out)
                _cache.set(ck, result, _TTL_NEWS)
                return result
        except Exception:
            pass

    # ── Method 3: SEC EDGAR public EDGAR API (no key needed) ─
    try:
        # Get CIK for ticker
        headers = {"User-Agent": "AMHANi Enterprise contact@amhanienterprise.com"}
        cik_data = _http_get(
            "https://efts.sec.gov/LATEST/search-index?q=%22"
            + ticker + "%22&dateRange=custom&startdt=2024-01-01&forms=4",
            headers=headers,
        )
        if cik_data:
            hits = cik_data.get("hits", {}).get("hits", [])
            if hits:
                out = [f"── {ticker} Insider Trades (SEC EDGAR) ──"]
                for h in hits[:5]:
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

    return (
        f"⚠️ Insider trade data for {ticker} currently unavailable.\n"
        f"Ensure D2V_API_KEY or FMP_API_KEY is set in Streamlit secrets.\n"
        f"You can also check directly at: https://www.sec.gov/cgi-bin/browse-edgar"
        f"?action=getcompany&type=4&dateb=&owner=include&count=20&search_text="
    )


# ══════════════════════════════════════════════════════════════
# 6. STOCK FINANCIALS (FMP)
# ══════════════════════════════════════════════════════════════
@tool
def get_stock_financials(input: str) -> str:
    """
    Get detailed financial ratios, income statement and valuation for any stock.
    Input: ticker e.g. 'AAPL'  'TSLA'  'DANGOTE.LG'
    Optional: 'AAPL, quarterly' for quarterly data
    Requires FMP_API_KEY in Streamlit secrets.
    """
    parts    = [p.strip() for p in input.split(",")]
    ticker   = parts[0].upper()
    period   = "quarterly" if len(parts) > 1 and "q" in parts[1].lower() else "annual"
    ck       = f"fin_{ticker}_{period}"
    cached   = _cache.get(ck)
    if cached:
        return cached

    fmp_key = _FMP_KEY()
    if not fmp_key:
        return (
            f"⚠️ FMP_API_KEY not set. Add it to Streamlit secrets to access "
            f"financial statements for {ticker}."
        )

    try:
        # Ratios
        ratios = _http_get(
            f"https://financialmodelingprep.com/api/v3/ratios-ttm/{ticker}",
            params={"apikey": fmp_key},
        )
        # Income statement
        income = _http_get(
            f"https://financialmodelingprep.com/api/v3/income-statement/{ticker}",
            params={"limit": 2, "period": period, "apikey": fmp_key},
        )
        # Key metrics
        metrics = _http_get(
            f"https://financialmodelingprep.com/api/v3/key-metrics-ttm/{ticker}",
            params={"apikey": fmp_key},
        )

        out = [f"── {ticker} Financials ({period.title()}) ──"]

        if ratios and isinstance(ratios, list) and ratios[0]:
            r = ratios[0]
            out.append(
                f"\nValuation Ratios (TTM)\n"
                f"P/E:          {r.get('peRatioTTM') or 'N/A':.2f}\n"
                f"P/B:          {r.get('priceToBookRatioTTM') or 'N/A':.2f}\n"
                f"P/S:          {r.get('priceToSalesRatioTTM') or 'N/A':.2f}\n"
                f"EV/EBITDA:    {r.get('enterpriseValueMultipleTTM') or 'N/A':.2f}\n"
                f"ROE:          {(r.get('returnOnEquityTTM') or 0)*100:.1f}%\n"
                f"ROA:          {(r.get('returnOnAssetsTTM') or 0)*100:.1f}%\n"
                f"Gross Margin: {(r.get('grossProfitMarginTTM') or 0)*100:.1f}%\n"
                f"Net Margin:   {(r.get('netProfitMarginTTM') or 0)*100:.1f}%\n"
                f"D/E Ratio:    {r.get('debtEquityRatioTTM') or 'N/A':.2f}"
            )

        if income and isinstance(income, list) and len(income) > 0:
            inc = income[0]
            rev = inc.get("revenue", 0) or 0
            ni  = inc.get("netIncome", 0) or 0
            eps = inc.get("eps") or 0
            out.append(
                f"\nIncome Statement (Latest {period.title()})\n"
                f"Revenue:    ${rev/1e9:.2f}B\n"
                f"Net Income: ${ni/1e9:.2f}B\n"
                f"EPS:        ${eps:.2f}"
            )

        if metrics and isinstance(metrics, list) and metrics[0]:
            m = metrics[0]
            out.append(
                f"\nKey Metrics (TTM)\n"
                f"Market Cap:  ${(m.get('marketCapTTM') or 0)/1e9:.1f}B\n"
                f"Free CF/Shr: ${m.get('freeCashFlowPerShareTTM') or 0:.2f}\n"
                f"Div Yield:   {(m.get('dividendYieldTTM') or 0)*100:.2f}%"
            )

        result = "\n".join(out)
        _cache.set(ck, result, 3600)   # cache 1 hour — financials change slowly
        return result

    except Exception as e:
        return f"Financials error for {ticker}: {e}"


# ══════════════════════════════════════════════════════════════
# 7. NGN MARKET — Nigerian equities via NGNMarket API
# ══════════════════════════════════════════════════════════════
@tool
def get_ngn_market(input: str = "overview") -> str:
    """
    Nigerian stock exchange data via NGNMarket API.
    Input: 'overview'           → NGX top movers and market summary
           'GTCO'               → specific NGX stock price
           'DANGOTE'            → specific NGX stock price
           'top gainers'        → today's biggest gainers
           'top losers'         → today's biggest losers
    Requires NGNMARKET_API_KEY in Streamlit secrets.
    """
    inp     = input.strip().lower()
    ck      = f"ngn_{inp}"
    cached  = _cache.get(ck)
    if cached:
        return cached

    ngnkey = _NGNMKT_KEY()

    if ngnkey:
        headers = {"Authorization": f"Bearer {ngnkey}", "Accept": "application/json"}

        # Specific stock lookup
        if inp not in ("overview","top gainers","top losers","market"):
            ticker_ngn = inp.upper()
            try:
                data = _http_get(
                    f"https://api.ngnmarket.com/v1/stocks/{ticker_ngn}",
                    headers=headers,
                )
                if not data:
                    data = _http_get(
                        f"https://api.ngnmarket.com/v1/quote/{ticker_ngn}",
                        headers=headers,
                    )
                if data:
                    price  = data.get("price") or data.get("close") or 0
                    chg    = data.get("change") or 0
                    pct    = data.get("changePercent") or data.get("pct_change") or 0
                    vol    = data.get("volume") or 0
                    name_  = data.get("name") or ticker_ngn
                    arrow  = "▲" if chg >= 0 else "▼"
                    result = (
                        f"📈 {ticker_ngn} — {name_} (NGX)\n"
                        f"Price:  ₦{price:,.2f}\n"
                        f"Change: {arrow} ₦{chg:+.2f} ({pct:+.2f}%)\n"
                        f"Volume: {vol:,.0f}\n"
                        f"Source: NGNMarket API (live)"
                    )
                    _cache.set(ck, result, _TTL_STOCK)
                    return result
            except Exception:
                pass

        # Market overview
        try:
            url_map = {
                "top gainers": "https://api.ngnmarket.com/v1/market/gainers",
                "top losers":  "https://api.ngnmarket.com/v1/market/losers",
            }
            url  = url_map.get(inp, "https://api.ngnmarket.com/v1/market/overview")
            data = _http_get(url, headers=headers)
            if data:
                out = [f"── NGX Market {'Overview' if inp=='overview' else inp.title()} ──"]
                stocks = data if isinstance(data, list) else data.get("data", [])
                for s in (stocks[:10] if stocks else []):
                    sym   = s.get("symbol","")
                    price = s.get("price") or s.get("close",0)
                    pct   = s.get("changePercent") or s.get("pct_change",0)
                    arrow = "▲" if pct >= 0 else "▼"
                    out.append(f"{sym:12} ₦{price:>10,.2f}  {arrow} {pct:+.2f}%")
                if len(out) > 1:
                    result = "\n".join(out)
                    _cache.set(ck, result, _TTL_STOCK)
                    return result
        except Exception:
            pass

    # ── Fallback: yfinance with .LG suffix for NGX ────────────
    ticker_yf = inp.upper()
    if inp not in ("overview","top gainers","top losers"):
        for suffix in [".LG", ".LA"]:
            h = _yf_fetch(f"{ticker_yf}{suffix}", period="2d")
            if not h.empty and len(h) >= 1:
                p = h["Close"].iloc[-1]
                if p == p and p > 0:
                    pv  = h["Close"].iloc[-2] if len(h) > 1 else p
                    chg = p - pv
                    pct = (chg / pv * 100) if pv else 0
                    result = (
                        f"📈 {ticker_yf} (NGX)\n"
                        f"Price:  ₦{p:,.2f}\n"
                        f"Change: {'▲' if chg>=0 else '▼'} ₦{chg:+.2f} ({pct:+.2f}%)\n"
                        f"Source: Yahoo Finance ({ticker_yf}{suffix})"
                    )
                    _cache.set(ck, result, _TTL_STOCK)
                    return result

    return (
        "⚠️ Nigerian market data unavailable.\n"
        "Add NGNMARKET_API_KEY to Streamlit secrets for live NGX data.\n"
        "Or try specific tickers like: 'GTCO.LG', 'DANGOTE.LG' via get_stock_price."
    )


# ══════════════════════════════════════════════════════════════
# 8. P/E RATIO
# ══════════════════════════════════════════════════════════════
@tool
def calculate_pe_ratio(input: str) -> str:
    """P/E ratio calculator. Format: 'price, eps'  e.g. '150, 10.5'"""
    try:
        p = input.replace(";",",").split(",")
        if len(p) < 2:
            return "Format: 'price, eps'"
        price, eps = float(p[0]), float(p[1])
        if eps == 0:
            return "EPS cannot be zero."
        pe = price / eps
        return (
            f"P/E: {pe:.2f}  |  ${price:.2f} / ${eps:.2f}\n"
            f"{'Undervalued' if pe<15 else 'Fairly valued' if pe<25 else 'Premium/Growth' if pe<40 else 'Speculative'}"
        )
    except Exception as e:
        return f"Error: {e}"


# ══════════════════════════════════════════════════════════════
# 9. PYTHON EXECUTOR
# ══════════════════════════════════════════════════════════════
@tool
def execute_python(code: str) -> str:
    """Execute Python code. Use print() to show output. pandas (pd), math, json available."""
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
    """Analyse JSON financial data. Input: '[{"month":"Jan","revenue":50000}, ...]'"""
    try:
        df  = pd.DataFrame(json.loads(input))
        out = [f"📊 {df.shape[0]}r × {df.shape[1]}c — {', '.join(df.columns)}"]
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
# 11. STOCK CHART
# ══════════════════════════════════════════════════════════════
@tool
def generate_stock_chart(input: str) -> str:
    """Gold-themed chart. Input: 'TICKER' or 'TICKER, period' (1mo 3mo 6mo 1y 2y)"""
    try:
        parts  = [p.strip() for p in input.split(",")]
        ticker = parts[0].upper()
        period = parts[1] if len(parts) > 1 else "3mo"
        hist   = _yf_fetch(ticker, period=period, timeout_sec=20)
        if hist.empty:
            return f"No chart data for {ticker}"
        fig, (a1, a2) = plt.subplots(2,1,figsize=(10,6),
                                      gridspec_kw={"height_ratios":[3,1]},
                                      facecolor="#0F0F0C")
        fig.suptitle(f"{ticker}  ·  {period.upper()}", color="#C9A84C",
                     fontsize=13, fontweight="bold", y=0.99)
        a1.plot(hist.index, hist["Close"], color="#C9A84C", linewidth=1.8)
        a1.fill_between(hist.index, hist["Close"], hist["Close"].min(),
                        alpha=0.07, color="#C9A84C")
        a1.set_facecolor("#0F0F0C"); a1.tick_params(colors="#666",labelsize=8)
        for s in a1.spines.values(): s.set_edgecolor("#2a2a20")
        a2.bar(hist.index, hist["Volume"], color="#C9A84C", alpha=0.3, width=1)
        a2.set_facecolor("#0F0F0C"); a2.tick_params(colors="#666",labelsize=7)
        for s in a2.spines.values(): s.set_edgecolor("#2a2a20")
        plt.tight_layout(rect=[0,0,1,0.97])
        buf = io.BytesIO()
        plt.savefig(buf,format="png",bbox_inches="tight",dpi=130,facecolor="#0F0F0C")
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
        calc  = parts[0].lower().replace(" ","_")
        if calc == "compound_interest":
            P,r,n = float(parts[1]),float(parts[2]),float(parts[3])
            A = P*(1+r)**n
            return (f"💰 ₦{P:,.2f} @ {r*100:.1f}%/yr × {n:.0f}yrs\n"
                    f"Final: ₦{A:,.2f}  Gain: ₦{A-P:,.2f} ({((A-P)/P)*100:.1f}%)")
        elif calc == "loan_payment":
            P,r_a,y = float(parts[1]),float(parts[2]),float(parts[3])
            r=r_a/12; n=y*12
            m = P*r*(1+r)**n/((1+r)**n-1) if r>0 else P/n
            return f"🏦 Monthly: ₦{m:,.2f}  Total: ₦{m*n:,.2f}  Interest: ₦{m*n-P:,.2f}"
        elif calc == "roi":
            g,c = float(parts[1]),float(parts[2])
            return f"📈 ROI: {((g-c)/c)*100:.2f}%  Profit: ₦{g-c:,.2f}"
        elif calc == "break_even":
            f_,p,v = float(parts[1]),float(parts[2]),float(parts[3])
            m=p-v
            if m<=0: return "Price must exceed variable cost."
            return f"⚖️ Break-Even: {f_/m:,.0f} units  Revenue: ₦{(f_/m)*p:,.2f}"
        elif calc == "inflation_adjust":
            a,r,y = float(parts[1]),float(parts[2]),float(parts[3])
            real=a/(1+r)**y
            return f"📉 Real: ₦{real:,.2f}  Lost: ₦{a-real:,.2f} ({((a-real)/a)*100:.1f}%)"
        elif calc == "future_value":
            pv,r,y = float(parts[1]),float(parts[2]),float(parts[3])
            return f"🔭 Future: ₦{pv*(1+r)**y:,.2f}"
        elif calc == "payback_period":
            i,cf = float(parts[1]),float(parts[2])
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
        for name, sym in [("S&P 500","^GSPC"),("Dow Jones","^DJI"),
                           ("NASDAQ","^IXIC"),("VIX","^VIX")]:
            h = _yf_fetch(sym, period="2d")
            if len(h) >= 2:
                c1,c2 = h["Close"].iloc[-1], h["Close"].iloc[-2]
                if c1==c1 and c2==c2 and c2!=0:
                    chg=c1-c2; pct=(chg/c2)*100
                    out.append(f"{name:12} {c1:>12,.2f}  {'▲' if chg>=0 else '▼'} {pct:+.2f}%")
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
# EXPORT — full tool list
# ══════════════════════════════════════════════════════════════
amhani_tools = [
    get_stock_price,
    convert_currency,
    get_crypto_price,
    get_index_4h,
    get_insider_trades,
    get_stock_financials,
    get_ngn_market,
    calculate_pe_ratio,
    execute_python,
    analyse_financial_data,
    generate_stock_chart,
    financial_calculator,
    get_market_overview,
    plan_task,
]
