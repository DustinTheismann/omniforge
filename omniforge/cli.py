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

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
