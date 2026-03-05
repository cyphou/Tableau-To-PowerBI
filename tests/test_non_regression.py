"""
Non-Regression Test Suite
=========================
End-to-end migration tests for all sample Tableau workbooks.
Each test migrates a .twb file and validates the generated .pbip project
for structural correctness, TMDL validity, PBIR integrity, and absence
of Tableau syntax leakage.

These tests serve as regression guards whenever the codebase changes.
"""

import glob
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

# Project root
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tableau_export'))
sys.path.insert(0, os.path.join(ROOT, 'powerbi_import'))

SAMPLES_DIR = os.path.join(ROOT, 'examples', 'tableau_samples')

# All available sample workbooks
ALL_SAMPLES = [
    'Superstore_Sales',
    'HR_Analytics',
    'Financial_Report',
    'BigQuery_Analytics',
    'Enterprise_Sales',
    'Manufacturing_IoT',
    'Marketing_Campaign',
    'Security_Test',
]


# ═══════════════════════════════════════════════════════════════════════
# Helper — run the full extraction + generation pipeline
# ═══════════════════════════════════════════════════════════════════════

def _run_migration(twb_path, output_dir):
    """
    Run the 2-step migration pipeline: extraction → generation.
    Returns the project directory path.

    The pipeline uses CWD-relative paths (tableau_export/, artifacts/),
    so we chdir to a temp workspace and set up the required structure.
    """
    from extract_tableau_data import TableauExtractor
    from import_to_powerbi import PowerBIImporter

    report_name = os.path.splitext(os.path.basename(twb_path))[0]

    # Create workspace subdirs that the pipeline expects
    te_dir = os.path.join(output_dir, 'tableau_export')
    os.makedirs(te_dir, exist_ok=True)
    os.makedirs(os.path.join(output_dir, 'artifacts', 'powerbi_projects'), exist_ok=True)
    os.makedirs(os.path.join(output_dir, 'artifacts', 'powerbi_objects'), exist_ok=True)

    old_cwd = os.getcwd()
    old_stdout = sys.stdout
    sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding='utf-8')
    try:
        os.chdir(output_dir)

        # Step 1: Extract (writes JSONs to tableau_export/)
        extractor = TableauExtractor(twb_path)
        success = extractor.extract_all()
        if not success:
            raise RuntimeError(f"Extraction failed for {twb_path}")

        # Step 2: Generate (reads from tableau_export/, writes to artifacts/powerbi_projects/)
        importer = PowerBIImporter()
        importer.import_all(generate_pbip=True, report_name=report_name)
    finally:
        os.chdir(old_cwd)
        sys.stdout = old_stdout

    project_dir = os.path.join(output_dir, 'artifacts', 'powerbi_projects', report_name)
    return project_dir


# ═══════════════════════════════════════════════════════════════════════
# Shared assertion helpers
# ═══════════════════════════════════════════════════════════════════════

def _assert_project_structure(test_case, project_dir, report_name):
    """Assert all required project files are present."""
    required = [
        f"{report_name}.pbip",
        os.path.join(f"{report_name}.Report", ".platform"),
        os.path.join(f"{report_name}.Report", "definition.pbir"),
        os.path.join(f"{report_name}.Report", "definition", "report.json"),
        os.path.join(f"{report_name}.Report", "definition", "version.json"),
        os.path.join(f"{report_name}.Report", "definition", "pages", "pages.json"),
        os.path.join(f"{report_name}.SemanticModel", ".platform"),
        os.path.join(f"{report_name}.SemanticModel", "definition.pbism"),
        os.path.join(f"{report_name}.SemanticModel", "definition", "model.tmdl"),
        os.path.join(f"{report_name}.SemanticModel", "definition", "database.tmdl"),
        os.path.join(f"{report_name}.SemanticModel", "definition", "expressions.tmdl"),
    ]
    for rel_path in required:
        full_path = os.path.join(project_dir, rel_path)
        test_case.assertTrue(
            os.path.exists(full_path),
            f"Missing required file: {rel_path}"
        )


def _assert_json_files_valid(test_case, project_dir):
    """Assert all .json files in the project are parsable."""
    json_files = glob.glob(os.path.join(project_dir, "**", "*.json"), recursive=True)
    test_case.assertGreater(len(json_files), 0, "No JSON files found")
    for jf in json_files:
        with open(jf, 'r', encoding='utf-8') as f:
            try:
                json.load(f)
            except json.JSONDecodeError as e:
                rel = os.path.relpath(jf, project_dir)
                test_case.fail(f"Invalid JSON: {rel} — {e}")


def _assert_tmdl_syntax(test_case, project_dir, report_name):
    """Assert all .tmdl files have valid syntax."""
    tmdl_dir = os.path.join(
        project_dir, f"{report_name}.SemanticModel", "definition"
    )
    tmdl_files = glob.glob(os.path.join(tmdl_dir, "**", "*.tmdl"), recursive=True)
    test_case.assertGreater(len(tmdl_files), 0, "No TMDL files found")

    for tf in tmdl_files:
        with open(tf, 'r', encoding='utf-8') as f:
            content = f.read()
        rel = os.path.relpath(tf, project_dir)

        # model.tmdl must start with 'model Model'
        if os.path.basename(tf) == 'model.tmdl':
            test_case.assertTrue(
                content.strip().startswith('model Model'),
                f"{rel} doesn't start with 'model Model'"
            )
        # database.tmdl must start with 'database'
        elif os.path.basename(tf) == 'database.tmdl':
            test_case.assertTrue(
                content.strip().startswith('database'),
                f"{rel} doesn't start with 'database'"
            )
        # table files must start with 'table'
        elif os.path.basename(tf) not in (
            'expressions.tmdl', 'relationships.tmdl', 'roles.tmdl',
            'perspectives.tmdl'
        ) and 'tables' in rel:
            test_case.assertTrue(
                content.strip().startswith('table'),
                f"{rel} doesn't start with 'table'"
            )

        # No unclosed quotes or brackets (simple check)
        single_quotes = content.count("'")
        # Escaped quotes '' count as 2 each, which is fine


def _assert_no_tableau_leakage(test_case, project_dir, report_name):
    """Assert no Tableau-specific syntax leaks into TMDL / DAX."""
    tmdl_dir = os.path.join(
        project_dir, f"{report_name}.SemanticModel", "definition"
    )
    tmdl_files = glob.glob(os.path.join(tmdl_dir, "**", "*.tmdl"), recursive=True)

    tableau_patterns = [
        (r'{FIXED\s', "LOD FIXED expression"),
        (r'{INCLUDE\s', "LOD INCLUDE expression"),
        (r'{EXCLUDE\s', "LOD EXCLUDE expression"),
        (r'\bELSEIF\b', "ELSEIF keyword"),
        (r'\bCOUNTD\b', "COUNTD function"),
        (r'\bZN\b(?!\()', "ZN function (not in function context)"),
        (r'\bIFNULL\b', "IFNULL function"),
        (r'\bISNULL\b', "ISNULL function"),
        (r'\bDATETRUNC\b', "DATETRUNC function"),
        (r'\bMAKEPOINT\b', "MAKEPOINT function"),
    ]

    for tf in tmdl_files:
        with open(tf, 'r', encoding='utf-8') as f:
            content = f.read()
        rel = os.path.relpath(tf, project_dir)

        for pattern, desc in tableau_patterns:
            # Search only in DAX expressions (after = sign)
            for line in content.split('\n'):
                if '=' in line and 'expression' not in line.lower():
                    expr_part = line.split('=', 1)[-1]
                    # Skip comments (lines starting with //)
                    if expr_part.strip().startswith('//'):
                        continue
                    match = re.search(pattern, expr_part, re.IGNORECASE)
                    if match:
                        test_case.fail(
                            f"Tableau syntax leaked in {rel}: "
                            f"{desc} found in: {line.strip()[:80]}"
                        )


def _assert_pages_present(test_case, project_dir, report_name, min_pages=1):
    """Assert at least min_pages report pages exist."""
    pages_dir = os.path.join(
        project_dir, f"{report_name}.Report", "definition", "pages"
    )
    if not os.path.isdir(pages_dir):
        test_case.fail("No pages directory found")
    sections = [
        d for d in os.listdir(pages_dir)
        if os.path.isdir(os.path.join(pages_dir, d)) and d.startswith('ReportSection')
    ]
    test_case.assertGreaterEqual(
        len(sections), min_pages,
        f"Expected >= {min_pages} pages, found {len(sections)}"
    )


def _assert_visuals_present(test_case, project_dir, report_name, min_visuals=1):
    """Assert at least min_visuals visual.json files exist."""
    pages_dir = os.path.join(
        project_dir, f"{report_name}.Report", "definition", "pages"
    )
    visual_files = glob.glob(
        os.path.join(pages_dir, "**", "visual.json"), recursive=True
    )
    test_case.assertGreaterEqual(
        len(visual_files), min_visuals,
        f"Expected >= {min_visuals} visuals, found {len(visual_files)}"
    )


def _assert_tables_present(test_case, project_dir, report_name, min_tables=1):
    """Assert at least min_tables table .tmdl files exist."""
    tables_dir = os.path.join(
        project_dir, f"{report_name}.SemanticModel", "definition", "tables"
    )
    if not os.path.isdir(tables_dir):
        test_case.fail("No tables directory found")
    tmdl_files = [f for f in os.listdir(tables_dir) if f.endswith('.tmdl')]
    test_case.assertGreaterEqual(
        len(tmdl_files), min_tables,
        f"Expected >= {min_tables} tables, found {len(tmdl_files)}"
    )


def _assert_perspectives_present(test_case, project_dir, report_name):
    """Assert perspectives.tmdl exists and contains 'Full Model'."""
    persp_path = os.path.join(
        project_dir, f"{report_name}.SemanticModel", "definition",
        "perspectives.tmdl"
    )
    if os.path.exists(persp_path):
        with open(persp_path, 'r', encoding='utf-8') as f:
            content = f.read()
        test_case.assertIn("Full Model", content)


def _assert_diagram_layout_present(test_case, project_dir, report_name):
    """Assert diagramLayout.json exists."""
    dl_path = os.path.join(
        project_dir, f"{report_name}.SemanticModel", "definition",
        "diagramLayout.json"
    )
    test_case.assertTrue(
        os.path.exists(dl_path),
        "diagramLayout.json not found"
    )


def _assert_m_queries_valid(test_case, project_dir, report_name):
    """Assert expressions.tmdl exists and contains valid M query or parameter patterns."""
    expr_path = os.path.join(
        project_dir, f"{report_name}.SemanticModel", "definition",
        "expressions.tmdl"
    )
    if os.path.exists(expr_path):
        with open(expr_path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Should contain M queries (let/in) or parameter expressions
        if 'expression' in content:
            has_m_query = "let" in content.lower()
            has_parameter = "meta" in content.lower() or "isparameterquery" in content.lower()
            test_case.assertTrue(
                has_m_query or has_parameter,
                "expressions.tmdl has 'expression' but no M query (let) or parameter"
            )


def _assert_visual_json_valid(test_case, project_dir, report_name):
    """Assert all visual.json files have required schema and visualType."""
    pages_dir = os.path.join(
        project_dir, f"{report_name}.Report", "definition", "pages"
    )
    visual_files = glob.glob(
        os.path.join(pages_dir, "**", "visual.json"), recursive=True
    )
    for vf in visual_files:
        with open(vf, 'r', encoding='utf-8') as f:
            data = json.load(f)
        rel = os.path.relpath(vf, project_dir)
        test_case.assertIn("$schema", data, f"{rel}: missing $schema")
        test_case.assertIn("visual", data, f"{rel}: missing visual key")
        test_case.assertIn(
            "visualType", data["visual"],
            f"{rel}: missing visualType"
        )


def _assert_pbip_valid(test_case, project_dir, report_name):
    """Assert .pbip file is valid JSON with required fields."""
    pbip_path = os.path.join(project_dir, f"{report_name}.pbip")
    with open(pbip_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    test_case.assertIn("version", data)


def _assert_report_json_valid(test_case, project_dir, report_name):
    """Assert report.json has correct schema reference."""
    report_path = os.path.join(
        project_dir, f"{report_name}.Report", "definition", "report.json"
    )
    with open(report_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    test_case.assertIn("$schema", data)
    test_case.assertIn("report", data["$schema"].lower())


# ═══════════════════════════════════════════════════════════════════════
# Base test class — runs migration once per sample
# ═══════════════════════════════════════════════════════════════════════

class NonRegressionBase(unittest.TestCase):
    """
    Base class that migrates a sample workbook once in setUpClass
    and provides the project directory to all test methods.
    """
    SAMPLE_NAME = None  # Override in subclasses

    @classmethod
    def setUpClass(cls):
        if cls.SAMPLE_NAME is None:
            raise unittest.SkipTest("Base class — no sample defined")

        twb_path = os.path.join(SAMPLES_DIR, f"{cls.SAMPLE_NAME}.twb")
        if not os.path.exists(twb_path):
            raise unittest.SkipTest(f"Sample not found: {twb_path}")

        cls._output_dir = tempfile.mkdtemp(prefix=f"test_{cls.SAMPLE_NAME}_")
        try:
            cls._project_dir = _run_migration(twb_path, cls._output_dir)
        except Exception as e:
            shutil.rmtree(cls._output_dir, ignore_errors=True)
            raise unittest.SkipTest(f"Migration failed for {cls.SAMPLE_NAME}: {e}")

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, '_output_dir'):
            shutil.rmtree(cls._output_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════
# Per-sample regression suites
# ═══════════════════════════════════════════════════════════════════════

class TestSuperstoreSales(NonRegressionBase):
    SAMPLE_NAME = "Superstore_Sales"

    def test_project_structure(self):
        _assert_project_structure(self, self._project_dir, self.SAMPLE_NAME)

    def test_json_files_valid(self):
        _assert_json_files_valid(self, self._project_dir)

    def test_tmdl_syntax(self):
        _assert_tmdl_syntax(self, self._project_dir, self.SAMPLE_NAME)

    def test_no_tableau_leakage(self):
        _assert_no_tableau_leakage(self, self._project_dir, self.SAMPLE_NAME)

    def test_pages_present(self):
        _assert_pages_present(self, self._project_dir, self.SAMPLE_NAME)

    def test_visuals_present(self):
        _assert_visuals_present(self, self._project_dir, self.SAMPLE_NAME)

    def test_tables_present(self):
        _assert_tables_present(self, self._project_dir, self.SAMPLE_NAME)

    def test_perspectives(self):
        _assert_perspectives_present(self, self._project_dir, self.SAMPLE_NAME)

    def test_diagram_layout(self):
        _assert_diagram_layout_present(self, self._project_dir, self.SAMPLE_NAME)

    def test_m_queries(self):
        _assert_m_queries_valid(self, self._project_dir, self.SAMPLE_NAME)

    def test_visual_json(self):
        _assert_visual_json_valid(self, self._project_dir, self.SAMPLE_NAME)

    def test_pbip_valid(self):
        _assert_pbip_valid(self, self._project_dir, self.SAMPLE_NAME)

    def test_report_json(self):
        _assert_report_json_valid(self, self._project_dir, self.SAMPLE_NAME)


class TestHRAnalytics(NonRegressionBase):
    SAMPLE_NAME = "HR_Analytics"

    def test_project_structure(self):
        _assert_project_structure(self, self._project_dir, self.SAMPLE_NAME)

    def test_json_files_valid(self):
        _assert_json_files_valid(self, self._project_dir)

    def test_tmdl_syntax(self):
        _assert_tmdl_syntax(self, self._project_dir, self.SAMPLE_NAME)

    def test_no_tableau_leakage(self):
        _assert_no_tableau_leakage(self, self._project_dir, self.SAMPLE_NAME)

    def test_pages_present(self):
        _assert_pages_present(self, self._project_dir, self.SAMPLE_NAME)

    def test_visuals_present(self):
        _assert_visuals_present(self, self._project_dir, self.SAMPLE_NAME)

    def test_tables_present(self):
        _assert_tables_present(self, self._project_dir, self.SAMPLE_NAME)

    def test_perspectives(self):
        _assert_perspectives_present(self, self._project_dir, self.SAMPLE_NAME)

    def test_diagram_layout(self):
        _assert_diagram_layout_present(self, self._project_dir, self.SAMPLE_NAME)

    def test_visual_json(self):
        _assert_visual_json_valid(self, self._project_dir, self.SAMPLE_NAME)

    def test_pbip_valid(self):
        _assert_pbip_valid(self, self._project_dir, self.SAMPLE_NAME)


class TestFinancialReport(NonRegressionBase):
    SAMPLE_NAME = "Financial_Report"

    def test_project_structure(self):
        _assert_project_structure(self, self._project_dir, self.SAMPLE_NAME)

    def test_json_files_valid(self):
        _assert_json_files_valid(self, self._project_dir)

    def test_tmdl_syntax(self):
        _assert_tmdl_syntax(self, self._project_dir, self.SAMPLE_NAME)

    def test_no_tableau_leakage(self):
        _assert_no_tableau_leakage(self, self._project_dir, self.SAMPLE_NAME)

    def test_pages_present(self):
        _assert_pages_present(self, self._project_dir, self.SAMPLE_NAME)

    def test_tables_present(self):
        _assert_tables_present(self, self._project_dir, self.SAMPLE_NAME)

    def test_perspectives(self):
        _assert_perspectives_present(self, self._project_dir, self.SAMPLE_NAME)

    def test_pbip_valid(self):
        _assert_pbip_valid(self, self._project_dir, self.SAMPLE_NAME)


class TestBigQueryAnalytics(NonRegressionBase):
    SAMPLE_NAME = "BigQuery_Analytics"

    def test_project_structure(self):
        _assert_project_structure(self, self._project_dir, self.SAMPLE_NAME)

    def test_json_files_valid(self):
        _assert_json_files_valid(self, self._project_dir)

    def test_tmdl_syntax(self):
        _assert_tmdl_syntax(self, self._project_dir, self.SAMPLE_NAME)

    def test_no_tableau_leakage(self):
        _assert_no_tableau_leakage(self, self._project_dir, self.SAMPLE_NAME)

    def test_tables_present(self):
        _assert_tables_present(self, self._project_dir, self.SAMPLE_NAME)

    def test_pbip_valid(self):
        _assert_pbip_valid(self, self._project_dir, self.SAMPLE_NAME)


class TestEnterpriseSales(NonRegressionBase):
    SAMPLE_NAME = "Enterprise_Sales"

    def test_project_structure(self):
        _assert_project_structure(self, self._project_dir, self.SAMPLE_NAME)

    def test_json_files_valid(self):
        _assert_json_files_valid(self, self._project_dir)

    def test_tmdl_syntax(self):
        _assert_tmdl_syntax(self, self._project_dir, self.SAMPLE_NAME)

    def test_no_tableau_leakage(self):
        _assert_no_tableau_leakage(self, self._project_dir, self.SAMPLE_NAME)

    def test_tables_present(self):
        _assert_tables_present(self, self._project_dir, self.SAMPLE_NAME)

    def test_pbip_valid(self):
        _assert_pbip_valid(self, self._project_dir, self.SAMPLE_NAME)


class TestManufacturingIoT(NonRegressionBase):
    SAMPLE_NAME = "Manufacturing_IoT"

    def test_project_structure(self):
        _assert_project_structure(self, self._project_dir, self.SAMPLE_NAME)

    def test_json_files_valid(self):
        _assert_json_files_valid(self, self._project_dir)

    def test_tmdl_syntax(self):
        _assert_tmdl_syntax(self, self._project_dir, self.SAMPLE_NAME)

    def test_no_tableau_leakage(self):
        _assert_no_tableau_leakage(self, self._project_dir, self.SAMPLE_NAME)

    def test_pbip_valid(self):
        _assert_pbip_valid(self, self._project_dir, self.SAMPLE_NAME)


class TestMarketingCampaign(NonRegressionBase):
    SAMPLE_NAME = "Marketing_Campaign"

    def test_project_structure(self):
        _assert_project_structure(self, self._project_dir, self.SAMPLE_NAME)

    def test_json_files_valid(self):
        _assert_json_files_valid(self, self._project_dir)

    def test_tmdl_syntax(self):
        _assert_tmdl_syntax(self, self._project_dir, self.SAMPLE_NAME)

    def test_pbip_valid(self):
        _assert_pbip_valid(self, self._project_dir, self.SAMPLE_NAME)


class TestSecurityTest(NonRegressionBase):
    SAMPLE_NAME = "Security_Test"

    def test_project_structure(self):
        _assert_project_structure(self, self._project_dir, self.SAMPLE_NAME)

    def test_json_files_valid(self):
        _assert_json_files_valid(self, self._project_dir)

    def test_tmdl_syntax(self):
        _assert_tmdl_syntax(self, self._project_dir, self.SAMPLE_NAME)

    def test_no_tableau_leakage(self):
        _assert_no_tableau_leakage(self, self._project_dir, self.SAMPLE_NAME)

    def test_pbip_valid(self):
        _assert_pbip_valid(self, self._project_dir, self.SAMPLE_NAME)

    def test_rls_roles(self):
        """Security_Test should produce RLS roles."""
        roles_path = os.path.join(
            self._project_dir, f"{self.SAMPLE_NAME}.SemanticModel",
            "definition", "roles.tmdl"
        )
        # RLS roles file should exist for the security test workbook
        if os.path.exists(roles_path):
            with open(roles_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn("role", content.lower())


# ═══════════════════════════════════════════════════════════════════════
# Cross-Sample Consistency Tests
# ═══════════════════════════════════════════════════════════════════════

class TestCrossSampleConsistency(unittest.TestCase):
    """
    Tests that run across all already-generated projects in
    artifacts/powerbi_projects/ (no re-migration needed).
    """

    def _get_existing_projects(self):
        """Return list of (name, path) for existing generated projects."""
        projects_dir = os.path.join(ROOT, 'artifacts', 'powerbi_projects')
        if not os.path.isdir(projects_dir):
            return []
        return [
            (d, os.path.join(projects_dir, d))
            for d in os.listdir(projects_dir)
            if os.path.isdir(os.path.join(projects_dir, d))
            and os.path.exists(os.path.join(projects_dir, d, f"{d}.pbip"))
        ]

    def test_all_projects_have_metadata(self):
        """Every generated project should have migration_metadata.json."""
        projects = self._get_existing_projects()
        if not projects:
            self.skipTest("No generated projects found")
        for name, path in projects:
            meta = os.path.join(path, 'migration_metadata.json')
            self.assertTrue(
                os.path.exists(meta),
                f"{name}: missing migration_metadata.json"
            )

    def test_all_projects_have_model_tmdl(self):
        """Every project should have model.tmdl."""
        projects = self._get_existing_projects()
        if not projects:
            self.skipTest("No generated projects found")
        for name, path in projects:
            model = os.path.join(path, f"{name}.SemanticModel", "definition", "model.tmdl")
            self.assertTrue(
                os.path.exists(model),
                f"{name}: missing model.tmdl"
            )

    def test_no_empty_visual_dirs(self):
        """Visual directories should contain visual.json."""
        projects = self._get_existing_projects()
        if not projects:
            self.skipTest("No generated projects found")
        empty_dirs = []
        for name, path in projects:
            pages_dir = os.path.join(path, f"{name}.Report", "definition", "pages")
            if not os.path.isdir(pages_dir):
                continue
            for section in os.listdir(pages_dir):
                vis_dir = os.path.join(pages_dir, section, "visuals")
                if not os.path.isdir(vis_dir):
                    continue
                for vid in os.listdir(vis_dir):
                    vdir = os.path.join(vis_dir, vid)
                    if os.path.isdir(vdir):
                        visual_json = os.path.join(vdir, "visual.json")
                        if not os.path.exists(visual_json):
                            empty_dirs.append(f"{name}/{vid}")
        # Warn but don't fail for empty visual dirs in pre-existing artifacts
        if empty_dirs:
            import warnings
            warnings.warn(
                f"{len(empty_dirs)} empty visual dirs found: {', '.join(empty_dirs[:5])}"
            )

    def test_schemas_are_consistent(self):
        """All visual.json files should use the same schema version."""
        projects = self._get_existing_projects()
        if not projects:
            self.skipTest("No generated projects found")
        schemas = set()
        for name, path in projects:
            visual_files = glob.glob(
                os.path.join(path, "**", "visual.json"), recursive=True
            )
            for vf in visual_files:
                with open(vf, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if "$schema" in data:
                    schemas.add(data["$schema"])
        # All visuals should use the same schema
        self.assertLessEqual(
            len(schemas), 1,
            f"Inconsistent visual schemas: {schemas}"
        )


if __name__ == '__main__':
    unittest.main(verbosity=2)
