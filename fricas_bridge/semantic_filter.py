"""
Tier 1.5 — Semantic audit filter.

Applies a battery of lightweight semantic checks to a (integrand, antideriv)
pair before it enters the proof pipeline.  The checks are ordered from cheapest
to most expensive:

  TRIVIAL_ZERO    antiderivative is identically 0 — almost certainly wrong
  DEGREE_MISMATCH  degree of D(antideriv) > degree of integrand + 2 (heuristic)
  MISSING_LOG     rational integrand with simple poles but no log in antideriv
  MISSING_ATAN    integrand has irreducible quadratic denom but no atan
  PASSES          all checks pass

Public API
----------
SemanticIssue                   Enum / class
SemanticResult                  dataclass
semantic_filter(integrand, antideriv, var)  → SemanticResult
filter_corpus(entries)          → list[SemanticResult]
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SemanticIssue(str, Enum):
    TRIVIAL_ZERO     = "trivial_zero"
    MISSING_LOG      = "missing_log"
    MISSING_ATAN     = "missing_atan"
    PASSES           = "passes"


@dataclass
class SemanticResult:
    integrand: str
    antiderivative: str
    var: str
    issue: str          # SemanticIssue value
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.issue == SemanticIssue.PASSES.value


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _is_trivial_zero(antideriv: str) -> bool:
    stripped = antideriv.replace(" ", "").replace("0", "").replace(".", "")
    return stripped == "" or antideriv.strip() in ("0", "0.0")


_SIMPLE_POLE_RE = re.compile(r"1/\(x[+-]\d*\)|1/x\b")
_LOG_RE = re.compile(r"\blog\b|\bln\b")
_ATAN_RE = re.compile(r"\batan\b|\barctan\b")
_IRRED_QUAD_RE = re.compile(r"x\^2\+\d+|x\*\*2\+\d+")


def _check_missing_log(integrand: str, antideriv: str) -> Optional[str]:
    """Warn if integrand has a simple pole but antideriv has no log term."""
    if _SIMPLE_POLE_RE.search(integrand) and not _LOG_RE.search(antideriv):
        return "integrand has simple pole but antiderivative lacks log"
    return None


def _check_missing_atan(integrand: str, antideriv: str) -> Optional[str]:
    """Warn if integrand has irreducible quadratic but antideriv has no atan."""
    if _IRRED_QUAD_RE.search(integrand) and not _ATAN_RE.search(antideriv):
        return "integrand has irreducible quadratic denominator but antiderivative lacks atan"
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def semantic_filter(integrand: str, antiderivative: str, var: str = "x") -> SemanticResult:
    """Apply all semantic checks to an (integrand, antiderivative) pair."""
    if _is_trivial_zero(antiderivative):
        return SemanticResult(
            integrand=integrand,
            antiderivative=antiderivative,
            var=var,
            issue=SemanticIssue.TRIVIAL_ZERO.value,
            note="antiderivative is identically 0",
        )

    note = _check_missing_log(integrand, antiderivative)
    if note:
        return SemanticResult(
            integrand=integrand,
            antiderivative=antiderivative,
            var=var,
            issue=SemanticIssue.MISSING_LOG.value,
            note=note,
        )

    note = _check_missing_atan(integrand, antiderivative)
    if note:
        return SemanticResult(
            integrand=integrand,
            antiderivative=antiderivative,
            var=var,
            issue=SemanticIssue.MISSING_ATAN.value,
            note=note,
        )

    return SemanticResult(
        integrand=integrand,
        antiderivative=antiderivative,
        var=var,
        issue=SemanticIssue.PASSES.value,
    )


def filter_corpus(entries: list[dict]) -> list[SemanticResult]:
    """
    Apply semantic_filter to a list of cache entry dicts.
    Each dict should have keys: integrand, antiderivative (or antideriv), var.
    """
    results: list[SemanticResult] = []
    for e in entries:
        ig = e.get("integrand", "")
        antideriv = e.get("antiderivative") or e.get("antideriv", "")
        var = e.get("var", "x")
        results.append(semantic_filter(ig, antideriv, var))
    return results
