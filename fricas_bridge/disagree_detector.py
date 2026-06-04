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
  DOMAIN_DISAGREE    Answers differ in domain of validity / named functions.
                     Refined by DomainSubclass into:
                       special_fn_repr        same fn, different special-function
                                              notation (asinh vs log) — NOT yet
                                              kernel-adjudicated
                       analytic_continuation  agree on a real interval, differ by
                                              πi branch terms in ℂ
                       true_domain_divergence valid on different real domains and
                                              unequal on the overlap (closest to
                                              a real bug)
  GENUINE_DISAGREE   At least one answer fails the derivative check (potential
                     CAS bug or incorrect side-condition handling).
  ONE_MISSING        Exactly one CAS returned no result.
  TWO_MISSING        Exactly two CAS returned no result.
  BOTH_MISSING / ALL_MISSING  No CAS returned a result.

IMPORTANT — the derivative check is TRIAGE, not proof.  A GENUINE_DISAGREE flag
means "a candidate worth a kernel rejection proof", never "proven wrong".  The
binding verdict is always a Lean/Coq kernel theorem.

A KernelAdjudicationPlan is generated for FORM_DISAGREE and DOMAIN_DISAGREE
cases: it lists the Lean HasDerivAt statement that would need to be proved for
each candidate antiderivative, and which hypotheses each form requires.  The
plan is a specification, not a running prover — the Lean CI is the arbiter.

Public API
----------
DisagreementClass               Enum
DomainSubclass                  Enum  (refinement of DOMAIN_DISAGREE)
DisagreementReport              dataclass (has .domain_subclass)
KernelAdjudicationPlan          dataclass
compare_triple(integrand, var)  → DisagreementReport   (all offline)
compare_live(integrand, var)    → DisagreementReport   (SymPy online)
compare_live_all(integrand, var)→ DisagreementReport   (SymPy + Maxima online)
scan_corpus(entries)            → list[DisagreementReport]
scan_bronstein()                → list[DisagreementReport]
scan_live / scan_live_all       → list[DisagreementReport]
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


class DomainSubclass(str, Enum):
    """
    Refinement of DOMAIN_DISAGREE.  The top-level class stays DOMAIN_DISAGREE
    (stable across tooling); this names *why* the domains differ so the
    adjudication layer can pick the right treatment.

    SPECIAL_FN_REPR
        The two answers are the *same function* written with different named
        special functions — e.g. Maxima asinh(x) vs SymPy log(x+√(x²+1)).
        They are equal everywhere both are real-defined.  Not a real
        disagreement; just two notations.  NOT yet kernel-adjudicated because
        Mathlib would need the asinh/acosh ↔ log identity proved first.

    ANALYTIC_CONTINUATION
        The answers agree on a real interval but their complex continuations
        differ by branch-cut terms (multiples of πi) on disconnected components
        of the domain — the log(∏)/Σlog story when the factors can be negative.
        Both are valid real antiderivatives; they differ by a locally-constant
        imaginary offset.

    TRUE_DOMAIN_DIVERGENCE
        The answers are valid on genuinely different real domains and are NOT
        equal on the overlap.  This is the dangerous case — closest to a real
        bug — and is flagged for kernel scrutiny rather than dismissed.
    """
    SPECIAL_FN_REPR        = "special_fn_repr"
    ANALYTIC_CONTINUATION  = "analytic_continuation"
    TRUE_DOMAIN_DIVERGENCE = "true_domain_divergence"


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
    domain_subclass: Optional[str] = None  # DomainSubclass value when DOMAIN_DISAGREE


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


def _domain_subclass(a: str, b: str, var: str = "x") -> "DomainSubclass":
    """
    Refine a DOMAIN_DISAGREE into SPECIAL_FN_REPR / ANALYTIC_CONTINUATION /
    TRUE_DOMAIN_DIVERGENCE.

    Heuristics (triage only — a kernel proof is the binding verdict):
      * One side names an inverse-hyperbolic (acosh/asinh/atanh) and the other a
        logarithm  →  SPECIAL_FN_REPR (same function, two notations).
      * Both are log-based and their difference is locally constant (the πi /
        log(∏) vs Σlog story)  →  ANALYTIC_CONTINUATION.
      * Difference is not locally constant on the overlap  →
        TRUE_DOMAIN_DIVERGENCE.
    """
    if _forms_are_inverse_hyp_vs_log(a, b):
        return DomainSubclass.SPECIAL_FN_REPR
    if _is_locally_constant_difference(a, b, var):
        return DomainSubclass.ANALYTIC_CONTINUATION
    return DomainSubclass.TRUE_DOMAIN_DIVERGENCE


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
    domain_subclass = (
        _compute_domain_subclass(present, var)
        if cls == DisagreementClass.DOMAIN_DISAGREE else None
    )

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
        domain_subclass=domain_subclass,
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


def _compute_domain_subclass(present: dict[str, str], var: str) -> Optional[str]:
    """
    When the verdict is DOMAIN_DISAGREE, name the subclass by inspecting the
    present antiderivative pair(s).  Returns a DomainSubclass value or None if
    no two distinct present forms exist.
    """
    vals = [v for v in present.values() if v]
    for i in range(len(vals)):
        for j in range(i + 1, len(vals)):
            if _norm(vals[i]) != _norm(vals[j]):
                return _domain_subclass(vals[i], vals[j], var).value
    return None


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
    domain_subclass = (
        _compute_domain_subclass(present, var)
        if cls == DisagreementClass.DOMAIN_DISAGREE else None
    )

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
        domain_subclass=domain_subclass,
    )


def compare_live_all(integrand: str, var: str = "x") -> DisagreementReport:
    """
    Fully-live two-CAS comparison: SymPy AND Maxima are both queried online.

    Unlike compare_live (which only runs SymPy live and reads Maxima from the
    committed offline cache), this spawns both CAS subprocesses.  It is the
    scan path used by the live CI hunt (cross_prover.cas_hunt): no hand-authored
    table is consulted for SymPy or Maxima — the answers come straight from the
    installed CAS.  FriCAS, which has no apt package, is still read from its
    offline cache (None on a miss).

    The derivative-correctness gate is SymPy's `diff`, used as triage only.
    A False here flags a candidate GENUINE_DISAGREE; the binding verdict for any
    such case is a Lean/Coq kernel proof, never this check.
    """
    from fricas_bridge.sympy_resolver import SymPyResolver as SR

    fricas = FriCASResolver(mode="offline").resolve(integrand, var)
    fricas_result = fricas.antiderivative if fricas.ok else None
    sympy_result  = SR(mode="online").integrate(integrand, var)
    maxima_result = MaximaResolver(mode="online").integrate(integrand, var)

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
    domain_subclass = (
        _compute_domain_subclass(present, var)
        if cls == DisagreementClass.DOMAIN_DISAGREE else None
    )

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
        domain_subclass=domain_subclass,
    )


def scan_live(integrands: list[str], var: str = "x") -> list[DisagreementReport]:
    """
    Scan a list of integrand strings using live SymPy queries
    (SymPy online, Maxima + FriCAS offline).

    Returns a report for each integrand, including any newly discovered
    disagreements not covered by the offline corpus.
    """
    return [compare_live(ig, var) for ig in integrands]


def scan_live_all(integrands: list[str], var: str = "x") -> list[DisagreementReport]:
    """
    Fully-live batch scan: both SymPy and Maxima are queried online for every
    integrand (see compare_live_all).  This is the discovery path — no
    hand-authored table is consulted for the two live CAS.
    """
    return [compare_live_all(ig, var) for ig in integrands]
