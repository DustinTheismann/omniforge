"""
Tests for Tier 8.1 — Coq / Coquelicot proof emitter.

Run with:  python -m pytest tests/test_coq_emitter.py -v
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest

from cross_prover.coq_emitter import (
    CoqProof,
    emit_coq,
    emit_all,
    emit_coq_from_antideriv,
    write_coq_file,
    _lean_to_coq_expr,
)


# ---------------------------------------------------------------------------
# Expression translator
# ---------------------------------------------------------------------------

def test_real_log_becomes_ln():
    assert _lean_to_coq_expr("Real.log x") == "ln x"


def test_real_arctan_becomes_atan():
    assert _lean_to_coq_expr("Real.arctan x") == "atan x"


def test_not_equal_symbol():
    assert _lean_to_coq_expr("x ≠ 0") == "x <> 0"


def test_real_type_becomes_r():
    assert _lean_to_coq_expr("(x : ℝ)") == "(x : R)"


def test_rename_bound_replaces_t():
    result = _lean_to_coq_expr("Real.log t", rename_bound=True)
    assert result == "ln x"


def test_rename_bound_does_not_corrupt_atan():
    result = _lean_to_coq_expr("Real.arctan (t + 1)", rename_bound=True)
    assert "atan (x + 1)" == result
    # 't' in 'atan' must not be replaced
    assert "aXan" not in result


def test_rename_bound_does_not_corrupt_sqrt():
    result = _lean_to_coq_expr("Real.sqrt t", rename_bound=True)
    assert "sqrt x" == result


# ---------------------------------------------------------------------------
# CoqProof dataclass
# ---------------------------------------------------------------------------

def test_full_text_contains_theorem_and_proof():
    p = emit_coq("pf.integral.bronstein_007")
    assert "Theorem coq_autodischarge_007" in p.full_text
    assert "Proof." in p.full_text
    assert "Qed." in p.full_text


# ---------------------------------------------------------------------------
# emit_coq — individual claims
# ---------------------------------------------------------------------------

def test_emit_001_class_a_no_hyps():
    p = emit_coq("pf.integral.bronstein_001")
    assert p.hypotheses == []
    assert p.antideriv_shape == "COMPLEX_SUM"


def test_emit_003_log_pos_quad():
    p = emit_coq("pf.integral.bronstein_003")
    assert p.antideriv_shape == "LOG_POS_QUAD"
    assert "ln (x ^ 2 + 1)" in p.statement


def test_emit_007_log_simple_has_hypothesis():
    p = emit_coq("pf.integral.bronstein_007")
    assert p.antideriv_shape == "LOG_SIMPLE"
    assert len(p.hypotheses) == 1
    assert "hx : x <> 0" in p.hypotheses[0]


def test_emit_007_statement_uses_x_not_t():
    p = emit_coq("pf.integral.bronstein_007")
    # bound variable must be x, not t
    assert "ln x" in p.statement
    assert "ln t" not in p.statement


def test_emit_007_proof_uses_exact_hx():
    p = emit_coq("pf.integral.bronstein_007")
    assert "exact hx" in p.proof_script


def test_emit_008_log_neg_quad():
    p = emit_coq("pf.integral.bronstein_008")
    assert p.antideriv_shape == "LOG_NEG_QUAD"
    assert len(p.hypotheses) == 1


def test_emit_005_class_c_two_hypotheses():
    p = emit_coq("pf.integral.bronstein_005")
    assert p.antideriv_shape == "LOG_PFD"
    assert len(p.hypotheses) == 2
    assert "exact hx" in p.proof_script
    assert "exact hx1" in p.proof_script


def test_emit_009_class_d_three_hypotheses():
    p = emit_coq("pf.integral.bronstein_009")
    assert p.antideriv_shape == "LOG_PFD"
    assert len(p.hypotheses) == 3
    assert "exact hx2" in p.proof_script


def test_emit_004_arctan_pow():
    p = emit_coq("pf.integral.bronstein_004")
    assert p.antideriv_shape == "ARCTAN_POW"
    assert "atan" in p.statement


def test_emit_006_arctan_linear():
    p = emit_coq("pf.integral.bronstein_006")
    assert p.antideriv_shape == "ARCTAN_LINEAR"
    assert "atan" in p.statement


def test_emit_coq_theorem_name_correct():
    for suffix in ["001", "003", "004", "005", "006", "007", "008", "009"]:
        p = emit_coq(f"pf.integral.bronstein_{suffix}")
        assert p.theorem_name == f"coq_autodischarge_{suffix}"


# ---------------------------------------------------------------------------
# emit_all
# ---------------------------------------------------------------------------

def test_emit_all_returns_eight():
    proofs = emit_all()
    assert len(proofs) == 8


def test_emit_all_distinct_names():
    names = [p.theorem_name for p in emit_all()]
    assert len(set(names)) == 8


def test_emit_all_class_distribution():
    proofs = emit_all()
    shape_counts: dict[str, int] = {}
    for p in proofs:
        shape_counts[p.antideriv_shape] = shape_counts.get(p.antideriv_shape, 0) + 1
    # Must have at least one LOG_SIMPLE, one LOG_PFD
    assert shape_counts.get("LOG_SIMPLE", 0) >= 1
    assert shape_counts.get("LOG_PFD", 0) >= 1


def test_emit_all_every_proof_has_qed():
    for p in emit_all():
        assert "Qed." in p.proof_script, f"{p.theorem_name} missing Qed."


def test_emit_all_no_t_in_bodies():
    """Lambda bodies must use x, not the Lean-internal t."""
    for p in emit_all():
        # The body inside fun x => ... should not contain standalone 't'
        body_match = re.search(r"fun x => (.+?)\)", p.statement)
        if body_match:
            body = body_match.group(1)
            assert not re.search(r"\bt\b", body), (
                f"{p.theorem_name} still contains bare `t` in body: {body}"
            )


# ---------------------------------------------------------------------------
# emit_coq_from_antideriv
# ---------------------------------------------------------------------------

def test_emit_from_antideriv_simple():
    p = emit_coq_from_antideriv(
        "log(x)",
        "1/x",
        theorem_name="test_log",
        claim_id="test.claim",
    )
    assert p.theorem_name == "test_log"
    assert p.antideriv_shape == "LOG_SIMPLE"


def test_emit_from_antideriv_quad():
    p = emit_coq_from_antideriv(
        "log(x^2+1)/2",
        "x/(x^2+1)",
        theorem_name="test_quad",
        claim_id="test.quad",
    )
    assert p.antideriv_shape == "LOG_POS_QUAD"
    assert p.hypotheses == []


# ---------------------------------------------------------------------------
# write_coq_file
# ---------------------------------------------------------------------------

def test_write_coq_file_creates_file():
    with tempfile.TemporaryDirectory() as td:
        out = write_coq_file(str(Path(td) / "out.v"))
        assert out.exists()


def test_write_coq_file_has_header():
    with tempfile.TemporaryDirectory() as td:
        out = write_coq_file(str(Path(td) / "out.v"))
        text = out.read_text()
        assert "Require Import Reals Coquelicot" in text
        assert "Open Scope R_scope" in text


def test_write_coq_file_contains_all_theorems():
    with tempfile.TemporaryDirectory() as td:
        out = write_coq_file(str(Path(td) / "out.v"))
        text = out.read_text()
        for suffix in ["001", "003", "004", "005", "006", "007", "008", "009"]:
            assert f"coq_autodischarge_{suffix}" in text


def test_write_coq_file_has_claim_comments():
    with tempfile.TemporaryDirectory() as td:
        out = write_coq_file(str(Path(td) / "out.v"))
        text = out.read_text()
        assert "(* Claim: pf.integral.bronstein_007" in text


def test_write_coq_file_cross_prover_header():
    with tempfile.TemporaryDirectory() as td:
        out = write_coq_file(str(Path(td) / "out.v"))
        text = out.read_text()
        assert "cross-prover certificate" in text
