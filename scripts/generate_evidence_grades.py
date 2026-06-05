#!/usr/bin/env python3
"""
Generate the canonical "evidence grade" block for the demonstrated claims, as
``min(grader_class, wiring_class)``.

WHY THIS EXISTS
---------------
The grader computes a claim's evidence class from its ``checker_results``'
``formal_verified`` flags. Those flags live in the claim JSON and can be
*asserted* there without the corresponding proof ever running in CI — that is
exactly how E9 once read "Demonstrated" while neither of its formal anchors
(``Gf2Identity`` in the Lean build, ``cake_lpr`` on the gf2 CNF) was built or
executed on push.

So printing ``grader.grade(claim)`` would faithfully re-render the overclaim
from the same flags that caused the bug — the keystroke removed, the lie
laundered through generation. To actually retire the failure mode the grade has
to be gated on a *wiring check* that can only ever LOWER it:

    effective = min(grader_class, wiring_class)

``wiring_class`` is the grade the claim earns when every formal anchor that is
NOT wired into CI has its ``formal_verified`` contribution stripped. The wiring
check reads the real repo — lakefile roots, the lean.yml sorry/axiom guard,
the coqc step in coq.yml, and the SAT-pipeline step/Make target that feeds
``cake_lpr`` a committed CNF — so removing any of that wiring drops the cell to
Candidate regardless of what the JSON asserts. Run against the original E9
state this generates Candidate; run against main today it generates E9.

WHAT "Demonstrated" MEANS HERE — AND WHAT IT DOES NOT
-----------------------------------------------------
A generated "Demonstrated" means **graded-and-wired**: the grader grants the
class AND every formal anchor it rests on is built/guarded and referenced by a
CI workflow. It does **not** assert that the anchor's step passed in *this* CI
run. A single GitHub Actions job cannot witness that sibling workflows
(lean.yml / coq.yml / ci.yml) executed; proving runtime co-execution would mean
restructuring CI into one gating pipeline. This guard deliberately claims only
the weaker, statically-checkable property — because the anti-overclaim guard
must not itself overclaim.

USAGE
-----
    python scripts/generate_evidence_grades.py            # print the block
    python scripts/generate_evidence_grades.py --write    # inject into CURRENT_STATUS.md
    python scripts/generate_evidence_grades.py --check     # exit 1 if doc diverges
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from protocols.claim_protocol.types import EvidenceClass          # noqa: E402
from protocols.evidence_protocol.grader import grade, _checker_family  # noqa: E402

STATUS_DOC = REPO_ROOT / "CURRENT_STATUS.md"
BEGIN_MARKER = "<!-- BEGIN GENERATED: evidence grades — DO NOT EDIT BY HAND -->"
END_MARKER = "<!-- END GENERATED: evidence grades -->"

# The demonstrated claims whose grade is gated. (claim path, rung label.)
CLAIMS: list[tuple[str, str]] = [
    ("protocols/claim_protocol/examples/unsat_000001.json",        "SAT lane"),
    ("protocols/claim_protocol/examples/cross_bronstein_003.json", "Integration (cross-prover)"),
    ("protocols/claim_protocol/examples/multimethod_000001.json",  "Cross-method (gf2 toy)"),
    ("protocols/claim_protocol/examples/tseitin_c5_000001.json",    "Cross-method (Tseitin C5)"),
]

# cake_lpr anchors are not bound to a committed file by the claim alone; map the
# claim's CNF to the (Make target, committed CNF) that feeds it through the
# cadical→drat-trim→lrat-trim→cake_lpr pipeline. Unknown CNF ⇒ not provably
# wired (conservative): a new cake_lpr claim is never auto-blessed.
_CAKE_PIPELINES: dict[str, tuple[str, str | None]] = {
    "gf2_tautology.cnf":      ("gf2",  "benches/multimethod/gf2_tautology.cnf"),
    "tseitin_c5.cnf":         ("tseitin", "benches/multimethod/tseitin_c5.cnf"),
    "unsat_contradiction.cnf": ("demo", None),  # demo runs the three-checker pipeline
}


# ---------------------------------------------------------------------------
# Repo readers
# ---------------------------------------------------------------------------

def _read(rel: str) -> str:
    p = REPO_ROOT / rel
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _make_recipe(makefile: str, target: str) -> str | None:
    """Return the recipe body for ``target:`` in a Makefile, or None if absent."""
    lines = makefile.splitlines()
    out: list[str] = []
    capturing = False
    target_re = re.compile(r"^" + re.escape(target) + r"\s*:")
    for line in lines:
        if capturing:
            if line.startswith((" ", "\t")):
                out.append(line)
                continue
            if line.strip() == "":
                continue
            break  # next unindented line ends the recipe
        if target_re.match(line):
            capturing = True
    return "\n".join(out) if capturing else None


def _any_workflow_invokes_make(target: str) -> bool:
    wf_dir = REPO_ROOT / ".github" / "workflows"
    token = re.compile(r"\bmake\s+" + re.escape(target) + r"\b")
    for wf in wf_dir.glob("*.yml"):
        if token.search(wf.read_text(encoding="utf-8")):
            return True
    return False


# ---------------------------------------------------------------------------
# Wiring oracle — returns True iff a checker_result's anchor is wired into CI
# ---------------------------------------------------------------------------

def _lean_anchor_wired(lean_file: str) -> bool:
    """Lean anchor is wired iff its module is a lakefile lib root AND the file is
    in lean.yml's sorry/axiom VERIFIED_ROOTS guard (built + guarded)."""
    module = Path(lean_file).stem
    root_re = re.compile(r"roots\s*:=\s*#\[`" + re.escape(module) + r"\]")
    in_build = bool(root_re.search(_read("fricas_bridge/lakefile.lean")))
    in_guard = lean_file in _read(".github/workflows/lean.yml")
    return in_build and in_guard


def _coq_anchor_wired(coq_file: str) -> bool:
    """Coq anchor is wired iff coq.yml's coqc step references the .v file."""
    return Path(coq_file).name in _read(".github/workflows/coq.yml")


def _cake_lpr_anchor_wired(claim: dict) -> bool:
    """cake_lpr anchor is wired iff the claim's CNF is fed through the SAT
    pipeline by a Make target that a workflow invokes (and, when the CNF is a
    committed benchmark, that file exists)."""
    cnf = (claim.get("inputs") or {}).get("cnf_file")
    binding = _CAKE_PIPELINES.get(cnf or "")
    if binding is None:
        return False
    target, committed_cnf = binding
    recipe = _make_recipe(_read("Makefile"), target)
    if recipe is None:
        return False
    if committed_cnf is not None:
        if committed_cnf not in recipe or not (REPO_ROOT / committed_cnf).exists():
            return False
    return _any_workflow_invokes_make(target)


def anchor_wired(checker_result: dict, claim: dict) -> bool:
    """Default wiring oracle for one formal checker_result of *claim*."""
    family = _checker_family(checker_result.get("checker", ""))
    artifact = checker_result.get("artifact", "") or ""
    if family == "lean4":
        return _lean_anchor_wired(artifact)
    if family == "coq":
        return _coq_anchor_wired(artifact)
    if family == "cake_lpr":
        return _cake_lpr_anchor_wired(claim)
    # Non-formal corroboration (cadical/drat-trim/…) is not an anchor; leave as-is.
    return True


WiredFn = Callable[[dict, dict], bool]


# ---------------------------------------------------------------------------
# Grade computation: effective = min(grader, wiring)
# ---------------------------------------------------------------------------

def _wiring_adjusted(claim: dict, wired_fn: WiredFn) -> dict:
    """Copy of *claim* with formal_verified stripped from unwired formal anchors."""
    adjusted = dict(claim)
    new_results = []
    for r in claim.get("checker_results", []):
        r = dict(r)
        if r.get("formal_verified") is True and not wired_fn(r, claim):
            r["formal_verified"] = False
        new_results.append(r)
    adjusted["checker_results"] = new_results
    return adjusted


def grades_for(
    claim: dict, wired_fn: WiredFn = anchor_wired
) -> tuple[EvidenceClass, EvidenceClass, EvidenceClass]:
    """Return (grader_class, wiring_class, effective) where effective is the
    lower of the two by ladder level."""
    grader_class = grade(claim)
    wiring_class = grade(_wiring_adjusted(claim, wired_fn))
    effective = grader_class if grader_class.level <= wiring_class.level else wiring_class
    return grader_class, wiring_class, effective


def _short(ec: EvidenceClass) -> str:
    return ec.value.split("_")[0]


def _status(effective: EvidenceClass) -> str:
    # These rows are formal-demonstration claims: graded-and-wired at >= E7 is a
    # genuine kernel demonstration; anything lower means an anchor isn't wired.
    return "✅ Demonstrated" if effective.level >= 7 else "🟡 Candidate"


def render_block(wired_fn: WiredFn = anchor_wired) -> str:
    rows = []
    for rel, rung in CLAIMS:
        claim = json.loads((REPO_ROOT / rel).read_text(encoding="utf-8"))
        g, w, eff = grades_for(claim, wired_fn)
        rows.append(
            f"| `{claim['claim_id']}` | {rung} | {_short(g)} | {_short(w)} "
            f"| {_short(eff)} | {_status(eff)} |"
        )
    lines = [
        BEGIN_MARKER,
        "<!-- regenerate: python scripts/generate_evidence_grades.py --write -->",
        "<!-- grade = min(grader, wiring). \"Demonstrated\" = grader grants the class"
        " AND every formal anchor is wired into CI (Lean: lakefile root + sorry/axiom"
        " guard; Coq: coqc step; cake_lpr: SAT-pipeline Make target on a committed CNF)."
        " It does NOT assert the step passed in this run — see"
        " scripts/generate_evidence_grades.py. -->",
        "",
        "| Claim | Rung | Grader | Wiring | Effective | Status |",
        "|-------|------|--------|--------|-----------|--------|",
        *rows,
        END_MARKER,
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Doc injection / check
# ---------------------------------------------------------------------------

def extract_committed_block(doc: str) -> str | None:
    if BEGIN_MARKER not in doc or END_MARKER not in doc:
        return None
    start = doc.index(BEGIN_MARKER)
    end = doc.index(END_MARKER) + len(END_MARKER)
    return doc[start:end]


def write_block() -> None:
    doc = STATUS_DOC.read_text(encoding="utf-8")
    block = render_block()
    if BEGIN_MARKER in doc and END_MARKER in doc:
        start = doc.index(BEGIN_MARKER)
        end = doc.index(END_MARKER) + len(END_MARKER)
        doc = doc[:start] + block + doc[end:]
    else:
        raise SystemExit(
            f"markers not found in {STATUS_DOC.name}; add an anchor first:\n"
            f"{BEGIN_MARKER}\n{END_MARKER}"
        )
    STATUS_DOC.write_text(doc, encoding="utf-8")
    print(f"wrote evidence-grade block into {STATUS_DOC.name}")


def check() -> int:
    committed = extract_committed_block(STATUS_DOC.read_text(encoding="utf-8"))
    expected = render_block()
    if committed is None:
        print(f"FAIL: generated block markers not found in {STATUS_DOC.name}")
        return 1
    if committed.strip() != expected.strip():
        print(
            "FAIL: CURRENT_STATUS.md evidence-grade block is stale.\n"
            "Run: python scripts/generate_evidence_grades.py --write\n"
            "--- committed ---\n" + committed + "\n--- expected ---\n" + expected
        )
        return 1
    print("OK: evidence-grade block matches min(grader, wiring).")
    return 0


def main(argv: list[str]) -> int:
    if "--write" in argv:
        write_block()
        return 0
    if "--check" in argv:
        return check()
    print(render_block())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
