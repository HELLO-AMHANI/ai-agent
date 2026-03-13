# agent.py — AMHANi | CONSULTAMHANi Agent
# All secrets loaded from config.py (works locally AND on Streamlit Cloud)

import argparse
from config import OPENAI_API_KEY, OPENAI_MODEL, AGENT_NAME as DEFAULT_AGENT_NAME

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import create_tool_calling_agent, AgentExecutor

from tools import get_stock_price, calculate_pe_ratio


def build_tools():
    tools = [get_stock_price, calculate_pe_ratio]

    # Optional SerpAPI web search
    try:
        from config import get_secret
        serp_key = get_secret("SERPAPI_API_KEY")
        if serp_key:
            from langchain_community.utilities import SerpAPIWrapper
            from langchain_core.tools import Tool
            search = SerpAPIWrapper(serpapi_api_key=serp_key)
            tools.append(
                Tool(
                    name="WebSearch",
                    func=search.run,
                    description=(
                        "Search the web for recent news, events, or facts. "
                        "Input should be a plain search query string."
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
            f"You are {agent_name}, a professional AI-powered financial research assistant "
            f"for AMHANi Enterprise. Help users with stock prices, financial analysis, "
            f"market research, P/E ratios, and investment insights. "
            f"Always be concise, accurate, and data-driven. "
            f"Never give vague advice — work with facts, not rule of thumb."
        ),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])


def build_agent(agent_name: str = DEFAULT_AGENT_NAME, verbose: bool = False):
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is missing.\n"
            "Locally: add it to your .env file.\n"
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
    )

    return executor


# ── CLI usage ──────────────────────────────────────────────────────────────────
def repl(executor, agent_name):
    print(f"\n{agent_name} is ready. Type your question or 'exit' to quit.\n")
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
    parser = argparse.ArgumentParser(description="Run the AMHANi CLI Agent")
    parser.add_argument("--repl",    action="store_true", help="Start interactive REPL mode")
    parser.add_argument("--ask",     type=str,            help="Ask a single question and exit")
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
        answer = one_shot(executor, args.ask)
        print(f"\n{agent_name}: {answer}")
    else:
        print("\nNo mode selected.")
        print("  --repl              Start interactive chat")
        print('  --ask "question"    Ask a single question')
        print("  --verbose           Show reasoning steps")
        print("  --name NAME         Override agent name")


if __name__ == "__main__":
    main()
