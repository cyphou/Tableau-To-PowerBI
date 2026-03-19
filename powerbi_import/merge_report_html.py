"""
Shared Semantic Model — HTML Merge Report Generator.

Produces a visual HTML report showing:
- Tableau source inventory (per-workbook tables, measures, relationships)
- Power BI merged output (unified model structure)
- Merge details (how tables were matched, column overlap, conflicts resolved)
- Measure/relationship mapping (Tableau → Power BI, dedup/namespace)

Usage::

    from powerbi_import.merge_report_html import generate_merge_html_report

    html_path = generate_merge_html_report(
        assessment=assessment,
        all_extracted=all_extracted,
        workbook_names=workbook_names,
        merged=merged_objects,
        model_name="SharedModel",
        output_path="merge_report.html",
    )
"""

from __future__ import annotations

import datetime
import json
import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from powerbi_import.shared_model import MergeAssessment
except ImportError:
    from shared_model import MergeAssessment


# ═══════════════════════════════════════════════════════════════════
#  Color palette (matches generate_report.py)
# ═══════════════════════════════════════════════════════════════════
PBI_BLUE = "#0078d4"
PBI_DARK = "#323130"
PBI_GRAY = "#605e5c"
PBI_LIGHT_GRAY = "#a19f9d"
PBI_BG = "#f5f5f5"
SUCCESS = "#28a745"
WARN = "#ffc107"
FAIL = "#dc3545"


def _esc(text: str) -> str:
    """HTML-escape a string."""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def _safe_id(text: str) -> str:
    """Create a safe HTML id from arbitrary text (alphanumeric + underscore only)."""
    import re
    return re.sub(r'[^a-zA-Z0-9_]', '', text.replace(' ', '_'))


def _score_color(score: int) -> str:
    if score >= 60:
        return SUCCESS
    if score >= 30:
        return WARN
    return FAIL


def _overlap_bar(pct: float) -> str:
    """Render a % bar for column overlap."""
    width = max(int(pct * 100), 0)
    color = SUCCESS if pct >= 0.7 else WARN if pct >= 0.4 else FAIL
    return (
        f'<div style="background:#e9ecef;border-radius:4px;width:120px;'
        f'display:inline-block;vertical-align:middle">'
        f'<div style="background:{color};width:{width}%;height:16px;'
        f'border-radius:4px;text-align:center;font-size:11px;color:#fff;'
        f'line-height:16px">{width}%</div></div>'
    )


def _rec_badge(rec: str) -> str:
    """Render recommendation as styled badge."""
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


# ═══════════════════════════════════════════════════════════════════
#  Source inventory helpers
# ═══════════════════════════════════════════════════════════════════

def _count_tables(extracted: dict) -> int:
    count = 0
    for ds in extracted.get('datasources', []):
        count += sum(1 for t in ds.get('tables', []) if t.get('type', 'table') == 'table')
    return count


def _count_columns(extracted: dict) -> int:
    count = 0
    for ds in extracted.get('datasources', []):
        for t in ds.get('tables', []):
            count += len(t.get('columns', []))
    return count


def _count_measures(extracted: dict) -> int:
    count = 0
    for ds in extracted.get('datasources', []):
        for c in ds.get('calculations', []):
            if c.get('role', 'measure') == 'measure':
                count += 1
    for c in extracted.get('calculations', []):
        if c.get('role', 'measure') == 'measure':
            count += 1
    return count


def _count_calc_columns(extracted: dict) -> int:
    count = 0
    for ds in extracted.get('datasources', []):
        for c in ds.get('calculations', []):
            if c.get('role') == 'dimension':
                count += 1
    for c in extracted.get('calculations', []):
        if c.get('role') == 'dimension':
            count += 1
    return count


def _count_relationships(extracted: dict) -> int:
    count = 0
    for ds in extracted.get('datasources', []):
        count += len(ds.get('relationships', []))
    return count


def _get_connection_types(extracted: dict) -> list:
    types = set()
    for ds in extracted.get('datasources', []):
        conn = ds.get('connection', {})
        ct = conn.get('type', '')
        if ct:
            types.add(ct)
    return sorted(types)


def _get_table_names(extracted: dict) -> list:
    names = []
    for ds in extracted.get('datasources', []):
        for t in ds.get('tables', []):
            if t.get('type', 'table') == 'table':
                names.append(t.get('name', ''))
    return names


def _get_measures_list(extracted: dict) -> list:
    """Return list of (caption, formula) tuples for measures."""
    measures = []
    seen = set()
    for ds in extracted.get('datasources', []):
        for c in ds.get('calculations', []):
            if c.get('role', 'measure') == 'measure':
                caption = c.get('caption', c.get('name', ''))
                if caption not in seen:
                    seen.add(caption)
                    measures.append((caption, c.get('formula', '')))
    for c in extracted.get('calculations', []):
        if c.get('role', 'measure') == 'measure':
            caption = c.get('caption', c.get('name', ''))
            if caption not in seen:
                seen.add(caption)
                measures.append((caption, c.get('formula', '')))
    return measures


# ═══════════════════════════════════════════════════════════════════
#  Merged model helpers
# ═══════════════════════════════════════════════════════════════════

def _merged_table_count(merged: dict) -> int:
    for ds in merged.get('datasources', []):
        return sum(1 for t in ds.get('tables', []) if t.get('type', 'table') == 'table')
    return 0


def _merged_column_count(merged: dict) -> int:
    count = 0
    for ds in merged.get('datasources', []):
        for t in ds.get('tables', []):
            count += len(t.get('columns', []))
    return count


def _merged_relationship_count(merged: dict) -> int:
    for ds in merged.get('datasources', []):
        return len(ds.get('relationships', []))
    return 0


def _merged_measure_count(merged: dict) -> int:
    count = len([c for c in merged.get('calculations', [])
                 if c.get('role', 'measure') == 'measure'])
    for ds in merged.get('datasources', []):
        count += len([c for c in ds.get('calculations', [])
                      if c.get('role', 'measure') == 'measure'])
    return count


def _merged_tables_list(merged: dict) -> list:
    """Return list of (name, col_count) for merged tables."""
    tables = []
    for ds in merged.get('datasources', []):
        for t in ds.get('tables', []):
            if t.get('type', 'table') == 'table':
                tables.append((t.get('name', ''), len(t.get('columns', []))))
    return tables


def _merged_measures_list(merged: dict) -> list:
    """Return list of (caption, formula, source_wb_or_None) for merged measures."""
    measures = []
    for c in merged.get('calculations', []):
        if c.get('role', 'measure') == 'measure':
            caption = c.get('caption', c.get('name', ''))
            formula = c.get('formula', '')
            src = c.get('_source_workbook', None)
            original = c.get('_original_caption', None)
            measures.append((caption, formula, src, original))
    for ds in merged.get('datasources', []):
        for c in ds.get('calculations', []):
            if c.get('role', 'measure') == 'measure':
                caption = c.get('caption', c.get('name', ''))
                formula = c.get('formula', '')
                measures.append((caption, formula, None, None))
    return measures


# ═══════════════════════════════════════════════════════════════════
#  Main HTML generator
# ═══════════════════════════════════════════════════════════════════

def generate_merge_html_report(
    assessment: MergeAssessment,
    all_extracted: List[dict],
    workbook_names: List[str],
    merged: dict,
    model_name: str = "SharedModel",
    output_path: Optional[str] = None,
) -> str:
    """Generate the HTML merge report.

    Args:
        assessment: The MergeAssessment from assess_merge().
        all_extracted: Original extracted data per workbook.
        workbook_names: Workbook names (parallel with all_extracted).
        merged: The merged converted_objects from merge_semantic_models().
        model_name: Name of the shared semantic model.
        output_path: File path for the HTML output.

    Returns:
        The output file path.
    """
    try:
        from powerbi_import import __version__ as tool_version
    except Exception:
        tool_version = "13.0.0"

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    score = assessment.merge_score
    score_color = _score_color(score)

    # ── Compute per-workbook stats ──
    wb_stats = []
    for wb_name, extracted in zip(workbook_names, all_extracted):
        wb_stats.append({
            'name': wb_name,
            'tables': _count_tables(extracted),
            'columns': _count_columns(extracted),
            'measures': _count_measures(extracted),
            'calc_columns': _count_calc_columns(extracted),
            'relationships': _count_relationships(extracted),
            'connectors': _get_connection_types(extracted),
            'table_names': _get_table_names(extracted),
            'worksheets': len(extracted.get('worksheets', [])),
            'dashboards': len(extracted.get('dashboards', [])),
            'parameters': len(extracted.get('parameters', [])),
        })

    # ── Merged model stats ──
    merged_stats = {
        'tables': _merged_table_count(merged),
        'columns': _merged_column_count(merged),
        'measures': _merged_measure_count(merged),
        'relationships': _merged_relationship_count(merged),
        'parameters': len(merged.get('parameters', [])),
    }

    # Total source stats
    total_src_tables = sum(s['tables'] for s in wb_stats)
    total_src_measures = sum(s['measures'] for s in wb_stats)
    total_src_rels = sum(s['relationships'] for s in wb_stats)
    tables_saved = total_src_tables - merged_stats['tables']

    # ══════════════════════════════════════════════════════════════
    #  Build HTML
    # ══════════════════════════════════════════════════════════════

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Shared Semantic Model — Merge Report</title>
<style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; background: {PBI_BG}; color: {PBI_DARK}; }}
    .container {{ max-width: 1400px; margin: 0 auto; }}
    h1 {{ color: {PBI_BLUE}; border-bottom: 3px solid {PBI_BLUE}; padding-bottom: 10px; font-size: 1.6em; }}
    h2 {{ color: {PBI_DARK}; margin-top: 30px; font-size: 1.25em; cursor: pointer; }}
    h2:hover {{ color: {PBI_BLUE}; }}
    h3 {{ color: {PBI_GRAY}; margin-top: 20px; }}
    .card {{ background: #fff; border-radius: 8px; padding: 20px; margin: 15px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
    .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; }}
    .stat {{ background: #fff; border-radius: 8px; padding: 16px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); transition: transform 0.15s; }}
    .stat:hover {{ transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,0.15); }}
    .stat .number {{ font-size: 2em; font-weight: bold; color: {PBI_BLUE}; }}
    .stat .label {{ font-size: 0.85em; color: {PBI_GRAY}; margin-top: 4px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
    th {{ background: {PBI_BLUE}; color: #fff; padding: 10px 12px; text-align: left; font-size: 0.85em; position: sticky; top: 0; }}
    td {{ padding: 8px 12px; border-bottom: 1px solid #e1dfdd; font-size: 0.85em; }}
    tr:hover {{ background: #f3f2f1; }}
    .detail-table th {{ background: {PBI_GRAY}; }}
    .footer {{ text-align: center; color: {PBI_LIGHT_GRAY}; font-size: 0.85em; margin-top: 40px; padding: 20px; }}
    .connector-tag {{ background: #e8f0fe; color: #1a73e8; padding: 2px 6px; border-radius: 3px; font-size: 0.82em; white-space: nowrap; }}
    .warn-tag {{ background: #fff3cd; color: #856404; padding: 2px 6px; border-radius: 3px; font-size: 0.82em; }}
    .success-tag {{ background: #d4edda; color: #155724; padding: 2px 6px; border-radius: 3px; font-size: 0.82em; }}
    .danger-tag {{ background: #f8d7da; color: #721c24; padding: 2px 6px; border-radius: 3px; font-size: 0.82em; }}
    .merge-arrow {{ color: {PBI_BLUE}; font-weight: bold; font-size: 1.2em; padding: 0 8px; }}
    .mono {{ font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 0.82em; }}
    .section-icon {{ font-size: 1.2em; margin-right: 4px; }}
    .collapsible {{ overflow: hidden; transition: max-height 0.3s ease-out; max-height: 5000px; }}
    .collapsed {{ max-height: 0 !important; }}
    .toggle-icon {{ float: right; font-size: 0.8em; color: {PBI_LIGHT_GRAY}; }}
    .tab-bar {{ display: flex; gap: 2px; border-bottom: 2px solid #e1dfdd; margin-bottom: 15px; }}
    .tab {{ padding: 8px 16px; cursor: pointer; font-size: 0.9em; border-radius: 4px 4px 0 0; transition: background 0.2s; color: {PBI_GRAY}; }}
    .tab:hover {{ background: #e8f0fe; }}
    .tab.active {{ background: {PBI_BLUE}; color: #fff; font-weight: bold; }}
    .tab-content {{ display: none; }}
    .tab-content.active {{ display: block; }}
    .flow-box {{ display: inline-block; padding: 12px 20px; border-radius: 8px; text-align: center; font-weight: bold; font-size: 0.95em; }}
    .flow-arrow {{ display: inline-block; font-size: 1.8em; color: {PBI_BLUE}; vertical-align: middle; padding: 0 10px; }}
    @media print {{
        .collapsible {{ max-height: none !important; }}
        h2 {{ cursor: default; }}
        .toggle-icon {{ display: none; }}
    }}
</style>
</head>
<body>
<div class="container">
<h1>&#128279; Shared Semantic Model — Merge Report</h1>
<p style="color:{PBI_GRAY};font-size:0.9em">
    Generated: {now} &nbsp;|&nbsp; Tool: v{tool_version} &nbsp;|&nbsp;
    Model: <strong>{_esc(model_name)}</strong> &nbsp;|&nbsp;
    Workbooks: {len(workbook_names)}
</p>
"""

    # ══════════════════════════════════════════════════════════════
    # 1. EXECUTIVE SUMMARY
    # ══════════════════════════════════════════════════════════════
    html += f"""
<h2 onclick="toggleSection('exec')"><span class="section-icon">&#128200;</span>
Executive Summary <span class="toggle-icon" id="exec-icon">&#9660;</span></h2>
<div id="exec" class="collapsible">
<div class="stats">
    <div class="stat"><div class="number">{len(workbook_names)}</div><div class="label">Workbooks</div></div>
    <div class="stat"><div class="number" style="color:{score_color}">{score}/100</div><div class="label">Merge Score</div></div>
    <div class="stat"><div class="number">{total_src_tables}</div><div class="label">Source Tables</div></div>
    <div class="stat"><div class="number" style="color:{SUCCESS}">{merged_stats['tables']}</div><div class="label">Merged Tables</div></div>
    <div class="stat"><div class="number" style="color:{SUCCESS}">{tables_saved}</div><div class="label">Tables Saved</div></div>
    <div class="stat"><div class="number">{assessment.measure_duplicates_removed}</div><div class="label">Measures Deduped</div></div>
    <div class="stat"><div class="number">{assessment.relationship_duplicates_removed}</div><div class="label">Rels Deduped</div></div>
    <div class="stat"><div class="number" style="color:{WARN if assessment.measure_conflicts else SUCCESS}">{len(assessment.measure_conflicts)}</div><div class="label">Conflicts</div></div>
</div>

<div class="card" style="margin-top:15px;text-align:center">
    <div class="flow-box" style="background:#e8f0fe;color:#1a73e8">
        {len(workbook_names)} Tableau Workbooks<br>
        <span style="font-size:0.8em;font-weight:normal">{total_src_tables} tables &bull; {total_src_measures} measures</span>
    </div>
    <span class="flow-arrow">&#10132;</span>
    <div class="flow-box" style="background:#fff3cd;color:#856404">
        Merge Engine<br>
        <span style="font-size:0.8em;font-weight:normal">Score: {score}/100 &bull; {_rec_badge(assessment.recommendation)}</span>
    </div>
    <span class="flow-arrow">&#10132;</span>
    <div class="flow-box" style="background:#d4edda;color:#155724">
        1 Shared Semantic Model<br>
        <span style="font-size:0.8em;font-weight:normal">{merged_stats['tables']} tables &bull; {merged_stats['measures']} measures &bull; {merged_stats['relationships']} rels</span>
    </div>
    <span class="flow-arrow">+</span>
    <div class="flow-box" style="background:#d4edda;color:#155724">
        {len(workbook_names)} Thin Reports<br>
        <span style="font-size:0.8em;font-weight:normal">byPath &#8594; {_esc(model_name)}.SemanticModel</span>
    </div>
</div>
</div>
"""

    # ══════════════════════════════════════════════════════════════
    # 2. TABLEAU SOURCE INVENTORY
    # ══════════════════════════════════════════════════════════════
    html += f"""
<h2 onclick="toggleSection('source')"><span class="section-icon">&#128214;</span>
Tableau Source Inventory <span class="toggle-icon" id="source-icon">&#9660;</span></h2>
<div id="source" class="collapsible">
<div class="card">
<table>
<tr>
    <th>Workbook</th><th>Connectors</th><th>Tables</th><th>Columns</th>
    <th>Measures</th><th>Calc Columns</th><th>Relationships</th>
    <th>Worksheets</th><th>Parameters</th>
</tr>
"""
    for ws in wb_stats:
        conn_html = " ".join(
            f'<span class="connector-tag">{_esc(c)}</span>' for c in ws['connectors']
        ) or "—"
        html += f"""<tr>
    <td><strong>{_esc(ws['name'])}</strong></td>
    <td>{conn_html}</td>
    <td>{ws['tables']}</td><td>{ws['columns']}</td>
    <td>{ws['measures']}</td><td>{ws['calc_columns']}</td>
    <td>{ws['relationships']}</td>
    <td>{ws['worksheets']}</td><td>{ws['parameters']}</td>
</tr>"""

    # Totals row
    html += f"""<tr style="background:#e8f0fe;font-weight:bold">
    <td>TOTAL</td><td></td>
    <td>{total_src_tables}</td><td>{sum(s['columns'] for s in wb_stats)}</td>
    <td>{total_src_measures}</td><td>{sum(s['calc_columns'] for s in wb_stats)}</td>
    <td>{total_src_rels}</td>
    <td>{sum(s['worksheets'] for s in wb_stats)}</td>
    <td>{sum(s['parameters'] for s in wb_stats)}</td>
</tr>"""
    html += "</table></div></div>"

    # ══════════════════════════════════════════════════════════════
    # 3. POWER BI MERGED OUTPUT
    # ══════════════════════════════════════════════════════════════
    html += f"""
<h2 onclick="toggleSection('output')"><span class="section-icon">&#9889;</span>
Power BI Merged Output <span class="toggle-icon" id="output-icon">&#9660;</span></h2>
<div id="output" class="collapsible">
<div class="stats">
    <div class="stat"><div class="number" style="color:{PBI_BLUE}">{merged_stats['tables']}</div><div class="label">Tables</div></div>
    <div class="stat"><div class="number">{merged_stats['columns']}</div><div class="label">Columns</div></div>
    <div class="stat"><div class="number">{merged_stats['measures']}</div><div class="label">Measures</div></div>
    <div class="stat"><div class="number">{merged_stats['relationships']}</div><div class="label">Relationships</div></div>
    <div class="stat"><div class="number">{merged_stats['parameters']}</div><div class="label">Parameters</div></div>
    <div class="stat"><div class="number">{len(workbook_names)}</div><div class="label">Thin Reports</div></div>
</div>

<div class="card">
<h3>Merged Tables</h3>
<table class="detail-table">
<tr><th>Table Name</th><th>Columns</th><th>Source Workbooks</th><th>Merge Action</th></tr>
"""
    # Build table → source workbooks mapping from merge candidates
    table_sources = {}
    for mc in assessment.merge_candidates:
        table_sources[mc.table_name] = [s[0] for s in mc.sources]

    for tname, col_count in _merged_tables_list(merged):
        sources = table_sources.get(tname, [])
        if sources:
            src_html = ", ".join(f'<span class="connector-tag">{_esc(s)}</span>' for s in sources)
            action = '<span class="success-tag">Merged</span>'
        else:
            # Unique table — find which workbook it came from
            owner = "—"
            for wb_name, ws in zip(workbook_names, wb_stats):
                if tname in ws['table_names']:
                    owner = wb_name
                    break
            src_html = f'<span class="connector-tag">{_esc(owner)}</span>'
            action = '<span class="warn-tag">Unique (kept as-is)</span>'
        html += f"""<tr>
    <td><strong>{_esc(tname)}</strong></td>
    <td>{col_count}</td>
    <td>{src_html}</td>
    <td>{action}</td>
</tr>"""

    html += "</table></div></div>"

    # ══════════════════════════════════════════════════════════════
    # 4. MERGE DETAILS — TABLE MATCHING
    # ══════════════════════════════════════════════════════════════
    html += f"""
<h2 onclick="toggleSection('details')"><span class="section-icon">&#128269;</span>
Merge Details — Table Matching <span class="toggle-icon" id="details-icon">&#9660;</span></h2>
<div id="details" class="collapsible">
"""

    if assessment.merge_candidates:
        html += """<div class="card">
<table>
<tr>
    <th>Table</th><th>Fingerprint</th><th>Workbooks</th>
    <th>Column Overlap</th><th>Conflicts</th>
</tr>
"""
        for mc in assessment.merge_candidates:
            fp = mc.fingerprint
            fp_parts = f"{_esc(fp.connection_type)} | {_esc(fp.server)} | {_esc(fp.database)} | {_esc(fp.table_name)}"
            wb_list = ", ".join(s[0] for s in mc.sources)
            conflict_html = ""
            if mc.conflicts:
                conflict_html = "<br>".join(
                    f'<span class="danger-tag">{_esc(c)}</span>' for c in mc.conflicts[:5]
                )
            else:
                conflict_html = '<span class="success-tag">None</span>'

            html += f"""<tr>
    <td><strong>{_esc(mc.table_name)}</strong></td>
    <td class="mono" style="max-width:300px;word-break:break-all">{fp_parts}</td>
    <td>{_esc(wb_list)}</td>
    <td>{_overlap_bar(mc.column_overlap)}</td>
    <td>{conflict_html}</td>
</tr>"""
        html += "</table></div>"
    else:
        html += '<div class="card"><p style="color:#a19f9d">No merge candidates found — tables are all unique across workbooks.</p></div>'

    # Unique tables section
    if assessment.unique_tables:
        html += """<div class="card">
<h3>Unique Tables (no matching across workbooks)</h3>
<table class="detail-table">
<tr><th>Table</th><th>Workbook</th></tr>
"""
        for wb, tables in assessment.unique_tables.items():
            for t in tables:
                html += f'<tr><td>{_esc(t)}</td><td><span class="connector-tag">{_esc(wb)}</span></td></tr>'
        html += "</table></div>"

    html += "</div>"  # end details section

    # ══════════════════════════════════════════════════════════════
    # 5. MEASURE MAPPING
    # ══════════════════════════════════════════════════════════════
    html += f"""
<h2 onclick="toggleSection('measures')"><span class="section-icon">&#128202;</span>
Measure Mapping — Tableau to Power BI <span class="toggle-icon" id="measures-icon">&#9660;</span></h2>
<div id="measures" class="collapsible">
"""

    # Build source measures per workbook
    all_source_measures = {}
    for wb_name, extracted in zip(workbook_names, all_extracted):
        all_source_measures[wb_name] = _get_measures_list(extracted)

    # Tabs: one per workbook + "Conflicts" tab
    has_conflicts = bool(assessment.measure_conflicts)
    html += '<div class="tab-bar">'
    html += '<div class="tab active" onclick="switchTab(\'meas\', \'all\')">All Measures</div>'
    for wb_name in workbook_names:
        safe = _safe_id(wb_name)
        html += f'<div class="tab" onclick="switchTab(\'meas\', \'{safe}\')">{_esc(wb_name)}</div>'
    if has_conflicts:
        html += '<div class="tab" onclick="switchTab(\'meas\', \'conflicts\')" style="color:#dc3545">&#9888; Conflicts</div>'
    html += '</div>'

    # All measures tab — merged output
    merged_measures = _merged_measures_list(merged)
    html += '<div class="tab-content active" id="meas-all"><div class="card">'
    html += '<table class="detail-table"><tr><th>Power BI Measure</th><th>DAX Formula</th><th>Action</th><th>Source</th></tr>'
    for caption, formula, src_wb, original in merged_measures:
        short_formula = _esc(formula[:80] + '...' if len(formula) > 80 else formula)
        if src_wb:
            action = f'<span class="warn-tag">Namespaced from [{_esc(original or caption)}]</span>'
            src = f'<span class="connector-tag">{_esc(src_wb)}</span>'
        else:
            action = '<span class="success-tag">Kept / Deduped</span>'
            src = '<span class="connector-tag">Shared</span>'
        html += f"""<tr>
    <td><strong>{_esc(caption)}</strong></td>
    <td class="mono" style="max-width:400px;word-break:break-all">{short_formula}</td>
    <td>{action}</td><td>{src}</td>
</tr>"""
    if not merged_measures:
        html += '<tr><td colspan="4" style="color:#a19f9d;text-align:center">No measures</td></tr>'
    html += '</table></div></div>'

    # Per-workbook tabs
    for wb_name in workbook_names:
        safe = _safe_id(wb_name)
        measures = all_source_measures.get(wb_name, [])
        html += f'<div class="tab-content" id="meas-{safe}"><div class="card">'
        html += f'<table class="detail-table"><tr><th>Tableau Measure</th><th>Tableau Formula</th><th>&#10132; Power BI</th></tr>'
        for caption, formula in measures:
            # Find what it became in merged model
            pbi_name = caption
            action_label = "Kept"
            for mc in assessment.measure_conflicts:
                if mc.name == caption and wb_name in mc.variants:
                    pbi_name = f"{caption} ({wb_name})"
                    action_label = "Namespaced"
                    break
            short_formula = _esc(formula[:80] + '...' if len(formula) > 80 else formula)
            html += f"""<tr>
    <td><strong>{_esc(caption)}</strong></td>
    <td class="mono" style="max-width:350px;word-break:break-all">{short_formula}</td>
    <td><span class="merge-arrow">&#10132;</span> <strong>{_esc(pbi_name)}</strong>
        <br><span class="{'warn-tag' if action_label == 'Namespaced' else 'success-tag'}">{action_label}</span></td>
</tr>"""
        if not measures:
            html += '<tr><td colspan="3" style="color:#a19f9d;text-align:center">No measures in this workbook</td></tr>'
        html += '</table></div></div>'

    # Conflicts tab
    if has_conflicts:
        html += '<div class="tab-content" id="meas-conflicts"><div class="card">'
        html += '<table class="detail-table"><tr><th>Measure Name</th><th>Workbook</th><th>Tableau Formula</th><th>&#10132; Power BI Name</th></tr>'
        for mc in assessment.measure_conflicts:
            first = True
            for wb, formula in mc.variants.items():
                short = _esc(formula[:80] + '...' if len(formula) > 80 else formula)
                name_cell = f'<td rowspan="{len(mc.variants)}"><strong>{_esc(mc.name)}</strong><br><span class="danger-tag">CONFLICT</span></td>' if first else ''
                pbi_name = f"{mc.name} ({wb})"
                html += f"""<tr>
    {name_cell}
    <td><span class="connector-tag">{_esc(wb)}</span></td>
    <td class="mono" style="max-width:350px;word-break:break-all">{short}</td>
    <td><strong>{_esc(pbi_name)}</strong></td>
</tr>"""
                first = False
        html += '</table></div></div>'

    html += "</div>"

    # ══════════════════════════════════════════════════════════════
    # 6. RELATIONSHIP MAPPING
    # ══════════════════════════════════════════════════════════════
    html += f"""
<h2 onclick="toggleSection('rels')"><span class="section-icon">&#128279;</span>
Relationship Mapping <span class="toggle-icon" id="rels-icon">&#9660;</span></h2>
<div id="rels" class="collapsible">
<div class="card">
"""

    # Collect all source relationships
    all_src_rels = []
    for wb_name, extracted in zip(workbook_names, all_extracted):
        for ds in extracted.get('datasources', []):
            for rel in ds.get('relationships', []):
                all_src_rels.append((wb_name, rel))

    # Merged relationships
    merged_rels = []
    for ds in merged.get('datasources', []):
        merged_rels = ds.get('relationships', [])
        break

    html += f"""<p>Source relationships: <strong>{len(all_src_rels)}</strong> &nbsp;&#10132;&nbsp;
Merged (deduplicated): <strong>{len(merged_rels)}</strong> &nbsp;
(<span class="success-tag">{assessment.relationship_duplicates_removed} duplicates removed</span>)</p>
<table class="detail-table">
<tr><th>From Table</th><th>From Column</th><th>&#10132;</th><th>To Table</th><th>To Column</th><th>Cardinality</th></tr>
"""
    for rel in merged_rels:
        if 'left' in rel:
            ft, fc = rel['left'].get('table', ''), rel['left'].get('column', '')
            tt, tc = rel['right'].get('table', ''), rel['right'].get('column', '')
        else:
            ft, fc = rel.get('from_table', ''), rel.get('from_column', '')
            tt, tc = rel.get('to_table', ''), rel.get('to_column', '')
        card = rel.get('cardinality', rel.get('join_type', '—'))
        html += f"""<tr>
    <td><strong>{_esc(ft)}</strong></td>
    <td class="mono">{_esc(fc)}</td>
    <td style="text-align:center;color:{PBI_BLUE};font-weight:bold">&#10132;</td>
    <td><strong>{_esc(tt)}</strong></td>
    <td class="mono">{_esc(tc)}</td>
    <td><span class="connector-tag">{_esc(card)}</span></td>
</tr>"""
    if not merged_rels:
        html += '<tr><td colspan="6" style="color:#a19f9d;text-align:center">No relationships</td></tr>'

    html += "</table></div></div>"

    # ══════════════════════════════════════════════════════════════
    # 7. PARAMETER & CONFLICT SUMMARY
    # ══════════════════════════════════════════════════════════════
    if assessment.parameter_conflicts or assessment.parameter_duplicates_removed > 0:
        html += f"""
<h2 onclick="toggleSection('params')"><span class="section-icon">&#9881;</span>
Parameters <span class="toggle-icon" id="params-icon">&#9660;</span></h2>
<div id="params" class="collapsible">
<div class="card">
<p>Duplicates removed: <strong>{assessment.parameter_duplicates_removed}</strong> &nbsp;|&nbsp;
Conflicts: <strong>{len(assessment.parameter_conflicts)}</strong></p>
"""
        if assessment.parameter_conflicts:
            html += '<table class="detail-table"><tr><th>Parameter</th><th>Workbook</th><th>Type</th><th>Value</th></tr>'
            for pc in assessment.parameter_conflicts:
                pname = pc.get('name', '')
                first = True
                for wb, details in pc.get('variants', {}).items():
                    name_cell = f'<td rowspan="{len(pc["variants"])}"><strong>{_esc(pname)}</strong><br><span class="warn-tag">CONFLICT</span></td>' if first else ''
                    html += f"""<tr>
    {name_cell}
    <td><span class="connector-tag">{_esc(wb)}</span></td>
    <td>{_esc(details.get('datatype', ''))}</td>
    <td class="mono">{_esc(str(details.get('current_value', '')))}</td>
</tr>"""
                    first = False
            html += '</table>'
        html += "</div></div>"

    # ══════════════════════════════════════════════════════════════
    # 8. SECURITY — RLS ROLES
    # ══════════════════════════════════════════════════════════════
    rls_roles = merged.get('user_filters', [])
    if rls_roles:
        # Import validation helpers
        try:
            from powerbi_import.shared_model import (
                validate_rls_propagation,
                validate_rls_principals,
            )
            propagation = {r['role']: r for r in validate_rls_propagation(merged)}
            principals = {r['role']: r for r in validate_rls_principals(merged)}
        except Exception:
            propagation = {}
            principals = {}

        html += f"""
<h2 onclick="toggleSection('security')"><span class="section-icon">&#128274;</span>
Security &mdash; RLS Roles ({len(rls_roles)}) <span class="toggle-icon" id="security-icon">&#9660;</span></h2>
<div id="security" class="collapsible">
<div class="card">
<table class="detail-table">
<tr><th>Role</th><th>Table</th><th>Expression</th><th>Propagation</th><th>Principal Format</th><th>Source</th></tr>"""
        for uf in rls_roles:
            role_name = uf.get('name', uf.get('field', ''))
            table = uf.get('table', '')
            expr = uf.get('filter_expression', uf.get('formula', ''))[:120]
            source_wbs = ', '.join(uf.get('_source_workbooks', []))
            # Propagation status
            prop = propagation.get(role_name, {})
            prop_status = prop.get('status', '')
            if prop_status == 'ok':
                prop_html = '<span style="color:#107c10">&#10003; Connected</span>'
            elif prop_status == 'warning':
                prop_html = f'<span style="color:#ca5010">&#9888; {_esc(prop.get("reason", ""))}</span>'
            elif prop_status == 'error':
                prop_html = f'<span style="color:#d13438">&#10007; {_esc(prop.get("reason", ""))}</span>'
            else:
                prop_html = '<span style="color:#a19f9d">N/A</span>'
            # Principal format
            princ = principals.get(role_name, {})
            princ_fmt = _esc(princ.get('format_detected', ''))
            html += f"""<tr>
    <td><strong>{_esc(role_name)}</strong></td>
    <td>{_esc(table)}</td>
    <td class="mono" style="max-width:300px;word-break:break-all">{_esc(expr)}</td>
    <td>{prop_html}</td>
    <td>{princ_fmt}</td>
    <td>{_esc(source_wbs)}</td>
</tr>"""
        html += "</table></div></div>"

    # ══════════════════════════════════════════════════════════════
    # FOOTER
    # ══════════════════════════════════════════════════════════════
    html += f"""
<div class="footer">
    Tableau &#8594; Power BI Migration Tool v{tool_version} &nbsp;|&nbsp;
    Report generated: {now} &nbsp;|&nbsp;
    Model: {_esc(model_name)}
</div>

</div><!-- /.container -->

<script>
function toggleSection(id) {{
    var el = document.getElementById(id);
    el.classList.toggle('collapsed');
    var icon = document.getElementById(id + '-icon');
    if (icon) icon.innerHTML = el.classList.contains('collapsed') ? '&#9654;' : '&#9660;';
}}
function switchTab(group, tabId) {{
    var contents = document.querySelectorAll('[id^="' + group + '-"]');
    contents.forEach(function(c) {{ c.classList.remove('active'); }});
    var target = document.getElementById(group + '-' + tabId);
    if (target) target.classList.add('active');
    var bar = target ? target.parentElement.querySelector('.tab-bar') : null;
    if (!bar) {{
        // Find tab bar by walking siblings
        var sibling = target;
        while (sibling && !sibling.classList.contains('tab-bar')) sibling = sibling.previousElementSibling;
        bar = sibling;
    }}
    if (bar) {{
        bar.querySelectorAll('.tab').forEach(function(t) {{ t.classList.remove('active'); }});
        // Find matching tab
        bar.querySelectorAll('.tab').forEach(function(t) {{
            if (t.getAttribute('onclick') && t.getAttribute('onclick').indexOf("'" + tabId + "'") !== -1) {{
                t.classList.add('active');
            }}
        }});
    }}
}}
</script>
</body>
</html>"""

    # ── Write output ──
    if not output_path:
        output_path = 'merge_report.html'

    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    logger.info("Merge HTML report saved to %s", output_path)
    return output_path
