"""
Parameterized Lean proof generators for elementary antiderivatives.

Each ``Piece`` subclass represents a single summand in an antiderivative and
knows how to generate the Lean tactic proof that its derivative equals the
corresponding integrand term.

Composition: the full antiderivative is a sum of Pieces; the proof is
assembled by chaining the individual piece proofs with `HasDerivAt.add`.

Supported piece types
---------------------
- LogLinear      log(a·x + b),        a ≠ 0, (a·x+b) ≠ 0
- LogPosQuad     log(x² + c) / 2,     c > 0  (no hypotheses needed)
- ArctanLinear   arctan(x / a) / a,   a ≠ 0
- ArctanPoly     arctan(p(x)),        p a Lean expression
- Power          x^n / n,             n ≠ 0
- Constant       literal constant     (derivative = 0)
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Piece(abc.ABC):
    """A single summand in an antiderivative."""

    @abc.abstractmethod
    def lean_expr(self, var: str = "x") -> str:
        """Lean expression for this summand (as a function of *var*)."""

    @abc.abstractmethod
    def deriv_expr(self, var: str = "x") -> str:
        """Lean expression for the derivative of this summand."""

    @abc.abstractmethod
    def proof_tactic(self, var: str = "x", label: str = "h") -> str:
        """
        Lean tactic block (without surrounding ``by``) that proves::

            HasDerivAt (fun t => <lean_expr(t)>) (<deriv_expr(var)>) var
        """

    @property
    def hypotheses(self) -> list[str]:
        """Return Lean-style hypotheses required for this piece (may be empty)."""
        return []


# ---------------------------------------------------------------------------
# Concrete pieces
# ---------------------------------------------------------------------------

@dataclass
class LogLinear(Piece):
    """
    Antiderivative: log(a·x + b) / a
    Derivative:     1 / (a·x + b)

    Required hypothesis: (a·x + b) ≠ 0
    """
    a: str  # coefficient as Lean literal (e.g. "2", "-1")
    b: str  # offset as Lean literal (e.g. "0", "1", "-3")

    def _inner(self, var: str) -> str:
        if self.b == "0":
            return f"{self.a} * {var}"
        sign = "+" if not self.b.startswith("-") else ""
        return f"{self.a} * {var} {sign} {self.b}"

    def lean_expr(self, var: str = "x") -> str:
        inner = self._inner(var)
        if self.a == "1":
            return f"Real.log ({inner})"
        return f"Real.log ({inner}) / {self.a}"

    def deriv_expr(self, var: str = "x") -> str:
        return f"1 / ({self._inner(var)})"

    @property
    def hypotheses(self) -> list[str]:
        return [f"{self._inner('x')} ≠ 0"]

    def proof_tactic(self, var: str = "x", label: str = "h") -> str:
        inner = self._inner(var)
        return (
            f"have hg : HasDerivAt (fun t => {self.a} * t + ({self.b})) {self.a} {var} := by\n"
            f"    simpa using ((hasDerivAt_id {var}).const_mul {self.a}).add (hasDerivAt_const {var} ({self.b}))\n"
            f"  have hlog := (hg.log {label}).div_const {self.a}\n"
            f"  convert hlog using 1; field_simp [{label}]"
        )


@dataclass
class LogPosQuad(Piece):
    """
    Antiderivative: log(x² + c) / 2        (c > 0 ⟹ argument always positive)
    Derivative:     x / (x² + c)
    """
    c: str  # positive constant as Lean literal (e.g. "1", "4")

    def lean_expr(self, var: str = "x") -> str:
        return f"Real.log ({var}^2 + {self.c}) / 2"

    def deriv_expr(self, var: str = "x") -> str:
        return f"{var} / ({var}^2 + {self.c})"

    @property
    def hypotheses(self) -> list[str]:
        return []  # x²+c > 0 when c > 0; no explicit hypothesis needed

    def proof_tactic(self, var: str = "x", label: str = "h") -> str:
        return (
            f"have hpos : (0 : ℝ) < {var}^2 + {self.c} := by positivity\n"
            f"  have hg : HasDerivAt (fun t => t^2 + {self.c}) (2 * {var}) {var} := by\n"
            f"    simpa using (hasDerivAt_pow 2 {var}).add (hasDerivAt_const {var} ({self.c}))\n"
            f"  have h := (hg.log hpos.ne').div_const 2\n"
            f"  convert h using 1; field_simp [hpos.ne']; ring"
        )


@dataclass
class ArctanLinear(Piece):
    """
    Antiderivative: arctan(x / a) / a      (a ≠ 0, a² > 0)
    Derivative:     1 / (x² + a²)
    """
    a: str  # denominator as Lean literal

    def lean_expr(self, var: str = "x") -> str:
        return f"Real.arctan ({var} / {self.a}) / {self.a}"

    def deriv_expr(self, var: str = "x") -> str:
        return f"1 / ({var}^2 + {self.a}^2)"

    def proof_tactic(self, var: str = "x", label: str = "h") -> str:
        return (
            f"have hg : HasDerivAt (fun t => t / {self.a}) (1 / {self.a}) {var} := by\n"
            f"    simpa using (hasDerivAt_id {var}).div_const {self.a}\n"
            f"  have hF := (Real.hasDerivAt_arctan ({var} / {self.a})).comp {var} hg\n"
            f"  have hF2 := hF.div_const {self.a}\n"
            f"  convert hF2 using 1\n"
            f"  have h1 : (0 : ℝ) < 1 + ({var} / {self.a})^2 := by positivity\n"
            f"  field_simp [h1.ne']; ring"
        )


@dataclass
class ArctanPoly(Piece):
    """
    Antiderivative: arctan(p(x))
    Derivative:     p'(x) / (1 + p(x)²)

    The caller must supply the Lean expressions for p and p' as strings.
    """
    p_lean: str   # e.g. "x + 1", "x^2"
    dp_lean: str  # derivative of p, e.g. "1", "2 * x"

    def lean_expr(self, var: str = "x") -> str:
        p = self.p_lean.replace("x", var)
        return f"Real.arctan ({p})"

    def deriv_expr(self, var: str = "x") -> str:
        p  = self.p_lean.replace("x", var)
        dp = self.dp_lean.replace("x", var)
        return f"{dp} / (1 + ({p})^2)"

    def proof_tactic(self, var: str = "x", label: str = "h") -> str:
        p  = self.p_lean.replace("x", var)
        dp = self.dp_lean.replace("x", var)
        return (
            f"have hg : HasDerivAt (fun t => {self.p_lean.replace('x', 't')}) ({dp}) {var} := by\n"
            f"    sorry -- caller fills in\n"
            f"  have hF := (Real.hasDerivAt_arctan ({p})).comp {var} hg\n"
            f"  convert hF using 1\n"
            f"  have h1 : (0 : ℝ) < 1 + ({p})^2 := by positivity\n"
            f"  field_simp [h1.ne']; ring"
        )


@dataclass
class Power(Piece):
    """
    Antiderivative: x^n / n
    Derivative:     x^(n-1)
    """
    n: int

    def lean_expr(self, var: str = "x") -> str:
        return f"{var}^{self.n} / {self.n}"

    def deriv_expr(self, var: str = "x") -> str:
        if self.n - 1 == 0:
            return "1"
        return f"{var}^{self.n - 1}"

    def proof_tactic(self, var: str = "x", label: str = "h") -> str:
        return (
            f"have h := (hasDerivAt_pow {self.n} {var}).div_const {self.n}\n"
            f"  convert h using 1; push_cast; ring"
        )


@dataclass
class Constant(Piece):
    """A literal constant term (derivative = 0)."""
    value: str

    def lean_expr(self, var: str = "x") -> str:
        return self.value

    def deriv_expr(self, var: str = "x") -> str:
        return "0"

    def proof_tactic(self, var: str = "x", label: str = "h") -> str:
        return f"exact hasDerivAt_const {var} ({self.value})"


# ---------------------------------------------------------------------------
# Composition helper
# ---------------------------------------------------------------------------

def compose_pieces(pieces: list[Piece], var: str = "x") -> str:
    """
    Return a Lean tactic block proving HasDerivAt for the sum of all pieces.

    The strategy is:
      1. Prove HasDerivAt for each individual piece.
      2. Combine with repeated `.add`.
    """
    if not pieces:
        raise ValueError("At least one piece required")

    lines: list[str] = []
    step_names: list[str] = []

    for i, piece in enumerate(pieces):
        sname = f"step{i}"
        step_names.append(sname)
        tactic = piece.proof_tactic(var=var, label=f"hyp{i}")
        lines.append(f"  have {sname} : HasDerivAt (fun {var} => {piece.lean_expr(var)}) ({piece.deriv_expr(var)}) {var} := by")
        for tline in tactic.split("\n"):
            lines.append(f"    {tline}")

    # Combine
    combined = step_names[0]
    for sname in step_names[1:]:
        combined = f"({combined}).add ({sname})"

    lines.append(f"  convert {combined} using 1; ring")
    return "\n".join(lines)
