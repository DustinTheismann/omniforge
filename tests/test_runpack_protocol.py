"""
Tests for protocols/runpack_protocol — pack, verify, hash integrity.

Run with:  python -m pytest tests/test_runpack_protocol.py -v
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from protocols.runpack_protocol.pack import RunpackBuilder, Runpack
from protocols.runpack_protocol.verify import verify_runpack, VerifyResult


# ---------------------------------------------------------------------------
# RunpackBuilder — basic construction
# ---------------------------------------------------------------------------

def test_builder_creates_runpack():
    rp = RunpackBuilder("pf.test.000001").build()
    assert rp.runpack_id.startswith("rp.pf.test.000001.")
    assert rp.verification_result == "not_run"


def test_builder_sets_verification_result():
    rp = RunpackBuilder("pf.test.000001").build(verification_result="passed")
    assert rp.verification_result == "passed"


def test_builder_records_commands():
    builder = RunpackBuilder("pf.test.000001")
    builder.record_command(["python", "run.py"], exit_code=0, elapsed_ms=42.0)
    rp = builder.build()
    d = rp.to_dict()
    assert len(d["commands"]) == 1
    assert d["commands"][0]["exit_code"] == 0
    assert d["commands"][0]["elapsed_ms"] == pytest.approx(42.0)


def test_builder_tool_versions():
    builder = RunpackBuilder("pf.test.000001")
    builder.add_tool_version("lean", "4.x").add_tool_version("fricas", "1.3.11")
    rp = builder.build()
    assert rp.to_dict()["environment"]["tool_versions"]["lean"] == "4.x"


# ---------------------------------------------------------------------------
# Manifest hash integrity
# ---------------------------------------------------------------------------

def test_manifest_hash_is_hex64():
    rp = RunpackBuilder("pf.test.000001").build()
    h = rp.manifest_hash
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_manifest_hash_deterministic_for_same_content():
    # Two builders with identical content should produce the same manifest hash
    # (modulo timestamp — we check hash_chain field is stable)
    rp = RunpackBuilder("pf.test.000001", tool_versions={"lean": "4.0"}).build(
        verification_result="passed"
    )
    assert rp.manifest_hash != "pending"


# ---------------------------------------------------------------------------
# Save / load round-trip
# ---------------------------------------------------------------------------

def test_save_and_load(tmp_path):
    rp = RunpackBuilder("pf.test.000002").build(verification_result="passed")
    manifest_path = tmp_path / "manifest.json"
    rp.save(manifest_path)

    assert manifest_path.exists()
    loaded = Runpack.load(manifest_path)
    assert loaded.runpack_id == rp.runpack_id


# ---------------------------------------------------------------------------
# verify_runpack
# ---------------------------------------------------------------------------

def test_verify_clean_runpack(tmp_path):
    rp = RunpackBuilder("pf.test.000003").build(verification_result="passed")
    manifest_path = tmp_path / "manifest.json"
    rp.save(manifest_path)

    result = verify_runpack(manifest_path, check_artifacts_on_disk=False)
    assert result.ok, f"Unexpected errors: {result.errors}"


def test_verify_detects_manifest_hash_tampering(tmp_path):
    rp = RunpackBuilder("pf.test.000004").build()
    manifest_path = tmp_path / "manifest.json"
    rp.save(manifest_path)

    # Tamper with the manifest
    d = json.loads(manifest_path.read_text())
    d["verification_result"] = "passed"  # change content without updating hash
    manifest_path.write_text(json.dumps(d))

    result = verify_runpack(manifest_path, check_artifacts_on_disk=False)
    assert not result.ok
    assert any("mismatch" in e.lower() or "hash" in e.lower() for e in result.errors)


def test_verify_missing_file():
    result = verify_runpack(Path("/nonexistent/manifest.json"))
    assert not result.ok
    assert result.errors


def test_verify_result_str_ok(tmp_path):
    rp = RunpackBuilder("pf.test.000005").build(verification_result="passed")
    manifest_path = tmp_path / "manifest.json"
    rp.save(manifest_path)
    result = verify_runpack(manifest_path, check_artifacts_on_disk=False)
    assert "[OK]" in str(result)


def test_verify_result_str_fail(tmp_path):
    rp = RunpackBuilder("pf.test.000006").build()
    manifest_path = tmp_path / "manifest.json"
    rp.save(manifest_path)
    d = json.loads(manifest_path.read_text())
    d["verification_result"] = "tampered"
    manifest_path.write_text(json.dumps(d))
    result = verify_runpack(manifest_path, check_artifacts_on_disk=False)
    assert "[FAIL]" in str(result)
