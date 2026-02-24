# OmniForge / ProofForge — Verifiable Algorithm Foundry (v0.2-seed)

This repository is a minimal, publishable seed for a **lane-based algorithm foundry**.
It treats "improvement" as an engineering artifact: controlled evaluation + fail-closed gates + replayable run bundles.

## What is different
- **Fail-closed**: a claim is rejected if required evidence is missing or invalid.
- **Controlled eval contract**: resources and determinism are explicit and machine-checked.
- **Artifact-first**: every run emits a hashable bundle with a manifest.

## Lanes (seed)
- SAT Lane: placeholder executor (wiring points are present).
- Correctness Lane: placeholder (wiring points are present).
- Proof Lane: contract supports UNSAT proof requirements (plumbing to be connected to a real solver).

## One-command demo
Creates a run bundle under `artifacts/` and validates it against the artifact manifest schema.

```bash
make demo
```

You should see a printed `run_id` and an artifact bundle at:

- `artifacts/run_<run_id>/manifest.json`
- `artifacts/run_<run_id>/stdout.txt`
- `artifacts/run_<run_id>/stderr.txt`

## Validate contracts (CI does this)
```bash
make validate-contracts
```

## Reproduce a run (verify hashes)
```bash
make reproduce RUN_ID=<run_id>
```

## Contracts
- `omniforge/contracts/eval_contract.schema.json`
- `omniforge/contracts/artifact_manifest.schema.json`

## Notes
This is intentionally small. The next step is to swap the placeholder executor with a real solver and wire in:
- BenchExec (or equivalent) sandboxing
- solver proof logs for UNSAT
- external proof checking (fail-closed)
