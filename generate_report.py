#!/usr/bin/env python3
"""Generate a consolidated Migration & Assessment Report (HTML) from artifacts."""

import json
import os
import glob
import datetime

from powerbi_import.html_template import (
    html_open, html_close, stat_card, stat_grid, section_open, section_close,
    badge, fidelity_bar, donut_chart, bar_chart, data_table, tab_bar,
    tab_content, card, heatmap_table, flow_diagram, esc,
    PBI_BLUE, PBI_DARK, PBI_GRAY, PBI_LIGHT_GRAY, PBI_BG,
    SUCCESS, WARN, FAIL, PURPLE, TEAL, ORANGE,
)

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


def load_lineage(base_dir=None):
    """Load lineage_map.json from each project directory."""
    lineage = {}
    search_dir = base_dir or MIGRATED_DIR
    for d in sorted(glob.glob(os.path.join(search_dir, "*"))):
        if os.path.isdir(d):
            lin_file = os.path.join(d, "lineage_map.json")
            if os.path.isfile(lin_file):
                try:
                    with open(lin_file, encoding="utf-8") as fh:
                        lineage[os.path.basename(d)] = json.load(fh)
                except (json.JSONDecodeError, OSError):
                    pass
    return lineage


def _badge(score):
    """Return colored badge HTML for assessment score (uses shared template)."""
    return badge(score)


def _fidelity_bar(pct):
    """Return a visual progress bar for fidelity percentage (uses shared template)."""
    return fidelity_bar(pct)


def generate_html(assessments, reports, metadata, lineage=None, pbi_validation=None):
    """Generate consolidated HTML report."""
    lineage = lineage or {}
    pbi_validation = pbi_validation or {}
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

    # Category colors
    cat_colors = {"datasource": PBI_BLUE, "calculation": PURPLE, "visual": TEAL,
                  "parameter": "#c19c00", "filter": FAIL, "relationship": SUCCESS,
                  "set": PBI_GRAY, "group": ORANGE, "hierarchy": "#4f6bed"}
    conn_colors = {"Excel": "#217346", "SQL Server": "#cc2927", "PostgreSQL": "#336791",
                   "Oracle": "#f80000", "MySQL": "#4479a1", "CSV": "#ff6d00",
                   "Snowflake": "#29b5e8", "BigQuery": "#4285f4", "Tableau Server": "#e97627",
                   "Unknown": PBI_GRAY}

    # ═══════════════════════════════════════════════════════════════
    #  Build HTML using shared template
    # ═══════════════════════════════════════════════════════════════
    html = html_open(
        title="Tableau \u2192 Power BI \u2014 Migration Dashboard",
        subtitle=f"{total_workbooks} workbook{'s' if total_workbooks != 1 else ''} migrated",
        timestamp=now,
        version=tool_version,
    )

    # ── Executive Summary ───────────────────────────────────────
    html += section_open("exec", "Executive Summary", "&#128200;")
    html += stat_grid([
        stat_card(total_workbooks, "Workbooks", accent="blue"),
        stat_card(f"{avg_fidelity:.1f}%", "Avg. Fidelity", accent="success"),
        stat_card(total_items, "Items Converted"),
        stat_card(total_exact, "Exact", accent="success"),
        stat_card(total_approx, "Approximate", accent="warn"),
        stat_card(total_unsupported, "Unsupported", accent="fail"),
    ])

    # Charts row
    html += '<div class="chart-row">'

    # Donut chart: Conversion Status
    html += '<div class="chart-card"><h4>&#127919; Conversion Status</h4>'
    html += donut_chart([
        ("Exact", total_exact, SUCCESS),
        ("Approximate", total_approx, "#c19c00"),
        ("Unsupported", total_unsupported, FAIL),
    ], center_text=f"{avg_fidelity:.0f}%")
    html += '</div>'

    # Bar chart: By Category
    cat_items = [(cat.title(), vals["total"], cat_colors.get(cat, PBI_BLUE))
                 for cat, vals in sorted(cat_totals.items(), key=lambda x: -x[1]["total"])]
    html += '<div class="chart-card"><h4>&#128202; Items by Category</h4>'
    html += bar_chart(cat_items)
    html += '</div>'

    # Bar chart: Connectors
    conn_items = [(conn, count, conn_colors.get(conn, PBI_BLUE))
                  for conn, count in sorted(connector_counts.items(), key=lambda x: -x[1])]
    html += '<div class="chart-card"><h4>&#128268; Data Connectors</h4>'
    html += bar_chart(conn_items)
    html += '</div>'

    html += '</div>'  # chart-row
    html += section_close()

    # ── Generated Artifacts ─────────────────────────────────────
    html += section_open("artifacts", "Generated Artifacts", "&#128736;")
    html += stat_grid([
        stat_card(total_tables, "TMDL Tables", accent="blue"),
        stat_card(total_columns, "Columns", accent="blue"),
        stat_card(total_measures, "DAX Measures", accent="purple"),
        stat_card(total_relationships, "Relationships", accent="teal"),
        stat_card(total_pages, "Report Pages"),
        stat_card(total_visuals, "Visuals"),
    ])

    # Workbook Complexity Heatmap
    if wb_complexity:
        dims = ("tables", "columns", "measures", "relationships", "worksheets",
                "dashboards", "calculations", "filters", "pages", "visuals")
        maxima = {}
        for dim in dims:
            maxima[dim] = max((v.get(dim, 0) for v in wb_complexity.values()), default=1) or 1

        heat_headers = ["Workbook"] + [d.title() for d in dims]
        heat_rows = []
        for wb_name, vals in wb_complexity.items():
            row = [f'<strong>{esc(wb_name)}</strong>']
            for dim in dims:
                v = vals.get(dim, 0)
                intensity = v / maxima[dim] if maxima[dim] else 0
                bg = f"rgba(0,120,212,{0.08 + intensity * 0.65:.2f})"
                fg = "#fff" if intensity > 0.5 else PBI_DARK
                row.append(f'<span style="display:block;padding:4px;border-radius:3px;background:{bg};color:{fg};text-align:center;font-weight:600">{v}</span>')
            heat_rows.append(row)
        html += '<div class="card"><h4>&#127919; Workbook Complexity Heatmap</h4>'
        html += data_table(heat_headers, heat_rows, "heatmap-tbl", sortable=True)
        html += '</div>'

    html += section_close()

    # ── Assessment Results ─────────────────────────────────────────
    if assessments:
        html += section_open("assess", "Assessment Results", "&#9989;")
        assess_rows = []
        for name in all_names:
            a = assessments.get(name, {})
            if not a:
                continue
            score = a.get("overall_score", "N/A")
            totals = a.get("totals", {})
            connectors = []
            complexity = ""
            for cat_data in a.get("categories", []):
                for check in cat_data.get("checks", []):
                    if check.get("name", "").startswith("Connector:"):
                        connectors.append(check["name"].replace("Connector: ", ""))
                    if "Complexity score" in check.get("detail", ""):
                        complexity = check["detail"].replace("Complexity score: ", "")
            conn_html = " ".join(f'<span class="tag tag-connector">{esc(c)}</span>' for c in connectors) if connectors else "\u2014"
            warn_val = totals.get('warn', 0)
            warn_html = f'<span class="tag tag-warn">{warn_val}</span>' if warn_val > 0 else str(warn_val or '\u2014')
            assess_rows.append([
                f'<strong>{esc(name)}</strong>',
                badge(score),
                str(totals.get('checks', '\u2014')),
                str(totals.get('pass', '\u2014')),
                warn_html,
                str(totals.get('fail', '\u2014')),
                complexity or "\u2014",
                conn_html,
            ])
        html += '<div class="card">'
        html += data_table(
            ["Workbook", "Readiness", "Checks", "Passed", "Warnings", "Failures", "Complexity", "Connectors"],
            assess_rows, "assess-tbl", sortable=True, searchable=True,
        )
        html += '</div>'
        html += section_close()

    # ── Migration Results Table ────────────────────────────────────
    html += section_open("migration", "Migration Results", "&#128640;")
    mig_rows = []
    for name in all_names:
        r = reports.get(name, {})
        m = metadata.get(name, {})
        s = r.get("summary", {})
        fid = s.get("fidelity_score", 0)
        tmdl = m.get("tmdl_stats", {})
        gen = m.get("generated_output", {})

        approx_val = s.get('approximate', 0)
        unsup_val = s.get('unsupported', 0)
        mig_rows.append([
            f'<strong>{esc(name)}</strong>',
            fidelity_bar(fid),
            str(s.get('total_items', '\u2014')),
            f'<span class="text-success fw-bold">{s.get("exact", "\u2014")}</span>',
            str(approx_val) if approx_val > 0 else '\u2014',
            str(unsup_val) if unsup_val > 0 else '\u2014',
            str(tmdl.get('tables', '\u2014')),
            str(tmdl.get('measures', '\u2014')),
            str(gen.get('pages', '\u2014')),
            str(gen.get('visuals', '\u2014')),
        ])
    html += '<div class="card">'
    html += data_table(
        ["Workbook", "Fidelity", "Total", "Exact", "Approx.", "Unsupported",
         "Tables", "Measures", "Pages", "Visuals"],
        mig_rows, "mig-tbl", sortable=True, searchable=True,
    )
    html += '</div>'
    html += section_close()

    # ── Lineage Map ──────────────────────────────────────────────
    # Merge all per-workbook lineage maps into aggregate lists
    all_lin_tables = []
    all_lin_calcs = []
    all_lin_rels = []
    all_lin_ws = []
    for wb_name, lin in lineage.items():
        for t in lin.get('tables', []):
            all_lin_tables.append((wb_name, t))
        for c in lin.get('calculations', []):
            all_lin_calcs.append((wb_name, c))
        for r in lin.get('relationships', []):
            all_lin_rels.append((wb_name, r))
        for w in lin.get('worksheets', []):
            all_lin_ws.append((wb_name, w))

    total_lineage = len(all_lin_tables) + len(all_lin_calcs) + len(all_lin_rels) + len(all_lin_ws)
    if total_lineage > 0:
        html += section_open("lineage", "Lineage Map", "&#128279;")

        # Summary flow diagram
        html += '<div class="card">'
        html += '<h4>&#128260; Migration Flow</h4>'
        html += flow_diagram([
            (f"Tableau Sources ({len(all_lin_tables)} tables)", False),
            (f"Calculations ({len(all_lin_calcs)})", True),
            (f"Power BI Model ({len(all_lin_rels)} relationships)", False),
            (f"Report Pages ({len(all_lin_ws)} pages)", True),
        ])
        html += '</div>'

        # Stat cards
        html += stat_grid([
            stat_card(len(all_lin_tables), "Tables Mapped", accent="blue"),
            stat_card(len(all_lin_calcs), "Calculations Traced", accent="purple"),
            stat_card(len(all_lin_rels), "Relationships", accent="teal"),
            stat_card(len(all_lin_ws), "Worksheets \u2192 Pages"),
        ])

        # Tabbed detail views
        lin_group = "lineage-tabs"
        lin_tabs = [
            ("tables", f"Tables ({len(all_lin_tables)})", True),
            ("calcs", f"Calculations ({len(all_lin_calcs)})", False),
            ("rels", f"Relationships ({len(all_lin_rels)})", False),
            ("ws", f"Worksheets ({len(all_lin_ws)})", False),
        ]
        html += tab_bar(lin_group, lin_tabs)

        # Tables tab
        tbl_rows = []
        for wb, t in all_lin_tables:
            tbl_rows.append([
                f'<strong>{esc(wb)}</strong>',
                esc(t.get('tableau_datasource', '') or '\u2014'),
                esc(t.get('tableau_table', '')),
                '\u27a1',
                f'<span class="tag tag-success">{esc(t.get("pbi_table", ""))}</span>',
            ])
        html += tab_content(lin_group, "tables",
            data_table(["Workbook", "Tableau Datasource", "Tableau Table", "", "PBI Table"],
                       tbl_rows, "lin-tbl", sortable=True, searchable=True),
            active=True)

        # Calculations tab
        calc_rows = []
        for wb, c in all_lin_calcs:
            pbi_type = c.get('pbi_type', '')
            type_cls = "tag-connector" if pbi_type == "measure" else "tag-dim"
            calc_rows.append([
                f'<strong>{esc(wb)}</strong>',
                f'<span class="mono fs-sm" style="max-width:350px;word-break:break-all;display:inline-block">{esc(c.get("tableau_calculation", ""))}</span>',
                '\u27a1',
                f'<strong>{esc(c.get("pbi_object", ""))}</strong>',
                f'<span class="tag {type_cls}">{esc(c.get("pbi_table", ""))}</span>',
                f'<span class="tag tag-success">{esc(pbi_type)}</span>',
            ])
        html += tab_content(lin_group, "calcs",
            data_table(["Workbook", "Tableau Calculation", "", "PBI Object", "PBI Table", "Type"],
                       calc_rows, "lin-calc", sortable=True, searchable=True))

        # Relationships tab
        rel_rows = []
        for wb, r in all_lin_rels:
            rel_rows.append([
                f'<strong>{esc(wb)}</strong>',
                f'<span class="mono">{esc(r.get("from", ""))}</span>',
                '\u27a1',
                f'<span class="mono">{esc(r.get("to", ""))}</span>',
                esc(r.get('cardinality', '')),
            ])
        html += tab_content(lin_group, "rels",
            data_table(["Workbook", "From", "", "To", "Cardinality"],
                       rel_rows, "lin-rel", sortable=True, searchable=True))

        # Worksheets tab
        ws_rows = []
        for wb, w in all_lin_ws:
            ws_rows.append([
                f'<strong>{esc(wb)}</strong>',
                esc(w.get('tableau_worksheet', '')),
                '\u27a1',
                f'<span class="tag tag-success">{esc(w.get("pbi_page", ""))}</span>',
            ])
        html += tab_content(lin_group, "ws",
            data_table(["Workbook", "Tableau Worksheet", "", "PBI Page"],
                       ws_rows, "lin-ws", sortable=True, searchable=True))

        html += section_close()

    # ── Converted Items — Split by Report ──────────────────────────
    all_items_by_report = []
    for name in all_names:
        r = reports.get(name, {})
        for item in r.get("items", []):
            all_items_by_report.append((name, item))

    if all_items_by_report:
        html += section_open("converted", "Converted Items by Report", "&#128221;")

        # Helper to render a table of converted items
        def _conv_rows(item_tuples, show_report=True):
            rows = []
            for rpt_name, item in item_tuples:
                status = item.get("status", "")
                src = esc(item.get("source_formula") or item.get("note") or "")
                dax = esc(item.get("dax") or "")
                # Suppress redundant DAX when identical to source
                # (e.g. string-literal Tableau parameters / KPI metadata)
                if dax and src and dax == src:
                    dax = ""
                short_rpt = rpt_name.split("\\")[-1] if "\\" in rpt_name else rpt_name
                row = []
                if show_report:
                    row.append(f'<strong class="nowrap">{esc(short_rpt)}</strong>')
                row += [
                    f'<span class="tag tag-connector">{esc(item.get("category", ""))}</span>',
                    f'<strong>{esc(item.get("name", ""))}</strong>',
                    badge(status),
                    f'<span class="mono fs-sm" style="max-width:350px;word-break:break-all;display:inline-block">{src}</span>',
                    f'<span class="mono fs-sm" style="max-width:350px;word-break:break-all;display:inline-block">{dax}</span>',
                ]
                rows.append(row)
            return rows

        # Build tabs per report
        report_tabs = {}
        for name in all_names:
            r = reports.get(name, {})
            ritems = r.get("items", [])
            if ritems:
                report_tabs[name] = ritems

        conv_group = "conv-report"
        tabs = [("all", f"All ({len(all_items_by_report)})", True)]
        for rname, ritems in report_tabs.items():
            safe_rname = rname.replace(" ", "_").replace("'", "").replace("\\", "_")
            short = rname.split("\\")[-1] if "\\" in rname else rname
            tabs.append((safe_rname, f"{short} ({len(ritems)})", False))
        html += tab_bar(conv_group, tabs)

        # All tab
        all_headers = ["Report", "Category", "Name", "Status", "Source Formula / Note", "DAX / Target"]
        html += tab_content(conv_group, "all",
            data_table(all_headers, _conv_rows(all_items_by_report, True),
                       f"conv-all-tbl", searchable=True, detail=True),
            active=True)

        # Per-report tabs
        per_headers = ["Category", "Name", "Status", "Source Formula / Note", "DAX / Target"]
        for rname, ritems in report_tabs.items():
            safe_rname = rname.replace(" ", "_").replace("'", "").replace("\\", "_")
            html += tab_content(conv_group, safe_rname,
                data_table(per_headers,
                           _conv_rows([(rname, i) for i in ritems], False),
                           f"conv-{safe_rname}-tbl", searchable=True, detail=True))

        html += section_close()

    # ── Per-Workbook Detail Sections ─────────────────────────────
    html += section_open("details", "Per-Workbook Details", "&#128221;")

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

        # Workbook card with collapsible detail
        badge_html = badge(score) if score != "N/A" else ""
        fid_html = fidelity_bar(fid) if fid else ""
        html += f"""
<div class="card">
<div class="section-header" onclick="toggleSection('wb-{safe_name}')" style="margin-top:0;border-bottom:none">
    <h2 style="font-size:1em">{esc(name)} &nbsp; {badge_html} &nbsp; {fid_html}</h2>
    <span class="toggle-arrow" id="wb-{safe_name}-arrow">&#9660;</span>
</div>
<div class="section-body" id="wb-{safe_name}">"""

        # Objects converted summary
        obj = m.get("objects_converted", {})
        if obj:
            non_zero = {k: v for k, v in obj.items() if v > 0}
            if non_zero:
                tags = " &nbsp;|&nbsp; ".join(f"<strong>{esc(k)}</strong>:&nbsp;{v}" for k, v in non_zero.items())
                html += f'<p class="text-gray fs-sm">&#128230; {tags}</p>'

        # By-category mini bar chart
        if by_cat:
            cat_bar_items = []
            for cat_name, vals in sorted(by_cat.items(), key=lambda x: -x[1].get("total", 0)):
                total = vals.get("total", 0)
                exact_cnt = vals.get("exact", 0)
                color = cat_colors.get(cat_name, PBI_BLUE)
                cat_bar_items.append((cat_name.title(), total, color))
            html += bar_chart(cat_bar_items)

        # Visual type mappings
        visual_details = m.get("visual_details", [])
        vtm = m.get("visual_type_mappings", {})
        if visual_details:
            vis_rows = []
            for vd in visual_details:
                dims = vd.get('dimensions', [])
                meas = vd.get('measures', [])
                dims_html = ', '.join(f'<span class="tag tag-dim">{esc(d)}</span>' for d in dims) if dims else '<span class="text-muted">—</span>'
                meas_html = ', '.join(f'<span class="tag tag-measure">{esc(me)}</span>' for me in meas) if meas else '<span class="text-muted">—</span>'
                vis_rows.append([
                    f'<strong>{esc(vd.get("worksheet", ""))}</strong>',
                    f'<span class="tag tag-connector">{esc(vd.get("tableau_mark", "?"))}</span>',
                    '&#8594;',
                    f'<span class="tag tag-success">{esc(vd.get("pbi_visual", "?"))}</span>',
                    dims_html,
                    meas_html,
                    str(vd.get('field_count', 0)),
                ])
            html += '<h4>&#127912; Tableau Visual &#8594; Power BI Visual</h4>'
            html += data_table(
                ["Worksheet", "Tableau Mark", "", "Power BI Visual", "Dimensions", "Measures", "Fields"],
                vis_rows, detail=True)
        elif vtm:
            _mark_to_pbi = {
                "Automatic": "table", "Bar": "clusteredBarChart",
                "Stacked Bar": "stackedBarChart", "Line": "lineChart",
                "Area": "areaChart", "Pie": "pieChart", "Circle": "scatterChart",
                "Square": "treemap", "Text": "tableEx", "Map": "map",
                "Polygon": "filledMap", "Gantt Bar": "clusteredBarChart",
                "Shape": "scatterChart", "SemiCircle": "donutChart",
                "Histogram": "clusteredColumnChart", "Box Plot": "boxAndWhisker",
                "Waterfall": "waterfallChart", "Funnel": "funnel",
                "Heat Map": "matrix", "Packed Bubble": "scatterChart",
                "Dual Axis": "lineClusteredColumnComboChart",
                "Density": "map", "Treemap": "treemap",
            }
            vtm_rows = []
            for ws, mark in vtm.items():
                pbi_vis = _mark_to_pbi.get(mark, mark.lower().replace(" ", ""))
                vtm_rows.append([
                    esc(ws),
                    f'<span class="tag tag-connector">{esc(mark)}</span>',
                    '&#8594;',
                    f'<span class="tag tag-success">{esc(pbi_vis)}</span>',
                ])
            html += '<h4>&#127912; Visual Mappings</h4>'
            html += data_table(["Worksheet", "Tableau Mark", "", "Power BI Visual"], vtm_rows, detail=True)

        # Table mapping
        table_mapping = r.get("table_mapping", [])
        if table_mapping:
            tm_rows = []
            for tm_item in table_mapping:
                tgt = tm_item.get('target_table', '')
                tgt_cls = ' class="text-fail"' if tgt.startswith('(') else ''
                tm_rows.append([
                    esc(tm_item.get('source_datasource', '')),
                    f'<strong>{esc(tm_item.get("source_table", ""))}</strong>',
                    f'<strong{tgt_cls}>{esc(tgt)}</strong>',
                    f'<span class="tag tag-connector">{esc(tm_item.get("connection_type", "?"))}</span>',
                    str(tm_item.get('columns', 0)),
                ])
            html += '<h4>&#128203; Table Mapping</h4>'
            html += data_table(
                ["Source Datasource", "Source Table", "Target Table (PBI)", "Connection", "Columns"],
                tm_rows, detail=True)

        # Approximations
        approx_list = m.get("approximations", [])
        if approx_list:
            html += '<h4 class="text-warn">&#9888; Approximations</h4><ul class="fs-sm text-warn">'
            for ap in approx_list:
                html += f'<li>{esc(ap.get("worksheet", ""))}: {esc(ap.get("source_type", ""))} — {esc(ap.get("note", ""))}</li>'
            html += '</ul>'

        # Assessment warnings
        warnings = []
        for cat_data in a.get("categories", []):
            for check in cat_data.get("checks", []):
                if check.get("severity") in ("warn", "fail"):
                    warnings.append(check)
        if warnings:
            html += '<h4 class="text-warn">&#9888; Assessment Warnings</h4><ul class="fs-sm">'
            for w in warnings:
                cls = "text-warn" if w["severity"] == "warn" else "text-fail"
                html += f'<li class="{cls}">[{w["severity"].upper()}] {esc(w["name"])}: {esc(w["detail"])}'
                if w.get("recommendation"):
                    html += f' &rarr; <em>{esc(w["recommendation"])}</em>'
                html += '</li>'
            html += '</ul>'

        # DAX Conversion Details (Tabbed)
        if items:
            calc_items = [i for i in items if i.get("category") == "calculation"]
            ds_items = [i for i in items if i.get("category") == "datasource"]
            vis_items = [i for i in items if i.get("category") == "visual"]
            other_items = [i for i in items if i.get("category") not in ("calculation", "datasource", "visual")]

            wb_tab_group = f"wb-tab-{safe_name}"
            wb_tabs = [
                ("all", f"All ({len(items)})", True),
                ("calc", f"Calculations ({len(calc_items)})", False),
                ("ds", f"Datasources ({len(ds_items)})", False),
                ("vis", f"Visuals ({len(vis_items)})", False),
            ]
            if other_items:
                wb_tabs.append(("other", f"Other ({len(other_items)})", False))

            html += '<h4>&#128221; Converted Items</h4>'
            html += tab_bar(wb_tab_group, wb_tabs)

            def _render_wb_items(item_list, tid, active=False):
                if not item_list:
                    return tab_content(wb_tab_group, tid,
                                       '<p class="text-muted" style="font-style:italic">No items in this category.</p>',
                                       active)
                rows = []
                for item in item_list:
                    status = item.get("status", "")
                    src = esc(item.get("source_formula") or item.get("note") or "")
                    dax = esc(item.get("dax") or "")
                    if dax and src and dax == src:
                        dax = ""
                    rows.append([
                        f'<span class="tag tag-connector">{esc(item.get("category", ""))}</span>',
                        f'<strong>{esc(item.get("name", ""))}</strong>',
                        badge(status),
                        f'<span class="mono fs-sm" style="max-width:350px;word-break:break-all;display:inline-block">{src}</span>',
                        f'<span class="mono fs-sm" style="max-width:350px;word-break:break-all;display:inline-block">{dax}</span>',
                    ])
                return tab_content(wb_tab_group, tid,
                    data_table(["Category", "Name", "Status", "Source Formula / Note", "DAX / Target"],
                               rows, detail=True), active)

            html += _render_wb_items(items, "all", active=True)
            html += _render_wb_items(calc_items, "calc")
            html += _render_wb_items(ds_items, "ds")
            html += _render_wb_items(vis_items, "vis")
            if other_items:
                html += _render_wb_items(other_items, "other")

        html += "</div></div>"  # close section-body + card

    html += section_close()

    # ── PBI Desktop Validation ─────────────────────────────────────
    if pbi_validation:
        total_errors = sum(len(v.get('errors', [])) for v in pbi_validation.values())
        total_warnings = sum(len(v.get('warnings', [])) for v in pbi_validation.values())
        all_passed = all(v.get('passed', True) for v in pbi_validation.values())

        if total_errors > 0 or total_warnings > 0:
            html += section_open('pbi-validation', 'PBI Desktop Validation', '&#128270;')

            status_accent = 'fail' if total_errors > 0 else ('warn' if total_warnings > 0 else 'success')
            status_label = 'Failed' if total_errors > 0 else ('Warnings' if total_warnings > 0 else 'Passed')
            html += stat_grid([
                stat_card(status_label, 'Status', accent=status_accent),
                stat_card(total_errors, 'Errors', accent='fail' if total_errors > 0 else 'success'),
                stat_card(total_warnings, 'Warnings', accent='warn' if total_warnings > 0 else 'success'),
            ])

            for wb_name, result in pbi_validation.items():
                wb_errors = result.get('errors', [])
                wb_warnings = result.get('warnings', [])
                if not wb_errors and not wb_warnings:
                    continue

                wb_passed = result.get('passed', True)
                wb_badge = badge('GREEN') if wb_passed and not wb_warnings else (badge('RED') if not wb_passed else badge('YELLOW'))
                html += f'<div class="card"><h4>{esc(wb_name)} &nbsp; {wb_badge}</h4>'

                if wb_errors:
                    html += '<h5 class="text-fail">&#10060; Errors &mdash; will cause failures in PBI Desktop</h5>'
                    html += '<ul class="fs-sm">'
                    for e in wb_errors:
                        html += f'<li class="text-fail">{esc(e)}</li>'
                    html += '</ul>'

                if wb_warnings:
                    html += '<h5 class="text-warn">&#9888; Warnings &mdash; may cause issues at runtime</h5>'
                    html += '<ul class="fs-sm">'
                    for w in wb_warnings:
                        html += f'<li class="text-warn">{esc(w)}</li>'
                    html += '</ul>'

                html += '</div>'

            html += section_close()

    # ── Close HTML ─────────────────────────────────────────────────
    html += html_close(version=tool_version, timestamp=now)

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

    # ── Locate lineage map JSON ────────────────────────────────────
    lineage = {}
    lin_candidate = os.path.join(output_dir, report_name, "lineage_map.json")
    if os.path.isfile(lin_candidate):
        try:
            with open(lin_candidate, encoding="utf-8") as fh:
                lineage[report_name] = json.load(fh)
        except (json.JSONDecodeError, OSError):
            pass

    if not reports and not metadata:
        return None

    # ── Run PBI Desktop validation ────────────────────────────────
    pbi_validation = {}
    pbip_dir = os.path.join(output_dir, report_name)
    if os.path.isdir(pbip_dir):
        try:
            from powerbi_import.validator import ArtifactValidator
            pbi_validation[report_name] = ArtifactValidator.run_pbi_validation(pbip_dir)
        except Exception:
            pass

    html = generate_html({}, reports, metadata, lineage, pbi_validation=pbi_validation)

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

    # Load lineage maps from output directories
    lineage = {}
    for name, paths in workbook_results.items():
        lp = paths.get("lineage_path")
        if not lp:
            lp = os.path.join(output_dir, name, "lineage_map.json")
        if os.path.isfile(lp):
            try:
                with open(lp, encoding="utf-8") as fh:
                    lineage[name] = json.load(fh)
            except (json.JSONDecodeError, OSError):
                pass

    if not reports and not metadata:
        return None

    # ── Run PBI Desktop validation per workbook ───────────────────
    pbi_validation = {}
    for name in workbook_results:
        pbip_dir = os.path.join(output_dir, name)
        if os.path.isdir(pbip_dir):
            try:
                from powerbi_import.validator import ArtifactValidator
                pbi_validation[name] = ArtifactValidator.run_pbi_validation(pbip_dir)
            except Exception:
                pass

    html = generate_html({}, reports, metadata, lineage, pbi_validation=pbi_validation)

    html_path = os.path.join(output_dir, "MIGRATION_DASHBOARD.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    return html_path


def main():
    assessments = load_assessments()
    reports = load_migration_reports()
    metadata = load_metadata()
    lineage = load_lineage()

    print(f"Loaded: {len(assessments)} assessments, {len(reports)} migration reports, {len(metadata)} metadata files, {len(lineage)} lineage maps")

    html = generate_html(assessments, reports, metadata, lineage)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Report generated: {OUTPUT}")
    print(f"  Size: {len(html):,} bytes")


if __name__ == "__main__":
    main()
