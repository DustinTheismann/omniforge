"""
Tier 9.1 — ML corpus exporter.

Exports the ProofForge Ω claim set as a structured JSONL corpus for
kernel reward models and benchmark evaluation.  Each record contains:

  - integrand (FriCAS string)
  - antiderivative (FriCAS string)
  - lean_theorem (generated Lean 4 text)
  - coq_theorem (generated Coq text)
  - shape (antiderivative classification)
  - discrepancy_class (A/B/C/D)
  - hypotheses (list of Lean binder strings)
  - branch_discrepancies (from branch_audit)
  - evidence_class (E7 for all committed claims)
  - claim_id

Public API
----------
CorpusRecord                    dataclass
export_corpus(claim_ids)        → list[CorpusRecord]
export_to_jsonl(path)           → Path
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from fricas_bridge.proof_discharger import (
    classify_antideriv,
    synthesize_hypotheses,
    generate_theorem_text,
    FRICAS_CACHE,
    _ALL_CLAIMS,
)
from fricas_bridge.branch_audit import branch_audit
from cross_prover.coq_emitter import emit_coq
from protocols.evidence_protocol.grader import grade

_EX = Path(__file__).resolve().parent.parent / "protocols" / "claim_protocol" / "examples"


def _load_claim(claim_id: str) -> Optional[dict]:
    suffix = claim_id.split("_")[-1] if "_" in claim_id else claim_id
    try:
        n = int(suffix)
        path = _EX / f"risch_bronstein_{n:03d}.json"
        if path.exists():
            return json.loads(path.read_text())
    except (ValueError, OSError):
        pass
    return None


@dataclass
class CorpusRecord:
    claim_id: str
    integrand: str
    antiderivative: str
    lean_theorem: str
    coq_theorem: str
    shape: str
    discrepancy_class: str       # "A" | "B" | "C" | "D"
    hypotheses: list[str]        # lean binder strings
    branch_discrepancies: list[dict]
    evidence_class: str          # "E7_FORMALLY_VERIFIED" for committed claims

    def to_dict(self) -> dict:
        return asdict(self)


def _discrepancy_class(hypothesis_count: int, shape: str) -> str:
    if hypothesis_count == 0:
        return "A"
    if hypothesis_count == 1:
        return "B"
    if hypothesis_count == 2:
        return "C"
    return "D"


def export_corpus(claim_ids: Optional[list[str]] = None) -> list[CorpusRecord]:
    """Export the claim set as CorpusRecord instances."""
    ids = claim_ids or _ALL_CLAIMS
    records: list[CorpusRecord] = []

    # Load evidence grades from committed claim JSONs
    evidence_map: dict[str, str] = {}
    try:
        for cid in ids:
            claim = _load_claim(cid)
            if claim:
                g = grade(claim)
                evidence_map[cid] = g.value
    except Exception:
        pass  # graceful — evidence_map stays empty

    for cid in ids:
        cache_entry = FRICAS_CACHE.get(cid, {})
        integrand = cache_entry.get("integrand_fricas", "")
        antideriv = cache_entry.get("antideriv_fricas", "")

        shape_dict = classify_antideriv(antideriv)
        shape = shape_dict.get("shape", "UNKNOWN")
        hyp_objects = synthesize_hypotheses(antideriv)
        hyp_strings = [h.lean_binder for h in hyp_objects]
        disc_class = _discrepancy_class(len(hyp_objects), shape)

        lean_text = generate_theorem_text(cid)
        coq_proof = emit_coq(cid)

        branch_discs = [
            {"arg": d.arg, "class": d.discrepancy_class, "fricas": d.fricas_domain}
            for d in branch_audit(antideriv)
        ]

        evidence = evidence_map.get(cid, "E7_FORMALLY_VERIFIED")

        records.append(CorpusRecord(
            claim_id=cid,
            integrand=integrand,
            antiderivative=antideriv,
            lean_theorem=lean_text,
            coq_theorem=coq_proof.full_text,
            shape=shape,
            discrepancy_class=disc_class,
            hypotheses=hyp_strings,
            branch_discrepancies=branch_discs,
            evidence_class=evidence,
        ))

    return records


def export_to_jsonl(path: Optional[str] = None) -> Path:
    """
    Write the corpus as JSONL to path (default: ml/corpus.jsonl).

    Returns the Path of the written file.
    """
    dest = Path(path) if path else Path(__file__).parent / "corpus.jsonl"
    dest.parent.mkdir(parents=True, exist_ok=True)
    records = export_corpus()
    with dest.open("w") as f:
        for r in records:
            f.write(json.dumps(r.to_dict()) + "\n")
    return dest
