# agent.py — AMHANi ENTERPRISE
# Uses LCEL — no AgentExecutor, works on all Python versions

import os
from dotenv import load_dotenv
load_dotenv()

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from langchain.agents import create_tool_calling_agent
from langchain.agents import AgentExecutor
from tools import amhani_tools

# ── LLM ──────────────────────────────────────────────────────
llm = ChatOpenAI(
    model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    temperature=1,
    api_key=os.getenv("OPENAI_API_KEY"),
    request_timeout=60,
)

# ── Prompt ────────────────────────────────────────────────────
agent_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are AMHANi, an expert AI financial consultant built by AMHANi Enterprise. "
     "You help clients with financial planning, investment advisory, business "
     "development, market research, data analysis, and financial calculations.\n\n"
     "Rules:\n"
     "- For complex multi-step requests, use plan_task first\n"
     "- For code tasks: write AND run code in execute_python\n"
     "- Work with facts and verified data only — never guesswork\n"
     "- Use ₦ for Nigerian Naira where relevant\n"
     "- Be transparent, concise, and professional"),
    MessagesPlaceholder("chat_history", optional=True),
    ("human", "{input}"),
    MessagesPlaceholder("agent_scratchpad"),
])

# ── Agent ─────────────────────────────────────────────────────
_agent = create_tool_calling_agent(
    llm=llm,
    tools=amhani_tools,
    prompt=agent_prompt,
)

agent_executor = AgentExecutor(
    agent=_agent,
    tools=amhani_tools,
    verbose=True,
    max_iterations=10,
    max_execution_time=90,
    handle_parsing_errors=True,
    return_intermediate_steps=True,
)

# ── Short-term memory (in-memory, per session) ────────────────
# Stored as plain list — no LangChain memory class needed
# This avoids all version-specific memory import issues

def sync_memory(messages: list) -> list:
    """
    Convert Streamlit message history to LangChain message objects.
    Returns a list of HumanMessage / AIMessage for chat_history.
    """
    history = []
    for msg in messages:
        if msg.get("role") == "user":
            history.append(HumanMessage(content=msg["content"]))
        elif msg.get("role") == "assistant":
            history.append(AIMessage(content=msg["content"]))
    return history


# ── Main run function ─────────────────────────────────────────
def run_agent(
    question: str,
    long_term_context: str = "",
    chat_history: list = None,
) -> dict:
    """
    Run the agent with retry and self-correction.
    chat_history: list of LangChain message objects from sync_memory()
    """
    full_input = question
    if long_term_context and long_term_context.strip():
        full_input = (
            f"{long_term_context.strip()}\n\nCurrent question: {question}"
        )

    history = chat_history or []
    last_error = None

    for attempt in range(3):
        try:
            result = agent_executor.invoke({
                "input": full_input,
                "chat_history": history,
            })
            output = result.get("output", "")
            if output and len(output.strip()) > 10:
                return result
        except Exception as e:
            last_error = str(e)
            if attempt < 2:
                full_input = (
                    f"Previous attempt failed: {last_error}\n"
                    f"Try a different approach to answer: {question}"
                )

    return {
        "output": (
            "I encountered a technical issue after 3 attempts.\n"
            f"Error: {last_error}\n\n"
            "Please rephrase your question or try a simpler request."
        ),
        "intermediate_steps": [],
    }


# ── CLI ───────────────────────────────────────────────────────
if __name__ == "__main__":
    import click

    @click.command()
    @click.option("--ask",     default=None, help="Single question")
    @click.option("--repl",    is_flag=True, help="Interactive mode")
    @click.option("--verbose", is_flag=True, help="Show steps")
    def cli(ask, repl, verbose):
        if ask:
            result = run_agent(ask)
            print("\n── AMHANi ──────────────────────────────")
            print(result["output"])
            if verbose:
                for i, (action, obs) in enumerate(
                    result.get("intermediate_steps", [])
                ):
                    print(f"\nStep {i+1}: {action.tool}")
                    print(f"  Input:  {str(action.tool_input)[:200]}")
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
            print("Use --ask 'question' or --repl")

    cli()
