"""
Tests for ProofForge Ω Tier 4: obligation protocol, transmutation engine,
and the cross-claim dependency graph.

Run with:  python -m pytest tests/test_proofforge_tier4.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from protocols.obligation_protocol import (
    Obligation,
    ObligationStatus,
    build_obligation_graph,
    discharge,
    obligations_for_claim,
    verify_obligation_artifact,
)
from protocols.transmute import transmute, transmute_all
from protocols.claim_protocol.depgraph import build_depgraph

_EX = Path(__file__).parent.parent / "protocols" / "claim_protocol" / "examples"


def _claims() -> list[dict]:
    return [json.loads((_EX / f"risch_bronstein_{n:03d}.json").read_text())
            for n in range(1, 10)]


# ---------------------------------------------------------------------------
# Obligation protocol
# ---------------------------------------------------------------------------

def test_obligations_one_per_formal_target():
    claim = _claims()[0]
    obs = obligations_for_claim(claim)
    assert len(obs) >= 1
    assert all(isinstance(o, Obligation) for o in obs)


def test_obligation_id_namespaced_by_claim():
    claim = _claims()[0]
    obs = obligations_for_claim(claim)
    assert obs[0].obligation_id.startswith("ob.pf.integral.bronstein_001")


def test_obligation_default_status_pending():
    obs = obligations_for_claim(_claims()[2])
    assert obs[0].status == ObligationStatus.PENDING.value


def test_obligation_checker_is_lean():
    obs = obligations_for_claim(_claims()[2])
    assert "lean4" in obs[0].checker


def test_build_obligation_graph_covers_all_claims():
    g = build_obligation_graph(_claims())
    assert len(g["by_claim"]) == 9
    assert len(g["obligations"]) >= 9


def test_verify_artifact_pending_is_false():
    obs = obligations_for_claim(_claims()[0])
    assert verify_obligation_artifact(obs[0]) is False


def test_discharge_against_real_artifact():
    """Discharge an obligation against the committed RischVerification.lean."""
    obs = obligations_for_claim(_claims()[0])
    discharged = discharge(obs[0], artifact="fricas_bridge/RischVerification.lean")
    assert discharged.status == ObligationStatus.DISCHARGED.value
    assert discharged.discharge_hash is not None
    assert len(discharged.discharge_hash) == 64
    assert verify_obligation_artifact(discharged) is True


def test_discharge_hash_detects_tampering():
    obs = obligations_for_claim(_claims()[0])
    discharged = discharge(obs[0], artifact="fricas_bridge/RischVerification.lean")
    # Corrupt the recorded hash → verification fails.
    tampered = Obligation(
        obligation_id=discharged.obligation_id,
        claim_id=discharged.claim_id,
        statement=discharged.statement,
        checker=discharged.checker,
        status=discharged.status,
        discharge_artifact=discharged.discharge_artifact,
        discharge_hash="0" * 64,
    )
    assert verify_obligation_artifact(tampered) is False


# ---------------------------------------------------------------------------
# Transmutation engine
# ---------------------------------------------------------------------------

def test_transmute_single_claim_reaches_e7():
    claim = _claims()[0]
    result = transmute(claim)
    assert result.evidence_class == "E7_FORMALLY_VERIFIED"


def test_transmute_all_nine_reach_e7():
    results = transmute_all(_claims())
    assert len(results) == 9
    assert all(r.evidence_class == "E7_FORMALLY_VERIFIED" for r in results)


def test_transmute_discharges_obligations():
    result = transmute(_claims()[2])
    assert result.all_discharged
    assert result.n_discharged == len(result.obligations)


def test_transmute_pending_when_no_formal_pass():
    """A claim with no formal_verified checker_result should not auto-discharge."""
    bare = {
        "claim_id": "pf.test.bare",
        "formal_targets": [{"name": "t", "statement_text": "True", "backend": "lean4"}],
        "checker_results": [],
        "source": {"kind": "test", "name": "unit"},
    }
    result = transmute(bare)
    assert result.n_discharged == 0
    assert result.evidence_class != "E7_FORMALLY_VERIFIED"


def test_transmute_does_not_mutate_claim():
    claim = _claims()[0]
    before = json.dumps(claim, sort_keys=True)
    transmute(claim)
    assert json.dumps(claim, sort_keys=True) == before


# ---------------------------------------------------------------------------
# Dependency graph
# ---------------------------------------------------------------------------

def test_depgraph_nine_nodes():
    dg = build_depgraph(_claims())
    assert len(dg.nodes) == 9


def test_depgraph_acyclic():
    dg = build_depgraph(_claims())
    assert dg.has_cycle() is False


def test_depgraph_topological_order_complete():
    dg = build_depgraph(_claims())
    order = dg.topological_order()
    assert set(order) == dg.nodes
    assert len(order) == 9


def test_depgraph_explicit_depends_on():
    claims = [
        {"claim_id": "a", "formal_targets": []},
        {"claim_id": "b", "depends_on": ["a"], "formal_targets": []},
    ]
    dg = build_depgraph(claims)
    assert "a" in dg.edges["b"]
    order = dg.topological_order()
    assert order.index("a") < order.index("b")


def test_depgraph_dependents_of():
    claims = [
        {"claim_id": "a", "formal_targets": []},
        {"claim_id": "b", "depends_on": ["a"], "formal_targets": []},
        {"claim_id": "c", "depends_on": ["b"], "formal_targets": []},
    ]
    dg = build_depgraph(claims)
    assert dg.dependents_of("a") == {"b", "c"}


def test_depgraph_cycle_detected():
    claims = [
        {"claim_id": "a", "depends_on": ["b"], "formal_targets": []},
        {"claim_id": "b", "depends_on": ["a"], "formal_targets": []},
    ]
    dg = build_depgraph(claims)
    assert dg.has_cycle() is True
    with pytest.raises(ValueError):
        dg.topological_order()
