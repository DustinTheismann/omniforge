[![ci](https://github.com/DustinTheismann/omniforge/actions/workflows/ci.yml/badge.svg)](https://github.com/DustinTheismann/omniforge/actions/workflows/ci.yml)
# OmniForge / ProofForge Ω — Verifiable Algorithm Foundry (v0.4.0)

A **lane-based verifiable algorithm foundry**. Every claim that passes through ProofForge Ω carries an immutable evidence class, a sealed runpack, and a checkable obligation graph. Nothing advances beyond E0 (raw assertion) without passing gated checkers.

## What is different

- **Fail-closed**: a claim is rejected if any required gate fails; failures are first-class outputs.
- **Evidence ladder**: claims carry an explicit evidence class (E0–E10); no rung can be skipped without satisfying the gate condition.
- **Reproducible**: every run emits a runpack — pinned tool versions, all commands, SHA-256 artifact hashes, tamper-evident manifest.
- **Formally anchored**: the trust anchor for each lane is a proof-assistant kernel output (Lean 4, HOL4), not an LLM assertion.

---

## Lanes

### SAT Lane — three-checker UNSAT verification
**Status: live, HOL4-verified trust anchor.**

Full pipeline: CaDiCaL (solver) → drat-trim (DRAT gate) → lrat-trim (LRAT gate) → cake_lpr (formal gate).

`cake_lpr` is a CakeML binary whose LRAT-checking logic is **formally proven correct in HOL4**. Its acceptance of the LRAT proof (`s VERIFIED UNSAT` + exit 0) is a formal soundness guarantee, not a heuristic check. All three gates are fail-closed: the UNSAT verdict is rejected if any gate fails.

Result: `unsat_certificate` claims grade at **E8_CROSS_VERIFIED** — two independent checker families (SAT family: cadical/drat-trim/lrat-trim; formal family: cake_lpr) both verify the same proof.

### Integration Lane — CAS × Lean 4 adjudication
**Status: live, kernel-verified.**

Pipeline: FriCAS Risch integration → symbolic derivative residual check (SymPy/Maxima) → Lean 4 kernel proof.

Live two-CAS scan (SymPy + Maxima) over 191 integrands found 0 net genuine CAS errors after review.
- `fricas_bridge/CasAdjudication.lean`: 10 Lean 4 theorems, 0 sorry, 0 axiom.
- `fricas_bridge/RischVerification.lean`: 9 Lean 4 theorems, 0 sorry, 0 axiom — first kernel-verified FriCAS Risch certificates.

---

## One-command demo

Runs the full three-checker SAT pipeline on a benchmark CNF, emits a claim at E8_CROSS_VERIFIED, and validates the artifact bundle.

```bash
make demo
```

Produces:
- `artifacts/run_<run_id>/manifest.json`
- `artifacts/run_<run_id>/claim.json` — unsat_certificate at E8_CROSS_VERIFIED
- `artifacts/run_<run_id>/runpacks/<claim_id>/manifest.json` — sealed runpack

## Run the tests

```bash
make test-all          # all tests
pytest tests/ -v       # protocol + lane tests
pytest backbone/ -v    # CAS adjudication tests
```

## Validate contracts

```bash
make validate-contracts
```

## Reproduce a run (verify hashes)

```bash
make reproduce RUN_ID=<run_id>
```

---

## Protocol spine

| Protocol | Location | Purpose |
|---|---|---|
| Claim | `protocols/claim_protocol/` | Universal evidence object; JSON Schema + Python types |
| Runpack | `protocols/runpack_protocol/` | Reproducibility capsule; pinned tools + artifact hashes |
| Evidence | `protocols/evidence_protocol/` | `grade(claim)` → E0–E10; fail-closed gates |
| Obligation | `protocols/obligation_protocol/` | Decomposes claims into checkable units |

## Contracts

- `omniforge/contracts/eval_contract.schema.json`
- `omniforge/contracts/artifact_manifest.schema.json`

## Toolchain pins

`tools/toolchain.lock.json` pins every checker to an exact git commit SHA, verified via `git ls-remote` against the canonical repository — never scraped from web pages.
