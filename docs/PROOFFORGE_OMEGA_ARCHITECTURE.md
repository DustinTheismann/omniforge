# ProofForge Ω — Architecture

**ProofForge Ω** is a machine-checkable accountability layer for generated knowledge.

It takes claims from AI systems, CAS outputs, papers, code, and benchmarks and forces them through:

```
claim → formal representation → executable test → proof/counterexample/search
      → reproducible runpack → evidence class → public audit artifact
```

---

## Core thesis

AI can now generate hypotheses, code, proofs, algorithms, and scientific claims faster than humans can verify them.
The bottleneck is no longer generation — it is **verification, reproducibility, falsification, and formal accountability**.

ProofForge Ω is the survival machine: it cannot make generated knowledge right, but it can make it *accountable*.

---

## Protocol Spine (Phase 0)

Everything in ProofForge Ω is built on four interlocking protocols.

### 1. Claim Protocol — `protocols/claim_protocol/`

The **universal atomic evidence object**.

Every computational, mathematical, or scientific claim becomes a `Claim` instance:

```json
{
  "claim_id": "pf.integral.000001",
  "claim_type": "symbolic_antiderivative",
  "natural_language": "The derivative of log(x²+1)/2 is x/(x²+1).",
  "source": {"kind": "cas", "name": "FriCAS", "version": "1.3.11"},
  "inputs":  {"integrand": "x/(x^2+1)", "variable": "x"},
  "outputs": {"candidate_antiderivative": "log(x^2+1)/2"},
  "formal_targets": [...],
  "assumptions":    [...],
  "obligations":    [...],
  "checker_results":[...],
  "evidence_class": "E7_FORMALLY_VERIFIED",
  "flags": [],
  "artifacts": {"lean_file": "..."}
}
```

Supported `claim_type` values:
- `symbolic_antiderivative`
- `algebraic_identity`
- `theorem_statement`
- `algorithm_benchmark`
- `numerical_experiment`
- `paper_claim`
- `simulation_result`
- `code_correctness`
- `unsat_certificate`

Key files:
| File | Purpose |
|---|---|
| `schema.json` | JSON Schema (draft 2020-12) — canonical definition |
| `types.py` | Python dataclasses and enums for typed access |
| `validate.py` | `validate_claim()` / `ClaimValidationError` |
| `examples/` | 6 example claims (one per major claim type) |

### 2. Runpack Protocol — `protocols/runpack_protocol/`

Every claim that passes through the Claim Transmutation Engine emits a **runpack** — a reproducibility capsule containing:
- All tool versions (pinned)
- All commands executed (with exit codes and stdout/stderr hashes)
- All artifact files with SHA-256 hashes
- A hash chain so any third party can verify integrity

```
RunpackBuilder("pf.integral.000001")
  .record_command(["lean", "build"], exit_code=0)
  .record_artifact("artifacts/Theorem.lean", role="proof")
  .build(verification_result="passed")
  .save(Path("runpacks/manifest.json"))
```

`verify_runpack(path)` checks:
1. Schema validity
2. `manifest_hash` matches recomputed hash (tamper detection)
3. All artifact SHA-256 hashes match files on disk

Key files:
| File | Purpose |
|---|---|
| `manifest.schema.json` | JSON Schema for the runpack manifest |
| `pack.py` | `RunpackBuilder` — create runpacks |
| `verify.py` | `verify_runpack()` — verify integrity |

### 3. Evidence Protocol — `protocols/evidence_protocol/`

The **evidence ladder** prevents hype. Every claim gets an evidence class; no claim can skip rungs without satisfying the gate condition.

```
E0  RAW_CLAIM          — prose, assertion, model output
E1  SOURCED            — origin is known
E2  PARSED             — typed, schema-valid claim object
E3  EXECUTABLE         — at least one obligation has been run
E4  REPRODUCED         — runpack replay passes
E5  NUMERICALLY_SUPPORTED — property/interval tests pass
E6  SYMBOLICALLY_SUPPORTED — CAS or SMT checker passes
E7  FORMALLY_VERIFIED  — proof kernel accepts the proof  ← GOLD STANDARD
E8  CROSS_VERIFIED     — 2+ independent checker families
E9  ADVERSARIALLY_HARDENED — falsifier failed to refute
E10 FIELD_VALIDATED    — upstream accepted, peer-reviewed
EX  REFUTED            — counterexample or failed reproduction (OVERRIDES ALL)
```

**Critical invariant**: `E7_FORMALLY_VERIFIED` requires `checker_result.formal_verified == True`.
This flag may only be set by a proof-assistant kernel output — never by an LLM assertion.

**Critical invariant**: `EX_REFUTED` overrides all positive classes when triggered.

Key files:
| File | Purpose |
|---|---|
| `evidence_classes.yaml` | Human-readable ladder with gates and upgrade rules |
| `grader.py` | `grade(claim)` — compute evidence class; `downgrade()` — force EX_REFUTED |

### 4. Obligation Protocol — `protocols/obligation_protocol/`

A claim decomposes into one or more **obligations** — individual things that must be checked:

```
Claim: "algorithm A is correct and faster than B"
  O1: formal_equivalence    → checker: Lean4
  O2: benchmark_performance → checker: timeit
  O3: statistical_claim     → checker: scipy.stats
  O4: reproduction          → checker: docker_repro
```

Obligation kinds:
- `formal_derivative_check`, `formal_theorem`, `formal_equivalence`
- `numeric_property`, `reproduction`
- `benchmark_correctness`, `benchmark_performance`, `statistical_claim`
- `counterexample_search`

---

## Six-Layer Architecture

```
             ┌─────────────────────────────┐
             │  AI / Human / Paper / CAS    │
             │  Code / Notebook / Benchmark │
             └──────────────┬──────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────┐
│  L1: Claim Intake                                         │
│  Parse, classify, normalize, source, decompose            │
└───────────────────────┬──────────────────────────────────┘
                        ▼
┌──────────────────────────────────────────────────────────┐
│  L2: Claim Formalization                                  │
│  NL → typed claim → formal target → assumptions           │
└───────────────────────┬──────────────────────────────────┘
                        ▼
┌──────────────────────────────────────────────────────────┐
│  L3: Obligation Graph                                     │
│  Theorem obligations, tests, repro commands, falsifiers   │
└───────────────────────┬──────────────────────────────────┘
                        ▼
┌──────────────────────────────────────────────────────────┐
│  L4: Checker Mesh                                         │
│  Lean, CAS, SMT, property tests, interval arithmetic, CI  │
└───────────────────────┬──────────────────────────────────┘
                        ▼
┌──────────────────────────────────────────────────────────┐
│  L5: Evidence Ledger                                      │
│  Proofs, failures, counterexamples, runpacks, hashes      │
└───────────────────────┬──────────────────────────────────┘
                        ▼
┌──────────────────────────────────────────────────────────┐
│  L6: Public Knowledge Interface                           │
│  Audit cards, discrepancy atlas, badges, dashboards       │
└──────────────────────────────────────────────────────────┘
```

---

## Five Foundries

All foundries share the same backbone protocols.

| Foundry | Input | Primary checkers |
|---|---|---|
| **MathClaim Forge** | CAS outputs, integration tables, theorem statements | Lean 4, FriCAS, SymPy, Maxima |
| **Algorithm Forge** | AI-proposed algorithms, benchmark claims | pytest, timeit, property tests |
| **PaperClaim Forge** | arXiv/PDF papers, notebooks | repro capsules, equation parsers |
| **Simulation Forge** | ODE/PDE/Monte Carlo results | interval arithmetic, convergence tests |
| **Discrepancy Atlas** | All failures from the other foundries | human review, upstream issue export |

---

## Checker Mesh

Each formal proof system has its own unique checker family name in the grader
(lean4, coq, isabelle, cake_lpr, …). This means Lean+Coq counts as two
independent formal families; Lean alone counts as one.

| Checker family | Examples | Highest evidence class reachable |
|---|---|---|
| lean4 | Lean 4 kernel | E8_CROSS_VERIFIED (with ≥1 other formal kernel) |
| coq | Coq/Rocq kernel | E8_CROSS_VERIFIED (with ≥1 other formal kernel) |
| isabelle | Isabelle/HOL | E8_CROSS_VERIFIED (with ≥1 other formal kernel) |
| cake_lpr | cake_lpr (HOL4-proven binary) | E8_CROSS_VERIFIED (with ≥1 other formal kernel) |
| cas | FriCAS, SymPy, Maxima | E6_SYMBOLICALLY_SUPPORTED |
| smt | Z3, CVC5 | E6_SYMBOLICALLY_SUPPORTED |
| sat | CaDiCaL, drat-trim, lrat-trim | E6_SYMBOLICALLY_SUPPORTED |
| numeric | Hypothesis, interval arithmetic | E5_NUMERICALLY_SUPPORTED |
| repro | Docker replay, notebook exec | E4_REPRODUCED |

**E8 gate**: E8_CROSS_VERIFIED requires ≥2 distinct formal kernel systems,
each reporting `formal_verified=True`. SAT/CAS/SMT corroboration contributes
to E6 but does not satisfy the E8 gate. Example paths to E8:
- Integration lane: Lean 4 kernel + Coq kernel both check the same theorem
- SAT lane: cake_lpr (HOL4) + Isabelle-verified gratchk both check the LRAT proof

**Current status** (v0.4.0):
- SAT lane: cake_lpr alone → **E7_FORMALLY_VERIFIED** (1 formal kernel)
- Integration lane: Lean 4 alone → **E7_FORMALLY_VERIFIED** (1 formal kernel)

---

## Governance — non-negotiable rules

1. Never label a claim `proved` unless `formal_verified == True` in a checker result.
2. Never label a result `reproduced` unless the runpack replay passes with matching hashes.
3. Never hide failed checks — failures are first-class outputs.
4. `EX_REFUTED` overrides all positive evidence.
5. LLMs propose; checkers assign evidence.
6. Always record assumptions.
7. Always pin tool versions.
8. Always hash artifacts.

---

## Phase roadmap

| Phase | Deliverable | Status |
|---|---|---|
| 0 | Protocol spine (claim, runpack, evidence, obligation, transmutation) | **Done** |
| 1 | Symbolic integration wedge (FriCAS → Lean 4) | **Done** — 31 kernel-verified theorems/lemmas (0 sorry, 0 axiom) |
| 2 | SymPy/Maxima adapters + cross-CAS disagreement detector | **Done** — live hunt over 191 integrands; 0 net genuine CAS errors |
| 3 | SAT lane with HOL4-verified formal trust anchor (cake_lpr) | **Done** — three-checker pipeline, E7_FORMALLY_VERIFIED unsat_certificate |
| 4 | Corpus-scale runner (Rubi/DLMF/Bronstein) | Planned |
| 5 | Discrepancy atlas + public dashboard | Planned |
| 6 | Algorithm forge (benchmark claim protocol) | Planned |
| 7 | PaperClaim forge (LaTeX extractor + repro capsules) | Planned |
| 8 | GitHub Action + CLI installer | Planned |
| 9 | `ProofForge Standard v1` + paper/preprint | Planned |

---

## Quick start

```bash
# Install
pip install -e .

# Validate all example claims
python -m pytest tests/test_claim_protocol.py -v

# Validate runpack integrity
python -m pytest tests/test_runpack_protocol.py -v

# Validate evidence grader
python -m pytest tests/test_evidence_grader.py -v

# All backbone tests (CAS protocol)
python -m pytest backbone/tests/ -v

# Everything
make test-all
```

---

## The north star

> ProofForge Ω becomes the GitHub Actions of scientific truth claims —
> not because it decides truth absolutely, but because it forces every claim to declare:
> what it is, where it came from, what checked it, what failed,
> what assumptions it needs, how to replay it, and how strong the evidence is.
