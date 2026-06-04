"""
Tests for Tier 8.2 — cross-prover certificate.

The "honest edge": one integral verified by Lean 4 + Mathlib AND Coq +
Coquelicot with no shared trusted base.

Run with:  python -m pytest tests/test_cross_certificate.py -v
"""
from __future__ import annotations

import pytest

from cross_prover.cross_certificate import (
    CrossProverCertificate,
    KernelWitness,
    build_certificate,
    certify_all,
    _normalise,
)


# ---------------------------------------------------------------------------
# Normaliser unit tests
# ---------------------------------------------------------------------------

def test_normalise_lean_007():
    lean = (
        "theorem autodischarge_007 (x : ℝ) (hx : x ≠ 0) :\n"
        "    HasDerivAt (fun t : ℝ => Real.log t)\n"
        "               (1 / x) x := by"
    )
    result = _normalise(lean)
    assert "log x" in result
    assert "1 / x" in result


def test_normalise_coq_007():
    coq = (
        "Theorem coq_autodischarge_007 (x : R) (hx : x <> 0) :\n"
        "  is_derive (fun x => ln x) x (1 / x)."
    )
    result = _normalise(coq)
    assert "log x" in result
    assert "1 / x" in result


def test_normalise_lean_coq_007_equal():
    lean = (
        "theorem autodischarge_007 (x : ℝ) (hx : x ≠ 0) :\n"
        "    HasDerivAt (fun t : ℝ => Real.log t)\n"
        "               (1 / x) x := by"
    )
    coq = "Theorem coq_autodischarge_007 (x : R) (hx : x <> 0) :\n  is_derive (fun x => ln x) x (1 / x)."
    assert _normalise(lean) == _normalise(coq)


def test_normalise_drops_theorem_name():
    s = "theorem autodischarge_007 (x : ℝ) : HasDerivAt (fun t : ℝ => Real.log t) (1 / x) x := by"
    result = _normalise(s)
    assert "autodischarge_007" not in result
    assert "theorem" not in result.lower()


# ---------------------------------------------------------------------------
# KernelWitness and CrossProverCertificate structure
# ---------------------------------------------------------------------------

def test_build_certificate_returns_dataclass():
    cert = build_certificate("pf.integral.bronstein_007")
    assert isinstance(cert, CrossProverCertificate)
    assert isinstance(cert.lean_witness, KernelWitness)
    assert isinstance(cert.coq_witness, KernelWitness)


def test_certificate_claim_id():
    cert = build_certificate("pf.integral.bronstein_007")
    assert cert.claim_id == "pf.integral.bronstein_007"


def test_certificate_has_integrand():
    cert = build_certificate("pf.integral.bronstein_007")
    assert "1" in cert.integrand or "x" in cert.integrand


# ---------------------------------------------------------------------------
# Lean witness
# ---------------------------------------------------------------------------

def test_lean_witness_kernel_label():
    cert = build_certificate("pf.integral.bronstein_007")
    assert "lean4" in cert.lean_witness.kernel.lower()
    assert "mathlib" in cert.lean_witness.kernel.lower()


def test_lean_witness_theorem_name():
    cert = build_certificate("pf.integral.bronstein_007")
    assert cert.lean_witness.theorem_name == "autodischarge_007"


def test_lean_witness_artifact_path():
    cert = build_certificate("pf.integral.bronstein_007")
    assert "RischAutoDischarge.lean" in cert.lean_witness.artifact_path


def test_lean_witness_sha256_present():
    cert = build_certificate("pf.integral.bronstein_007")
    sha = cert.lean_witness.artifact_sha256
    assert sha is not None
    assert len(sha) == 64


# ---------------------------------------------------------------------------
# Coq witness
# ---------------------------------------------------------------------------

def test_coq_witness_kernel_label():
    cert = build_certificate("pf.integral.bronstein_007")
    assert "coq" in cert.coq_witness.kernel.lower()
    assert "coquelicot" in cert.coq_witness.kernel.lower()


def test_coq_witness_theorem_name():
    cert = build_certificate("pf.integral.bronstein_007")
    assert cert.coq_witness.theorem_name == "coq_autodischarge_007"


def test_coq_witness_artifact_path():
    cert = build_certificate("pf.integral.bronstein_007")
    assert "RischCoqDischarge.v" in cert.coq_witness.artifact_path


def test_coq_witness_sha256_present():
    cert = build_certificate("pf.integral.bronstein_007")
    sha = cert.coq_witness.artifact_sha256
    assert sha is not None
    assert len(sha) == 64


def test_lean_coq_sha256_differ():
    """Lean .lean and Coq .v are different files → different hashes."""
    cert = build_certificate("pf.integral.bronstein_007")
    assert cert.lean_witness.artifact_sha256 != cert.coq_witness.artifact_sha256


# ---------------------------------------------------------------------------
# Honest semantics: equation equivalence vs domain relation
# ---------------------------------------------------------------------------

def test_certificate_complete_both_artifacts():
    cert = build_certificate("pf.integral.bronstein_003")
    assert cert.is_complete is True


def test_caveat_free_flagship_003():
    """003 (ln(x²+1)/2, positive arg) is caveat-free in both kernels."""
    cert = build_certificate("pf.integral.bronstein_003")
    assert cert.equation_equivalent is True
    assert cert.domain_relation == "identical"
    assert cert.caveat_free is True
    assert cert.statements_equivalent is True   # back-compat alias


def test_caveat_free_arctan_004():
    cert = build_certificate("pf.integral.bronstein_004")
    assert cert.caveat_free is True


@pytest.mark.parametrize("claim_id", [
    "pf.integral.bronstein_007",
    "pf.integral.bronstein_009",
])
def test_branch_cut_cases_equation_matches_domain_diverges(claim_id):
    """007/009: the derivative equation matches, but Lean (arg≠0) and Coq
    (0<arg) prove it on different domains — honestly NOT caveat-free."""
    cert = build_certificate(claim_id)
    assert cert.equation_equivalent is True
    assert cert.domain_relation == "branch_cut_divergent"
    assert cert.caveat_free is False
    assert cert.statements_equivalent is False


def test_branch_cut_hypotheses_recorded():
    cert = build_certificate("pf.integral.bronstein_007")
    assert any("≠" in h for h in cert.lean_witness.hypotheses)
    assert any("0 <" in h for h in cert.coq_witness.hypotheses)


# ---------------------------------------------------------------------------
# certify_all — two caveat-free, one branch-cut
# ---------------------------------------------------------------------------

def test_certify_all_returns_three():
    certs = certify_all()
    assert len(certs) == 3


def test_certify_all_all_complete():
    for cert in certify_all():
        assert cert.is_complete, f"{cert.claim_id}: not complete"


def test_certify_all_has_caveat_free_and_branch_cut():
    certs = certify_all()
    caveat_free = [c for c in certs if c.caveat_free]
    branch_cut = [c for c in certs if c.domain_relation == "branch_cut_divergent"]
    assert len(caveat_free) == 2, "expected 003 and 004 caveat-free"
    assert len(branch_cut) == 1, "expected 007 branch-cut divergent"


def test_certify_all_every_equation_matches():
    for cert in certify_all():
        assert cert.equation_equivalent, f"{cert.claim_id}: equation mismatch"


def test_certify_all_accepts_custom_list():
    certs = certify_all(["pf.integral.bronstein_003"])
    assert len(certs) == 1
    assert certs[0].claim_id == "pf.integral.bronstein_003"


def test_certificate_to_dict_serialisable():
    import json
    cert = build_certificate("pf.integral.bronstein_003")
    d = cert.to_dict()
    json.dumps(d)  # must not raise
    assert d["claim_id"] == "pf.integral.bronstein_003"
    assert "lean_witness" in d
    assert "coq_witness" in d
    assert d["domain_relation"] == "identical"


# ---------------------------------------------------------------------------
# Live coqc verification (when available)
# ---------------------------------------------------------------------------

def test_verify_coq_artifact_runs_kernel():
    from cross_prover.cross_certificate import verify_coq_artifact
    result = verify_coq_artifact()
    # None when coqc absent (CI's coq.yml covers it); True/False when present.
    if result is None:
        import shutil
        assert shutil.which("coqc") is None
    else:
        assert result is True, "coqc rejected the committed Coq artifact"
