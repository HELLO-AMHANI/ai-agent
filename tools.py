# =============================================================
# tools.py — AMHANi ENTERPRISE · Full Agentic Tools
# FILE 2 OF 7 — FULL REPLACEMENT
# Delete everything in your existing tools.py and paste this.
# =============================================================

import io
import os
import sys
import json
import math
import base64
import traceback
from datetime import datetime

import yfinance as yf
import pandas as pd

import matplotlib
matplotlib.use("Agg")           # Must be set before importing pyplot
import matplotlib.pyplot as plt

from langchain.tools import tool


# ══════════════════════════════════════════════════════════════
# 1. STOCK PRICE
# ══════════════════════════════════════════════════════════════
@tool
def get_stock_price(ticker: str) -> str:
    """
    Get the current stock price and a 5-day summary for a given
    ticker symbol.  Input: ticker string e.g. 'AAPL' or 'TSLA'.
    """
    try:
        ticker = ticker.upper().strip()
        stock  = yf.Ticker(ticker)
        hist   = stock.history(period="5d")
        info   = stock.info

        if hist.empty:
            return f"No price data found for ticker: {ticker}"

        latest = hist.iloc[-1]
        prev   = hist.iloc[-2] if len(hist) > 1 else latest
        change = latest["Close"] - prev["Close"]
        pct    = (change / prev["Close"]) * 100 if prev["Close"] != 0 else 0

        return (
            f"📈 {ticker} — {info.get('shortName', ticker)}\n"
            f"Price:      ${latest['Close']:.2f}\n"
            f"Change:     {'+' if change >= 0 else ''}{change:.2f} "
            f"({pct:+.2f}%)\n"
            f"Open:       ${latest['Open']:.2f}\n"
            f"High:       ${latest['High']:.2f}\n"
            f"Low:        ${latest['Low']:.2f}\n"
            f"Volume:     {int(latest['Volume']):,}\n"
            f"Market Cap: ${info.get('marketCap', 0):,}\n"
            f"Sector:     {info.get('sector', 'N/A')}"
        )
    except Exception as e:
        return f"Error fetching {ticker}: {e}"


# ══════════════════════════════════════════════════════════════
# 2. P/E RATIO CALCULATOR
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
        if pe < 15:
            verdict = "Potentially undervalued (below market average)"
        elif pe < 25:
            verdict = "Fairly valued (within market average range)"
        elif pe < 40:
            verdict = "Premium / Growth stock"
        else:
            verdict = "Highly speculative — review carefully before investing"

        return (
            f"P/E Ratio:   {pe:.2f}\n"
            f"Price:       ${price:.2f}\n"
            f"EPS:         ${eps:.2f}\n"
            f"Assessment:  {verdict}"
        )
    except Exception as e:
        return f"Error: {e}. Use format: 'price, eps'  e.g. '150, 10.5'"


# ══════════════════════════════════════════════════════════════
# 3. PYTHON CODE EXECUTOR
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
        namespace = {
            "pd":       pd,
            "json":     json,
            "math":     math,
            "datetime": datetime,
        }
        exec(compile(code, "<amhani_exec>", "exec"), namespace)
        result = buffer.getvalue()
        if not result.strip():
            result = "Code executed successfully. No print() output was produced."
    except Exception:
        result = f"Execution Error:\n{traceback.format_exc()}"
    finally:
        sys.stdout = old_stdout

    return result[:4000]   # Cap to avoid token overflow


# ══════════════════════════════════════════════════════════════
# 4. FINANCIAL DATA ANALYSER
# ══════════════════════════════════════════════════════════════
@tool
def analyse_financial_data(input: str) -> str:
    """
    Analyse financial data supplied as a JSON string.
    Input: JSON array of records, e.g.
    '[{"month":"Jan","revenue":50000,"expenses":30000}, ...]'
    Returns: summary statistics, period growth, profit analysis.
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
                        out.append(
                            f"{col}: {g:+.1f}%  "
                            f"({first:,.0f} → {last:,.0f})"
                        )

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
        return (
            "Invalid JSON. Required format:\n"
            '[{"col1": value, "col2": value}, ...]'
        )
    except Exception as e:
        return f"Analysis error: {e}"


# ══════════════════════════════════════════════════════════════
# 5. STOCK CHART GENERATOR
# ══════════════════════════════════════════════════════════════
@tool
def generate_stock_chart(input: str) -> str:
    """
    Generate a gold-themed price + volume chart for a stock.
    Input: 'TICKER' or 'TICKER, period'
    Valid periods: 1mo  3mo  6mo  1y  2y
    Example: 'AAPL, 6mo'
    Returns a base64 PNG string prefixed with CHART_BASE64:
    The UI will automatically render this as an image.
    """
    try:
        parts  = [p.strip() for p in input.split(",")]
        ticker = parts[0].upper()
        period = parts[1] if len(parts) > 1 else "3mo"

        stock = yf.Ticker(ticker)
        hist  = stock.history(period=period)

        if hist.empty:
            return f"No chart data available for {ticker}"

        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(10, 6),
            gridspec_kw={"height_ratios": [3, 1]},
            facecolor="#0F0F0C",
        )
        fig.suptitle(
            f"{ticker}  ·  {period.upper()}",
            color="#C9A84C", fontsize=13, fontweight="bold", y=0.99,
        )

        # Price line + fill
        ax1.plot(hist.index, hist["Close"], color="#C9A84C", linewidth=1.8)
        ax1.fill_between(
            hist.index, hist["Close"], hist["Close"].min(),
            alpha=0.07, color="#C9A84C",
        )
        ax1.set_facecolor("#0F0F0C")
        ax1.tick_params(colors="#666", labelsize=8)
        ax1.set_ylabel("Price (USD)", color="#888", fontsize=8)
        for spine in ax1.spines.values():
            spine.set_edgecolor("#2a2a20")

        # Volume bars
        ax2.bar(hist.index, hist["Volume"], color="#C9A84C", alpha=0.3, width=1)
        ax2.set_facecolor("#0F0F0C")
        ax2.tick_params(colors="#666", labelsize=7)
        ax2.set_ylabel("Volume", color="#888", fontsize=8)
        for spine in ax2.spines.values():
            spine.set_edgecolor("#2a2a20")

        plt.tight_layout(rect=[0, 0, 1, 0.97])

        buf = io.BytesIO()
        plt.savefig(
            buf, format="png", bbox_inches="tight",
            dpi=130, facecolor="#0F0F0C",
        )
        plt.close(fig)
        buf.seek(0)
        encoded = base64.b64encode(buf.read()).decode()
        return f"CHART_BASE64:{encoded}"

    except Exception as e:
        return f"Chart generation error: {e}"


# ══════════════════════════════════════════════════════════════
# 6. FINANCIAL CALCULATOR
# ══════════════════════════════════════════════════════════════
@tool
def financial_calculator(input: str) -> str:
    """
    Run common financial calculations.
    Format: 'TYPE, param1, param2, param3'

    Supported calculation types:
      compound_interest  principal, rate(decimal), years
      loan_payment       principal, annual_rate(decimal), years
      roi                return_amount, cost_amount
      break_even         fixed_costs, price_per_unit, variable_cost_per_unit
      inflation_adjust   amount, inflation_rate(decimal), years
      future_value       present_value, rate(decimal), years
      payback_period     initial_investment, annual_cashflow

    Examples:
      'compound_interest, 500000, 0.15, 5'
      'loan_payment, 2000000, 0.22, 3'
      'roi, 750000, 500000'
      'break_even, 200000, 5000, 2000'
    """
    try:
        parts = [p.strip() for p in input.split(",")]
        calc  = parts[0].lower().replace(" ", "_")

        if calc == "compound_interest":
            P, r, n = float(parts[1]), float(parts[2]), float(parts[3])
            A = P * (1 + r) ** n
            return (
                f"💰 Compound Interest\n"
                f"Principal:     ₦{P:,.2f}\n"
                f"Rate:          {r * 100:.1f}% per year\n"
                f"Years:         {n:.0f}\n"
                f"Final Amount:  ₦{A:,.2f}\n"
                f"Total Gain:    ₦{A - P:,.2f} ({((A - P) / P) * 100:.1f}%)"
            )

        elif calc == "loan_payment":
            P, r_annual, years = float(parts[1]), float(parts[2]), float(parts[3])
            r = r_annual / 12
            n = years * 12
            if r > 0:
                monthly = P * r * (1 + r) ** n / ((1 + r) ** n - 1)
            else:
                monthly = P / n
            total = monthly * n
            return (
                f"🏦 Loan Payment\n"
                f"Principal:        ₦{P:,.2f}\n"
                f"Annual Rate:      {r_annual * 100:.1f}%\n"
                f"Term:             {years:.0f} years\n"
                f"Monthly Payment:  ₦{monthly:,.2f}\n"
                f"Total Repaid:     ₦{total:,.2f}\n"
                f"Total Interest:   ₦{total - P:,.2f}"
            )

        elif calc == "roi":
            gain, cost = float(parts[1]), float(parts[2])
            if cost == 0:
                return "Cost cannot be zero."
            roi = ((gain - cost) / cost) * 100
            return (
                f"📈 Return on Investment\n"
                f"Investment: ₦{cost:,.2f}\n"
                f"Return:     ₦{gain:,.2f}\n"
                f"ROI:        {roi:.2f}%\n"
                f"Profit:     ₦{gain - cost:,.2f}"
            )

        elif calc == "break_even":
            fixed, price, variable = (
                float(parts[1]), float(parts[2]), float(parts[3])
            )
            margin = price - variable
            if margin <= 0:
                return "Price per unit must be greater than variable cost per unit."
            units = fixed / margin
            return (
                f"⚖️ Break-Even Analysis\n"
                f"Fixed Costs:          ₦{fixed:,.2f}\n"
                f"Price / Unit:         ₦{price:,.2f}\n"
                f"Variable Cost / Unit: ₦{variable:,.2f}\n"
                f"Contribution Margin:  ₦{margin:,.2f}\n"
                f"Break-Even Units:     {units:,.0f}\n"
                f"Break-Even Revenue:   ₦{units * price:,.2f}"
            )

        elif calc == "inflation_adjust":
            amount, rate, years = float(parts[1]), float(parts[2]), float(parts[3])
            real = amount / (1 + rate) ** years
            return (
                f"📉 Inflation Adjustment\n"
                f"Nominal Amount:       ₦{amount:,.2f}\n"
                f"Inflation Rate:       {rate * 100:.1f}% per year\n"
                f"Years:                {years:.0f}\n"
                f"Real Value Today:     ₦{real:,.2f}\n"
                f"Purchasing Power Lost:₦{amount - real:,.2f} "
                f"({((amount - real) / amount) * 100:.1f}%)"
            )

        elif calc == "future_value":
            pv, rate, years = float(parts[1]), float(parts[2]), float(parts[3])
            fv = pv * (1 + rate) ** years
            return (
                f"🔭 Future Value\n"
                f"Present Value: ₦{pv:,.2f}\n"
                f"Rate:          {rate * 100:.1f}% per year\n"
                f"Years:         {years:.0f}\n"
                f"Future Value:  ₦{fv:,.2f}"
            )

        elif calc == "payback_period":
            invest, cashflow = float(parts[1]), float(parts[2])
            if cashflow <= 0:
                return "Annual cashflow must be greater than zero."
            years = invest / cashflow
            return (
                f"⏱️ Payback Period\n"
                f"Investment:      ₦{invest:,.2f}\n"
                f"Annual Cashflow: ₦{cashflow:,.2f}\n"
                f"Payback Period:  {years:.2f} years"
            )

        else:
            return (
                f"Unknown type: '{calc}'.\n"
                "Supported: compound_interest, loan_payment, roi, "
                "break_even, inflation_adjust, future_value, payback_period"
            )

    except IndexError:
        return "Not enough parameters. Check the format in the tool description."
    except Exception as e:
        return f"Calculator error: {e}"


# ══════════════════════════════════════════════════════════════
# 7. MARKET OVERVIEW
# ══════════════════════════════════════════════════════════════
@tool
def get_market_overview(input: str = "all") -> str:
    """
    Get a live snapshot of major global indices and crypto prices.
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
                        chg   = h["Close"].iloc[-1] - h["Close"].iloc[-2]
                        pct   = (chg / h["Close"].iloc[-2]) * 100
                        arrow = "▲" if chg >= 0 else "▼"
                        out.append(
                            f"{name:12} {h['Close'].iloc[-1]:>12,.2f}"
                            f"  {arrow} {pct:+.2f}%"
                        )
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
                try:
                    h = yf.Ticker(sym).history(period="2d")
                    if len(h) >= 2:
                        chg   = h["Close"].iloc[-1] - h["Close"].iloc[-2]
                        pct   = (chg / h["Close"].iloc[-2]) * 100
                        arrow = "▲" if chg >= 0 else "▼"
                        out.append(
                            f"{name:10} ${h['Close'].iloc[-1]:>12,.2f}"
                            f"  {arrow} {pct:+.2f}%"
                        )
                except Exception:
                    pass

        return "\n".join(out) if out else "Market data temporarily unavailable."

    except Exception as e:
        return f"Market overview error: {e}"


# ══════════════════════════════════════════════════════════════
# 8. TASK PLANNER
# ══════════════════════════════════════════════════════════════
@tool
def plan_task(goal: str) -> str:
    """
    Break a complex financial goal into a clear step-by-step plan.
    Use this FIRST whenever the user has a multi-step or complex request.
    Input: plain description of what the user wants to accomplish.
    """
    return (
        f"📋 Plan for: {goal}\n\n"
        "Step 1 — Clarify the objective and identify missing information\n"
        "Step 2 — Determine which data sources or tools are needed\n"
        "Step 3 — Gather required data (prices, financials, inputs)\n"
        "Step 4 — Perform calculations or analysis\n"
        "Step 5 — Validate results for accuracy and consistency\n"
        "Step 6 — Summarise findings with a clear, actionable recommendation\n\n"
        "Proceeding with execution..."
    )


# ══════════════════════════════════════════════════════════════
# EXPORT — import this list in agent.py
# ══════════════════════════════════════════════════════════════
amhani_tools = [
    get_stock_price,
    calculate_pe_ratio,
    execute_python,
    analyse_financial_data,
    generate_stock_chart,
    financial_calculator,
    get_market_overview,
    plan_task,
]
