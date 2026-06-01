"""
Tier 10 — End-to-end pipeline integration tests.

These tests verify that the full ProofForge Ω pipeline works end-to-end
without a live FriCAS or Lean process, using only the committed offline
caches and artifacts.

Pipeline:
  integrand
  → FriCAS offline resolver (antiderivative)
  → shape classifier + hypothesis synthesizer
  → Lean theorem generator
  → Coq theorem generator
  → Isabelle theorem generator
  → branch audit
  → semantic filter
  → obligation derivation
  → evidence grader
  → cross-prover certificate
  → bug hunt verification
  → corpus record

Run with:  python -m pytest tests/test_e2e_pipeline.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# All pipeline stages
from fricas_bridge.offline_cache import FriCASResolver
from fricas_bridge.proof_discharger import (
    classify_antideriv,
    synthesize_hypotheses,
    generate_theorem_text,
)
from cross_prover.coq_emitter import emit_coq
from cross_prover.isabelle_emitter import emit_isabelle
from fricas_bridge.branch_audit import branch_audit, discrepancies_only
from fricas_bridge.semantic_filter import semantic_filter
from fricas_bridge.bug_hunt import run_bug_hunt, VERIFIED
from protocols.obligation_protocol import obligations_for_claim
from protocols.transmute import transmute
from cross_prover.cross_certificate import build_certificate
from ml.export_corpus import export_corpus

_EX = Path(__file__).parent.parent / "protocols" / "claim_protocol" / "examples"

# Focus claim: the cleanest case — ∫ 1/x dx = log x
_CLAIM_007_ID = "pf.integral.bronstein_007"
_CLAIM_007_INTEGRAND = "1/x"


def _load_claim_007():
    return json.loads((_EX / "risch_bronstein_007.json").read_text())


# ---------------------------------------------------------------------------
# Stage 1: FriCAS resolution
# ---------------------------------------------------------------------------

def test_e2e_fricas_resolves_1_over_x():
    r = FriCASResolver(mode="offline").resolve(_CLAIM_007_INTEGRAND)
    assert r.ok
    assert r.antiderivative == "log(x)"


# ---------------------------------------------------------------------------
# Stage 2: Shape classification + hypothesis synthesis
# ---------------------------------------------------------------------------

def test_e2e_classify_log_x():
    shape = classify_antideriv("log(x)")
    assert shape["shape"] == "LOG_SIMPLE"


def test_e2e_synthesize_hypothesis():
    hyps = synthesize_hypotheses("log(x)")
    assert len(hyps) == 1
    assert "x ≠ 0" in hyps[0].lean_binder


# ---------------------------------------------------------------------------
# Stage 3: Lean theorem generation
# ---------------------------------------------------------------------------

def test_e2e_lean_theorem_007():
    text = generate_theorem_text(_CLAIM_007_ID)
    assert "HasDerivAt" in text
    assert "autodischarge_007" in text
    assert "(hx : x ≠ 0)" in text


# ---------------------------------------------------------------------------
# Stage 4: Coq theorem generation
# ---------------------------------------------------------------------------

def test_e2e_coq_theorem_007():
    p = emit_coq(_CLAIM_007_ID)
    assert "coq_autodischarge_007" in p.theorem_name
    assert "is_derive" in p.statement
    assert "hx : x <> 0" in p.hypotheses[0]


# ---------------------------------------------------------------------------
# Stage 5: Isabelle theorem generation
# ---------------------------------------------------------------------------

def test_e2e_isabelle_theorem_007():
    p = emit_isabelle(_CLAIM_007_ID)
    assert "isabelle_autodischarge_007" in p.theorem_name
    assert "has_real_derivative" in p.statement
    assert "x ≠ 0" in p.hypotheses[0]


# ---------------------------------------------------------------------------
# Stage 6: Branch audit
# ---------------------------------------------------------------------------

def test_e2e_branch_audit_007():
    discrepancies = discrepancies_only("log(x)")
    assert len(discrepancies) == 1
    assert discrepancies[0].discrepancy_class == "E_branch_cut"


# ---------------------------------------------------------------------------
# Stage 7: Semantic filter
# ---------------------------------------------------------------------------

def test_e2e_semantic_filter_007():
    r = semantic_filter(_CLAIM_007_INTEGRAND, "log(x)")
    assert r.ok is True


# ---------------------------------------------------------------------------
# Stage 8: Bug hunt verification
# ---------------------------------------------------------------------------

def test_e2e_bug_hunt_007():
    [result] = run_bug_hunt([(_CLAIM_007_INTEGRAND, "x")])
    assert result.verdict == VERIFIED


# ---------------------------------------------------------------------------
# Stage 9: Obligation derivation + transmutation
# ---------------------------------------------------------------------------

def test_e2e_obligations_007():
    claim = _load_claim_007()
    obs = obligations_for_claim(claim)
    assert len(obs) >= 1
    assert "lean4" in obs[0].checker


def test_e2e_transmute_007_reaches_e7():
    claim = _load_claim_007()
    result = transmute(claim)
    assert result.evidence_class == "E7_FORMALLY_VERIFIED"


def test_e2e_transmute_007_all_discharged():
    claim = _load_claim_007()
    result = transmute(claim)
    assert result.all_discharged


# ---------------------------------------------------------------------------
# Stage 10: Cross-prover certificate
# ---------------------------------------------------------------------------

def test_e2e_cross_certificate_007():
    cert = build_certificate(_CLAIM_007_ID)
    assert cert.is_complete
    assert cert.statements_equivalent
    assert cert.lean_witness.artifact_sha256 is not None
    assert cert.coq_witness.artifact_sha256 is not None


def test_e2e_certificate_both_kernels():
    cert = build_certificate(_CLAIM_007_ID)
    assert "lean4" in cert.lean_witness.kernel.lower()
    assert "coq" in cert.coq_witness.kernel.lower()


# ---------------------------------------------------------------------------
# Stage 11: Corpus export
# ---------------------------------------------------------------------------

def test_e2e_corpus_contains_007():
    records = {r.claim_id: r for r in export_corpus()}
    assert _CLAIM_007_ID in records
    r = records[_CLAIM_007_ID]
    assert r.integrand == _CLAIM_007_INTEGRAND
    assert "HasDerivAt" in r.lean_theorem
    assert "is_derive" in r.coq_theorem
    assert r.evidence_class == "E7_FORMALLY_VERIFIED"
    assert r.discrepancy_class == "B"


# ---------------------------------------------------------------------------
# Full pipeline smoke test: all 8 claims
# ---------------------------------------------------------------------------

def test_e2e_all_eight_claims_pipeline():
    """All 8 claims pass the full pipeline without error."""
    claims = [
        json.loads((_EX / f"risch_bronstein_{n:03d}.json").read_text())
        for n in (1, 3, 4, 5, 6, 7, 8, 9)
    ]
    for claim in claims:
        cid = claim["claim_id"]
        # Obligations
        obs = obligations_for_claim(claim)
        assert len(obs) >= 1, f"{cid}: no obligations"
        # Transmutation
        result = transmute(claim)
        assert result.evidence_class == "E7_FORMALLY_VERIFIED", f"{cid}: not E7"
        # Lean + Coq theorem
        lean_text = generate_theorem_text(cid)
        assert "HasDerivAt" in lean_text, f"{cid}: no HasDerivAt in Lean"
        coq_proof = emit_coq(cid)
        assert "is_derive" in coq_proof.statement, f"{cid}: no is_derive in Coq"
