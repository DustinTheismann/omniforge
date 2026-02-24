from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


def _load_schema(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_contracts(root: Path) -> None:
    contracts_dir = root / "omniforge" / "contracts"
    eval_schema = _load_schema(contracts_dir / "eval_contract.schema.json")
    art_schema = _load_schema(contracts_dir / "artifact_manifest.schema.json")

    # Ensure schemas are themselves valid Draft 2020-12 schemas
    Draft202012Validator.check_schema(eval_schema)
    Draft202012Validator.check_schema(art_schema)

    # Validate sample instances
    sample_eval = {
        "version": "0.2.0",
        "lane": "sat",
        "benchmarks": {"suite_id": "sat.tiny", "cases": ["uf20-01.cnf"]},
        "resources": {"cpu_seconds": 2, "memory_mb": 256, "wall_seconds": 2},
        "determinism": {"seed": 0, "threads": 1, "env_locked": True},
        "evidence_requirements": {
            "require_artifacts": True,
            "require_hash_manifest": True,
            "unsat_requires_proof": True,
            "proof_checker": "placeholder"
        },
    }
    Draft202012Validator(eval_schema).validate(sample_eval)

    sample_manifest = {
        "manifest_version": "0.2.0",
        "run_id": "demo",
        "timestamp_utc": "1970-01-01T00:00:00Z",
        "lane": "sat",
        "inputs": {"bench_suite": "sat.tiny", "case_id": "uf20-01.cnf"},
        "candidate": {"executor": "placeholder", "genome": {"example": 1}, "commandline": ["solver", "--flag"]},
        "outputs": {"result": "UNKNOWN", "stdout_path": "stdout.txt", "stderr_path": "stderr.txt"},
        "hashes": {"stdout.txt": "0"*64, "stderr.txt": "0"*64, "manifest.json": "0"*64}
    }
    Draft202012Validator(art_schema).validate(sample_manifest)
