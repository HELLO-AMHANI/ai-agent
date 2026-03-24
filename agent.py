# =============================================================
# agent.py — AMHANi ENTERPRISE
# Custom tool-calling loop — no AgentExecutor dependency
# Python 3.11 / 3.12 / 3.13 compatible
# =============================================================

import os
import json
import logging
from dotenv import load_dotenv
load_dotenv()

# ── Suppress LangChain verbose logs (fixes CONNECTING / RUNNING) ──
logging.getLogger("langchain").setLevel(logging.ERROR)
logging.getLogger("langchain_core").setLevel(logging.ERROR)
logging.getLogger("openai").setLevel(logging.ERROR)

from langchain_openai import ChatOpenAI
from langchain_core.messages import (
    HumanMessage, AIMessage, SystemMessage, ToolMessage
)
from tools import amhani_tools


# ── LLM — bind tools so it can call them ─────────────────────
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
    "You are AMHANi, an expert AI financial consultant built by AMHANi Enterprise. "
    "You help clients with financial planning, investment advisory, business "
    "development, market research, data analysis, and financial calculations.\n\n"

    "TOOL SELECTION RULES — follow these exactly, every time:\n"
    "- Stock price for any ticker (AAPL, TSLA etc)  → get_stock_price\n"
    "- Currency conversion (USD to NGN, any FX)     → convert_currency\n"
    "- Crypto prices (BTC, ETH, BNB, any coin)      → get_crypto_price\n"
    "- BTC 4-hour levels / intraday crypto          → get_crypto_price with '4h'\n"
    "- Global market indices / market snapshot      → get_market_overview\n"
    "- Price-to-Earnings ratio                      → calculate_pe_ratio\n"
    "- Compound interest / loan / ROI / break-even  → financial_calculator\n"
    "- Analyse tabular or JSON financial data       → analyse_financial_data\n"
    "- Stock price chart or graph                   → generate_stock_chart\n"
    "- Python code / loops / custom calculations    → execute_python\n"
    "- Complex multi-step task                      → plan_task FIRST\n\n"

    "STRICT BEHAVIOUR:\n"
    "1. Answer the CURRENT question only. Never repeat or rehash previous answers.\n"
    "2. Never ask clarifying questions for simple requests — execute the tool immediately.\n"
    "3. If a live data tool fails or returns NaN — say so clearly and honestly. "
    "   Never return NaN or invented numbers to the user.\n"
    "4. Use ₦ for Nigerian Naira. Use $ for USD.\n"
    "5. Be concise and professional in every response."
)


# ── Core agentic loop ─────────────────────────────────────────
def _run_loop(messages: list, max_iterations: int = 10) -> dict:
    """
    Core tool-calling loop:
    1. Send messages to LLM
    2. If LLM calls tools → run them → append results → loop again
    3. If LLM returns plain text → that is the final answer
    """
    intermediate_steps = []

    for _ in range(max_iterations):
        response = llm.invoke(messages)

        # No tool calls — this is the final answer
        if not response.tool_calls:
            return {
                "output": response.content,
                "intermediate_steps": intermediate_steps,
            }

        # Append assistant message with tool calls
        messages.append(response)

        # Execute every tool the LLM requested
        for tool_call in response.tool_calls:
            tool_name  = tool_call["name"]
            tool_input = tool_call["args"]
            tool_id    = tool_call["id"]

            tool_fn = TOOL_MAP.get(tool_name)
            if tool_fn:
                try:
                    # Tools accept a single string — normalise dict inputs
                    if isinstance(tool_input, dict):
                        if len(tool_input) == 1:
                            raw_input = str(list(tool_input.values())[0])
                        else:
                            raw_input = json.dumps(tool_input)
                    else:
                        raw_input = str(tool_input) if tool_input else ""

                    result = tool_fn.invoke(raw_input)
                except Exception as e:
                    result = f"Tool error: {e}"
            else:
                result = f"Tool '{tool_name}' not found."

            # Store for reasoning expander in UI
            intermediate_steps.append((tool_name, tool_input, str(result)))

            # Append tool result back into message thread
            messages.append(
                ToolMessage(content=str(result), tool_call_id=tool_id)
            )

    return {
        "output": (
            "Reached maximum iterations without a final answer. "
            "Please try a simpler or more specific request."
        ),
        "intermediate_steps": intermediate_steps,
    }


# ── Memory sync ───────────────────────────────────────────────
def sync_memory(messages: list) -> list:
    """
    Convert Streamlit message history into LangChain message objects.
    Returns only the last 6 clean user/assistant pairs to avoid context bloat.
    Skips any message with empty or None content.
    Called by app.py — return value is passed to run_agent as chat_history.
    """
    pairs = []
    i = 0
    # Build pairs — only confirmed user+assistant sequences
    while i < len(messages) - 1:
        u = messages[i]
        a = messages[i + 1]
        if u.get("role") == "user" and a.get("role") == "assistant":
            u_content = (u.get("content") or "").strip()
            a_content = (a.get("content") or "").strip()
            if u_content and a_content:
                pairs.append((u_content, a_content[:500]))
        i += 2

    # Keep only last 6 pairs
    history = []
    for u_content, a_content in pairs[-6:]:
        history.append(HumanMessage(content=u_content))
        history.append(AIMessage(content=a_content))

    return history


# ── Public run function ───────────────────────────────────────
def run_agent(
    question: str,
    long_term_context: str = "",
    chat_history: list = None,
) -> dict:
    """
    Run the agent.
    - question: the user's current message
    - long_term_context: facts from Supabase memory (optional, capped at 400 chars)
    - chat_history: list of LangChain HumanMessage/AIMessage objects from sync_memory()
    """
    # Inject long-term context as a lightweight prefix
    if long_term_context and long_term_context.strip():
        full_input = (
            f"[Client context: {long_term_context.strip()[:400]}]\n"
            f"{question}"
        )
    else:
        full_input = str(question) if question else "Hello"

    last_error = None

    for attempt in range(3):
        try:
            # Build message thread fresh each attempt
            messages = [SystemMessage(content=SYSTEM_PROMPT)]

            # Inject prior conversation (short-term memory)
            if chat_history:
                messages.extend(chat_history)

            # Append the current question
            messages.append(HumanMessage(content=full_input))

            result = _run_loop(messages, max_iterations=10)
            output = result.get("output", "")
            if output and len(output.strip()) > 10:
                return result

        except Exception as e:
            last_error = str(e)
            if attempt < 2:
                full_input = (
                    f"Previous attempt failed with error: {last_error}\n"
                    f"Try a completely different approach to answer: {question}"
                )

    return {
        "output": (
            f"I could not complete that request after 3 attempts.\n"
            f"Error: {last_error}\n"
            f"Please rephrase or simplify your question."
        ),
        "intermediate_steps": [],
    }


# ── CLI (local testing only) ──────────────────────────────────
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
            if verbose and result.get("intermediate_steps"):
                print(f"\n── Reasoning ({len(result['intermediate_steps'])} steps) ──")
                for i, step in enumerate(result["intermediate_steps"]):
                    name = step[0] if len(step) > 0 else "unknown"
                    inp  = step[1] if len(step) > 1 else ""
                    obs  = step[2] if len(step) > 2 else ""
                    print(f"\nStep {i + 1}: {name}")
                    print(f"  Input:  {str(inp)[:200]}")
                    print(f"  Result: {str(obs)[:300]}")

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
