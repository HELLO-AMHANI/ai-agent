# agent.py — AMHANi ENTERPRISE
# Custom tool-calling loop — no AgentExecutor dependency
# Works on Python 3.11, 3.12, 3.13, 3.14

import os
import json
from dotenv import load_dotenv
load_dotenv()

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import BaseTool
from tools import amhani_tools

# ── LLM ──────────────────────────────────────────────────────
llm = ChatOpenAI(
    model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
    temperature=1,
    api_key=os.getenv("OPENAI_API_KEY"),
    request_timeout=60,
).bind_tools(amhani_tools)

# ── Tool lookup map ───────────────────────────────────────────
TOOL_MAP = {tool.name: tool for tool in amhani_tools}

SYSTEM_PROMPT = (
    "You are AMHANi, an expert AI financial consultant built by AMHANi Enterprise. "
    "You help clients with financial planning, investment advisory, business "
    "development, market research, data analysis, and financial calculations.\n\n"
    "Rules:\n"
    "- For complex multi-step requests, use plan_task first\n"
    "- For code tasks: write AND run code in execute_python — never just describe it\n"
    "- Work with facts and verified data only — never guesswork\n"
    "- Use ₦ for Nigerian Naira where relevant\n"
    "- Be transparent, concise, and professional\n"
    "- NEVER ask the user clarifying questions for simple requests — just answer\n"
    "- For currency conversion always use convert_currency tool immediately\n"
    "- For stock prices always use get_stock_price tool immediately\n"
    "- For calculations always compute and return the answer directly\n"
    "- Each question is independent — never repeat previous answers\n"
    "- Always answer exactly what was asked, then stop"
)
# ── Custom agentic loop ───────────────────────────────────────
def _run_loop(messages: list, max_iterations: int = 10) -> dict:
    """
    Core agentic loop:
    1. Send messages to LLM
    2. If LLM calls a tool → run it → append result → loop
    3. If LLM gives a text response → return it
    Repeats up to max_iterations times.
    """
    intermediate_steps = []

    for _ in range(max_iterations):
        response = llm.invoke(messages)

        # No tool calls — final answer
        if not response.tool_calls:
            return {
                "output": response.content,
                "intermediate_steps": intermediate_steps,
            }

        # Process each tool call
        messages.append(response)  # append assistant message with tool calls

        for tool_call in response.tool_calls:
            tool_name  = tool_call["name"]
            tool_input = tool_call["args"]
            tool_id    = tool_call["id"]

            tool = TOOL_MAP.get(tool_name)
            if tool:
                try:
                    # Tools expect a single string — convert dict if needed
                    if isinstance(tool_input, dict):
                        if len(tool_input) == 1:
                            raw_input = str(list(tool_input.values())[0])
                        else:
                            raw_input = json.dumps(tool_input)
                    else:
                        raw_input = str(tool_input)

                    result = tool.invoke(raw_input)
                except Exception as e:
                    result = f"Tool error: {e}"
            else:
                result = f"Tool '{tool_name}' not found."

            intermediate_steps.append((tool_name, tool_input, result))

            # Append tool result as ToolMessage
            from langchain_core.messages import ToolMessage
            messages.append(
                ToolMessage(content=str(result), tool_call_id=tool_id)
            )

    return {
        "output": "Reached maximum iterations without a final answer. Please try a simpler request.",
        "intermediate_steps": intermediate_steps,
    }


# ── Memory sync ───────────────────────────────────────────────
def sync_memory(messages: list) -> list:
    """
    Convert Streamlit message history to LangChain message objects.
    Skips any message with missing or None content.
    """
    history = []
    for msg in messages:
        content = msg.get("content") or ""
        if not content.strip():
            continue
        if msg.get("role") == "user":
            history.append(HumanMessage(content=content))
        elif msg.get("role") == "assistant":
            history.append(AIMessage(content=content))
    return history

# ── Public run function ───────────────────────────────────────

def run_agent(question: str, long_term_context: str = "") -> dict:
    """
    Run the agent. Long-term context is injected as a
    lightweight prefix only — never mixed into the question itself.
    """
    # Keep context injection minimal and clean
    if long_term_context and long_term_context.strip():
        full_input = (
            f"[Client context: {long_term_context.strip()[:400]}]\n"
            f"{question}"
        )
    else:
        full_input = question

    last_error = None

    for attempt in range(3):
        try:
            result = agent_executor.invoke({"input": full_input})
            output = result.get("output", "")
            if output and len(output.strip()) > 10:
                return result
        except Exception as e:
            last_error = str(e)
            if attempt < 2:
                full_input = (
                    f"Previous attempt failed: {last_error}\n"
                    f"Try a different approach: {question}"
                )

    return {
        "output": (
            f"I could not complete that request after 3 attempts.\n"
            f"Error: {last_error}\n"
            f"Please rephrase or simplify your question."
        ),
        "intermediate_steps": [],
    }


def sync_memory(messages: list) -> None:
    """
    Sync only the last 4 exchanges into LangChain memory.
    Less is more — prevents old answers from poisoning new ones.
    """
    memory.clear()
    recent = messages[-8:] if len(messages) > 8 else messages

    for i in range(0, len(recent) - 1, 2):
        if i + 1 < len(recent):
            u = recent[i]
            a = recent[i + 1]
            if u.get("role") == "user" and a.get("role") == "assistant":
                memory.save_context(
                    {"input":  u["content"]},
                    {"output": a["content"][:400]},  # cap old answers
                )

# ── CLI ───────────────────────────────────────────────────────
if __name__ == "__main__":
    import click

    @click.command()
    @click.option("--ask",     default=None, help="Ask a single question")
    @click.option("--repl",    is_flag=True,  help="Interactive REPL mode")
    @click.option("--verbose", is_flag=True,  help="Show reasoning steps")
    def cli(ask, repl, verbose):
        if ask:
            result = run_agent(ask)
            print("\n── AMHANi ──────────────────────────────")
            print(result["output"])
            if verbose and result.get("intermediate_steps"):
                print(f"\n── Reasoning ({len(result['intermediate_steps'])} steps) ──")
                for i, (name, inp, obs) in enumerate(result["intermediate_steps"]):
                    print(f"\nStep {i+1}: {name}")
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

# Patched sync_memory — override the one defined above
def sync_memory(messages: list) -> list:
    history = []
    for msg in messages:
        content = msg.get("content") or ""
        if not content.strip():
            continue
        if msg.get("role") == "user":
            history.append(HumanMessage(content=content))
        elif msg.get("role") == "assistant":
            history.append(AIMessage(content=content))
    return history
