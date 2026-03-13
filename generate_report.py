#!/usr/bin/env python3
"""Generate a consolidated Migration & Assessment Report (HTML) from artifacts."""

import json
import os
import glob
import datetime

BASE = "artifacts/powerbi_projects"
ASSESSMENTS_DIR = os.path.join(BASE, "assessments")
REPORTS_DIR = os.path.join(BASE, "reports")
MIGRATED_DIR = os.path.join(BASE, "migrated")
OUTPUT = os.path.join(BASE, "MIGRATION_ASSESSMENT_REPORT.html")


def load_assessments():
    """Load all assessment JSON files."""
    assessments = {}
    for d in sorted(glob.glob(os.path.join(ASSESSMENTS_DIR, "assessment_*.json"))):
        if os.path.isdir(d):
            name = os.path.basename(d).replace("assessment_", "").replace(".json", "")
            for f in glob.glob(os.path.join(d, "*.json")):
                with open(f, encoding="utf-8") as fh:
                    data = json.load(fh)
                    assessments[name] = data
    return assessments


def load_migration_reports():
    """Load latest migration report per workbook."""
    reports = {}
    for f in sorted(glob.glob(os.path.join(REPORTS_DIR, "migration_report_*.json"))):
        if os.path.isfile(f):
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
                name = data.get("report_name", "")
                if name not in reports or data.get("created_at", "") > reports[name].get("created_at", ""):
                    reports[name] = data
    return reports


def load_metadata():
    """Load migration_metadata.json from each project directory."""
    metadata = {}
    for d in sorted(glob.glob(os.path.join(MIGRATED_DIR, "*"))):
        if os.path.isdir(d):
            meta_file = os.path.join(d, "migration_metadata.json")
            if os.path.isfile(meta_file):
                with open(meta_file, encoding="utf-8") as fh:
                    metadata[os.path.basename(d)] = json.load(fh)
    return metadata


def badge(score):
    """Return colored badge HTML for assessment score."""
    colors = {"GREEN": "#28a745", "YELLOW": "#ffc107", "RED": "#dc3545"}
    color = colors.get(score, "#6c757d")
    text_color = "#000" if score == "YELLOW" else "#fff"
    return f'<span style="background:{color};color:{text_color};padding:2px 8px;border-radius:4px;font-weight:bold;font-size:0.85em">{score}</span>'


def fidelity_bar(pct):
    """Return a visual progress bar for fidelity percentage."""
    color = "#28a745" if pct >= 95 else "#ffc107" if pct >= 80 else "#dc3545"
    return f'''<div style="background:#e9ecef;border-radius:4px;width:120px;display:inline-block;vertical-align:middle">
        <div style="background:{color};width:{pct:.0f}%;height:16px;border-radius:4px;text-align:center;font-size:11px;color:#fff;line-height:16px">{pct:.1f}%</div>
    </div>'''


def generate_html(assessments, reports, metadata):
    """Generate consolidated HTML report."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    # Import version
    try:
        from powerbi_import import __version__ as tool_version
    except Exception:
        tool_version = "12.0.0"

    # Compute aggregate stats
    total_workbooks = len(set(list(assessments.keys()) + list(reports.keys())))
    green = sum(1 for a in assessments.values() if a.get("overall_score") == "GREEN")
    yellow = sum(1 for a in assessments.values() if a.get("overall_score") == "YELLOW")
    red = sum(1 for a in assessments.values() if a.get("overall_score") == "RED")
    avg_fidelity = 0
    fidelity_scores = [r.get("summary", {}).get("fidelity_score", 0) for r in reports.values()]
    if fidelity_scores:
        avg_fidelity = sum(fidelity_scores) / len(fidelity_scores)

    total_items = sum(r.get("summary", {}).get("total_items", 0) for r in reports.values())
    total_exact = sum(r.get("summary", {}).get("exact", 0) for r in reports.values())
    total_approx = sum(r.get("summary", {}).get("approximate", 0) for r in reports.values())
    total_unsupported = sum(r.get("summary", {}).get("unsupported", 0) for r in reports.values())

    total_tables = sum(m.get("tmdl_stats", {}).get("tables", 0) for m in metadata.values())
    total_measures = sum(m.get("tmdl_stats", {}).get("measures", 0) for m in metadata.values())
    total_columns = sum(m.get("tmdl_stats", {}).get("columns", 0) for m in metadata.values())
    total_relationships = sum(m.get("tmdl_stats", {}).get("relationships", 0) for m in metadata.values())
    total_pages = sum(m.get("generated_output", {}).get("pages", 0) for m in metadata.values())
    total_visuals = sum(m.get("generated_output", {}).get("visuals", 0) for m in metadata.values())

    # Aggregate by-category breakdown
    cat_totals = {}
    for r in reports.values():
        by_cat = r.get("summary", {}).get("by_category", {})
        for cat, vals in by_cat.items():
            if cat not in cat_totals:
                cat_totals[cat] = {"total": 0, "exact": 0, "approx": 0}
            cat_totals[cat]["total"] += vals.get("total", 0)
            cat_totals[cat]["exact"] += vals.get("exact", 0)
            cat_totals[cat]["approx"] += vals.get("approximate", 0)

    # Connector distribution
    connector_counts = {}
    for r in reports.values():
        for tm in r.get("table_mapping", []):
            ct = tm.get("connection_type", "Unknown")
            connector_counts[ct] = connector_counts.get(ct, 0) + 1

    # Per-workbook complexity data for chart
    wb_complexity = {}
    all_names = sorted(set(list(assessments.keys()) + list(reports.keys())))
    for name in all_names:
        m = metadata.get(name, {})
        tmdl = m.get("tmdl_stats", {})
        gen = m.get("generated_output", {})
        obj = m.get("objects_converted", {})
        wb_complexity[name] = {
            "tables": tmdl.get("tables", 0),
            "measures": tmdl.get("measures", 0),
            "columns": tmdl.get("columns", 0),
            "relationships": tmdl.get("relationships", 0),
            "pages": gen.get("pages", 0),
            "visuals": gen.get("visuals", 0),
            "calculations": obj.get("calculations", 0),
            "filters": obj.get("filters", 0),
            "worksheets": obj.get("worksheets", 0),
            "dashboards": obj.get("dashboards", 0),
        }

    # CSS color palette
    pbi_blue = "#0078d4"
    pbi_dark = "#323130"
    pbi_gray = "#605e5c"
    pbi_light_gray = "#a19f9d"
    pbi_bg = "#f5f5f5"
    success_green = "#28a745"
    warn_yellow = "#ffc107"
    fail_red = "#dc3545"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tableau to Power BI — Migration Dashboard</title>
<style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; background: {pbi_bg}; color: {pbi_dark}; }}
    .container {{ max-width: 1400px; margin: 0 auto; }}
    h1 {{ color: {pbi_blue}; border-bottom: 3px solid {pbi_blue}; padding-bottom: 10px; font-size: 1.6em; }}
    h2 {{ color: {pbi_dark}; margin-top: 30px; font-size: 1.25em; cursor: pointer; }}
    h2:hover {{ color: {pbi_blue}; }}
    h3 {{ color: {pbi_gray}; }}
    .card {{ background: #fff; border-radius: 8px; padding: 20px; margin: 15px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
    .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; }}
    .stat {{ background: #fff; border-radius: 8px; padding: 16px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); transition: transform 0.15s; }}
    .stat:hover {{ transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,0.15); }}
    .stat .number {{ font-size: 2em; font-weight: bold; color: {pbi_blue}; }}
    .stat .label {{ font-size: 0.85em; color: {pbi_gray}; margin-top: 4px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
    th {{ background: {pbi_blue}; color: #fff; padding: 10px 12px; text-align: left; font-size: 0.85em; position: sticky; top: 0; }}
    td {{ padding: 8px 12px; border-bottom: 1px solid #e1dfdd; font-size: 0.85em; }}
    tr:hover {{ background: #f3f2f1; }}
    .detail-table th {{ background: {pbi_gray}; }}
    .footer {{ text-align: center; color: {pbi_light_gray}; font-size: 0.85em; margin-top: 40px; padding: 20px; }}
    .connector-tag {{ background: #e8f0fe; color: #1a73e8; padding: 2px 6px; border-radius: 3px; font-size: 0.82em; white-space: nowrap; }}
    .warn-tag {{ background: #fff3cd; color: #856404; padding: 2px 6px; border-radius: 3px; font-size: 0.82em; }}
    .section-icon {{ font-size: 1.2em; margin-right: 4px; }}

    /* Charts */
    .chart-row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 15px; margin: 15px 0; }}
    .chart-card {{ background: #fff; border-radius: 8px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
    .chart-card h4 {{ margin: 0 0 12px 0; color: {pbi_dark}; font-size: 0.95em; }}

    /* Donut chart */
    .donut-container {{ display: flex; align-items: center; justify-content: center; gap: 24px; }}
    .donut {{ width: 140px; height: 140px; }}
    .donut-legend {{ font-size: 0.85em; line-height: 1.8; }}
    .legend-dot {{ display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }}

    /* Bar chart */
    .bar-chart {{ display: flex; flex-direction: column; gap: 6px; }}
    .bar-row {{ display: flex; align-items: center; gap: 8px; }}
    .bar-label {{ width: 100px; text-align: right; font-size: 0.82em; color: {pbi_gray}; flex-shrink: 0; }}
    .bar-track {{ flex: 1; height: 22px; background: #e9ecef; border-radius: 4px; position: relative; overflow: hidden; }}
    .bar-fill {{ height: 100%; border-radius: 4px; display: flex; align-items: center; justify-content: flex-end; padding-right: 6px; color: #fff; font-size: 0.75em; font-weight: bold; transition: width 0.4s; }}
    .bar-value {{ font-size: 0.82em; color: {pbi_gray}; width: 30px; text-align: right; }}

    /* Collapsible */
    .collapsible {{ overflow: hidden; transition: max-height 0.3s ease-out; max-height: 2000px; }}
    .collapsed {{ max-height: 0 !important; }}
    .toggle-icon {{ float: right; font-size: 0.8em; color: {pbi_light_gray}; }}

    /* Heatmap table */
    .heatmap td {{ text-align: center; font-weight: bold; }}

    /* Tabs */
    .tab-bar {{ display: flex; gap: 2px; border-bottom: 2px solid #e1dfdd; margin-bottom: 15px; }}
    .tab {{ padding: 8px 16px; cursor: pointer; font-size: 0.9em; border-radius: 4px 4px 0 0; transition: background 0.2s; color: {pbi_gray}; }}
    .tab:hover {{ background: #e8f0fe; }}
    .tab.active {{ background: {pbi_blue}; color: #fff; font-weight: bold; }}
    .tab-content {{ display: none; }}
    .tab-content.active {{ display: block; }}

    @media print {{
        .collapsible {{ max-height: none !important; }}
        h2 {{ cursor: default; }}
        .toggle-icon {{ display: none; }}
    }}
</style>
</head>
<body>
<div class="container">
<h1>&#128202; Tableau &#8594; Power BI — Migration Dashboard</h1>
<p style="color:{pbi_gray};font-size:0.9em">Generated: {now} &nbsp;|&nbsp; Tool: v{tool_version} &nbsp;|&nbsp; Workbooks: {total_workbooks}</p>

<!-- ═══════════════════════════════════════════════════════════════ -->
<!-- EXECUTIVE SUMMARY                                              -->
<!-- ═══════════════════════════════════════════════════════════════ -->
<h2 onclick="toggleSection('exec')"><span class="section-icon">&#128200;</span>Executive Summary <span class="toggle-icon" id="exec-icon">&#9660;</span></h2>
<div id="exec" class="collapsible">
<div class="stats">
    <div class="stat"><div class="number">{total_workbooks}</div><div class="label">Workbooks</div></div>
    <div class="stat"><div class="number" style="color:{success_green}">{avg_fidelity:.1f}%</div><div class="label">Avg. Fidelity</div></div>
    <div class="stat"><div class="number">{total_items}</div><div class="label">Items Converted</div></div>
    <div class="stat"><div class="number" style="color:{success_green}">{total_exact}</div><div class="label">Exact</div></div>
    <div class="stat"><div class="number" style="color:{warn_yellow}">{total_approx}</div><div class="label">Approximate</div></div>
    <div class="stat"><div class="number" style="color:{fail_red}">{total_unsupported}</div><div class="label">Unsupported</div></div>
</div>

<!-- Charts row: Donut + Category Breakdown + Connectors -->
<div class="chart-row">"""

    # ── Donut chart: Conversion Status ─────────────────────────────────
    safe_total = max(total_items, 1)
    exact_pct = total_exact / safe_total * 100
    approx_pct = total_approx / safe_total * 100
    unsup_pct = total_unsupported / safe_total * 100
    # SVG donut
    exact_deg = exact_pct * 3.6
    approx_deg = approx_pct * 3.6
    unsup_deg = unsup_pct * 3.6
    html += f"""
    <div class="chart-card">
        <h4>&#127919; Conversion Status</h4>
        <div class="donut-container">
            <svg class="donut" viewBox="0 0 42 42">
                <circle cx="21" cy="21" r="15.91549431" fill="transparent" stroke="#e9ecef" stroke-width="6"></circle>
                <circle cx="21" cy="21" r="15.91549431" fill="transparent" stroke="{success_green}" stroke-width="6"
                    stroke-dasharray="{exact_pct} {100-exact_pct}" stroke-dashoffset="25"></circle>
                <circle cx="21" cy="21" r="15.91549431" fill="transparent" stroke="{warn_yellow}" stroke-width="6"
                    stroke-dasharray="{approx_pct} {100-approx_pct}" stroke-dashoffset="{25-exact_pct}"></circle>
                <circle cx="21" cy="21" r="15.91549431" fill="transparent" stroke="{fail_red}" stroke-width="6"
                    stroke-dasharray="{unsup_pct} {100-unsup_pct}" stroke-dashoffset="{25-exact_pct-approx_pct}"></circle>
                <text x="21" y="22" text-anchor="middle" font-size="6" font-weight="bold" fill="{pbi_dark}">{avg_fidelity:.0f}%</text>
            </svg>
            <div class="donut-legend">
                <div><span class="legend-dot" style="background:{success_green}"></span>Exact: {total_exact}</div>
                <div><span class="legend-dot" style="background:{warn_yellow}"></span>Approximate: {total_approx}</div>
                <div><span class="legend-dot" style="background:{fail_red}"></span>Unsupported: {total_unsupported}</div>
            </div>
        </div>
    </div>"""

    # ── Bar chart: By Category ─────────────────────────────────────────
    html += """
    <div class="chart-card">
        <h4>&#128202; Items by Category</h4>
        <div class="bar-chart">"""
    max_cat = max((v["total"] for v in cat_totals.values()), default=1)
    cat_colors = {"datasource": "#0078d4", "calculation": "#8764b8", "visual": "#00b294",
                  "parameter": "#ffb900", "filter": "#e74856", "relationship": "#107c10",
                  "set": "#767676", "group": "#ca5010", "hierarchy": "#4f6bed"}
    for cat, vals in sorted(cat_totals.items(), key=lambda x: -x[1]["total"]):
        pct = vals["total"] / max(max_cat, 1) * 100
        color = cat_colors.get(cat, pbi_blue)
        html += f"""
            <div class="bar-row">
                <div class="bar-label">{cat.title()}</div>
                <div class="bar-track"><div class="bar-fill" style="width:{pct}%;background:{color}">{vals['total']}</div></div>
            </div>"""
    html += """
        </div>
    </div>"""

    # ── Connector Distribution ─────────────────────────────────────────
    html += """
    <div class="chart-card">
        <h4>&#128268; Data Connectors</h4>
        <div class="bar-chart">"""
    max_conn = max(connector_counts.values(), default=1)
    conn_colors = {"Excel": "#217346", "SQL Server": "#cc2927", "PostgreSQL": "#336791",
                   "Oracle": "#f80000", "MySQL": "#4479a1", "CSV": "#ff6d00",
                   "Snowflake": "#29b5e8", "BigQuery": "#4285f4", "Tableau Server": "#e97627",
                   "Unknown": "#767676"}
    for conn, count in sorted(connector_counts.items(), key=lambda x: -x[1]):
        pct = count / max(max_conn, 1) * 100
        color = conn_colors.get(conn, pbi_blue)
        html += f"""
            <div class="bar-row">
                <div class="bar-label">{conn}</div>
                <div class="bar-track"><div class="bar-fill" style="width:{pct}%;background:{color}">{count}</div></div>
            </div>"""
    html += """
        </div>
    </div>
</div>
</div>

<!-- ═══════════════════════════════════════════════════════════════ -->
<!-- GENERATED ARTIFACTS                                            -->
<!-- ═══════════════════════════════════════════════════════════════ -->"""

    html += f"""
<h2 onclick="toggleSection('artifacts')"><span class="section-icon">&#128736;</span>Generated Artifacts <span class="toggle-icon" id="artifacts-icon">&#9660;</span></h2>
<div id="artifacts" class="collapsible">
<div class="stats">
    <div class="stat"><div class="number">{total_tables}</div><div class="label">TMDL Tables</div></div>
    <div class="stat"><div class="number">{total_columns}</div><div class="label">Columns</div></div>
    <div class="stat"><div class="number">{total_measures}</div><div class="label">DAX Measures</div></div>
    <div class="stat"><div class="number">{total_relationships}</div><div class="label">Relationships</div></div>
    <div class="stat"><div class="number">{total_pages}</div><div class="label">Report Pages</div></div>
    <div class="stat"><div class="number">{total_visuals}</div><div class="label">Visuals</div></div>
</div>"""

    # ── Workbook Complexity Heatmap ────────────────────────────────────
    if wb_complexity:
        html += """
<div class="card" style="margin-top:15px;overflow-x:auto">
<h4 style="margin:0 0 10px 0">&#127919; Workbook Complexity Heatmap</h4>
<table class="heatmap">
<tr><th>Workbook</th><th>Tables</th><th>Columns</th><th>Measures</th><th>Relationships</th><th>Worksheets</th><th>Dashboards</th><th>Calculations</th><th>Filters</th><th>Pages</th><th>Visuals</th></tr>"""
        # Compute maxima for color scaling
        maxima = {}
        for dim in ("tables", "columns", "measures", "relationships", "worksheets", "dashboards", "calculations", "filters", "pages", "visuals"):
            maxima[dim] = max((v.get(dim, 0) for v in wb_complexity.values()), default=1) or 1

        for wb_name, vals in wb_complexity.items():
            html += f"<tr><td style='text-align:left;font-weight:bold'>{wb_name}</td>"
            for dim in ("tables", "columns", "measures", "relationships", "worksheets", "dashboards", "calculations", "filters", "pages", "visuals"):
                v = vals.get(dim, 0)
                intensity = v / maxima[dim] if maxima[dim] else 0
                bg = f"rgba(0,120,212,{0.1 + intensity * 0.6:.2f})"
                fg = "#fff" if intensity > 0.5 else pbi_dark
                html += f'<td style="background:{bg};color:{fg}">{v}</td>'
            html += "</tr>"
        html += "</table></div>"
    html += "</div>"

    # ── Assessment Results ─────────────────────────────────────────────
    if assessments:
        html += """
<h2 onclick="toggleSection('assess')"><span class="section-icon">&#9989;</span>Assessment Results <span class="toggle-icon" id="assess-icon">&#9660;</span></h2>
<div id="assess" class="collapsible">
<div class="card">
<table>
<tr>
    <th>Workbook</th><th>Readiness</th><th>Checks</th><th>Passed</th><th>Warnings</th><th>Failures</th><th>Complexity</th><th>Connectors</th>
</tr>"""
        for name in all_names:
            a = assessments.get(name, {})
            if not a:
                continue
            score = a.get("overall_score", "N/A")
            totals = a.get("totals", {})
            connectors = []
            complexity = ""
            for cat in a.get("categories", []):
                for check in cat.get("checks", []):
                    if check.get("name", "").startswith("Connector:"):
                        connectors.append(check["name"].replace("Connector: ", ""))
                    if "Complexity score" in check.get("detail", ""):
                        complexity = check["detail"].replace("Complexity score: ", "")
            conn_html = " ".join(f'<span class="connector-tag">{c}</span>' for c in connectors) if connectors else "—"
            html += f"""
<tr>
    <td><strong>{name}</strong></td>
    <td>{badge(score)}</td>
    <td>{totals.get('checks', '—')}</td>
    <td>{totals.get('pass', '—')}</td>
    <td>{'<span class="warn-tag">' + str(totals.get('warn', 0)) + '</span>' if totals.get('warn', 0) > 0 else str(totals.get('warn', '—'))}</td>
    <td>{totals.get('fail', '—')}</td>
    <td>{complexity or '—'}</td>
    <td>{conn_html}</td>
</tr>"""
        html += "</table></div></div>"

    # ── Migration Results Table ────────────────────────────────────────
    html += """
<h2 onclick="toggleSection('migration')"><span class="section-icon">&#128640;</span>Migration Results <span class="toggle-icon" id="migration-icon">&#9660;</span></h2>
<div id="migration" class="collapsible">
<div class="card">
<table>
<tr>
    <th>Workbook</th><th>Fidelity</th><th>Total</th><th>Exact</th><th>Approx.</th><th>Unsupported</th><th>Tables</th><th>Measures</th><th>Pages</th><th>Visuals</th>
</tr>"""

    for name in all_names:
        r = reports.get(name, {})
        m = metadata.get(name, {})
        s = r.get("summary", {})
        fid = s.get("fidelity_score", 0)
        tmdl = m.get("tmdl_stats", {})
        gen = m.get("generated_output", {})

        html += f"""
<tr>
    <td><strong>{name}</strong></td>
    <td>{fidelity_bar(fid)}</td>
    <td>{s.get('total_items', '—')}</td>
    <td style="color:{success_green};font-weight:bold">{s.get('exact', '—')}</td>
    <td>{s.get('approximate', 0) if s.get('approximate', 0) > 0 else '—'}</td>
    <td>{s.get('unsupported', 0) if s.get('unsupported', 0) > 0 else '—'}</td>
    <td>{tmdl.get('tables', '—')}</td>
    <td>{tmdl.get('measures', '—')}</td>
    <td>{gen.get('pages', '—')}</td>
    <td>{gen.get('visuals', '—')}</td>
</tr>"""

    html += """
</table>
</div>
</div>"""

    # ── Per-Workbook Detail Sections ───────────────────────────────────
    html += """
<h2 onclick="toggleSection('details')"><span class="section-icon">&#128221;</span>Per-Workbook Details <span class="toggle-icon" id="details-icon">&#9660;</span></h2>
<div id="details" class="collapsible">"""

    for name in all_names:
        r = reports.get(name, {})
        a = assessments.get(name, {})
        m = metadata.get(name, {})

        items = r.get("items", [])
        if not items and not a:
            continue

        score = a.get("overall_score", "N/A")
        s = r.get("summary", {})
        fid = s.get("fidelity_score", 0)
        by_cat = s.get("by_category", {})

        safe_name = name.replace(" ", "_").replace("'", "")
        html += f"""
<div class="card">
<h3 onclick="toggleSection('wb-{safe_name}')" style="cursor:pointer">
    {name} &nbsp; {badge(score) if score != "N/A" else ""} &nbsp; {fidelity_bar(fid) if fid else ""}
    <span class="toggle-icon" id="wb-{safe_name}-icon">&#9660;</span>
</h3>
<div id="wb-{safe_name}" class="collapsible">"""

        # ── Objects converted summary ──────────────────────────────────
        obj = m.get("objects_converted", {})
        if obj:
            non_zero = {k: v for k, v in obj.items() if v > 0}
            if non_zero:
                tags = " &nbsp;|&nbsp; ".join(f"<strong>{k}</strong>:&nbsp;{v}" for k, v in non_zero.items())
                html += f'<p style="color:{pbi_gray};font-size:0.88em">&#128230; {tags}</p>'

        # ── By-category mini bar chart ─────────────────────────────────
        if by_cat:
            html += '<div style="margin:10px 0">'
            bc_max = max((v.get("total", 0) for v in by_cat.values()), default=1) or 1
            for cat, vals in sorted(by_cat.items(), key=lambda x: -x[1].get("total", 0)):
                total = vals.get("total", 0)
                exact = vals.get("exact", 0)
                pct = total / bc_max * 100
                color = cat_colors.get(cat, pbi_blue)
                html += f"""<div class="bar-row">
                    <div class="bar-label">{cat.title()}</div>
                    <div class="bar-track"><div class="bar-fill" style="width:{pct}%;background:{color}">{exact}/{total}</div></div>
                </div>"""
            html += '</div>'

        # ── Visual type mappings ───────────────────────────────────────
        vtm = m.get("visual_type_mappings", {})
        if vtm:
            html += '<p style="font-size:0.85em;color:{0}"><strong>&#127912; Visual mappings:</strong></p>'.format(pbi_gray)
            html += '<table class="detail-table"><tr><th>Worksheet</th><th>Tableau Mark Type</th></tr>'
            for ws, mark in vtm.items():
                html += f'<tr><td>{ws}</td><td><span class="connector-tag">{mark}</span></td></tr>'
            html += '</table>'

        # ── Table mapping ──────────────────────────────────────────────
        table_mapping = r.get("table_mapping", [])
        if table_mapping:
            html += """<h4 style="margin-top:15px;color:{0}">&#128203; Table Mapping</h4>
<table class="detail-table">
<tr><th>Source Datasource</th><th>Source Table</th><th>Target Table (PBI)</th><th>Connection</th><th>Columns</th></tr>""".format(pbi_dark)
            for tm in table_mapping:
                tgt = tm.get('target_table', '')
                tgt_style = f'color:{fail_red};font-style:italic' if tgt.startswith('(') else ''
                html += f"""<tr>
    <td>{tm.get('source_datasource', '')}</td>
    <td><strong>{tm.get('source_table', '')}</strong></td>
    <td style="{tgt_style}"><strong>{tgt}</strong></td>
    <td><span class="connector-tag">{tm.get('connection_type', '?')}</span></td>
    <td style="text-align:right">{tm.get('columns', 0)}</td>
</tr>"""
            html += "</table>"

        # ── Approximations ─────────────────────────────────────────────
        approx = m.get("approximations", [])
        if approx:
            html += f'<p style="font-size:0.85em;color:#856404"><strong>&#9888; Approximations:</strong></p><ul style="font-size:0.85em;color:#856404">'
            for ap in approx:
                html += f'<li>{ap.get("worksheet","")}: {ap.get("source_type","")} — {ap.get("note","")}</li>'
            html += '</ul>'

        # ── Assessment warnings ────────────────────────────────────────
        warnings = []
        for cat in a.get("categories", []):
            for check in cat.get("checks", []):
                if check.get("severity") in ("warn", "fail"):
                    warnings.append(check)
        if warnings:
            html += f'<p style="font-size:0.85em;color:#856404"><strong>&#9888; Assessment warnings:</strong></p><ul style="font-size:0.85em">'
            for w in warnings:
                sev_color = "#856404" if w["severity"] == "warn" else fail_red
                html += f'<li style="color:{sev_color}">[{w["severity"].upper()}] {w["name"]}: {w["detail"]}'
                if w.get("recommendation"):
                    html += f' &rarr; <em>{w["recommendation"]}</em>'
                html += '</li>'
            html += '</ul>'

        # ── DAX Conversion Details (Tabbed: Calculations / Datasources / Visuals) ──
        if items:
            calc_items = [i for i in items if i.get("category") == "calculation"]
            ds_items = [i for i in items if i.get("category") == "datasource"]
            vis_items = [i for i in items if i.get("category") == "visual"]
            other_items = [i for i in items if i.get("category") not in ("calculation", "datasource", "visual")]

            tab_id = f"tab-{safe_name}"
            html += f"""
<h4 style="margin-top:15px;color:{pbi_dark}">&#128221; Converted Items</h4>
<div class="tab-bar">
    <div class="tab active" onclick="switchTab('{tab_id}', 'all')">All ({len(items)})</div>
    <div class="tab" onclick="switchTab('{tab_id}', 'calc')">Calculations ({len(calc_items)})</div>
    <div class="tab" onclick="switchTab('{tab_id}', 'ds')">Datasources ({len(ds_items)})</div>
    <div class="tab" onclick="switchTab('{tab_id}', 'vis')">Visuals ({len(vis_items)})</div>"""
            if other_items:
                html += f"""
    <div class="tab" onclick="switchTab('{tab_id}', 'other')">Other ({len(other_items)})</div>"""
            html += "</div>"

            def _render_items_table(item_list, tid):
                """Render a table of converted items."""
                out = f'<div class="tab-content{" active" if tid == "all" else ""}" id="{tab_id}-{tid}">'
                if not item_list:
                    out += '<p style="color:#a19f9d;font-style:italic">No items in this category.</p>'
                    out += '</div>'
                    return out
                out += '<table class="detail-table"><tr><th>Category</th><th>Name</th><th>Status</th><th>Source Formula / Note</th><th>DAX / Target</th></tr>'
                for item in item_list:
                    status = item.get("status", "")
                    st_color = success_green if status == "exact" else warn_yellow if status == "approximate" else fail_red
                    src = (item.get("source_formula") or item.get("note") or "").replace("<", "&lt;").replace(">", "&gt;")
                    dax = (item.get("dax") or "").replace("<", "&lt;").replace(">", "&gt;")
                    out += f"""<tr>
    <td><span class="connector-tag">{item.get('category','')}</span></td>
    <td><strong>{item.get('name','')}</strong></td>
    <td style="color:{st_color};font-weight:bold">{status}</td>
    <td style="font-family:'Cascadia Code','Consolas',monospace;font-size:0.8em;max-width:350px;word-break:break-all">{src}</td>
    <td style="font-family:'Cascadia Code','Consolas',monospace;font-size:0.8em;max-width:350px;word-break:break-all">{dax}</td>
</tr>"""
                out += '</table></div>'
                return out

            html += _render_items_table(items, "all")
            html += _render_items_table(calc_items, "calc")
            html += _render_items_table(ds_items, "ds")
            html += _render_items_table(vis_items, "vis")
            if other_items:
                html += _render_items_table(other_items, "other")

        html += "</div></div>"  # close collapse + card

    html += "</div>"  # close details section

    # ── JavaScript ─────────────────────────────────────────────────────
    html += """
<script>
function toggleSection(id) {
    var el = document.getElementById(id);
    var icon = document.getElementById(id + '-icon');
    if (el) {
        el.classList.toggle('collapsed');
        if (icon) icon.innerHTML = el.classList.contains('collapsed') ? '&#9654;' : '&#9660;';
    }
}
function switchTab(groupId, tabName) {
    // Deactivate all tabs and contents in this group
    var bar = document.querySelector('[onclick*=\"' + groupId + '\"]').parentElement;
    bar.querySelectorAll('.tab').forEach(function(t) { t.classList.remove('active'); });
    // Find all tab-contents for this group
    var contents = document.querySelectorAll('[id^=\"' + groupId + '-\"]');
    contents.forEach(function(c) { c.classList.remove('active'); });
    // Activate clicked tab
    bar.querySelectorAll('.tab').forEach(function(t) {
        if (t.textContent.toLowerCase().startsWith(tabName === 'all' ? 'all' : tabName === 'calc' ? 'calc' : tabName === 'ds' ? 'data' : tabName === 'vis' ? 'vis' : 'other')) {
            t.classList.add('active');
        }
    });
    var target = document.getElementById(groupId + '-' + tabName);
    if (target) target.classList.add('active');
}
</script>"""

    html += f"""
<div class="footer">
    <p>Tableau &#8594; Power BI Migration Tool v{tool_version} — Dashboard generated {now}</p>
    <p>Open .pbip files in Power BI Desktop (Developer Mode) to validate</p>
</div>
</div>
</body>
</html>"""

    return html


def generate_dashboard(report_name, output_dir, migration_report_path=None, metadata_path=None):
    """Generate an HTML migration dashboard for a single migration run.

    This is called automatically at the end of each migration.  It reads the
    migration report JSON and metadata JSON from the output directory,
    then produces a self-contained HTML dashboard next to the .pbip project.

    Args:
        report_name: Name of the migrated report.
        output_dir: Directory containing the generated .pbip project.
        migration_report_path: Explicit path to the migration report JSON.
            If None, the latest ``migration_report_*.json`` in *output_dir*
            is used.
        metadata_path: Explicit path to ``migration_metadata.json``.
            If None, it is looked up inside
            ``<output_dir>/<report_name>/migration_metadata.json``.

    Returns:
        str or None: Path to the generated HTML file, or None on failure.
    """
    # ── Locate migration report JSON ──────────────────────────────────
    reports = {}
    if migration_report_path and os.path.isfile(migration_report_path):
        try:
            with open(migration_report_path, encoding="utf-8") as fh:
                data = json.load(fh)
            reports[data.get("report_name", report_name)] = data
        except (json.JSONDecodeError, OSError):
            pass
    else:
        # Auto-discover latest migration report in output_dir
        pattern = os.path.join(output_dir, f"migration_report_{report_name}_*.json")
        candidates = sorted(glob.glob(pattern))
        if candidates:
            try:
                with open(candidates[-1], encoding="utf-8") as fh:
                    data = json.load(fh)
                reports[data.get("report_name", report_name)] = data
            except (json.JSONDecodeError, OSError):
                pass

    # ── Locate metadata JSON ─────────────────────────────────────────
    metadata = {}
    if metadata_path and os.path.isfile(metadata_path):
        try:
            with open(metadata_path, encoding="utf-8") as fh:
                metadata[report_name] = json.load(fh)
        except (json.JSONDecodeError, OSError):
            pass
    else:
        candidate = os.path.join(output_dir, report_name, "migration_metadata.json")
        if os.path.isfile(candidate):
            try:
                with open(candidate, encoding="utf-8") as fh:
                    metadata[report_name] = json.load(fh)
            except (json.JSONDecodeError, OSError):
                pass

    if not reports and not metadata:
        return None

    html = generate_html({}, reports, metadata)

    html_path = os.path.join(output_dir, f"MIGRATION_DASHBOARD_{report_name}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    return html_path


def generate_batch_dashboard(output_dir, workbook_results):
    """Generate a consolidated HTML dashboard for a batch migration.

    Args:
        output_dir: Root output directory.
        workbook_results: dict mapping workbook names to dicts with keys
            ``migration_report_path`` and ``metadata_path`` (both optional).

    Returns:
        str or None: Path to the generated HTML file.
    """
    reports = {}
    metadata = {}

    for name, paths in workbook_results.items():
        rp = paths.get("migration_report_path")
        if rp and os.path.isfile(rp):
            try:
                with open(rp, encoding="utf-8") as fh:
                    reports[name] = json.load(fh)
            except (json.JSONDecodeError, OSError):
                pass
        mp = paths.get("metadata_path")
        if mp and os.path.isfile(mp):
            try:
                with open(mp, encoding="utf-8") as fh:
                    metadata[name] = json.load(fh)
            except (json.JSONDecodeError, OSError):
                pass

    if not reports and not metadata:
        return None

    html = generate_html({}, reports, metadata)

    html_path = os.path.join(output_dir, "MIGRATION_DASHBOARD.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    return html_path


def main():
    assessments = load_assessments()
    reports = load_migration_reports()
    metadata = load_metadata()

    print(f"Loaded: {len(assessments)} assessments, {len(reports)} migration reports, {len(metadata)} metadata files")

    html = generate_html(assessments, reports, metadata)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Report generated: {OUTPUT}")
    print(f"  Size: {len(html):,} bytes")


if __name__ == "__main__":
    main()
