# tests/smoke_test.py
import pytest

def test_imports():
    import agent
    assert hasattr(agent, "build_agent")
    assert hasattr(agent, "one_shot")
    assert hasattr(agent, "repl")

def test_tools_importable():
    from tools import get_stock_price, calculate_pe_ratio
    assert callable(get_stock_price)
    assert callable(calculate_pe_ratio)

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

@pytest.mark.skipif(
    not __import__('os').getenv("OPENAI_API_KEY"),
    reason="Skipping live agent test — no API key in environment"
)
def test_agent_builds():
    from agent import build_agent
    executor = build_agent(agent_name="TestAgent")
    assert executor is not None

@pytest.mark.skipif(
    not __import__('os').getenv("OPENAI_API_KEY"),
    reason="Skipping live stock test — no API key in environment"
)
def test_stock_tool_runs():
    from tools import get_stock_price
    result = get_stock_price.invoke("AAPL")
    assert isinstance(result, str)
    assert "AAPL" in result or "Error" in result
