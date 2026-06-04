"""
Tests for cross_prover/cross_claim.py — the integration lane's E8 path.

A caveat-free cross-prover certificate (Lean 4 + Coq, same statement, same
domain) becomes a ProofForge Ω claim graded at E8_CROSS_VERIFIED. Branch-cut-
divergent certificates are honestly refused (held at E7).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from cross_prover.cross_certificate import build_certificate
from cross_prover.cross_claim import claim_from_cross_certificate
from protocols.claim_protocol.types import EvidenceClass
from protocols.claim_protocol.validate import validate_claim
from protocols.evidence_protocol.grader import grade

ROOT = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# E8 by construction for caveat-free certificates
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("claim_id", [
    "pf.integral.bronstein_003",
    "pf.integral.bronstein_004",
])
def test_caveat_free_cert_grades_e8(claim_id):
    cert = build_certificate(claim_id)
    claim, _ = claim_from_cross_certificate(cert)
    assert claim["evidence_class"] == EvidenceClass.E8_CROSS_VERIFIED.value


def test_grade_directly_reaches_e8():
    cert = build_certificate("pf.integral.bronstein_003")
    claim, _ = claim_from_cross_certificate(cert)
    assert grade(claim) == EvidenceClass.E8_CROSS_VERIFIED


def test_two_distinct_formal_families():
    """The two checkers must be lean4 and coq — two independent formal families."""
    cert = build_certificate("pf.integral.bronstein_003")
    claim, _ = claim_from_cross_certificate(cert)
    checkers = {r["checker"] for r in claim["checker_results"]}
    assert checkers == {"lean4", "coq"}
    assert all(r["formal_verified"] is True for r in claim["checker_results"])


def test_two_formal_targets_proved():
    cert = build_certificate("pf.integral.bronstein_003")
    claim, _ = claim_from_cross_certificate(cert)
    assert len(claim["formal_targets"]) == 2
    assert all(t["status"] == "proved" for t in claim["formal_targets"])


# ---------------------------------------------------------------------------
# Honest gate: branch-cut cases refused
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("claim_id", [
    "pf.integral.bronstein_007",
    "pf.integral.bronstein_009",
])
def test_branch_cut_cert_refused(claim_id):
    cert = build_certificate(claim_id)
    with pytest.raises(ValueError, match="caveat-free"):
        claim_from_cross_certificate(cert)


def test_coq_kernel_rejection_fails_closed():
    """If the Coq kernel is reported as rejecting, the claim must not be graded."""
    cert = build_certificate("pf.integral.bronstein_003")
    with pytest.raises(ValueError, match="rejected"):
        claim_from_cross_certificate(cert, coq_kernel_verified=False)


def test_explicit_coq_verified_true_still_e8():
    cert = build_certificate("pf.integral.bronstein_003")
    claim, _ = claim_from_cross_certificate(cert, coq_kernel_verified=True)
    assert claim["evidence_class"] == EvidenceClass.E8_CROSS_VERIFIED.value


# ---------------------------------------------------------------------------
# Schema + runpack
# ---------------------------------------------------------------------------

def test_claim_validates_against_schema():
    cert = build_certificate("pf.integral.bronstein_003")
    claim, _ = claim_from_cross_certificate(cert)
    errors = validate_claim(claim)
    assert errors == [], f"schema errors: {errors}"


def test_runpack_has_two_commands():
    cert = build_certificate("pf.integral.bronstein_003")
    _, runpack = claim_from_cross_certificate(cert)
    d = runpack.to_dict()
    assert len(d["commands"]) == 2  # lake build + coqc


def test_runpack_records_both_artifacts():
    cert = build_certificate("pf.integral.bronstein_003")
    _, runpack = claim_from_cross_certificate(cert)
    roles = {a["role"] for a in runpack.to_dict()["artifacts"]}
    assert roles == {"lean_proof", "coq_proof"}


def test_runpack_has_manifest_hash():
    cert = build_certificate("pf.integral.bronstein_003")
    _, runpack = claim_from_cross_certificate(cert)
    assert isinstance(runpack.manifest_hash, str) and len(runpack.manifest_hash) == 64


def test_claim_id_namespaced():
    cert = build_certificate("pf.integral.bronstein_003")
    claim, _ = claim_from_cross_certificate(cert)
    assert claim["claim_id"] == "pf.cross.bronstein_003"


# ---------------------------------------------------------------------------
# Canonical example file
# ---------------------------------------------------------------------------

def test_example_cross_bronstein_003_validates():
    path = ROOT / "protocols" / "claim_protocol" / "examples" / "cross_bronstein_003.json"
    assert path.exists()
    errors = validate_claim(json.loads(path.read_text()))
    assert errors == [], f"cross_bronstein_003.json schema errors: {errors}"


def test_example_cross_bronstein_003_grades_e8():
    path = ROOT / "protocols" / "claim_protocol" / "examples" / "cross_bronstein_003.json"
    claim = json.loads(path.read_text())
    assert grade(claim) == EvidenceClass.E8_CROSS_VERIFIED
