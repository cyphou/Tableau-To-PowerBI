"""Sprint 111 — Schema drift detection tests.

Tests for detecting added/removed/modified columns, calculations,
worksheets, relationships, parameters, and filters between extraction
snapshots.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))

from schema_drift import (
    SchemaDriftEntry,
    SchemaDriftReport,
    detect_schema_drift,
    load_snapshot,
    save_snapshot,
)


class TestSchemaDriftEntry(unittest.TestCase):
    """SchemaDriftEntry data class."""

    def test_to_dict(self):
        e = SchemaDriftEntry('column', 'added', 'Revenue', table='Sales')
        d = e.to_dict()
        self.assertEqual(d['category'], 'column')
        self.assertEqual(d['change_type'], 'added')
        self.assertEqual(d['name'], 'Revenue')
        self.assertEqual(d['table'], 'Sales')

    def test_repr(self):
        e = SchemaDriftEntry('table', 'removed', 'OldTable')
        self.assertIn('removed', repr(e))


class TestSchemaDriftReport(unittest.TestCase):
    """SchemaDriftReport collection."""

    def test_empty_report(self):
        r = SchemaDriftReport()
        self.assertFalse(r.has_drift)
        self.assertIn('No schema drift', r.summary())

    def test_with_entries(self):
        entries = [
            SchemaDriftEntry('column', 'added', 'NewCol', 'T1'),
            SchemaDriftEntry('column', 'removed', 'OldCol', 'T1'),
            SchemaDriftEntry('table', 'added', 'NewTable'),
        ]
        r = SchemaDriftReport(entries, source_name='test.twbx')
        self.assertTrue(r.has_drift)
        self.assertEqual(len(r.added), 2)
        self.assertEqual(len(r.removed), 1)
        self.assertEqual(len(r.by_category('column')), 2)

    def test_to_json(self):
        entries = [SchemaDriftEntry('measure', 'modified', 'Sum of Sales')]
        r = SchemaDriftReport(entries)
        j = r.to_json()
        data = json.loads(j)
        self.assertTrue(data['has_drift'])
        self.assertEqual(data['total_changes'], 1)

    def test_save_load(self):
        entries = [SchemaDriftEntry('table', 'added', 'NewT')]
        r = SchemaDriftReport(entries, source_name='wb')
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'drift.json')
            r.save(path)
            self.assertTrue(os.path.isfile(path))
            with open(path) as f:
                data = json.load(f)
            self.assertEqual(data['total_changes'], 1)

    def test_summary_format(self):
        entries = [
            SchemaDriftEntry('column', 'added', 'A'),
            SchemaDriftEntry('column', 'added', 'B'),
            SchemaDriftEntry('column', 'removed', 'C'),
            SchemaDriftEntry('worksheet', 'modified', 'Sheet1'),
        ]
        r = SchemaDriftReport(entries)
        s = r.summary()
        self.assertIn('column: +2, -1', s)
        self.assertIn('worksheet: ~1', s)


class TestDetectTableDrift(unittest.TestCase):
    """Detect table-level changes."""

    def test_added_table(self):
        prev = {'datasources': [{'tables': [{'name': 'A', 'columns': []}]}]}
        curr = {'datasources': [{'tables': [
            {'name': 'A', 'columns': []},
            {'name': 'B', 'columns': []},
        ]}]}
        report = detect_schema_drift(curr, prev)
        tables_added = [e for e in report.entries
                        if e.category == 'table' and e.change_type == 'added']
        self.assertEqual(len(tables_added), 1)
        self.assertEqual(tables_added[0].name, 'B')

    def test_removed_table(self):
        prev = {'datasources': [{'tables': [
            {'name': 'A', 'columns': []},
            {'name': 'B', 'columns': []},
        ]}]}
        curr = {'datasources': [{'tables': [{'name': 'A', 'columns': []}]}]}
        report = detect_schema_drift(curr, prev)
        removed = [e for e in report.entries
                   if e.category == 'table' and e.change_type == 'removed']
        self.assertEqual(len(removed), 1)
        self.assertEqual(removed[0].name, 'B')

    def test_no_drift(self):
        data = {'datasources': [{'tables': [{'name': 'T', 'columns': []}]}]}
        report = detect_schema_drift(data, data)
        self.assertFalse(report.has_drift)


class TestDetectColumnDrift(unittest.TestCase):
    """Detect column-level changes within tables."""

    def test_added_column(self):
        prev = {'datasources': [{'tables': [{'name': 'T',
                'columns': [{'name': 'ID', 'datatype': 'integer'}]}]}]}
        curr = {'datasources': [{'tables': [{'name': 'T',
                'columns': [
                    {'name': 'ID', 'datatype': 'integer'},
                    {'name': 'Revenue', 'datatype': 'double'},
                ]}]}]}
        report = detect_schema_drift(curr, prev)
        added = [e for e in report.entries
                 if e.category == 'column' and e.change_type == 'added']
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0].name, 'Revenue')
        self.assertEqual(added[0].table, 'T')

    def test_removed_column(self):
        prev = {'datasources': [{'tables': [{'name': 'T',
                'columns': [
                    {'name': 'ID', 'datatype': 'integer'},
                    {'name': 'Old', 'datatype': 'string'},
                ]}]}]}
        curr = {'datasources': [{'tables': [{'name': 'T',
                'columns': [{'name': 'ID', 'datatype': 'integer'}]}]}]}
        report = detect_schema_drift(curr, prev)
        removed = [e for e in report.entries
                   if e.category == 'column' and e.change_type == 'removed']
        self.assertEqual(len(removed), 1)
        self.assertEqual(removed[0].name, 'Old')

    def test_type_change(self):
        prev = {'datasources': [{'tables': [{'name': 'T',
                'columns': [{'name': 'X', 'datatype': 'string'}]}]}]}
        curr = {'datasources': [{'tables': [{'name': 'T',
                'columns': [{'name': 'X', 'datatype': 'integer'}]}]}]}
        report = detect_schema_drift(curr, prev)
        modified = [e for e in report.entries
                    if e.category == 'column' and e.change_type == 'modified']
        self.assertEqual(len(modified), 1)
        self.assertIn('type changed', modified[0].detail)


class TestDetectCalculationDrift(unittest.TestCase):
    """Detect calculation formula changes."""

    def test_added_calculation(self):
        prev = {'calculations': [{'name': 'CalcA', 'formula': 'SUM([X])'}]}
        curr = {'calculations': [
            {'name': 'CalcA', 'formula': 'SUM([X])'},
            {'name': 'CalcB', 'formula': 'AVG([Y])'},
        ]}
        report = detect_schema_drift(curr, prev)
        added = [e for e in report.entries if e.category == 'calculation' and e.change_type == 'added']
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0].name, 'CalcB')

    def test_modified_formula(self):
        prev = {'calculations': [{'name': 'Calc', 'formula': 'SUM([X])'}]}
        curr = {'calculations': [{'name': 'Calc', 'formula': 'AVG([X])'}]}
        report = detect_schema_drift(curr, prev)
        modified = [e for e in report.entries if e.category == 'calculation' and e.change_type == 'modified']
        self.assertEqual(len(modified), 1)


class TestDetectWorksheetDrift(unittest.TestCase):
    """Detect worksheet changes."""

    def test_added_worksheet(self):
        prev = {'worksheets': [{'name': 'Sheet1'}]}
        curr = {'worksheets': [{'name': 'Sheet1'}, {'name': 'Sheet2'}]}
        report = detect_schema_drift(curr, prev)
        added = [e for e in report.entries if e.category == 'worksheet' and e.change_type == 'added']
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0].name, 'Sheet2')

    def test_modified_fields(self):
        prev = {'worksheets': [{'name': 'S', 'fields': [{'name': 'F1'}, {'name': 'F2'}]}]}
        curr = {'worksheets': [{'name': 'S', 'fields': [{'name': 'F1'}, {'name': 'F3'}]}]}
        report = detect_schema_drift(curr, prev)
        modified = [e for e in report.entries if e.category == 'worksheet' and e.change_type == 'modified']
        self.assertEqual(len(modified), 1)
        self.assertIn('fields', modified[0].detail)


class TestDetectRelationshipDrift(unittest.TestCase):
    """Detect relationship changes."""

    def test_added_relationship(self):
        prev = {'datasources': [{'tables': [], 'relationships': []}]}
        curr = {'datasources': [{'tables': [], 'relationships': [
            {'from_table': 'A', 'from_column': 'id', 'to_table': 'B', 'to_column': 'a_id'}
        ]}]}
        report = detect_schema_drift(curr, prev)
        added = [e for e in report.entries if e.category == 'relationship']
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0].change_type, 'added')

    def test_removed_relationship(self):
        prev = {'datasources': [{'tables': [], 'relationships': [
            {'from_table': 'A', 'from_column': 'id', 'to_table': 'B', 'to_column': 'a_id'}
        ]}]}
        curr = {'datasources': [{'tables': [], 'relationships': []}]}
        report = detect_schema_drift(curr, prev)
        removed = [e for e in report.entries if e.category == 'relationship']
        self.assertEqual(len(removed), 1)
        self.assertEqual(removed[0].change_type, 'removed')


class TestDetectParameterDrift(unittest.TestCase):
    """Detect parameter changes."""

    def test_added_parameter(self):
        prev = {'parameters': []}
        curr = {'parameters': [{'name': 'P1', 'current_value': '10'}]}
        report = detect_schema_drift(curr, prev)
        added = [e for e in report.entries if e.category == 'parameter']
        self.assertEqual(len(added), 1)

    def test_modified_value(self):
        prev = {'parameters': [{'name': 'P1', 'current_value': '10'}]}
        curr = {'parameters': [{'name': 'P1', 'current_value': '20'}]}
        report = detect_schema_drift(curr, prev)
        modified = [e for e in report.entries if e.category == 'parameter' and e.change_type == 'modified']
        self.assertEqual(len(modified), 1)


class TestDetectFilterDrift(unittest.TestCase):
    """Detect filter changes."""

    def test_added_filter(self):
        prev = {'filters': []}
        curr = {'filters': [{'field': 'Region'}]}
        report = detect_schema_drift(curr, prev)
        added = [e for e in report.entries if e.category == 'filter']
        self.assertEqual(len(added), 1)


class TestSnapshotIO(unittest.TestCase):
    """Save and load extraction snapshots."""

    def test_save_and_load(self):
        data = {
            'datasources': [{'tables': [{'name': 'T1', 'columns': []}]}],
            'worksheets': [{'name': 'Sheet1'}],
            'calculations': [{'name': 'Calc1', 'formula': 'SUM([X])'}],
            'parameters': [],
            'filters': [],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            save_snapshot(data, tmpdir)
            loaded = load_snapshot(tmpdir)
            self.assertEqual(len(loaded['datasources']), 1)
            self.assertEqual(len(loaded['worksheets']), 1)
            self.assertEqual(len(loaded['calculations']), 1)

    def test_load_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            loaded = load_snapshot(tmpdir)
            self.assertEqual(loaded['datasources'], [])


class TestFullDriftScenario(unittest.TestCase):
    """End-to-end drift detection with complex changes."""

    def test_multiple_changes(self):
        prev = {
            'datasources': [{'tables': [
                {'name': 'Sales', 'columns': [
                    {'name': 'OrderID', 'datatype': 'integer'},
                    {'name': 'Amount', 'datatype': 'double'},
                    {'name': 'OldCol', 'datatype': 'string'},
                ]},
            ], 'relationships': []}],
            'calculations': [
                {'name': 'TotalSales', 'formula': 'SUM([Amount])'},
            ],
            'worksheets': [{'name': 'Dashboard'}],
            'parameters': [{'name': 'TopN', 'current_value': '10'}],
            'filters': [{'field': 'Region'}],
        }
        curr = {
            'datasources': [{'tables': [
                {'name': 'Sales', 'columns': [
                    {'name': 'OrderID', 'datatype': 'integer'},
                    {'name': 'Amount', 'datatype': 'decimal'},  # type changed
                    {'name': 'NewCol', 'datatype': 'string'},   # added, OldCol removed
                ]},
                {'name': 'Products', 'columns': []},  # new table
            ], 'relationships': [
                {'from_table': 'Sales', 'from_column': 'ProductID',
                 'to_table': 'Products', 'to_column': 'ID'},
            ]}],
            'calculations': [
                {'name': 'TotalSales', 'formula': 'SUM([Amount]) + 0'},  # modified
                {'name': 'AvgSales', 'formula': 'AVG([Amount])'},         # new
            ],
            'worksheets': [
                {'name': 'Dashboard'},
                {'name': 'Detail'},  # new
            ],
            'parameters': [{'name': 'TopN', 'current_value': '20'}],  # modified
            'filters': [{'field': 'Region'}, {'field': 'Category'}],  # added
        }

        report = detect_schema_drift(curr, prev, source_name='test.twbx')
        self.assertTrue(report.has_drift)
        self.assertEqual(report.source_name, 'test.twbx')

        # Check specific changes
        self.assertTrue(any(
            e.category == 'table' and e.change_type == 'added' and e.name == 'Products'
            for e in report.entries
        ))
        self.assertTrue(any(
            e.category == 'column' and e.change_type == 'added' and e.name == 'NewCol'
            for e in report.entries
        ))
        self.assertTrue(any(
            e.category == 'column' and e.change_type == 'removed' and e.name == 'OldCol'
            for e in report.entries
        ))
        self.assertTrue(any(
            e.category == 'column' and e.change_type == 'modified' and e.name == 'Amount'
            for e in report.entries
        ))
        self.assertTrue(any(
            e.category == 'relationship' and e.change_type == 'added'
            for e in report.entries
        ))
        self.assertTrue(any(
            e.category == 'calculation' and e.change_type == 'modified'
            for e in report.entries
        ))
        self.assertTrue(any(
            e.category == 'worksheet' and e.change_type == 'added' and e.name == 'Detail'
            for e in report.entries
        ))

        # Summary should mention all categories
        s = report.summary()
        self.assertIn('table:', s)
        self.assertIn('column:', s)
        self.assertIn('calculation:', s)
        self.assertIn('worksheet:', s)


if __name__ == '__main__':
    unittest.main()
