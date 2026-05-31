"""
Lean proof generator for partial-fraction antiderivatives.

A partial-fraction antiderivative is a sum of terms of the form

    c_i * log(a_i * x + b_i)

where each (a_i * x + b_i) must be nonzero.

Given the list of poles, this module generates:
  - The antiderivative Lean expression
  - The derivative Lean expression
  - The required hypotheses
  - A Lean tactic proof

The proof strategy mirrors the hand-written theorems in RischVerification.lean:
  1. Prove HasDerivAt for each log(a_i*x+b_i) / a_i piece using .log + chain rule.
  2. Scale by c_i using .const_mul.
  3. Combine with .add / .sub.
  4. Close with field_simp + ring.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LogTerm:
    """c * log(a*x + b)."""
    coeff: str   # Lean literal coefficient, e.g. "1/2", "-1", "4"
    a: str       # coefficient of x inside log, e.g. "1", "2"
    b: str       # constant inside log, e.g. "0", "1", "-3"

    def inner(self, var: str = "x") -> str:
        """Return the Lean expression for the log argument."""
        if self.a == "1" and self.b == "0":
            return var
        if self.b == "0":
            return f"{self.a} * {var}"
        sign = "+" if not self.b.startswith("-") else ""
        return f"{self.a} * {var} {sign} {self.b}"

    def lean_expr(self, var: str = "x") -> str:
        inner = self.inner(var)
        if self.coeff == "1":
            return f"Real.log ({inner})"
        return f"{self.coeff} * Real.log ({inner})"

    def hyp_name(self, idx: int) -> str:
        return f"hne{idx}"

    def hypothesis(self, var: str = "x") -> str:
        return f"{self.inner(var)} ≠ 0"


def pf_antideriv(terms: list[LogTerm], var: str = "x") -> str:
    """Return the full antiderivative as a Lean expression."""
    if not terms:
        return "0"
    return " + ".join(t.lean_expr(var) for t in terms)


def pf_hypotheses(terms: list[LogTerm], var: str = "x") -> list[tuple[str, str]]:
    """Return list of (hyp_name, lean_expr) pairs."""
    return [(t.hyp_name(i), t.hypothesis(var)) for i, t in enumerate(terms)]


def pf_proof_tactic(
    terms: list[LogTerm],
    theorem_name: str,
    var: str = "x",
) -> str:
    """
    Generate a complete Lean theorem + proof for HasDerivAt of the PF antiderivative.

    Returns a string containing the full theorem (including signature) ready
    to paste into a .lean file after ``import`` and ``open Real`` statements.
    """
    hyps = pf_hypotheses(terms, var)

    # Theorem signature
    hyp_sig = " ".join(
        [f"({var} : ℝ)"] + [f"({name} : {expr})" for name, expr in hyps]
    )

    # Build the antiderivative and derivative Lean expressions
    antideriv = pf_antideriv(terms, var)

    # The derivative of the full PF is the original integrand (rational function)
    # We express it symbolically; field_simp + ring will close the goal.
    deriv_terms: list[str] = []
    for t in terms:
        # d/dx [c * log(a*x+b)] = c * a / (a*x+b)
        numer = f"({t.coeff}) * ({t.a})"
        denom = t.inner(var)
        deriv_terms.append(f"{numer} / ({denom})")
    deriv_expr = " + ".join(deriv_terms) if deriv_terms else "0"

    # Individual step proofs
    step_lines: list[str] = []
    step_names: list[str] = []
    for i, (term, (hname, _)) in enumerate(zip(terms, hyps)):
        sname = f"hL{i}"
        step_names.append(sname)
        inner = term.inner(var)
        step_lines.append(
            f"  have hg{i} : HasDerivAt (fun t => {term.a} * t + ({term.b})) {term.a} {var} := by\n"
            f"    simpa using ((hasDerivAt_id {var}).const_mul {term.a}).add (hasDerivAt_const {var} ({term.b}))\n"
            f"  have {sname} := ((hg{i}.log {hname}).const_mul ({term.coeff}))"
        )

    # Combine steps
    if len(step_names) == 1:
        combined = step_names[0]
    else:
        combined = step_names[0]
        for sname in step_names[1:]:
            combined = f"({combined}).add ({sname})"

    hyp_names = " ".join(h for h, _ in hyps)

    proof_body = "\n".join(step_lines)
    proof_body += f"\n  convert {combined} using 1\n  field_simp [{hyp_names}]; ring"

    theorem = (
        f"theorem {theorem_name} {hyp_sig} :\n"
        f"    HasDerivAt (fun {var} => {antideriv}) ({deriv_expr}) {var} := by\n"
        f"{proof_body}"
    )
    return theorem


# ---------------------------------------------------------------------------
# Helper: build LogTerm list from corpus entry
# ---------------------------------------------------------------------------

def terms_from_entry(entry: dict) -> list[LogTerm]:
    """
    Extract LogTerm list from a corpus entry (best-effort).

    Parses the antiderivative string for ``c * log(...)`` patterns.
    Returns an empty list if parsing fails — caller should fall back to sorry.
    """
    import re

    antideriv = entry.get("antiderivative", "")
    # Match patterns like: log(x+1)/2, -log(x+1), 4*log(x+2), log(x-3)/2
    pat = re.compile(
        r'([+-]?\s*(?:\d+(?:\.\d+)?/\d+|\d+(?:\.\d+)?)?\*?)\s*'
        r'log\(([^)]+)\)'
        r'(?:/(\d+))?'
    )
    terms: list[LogTerm] = []
    for m in pat.finditer(antideriv):
        coeff_raw = (m.group(1) or "1").strip().rstrip("*").strip() or "1"
        inner_raw = m.group(2).strip()
        div_raw   = m.group(3)
        if div_raw:
            coeff_raw = f"({coeff_raw}) / {div_raw}" if coeff_raw != "1" else f"1 / {div_raw}"
        # Parse inner: a*x+b or x+b or x-b or x
        var = entry.get("var", "x")
        inner_m = re.match(
            rf'^(\d*)\*?{re.escape(var)}\s*([+-]\s*\d+)?$', inner_raw
        )
        if not inner_m:
            return []  # give up
        a = inner_m.group(1) or "1"
        b_raw = (inner_m.group(2) or "").replace(" ", "") or "0"
        terms.append(LogTerm(coeff=coeff_raw, a=a, b=b_raw))
    return terms
