"""Tests for powerbi_import/merge_report_html.py — HTML merge report generator."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from powerbi_import.shared_model import (
    MergeAssessment, MergeCandidate, MeasureConflict, TableFingerprint,
    assess_merge, merge_semantic_models,
)
from powerbi_import.merge_report_html import generate_merge_html_report


def _make_datasource(name, conn_type, server, database, tables, calcs=None, rels=None):
    """Factory helper for datasource dicts."""
    return {
        'name': name,
        'connection': {
            'type': conn_type,
            'details': {'server': server, 'database': database},
        },
        'tables': tables,
        'calculations': calcs or [],
        'relationships': rels or [],
    }


def _make_table(name, columns, ttype='table'):
    return {
        'name': name,
        'type': ttype,
        'columns': [{'name': c, 'datatype': 'string'} for c in columns],
    }


def _make_measure(caption, formula):
    return {'caption': caption, 'name': caption, 'formula': formula, 'role': 'measure'}


def _make_calc_column(caption, formula):
    return {'caption': caption, 'name': caption, 'formula': formula, 'role': 'dimension'}


def _make_relationship(from_t, from_c, to_t, to_c):
    return {'from_table': from_t, 'from_column': from_c, 'to_table': to_t, 'to_column': to_c}


# ═══════════════════════════════════════════════════════════════════
#  Fixtures
# ═══════════════════════════════════════════════════════════════════

def _shared_workbooks():
    """Build two workbooks with shared 'Orders' table + one unique table each."""
    wb_a = {
        'datasources': [_make_datasource(
            'DS_A', 'sqlserver', 'srv1', 'db1',
            tables=[
                _make_table('[dbo].[Orders]', ['OrderID', 'Amount', 'Date']),
                _make_table('[dbo].[Customers]', ['CustID', 'Name']),
            ],
            calcs=[
                _make_measure('Total Sales', 'SUM([Amount])'),
                _make_measure('Order Count', 'COUNT([OrderID])'),
            ],
            rels=[_make_relationship('Orders', 'CustID', 'Customers', 'CustID')],
        )],
        'worksheets': [{'name': 'Sales Overview'}],
        'dashboards': [{'name': 'Dashboard A'}],
        'calculations': [],
        'parameters': [{'name': 'DateRange', 'datatype': 'date', 'domain_type': 'range', 'current_value': '2024-01-01'}],
        'filters': [], 'stories': [], 'actions': [],
        'sets': [], 'groups': [], 'bins': [],
        'hierarchies': [], 'sort_orders': [], 'aliases': {},
        'custom_sql': [], 'user_filters': [],
    }

    wb_b = {
        'datasources': [_make_datasource(
            'DS_B', 'sqlserver', 'srv1', 'db1',
            tables=[
                _make_table('[dbo].[Orders]', ['OrderID', 'Amount', 'Date', 'Region']),
                _make_table('[dbo].[Products]', ['ProdID', 'Name', 'Price']),
            ],
            calcs=[
                _make_measure('Total Sales', 'SUMX(Orders, [Qty] * [Price])'),  # conflict!
                _make_measure('Avg Price', 'AVERAGE([Price])'),
            ],
            rels=[
                _make_relationship('Orders', 'CustID', 'Customers', 'CustID'),
                _make_relationship('Orders', 'ProdID', 'Products', 'ProdID'),
            ],
        )],
        'worksheets': [{'name': 'Product Detail'}, {'name': 'Region View'}],
        'dashboards': [],
        'calculations': [],
        'parameters': [{'name': 'DateRange', 'datatype': 'date', 'domain_type': 'range', 'current_value': '2024-01-01'}],
        'filters': [], 'stories': [], 'actions': [],
        'sets': [], 'groups': [], 'bins': [],
        'hierarchies': [], 'sort_orders': [], 'aliases': {},
        'custom_sql': [], 'user_filters': [],
    }

    return [wb_a, wb_b], ['SalesOverview', 'ProductDetail']


class TestMergeHtmlReportGeneration(unittest.TestCase):
    """Test that generate_merge_html_report produces valid HTML."""

    def setUp(self):
        self.all_extracted, self.workbook_names = _shared_workbooks()
        self.assessment = assess_merge(self.all_extracted, self.workbook_names)
        self.merged = merge_semantic_models(
            self.all_extracted, self.assessment, 'TestShared'
        )
        self.tmpdir = tempfile.mkdtemp()

    def _generate(self, **kwargs):
        path = os.path.join(self.tmpdir, 'report.html')
        return generate_merge_html_report(
            assessment=self.assessment,
            all_extracted=self.all_extracted,
            workbook_names=self.workbook_names,
            merged=self.merged,
            model_name='TestShared',
            output_path=path,
            **kwargs,
        )

    def test_generates_html_file(self):
        path = self._generate()
        self.assertTrue(os.path.isfile(path))
        self.assertTrue(path.endswith('.html'))

    def test_html_is_valid_structure(self):
        path = self._generate()
        with open(path, encoding='utf-8') as f:
            content = f.read()
        self.assertIn('<!DOCTYPE html>', content)
        self.assertIn('</html>', content)
        self.assertIn('<body>', content)
        self.assertIn('</body>', content)

    def test_contains_model_name(self):
        path = self._generate()
        with open(path, encoding='utf-8') as f:
            content = f.read()
        self.assertIn('TestShared', content)

    def test_contains_workbook_names(self):
        path = self._generate()
        with open(path, encoding='utf-8') as f:
            content = f.read()
        self.assertIn('SalesOverview', content)
        self.assertIn('ProductDetail', content)

    def test_contains_executive_summary(self):
        path = self._generate()
        with open(path, encoding='utf-8') as f:
            content = f.read()
        self.assertIn('Executive Summary', content)
        self.assertIn('Merge Score', content)

    def test_contains_source_inventory(self):
        path = self._generate()
        with open(path, encoding='utf-8') as f:
            content = f.read()
        self.assertIn('Tableau Source Inventory', content)
        self.assertIn('sqlserver', content)

    def test_contains_merged_output(self):
        path = self._generate()
        with open(path, encoding='utf-8') as f:
            content = f.read()
        self.assertIn('Power BI Merged Output', content)
        self.assertIn('Merged Tables', content)

    def test_contains_merge_details(self):
        path = self._generate()
        with open(path, encoding='utf-8') as f:
            content = f.read()
        self.assertIn('Merge Details', content)
        self.assertIn('Column Overlap', content)

    def test_contains_measure_mapping(self):
        path = self._generate()
        with open(path, encoding='utf-8') as f:
            content = f.read()
        self.assertIn('Measure Mapping', content)

    def test_contains_relationship_mapping(self):
        path = self._generate()
        with open(path, encoding='utf-8') as f:
            content = f.read()
        self.assertIn('Relationship Mapping', content)

    def test_merge_score_displayed(self):
        path = self._generate()
        with open(path, encoding='utf-8') as f:
            content = f.read()
        self.assertIn(f'{self.assessment.merge_score}/100', content)

    def test_tables_saved_displayed(self):
        path = self._generate()
        with open(path, encoding='utf-8') as f:
            content = f.read()
        self.assertIn('Tables Saved', content)

    def test_measure_conflict_shown(self):
        """Total Sales has different formulas → should show conflict."""
        path = self._generate()
        with open(path, encoding='utf-8') as f:
            content = f.read()
        self.assertIn('Total Sales', content)
        self.assertIn('Conflicts', content)

    def test_namespaced_measure_shown(self):
        """Conflicting measures get (workbook) suffix in merged output."""
        path = self._generate()
        with open(path, encoding='utf-8') as f:
            content = f.read()
        # Should contain at least one namespaced version
        self.assertTrue(
            'Total Sales (SalesOverview)' in content or
            'Total Sales (ProductDetail)' in content
        )

    def test_unique_table_shown(self):
        """Customers and Products are unique to one workbook each."""
        path = self._generate()
        with open(path, encoding='utf-8') as f:
            content = f.read()
        # Products only in ProductDetail
        self.assertIn('Products', content)

    def test_merged_tables_have_source_workbooks(self):
        """Orders table should show both workbooks as sources."""
        path = self._generate()
        with open(path, encoding='utf-8') as f:
            content = f.read()
        self.assertIn('Merged', content)

    def test_relationship_dedup_shown(self):
        path = self._generate()
        with open(path, encoding='utf-8') as f:
            content = f.read()
        self.assertIn('duplicates removed', content)

    def test_flow_diagram_present(self):
        """The flow diagram (Tableau → Merge → PBI) should be present."""
        path = self._generate()
        with open(path, encoding='utf-8') as f:
            content = f.read()
        self.assertIn('Merge Engine', content)
        self.assertIn('Thin Reports', content)

    def test_javascript_present(self):
        path = self._generate()
        with open(path, encoding='utf-8') as f:
            content = f.read()
        self.assertIn('toggleSection', content)
        self.assertIn('switchTab', content)

    def test_css_styling_present(self):
        path = self._generate()
        with open(path, encoding='utf-8') as f:
            content = f.read()
        self.assertIn('.card', content)
        self.assertIn('.stat', content)
        self.assertIn('.connector-tag', content)


class TestMergeHtmlNoOverlap(unittest.TestCase):
    """Test with workbooks that have no table overlap."""

    def test_no_merge_candidates_message(self):
        wb_a = {
            'datasources': [_make_datasource(
                'DS_A', 'sqlserver', 'srv1', 'db1',
                tables=[_make_table('[dbo].[Sales]', ['ID', 'Amount'])],
            )],
            'worksheets': [], 'dashboards': [], 'calculations': [],
            'parameters': [], 'filters': [], 'stories': [], 'actions': [],
            'sets': [], 'groups': [], 'bins': [],
            'hierarchies': [], 'sort_orders': [], 'aliases': {},
            'custom_sql': [], 'user_filters': [],
        }
        wb_b = {
            'datasources': [_make_datasource(
                'DS_B', 'postgres', 'srv2', 'db2',
                tables=[_make_table('products', ['ProdID', 'Name'])],
            )],
            'worksheets': [], 'dashboards': [], 'calculations': [],
            'parameters': [], 'filters': [], 'stories': [], 'actions': [],
            'sets': [], 'groups': [], 'bins': [],
            'hierarchies': [], 'sort_orders': [], 'aliases': {},
            'custom_sql': [], 'user_filters': [],
        }
        names = ['WB_A', 'WB_B']
        assessment = assess_merge([wb_a, wb_b], names)
        merged = merge_semantic_models([wb_a, wb_b], assessment, 'NoOverlap')

        tmpdir = tempfile.mkdtemp()
        path = generate_merge_html_report(
            assessment=assessment,
            all_extracted=[wb_a, wb_b],
            workbook_names=names,
            merged=merged,
            model_name='NoOverlap',
            output_path=os.path.join(tmpdir, 'report.html'),
        )
        with open(path, encoding='utf-8') as f:
            content = f.read()
        self.assertIn('unique across workbooks', content)


class TestMergeHtmlEdgeCases(unittest.TestCase):
    """Test edge cases."""

    def test_empty_workbooks(self):
        """No datasources in either workbook."""
        empty = {
            'datasources': [], 'worksheets': [], 'dashboards': [],
            'calculations': [], 'parameters': [], 'filters': [],
            'stories': [], 'actions': [], 'sets': [], 'groups': [],
            'bins': [], 'hierarchies': [], 'sort_orders': [],
            'aliases': {}, 'custom_sql': [], 'user_filters': [],
        }
        names = ['Empty1', 'Empty2']
        assessment = assess_merge([empty, empty], names)
        merged = merge_semantic_models([empty, empty], assessment, 'EmptyModel')

        tmpdir = tempfile.mkdtemp()
        path = generate_merge_html_report(
            assessment=assessment,
            all_extracted=[empty, empty],
            workbook_names=names,
            merged=merged,
            model_name='EmptyModel',
            output_path=os.path.join(tmpdir, 'report.html'),
        )
        self.assertTrue(os.path.isfile(path))
        with open(path, encoding='utf-8') as f:
            content = f.read()
        self.assertIn('</html>', content)

    def test_special_characters_in_names(self):
        """Workbook names with special chars should be HTML-escaped."""
        wb = {
            'datasources': [_make_datasource(
                'DS', 'sqlserver', 'srv', 'db',
                tables=[_make_table('[dbo].[T]', ['Col'])],
            )],
            'worksheets': [], 'dashboards': [], 'calculations': [],
            'parameters': [], 'filters': [], 'stories': [], 'actions': [],
            'sets': [], 'groups': [], 'bins': [],
            'hierarchies': [], 'sort_orders': [], 'aliases': {},
            'custom_sql': [], 'user_filters': [],
        }
        names = ['<script>alert(1)</script>', 'Normal']
        assessment = assess_merge([wb, wb], names)
        merged = merge_semantic_models([wb, wb], assessment, 'XSSTest')

        tmpdir = tempfile.mkdtemp()
        path = generate_merge_html_report(
            assessment=assessment,
            all_extracted=[wb, wb],
            workbook_names=names,
            merged=merged,
            model_name='XSSTest',
            output_path=os.path.join(tmpdir, 'report.html'),
        )
        with open(path, encoding='utf-8') as f:
            content = f.read()
        # Script tag should be escaped, not raw
        self.assertNotIn('<script>alert(1)</script>', content)
        self.assertIn('&lt;script&gt;', content)

    def test_three_workbooks(self):
        """Three workbooks should all appear in the report."""
        def _wb(table_name, cols):
            return {
                'datasources': [_make_datasource(
                    'DS', 'sqlserver', 'srv1', 'db1',
                    tables=[_make_table(table_name, cols)],
                )],
                'worksheets': [], 'dashboards': [], 'calculations': [],
                'parameters': [], 'filters': [], 'stories': [], 'actions': [],
                'sets': [], 'groups': [], 'bins': [],
                'hierarchies': [], 'sort_orders': [], 'aliases': {},
                'custom_sql': [], 'user_filters': [],
            }

        wbs = [
            _wb('[dbo].[Orders]', ['ID', 'Amount']),
            _wb('[dbo].[Orders]', ['ID', 'Amount', 'Date']),
            _wb('[dbo].[Orders]', ['ID', 'Amount']),
        ]
        names = ['Alpha', 'Beta', 'Gamma']
        assessment = assess_merge(wbs, names)
        merged = merge_semantic_models(wbs, assessment, 'TripleModel')

        tmpdir = tempfile.mkdtemp()
        path = generate_merge_html_report(
            assessment=assessment,
            all_extracted=wbs,
            workbook_names=names,
            merged=merged,
            model_name='TripleModel',
            output_path=os.path.join(tmpdir, 'report.html'),
        )
        with open(path, encoding='utf-8') as f:
            content = f.read()
        self.assertIn('Alpha', content)
        self.assertIn('Beta', content)
        self.assertIn('Gamma', content)


if __name__ == '__main__':
    unittest.main()
