"""
Tests for Tier 7 — AlphaIntegrate discovery loop.

Run with:  python -m pytest tests/test_discovery.py -v
"""
from __future__ import annotations

import pytest

from fricas_bridge.discovery import (
    DiscoveryResult,
    novelty_score,
    discover,
    discover_from_generator,
)


# ---------------------------------------------------------------------------
# novelty_score
# ---------------------------------------------------------------------------

def test_novelty_score_known_returns_zero():
    """1/x is in both FriCAS and SymPy caches → score 0."""
    assert novelty_score("1/x") == 0


def test_novelty_score_unknown_returns_two():
    """Totally unknown integrand → neither cache has it → score 2."""
    assert novelty_score("mystery_fn(x)") == 2


def test_novelty_score_returns_int():
    score = novelty_score("x/(x^2+1)")
    assert isinstance(score, int)
    assert 0 <= score <= 3


# ---------------------------------------------------------------------------
# discover single item
# ---------------------------------------------------------------------------

def test_discover_returns_list():
    results = discover([("1/x", "x")])
    assert isinstance(results, list)
    assert len(results) == 1


def test_discover_result_is_dataclass():
    [r] = discover([("1/x", "x")])
    assert isinstance(r, DiscoveryResult)


def test_discover_known_is_not_novel():
    [r] = discover([("1/x", "x")])
    assert r.novelty_score == 0
    assert r.is_novel is False
    assert r.is_disagreement is False


def test_discover_unknown_is_novel():
    [r] = discover([("mystery_fn(x)", "x")])
    assert r.is_novel is True


def test_discover_result_fields():
    [r] = discover([("1/x", "x")])
    assert r.integrand == "1/x"
    assert r.var == "x"
    assert r.fricas_result is not None
    assert r.sympy_result is not None
    assert isinstance(r.agreement, str)


# ---------------------------------------------------------------------------
# discover multiple items
# ---------------------------------------------------------------------------

def test_discover_multiple():
    pairs = [("1/x", "x"), ("x/(x^2+1)", "x"), ("1/(x^2+2*x+2)", "x")]
    results = discover(pairs)
    assert len(results) == 3
    assert all(isinstance(r, DiscoveryResult) for r in results)


def test_discover_bronstein_all_known():
    bronstein = [
        ("1/x", "x"),
        ("x/(x^2+1)", "x"),
        ("2*x/(1+x^4)", "x"),
        ("(x+1)/(x*(x+2))", "x"),
        ("1/(x^2+2*x+2)", "x"),
        ("x/(x^2-4)", "x"),
        ("1/(x*(x+1)*(x+2))", "x"),
    ]
    results = discover(bronstein)
    known = [r for r in results if r.novelty_score == 0]
    assert len(known) == len(bronstein), (
        f"Expected all known; novel: {[r.integrand for r in results if r.is_novel]}"
    )


# ---------------------------------------------------------------------------
# discover_from_generator
# ---------------------------------------------------------------------------

def test_discover_from_generator_returns_list():
    results = discover_from_generator()
    assert isinstance(results, list)
    assert len(results) > 0


def test_discover_from_generator_has_results():
    results = discover_from_generator()
    assert len(results) >= 10


def test_discover_from_generator_all_have_integrand():
    for r in discover_from_generator():
        assert r.integrand != ""
        assert r.var == "x"


def test_discover_from_generator_no_disagreements():
    """The built-in generator should not produce cross-CAS disagreements
    since the caches are consistent."""
    results = discover_from_generator()
    disagreements = [r for r in results if r.is_disagreement]
    assert disagreements == [], f"Unexpected disagreements: {[d.integrand for d in disagreements]}"
