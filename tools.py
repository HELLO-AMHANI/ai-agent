# tools.py — AMHANi | Full Tool Suite
import os
import requests
import yfinance as yf
from langchain_core.tools import tool

# ── Existing tools ────────────────────────────────────────────────────────────

@tool
def get_stock_price(ticker: str) -> str:
    """
    Get a price snapshot for a stock ticker.
    Input should be a ticker symbol like AAPL, MSFT, or TSLA.
    Returns last close price, 5-day history, sector, and market cap.
    """
    ticker = ticker.strip().upper()
    try:
        t    = yf.Ticker(ticker)
        hist = t.history(period="5d", interval="1d")
        if hist.empty:
            return f"No data found for '{ticker}'. Check the symbol."
        last_close = round(float(hist["Close"].iloc[-1]), 2)
        five_day   = [round(p, 2) for p in hist["Close"].tolist()]
        info       = t.info or {}
        return str({
            "ticker":     ticker,
            "last_close": last_close,
            "5d_closes":  five_day,
            "name":       info.get("shortName", "N/A"),
            "sector":     info.get("sector", "N/A"),
            "market_cap": info.get("marketCap", "N/A"),
        })
    except Exception as e:
        return f"Error fetching '{ticker}': {e}"


@tool
def calculate_pe_ratio(input: str) -> str:
    """
    Calculate the Price-to-Earnings (P/E) ratio.
    Input MUST be two numbers separated by a comma: "price, earnings_per_share"
    Example: "150.0, 7.5"
    """
    try:
        parts = input.split(",")
        if len(parts) != 2:
            return "Error: provide exactly two values separated by a comma. Example: '150.0, 7.5'"
        price = float(parts[0].strip())
        eps   = float(parts[1].strip())
        if eps == 0:
            return "Cannot calculate P/E ratio: EPS is zero."
        return f"P/E Ratio = {round(price / eps, 2)}  (Price: ${price}, EPS: ${eps})"
    except ValueError:
        return "Error: could not parse input. Example: '150.0, 7.5'"


# ── NEW: AlphaVantage — Market news & stock fundamentals ──────────────────────

@tool
def get_market_news(topic: str) -> str:
    """
    Get the latest financial market news for a topic or ticker.
    Input: a topic or ticker symbol. Examples: "AAPL", "crypto", "oil", "Nigeria economy"
    Powered by AlphaVantage News Sentiment API.
    """
    api_key = os.getenv("ALPHAVANTAGE_API_KEY")
    if not api_key:
        return "AlphaVantage API key not set. Add ALPHAVANTAGE_API_KEY to your .env file."
    try:
        url    = "https://www.alphavantage.co/query"
        params = {
            "function": "NEWS_SENTIMENT",
            "tickers":  topic.upper(),
            "limit":    5,
            "apikey":   api_key,
        }
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        feed = data.get("feed", [])
        if not feed:
            return f"No news found for '{topic}'."
        results = []
        for article in feed[:5]:
            results.append({
                "title":   article.get("title", "N/A"),
                "source":  article.get("source", "N/A"),
                "summary": article.get("summary", "")[:200] + "...",
                "url":     article.get("url", ""),
            })
        return str(results)
    except Exception as e:
        return f"Error fetching news for '{topic}': {e}"


@tool
def get_company_overview(ticker: str) -> str:
    """
    Get detailed fundamental data for a company — revenue, profit margin,
    dividend yield, 52-week high/low, analyst target price, and more.
    Input: a stock ticker symbol like AAPL, TSLA, MSFT.
    Powered by AlphaVantage.
    """
    api_key = os.getenv("ALPHAVANTAGE_API_KEY")
    if not api_key:
        return "AlphaVantage API key not set. Add ALPHAVANTAGE_API_KEY to your .env file."
    try:
        url    = "https://www.alphavantage.co/query"
        params = {
            "function": "OVERVIEW",
            "symbol":   ticker.strip().upper(),
            "apikey":   api_key,
        }
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if not data or "Symbol" not in data:
            return f"No fundamental data found for '{ticker}'."
        return str({
            "name":             data.get("Name"),
            "sector":           data.get("Sector"),
            "industry":         data.get("Industry"),
            "market_cap":       data.get("MarketCapitalization"),
            "pe_ratio":         data.get("PERatio"),
            "eps":              data.get("EPS"),
            "revenue_ttm":      data.get("RevenueTTM"),
            "profit_margin":    data.get("ProfitMargin"),
            "dividend_yield":   data.get("DividendYield"),
            "52wk_high":        data.get("52WeekHigh"),
            "52wk_low":         data.get("52WeekLow"),
            "analyst_target":   data.get("AnalystTargetPrice"),
            "description":      data.get("Description", "")[:300] + "...",
        })
    except Exception as e:
        return f"Error fetching overview for '{ticker}': {e}"


# ── NEW: ExchangeRate — Live currency conversion ───────────────────────────────

@tool
def get_exchange_rate(input: str) -> str:
    """
    Get the live exchange rate between two currencies.
    Input MUST be two currency codes separated by a comma: "FROM, TO"
    Examples: "USD, NGN"  "GBP, USD"  "EUR, NGN"
    Powered by ExchangeRate API.
    """
    api_key = os.getenv("EXCHANGERATE_API_KEY")
    if not api_key:
        return "ExchangeRate API key not set. Add EXCHANGERATE_API_KEY to your .env file."
    try:
        parts = input.split(",")
        if len(parts) != 2:
            return "Error: provide two currency codes separated by a comma. Example: 'USD, NGN'"
        from_cur = parts[0].strip().upper()
        to_cur   = parts[1].strip().upper()
        url      = f"https://v6.exchangerate-api.com/v6/{api_key}/pair/{from_cur}/{to_cur}"
        resp     = requests.get(url, timeout=10)
        data     = resp.json()
        if data.get("result") != "success":
            return f"Error: {data.get('error-type', 'Unknown error')}. Check currency codes."
        rate = data.get("conversion_rate")
        return (
            f"1 {from_cur} = {rate} {to_cur}  "
            f"(Last updated: {data.get('time_last_update_utc', 'N/A')})"
        )
    except Exception as e:
        return f"Error fetching exchange rate: {e}"


@tool
def convert_currency(input: str) -> str:
    """
    Convert an amount from one currency to another using live rates.
    Input MUST be: "amount, FROM, TO"
    Examples: "1000, USD, NGN"   "500, GBP, EUR"
    """
    api_key = os.getenv("EXCHANGERATE_API_KEY")
    if not api_key:
        return "ExchangeRate API key not set. Add EXCHANGERATE_API_KEY to your .env file."
    try:
        parts = [p.strip() for p in input.split(",")]
        if len(parts) != 3:
            return "Error: provide amount, FROM, TO. Example: '1000, USD, NGN'"
        amount   = float(parts[0])
        from_cur = parts[1].upper()
        to_cur   = parts[2].upper()
        url      = f"https://v6.exchangerate-api.com/v6/{api_key}/pair/{from_cur}/{to_cur}/{amount}"
        resp     = requests.get(url, timeout=10)
        data     = resp.json()
        if data.get("result") != "success":
            return f"Error: {data.get('error-type', 'Unknown error')}."
        converted = data.get("conversion_result")
        rate      = data.get("conversion_rate")
        return (
            f"{amount} {from_cur} = {converted} {to_cur}  "
            f"(Rate: 1 {from_cur} = {rate} {to_cur})"
        )
    except ValueError:
        return "Error: amount must be a number. Example: '1000, USD, NGN'"
    except Exception as e:
        return f"Error converting currency: {e}"


# ── NEW: WorldBank — Macro economic indicators ────────────────────────────────

@tool
def get_gdp_data(input: str) -> str:
    """
    Get GDP data for a country from the World Bank.
    Input MUST be: "country_code" or "country_code, year"
    Country codes: NGA (Nigeria), USA, GBR, ZAF, KEN, GHA
    Examples: "NGA"   "USA, 2022"
    Powered by World Bank Open Data API — no key required.
    """
    try:
        parts   = [p.strip() for p in input.split(",")]
        country = parts[0].upper()
        year    = parts[1].strip() if len(parts) > 1 else ""
        date    = year if year else "2015:2023"
        url     = (
            f"https://api.worldbank.org/v2/country/{country}"
            f"/indicator/NY.GDP.MKTP.CD"
            f"?format=json&date={date}&per_page=10"
        )
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if not data or len(data) < 2 or not data[1]:
            return f"No GDP data found for '{country}'. Check the country code."
        records = [
            {"year": r["date"], "gdp_usd": r["value"]}
            for r in data[1] if r.get("value") is not None
        ]
        if not records:
            return f"GDP data unavailable for '{country}' in the requested period."
        return str({"country": country, "indicator": "GDP (current USD)", "data": records})
    except Exception as e:
        return f"Error fetching GDP data: {e}"


@tool
def get_inflation_data(country_code: str) -> str:
    """
    Get annual inflation rate data for a country from the World Bank.
    Input: a World Bank country code.
    Examples: "NGA" (Nigeria), "USA", "GBR", "ZAF", "KEN", "GHA"
    Powered by World Bank Open Data API.
    """
    try:
        country = country_code.strip().upper()
        url     = (
            f"https://api.worldbank.org/v2/country/{country}"
            f"/indicator/FP.CPI.TOTL.ZG"
            f"?format=json&date=2015:2023&per_page=10"
        )
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if not data or len(data) < 2 or not data[1]:
            return f"No inflation data found for '{country}'. Check the country code."
        records = [
            {"year": r["date"], "inflation_pct": round(r["value"], 2)}
            for r in data[1] if r.get("value") is not None
        ]
        if not records:
            return f"Inflation data unavailable for '{country}'."
        return str({"country": country, "indicator": "Inflation rate (%)", "data": records})
    except Exception as e:
        return f"Error fetching inflation data: {e}"
