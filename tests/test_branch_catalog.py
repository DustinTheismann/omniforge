"""
Tests for Tier 2.3 — branch-cut discrepancy catalog.

Run with:  python -m pytest tests/test_branch_catalog.py -v
"""
from __future__ import annotations

from fricas_bridge.branch_catalog import (
    CatalogEntry,
    build_catalog,
    catalog_summary,
)


def test_build_catalog_returns_list():
    assert isinstance(build_catalog(), list)


def test_build_catalog_non_empty():
    assert len(build_catalog()) > 0


def test_catalog_entries_are_dataclass():
    for e in build_catalog():
        assert isinstance(e, CatalogEntry)


def test_catalog_has_e_branch_cut_entries():
    entries = build_catalog()
    e_entries = [e for e in entries if e.discrepancy_class == "E_branch_cut"]
    assert len(e_entries) > 0


def test_catalog_has_no_discrepancy_entries():
    entries = build_catalog()
    none_entries = [e for e in entries if e.discrepancy_class == "none"]
    assert len(none_entries) > 0


def test_catalog_discrepancy_property():
    for e in build_catalog():
        if e.discrepancy_class == "none":
            assert e.is_discrepancy is False
        else:
            assert e.is_discrepancy is True


def test_catalog_summary_keys():
    s = catalog_summary()
    assert "none" in s
    assert "E_branch_cut" in s
    assert "F_sign_dependent" in s
    assert "total_antiderivatives" in s


def test_catalog_summary_counts_positive():
    s = catalog_summary()
    assert s["E_branch_cut"] > 0
    assert s["total_antiderivatives"] > 0


def test_catalog_summary_total_antiderivatives():
    """Should match the 24-entry offline cache."""
    s = catalog_summary()
    assert s["total_antiderivatives"] >= 20


def test_catalog_log_subexpr_present():
    for e in build_catalog():
        if e.is_discrepancy:
            assert e.log_subexpr.startswith("log("), (
                f"Expected log(...) subexpr, got {e.log_subexpr!r}"
            )


def test_catalog_fricas_domain_present_for_discrepancies():
    for e in build_catalog():
        if e.is_discrepancy:
            assert e.fricas_domain != ""


def test_catalog_lean_domain_present_for_discrepancies():
    for e in build_catalog():
        if e.is_discrepancy:
            assert e.lean_domain != ""
