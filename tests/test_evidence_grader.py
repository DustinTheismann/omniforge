"""
Tests for protocols/evidence_protocol/grader.py

Run with:  python -m pytest tests/test_evidence_grader.py -v
"""
from __future__ import annotations

import pytest

from protocols.evidence_protocol.grader import grade, downgrade, _checker_family
from protocols.claim_protocol.types import EvidenceClass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _claim(**kwargs) -> dict:
    """Build a minimal claim dict, optionally overriding fields."""
    base = {
        "claim_id": "pf.test.000001",
        "claim_type": "symbolic_antiderivative",
        "natural_language": "test",
        "source": {"kind": "cas", "name": "FriCAS"},
        "checker_results": [],
        "formal_targets": [],
        "obligations": [],
        "assumptions": [],
        "flags": [],
        "metadata": {},
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# Baseline grading
# ---------------------------------------------------------------------------

def test_empty_claim_gets_e2():
    claim = _claim()
    assert grade(claim) == EvidenceClass.E2_PARSED


def test_no_source_name_stays_e2():
    claim = _claim(source={"kind": "cas"})
    result = grade(claim)
    # E1 requires name — without name, still E2 (schema-valid)
    assert result == EvidenceClass.E2_PARSED


def test_with_source_name_can_reach_e1_minimum():
    # grade returns highest reachable; with source + no obligations, should be ≥ E2
    claim = _claim(source={"kind": "cas", "name": "FriCAS"})
    assert grade(claim).level >= 1


# ---------------------------------------------------------------------------
# Obligation gate → E3
# ---------------------------------------------------------------------------

def test_ran_obligation_reaches_e3():
    claim = _claim(obligations=[
        {"obligation_id": "o1", "kind": "formal_derivative_check", "status": "passed"}
    ])
    assert grade(claim).level >= 3


def test_pending_obligation_does_not_reach_e3():
    claim = _claim(obligations=[
        {"obligation_id": "o1", "kind": "formal_derivative_check", "status": "pending"}
    ])
    assert grade(claim).level < 3


# ---------------------------------------------------------------------------
# Numeric checker → E5
# ---------------------------------------------------------------------------

def test_numeric_checker_reaches_e5():
    claim = _claim(
        obligations=[{"obligation_id": "o1", "kind": "numeric_property", "status": "passed"}],
        checker_results=[{"checker": "hypothesis", "result": "supported", "formal_verified": False}]
    )
    assert grade(claim) == EvidenceClass.E5_NUMERICALLY_SUPPORTED


# ---------------------------------------------------------------------------
# CAS checker → E6
# ---------------------------------------------------------------------------

def test_cas_checker_reaches_e6():
    claim = _claim(
        obligations=[{"obligation_id": "o1", "kind": "formal_derivative_check", "status": "passed"}],
        checker_results=[
            {"checker": "sympy", "result": "supported", "formal_verified": False}
        ]
    )
    assert grade(claim) == EvidenceClass.E6_SYMBOLICALLY_SUPPORTED


# ---------------------------------------------------------------------------
# Formal verified → E7
# ---------------------------------------------------------------------------

def test_formal_verified_reaches_e7():
    claim = _claim(
        obligations=[{"obligation_id": "o1", "kind": "formal_theorem", "status": "passed"}],
        checker_results=[
            {"checker": "Lean4", "result": "passed", "formal_verified": True}
        ],
        formal_targets=[{"system": "Lean4", "status": "proved"}]
    )
    assert grade(claim) == EvidenceClass.E7_FORMALLY_VERIFIED


def test_formal_verified_false_does_not_reach_e7():
    claim = _claim(
        obligations=[{"obligation_id": "o1", "kind": "formal_theorem", "status": "passed"}],
        checker_results=[
            {"checker": "Lean4", "result": "passed", "formal_verified": False}
        ],
        formal_targets=[{"system": "Lean4", "status": "proved"}]
    )
    assert grade(claim).level < 7


def test_sorry_proof_does_not_reach_e7():
    claim = _claim(
        checker_results=[{"checker": "Lean4", "result": "passed", "formal_verified": True}],
        formal_targets=[{"system": "Lean4", "status": "sorry"}]
    )
    assert grade(claim).level < 7


# ---------------------------------------------------------------------------
# Cross-verified → E8
# ---------------------------------------------------------------------------

def test_two_families_reaches_e8():
    claim = _claim(
        obligations=[{"obligation_id": "o1", "kind": "formal_theorem", "status": "passed"}],
        checker_results=[
            {"checker": "lean4", "result": "passed", "formal_verified": True},
            {"checker": "sympy", "result": "supported", "formal_verified": False},
        ],
        formal_targets=[{"system": "Lean4", "status": "proved"}]
    )
    assert grade(claim) == EvidenceClass.E8_CROSS_VERIFIED


# ---------------------------------------------------------------------------
# Refutation overrides everything
# ---------------------------------------------------------------------------

def test_refuted_by_failed_formal_target():
    claim = _claim(
        checker_results=[{"checker": "Lean4", "result": "passed", "formal_verified": True}],
        formal_targets=[{"system": "Lean4", "status": "failed"}]
    )
    assert grade(claim) == EvidenceClass.EX_REFUTED


def test_refuted_by_counterexample_obligation():
    claim = _claim(
        obligations=[{"obligation_id": "o1", "kind": "counterexample_search", "status": "passed"}]
    )
    assert grade(claim) == EvidenceClass.EX_REFUTED


def test_refuted_by_refuted_checker_result_with_formal():
    claim = _claim(
        checker_results=[{"checker": "lean4", "result": "refuted", "formal_verified": True}]
    )
    assert grade(claim) == EvidenceClass.EX_REFUTED


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------

def test_downgrade_sets_ex_refuted():
    claim = _claim(evidence_class="E7_FORMALLY_VERIFIED")
    result = downgrade(claim, "counterexample found at x=0")
    assert result["evidence_class"] == EvidenceClass.EX_REFUTED.value


def test_downgrade_adds_note():
    claim = _claim()
    result = downgrade(claim, "test reason")
    assert "test reason" in result["metadata"]["notes"]


def test_downgrade_does_not_mutate_original():
    claim = _claim(evidence_class="E7_FORMALLY_VERIFIED")
    _ = downgrade(claim, "reason")
    assert claim["evidence_class"] != EvidenceClass.EX_REFUTED.value


# ---------------------------------------------------------------------------
# _checker_family classification
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("checker,expected", [
    ("lean4", "formal"), ("Lean4", "formal"), ("lean", "formal"),
    ("coq", "formal"), ("isabelle", "formal"),
    ("fricas", "cas"), ("sympy", "cas"), ("maxima", "cas"),
    ("z3", "smt"), ("cvc5", "smt"),
    ("cadical", "sat"), ("kissat", "sat"),
    ("hypothesis", "numeric"), ("pytest", "numeric"), ("interval_arithmetic", "numeric"),
    ("docker_repro", "repro"), ("notebook_repro", "repro"),
    ("something_else", "other"),
])
def test_checker_family(checker: str, expected: str):
    assert _checker_family(checker) == expected
