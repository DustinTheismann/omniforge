"""
Tier 7 — AlphaIntegrate discovery loop.

The discovery loop takes a stream of candidate integrands, evaluates each
through the FriCAS resolver, checks agreement with SymPy, and classifies
the result.  Integrands that produce antiderivatives unknown to the offline
cache are tagged as "novel candidates" — potential additions to the corpus.

A *novelty score* is computed for each integrand:
  0 — already in both FriCAS and SymPy offline caches (known)
  1 — in FriCAS only  (single-source, potentially interesting)
  2 — in neither cache (genuinely novel to the offline corpus)
  3 — FriCAS and SymPy disagree (cross-CAS disagreement → Bug Hunt trigger)

The default candidate generator produces a finite set of rational integrands
by composing poles and partial fractions.

Public API
----------
DiscoveryResult                 dataclass
novelty_score(integrand, var)   → int
discover(integrands)            → list[DiscoveryResult]
discover_from_generator()       → list[DiscoveryResult]
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Optional

from fricas_bridge.offline_cache import FriCASResolver
from fricas_bridge.sympy_resolver import SymPyResolver
from fricas_bridge.agreement_checker import check_agreement, AgreementClass


@dataclass
class DiscoveryResult:
    integrand: str
    var: str
    fricas_result: Optional[str]
    sympy_result: Optional[str]
    agreement: str
    novelty_score: int
    is_novel: bool           # novelty_score > 0
    is_disagreement: bool    # fricas and sympy actively disagree


def novelty_score(integrand: str, var: str = "x") -> int:
    """
    Return 0–3 indicating how novel an integrand is:
      0 = both caches have it (known)
      1 = FriCAS only (single-source)
      2 = neither cache has it
      3 = active cross-CAS disagreement
    """
    fricas_r = FriCASResolver(mode="offline").resolve(integrand, var)
    sympy_r  = SymPyResolver(mode="offline").integrate(integrand, var)
    fricas_ok = fricas_r.ok
    sympy_ok  = sympy_r is not None

    if fricas_ok and sympy_ok:
        # Check if they agree
        ag = check_agreement(integrand, var)
        if ag.agreement == AgreementClass.DISAGREE.value:
            return 3
        return 0
    elif fricas_ok and not sympy_ok:
        return 1
    elif not fricas_ok and not sympy_ok:
        return 2
    else:
        # sympy only — also "single-source"
        return 1


def _discover_one(integrand: str, var: str) -> DiscoveryResult:
    ag = check_agreement(integrand, var)
    score = novelty_score(integrand, var)
    return DiscoveryResult(
        integrand=integrand,
        var=var,
        fricas_result=ag.fricas_result,
        sympy_result=ag.sympy_result,
        agreement=ag.agreement,
        novelty_score=score,
        is_novel=score > 0,
        is_disagreement=(ag.agreement == AgreementClass.DISAGREE.value),
    )


def discover(integrands: list[tuple[str, str]]) -> list[DiscoveryResult]:
    """Run the discovery loop over a list of (integrand, var) pairs."""
    return [_discover_one(ig, var) for ig, var in integrands]


# ---------------------------------------------------------------------------
# Default candidate generator
# ---------------------------------------------------------------------------

def _generate_rational_candidates() -> list[tuple[str, str]]:
    """
    Generate a small finite set of rational integrand candidates by:
    - simple rational functions 1/(x+a) for a in {0,1,2,3,4}
    - products of linear factors: 1/((x+a)*(x+b))
    - quadratic denominators: 1/(x^2+c) and x/(x^2+c)

    Returns (integrand, var) pairs.
    """
    candidates: list[tuple[str, str]] = []

    # Single poles
    for a in range(5):
        if a == 0:
            candidates.append(("1/x", "x"))
        else:
            candidates.append((f"1/(x+{a})", "x"))
            candidates.append((f"1/(x-{a})", "x"))

    # Two-pole partial fractions
    poles = [0, 1, 2, 3]
    for a, b in itertools.combinations(poles, 2):
        if a == 0:
            candidates.append((f"1/(x*(x+{b}))", "x"))
        else:
            candidates.append((f"1/((x+{a})*(x+{b}))", "x"))

    # Quadratic denominators
    for c in [1, 2, 4, 5]:
        candidates.append((f"1/(x^2+{c})", "x"))
        candidates.append((f"x/(x^2+{c})", "x"))
        candidates.append((f"x/(x^2-{c})", "x"))

    # Three-pole
    candidates.append(("1/(x*(x+1)*(x+2))", "x"))
    candidates.append(("1/(x*(x+1)*(x+3))", "x"))

    return candidates


def discover_from_generator() -> list[DiscoveryResult]:
    """Run the discovery loop over the built-in rational candidate generator."""
    return discover(_generate_rational_candidates())
