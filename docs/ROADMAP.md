# Beyond Groundbreaking: Full Technical Execution Plan

**Source state:** `omniforge` PR #2, Lean CI green  
**Plan scope:** five parallel swings, ~18 months to "field-defining," 36–60 months to "transformative"

## Architectural premise

The five swings share a substantial backbone. Phase 0 (weeks 1–4) builds that backbone;
Swings 1, 2, 3 begin parallel execution at week 4; Swing 4 at month 4; Swing 5 is a
continuous design track going capital-intensive in year 2.

```
                    ┌─── Swing 1: Mathlib Tactic ────┐
Phase 0 backbone ───┼─── Swing 2: Bug Hunt ──────────┤── Swing 4: Cross-CAS
(weeks 1–4)         └─── Swing 3: AlphaIntegrate ────┘   (months 4–18)
                                                          Swing 5: Successor CAS (continuous)
```

## Phase 0: Backbone (weeks 1–4)

- `backbone/fricas_runtime/`: dockerized FriCAS JSON-RPC server with SQLite cache
- `backbone/cas_protocol/`: cross-CAS interchange schema + Lean emitter
- `backbone/proof_template/`: parameterized Lean proof generator
- `backbone/corpus/`: master integration corpus (target: 8,000–12,000 entries)

Acceptance: docker image answers requests at <200ms cache-hit; corpus ≥8,000 entries;
proof_template regenerates all existing theorems; backbone.yml CI green.

## Swing 1: Mathlib `by fricas_integrate` tactic (months 2–6)

Lean 4 tactic that reflects a `HasDerivAt` goal, calls FriCAS via the dockerized runtime,
generates a proof via `backbone/proof_template`, and discharges the goal.
Ships with a precomputed offline cache so Mathlib CI does not need FriCAS.

## Swing 2: Bug Hunt (months 2–9)

Parallel batch runner over the full corpus. Every outcome classified:
VERIFIED_CLEAN / VERIFIED_HYPOTHESES / AUDIT_FALSE_POSITIVE / MATHLIB_GAP /
SUSPECTED_FRICAS_BUG / FRICAS_NO_RESULT / PIPELINE_ERROR.
Weekly reports in `swing2_bug_hunt/reports/`. Confirmed bugs filed to FriCAS upstream
with kernel-checked counterexamples.

## Swing 3: AlphaIntegrate (months 2–12)

arXiv scraper (math.CA, math-ph, hep-th) → integral extractor → FriCAS →
bridge verification → novelty filter (Wolfram Functions, DLMF, G&R) →
LLM candidate-variant generation (Claude API) → publication queue.
Target: ≥1 paper-novel identity published with kernel-checked proof in year 1.

## Swing 4: Cross-CAS Arbitration (months 4–18)

SymPy and Maxima bridges built against the same `cas_protocol` schema.
Disagreement detector finds integrals where CAS systems diverge; Lean kernel adjudicates.
Target: ≥50 documented disagreements, ≥5 revealing a genuine CAS assumption gap.

## Swing 5: Successor CAS (continuous design, capital from year 2)

RFC-001: domain-tracking types in SPAD / Lean 4 type system.
RFC-002: constructive Risch algorithm where output type is `Σ F, Domain × ∀ x ∈ Domain, HasDerivAt F (f x) x`.
Year 2: minimal prototype for transcendental case, polynomial denominators only.

## Timeline

| Month | Phase 0 | Swing 1 | Swing 2 | Swing 3 | Swing 4 | Swing 5 |
|---|---|---|---|---|---|---|
| 1 | infrastructure | — | — | — | — | RFC drafts |
| 2 | complete | tactic kickoff | corpus run | scraper live | — | RFC review |
| 4 | — | tactic beta | weekly reports | LLM agent | sympy bridge | design |
| 6 | — | Mathlib PR | Mathlib lemma PRs | manuscript | disagreements | design |
| 9 | — | PR landing | bug hunt mature | submission | catalog | RFC v1.0 |
| 12 | — | in Mathlib | retrospective | first pub | ISSAC paper | prototype |
| 24 | — | — | — | — | — | prototype beta |

*Roadmap v1.0 · D. Theismann + Claude (Anthropic)*
