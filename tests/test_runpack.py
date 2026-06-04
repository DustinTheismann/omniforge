"""
Tests for Tier 4.4 — hash-chained runpack replay verifier.

Run with:  python -m pytest tests/test_runpack.py -v
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from protocols.runpack import (
    Runpack,
    RunpackEntry,
    ReplayReport,
    build_runpack,
    verify_runpack,
    replay_runpack,
    _manifest_hash,
)


_LEAN_ARTIFACT = "fricas_bridge/RischAutoDischarge.lean"
_COQ_ARTIFACT  = "cross_prover/RischCoqDischarge.v"


# ---------------------------------------------------------------------------
# build_runpack
# ---------------------------------------------------------------------------

def test_build_runpack_returns_dataclass():
    rp = build_runpack("pf.integral.bronstein_007")
    assert isinstance(rp, Runpack)


def test_build_runpack_claim_id():
    rp = build_runpack("pf.integral.bronstein_007")
    assert rp.claim_id == "pf.integral.bronstein_007"


def test_build_runpack_has_runpack_id():
    rp = build_runpack("pf.integral.bronstein_007")
    assert "pf.integral.bronstein_007" in rp.runpack_id
    assert rp.runpack_id.startswith("rp.")


def test_build_runpack_version_defaults():
    rp = build_runpack("pf.integral.bronstein_007")
    assert "v4.30.0" in rp.lean_version
    assert "v4.30.0" in rp.mathlib_version


def test_build_runpack_with_file_entry():
    rp = build_runpack(
        "pf.integral.bronstein_007",
        artifact_paths=[_LEAN_ARTIFACT],
    )
    assert len(rp.entries) == 1
    assert rp.entries[0].kind == "file"
    assert len(rp.entries[0].sha256) == 64


def test_build_runpack_with_inline_entry():
    rp = build_runpack(
        "pf.integral.bronstein_007",
        inline_entries=[("statement", "HasDerivAt (fun x => log x) (1/x) x")],
    )
    assert len(rp.entries) == 1
    e = rp.entries[0]
    assert e.kind == "inline"
    assert e.content is not None
    assert len(e.sha256) == 64


def test_build_runpack_two_artifact_sources():
    rp = build_runpack(
        "pf.integral.bronstein_007",
        artifact_paths=[_LEAN_ARTIFACT, _COQ_ARTIFACT],
    )
    assert len(rp.entries) == 2


def test_build_runpack_has_manifest_hash():
    rp = build_runpack("pf.integral.bronstein_007", artifact_paths=[_LEAN_ARTIFACT])
    assert len(rp.manifest_sha256) == 64


def test_build_runpack_manifest_deterministic():
    rp1 = build_runpack("pf.integral.bronstein_007", artifact_paths=[_LEAN_ARTIFACT])
    rp2 = build_runpack("pf.integral.bronstein_007", artifact_paths=[_LEAN_ARTIFACT])
    assert rp1.manifest_sha256 == rp2.manifest_sha256


# ---------------------------------------------------------------------------
# verify_runpack (manifest integrity only)
# ---------------------------------------------------------------------------

def test_verify_runpack_fresh_build_passes():
    rp = build_runpack("pf.integral.bronstein_007", artifact_paths=[_LEAN_ARTIFACT])
    assert verify_runpack(rp) is True


def test_verify_runpack_tampered_manifest_fails():
    rp = build_runpack("pf.integral.bronstein_007", artifact_paths=[_LEAN_ARTIFACT])
    tampered = Runpack(
        runpack_id=rp.runpack_id,
        claim_id=rp.claim_id,
        lean_version=rp.lean_version,
        mathlib_version=rp.mathlib_version,
        entries=rp.entries,
        manifest_sha256="0" * 64,
    )
    assert verify_runpack(tampered) is False


def test_verify_runpack_entry_mutation_fails():
    rp = build_runpack(
        "pf.integral.bronstein_007",
        inline_entries=[("stmt", "original content")],
    )
    # Mutate an entry's sha256 directly
    rp.entries[0] = RunpackEntry(
        kind="inline",
        name="stmt",
        path=None,
        content="original content",
        sha256="0" * 64,
    )
    # The manifest hash was computed from the original; recomputing will differ
    assert verify_runpack(rp) is False


# ---------------------------------------------------------------------------
# replay_runpack (per-entry hash verification)
# ---------------------------------------------------------------------------

def test_replay_runpack_all_ok():
    rp = build_runpack(
        "pf.integral.bronstein_007",
        artifact_paths=[_LEAN_ARTIFACT],
        inline_entries=[("integrand", "1 / x")],
    )
    report = replay_runpack(rp)
    assert isinstance(report, ReplayReport)
    assert report.ok is True
    assert report.n_verified == 2
    assert report.failures == []


def test_replay_runpack_missing_file():
    rp = build_runpack(
        "pf.integral.bronstein_007",
        artifact_paths=["nonexistent/file.lean"],
    )
    report = replay_runpack(rp)
    assert report.ok is False
    assert report.n_verified == 0
    assert len(report.failures) == 1


def test_replay_runpack_tampered_inline():
    rp = build_runpack(
        "pf.integral.bronstein_007",
        inline_entries=[("stmt", "correct content")],
    )
    # Replace content but keep old hash → mismatch
    rp.entries[0] = RunpackEntry(
        kind="inline",
        name="stmt",
        path=None,
        content="tampered content",
        sha256=rp.entries[0].sha256,   # stale hash
    )
    report = replay_runpack(rp)
    assert report.ok is False
    assert len(report.failures) == 1
    assert "mismatch" in report.failures[0]


def test_replay_report_fields():
    rp = build_runpack("pf.integral.bronstein_007", artifact_paths=[_LEAN_ARTIFACT])
    report = replay_runpack(rp)
    assert report.runpack_id == rp.runpack_id
    assert report.claim_id == rp.claim_id
    assert report.n_entries == len(rp.entries)


# ---------------------------------------------------------------------------
# to_dict serialisability
# ---------------------------------------------------------------------------

def test_runpack_to_dict():
    import json
    rp = build_runpack("pf.integral.bronstein_007", artifact_paths=[_LEAN_ARTIFACT])
    d = rp.to_dict()
    json.dumps(d)  # must not raise
    assert d["claim_id"] == "pf.integral.bronstein_007"
    assert "entries" in d


# ---------------------------------------------------------------------------
# manifest_hash is order-independent
# ---------------------------------------------------------------------------

def test_manifest_hash_order_independent():
    e1 = RunpackEntry("inline", "a", None, "hello", "h1")
    e2 = RunpackEntry("inline", "b", None, "world", "h2")
    h1 = _manifest_hash([e1, e2])
    h2 = _manifest_hash([e2, e1])
    assert h1 == h2
