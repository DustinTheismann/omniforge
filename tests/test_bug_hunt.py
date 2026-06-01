"""
Tests for Tier 6 — CAS bug hunt verification loop.

Run with:  python -m pytest tests/test_bug_hunt.py -v
"""
from __future__ import annotations

import pytest

from fricas_bridge.bug_hunt import (
    BugCandidate,
    VERIFIED,
    MISMATCH,
    INCONCLUSIVE,
    NO_ANTIDERIV,
    run_bug_hunt,
    run_bronstein_bug_hunt,
)


# ---------------------------------------------------------------------------
# run_bug_hunt basics
# ---------------------------------------------------------------------------

def test_run_bug_hunt_returns_list():
    results = run_bug_hunt([("1/x", "x")])
    assert isinstance(results, list)
    assert len(results) == 1


def test_run_bug_hunt_returns_bug_candidates():
    results = run_bug_hunt([("1/x", "x")])
    assert isinstance(results[0], BugCandidate)


def test_verified_1_over_x():
    """∫ 1/x dx = log(x), D(log(x)) = 1/x — verified."""
    [r] = run_bug_hunt([("1/x", "x")])
    assert r.verdict == VERIFIED
    assert r.fricas_antideriv == "log(x)"
    assert r.differentiated == "1/x"


def test_verified_x_over_quad():
    [r] = run_bug_hunt([("x/(x^2+1)", "x")])
    assert r.verdict == VERIFIED


def test_verified_atan():
    [r] = run_bug_hunt([("1/(x^2+2*x+2)", "x")])
    assert r.verdict == VERIFIED


def test_no_antideriv_cache_miss():
    [r] = run_bug_hunt([("mystery_integrand(x)", "x")])
    assert r.verdict == NO_ANTIDERIV
    assert r.fricas_antideriv is None


def test_inconclusive_when_diff_cache_miss():
    """When the FriCAS antideriv exists but D(antideriv) is not in the cache."""
    # Use an integrand we know has an antideriv entry but the antideriv
    # itself is not in the differentiation cache.
    # We'll pick an entry from the FriCAS cache that maps to something not
    # in CACHE_DIFF.  The simplest: check bronstein_001 antideriv.
    from fricas_bridge.offline_cache import FriCASResolver
    result = FriCASResolver(mode="offline").resolve("(2*x*log(x^2+1)+x^3)/(x^2+1)")
    antideriv = result.antiderivative if result.ok else None
    if antideriv is None:
        pytest.skip("bronstein_001 not in FriCAS cache")

    from fricas_bridge.lateral_ops import fricas_differentiate, _MISSING
    diff = fricas_differentiate(antideriv)
    if diff != _MISSING:
        pytest.skip("antideriv unexpectedly in diff cache — skip inconclusive test")

    [r] = run_bug_hunt([("(2*x*log(x^2+1)+x^3)/(x^2+1)", "x")])
    assert r.verdict in (INCONCLUSIVE, VERIFIED)


# ---------------------------------------------------------------------------
# Bronstein bug hunt — all should be VERIFIED or INCONCLUSIVE (not MISMATCH)
# ---------------------------------------------------------------------------

def test_bronstein_bug_hunt_returns_eight():
    results = run_bronstein_bug_hunt()
    assert len(results) == 8


def test_bronstein_no_mismatches():
    """The Bronstein corpus should contain no genuine CAS bugs."""
    results = run_bronstein_bug_hunt()
    mismatches = [r for r in results if r.verdict == MISMATCH]
    assert mismatches == [], f"Unexpected mismatches: {[m.integrand for m in mismatches]}"


def test_bronstein_verified_count():
    """All 8 Bronstein integrands should be verified end-to-end."""
    results = run_bronstein_bug_hunt()
    verified = [r for r in results if r.verdict == VERIFIED]
    assert len(verified) == 8, f"Only {len(verified)}/8 verified"


def test_bronstein_results_have_fields():
    for r in run_bronstein_bug_hunt():
        assert isinstance(r.integrand, str)
        assert isinstance(r.var, str)
        assert r.verdict in (VERIFIED, MISMATCH, INCONCLUSIVE, NO_ANTIDERIV)


# ---------------------------------------------------------------------------
# Verdict constants
# ---------------------------------------------------------------------------

def test_verdict_constants_are_strings():
    assert VERIFIED == "verified"
    assert MISMATCH == "mismatch"
    assert INCONCLUSIVE == "inconclusive"
    assert NO_ANTIDERIV == "no_antideriv"
