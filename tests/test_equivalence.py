"""Tests for Sprint 94 — Cross-Platform Validation & Regression.

Covers:
- Query equivalence framework (measure value comparison)
- Visual screenshot comparison (SSIM-based)
- Regression suite generation and snapshot comparison
- Validation CLI flags
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))


class TestMeasureValueComparison(unittest.TestCase):
    """Tests for measure value equivalence checking."""

    def test_exact_match(self):
        from powerbi_import.equivalence_tester import compare_measure_values
        result = compare_measure_values(
            {'Sales': 100.0, 'Profit': 25.0},
            {'Sales': 100.0, 'Profit': 25.0},
        )
        self.assertEqual(result['passed'], 2)
        self.assertEqual(result['failed'], 0)

    def test_within_tolerance(self):
        from powerbi_import.equivalence_tester import compare_measure_values
        result = compare_measure_values(
            {'Sales': 100.0},
            {'Sales': 100.5},
            tolerance=0.01
        )
        self.assertEqual(result['passed'], 1)
        self.assertEqual(result['failed'], 0)

    def test_exceeds_tolerance(self):
        from powerbi_import.equivalence_tester import compare_measure_values
        result = compare_measure_values(
            {'Sales': 100.0},
            {'Sales': 120.0},
            tolerance=0.01
        )
        self.assertEqual(result['failed'], 1)

    def test_missing_measure(self):
        from powerbi_import.equivalence_tester import compare_measure_values
        result = compare_measure_values(
            {'Sales': 100.0, 'Profit': 50.0},
            {'Sales': 100.0},
        )
        self.assertEqual(len(result['missing']), 1)
        self.assertIn('Profit', result['missing'])

    def test_string_values_exact_match(self):
        from powerbi_import.equivalence_tester import compare_measure_values
        result = compare_measure_values(
            {'Category': 'Electronics'},
            {'Category': 'Electronics'},
        )
        self.assertEqual(result['passed'], 1)

    def test_string_values_mismatch(self):
        from powerbi_import.equivalence_tester import compare_measure_values
        result = compare_measure_values(
            {'Category': 'Electronics'},
            {'Category': 'Furniture'},
        )
        self.assertEqual(result['failed'], 1)

    def test_zero_values(self):
        from powerbi_import.equivalence_tester import compare_measure_values
        result = compare_measure_values(
            {'Count': 0},
            {'Count': 0},
        )
        self.assertEqual(result['passed'], 1)

    def test_empty_measures(self):
        from powerbi_import.equivalence_tester import compare_measure_values
        result = compare_measure_values({}, {})
        self.assertEqual(result['total'], 0)
        self.assertEqual(result['passed'], 0)


class TestScreenshotComparison(unittest.TestCase):
    """Tests for SSIM-based visual comparison."""

    def test_identical_images(self):
        from powerbi_import.equivalence_tester import compare_screenshots
        data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        result = compare_screenshots(data, data)
        self.assertEqual(result['ssim'], 1.0)
        self.assertTrue(result['passed'])

    def test_completely_different(self):
        from powerbi_import.equivalence_tester import compare_screenshots
        data_a = b'\x00' * 100
        data_b = b'\xff' * 100
        result = compare_screenshots(data_a, data_b)
        self.assertLess(result['ssim'], 1.0)

    def test_empty_image(self):
        from powerbi_import.equivalence_tester import compare_screenshots
        result = compare_screenshots(b'', b'\x00' * 100)
        self.assertEqual(result['ssim'], 0.0)
        self.assertFalse(result['passed'])

    def test_custom_threshold(self):
        from powerbi_import.equivalence_tester import compare_screenshots
        data = b'\x89PNG' + b'\x00' * 100
        result = compare_screenshots(data, data, threshold=0.99)
        self.assertTrue(result['passed'])
        self.assertEqual(result['threshold'], 0.99)

    def test_ssim_computation(self):
        from powerbi_import.equivalence_tester import compute_ssim
        data_a = b'\x89PNG\r\n' + b'\x42' * 500
        data_b = b'\x89PNG\r\n' + b'\x42' * 500
        ssim = compute_ssim(data_a, data_b)
        self.assertEqual(ssim, 1.0)


class TestValidationReport(unittest.TestCase):
    """Tests for validation report generation."""

    def test_report_overall_pass(self):
        from powerbi_import.equivalence_tester import generate_validation_report
        measure_results = {'passed': 3, 'failed': 0, 'missing': [], 'total': 3, 'details': []}
        report = generate_validation_report(measure_results)
        self.assertTrue(report['overall_pass'])

    def test_report_overall_fail_on_measures(self):
        from powerbi_import.equivalence_tester import generate_validation_report
        measure_results = {'passed': 2, 'failed': 1, 'missing': [], 'total': 3, 'details': []}
        report = generate_validation_report(measure_results)
        self.assertFalse(report['overall_pass'])

    def test_report_overall_fail_on_missing(self):
        from powerbi_import.equivalence_tester import generate_validation_report
        measure_results = {'passed': 2, 'failed': 0, 'missing': ['X'], 'total': 3, 'details': []}
        report = generate_validation_report(measure_results)
        self.assertFalse(report['overall_pass'])

    def test_report_writes_json(self):
        from powerbi_import.equivalence_tester import generate_validation_report
        measure_results = {'passed': 1, 'failed': 0, 'missing': [], 'total': 1, 'details': []}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'validation.json')
            report = generate_validation_report(measure_results, output_path=path)
            self.assertTrue(os.path.exists(path))
            with open(path) as f:
                data = json.load(f)
            self.assertTrue(data['overall_pass'])


class TestRegressionSnapshot(unittest.TestCase):
    """Tests for regression suite snapshot generation."""

    def test_generate_snapshot(self):
        from powerbi_import.regression_suite import generate_regression_snapshot
        converted = {
            'datasources': [{'tables': [{'name': 'Orders', 'columns': [{'name': 'ID'}]}]}],
            'calculations': [{'name': 'Sales', 'formula': "SUM([Amount])"}],
            'worksheets': [{'name': 'Sheet1', 'fields': ['F1', 'F2']}],
            'filters': [{'field': 'Region'}],
        }
        snap = generate_regression_snapshot(converted)
        self.assertIn('Orders', snap['tables'])
        self.assertEqual(snap['tables']['Orders']['column_count'], 1)
        self.assertIn('Sales', snap['measures'])
        self.assertEqual(snap['filters'], 1)

    def test_snapshot_writes_json(self):
        from powerbi_import.regression_suite import generate_regression_snapshot
        converted = {'datasources': [], 'calculations': [], 'worksheets': [], 'filters': []}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'snapshot.json')
            generate_regression_snapshot(converted, output_path=path)
            self.assertTrue(os.path.exists(path))

    def test_snapshot_formula_hash(self):
        from powerbi_import.regression_suite import generate_regression_snapshot
        converted = {
            'datasources': [],
            'calculations': [{'name': 'M', 'formula': 'SUM([X])'}],
            'worksheets': [], 'filters': [],
        }
        snap = generate_regression_snapshot(converted)
        self.assertIn('formula_hash', snap['measures']['M'])
        self.assertEqual(len(snap['measures']['M']['formula_hash']), 16)


class TestSnapshotComparison(unittest.TestCase):
    """Tests for regression snapshot comparison."""

    def test_identical_snapshots(self):
        from powerbi_import.regression_suite import compare_snapshots
        snap = {
            'tables': {'T1': {'column_count': 3}},
            'measures': {'M1': {'formula_hash': 'abc123'}},
            'filters': 2,
        }
        result = compare_snapshots(snap, snap)
        self.assertTrue(result['passed'])
        self.assertEqual(len(result['drifts']), 0)

    def test_table_added(self):
        from powerbi_import.regression_suite import compare_snapshots
        base = {'tables': {'T1': {'column_count': 3}}, 'measures': {}, 'filters': 0}
        curr = {'tables': {'T1': {'column_count': 3}, 'T2': {'column_count': 2}}, 'measures': {}, 'filters': 0}
        result = compare_snapshots(base, curr)
        self.assertFalse(result['passed'])
        self.assertTrue(any(d['type'] == 'tables_added' for d in result['drifts']))

    def test_table_removed(self):
        from powerbi_import.regression_suite import compare_snapshots
        base = {'tables': {'T1': {'column_count': 3}, 'T2': {'column_count': 2}}, 'measures': {}, 'filters': 0}
        curr = {'tables': {'T1': {'column_count': 3}}, 'measures': {}, 'filters': 0}
        result = compare_snapshots(base, curr)
        self.assertTrue(any(d['type'] == 'tables_removed' for d in result['drifts']))

    def test_column_count_drift(self):
        from powerbi_import.regression_suite import compare_snapshots
        base = {'tables': {'T1': {'column_count': 3}}, 'measures': {}, 'filters': 0}
        curr = {'tables': {'T1': {'column_count': 5}}, 'measures': {}, 'filters': 0}
        result = compare_snapshots(base, curr)
        self.assertTrue(any(d['type'] == 'column_count_changed' for d in result['drifts']))

    def test_measure_changed(self):
        from powerbi_import.regression_suite import compare_snapshots
        base = {'tables': {}, 'measures': {'M': {'formula_hash': 'aaa'}}, 'filters': 0}
        curr = {'tables': {}, 'measures': {'M': {'formula_hash': 'bbb'}}, 'filters': 0}
        result = compare_snapshots(base, curr)
        self.assertTrue(any(d['type'] == 'measure_changed' for d in result['drifts']))

    def test_filter_count_drift(self):
        from powerbi_import.regression_suite import compare_snapshots
        base = {'tables': {}, 'measures': {}, 'filters': 3}
        curr = {'tables': {}, 'measures': {}, 'filters': 5}
        result = compare_snapshots(base, curr)
        self.assertTrue(any(d['type'] == 'filter_count_changed' for d in result['drifts']))


class TestCLIValidationFlags(unittest.TestCase):
    """Tests for --validate-data CLI argument."""

    def test_validate_data_flag(self):
        import migrate
        parser = migrate._build_argument_parser()
        args = parser.parse_args(['test.twbx', '--validate-data'])
        self.assertTrue(args.validate_data)

    def test_validate_data_default_false(self):
        import migrate
        parser = migrate._build_argument_parser()
        args = parser.parse_args(['test.twbx'])
        self.assertFalse(args.validate_data)


if __name__ == '__main__':
    unittest.main()
