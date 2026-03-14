# =============================================================
# agent.py — AMHANi ENTERPRISE · Full Agentic Engine
# FILE 3 OF 7 — FULL REPLACEMENT
# Delete everything in your existing agent.py and paste this.
# =============================================================

import os
from dotenv import load_dotenv
load_dotenv()

from langchain_openai import ChatOpenAI
try:
    from langchain.agents import AgentExecutor
except ImportError:
    from langchain_core.agents import AgentExecutor

try:
    from langchain.agents import create_tool_calling_agent
except ImportError:
    from langchain_core.agent import create_tool_calling_agent

# ── ConversationBufferWindowMemory — works across LangChain versions ──
try:
    from langchain.memory import ConversationBufferWindowMemory
except ImportError:
    try:
        from langchain_community.memory import ConversationBufferWindowMemory
    except ImportError:
        # Fallback: minimal in-memory replacement so app never crashes
        class ConversationBufferWindowMemory:
            def __init__(self, **kwargs):
                self._history = []
                self.memory_key = kwargs.get("memory_key", "chat_history")
                self.k = kwargs.get("k", 10)

            def clear(self):
                self._history = []

            def save_context(self, inp, out):
                self._history.append((inp.get("input", ""), out.get("output", "")))
                if len(self._history) > self.k:
                    self._history = self._history[-self.k:]

            def load_memory_variables(self, _):
                lines = []
                for u, a in self._history:
                    lines.append(f"Human: {u}")
                    lines.append(f"Assistant: {a}")
                return {self.memory_key: "\n".join(lines)}

from tools import amhani_tools


# ── LLM ──────────────────────────────────────────────────────
from langchain_openai import ChatOpenAI as _BaseChatOpenAI

class _PatchedLLM(_BaseChatOpenAI):
    """Drop the 'stop' parameter which gpt-5-mini does not support."""
    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        return super()._get_request_payload(input_, stop=None, **kwargs)

llm = _PatchedLLM(
    model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
    temperature=1,
    api_key=os.getenv("OPENAI_API_KEY"),
    request_timeout=60,
)

# ── Short-term memory (last 10 exchanges per session) ─────────
memory = ConversationBufferWindowMemory(
    k=10,
    memory_key="chat_history",
    return_messages=True,
    input_key="input",
    output_key="output",
)

# ── ReAct Prompt ──────────────────────────────────────────────
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

agent_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are AMHANi, an expert AI financial consultant built by AMHANi Enterprise. "
     "You help clients with financial planning, investment advisory, business development, "
     "market research, data analysis, and Python-powered financial calculations.\n\n"
     "Rules:\n"
     "- For complex multi-step requests, use plan_task first\n"
     "- For code tasks: write AND run code in execute_python — never just describe it\n"
     "- Work with facts and verified data only — never guesswork\n"
     "- Use ₦ for Nigerian Naira where relevant\n"
     "- Be transparent, concise, and professional"),
    MessagesPlaceholder("chat_history", optional=True),
    ("human", "{input}"),
    MessagesPlaceholder("agent_scratchpad"),
])

# ── Agent + Executor ──────────────────────────────────────────
_agent = create_tool_calling_agent(
    llm=llm,
    tools=amhani_tools,
    prompt=agent_prompt,
)
agent_executor = AgentExecutor(
    agent=_agent,
    tools=amhani_tools,
    memory=memory,
    verbose=True,
    max_iterations=10,
    max_execution_time=90,
    handle_parsing_errors=True,       # Self-corrects malformed outputs
    return_intermediate_steps=True,   # Exposes reasoning steps to UI
)


# ── Main entry point ──────────────────────────────────────────
def run_agent(question: str, long_term_context: str = "") -> dict:
    """
    Run the agent with automatic retry and self-correction.
    Injects long-term memory context when available.

    Returns a dict with keys:
      'output'             — final answer string
      'intermediate_steps' — list of (action, observation) tuples
    """
    # Build full input, injecting long-term context if present
    full_input = question
    if long_term_context and long_term_context.strip():
        full_input = (
            f"{long_term_context.strip()}\n\nCurrent question: {question}"
        )

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
                # Feed the error back so the agent tries a different approach
                full_input = (
                    f"Your previous attempt raised this error: {last_error}\n"
                    f"Please try a completely different approach to answer: "
                    f"{question}"
                )

    return {
        "output": (
            "I encountered a technical issue and could not complete your "
            f"request after 3 attempts.\nLast error: {last_error}\n\n"
            "Please try rephrasing your question or break it into smaller parts."
        ),
        "intermediate_steps": [],
    }


# ── Memory sync helper (called by app.py) ─────────────────────
def sync_memory(messages: list) -> None:
    """
    Sync Streamlit's chat history list into LangChain's short-term
    memory so the agent knows what was said earlier in the session.
    Call this BEFORE every agent invocation in app.py.
    """
    memory.clear()
    # messages is a flat list: [user, assistant, user, assistant, ...]
    for i in range(0, len(messages) - 1, 2):
        if i + 1 < len(messages):
            u = messages[i]
            a = messages[i + 1]
            if u.get("role") == "user" and a.get("role") == "assistant":
                memory.save_context(
                    {"input":  u["content"]},
                    {"output": a["content"]},
                )


# ── CLI (for local testing) ───────────────────────────────────
if __name__ == "__main__":
    import click

    @click.command()
    @click.option("--ask",     default=None,  help="Ask a single question")
    @click.option("--repl",    is_flag=True,  help="Start interactive mode")
    @click.option("--verbose", is_flag=True,  help="Show reasoning steps")
    def cli(ask, repl, verbose):
        if ask:
            result = run_agent(ask)
            print("\n── AMHANi ──────────────────────────────")
            print(result["output"])
            if verbose:
                steps = result.get("intermediate_steps", [])
                if steps:
                    print(f"\n── Reasoning ({len(steps)} steps) ──────────")
                    for i, (action, obs) in enumerate(steps):
                        print(f"\nStep {i + 1}: {action.tool}")
                        print(f"  Input: {str(action.tool_input)[:200]}")
                        print(f"  Result: {str(obs)[:300]}")

        elif repl:
            print("AMHANi Agent  —  type 'exit' to quit\n")
            while True:
                q = input("You: ").strip()
                if q.lower() in ("exit", "quit", "q"):
                    print("Goodbye.")
                    break
                if not q:
                    continue
                result = run_agent(q)
                print(f"\nAMHANi: {result['output']}\n")
        else:
            print("Use --ask 'your question' or --repl for interactive mode.")

    cli()
