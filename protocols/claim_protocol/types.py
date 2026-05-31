"""
Typed Python representations for ProofForge claim protocol objects.

These dataclasses mirror the JSON Schema in schema.json.
Use ``ClaimValidator`` to validate raw dicts; use these types for typed access.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class ClaimType(str, Enum):
    SYMBOLIC_ANTIDERIVATIVE = "symbolic_antiderivative"
    ALGEBRAIC_IDENTITY      = "algebraic_identity"
    THEOREM_STATEMENT       = "theorem_statement"
    ALGORITHM_BENCHMARK     = "algorithm_benchmark"
    NUMERICAL_EXPERIMENT    = "numerical_experiment"
    PAPER_CLAIM             = "paper_claim"
    SIMULATION_RESULT       = "simulation_result"
    CODE_CORRECTNESS        = "code_correctness"


class EvidenceClass(str, Enum):
    E0_RAW_CLAIM             = "E0_RAW_CLAIM"
    E1_SOURCED               = "E1_SOURCED"
    E2_PARSED                = "E2_PARSED"
    E3_EXECUTABLE            = "E3_EXECUTABLE"
    E4_REPRODUCED            = "E4_REPRODUCED"
    E5_NUMERICALLY_SUPPORTED = "E5_NUMERICALLY_SUPPORTED"
    E6_SYMBOLICALLY_SUPPORTED= "E6_SYMBOLICALLY_SUPPORTED"
    E7_FORMALLY_VERIFIED     = "E7_FORMALLY_VERIFIED"
    E8_CROSS_VERIFIED        = "E8_CROSS_VERIFIED"
    E9_ADVERSARIALLY_HARDENED= "E9_ADVERSARIALLY_HARDENED"
    E10_FIELD_VALIDATED      = "E10_FIELD_VALIDATED"
    EX_REFUTED               = "EX_REFUTED"

    @property
    def level(self) -> int:
        _levels = {
            "E0_RAW_CLAIM": 0, "E1_SOURCED": 1, "E2_PARSED": 2,
            "E3_EXECUTABLE": 3, "E4_REPRODUCED": 4,
            "E5_NUMERICALLY_SUPPORTED": 5, "E6_SYMBOLICALLY_SUPPORTED": 6,
            "E7_FORMALLY_VERIFIED": 7, "E8_CROSS_VERIFIED": 8,
            "E9_ADVERSARIALLY_HARDENED": 9, "E10_FIELD_VALIDATED": 10,
            "EX_REFUTED": -1,
        }
        return _levels.get(self.value, -99)

    def can_upgrade_to(self, target: "EvidenceClass") -> bool:
        if self == EvidenceClass.EX_REFUTED:
            return False
        if target == EvidenceClass.EX_REFUTED:
            return True
        return target.level == self.level + 1


class ClaimFlag(str, Enum):
    REQUIRES_ASSUMPTIONS   = "REQUIRES_ASSUMPTIONS"
    CHECKER_DISAGREEMENT   = "CHECKER_DISAGREEMENT"
    MISSING_LEMMA          = "MISSING_LEMMA"
    TRANSLATION_FAILURE    = "TRANSLATION_FAILURE"
    SUSPECTED_CAS_BUG      = "SUSPECTED_CAS_BUG"
    HUMAN_REVIEW_REQUIRED  = "HUMAN_REVIEW_REQUIRED"
    INCOMPLETE_PROOF       = "INCOMPLETE_PROOF"
    NONREPRODUCIBLE        = "NONREPRODUCIBLE"
    OVERCLAIMING_RISK      = "OVERCLAIMING_RISK"


# ---------------------------------------------------------------------------
# Sub-objects
# ---------------------------------------------------------------------------

@dataclass
class ClaimSource:
    kind:        str
    name:        Optional[str] = None
    version:     Optional[str] = None
    url:         Optional[str] = None
    doi:         Optional[str] = None
    source_hash: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> "ClaimSource":
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})


@dataclass
class FormalTarget:
    system:          str
    status:          str
    statement_file:  Optional[str] = None
    statement_text:  Optional[str] = None
    checker_version: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> "FormalTarget":
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})


@dataclass
class Assumption:
    kind:        str
    statement:   str
    required_by: Optional[str] = None
    discharged:  bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "Assumption":
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})


@dataclass
class Obligation:
    obligation_id: str
    kind:          str
    status:        str
    checker:       Optional[str] = None
    artifact:      Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> "Obligation":
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})


@dataclass
class CheckerResult:
    checker:         str
    result:          str
    checker_version: Optional[str] = None
    formal_verified: bool = False
    artifact:        Optional[str] = None
    elapsed_ms:      Optional[float] = None
    notes:           Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> "CheckerResult":
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Top-level Claim
# ---------------------------------------------------------------------------

@dataclass
class Claim:
    claim_id:        str
    claim_type:      ClaimType
    natural_language:str
    source:          ClaimSource
    title:           str = ""
    inputs:          dict[str, Any] = field(default_factory=dict)
    outputs:         dict[str, Any] = field(default_factory=dict)
    formal_targets:  list[FormalTarget] = field(default_factory=list)
    assumptions:     list[Assumption]   = field(default_factory=list)
    obligations:     list[Obligation]   = field(default_factory=list)
    checker_results: list[CheckerResult]= field(default_factory=list)
    evidence_class:  EvidenceClass = EvidenceClass.E0_RAW_CLAIM
    flags:           list[ClaimFlag] = field(default_factory=list)
    artifacts:       dict[str, Any] = field(default_factory=dict)
    metadata:        dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "Claim":
        return cls(
            claim_id         = d["claim_id"],
            claim_type       = ClaimType(d["claim_type"]),
            natural_language = d["natural_language"],
            source           = ClaimSource.from_dict(d["source"]),
            title            = d.get("title", ""),
            inputs           = d.get("inputs", {}),
            outputs          = d.get("outputs", {}),
            formal_targets   = [FormalTarget.from_dict(t) for t in d.get("formal_targets", [])],
            assumptions      = [Assumption.from_dict(a) for a in d.get("assumptions", [])],
            obligations      = [Obligation.from_dict(o) for o in d.get("obligations", [])],
            checker_results  = [CheckerResult.from_dict(r) for r in d.get("checker_results", [])],
            evidence_class   = EvidenceClass(d.get("evidence_class", "E0_RAW_CLAIM")),
            flags            = [ClaimFlag(f) for f in d.get("flags", [])],
            artifacts        = d.get("artifacts", {}),
            metadata         = d.get("metadata", {}),
        )

    def to_dict(self) -> dict:
        return {
            "claim_id":         self.claim_id,
            "claim_type":       self.claim_type.value,
            "natural_language": self.natural_language,
            "title":            self.title,
            "source":           self.source.__dict__,
            "inputs":           self.inputs,
            "outputs":          self.outputs,
            "formal_targets":   [t.__dict__ for t in self.formal_targets],
            "assumptions":      [a.__dict__ for a in self.assumptions],
            "obligations":      [o.__dict__ for o in self.obligations],
            "checker_results":  [r.__dict__ for r in self.checker_results],
            "evidence_class":   self.evidence_class.value,
            "flags":            [f.value for f in self.flags],
            "artifacts":        self.artifacts,
            "metadata":         self.metadata,
        }
