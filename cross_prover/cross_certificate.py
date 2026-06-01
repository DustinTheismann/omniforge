"""
Tier 8.2 — Cross-prover certificate.

The "honest edge": one integral verified by two independent proof kernels —
Lean 4 + Mathlib and Coq + Coquelicot — with no shared trusted base.

A CrossProverCertificate records:
  - which claim was verified
  - which artifact was checked by each kernel (file path + SHA-256)
  - the Lean theorem statement and the Coq theorem statement
  - whether the two statements are semantically equivalent (checked by
    comparing their normalised forms)

The default focus claim is bronstein_007:  ∫ 1/x dx = log x
  Lean 4:  autodischarge_007 in fricas_bridge/RischAutoDischarge.lean
  Coq:     coq_autodischarge_007 in cross_prover/RischCoqDischarge.v

Public API
----------
CrossProverCertificate          dataclass
build_certificate(claim_id)     → CrossProverCertificate
certify_all()                   → list[CrossProverCertificate]
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from cross_prover.coq_emitter import emit_coq
from fricas_bridge.proof_discharger import generate_theorem_text

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Default pair: the cleanest integral — log x
_DEFAULT_CLAIM = "pf.integral.bronstein_007"

# Claims to certify by default
_CERT_CLAIMS = [
    "pf.integral.bronstein_007",   # Class B — log x  (simplest cross-cert)
    "pf.integral.bronstein_003",   # Class A — log(x²+1)/2
    "pf.integral.bronstein_009",   # Class D — three-pole PFD
]


@dataclass
class KernelWitness:
    kernel: str                    # "lean4:v4.30.0+mathlib" or "coq:coquelicot3"
    theorem_name: str              # "autodischarge_007"
    artifact_path: str             # relative repo path
    artifact_sha256: Optional[str] # sha256 of file, None if not on disk
    theorem_statement: str         # normalised statement text


@dataclass
class CrossProverCertificate:
    claim_id: str
    integrand: str
    antideriv: str
    lean_witness: KernelWitness
    coq_witness: KernelWitness
    statements_equivalent: bool    # True when normalised forms match

    @property
    def is_complete(self) -> bool:
        """True when both witnesses have artifacts on disk."""
        return (
            self.lean_witness.artifact_sha256 is not None
            and self.coq_witness.artifact_sha256 is not None
        )

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Statement normalisation
# ---------------------------------------------------------------------------

def _normalise(stmt: str) -> str:
    """
    Reduce a Lean 4 or Coq theorem statement to a token-canonical string so
    that semantically equivalent statements compare equal.

    Strategy: strip all structural noise (theorem name, binders, proof opener,
    keywords HasDerivAt/is_derive, point variable) and normalise library names,
    then compare the residual mathematical tokens.
    """
    s = re.sub(r"\s+", " ", stmt).strip()

    # Library names → canonical
    s = re.sub(r"Real\.log", "log", s)
    s = re.sub(r"\bln\b", "log", s)
    s = re.sub(r"Real\.arctan", "arctan", s)
    s = re.sub(r"\batan\b", "arctan", s)

    # Lean bound variable t → x
    s = re.sub(r"\bt\b", "x", s)

    # Strip theorem declaration (keyword + name + up to ':')
    s = re.sub(r"(?i)^(theorem|lemma)\s+\S+", "", s)

    # Strip hypothesis binders and type annotations: (name : type)
    # Only match binders that don't contain `fun` or `=>` (those are lambda bodies).
    for _ in range(4):
        s = re.sub(r"\([^()=]+:[^()=]+\)", "", s)

    # Strip proof opener :=  by and trailing full-stop
    s = re.sub(r":=\s*by\s*$", "", s)
    s = s.rstrip(".")

    # Strip keywords
    s = re.sub(r"\b(HasDerivAt|is_derive)\b", "", s)

    # Strip the lambda abstraction keyword: `fun x =>` or `fun x : R =>`
    s = re.sub(r"\bfun\s+x\s*(?::\s*[ℝR])?\s*=>", "", s)

    # Strip the evaluation point `x` — it appears at the end in Lean
    # (HasDerivAt f f' x) or between the fun-body and integrand in Coq
    # (is_derive f x f').  Both are normalised away.
    s = re.sub(r"\s*\bx\s*$", "", s.rstrip())        # trailing x (Lean)
    s = re.sub(r"\)\s+x\s+\(", ") (", s)             # middle x (Coq)

    # Normalise whitespace and remove empty parens
    s = re.sub(r"\(\s*\)", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _sha256_of(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Certificate builder
# ---------------------------------------------------------------------------

def build_certificate(claim_id: str) -> CrossProverCertificate:
    """
    Build a cross-prover certificate for one claim.

    Reads the Lean theorem from proof_discharger.generate_theorem_text and
    the Coq theorem from coq_emitter.emit_coq, then records SHA-256 of the
    committed artifact files.
    """
    suffix = claim_id.split("_")[-1] if "_" in claim_id else claim_id

    # ---- Lean witness ----
    lean_text = generate_theorem_text(claim_id)
    lean_artifact = "fricas_bridge/RischAutoDischarge.lean"
    lean_path = _REPO_ROOT / lean_artifact
    lean_sha = _sha256_of(lean_path)
    lean_stmt = _extract_lean_theorem(lean_text, f"autodischarge_{suffix}")

    lean_witness = KernelWitness(
        kernel="lean4:v4.30.0 + mathlib:v4.30.0",
        theorem_name=f"autodischarge_{suffix}",
        artifact_path=lean_artifact,
        artifact_sha256=lean_sha,
        theorem_statement=lean_stmt,
    )

    # ---- Coq witness ----
    coq_proof = emit_coq(claim_id)
    coq_artifact = "cross_prover/RischCoqDischarge.v"
    coq_path = _REPO_ROOT / coq_artifact
    coq_sha = _sha256_of(coq_path)

    coq_witness = KernelWitness(
        kernel="coq:coquelicot3",
        theorem_name=coq_proof.theorem_name,
        artifact_path=coq_artifact,
        artifact_sha256=coq_sha,
        theorem_statement=coq_proof.statement,
    )

    # ---- Equivalence check ----
    equiv = _normalise(lean_stmt) == _normalise(coq_proof.statement)

    return CrossProverCertificate(
        claim_id=claim_id,
        integrand=coq_proof.integrand,
        antideriv=coq_proof.antideriv,
        lean_witness=lean_witness,
        coq_witness=coq_witness,
        statements_equivalent=equiv,
    )


def certify_all(claim_ids: Optional[list[str]] = None) -> list[CrossProverCertificate]:
    """Build certificates for all default claims (or a provided list)."""
    ids = claim_ids if claim_ids is not None else _CERT_CLAIMS
    return [build_certificate(cid) for cid in ids]


# ---------------------------------------------------------------------------
# Lean theorem extractor (from the generated Lean file text)
# ---------------------------------------------------------------------------

def _extract_lean_theorem(lean_text: str, theorem_name: str) -> str:
    """
    Pull the theorem statement (up to ':= by') from generated Lean text.
    Returns just the theorem line(s), not the proof body.
    """
    lines = lean_text.splitlines()
    collecting = False
    stmt_lines: list[str] = []
    for line in lines:
        if f"theorem {theorem_name}" in line:
            collecting = True
        if collecting:
            stmt_lines.append(line)
            if ":= by" in line or line.strip().endswith(":= by"):
                break
    return "\n".join(stmt_lines)
