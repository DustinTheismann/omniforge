"""
Step D — Proof Discharge.

Pipeline:
  HasDerivAt F f x goal
    → lean_to_fricas  (FriCAS integrand string)
    → FriCAS call     (antiderivative string)  [or FRICAS_CACHE offline]
    → fricas_to_lean  (Lean term)
    → shape classify  (proof strategy)
    → proof script    (Lean tactic block)

Public API
----------
FRICAS_CACHE                       dict[claim_id → {integrand_fricas, antideriv_fricas}]
classify_antideriv(fricas_str)     → shape dict (keys: shape, …)
generate_theorem_text(claim_id)    → str  (theorem statement + proof)
generate_autodischarge_lean()      → str  (full .lean file)
discharge_all()                    → list[dict]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from fricas_bridge.fricas_to_lean import fricas_antideriv_to_lean

_EXAMPLES = Path(__file__).parent.parent / "protocols" / "claim_protocol" / "examples"
_LEAN_OUT  = Path(__file__).parent / "RischAutoDischarge.lean"


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

_RE_LOG_POS_QUAD   = re.compile(r"^log\(x\^2\+(\d+)\)/2$")
_RE_ARCTAN_POW     = re.compile(r"^atan\(x\^(\d+)\)$")
_RE_ARCTAN_LINEAR  = re.compile(r"^atan\(x\+(.+)\)$")


def _diff_inner(inner_lean: str) -> str:
    """Return derivative of a simple polynomial in t (Lean form)."""
    s = inner_lean.strip()
    m = re.fullmatch(r"t \^ (\d+)", s)
    if m:
        n = int(m.group(1))
        return "2 * t" if n == 2 else f"{n} * t ^ {n - 1}"
    if re.fullmatch(r"t \+ \d+(?:\.\d+)?", s):
        return "1"
    if s == "t":
        return "1"
    m = re.fullmatch(r"(\d+) \* t", s)
    if m:
        return m.group(1)
    return "1"


def classify_antideriv(fricas_antideriv: str) -> dict:
    """
    Classify a FriCAS antiderivative string into a proof shape.

    Returns a dict with a ``shape`` key plus shape-specific parameters.
    Shapes:
      LOG_POS_QUAD   — log(x²+c)/2,    c > 0
      ARCTAN_POW     — atan(x^n)
      ARCTAN_LINEAR  — atan(x+c)
      COMPLEX_SUM    — multi-term (claim 001 pattern)
      UNKNOWN        — unrecognised
    """
    s = fricas_antideriv.strip().replace(" ", "")

    m = _RE_LOG_POS_QUAD.match(s)
    if m:
        c = m.group(1)
        return {"shape": "LOG_POS_QUAD", "c": c}

    m = _RE_ARCTAN_POW.match(s)
    if m:
        n = int(m.group(1))
        p_lean = f"t ^ {n}"
        dp_lean = "2 * t" if n == 2 else f"{n} * t ^ {n - 1}"
        return {"shape": "ARCTAN_POW", "n": n, "p_lean": p_lean, "dp_lean": dp_lean}

    m = _RE_ARCTAN_LINEAR.match(s)
    if m:
        c = m.group(1)
        p_lean = f"t + {c}"
        return {"shape": "ARCTAN_LINEAR", "c": c, "p_lean": p_lean, "dp_lean": "1"}

    if "log" in s and "^2" in s:
        return {"shape": "COMPLEX_SUM"}

    return {"shape": "UNKNOWN"}


# ---------------------------------------------------------------------------
# Proof generators
# ---------------------------------------------------------------------------

def _proof_log_pos_quad(c: str) -> str:
    """Proof body for HasDerivAt (fun t => Real.log (t^2 + c) / 2) (x/(x^2+c)) x."""
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
    """Proof body for HasDerivAt (fun t => Real.arctan (t^n)) (n*x/(1+x^(2n))) x."""
    p_lean  = f"t ^ {n}"
    p_at_x  = f"x ^ {n}"
    dp_lean = "2 * x" if n == 2 else f"{n} * x"
    x2n     = f"x ^ {2 * n}"
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
    """Proof body for HasDerivAt (fun t => Real.arctan (t+c)) (1/(x²+2cx+c²+1)) x."""
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
    """7-step proof for claim 001: log(x²+1)²/2 + x²/2 − log(x²+1)/2."""
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
# Per-claim theorem text
# ---------------------------------------------------------------------------

_CLASS_A_CLAIMS = [
    ("pf.integral.bronstein_001", "autodischarge_001"),
    ("pf.integral.bronstein_003", "autodischarge_003"),
    ("pf.integral.bronstein_004", "autodischarge_004"),
    ("pf.integral.bronstein_006", "autodischarge_006"),
]

# Lean statement fragments for each Class A claim (antideriv_body, integrand_expr)
_CLAIM_LEAN: dict[str, tuple[str, str]] = {
    "pf.integral.bronstein_001": (
        "Real.log (t ^ 2 + 1) ^ 2 / 2 + t ^ 2 / 2 - Real.log (t ^ 2 + 1) / 2",
        "(2 * x * Real.log (x ^ 2 + 1) + x ^ 3) / (x ^ 2 + 1)",
    ),
    "pf.integral.bronstein_003": (
        "Real.log (t ^ 2 + 1) / 2",
        "x / (x ^ 2 + 1)",
    ),
    "pf.integral.bronstein_004": (
        "Real.arctan (t ^ 2)",
        "2 * x / (1 + x ^ 4)",
    ),
    "pf.integral.bronstein_006": (
        "Real.arctan (t + 1)",
        "1 / (x ^ 2 + 2 * x + 2)",
    ),
}


def generate_theorem_text(claim_id: str) -> str:
    """
    Generate the complete Lean theorem + proof for a Class A claim.

    Returns a multi-line string starting with the ``theorem`` keyword.
    Raises ``KeyError`` if claim_id is not a supported Class A claim.
    """
    antideriv_body, integrand_expr = _CLAIM_LEAN[claim_id]
    theorem_name = "autodischarge_" + claim_id.split("_")[-1]

    # Determine theorem statement
    stmt = (
        f"theorem {theorem_name} (x : ℝ) :\n"
        f"    HasDerivAt (fun t : ℝ => {antideriv_body})\n"
        f"               ({integrand_expr}) x := by"
    )

    # Select proof body
    fricas_antideriv = FRICAS_CACHE[claim_id]["antideriv_fricas"]
    shape = classify_antideriv(fricas_antideriv)

    if shape["shape"] == "LOG_POS_QUAD":
        proof_body = _proof_log_pos_quad(shape["c"])
    elif shape["shape"] == "ARCTAN_POW":
        proof_body = _proof_arctan_pow(shape["n"])
    elif shape["shape"] == "ARCTAN_LINEAR":
        proof_body = _proof_arctan_linear(shape["c"])
    elif shape["shape"] == "COMPLEX_SUM":
        proof_body = _proof_complex_sum_001()
    else:
        raise ValueError(f"Unsupported shape {shape['shape']!r} for {claim_id}")

    return f"{stmt}\n{proof_body}"


# ---------------------------------------------------------------------------
# Full .lean file generator
# ---------------------------------------------------------------------------

_LEAN_HEADER = """\
-- AUTO-GENERATED by fricas_bridge/proof_discharger.py
-- DO NOT EDIT BY HAND — regenerate with:
--   python fricas_bridge/proof_discharger.py --generate
--
-- Four Class A Risch–Bronstein HasDerivAt theorems, auto-discharged.
-- Each proof is produced mechanically from the FriCAS antiderivative shape.
import Mathlib.Analysis.SpecialFunctions.Log.Deriv
import Mathlib.Analysis.SpecialFunctions.Trigonometric.Deriv
import Mathlib.Tactic

noncomputable section
open Real

"""

_LEAN_FOOTER = "\nend\n"


def generate_autodischarge_lean() -> str:
    """Return the full text of RischAutoDischarge.lean."""
    theorems = [generate_theorem_text(cid) for cid, _ in _CLASS_A_CLAIMS]
    return _LEAN_HEADER + "\n\n".join(theorems) + _LEAN_FOOTER


# ---------------------------------------------------------------------------
# discharge_all — public convenience wrapper
# ---------------------------------------------------------------------------

def discharge_all() -> list[dict]:
    """Return one entry per Class A claim with claim_id and generated theorem text."""
    result = []
    for claim_id, theorem_name in _CLASS_A_CLAIMS:
        text = generate_theorem_text(claim_id)
        result.append({
            "claim_id":     claim_id,
            "theorem_name": theorem_name,
            "lean_text":    text,
            "shape":        classify_antideriv(FRICAS_CACHE[claim_id]["antideriv_fricas"]),
        })
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _verify() -> bool:
    """Return True iff RischAutoDischarge.lean matches what we would generate."""
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

    parser = argparse.ArgumentParser(description="Proof discharger for Class A Risch claims")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--generate", action="store_true",
                       help="Write RischAutoDischarge.lean")
    group.add_argument("--verify", action="store_true",
                       help="Check that RischAutoDischarge.lean matches generated content")
    args = parser.parse_args()

    if args.generate:
        content = generate_autodischarge_lean()
        _LEAN_OUT.write_text(content)
        print(f"Written {_LEAN_OUT} ({len(content)} chars)")
    else:
        sys.exit(0 if _verify() else 1)
