"""
Tests for Tier 5.5 — CAS Corpus.

Run with:  python -m pytest tests/test_cas_corpus.py -v
"""
from __future__ import annotations

import pytest

from fricas_bridge.cas_corpus import (
    CorpusEntry,
    load_corpus,
    load_bronstein_set,
    load_disagreement_candidates,
)


def test_load_corpus_returns_list():
    corpus = load_corpus()
    assert isinstance(corpus, list)
    assert len(corpus) >= 35


def test_corpus_entries_are_dataclasses():
    for e in load_corpus():
        assert isinstance(e, CorpusEntry)
        assert e.integrand
        assert e.var
        assert e.category


def test_bronstein_set_has_eight():
    assert len(load_bronstein_set()) == 8


def test_bronstein_set_all_bronstein_category():
    for e in load_bronstein_set():
        assert e.category == "BRONSTEIN"


def test_bronstein_set_has_1_over_x():
    entries = load_bronstein_set()
    assert any("1/x" == e.integrand for e in entries)


def test_bronstein_set_has_form_disagree_note():
    """bronstein_005 and bronstein_009 are documented form-disagree cases."""
    entries = load_bronstein_set()
    flagged = [e for e in entries if "FORM_DISAGREE" in e.notes]
    assert len(flagged) == 2


def test_bronstein_set_uses_x_var():
    for e in load_bronstein_set():
        assert e.var == "x"


def test_corpus_has_radical_category():
    corpus = load_corpus()
    cats = {e.category for e in corpus}
    assert "RADICAL" in cats


def test_corpus_has_non_elementary():
    corpus = load_corpus()
    ne = [e for e in corpus if e.category == "NON_ELEMENTARY"]
    assert len(ne) >= 3
    assert any("exp" in e.integrand for e in ne)


def test_corpus_has_gaussian():
    corpus = load_corpus()
    assert any("exp(-x^2)" in e.integrand for e in corpus)


def test_corpus_has_sine_integral():
    corpus = load_corpus()
    assert any("sin(x)/x" in e.integrand for e in corpus)


def test_disagreement_candidates_non_empty():
    cands = load_disagreement_candidates()
    assert len(cands) >= 10


def test_disagreement_candidates_include_radicals():
    cands = load_disagreement_candidates()
    cats = {e.category for e in cands}
    assert "RADICAL" in cats


def test_corpus_all_unique_integrands_per_var():
    corpus = load_corpus()
    seen: set[tuple[str, str]] = set()
    for e in corpus:
        key = (e.integrand, e.var)
        assert key not in seen, f"Duplicate: {key}"
        seen.add(key)


def test_bronstein_set_is_subset_of_corpus():
    corpus_keys = {(e.integrand, e.var) for e in load_corpus()}
    for e in load_bronstein_set():
        assert (e.integrand, e.var) in corpus_keys
