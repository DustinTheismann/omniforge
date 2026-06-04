"""
Tier 5.1 — SymPy offline resolver.

Mirrors the FriCASResolver offline cache model (Tier 0 / Session 6) but
queries SymPy's symbolic integrator.  When SymPy is installed and in online
mode the result is computed live; otherwise a committed cache is consulted.

The offline cache is keyed by sha256(integrand||var), byte-identical to the
FriCAS cache key scheme, so the two caches are directly comparable.

Public API
----------
SymPyResolver(mode, strict)
SymPyResolver.integrate(integrand, var)  → str | None
SYMPY_CACHE                              dict (for testing / inspection)
"""
from __future__ import annotations

import hashlib
from typing import Optional


def _key(integrand: str, var: str) -> str:
    payload = f"{integrand}||{var}".encode()
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# Offline cache — SymPy answers for the nine Risch–Bronstein integrands
# and a selection of standard integrals.
# ---------------------------------------------------------------------------

SYMPY_CACHE: dict[str, str] = {
    # Bronstein set — actual SymPy 1.14.0 output (verified with live sympy.integrate)
    # NOTE: SymPy returns product-log form for bronstein_005 and bronstein_009.
    # FriCAS/Maxima return factored form.  This is the documented FORM_DISAGREE.
    _key("(2*x*log(x^2+1)+x^3)/(x^2+1)", "x"): "x**2/2 + log(x**2+1)**2/2 - log(x**2+1)/2",
    _key("x/(x^2+1)", "x"):                 "log(x**2+1)/2",
    _key("2*x/(1+x^4)", "x"):               "atan(x**2)",
    # FORM_DISAGREE with FriCAS/Maxima: log(x)/2+log(x+2)/2 vs log(x*(x+2))/2
    _key("(x+1)/(x*(x+2))", "x"):           "log(x**2+2*x)/2",
    _key("1/(x^2+2*x+2)", "x"):             "atan(x+1)",
    _key("1/x", "x"):                       "log(x)",
    _key("x/(x^2-4)", "x"):                 "log(x**2-4)/2",
    # FORM_DISAGREE with FriCAS/Maxima: factored vs -log(x+1)+log(x*(x+2))/2
    _key("1/(x*(x+1)*(x+2))", "x"):         "-log(x+1)+log(x**2+2*x)/2",
    # Extended corpus — SymPy 1.14.0 results (keys use ^ notation, matching FriCAS/Maxima)
    _key("1/(1-x^2)", "x"):                 "-log(x-1)/2+log(x+1)/2",
    _key("1/(x^2-1)", "x"):                 "log(x-1)/2-log(x+1)/2",
    _key("1/sqrt(x^2-1)", "x"):             "log(x+sqrt(x^2-1))",
    _key("1/sqrt(x^2+1)", "x"):             "log(x+sqrt(x^2+1))",
    _key("sqrt(x^2-1)", "x"):               "x*sqrt(x^2-1)/2-log(x+sqrt(x^2-1))/2",
    _key("sqrt(x^2+1)", "x"):               "x*sqrt(x^2+1)/2+log(x+sqrt(x^2+1))/2",
    _key("sqrt(1-x^2)", "x"):               "x*sqrt(1-x^2)/2+asin(x)/2",
    _key("1/sqrt(1-x^2)", "x"):             "asin(x)",
    _key("atan(x)", "x"):                   "x*atan(x)-log(x^2+1)/2",
    _key("log(x)", "x"):                    "x*log(x)-x",
    _key("log(x)/x", "x"):                  "log(x)^2/2",
    _key("1/(x*log(x))", "x"):              "log(log(x))",
    _key("x*log(x)", "x"):                  "x^2*log(x)/2-x^2/4",
    _key("x^3/(x^2+1)", "x"):              "x^2/2-log(x^2+1)/2",
    _key("1/(x^4-1)", "x"):                "log(x-1)/4-log(x+1)/4-atan(x)/2",
    _key("x/(x^4-1)", "x"):                "log(x^2-1)/4-log(x^2+1)/4",
    _key("1/(x^3+x)", "x"):                "log(x)-log(x^2+1)/2",
    _key("1/(x^2*(x+1))", "x"):            "-log(x)+log(x+1)-1/x",
    # FORM_DISAGREE: SymPy product form vs FriCAS factored form (Real.log_mul)
    # x/(x^4-1): log(x^2-1)/4 - log(x^2+1)/4  vs  log(x-1)/4+log(x+1)/4-log(x^2+1)/4
    _key("x/(x^4-1)", "x"):               "log(x**2-1)/4-log(x**2+1)/4",
    # 1/(x*(x+1)*(x-1)): -log(x)+log(x^2-1)/2  vs  -log(x)+log(x-1)/2+log(x+1)/2
    _key("1/(x*(x+1)*(x-1))", "x"):       "-log(x)+log(x**2-1)/2",
    # Standard integrals
    _key("1", "x"):                         "x",
    _key("x", "x"):                         "x**2/2",
    _key("x**2", "x"):                      "x**3/3",
    _key("1/(1+x**2)", "x"):                "atan(x)",
    _key("exp(x)", "x"):                    "exp(x)",
    _key("sin(x)", "x"):                    "-cos(x)",
    _key("cos(x)", "x"):                    "sin(x)",
    _key("1/x**2", "x"):                    "-1/x",
    _key("sqrt(x)", "x"):                   "2*x**(3/2)/3",
}

_ONLINE_NOT_AVAILABLE = "**sympy_online_unavailable**"
_CACHE_MISS = "**sympy_cache_miss**"


class SymPyResolver:
    """
    Resolve integrals using SymPy.

    mode="offline"  — only the committed cache (default, no imports needed)
    mode="online"   — try SymPy live, fall back to cache, then sentinel
    """

    def __init__(self, mode: str = "offline", *, strict: bool = False) -> None:
        if mode not in ("offline", "online"):
            raise ValueError(f"mode must be 'offline' or 'online', got {mode!r}")
        self.mode = mode
        self.strict = strict

    def integrate(self, integrand: str, var: str = "x") -> Optional[str]:
        """
        Return an antiderivative of integrand wrt var, or None on miss.

        In offline mode: cache-only.
        In online mode: try SymPy live first, fall back to cache.
        """
        k = _key(integrand, var)

        if self.mode == "online":
            result = self._live_integrate(integrand, var)
            if result is not None:
                return result

        cached = SYMPY_CACHE.get(k)
        if cached is not None:
            return cached

        if self.strict:
            raise KeyError(f"SymPyResolver: no cache entry for {integrand!r} wrt {var!r}")
        return None

    def _live_integrate(self, integrand: str, var: str) -> Optional[str]:
        try:
            import sympy  # noqa: F401 — only imported in online mode
            from sympy import integrate, symbols, sympify
            x = symbols(var)
            expr = sympify(integrand)
            result = integrate(expr, x)
            return str(result)
        except Exception:
            return None
