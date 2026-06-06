# ProofForge Ω: A Unified, Evidence-Graded Foundry for Machine-Checked Verification of Generated Claims

**Draft — tools / system-demonstrator paper.**
Author: Dustin Theismann *(author line is a placeholder for the draft)*
Artifact: `github.com/DustinTheismann/omniforge` (v0.4.0), commit on `main` at time of writing.

> **Status of this document.** This is a working draft intended for a
> tools/demonstrator track (e.g. CICM or an ITP tool paper) or arXiv. Every
> empirical claim below is cross-referenced to a file or CI workflow in the
> artifact; numbers are those enforced by the repository's own guards. The
> bibliography (Appendix B) has been **verified against primary sources** (web
> check, June 2026): author lists, titles, venues, years, pages, and DOIs are
> as listed. What remains is editorial — final reference *formatting* in the
> chosen venue's style, and the author/affiliation line.

---

## Abstract

Modern producers — computer-algebra systems (CAS), SAT/SMT solvers, and large
language models — emit candidate mathematical and computational claims faster
than humans can check them. We present **ProofForge Ω**, a lane-based foundry
that treats verification, not generation, as the deliverable. Each claim is a
typed object carrying a sealed, hash-pinned reproducibility capsule and is
assigned an immutable **evidence class** on a fail-closed ladder (E0–E11) by a
deterministic grader; no rung is reachable without satisfying its gate. The
defensible thesis is **structural**: SAT refutation and symbolic-integration
verification are instances of *one* trust pattern — *untrusted producer +
formally-verified checker → graded, reproducible result* — and can be graded on
a single ladder. We instantiate the pattern in two working lanes (a
three-checker UNSAT pipeline whose trust anchor `cake_lpr` is proven correct in
HOL4; and a FriCAS→Lean/Coq integration lane reaching cross-prover verification
on caveat-free cases) and add an evidence class, **E9**, that grades by
*methodological diversity*: two formal kernel families proving the same fact by
two genuinely different methods. We demonstrate E9 on a Tseitin parity
contradiction — the textbook separator of algebraic and resolution proofs —
verified by GF(2) linear algebra in Lean 4 and by resolution refutation in
`cake_lpr`. Finally, we report an integrity mechanism that we believe is the
most transferable contribution: **structural guards** that make the grade a
*generated* function of what is actually wired into CI (`min(grader, wiring)`),
so a "Demonstrated" grade cannot be asserted ahead of its executed evidence. We
are explicit about scope: this is a research-grade proof-of-concept (33
kernel-checked theorems; a 191-integrand CAS hunt with a null result; two E9
instances), not a validated-at-scale library.

---

## 1. Introduction

The cost structure of producing computational knowledge has inverted. A CAS
returns an antiderivative in milliseconds; a SAT solver decides industrial
instances; an LLM drafts a proof sketch on request. What none of them returns is
a *warranted reason to believe the output* that a third party can check
mechanically and reproduce. The bottleneck has moved from generation to
**verification, reproducibility, and falsification**.

ProofForge Ω is built around a single observation: many of these verification
problems share a shape. A *producer* we do not trust (CaDiCaL, FriCAS, an LLM)
emits a candidate; a *checker* whose soundness is itself formally established (a
proof-assistant kernel; a SAT proof-checker verified in HOL4) either accepts a
certificate or does not; and the result is recorded with enough provenance to
re-run. The contribution of this paper is not any single checker — those are
prior art — but (i) the **unification**: treating SAT and symbolic integration
as instances of one graded pattern; (ii) an **evidence class that grades by
method diversity** (E9); and (iii) an **integrity discipline** that prevents the
grade from outrunning the executed evidence.

We state the limitations up front, because the project's own history is a case
study in claims preceding their verification (§6): the system is small (§9), and
the strongest honest statement is that the *pattern* is demonstrated, not that it
is validated at scale.

### Contributions

1. A **fail-closed evidence ladder** (E0–E11, plus an `EX_REFUTED` override) with
   a deterministic grader, and a protocol spine (claim/runpack/evidence/
   obligation) that makes every claim a reproducible, hash-sealed object (§3–4).
2. Two working **lanes** instantiating the trust pattern in unrelated domains: a
   three-checker UNSAT lane (HOL4-verified anchor) and a FriCAS→Lean/Coq
   integration lane with cross-prover verification (§5).
3. **E9 (multi-method)** and a non-toy demonstration: a Tseitin parity
   contradiction proved by GF(2) linear algebra (Lean) and by resolution
   (`cake_lpr`) — two genuinely different methods, kept cheap by a
   bounded-treewidth instance (§5.3).
4. **Structural guards** that generate the headline grade as `min(grader,
   wiring)` and fail CI if the committed status diverges — making it impossible
   to record a demonstration whose anchors are not actually wired into CI (§6).
5. An **honest null result**: a live two-CAS hunt over 191 integrands that found
   no genuine CAS error, with apparent positives traced to bugs in our own
   instrument and corrected (§7).

---

## 2. Background and related work

(Numbers in brackets key to Appendix B.)

**LCF-style kernels and the skeptic approach.** Verifying CAS output against a
proof assistant is a well-trodden idea. Harrison and Théry's "skeptic's
approach" combined HOL with Maple, having the untrusted CAS produce a result the
trusted kernel re-derives [1]. Our integration lane is an instance of exactly
this pattern; we claim no novelty for the technique itself, only for embedding it
in a graded, multi-lane foundry.

**CAS ↔ prover bridges.** OpenMath [2] standardizes moving mathematical objects
between systems. Our FriCAS→Lean translation is a narrow, special-purpose
instance, not a general bridge.

**Formally verified proof checking.** The trust anchor of our SAT lane,
`cake_lpr`, is a CakeML [3] program whose LRAT-checking logic is proven correct
in HOL4 [4]. The unverified checkers `drat-trim` [5] and `lrat-trim` provide
corroboration; the LRAT format itself was introduced for exactly this
solver-emits-proof / checker-verifies-proof discipline [6]. We use these as-is.

**Certificate-checked optimization.** VIPR [7] verifies MILP results via
certificates; we cite it as the model our (not yet built) MILP lane would
follow, and as evidence the trust pattern generalizes beyond our two lanes.

**Proof complexity.** Our E9 demonstration rests on a classical fact: Tseitin
formulas [8] separate algebraic (Gaussian elimination over GF(2)) from
resolution reasoning — exponentially so on expander graphs [9, 10]. This is
*why* the two methods we combine are genuinely different rather than notational
variants; we exploit a bounded-treewidth instance to keep both proofs cheap.

**What is new here.** Not the checkers, not cross-prover verification, not the
skeptic approach. New is the *unified evidence-graded foundry* that treats these
as one pattern, the *method-diversity evidence class* (E9), and the *generated,
CI-enforced grade* that closes the gap between a recorded grade and its executed
evidence (§6). These claims are deliberately narrow.

---

## 3. The evidence ladder

Every claim carries exactly one `evidence_class`. The ladder is **fail-closed**:
a rung is granted only if its gate condition holds, and `grade()` returns the
highest rung reached. `EX_REFUTED` overrides everything.

| Rung | Name | Gate (abbreviated) |
|---|---|---|
| E0 | RAW_CLAIM | baseline |
| E1 | SOURCED | `source.kind` + `source.name` present |
| E2 | PARSED | schema-valid |
| E3 | EXECUTABLE | ≥1 obligation run |
| E4 | REPRODUCED | reproduction-family checker passed |
| E5 | NUMERICALLY_SUPPORTED | numeric checker passed |
| E6 | SYMBOLICALLY_SUPPORTED | CAS / SAT / SMT checker passed |
| E7 | FORMALLY_VERIFIED | ≥1 formal kernel reports `formal_verified=True` **and** a `formal_target` is `proved` |
| E8 | CROSS_VERIFIED | ≥2 **independent formal kernel families** each `formal_verified=True` |
| E9 | MULTI_METHOD | E8 **and** ≥2 **distinct methods** across those families |
| E10 | ADVERSARIALLY_HARDENED | falsifier ran, found no counterexample, no disagreement flag *(not implemented)* |
| E11 | FIELD_VALIDATED | external reproduction *(reserved)* |
| EX | REFUTED | formal refutation / counterexample (overrides all) |

The decisive design choice is at E7: `formal_verified` may be set **only** by a
proof-kernel's acceptance, never by a producer's assertion. CAS, SMT, and SAT
*solver* outputs raise a claim only to E6 (symbolic support); they are
corroboration, not proof. The formal kernel **families** are distinguished so
that Lean + Coq counts as two independent anchors (→ E8) while Lean alone, or
`cake_lpr` alone, counts as one (→ E7). E9 additionally requires the two
families to use *different methods* (e.g. differentiation vs SAT refutation;
algebraic identity vs resolution), so that a systematic error in one method's
encoding is caught by the orthogonal method. The grader is ~200 lines of pure
Python (`protocols/evidence_protocol/grader.py`) with no I/O, so grading is
deterministic and unit-testable.

---

## 4. System architecture: the protocol spine

Four interlocking protocols (`protocols/`) make a claim a self-describing,
reproducible object.

- **Claim** — the universal evidence object (JSON Schema draft 2020-12 +
  typed Python). Fields include `source`, `inputs`/`outputs`, `formal_targets`,
  `obligations`, `checker_results`, `flags`, and the graded `evidence_class`.
- **Runpack** — a reproducibility capsule: pinned tool versions, every command
  with exit code, and SHA-256 hashes of all artifacts, bound by a `manifest_hash`
  hash-chain so a third party can detect tampering (`verify_runpack`).
- **Evidence** — `grade(claim)` and the ladder of §3.
- **Obligation** — decomposition of a claim into individually checkable units.

Checker binaries are pinned in `tools/toolchain.lock.json` to exact git commit
SHAs, each verified by `git ls-remote` against the canonical upstream — not
scraped from a web page. This makes "the verified checker" a precise, rebuildable
referent rather than "whatever was on `PATH`."

---

## 5. Lanes

### 5.1 SAT lane — three-checker UNSAT, HOL4-verified anchor

Pipeline: **CaDiCaL** [14] (solver; untrusted) → **drat-trim** (DRAT check) →
**lrat-trim** (LRAT check) → **`cake_lpr`** (formal gate). CaDiCaL emits a DRAT
proof; the two unverified checkers corroborate; `cake_lpr` — whose LRAT-checking
logic is proven correct in HOL4 — accepts the LRAT certificate (`s VERIFIED
UNSAT`, exit 0). All three gates are fail-closed: any failure yields `ERROR`, not
a silent pass. An `unsat_certificate` claim therefore grades at **E7**: one
formal kernel family (`cake_lpr`/HOL4). The honest path to E8 is a *second*
independent formally-verified LRAT checker; we have not wired one, and the ladder
correctly refuses E8 until we do (a documented gap, §9).

### 5.2 Integration lane — FriCAS × Lean/Coq adjudication

Pipeline: **FriCAS** runs the Risch algorithm (untrusted producer); a **SymPy +
Maxima** derivative residual check is used as *triage* (explicitly not proof —
it can be fooled by branch cuts and simplification limits); promising cases are
discharged by a **Lean 4** [11] kernel proof against Mathlib [12]. The library contains 33
theorems/lemmas with **0 `sorry`, 0 `axiom`**, a count enforced by CI (§6).

For cross-prover verification, the same derivative identity is proved
independently in **Coq + Coquelicot** [13]. Where both kernels prove the *same*
statement on the *same* domain (caveat-free), the claim reaches **E8** —
demonstrated for `bronstein_003` and `bronstein_004`. Branch-cut-divergent cases
are *deliberately held at E7*: Lean's lemma assumes `x ≠ 0` while Coq's assumes
`0 < x`, and the cross-prover gate refuses to call non-identical domain
conditions a cross-verification. This refusal is a feature — it is the ladder
declining to over-grade.

### 5.3 Cross-method lane — E9, and a non-toy instance

E9 requires two formal families proving the same fact by two *genuinely
different methods*. Our verifiable witness that "same fact" is meaningful is a
**cross-translation validator** (`protocols/cross_method_claim.py`): for an
n-variable Boolean statement it enumerates all 2ⁿ assignments and confirms the
CNF and the algebraic predicate denote the same function.

A first instance is a two-variable tautology proved by `ring` over `ZMod 2`
(Lean) and by SAT refutation (`cake_lpr`). It is honest but a *toy*: a reviewer
rightly objects that a novel evidence class deserves a non-trivial witness.

**The non-toy instance is a Tseitin parity contradiction on the 5-cycle C₅.**
Assign a Boolean variable to each edge and one parity constraint per vertex with
an odd total charge:

```
e₅ + e₁ = 1,  e₁ + e₂ = 0,  e₂ + e₃ = 0,  e₃ + e₄ = 0,  e₄ + e₅ = 0   (over GF(2))
```

*Method 1 — GF(2) linear algebra (Lean 4).* Summing the five constraints, every
edge variable lies on exactly two vertices and cancels in characteristic 2, so
the left side collapses to 0 while the right is the total charge, 1 — hence
`0 = 1`. The Lean proof (`fricas_bridge/TseitinC5.lean`) is, in full:

```lean
theorem tseitin_c5_unsat (e1 e2 e3 e4 e5 : ZMod 2)
    (h1 : e5 + e1 = 1) (h2 : e1 + e2 = 0) (h3 : e2 + e3 = 0)
    (h4 : e3 + e4 = 0) (h5 : e4 + e5 = 0) : False := by
  have htwo : (2 : ZMod 2) = 0 := by decide
  have hsum : (2 : ZMod 2) * (e1 + e2 + e3 + e4 + e5) = 1 := by
    linear_combination h1 + h2 + h3 + h4 + h5
  have hzero : (2 : ZMod 2) * (e1 + e2 + e3 + e4 + e5) = 0 := by
    rw [htwo, zero_mul]
  rw [hzero] at hsum
  exact absurd hsum (by decide)
```

This is genuinely the algebraic argument, not enumeration in disguise: the
substantive step is `linear_combination` summing the constraint equations, whose
residual `2·Σeᵢ − 1` is identical on both sides and so closes by `ring` with *no
characteristic assumption*. `decide` is used only on the closed numerals
`(2 : ZMod 2) = 0` and `(0 : ZMod 2) ≠ 1` — never to enumerate the 2⁵
assignments. (This matters: a `decide` over assignments would be the same method
as the SAT side in different syntax.)

*Method 2 — resolution refutation (`cake_lpr`/HOL4).* The same system, encoded as
a 5-variable, 10-clause DIMACS CNF (`benches/multimethod/tseitin_c5.cnf`), is
refuted by CaDiCaL and the LRAT proof accepted by `cake_lpr`.

These are the canonical pair of *different* methods for unsatisfiability:
algebraic (Gaussian elimination over GF(2)) versus propositional resolution,
which are exponentially separated on expander graphs. We deliberately pick a
cycle — bounded treewidth — so both proofs stay cheap while the methods remain
orthogonal. The claim therefore grades **E9** with `lean4`/`gf2_linear_algebra`
+ `cake_lpr`/`sat_refutation`.

---

## 6. Integrity infrastructure: the grade cannot outrun the evidence

The most transferable lesson of building this system was a recurring failure
mode: **capability and documentation repeatedly outran CI-backing** — a theorem
stated before it was in the build; a grade recorded before its proof ran in CI.
Each instance was caught only by external review. The cure is structural, and we
adopted three guards, each of which converts "we checked" into "the build
enforces it."

1. **Soundness guard.** No verified library root may contain `sorry`, `admit`, or
   a top-level `axiom` (Lean: `lean.yml`; Coq: an `Admitted`/`Axiom` guard in
   `coq.yml`). Kernels accept these silently, so green CI without this guard is
   meaningless.
2. **Count guard.** The headline theorem count (33) is recomputed from the source
   files and asserted, so the number in the README, the architecture doc, and the
   status file cannot drift apart (`tests/test_theorem_count.py`).
3. **Evidence-grade guard.** The headline E7/E8/E9 grades are *generated*, not
   hand-written, as `min(grader_class, wiring_class)` and CI fails if the
   committed status block diverges from a fresh regeneration
   (`scripts/generate_evidence_grades.py`, `tests/test_evidence_grades_generated.py`,
   `.github/workflows/evidence-guard.yml`).

The third guard is the load-bearing one, and its design embodies a subtlety
worth stating. Printing `grader.grade(claim)` alone would be unsound: the grader
reads `formal_verified` flags that live in the claim JSON and can be *asserted*
there without the proof ever executing — which is exactly how an earlier E9 read
"Demonstrated" while neither anchor was built. So the grade is gated by a
**wiring check** that reads the real repository (Lean lakefile roots and the
sorry/axiom guard list; the Coq `coqc` step; the SAT-pipeline Make target on a
committed CNF) and strips the `formal_verified` contribution of any anchor not
wired into CI. The wiring term can only *lower* the grade:

```
effective = min(grader_class, wiring_class)
```

Run against the original (unwired) E9 state this generates **Candidate**; run
against the current repository it generates **E9**. The guard would have caught
the original over-grade automatically.

**The guard does not overclaim about itself.** A single CI job cannot witness
that sibling workflows (`lean.yml`, `coq.yml`, `ci.yml`) actually executed, so a
generated "Demonstrated" means **graded-and-wired**, *not* executed-in-this-run.
We state this limit in the generated block and the script. (For the results in
this paper we separately confirmed per-step execution on `main`.) The
anti-overclaim guard must not become the next overclaim — which is itself an
instance of the discipline applied to its own remedy. Notably, while building the
third guard we discovered that the count guard, long cited as our model of
structural enforcement, was referenced by *no* workflow and had never actually
run in CI; the consolidating workflow runs unconditionally (no path filter) so
that it cannot silently skip.

---

## 7. Honest supporting work: a CAS hunt with a null result

To test whether the apparatus could *discover* error rather than only certify
curated cases, we ran a live two-CAS scan (SymPy + Maxima) over 191 integrands
(`cross_prover/cas_hunt.py`), classifying each disagreement (AGREE,
AGREE_UP_TO_C, FORM_DISAGREE, DOMAIN_DISAGREE with subclasses, GENUINE_DISAGREE).
The result is a **clean null**: no `GENUINE_DISAGREE` — no CAS caught producing a
wrong antiderivative.

The result we are most willing to stand behind is methodological: the apparent
positives in early runs were traced to bugs in *our own instrument* (a Maxima
parser issue; a complex-axis sampling artifact) and corrected, rather than
reported as findings. Four `FORM_DISAGREE` cases (genuinely different symbolic
forms of the same antiderivative) are **kernel-adjudicated** — proved equal in
Lean via `Real.log_mul` (`fricas_bridge/CasAdjudication.lean`), with a CI check
guaranteeing every adjudication certificate names a theorem that actually exists.
We are explicit that the SymPy/Maxima derivative check is **triage, not proof**:
only the Lean/Coq kernel theorems are binding verdicts. A null result at this
scale is honest supporting evidence, not a headline; scaling the hunt (or
pivoting to verified *non-existence*, §10) is where a citable finding would come
from.

---

## 8. Novelty, stated as narrowly as the artifact supports

**Claimed.** A unified, mechanized, evidence-graded foundry that treats SAT
refutation and symbolic-integration verification as instances of one trust
pattern, with (a) a fail-closed ladder whose E7 gate cannot be reached by
assertion, (b) an evidence class (E9) that grades by independent-method
diversity, demonstrated on a non-trivial Tseitin instance, and (c) a generated,
CI-enforced grade that prevents the recorded evidence class from preceding its
executed proof.

**Not claimed.** Cross-prover verification (Lean+Coq of one theorem) is not
novel; we built a clean instance. The skeptic approach to CAS output, the
DRAT/LRAT checker ecosystem, and `cake_lpr` itself are prior art used as-is. "First
kernel-verified FriCAS Risch certificates" is true only in the narrow,
FriCAS-specific sense; the general technique is well established and we scope the
claim tightly. The E9 *mechanism* is the contribution; the Tseitin instance is a
minimal witness, not evidence of scale.

---

## 9. Limitations and threats to validity

- **Scale.** 33 kernel-checked theorems, 191 integrands, two E9 instances (one
  toy, one non-toy), two lanes, no external users. The *pattern* is demonstrated;
  it is **not validated at scale**. This is an appropriate stage for a
  demonstrator paper, not a library others depend on.
- **Single-kernel adjudication.** CAS disagreement cases are adjudicated by Lean
  alone; there is no Coq adjudication theorem yet.
- **SAT lane is E7, not E8.** Only one formally-verified LRAT checker is wired.
- **"Wired ≠ executed-this-run."** The grade guard certifies static wiring plus
  the grader; cross-run co-execution of the formal anchors is confirmed
  out-of-band, not by a single gating pipeline.
- **E10/E11 unimplemented.** No adversarial falsifier; no external field
  validation.
- **Bus factor / rapid AI-assisted development.** The verification discipline has
  historically depended on external scrutiny; the structural guards (§6) reduce
  but do not eliminate that dependence.

---

## 10. Future work

In priority order: (1) a second formally-verified LRAT checker to lift the SAT
lane to E8; (2) *scaling the hunt* to thousands of integrands (a strong null is
publishable) or, more ambitiously, attacking **verified non-existence** —
formalizing Liouville's theorem on non-elementary integrability, which no
proof assistant has done and which is the genuine frontier; (3) a MILP lane on
the VIPR certificate model; (4) Isabelle as a third kernel family; (5) the E10
adversarial falsifier.

---

## 11. Conclusion

ProofForge Ω is a coherent, honestly-graded, CI-backed proof-of-concept for a
unified verification foundry. Its defensible contributions are narrow and real:
the structural-identity thesis across two unrelated lanes, an evidence class that
grades by method diversity with a non-toy demonstration, and an integrity
mechanism that makes a recorded grade unable to outrun its executed evidence. The
last of these is the one we most want others to take: in a world where producers
out-run checkers, the scarce discipline is not generating another claim but
refusing to record it as verified until the verification has actually run.

---

## Appendix A — Reproducibility

- **Python tests** (no external tools): `pip install -e ".[dev]" && pytest tests/ backbone/ -v`.
- **SAT lane**: `bash scripts/tools/install_sat_toolchain.sh` (builds cadical,
  drat-trim, lrat-trim, cake_lpr from SHA-pinned sources) then `make demo`;
  per-instance checks via `make gf2` and `make tseitin`.
- **Lean / Coq**: `.github/workflows/lean.yml` and `coq.yml` give the exact
  toolchain; proofs are kernel-checked in CI on every push.
- **Grades**: `python scripts/generate_evidence_grades.py --check` regenerates and
  verifies the headline grade block.
- **Pins**: `tools/toolchain.lock.json` (git-SHA-pinned, `git ls-remote`-verified).

## Appendix B — Bibliography

Verified against primary sources (web check, June 2026). Entries give
authors, title, venue, year, pages, and DOI/identifier where one exists.
Final *formatting* should follow the chosen venue's style (e.g. BibTeX/LNCS);
the bibliographic facts below are the checked content.

1. J. Harrison and L. Théry. *A Skeptic's Approach to Combining HOL and Maple.*
   Journal of Automated Reasoning 21(3):279–294, 1998. DOI 10.1023/A:1006023127567.
2. S. Buswell, O. Caprotti, D. P. Carlisle, M. C. Dewar, M. Gaëtano, and
   M. Kohlhase. *The OpenMath Standard, Version 2.0.* The OpenMath Society, 2004.
   https://openmath.org/standard/
3. R. Kumar, M. O. Myreen, M. Norrish, and S. Owens. *CakeML: A Verified
   Implementation of ML.* POPL 2014, pp. 179–191. DOI 10.1145/2535838.2535841.
4. Y. K. Tan, M. J. H. Heule, and M. O. Myreen. *cake_lpr: Verified Propagation
   Redundancy Checking in CakeML.* TACAS 2021, LNCS 12651, pp. 223–241.
   DOI 10.1007/978-3-030-72013-1_12.
5. N. Wetzler, M. J. H. Heule, and W. A. Hunt Jr. *DRAT-trim: Efficient Checking
   and Trimming Using Expressive Clausal Proofs.* SAT 2014, LNCS 8561,
   pp. 422–429. DOI 10.1007/978-3-319-09284-3_31.
6. L. Cruz-Filipe, M. J. H. Heule, W. A. Hunt Jr., M. Kaufmann, and
   P. Schneider-Kamp. *Efficient Certified RAT Verification.* CADE 2017,
   LNCS 10395, pp. 220–236. DOI 10.1007/978-3-319-63046-5_14. (arXiv:1612.02353)
7. K. K. H. Cheung, A. Gleixner, and D. E. Steffy. *Verifying Integer Programming
   Results.* IPCO 2017, LNCS 10328, pp. 148–160. (arXiv:1611.08832)
8. G. S. Tseitin. *On the complexity of derivation in propositional calculus.*
   Zapiski Nauchnykh Seminarov LOMI 8 (1968), pp. 234–259 (Russian); English
   translation in A. O. Slisenko (ed.), *Studies in Constructive Mathematics and
   Mathematical Logic, Part II*, 1970, pp. 115–125.
9. A. Urquhart. *Hard examples for resolution.* Journal of the ACM 34(1):209–219,
   1987. DOI 10.1145/7531.8928.
10. E. Ben-Sasson and A. Wigderson. *Short Proofs Are Narrow—Resolution Made
    Simple.* Journal of the ACM 48(2):149–169, 2001 (prelim. STOC 1999).
    DOI 10.1145/375827.375835.
11. L. de Moura and S. Ullrich. *The Lean 4 Theorem Prover and Programming
    Language.* CADE 28, 2021, LNCS 12699, pp. 625–635.
    DOI 10.1007/978-3-030-79876-5_37.
12. The mathlib Community. *The Lean Mathematical Library.* CPP 2020,
    pp. 367–381. DOI 10.1145/3372885.3373824. (arXiv:1910.09336)
13. S. Boldo, C. Lelay, and G. Melquiond. *Coquelicot: A User-Friendly Library of
    Real Analysis for Coq.* Mathematics in Computer Science 9(1):41–62, 2015.
    DOI 10.1007/s11786-014-0181-1.
14. A. Biere, K. Fazekas, M. Fleury, and M. Heisinger. *CaDiCaL, Kissat,
    Paracooba, Plingeling and Treengeling Entering the SAT Competition 2020.*
    Proc. SAT Competition 2020 — Solver and Benchmark Descriptions, pp. 51–53,
    University of Helsinki, 2020.

*Note.* Entry 7 (VIPR): the IPCO 2017 chapter DOI was not independently
confirmed in this pass; the arXiv identifier and venue/pages are verified. Add
the chapter DOI from the proceedings when formatting.
