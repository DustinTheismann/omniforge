from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from omniforge.artifacts.pack import create_demo_run_bundle, verify_run_bundle_hashes
from omniforge.contracts import validate_contracts


def cmd_demo(_: argparse.Namespace) -> int:
    run_id = create_demo_run_bundle(root=Path.cwd())
    print(run_id)
    return 0


def cmd_reproduce(args: argparse.Namespace) -> int:
    ok, details = verify_run_bundle_hashes(root=Path.cwd(), run_id=args.run_id)
    if ok:
        print("OK: hashes verified")
        return 0
    print("FAIL: hashes did not verify")
    print(details)
    return 2


def cmd_validate_contracts(_: argparse.Namespace) -> int:
    validate_contracts(root=Path.cwd())
    print("OK: contracts validated")
    return 0


def cmd_verify_cnf(args: argparse.Namespace) -> int:
    """Run the three-checker UNSAT pipeline (cadical → drat-trim → lrat-trim →
    cake_lpr) on a CNF and fail closed unless every gate verifies UNSAT.

    This is what reproduces the E9 SAT anchor in CI: cake_lpr (HOL4-verified)
    actually re-checks the gf2 tautology's refutation, rather than the claim
    JSON merely asserting formal_verified=True.
    """
    from omniforge.lanes.sat_lane import run_sat_two_checker

    root = Path.cwd()
    res = run_sat_two_checker(
        root=root,
        cnf_path=Path(args.cnf),
        seed=args.seed,
        wall_seconds=args.wall_seconds,
        out_dir=Path(args.out_dir),
    )
    print(f"result={res.result}")
    for chk in (res.check_drat, res.check_lrat, res.check_cake_lpr):
        if chk is not None:
            print(f"  {chk.checker}: ok={chk.ok} returncode={chk.returncode}")

    if not args.expect_unsat:
        return 0

    all_ok = res.result == "UNSAT" and all(
        c is not None and c.ok
        for c in (res.check_drat, res.check_lrat, res.check_cake_lpr)
    )
    if all_ok:
        print("OK: UNSAT verified by drat-trim + lrat-trim + cake_lpr")
        return 0
    print("FAIL: expected UNSAT verified by all three checkers")
    return 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="omniforge", description="OmniForge seed CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("demo", help="Create a demo run bundle and validate it")
    d.set_defaults(func=cmd_demo)

    r = sub.add_parser("reproduce", help="Verify hashes for an existing run bundle")
    r.add_argument("--run-id", required=True)
    r.set_defaults(func=cmd_reproduce)

    v = sub.add_parser("validate-contracts", help="Validate JSON schemas and sample instances")
    v.set_defaults(func=cmd_validate_contracts)

    c = sub.add_parser(
        "verify-cnf",
        help="Run cadical → drat-trim → lrat-trim → cake_lpr on a CNF (fail-closed UNSAT check)",
    )
    c.add_argument("--cnf", required=True, help="Path to the DIMACS CNF file")
    c.add_argument("--out-dir", default="artifacts/verify-cnf", help="Output directory for proofs")
    c.add_argument("--seed", type=int, default=0)
    c.add_argument("--wall-seconds", type=int, default=60)
    c.add_argument(
        "--expect-unsat",
        action="store_true",
        help="Exit non-zero unless UNSAT is verified by all three checkers",
    )
    c.set_defaults(func=cmd_verify_cnf)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
