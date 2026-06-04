"""
Tests for Tier 2.1 — branch-cut audit module.

Run with:  python -m pytest tests/test_branch_audit.py -v
"""
from __future__ import annotations

import pytest

from fricas_bridge.branch_audit import (
    BranchDiscrepancy,
    branch_audit,
    discrepancies_only,
)


# ---------------------------------------------------------------------------
# Single-subexpression classification
# ---------------------------------------------------------------------------

def test_provably_positive_quad_no_discrepancy():
    result = branch_audit("x^2+1/2")
    # No log terms → empty
    assert result == []


def test_log_provably_positive_quad():
    result = branch_audit("log(x^2+4)")
    assert len(result) == 1
    d = result[0]
    assert d.discrepancy_class == "none"
    assert d.antideriv_subexpr == "log(x^2+4)"
    assert d.is_discrepancy is False


def test_log_provably_positive_quad_commuted():
    result = branch_audit("log(1+x^2)")
    assert result[0].discrepancy_class == "none"


def test_log_simple_x_is_branch_cut():
    result = branch_audit("log(x)")
    assert len(result) == 1
    d = result[0]
    assert d.discrepancy_class == "E_branch_cut"
    assert "x > 0" in d.fricas_domain
    assert "x ≠ 0" in d.lean_domain
    assert d.is_discrepancy is True


def test_log_linear_x_plus_a():
    result = branch_audit("log(x+3)")
    d = result[0]
    assert d.discrepancy_class == "E_branch_cut"
    assert d.arg == "x+3"


def test_log_linear_x_minus_a():
    result = branch_audit("log(x-2)")
    d = result[0]
    assert d.discrepancy_class == "E_branch_cut"
    assert d.arg == "x-2"


def test_log_sign_changing_quad():
    result = branch_audit("log(x^2-9)")
    assert len(result) == 1
    d = result[0]
    assert d.discrepancy_class == "F_sign_dependent"
    assert "9" in d.fricas_domain
    assert "9" in d.lean_domain
    assert d.is_discrepancy is True


def test_atan_produces_no_entry():
    """atan is total on ℝ; branch_audit should ignore it."""
    result = branch_audit("atan(x) + atan(x+1)")
    assert result == []


def test_atan_mixed_with_log():
    """Only log subexpressions are reported."""
    result = branch_audit("log(x) + atan(x)")
    assert len(result) == 1
    assert result[0].antideriv_subexpr == "log(x)"


# ---------------------------------------------------------------------------
# Multiple log subexpressions
# ---------------------------------------------------------------------------

def test_multiple_logs_each_classified():
    expr = "log(x)/2 - log(x+1) + log(x+2)/2"
    result = branch_audit(expr)
    assert len(result) == 3
    args = [d.arg for d in result]
    assert "x" in args
    assert "x+1" in args
    assert "x+2" in args


def test_multiple_logs_all_branch_cut():
    expr = "log(x)/2 - log(x+1) + log(x+2)/2"
    result = branch_audit(expr)
    assert all(d.discrepancy_class == "E_branch_cut" for d in result)


def test_mixed_classes():
    """One provably-positive log and one sign-changing log."""
    expr = "log(x^2+1) + log(x^2-4)"
    result = branch_audit(expr)
    assert len(result) == 2
    classes = {d.discrepancy_class for d in result}
    assert "none" in classes
    assert "F_sign_dependent" in classes


# ---------------------------------------------------------------------------
# discrepancies_only filter
# ---------------------------------------------------------------------------

def test_discrepancies_only_drops_none():
    expr = "log(x^2+1) + log(x)"
    full = branch_audit(expr)
    filtered = discrepancies_only(expr)
    assert len(full) == 2
    assert len(filtered) == 1
    assert filtered[0].discrepancy_class == "E_branch_cut"


def test_discrepancies_only_empty_when_all_clear():
    assert discrepancies_only("log(x^2+1)") == []


def test_discrepancies_only_keeps_f_sign():
    assert len(discrepancies_only("log(x^2-4)")) == 1


# ---------------------------------------------------------------------------
# BranchDiscrepancy dataclass
# ---------------------------------------------------------------------------

def test_branch_discrepancy_fields():
    result = branch_audit("log(x)")
    d = result[0]
    assert d.antideriv_subexpr == "log(x)"
    assert d.arg == "x"
    assert isinstance(d.fricas_domain, str)
    assert isinstance(d.lean_domain, str)
    assert isinstance(d.discrepancy_class, str)


def test_is_discrepancy_property():
    d_none = BranchDiscrepancy("log(x^2+1)", "x^2+1", "f", "l", "none")
    d_e = BranchDiscrepancy("log(x)", "x", "f", "l", "E_branch_cut")
    d_f = BranchDiscrepancy("log(x^2-4)", "x^2-4", "f", "l", "F_sign_dependent")
    assert d_none.is_discrepancy is False
    assert d_e.is_discrepancy is True
    assert d_f.is_discrepancy is True


# ---------------------------------------------------------------------------
# Real antiderivatives from the Risch–Bronstein claim set
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("antideriv, expected_class", [
    # Class A: no log
    ("x^2/2", None),
    # Class A: log(x^2+1) — provably positive
    ("atan(x) + x/(2*(x^2+1))", None),
    # Class B: log(x)
    ("log(x)", "E_branch_cut"),
    # Class C: log(x)/2 - log(x+1)
    ("log(x)/2 - log(x+1)", "E_branch_cut"),
    # F_sign_dependent
    ("log(x^2-1)/2", "F_sign_dependent"),
])
def test_real_antiderivatives(antideriv, expected_class):
    result = branch_audit(antideriv)
    if expected_class is None:
        assert all(d.discrepancy_class == "none" for d in result)
    else:
        assert any(d.discrepancy_class == expected_class for d in result)
