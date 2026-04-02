"""
Prep Lineage Report — Global HTML report & merge advisor for Prep flow portfolios.

Generates an interactive HTML report with:
1. Executive summary (stat cards)
2. Flow inventory table
3. Source inventory (shared sources highlighted)
4. Output inventory
5. Lineage diagram (Mermaid)
6. Merge recommendations with scoring

Usage::

    from powerbi_import.prep_lineage_report import (
        generate_prep_lineage_report,
        compute_merge_recommendations,
        save_lineage_json,
    )

    recs = compute_merge_recommendations(graph)
    generate_prep_lineage_report(graph, recs, "lineage_report.html")
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from powerbi_import.prep_lineage import (
        PrepLineageGraph, LineageEdge, SourceEndpoint, SinkEndpoint,
    )
except ImportError:
    from prep_lineage import (
        PrepLineageGraph, LineageEdge, SourceEndpoint, SinkEndpoint,
    )

try:
    from powerbi_import.html_template import (
        html_open, html_close, stat_grid, stat_card, section_open,
        section_close, data_table, badge, esc, card,
    )
except ImportError:
    try:
        from html_template import (
            html_open, html_close, stat_grid, stat_card, section_open,
            section_close, data_table, badge, esc, card,
        )
    except ImportError:
        # Fallback stubs for testing
        def esc(t):
            return str(t).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        def html_open(**kw):
            return '<html><body>'

        def html_close(**kw):
            return '</body></html>'

        def stat_card(value, label, **kw):
            return f'<div>{value} {label}</div>'

        def stat_grid(cards):
            return ''.join(cards)

        def section_open(section_id, title, **kw):
            return f'<div id="{section_id}"><h2>{title}</h2>'

        def section_close():
            return '</div>'

        def data_table(headers, rows, **kw):
            return '<table></table>'

        def badge(score, level=''):
            return f'<span>{score}</span>'

        def card(content='', title=''):
            return f'<div>{content}</div>'


# ═══════════════════════════════════════════════════════════════════════════════
#  MERGE RECOMMENDATION ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class MergeRecommendation:
    """A merge recommendation for simplifying the Prep portfolio."""
    rec_type: str          # source_consolidation, chain_collapse, source_dedup,
                           # redundant_output, fan_in_simplification, isolated
    flows: List[str]       # Flow names involved
    description: str
    impact: str            # Human-readable impact description
    score: int = 0         # 0–100

    @property
    def level(self) -> str:
        if self.score >= 70:
            return 'green'
        if self.score >= 40:
            return 'yellow'
        return 'gray'

    @property
    def label(self) -> str:
        if self.score >= 70:
            return 'Strong merge'
        if self.score >= 40:
            return 'Possible merge'
        return 'Keep separate'

    def to_dict(self) -> dict:
        return {
            'type': self.rec_type,
            'flows': self.flows,
            'description': self.description,
            'impact': self.impact,
            'score': self.score,
            'level': self.level,
            'label': self.label,
        }


def _source_overlap(a_fp: set, b_fp: set) -> float:
    """Jaccard-like source fingerprint overlap (0.0–1.0)."""
    if not a_fp and not b_fp:
        return 0.0
    return len(a_fp & b_fp) / len(a_fp | b_fp) if (a_fp | b_fp) else 0.0


def _transform_similarity(a_types: List[str], b_types: List[str],
                          a_flows=None, b_flows=None) -> float:
    """Compare transform sequences (0.0–1.0).

    Uses longest-common-subsequence ratio on transform types.
    When flow profiles are provided, also compares operation-level detail
    for a more accurate similarity score.
    """
    if not a_types and not b_types:
        return 0.0
    if not a_types or not b_types:
        return 0.0

    # Type-level LCS
    m, n = len(a_types), len(b_types)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a_types[i - 1] == b_types[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    lcs = dp[m][n]
    type_sim = lcs / max(m, n)

    # Operation-level similarity (when available)
    if a_flows is not None and b_flows is not None:
        a_ops = _collect_operation_types(a_flows)
        b_ops = _collect_operation_types(b_flows)
        if a_ops or b_ops:
            all_ops = a_ops | b_ops
            if all_ops:
                shared = a_ops & b_ops
                op_sim = len(shared) / len(all_ops)
                # Blend: 60% type-level + 40% operation-level
                return type_sim * 0.6 + op_sim * 0.4

    return type_sim


def _collect_operation_types(flow) -> set:
    """Collect unique operation type strings from a flow profile."""
    ops: set = set()
    for t in flow.transforms:
        details = t.details or {}
        for op in details.get('operations', []):
            ops.add(op.get('type', 'unknown'))
        if details.get('join_type'):
            ops.add(f'join_{details["join_type"]}')
        if details.get('group_by_columns'):
            ops.add('aggregate')
        if details.get('pivot_type'):
            ops.add(f'pivot_{details["pivot_type"]}')
    return ops


def _column_overlap(a_cols: set, b_cols: set) -> float:
    """Jaccard column name overlap (0.0–1.0)."""
    if not a_cols and not b_cols:
        return 0.0
    return len(a_cols & b_cols) / len(a_cols | b_cols) if (a_cols | b_cols) else 0.0


def compute_merge_recommendations(graph: PrepLineageGraph) -> List[MergeRecommendation]:
    """Analyze the lineage graph and produce merge recommendations.

    Recommendation types:
    1. Source consolidation — flows with high source overlap
    2. Chain collapse — linear A→B chains
    3. Source dedup — same source used by 3+ flows
    4. Redundant output — two flows producing same output fingerprint
    5. Isolated flow — no cross-flow edges
    """
    recs: List[MergeRecommendation] = []
    flow_by_name = {f.name: f for f in graph.flows}

    # ── Source Consolidation ──────────────────────────────────────
    flow_names = sorted(flow_by_name.keys())
    for i, fa_name in enumerate(flow_names):
        fa = flow_by_name[fa_name]
        fa_fps = {inp.fingerprint for inp in fa.inputs}
        fa_ttypes = [t.transform_type for t in fa.transforms]
        fa_out_cols: set = set()
        for o in fa.outputs:
            fa_out_cols.update(c.lower() for c in o.column_names)

        for fb_name in flow_names[i + 1:]:
            fb = flow_by_name[fb_name]
            fb_fps = {inp.fingerprint for inp in fb.inputs}

            src_ovl = _source_overlap(fa_fps, fb_fps)
            if src_ovl < 0.3:
                continue  # Not enough overlap

            fb_ttypes = [t.transform_type for t in fb.transforms]
            trans_sim = _transform_similarity(fa_ttypes, fb_ttypes,
                                              a_flows=fa, b_flows=fb)

            fb_out_cols: set = set()
            for o in fb.outputs:
                fb_out_cols.update(c.lower() for c in o.column_names)
            col_ovl = _column_overlap(fa_out_cols, fb_out_cols)

            # Complexity reduction estimate
            shared_nodes = min(fa.node_count, fb.node_count)
            total_nodes = fa.node_count + fb.node_count
            complexity_red = shared_nodes / total_nodes if total_nodes else 0

            score = int(
                src_ovl * 40
                + trans_sim * 30
                + col_ovl * 20
                + complexity_red * 10
            )

            if score >= 30:
                shared_count = len(fa_fps & fb_fps)
                recs.append(MergeRecommendation(
                    rec_type='source_consolidation',
                    flows=[fa_name, fb_name],
                    description=f'Both read {shared_count} common source(s), '
                                f'{int(trans_sim * 100)}% transform similarity',
                    impact=f'Eliminate 1 flow, reduce {shared_count} duplicate source connections',
                    score=score,
                ))

    # ── Chain Collapse ────────────────────────────────────────────
    for chain in graph.chains:
        if len(chain) < 2:
            continue
        total_nodes = sum(flow_by_name[n].node_count for n in chain if n in flow_by_name)
        score = min(80, 50 + len(chain) * 10)
        recs.append(MergeRecommendation(
            rec_type='chain_collapse',
            flows=chain,
            description=f'Linear chain of {len(chain)} flows with no fan-out',
            impact=f'Merge into 1 flow ({total_nodes} total nodes)',
            score=score,
        ))

    # ── Source Dedup ──────────────────────────────────────────────
    for src in graph.external_sources:
        if len(src.consumed_by) >= 3:
            flow_list = sorted(set(f for f, _ in src.consumed_by))
            table_desc = src.table_name or src.filename or src.fingerprint[:8]
            recs.append(MergeRecommendation(
                rec_type='source_dedup',
                flows=flow_list,
                description=f'Source "{table_desc}" ({src.connection_type}) '
                            f'read by {len(src.consumed_by)} flows',
                impact=f'Reduce {len(src.consumed_by)}→1 source connections via shared query',
                score=min(75, 40 + len(src.consumed_by) * 8),
            ))

    # ── Redundant Output ──────────────────────────────────────────
    output_fps: Dict[str, List[Tuple[str, str]]] = {}
    for flow in graph.flows:
        for out in flow.outputs:
            output_fps.setdefault(out.fingerprint, []).append((flow.name, out.name))
    for fp, producers in output_fps.items():
        if len(producers) >= 2:
            flow_list = sorted(set(f for f, _ in producers))
            out_names = ', '.join(set(n for _, n in producers))
            recs.append(MergeRecommendation(
                rec_type='redundant_output',
                flows=flow_list,
                description=f'{len(producers)} flows produce same output "{out_names}"',
                impact=f'Keep 1, remove {len(producers) - 1} redundant output(s)',
                score=65,
            ))

    # ── Isolated Flows ────────────────────────────────────────────
    for name in graph.isolated_flows:
        recs.append(MergeRecommendation(
            rec_type='isolated',
            flows=[name],
            description='No cross-flow connections detected',
            impact='Standalone migration — no merge needed',
            score=0,
        ))

    # Sort by score descending
    recs.sort(key=lambda r: (-r.score, r.rec_type))
    return recs


# ═══════════════════════════════════════════════════════════════════════════════
#  HTML REPORT GENERATION
# ═══════════════════════════════════════════════════════════════════════════════

def _render_executive_summary(graph: PrepLineageGraph,
                              rec_count: int) -> str:
    """Section 1 — stat cards."""
    cards = [
        stat_card(graph.total_flows, 'Total Flows', accent='blue'),
        stat_card(graph.total_sources, 'External Sources', accent='teal'),
        stat_card(graph.total_outputs, 'Final Outputs', accent='purple'),
        stat_card(graph.total_cross_flow_edges, 'Cross-Flow Edges'),
        stat_card(graph.max_chain_depth, 'Max Chain Depth'),
        stat_card(rec_count, 'Merge Candidates', accent='success' if rec_count else ''),
    ]
    return stat_grid(cards)


def _complexity_badge(label: str) -> str:
    level_map = {'Low': 'green', 'Medium': 'yellow', 'High': 'red'}
    return badge(label, level_map.get(label, 'gray'))


def _render_flow_inventory(graph: PrepLineageGraph) -> str:
    """Section 2 — flow inventory table."""
    headers = ['Flow', 'Inputs', 'Outputs', 'Transforms', 'Joins', 'Unions',
               'Scripts', 'Depth', 'Complexity']
    rows = []
    for f in sorted(graph.flows, key=lambda x: x.name):
        rows.append([
            esc(f.name),
            str(len(f.inputs)),
            str(len(f.outputs)),
            str(len(f.transforms)),
            str(f.join_count),
            str(f.union_count),
            str(f.script_count) if f.script_count else '—',
            str(f.dag_depth),
            _complexity_badge(f.complexity_label),
        ])
    return data_table(headers, rows, table_id='flow-inventory',
                      sortable=True, searchable=True)


def _render_source_inventory(graph: PrepLineageGraph) -> str:
    """Section 3 — all external sources across all flows."""
    headers = ['Source', 'Connection', 'Server', 'Database', 'Table / File', 'Used By']
    rows = []
    for src in sorted(graph.external_sources,
                      key=lambda s: -len(s.consumed_by)):
        flow_list = sorted(set(f for f, _ in src.consumed_by))
        flow_badges = ' '.join(badge(f, 'blue') for f in flow_list)
        shared = badge('SHARED', 'yellow') + ' ' if len(flow_list) >= 2 else ''
        table_or_file = esc(src.table_name or src.filename or '—')
        rows.append([
            shared + table_or_file,
            esc(src.connection_type or '—'),
            esc(src.server or '—'),
            esc(src.database or '—'),
            table_or_file,
            flow_badges,
        ])
    return data_table(headers, rows, table_id='source-inventory',
                      sortable=True, searchable=True)


def _render_output_inventory(graph: PrepLineageGraph) -> str:
    """Section 4 — all outputs."""
    headers = ['Output', 'Type', 'Target', 'Produced By', 'Consumed By']
    rows = []

    # Build consumed-by lookup from edges
    consumed_map: Dict[str, List[str]] = {}
    for e in graph.edges:
        key = f"{e.source_flow}::{e.source_output}"
        consumed_map.setdefault(key, []).append(e.target_flow)

    for sink in graph.final_sinks:
        flow_name, out_name = sink.produced_by
        key = f"{flow_name}::{out_name}"
        consumers = consumed_map.get(key, [])
        consumer_html = ', '.join(badge(c, 'blue') for c in consumers) if consumers else '—  (final)'
        target = esc(sink.target_table or sink.target_filename or '—')
        rows.append([
            esc(out_name),
            esc(sink.output_type or '—'),
            target,
            badge(flow_name, 'blue'),
            consumer_html,
        ])
    return data_table(headers, rows, table_id='output-inventory',
                      sortable=True)


def _render_lineage_diagram(graph: PrepLineageGraph) -> str:
    """Section 5 — Mermaid diagram embedded in HTML."""
    lines = ['graph LR']

    # External sources
    src_ids: Dict[str, str] = {}
    for i, src in enumerate(graph.external_sources):
        sid = f'SRC{i}'
        label = esc(src.table_name or src.filename or src.fingerprint[:8])
        lines.append(f'    {sid}[("{label}<br/><small>{esc(src.connection_type)}</small>")]')
        lines.append(f'    style {sid} fill:#deecf9,stroke:#0078d4')
        src_ids[src.fingerprint] = sid

    # Flow nodes
    flow_ids = {}
    for f in graph.flows:
        fid = f'F_{f.name.replace(" ", "_").replace("-", "_")}'
        flow_ids[f.name] = fid
        label = esc(f.name)
        lines.append(f'    {fid}["{label}<br/><small>{len(f.transforms)} transforms</small>"]')

    # Final sinks
    sink_ids = {}
    for i, sink in enumerate(graph.final_sinks):
        sid = f'SINK{i}'
        label = esc(sink.target_table or sink.target_filename or sink.produced_by[1])
        lines.append(f'    {sid}(("{label}"))')
        lines.append(f'    style {sid} fill:#dff6dd,stroke:#107c10')
        sink_ids[(sink.produced_by[0], sink.produced_by[1])] = sid

    # Edges: sources → flows
    for src in graph.external_sources:
        sid = src_ids.get(src.fingerprint)
        if not sid:
            continue
        for flow_name, _ in src.consumed_by:
            fid = flow_ids.get(flow_name)
            if fid:
                lines.append(f'    {sid} --> {fid}')

    # Edges: flow → flow (cross-flow)
    for e in graph.edges:
        sfid = flow_ids.get(e.source_flow)
        tfid = flow_ids.get(e.target_flow)
        if sfid and tfid:
            lines.append(f'    {sfid} -->|"{e.match_type}"| {tfid}')

    # Edges: flow → sinks
    for flow in graph.flows:
        fid = flow_ids.get(flow.name)
        for out in flow.outputs:
            key = (flow.name, out.name)
            sid = sink_ids.get(key)
            if fid and sid:
                lines.append(f'    {fid} --> {sid}')

    mermaid_code = '\n'.join(lines)

    return f"""<div class="card">
<div id="mermaid-diagram" class="mermaid">
{mermaid_code}
</div>
</div>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<script>mermaid.initialize({{startOnLoad:true, theme:'default', securityLevel:'loose'}});</script>
"""


def _render_merge_recommendations(recs: List[MergeRecommendation]) -> str:
    """Section 6 — merge recommendation table."""
    if not recs:
        return card(content='<p>No merge recommendations — all flows are independent.</p>',
                    title='No Action Needed')

    actionable = [r for r in recs if r.score > 0]
    isolated = [r for r in recs if r.score == 0]

    headers = ['Score', 'Type', 'Flows', 'Description', 'Impact']
    rows = []
    for r in actionable:
        type_labels = {
            'source_consolidation': 'Source Consolidation',
            'chain_collapse': 'Chain Collapse',
            'source_dedup': 'Source Dedup',
            'redundant_output': 'Redundant Output',
            'fan_in_simplification': 'Fan-in Simplification',
        }
        rows.append([
            badge(f'{r.score}/100', r.level),
            esc(type_labels.get(r.rec_type, r.rec_type)),
            ', '.join(badge(f, 'blue') for f in r.flows),
            esc(r.description),
            esc(r.impact),
        ])

    html = data_table(headers, rows, table_id='merge-recs', sortable=True)

    if isolated:
        html += f'\n<p style="margin-top:12px;color:#605e5c;">'
        html += f'{len(isolated)} isolated flow(s) require no merging: '
        html += ', '.join(esc(r.flows[0]) for r in isolated)
        html += '</p>'

    return html


def _render_transform_documentation(graph: PrepLineageGraph) -> str:
    """Section 7 — per-flow transformation pipeline documentation."""
    html_parts: List[str] = []
    for flow in sorted(graph.flows, key=lambda x: x.name):
        if not flow.transforms:
            continue
        # Flow header
        html_parts.append(f'<div class="card" style="margin-bottom:16px;">')
        html_parts.append(f'<h3 style="margin:0 0 8px;">{esc(flow.name)}</h3>')
        html_parts.append(f'<p style="color:#605e5c;margin:0 0 12px;">'
                          f'{len(flow.inputs)} input(s) → '
                          f'{len(flow.transforms)} transform(s) → '
                          f'{len(flow.outputs)} output(s) | '
                          f'Complexity: {_complexity_badge(flow.complexity_label)}</p>')

        # Transform pipeline table
        headers = ['#', 'Step', 'Type', 'Operations', 'Details']
        rows = []
        for idx, t in enumerate(flow.transforms, 1):
            details = t.details or {}

            # Build operations summary
            ops = details.get('operations', [])
            if ops:
                op_types = {}
                for op in ops:
                    ot = op.get('type', 'unknown')
                    op_types[ot] = op_types.get(ot, 0) + 1
                ops_html = ', '.join(f'{badge(str(c), "blue")} {esc(ot)}'
                                     for ot, c in sorted(op_types.items()))
            elif details.get('join_keys'):
                keys = details['join_keys']
                ops_html = ', '.join(f'{esc(k.get("left", "?"))} = {esc(k.get("right", "?"))}'
                                     for k in keys)
            elif details.get('group_by_columns'):
                gcols = details['group_by_columns']
                acols = details.get('aggregate_columns', [])
                ops_html = f'Group by: {", ".join(esc(c) for c in gcols)}'
                if acols:
                    ops_html += f'<br/>Agg: {", ".join(esc(a) for a in acols)}'
            else:
                ops_html = '—'

            # Detail strings
            detail_parts = []
            if details.get('join_type'):
                detail_parts.append(f'Join: {esc(details["join_type"])}')
            if details.get('key_count'):
                detail_parts.append(f'{details["key_count"]} key(s)')
            if details.get('action_count'):
                detail_parts.append(f'{details["action_count"]} action(s)')
            if details.get('group_fields'):
                detail_parts.append(f'{details["group_fields"]} group field(s)')
            if details.get('agg_fields'):
                detail_parts.append(f'{details["agg_fields"]} agg field(s)')
            if details.get('pivot_type'):
                detail_parts.append(f'Pivot: {esc(details["pivot_type"])}')
            if details.get('script_type'):
                detail_parts.append(f'Language: {esc(details["script_type"])}')
            out_cols = details.get('output_columns', [])
            if out_cols:
                detail_parts.append(f'{len(out_cols)} output col(s)')

            rows.append([
                str(idx),
                esc(t.name),
                badge(t.transform_type, {
                    'Clean': 'blue', 'Join': 'purple', 'Union': 'teal',
                    'Aggregate': 'yellow', 'Pivot': 'yellow',
                    'Script': 'red', 'Prediction': 'red',
                }.get(t.transform_type, 'gray')),
                ops_html,
                '; '.join(detail_parts) if detail_parts else '—',
            ])

        html_parts.append(data_table(headers, rows,
                                      table_id=f'transforms-{flow.name.replace(" ", "-")}',
                                      sortable=False))

        # Expanded operations detail (collapsible)
        all_ops = []
        for t in flow.transforms:
            for op in (t.details or {}).get('operations', []):
                all_ops.append((t.name, op))
        if all_ops:
            html_parts.append('<details style="margin-top:8px;">')
            html_parts.append('<summary style="cursor:pointer;color:#0078d4;">'
                              f'Show {len(all_ops)} individual operation(s)</summary>')
            op_headers = ['Step', 'Operation', 'Column', 'Description']
            op_rows = []
            for step_name, op in all_ops:
                op_rows.append([
                    esc(step_name),
                    badge(op.get('type', '?'), 'gray'),
                    esc(op.get('column', '—')),
                    esc(op.get('description', '—')),
                ])
            html_parts.append(data_table(op_headers, op_rows,
                                          table_id=f'ops-{flow.name.replace(" ", "-")}',
                                          sortable=False))
            html_parts.append('</details>')

        html_parts.append('</div>')

    if not html_parts:
        return card(content='<p>No transformations found in any flow.</p>',
                    title='No Transforms')
    return '\n'.join(html_parts)


def generate_prep_lineage_report(
    graph: PrepLineageGraph,
    recommendations: List[MergeRecommendation],
    output_path: str,
    version: str = '',
) -> str:
    """Generate the full interactive HTML lineage report.

    Args:
        graph: PrepLineageGraph from build_lineage_graph()
        recommendations: List from compute_merge_recommendations()
        output_path: Path to write the HTML file
        version: Tool version string

    Returns:
        The output path
    """
    ts = datetime.now().strftime('%Y-%m-%d %H:%M')
    actionable = sum(1 for r in recommendations if r.score > 0)

    html = html_open(
        title='Tableau Prep — Flow Lineage Report',
        subtitle=f'{graph.total_flows} flows analyzed | '
                 f'{graph.total_cross_flow_edges} cross-flow edges | '
                 f'{actionable} merge candidates',
        timestamp=ts,
        version=version,
    )

    # Section 1: Executive Summary
    html += _render_executive_summary(graph, actionable)

    # Section 2: Flow Inventory
    html += section_open('sec-flows', 'Flow Inventory', icon='📋')
    html += _render_flow_inventory(graph)
    html += section_close()

    # Section 3: Source Inventory
    html += section_open('sec-sources', 'Source Inventory', icon='🗄️')
    html += _render_source_inventory(graph)
    html += section_close()

    # Section 4: Output Inventory
    html += section_open('sec-outputs', 'Output Inventory', icon='📤')
    html += _render_output_inventory(graph)
    html += section_close()

    # Section 5: Lineage Diagram
    html += section_open('sec-lineage', 'Lineage Diagram', icon='🔗')
    html += _render_lineage_diagram(graph)
    html += section_close()

    # Section 6: Merge Recommendations
    html += section_open('sec-merge', 'Merge Recommendations', icon='🔀')
    html += _render_merge_recommendations(recommendations)
    html += section_close()

    # Section 7: Transform Documentation
    html += section_open('sec-transforms', 'Transform Documentation', icon='🔧')
    html += _render_transform_documentation(graph)
    html += section_close()

    html += html_close(version=version, timestamp=ts)

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    logger.info("Lineage report saved to %s", output_path)
    return output_path


def save_lineage_json(graph: PrepLineageGraph,
                      recommendations: List[MergeRecommendation],
                      output_path: str) -> str:
    """Export lineage graph and recommendations as JSON.

    Args:
        graph: PrepLineageGraph
        recommendations: List of MergeRecommendation
        output_path: Path to write JSON

    Returns:
        The output path
    """
    data = graph.to_dict()
    data['recommendations'] = [r.to_dict() for r in recommendations]
    data['timestamp'] = datetime.now(timezone.utc).isoformat()

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info("Lineage JSON saved to %s", output_path)
    return output_path


def print_lineage_summary(graph: PrepLineageGraph,
                          recommendations: List[MergeRecommendation]):
    """Print a formatted console summary."""
    w = 64

    print()
    print('=' * w)
    print('  Prep Flow Lineage Analysis'.center(w))
    print('=' * w)
    print(f'  Total flows:              {graph.total_flows}')
    print(f'  External sources:         {graph.total_sources}')
    print(f'  Final outputs:            {graph.total_outputs}')
    print(f'  Cross-flow edges:         {graph.total_cross_flow_edges}')
    print(f'  Max chain depth:          {graph.max_chain_depth}')
    print(f'  Isolated flows:           {len(graph.isolated_flows)}')
    print('-' * w)

    if graph.edges:
        print('  CROSS-FLOW CONNECTIONS:')
        for e in graph.edges:
            print(f'    {e.source_flow} → {e.target_flow} ({e.match_type}, '
                  f'confidence={e.confidence})')
        print()

    # Per-flow transform summary
    has_transforms = any(f.transforms for f in graph.flows)
    if has_transforms:
        print('  TRANSFORM DOCUMENTATION:')
        for flow in sorted(graph.flows, key=lambda x: x.name):
            if not flow.transforms:
                continue
            print(f'    ── {flow.name} ({flow.complexity_label} complexity) ──')
            for idx, t in enumerate(flow.transforms, 1):
                details = t.details or {}
                ops = details.get('operations', [])
                extras = []
                if ops:
                    op_summary = {}
                    for op in ops:
                        ot = op.get('type', 'unknown')
                        op_summary[ot] = op_summary.get(ot, 0) + 1
                    extras.append(', '.join(f'{c}× {ot}' for ot, c in sorted(op_summary.items())))
                if details.get('join_keys'):
                    keys = details['join_keys']
                    extras.append('keys: ' + ', '.join(
                        f'{k.get("left", "?")}={k.get("right", "?")}' for k in keys))
                if details.get('group_by_columns'):
                    extras.append('group by: ' + ', '.join(details['group_by_columns']))
                if details.get('aggregate_columns'):
                    extras.append('agg: ' + ', '.join(details['aggregate_columns']))
                detail_str = f' [{"; ".join(extras)}]' if extras else ''
                print(f'      {idx}. {t.transform_type}: {t.name}{detail_str}')
            print()

    actionable = [r for r in recommendations if r.score > 0]
    if actionable:
        print('  MERGE RECOMMENDATIONS:')
        for r in actionable:
            icon = '🟢' if r.score >= 70 else '🟡' if r.score >= 40 else '⚪'
            print(f'    {icon} {r.label}: {", ".join(r.flows)} (score: {r.score}/100)')
            print(f'       → {r.description}')
        print()

    isolated = [r for r in recommendations if r.rec_type == 'isolated']
    if isolated:
        names = ', '.join(r.flows[0] for r in isolated)
        print(f'  Isolated (standalone): {names}')
    print('=' * w)
