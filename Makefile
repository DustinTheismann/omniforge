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

.PHONY: validate-protocols
validate-protocols:
	$(PY) -m pytest tests/test_claim_protocol.py tests/test_runpack_protocol.py tests/test_evidence_grader.py -v --tb=short

.PHONY: validate-backbone
validate-backbone:
	$(PY) -m pytest backbone/tests/ -v --tb=short

.PHONY: test-all
test-all: validate-backbone validate-protocols
