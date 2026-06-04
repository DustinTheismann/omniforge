"""
Evidence grader for ProofForge Ω.

Given a claim's checker_results, obligations, formal_targets, and flags,
computes the highest evidence class the claim is entitled to, applying all
upgrade gates and the EX_REFUTED override.

Key invariants:
  ``EX_REFUTED`` overrides everything.
  ``E7_FORMALLY_VERIFIED`` requires ``formal_verified == True`` on a checker
  result — it cannot be reached by LLM assertion.
  ``E8_CROSS_VERIFIED`` requires ≥2 independent formal kernel systems to each
  report ``formal_verified == True``. SAT/CAS/SMT corroboration is valuable
  and contributes to E6 but does not satisfy the E8 gate on its own.
"""
from __future__ import annotations

from typing import Any

from protocols.claim_protocol.types import EvidenceClass, ClaimFlag


# ---------------------------------------------------------------------------
# Checker family classification
# ---------------------------------------------------------------------------
# Each formal proof system gets its own unique family name so that
# Lean+Coq counts as two independent formal anchors (→ E8), while
# Lean alone or cake_lpr alone counts as one (→ E7).

_FORMAL_CHECKERS: dict[str, str] = {
    "lean4":    "lean4",
    "lean":     "lean4",
    "coq":      "coq",
    "rocq":     "coq",
    "isabelle": "isabelle",
    "agda":     "agda",
    # cake_lpr: CakeML binary whose LRAT-checking logic is proven correct in
    # HOL4. Carries the same formal_verified guarantee as a proof kernel.
    "cake_lpr": "cake_lpr",
}
_FORMAL_FAMILIES = frozenset(_FORMAL_CHECKERS.values())

_CAS_CHECKERS    = frozenset({"fricas", "sympy", "maxima", "sage", "mathematica"})
_SMT_CHECKERS    = frozenset({"z3", "cvc5", "cvc4"})
_SAT_CHECKERS    = frozenset({
    "cadical", "kissat", "minisat",
    # SAT proof checkers (not solvers, but SAT-domain verification tools)
    "drat-trim", "lrat-trim",
})
_NUMERIC_CHECKERS= frozenset({"property_test", "interval_arithmetic", "monte_carlo",
                               "differential_test", "pytest", "hypothesis"})
_REPRO_CHECKERS  = frozenset({"docker_repro", "nix_repro", "pytest_repro", "notebook_repro"})


def _checker_family(checker_name: str) -> str:
    name = checker_name.lower()
    if name in _FORMAL_CHECKERS:  return _FORMAL_CHECKERS[name]
    if name in _CAS_CHECKERS:     return "cas"
    if name in _SMT_CHECKERS:     return "smt"
    if name in _SAT_CHECKERS:     return "sat"
    if name in _NUMERIC_CHECKERS: return "numeric"
    if name in _REPRO_CHECKERS:   return "repro"
    return "other"


# ---------------------------------------------------------------------------
# Refutation detectors
# ---------------------------------------------------------------------------

def _is_refuted(
    checker_results: list[dict],
    formal_targets: list[dict],
    flags: list[str],
    obligations: list[dict],
) -> bool:
    for r in checker_results:
        if r.get("result") in ("refuted", "failed") and r.get("formal_verified", False):
            return True
    for t in formal_targets:
        if t.get("status") == "failed":
            return True
    for o in obligations:
        if o.get("kind") == "counterexample_search" and o.get("status") == "passed":
            return True
    return False


# ---------------------------------------------------------------------------
# Grade function
# ---------------------------------------------------------------------------

def grade(claim: dict[str, Any]) -> EvidenceClass:
    """
    Compute and return the evidence class for *claim*.

    Does NOT mutate the claim dict — caller is responsible for writing it back.
    """
    checker_results: list[dict] = claim.get("checker_results", [])
    formal_targets:  list[dict] = claim.get("formal_targets", [])
    obligations:     list[dict] = claim.get("obligations", [])
    assumptions:     list[dict] = claim.get("assumptions", [])
    flags:           list[str]  = claim.get("flags", [])
    source:          dict       = claim.get("source", {})

    # ── Refutation check (always wins) ──────────────────────────────────────
    if _is_refuted(checker_results, formal_targets, flags, obligations):
        return EvidenceClass.EX_REFUTED

    # ── E0: always passes ───────────────────────────────────────────────────
    level = 0

    # ── E1: source populated ────────────────────────────────────────────────
    if source.get("kind") and source.get("name"):
        level = max(level, 1)

    # ── E2: schema-valid (assumed if we got here; caller must pre-validate) ─
    level = max(level, 2)

    # ── E3: at least one obligation has been run ─────────────────────────────
    if any(o.get("status") not in ("pending", None) for o in obligations):
        level = max(level, 3)

    # ── E4: reproduction passed ──────────────────────────────────────────────
    repro_passed = any(
        r.get("result") in ("passed", "supported")
        and _checker_family(r.get("checker", "")) == "repro"
        for r in checker_results
    )
    if repro_passed:
        level = max(level, 4)

    # ── E5: numeric checker passed ───────────────────────────────────────────
    numeric_passed = any(
        r.get("result") in ("passed", "supported")
        and _checker_family(r.get("checker", "")) == "numeric"
        for r in checker_results
    )
    if numeric_passed:
        level = max(level, 5)

    # ── E6: CAS or SMT checker passed ────────────────────────────────────────
    symbolic_passed = any(
        r.get("result") in ("passed", "supported")
        and _checker_family(r.get("checker", "")) in ("cas", "smt", "sat")
        for r in checker_results
    )
    if symbolic_passed:
        level = max(level, 6)

    # ── E7: formal checker verified ──────────────────────────────────────────
    # INVARIANT: formal_verified must be explicitly True. LLM-generated proofs
    # must NOT set this flag — only the Lean/Coq kernel output may.
    formal_verified = any(
        r.get("formal_verified") is True
        and r.get("result") == "passed"
        for r in checker_results
    ) and any(
        t.get("status") == "proved"
        for t in formal_targets
    )
    if formal_verified:
        level = max(level, 7)

    # ── E8: cross-verified by ≥2 independent formal kernel systems ──────────
    # Requires two distinct proof systems (lean4, coq, isabelle, cake_lpr, …)
    # to each independently report formal_verified=True. SAT/CAS/SMT is
    # valuable corroboration (→ E6) but does not satisfy this gate.
    formal_passing_systems = {
        _checker_family(r.get("checker", ""))
        for r in checker_results
        if r.get("formal_verified") is True
        and r.get("result") == "passed"
        and _checker_family(r.get("checker", "")) in _FORMAL_FAMILIES
    }
    if len(formal_passing_systems) >= 2 and level >= 7:
        level = max(level, 8)

    # ── E9: cross-method (≥2 formal families AND ≥2 distinct formal methods) ─
    # Strictly stronger than E8: two formal kernel systems must each report
    # formal_verified=True, AND they must use two distinct verification methods
    # (e.g. differentiation ≠ sat_refutation). A systematic error in one method's
    # encoding is caught by the orthogonal method.
    formal_methods = {
        r.get("method", "")
        for r in checker_results
        if r.get("formal_verified") is True
        and r.get("result") == "passed"
        and _checker_family(r.get("checker", "")) in _FORMAL_FAMILIES
        and r.get("method")  # skip unset/empty method
    }
    if len(formal_passing_systems) >= 2 and len(formal_methods) >= 2 and level >= 8:
        level = max(level, 9)

    # ── E10: adversarially hardened ──────────────────────────────────────────
    falsifier_ran = any(
        o.get("kind") == "counterexample_search"
        and o.get("status") == "failed"   # falsifier FAILED to find counterexample
        for o in obligations
    )
    no_disagreement = ClaimFlag.CHECKER_DISAGREEMENT.value not in flags
    if level >= 9 and falsifier_ran and no_disagreement:
        level = max(level, 10)

    _MAP = [
        EvidenceClass.E0_RAW_CLAIM,
        EvidenceClass.E1_SOURCED,
        EvidenceClass.E2_PARSED,
        EvidenceClass.E3_EXECUTABLE,
        EvidenceClass.E4_REPRODUCED,
        EvidenceClass.E5_NUMERICALLY_SUPPORTED,
        EvidenceClass.E6_SYMBOLICALLY_SUPPORTED,
        EvidenceClass.E7_FORMALLY_VERIFIED,
        EvidenceClass.E8_CROSS_VERIFIED,
        EvidenceClass.E9_MULTI_METHOD,
        EvidenceClass.E10_ADVERSARIALLY_HARDENED,
        EvidenceClass.E11_FIELD_VALIDATED,
    ]
    return _MAP[min(level, 11)]


def downgrade(claim: dict[str, Any], reason: str) -> dict[str, Any]:
    """
    Downgrade claim to EX_REFUTED and add a note. Returns updated claim dict.
    """
    claim = dict(claim)
    claim["evidence_class"] = EvidenceClass.EX_REFUTED.value
    notes = claim.setdefault("metadata", {}).get("notes", "")
    claim["metadata"]["notes"] = f"{notes}\n[REFUTED] {reason}".strip()
    return claim
