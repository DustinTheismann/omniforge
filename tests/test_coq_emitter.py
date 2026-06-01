"""
Tests for Tier 8.1 — Coq / Coquelicot proof reflector.

The emitter now reflects the kernel-checked committed file RischCoqDischarge.v
(verified by coqc + Coquelicot in .github/workflows/coq.yml), so "emitted ==
verified" holds by construction.  Where coqc is available, one test actually
runs the kernel.

Run with:  python -m pytest tests/test_coq_emitter.py -v
"""
from __future__ import annotations

import shutil
import subprocess
import os
from pathlib import Path

import pytest

from cross_prover.coq_emitter import (
    CoqProof,
    emit_coq,
    emit_all,
    write_coq_file,
    COQ_SOURCE,
)


# ---------------------------------------------------------------------------
# Parser reflects the committed file
# ---------------------------------------------------------------------------

def test_emit_all_returns_eight():
    assert len(emit_all()) == 8


def test_emit_all_distinct_names():
    names = [p.theorem_name for p in emit_all()]
    assert len(set(names)) == 8


def test_every_proof_is_coqproof():
    for p in emit_all():
        assert isinstance(p, CoqProof)


def test_full_text_has_theorem_and_qed():
    p = emit_coq("pf.integral.bronstein_007")
    assert "Theorem coq_autodischarge_007" in p.full_text
    assert "Qed." in p.full_text


def test_emit_coq_theorem_names():
    for suffix in ["001", "003", "004", "005", "006", "007", "008", "009"]:
        p = emit_coq(f"pf.integral.bronstein_{suffix}")
        assert p.theorem_name == f"coq_autodischarge_{suffix}"


def test_emit_coq_unknown_claim_raises():
    with pytest.raises(KeyError):
        emit_coq("pf.integral.nonexistent_999")


# ---------------------------------------------------------------------------
# Branch-cut hypotheses: Coq's ln needs 0<arg, NOT arg<>0
# ---------------------------------------------------------------------------

def test_007_branch_cut_positivity_hypothesis():
    p = emit_coq("pf.integral.bronstein_007")
    assert p.is_branch_cut is True
    assert any("0 < x" in h for h in p.hypotheses)
    # The wrong hypothesis must NOT be present.
    assert not any("<> 0" in h for h in p.hypotheses)


def test_009_three_positivity_hypotheses():
    p = emit_coq("pf.integral.bronstein_009")
    assert len(p.hypotheses) == 3
    assert all("0 <" in h for h in p.hypotheses)


def test_005_two_positivity_hypotheses():
    p = emit_coq("pf.integral.bronstein_005")
    assert len(p.hypotheses) == 2
    assert all("0 <" in h for h in p.hypotheses)


def test_008_neg_quad_positivity():
    p = emit_coq("pf.integral.bronstein_008")
    assert p.is_branch_cut is True
    assert any("0 < x ^ 2 - 4" in h for h in p.hypotheses)


# ---------------------------------------------------------------------------
# Positive-argument cases are unconditional (caveat-free in both kernels)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("suffix", ["001", "003", "004", "006"])
def test_positive_argument_cases_unconditional(suffix):
    p = emit_coq(f"pf.integral.bronstein_{suffix}")
    assert p.hypotheses == []
    assert p.is_branch_cut is False


def test_003_statement_shape():
    p = emit_coq("pf.integral.bronstein_003")
    assert "ln (x ^ 2 + 1) / 2" in p.statement
    assert "is_derive" in p.statement


def test_004_arctan():
    p = emit_coq("pf.integral.bronstein_004")
    assert "atan" in p.statement


# ---------------------------------------------------------------------------
# write_coq_file reflects the committed file verbatim
# ---------------------------------------------------------------------------

def test_write_coq_file_no_arg_returns_committed():
    out = write_coq_file()
    assert out == COQ_SOURCE
    assert out.exists()


def test_write_coq_file_copies_verbatim(tmp_path):
    out = write_coq_file(str(tmp_path / "out.v"))
    assert out.read_text() == COQ_SOURCE.read_text()


def test_committed_file_requires_coquelicot():
    text = COQ_SOURCE.read_text()
    assert "Require Import Reals Coquelicot.Coquelicot" in text
    assert "is_derive" in text


# ---------------------------------------------------------------------------
# The honest kernel check: actually run coqc when it is available.
# ---------------------------------------------------------------------------

def test_coqc_accepts_committed_file():
    if shutil.which("coqc") is None:
        pytest.skip("coqc not installed; .github/workflows/coq.yml checks this in CI")
    env = dict(os.environ)
    contrib = "/usr/lib/ocaml/coq/user-contrib"
    if Path(contrib).exists():
        env["COQPATH"] = contrib + (":" + env["COQPATH"] if env.get("COQPATH") else "")
    proc = subprocess.run(
        ["coqc", COQ_SOURCE.name],
        cwd=str(COQ_SOURCE.parent),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    # Clean the .vo so the test leaves no build artifact.
    vo = COQ_SOURCE.with_suffix(".vo")
    if vo.exists():
        vo.unlink()
    for junk in COQ_SOURCE.parent.glob("*.glob"):
        junk.unlink()
    nra = COQ_SOURCE.parent / ".nra.cache"
    if nra.exists():
        nra.unlink()
    assert proc.returncode == 0, f"coqc rejected the file:\n{proc.stderr}"
