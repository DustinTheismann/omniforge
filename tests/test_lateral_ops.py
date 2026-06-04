"""
Tests for Tier 3 — lateral FriCAS operations (differentiate, limit, series, factor).

Run with:  python -m pytest tests/test_lateral_ops.py -v
"""
from __future__ import annotations

import pytest

from fricas_bridge.lateral_ops import (
    fricas_differentiate,
    fricas_limit,
    fricas_series,
    fricas_factor,
    CACHE_DIFF,
    CACHE_LIMIT,
    CACHE_SERIES,
    CACHE_FACTOR,
    _MISSING,
)


# ---------------------------------------------------------------------------
# fricas_differentiate
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("expr, expected", [
    ("x^2/2",   "x"),
    ("x^3/3",   "x^2"),
    ("log(x)",  "1/x"),
    ("atan(x)", "1/(1+x^2)"),
    ("sin(x)",  "cos(x)"),
    ("cos(x)",  "-sin(x)"),
    ("exp(x)",  "exp(x)"),
])
def test_differentiate_known(expr, expected):
    assert fricas_differentiate(expr) == expected


def test_differentiate_bronstein_003():
    assert fricas_differentiate("log(x^2+1)/2") == "x/(x^2+1)"


def test_differentiate_bronstein_007():
    assert fricas_differentiate("log(x)") == "1/x"


def test_differentiate_bronstein_009():
    result = fricas_differentiate("log(x)/2-log(x+1)+log(x+2)/2")
    assert result == "1/(x*(x+1)*(x+2))"


def test_differentiate_missing_returns_sentinel():
    result = fricas_differentiate("completely_unknown(x)")
    assert result == _MISSING


def test_differentiate_missing_strict_raises():
    with pytest.raises(KeyError, match="fricas_differentiate"):
        fricas_differentiate("completely_unknown(x)", strict=True)


def test_differentiate_cache_has_all_bronstein():
    # All 9 Bronstein antiderivatives should be in the cache
    bronstein = [
        "log(x^2+1)^2/2+x^2/2-log(x^2+1)/2",  # 001
        "log(x^2+1)/2",                         # 003
        "log(x)/2+log(x+2)/2",                  # 005
        "log(x)",                               # 007
        "log(x^2-4)/2",                         # 008
        "log(x)/2-log(x+1)+log(x+2)/2",        # 009
    ]
    for expr in bronstein:
        result = fricas_differentiate(expr)
        assert result != _MISSING, f"Missing cache entry for: {expr}"


# ---------------------------------------------------------------------------
# fricas_limit
# ---------------------------------------------------------------------------

def test_limit_1_over_x_right():
    assert fricas_limit("1/x", "x", "0", "+") == "+infinity"


def test_limit_1_over_x_left():
    assert fricas_limit("1/x", "x", "0", "-") == "-infinity"


def test_limit_1_over_x_infinity():
    assert fricas_limit("1/x", "x", "infinity", "") == "0"


def test_limit_sinc_at_zero():
    assert fricas_limit("sin(x)/x", "x", "0", "") == "1"


def test_limit_log_at_zero_right():
    assert fricas_limit("log(x)", "x", "0", "+") == "-infinity"


def test_limit_atan_at_infinity():
    assert fricas_limit("atan(x)", "x", "infinity", "") == "pi/2"


def test_limit_atan_at_neg_infinity():
    assert fricas_limit("atan(x)", "x", "-infinity", "") == "-pi/2"


def test_limit_missing_returns_sentinel():
    assert fricas_limit("mystery(x)", "x", "0", "") == _MISSING


def test_limit_missing_strict_raises():
    with pytest.raises(KeyError, match="fricas_limit"):
        fricas_limit("mystery(x)", "x", "0", "", strict=True)


# ---------------------------------------------------------------------------
# fricas_series
# ---------------------------------------------------------------------------

def test_series_exp():
    result = fricas_series("exp(x)", "x", "0", 5)
    assert "x^2/2" in result
    assert "O(x^5)" in result


def test_series_sin():
    result = fricas_series("sin(x)", "x", "0", 5)
    assert "x^3/6" in result
    assert "O(x^5)" in result


def test_series_log_1_plus_x():
    result = fricas_series("log(1+x)", "x", "0", 5)
    assert "x^2/2" in result


def test_series_atan():
    result = fricas_series("atan(x)", "x", "0", 5)
    assert "x^3/3" in result


def test_series_geometric():
    result = fricas_series("1/(1-x)", "x", "0", 5)
    assert "x^4" in result


def test_series_missing_returns_sentinel():
    assert fricas_series("unknown(x)", "x", "0", 5) == _MISSING


def test_series_missing_strict_raises():
    with pytest.raises(KeyError, match="fricas_series"):
        fricas_series("unknown(x)", "x", "0", 5, strict=True)


# ---------------------------------------------------------------------------
# fricas_factor
# ---------------------------------------------------------------------------

def test_factor_difference_of_squares():
    assert fricas_factor("x^2-1") == "(x-1)*(x+1)"


def test_factor_x_squared_minus_4():
    assert fricas_factor("x^2-4") == "(x-2)*(x+2)"


def test_factor_perfect_square():
    assert fricas_factor("x^2+2*x+1") == "(x+1)^2"


def test_factor_cubic():
    assert fricas_factor("x^3-1") == "(x-1)*(x^2+x+1)"


def test_factor_irreducible_over_r():
    assert fricas_factor("x^2+1") == "x^2+1"


def test_factor_missing_returns_sentinel():
    assert fricas_factor("unknown_poly") == _MISSING


def test_factor_missing_strict_raises():
    with pytest.raises(KeyError, match="fricas_factor"):
        fricas_factor("unknown_poly", strict=True)


# ---------------------------------------------------------------------------
# Cache completeness
# ---------------------------------------------------------------------------

def test_caches_non_empty():
    assert len(CACHE_DIFF) > 0
    assert len(CACHE_LIMIT) > 0
    assert len(CACHE_SERIES) > 0
    assert len(CACHE_FACTOR) > 0
