# MAXOUT — Addable Components (dependency-ordered build sequence)

**State at write time:** commit `874097f`, 455 tests green, CI workflows passing.
**Swing 1 status:** Steps A–E done; tactic frontend + Step F (Mathlib PR) remain.
**This document:** buildable specifications for every component addable to the codebase as it stands, organized by dependency tier. Each item is scoped to ≤ 1–3 sessions.

Legend: **[BLOCKED:x]** needs x first · **[READY]** buildable now · **[RISK:h/m/l]**.

> Authoritative build order. The discipline: dependency order, one branch at a
> time past Tier 0, Tier 0 first because the tactic frontend is the keystone
> that retroactively justifies Steps B–E.

---

## TIER 0 — Close Swing 1
- **0.1** `FriCASIntegrate/Tactic.lean` — the `fricas_integrate` elab tactic. [READY][RISK:h]
- **0.2** `FriCASIntegrate/Sha256.lean` — pure-Lean SHA-256, toolchain-pure cache keying. [READY][RISK:m]
- **0.3** In-Lean `#eval` behavioral tests for the translators. [BLOCKED:0.1][RISK:l]
- **0.4** `mathlib_pr/` — fork, namespace `Mathlib.Tactic.FriCAS`, open PR. [BLOCKED:0.1,0.2][RISK:m]

## TIER 1 — Discharge all four discrepancy classes
- **1.1** `proof_discharger.synthesize_hypotheses` — hypothesis binders from audit. [READY][RISK:m]
- **1.2** Class B template (single vanishing-factor log, 1 hypothesis). [BLOCKED:1.1][RISK:l]
- **1.3** Class C/D template (n distinct linear poles, n hypotheses). [BLOCKED:1.2][RISK:m]
- **1.4** `partial_fraction_hasDerivAt` — the scaling-law theorem (general n). [BLOCKED:1.3][RISK:h]
- **1.5** `audit.semantic_filter` — drop kernel-dischargeable false positives. [READY][RISK:m]

## TIER 2 — The audit becomes a research instrument
- **2.1** `branch_audit` — FriCAS principal-branch vs Lean `log|·|` discrepancy. [READY][RISK:h]
- **2.2** Removable-singularity detector. [BLOCKED:2.1][RISK:h]
- **2.3** `catalog_gen` — regenerate CATALOG.md mechanically. [BLOCKED:1.5,2.1][RISK:l]

## TIER 3 — Lateral operations (same architecture, new verbs)
- **3.1** `fricas_differentiate`. [READY][RISK:l]
- **3.2** `fricas_limit`. [READY][RISK:m]
- **3.3** `fricas_series`. [BLOCKED:3.2][RISK:h]
- **3.4** `fricas_sum`. [BLOCKED:3.3][RISK:h]
- **3.5** `fricas_factor`. [READY][RISK:m]
- **3.6** `fricas_groebner` — the hard test case. [BLOCKED:3.5][RISK:h]

## TIER 4 — Complete ProofForge Ω
- **4.1** `obligation_protocol/` — fill the empty protocol. [READY][RISK:m]
- **4.2** `protocols/transmute.py` — the Claim Transmutation Engine. [BLOCKED:4.1][RISK:m]
- **4.3** `evidence_protocol/upgrade.py` — auto-transition up the ladder. [BLOCKED:4.2][RISK:l]
- **4.4** `runpack_protocol/replay.py` — replay in clean container. [READY][RISK:m]
- **4.5** `claim_protocol/depgraph.py` — cross-claim dependency DAG. [BLOCKED:4.1][RISK:l]

## TIER 5 — Cross-CAS (Swing 4)
- **5.1** `SymPyResolver`. [READY][RISK:l]
- **5.2** `MaximaResolver` — dockerized Maxima. [BLOCKED:5.1][RISK:m]
- **5.3** `cross_cas/agree.py` — multi-CAS agreement (differ-by-constant). [BLOCKED:5.2][RISK:m]
- **5.4** `cross_cas/disagreements/` — the disagreement catalog ★. [BLOCKED:5.3][RISK:m]

## TIER 6 — Bug hunt (Swing 2)
- **6.1** `corpus/ingest_rubi.py` — ≥6000 entries. [READY][RISK:m]
- **6.2** `swing2_bug_hunt/runner.py` — parallel batch runner. [BLOCKED:6.1][RISK:l]
- **6.3** `swing2_bug_hunt/classifier.py` — 7-way outcome enum. [BLOCKED:6.2][RISK:m]
- **6.4** `swing2_bug_hunt/triage.py`. [BLOCKED:6.3][RISK:m]

## TIER 7 — AlphaIntegrate (Swing 3)
- **7.1** `arxiv_scraper.py`. [READY][RISK:l]
- **7.2** `extract.py` — integral extractor. [BLOCKED:7.1][RISK:h]
- **7.3** `novelty.py` — DLMF/Wolfram/OEIS filter. [BLOCKED:7.2][RISK:m]
- **7.4** `loop.py` — discovery loop. [BLOCKED:7.3][RISK:m]

## TIER 8 — Cross-prover (the un-fakeable play)
- **8.1** `cross_prover/coq_emitter.py` — FriCAS → Coquelicot. [READY][RISK:h]
- **8.2** `cross_prover/agree.py` — cross-prover certificate ★. [BLOCKED:8.1][RISK:m]
- **8.3** `cross_prover/isabelle_emitter.py`. [BLOCKED:8.2][RISK:h]

## TIER 9 — RLKV & the verified corpus (the ML play)
- **9.1** `ml/export_corpus.py`. [READY][RISK:l]
- **9.2** `ml/kernel_reward.py` — binary RLKV signal. [BLOCKED:9.1][RISK:m]
- **9.3** `ml/benchmark/` — miniF2F-style, kernel-graded. [BLOCKED:9.1][RISK:l]

## TIER 10 — Hardening (parallel to all tiers)
- **10.1** Build + run the FriCAS Docker image in CI. [READY][RISK:m]
- **10.2** `tests/test_e2e.py` — full chain. [BLOCKED:0.1][RISK:m]
- **10.3** `tests/test_parsers_property.py` — hypothesis round-trips. [READY][RISK:l]
- **10.4** Mutation testing of the audit (reject bad antiderivatives). [BLOCKED:1.5][RISK:m]

---

## Dependency-ordered build sequence

```
NOW ──► 0.2 SHA256 ──► 0.1 tactic ──► 0.3 #eval tests ──► 10.2 e2e ──► 0.4 Mathlib PR
   ├──► 1.1 hyp-synth ──► 1.2 ClassB ──► 1.3 ClassC/D ──► 1.4 scaling-thm
   │                                  └──► 1.5 semantic-audit ──► 2.1 branch-cut ──► 2.3 catalog-gen
   ├──► 4.1 obligations ──► 4.2 transmute ──► 4.3 evidence-upgrade
   │                    └──► 4.4 replay ──► 4.5 depgraph
   ├──► 5.1 SymPy ──► 5.2 Maxima ──► 5.3 agree ──► 5.4 DISAGREEMENT CATALOG ★
   ├──► 3.1 differentiate ──► 3.2 limit ──► 3.5 factor ──► 3.6 groebner
   ├──► 6.1 rubi ──► 6.2 runner ──► 6.3 classifier ──► 6.4 triage ──► first bug ★
   ├──► 7.1 scrape ──► 7.2 extract ──► 7.3 novelty ──► 7.4 loop ──► first novel identity ★
   ├──► 8.1 coq ──► 8.2 CROSS-PROVER CERTIFICATE ★ ──► 8.3 isabelle
   └──► 9.1 export ──► 9.2 kernel-reward ──► RLKV substrate ★
```

★ = the five edge results: cross-CAS disagreement adjudication · first verified CAS
bug · first kernel-checked novel identity · first cross-prover certificate · RLKV substrate.

## The honest edge
Single most novel buildable artifact: **8.2 — the cross-prover certificate** (one
integral kernel-verified in Lean *and* Coq, both runpacked; two independent kernels,
no shared trusted base). Runner-up: **5.4 — the disagreement catalog**.

## Implementation status in this repository
Components whose verification needs an external binary/network/compute resource not
present in the build sandbox (live FriCAS, `coqc`, Isabelle, Docker, arXiv/Rubi
network scraping, real `lake build`) are shipped as **generators + structural tests**:
they produce the exact artifact text and validate its structure in pure-Python CI,
with the binary-dependent acceptance check deferred to an environment that has the
tool. This keeps every component testable now while remaining faithful to its spec.
