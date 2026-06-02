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
from typing import Optional


# Recognised expected-outcome tags.  These mirror DisagreementClass /
# DomainSubclass values so a corpus entry can be checked against what the
# detector actually reports (see tests/test_cas_corpus.py).
EXPECTED_OUTCOMES = frozenset({
    "agree",
    "agree_up_to_c",
    "form_disagree",
    "domain_disagree",
    "genuine_disagree",
    "one_missing",
    "two_missing",
    "all_missing",
    "unknown",            # not yet characterised
})

EXPECTED_SUBCLASSES = frozenset({
    "special_fn_repr",
    "analytic_continuation",
    "true_domain_divergence",
    None,
})


@dataclass(frozen=True)
class CorpusEntry:
    integrand: str
    var: str
    category: str
    notes: str = ""
    # Structured expectation: what the three-CAS detector *should* report for
    # this integrand, and (for domain_disagree) which subclass.  Defaults to
    # "unknown" so legacy entries remain valid; tests assert that every entry
    # with a concrete expectation matches the live detector output.
    expected: str = "unknown"
    expected_subclass: Optional[str] = None
    # Whether a committed Lean theorem in CasAdjudication.lean adjudicates this.
    kernel_adjudicated: bool = False

    def __post_init__(self) -> None:
        if self.expected not in EXPECTED_OUTCOMES:
            raise ValueError(
                f"CorpusEntry.expected={self.expected!r} not in EXPECTED_OUTCOMES"
            )
        if self.expected_subclass not in EXPECTED_SUBCLASSES:
            raise ValueError(
                f"CorpusEntry.expected_subclass={self.expected_subclass!r} invalid"
            )


# ---------------------------------------------------------------------------
# Category: Risch–Bronstein–Trager baseline
# ---------------------------------------------------------------------------
_BRONSTEIN = [
    CorpusEntry("(2*x*log(x^2+1)+x^3)/(x^2+1)", "x", "BRONSTEIN",
                "bronstein_001: FriCAS verified by Lean",
                expected="agree_up_to_c"),
    CorpusEntry("x/(x^2+1)", "x", "BRONSTEIN",
                "bronstein_003: caveat-free in both Lean and Coq",
                expected="agree"),
    CorpusEntry("2*x/(1+x^4)", "x", "BRONSTEIN",
                "bronstein_004: arctan chain",
                expected="agree"),
    CorpusEntry("(x+1)/(x*(x+2))", "x", "BRONSTEIN",
                "bronstein_005: FORM_DISAGREE — FriCAS/Maxima factored, SymPy product",
                expected="form_disagree", kernel_adjudicated=True),
    CorpusEntry("1/(x^2+2*x+2)", "x", "BRONSTEIN",
                "bronstein_006: atan(x+1)",
                expected="agree"),
    CorpusEntry("1/x", "x", "BRONSTEIN",
                "bronstein_007: branch-cut disagreement between Lean and Coq",
                expected="agree"),
    CorpusEntry("x/(x^2-4)", "x", "BRONSTEIN",
                "bronstein_008: log product form",
                expected="agree"),
    CorpusEntry("1/(x*(x+1)*(x+2))", "x", "BRONSTEIN",
                "bronstein_009: FORM_DISAGREE — FriCAS/Maxima factored, SymPy product",
                expected="form_disagree", kernel_adjudicated=True),
]

# ---------------------------------------------------------------------------
# Category: Rational PFD — form disagreements
# ---------------------------------------------------------------------------
_RATIONAL_PFD = [
    CorpusEntry("1/(x^2-1)", "x", "RATIONAL_PFD",
                "log(x-1)/2 - log(x+1)/2 vs atanh variants",
                expected="agree"),
    CorpusEntry("1/(1-x^2)", "x", "RATIONAL_PFD",
                "sign variant of 1/(x^2-1)",
                expected="agree"),
    CorpusEntry("1/(x^4-1)", "x", "RATIONAL_PFD",
                "PFD with real and complex poles",
                expected="agree"),
    CorpusEntry("x/(x^4-1)", "x", "RATIONAL_PFD",
                "log product form vs factored",
                expected="form_disagree", kernel_adjudicated=True),
    CorpusEntry("1/(x^3-1)", "x", "RATIONAL_PFD",
                "one real pole + complex conjugate pair; FriCAS+Maxima offline miss",
                expected="all_missing"),
    CorpusEntry("1/(x^3+x)", "x", "RATIONAL_PFD",
                "log(x) - log(x^2+1)/2; only SymPy cached offline",
                expected="one_missing"),
    CorpusEntry("1/(x^2*(x+1))", "x", "RATIONAL_PFD",
                "-1/x + log(x+1) - log(x)",
                expected="agree_up_to_c"),
    CorpusEntry("(x^2+1)/(x^4-1)", "x", "RATIONAL_PFD",
                "simplifies to log(x-1)/2 - log(x+1)/2; FriCAS+Maxima offline miss",
                expected="all_missing"),
    CorpusEntry("1/(x*(x+1)*(x-1))", "x", "RATIONAL_PFD",
                "three real poles, symmetric",
                expected="form_disagree", kernel_adjudicated=True),
]

# ---------------------------------------------------------------------------
# Category: Radical — acosh/asinh vs log form disagreement
# ---------------------------------------------------------------------------
_RADICAL = [
    CorpusEntry("1/sqrt(x^2-1)", "x", "RADICAL",
                "Maxima acosh(x), SymPy log(x+sqrt(x^2-1)): same fn, two notations",
                expected="domain_disagree", expected_subclass="special_fn_repr"),
    CorpusEntry("1/sqrt(x^2+1)", "x", "RADICAL",
                "Maxima asinh(x), SymPy log(x+sqrt(x^2+1)): same fn, two notations",
                expected="domain_disagree", expected_subclass="special_fn_repr"),
    CorpusEntry("sqrt(x^2-1)", "x", "RADICAL",
                "x*sqrt(x^2-1)/2 - acosh(x)/2  vs  log-based form",
                expected="domain_disagree", expected_subclass="special_fn_repr"),
    CorpusEntry("sqrt(x^2+1)", "x", "RADICAL",
                "x*sqrt(x^2+1)/2 + asinh(x)/2  vs  log-based form",
                expected="domain_disagree", expected_subclass="special_fn_repr"),
    CorpusEntry("sqrt(1-x^2)", "x", "RADICAL",
                "x*sqrt(1-x^2)/2 + asin(x)/2; only SymPy cached offline",
                expected="one_missing"),
    CorpusEntry("1/sqrt(1-x^2)", "x", "RADICAL",
                "asin(x); only SymPy cached offline",
                expected="one_missing"),
    CorpusEntry("x*sqrt(x^2+1)", "x", "RADICAL",
                "(x^2+1)^(3/2)/3; not in any offline cache",
                expected="all_missing"),
    CorpusEntry("x/sqrt(x^2+1)", "x", "RADICAL",
                "sqrt(x^2+1); not in any offline cache",
                expected="all_missing"),
]

# ---------------------------------------------------------------------------
# Category: Inverse trig and log-poly
# ---------------------------------------------------------------------------
_TRIG_INV = [
    CorpusEntry("atan(x)", "x", "TRIG_INV",
                "x*atan(x) - log(x^2+1)/2; only SymPy cached offline",
                expected="one_missing"),
    CorpusEntry("asin(x)", "x", "TRIG_INV",
                "x*asin(x) + sqrt(1-x^2); not in any offline cache",
                expected="all_missing"),
    CorpusEntry("log(x)", "x", "TRIG_INV",
                "x*log(x) - x  (all agree)",
                expected="agree"),
    CorpusEntry("log(x)/x", "x", "TRIG_INV",
                "log(x)^2/2; only SymPy cached offline",
                expected="one_missing"),
    CorpusEntry("1/(x*log(x))", "x", "TRIG_INV",
                "log(log(x)); only SymPy cached offline",
                expected="one_missing"),
    CorpusEntry("x*log(x)", "x", "TRIG_INV",
                "x^2*log(x)/2 - x^2/4; only SymPy cached offline",
                expected="one_missing"),
    CorpusEntry("x^3/(x^2+1)", "x", "TRIG_INV",
                "x^2/2 - log(x^2+1)/2; only SymPy cached offline",
                expected="one_missing"),
    CorpusEntry("x^2/(x^4+1)", "x", "TRIG_INV",
                "mixed log and atan; not in any offline cache",
                expected="all_missing"),
]

# ---------------------------------------------------------------------------
# Category: Non-elementary (all CAS should return None or a special function)
# ---------------------------------------------------------------------------
_NON_ELEMENTARY = [
    CorpusEntry("exp(-x^2)", "x", "NON_ELEMENTARY",
                "Gaussian integral: no elementary form (erf); not in offline caches",
                expected="all_missing"),
    CorpusEntry("sin(x)/x", "x", "NON_ELEMENTARY",
                "Si(x): sine integral, not elementary; not in offline caches",
                expected="all_missing"),
    CorpusEntry("exp(x)/x", "x", "NON_ELEMENTARY",
                "Ei(x): exponential integral, not elementary; not in offline caches",
                expected="all_missing"),
    CorpusEntry("1/log(x)", "x", "NON_ELEMENTARY",
                "Li(x): logarithmic integral, not elementary; not in offline caches",
                expected="all_missing"),
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
        if e.expected in ("form_disagree", "domain_disagree")
        or e.category in ("RADICAL", "RATIONAL_PFD")
    ]


def load_kernel_adjudicated() -> list[CorpusEntry]:
    """Return entries that a committed Lean theorem in CasAdjudication.lean proves."""
    return [e for e in _ALL if e.kernel_adjudicated]
