"""
Prep Lineage — Cross-flow lineage graph for Tableau Prep portfolios.

Builds a global DAG connecting multiple Prep flows by matching
one flow's outputs to another flow's inputs via fingerprinting.
Detects chains, fan-out/fan-in, external sources, and final sinks.

Usage::

    from powerbi_import.prep_lineage import build_lineage_graph

    graph = build_lineage_graph(profiles)  # List[FlowProfile]
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from prep_flow_analyzer import FlowProfile, FlowInput, FlowOutput
except ImportError:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))
    from prep_flow_analyzer import FlowProfile, FlowInput, FlowOutput


# ═══════════════════════════════════════════════════════════════════════════════
#  DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class LineageEdge:
    """A cross-flow connection: one flow's output feeds another flow's input."""
    source_flow: str
    source_output: str
    target_flow: str
    target_input: str
    match_type: str        # 'exact', 'table_name', 'published_ds', 'fuzzy'
    confidence: float = 1.0

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class SourceEndpoint:
    """An external source (not produced by any flow in the portfolio)."""
    fingerprint: str
    connection_type: str
    server: str = ''
    database: str = ''
    table_name: str = ''
    filename: str = ''
    consumed_by: List[Tuple[str, str]] = field(default_factory=list)  # [(flow, input)]

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d['consumed_by'] = [{'flow': f, 'input': i} for f, i in self.consumed_by]
        return d


@dataclass
class SinkEndpoint:
    """A final output (not consumed by any flow in the portfolio)."""
    fingerprint: str
    output_type: str = ''
    target_table: str = ''
    target_filename: str = ''
    produced_by: Tuple[str, str] = ('', '')  # (flow, output)

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d['produced_by'] = {'flow': self.produced_by[0], 'output': self.produced_by[1]}
        return d


@dataclass
class PrepLineageGraph:
    """Cross-flow lineage for the entire Prep portfolio."""
    flows: List[FlowProfile] = field(default_factory=list)
    edges: List[LineageEdge] = field(default_factory=list)
    external_sources: List[SourceEndpoint] = field(default_factory=list)
    final_sinks: List[SinkEndpoint] = field(default_factory=list)
    layers: List[List[str]] = field(default_factory=list)
    isolated_flows: List[str] = field(default_factory=list)
    chains: List[List[str]] = field(default_factory=list)

    @property
    def total_flows(self) -> int:
        return len(self.flows)

    @property
    def total_sources(self) -> int:
        return len(self.external_sources)

    @property
    def total_outputs(self) -> int:
        return len(self.final_sinks)

    @property
    def total_transforms(self) -> int:
        return sum(len(f.transforms) for f in self.flows)

    @property
    def total_cross_flow_edges(self) -> int:
        return len(self.edges)

    @property
    def max_chain_depth(self) -> int:
        return max((len(c) for c in self.chains), default=0)

    def to_dict(self) -> dict:
        return {
            'total_flows': self.total_flows,
            'total_sources': self.total_sources,
            'total_outputs': self.total_outputs,
            'total_transforms': self.total_transforms,
            'total_cross_flow_edges': self.total_cross_flow_edges,
            'max_chain_depth': self.max_chain_depth,
            'flows': [f.to_dict() for f in self.flows],
            'edges': [e.to_dict() for e in self.edges],
            'external_sources': [s.to_dict() for s in self.external_sources],
            'final_sinks': [s.to_dict() for s in self.final_sinks],
            'layers': self.layers,
            'isolated_flows': self.isolated_flows,
            'chains': self.chains,
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  MATCHING LOGIC
# ═══════════════════════════════════════════════════════════════════════════════

def _normalize_name(name: str) -> str:
    """Normalize a name for fuzzy comparison."""
    return name.lower().replace(' ', '_').replace('-', '_').strip()


def _fuzzy_match_name(a: str, b: str) -> float:
    """Name similarity score (0.0–1.0) using character overlap."""
    na, nb = _normalize_name(a), _normalize_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    # Substring match
    if na in nb or nb in na:
        return 0.8
    # Character-level Jaccard
    sa, sb = set(na), set(nb)
    intersection = sa & sb
    union = sa | sb
    return len(intersection) / len(union) if union else 0.0


def _match_outputs_to_inputs(profiles: List[FlowProfile]) -> List[LineageEdge]:
    """Match outputs of each flow to inputs of other flows."""
    edges: List[LineageEdge] = []

    # Build index: fingerprint → [(flow_name, output)]
    output_index: Dict[str, List[Tuple[str, FlowOutput]]] = {}
    output_names: Dict[str, List[Tuple[str, FlowOutput]]] = {}  # normalized name → entries

    for prof in profiles:
        for out in prof.outputs:
            output_index.setdefault(out.fingerprint, []).append((prof.name, out))
            nname = _normalize_name(out.name)
            output_names.setdefault(nname, []).append((prof.name, out))
            # Also index by target_table
            if out.target_table:
                tn = _normalize_name(out.target_table)
                output_names.setdefault(tn, []).append((prof.name, out))

    matched_inputs: set = set()  # (flow_name, input_node_id)

    for prof in profiles:
        for inp in prof.inputs:
            key = (prof.name, inp.node_id)

            # 1. Exact fingerprint match
            if inp.fingerprint in output_index:
                for src_flow, src_out in output_index[inp.fingerprint]:
                    if src_flow != prof.name:
                        edges.append(LineageEdge(
                            source_flow=src_flow,
                            source_output=src_out.name,
                            target_flow=prof.name,
                            target_input=inp.name,
                            match_type='exact',
                            confidence=1.0,
                        ))
                        matched_inputs.add(key)

            # 2. Published datasource name match
            if key not in matched_inputs and inp.connection_type in ('published', 'publisheddatasource'):
                inp_norm = _normalize_name(inp.name)
                if inp_norm in output_names:
                    for src_flow, src_out in output_names[inp_norm]:
                        if src_flow != prof.name:
                            edges.append(LineageEdge(
                                source_flow=src_flow,
                                source_output=src_out.name,
                                target_flow=prof.name,
                                target_input=inp.name,
                                match_type='published_ds',
                                confidence=0.9,
                            ))
                            matched_inputs.add(key)

            # 3. Table name match (same table name, different server)
            if key not in matched_inputs and inp.table_name:
                inp_norm = _normalize_name(inp.table_name)
                if inp_norm in output_names:
                    for src_flow, src_out in output_names[inp_norm]:
                        if src_flow != prof.name:
                            edges.append(LineageEdge(
                                source_flow=src_flow,
                                source_output=src_out.name,
                                target_flow=prof.name,
                                target_input=inp.name,
                                match_type='table_name',
                                confidence=0.8,
                            ))
                            matched_inputs.add(key)

            # 4. Fuzzy name match
            if key not in matched_inputs:
                best_score = 0.0
                best_match: Optional[Tuple[str, FlowOutput]] = None
                for other in profiles:
                    if other.name == prof.name:
                        continue
                    for out in other.outputs:
                        score = _fuzzy_match_name(inp.name, out.name)
                        if score > best_score:
                            best_score = score
                            best_match = (other.name, out)
                if best_match and best_score >= 0.7:
                    edges.append(LineageEdge(
                        source_flow=best_match[0],
                        source_output=best_match[1].name,
                        target_flow=prof.name,
                        target_input=inp.name,
                        match_type='fuzzy',
                        confidence=round(best_score, 2),
                    ))
                    matched_inputs.add(key)

    # Deduplicate edges (same output indexed under both name and target_table)
    seen: set = set()
    unique_edges: List[LineageEdge] = []
    for e in edges:
        ekey = (e.source_flow, e.target_flow, e.source_output, e.target_input, e.match_type)
        if ekey not in seen:
            seen.add(ekey)
            unique_edges.append(e)
    return unique_edges


def _identify_external_sources(profiles: List[FlowProfile],
                               edges: List[LineageEdge]) -> List[SourceEndpoint]:
    """Sources not produced by any flow in the portfolio."""
    # Collect all input fingerprints that are matched by an edge
    fed_inputs: set = set()
    for e in edges:
        fed_inputs.add((_normalize_name(e.target_flow), _normalize_name(e.target_input)))

    # Group inputs by fingerprint
    fp_map: Dict[str, SourceEndpoint] = {}
    for prof in profiles:
        for inp in prof.inputs:
            key = (_normalize_name(prof.name), _normalize_name(inp.name))
            if key in fed_inputs:
                continue
            if inp.fingerprint not in fp_map:
                fp_map[inp.fingerprint] = SourceEndpoint(
                    fingerprint=inp.fingerprint,
                    connection_type=inp.connection_type,
                    server=inp.server,
                    database=inp.database,
                    table_name=inp.table_name,
                    filename=inp.filename,
                )
            fp_map[inp.fingerprint].consumed_by.append((prof.name, inp.name))

    return list(fp_map.values())


def _identify_final_sinks(profiles: List[FlowProfile],
                          edges: List[LineageEdge]) -> List[SinkEndpoint]:
    """Outputs not consumed by any flow in the portfolio."""
    # Collect all output names that feed an edge
    feeding_outputs: set = set()
    for e in edges:
        feeding_outputs.add((_normalize_name(e.source_flow), _normalize_name(e.source_output)))

    sinks = []
    for prof in profiles:
        for out in prof.outputs:
            key = (_normalize_name(prof.name), _normalize_name(out.name))
            if key not in feeding_outputs:
                sinks.append(SinkEndpoint(
                    fingerprint=out.fingerprint,
                    output_type=out.output_type,
                    target_table=out.target_table,
                    target_filename=out.target_filename,
                    produced_by=(prof.name, out.name),
                ))
    return sinks


def _compute_flow_layers(profiles: List[FlowProfile],
                         edges: List[LineageEdge]) -> List[List[str]]:
    """Topological layering of flows for visualization."""
    flow_names = {p.name for p in profiles}
    # Build adjacency
    graph: Dict[str, List[str]] = {n: [] for n in flow_names}
    in_degree: Dict[str, int] = {n: 0 for n in flow_names}

    for e in edges:
        if e.source_flow in flow_names and e.target_flow in flow_names:
            graph[e.source_flow].append(e.target_flow)
            in_degree[e.target_flow] = in_degree.get(e.target_flow, 0) + 1

    # BFS layer assignment
    layers: List[List[str]] = []
    queue = [n for n, deg in in_degree.items() if deg == 0]

    while queue:
        layers.append(sorted(queue))
        next_queue = []
        for n in queue:
            for child in graph.get(n, []):
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    next_queue.append(child)
        queue = next_queue

    return layers


def _detect_chains(profiles: List[FlowProfile],
                   edges: List[LineageEdge]) -> List[List[str]]:
    """Find linear flow chains (A→B→C with no fan-out/fan-in)."""
    flow_names = {p.name for p in profiles}
    # out_degree and in_degree per flow (counting distinct connected flows)
    out_targets: Dict[str, set] = {n: set() for n in flow_names}
    in_sources: Dict[str, set] = {n: set() for n in flow_names}

    for e in edges:
        if e.source_flow in flow_names and e.target_flow in flow_names:
            out_targets[e.source_flow].add(e.target_flow)
            in_sources[e.target_flow].add(e.source_flow)

    # A chain start: out_degree=1, in_degree=0 or in_degree>1 (not single-in)
    # Actually: chain is a maximal path where each node has exactly 1 successor and 1 predecessor
    visited: set = set()
    chains: List[List[str]] = []

    for start in flow_names:
        if start in visited:
            continue
        if len(in_sources[start]) != 0:
            continue  # not a chain start
        # Try to extend
        chain = [start]
        current = start
        while True:
            targets = out_targets.get(current, set())
            if len(targets) != 1:
                break
            nxt = next(iter(targets))
            if len(in_sources.get(nxt, set())) != 1:
                break
            chain.append(nxt)
            current = nxt
        if len(chain) >= 2:
            chains.append(chain)
            visited.update(chain)

    return chains


def _find_isolated_flows(profiles: List[FlowProfile],
                         edges: List[LineageEdge]) -> List[str]:
    """Flows with no cross-flow edges."""
    connected = set()
    for e in edges:
        connected.add(e.source_flow)
        connected.add(e.target_flow)
    return sorted(p.name for p in profiles if p.name not in connected)


# ═══════════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

def build_lineage_graph(profiles: List[FlowProfile]) -> PrepLineageGraph:
    """Build the cross-flow lineage graph from analysed flow profiles.

    Args:
        profiles: List of FlowProfile objects from analyze_flow()

    Returns:
        PrepLineageGraph with edges, sources, sinks, layers, chains
    """
    edges = _match_outputs_to_inputs(profiles)
    external_sources = _identify_external_sources(profiles, edges)
    final_sinks = _identify_final_sinks(profiles, edges)
    layers = _compute_flow_layers(profiles, edges)
    chains = _detect_chains(profiles, edges)
    isolated = _find_isolated_flows(profiles, edges)

    return PrepLineageGraph(
        flows=profiles,
        edges=edges,
        external_sources=external_sources,
        final_sinks=final_sinks,
        layers=layers,
        isolated_flows=isolated,
        chains=chains,
    )
