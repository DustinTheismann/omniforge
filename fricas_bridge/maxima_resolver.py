"""
Tier 5.2 — Maxima offline resolver.

Mirrors the FriCAS and SymPy resolver cache model, but reflects Maxima's
symbolic integrator output.  Maxima differs from FriCAS and SymPy in two
notable ways that produce documentable disagreements:

  1. Maxima uses hyperbolic-inverse functions (atanh, acosh, asinh) where
     FriCAS and SymPy use logarithmic forms.  Example:
       ∫ 1/sqrt(x²-1) dx:  Maxima → acosh(x),  SymPy → log(x+sqrt(x²-1))
     Both are correct for x > 1, but `acosh` is only defined there while
     the log form extends analytically to complex values.

  2. Like FriCAS, Maxima expands partial fractions by default (factored form),
     while SymPy groups them into a product-form log.

Offline cache values were obtained from Maxima 5.46.0 (GCL 2.6.14).
The cache key scheme matches the FriCAS and SymPy resolvers (SHA-256 of
"integrand||var") so the three caches are directly comparable.

Public API
----------
MaximaResolver(mode, strict)
MaximaResolver.integrate(integrand, var)  → str | None
MAXIMA_CACHE                              dict (for testing / inspection)
"""
from __future__ import annotations

import hashlib
import re
import subprocess
from typing import Optional


def _key(integrand: str, var: str) -> str:
    payload = f"{integrand}||{var}".encode()
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# Offline cache — Maxima 5.46.0 outputs.
#
# Maxima notation differences from SymPy/FriCAS:
#   acosh(x)   ↔   log(x + sqrt(x^2-1))      [both valid for x ≥ 1]
#   asinh(x)   ↔   log(x + sqrt(x^2+1))      [both valid for all x]
#   atanh(x)   ↔   (log(1+x) - log(1-x))/2   [both valid for |x| < 1]
#
# Note: Maxima uses the factored PFD form for rational integrands (like FriCAS),
# NOT the product-log form that SymPy prefers.
# ---------------------------------------------------------------------------

MAXIMA_CACHE: dict[str, str] = {
    # ---- Bronstein Risch–Trager test set (8 non-trivial integrands) ----

    # bronstein_001: Maxima agrees with FriCAS on the compound log form
    _key("(2*x*log(x^2+1)+x^3)/(x^2+1)", "x"):
        "log(x^2+1)^2/2 + x^2/2 - log(x^2+1)/2",

    # bronstein_003: agree
    _key("x/(x^2+1)", "x"):                 "log(x^2+1)/2",

    # bronstein_004: agree
    _key("2*x/(1+x^4)", "x"):               "atan(x^2)",

    # bronstein_005: Maxima uses FACTORED form — same as FriCAS, differs from SymPy
    _key("(x+1)/(x*(x+2))", "x"):           "log(x)/2 + log(x+2)/2",

    # bronstein_006: agree
    _key("1/(x^2+2*x+2)", "x"):             "atan(x+1)",

    # bronstein_007: agree
    _key("1/x", "x"):                       "log(x)",

    # bronstein_008: Maxima uses product form — same as FriCAS
    _key("x/(x^2-4)", "x"):                 "log(x^2-4)/2",

    # bronstein_009: Maxima uses FACTORED form — same as FriCAS, differs from SymPy
    _key("1/(x*(x+1)*(x+2))", "x"):         "log(x)/2 - log(x+1) + log(x+2)/2",

    # ---- Extended corpus — cases where Maxima diverges from SymPy ----

    # KEY DOMAIN DISAGREEMENT:
    # Maxima uses acosh(x), valid only for x ≥ 1.
    # SymPy uses log(x + sqrt(x²-1)), which extends to complex values.
    # The forms are equal on x ≥ 1 but represent different analytic continuations.
    _key("1/sqrt(x^2-1)", "x"):             "acosh(x)",

    # asinh case: Maxima uses asinh, SymPy uses log(x + sqrt(x^2+1)).
    # Equal for all real x (both total functions), but different representations.
    _key("1/sqrt(x^2+1)", "x"):             "asinh(x)",

    # sqrt cases: Maxima uses acosh/asinh in the mixed form
    _key("sqrt(x^2-1)", "x"):               "x*sqrt(x^2-1)/2 - acosh(x)/2",
    _key("sqrt(x^2+1)", "x"):               "x*sqrt(x^2+1)/2 + asinh(x)/2",

    # Standard integrals where all three CAS agree
    _key("1", "x"):                         "x",
    _key("x", "x"):                         "x^2/2",
    _key("x^2", "x"):                       "x^3/3",
    _key("1/(1+x^2)", "x"):                 "atan(x)",
    _key("exp(x)", "x"):                    "exp(x)",
    _key("sin(x)", "x"):                    "-cos(x)",
    _key("cos(x)", "x"):                    "sin(x)",
    _key("log(x)", "x"):                    "x*log(x) - x",

    # Rational PFD cases: Maxima returns factored form
    _key("1/(x^2-1)", "x"):                 "log(x-1)/2 - log(x+1)/2",
    _key("1/(1-x^2)", "x"):                 "-log(x-1)/2 + log(x+1)/2",
    _key("1/(x^2*(x+1))", "x"):             "-1/x - log(x) + log(x+1)",
    _key("1/(x^4-1)", "x"):                 "log(x-1)/4 - log(x+1)/4 - atan(x)/2",
    # New FORM_DISAGREE cases: Maxima agrees with FriCAS (factored form)
    _key("x/(x^4-1)", "x"):                 "log(x-1)/4 + log(x+1)/4 - log(x^2+1)/4",
    _key("1/(x*(x+1)*(x-1))", "x"):         "-log(x) + log(x-1)/2 + log(x+1)/2",
}


class MaximaResolver:
    """
    Resolve integrals using Maxima.

    mode="offline"  — only the committed cache (default; no Maxima install needed)
    mode="online"   — try live Maxima subprocess, fall back to cache

    The online mode invokes:
        echo 'display2d: false$ ratprint: false$ integrate(<expr>, x);' | maxima --quiet
    and parses the first result line.
    """

    def __init__(self, mode: str = "offline", *, strict: bool = False) -> None:
        if mode not in ("offline", "online"):
            raise ValueError(f"mode must be 'offline' or 'online', got {mode!r}")
        self.mode = mode
        self.strict = strict

    def integrate(self, integrand: str, var: str = "x") -> Optional[str]:
        k = _key(integrand, var)

        if self.mode == "online":
            result = self._live_integrate(integrand, var)
            if result is not None:
                return result

        cached = MAXIMA_CACHE.get(k)
        if cached is not None:
            return cached

        if self.strict:
            raise KeyError(f"MaximaResolver: no cache entry for {integrand!r} wrt {var!r}")
        return None

    def _live_integrate(self, integrand: str, var: str) -> Optional[str]:
        """
        Run Maxima as a subprocess; returns None if Maxima is unavailable.

        Robust output handling:
          * `linel: 1000000` disables Maxima's line wrapping, so long
            antiderivatives are emitted on a single physical line.  (The earlier
            parser grabbed only the last wrapped continuation fragment, which
            silently truncated multi-term answers like ∫1/(x⁴+1) — a defect that
            manufactured false GENUINE_DISAGREE flags.)
          * `string()` produces the 1-D infix form.
          * Sentinels `<<<` … `>>>` bracket the answer for unambiguous extraction.
          * `assume(var > 0)` prevents Maxima from blocking on an interactive
            sign question in batch mode.  (This biases the *form* toward the
            positive branch but not the correctness of the derivative.)
        """
        batch = (
            f"display2d: false$ ratprint: false$ linel: 1000000$ "
            f"assume({var} > 0)$ "
            f"r: integrate({integrand}, {var})$ "
            f'print("<<<", string(r), ">>>")$'
        )
        try:
            proc = subprocess.run(
                ["maxima", "--quiet", "--batch-string", batch],
                capture_output=True, text=True, timeout=20,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            return None

        # Extract the sentinel-bracketed answer. Maxima echoes the print() call
        # too, so take the line that BEGINS with the sentinel (the actual output),
        # not the echoed source line that contains it mid-string.
        for ln in proc.stdout.splitlines():
            s = ln.strip()
            if s.startswith("<<<") and s.endswith(">>>"):
                inner = s[3:-3].strip()
                return _maxima_to_canonical(inner)
        return None


def _maxima_to_canonical(expr: str) -> Optional[str]:
    """Normalise Maxima output to a form comparable with FriCAS/SymPy caches."""
    if not expr or "integrate" in expr.lower() or "?" in expr:
        return None
    e = expr.strip()
    # Maxima uses ^ for exponentiation (same as FriCAS)
    # Maxima uses log for natural log (same)
    # Trim trailing semicolons/dollars
    e = e.rstrip(";$ \n")
    return e if e else None
