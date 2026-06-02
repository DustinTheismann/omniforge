"""
Tests for the live CAS hunt engine (cross_prover/cas_hunt.py).

The live two-CAS scan itself needs SymPy + Maxima installed and is exercised in
the cas-hunt.yml CI job, not here.  These unit tests cover the pure logic:
corpus shape, the triage derivative checker (SymPy only), unevaluated-integral
detection, and verdict classification — none of which spawn Maxima.
"""
from __future__ import annotations

import pytest

from cross_prover.cas_hunt import (
    HUNT_CORPUS,
    HuntResult,
    TRIAGE_REVIEWED_FALSE_POSITIVES,
    classify_pair,
    deriv_residual_is_zero,
    hunt_corpus,
    is_unevaluated,
    summarise,
)


# ---------------------------------------------------------------------------
# Corpus
# ---------------------------------------------------------------------------

def test_corpus_is_substantial():
    assert len(HUNT_CORPUS) >= 150


def test_corpus_entries_are_pairs():
    for ig, family in HUNT_CORPUS:
        assert isinstance(ig, str) and ig
        assert isinstance(family, str) and family


def test_corpus_filter_by_category():
    trig = hunt_corpus(["TRIG"])
    assert trig
    assert all(fam == "TRIG" for _, fam in trig)


# ---------------------------------------------------------------------------
# Unevaluated-integral detection
# ---------------------------------------------------------------------------

def test_is_unevaluated_detects_integral():
    assert is_unevaluated("Integral(sqrt(tan(x)), x)")
    assert is_unevaluated(None)
    assert is_unevaluated("")


def test_is_unevaluated_passes_real_answers():
    assert not is_unevaluated("log(x)")
    assert not is_unevaluated("x*atan(x) - log(x**2 + 1)/2")
    assert not is_unevaluated("sqrt(pi)*erf(x)/2")  # special fn is a real answer


# ---------------------------------------------------------------------------
# Triage derivative checker (SymPy only)
# ---------------------------------------------------------------------------

def test_deriv_check_accepts_correct_antideriv():
    assert deriv_residual_is_zero("x**2/2", "x", "x") is True
    assert deriv_residual_is_zero("log(x)", "1/x", "x") is True
    assert deriv_residual_is_zero("atan(x)", "1/(1+x**2)", "x") is True


def test_deriv_check_rejects_wrong_antideriv():
    # d/dx (x**3) = 3x**2, not x**2
    assert deriv_residual_is_zero("x**3", "x**2", "x") is False


def test_deriv_check_accepts_globally_valid_radical_form():
    """asinh(x) is a globally valid antiderivative of 1/sqrt(x^2+1) — must pass."""
    res = deriv_residual_is_zero("asinh(x)", "1/sqrt(x**2+1)", "x")
    assert res is True


def test_deriv_check_flags_domain_restricted_form_as_false():
    """
    -asinh(1/x) is correct for 1/(x*sqrt(x^2+1)) only on x>0; for x<0 the sign
    flips.  The full-range checker therefore returns False — which is exactly
    why this integrand lives in TRIAGE_REVIEWED_FALSE_POSITIVES (domain-
    restricted, not an arithmetic error).  This test pins that behaviour so the
    review table stays justified.
    """
    res = deriv_residual_is_zero("-asinh(1/x)", "1/(x*sqrt(x**2+1))", "x")
    assert res is False
    assert "1/(x*sqrt(x^2+1))" in TRIAGE_REVIEWED_FALSE_POSITIVES


def test_deriv_check_unevaluated_returns_none():
    assert deriv_residual_is_zero("Integral(f(x), x)", "f(x)", "x") is None


# ---------------------------------------------------------------------------
# Verdict classification
# ---------------------------------------------------------------------------

def test_classify_agree():
    v, _ = classify_pair("1/x", "x", "log(x)", "log(x)", True, True)
    assert v == "AGREE"


def test_classify_form_disagree():
    v, _ = classify_pair(
        "(x+1)/(x*(x+2))", "x",
        "log(x**2+2*x)/2", "log(x)/2+log(x+2)/2", True, True,
    )
    assert v == "FORM_DISAGREE"


def test_classify_genuine_disagree_one_fails():
    v, note = classify_pair("f", "x", "good", "bad", True, False)
    assert v == "GENUINE_DISAGREE"
    assert "Maxima" in note


def test_classify_both_wrong():
    v, _ = classify_pair("f", "x", "a", "b", False, False)
    assert v == "BOTH_WRONG"


def test_classify_one_missing():
    v, _ = classify_pair("f", "x", "log(x)", None, True, None)
    assert v == "ONE_MISSING"


def test_classify_all_missing():
    v, _ = classify_pair("f", "x", None, None, None, None)
    assert v == "ALL_MISSING"


def test_classify_genuine_only_answer_fails():
    """A lone answer that fails its own check is a GENUINE_DISAGREE, not ONE_MISSING."""
    v, _ = classify_pair("f", "x", "wrong", None, False, None)
    assert v == "GENUINE_DISAGREE"


# ---------------------------------------------------------------------------
# summarise() annotation
# ---------------------------------------------------------------------------

def test_summarise_annotates_reviewed_false_positives():
    results = [
        HuntResult("1/(x*sqrt(x^2+1))", "RADICAL", "-asinh(1/x)", "-asinh(1/x)",
                   False, False, "BOTH_WRONG", "triage"),
        HuntResult("1/x", "RATIONAL", "log(x)", "log(x)", True, True, "AGREE", ""),
    ]
    s = summarise(results)
    assert s["net_genuine_after_review"] == 0
    assert s["both_wrong"][0]["triage_reviewed"] is True
    assert s["unreviewed_candidates"] == []


def test_summarise_flags_unreviewed_genuine():
    results = [
        HuntResult("made_up_integrand", "MISC", "good", "actually_wrong",
                   True, False, "GENUINE_DISAGREE", "triage"),
    ]
    s = summarise(results)
    # Not in the reviewed table → must surface as an unreviewed candidate.
    assert s["net_genuine_after_review"] == 1
    assert s["unreviewed_candidates"][0]["integrand"] == "made_up_integrand"


def test_reviewed_table_nonempty():
    assert len(TRIAGE_REVIEWED_FALSE_POSITIVES) >= 4
