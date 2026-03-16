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
import tempfile
import concurrent.futures
from datetime import datetime
from enum import IntEnum


# ── Structured exit codes ────────────────────────────────────────────

class ExitCode(IntEnum):
    """Structured exit codes for CI/CD integration."""
    SUCCESS = 0
    GENERAL_ERROR = 1
    FILE_NOT_FOUND = 2
    EXTRACTION_FAILED = 3
    GENERATION_FAILED = 4
    VALIDATION_FAILED = 5
    ASSESSMENT_FAILED = 6
    BATCH_PARTIAL_FAIL = 7
    KEYBOARD_INTERRUPT = 130

# Ensure Unicode output on Windows consoles (✓, →, ❌, etc.)
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        pass


# ── Structured logging setup ────────────────────────────────────────

logger = logging.getLogger('tableau_to_powerbi')


def setup_logging(verbose=False, log_file=None, quiet=False):
    """Configure structured logging.

    Args:
        verbose: If True, set DEBUG level; otherwise INFO.
        log_file: Optional path to a log file.
        quiet: If True, suppress all output except ERROR level.
    """
    if quiet:
        level = logging.ERROR
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO
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
        logger.error(f"Tableau file not found: {tableau_file}")
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
                    except (json.JSONDecodeError, OSError) as e:
                        logger.debug("Could not load stats from %s: %s", fname, e)

            print("\n✓ Extraction completed successfully")
            return True
        else:
            print("\nError during extraction")
            return False

    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)
        print(f"\nError during extraction: {str(e)}")
        return False


def run_generation(report_name=None, output_dir=None, calendar_start=None,
                   calendar_end=None, culture=None, model_mode='import',
                   output_format='pbip', paginated=False, languages=None):
    """Generate Power BI project (.pbip) from extracted data

    Args:
        report_name: Override report name (defaults to dashboard name or 'Report')
        output_dir: Custom output directory for .pbip projects (default: artifacts/powerbi_projects/)
        calendar_start: Start year for Calendar table (default: 2020)
        calendar_end: End year for Calendar table (default: 2030)
        culture: Override culture/locale for semantic model (e.g., fr-FR)
        paginated: If True, generate paginated report layout alongside interactive report
        languages: Comma-separated additional locales (e.g. 'fr-FR,de-DE')
    """
    global _stats
    print_step(2, 2, "POWER BI PROJECT GENERATION")

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'powerbi_import'))
    try:
        from import_to_powerbi import PowerBIImporter

        importer = PowerBIImporter()
        importer.import_all(generate_pbip=True, report_name=report_name, output_dir=output_dir,
                            calendar_start=calendar_start, calendar_end=calendar_end,
                            culture=culture, model_mode=model_mode,
                            output_format=output_format, languages=languages)

        # Collect generation stats from the output
        base_dir = output_dir or os.path.join('artifacts', 'powerbi_projects', 'migrated')
        project_dir = os.path.join(base_dir, report_name or 'Report')
        if os.path.exists(project_dir):
            _stats.pbip_path = project_dir
            # Count TMDL tables
            tables_dir = None
            for root, dirs, files in os.walk(project_dir):
                if os.path.basename(root) == 'tables':
                    tables_dir = root
                    _stats.tmdl_tables = len([f for f in files if f.endswith('.tmdl')])
                # Count pages: only ReportSection dirs that contain page.json
                if os.path.basename(root) == 'pages':
                    _stats.pages_generated = sum(
                        1 for d in dirs if d.startswith('ReportSection')
                        and os.path.isfile(os.path.join(root, d, 'page.json'))
                    )
                # Count visuals: only UUID dirs that contain visual.json
                if os.path.basename(root) == 'visuals':
                    _stats.visuals_generated += sum(
                        1 for d in dirs
                        if os.path.isfile(os.path.join(root, d, 'visual.json'))
                    )
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
                except (json.JSONDecodeError, OSError, KeyError) as e:
                    logger.debug("Could not load TMDL stats: %s", e)

        print("\n✓ Power BI project generated successfully")
        return True

    except Exception as e:
        logger.error(f"Generation failed: {e}", exc_info=True)
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

        # Add datasources (also builds source→target table mapping)
        if datasources:
            report.add_datasources(datasources)

        # Update table mapping with actual TMDL target table names
        base_dir = output_dir or os.path.join('artifacts', 'powerbi_projects', 'migrated')
        tables_dir = os.path.join(base_dir, report_name,
                                  f'{report_name}.SemanticModel',
                                  'definition', 'tables')
        if os.path.isdir(tables_dir):
            tmdl_tables = set()
            for tmdl_file in os.listdir(tables_dir):
                if tmdl_file.endswith('.tmdl'):
                    # Table name = file name without .tmdl extension
                    tmdl_tables.add(tmdl_file[:-5])
            report.add_table_mapping_from_tmdl(tmdl_tables)

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
        reports_dir = output_dir or os.path.join('artifacts', 'powerbi_projects', 'reports')
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
    except (json.JSONDecodeError, OSError) as e:
        logger.debug("Could not load JSON %s: %s", filepath, e)
    return []


def run_html_dashboard(report_name, output_dir):
    """Generate an HTML migration dashboard for a completed migration.

    Args:
        report_name: Name of the migrated report.
        output_dir: Directory containing the .pbip project and report JSON.

    Returns:
        str or None: Path to the generated HTML file.
    """
    try:
        from generate_report import generate_dashboard
        html_path = generate_dashboard(report_name, output_dir)
        if html_path:
            print(f"\n📊 HTML dashboard: {html_path}")
        return html_path
    except (ImportError, OSError, ValueError) as e:
        logger.warning(f"HTML dashboard generation failed: {e}")
        return None


def run_batch_html_dashboard(output_dir, workbook_results):
    """Generate a consolidated HTML dashboard for a batch migration.

    Args:
        output_dir: Root output directory.
        workbook_results: dict mapping workbook name → paths dict.

    Returns:
        str or None: Path to the generated HTML file.
    """
    try:
        from generate_report import generate_batch_dashboard
        html_path = generate_batch_dashboard(output_dir, workbook_results)
        if html_path:
            print(f"\n📊 Batch HTML dashboard: {html_path}")
        return html_path
    except (ImportError, OSError, ValueError) as e:
        logger.warning(f"Batch HTML dashboard generation failed: {e}")
        return None


def run_consolidate_reports(directory):
    """Scan a directory tree for existing migration reports and metadata,
    then generate a single consolidated MIGRATION_DASHBOARD.html.

    This allows producing a unified report after running multiple individual
    migrations (e.g., one per subfolder) without re-running the migrations.

    The function searches recursively for:
    - ``migration_report_*.json`` files (per-workbook migration reports)
    - ``migration_metadata.json`` files (per-workbook metadata)

    Args:
        directory: Root directory to scan for existing migration artifacts.

    Returns:
        int: 0 on success, 1 on failure.
    """
    directory = os.path.abspath(directory)
    if not os.path.isdir(directory):
        print(f"Error: Directory not found: {directory}")
        return 1

    print_header("CONSOLIDATE MIGRATION REPORTS")
    print(f"  Scanning: {directory}")
    print()

    # Discover migration report JSON files
    report_files = []
    metadata_files = []
    for root, _dirs, files in os.walk(directory):
        for f in files:
            full = os.path.join(root, f)
            if f.startswith('migration_report_') and f.endswith('.json'):
                report_files.append(full)
            elif f == 'migration_metadata.json':
                metadata_files.append(full)

    if not report_files and not metadata_files:
        print("  No migration reports or metadata found.")
        print("  Run migrations first, then consolidate.")
        return 1

    # Build workbook_results dict: name → {migration_report_path, metadata_path}
    # Group by workbook name, keeping the latest report per name
    workbook_results = {}

    for rp in sorted(report_files):
        try:
            with open(rp, encoding='utf-8') as fh:
                data = json.load(fh)
            name = data.get('report_name', '')
            if not name:
                continue
            if name not in workbook_results:
                workbook_results[name] = {}
            # Keep the latest report (sorted → last wins)
            workbook_results[name]['migration_report_path'] = rp
        except (json.JSONDecodeError, OSError) as e:
            logger.debug("Skipping unreadable report %s: %s", rp, e)
            continue

    for mp in metadata_files:
        # metadata lives inside <output_dir>/<report_name>/migration_metadata.json
        parent = os.path.basename(os.path.dirname(mp))
        if parent not in workbook_results:
            workbook_results[parent] = {}
        workbook_results[parent]['metadata_path'] = mp

    if not workbook_results:
        print("  No valid migration data found.")
        return 1

    print(f"  Found {len(workbook_results)} workbook(s):")
    for name in sorted(workbook_results):
        has_report = 'migration_report_path' in workbook_results[name]
        has_meta = 'metadata_path' in workbook_results[name]
        flags = []
        if has_report:
            flags.append('report')
        if has_meta:
            flags.append('metadata')
        print(f"    - {name} ({', '.join(flags)})")
    print()

    # Generate consolidated dashboard
    html_path = run_batch_html_dashboard(directory, workbook_results)
    if html_path:
        print(f"\n  Consolidated report: {html_path}")
        return 0
    else:
        print("  Failed to generate consolidated dashboard.")
        return 1


def _build_calc_map_from_tmdl(report_name, output_dir=None):
    """Scan generated TMDL table files to build a calculation→DAX map.

    Parses 'expression =' lines from .tmdl files in the tables directory.
    Used to classify the fidelity of each DAX formula.

    Returns:
        dict: mapping calculation name → DAX expression
    """
    import re as _re

    calc_map = {}
    base_dir = output_dir or os.path.join('artifacts', 'powerbi_projects', 'migrated')
    tables_dir = os.path.join(base_dir, report_name,
                              f'{report_name}.SemanticModel',
                              'definition', 'tables')

    if not os.path.isdir(tables_dir):
        return calc_map

    # TMDL inline format: measure 'Name' = DAX  or  column 'Name' = DAX
    inline_pattern = _re.compile(r'(?:measure|column)\s+(.+?)\s*=\s*(.*)')
    # Multi-line format: measure 'Name' = ```
    multiline_start = _re.compile(r'(?:measure|column)\s+(.+?)\s*=\s*```\s*$')
    # Column declaration without expression (M-based calculated columns)
    col_only_pattern = _re.compile(r'^\s+column\s+(.+?)\s*$')
    # Table.AddColumn step in M partition
    m_add_col_pattern = _re.compile(r'Table\.AddColumn\([^,]+,\s*"([^"]+)"')

    def _strip_quotes(name):
        """Remove surrounding TMDL single-quotes and unescape doubled quotes."""
        name = name.strip()
        if name.startswith("'") and name.endswith("'"):
            name = name[1:-1]
        # TMDL escapes apostrophes as '' — unescape to match extraction names
        name = name.replace("''", "'")
        return name

    for tmdl_file in os.listdir(tables_dir):
        if not tmdl_file.endswith('.tmdl'):
            continue
        filepath = os.path.join(tables_dir, tmdl_file)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # Collect M-based column names from Table.AddColumn steps in partitions
            m_based_columns = set()
            for line in lines:
                m_add = m_add_col_pattern.search(line)
                if m_add:
                    m_based_columns.add(m_add.group(1))

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
                    continue

                # M-based calculated column: column 'Name' (no = sign)
                # These are generated as Table.AddColumn in the M partition
                m = col_only_pattern.match(lines[i])
                if m:
                    name = _strip_quotes(m.group(1))
                    if name not in calc_map and name in m_based_columns:
                        calc_map[name] = '[M-based column]'

                i += 1

        except (OSError, UnicodeDecodeError) as e:
            logger.debug("Could not read TMDL file: %s", e)
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

    except (ImportError, OSError, json.JSONDecodeError) as e:
        logger.error("Prep flow parsing failed: %s", e, exc_info=True)
        print(f"\nError during Prep flow parsing: {str(e)}")
        return False


def _run_batch_config(args):
    """Run migrations using a JSON batch configuration file.

    The config file is a JSON array of objects, each specifying a
    workbook to migrate with optional per-workbook overrides::

        [
          {"file": "sales.twbx", "culture": "fr-FR", "paginated": true},
          {"file": "finance.twb", "prep": "flow.tfl", "calendar_start": 2018}
        ]

    Supported keys per entry:
        file (required), prep, output_dir, culture, calendar_start,
        calendar_end, mode, paginated, skip_extraction
    """
    config_path = args.batch_config
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            entries = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Error: Cannot load batch config: {exc}")
        return ExitCode.GENERAL_ERROR

    if not isinstance(entries, list):
        print("Error: Batch config must be a JSON array of objects")
        return ExitCode.GENERAL_ERROR

    config_dir = os.path.dirname(os.path.abspath(config_path))

    print_header("TABLEAU TO POWER BI BATCH-CONFIG MIGRATION")
    print(f"  Config file:  {config_path}")
    print(f"  Entries:      {len(entries)}")
    print()

    global _stats
    batch_start = datetime.now()
    results = {}

    for i, entry in enumerate(entries, 1):
        raw_file = entry.get('file', '')
        if not raw_file:
            print(f"  [{i}/{len(entries)}] SKIP — missing 'file' key")
            continue

        # Resolve relative paths against config file location
        tableau_file = raw_file if os.path.isabs(raw_file) else os.path.join(config_dir, raw_file)
        if not os.path.isfile(tableau_file):
            print(f"  [{i}/{len(entries)}] SKIP — file not found: {raw_file}")
            results[raw_file] = {'success': False, 'error': 'file_not_found'}
            continue

        basename = os.path.splitext(os.path.basename(tableau_file))[0]
        print(f"\n{'=' * 80}")
        print(f"  [{i}/{len(entries)}] Migrating: {basename}")
        print(f"{'=' * 80}")

        _stats = MigrationStats()

        # Per-entry overrides (fall back to CLI args)
        skip = entry.get('skip_extraction', args.skip_extraction)
        prep = entry.get('prep', args.prep)
        out_dir = entry.get('output_dir', args.output_dir)
        cal_start = entry.get('calendar_start', args.calendar_start)
        cal_end = entry.get('calendar_end', args.calendar_end)
        culture = entry.get('culture', args.culture)
        paginated = entry.get('paginated', getattr(args, 'paginated', False))

        file_results = {}

        # Extract
        if not skip:
            file_results['extraction'] = run_extraction(tableau_file)
            if not file_results['extraction']:
                results[basename] = {'success': False, 'error': 'extraction'}
                continue
        else:
            file_results['extraction'] = True

        # Prep flow
        if prep:
            ppath = prep if os.path.isabs(prep) else os.path.join(config_dir, prep)
            file_results['prep'] = run_prep_flow(ppath)

        # Generate
        file_results['generation'] = run_generation(
            report_name=basename,
            output_dir=out_dir,
            calendar_start=cal_start,
            calendar_end=cal_end,
            culture=culture,
            paginated=paginated,
        )

        # Migration report
        report_summary = None
        if file_results.get('generation'):
            report_summary = run_migration_report(report_name=basename, output_dir=out_dir)

        all_ok = all(v for v in file_results.values() if v is not None)
        dashboard_dir = out_dir or os.path.join('artifacts', 'powerbi_projects', 'migrated')
        results[basename] = {
            'success': all_ok,
            'stats': _stats.to_dict(),
            'fidelity': report_summary.get('fidelity_score') if report_summary else None,
            'metadata_path': os.path.join(dashboard_dir, basename, 'migration_metadata.json'),
        }

    # Summary
    batch_duration = datetime.now() - batch_start
    succeeded = sum(1 for r in results.values() if r.get('success'))
    failed = len(results) - succeeded

    # Consolidated batch HTML dashboard
    effective_output = args.output_dir or os.path.join('artifacts', 'powerbi_projects', 'migrated')
    wb_paths = {}
    for name, res in results.items():
        if res.get('success'):
            wb_paths[name] = {
                'metadata_path': res.get('metadata_path'),
            }
            pattern = os.path.join(effective_output, f'migration_report_{name}_*.json')
            candidates = sorted(glob.glob(pattern))
            if candidates:
                wb_paths[name]['migration_report_path'] = candidates[-1]
    if wb_paths:
        run_batch_html_dashboard(effective_output, wb_paths)

    print_header("BATCH-CONFIG MIGRATION SUMMARY")
    print(f"  Total entries: {len(results)}")
    print(f"  Succeeded:     {succeeded}")
    print(f"  Failed:        {failed}")
    print(f"  Duration:      {batch_duration}")
    print()
    for name, res in results.items():
        status = "[OK]" if res.get('success') else "[FAIL]"
        fid = res.get('fidelity')
        fid_str = f"  (fidelity: {fid}%)" if fid is not None else ""
        print(f"  {status} {name}{fid_str}")

    return ExitCode.SUCCESS if failed == 0 else ExitCode.BATCH_PARTIAL_FAIL


def _migrate_single_workbook(tableau_file, basename, workbook_output_dir, display_name,
                             skip_extraction, wb_prep, wb_cal_start, wb_cal_end, wb_culture):
    """Migrate a single workbook — used by both sequential and parallel batch modes.

    Returns:
        dict: Result dict with success, stats, fidelity, report_name, output_dir, metadata_path
    """
    global _stats
    _stats = MigrationStats()

    file_results = {}

    # Step 1: Extract
    if not skip_extraction:
        file_results['extraction'] = run_extraction(tableau_file)
        if not file_results['extraction']:
            logger.warning("Extraction failed for %s, skipping", display_name)
            return {'success': False, 'error': 'extraction', 'report_name': basename,
                    'output_dir': workbook_output_dir,
                    'metadata_path': os.path.join(workbook_output_dir, basename, 'migration_metadata.json')}
    else:
        file_results['extraction'] = True

    # Step 1b: Prep flow (optional)
    if wb_prep:
        file_results['prep'] = run_prep_flow(wb_prep)

    # Step 2: Generate
    file_results['generation'] = run_generation(
        report_name=basename,
        output_dir=workbook_output_dir,
        calendar_start=wb_cal_start,
        calendar_end=wb_cal_end,
        culture=wb_culture,
    )

    # Step 3: Migration report
    report_summary = None
    if file_results.get('generation'):
        report_summary = run_migration_report(
            report_name=basename,
            output_dir=workbook_output_dir,
        )

    all_ok = all(v for v in file_results.values() if v is not None)
    return {
        'success': all_ok,
        'stats': _stats.to_dict(),
        'fidelity': report_summary.get('fidelity_score') if report_summary else None,
        'report_name': basename,
        'output_dir': workbook_output_dir,
        'metadata_path': os.path.join(workbook_output_dir, basename, 'migration_metadata.json'),
    }


def run_batch_migration(batch_dir, output_dir=None, prep_file=None, skip_extraction=False,
                        calendar_start=None, calendar_end=None, culture=None,
                        parallel=None, resume=False, jsonl_log=None, manifest=None):
    """Batch migrate all .twb/.twbx files in a directory (recursive).

    Searches the directory tree recursively for Tableau workbooks and
    preserves the relative subfolder structure in the output.  A single
    consolidated HTML migration dashboard is generated at the root of
    the output directory.

    Args:
        batch_dir: Root directory containing Tableau workbooks (searched recursively)
        output_dir: Custom output directory for .pbip projects.
            A ``migrated/`` subfolder is created inside it.
            Defaults to ``<batch_dir>/migrated``.
        prep_file: Optional Prep flow to merge into each workbook
        skip_extraction: Skip extraction step
        calendar_start: Start year for Calendar table
        calendar_end: End year for Calendar table
        culture: Override culture/locale
        parallel: Number of parallel workers (None = sequential)
        resume: Skip workbooks with existing .pbip output
        jsonl_log: Path to write structured JSONL migration events
        manifest: List of manifest entries [{file, culture, calendar_start, ...}] for per-workbook config

    Returns:
        int: 0 if all succeeded, 1 if any failed
    """
    if not os.path.isdir(batch_dir):
        print(f"Error: Batch directory not found: {batch_dir}")
        return 1

    batch_dir = os.path.abspath(batch_dir)

    # Find all Tableau workbooks recursively
    tableau_files = []
    for root, _dirs, files in os.walk(batch_dir):
        for f in files:
            if f.lower().endswith(('.twb', '.twbx')) and not f.startswith('~'):
                tableau_files.append(os.path.join(root, f))

    if not tableau_files:
        print(f"Error: No .twb/.twbx files found in {batch_dir}")
        return 1

    tableau_files.sort()

    # Output root: honour --output-dir or default to <batch_dir>/migrated
    migrated_root = output_dir if output_dir else os.path.join(batch_dir, 'migrated')
    os.makedirs(migrated_root, exist_ok=True)

    print_header("TABLEAU TO POWER BI BATCH MIGRATION")
    print(f"  Source:     {batch_dir}")
    print(f"  Workbooks:  {len(tableau_files)}")
    print(f"  Output:     {migrated_root}")
    if parallel:
        print(f"  Parallel:   {parallel} workers")
    if resume:
        print(f"  Resume:     enabled (skip completed)")
    if jsonl_log:
        print(f"  JSONL log:  {jsonl_log}")
    print()

    # ── JSONL structured logging ──────────────────────────────
    jsonl_fh = None
    if jsonl_log:
        jsonl_fh = open(jsonl_log, 'a', encoding='utf-8')

    def _write_jsonl(event_type, data):
        """Append a structured event to the JSONL log file."""
        if jsonl_fh is None:
            return
        import json as _json
        record = {
            'timestamp': datetime.now().isoformat(),
            'event': event_type,
            **data,
        }
        jsonl_fh.write(_json.dumps(record, default=str) + '\n')
        jsonl_fh.flush()

    _write_jsonl('batch_start', {
        'source_dir': batch_dir,
        'workbook_count': len(tableau_files),
        'output_dir': migrated_root,
        'parallel': parallel,
        'resume': resume,
    })

    # ── Resume: filter out completed workbooks ────────────────
    if resume:
        original_count = len(tableau_files)
        filtered = []
        for twb in tableau_files:
            bn = os.path.splitext(os.path.basename(twb))[0]
            rel = os.path.relpath(os.path.dirname(twb), batch_dir)
            out_base = os.path.join(migrated_root, rel) if rel != '.' else migrated_root
            pbip_path = os.path.join(out_base, bn, f'{bn}.pbip')
            if os.path.exists(pbip_path):
                logger.info("Resume: skipping already-completed %s", bn)
                _write_jsonl('resume_skip', {'workbook': bn, 'pbip_path': pbip_path})
            else:
                filtered.append(twb)
        tableau_files = filtered
        skipped = original_count - len(tableau_files)
        if skipped:
            print(f"  Resume: skipped {skipped} already-completed workbook(s)")
        if not tableau_files:
            print("  All workbooks already completed — nothing to do.")
            if jsonl_fh:
                _write_jsonl('batch_end', {'status': 'all_completed', 'skipped': skipped})
                jsonl_fh.close()
            return ExitCode.SUCCESS

    batch_start = datetime.now()
    batch_results = {}

    # ── Manifest: per-workbook config overrides ───────────────
    manifest_lookup = {}
    if manifest:
        for entry in manifest:
            key = os.path.normpath(entry.get('file', ''))
            manifest_lookup[key] = entry

    # ── Pre-compute workbook tasks ──────────────────────────────
    tasks = []
    for i, tableau_file in enumerate(tableau_files, 1):
        basename = os.path.splitext(os.path.basename(tableau_file))[0]
        rel_dir = os.path.relpath(os.path.dirname(tableau_file), batch_dir)
        workbook_output_dir = os.path.join(migrated_root, rel_dir) if rel_dir != '.' else migrated_root
        os.makedirs(workbook_output_dir, exist_ok=True)
        display_name = os.path.join(rel_dir, basename) if rel_dir != '.' else basename

        # Per-workbook config from manifest (if provided)
        wb_culture = culture
        wb_cal_start = calendar_start
        wb_cal_end = calendar_end
        wb_prep = prep_file
        if manifest_lookup:
            rel_path = os.path.relpath(tableau_file, batch_dir)
            m_entry = manifest_lookup.get(os.path.normpath(rel_path), {})
            if not m_entry:
                m_entry = manifest_lookup.get(os.path.normpath(os.path.basename(tableau_file)), {})
            wb_culture = m_entry.get('culture', wb_culture)
            wb_cal_start = m_entry.get('calendar_start', wb_cal_start)
            wb_cal_end = m_entry.get('calendar_end', wb_cal_end)
            wb_prep = m_entry.get('prep', wb_prep)

        tasks.append({
            'index': i,
            'tableau_file': tableau_file,
            'basename': basename,
            'workbook_output_dir': workbook_output_dir,
            'display_name': display_name,
            'skip_extraction': skip_extraction,
            'wb_prep': wb_prep,
            'wb_cal_start': wb_cal_start,
            'wb_cal_end': wb_cal_end,
            'wb_culture': wb_culture,
        })

    def _run_task(task):
        """Execute a single workbook migration task."""
        print(f"\n{'=' * 80}")
        print(f"  [{task['index']}/{len(tasks)}] Migrating: {task['display_name']}")
        print(f"{'=' * 80}")

        wb_start_time = datetime.now()
        _write_jsonl('workbook_start', {
            'workbook': task['display_name'],
            'index': task['index'],
            'total': len(tasks),
        })

        wb_result = _migrate_single_workbook(
            tableau_file=task['tableau_file'],
            basename=task['basename'],
            workbook_output_dir=task['workbook_output_dir'],
            display_name=task['display_name'],
            skip_extraction=task['skip_extraction'],
            wb_prep=task['wb_prep'],
            wb_cal_start=task['wb_cal_start'],
            wb_cal_end=task['wb_cal_end'],
            wb_culture=task['wb_culture'],
        )

        wb_duration = (datetime.now() - wb_start_time).total_seconds()
        _write_jsonl('workbook_end', {
            'workbook': task['display_name'],
            'success': wb_result.get('success', False),
            'duration_sec': wb_duration,
            'fidelity': wb_result.get('fidelity'),
            'stats': wb_result.get('stats', {}),
        })
        return task['display_name'], wb_result

    # ── Execute tasks (sequential or parallel) ────────────────
    if parallel and parallel > 1 and len(tasks) > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = {executor.submit(_run_task, t): t for t in tasks}
            for future in concurrent.futures.as_completed(futures):
                try:
                    display_name, wb_result = future.result()
                    batch_results[display_name] = wb_result
                except Exception:
                    task = futures[future]
                    batch_results[task['display_name']] = {'success': False, 'error': 'parallel_exception'}
                    logger.exception("Parallel migration failed for %s", task['display_name'])
    else:
        for task in tasks:
            display_name, wb_result = _run_task(task)
            batch_results[display_name] = wb_result

    # Batch summary
    batch_duration = datetime.now() - batch_start
    succeeded = sum(1 for r in batch_results.values() if r['success'])
    failed = len(batch_results) - succeeded

    # Single consolidated HTML dashboard at root output level
    wb_paths = {}
    for display_name, res in batch_results.items():
        if res.get('success'):
            name = res.get('report_name', display_name)
            out = res.get('output_dir', migrated_root)
            wb_paths[name] = {
                'metadata_path': res.get('metadata_path'),
            }
            # Auto-discover migration report JSON in the workbook's output dir
            pattern = os.path.join(out, f'migration_report_{name}_*.json')
            candidates = sorted(glob.glob(pattern))
            if candidates:
                wb_paths[name]['migration_report_path'] = candidates[-1]
    if wb_paths:
        run_batch_html_dashboard(migrated_root, wb_paths)

    print_header("BATCH MIGRATION SUMMARY")
    print(f"  Total workbooks: {len(batch_results)}")
    print(f"  Succeeded:       {succeeded}")
    print(f"  Failed:          {failed}")
    print(f"  Duration:        {batch_duration}")
    print()

    # Formatted summary table
    name_width = max((len(n) for n in batch_results), default=20)
    name_width = max(name_width, 20)
    header = f"  {'Workbook':<{name_width}}  {'Status':>8}  {'Fidelity':>9}  {'Tables':>7}  {'Visuals':>8}"
    print(header)
    print(f"  {'-' * name_width}  {'--------':>8}  {'---------':>9}  {'-------':>7}  {'--------':>8}")
    for name, result in batch_results.items():
        status = "OK" if result['success'] else "FAIL"
        fidelity = result.get('fidelity')
        fid_str = f"{fidelity}%" if fidelity is not None else "—"
        stats = result.get('stats', {})
        tables = stats.get('tmdl_tables', '—')
        visuals = stats.get('visuals_generated', '—')
        print(f"  {name:<{name_width}}  {status:>8}  {fid_str:>9}  {str(tables):>7}  {str(visuals):>8}")
    print()

    # Aggregate stats
    fidelities = [r['fidelity'] for r in batch_results.values() if r.get('fidelity') is not None]
    if fidelities:
        avg_fid = round(sum(fidelities) / len(fidelities), 1)
        min_fid = min(fidelities)
        max_fid = max(fidelities)
        print(f"  Fidelity: avg {avg_fid}% | min {min_fid}% | max {max_fid}%")

    # ── Close JSONL log ────────────────────────────────────
    _write_jsonl('batch_end', {
        'total': len(batch_results),
        'succeeded': succeeded,
        'failed': failed,
        'duration_sec': batch_duration.total_seconds(),
        'avg_fidelity': round(sum(fidelities) / len(fidelities), 1) if fidelities else None,
    })
    if jsonl_fh:
        jsonl_fh.close()

    return ExitCode.SUCCESS if failed == 0 else ExitCode.BATCH_PARTIAL_FAIL


# ── Argument parser ──────────────────────────────────────────────────────────

def _build_argument_parser():
    """Build and return the CLI argument parser."""
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
        '--wizard',
        action='store_true',
        default=False,
        help='Launch the interactive migration wizard (guided step-by-step prompts)'
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
        '--quiet', '-q',
        action='store_true',
        help='Suppress all output except errors (useful for scripted/CI usage)'
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
        '--consolidate',
        metavar='DIR',
        default=None,
        help=(
            'Scan a directory tree for existing migration reports and metadata, '
            'then generate a single consolidated MIGRATION_DASHBOARD.html. '
            'Use this after running multiple individual migrations to produce '
            'one unified report covering all workbooks.'
        )
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
        '--languages',
        metavar='LOCALES',
        default=None,
        help='Comma-separated additional locales for multi-language TMDL cultures (e.g., fr-FR,de-DE,es-ES)'
    )

    parser.add_argument(
        '--goals',
        action='store_true',
        default=False,
        help='Generate PBI Goals/Scorecard JSON from Tableau Pulse metrics (requires Fabric workspace for deployment)'
    )

    parser.add_argument(
        '--assess',
        action='store_true',
        help='Run pre-migration assessment and strategy analysis after extraction (no generation)'
    )

    parser.add_argument(
        '--mode',
        choices=['import', 'directquery', 'composite'],
        default='import',
        help='Semantic model mode: import (default), directquery, or composite'
    )

    parser.add_argument(
        '--rollback',
        action='store_true',
        help='Backup existing .pbip project before overwriting'
    )

    parser.add_argument(
        '--output-format',
        choices=['pbip', 'tmdl', 'pbir'],
        default='pbip',
        help='Output format: pbip (default, full project), tmdl (semantic model only), pbir (report only)'
    )

    parser.add_argument(
        '--config',
        metavar='FILE',
        default=None,
        help='Path to a JSON configuration file (CLI args override config file values)'
    )

    parser.add_argument(
        '--incremental',
        metavar='DIR',
        default=None,
        help='Path to an existing .pbip project — merge changes incrementally, preserving manual edits'
    )

    parser.add_argument(
        '--compare',
        action='store_true',
        default=False,
        help='Generate an HTML side-by-side comparison report (Tableau vs. Power BI)'
    )

    parser.add_argument(
        '--dashboard',
        action='store_true',
        default=False,
        help='Generate an HTML telemetry dashboard (aggregated migration statistics)'
    )

    parser.add_argument(
        '--telemetry',
        action='store_true',
        default=False,
        help='Enable anonymous usage telemetry (opt-in, no PII collected)'
    )

    parser.add_argument(
        '--paginated',
        action='store_true',
        default=False,
        help='Generate a paginated report layout alongside the interactive report'
    )

    parser.add_argument(
        '--batch-config',
        metavar='FILE',
        default=None,
        help=(
            'Path to a JSON batch configuration file.  The file should '
            'contain a list of objects, each with at least a "file" key '
            'and optional per-workbook overrides (prep, culture, '
            'calendar_start, calendar_end, mode, paginated, output_dir).  '
            'Example: [{"file": "sales.twbx", "culture": "fr-FR"}]'
        )
    )

    parser.add_argument(
        '--deploy',
        metavar='WORKSPACE_ID',
        default=None,
        help=(
            'Deploy the generated .pbip project to a Power BI Service workspace. '
            'Requires PBI_TENANT_ID, PBI_CLIENT_ID, PBI_CLIENT_SECRET env vars '
            '(or PBI_ACCESS_TOKEN). Pass the target workspace/group ID.'
        )
    )

    parser.add_argument(
        '--deploy-refresh',
        action='store_true',
        default=False,
        help='Trigger a dataset refresh after deploying to Power BI Service (requires --deploy)'
    )

    # ── Tableau Server extraction arguments ───────────────────
    parser.add_argument(
        '--server',
        metavar='URL',
        default=None,
        help='Tableau Server/Cloud URL (e.g., https://tableau.company.com)'
    )

    parser.add_argument(
        '--site',
        metavar='SITE_ID',
        default='',
        help='Tableau site content URL (empty for Default site)'
    )

    parser.add_argument(
        '--workbook',
        metavar='NAME_OR_ID',
        default=None,
        help='Workbook name or LUID to download from Tableau Server (requires --server)'
    )

    parser.add_argument(
        '--token-name',
        metavar='NAME',
        default=None,
        help='Personal Access Token name for Tableau Server auth'
    )

    parser.add_argument(
        '--token-secret',
        metavar='SECRET',
        default=None,
        help='Personal Access Token secret for Tableau Server auth'
    )

    parser.add_argument(
        '--server-batch',
        metavar='PROJECT',
        default=None,
        help='Download and migrate all workbooks from a Tableau Server project (requires --server)'
    )

    # ── Sprint 24: Enterprise & Scale features ────────────────
    parser.add_argument(
        '--parallel',
        metavar='N',
        type=int,
        default=None,
        help='Number of parallel workers for batch migration (default: sequential)'
    )

    parser.add_argument(
        '--resume',
        action='store_true',
        default=False,
        help='Skip already-completed workbooks in batch mode (checks for existing .pbip in output dir)'
    )

    parser.add_argument(
        '--manifest',
        metavar='FILE',
        default=None,
        help=(
            'Path to a JSON manifest file mapping source workbooks to target configs. '
            'Format: [{"file": "path/to/workbook.twbx", "culture": "fr-FR", ...}]'
        )
    )

    parser.add_argument(
        '--jsonl-log',
        metavar='FILE',
        default=None,
        help='Write structured migration events to a JSON Lines (.jsonl) file for machine parsing'
    )

    parser.add_argument(
        '--check-schema',
        action='store_true',
        default=False,
        help='Check PBIR schema versions for updates and exit'
    )

    # ── Shared Semantic Model arguments ───────────────────────
    parser.add_argument(
        '--shared-model',
        nargs='*',
        metavar='WORKBOOK',
        default=None,
        help=(
            'Merge multiple workbooks into a shared semantic model with thin reports. '
            'Provide workbook paths as positional args, or combine with --batch.'
        )
    )

    parser.add_argument(
        '--model-name',
        metavar='NAME',
        default=None,
        help='Name for the shared semantic model (default: "SharedModel")'
    )

    parser.add_argument(
        '--assess-merge',
        action='store_true',
        default=False,
        help='Only assess merge feasibility for --shared-model, do not generate'
    )

    parser.add_argument(
        '--force-merge',
        action='store_true',
        default=False,
        help='Force merge even with low overlap score (use with --shared-model)'
    )

    parser.add_argument(
        '--merge-config',
        metavar='FILE',
        default=None,
        help='Load merge decisions from a JSON config file (reproducible migrations)'
    )

    parser.add_argument(
        '--save-merge-config',
        action='store_true',
        default=False,
        help='Save merge decisions to merge_config.json for later reuse'
    )

    return parser


# ── Config file loader ───────────────────────────────────────────────────────

def _apply_config_file(args):
    """Load a JSON configuration file and apply values where CLI args have defaults."""
    if not args.config:
        return
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'powerbi_import'))
        from config.migration_config import load_config
        config = load_config(filepath=args.config, args=args)
        # Apply config values to args where args has defaults
        if not args.tableau_file and config.tableau_file:
            args.tableau_file = config.tableau_file
            if not args.prep and config.prep_flow:
                args.prep = config.prep_flow
            if not args.output_dir and config.output_dir:
                args.output_dir = config.output_dir
            if args.mode == 'import' and config.model_mode != 'import':
                args.mode = config.model_mode
            if not args.culture and config.culture != 'en-US':
                args.culture = config.culture
            if args.calendar_start is None and config.calendar_start != 2020:
                args.calendar_start = config.calendar_start
            if args.calendar_end is None and config.calendar_end != 2030:
                args.calendar_end = config.calendar_end
            if args.output_format == 'pbip' and config.output_format != 'pbip':
                args.output_format = config.output_format
            if not args.rollback and config.rollback:
                args.rollback = True
            if not args.verbose and config.verbose:
                args.verbose = True
            if not args.log_file and config.log_file:
                args.log_file = config.log_file
            logger.info(f"Configuration loaded from: {args.config}")
    except Exception as e:
        print(f"Warning: Failed to load config file: {e}")


# ── Tableau Server download ─────────────────────────────────────────────────

def _download_from_server(args):
    """Download workbooks from Tableau Server/Cloud.

    Returns ExitCode on failure, None on success (caller should continue).
    Mutates args.tableau_file or args.batch.
    """
    try:
        from tableau_export.server_client import TableauServerClient
        print_header("TABLEAU SERVER DOWNLOAD")
        print(f"  Server: {args.server}")
        print(f"  Site:   {args.site or '(Default)'}")

        ts_client = TableauServerClient(
            server_url=args.server,
            token_name=getattr(args, 'token_name', None),
            token_secret=getattr(args, 'token_secret', None),
            site_id=getattr(args, 'site', ''),
        )
        ts_client.sign_in()

        download_dir = os.path.join(
            tempfile.gettempdir(), 'tableau_server_downloads'
        )

        if getattr(args, 'server_batch', None):
            # Batch: download all workbooks from a project
            print(f"  Project: {args.server_batch}")
            dl_results = ts_client.download_all_workbooks(
                download_dir, project_name=args.server_batch,
            )
            ts_client.sign_out()
            succeeded = [r for r in dl_results if r['status'] == 'success']
            print(f"  Downloaded: {len(succeeded)}/{len(dl_results)} workbooks")
            if not succeeded:
                print("  No workbooks downloaded — aborting")
                return ExitCode.EXTRACTION_FAILED
            # Switch to batch mode
            args.batch = download_dir
        elif getattr(args, 'workbook', None):
            # Single workbook download
            print(f"  Workbook: {args.workbook}")
            workbooks = ts_client.list_workbooks()
            match = None
            for wb in workbooks:
                if wb.get('id') == args.workbook or wb.get('name') == args.workbook:
                    match = wb
                    break
            if not match:
                # Try regex search
                matches = ts_client.search_workbooks(args.workbook)
                if matches:
                    match = matches[0]

            if not match:
                ts_client.sign_out()
                print(f"  Workbook '{args.workbook}' not found on server")
                return ExitCode.EXTRACTION_FAILED

            import re as _re
            safe_name = _re.sub(r'[^\w\-.]', '_', match.get('name', 'workbook'))
            twbx_path = os.path.join(download_dir, f'{safe_name}.twbx')
            os.makedirs(download_dir, exist_ok=True)
            ts_client.download_workbook(match['id'], twbx_path)
            ts_client.sign_out()
            print(f"  Downloaded: {twbx_path}")
            args.tableau_file = twbx_path
        else:
            ts_client.sign_out()
            print("  Specify --workbook NAME or --server-batch PROJECT")
            return ExitCode.GENERAL_ERROR
    except Exception as exc:
        print(f"  Server download failed: {exc}")
        logger.error(f"Tableau Server error: {exc}", exc_info=True)
        return ExitCode.EXTRACTION_FAILED
    return None


# ── Migration summary printer ────────────────────────────────────────────────

def _print_migration_summary(results, report_summary, start_time):
    """Print the final migration summary and return whether all steps succeeded."""
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
            continue
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

    return all_success


# ── Shared Semantic Model migration ─────────────────────────────────────────

def run_shared_model_migration(workbook_paths, model_name=None, output_dir=None,
                               assess_only=False, force_merge=False,
                               calendar_start=None, calendar_end=None,
                               culture=None, model_mode='import',
                               languages=None):
    """Orchestrate shared semantic model migration for multiple workbooks.

    Steps:
        1. Extract each workbook to an isolated temp directory
        2. Load all converted_objects into memory
        3. Delegate to PowerBIImporter.import_shared_model()

    Returns:
        ExitCode
    """
    import tempfile
    import shutil

    if not workbook_paths:
        print("Error: No workbooks specified for --shared-model")
        return ExitCode.GENERAL_ERROR

    # Validate all files exist
    for wb_path in workbook_paths:
        if not os.path.exists(wb_path):
            print(f"Error: Workbook not found: {wb_path}")
            return ExitCode.GENERAL_ERROR

    model_name = model_name or 'SharedModel'
    print_header("SHARED SEMANTIC MODEL MIGRATION")
    print(f"  Workbooks:    {len(workbook_paths)}")
    print(f"  Model name:   {model_name}")
    if assess_only:
        print(f"  Mode:         Assessment only")
    print()

    # Step 1: Extract each workbook to an isolated temp directory
    all_converted = []
    workbook_names = []
    temp_dirs = []

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tableau_export'))
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'powerbi_import'))

    try:
        from extract_tableau_data import TableauExtractor
        from import_to_powerbi import PowerBIImporter

        for wb_path in workbook_paths:
            basename = os.path.splitext(os.path.basename(wb_path))[0]
            workbook_names.append(basename)

            print(f"  Extracting: {basename}...")
            temp_dir = tempfile.mkdtemp(prefix=f'tableau_{basename}_')
            temp_dirs.append(temp_dir)

            extractor = TableauExtractor(wb_path, output_dir=temp_dir)
            success = extractor.extract_all()

            if not success:
                print(f"  Warning: Extraction failed for {basename}, skipping")
                all_converted.append(_empty_converted_objects())
                continue

            # Load the extracted data
            importer = PowerBIImporter(source_dir=temp_dir)
            converted = importer._load_converted_objects()
            all_converted.append(converted)

        if not any(c.get('datasources') for c in all_converted):
            print("\nError: No datasources extracted from any workbook")
            return ExitCode.EXTRACTION_FAILED

        # Step 2: Assess or full migration
        if assess_only:
            from powerbi_import.shared_model import assess_merge
            from powerbi_import.merge_assessment import print_merge_summary, generate_merge_report

            assessment = assess_merge(all_converted, workbook_names)
            print_merge_summary(assessment)

            # Save assessment JSON
            out = output_dir or os.path.join('artifacts', 'powerbi_projects', 'assessments')
            os.makedirs(out, exist_ok=True)
            assess_path = os.path.join(out, f'merge_assessment_{model_name}.json')
            generate_merge_report(assessment, output_path=assess_path)
            print(f"  Assessment saved: {assess_path}")

            return ExitCode.SUCCESS
        else:
            importer = PowerBIImporter()
            result = importer.import_shared_model(
                model_name=model_name,
                all_converted_objects=all_converted,
                workbook_names=workbook_names,
                output_dir=output_dir,
                calendar_start=calendar_start,
                calendar_end=calendar_end,
                culture=culture,
                model_mode=model_mode,
                languages=languages,
                force_merge=force_merge,
                merge_config_path=getattr(args, 'merge_config', None),
                save_config=getattr(args, 'save_merge_config', False),
            )

            if result.get('model_path'):
                return ExitCode.SUCCESS
            else:
                return ExitCode.GENERAL_ERROR

    except Exception as e:
        logger.error("Shared model migration failed: %s", e, exc_info=True)
        print(f"\nError: {e}")
        return ExitCode.GENERAL_ERROR

    finally:
        # Clean up temp directories
        for td in temp_dirs:
            try:
                shutil.rmtree(td, ignore_errors=True)
            except Exception:
                pass


def _empty_converted_objects():
    """Return an empty converted_objects dict."""
    return {
        'datasources': [], 'worksheets': [], 'dashboards': [],
        'calculations': [], 'parameters': [], 'filters': [],
        'stories': [], 'actions': [], 'sets': [], 'groups': [],
        'bins': [], 'hierarchies': [], 'sort_orders': [],
        'aliases': {}, 'custom_sql': [], 'user_filters': [],
    }


# ── Assessment mode ──────────────────────────────────────────────────────────

def _run_assessment_mode(args, results):
    """Run pre-migration assessment and strategy analysis. Returns ExitCode."""
    try:
        from powerbi_import.assessment import run_assessment, print_assessment_report, save_assessment_report
        from powerbi_import.strategy_advisor import recommend_strategy, print_recommendation

        # Load extracted data
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
        out_dir = args.output_dir or os.path.join('artifacts', 'powerbi_projects', 'assessments')
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
        return ExitCode.SUCCESS
    except Exception as e:
        logger.error(f"Assessment failed: {e}")
        print(f"\n✗ Assessment failed: {e}")
        return ExitCode.ASSESSMENT_FAILED


# ── Main entry point ─────────────────────────────────────────────────────────

def main():
    """Main entry point — orchestrates the full migration pipeline."""
    parser = _build_argument_parser()
    args = parser.parse_args()

    # Load configuration file if specified
    _apply_config_file(args)

    # ── Interactive wizard mode ───────────────────────────────
    if getattr(args, 'wizard', False):
        from powerbi_import.wizard import run_wizard, wizard_to_args
        config = run_wizard()
        if config is None:
            return ExitCode.SUCCESS
        args = wizard_to_args(config)

    # Setup structured logging
    setup_logging(verbose=args.verbose, log_file=args.log_file,
                  quiet=getattr(args, 'quiet', False))

    # ── Batch-config migration mode ───────────────────────────
    if args.batch_config:
        return _run_batch_config(args)

    # ── Tableau Server download ───────────────────────────────
    if getattr(args, 'server', None):
        server_result = _download_from_server(args)
        if server_result is not None:
            return server_result

    # ── PBIR schema version check mode ────────────────────────
    if getattr(args, 'check_schema', False):
        from powerbi_import.validator import ArtifactValidator
        print_header("PBIR SCHEMA VERSION CHECK")
        info = ArtifactValidator.check_pbir_schema_version(fetch=True)
        for schema_type, details in info.items():
            status = "UPDATE AVAILABLE" if details.get('update_available') else "up to date"
            latest = details.get('latest', details['current'])
            print(f"  {schema_type:20s}  current={details['current']}  latest={latest}  [{status}]")
        return ExitCode.SUCCESS

    # ── Consolidate existing reports mode ─────────────────────
    if getattr(args, 'consolidate', None):
        result = run_consolidate_reports(args.consolidate)
        return ExitCode.SUCCESS if result == 0 else ExitCode.GENERAL_ERROR

    # ── Shared Semantic Model mode ────────────────────────────
    if getattr(args, 'shared_model', None) is not None:
        workbook_paths = list(args.shared_model or [])

        # If --batch is also given, discover workbooks from directory
        if args.batch and not workbook_paths:
            import glob
            for ext in ('*.twb', '*.twbx'):
                workbook_paths.extend(
                    glob.glob(os.path.join(args.batch, '**', ext), recursive=True)
                )
            workbook_paths.sort()

        return run_shared_model_migration(
            workbook_paths=workbook_paths,
            model_name=getattr(args, 'model_name', None),
            output_dir=args.output_dir,
            assess_only=getattr(args, 'assess_merge', False),
            force_merge=getattr(args, 'force_merge', False),
            calendar_start=args.calendar_start,
            calendar_end=args.calendar_end,
            culture=args.culture,
            model_mode=getattr(args, 'mode', 'import'),
            languages=getattr(args, 'languages', None),
        )

    # ── Manifest-based batch migration ─────────────────────────
    manifest_data = None
    if getattr(args, 'manifest', None):
        try:
            with open(args.manifest, 'r', encoding='utf-8') as mf:
                manifest_data = json.loads(mf.read())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Error: Cannot load manifest {args.manifest}: {exc}")
            return ExitCode.GENERAL_ERROR

        # If no --batch dir given, derive from manifest file location
        if not args.batch:
            args.batch = os.path.dirname(os.path.abspath(args.manifest)) or '.'

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
            parallel=getattr(args, 'parallel', None),
            resume=getattr(args, 'resume', False),
            jsonl_log=getattr(args, 'jsonl_log', None),
            manifest=manifest_data,
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
    if args.mode and args.mode != 'import':
        print(f"Mode:        {args.mode}")
    if args.output_format and args.output_format != 'pbip':
        print(f"Format:      {args.output_format}")
    if args.rollback:
        print(f"Rollback:    enabled")
    if getattr(args, 'telemetry', False):
        print(f"Telemetry:   enabled")
    print()

    start_time = datetime.now()
    results = {}

    # Initialize progress tracker
    from powerbi_import.progress import MigrationProgress, NullProgress
    show_progress = not getattr(args, 'quiet', False)
    total_steps = 4  # extraction, generation, report, dashboard
    if args.prep:
        total_steps += 1
    if getattr(args, 'deploy', None):
        total_steps += 1
    if getattr(args, 'compare', False):
        total_steps += 1
    progress = MigrationProgress(total_steps=total_steps, show_bar=show_progress) if show_progress else NullProgress()

    # Initialize telemetry (opt-in)
    telemetry = None
    if getattr(args, 'telemetry', False):
        try:
            from powerbi_import.telemetry import TelemetryCollector
            telemetry = TelemetryCollector(enabled=True)
            telemetry.start()
        except Exception:
            pass

    # Step 1: Extraction
    progress.start("Extracting Tableau data")
    if not args.skip_extraction:
        results['extraction'] = run_extraction(args.tableau_file)
        if not results['extraction']:
            progress.fail("Extraction failed")
            print("\nMigration aborted due to extraction failure")
            return ExitCode.EXTRACTION_FAILED
        progress.complete(f"Extracted from {os.path.basename(args.tableau_file)}")
    else:
        progress.complete("Skipped (using existing data)")
        results['extraction'] = True

    # Step 1b: Prep flow (optional)
    if args.prep:
        progress.start("Parsing Prep flow")
        results['prep'] = run_prep_flow(args.prep)
        if not results['prep']:
            progress.fail("Prep flow parsing failed")
            print("\n⚠ Prep flow parsing failed — continuing with TWB data only")
        else:
            progress.complete("Prep flow merged")

    # Step 1c: Assessment (optional)
    if args.assess and results.get('extraction'):
        return _run_assessment_mode(args, results)

    # Step 2: Generate .pbip project
    # Derive report name from the source filename
    source_basename = os.path.splitext(os.path.basename(args.tableau_file))[0]

    # Rollback: backup existing output if requested
    if args.rollback and not args.dry_run:
        out_base = args.output_dir or os.path.join('artifacts', 'powerbi_projects', 'migrated')
        existing_dir = os.path.join(out_base, source_basename)
        if os.path.exists(existing_dir):
            import shutil
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_dir = existing_dir + f'.backup_{ts}'
            shutil.copytree(existing_dir, backup_dir)
            logger.info(f"Rollback backup created: {backup_dir}")
            print(f"  Rollback backup: {backup_dir}")

    if args.dry_run:
        print("\n[DRY RUN] Skipping generation — would produce:")
        print(f"  Report:  {source_basename}")
        out_dir = args.output_dir or os.path.join('artifacts', 'powerbi_projects', 'migrated')
        print(f"  Output:  {os.path.join(out_dir, source_basename)}")
        results['generation'] = True
        progress.start("Generating Power BI project")
        progress.complete("Dry run — skipped")
    else:
        progress.start("Generating Power BI project")
        results['generation'] = run_generation(
            report_name=source_basename,
            output_dir=args.output_dir,
            calendar_start=args.calendar_start,
            calendar_end=args.calendar_end,
            culture=args.culture,
            model_mode=args.mode,
            output_format=args.output_format,
            paginated=getattr(args, 'paginated', False),
            languages=getattr(args, 'languages', None),
        )
        if results['generation']:
            progress.complete(f"Generated {source_basename}")
        else:
            progress.fail("Generation failed")

    # Step 3: Incremental merge (optional)
    if getattr(args, 'incremental', None) and results.get('generation'):
        try:
            from powerbi_import.incremental import IncrementalMerger
            out_dir = args.output_dir or os.path.join('artifacts', 'powerbi_projects', 'migrated')
            generated_dir = os.path.join(out_dir, source_basename)
            existing_dir = args.incremental
            if os.path.isdir(existing_dir) and os.path.isdir(generated_dir):
                print_header("INCREMENTAL MERGE")
                merge_stats = IncrementalMerger.merge(
                    existing_dir=existing_dir,
                    incoming_dir=generated_dir,
                    output_dir=generated_dir,
                )
                print(f"  Added: {merge_stats['added']}")
                print(f"  Merged: {merge_stats['merged']}")
                print(f"  Removed: {merge_stats['removed']}")
                print(f"  Preserved: {merge_stats['preserved']}")
                if merge_stats['conflicts']:
                    print(f"  Conflicts: {len(merge_stats['conflicts'])}")
                    for c in merge_stats['conflicts']:
                        print(f"    ⚠ {c}")
            else:
                print(f"  ⚠ Incremental merge skipped: directory not found")
        except Exception as exc:
            print(f"  ⚠ Incremental merge failed: {exc}")

    # Step 3b: Goals/Scorecard generation (optional, --goals flag)
    if getattr(args, 'goals', False) and results.get('generation'):
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tableau_export'))
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'powerbi_import'))
            from pulse_extractor import extract_pulse_metrics, has_pulse_metrics
            from goals_generator import generate_goals_json, write_goals_artifact
            import xml.etree.ElementTree as _ET

            twb_path = args.workbook
            pulse_root = None
            if twb_path and os.path.isfile(twb_path):
                if twb_path.endswith('.twbx'):
                    import zipfile
                    with zipfile.ZipFile(twb_path, 'r') as z:
                        for name in z.namelist():
                            if name.endswith('.twb'):
                                with z.open(name) as f:
                                    pulse_root = _ET.parse(f).getroot()
                                break
                else:
                    pulse_root = _ET.parse(twb_path).getroot()

            if pulse_root is not None and has_pulse_metrics(pulse_root):
                metrics = extract_pulse_metrics(pulse_root)
                if metrics:
                    scorecard = generate_goals_json(metrics, report_name=source_basename)
                    out_dir = args.output_dir or os.path.join('artifacts', 'powerbi_projects', 'migrated')
                    project_dir = os.path.join(out_dir, source_basename)
                    filepath = write_goals_artifact(scorecard, project_dir)
                    print(f"  ✓ Goals scorecard: {filepath} ({len(metrics)} goals)")
                else:
                    print("  ⚠ No Pulse metrics found in workbook")
            else:
                print("  ⚠ No Pulse metrics found in workbook")
        except Exception as exc:
            print(f"  ⚠ Goals generation failed: {exc}")

    # Step 4: Migration report
    progress.start("Generating migration report")
    report_summary = None
    if results.get('generation'):
        report_summary = run_migration_report(
            report_name=source_basename,
            output_dir=args.output_dir,
        )
    fid = report_summary.get('fidelity_score', '?') if report_summary else '?'
    progress.complete(f"Fidelity: {fid}%")

    # Step 4b: HTML migration dashboard
    if results.get('generation') and not args.dry_run:
        dashboard_dir = args.output_dir or os.path.join('artifacts', 'powerbi_projects', 'migrated')
        run_html_dashboard(source_basename, dashboard_dir)

    # Step 4c: Comparison report (optional)
    if getattr(args, 'compare', False) and results.get('generation') and not args.dry_run:
        try:
            from powerbi_import.comparison_report import generate_comparison_report
            extract_dir = os.path.join(os.path.dirname(__file__), 'tableau_export')
            out_base = args.output_dir or os.path.join('artifacts', 'powerbi_projects', 'migrated')
            pbip_dir = os.path.join(out_base, source_basename)
            cmp_path = os.path.join(out_base, f'comparison_{source_basename}.html')
            html_path = generate_comparison_report(extract_dir, pbip_dir, output_path=cmp_path)
            if html_path:
                print(f"\n📋 Comparison report: {html_path}")
        except Exception as exc:
            logger.warning(f"Comparison report generation failed: {exc}")

    # Step 4d: Telemetry dashboard (optional)
    if getattr(args, 'dashboard', False) and results.get('generation') and not args.dry_run:
        try:
            from powerbi_import.telemetry_dashboard import generate_dashboard as gen_telem_dashboard
            out_base = args.output_dir or os.path.join('artifacts', 'powerbi_projects', 'migrated')
            dash_path = gen_telem_dashboard(out_base)
            if dash_path:
                print(f"\n📊 Telemetry dashboard: {dash_path}")
        except Exception as exc:
            logger.warning(f"Telemetry dashboard generation failed: {exc}")

    # Step 5: Deploy to Power BI Service (optional)
    deploy_result = None
    if getattr(args, 'deploy', None) and results.get('generation') and not args.dry_run:
        try:
            from powerbi_import.deploy.pbi_deployer import PBIWorkspaceDeployer
            print_header("DEPLOYING TO POWER BI SERVICE")
            deployer = PBIWorkspaceDeployer(workspace_id=args.deploy)
            out_dir = args.output_dir or os.path.join('artifacts', 'powerbi_projects', 'migrated')
            project_dir = os.path.join(out_dir, source_basename)
            print(f"  Workspace: {args.deploy}")
            print(f"  Project:   {project_dir}")
            deploy_result = deployer.deploy_project(
                project_dir,
                dataset_name=source_basename,
                refresh=getattr(args, 'deploy_refresh', False),
            )
            if deploy_result.status == 'succeeded':
                print(f"  ✓ Deployed — dataset={deploy_result.dataset_id}")
                if deploy_result.report_id:
                    print(f"  ✓ Report  — id={deploy_result.report_id}")
            else:
                print(f"  ✗ Deploy failed: {deploy_result.error}")
        except Exception as exc:
            print(f"  ✗ Deployment error: {exc}")
            logger.error(f"Deployment failed: {exc}", exc_info=True)

    # Final report
    all_success = _print_migration_summary(results, report_summary, start_time)

    # Finalize telemetry
    if telemetry:
        try:
            telemetry.record_stats(
                success=all_success,
                extraction=bool(results.get('extraction')),
                generation=bool(results.get('generation')),
            )
            telemetry.finish()
            telemetry.save()
            telemetry.send()
        except Exception:
            pass

    return ExitCode.SUCCESS if all_success else ExitCode.GENERAL_ERROR


if __name__ == '__main__':
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nMigration interrupted by user")
        sys.exit(ExitCode.KEYBOARD_INTERRUPT)
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        print(f"\n\nFatal error: {str(e)}")
        sys.exit(ExitCode.GENERAL_ERROR)
