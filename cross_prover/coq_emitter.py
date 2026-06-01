"""
Tier 8.1 — Coq / Coquelicot proof reflector.

This module reflects the *kernel-checked* Coq theorems in the committed file
cross_prover/RischCoqDischarge.v, which is verified by coqc + Coquelicot in CI
(.github/workflows/coq.yml).  Earlier this module emitted Coq *text* that no
Coq kernel ever checked — and, worse, emitted the wrong hypothesis (`x <> 0`)
for the log cases.  Running coqc revealed the real constraint:

  Coq's `ln` is the PRINCIPAL branch, differentiable only where its argument
  is > 0.  So the log theorems carry `0 < arg` hypotheses, NOT `arg <> 0`.

To make "emitted == verified" true by construction, the public API now parses
the committed, kernel-accepted .v file rather than generating fresh text.

Public API
----------
CoqProof                        dataclass (one kernel-checked theorem)
emit_coq(claim_id)              → CoqProof
emit_all()                      → list[CoqProof]
write_coq_file(path)            → Path     (copies the verified file verbatim)
COQ_SOURCE                      Path       (the committed, CI-checked .v)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from fricas_bridge.proof_discharger import _ALL_CLAIMS, FRICAS_CACHE, classify_antideriv

COQ_SOURCE = Path(__file__).resolve().parent / "RischCoqDischarge.v"


@dataclass
class CoqProof:
    theorem_name: str           # "coq_autodischarge_007"
    claim_id: str               # "pf.integral.bronstein_007"
    integrand: str              # RHS of is_derive (Coq syntax)
    antideriv: str              # lambda body of is_derive (Coq syntax)
    hypotheses: list[str]       # ["hx : 0 < x"]   (Coq syntax, kernel-checked)
    statement: str              # full Coq `Theorem ... .` line(s)
    proof_script: str           # `Proof. ... Qed.`
    antideriv_shape: str        # classify_antideriv key

    @property
    def full_text(self) -> str:
        return self.statement + "\n" + self.proof_script + "\n"

    @property
    def is_branch_cut(self) -> bool:
        """True when the Coq proof needed a 0<arg hypothesis (principal branch),
        i.e. its domain differs from Lean's total Real.log (arg <> 0)."""
        return any("0 <" in h for h in self.hypotheses)


# ---------------------------------------------------------------------------
# Parser: committed .v  →  CoqProof records
# ---------------------------------------------------------------------------

# Anchor the statement on `is_derive` so the separator colon (the one that
# precedes the statement) is found by backtracking past the binders' colons.
_THEOREM_RE = re.compile(
    r"Theorem\s+(coq_autodischarge_(\d+))\s+(.*?):\s*(is_derive\b.*?)\.\s*"
    r"(Proof\..*?Qed\.)",
    re.DOTALL,
)
# is_derive (fun x => <BODY>) x (<INTEGRAND>)
_ISDERIVE_RE = re.compile(
    r"is_derive\s*\(fun\s+x\s*=>\s*(.*)\)\s*x\s*\((.*)\)\s*$",
    re.DOTALL,
)
_BINDER_RE = re.compile(r"\(([^()]*?:[^()]*?)\)")


def _suffix_to_claim_id(suffix: str) -> str:
    for cid in _ALL_CLAIMS:
        if cid.endswith(suffix):
            return cid
    return f"pf.integral.bronstein_{suffix}"


def _parse_source() -> list[CoqProof]:
    text = COQ_SOURCE.read_text()
    proofs: list[CoqProof] = []
    for m in _THEOREM_RE.finditer(text):
        theorem_name, suffix, binder_blob, stmt_body, proof = m.groups()
        claim_id = _suffix_to_claim_id(suffix)

        # Hypotheses are the non-`x : R` binders.
        binders = " ".join(binder_blob.split())
        hyps: list[str] = []
        for b in _BINDER_RE.findall(binders):
            b = " ".join(b.split())
            if b.replace(" ", "") == "x:R":
                continue
            hyps.append(b)

        body, integrand = "", ""
        idm = _ISDERIVE_RE.search(" ".join(stmt_body.split()))
        if idm:
            body = idm.group(1).strip()
            integrand = idm.group(2).strip()

        fricas_antideriv = FRICAS_CACHE.get(claim_id, {}).get("antideriv_fricas", "")
        shape = classify_antideriv(fricas_antideriv).get("shape", "UNKNOWN") \
            if fricas_antideriv else "UNKNOWN"

        statement = f"Theorem {theorem_name} {binders}:\n  {' '.join(stmt_body.split())}."
        proofs.append(CoqProof(
            theorem_name=theorem_name,
            claim_id=claim_id,
            integrand=integrand,
            antideriv=body,
            hypotheses=hyps,
            statement=statement,
            proof_script=proof.strip(),
            antideriv_shape=shape,
        ))
    proofs.sort(key=lambda p: p.theorem_name)
    return proofs


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def emit_all() -> list[CoqProof]:
    """Return every kernel-checked Coq theorem from the committed .v file."""
    return _parse_source()


def emit_coq(claim_id: str) -> CoqProof:
    """Return the kernel-checked Coq theorem for one Bronstein claim."""
    suffix = claim_id.split("_")[-1] if "_" in claim_id else claim_id
    for p in _parse_source():
        if p.theorem_name.endswith(suffix):
            return p
    raise KeyError(f"emit_coq: no Coq theorem for {claim_id!r} in {COQ_SOURCE.name}")


def write_coq_file(path: Optional[str] = None) -> Path:
    """
    Reflect the committed, CI-checked .v file.

    With a path, copy it there verbatim (any emitted artifact is byte-identical
    to what coqc accepted).  With no path, return the committed file's location.
    """
    if path is None:
        return COQ_SOURCE
    dest = Path(path)
    dest.write_text(COQ_SOURCE.read_text())
    return dest
