"""
Tier 2.1 — Branch-cut audit.

The paper's flagged limitation, made into an instrument.  FriCAS's `log` denotes
the principal branch and requires its argument > 0 on a connected component;
Lean's `Real.log` is `log|·|`, total on ℝ and requiring only argument ≠ 0.  Where
the two disagree, the antiderivative carries a branch-cut discrepancy that a
pointwise `≠ 0` hypothesis does not capture.

This module classifies each `log(...)` / `atan(...)` subexpression of a FriCAS
antiderivative into a discrepancy class:

  (no discrepancy)  log(x²+c), atan(...)   — argument provably > 0, branches agree
  E_branch_cut      log(x), log(x+a)       — FriCAS x>−a (principal) vs Lean x≠−a
  F_sign_dependent  log(x²−c)              — argument changes sign; Lean's |·| hides it

Public API
----------
BranchDiscrepancy               dataclass
branch_audit(fricas_antideriv)  → list[BranchDiscrepancy]
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# log(<arg>) with a single level of parens in the argument
_LOG = re.compile(r"log\(([^()]*(?:\([^()]*\)[^()]*)*)\)")


@dataclass
class BranchDiscrepancy:
    antideriv_subexpr: str   # "log(x)"
    arg: str                 # "x"
    fricas_domain: str       # "x > 0  (principal branch)"
    lean_domain: str         # "x ≠ 0  (Real.log = log|x|)"
    discrepancy_class: str   # "E_branch_cut" | "F_sign_dependent" | "none"

    @property
    def is_discrepancy(self) -> bool:
        return self.discrepancy_class != "none"


def _classify_arg(arg: str) -> tuple[str, str, str]:
    """Return (class, fricas_domain, lean_domain) for a log argument."""
    a = arg.replace(" ", "")

    # Provably-positive quadratic: x^2+c  (c ≥ 0) — branches agree, no hypothesis
    if re.fullmatch(r"x\^2\+\d+", a) or re.fullmatch(r"\d+\+x\^2", a):
        return ("none",
                "argument > 0 everywhere (principal branch total here)",
                "argument > 0 everywhere (|·| irrelevant)")

    # Sign-changing quadratic: x^2-c — argument negative on (−√c, √c)
    if re.fullmatch(r"x\^2-\d+", a):
        c = a.split("-")[1]
        return ("F_sign_dependent",
                f"requires x² > {c} (principal branch undefined where x² < {c})",
                f"requires x² ≠ {c} (Real.log = log|·| absorbs the sign)")

    # Linear factor: x, x+a, x-a — FriCAS needs >0, Lean needs ≠0
    if a == "x":
        return ("E_branch_cut", "x > 0  (principal branch)", "x ≠ 0  (Real.log = log|x|)")
    m = re.fullmatch(r"x([+-]\d+)", a)
    if m:
        off = m.group(1)
        # x+a > 0  ⇔  x > −a ; Lean: x+a ≠ 0
        neg = off[1:] if off[0] == "+" else f"-{off[1:]}"
        return ("E_branch_cut",
                f"x > {('-' + off[1:]) if off[0] == '+' else off[1:]}  (principal branch)",
                f"x {off} ≠ 0  (Real.log = log|x{off}|)")

    # Unknown form — report conservatively as a potential branch issue.
    return ("E_branch_cut",
            f"{arg} > 0  (principal branch)",
            f"{arg} ≠ 0  (Real.log = log|·|)")


def branch_audit(fricas_antideriv: str) -> list[BranchDiscrepancy]:
    """
    Return one BranchDiscrepancy per log(...) subexpression of the antiderivative.

    atan(...) terms produce no entry: arctan is total and single-valued on ℝ, so
    FriCAS and Lean agree unconditionally.
    """
    out: list[BranchDiscrepancy] = []
    for m in _LOG.finditer(fricas_antideriv):
        arg = m.group(1)
        cls, fdom, ldom = _classify_arg(arg)
        out.append(BranchDiscrepancy(
            antideriv_subexpr=f"log({arg})",
            arg=arg,
            fricas_domain=fdom,
            lean_domain=ldom,
            discrepancy_class=cls,
        ))
    return out


def discrepancies_only(fricas_antideriv: str) -> list[BranchDiscrepancy]:
    """branch_audit filtered to genuine discrepancies."""
    return [d for d in branch_audit(fricas_antideriv) if d.is_discrepancy]
