"""
Tier 4.4 — Hash-chained runpack and replay verifier.

A runpack is a tamper-detectable manifest pinning the exact versions and
artifact SHA-256s needed to replay a proof obligation.  The chain is:

  manifest SHA-256  ←  sha256(json(entries sorted by key))
  entry SHA-256     ←  sha256(file-bytes)  for file entries
                    ←  sha256(content.encode())  for inline entries

The runpack_id referenced on an Obligation links to the manifest.  Replay
verification re-hashes every entry and checks against the recorded hash.

Public API
----------
RunpackEntry                    dataclass  (one pinned artifact)
Runpack                         dataclass  (the full manifest)
build_runpack(claim_id, ...)    → Runpack
verify_runpack(runpack, root)   → bool
replay_runpack(runpack, root)   → ReplayReport
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class RunpackEntry:
    kind: str              # "file" | "inline"
    name: str              # human label
    path: Optional[str]    # relative path (for file entries)
    content: Optional[str] # inline string (for inline entries)
    sha256: str            # recorded hash


@dataclass
class Runpack:
    runpack_id: str
    claim_id: str
    lean_version: str
    mathlib_version: str
    entries: list[RunpackEntry]
    manifest_sha256: str   # hash of sorted-key JSON of entries

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReplayReport:
    runpack_id: str
    claim_id: str
    ok: bool
    n_entries: int
    n_verified: int
    failures: list[str]   # entry names that failed


# ---------------------------------------------------------------------------
# Hashing helpers
# ---------------------------------------------------------------------------

def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha256_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    return _sha256_bytes(path.read_bytes())


def _manifest_hash(entries: list[RunpackEntry]) -> str:
    """Canonical hash of the entries list (sorted by name for determinism)."""
    payload = json.dumps(
        [asdict(e) for e in sorted(entries, key=lambda e: e.name)],
        sort_keys=True,
    ).encode()
    return _sha256_bytes(payload)


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build_runpack(
    claim_id: str,
    *,
    lean_version: str = "v4.30.0",
    mathlib_version: str = "v4.30.0",
    artifact_paths: Optional[list[str]] = None,
    inline_entries: Optional[list[tuple[str, str]]] = None,
    root: Optional[Path] = None,
) -> Runpack:
    """
    Build a Runpack for a claim.

    artifact_paths   — list of repo-relative file paths to pin
    inline_entries   — list of (name, content) pairs to pin inline
    """
    base = root if root is not None else _REPO_ROOT
    entries: list[RunpackEntry] = []

    for path_str in (artifact_paths or []):
        p = (base / path_str).resolve()
        sha = _sha256_file(p)
        entries.append(RunpackEntry(
            kind="file",
            name=path_str,
            path=path_str,
            content=None,
            sha256=sha or "",
        ))

    for name, content in (inline_entries or []):
        sha = _sha256_bytes(content.encode())
        entries.append(RunpackEntry(
            kind="inline",
            name=name,
            path=None,
            content=content,
            sha256=sha,
        ))

    suffix = claim_id.split("_")[-1] if "_" in claim_id else claim_id
    runpack_id = f"rp.{claim_id}.lean{lean_version}"
    manifest_sha = _manifest_hash(entries)

    return Runpack(
        runpack_id=runpack_id,
        claim_id=claim_id,
        lean_version=lean_version,
        mathlib_version=mathlib_version,
        entries=entries,
        manifest_sha256=manifest_sha,
    )


# ---------------------------------------------------------------------------
# Verify / replay
# ---------------------------------------------------------------------------

def verify_runpack(runpack: Runpack, *, root: Optional[Path] = None) -> bool:
    """
    Return True iff the runpack's manifest_sha256 matches a recomputation
    from its entry list.  Does NOT check whether individual files still match
    their recorded hashes — use replay_runpack for that.
    """
    return _manifest_hash(runpack.entries) == runpack.manifest_sha256


def replay_runpack(runpack: Runpack, *, root: Optional[Path] = None) -> ReplayReport:
    """
    Re-hash every entry and compare to the recorded hashes.

    Returns a ReplayReport with per-entry verification results.
    """
    base = root if root is not None else _REPO_ROOT
    failures: list[str] = []
    n_verified = 0

    for entry in runpack.entries:
        if entry.kind == "file":
            p = (base / entry.path).resolve() if entry.path else None
            computed = _sha256_file(p) if p else None
        else:
            computed = _sha256_bytes(entry.content.encode()) if entry.content else None

        if computed is None:
            failures.append(f"{entry.name}: file not found")
        elif computed != entry.sha256:
            failures.append(f"{entry.name}: hash mismatch (got {computed[:8]}…, want {entry.sha256[:8]}…)")
        else:
            n_verified += 1

    return ReplayReport(
        runpack_id=runpack.runpack_id,
        claim_id=runpack.claim_id,
        ok=len(failures) == 0,
        n_entries=len(runpack.entries),
        n_verified=n_verified,
        failures=failures,
    )
