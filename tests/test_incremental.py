"""
Tests for incremental migration module — Sprint 56.

Covers:
  - DiffEntry creation and to_dict
  - diff_projects (added, removed, modified, unchanged)
  - merge (in-place and separate output)
  - JSON merge with user-editable key preservation
  - User-owned file detection
  - generate_diff_report
  - Edge cases: empty dirs, non-JSON files, corrupt JSON
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from powerbi_import.incremental import DiffEntry, IncrementalMerger


def _create_file(directory, rel_path, content):
    """Helper to create a file with content."""
    full = os.path.join(directory, rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w', encoding='utf-8') as f:
        f.write(content)


def _create_json(directory, rel_path, data):
    """Helper to create a JSON file."""
    full = os.path.join(directory, rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w', encoding='utf-8') as f:
        json.dump(data, f)


class TestDiffEntry(unittest.TestCase):
    def test_creation(self):
        entry = DiffEntry('file.json', DiffEntry.ADDED, 'new file')
        self.assertEqual(entry.path, 'file.json')
        self.assertEqual(entry.kind, 'added')
        self.assertEqual(entry.detail, 'new file')

    def test_to_dict(self):
        entry = DiffEntry('a.json', DiffEntry.MODIFIED, 'changed')
        d = entry.to_dict()
        self.assertEqual(d['path'], 'a.json')
        self.assertEqual(d['kind'], 'modified')
        self.assertEqual(d['detail'], 'changed')

    def test_repr(self):
        entry = DiffEntry('test.txt', DiffEntry.REMOVED)
        self.assertIn('test.txt', repr(entry))
        self.assertIn('removed', repr(entry))

    def test_constants(self):
        self.assertEqual(DiffEntry.ADDED, 'added')
        self.assertEqual(DiffEntry.REMOVED, 'removed')
        self.assertEqual(DiffEntry.MODIFIED, 'modified')
        self.assertEqual(DiffEntry.UNCHANGED, 'unchanged')


class TestDiffProjects(unittest.TestCase):
    def test_identical_projects(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            _create_file(d1, 'report.json', '{"a": 1}')
            _create_file(d2, 'report.json', '{"a": 1}')
            diffs = IncrementalMerger.diff_projects(d1, d2)
            self.assertEqual(len(diffs), 1)
            self.assertEqual(diffs[0].kind, DiffEntry.UNCHANGED)

    def test_added_file(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            _create_file(d1, 'existing.json', '{}')
            _create_file(d2, 'existing.json', '{}')
            _create_file(d2, 'new_file.json', '{"new": true}')
            diffs = IncrementalMerger.diff_projects(d1, d2)
            added = [d for d in diffs if d.kind == DiffEntry.ADDED]
            self.assertEqual(len(added), 1)
            self.assertIn('new_file', added[0].path)

    def test_removed_file(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            _create_file(d1, 'old.json', '{}')
            _create_file(d1, 'keep.json', '{}')
            _create_file(d2, 'keep.json', '{}')
            diffs = IncrementalMerger.diff_projects(d1, d2)
            removed = [d for d in diffs if d.kind == DiffEntry.REMOVED]
            self.assertEqual(len(removed), 1)

    def test_modified_file(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            _create_json(d1, 'report.json', {'a': 1})
            _create_json(d2, 'report.json', {'a': 2})
            diffs = IncrementalMerger.diff_projects(d1, d2)
            modified = [d for d in diffs if d.kind == DiffEntry.MODIFIED]
            self.assertEqual(len(modified), 1)

    def test_empty_dirs(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            diffs = IncrementalMerger.diff_projects(d1, d2)
            self.assertEqual(len(diffs), 0)

    def test_modified_json_detail(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            _create_json(d1, 'r.json', {'a': 1, 'b': 2})
            _create_json(d2, 'r.json', {'a': 1, 'b': 3, 'c': 4})
            diffs = IncrementalMerger.diff_projects(d1, d2)
            modified = [d for d in diffs if d.kind == DiffEntry.MODIFIED]
            self.assertEqual(len(modified), 1)
            self.assertIn('+1 keys', modified[0].detail)

    def test_nested_files(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            _create_file(d1, 'pages/page1/visual.json', '{"v": 1}')
            _create_file(d2, 'pages/page1/visual.json', '{"v": 1}')
            _create_file(d2, 'pages/page2/visual.json', '{"v": 2}')
            diffs = IncrementalMerger.diff_projects(d1, d2)
            added = [d for d in diffs if d.kind == DiffEntry.ADDED]
            self.assertEqual(len(added), 1)


class TestMerge(unittest.TestCase):
    def test_merge_adds_new_file(self):
        with tempfile.TemporaryDirectory() as d1, \
             tempfile.TemporaryDirectory() as d2, \
             tempfile.TemporaryDirectory() as out:
            _create_file(d1, 'existing.txt', 'hello')
            _create_file(d2, 'existing.txt', 'hello')
            _create_file(d2, 'new.txt', 'world')
            stats = IncrementalMerger.merge(d1, d2, out)
            self.assertEqual(stats['added'], 1)
            self.assertTrue(os.path.exists(os.path.join(out, 'new.txt')))

    def test_merge_removes_non_user_file(self):
        with tempfile.TemporaryDirectory() as d1, \
             tempfile.TemporaryDirectory() as d2, \
             tempfile.TemporaryDirectory() as out:
            _create_file(d1, 'old.txt', 'content')
            _create_file(d1, 'keep.txt', 'keep')
            _create_file(d2, 'keep.txt', 'keep')
            stats = IncrementalMerger.merge(d1, d2, out)
            self.assertEqual(stats['removed'], 1)

    def test_merge_preserves_user_owned(self):
        with tempfile.TemporaryDirectory() as d1, \
             tempfile.TemporaryDirectory() as d2, \
             tempfile.TemporaryDirectory() as out:
            _create_file(d1, 'staticResources/image.png', 'data')
            _create_file(d1, 'keep.txt', 'keep')
            _create_file(d2, 'keep.txt', 'keep')
            stats = IncrementalMerger.merge(d1, d2, out)
            self.assertEqual(stats['preserved'], 1)
            self.assertTrue(os.path.exists(
                os.path.join(out, 'staticResources', 'image.png')))

    def test_merge_json_preserves_user_editable(self):
        with tempfile.TemporaryDirectory() as d1, \
             tempfile.TemporaryDirectory() as d2, \
             tempfile.TemporaryDirectory() as out:
            _create_json(d1, 'visual.json', {
                'title': 'My Custom Title',
                'visualType': 'barChart',
                'data': 'old',
            })
            _create_json(d2, 'visual.json', {
                'title': 'Generated Title',
                'visualType': 'lineChart',
                'data': 'new',
            })
            stats = IncrementalMerger.merge(d1, d2, out)
            with open(os.path.join(out, 'visual.json'), 'r') as f:
                result = json.load(f)
            self.assertEqual(result['title'], 'My Custom Title')
            self.assertEqual(result['data'], 'new')

    def test_merge_writes_report(self):
        with tempfile.TemporaryDirectory() as d1, \
             tempfile.TemporaryDirectory() as d2, \
             tempfile.TemporaryDirectory() as out:
            _create_file(d1, 'a.txt', 'x')
            _create_file(d2, 'a.txt', 'x')
            IncrementalMerger.merge(d1, d2, out)
            report_path = os.path.join(out, '.migration_merge_report.json')
            self.assertTrue(os.path.exists(report_path))
            with open(report_path, 'r') as f:
                report = json.load(f)
            self.assertIn('stats', report)
            self.assertIn('timestamp', report)

    def test_merge_non_json_modified_takes_incoming(self):
        with tempfile.TemporaryDirectory() as d1, \
             tempfile.TemporaryDirectory() as d2, \
             tempfile.TemporaryDirectory() as out:
            _create_file(d1, 'model.tmdl', 'old content')
            _create_file(d2, 'model.tmdl', 'new content')
            stats = IncrementalMerger.merge(d1, d2, out)
            self.assertEqual(stats['merged'], 1)
            with open(os.path.join(out, 'model.tmdl'), 'r') as f:
                self.assertEqual(f.read(), 'new content')

    def test_merge_stats_structure(self):
        with tempfile.TemporaryDirectory() as d1, \
             tempfile.TemporaryDirectory() as d2, \
             tempfile.TemporaryDirectory() as out:
            _create_file(d1, 'a.txt', 'x')
            _create_file(d2, 'a.txt', 'x')
            stats = IncrementalMerger.merge(d1, d2, out)
            for key in ('merged', 'added', 'removed', 'preserved', 'conflicts'):
                self.assertIn(key, stats)


class TestIsUserOwned(unittest.TestCase):
    def test_static_resources(self):
        self.assertTrue(IncrementalMerger._is_user_owned('staticResources/img.png'))

    def test_regular_file(self):
        self.assertFalse(IncrementalMerger._is_user_owned('pages/page1/visual.json'))


class TestGenerateDiffReport(unittest.TestCase):
    def test_report_format(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            _create_file(d1, 'a.json', '{}')
            _create_file(d2, 'a.json', '{"x": 1}')
            _create_file(d2, 'b.json', '{}')
            report = IncrementalMerger.generate_diff_report(d1, d2)
            self.assertIn('Migration Diff Report', report)
            self.assertIn('ADDED', report)
            self.assertIn('MODIFIED', report)

    def test_empty_report(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            report = IncrementalMerger.generate_diff_report(d1, d2)
            self.assertIn('0 files compared', report)


class TestMergeJson(unittest.TestCase):
    def test_corrupt_json_takes_incoming(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            existing = os.path.join(tmpdir, 'existing.json')
            incoming = os.path.join(tmpdir, 'incoming.json')
            target = os.path.join(tmpdir, 'target.json')
            with open(existing, 'w') as f:
                f.write('not json')
            _create_json(tmpdir, 'incoming.json', {'a': 1})
            success, conflict = IncrementalMerger._merge_json(
                existing, incoming, target)
            self.assertTrue(success)
            self.assertFalse(conflict)

    def test_non_dict_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            existing = os.path.join(tmpdir, 'existing.json')
            incoming = os.path.join(tmpdir, 'incoming.json')
            target = os.path.join(tmpdir, 'target.json')
            with open(existing, 'w') as f:
                json.dump([1, 2], f)
            with open(incoming, 'w') as f:
                json.dump([3, 4], f)
            IncrementalMerger._merge_json(existing, incoming, target)
            with open(target, 'r') as f:
                result = json.load(f)
            self.assertEqual(result, [3, 4])


class TestCollectFiles(unittest.TestCase):
    def test_non_existent_dir(self):
        result = IncrementalMerger._collect_files('/nonexistent/path/xyz')
        self.assertEqual(result, set())

    def test_collect_nested(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_file(tmpdir, 'a.txt', 'x')
            _create_file(tmpdir, 'sub/b.txt', 'y')
            result = IncrementalMerger._collect_files(tmpdir)
            self.assertIn('a.txt', result)
            self.assertIn('sub/b.txt', result)


if __name__ == '__main__':
    unittest.main()
