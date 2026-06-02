"""
Tests for Tier 5.6 — CAS Disagreement Adjudication Certificate.

Run with:  python -m pytest tests/test_adjudication_certificate.py -v
"""
from __future__ import annotations

import json

import pytest

from cross_prover.adjudication_certificate import (
    AdjudicationCertificate,
    AdjudicationKind,
    build_adjudication_cert,
    certify_all_corpus,
    lean_adjudication_file_exists,
    lean_adjudication_theorems,
)


# ---------------------------------------------------------------------------
# Lean file presence
# ---------------------------------------------------------------------------

def test_lean_adjudication_file_exists():
    assert lean_adjudication_file_exists()


def test_lean_adjudication_theorems_present():
    theorems = lean_adjudication_theorems()
    # The six theorems in CasAdjudication.lean
    for name in [
        "form_disagree_005_equivalent",
        "autodischarge_005_sympy_form",
        "adjudicate_005",
        "form_disagree_009_equivalent",
        "autodischarge_009_sympy_form",
        "adjudicate_009",
    ]:
        assert name in theorems, f"Missing theorem: {name}"


def test_lean_adjudication_file_has_six_theorems():
    assert len(lean_adjudication_theorems()) == 6


# ---------------------------------------------------------------------------
# bronstein_005 — NOTATIONAL_ONLY (kernel-adjudicated)
# ---------------------------------------------------------------------------

def test_005_cert_returns_dataclass():
    cert = build_adjudication_cert("(x+1)/(x*(x+2))")
    assert isinstance(cert, AdjudicationCertificate)


def test_005_cert_notational_only():
    cert = build_adjudication_cert("(x+1)/(x*(x+2))")
    assert cert.adjudication_kind == AdjudicationKind.NOTATIONAL_ONLY.value


def test_005_cert_is_kernel_adjudicated():
    cert = build_adjudication_cert("(x+1)/(x*(x+2))")
    assert cert.is_kernel_adjudicated is True


def test_005_cert_lean_lemma():
    cert = build_adjudication_cert("(x+1)/(x*(x+2))")
    assert cert.lean_equivalence_lemma == "form_disagree_005_equivalent"


def test_005_cert_lean_file():
    cert = build_adjudication_cert("(x+1)/(x*(x+2))")
    assert "CasAdjudication.lean" in (cert.lean_file or "")


def test_005_cert_lean_kernel():
    cert = build_adjudication_cert("(x+1)/(x*(x+2))")
    assert "lean4" in cert.lean_kernel.lower()
    assert "mathlib" in cert.lean_kernel.lower()


def test_005_cert_has_both_antiderivs():
    cert = build_adjudication_cert("(x+1)/(x*(x+2))")
    assert cert.fricas_antideriv is not None
    assert cert.sympy_antideriv is not None
    # FriCAS has factored form, SymPy has product form
    assert "log(x)" in cert.fricas_antideriv
    assert "log(x+2)" in cert.fricas_antideriv or "log(x + 2)" in cert.fricas_antideriv
    assert "log" in cert.sympy_antideriv
    # They should be different strings
    assert cert.fricas_antideriv.replace(" ", "") != cert.sympy_antideriv.replace(" ", "")


def test_005_cert_note_mentions_log_mul():
    cert = build_adjudication_cert("(x+1)/(x*(x+2))")
    assert "Real.log_mul" in cert.adjudication_note or "log_mul" in cert.adjudication_note


def test_005_cert_sha256_present():
    cert = build_adjudication_cert("(x+1)/(x*(x+2))")
    assert len(cert.sha256) == 64


def test_005_cert_serialisable():
    cert = build_adjudication_cert("(x+1)/(x*(x+2))")
    d = cert.to_dict()
    json.dumps(d)  # must not raise
    assert d["is_kernel_adjudicated"] is True
    assert d["adjudication_kind"] == "notational_only"


# ---------------------------------------------------------------------------
# bronstein_009 — NOTATIONAL_ONLY (kernel-adjudicated)
# ---------------------------------------------------------------------------

def test_009_cert_notational_only():
    cert = build_adjudication_cert("1/(x*(x+1)*(x+2))")
    assert cert.adjudication_kind == AdjudicationKind.NOTATIONAL_ONLY.value
    assert cert.is_kernel_adjudicated is True


def test_009_cert_lean_lemma():
    cert = build_adjudication_cert("1/(x*(x+1)*(x+2))")
    assert cert.lean_equivalence_lemma == "form_disagree_009_equivalent"


def test_009_cert_both_antiderivs_present():
    cert = build_adjudication_cert("1/(x*(x+1)*(x+2))")
    assert cert.fricas_antideriv is not None
    assert cert.sympy_antideriv is not None


# ---------------------------------------------------------------------------
# 1/sqrt(x^2-1) — DOMAIN_RESTRICTED
# ---------------------------------------------------------------------------

def test_sqrt_cert_domain_restricted():
    cert = build_adjudication_cert("1/sqrt(x^2-1)")
    assert cert.adjudication_kind == AdjudicationKind.DOMAIN_RESTRICTED.value


def test_sqrt_cert_not_kernel_adjudicated():
    """No Lean equivalence lemma exists for acosh vs log form."""
    cert = build_adjudication_cert("1/sqrt(x^2-1)")
    assert cert.is_kernel_adjudicated is False
    assert cert.lean_equivalence_lemma is None


def test_sqrt_cert_domain_notes():
    cert = build_adjudication_cert("1/sqrt(x^2-1)")
    assert isinstance(cert.domain_notes, dict)
    # Should have some domain info
    assert len(cert.domain_notes) > 0


# ---------------------------------------------------------------------------
# Agreeing integrals — NOT_ADJUDICATED
# ---------------------------------------------------------------------------

def test_agree_cert_not_adjudicated():
    cert = build_adjudication_cert("1/x")
    assert cert.adjudication_kind == AdjudicationKind.NOT_ADJUDICATED.value
    assert cert.is_kernel_adjudicated is False


def test_agree_cert_has_antiderivs():
    cert = build_adjudication_cert("1/x")
    assert cert.fricas_antideriv == "log(x)"
    assert cert.sympy_antideriv == "log(x)"


# ---------------------------------------------------------------------------
# certify_all_corpus
# ---------------------------------------------------------------------------

def test_certify_all_corpus_returns_list():
    certs = certify_all_corpus()
    assert isinstance(certs, list)
    assert len(certs) >= 35


def test_certify_all_corpus_all_dataclasses():
    for cert in certify_all_corpus():
        assert isinstance(cert, AdjudicationCertificate)


def test_certify_all_corpus_has_two_kernel_adjudicated():
    """Exactly two integrands have Lean kernel adjudication (005 and 009)."""
    certs = certify_all_corpus()
    ka = [c for c in certs if c.is_kernel_adjudicated]
    assert len(ka) == 2
    integrands = {c.integrand for c in ka}
    assert "(x+1)/(x*(x+2))" in integrands
    assert "1/(x*(x+1)*(x+2))" in integrands


def test_certify_all_corpus_has_domain_restricted():
    certs = certify_all_corpus()
    dr = [c for c in certs if c.adjudication_kind == AdjudicationKind.DOMAIN_RESTRICTED.value]
    assert len(dr) >= 2  # at least 1/sqrt(x^2-1) and 1/sqrt(x^2+1)


def test_certify_all_corpus_no_genuine_disagree_in_bronstein():
    """No Bronstein integrand should produce a GENUINE_DISAGREE."""
    from fricas_bridge.cas_corpus import load_bronstein_set
    bronstein_igs = {e.integrand for e in load_bronstein_set()}
    certs = certify_all_corpus()
    for cert in certs:
        if cert.integrand in bronstein_igs:
            assert cert.adjudication_kind != AdjudicationKind.GENUINE_DISAGREE.value, (
                f"{cert.integrand!r}: unexpected GENUINE_DISAGREE"
            )


def test_adjudication_kinds_complete():
    assert AdjudicationKind.NOTATIONAL_ONLY.value == "notational_only"
    assert AdjudicationKind.DOMAIN_RESTRICTED.value == "domain_restricted"
    assert AdjudicationKind.NOT_ADJUDICATED.value == "not_adjudicated"
    assert AdjudicationKind.GENUINE_DISAGREE.value == "genuine_disagree"
