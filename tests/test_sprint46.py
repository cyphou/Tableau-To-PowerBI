"""
Tests for Sprint 46 — Data Alerts, Visual Diff, Enhanced Validation,
Migration Completeness Scoring, Connection String Audit.
"""

import json
import os
import tempfile
import unittest

from powerbi_import.alerts_generator import (
    extract_alerts,
    generate_alert_rules,
    save_alert_rules,
)
from powerbi_import.visual_diff import (
    generate_visual_diff,
    generate_visual_diff_json,
    _diff_worksheet,
    _extract_pbi_visual_info,
)
from powerbi_import.validator import ArtifactValidator
from powerbi_import.migration_report import MigrationReport
from powerbi_import.assessment import (
    run_assessment,
    _check_connection_strings,
    PASS,
    FAIL,
)


# ═══════════════════════════════════════════════════════════════════
#  46.1 — Data-driven Alerts
# ═══════════════════════════════════════════════════════════════════

class TestExtractAlerts(unittest.TestCase):
    """Test alert extraction from Tableau data."""

    def test_extract_from_alert_parameter(self):
        """Parameters with alert-related names should produce alerts."""
        data = {
            'parameters': [
                {'name': 'Alert Threshold', 'value': '100', 'datatype': 'real'},
            ],
            'calculations': [],
            'worksheets': [],
        }
        alerts = extract_alerts(data)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['threshold'], 100.0)
        self.assertIn('Alert Threshold', alerts[0]['name'])

    def test_extract_from_target_parameter(self):
        """Parameters with 'target' in name should produce alerts."""
        data = {
            'parameters': [
                {'name': 'Sales Target', 'value': '50000'},
            ],
            'calculations': [],
            'worksheets': [],
        }
        alerts = extract_alerts(data)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['threshold'], 50000.0)

    def test_no_alerts_from_non_alert_parameters(self):
        """Regular parameters should NOT produce alerts."""
        data = {
            'parameters': [
                {'name': 'Region Selector', 'value': 'West'},
            ],
            'calculations': [],
            'worksheets': [],
        }
        alerts = extract_alerts(data)
        self.assertEqual(len(alerts), 0)

    def test_extract_from_calculation_threshold(self):
        """Calculations with IF/threshold patterns should produce alerts."""
        data = {
            'parameters': [
                {'name': 'Alert Threshold', 'value': '75'},
            ],
            'calculations': [
                {
                    'name': 'Over Alert Threshold',
                    'caption': 'Over Alert Threshold',
                    'formula': 'IF [Sales] > [Parameters].[Alert Threshold] THEN "Over" ELSE "Under" END',
                },
            ],
            'worksheets': [],
        }
        alerts = extract_alerts(data)
        # Should find at least one alert from parameter + one from calc
        self.assertGreaterEqual(len(alerts), 1)

    def test_extract_from_literal_threshold(self):
        """Calculations with literal threshold values should produce alerts."""
        data = {
            'parameters': [],
            'calculations': [
                {
                    'name': 'Alert Flag',
                    'caption': 'Alert Flag',
                    'formula': 'IF [Revenue] > 10000 THEN "Alert" END',
                },
            ],
            'worksheets': [],
        }
        alerts = extract_alerts(data)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['threshold'], 10000.0)
        self.assertEqual(alerts[0]['measure'], 'Revenue')

    def test_reference_line_target_alert(self):
        """Reference lines with 'target' label should produce alerts."""
        data = {
            'parameters': [],
            'calculations': [],
            'worksheets': [
                {
                    'name': 'Sales Chart',
                    'reference_lines': [
                        {'value': '500', 'label': 'Target Line'},
                    ],
                    'fields': [{'name': 'Sales', 'role': 'measure'}],
                },
            ],
        }
        alerts = extract_alerts(data)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['threshold'], 500.0)

    def test_reference_line_no_alert_without_keyword(self):
        """Reference lines without alert keywords should not produce alerts."""
        data = {
            'parameters': [],
            'calculations': [],
            'worksheets': [
                {
                    'name': 'Sales Chart',
                    'reference_lines': [
                        {'value': '500', 'label': 'Average'},
                    ],
                    'fields': [],
                },
            ],
        }
        alerts = extract_alerts(data)
        self.assertEqual(len(alerts), 0)

    def test_empty_data(self):
        """Empty extracted data should produce zero alerts."""
        alerts = extract_alerts({})
        self.assertEqual(len(alerts), 0)

    def test_dict_format_parameters(self):
        """Parameters in dict format should be handled."""
        data = {
            'parameters': {'parameters': [
                {'name': 'Limit Threshold', 'value': '200'},
            ]},
            'calculations': {'calculations': []},
            'worksheets': {'worksheets': []},
        }
        alerts = extract_alerts(data)
        self.assertEqual(len(alerts), 1)

    def test_lower_limit_infers_lessThan(self):
        """Parameters with 'min'/'lower' should infer lessThan operator."""
        data = {
            'parameters': [
                {'name': 'Lower Limit Threshold', 'value': '10'},
            ],
            'calculations': [],
            'worksheets': [],
        }
        alerts = extract_alerts(data)
        self.assertEqual(alerts[0]['operator'], 'lessThan')


class TestGenerateAlertRules(unittest.TestCase):
    """Test PBI alert rule generation."""

    def test_generate_rules(self):
        """Generated rules should have required PBI fields."""
        alerts = [
            {
                'name': 'Alert: High Sales',
                'measure': 'Sales',
                'operator': 'greaterThan',
                'threshold': 100000,
                'frequency': 'atMostOncePerDay',
                'source': 'parameter:Sales Alert',
            },
        ]
        rules = generate_alert_rules(alerts)
        self.assertEqual(len(rules), 1)
        rule = rules[0]
        self.assertEqual(rule['condition']['operator'], 'greaterThan')
        self.assertEqual(rule['condition']['threshold'], 100000)
        self.assertTrue(rule['isEnabled'])
        self.assertEqual(rule['measure'], 'Sales')

    def test_empty_alerts(self):
        """No alerts should produce no rules."""
        self.assertEqual(generate_alert_rules([]), [])


class TestSaveAlertRules(unittest.TestCase):
    """Test alert rules file output."""

    def test_save_creates_file(self):
        """save_alert_rules should create a JSON file."""
        rules = [{'name': 'test', 'condition': {}, 'measure': 'X',
                  'frequency': 'once', 'isEnabled': True, 'migrationSource': '',
                  'migrationNote': ''}]
        with tempfile.TemporaryDirectory() as td:
            path = save_alert_rules(rules, td)
            self.assertTrue(os.path.exists(path))
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.assertEqual(len(data['alertRules']), 1)


# ═══════════════════════════════════════════════════════════════════
#  46.2 — Visual Diff Report
# ═══════════════════════════════════════════════════════════════════

class TestDiffWorksheet(unittest.TestCase):
    """Test individual worksheet diff logic."""

    def test_exact_match(self):
        """Worksheet matching a PBI visual by title should be exact."""
        ws = {
            'name': 'Sales Chart',
            'mark_type': 'bar',
            'fields': [{'name': 'Sales', 'role': 'measure'}],
            'mark_encoding': {},
            'filters': [],
        }
        pbi_visuals = [{
            'title': {'text': 'Sales Chart'},
            'visual': {'visualType': 'clusteredBarChart'},
            'query': {},
        }]
        result = _diff_worksheet(ws, pbi_visuals)
        self.assertEqual(result['status'], 'exact')
        self.assertEqual(result['name'], 'Sales Chart')
        self.assertEqual(result['expected_pbi_type'], 'clusteredBarChart')

    def test_unmapped_when_no_visuals(self):
        """Worksheet with no matching PBI visuals should be unmapped."""
        ws = {
            'name': 'Revenue',
            'mark_type': 'line',
            'fields': [],
            'mark_encoding': {},
            'filters': [],
        }
        result = _diff_worksheet(ws, [])
        self.assertEqual(result['status'], 'unmapped')
        self.assertIsNone(result['actual_pbi_type'])

    def test_field_coverage_calculation(self):
        """Field coverage should be computed correctly."""
        ws = {
            'name': 'Test',
            'mark_type': 'bar',
            'fields': [
                {'name': 'Sales'},
                {'name': 'Region'},
                {'name': 'Date'},
            ],
            'mark_encoding': {},
            'filters': [],
        }
        result = _diff_worksheet(ws, [])
        self.assertEqual(result['field_coverage'], 0)
        self.assertEqual(len(result['unmapped_fields']), 3)

    def test_encoding_detection(self):
        """Encodings present in mark_encoding should be detected."""
        ws = {
            'name': 'Test',
            'mark_type': 'scatter',
            'fields': [],
            'mark_encoding': {'color': 'Region', 'size': 'Sales'},
            'filters': [],
        }
        result = _diff_worksheet(ws, [])
        self.assertTrue(result['tableau_encodings']['color'])
        self.assertTrue(result['tableau_encodings']['size'])
        self.assertFalse(result['tableau_encodings']['tooltip'])

    def test_dict_mark_type(self):
        """mark_type as dict should be handled."""
        ws = {
            'name': 'Test',
            'mark_type': {'type': 'pie'},
            'fields': [],
            'mark_encoding': {},
            'filters': [],
        }
        result = _diff_worksheet(ws, [])
        self.assertEqual(result['mark_type'], 'pie')
        self.assertEqual(result['expected_pbi_type'], 'pieChart')


class TestExtractPbiVisualInfo(unittest.TestCase):
    """Test PBI visual.json info extraction."""

    def test_extract_visual_type(self):
        """Should extract visualType from visual JSON."""
        data = {'visual': {'visualType': 'clusteredBarChart'}}
        info = _extract_pbi_visual_info(data)
        self.assertEqual(info['visualType'], 'clusteredBarChart')

    def test_extract_title(self):
        """Should extract title text."""
        data = {
            'title': {'text': 'My Chart'},
            'visual': {'visualType': 'lineChart'},
        }
        info = _extract_pbi_visual_info(data)
        self.assertEqual(info['title'], 'My Chart')


class TestVisualDiffJson(unittest.TestCase):
    """Test JSON output of visual diff."""

    def test_generate_diff_empty(self):
        """Empty worksheets should produce empty diff."""
        with tempfile.TemporaryDirectory() as td:
            result = generate_visual_diff_json({}, td)
            self.assertEqual(result['total'], 0)
            self.assertEqual(result['exact'], 0)

    def test_generate_diff_with_worksheets(self):
        """Should produce diff entries for each worksheet."""
        data = {
            'worksheets': [
                {'name': 'Sheet1', 'mark_type': 'bar', 'fields': [],
                 'mark_encoding': {}, 'filters': []},
                {'name': 'Sheet2', 'mark_type': 'line', 'fields': [],
                 'mark_encoding': {}, 'filters': []},
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            result = generate_visual_diff_json(data, td)
            self.assertEqual(result['total'], 2)
            self.assertEqual(len(result['visuals']), 2)


class TestVisualDiffHtml(unittest.TestCase):
    """Test HTML output of visual diff."""

    def test_generate_html(self):
        """Should create an HTML file."""
        data = {
            'worksheets': [
                {'name': 'Sheet1', 'mark_type': 'bar', 'fields': [],
                 'mark_encoding': {}, 'filters': []},
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            path = generate_visual_diff(data, td, os.path.join(td, 'diff.html'))
            self.assertTrue(os.path.exists(path))
            with open(path, 'r', encoding='utf-8') as f:
                html = f.read()
            self.assertIn('Visual Diff Report', html)
            self.assertIn('Sheet1', html)


# ═══════════════════════════════════════════════════════════════════
#  46.3 — Enhanced Semantic Validation
# ═══════════════════════════════════════════════════════════════════

def _create_tmdl_project(base_dir, model_content, tables=None):
    """Helper: create a minimal TMDL project structure."""
    name = 'Test'
    sm_dir = os.path.join(base_dir, f'{name}.SemanticModel')
    def_dir = os.path.join(sm_dir, 'definition')
    tables_dir = os.path.join(def_dir, 'tables')
    os.makedirs(tables_dir, exist_ok=True)

    with open(os.path.join(def_dir, 'model.tmdl'), 'w', encoding='utf-8') as f:
        f.write(model_content)

    if tables:
        for tname, tcontent in tables.items():
            with open(os.path.join(tables_dir, f'{tname}.tmdl'), 'w', encoding='utf-8') as f:
                f.write(tcontent)

    return sm_dir


class TestCircularRelationships(unittest.TestCase):
    """Test circular dependency detection in relationships."""

    def test_no_cycles(self):
        """Linear relationships should not produce cycles."""
        model = (
            "model Model\n"
            "\n"
            "relationship r1\n"
            "\tfromTable: 'Orders'\n"
            "\ttoTable: 'Products'\n"
            "\n"
            "relationship r2\n"
            "\tfromTable: 'Products'\n"
            "\ttoTable: 'Categories'\n"
        )
        with tempfile.TemporaryDirectory() as td:
            sm_dir = _create_tmdl_project(td, model)
            cycles = ArtifactValidator.detect_circular_relationships(sm_dir)
            self.assertEqual(len(cycles), 0)

    def test_direct_cycle(self):
        """A→B→A should be detected as a cycle."""
        model = (
            "model Model\n"
            "\n"
            "relationship r1\n"
            "\tfromTable: 'A'\n"
            "\ttoTable: 'B'\n"
            "\n"
            "relationship r2\n"
            "\tfromTable: 'B'\n"
            "\ttoTable: 'A'\n"
        )
        with tempfile.TemporaryDirectory() as td:
            sm_dir = _create_tmdl_project(td, model)
            cycles = ArtifactValidator.detect_circular_relationships(sm_dir)
            self.assertGreater(len(cycles), 0)

    def test_indirect_cycle(self):
        """A→B→C→A should be detected as a cycle."""
        model = (
            "model Model\n"
            "\n"
            "relationship r1\n"
            "\tfromTable: 'A'\n"
            "\ttoTable: 'B'\n"
            "\n"
            "relationship r2\n"
            "\tfromTable: 'B'\n"
            "\ttoTable: 'C'\n"
            "\n"
            "relationship r3\n"
            "\tfromTable: 'C'\n"
            "\ttoTable: 'A'\n"
        )
        with tempfile.TemporaryDirectory() as td:
            sm_dir = _create_tmdl_project(td, model)
            cycles = ArtifactValidator.detect_circular_relationships(sm_dir)
            self.assertGreater(len(cycles), 0)

    def test_empty_model(self):
        """Model with no relationships should return no cycles."""
        with tempfile.TemporaryDirectory() as td:
            sm_dir = _create_tmdl_project(td, "model Model\n")
            cycles = ArtifactValidator.detect_circular_relationships(sm_dir)
            self.assertEqual(len(cycles), 0)


class TestOrphanTables(unittest.TestCase):
    """Test orphan table detection."""

    def test_no_orphans_all_related(self):
        """Tables all in relationships should have no orphans."""
        model = (
            "model Model\n"
            "\n"
            "relationship r1\n"
            "\tfromTable: 'Orders'\n"
            "\ttoTable: 'Products'\n"
        )
        tables = {
            'Orders': "table 'Orders'\n\tcolumn 'OrderId'\n",
            'Products': "table 'Products'\n\tcolumn 'ProductId'\n",
        }
        with tempfile.TemporaryDirectory() as td:
            sm_dir = _create_tmdl_project(td, model, tables)
            orphans = ArtifactValidator.detect_orphan_tables(sm_dir)
            self.assertEqual(len(orphans), 0)

    def test_orphan_detected(self):
        """Table not in any relationship and not referenced should be orphan."""
        model = (
            "model Model\n"
            "\n"
            "relationship r1\n"
            "\tfromTable: 'Orders'\n"
            "\ttoTable: 'Products'\n"
        )
        tables = {
            'Orders': "table 'Orders'\n\tcolumn 'OrderId'\n",
            'Products': "table 'Products'\n\tcolumn 'ProductId'\n",
            'Orphan': "table 'Orphan'\n\tcolumn 'Id'\n",
        }
        with tempfile.TemporaryDirectory() as td:
            sm_dir = _create_tmdl_project(td, model, tables)
            orphans = ArtifactValidator.detect_orphan_tables(sm_dir)
            self.assertIn('Orphan', orphans)

    def test_dax_referenced_not_orphan(self):
        """Table referenced in DAX should not be orphan."""
        model = "model Model\n"
        tables = {
            'Orders': "table 'Orders'\n\tmeasure 'Total' = SUM('Products'[Price])\n",
            'Products': "table 'Products'\n\tcolumn 'Price'\n",
        }
        with tempfile.TemporaryDirectory() as td:
            sm_dir = _create_tmdl_project(td, model, tables)
            orphans = ArtifactValidator.detect_orphan_tables(sm_dir)
            self.assertNotIn('Products', orphans)

    def test_single_table_not_orphan(self):
        """Single table model should not report orphans."""
        model = "model Model\n"
        tables = {'Solo': "table 'Solo'\n\tcolumn 'Id'\n"}
        with tempfile.TemporaryDirectory() as td:
            sm_dir = _create_tmdl_project(td, model, tables)
            orphans = ArtifactValidator.detect_orphan_tables(sm_dir)
            self.assertEqual(len(orphans), 0)

    def test_calendar_excluded(self):
        """Calendar/Date utility tables should be excluded from orphans."""
        model = "model Model\n"
        tables = {
            'Orders': "table 'Orders'\n\tcolumn 'OrderId'\n",
            'Calendar': "table 'Calendar'\n\tcolumn 'Date'\n",
        }
        with tempfile.TemporaryDirectory() as td:
            sm_dir = _create_tmdl_project(td, model, tables)
            orphans = ArtifactValidator.detect_orphan_tables(sm_dir)
            self.assertNotIn('Calendar', orphans)


class TestUnusedParameters(unittest.TestCase):
    """Test unused parameter detection."""

    def test_used_parameter(self):
        """Parameter referenced in another table should not be unused."""
        model = "model Model\n"
        tables = {
            'SalesParameter': (
                "table 'SalesParameter'\n"
                "\tcolumn 'Value'\n"
                "\tmeasure 'Sales Parameter Value' = SELECTEDVALUE('SalesParameter'[Value])\n"
                "\tpartition p = GENERATESERIES(0, 100, 1)\n"
            ),
            'Orders': (
                "table 'Orders'\n"
                "\tcolumn 'Amount'\n"
                "\tmeasure 'Filtered Sales' = CALCULATE(SUM([Amount]), [Sales Parameter Value])\n"
            ),
        }
        with tempfile.TemporaryDirectory() as td:
            sm_dir = _create_tmdl_project(td, model, tables)
            unused = ArtifactValidator.detect_unused_parameters(sm_dir)
            self.assertEqual(len(unused), 0)

    def test_unused_parameter(self):
        """Parameter not referenced anywhere should be detected."""
        model = "model Model\n"
        tables = {
            'MyParameter': (
                "table 'MyParameter'\n"
                "\tcolumn 'Value'\n"
                "\tmeasure 'My Param Val' = SELECTEDVALUE('MyParameter'[Value])\n"
                "\tpartition p = GENERATESERIES(0, 100, 1)\n"
            ),
            'Orders': (
                "table 'Orders'\n"
                "\tcolumn 'Amount'\n"
                "\tmeasure 'Total' = SUM([Amount])\n"
            ),
        }
        with tempfile.TemporaryDirectory() as td:
            sm_dir = _create_tmdl_project(td, model, tables)
            unused = ArtifactValidator.detect_unused_parameters(sm_dir)
            self.assertIn('MyParameter', unused)

    def test_no_parameter_tables(self):
        """Model with no parameter tables should return empty."""
        model = "model Model\n"
        tables = {
            'Orders': "table 'Orders'\n\tcolumn 'Amount'\n",
        }
        with tempfile.TemporaryDirectory() as td:
            sm_dir = _create_tmdl_project(td, model, tables)
            unused = ArtifactValidator.detect_unused_parameters(sm_dir)
            self.assertEqual(len(unused), 0)


# ═══════════════════════════════════════════════════════════════════
#  46.4 — Migration Completeness Scoring
# ═══════════════════════════════════════════════════════════════════

class TestCompletenessScoring(unittest.TestCase):
    """Test per-category fidelity breakdown and grading."""

    def _make_report(self):
        r = MigrationReport('Test')
        r.add_item('calculation', 'Profit', 'exact', dax='SUM([Profit])')
        r.add_item('calculation', 'Tax', 'approximate', dax='/* approx */ [Tax]')
        r.add_item('calculation', 'Spatial', 'unsupported', note='MAKEPOINT')
        r.add_item('visual', 'Chart1', 'exact')
        r.add_item('visual', 'Chart2', 'exact')
        r.add_item('datasource', 'DB1', 'exact')
        r.add_item('relationship', 'A→B', 'exact')
        r.add_item('parameter', 'P1', 'exact')
        return r

    def test_completeness_score_structure(self):
        """Completeness score should have categories, overall_score, grade."""
        r = self._make_report()
        cs = r.get_completeness_score()
        self.assertIn('categories', cs)
        self.assertIn('overall_score', cs)
        self.assertIn('grade', cs)

    def test_per_category_fidelity(self):
        """Each category should have fidelity_pct."""
        r = self._make_report()
        cs = r.get_completeness_score()
        calc_info = cs['categories']['calculation']
        self.assertEqual(calc_info['total'], 3)
        self.assertEqual(calc_info['exact'], 1)
        self.assertEqual(calc_info['approximate'], 1)
        # fidelity = (1*100 + 1*50) / 3 = 50.0
        self.assertAlmostEqual(calc_info['fidelity_pct'], 50.0, places=1)

    def test_visual_100_fidelity(self):
        """All exact visuals should be 100% fidelity."""
        r = self._make_report()
        cs = r.get_completeness_score()
        self.assertEqual(cs['categories']['visual']['fidelity_pct'], 100.0)

    def test_grade_A(self):
        """All exact items should produce grade A."""
        r = MigrationReport('Test')
        r.add_item('calculation', 'C1', 'exact')
        r.add_item('visual', 'V1', 'exact')
        cs = r.get_completeness_score()
        self.assertEqual(cs['grade'], 'A')
        self.assertGreaterEqual(cs['overall_score'], 90)

    def test_grade_F(self):
        """All unsupported items should produce grade F."""
        r = MigrationReport('Test')
        for i in range(10):
            r.add_item('calculation', f'C{i}', 'unsupported')
        cs = r.get_completeness_score()
        self.assertEqual(cs['grade'], 'F')

    def test_empty_report(self):
        """Empty report should give 100% score."""
        r = MigrationReport('Test')
        cs = r.get_completeness_score()
        self.assertEqual(cs['overall_score'], 100.0)
        self.assertEqual(cs['grade'], 'A')

    def test_completeness_in_to_dict(self):
        """to_dict should include completeness."""
        r = self._make_report()
        d = r.to_dict()
        self.assertIn('completeness', d)
        self.assertIn('overall_score', d['completeness'])


# ═══════════════════════════════════════════════════════════════════
#  46.5 — Connection String Audit
# ═══════════════════════════════════════════════════════════════════

class TestConnectionStringAudit(unittest.TestCase):
    """Test connection string security checks."""

    def test_no_credentials_pass(self):
        """Clean connection strings should pass."""
        data = {
            'datasources': [
                {
                    'name': 'DB',
                    'connection': {'type': 'sqlserver', 'server': 'myserver.db'},
                },
            ],
        }
        result = _check_connection_strings(data)
        self.assertEqual(result.worst_severity, PASS)

    def test_password_detected(self):
        """Connection strings with passwords should fail."""
        data = {
            'datasources': [
                {
                    'name': 'DB',
                    'connection': {
                        'type': 'sqlserver',
                        'connection_string': 'Server=db;Password=secret123;',
                    },
                },
            ],
        }
        result = _check_connection_strings(data)
        self.assertEqual(result.worst_severity, FAIL)
        self.assertIn('password', result.checks[0].detail.lower())

    def test_token_detected(self):
        """Connection strings with tokens should fail."""
        data = {
            'datasources': [
                {
                    'name': 'API',
                    'connection': {
                        'type': 'web',
                        'authentication': 'Bearer eyJhbGciOiJIUzI1NiJ9.test',
                    },
                },
            ],
        }
        result = _check_connection_strings(data)
        self.assertEqual(result.worst_severity, FAIL)

    def test_api_key_detected(self):
        """Connection strings with API keys should fail."""
        data = {
            'datasources': [
                {
                    'name': 'Service',
                    'connection': {
                        'type': 'web',
                        'api_key': 'apikey=12345abcdef',
                    },
                },
            ],
        }
        result = _check_connection_strings(data)
        self.assertEqual(result.worst_severity, FAIL)

    def test_no_datasources_pass(self):
        """No datasources should pass."""
        result = _check_connection_strings({})
        self.assertEqual(result.worst_severity, PASS)

    def test_multiple_sensitive_fields(self):
        """Multiple sensitive fields should all be reported."""
        data = {
            'datasources': [
                {
                    'name': 'DB',
                    'connection': {
                        'type': 'sqlserver',
                        'connection_string': 'Server=db;Password=abc;',
                        'secret_value': 'token=xyz',
                    },
                },
            ],
        }
        result = _check_connection_strings(data)
        self.assertEqual(result.worst_severity, FAIL)

    def test_integrated_in_assessment(self):
        """Connection string audit should run as part of full assessment."""
        data = {
            'datasources': [
                {
                    'name': 'DB',
                    'connection': {
                        'type': 'sqlserver',
                        'connection_string': 'Server=db;Password=secret;',
                    },
                },
            ],
        }
        report = run_assessment(data, workbook_name='TestWB')
        cat_names = [c.name for c in report.categories]
        self.assertIn('Connection String Security', cat_names)


# ═══════════════════════════════════════════════════════════════════
#  Integration: validate_project with new checks
# ═══════════════════════════════════════════════════════════════════

class TestValidateProjectEnhanced(unittest.TestCase):
    """Test that validate_project runs enhanced checks."""

    def _create_project(self, td, model_content, tables=None):
        """Create a minimal .pbip project for validation."""
        name = 'Test'
        proj_dir = os.path.join(td, name)
        os.makedirs(proj_dir, exist_ok=True)

        # .pbip file
        with open(os.path.join(proj_dir, f'{name}.pbip'), 'w') as f:
            json.dump({'version': '1.0'}, f)

        # Report dir
        report_dir = os.path.join(proj_dir, f'{name}.Report', 'definition')
        os.makedirs(report_dir, exist_ok=True)
        with open(os.path.join(report_dir, 'report.json'), 'w') as f:
            json.dump({'$schema': ArtifactValidator.VALID_REPORT_SCHEMAS[0]}, f)

        # SemanticModel dir
        sm_dir = os.path.join(proj_dir, f'{name}.SemanticModel', 'definition')
        tables_dir = os.path.join(sm_dir, 'tables')
        os.makedirs(tables_dir, exist_ok=True)
        with open(os.path.join(sm_dir, 'model.tmdl'), 'w', encoding='utf-8') as f:
            f.write(model_content)

        if tables:
            for tname, tcontent in tables.items():
                with open(os.path.join(tables_dir, f'{tname}.tmdl'), 'w',
                          encoding='utf-8') as f:
                    f.write(tcontent)

        return proj_dir

    def test_circular_warning_in_project(self):
        """Circular relationships should appear in project warnings."""
        model = (
            "model Model\n"
            "\n"
            "relationship r1\n"
            "\tfromTable: 'A'\n"
            "\ttoTable: 'B'\n"
            "\n"
            "relationship r2\n"
            "\tfromTable: 'B'\n"
            "\ttoTable: 'A'\n"
        )
        tables = {
            'A': "table 'A'\n\tcolumn 'Id'\n",
            'B': "table 'B'\n\tcolumn 'Id'\n",
        }
        with tempfile.TemporaryDirectory() as td:
            proj = self._create_project(td, model, tables)
            result = ArtifactValidator.validate_project(proj)
            circular_warnings = [
                w for w in result['warnings'] if 'Circular' in w
            ]
            self.assertGreater(len(circular_warnings), 0)

    def test_orphan_warning_in_project(self):
        """Orphan tables should appear in project warnings."""
        model = (
            "model Model\n"
            "\n"
            "relationship r1\n"
            "\tfromTable: 'Orders'\n"
            "\ttoTable: 'Products'\n"
        )
        tables = {
            'Orders': "table 'Orders'\n\tcolumn 'Id'\n",
            'Products': "table 'Products'\n\tcolumn 'Id'\n",
            'Unused': "table 'Unused'\n\tcolumn 'Id'\n",
        }
        with tempfile.TemporaryDirectory() as td:
            proj = self._create_project(td, model, tables)
            result = ArtifactValidator.validate_project(proj)
            orphan_warnings = [
                w for w in result['warnings'] if 'Orphan' in w
            ]
            self.assertGreater(len(orphan_warnings), 0)


if __name__ == '__main__':
    unittest.main()
