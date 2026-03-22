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
import zipfile
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


def run_extraction(tableau_file, hyper_max_rows=None):
    """Run Tableau extraction with path validation."""
    global _stats
    print_step(1, 2, "TABLEAU OBJECTS EXTRACTION")

    # Security: validate file path
    if not tableau_file:
        logger.error("No Tableau file specified")
        print("Error: No Tableau file specified")
        return False

    # Null byte check
    if '\x00' in tableau_file:
        logger.error("Invalid file path (contains null bytes)")
        print("Error: Invalid file path")
        return False

    # Resolve and validate path
    resolved = os.path.realpath(tableau_file)
    ext = os.path.splitext(resolved)[1].lower()
    if ext not in ('.twb', '.twbx', '.tds', '.tdsx'):
        logger.error(f"Unsupported file extension: {ext}")
        print(f"Error: Unsupported file type: {ext}. Use .twb, .twbx, .tds, or .tdsx")
        return False

    if not os.path.exists(resolved):
        logger.error(f"Tableau file not found: {resolved}")
        print(f"Error: Tableau file not found: {resolved}")
        return False

    print(f"Source file: {tableau_file}")
    _stats.app_name = os.path.splitext(os.path.basename(tableau_file))[0]

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tableau_export'))
    try:
        from extract_tableau_data import TableauExtractor

        extractor = TableauExtractor(tableau_file, hyper_max_rows=hyper_max_rows)
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


def _run_fabric_generation(report_name=None, output_dir=None,
                           calendar_start=None, calendar_end=None,
                           culture=None, languages=None):
    """Generate Fabric-native artifacts (Lakehouse + Dataflow Gen2 +
    Notebook + DirectLake Semantic Model + Pipeline).

    Returns True on success, False on failure.
    """
    global _stats
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'powerbi_import'))
    try:
        from fabric_project_generator import FabricProjectGenerator
        from import_to_powerbi import PowerBIImporter

        # Load extracted JSON files
        loader = PowerBIImporter()
        extracted = loader._load_converted_objects()

        if not extracted.get('datasources'):
            print("  [ERROR] No datasources found — run extraction first")
            return False

        # Determine report name
        if not report_name:
            dashboards = extracted.get('dashboards', [])
            if dashboards:
                report_name = dashboards[0].get('name', 'Report')
            else:
                report_name = 'Report'

        base_dir = output_dir or os.path.join('artifacts', 'fabric_projects', 'migrated')

        generator = FabricProjectGenerator(output_dir=base_dir)
        results = generator.generate_project(
            project_name=report_name,
            extracted_data=extracted,
            calendar_start=calendar_start,
            calendar_end=calendar_end,
            culture=culture,
            languages=languages,
        )

        project_dir = results.get('project_path', '')
        if project_dir and os.path.exists(project_dir):
            _stats.pbip_path = project_dir
            sm = results.get('artifacts', {}).get('semantic_model', {})
            _stats.tmdl_tables = sm.get('tables', 0)
            _stats.tmdl_columns = sm.get('columns', 0)
            _stats.tmdl_measures = sm.get('measures', 0)
            _stats.tmdl_relationships = sm.get('relationships', 0)

        print("\n✓ Fabric project generated successfully")
        return True

    except Exception as e:
        logger.error(f"Fabric generation failed: {e}", exc_info=True)
        print(f"\nError during Fabric generation: {str(e)}")
        return False


def run_generation(report_name=None, output_dir=None, calendar_start=None,
                   calendar_end=None, culture=None, model_mode='import',
                   output_format='pbip', paginated=False, languages=None,
                   composite_threshold=None, agg_tables='none'):
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

    # ── Fabric-native output format ──────────────────────────────
    if output_format == 'fabric':
        return _run_fabric_generation(
            report_name=report_name, output_dir=output_dir,
            calendar_start=calendar_start, calendar_end=calendar_end,
            culture=culture, languages=languages,
        )

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'powerbi_import'))
    try:
        from import_to_powerbi import PowerBIImporter

        importer = PowerBIImporter()
        importer.import_all(generate_pbip=True, report_name=report_name, output_dir=output_dir,
                            calendar_start=calendar_start, calendar_end=calendar_end,
                            culture=culture, model_mode=model_mode,
                            output_format=output_format, languages=languages,
                            composite_threshold=composite_threshold, agg_tables=agg_tables)

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

        summary = report.get_summary()
        # Include weighted completeness score — more accurate than flat average
        completeness = report.get_completeness_score()
        summary['overall_score'] = completeness['overall_score']
        summary['grade'] = completeness['grade']
        return summary

    except Exception as e:
        logger.warning(f"Migration report generation failed: {e}", exc_info=True)
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


def _run_check_hyper(args):
    """Analyse .hyper files in a workbook and print diagnostic report."""
    import sys as _sys
    sys_path = os.path.dirname(os.path.abspath(__file__))
    if os.path.join(sys_path, 'tableau_export') not in _sys.path:
        _sys.path.insert(0, os.path.join(sys_path, 'tableau_export'))
    from hyper_reader import read_hyper, read_hyper_from_twbx, get_hyper_metadata, infer_hyper_relationships

    tableau_file = getattr(args, 'tableau_file', None)
    if not tableau_file:
        print("Error: No workbook file specified. Provide a .twbx path.")
        return ExitCode.GENERAL_ERROR

    print_header("HYPER FILE DIAGNOSTIC REPORT")
    ext = os.path.splitext(tableau_file)[1].lower()

    all_tables = []
    if ext in ('.twbx', '.tdsx'):
        print(f"  Archive: {os.path.basename(tableau_file)}")
        max_rows = getattr(args, 'hyper_rows', None) or 20
        results = read_hyper_from_twbx(tableau_file, max_rows=max_rows)
        if not results:
            print("  No .hyper files found in archive.")
            return ExitCode.SUCCESS

        for r in results:
            fname = r.get('original_filename', r.get('archive_path', '?'))
            fmt = r.get('format', 'unknown')
            tables = r.get('tables', [])
            meta = r.get('metadata', {})
            fsize = meta.get('file_size_bytes', 0)
            print(f"\n  ── {fname} ──")
            print(f"     Format: {fmt}    Size: {fsize:,} bytes")
            print(f"     Tables: {len(tables)}")

            for t in tables:
                tname = t.get('table', '?')
                rc = t.get('row_count', 0)
                cc = t.get('column_count', len(t.get('columns', [])))
                sr = t.get('sample_row_count', len(t.get('sample_rows', [])))
                print(f"       • {tname}: {rc:,} rows, {cc} columns, {sr} sample rows")
                cols = t.get('columns', [])
                for col in cols[:10]:
                    ht = col.get('hyper_type', 'unknown')
                    print(f"           {col['name']:30s}  {ht}")
                if len(cols) > 10:
                    print(f"           ... and {len(cols) - 10} more columns")
                # Column stats
                stats = t.get('column_stats', {})
                high_card = [(c, s) for c, s in stats.items()
                             if s.get('distinct_count', 0) and s['distinct_count'] > 100000]
                if high_card:
                    print(f"       ⚠ High-cardinality columns:")
                    for cname, st in high_card[:5]:
                        print(f"           {cname}: {st['distinct_count']:,} distinct values")

            all_tables.extend(tables)

        # Relationship inference
        rels = infer_hyper_relationships(all_tables)
        if rels:
            print(f"\n  ── Inferred Relationships ({len(rels)}) ──")
            for rel in rels:
                print(f"     {rel['from_table']}.{rel['from_column']} → "
                      f"{rel['to_table']}.{rel['to_column']} ({rel['cardinality']})")

        # Recommendations
        total_rows = sum(t.get('row_count', 0) for t in all_tables)
        print(f"\n  ── Summary ──")
        print(f"     Total tables: {len(all_tables)}")
        print(f"     Total rows:   {total_rows:,}")
        if total_rows > 10_000_000:
            print(f"     ⚠ Over 10M rows — consider DirectQuery instead of Import")
        elif total_rows > 1_000_000:
            print(f"     ℹ Over 1M rows — monitor refresh times in Import mode")

        # Check tableauhyperapi availability
        try:
            import tableauhyperapi  # noqa: F401
            print(f"     ✓ tableauhyperapi installed — full Hyper reading available")
        except ImportError:
            fmt_found = {r.get('format') for r in results}
            if 'hyper_api' not in fmt_found and any(r.get('format') == 'unknown' or
                                                     (r.get('format') == 'hyper' and not r.get('tables'))
                                                     for r in results):
                print(f"     ⚠ tableauhyperapi not installed — some .hyper files may have limited data")
                print(f"       Install: pip install tableauhyperapi")
    elif ext == '.hyper':
        result = read_hyper(tableau_file, max_rows=getattr(args, 'hyper_rows', None) or 20)
        meta_report = get_hyper_metadata(tableau_file, max_rows=getattr(args, 'hyper_rows', None) or 20)
        print(f"  File: {os.path.basename(tableau_file)}")
        print(f"  Format: {result.get('format', 'unknown')}")
        print(f"  Total tables: {meta_report.get('total_tables', 0)}")
        print(f"  Total rows: {meta_report.get('total_rows', 0):,}")
        for t in meta_report.get('tables', []):
            print(f"    • {t['name']}: {t.get('row_count', 0):,} rows, {t.get('column_count', 0)} columns")
        for rec in meta_report.get('recommendations', []):
            print(f"  ⚠ {rec}")
    else:
        print(f"  Unsupported file type: {ext} (expected .twbx, .tdsx, or .hyper)")
        return ExitCode.GENERAL_ERROR

    return ExitCode.SUCCESS


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
            'fidelity': report_summary.get('overall_score', report_summary.get('fidelity_score')) if report_summary else None,
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
        'fidelity': report_summary.get('overall_score', report_summary.get('fidelity_score')) if report_summary else None,
        'report_name': basename,
        'output_dir': workbook_output_dir,
        'metadata_path': os.path.join(workbook_output_dir, basename, 'migration_metadata.json'),
    }


def _print_batch_summary(batch_results, batch_duration, migrated_root):
    """Print formatted batch summary and consolidated HTML dashboard.

    Returns:
        Tuple of (succeeded_count, failed_count).
    """
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

    return succeeded, failed


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

    batch_duration = datetime.now() - batch_start
    succeeded, failed = _print_batch_summary(batch_results, batch_duration, migrated_root)

    # ── Close JSONL log ────────────────────────────────────
    fidelities = [r['fidelity'] for r in batch_results.values() if r.get('fidelity') is not None]
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

def _add_source_args(parser):
    """Add source file and extraction arguments."""
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


def _add_output_args(parser):
    """Add output directory and logging arguments."""
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


def _add_batch_args(parser):
    """Add batch migration and consolidation arguments."""
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


def _add_migration_args(parser):
    """Add migration options (calendar, culture, format, etc.)."""
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
        '--hyper-rows',
        metavar='N',
        type=int,
        default=None,
        help='Max rows to inline from .hyper extract data (default: 20 for sample, up to 500 for inline #table). '
             'Set higher to include more data; above 500 switches to Csv.Document() reference.'
    )

    parser.add_argument(
        '--mode',
        choices=['import', 'directquery', 'composite'],
        default='import',
        help='Semantic model mode: import (default), directquery, or composite'
    )

    parser.add_argument(
        '--composite-threshold',
        metavar='COLS',
        type=int,
        default=None,
        help='Column count threshold for composite mode: tables with more columns → directQuery (default: 10)'
    )

    parser.add_argument(
        '--agg-tables',
        choices=['auto', 'none'],
        default='none',
        help='Generate Import-mode aggregation tables for directQuery fact tables (composite mode only)'
    )

    parser.add_argument(
        '--rollback',
        action='store_true',
        help='Backup existing .pbip project before overwriting'
    )

    parser.add_argument(
        '--output-format',
        choices=['pbip', 'tmdl', 'pbir', 'fabric'],
        default='pbip',
        help='Output format: pbip (default, full project), tmdl (semantic model only), pbir (report only), fabric (Fabric-native: Lakehouse + Dataflow Gen2 + Notebook + DirectLake Semantic Model + Pipeline)'
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
        '--optimize-dax',
        action='store_true',
        default=False,
        help='Run DAX optimizer on converted measures (nested IF→SWITCH, COALESCE, constant fold)'
    )

    parser.add_argument(
        '--time-intelligence',
        choices=['auto', 'none'],
        default='none',
        help='Auto-inject Time Intelligence measures (YTD, PY, YoY%%) for date-based measures'
    )

    parser.add_argument(
        '--validate-data',
        action='store_true',
        default=False,
        help='Run post-migration data validation comparing expected vs actual measure values'
    )


def _add_report_args(parser):
    """Add report, dashboard, and telemetry arguments."""
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


def _add_deploy_args(parser):
    """Add deployment arguments (PBI Service, Fabric bundle)."""
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

    parser.add_argument(
        '--deploy-bundle',
        metavar='WORKSPACE_ID',
        default=None,
        help=(
            'Deploy a shared semantic model project as a Fabric bundle '
            '(SemanticModel + thin reports). Requires FABRIC_TENANT_ID, '
            'FABRIC_CLIENT_ID, FABRIC_CLIENT_SECRET env vars. '
            'Use with --shared-model or point --output-dir to an existing project.'
        )
    )

    parser.add_argument(
        '--bundle-refresh',
        action='store_true',
        default=False,
        help='Trigger a dataset refresh after bundle deployment (requires --deploy-bundle)'
    )

    parser.add_argument(
        '--multi-tenant',
        metavar='CONFIG_FILE',
        default=None,
        help=(
            'Deploy the shared model to multiple tenant workspaces using a JSON '
            'config file with per-tenant connection overrides and RLS mappings. '
            'Use with --deploy-bundle or --shared-model.'
        )
    )

    parser.add_argument(
        '--sync',
        action='store_true',
        default=False,
        help=(
            'Sync mode: detect changed workbooks, incrementally migrate only '
            'modified artifacts, and deploy updates. Use with --deploy or --batch.'
        )
    )


def _add_server_args(parser):
    """Add Tableau Server extraction arguments."""
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
        help='Personal Access Token secret for Tableau Server auth. '
             'Prefer TABLEAU_TOKEN_SECRET env var to avoid process list exposure.'
    )

    parser.add_argument(
        '--server-batch',
        metavar='PROJECT',
        default=None,
        help='Download and migrate all workbooks from a Tableau Server project (requires --server)'
    )

    parser.add_argument(
        '--migrate-schedules',
        action='store_true',
        default=False,
        help='Extract Tableau refresh schedules / subscriptions and generate PBI refresh config JSON'
    )


def _add_enterprise_args(parser):
    """Add enterprise and scale arguments (parallel, resume, manifest, etc.)."""
    parser.add_argument(
        '--parallel', '--workers',
        metavar='N',
        type=int,
        default=None,
        dest='parallel',
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

    parser.add_argument(
        '--check-hyper',
        action='store_true',
        default=False,
        help='Analyse .hyper files in the workbook and print diagnostic report, then exit'
    )

    parser.add_argument(
        '--governance',
        choices=['warn', 'enforce'],
        default=None,
        help='Run governance checks after generation: naming conventions, PII detection, audit trail. '
             '"warn" reports issues; "enforce" auto-renames and blocks on violations.'
    )

    parser.add_argument(
        '--governance-config',
        metavar='JSON_FILE',
        default=None,
        help='Path to governance configuration JSON file (naming rules, PII patterns, sensitivity mapping). '
             'Default rules apply when not specified.'
    )


def _add_shared_model_args(parser):
    """Add shared semantic model arguments."""
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

    parser.add_argument(
        '--global-assess',
        nargs='*',
        metavar='WORKBOOK',
        default=None,
        help=(
            'Run a global cross-workbook assessment to find merge candidates. '
            'Provide workbook paths or combine with --batch DIR. '
            'Generates an HTML report with merge clusters and pairwise scores.'
        )
    )

    parser.add_argument(
        '--merge-preview',
        action='store_true',
        default=False,
        help=(
            'Dry-run merge: show what would be merged, renamed, and conflicted '
            'without writing any files (use with --shared-model)'
        )
    )

    parser.add_argument(
        '--strict-merge',
        action='store_true',
        default=False,
        help=(
            'Strict merge validation: block generation if post-merge safety '
            'checks fail (cycles, unresolved DAX references, incompatible '
            'column types). Without this flag, validation is advisory.'
        )
    )

    parser.add_argument(
        '--add-to-model',
        nargs=2,
        metavar=('DIR', 'WORKBOOK'),
        default=None,
        help=(
            'Add a new workbook to an existing shared model. '
            'DIR is the shared model output directory, WORKBOOK is the .twb/.twbx to add.'
        )
    )

    parser.add_argument(
        '--remove-from-model',
        nargs=2,
        metavar=('DIR', 'WB_NAME'),
        default=None,
        help=(
            'Remove a workbook from an existing shared model. '
            'DIR is the shared model output directory, WB_NAME is the workbook name to remove. '
            'Shared tables (used by other workbooks) are kept.'
        )
    )

    parser.add_argument(
        '--bulk-assess',
        metavar='DIR',
        default=None,
        help=(
            'Scan a folder of .twb/.twbx files and produce a portfolio-level '
            'readiness report (HTML dashboard) without migrating'
        )
    )

    parser.add_argument(
        '--server-assess',
        action='store_true',
        default=False,
        help=(
            'Assess all workbooks on a Tableau Server site and produce a '
            'portfolio readiness report (requires --server)'
        )
    )

    parser.add_argument(
        '--live-connection',
        metavar='WORKSPACE_ID/MODEL_NAME',
        default=None,
        help=(
            'Wire thin reports via byConnection (Fabric workspace reference) '
            'instead of byPath. Format: WORKSPACE_ID/MODEL_NAME. '
            'Use with --shared-model.'
        )
    )


def _build_argument_parser():
    """Build and return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description='Migrate a Tableau workbook to a Power BI project (.pbip)'
    )

    _add_source_args(parser)
    _add_output_args(parser)
    _add_batch_args(parser)
    _add_migration_args(parser)
    _add_report_args(parser)
    _add_deploy_args(parser)
    _add_server_args(parser)
    _add_enterprise_args(parser)
    _add_shared_model_args(parser)

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
    except (OSError, json.JSONDecodeError, ValueError) as e:
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
            token_secret=getattr(args, 'token_secret', None) or os.environ.get('TABLEAU_TOKEN_SECRET'),
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


# ── Bundle deployment helper ────────────────────────────────────────────────

def _run_bundle_deploy(project_dir, workspace_id, refresh=False):
    """Deploy a shared model project as a Fabric bundle.

    Args:
        project_dir: Root project directory with .SemanticModel + .Report dirs.
        workspace_id: Target Fabric workspace ID.
        refresh: Trigger dataset refresh after deployment.

    Returns:
        ExitCode
    """
    try:
        from powerbi_import.deploy.bundle_deployer import deploy_bundle_from_cli

        print_header("FABRIC BUNDLE DEPLOYMENT")
        print(f"  Workspace: {workspace_id}")
        print(f"  Project:   {project_dir}")

        result = deploy_bundle_from_cli(
            project_dir=project_dir,
            workspace_id=workspace_id,
            refresh=refresh,
        )

        if result.success:
            return ExitCode.SUCCESS
        else:
            return ExitCode.GENERAL_ERROR

    except Exception as exc:
        logger.error("Bundle deployment failed: %s", exc, exc_info=True)
        print(f"\n  ✗ Bundle deployment error: {exc}")
        return ExitCode.GENERAL_ERROR


# ── Global Assessment mode ──────────────────────────────────────────────────

def run_global_assessment_mode(args):
    """Run cross-workbook global assessment and generate HTML report.

    Discovers workbooks from --global-assess paths or --batch directory,
    extracts each, runs pairwise merge analysis, and outputs HTML + JSON.

    Returns:
        ExitCode
    """
    import tempfile
    import shutil

    workbook_paths = list(args.global_assess or [])

    # If --batch is also given, discover workbooks from directory
    if args.batch and not workbook_paths:
        import glob
        for ext in ('*.twb', '*.twbx'):
            workbook_paths.extend(
                glob.glob(os.path.join(args.batch, '**', ext), recursive=True)
            )
        workbook_paths.sort()

    if len(workbook_paths) < 2:
        print("Error: --global-assess requires at least 2 workbooks "
              "(or use --batch DIR)")
        return ExitCode.GENERAL_ERROR

    # Validate all files exist
    for wb_path in workbook_paths:
        if not os.path.exists(wb_path):
            print(f"Error: Workbook not found: {wb_path}")
            return ExitCode.GENERAL_ERROR

    print_header("GLOBAL CROSS-WORKBOOK ASSESSMENT")
    print(f"  Workbooks:  {len(workbook_paths)}")
    for wp in workbook_paths:
        print(f"    - {os.path.basename(wp)}")
    print()

    all_converted = []
    workbook_names = []
    temp_dirs = []

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tableau_export'))
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'powerbi_import'))

    try:
        from extract_tableau_data import TableauExtractor
        from import_to_powerbi import PowerBIImporter
        from powerbi_import.global_assessment import (
            run_global_assessment,
            print_global_summary,
            generate_global_html_report,
            save_global_assessment_json,
        )

        # Extract each workbook
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

            importer = PowerBIImporter(source_dir=temp_dir)
            converted = importer._load_converted_objects()
            all_converted.append(converted)

        if sum(1 for c in all_converted if c.get('datasources')) < 2:
            print("\nError: Need at least 2 workbooks with datasources")
            return ExitCode.EXTRACTION_FAILED

        # Run global assessment
        print("\n  Analyzing pairwise merge scores...")
        result = run_global_assessment(all_converted, workbook_names)

        # Print console summary
        print_global_summary(result)

        # Save outputs
        out = args.output_dir or os.path.join(
            'artifacts', 'powerbi_projects', 'assessments'
        )
        os.makedirs(out, exist_ok=True)

        html_path = os.path.join(out, 'global_assessment.html')
        generate_global_html_report(result, output_path=html_path)
        print(f"  HTML report: {html_path}")

        json_path = os.path.join(out, 'global_assessment.json')
        save_global_assessment_json(result, output_path=json_path)
        print(f"  JSON report: {json_path}")

        return ExitCode.SUCCESS

    except Exception as e:
        logger.error("Global assessment failed: %s", e, exc_info=True)
        print(f"\nError: {e}")
        return ExitCode.GENERAL_ERROR

    finally:
        for td in temp_dirs:
            try:
                shutil.rmtree(td, ignore_errors=True)
            except OSError as e:
                logger.debug('Temp dir cleanup failed: %s', e)


# ── Shared Semantic Model migration ─────────────────────────────────────────

def run_shared_model_migration(workbook_paths, model_name=None, output_dir=None,
                               assess_only=False, force_merge=False,
                               calendar_start=None, calendar_end=None,
                               culture=None, model_mode='import',
                               languages=None, merge_config_path=None,
                               save_config=False, strict_merge=False,
                               output_format='pbip'):
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
                merge_config_path=merge_config_path,
                save_config=save_config,
                strict_merge=strict_merge,
                workbook_paths=workbook_paths,
                output_format=output_format,
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
            except OSError as e:
                logger.debug('Temp dir cleanup failed: %s', e)


def _empty_converted_objects():
    """Return an empty converted_objects dict."""
    return {
        'datasources': [], 'worksheets': [], 'dashboards': [],
        'calculations': [], 'parameters': [], 'filters': [],
        'stories': [], 'actions': [], 'sets': [], 'groups': [],
        'bins': [], 'hierarchies': [], 'sort_orders': [],
        'aliases': {}, 'custom_sql': [], 'user_filters': [],
    }


def _run_add_to_model(args):
    """Handle --add-to-model DIR WORKBOOK."""
    import tempfile
    import shutil

    model_dir, workbook_path = args.add_to_model
    if not os.path.isdir(model_dir):
        print(f"Error: Model directory not found: {model_dir}")
        return ExitCode.GENERAL_ERROR
    if not os.path.exists(workbook_path):
        print(f"Error: Workbook not found: {workbook_path}")
        return ExitCode.GENERAL_ERROR

    basename = os.path.splitext(os.path.basename(workbook_path))[0]
    print_header("ADD WORKBOOK TO SHARED MODEL")
    print(f"  Model dir:  {model_dir}")
    print(f"  Workbook:   {basename}")
    print()

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tableau_export'))
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'powerbi_import'))

    temp_dir = None
    try:
        from extract_tableau_data import TableauExtractor
        from powerbi_import.shared_model import add_to_model
        from import_to_powerbi import PowerBIImporter

        # Extract new workbook
        temp_dir = tempfile.mkdtemp(prefix=f'tableau_{basename}_')
        extractor = TableauExtractor(workbook_path, output_dir=temp_dir)
        success = extractor.extract_all()
        if not success:
            print(f"Error: Extraction failed for {basename}")
            return ExitCode.EXTRACTION_FAILED

        importer = PowerBIImporter(source_dir=temp_dir)
        new_extracted = importer._load_converted_objects()

        # Run incremental add
        result = add_to_model(
            model_dir=model_dir,
            new_extracted=new_extracted,
            new_workbook_name=basename,
            new_workbook_path=workbook_path,
            force=getattr(args, 'force_merge', False),
        )

        status = result.get('status', 'unknown')
        if status == 'rejected':
            print(f"  Add rejected: {result.get('reason', '')}")
            return ExitCode.GENERAL_ERROR

        if status == 'added':
            manifest = result['manifest']
            manifest.save(model_dir)

            # Regenerate TMDL from merged model
            merged = result['merged']
            importer2 = PowerBIImporter()
            project_dir = model_dir
            sm_dir = None
            for entry in os.listdir(model_dir):
                if entry.endswith('.SemanticModel'):
                    sm_dir = os.path.join(model_dir, entry)
                    break

            if sm_dir:
                importer2.create_semantic_model_structure(
                    project_dir, manifest.model_name, merged
                )

            # Generate thin report for new workbook
            from powerbi_import.thin_report_generator import ThinReportGenerator
            from powerbi_import.shared_model import build_field_mapping, assess_merge

            assessment = result['assessment']
            field_mapping = build_field_mapping(assessment, basename)
            thin_gen = ThinReportGenerator(manifest.model_name, model_dir)
            thin_gen.generate_thin_report(basename, new_extracted, field_mapping=field_mapping)

            val = result.get('validation', {})
            score = val.get('score', 0) if val else 0
            print(f"  [OK] Workbook '{basename}' added to model")
            print(f"  Tables: {manifest.artifact_counts.get('tables', 0)}")
            print(f"  Validation: {score}/100")
            return ExitCode.SUCCESS

        print(f"  Unexpected status: {status}")
        return ExitCode.GENERAL_ERROR

    except Exception as e:
        logger.error("Add-to-model failed: %s", e, exc_info=True)
        print(f"\nError: {e}")
        return ExitCode.GENERAL_ERROR
    finally:
        if temp_dir:
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except OSError:
                pass


def _run_remove_from_model(args):
    """Handle --remove-from-model DIR WB_NAME."""
    model_dir, wb_name = args.remove_from_model
    if not os.path.isdir(model_dir):
        print(f"Error: Model directory not found: {model_dir}")
        return ExitCode.GENERAL_ERROR

    print_header("REMOVE WORKBOOK FROM SHARED MODEL")
    print(f"  Model dir:  {model_dir}")
    print(f"  Workbook:   {wb_name}")
    print()

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'powerbi_import'))

    try:
        from powerbi_import.shared_model import remove_from_model

        result = remove_from_model(model_dir=model_dir, workbook_name=wb_name)

        status = result.get('status', 'unknown')
        if status == 'not_found':
            print(f"  Workbook '{wb_name}' not found in manifest.")
            return ExitCode.GENERAL_ERROR

        if status == 'removed':
            manifest = result['manifest']
            manifest.save(model_dir)

            removed_t = result.get('removed_tables', [])
            removed_m = result.get('removed_measures', [])
            kept = result.get('shared_tables_kept', [])

            print(f"  [OK] Workbook '{wb_name}' removed from model")
            if removed_t:
                print(f"  Removed tables: {', '.join(removed_t)}")
            if removed_m:
                print(f"  Removed measures: {', '.join(removed_m)}")
            if kept:
                print(f"  Shared tables kept: {', '.join(kept)}")
            print(f"  Remaining workbooks: {len(manifest.workbooks)}")

            # Regenerate TMDL from updated model
            merged = result.get('merged')
            if merged:
                from import_to_powerbi import PowerBIImporter
                importer = PowerBIImporter()
                sm_dir = None
                for entry in os.listdir(model_dir):
                    if entry.endswith('.SemanticModel'):
                        sm_dir = os.path.join(model_dir, entry)
                        break
                if sm_dir:
                    importer.create_semantic_model_structure(
                        model_dir, manifest.model_name, merged
                    )

            # Remove the thin report directory
            for entry in os.listdir(model_dir):
                if entry.startswith(wb_name) and entry.endswith('.Report'):
                    report_dir = os.path.join(model_dir, entry)
                    if os.path.isdir(report_dir):
                        import shutil
                        shutil.rmtree(report_dir, ignore_errors=True)
                        print(f"  Removed thin report: {entry}")

            return ExitCode.SUCCESS

        print(f"  Unexpected status: {status}")
        return ExitCode.GENERAL_ERROR

    except Exception as e:
        logger.error("Remove-from-model failed: %s", e, exc_info=True)
        print(f"\nError: {e}")
        return ExitCode.GENERAL_ERROR


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

    # ── Hyper diagnostic mode ─────────────────────────────────
    if getattr(args, 'check_hyper', False):
        return _run_check_hyper(args)

    # ── Consolidate existing reports mode ─────────────────────
    if getattr(args, 'consolidate', None):
        result = run_consolidate_reports(args.consolidate)
        return ExitCode.SUCCESS if result == 0 else ExitCode.GENERAL_ERROR

    # ── Global Assessment mode ─────────────────────────────────
    if getattr(args, 'global_assess', None) is not None:
        return run_global_assessment_mode(args)

    # ── Add-to-model mode ───────────────────────────────────
    if getattr(args, 'add_to_model', None):
        return _run_add_to_model(args)

    # ── Remove-from-model mode ────────────────────────────────
    if getattr(args, 'remove_from_model', None):
        return _run_remove_from_model(args)

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

        exit_code = run_shared_model_migration(
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
            merge_config_path=getattr(args, 'merge_config', None),
            save_config=getattr(args, 'save_merge_config', False),
            strict_merge=getattr(args, 'strict_merge', False),
            output_format=getattr(args, 'output_format', 'pbip'),
        )

        # Auto-deploy bundle if --deploy-bundle is given alongside --shared-model
        if exit_code == ExitCode.SUCCESS and getattr(args, 'deploy_bundle', None):
            model_name = getattr(args, 'model_name', None) or 'SharedModel'
            project_dir = os.path.join(
                args.output_dir or os.path.join('artifacts', 'powerbi_projects', 'shared'),
                model_name,
            )
            exit_code = _run_bundle_deploy(
                project_dir, args.deploy_bundle,
                refresh=getattr(args, 'bundle_refresh', False),
            )

        return exit_code

    # ── Standalone bundle deployment mode ─────────────────────
    if getattr(args, 'deploy_bundle', None) and not getattr(args, 'shared_model', None):
        project_dir = args.output_dir
        if not project_dir:
            print("Error: --deploy-bundle requires --output-dir pointing to a project directory")
            return ExitCode.GENERAL_ERROR
        if not os.path.isdir(project_dir):
            print(f"Error: project directory not found: {project_dir}")
            return ExitCode.GENERAL_ERROR
        return _run_bundle_deploy(
            project_dir, args.deploy_bundle,
            refresh=getattr(args, 'bundle_refresh', False),
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

    return _run_single_migration(args)


def _print_single_migration_header(args):
    """Print the header with migration options for a single file."""
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


def _init_telemetry(args):
    """Initialize telemetry collector if opt-in. Returns collector or None."""
    if not getattr(args, 'telemetry', False):
        return None
    try:
        from powerbi_import.telemetry import TelemetryCollector
        telemetry = TelemetryCollector(enabled=True)
        telemetry.start()
        return telemetry
    except (ImportError, OSError, ValueError) as e:
        logger.debug('Telemetry init failed: %s', e)
        return None


def _finalize_telemetry(telemetry, all_success, results):
    """Finalize and send telemetry data."""
    if not telemetry:
        return
    try:
        telemetry.record_stats(
            success=all_success,
            extraction=bool(results.get('extraction')),
            generation=bool(results.get('generation')),
        )
        telemetry.finish()
        telemetry.save()
        telemetry.send()
    except (OSError, ValueError) as e:
        logger.debug('Telemetry finalization failed: %s', e)


def _run_incremental_merge(args, source_basename):
    """Run optional incremental merge step."""
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
    except (ImportError, OSError, ValueError) as exc:
        print(f"  ⚠ Incremental merge failed: {exc}")


def _run_goals_generation(args, source_basename):
    """Run optional Pulse → Goals/Scorecard generation."""
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
    except (ImportError, OSError, ValueError) as exc:
        print(f"  ⚠ Goals generation failed: {exc}")


def _run_governance_checks(args, source_basename):
    """Run governance checks on the generated TMDL artifacts.

    Reads extracted data and runs naming convention enforcement,
    PII detection, and audit trail recording.
    """
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'powerbi_import'))
        from governance import GovernanceEngine, AuditTrail, run_governance

        # Load governance config
        gov_config = {"mode": args.governance}
        if getattr(args, 'governance_config', None):
            config_path = args.governance_config
            if os.path.isfile(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    user_cfg = json.load(f)
                if isinstance(user_cfg, dict):
                    gov_config.update(user_cfg)

        # Load extracted data to build table list for checks
        source_dir = os.path.join(os.path.dirname(__file__), 'tableau_export')
        tmdl_tables = []
        ds_path = os.path.join(source_dir, 'datasources.json')
        if os.path.isfile(ds_path):
            with open(ds_path, 'r', encoding='utf-8') as f:
                datasources = json.load(f)
            for ds in datasources:
                for table in ds.get('tables', []):
                    tmdl_tables.append({
                        'name': table.get('name', ''),
                        'columns': table.get('columns', []),
                        'measures': [],
                    })
        calc_path = os.path.join(source_dir, 'calculations.json')
        if os.path.isfile(calc_path):
            with open(calc_path, 'r', encoding='utf-8') as f:
                calcs = json.load(f)
            # Add measures to the first table (main table)
            if tmdl_tables:
                tmdl_tables[0]['measures'] = [
                    {'name': c.get('caption', c.get('name', '')).replace('[', '').replace(']', '')}
                    for c in calcs if c.get('role', 'measure') == 'measure'
                ]

        # Run checks
        report = run_governance(tmdl_tables, config=gov_config)

        # Print results
        print(f"\n  Governance ({args.governance} mode): "
              f"{report.issue_count} issues ({report.warn_count} warn, {report.fail_count} fail)")
        if report.classifications:
            print(f"  PII classifications: {len(report.classifications)} columns flagged")
        for issue in report.issues[:10]:
            severity_icon = "⚠" if issue.severity == "warn" else "✗" if issue.severity == "fail" else "ℹ"
            print(f"    {severity_icon} [{issue.category}] {issue.message}")
        if len(report.issues) > 10:
            print(f"    ... and {len(report.issues) - 10} more issues")

        # Save governance report JSON alongside the project
        out_dir = args.output_dir or os.path.join('artifacts', 'powerbi_projects', 'migrated')
        project_dir = os.path.join(out_dir, source_basename)
        if os.path.isdir(project_dir):
            gov_path = os.path.join(project_dir, 'governance_report.json')
            with open(gov_path, 'w', encoding='utf-8') as f:
                json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
            print(f"  ✓ Governance report: {gov_path}")

        # Audit trail
        if gov_config.get('audit_trail', True):
            audit_log_path = gov_config.get('audit_log_path', 'migration_audit.jsonl')
            # If relative, place alongside the project
            if not os.path.isabs(audit_log_path) and os.path.isdir(project_dir):
                audit_log_path = os.path.join(project_dir, audit_log_path)
            audit = AuditTrail(log_path=audit_log_path)
            source_hash = AuditTrail.compute_file_hash(getattr(args, 'tableau_file', ''))
            output_hash = AuditTrail.compute_dir_hash(project_dir) if os.path.isdir(project_dir) else ""
            audit.record(
                source_file=getattr(args, 'tableau_file', ''),
                output_dir=project_dir,
                workbook_name=source_basename,
                source_hash=source_hash,
                output_hash=output_hash,
                governance_summary={
                    'mode': args.governance,
                    'issues': report.issue_count,
                    'warns': report.warn_count,
                    'fails': report.fail_count,
                    'pii_columns': len(report.classifications),
                },
            )
            saved = audit.save()
            if saved:
                print(f"  ✓ Audit trail: {audit_log_path} ({saved} entries)")

    except (ImportError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"  ⚠ Governance checks failed: {exc}")


def _extract_twbx_data_files(args, source_basename):
    """Extract embedded data files from TWBX into the PBI output directory.

    For .twbx sources, extracts xlsx/csv/txt/json data files into a ``Data/``
    subdirectory alongside the .pbip project and updates the ``DataFolder``
    M parameter in ``expressions.tmdl`` so Power BI can find them.
    """
    source = getattr(args, 'tableau_file', '')
    if not source or not source.lower().endswith('.twbx'):
        return
    if not zipfile.is_zipfile(source):
        return

    out_base = args.output_dir or os.path.join('artifacts', 'powerbi_projects', 'migrated')
    project_dir = os.path.join(out_base, source_basename)
    data_dir = os.path.join(project_dir, 'Data')

    _SKIP_EXT = {'.twb', '.tds', '.twbr'}
    extracted_files = []

    try:
        with zipfile.ZipFile(source, 'r') as zf:
            for entry in zf.namelist():
                ext = os.path.splitext(entry)[1].lower()
                if ext in _SKIP_EXT or entry.endswith('/'):
                    continue
                # Extract data and image files
                dest = os.path.join(data_dir, entry)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with zf.open(entry) as src, open(dest, 'wb') as dst:
                    dst.write(src.read())
                extracted_files.append(entry)
    except (zipfile.BadZipFile, OSError) as exc:
        logger.warning("Could not extract TWBX data files: %s", exc)
        return

    if not extracted_files:
        return

    # Update DataFolder expression to point to the Data/ directory
    expr_path = os.path.join(
        project_dir, f'{source_basename}.SemanticModel', 'definition', 'expressions.tmdl')
    if os.path.isfile(expr_path):
        data_abs = os.path.abspath(data_dir).replace('\\', '\\\\')
        try:
            with open(expr_path, 'r', encoding='utf-8') as f:
                content = f.read()
            import re as _re
            content = _re.sub(
                r'(expression DataFolder = )"[^"]*"',
                rf'\1"{data_abs}"',
                content,
            )
            with open(expr_path, 'w', encoding='utf-8') as f:
                f.write(content)
        except OSError as exc:
            logger.warning("Could not update DataFolder expression: %s", exc)

    print(f"  📁 Extracted {len(extracted_files)} data file(s) from TWBX into {data_dir}")

    # Resolve embedded image references in visual.json files to base64 data URIs
    import base64 as _b64
    import glob as _glob
    _MIME_MAP = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                 '.gif': 'image/gif', '.svg': 'image/svg+xml', '.bmp': 'image/bmp'}
    report_dir = os.path.join(project_dir, f'{source_basename}.Report', 'definition')
    for vj_path in _glob.glob(os.path.join(report_dir, 'pages', '*', 'visuals', '*', 'visual.json')):
        try:
            with open(vj_path, 'r', encoding='utf-8') as f:
                vj = json.load(f)
            gen_props = (vj.get('visual', {}).get('objects', {}).get('general', [{}])[0]
                         .get('properties', {}))
            url_obj = gen_props.get('imageUrl', {})
            url_val = url_obj.get('expr', {}).get('Literal', {}).get('Value', '')
            # Strip surrounding quotes
            img_ref = url_val.strip("'\"")
            if not img_ref or img_ref.startswith(('http://', 'https://', 'data:')):
                continue
            # Try to find the image in extracted Data directory
            img_file = os.path.join(data_dir, img_ref)
            if os.path.isfile(img_file):
                ext = os.path.splitext(img_ref)[1].lower()
                mime = _MIME_MAP.get(ext, 'application/octet-stream')
                with open(img_file, 'rb') as f:
                    b64 = _b64.b64encode(f.read()).decode('ascii')
                data_uri = f'data:{mime};base64,{b64}'
                gen_props['imageUrl'] = {"expr": {"Literal": {"Value": f"'{data_uri}'"}}}
                with open(vj_path, 'w', encoding='utf-8') as f:
                    json.dump(vj, f, indent=2, ensure_ascii=False)
        except (OSError, KeyError, IndexError, json.JSONDecodeError):
            continue


def _run_post_generation_reports(args, source_basename, results):
    """Run comparison report and telemetry dashboard if requested."""
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
        except (ImportError, OSError, ValueError) as exc:
            logger.warning(f"Comparison report generation failed: {exc}")

    if getattr(args, 'dashboard', False) and results.get('generation') and not args.dry_run:
        try:
            from powerbi_import.telemetry_dashboard import generate_dashboard as gen_telem_dashboard
            out_base = args.output_dir or os.path.join('artifacts', 'powerbi_projects', 'migrated')
            dash_path = gen_telem_dashboard(out_base)
            if dash_path:
                print(f"\n📊 Telemetry dashboard: {dash_path}")
        except (ImportError, OSError, ValueError) as exc:
            logger.warning(f"Telemetry dashboard generation failed: {exc}")


def _run_deploy_to_pbi_service(args, source_basename):
    """Deploy generated project to Power BI Service."""
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
        logger.error("Deployment failed: %s", exc, exc_info=True)


def _run_schedule_migration(args, source_basename):
    """Extract Tableau refresh schedules and generate PBI refresh config."""
    try:
        from powerbi_import.refresh_generator import generate_refresh_json
        print_header("REFRESH SCHEDULE MIGRATION")
        out_dir = args.output_dir or os.path.join('artifacts', 'powerbi_projects', 'migrated')
        project_dir = os.path.join(out_dir, source_basename)

        extract_tasks = []
        subscriptions = []
        schedules = []

        # Try to fetch from server if connected
        if getattr(args, 'server', None) and getattr(args, '_server_workbook_id', None):
            try:
                from tableau_export.server_client import TableauServerClient
                ts_client = TableauServerClient(
                    server_url=args.server,
                    token_name=getattr(args, 'token_name', None),
                    token_secret=getattr(args, 'token_secret', None) or os.environ.get('TABLEAU_TOKEN_SECRET'),
                    site_id=getattr(args, 'site', ''),
                )
                ts_client.sign_in()
                wb_id = args._server_workbook_id
                extract_tasks = ts_client.get_workbook_extract_tasks(wb_id)
                subscriptions = ts_client.get_workbook_subscriptions(wb_id)
                schedules = ts_client.list_schedules()
                ts_client.sign_out()
                print(f"  Extract tasks: {len(extract_tasks)}")
                print(f"  Subscriptions: {len(subscriptions)}")
            except Exception as exc:
                print(f"  ⚠ Could not fetch schedules from server: {exc}")
                logger.warning("Schedule fetch failed: %s", exc)

        config = generate_refresh_json(extract_tasks, subscriptions, schedules)

        # Write to project dir
        config_path = os.path.join(project_dir, 'refresh_config.json')
        os.makedirs(project_dir, exist_ok=True)
        import json as _json
        with open(config_path, 'w', encoding='utf-8') as f:
            _json.dump(config, f, indent=2)
        print(f"  ✓ Refresh config: {config_path}")

        for note in config.get('migration_notes', []):
            print(f"  ℹ {note}")
        for note in config.get('refresh', {}).get('notes', []):
            print(f"  ⚠ {note}")

    except Exception as exc:
        print(f"  ✗ Schedule migration error: {exc}")
        logger.error("Schedule migration failed: %s", exc, exc_info=True)


def _run_single_migration(args):
    """Execute the full single-file migration pipeline.

    Handles extraction, generation, incremental merge, goals, reports,
    and optional deployment for a single Tableau workbook.
    """
    _print_single_migration_header(args)

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

    telemetry = _init_telemetry(args)

    # Step 1: Extraction
    progress.start("Extracting Tableau data")
    if not args.skip_extraction:
        results['extraction'] = run_extraction(
            args.tableau_file,
            hyper_max_rows=getattr(args, 'hyper_rows', None),
        )
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
            # Extract embedded data files from TWBX into PBI output
            _extract_twbx_data_files(args, source_basename)
        else:
            progress.fail("Generation failed")

    # Step 3: Incremental merge (optional)
    if getattr(args, 'incremental', None) and results.get('generation'):
        _run_incremental_merge(args, source_basename)

    # Step 3b: Goals/Scorecard generation (optional, --goals flag)
    if getattr(args, 'goals', False) and results.get('generation'):
        _run_goals_generation(args, source_basename)

    # Step 3c: Governance checks (optional, --governance flag)
    if getattr(args, 'governance', None) and results.get('generation'):
        _run_governance_checks(args, source_basename)

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

    # Step 4c–4d: Comparison report and telemetry dashboard (optional)
    _run_post_generation_reports(args, source_basename, results)

    # Step 5: Deploy to Power BI Service (optional)
    if getattr(args, 'deploy', None) and results.get('generation') and not args.dry_run:
        _run_deploy_to_pbi_service(args, source_basename)

    # Step 5b: Migrate refresh schedules (optional, requires --server + --migrate-schedules)
    if getattr(args, 'migrate_schedules', False) and results.get('generation'):
        _run_schedule_migration(args, source_basename)

    # Final report
    all_success = _print_migration_summary(results, report_summary, start_time)

    _finalize_telemetry(telemetry, all_success, results)

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
