"""Tests for Sprint 62 — RLS Consolidation & Security Hardening."""

import copy
import json
import os
import tempfile
import unittest

from powerbi_import.shared_model import (
    RLSConsolidation,
    consolidate_rls_roles,
    detect_isolated_tables,
    merge_rls_roles,
    validate_rls_principals,
    validate_rls_propagation,
)


def _make_extracted(user_filters=None):
    return {'user_filters': user_filters or []}


def _make_merged(user_filters=None, tables=None, relationships=None):
    return {
        'user_filters': user_filters or [],
        'tables': tables or [],
        'relationships': relationships or [],
    }


class TestConsolidateRLSRoles(unittest.TestCase):
    """Tests for consolidate_rls_roles()."""

    def test_single_workbook_keep(self):
        ext = [_make_extracted([{'name': 'Region', 'table': 'Sales', 'filter_expression': '[Region] = "East"'}])]
        result = consolidate_rls_roles(ext, ['WB1'])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].action, 'keep')
        self.assertEqual(result[0].role_name, 'Region')

    def test_same_filter_dedup(self):
        ext = [
            _make_extracted([{'name': 'Region', 'table': 'Sales', 'filter_expression': '[Region] = "East"'}]),
            _make_extracted([{'name': 'Region', 'table': 'Sales', 'filter_expression': '[Region] = "East"'}]),
        ]
        result = consolidate_rls_roles(ext, ['WB1', 'WB2'])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].action, 'merge')
        self.assertEqual(result[0].merged_expression, '[Region] = "East"')

    def test_different_filters_or_strategy(self):
        ext = [
            _make_extracted([{'name': 'Region', 'table': 'Sales', 'filter_expression': '[Region] = "East"'}]),
            _make_extracted([{'name': 'Region', 'table': 'Sales', 'filter_expression': '[Region] = "West"'}]),
        ]
        result = consolidate_rls_roles(ext, ['WB1', 'WB2'], strategy='or')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].action, 'merge')
        self.assertIn('||', result[0].merged_expression)

    def test_different_filters_and_strategy(self):
        ext = [
            _make_extracted([{'name': 'Region', 'table': 'Sales', 'filter_expression': '[Region] = "East"'}]),
            _make_extracted([{'name': 'Region', 'table': 'Sales', 'filter_expression': '[Region] = "West"'}]),
        ]
        result = consolidate_rls_roles(ext, ['WB1', 'WB2'], strategy='and')
        self.assertEqual(len(result), 1)
        self.assertIn('&&', result[0].merged_expression)

    def test_namespace_strategy(self):
        ext = [
            _make_extracted([{'name': 'Region', 'table': 'Sales', 'filter_expression': '[Region] = "East"'}]),
            _make_extracted([{'name': 'Region', 'table': 'Sales', 'filter_expression': '[Region] = "West"'}]),
        ]
        result = consolidate_rls_roles(ext, ['WB1', 'WB2'], strategy='namespace')
        self.assertEqual(len(result), 2)
        names = {r.role_name for r in result}
        self.assertIn('Region (WB1)', names)
        self.assertIn('Region (WB2)', names)
        for r in result:
            self.assertEqual(r.action, 'namespace')

    def test_different_role_names_kept_separate(self):
        ext = [
            _make_extracted([{'name': 'RoleA', 'table': 'T1', 'filter_expression': 'expr1'}]),
            _make_extracted([{'name': 'RoleB', 'table': 'T2', 'filter_expression': 'expr2'}]),
        ]
        result = consolidate_rls_roles(ext, ['WB1', 'WB2'])
        self.assertEqual(len(result), 2)
        names = {r.role_name for r in result}
        self.assertIn('RoleA', names)
        self.assertIn('RoleB', names)

    def test_empty_filters(self):
        ext = [_make_extracted([]), _make_extracted([])]
        result = consolidate_rls_roles(ext, ['WB1', 'WB2'])
        self.assertEqual(result, [])

    def test_field_fallback_name(self):
        ext = [_make_extracted([{'field': 'Country', 'table': 'Dim', 'formula': 'val'}])]
        result = consolidate_rls_roles(ext, ['WB1'])
        self.assertEqual(result[0].role_name, 'Country')


class TestMergeRLSRoles(unittest.TestCase):
    """Tests for merge_rls_roles()."""

    def test_merge_dedup(self):
        ext = [
            _make_extracted([{'name': 'R1', 'table': 'T', 'filter_expression': 'x'}]),
            _make_extracted([{'name': 'R1', 'table': 'T', 'filter_expression': 'x'}]),
        ]
        result = merge_rls_roles(ext, ['WB1', 'WB2'])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].get('name', result[0].get('field')), 'R1')

    def test_merge_different_kept(self):
        ext = [
            _make_extracted([{'name': 'R1', 'table': 'T', 'filter_expression': 'x'}]),
            _make_extracted([{'name': 'R2', 'table': 'T', 'filter_expression': 'y'}]),
        ]
        result = merge_rls_roles(ext, ['WB1', 'WB2'])
        self.assertEqual(len(result), 2)


class TestValidateRLSPropagation(unittest.TestCase):
    """Tests for validate_rls_propagation()."""

    def test_connected_table_ok(self):
        merged = _make_merged(
            user_filters=[{'name': 'R1', 'table': 'Sales'}],
            tables=[{'name': 'Sales'}, {'name': 'Calendar'}],
            relationships=[{'fromTable': 'Sales', 'toTable': 'Calendar'}],
        )
        result = validate_rls_propagation(merged)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['status'], 'ok')

    def test_isolated_table_warning(self):
        merged = _make_merged(
            user_filters=[{'name': 'R1', 'table': 'Orphan'}],
            tables=[{'name': 'Orphan'}, {'name': 'Sales'}],
            relationships=[],
        )
        result = validate_rls_propagation(merged)
        self.assertEqual(result[0]['status'], 'warning')
        self.assertIn('isolated', result[0]['reason'])

    def test_missing_table_error(self):
        merged = _make_merged(
            user_filters=[{'name': 'R1', 'table': 'Ghost'}],
            tables=[{'name': 'Sales'}],
            relationships=[],
        )
        result = validate_rls_propagation(merged)
        self.assertEqual(result[0]['status'], 'error')
        self.assertIn('not found', result[0]['reason'])

    def test_no_table_specified_warning(self):
        merged = _make_merged(
            user_filters=[{'name': 'R1', 'table': ''}],
            tables=[{'name': 'Sales'}],
            relationships=[],
        )
        result = validate_rls_propagation(merged)
        self.assertEqual(result[0]['status'], 'warning')
        self.assertIn('No table', result[0]['reason'])

    def test_multiple_roles_mixed(self):
        merged = _make_merged(
            user_filters=[
                {'name': 'R1', 'table': 'Sales'},
                {'name': 'R2', 'table': 'Orphan'},
            ],
            tables=[{'name': 'Sales'}, {'name': 'Orphan'}],
            relationships=[{'fromTable': 'Sales', 'toTable': 'Calendar'}],
        )
        result = validate_rls_propagation(merged)
        statuses = {r['role']: r['status'] for r in result}
        self.assertEqual(statuses['R1'], 'ok')
        self.assertEqual(statuses['R2'], 'warning')

    def test_empty_roles(self):
        merged = _make_merged()
        result = validate_rls_propagation(merged)
        self.assertEqual(result, [])


class TestValidateRLSPrincipals(unittest.TestCase):
    """Tests for validate_rls_principals()."""

    def test_upn_detected(self):
        merged = _make_merged(
            user_filters=[{'name': 'R1', 'filter_expression': 'USERPRINCIPALNAME() = "test@example.com"'}],
        )
        result = validate_rls_principals(merged)
        self.assertEqual(len(result), 1)
        self.assertIn('UPN', result[0]['format_detected'])

    def test_username_detected(self):
        merged = _make_merged(
            user_filters=[{'name': 'R1', 'filter_expression': 'USERNAME() = "DOMAIN\\user"'}],
        )
        result = validate_rls_principals(merged)
        self.assertIn('USERNAME', result[0]['format_detected'])

    def test_unknown_format(self):
        merged = _make_merged(
            user_filters=[{'name': 'R1', 'filter_expression': '[Role] = "Admin"'}],
        )
        result = validate_rls_principals(merged)
        self.assertEqual(result[0]['format_detected'], 'unknown')

    def test_empty_expression_skipped(self):
        merged = _make_merged(
            user_filters=[{'name': 'R1', 'filter_expression': ''}],
        )
        result = validate_rls_principals(merged)
        self.assertEqual(result, [])

    def test_field_fallback(self):
        merged = _make_merged(
            user_filters=[{'field': 'R1', 'formula': 'USERPRINCIPALNAME() = "a@b.c"'}],
        )
        result = validate_rls_principals(merged)
        self.assertEqual(result[0]['role'], 'R1')
        self.assertIn('UPN', result[0]['format_detected'])

    def test_expression_truncated(self):
        long_expr = 'USERPRINCIPALNAME() = "' + 'x' * 200 + '"'
        merged = _make_merged(
            user_filters=[{'name': 'R1', 'filter_expression': long_expr}],
        )
        result = validate_rls_principals(merged)
        self.assertLessEqual(len(result[0]['expression']), 100)


class TestDetectIsolatedTables(unittest.TestCase):
    """Tests for detect_isolated_tables()."""

    def test_no_isolated(self):
        merged = _make_merged(
            tables=[{'name': 'A'}, {'name': 'B'}],
            relationships=[{'fromTable': 'A', 'toTable': 'B'}],
        )
        result = detect_isolated_tables(merged)
        self.assertEqual(result, [])

    def test_one_isolated(self):
        merged = _make_merged(
            tables=[{'name': 'A'}, {'name': 'B'}, {'name': 'C'}],
            relationships=[{'fromTable': 'A', 'toTable': 'B'}],
        )
        result = detect_isolated_tables(merged)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['table'], 'C')

    def test_all_isolated(self):
        merged = _make_merged(
            tables=[{'name': 'X'}, {'name': 'Y'}],
            relationships=[],
        )
        result = detect_isolated_tables(merged)
        self.assertEqual(len(result), 2)

    def test_empty(self):
        result = detect_isolated_tables(_make_merged())
        self.assertEqual(result, [])


class TestMergeConfigRLS(unittest.TestCase):
    """Tests for RLS rules in merge config save/load/apply."""

    def _make_assessment(self, rls_consolidations=None):
        """Create a minimal assessment-like object."""
        class FakeAssessment:
            merge_score = 80
            recommendation = 'merge'
            merge_candidates = []
            unique_tables = {}
            parameter_conflicts = []
            parameter_duplicates_removed = 0
            measure_conflicts = []
        a = FakeAssessment()
        if rls_consolidations is not None:
            a.rls_consolidations = rls_consolidations
        return a

    def test_save_with_rls(self):
        from powerbi_import.merge_config import save_merge_config, load_merge_config
        cons = [RLSConsolidation(
            role_name='Region',
            source_workbooks=['WB1', 'WB2'],
            tables_affected=['Sales'],
            filter_expressions={'WB1': 'expr1', 'WB2': 'expr2'},
            action='merge',
            merged_expression='(expr1) || (expr2)',
        )]
        assessment = self._make_assessment(rls_consolidations=cons)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'config.json')
            save_merge_config(assessment, ['WB1', 'WB2'], path, merged={'tables': []})
            config = load_merge_config(path)
            self.assertIn('rls_rules', config)
            self.assertEqual(len(config['rls_rules']), 1)
            self.assertEqual(config['rls_rules'][0]['role_name'], 'Region')
            self.assertEqual(config['rls_rules'][0]['action'], 'merge')

    def test_save_without_rls(self):
        from powerbi_import.merge_config import save_merge_config, load_merge_config
        assessment = self._make_assessment()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'config.json')
            save_merge_config(assessment, ['WB1'], path)
            config = load_merge_config(path)
            self.assertEqual(config.get('rls_rules', []), [])

    def test_apply_stores_rls_rules(self):
        from powerbi_import.merge_config import apply_merge_config
        assessment = self._make_assessment()
        config = {
            'version': '1.0',
            'table_decisions': [],
            'measure_decisions': [],
            'options': {},
            'rls_rules': [
                {'role_name': 'R1', 'action': 'merge', 'strategy': 'and'},
            ],
        }
        apply_merge_config(assessment, config)
        self.assertIn('R1', assessment._rls_rules)
        self.assertEqual(assessment._rls_rules['R1']['strategy'], 'and')


class TestMergeReportSecuritySection(unittest.TestCase):
    """Tests for Security section in merge HTML report."""

    def test_security_section_present(self):
        from powerbi_import.merge_report_html import generate_merge_html_report
        from powerbi_import.shared_model import MergeAssessment

        assessment = MergeAssessment(
            workbooks=['WB1'],
            merge_score=80,
            recommendation='merge',
        )
        merged = {
            'datasources': [{'tables': [{'name': 'Sales'}]}],
            'calculations': [],
            'parameters': [],
            'user_filters': [
                {
                    'name': 'Region',
                    'table': 'Sales',
                    'filter_expression': 'USERPRINCIPALNAME() = "user@test.com"',
                    '_source_workbooks': ['WB1'],
                },
            ],
            'tables': [{'name': 'Sales'}],
            'relationships': [{'fromTable': 'Sales', 'toTable': 'Calendar'}],
        }
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'report.html')
            result = generate_merge_html_report(
                assessment, [{}], ['WB1'], merged,
                model_name='Test', output_path=path,
            )
            with open(result, 'r', encoding='utf-8') as f:
                html = f.read()
            self.assertIn('Security', html)
            self.assertIn('Region', html)
            self.assertIn('RLS Roles', html)

    def test_no_security_section_without_rls(self):
        from powerbi_import.merge_report_html import generate_merge_html_report
        from powerbi_import.shared_model import MergeAssessment

        assessment = MergeAssessment(
            workbooks=['WB1'],
            merge_score=80,
            recommendation='merge',
        )
        merged = {
            'datasources': [{'tables': []}],
            'calculations': [],
            'parameters': [],
            'user_filters': [],
            'tables': [],
            'relationships': [],
        }
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'report.html')
            result = generate_merge_html_report(
                assessment, [{}], ['WB1'], merged,
                model_name='Test', output_path=path,
            )
            with open(result, 'r', encoding='utf-8') as f:
                html = f.read()
            self.assertNotIn('security', html.lower().split('footer')[0].split('script')[0])


if __name__ == '__main__':
    unittest.main()
