#!/usr/bin/env python3
"""
Validate that every compiled axiom in the generated Lean file uses only
operations that are in scope for its enclosing typeclass.
This is the first gate Lean's elaborator applies: name resolution.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from spad2lean import parse_spad_file, parse_spad_files, Category, AxiomCompiler, op_to_field, DEFAULT_FILES


def collect_scope(cat_name: str, cat_by_name: dict) -> set:
    """Transitively collect all lean field names available in a category's scope."""
    visited: set = set()
    names: set = set()

    def recurse(name: str):
        if name in visited:
            return
        visited.add(name)
        cat = cat_by_name.get(name)
        if cat is None:
            return
        for op in cat.ops:
            for arity in range(4):
                names.add(op_to_field(op.name, arity))
            names.add(op.name)
        for p in cat.parents:
            base = re.match(r'([A-Za-z][A-Za-z0-9]*)', p)
            if base:
                recurse(base.group(1))

    recurse(cat_name)
    return names


def extract_lean_identifiers(lean_expr: str) -> set:
    """Extract function-position identifiers from a Lean proposition."""
    # Remove quantifier prefix  ∀ x y z : α,
    expr = re.sub(r'∀[^,]+,\s*', '', lean_expr)
    idents = set(re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', expr))
    # Remove lean builtins and type names
    lean_builtins = {
        'forall', 'fun', 'let', 'in', 'if', 'then', 'else',
        'Type', 'Prop', 'Bool', 'Nat', 'Int', 'True', 'False',
        'Not', 'And', 'Or', 'Option', 'Some', 'None', 'List',
        'PosNat', 'Record_',
    }
    return idents - lean_builtins


def validate(categories: list, verbose: bool = True) -> tuple:
    cat_by_name = {c.long_name: c for c in categories}
    passed = 0
    failed = 0
    failures = []

    for cat in categories:
        scope = collect_scope(cat.long_name, cat_by_name)
        # Bound single-letter variables are always in scope
        bound_vars = set('abcdefghijklmnopqrstuvwxyz')
        scope |= bound_vars
        # Numeric literals
        scope |= {'0', '1', '2', '3', '4', '5', '6', '7', '8', '9'}

        compiler = AxiomCompiler(cat, cat_by_name)
        for ax in cat.axioms:
            lean_prop = compiler.compile(ax.raw)
            if lean_prop is None:
                continue  # informal — skip

            idents = extract_lean_identifiers(lean_prop)
            # Unresolved = identifiers not in scope, not a single lowercase letter, not numeric
            unresolved = {
                i for i in idents
                if i not in scope
                and not (len(i) == 1 and i.islower())
                and not i.isdigit()
            }

            if unresolved:
                failures.append((cat.long_name, ax.raw, lean_prop, unresolved))
                failed += 1
                if verbose:
                    print(f"FAIL  {cat.long_name}")
                    print(f"      raw:  {ax.raw}")
                    print(f"      lean: {lean_prop}")
                    print(f"      unresolved: {sorted(unresolved)}")
            else:
                passed += 1
                if verbose:
                    print(f"OK    [{cat.long_name}]  {lean_prop[:90]}")

    return passed, failed, failures


def print_summary(categories: list):
    """Print per-category axiom compilation summary."""
    cat_by_name = {c.long_name: c for c in categories}
    print(f"\n{'Category':<35}  {'Compiled':>8}  {'Informal':>8}")
    print("─" * 55)
    for cat in categories:
        compiler = AxiomCompiler(cat, cat_by_name)
        compiled = sum(1 for ax in cat.axioms if compiler.compile(ax.raw) is not None)
        informal = len(cat.axioms) - compiled
        if cat.axioms:
            print(f"  {cat.long_name:<33}  {compiled:>8}  {informal:>8}")


def main():
    import argparse
    ap = argparse.ArgumentParser(
        description="Validate FriCAS→Lean bridge: axiom name resolution check"
    )
    ap.add_argument("spad_files", nargs='*',
                    default=[str(f) for f in DEFAULT_FILES],
                    help="SPAD source files (default: all four bundled files)")
    ap.add_argument("--quiet", "-q", action="store_true")
    ap.add_argument("--summary", "-s", action="store_true",
                    help="Print per-category axiom summary")
    args = ap.parse_args()

    categories = parse_spad_files(args.spad_files)

    print(f"Validating {len(categories)} categories...\n")
    passed, failed, failures = validate(categories, verbose=not args.quiet)

    if args.summary:
        print_summary(categories)

    print(f"\n{'='*60}")
    print(f"Results: {passed} axioms passed, {failed} axioms failed")

    if failed:
        print("\nFailed axioms:")
        for cat_name, raw, lean_prop, unresolved in failures:
            print(f"  [{cat_name}] {raw!r}")
            print(f"    lean:       {lean_prop}")
            print(f"    unresolved: {sorted(unresolved)}")
        sys.exit(1)
    else:
        print("All compiled axioms pass name resolution. ✓")


if __name__ == "__main__":
    main()
