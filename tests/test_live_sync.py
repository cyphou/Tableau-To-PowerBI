"""
Sprint 89 — Live Sync & Incremental Refresh Tests.

Validates source change detection, incremental diff generation,
sync deployment, and change notification.
"""

import json
import os
import shutil
import tempfile
import unittest

from powerbi_import.incremental import (
    DiffEntry,
    IncrementalMerger,
    SourceChangeDetector,
    IncrementalDiffGenerator,
)
from powerbi_import.telemetry import ChangeNotifier


# ═══════════════════════════════════════════════════════════════════
# 1. Source change detection (89.1)
# ═══════════════════════════════════════════════════════════════════

class TestSourceChangeDetection(unittest.TestCase):
    """89.1 — Detect changed workbooks via manifest comparison."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_manifest_all_new(self):
        infos = [
            {'name': 'WB1', 'updated_at': '2025-01-01T00:00:00Z'},
            {'name': 'WB2', 'updated_at': '2025-01-01T00:00:00Z'},
        ]
        changed = SourceChangeDetector.detect_changes(infos, {})
        self.assertEqual(sorted(changed), ['WB1', 'WB2'])

    def test_unchanged_workbook(self):
        manifest = {
            'WB1': {'updated_at': '2025-01-01T00:00:00Z', 'content_hash': 'abc'},
        }
        infos = [{'name': 'WB1', 'updated_at': '2025-01-01T00:00:00Z', 'content_hash': 'abc'}]
        changed = SourceChangeDetector.detect_changes(infos, manifest)
        self.assertEqual(changed, [])

    def test_timestamp_changed(self):
        manifest = {'WB1': {'updated_at': '2025-01-01T00:00:00Z'}}
        infos = [{'name': 'WB1', 'updated_at': '2025-02-01T00:00:00Z'}]
        changed = SourceChangeDetector.detect_changes(infos, manifest)
        self.assertEqual(changed, ['WB1'])

    def test_hash_changed(self):
        manifest = {'WB1': {'updated_at': '', 'content_hash': 'old'}}
        infos = [{'name': 'WB1', 'updated_at': '', 'content_hash': 'new'}]
        changed = SourceChangeDetector.detect_changes(infos, manifest)
        self.assertEqual(changed, ['WB1'])

    def test_save_and_load_manifest(self):
        path = os.path.join(self.tmp, 'manifest.json')
        manifest = {'WB1': {'updated_at': '2025-01-01', 'content_hash': 'x'}}
        SourceChangeDetector.save_manifest(path, manifest)
        loaded = SourceChangeDetector.load_manifest(path)
        self.assertEqual(loaded, manifest)

    def test_load_missing_manifest(self):
        path = os.path.join(self.tmp, 'nonexistent.json')
        self.assertEqual(SourceChangeDetector.load_manifest(path), {})

    def test_update_manifest(self):
        manifest = {}
        SourceChangeDetector.update_manifest(manifest, 'WB1', '2025-06-01', 'hash1')
        self.assertIn('WB1', manifest)
        self.assertEqual(manifest['WB1']['content_hash'], 'hash1')
        self.assertIn('last_migration_ts', manifest['WB1'])

    def test_mixed_new_and_unchanged(self):
        manifest = {'WB1': {'updated_at': '2025-01-01'}}
        infos = [
            {'name': 'WB1', 'updated_at': '2025-01-01'},
            {'name': 'WB2', 'updated_at': '2025-01-01'},
        ]
        changed = SourceChangeDetector.detect_changes(infos, manifest)
        self.assertEqual(changed, ['WB2'])


# ═══════════════════════════════════════════════════════════════════
# 2. Incremental diff generation (89.2)
# ═══════════════════════════════════════════════════════════════════

class TestIncrementalDiffGeneration(unittest.TestCase):
    """89.2 — Generate incremental diffs for changed artifacts."""

    def setUp(self):
        self.existing = tempfile.mkdtemp()
        self.incoming = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.existing, ignore_errors=True)
        shutil.rmtree(self.incoming, ignore_errors=True)

    def _write(self, base, rel_path, content):
        path = os.path.join(base, rel_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)

    def test_no_changes_detected(self):
        self._write(self.existing, 'file.json', '{"a": 1}')
        self._write(self.incoming, 'file.json', '{"a": 1}')
        result = IncrementalDiffGenerator.generate_incremental_update(
            self.existing, self.incoming)
        self.assertFalse(result['has_changes'])

    def test_added_file_detected(self):
        self._write(self.existing, 'file.json', '{"a": 1}')
        self._write(self.incoming, 'file.json', '{"a": 1}')
        self._write(self.incoming, 'new.json', '{"b": 2}')
        result = IncrementalDiffGenerator.generate_incremental_update(
            self.existing, self.incoming)
        self.assertTrue(result['has_changes'])
        self.assertIn('new.json', result['added'])

    def test_modified_file_detected(self):
        self._write(self.existing, 'file.json', '{"a": 1}')
        self._write(self.incoming, 'file.json', '{"a": 2}')
        result = IncrementalDiffGenerator.generate_incremental_update(
            self.existing, self.incoming)
        self.assertTrue(result['has_changes'])
        self.assertIn('file.json', result['modified'])

    def test_removed_file_detected(self):
        self._write(self.existing, 'old.json', '{"x": 1}')
        self._write(self.existing, 'keep.json', '{}')
        self._write(self.incoming, 'keep.json', '{}')
        result = IncrementalDiffGenerator.generate_incremental_update(
            self.existing, self.incoming)
        self.assertTrue(result['has_changes'])
        self.assertIn('old.json', result['removed'])

    def test_apply_incremental_update(self):
        self._write(self.existing, 'file.json', '{"a": 1}')
        self._write(self.incoming, 'file.json', '{"a": 2}')
        output = tempfile.mkdtemp()
        try:
            merge_result = IncrementalDiffGenerator.apply_incremental_update(
                self.existing, self.incoming, output)
            self.assertIn('merged', merge_result)
        finally:
            shutil.rmtree(output, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════
# 3. Sync deployment (89.3)
# ═══════════════════════════════════════════════════════════════════

class TestSyncDeployment(unittest.TestCase):
    """89.3 — deploy_sync detects changes before deploying."""

    def test_deploy_sync_signature(self):
        """PBIWorkspaceDeployer should have deploy_sync method."""
        import inspect
        from powerbi_import.deploy.pbi_deployer import PBIWorkspaceDeployer
        self.assertTrue(hasattr(PBIWorkspaceDeployer, 'deploy_sync'))
        sig = inspect.signature(PBIWorkspaceDeployer.deploy_sync)
        params = list(sig.parameters.keys())
        self.assertIn('project_dir', params)
        self.assertIn('previous_dir', params)
        self.assertIn('refresh', params)


# ═══════════════════════════════════════════════════════════════════
# 4. Change notification (89.4)
# ═══════════════════════════════════════════════════════════════════

class TestChangeNotification(unittest.TestCase):
    """89.4 — Structured events for detected changes."""

    def test_notify_returns_payload(self):
        notifier = ChangeNotifier()
        payload = notifier.notify('WB1', 'modified', ['measure.tmdl', 'page1.json'])
        self.assertEqual(payload['workbook'], 'WB1')
        self.assertEqual(payload['change_type'], 'modified')
        self.assertEqual(len(payload['affected_artifacts']), 2)
        self.assertIn('timestamp', payload)

    def test_notify_new_workbook(self):
        notifier = ChangeNotifier()
        payload = notifier.notify('NewWB', 'new')
        self.assertEqual(payload['change_type'], 'new')
        self.assertEqual(payload['affected_artifacts'], [])

    def test_notify_with_telemetry(self):
        events = []

        class MockTelemetry:
            def record_event(self, event_type, **data):
                events.append({'type': event_type, **data})

        notifier = ChangeNotifier(telemetry_collector=MockTelemetry())
        notifier.notify('WB1', 'modified', ['file1'])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['type'], 'source_change_detected')
        self.assertEqual(events[0]['workbook'], 'WB1')

    def test_no_webhook_no_error(self):
        """Notify without webhook should not raise."""
        notifier = ChangeNotifier(webhook_url=None)
        payload = notifier.notify('WB1', 'deleted')
        self.assertIsNotNone(payload)

    def test_bad_webhook_no_error(self):
        """Bad webhook URL should not raise (best-effort)."""
        notifier = ChangeNotifier(webhook_url='http://localhost:1/invalid')
        # Should not raise
        payload = notifier.notify('WB1', 'modified')
        self.assertIsNotNone(payload)


if __name__ == '__main__':
    unittest.main()
