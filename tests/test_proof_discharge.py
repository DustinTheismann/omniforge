"""
Tests for fricas_bridge/proof_discharger.py — Step D acceptance criteria.

Verifies:
  - FRICAS_CACHE contains all 9 claims
  - classify_antideriv identifies correct shapes for Class A claims
  - generate_theorem_text produces syntactically plausible Lean output
  - RischAutoDischarge.lean exists and matches the generator output
  - All four Class A theorem names are present in the generated file

Run with:  python -m pytest tests/test_proof_discharge.py -v
"""
from __future__ import annotations

from pathlib import Path

import pytest

from fricas_bridge.proof_discharger import (
    FRICAS_CACHE,
    classify_antideriv,
    discharge_all,
    generate_autodischarge_lean,
    generate_theorem_text,
)

_LEAN_FILE = Path(__file__).parent.parent / "fricas_bridge" / "RischAutoDischarge.lean"
_CLASS_A   = [
    "pf.integral.bronstein_001",
    "pf.integral.bronstein_003",
    "pf.integral.bronstein_004",
    "pf.integral.bronstein_006",
]


# ---------------------------------------------------------------------------
# FRICAS_CACHE
# ---------------------------------------------------------------------------

def test_cache_has_nine_entries():
    assert len(FRICAS_CACHE) == 9


@pytest.mark.parametrize("n", range(1, 10))
def test_cache_entry_has_required_keys(n: int):
    cid = f"pf.integral.bronstein_{n:03d}"
    entry = FRICAS_CACHE[cid]
    assert "integrand_fricas" in entry
    assert "antideriv_fricas" in entry


def test_cache_class_a_integrands():
    assert FRICAS_CACHE["pf.integral.bronstein_003"]["integrand_fricas"] == "x/(x^2+1)"
    assert FRICAS_CACHE["pf.integral.bronstein_004"]["integrand_fricas"] == "2*x/(1+x^4)"
    assert FRICAS_CACHE["pf.integral.bronstein_006"]["integrand_fricas"] == "1/(x^2+2*x+2)"


# ---------------------------------------------------------------------------
# classify_antideriv
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fricas,expected_shape", [
    ("log(x^2+1)/2",  "LOG_POS_QUAD"),
    ("atan(x^2)",     "ARCTAN_POW"),
    ("atan(x+1)",     "ARCTAN_LINEAR"),
    ("log(x^2+1)^2/2 + x^2/2 - log(x^2+1)/2", "COMPLEX_SUM"),
])
def test_classify_shape(fricas: str, expected_shape: str):
    result = classify_antideriv(fricas)
    assert result["shape"] == expected_shape, (
        f"classify_antideriv({fricas!r}) gave shape {result['shape']!r}, "
        f"expected {expected_shape!r}"
    )


def test_classify_log_pos_quad_c():
    result = classify_antideriv("log(x^2+1)/2")
    assert result["c"] == "1"


def test_classify_arctan_pow_params():
    result = classify_antideriv("atan(x^2)")
    assert result["n"] == 2
    assert "t ^ 2" in result["p_lean"]
    assert "2 * t" in result["dp_lean"]


def test_classify_arctan_linear_params():
    result = classify_antideriv("atan(x+1)")
    assert result["c"] == "1"
    assert "t + 1" in result["p_lean"]
    assert result["dp_lean"] == "1"


def test_classify_claim_001_fricas():
    antideriv = FRICAS_CACHE["pf.integral.bronstein_001"]["antideriv_fricas"]
    result = classify_antideriv(antideriv)
    assert result["shape"] == "COMPLEX_SUM"


# ---------------------------------------------------------------------------
# generate_theorem_text
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("claim_id", _CLASS_A)
def test_theorem_text_is_nonempty(claim_id: str):
    text = generate_theorem_text(claim_id)
    assert len(text) > 0


@pytest.mark.parametrize("claim_id,theorem_name", [
    ("pf.integral.bronstein_001", "autodischarge_001"),
    ("pf.integral.bronstein_003", "autodischarge_003"),
    ("pf.integral.bronstein_004", "autodischarge_004"),
    ("pf.integral.bronstein_006", "autodischarge_006"),
])
def test_theorem_text_contains_name(claim_id: str, theorem_name: str):
    text = generate_theorem_text(claim_id)
    assert f"theorem {theorem_name}" in text


@pytest.mark.parametrize("claim_id", _CLASS_A)
def test_theorem_text_has_has_deriv_at(claim_id: str):
    text = generate_theorem_text(claim_id)
    assert "HasDerivAt" in text


@pytest.mark.parametrize("claim_id", _CLASS_A)
def test_theorem_text_has_proof_opener(claim_id: str):
    text = generate_theorem_text(claim_id)
    assert ":= by" in text


@pytest.mark.parametrize("claim_id", _CLASS_A)
def test_theorem_text_has_fun_lambda(claim_id: str):
    text = generate_theorem_text(claim_id)
    assert "fun t : ℝ =>" in text


# Antiderivative bodies must appear in statements
def test_theorem_001_antideriv_body():
    text = generate_theorem_text("pf.integral.bronstein_001")
    assert "Real.log (t ^ 2 + 1) ^ 2 / 2" in text
    assert "t ^ 2 / 2" in text


def test_theorem_003_antideriv_body():
    text = generate_theorem_text("pf.integral.bronstein_003")
    assert "Real.log (t ^ 2 + 1) / 2" in text


def test_theorem_004_antideriv_body():
    text = generate_theorem_text("pf.integral.bronstein_004")
    assert "Real.arctan (t ^ 2)" in text


def test_theorem_006_antideriv_body():
    text = generate_theorem_text("pf.integral.bronstein_006")
    assert "Real.arctan (t + 1)" in text


# Proof strategies
def test_theorem_003_uses_positivity():
    text = generate_theorem_text("pf.integral.bronstein_003")
    assert "positivity" in text


def test_theorem_004_uses_comp():
    text = generate_theorem_text("pf.integral.bronstein_004")
    assert ".comp" in text


def test_theorem_006_uses_nlinarith():
    text = generate_theorem_text("pf.integral.bronstein_006")
    assert "nlinarith" in text


def test_theorem_001_uses_field_simp_ring():
    text = generate_theorem_text("pf.integral.bronstein_001")
    assert "field_simp" in text
    assert "ring" in text


# ---------------------------------------------------------------------------
# discharge_all
# ---------------------------------------------------------------------------

def test_discharge_all_returns_eight():
    """All nine claims minus 002 (equational corollary of 001) = 8 theorems."""
    results = discharge_all()
    assert len(results) == 8


def test_discharge_all_has_required_keys():
    for entry in discharge_all():
        assert "claim_id"     in entry
        assert "theorem_name" in entry
        assert "lean_text"    in entry
        assert "shape"        in entry
        assert "class"        in entry
        assert "hypotheses"   in entry


def test_discharge_all_claim_ids():
    ids = {e["claim_id"] for e in discharge_all()}
    assert ids == {f"pf.integral.bronstein_{n:03d}" for n in (1, 3, 4, 5, 6, 7, 8, 9)}


# ---------------------------------------------------------------------------
# RischAutoDischarge.lean on disk
# ---------------------------------------------------------------------------

def test_lean_file_exists():
    assert _LEAN_FILE.exists(), f"RischAutoDischarge.lean not found at {_LEAN_FILE}"


def test_lean_file_has_auto_generated_header():
    src = _LEAN_FILE.read_text()
    assert "AUTO-GENERATED" in src


def test_lean_file_has_mathlib_imports():
    src = _LEAN_FILE.read_text()
    assert "import Mathlib" in src


def test_lean_file_contains_all_eight_theorems():
    src = _LEAN_FILE.read_text()
    for n in (1, 3, 4, 5, 6, 7, 8, 9):
        name = f"autodischarge_{n:03d}"
        assert f"theorem {name}" in src, f"Missing theorem {name} in RischAutoDischarge.lean"


def test_lean_file_matches_generator():
    """Committed file must match what generate_autodischarge_lean() would produce."""
    expected = generate_autodischarge_lean()
    actual = _LEAN_FILE.read_text()
    assert actual == expected, (
        "RischAutoDischarge.lean is out of sync with proof_discharger.py.\n"
        "Regenerate with: python -m fricas_bridge.proof_discharger --generate"
    )


def test_lean_file_has_all_class_a_integrands():
    src = _LEAN_FILE.read_text()
    # Integrand expressions present in theorem statements
    assert "x ^ 2 + 1" in src
    assert "1 + x ^ 4" in src
    assert "x ^ 2 + 2 * x + 2" in src


# ---------------------------------------------------------------------------
# Tier 1 — all four discrepancy classes
# ---------------------------------------------------------------------------

from fricas_bridge.proof_discharger import synthesize_hypotheses  # noqa: E402

_ALL = [f"pf.integral.bronstein_{n:03d}" for n in (1, 3, 4, 5, 6, 7, 8, 9)]


@pytest.mark.parametrize("fricas,shape", [
    ("log(x)",          "LOG_SIMPLE"),
    ("log(x^2-4)/2",    "LOG_NEG_QUAD"),
    ("log(x)/2 + log(x+2)/2", "LOG_PFD"),
    ("log(x)/2 - log(x+1) + log(x+2)/2", "LOG_PFD"),
])
def test_classify_bcd_shapes(fricas: str, shape: str):
    assert classify_antideriv(fricas)["shape"] == shape


def test_synthesize_class_a_no_hypotheses():
    for fricas in ("log(x^2+1)/2", "atan(x^2)", "atan(x+1)"):
        assert synthesize_hypotheses(fricas) == []


def test_synthesize_class_b_single_hypothesis():
    hyps = synthesize_hypotheses("log(x)")
    assert len(hyps) == 1
    assert hyps[0].statement == "x ≠ 0"


def test_synthesize_class_b_quadratic_arg():
    hyps = synthesize_hypotheses("log(x^2-4)/2")
    assert len(hyps) == 1
    assert "x ^ 2 - 4 ≠ 0" == hyps[0].statement


def test_synthesize_class_c_two_hypotheses():
    hyps = synthesize_hypotheses("log(x)/2 + log(x+2)/2")
    stmts = [h.statement for h in hyps]
    assert stmts == ["x ≠ 0", "x + 2 ≠ 0"]


def test_synthesize_class_d_three_hypotheses():
    hyps = synthesize_hypotheses("log(x)/2 - log(x+1) + log(x+2)/2")
    stmts = [h.statement for h in hyps]
    assert stmts == ["x ≠ 0", "x + 1 ≠ 0", "x + 2 ≠ 0"]


@pytest.mark.parametrize("claim_id", _ALL)
def test_all_claims_generate(claim_id: str):
    text = generate_theorem_text(claim_id)
    assert "HasDerivAt" in text and ":= by" in text


def test_class_b_theorem_carries_hypothesis_binder():
    text = generate_theorem_text("pf.integral.bronstein_007")
    assert "(hx : x ≠ 0)" in text


def test_class_c_theorem_carries_two_binders():
    text = generate_theorem_text("pf.integral.bronstein_005")
    assert "(hx : x ≠ 0)" in text
    assert "(hx2 : x + 2 ≠ 0)" in text


def test_class_d_theorem_carries_three_binders():
    text = generate_theorem_text("pf.integral.bronstein_009")
    assert "(hx : x ≠ 0)" in text
    assert "(hx1 : x + 1 ≠ 0)" in text
    assert "(hx2 : x + 2 ≠ 0)" in text


def test_class_distribution():
    by_class: dict[str, int] = {}
    for e in discharge_all():
        by_class[e["class"]] = by_class.get(e["class"], 0) + 1
    assert by_class == {"A": 4, "B": 2, "C": 1, "D": 1}
