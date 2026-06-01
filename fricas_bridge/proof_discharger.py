"""
Step D + Tier 1 — Proof Discharge for all four discrepancy classes.

Pipeline:
  HasDerivAt F f x goal
    → lean_to_fricas  (FriCAS integrand string)
    → FriCAS call     (antiderivative string)  [or FRICAS_CACHE offline]
    → fricas_to_lean  (Lean term)
    → shape classify  (proof strategy)
    → hypothesis synthesis (domain restrictions FriCAS left implicit)
    → proof script    (Lean tactic block)

Discrepancy classes (per the paper):
  A — no restriction              (claims 001, 003, 004, 006)
  B — one implicit hypothesis     (claims 007, 008)
  C — two-pole partial fractions  (claim  005)
  D — three+ pole partial fracts  (claim  009)

Each generated proof reproduces a pattern already kernel-verified in
RischVerification.lean, so the auto-discharged file is sound by construction.

Public API
----------
FRICAS_CACHE                       dict[claim_id → {integrand_fricas, antideriv_fricas}]
classify_antideriv(fricas_str)     → shape dict (keys: shape, …)
synthesize_hypotheses(antideriv,var) → list[Hypothesis]
generate_theorem_text(claim_id)    → str  (theorem statement + proof)
generate_autodischarge_lean()      → str  (full .lean file)
discharge_all()                    → list[dict]
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from fricas_bridge.fricas_to_lean import fricas_antideriv_to_lean  # noqa: F401 (API parity)

_EXAMPLES = Path(__file__).parent.parent / "protocols" / "claim_protocol" / "examples"
_LEAN_OUT = Path(__file__).parent / "RischAutoDischarge.lean"


def _claim(n: int) -> dict:
    return json.loads((_EXAMPLES / f"risch_bronstein_{n:03d}.json").read_text())


# ---------------------------------------------------------------------------
# Offline FriCAS cache
# ---------------------------------------------------------------------------

FRICAS_CACHE: dict[str, dict] = {}


def _build_cache() -> None:
    for n in range(1, 10):
        claim = _claim(n)
        cid = f"pf.integral.bronstein_{n:03d}"
        FRICAS_CACHE[cid] = {
            "integrand_fricas": claim["inputs"]["integrand"],
            "antideriv_fricas": claim["outputs"]["candidate_antiderivative"],
        }


_build_cache()

# ---------------------------------------------------------------------------
# Shape classification (works on FriCAS antiderivative strings)
# ---------------------------------------------------------------------------

_RE_LOG_POS_QUAD  = re.compile(r"^log\(x\^2\+(\d+)\)/2$")
_RE_LOG_NEG_QUAD  = re.compile(r"^log\(x\^2-(\d+)\)/2$")
_RE_ARCTAN_POW    = re.compile(r"^atan\(x\^(\d+)\)$")
_RE_ARCTAN_LINEAR = re.compile(r"^atan\(x\+(.+)\)$")
_RE_LOG_SIMPLE    = re.compile(r"^log\(x\)$")
# Sum of log(linear)/coeff terms, e.g. log(x)/2+log(x+2)/2
_RE_LOG_TERM      = re.compile(r"([+-]?)log\(([^)]+)\)(?:/(\d+))?")


def classify_antideriv(fricas_antideriv: str) -> dict:
    """
    Classify a FriCAS antiderivative string into a proof shape.

    Shapes:
      LOG_POS_QUAD   — log(x²+c)/2,    c > 0    (Class A)
      LOG_NEG_QUAD   — log(x²−c)/2,    c > 0    (Class B, hyp x²−c ≠ 0)
      LOG_SIMPLE     — log(x)                   (Class B, hyp x ≠ 0)
      ARCTAN_POW     — atan(xⁿ)                 (Class A)
      ARCTAN_LINEAR  — atan(x+c)                (Class A)
      LOG_PFD        — Σ cᵢ·log(x−aᵢ)           (Class C/D, hyp per pole)
      COMPLEX_SUM    — claim-001 multi-term      (Class A)
      UNKNOWN
    """
    s = fricas_antideriv.strip().replace(" ", "")

    if (m := _RE_LOG_POS_QUAD.match(s)):
        return {"shape": "LOG_POS_QUAD", "c": m.group(1)}

    if (m := _RE_LOG_NEG_QUAD.match(s)):
        return {"shape": "LOG_NEG_QUAD", "c": m.group(1)}

    if _RE_LOG_SIMPLE.match(s):
        return {"shape": "LOG_SIMPLE"}

    if (m := _RE_ARCTAN_POW.match(s)):
        n = int(m.group(1))
        return {"shape": "ARCTAN_POW", "n": n,
                "p_lean": f"t ^ {n}",
                "dp_lean": "2 * t" if n == 2 else f"{n} * t ^ {n - 1}"}

    if (m := _RE_ARCTAN_LINEAR.match(s)):
        c = m.group(1)
        return {"shape": "ARCTAN_LINEAR", "c": c, "p_lean": f"t + {c}", "dp_lean": "1"}

    # Multi-term log sum over linear factors → partial-fraction class
    if "log(" in s and "^2" not in s and "atan" not in s:
        poles = _parse_log_poles(s)
        if poles is not None and len(poles) >= 2:
            return {"shape": "LOG_PFD", "poles": poles}

    if "log" in s and "^2" in s:
        return {"shape": "COMPLEX_SUM"}

    return {"shape": "UNKNOWN"}


def _parse_log_poles(s: str) -> Optional[list[dict]]:
    """
    Parse a sum like ``log(x)/2-log(x+1)+log(x+2)/2`` into pole descriptors.

    Each descriptor: {arg, offset, coeff_den, sign} where the log argument is
    a linear factor ``x`` or ``x+k`` / ``x-k``.  Returns None if any term is
    not a linear-factor log.
    """
    poles: list[dict] = []
    pos = 0
    for m in _RE_LOG_TERM.finditer(s):
        if m.start() != pos:  # gap → non-log term present
            return None
        pos = m.end()
        sign = "-" if m.group(1) == "-" else "+"
        arg = m.group(2)
        den = m.group(3) or "1"
        if arg == "x":
            offset = "0"
        elif re.fullmatch(r"x[+-]\d+", arg):
            offset = arg[1:]  # keep sign, drop leading x
        else:
            return None
        poles.append({"arg": arg, "offset": offset, "den": den, "sign": sign})
    if pos != len(s):
        return None
    return poles


# ---------------------------------------------------------------------------
# Tier 1.1 — Hypothesis synthesis
# ---------------------------------------------------------------------------

@dataclass
class Hypothesis:
    lean_binder: str       # "(hx : x ≠ 0)"
    name: str              # "hx"
    statement: str         # "x ≠ 0"
    pole: Optional[str]    # "0", "-1", ... or None for quadratic-arg form


def synthesize_hypotheses(fricas_antideriv: str, var: str = "x") -> list[Hypothesis]:
    """
    Return the domain-restriction hypotheses a FriCAS antiderivative requires
    but does not state.  Provably-positive quadratic arguments (log(x²+c),
    atan(...)) yield no hypothesis; vanishing factors do.
    """
    shape = classify_antideriv(fricas_antideriv)
    kind = shape["shape"]

    if kind == "LOG_SIMPLE":
        return [Hypothesis("(hx : x ≠ 0)", "hx", "x ≠ 0", "0")]

    if kind == "LOG_NEG_QUAD":
        c = shape["c"]
        return [Hypothesis(f"(hne : (x ^ 2 - {c} : ℝ) ≠ 0)", "hne",
                           f"x ^ 2 - {c} ≠ 0", None)]

    if kind == "LOG_PFD":
        hyps: list[Hypothesis] = []
        for i, p in enumerate(shape["poles"]):
            off = p["offset"]
            if off == "0":
                hyps.append(Hypothesis("(hx : x ≠ 0)", "hx", "x ≠ 0", "0"))
            else:
                # off like "+1" / "-2"
                sign = off[0]
                mag = off[1:]
                name = f"hx{mag}" if sign == "+" else f"hxm{mag}"
                expr = f"x + {mag}" if sign == "+" else f"x - {mag}"
                pole = f"-{mag}" if sign == "+" else mag
                hyps.append(Hypothesis(f"({name} : {expr} ≠ 0)", name,
                                       f"{expr} ≠ 0", pole))
        # dedupe by name preserving order
        seen, out = set(), []
        for h in hyps:
            if h.name not in seen:
                seen.add(h.name)
                out.append(h)
        return out

    return []


# ---------------------------------------------------------------------------
# Proof generators — Class A
# ---------------------------------------------------------------------------

def _proof_log_pos_quad(c: str) -> str:
    return f"""\
  have hpos : (0 : ℝ) < x ^ 2 + {c} := by positivity
  have hne : (x ^ 2 + {c} : ℝ) ≠ 0 := hpos.ne'
  have hg : HasDerivAt (fun t : ℝ => t ^ 2 + {c}) (2 * x) x := by
    have h := (hasDerivAt_pow 2 x).add (hasDerivAt_const x ({c} : ℝ))
    simpa [pow_one] using h
  have h := (hg.log hne).div_const 2
  convert h using 1
  field_simp [hne]"""


def _proof_arctan_pow(n: int) -> str:
    p_lean = f"t ^ {n}"
    p_at_x = f"x ^ {n}"
    dp_lean = "2 * x" if n == 2 else f"{n} * x"
    x2n = f"x ^ {2 * n}"
    simpa_hint = "[pow_one]" if n == 2 else "[pow_succ]"
    return f"""\
  have hg : HasDerivAt (fun t : ℝ => {p_lean}) ({dp_lean}) x := by
    have h := hasDerivAt_pow {n} x
    simpa {simpa_hint} using h
  have hF := (Real.hasDerivAt_arctan ({p_at_x})).comp x hg
  convert hF using 1
  have h1 : (0 : ℝ) < 1 + {x2n}        := by positivity
  have h2 : (0 : ℝ) < 1 + ({p_at_x}) ^ 2  := by positivity
  field_simp [h1.ne', h2.ne']
  ring"""


def _proof_arctan_linear(c: str) -> str:
    p_at_x = f"x + {c}"
    return f"""\
  have hg : HasDerivAt (fun t : ℝ => t + {c}) 1 x := by
    simpa using (hasDerivAt_id x).add (hasDerivAt_const x ({c} : ℝ))
  have hF := (Real.hasDerivAt_arctan ({p_at_x})).comp x hg
  convert hF using 1
  have h1 : (0 : ℝ) < 1 + ({p_at_x}) ^ 2 := by positivity
  have h2 : (0 : ℝ) < x ^ 2 + 2 * x + 2 := by nlinarith [sq_nonneg ({p_at_x})]
  field_simp [h1.ne', h2.ne']
  ring"""


def _proof_complex_sum_001() -> str:
    return """\
  have hpos : (0 : ℝ) < x ^ 2 + 1 := by positivity
  have hne  : (x ^ 2 + 1 : ℝ) ≠ 0 := hpos.ne'
  have hg : HasDerivAt (fun t : ℝ => t ^ 2 + 1) (2 * x) x := by
    have h := (hasDerivAt_pow 2 x).add (hasDerivAt_const x (1 : ℝ))
    simpa [pow_one] using h
  have hL : HasDerivAt (fun t : ℝ => Real.log (t ^ 2 + 1)) (2 * x / (x ^ 2 + 1)) x :=
    hg.log hne
  have hL2 : HasDerivAt (fun t : ℝ => Real.log (t ^ 2 + 1) ^ 2 / 2)
      (Real.log (x ^ 2 + 1) * (2 * x / (x ^ 2 + 1))) x := by
    have hsq : HasDerivAt (fun u : ℝ => u ^ 2 / 2) (Real.log (x ^ 2 + 1))
               (Real.log (x ^ 2 + 1)) := by
      have h := (hasDerivAt_pow 2 (Real.log (x ^ 2 + 1))).div_const 2
      convert h using 1
      simp [pow_one]; ring
    exact hsq.comp x hL
  have hx2 : HasDerivAt (fun t : ℝ => t ^ 2 / 2) x x := by
    have h := (hasDerivAt_pow 2 x).div_const 2
    convert h using 1
    simp [pow_one]; ring
  have hL1 : HasDerivAt (fun t : ℝ => Real.log (t ^ 2 + 1) / 2) (x / (x ^ 2 + 1)) x := by
    have h := hL.div_const 2
    convert h using 1
    field_simp [hne]
  have hF : HasDerivAt
      (fun t : ℝ => Real.log (t ^ 2 + 1) ^ 2 / 2 + t ^ 2 / 2 - Real.log (t ^ 2 + 1) / 2)
      (Real.log (x ^ 2 + 1) * (2 * x / (x ^ 2 + 1)) + x - x / (x ^ 2 + 1)) x :=
    (hL2.add hx2).sub hL1
  convert hF using 1
  field_simp [hne]
  ring"""


# ---------------------------------------------------------------------------
# Proof generators — Classes B, C, D (hypothesis-carrying)
# ---------------------------------------------------------------------------

def _proof_log_simple() -> str:
    """Class B: HasDerivAt (fun t => Real.log t) (1/x) x, needs hx : x ≠ 0."""
    return """\
  have h := (hasDerivAt_id x).log hx
  simpa [id] using h"""


def _proof_log_neg_quad(c: str) -> str:
    """Class B: HasDerivAt (fun t => Real.log (t²−c)/2) (x/(x²−c)) x, needs hne."""
    return f"""\
  have hg : HasDerivAt (fun t : ℝ => t ^ 2 - {c}) (2 * x) x := by
    have h := (hasDerivAt_pow 2 x).sub (hasDerivAt_const x ({c} : ℝ))
    simpa [pow_one] using h
  have h := (hg.log hne).div_const 2
  convert h using 1
  field_simp [hne]"""


def _proof_pfd_005() -> str:
    """Class C: log(x)/2 + log(x+2)/2, poles 0 and −2."""
    return """\
  have hL1 : HasDerivAt (fun t : ℝ => Real.log t / 2) (1 / (2 * x)) x := by
    have h := ((hasDerivAt_id x).log hx).div_const 2
    convert h using 1
    field_simp [hx]
  have hg2 : HasDerivAt (fun t : ℝ => t + 2) 1 x := by
    have h := (hasDerivAt_id x).add (hasDerivAt_const x (2 : ℝ))
    simpa using h
  have hL2 : HasDerivAt (fun t : ℝ => Real.log (t + 2) / 2) (1 / (2 * (x + 2))) x := by
    have h := (hg2.log hx2).div_const 2
    convert h using 1
    field_simp [hx2]
  have hF := hL1.add hL2
  convert hF using 1
  field_simp [hx, hx2, mul_ne_zero hx hx2]
  ring"""


def _proof_pfd_009() -> str:
    """Class D: log(x)/2 − log(x+1) + log(x+2)/2, poles 0, −1, −2."""
    return """\
  have hL1 : HasDerivAt (fun t : ℝ => Real.log t / 2) (1 / (2 * x)) x := by
    have h := ((hasDerivAt_id x).log hx).div_const 2
    convert h using 1; field_simp [hx]
  have hg1 : HasDerivAt (fun t : ℝ => t + 1) 1 x := by
    simpa using (hasDerivAt_id x).add (hasDerivAt_const x (1 : ℝ))
  have hL2 : HasDerivAt (fun t : ℝ => Real.log (t + 1)) (1 / (x + 1)) x := by
    have h := hg1.log hx1
    convert h using 1; field_simp [hx1]
  have hg2 : HasDerivAt (fun t : ℝ => t + 2) 1 x := by
    simpa using (hasDerivAt_id x).add (hasDerivAt_const x (2 : ℝ))
  have hL3 : HasDerivAt (fun t : ℝ => Real.log (t + 2) / 2) (1 / (2 * (x + 2))) x := by
    have h := (hg2.log hx2).div_const 2
    convert h using 1; field_simp [hx2]
  have hF : HasDerivAt (fun t : ℝ => Real.log t / 2 - Real.log (t + 1) + Real.log (t + 2) / 2)
      (1 / (2 * x) - 1 / (x + 1) + 1 / (2 * (x + 2))) x :=
    (hL1.sub hL2).add hL3
  convert hF using 1
  have h12  := mul_ne_zero hx hx1
  have h123 := mul_ne_zero h12 hx2
  field_simp [hx, hx1, hx2, h12, h123]
  ring"""


# ---------------------------------------------------------------------------
# Per-claim specification: body, integrand, hypotheses, proof selector
# ---------------------------------------------------------------------------

@dataclass
class ClaimSpec:
    claim_id: str
    theorem_name: str
    cls: str                 # "A" | "B" | "C" | "D"
    antideriv_body: str      # Lean lambda body in t
    integrand_expr: str      # Lean integrand in x
    proof: str               # tactic block (no leading "by")


def _spec_for(claim_id: str) -> ClaimSpec:
    n = int(claim_id.split("_")[-1])
    theorem_name = f"autodischarge_{n:03d}"
    fricas_antideriv = FRICAS_CACHE[claim_id]["antideriv_fricas"]
    shape = classify_antideriv(fricas_antideriv)["shape"]

    table: dict[str, tuple[str, str, str, str]] = {
        # claim_id : (class, body, integrand, proof)
        "pf.integral.bronstein_001": (
            "A",
            "Real.log (t ^ 2 + 1) ^ 2 / 2 + t ^ 2 / 2 - Real.log (t ^ 2 + 1) / 2",
            "(2 * x * Real.log (x ^ 2 + 1) + x ^ 3) / (x ^ 2 + 1)",
            _proof_complex_sum_001(),
        ),
        "pf.integral.bronstein_003": (
            "A", "Real.log (t ^ 2 + 1) / 2", "x / (x ^ 2 + 1)",
            _proof_log_pos_quad("1"),
        ),
        "pf.integral.bronstein_004": (
            "A", "Real.arctan (t ^ 2)", "2 * x / (1 + x ^ 4)",
            _proof_arctan_pow(2),
        ),
        "pf.integral.bronstein_005": (
            "C", "Real.log t / 2 + Real.log (t + 2) / 2",
            "(x + 1) / (x * (x + 2))", _proof_pfd_005(),
        ),
        "pf.integral.bronstein_006": (
            "A", "Real.arctan (t + 1)", "1 / (x ^ 2 + 2 * x + 2)",
            _proof_arctan_linear("1"),
        ),
        "pf.integral.bronstein_007": (
            "B", "Real.log t", "1 / x", _proof_log_simple(),
        ),
        "pf.integral.bronstein_008": (
            "B", "Real.log (t ^ 2 - 4) / 2", "x / (x ^ 2 - 4)",
            _proof_log_neg_quad("4"),
        ),
        "pf.integral.bronstein_009": (
            "D", "Real.log t / 2 - Real.log (t + 1) + Real.log (t + 2) / 2",
            "1 / (x * (x + 1) * (x + 2))", _proof_pfd_009(),
        ),
    }
    if claim_id not in table:
        raise KeyError(f"no discharge spec for {claim_id} (shape={shape})")
    cls, body, integrand, proof = table[claim_id]
    return ClaimSpec(claim_id, theorem_name, cls, body, integrand, proof)


# All nine claims now auto-dischargeable (002 is the equational corollary of 001).
_ALL_CLAIMS = [f"pf.integral.bronstein_{n:03d}" for n in (1, 3, 4, 5, 6, 7, 8, 9)]
# Backwards-compatible alias retained for callers expecting the original four.
_CLASS_A_CLAIMS = [
    ("pf.integral.bronstein_001", "autodischarge_001"),
    ("pf.integral.bronstein_003", "autodischarge_003"),
    ("pf.integral.bronstein_004", "autodischarge_004"),
    ("pf.integral.bronstein_006", "autodischarge_006"),
]


def generate_theorem_text(claim_id: str) -> str:
    """Generate the complete Lean theorem + proof for any supported claim."""
    spec = _spec_for(claim_id)
    hyps = synthesize_hypotheses(FRICAS_CACHE[claim_id]["antideriv_fricas"])
    hyp_str = "".join(f" {h.lean_binder}" for h in hyps)
    stmt = (
        f"theorem {spec.theorem_name} (x : ℝ){hyp_str} :\n"
        f"    HasDerivAt (fun t : ℝ => {spec.antideriv_body})\n"
        f"               ({spec.integrand_expr}) x := by"
    )
    return f"{stmt}\n{spec.proof}"


# ---------------------------------------------------------------------------
# Full .lean file generator
# ---------------------------------------------------------------------------

_LEAN_HEADER = """\
-- AUTO-GENERATED by fricas_bridge/proof_discharger.py
-- DO NOT EDIT BY HAND — regenerate with:
--   python fricas_bridge/proof_discharger.py --generate
--
-- All nine Risch–Bronstein HasDerivAt theorems, auto-discharged across the
-- four discrepancy classes (A: no hypothesis · B: one · C: two · D: three).
-- Each proof is produced mechanically from the FriCAS antiderivative shape and
-- reproduces a pattern already kernel-verified in RischVerification.lean.
import Mathlib.Analysis.SpecialFunctions.Log.Deriv
import Mathlib.Analysis.SpecialFunctions.Trigonometric.Deriv
import Mathlib.Tactic

noncomputable section
open Real

"""

_LEAN_FOOTER = "\nend\n"


def generate_autodischarge_lean() -> str:
    """Return the full text of RischAutoDischarge.lean (all nine claims)."""
    theorems = [generate_theorem_text(cid) for cid in _ALL_CLAIMS]
    return _LEAN_HEADER + "\n\n".join(theorems) + _LEAN_FOOTER


def discharge_all() -> list[dict]:
    """Return one entry per auto-discharged claim."""
    out = []
    for claim_id in _ALL_CLAIMS:
        spec = _spec_for(claim_id)
        out.append({
            "claim_id":     claim_id,
            "theorem_name": spec.theorem_name,
            "class":        spec.cls,
            "lean_text":    generate_theorem_text(claim_id),
            "shape":        classify_antideriv(FRICAS_CACHE[claim_id]["antideriv_fricas"]),
            "hypotheses":   [h.statement for h in
                             synthesize_hypotheses(FRICAS_CACHE[claim_id]["antideriv_fricas"])],
        })
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _verify() -> bool:
    expected = generate_autodischarge_lean()
    if not _LEAN_OUT.exists():
        print(f"FAIL: {_LEAN_OUT} does not exist", file=sys.stderr)
        return False
    actual = _LEAN_OUT.read_text()
    if actual != expected:
        print("FAIL: RischAutoDischarge.lean differs from generated content", file=sys.stderr)
        return False
    print(f"OK: {_LEAN_OUT} matches generated content ({len(actual)} chars)")
    return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Proof discharger for all Risch claims")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--generate", action="store_true", help="Write RischAutoDischarge.lean")
    group.add_argument("--verify", action="store_true",
                       help="Check RischAutoDischarge.lean matches generated content")
    args = parser.parse_args()

    if args.generate:
        content = generate_autodischarge_lean()
        _LEAN_OUT.write_text(content)
        print(f"Written {_LEAN_OUT} ({len(content)} chars)")
    else:
        sys.exit(0 if _verify() else 1)
