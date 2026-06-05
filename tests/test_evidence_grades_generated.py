"""
Evidence-grade generation guard.

This is the structural fix for the project's defining failure mode: a claim
graded "Demonstrated" whose formal anchors are not actually wired into CI (the
E9 episode). It guards two things:

1. The committed evidence-grade block in CURRENT_STATUS.md equals a fresh
   regeneration — the same doc-equals-generated pattern as the theorem-count
   guard. A human cannot hand-type "Demonstrated" ahead of the evidence,
   because the cell is generated and CI fails on divergence.

2. The grade is min(grader, wiring), and the wiring term can only LOWER it.
   This is the property that makes the generation a fix rather than a
   relocation of the bug: printing grader.grade(claim) alone would faithfully
   re-render an overclaim from asserted flags. We assert that with anchors
   unwired, every demonstrated claim drops below E7 (Candidate).
"""
from __future__ import annotations

import json
from pathlib import Path

import scripts.generate_evidence_grades as gen
from protocols.claim_protocol.types import EvidenceClass

REPO_ROOT = Path(__file__).parent.parent


def test_committed_block_matches_generation():
    """CURRENT_STATUS.md's generated block must equal a fresh render."""
    doc = (REPO_ROOT / "CURRENT_STATUS.md").read_text(encoding="utf-8")
    committed = gen.extract_committed_block(doc)
    assert committed is not None, (
        "evidence-grade block markers not found in CURRENT_STATUS.md"
    )
    assert committed.strip() == gen.render_block().strip(), (
        "CURRENT_STATUS.md evidence-grade block is stale. Regenerate with:\n"
        "  python scripts/generate_evidence_grades.py --write"
    )


def test_effective_is_min_not_grader_echo():
    """With every anchor unwired, the effective grade must fall below E7 for
    each demonstrated claim — proving the wiring term gates the grader rather
    than echoing it. This is precisely the original-E9 state."""
    unwired = lambda cr, claim: False  # noqa: E731
    for rel, _rung in gen.CLAIMS:
        claim = json.loads((REPO_ROOT / rel).read_text(encoding="utf-8"))
        grader_class, wiring_class, effective = gen.grades_for(claim, unwired)
        assert grader_class.level >= 7, (
            f"{rel}: expected a formal demonstration (grader >= E7), got {grader_class.value}"
        )
        assert effective.level < 7, (
            f"{rel}: unwired anchors must drop the effective grade below E7, "
            f"got {effective.value} (gate is not lowering the grade)"
        )
        assert effective.level <= grader_class.level, "effective must never exceed grader"


def test_wired_state_matches_grader():
    """On the current repo state every demonstrated claim is fully wired, so the
    wiring term does not lower it and effective == grader."""
    for rel, _rung in gen.CLAIMS:
        claim = json.loads((REPO_ROOT / rel).read_text(encoding="utf-8"))
        grader_class, wiring_class, effective = gen.grades_for(claim)
        assert effective == grader_class, (
            f"{rel}: effective {effective.value} != grader {grader_class.value} — "
            f"an anchor is no longer wired into CI (wiring={wiring_class.value})"
        )
        assert effective.level >= 7


def test_unwiring_an_anchor_is_detected():
    """A targeted check: if the Lean anchor for the E9 claim were not a lakefile
    root, the cell would drop to Candidate. Simulated via the oracle so it needs
    no repo mutation."""
    mm = json.loads(
        (REPO_ROOT / "protocols/claim_protocol/examples/multimethod_000001.json").read_text()
    )

    def lean_unwired(cr, claim):
        if cr.get("checker") in ("lean4", "lean"):
            return False
        return gen.anchor_wired(cr, claim)

    _g, _w, effective = gen.grades_for(mm, lean_unwired)
    # Losing one of the two formal families drops E9 below the E8 gate.
    assert effective.level < EvidenceClass.E8_CROSS_VERIFIED.level
