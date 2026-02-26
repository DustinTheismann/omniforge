from __future__ import annotations

import json
import secrets
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from omniforge.artifacts.manifest import sha256_file
from omniforge.lanes.sat_lane import run_sat_two_checker


def _load_schema(root: Path, rel: str) -> dict[str, Any]:
    return json.loads((root / rel).read_text(encoding="utf-8"))


def create_demo_run_bundle(root: Path) -> str:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4)
    out_dir = root / "artifacts" / f"run_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=False)

    bench_suite = "sat.tiny"
    case_id = "tiny/unsat_contradiction.cnf"
    cnf_src = root / "benches" / "sat" / case_id
    if not cnf_src.exists():
        raise FileNotFoundError(f"missing benchmark CNF: {cnf_src}")

    cnf_dst = out_dir / "input.cnf"
    shutil.copyfile(cnf_src, cnf_dst)

    res = run_sat_two_checker(
        root=root,
        cnf_path=cnf_dst,
        seed=0,
        wall_seconds=5,
        out_dir=out_dir,
    )

    # Fail-closed demo: must be UNSAT verified by two checkers
    if res.result != "UNSAT":
        raise RuntimeError(f"demo expected UNSAT, got {res.result}")

    # Write solver logs
    (out_dir / "solver_stdout.txt").write_text(res.stdout, encoding="utf-8")
    (out_dir / "solver_stderr.txt").write_text(res.stderr, encoding="utf-8")

    manifest: dict[str, Any] = {
        "manifest_version": "0.3.0",
        "run_id": run_id,
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lane": "sat",
        "inputs": {"bench_suite": bench_suite, "case_id": case_id, "bundle_cnf_path": "input.cnf"},
        "candidate": {
            "executor": "cadical",
            "genome": {"seed": 0, "notes": "two-checker UNSAT verification"},
            "commandline": res.commandline,
            "proof_policy": {"unsat_requires_two_checkers": True, "checkers": ["drat-trim", "lrat-trim"]},
        },
        "outputs": {
            "result": res.result,
            "stdout_path": "solver_stdout.txt",
            "stderr_path": "solver_stderr.txt",
            "drat_proof_path": res.drat_relpath,
            "lrat_proof_path": res.lrat_relpath,
            "drat_check_path": "proofcheck/drat-trim.json",
            "lrat_check_path": "proofcheck/lrat-trim.json",
        },
        "hashes": {},
    }

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    # Hash everything relevant
    hashes: dict[str, str] = {
        "input.cnf": sha256_file(cnf_dst),
        "solver_stdout.txt": sha256_file(out_dir / "solver_stdout.txt"),
        "solver_stderr.txt": sha256_file(out_dir / "solver_stderr.txt"),
        "manifest.json": sha256_file(manifest_path),
    }

    for rel in [res.drat_relpath, res.lrat_relpath, "proofcheck/drat-trim.json", "proofcheck/lrat-trim.json"]:
        if rel:
            hashes[rel] = sha256_file(out_dir / rel)

    manifest["hashes"] = hashes
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    # Validate schema
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
    details: list[str] = []
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
