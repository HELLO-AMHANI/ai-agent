# =============================================================
# tools.py — AMHANi ENTERPRISE · Full Agentic Tools
# All bugs fixed: duplicate tools removed, NaN guard added,
# imports consolidated at top
# =============================================================

import io
import os
import sys
import json
import math
import time
import base64
import traceback
import requests
from datetime import datetime

import yfinance as yf
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from langchain.tools import tool


# ══════════════════════════════════════════════════════════════
# 1. STOCK PRICE — with automatic fallback
# ══════════════════════════════════════════════════════════════
@tool
def get_stock_price(ticker: str) -> str:
    """
    Get current stock price for a ticker symbol.
    Tries fast_info first (least rate-limited), then history.
    Input: ticker e.g. 'AAPL', 'TSLA', 'DANGOTE.LG'
    """
    ticker = ticker.upper().strip()

    # Method 1 — fast_info (lightest call)
    try:
        fi    = yf.Ticker(ticker).fast_info
        price = fi.last_price
        prev  = fi.previous_close or price

        # Guard against NaN
        if price and price == price and price > 0:
            chg = price - prev
            pct = (chg / prev * 100) if prev else 0
            return (
                f"📈 {ticker}\n"
                f"Price:  ${price:.2f}\n"
                f"Change: {'+' if chg >= 0 else ''}{chg:.2f} ({pct:+.2f}%)\n"
                f"High:   ${fi.day_high:.2f}\n"
                f"Low:    ${fi.day_low:.2f}\n"
                f"Source: Yahoo Finance (live)"
            )
    except Exception:
        pass

    # Method 2 — history with delay
    try:
        time.sleep(1.5)
        hist = yf.Ticker(ticker).history(period="2d")
        if not hist.empty:
            latest = hist.iloc[-1]
            prev   = hist.iloc[-2] if len(hist) > 1 else latest
            chg    = latest["Close"] - prev["Close"]
            pct    = (chg / prev["Close"] * 100) if prev["Close"] else 0
            return (
                f"📈 {ticker}\n"
                f"Price:  ${latest['Close']:.2f}\n"
                f"Change: {'+' if chg >= 0 else ''}{chg:.2f} ({pct:+.2f}%)\n"
                f"High:   ${latest['High']:.2f}\n"
                f"Low:    ${latest['Low']:.2f}\n"
                f"Source: Yahoo Finance (delayed)"
            )
    except Exception:
        pass

    return (
        f"⚠️ Live price for {ticker} is temporarily unavailable due to "
        f"data provider rate limits. Please try again in 60 seconds, "
        f"or visit finance.yahoo.com/quote/{ticker} directly."
    )


# ══════════════════════════════════════════════════════════════
# 2. CURRENCY CONVERTER — single clean definition
# ══════════════════════════════════════════════════════════════
@tool
def convert_currency(input: str) -> str:
    """
    Convert between currencies using live exchange rates.
    Input format: 'amount, FROM, TO'
    Examples: '1500, USD, NGN'  or  '50000, NGN, USD'
    Supported: USD, NGN, GBP, EUR, JPY, CAD, AUD, CNY, ZAR, GHS, KES
    """
    try:
        parts  = [p.strip() for p in input.split(",")]
        amount = float(parts[0])
        frm    = parts[1].upper()
        to     = parts[2].upper()

        # Method 1 — free ExchangeRate-API (no key required)
        try:
            url  = f"https://open.er-api.com/v6/latest/{frm}"
            resp = requests.get(url, timeout=8)
            data = resp.json()
            if data.get("result") == "success":
                rate = data["rates"].get(to)
                if rate:
                    converted = amount * rate
                    return (
                        f"💱 Currency Conversion\n"
                        f"{amount:,.2f} {frm} = {converted:,.2f} {to}\n"
                        f"Rate: 1 {frm} = {rate:,.4f} {to}\n"
                        f"Source: ExchangeRate-API (live)"
                    )
        except Exception:
            pass

        # Method 2 — yfinance forex pair fallback
        try:
            pair = f"{frm}{to}=X"
            time.sleep(1)
            hist = yf.Ticker(pair).history(period="2d")
            if not hist.empty:
                rate      = hist["Close"].iloc[-1]
                converted = amount * rate
                return (
                    f"💱 Currency Conversion\n"
                    f"{amount:,.2f} {frm} = {converted:,.2f} {to}\n"
                    f"Rate: 1 {frm} = {rate:,.4f} {to}\n"
                    f"Source: Yahoo Finance (delayed)"
                )
        except Exception:
            pass

        # Method 3 — approximate hardcoded NGN rates (last resort)
        ngn_rates = {
            "USD": 1620, "GBP": 2050, "EUR": 1750,
            "CAD": 1190, "AUD": 1040, "CNY": 223,
            "ZAR": 88,   "GHS": 110,  "KES": 12.5,
        }
        if to == "NGN" and frm in ngn_rates:
            rate   = ngn_rates[frm]
            result = amount * rate
            return (
                f"💱 Currency Conversion (estimated)\n"
                f"{amount:,.2f} {frm} ≈ ₦{result:,.2f}\n"
                f"Rate used: ₦{rate:,.0f} per {frm}\n"
                f"⚠️ Approximate rate — verify with your bank."
            )
        elif frm == "NGN" and to in ngn_rates:
            rate   = ngn_rates[to]
            result = amount / rate
            return (
                f"💱 Currency Conversion (estimated)\n"
                f"₦{amount:,.2f} ≈ {result:,.4f} {to}\n"
                f"Rate used: ₦{rate:,.0f} per {to}\n"
                f"⚠️ Approximate rate — verify with your bank."
            )

        return f"⚠️ Could not fetch rate for {frm}→{to}. Try again shortly."

    except IndexError:
        return "Format: 'amount, FROM, TO'  e.g. '1500, USD, NGN'"
    except Exception as e:
        return f"Conversion error: {e}"


# ══════════════════════════════════════════════════════════════
# 3. CRYPTO PRICE — with NaN guard and 4H support
# ══════════════════════════════════════════════════════════════
@tool
def get_crypto_price(input: str = "BTC,ETH") -> str:
    """
    Get live crypto prices with automatic fallback.
    Input: comma-separated symbols e.g. 'BTC,ETH,BNB'
    For 4-hour level analysis append 4h: 'BTC,4h'
    Examples: 'BTC'  'BTC,ETH'  'BTC,4h'
    """
    try:
        want_4h = "4h" in input.lower() or "4hour" in input.lower()
        raw     = input.lower().replace("4h", "").replace("4hour", "")
        coins   = [c.strip().upper() for c in raw.split(",") if c.strip()]
        if not coins:
            coins = ["BTC"]

        out = ["── Crypto Prices ──"]

        for coin in coins:
            sym = f"{coin}-USD"

            # Method 1 — fast_info with NaN guard
            try:
                fi    = yf.Ticker(sym).fast_info
                price = fi.last_price
                prev  = fi.previous_close

                # Explicit NaN check — NaN != NaN in Python
                if price and price == price and prev and prev == prev and price > 0:
                    chg   = price - prev
                    pct   = (chg / prev * 100) if prev else 0
                    arrow = "▲" if chg >= 0 else "▼"
                    out.append(f"{coin}: ${price:>12,.2f}  {arrow} {pct:+.2f}%")
                    continue
            except Exception:
                pass

            # Method 2 — history fallback
            try:
                time.sleep(1)
                h = yf.Ticker(sym).history(period="2d")
                if not h.empty and len(h) >= 1:
                    price = h["Close"].iloc[-1]
                    prev  = h["Close"].iloc[-2] if len(h) > 1 else price
                    # NaN guard
                    if price == price and prev == prev:
                        chg   = price - prev
                        pct   = (chg / prev * 100) if prev else 0
                        arrow = "▲" if chg >= 0 else "▼"
                        out.append(f"{coin}: ${price:>12,.2f}  {arrow} {pct:+.2f}%")
                        continue
            except Exception:
                pass

            out.append(f"{coin}: data temporarily unavailable — try again shortly")

        # 4-hour BTC analysis
        if want_4h and "BTC" in coins:
            try:
                time.sleep(1.5)
                hist = yf.Ticker("BTC-USD").history(interval="1h", period="2d")
                if not hist.empty and len(hist) >= 4:
                    recent = hist.tail(4)
                    high4h = recent["High"].max()
                    low4h  = recent["Low"].min()
                    close  = recent["Close"].iloc[-1]
                    mid    = (high4h + low4h) / 2
                    bias   = "Bullish" if close > mid else "Bearish"
                    side   = "above" if close > mid else "below"
                    out.append(f"\n── BTC 4-Hour Levels ──")
                    out.append(f"Current:  ${close:,.2f}")
                    out.append(f"4H High:  ${high4h:,.2f}")
                    out.append(f"4H Low:   ${low4h:,.2f}")
                    out.append(f"Midpoint: ${mid:,.2f}")
                    out.append(f"Bias:     {bias} (price {side} midpoint)")
            except Exception:
                out.append("\n⚠️ 4H level data temporarily unavailable")

        return "\n".join(out)

    except Exception as e:
        return f"Crypto data error: {e}"


# ══════════════════════════════════════════════════════════════
# 4. P/E RATIO CALCULATOR
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
            return "Provide both price and EPS: 'price, eps'  e.g. '150, 10.5'"
        price = float(parts[0].strip())
        eps   = float(parts[1].strip())
        if eps == 0:
            return "EPS cannot be zero — P/E ratio is undefined."
        pe = price / eps
        verdict = (
            "Potentially undervalued (below market average)" if pe < 15 else
            "Fairly valued (within market average range)"   if pe < 25 else
            "Premium / Growth stock"                        if pe < 40 else
            "Highly speculative — review carefully"
        )
        return (
            f"P/E Ratio:   {pe:.2f}\n"
            f"Price:       ${price:.2f}\n"
            f"EPS:         ${eps:.2f}\n"
            f"Assessment:  {verdict}"
        )
    except Exception as e:
        return f"Error: {e}. Use format: 'price, eps'  e.g. '150, 10.5'"


# ══════════════════════════════════════════════════════════════
# 5. PYTHON CODE EXECUTOR
# ══════════════════════════════════════════════════════════════
@tool
def execute_python(code: str) -> str:
    """
    Write AND execute Python code to solve financial problems.
    Use for: calculations, loops, data processing, logic, analysis.
    Available: pandas (pd), json, math, datetime.
    Always use print() to show results — output is captured.
    """
    old_stdout = sys.stdout
    sys.stdout = buffer = io.StringIO()
    result = ""
    try:
        namespace = {"pd": pd, "json": json, "math": math, "datetime": datetime}
        exec(compile(code, "<amhani_exec>", "exec"), namespace)
        result = buffer.getvalue()
        if not result.strip():
            result = "Code executed successfully. No print() output was produced."
    except Exception:
        result = f"Execution Error:\n{traceback.format_exc()}"
    finally:
        sys.stdout = old_stdout
    return result[:4000]


# ══════════════════════════════════════════════════════════════
# 6. FINANCIAL DATA ANALYSER
# ══════════════════════════════════════════════════════════════
@tool
def analyse_financial_data(input: str) -> str:
    """
    Analyse financial data supplied as a JSON string.
    Input: JSON array of records e.g.
    '[{"month":"Jan","revenue":50000,"expenses":30000}, ...]'
    Returns: summary stats, period growth, profit analysis.
    """
    try:
        data = json.loads(input)
        df   = pd.DataFrame(data)
        out  = []
        out.append(f"📊 Dataset: {df.shape[0]} rows × {df.shape[1]} columns")
        out.append(f"Columns: {', '.join(df.columns.tolist())}\n")
        numeric = df.select_dtypes(include="number")
        if not numeric.empty:
            out.append("── Summary Statistics ──")
            out.append(numeric.describe().round(2).to_string())
            out.append("\n── Period-over-Period Growth ──")
            for col in numeric.columns:
                if len(df) > 1:
                    first = df[col].iloc[0]
                    last  = df[col].iloc[-1]
                    if first != 0:
                        g = ((last - first) / abs(first)) * 100
                        out.append(f"{col}: {g:+.1f}%  ({first:,.0f} → {last:,.0f})")
        lower = {c.lower(): c for c in df.columns}
        if "revenue" in lower and "expenses" in lower:
            rev = lower["revenue"]
            exp = lower["expenses"]
            df["__profit__"] = df[rev] - df[exp]
            total  = df["__profit__"].sum()
            margin = (total / df[rev].sum()) * 100 if df[rev].sum() != 0 else 0
            out.append("\n── Profit Analysis ──")
            out.append(f"Total Profit:   {total:,.2f}")
            out.append(f"Profit Margin:  {margin:.1f}%")
            out.append(f"Best Period:    Row {df['__profit__'].idxmax()}")
            out.append(f"Worst Period:   Row {df['__profit__'].idxmin()}")
        return "\n".join(out)
    except json.JSONDecodeError:
        return 'Invalid JSON. Format: [{"col1": value, "col2": value}, ...]'
    except Exception as e:
        return f"Analysis error: {e}"


# ══════════════════════════════════════════════════════════════
# 7. STOCK CHART GENERATOR
# ══════════════════════════════════════════════════════════════
@tool
def generate_stock_chart(input: str) -> str:
    """
    Generate a gold-themed price + volume chart for a stock.
    Input: 'TICKER' or 'TICKER, period'
    Valid periods: 1mo  3mo  6mo  1y  2y
    Example: 'AAPL, 6mo'
    Returns base64 PNG prefixed with CHART_BASE64: for inline rendering.
    """
    try:
        parts  = [p.strip() for p in input.split(",")]
        ticker = parts[0].upper()
        period = parts[1] if len(parts) > 1 else "3mo"
        hist   = yf.Ticker(ticker).history(period=period)
        if hist.empty:
            return f"No chart data available for {ticker}"

        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(10, 6),
            gridspec_kw={"height_ratios": [3, 1]},
            facecolor="#0F0F0C",
        )
        fig.suptitle(f"{ticker}  ·  {period.upper()}", color="#C9A84C", fontsize=13, fontweight="bold", y=0.99)
        ax1.plot(hist.index, hist["Close"], color="#C9A84C", linewidth=1.8)
        ax1.fill_between(hist.index, hist["Close"], hist["Close"].min(), alpha=0.07, color="#C9A84C")
        ax1.set_facecolor("#0F0F0C")
        ax1.tick_params(colors="#666", labelsize=8)
        ax1.set_ylabel("Price (USD)", color="#888", fontsize=8)
        for spine in ax1.spines.values():
            spine.set_edgecolor("#2a2a20")
        ax2.bar(hist.index, hist["Volume"], color="#C9A84C", alpha=0.3, width=1)
        ax2.set_facecolor("#0F0F0C")
        ax2.tick_params(colors="#666", labelsize=7)
        ax2.set_ylabel("Volume", color="#888", fontsize=8)
        for spine in ax2.spines.values():
            spine.set_edgecolor("#2a2a20")
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
    Run common financial calculations.
    Format: 'TYPE, param1, param2, ...'

    Types:
      compound_interest  principal, rate(decimal), years
      loan_payment       principal, annual_rate(decimal), years
      roi                return_amount, cost_amount
      break_even         fixed_costs, price_per_unit, variable_cost_per_unit
      inflation_adjust   amount, rate(decimal), years
      future_value       present_value, rate(decimal), years
      payback_period     initial_investment, annual_cashflow

    Examples:
      'compound_interest, 500000, 0.15, 5'
      'roi, 750000, 500000'
      'break_even, 200000, 5000, 2000'
    """
    try:
        parts = [p.strip() for p in input.split(",")]
        calc  = parts[0].lower().replace(" ", "_")

        if calc == "compound_interest":
            P, r, n = float(parts[1]), float(parts[2]), float(parts[3])
            A = P * (1 + r) ** n
            return (f"💰 Compound Interest\nPrincipal: ₦{P:,.2f}\nRate: {r*100:.1f}%/yr\n"
                    f"Years: {n:.0f}\nFinal: ₦{A:,.2f}\nGain: ₦{A-P:,.2f} ({((A-P)/P)*100:.1f}%)")

        elif calc == "loan_payment":
            P, r_a, y = float(parts[1]), float(parts[2]), float(parts[3])
            r = r_a / 12; n = y * 12
            monthly = P * r * (1+r)**n / ((1+r)**n - 1) if r > 0 else P / n
            total   = monthly * n
            return (f"🏦 Loan Payment\nPrincipal: ₦{P:,.2f}\nRate: {r_a*100:.1f}%/yr\n"
                    f"Term: {y:.0f} yrs\nMonthly: ₦{monthly:,.2f}\n"
                    f"Total Repaid: ₦{total:,.2f}\nInterest: ₦{total-P:,.2f}")

        elif calc == "roi":
            gain, cost = float(parts[1]), float(parts[2])
            if cost == 0: return "Cost cannot be zero."
            roi = ((gain - cost) / cost) * 100
            return (f"📈 ROI\nInvestment: ₦{cost:,.2f}\nReturn: ₦{gain:,.2f}\n"
                    f"ROI: {roi:.2f}%\nProfit: ₦{gain-cost:,.2f}")

        elif calc == "break_even":
            fixed, price, variable = float(parts[1]), float(parts[2]), float(parts[3])
            m = price - variable
            if m <= 0: return "Price must exceed variable cost."
            units = fixed / m
            return (f"⚖️ Break-Even\nFixed: ₦{fixed:,.2f}\nPrice/Unit: ₦{price:,.2f}\n"
                    f"Variable/Unit: ₦{variable:,.2f}\nMargin: ₦{m:,.2f}\n"
                    f"Units: {units:,.0f}\nRevenue: ₦{units*price:,.2f}")

        elif calc == "inflation_adjust":
            amount, rate, years = float(parts[1]), float(parts[2]), float(parts[3])
            real = amount / (1 + rate) ** years
            return (f"📉 Inflation Adjust\nNominal: ₦{amount:,.2f}\nRate: {rate*100:.1f}%/yr\n"
                    f"Years: {years:.0f}\nReal Value: ₦{real:,.2f}\nLost: ₦{amount-real:,.2f}")

        elif calc == "future_value":
            pv, rate, years = float(parts[1]), float(parts[2]), float(parts[3])
            fv = pv * (1 + rate) ** years
            return (f"🔭 Future Value\nPresent: ₦{pv:,.2f}\nRate: {rate*100:.1f}%/yr\n"
                    f"Years: {years:.0f}\nFuture: ₦{fv:,.2f}")

        elif calc == "payback_period":
            invest, cf = float(parts[1]), float(parts[2])
            if cf <= 0: return "Cashflow must be positive."
            return (f"⏱️ Payback Period\nInvestment: ₦{invest:,.2f}\n"
                    f"Annual CF: ₦{cf:,.2f}\nPayback: {invest/cf:.2f} years")

        else:
            return (f"Unknown type: '{calc}'. Supported: compound_interest, loan_payment, "
                    f"roi, break_even, inflation_adjust, future_value, payback_period")

    except IndexError:
        return "Not enough parameters. Check the format in the tool description."
    except Exception as e:
        return f"Calculator error: {e}"


# ══════════════════════════════════════════════════════════════
# 9. MARKET OVERVIEW — with NaN guard on crypto
# ══════════════════════════════════════════════════════════════
@tool
def get_market_overview(input: str = "all") -> str:
    """
    Live snapshot of global indices and crypto.
    Input: 'all', 'indices', or 'crypto'
    """
    try:
        out = []

        if input.lower() in ("all", "indices"):
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
                        c1  = h["Close"].iloc[-1]
                        c2  = h["Close"].iloc[-2]
                        # NaN guard
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

        if input.lower() in ("all", "crypto"):
            crypto = {
                "Bitcoin":  "BTC-USD",
                "Ethereum": "ETH-USD",
                "BNB":      "BNB-USD",
            }
            out.append("\n── Crypto ──")
            for name, sym in crypto.items():
                fetched = False

                # Method 1 — fast_info with NaN guard
                try:
                    fi    = yf.Ticker(sym).fast_info
                    price = fi.last_price
                    prev  = fi.previous_close
                    if price and price == price and prev and prev == prev and price > 0:
                        chg   = price - prev
                        pct   = (chg / prev * 100) if prev else 0
                        arrow = "▲" if chg >= 0 else "▼"
                        out.append(f"{name:10} ${price:>12,.2f}  {arrow} {pct:+.2f}%")
                        fetched = True
                except Exception:
                    pass

                # Method 2 — history fallback
                if not fetched:
                    try:
                        time.sleep(0.8)
                        h = yf.Ticker(sym).history(period="2d")
                        if len(h) >= 2:
                            c1 = h["Close"].iloc[-1]
                            c2 = h["Close"].iloc[-2]
                            if c1 == c1 and c2 == c2 and c2 != 0:
                                chg   = c1 - c2
                                pct   = (chg / c2) * 100
                                arrow = "▲" if chg >= 0 else "▼"
                                out.append(f"{name:10} ${c1:>12,.2f}  {arrow} {pct:+.2f}%")
                                fetched = True
                    except Exception:
                        pass

                if not fetched:
                    out.append(f"{name:10}  temporarily unavailable")

        return "\n".join(out) if out else "Market data temporarily unavailable."

    except Exception as e:
        return f"Market overview error: {e}"


# ══════════════════════════════════════════════════════════════
# 10. TASK PLANNER
# ══════════════════════════════════════════════════════════════
@tool
def plan_task(goal: str) -> str:
    """
    Break a complex financial goal into a step-by-step execution plan.
    Use this FIRST for multi-step or complex requests.
    Input: plain description of what the user wants to accomplish.
    """
    return (
        f"📋 Plan for: {goal}\n\n"
        "Step 1 — Clarify the objective and identify any missing inputs\n"
        "Step 2 — Determine which data sources or tools are needed\n"
        "Step 3 — Gather required data (prices, financials, user inputs)\n"
        "Step 4 — Perform calculations or analysis\n"
        "Step 5 — Validate results for accuracy\n"
        "Step 6 — Summarise with a clear, actionable recommendation\n\n"
        "Proceeding with execution..."
    )


# ══════════════════════════════════════════════════════════════
# EXPORT — import this in agent.py
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
