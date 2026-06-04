"""
Expression normalization utilities for cross-CAS comparison.

FriCAS, SymPy, and Maxima use different surface syntax for the same expression.
This module provides a canonical string form used as the comparison key when
checking whether two CAS systems agree on an antiderivative.
"""
from __future__ import annotations

import re


# ---------------------------------------------------------------------------
# Token-level normalizations applied in order
# ---------------------------------------------------------------------------

_RULES: list[tuple[re.Pattern, str]] = [
    # Whitespace collapse
    (re.compile(r'\s+'), ''),
    # FriCAS: log(...) → log(...)   (already canonical)
    # SymPy:  log(...) → log(...)   (same)
    # Maxima: log(...) → log(...)   (same)
    # FriCAS atan → arctan (Lean uses Real.arctan; we normalise to 'arctan')
    (re.compile(r'\batan\b'), 'arctan'),
    # Remove leading + from terms
    (re.compile(r'(?<![eE\d])\+(?=\w|\()'), '+'),
    # Normalise ** (Python/SymPy) → ^ (FriCAS/Lean)
    (re.compile(r'\*\*'), '^'),
    # Normalise 1*x → x, x*1 → x (trivial coefficients)
    (re.compile(r'\b1\*(?=\w)'), ''),
    (re.compile(r'(?<=\w)\*1\b'), ''),
]


def normalize(expr: str) -> str:
    """Return a canonical whitespace-free form of *expr* for equality checks."""
    s = expr
    for pattern, repl in _RULES:
        s = pattern.sub(repl, s)
    return s


def fricas_to_lean(expr: str) -> str:
    """
    Best-effort translation of a FriCAS antiderivative string to Lean 4 syntax.

    This is intentionally shallow — it handles the subset of expressions that
    appear in the Bronstein corpus.  Anything outside that subset must be
    translated manually.
    """
    s = expr.strip()
    # Power operator
    s = s.replace("^", "^")              # already the same; kept for clarity
    # FriCAS atan → Real.arctan
    s = re.sub(r'\batan\b', 'Real.arctan', s)
    # log → Real.log
    s = re.sub(r'\blog\b', 'Real.log', s)
    # Division: a/b literal fractions stay as-is (Lean handles them with /)
    return s


def lean_to_fricas(expr: str) -> str:
    """Reverse translation for round-trip testing."""
    s = expr.strip()
    s = re.sub(r'\bReal\.arctan\b', 'atan', s)
    s = re.sub(r'\bReal\.log\b', 'log', s)
    return s


# ---------------------------------------------------------------------------
# Hypothesis canonicalization
# ---------------------------------------------------------------------------

def canonical_hyp(lean_expr: str) -> str:
    """Return a normalised hypothesis string for deduplication."""
    return normalize(lean_expr).lower()
