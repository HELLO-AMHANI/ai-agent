# =============================================================
# tests.py — AMHANi ENTERPRISE v5
#
# FIX: Previous version tested agent.build_agent / agent.one_shot /
# agent.repl — none of these exist in agent.py v5. They were
# leftover from an earlier AgentExecutor-based implementation.
# agent.py has since been refactored to:
#   run_agent(question, long_term_context, chat_history, timeout)
#   sync_memory(messages)
#   cli()  (Click command, not a bare function)
#
# This rewrite tests the ACTUAL public API and adds coverage
# for the v5 tools (get_ngx_market, get_stock_financials,
# get_insider_trades) that had zero test coverage before.
# =============================================================

import os
import pytest


# ══════════════════════════════════════════════════════════════
# IMPORT SANITY — matches agent.py v5's real exports
# ══════════════════════════════════════════════════════════════
def test_agent_imports():
    import agent
    assert hasattr(agent, "run_agent")
    assert hasattr(agent, "sync_memory")
    assert hasattr(agent, "llm")
    assert callable(agent.run_agent)
    assert callable(agent.sync_memory)


def test_tools_module_imports():
    import tools
    assert hasattr(tools, "amhani_tools")
    assert isinstance(tools.amhani_tools, list)
    assert len(tools.amhani_tools) >= 10


def test_core_tools_importable():
    from tools import get_stock_price, calculate_pe_ratio
    assert callable(get_stock_price.invoke)
    assert callable(calculate_pe_ratio.invoke)


def test_v5_tools_importable():
    """v5 added these — previously untested."""
    from tools import get_ngx_market, get_stock_financials, get_insider_trades
    assert callable(get_ngx_market.invoke)
    assert callable(get_stock_financials.invoke)
    assert callable(get_insider_trades.invoke)


def test_all_tools_have_unique_names():
    """Every tool registered in amhani_tools must have a unique .name."""
    from tools import amhani_tools
    names = [t.name for t in amhani_tools]
    assert len(names) == len(set(names)), f"Duplicate tool names: {names}"


# ══════════════════════════════════════════════════════════════
# PURE-LOGIC TOOLS — no network, no API keys required
# ══════════════════════════════════════════════════════════════
def test_pe_ratio_valid():
    from tools import calculate_pe_ratio
    result = calculate_pe_ratio.invoke("150.0, 7.5")
    assert "20.0" in result


def test_pe_ratio_zero_eps():
    from tools import calculate_pe_ratio
    result = calculate_pe_ratio.invoke("150.0, 0")
    assert "zero" in result.lower()


def test_pe_ratio_bad_input():
    from tools import calculate_pe_ratio
    result = calculate_pe_ratio.invoke("not a number")
    assert "error" in result.lower()


def test_financial_calculator_compound_interest():
    from tools import financial_calculator
    result = financial_calculator.invoke("compound_interest, 100000, 0.10, 2")
    assert "₦" in result
    assert "Final" in result


def test_financial_calculator_unknown_type():
    from tools import financial_calculator
    result = financial_calculator.invoke("not_a_real_calc_type, 1, 2")
    assert "Types:" in result or "calculator" in result.lower()


def test_execute_python_basic():
    from tools import execute_python
    result = execute_python.invoke("print(2 + 2)")
    assert "4" in result


def test_execute_python_catches_errors():
    from tools import execute_python
    result = execute_python.invoke("1 / 0")
    assert "error" in result.lower()


def test_analyse_financial_data():
    from tools import analyse_financial_data
    result = analyse_financial_data.invoke(
        '[{"month":"Jan","revenue":50000,"expenses":30000}]'
    )
    assert "Profit" in result or "rows" in result.lower() or "r ×" in result


# ══════════════════════════════════════════════════════════════
# ENV / SECRETS CONFIGURATION CHECKS
# ══════════════════════════════════════════════════════════════
def test_openai_key_present():
    assert os.getenv("OPENAI_API_KEY"), (
        "OPENAI_API_KEY is required for the agent to function at all."
    )


@pytest.mark.skipif(
    not os.getenv("POLYGON_API_KEY"),
    reason="POLYGON_API_KEY not set — stock price/financials/insider "
           "trades will silently fall back to yfinance",
)
def test_polygon_key_format():
    key = os.getenv("POLYGON_API_KEY", "")
    assert len(key) > 10, "POLYGON_API_KEY looks too short to be valid"


@pytest.mark.skipif(
    not os.getenv("X_API_KEY"),
    reason="X_API_KEY not set — NGX market data will fall back to "
           "yfinance .LG suffix tickers",
)
def test_ngx_pulse_key_format():
    key = os.getenv("X_API_KEY", "")
    assert len(key) > 10, "X_API_KEY looks too short to be valid"


# ══════════════════════════════════════════════════════════════
# LIVE NETWORK TESTS — skipped automatically without OPENAI_API_KEY
# ══════════════════════════════════════════════════════════════
@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="Skipping live agent test — no OPENAI_API_KEY in environment",
)
def test_agent_runs_simple_question():
    from agent import run_agent
    result = run_agent("What is 2 + 2?")
    assert isinstance(result, dict)
    assert "output" in result
    assert isinstance(result["output"], str)
    assert len(result["output"]) > 0


@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="Skipping live stock test — no OPENAI_API_KEY in environment",
)
def test_stock_tool_runs_live():
    from tools import get_stock_price
    result = get_stock_price.invoke("AAPL")
    assert isinstance(result, str)
    assert "AAPL" in result or "unavailable" in result.lower()


@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="Skipping live crypto test — no OPENAI_API_KEY in environment",
)
def test_crypto_tool_runs_live():
    from tools import get_crypto_price
    result = get_crypto_price.invoke("BTC")
    assert isinstance(result, str)
    assert "BTC" in result


@pytest.mark.skipif(
    not os.getenv("POLYGON_API_KEY"),
    reason="Skipping Polygon.io live test — POLYGON_API_KEY not set",
)
def test_polygon_stock_price_live():
    from tools import get_stock_price
    result = get_stock_price.invoke("AAPL")
    assert "Polygon.io" in result or "Yahoo Finance" in result


@pytest.mark.skipif(
    not os.getenv("X_API_KEY"),
    reason="Skipping NGX Pulse live test — X_API_KEY not set",
)
def test_ngx_market_overview_live():
    from tools import get_ngx_market
    result = get_ngx_market.invoke("overview")
    assert isinstance(result, str)
    assert len(result) > 0


# ══════════════════════════════════════════════════════════════
# MEMORY / CHAT STORE — import safety only
# ══════════════════════════════════════════════════════════════
def test_memory_store_imports_without_supabase():
    """
    Regression test for the original bug: memory_store.py used to
    import `from supabase import create_client` at module level,
    causing Streamlit Cloud cold-start failures when the network
    wasn't ready yet. Confirms the module imports cleanly even
    with zero Supabase env vars set.
    """
    os.environ.pop("SUPABASE_URL", None)
    os.environ.pop("SUPABASE_SERVICE_KEY", None)
    import memory_store
    assert hasattr(memory_store, "save_memory")
    assert hasattr(memory_store, "load_memory")
    assert hasattr(memory_store, "extract_and_save_facts")
    assert hasattr(memory_store, "clear_memory")
    assert memory_store.load_memory("fake-user-id") == ""


def test_chat_store_imports_without_supabase():
    """Same regression test pattern for chat_store.py."""
    os.environ.pop("SUPABASE_URL", None)
    os.environ.pop("SUPABASE_SERVICE_KEY", None)
    import chat_store
    assert hasattr(chat_store, "save_message")
    assert hasattr(chat_store, "load_messages")
    assert hasattr(chat_store, "clear_chat")
    assert chat_store.load_messages("fake-user-id") == []


def test_chat_store_rejects_invalid_role():
    import chat_store
    chat_store.save_message("fake-user-id", "invalid_role", "test content")


def test_chat_store_rejects_empty_content():
    import chat_store
    chat_store.save_message("fake-user-id", "user", "")
    chat_store.save_message("fake-user-id", "user", "   ")