"""
Tests for Pre-Migration Assessment Module (powerbi_import.assessment).
"""

import json
import os
import sys
import tempfile
import shutil
import unittest

# Ensure parent dir on path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from powerbi_import.assessment import (
    CheckItem, CategoryResult, AssessmentReport,
    run_assessment, print_assessment_report, save_assessment_report,
    _check_datasources, _check_calculations, _check_visuals,
    _check_filters, _check_data_model, _check_interactivity,
    _check_extract_and_packaging, _check_migration_scope,
    PASS, INFO, WARN, FAIL,
)


# ── Test fixtures ───────────────────────────────────────────────────

def _empty_extracted():
    return {
        'datasources': [], 'worksheets': [], 'dashboards': [],
        'calculations': [], 'parameters': [], 'filters': [],
        'stories': [], 'actions': [], 'sets': [], 'groups': [],
        'bins': [], 'hierarchies': [], 'sort_orders': [],
        'custom_sql': [], 'user_filters': [],
    }


def _simple_extracted():
    return {
        'datasources': [{
            'name': 'Sales',
            'connection': {'type': 'Excel'},
            'tables': [
                {'name': 'Orders', 'columns': [
                    {'name': 'OrderID', 'datatype': 'integer'},
                    {'name': 'Amount', 'datatype': 'real'},
                ]},
            ],
            'relationships': [],
        }],
        'worksheets': [
            {'name': 'Sheet1', 'chart_type': 'bar', 'mark_type': 'bar'},
            {'name': 'Sheet2', 'chart_type': 'line', 'mark_type': 'line'},
        ],
        'dashboards': [{'name': 'Dashboard 1'}],
        'calculations': [
            {'name': 'Total', 'caption': 'Total', 'formula': 'SUM([Amount])'},
        ],
        'parameters': [], 'filters': [], 'stories': [], 'actions': [],
        'sets': [], 'groups': [], 'bins': [], 'hierarchies': [],
        'sort_orders': [], 'custom_sql': [], 'user_filters': [],
    }


def _complex_extracted():
    return {
        'datasources': [
            {
                'name': 'BigQuery Source',
                'connection': {'type': 'BigQuery'},
                'tables': [
                    {'name': 'events', 'columns': [
                        {'name': f'col{i}', 'datatype': 'string'} for i in range(100)
                    ]},
                ],
                'relationships': [],
            },
            {
                'name': 'Splunk Source',
                'connection': {'type': 'Splunk'},
                'tables': [{'name': 'logs', 'columns': []}],
                'relationships': [],
            },
        ],
        'worksheets': [
            {'name': 'WS1', 'chart_type': 'custom_viz_type', 'mark_type': 'custom_viz_type',
             'dual_axis': {'has_dual_axis': True}},
        ],
        'dashboards': [{'name': 'D1', 'device_layouts': [{'type': 'phone'}]}],
        'calculations': [
            {'name': 'ScriptCalc', 'caption': 'ScriptCalc',
             'formula': 'SCRIPT_REAL("return 1", [x])'},
            {'name': 'LOD', 'caption': 'LOD', 'formula': '{FIXED [Region] : SUM([Sales])}'},
            {'name': 'RunSum', 'caption': 'RunSum', 'formula': 'RUNNING_SUM(SUM([Sales]))'},
            {'name': 'RegexCalc', 'caption': 'RegexCalc',
             'formula': 'REGEXP_MATCH([Name], "^A")'},
        ],
        'parameters': [
            {'name': 'P1', 'allowable_values': [{'value': str(i)} for i in range(25)]},
        ],
        'filters': [{'field': 'Region'}],
        'stories': [{'name': 'Story1', 'story_points': [{'name': 'SP1'}]}],
        'actions': [
            {'type': 'filter'}, {'type': 'url'}, {'type': 'set'},
        ],
        'sets': [{'name': 'SetA'}],
        'groups': [{'name': 'GroupA'}],
        'bins': [{'name': 'BinA'}],
        'hierarchies': [{'name': 'Hier1'}],
        'sort_orders': [],
        'custom_sql': [{'name': 'Q1', 'query': 'SELECT * FROM tbl'}],
        'user_filters': [{'type': 'user_filter', 'users': ['user1']}],
        'hyper_files': [{'name': 'extract.hyper', 'size_bytes': 5 * 1024 * 1024}],
        'custom_shapes': [{'name': 'shape1.png'}],
        'embedded_fonts': [{'name': 'CustomFont.ttf'}],
        'custom_geocoding': [{'type': 'custom_file', 'name': 'geo.csv'}],
    }


# ═══════════════════════════════════════════════════════════════════
#  Data class tests
# ═══════════════════════════════════════════════════════════════════

class TestDataClasses(unittest.TestCase):
    def test_check_item_creation(self):
        ci = CheckItem("cat", "name", PASS, "detail")
        self.assertEqual(ci.category, "cat")
        self.assertEqual(ci.severity, PASS)
        self.assertEqual(ci.recommendation, "")

    def test_category_result_severity(self):
        cat = CategoryResult(name="Test")
        cat.checks.append(CheckItem("Test", "a", PASS, "ok"))
        self.assertEqual(cat.worst_severity, PASS)
        cat.checks.append(CheckItem("Test", "b", WARN, "warning"))
        self.assertEqual(cat.worst_severity, WARN)
        cat.checks.append(CheckItem("Test", "c", FAIL, "fail"))
        self.assertEqual(cat.worst_severity, FAIL)

    def test_category_result_counts(self):
        cat = CategoryResult(name="Test")
        cat.checks = [
            CheckItem("T", "a", PASS, ""),
            CheckItem("T", "b", PASS, ""),
            CheckItem("T", "c", WARN, ""),
            CheckItem("T", "d", FAIL, ""),
        ]
        self.assertEqual(cat.pass_count, 2)
        self.assertEqual(cat.warn_count, 1)
        self.assertEqual(cat.fail_count, 1)

    def test_empty_category_severity(self):
        cat = CategoryResult(name="Empty")
        self.assertEqual(cat.worst_severity, PASS)

    def test_assessment_report_score_green(self):
        report = AssessmentReport("WB", "2025-01-01T00:00:00Z")
        cat = CategoryResult(name="Test")
        cat.checks.append(CheckItem("Test", "a", PASS, "ok"))
        report.categories.append(cat)
        self.assertEqual(report.overall_score, "GREEN")

    def test_assessment_report_score_yellow(self):
        report = AssessmentReport("WB", "2025-01-01T00:00:00Z")
        cat = CategoryResult(name="Test")
        cat.checks.append(CheckItem("Test", "a", WARN, "warn"))
        report.categories.append(cat)
        self.assertEqual(report.overall_score, "YELLOW")

    def test_assessment_report_score_red(self):
        report = AssessmentReport("WB", "2025-01-01T00:00:00Z")
        cat = CategoryResult(name="Test")
        cat.checks.append(CheckItem("Test", "a", FAIL, "fail"))
        report.categories.append(cat)
        self.assertEqual(report.overall_score, "RED")

    def test_to_dict_roundtrip(self):
        report = AssessmentReport("WB", "2025-01-01T00:00:00Z")
        cat = CategoryResult(name="Cat1")
        cat.checks.append(CheckItem("Cat1", "check1", PASS, "detail1", "rec1"))
        report.categories.append(cat)
        report.summary = {"test": True}
        d = report.to_dict()
        self.assertEqual(d["workbook_name"], "WB")
        self.assertEqual(d["overall_score"], "GREEN")
        self.assertEqual(len(d["categories"]), 1)
        self.assertEqual(d["totals"]["pass"], 1)


# ═══════════════════════════════════════════════════════════════════
#  Category check tests
# ═══════════════════════════════════════════════════════════════════

class TestCheckDatasources(unittest.TestCase):
    def test_no_datasources(self):
        cat = _check_datasources({'datasources': []})
        self.assertEqual(cat.worst_severity, WARN)

    def test_fully_supported_connector(self):
        ext = {'datasources': [{'name': 'DS1', 'connection': {'type': 'Excel'}}]}
        cat = _check_datasources(ext)
        sevs = [c.severity for c in cat.checks]
        self.assertIn(PASS, sevs)

    def test_partially_supported_connector(self):
        ext = {'datasources': [{'name': 'DS1', 'connection': {'type': 'BigQuery'}}]}
        cat = _check_datasources(ext)
        sevs = [c.severity for c in cat.checks]
        self.assertIn(WARN, sevs)

    def test_unsupported_connector(self):
        ext = {'datasources': [{'name': 'DS1', 'connection': {'type': 'Splunk'}}]}
        cat = _check_datasources(ext)
        sevs = [c.severity for c in cat.checks]
        self.assertIn(FAIL, sevs)

    def test_unknown_connector(self):
        ext = {'datasources': [{'name': 'DS1', 'connection': {'type': 'Unknown'}}]}
        cat = _check_datasources(ext)
        self.assertEqual(cat.worst_severity, WARN)

    def test_parameters_datasource_skipped(self):
        ext = {'datasources': [
            {'name': 'Parameters', 'connection': {'type': 'Unknown'}},
            {'name': 'Real DS', 'connection': {'type': 'Excel'}},
        ]}
        cat = _check_datasources(ext)
        # Should not have Unknown warning for Parameters
        for c in cat.checks:
            if 'Unknown' in c.name:
                self.fail("Parameters datasource should be skipped")

    def test_data_blending(self):
        ext = {
            'datasources': [{'name': 'DS1', 'connection': {'type': 'Excel'}}],
            'data_blending': [{'secondary_datasource': 'DS2'}],
        }
        cat = _check_datasources(ext)
        blending_checks = [c for c in cat.checks if 'blending' in c.name.lower()]
        self.assertTrue(any(c.severity == INFO for c in blending_checks))

    def test_custom_sql(self):
        ext = {
            'datasources': [{'name': 'DS1', 'connection': {'type': 'Excel'}}],
            'custom_sql': [{'query': 'SELECT 1'}],
        }
        cat = _check_datasources(ext)
        sql_checks = [c for c in cat.checks if 'SQL' in c.name]
        self.assertTrue(any(c.severity == INFO for c in sql_checks))

    def test_sqlproxy_connector(self):
        ext = {'datasources': [{'name': 'DS1', 'connection': {'type': 'sqlproxy'}}]}
        cat = _check_datasources(ext)
        sqlproxy = [c for c in cat.checks if 'sqlproxy' in c.name.lower()]
        self.assertTrue(any(c.severity == PASS for c in sqlproxy))


class TestCheckCalculations(unittest.TestCase):
    def test_no_calculations(self):
        cat = _check_calculations({'calculations': []})
        self.assertEqual(cat.worst_severity, PASS)

    def test_simple_calculations_pass(self):
        ext = {'calculations': [
            {'name': 'Total', 'formula': 'SUM([Amount])'},
        ]}
        cat = _check_calculations(ext)
        self.assertNotEqual(cat.worst_severity, FAIL)

    def test_unsupported_script(self):
        """SCRIPT_* functions are now WARN (Python/R visual), not FAIL."""
        ext = {'calculations': [
            {'name': 'Script', 'caption': 'Script', 'formula': 'SCRIPT_REAL("x", [y])'},
        ]}
        cat = _check_calculations(ext)
        self.assertEqual(cat.worst_severity, WARN)
        script_checks = [c for c in cat.checks if 'SCRIPT' in c.name]
        self.assertTrue(len(script_checks) > 0)
        self.assertIn('Python/R', script_checks[0].recommendation)

    def test_partial_regex(self):
        ext = {'calculations': [
            {'name': 'Regex', 'caption': 'Regex', 'formula': 'REGEXP_MATCH([Name], "^A")'},
        ]}
        cat = _check_calculations(ext)
        self.assertEqual(cat.worst_severity, WARN)

    def test_lod_detected(self):
        ext = {'calculations': [
            {'name': 'LOD', 'caption': 'LOD', 'formula': '{FIXED [Region] : SUM([Sales])}'},
        ]}
        cat = _check_calculations(ext)
        info_checks = [c for c in cat.checks if c.severity == INFO]
        self.assertTrue(any('LOD' in c.name for c in info_checks))

    def test_table_calc_detected(self):
        ext = {'calculations': [
            {'name': 'RC', 'caption': 'RC', 'formula': 'RUNNING_SUM(SUM([Sales]))'},
        ]}
        cat = _check_calculations(ext)
        info_checks = [c for c in cat.checks if c.severity == INFO]
        self.assertTrue(any('Table' in c.name for c in info_checks))

    def test_multiple_unsupported_truncated(self):
        calcs = [{'name': f'C{i}', 'caption': f'C{i}', 'formula': 'COLLECT([x])'}
                 for i in range(8)]
        ext = {'calculations': calcs}
        cat = _check_calculations(ext)
        fail_checks = [c for c in cat.checks if c.severity == FAIL]
        self.assertTrue(any('+' in c.detail for c in fail_checks))


class TestCheckVisuals(unittest.TestCase):
    def test_mapped_chart_types(self):
        ext = {
            'worksheets': [{'name': 'WS1', 'chart_type': 'bar'}],
            'dashboards': [{'name': 'D1'}],
        }
        cat = _check_visuals(ext)
        self.assertNotEqual(cat.worst_severity, FAIL)

    def test_unmapped_chart_type_warns(self):
        ext = {
            'worksheets': [{'name': 'WS1', 'chart_type': 'custom_nonexistent'}],
            'dashboards': [],
        }
        cat = _check_visuals(ext)
        self.assertEqual(cat.worst_severity, WARN)

    def test_dual_axis_warning(self):
        ext = {
            'worksheets': [{'name': 'WS1', 'dual_axis': {'has_dual_axis': True}}],
            'dashboards': [],
        }
        cat = _check_visuals(ext)
        dual = [c for c in cat.checks if 'dual' in c.name.lower()]
        self.assertTrue(any(c.severity == WARN for c in dual))

    def test_device_layouts_info(self):
        ext = {
            'worksheets': [],
            'dashboards': [{'name': 'D1', 'device_layouts': [{'type': 'phone'}]}],
        }
        cat = _check_visuals(ext)
        dl = [c for c in cat.checks if 'device' in c.name.lower()]
        self.assertTrue(any(c.severity == INFO for c in dl))


class TestCheckFilters(unittest.TestCase):
    def test_no_user_filters(self):
        ext = {'filters': [], 'parameters': [], 'user_filters': []}
        cat = _check_filters(ext)
        # INFO items always present for filter/parameter counts
        self.assertEqual(cat.worst_severity, INFO)

    def test_user_filters_rls(self):
        ext = {'filters': [], 'parameters': [], 'user_filters': [{'type': 'uf'}]}
        cat = _check_filters(ext)
        rls = [c for c in cat.checks if 'RLS' in c.name]
        self.assertTrue(any(c.severity == INFO for c in rls))

    def test_complex_parameters(self):
        ext = {
            'filters': [], 'user_filters': [],
            'parameters': [{'name': 'P', 'allowable_values': [{'v': i} for i in range(25)]}],
        }
        cat = _check_filters(ext)
        cp = [c for c in cat.checks if 'Complex' in c.name]
        self.assertTrue(len(cp) > 0)


class TestCheckDataModel(unittest.TestCase):
    def test_large_table_count_warns(self):
        ext = {'datasources': [{'tables': [{'name': f'T{i}', 'columns': []} for i in range(25)]}],
               'hierarchies': [], 'sets': [], 'groups': [], 'bins': []}
        cat = _check_data_model(ext)
        tbl = [c for c in cat.checks if 'Table count' in c.name]
        self.assertTrue(any(c.severity == WARN for c in tbl))

    def test_wide_schema_warns(self):
        ext = {'datasources': [{'tables': [{'name': 'T1', 'columns': [
            {'name': f'c{i}'} for i in range(250)
        ]}]}], 'hierarchies': [], 'sets': [], 'groups': [], 'bins': []}
        cat = _check_data_model(ext)
        col = [c for c in cat.checks if 'Column count' in c.name]
        self.assertTrue(any(c.severity == WARN for c in col))

    def test_sets_groups_bins(self):
        ext = {'datasources': [], 'hierarchies': [],
               'sets': [{'name': 'S1'}], 'groups': [{'name': 'G1'}], 'bins': [{'name': 'B1'}]}
        cat = _check_data_model(ext)
        sgb = [c for c in cat.checks if 'Sets' in c.name]
        self.assertTrue(len(sgb) > 0)


class TestCheckInteractivity(unittest.TestCase):
    def test_no_actions_or_stories(self):
        ext = {'actions': [], 'stories': []}
        cat = _check_interactivity(ext)
        self.assertEqual(cat.worst_severity, PASS)

    def test_filter_action_pass(self):
        ext = {'actions': [{'type': 'filter'}], 'stories': []}
        cat = _check_interactivity(ext)
        fa = [c for c in cat.checks if 'filter' in c.name.lower()]
        self.assertTrue(any(c.severity == PASS for c in fa))

    def test_url_action_info(self):
        ext = {'actions': [{'type': 'url'}], 'stories': []}
        cat = _check_interactivity(ext)
        ua = [c for c in cat.checks if 'URL' in c.name]
        self.assertTrue(any(c.severity == INFO for c in ua))

    def test_set_action_warn(self):
        ext = {'actions': [{'type': 'set'}], 'stories': []}
        cat = _check_interactivity(ext)
        sa = [c for c in cat.checks if 'Set' in c.name]
        self.assertTrue(any(c.severity == WARN for c in sa))

    def test_stories_to_bookmarks(self):
        ext = {'actions': [], 'stories': [{'name': 'S', 'story_points': [{'n': 1}]}]}
        cat = _check_interactivity(ext)
        st = [c for c in cat.checks if 'Stories' in c.name]
        self.assertTrue(any(c.severity == INFO for c in st))


class TestCheckExtractAndPackaging(unittest.TestCase):
    def test_hyper_files(self):
        ext = {'hyper_files': [{'name': 'e.hyper', 'size_bytes': 1024}]}
        cat = _check_extract_and_packaging(ext)
        hf = [c for c in cat.checks if 'Hyper' in c.name]
        self.assertTrue(any(c.severity == INFO for c in hf))

    def test_custom_shapes_warn(self):
        ext = {'custom_shapes': [{'name': 'shape.png'}]}
        cat = _check_extract_and_packaging(ext)
        cs = [c for c in cat.checks if 'shapes' in c.name.lower()]
        self.assertTrue(any(c.severity == WARN for c in cs))

    def test_no_extras(self):
        ext = {}
        cat = _check_extract_and_packaging(ext)
        self.assertNotEqual(cat.worst_severity, FAIL)


class TestCheckMigrationScope(unittest.TestCase):
    def test_low_complexity(self):
        ext = _empty_extracted()
        ext['worksheets'] = [{'name': 'WS1'}]
        cat = _check_migration_scope(ext)
        details = ' '.join(c.detail for c in cat.checks)
        self.assertIn('Low', details)

    def test_high_complexity(self):
        ext = _complex_extracted()
        cat = _check_migration_scope(ext)
        details = ' '.join(c.detail for c in cat.checks)
        # Should be at least Medium with all that complexity
        self.assertTrue('Medium' in details or 'High' in details or 'Very High' in details)

    def test_object_inventory(self):
        ext = _simple_extracted()
        cat = _check_migration_scope(ext)
        inv = [c for c in cat.checks if 'inventory' in c.name.lower()]
        self.assertTrue(len(inv) > 0)
        self.assertIn('Worksheets', inv[0].detail)


# ═══════════════════════════════════════════════════════════════════
#  Full assessment flow
# ═══════════════════════════════════════════════════════════════════

class TestRunAssessment(unittest.TestCase):
    def test_green_assessment(self):
        report = run_assessment(_simple_extracted(), workbook_name="Simple")
        self.assertEqual(report.overall_score, "GREEN")
        self.assertEqual(len(report.categories), 14)
        self.assertTrue(report.total_checks > 0)

    def test_red_assessment(self):
        report = run_assessment(_complex_extracted(), workbook_name="Complex")
        self.assertEqual(report.overall_score, "RED")

    def test_timestamp_present(self):
        report = run_assessment(_empty_extracted(), workbook_name="Empty")
        self.assertIn("T", report.timestamp)

    def test_summary_populated(self):
        report = run_assessment(_simple_extracted(), workbook_name="Test")
        self.assertEqual(report.summary["workbook"], "Test")


class TestPrintAndSave(unittest.TestCase):
    def test_print_no_errors(self):
        report = run_assessment(_simple_extracted(), workbook_name="PrintTest")
        # Should not raise
        print_assessment_report(report)

    def test_save_creates_file(self):
        report = run_assessment(_simple_extracted(), workbook_name="SaveTest")
        tmpdir = tempfile.mkdtemp(prefix='assess_test_')
        try:
            path = save_assessment_report(report, output_dir=tmpdir)
            self.assertTrue(os.path.exists(path))
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.assertEqual(data["workbook_name"], "SaveTest")
            self.assertEqual(data["overall_score"], "GREEN")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_save_roundtrip(self):
        report = run_assessment(_complex_extracted(), workbook_name="Roundtrip")
        d = report.to_dict()
        self.assertEqual(d["overall_score"], report.overall_score)
        self.assertEqual(d["totals"]["checks"], report.total_checks)


class TestEdgeCases(unittest.TestCase):
    def test_missing_keys(self):
        # Should not raise even with minimal dict
        report = run_assessment({}, workbook_name="Minimal")
        self.assertIsNotNone(report.overall_score)

    def test_empty_formulas(self):
        ext = {'calculations': [{'name': 'X', 'formula': ''}]}
        cat = _check_calculations(ext)
        # Should not crash

    def test_none_values(self):
        ext = {'datasources': [{'name': None, 'connection': {'type': None}}]}
        cat = _check_datasources(ext)
        # Should not crash


if __name__ == '__main__':
    unittest.main()
