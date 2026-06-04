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
    check_cake_lpr: Optional[ProofCheck]


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


def _run(
    cmd: list[str], *, cwd: Path, timeout: Optional[int] = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout
    )


def run_sat_two_checker(
    *,
    root: Path,
    cnf_path: Path,
    seed: int,
    wall_seconds: int,
    out_dir: Path,
) -> SatExecResult:
    """
    Three-checker UNSAT policy (name kept for API compatibility):
      - Solver (CaDiCaL) must return UNSAT with a DRAT proof.
      - Gate 1: drat-trim verifies the DRAT proof.
      - Gate 2: lrat-trim verifies a separately-produced LRAT proof.
      - Gate 3: cake_lpr (HOL4-formally-verified) verifies the same LRAT proof.
    All three gates must pass; any failure => ERROR (fail-closed).
    SAT/UNKNOWN/TIMEOUT results skip proof checking.
    """
    bin_dir = _repo_bin(root)
    cadical = bin_dir / "cadical"
    drat_trim = bin_dir / "drat-trim"
    lrat_trim = bin_dir / "lrat-trim"
    cake_lpr = bin_dir / "cake_lpr"

    _require_exe(cadical)
    _require_exe(drat_trim)
    _require_exe(lrat_trim)
    _require_exe(cake_lpr)

    proofs_dir = out_dir / "proofs"
    proofcheck_dir = out_dir / "proofcheck"
    proofs_dir.mkdir(parents=True, exist_ok=True)
    proofcheck_dir.mkdir(parents=True, exist_ok=True)

    drat_path = proofs_dir / "proof.drat"
    lrat_path = proofs_dir / "proof.lrat"

    # 1) Run CaDiCaL → DRAT proof (text format via --no-binary)
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
            check_cake_lpr=None,
        )

    stdout = p.stdout or ""
    stderr = p.stderr or ""
    status = _parse_dimacs_status(stdout)

    if status != "UNSAT":
        for f in (drat_path,):
            if f.exists():
                try:
                    f.unlink()
                except Exception:
                    pass
        return SatExecResult(
            result=status if p.returncode in (10, 20) else "ERROR",
            stdout=stdout,
            stderr=stderr,
            commandline=cmd,
            drat_relpath=None,
            lrat_relpath=None,
            check_drat=None,
            check_lrat=None,
            check_cake_lpr=None,
        )

    # Fail-closed: UNSAT requires non-empty DRAT proof
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
            check_cake_lpr=None,
        )

    # 2) Gate 1: verify DRAT with drat-trim
    chk_drat_cp = _run([str(drat_trim), str(cnf_path), str(drat_path)], cwd=root)
    chk_drat = ProofCheck(
        checker="drat-trim",
        ok=(chk_drat_cp.returncode == 0),
        returncode=chk_drat_cp.returncode,
        stdout=chk_drat_cp.stdout or "",
        stderr=chk_drat_cp.stderr or "",
    )
    (proofcheck_dir / "drat-trim.json").write_text(chk_drat.to_json(), encoding="utf-8")

    # 3) Produce LRAT proof via CaDiCaL (binary format)
    lrat_cp = _run(
        [str(cadical), f"--seed={seed}", "--lrat", str(cnf_path), str(lrat_path)],
        cwd=root,
        timeout=wall_seconds,
    )

    if (not lrat_path.exists()) or lrat_path.stat().st_size == 0:
        return SatExecResult(
            result="ERROR",
            stdout=stdout,
            stderr=stderr + "\nmissing or empty LRAT proof\n",
            commandline=cmd,
            drat_relpath=str(drat_path.relative_to(out_dir)),
            lrat_relpath=None,
            check_drat=chk_drat,
            check_lrat=None,
            check_cake_lpr=None,
        )

    # 4) Gate 2: verify LRAT with lrat-trim (DIMACS convention: exit 20 = UNSAT verified)
    chk_lrat_cp = _run([str(lrat_trim), str(cnf_path), str(lrat_path)], cwd=root)
    chk_lrat = ProofCheck(
        checker="lrat-trim",
        ok=(chk_lrat_cp.returncode == 20),
        returncode=chk_lrat_cp.returncode,
        stdout=chk_lrat_cp.stdout or "",
        stderr=chk_lrat_cp.stderr or "",
    )
    (proofcheck_dir / "lrat-trim.json").write_text(chk_lrat.to_json(), encoding="utf-8")

    # 5) Gate 3: verify LRAT with cake_lpr (HOL4-verified; success = "s VERIFIED UNSAT" on stdout)
    chk_cake_cp = _run([str(cake_lpr), str(cnf_path), str(lrat_path)], cwd=root)
    cake_ok = (
        chk_cake_cp.returncode == 0
        and "s VERIFIED UNSAT" in (chk_cake_cp.stdout or "")
    )
    chk_cake = ProofCheck(
        checker="cake_lpr",
        ok=cake_ok,
        returncode=chk_cake_cp.returncode,
        stdout=chk_cake_cp.stdout or "",
        stderr=chk_cake_cp.stderr or "",
    )
    (proofcheck_dir / "cake_lpr.json").write_text(chk_cake.to_json(), encoding="utf-8")

    # Fail-closed: all three gates must pass
    if not (chk_drat.ok and chk_lrat.ok and chk_cake.ok):
        return SatExecResult(
            result="ERROR",
            stdout=stdout,
            stderr=stderr + "\nUNSAT proof verification failed (three-checker gate)\n",
            commandline=cmd,
            drat_relpath=str(drat_path.relative_to(out_dir)),
            lrat_relpath=str(lrat_path.relative_to(out_dir)),
            check_drat=chk_drat,
            check_lrat=chk_lrat,
            check_cake_lpr=chk_cake,
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
        check_cake_lpr=chk_cake,
    )
