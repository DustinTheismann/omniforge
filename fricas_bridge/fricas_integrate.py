#!/usr/bin/env python3
"""
fricas_integrate.py — FriCAS → Lean 4 integration verification pipeline.

For each integral: call FriCAS (if available), translate the result into Lean 4,
infer domain-restriction hypotheses (the conditions FriCAS omits), and emit a
HasDerivAt theorem file with a proof scaffold.

Usage
-----
  # With FriCAS in PATH — full pipeline:
  python3 fricas_integrate.py --integrand "x/(x^2+1)" --var x

  # Supply antiderivative manually (no FriCAS needed):
  python3 fricas_integrate.py --integrand "(2*x*log(x^2+1)+x^3)/(x^2+1)" \\
                               --antideriv "log(x^2+1)^2/2 + x^2/2 - log(x^2+1)/2"

  # Run the built-in corpus and emit all theorems:
  python3 fricas_integrate.py --corpus

  # Show inferred hypotheses only (domain-restriction audit):
  python3 fricas_integrate.py --corpus --audit

Output
------
  One .lean file per integral, e.g. risch_001.lean, risch_002.lean, ...
  Written to output/risch/ by default.

Discrepancy-finding
-------------------
  The --audit flag prints every implicit domain restriction that FriCAS's output
  fails to state.  Each one is either:
    (a) a routine condition (x²+1 ≠ 0, always satisfied) — not a discrepancy
    (b) a genuine restriction (x ≠ 0, x ≠ -2) — must appear as hypothesis
    (c) a branch-cut condition — may indicate FriCAS chose a non-principal branch
  Case (b) and (c) are the interesting ones: they surface assumptions FriCAS
  treated as implicit.  Every (b)/(c) that appears without a corresponding
  explicit note in the CAS output is a documentation gap or a potential bug.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from textwrap import dedent

# ---------------------------------------------------------------------------
# Built-in corpus: (label, fricas_integrand, fricas_antiderivative, variable)
# From Bronstein, Symbolic Integration I (2005), and standard tables.
# ---------------------------------------------------------------------------

CORPUS: list[dict] = [
    # ── Class A: No domain restriction (log args always x²+c > 0) ────────────
    {
        "label": "bronstein_1_1",
        "class": "A",
        "description": "Bronstein §1.1 — flagship Risch example; no domain restriction (x²+1 > 0)",
        "integrand":    "(2*x*log(x^2+1)+x^3)/(x^2+1)",
        "antiderivative": "log(x^2+1)^2/2 + x^2/2 - log(x^2+1)/2",
        "var": "x",
    },
    {
        "label": "simple_log",
        "class": "A",
        "description": "∫ x/(x²+1) dx = log(x²+1)/2; no domain restriction",
        "integrand":    "x/(x^2+1)",
        "antiderivative": "log(x^2+1)/2",
        "var": "x",
    },
    {
        "label": "arctan_chain",
        "class": "A",
        "description": "∫ 2x/(1+x⁴) dx = arctan(x²); no domain restriction",
        "integrand":    "2*x/(1+x^4)",
        "antiderivative": "atan(x^2)",
        "var": "x",
    },
    {
        "label": "basic_arctan",
        "class": "A",
        "description": "∫ 1/(1+x²) dx = arctan(x); no domain restriction",
        "integrand":    "1/(1+x^2)",
        "antiderivative": "atan(x)",
        "var": "x",
    },
    {
        "label": "quadratic_arctan",
        "class": "A",
        "description": "∫ 1/(x²+4) dx = arctan(x/2)/2; no domain restriction",
        "integrand":    "1/(x^2+4)",
        "antiderivative": "atan(x/2)/2",
        "var": "x",
    },
    {
        "label": "arctan_shifted",
        "class": "A",
        "description": "∫ 1/(x²+2x+2) dx = arctan(x+1); no domain restriction ((x+1)²+1 > 0)",
        "integrand":    "1/(x^2+2*x+2)",
        "antiderivative": "atan(x+1)",
        "var": "x",
    },
    # ── Class B: Log with sign-sensitive argument (simple poles) ─────────────
    {
        "label": "log_x",
        "class": "B",
        "description": "∫ log(x) dx = x·log(x)−x; domain: x ≠ 0  [FriCAS omits this]",
        "integrand":    "log(x)",
        "antiderivative": "x*log(x) - x",
        "var": "x",
    },
    {
        "label": "x2_log_x",
        "class": "B",
        "description": "∫ x²·log(x) dx = x³·log(x)/3−x³/9; domain: x ≠ 0  [FriCAS omits]",
        "integrand":    "x^2*log(x)",
        "antiderivative": "x^3*log(x)/3 - x^3/9",
        "var": "x",
    },
    {
        "label": "recip_x",
        "class": "B",
        "description": "∫ 1/x dx = log(x); domain: x ≠ 0  [FriCAS omits]",
        "integrand":    "1/x",
        "antiderivative": "log(x)",
        "var": "x",
    },
    {
        "label": "recip_linear",
        "class": "B",
        "description": "∫ 1/(x+1) dx = log(x+1); domain: x+1 ≠ 0  [FriCAS omits]",
        "integrand":    "1/(x+1)",
        "antiderivative": "log(x+1)",
        "var": "x",
    },
    {
        "label": "linear_over_linear",
        "class": "B",
        "description": "∫ (x+2)/(x+1) dx = x+log(x+1); domain: x+1 ≠ 0  [FriCAS omits]",
        "integrand":    "(x+2)/(x+1)",
        "antiderivative": "x + log(x+1)",
        "var": "x",
    },
    {
        "label": "log_quadratic_neg",
        "class": "B",
        "description": "∫ x/(x²−4) dx = log(x²−4)/2; domain: x²−4 ≠ 0 (x ≠ ±2)  [FriCAS omits]",
        "integrand":    "x/(x^2-4)",
        "antiderivative": "log(x^2-4)/2",
        "var": "x",
    },
    # ── Class C: Two-pole partial fractions ──────────────────────────────────
    {
        "label": "rational_poles",
        "class": "C",
        "description": "∫ 1/(x²−1) dx = log(x−1)/2−log(x+1)/2; domain: x≠1, x≠−1",
        "integrand":    "1/(x^2-1)",
        "antiderivative": "log(x-1)/2 - log(x+1)/2",
        "var": "x",
    },
    {
        "label": "partial_fractions",
        "class": "C",
        "description": "∫ (x+1)/(x(x+2)) dx; domain: x≠0, x≠−2  [FriCAS omits both]",
        "integrand":    "(x+1)/(x*(x+2))",
        "antiderivative": "log(x)/2 + log(x+2)/2",
        "var": "x",
    },
    {
        "label": "two_poles_linear",
        "class": "C",
        "description": "∫ (2x+1)/(x(x+1)) dx = log(x)+log(x+1); domain: x≠0, x≠−1",
        "integrand":    "(2*x+1)/(x*(x+1))",
        "antiderivative": "log(x) + log(x+1)",
        "var": "x",
    },
    {
        "label": "pf_distinct_2",
        "class": "C",
        "description": "∫ 1/((x−1)(x−3)) dx = log(x−3)/2−log(x−1)/2; domain: x≠1, x≠3",
        "integrand":    "1/((x-1)*(x-3))",
        "antiderivative": "log(x-3)/2 - log(x-1)/2",
        "var": "x",
    },
    {
        "label": "pf_shifted_2",
        "class": "C",
        "description": "∫ (3x+2)/((x+1)(x+2)) dx = −log(x+1)+4log(x+2); domain: x≠−1, x≠−2",
        "integrand":    "(3*x+2)/((x+1)*(x+2))",
        "antiderivative": "-log(x+1) + 4*log(x+2)",
        "var": "x",
    },
    {
        "label": "log_ratio_2",
        "class": "C",
        "description": "∫ 1/((x+2)(x+4)) dx = log(x+2)/2−log(x+4)/2; domain: x≠−2, x≠−4",
        "integrand":    "1/((x+2)*(x+4))",
        "antiderivative": "log(x+2)/2 - log(x+4)/2",
        "var": "x",
    },
    # ── Class D: Three-or-more-pole partial fractions ─────────────────────────
    {
        "label": "three_poles",
        "class": "D",
        "description": "∫ 1/(x(x+1)(x+2)) dx; domain: x≠0, x≠−1, x≠−2  [3 implicit hypotheses]",
        "integrand":    "1/(x*(x+1)*(x+2))",
        "antiderivative": "log(x)/2 - log(x+1) + log(x+2)/2",
        "var": "x",
    },
    {
        "label": "three_poles_sym",
        "class": "D",
        "description": "∫ 1/(x(x−1)(x+1)) dx; domain: x≠0, x≠1, x≠−1  [3 implicit hypotheses]",
        "integrand":    "1/(x*(x-1)*(x+1))",
        "antiderivative": "-log(x) + log(x-1)/2 + log(x+1)/2",
        "var": "x",
    },
    {
        "label": "three_poles_shifted",
        "class": "D",
        "description": "∫ 1/((x+1)(x+2)(x+3)) dx; domain: x≠−1, x≠−2, x≠−3",
        "integrand":    "1/((x+1)*(x+2)*(x+3))",
        "antiderivative": "log(x+1)/2 - log(x+2) + log(x+3)/2",
        "var": "x",
    },
    {
        "label": "pf_weighted",
        "class": "D",
        "description": "∫ (2x²+5x+1)/(x(x+1)(x+2)) dx; domain: x≠0, x≠−1, x≠−2",
        "integrand":    "(2*x^2+5*x+1)/(x*(x+1)*(x+2))",
        "antiderivative": "log(x)/2 + 2*log(x+1) - log(x+2)/2",
        "var": "x",
    },
    {
        "label": "four_poles",
        "class": "D",
        "description": "∫ 1/(x(x+1)(x+2)(x+3)) dx; domain: x≠0,−1,−2,−3  [4 implicit hypotheses]",
        "integrand":    "1/(x*(x+1)*(x+2)*(x+3))",
        "antiderivative": "log(x)/6 - log(x+1)/2 + log(x+2)/2 - log(x+3)/6",
        "var": "x",
    },
    {
        "label": "pf_numer_deg2",
        "class": "D",
        "description": "∫ (x²−x−1)/(x(x−1)(x+1)) dx; domain: x≠0, x≠1, x≠−1",
        "integrand":    "(x^2-x-1)/(x*(x-1)*(x+1))",
        "antiderivative": "log(x) - log(x-1)/2 + log(x+1)/2",
        "var": "x",
    },
    # ── Class E: Extended rational PFD — new FORM_DISAGREE cases ─────────────
    # These integrands produce FriCAS factored log form vs SymPy product form.
    # The disagreement is proved notational by Real.log_mul in CasAdjudication.lean.
    {
        "label": "x_over_x4m1",
        "class": "E",
        "description": (
            "∫ x/(x⁴−1) dx; FriCAS → log(x−1)/4+log(x+1)/4−log(x²+1)/4; "
            "SymPy → log(x²−1)/4−log(x²+1)/4; FORM_DISAGREE via Real.log_mul"
        ),
        "integrand":    "x/(x^4-1)",
        "antiderivative": "log(x-1)/4 + log(x+1)/4 - log(x^2+1)/4",
        "var": "x",
    },
    {
        "label": "three_poles_sym_alt",
        "class": "E",
        "description": (
            "∫ 1/(x(x+1)(x−1)) dx; FriCAS → −log(x)+log(x−1)/2+log(x+1)/2; "
            "SymPy → −log(x)+log(x²−1)/2; FORM_DISAGREE via Real.log_mul. "
            "Alias for three_poles_sym with x+1 and x−1 swapped."
        ),
        "integrand":    "1/(x*(x+1)*(x-1))",
        "antiderivative": "-log(x) + log(x-1)/2 + log(x+1)/2",
        "var": "x",
    },
]


# ---------------------------------------------------------------------------
# Expression translation: FriCAS/SPAD → Lean 4
# ---------------------------------------------------------------------------

# Ordered list of (pattern, replacement) for regex substitution.
# Apply in order — earlier rules take priority.
_TRANS_RULES: list[tuple[str, str]] = [
    # Function names
    (r'\batan\b',    'Real.arctan'),
    (r'\barctan\b',  'Real.arctan'),
    (r'\basin\b',    'Real.arcsin'),
    (r'\bacos\b',    'Real.arccos'),
    (r'\bsin\b',     'Real.sin'),
    (r'\bcos\b',     'Real.cos'),
    (r'\btan\b',     'Real.tan'),
    (r'\bexp\b',     'Real.exp'),
    (r'\bsqrt\b',    'Real.sqrt'),
    (r'\babs\b',     'abs'),
    (r'\blog\b',     'Real.log'),   # must come after atan/asin/acos/exp
    # Power: ensure spaces (x^2 → x ^ 2)
    (r'\^',          ' ^ '),
    # Collapse multiple spaces
    (r'  +',         ' '),
]


def fricas_to_lean(expr: str) -> str:
    """Translate a FriCAS-style expression string to Lean 4 notation."""
    s = expr.strip()
    for pat, rep in _TRANS_RULES:
        s = re.sub(pat, rep, s)
    # Add spaces around binary + and - (preceded by alphanumeric/) followed by alnum/()
    s = re.sub(r'(?<=[a-zA-Z0-9_\)])([+\-])(?=[a-zA-Z0-9_(])', r' \1 ', s)
    # Collapse multiple spaces
    s = re.sub(r'  +', ' ', s)
    return s.strip()


# ---------------------------------------------------------------------------
# Hypothesis inference: find conditions FriCAS leaves implicit
# ---------------------------------------------------------------------------

@dataclass
class Hypothesis:
    lean_expr: str    # e.g. "x ^ 2 + 1"
    kind: str         # "denom" | "log_arg"
    trivial: bool     # True if x²+1 type — always positive, nonzero

    @property
    def _base_name(self) -> str:
        s = self.lean_expr
        s = re.sub(r'\s+\+\s+', '_add_', s)
        s = re.sub(r'\s+-\s+', '_sub_', s)
        s = re.sub(r'[^a-zA-Z0-9]', '_', s).strip('_')
        return re.sub(r'__+', '_', s)

    @property
    def name(self) -> str:
        return f"h_{self._base_name}"

    @property
    def statement(self) -> str:
        return f"({self.lean_expr} : ℝ) ≠ 0"


def _is_trivially_positive(expr: str) -> bool:
    """Return True if expr is syntactically x^(2k)+c form — always positive."""
    e = expr.strip().replace(' ', '')
    # Matches: c, x^2+c, x^4+c, etc.
    return bool(re.match(r'^[a-z]\s*\^\s*[2468]\s*\+\s*\d+$', e)
                or re.match(r'^\d+\s*\+\s*[a-z]\s*\^\s*[2468]$', e)
                or re.match(r'^\d+$', e)
                or re.match(r'^[a-z]\s*\^\s*[2468]$', e))


def _extract_denominators(expr: str) -> list[str]:
    """Extract all denominator subexpressions from a / b patterns at depth 0."""
    results = []
    i = 0
    while i < len(expr):
        if expr[i] == '/' and (i == 0 or expr[i-1] not in '*/'):
            # find the numerator end and denominator start
            j = i + 1
            while j < len(expr) and expr[j] == ' ':
                j += 1
            if j < len(expr) and expr[j] == '(':
                # parenthesized denominator
                depth, k = 1, j + 1
                while k < len(expr) and depth > 0:
                    if expr[k] == '(':
                        depth += 1
                    elif expr[k] == ')':
                        depth -= 1
                    k += 1
                results.append(expr[j+1:k-1].strip())
            else:
                # simple token denominator
                m = re.match(r'([a-zA-Z_][a-zA-Z0-9_]*(?:\s*\^\s*\d+)?)', expr[j:])
                if m:
                    results.append(m.group(1).strip())
        i += 1
    return results


def _extract_log_args(expr: str) -> list[str]:
    """Extract argument expressions from log(...) calls."""
    results = []
    for m in re.finditer(r'\blog\s*\(', expr):
        start = m.end()
        depth, i = 1, start
        while i < len(expr) and depth > 0:
            if expr[i] == '(':
                depth += 1
            elif expr[i] == ')':
                depth -= 1
            i += 1
        results.append(expr[start:i-1].strip())
    return results


def infer_hypotheses(integrand: str, antiderivative: str, var: str) -> list[Hypothesis]:
    """
    Scan integrand and antiderivative for implicit domain conditions.
    Returns hypotheses in the order FriCAS would need to state them.
    """
    hyps: list[Hypothesis] = []
    seen: set[str] = set()

    def add(lean_expr: str, kind: str):
        key = lean_expr.replace(' ', '')
        if key not in seen:
            seen.add(key)
            trivial = _is_trivially_positive(lean_expr.replace(' ', ''))
            hyps.append(Hypothesis(lean_expr=lean_expr, kind=kind, trivial=trivial))

    # Denominators in the integrand (must be nonzero for the integrand to be defined)
    for raw in _extract_denominators(integrand):
        add(fricas_to_lean(raw), 'denom')

    # Log arguments in the antiderivative (must be nonzero for HasDerivAt.log)
    for raw in _extract_log_args(antiderivative):
        add(fricas_to_lean(raw), 'log_arg')

    return hyps


# ---------------------------------------------------------------------------
# Lean theorem file generation
# ---------------------------------------------------------------------------

_THEOREM_TEMPLATE = """\
import Mathlib.Analysis.SpecialFunctions.Log.Deriv
import Mathlib.Analysis.SpecialFunctions.Trigonometric.Deriv
import Mathlib.Tactic

/-!
# Risch Integration Certificate — {label}

{description}

FriCAS input:
  integrate({integrand_fricas}, {var})

FriCAS output:
  {antiderivative_fricas}

Lean verification: HasDerivAt antiderivative (integrand x) x

{domain_note}
-/

noncomputable section
open Real

def risch_integrand_{label} ({var} : ℝ) : ℝ :=
  {integrand_lean}

def risch_antideriv_{label} ({var} : ℝ) : ℝ :=
  {antiderivative_lean}

end

/--
FriCAS certificate: the antiderivative has derivative equal to the integrand.
{hyp_doc}
-/
theorem risch_verified_{label} ({var} : ℝ){hyp_args} :
    HasDerivAt risch_antideriv_{label} (risch_integrand_{label} {var}) {var} := by
{proof_body}
"""

_PROOF_SCAFFOLD = """\
  -- TODO: fill in derivative computation
  -- Hint: unfold risch_antideriv_{label} risch_integrand_{label}
  -- 1. For each summand d_i of the antiderivative:
  --      have h_i : HasDerivAt (fun t => <summand_i>) <deriv_i> x := by ...
  -- 2. Combine with h_1.add h_2 ... |>.sub h_k
  -- 3. convert ... using 1; field_simp {hyp_names}; ring
  sorry"""


def generate_lean_file(entry: dict) -> str:
    """Generate a Lean 4 theorem file from a corpus entry."""
    label        = entry["label"]
    var          = entry.get("var", "x")
    int_fricas   = entry["integrand"]
    anti_fricas  = entry["antiderivative"]
    description  = entry.get("description", "")
    int_lean     = fricas_to_lean(int_fricas)
    anti_lean    = fricas_to_lean(anti_fricas)

    hyps = infer_hypotheses(int_fricas, anti_fricas, var)
    nontrivial = [h for h in hyps if not h.trivial]

    # Build deduplicated hypothesis names
    _name_counts: dict[str, int] = {}
    hyp_names_list: list[str] = []
    for h in nontrivial:
        base = h.name
        n = _name_counts.get(base, 0)
        _name_counts[base] = n + 1
        hyp_names_list.append(base if n == 0 else f"{base}_{n + 1}")

    # Hypothesis arguments for theorem signature
    if nontrivial:
        hyp_args = " " + " ".join(
            f"({name} : {h.statement})"
            for name, h in zip(hyp_names_list, nontrivial)
        )
    else:
        hyp_args = ""

    # Domain restriction note for the module doc
    if nontrivial:
        lines = ["**Domain restrictions** (implicit in FriCAS, explicit here):"]
        for name, h in zip(hyp_names_list, nontrivial):
            lines.append(f"  - `{h.lean_expr} ≠ 0`  ({h.kind})  → hypothesis `{name}`")
        domain_note = "\n".join(lines)
        hyp_doc = "\nHypotheses: " + ", ".join(f"`{n}`" for n in hyp_names_list)
        hyp_names = "[" + ", ".join(hyp_names_list) + "]"
    else:
        domain_note = "No domain restriction needed — the integrand is defined on all of ℝ."
        hyp_doc = ""
        hyp_names = ""

    proof_body = _PROOF_SCAFFOLD.format(label=label, hyp_names=hyp_names)

    return _THEOREM_TEMPLATE.format(
        label            = label,
        description      = description,
        var              = var,
        integrand_fricas = int_fricas,
        antiderivative_fricas = anti_fricas,
        integrand_lean   = int_lean,
        antiderivative_lean = anti_lean,
        domain_note      = domain_note,
        hyp_doc          = hyp_doc,
        hyp_args         = hyp_args,
        proof_body       = proof_body,
    )


# ---------------------------------------------------------------------------
# FriCAS subprocess interface
# ---------------------------------------------------------------------------

FRICAS_PREAMBLE = """)set output algebra on
)set output mathml off
)set output tex off
"""

def call_fricas(integrand: str, var: str, timeout: int = 30) -> str | None:
    """
    Call FriCAS via subprocess and return the antiderivative string.
    Returns None if FriCAS is not available or the computation fails.
    """
    if not shutil.which("fricas"):
        return None

    cmd = f"{FRICAS_PREAMBLE}integrate({integrand}, {var})\n)quit\n"
    try:
        result = subprocess.run(
            ["fricas", "-nosman"],
            input=cmd, capture_output=True, text=True, timeout=timeout
        )
        output = result.stdout
        # FriCAS wraps its answer; extract the expression after "="
        m = re.search(r'\(1\)\s+(.*?)(?:\n|$)', output)
        if m:
            return m.group(1).strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


# ---------------------------------------------------------------------------
# Audit mode: print domain restriction summary across the corpus
# ---------------------------------------------------------------------------

_CLASS_NAMES = {
    "A": "No domain restriction (log args always positive)",
    "B": "Simple log-domain restriction",
    "C": "Two-pole partial fractions",
    "D": "Three-or-more-pole partial fractions",
}


def audit_corpus(corpus: list[dict]) -> None:
    # Collect per-entry results first
    results = []
    for entry in corpus:
        hyps = infer_hypotheses(entry["integrand"], entry["antiderivative"], entry["var"])
        nontrivial = [h for h in hyps if not h.trivial]
        results.append((entry, nontrivial))

    # Group by class
    classes: dict[str, list] = {}
    for entry, hyps in results:
        cls = entry.get("class", "?")
        classes.setdefault(cls, []).append((entry, hyps))

    total_gaps = 0
    total_integrals = len(corpus)

    for cls in sorted(classes):
        cls_entries = classes[cls]
        cls_gaps = sum(len(h) for _, h in cls_entries)
        total_gaps += cls_gaps
        clean = sum(1 for _, h in cls_entries if not h)
        print(f"\nClass {cls}: {_CLASS_NAMES.get(cls, cls)}")
        print(f"  {len(cls_entries)} integrals, {cls_gaps} non-trivial conditions, {clean} clean")
        print(f"  {'Integral':<26} {'Lean condition':<32} Kind")
        print(f"  {'-'*26} {'-'*32} ----")
        for entry, hyps in cls_entries:
            if not hyps:
                print(f"  {entry['label']:<26} (none — defined on all ℝ)")
            for h in hyps:
                print(f"  {entry['label']:<26} {h.lean_expr:<32} {h.kind}")

    print()
    print("=" * 72)
    print(f"SUMMARY: {total_integrals} integrals, {total_gaps} non-trivial conditions")
    print(f"  FriCAS omits every one of these {total_gaps} conditions from its output.")
    print(f"  Each is a hypothesis that Lean forces the caller to state explicitly.")
    class_counts = {cls: sum(len(h) for _, h in entries)
                    for cls, entries in classes.items()}
    for cls in sorted(class_counts):
        n = class_counts[cls]
        total_in_class = len(classes[cls])
        print(f"  Class {cls}: {n} conditions across {total_in_class} integrals")
    print("=" * 72)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    ap = argparse.ArgumentParser(
        description="FriCAS → Lean 4 integration verification pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage")[0].strip(),
    )
    ap.add_argument("--integrand",    help="integrand expression (FriCAS syntax)")
    ap.add_argument("--antideriv",    help="antiderivative (FriCAS syntax); omit to call FriCAS")
    ap.add_argument("--var",          default="x", help="integration variable")
    ap.add_argument("--corpus",       action="store_true", help="process the built-in corpus")
    ap.add_argument("--audit",        action="store_true", help="print domain-restriction audit")
    ap.add_argument("--fricas",       action="store_true", help="call FriCAS for each corpus entry")
    ap.add_argument("--output-dir",   default="output/risch", help="output directory")
    args = ap.parse_args()

    out_dir = Path(args.output_dir)

    # --- Audit mode ---
    if args.audit:
        audit_corpus(CORPUS)
        return

    # --- Corpus mode ---
    if args.corpus:
        out_dir.mkdir(parents=True, exist_ok=True)
        for i, entry in enumerate(CORPUS, 1):
            if args.fricas:
                anti = call_fricas(entry["integrand"], entry["var"])
                if anti:
                    print(f"FriCAS [{entry['label']}]: {anti}")
                    entry = {**entry, "antiderivative": anti}
                else:
                    print(f"FriCAS unavailable for {entry['label']}; using corpus value.")
            lean_code = generate_lean_file(entry)
            out_path = out_dir / f"risch_{i:03d}_{entry['label']}.lean"
            out_path.write_text(lean_code)
            hyps = [h for h in infer_hypotheses(
                entry["integrand"], entry["antiderivative"], entry["var"])
                if not h.trivial]
            restrictions = ", ".join(f"{h.lean_expr} ≠ 0" for h in hyps) or "(none)"
            print(f"  [{i:02d}] {entry['label']:<25}  domain: {restrictions}")
            print(f"        → {out_path}")
        print(f"\n{len(CORPUS)} theorem files written to {out_dir}/")
        return

    # --- Single integral mode ---
    if not args.integrand:
        ap.print_help()
        sys.exit(1)

    antiderivative = args.antideriv
    if antiderivative is None:
        antiderivative = call_fricas(args.integrand, args.var)
        if antiderivative is None:
            print("Error: FriCAS not available. Provide --antideriv explicitly.")
            sys.exit(1)
        print(f"FriCAS result: {antiderivative}")

    entry = {
        "label":          re.sub(r'[^a-z0-9]', '_', args.integrand[:20].lower()),
        "description":    f"∫ {args.integrand} d{args.var}",
        "integrand":      args.integrand,
        "antiderivative": antiderivative,
        "var":            args.var,
    }
    lean_code = generate_lean_file(entry)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"risch_{entry['label']}.lean"
    out_path.write_text(lean_code)
    print(lean_code)
    print(f"\n→ Written to {out_path}")


if __name__ == "__main__":
    main()
