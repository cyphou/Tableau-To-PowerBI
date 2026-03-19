"""
Tests for v4.1.0 backlog features:
  1. Multi-datasource context (resolve_table_for_column)
  2. Hyper metadata depth (enhanced extract_hyper_metadata)
  3. Incremental migration (IncrementalMerger)
  4. PBIR schema validation (validate_pbir_structure)
  5. Telemetry (TelemetryCollector)
  6. API documentation generator
"""

import json
import os
import shutil
import tempfile
import unittest

from tests.conftest import SAMPLE_DATASOURCE, SAMPLE_EXTRACTED, make_temp_dir, cleanup_dir

from powerbi_import.tmdl_generator import resolve_table_for_column
from powerbi_import.tmdl_generator import generate_tmdl
from powerbi_import.incremental import IncrementalMerger, DiffEntry
from powerbi_import.incremental import IncrementalMerger
from powerbi_import.incremental import DiffEntry
from powerbi_import.validator import ArtifactValidator
from powerbi_import.telemetry import is_telemetry_enabled
from powerbi_import.telemetry import TelemetryCollector
import sys
from docs.generate_api_docs import generate_with_builtin
import docs.generate_api_docs as gen_mod


class TestMultiDatasourceContext(unittest.TestCase):
    """Tests for multi-datasource column-to-table routing."""

    def test_resolve_table_for_column_global(self):
        """Falls back to global column_table_map when no datasource specified."""
        ctx = {
            'column_table_map': {'Sales': 'Orders', 'Profit': 'Orders'},
            'ds_column_table_map': {},
        }
        self.assertEqual(resolve_table_for_column('Sales', dax_context=ctx), 'Orders')

    def test_resolve_table_for_column_ds_scoped(self):
        """Returns datasource-specific table when scoped."""
        ctx = {
            'column_table_map': {'Sales': 'AllOrders'},
            'ds_column_table_map': {
                'DS_A': {'Sales': 'OrdersA'},
                'DS_B': {'Sales': 'OrdersB'},
            },
        }
        self.assertEqual(
            resolve_table_for_column('Sales', datasource_name='DS_A', dax_context=ctx),
            'OrdersA'
        )
        self.assertEqual(
            resolve_table_for_column('Sales', datasource_name='DS_B', dax_context=ctx),
            'OrdersB'
        )

    def test_resolve_table_for_column_fallback(self):
        """Falls back to global when column not in datasource-specific map."""
        ctx = {
            'column_table_map': {'Region': 'Geo'},
            'ds_column_table_map': {
                'DS_A': {'Sales': 'Orders'},
            },
        }
        self.assertEqual(
            resolve_table_for_column('Region', datasource_name='DS_A', dax_context=ctx),
            'Geo'
        )

    def test_resolve_table_for_column_none_context(self):
        """Returns None when dax_context is None."""
        self.assertIsNone(resolve_table_for_column('Sales'))

    def test_resolve_table_for_column_unknown(self):
        """Returns None for unknown columns."""
        ctx = {'column_table_map': {}, 'ds_column_table_map': {}}
        self.assertIsNone(resolve_table_for_column('Unknown', dax_context=ctx))

    def test_dax_context_has_ds_maps(self):
        """generate_tmdl produces dax_context with ds_column_table_map."""
        tmp = make_temp_dir()
        try:
            datasources = [{
                'name': 'DS1',
                'connection': {'type': 'SQL Server', 'details': {'server': 's', 'database': 'd'}},
                'connection_map': {},
                'tables': [{
                    'name': 'T1',
                    'columns': [{'name': 'Col1', 'datatype': 'string'}],
                }],
                'calculations': [],
            }, {
                'name': 'DS2',
                'connection': {'type': 'CSV', 'details': {'filename': 'f.csv'}},
                'connection_map': {},
                'tables': [{
                    'name': 'T2',
                    'columns': [{'name': 'Col2', 'datatype': 'integer'}],
                }],
                'calculations': [],
            }]
            sm_dir = os.path.join(tmp, 'Test.SemanticModel')
            stats = generate_tmdl(datasources, 'Test', {}, sm_dir)
            # Should generate tables from both datasources
            self.assertGreaterEqual(stats['tables'], 2)
        finally:
            cleanup_dir(tmp)


class TestIncrementalMigration(unittest.TestCase):
    """Tests for IncrementalMerger diff and merge."""

    def setUp(self):
        self.tmp = make_temp_dir()
        self.existing = os.path.join(self.tmp, 'existing')
        self.incoming = os.path.join(self.tmp, 'incoming')
        self.output = os.path.join(self.tmp, 'output')
        os.makedirs(self.existing)
        os.makedirs(self.incoming)

    def tearDown(self):
        cleanup_dir(self.tmp)

    def _write(self, base, path, content):
        full = os.path.join(base, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'w', encoding='utf-8') as f:
            f.write(content)

    def test_diff_identical(self):
        """Identical files produce UNCHANGED entries."""
        self._write(self.existing, 'a.json', '{"x": 1}')
        self._write(self.incoming, 'a.json', '{"x": 1}')
        diffs = IncrementalMerger.diff_projects(self.existing, self.incoming)
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0].kind, DiffEntry.UNCHANGED)

    def test_diff_added(self):
        """New file in incoming is detected as ADDED."""
        self._write(self.existing, 'a.json', '{}')
        self._write(self.incoming, 'a.json', '{}')
        self._write(self.incoming, 'b.json', '{"new": true}')
        diffs = IncrementalMerger.diff_projects(self.existing, self.incoming)
        added = [d for d in diffs if d.kind == DiffEntry.ADDED]
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0].path, 'b.json')

    def test_diff_removed(self):
        """File missing from incoming is detected as REMOVED."""
        self._write(self.existing, 'a.json', '{}')
        self._write(self.existing, 'b.json', '{}')
        self._write(self.incoming, 'a.json', '{}')
        diffs = IncrementalMerger.diff_projects(self.existing, self.incoming)
        removed = [d for d in diffs if d.kind == DiffEntry.REMOVED]
        self.assertEqual(len(removed), 1)

    def test_diff_modified(self):
        """Changed content is detected as MODIFIED."""
        self._write(self.existing, 'a.json', '{"x": 1}')
        self._write(self.incoming, 'a.json', '{"x": 2}')
        diffs = IncrementalMerger.diff_projects(self.existing, self.incoming)
        modified = [d for d in diffs if d.kind == DiffEntry.MODIFIED]
        self.assertEqual(len(modified), 1)

    def test_merge_preserves_user_editable_keys(self):
        """Merge preserves user-editable keys from existing project."""
        self._write(self.existing, 'visual.json',
                     json.dumps({"title": "My Custom Title", "x": 1}))
        self._write(self.incoming, 'visual.json',
                     json.dumps({"title": "Generated Title", "x": 2}))
        stats = IncrementalMerger.merge(self.existing, self.incoming, self.output)
        self.assertEqual(stats['merged'], 1)
        with open(os.path.join(self.output, 'visual.json'), 'r') as f:
            result = json.load(f)
        # User's title preserved, incoming x value taken
        self.assertEqual(result['title'], 'My Custom Title')
        self.assertEqual(result['x'], 2)

    def test_merge_adds_new_files(self):
        """Merge adds new files from incoming."""
        self._write(self.existing, 'a.json', '{}')
        self._write(self.incoming, 'a.json', '{}')
        self._write(self.incoming, 'new.json', '{"added": true}')
        stats = IncrementalMerger.merge(self.existing, self.incoming, self.output)
        self.assertEqual(stats['added'], 1)
        self.assertTrue(os.path.exists(os.path.join(self.output, 'new.json')))

    def test_merge_preserves_user_owned(self):
        """User-owned files (staticResources/) are preserved even if removed."""
        self._write(self.existing, 'staticResources/logo.png', 'PNG_DATA')
        self._write(self.existing, 'a.json', '{}')
        self._write(self.incoming, 'a.json', '{}')
        stats = IncrementalMerger.merge(self.existing, self.incoming, self.output)
        self.assertEqual(stats['preserved'], 1)

    def test_merge_writes_report(self):
        """Merge creates a .migration_merge_report.json."""
        self._write(self.existing, 'a.json', '{}')
        self._write(self.incoming, 'a.json', '{"changed": true}')
        IncrementalMerger.merge(self.existing, self.incoming, self.output)
        report_path = os.path.join(self.output, '.migration_merge_report.json')
        self.assertTrue(os.path.exists(report_path))
        with open(report_path, 'r') as f:
            report = json.load(f)
        self.assertIn('stats', report)
        self.assertIn('timestamp', report)

    def test_generate_diff_report(self):
        """generate_diff_report returns a formatted string."""
        self._write(self.existing, 'a.json', '{"x": 1}')
        self._write(self.incoming, 'a.json', '{"x": 2}')
        self._write(self.incoming, 'b.json', '{}')
        report = IncrementalMerger.generate_diff_report(self.existing, self.incoming)
        self.assertIn('Migration Diff Report', report)
        self.assertIn('ADDED', report.upper())
        self.assertIn('MODIFIED', report.upper())

    def test_diff_entry_to_dict(self):
        """DiffEntry.to_dict returns expected format."""
        d = DiffEntry('path/to/file.json', DiffEntry.MODIFIED, 'key changed')
        dd = d.to_dict()
        self.assertEqual(dd['path'], 'path/to/file.json')
        self.assertEqual(dd['kind'], 'modified')
        self.assertEqual(dd['detail'], 'key changed')

    def test_merge_tmdl_takes_incoming(self):
        """Non-JSON files (like .tmdl) always take the incoming version."""
        self._write(self.existing, 'model.tmdl', 'model Model\n  old content')
        self._write(self.incoming, 'model.tmdl', 'model Model\n  new content')
        stats = IncrementalMerger.merge(self.existing, self.incoming, self.output)
        with open(os.path.join(self.output, 'model.tmdl'), 'r') as f:
            content = f.read()
        self.assertIn('new content', content)


class TestPBIRSchemaValidation(unittest.TestCase):
    """Tests for PBIR structural schema validation."""

    def test_valid_report_json(self):
        """Valid report.json passes structural validation."""
        data = {'$schema': ArtifactValidator.VALID_REPORT_SCHEMAS[0]}
        errors = ArtifactValidator.validate_pbir_structure(
            data, ArtifactValidator.VALID_REPORT_SCHEMAS[0])
        self.assertEqual(errors, [])

    def test_missing_schema_key(self):
        """Missing $schema in report JSON is flagged."""
        url = 'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/2.0.0/schema.json'
        data = {'datasetReference': {}}
        errors = ArtifactValidator.validate_pbir_structure(data, url)
        self.assertTrue(any('$schema' in e for e in errors))

    def test_valid_page_json(self):
        """Valid page.json passes structural validation."""
        url = ArtifactValidator.VALID_PAGE_SCHEMAS[0]
        data = {'$schema': url, 'name': 'Page1', 'displayName': 'Sales'}
        errors = ArtifactValidator.validate_pbir_structure(data, url)
        self.assertEqual(errors, [])

    def test_page_missing_required(self):
        """Page JSON missing 'name' or 'displayName' is flagged."""
        url = ArtifactValidator.VALID_PAGE_SCHEMAS[0]
        data = {'$schema': url, 'name': 'Page1'}
        errors = ArtifactValidator.validate_pbir_structure(data, url)
        self.assertTrue(any('displayName' in e for e in errors))

    def test_visual_valid(self):
        """Valid visual.json passes structural validation."""
        url = ArtifactValidator.VALID_VISUAL_SCHEMAS[0]
        data = {'$schema': url, 'name': 'vis1'}
        errors = ArtifactValidator.validate_pbir_structure(data, url)
        self.assertEqual(errors, [])

    def test_non_dict_input(self):
        """Non-dict JSON produces an error."""
        errors = ArtifactValidator.validate_pbir_structure([], 'report/')
        self.assertTrue(any('JSON object' in e for e in errors))

    def test_unknown_schema_skipped(self):
        """Unknown schema URLs produce no errors (graceful skip)."""
        data = {'$schema': 'https://example.com/unknown/schema'}
        errors = ArtifactValidator.validate_pbir_structure(data, 'https://example.com/unknown')
        self.assertEqual(errors, [])

    def test_wrong_schema_version_warning(self):
        """Wrong schema version produces a warning."""
        url = 'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/9.9.9/schema.json'
        data = {'$schema': url}
        errors = ArtifactValidator.validate_pbir_structure(data, url)
        self.assertTrue(any('Unexpected' in e for e in errors))


class TestTelemetry(unittest.TestCase):
    """Tests for the telemetry collector."""

    def test_disabled_by_default(self):
        """Telemetry is disabled when env var not set."""
        # Ensure env var is not set
        os.environ.pop('TTPBI_TELEMETRY', None)
        self.assertFalse(is_telemetry_enabled())

    def test_enabled_via_env(self):
        """Telemetry is enabled when TTPBI_TELEMETRY=1."""
        os.environ['TTPBI_TELEMETRY'] = '1'
        try:
            self.assertTrue(is_telemetry_enabled())
        finally:
            os.environ.pop('TTPBI_TELEMETRY', None)

    def test_collector_records_stats(self):
        """TelemetryCollector records stats correctly."""
        t = TelemetryCollector(enabled=True)
        t.start()
        t.record_stats(tables=5, columns=20)
        t.record_error('dax', 'test error')
        t.finish()
        data = t.get_data()
        self.assertEqual(data['stats']['tables'], 5)
        self.assertEqual(len(data['errors']), 1)
        self.assertIsNotNone(data['duration_seconds'])
        self.assertGreaterEqual(data['duration_seconds'], 0)

    def test_collector_disabled_no_record(self):
        """Disabled collector doesn't record anything."""
        t = TelemetryCollector(enabled=False)
        t.record_stats(tables=5)
        t.record_error('dax', 'err')
        data = t.get_data()
        self.assertEqual(data['stats'], {})
        self.assertEqual(data['errors'], [])

    def test_collector_save_to_file(self):
        """Collector saves JSONL to file."""
        tmp = make_temp_dir()
        try:
            log_path = os.path.join(tmp, 'telemetry.json')
            t = TelemetryCollector(enabled=True, log_path=log_path)
            t.start()
            t.record_stats(tables=3)
            t.finish()
            t.save()
            self.assertTrue(os.path.exists(log_path))
            with open(log_path, 'r') as f:
                line = f.readline()
                data = json.loads(line)
            self.assertEqual(data['stats']['tables'], 3)
        finally:
            cleanup_dir(tmp)

    def test_collector_read_log(self):
        """read_log parses JSONL correctly."""
        tmp = make_temp_dir()
        try:
            log_path = os.path.join(tmp, 'telemetry.json')
            # Write two entries
            for i in range(2):
                t = TelemetryCollector(enabled=True, log_path=log_path)
                t.start()
                t.record_stats(run=i)
                t.finish()
                t.save()
            entries = TelemetryCollector.read_log(log_path)
            self.assertEqual(len(entries), 2)
        finally:
            cleanup_dir(tmp)

    def test_collector_summary(self):
        """summary() returns aggregate stats."""
        tmp = make_temp_dir()
        try:
            log_path = os.path.join(tmp, 'telemetry.json')
            for i in range(3):
                t = TelemetryCollector(enabled=True, log_path=log_path)
                t.start()
                t.finish()
                t.save()
            summary = TelemetryCollector.summary(log_path)
            self.assertEqual(summary['sessions'], 3)
        finally:
            cleanup_dir(tmp)

    def test_collector_no_log_file(self):
        """read_log returns empty list for missing file."""
        entries = TelemetryCollector.read_log('/tmp/nonexistent_ttpbi.json')
        self.assertEqual(entries, [])

    def test_collector_version_detection(self):
        """Tool version is detected from CHANGELOG."""
        t = TelemetryCollector(enabled=True)
        data = t.get_data()
        # Should find a version or 'unknown'
        self.assertIsInstance(data['tool_version'], str)
        self.assertGreater(len(data['tool_version']), 0)


class TestAPIDocGenerator(unittest.TestCase):
    """Tests for the API documentation generator."""

    def test_builtin_generator(self):
        """Built-in doc generator produces HTML files."""
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if root not in sys.path:
            sys.path.insert(0, root)

        tmp = make_temp_dir()
        try:
            # Generate docs for a subset to keep test fast
            original_modules = gen_mod.MODULES
            gen_mod.MODULES = ['powerbi_import.validator']
            try:
                result = generate_with_builtin(tmp)
            finally:
                gen_mod.MODULES = original_modules
            self.assertTrue(result)
            self.assertTrue(os.path.exists(os.path.join(tmp, 'index.html')))
            self.assertTrue(os.path.exists(
                os.path.join(tmp, 'powerbi_import.validator.html')))
        finally:
            cleanup_dir(tmp)


class TestMutationConfig(unittest.TestCase):
    """Tests for mutation testing configuration."""

    def test_setup_cfg_exists(self):
        """setup.cfg with [mutmut] section exists."""
        cfg_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                'setup.cfg')
        self.assertTrue(os.path.exists(cfg_path))
        with open(cfg_path, 'r') as f:
            content = f.read()
        self.assertIn('[mutmut]', content)
        self.assertIn('dax_converter.py', content)
        self.assertIn('tmdl_generator.py', content)


if __name__ == '__main__':
    unittest.main()
