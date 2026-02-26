from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class ProofCheck:
    checker: str
    ok: bool
    returncode: int
    stdout: str
    stderr: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "checker": self.checker,
                "ok": self.ok,
                "returncode": self.returncode,
                "stdout": self.stdout,
                "stderr": self.stderr,
            },
            indent=2,
            sort_keys=True,
        )


@dataclass(frozen=True)
class SatExecResult:
    result: str  # SAT | UNSAT | UNKNOWN | ERROR | TIMEOUT
    stdout: str
    stderr: str
    commandline: list[str]
    drat_relpath: Optional[str]
    lrat_relpath: Optional[str]
    check_drat: Optional[ProofCheck]
    check_lrat: Optional[ProofCheck]


def _repo_bin(root: Path) -> Path:
    return root / "tools" / "bin"


def _require_exe(path: Path) -> None:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"missing executable: {path}")


def _parse_dimacs_status(stdout: str) -> str:
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("s "):
            if "UNSAT" in line:
                return "UNSAT"
            if "SAT" in line:
                return "SAT"
            if "UNKNOWN" in line:
                return "UNKNOWN"
    return "UNKNOWN"


def _run(cmd: list[str], *, cwd: Path, timeout: Optional[int] = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)


def run_sat_two_checker(
    *,
    root: Path,
    cnf_path: Path,
    seed: int,
    wall_seconds: int,
    out_dir: Path,
) -> SatExecResult:
    """
    Two-checker policy:
      - If solver returns UNSAT:
          * require DRAT proof and verify with drat-trim
          * require LRAT proof and verify with lrat-trim
          * fail-closed: if either checker fails => ERROR
      - If SAT/UNKNOWN: proofs optional; we do not require them.
    """
    bin_dir = _repo_bin(root)
    cadical = bin_dir / "cadical"
    drat_trim = bin_dir / "drat-trim"
    lrat_trim = bin_dir / "lrat-trim"

    _require_exe(cadical)
    _require_exe(drat_trim)
    _require_exe(lrat_trim)

    proofs_dir = out_dir / "proofs"
    proofcheck_dir = out_dir / "proofcheck"
    proofs_dir.mkdir(parents=True, exist_ok=True)
    proofcheck_dir.mkdir(parents=True, exist_ok=True)

    drat_path = proofs_dir / "proof.drat"
    lrat_path = proofs_dir / "proof.lrat"

    # 1) Run CaDiCaL to produce DRAT proof (file)
    cmd = [
        str(cadical),
        f"--seed={seed}",
        "--no-binary",
        str(cnf_path),
        str(drat_path),
    ]

    try:
        p = _run(cmd, cwd=root, timeout=wall_seconds)
    except subprocess.TimeoutExpired as e:
        return SatExecResult(
            result="TIMEOUT",
            stdout=e.stdout or "",
            stderr=e.stderr or "",
            commandline=cmd,
            drat_relpath=None,
            lrat_relpath=None,
            check_drat=None,
            check_lrat=None,
        )

    stdout = p.stdout or ""
    stderr = p.stderr or ""
    status = _parse_dimacs_status(stdout)

    if status != "UNSAT":
        # Clean up proofs if created
        if drat_path.exists():
            try:
                drat_path.unlink()
            except Exception:
                pass
        return SatExecResult(
            result=status if p.returncode == 0 else "ERROR",
            stdout=stdout,
            stderr=stderr,
            commandline=cmd,
            drat_relpath=None,
            lrat_relpath=None,
            check_drat=None,
            check_lrat=None,
        )

    # Fail-closed: UNSAT requires DRAT proof file
    if (not drat_path.exists()) or drat_path.stat().st_size == 0:
        return SatExecResult(
            result="ERROR",
            stdout=stdout,
            stderr=stderr + "\nmissing or empty DRAT proof\n",
            commandline=cmd,
            drat_relpath=None,
            lrat_relpath=None,
            check_drat=None,
            check_lrat=None,
        )

    # 2) Verify DRAT with drat-trim
    chk_drat_cp = _run([str(drat_trim), str(cnf_path), str(drat_path)], cwd=root)
    chk_drat = ProofCheck(
        checker="drat-trim",
        ok=(chk_drat_cp.returncode == 0),
        returncode=chk_drat_cp.returncode,
        stdout=chk_drat_cp.stdout or "",
        stderr=chk_drat_cp.stderr or "",
    )
    (proofcheck_dir / "drat-trim.json").write_text(chk_drat.to_json(), encoding="utf-8")

    # 3) Produce LRAT proof.
    # CaDiCaL can emit LRAT via --lrat; send proof to stdout by passing '-' as output.
    # We keep stderr/stdout separate from the earlier run; this is proof material only.
    lrat_cp = _run(
        [str(cadical), f"--seed={seed}", "--lrat", str(cnf_path), "-"],
        cwd=root,
        timeout=wall_seconds,
    )
    lrat_text = lrat_cp.stdout or ""
    lrat_path.write_text(lrat_text, encoding="utf-8")

    if lrat_path.stat().st_size == 0:
        return SatExecResult(
            result="ERROR",
            stdout=stdout,
            stderr=stderr + "\nmissing or empty LRAT proof\n",
            commandline=cmd,
            drat_relpath=str(drat_path.relative_to(out_dir)),
            lrat_relpath=None,
            check_drat=chk_drat,
            check_lrat=None,
        )

    # 4) Verify LRAT with lrat-trim
    chk_lrat_cp = _run([str(lrat_trim), str(cnf_path), str(lrat_path)], cwd=root)
    chk_lrat = ProofCheck(
        checker="lrat-trim",
        ok=(chk_lrat_cp.returncode == 0),
        returncode=chk_lrat_cp.returncode,
        stdout=chk_lrat_cp.stdout or "",
        stderr=chk_lrat_cp.stderr or "",
    )
    (proofcheck_dir / "lrat-trim.json").write_text(chk_lrat.to_json(), encoding="utf-8")

    # Fail-closed on both checkers
    if not (chk_drat.ok and chk_lrat.ok):
        return SatExecResult(
            result="ERROR",
            stdout=stdout,
            stderr=stderr + "\nUNSAT proof verification failed (two-checker)\n",
            commandline=cmd,
            drat_relpath=str(drat_path.relative_to(out_dir)),
            lrat_relpath=str(lrat_path.relative_to(out_dir)),
            check_drat=chk_drat,
            check_lrat=chk_lrat,
        )

    return SatExecResult(
        result="UNSAT",
        stdout=stdout,
        stderr=stderr,
        commandline=cmd,
        drat_relpath=str(drat_path.relative_to(out_dir)),
        lrat_relpath=str(lrat_path.relative_to(out_dir)),
        check_drat=chk_drat,
        check_lrat=chk_lrat,
    )
