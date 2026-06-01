"""
ProofForge Ω — Obligation Protocol (Tier 4.1).

An *obligation* is a discharged-or-pending proof requirement linking a claim to
the checker that decides it.  Where the claim protocol says *what* is asserted
and the evidence protocol says *how strongly* it is supported, the obligation
protocol records the concrete proof tasks and their outcomes — the bridge
between a claim and a kernel.

Public API
----------
Obligation                      dataclass (one proof task + outcome)
ObligationStatus                Enum: pending|discharged|failed|refuted
obligations_for_claim(claim)    → list[Obligation]   (derive from a claim dict)
build_obligation_graph(claims)  → dict               (claims → obligations → runpacks)
verify_obligation_artifact(ob)  → bool               (recompute discharge_hash)
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class ObligationStatus(str, Enum):
    PENDING    = "pending"
    DISCHARGED = "discharged"
    FAILED     = "failed"
    REFUTED    = "refuted"


@dataclass
class Obligation:
    """A single proof requirement attached to a claim."""
    obligation_id: str            # "ob.pf.integral.bronstein_001.deriv"
    claim_id: str
    statement: str                # the Lean goal text
    checker: str                  # "lean4:v4.30.0 + mathlib:v4.30.0"
    status: str = ObligationStatus.PENDING.value
    discharge_artifact: Optional[str] = None   # path to the .lean proof
    discharge_hash: Optional[str] = None       # sha256 of the artifact bytes
    runpack_id: Optional[str] = None           # links to the reproducibility capsule

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def is_discharged(self) -> bool:
        return self.status == ObligationStatus.DISCHARGED.value


# ---------------------------------------------------------------------------
# Derivation: claim → obligations
# ---------------------------------------------------------------------------

_DEFAULT_CHECKER = "lean4:v4.30.0 + mathlib:v4.30.0"


def obligations_for_claim(claim: dict) -> list[Obligation]:
    """
    Derive the obligation(s) a claim implies from its formal_targets.

    Each formal_target with a Lean statement becomes one obligation whose
    statement is the target's statement_text and whose checker is the formal
    backend named in the target (default Lean 4 + Mathlib).
    """
    claim_id = claim.get("claim_id") or claim.get("id") or "unknown"
    targets = claim.get("formal_targets", [])
    obligations: list[Obligation] = []

    for i, tgt in enumerate(targets):
        backend = tgt.get("backend") or tgt.get("prover") or "lean4"
        checker = _DEFAULT_CHECKER if backend.lower().startswith("lean") else backend
        stmt = tgt.get("statement_text", "")
        suffix = tgt.get("name") or f"target{i}"
        obligations.append(Obligation(
            obligation_id=f"ob.{claim_id}.{suffix}",
            claim_id=claim_id,
            statement=stmt,
            checker=checker,
            status=ObligationStatus.PENDING.value,
        ))

    if not obligations:
        # A claim with no formal target still implies a trivial parse obligation.
        obligations.append(Obligation(
            obligation_id=f"ob.{claim_id}.parse",
            claim_id=claim_id,
            statement=claim.get("statement_text", ""),
            checker="parser",
        ))
    return obligations


# ---------------------------------------------------------------------------
# Artifact verification
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_obligation_artifact(ob: Obligation, *, root: Optional[Path] = None) -> bool:
    """
    Return True iff the obligation is discharged and its artifact on disk hashes
    to the recorded discharge_hash.  A pending/failed obligation returns False.
    """
    if not ob.is_discharged or not ob.discharge_artifact or not ob.discharge_hash:
        return False
    base = root if root is not None else _REPO_ROOT
    artifact = (base / ob.discharge_artifact).resolve()
    if not artifact.exists():
        return False
    return _sha256_file(artifact) == ob.discharge_hash


# ---------------------------------------------------------------------------
# Obligation graph
# ---------------------------------------------------------------------------

def build_obligation_graph(claims: list[dict]) -> dict:
    """
    Build a JSON-serialisable graph linking claims → obligations → runpacks.

    Returns {"obligations": [...], "by_claim": {claim_id: [obligation_id, ...]}}.
    """
    all_obs: list[dict] = []
    by_claim: dict[str, list[str]] = {}
    for claim in claims:
        obs = obligations_for_claim(claim)
        cid = obs[0].claim_id if obs else "unknown"
        by_claim[cid] = [o.obligation_id for o in obs]
        all_obs.extend(o.to_dict() for o in obs)
    return {"obligations": all_obs, "by_claim": by_claim}


def discharge(
    ob: Obligation,
    *,
    artifact: str,
    runpack_id: Optional[str] = None,
    root: Optional[Path] = None,
) -> Obligation:
    """
    Mark an obligation discharged against an artifact on disk, recording the
    artifact's SHA-256.  Returns a new Obligation (does not mutate in place).
    """
    base = root if root is not None else _REPO_ROOT
    path = (base / artifact).resolve()
    h = _sha256_file(path) if path.exists() else None
    return Obligation(
        obligation_id=ob.obligation_id,
        claim_id=ob.claim_id,
        statement=ob.statement,
        checker=ob.checker,
        status=ObligationStatus.DISCHARGED.value if h else ObligationStatus.FAILED.value,
        discharge_artifact=artifact,
        discharge_hash=h,
        runpack_id=runpack_id,
    )
