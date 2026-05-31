"""
Claim protocol validator.

Usage:
    from protocols.claim_protocol.validate import validate_claim, ClaimValidationError

    errors = validate_claim(claim_dict)
    if errors:
        raise ClaimValidationError(errors)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema import Draft202012Validator

_SCHEMA_PATH = Path(__file__).parent / "schema.json"
_schema: dict | None = None


def _load_schema() -> dict:
    global _schema
    if _schema is None:
        _schema = json.loads(_SCHEMA_PATH.read_text())
    return _schema


class ClaimValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))


def validate_claim(claim: dict[str, Any], *, raise_on_error: bool = False) -> list[str]:
    """
    Validate *claim* against the claim protocol schema.

    Returns a list of error strings (empty on success).
    If *raise_on_error* is True, raises ClaimValidationError on any error.
    """
    schema = _load_schema()
    validator = Draft202012Validator(schema)
    errors = [
        f"{'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in validator.iter_errors(claim)
    ]
    if errors and raise_on_error:
        raise ClaimValidationError(errors)
    return errors


def validate_claim_file(path: Path, *, raise_on_error: bool = False) -> list[str]:
    """Load a JSON file and validate it as a claim."""
    claim = json.loads(path.read_text())
    return validate_claim(claim, raise_on_error=raise_on_error)


def validate_claim_batch(claims: list[dict]) -> dict[str, list[str]]:
    """
    Validate a list of claim dicts.
    Returns {claim_id: [errors]} for every claim that has errors.
    """
    results: dict[str, list[str]] = {}
    for claim in claims:
        cid = claim.get("claim_id", "<unknown>")
        errors = validate_claim(claim)
        if errors:
            results[cid] = errors
    return results
