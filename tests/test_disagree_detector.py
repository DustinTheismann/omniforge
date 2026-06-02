"""
Tests for Tier 5.4 — Three-CAS disagreement detector with kernel adjudication plans.

Run with:  python -m pytest tests/test_disagree_detector.py -v
"""
from __future__ import annotations

import pytest

from fricas_bridge.disagree_detector import (
    DisagreementClass,
    DisagreementReport,
    KernelAdjudicationPlan,
    compare_triple,
    scan_bronstein,
    scan_corpus,
)


# ---------------------------------------------------------------------------
# Return types
# ---------------------------------------------------------------------------

def test_compare_triple_returns_report():
    r = compare_triple("1/x")
    assert isinstance(r, DisagreementReport)


def test_report_fields():
    r = compare_triple("1/x")
    assert r.integrand == "1/x"
    assert r.var == "x"
    assert r.disagreement in DisagreementClass._value2member_map_


def test_report_present_count_1_over_x():
    r = compare_triple("1/x")
    # FriCAS, SymPy, and Maxima all have 1/x → log(x)
    assert r.present_count == 3


# ---------------------------------------------------------------------------
# Confirmed agreeing cases
# ---------------------------------------------------------------------------

def test_1_over_x_agrees():
    r = compare_triple("1/x")
    assert r.disagreement == DisagreementClass.AGREE.value


def test_arctan_chain_agrees():
    r = compare_triple("2*x/(1+x^4)")
    assert r.disagreement == DisagreementClass.AGREE.value


def test_arctan_shifted_agrees():
    r = compare_triple("1/(x^2+2*x+2)")
    assert r.disagreement == DisagreementClass.AGREE.value


def test_bronstein_001_agree_up_to_c():
    """bronstein_001: agree up to constant (terms reordered)."""
    r = compare_triple("(2*x*log(x^2+1)+x^3)/(x^2+1)")
    assert r.disagreement in (
        DisagreementClass.AGREE.value,
        DisagreementClass.AGREE_UP_TO_C.value,
    )


# ---------------------------------------------------------------------------
# Confirmed FORM_DISAGREE: log factored vs product
# ---------------------------------------------------------------------------

def test_bronstein_005_form_disagree():
    """
    (x+1)/(x*(x+2)):
      FriCAS/Maxima → log(x)/2 + log(x+2)/2   (factored PFD)
      SymPy         → log(x^2+2*x)/2            (product form)
    Both are valid antiderivatives; they differ by a locally-constant
    complex offset on some connected components of the domain.
    """
    r = compare_triple("(x+1)/(x*(x+2))")
    assert r.disagreement == DisagreementClass.FORM_DISAGREE.value


def test_bronstein_009_form_disagree():
    """1/(x*(x+1)*(x+2)): same factored-vs-product pattern."""
    r = compare_triple("1/(x*(x+1)*(x+2))")
    assert r.disagreement == DisagreementClass.FORM_DISAGREE.value


def test_form_disagree_all_derivatives_correct():
    """Both forms must be verified correct by SymPy differentiation."""
    for ig in ["(x+1)/(x*(x+2))", "1/(x*(x+1)*(x+2))"]:
        r = compare_triple(ig)
        for src, ok in r.derivative_correct.items():
            assert ok, f"{ig}: {src} derivative check failed"


def test_form_disagree_has_adjudication_plan():
    r = compare_triple("(x+1)/(x*(x+2))")
    assert r.adjudication_plan is not None
    assert isinstance(r.adjudication_plan, KernelAdjudicationPlan)


def test_form_disagree_plan_form_equivalent():
    """Log factored-vs-product forms are adjudicated as 'form_equivalent'."""
    r = compare_triple("(x+1)/(x*(x+2))")
    assert r.adjudication_plan.adjudication_class == "form_equivalent"


def test_form_disagree_plan_has_three_candidates():
    r = compare_triple("(x+1)/(x*(x+2))")
    plan = r.adjudication_plan
    assert len(plan.candidates) == 3


def test_form_disagree_plan_candidates_have_lean_statements():
    r = compare_triple("(x+1)/(x*(x+2))")
    for c in r.adjudication_plan.candidates:
        assert "HasDerivAt" in c["lean_statement"]
        assert "source" in c
        assert "antideriv" in c


def test_form_disagree_fricas_and_maxima_agree():
    """FriCAS and Maxima both return the factored form; only SymPy uses product form."""
    r = compare_triple("(x+1)/(x*(x+2))")
    assert r.fricas_result is not None
    assert r.maxima_result is not None
    assert r.sympy_result is not None
    # FriCAS and Maxima should give the same factored form
    from fricas_bridge.disagree_detector import _norm
    assert _norm(r.fricas_result) == _norm(r.maxima_result)
    # SymPy gives the product form
    assert _norm(r.sympy_result) != _norm(r.fricas_result)


# ---------------------------------------------------------------------------
# Confirmed DOMAIN_DISAGREE: acosh/asinh vs log form
# ---------------------------------------------------------------------------

def test_1_over_sqrt_x2m1_domain_disagree():
    """
    1/sqrt(x^2-1):
      Maxima → acosh(x)               (domain: x ≥ 1 only)
      SymPy  → log(x+sqrt(x^2-1))    (analytic continuation)
    """
    r = compare_triple("1/sqrt(x^2-1)")
    assert r.disagreement == DisagreementClass.DOMAIN_DISAGREE.value


def test_1_over_sqrt_x2p1_domain_disagree():
    """
    1/sqrt(x^2+1):
      Maxima → asinh(x)               (total, equal to log form for all x)
      SymPy  → log(x+sqrt(x^2+1))    (same domain but different form)
    """
    r = compare_triple("1/sqrt(x^2+1)")
    assert r.disagreement == DisagreementClass.DOMAIN_DISAGREE.value


def test_sqrt_x2m1_domain_disagree():
    """sqrt(x^2-1): Maxima uses acosh, SymPy uses log form."""
    r = compare_triple("sqrt(x^2-1)")
    assert r.disagreement == DisagreementClass.DOMAIN_DISAGREE.value


def test_sqrt_x2p1_domain_disagree():
    """sqrt(x^2+1): Maxima uses asinh, SymPy uses log form."""
    r = compare_triple("sqrt(x^2+1)")
    assert r.disagreement == DisagreementClass.DOMAIN_DISAGREE.value


def test_domain_disagree_plan_domain_restricted():
    r = compare_triple("1/sqrt(x^2-1)")
    assert r.adjudication_plan is not None
    assert r.adjudication_plan.adjudication_class == "domain_restricted"


def test_domain_disagree_all_derivatives_correct():
    """All present antiderivatives should pass the derivative check."""
    r = compare_triple("1/sqrt(x^2-1)")
    for src, ok in r.derivative_correct.items():
        assert ok, f"1/sqrt(x^2-1): {src} derivative check failed"


# ---------------------------------------------------------------------------
# Bronstein full scan
# ---------------------------------------------------------------------------

def test_scan_bronstein_returns_eight():
    results = scan_bronstein()
    assert len(results) == 8


def test_scan_bronstein_no_genuine_disagree():
    """None of the Bronstein integrands should produce a GENUINE_DISAGREE."""
    for r in scan_bronstein():
        assert r.disagreement != DisagreementClass.GENUINE_DISAGREE.value, (
            f"{r.integrand!r}: unexpected GENUINE_DISAGREE"
        )


def test_scan_bronstein_two_form_disagrees():
    """Exactly bronstein_005 and bronstein_009 are FORM_DISAGREE."""
    form_disagrees = [
        r for r in scan_bronstein()
        if r.disagreement == DisagreementClass.FORM_DISAGREE.value
    ]
    assert len(form_disagrees) == 2
    integrands = {r.integrand for r in form_disagrees}
    assert "(x+1)/(x*(x+2))" in integrands
    assert "1/(x*(x+1)*(x+2))" in integrands


def test_scan_bronstein_all_have_three_present():
    """All 8 Bronstein integrands are in all three CAS caches."""
    for r in scan_bronstein():
        assert r.present_count == 3, f"{r.integrand!r}: only {r.present_count} CAS present"


def test_scan_bronstein_all_derivatives_correct():
    """All Bronstein antiderivatives pass the SymPy derivative check."""
    for r in scan_bronstein():
        for src, ok in r.derivative_correct.items():
            assert ok, f"{r.integrand!r}: {src} derivative check failed"


# ---------------------------------------------------------------------------
# scan_corpus utility
# ---------------------------------------------------------------------------

def test_scan_corpus_accepts_tuples():
    results = scan_corpus([("1/x", "x"), ("x/(x^2+1)", "x")])
    assert len(results) == 2


def test_scan_corpus_accepts_corpus_entries():
    from fricas_bridge.cas_corpus import load_bronstein_set
    results = scan_corpus(load_bronstein_set())
    assert len(results) == 8


# ---------------------------------------------------------------------------
# Missing entries
# ---------------------------------------------------------------------------

def test_unknown_integrand_all_missing():
    r = compare_triple("completely_unknown_42(x)")
    assert r.disagreement == DisagreementClass.ALL_MISSING.value
    assert r.present_count == 0
