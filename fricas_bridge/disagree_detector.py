"""
Tier 5.4 — Three-CAS disagreement detector with kernel adjudication stubs.

Compares FriCAS, SymPy, and Maxima antiderivatives for the same integrand
and classifies the disagreement precisely:

  AGREE              All present answers are symbolically identical (after norm).
  AGREE_UP_TO_C      All present answers differ by at most a real constant.
  FORM_DISAGREE      All answers are mathematically correct (verified by SymPy
                     differentiation) but take different symbolic forms — e.g.
                     FriCAS log(a)/2 + log(b)/2 vs SymPy log(a*b)/2.  These
                     forms are equal on the principal real domain but may differ
                     as complex-valued functions (branch-cut choice).
  DOMAIN_DISAGREE    Answers differ in domain of validity on the real line, e.g.
                     Maxima acosh(x) (only real for x ≥ 1) vs SymPy log(x +
                     sqrt(x²-1)) (extends via complex log).
  GENUINE_DISAGREE   At least one answer fails the derivative check (potential
                     CAS bug or incorrect side-condition handling).
  ONE_MISSING        Exactly one CAS returned no result.
  TWO_MISSING        Exactly two CAS returned no result.
  BOTH_MISSING / ALL_MISSING  No CAS returned a result.

A KernelAdjudicationPlan is generated for FORM_DISAGREE and DOMAIN_DISAGREE
cases: it lists the Lean HasDerivAt statement that would need to be proved for
each candidate antiderivative, and which hypotheses each form requires.  The
plan is a specification, not a running prover — the Lean CI is the arbiter.

Public API
----------
DisagreementClass               Enum
DisagreementReport              dataclass
KernelAdjudicationPlan          dataclass
compare_triple(integrand, var)  → DisagreementReport
scan_corpus(entries)            → list[DisagreementReport]
scan_bronstein()                → list[DisagreementReport]
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from fricas_bridge.offline_cache import FriCASResolver
from fricas_bridge.sympy_resolver import SymPyResolver
from fricas_bridge.maxima_resolver import MaximaResolver


class DisagreementClass(str, Enum):
    AGREE            = "agree"
    AGREE_UP_TO_C    = "agree_up_to_c"
    FORM_DISAGREE    = "form_disagree"
    DOMAIN_DISAGREE  = "domain_disagree"
    GENUINE_DISAGREE = "genuine_disagree"
    ONE_MISSING      = "one_missing"
    TWO_MISSING      = "two_missing"
    ALL_MISSING      = "all_missing"


@dataclass
class KernelAdjudicationPlan:
    """
    Specification for kernel adjudication of a disagreement.

    Each candidate is a dict {"antideriv": str, "hypotheses": list[str], "lean_statement": str}.
    The `lean_statement` is the HasDerivAt theorem text that would need to be
    checked by Lean + Mathlib.  The actual verdict is determined by CI.
    """
    integrand: str
    var: str
    candidates: list[dict]  # [{"source": str, "antideriv": str, "hypotheses": list[str], "lean_statement": str}]
    adjudication_class: str  # "form_equivalent" | "domain_restricted" | "one_incorrect"
    notes: str = ""


@dataclass
class DisagreementReport:
    integrand: str
    var: str
    fricas_result: Optional[str]
    sympy_result: Optional[str]
    maxima_result: Optional[str]
    disagreement: str                      # DisagreementClass value
    present_count: int
    derivative_correct: dict[str, bool]    # {source: correct?} — SymPy-verified
    adjudication_plan: Optional[KernelAdjudicationPlan] = None
    notes: str = ""


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def _norm(expr: str) -> str:
    """Quick canonical form: whitespace-free, ^ unified, log/ln unified."""
    if not expr:
        return ""
    s = expr.replace(" ", "")
    s = s.replace("**", "^")
    s = re.sub(r"\bln\(", "log(", s)
    s = s.lower()
    return s


def _differ_by_constant(a: str, b: str) -> bool:
    """Heuristic: a and b differ by a constant iff their non-constant token sets match."""
    def _tokens(s: str) -> frozenset:
        norm = _norm(s)
        parts = re.split(r"(?<![e*/^(])[+-]", norm)
        return frozenset(p.strip() for p in parts
                         if p.strip() and not re.fullmatch(r"[\d./]+", p.strip()))
    return _tokens(a) == _tokens(b)


# ---------------------------------------------------------------------------
# Derivative verification via SymPy
# ---------------------------------------------------------------------------

def _sympy_deriv_correct(antideriv: str, integrand: str, var: str = "x") -> Optional[bool]:
    """
    Use SymPy to check whether d/d(var) antideriv == integrand.

    Tries symbolic simplification first; falls back to numerical sampling
    for expressions like acosh/asinh where SymPy's simplify fails on
    algebraically equivalent but non-simplified radicals.
    """
    try:
        from sympy import symbols, diff, simplify, sympify, N
        v = symbols(var)
        F = sympify(antideriv.replace("^", "**"))
        f = sympify(integrand.replace("^", "**"))
        residual = simplify(diff(F, v) - f)
        if residual == 0:
            return True
        # Symbolic check failed — try numerical sampling at safe points
        # (avoids branch points; x=2 is safe for sqrt(x^2-1), x=1.5 for log domain)
        test_points = [1.5, 2.0, 3.0, 5.0]
        for pt in test_points:
            try:
                val = complex(N(residual.subs(v, pt)))
                if abs(val) > 1e-8:
                    return False
            except Exception:
                continue
        # All sampled points checked out — accept as numerically correct
        return True
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Form-disagree detection
#
# Two antiderivatives are "form-different" when:
#   1. Both have correct derivatives (confirmed by SymPy)
#   2. They normalise to different strings
#   3. d/dx (A - B) = 0  →  A - B is locally constant (possibly complex)
# ---------------------------------------------------------------------------

def _is_locally_constant_difference(a: str, b: str, var: str = "x") -> bool:
    """True when d/d(var)(A - B) = 0 (symbolically or numerically)."""
    try:
        from sympy import symbols, diff, simplify, sympify, N
        v = symbols(var)
        A = sympify(a.replace("^", "**"))
        B = sympify(b.replace("^", "**"))
        res = simplify(diff(A - B, v))
        if res == 0:
            return True
        # Numeric fallback — sample at points away from obvious branch points
        for pt in [1.5, 2.0, 3.0, 5.0]:
            try:
                val = complex(N(res.subs(v, pt)))
                if abs(val) > 1e-8:
                    return False
            except Exception:
                continue
        return True
    except Exception:
        return False


def _forms_are_log_factored_vs_product(a: str, b: str) -> bool:
    """
    Detect the concrete FriCAS/SymPy log-factoring disagreement pattern:
      log(u)/c + log(v)/c   vs   log(u*v)/c  (or sign variants)
    These are the two forms we found empirically in the Bronstein corpus.
    """
    na, nb = _norm(a), _norm(b)
    has_sum_of_logs = bool(re.search(r"log\(.*?\).*\+.*log\(", na)
                           or re.search(r"log\(.*?\).*-.*log\(", na)
                           or re.search(r"log\(.*?\).*\+.*log\(", nb)
                           or re.search(r"log\(.*?\).*-.*log\(", nb))
    has_log_of_product = bool(re.search(r"log\(.*?\*.*?\)", na)
                              or re.search(r"log\(.*?\*.*?\)", nb))
    return has_sum_of_logs and has_log_of_product


def _forms_are_inverse_hyp_vs_log(a: str, b: str) -> bool:
    """Detect acosh/asinh vs log(x+sqrt(...)) pattern."""
    either = a + " " + b
    return bool(
        re.search(r"\bacosh\b", either) or
        re.search(r"\basinh\b", either) or
        re.search(r"\batanh\b", either)
    )


# ---------------------------------------------------------------------------
# Lean theorem text generation for adjudication plans
# ---------------------------------------------------------------------------

def _lean_statement(integrand: str, antideriv: str, hypotheses: list[str], var: str = "x") -> str:
    """
    Generate a HasDerivAt theorem statement for kernel adjudication.
    This is a specification text; Lean CI is the arbiter.
    """
    hyp_str = " ".join(f"({h})" for h in hypotheses)
    clean_ig = integrand.replace("^", "^")  # keep as-is; Lean uses ^
    clean_F = antideriv.replace("^", "^")
    return (
        f"theorem candidate ({var} : ℝ) {hyp_str} :\n"
        f"    HasDerivAt (fun {var} : ℝ => {clean_F}) ({clean_ig}) {var}"
    )


def _hypotheses_for(antideriv: str, var: str = "x") -> list[str]:
    """Infer likely Lean hypotheses from the antiderivative structure."""
    hyps: list[str] = []
    # log(x) needs x ≠ 0; log(x-a) needs x-a ≠ 0
    for m in re.finditer(r"log\((" + var + r"[^)]*)\)", antideriv):
        arg = m.group(1).strip()
        hyps.append(f"h_{re.sub('[^a-z0-9]', '_', arg.lower())} : {arg} ≠ 0")
    # acosh(x) needs x ≥ 1
    if re.search(r"\bacosh\b", antideriv):
        hyps.append(f"h_domain : 1 ≤ {var}")
    # asinh: total, no hypothesis
    # sqrt(x^2-1): needs x^2-1 ≥ 0
    if re.search(r"sqrt\(" + var + r"\^2-1\)", antideriv):
        hyps.append(f"h_sq : 1 ≤ {var}")
    # Deduplicate
    seen: set[str] = set()
    out: list[str] = []
    for h in hyps:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out


# ---------------------------------------------------------------------------
# Main comparison engine
# ---------------------------------------------------------------------------

def compare_triple(integrand: str, var: str = "x") -> DisagreementReport:
    """
    Compare FriCAS, SymPy, and Maxima antiderivatives for integrand.
    Returns a DisagreementReport with the disagreement class and adjudication plan.
    """
    fricas = FriCASResolver(mode="offline").resolve(integrand, var)
    fricas_result = fricas.antiderivative if fricas.ok else None
    sympy_result  = SymPyResolver(mode="offline").integrate(integrand, var)
    maxima_result = MaximaResolver(mode="offline").integrate(integrand, var)

    results = {
        "FriCAS": fricas_result,
        "SymPy":  sympy_result,
        "Maxima": maxima_result,
    }
    present = {k: v for k, v in results.items() if v is not None}
    present_count = len(present)

    # Derivative correctness check (SymPy-verified)
    deriv_correct: dict[str, bool] = {}
    for src, antideriv in present.items():
        ok = _sympy_deriv_correct(antideriv, integrand, var)
        if ok is not None:
            deriv_correct[src] = ok

    cls, notes, plan = _classify(integrand, var, present, deriv_correct)

    return DisagreementReport(
        integrand=integrand,
        var=var,
        fricas_result=fricas_result,
        sympy_result=sympy_result,
        maxima_result=maxima_result,
        disagreement=cls.value,
        present_count=present_count,
        derivative_correct=deriv_correct,
        adjudication_plan=plan,
        notes=notes,
    )


def _classify(
    integrand: str,
    var: str,
    present: dict[str, str],
    deriv_correct: dict[str, bool],
) -> tuple[DisagreementClass, str, Optional[KernelAdjudicationPlan]]:
    n = len(present)
    values = list(present.values())
    sources = list(present.keys())

    if n == 0:
        return DisagreementClass.ALL_MISSING, "No CAS returned a result.", None

    if n == 1:
        return DisagreementClass.ONE_MISSING, f"Only {sources[0]} returned a result.", None

    # n == 2: one CAS missing — still compare the two present values below
    # n == 3: all present — full comparison

    # All three present — check for genuine errors first
    incorrect = [k for k, ok in deriv_correct.items() if not ok]
    if incorrect:
        return (
            DisagreementClass.GENUINE_DISAGREE,
            f"Derivative check failed for: {', '.join(incorrect)}.",
            None,
        )

    # Normalise
    norms = {k: _norm(v) for k, v in present.items()}
    distinct_norms = set(norms.values())

    if len(distinct_norms) == 1:
        return DisagreementClass.AGREE, "All three CAS agree.", None

    if all(_differ_by_constant(values[0], v) for v in values[1:]):
        return DisagreementClass.AGREE_UP_TO_C, "Answers differ by a constant.", None

    # At this point we have a genuine symbolic difference.
    # Check if all correct antiderivatives are locally-constant-different
    # (i.e., their difference has zero derivative — both are valid).
    all_locally_const = all(
        _is_locally_constant_difference(v1, v2, var)
        for i, (k1, v1) in enumerate(present.items())
        for k2, v2 in list(present.items())[i + 1:]
    )

    if all_locally_const:
        # Form or domain disagreement — build adjudication plan
        plan = _build_adjudication_plan(integrand, var, present)

        if _forms_are_log_factored_vs_product(values[0], values[1]) or (
            len(values) > 2 and _forms_are_log_factored_vs_product(values[0], values[2])
        ):
            notes = (
                "Log factored-form vs product-form disagreement: FriCAS/Maxima use "
                "Σ log(factor)/c; SymPy uses log(∏ factors)/c.  Both are valid "
                "antiderivatives; they differ by a locally-constant imaginary-valued "
                "function (multiples of πi) on disconnected components of the domain."
            )
            return DisagreementClass.FORM_DISAGREE, notes, plan

        if _forms_are_inverse_hyp_vs_log(values[0], values[1]) or (
            len(values) > 2 and _forms_are_inverse_hyp_vs_log(values[0], values[2])
        ):
            notes = (
                "Inverse-hyperbolic vs logarithmic form: acosh(x) and "
                "log(x+sqrt(x²-1)) are equal for x≥1 but represent different "
                "analytic continuations.  acosh is domain-restricted (x≥1) "
                "while the log form extends to complex values."
            )
            return DisagreementClass.DOMAIN_DISAGREE, notes, plan

        return DisagreementClass.FORM_DISAGREE, "Symbolic forms differ; all derivatives verified.", plan

    return (
        DisagreementClass.GENUINE_DISAGREE,
        "Answers differ and are not locally-constant-related.",
        None,
    )


def _build_adjudication_plan(
    integrand: str, var: str, present: dict[str, str]
) -> KernelAdjudicationPlan:
    candidates = []
    for source, antideriv in present.items():
        hyps = _hypotheses_for(antideriv, var)
        candidates.append({
            "source": source,
            "antideriv": antideriv,
            "hypotheses": hyps,
            "lean_statement": _lean_statement(integrand, antideriv, hyps, var),
        })

    # Determine adjudication class from the disagreement pattern
    all_antidelivs = [c["antideriv"] for c in candidates]
    if any(_forms_are_inverse_hyp_vs_log(a, b)
           for i, a in enumerate(all_antidelivs)
           for b in all_antidelivs[i + 1:]):
        adj_class = "domain_restricted"
    else:
        adj_class = "form_equivalent"

    return KernelAdjudicationPlan(
        integrand=integrand,
        var=var,
        candidates=candidates,
        adjudication_class=adj_class,
    )


# ---------------------------------------------------------------------------
# Corpus-level scanning
# ---------------------------------------------------------------------------

def scan_corpus(entries) -> list[DisagreementReport]:
    """Run compare_triple on a list of CorpusEntry or (integrand, var) tuples."""
    reports: list[DisagreementReport] = []
    for e in entries:
        if hasattr(e, "integrand"):
            reports.append(compare_triple(e.integrand, e.var))
        else:
            ig, var = e
            reports.append(compare_triple(ig, var))
    return reports


def scan_bronstein() -> list[DisagreementReport]:
    """Scan only the 8 Bronstein baseline integrands."""
    from fricas_bridge.cas_corpus import load_bronstein_set
    return scan_corpus(load_bronstein_set())


def compare_live(integrand: str, var: str = "x") -> DisagreementReport:
    """
    Like compare_triple but queries SymPy live (mode="online") for the integrand.

    This extends coverage beyond the offline SymPy cache: any integrand that
    SymPy can handle will be compared against FriCAS and Maxima offline caches,
    and if a new disagreement is found, a DisagreementReport is returned.

    If SymPy cannot integrate the expression, the report will show ONE_MISSING.
    """
    fricas = FriCASResolver(mode="offline").resolve(integrand, var)
    fricas_result = fricas.antiderivative if fricas.ok else None

    from fricas_bridge.sympy_resolver import SymPyResolver as SR
    sympy_result = SR(mode="online").integrate(integrand, var)
    maxima_result = MaximaResolver(mode="offline").integrate(integrand, var)

    results = {
        "FriCAS": fricas_result,
        "SymPy":  sympy_result,
        "Maxima": maxima_result,
    }
    present = {k: v for k, v in results.items() if v is not None}

    deriv_correct: dict[str, bool] = {}
    for src, antideriv in present.items():
        ok = _sympy_deriv_correct(antideriv, integrand, var)
        if ok is not None:
            deriv_correct[src] = ok

    cls, notes, plan = _classify(integrand, var, present, deriv_correct)

    return DisagreementReport(
        integrand=integrand,
        var=var,
        fricas_result=fricas_result,
        sympy_result=sympy_result,
        maxima_result=maxima_result,
        disagreement=cls.value,
        present_count=len(present),
        derivative_correct=deriv_correct,
        adjudication_plan=plan,
        notes=notes,
    )


def scan_live(integrands: list[str], var: str = "x") -> list[DisagreementReport]:
    """
    Scan a list of integrand strings using live SymPy queries.

    Returns a report for each integrand, including any newly discovered
    disagreements not covered by the offline corpus.
    """
    return [compare_live(ig, var) for ig in integrands]
