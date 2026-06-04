"""
Tier 2.2 — Removable-singularity detector.

A FriCAS antiderivative may contain expressions like ``log(x^2)/2 - log(x)``
which simplify (over ℝ, x>0) to ``log(x^2)/2 - log(x) = log|x| - log|x| = 0``
— apparently harmless, but across a sign change the two log terms are NOT
individually differentiable at x=0.  The combined expression has a removable
singularity at the pole that the pointwise ≠0 hypothesis does not capture.

This module finds such pairs in a FriCAS antiderivative and classifies each
as a RemovableSingularity record, with the relevant poles and a cancellation
note.

Public API
----------
RemovableSingularity            dataclass
detect_removable(fricas_expr)   → list[RemovableSingularity]
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class RemovableSingularity:
    expr1: str             # first log term, e.g. "log(x^2)/2"
    expr2: str             # second log term, e.g. "log(x)"
    pole: str              # the common pole, e.g. "x=0"
    cancellation: str      # human note on the algebraic identity
    lean_issue: str        # what this means for the Lean proof


# ---------------------------------------------------------------------------
# Simple symbolic helpers
# ---------------------------------------------------------------------------

_LOG_TERM = re.compile(
    r"([+-]?\s*(?:\d+/)?)?\s*log\(([^()]*(?:\([^()]*\)[^()]*)*)\)(?:/(\d+))?",
)


@dataclass
class _LogTerm:
    sign: str        # "+" or "-"
    arg: str         # content of log(...)
    den: int         # denominator of the coefficient (1 if none)
    raw: str         # original match text


def _parse_log_terms(expr: str) -> list[_LogTerm]:
    """Extract all log(...) terms from an expression with their signs."""
    terms: list[_LogTerm] = []
    # Normalise leading sign
    s = expr.replace(" ", "")
    for m in re.finditer(r"([+-]?)log\(([^()]*(?:\([^()]*\)[^()]*)*)\)(?:/(\d+))?", s):
        sign = m.group(1) or "+"
        arg = m.group(2)
        den = int(m.group(3)) if m.group(3) else 1
        terms.append(_LogTerm(sign=sign, arg=arg, den=den, raw=m.group(0)))
    return terms


def _coefficient(term: _LogTerm) -> float:
    """Signed rational coefficient: +1/2, -1, etc."""
    val = 1.0 / term.den
    return val if term.sign == "+" else -val


def _pole_of(arg: str) -> Optional[str]:
    """Infer the pole from a log argument."""
    a = arg.strip()
    if a == "x":
        return "x=0"
    m = re.fullmatch(r"x([+-]\d+)", a)
    if m:
        off = m.group(1)
        rhs = off[1:] if off[0] == "+" else off
        return f"x={('-' + off[1:]) if off[0] == '+' else off[1:]}"
    if re.fullmatch(r"x\^2", a):
        return "x=0"
    m2 = re.fullmatch(r"x\^2([+-]\d+)", a)
    if m2:
        c = m2.group(1)
        return f"x²={c[1:]}" if c[0] == "+" else f"x²=-{c[1:]}"
    return None


# ---------------------------------------------------------------------------
# Pair-cancellation check
# ---------------------------------------------------------------------------

def _cancels(t1: _LogTerm, t2: _LogTerm) -> Optional[RemovableSingularity]:
    """
    Return a RemovableSingularity if t1 and t2 algebraically cancel at a pole.

    The classic case: log(x^2)/2 + (-1)*log(x) = log|x| - log|x| = 0
    when x > 0, but separately each term has a singularity at x=0.
    """
    c1 = _coefficient(t1)
    c2 = _coefficient(t2)
    a1 = t1.arg.replace(" ", "")
    a2 = t2.arg.replace(" ", "")

    # Case 1: log(x^2)/2 - log(x)  →  cancels at x=0
    # c1*log(x^2) + c2*log(x): using log(x^2) = 2*log|x|,
    # c1*2 + c2 = 0  ⇒  cancellation
    if a1 == "x^2" and a2 == "x" and abs(2 * c1 + c2) < 1e-9:
        return RemovableSingularity(
            expr1=t1.raw,
            expr2=t2.raw,
            pole="x=0",
            cancellation=f"{t1.raw} + {t2.raw} = 0 for x>0 via log(x²)=2·log|x|",
            lean_issue=(
                "Real.log is total (log|·|) so the combined expression is "
                "differentiable at x≠0, but the individual terms diverge; "
                "the HasDerivAt proof must treat them together, not separately."
            ),
        )

    # Case 2: log(x)/2 - log(sqrt(x))  — less common but detect it
    if a2 == "sqrt(x)" and a1 == "x" and abs(c1 / 2 + c2) < 1e-9:
        return RemovableSingularity(
            expr1=t1.raw,
            expr2=t2.raw,
            pole="x=0",
            cancellation=f"{t1.raw} + {t2.raw} = 0 for x>0 via log(x)/2=log(sqrt|x|)",
            lean_issue="Individual log terms not differentiable at x=0; treat combined.",
        )

    # Case 3: log(x+a)/k - log(x+b)/k with a=b (trivial tautology)
    if a1 == a2 and abs(c1 + c2) < 1e-9:
        pole = _pole_of(a1) or f"arg({a1})=0"
        return RemovableSingularity(
            expr1=t1.raw,
            expr2=t2.raw,
            pole=pole,
            cancellation=f"{t1.raw} + {t2.raw} = 0 (tautological cancellation)",
            lean_issue="Redundant terms; simplify before emitting HasDerivAt proof.",
        )

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_removable(fricas_expr: str) -> list[RemovableSingularity]:
    """
    Scan a FriCAS antiderivative for removable-singularity log-pair cancellations.

    Returns one RemovableSingularity per detected cancelling pair.
    """
    terms = _parse_log_terms(fricas_expr)
    found: list[RemovableSingularity] = []
    checked: set[tuple[int, int]] = set()

    for i, t1 in enumerate(terms):
        for j, t2 in enumerate(terms):
            if i >= j or (i, j) in checked:
                continue
            checked.add((i, j))
            rs = _cancels(t1, t2)
            if rs is not None:
                found.append(rs)

    return found
