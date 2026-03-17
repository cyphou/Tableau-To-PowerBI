"""
Server-Level Assessment Pipeline — Portfolio Assessment for Tableau Server
or local folder of workbooks.

Produces enterprise-grade readiness reports including:
- Per-workbook RED/YELLOW/GREEN classification
- Connector census (histogram of datasource types)
- Complexity heatmap (5 axes)
- Migration wave planning (grouping by shared data + complexity)
- Effort estimation (hours per workbook)
- Executive HTML dashboard report

Usage (CLI)::

    python migrate.py --bulk-assess folder_of_twbx/
    python migrate.py --server https://tableau.company.com --server-assess

Usage (programmatic)::

    from powerbi_import.server_assessment import (
        ServerAssessment, run_server_assessment, generate_server_html_report
    )

    result = run_server_assessment(all_extracted_list, workbook_names)
    generate_server_html_report(result, "server_assessment.html")
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
    from powerbi_import.assessment import run_assessment, AssessmentReport
except ImportError:
    from assessment import run_assessment, AssessmentReport


# ═══════════════════════════════════════════════════════════════════
#  Constants
# ═══════════════════════════════════════════════════════════════════

PBI_BLUE = "#0078d4"
PBI_DARK = "#323130"
PBI_GRAY = "#605e5c"
PBI_BG = "#f5f5f5"
GREEN = "#107c10"
YELLOW = "#ffb900"
RED = "#d13438"

# Effort estimation weights (hours per unit)
_EFFORT_PER_VISUAL = 0.15
_EFFORT_PER_CALC = 0.2
_EFFORT_PER_LOD = 0.5
_EFFORT_PER_TABLE_CALC = 0.4
_EFFORT_PER_DATASOURCE = 0.3
_EFFORT_PER_TABLE = 0.1
_EFFORT_BASE_HOURS = 1.0  # Base overhead per workbook


# ═══════════════════════════════════════════════════════════════════
#  Data classes
# ═══════════════════════════════════════════════════════════════════

@dataclass
class WorkbookReadiness:
    """Per-workbook readiness result."""
    name: str
    status: str  # "GREEN", "YELLOW", "RED"
    pass_count: int = 0
    warn_count: int = 0
    fail_count: int = 0
    info_count: int = 0
    complexity: Dict[str, int] = field(default_factory=dict)
    effort_hours: float = 0.0
    connector_types: List[str] = field(default_factory=list)
    visual_count: int = 0
    calc_count: int = 0
    table_count: int = 0
    assessment_report: Optional[object] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "pass_count": self.pass_count,
            "warn_count": self.warn_count,
            "fail_count": self.fail_count,
            "info_count": self.info_count,
            "complexity": self.complexity,
            "effort_hours": round(self.effort_hours, 1),
            "connector_types": self.connector_types,
            "visual_count": self.visual_count,
            "calc_count": self.calc_count,
            "table_count": self.table_count,
        }


@dataclass
class MigrationWave:
    """A group of workbooks to migrate together."""
    wave_number: int
    label: str  # "Easy", "Medium", "Complex"
    workbooks: List[str] = field(default_factory=list)
    total_effort: float = 0.0

    def to_dict(self) -> dict:
        return {
            "wave_number": self.wave_number,
            "label": self.label,
            "workbooks": self.workbooks,
            "total_effort": round(self.total_effort, 1),
        }


@dataclass
class ServerAssessment:
    """Complete server-level assessment result."""
    workbook_results: List[WorkbookReadiness] = field(default_factory=list)
    connector_census: Dict[str, int] = field(default_factory=dict)
    waves: List[MigrationWave] = field(default_factory=list)
    total_workbooks: int = 0
    green_count: int = 0
    yellow_count: int = 0
    red_count: int = 0
    total_effort_hours: float = 0.0
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "total_workbooks": self.total_workbooks,
            "green_count": self.green_count,
            "yellow_count": self.yellow_count,
            "red_count": self.red_count,
            "total_effort_hours": round(self.total_effort_hours, 1),
            "workbook_results": [r.to_dict() for r in self.workbook_results],
            "connector_census": self.connector_census,
            "waves": [w.to_dict() for w in self.waves],
        }

    @property
    def readiness_pct(self) -> int:
        if self.total_workbooks == 0:
            return 0
        return int(self.green_count / self.total_workbooks * 100)


# ═══════════════════════════════════════════════════════════════════
#  Core pipeline
# ═══════════════════════════════════════════════════════════════════

def run_server_assessment(
    all_extracted: List[dict],
    workbook_names: List[str],
) -> ServerAssessment:
    """Run portfolio-level assessment across multiple workbooks.

    Args:
        all_extracted: List of extracted workbook dicts.
        workbook_names: Parallel list of workbook names.

    Returns:
        ServerAssessment with per-workbook scoring and aggregated analysis.
    """
    result = ServerAssessment(
        total_workbooks=len(workbook_names),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    connector_counter: Dict[str, int] = {}

    for wb_name, extracted in zip(workbook_names, all_extracted):
        readiness = _assess_single_workbook(wb_name, extracted)
        result.workbook_results.append(readiness)

        # Accumulate connector census
        for conn in readiness.connector_types:
            connector_counter[conn] = connector_counter.get(conn, 0) + 1

        # Accumulate totals
        if readiness.status == "GREEN":
            result.green_count += 1
        elif readiness.status == "YELLOW":
            result.yellow_count += 1
        else:
            result.red_count += 1
        result.total_effort_hours += readiness.effort_hours

    result.connector_census = dict(
        sorted(connector_counter.items(), key=lambda x: x[1], reverse=True)
    )

    # Build migration waves
    result.waves = _build_migration_waves(result.workbook_results)

    return result


def _assess_single_workbook(wb_name: str, extracted: dict) -> WorkbookReadiness:
    """Run assessment on a single workbook and produce readiness result."""
    report = run_assessment(extracted)

    pass_c = warn_c = fail_c = info_c = 0
    for cat in report.categories:
        for check in cat.checks:
            if check.severity == "pass":
                pass_c += 1
            elif check.severity == "warn":
                warn_c += 1
            elif check.severity == "fail":
                fail_c += 1
            else:
                info_c += 1

    # Classify status
    if fail_c == 0 and warn_c <= 2:
        status = "GREEN"
    elif fail_c <= 2:
        status = "YELLOW"
    else:
        status = "RED"

    # Extract complexity metrics
    complexity = _compute_complexity(extracted)

    # Extract connector types
    connectors = []
    for ds in extracted.get('datasources', []):
        conn = ds.get('connection', {})
        ctype = conn.get('type', 'unknown')
        if ctype and ctype not in connectors:
            connectors.append(ctype)

    # Estimate effort
    effort = _estimate_effort(extracted, complexity)

    return WorkbookReadiness(
        name=wb_name,
        status=status,
        pass_count=pass_c,
        warn_count=warn_c,
        fail_count=fail_c,
        info_count=info_c,
        complexity=complexity,
        effort_hours=effort,
        connector_types=connectors,
        visual_count=complexity.get('visuals', 0),
        calc_count=complexity.get('calculations', 0),
        table_count=complexity.get('tables', 0),
        assessment_report=report,
    )


def _compute_complexity(extracted: dict) -> Dict[str, int]:
    """Compute complexity metrics for a workbook."""
    visuals = len(extracted.get('worksheets', []))
    dashboards = len(extracted.get('dashboards', []))

    calc_count = len(extracted.get('calculations', []))
    for ds in extracted.get('datasources', []):
        calc_count += len(ds.get('calculations', []))

    table_count = 0
    for ds in extracted.get('datasources', []):
        table_count += sum(
            1 for t in ds.get('tables', [])
            if t.get('type', 'table') == 'table'
        )

    lod_count = 0
    table_calc_count = 0
    all_calcs = list(extracted.get('calculations', []))
    for ds in extracted.get('datasources', []):
        all_calcs.extend(ds.get('calculations', []))
    for calc in all_calcs:
        formula = calc.get('formula', '')
        if '{' in formula and any(
            kw in formula.upper() for kw in ('FIXED', 'INCLUDE', 'EXCLUDE')
        ):
            lod_count += 1
        if any(kw in formula.upper() for kw in (
            'RUNNING_', 'WINDOW_', 'RANK(', 'RANK_', 'INDEX(', 'FIRST(', 'LAST(',
        )):
            table_calc_count += 1

    filters = len(extracted.get('filters', []))
    actions = len(extracted.get('actions', []))

    return {
        'visuals': visuals,
        'dashboards': dashboards,
        'calculations': calc_count,
        'tables': table_count,
        'lod_expressions': lod_count,
        'table_calcs': table_calc_count,
        'filters': filters,
        'actions': actions,
    }


def _estimate_effort(extracted: dict, complexity: Dict[str, int]) -> float:
    """Estimate migration effort in hours."""
    hours = _EFFORT_BASE_HOURS
    hours += complexity.get('visuals', 0) * _EFFORT_PER_VISUAL
    hours += complexity.get('calculations', 0) * _EFFORT_PER_CALC
    hours += complexity.get('lod_expressions', 0) * _EFFORT_PER_LOD
    hours += complexity.get('table_calcs', 0) * _EFFORT_PER_TABLE_CALC
    hours += complexity.get('tables', 0) * _EFFORT_PER_TABLE

    ds_count = len(extracted.get('datasources', []))
    hours += ds_count * _EFFORT_PER_DATASOURCE

    return round(hours, 1)


def _build_migration_waves(
    workbook_results: List[WorkbookReadiness],
) -> List[MigrationWave]:
    """Group workbooks into migration waves based on complexity."""
    easy = []
    medium = []
    hard = []

    for r in workbook_results:
        score = (
            r.complexity.get('calculations', 0) +
            r.complexity.get('lod_expressions', 0) * 3 +
            r.complexity.get('table_calcs', 0) * 2
        )
        if r.status == "GREEN" and score <= 5:
            easy.append(r)
        elif r.status == "RED" or score > 20:
            hard.append(r)
        else:
            medium.append(r)

    waves = []
    wave_num = 1
    if easy:
        waves.append(MigrationWave(
            wave_number=wave_num,
            label="Easy (quick wins)",
            workbooks=[r.name for r in easy],
            total_effort=sum(r.effort_hours for r in easy),
        ))
        wave_num += 1
    if medium:
        waves.append(MigrationWave(
            wave_number=wave_num,
            label="Medium (standard migration)",
            workbooks=[r.name for r in medium],
            total_effort=sum(r.effort_hours for r in medium),
        ))
        wave_num += 1
    if hard:
        waves.append(MigrationWave(
            wave_number=wave_num,
            label="Complex (manual review recommended)",
            workbooks=[r.name for r in hard],
            total_effort=sum(r.effort_hours for r in hard),
        ))

    return waves


# ═══════════════════════════════════════════════════════════════════
#  JSON output
# ═══════════════════════════════════════════════════════════════════

def save_server_assessment_json(
    assessment: ServerAssessment, output_path: str
) -> dict:
    """Save server assessment to JSON file."""
    report = assessment.to_dict()
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    logger.info("Server assessment saved to %s", output_path)
    return report


# ═══════════════════════════════════════════════════════════════════
#  Console summary
# ═══════════════════════════════════════════════════════════════════

def print_server_summary(assessment: ServerAssessment):
    """Print a formatted console summary of the server assessment."""
    w = 70
    print()
    print("=" * w)
    print("  Tableau Server — Portfolio Assessment".center(w))
    print("=" * w)

    print(f"  Total workbooks:    {assessment.total_workbooks}")
    print(f"  GREEN (ready):      {assessment.green_count}")
    print(f"  YELLOW (review):    {assessment.yellow_count}")
    print(f"  RED (complex):      {assessment.red_count}")
    print(f"  Readiness:          {assessment.readiness_pct}%")
    print(f"  Est. total effort:  {assessment.total_effort_hours:.1f} hours")
    print("-" * w)

    # Connector census
    if assessment.connector_census:
        print("  CONNECTOR CENSUS:")
        for conn, count in assessment.connector_census.items():
            bar = "#" * min(count, 30)
            print(f"    {conn:<20} {bar} ({count})")
        print()

    # Waves
    for wave in assessment.waves:
        print(f"  WAVE {wave.wave_number}: {wave.label}")
        for wb in wave.workbooks:
            print(f"    - {wb}")
        print(f"    Est. effort: {wave.total_effort:.1f} hours")
        print()

    print("=" * w)


# ═══════════════════════════════════════════════════════════════════
#  HTML report generator
# ═══════════════════════════════════════════════════════════════════

def generate_server_html_report(
    assessment: ServerAssessment,
    output_path: str = "server_assessment.html",
) -> str:
    """Generate an executive HTML dashboard report for the server assessment."""

    # Readiness pie data
    pie_data = {
        'GREEN': assessment.green_count,
        'YELLOW': assessment.yellow_count,
        'RED': assessment.red_count,
    }

    # Top connectors
    connector_rows = ""
    for conn, count in assessment.connector_census.items():
        pct = int(count / max(assessment.total_workbooks, 1) * 100)
        connector_rows += f"""
            <tr>
                <td>{conn}</td>
                <td>{count}</td>
                <td>
                    <div style="background:{PBI_BLUE};width:{pct}%;height:16px;border-radius:3px"></div>
                </td>
            </tr>"""

    # Workbook detail rows
    wb_rows = ""
    for r in sorted(assessment.workbook_results, key=lambda x: x.effort_hours, reverse=True):
        color = GREEN if r.status == "GREEN" else (YELLOW if r.status == "YELLOW" else RED)
        wb_rows += f"""
            <tr>
                <td><span style="color:{color};font-weight:bold">{r.status}</span></td>
                <td>{r.name}</td>
                <td>{r.visual_count}</td>
                <td>{r.calc_count}</td>
                <td>{r.table_count}</td>
                <td>{r.complexity.get('lod_expressions', 0)}</td>
                <td>{r.effort_hours:.1f}h</td>
                <td>{', '.join(r.connector_types) or 'N/A'}</td>
            </tr>"""

    # Wave rows
    wave_rows = ""
    for wave in assessment.waves:
        wave_rows += f"""
            <tr>
                <td><strong>Wave {wave.wave_number}</strong></td>
                <td>{wave.label}</td>
                <td>{len(wave.workbooks)}</td>
                <td>{wave.total_effort:.1f}h</td>
                <td>{', '.join(wave.workbooks[:5])}{'...' if len(wave.workbooks) > 5 else ''}</td>
            </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Tableau Server Assessment</title>
<style>
    body {{ font-family: 'Segoe UI', sans-serif; margin: 20px; background: {PBI_BG}; color: {PBI_DARK}; }}
    h1 {{ color: {PBI_BLUE}; }}
    h2 {{ color: {PBI_DARK}; border-bottom: 2px solid {PBI_BLUE}; padding-bottom: 6px; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; background: white; }}
    th, td {{ padding: 8px 12px; border: 1px solid #e0e0e0; text-align: left; }}
    th {{ background: {PBI_BLUE}; color: white; }}
    .summary-box {{ display: inline-block; padding: 16px 24px; margin: 8px; background: white;
                   border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.1); text-align: center; }}
    .summary-box .number {{ font-size: 2em; font-weight: bold; }}
    .green {{ color: {GREEN}; }}
    .yellow {{ color: {YELLOW}; }}
    .red {{ color: {RED}; }}
    .blue {{ color: {PBI_BLUE}; }}
</style>
</head>
<body>
<h1>Tableau Server — Portfolio Assessment</h1>
<p>Generated: {assessment.timestamp}</p>

<div>
    <div class="summary-box">
        <div class="number blue">{assessment.total_workbooks}</div>
        <div>Total Workbooks</div>
    </div>
    <div class="summary-box">
        <div class="number green">{assessment.green_count}</div>
        <div>GREEN (Ready)</div>
    </div>
    <div class="summary-box">
        <div class="number yellow">{assessment.yellow_count}</div>
        <div>YELLOW (Review)</div>
    </div>
    <div class="summary-box">
        <div class="number red">{assessment.red_count}</div>
        <div>RED (Complex)</div>
    </div>
    <div class="summary-box">
        <div class="number blue">{assessment.readiness_pct}%</div>
        <div>Readiness</div>
    </div>
    <div class="summary-box">
        <div class="number blue">{assessment.total_effort_hours:.1f}h</div>
        <div>Est. Total Effort</div>
    </div>
</div>

<h2>Connector Census</h2>
<table>
    <tr><th>Connector</th><th>Count</th><th>Distribution</th></tr>
    {connector_rows}
</table>

<h2>Migration Waves</h2>
<table>
    <tr><th>Wave</th><th>Classification</th><th>Workbooks</th><th>Effort</th><th>Members</th></tr>
    {wave_rows}
</table>

<h2>Workbook Detail</h2>
<table>
    <tr>
        <th>Status</th><th>Workbook</th><th>Visuals</th><th>Calcs</th>
        <th>Tables</th><th>LOD</th><th>Effort</th><th>Connectors</th>
    </tr>
    {wb_rows}
</table>

</body>
</html>"""

    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    logger.info("Server assessment HTML report saved to %s", output_path)
    return output_path
