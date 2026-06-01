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
# Certificate completeness and equivalence
# ---------------------------------------------------------------------------

def test_certificate_007_is_complete():
    cert = build_certificate("pf.integral.bronstein_007")
    assert cert.is_complete is True


def test_certificate_007_statements_equivalent():
    cert = build_certificate("pf.integral.bronstein_007")
    assert cert.statements_equivalent is True


@pytest.mark.parametrize("claim_id", [
    "pf.integral.bronstein_007",
    "pf.integral.bronstein_003",
    "pf.integral.bronstein_009",
])
def test_certificate_complete_and_equivalent(claim_id):
    cert = build_certificate(claim_id)
    assert cert.is_complete, f"{claim_id}: artifacts missing"
    assert cert.statements_equivalent, f"{claim_id}: statements not equivalent"


# ---------------------------------------------------------------------------
# certify_all
# ---------------------------------------------------------------------------

def test_certify_all_returns_three():
    certs = certify_all()
    assert len(certs) == 3


def test_certify_all_all_complete():
    for cert in certify_all():
        assert cert.is_complete, f"{cert.claim_id}: not complete"


def test_certify_all_all_equivalent():
    for cert in certify_all():
        assert cert.statements_equivalent, f"{cert.claim_id}: not equivalent"


def test_certify_all_accepts_custom_list():
    certs = certify_all(["pf.integral.bronstein_007"])
    assert len(certs) == 1
    assert certs[0].claim_id == "pf.integral.bronstein_007"


def test_certificate_to_dict_serialisable():
    import json
    cert = build_certificate("pf.integral.bronstein_007")
    d = cert.to_dict()
    # Must be JSON serialisable (no non-serialisable objects)
    json.dumps(d)
    assert d["claim_id"] == "pf.integral.bronstein_007"
    assert "lean_witness" in d
    assert "coq_witness" in d
