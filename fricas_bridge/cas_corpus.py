"""
Tier 5.5 — CAS Corpus: curated integrand library.

Provides a structured corpus of integrands organised by category for
three-CAS comparison testing.  The corpus is the raw input to the
disagree_detector; it does not store antiderivatives.

Categories
----------
BRONSTEIN      8 non-trivial Risch–Bronstein–Trager claims (the project baseline)
RATIONAL_PFD   Rational functions with real poles (PFD form varies by CAS)
RADICAL        Integrands with square roots (acosh/asinh vs log form)
TRIG_INV       Integrands whose antiderivatives are arctan/arcsin/arccosh
LOGPOLY        Integrals involving log*poly
NON_ELEMENTARY Integrands with no elementary antiderivative (all three should fail)

Public API
----------
CorpusEntry                     dataclass
load_corpus()                   → list[CorpusEntry]
load_bronstein_set()            → list[CorpusEntry]
load_disagreement_candidates()  → list[CorpusEntry]
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CorpusEntry:
    integrand: str
    var: str
    category: str
    notes: str = ""


# ---------------------------------------------------------------------------
# Category: Risch–Bronstein–Trager baseline
# ---------------------------------------------------------------------------
_BRONSTEIN = [
    CorpusEntry("(2*x*log(x^2+1)+x^3)/(x^2+1)", "x", "BRONSTEIN",
                "bronstein_001: FriCAS verified by Lean"),
    CorpusEntry("x/(x^2+1)", "x", "BRONSTEIN",
                "bronstein_003: caveat-free in both Lean and Coq"),
    CorpusEntry("2*x/(1+x^4)", "x", "BRONSTEIN",
                "bronstein_004: arctan chain"),
    CorpusEntry("(x+1)/(x*(x+2))", "x", "BRONSTEIN",
                "bronstein_005: FORM_DISAGREE — FriCAS/Maxima factored, SymPy product"),
    CorpusEntry("1/(x^2+2*x+2)", "x", "BRONSTEIN",
                "bronstein_006: atan(x+1)"),
    CorpusEntry("1/x", "x", "BRONSTEIN",
                "bronstein_007: branch-cut disagreement between Lean and Coq"),
    CorpusEntry("x/(x^2-4)", "x", "BRONSTEIN",
                "bronstein_008: log product form"),
    CorpusEntry("1/(x*(x+1)*(x+2))", "x", "BRONSTEIN",
                "bronstein_009: FORM_DISAGREE — FriCAS/Maxima factored, SymPy product"),
]

# ---------------------------------------------------------------------------
# Category: Rational PFD — form disagreements
# ---------------------------------------------------------------------------
_RATIONAL_PFD = [
    CorpusEntry("1/(x^2-1)", "x", "RATIONAL_PFD",
                "log(x-1)/2 - log(x+1)/2 vs atanh variants"),
    CorpusEntry("1/(1-x^2)", "x", "RATIONAL_PFD",
                "sign variant of 1/(x^2-1)"),
    CorpusEntry("1/(x^4-1)", "x", "RATIONAL_PFD",
                "PFD with real and complex poles"),
    CorpusEntry("x/(x^4-1)", "x", "RATIONAL_PFD",
                "log product form vs factored"),
    CorpusEntry("1/(x^3-1)", "x", "RATIONAL_PFD",
                "one real pole + complex conjugate pair"),
    CorpusEntry("1/(x^3+x)", "x", "RATIONAL_PFD",
                "log(x) - log(x^2+1)/2"),
    CorpusEntry("1/(x^2*(x+1))", "x", "RATIONAL_PFD",
                "-1/x + log(x+1) - log(x)"),
    CorpusEntry("(x^2+1)/(x^4-1)", "x", "RATIONAL_PFD",
                "simplifies to log(x-1)/2 - log(x+1)/2"),
    CorpusEntry("1/(x*(x+1)*(x-1))", "x", "RATIONAL_PFD",
                "three real poles, symmetric"),
]

# ---------------------------------------------------------------------------
# Category: Radical — acosh/asinh vs log form disagreement
# ---------------------------------------------------------------------------
_RADICAL = [
    CorpusEntry("1/sqrt(x^2-1)", "x", "RADICAL",
                "FORM_DISAGREE: Maxima acosh(x), SymPy log(x+sqrt(x^2-1))"),
    CorpusEntry("1/sqrt(x^2+1)", "x", "RADICAL",
                "FORM_DISAGREE: Maxima asinh(x), SymPy log(x+sqrt(x^2+1))"),
    CorpusEntry("sqrt(x^2-1)", "x", "RADICAL",
                "x*sqrt(x^2-1)/2 - acosh(x)/2  vs  log-based form"),
    CorpusEntry("sqrt(x^2+1)", "x", "RADICAL",
                "x*sqrt(x^2+1)/2 + asinh(x)/2"),
    CorpusEntry("sqrt(1-x^2)", "x", "RADICAL",
                "x*sqrt(1-x^2)/2 + asin(x)/2  (all CAS agree)"),
    CorpusEntry("1/sqrt(1-x^2)", "x", "RADICAL",
                "asin(x)  (all agree)"),
    CorpusEntry("x*sqrt(x^2+1)", "x", "RADICAL",
                "(x^2+1)^(3/2)/3"),
    CorpusEntry("x/sqrt(x^2+1)", "x", "RADICAL",
                "sqrt(x^2+1)"),
]

# ---------------------------------------------------------------------------
# Category: Inverse trig and log-poly
# ---------------------------------------------------------------------------
_TRIG_INV = [
    CorpusEntry("atan(x)", "x", "TRIG_INV",
                "x*atan(x) - log(x^2+1)/2"),
    CorpusEntry("asin(x)", "x", "TRIG_INV",
                "x*asin(x) + sqrt(1-x^2)"),
    CorpusEntry("log(x)", "x", "TRIG_INV",
                "x*log(x) - x  (all agree)"),
    CorpusEntry("log(x)/x", "x", "TRIG_INV",
                "log(x)^2/2"),
    CorpusEntry("1/(x*log(x))", "x", "TRIG_INV",
                "log(log(x))"),
    CorpusEntry("x*log(x)", "x", "TRIG_INV",
                "x^2*log(x)/2 - x^2/4"),
    CorpusEntry("x^3/(x^2+1)", "x", "TRIG_INV",
                "x^2/2 - log(x^2+1)/2"),
    CorpusEntry("x^2/(x^4+1)", "x", "TRIG_INV",
                "mixed log and atan"),
]

# ---------------------------------------------------------------------------
# Category: Non-elementary (all CAS should return None or a special function)
# ---------------------------------------------------------------------------
_NON_ELEMENTARY = [
    CorpusEntry("exp(-x^2)", "x", "NON_ELEMENTARY",
                "Gaussian integral: no elementary form (erf)"),
    CorpusEntry("sin(x)/x", "x", "NON_ELEMENTARY",
                "Si(x): sine integral, not elementary"),
    CorpusEntry("exp(x)/x", "x", "NON_ELEMENTARY",
                "Ei(x): exponential integral, not elementary"),
    CorpusEntry("1/log(x)", "x", "NON_ELEMENTARY",
                "Li(x): logarithmic integral, not elementary"),
]

_ALL = _BRONSTEIN + _RATIONAL_PFD + _RADICAL + _TRIG_INV + _NON_ELEMENTARY

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_corpus() -> list[CorpusEntry]:
    """Return the full corpus (all categories)."""
    return list(_ALL)


def load_bronstein_set() -> list[CorpusEntry]:
    """Return only the 8 Risch–Bronstein–Trager baseline entries."""
    return list(_BRONSTEIN)


def load_disagreement_candidates() -> list[CorpusEntry]:
    """
    Return entries known or suspected to show form or domain disagreement
    between at least two of the three CAS systems.
    """
    return [
        e for e in _ALL
        if "FORM_DISAGREE" in e.notes or "DOMAIN_DISAGREE" in e.notes
        or e.category in ("RADICAL", "RATIONAL_PFD")
    ]
