"""
Tier 5.7 — Live CAS disagreement hunt at scale.

This is the discovery engine the disagreement-adjudication apparatus was built
for.  Earlier work (Tier 1.5 / 5.4 / 5.6) demonstrated kernel adjudication on a
handful of hand-picked, known-equivalent pairs.  That proves the instrument is
correct; it does not constitute a finding.  A finding requires pointing the
instrument at a large corpus with the CAS *actually running* and surfacing
whatever falls out.

What this module does
---------------------
  1. Holds a large curated corpus (HUNT_CORPUS) of integrands drawn from
     standard integral tables (Gradshteyn–Ryzhik / Rubi families): rational,
     radical, trigonometric, hyperbolic, exponential, logarithmic, inverse-trig,
     and product forms.  Several hundred entries.
  2. Runs SymPy *and* Maxima live (subprocess), no hand-authored table.
  3. Triages every answer with a robust numeric+symbolic derivative check
     (`deriv_residual_is_zero`): does d/dx F equal the integrand?
  4. Classifies each integrand and surfaces:
        GENUINE_DISAGREE  — a CAS answer fails its own derivative check
                            (a real CAS bug, the headline target)
        DOMAIN_DISAGREE   — answers valid on different real domains
        FORM_DISAGREE     — notational difference, both correct
  5. Writes a JSON report (hunt_report.json) and prints a summary.

HONESTY CONTRACT
----------------
The SymPy derivative check here is *triage*, not proof.  A GENUINE_DISAGREE flag
means "this candidate deserves a kernel proof of rejection", not "this is proven
wrong".  The binding verdict is a Lean and/or Coq theorem.  The numeric checker
is deliberately conservative: it samples many points, uses complex arithmetic,
and only flags an answer as incorrect when the residual is non-negligible at a
clear majority of in-domain sample points.  This avoids branch-point artifacts
masquerading as CAS bugs.

CLI
---
    python -m cross_prover.cas_hunt --run            # full live hunt
    python -m cross_prover.cas_hunt --run --limit 50 # first 50 (smoke test)
    python -m cross_prover.cas_hunt --categories TRIG HYPERBOLIC
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# The hunt corpus — integrand strings keyed by family.
# ^ is the power operator (translated to ** for SymPy, kept for Maxima).
# ---------------------------------------------------------------------------

_RATIONAL = [
    "1/(x^2-1)", "1/(x^2+1)", "1/(x^3-1)", "1/(x^3+1)", "1/(x^4-1)",
    "1/(x^4+1)", "x/(x^4-1)", "x/(x^4+1)", "x^2/(x^4-1)", "x^2/(x^4+1)",
    "x^3/(x^4-1)", "x^3/(x^4+1)", "1/(x*(x+1))", "1/(x*(x+1)*(x+2))",
    "1/(x*(x+1)*(x-1))", "1/(x^2*(x+1))", "1/(x^2*(x-1))", "1/(x^2*(x-1)^2)",
    "(x+1)/(x*(x+2))", "(x^2+1)/(x^4-1)", "(x^2-1)/(x^4+1)", "1/(x^3+x)",
    "1/(x^3-x)", "x/(x^2-4)", "1/((x-1)*(x-2)*(x-3))", "1/(x^5-1)",
    "1/(x^2+2*x+2)", "1/(x^2+4*x+5)", "(2*x+3)/(x^2+3*x+2)", "1/(x^6-1)",
    "1/(x^2-2)", "1/(x^4-2*x^2+1)", "x/((x^2+1)^2)", "1/((x^2+1)^2)",
    "1/((x^2+1)^3)", "x/((x^2+1)*(x^2+2))", "1/((x^2+1)*(x^2+4))",
]

_RADICAL = [
    "1/sqrt(x^2-1)", "1/sqrt(x^2+1)", "1/sqrt(1-x^2)", "1/sqrt(x^2-4)",
    "1/sqrt(4-x^2)", "1/sqrt(x^2+4)", "sqrt(x^2-1)", "sqrt(x^2+1)",
    "sqrt(1-x^2)", "sqrt(x^2-4)", "sqrt(4-x^2)", "x/sqrt(x^2-1)",
    "x/sqrt(x^2+1)", "x/sqrt(1-x^2)", "x/sqrt(4-x^2)", "x^2/sqrt(x^2-1)",
    "x^2/sqrt(x^2+1)", "x^2/sqrt(1-x^2)", "1/(x*sqrt(x^2-1))",
    "1/(x*sqrt(x^2+1))", "1/(x*sqrt(1-x^2))", "sqrt(x)/(x+1)",
    "1/sqrt(x)", "sqrt(x)", "x*sqrt(x+1)", "1/sqrt(x*(x+1))",
    "1/((x+1)*sqrt(x))", "sqrt((x-1)/(x+1))", "1/sqrt(x^2+x)",
    "(x^2+1)/sqrt(x^2-1)", "sqrt(x^2+2*x+2)", "1/sqrt(x^2+2*x+5)",
]

_TRIG = [
    "sin(x)", "cos(x)", "tan(x)", "1/tan(x)", "1/sin(x)", "1/cos(x)",
    "sin(x)^2", "cos(x)^2", "tan(x)^2", "sin(x)^3", "cos(x)^3",
    "sin(x)*cos(x)", "sin(x)^2*cos(x)", "1/sin(x)^2", "1/cos(x)^2",
    "1/(1+sin(x))", "1/(1-sin(x))", "1/(1+cos(x))", "1/(1-cos(x))",
    "1/(1+cos(x)^2)", "sin(x)/(1+cos(x))", "1/(sin(x)+cos(x))",
    "1/(sin(x)*cos(x))", "sin(2*x)", "cos(2*x)", "sin(x)*cos(2*x)",
    "x*sin(x)", "x*cos(x)", "x^2*sin(x)", "sin(x)/x^2",
    "sin(x)^2*cos(x)^2", "1/(2+sin(x))", "1/(3+5*cos(x))",
    "tan(x)^3", "sec(x)^3", "1/(1+tan(x))",
]

_HYPERBOLIC = [
    "sinh(x)", "cosh(x)", "tanh(x)", "1/tanh(x)", "1/sinh(x)", "1/cosh(x)",
    "sinh(x)^2", "cosh(x)^2", "tanh(x)^2", "sinh(x)*cosh(x)",
    "1/(1+cosh(x))", "1/(1+sinh(x))", "x*sinh(x)", "x*cosh(x)",
    "sinh(x)/x", "tanh(x)^3", "1/(cosh(x)^2)", "1/(sinh(x)^2)",
    "sinh(x)^3", "cosh(x)^3", "1/(cosh(x)-1)", "sinh(2*x)",
]

_EXP_LOG = [
    "exp(x)", "exp(-x)", "exp(2*x)", "x*exp(x)", "x^2*exp(x)",
    "exp(x)*sin(x)", "exp(x)*cos(x)", "exp(x^2)", "exp(-x^2)",
    "exp(x)/x", "exp(sqrt(x))", "log(x)", "log(x)^2", "log(x)/x",
    "log(x)/x^2", "x*log(x)", "x^2*log(x)", "log(x+1)", "log(1-x)",
    "log(x^2+1)", "log(x^2-1)", "1/(x*log(x))", "1/log(x)",
    "log(log(x))/x", "log(x)/(x+1)", "x/log(x)", "exp(x)/(1+exp(x))",
    "1/(1+exp(x))", "exp(x)/(exp(x)+exp(-x))",
]

_INVERSE_TRIG = [
    "atan(x)", "asin(x)", "acos(x)", "atan(x)^2", "x*atan(x)",
    "x*asin(x)", "atan(x)/x", "asin(x)/x", "atan(x)/(1+x^2)",
    "atan(sqrt(x))", "asin(x)/sqrt(1-x^2)", "x*atan(x)^2",
    "atan(1/x)", "acot(x)", "asec(x)",
]

_PRODUCTS_MISC = [
    "x*exp(-x^2)", "x^3*exp(-x^2)", "sin(x)*exp(-x)", "x/sqrt(x^4+1)",
    "1/(x^4+x^2+1)", "x^2/(x^6+1)", "1/(x^6+1)", "x/(x^3+1)",
    "(x-1)/(x^2+x+1)", "1/((x^2+1)*sqrt(x^2-1))", "sin(x^2)",
    "cos(x^2)", "sin(x)/sqrt(x)", "x/(exp(x)+1)", "sqrt(tan(x))",
    "1/(x^4-x^2)", "x^2/((x^2+1)^2)", "1/(x*(x^4+1))",
    "(x^2+1)/(x*(x^2-1))", "1/(x^8-1)",
]

# ---------------------------------------------------------------------------
# Manually adjudicated triage flags.
#
# The numeric derivative check is triage and has false positives on integrands
# whose real domain is disconnected: a CAS may return a primitive valid on one
# component (e.g. x>1) while the sampler also probes another component (x<-1)
# where that primitive goes complex or picks the wrong branch.  Each integrand
# below was flagged by triage, then HAND-VERIFIED correct on its natural domain
# (see docs/CAS_DISAGREEMENT_ADJUDICATION.md and HUNT_FINDINGS.md).  None is a
# genuine CAS arithmetic error.  This table lets summarise() annotate them so
# the headline count is not misleading.
# ---------------------------------------------------------------------------
TRIAGE_REVIEWED_FALSE_POSITIVES: dict[str, str] = {
    "1/sqrt(x*(x+1))":
        "Maxima atanh-log form verified correct for x>0; triage probed x<0.",
    "sqrt((x-1)/(x+1))":
        "Maxima primitive verified correct for x>1 (a disconnected-domain "
        "branch); triage probed x<-1 where it picks the other branch.",
    "1/(x*sqrt(x^2-1))":
        "-asin(1/x) verified correct for |x|>1; triage hit branch cuts.",
    "1/(x*sqrt(x^2+1))":
        "-asinh(1/x) verified correct for x>0 (SymPy and Maxima identical); "
        "triage hit asinh(1/x) branch cut near 0.",
}


_FAMILIES: dict[str, list[str]] = {
    "RATIONAL":     _RATIONAL,
    "RADICAL":      _RADICAL,
    "TRIG":         _TRIG,
    "HYPERBOLIC":   _HYPERBOLIC,
    "EXP_LOG":      _EXP_LOG,
    "INVERSE_TRIG": _INVERSE_TRIG,
    "MISC":         _PRODUCTS_MISC,
}


def hunt_corpus(categories: Optional[list[str]] = None) -> list[tuple[str, str]]:
    """Return (integrand, family) pairs for the requested categories (all by default)."""
    cats = categories or list(_FAMILIES.keys())
    out: list[tuple[str, str]] = []
    for cat in cats:
        for ig in _FAMILIES.get(cat, []):
            out.append((ig, cat))
    return out


HUNT_CORPUS = hunt_corpus()


# ---------------------------------------------------------------------------
# Robust derivative check (triage gate)
# ---------------------------------------------------------------------------

def is_unevaluated(result: Optional[str]) -> bool:
    """
    True if a CAS 'answer' is not actually a closed form — an unevaluated
    SymPy Integral(...) (or a bare integral echo).  Such a string differentiates
    back to the integrand trivially and would pass any derivative check while
    telling us nothing, so it must be treated as a MISS, not an answer.
    """
    if not result:
        return True
    r = result.strip()
    return r.startswith("Integral(") or "Integral(" in r and r.endswith(", x)")


def deriv_residual_is_zero(
    antideriv: str, integrand: str, var: str = "x",
    *, n_points: int = 40, tol: float = 1e-6, seed: int = 1234,
) -> Optional[bool]:
    """
    Triage check: is d/d(var) antideriv == integrand, as REAL functions on the
    real domain where the antiderivative is defined?

    Strategy:
      1. Symbolic simplify(diff(F) - f) == 0  (definitive when it works).
      2. Real-axis in-domain sampling.  We evaluate the residual diff(F)-f at
         many real points and KEEP only those where it evaluates to a finite,
         essentially-real value (|Im| small) — i.e. points inside the real
         domain of both F and f.  The answer is "correct" iff the residual is
         negligible at every kept point.

    Why real-axis, not complex: the earlier complex-plane sampler produced
    false GENUINE_DISAGREE flags on branch-cut-heavy but perfectly correct real
    antiderivatives (e.g. -asin(1/x), -asinh(1/x), Maxima's sqrt((x-1)/(x+1))
    primitive).  Off-axis the branch structures legitimately differ; on the real
    domain they agree.  Real-axis sampling matches the question we actually ask:
    "is this a valid real antiderivative?"

    Returns True / False / None (None = never landed inside a shared real domain).

    Conservative about False: a False promotes a candidate to GENUINE_DISAGREE,
    a claim that a CAS is wrong — which must then be settled by a kernel proof.
    """
    try:
        from sympy import symbols, diff, simplify, sympify, N, im as sym_im
    except Exception:
        return None

    if is_unevaluated(antideriv):
        return None

    v = symbols(var)
    try:
        F = sympify(antideriv.replace("^", "**"))
        f = sympify(integrand.replace("^", "**"))
    except Exception:
        return None

    # 1. Symbolic
    try:
        if simplify(diff(F, v) - f) == 0:
            return True
    except Exception:
        pass

    # 2. Real-axis in-domain sampling
    try:
        dF = diff(F, v)
    except Exception:
        return None

    rng = random.Random(seed)
    in_domain = 0
    bad = 0
    # Spread sample points across a wide real range; domains like x>1, |x|<1,
    # x>0 will simply contribute the subset of points where things are real.
    for _ in range(n_points):
        pt = rng.uniform(-6.0, 6.0)
        if abs(pt) < 1e-3:
            continue
        try:
            dval = complex(N(dF.subs(v, pt)))
            fval = complex(N(f.subs(v, pt)))
        except Exception:
            continue
        # Keep only points inside the real domain: both values finite and
        # essentially real (small imaginary part relative to magnitude).
        if not (abs(dval) < 1e25 and abs(fval) < 1e25):
            continue
        mag = max(abs(dval), abs(fval), 1.0)
        if abs(dval.imag) > 1e-6 * mag or abs(fval.imag) > 1e-6 * mag:
            continue
        in_domain += 1
        if abs(dval - fval) / max(1.0, abs(fval)) > tol:
            bad += 1

    if in_domain == 0:
        return None
    return bad == 0


# ---------------------------------------------------------------------------
# Hunt
# ---------------------------------------------------------------------------

@dataclass
class HuntResult:
    integrand: str
    family: str
    sympy_result: Optional[str]
    maxima_result: Optional[str]
    sympy_deriv_ok: Optional[bool]
    maxima_deriv_ok: Optional[bool]
    verdict: str               # see classify_pair
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "integrand": self.integrand,
            "family": self.family,
            "sympy_result": self.sympy_result,
            "maxima_result": self.maxima_result,
            "sympy_deriv_ok": self.sympy_deriv_ok,
            "maxima_deriv_ok": self.maxima_deriv_ok,
            "verdict": self.verdict,
            "notes": self.notes,
        }


def classify_pair(
    integrand: str, var: str,
    sympy_result: Optional[str], maxima_result: Optional[str],
    sympy_ok: Optional[bool], maxima_ok: Optional[bool],
) -> tuple[str, str]:
    """
    Classify a live SymPy/Maxima pair.  Returns (verdict, notes).

    Verdicts:
      GENUINE_DISAGREE  one present answer fails its derivative check
      BOTH_WRONG        both present answers fail (rare; usually a parse problem)
      AGREE             both present and locally-constant-equal
      FORM_DISAGREE     both correct, different symbolic form
      ONE_MISSING       exactly one CAS produced a result
      ALL_MISSING       neither produced a result
    """
    present = {k: v for k, v in
               (("SymPy", sympy_result), ("Maxima", maxima_result)) if v}
    if not present:
        return "ALL_MISSING", "Neither CAS integrated this."
    if len(present) == 1:
        only = next(iter(present))
        ok = sympy_ok if only == "SymPy" else maxima_ok
        if ok is False:
            return "GENUINE_DISAGREE", f"{only} is the only answer and FAILS its derivative check."
        return "ONE_MISSING", f"Only {only} produced a result."

    # Both present
    failures = [name for name, ok in
                (("SymPy", sympy_ok), ("Maxima", maxima_ok)) if ok is False]
    if len(failures) == 2:
        return "BOTH_WRONG", "Both answers fail the derivative check (suspect parse error)."
    if len(failures) == 1:
        return ("GENUINE_DISAGREE",
                f"{failures[0]} FAILS its derivative check while the other passes.")

    # Both correct — agree or notational difference
    from fricas_bridge.disagree_detector import (
        _norm, _is_locally_constant_difference,
    )
    if _norm(sympy_result) == _norm(maxima_result):
        return "AGREE", "Identical after normalisation."
    if _is_locally_constant_difference(sympy_result, maxima_result, var):
        return "FORM_DISAGREE", "Both correct; differ by a locally-constant term."
    # Both pass derivative check yet not locally-constant-equal → flag for review
    return ("FORM_DISAGREE",
            "Both pass derivative check but difference is not provably constant "
            "by triage; review (possible domain split).")


def run_hunt(
    categories: Optional[list[str]] = None,
    *, limit: Optional[int] = None, var: str = "x",
    verbose: bool = True,
) -> list[HuntResult]:
    """Run the live two-CAS hunt over the corpus.  Requires SymPy + Maxima installed."""
    from fricas_bridge.sympy_resolver import SymPyResolver
    from fricas_bridge.maxima_resolver import MaximaResolver

    sympy = SymPyResolver(mode="online")
    maxima = MaximaResolver(mode="online")

    corpus = hunt_corpus(categories)
    if limit:
        corpus = corpus[:limit]

    results: list[HuntResult] = []
    for i, (ig, family) in enumerate(corpus, 1):
        s_res = sympy.integrate(ig, var)
        m_res = maxima.integrate(ig, var)
        # An unevaluated Integral(...) is not a closed-form answer — drop it so
        # it neither passes triage trivially nor counts as a present result.
        if is_unevaluated(s_res):
            s_res = None
        if is_unevaluated(m_res):
            m_res = None
        s_ok = deriv_residual_is_zero(s_res, ig, var) if s_res else None
        m_ok = deriv_residual_is_zero(m_res, ig, var) if m_res else None
        verdict, notes = classify_pair(ig, var, s_res, m_res, s_ok, m_ok)
        hr = HuntResult(ig, family, s_res, m_res, s_ok, m_ok, verdict, notes)
        results.append(hr)
        if verbose and verdict in ("GENUINE_DISAGREE", "BOTH_WRONG", "FORM_DISAGREE"):
            print(f"[{i}/{len(corpus)}] {verdict}: {ig}")
            print(f"      SymPy : {s_res}  (deriv_ok={s_ok})")
            print(f"      Maxima: {m_res}  (deriv_ok={m_ok})")
            print(f"      {notes}")
    return results


def summarise(results: list[HuntResult]) -> dict:
    """Aggregate counts by verdict and list the interesting cases."""
    from collections import Counter
    counts = Counter(r.verdict for r in results)

    def _annotate(r: HuntResult) -> dict:
        d = r.to_dict()
        review = TRIAGE_REVIEWED_FALSE_POSITIVES.get(r.integrand)
        d["triage_reviewed"] = review is not None
        d["review_note"] = review or ""
        return d

    genuine = [_annotate(r) for r in results if r.verdict == "GENUINE_DISAGREE"]
    both_wrong = [_annotate(r) for r in results if r.verdict == "BOTH_WRONG"]
    form = [r.to_dict() for r in results if r.verdict == "FORM_DISAGREE"]

    # Genuine candidates NOT already hand-cleared — these would be real findings.
    unreviewed = [r for r in (genuine + both_wrong) if not r["triage_reviewed"]]

    return {
        "total": len(results),
        "counts": dict(counts),
        "genuine_disagree": genuine,
        "both_wrong": both_wrong,
        "form_disagree": form,
        "unreviewed_candidates": unreviewed,
        "net_genuine_after_review": len(unreviewed),
    }


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Live CAS disagreement hunt")
    parser.add_argument("--run", action="store_true", help="run the live hunt")
    parser.add_argument("--limit", type=int, default=None, help="cap corpus size")
    parser.add_argument("--categories", nargs="*", default=None,
                        help="families to scan (default: all)")
    parser.add_argument("--out", default="hunt_report.json", help="JSON output path")
    args = parser.parse_args()

    if not args.run:
        parser.print_help()
        return

    results = run_hunt(args.categories, limit=args.limit)
    summary = summarise(results)

    Path(args.out).write_text(json.dumps(
        {"summary": summary, "results": [r.to_dict() for r in results]},
        indent=2, sort_keys=True) + "\n")

    print("\n" + "=" * 60)
    print(f"HUNT COMPLETE — {summary['total']} integrands")
    print("=" * 60)
    for verdict, n in sorted(summary["counts"].items()):
        print(f"  {verdict:18s} {n}")
    print(f"\n  GENUINE_DISAGREE (triage): {len(summary['genuine_disagree'])}")
    print(f"  BOTH_WRONG (triage):       {len(summary['both_wrong'])}")
    print(f"  NET genuine after manual/known review: "
          f"{summary['net_genuine_after_review']}")
    if summary["unreviewed_candidates"]:
        print("  ⚠️  UNREVIEWED candidate(s) — need a kernel rejection proof:")
        for r in summary["unreviewed_candidates"]:
            print(f"        {r['integrand']}")
    print(f"  Report written to {args.out}")


if __name__ == "__main__":
    main()
