"""
Tier 2.3 — Branch-cut discrepancy catalog generator.

Runs branch_audit over all entries in the FriCAS offline cache and
builds a catalog of every log(...) subexpression, annotated with its
discrepancy class and domain conditions.

Public API
----------
CatalogEntry                    dataclass
build_catalog()                 → list[CatalogEntry]
catalog_summary()               → dict   (counts by class)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fricas_bridge.branch_audit import branch_audit, BranchDiscrepancy
from fricas_bridge.offline_cache import load_offline_cache


@dataclass
class CatalogEntry:
    integrand: str
    antiderivative: str
    label: str
    log_subexpr: str
    arg: str
    discrepancy_class: str   # "none" | "E_branch_cut" | "F_sign_dependent"
    fricas_domain: str
    lean_domain: str

    @property
    def is_discrepancy(self) -> bool:
        return self.discrepancy_class != "none"


def build_catalog() -> list[CatalogEntry]:
    """Build the catalog from the full offline cache."""
    raw_cache = load_offline_cache()
    # The cache has a wrapper structure: {"description": ..., "entries": {...}, ...}
    cache_entries = raw_cache.get("entries", raw_cache)
    entries: list[CatalogEntry] = []

    for record in cache_entries.values():
        if not isinstance(record, dict):
            continue
        antideriv = record.get("antiderivative", "")
        integrand = record.get("integrand", "")
        label = record.get("label", "")

        if not antideriv:
            continue

        discrepancies = branch_audit(antideriv)
        if not discrepancies:
            # Add a single no-discrepancy marker for the complete picture
            entries.append(CatalogEntry(
                integrand=integrand,
                antiderivative=antideriv,
                label=label,
                log_subexpr="(none)",
                arg="",
                discrepancy_class="none",
                fricas_domain="",
                lean_domain="",
            ))
        else:
            for d in discrepancies:
                entries.append(CatalogEntry(
                    integrand=integrand,
                    antiderivative=antideriv,
                    label=label,
                    log_subexpr=d.antideriv_subexpr,
                    arg=d.arg,
                    discrepancy_class=d.discrepancy_class,
                    fricas_domain=d.fricas_domain,
                    lean_domain=d.lean_domain,
                ))

    return entries


def catalog_summary() -> dict:
    """Return count of entries by discrepancy class."""
    entries = build_catalog()
    summary: dict[str, int] = {"none": 0, "E_branch_cut": 0, "F_sign_dependent": 0}
    for e in entries:
        summary[e.discrepancy_class] = summary.get(e.discrepancy_class, 0) + 1
    summary["total_log_terms"] = sum(
        1 for e in entries if e.discrepancy_class != "none"
    ) + sum(1 for e in entries if e.discrepancy_class == "none" and e.log_subexpr != "(none)")
    summary["total_antiderivatives"] = len({e.antiderivative for e in entries})
    return summary
