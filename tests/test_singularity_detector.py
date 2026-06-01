"""
Tests for Tier 2.2 — removable-singularity detector.

Run with:  python -m pytest tests/test_singularity_detector.py -v
"""
from __future__ import annotations

import pytest

from fricas_bridge.singularity_detector import (
    RemovableSingularity,
    detect_removable,
)


def test_no_log_no_singularity():
    assert detect_removable("x^2/2 + atan(x)") == []


def test_single_log_no_cancellation():
    assert detect_removable("log(x)") == []


def test_two_unrelated_logs_no_cancellation():
    assert detect_removable("log(x)/2 - log(x+1)") == []


def test_log_x2_half_minus_log_x_cancels():
    """log(x^2)/2 - log(x) is identically 0 for x>0 via log(x^2)=2·log|x|."""
    result = detect_removable("log(x^2)/2 - log(x)")
    assert len(result) == 1
    rs = result[0]
    assert isinstance(rs, RemovableSingularity)
    assert rs.pole == "x=0"
    assert "log(x²)=2·log|x|" in rs.cancellation or "log(x^2)" in rs.cancellation.replace("²","^2")


def test_cancellation_lean_issue_present():
    result = detect_removable("log(x^2)/2 - log(x)")
    assert result[0].lean_issue != ""
    assert "Real.log" in result[0].lean_issue or "HasDerivAt" in result[0].lean_issue


def test_tautological_cancellation():
    """log(x+1)/2 - log(x+1)/2 = 0."""
    result = detect_removable("log(x+1)/2 - log(x+1)/2")
    assert len(result) == 1
    assert result[0].pole != ""


def test_removable_singularity_fields():
    result = detect_removable("log(x^2)/2 - log(x)")
    rs = result[0]
    assert isinstance(rs.expr1, str) and rs.expr1 != ""
    assert isinstance(rs.expr2, str) and rs.expr2 != ""
    assert isinstance(rs.pole, str) and rs.pole != ""
    assert isinstance(rs.cancellation, str)
    assert isinstance(rs.lean_issue, str)


def test_no_false_positive_pfd():
    """A normal two-pole PFD should not be flagged."""
    result = detect_removable("log(x)/2 - log(x+1) + log(x+2)/2")
    assert result == []


def test_no_false_positive_pos_quad():
    """log(x^2+1) — provably positive arg, no singularity."""
    result = detect_removable("atan(x) + log(x^2+1)/2")
    assert result == []
