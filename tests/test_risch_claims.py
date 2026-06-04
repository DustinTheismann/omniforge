"""
Tests that the 9 kernel-verified RischVerification.lean theorems are correctly
wired into ProofForge as E7_FORMALLY_VERIFIED Claim instances.

These tests guard the bridge between the Lean proof layer and the ProofForge
evidence protocol — if any claim file regresses below E7, or loses its
formal_verified flag, these tests fail.

Run with:  python -m pytest tests/test_risch_claims.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from protocols.claim_protocol.validate import validate_claim
from protocols.claim_protocol.types import EvidenceClass
from protocols.evidence_protocol.grader import grade

EXAMPLES_DIR = Path(__file__).parent.parent / "protocols" / "claim_protocol" / "examples"
LEAN_SOURCE   = Path(__file__).parent.parent / "fricas_bridge" / "RischVerification.lean"

RISCH_IDS = [f"pf.integral.bronstein_{i:03d}" for i in range(1, 10)]

RISCH_FILES = [
    EXAMPLES_DIR / f"risch_bronstein_{i:03d}.json" for i in range(1, 10)
]


@pytest.fixture(scope="module")
def risch_claims() -> list[dict]:
    return [json.loads(p.read_text()) for p in RISCH_FILES]


# ---------------------------------------------------------------------------
# File existence
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", RISCH_FILES, ids=lambda p: p.name)
def test_risch_claim_file_exists(path: Path):
    assert path.exists(), f"Missing claim file: {path.name}"


# ---------------------------------------------------------------------------
# Schema validity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", RISCH_FILES, ids=lambda p: p.name)
def test_risch_claim_validates(path: Path):
    claim = json.loads(path.read_text())
    errors = validate_claim(claim)
    assert not errors, f"{path.name} schema errors:\n" + "\n".join(errors)


# ---------------------------------------------------------------------------
# Evidence class — every claim must be E7_FORMALLY_VERIFIED
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", RISCH_FILES, ids=lambda p: p.name)
def test_risch_claim_is_e7(path: Path):
    claim = json.loads(path.read_text())
    assert claim["evidence_class"] == "E7_FORMALLY_VERIFIED", (
        f"{path.name}: expected E7_FORMALLY_VERIFIED, got {claim['evidence_class']}"
    )


@pytest.mark.parametrize("path", RISCH_FILES, ids=lambda p: p.name)
def test_grader_assigns_e7(path: Path):
    claim = json.loads(path.read_text())
    computed = grade(claim)
    assert computed == EvidenceClass.E7_FORMALLY_VERIFIED, (
        f"{path.name}: grader returned {computed.value}"
    )


# ---------------------------------------------------------------------------
# formal_verified invariant — must be True in every checker result
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", RISCH_FILES, ids=lambda p: p.name)
def test_formal_verified_is_true(path: Path):
    claim = json.loads(path.read_text())
    for cr in claim.get("checker_results", []):
        if cr.get("checker", "").lower() in ("lean4", "lean"):
            assert cr.get("formal_verified") is True, (
                f"{path.name}: Lean checker_result has formal_verified != True"
            )


@pytest.mark.parametrize("path", RISCH_FILES, ids=lambda p: p.name)
def test_formal_target_status_proved(path: Path):
    claim = json.loads(path.read_text())
    for ft in claim.get("formal_targets", []):
        assert ft["status"] == "proved", (
            f"{path.name}: formal_target status is '{ft['status']}', expected 'proved'"
        )


# ---------------------------------------------------------------------------
# Source hash — must match current RischVerification.lean
# ---------------------------------------------------------------------------

def test_source_hashes_match_lean_file(risch_claims):
    import hashlib
    h = hashlib.sha256()
    with open(LEAN_SOURCE, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    current_hash = h.hexdigest()

    for claim in risch_claims:
        stored = claim.get("artifacts", {}).get("source_hash", "")
        assert stored == current_hash, (
            f"{claim['claim_id']}: source_hash {stored[:12]}… "
            f"≠ current {current_hash[:12]}…  "
            f"(run: python fricas_bridge/proofforge_export.py to regenerate)"
        )


# ---------------------------------------------------------------------------
# Claim IDs are correct sequence
# ---------------------------------------------------------------------------

def test_claim_ids_are_sequential(risch_claims):
    actual_ids = [c["claim_id"] for c in risch_claims]
    assert actual_ids == RISCH_IDS, f"ID mismatch: {actual_ids}"


# ---------------------------------------------------------------------------
# Discrepancy class distribution — assert bridge covers all 4 classes
# ---------------------------------------------------------------------------

def test_covers_class_a(risch_claims):
    no_hyp = [c for c in risch_claims if not c.get("assumptions")]
    assert no_hyp, "No Class A claims (no domain restrictions) found"


def test_covers_class_b_or_higher(risch_claims):
    with_hyp = [c for c in risch_claims if c.get("assumptions")]
    assert with_hyp, "No claims with domain restrictions found"


def test_max_discrepancy_is_three_poles(risch_claims):
    three = [c for c in risch_claims
             if len(c.get("assumptions", [])) >= 3]
    assert three, "No Class D (3+ pole) claim found"


# ---------------------------------------------------------------------------
# CAS source is FriCAS
# ---------------------------------------------------------------------------

def test_all_sourced_from_fricas(risch_claims):
    for c in risch_claims:
        assert c["source"]["name"] == "FriCAS", (
            f"{c['claim_id']}: expected source.name == 'FriCAS'"
        )


# ---------------------------------------------------------------------------
# Lean theorem names appear in statement_text
# ---------------------------------------------------------------------------

THEOREM_NAME_MAP = {
    "pf.integral.bronstein_001": "risch_verified_bronstein_1",
    "pf.integral.bronstein_002": "risch_equational",
    "pf.integral.bronstein_003": "risch_simple_log",
    "pf.integral.bronstein_004": "risch_arctan",
    "pf.integral.bronstein_005": "risch_partial_fractions",
    "pf.integral.bronstein_006": "risch_arctan_shifted",
    "pf.integral.bronstein_007": "risch_recip_x",
    "pf.integral.bronstein_008": "risch_log_quadratic_neg",
    "pf.integral.bronstein_009": "risch_three_poles",
}

@pytest.mark.parametrize("path", RISCH_FILES, ids=lambda p: p.name)
def test_theorem_name_in_statement(path: Path):
    claim = json.loads(path.read_text())
    cid = claim["claim_id"]
    expected_name = THEOREM_NAME_MAP[cid]
    stmt = claim["formal_targets"][0]["statement_text"]
    assert expected_name in stmt, (
        f"{cid}: expected '{expected_name}' in statement_text, got:\n{stmt}"
    )
