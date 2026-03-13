# tools.py — CONSULTAMHANi | Financial Tools

import yfinance as yf
from langchain_core.tools import tool


@tool
def get_stock_price(ticker: str) -> str:
    """
    Get a real-time price snapshot for a stock ticker.
    Input must be a ticker symbol like AAPL, MSFT, TSLA, DANGOTE.
    Returns last close price, 5-day history, sector, and market cap.
    """
    ticker = ticker.strip().upper()
    try:
        t    = yf.Ticker(ticker)
        hist = t.history(period="5d", interval="1d")
        if hist.empty:
            return (
                f"No data found for '{ticker}'. "
                f"Please check the symbol and try again."
            )
        last_close = round(float(hist["Close"].iloc[-1]), 2)
        five_day   = [round(p, 2) for p in hist["Close"].tolist()]
        info       = t.info or {}
        result = {
            "ticker":     ticker,
            "last_close": last_close,
            "5d_closes":  five_day,
            "name":       info.get("shortName", "N/A"),
            "sector":     info.get("sector", "N/A"),
            "market_cap": info.get("marketCap", "N/A"),
            "currency":   info.get("currency", "USD"),
        }
        return str(result)
    except Exception as e:
        return f"Error fetching data for '{ticker}': {e}"


@tool
def calculate_pe_ratio(input: str) -> str:
    """
    Calculate the Price-to-Earnings (P/E) ratio.
    Input MUST be two numbers separated by a comma: "price, earnings_per_share"
    Example: "150.0, 7.5" means stock price is 150 and EPS is 7.5.
    """
    try:
        parts = input.split(",")
        if len(parts) != 2:
            return (
                "Error: provide exactly two values separated by a comma. "
                "Example: '150.0, 7.5'"
            )
        price = float(parts[0].strip())
        eps   = float(parts[1].strip())
        if eps == 0:
            return "Cannot calculate P/E ratio: EPS is zero."
        pe = round(price / eps, 2)
        return (
            f"P/E Ratio = {pe}  "
            f"(Price: ${price}, EPS: ${eps}) — "
            f"{'Overvalued' if pe > 25 else 'Fair value' if pe > 15 else 'Undervalued'} range"
        )
    except ValueError:
        return (
            "Error: could not parse input. "
            "Make sure both values are numbers. Example: '150.0, 7.5'"
        )
