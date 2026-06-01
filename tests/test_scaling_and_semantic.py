"""
Tests for Tier 1.4 (scaling theorem) and Tier 1.5 (semantic audit filter).

Run with:  python -m pytest tests/test_scaling_and_semantic.py -v
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from fricas_bridge.scaling_theorem import (
    GeneralPFDTheorem,
    ConcreteInstance,
    build_general_theorem,
    build_concrete_instances,
    write_pfd_lean_file,
)
from fricas_bridge.semantic_filter import (
    SemanticIssue,
    SemanticResult,
    semantic_filter,
    filter_corpus,
)


# ---------------------------------------------------------------------------
# Scaling theorem — Tier 1.4
# ---------------------------------------------------------------------------

def test_build_general_theorem_returns_dataclass():
    g = build_general_theorem()
    assert isinstance(g, GeneralPFDTheorem)


def test_general_theorem_has_lean_syntax():
    g = build_general_theorem()
    assert "HasDerivAt" in g.statement
    assert "partial_fraction_hasDerivAt" in g.statement
    assert "Fin n" in g.statement


def test_general_theorem_has_proof():
    g = build_general_theorem()
    assert ":= by" in g.statement
    assert "HasDerivAt.sum" in g.statement


def test_build_concrete_instances_count():
    instances = build_concrete_instances(max_poles=4)
    assert len(instances) == 4


def test_concrete_instances_are_dataclass():
    for inst in build_concrete_instances():
        assert isinstance(inst, ConcreteInstance)


def test_concrete_1_pole():
    [inst] = build_concrete_instances(max_poles=1)
    assert inst.n_poles == 1
    assert "HasDerivAt" in inst.lean_statement
    assert "c1" in inst.lean_statement


def test_concrete_2_poles():
    instances = build_concrete_instances(max_poles=2)
    inst = instances[1]
    assert inst.n_poles == 2
    assert "b" in inst.lean_statement
    assert "c2" in inst.lean_statement


def test_concrete_proof_scripts_non_empty():
    for inst in build_concrete_instances():
        assert inst.proof_script.strip() != ""


def test_write_pfd_lean_file():
    with tempfile.TemporaryDirectory() as td:
        out = write_pfd_lean_file(str(Path(td) / "pfd.lean"))
        assert out.exists()
        text = out.read_text()
        assert "partial_fraction_hasDerivAt" in text
        assert "pfd_1_poles" in text
        assert "pfd_4_poles" in text
        assert "import Mathlib" in text


# ---------------------------------------------------------------------------
# Semantic filter — Tier 1.5
# ---------------------------------------------------------------------------

def test_semantic_filter_passes():
    r = semantic_filter("1/x", "log(x)")
    assert r.ok is True
    assert r.issue == SemanticIssue.PASSES.value


def test_semantic_filter_trivial_zero():
    r = semantic_filter("sin(x)", "0")
    assert r.issue == SemanticIssue.TRIVIAL_ZERO.value
    assert r.ok is False


def test_semantic_filter_missing_log():
    r = semantic_filter("1/x", "x")
    assert r.issue == SemanticIssue.MISSING_LOG.value
    assert r.ok is False


def test_semantic_filter_missing_atan():
    r = semantic_filter("1/(x^2+1)", "x")
    assert r.issue == SemanticIssue.MISSING_ATAN.value
    assert r.ok is False


def test_semantic_filter_log_present():
    r = semantic_filter("1/x", "log(x)")
    assert r.ok is True


def test_semantic_filter_atan_present():
    r = semantic_filter("1/(x^2+1)", "atan(x)")
    assert r.ok is True


def test_semantic_filter_result_fields():
    r = semantic_filter("1/x", "log(x)")
    assert r.integrand == "1/x"
    assert r.antiderivative == "log(x)"
    assert r.var == "x"


def test_filter_corpus_returns_list():
    entries = [
        {"integrand": "1/x", "antiderivative": "log(x)", "var": "x"},
        {"integrand": "sin(x)", "antiderivative": "0", "var": "x"},
    ]
    results = filter_corpus(entries)
    assert len(results) == 2


def test_filter_corpus_correct_verdicts():
    entries = [
        {"integrand": "1/x", "antiderivative": "log(x)", "var": "x"},
        {"integrand": "sin(x)", "antiderivative": "0", "var": "x"},
    ]
    results = filter_corpus(entries)
    assert results[0].ok is True
    assert results[1].ok is False


def test_semantic_issue_values():
    assert SemanticIssue.PASSES.value == "passes"
    assert SemanticIssue.TRIVIAL_ZERO.value == "trivial_zero"
    assert SemanticIssue.MISSING_LOG.value == "missing_log"
    assert SemanticIssue.MISSING_ATAN.value == "missing_atan"
