from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from omniforge.artifacts.manifest import sha256_file
from omniforge.lanes.sat_lane import placeholder_sat_executor


def _load_schema(root: Path, rel: str) -> dict[str, Any]:
    p = root / rel
    return json.loads(p.read_text(encoding="utf-8"))


def create_demo_run_bundle(root: Path) -> str:
    """Create a minimal run bundle under artifacts/ and validate its manifest."""
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4)
    out_dir = root / "artifacts" / f"run_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=False)

    result, stdout, stderr = placeholder_sat_executor()

    stdout_path = out_dir / "stdout.txt"
    stderr_path = out_dir / "stderr.txt"
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")

    manifest = {
        "manifest_version": "0.2.0",
        "run_id": run_id,
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lane": "sat",
        "inputs": {"bench_suite": "sat.tiny", "case_id": "uf20-01.cnf"},
        "candidate": {
            "executor": "placeholder_sat_executor",
            "genome": {"seed": 0, "notes": "v0.2-seed placeholder"},
            "commandline": ["placeholder_solver", "--seed", "0"],
        },
        "outputs": {
            "result": result,
            "stdout_path": "stdout.txt",
            "stderr_path": "stderr.txt",
        },
        "hashes": {}
    }

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    hashes = {
        "stdout.txt": sha256_file(stdout_path),
        "stderr.txt": sha256_file(stderr_path),
        "manifest.json": sha256_file(manifest_path),
    }

    manifest["hashes"] = hashes
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    # Validate manifest
    schema = _load_schema(root, "omniforge/contracts/artifact_manifest.schema.json")
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)

    return run_id


def verify_run_bundle_hashes(root: Path, run_id: str) -> tuple[bool, str]:
    run_dir = root / "artifacts" / f"run_{run_id}"
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return False, f"manifest not found: {manifest_path}"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = manifest.get("hashes", {})
    if not isinstance(expected, dict):
        return False, "invalid hashes field"

    details = []
    ok = True
    for rel, exp in expected.items():
        p = run_dir / rel
        if not p.exists():
            ok = False
            details.append(f"missing: {rel}")
            continue
        got = sha256_file(p)
        if got != exp:
            ok = False
            details.append(f"mismatch: {rel} expected={exp} got={got}")

    return ok, "\n".join(details)
