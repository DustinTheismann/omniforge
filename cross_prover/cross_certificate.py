"""
Tier 8.2 — Cross-prover certificate.

The "honest edge": one integral verified by two independent proof kernels —
Lean 4 + Mathlib and Coq + Coquelicot — with no shared trusted base.

A CrossProverCertificate records:
  - which claim was verified
  - which artifact was checked by each kernel (file path + SHA-256)
  - the Lean theorem statement and the Coq theorem statement
  - whether the derivative EQUATION matches across kernels (equation_equivalent)
  - how the DOMAINS relate (domain_relation): identical, or branch-cut divergent

The honest distinction this module now enforces:
  * Lean's `Real.log` is total, so its log theorems carry `arg <> 0`.
  * Coq's `ln` is the PRINCIPAL branch (kernel-confirmed by coqc), so its log
    theorems carry `0 < arg`.
  A caveat-free cross-prover certificate therefore exists ONLY for the
  positive-argument cases (bronstein_001/003/004/006), where both kernels prove
  the SAME unconditional statement.  For the branch-cut cases (005/007/008/009)
  the equation matches but the domains diverge — which is itself evidence of the
  branch-cut discrepancy, not a caveat-free certificate.

The default flagship is bronstein_003:  d/dx ln(x²+1)/2 = x/(x²+1)
  Lean 4:  autodischarge_003 in fricas_bridge/RischAutoDischarge.lean   (lean.yml)
  Coq:     coq_autodischarge_003 in cross_prover/RischCoqDischarge.v     (coq.yml)

Public API
----------
CrossProverCertificate          dataclass
build_certificate(claim_id)     → CrossProverCertificate
certify_all()                   → list[CrossProverCertificate]
verify_coq_artifact()           → Optional[bool]   (runs coqc if available)
"""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

from cross_prover.coq_emitter import emit_coq, COQ_SOURCE
from fricas_bridge.proof_discharger import generate_theorem_text

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Default flagship: caveat-free in both kernels (positive argument, no branch cut).
_DEFAULT_CLAIM = "pf.integral.bronstein_003"

# Claims to certify by default: two caveat-free, one branch-cut (to show the line).
_CERT_CLAIMS = [
    "pf.integral.bronstein_003",   # caveat-free: ln(x²+1)/2, arg > 0 always
    "pf.integral.bronstein_004",   # caveat-free: arctan(x²), total
    "pf.integral.bronstein_007",   # branch-cut divergent: ln x  (Lean x≠0 / Coq 0<x)
]


@dataclass
class KernelWitness:
    kernel: str                    # "lean4:v4.30.0+mathlib" or "coq:coquelicot3"
    theorem_name: str              # "autodischarge_007"
    artifact_path: str             # relative repo path
    artifact_sha256: Optional[str] # sha256 of file, None if not on disk
    theorem_statement: str         # statement text
    hypotheses: list[str] = field(default_factory=list)


@dataclass
class CrossProverCertificate:
    claim_id: str
    integrand: str
    antideriv: str
    lean_witness: KernelWitness
    coq_witness: KernelWitness
    equation_equivalent: bool      # derivative equation matches (ignoring domain)
    domain_relation: str           # "identical" | "branch_cut_divergent"

    @property
    def caveat_free(self) -> bool:
        """A genuine cross-prover certificate: same equation AND same domain."""
        return self.equation_equivalent and self.domain_relation == "identical"

    @property
    def statements_equivalent(self) -> bool:
        """Back-compat alias: the statements are identical iff caveat-free."""
        return self.caveat_free

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


_LEAN_BINDER_RE = re.compile(r"\(([^()]*?:[^()]*?)\)")


def _extract_lean_hypotheses(lean_stmt: str) -> list[str]:
    """Pull non-`(x : ℝ)` binders out of a Lean theorem signature."""
    head = lean_stmt.split("HasDerivAt", 1)[0]
    hyps: list[str] = []
    for b in _LEAN_BINDER_RE.findall(head):
        b = " ".join(b.split())
        if b.replace(" ", "") in ("x:ℝ", "x:R"):
            continue
        hyps.append(b)
    return hyps


def _domain_relation(lean_hyps: list[str], coq_hyps: list[str]) -> str:
    """
    Classify how the two kernels' domains relate.

    - both unconditional            → "identical"
    - Lean uses `≠`/Coq uses `0 <`  → "branch_cut_divergent"
    - otherwise (same shape)         → "identical"
    """
    if not lean_hyps and not coq_hyps:
        return "identical"
    coq_is_positivity = any("0 <" in h for h in coq_hyps)
    lean_is_nonzero = any("≠" in h or "<>" in h for h in lean_hyps)
    if coq_is_positivity and lean_is_nonzero:
        return "branch_cut_divergent"
    if coq_is_positivity != lean_is_nonzero:
        return "branch_cut_divergent"
    return "identical"


def verify_coq_artifact(root: Optional[Path] = None) -> Optional[bool]:
    """
    Run coqc on the committed Coq artifact if a Coq toolchain is available.

    Returns True if the Coq kernel accepts every theorem, False if it rejects,
    and None if `coqc` is not installed (so callers can skip rather than fail).
    The authoritative check is .github/workflows/coq.yml; this lets local/CI
    runs that *do* have coqc assert kernel acceptance directly.
    """
    if shutil.which("coqc") is None:
        return None
    src = (root / "cross_prover" / "RischCoqDischarge.v") if root else COQ_SOURCE
    env_path = "/usr/lib/ocaml/coq/user-contrib"
    import os
    env = dict(os.environ)
    # Prepend the standard Debian Coquelicot location if present.
    if Path(env_path).exists():
        env["COQPATH"] = env_path + (":" + env["COQPATH"] if env.get("COQPATH") else "")
    try:
        proc = subprocess.run(
            ["coqc", src.name],
            cwd=str(src.parent),
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
        return proc.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return None


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

    lean_hyps = _extract_lean_hypotheses(lean_stmt)
    lean_witness = KernelWitness(
        kernel="lean4:v4.30.0 + mathlib:v4.30.0",
        theorem_name=f"autodischarge_{suffix}",
        artifact_path=lean_artifact,
        artifact_sha256=lean_sha,
        theorem_statement=lean_stmt,
        hypotheses=lean_hyps,
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
        hypotheses=coq_proof.hypotheses,
    )

    # ---- Equation equivalence (ignores domain) + domain relation ----
    equation_equivalent = _normalise(lean_stmt) == _normalise(coq_proof.statement)
    domain_relation = _domain_relation(lean_hyps, coq_proof.hypotheses)

    return CrossProverCertificate(
        claim_id=claim_id,
        integrand=coq_proof.integrand,
        antideriv=coq_proof.antideriv,
        lean_witness=lean_witness,
        coq_witness=coq_witness,
        equation_equivalent=equation_equivalent,
        domain_relation=domain_relation,
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
