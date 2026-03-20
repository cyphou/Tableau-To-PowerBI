"""Side-by-side comparison report — Tableau vs. Power BI.

Generates an HTML report that shows each Tableau worksheet alongside
the corresponding Power BI visual definition, highlighting:

* Visual type mapping
* DAX formula conversions
* Filter mapping
* Data model differences (columns, measures, relationships)

Usage::

    python -m powerbi_import.comparison_report \\
        tableau_export/ artifacts/powerbi_projects/MyProject/ \\
        --output comparison.html
"""

import json
import os
import html as html_mod
import argparse
import glob


# ────────────────────────────────────────────────────────
# CSS Theme
# ────────────────────────────────────────────────────────

_CSS = """
* { box-sizing: border-box; }
body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
       margin: 0; padding: 0; background: #f0f2f5; color: #333; }
header { background: linear-gradient(135deg, #1a237e 0%, #283593 100%);
         color: #fff; padding: 1.5rem 2rem; }
header h1 { margin: 0; font-size: 1.5rem; }
header p { margin: 0.3rem 0 0; opacity: 0.85; font-size: 0.9rem; }
.container { max-width: 1400px; margin: 1rem auto; padding: 0 1rem; }
.summary { display: flex; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
.card { background: #fff; border-radius: 8px; padding: 1rem 1.5rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.12); flex: 1; min-width: 200px; }
.card h3 { margin-top: 0; font-size: 0.85rem; color: #666; text-transform: uppercase; }
.card .val { font-size: 2rem; font-weight: 700; }
.comparison { background: #fff; border-radius: 8px; margin-bottom: 1rem;
              box-shadow: 0 1px 3px rgba(0,0,0,0.12); overflow: hidden; }
.comparison .row-header { background: #e8eaf6; padding: 0.75rem 1rem;
                          font-weight: 600; display: flex; justify-content: space-between; }
.comparison .row-header .badge { background: #4caf50; color: #fff; padding: 2px 8px;
                                  border-radius: 4px; font-size: 0.75rem; }
.comparison .row-header .badge.warn { background: #ff9800; }
.comparison .row-header .badge.fail { background: #f44336; }
.cols { display: grid; grid-template-columns: 1fr 1fr; }
.col { padding: 1rem; border-top: 1px solid #e0e0e0; }
.col:first-child { border-right: 1px solid #e0e0e0; }
.col h4 { margin: 0 0 0.5rem; color: #1a237e; font-size: 0.8rem; text-transform: uppercase; }
pre { background: #f5f5f5; padding: 0.5rem; border-radius: 4px; overflow-x: auto;
      font-size: 0.82rem; margin: 0.3rem 0; white-space: pre-wrap; }
.label { font-weight: 600; color: #555; font-size: 0.8rem; }
table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
th, td { border: 1px solid #e0e0e0; padding: 4px 8px; text-align: left; }
th { background: #fafafa; }
.pass { color: #4caf50; } .warn { color: #ff9800; } .fail { color: #f44336; }
"""


# ────────────────────────────────────────────────────────
# Data loaders
# ────────────────────────────────────────────────────────

def _load_json(path):
    """Load a JSON file, returning empty dict/list on failure."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _load_extracted(extract_dir):
    """Load all 16 extracted JSON files from the extraction directory."""
    data = {}
    names = [
        'worksheets', 'dashboards', 'datasources', 'calculations',
        'parameters', 'filters', 'stories', 'actions', 'sets', 'groups',
        'bins', 'hierarchies', 'sort_orders', 'aliases', 'custom_sql',
        'user_filters',
    ]
    for name in names:
        path = os.path.join(extract_dir, f'{name}.json')
        data[name] = _load_json(path)
    return data


def _load_pbip(pbip_dir):
    """Load Power BI project artifacts from a .pbip directory."""
    result = {'pages': [], 'model': {}, 'report': {}}
    # Find report.json
    for root, dirs, files in os.walk(pbip_dir):
        for f in files:
            full = os.path.join(root, f)
            if f == 'report.json':
                result['report'] = _load_json(full)
            elif f.endswith('.json') and 'page' in root.lower():
                result['pages'].append({'path': full, 'data': _load_json(full)})
            elif f.endswith('.json') and 'visual' in f.lower():
                result.setdefault('visuals', []).append(
                    {'path': full, 'data': _load_json(full)}
                )
    # Load migration report if present
    reports = glob.glob(os.path.join(pbip_dir, '..', 'migration_report_*.json'))
    if not reports:
        # Check new layout: reports/ sibling directory of migrated/
        reports = glob.glob(os.path.join(pbip_dir, '..', '..', 'reports', 'migration_report_*.json'))
    if reports:
        result['migration_report'] = _load_json(sorted(reports)[-1])
    return result


# ────────────────────────────────────────────────────────
# Comparison logic
# ────────────────────────────────────────────────────────

def _compare_worksheets(extracted, pbip_data):
    """Compare Tableau worksheets to PBI pages/visuals."""
    comparisons = []
    worksheets = extracted.get('worksheets', [])
    if isinstance(worksheets, dict):
        worksheets = worksheets.get('worksheets', [])

    pbi_pages = pbip_data.get('pages', [])
    pbi_visuals = pbip_data.get('visuals', [])

    for ws in worksheets:
        name = ws.get('name', 'Unknown')
        tab_type = ws.get('mark_type', ws.get('mark_encoding', {}).get('type', 'auto'))
        tab_fields = ws.get('fields', [])
        tab_filters = ws.get('filters', [])

        # Try to find matching PBI visual
        pbi_match = None
        for v in (pbi_visuals or []):
            vdata = v.get('data', {})
            title = vdata.get('title', {}).get('text', '')
            if title and (name.lower() in title.lower() or title.lower() in name.lower()):
                pbi_match = vdata
                break

        comparisons.append({
            'name': name,
            'tableau': {
                'mark_type': tab_type,
                'field_count': len(tab_fields),
                'fields': tab_fields[:10],
                'filter_count': len(tab_filters),
            },
            'powerbi': {
                'visual_type': pbi_match.get('visualType', 'N/A') if pbi_match else 'N/A',
                'matched': pbi_match is not None,
            },
            'status': 'pass' if pbi_match else 'warn',
        })
    return comparisons


def _compare_calculations(extracted, pbip_data):
    """Compare Tableau calculations to PBI DAX measures/columns."""
    calcs = extracted.get('calculations', [])
    if isinstance(calcs, dict):
        calcs = calcs.get('calculations', [])

    results = []
    for calc in calcs[:50]:  # Limit for report size
        name = calc.get('name', calc.get('caption', ''))
        formula = calc.get('formula', '')
        role = calc.get('role', '')
        results.append({
            'name': name,
            'tableau_formula': formula,
            'role': role,
        })
    return results


def _compare_field_bindings(extracted, pbip_dir):
    """Compare Tableau worksheet field bindings against PBI visual fields.

    Returns a list of per-worksheet results with match status and field details.
    """
    worksheets = extracted.get('worksheets', [])
    if isinstance(worksheets, dict):
        worksheets = worksheets.get('worksheets', [])

    # ── Load PBI visuals from disk ──
    pbi_visuals = []
    vis_pattern = os.path.join(pbip_dir, '**', 'visual.json')
    for filepath in sorted(glob.glob(vis_pattern, recursive=True)):
        data = _load_json(filepath)
        vis = data.get('visual', {})
        vtype = vis.get('visualType', 'unknown')
        # Extract title
        title = ''
        for t_item in vis.get('visualContainerObjects', vis.get('vcObjects', {})).get('title', []):
            txt = t_item.get('properties', {}).get('text', {})
            if isinstance(txt, dict):
                val = txt.get('expr', {}).get('Literal', {}).get('Value', '')
                title = val.strip("'").strip('"')
        # Extract fields from queryState
        qs = vis.get('query', {}).get('queryState', {})
        fields = []
        for role, role_data in qs.items():
            for proj in role_data.get('projections', []):
                fi = proj.get('field', {})
                agg_node = fi.get('Aggregation', {})
                if agg_node:
                    prop = agg_node.get('Expression', {}).get('Column', {}).get('Property', '')
                else:
                    prop = fi.get('Column', {}).get('Property', '')
                if prop:
                    fields.append(prop)
        pbi_visuals.append({
            'type': vtype,
            'title': title,
            'fields': fields,
            'is_empty': len(fields) == 0,
        })

    # ── Generated fields to ignore ──
    _GENERATED = {'Latitude (generated)', 'Longitude (generated)',
                  'Number of Records', 'Multiple Values'}

    results = []
    used_indices = set()

    for ws in worksheets:
        ws_name = ws.get('name', '')
        ws_raw_fields = ws.get('fields', [])
        ws_field_names = set()
        for f in ws_raw_fields:
            name = f.get('name', '') if isinstance(f, dict) else str(f)
            if name and name not in _GENERATED:
                ws_field_names.add(name)
        ws_is_empty = len(ws_field_names) == 0

        # Match by best field overlap (Jaccard)
        best_idx, best_score = None, -1
        for i, v in enumerate(pbi_visuals):
            if i in used_indices:
                continue
            pbi_set = set(v['fields'])
            overlap = len(ws_field_names & pbi_set)
            union = len(ws_field_names | pbi_set)
            score = overlap / union if union else (1.0 if ws_is_empty and v['is_empty'] else 0)
            if score > best_score:
                best_score = score
                best_idx = i

        pbi = pbi_visuals[best_idx] if best_idx is not None else None
        if pbi:
            used_indices.add(best_idx)

        pbi_field_names = set(pbi['fields']) if pbi else set()
        matched = ws_field_names & pbi_field_names
        missing = ws_field_names - pbi_field_names
        extra = pbi_field_names - ws_field_names

        if ws_is_empty:
            status = 'EMPTY'
        elif not pbi:
            status = 'NO_VISUAL'
        elif missing and not extra:
            status = 'MISSING'
        elif missing and extra:
            status = 'PARTIAL'
        elif extra and not missing:
            status = 'EXTRA'
        else:
            status = 'OK'

        results.append({
            'worksheet': ws_name,
            'visual_type': pbi['type'] if pbi else None,
            'status': status,
            'matched': sorted(matched),
            'missing': sorted(missing),
            'extra': sorted(extra),
            'tab_count': len(ws_field_names),
            'pbi_count': len(pbi_field_names),
        })

    return results


def _compare_datasources(extracted):
    """Summarize datasource comparison."""
    ds = extracted.get('datasources', [])
    if isinstance(ds, dict):
        ds = ds.get('datasources', [])
    summary = []
    for d in ds:
        name = d.get('name', d.get('caption', ''))
        conn = d.get('connection', {})
        tables = d.get('tables', [])
        summary.append({
            'name': name,
            'type': conn.get('class', conn.get('type', 'unknown')),
            'table_count': len(tables),
            'column_count': sum(len(t.get('columns', [])) for t in tables),
        })
    return summary


# ────────────────────────────────────────────────────────
# HTML generation
# ────────────────────────────────────────────────────────

def _esc(text):
    """HTML-escape text."""
    return html_mod.escape(str(text)) if text else ''


def generate_comparison_report(extract_dir, pbip_dir, output_path=None):
    """Generate an HTML comparison report.

    Args:
        extract_dir: Path to the tableau_export/ directory with JSON files.
        pbip_dir: Path to the generated .pbip project directory.
        output_path: Output HTML file path (default: comparison_report.html
                     in the pbip directory's parent).

    Returns:
        str: Path to the generated HTML file.
    """
    extracted = _load_extracted(extract_dir)
    pbip_data = _load_pbip(pbip_dir)

    ws_compare = _compare_worksheets(extracted, pbip_data)
    calc_compare = _compare_calculations(extracted, pbip_data)
    ds_compare = _compare_datasources(extracted)
    field_compare = _compare_field_bindings(extracted, pbip_dir)
    migration_report = pbip_data.get('migration_report', {})

    # Counts
    ws_total = len(ws_compare)
    ws_matched = sum(1 for w in ws_compare if w['status'] == 'pass')
    calc_total = len(calc_compare)
    ds_total = len(ds_compare)
    field_ok = sum(1 for f in field_compare if f['status'] in ('OK', 'EMPTY', 'EXTRA'))
    field_issues = len(field_compare) - field_ok

    if output_path is None:
        output_path = os.path.join(os.path.dirname(pbip_dir), 'comparison_report.html')

    parts = [f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Migration Comparison Report</title>
<style>{_CSS}</style>
</head>
<body>
<header>
<h1>Tableau → Power BI — Side-by-Side Comparison</h1>
<p>Extract: {_esc(extract_dir)} | Project: {_esc(pbip_dir)}</p>
</header>
<div class="container">
"""]

    # Summary cards
    fidelity = migration_report.get('overall_fidelity', 'N/A')
    field_cls = 'pass' if field_issues == 0 else 'warn'
    parts.append(f"""
<div class="summary">
  <div class="card"><h3>Worksheets</h3><div class="val">{ws_total}</div></div>
  <div class="card"><h3>Matched Visuals</h3><div class="val">{ws_matched}/{ws_total}</div></div>
  <div class="card"><h3>Field Bindings</h3><div class="val {field_cls}">{field_ok}/{len(field_compare)}</div></div>
  <div class="card"><h3>Calculations</h3><div class="val">{calc_total}</div></div>
  <div class="card"><h3>Datasources</h3><div class="val">{ds_total}</div></div>
  <div class="card"><h3>Fidelity</h3><div class="val">{_esc(str(fidelity))}</div></div>
</div>
""")

    # ── Worksheet comparison ──
    parts.append('<h2>Worksheet → Visual Mapping</h2>')
    for ws in ws_compare:
        badge_cls = ws['status']
        badge_txt = 'Matched' if badge_cls == 'pass' else 'Unmatched'
        parts.append(f"""
<div class="comparison">
  <div class="row-header">
    <span>{_esc(ws['name'])}</span>
    <span class="badge {badge_cls}">{badge_txt}</span>
  </div>
  <div class="cols">
    <div class="col">
      <h4>Tableau</h4>
      <p><span class="label">Mark type:</span> {_esc(ws['tableau']['mark_type'])}</p>
      <p><span class="label">Fields:</span> {ws['tableau']['field_count']}</p>
      <p><span class="label">Filters:</span> {ws['tableau']['filter_count']}</p>
    </div>
    <div class="col">
      <h4>Power BI</h4>
      <p><span class="label">Visual type:</span> {_esc(ws['powerbi']['visual_type'])}</p>
    </div>
  </div>
</div>""")

    # ── Field Binding Verification ──
    if field_compare:
        parts.append('<h2>Field Binding Verification</h2>')
        parts.append('<table><tr>'
                     '<th>Worksheet</th><th>Visual Type</th><th>Status</th>'
                     '<th>Tableau</th><th>PBI</th><th>Matched</th>'
                     '<th>Missing in PBI</th><th>Extra in PBI</th></tr>')
        _STATUS_BADGE = {
            'OK': ('pass', 'OK'), 'EMPTY': ('', 'Empty'),
            'EXTRA': ('pass', 'Extra'), 'MISSING': ('fail', 'Missing'),
            'PARTIAL': ('warn', 'Partial'), 'NO_VISUAL': ('fail', 'No Visual'),
        }
        for fc in field_compare:
            cls, label = _STATUS_BADGE.get(fc['status'], ('', fc['status']))
            missing_str = ', '.join(fc['missing']) if fc['missing'] else '—'
            extra_str = ', '.join(fc['extra']) if fc['extra'] else '—'
            parts.append(
                f"<tr><td>{_esc(fc['worksheet'])}</td>"
                f"<td>{_esc(fc['visual_type'] or 'N/A')}</td>"
                f"<td class=\"{cls}\">{_esc(label)}</td>"
                f"<td>{fc['tab_count']}</td><td>{fc['pbi_count']}</td>"
                f"<td>{len(fc['matched'])}</td>"
                f"<td>{_esc(missing_str)}</td>"
                f"<td>{_esc(extra_str)}</td></tr>"
            )
        parts.append('</table>')

    # ── Calculation comparison ──
    if calc_compare:
        parts.append('<h2>Calculation Conversions</h2>')
        parts.append('<table><tr><th>Name</th><th>Tableau Formula</th><th>Role</th></tr>')
        for c in calc_compare:
            parts.append(
                f"<tr><td>{_esc(c['name'])}</td>"
                f"<td><pre>{_esc(c['tableau_formula'])}</pre></td>"
                f"<td>{_esc(c['role'])}</td></tr>"
            )
        parts.append('</table>')

    # ── Datasource comparison ──
    if ds_compare:
        parts.append('<h2>Datasource Summary</h2>')
        parts.append('<table><tr><th>Name</th><th>Type</th><th>Tables</th><th>Columns</th></tr>')
        for d in ds_compare:
            parts.append(
                f"<tr><td>{_esc(d['name'])}</td><td>{_esc(d['type'])}</td>"
                f"<td>{d['table_count']}</td><td>{d['column_count']}</td></tr>"
            )
        parts.append('</table>')

    # ── Migration report items ──
    items = migration_report.get('items', [])
    if items:
        parts.append('<h2>Migration Item Status</h2>')
        parts.append('<table><tr><th>Item</th><th>Type</th><th>Status</th><th>Notes</th></tr>')
        for item in items[:100]:
            status = item.get('status', '')
            cls = 'pass' if status in ('migrated', 'converted') else 'warn' if status == 'partial' else 'fail'
            parts.append(
                f"<tr><td>{_esc(item.get('name', ''))}</td>"
                f"<td>{_esc(item.get('type', ''))}</td>"
                f"<td class=\"{cls}\">{_esc(status)}</td>"
                f"<td>{_esc(item.get('notes', ''))}</td></tr>"
            )
        parts.append('</table>')

    parts.append('</div></body></html>')

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(parts))
    print(f"  ✓ Comparison report: {output_path}")
    return output_path


# ────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Generate a side-by-side Tableau vs Power BI comparison report'
    )
    parser.add_argument('extract_dir', help='Path to tableau_export/ directory')
    parser.add_argument('pbip_dir', help='Path to generated .pbip project directory')
    parser.add_argument(
        '--output', '-o', default=None,
        help='Output HTML file path (default: comparison_report.html in pbip parent)'
    )
    args = parser.parse_args()
    generate_comparison_report(args.extract_dir, args.pbip_dir, args.output)


if __name__ == '__main__':
    main()
