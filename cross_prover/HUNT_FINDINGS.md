# Live CAS Hunt — Findings

This records the first run of the disagreement-adjudication apparatus **at
scale, with two CAS actually running** (not a hand-authored table). It is the
step that converts the instrument from "demonstrated on safe cases" to "pointed
at the corpus and hunting."

## Setup

| | |
|---|---|
| Engine | `cross_prover/cas_hunt.py` |
| Live CAS #1 | SymPy 1.14.0 (`pip install sympy`) |
| Live CAS #2 | Maxima 5.46.0 (`apt-get install maxima`) |
| FriCAS | offline cache only (no apt package) |
| Corpus | 191 integrands across 7 families (rational, radical, trig, hyperbolic, exp/log, inverse-trig, misc) |
| Triage gate | `deriv_residual_is_zero` — symbolic, then real-axis in-domain sampling |
| Binding gate | Lean / Coq kernel theorem (none required this run — see result) |

## Result

```
AGREE              ~47
FORM_DISAGREE      ~134     (notational, both CAS correct)
ONE_MISSING          3
ALL_MISSING          3
GENUINE_DISAGREE     2      (triage flags)
BOTH_WRONG           2      (triage flags)
------------------------------------------------------------
NET genuine CAS errors after review:  0
```

**Across 191 integrands, the two CAS never genuinely disagreed.** Every apparent
disagreement is notational (different but equivalent symbolic forms) or a
domain-restricted primitive. This is the null result the pivot anticipated, and
it is a result: *on this corpus, SymPy and Maxima never produce contradictory
antiderivatives; all differences are notation or branch/domain choices.*

(Counts vary by ±1–2 between runs because a couple of hard integrands
occasionally hit Maxima's timeout; the qualitative result — zero net genuine
errors — is stable.)

## The four triage flags, hand-adjudicated

The numeric derivative check is **triage, not proof**, and it has false
positives on integrands whose real domain is *disconnected*: a CAS returns a
primitive valid on one component while the sampler also probes another component
where that primitive takes the other branch. All four flagged candidates were
verified correct on their natural domain (reproduce with the snippet in
`cas_hunt.py`'s `TRIAGE_REVIEWED_FALSE_POSITIVES`):

| Integrand | Flagged form | Verified correct on | Why triage tripped |
|---|---|---|---|
| `1/sqrt(x*(x+1))` | Maxima atanh-log form | `x>0` | sampler probed `x<0` |
| `sqrt((x-1)/(x+1))` | Maxima `√(x²−1)−log(2√(x²−1)+2x)` | `x>1` | other real component `x<−1` is a different branch |
| `1/(x*sqrt(x^2-1))` | `−asin(1/x)` | `|x|>1` | branch cuts near `|x|=1` |
| `1/(x*sqrt(x^2+1))` | `−asinh(1/x)` (SymPy and Maxima identical!) | `x>0` | `asinh(1/x)` branch cut near `0` |

The last is the clearest tell that these are triage artifacts: SymPy and Maxima
returned the **identical** expression `−asinh(1/x)`, yet triage flagged both —
two identical correct answers cannot both be wrong.

## Two real defects the hunt exposed — in the instrument, not the CAS

1. **Maxima multi-line output parser truncation.** The original
   `MaximaResolver._live_integrate` kept only the last wrapped continuation line
   of Maxima's output, silently truncating multi-term answers like
   `∫1/(x⁴+1)`. This manufactured **6 false `GENUINE_DISAGREE`** in the first
   run. Fixed by setting `linel: 1000000` (disable wrapping) + `string()` +
   `<<< … >>>` sentinels. The false count dropped 7 → 1 immediately.

2. **Complex-axis derivative sampling.** The first checker sampled off the real
   axis to "dodge branch cuts," but that is exactly where correct real
   primitives legitimately diverge (the branch structures differ off-axis).
   Replaced with **real-axis in-domain sampling**, which matches the question we
   actually ask: "is this a valid *real* antiderivative?"

Both fixes are committed. The hunt is reproducible:

```bash
python -m cross_prover.cas_hunt --run --out hunt_report.json
```

## What would change the headline

A `net_genuine_after_review > 0` — a triage flag that is **not** a known
domain/branch artifact and survives hand inspection — is a candidate CAS bug.
The committed plan for that case is a **kernel rejection proof in both Lean and
Coq**: two independent kernels rejecting the same CAS output is the
un-fakeable version of the finding. No such case has appeared yet.

## Honesty notes

- This is 191 integrands, not the full Rubi corpus (thousands). The engine
  scales; expanding the corpus is mechanical (add to `_FAMILIES`).
- FriCAS was not live (no apt package), so this run is genuinely *two*-CAS, not
  three. The FriCAS offline cache still participates where it has entries.
- The committed `data/hunt_report.json` is the raw triage output, annotated with
  `triage_reviewed` / `review_note` for the four hand-cleared candidates.
