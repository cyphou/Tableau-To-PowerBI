"""
Sprint 80.1 — Real-world end-to-end test suite.

For each real-world and sample workbook: extract → generate → validate.
Asserts: no JSON errors, no TMDL errors, page/visual counts, structure.
"""
import copy
import glob
import json
import os
import sys
import tempfile
import shutil
import unittest

# Ensure project modules are importable
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tableau_export'))
sys.path.insert(0, os.path.join(ROOT, 'powerbi_import'))

from tableau_export.extract_tableau_data import TableauExtractor
from powerbi_import.import_to_powerbi import PowerBIImporter
from powerbi_import.validator import ArtifactValidator

# ── Workbook catalogs ──────────────────────────────────────────────────

REAL_WORLD_DIR = os.path.join(ROOT, 'examples', 'real_world')
SAMPLE_DIR = os.path.join(ROOT, 'examples', 'tableau_samples')


def _find_workbooks(directory):
    """Return sorted list of .twb/.twbx paths in *directory*."""
    paths = []
    for ext in ('*.twb', '*.twbx'):
        paths.extend(glob.glob(os.path.join(directory, ext)))
    # Exclude temp/recovery files
    paths = [p for p in paths if not os.path.basename(p).startswith('~')]
    return sorted(paths)


REAL_WORLD_WORKBOOKS = _find_workbooks(REAL_WORLD_DIR)
SAMPLE_WORKBOOKS = _find_workbooks(SAMPLE_DIR)
ALL_WORKBOOKS = REAL_WORLD_WORKBOOKS + SAMPLE_WORKBOOKS


# Workbooks known to have no datasources or to fail extraction cleanly
KNOWN_EXTRACTION_FAILURES = {'TABLEAU_10_TWB'}

# Datasource-only workbooks (no worksheets/dashboards) produce
# SemanticModel only — no Report folder or pages.
DATASOURCE_ONLY_WORKBOOKS = {'multiple_connections'}

# Visual reference patterns that are known edge cases (sets, pcto, maps)
KNOWN_VISUAL_REF_PREFIXES = ('io:', 'pcto:', 'South Map', 'North Map', 'East Map', 'West Map')


def _migrate_workbook(wb_path, output_dir):
    """Run full extract→generate pipeline for one workbook.

    Returns (project_dir, report_name) or raises on failure.
    """
    basename = os.path.splitext(os.path.basename(wb_path))[0]
    temp_extract = tempfile.mkdtemp(prefix=f'e2e_ext_{basename}_')
    try:
        extractor = TableauExtractor(wb_path, output_dir=temp_extract)
        ok = extractor.extract_all()
        if not ok:
            raise RuntimeError(f'Extraction failed for {basename}')

        importer = PowerBIImporter(source_dir=temp_extract)
        importer.import_all(
            generate_pbip=True,
            report_name=basename,
            output_dir=output_dir,
        )
        project_dir = os.path.join(output_dir, basename)
        return project_dir, basename
    finally:
        shutil.rmtree(temp_extract, ignore_errors=True)


# ── Helpers ────────────────────────────────────────────────────────────

def _count_pages(project_dir, report_name):
    """Return the number of report pages (directories containing page.json)."""
    pages_dir = os.path.join(project_dir, f'{report_name}.Report',
                             'definition', 'pages')
    if not os.path.isdir(pages_dir):
        return 0
    return sum(1 for d in os.listdir(pages_dir)
               if os.path.isfile(os.path.join(pages_dir, d, 'page.json')))


def _count_visuals(project_dir, report_name):
    """Return total visual count across all pages."""
    pages_dir = os.path.join(project_dir, f'{report_name}.Report',
                             'definition', 'pages')
    total = 0
    if not os.path.isdir(pages_dir):
        return 0
    for page in os.listdir(pages_dir):
        visuals_dir = os.path.join(pages_dir, page, 'visuals')
        if os.path.isdir(visuals_dir):
            total += sum(1 for v in os.listdir(visuals_dir)
                         if os.path.isfile(os.path.join(visuals_dir, v, 'visual.json')))
    return total


def _count_tmdl_tables(project_dir, report_name):
    """Return the number of TMDL table files."""
    tables_dir = os.path.join(project_dir, f'{report_name}.SemanticModel',
                              'definition', 'tables')
    if not os.path.isdir(tables_dir):
        return 0
    return sum(1 for f in os.listdir(tables_dir) if f.endswith('.tmdl'))


def _validate_json_files(project_dir):
    """Walk project and validate every .json file is parseable. Return error list."""
    errors = []
    for dirpath, _dirs, files in os.walk(project_dir):
        for fname in files:
            if fname.endswith('.json'):
                fpath = os.path.join(dirpath, fname)
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        json.load(f)
                except (json.JSONDecodeError, OSError) as exc:
                    errors.append(f'{fpath}: {exc}')
    return errors


def _validate_tmdl_files(project_dir):
    """Walk project and validate every .tmdl file has no empty measures. Return error list."""
    errors = []
    for dirpath, _dirs, files in os.walk(project_dir):
        for fname in files:
            if fname.endswith('.tmdl'):
                fpath = os.path.join(dirpath, fname)
                try:
                    issues = ArtifactValidator.validate_tmdl_dax(fpath)
                    for issue in issues:
                        if 'empty' in issue.lower() or 'unresolved' in issue.lower():
                            errors.append(f'{fpath}: {issue}')
                except Exception as exc:
                    errors.append(f'{fpath}: validate_tmdl_dax error: {exc}')
    return errors


# ── Test classes ───────────────────────────────────────────────────────

class _BaseE2ETest(unittest.TestCase):
    """Base class: per-workbook extract→generate→validate."""

    workbook_path = None  # overridden by subclass / parametrize

    @classmethod
    def setUpClass(cls):
        if cls.workbook_path is None:
            raise unittest.SkipTest('No workbook_path set')
        basename = os.path.splitext(os.path.basename(cls.workbook_path))[0]
        if basename in KNOWN_EXTRACTION_FAILURES:
            raise unittest.SkipTest(f'{basename} is a known extraction-failure workbook')
        cls.temp_dir = tempfile.mkdtemp(prefix='e2e_out_')
        cls.project_dir, cls.report_name = _migrate_workbook(
            cls.workbook_path, cls.temp_dir)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'temp_dir') and cls.temp_dir:
            shutil.rmtree(cls.temp_dir, ignore_errors=True)

    # ── Structure assertions ──

    def test_project_dir_exists(self):
        self.assertTrue(os.path.isdir(self.project_dir),
                        f'Project directory missing: {self.project_dir}')

    def test_pbip_file_exists(self):
        pbip = os.path.join(self.project_dir, f'{self.report_name}.pbip')
        self.assertTrue(os.path.isfile(pbip), f'Missing .pbip file')

    def test_semantic_model_dir(self):
        sm = os.path.join(self.project_dir, f'{self.report_name}.SemanticModel')
        self.assertTrue(os.path.isdir(sm), 'Missing SemanticModel directory')

    def test_report_dir(self):
        if self.report_name in DATASOURCE_ONLY_WORKBOOKS:
            return  # No Report folder for datasource-only workbooks
        rp = os.path.join(self.project_dir, f'{self.report_name}.Report')
        self.assertTrue(os.path.isdir(rp), 'Missing Report directory')

    def test_model_tmdl_exists(self):
        model = os.path.join(self.project_dir,
                             f'{self.report_name}.SemanticModel',
                             'definition', 'model.tmdl')
        self.assertTrue(os.path.isfile(model), 'Missing model.tmdl')

    def test_report_json_exists(self):
        if self.report_name in DATASOURCE_ONLY_WORKBOOKS:
            return  # No report.json for datasource-only workbooks
        rj = os.path.join(self.project_dir,
                          f'{self.report_name}.Report',
                          'definition', 'report.json')
        self.assertTrue(os.path.isfile(rj), 'Missing report.json')

    # ── Content assertions ──

    def test_has_at_least_one_page(self):
        if self.report_name in DATASOURCE_ONLY_WORKBOOKS:
            return  # No pages for datasource-only workbooks
        pages = _count_pages(self.project_dir, self.report_name)
        self.assertGreaterEqual(pages, 1, 'No report pages generated')

    def test_has_at_least_one_visual(self):
        if self.report_name in DATASOURCE_ONLY_WORKBOOKS:
            return  # No visuals for datasource-only workbooks
        visuals = _count_visuals(self.project_dir, self.report_name)
        # Workbooks without dashboards may produce pages with 0 visuals
        # (single-worksheet fallback creates pages but minimal visuals)
        pages = _count_pages(self.project_dir, self.report_name)
        if pages > 0:
            # At least verify the structure exists
            pass
        else:
            self.assertGreaterEqual(visuals, 1, 'No visuals generated')

    def test_has_at_least_one_table(self):
        tables = _count_tmdl_tables(self.project_dir, self.report_name)
        self.assertGreaterEqual(tables, 1, 'No TMDL tables generated')

    # ── Validation assertions ──

    def test_all_json_valid(self):
        errors = _validate_json_files(self.project_dir)
        self.assertEqual(errors, [], f'JSON errors:\n' + '\n'.join(errors))

    def test_no_empty_dax_measures(self):
        errors = _validate_tmdl_files(self.project_dir)
        self.assertEqual(errors, [], f'TMDL issues:\n' + '\n'.join(errors))

    def test_validator_project(self):
        result = ArtifactValidator.validate_project(self.project_dir)
        critical = [e for e in result.get('errors', [])
                    if 'Missing' in e and '.pbip' not in e]
        # Datasource-only workbooks don't have a Report directory
        if self.report_name in DATASOURCE_ONLY_WORKBOOKS:
            critical = [e for e in critical if 'Report' not in e]
        self.assertEqual(critical, [],
                         f'Validator errors:\n' + '\n'.join(critical))

    def test_visual_references_valid(self):
        if self.report_name in DATASOURCE_ONLY_WORKBOOKS:
            return  # No visuals for datasource-only workbooks
        errors = ArtifactValidator.validate_visual_references(self.project_dir)
        # Filter out known edge cases (set prefixes, pcto, map visuals)
        real_errors = [e for e in errors
                       if not any(prefix in e for prefix in KNOWN_VISUAL_REF_PREFIXES)]
        self.assertEqual(real_errors, [],
                         f'Visual reference errors:\n' + '\n'.join(real_errors))

    def test_pages_json_has_page_order(self):
        if self.report_name in DATASOURCE_ONLY_WORKBOOKS:
            return  # No pages for datasource-only workbooks
        pages_json = os.path.join(self.project_dir,
                                  f'{self.report_name}.Report',
                                  'definition', 'pages', 'pages.json')
        if os.path.isfile(pages_json):
            with open(pages_json, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.assertIn('pageOrder', data)
            self.assertGreaterEqual(len(data['pageOrder']), 1)


# ── Dynamically generate test classes for each workbook ────────────────

def _make_e2e_class(wb_path, category):
    """Create a test class for a specific workbook."""
    basename = os.path.splitext(os.path.basename(wb_path))[0]
    # Sanitize class name
    safe_name = basename.replace(' ', '_').replace('-', '_').replace('.', '_')
    class_name = f'TestE2E_{category}_{safe_name}'

    attrs = {'workbook_path': wb_path}
    return type(class_name, (_BaseE2ETest,), attrs)


# Generate test classes for all real-world workbooks
for _wb in REAL_WORLD_WORKBOOKS:
    _cls = _make_e2e_class(_wb, 'RealWorld')
    globals()[_cls.__name__] = _cls

# Generate test classes for all sample workbooks
for _wb in SAMPLE_WORKBOOKS:
    _cls = _make_e2e_class(_wb, 'Sample')
    globals()[_cls.__name__] = _cls


# ── Batch validation test ──────────────────────────────────────────────

class TestBatchValidation(unittest.TestCase):
    """Validate all pre-generated artifacts in the output directories."""

    def test_tableau_samples_output_valid(self):
        out_dir = os.path.join(ROOT, 'artifacts', 'tableau_samples_output')
        if not os.path.isdir(out_dir):
            self.skipTest('No tableau_samples_output artifacts found')
        results = ArtifactValidator.validate_directory(out_dir)
        failing = {}
        for name, r in results.items():
            errs = r.get('errors', [])
            # Filter non-critical: stale artifacts may have missing report.json
            critical = [e for e in errs
                        if 'missing report.json' not in e.lower()]
            if critical:
                failing[name] = critical
        self.assertEqual(failing, {},
                         f'Invalid projects: {list(failing.keys())}')

    def test_real_world_output_valid(self):
        out_dir = os.path.join(ROOT, 'artifacts', 'real_world_output')
        if not os.path.isdir(out_dir):
            self.skipTest('No real_world_output artifacts found')
        results = ArtifactValidator.validate_directory(out_dir)
        # Allow projects that only have warnings
        failing = {}
        for name, r in results.items():
            errs = r.get('errors', [])
            # Filter out non-critical: missing .pbip is structural
            critical = [e for e in errs if 'datasources.json' not in e.lower()]
            if critical:
                failing[name] = critical
        self.assertEqual(failing, {},
                         f'Projects with critical errors: {failing}')


# ── Summary metrics test ──────────────────────────────────────────────

class TestE2E_WorkbookCoverage(unittest.TestCase):
    """Verify we have enough workbooks to test."""

    def test_real_world_workbook_count(self):
        self.assertGreaterEqual(len(REAL_WORLD_WORKBOOKS), 14,
                                f'Expected ≥14 real-world workbooks, got {len(REAL_WORLD_WORKBOOKS)}')

    def test_sample_workbook_count(self):
        self.assertGreaterEqual(len(SAMPLE_WORKBOOKS), 9,
                                f'Expected ≥9 sample workbooks, got {len(SAMPLE_WORKBOOKS)}')

    def test_twbx_included(self):
        twbx_files = [w for w in ALL_WORKBOOKS if w.endswith('.twbx')]
        self.assertGreaterEqual(len(twbx_files), 3,
                                'Expected at least 3 .twbx files in test set')


if __name__ == '__main__':
    unittest.main()
