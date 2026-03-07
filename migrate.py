"""
Main script for Tableau to Power BI migration

Pipeline:
1. Extract datasources from the Tableau file (.twb/.twbx)
1b. (Optional) Parse Tableau Prep flow (.tfl/.tflx) and merge transforms
2. Generate the Power BI project (.pbip) with TMDL model
3. Generate migration report with per-item fidelity tracking

Supports:
- Single workbook migration:  python migrate.py workbook.twbx
- Batch migration:            python migrate.py --batch folder/
- Custom output directory:    python migrate.py workbook.twbx --output-dir out/
- Verbose logging:            python migrate.py workbook.twbx --verbose
"""

import os
import sys
import glob
import json
import logging
import argparse
from datetime import datetime

# Ensure Unicode output on Windows consoles (✓, →, ❌, etc.)
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


# ── Structured logging setup ────────────────────────────────────────

logger = logging.getLogger('tableau_to_powerbi')


def setup_logging(verbose=False, log_file=None):
    """Configure structured logging.

    Args:
        verbose: If True, set DEBUG level; otherwise INFO.
        log_file: Optional path to a log file.
    """
    level = logging.DEBUG if verbose else logging.INFO
    fmt = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    datefmt = '%Y-%m-%d %H:%M:%S'

    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        os.makedirs(os.path.dirname(log_file) or '.', exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding='utf-8'))

    logging.basicConfig(level=level, format=fmt, datefmt=datefmt, handlers=handlers)
    # Silence noisy sub-loggers unless verbose
    if not verbose:
        logging.getLogger('tableau_to_powerbi').setLevel(logging.INFO)


# ── Migration statistics tracker ────────────────────────────────────

class MigrationStats:
    """Tracks statistics across all pipeline steps."""

    def __init__(self):
        # Extraction
        self.app_name = ""
        self.datasources = 0
        self.worksheets = 0
        self.dashboards = 0
        self.calculations = 0
        self.parameters = 0
        self.filters = 0
        self.stories = 0
        self.actions = 0
        self.sets = 0
        self.groups = 0
        self.bins = 0
        self.hierarchies = 0
        self.user_filters = 0
        self.custom_sql = 0
        # Generation
        self.tmdl_tables = 0
        self.tmdl_columns = 0
        self.tmdl_measures = 0
        self.tmdl_relationships = 0
        self.tmdl_hierarchies = 0
        self.tmdl_roles = 0
        self.visuals_generated = 0
        self.pages_generated = 0
        self.theme_applied = False
        self.pbip_path = ""
        # Diagnostics
        self.warnings = []
        self.skipped = []

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()}


_stats = MigrationStats()


def print_header(text):
    """Print a formatted header"""
    print()
    print("=" * 80)
    print(text.center(80))
    print("=" * 80)
    print()


def print_step(step_num, total_steps, text):
    """Print a step indicator"""
    print(f"\n[Step {step_num}/{total_steps}] {text}")
    print("-" * 80)


def run_extraction(tableau_file):
    """Run Tableau extraction"""
    global _stats
    print_step(1, 2, "TABLEAU OBJECTS EXTRACTION")

    if not os.path.exists(tableau_file):
        print(f"Error: Tableau file not found: {tableau_file}")
        return False

    print(f"Source file: {tableau_file}")
    _stats.app_name = os.path.splitext(os.path.basename(tableau_file))[0]

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tableau_export'))
    try:
        from extract_tableau_data import TableauExtractor

        extractor = TableauExtractor(tableau_file)
        success = extractor.extract_all()

        if success:
            # Collect extraction counts from saved JSON files
            json_dir = os.path.join(os.path.dirname(__file__), 'tableau_export')
            for attr, fname in [
                ('datasources', 'datasources.json'),
                ('worksheets', 'worksheets.json'),
                ('dashboards', 'dashboards.json'),
                ('calculations', 'calculations.json'),
                ('parameters', 'parameters.json'),
                ('filters', 'filters.json'),
                ('stories', 'stories.json'),
                ('actions', 'actions.json'),
                ('sets', 'sets.json'),
                ('groups', 'groups.json'),
                ('bins', 'bins.json'),
                ('hierarchies', 'hierarchies.json'),
                ('user_filters', 'user_filters.json'),
                ('custom_sql', 'custom_sql.json'),
            ]:
                fpath = os.path.join(json_dir, fname)
                if os.path.exists(fpath):
                    try:
                        with open(fpath, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        setattr(_stats, attr, len(data) if isinstance(data, list) else 0)
                    except Exception:
                        pass

            print("\n✓ Extraction completed successfully")
            return True
        else:
            print("\nError during extraction")
            return False

    except Exception as e:
        print(f"\nError during extraction: {str(e)}")
        return False


def run_generation(report_name=None, output_dir=None, calendar_start=None,
                   calendar_end=None, culture=None):
    """Generate Power BI project (.pbip) from extracted data

    Args:
        report_name: Override report name (defaults to dashboard name or 'Report')
        output_dir: Custom output directory for .pbip projects (default: artifacts/powerbi_projects/)
        calendar_start: Start year for Calendar table (default: 2020)
        calendar_end: End year for Calendar table (default: 2030)
        culture: Override culture/locale for semantic model (e.g., fr-FR)
    """
    global _stats
    print_step(2, 2, "POWER BI PROJECT GENERATION")

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'powerbi_import'))
    try:
        from import_to_powerbi import PowerBIImporter

        importer = PowerBIImporter()
        importer.import_all(generate_pbip=True, report_name=report_name, output_dir=output_dir,
                            calendar_start=calendar_start, calendar_end=calendar_end,
                            culture=culture)

        # Collect generation stats from the output
        base_dir = output_dir or os.path.join('artifacts', 'powerbi_projects')
        project_dir = os.path.join(base_dir, report_name or 'Report')
        if os.path.exists(project_dir):
            _stats.pbip_path = project_dir
            # Count TMDL tables
            tables_dir = None
            for root, dirs, files in os.walk(project_dir):
                if os.path.basename(root) == 'tables':
                    tables_dir = root
                    _stats.tmdl_tables = len([f for f in files if f.endswith('.tmdl')])
                # Count pages and visuals
                if os.path.basename(root) == 'pages':
                    _stats.pages_generated = len([d for d in dirs if d.startswith('ReportSection')])
                if os.path.basename(root) == 'visuals':
                    _stats.visuals_generated += len(dirs)
                # Check for theme
                if 'TableauMigrationTheme.json' in files:
                    _stats.theme_applied = True

            # Read TMDL stats from metadata if available
            meta_path = os.path.join(project_dir, 'migration_metadata.json')
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, 'r', encoding='utf-8') as f:
                        meta = json.load(f)
                    tmdl = meta.get('tmdl_stats', {})
                    _stats.tmdl_columns = tmdl.get('columns', 0)
                    _stats.tmdl_measures = tmdl.get('measures', 0)
                    _stats.tmdl_relationships = tmdl.get('relationships', 0)
                    _stats.tmdl_hierarchies = tmdl.get('hierarchies', 0)
                    _stats.tmdl_roles = tmdl.get('roles', 0)
                except Exception:
                    pass

        print("\n✓ Power BI project generated successfully")
        return True

    except Exception as e:
        print(f"\nError during generation: {str(e)}")
        return False


def run_migration_report(report_name, output_dir=None):
    """Generate a structured migration report with per-item fidelity tracking.

    Reads the extracted JSON files and the generated TMDL files,
    classifies each converted item, and produces a JSON report.

    Args:
        report_name: Name of the report
        output_dir: Custom output directory (default: artifacts/migration_reports/)

    Returns:
        dict or None: Report summary dict, or None on failure
    """
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'powerbi_import'))
    try:
        from migration_report import MigrationReport

        report = MigrationReport(report_name)

        # Load extracted JSON files
        json_dir = os.path.join(os.path.dirname(__file__), 'tableau_export')
        _load = lambda fname: _load_json(os.path.join(json_dir, fname))

        datasources = _load('datasources.json')
        worksheets = _load('worksheets.json')
        calculations = _load('calculations.json')
        parameters = _load('parameters.json')
        stories = _load('stories.json')
        sets = _load('sets.json')
        groups = _load('groups.json')
        bins = _load('bins.json')
        hierarchies = _load('hierarchies.json')
        user_filters = _load('user_filters.json')

        # Add datasources
        if datasources:
            report.add_datasources(datasources)

        # Build calc_map from generated TMDL files to classify calculations
        calc_map = _build_calc_map_from_tmdl(report_name, output_dir)

        # Filter out calculations that are already tracked as groups/bins/sets
        # to avoid double-counting (they appear in both calculations.json and
        # their respective JSON files)
        excluded_calc_names = set()
        for g in (groups or []):
            excluded_calc_names.add(g.get('name', ''))
        for b in (bins or []):
            excluded_calc_names.add(b.get('name', ''))
        for s in (sets or []):
            excluded_calc_names.add(s.get('name', ''))
        filtered_calculations = [
            c for c in (calculations or [])
            if c.get('name', '') not in excluded_calc_names
        ]

        # Add calculations with classification
        if filtered_calculations:
            report.add_calculations(filtered_calculations, calc_map)

        # Add visuals (worksheets)
        if worksheets:
            report.add_visuals(worksheets)

        # Add parameters
        if parameters:
            report.add_parameters(parameters)

        # Add hierarchies
        if hierarchies:
            report.add_hierarchies(hierarchies)

        # Add sets, groups, bins
        if sets:
            report.add_sets(sets)
        if groups:
            report.add_groups(groups)
        if bins:
            report.add_bins(bins)

        # Add stories → bookmarks
        if stories:
            report.add_stories(stories)

        # Add RLS roles
        if user_filters:
            report.add_user_filters(user_filters)

        # Save report
        reports_dir = output_dir or os.path.join('artifacts', 'migration_reports')
        saved_path = report.save(reports_dir)
        logger.info(f"Migration report saved: {saved_path}")

        # Print summary
        report.print_summary()

        return report.get_summary()

    except Exception as e:
        logger.warning(f"Migration report generation failed: {e}")
        return None


def _load_json(filepath):
    """Load a JSON file, returning empty list on failure."""
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _build_calc_map_from_tmdl(report_name, output_dir=None):
    """Scan generated TMDL table files to build a calculation→DAX map.

    Parses 'expression =' lines from .tmdl files in the tables directory.
    Used to classify the fidelity of each DAX formula.

    Returns:
        dict: mapping calculation name → DAX expression
    """
    import re as _re

    calc_map = {}
    base_dir = output_dir or os.path.join('artifacts', 'powerbi_projects')
    tables_dir = os.path.join(base_dir, report_name,
                              f'{report_name}.SemanticModel',
                              'definition', 'tables')

    if not os.path.isdir(tables_dir):
        return calc_map

    # TMDL inline format: measure 'Name' = DAX  or  column 'Name' = DAX
    inline_pattern = _re.compile(r'(?:measure|column)\s+(.+?)\s*=\s*(.*)')
    # Multi-line format: measure 'Name' = ```
    multiline_start = _re.compile(r'(?:measure|column)\s+(.+?)\s*=\s*```\s*$')

    def _strip_quotes(name):
        """Remove surrounding TMDL single-quotes."""
        name = name.strip()
        if name.startswith("'") and name.endswith("'"):
            name = name[1:-1]
        return name

    for tmdl_file in os.listdir(tables_dir):
        if not tmdl_file.endswith('.tmdl'):
            continue
        filepath = os.path.join(tables_dir, tmdl_file)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            i = 0
            while i < len(lines):
                stripped = lines[i].strip()

                # Multi-line expression: measure 'Name' = ```
                m = multiline_start.match(stripped)
                if m:
                    name = _strip_quotes(m.group(1))
                    expr_lines = []
                    i += 1
                    while i < len(lines):
                        l = lines[i].strip()
                        if l == '```':
                            break
                        expr_lines.append(l)
                        i += 1
                    expression = ' '.join(expr_lines).strip()
                    if expression and not expression.startswith('let'):
                        calc_map[name] = expression
                    i += 1
                    continue

                # Inline expression: measure 'Name' = DAX
                m = inline_pattern.match(stripped)
                if m:
                    name = _strip_quotes(m.group(1))
                    expression = m.group(2).strip()
                    if expression and not expression.startswith('let'):
                        calc_map[name] = expression
                i += 1

        except Exception:
            continue

    return calc_map


def run_prep_flow(prep_file, datasources_json='tableau_export/datasources.json'):
    """Parse Tableau Prep flow and merge transforms into extracted datasources.

    Reads the Prep flow (.tfl/.tflx), converts all steps to Power Query M,
    then merges the resulting M queries into the TWB datasources JSON.

    Args:
        prep_file: Path to .tfl or .tflx file
        datasources_json: Path to the extracted datasources.json

    Returns:
        bool: True if successful
    """
    import json as _json

    print_step("1b", 2, "TABLEAU PREP FLOW PARSING")

    if not os.path.exists(prep_file):
        print(f"Error: Prep flow file not found: {prep_file}")
        return False

    print(f"Prep flow: {prep_file}")

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tableau_export'))
    try:
        from prep_flow_parser import parse_prep_flow, merge_prep_with_workbook

        # Parse the Prep flow
        prep_datasources = parse_prep_flow(prep_file)
        print(f"\n  [OK] {len(prep_datasources)} Prep output(s) parsed")

        # Load existing TWB datasources
        if os.path.exists(datasources_json):
            with open(datasources_json, 'r', encoding='utf-8') as f:
                twb_datasources = _json.load(f)
            print(f"  [OK] {len(twb_datasources)} TWB datasource(s) loaded")
        else:
            twb_datasources = []
            print("  [WARN] No TWB datasources found -- using Prep flow only")

        # Merge Prep transforms into TWB datasources
        merged = merge_prep_with_workbook(prep_datasources, twb_datasources)

        # Save merged datasources back
        with open(datasources_json, 'w', encoding='utf-8') as f:
            _json.dump(merged, f, indent=2, ensure_ascii=False)
        print(f"  [OK] {len(merged)} merged datasource(s) saved to {datasources_json}")

        print("\n[OK] Prep flow parsing completed successfully")
        return True

    except Exception as e:
        print(f"\nError during Prep flow parsing: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def run_batch_migration(batch_dir, output_dir=None, prep_file=None, skip_extraction=False,
                        calendar_start=None, calendar_end=None, culture=None):
    """Batch migrate all .twb/.twbx files in a directory.

    Args:
        batch_dir: Directory containing Tableau workbooks
        output_dir: Custom output directory for .pbip projects
        prep_file: Optional Prep flow to merge into each workbook
        skip_extraction: Skip extraction step
        calendar_start: Start year for Calendar table
        calendar_end: End year for Calendar table
        culture: Override culture/locale

    Returns:
        int: 0 if all succeeded, 1 if any failed
    """
    if not os.path.isdir(batch_dir):
        print(f"Error: Batch directory not found: {batch_dir}")
        return 1

    # Find all Tableau workbooks
    patterns = ['*.twb', '*.twbx']
    tableau_files = []
    for pattern in patterns:
        tableau_files.extend(glob.glob(os.path.join(batch_dir, pattern)))

    if not tableau_files:
        print(f"Error: No .twb/.twbx files found in {batch_dir}")
        return 1

    tableau_files.sort()

    print_header("TABLEAU TO POWER BI BATCH MIGRATION")
    print(f"  Directory: {batch_dir}")
    print(f"  Workbooks found: {len(tableau_files)}")
    if output_dir:
        print(f"  Output dir: {output_dir}")
    print()

    batch_start = datetime.now()
    batch_results = {}

    for i, tableau_file in enumerate(tableau_files, 1):
        basename = os.path.splitext(os.path.basename(tableau_file))[0]
        print(f"\n{'=' * 80}")
        print(f"  [{i}/{len(tableau_files)}] Migrating: {basename}")
        print(f"{'=' * 80}")

        global _stats
        _stats = MigrationStats()

        file_results = {}

        # Step 1: Extract
        if not skip_extraction:
            file_results['extraction'] = run_extraction(tableau_file)
            if not file_results['extraction']:
                logger.warning(f"Extraction failed for {basename}, skipping")
                batch_results[basename] = {'success': False, 'error': 'extraction'}
                continue
        else:
            file_results['extraction'] = True

        # Step 1b: Prep flow (optional)
        if prep_file:
            file_results['prep'] = run_prep_flow(prep_file)

        # Step 2: Generate
        file_results['generation'] = run_generation(
            report_name=basename,
            output_dir=output_dir,
            calendar_start=calendar_start,
            calendar_end=calendar_end,
            culture=culture,
        )

        # Step 3: Migration report
        report_summary = None
        if file_results.get('generation'):
            report_summary = run_migration_report(
                report_name=basename,
                output_dir=output_dir,
            )

        all_ok = all(v for v in file_results.values() if v is not None)
        batch_results[basename] = {
            'success': all_ok,
            'stats': _stats.to_dict(),
            'fidelity': report_summary.get('fidelity_score') if report_summary else None,
        }

    # Batch summary
    batch_duration = datetime.now() - batch_start
    succeeded = sum(1 for r in batch_results.values() if r['success'])
    failed = len(batch_results) - succeeded

    print_header("BATCH MIGRATION SUMMARY")
    print(f"  Total workbooks: {len(batch_results)}")
    print(f"  Succeeded:       {succeeded}")
    print(f"  Failed:          {failed}")
    print(f"  Duration:        {batch_duration}")
    print()

    for name, result in batch_results.items():
        status = "[OK]" if result['success'] else "[FAIL]"
        fidelity = result.get('fidelity')
        fid_str = f"  (fidelity: {fidelity}%)" if fidelity is not None else ""
        print(f"  {status} {name}{fid_str}")

    return 0 if failed == 0 else 1


def main():
    """Main entry point"""

    parser = argparse.ArgumentParser(
        description='Migrate a Tableau workbook to a Power BI project (.pbip)'
    )

    parser.add_argument(
        'tableau_file',
        nargs='?',
        default=None,
        help='Path to the Tableau file (.twb or .twbx)'
    )

    parser.add_argument(
        '--prep',
        metavar='PREP_FILE',
        help='Path to a Tableau Prep flow file (.tfl or .tflx) to merge transforms'
    )

    parser.add_argument(
        '--skip-extraction',
        action='store_true',
        help='Skip extraction (use existing datasources.json)'
    )

    parser.add_argument(
        '--skip-conversion',
        action='store_true',
        help='Skip DAX/M conversion step (use existing intermediate files)'
    )

    parser.add_argument(
        '--output-dir',
        metavar='DIR',
        default=None,
        help='Custom output directory for generated .pbip projects (default: artifacts/powerbi_projects/)'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose (DEBUG) logging'
    )

    parser.add_argument(
        '--log-file',
        metavar='FILE',
        default=None,
        help='Write logs to a file in addition to console'
    )

    parser.add_argument(
        '--batch',
        metavar='DIR',
        default=None,
        help='Batch migrate all .twb/.twbx files in the specified directory'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview migration without writing any files (extraction + analysis only)'
    )

    parser.add_argument(
        '--calendar-start',
        metavar='YEAR',
        type=int,
        default=None,
        help='Start year for the auto-generated Calendar table (default: 2020)'
    )

    parser.add_argument(
        '--calendar-end',
        metavar='YEAR',
        type=int,
        default=None,
        help='End year for the auto-generated Calendar table (default: 2030)'
    )

    parser.add_argument(
        '--culture',
        metavar='LOCALE',
        default=None,
        help='Override culture/locale for the semantic model (e.g., fr-FR, de-DE). Default: en-US'
    )

    parser.add_argument(
        '--assess',
        action='store_true',
        help='Run pre-migration assessment and strategy analysis after extraction (no generation)'
    )

    args = parser.parse_args()

    # Setup structured logging
    setup_logging(verbose=args.verbose, log_file=args.log_file)

    # ── Batch migration mode ──────────────────────────────────
    if args.batch:
        return run_batch_migration(
            batch_dir=args.batch,
            output_dir=args.output_dir,
            prep_file=args.prep,
            skip_extraction=args.skip_extraction,
            calendar_start=args.calendar_start,
            calendar_end=args.calendar_end,
            culture=args.culture,
        )

    # ── Single file migration ─────────────────────────────────
    if not args.tableau_file:
        parser.error('tableau_file is required (or use --batch DIR)')

    print_header("TABLEAU TO POWER BI MIGRATION")
    print(f"Source file: {args.tableau_file}")
    if args.prep:
        print(f"Prep flow:   {args.prep}")
    if args.output_dir:
        print(f"Output dir:  {args.output_dir}")
    if args.dry_run:
        print(f"Mode:        DRY RUN (no files will be written)")
    if args.calendar_start or args.calendar_end:
        cal_start = args.calendar_start or 2020
        cal_end = args.calendar_end or 2030
        print(f"Calendar:    {cal_start}–{cal_end}")
    if args.culture:
        print(f"Culture:     {args.culture}")
    print()

    start_time = datetime.now()
    results = {}

    # Step 1: Extraction
    if not args.skip_extraction:
        results['extraction'] = run_extraction(args.tableau_file)
        if not results['extraction']:
            print("\nMigration aborted due to extraction failure")
            return 1
    else:
        print("\nExtraction skipped (using existing datasources.json)")
        results['extraction'] = True

    # Step 1b: Prep flow (optional)
    if args.prep:
        results['prep'] = run_prep_flow(args.prep)
        if not results['prep']:
            print("\n⚠ Prep flow parsing failed — continuing with TWB data only")

    # Step 1c: Assessment (optional)
    if args.assess and results.get('extraction'):
        try:
            from powerbi_import.assessment import run_assessment, print_assessment_report, save_assessment_report
            from powerbi_import.strategy_advisor import recommend_strategy, print_recommendation

            # Load extracted data
            extract_dir = os.path.dirname(args.tableau_file) if args.tableau_file else 'tableau_export'
            extracted = {}
            json_files = ['datasources', 'worksheets', 'dashboards', 'calculations',
                          'parameters', 'filters', 'stories', 'actions', 'sets',
                          'groups', 'bins', 'hierarchies', 'custom_sql', 'user_filters',
                          'sort_orders', 'aliases']
            for jf in json_files:
                fpath = os.path.join('tableau_export', f'{jf}.json')
                if os.path.exists(fpath):
                    with open(fpath, 'r', encoding='utf-8') as f:
                        extracted[jf] = json.load(f)

            # Run assessment
            report = run_assessment(extracted)
            print_assessment_report(report)

            # Save assessment report
            out_dir = args.output_dir or os.path.join('artifacts', 'powerbi_projects')
            os.makedirs(out_dir, exist_ok=True)
            source_basename = os.path.splitext(os.path.basename(args.tableau_file))[0]
            assess_path = os.path.join(out_dir, f'assessment_{source_basename}.json')
            save_assessment_report(report, assess_path)
            print(f"\n  Assessment saved to: {assess_path}")

            # Strategy recommendation
            has_prep = bool(args.prep and results.get('prep'))
            rec = recommend_strategy(extracted, prep_flow=has_prep)
            print_recommendation(rec)

            print("\n✓ Assessment complete (no generation performed)")
            return 0
        except Exception as e:
            logger.error(f"Assessment failed: {e}")
            print(f"\n✗ Assessment failed: {e}")
            return 1

    # Step 2: Generate .pbip project
    # Derive report name from the source filename
    source_basename = os.path.splitext(os.path.basename(args.tableau_file))[0]

    if args.dry_run:
        print("\n[DRY RUN] Skipping generation — would produce:")
        print(f"  Report:  {source_basename}")
        out_dir = args.output_dir or os.path.join('artifacts', 'powerbi_projects')
        print(f"  Output:  {os.path.join(out_dir, source_basename)}")
        results['generation'] = True
    else:
        results['generation'] = run_generation(
            report_name=source_basename,
            output_dir=args.output_dir,
            calendar_start=args.calendar_start,
            calendar_end=args.calendar_end,
            culture=args.culture,
        )

    # Step 3: Migration report
    report_summary = None
    if results.get('generation'):
        report_summary = run_migration_report(
            report_name=source_basename,
            output_dir=args.output_dir,
        )

    # Final report
    duration = datetime.now() - start_time
    print_header("MIGRATION SUMMARY")

    # Step results
    print("  Step Results:")
    for step_name, success in [
        ("Tableau Extraction", results.get('extraction', False)),
        ("Prep Flow Parsing", results.get('prep', None)),
        ("Power BI Generation", results.get('generation', False)),
        ("Migration Report", report_summary is not None if results.get('generation') else None),
    ]:
        if success is None:
            continue  # Step not executed
        status = "✓ Success" if success else "✗ Failed"
        print(f"    {step_name:<30} {status}")

    # Extraction summary
    if results.get('extraction'):
        print(f"\n  Extraction Summary ({_stats.app_name}):")
        extraction_items = [
            ("Datasources", _stats.datasources),
            ("Worksheets", _stats.worksheets),
            ("Dashboards", _stats.dashboards),
            ("Calculations", _stats.calculations),
            ("Parameters", _stats.parameters),
            ("Filters", _stats.filters),
            ("Stories", _stats.stories),
            ("Actions", _stats.actions),
            ("Sets", _stats.sets),
            ("Groups", _stats.groups),
            ("Bins", _stats.bins),
            ("Hierarchies", _stats.hierarchies),
            ("User Filters / RLS", _stats.user_filters),
            ("Custom SQL", _stats.custom_sql),
        ]
        for label, count in extraction_items:
            if count > 0:
                print(f"    {label:<30} {count}")

    # Generation summary
    if results.get('generation'):
        print(f"\n  Generation Summary:")
        gen_items = [
            ("TMDL Tables", _stats.tmdl_tables),
            ("TMDL Columns", _stats.tmdl_columns),
            ("DAX Measures", _stats.tmdl_measures),
            ("Relationships", _stats.tmdl_relationships),
            ("Hierarchies", _stats.tmdl_hierarchies),
            ("RLS Roles", _stats.tmdl_roles),
            ("Report Pages", _stats.pages_generated),
            ("Visuals", _stats.visuals_generated),
        ]
        for label, count in gen_items:
            if count > 0:
                print(f"    {label:<30} {count}")
        if _stats.theme_applied:
            print(f"    {'Custom Theme':<30} ✓ Applied")

    # Fidelity score from migration report
    if report_summary:
        fidelity = report_summary.get('fidelity_score', 0)
        total = report_summary.get('total_items', 0)
        exact = report_summary.get('exact', 0)
        approx = report_summary.get('approximate', 0)
        unsup = report_summary.get('unsupported', 0)
        print(f"\n  Migration Fidelity:")
        print(f"    {'Fidelity Score':<30} {fidelity}%")
        print(f"    {'Exact Conversions':<30} {exact}/{total}")
        if approx:
            print(f"    {'Approximate':<30} {approx}")
        if unsup:
            print(f"    {'Unsupported':<30} {unsup}")

    # Warnings
    if _stats.warnings:
        print(f"\n  Warnings ({len(_stats.warnings)}):")
        for w in _stats.warnings[:10]:
            print(f"    ⚠ {w}")
        if len(_stats.warnings) > 10:
            print(f"    ... and {len(_stats.warnings) - 10} more")

    # Skipped items
    if _stats.skipped:
        print(f"\n  Skipped ({len(_stats.skipped)}):")
        for s in _stats.skipped[:5]:
            print(f"    ⊘ {s}")

    print(f"\n  Duration: {duration}")

    all_success = all(v for v in results.values() if v is not None)

    if all_success:
        print("\n✓ Migration completed successfully!")
        if _stats.pbip_path:
            print(f"\n  Output: {_stats.pbip_path}")
        print("\n  Next steps:")
        print("    1. Open the .pbip file in Power BI Desktop (Developer Mode)")
        print("    2. Configure data sources in Power Query Editor")
        print("    3. Verify DAX measures and calculated columns")
        print("    4. Check relationships in the Model view")
        print("    5. Compare visuals with the original Tableau workbook")
    else:
        print("\n✗ Migration completed with errors")

    return 0 if all_success else 1


if __name__ == '__main__':
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nMigration interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nFatal error: {str(e)}")
        sys.exit(1)
