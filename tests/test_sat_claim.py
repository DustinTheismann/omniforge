"""
Tests for the ProofForge Ω SAT lane wiring:
  - sat_claim.claim_from_sat_result → Claim dict + Runpack
  - evidence grader recognises cake_lpr as formal family (→ E8)
  - schema validation of the unsat_000001 example
  - ClaimType.UNSAT_CERTIFICATE exists
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from omniforge.lanes.sat_claim import claim_from_sat_result
from omniforge.lanes.sat_lane import ProofCheck, SatExecResult
from protocols.claim_protocol.types import ClaimType, EvidenceClass
from protocols.claim_protocol.validate import validate_claim
from protocols.evidence_protocol.grader import grade, _checker_family

ROOT = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok_check(checker: str) -> ProofCheck:
    ok_val = "s VERIFIED UNSAT" if checker == "cake_lpr" else "VERIFIED"
    return ProofCheck(checker=checker, ok=True, returncode=0 if checker == "cake_lpr" else (20 if checker == "lrat-trim" else 0), stdout=ok_val, stderr="")


def _mock_unsat_result(cnf_path: Path) -> SatExecResult:
    return SatExecResult(
        result="UNSAT",
        stdout="s UNSATISFIABLE\n",
        stderr="",
        commandline=["cadical", "--seed=0", str(cnf_path), "proof.drat"],
        drat_relpath="proofs/proof.drat",
        lrat_relpath="proofs/proof.lrat",
        check_drat=_ok_check("drat-trim"),
        check_lrat=ProofCheck("lrat-trim", ok=True, returncode=20, stdout="LRAT OK", stderr=""),
        check_cake_lpr=ProofCheck("cake_lpr", ok=True, returncode=0, stdout="s VERIFIED UNSAT\n", stderr=""),
    )


# ---------------------------------------------------------------------------
# ClaimType enum
# ---------------------------------------------------------------------------

def test_unsat_certificate_claim_type_exists():
    assert ClaimType.UNSAT_CERTIFICATE.value == "unsat_certificate"


# ---------------------------------------------------------------------------
# Evidence grader: cake_lpr in formal family
# ---------------------------------------------------------------------------

def test_cake_lpr_is_formal_family():
    assert _checker_family("cake_lpr") == "cake_lpr"


def test_drat_trim_is_sat_family():
    assert _checker_family("drat-trim") == "sat"


def test_lrat_trim_is_sat_family():
    assert _checker_family("lrat-trim") == "sat"


def test_unsat_claim_grades_e7(tmp_path):
    """Three-checker UNSAT claim with cake_lpr alone grades at E7_FORMALLY_VERIFIED.

    E8 requires ≥2 independent formal kernel systems. The SAT lane currently
    has one formal anchor (cake_lpr/HOL4). drat-trim and lrat-trim are sat-family
    corroboration, not independent formal kernels.
    """
    cnf = tmp_path / "test.cnf"
    cnf.write_text("p cnf 1 2\n1 0\n-1 0\n")
    res = _mock_unsat_result(cnf)
    claim_dict, _ = claim_from_sat_result(res, cnf_path=cnf, run_id="test_run_001")
    assert claim_dict["evidence_class"] == EvidenceClass.E7_FORMALLY_VERIFIED.value


def test_unsat_claim_grades_e7_via_grader():
    """Grade function directly: cake_lpr (1 formal system) + sat family → E7."""
    claim = {
        "source": {"kind": "benchmark", "name": "cadical"},
        "checker_results": [
            {"checker": "cadical",   "result": "passed", "formal_verified": False},
            {"checker": "drat-trim", "result": "passed", "formal_verified": False},
            {"checker": "lrat-trim", "result": "passed", "formal_verified": False},
            {"checker": "cake_lpr",  "result": "passed", "formal_verified": True},
        ],
        "formal_targets": [{"system": "other", "status": "proved"}],
        "obligations": [
            {"obligation_id": "o1", "kind": "formal_theorem", "status": "passed"},
        ],
        "assumptions": [],
        "flags": [],
        "metadata": {},
    }
    assert grade(claim) == EvidenceClass.E7_FORMALLY_VERIFIED


def test_two_formal_sat_checkers_grade_e8():
    """cake_lpr + isabelle (2 independent formal systems) → E8_CROSS_VERIFIED."""
    claim = {
        "source": {"kind": "benchmark", "name": "cadical"},
        "checker_results": [
            {"checker": "cadical",   "result": "passed", "formal_verified": False},
            {"checker": "cake_lpr",  "result": "passed", "formal_verified": True},
            {"checker": "isabelle",  "result": "passed", "formal_verified": True},
        ],
        "formal_targets": [
            {"system": "other",    "status": "proved"},
            {"system": "isabelle", "status": "proved"},
        ],
        "obligations": [
            {"obligation_id": "o1", "kind": "formal_theorem", "status": "passed"},
        ],
        "assumptions": [],
        "flags": [],
        "metadata": {},
    }
    assert grade(claim) == EvidenceClass.E8_CROSS_VERIFIED


def test_without_cake_lpr_formal_verified_grades_e6():
    """Without a formal_verified=True checker, we cap at E6 (SAT family only)."""
    claim = {
        "source": {"kind": "benchmark", "name": "cadical"},
        "checker_results": [
            {"checker": "cadical",  "result": "passed", "formal_verified": False},
            {"checker": "lrat-trim","result": "passed", "formal_verified": False},
        ],
        "formal_targets": [],
        "obligations": [{"obligation_id": "o1", "kind": "benchmark_correctness", "status": "passed"}],
        "assumptions": [],
        "flags": [],
        "metadata": {},
    }
    assert grade(claim) == EvidenceClass.E6_SYMBOLICALLY_SUPPORTED


# ---------------------------------------------------------------------------
# claim_from_sat_result structure
# ---------------------------------------------------------------------------

def test_claim_has_correct_type(tmp_path):
    cnf = tmp_path / "test.cnf"
    cnf.write_text("p cnf 1 2\n1 0\n-1 0\n")
    res = _mock_unsat_result(cnf)
    claim_dict, _ = claim_from_sat_result(res, cnf_path=cnf, run_id="test_run_002")
    assert claim_dict["claim_type"] == "unsat_certificate"


def test_claim_has_four_checker_results(tmp_path):
    cnf = tmp_path / "test.cnf"
    cnf.write_text("p cnf 1 2\n1 0\n-1 0\n")
    res = _mock_unsat_result(cnf)
    claim_dict, _ = claim_from_sat_result(res, cnf_path=cnf, run_id="test_run_003")
    checkers = [r["checker"] for r in claim_dict["checker_results"]]
    assert set(checkers) == {"cadical", "drat-trim", "lrat-trim", "cake_lpr"}


def test_cake_lpr_formal_verified_true(tmp_path):
    cnf = tmp_path / "test.cnf"
    cnf.write_text("p cnf 1 2\n1 0\n-1 0\n")
    res = _mock_unsat_result(cnf)
    claim_dict, _ = claim_from_sat_result(res, cnf_path=cnf, run_id="test_run_004")
    cake = next(r for r in claim_dict["checker_results"] if r["checker"] == "cake_lpr")
    assert cake["formal_verified"] is True
    assert cake["result"] == "passed"


def test_formal_target_is_proved(tmp_path):
    cnf = tmp_path / "test.cnf"
    cnf.write_text("p cnf 1 2\n1 0\n-1 0\n")
    res = _mock_unsat_result(cnf)
    claim_dict, _ = claim_from_sat_result(res, cnf_path=cnf, run_id="test_run_005")
    assert len(claim_dict["formal_targets"]) == 1
    assert claim_dict["formal_targets"][0]["status"] == "proved"
    assert claim_dict["formal_targets"][0]["system"] == "other"


def test_claim_validates_against_schema(tmp_path):
    cnf = tmp_path / "test.cnf"
    cnf.write_text("p cnf 1 2\n1 0\n-1 0\n")
    res = _mock_unsat_result(cnf)
    claim_dict, _ = claim_from_sat_result(res, cnf_path=cnf, run_id="test_run_006")
    errors = validate_claim(claim_dict)
    assert errors == [], f"Schema validation errors: {errors}"


def test_runpack_has_four_commands(tmp_path):
    cnf = tmp_path / "test.cnf"
    cnf.write_text("p cnf 1 2\n1 0\n-1 0\n")
    res = _mock_unsat_result(cnf)
    _, runpack = claim_from_sat_result(res, cnf_path=cnf, run_id="test_run_007")
    d = runpack.to_dict()
    assert len(d["commands"]) == 4  # cadical + drat-trim + lrat-trim + cake_lpr


def test_runpack_verification_result_passed(tmp_path):
    cnf = tmp_path / "test.cnf"
    cnf.write_text("p cnf 1 2\n1 0\n-1 0\n")
    res = _mock_unsat_result(cnf)
    _, runpack = claim_from_sat_result(res, cnf_path=cnf, run_id="test_run_008")
    assert runpack.verification_result == "passed"


def test_runpack_has_manifest_hash(tmp_path):
    cnf = tmp_path / "test.cnf"
    cnf.write_text("p cnf 1 2\n1 0\n-1 0\n")
    res = _mock_unsat_result(cnf)
    _, runpack = claim_from_sat_result(res, cnf_path=cnf, run_id="test_run_009")
    h = runpack.manifest_hash
    assert isinstance(h, str) and len(h) == 64


def test_raises_on_non_unsat_result(tmp_path):
    cnf = tmp_path / "test.cnf"
    cnf.write_text("p cnf 1 1\n1 0\n")
    res = SatExecResult(
        result="SAT", stdout="s SATISFIABLE\n", stderr="",
        commandline=[], drat_relpath=None, lrat_relpath=None,
        check_drat=None, check_lrat=None, check_cake_lpr=None,
    )
    with pytest.raises(ValueError, match="UNSAT"):
        claim_from_sat_result(res, cnf_path=cnf, run_id="test_run_010")


# ---------------------------------------------------------------------------
# Example JSON validates against schema
# ---------------------------------------------------------------------------

def test_example_unsat_000001_validates():
    path = ROOT / "protocols" / "claim_protocol" / "examples" / "unsat_000001.json"
    assert path.exists()
    errors = validate_claim(json.loads(path.read_text()))
    assert errors == [], f"unsat_000001.json schema errors: {errors}"


def test_example_unsat_000001_grades_e7():
    """unsat_000001.json has one formal anchor (cake_lpr) → E7_FORMALLY_VERIFIED."""
    path = ROOT / "protocols" / "claim_protocol" / "examples" / "unsat_000001.json"
    claim = json.loads(path.read_text())
    assert grade(claim) == EvidenceClass.E7_FORMALLY_VERIFIED
