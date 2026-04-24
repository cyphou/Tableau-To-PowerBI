"""Sprint 130.3 — Recovery report v2 HTML output tests."""

import os
import tempfile
import unittest

from powerbi_import.recovery_report import RecoveryReport


class TestRecoveryHtml(unittest.TestCase):

    def _new(self, name='test_report'):
        return RecoveryReport(name)

    def test_save_html_empty_report(self):
        recovery = self._new('empty')
        with tempfile.TemporaryDirectory() as tmp:
            path = recovery.save_html(output_dir=tmp)
            self.assertTrue(os.path.exists(path))
            self.assertTrue(path.endswith('empty_recovery.html'))
            html = open(path, encoding='utf-8').read()
            # No-repairs message present
            self.assertIn('No automatic repairs', html)
            # Stat grid still rendered
            self.assertIn('Total Repairs', html)
            # Header
            self.assertIn('Self-Healing Recovery Report', html)

    def test_save_html_with_repairs(self):
        recovery = self._new('busy')
        recovery.record(
            category='tmdl', repair_type='broken_column_ref',
            description="Measure 'Profit YoY' refs missing column",
            action='Hidden with MigrationNote',
            severity='warning', item_name='Profit YoY',
            original_value='SUM([Region2])',
            repaired_value='SUM([Region])',
            follow_up='Review and rewire',
        )
        recovery.record(
            category='m_query', repair_type='paren_balance',
            description='Unbalanced parens in M partition',
            action='Auto-closed 2 trailing parens',
            severity='info', item_name='Sales/P0',
        )
        recovery.record(
            category='visual', repair_type='fallback',
            description='Unmapped visual type',
            action='Fell back to table',
            severity='error', item_name='Sales Story',
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = recovery.save_html(output_dir=tmp)
            html = open(path, encoding='utf-8').read()

        # Three repairs should all appear
        self.assertIn('Profit YoY', html)
        self.assertIn('Sales/P0', html)
        self.assertIn('Sales Story', html)
        # Severity badges
        self.assertIn('WARNING', html)
        self.assertIn('INFO', html)
        self.assertIn('ERROR', html)
        # Original / repaired columns
        self.assertIn('SUM([Region2])', html)
        self.assertIn('SUM([Region])', html)
        # Follow-up flagged
        self.assertIn('Review and rewire', html)
        # Per-category summary table
        self.assertIn('Repairs by Category', html)
        # Audit section
        self.assertIn('Per-Artifact Repair Audit', html)

    def test_save_html_returns_path(self):
        recovery = self._new('Some Report/With Slashes')
        with tempfile.TemporaryDirectory() as tmp:
            path = recovery.save_html(output_dir=tmp)
            # Path-traversal-safe naming
            self.assertNotIn('/With', os.path.basename(path))
            self.assertTrue(path.endswith('.html'))

    def test_save_html_creates_output_dir(self):
        recovery = self._new('mkdirs')
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, 'nested', 'deeper')
            path = recovery.save_html(output_dir=target)
            self.assertTrue(os.path.exists(path))

    def test_html_escapes_special_chars(self):
        recovery = self._new('xss')
        recovery.record(
            category='tmdl', repair_type='test',
            description='<script>alert(1)</script>',
            action='Replaced with safe&amp;',
            severity='warning',
            item_name='<img src=x>',
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = recovery.save_html(output_dir=tmp)
            html = open(path, encoding='utf-8').read()
        # Raw script tag must NOT appear
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertIn('&lt;script&gt;', html)


if __name__ == '__main__':
    unittest.main()
