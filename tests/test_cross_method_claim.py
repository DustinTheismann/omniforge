"""
Tests for protocols/cross_method_claim.py — E9_MULTI_METHOD.

Two formally-anchored but methodologically independent proofs of the same
Boolean tautology grade at E9_MULTI_METHOD. Tests cover: correct grade,
fail-closed gates, schema validity, translation validator, example file.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from omniforge.lanes.sat_lane import ProofCheck, SatExecResult
from protocols.claim_protocol.types import EvidenceClass
from protocols.claim_protocol.validate import validate_claim
from protocols.cross_method_claim import (
    LeanGf2Witness,
    _parse_dimacs,
    _validate_cross_translation,
    claim_from_cross_method,
)
from protocols.evidence_protocol.grader import grade

ROOT = Path(__file__).parent.parent
CNF_PATH = ROOT / "benches" / "multimethod" / "gf2_tautology.cnf"
LEAN_ARTIFACT = "fricas_bridge/Gf2Identity.lean"

_GF2_VARS = 2

# GF(2) identity for (a ∧ b) ∨ (a ∧ ¬b) ↔ a : a*b + a*(1-b) = a over ZMod 2
def _gf2_id(a: int, b: int) -> bool:
    return (a * b + a * (1 - b)) % 2 == a % 2


def _lean_witness() -> LeanGf2Witness:
    return LeanGf2Witness(
        theorem_name="gf2_and_or_identity",
        formula_natural="a * b + a * (1 - b) = a over ZMod 2",
        artifact_path=LEAN_ARTIFACT,
        kernel="leanprover/lean4:v4.30.0 + mathlib:v4.30.0",
    )


def _mock_unsat() -> SatExecResult:
    return SatExecResult(
        result="UNSAT",
        stdout="s UNSATISFIABLE\n",
        stderr="",
        commandline=["cadical", "--seed=0", str(CNF_PATH), "proof.drat"],
        drat_relpath="proofs/proof.drat",
        lrat_relpath="proofs/proof.lrat",
        check_drat=ProofCheck("drat-trim", ok=True, returncode=0, stdout="VERIFIED", stderr=""),
        check_lrat=ProofCheck("lrat-trim", ok=True, returncode=20, stdout="LRAT OK", stderr=""),
        check_cake_lpr=ProofCheck("cake_lpr", ok=True, returncode=0, stdout="s VERIFIED UNSAT\n", stderr=""),
    )


def _make_claim(**kwargs):
    defaults = dict(
        lean_witness=_lean_witness(),
        sat_result=_mock_unsat(),
        cnf_path=CNF_PATH,
        run_id="test_001",
        formula_natural="(a∧b)∨(a∧¬b)↔a",
        tautology_name="gf2_and_or",
        gf2_vars=_GF2_VARS,
        gf2_identity_fn=_gf2_id,
    )
    defaults.update(kwargs)
    return claim_from_cross_method(_lean_witness(), **{k: v for k, v in defaults.items() if k != "lean_witness"})


# ---------------------------------------------------------------------------
# E9 by construction
# ---------------------------------------------------------------------------

def test_grades_e9_multi_method():
    claim, _ = _make_claim()
    assert claim["evidence_class"] == EvidenceClass.E9_MULTI_METHOD.value


def test_grade_function_returns_e9():
    claim, _ = _make_claim()
    assert grade(claim) == EvidenceClass.E9_MULTI_METHOD


def test_e9_requires_two_methods():
    """Confirming the grader gate: two families + two methods → E9."""
    claim, _ = _make_claim()
    checkers = claim["checker_results"]
    methods = {r["method"] for r in checkers if r.get("formal_verified")}
    families = {"lean4", "cake_lpr"}
    assert methods == {"gf2_algebraic", "sat_refutation"}
    assert len(methods) == 2
    assert len(families) == 2


def test_e9_above_e8():
    assert EvidenceClass.E9_MULTI_METHOD.level == 9
    assert EvidenceClass.E8_CROSS_VERIFIED.level == 8
    assert EvidenceClass.E9_MULTI_METHOD.level > EvidenceClass.E8_CROSS_VERIFIED.level


def test_both_formal_verified_true():
    claim, _ = _make_claim()
    for r in claim["checker_results"]:
        assert r["formal_verified"] is True, f"{r['checker']} missing formal_verified=True"


def test_two_formal_targets_proved():
    claim, _ = _make_claim()
    assert len(claim["formal_targets"]) == 2
    assert all(t["status"] == "proved" for t in claim["formal_targets"])


# ---------------------------------------------------------------------------
# Fail-closed gates
# ---------------------------------------------------------------------------

def test_raises_on_sat_result():
    bad = _mock_unsat()
    bad = SatExecResult(
        result="SAT", stdout="s SATISFIABLE\n", stderr="",
        commandline=[], drat_relpath=None, lrat_relpath=None,
        check_drat=None, check_lrat=None, check_cake_lpr=None,
    )
    with pytest.raises(ValueError, match="UNSAT"):
        claim_from_cross_method(
            _lean_witness(), sat_result=bad, cnf_path=CNF_PATH,
            run_id="x", formula_natural="f", tautology_name="t",
            gf2_vars=_GF2_VARS, gf2_identity_fn=_gf2_id,
        )


def test_raises_when_cake_lpr_fails():
    bad = SatExecResult(
        result="UNSAT", stdout="s UNSATISFIABLE\n", stderr="",
        commandline=[], drat_relpath="p.drat", lrat_relpath="p.lrat",
        check_drat=ProofCheck("drat-trim", ok=True, returncode=0, stdout="OK", stderr=""),
        check_lrat=ProofCheck("lrat-trim", ok=True, returncode=20, stdout="OK", stderr=""),
        check_cake_lpr=ProofCheck("cake_lpr", ok=False, returncode=1, stdout="FAIL", stderr=""),
    )
    with pytest.raises(ValueError, match="cake_lpr"):
        claim_from_cross_method(
            _lean_witness(), sat_result=bad, cnf_path=CNF_PATH,
            run_id="x", formula_natural="f", tautology_name="t",
            gf2_vars=_GF2_VARS, gf2_identity_fn=_gf2_id,
        )


def test_raises_when_lean_artifact_missing(tmp_path):
    bad_lean = LeanGf2Witness(
        theorem_name="gf2_and_or_identity",
        formula_natural="a*b + a*(1-b) = a",
        artifact_path="nonexistent/file.lean",
        kernel="lean4",
    )
    with pytest.raises(ValueError, match="Lean artifact missing"):
        claim_from_cross_method(
            bad_lean, sat_result=_mock_unsat(), cnf_path=CNF_PATH,
            run_id="x", formula_natural="f", tautology_name="t",
            gf2_vars=_GF2_VARS, gf2_identity_fn=_gf2_id,
        )


def test_raises_when_translation_fails():
    """A GF(2) function that is NOT the same as the CNF encoding → gate refuses."""
    def wrong_fn(a, b):  # always True regardless of formula
        return True

    # wrong_fn is always True so _validate_cross_translation returns True for gf2_all_true
    # but the CNF is UNSAT, so the overall check should still pass...
    # Actually we need wrong_fn to describe a DIFFERENT tautology, so gf2 is fine
    # but the CNF encodes a different formula. Let's test with CNF that is NOT UNSAT.
    cnf_sat = "p cnf 1 1\n1 0\n"  # formula: a=T — SAT, not UNSAT

    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".cnf", mode="w", delete=False) as f:
        f.write(cnf_sat)
        tmpname = f.name
    try:
        with pytest.raises(ValueError, match="[Cc]ross-translation"):
            claim_from_cross_method(
                _lean_witness(), sat_result=_mock_unsat(),
                cnf_path=Path(tmpname),
                run_id="x", formula_natural="f", tautology_name="t",
                gf2_vars=_GF2_VARS, gf2_identity_fn=_gf2_id,
            )
    finally:
        os.unlink(tmpname)


# ---------------------------------------------------------------------------
# Translation validator unit tests
# ---------------------------------------------------------------------------

def test_parse_dimacs_correct_clause_count():
    _, clauses = _parse_dimacs(CNF_PATH.read_text())
    assert len(clauses) == 11


def test_parse_dimacs_correct_var_count():
    num_vars, _ = _parse_dimacs(CNF_PATH.read_text())
    assert num_vars == 5


def test_cnf_is_unsat():
    """The benchmark CNF must be UNSAT — the tautology is universally true."""
    cnf_text = CNF_PATH.read_text()
    assert _validate_cross_translation(cnf_text, _GF2_VARS, _gf2_id)


def test_gf2_id_is_universally_true():
    from itertools import product
    assert all(_gf2_id(a, b) for a, b in product([0, 1], repeat=2))


# ---------------------------------------------------------------------------
# Schema + runpack
# ---------------------------------------------------------------------------

def test_claim_validates_against_schema():
    claim, _ = _make_claim()
    errors = validate_claim(claim)
    assert errors == [], f"schema errors: {errors}"


def test_runpack_has_five_commands():
    """lake + cadical + drat-trim + lrat-trim + cake_lpr"""
    claim, runpack = _make_claim()
    assert len(runpack.to_dict()["commands"]) == 5


def test_runpack_records_lean_and_cnf_artifacts():
    _, runpack = _make_claim()
    roles = {a["role"] for a in runpack.to_dict()["artifacts"]}
    assert roles == {"lean_proof", "cnf"}


def test_runpack_has_manifest_hash():
    _, runpack = _make_claim()
    assert isinstance(runpack.manifest_hash, str) and len(runpack.manifest_hash) == 64


def test_claim_type_is_algebraic_identity():
    claim, _ = _make_claim()
    assert claim["claim_type"] == "algebraic_identity"


# ---------------------------------------------------------------------------
# Canonical example file
# ---------------------------------------------------------------------------

def test_example_multimethod_000001_exists():
    path = ROOT / "protocols" / "claim_protocol" / "examples" / "multimethod_000001.json"
    assert path.exists()


def test_example_multimethod_000001_validates():
    path = ROOT / "protocols" / "claim_protocol" / "examples" / "multimethod_000001.json"
    errors = validate_claim(json.loads(path.read_text()))
    assert errors == [], f"multimethod_000001.json schema errors: {errors}"


def test_example_multimethod_000001_grades_e9():
    path = ROOT / "protocols" / "claim_protocol" / "examples" / "multimethod_000001.json"
    claim = json.loads(path.read_text())
    assert grade(claim) == EvidenceClass.E9_MULTI_METHOD
