# =============================================================
# agent.py — AMHANi ENTERPRISE v4
#
# ROOT CAUSES FIXED:
#
# 1. HTTP 400 "temperature does not support 0.7 with this model"
#    OpenAI's newer models (gpt-4o-mini and any o-series model)
#    enforce temperature=1 as the ONLY accepted value at the API
#    level. Sending any other value — including 0.7 — returns
#    a hard 400 error before the request even reaches the LLM.
#    All 3 retry attempts hit the same 400, hence the final
#    "couldn't complete after 3 attempts" message.
#    FIX: temperature=1  (the only universally supported value)
#
# 2. "Tried to use SessionInfo before it was initiated"
#    LangChain's ChatOpenAI streaming callbacks inspect
#    Streamlit's thread-local session context. Running the loop
#    in the main Streamlit thread triggers this when callbacks
#    fire outside the registered session scope.
#    FIX: _run_loop() runs inside a ThreadPoolExecutor worker.
#    Worker threads have ZERO Streamlit session context, so no
#    callback can accidentally touch st.session_state.
#
# 3. "Bad message format" / None tool_call ids
#    AIMessage tool_calls with None id fields are rejected.
#    FIX: Sanitize every tool_call before appending to messages.
#
# 4. "CONNECTING" noise in UI
#    LangChain httpx logger writes to stderr which Streamlit
#    captures in the spinner area.
#    FIX: All loggers set to CRITICAL + StringIO redirect inside
#    the isolated worker where it cannot touch Streamlit.
# =============================================================

import os
import sys
import io
import json
import logging
import concurrent.futures
from dotenv import load_dotenv
load_dotenv()

# ── Kill all LangChain/OpenAI logging before import ──────────
for _logger_name in (
    "langchain", "langchain_core", "langchain_openai",
    "openai", "httpx", "httpcore", "urllib3",
):
    logging.getLogger(_logger_name).setLevel(logging.CRITICAL)

from langchain_openai import ChatOpenAI
from langchain_core.messages import (
    HumanMessage, AIMessage, SystemMessage, ToolMessage
)
from tools import amhani_tools


# ── LLM ──────────────────────────────────────────────────────
# CRITICAL FIX: temperature=1 (not 0.7).
# gpt-4o-mini and all o-series models reject any value other
# than 1 at the API level with HTTP 400. This was the sole
# cause of "couldn't complete after 3 attempts".
llm = ChatOpenAI(
    model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    temperature=1,          # ← FIXED: was 0.7, only 1 is supported
    api_key=os.getenv("OPENAI_API_KEY"),
    request_timeout=60,
    streaming=False,        # streaming=True triggers SessionInfo callbacks
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
    "- Insider trades / SEC Form 4 filings            → get_insider_trades\n"
    "- Financial statements, ratios, P/E, margins     → get_stock_financials\n"
    "- Nigerian stocks / NGX market data              → get_ngn_market\n"
    "- Global indices snapshot                        → get_market_overview\n"
    "- P/E ratio from price + EPS                    → calculate_pe_ratio\n"
    "- Compound interest / loan / ROI / break-even   → financial_calculator\n"
    "- Analyse CSV/JSON financial data                → analyse_financial_data\n"
    "- Stock chart or price graph                     → generate_stock_chart\n"
    "- Custom Python / complex calculation            → execute_python\n"
    "- Multi-step complex request                     → plan_task FIRST\n\n"

    "BEHAVIOUR:\n"
    "1. Answer the CURRENT question only.\n"
    "2. Never ask clarifying questions for simple data requests — call the tool.\n"
    "3. If a tool returns unavailable or error — report it honestly, never invent data.\n"
    "4. Use ₦ for Nigerian Naira, $ for USD.\n"
    "5. Be concise, precise, and professional.\n"
    "6. For insider trades: explain what large buys/sells mean for investors."
)


# ═════════════════════════════════════════════════════════════
# CORE LOOP — runs in an isolated worker thread
# ═════════════════════════════════════════════════════════════
def _run_loop(messages: list, max_iter: int = 10) -> dict:
    """
    Tool-calling loop. Runs inside a ThreadPoolExecutor worker —
    completely isolated from Streamlit's session context.
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

            # Sanitize tool_calls — ensure no None id/name/args
            clean_tcs = []
            for tc in response.tool_calls:
                clean_tcs.append({
                    "id":   str(tc.get("id") or f"call_{len(intermediate)}"),
                    "name": str(tc.get("name") or ""),
                    "args": tc.get("args") or {},
                    "type": "tool_call",
                })

            ai_msg = AIMessage(
                content=response.content or "",
                tool_calls=clean_tcs,
            )
            messages.append(ai_msg)

            for tc in clean_tcs:
                tool_name = tc["name"]
                tool_args = tc["args"]
                tool_id   = tc["id"]

                fn = TOOL_MAP.get(tool_name)
                if fn:
                    try:
                        if isinstance(tool_args, dict):
                            raw = (
                                str(list(tool_args.values())[0])
                                if len(tool_args) == 1
                                else json.dumps(tool_args)
                            )
                        else:
                            raw = str(tool_args) if tool_args else ""

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


# ═════════════════════════════════════════════════════════════
# PUBLIC API — called by app.py
# ═════════════════════════════════════════════════════════════
def run_agent(
    question: str,
    long_term_context: str = "",
    chat_history: list = None,
    timeout: int = 90,
) -> dict:
    """
    Run the agent in an isolated worker thread (SessionInfo fix).
    Returns {"output": str, "intermediate_steps": list}.
    """
    if not question or not question.strip():
        return {"output": "Please enter a question.", "intermediate_steps": []}

    full_input = question.strip()
    if long_term_context and long_term_context.strip():
        full_input = (
            f"[Client context: {long_term_context.strip()[:400]}]\n"
            f"{full_input}"
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
                    "The data source may be slow. Please try again."
                ),
                "intermediate_steps": [],
            }
        except Exception as e:
            last_error = str(e)
            if attempt < 2:
                full_input = (
                    f"Previous attempt had an error: {last_error}. "
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
    """Convert Streamlit message history to LangChain message objects."""
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
    @click.option("--ask",     default=None,  help="Single question")
    @click.option("--repl",    is_flag=True,   help="Interactive REPL")
    @click.option("--verbose", is_flag=True,   help="Show reasoning steps")
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
