"""
Runpack verifier.

Checks that a runpack manifest is internally consistent:
  1. manifest_hash matches recomputed hash
  2. all artifact sha256 hashes match files on disk (when present)
  3. schema validates

Usage:
    from protocols.runpack_protocol.verify import verify_runpack

    result = verify_runpack(Path("runpacks/pf.integral.000001/manifest.json"))
    if not result.ok:
        print(result.errors)
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema

_SCHEMA_PATH = Path(__file__).parent / "manifest.schema.json"
_schema: dict | None = None


def _load_schema() -> dict:
    global _schema
    if _schema is None:
        _schema = json.loads(_SCHEMA_PATH.read_text())
    return _schema


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class VerifyResult:
    ok: bool
    runpack_id: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        status = "OK" if self.ok else "FAIL"
        parts = [f"[{status}] {self.runpack_id}"]
        for e in self.errors:
            parts.append(f"  ERROR: {e}")
        for w in self.warnings:
            parts.append(f"  WARN:  {w}")
        return "\n".join(parts)


def verify_runpack(
    path: Path,
    *,
    check_artifacts_on_disk: bool = True,
) -> VerifyResult:
    """
    Verify the runpack manifest at *path*.

    Returns a VerifyResult. Never raises — all failures are reported as errors.
    """
    errors: list[str] = []
    warnings: list[str] = []

    try:
        raw = path.read_text()
        manifest = json.loads(raw)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        return VerifyResult(ok=False, runpack_id="<unknown>", errors=[str(exc)])

    runpack_id = manifest.get("runpack_id", "<unknown>")

    # 1. Schema validation
    schema = _load_schema()
    validator = jsonschema.Draft202012Validator(schema)
    schema_errors = [e.message for e in validator.iter_errors(manifest)]
    errors.extend(schema_errors)

    # 2. Manifest hash check
    stored_hash = manifest.get("hash_chain", {}).get("manifest_hash", "")
    if stored_hash and stored_hash != "pending":
        # Recompute: set hash_chain.manifest_hash to "pending", serialise, hash
        import copy
        m2 = copy.deepcopy(manifest)
        m2["hash_chain"]["manifest_hash"] = "pending"
        expected = _sha256_text(json.dumps(m2, sort_keys=True))
        if expected != stored_hash:
            errors.append(
                f"manifest_hash mismatch: stored={stored_hash[:16]}… "
                f"computed={expected[:16]}…"
            )

    # 3. Artifact hash checks
    if check_artifacts_on_disk:
        base = path.parent
        for art in manifest.get("artifacts", []):
            art_path = base / art["path"] if not Path(art["path"]).is_absolute() else Path(art["path"])
            if art_path.exists():
                actual = _sha256_file(art_path)
                if actual != art.get("sha256", ""):
                    errors.append(
                        f"artifact {art['path']}: hash mismatch "
                        f"stored={art.get('sha256','')[:16]}… actual={actual[:16]}…"
                    )
            else:
                warnings.append(f"artifact not on disk: {art['path']}")

    return VerifyResult(ok=not errors, runpack_id=runpack_id, errors=errors, warnings=warnings)
