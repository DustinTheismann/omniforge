"""
Verify that the 9 committed runpack manifests for the Risch–Bronstein theorems
are internally consistent and match the current RischVerification.lean source.

Run with:  python -m pytest tests/test_runpack_risch.py -v
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from protocols.runpack_protocol.verify import verify_runpack

REPO_ROOT = Path(__file__).parent.parent
RUNPACKS_DIR = REPO_ROOT / "artifacts" / "runpacks"
LEAN_SOURCE = REPO_ROOT / "fricas_bridge" / "RischVerification.lean"

CLAIM_IDS = [f"pf.integral.bronstein_{i:03d}" for i in range(1, 10)]
MANIFEST_PATHS = [RUNPACKS_DIR / cid / "manifest.json" for cid in CLAIM_IDS]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@pytest.fixture(scope="module")
def lean_source_hash() -> str:
    return _sha256_file(LEAN_SOURCE)


@pytest.fixture(scope="module")
def manifests() -> list[dict]:
    return [json.loads(p.read_text()) for p in MANIFEST_PATHS]


# ---------------------------------------------------------------------------
# File existence
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", MANIFEST_PATHS, ids=lambda p: p.parent.name)
def test_runpack_file_exists(path: Path):
    assert path.exists(), f"Missing runpack: {path}"


# ---------------------------------------------------------------------------
# Schema + manifest_hash integrity (via verify_runpack)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", MANIFEST_PATHS, ids=lambda p: p.parent.name)
def test_runpack_verifies(path: Path):
    result = verify_runpack(path, root=REPO_ROOT)
    assert result.ok, f"{path.parent.name} verification failed:\n" + "\n".join(result.errors)


# ---------------------------------------------------------------------------
# Core fields
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", MANIFEST_PATHS, ids=lambda p: p.parent.name)
def test_runpack_verification_passed(path: Path):
    m = json.loads(path.read_text())
    assert m["verification_result"] == "passed", (
        f"{path.parent.name}: expected verification_result='passed', got '{m['verification_result']}'"
    )


@pytest.mark.parametrize("path", MANIFEST_PATHS, ids=lambda p: p.parent.name)
def test_runpack_evidence_class_e7(path: Path):
    m = json.loads(path.read_text())
    assert m["evidence_class_claimed"] == "E7_FORMALLY_VERIFIED", (
        f"{path.parent.name}: expected E7_FORMALLY_VERIFIED, got '{m['evidence_class_claimed']}'"
    )


# ---------------------------------------------------------------------------
# Claim ID correspondence
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cid,path", list(zip(CLAIM_IDS, MANIFEST_PATHS)), ids=CLAIM_IDS)
def test_runpack_claim_id(cid: str, path: Path):
    m = json.loads(path.read_text())
    assert m["claim_id"] == cid, f"{path.parent.name}: claim_id mismatch"


# ---------------------------------------------------------------------------
# Stable runpack ID scheme
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cid,path", list(zip(CLAIM_IDS, MANIFEST_PATHS)), ids=CLAIM_IDS)
def test_runpack_id_scheme(cid: str, path: Path):
    m = json.loads(path.read_text())
    expected = f"rp.{cid}.lean430"
    assert m["runpack_id"] == expected, (
        f"{cid}: expected runpack_id='{expected}', got '{m['runpack_id']}'"
    )


# ---------------------------------------------------------------------------
# Tool version pins
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", MANIFEST_PATHS, ids=lambda p: p.parent.name)
def test_runpack_lean4_version(path: Path):
    m = json.loads(path.read_text())
    tv = m["environment"]["tool_versions"]
    assert tv.get("lean4") == "leanprover/lean4:v4.30.0", (
        f"{path.parent.name}: lean4 version not pinned to v4.30.0"
    )


@pytest.mark.parametrize("path", MANIFEST_PATHS, ids=lambda p: p.parent.name)
def test_runpack_mathlib4_version(path: Path):
    m = json.loads(path.read_text())
    tv = m["environment"]["tool_versions"]
    assert tv.get("mathlib4") == "v4.30.0", (
        f"{path.parent.name}: mathlib4 version not pinned to v4.30.0"
    )


# ---------------------------------------------------------------------------
# Lake build commands recorded
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", MANIFEST_PATHS, ids=lambda p: p.parent.name)
def test_runpack_lake_commands(path: Path):
    m = json.loads(path.read_text())
    commands = [c["command"] for c in m["commands"]]
    assert "lake build RischVerification" in commands, (
        f"{path.parent.name}: 'lake build RischVerification' not in commands"
    )
    assert "lake update" in commands, (
        f"{path.parent.name}: 'lake update' not in commands"
    )


# ---------------------------------------------------------------------------
# Artifact SHA-256 matches current RischVerification.lean
# ---------------------------------------------------------------------------

def test_artifact_hashes_match_lean_source(manifests, lean_source_hash):
    for m in manifests:
        cid = m["claim_id"]
        for art in m.get("artifacts", []):
            if "RischVerification.lean" in art["path"]:
                assert art["sha256"] == lean_source_hash, (
                    f"{cid}: artifact sha256 {art['sha256'][:12]}… "
                    f"≠ current {lean_source_hash[:12]}…  "
                    f"(run: python fricas_bridge/proofforge_runpack.py to regenerate)"
                )


# ---------------------------------------------------------------------------
# All 9 runpacks reference RischVerification.lean
# ---------------------------------------------------------------------------

def test_all_runpacks_reference_lean_source(manifests):
    for m in manifests:
        cid = m["claim_id"]
        lean_artifacts = [
            a for a in m.get("artifacts", [])
            if "RischVerification.lean" in a["path"]
        ]
        assert lean_artifacts, f"{cid}: no RischVerification.lean artifact recorded"
