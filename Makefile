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
