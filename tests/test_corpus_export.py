"""
Tests for Tier 9.1 — ML corpus exporter.

Run with:  python -m pytest tests/test_corpus_export.py -v
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from ml.export_corpus import CorpusRecord, export_corpus, export_to_jsonl


# ---------------------------------------------------------------------------
# export_corpus
# ---------------------------------------------------------------------------

def test_export_corpus_returns_list():
    records = export_corpus()
    assert isinstance(records, list)


def test_export_corpus_eight_records():
    records = export_corpus()
    assert len(records) == 8


def test_export_corpus_returns_corpus_records():
    for r in export_corpus():
        assert isinstance(r, CorpusRecord)


def test_all_claim_ids_present():
    records = export_corpus()
    ids = {r.claim_id for r in records}
    assert "pf.integral.bronstein_001" in ids
    assert "pf.integral.bronstein_007" in ids
    assert "pf.integral.bronstein_009" in ids


def test_all_records_have_integrand():
    for r in export_corpus():
        assert r.integrand != "", f"{r.claim_id}: empty integrand"


def test_all_records_have_antiderivative():
    for r in export_corpus():
        assert r.antiderivative != "", f"{r.claim_id}: empty antiderivative"


def test_all_records_have_lean_theorem():
    for r in export_corpus():
        assert "HasDerivAt" in r.lean_theorem, f"{r.claim_id}: no HasDerivAt"


def test_all_records_have_coq_theorem():
    for r in export_corpus():
        assert "is_derive" in r.coq_theorem, f"{r.claim_id}: no is_derive"


def test_class_b_has_hypotheses():
    records = {r.claim_id: r for r in export_corpus()}
    r007 = records["pf.integral.bronstein_007"]
    assert r007.discrepancy_class == "B"
    assert len(r007.hypotheses) > 0


def test_class_a_no_hypotheses():
    records = {r.claim_id: r for r in export_corpus()}
    r003 = records["pf.integral.bronstein_003"]
    assert r003.discrepancy_class == "A"
    assert r003.hypotheses == []


def test_class_d_three_hypotheses():
    records = {r.claim_id: r for r in export_corpus()}
    r009 = records["pf.integral.bronstein_009"]
    assert r009.discrepancy_class == "D"
    assert len(r009.hypotheses) == 3


def test_all_records_evidence_class():
    for r in export_corpus():
        assert "E7" in r.evidence_class or "FORMALLY" in r.evidence_class, (
            f"{r.claim_id}: unexpected evidence_class {r.evidence_class!r}"
        )


def test_records_have_shape():
    for r in export_corpus():
        assert r.shape != "" and r.shape != "UNKNOWN", f"{r.claim_id}: shape={r.shape!r}"


def test_records_have_branch_discrepancies_list():
    for r in export_corpus():
        assert isinstance(r.branch_discrepancies, list)


def test_class_b_has_branch_discrepancy():
    records = {r.claim_id: r for r in export_corpus()}
    r007 = records["pf.integral.bronstein_007"]
    assert len(r007.branch_discrepancies) >= 1
    assert r007.branch_discrepancies[0]["class"] == "E_branch_cut"


# ---------------------------------------------------------------------------
# to_dict serialisability
# ---------------------------------------------------------------------------

def test_corpus_record_to_dict_json():
    for r in export_corpus():
        d = r.to_dict()
        json.dumps(d)  # must not raise


# ---------------------------------------------------------------------------
# export_to_jsonl
# ---------------------------------------------------------------------------

def test_export_to_jsonl_creates_file():
    with tempfile.TemporaryDirectory() as td:
        out = export_to_jsonl(str(Path(td) / "corpus.jsonl"))
        assert out.exists()


def test_export_to_jsonl_line_count():
    with tempfile.TemporaryDirectory() as td:
        out = export_to_jsonl(str(Path(td) / "corpus.jsonl"))
        lines = out.read_text().splitlines()
        assert len(lines) == 8


def test_export_to_jsonl_valid_json_lines():
    with tempfile.TemporaryDirectory() as td:
        out = export_to_jsonl(str(Path(td) / "corpus.jsonl"))
        for line in out.read_text().splitlines():
            obj = json.loads(line)
            assert "claim_id" in obj
            assert "integrand" in obj
            assert "lean_theorem" in obj
            assert "coq_theorem" in obj


def test_export_corpus_custom_ids():
    records = export_corpus(["pf.integral.bronstein_007"])
    assert len(records) == 1
    assert records[0].claim_id == "pf.integral.bronstein_007"
