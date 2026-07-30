"""
core/calculator.py
Safe math expression evaluator using asteval.
Detects arithmetic intent via regex before touching asteval so the classifier
can make the decision with zero library overhead.
"""
import re
import logging
from typing import Optional

log = logging.getLogger(__name__)

# Regex: matches expressions that look like arithmetic.
# Allows digits, operators, parens, %, decimal points, spaces.
# Anchored so "open chrome" doesn't match.
_ARITH_PATTERN = re.compile(
    r"^[\d\s\+\-\*\/\%\(\)\.\^]+$"
)

# Also catch natural "X + Y = ?" style
_NATURAL_PATTERN = re.compile(
    r"(?:what(?:'s| is)\s+)?(?:[\d\s\+\-\*\/\%\(\)\.\^]+)(?:\s*=\s*\??)?\s*$",
    re.IGNORECASE,
)

# Lazy import — asteval is heavyweight, only load if we actually need it
_aeval = None


def _get_evaluator():
    global _aeval
    if _aeval is None:
        from asteval import Interpreter
        _aeval = Interpreter(err_writer=None, out_writer=None)
    return _aeval


def is_arithmetic(query: str) -> bool:
    """
    Return True if query looks like a math expression.
    Pure regex — no library calls, safe to run on every keystroke.
    """
    q = query.strip()
    if not q:
        return False
    # Any alphabetic character → definitely not arithmetic
    # (catches URLs, app names, phrases, "what is 2+2", etc.)
    if re.search(r"[a-zA-Z]", q):
        return False
    # Must contain at least one digit
    if not re.search(r"\d", q):
        return False
    # Must match the full arithmetic pattern (digits, ops, parens, dots, spaces)
    return bool(_ARITH_PATTERN.match(q))


def evaluate(expression: str) -> Optional[str]:
    """
    Safely evaluate a math expression.

    Returns a formatted string result, or None if evaluation fails.
    Never raises.
    """
    expr = expression.strip()
    if not expr:
        return None

    # Replace ^ with ** for Python exponentiation
    expr = expr.replace("^", "**")

    # Pre-validate syntax with compile() — catches "2 +" style incomplete
    # expressions before asteval even tries, with zero side effects.
    try:
        compile(expr, "<calc>", "eval")
    except SyntaxError:
        return None

    try:
        aeval = _get_evaluator()
        # Clear any leftover errors from previous calls
        if aeval.error:
            aeval.error.clear()

        result = aeval(expr)

        if aeval.error:
            log.debug("asteval error: %s", aeval.error)
            aeval.error.clear()
            return None
        if result is None:
            return None

        # Format nicely: ints without .0, floats with up to 10 sig figs
        if isinstance(result, float):
            if result.is_integer():
                return str(int(result))
            return f"{result:.10g}"
        return str(result)

    except Exception as exc:
        log.debug("Calculator error for %r: %s", expression, exc)
        return None


def calculate(expression: str) -> dict:
    """
    High-level calculator call.

    Returns:
        {"expression": str, "result": str, "error": str|None}
    """
    result = evaluate(expression)
    if result is None:
        return {"expression": expression, "result": "", "error": "Could not evaluate"}
    return {"expression": expression, "result": result, "error": None}
