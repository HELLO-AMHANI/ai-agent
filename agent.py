# =============================================================
# agent.py — AMHANi ENTERPRISE
# DIAGNOSIS FIX:
#   - "Bad message format": _run_loop was appending raw response
#     object which LangChain couldn't serialize consistently.
#     FIX: Explicitly reconstruct AIMessage with clean content.
#   - "CONNECTING" in UI: LangChain still output to stderr even
#     with verbose=False. FIX: Redirect both stdout and stderr
#     during tool execution.
#   - agent_executor not defined but called: removed entirely,
#     _run_loop is the sole execution path.
#   - sync_memory defined 3 times: single clean definition only.
# =============================================================

import os
import sys
import io
import json
import logging
from dotenv import load_dotenv
load_dotenv()

# ── Suppress ALL LangChain/OpenAI output ─────────────────────
# This permanently stops CONNECTING/RUNNING from appearing in UI
logging.getLogger("langchain").setLevel(logging.CRITICAL)
logging.getLogger("langchain_core").setLevel(logging.CRITICAL)
logging.getLogger("langchain_openai").setLevel(logging.CRITICAL)
logging.getLogger("openai").setLevel(logging.CRITICAL)
logging.getLogger("httpx").setLevel(logging.CRITICAL)
logging.getLogger("httpcore").setLevel(logging.CRITICAL)

from langchain_openai import ChatOpenAI
from langchain_core.messages import (
    HumanMessage, AIMessage, SystemMessage, ToolMessage
)
from tools import amhani_tools


# ── LLM ──────────────────────────────────────────────────────
llm = ChatOpenAI(
    model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    temperature=1,
    api_key=os.getenv("OPENAI_API_KEY"),
    request_timeout=60,
).bind_tools(amhani_tools)


# ── Tool lookup ───────────────────────────────────────────────
TOOL_MAP = {tool.name: tool for tool in amhani_tools}


# ── System prompt ─────────────────────────────────────────────
SYSTEM_PROMPT = (
    "You are AMHANi, an expert AI financial consultant built by AMHANi Enterprise.\n\n"

    "TOOL SELECTION — follow these exactly:\n"
    "- Any stock ticker (AAPL, TSLA, DANGOTE)      → get_stock_price\n"
    "- Currency conversion (USD→NGN, any FX pair)  → convert_currency\n"
    "- Crypto prices (BTC, ETH, BNB, any coin)     → get_crypto_price\n"
    "- BTC 4-hour / intraday crypto levels         → get_crypto_price input='BTC,4h'\n"
    "- Global market indices snapshot              → get_market_overview\n"
    "- Price-to-Earnings ratio                     → calculate_pe_ratio\n"
    "- Compound interest / loan / ROI / break-even → financial_calculator\n"
    "- Analyse JSON financial data                 → analyse_financial_data\n"
    "- Stock chart or graph                        → generate_stock_chart\n"
    "- Python code / loops / custom calculations   → execute_python\n"
    "- Complex multi-step task                     → plan_task FIRST\n\n"

    "BEHAVIOUR:\n"
    "1. Answer the CURRENT question only. Do not repeat previous answers.\n"
    "2. Never ask clarifying questions for simple requests — use the tool immediately.\n"
    "3. If a tool returns a rate-limit or unavailable message — report it honestly.\n"
    "   Never invent numbers or return NaN to the user.\n"
    "4. Use ₦ for Nigerian Naira. Use $ for USD.\n"
    "5. Be concise and professional."
)


# ── Core agentic loop ─────────────────────────────────────────
def _run_loop(messages: list, max_iterations: int = 10) -> dict:
    """
    Tool-calling loop.
    Sends messages → executes any tool calls → loops until final text answer.
    FIX: Redirects stdout/stderr during execution to prevent UI noise.
    """
    intermediate_steps = []

    # Redirect stdout+stderr during the entire loop
    _old_stdout = sys.stdout
    _old_stderr = sys.stderr
    _dev_null   = io.StringIO()

    try:
        sys.stdout = _dev_null
        sys.stderr = _dev_null

        for _ in range(max_iterations):
            response = llm.invoke(messages)

            # No tool calls — final answer
            if not response.tool_calls:
                sys.stdout = _old_stdout
                sys.stderr = _old_stderr
                return {
                    "output": response.content or "",
                    "intermediate_steps": intermediate_steps,
                }

            # Restore output temporarily so tool results print correctly
            sys.stdout = _old_stdout
            sys.stderr = _old_stderr

            # ── FIX: explicitly reconstruct AIMessage ──────────
            # Appending the raw response object directly caused
            # "bad message format" errors in some LangChain versions.
            # Explicitly building the AIMessage is stable across versions.
            ai_msg = AIMessage(
                content=response.content or "",
                tool_calls=response.tool_calls,
            )
            messages.append(ai_msg)

            # Suppress output again for tool execution
            sys.stdout = _dev_null
            sys.stderr = _dev_null

            for tc in response.tool_calls:
                tool_name  = tc.get("name", "")
                tool_input = tc.get("args", {})
                tool_id    = tc.get("id", "")

                tool_fn = TOOL_MAP.get(tool_name)
                if tool_fn:
                    try:
                        # Normalise dict input to string
                        if isinstance(tool_input, dict):
                            raw = (
                                str(list(tool_input.values())[0])
                                if len(tool_input) == 1
                                else json.dumps(tool_input)
                            )
                        else:
                            raw = str(tool_input) if tool_input else ""

                        # Restore output around tool call so tool's
                        # own print() still works (execute_python etc.)
                        sys.stdout = _old_stdout
                        sys.stderr = _old_stderr
                        result = tool_fn.invoke(raw)
                        sys.stdout = _dev_null
                        sys.stderr = _dev_null

                    except Exception as e:
                        result = f"Tool error: {e}"
                else:
                    result = f"Tool '{tool_name}' not found."

                intermediate_steps.append((tool_name, tool_input, str(result)))
                messages.append(
                    ToolMessage(content=str(result), tool_call_id=tool_id)
                )

        sys.stdout = _old_stdout
        sys.stderr = _old_stderr
        return {
            "output": "Max iterations reached. Please try a simpler request.",
            "intermediate_steps": intermediate_steps,
        }

    except Exception as e:
        sys.stdout = _old_stdout
        sys.stderr = _old_stderr
        raise e


# ── Memory sync ───────────────────────────────────────────────
def sync_memory(messages: list) -> list:
    """
    Convert Streamlit message history to LangChain message objects.
    Returns the last 6 clean user/assistant pairs only.
    Called by app.py — the RETURN VALUE must be passed to run_agent.
    """
    pairs = []
    i = 0
    while i < len(messages) - 1:
        u = messages[i]
        a = messages[i + 1]
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


# ── Public run function ───────────────────────────────────────
def run_agent(
    question: str,
    long_term_context: str = "",
    chat_history: list = None,
) -> dict:
    """
    Run the agent with up to 3 self-correcting retry attempts.

    Args:
        question:           The user's current message (string).
        long_term_context:  Facts from Supabase memory store (optional).
        chat_history:       List of HumanMessage/AIMessage from sync_memory().
    """
    if not question or not question.strip():
        return {"output": "Please enter a question.", "intermediate_steps": []}

    # Prefix long-term context cleanly
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

            result = _run_loop(messages, max_iterations=10)
            output = (result.get("output") or "").strip()
            if output and len(output) > 10:
                return result

        except Exception as e:
            last_error = str(e)
            if attempt < 2:
                full_input = (
                    f"Previous attempt failed: {last_error}. "
                    f"Try a different approach to answer: {question}"
                )

    return {
        "output": (
            f"I could not complete that request after 3 attempts.\n"
            f"Error: {last_error}\n"
            f"Please rephrase or try a simpler request."
        ),
        "intermediate_steps": [],
    }


# ── CLI ───────────────────────────────────────────────────────
if __name__ == "__main__":
    import click

    @click.command()
    @click.option("--ask",     default=None, help="Single question")
    @click.option("--repl",    is_flag=True,  help="Interactive mode")
    @click.option("--verbose", is_flag=True,  help="Show reasoning steps")
    def cli(ask, repl, verbose):
        if ask:
            result = run_agent(ask)
            print("\n── AMHANi ──────────────────────────────")
            print(result["output"])
            if verbose:
                steps = result.get("intermediate_steps", [])
                for i, step in enumerate(steps):
                    print(f"\nStep {i+1}: {step[0]}")
                    print(f"  Input:  {str(step[1])[:200]}")
                    print(f"  Result: {str(step[2])[:300]}")

        elif repl:
            print("AMHANi Agent — type 'exit' to quit\n")
            history = []
            while True:
                q = input("You: ").strip()
                if q.lower() in ("exit", "quit"):
                    break
                if not q:
                    continue
                result = run_agent(q, chat_history=history)
                answer = result["output"]
                print(f"\nAMHANi: {answer}\n")
                history.append(HumanMessage(content=q))
                history.append(AIMessage(content=answer))
        else:
            print("Use --ask 'question' or --repl for interactive mode.")

    cli()
