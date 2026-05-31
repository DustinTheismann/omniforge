"""
Runpack packer.

Creates a runpack manifest from a claim + list of executed commands/artifacts.
Every artifact file is hashed (SHA-256). The manifest itself is hashed last
and the hash is written into hash_chain.manifest_hash.

Usage:
    from protocols.runpack_protocol.pack import pack_runpack, RunpackBuilder

    builder = RunpackBuilder(claim_id="pf.integral.000001")
    builder.record_command(["python", "run.py"], cwd=".", exit_code=0)
    builder.record_artifact("artifacts/theorem.lean", role="theorem")
    manifest = builder.build(verification_result="passed")
    manifest.save(Path("runpacks/pf.integral.000001/manifest.json"))
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass
class CommandRecord:
    seq:         int
    command:     list[str] | str
    cwd:         Optional[str]
    exit_code:   int
    stdout_hash: Optional[str] = None
    stderr_hash: Optional[str] = None
    elapsed_ms:  Optional[float] = None

    def to_dict(self) -> dict:
        cmd = self.command if isinstance(self.command, str) else " ".join(self.command)
        return {
            "seq":         self.seq,
            "command":     cmd,
            "cwd":         self.cwd,
            "exit_code":   self.exit_code,
            "stdout_hash": self.stdout_hash,
            "stderr_hash": self.stderr_hash,
            "elapsed_ms":  self.elapsed_ms,
        }


@dataclass
class ArtifactRecord:
    path:       str
    role:       str
    sha256:     str
    size_bytes: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "path":       self.path,
            "role":       self.role,
            "sha256":     self.sha256,
            "size_bytes": self.size_bytes,
        }


class RunpackBuilder:
    def __init__(
        self,
        claim_id: str,
        schema_version: str = "0.1.0",
        tool_versions: Optional[dict] = None,
    ) -> None:
        self.claim_id      = claim_id
        self.schema_version= schema_version
        self._commands:  list[CommandRecord]  = []
        self._artifacts: list[ArtifactRecord] = []
        self._tool_versions = tool_versions or {}
        self._created_at = datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------

    def record_command(
        self,
        command: list[str] | str,
        *,
        cwd: Optional[str] = None,
        exit_code: int = 0,
        stdout: Optional[str] = None,
        stderr: Optional[str] = None,
        elapsed_ms: Optional[float] = None,
    ) -> "RunpackBuilder":
        seq = len(self._commands)
        self._commands.append(CommandRecord(
            seq=seq,
            command=command,
            cwd=cwd,
            exit_code=exit_code,
            stdout_hash=_sha256_text(stdout) if stdout else None,
            stderr_hash=_sha256_text(stderr) if stderr else None,
            elapsed_ms=elapsed_ms,
        ))
        return self

    def record_artifact(
        self,
        path: str | Path,
        *,
        role: str = "output",
    ) -> "RunpackBuilder":
        p = Path(path)
        self._artifacts.append(ArtifactRecord(
            path=str(p),
            role=role,
            sha256=_sha256(p) if p.exists() else "0" * 64,
            size_bytes=p.stat().st_size if p.exists() else None,
        ))
        return self

    def add_tool_version(self, name: str, version: str) -> "RunpackBuilder":
        self._tool_versions[name] = version
        return self

    # ------------------------------------------------------------------

    def build(
        self,
        verification_result: str = "not_run",
        evidence_class: Optional[str] = None,
        claim_hash: Optional[str] = None,
    ) -> "Runpack":
        ts_ms = int(time.time() * 1000)
        runpack_id = f"rp.{self.claim_id}.{ts_ms}"

        manifest: dict = {
            "runpack_id":       runpack_id,
            "claim_id":         self.claim_id,
            "schema_version":   self.schema_version,
            "created_at":       self._created_at,
            "environment": {
                "platform":        platform.platform(),
                "python_version":  sys.version,
                "tool_versions":   self._tool_versions,
                "container_image": None,
                "env_vars":        {},
            },
            "commands":          [c.to_dict() for c in self._commands],
            "artifacts":         [a.to_dict() for a in self._artifacts],
            "verification_result": verification_result,
            "evidence_class_claimed": evidence_class,
            "hash_chain": {
                "manifest_hash": "pending",
                "claim_hash":    claim_hash,
                "prior_runpack": None,
            },
        }

        # Compute manifest hash (hash of the manifest with hash_chain.manifest_hash == "pending")
        manifest_text = json.dumps(manifest, sort_keys=True)
        manifest["hash_chain"]["manifest_hash"] = _sha256_text(manifest_text)

        return Runpack(manifest)


@dataclass
class Runpack:
    _manifest: dict

    @property
    def manifest_hash(self) -> str:
        return self._manifest["hash_chain"]["manifest_hash"]

    @property
    def runpack_id(self) -> str:
        return self._manifest["runpack_id"]

    @property
    def verification_result(self) -> str:
        return self._manifest["verification_result"]

    def to_dict(self) -> dict:
        return dict(self._manifest)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._manifest, indent=2))

    @classmethod
    def load(cls, path: Path) -> "Runpack":
        return cls(json.loads(path.read_text()))
