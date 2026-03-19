"""
Tests for Sprint 59 — Validator Enhancements.

Covers:
  - TMDL indentation validation (clean, mixed tabs/spaces)
  - TMDL keyword balance (table without columns, role without tablePermission)
  - M query validation (unmatched let/in, unclosed brackets, dangling {prev})
  - Visual completeness (missing visualType, zero size)
  - Cross-file reference checking (missing page.json, missing visual.json)
  - Severity levels (ERROR, WARNING, INFO)
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from powerbi_import.validator import ArtifactValidator as PBIPValidator


class TestTmdlIndentation(unittest.TestCase):
    def test_clean_tabs(self):
        content = "table 'Sales'\n\tcolumn Name\n\t\tannotation x = y\n"
        issues = PBIPValidator.validate_tmdl_indentation(content)
        self.assertEqual(len(issues), 0)

    def test_mixed_tabs_spaces(self):
        content = "table 'Sales'\n\t column Name\n"
        issues = PBIPValidator.validate_tmdl_indentation(content)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]['severity'], 'WARNING')
        self.assertIn('Mixed', issues[0]['message'])

    def test_all_spaces(self):
        # Pure spaces — no mix warning since no tabs
        content = "table 'Sales'\n  column Name\n"
        issues = PBIPValidator.validate_tmdl_indentation(content)
        self.assertEqual(len(issues), 0)

    def test_empty_content(self):
        issues = PBIPValidator.validate_tmdl_indentation('')
        self.assertEqual(len(issues), 0)

    def test_filepath_in_message(self):
        content = "table 'Sales'\n\t column\n"
        issues = PBIPValidator.validate_tmdl_indentation(content, filepath='model.tmdl')
        self.assertIn('model.tmdl', issues[0]['message'])


class TestTmdlStructure(unittest.TestCase):
    def test_table_with_column(self):
        content = "table 'Sales'\n\tcolumn Name\n\tpartition p1\n"
        issues = PBIPValidator.validate_tmdl_structure(content)
        self.assertEqual(len(issues), 0)

    def test_table_without_column(self):
        content = "table 'Sales'\n\tmeasure Revenue = SUM(Amount)\n"
        issues = PBIPValidator.validate_tmdl_structure(content)
        self.assertEqual(len(issues), 1)
        self.assertIn('Sales', issues[0]['message'])
        self.assertIn('no columns', issues[0]['message'])

    def test_role_with_table_permission(self):
        content = "role 'Admin'\n\ttablePermission 'Sales' = TRUE()\n"
        issues = PBIPValidator.validate_tmdl_structure(content)
        self.assertEqual(len(issues), 0)

    def test_role_without_table_permission(self):
        content = "role 'Admin'\n\tannotation x = y\n"
        issues = PBIPValidator.validate_tmdl_structure(content)
        self.assertEqual(len(issues), 1)
        self.assertIn('Admin', issues[0]['message'])
        self.assertIn('no tablePermission', issues[0]['message'])

    def test_multiple_tables(self):
        content = "table 'T1'\n\tcolumn A\ntable 'T2'\n\tmeasure M = 1\n"
        issues = PBIPValidator.validate_tmdl_structure(content)
        self.assertEqual(len(issues), 1)
        self.assertIn('T2', issues[0]['message'])

    def test_empty_content(self):
        issues = PBIPValidator.validate_tmdl_structure('')
        self.assertEqual(len(issues), 0)


class TestMExpressionValidation(unittest.TestCase):
    def test_valid_expression(self):
        m = 'let Source = Sql.Database("server", "db") in Source'
        issues = PBIPValidator.validate_m_expression(m)
        self.assertEqual(len(issues), 0)

    def test_let_without_in(self):
        m = 'let Source = Sql.Database("server", "db")'
        issues = PBIPValidator.validate_m_expression(m)
        has_error = any(i['severity'] == 'ERROR' and 'let' in i['message'] for i in issues)
        self.assertTrue(has_error)

    def test_unmatched_parens(self):
        m = 'let Source = Sql.Database("server" in Source'
        issues = PBIPValidator.validate_m_expression(m)
        has_parens = any('parentheses' in i['message'] for i in issues)
        self.assertTrue(has_parens)

    def test_unmatched_brackets(self):
        m = 'let Source = Table.SelectRows(prev, [Col) in Source'
        issues = PBIPValidator.validate_m_expression(m)
        has_bracket = any('brackets' in i['message'] for i in issues)
        self.assertTrue(has_bracket)

    def test_dangling_prev(self):
        m = 'let Source = Table.RenameColumns({prev}, {{"A", "B"}}) in Source'
        issues = PBIPValidator.validate_m_expression(m)
        has_prev = any('{prev}' in i['message'] for i in issues)
        self.assertTrue(has_prev)

    def test_empty_expression(self):
        issues = PBIPValidator.validate_m_expression('')
        self.assertEqual(len(issues), 0)

    def test_context_in_message(self):
        m = 'let x = 1'
        issues = PBIPValidator.validate_m_expression(m, context='Sales.tmdl')
        self.assertTrue(any('Sales.tmdl' in i['message'] for i in issues))


class TestVisualCompleteness(unittest.TestCase):
    def test_valid_visual(self):
        v = {
            'visual': {'visualType': 'barChart'},
            'position': {'width': 400, 'height': 300},
        }
        issues = PBIPValidator.validate_visual_completeness(v)
        self.assertEqual(len(issues), 0)

    def test_missing_visual_type(self):
        v = {'visual': {}, 'position': {'width': 400, 'height': 300}}
        issues = PBIPValidator.validate_visual_completeness(v)
        has_vtype = any('visualType' in i['message'] for i in issues)
        self.assertTrue(has_vtype)

    def test_zero_size(self):
        v = {
            'visual': {'visualType': 'table'},
            'position': {'width': 0, 'height': 300},
        }
        issues = PBIPValidator.validate_visual_completeness(v)
        has_size = any('zero' in i['message'] for i in issues)
        self.assertTrue(has_size)

    def test_negative_size(self):
        v = {
            'visual': {'visualType': 'table'},
            'position': {'width': -10, 'height': 300},
        }
        issues = PBIPValidator.validate_visual_completeness(v)
        self.assertTrue(len(issues) > 0)


class TestCrossReferences(unittest.TestCase):
    def _make_project(self, tmpdir, pages=None, visuals_per_page=None):
        """Create a minimal PBIP project structure."""
        proj_dir = os.path.join(tmpdir, 'TestProject')
        os.makedirs(proj_dir)
        report_dir = os.path.join(proj_dir, 'TestProject.Report')
        pages_dir = os.path.join(report_dir, 'pages')

        for page_name in (pages or []):
            page_dir = os.path.join(pages_dir, page_name)
            os.makedirs(page_dir, exist_ok=True)
            # Write page.json
            with open(os.path.join(page_dir, 'page.json'), 'w') as f:
                json.dump({'displayName': page_name}, f)

            if visuals_per_page and page_name in visuals_per_page:
                vis_dir = os.path.join(page_dir, 'visuals')
                for vis_name in visuals_per_page[page_name]:
                    vd = os.path.join(vis_dir, vis_name)
                    os.makedirs(vd, exist_ok=True)
                    with open(os.path.join(vd, 'visual.json'), 'w') as f:
                        json.dump({'visualType': 'table'}, f)

        return proj_dir

    def test_complete_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = self._make_project(tmpdir, pages=['p1'], visuals_per_page={'p1': ['v1']})
            issues = PBIPValidator.validate_cross_references(proj)
            self.assertEqual(len(issues), 0)

    def test_missing_page_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = self._make_project(tmpdir, pages=['p1'])
            # Remove page.json
            os.remove(os.path.join(proj, 'TestProject.Report', 'pages', 'p1', 'page.json'))
            issues = PBIPValidator.validate_cross_references(proj)
            has_missing = any('page.json missing' in i['message'] for i in issues)
            self.assertTrue(has_missing)

    def test_missing_visual_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = self._make_project(tmpdir, pages=['p1'], visuals_per_page={'p1': ['v1']})
            # Remove visual.json
            os.remove(os.path.join(proj, 'TestProject.Report', 'pages', 'p1', 'visuals', 'v1', 'visual.json'))
            issues = PBIPValidator.validate_cross_references(proj)
            has_missing = any('visual.json missing' in i['message'] for i in issues)
            self.assertTrue(has_missing)

    def test_no_report_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = os.path.join(tmpdir, 'Empty')
            os.makedirs(proj)
            issues = PBIPValidator.validate_cross_references(proj)
            self.assertEqual(len(issues), 0)  # No report dir → nothing to check


class TestSeverityLevels(unittest.TestCase):
    def test_severity_constants(self):
        self.assertEqual(PBIPValidator._SEVERITY_ERROR, 'ERROR')
        self.assertEqual(PBIPValidator._SEVERITY_WARNING, 'WARNING')
        self.assertEqual(PBIPValidator._SEVERITY_INFO, 'INFO')

    def test_m_errors_are_error_severity(self):
        m = 'let x = 1'
        issues = PBIPValidator.validate_m_expression(m)
        for issue in issues:
            self.assertEqual(issue['severity'], 'ERROR')

    def test_indentation_issues_are_warnings(self):
        content = "table 'X'\n\t col\n"
        issues = PBIPValidator.validate_tmdl_indentation(content)
        for issue in issues:
            self.assertEqual(issue['severity'], 'WARNING')


if __name__ == '__main__':
    unittest.main()
