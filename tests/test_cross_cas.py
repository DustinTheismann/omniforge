"""
Tests for Tier 5 — Cross-CAS: SymPy resolver and agreement checker.

Run with:  python -m pytest tests/test_cross_cas.py -v
"""
from __future__ import annotations

import pytest

from fricas_bridge.sympy_resolver import SymPyResolver, SYMPY_CACHE
from fricas_bridge.agreement_checker import (
    AgreementClass,
    AgreementResult,
    check_agreement,
    check_all_bronstein,
)


# ---------------------------------------------------------------------------
# SymPyResolver — offline mode
# ---------------------------------------------------------------------------

def test_sympy_resolver_offline_mode():
    r = SymPyResolver(mode="offline")
    assert r.mode == "offline"


def test_sympy_resolver_invalid_mode():
    with pytest.raises(ValueError):
        SymPyResolver(mode="bad")


def test_sympy_integrate_1_over_x():
    r = SymPyResolver()
    assert r.integrate("1/x") == "log(x)"


def test_sympy_integrate_x():
    r = SymPyResolver()
    result = r.integrate("x")
    assert "x" in result


def test_sympy_integrate_atan():
    r = SymPyResolver()
    result = r.integrate("1/(1+x**2)")
    assert "atan" in result


@pytest.mark.parametrize("integrand,expected_fragment", [
    ("1/x", "log"),
    ("exp(x)", "exp"),
    ("sin(x)", "cos"),
    ("cos(x)", "sin"),
])
def test_sympy_known_integrals(integrand, expected_fragment):
    r = SymPyResolver()
    result = r.integrate(integrand)
    assert result is not None
    assert expected_fragment in result


def test_sympy_bronstein_009():
    r = SymPyResolver()
    result = r.integrate("1/(x*(x+1)*(x+2))")
    assert result is not None
    assert "log" in result


def test_sympy_missing_returns_none():
    r = SymPyResolver()
    result = r.integrate("transcendental_unknown(x)")
    assert result is None


def test_sympy_missing_strict_raises():
    r = SymPyResolver(mode="offline", strict=True)
    with pytest.raises(KeyError):
        r.integrate("transcendental_unknown(x)")


def test_sympy_cache_non_empty():
    assert len(SYMPY_CACHE) >= 8


def test_sympy_cache_covers_bronstein_set():
    r = SymPyResolver()
    bronstein_integrands = [
        "(2*x*log(x^2+1)+x^3)/(x^2+1)",
        "x/(x^2+1)",
        "2*x/(1+x^4)",
        "(x+1)/(x*(x+2))",
        "1/(x^2+2*x+2)",
        "1/x",
        "x/(x^2-4)",
        "1/(x*(x+1)*(x+2))",
    ]
    for ig in bronstein_integrands:
        assert r.integrate(ig) is not None, f"Missing cache entry: {ig}"


# ---------------------------------------------------------------------------
# Agreement checker
# ---------------------------------------------------------------------------

def test_check_agreement_returns_dataclass():
    result = check_agreement("1/x")
    assert isinstance(result, AgreementResult)


def test_check_agreement_agree_1_over_x():
    result = check_agreement("1/x")
    assert result.agreement == AgreementClass.AGREE.value


def test_check_agreement_agree_x_over_quad():
    result = check_agreement("x/(x^2+1)")
    assert result.agreement == AgreementClass.AGREE.value


def test_check_agreement_agree_atan():
    result = check_agreement("1/(x^2+2*x+2)")
    assert result.agreement == AgreementClass.AGREE.value


def test_check_agreement_both_missing():
    result = check_agreement("totally_unknown_integrand(x)")
    assert result.agreement == AgreementClass.BOTH_MISSING.value
    assert result.fricas_result is None
    assert result.sympy_result is None


def test_check_agreement_fields():
    result = check_agreement("1/x")
    assert result.integrand == "1/x"
    assert result.var == "x"
    assert result.fricas_result is not None
    assert result.sympy_result is not None


def test_check_all_bronstein_length():
    results = check_all_bronstein()
    assert len(results) == 8


def test_check_all_bronstein_all_agree():
    results = check_all_bronstein()
    for r in results:
        assert r.agreement in (
            AgreementClass.AGREE.value,
            AgreementClass.AGREE_UP_TO_C.value,
        ), f"Expected agreement for {r.integrand!r}, got {r.agreement!r}"


def test_check_all_bronstein_no_both_missing():
    for r in check_all_bronstein():
        assert r.agreement != AgreementClass.BOTH_MISSING.value


def test_agreement_class_values():
    assert AgreementClass.AGREE.value == "agree"
    assert AgreementClass.DISAGREE.value == "disagree"
    assert AgreementClass.BOTH_MISSING.value == "both_missing"
    assert AgreementClass.ONE_MISSING.value == "one_missing"
    assert AgreementClass.AGREE_UP_TO_C.value == "agree_up_to_c"
