PY=python3

.PHONY: demo
demo:
	$(PY) -m omniforge.cli demo

.PHONY: reproduce
reproduce:
	@if [ -z "$(RUN_ID)" ]; then echo "RUN_ID required"; exit 1; fi
	$(PY) -m omniforge.cli reproduce --run-id $(RUN_ID)

.PHONY: validate-contracts
validate-contracts:
	$(PY) -m omniforge.cli validate-contracts

# E9 SAT anchor: re-check the gf2 tautology refutation with cake_lpr (HOL4).
.PHONY: gf2
gf2:
	$(PY) -m omniforge.cli verify-cnf --cnf benches/multimethod/gf2_tautology.cnf --expect-unsat

# E9 (non-toy) SAT anchor: re-check the Tseitin C5 refutation with cake_lpr.
.PHONY: tseitin
tseitin:
	$(PY) -m omniforge.cli verify-cnf --cnf benches/multimethod/tseitin_c5.cnf --expect-unsat

# Typeset the paper (needs pandoc + a LaTeX toolchain; CI builds it in paper.yml).
.PHONY: paper
paper:
	bash paper/build_pdf.sh

.PHONY: validate-protocols
validate-protocols:
	$(PY) -m pytest tests/test_claim_protocol.py tests/test_runpack_protocol.py tests/test_evidence_grader.py -v --tb=short

.PHONY: validate-backbone
validate-backbone:
	$(PY) -m pytest backbone/tests/ -v --tb=short

.PHONY: test-all
test-all: validate-backbone validate-protocols
