"""
Theorem count guard.

The number of kernel-verified theorems/lemmas in the integration lane is a
recurring liability: it appears in README.md and the architecture doc, and it
has been miscounted before (e.g. "19" and "31" both shipped while the true
count was 29). This guard parses the core Lean library files and asserts the
canonical per-file and total counts, so any drift breaks CI with a clear
message that points at the file and the docs that must be updated together.

Counts ONLY `theorem`/`lemma` declarations at the start of a line (after
optional whitespace). It deliberately does NOT count `def`/`noncomputable def`
— those are definitions, not proven statements, and conflating them is exactly
how the count drifted to 31.

If you add or remove a theorem, update CANONICAL below AND the two docs:
  - README.md  (Integration Lane bullet)
  - docs/PROOFFORGE_OMEGA_ARCHITECTURE.md  (Phase 1 roadmap row)
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
LEAN_DIR = REPO_ROOT / "fricas_bridge"

# Canonical per-file theorem/lemma counts for the core integration-lane library.
# This is the single source of truth referenced by README and the arch doc.
CANONICAL: dict[str, int] = {
    "CasAdjudication.lean":          10,
    "RischVerification.lean":         9,
    "RischAutoDischarge.lean":        8,
    "PartialFractionHasDerivAt.lean": 2,
    "Gf2Identity.lean":               2,   # gf2_and_or_identity + bool_and_or_identity
    "TseitinC5.lean":                 2,   # tseitin_c5_unsat + tseitin_c5_no_model
}
CANONICAL_TOTAL = 33

# theorem/lemma at line start (optional leading whitespace), word-boundary so
# `theorem_name` in prose/comments mid-line is never matched.
_DECL_RE = re.compile(r"^\s*(theorem|lemma)\b")


def _count_theorems(path: Path) -> int:
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if _DECL_RE.match(line):
            n += 1
    return n


def test_canonical_total_is_self_consistent():
    """The per-file table must sum to the advertised total."""
    assert sum(CANONICAL.values()) == CANONICAL_TOTAL


@pytest.mark.parametrize("filename,expected", sorted(CANONICAL.items()))
def test_per_file_theorem_count(filename: str, expected: int):
    path = LEAN_DIR / filename
    assert path.exists(), f"core Lean file missing: {path}"
    actual = _count_theorems(path)
    assert actual == expected, (
        f"{filename}: counted {actual} theorem/lemma decls, expected {expected}. "
        f"If this change is intentional, update CANONICAL in this file AND the "
        f"theorem count in README.md and docs/PROOFFORGE_OMEGA_ARCHITECTURE.md."
    )


def test_total_theorem_count():
    total = sum(_count_theorems(LEAN_DIR / f) for f in CANONICAL)
    assert total == CANONICAL_TOTAL, (
        f"Total kernel-verified theorem/lemma count is {total}, expected "
        f"{CANONICAL_TOTAL}. Update CANONICAL and both docs together."
    )


def test_no_sorry_in_core_libraries():
    """Guard the 'no sorry' claim alongside the count."""
    offenders = []
    for f in CANONICAL:
        text = (LEAN_DIR / f).read_text(encoding="utf-8")
        # Match `sorry` as a standalone token, not inside identifiers/comments words.
        if re.search(r"(^|\s)sorry(\s|$)", text):
            offenders.append(f)
    assert offenders == [], f"`sorry` found in core libraries: {offenders}"


def test_no_axiom_in_core_libraries():
    """Guard the 'no axiom' claim alongside the count."""
    offenders = []
    for f in CANONICAL:
        text = (LEAN_DIR / f).read_text(encoding="utf-8")
        if re.search(r"^\s*axiom\b", text, re.MULTILINE):
            offenders.append(f)
    assert offenders == [], f"`axiom` declaration found in core libraries: {offenders}"
