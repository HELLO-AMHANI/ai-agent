# =============================================================
# agent.py — AMHANi ENTERPRISE v5
#
# CHANGES FROM v4:
#
# 1. "CONNECTING" text appearing in UI — DEFINITIVE FIX
#    Root cause: LangChain's httpx client emits INFO-level log
#    records at the MODULE level, before any worker thread runs.
#    The previous fix only redirected stderr INSIDE the worker,
#    but httpx logs are emitted via Python's logging framework,
#    which Streamlit captures and renders in the UI (not stderr).
#    Fix A: NullHandler attached to every noisy logger replaces
#      the default StreamHandler — logs are silently discarded.
#    Fix B: logging.disable(logging.WARNING) called at module
#      level as a belt-and-suspenders guarantee.
#    Fix C: stderr/stdout redirected inside the worker as before
#      for any edge cases that bypass the logging framework.
#
# 2. Tool registry updated — get_ngn_market → get_ngx_market
#    System prompt updated with NGX Pulse and Polygon.io tools.
#
# 3. temperature=1 (unchanged from v4 fix — DO NOT change this)
#    streaming=False (unchanged — prevents SessionInfo callbacks)
# =============================================================

import os
import sys
import io
import json
import logging
import concurrent.futures
from dotenv import load_dotenv
load_dotenv()

# ══════════════════════════════════════════════════════════════
# SILENCE ALL NOISY LOGGERS — module level, before any import
#
# Root cause of "CONNECTING" in UI:
#   Python's logging framework has a root logger with a
#   StreamHandler that writes to stderr by default. Streamlit
#   captures stderr and renders it in the spinner/status area.
#   LangChain's httpx client logs every connection attempt at
#   INFO level, which flows through to stderr via that handler.
#
# Fix: replace the StreamHandler with a NullHandler on every
#   logger we care about. NullHandler discards all records.
#   logging.disable(WARNING) catches anything that slips through.
# ══════════════════════════════════════════════════════════════
_NOISY_LOGGERS = [
    "langchain", "langchain_core", "langchain_openai",
    "openai", "httpx", "httpcore", "urllib3",
    "requests", "asyncio", "hpack", "h2",
]
for _name in _NOISY_LOGGERS:
    _log = logging.getLogger(_name)
    _log.handlers = [logging.NullHandler()]
    _log.propagate = False                   # do not bubble up to root
    _log.setLevel(logging.CRITICAL)

# Belt-and-suspenders: disable all WARNING and below globally
logging.disable(logging.WARNING)

# ── Now safe to import LangChain ──────────────────────────────
from langchain_openai import ChatOpenAI
from langchain_core.messages import (
    HumanMessage, AIMessage, SystemMessage, ToolMessage,
)
from tools import amhani_tools


# ── LLM ──────────────────────────────────────────────────────
llm = ChatOpenAI(
    model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    temperature=1,          # only supported value for this model family
    api_key=os.getenv("OPENAI_API_KEY"),
    request_timeout=60,
    streaming=False,        # True triggers SessionInfo callback errors
).bind_tools(amhani_tools)

TOOL_MAP = {t.name: t for t in amhani_tools}


# ── System prompt ─────────────────────────────────────────────
SYSTEM_PROMPT = (
    "You are AMHANi, an expert AI financial consultant built by AMHANi Enterprise.\n\n"

    "TOOL SELECTION — follow exactly:\n"
    "- Stock price (AAPL, TSLA, NVDA, any ticker)    → get_stock_price\n"
    "- Currency conversion (USD→NGN, any FX)         → convert_currency\n"
    "- Crypto prices (BTC, ETH, BNB, any coin)       → get_crypto_price\n"
    "- Crypto 4H analysis (BTC 4h, ETH 4h)           → get_crypto_price input='COIN,4h'\n"
    "- Index 4H (US30, SPX, NAS100, GOLD, OIL)       → get_index_4h\n"
    "- Nigerian stocks / NGX live data (NGX Pulse)    → get_ngx_market\n"
    "- Stock financials, ratios, income statement     → get_stock_financials\n"
    "- Insider trades / SEC Form 4 filings            → get_insider_trades\n"
    "- Global indices snapshot                        → get_market_overview\n"
    "- P/E ratio from price + EPS                    → calculate_pe_ratio\n"
    "- Compound interest / loan / ROI / break-even   → financial_calculator\n"
    "- Analyse CSV/JSON financial data                → analyse_financial_data\n"
    "- Stock chart or price graph                     → generate_stock_chart\n"
    "- Custom Python / complex calculation            → execute_python\n"
    "- Multi-step complex request                     → plan_task FIRST\n\n"

    "DATA SOURCES:\n"
    "- US Stocks: Polygon.io (primary) → Yahoo Finance (fallback)\n"
    "- Nigerian Stocks: NGX Pulse API (X_API_KEY) → Yahoo Finance .LG suffix\n"
    "- Crypto: CoinGecko (price) + Binance (4H candles)\n"
    "- Forex: ExchangeRate-API + Frankfurter (ECB)\n\n"

    "BEHAVIOUR:\n"
    "1. Answer the CURRENT question only.\n"
    "2. Never ask clarifying questions for simple data requests — call the tool.\n"
    "3. If a tool returns unavailable or error — report honestly, never invent data.\n"
    "4. Use ₦ for Nigerian Naira, $ for USD.\n"
    "5. Be concise, precise, and professional.\n"
    "6. For insider trades: explain what large buys/sells signal for investors."
)


# ══════════════════════════════════════════════════════════════
# CORE LOOP — isolated worker thread (SessionInfo fix)
# ══════════════════════════════════════════════════════════════
def _run_loop(messages: list, max_iter: int = 10) -> dict:
    """
    Tool-calling loop. Runs in a ThreadPoolExecutor worker thread
    with zero Streamlit session context — prevents SessionInfo errors.
    """
    _null = io.StringIO()
    _orig_out, _orig_err = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = _null

    intermediate = []

    try:
        for _ in range(max_iter):
            response = llm.invoke(messages)

            if not response.tool_calls:
                sys.stdout, sys.stderr = _orig_out, _orig_err
                return {
                    "output": response.content or "",
                    "intermediate_steps": intermediate,
                }

            # Sanitize tool_calls — prevent None id/name/args
            clean_tcs = []
            for tc in response.tool_calls:
                clean_tcs.append({
                    "id":   str(tc.get("id") or f"call_{len(intermediate)}"),
                    "name": str(tc.get("name") or ""),
                    "args": tc.get("args") or {},
                    "type": "tool_call",
                })

            messages.append(AIMessage(
                content=response.content or "",
                tool_calls=clean_tcs,
            ))

            for tc in clean_tcs:
                tool_name = tc["name"]
                tool_args = tc["args"]
                tool_id   = tc["id"]

                fn = TOOL_MAP.get(tool_name)
                if fn:
                    try:
                        raw = (
                            str(list(tool_args.values())[0])
                            if isinstance(tool_args, dict) and len(tool_args) == 1
                            else json.dumps(tool_args) if isinstance(tool_args, dict)
                            else str(tool_args) if tool_args else ""
                        )
                        sys.stdout, sys.stderr = _orig_out, _orig_err
                        result = fn.invoke(raw)
                        sys.stdout = sys.stderr = _null
                    except Exception as e:
                        result = f"Tool error ({tool_name}): {e}"
                else:
                    result = f"Tool '{tool_name}' not found."

                intermediate.append((tool_name, tool_args, str(result)))
                messages.append(ToolMessage(
                    content=str(result),
                    tool_call_id=tool_id,
                ))

        sys.stdout, sys.stderr = _orig_out, _orig_err
        return {
            "output": "Max iterations reached. Try a simpler request.",
            "intermediate_steps": intermediate,
        }

    except Exception as e:
        sys.stdout, sys.stderr = _orig_out, _orig_err
        raise e


# ══════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════
def run_agent(
    question: str,
    long_term_context: str = "",
    chat_history: list = None,
    timeout: int = 90,
) -> dict:
    """
    Run agent in an isolated worker thread.
    Returns {"output": str, "intermediate_steps": list}.
    """
    if not question or not question.strip():
        return {"output": "Please enter a question.", "intermediate_steps": []}

    full_input = question.strip()
    if long_term_context and long_term_context.strip():
        full_input = (
            f"[Client context: {long_term_context.strip()[:400]}]\n{full_input}"
        )

    last_error = None

    for attempt in range(3):
        try:
            messages = [SystemMessage(content=SYSTEM_PROMPT)]
            if chat_history:
                messages.extend(chat_history)
            messages.append(HumanMessage(content=full_input))

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(_run_loop, messages)
                result = future.result(timeout=timeout)

            output = (result.get("output") or "").strip()
            if output and len(output) > 5:
                return result

        except concurrent.futures.TimeoutError:
            return {
                "output": (
                    "⏱️ Request timed out after 90 seconds.\n"
                    "Please try again — data source may be temporarily slow."
                ),
                "intermediate_steps": [],
            }
        except Exception as e:
            last_error = str(e)
            if attempt < 2:
                full_input = (
                    f"Previous attempt errored: {last_error}. "
                    f"Try a different approach for: {question}"
                )

    return {
        "output": (
            f"I couldn't complete that request after 3 attempts.\n"
            f"Last error: {last_error}\n"
            f"Please rephrase or try a simpler request."
        ),
        "intermediate_steps": [],
    }


# ── Memory sync ───────────────────────────────────────────────
def sync_memory(messages: list) -> list:
    pairs = []
    i = 0
    while i < len(messages) - 1:
        u = messages[i]; a = messages[i + 1]
        if u.get("role") == "user" and a.get("role") == "assistant":
            uc = (u.get("content") or "").strip()
            ac = (a.get("content") or "").strip()
            if uc and ac:
                pairs.append((uc, ac[:500]))
        i += 2
    history = []
    for uc, ac in pairs[-6:]:
        history.append(HumanMessage(content=uc))
        history.append(AIMessage(content=ac))
    return history


# ── CLI ───────────────────────────────────────────────────────
if __name__ == "__main__":
    import click

    @click.command()
    @click.option("--ask",     default=None, help="Single question")
    @click.option("--repl",    is_flag=True,  help="Interactive REPL")
    @click.option("--verbose", is_flag=True,  help="Show reasoning steps")
    def cli(ask, repl, verbose):
        if ask:
            r = run_agent(ask)
            print(f"\n── AMHANi ──\n{r['output']}")
            if verbose:
                for i, s in enumerate(r.get("intermediate_steps", [])):
                    print(
                        f"\nStep {i+1}: {s[0]}\n"
                        f"  Input:  {str(s[1])[:200]}\n"
                        f"  Result: {str(s[2])[:300]}"
                    )
        elif repl:
            print("AMHANi — type 'exit' to quit\n")
            history = []
            while True:
                q = input("You: ").strip()
                if q.lower() in ("exit", "quit"):
                    break
                if not q:
                    continue
                r = run_agent(q, chat_history=history)
                print(f"\nAMHANi: {r['output']}\n")
                history.append(HumanMessage(content=q))
                history.append(AIMessage(content=r["output"]))
        else:
            print("Use --ask 'question' or --repl")

    cli()