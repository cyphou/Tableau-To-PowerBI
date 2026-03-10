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

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tableau to Power BI — Migration &amp; Assessment Report</title>
<style>
    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; color: #333; }}
    .container {{ max-width: 1200px; margin: 0 auto; }}
    h1 {{ color: #0078d4; border-bottom: 3px solid #0078d4; padding-bottom: 10px; }}
    h2 {{ color: #323130; margin-top: 30px; }}
    h3 {{ color: #605e5c; }}
    .card {{ background: #fff; border-radius: 8px; padding: 20px; margin: 15px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
    .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; }}
    .stat {{ background: #fff; border-radius: 8px; padding: 20px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
    .stat .number {{ font-size: 2.2em; font-weight: bold; color: #0078d4; }}
    .stat .label {{ font-size: 0.9em; color: #605e5c; margin-top: 5px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
    th {{ background: #0078d4; color: #fff; padding: 10px 12px; text-align: left; font-size: 0.9em; }}
    td {{ padding: 8px 12px; border-bottom: 1px solid #e1dfdd; font-size: 0.9em; }}
    tr:hover {{ background: #f3f2f1; }}
    .detail-table th {{ background: #605e5c; }}
    .footer {{ text-align: center; color: #a19f9d; font-size: 0.85em; margin-top: 40px; padding: 20px; }}
    .section-icon {{ font-size: 1.3em; margin-right: 6px; }}
    .connector-tag {{ background: #e8f0fe; color: #1a73e8; padding: 2px 6px; border-radius: 3px; font-size: 0.85em; }}
    .warn-tag {{ background: #fff3cd; color: #856404; padding: 2px 6px; border-radius: 3px; font-size: 0.85em; }}
</style>
</head>
<body>
<div class="container">
<h1>&#128202; Tableau to Power BI — Migration &amp; Assessment Report</h1>
<p style="color:#605e5c">Generated: {now} &nbsp;|&nbsp; Tool version: v5.5.0 &nbsp;|&nbsp; Workbooks processed: {total_workbooks}</p>

<h2><span class="section-icon">&#128200;</span>Executive Summary</h2>
<div class="stats">
    <div class="stat"><div class="number">{total_workbooks}</div><div class="label">Workbooks</div></div>
    <div class="stat"><div class="number" style="color:#28a745">{green}</div><div class="label">GREEN readiness</div></div>
    <div class="stat"><div class="number" style="color:#ffc107">{yellow}</div><div class="label">YELLOW readiness</div></div>
    <div class="stat"><div class="number" style="color:#dc3545">{red}</div><div class="label">RED readiness</div></div>
    <div class="stat"><div class="number">{avg_fidelity:.1f}%</div><div class="label">Avg. fidelity</div></div>
    <div class="stat"><div class="number">{total_items}</div><div class="label">Items converted</div></div>
</div>

<h2><span class="section-icon">&#128736;</span>Generated Artifacts</h2>
<div class="stats">
    <div class="stat"><div class="number">{total_tables}</div><div class="label">TMDL Tables</div></div>
    <div class="stat"><div class="number">{total_columns}</div><div class="label">Columns</div></div>
    <div class="stat"><div class="number">{total_measures}</div><div class="label">DAX Measures</div></div>
    <div class="stat"><div class="number">{total_relationships}</div><div class="label">Relationships</div></div>
    <div class="stat"><div class="number">{total_pages}</div><div class="label">Report Pages</div></div>
    <div class="stat"><div class="number">{total_visuals}</div><div class="label">Visuals</div></div>
</div>

<h2><span class="section-icon">&#9989;</span>Assessment Results</h2>
<div class="card">
<table>
<tr>
    <th>Workbook</th>
    <th>Readiness</th>
    <th>Checks</th>
    <th>Passed</th>
    <th>Warnings</th>
    <th>Failures</th>
    <th>Complexity</th>
    <th>Connectors</th>
</tr>"""

    all_names = sorted(set(list(assessments.keys()) + list(reports.keys())))
    for name in all_names:
        a = assessments.get(name, {})
        score = a.get("overall_score", "N/A")
        summary = a.get("summary", {})
        totals = a.get("totals", {})

        # Extract connector info and complexity from categories
        connectors = []
        complexity = ""
        for cat in a.get("categories", []):
            for check in cat.get("checks", []):
                if check.get("name", "").startswith("Connector:"):
                    conn = check["name"].replace("Connector: ", "")
                    connectors.append(conn)
                if "Complexity score" in check.get("detail", ""):
                    complexity = check["detail"].replace("Complexity score: ", "")

        conn_html = " ".join(f'<span class="connector-tag">{c}</span>' for c in connectors) if connectors else "—"

        html += f"""
<tr>
    <td><strong>{name}</strong></td>
    <td>{badge(score) if score != "N/A" else "—"}</td>
    <td>{totals.get('checks', '—')}</td>
    <td>{totals.get('pass', '—')}</td>
    <td>{'<span class="warn-tag">' + str(totals.get('warn', 0)) + '</span>' if totals.get('warn', 0) > 0 else str(totals.get('warn', '—'))}</td>
    <td>{totals.get('fail', '—')}</td>
    <td>{complexity or '—'}</td>
    <td>{conn_html}</td>
</tr>"""

    html += """
</table>
</div>

<h2><span class="section-icon">&#128640;</span>Migration Results</h2>
<div class="card">
<table>
<tr>
    <th>Workbook</th>
    <th>Fidelity</th>
    <th>Total Items</th>
    <th>Exact</th>
    <th>Approximate</th>
    <th>Unsupported</th>
    <th>Tables</th>
    <th>Measures</th>
    <th>Visuals</th>
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
    <td>{s.get('exact', '—')}</td>
    <td>{s.get('approximate', 0) if s.get('approximate', 0) > 0 else '—'}</td>
    <td>{s.get('unsupported', 0) if s.get('unsupported', 0) > 0 else '—'}</td>
    <td>{tmdl.get('tables', '—')}</td>
    <td>{tmdl.get('measures', '—')}</td>
    <td>{gen.get('visuals', '—')}</td>
</tr>"""

    html += """
</table>
</div>"""

    # --- Per-workbook detail sections ---
    html += """
<h2><span class="section-icon">&#128221;</span>Per-Workbook Details</h2>"""

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

        html += f"""
<div class="card">
<h3>{name} &nbsp; {badge(score) if score != "N/A" else ""} &nbsp; {fidelity_bar(fid) if fid else ""}</h3>"""

        # Objects converted
        obj = m.get("objects_converted", {})
        if obj:
            non_zero = {k: v for k, v in obj.items() if v > 0}
            if non_zero:
                tags = " &nbsp; ".join(f"<strong>{k}</strong>:&nbsp;{v}" for k, v in non_zero.items())
                html += f'<p style="color:#605e5c;font-size:0.9em">{tags}</p>'

        # Visual type mappings
        vtm = m.get("visual_type_mappings", {})
        if vtm:
            vt_tags = " &nbsp; ".join(f'{ws}→<em>{mark}</em>' for ws, mark in vtm.items())
            html += f'<p style="font-size:0.85em;color:#605e5c"><strong>Visual mappings:</strong> {vt_tags}</p>'

        # Approximations
        approx = m.get("approximations", [])
        if approx:
            html += '<p style="font-size:0.85em;color:#856404"><strong>&#9888; Approximations:</strong></p><ul style="font-size:0.85em;color:#856404">'
            for ap in approx:
                html += f'<li>{ap.get("worksheet","")}: {ap.get("source_type","")} — {ap.get("note","")}</li>'
            html += '</ul>'

        # Assessment warnings
        warnings = []
        for cat in a.get("categories", []):
            for check in cat.get("checks", []):
                if check.get("severity") in ("warn", "fail"):
                    warnings.append(check)
        if warnings:
            html += '<p style="font-size:0.85em;color:#856404"><strong>&#9888; Assessment warnings:</strong></p><ul style="font-size:0.85em">'
            for w in warnings:
                sev_color = "#856404" if w["severity"] == "warn" else "#dc3545"
                html += f'<li style="color:{sev_color}">[{w["severity"].upper()}] {w["name"]}: {w["detail"]}'
                if w.get("recommendation"):
                    html += f' → <em>{w["recommendation"]}</em>'
                html += '</li>'
            html += '</ul>'

        # Converted items table
        if items:
            html += """<table class="detail-table">
<tr><th>Category</th><th>Name</th><th>Status</th><th>Source Formula</th><th>DAX</th></tr>"""
            for item in items:
                status = item.get("status", "")
                st_color = "#28a745" if status == "exact" else "#ffc107" if status == "approximate" else "#dc3545"
                src = (item.get("source_formula") or "").replace("<", "&lt;").replace(">", "&gt;")[:80]
                dax = (item.get("dax") or item.get("note") or "").replace("<", "&lt;").replace(">", "&gt;")[:80]
                html += f"""<tr>
    <td>{item.get('category','')}</td>
    <td>{item.get('name','')}</td>
    <td style="color:{st_color};font-weight:bold">{status}</td>
    <td style="font-family:monospace;font-size:0.8em">{src}</td>
    <td style="font-family:monospace;font-size:0.8em">{dax}</td>
</tr>"""
            html += "</table>"

        html += "</div>"

    html += f"""
<div class="footer">
    <p>Tableau to Power BI Migration Tool v5.5.0 — Report generated {now}</p>
    <p>Open .pbip files in Power BI Desktop (Developer Mode) to validate</p>
</div>
</div>
</body>
</html>"""

    return html


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
