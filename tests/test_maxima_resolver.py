"""
Tests for Tier 5.2 — Maxima offline resolver.

Run with:  python -m pytest tests/test_maxima_resolver.py -v
"""
from __future__ import annotations

import pytest

from fricas_bridge.maxima_resolver import MaximaResolver, MAXIMA_CACHE


# ---------------------------------------------------------------------------
# Resolver construction
# ---------------------------------------------------------------------------

def test_maxima_resolver_offline_mode():
    r = MaximaResolver(mode="offline")
    assert r.mode == "offline"


def test_maxima_resolver_online_mode():
    r = MaximaResolver(mode="online")
    assert r.mode == "online"


def test_maxima_resolver_invalid_mode():
    with pytest.raises(ValueError):
        MaximaResolver(mode="bad")


# ---------------------------------------------------------------------------
# Offline cache coverage
# ---------------------------------------------------------------------------

def test_maxima_cache_non_empty():
    assert len(MAXIMA_CACHE) >= 15


def test_maxima_integrate_1_over_x():
    r = MaximaResolver()
    assert r.integrate("1/x") == "log(x)"


def test_maxima_integrate_x_over_quad():
    r = MaximaResolver()
    assert r.integrate("x/(x^2+1)") == "log(x^2+1)/2"


def test_maxima_integrate_arctan_chain():
    r = MaximaResolver()
    assert r.integrate("2*x/(1+x^4)") == "atan(x^2)"


def test_maxima_bronstein_005_factored():
    """Maxima uses factored PFD form for (x+1)/(x*(x+2)), like FriCAS."""
    r = MaximaResolver()
    result = r.integrate("(x+1)/(x*(x+2))")
    assert result == "log(x)/2 + log(x+2)/2"
    # NOT the SymPy product form log(x^2+2*x)/2
    assert "x^2" not in result


def test_maxima_bronstein_009_factored():
    """Maxima uses factored form for 1/(x*(x+1)*(x+2)), like FriCAS."""
    r = MaximaResolver()
    result = r.integrate("1/(x*(x+1)*(x+2))")
    assert result is not None
    assert "log(x)" in result
    assert "log(x+1)" in result
    assert "log(x+2)" in result


def test_maxima_bronstein_008_product():
    """Maxima uses product log for x/(x^2-4), like FriCAS."""
    r = MaximaResolver()
    assert r.integrate("x/(x^2-4)") == "log(x^2-4)/2"


def test_maxima_covers_bronstein_set():
    r = MaximaResolver()
    bronstein = [
        "(2*x*log(x^2+1)+x^3)/(x^2+1)",
        "x/(x^2+1)",
        "2*x/(1+x^4)",
        "(x+1)/(x*(x+2))",
        "1/(x^2+2*x+2)",
        "1/x",
        "x/(x^2-4)",
        "1/(x*(x+1)*(x+2))",
    ]
    for ig in bronstein:
        assert r.integrate(ig) is not None, f"Maxima cache missing: {ig}"


# ---------------------------------------------------------------------------
# Key domain-disagreement entries (acosh vs log form)
# ---------------------------------------------------------------------------

def test_maxima_1_over_sqrt_x2m1_returns_acosh():
    """Maxima uses acosh(x) for 1/sqrt(x^2-1), valid only for x≥1."""
    r = MaximaResolver()
    result = r.integrate("1/sqrt(x^2-1)")
    assert result == "acosh(x)"
    assert "log" not in result


def test_maxima_1_over_sqrt_x2p1_returns_asinh():
    """Maxima uses asinh(x) for 1/sqrt(x^2+1), defined for all reals."""
    r = MaximaResolver()
    result = r.integrate("1/sqrt(x^2+1)")
    assert result == "asinh(x)"
    assert "log" not in result


def test_maxima_sqrt_x2m1_uses_acosh():
    r = MaximaResolver()
    result = r.integrate("sqrt(x^2-1)")
    assert result is not None
    assert "acosh" in result


def test_maxima_sqrt_x2p1_uses_asinh():
    r = MaximaResolver()
    result = r.integrate("sqrt(x^2+1)")
    assert result is not None
    assert "asinh" in result


# ---------------------------------------------------------------------------
# Missing entries
# ---------------------------------------------------------------------------

def test_maxima_missing_returns_none():
    r = MaximaResolver()
    assert r.integrate("totally_unknown(x)") is None


def test_maxima_strict_raises():
    r = MaximaResolver(strict=True)
    with pytest.raises(KeyError):
        r.integrate("unknown_integrand(x)")


# ---------------------------------------------------------------------------
# Live mode (skips if Maxima not installed)
# ---------------------------------------------------------------------------

def test_maxima_online_falls_back_to_cache():
    """In online mode, if Maxima is absent, fall back to cache."""
    import shutil
    r = MaximaResolver(mode="online")
    result = r.integrate("1/x")
    if shutil.which("maxima") is None:
        assert result == "log(x)"  # from cache
    else:
        assert result is not None
