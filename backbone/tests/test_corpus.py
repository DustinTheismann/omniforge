"""
Tests for corpus/bronstein.jsonl schema validity and internal consistency.

Run with:  python -m pytest backbone/tests/test_corpus.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

CORPUS_PATH = Path(__file__).parent.parent / "corpus" / "bronstein.jsonl"
SCHEMA_PATH = Path(__file__).parent.parent / "cas_protocol" / "schema.json"


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


@pytest.fixture(scope="module")
def entries() -> list[dict]:
    lines = [l for l in CORPUS_PATH.read_text().splitlines() if l.strip()]
    return [json.loads(line) for line in lines]


# ---------------------------------------------------------------------------
# Basic integrity
# ---------------------------------------------------------------------------

def test_corpus_is_nonempty(entries):
    assert len(entries) >= 24, f"Expected ≥24 entries, got {len(entries)}"


def test_all_ids_unique(entries):
    ids = [e["id"] for e in entries]
    assert len(ids) == len(set(ids)), "Duplicate IDs in corpus"


def test_all_have_required_fields(entries):
    required = {"id", "source", "integrand", "antiderivative", "variable", "discrepancy_class"}
    for entry in entries:
        missing = required - entry.keys()
        assert not missing, f"Entry {entry.get('id')} missing: {missing}"


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def test_each_entry_validates_against_schema(schema, entries):
    validator = jsonschema.Draft202012Validator(schema)
    for entry in entries:
        errors = list(validator.iter_errors(entry))
        assert not errors, (
            f"Entry {entry.get('id')} schema errors:\n"
            + "\n".join(str(e) for e in errors)
        )


# ---------------------------------------------------------------------------
# Domain class invariants
# ---------------------------------------------------------------------------

def test_class_a_has_no_hypotheses(entries):
    for e in entries:
        if e["discrepancy_class"] == "A":
            hyps = e.get("required_hypotheses", [])
            assert len(hyps) == 0, (
                f"Class A entry {e['id']} should have 0 hypotheses, got {len(hyps)}"
            )


def test_class_b_has_exactly_one_hypothesis(entries):
    for e in entries:
        if e["discrepancy_class"] == "B":
            hyps = e.get("required_hypotheses", [])
            assert len(hyps) == 1, (
                f"Class B entry {e['id']} should have 1 hypothesis, got {len(hyps)}"
            )


def test_class_c_has_exactly_two_hypotheses(entries):
    for e in entries:
        if e["discrepancy_class"] == "C":
            hyps = e.get("required_hypotheses", [])
            assert len(hyps) == 2, (
                f"Class C entry {e['id']} should have 2 hypotheses, got {len(hyps)}"
            )


def test_class_d_has_three_or_more_hypotheses(entries):
    for e in entries:
        if e["discrepancy_class"] == "D":
            hyps = e.get("required_hypotheses", [])
            assert len(hyps) >= 3, (
                f"Class D entry {e['id']} should have ≥3 hypotheses, got {len(hyps)}"
            )


# ---------------------------------------------------------------------------
# Hypothesis structure
# ---------------------------------------------------------------------------

VALID_REASONS = {"log_arg_nonzero", "denominator_nonzero", "log_arg_positive"}

def test_hypothesis_reasons_are_valid(entries):
    for e in entries:
        for h in e.get("required_hypotheses", []):
            assert h["reason"] in VALID_REASONS, (
                f"Entry {e['id']}: unknown reason {h['reason']!r}"
            )


def test_hypothesis_lean_exprs_nonempty(entries):
    for e in entries:
        for h in e.get("required_hypotheses", []):
            assert h["lean_expr"].strip(), (
                f"Entry {e['id']}: empty lean_expr in hypothesis"
            )


# ---------------------------------------------------------------------------
# Class distribution
# ---------------------------------------------------------------------------

def test_all_four_classes_present(entries):
    classes = {e["discrepancy_class"] for e in entries}
    missing = {"A", "B", "C", "D"} - classes
    assert not missing, f"Missing discrepancy classes: {missing}"


def test_class_counts(entries):
    from collections import Counter
    counts = Counter(e["discrepancy_class"] for e in entries)
    assert counts["A"] >= 4, f"Expected ≥4 Class A entries, got {counts['A']}"
    assert counts["B"] >= 4, f"Expected ≥4 Class B entries, got {counts['B']}"
    assert counts["C"] >= 4, f"Expected ≥4 Class C entries, got {counts['C']}"
    assert counts["D"] >= 4, f"Expected ≥4 Class D entries, got {counts['D']}"
