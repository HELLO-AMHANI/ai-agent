# agent.py — CONSULTAMHANi | AI Agent Core
# Uses config.py for all secrets — works locally AND on Streamlit Cloud

import argparse
from config import OPENAI_API_KEY, OPENAI_MODEL, AGENT_NAME as DEFAULT_AGENT_NAME, SERPAPI_API_KEY

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

# ── Safe import for create_tool_calling_agent ─────────────────────────────────
try:
    from langchain.agents import create_tool_calling_agent, AgentExecutor
except ImportError:
    try:
        from langchain_core.agents import create_tool_calling_agent
        from langchain.agents import AgentExecutor
    except ImportError:
        from langchain.agents.tool_calling_agent.base import create_tool_calling_agent
        from langchain.agents import AgentExecutor

from tools import get_stock_price, calculate_pe_ratio


def build_tools():
    tools = [get_stock_price, calculate_pe_ratio]

    # Optional SerpAPI web search
    if SERPAPI_API_KEY:
        try:
            from langchain_community.utilities import SerpAPIWrapper
            from langchain_core.tools import Tool
            search = SerpAPIWrapper(serpapi_api_key=SERPAPI_API_KEY)
            tools.append(
                Tool(
                    name="WebSearch",
                    func=search.run,
                    description=(
                        "Search the web for recent financial news, market events, "
                        "or facts. Input should be a plain search query string."
                    ),
                )
            )
        except Exception:
            pass

    return tools


def get_prompt(agent_name: str):
    return ChatPromptTemplate.from_messages([
        (
            "system",
            f"You are {agent_name}, a professional AI-powered financial research "
            f"assistant for AMHANi Enterprise. "
            f"Help users with stock prices, financial analysis, market research, "
            f"P/E ratios, investment insights, and business financial advice. "
            f"Always be concise, accurate, and data-driven. "
            f"Work with facts — never give vague or speculative advice. "
            f"Format numbers clearly. Be professional but approachable."
        ),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])


def build_agent(agent_name: str = DEFAULT_AGENT_NAME, verbose: bool = False):
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is missing.\n"
            "Local: add it to your .env file.\n"
            "Streamlit Cloud: add it in App Settings → Secrets."
        )

    llm = ChatOpenAI(
        model=OPENAI_MODEL,
        temperature=1,
        openai_api_key=OPENAI_API_KEY,
    )

    tools  = build_tools()
    prompt = get_prompt(agent_name)

    agent = create_tool_calling_agent(llm=llm, tools=tools, prompt=prompt)

    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=verbose,
        handle_parsing_errors=True,
        max_iterations=8,
        return_intermediate_steps=False,
    )

    return executor


# ── CLI usage ──────────────────────────────────────────────────────────────────
def repl(executor, agent_name):
    print(f"\n{agent_name} ready. Type your question or 'exit' to quit.\n")
    while True:
        try:
            user_input = input(">> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            break
        if not user_input:
            continue
        if user_input.lower() in {"quit", "exit"}:
            print("Goodbye.")
            break
        try:
            result   = executor.invoke({"input": user_input})
            response = result.get("output", "No response generated.")
            print(f"\n{agent_name}: {response}\n")
        except Exception as e:
            print(f"\nError: {e}\n")


def one_shot(executor, prompt_text):
    result = executor.invoke({"input": prompt_text})
    return result.get("output", "No response generated.")


def main():
    parser = argparse.ArgumentParser(description="Run the CONSULTAMHANi CLI Agent")
    parser.add_argument("--repl",    action="store_true", help="Interactive REPL mode")
    parser.add_argument("--ask",     type=str,            help="Ask a single question")
    parser.add_argument("--name",    type=str,            help="Override agent name")
    parser.add_argument("--verbose", action="store_true", help="Show reasoning steps")
    args = parser.parse_args()

    agent_name = args.name or DEFAULT_AGENT_NAME
    print(f"Loading {agent_name} (model: {OPENAI_MODEL})...")

    try:
        executor = build_agent(agent_name=agent_name, verbose=args.verbose)
    except RuntimeError as e:
        print(f"Startup error: {e}")
        return

    if args.repl:
        repl(executor, agent_name)
    elif args.ask:
        print(f"\n{agent_name}: {one_shot(executor, args.ask)}")
    else:
        print("\nOptions:")
        print("  --repl              Interactive chat")
        print('  --ask "question"    Single question')
        print("  --verbose           Show reasoning")
        print("  --name NAME         Override agent name")


if __name__ == "__main__":
    main()
