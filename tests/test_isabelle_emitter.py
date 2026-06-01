"""
Tests for Tier 8.3 — Isabelle/HOL proof emitter.

Run with:  python -m pytest tests/test_isabelle_emitter.py -v
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from cross_prover.isabelle_emitter import (
    IsabelleProof,
    emit_isabelle,
    emit_all_isabelle,
    write_isabelle_file,
)


def test_emit_isabelle_returns_dataclass():
    p = emit_isabelle("pf.integral.bronstein_007")
    assert isinstance(p, IsabelleProof)


def test_emit_007_has_hypothesis():
    p = emit_isabelle("pf.integral.bronstein_007")
    assert len(p.hypotheses) == 1
    # Isabelle/HOL ln is principal-branch (DERIV_ln needs 0<x), not x≠0.
    assert "x > 0" in p.hypotheses[0]
    assert "≠" not in p.hypotheses[0]


def test_emit_007_statement_has_ln():
    p = emit_isabelle("pf.integral.bronstein_007")
    assert "ln x" in p.statement


def test_emit_007_uses_has_real_derivative():
    p = emit_isabelle("pf.integral.bronstein_007")
    assert "has_real_derivative" in p.statement


def test_emit_007_assumes_keyword():
    p = emit_isabelle("pf.integral.bronstein_007")
    assert "assumes" in p.statement


def test_emit_009_three_assumes():
    p = emit_isabelle("pf.integral.bronstein_009")
    assert p.statement.count("assumes") == 3


def test_emit_003_no_assumes():
    p = emit_isabelle("pf.integral.bronstein_003")
    assert "assumes" not in p.statement


def test_emit_all_returns_eight():
    assert len(emit_all_isabelle()) == 8


def test_emit_all_every_has_shows():
    for p in emit_all_isabelle():
        assert "shows" in p.statement, f"{p.theorem_name} missing 'shows'"


def test_emit_all_no_t_in_bodies():
    import re
    for p in emit_all_isabelle():
        body_m = re.search(r"\\<lambda>x\.\s*(.+?)\)", p.statement)
        if body_m:
            body = body_m.group(1)
            assert not re.search(r"\bt\b", body), f"{p.theorem_name}: bare `t` in body"


def test_emit_all_proof_script_non_empty():
    for p in emit_all_isabelle():
        assert p.proof_script.strip() != ""


def test_write_isabelle_file_creates_theory():
    with tempfile.TemporaryDirectory() as td:
        out = write_isabelle_file(str(Path(td) / "test.thy"))
        assert out.exists()
        text = out.read_text()
        assert "theory RischIsabelleDischarge" in text
        assert "imports" in text
        assert "end" in text


def test_write_isabelle_file_contains_all_lemmas():
    with tempfile.TemporaryDirectory() as td:
        out = write_isabelle_file(str(Path(td) / "test.thy"))
        text = out.read_text()
        for suffix in ["001", "003", "004", "005", "006", "007", "008", "009"]:
            assert f"isabelle_autodischarge_{suffix}" in text


def test_isabelle_output_marked_not_kernel_checked():
    """The Isabelle theory must NOT claim to be verified — there is no Isabelle
    kernel in CI, so over-claiming would be dishonest."""
    with tempfile.TemporaryDirectory() as td:
        out = write_isabelle_file(str(Path(td) / "test.thy"))
        text = out.read_text()
        assert "NOT KERNEL-CHECKED" in text


def test_log_cases_use_positivity_not_nonzero():
    """All log-bearing claims assume 0<arg (principal branch), never arg≠0."""
    for suffix in ["005", "007", "008", "009"]:
        p = emit_isabelle(f"pf.integral.bronstein_{suffix}")
        for h in p.hypotheses:
            assert ">" in h and "≠" not in h, f"{p.theorem_name}: {h!r}"
