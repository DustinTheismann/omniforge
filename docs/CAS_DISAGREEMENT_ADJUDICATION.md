# CAS Disagreement Adjudication

When two computer-algebra systems (CAS) integrate the same function and print
different answers, that difference can mean several very different things. This
page defines the vocabulary the project uses, says which cases are
**kernel-adjudicated** (proved in Lean), and — most importantly — states
exactly how much trust each layer earns.

> **Trust warning — read this first.**
> The SymPy derivative check is **triage, not proof.** When the apparatus says
> "this antiderivative is correct," that statement was produced by
> differentiating with SymPy and comparing — a fast filter that can be fooled by
> branch cuts, domain restrictions, and its own simplification limits. The
> **only** binding verdicts in this repository are **Lean** and **Coq** kernel
> theorems. A green derivative check promotes a case to "worth proving"; it
> never settles it. Anywhere this doc says "correct," read "passed triage unless
> a kernel theorem is cited."

---

## The pipeline

```
integrand ──> [SymPy] ─┐
          ──> [Maxima] ─┼─> normalise ─> derivative-check (TRIAGE)
          ──> [FriCAS] ─┘                        │
                                                 ▼
                                   classify ─> DisagreementClass
                                                 │
                              (form/domain disagreement)
                                                 ▼
                              Lean / Coq kernel theorem  (PROOF GATE)
                                                 ▼
                                   AdjudicationCertificate
```

- **SymPy** runs live (`mode="online"`) or from a committed cache.
- **Maxima** runs live via subprocess or from a committed cache.
- **FriCAS** has no apt package in CI, so it is read from its offline cache
  (`fricas_bridge/data/fricas_offline_cache.json`); a miss yields `None`.

---

## The four (plus refinements) statuses

The detector (`fricas_bridge/disagree_detector.py`) assigns each integrand a
`DisagreementClass`:

| Class | Meaning | Who's right? |
|---|---|---|
| `AGREE` | Identical after normalisation | everyone |
| `AGREE_UP_TO_C` | Differ only by an additive constant | everyone |
| `FORM_DISAGREE` | Both correct, different symbolic form (e.g. Σlog vs log∏) | everyone |
| `DOMAIN_DISAGREE` | Valid on different real domains / different named functions | see subclass |
| `GENUINE_DISAGREE` | At least one answer **fails** its derivative check | someone is wrong |
| `ONE_MISSING` / `TWO_MISSING` / `ALL_MISSING` | Fewer CAS returned a result | — |

### `DOMAIN_DISAGREE` is refined into three subclasses

`DOMAIN_DISAGREE` is a coarse bucket; the `domain_subclass` field
(`DomainSubclass`) says *why* the domains differ:

| Subclass | Meaning | Example | Kernel status |
|---|---|---|---|
| `special_fn_repr` | Same function, different named special function | Maxima `asinh(x)` vs SymPy `log(x+√(x²+1))` | **Not** kernel-adjudicated — would need the asinh/acosh ↔ log identity in Mathlib first |
| `analytic_continuation` | Agree on a real interval; complex continuations differ by πi branch terms | `log(∏)` vs `Σlog` on disconnected domains | partially (the real-domain equality is what `CasAdjudication.lean` proves) |
| `true_domain_divergence` | Valid on genuinely different real domains, **not** equal on the overlap | (none found yet) | flagged for scrutiny — closest to a real bug |

---

## Which cases are kernel-adjudicated

"Kernel-adjudicated" means a committed theorem in
`fricas_bridge/CasAdjudication.lean` is typechecked by the Lean kernel + Mathlib
in CI (the `lean.yml` workflow), with no `sorry`/`axiom` escape hatch (enforced
by the structural guard). As of this writing, **four** integrands are
kernel-adjudicated, all of class `FORM_DISAGREE`, all resolved by `Real.log_mul`:

| Integrand | FriCAS/Maxima form | SymPy form | Lean theorem |
|---|---|---|---|
| `(x+1)/(x*(x+2))` | `log(x)/2 + log(x+2)/2` | `log(x²+2x)/2` | `form_disagree_005_equivalent` |
| `1/(x*(x+1)*(x+2))` | `log(x)/2 − log(x+1) + log(x+2)/2` | `−log(x+1) + log(x²+2x)/2` | `form_disagree_009_equivalent` |
| `x/(x^4-1)` | `log(x−1)/4 + log(x+1)/4 − log(x²+1)/4` | `log(x²−1)/4 − log(x²+1)/4` | `form_disagree_x_over_x4m1_equivalent` |
| `1/(x*(x+1)*(x-1))` | `−log(x) + log(x−1)/2 + log(x+1)/2` | `−log(x) + log(x²−1)/2` | `form_disagree_recip_xpolesym_equivalent` |

Each kernel-adjudicated case carries an `AdjudicationCertificate`
(`cross_prover/adjudication_certificate.py`) with `is_kernel_adjudicated=True`
and a `lean_equivalence_lemma` field. A CI/test check
(`validate_kernel_adjudication_lemmas`) guarantees that **every** such
certificate names a theorem that actually exists in `CasAdjudication.lean` —
a certificate can never claim a proof that isn't there.

### What is NOT kernel-adjudicated

- **`special_fn_repr` cases** (`1/sqrt(x²±1)`, `sqrt(x²±1)`): both forms pass
  triage and are equal where defined, but no Lean theorem unifies `acosh`/`asinh`
  with the log form yet. The certificate records `DOMAIN_RESTRICTED` /
  `is_kernel_adjudicated=False`.
- **Any `GENUINE_DISAGREE`**: none has been found in the corpus to date. The
  enum value and handling code exist; the apparatus to catch a real CAS error is
  built and tested but has not fired. If a live scan surfaces one, the plan is to
  reject it with a Lean **and** a Coq theorem — two independent kernels.

---

## Honesty scorecard

| Claim | Status |
|---|---|
| The four `FORM_DISAGREE` equivalences are proved by the Lean kernel | ✅ true |
| Adjudication is **single-kernel** (Lean only; no Coq adjudication theorem yet) | ⚠️ acknowledged limitation |
| A CAS has been caught producing a **wrong** antiderivative | ❌ not yet — no `GENUINE_DISAGREE` found |
| `special_fn_repr` (acosh/asinh vs log) is kernel-proved equal | ❌ not yet — needs Mathlib identity |
| SymPy derivative check is a proof | ❌ it is triage only |
| Disagreements were **discovered** by scanning, not hand-authored | ⚠️ partially — see the live hunt (`cross_prover/cas_hunt.py`) |

---

## Running the hunt yourself

```bash
# Full live two-CAS scan (needs sympy + maxima installed)
python -m cross_prover.cas_hunt --run --out hunt_report.json

# Smoke test: first 40 integrands
python -m cross_prover.cas_hunt --run --limit 40

# One family
python -m cross_prover.cas_hunt --run --categories TRIG HYPERBOLIC
```

The hunt classifies each integrand and surfaces every `GENUINE_DISAGREE`,
`BOTH_WRONG`, and `FORM_DISAGREE`. A `GENUINE_DISAGREE` is a **candidate** CAS
bug — the next step for any such case is a kernel rejection proof, not a
press release.

---

## Files

| File | Role |
|---|---|
| `fricas_bridge/disagree_detector.py` | classification engine, `DisagreementClass`, `DomainSubclass` |
| `fricas_bridge/cas_corpus.py` | curated corpus with structured `expected` / `expected_subclass` |
| `fricas_bridge/sympy_resolver.py`, `maxima_resolver.py` | live + cached CAS resolvers |
| `cross_prover/cas_hunt.py` | live two-CAS hunt at scale |
| `cross_prover/adjudication_certificate.py` | certificate layer + lemma validator |
| `fricas_bridge/CasAdjudication.lean` | the kernel-checked equivalence theorems |
