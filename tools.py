# tools.py — CONSULTAMHANi | Financial Tools
# Plain Python functions — no LangChain dependency

import json
import yfinance as yf


def get_stock_price(ticker: str) -> str:
    """
    Get real-time stock price data for a ticker symbol.
    Returns last close, 5-day history, sector, and market cap.
    """
    ticker = ticker.strip().upper()
    try:
        t    = yf.Ticker(ticker)
        hist = t.history(period="5d", interval="1d")
        if hist.empty:
            return f"No data found for '{ticker}'. Please check the symbol."
        last_close = round(float(hist["Close"].iloc[-1]), 2)
        five_day   = [round(float(p), 2) for p in hist["Close"].tolist()]
        info       = t.info or {}
        return json.dumps({
            "ticker":     ticker,
            "last_close": last_close,
            "5d_closes":  five_day,
            "name":       info.get("shortName", "N/A"),
            "sector":     info.get("sector", "N/A"),
            "market_cap": info.get("marketCap", "N/A"),
            "currency":   info.get("currency", "USD"),
        })
    except Exception as e:
        return f"Error fetching data for '{ticker}': {e}"


def calculate_pe_ratio(price: float, eps: float) -> str:
    """
    Calculate the Price-to-Earnings (P/E) ratio.
    price = stock price, eps = earnings per share.
    """
    try:
        if eps == 0:
            return "Cannot calculate P/E ratio: EPS is zero."
        pe = round(price / eps, 2)
        if pe > 25:
            verdict = "Overvalued range"
        elif pe > 15:
            verdict = "Fair value range"
        else:
            verdict = "Undervalued range"
        return json.dumps({"pe_ratio": pe, "price": price, "eps": eps, "verdict": verdict})
    except Exception as e:
        return f"Error calculating P/E ratio: {e}"


# ── OpenAI tool schemas ────────────────────────────────────────────────────────
# These are passed directly to the OpenAI API as function definitions

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_stock_price",
            "description": (
                "Get real-time stock price and market data for a ticker symbol. "
                "Use this for any question about stock prices, market cap, or sector info."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol e.g. AAPL, TSLA, MSFT, DANGOTE.LG"
                    }
                },
                "required": ["ticker"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_pe_ratio",
            "description": (
                "Calculate the Price-to-Earnings (P/E) ratio given a stock price and EPS. "
                "Use this when asked about P/E ratio or valuation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "price": {
                        "type": "number",
                        "description": "Current stock price"
                    },
                    "eps": {
                        "type": "number",
                        "description": "Earnings per share (EPS)"
                    }
                },
                "required": ["price", "eps"]
            }
        }
    }
]


# ── Tool dispatcher ────────────────────────────────────────────────────────────
def run_tool(name: str, arguments: dict) -> str:
    """Execute a tool by name with given arguments."""
    if name == "get_stock_price":
        return get_stock_price(arguments.get("ticker", ""))
    elif name == "calculate_pe_ratio":
        return calculate_pe_ratio(
            float(arguments.get("price", 0)),
            float(arguments.get("eps", 0))
        )
    return f"Unknown tool: {name}"
