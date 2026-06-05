[![ci](https://github.com/DustinTheismann/omniforge/actions/workflows/ci.yml/badge.svg)](https://github.com/DustinTheismann/omniforge/actions/workflows/ci.yml)
# OmniForge / ProofForge Ω — Verifiable Algorithm Foundry (v0.4.0)

A **lane-based verifiable algorithm foundry**. Every claim that passes through ProofForge Ω carries an immutable evidence class, a sealed runpack, and a checkable obligation graph. Nothing advances beyond E0 (raw assertion) without passing gated checkers.

## What is different

- **Fail-closed**: a claim is rejected if any required gate fails; failures are first-class outputs.
- **Evidence ladder**: claims carry an explicit evidence class (E0–E11); no rung can be skipped without satisfying the gate condition.
- **Reproducible**: every run emits a runpack — pinned tool versions, all commands, SHA-256 artifact hashes, tamper-evident manifest.
- **Formally anchored**: the trust anchor for each lane is a proof-assistant kernel output (Lean 4, HOL4), not an LLM assertion.

---

## Lanes

### SAT Lane — three-checker UNSAT verification
**Status: live, HOL4-verified trust anchor.**

Pipeline: CaDiCaL (solver, untrusted producer) → drat-trim (DRAT checker) → lrat-trim (LRAT checker) → cake_lpr (formal gate, trust anchor).

`cake_lpr` is a CakeML binary whose LRAT-checking logic is **formally proven correct in HOL4**. Its acceptance of the LRAT proof (`s VERIFIED UNSAT` + exit 0) is a formal soundness guarantee. drat-trim and lrat-trim are corroboration; cake_lpr is the trust anchor. All gates are fail-closed.

Result: `unsat_certificate` claims grade at **E7_FORMALLY_VERIFIED** — one formal kernel (cake_lpr/HOL4) independently verifies the proof. Adding a second independent formal system (e.g. Isabelle-verified gratchk) would lift to E8_CROSS_VERIFIED.

### Integration Lane — CAS × Lean 4 adjudication
**Status: live, kernel-verified.**

Pipeline: FriCAS Risch integration → symbolic derivative residual check (SymPy/Maxima) → Lean 4 kernel proof.

Live two-CAS scan (SymPy + Maxima) over 191 integrands found 0 net genuine CAS errors after review.
- 33 Lean 4 theorems/lemmas across core library files (CasAdjudication: 10, RischVerification: 9, RischAutoDischarge: 8, PartialFractionHasDerivAt: 2, Gf2Identity: 2, TseitinC5: 2), 0 sorry, 0 axiom. Count guarded by `tests/test_theorem_count.py`.
- First kernel-verified FriCAS Risch certificates.
- Cross-prover certificates: integration claims verified by **two independent formal kernels** (Lean 4 + Coq), reaching **E8_CROSS_VERIFIED** for caveat-free cases (bronstein_003, bronstein_004).

---

## Quick start

**Python tests only** (no external tools required):

```bash
git clone https://github.com/DustinTheismann/omniforge.git
cd omniforge
pip install -e ".[dev]"          # installs jsonschema, sympy, pyyaml, pytest
pytest tests/ backbone/ -v       # 970 tests, ~30s
```

**Full SAT lane demo** (requires build toolchain: `gcc`, `git`, `make`):

```bash
bash scripts/tools/install_sat_toolchain.sh   # builds cadical, drat-trim, lrat-trim, cake_lpr
make demo                                      # runs three-checker UNSAT pipeline
```

`make demo` produces a sealed runpack under `artifacts/` with the UNSAT certificate at E7_FORMALLY_VERIFIED.

**Lean 4 / Coq proofs**: see `.github/workflows/lean.yml` and `coq.yml` for exact toolchain setup; the proofs are checked by CI on every push.

---

## One-command demo

Runs the full three-checker SAT pipeline on a benchmark CNF, emits an `unsat_certificate` claim at E7_FORMALLY_VERIFIED, and validates the artifact bundle.

```bash
make demo
```

Produces:
- `artifacts/run_<run_id>/manifest.json`
- `artifacts/run_<run_id>/claim.json` — unsat_certificate at E7_FORMALLY_VERIFIED
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
| Evidence | `protocols/evidence_protocol/` | `grade(claim)` → E0–E11; fail-closed gates |
| Obligation | `protocols/obligation_protocol/` | Decomposes claims into checkable units |

## Contracts

- `omniforge/contracts/eval_contract.schema.json`
- `omniforge/contracts/artifact_manifest.schema.json`

## Toolchain pins

`tools/toolchain.lock.json` pins every checker to an exact git commit SHA, verified via `git ls-remote` against the canonical repository — never scraped from web pages.
