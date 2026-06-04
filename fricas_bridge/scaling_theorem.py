"""
Tier 1.4 — Scaling-law theorem: general partial-fraction HasDerivAt pattern.

For a rational function with simple real poles a_1, …, a_n and partial
fraction coefficients c_1, …, c_n:

   ∫ Σ c_i/(x - a_i) dx  =  Σ c_i · log|x - a_i|

The corresponding HasDerivAt theorem:

   theorem partial_fraction_hasDerivAt
     (n : ℕ) (poles : Fin n → ℝ) (coeffs : Fin n → ℝ)
     (x : ℝ) (h : ∀ i, x ≠ poles i) :
     HasDerivAt (fun x => ∑ i, coeffs i * Real.log (x - poles i))
                (∑ i, coeffs i / (x - poles i)) x

This module generates:
  1. The Lean statement of the general theorem
  2. Concrete instantiations for 1, 2, 3, 4 poles
  3. A proof sketch (the full proof is by induction on n + simp)

Public API
----------
GeneralPFDTheorem               dataclass
ConcreteInstance                dataclass
build_general_theorem()         → GeneralPFDTheorem
build_concrete_instances(max_poles) → list[ConcreteInstance]
write_pfd_lean_file(path)       → Path
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class GeneralPFDTheorem:
    statement: str    # the ∀ n theorem
    proof_sketch: str


@dataclass
class ConcreteInstance:
    n_poles: int
    poles: list[str]          # ["a", "b", ...]  (variable names)
    coeffs: list[str]         # ["c1", "c2", ...]
    lean_statement: str
    proof_script: str


# The committed, kernel-checked Lean file is the single source of truth.
# scaling_theorem.py reflects it rather than carrying a separate proof string,
# so the generator can never drift from what the Lean toolchain actually accepts.
_COMMITTED_LEAN = Path(__file__).resolve().parent / "PartialFractionHasDerivAt.lean"

_GENERAL_PROOF_SKETCH = (
    "Per-term: hasDerivAt_id |> sub_const |> HasDerivAt.log |> const_mul; "
    "combined with HasDerivAt.sum over Finset.univ."
)


def _committed_general_theorem() -> str:
    """Extract the `partial_fraction_hasDerivAt` theorem block from the
    committed Lean file (the kernel-checked source of truth)."""
    text = _COMMITTED_LEAN.read_text()
    lines = text.splitlines()
    out: list[str] = []
    collecting = False
    for line in lines:
        if line.startswith("theorem partial_fraction_hasDerivAt"):
            collecting = True
        if collecting:
            # Stop at the start of the next top-level theorem/end.
            if out and (line.startswith("theorem ") or line.startswith("/--")
                        or line == "end"):
                break
            out.append(line)
    return "\n".join(out).rstrip() + "\n"


def build_general_theorem() -> GeneralPFDTheorem:
    return GeneralPFDTheorem(
        statement=_committed_general_theorem(),
        proof_sketch=_GENERAL_PROOF_SKETCH,
    )


def build_concrete_instances(max_poles: int = 4) -> list[ConcreteInstance]:
    """
    Return the kernel-checked concrete specialisations present in the committed
    Lean file (currently `partial_fraction_one_pole`, the n = 1 instance).

    Unlike the earlier version, this no longer fabricates unchecked `pfd_N_poles`
    theorem text: it reflects only theorems that the Lean toolchain actually
    elaborates in CI.  Add a new specialisation to PartialFractionHasDerivAt.lean
    (and let CI accept it) before it appears here.
    """
    text = _COMMITTED_LEAN.read_text()
    instances: list[ConcreteInstance] = []

    # n = 1 specialisation, if present in the committed file.
    if "theorem partial_fraction_one_pole" in text:
        instances.append(ConcreteInstance(
            n_poles=1,
            poles=["a"],
            coeffs=["c"],
            lean_statement="theorem partial_fraction_one_pole",
            proof_script="derived from partial_fraction_hasDerivAt (n := 1)",
        ))

    return instances


def write_pfd_lean_file(path: Optional[str] = None) -> Path:
    """
    Write the kernel-checked scaling-law Lean file.

    If a path is given, the committed PartialFractionHasDerivAt.lean is copied
    there verbatim, so any emitted artifact is byte-identical to what CI checks.
    With no path, returns the committed file's location without rewriting it
    (it is hand-maintained as the source of truth).
    """
    if path is None:
        return _COMMITTED_LEAN
    dest = Path(path)
    dest.write_text(_COMMITTED_LEAN.read_text())
    return dest
