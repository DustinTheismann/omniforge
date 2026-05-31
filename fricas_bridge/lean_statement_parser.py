"""
Python-side mirror of FriCASTranslator.lean.

Parses Lean 4 theorem statement *strings* from RischVerification.lean and
converts the embedded integrand expression to FriCAS format.

This module is the testable Python analogue of `lean_to_fricas : Expr → MetaM String`.
It operates on text rather than Lean 4 `Expr` objects, so it can run in CI
without a Lean 4 installation.

Public API
----------
extract_integrand(stmt)   → Lean 4 integrand string (or None)
lean_expr_to_fricas(expr) → FriCAS-compatible string
to_fricas(stmt)           → combined convenience wrapper
"""
from __future__ import annotations

import re
from typing import Optional


# ---------------------------------------------------------------------------
# Bracket-aware string utilities
# ---------------------------------------------------------------------------

def _find_close(s: str, start: int) -> int:
    """Return index of ')' matching the '(' at s[start]. Returns -1 on failure."""
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "(":
            depth += 1
        elif s[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _next_token(s: str, pos: int) -> tuple[str, int]:
    """
    Read the next whitespace-delimited 'token' from s starting at pos.
    A token is either:
      - a parenthesised group (possibly nested): returns the interior string
      - a word (no spaces, no parens)
    Returns (token_text, end_pos) where end_pos is the index after the token.
    """
    while pos < len(s) and s[pos].isspace():
        pos += 1
    if pos >= len(s):
        return ("", pos)
    if s[pos] == "(":
        close = _find_close(s, pos)
        if close == -1:
            return ("", len(s))
        return (s[pos + 1 : close], close + 1)
    # Plain word
    start = pos
    while pos < len(s) and not s[pos].isspace() and s[pos] != "(":
        pos += 1
    return (s[start:pos], pos)


# ---------------------------------------------------------------------------
# Statement-level extraction
# ---------------------------------------------------------------------------

def extract_integrand(stmt: str) -> Optional[str]:
    """
    Extract the integrand expression from a Lean 4 theorem statement string.

    Handled forms:
      HasDerivAt <antideriv> <integrand> x          → returns integrand text
      deriv (fun t => ...) x = <integrand>          → returns RHS text

    Returns None for unrecognised forms.
    Notes:
      - `risch_verified_bronstein_1` uses `HasDerivAt antiderivative (integrand x) x`
        where `integrand` is an external definition.  The function returns
        ``"integrand x"`` so the caller can detect it as a reference form.
    """
    # Equational form:  ... x = <integrand>
    if " deriv " in stmt or stmt.lstrip().startswith("deriv "):
        eq_pos = stmt.rfind(" = ")
        if eq_pos != -1:
            rhs = stmt[eq_pos + 3 :].strip()
            # Strip a single outer paren pair if present
            if rhs.startswith("(") and _find_close(rhs, 0) == len(rhs) - 1:
                rhs = rhs[1:-1].strip()
            return rhs

    # HasDerivAt form
    hd_pos = stmt.find("HasDerivAt ")
    if hd_pos == -1:
        return None

    pos = hd_pos + len("HasDerivAt ")

    # Skip the antiderivative argument (first arg)
    _, pos = _next_token(stmt, pos)

    # Extract integrand argument (second arg)
    integrand, _ = _next_token(stmt, pos)
    return integrand if integrand else None


def extract_antideriv(stmt: str) -> Optional[str]:
    """
    Extract the antiderivative lambda body from a HasDerivAt theorem statement.

    For `HasDerivAt (fun t : ℝ => <body>) <integrand> x`, returns `<body>`.
    For the equational `deriv (fun t => <body>) x = ...`, returns `<body>`.
    Returns None for reference forms (e.g. `HasDerivAt antiderivative ...`).
    """
    # HasDerivAt (fun t : ℝ => <body>) ...
    hd_pos = stmt.find("HasDerivAt ")
    if hd_pos != -1:
        pos = hd_pos + len("HasDerivAt ")
        first_tok, _ = _next_token(stmt, pos)
        # Reference form: first token is a plain identifier, not a lambda
        if not first_tok.startswith("fun "):
            return None
        # first_tok is the content of the paren: "fun t : ℝ => <body>"
        arrow = first_tok.find("=>")
        if arrow == -1:
            return None
        return first_tok[arrow + 2:].strip()

    # Equational: deriv (fun t => <body>) x = ...
    if " deriv " in stmt or stmt.lstrip().startswith("deriv "):
        start = stmt.find("(fun ")
        if start == -1:
            return None
        paren_content, _ = _next_token(stmt, start)
        arrow = paren_content.find("=>")
        if arrow == -1:
            return None
        return paren_content[arrow + 2:].strip()

    return None


# ---------------------------------------------------------------------------
# Expression-level conversion
# ---------------------------------------------------------------------------

# Regex: Real.<fn> followed by a parenthesised argument.
# Uses a non-greedy group that handles one level of nesting — sufficient
# for the 9 Risch integrands.
_REAL_FN_PAREN = re.compile(
    r"Real\.(log|exp|arctan|sin|cos|sqrt)\s+\(([^()]+)\)"
)
_REAL_FN_WORD = re.compile(
    r"Real\.(log|exp|arctan|sin|cos|sqrt)\s+(\w+)"
)

# Map Lean 4 names to FriCAS names
_FN_MAP = {
    "log": "log",
    "exp": "exp",
    "arctan": "atan",
    "sin": "sin",
    "cos": "cos",
    "sqrt": "sqrt",
}


def lean_expr_to_fricas(expr: str) -> str:
    """
    Convert a Lean 4 expression string to FriCAS format.

    Transformations applied (in order):
      1. `Real.<fn> (<arg>)` → `<fricas_fn>(<arg>)`    [paren form]
      2. `Real.<fn> <word>`  → `<fricas_fn>(<word>)`   [bare-word form]
      3. Remove spaces around `^`, `/`, `*`, `+`, `-`

    Limitations:
      - Only one level of nesting is handled for special-function arguments.
      - Unary minus: ``\\s*-\\s*`` removes surrounding spaces; callers should
        ensure the expression does not start with `- `.
    """
    s = expr.strip()

    # Step 1 & 2: special functions
    def _replace_fn(m: re.Match) -> str:
        lean_fn = m.group(1)
        arg = m.group(2)
        fricas_fn = _FN_MAP.get(lean_fn, lean_fn)
        return f"{fricas_fn}({arg})"

    # Apply paren form first (more specific)
    s = _REAL_FN_PAREN.sub(_replace_fn, s)
    # Then bare-word form for any remaining Real.<fn> <word> patterns
    s = _REAL_FN_WORD.sub(_replace_fn, s)

    # Step 3: remove spaces around binary operators
    # Order matters: ^ before / before * before + before -
    s = re.sub(r"\s*\^\s*", "^", s)
    s = re.sub(r"\s*/\s*", "/", s)
    s = re.sub(r"\s*\*\s*", "*", s)
    s = re.sub(r"\s*\+\s*", "+", s)
    s = re.sub(r"\s+-\s+", "-", s)  # binary minus only (flanked by spaces)

    return s


def to_fricas(stmt: str) -> Optional[str]:
    """Extract integrand from statement and convert to FriCAS format."""
    raw = extract_integrand(stmt)
    if raw is None:
        return None
    return lean_expr_to_fricas(raw)
