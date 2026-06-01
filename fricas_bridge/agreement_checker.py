"""
Tier 5.3 — Cross-CAS agreement checker.

Compares FriCAS and SymPy antiderivatives for the same integrand and
classifies the pair as:

  AGREE          — symbolically identical after normalisation
  AGREE_UP_TO_C  — differ by a constant (both valid antiderivatives)
  DISAGREE       — genuinely different (potential CAS bug, or branch choice)
  ONE_MISSING    — one CAS returned no result
  BOTH_MISSING   — neither CAS has an answer

Public API
----------
AgreementClass                  Enum
AgreementResult                 dataclass
check_agreement(integrand, var) → AgreementResult
check_all_bronstein()           → list[AgreementResult]
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from fricas_bridge.offline_cache import FriCASResolver
from fricas_bridge.sympy_resolver import SymPyResolver


class AgreementClass(str, Enum):
    AGREE         = "agree"
    AGREE_UP_TO_C = "agree_up_to_c"
    DISAGREE      = "disagree"
    ONE_MISSING   = "one_missing"
    BOTH_MISSING  = "both_missing"


@dataclass
class AgreementResult:
    integrand: str
    var: str
    fricas_result: Optional[str]
    sympy_result: Optional[str]
    agreement: str       # AgreementClass value


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _norm(expr: str) -> str:
    """Strip whitespace, sort commutative tokens for a quick canonical form."""
    if not expr:
        return ""
    s = expr.replace(" ", "")
    # Normalise ** and ^ to a single form
    s = s.replace("**", "^")
    # Normalise log/ln
    s = re.sub(r"\bln\(", "log(", s)
    # Lower-case
    s = s.lower()
    return s


def _differ_by_constant(a: str, b: str) -> bool:
    """
    Heuristic: two antiderivatives differ by a constant if, after subtracting
    their token multisets (ignoring sign), only constant-looking residues remain.

    This is a lightweight check — it errs on the side of AGREE_UP_TO_C for
    expressions that a full CAS would confirm are equal.
    """
    # Strip overall sign and leading constant term
    def _canonical_tokens(s: str) -> set[str]:
        norm = _norm(s)
        # Split on + and - boundaries (crude but effective for our expressions)
        parts = re.split(r"(?<![e*/^(])[+-]", norm)
        return {p.strip() for p in parts if p.strip() and not re.fullmatch(r"[\d/]+", p.strip())}

    tokens_a = _canonical_tokens(a)
    tokens_b = _canonical_tokens(b)
    # If the non-constant tokens are equal the expressions agree up to C
    return tokens_a == tokens_b


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_agreement(integrand: str, var: str = "x") -> AgreementResult:
    """Compare FriCAS and SymPy antiderivatives for integrand."""
    fricas_result = FriCASResolver(mode="offline").resolve(integrand, var)
    fricas = fricas_result.antiderivative if fricas_result.ok else None
    sympy  = SymPyResolver(mode="offline").integrate(integrand, var)

    if fricas is None and sympy is None:
        cls = AgreementClass.BOTH_MISSING
    elif fricas is None or sympy is None:
        cls = AgreementClass.ONE_MISSING
    elif _norm(fricas) == _norm(sympy):
        cls = AgreementClass.AGREE
    elif _differ_by_constant(fricas, sympy):
        cls = AgreementClass.AGREE_UP_TO_C
    else:
        cls = AgreementClass.DISAGREE

    return AgreementResult(
        integrand=integrand,
        var=var,
        fricas_result=fricas,
        sympy_result=sympy,
        agreement=cls.value,
    )


_BRONSTEIN_INTEGRANDS = [
    ("(2*x*log(x^2+1)+x^3)/(x^2+1)", "x"),   # bronstein_001
    ("x/(x^2+1)", "x"),                        # bronstein_003
    ("2*x/(1+x^4)", "x"),                      # bronstein_004
    ("(x+1)/(x*(x+2))", "x"),                  # bronstein_005
    ("1/(x^2+2*x+2)", "x"),                    # bronstein_006
    ("1/x", "x"),                              # bronstein_007
    ("x/(x^2-4)", "x"),                        # bronstein_008
    ("1/(x*(x+1)*(x+2))", "x"),               # bronstein_009
]


def check_all_bronstein() -> list[AgreementResult]:
    """Run the agreement check for all eight non-trivial Bronstein integrands."""
    return [check_agreement(ig, v) for ig, v in _BRONSTEIN_INTEGRANDS]
