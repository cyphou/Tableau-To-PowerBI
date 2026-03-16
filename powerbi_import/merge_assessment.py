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

    # Unique tables
    if assessment.unique_tables:
        print("  UNIQUE TABLES (no merge possible):")
        for wb, tables in assessment.unique_tables.items():
            for t in tables:
                print(f"    {t:<25} — only in {wb}")
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
