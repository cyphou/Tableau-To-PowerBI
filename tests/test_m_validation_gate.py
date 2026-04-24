"""Sprint 129.2 — M-partition validation gate tests.

Verifies that ``_validate_m_partitions`` walks every M partition in a
generated model, records issues to the recovery report, and is
non-blocking (always returns; never raises; never aborts generation).
"""

import unittest
from unittest.mock import MagicMock

from powerbi_import.tmdl_generator import _validate_m_partitions
from powerbi_import.recovery_report import RecoveryReport


def _model(*partitions):
    return {
        'model': {
            'tables': [
                {
                    'name': f'T{i}',
                    'partitions': [
                        {
                            'name': f'P{i}',
                            'mode': 'import',
                            'source': {'type': 'm', 'expression': expr},
                        }
                    ],
                }
                for i, expr in enumerate(partitions)
            ]
        }
    }


class TestMValidationGate(unittest.TestCase):

    def test_clean_model_zero_issues(self):
        m = 'let Source = #table({"a"}, {{1}}) in Source'
        model = _model(m, m)
        recovery = RecoveryReport('test')
        failing = _validate_m_partitions(model, recovery=recovery)
        self.assertEqual(failing, 0)
        self.assertFalse(recovery.has_repairs)

    def test_unbalanced_parens_recorded(self):
        # Trailing unmatched paren
        bad = 'let Source = Table.FromRecords({[a=1]} in Source'
        model = _model(bad)
        recovery = RecoveryReport('test')
        failing = _validate_m_partitions(model, recovery=recovery)
        self.assertGreaterEqual(failing, 1)
        self.assertTrue(recovery.has_repairs)

    def test_skips_non_m_partitions(self):
        # DAX-table partition (calculated table) → skipped
        model = {
            'model': {
                'tables': [
                    {
                        'name': 'T',
                        'partitions': [
                            {'name': 'P', 'source': {'type': 'calculated',
                                                      'expression': 'NOT M'}}
                        ],
                    }
                ]
            }
        }
        failing = _validate_m_partitions(model, recovery=RecoveryReport('t'))
        self.assertEqual(failing, 0)

    def test_skips_empty_expression(self):
        model = _model('', '   ')
        failing = _validate_m_partitions(model, recovery=RecoveryReport('t'))
        self.assertEqual(failing, 0)

    def test_validator_exception_logged_not_raised(self):
        # Patch the validator to raise — gate must still return
        import powerbi_import.tmdl_generator as tg

        original = tg._validate_m_partitions
        # Build a fake model and inject a broken validator path by
        # monkey-patching the import inside the function via sys.modules.
        import sys
        fake = MagicMock()
        fake.validate_m_query = MagicMock(side_effect=RuntimeError('boom'))
        sys.modules['powerbi_import.m_validator'] = fake
        try:
            model = _model('let x = 1 in x')
            recovery = RecoveryReport('t')
            failing = _validate_m_partitions(model, recovery=recovery)
            self.assertEqual(failing, 1)
            self.assertTrue(recovery.has_repairs)
        finally:
            del sys.modules['powerbi_import.m_validator']
            # Re-import to restore real module for downstream tests
            import importlib
            importlib.import_module('powerbi_import.m_validator')

    def test_no_recovery_argument_is_safe(self):
        bad = 'let x = ( in x'
        model = _model(bad)
        # Must not crash when recovery is None
        failing = _validate_m_partitions(model, recovery=None)
        self.assertGreaterEqual(failing, 1)

    def test_empty_model(self):
        self.assertEqual(_validate_m_partitions({}, recovery=None), 0)
        self.assertEqual(
            _validate_m_partitions({'model': {'tables': []}}, recovery=None), 0
        )


if __name__ == '__main__':
    unittest.main()
