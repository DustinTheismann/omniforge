"""
Tests for protocols/claim_protocol — schema, types, validate.

Run with:  python -m pytest tests/test_claim_protocol.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from protocols.claim_protocol.validate import validate_claim, validate_claim_file, ClaimValidationError
from protocols.claim_protocol.types import Claim, ClaimType, EvidenceClass, ClaimFlag

EXAMPLES_DIR = Path(__file__).parent.parent / "protocols" / "claim_protocol" / "examples"
EXAMPLE_FILES = list(EXAMPLES_DIR.glob("*.json"))


# ---------------------------------------------------------------------------
# Schema validation against all example files
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", EXAMPLE_FILES, ids=lambda p: p.name)
def test_example_validates(path: Path):
    errors = validate_claim_file(path)
    assert not errors, f"{path.name} schema errors:\n" + "\n".join(errors)


# ---------------------------------------------------------------------------
# validate_claim
# ---------------------------------------------------------------------------

def test_validate_missing_required_fields():
    errors = validate_claim({"claim_type": "symbolic_antiderivative"})
    assert any("claim_id" in e or "required" in e.lower() for e in errors)


def test_validate_unknown_claim_type():
    claim = {
        "claim_id": "pf.test.000001",
        "claim_type": "unknown_type",
        "natural_language": "test",
        "source": {"kind": "human"}
    }
    errors = validate_claim(claim)
    assert errors  # unknown enum value


def test_validate_raises_on_error():
    with pytest.raises(ClaimValidationError):
        validate_claim({"claim_type": "bad"}, raise_on_error=True)


def test_validate_clean_claim_no_errors():
    claim = {
        "claim_id": "pf.test.000001",
        "claim_type": "theorem_statement",
        "natural_language": "1 + 1 = 2",
        "source": {"kind": "human", "name": "Peano"}
    }
    assert validate_claim(claim) == []


# ---------------------------------------------------------------------------
# types.py — ClaimType
# ---------------------------------------------------------------------------

def test_claim_type_values():
    assert ClaimType.SYMBOLIC_ANTIDERIVATIVE.value == "symbolic_antiderivative"
    assert ClaimType.ALGORITHM_BENCHMARK.value == "algorithm_benchmark"


# ---------------------------------------------------------------------------
# types.py — EvidenceClass level ordering
# ---------------------------------------------------------------------------

def test_evidence_class_levels_ordered():
    classes_in_order = [
        EvidenceClass.E0_RAW_CLAIM,
        EvidenceClass.E1_SOURCED,
        EvidenceClass.E2_PARSED,
        EvidenceClass.E3_EXECUTABLE,
        EvidenceClass.E4_REPRODUCED,
        EvidenceClass.E5_NUMERICALLY_SUPPORTED,
        EvidenceClass.E6_SYMBOLICALLY_SUPPORTED,
        EvidenceClass.E7_FORMALLY_VERIFIED,
        EvidenceClass.E8_CROSS_VERIFIED,
        EvidenceClass.E9_ADVERSARIALLY_HARDENED,
        EvidenceClass.E10_FIELD_VALIDATED,
    ]
    for i, ec in enumerate(classes_in_order):
        assert ec.level == i, f"{ec.value} should have level {i}, got {ec.level}"


def test_ex_refuted_has_negative_level():
    assert EvidenceClass.EX_REFUTED.level < 0


def test_cannot_upgrade_from_refuted():
    assert not EvidenceClass.EX_REFUTED.can_upgrade_to(EvidenceClass.E0_RAW_CLAIM)


# ---------------------------------------------------------------------------
# types.py — Claim.from_dict / to_dict round-trip
# ---------------------------------------------------------------------------

def test_claim_roundtrip():
    raw = json.loads((EXAMPLES_DIR / "int_000001.json").read_text())
    claim = Claim.from_dict(raw)
    assert claim.claim_id == raw["claim_id"]
    assert claim.claim_type == ClaimType.SYMBOLIC_ANTIDERIVATIVE
    assert claim.evidence_class == EvidenceClass.E2_PARSED


def test_claim_roundtrip_with_flags():
    raw = json.loads((EXAMPLES_DIR / "int_000002.json").read_text())
    claim = Claim.from_dict(raw)
    assert ClaimFlag.REQUIRES_ASSUMPTIONS in claim.flags
    assert claim.evidence_class == EvidenceClass.E7_FORMALLY_VERIFIED


def test_to_dict_preserves_claim_type():
    raw = json.loads((EXAMPLES_DIR / "algo_000001.json").read_text())
    claim = Claim.from_dict(raw)
    out = claim.to_dict()
    assert out["claim_type"] == "algorithm_benchmark"


# ---------------------------------------------------------------------------
# All examples round-trip through Claim.from_dict
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", EXAMPLE_FILES, ids=lambda p: p.name)
def test_example_loads_as_claim(path: Path):
    raw = json.loads(path.read_text())
    claim = Claim.from_dict(raw)
    assert claim.claim_id == raw["claim_id"]
