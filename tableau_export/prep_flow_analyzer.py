"""
Prep Flow Analyzer — Per-flow metadata extraction for lineage analysis.

Parses individual .tfl/.tflx files and extracts structured metadata:
inputs (sources), outputs (destinations), transforms, DAG statistics,
and complexity signals. Produces FlowProfile objects used by the
cross-flow lineage engine (prep_lineage.py).

Usage::

    from prep_flow_analyzer import analyze_flow, analyze_flows_bulk

    profile = analyze_flow("path/to/flow.tfl")
    profiles = analyze_flows_bulk("path/to/flows/")
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from prep_flow_parser import (
    read_prep_flow,
    _get_node_type,
    _topological_sort,
    _find_upstream_nodes,
    _PREP_CONNECTION_MAP,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
#  DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

def _fingerprint(*parts: str) -> str:
    """SHA-256 fingerprint from normalized parts."""
    raw = '\x00'.join(p.lower().strip() for p in parts)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]


@dataclass
class FlowInput:
    """A source feeding into a Prep flow."""
    node_id: str
    name: str
    connection_type: str
    server: str = ''
    database: str = ''
    schema: str = ''
    table_name: str = ''
    filename: str = ''
    column_count: int = 0
    column_names: List[str] = field(default_factory=list)
    fingerprint: str = ''

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class FlowOutput:
    """A destination produced by a Prep flow."""
    node_id: str
    name: str
    output_type: str = ''
    target_server: str = ''
    target_database: str = ''
    target_table: str = ''
    target_filename: str = ''
    column_count: int = 0
    column_names: List[str] = field(default_factory=list)
    fingerprint: str = ''

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class FlowTransform:
    """A transformation step inside a Prep flow."""
    node_id: str
    name: str
    transform_type: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class FlowProfile:
    """Complete metadata for one Tableau Prep flow."""
    name: str
    file_path: str
    inputs: List[FlowInput] = field(default_factory=list)
    outputs: List[FlowOutput] = field(default_factory=list)
    transforms: List[FlowTransform] = field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0
    dag_depth: int = 0
    join_count: int = 0
    union_count: int = 0
    script_count: int = 0
    calc_count: int = 0
    node_graph: Dict[str, List[str]] = field(default_factory=dict)

    @property
    def complexity_score(self) -> int:
        """Weighted complexity: joins×3 + unions×2 + scripts×5 + calcs×1 + nodes×0.5."""
        return int(
            self.join_count * 3
            + self.union_count * 2
            + self.script_count * 5
            + self.calc_count * 1
            + self.node_count * 0.5
        )

    @property
    def complexity_label(self) -> str:
        s = self.complexity_score
        if s <= 10:
            return 'Low'
        if s <= 30:
            return 'Medium'
        return 'High'

    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'file_path': self.file_path,
            'inputs': [i.to_dict() for i in self.inputs],
            'outputs': [o.to_dict() for o in self.outputs],
            'transforms': [t.to_dict() for t in self.transforms],
            'node_count': self.node_count,
            'edge_count': self.edge_count,
            'dag_depth': self.dag_depth,
            'join_count': self.join_count,
            'union_count': self.union_count,
            'script_count': self.script_count,
            'calc_count': self.calc_count,
            'complexity_score': self.complexity_score,
            'complexity_label': self.complexity_label,
            'node_graph': self.node_graph,
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  EXTRACTION HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_inputs(nodes: dict, connections: dict) -> List[FlowInput]:
    """Collect all input nodes from the flow."""
    inputs = []
    for nid, node in nodes.items():
        if node.get('baseType') != 'input':
            continue

        conn_id = node.get('connectionId', '')
        conn_def = connections.get(conn_id, {})
        conn_attrs = {**conn_def.get('connectionAttributes', {}),
                      **node.get('connectionAttributes', {})}

        conn_class = conn_attrs.get('class', '').lower()
        conn_type = _PREP_CONNECTION_MAP.get(conn_class, conn_class)

        server = conn_attrs.get('server', '')
        database = conn_attrs.get('dbname', conn_attrs.get('database', ''))
        schema = conn_attrs.get('schema', '')
        table_name = conn_attrs.get('table', node.get('name', ''))
        filename = conn_attrs.get('filename', '')

        col_names = [f.get('name', '') for f in node.get('fields', [])]

        fp = _fingerprint(conn_type, server, database, schema, table_name or filename)

        inputs.append(FlowInput(
            node_id=nid,
            name=node.get('name', nid[:8]),
            connection_type=conn_type,
            server=server,
            database=database,
            schema=schema,
            table_name=table_name,
            filename=filename,
            column_count=len(col_names),
            column_names=col_names,
            fingerprint=fp,
        ))
    return inputs


def _extract_outputs(nodes: dict) -> List[FlowOutput]:
    """Collect all output nodes (and leaf nodes as fallback)."""
    outputs = []
    has_output_base = False

    for nid, node in nodes.items():
        if node.get('baseType') == 'output':
            has_output_base = True
            sem = _get_node_type(node)
            attrs = node.get('connectionAttributes', {})
            col_names = [f.get('name', '') for f in node.get('fields', [])]
            target_server = attrs.get('server', '')
            target_db = attrs.get('dbname', attrs.get('database', ''))
            target_table = attrs.get('table', node.get('name', ''))
            target_file = attrs.get('filename', '')

            fp = _fingerprint(sem, target_server, target_db, '', target_table or target_file)

            outputs.append(FlowOutput(
                node_id=nid,
                name=node.get('name', nid[:8]),
                output_type=sem,
                target_server=target_server,
                target_database=target_db,
                target_table=target_table,
                target_filename=target_file,
                column_count=len(col_names),
                column_names=col_names,
                fingerprint=fp,
            ))

    # Fallback: leaf nodes (no outgoing edges)
    if not has_output_base:
        for nid, node in nodes.items():
            if not node.get('nextNodes'):
                col_names = [f.get('name', '') for f in node.get('fields', [])]
                name = node.get('name', nid[:8])
                fp = _fingerprint('leaf', '', '', '', name)
                outputs.append(FlowOutput(
                    node_id=nid,
                    name=name,
                    output_type='LeafNode',
                    column_count=len(col_names),
                    column_names=col_names,
                    fingerprint=fp,
                ))
    return outputs


_TRANSFORM_TYPES = {
    'SuperTransform': 'Clean',
    'SuperAggregate': 'Aggregate',
    'SuperJoin': 'Join',
    'Join': 'Join',
    'SuperUnion': 'Union',
    'Union': 'Union',
    'Pivot': 'Pivot',
    'Script': 'Script',
    'RunScript': 'Script',
    'RunCommand': 'Script',
    'Prediction': 'Prediction',
    'TabPy': 'Script',
    'Einstein': 'Prediction',
    'CrossJoin': 'Join',
    'PublishedDataSource': 'PublishedDS',
    'LoadPublishedDataSource': 'PublishedDS',
}


def _extract_transforms(sorted_ids: list, nodes: dict) -> List[FlowTransform]:
    """Classify each transform step and extract action-level detail."""
    transforms = []
    for nid in sorted_ids:
        node = nodes.get(nid, {})
        if node.get('baseType') != 'transform':
            continue
        sem = _get_node_type(node)
        ttype = _TRANSFORM_TYPES.get(sem, 'Other')
        details: Dict[str, Any] = {}

        if sem == 'SuperTransform':
            actions = node.get('actions', [])
            details['action_count'] = len(actions)
            details['action_types'] = list({a.get('type', '') for a in actions})
            # Extract individual operations for retro-documentation
            operations = _extract_clean_operations(actions, node)
            if operations:
                details['operations'] = operations
        elif sem in ('SuperJoin', 'Join', 'CrossJoin'):
            details['join_type'] = node.get('joinType', 'inner')
            conditions = node.get('joinConditions', [])
            details['key_count'] = len(conditions)
            # Extract join key columns
            keys = []
            for cond in conditions:
                left = cond.get('leftField', cond.get('left', ''))
                right = cond.get('rightField', cond.get('right', ''))
                if left or right:
                    keys.append({'left': left, 'right': right})
            if keys:
                details['join_keys'] = keys
        elif sem in ('SuperAggregate',):
            details['group_fields'] = len(node.get('groupByFields', []))
            details['agg_fields'] = len(node.get('aggregateFields', []))
            # Extract group-by and aggregate column names
            gnames = [f.get('name', '') for f in node.get('groupByFields', []) if f.get('name')]
            anames = []
            for af in node.get('aggregateFields', []):
                agg = af.get('aggregation', af.get('type', ''))
                col = af.get('name', af.get('field', ''))
                anames.append(f'{agg}({col})' if agg else col)
            if gnames:
                details['group_by_columns'] = gnames
            if anames:
                details['aggregate_columns'] = anames
        elif sem == 'Pivot':
            details['pivot_type'] = node.get('pivotType', '')
        elif sem in ('Script', 'RunScript', 'TabPy', 'RunCommand'):
            details['script_type'] = node.get('scriptType', node.get('language', 'unknown'))

        # Capture input/output column names when present
        fields = node.get('fields', [])
        if fields:
            details['output_columns'] = [f.get('name', '') for f in fields if f.get('name')]

        transforms.append(FlowTransform(
            node_id=nid,
            name=node.get('name', nid[:8]),
            transform_type=ttype,
            details=details,
        ))
    return transforms


# ── Clean step operation extractor ──────────────────────────────────────────

# Map nodeType suffixes to human-readable operation categories
_ACTION_TYPE_MAP = {
    'RemoveColumns': 'remove_columns',
    'RenameColumn': 'rename_column',
    'RenameColumns': 'rename_columns',
    'ChangeDataType': 'change_type',
    'Filter': 'filter',
    'FilterValues': 'filter',
    'FilterRange': 'filter',
    'FilterCalculation': 'filter',
    'AddColumn': 'add_column',
    'ConditionalColumn': 'conditional_column',
    'calc': 'calculated_field',
    'GroupReplace': 'group_replace',
    'SplitValues': 'split',
    'MergeValues': 'merge',
    'CleanText': 'clean_text',
    'Replace': 'replace_value',
    'ReplaceValues': 'replace_value',
    'SortValues': 'sort',
}


def _extract_clean_operations(actions: list, node: dict) -> List[Dict[str, Any]]:
    """Extract individual operations from a SuperTransform's action list.

    Each operation is returned as a dict with at minimum 'type' and 'description'.
    """
    ops: List[Dict[str, Any]] = []
    for action in actions:
        # Action type can come from 'type', or 'nodeType' suffix after the last '.'
        raw_type = action.get('type', '')
        node_type = action.get('nodeType', '')
        if not raw_type and node_type:
            raw_type = node_type.rsplit('.', 1)[-1] if '.' in node_type else node_type

        op_type = _ACTION_TYPE_MAP.get(raw_type, raw_type or 'unknown')
        name = action.get('name', '')
        column = action.get('column', action.get('columnName', ''))
        expression = action.get('expression', action.get('formula', ''))

        op: Dict[str, Any] = {'type': op_type}
        if name:
            op['name'] = name
        if column:
            op['column'] = column
        if expression:
            op['expression'] = str(expression)[:200]

        # Extract columns affected from the action name (e.g., "Remove Right_Row ID + 19 more")
        if not column and name:
            op['description'] = name
        elif column and expression:
            op['description'] = f'{column} = {str(expression)[:100]}'
        elif column:
            op['description'] = f'{op_type}: {column}'
        else:
            op['description'] = name or op_type

        ops.append(op)
    return ops


def _build_node_graph(nodes: dict) -> Tuple[Dict[str, List[str]], int]:
    """Build adjacency list and count edges."""
    graph: Dict[str, List[str]] = {}
    edge_count = 0
    for nid, node in nodes.items():
        nexts = []
        for edge in node.get('nextNodes', []):
            next_id = edge.get('nextNodeId', '')
            if next_id:
                nexts.append(next_id)
                edge_count += 1
        graph[nid] = nexts
    return graph, edge_count


def _compute_dag_depth(nodes: dict) -> int:
    """Longest path from any input to any output."""
    graph: Dict[str, List[str]] = {}
    for nid, node in nodes.items():
        graph[nid] = [e.get('nextNodeId', '') for e in node.get('nextNodes', []) if e.get('nextNodeId')]

    sorted_ids = _topological_sort(nodes)
    depth: Dict[str, int] = {nid: 0 for nid in sorted_ids}

    for nid in sorted_ids:
        for next_id in graph.get(nid, []):
            if next_id in depth:
                depth[next_id] = max(depth[next_id], depth[nid] + 1)

    return max(depth.values()) if depth else 0


def _count_calcs(nodes: dict) -> int:
    """Count calculated fields across Clean steps."""
    count = 0
    for node in nodes.values():
        if node.get('baseType') == 'transform':
            for action in node.get('actions', []):
                atype = action.get('type', '')
                if atype in ('AddColumn', 'ConditionalColumn', 'calc'):
                    count += 1
    return count


# ═══════════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_flow(filepath: str) -> FlowProfile:
    """Parse one TFL/TFLX and extract full metadata.

    Args:
        filepath: Path to .tfl or .tflx file

    Returns:
        FlowProfile with inputs, outputs, transforms, DAG stats
    """
    flow = read_prep_flow(filepath)
    nodes = flow.get('nodes', {})
    connections = flow.get('connections', {})

    sorted_ids = _topological_sort(nodes)
    inputs = _extract_inputs(nodes, connections)
    outputs = _extract_outputs(nodes)
    transforms = _extract_transforms(sorted_ids, nodes)
    node_graph, edge_count = _build_node_graph(nodes)
    dag_depth = _compute_dag_depth(nodes)

    join_count = sum(1 for t in transforms if t.transform_type == 'Join')
    union_count = sum(1 for t in transforms if t.transform_type == 'Union')
    script_count = sum(1 for t in transforms if t.transform_type == 'Script')
    calc_count = _count_calcs(nodes)

    name = os.path.splitext(os.path.basename(filepath))[0]

    return FlowProfile(
        name=name,
        file_path=os.path.abspath(filepath),
        inputs=inputs,
        outputs=outputs,
        transforms=transforms,
        node_count=len(nodes),
        edge_count=edge_count,
        dag_depth=dag_depth,
        join_count=join_count,
        union_count=union_count,
        script_count=script_count,
        calc_count=calc_count,
        node_graph=node_graph,
    )


def analyze_flows_bulk(directory: str) -> List[FlowProfile]:
    """Scan a directory for .tfl/.tflx files and analyze each.

    Args:
        directory: Path to folder containing Prep flows

    Returns:
        List of FlowProfile objects sorted by name
    """
    profiles = []
    for root, _dirs, files in os.walk(directory):
        for fname in sorted(files):
            if fname.lower().endswith(('.tfl', '.tflx')):
                fpath = os.path.join(root, fname)
                try:
                    profile = analyze_flow(fpath)
                    profiles.append(profile)
                except (ValueError, OSError, KeyError) as exc:
                    logger.warning("Failed to analyze %s: %s", fpath, exc)
    return profiles
