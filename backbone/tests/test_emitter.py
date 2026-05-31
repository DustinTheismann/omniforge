"""
Tests for backbone/cas_protocol/lean_emitter.py

Run with:  python -m pytest backbone/tests/test_emitter.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backbone.cas_protocol.lean_emitter import emit_lean_file, emit_lean_batch
from backbone.cas_protocol.normalize import normalize, fricas_to_lean, lean_to_fricas

CORPUS_PATH = Path(__file__).parent.parent / "corpus" / "bronstein.jsonl"


@pytest.fixture(scope="module")
def entries() -> list[dict]:
    lines = [l for l in CORPUS_PATH.read_text().splitlines() if l.strip()]
    return [json.loads(line) for line in lines]


# ---------------------------------------------------------------------------
# normalize.py
# ---------------------------------------------------------------------------

def test_normalize_collapses_whitespace():
    assert normalize("x + y") == "x+y"


def test_normalize_atan_to_arctan():
    assert normalize("atan(x)") == "arctan(x)"


def test_normalize_power_operator():
    assert normalize("x**2") == "x^2"


def test_fricas_to_lean_log():
    result = fricas_to_lean("log(x^2+1)/2")
    assert "Real.log" in result


def test_fricas_to_lean_arctan():
    result = fricas_to_lean("atan(x+1)")
    assert "Real.arctan" in result
    assert "atan" not in result.replace("Real.arctan", "")


def test_lean_to_fricas_roundtrip():
    orig = "Real.log (x + 1) / 2"
    back = lean_to_fricas(orig)
    assert "Real.log" not in back
    assert "log" in back


# ---------------------------------------------------------------------------
# emit_lean_file
# ---------------------------------------------------------------------------

def test_emit_lean_file_returns_string(entries):
    entry = entries[0]
    src = emit_lean_file(entry)
    assert isinstance(src, str)
    assert len(src) > 50


def test_emit_lean_file_contains_imports(entries):
    src = emit_lean_file(entries[0])
    assert "import Mathlib" in src


def test_emit_lean_file_contains_theorem(entries):
    entry = entries[0]
    src = emit_lean_file(entry)
    assert "theorem" in src
    assert entry["id"] in src


def test_emit_lean_file_no_hyps_for_class_a(entries):
    class_a = next(e for e in entries if e["discrepancy_class"] == "A")
    src = emit_lean_file(class_a)
    assert "HasDerivAt" in src
    # No hypothesis parameters in signature
    lines = src.splitlines()
    theorem_line = next(l for l in lines if l.startswith("theorem"))
    assert "hne" not in theorem_line


def test_emit_lean_file_has_hyp_params_for_class_b(entries):
    class_b = next(e for e in entries if e["discrepancy_class"] == "B")
    src = emit_lean_file(class_b)
    assert "h0 :" in src


def test_emit_lean_file_has_hyp_params_for_class_d(entries):
    class_d = next(e for e in entries if e["discrepancy_class"] == "D")
    src = emit_lean_file(class_d)
    # Class D has ≥3 hypotheses → h0, h1, h2 all present
    assert "h0 :" in src
    assert "h1 :" in src
    assert "h2 :" in src


# ---------------------------------------------------------------------------
# emit_lean_batch
# ---------------------------------------------------------------------------

def test_emit_lean_batch_returns_string(entries):
    src = emit_lean_batch(entries[:3])
    assert isinstance(src, str)


def test_emit_lean_batch_contains_all_ids(entries):
    batch = entries[:5]
    src = emit_lean_batch(batch)
    for entry in batch:
        assert entry["id"] in src, f"Missing {entry['id']} in batch output"


def test_emit_lean_batch_has_single_import_block(entries):
    src = emit_lean_batch(entries)
    import_count = src.count("import Mathlib.Analysis.SpecialFunctions.Log.Deriv")
    assert import_count == 1, f"Expected 1 import block, got {import_count}"


def test_emit_lean_batch_all_24_entries(entries):
    src = emit_lean_batch(entries)
    theorem_count = src.count("theorem risch_")
    assert theorem_count == len(entries), (
        f"Expected {len(entries)} theorems, got {theorem_count}"
    )
