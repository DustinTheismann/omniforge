"""
ProofForge Ω — Claim Transmutation Engine (Tier 4.2).

The orchestrator that makes ProofForge *active* rather than a static schema.
``transmute`` takes a claim dict, derives its obligations, dispatches them to
checkers (offline: using the recorded checker_results), grades the evidence,
and returns the assembled TransmutedClaim.

This deliberately does NOT spawn live provers: in the build sandbox it consumes
the claim's recorded ``checker_results`` as the dispatch outcome, which is what
lets the 9 committed Risch claims reproduce their E7 grades end-to-end without a
Lean toolchain.  An online mode (live dispatch) is a drop-in replacement for
``_dispatch``.

Public API
----------
transmute(claim)                → TransmutedClaim
transmute_all(claims)           → list[TransmutedClaim]
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from protocols.evidence_protocol.grader import grade
from protocols.obligation_protocol import (
    Obligation,
    ObligationStatus,
    obligations_for_claim,
)


@dataclass
class ObligationResult:
    obligation: Obligation
    status: str                  # discharged|failed|pending
    checker_result: Optional[dict] = None


@dataclass
class TransmutedClaim:
    claim_id: str
    obligations: list[Obligation]
    results: list[ObligationResult]
    evidence_class: str
    n_discharged: int

    @property
    def all_discharged(self) -> bool:
        return self.n_discharged == len(self.obligations) and self.obligations != []


# ---------------------------------------------------------------------------
# Dispatch — offline (recorded) by default
# ---------------------------------------------------------------------------

def _dispatch_offline(ob: Obligation, claim: dict) -> ObligationResult:
    """
    Resolve an obligation from the claim's recorded checker_results.

    A formal checker_result with formal_verified=True and result=passed marks
    the obligation discharged.
    """
    for r in claim.get("checker_results", []):
        checker = str(r.get("checker", "")).lower()
        if checker.startswith("lean") or checker in ("coq", "rocq", "isabelle"):
            if r.get("result") == "passed" and r.get("formal_verified") is True:
                return ObligationResult(ob, ObligationStatus.DISCHARGED.value, r)
    # No formal pass on record → pending
    return ObligationResult(ob, ObligationStatus.PENDING.value, None)


DispatchFn = Callable[[Obligation, dict], ObligationResult]


# ---------------------------------------------------------------------------
# Transmute
# ---------------------------------------------------------------------------

def transmute(claim: dict, *, dispatch: Optional[DispatchFn] = None) -> TransmutedClaim:
    """
    Run a claim through the obligation pipeline and grade the result.

    The evidence class is computed by the existing grader over the claim dict,
    so a claim that records a formal_verified Lean pass grades E7 (or higher if
    cross-verified), exactly as the committed claims do.
    """
    dispatch = dispatch or _dispatch_offline
    claim_id = claim.get("claim_id") or claim.get("id") or "unknown"

    obligations = obligations_for_claim(claim)
    results = [dispatch(ob, claim) for ob in obligations]

    # Reflect dispatch outcomes back onto the obligation objects.
    resolved: list[Obligation] = []
    for res in results:
        ob = res.obligation
        resolved.append(Obligation(
            obligation_id=ob.obligation_id,
            claim_id=ob.claim_id,
            statement=ob.statement,
            checker=ob.checker,
            status=res.status,
        ))

    evidence = grade(claim)
    n_discharged = sum(1 for r in results if r.status == ObligationStatus.DISCHARGED.value)

    return TransmutedClaim(
        claim_id=claim_id,
        obligations=resolved,
        results=results,
        evidence_class=evidence.value,
        n_discharged=n_discharged,
    )


def transmute_all(claims: list[dict], *, dispatch: Optional[DispatchFn] = None) -> list[TransmutedClaim]:
    return [transmute(c, dispatch=dispatch) for c in claims]
