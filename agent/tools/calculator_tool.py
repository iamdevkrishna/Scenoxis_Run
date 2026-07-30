"""
agent/tools/calculator_tool.py
LangChain @tool wrapper around core/calculator.py.
"""
from langchain_core.tools import tool
from core.calculator import calculate as _calculate


@tool
def calculate(expression: str) -> str:
    """
    Safely evaluate a math expression (e.g. '2 + 2 * 3', 'sqrt(16)', '15% of 200').
    Returns the computed result as a string.
    Never uses Python's eval — powered by asteval.
    """
    result = _calculate(expression)
    if result["error"]:
        return f"Could not evaluate: {result['error']}"
    return f"{result['expression']} = {result['result']}"
