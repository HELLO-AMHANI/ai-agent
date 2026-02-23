# agent.py
import os
import argparse
from dotenv import load_dotenv

load_dotenv()

from langchain_openai import ChatOpenAI
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

# Local tools
from tools import get_stock_price, calculate_pe_ratio

DEFAULT_AGENT_NAME = os.getenv("AGENT_NAME", "AMHANi")


def get_prompt(agent_name: str):
    """
    Tool-calling agents use a ChatPromptTemplate — no stop sequences needed.
    """
    return ChatPromptTemplate.from_messages([
        (
            "system",
            f"You are {agent_name}, a helpful financial research assistant. "
            "Use your tools to look up stock prices and calculate financial metrics. "
            "Always be concise and accurate."
        ),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),  # required for tool calls
    ])


def build_tools():
    tools = [get_stock_price, calculate_pe_ratio]

    serp_key = os.getenv("SERPAPI_API_KEY")
    if serp_key:
        try:
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
            print("SerpAPI web search tool enabled.")
        except ImportError:
            print("Warning: SerpAPI not available. Run: pip install google-search-results")

    return tools


def build_agent(agent_name: str = DEFAULT_AGENT_NAME, verbose: bool = False):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is missing. Add it to your .env file:\n  OPENAI_API_KEY=sk-..."
        )

    model_name = os.getenv("OPENAI_MODEL", "gpt-5-mini")

    llm = ChatOpenAI(
        model=model_name,
        temperature=1,
        openai_api_key=api_key,
    )

    tools = build_tools()
    prompt = get_prompt(agent_name)

    # create_tool_calling_agent — no stop sequences, works with gpt-5-mini
    agent = create_tool_calling_agent(llm=llm, tools=tools, prompt=prompt)

    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=verbose,
        handle_parsing_errors=True,
        max_iterations=8,
    )

    return executor


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
            result = executor.invoke({"input": user_input})
            response = result.get("output", "No response generated.")
            print(f"\n{agent_name}: {response}\n")
        except Exception as e:
            print(f"\nError: {e}\n")


def one_shot(executor, prompt_text):
    result = executor.invoke({"input": prompt_text})
    return result.get("output", "No response generated.")


def main():
    parser = argparse.ArgumentParser(description="Run the AI Agent CLI")
    parser.add_argument("--repl", action="store_true", help="Start interactive REPL mode")
    parser.add_argument("--ask", type=str, help="Ask a single question and exit")
    parser.add_argument("--name", type=str, help="Name this agent instance")
    parser.add_argument("--verbose", action="store_true", help="Show agent reasoning steps")
    args = parser.parse_args()

    agent_name = args.name or os.getenv("AGENT_NAME", DEFAULT_AGENT_NAME)

    print(f"Loading {agent_name} (model: {os.getenv('OPENAI_MODEL', 'gpt-5-mini')})...")

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
        print("\nNo mode selected. Options:")
        print("  --repl              Start interactive chat")
        print('  --ask "question"    Ask a single question')
        print("  --verbose           Show step-by-step reasoning")
        print("  --name NAME         Set the agent's name")


if __name__ == "__main__":
    main()
