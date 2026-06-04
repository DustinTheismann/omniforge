"""
Tests for fricas_bridge/lean_statement_parser.py —
the Python analogue of `lean_to_fricas : Expr → MetaM String`.

Round-trip contract: for every claim in claims 002-009,
  extract_integrand(statement_text)  →  Lean 4 integrand string
  lean_expr_to_fricas(lean_string)   →  FriCAS integrand string
  FriCAS integrand == claims.inputs.integrand

Claim 001 uses external symbol references (`antiderivative`, `integrand x`)
and is tested separately as a "reference form" parse.

Run with:  python -m pytest tests/test_lean_to_fricas.py -v
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pytest

from fricas_bridge.lean_statement_parser import (
    extract_integrand,
    lean_expr_to_fricas,
    to_fricas,
)

EXAMPLES_DIR = Path(__file__).parent.parent / "protocols" / "claim_protocol" / "examples"
LEAN_SOURCE = Path(__file__).parent.parent / "fricas_bridge" / "FriCASTranslator.lean"


def _claim(n: int) -> dict:
    return json.loads((EXAMPLES_DIR / f"risch_bronstein_{n:03d}.json").read_text())


# ---------------------------------------------------------------------------
# Lean 4 file exists and has the required function definition
# ---------------------------------------------------------------------------

def test_translator_lean_file_exists():
    assert LEAN_SOURCE.exists(), "FriCASTranslator.lean not found"


def test_translator_defines_lean_to_fricas():
    src = LEAN_SOURCE.read_text()
    assert "def lean_to_fricas" in src, (
        "FriCASTranslator.lean does not define lean_to_fricas"
    )


def test_translator_defines_integrand_of():
    src = LEAN_SOURCE.read_text()
    assert "def integrand_of_has_deriv_at" in src, (
        "FriCASTranslator.lean does not define integrand_of_has_deriv_at"
    )


def test_translator_covers_all_operators():
    src = LEAN_SOURCE.read_text()
    for op in ["HAdd.hAdd", "HSub.hSub", "HMul.hMul", "HDiv.hDiv", "HPow.hPow",
               "Neg.neg", "Real.log", "Real.exp", "Real.arctan",
               "Real.sin", "Real.cos", "Real.sqrt"]:
        assert op in src, f"FriCASTranslator.lean missing coverage for {op}"


def test_translator_uses_metalm():
    src = LEAN_SOURCE.read_text()
    assert "MetaM" in src, "FriCASTranslator.lean does not use MetaM"


# ---------------------------------------------------------------------------
# lean_expr_to_fricas — unit tests for individual expression patterns
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lean_expr,expected", [
    # Basic arithmetic
    ("x + 1",               "x+1"),
    ("x - 1",               "x-1"),
    ("2 * x",               "2*x"),
    ("1 / x",               "1/x"),
    ("x ^ 2",               "x^2"),
    # Grouped expressions
    ("x / (x ^ 2 + 1)",     "x/(x^2+1)"),
    ("2 * x / (1 + x ^ 4)", "2*x/(1+x^4)"),
    ("(x + 1) / (x * (x + 2))", "(x+1)/(x*(x+2))"),
    ("1 / (x ^ 2 + 2 * x + 2)", "1/(x^2+2*x+2)"),
    ("x / (x ^ 2 - 4)",     "x/(x^2-4)"),
    ("1 / (x * (x + 1) * (x + 2))", "1/(x*(x+1)*(x+2))"),
    # Special functions
    ("Real.log x",          "log(x)"),
    ("Real.log (x + 1)",    "log(x+1)"),
    ("Real.arctan x",       "atan(x)"),
    ("Real.arctan (x + 1)", "atan(x+1)"),
    ("Real.exp x",          "exp(x)"),
    ("Real.sin x",          "sin(x)"),
    ("Real.cos x",          "cos(x)"),
    ("Real.sqrt x",         "sqrt(x)"),
    # Log inside a larger expression (claim 002 integrand)
    (
        "(2 * x * Real.log (x ^ 2 + 1) + x ^ 3) / (x ^ 2 + 1)",
        "(2*x*log(x^2+1)+x^3)/(x^2+1)",
    ),
])
def test_lean_expr_to_fricas(lean_expr: str, expected: str):
    result = lean_expr_to_fricas(lean_expr)
    assert result == expected, f"lean_expr_to_fricas({lean_expr!r}) = {result!r}, expected {expected!r}"


# ---------------------------------------------------------------------------
# extract_integrand — statement text parsing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("stmt,expected", [
    # Standard HasDerivAt form
    (
        "theorem risch_simple_log (x : ℝ) : HasDerivAt (fun t : ℝ => Real.log (t ^ 2 + 1) / 2) (x / (x ^ 2 + 1)) x",
        "x / (x ^ 2 + 1)",
    ),
    (
        "theorem risch_arctan (x : ℝ) : HasDerivAt (fun t : ℝ => Real.arctan (t ^ 2)) (2 * x / (1 + x ^ 4)) x",
        "2 * x / (1 + x ^ 4)",
    ),
    (
        "theorem risch_partial_fractions (x : ℝ) (hx : x ≠ 0) (hx2 : x + 2 ≠ 0) : HasDerivAt (fun t : ℝ => Real.log t / 2 + Real.log (t + 2) / 2) ((x + 1) / (x * (x + 2))) x",
        "(x + 1) / (x * (x + 2))",
    ),
    (
        "theorem risch_arctan_shifted (x : ℝ) : HasDerivAt (fun t : ℝ => Real.arctan (t + 1)) (1 / (x ^ 2 + 2 * x + 2)) x",
        "1 / (x ^ 2 + 2 * x + 2)",
    ),
    (
        "theorem risch_recip_x (x : ℝ) (hx : x ≠ 0) : HasDerivAt (fun t : ℝ => Real.log t) (1 / x) x",
        "1 / x",
    ),
    (
        "theorem risch_log_quadratic_neg (x : ℝ) (hne : (x ^ 2 - 4 : ℝ) ≠ 0) : HasDerivAt (fun t : ℝ => Real.log (t ^ 2 - 4) / 2) (x / (x ^ 2 - 4)) x",
        "x / (x ^ 2 - 4)",
    ),
    (
        "theorem risch_three_poles (x : ℝ) (hx : x ≠ 0) (hx1 : x + 1 ≠ 0) (hx2 : x + 2 ≠ 0) : HasDerivAt (fun t : ℝ => Real.log t / 2 - Real.log (t + 1) + Real.log (t + 2) / 2) (1 / (x * (x + 1) * (x + 2))) x",
        "1 / (x * (x + 1) * (x + 2))",
    ),
])
def test_extract_integrand(stmt: str, expected: str):
    result = extract_integrand(stmt)
    assert result == expected, (
        f"extract_integrand() returned {result!r}, expected {expected!r}"
    )


def test_extract_integrand_equational_form():
    stmt = _claim(2)["formal_targets"][0]["statement_text"]
    result = extract_integrand(stmt)
    assert result is not None
    assert "Real.log" in result, "Equational integrand should contain Real.log"
    assert "x ^ 2 + 1" in result or "x^2+1" in result.replace(" ", "")


def test_extract_integrand_reference_form():
    """Claim 001 uses external symbol references — extract returns the reference."""
    stmt = _claim(1)["formal_targets"][0]["statement_text"]
    result = extract_integrand(stmt)
    assert result is not None
    assert "integrand" in result, (
        "Claim 001 reference form should contain 'integrand'"
    )


# ---------------------------------------------------------------------------
# Round-trip: statement_text → FriCAS integrand, for claims 003-009
# ---------------------------------------------------------------------------

ROUND_TRIP_CLAIMS = list(range(3, 10))  # 003-009 have inline expressions

@pytest.mark.parametrize("n", ROUND_TRIP_CLAIMS)
def test_round_trip(n: int):
    claim = _claim(n)
    stmt = claim["formal_targets"][0]["statement_text"]
    expected_fricas = claim["inputs"]["integrand"]

    result = to_fricas(stmt)
    assert result is not None, f"claim {n:03d}: to_fricas returned None"
    assert result == expected_fricas, (
        f"claim {n:03d}: round-trip mismatch\n"
        f"  statement : {stmt}\n"
        f"  extracted : {extract_integrand(stmt)!r}\n"
        f"  got       : {result!r}\n"
        f"  expected  : {expected_fricas!r}"
    )


def test_round_trip_claim_002():
    """Claim 002 uses equational form; verify it round-trips separately."""
    claim = _claim(2)
    stmt = claim["formal_targets"][0]["statement_text"]
    expected_fricas = claim["inputs"]["integrand"]  # "(2*x*log(x^2+1)+x^3)/(x^2+1)"

    result = to_fricas(stmt)
    assert result is not None, "claim 002: to_fricas returned None"
    assert result == expected_fricas, (
        f"claim 002 round-trip failed:\n"
        f"  got      {result!r}\n"
        f"  expected {expected_fricas!r}"
    )


# ---------------------------------------------------------------------------
# Operator coverage: each operator appears in at least one integrand
# ---------------------------------------------------------------------------

def test_coverage_division():
    assert lean_expr_to_fricas("1 / x") == "1/x"


def test_coverage_multiplication():
    assert lean_expr_to_fricas("2 * x") == "2*x"


def test_coverage_power():
    assert lean_expr_to_fricas("x ^ 2") == "x^2"


def test_coverage_addition():
    assert lean_expr_to_fricas("x + 1") == "x+1"


def test_coverage_subtraction():
    assert lean_expr_to_fricas("x - 1") == "x-1"


def test_coverage_log():
    assert lean_expr_to_fricas("Real.log (x + 1)") == "log(x+1)"


def test_coverage_arctan():
    assert lean_expr_to_fricas("Real.arctan x") == "atan(x)"


def test_coverage_exp():
    assert lean_expr_to_fricas("Real.exp x") == "exp(x)"


def test_coverage_sin():
    assert lean_expr_to_fricas("Real.sin x") == "sin(x)"


def test_coverage_cos():
    assert lean_expr_to_fricas("Real.cos x") == "cos(x)"


def test_coverage_sqrt():
    assert lean_expr_to_fricas("Real.sqrt x") == "sqrt(x)"


# ---------------------------------------------------------------------------
# Error sentinel: unrecognised expressions pass through unchanged
# (Python side returns the string as-is; Lean side returns "??" prefix)
# ---------------------------------------------------------------------------

def test_unknown_expression_is_not_empty():
    result = lean_expr_to_fricas("some_unknown_function x")
    assert result, "Unknown expressions should not produce empty string"
