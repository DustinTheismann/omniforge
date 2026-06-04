"""
Tier 3 — Lateral FriCAS operations.

Extends the offline-cache model (Tier 0 / Session 6) to four additional CAS
operations beyond integration:

  fricas_differentiate(expr, var)  → string    D(f, x)
  fricas_limit(expr, var, point)   → string    limit(f, x=a)
  fricas_series(expr, var, point)  → string    series(f, x=a, n)
  fricas_factor(expr)              → string    factor(p)

Each function first checks an in-memory offline cache; if missing it either
raises (strict=True) or returns a sentinel string.

The offline caches below contain answers for the nine Risch–Bronstein
integrands and a selection of auxiliary expressions, keeping the test suite
self-contained without a live FriCAS process.

Public API
----------
fricas_differentiate(expr, var)                → str
fricas_limit(expr, var, point, direction)      → str
fricas_series(expr, var, point, n_terms)       → str
fricas_factor(expr)                            → str
CACHE_DIFF / CACHE_LIMIT / CACHE_SERIES / CACHE_FACTOR   (dict, for testing)
"""
from __future__ import annotations

import hashlib
from typing import Optional


# ---------------------------------------------------------------------------
# Cache key helpers (byte-identical to FriCASResolver in offline_cache.py)
# ---------------------------------------------------------------------------

def _key(*parts: str) -> str:
    payload = "||".join(parts).encode()
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# Offline caches
# ---------------------------------------------------------------------------

# fricas_differentiate: D(expr, var)
CACHE_DIFF: dict[str, str] = {
    _key("x^2/2", "x"):                              "x",
    _key("x^3/3", "x"):                              "x^2",
    _key("log(x)", "x"):                             "1/x",
    _key("atan(x)", "x"):                            "1/(1+x^2)",
    _key("log(x^2+1)/2", "x"):                       "x/(x^2+1)",
    _key("Real.arctan(x^2)", "x"):                   "2*x/(1+x^4)",
    _key("Real.arctan(x+1)", "x"):                   "1/(x^2+2*x+2)",
    _key("log(x)/2+log(x+2)/2", "x"):                "(x+1)/(x*(x+2))",
    _key("log(x)/2-log(x+1)+log(x+2)/2", "x"):      "1/(x*(x+1)*(x+2))",
    _key("log(x^2-4)/2", "x"):                       "x/(x^2-4)",
    _key("log(x^2+1)^2/2+x^2/2-log(x^2+1)/2", "x"): "(2*x*log(x^2+1)+x^3)/(x^2+1)",
    # atan variants (FriCAS antiderivatives use atan not Real.arctan)
    _key("atan(x)", "x"):                            "1/(1+x^2)",
    _key("atan(x+1)", "x"):                          "1/(x^2+2*x+2)",
    _key("atan(x^2)", "x"):                          "2*x/(1+x^4)",
    # general identities
    _key("exp(x)", "x"):                             "exp(x)",
    _key("sin(x)", "x"):                             "cos(x)",
    _key("cos(x)", "x"):                             "-sin(x)",
}

# fricas_limit: limit(expr, var, point, direction)
CACHE_LIMIT: dict[str, str] = {
    _key("1/x", "x", "0", "+"):        "+infinity",
    _key("1/x", "x", "0", "-"):        "-infinity",
    _key("1/x", "x", "infinity", ""): "0",
    _key("sin(x)/x", "x", "0", ""):   "1",
    _key("log(x)", "x", "0", "+"):     "-infinity",
    _key("log(x)", "x", "1", ""):      "0",
    _key("atan(x)", "x", "infinity", ""): "pi/2",
    _key("atan(x)", "x", "-infinity", ""): "-pi/2",
    _key("x^2+1", "x", "0", ""):      "1",
    _key("(1+1/x)^x", "x", "infinity", ""): "e",
}

# fricas_series: series(expr, var, point, n_terms)
CACHE_SERIES: dict[str, str] = {
    _key("exp(x)", "x", "0", "5"):    "1 + x + x^2/2 + x^3/6 + x^4/24 + O(x^5)",
    _key("sin(x)", "x", "0", "5"):    "x - x^3/6 + O(x^5)",
    _key("cos(x)", "x", "0", "5"):    "1 - x^2/2 + x^4/24 + O(x^5)",
    _key("log(1+x)", "x", "0", "5"):  "x - x^2/2 + x^3/3 - x^4/4 + O(x^5)",
    _key("atan(x)", "x", "0", "5"):   "x - x^3/3 + O(x^5)",
    _key("1/(1-x)", "x", "0", "5"):   "1 + x + x^2 + x^3 + x^4 + O(x^5)",
    _key("1/x", "x", "1", "4"):       "1 - (x-1) + (x-1)^2 - (x-1)^3 + O((x-1)^4)",
}

# fricas_factor: factor(expr)
CACHE_FACTOR: dict[str, str] = {
    _key("x^2-1"):                 "(x-1)*(x+1)",
    _key("x^2-4"):                 "(x-2)*(x+2)",
    _key("x^2+2*x+1"):             "(x+1)^2",
    _key("x^3-1"):                 "(x-1)*(x^2+x+1)",
    _key("x*(x+1)*(x+2)"):         "x*(x+1)*(x+2)",
    _key("x^2+1"):                 "x^2+1",
    _key("x^4-1"):                 "(x-1)*(x+1)*(x^2+1)",
    _key("6*x^2-x-1"):             "(2*x-1)*(3*x+1)",
}

_MISSING = "**fricas_offline_cache_miss**"


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def fricas_differentiate(
    expr: str,
    var: str = "x",
    *,
    strict: bool = False,
) -> str:
    """
    Return D(expr, var) using the offline cache.

    Tries the expression as-is, then with spaces stripped, for robustness
    against formatting differences between the cache keys and FriCAS output.
    Raises KeyError when strict=True and the key is not in the cache.
    """
    result = CACHE_DIFF.get(_key(expr, var))
    if result is None:
        # Retry with whitespace stripped (FriCAS output may have spaces)
        stripped = expr.replace(" ", "")
        result = CACHE_DIFF.get(_key(stripped, var))
    if result is None:
        if strict:
            raise KeyError(f"fricas_differentiate: no cache entry for {expr!r} wrt {var!r}")
        return _MISSING
    return result


def fricas_limit(
    expr: str,
    var: str,
    point: str,
    direction: str = "",
    *,
    strict: bool = False,
) -> str:
    """
    Return limit(expr, var=point, direction) using the offline cache.

    direction: "" (two-sided), "+" (from right), "-" (from left).
    """
    result = CACHE_LIMIT.get(_key(expr, var, point, direction))
    if result is None:
        if strict:
            raise KeyError(
                f"fricas_limit: no cache entry for limit({expr}, {var}={point}, dir={direction!r})"
            )
        return _MISSING
    return result


def fricas_series(
    expr: str,
    var: str,
    point: str = "0",
    n_terms: int = 5,
    *,
    strict: bool = False,
) -> str:
    """
    Return the Taylor/Laurent series of expr around var=point to n_terms terms.
    """
    result = CACHE_SERIES.get(_key(expr, var, point, str(n_terms)))
    if result is None:
        if strict:
            raise KeyError(
                f"fricas_series: no cache entry for series({expr}, {var}={point}, n={n_terms})"
            )
        return _MISSING
    return result


def fricas_factor(
    expr: str,
    *,
    strict: bool = False,
) -> str:
    """Return the factored form of a polynomial expression."""
    result = CACHE_FACTOR.get(_key(expr))
    if result is None:
        if strict:
            raise KeyError(f"fricas_factor: no cache entry for {expr!r}")
        return _MISSING
    return result
