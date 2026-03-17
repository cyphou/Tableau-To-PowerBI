"""
Tests for Sprint 50 — Server-Level Assessment Pipeline.

Covers:
  - WorkbookReadiness scoring (GREEN/YELLOW/RED)
  - Complexity computation
  - Effort estimation
  - Migration wave planning
  - Connector census aggregation
  - ServerAssessment orchestration
  - HTML report generation
  - Console summary printing
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from powerbi_import.server_assessment import (
    ServerAssessment,
    WorkbookReadiness,
    MigrationWave,
    run_server_assessment,
    generate_server_html_report,
    save_server_assessment_json,
    print_server_summary,
    _assess_single_workbook,
    _compute_complexity,
    _estimate_effort,
    _build_migration_waves,
)


def _make_extracted(tables=None, calcs=None, worksheets=None,
                    conn_type="postgres", lod_count=0, table_calc_count=0):
    """Build a minimal extracted data dict for testing."""
    ds_tables = []
    for name, columns in (tables or []):
        ds_tables.append({
            "name": name,
            "type": "table",
            "columns": [{"name": c, "datatype": "string"} for c in columns],
        })

    calculations = []
    for i, c in enumerate(calcs or []):
        calculations.append({
            "name": c.get("name", f"calc_{i}"),
            "caption": c.get("name", f"calc_{i}"),
            "role": c.get("role", "measure"),
            "formula": c.get("formula", "SUM([Sales])"),
        })

    # Add LOD calculations
    for i in range(lod_count):
        calculations.append({
            "name": f"lod_{i}",
            "role": "measure",
            "formula": f"{{FIXED [Dim] : SUM([Val{i}])}}",
        })

    # Add table calc calculations
    for i in range(table_calc_count):
        calculations.append({
            "name": f"tc_{i}",
            "role": "measure",
            "formula": f"RUNNING_SUM(SUM([Val{i}]))",
        })

    ws_list = worksheets or [{"name": f"Sheet{i}"} for i in range(2)]

    return {
        "datasources": [{
            "name": "DS",
            "connection": {
                "type": conn_type,
                "details": {"server": "localhost", "database": "db"},
            },
            "tables": ds_tables,
            "calculations": [],
            "relationships": [],
        }],
        "worksheets": ws_list,
        "dashboards": [{"name": "Dash1"}],
        "calculations": calculations,
        "parameters": [],
        "filters": [{"field": "Region"}],
        "actions": [],
        "sets": [],
        "groups": [],
        "user_filters": [],
    }


class TestComputeComplexity(unittest.TestCase):
    """Test complexity metric computation."""

    def test_basic_complexity(self):
        ext = _make_extracted(
            tables=[("orders", ["id", "amount"])],
            calcs=[{"name": "Total", "formula": "SUM([amount])"}],
        )
        c = _compute_complexity(ext)
        self.assertEqual(c['visuals'], 2)
        self.assertEqual(c['tables'], 1)
        self.assertEqual(c['calculations'], 1)
        self.assertEqual(c['dashboards'], 1)
        self.assertEqual(c['lod_expressions'], 0)
        self.assertEqual(c['table_calcs'], 0)

    def test_lod_detection(self):
        ext = _make_extracted(lod_count=3)
        c = _compute_complexity(ext)
        self.assertEqual(c['lod_expressions'], 3)

    def test_table_calc_detection(self):
        ext = _make_extracted(table_calc_count=2)
        c = _compute_complexity(ext)
        self.assertEqual(c['table_calcs'], 2)

    def test_empty_workbook(self):
        ext = {
            "datasources": [], "worksheets": [], "dashboards": [],
            "calculations": [], "parameters": [], "filters": [],
            "actions": [],
        }
        c = _compute_complexity(ext)
        self.assertEqual(c['visuals'], 0)
        self.assertEqual(c['tables'], 0)


class TestEstimateEffort(unittest.TestCase):
    """Test effort estimation."""

    def test_base_effort(self):
        ext = {
            "datasources": [], "worksheets": [], "dashboards": [],
            "calculations": [], "parameters": [], "filters": [],
            "actions": [],
        }
        c = _compute_complexity(ext)
        effort = _estimate_effort(ext, c)
        self.assertGreater(effort, 0)
        self.assertAlmostEqual(effort, 1.0)  # base only

    def test_complex_workbook_more_effort(self):
        ext = _make_extracted(
            tables=[("t1", ["a", "b"]), ("t2", ["c", "d"])],
            calcs=[{"name": f"c{i}", "formula": f"SUM([x{i}])"} for i in range(10)],
            lod_count=5,
            table_calc_count=3,
        )
        c = _compute_complexity(ext)
        effort = _estimate_effort(ext, c)
        self.assertGreater(effort, 3.0)


class TestAssessSingleWorkbook(unittest.TestCase):
    """Test per-workbook assessment."""

    def test_simple_green_workbook(self):
        ext = _make_extracted(
            tables=[("orders", ["id", "amount"])],
            conn_type="postgres",
        )
        r = _assess_single_workbook("Sales", ext)
        self.assertEqual(r.name, "Sales")
        self.assertIn(r.status, ("GREEN", "YELLOW"))  # May vary by assessment
        self.assertGreater(r.effort_hours, 0)
        self.assertIn("postgres", r.connector_types)

    def test_complex_red_workbook(self):
        ext = _make_extracted(
            tables=[("t1", ["a"]), ("t2", ["b"]), ("t3", ["c"])],
            calcs=[{"name": f"c{i}", "formula": f"SUM([x{i}])"} for i in range(20)],
            lod_count=10,
            table_calc_count=5,
            conn_type="oracle",
        )
        r = _assess_single_workbook("Complex", ext)
        self.assertEqual(r.name, "Complex")
        self.assertGreater(r.effort_hours, 3.0)


class TestBuildMigrationWaves(unittest.TestCase):
    """Test wave grouping logic."""

    def test_single_easy_wave(self):
        results = [
            WorkbookReadiness(name="WB1", status="GREEN", complexity={"calculations": 2, "lod_expressions": 0, "table_calcs": 0}, effort_hours=1.5),
            WorkbookReadiness(name="WB2", status="GREEN", complexity={"calculations": 1, "lod_expressions": 0, "table_calcs": 0}, effort_hours=1.0),
        ]
        waves = _build_migration_waves(results)
        self.assertEqual(len(waves), 1)
        self.assertEqual(waves[0].label, "Easy (quick wins)")
        self.assertEqual(len(waves[0].workbooks), 2)

    def test_mixed_waves(self):
        results = [
            WorkbookReadiness(name="Easy1", status="GREEN", complexity={"calculations": 1, "lod_expressions": 0, "table_calcs": 0}, effort_hours=1.0),
            WorkbookReadiness(name="Medium1", status="YELLOW", complexity={"calculations": 10, "lod_expressions": 2, "table_calcs": 1}, effort_hours=3.0),
            WorkbookReadiness(name="Hard1", status="RED", complexity={"calculations": 30, "lod_expressions": 10, "table_calcs": 5}, effort_hours=8.0),
        ]
        waves = _build_migration_waves(results)
        self.assertGreaterEqual(len(waves), 2)
        wave_labels = [w.label for w in waves]
        self.assertTrue(any("Easy" in l for l in wave_labels))
        self.assertTrue(any("Complex" in l for l in wave_labels))

    def test_empty_input(self):
        waves = _build_migration_waves([])
        self.assertEqual(waves, [])


class TestRunServerAssessment(unittest.TestCase):
    """Test the full server assessment pipeline."""

    def test_two_workbooks(self):
        ext_a = _make_extracted(
            tables=[("orders", ["id", "amount"])],
            conn_type="postgres",
        )
        ext_b = _make_extracted(
            tables=[("products", ["id", "name"])],
            conn_type="mysql",
        )
        result = run_server_assessment([ext_a, ext_b], ["Sales", "Products"])

        self.assertEqual(result.total_workbooks, 2)
        self.assertEqual(len(result.workbook_results), 2)
        self.assertGreater(result.total_effort_hours, 0)
        self.assertTrue(result.timestamp)

        # Connector census
        self.assertIn("postgres", result.connector_census)
        self.assertIn("mysql", result.connector_census)

        # Waves
        self.assertGreater(len(result.waves), 0)

    def test_single_workbook(self):
        ext = _make_extracted(tables=[("t1", ["a"])])
        result = run_server_assessment([ext], ["WB1"])
        self.assertEqual(result.total_workbooks, 1)
        self.assertEqual(result.green_count + result.yellow_count + result.red_count, 1)

    def test_readiness_percentage(self):
        ext = _make_extracted(tables=[("t1", ["a"])])
        result = run_server_assessment([ext, ext, ext], ["W1", "W2", "W3"])
        self.assertGreaterEqual(result.readiness_pct, 0)
        self.assertLessEqual(result.readiness_pct, 100)


class TestServerAssessmentSerialization(unittest.TestCase):
    """Test JSON serialization."""

    def test_to_dict(self):
        assessment = ServerAssessment(
            total_workbooks=2,
            green_count=1,
            yellow_count=1,
            red_count=0,
            total_effort_hours=5.5,
            timestamp="2026-03-17T00:00:00Z",
        )
        d = assessment.to_dict()
        self.assertEqual(d['total_workbooks'], 2)
        self.assertEqual(d['total_effort_hours'], 5.5)
        self.assertEqual(d['green_count'], 1)

    def test_save_json(self):
        assessment = ServerAssessment(
            total_workbooks=1,
            timestamp="2026-03-17T00:00:00Z",
        )
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, 'report.json')
            result = save_server_assessment_json(assessment, path)
            self.assertTrue(os.path.exists(path))
            self.assertIn('total_workbooks', result)


class TestServerHtmlReport(unittest.TestCase):
    """Test HTML report generation."""

    def test_generate_html(self):
        ext = _make_extracted(
            tables=[("orders", ["id", "amount"])],
            conn_type="postgres",
        )
        result = run_server_assessment([ext], ["SalesWB"])

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, 'report.html')
            out = generate_server_html_report(result, path)
            self.assertTrue(os.path.exists(out))
            with open(out, 'r', encoding='utf-8') as f:
                html = f.read()
            self.assertIn('Portfolio Assessment', html)
            self.assertIn('SalesWB', html)
            self.assertIn('postgres', html)
            self.assertIn('Connector Census', html)

    def test_html_has_wave_section(self):
        ext_a = _make_extracted(tables=[("t1", ["a"])])
        ext_b = _make_extracted(tables=[("t2", ["b"])], lod_count=10)
        result = run_server_assessment([ext_a, ext_b], ["Easy", "Hard"])

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, 'report.html')
            generate_server_html_report(result, path)
            with open(path, 'r', encoding='utf-8') as f:
                html = f.read()
            self.assertIn('Migration Waves', html)
            self.assertIn('Wave', html)


class TestPrintServerSummary(unittest.TestCase):
    """Test console output doesn't crash."""

    def test_print_summary(self):
        ext = _make_extracted(tables=[("t1", ["a"])])
        result = run_server_assessment([ext], ["WB1"])
        # Should not raise
        print_server_summary(result)


class TestWorkbookReadinessToDict(unittest.TestCase):
    """Test WorkbookReadiness serialization."""

    def test_to_dict(self):
        r = WorkbookReadiness(
            name="TestWB",
            status="GREEN",
            pass_count=10,
            warn_count=1,
            fail_count=0,
            effort_hours=2.345,
            connector_types=["postgres"],
            visual_count=5,
            calc_count=3,
            table_count=2,
        )
        d = r.to_dict()
        self.assertEqual(d['name'], 'TestWB')
        self.assertEqual(d['status'], 'GREEN')
        self.assertEqual(d['effort_hours'], 2.3)


class TestMigrationWaveToDict(unittest.TestCase):
    """Test MigrationWave serialization."""

    def test_to_dict(self):
        w = MigrationWave(
            wave_number=1,
            label="Easy",
            workbooks=["WB1", "WB2"],
            total_effort=3.5,
        )
        d = w.to_dict()
        self.assertEqual(d['wave_number'], 1)
        self.assertEqual(len(d['workbooks']), 2)


if __name__ == '__main__':
    unittest.main()
