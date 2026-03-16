"""
Global Assessment — Cross-Workbook Merge Analysis & HTML Report.

Analyzes ALL workbooks in a batch to identify merge clusters,
pairwise overlap, and produces a visual HTML report showing:
- Workbook inventory (per-workbook stats)
- Pairwise merge score matrix (N×N heatmap)
- Merge clusters (groups of workbooks that share tables)
- Isolated workbooks (no overlap with any other)
- Per-cluster detailed breakdown

Usage (CLI)::

    python migrate.py --batch examples/tableau_samples/ --global-assess
    python migrate.py --global-assess wb1.twbx wb2.twbx wb3.twbx wb4.twbx

Usage (programmatic)::

    from powerbi_import.global_assessment import (
        run_global_assessment,
        generate_global_html_report,
    )

    result = run_global_assessment(all_extracted_list, workbook_names)
    generate_global_html_report(result, output_path="global_assessment.html")
"""

from __future__ import annotations

import datetime
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from powerbi_import.shared_model import (
        MergeAssessment,
        assess_merge,
        build_table_fingerprints,
    )
except ImportError:
    from shared_model import (
        MergeAssessment,
        assess_merge,
        build_table_fingerprints,
    )


# ═══════════════════════════════════════════════════════════════════
#  Color palette (matches merge_report_html.py)
# ═══════════════════════════════════════════════════════════════════
PBI_BLUE = "#0078d4"
PBI_DARK = "#323130"
PBI_GRAY = "#605e5c"
PBI_LIGHT_GRAY = "#a19f9d"
PBI_BG = "#f5f5f5"
SUCCESS = "#28a745"
WARN = "#ffc107"
FAIL = "#dc3545"


# ═══════════════════════════════════════════════════════════════════
#  Data classes
# ═══════════════════════════════════════════════════════════════════

@dataclass
class WorkbookProfile:
    """Stats for a single workbook."""
    name: str
    tables: int = 0
    columns: int = 0
    measures: int = 0
    calc_columns: int = 0
    relationships: int = 0
    worksheets: int = 0
    dashboards: int = 0
    parameters: int = 0
    connection_types: List[str] = field(default_factory=list)
    table_names: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "tables": self.tables,
            "columns": self.columns,
            "measures": self.measures,
            "calc_columns": self.calc_columns,
            "relationships": self.relationships,
            "worksheets": self.worksheets,
            "dashboards": self.dashboards,
            "parameters": self.parameters,
            "connection_types": self.connection_types,
            "table_names": self.table_names,
        }


@dataclass
class PairwiseScore:
    """Merge score between two workbooks."""
    wb_a: str
    wb_b: str
    merge_score: int = 0
    shared_tables: int = 0
    recommendation: str = "separate"

    def to_dict(self) -> dict:
        return {
            "workbook_a": self.wb_a,
            "workbook_b": self.wb_b,
            "merge_score": self.merge_score,
            "shared_tables": self.shared_tables,
            "recommendation": self.recommendation,
        }


@dataclass
class MergeCluster:
    """A group of workbooks recommended for merging."""
    cluster_id: int
    workbooks: List[str] = field(default_factory=list)
    shared_tables: List[str] = field(default_factory=list)
    avg_score: int = 0
    recommendation: str = "merge"
    assessment: Optional[MergeAssessment] = None

    def to_dict(self) -> dict:
        d = {
            "cluster_id": self.cluster_id,
            "workbooks": self.workbooks,
            "shared_tables": self.shared_tables,
            "avg_score": self.avg_score,
            "recommendation": self.recommendation,
        }
        if self.assessment:
            d["merge_details"] = self.assessment.to_dict()
        return d


@dataclass
class GlobalAssessment:
    """Full cross-workbook assessment."""
    workbook_profiles: List[WorkbookProfile] = field(default_factory=list)
    pairwise_scores: List[PairwiseScore] = field(default_factory=list)
    merge_clusters: List[MergeCluster] = field(default_factory=list)
    isolated_workbooks: List[str] = field(default_factory=list)
    total_workbooks: int = 0
    total_tables: int = 0
    total_measures: int = 0

    def to_dict(self) -> dict:
        return {
            "total_workbooks": self.total_workbooks,
            "total_tables": self.total_tables,
            "total_measures": self.total_measures,
            "merge_clusters": [c.to_dict() for c in self.merge_clusters],
            "isolated_workbooks": self.isolated_workbooks,
            "pairwise_scores": [p.to_dict() for p in self.pairwise_scores],
            "workbook_profiles": [w.to_dict() for w in self.workbook_profiles],
        }


# ═══════════════════════════════════════════════════════════════════
#  Profiling helpers
# ═══════════════════════════════════════════════════════════════════

def _build_profile(name: str, extracted: dict) -> WorkbookProfile:
    """Build a WorkbookProfile from extracted data."""
    p = WorkbookProfile(name=name)
    conn_types = set()
    for ds in extracted.get('datasources', []):
        conn = ds.get('connection', {})
        ct = conn.get('type', '')
        if ct:
            conn_types.add(ct)
        for t in ds.get('tables', []):
            if t.get('type', 'table') == 'table':
                p.tables += 1
                p.table_names.append(t.get('name', ''))
            p.columns += len(t.get('columns', []))
        for c in ds.get('calculations', []):
            if c.get('role', 'measure') == 'measure':
                p.measures += 1
            elif c.get('role') == 'dimension':
                p.calc_columns += 1
        p.relationships += len(ds.get('relationships', []))
    for c in extracted.get('calculations', []):
        if c.get('role', 'measure') == 'measure':
            p.measures += 1
        elif c.get('role') == 'dimension':
            p.calc_columns += 1
    p.worksheets = len(extracted.get('worksheets', []))
    p.dashboards = len(extracted.get('dashboards', []))
    p.parameters = len(extracted.get('parameters', []))
    p.connection_types = sorted(conn_types)
    return p


def _find_shared_table_names(ext_a: dict, ext_b: dict) -> List[str]:
    """Find table names shared between two workbooks via fingerprint matching."""
    fp_a = build_table_fingerprints(ext_a.get('datasources', []))
    fp_b = build_table_fingerprints(ext_b.get('datasources', []))
    hashes_a = {fp.fingerprint(): name for name, (fp, _, _) in fp_a.items()}
    hashes_b = {fp.fingerprint(): name for name, (fp, _, _) in fp_b.items()}
    shared_hashes = set(hashes_a.keys()) & set(hashes_b.keys())
    return [hashes_a[h] for h in shared_hashes]


# ═══════════════════════════════════════════════════════════════════
#  Core assessment
# ═══════════════════════════════════════════════════════════════════

def run_global_assessment(
    all_extracted: List[dict],
    workbook_names: List[str],
) -> GlobalAssessment:
    """Analyze all workbooks pairwise and identify merge clusters.

    Args:
        all_extracted: List of converted_objects dicts (one per workbook).
        workbook_names: Names for each workbook (parallel with all_extracted).

    Returns:
        GlobalAssessment with profiles, pairwise scores, and clusters.
    """
    n = len(workbook_names)
    result = GlobalAssessment(total_workbooks=n)

    # 1. Build per-workbook profiles
    for name, ext in zip(workbook_names, all_extracted):
        result.workbook_profiles.append(_build_profile(name, ext))
    result.total_tables = sum(p.tables for p in result.workbook_profiles)
    result.total_measures = sum(p.measures for p in result.workbook_profiles)

    # 2. Pairwise merge scores
    # adjacency: wb_index → set of wb_indices with score >= 30
    adjacency: Dict[int, set] = {i: set() for i in range(n)}

    for i in range(n):
        for j in range(i + 1, n):
            pair_assessment = assess_merge(
                [all_extracted[i], all_extracted[j]],
                [workbook_names[i], workbook_names[j]],
            )
            shared = _find_shared_table_names(all_extracted[i], all_extracted[j])
            ps = PairwiseScore(
                wb_a=workbook_names[i],
                wb_b=workbook_names[j],
                merge_score=pair_assessment.merge_score,
                shared_tables=len(shared),
                recommendation=pair_assessment.recommendation,
            )
            result.pairwise_scores.append(ps)
            if pair_assessment.merge_score >= 30:
                adjacency[i].add(j)
                adjacency[j].add(i)

    # 3. Find connected components (merge clusters) via BFS
    visited = set()
    cluster_id = 0
    for start in range(n):
        if start in visited:
            continue
        if not adjacency[start]:
            # Isolated workbook
            result.isolated_workbooks.append(workbook_names[start])
            visited.add(start)
            continue

        # BFS
        cluster_indices = []
        queue = [start]
        while queue:
            node = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            cluster_indices.append(node)
            for neighbor in adjacency[node]:
                if neighbor not in visited:
                    queue.append(neighbor)

        if len(cluster_indices) < 2:
            result.isolated_workbooks.append(workbook_names[cluster_indices[0]])
            continue

        # Build cluster assessment
        cluster_wb_names = [workbook_names[i] for i in cluster_indices]
        cluster_extracted = [all_extracted[i] for i in cluster_indices]
        cluster_assessment = assess_merge(cluster_extracted, cluster_wb_names)

        # Collect shared table names
        shared_names = sorted({
            mc.table_name for mc in cluster_assessment.merge_candidates
        })

        # Average pairwise score within cluster
        pair_scores = []
        for ps in result.pairwise_scores:
            if ps.wb_a in cluster_wb_names and ps.wb_b in cluster_wb_names:
                pair_scores.append(ps.merge_score)
        avg = int(sum(pair_scores) / len(pair_scores)) if pair_scores else 0

        cluster = MergeCluster(
            cluster_id=cluster_id,
            workbooks=cluster_wb_names,
            shared_tables=shared_names,
            avg_score=avg,
            recommendation=cluster_assessment.recommendation,
            assessment=cluster_assessment,
        )
        result.merge_clusters.append(cluster)
        cluster_id += 1

    return result


# ═══════════════════════════════════════════════════════════════════
#  Console output
# ═══════════════════════════════════════════════════════════════════

def print_global_summary(result: GlobalAssessment):
    """Print a formatted console summary."""
    w = 68
    print()
    print("=" * w)
    print("  Global Cross-Workbook Assessment".center(w))
    print("=" * w)
    print(f"  Workbooks analyzed:     {result.total_workbooks}")
    print(f"  Total tables:           {result.total_tables}")
    print(f"  Total measures:         {result.total_measures}")
    print(f"  Merge clusters found:   {len(result.merge_clusters)}")
    print(f"  Isolated workbooks:     {len(result.isolated_workbooks)}")
    print("-" * w)

    if result.merge_clusters:
        print()
        print("  MERGE CLUSTERS:")
        for cluster in result.merge_clusters:
            rec_label = {
                "merge": "MERGE",
                "partial": "PARTIAL",
                "separate": "SEPARATE",
            }.get(cluster.recommendation, cluster.recommendation.upper())
            print(f"    Cluster #{cluster.cluster_id + 1} "
                  f"[{rec_label}] (avg score: {cluster.avg_score}/100)")
            for wb in cluster.workbooks:
                print(f"      - {wb}")
            if cluster.shared_tables:
                print(f"      Shared tables: {', '.join(cluster.shared_tables)}")
            print()

    if result.isolated_workbooks:
        print("  ISOLATED WORKBOOKS (no merge candidates):")
        for wb in result.isolated_workbooks:
            print(f"    - {wb}")
        print()

    if result.pairwise_scores:
        print("  PAIRWISE SCORES:")
        for ps in result.pairwise_scores:
            marker = {
                "merge": "OK",
                "partial": "~~",
                "separate": "--",
            }.get(ps.recommendation, "--")
            print(f"    [{marker}] {ps.wb_a} <-> {ps.wb_b}: "
                  f"{ps.merge_score}/100 "
                  f"({ps.shared_tables} shared tables)")
        print()

    print("=" * w)
    print()


# ═══════════════════════════════════════════════════════════════════
#  HTML helpers
# ═══════════════════════════════════════════════════════════════════

def _esc(text: str) -> str:
    """HTML-escape a string."""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def _score_bg(score: int) -> str:
    """Return background color for a merge score cell."""
    if score >= 60:
        return "#d4edda"  # green tint
    if score >= 30:
        return "#fff3cd"  # yellow tint
    if score > 0:
        return "#f8d7da"  # red tint
    return "#f5f5f5"      # neutral


def _score_color(score: int) -> str:
    if score >= 60:
        return SUCCESS
    if score >= 30:
        return WARN
    return FAIL


def _rec_badge(rec: str) -> str:
    labels = {
        "merge": ("MERGE", SUCCESS),
        "partial": ("PARTIAL", WARN),
        "separate": ("SEPARATE", FAIL),
    }
    text, color = labels.get(rec, (rec.upper(), PBI_GRAY))
    return (
        f'<span style="background:{color};color:#fff;padding:4px 12px;'
        f'border-radius:4px;font-weight:bold;font-size:0.9em">{text}</span>'
    )


def _overlap_bar(pct: float) -> str:
    width = max(int(pct * 100), 0)
    color = SUCCESS if pct >= 0.7 else WARN if pct >= 0.4 else FAIL
    return (
        f'<div style="background:#e9ecef;border-radius:4px;width:120px;'
        f'display:inline-block;vertical-align:middle">'
        f'<div style="background:{color};width:{width}%;height:16px;'
        f'border-radius:4px;text-align:center;font-size:11px;color:#fff;'
        f'line-height:16px">{width}%</div></div>'
    )


# ═══════════════════════════════════════════════════════════════════
#  HTML report generator
# ═══════════════════════════════════════════════════════════════════

def generate_global_html_report(
    result: GlobalAssessment,
    output_path: Optional[str] = None,
) -> str:
    """Generate a comprehensive HTML report for the global assessment.

    Args:
        result: GlobalAssessment from run_global_assessment().
        output_path: File path for HTML output (default: global_assessment.html).

    Returns:
        The output file path.
    """
    try:
        from powerbi_import import __version__ as tool_version
    except Exception:
        tool_version = "14.0.0"

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    n = result.total_workbooks
    profiles = result.workbook_profiles
    wb_names = [p.name for p in profiles]

    # Build pairwise lookup: (a, b) → PairwiseScore
    pair_lookup: Dict[Tuple[str, str], PairwiseScore] = {}
    for ps in result.pairwise_scores:
        pair_lookup[(ps.wb_a, ps.wb_b)] = ps
        pair_lookup[(ps.wb_b, ps.wb_a)] = ps

    # ══════════════════════════════════════════════════════════
    #  HTML head
    # ══════════════════════════════════════════════════════════
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Global Assessment — Merge Analysis</title>
<style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
           margin: 0; padding: 20px; background: {PBI_BG}; color: {PBI_DARK}; }}
    .container {{ max-width: 1500px; margin: 0 auto; }}
    h1 {{ color: {PBI_BLUE}; border-bottom: 3px solid {PBI_BLUE};
         padding-bottom: 10px; font-size: 1.6em; }}
    h2 {{ color: {PBI_DARK}; margin-top: 30px; font-size: 1.25em;
         cursor: pointer; }}
    h2:hover {{ color: {PBI_BLUE}; }}
    h3 {{ color: {PBI_GRAY}; margin-top: 20px; }}
    .card {{ background: #fff; border-radius: 8px; padding: 20px;
            margin: 15px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
    .stats {{ display: grid;
             grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
             gap: 12px; }}
    .stat {{ background: #fff; border-radius: 8px; padding: 16px;
            text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            transition: transform 0.15s; }}
    .stat:hover {{ transform: translateY(-2px);
                  box-shadow: 0 4px 8px rgba(0,0,0,0.15); }}
    .stat .number {{ font-size: 2em; font-weight: bold; color: {PBI_BLUE}; }}
    .stat .label {{ font-size: 0.85em; color: {PBI_GRAY}; margin-top: 4px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
    th {{ background: {PBI_BLUE}; color: #fff; padding: 10px 12px;
         text-align: left; font-size: 0.85em; position: sticky; top: 0; }}
    td {{ padding: 8px 12px; border-bottom: 1px solid #e1dfdd;
         font-size: 0.85em; }}
    tr:hover {{ background: #f3f2f1; }}
    .detail-table th {{ background: {PBI_GRAY}; }}
    .connector-tag {{ background: #e8f0fe; color: #1a73e8;
                     padding: 2px 6px; border-radius: 3px;
                     font-size: 0.82em; white-space: nowrap; }}
    .success-tag {{ background: #d4edda; color: #155724;
                   padding: 2px 6px; border-radius: 3px; font-size: 0.82em; }}
    .warn-tag {{ background: #fff3cd; color: #856404;
                padding: 2px 6px; border-radius: 3px; font-size: 0.82em; }}
    .danger-tag {{ background: #f8d7da; color: #721c24;
                  padding: 2px 6px; border-radius: 3px; font-size: 0.82em; }}
    .isolated-tag {{ background: #e2e3e5; color: #383d41;
                    padding: 2px 6px; border-radius: 3px; font-size: 0.82em; }}
    .cluster-card {{ background: #fff; border-radius: 8px; padding: 20px;
                    margin: 12px 0; box-shadow: 0 2px 6px rgba(0,0,0,0.12);
                    border-left: 5px solid {PBI_BLUE}; }}
    .cluster-card.merge {{ border-left-color: {SUCCESS}; }}
    .cluster-card.partial {{ border-left-color: {WARN}; }}
    .cluster-card.separate {{ border-left-color: {FAIL}; }}
    .matrix-cell {{ text-align: center; font-weight: bold; font-size: 0.85em;
                   min-width: 80px; }}
    .mono {{ font-family: 'Cascadia Code', 'Consolas', monospace;
            font-size: 0.82em; }}
    .section-icon {{ font-size: 1.2em; margin-right: 4px; }}
    .collapsible {{ overflow: hidden; transition: max-height 0.3s ease-out;
                   max-height: 5000px; }}
    .collapsed {{ max-height: 0 !important; }}
    .toggle-icon {{ float: right; font-size: 0.8em; color: {PBI_LIGHT_GRAY}; }}
    .footer {{ text-align: center; color: {PBI_LIGHT_GRAY};
              font-size: 0.85em; margin-top: 40px; padding: 20px; }}
    .cmd-box {{ background: #1e1e1e; color: #d4d4d4; padding: 14px 18px;
               border-radius: 6px; font-family: 'Cascadia Code', Consolas, monospace;
               font-size: 0.85em; overflow-x: auto; white-space: pre; }}
    @media print {{
        .collapsible {{ max-height: none !important; }}
        h2 {{ cursor: default; }}
        .toggle-icon {{ display: none; }}
    }}
</style>
</head>
<body>
<div class="container">
<h1>&#128202; Global Assessment — Cross-Workbook Merge Analysis</h1>
<p style="color:{PBI_GRAY};font-size:0.9em">
    Generated: {now} &nbsp;|&nbsp; Tool: v{_esc(tool_version)} &nbsp;|&nbsp;
    Workbooks: {n}
</p>
"""

    # ══════════════════════════════════════════════════════════
    # 1. EXECUTIVE SUMMARY
    # ══════════════════════════════════════════════════════════
    merge_count = len(result.merge_clusters)
    iso_count = len(result.isolated_workbooks)
    clustered_count = sum(len(c.workbooks) for c in result.merge_clusters)

    html += f"""
<h2 onclick="toggleSection('exec')"><span class="section-icon">&#128200;</span>
Executive Summary <span class="toggle-icon" id="exec-icon">&#9660;</span></h2>
<div id="exec" class="collapsible">
<div class="stats">
    <div class="stat"><div class="number">{n}</div>
        <div class="label">Workbooks</div></div>
    <div class="stat"><div class="number">{result.total_tables}</div>
        <div class="label">Total Tables</div></div>
    <div class="stat"><div class="number">{result.total_measures}</div>
        <div class="label">Total Measures</div></div>
    <div class="stat"><div class="number" style="color:{SUCCESS if merge_count else PBI_GRAY}">{merge_count}</div>
        <div class="label">Merge Clusters</div></div>
    <div class="stat"><div class="number" style="color:{SUCCESS}">{clustered_count}</div>
        <div class="label">Workbooks in Clusters</div></div>
    <div class="stat"><div class="number" style="color:{PBI_GRAY}">{iso_count}</div>
        <div class="label">Isolated Workbooks</div></div>
</div>
"""
    # Recommendation summary
    if merge_count:
        html += '<div class="card" style="margin-top:15px">'
        html += '<h3>Recommended Actions</h3><ul>'
        for cluster in result.merge_clusters:
            wbs = ", ".join(f"<strong>{_esc(w)}</strong>" for w in cluster.workbooks)
            html += (f'<li>{_rec_badge(cluster.recommendation)} &nbsp; '
                     f'{wbs} &nbsp; '
                     f'(score: {cluster.avg_score}/100, '
                     f'{len(cluster.shared_tables)} shared tables)</li>')
        if result.isolated_workbooks:
            iso_list = ", ".join(
                f"<strong>{_esc(w)}</strong>" for w in result.isolated_workbooks
            )
            html += (f'<li><span class="isolated-tag">STANDALONE</span> &nbsp; '
                     f'{iso_list} &nbsp; (migrate individually)</li>')
        html += '</ul></div>'
    else:
        html += ('<div class="card" style="margin-top:15px"><p>'
                 'No merge clusters detected — all workbooks should be '
                 'migrated individually.</p></div>')
    html += '</div>'

    # ══════════════════════════════════════════════════════════
    # 2. WORKBOOK INVENTORY
    # ══════════════════════════════════════════════════════════
    html += f"""
<h2 onclick="toggleSection('inv')"><span class="section-icon">&#128214;</span>
Workbook Inventory <span class="toggle-icon" id="inv-icon">&#9660;</span></h2>
<div id="inv" class="collapsible">
<div class="card">
<table>
<tr>
    <th>Workbook</th><th>Connectors</th><th>Tables</th><th>Columns</th>
    <th>Measures</th><th>Calc Columns</th><th>Relationships</th>
    <th>Worksheets</th><th>Dashboards</th><th>Status</th>
</tr>
"""
    # Pre-compute which workbooks are clustered
    clustered_set = set()
    wb_cluster_map: Dict[str, int] = {}
    for cluster in result.merge_clusters:
        for wb in cluster.workbooks:
            clustered_set.add(wb)
            wb_cluster_map[wb] = cluster.cluster_id

    for p in profiles:
        conn_html = " ".join(
            f'<span class="connector-tag">{_esc(c)}</span>'
            for c in p.connection_types
        ) or "—"
        if p.name in clustered_set:
            cid = wb_cluster_map[p.name] + 1
            status = f'<span class="success-tag">Cluster #{cid}</span>'
        else:
            status = '<span class="isolated-tag">Standalone</span>'
        html += f"""<tr>
    <td><strong>{_esc(p.name)}</strong></td>
    <td>{conn_html}</td>
    <td>{p.tables}</td><td>{p.columns}</td>
    <td>{p.measures}</td><td>{p.calc_columns}</td>
    <td>{p.relationships}</td>
    <td>{p.worksheets}</td><td>{p.dashboards}</td>
    <td>{status}</td>
</tr>"""

    # Totals
    html += f"""<tr style="background:#e8f0fe;font-weight:bold">
    <td>TOTAL</td><td></td>
    <td>{sum(p.tables for p in profiles)}</td>
    <td>{sum(p.columns for p in profiles)}</td>
    <td>{sum(p.measures for p in profiles)}</td>
    <td>{sum(p.calc_columns for p in profiles)}</td>
    <td>{sum(p.relationships for p in profiles)}</td>
    <td>{sum(p.worksheets for p in profiles)}</td>
    <td>{sum(p.dashboards for p in profiles)}</td>
    <td></td>
</tr>"""
    html += '</table></div></div>'

    # ══════════════════════════════════════════════════════════
    # 3. PAIRWISE MERGE SCORE MATRIX
    # ══════════════════════════════════════════════════════════
    if n >= 2:
        html += f"""
<h2 onclick="toggleSection('matrix')"><span class="section-icon">&#127922;</span>
Pairwise Merge Score Matrix <span class="toggle-icon" id="matrix-icon">&#9660;</span></h2>
<div id="matrix" class="collapsible">
<div class="card" style="overflow-x:auto">
<table>
<tr><th style="min-width:150px"></th>"""
        for name in wb_names:
            short = _esc(name[:18] + '..' if len(name) > 20 else name)
            html += f'<th class="matrix-cell">{short}</th>'
        html += '</tr>'

        for i, name_a in enumerate(wb_names):
            short_a = _esc(name_a[:18] + '..' if len(name_a) > 20 else name_a)
            html += f'<tr><td><strong>{short_a}</strong></td>'
            for j, name_b in enumerate(wb_names):
                if i == j:
                    html += ('<td class="matrix-cell" '
                             f'style="background:#e8f0fe;color:{PBI_BLUE}">'
                             '—</td>')
                else:
                    ps = pair_lookup.get((name_a, name_b))
                    if ps:
                        bg = _score_bg(ps.merge_score)
                        html += (f'<td class="matrix-cell" '
                                 f'style="background:{bg}" '
                                 f'title="{_esc(name_a)} &lt;-&gt; '
                                 f'{_esc(name_b)}: '
                                 f'{ps.shared_tables} shared tables">'
                                 f'{ps.merge_score}</td>')
                    else:
                        html += '<td class="matrix-cell">—</td>'
            html += '</tr>'
        html += '</table>'
        html += ('<p style="font-size:0.8em;color:#a19f9d;margin-top:8px">'
                 'Green = merge recommended (60+) &nbsp;|&nbsp; '
                 'Yellow = partial merge (30-59) &nbsp;|&nbsp; '
                 'Red = keep separate (&lt;30) &nbsp;|&nbsp; '
                 'Hover for details</p>')
        html += '</div></div>'

    # ══════════════════════════════════════════════════════════
    # 4. MERGE CLUSTERS
    # ══════════════════════════════════════════════════════════
    if result.merge_clusters:
        html += f"""
<h2 onclick="toggleSection('clusters')"><span class="section-icon">&#128279;</span>
Merge Clusters <span class="toggle-icon" id="clusters-icon">&#9660;</span></h2>
<div id="clusters" class="collapsible">
"""
        for cluster in result.merge_clusters:
            border_class = cluster.recommendation
            html += f'<div class="cluster-card {border_class}">'
            html += (f'<h3 style="margin-top:0">Cluster #{cluster.cluster_id + 1} '
                     f'— {_rec_badge(cluster.recommendation)} '
                     f'&nbsp; avg score: '
                     f'<span style="color:{_score_color(cluster.avg_score)}">'
                     f'{cluster.avg_score}/100</span></h3>')

            # Workbooks in cluster
            html += '<p><strong>Workbooks:</strong> '
            html += " ".join(
                f'<span class="connector-tag">{_esc(w)}</span>'
                for w in cluster.workbooks
            )
            html += '</p>'

            # Shared tables
            if cluster.shared_tables:
                html += '<p><strong>Shared tables:</strong> '
                html += ", ".join(
                    f'<span class="success-tag">{_esc(t)}</span>'
                    for t in cluster.shared_tables
                )
                html += '</p>'

            # Command to run merge
            wbs_arg = " ".join(
                f'"{w}.twbx"' if " " in w else f"{w}.twbx"
                for w in cluster.workbooks
            )
            cmd = (f'python migrate.py --shared-model {wbs_arg} '
                   f'--model-name "Cluster{cluster.cluster_id + 1}Model"')
            html += f'<p style="margin-top:10px"><strong>Run:</strong></p>'
            html += f'<div class="cmd-box">{_esc(cmd)}</div>'

            # Cluster merge details (if assessment available)
            if cluster.assessment:
                a = cluster.assessment
                html += '<div style="margin-top:15px">'
                # Merge candidates table
                if a.merge_candidates:
                    html += ('<table class="detail-table">'
                             '<tr><th>Table</th><th>Workbooks</th>'
                             '<th>Column Overlap</th>'
                             '<th>Conflicts</th></tr>')
                    for mc in a.merge_candidates:
                        wb_list = ", ".join(s[0] for s in mc.sources)
                        conflict_html = ""
                        if mc.conflicts:
                            conflict_html = "<br>".join(
                                f'<span class="danger-tag">{_esc(c)}</span>'
                                for c in mc.conflicts[:3]
                            )
                        else:
                            conflict_html = ('<span class="success-tag">'
                                             'None</span>')
                        html += (f'<tr><td><strong>{_esc(mc.table_name)}'
                                 f'</strong></td>'
                                 f'<td>{_esc(wb_list)}</td>'
                                 f'<td>{_overlap_bar(mc.column_overlap)}</td>'
                                 f'<td>{conflict_html}</td></tr>')
                    html += '</table>'

                # Measure conflicts
                if a.measure_conflicts:
                    html += '<h4 style="margin-top:12px">Measure Conflicts</h4>'
                    html += ('<table class="detail-table">'
                             '<tr><th>Measure</th><th>Workbook</th>'
                             '<th>Formula</th></tr>')
                    for mc in a.measure_conflicts:
                        first = True
                        for wb, formula in mc.variants.items():
                            short = _esc(
                                formula[:60] + '...'
                                if len(formula) > 60 else formula
                            )
                            name_cell = (
                                f'<td rowspan="{len(mc.variants)}">'
                                f'<strong>{_esc(mc.name)}</strong><br>'
                                f'<span class="danger-tag">CONFLICT</span>'
                                f'</td>'
                            ) if first else ''
                            html += (f'<tr>{name_cell}'
                                     f'<td><span class="connector-tag">'
                                     f'{_esc(wb)}</span></td>'
                                     f'<td class="mono">{short}</td></tr>')
                            first = False
                    html += '</table>'

                # Stats line
                html += (f'<p style="font-size:0.85em;color:{PBI_GRAY};'
                         f'margin-top:10px">'
                         f'Measures deduped: {a.measure_duplicates_removed} '
                         f'&nbsp;|&nbsp; '
                         f'Relationships deduped: '
                         f'{a.relationship_duplicates_removed} '
                         f'&nbsp;|&nbsp; '
                         f'Parameters deduped: '
                         f'{a.parameter_duplicates_removed}</p>')
                html += '</div>'

            html += '</div>'  # end cluster-card

        html += '</div>'  # end clusters collapsible

    # ══════════════════════════════════════════════════════════
    # 5. ISOLATED WORKBOOKS
    # ══════════════════════════════════════════════════════════
    if result.isolated_workbooks:
        html += f"""
<h2 onclick="toggleSection('isolated')"><span class="section-icon">&#128683;</span>
Isolated Workbooks <span class="toggle-icon" id="isolated-icon">&#9660;</span></h2>
<div id="isolated" class="collapsible">
<div class="card">
<p>These workbooks share no tables with others and should be migrated
individually.</p>
<table class="detail-table">
<tr><th>Workbook</th><th>Tables</th><th>Measures</th><th>Worksheets</th>
    <th>Connectors</th><th>Command</th></tr>
"""
        for wb_name in result.isolated_workbooks:
            p = next(
                (x for x in profiles if x.name == wb_name), None
            )
            if not p:
                continue
            conn_html = " ".join(
                f'<span class="connector-tag">{_esc(c)}</span>'
                for c in p.connection_types
            ) or "—"
            cmd = f'python migrate.py {_esc(wb_name)}.twbx'
            html += f"""<tr>
    <td><strong>{_esc(wb_name)}</strong></td>
    <td>{p.tables}</td><td>{p.measures}</td><td>{p.worksheets}</td>
    <td>{conn_html}</td>
    <td class="mono">{cmd}</td>
</tr>"""
        html += '</table></div></div>'

    # ══════════════════════════════════════════════════════════
    # 6. PAIRWISE DETAIL TABLE
    # ══════════════════════════════════════════════════════════
    if result.pairwise_scores:
        html += f"""
<h2 onclick="toggleSection('pairs')"><span class="section-icon">&#128295;</span>
Pairwise Detail <span class="toggle-icon" id="pairs-icon">&#9660;</span></h2>
<div id="pairs" class="collapsible">
<div class="card">
<table>
<tr><th>Workbook A</th><th>Workbook B</th><th>Score</th>
    <th>Shared Tables</th><th>Recommendation</th></tr>
"""
        for ps in sorted(result.pairwise_scores,
                         key=lambda x: x.merge_score, reverse=True):
            bg = _score_bg(ps.merge_score)
            html += f"""<tr>
    <td><strong>{_esc(ps.wb_a)}</strong></td>
    <td><strong>{_esc(ps.wb_b)}</strong></td>
    <td class="matrix-cell" style="background:{bg}">{ps.merge_score}</td>
    <td>{ps.shared_tables}</td>
    <td>{_rec_badge(ps.recommendation)}</td>
</tr>"""
        html += '</table></div></div>'

    # ══════════════════════════════════════════════════════════
    # FOOTER
    # ══════════════════════════════════════════════════════════
    html += f"""
<div class="footer">
    Tableau &#8594; Power BI Migration Tool v{_esc(tool_version)} &nbsp;|&nbsp;
    Global Assessment generated: {now} &nbsp;|&nbsp;
    {n} workbooks analyzed
</div>

</div><!-- /.container -->

<script>
function toggleSection(id) {{
    var el = document.getElementById(id);
    el.classList.toggle('collapsed');
    var icon = document.getElementById(id + '-icon');
    if (icon) {{
        icon.innerHTML = el.classList.contains('collapsed')
            ? '&#9654;' : '&#9660;';
    }}
}}
</script>
</body>
</html>"""

    # ── Write output ──
    if not output_path:
        output_path = 'global_assessment.html'

    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    logger.info("Global assessment HTML saved to %s", output_path)
    return output_path


def save_global_assessment_json(
    result: GlobalAssessment,
    output_path: str,
) -> str:
    """Save the global assessment as JSON.

    Args:
        result: GlobalAssessment to serialize.
        output_path: File path for JSON output.

    Returns:
        The output file path.
    """
    data = result.to_dict()
    data['timestamp'] = datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat()

    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info("Global assessment JSON saved to %s", output_path)
    return output_path
