"""Telemetry dashboard — generates an HTML summary of migration runs.

Reads migration report JSON files and JSONL telemetry logs from the
artifacts directory and builds a single-page interactive dashboard with
charts, tables, and drill-down capabilities summarizing migration history,
fidelity trends, portfolio progress, and bottleneck analysis.

Usage::

    python -m powerbi_import.telemetry_dashboard [artifacts_dir] [-o dashboard.html]
"""

import json
import os
import glob
import logging
import argparse
import html as html_mod
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    from powerbi_import.html_template import get_report_css, get_report_js
except ImportError:
    from html_template import get_report_css, get_report_js

# Default JSONL telemetry log location (same as telemetry.py)
_DEFAULT_TELEMETRY_LOG = os.path.join(
    os.path.expanduser('~'), '.ttpbi_telemetry.json'
)


_CSS_EXTRA = """
/* telemetry-dashboard extras */
.progress-track { background: #e0e0e0; border-radius: 10px; height: 20px;
                  overflow: hidden; margin: 4px 0; }
.progress-fill { height: 100%; border-radius: 10px; transition: width 0.3s; }
.chart-bar { height: 24px; background: var(--pbi-blue); border-radius: 3px;
             display: inline-block; min-width: 2px; }
.collapsible { cursor: pointer; user-select: none; }
.collapsible::before { content: '\\25B6 '; font-size: 0.7rem; }
.collapsible.open::before { content: '\\25BC '; }
.detail-panel { display: none; padding: 0.5rem 1rem; background: var(--pbi-bg);
                border-radius: 4px; margin-bottom: 1rem; }
.detail-panel.open { display: block; }
.toolbar { display: flex; gap: 0.75rem; margin-bottom: 1rem; flex-wrap: wrap;
           align-items: center; }
.toolbar input, .toolbar select { padding: 6px 10px; border: 1px solid #ccc;
    border-radius: 4px; font-size: 0.85rem; }
.toolbar input[type=text] { width: 240px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 1rem; margin-bottom: 1.5rem; }
.card h3 { margin-top: 0; font-size: 0.8rem; color: #888; text-transform: uppercase; }
.card .val { font-size: 2rem; font-weight: 700; }
.card .sub { font-size: 0.85rem; color: #666; }
.pass { color: var(--success); font-weight: 600; }
.warn { color: #ca5010; font-weight: 600; }
.fail { color: var(--fail); font-weight: 600; }
"""


_JS_EXTRA = """
function filterByDate(inputId, tableId) {
  var val = document.getElementById(inputId).value;
  if (!val) { filterTable('search-runs', tableId); return; }
  var rows = document.getElementById(tableId).querySelectorAll('tbody tr');
  rows.forEach(function(row) {
    var ts = row.cells[3] ? row.cells[3].textContent : '';
    row.style.display = ts.indexOf(val) > -1 ? '' : 'none';
  });
}
function toggleDetail(id) {
  var el = document.getElementById(id);
  el.classList.toggle('open');
  var btn = el.previousElementSibling;
  if (btn) btn.classList.toggle('open');
}
"""


def _load_reports(artifacts_dir):
    """Load all migration report JSONs from the artifacts directory."""
    pattern = os.path.join(artifacts_dir, '**', 'migration_report_*.json')
    files = sorted(glob.glob(pattern, recursive=True))
    reports = []
    for f in files:
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            data['_file'] = f
            reports.append(data)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Skipping unreadable migration report %s: %s", f, exc)
    return reports


def _load_telemetry_events(log_path=None):
    """Load JSONL telemetry log entries."""
    path = log_path or _DEFAULT_TELEMETRY_LOG
    entries = []
    if not os.path.exists(path):
        return entries
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except OSError as exc:
        logger.warning("Could not read telemetry log %s: %s", path, exc)
    return entries


def _esc(text):
    return html_mod.escape(str(text)) if text else ''


def _analyze_bottlenecks(reports, telemetry_entries):
    """Identify migration bottlenecks from telemetry events and reports.

    Returns:
        list[dict]: Bottleneck items sorted by impact.
    """
    bottlenecks = {}

    # From reports: items with partial/skipped/failed status
    for r in reports:
        for item in r.get('items', []):
            notes = item.get('notes', '')
            status = item.get('status', 'unknown')
            if status in ('partial', 'skipped', 'failed'):
                kind = item.get('type', item.get('kind', 'unknown'))
                key = f'{kind}:{status}'
                if key not in bottlenecks:
                    bottlenecks[key] = {
                        'category': kind,
                        'status': status,
                        'count': 0,
                        'sample_notes': [],
                    }
                bottlenecks[key]['count'] += 1
                if notes and len(bottlenecks[key]['sample_notes']) < 3:
                    bottlenecks[key]['sample_notes'].append(notes[:100])

    # From telemetry: error events
    for entry in telemetry_entries:
        for err in entry.get('errors', []):
            cat = err.get('category', 'unknown')
            key = f'error:{cat}'
            if key not in bottlenecks:
                bottlenecks[key] = {
                    'category': cat,
                    'status': 'error',
                    'count': 0,
                    'sample_notes': [],
                }
            bottlenecks[key]['count'] += 1
            msg = err.get('message', '')
            if msg and len(bottlenecks[key]['sample_notes']) < 3:
                bottlenecks[key]['sample_notes'].append(msg[:100])

    return sorted(bottlenecks.values(), key=lambda b: -b['count'])


def _compute_portfolio_progress(reports):
    """Compute portfolio progress from migration reports.

    Returns:
        dict: {total, completed, partial, pending, pct_complete}.
    """
    total = len(reports)
    completed = 0
    partial = 0
    for r in reports:
        fid = r.get('fidelity_score', r.get('overall_fidelity', 0))
        try:
            fid = float(fid)
        except (TypeError, ValueError):
            fid = 0
        if fid >= 80:
            completed += 1
        elif fid > 0:
            partial += 1
    pending = total - completed - partial
    pct = round(completed / total * 100, 1) if total else 0
    return {
        'total': total,
        'completed': completed,
        'partial': partial,
        'pending': pending,
        'pct_complete': pct,
    }


def generate_dashboard(artifacts_dir, output_path=None, telemetry_log=None):
    """Generate an interactive HTML telemetry dashboard.

    Args:
        artifacts_dir: Path to the artifacts directory.
        output_path: Output file (default: artifacts/telemetry_dashboard.html).
        telemetry_log: Path to JSONL telemetry log (default: ~/.ttpbi_telemetry.json).

    Returns:
        str: Path to the generated HTML file.
    """
    reports = _load_reports(artifacts_dir)
    telemetry_entries = _load_telemetry_events(telemetry_log)

    if output_path is None:
        output_path = os.path.join(artifacts_dir, 'telemetry_dashboard.html')

    # Aggregate stats
    total_runs = len(reports)
    fidelities = [r.get('fidelity_score', r.get('overall_fidelity', 0))
                  for r in reports if r.get('fidelity_score') or r.get('overall_fidelity')]
    avg_fidelity = round(sum(fidelities) / len(fidelities), 1) if fidelities else 0
    max_fidelity = max(fidelities) if fidelities else 0
    min_fidelity = min(fidelities) if fidelities else 0

    # Items aggregation
    all_items = []
    status_counts = {}
    for r in reports:
        for item in r.get('items', []):
            all_items.append(item)
            st = item.get('status', 'unknown')
            status_counts[st] = status_counts.get(st, 0) + 1

    # Workbook names
    wbs = sorted(set(r.get('workbook_name', r.get('report_name', 'Unknown')) for r in reports))

    # Issue categories
    issue_counts = {}
    for item in all_items:
        notes = item.get('notes', '')
        if 'unsupported' in notes.lower() or 'not supported' in notes.lower():
            issue_counts['Unsupported feature'] = issue_counts.get('Unsupported feature', 0) + 1
        elif 'fallback' in notes.lower():
            issue_counts['Fallback applied'] = issue_counts.get('Fallback applied', 0) + 1
        elif 'manual' in notes.lower():
            issue_counts['Manual review needed'] = issue_counts.get('Manual review needed', 0) + 1

    # Telemetry stats
    tel_sessions = len(telemetry_entries)
    tel_durations = [e.get('duration_seconds', 0) for e in telemetry_entries if e.get('duration_seconds')]
    avg_duration = round(sum(tel_durations) / len(tel_durations), 1) if tel_durations else 0
    total_events = sum(len(e.get('events', [])) for e in telemetry_entries)

    # Bottlenecks
    bottlenecks = _analyze_bottlenecks(reports, telemetry_entries)

    # Portfolio progress
    portfolio = _compute_portfolio_progress(reports)

    # Build HTML
    parts = [f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Migration Observability Dashboard</title>
<style>{get_report_css()}{_CSS_EXTRA}</style>
</head>
<body>
<div class="report-header">
<h1>Migration Observability Dashboard</h1>
<p>Tableau &rarr; Power BI &mdash; {tel_sessions} telemetry sessions, {total_runs} migration reports</p>
</div>
<div class="container">
"""]

    # Tabs
    parts.append('<div class="tab-bar">')
    for name, label in [('overview', 'Overview'), ('portfolio', 'Portfolio'),
                        ('bottlenecks', 'Bottlenecks'), ('telemetry', 'Telemetry')]:
        active = ' active' if name == 'overview' else ''
        parts.append(f'<div class="tab{active}" data-tabgroup="main" data-tab="{name}" '
                     f'onclick="switchTab(\'main\',\'{name}\')">{label}</div>')
    parts.append('</div>')

    # ── Tab: Overview ──────────────────────────────────────────
    parts.append('<div class="tab-content active" data-tabcontent="main" data-tab="overview">')

    # Summary cards
    parts.append('<div class="grid">')
    parts.append(f'<div class="card"><h3>Total Migrations</h3><div class="val">{total_runs}</div>'
                 f'<div class="sub">{len(wbs)} unique workbooks</div></div>')
    parts.append(f'<div class="card"><h3>Avg Fidelity</h3><div class="val">{avg_fidelity}%</div>'
                 f'<div class="sub">min {min_fidelity}% / max {max_fidelity}%</div></div>')
    migrated = status_counts.get('migrated', 0) + status_counts.get('converted', 0)
    partial_ct = status_counts.get('partial', 0)
    skipped = status_counts.get('skipped', 0) + status_counts.get('failed', 0)
    parts.append(f'<div class="card"><h3>Items Migrated</h3><div class="val">{migrated}</div>'
                 f'<div class="sub">{partial_ct} partial, {skipped} skipped/failed</div></div>')
    parts.append(f'<div class="card"><h3>Avg Duration</h3><div class="val">{avg_duration}s</div>'
                 f'<div class="sub">{tel_sessions} telemetry sessions</div></div>')
    parts.append('</div>')

    # Fidelity history
    if fidelities:
        parts.append('<h2>Fidelity History</h2>')
        parts.append('<div class="card">')
        max_bar = max(fidelities) or 1
        for i, f in enumerate(fidelities[-30:]):
            w = int(f / max_bar * 300)
            color = '#4caf50' if f >= 80 else '#ff9800' if f >= 50 else '#f44336'
            parts.append(f'<div style="margin:2px 0"><span class="chart-bar" '
                         f'style="width:{w}px;background:{color}"></span> {f}%</div>')
        parts.append('</div>')

    # Per-workbook table with search + sort
    if reports:
        parts.append('<h2>Migration Runs</h2>')
        parts.append('<div class="toolbar">')
        parts.append('<input type="text" id="search-runs" placeholder="Search workbooks..." '
                     'oninput="filterTable(\'search-runs\',\'tbl-runs\')">')
        parts.append('<input type="date" id="date-runs" '
                     'onchange="filterByDate(\'date-runs\',\'tbl-runs\')">')
        parts.append('</div>')
        parts.append('<table id="tbl-runs"><thead><tr>'
                     '<th onclick="sortTable(\'tbl-runs\',0)">Workbook</th>'
                     '<th onclick="sortTable(\'tbl-runs\',1)">Fidelity</th>'
                     '<th onclick="sortTable(\'tbl-runs\',2)">Items</th>'
                     '<th onclick="sortTable(\'tbl-runs\',3)">Timestamp</th>'
                     '</tr></thead><tbody>')
        for r in reports[-50:]:
            name = r.get('workbook_name', r.get('report_name', ''))
            fid = r.get('fidelity_score', r.get('overall_fidelity', ''))
            items_count = len(r.get('items', []))
            ts = r.get('timestamp', r.get('generated_at', ''))
            try:
                fid_val = float(fid) if fid else 0
            except (TypeError, ValueError):
                fid_val = 0
            cls = 'pass' if fid_val >= 80 else 'warn' if fid_val >= 50 else 'fail'
            parts.append(f'<tr><td>{_esc(name)}</td>'
                         f'<td class="{cls}">{_esc(str(fid))}%</td>'
                         f'<td>{items_count}</td>'
                         f'<td>{_esc(ts)}</td></tr>')
        parts.append('</tbody></table>')

    # Status distribution
    if status_counts:
        parts.append('<h2>Status Distribution</h2>')
        parts.append('<table><thead><tr><th>Status</th><th>Count</th></tr></thead><tbody>')
        for st, cnt in sorted(status_counts.items(), key=lambda x: -x[1]):
            parts.append(f'<tr><td>{_esc(st)}</td><td>{cnt}</td></tr>')
        parts.append('</tbody></table>')

    parts.append('</div>')  # end overview tab

    # ── Tab: Portfolio ─────────────────────────────────────────
    parts.append('<div class="tab-content" data-tabcontent="main" data-tab="portfolio">')
    parts.append('<h2>Portfolio Progress</h2>')
    parts.append('<div class="grid">')
    parts.append(f'<div class="card"><h3>Completed (&#8805;80%)</h3>'
                 f'<div class="val pass">{portfolio["completed"]}</div></div>')
    parts.append(f'<div class="card"><h3>Partial (&lt;80%)</h3>'
                 f'<div class="val warn">{portfolio["partial"]}</div></div>')
    parts.append(f'<div class="card"><h3>Pending</h3>'
                 f'<div class="val">{portfolio["pending"]}</div></div>')
    parts.append(f'<div class="card"><h3>Completion Rate</h3>'
                 f'<div class="val">{portfolio["pct_complete"]}%</div></div>')
    parts.append('</div>')
    # Progress bar
    pct = portfolio['pct_complete']
    color = '#4caf50' if pct >= 75 else '#ff9800' if pct >= 40 else '#f44336'
    parts.append(f'<div class="progress-track"><div class="progress-fill" '
                 f'style="width:{pct}%;background:{color}"></div></div>')
    parts.append(f'<div class="sub" style="text-align:center">'
                 f'{portfolio["completed"]}/{portfolio["total"]} workbooks fully migrated</div>')
    parts.append('</div>')  # end portfolio tab

    # ── Tab: Bottlenecks ───────────────────────────────────────
    parts.append('<div class="tab-content" data-tabcontent="main" data-tab="bottlenecks">')
    parts.append('<h2>Bottleneck Analysis</h2>')
    if bottlenecks:
        parts.append('<table><thead><tr><th>Category</th><th>Status</th>'
                     '<th>Count</th><th>Sample Notes</th></tr></thead><tbody>')
        for b in bottlenecks[:20]:
            samples = '; '.join(b['sample_notes'][:2])
            parts.append(f'<tr><td>{_esc(b["category"])}</td>'
                         f'<td class="fail">{_esc(b["status"])}</td>'
                         f'<td>{b["count"]}</td>'
                         f'<td>{_esc(samples)}</td></tr>')
        parts.append('</tbody></table>')
    else:
        parts.append('<p>No bottlenecks detected — all items migrated successfully.</p>')

    # Common issues
    if issue_counts:
        parts.append('<h2>Common Issues</h2>')
        parts.append('<table><thead><tr><th>Issue</th><th>Occurrences</th></tr></thead><tbody>')
        for issue, cnt in sorted(issue_counts.items(), key=lambda x: -x[1]):
            parts.append(f'<tr><td>{_esc(issue)}</td><td>{cnt}</td></tr>')
        parts.append('</tbody></table>')
    parts.append('</div>')  # end bottlenecks tab

    # ── Tab: Telemetry ─────────────────────────────────────────
    parts.append('<div class="tab-content" data-tabcontent="main" data-tab="telemetry">')
    parts.append('<h2>Telemetry Sessions</h2>')
    parts.append('<div class="grid">')
    parts.append(f'<div class="card"><h3>Sessions</h3><div class="val">{tel_sessions}</div></div>')
    parts.append(f'<div class="card"><h3>Total Events</h3><div class="val">{total_events}</div></div>')
    total_errors = sum(len(e.get('errors', [])) for e in telemetry_entries)
    parts.append(f'<div class="card"><h3>Total Errors</h3>'
                 f'<div class="val fail">{total_errors}</div></div>')
    parts.append(f'<div class="card"><h3>Avg Duration</h3><div class="val">{avg_duration}s</div></div>')
    parts.append('</div>')

    if telemetry_entries:
        parts.append('<table><thead><tr><th>Session</th><th>Timestamp</th>'
                     '<th>Duration</th><th>Events</th><th>Errors</th>'
                     '<th>Platform</th></tr></thead><tbody>')
        for entry in telemetry_entries[-30:]:
            sid = entry.get('session_id', '?')
            ts = entry.get('timestamp', '')
            dur = entry.get('duration_seconds', '')
            evt_count = len(entry.get('events', []))
            err_count = len(entry.get('errors', []))
            plat = entry.get('platform', '')
            parts.append(f'<tr><td>{_esc(sid)}</td><td>{_esc(ts)}</td>'
                         f'<td>{dur}s</td><td>{evt_count}</td>'
                         f'<td>{err_count}</td><td>{_esc(plat)}</td></tr>')
        parts.append('</tbody></table>')
    else:
        parts.append('<p>No telemetry data found. Enable with '
                     '<code>--telemetry</code> or <code>TTPBI_TELEMETRY=1</code>.</p>')
    parts.append('</div>')  # end telemetry tab

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    parts.append(f'<div class="report-footer">Generated: {now} | '
                 f'Tableau &rarr; Power BI Migration Tool</div>')
    parts.append(f'</div><script>{get_report_js()}{_JS_EXTRA}</script></body></html>')

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(parts))
    print(f"  ✓ Observability dashboard: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description='Generate migration observability dashboard')
    parser.add_argument('artifacts_dir', nargs='?', default='artifacts/powerbi_projects',
                        help='Path to artifacts directory with migration reports')
    parser.add_argument('-o', '--output', default=None, help='Output HTML file path')
    parser.add_argument('--telemetry-log', default=None,
                        help='Path to JSONL telemetry log (default: ~/.ttpbi_telemetry.json)')
    args = parser.parse_args()
    generate_dashboard(args.artifacts_dir, args.output, args.telemetry_log)


if __name__ == '__main__':
    main()
