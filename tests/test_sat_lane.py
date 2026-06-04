"""
Unit tests for omniforge/lanes/sat_lane.py — no SAT tools required.

These tests verify the data structures, toolchain manifest, and install-script
integrity.  Actual three-checker UNSAT verification (cadical + drat-trim +
lrat-trim + cake_lpr) is exercised by the ci.yml "Demo" step after the
install_sat_toolchain.sh has run.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from omniforge.lanes.sat_lane import ProofCheck, SatExecResult, run_sat_two_checker

ROOT = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# Data-structure sanity
# ---------------------------------------------------------------------------

def test_proof_check_to_json_roundtrip():
    pc = ProofCheck(checker="drat-trim", ok=True, returncode=0, stdout="s VERIFIED UNSAT", stderr="")
    d = json.loads(pc.to_json())
    assert d["checker"] == "drat-trim"
    assert d["ok"] is True
    assert d["returncode"] == 0


def test_sat_exec_result_has_cake_lpr_field():
    r = SatExecResult(
        result="UNSAT",
        stdout="",
        stderr="",
        commandline=[],
        drat_relpath=None,
        lrat_relpath=None,
        check_drat=None,
        check_lrat=None,
        check_cake_lpr=None,
    )
    assert hasattr(r, "check_cake_lpr")
    assert r.check_cake_lpr is None


# ---------------------------------------------------------------------------
# Toolchain manifest
# ---------------------------------------------------------------------------

def test_toolchain_lock_exists():
    assert (ROOT / "tools" / "toolchain.lock.json").exists(), \
        "tools/toolchain.lock.json missing — run scripts/tools/install_sat_toolchain.sh"


def test_toolchain_lock_has_four_tools():
    lock = json.loads((ROOT / "tools" / "toolchain.lock.json").read_text())
    for key in ("cadical", "drat_trim", "lrat_trim", "cake_lpr"):
        assert key in lock, f"toolchain.lock.json missing entry: {key}"


def test_toolchain_lock_cake_lpr_has_repo_and_ref():
    lock = json.loads((ROOT / "tools" / "toolchain.lock.json").read_text())
    cake = lock["cake_lpr"]
    assert "repo" in cake and "tanyongkiam" in cake["repo"]
    assert "ref" in cake and cake["ref"]


# ---------------------------------------------------------------------------
# Install script
# ---------------------------------------------------------------------------

def test_install_script_exists_and_is_executable():
    script = ROOT / "scripts" / "tools" / "install_sat_toolchain.sh"
    assert script.exists()
    assert script.stat().st_mode & 0o111, "install script is not executable"


def test_install_script_mentions_cake_lpr():
    script = (ROOT / "scripts" / "tools" / "install_sat_toolchain.sh").read_text()
    assert "cake_lpr" in script
    assert "tanyongkiam" in script


# ---------------------------------------------------------------------------
# Benchmark CNF
# ---------------------------------------------------------------------------

def test_unsat_contradiction_cnf_exists():
    cnf = ROOT / "benches" / "sat" / "tiny" / "unsat_contradiction.cnf"
    assert cnf.exists()


def test_unsat_contradiction_cnf_is_valid_dimacs():
    cnf = (ROOT / "benches" / "sat" / "tiny" / "unsat_contradiction.cnf").read_text()
    header = [ln for ln in cnf.splitlines() if ln.startswith("p cnf")]
    assert len(header) == 1
    parts = header[0].split()
    nvars, nclauses = int(parts[2]), int(parts[3])
    assert nvars >= 1
    assert nclauses >= 2


# ---------------------------------------------------------------------------
# Three-checker policy: missing tools raise FileNotFoundError
# ---------------------------------------------------------------------------

def test_missing_cadical_raises(tmp_path):
    cnf = tmp_path / "test.cnf"
    cnf.write_text("p cnf 1 2\n1 0\n-1 0\n")
    with pytest.raises(FileNotFoundError, match="cadical"):
        run_sat_two_checker(root=tmp_path, cnf_path=cnf, seed=0, wall_seconds=5, out_dir=tmp_path / "out")


# ---------------------------------------------------------------------------
# Three-checker policy: cake_lpr ok flag
# ---------------------------------------------------------------------------

def test_proof_check_cake_lpr_ok_requires_verified_string():
    pc_ok = ProofCheck(checker="cake_lpr", ok=True, returncode=0,
                       stdout="s VERIFIED UNSAT\n", stderr="")
    pc_fail = ProofCheck(checker="cake_lpr", ok=False, returncode=0,
                         stdout="", stderr="c empty clause not derived at end of proof")
    assert pc_ok.ok is True
    assert pc_fail.ok is False
