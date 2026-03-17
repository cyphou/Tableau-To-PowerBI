"""
Merge Assessment Reporter — JSON + console output for shared semantic model merging.

Generates a detailed assessment report showing:
- Merge candidates (shared tables) with column overlap
- Measure conflicts and deduplication stats
- Relationship and parameter deduplication
- Merge score and recommendation

Usage::

    from powerbi_import.merge_assessment import generate_merge_report, print_merge_summary
    from powerbi_import.shared_model import assess_merge

    assessment = assess_merge(all_extracted, workbook_names)
    print_merge_summary(assessment)
    generate_merge_report(assessment, output_path="merge_assessment.json")
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

try:
    from powerbi_import.shared_model import MergeAssessment
except ImportError:
    from shared_model import MergeAssessment

# HTML report colors
_PBI_BLUE = "#0078d4"
_PBI_DARK = "#323130"
_PBI_BG = "#f5f5f5"
_GREEN = "#107c10"
_YELLOW = "#ffb900"
_RED = "#d13438"


def generate_merge_report(assessment: MergeAssessment,
                          output_path: str = None) -> dict:
    """Generate a detailed merge assessment report.

    Args:
        assessment: The MergeAssessment from assess_merge().
        output_path: Optional file path to write merge_assessment.json.

    Returns:
        The report dict.
    """
    report = assessment.to_dict()
    report['timestamp'] = datetime.now(timezone.utc).isoformat()

    if output_path:
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        logger.info("Merge assessment saved to %s", output_path)

    return report


def print_merge_summary(assessment: MergeAssessment):
    """Print a formatted console summary of the merge assessment."""
    w = 64  # Box width

    print()
    print("=" * w)
    print("  Shared Semantic Model — Merge Assessment".center(w))
    print("=" * w)

    # Overview
    tables_saved = assessment.total_tables - assessment.unique_table_count
    pct = int(tables_saved / max(assessment.total_tables, 1) * 100)
    print(f"  Workbooks analyzed:           {len(assessment.workbooks)}")
    print(f"  Total tables found:           {assessment.total_tables}")
    print(f"  Unique tables (after merge):  {assessment.unique_table_count}")
    print(f"  Tables saved by merging:      {tables_saved} ({pct}%)")
    print("-" * w)

    # Merge candidates
    if assessment.merge_candidates:
        print("  MERGE CANDIDATES (same connection + table name):")
        print()
        for mc in assessment.merge_candidates:
            wb_count = len(mc.sources)
            wb_total = len(assessment.workbooks)
            overlap_pct = int(mc.column_overlap * 100)
            marker = "OK" if overlap_pct >= 70 else "WARN"
            print(f"    [{marker}] {mc.table_name:<20} — "
                  f"found in {wb_count}/{wb_total} workbooks "
                  f"({overlap_pct}% col match)")
            if mc.conflicts:
                for c in mc.conflicts[:3]:
                    print(f"         ! {c}")
        print()

    # Measure conflicts
    if assessment.measure_conflicts:
        print("  MEASURE CONFLICTS:")
        print()
        for mc in assessment.measure_conflicts:
            print(f"    ! [{mc.name}] — different DAX in "
                  f"{', '.join(mc.variants.keys())}")
            for wb, formula in mc.variants.items():
                short = formula[:60] + '...' if len(formula) > 60 else formula
                print(f"      {wb}: {short}")
            print(f"      -> Will create [{mc.name} (workbook)] per variant")
        print()

    # Unique tables — split into linked and isolated
    if assessment.unique_tables:
        # Show linked unique tables (will be included in merged model)
        if assessment.linked_unique_tables:
            print("  LINKED UNIQUE TABLES (included in shared model):")
            for wb, tables in assessment.linked_unique_tables.items():
                for t in tables:
                    print(f"    ✓ {t:<25} — only in {wb}, but linked to shared tables")
            print()

        # Show isolated tables (will NOT be included in merged model)
        if assessment.isolated_tables:
            print("  ISOLATED TABLES (excluded from shared model — no links):")
            for wb, tables in assessment.isolated_tables.items():
                for t in tables:
                    print(f"    ✗ {t:<25} — only in {wb}, no relationships to other tables")
            print()

    # Stats
    print("-" * w)
    total_measures = (
        assessment.measure_duplicates_removed + len(assessment.measure_conflicts)
    )
    print(f"  MEASURES:       {total_measures} shared, "
          f"{assessment.measure_duplicates_removed} duplicates removed, "
          f"{len(assessment.measure_conflicts)} conflicts")
    print(f"  RELATIONSHIPS:  {assessment.relationship_duplicates_removed} "
          f"duplicates removed")
    print(f"  PARAMETERS:     {assessment.parameter_duplicates_removed} "
          f"duplicates removed, "
          f"{len(assessment.parameter_conflicts)} conflicts")

    # Recommendation
    print("-" * w)
    rec_labels = {
        "merge": "MERGE RECOMMENDED",
        "partial": "PARTIAL MERGE (review conflicts)",
        "separate": "KEEP SEPARATE (low overlap)",
    }
    rec = rec_labels.get(assessment.recommendation, assessment.recommendation)
    print(f"  Merge score:      {assessment.merge_score}/100")
    print(f"  Recommendation:   {rec}")
    print("=" * w)
    print()


def generate_merge_html_report(
    assessment: MergeAssessment,
    output_path: str = "merge_assessment.html",
    rls_conflicts: list = None,
    relationship_suggestions: list = None,
) -> str:
    """Generate an HTML merge assessment report.

    Args:
        assessment: MergeAssessment result.
        output_path: Path to write the HTML file.
        rls_conflicts: Optional list of RLS conflicts from detect_rls_conflicts().
        relationship_suggestions: Optional list from suggest_cross_workbook_relationships().

    Returns:
        Path to the generated HTML file.
    """
    rls_conflicts = rls_conflicts or []
    relationship_suggestions = relationship_suggestions or []

    # Candidate rows
    candidate_rows = ""
    for mc in assessment.merge_candidates:
        overlap_pct = int(mc.column_overlap * 100)
        color = _GREEN if overlap_pct >= 70 else (_YELLOW if overlap_pct >= 40 else _RED)
        sources = ", ".join(s[0] for s in mc.sources)
        conflicts_html = "<br>".join(mc.conflicts[:3]) if mc.conflicts else "None"
        candidate_rows += f"""
            <tr>
                <td>{mc.table_name}</td>
                <td>{sources}</td>
                <td><span style="color:{color};font-weight:bold">{overlap_pct}%</span></td>
                <td>{conflicts_html}</td>
            </tr>"""

    # Measure conflict rows
    measure_rows = ""
    for mc in assessment.measure_conflicts:
        for wb, formula in mc.variants.items():
            short = formula[:80] + '...' if len(formula) > 80 else formula
            measure_rows += f"""
                <tr>
                    <td>{mc.name}</td>
                    <td>{wb}</td>
                    <td><code>{short}</code></td>
                </tr>"""

    # RLS conflict rows
    rls_rows = ""
    for rc in rls_conflicts:
        for wb, expr in rc.get('variants', {}).items():
            short = str(expr)[:80] + '...' if len(str(expr)) > 80 else str(expr)
            rls_rows += f"""
                <tr>
                    <td>{rc.get('role_name', 'N/A')}</td>
                    <td>{rc.get('table', 'N/A')}</td>
                    <td>{wb}</td>
                    <td><code>{short}</code></td>
                </tr>"""

    # Relationship suggestion rows
    rel_rows = ""
    for rs in relationship_suggestions:
        color = _GREEN if rs.get('confidence') == 'high' else _YELLOW
        rel_rows += f"""
            <tr>
                <td>{rs.get('from_table', '')}</td>
                <td>{rs.get('from_column', '')}</td>
                <td>{rs.get('to_table', '')}</td>
                <td>{rs.get('to_column', '')}</td>
                <td><span style="color:{color}">{rs.get('confidence', 'medium')}</span></td>
            </tr>"""

    # Score color
    score = assessment.merge_score
    score_color = _GREEN if score >= 60 else (_YELLOW if score >= 30 else _RED)
    rec_labels = {
        "merge": "MERGE RECOMMENDED",
        "partial": "PARTIAL MERGE (review conflicts)",
        "separate": "KEEP SEPARATE (low overlap)",
    }
    rec = rec_labels.get(assessment.recommendation, assessment.recommendation)
    tables_saved = assessment.total_tables - assessment.unique_table_count

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Merge Assessment Report</title>
<style>
    body {{ font-family: 'Segoe UI', sans-serif; margin: 20px; background: {_PBI_BG}; color: {_PBI_DARK}; }}
    h1 {{ color: {_PBI_BLUE}; }}
    h2 {{ color: {_PBI_DARK}; border-bottom: 2px solid {_PBI_BLUE}; padding-bottom: 6px; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; background: white; }}
    th, td {{ padding: 8px 12px; border: 1px solid #e0e0e0; text-align: left; }}
    th {{ background: {_PBI_BLUE}; color: white; }}
    code {{ background: #f0f0f0; padding: 2px 4px; border-radius: 3px; font-size: 0.9em; }}
    .box {{ display: inline-block; padding: 16px 24px; margin: 8px; background: white;
            border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.1); text-align: center; }}
    .box .num {{ font-size: 2em; font-weight: bold; }}
</style>
</head>
<body>
<h1>Shared Semantic Model — Merge Assessment</h1>
<p>Workbooks: {', '.join(assessment.workbooks)}</p>

<div>
    <div class="box">
        <div class="num" style="color:{score_color}">{score}/100</div>
        <div>Merge Score</div>
    </div>
    <div class="box">
        <div class="num">{assessment.total_tables}</div>
        <div>Total Tables</div>
    </div>
    <div class="box">
        <div class="num" style="color:{_GREEN}">{tables_saved}</div>
        <div>Tables Saved</div>
    </div>
    <div class="box">
        <div class="num">{len(assessment.measure_conflicts)}</div>
        <div>Measure Conflicts</div>
    </div>
    <div class="box">
        <div class="num">{rec}</div>
        <div>Recommendation</div>
    </div>
</div>

<h2>Merge Candidates</h2>
<table>
    <tr><th>Table</th><th>Workbooks</th><th>Column Overlap</th><th>Conflicts</th></tr>
    {candidate_rows if candidate_rows else '<tr><td colspan="4">No merge candidates found</td></tr>'}
</table>

<h2>Measure Conflicts</h2>
<table>
    <tr><th>Measure</th><th>Workbook</th><th>Formula</th></tr>
    {measure_rows if measure_rows else '<tr><td colspan="3">No measure conflicts</td></tr>'}
</table>

<h2>RLS Conflicts</h2>
<table>
    <tr><th>Role</th><th>Table</th><th>Workbook</th><th>Expression</th></tr>
    {rls_rows if rls_rows else '<tr><td colspan="4">No RLS conflicts detected</td></tr>'}
</table>

<h2>Suggested Relationships</h2>
<table>
    <tr><th>From Table</th><th>From Column</th><th>To Table</th><th>To Column</th><th>Confidence</th></tr>
    {rel_rows if rel_rows else '<tr><td colspan="5">No relationship suggestions</td></tr>'}
</table>

</body>
</html>"""

    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    logger.info("Merge HTML report saved to %s", output_path)
    return output_path
