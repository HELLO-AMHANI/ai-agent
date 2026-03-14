# agent.py — CONSULTAMHANi | AI Agent Core
# Uses OpenAI client directly — no LangChain, no version conflicts, works on Python 3.14

import json
import argparse
from openai import OpenAI
from config import OPENAI_API_KEY, OPENAI_MODEL, AGENT_NAME as DEFAULT_AGENT_NAME
from tools import TOOLS_SCHEMA, run_tool

SYSTEM_PROMPT = """You are {agent_name}, a professional AI-powered financial research \
assistant for AMHANi Enterprise. Help users with stock prices, financial analysis, \
market research, P/E ratios, investment insights, and business financial advice. \
Always be concise, accurate, and data-driven. Work with facts — never give vague \
or speculative advice. Format numbers clearly. Be professional but approachable."""


class CONSULTAMHANiAgent:
    """
    Direct OpenAI tool-calling agent.
    No LangChain — no version conflicts — works on any Python version.
    """

    def __init__(self, agent_name: str = DEFAULT_AGENT_NAME, verbose: bool = False):
        if not OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY is missing.\n"
                "Local: add it to your .env file.\n"
                "Streamlit Cloud: add it in App Settings → Secrets."
            )
        self.client     = OpenAI(api_key=OPENAI_API_KEY)
        self.model      = OPENAI_MODEL
        self.agent_name = agent_name
        self.verbose    = verbose
        self.system     = SYSTEM_PROMPT.format(agent_name=agent_name)

    def invoke(self, user_input: str) -> str:
        """
        Run the agent on a user question.
        Handles tool calls in a loop until the model gives a final answer.
        Returns the final response string.
        """
        messages = [
            {"role": "system",  "content": self.system},
            {"role": "user",    "content": user_input},
        ]

        max_iterations = 8
        for _ in range(max_iterations):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
            )

            message = response.choices[0].message

            # ── Final answer — no tool calls ──────────────────────────────────
            if not message.tool_calls:
                return message.content or "No response generated."

            # ── Tool calls — execute each one ─────────────────────────────────
            messages.append({
                "role":       "assistant",
                "content":    message.content,
                "tool_calls": [
                    {
                        "id":       tc.id,
                        "type":     "function",
                        "function": {
                            "name":      tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    }
                    for tc in message.tool_calls
                ]
            })

            for tc in message.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tool_args = {}

                if self.verbose:
                    print(f"[Tool] {tool_name}({tool_args})")

                tool_result = run_tool(tool_name, tool_args)

                if self.verbose:
                    print(f"[Result] {tool_result}")

                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      str(tool_result),
                })

        return "Max iterations reached. Please try a simpler question."


def build_agent(agent_name: str = DEFAULT_AGENT_NAME, verbose: bool = False) -> CONSULTAMHANiAgent:
    """Build and return a CONSULTAMHANi agent instance."""
    return CONSULTAMHANiAgent(agent_name=agent_name, verbose=verbose)


# ── CLI ────────────────────────────────────────────────────────────────────────
def repl(agent: CONSULTAMHANiAgent):
    print(f"\n{agent.agent_name} ready. Type your question or 'exit' to quit.\n")
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
            response = agent.invoke(user_input)
            print(f"\n{agent.agent_name}: {response}\n")
        except Exception as e:
            print(f"\nError: {e}\n")


def main():
    parser = argparse.ArgumentParser(description="CONSULTAMHANi CLI Agent")
    parser.add_argument("--repl",    action="store_true", help="Interactive chat mode")
    parser.add_argument("--ask",     type=str,            help="Ask a single question")
    parser.add_argument("--name",    type=str,            help="Override agent name")
    parser.add_argument("--verbose", action="store_true", help="Show tool calls")
    args = parser.parse_args()

    agent_name = args.name or DEFAULT_AGENT_NAME
    print(f"Loading {agent_name} (model: {OPENAI_MODEL})...")

    try:
        agent = build_agent(agent_name=agent_name, verbose=args.verbose)
    except RuntimeError as e:
        print(f"Startup error: {e}")
        return

    if args.repl:
        repl(agent)
    elif args.ask:
        print(f"\n{agent_name}: {agent.invoke(args.ask)}")
    else:
        print("Use --repl for chat or --ask 'question' for a single query.")


if __name__ == "__main__":
    main()
