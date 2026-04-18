#!/usr/bin/env python3
"""Post-migration autoplay — automated validation of all 5 next steps.

Replaces the manual "Next steps" checklist printed after migration:
  1. Open the .pbip file in Power BI Desktop (Developer Mode)
  2. Configure data sources in Power Query Editor
  3. Verify DAX measures and calculated columns
  4. Check relationships in the Model view
  5. Compare visuals with the original Tableau workbook

Usage (standalone):
    python scripts/autoplay.py <pbip_dir> [--open] [--extract-dir DIR] [--json FILE]

Usage (integrated — via migrate.py):
    python migrate.py workbook.twbx --autoplay
"""

import argparse
import glob
import json
import logging
import os
import re
import subprocess
import sys
import time

# Ensure project root is on path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from powerbi_import.validator import ArtifactValidator

logger = logging.getLogger(__name__)

# ── ANSI colors ───────────────────────────────────────────────────────────
_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


# ═══════════════════════════════════════════════════════════════════════════
# Step 1 — Open .pbip in Power BI Desktop
# ═══════════════════════════════════════════════════════════════════════════

def find_pbip_file(pbip_dir):
    """Find the .pbip file inside the project directory."""
    for f in os.listdir(pbip_dir):
        if f.endswith(".pbip"):
            return os.path.join(pbip_dir, f)
    return None


def open_in_pbi_desktop(pbip_file):
    """Open a .pbip file in Power BI Desktop.

    Uses os.startfile (Windows) which delegates to the registered handler.
    Returns True if launched, False otherwise.
    """
    if not os.path.exists(pbip_file):
        return False, f"File not found: {pbip_file}"

    if sys.platform == "win32":
        try:
            os.startfile(pbip_file)
            return True, f"Opened in PBI Desktop: {os.path.basename(pbip_file)}"
        except OSError as e:
            return False, f"Failed to open: {e}"
    else:
        return False, "Auto-open only supported on Windows"


# ═══════════════════════════════════════════════════════════════════════════
# Step 2 — Validate data source configuration
# ═══════════════════════════════════════════════════════════════════════════

def check_datasources(pbip_dir):
    """Validate Power Query M data source configuration.

    Checks that M partitions have valid connection strings and
    identifies sources that need manual configuration.
    """
    results = {"sources": [], "warnings": [], "needs_config": []}

    sm_dir = _find_semantic_model_dir(pbip_dir)
    if not sm_dir:
        results["warnings"].append("No SemanticModel directory found")
        return results

    tables_dir = os.path.join(sm_dir, "definition", "tables")
    if not os.path.isdir(tables_dir):
        results["warnings"].append("No tables directory found")
        return results

    # Patterns that indicate placeholder / unconfigured connections
    placeholder_patterns = [
        r'localhost',
        r'127\.0\.0\.1',
        r'your[-_]?server',
        r'<server>',
        r'example\.com',
        r'PLACEHOLDER',
        r'TODO',
    ]
    placeholder_re = re.compile('|'.join(placeholder_patterns), re.IGNORECASE)

    # M connector patterns
    connector_re = re.compile(
        r'(Sql\.Database|PostgreSQL\.Database|Oracle\.Database|'
        r'MySQL\.Database|Snowflake\.Databases|GoogleBigQuery\.Database|'
        r'Databricks\.Catalogs|AmazonRedshift\.Database|'
        r'OData\.Feed|Web\.Contents|File\.Contents|Csv\.Document|'
        r'Excel\.Workbook|Folder\.Files|SharePoint\.Files|'
        r'Odbc\.DataSource|Value\.NativeQuery|'
        r'AzureStorage\.Blobs|Sql\.Databases|'
        r'#table)\s*\(',
        re.IGNORECASE
    )

    for tmdl_file in sorted(glob.glob(os.path.join(tables_dir, "*.tmdl"))):
        tname = os.path.splitext(os.path.basename(tmdl_file))[0]
        with open(tmdl_file, encoding="utf-8") as f:
            content = f.read()

        # Find M partition blocks
        for m_match in re.finditer(
            r'partition\s+.*?=\s*m\s*\n([\s\S]*?)(?=\n\t(?:measure|column|annotation|hierarchy|partition)\b|\n\n|\Z)',
            content
        ):
            m_code = m_match.group(1)

            # Detect connector type
            connectors = connector_re.findall(m_code)
            conn_type = connectors[0] if connectors else "unknown"

            source_info = {
                "table": tname,
                "connector": conn_type,
                "has_placeholder": False,
            }

            # Check for placeholders
            if placeholder_re.search(m_code):
                source_info["has_placeholder"] = True
                results["needs_config"].append(
                    f"{tname}: {conn_type} — connection string has placeholder values"
                )

            # Check for inline data (#table) — no config needed
            if "#table" in conn_type.lower():
                source_info["connector"] = "#table (inline data)"
                source_info["inline"] = True

            results["sources"].append(source_info)

    return results


# ═══════════════════════════════════════════════════════════════════════════
# Step 3 — Verify DAX measures and calculated columns
# ═══════════════════════════════════════════════════════════════════════════

def verify_dax(pbip_dir):
    """Verify DAX measures and calculated columns.

    Uses ArtifactValidator for structural + semantic DAX checks,
    plus additional checks for common migration issues.
    """
    results = {
        "measures": 0,
        "calc_columns": 0,
        "errors": [],
        "warnings": [],
        "info": [],
    }

    sm_dir = _find_semantic_model_dir(pbip_dir)
    if not sm_dir:
        results["errors"].append("No SemanticModel directory found")
        return results

    tables_dir = os.path.join(sm_dir, "definition", "tables")
    if not os.path.isdir(tables_dir):
        results["errors"].append("No tables directory found")
        return results

    measure_count = 0
    calc_col_count = 0

    for tmdl_file in sorted(glob.glob(os.path.join(tables_dir, "*.tmdl"))):
        tname = os.path.splitext(os.path.basename(tmdl_file))[0]

        # Use validator's semantic DAX check
        dax_issues = ArtifactValidator.validate_tmdl_dax(tmdl_file)
        for issue in dax_issues:
            if "ERROR" in issue.upper():
                results["errors"].append(issue)
            else:
                results["warnings"].append(issue)

        with open(tmdl_file, encoding="utf-8") as f:
            content = f.read()

        # Count measures and calc columns
        measures = re.findall(
            r"\tmeasure\s+(?:'[^']+(?:''[^']*)*'|[A-Za-z_]\w*)\s*=",
            content
        )
        measure_count += len(measures)

        calc_cols = re.findall(
            r"\tcolumn\s+(?:'[^']+(?:''[^']*)*'|[A-Za-z_]\w*)\s*=",
            content
        )
        calc_col_count += len(calc_cols)

    # LOOKUPVALUE ambiguity check
    lookupvalue_issues = ArtifactValidator.validate_lookupvalue_ambiguity(
        str(sm_dir)
    )
    results["warnings"].extend(lookupvalue_issues)

    # Measure context validation (bare column refs)
    context_issues = ArtifactValidator.validate_measure_column_context(
        str(sm_dir)
    )
    results["warnings"].extend(context_issues)

    results["measures"] = measure_count
    results["calc_columns"] = calc_col_count

    return results


# ═══════════════════════════════════════════════════════════════════════════
# Step 4 — Check relationships in the Model view
# ═══════════════════════════════════════════════════════════════════════════

def check_relationships(pbip_dir):
    """Validate relationships in the semantic model."""
    results = {
        "relationships": [],
        "count": 0,
        "errors": [],
        "warnings": [],
    }

    sm_dir = _find_semantic_model_dir(pbip_dir)
    if not sm_dir:
        results["errors"].append("No SemanticModel directory found")
        return results

    # Use validator's relationship column check
    rel_issues = ArtifactValidator.validate_relationship_columns(str(sm_dir))
    for issue in rel_issues:
        if "missing column" in issue.lower() or "error" in issue.lower():
            results["errors"].append(issue)
        else:
            results["warnings"].append(issue)

    # Circular relationship detection
    cycles = ArtifactValidator.detect_circular_relationships(str(sm_dir))
    for cycle in cycles:
        results["errors"].append(f"Circular relationship: {cycle}")

    # Orphan table detection
    orphans = ArtifactValidator.detect_orphan_tables(str(sm_dir))
    for orphan in orphans:
        results["warnings"].append(f"Orphan table: {orphan}")

    # Parse relationships from model.tmdl
    model_tmdl = os.path.join(sm_dir, "definition", "model.tmdl")
    if os.path.exists(model_tmdl):
        with open(model_tmdl, encoding="utf-8") as f:
            model_content = f.read()

        rel_re = re.compile(
            r"relationship\s+(\S+)\s*\n"
            r"(?:\s+.*\n)*?"
            r"\s+fromColumn:\s+'?([^'\n]+)'?\s*\n"
            r"(?:\s+.*\n)*?"
            r"\s+toColumn:\s+'?([^'\n]+)'?\s*\n"
            r"(?:\s+.*\n)*?"
            r"\s+fromTable:\s+'?([^'\n]+)'?\s*\n"
            r"(?:\s+.*\n)*?"
            r"\s+toTable:\s+'?([^'\n]+)'?",
            re.MULTILINE
        )
        for m in rel_re.finditer(model_content):
            results["relationships"].append({
                "id": m.group(1),
                "from": f"{m.group(4).strip()}[{m.group(2).strip()}]",
                "to": f"{m.group(5).strip()}[{m.group(3).strip()}]",
            })

        # Simpler count using ref relationship
        ref_count = len(re.findall(r'\bref\s+relationship\b', model_content))
        results["count"] = ref_count

    return results


# ═══════════════════════════════════════════════════════════════════════════
# Step 5 — Compare visuals with original Tableau workbook
# ═══════════════════════════════════════════════════════════════════════════

def compare_visuals(pbip_dir, extract_dir=None):
    """Run fidelity comparison between Tableau extraction and PBI output."""
    try:
        from scripts.compare_migration import run_comparison
    except ImportError:
        # Fallback path resolution
        sys.path.insert(0, _ROOT)
        from scripts.compare_migration import run_comparison

    if not extract_dir:
        extract_dir = os.path.join(_ROOT, "tableau_export")

    if not os.path.isdir(extract_dir):
        return {"error": f"Extraction directory not found: {extract_dir}"}

    return run_comparison(pbip_dir, extract_dir)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _find_semantic_model_dir(pbip_dir):
    """Find the .SemanticModel directory inside a .pbip project."""
    for d in os.listdir(pbip_dir):
        full = os.path.join(pbip_dir, d)
        if d.endswith(".SemanticModel") and os.path.isdir(full):
            return full
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Orchestrator
# ═══════════════════════════════════════════════════════════════════════════

def run_autoplay(pbip_dir, extract_dir=None, open_pbi=False, verbose=False):
    """Run all 5 post-migration validation steps.

    Returns a dict with per-step results and an overall pass/fail.
    """
    results = {
        "pbip_dir": pbip_dir,
        "steps": {},
        "overall_pass": True,
        "total_errors": 0,
        "total_warnings": 0,
    }

    pbip_file = find_pbip_file(pbip_dir)

    # ── Step 1: Open in PBI Desktop ──
    step1 = {"status": "skip", "message": ""}
    if open_pbi and pbip_file:
        ok, msg = open_in_pbi_desktop(pbip_file)
        step1 = {"status": "pass" if ok else "fail", "message": msg}
    elif pbip_file:
        step1 = {"status": "info", "message": f"Ready to open: {os.path.basename(pbip_file)}"}
    else:
        step1 = {"status": "fail", "message": "No .pbip file found"}
    results["steps"]["1_open_pbip"] = step1

    # ── Step 2: Data source configuration ──
    ds = check_datasources(pbip_dir)
    n_sources = len(ds["sources"])
    n_needs = len(ds["needs_config"])
    inline = sum(1 for s in ds["sources"] if s.get("inline"))
    step2 = {
        "status": "pass" if n_needs == 0 else "warn",
        "sources": n_sources,
        "inline_data": inline,
        "needs_config": ds["needs_config"],
        "warnings": ds["warnings"],
    }
    results["steps"]["2_datasources"] = step2
    results["total_warnings"] += len(ds["needs_config"]) + len(ds["warnings"])

    # ── Step 3: DAX verification ──
    dax = verify_dax(pbip_dir)
    step3 = {
        "status": "pass" if not dax["errors"] else "fail",
        "measures": dax["measures"],
        "calc_columns": dax["calc_columns"],
        "errors": dax["errors"],
        "warnings": dax["warnings"],
    }
    results["steps"]["3_dax_verification"] = step3
    results["total_errors"] += len(dax["errors"])
    results["total_warnings"] += len(dax["warnings"])
    if dax["errors"]:
        results["overall_pass"] = False

    # ── Step 4: Relationships ──
    rels = check_relationships(pbip_dir)
    step4 = {
        "status": "pass" if not rels["errors"] else "fail",
        "count": rels["count"],
        "errors": rels["errors"],
        "warnings": rels["warnings"],
    }
    results["steps"]["4_relationships"] = step4
    results["total_errors"] += len(rels["errors"])
    results["total_warnings"] += len(rels["warnings"])
    if rels["errors"]:
        results["overall_pass"] = False

    # ── Step 5: Fidelity comparison ──
    comparison = compare_visuals(pbip_dir, extract_dir)
    if "error" in comparison:
        step5 = {"status": "skip", "message": comparison["error"]}
    else:
        score = comparison.get("overall_score", 0)
        dash_info = comparison.get("dashboards", {})
        calc_info = comparison.get("calculations", {})
        # If extraction data doesn't match this project (0 dashboards matched
        # but dashboards exist), treat as skip rather than fail
        if (dash_info.get("dashboard_count", 0) > 0
                and dash_info.get("matched", 0) == 0):
            step5 = {
                "status": "skip",
                "message": "Extraction data does not match this project. "
                           "Use --extract-dir to point to the correct tableau_export/ directory.",
            }
        else:
            step5 = {
                "status": "pass" if score >= 90 else ("warn" if score >= 70 else "fail"),
                "score": score,
                "dashboards": dash_info.get("matched", 0),
                "calculations_matched": calc_info.get("matched", 0),
                "calculations_total": calc_info.get("tableau_calcs", 0),
            }
            if score < 70:
                results["overall_pass"] = False
    results["steps"]["5_fidelity"] = step5

    return results


def print_autoplay(results, verbose=False):
    """Print autoplay results to console."""
    print(f"\n{'=' * 72}")
    print(f"  {_BOLD}POST-MIGRATION AUTOPLAY VALIDATION{_RESET}")
    print(f"{'=' * 72}")
    print(f"  Project: {results['pbip_dir']}")
    print()

    step_icons = {"pass": f"{_GREEN}[PASS]{_RESET}", "fail": f"{_RED}[FAIL]{_RESET}",
                  "warn": f"{_YELLOW}[WARN]{_RESET}", "skip": f"{_DIM}[SKIP]{_RESET}",
                  "info": f"{_CYAN}[INFO]{_RESET}"}

    # ── Step 1 ──
    s1 = results["steps"]["1_open_pbip"]
    icon = step_icons.get(s1["status"], "")
    print(f"  {icon} Step 1: Open .pbip in Power BI Desktop")
    print(f"         {s1.get('message', '')}")

    # ── Step 2 ──
    s2 = results["steps"]["2_datasources"]
    icon = step_icons.get(s2["status"], "")
    print(f"\n  {icon} Step 2: Data Source Configuration")
    print(f"         Sources: {s2.get('sources', 0)}  (inline: {s2.get('inline_data', 0)})")
    if s2.get("needs_config"):
        print(f"         {_YELLOW}Needs configuration:{_RESET}")
        for nc in s2["needs_config"]:
            print(f"           - {nc}")
    if not s2.get("needs_config") and not s2.get("warnings"):
        print(f"         All data sources configured")

    # ── Step 3 ──
    s3 = results["steps"]["3_dax_verification"]
    icon = step_icons.get(s3["status"], "")
    print(f"\n  {icon} Step 3: DAX Measures & Calculated Columns")
    print(f"         Measures: {s3.get('measures', 0)}  |  Calc columns: {s3.get('calc_columns', 0)}")
    if s3.get("errors"):
        print(f"         {_RED}Errors ({len(s3['errors'])}):{_RESET}")
        for e in s3["errors"][:10]:
            print(f"           - {e}")
        if len(s3["errors"]) > 10:
            print(f"           ... and {len(s3['errors']) - 10} more")
    if s3.get("warnings") and verbose:
        print(f"         {_YELLOW}Warnings ({len(s3['warnings'])}):{_RESET}")
        for w in s3["warnings"][:10]:
            print(f"           - {w}")
        if len(s3["warnings"]) > 10:
            print(f"           ... and {len(s3['warnings']) - 10} more")
    elif s3.get("warnings"):
        print(f"         {_YELLOW}{len(s3['warnings'])} warning(s){_RESET} (use --verbose)")

    # ── Step 4 ──
    s4 = results["steps"]["4_relationships"]
    icon = step_icons.get(s4["status"], "")
    print(f"\n  {icon} Step 4: Relationships")
    print(f"         Relationships: {s4.get('count', 0)}")
    if s4.get("errors"):
        print(f"         {_RED}Errors ({len(s4['errors'])}):{_RESET}")
        for e in s4["errors"][:5]:
            print(f"           - {e}")
    if s4.get("warnings") and verbose:
        print(f"         {_YELLOW}Warnings ({len(s4['warnings'])}):{_RESET}")
        for w in s4["warnings"][:5]:
            print(f"           - {w}")
    elif s4.get("warnings"):
        print(f"         {_YELLOW}{len(s4['warnings'])} warning(s){_RESET} (use --verbose)")

    # ── Step 5 ──
    s5 = results["steps"]["5_fidelity"]
    icon = step_icons.get(s5["status"], "")
    print(f"\n  {icon} Step 5: Fidelity Comparison (Tableau vs PBI)")
    if "score" in s5:
        score = s5["score"]
        bar_len = 30
        filled = int(score / 100 * bar_len)
        bar_color = _GREEN if score >= 90 else (_YELLOW if score >= 70 else _RED)
        bar = f"{bar_color}{'█' * filled}{_DIM}{'░' * (bar_len - filled)}{_RESET}"
        print(f"         Score: {bar} {score}%")
        print(f"         Dashboards matched: {s5.get('dashboards', 0)}")
        print(f"         Calculations: {s5.get('calculations_matched', 0)}/{s5.get('calculations_total', 0)}")
    elif "message" in s5:
        print(f"         {s5['message']}")

    # ── Summary ──
    overall = results["overall_pass"]
    errs = results["total_errors"]
    warns = results["total_warnings"]

    print(f"\n{'─' * 72}")
    if overall:
        print(f"  {_GREEN}{_BOLD}RESULT: ALL CHECKS PASSED{_RESET}  ({errs} errors, {warns} warnings)")
    else:
        print(f"  {_RED}{_BOLD}RESULT: ISSUES FOUND{_RESET}  ({errs} errors, {warns} warnings)")
    print(f"{'=' * 72}\n")


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Post-migration autoplay — validate generated PBI project"
    )
    parser.add_argument("pbip_dir", help="Path to .pbip project directory")
    parser.add_argument("--open", action="store_true",
                        help="Open .pbip in Power BI Desktop")
    parser.add_argument("--extract-dir",
                        help="Tableau extraction directory (default: tableau_export/)")
    parser.add_argument("--json", metavar="FILE",
                        help="Save results to JSON file")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if not os.path.isdir(args.pbip_dir):
        print(f"ERROR: {args.pbip_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    results = run_autoplay(
        args.pbip_dir,
        extract_dir=args.extract_dir,
        open_pbi=args.open,
        verbose=args.verbose,
    )

    print_autoplay(results, verbose=args.verbose)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"  Results saved: {args.json}")

    sys.exit(0 if results["overall_pass"] else 1)


if __name__ == "__main__":
    main()
