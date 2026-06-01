"""
Tier 6 — CAS Bug Hunt: verification loop.

For each integrand in a corpus:
  1. Get the FriCAS antiderivative F
  2. Differentiate F (via offline cache)
  3. Check if D(F) ≡ integrand  (symbolically or by normalisation)
  4. Report mismatches as potential CAS bugs

When D(F) ≠ integrand this is either:
  - a genuine CAS bug (FriCAS returned a wrong antiderivative)
  - an equivalent form that our normaliser can't match
  - a missing differentiation cache entry (inconclusive)

Public API
----------
BugCandidate                    dataclass
run_bug_hunt(integrands)        → list[BugCandidate]
run_bronstein_bug_hunt()        → list[BugCandidate]
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from fricas_bridge.offline_cache import FriCASResolver
from fricas_bridge.lateral_ops import fricas_differentiate, _MISSING


class VerdictClass(str):
    pass


VERIFIED   = VerdictClass("verified")
MISMATCH   = VerdictClass("mismatch")
INCONCLUSIVE = VerdictClass("inconclusive")
NO_ANTIDERIV = VerdictClass("no_antideriv")


@dataclass
class BugCandidate:
    integrand: str
    var: str
    fricas_antideriv: Optional[str]
    differentiated: Optional[str]
    verdict: str                # "verified" | "mismatch" | "inconclusive" | "no_antideriv"
    note: str = ""


# ---------------------------------------------------------------------------
# Symbolic normalisation for comparison
# ---------------------------------------------------------------------------

def _normalise_expr(expr: str) -> str:
    """Strip whitespace, normalise powers, lower-case for comparison."""
    s = expr.replace(" ", "").replace("**", "^").lower()
    # Remove outermost coefficient 1* or 1/
    s = re.sub(r"(?<![0-9])1\*", "", s)
    return s


def _expressions_match(a: str, b: str) -> bool:
    """Return True if two expressions are symbolically equal under normalisation."""
    na, nb = _normalise_expr(a), _normalise_expr(b)
    return na == nb


# ---------------------------------------------------------------------------
# Core loop
# ---------------------------------------------------------------------------

def _check_one(integrand: str, var: str) -> BugCandidate:
    resolver = FriCASResolver(mode="offline")
    result = resolver.resolve(integrand, var)
    antideriv = result.antiderivative if result.ok else None

    if antideriv is None:
        return BugCandidate(
            integrand=integrand, var=var,
            fricas_antideriv=None, differentiated=None,
            verdict=NO_ANTIDERIV,
            note="FriCAS cache miss for this integrand",
        )

    diff = fricas_differentiate(antideriv, var)

    if diff == _MISSING:
        return BugCandidate(
            integrand=integrand, var=var,
            fricas_antideriv=antideriv, differentiated=None,
            verdict=INCONCLUSIVE,
            note=f"D({antideriv!r}) not in differentiation cache",
        )

    if _expressions_match(diff, integrand):
        return BugCandidate(
            integrand=integrand, var=var,
            fricas_antideriv=antideriv, differentiated=diff,
            verdict=VERIFIED,
        )

    return BugCandidate(
        integrand=integrand, var=var,
        fricas_antideriv=antideriv, differentiated=diff,
        verdict=MISMATCH,
        note=f"D(F) = {diff!r} but integrand = {integrand!r}",
    )


def run_bug_hunt(integrands: list[tuple[str, str]]) -> list[BugCandidate]:
    """
    Run the verification loop over a list of (integrand, var) pairs.
    Returns one BugCandidate per entry.
    """
    return [_check_one(ig, var) for ig, var in integrands]


_BRONSTEIN_CORPUS: list[tuple[str, str]] = [
    ("(2*x*log(x^2+1)+x^3)/(x^2+1)", "x"),
    ("x/(x^2+1)", "x"),
    ("2*x/(1+x^4)", "x"),
    ("(x+1)/(x*(x+2))", "x"),
    ("1/(x^2+2*x+2)", "x"),
    ("1/x", "x"),
    ("x/(x^2-4)", "x"),
    ("1/(x*(x+1)*(x+2))", "x"),
]


def run_bronstein_bug_hunt() -> list[BugCandidate]:
    """Run the verification loop on all eight non-trivial Bronstein integrands."""
    return run_bug_hunt(_BRONSTEIN_CORPUS)
