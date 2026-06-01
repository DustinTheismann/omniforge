"""
ProofForge Ω — Cross-claim Dependency Graph (Tier 4.5).

Claims cite claims: the equational corollary (bronstein_002) depends on the
flagship HasDerivAt theorem (bronstein_001).  This module builds the DAG, detects
cycles, and topologically orders obligation dispatch.

Dependencies are read from a claim's ``depends_on`` list when present, and
otherwise inferred from cross-references in formal_targets (a statement that
mentions another claim's theorem name or the shared `antiderivative`/`integrand`
definitions).

Public API
----------
build_depgraph(claims)          → DepGraph
DepGraph.topological_order()    → list[str]   (raises on cycle)
DepGraph.has_cycle()            → bool
DepGraph.dependents_of(cid)     → set[str]
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DepGraph:
    nodes: set[str]
    edges: dict[str, set[str]]          # cid → set of claim_ids it depends on

    def has_cycle(self) -> bool:
        WHITE, GREY, BLACK = 0, 1, 2
        color = {n: WHITE for n in self.nodes}

        def visit(n: str) -> bool:
            color[n] = GREY
            for m in self.edges.get(n, set()):
                if m not in color:
                    continue
                if color[m] == GREY:
                    return True
                if color[m] == WHITE and visit(m):
                    return True
            color[n] = BLACK
            return False

        return any(color[n] == WHITE and visit(n) for n in self.nodes)

    def topological_order(self) -> list[str]:
        """Dependencies first.  Raises ValueError on a cycle."""
        if self.has_cycle():
            raise ValueError("dependency graph has a cycle")
        order: list[str] = []
        seen: set[str] = set()

        def visit(n: str) -> None:
            if n in seen:
                return
            seen.add(n)
            for m in sorted(self.edges.get(n, set())):
                if m in self.nodes:
                    visit(m)
            order.append(n)

        for n in sorted(self.nodes):
            visit(n)
        return order

    def dependents_of(self, claim_id: str) -> set[str]:
        """Return every claim that (transitively) depends on claim_id."""
        result: set[str] = set()
        stack = [claim_id]
        while stack:
            cur = stack.pop()
            for n in self.nodes:
                if cur in self.edges.get(n, set()) and n not in result:
                    result.add(n)
                    stack.append(n)
        return result


def _claim_id(claim: dict) -> str:
    return claim.get("claim_id") or claim.get("id") or "unknown"


def _infer_edges(claim: dict, all_ids: set[str], name_to_id: dict[str, str]) -> set[str]:
    """Infer dependency edges for one claim."""
    cid = _claim_id(claim)
    deps: set[str] = set()

    # Explicit dependencies win.
    for d in claim.get("depends_on", []):
        if d in all_ids and d != cid:
            deps.add(d)

    # Inference: a formal_target that references another claim's theorem name.
    for tgt in claim.get("formal_targets", []):
        stmt = tgt.get("statement_text", "")
        for name, other_id in name_to_id.items():
            if other_id == cid:
                continue
            # the equational corollary references the shared defs of 001
            if name and name in stmt:
                deps.add(other_id)

    return deps


def build_depgraph(claims: list[dict]) -> DepGraph:
    """Construct the dependency DAG over a list of claim dicts."""
    nodes = {_claim_id(c) for c in claims}

    # Map theorem names → claim_id for cross-reference inference.
    name_to_id: dict[str, str] = {}
    for c in claims:
        cid = _claim_id(c)
        for tgt in c.get("formal_targets", []):
            nm = tgt.get("name")
            if nm:
                name_to_id[nm] = cid

    edges: dict[str, set[str]] = {}
    for c in claims:
        cid = _claim_id(c)
        edges[cid] = _infer_edges(c, nodes, name_to_id)
    return DepGraph(nodes=nodes, edges=edges)
