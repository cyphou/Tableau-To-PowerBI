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


class TestValidateDaxFormulaLineComments(unittest.TestCase):
    """Tests for validate_dax_formula // line-comment detection."""

    def test_comment_at_start(self):
        """DAX with // comment at the start is detected."""
        issues = ArtifactValidator.validate_dax_formula('// this is a comment')
        self.assertTrue(any('line comment' in i for i in issues))

    def test_comment_after_expression(self):
        """DAX with // comment after an expression is detected."""
        issues = ArtifactValidator.validate_dax_formula('SUM(Sales) // total')
        self.assertTrue(any('line comment' in i for i in issues))

    def test_url_protocol_not_flagged(self):
        """URL with :// should NOT be flagged as a comment."""
        issues = ArtifactValidator.validate_dax_formula(
            'IF(1, "https://example.com", 0)')
        comment_issues = [i for i in issues if 'line comment' in i]
        self.assertEqual(comment_issues, [])

    def test_double_slash_inside_string_literal(self):
        """// inside a string literal should NOT be flagged."""
        issues = ArtifactValidator.validate_dax_formula(
            '"http://example.com" & [Col]')
        comment_issues = [i for i in issues if 'line comment' in i]
        self.assertEqual(comment_issues, [])

    def test_clean_dax_no_issues(self):
        """Clean DAX without comments produces no line-comment issues."""
        issues = ArtifactValidator.validate_dax_formula(
            'CALCULATE(SUM(Sales[Amount]), ALL(Sales))')
        comment_issues = [i for i in issues if 'line comment' in i]
        self.assertEqual(comment_issues, [])

    def test_context_label_in_message(self):
        """Context label appears in the issue message."""
        issues = ArtifactValidator.validate_dax_formula(
            '1 + 2 // bad', context='MyMeasure')
        self.assertTrue(any('MyMeasure' in i for i in issues))


class TestValidateRelationshipColumns(unittest.TestCase):
    """Tests for validate_relationship_columns classmethod."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _create_sm(self, relationships_content, tables, model_refs=None):
        """Helper to build a minimal SemanticModel directory.

        Args:
            relationships_content: text for relationships.tmdl
            tables: dict table_name -> list of (col_name, data_type)
            model_refs: optional text for model.tmdl (auto-generated if None)
        """
        sm_dir = os.path.join(self.tmpdir, 'Test.SemanticModel')
        def_dir = os.path.join(sm_dir, 'definition')
        tables_dir = os.path.join(def_dir, 'tables')
        os.makedirs(tables_dir, exist_ok=True)

        # relationships.tmdl
        with open(os.path.join(def_dir, 'relationships.tmdl'), 'w',
                  encoding='utf-8') as f:
            f.write(relationships_content)

        # table TMDL files
        for tname, cols in tables.items():
            lines = [f'table {tname}']
            for cname, dtype in cols:
                lines.append(f'\tcolumn {cname}')
                lines.append(f'\t\tdataType: {dtype}')
            with open(os.path.join(tables_dir, f'{tname}.tmdl'), 'w',
                      encoding='utf-8') as f:
                f.write('\n'.join(lines) + '\n')

        # model.tmdl
        if model_refs is None:
            model_refs = 'model Model\n'
        with open(os.path.join(def_dir, 'model.tmdl'), 'w',
                  encoding='utf-8') as f:
            f.write(model_refs)

        return sm_dir

    def test_valid_relationship_no_issues(self):
        """Valid relationships with existing columns produce no issues."""
        rel = (
            'relationship abc-123\n'
            '\tfromColumn: Orders.ProductID\n'
            '\ttoColumn: Products.ProductID\n'
            '\tfromCardinality: many\n'
            '\ttoCardinality: one\n'
        )
        tables = {
            'Orders': [('ProductID', 'string'), ('Amount', 'double')],
            'Products': [('ProductID', 'string'), ('Name', 'string')],
        }
        sm_dir = self._create_sm(rel, tables)
        issues = ArtifactValidator.validate_relationship_columns(sm_dir)
        self.assertEqual(issues, [])

    def test_missing_column_detected(self):
        """Relationship referencing a non-existent column is flagged."""
        rel = (
            'relationship rel-001\n'
            '\tfromColumn: Orders.MissingCol\n'
            '\ttoColumn: Products.ProductID\n'
            '\tfromCardinality: many\n'
            '\ttoCardinality: one\n'
        )
        tables = {
            'Orders': [('ProductID', 'string'), ('Amount', 'double')],
            'Products': [('ProductID', 'string'), ('Name', 'string')],
        }
        sm_dir = self._create_sm(rel, tables)
        issues = ArtifactValidator.validate_relationship_columns(sm_dir)
        self.assertTrue(len(issues) > 0)
        self.assertTrue(any('MissingCol' in i for i in issues))

    def test_related_on_many_to_many_detected(self):
        """RELATED() referencing a manyToMany table is warned about."""
        rel = (
            'relationship rel-m2m\n'
            '\tfromColumn: Orders.ProductID\n'
            '\ttoColumn: Products.ProductID\n'
            '\tfromCardinality: many\n'
            '\ttoCardinality: many\n'
        )
        tables = {
            'Orders': [('ProductID', 'string'), ('Amount', 'double')],
            'Products': [('ProductID', 'string'), ('Name', 'string')],
        }
        sm_dir = self._create_sm(rel, tables)

        # Inject a RELATED() call referencing the manyToMany table
        orders_tmdl = os.path.join(
            sm_dir, 'definition', 'tables', 'Orders.tmdl')
        with open(orders_tmdl, 'a', encoding='utf-8') as f:
            f.write("\tmeasure TotalName = RELATED('Products'[Name])\n")

        issues = ArtifactValidator.validate_relationship_columns(sm_dir)
        self.assertTrue(any('RELATED' in i and 'Products' in i for i in issues))
        self.assertTrue(any('LOOKUPVALUE' in i for i in issues))

    def test_no_relationships_file_returns_empty(self):
        """Missing relationships.tmdl returns no issues (graceful)."""
        sm_dir = os.path.join(self.tmpdir, 'Empty.SemanticModel')
        def_dir = os.path.join(sm_dir, 'definition')
        os.makedirs(def_dir, exist_ok=True)
        with open(os.path.join(def_dir, 'model.tmdl'), 'w',
                  encoding='utf-8') as f:
            f.write('model Model\n')
        issues = ArtifactValidator.validate_relationship_columns(sm_dir)
        self.assertEqual(issues, [])


class TestValidateProjectRelationshipWarnings(unittest.TestCase):
    """Tests that validate_project surfaces relationship column warnings."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_validate_project_missing_rel_column_warning(self):
        """validate_project includes relationship column warnings."""
        proj_dir = os.path.join(self.tmpdir, 'MyReport')
        sm_dir = os.path.join(proj_dir, 'MyReport.SemanticModel')
        def_dir = os.path.join(sm_dir, 'definition')
        tables_dir = os.path.join(def_dir, 'tables')
        report_dir = os.path.join(proj_dir, 'MyReport.Report', 'definition')
        os.makedirs(tables_dir, exist_ok=True)
        os.makedirs(report_dir, exist_ok=True)

        # .pbip file
        with open(os.path.join(proj_dir, 'MyReport.pbip'), 'w',
                  encoding='utf-8') as f:
            json.dump({'version': '1.0'}, f)

        # report.json
        with open(os.path.join(report_dir, 'report.json'), 'w',
                  encoding='utf-8') as f:
            json.dump({'$schema': ArtifactValidator.VALID_REPORT_SCHEMAS[0]}, f)

        # definition.pbir
        with open(os.path.join(
                proj_dir, 'MyReport.Report', 'definition.pbir'), 'w',
                encoding='utf-8') as f:
            json.dump({'version': '2.0'}, f)

        # model.tmdl
        with open(os.path.join(def_dir, 'model.tmdl'), 'w',
                  encoding='utf-8') as f:
            f.write('model Model\n\tref relationship rel-bad\n')

        # relationships.tmdl with a bad column reference
        with open(os.path.join(def_dir, 'relationships.tmdl'), 'w',
                  encoding='utf-8') as f:
            f.write(
                'relationship rel-bad\n'
                '\tfromColumn: Orders.GhostCol\n'
                '\ttoColumn: Products.ProductID\n'
                '\tfromCardinality: many\n'
                '\ttoCardinality: one\n'
            )

        # table TMDL files
        for tname, cols in [('Orders', [('OrderID', 'int64')]),
                            ('Products', [('ProductID', 'string')])]:
            lines = [f'table {tname}']
            for c, d in cols:
                lines.append(f'\tcolumn {c}')
                lines.append(f'\t\tdataType: {d}')
            with open(os.path.join(tables_dir, f'{tname}.tmdl'), 'w',
                      encoding='utf-8') as f:
                f.write('\n'.join(lines) + '\n')

        result = ArtifactValidator.validate_project(proj_dir)
        self.assertTrue(any('GhostCol' in w for w in result.get('warnings', [])))


class TestDistinctcountIfConversion(unittest.TestCase):
    """DISTINCTCOUNT(IF(...)) must use CALCULATE+FILTER, not AGGX."""

    def test_simple_condition(self):
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        result = convert_tableau_formula_to_dax(
            'COUNTD(IF [Won Flag]="Y" THEN [Opportunity Id] END)',
            table_name='Opportunities',
        )
        self.assertNotIn('DISTINCTCOUNT(IF', result)
        self.assertIn('CALCULATE(DISTINCTCOUNT(', result)
        self.assertIn("FILTER('Opportunities'", result)

    def test_not_condition(self):
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        result = convert_tableau_formula_to_dax(
            'COUNTD(IF NOT [Is Open Opportunity?] THEN [Opportunity Id] END)',
            table_name='Facts',
        )
        self.assertNotIn('DISTINCTCOUNT(IF', result)
        self.assertIn('DISTINCTCOUNT(', result)
        self.assertIn("FILTER('Facts'", result)

    def test_complex_condition(self):
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        result = convert_tableau_formula_to_dax(
            'COUNTD(IF STARTSWITH([Category], "Closed") AND [Won]="Y" THEN [Id] END)',
            table_name='Data',
        )
        self.assertNotIn('DISTINCTCOUNT(IF', result)
        self.assertIn('DISTINCTCOUNT(', result)
        self.assertIn("FILTER('Data'", result)

    def test_plain_distinctcount_unchanged(self):
        """DISTINCTCOUNT([Column]) without IF should remain unchanged."""
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        result = convert_tableau_formula_to_dax(
            'COUNTD([Opportunity Id])',
            table_name='Data',
        )
        self.assertIn('DISTINCTCOUNT(', result)
        self.assertNotIn('FILTER', result)
        self.assertNotIn('CALCULATE', result)


class TestStringLiteralMeasureSkip(unittest.TestCase):
    """Formulas that are pure quoted strings should be skipped as measures."""

    def test_string_formula_skipped(self):
        from powerbi_import.tmdl_generator import _build_table
        table = {
            'name': 'T',
            'columns': [{'name': 'Col1', 'datatype': 'string',
                          'sourceColumn': 'Col1', 'role': 'dimension'}],
        }
        calcs = [
            {'name': 'KPI_Calc', 'caption': 'KPI_Calc',
             'formula': '"Count Distinct of IF [Flag]=""Y"" THEN [Id] END"',
             'role': 'measure', 'datatype': 'string'},
            {'name': 'RealMeasure', 'caption': 'Real Measure',
             'formula': 'SUM([Col1])',
             'role': 'measure', 'datatype': 'real'},
        ]
        ctx = {
            'calc_map': {}, 'param_map': {}, 'column_table_map': {},
            'measure_names': set(), 'param_values': {},
            'col_metadata_map': {}, 'compute_using_map': {},
        }
        result = _build_table(table, {}, calcs, {}, ctx)
        measure_names = [m.get('name') for m in result.get('measures', [])]
        self.assertNotIn('KPI_Calc', measure_names)
        self.assertIn('Real Measure', measure_names)


class TestPublicCustomVisualsInReportJson(unittest.TestCase):
    """Verify that publicCustomVisuals is injected into report.json when custom visuals are used."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _make_generator(self):
        from powerbi_import.pbip_generator import PowerBIProjectGenerator
        return PowerBIProjectGenerator()

    def test_gantt_custom_visual_registered(self):
        """When a worksheet uses a Gantt bar mark, publicCustomVisuals should
        include 'ganttChart' in the generated report.json."""
        gen = self._make_generator()
        converted = {
            'worksheets': [{
                'name': 'Gantt Sheet',
                'fields': [{'name': 'Task', 'role': 'dimension'},
                           {'name': 'Duration', 'role': 'measure'}],
                'original_mark_class': 'ganttbar',
                'chart_type': 'ganttChart',
            }],
            'dashboards': [],
            'datasources': [{'name': 'Sample', 'tables': [
                {'name': 'Tasks', 'columns': [
                    {'name': 'Task', 'datatype': 'string', 'role': 'dimension'},
                    {'name': 'Duration', 'datatype': 'int64', 'role': 'measure'},
                ]}
            ]}],
            'calculations': [], 'parameters': [], 'filters': [],
            'stories': [], 'actions': [], 'sets': [], 'groups': [],
            'bins': [], 'hierarchies': [], 'sort_orders': [], 'aliases': [],
            'custom_sql': [], 'user_filters': [],
        }
        report_dir = gen.create_report_structure(
            self.tmpdir, 'TestGantt', converted)
        report_json_path = os.path.join(
            report_dir, 'definition', 'report.json')
        self.assertTrue(os.path.exists(report_json_path))
        with open(report_json_path, 'r', encoding='utf-8') as f:
            rj = json.load(f)
        self.assertIn('publicCustomVisuals', rj)
        self.assertIn('ganttChart', rj['publicCustomVisuals'])

    def test_no_custom_visuals_no_key(self):
        """When no custom visuals are used, publicCustomVisuals should not appear."""
        gen = self._make_generator()
        converted = {
            'worksheets': [{
                'name': 'Bar Sheet',
                'fields': [{'name': 'Category', 'role': 'dimension'},
                           {'name': 'Sales', 'role': 'measure'}],
                'chart_type': 'clusteredBarChart',
            }],
            'dashboards': [],
            'datasources': [{'name': 'Sample', 'tables': [
                {'name': 'Data', 'columns': [
                    {'name': 'Category', 'datatype': 'string', 'role': 'dimension'},
                    {'name': 'Sales', 'datatype': 'int64', 'role': 'measure'},
                ]}
            ]}],
            'calculations': [], 'parameters': [], 'filters': [],
            'stories': [], 'actions': [], 'sets': [], 'groups': [],
            'bins': [], 'hierarchies': [], 'sort_orders': [], 'aliases': [],
            'custom_sql': [], 'user_filters': [],
        }
        report_dir = gen.create_report_structure(
            self.tmpdir, 'TestBar', converted)
        report_json_path = os.path.join(
            report_dir, 'definition', 'report.json')
        with open(report_json_path, 'r', encoding='utf-8') as f:
            rj = json.load(f)
        self.assertNotIn('publicCustomVisuals', rj)


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


class TestStringLiteralParameterSkip(unittest.TestCase):
    """KPI-style parameters with embedded quotes in values should be skipped
    by _create_parameter_tables; simple string params should create measures."""

    def test_kpi_string_param_with_embedded_quotes_skipped(self):
        from powerbi_import.tmdl_generator import _create_parameter_tables
        model = {'model': {'tables': [
            {'name': 'Main', 'columns': [], 'measures': []}
        ]}}
        params = [
            # Value has embedded quotes (e.g. IF [Col]="Y") — skip
            {'caption': 'KPI_Calc', 'datatype': 'string',
             'value': '"Average of IF [Won Flag]="Y" THEN [Amount] END"',
             'domain_type': 'any', 'allowable_values': []},
            {'caption': 'Real Param', 'datatype': 'real',
             'value': '42', 'domain_type': 'any', 'allowable_values': []},
        ]
        _create_parameter_tables(model, params, 'Main')
        measure_names = [m['name'] for m in model['model']['tables'][0].get('measures', [])]
        self.assertNotIn('KPI_Calc', measure_names,
                         "String param with embedded quotes should be skipped")
        self.assertIn('Real Param', measure_names,
                      "Real numeric parameter should be kept")

    def test_simple_string_param_creates_measure(self):
        """Simple string params like pOpportunityOwner_Champions='CHAMPIONS'
        should create measures so DAX referencing [caption] resolves."""
        from powerbi_import.tmdl_generator import _create_parameter_tables
        model = {'model': {'tables': [
            {'name': 'Main', 'columns': [], 'measures': []}
        ]}}
        params = [
            {'caption': 'pOpportunityOwner_Champions', 'datatype': 'string',
             'value': '"CHAMPIONS"',
             'domain_type': 'any', 'allowable_values': []},
            {'caption': 'pOpportunityOwner_Required', 'datatype': 'string',
             'value': '"REQUIRED IMPROVEMENTS"',
             'domain_type': 'any', 'allowable_values': []},
        ]
        _create_parameter_tables(model, params, 'Main')
        measure_names = [m['name'] for m in model['model']['tables'][0].get('measures', [])]
        self.assertIn('pOpportunityOwner_Champions', measure_names,
                      "Simple string param should produce a measure")
        self.assertIn('pOpportunityOwner_Required', measure_names,
                      "Simple string param should produce a measure")
        # Verify the DAX expression is correct
        for m in model['model']['tables'][0]['measures']:
            if m['name'] == 'pOpportunityOwner_Champions':
                self.assertEqual(m['expression'], '"CHAMPIONS"')


class TestOrphanFieldsFilteredFromVisuals(unittest.TestCase):
    """Fields that don't exist in the semantic model should be excluded
    from visual queryState to avoid 'Fields that need to be fixed' errors."""

    def test_orphan_field_excluded(self):
        from powerbi_import.pbip_generator import PowerBIProjectGenerator
        gen = PowerBIProjectGenerator()
        # Simulate _build_field_mapping output
        gen._field_map = {
            'Sales': ('Main', 'Sales'),
            'KPI_Desc': ('Main', 'KPI_Desc'),
            'Region': ('Main', 'Region'),
        }
        gen._main_table = 'Main'
        gen._measure_names = {'Sales', 'KPI_Desc'}
        gen._bim_measure_names = {'Sales'}  # KPI_Desc is NOT in BIM
        gen._datasources_ref = []
        # Actual symbols in the model — KPI_Desc was skipped
        gen._actual_bim_symbols = {('Main', 'Sales'), ('Main', 'Region')}

        ws = {
            'name': 'Sheet1',
            'fields': [
                {'name': 'Region', 'shelf': 'rows', 'role': 'dimension'},
                {'name': 'Sales', 'shelf': 'columns', 'role': 'measure'},
                {'name': 'KPI_Desc', 'shelf': 'columns', 'role': 'measure'},
            ],
            'chart_type': 'clusteredBarChart',
        }
        query = gen._build_visual_query(ws)
        # Collect all queryRef values from the query state
        refs = set()
        if query:
            for role_data in query.get('queryState', {}).values():
                for proj in role_data.get('projections', []):
                    refs.add(proj.get('queryRef', ''))
        self.assertIn('Main.Sales', refs)
        self.assertIn('Main.Region', refs)
        self.assertNotIn('Main.KPI_Desc', refs,
                         "Orphan field should be excluded from visual query")


class TestMakedateParamValuesConversion(unittest.TestCase):
    """MAKEDATE/MAKEDATETIME in param_values should be converted to DATE."""

    def test_makedate_inlined_as_date(self):
        """When a calc column inlines a literal MAKEDATE() value, the result
        should use DAX DATE() instead of the unconverted Tableau function."""
        from tableau_export.dax_converter import convert_tableau_formula_to_dax

        # Simulate: __MyToday calc has formula 'MAKEDATE(2022,04,18)'
        # Days to Close references __MyToday which gets inlined via param_values
        dax = convert_tableau_formula_to_dax(
            'DATEDIFF("day", [__MyToday], [CloseDate])',
            column_name='Days to Close',
            table_name='Main',
            calc_map={},
            param_map={},
            column_table_map={'CloseDate': 'Main'},
            measure_names=set(),
            is_calc_column=True,
            param_values={'__MyToday': 'DATE(2022,04,18)'},
        )
        self.assertIn('DATE(2022,04,18)', dax)
        self.assertNotIn('MAKEDATE', dax)

    def test_makedatetime_inlined_as_date(self):
        from tableau_export.dax_converter import convert_tableau_formula_to_dax

        dax = convert_tableau_formula_to_dax(
            '[__Cutoff]',
            column_name='Cutoff',
            table_name='Main',
            calc_map={},
            param_map={},
            column_table_map={},
            measure_names=set(),
            is_calc_column=True,
            param_values={'__Cutoff': 'DATE(2023,01,01)'},
        )
        self.assertIn('DATE(2023,01,01)', dax)


class TestCalcColumnInColumnTableMap(unittest.TestCase):
    """Dimension-role calculations (calc columns) should appear in
    column_table_map so cross-table references resolve correctly."""

    def test_calc_columns_registered(self):
        from powerbi_import.tmdl_generator import _collect_semantic_context

        datasources = [{
            'name': 'ds1',
            'connection': {'type': 'sqlserver'},
            'tables': [
                {
                    'name': 'Orders',
                    'columns': [
                        {'name': 'Amount', 'datatype': 'real'},
                        {'name': 'ProductId', 'datatype': 'integer'},
                    ],
                },
                {
                    'name': 'Products',
                    'columns': [
                        {'name': 'Id', 'datatype': 'integer'},
                        {'name': 'Name', 'datatype': 'string'},
                    ],
                },
            ],
            'calculations': [
                {
                    'name': '[IsExpensive]',
                    'caption': 'IsExpensive',
                    'formula': 'IF [Amount] > 1000 THEN "Y" ELSE "N" END',
                    'role': 'dimension',
                    'datasource_name': 'ds1',
                },
            ],
            'relationships': [],
        }]
        ctx = _collect_semantic_context(datasources, {
            'parameters': [], 'sets': [], 'groups': [], 'bins': [],
            'hierarchies': [], 'user_filters': [], 'datasource_filters': [],
            'hyper_files': [], 'table_extensions': [], 'data_blending': [],
            'linguistic_synonyms': [],
        })
        ctm = ctx['column_table_map']
        # Physical columns
        self.assertIn('Amount', ctm)
        # Calc column should also be registered
        self.assertIn('IsExpensive', ctm)


class TestCalcColumnsExcludedFromMeasureNames(unittest.TestCase):
    """Dimension-role calculations should not be in measure_names so
    _resolve_columns qualifies them via column_table_map."""

    def test_dimension_role_not_in_measure_names(self):
        from powerbi_import.tmdl_generator import _collect_semantic_context

        datasources = [{
            'name': 'ds1',
            'connection': {'type': 'sqlserver'},
            'tables': [
                {
                    'name': 'Facts',
                    'columns': [{'name': 'Value', 'datatype': 'real'}],
                },
            ],
            'calculations': [
                {
                    'name': '[IsActive]',
                    'caption': 'IsActive',
                    'formula': '[Status] = "Active"',
                    'role': 'dimension',
                    'datasource_name': 'ds1',
                },
                {
                    'name': '[TotalValue]',
                    'caption': 'TotalValue',
                    'formula': 'SUM([Value])',
                    'role': 'measure',
                    'datasource_name': 'ds1',
                },
            ],
            'relationships': [],
        }]
        ctx = _collect_semantic_context(datasources, {
            'parameters': [], 'sets': [], 'groups': [], 'bins': [],
            'hierarchies': [], 'user_filters': [], 'datasource_filters': [],
            'hyper_files': [], 'table_extensions': [], 'data_blending': [],
            'linguistic_synonyms': [],
        })
        mn = ctx['dax_context']['measure_names']
        self.assertNotIn('IsActive', mn, "Calc column should not be in measure_names")
        self.assertIn('TotalValue', mn, "Measure should be in measure_names")


class TestSumxCrossTableRelated(unittest.TestCase):
    """SUMX with cross-table refs should use RELATED for the non-iteration
    table, and _infer_iteration_table should prefer non-default table."""

    def test_infer_prefers_non_default(self):
        from tableau_export.dax_converter import _infer_iteration_table

        # Two tables, one is the default → prefer the other
        inner = "IF('DimTable'[Flag], 'FactTable'[Amount], BLANK())"
        result = _infer_iteration_table(inner, 'DimTable')
        self.assertEqual(result, 'FactTable')

    def test_wrap_cross_table_related(self):
        from tableau_export.dax_converter import _wrap_cross_table_related

        inner = "'Dim'[Flag]*'Fact'[Amount]"
        result = _wrap_cross_table_related(inner, 'Fact')
        self.assertIn("RELATED('Dim'[Flag])", result)
        self.assertIn("'Fact'[Amount]", result)
        self.assertNotIn("RELATED('Fact'[Amount])", result)

    def test_sumx_cross_table_full_conversion(self):
        from tableau_export.dax_converter import convert_tableau_formula_to_dax

        # SUM(IF [DimCalc] THEN [FactAmount] END)
        # with DimCalc on DimTable and FactAmount on FactTable
        dax = convert_tableau_formula_to_dax(
            'SUM(FLOAT(IF [IsOpen] THEN [Revenue] END))',
            column_name='Pipeline',
            table_name='DimTable',
            calc_map={},
            param_map={},
            column_table_map={'IsOpen': 'DimTable', 'Revenue': 'FactTable'},
            measure_names=set(),
            is_calc_column=False,
            param_values={},
        )
        # SUMX should iterate over FactTable (non-default)
        self.assertIn("SUMX('FactTable'", dax)
        # DimTable refs should be wrapped in RELATED
        self.assertIn("RELATED('DimTable'[IsOpen])", dax)
        # FactTable refs should NOT be wrapped
        self.assertNotIn("RELATED('FactTable'", dax)


class TestReplaceRelatedInAggxContext(unittest.TestCase):
    """_replace_related_in_aggx_context should convert RELATED to LOOKUPVALUE
    inside SUMX/AVERAGEX when the m2m pair matches the iteration table."""

    def test_related_in_sumx_converted(self):
        from powerbi_import.tmdl_generator import _replace_related_in_aggx_context

        m2m_pairs = {
            ('Opportunities', 'Created By'): ('Id', 'CreatedById'),
            ('Created By', 'Opportunities'): ('CreatedById', 'Id'),
        }
        expr = "SUMX('Opportunities', IF(RELATED('Created By'[Flag]), 'Opportunities'[Amount], BLANK()))"
        result = _replace_related_in_aggx_context(expr, m2m_pairs)
        self.assertIn("LOOKUPVALUE('Created By'[Flag]", result)
        self.assertNotIn("RELATED('Created By'[Flag])", result)

    def test_no_aggx_unchanged(self):
        from powerbi_import.tmdl_generator import _replace_related_in_aggx_context

        m2m_pairs = {('A', 'B'): ('id', 'fk')}
        expr = "IF(RELATED('B'[col]), 1, 0)"
        result = _replace_related_in_aggx_context(expr, m2m_pairs)
        self.assertEqual(result, expr, "Non-AGGX expression should not be modified")


class TestRoundSingleArgFix(unittest.TestCase):
    """Tableau ROUND(x) with 1 arg should become DAX ROUND(x, 0)."""

    def test_single_arg_round(self):
        from tableau_export.dax_converter import _fix_round_single_arg

        self.assertEqual(_fix_round_single_arg("ROUND([X])"), "ROUND([X], 0)")

    def test_two_arg_round_unchanged(self):
        from tableau_export.dax_converter import _fix_round_single_arg

        expr = "ROUND([X], 2)"
        self.assertEqual(_fix_round_single_arg(expr), expr)

    def test_nested_round(self):
        from tableau_export.dax_converter import _fix_round_single_arg

        result = _fix_round_single_arg("FORMAT(ROUND([V]), \"0\") & \" d\"")
        self.assertIn("ROUND([V], 0)", result)

    def test_mixed_rounds(self):
        from tableau_export.dax_converter import _fix_round_single_arg

        expr = "ROUND([A]) + ROUND([B], 1)"
        result = _fix_round_single_arg(expr)
        self.assertIn("ROUND([A], 0)", result)
        self.assertIn("ROUND([B], 1)", result)


class TestFilterControlParamResolution(unittest.TestCase):
    """Filter controls should resolve field names from `param` when
    `calc_column_id` is empty, instead of falling back to the worksheet name."""

    def _make_generator(self, bim_symbols=None, bim_measures=None):
        from powerbi_import.pbip_generator import PowerBIProjectGenerator
        gen = PowerBIProjectGenerator.__new__(PowerBIProjectGenerator)
        gen._actual_bim_symbols = bim_symbols or set()
        gen._actual_bim_measure_names = bim_measures or set()
        gen._field_map = {}
        return gen

    def test_param_field_resolved_from_param_ref(self):
        """When calc_column_id is empty, the calc ID should be extracted from
        the `param` field and resolved via calc_id_to_caption."""
        import tempfile, shutil
        gen = self._make_generator(
            bim_symbols={('T', 'Probability %')},
            bim_measures=set(),
        )
        tmpdir = tempfile.mkdtemp()
        try:
            obj = {
                'type': 'filter_control',
                'name': 'Pipeline Detail Table',
                'field': 'Pipeline Detail Table',
                'param': '[ds].[usr:Calc_123:qk]',
                'calc_column_id': '',
                'position': {'x': 0, 'y': 0, 'w': 100, 'h': 40},
            }
            calc_map = {'Calc_123': 'Probability %'}
            converted = {'datasources': [{'tables': [{'name': 'T', 'columns': [{'name': 'Probability %'}]}], 'calculations': []}]}
            gen._create_visual_filter_control(
                tmpdir, obj, 1.0, 1.0, 0, calc_map, converted)
            # Slicer should be created with resolved column name
            import glob, json
            visuals = glob.glob(os.path.join(tmpdir, '*', 'visual.json'))
            self.assertEqual(len(visuals), 1)
            data = json.loads(open(visuals[0]).read())
            query_prop = data['visual']['query']['queryState']['Values']['projections'][0]['field']['Column']['Property']
            self.assertEqual(query_prop, 'Probability %')
        finally:
            shutil.rmtree(tmpdir)

    def test_measure_slicer_skipped(self):
        """Slicers referencing measures should be skipped — measures cannot
        be slicer fields in Power BI."""
        import tempfile, shutil
        gen = self._make_generator(
            bim_symbols={('T', 'Pipeline Value')},
            bim_measures={'Pipeline Value'},
        )
        tmpdir = tempfile.mkdtemp()
        try:
            obj = {
                'type': 'filter_control',
                'name': 'Pipeline Detail Table',
                'field': 'Pipeline Detail Table',
                'param': '[ds].[usr:LinPack_123:qk]',
                'calc_column_id': '',
                'position': {'x': 0, 'y': 0, 'w': 100, 'h': 40},
            }
            calc_map = {'LinPack_123': 'Pipeline Value'}
            converted = {'datasources': []}
            gen._create_visual_filter_control(
                tmpdir, obj, 1.0, 1.0, 0, calc_map, converted)
            # No slicer should be created
            import glob
            visuals = glob.glob(os.path.join(tmpdir, '*', 'visual.json'))
            self.assertEqual(len(visuals), 0, "Measure-based slicer should be skipped")
        finally:
            shutil.rmtree(tmpdir)

    def test_unknown_field_slicer_skipped(self):
        """Slicers referencing fields not in the semantic model should be
        skipped to avoid 'missing field' errors in PBI Desktop."""
        import tempfile, shutil
        gen = self._make_generator(
            bim_symbols={('T', 'RealColumn')},
            bim_measures=set(),
        )
        tmpdir = tempfile.mkdtemp()
        try:
            obj = {
                'type': 'filter_control',
                'name': 'SomeWorksheet',
                'field': 'SomeWorksheet',
                'param': '',
                'calc_column_id': '',
                'position': {'x': 0, 'y': 0, 'w': 100, 'h': 40},
            }
            calc_map = {}
            converted = {'datasources': []}
            gen._create_visual_filter_control(
                tmpdir, obj, 1.0, 1.0, 0, calc_map, converted)
            import glob
            visuals = glob.glob(os.path.join(tmpdir, '*', 'visual.json'))
            self.assertEqual(len(visuals), 0, "Unknown-field slicer should be skipped")
        finally:
            shutil.rmtree(tmpdir)


class TestMCalcColumnMeasureRefFallback(unittest.TestCase):
    """Calcs that reference measures must be measures themselves, not
    calc columns — DAX calc columns cannot reference measures."""

    def test_dimension_calc_with_aggregation_becomes_measure(self):
        """A dimension-role calc with aggregation (SUM/MAX/etc) must be
        a measure — aggregation requires filter context."""
        from powerbi_import.tmdl_generator import _build_semantic_model

        calculations = [
            {
                'name': 'Profile Score',
                'caption': 'Profile Score',
                'formula': 'IF SUM([Amount]) <= 100 then "1" ELSE "2" END',
                'role': 'dimension',
                'datatype': 'string',
                'datasource_name': 'ds1',
            },
        ]
        datasources = [{
            'name': 'ds1',
            'tables': [{
                'name': 'Sales',
                'type': 'table',
                'columns': [
                    {'name': 'Amount', 'datatype': 'real'},
                    {'name': 'Region', 'datatype': 'string'},
                ]
            }],
            'calculations': calculations,
            'relationships': [],
            'connection': {'type': 'sqlserver', 'server': 'localhost', 'database': 'db'}
        }]
        extra = {
            'parameters': [],
            'hierarchies': [],
            'sets': [],
            'groups': [],
            'bins': [],
        }
        model = _build_semantic_model(datasources, 'TestAgg', extra)

        sales_table = None
        for t in model['model']['tables']:
            if t['name'] == 'Sales':
                sales_table = t
                break
        self.assertIsNotNone(sales_table)

        # Profile Score has aggregation → must be a measure, not a calc column
        measure_names = {m['name'] for m in sales_table.get('measures', [])}
        col_names = {c['name'] for c in sales_table.get('columns', [])}
        self.assertIn('Profile Score', measure_names,
                      "Dimension calc with aggregation should be a measure")
        self.assertNotIn('Profile Score', col_names,
                         "Dimension calc with aggregation should NOT be a column")

    def test_calc_referencing_measure_becomes_measure(self):
        """A dimension-role calc that references only measures (via INT())
        must also become a measure — calc columns cannot reference measures."""
        from powerbi_import.tmdl_generator import _build_semantic_model

        calculations = [
            {
                'name': 'Profile Score',
                'caption': 'Profile Score',
                'formula': 'IF SUM([Amount]) <= 100 then "1" ELSE "2" END',
                'role': 'dimension',
                'datatype': 'string',
                'datasource_name': 'ds1',
            },
            {
                'name': 'Score (num)',
                'caption': 'Score (num)',
                'formula': 'INT([Profile Score])',
                'role': 'dimension',
                'datatype': 'integer',
                'datasource_name': 'ds1',
            },
        ]
        datasources = [{
            'name': 'ds1',
            'tables': [{
                'name': 'Sales',
                'type': 'table',
                'columns': [
                    {'name': 'Amount', 'datatype': 'real'},
                    {'name': 'Region', 'datatype': 'string'},
                ]
            }],
            'calculations': calculations,
            'relationships': [],
            'connection': {'type': 'sqlserver', 'server': 'localhost', 'database': 'db'}
        }]
        extra = {
            'parameters': [],
            'hierarchies': [],
            'sets': [],
            'groups': [],
            'bins': [],
        }
        model = _build_semantic_model(datasources, 'TestMRef', extra)

        sales_table = None
        for t in model['model']['tables']:
            if t['name'] == 'Sales':
                sales_table = t
                break
        self.assertIsNotNone(sales_table)

        # Score (num) references a measure → must be a measure too
        measure_names = {m['name'] for m in sales_table.get('measures', [])}
        col_names = {c['name'] for c in sales_table.get('columns', [])}
        self.assertIn('Score (num)', measure_names,
                      "Calc referencing a measure should be a measure")
        self.assertNotIn('Score (num)', col_names,
                         "Calc referencing a measure should NOT be a column")

    def test_cascading_reclassification(self):
        """Calcs forming a chain (base→num→class) should all cascade to
        measures when the base has aggregation."""
        from powerbi_import.tmdl_generator import _build_semantic_model

        calculations = [
            {
                'name': 'Rating',
                'caption': 'Rating',
                'formula': 'IF MAX([Score]) > 80 THEN "High" ELSE "Low" END',
                'role': 'dimension',
                'datatype': 'string',
                'datasource_name': 'ds1',
            },
            {
                'name': 'Rating (num)',
                'caption': 'Rating (num)',
                'formula': 'INT([Rating])',
                'role': 'dimension',
                'datatype': 'integer',
                'datasource_name': 'ds1',
            },
            {
                'name': 'Rating Class',
                'caption': 'Rating Class',
                'formula': 'IF [Rating (num)] > 3 THEN "Excellent" ELSE "Average" END',
                'role': 'dimension',
                'datatype': 'string',
                'datasource_name': 'ds1',
            },
        ]
        datasources = [{
            'name': 'ds1',
            'tables': [{
                'name': 'Sales',
                'type': 'table',
                'columns': [
                    {'name': 'Score', 'datatype': 'integer'},
                ]
            }],
            'calculations': calculations,
            'relationships': [],
            'connection': {'type': 'sqlserver', 'server': 'localhost', 'database': 'db'}
        }]
        extra = {
            'parameters': [],
            'hierarchies': [],
            'sets': [],
            'groups': [],
            'bins': [],
        }
        model = _build_semantic_model(datasources, 'TestCascade', extra)

        sales_table = None
        for t in model['model']['tables']:
            if t['name'] == 'Sales':
                sales_table = t
                break
        self.assertIsNotNone(sales_table)

        measure_names = {m['name'] for m in sales_table.get('measures', [])}
        # All three should be measures (cascading from Rating's aggregation)
        self.assertIn('Rating', measure_names)
        self.assertIn('Rating (num)', measure_names)
        self.assertIn('Rating Class', measure_names)

    def test_calc_col_referencing_physical_column_stays_m(self):
        """A calc column referencing a physical source column should stay as M."""
        from powerbi_import.tmdl_generator import _build_semantic_model

        calculations = [
            {
                'name': 'Double Qty',
                'caption': 'Double Qty',
                'formula': '[Quantity] * 2',
                'role': 'dimension',
                'datatype': 'integer',
                'datasource_name': 'ds1',
            },
        ]
        datasources = [{
            'name': 'ds1',
            'tables': [{
                'name': 'Orders',
                'type': 'table',
                'columns': [
                    {'name': 'Quantity', 'datatype': 'integer'},
                ]
            }],
            'calculations': calculations,
            'relationships': [],
            'connection': {'type': 'sqlserver', 'server': 'localhost', 'database': 'db'}
        }]
        extra = {
            'parameters': [],
            'hierarchies': [],
            'sets': [],
            'groups': [],
            'bins': [],
        }
        model = _build_semantic_model(datasources, 'TestMPhys', extra)

        orders_table = None
        for t in model['model']['tables']:
            if t['name'] == 'Orders':
                orders_table = t
                break
        self.assertIsNotNone(orders_table)

        dbl_col = None
        for c in orders_table.get('columns', []):
            if c.get('name') == 'Double Qty':
                dbl_col = c
                break
        self.assertIsNotNone(dbl_col, "Double Qty column should exist")
        # Should be M-based (sourceColumn, no expression)
        self.assertIn('sourceColumn', dbl_col,
                      "Double Qty should be M-based source column")
        self.assertNotIn('expression', dbl_col,
                         "Double Qty should NOT be a DAX calc column")


class TestCamelCaseSplitColumnResolution(unittest.TestCase):
    """Salesforce-style CamelCase-split column names must resolve to actual
    suffixed column names (e.g. 'First Name' → 'FirstName (Created By)')."""

    def test_camelcase_split_resolves_to_suffixed_column(self):
        """A formula referencing [First Name] should resolve to
        'Table'[FirstName (Table)] when the physical column uses the
        Salesforce naming convention."""
        from powerbi_import.tmdl_generator import _build_semantic_model

        calculations = [
            {
                'name': 'Full Name',
                'caption': 'Full Name',
                'formula': "[First Name]+' '+[Last Name]",
                'role': 'dimension',
                'datatype': 'string',
                'datasource_name': 'ds1',
            },
        ]
        datasources = [{
            'name': 'ds1',
            'tables': [{
                'name': 'Created By',
                'type': 'table',
                'columns': [
                    {'name': 'FirstName (Created By)', 'datatype': 'string'},
                    {'name': 'LastName (Created By)', 'datatype': 'string'},
                    {'name': 'Id', 'datatype': 'string'},
                ]
            }],
            'calculations': calculations,
            'relationships': [],
            'connection': {'type': 'salesforce', 'server': 'salesforce.com'}
        }]
        extra = {
            'parameters': [],
            'hierarchies': [],
            'sets': [],
            'groups': [],
            'bins': [],
        }
        model = _build_semantic_model(datasources, 'TestSF', extra)

        cb_table = None
        for t in model['model']['tables']:
            if t['name'] == 'Created By':
                cb_table = t
                break
        self.assertIsNotNone(cb_table)

        # Full Name should exist and reference the correct suffixed columns
        full_name = None
        for c in cb_table.get('columns', []):
            if c.get('name') == 'Full Name':
                full_name = c
                break
        # May be M-based or DAX — either way, the column name references
        # should use the actual suffixed names, not bare 'First Name'
        if full_name is None:
            # Check measures in case it was classified as a measure
            for m in cb_table.get('measures', []):
                if m.get('name') == 'Full Name':
                    full_name = m
                    break
        self.assertIsNotNone(full_name, "Full Name should exist")

        # Check partition M expression or DAX expression for correct column refs
        has_correct_ref = False
        # Check M partition
        for p in cb_table.get('partitions', []):
            expr = p.get('source', {}).get('expression', '')
            if 'FirstName (Created By)' in expr:
                has_correct_ref = True
        # Check DAX expression
        dax_expr = full_name.get('expression', '')
        if 'FirstName (Created By)' in dax_expr:
            has_correct_ref = True
        self.assertTrue(has_correct_ref,
                        "Column ref should use 'FirstName (Created By)', "
                        f"not bare 'First Name'. Got: {dax_expr}")


class TestPBIDesktopValidation(unittest.TestCase):
    """Tests for automated PBI Desktop error detection (Bug 15)."""

    def _create_model(self, tables_tmdl, relationships_tmdl=None, model_tmdl=None):
        """Create a temporary SemanticModel directory with TMDL files."""
        tmpdir = tempfile.mkdtemp()
        proj_dir = os.path.join(tmpdir, 'Test')
        sm_dir = os.path.join(proj_dir, 'Test.SemanticModel', 'definition')
        tables_dir = os.path.join(sm_dir, 'tables')
        os.makedirs(tables_dir)
        # model.tmdl
        model_content = model_tmdl or "model Model\n\tculture: en-US\n"
        with open(os.path.join(sm_dir, 'model.tmdl'), 'w', encoding='utf-8') as f:
            f.write(model_content)
        # table files
        for name, content in tables_tmdl.items():
            with open(os.path.join(tables_dir, f'{name}.tmdl'), 'w', encoding='utf-8') as f:
                f.write(content)
        # relationships.tmdl
        if relationships_tmdl:
            with open(os.path.join(sm_dir, 'relationships.tmdl'), 'w', encoding='utf-8') as f:
                f.write(relationships_tmdl)
        self._tmpdir = tmpdir
        return proj_dir

    def tearDown(self):
        if hasattr(self, '_tmpdir') and os.path.exists(self._tmpdir):
            shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_validate_semantic_references_detects_missing_column(self):
        """validate_semantic_references catches 'Table'[NonExistent]."""
        proj = self._create_model({
            'Orders': (
                "table Orders\n"
                "\tcolumn Id\n"
                "\tcolumn Amount\n"
                "\tmeasure 'Total' = SUM('Orders'[Amount])\n"
                "\tmeasure 'Bad' = SUM('Orders'[NonExistent])\n"
            ),
        })
        sm_dir = os.path.join(proj, 'Test.SemanticModel')
        issues = ArtifactValidator.validate_semantic_references(sm_dir)
        self.assertTrue(any('NonExistent' in i and 'Orders' in i for i in issues))

    def test_validate_lookupvalue_ambiguity_flags_non_key(self):
        """LOOKUPVALUE on non-unique column is flagged."""
        proj = self._create_model(
            {
                'Users': (
                    "table Users\n"
                    "\tcolumn Id\n"
                    "\tcolumn 'Order Amount' = LOOKUPVALUE("
                    "Orders[Amount], Orders[UserId], Users[Id])\n"
                ),
                'Orders': (
                    "table Orders\n"
                    "\tcolumn Id\n"
                    "\tcolumn UserId\n"
                    "\tcolumn Amount\n"
                ),
            },
            relationships_tmdl=(
                "relationship r1\n"
                "\tfromColumn: Orders.UserId\n"
                "\ttoColumn: Users.Id\n"
                "\tfromCardinality: many\n"
                "\ttoCardinality: many\n"
            ),
        )
        sm_dir = os.path.join(proj, 'Test.SemanticModel')
        issues = ArtifactValidator.validate_lookupvalue_ambiguity(sm_dir)
        self.assertTrue(any('LOOKUPVALUE ambiguity' in i for i in issues),
                        f"Expected ambiguity warning, got: {issues}")

    def test_validate_lookupvalue_no_warning_on_key(self):
        """LOOKUPVALUE on a unique key column should not warn."""
        proj = self._create_model(
            {
                'Users': (
                    "table Users\n"
                    "\tcolumn Id\n"
                    "\tcolumn 'Order Amount' = LOOKUPVALUE("
                    "Orders[Amount], Orders[Id], Users[Id])\n"
                ),
                'Orders': (
                    "table Orders\n"
                    "\tcolumn Id\n"
                    "\tcolumn Amount\n"
                ),
            },
            relationships_tmdl=(
                "relationship r1\n"
                "\tfromColumn: Users.Id\n"
                "\ttoColumn: Orders.Id\n"
                "\tfromCardinality: many\n"
                "\ttoCardinality: one\n"
            ),
        )
        sm_dir = os.path.join(proj, 'Test.SemanticModel')
        issues = ArtifactValidator.validate_lookupvalue_ambiguity(sm_dir)
        self.assertEqual(len(issues), 0, f"Expected no warnings, got: {issues}")

    def test_validate_measure_column_context_bare_ref(self):
        """Measure with bare column ref (no aggregation) is flagged."""
        proj = self._create_model({
            'Sales': (
                "table Sales\n"
                "\tcolumn Id\n"
                "\tcolumn Region\n"
                "\tmeasure 'Bad Measure' = 'Sales'[Region]\n"
            ),
        })
        sm_dir = os.path.join(proj, 'Test.SemanticModel')
        issues = ArtifactValidator.validate_measure_column_context(sm_dir)
        self.assertTrue(any('without aggregation' in i for i in issues),
                        f"Expected bare ref warning, got: {issues}")

    def test_validate_measure_column_context_aggregated_ok(self):
        """Measure with aggregated column ref is not flagged."""
        proj = self._create_model({
            'Sales': (
                "table Sales\n"
                "\tcolumn Id\n"
                "\tcolumn Amount\n"
                "\tmeasure 'Total Sales' = SUM('Sales'[Amount])\n"
            ),
        })
        sm_dir = os.path.join(proj, 'Test.SemanticModel')
        issues = ArtifactValidator.validate_measure_column_context(sm_dir)
        self.assertEqual(len(issues), 0, f"Expected no warnings, got: {issues}")

    def test_run_pbi_validation_combined(self):
        """run_pbi_validation combines all checks."""
        proj = self._create_model({
            'Sales': (
                "table Sales\n"
                "\tcolumn Id\n"
                "\tcolumn Amount\n"
                "\tmeasure 'Total' = SUM('Sales'[Amount])\n"
                "\tmeasure 'Bad' = SUM('Sales'[Missing])\n"
            ),
        })
        result = ArtifactValidator.run_pbi_validation(proj)
        self.assertFalse(result['passed'])
        self.assertTrue(any('Missing' in e for e in result['errors']))

    def test_run_pbi_validation_clean_model(self):
        """run_pbi_validation passes on a clean model."""
        proj = self._create_model({
            'Sales': (
                "table Sales\n"
                "\tcolumn Id\n"
                "\tcolumn Amount\n"
                "\tmeasure 'Total' = SUM('Sales'[Amount])\n"
            ),
        })
        result = ArtifactValidator.run_pbi_validation(proj)
        self.assertTrue(result['passed'])
        self.assertEqual(len(result['errors']), 0)

    def test_validate_measure_column_context_bare_ref_inside_if(self):
        """Bare column ref inside IF() is flagged (IF is not an aggregation)."""
        proj = self._create_model({
            'Sales': (
                "table Sales\n"
                "\tcolumn Id\n"
                "\tcolumn Score\n"
                "\tmeasure 'Rating' = IF('Sales'[Score] > 3, \"High\", \"Low\")\n"
            ),
        })
        sm_dir = os.path.join(proj, 'Test.SemanticModel')
        issues = ArtifactValidator.validate_measure_column_context(sm_dir)
        self.assertTrue(any('without aggregation' in i for i in issues),
                        f"Expected bare ref warning inside IF, got: {issues}")

    def test_validate_measure_column_context_ref_inside_sumx_if(self):
        """Column ref inside SUMX(T, IF(T[Col]...)) is NOT flagged."""
        proj = self._create_model({
            'Sales': (
                "table Sales\n"
                "\tcolumn Id\n"
                "\tcolumn Amount\n"
                "\tcolumn Flag\n"
                "\tmeasure 'Conditional Sum' = SUMX('Sales', IF('Sales'[Flag], 'Sales'[Amount], 0))\n"
            ),
        })
        sm_dir = os.path.join(proj, 'Test.SemanticModel')
        issues = ArtifactValidator.validate_measure_column_context(sm_dir)
        self.assertEqual(len(issues), 0,
                         f"Expected no warnings (SUMX provides row context), got: {issues}")


class TestParameterControlSlicerSkip(unittest.TestCase):
    """Parameter control slicers referencing non-existent parameter tables
    should be silently skipped."""

    def _make_generator(self, bim_symbols=None, bim_measures=None):
        from powerbi_import.pbip_generator import PowerBIProjectGenerator
        gen = PowerBIProjectGenerator.__new__(PowerBIProjectGenerator)
        gen._actual_bim_symbols = bim_symbols or set()
        gen._actual_bim_measure_names = bim_measures or set()
        gen._field_map = {}
        return gen

    def test_missing_param_table_slicer_skipped(self):
        """If the parameter table doesn't exist in the model, the slicer
        should not be generated."""
        import tempfile, shutil, glob
        # Model has NO pSelectOpportunityOwner table
        gen = self._make_generator(
            bim_symbols={('Sales', 'Amount'), ('Sales', 'Region')},
            bim_measures=set(),
        )
        tmpdir = tempfile.mkdtemp()
        try:
            obj = {
                'type': 'parameter_control',
                'name': 'param_pSelectOpportunityOwner',
                'param': '[Parameters].[Opportunity Owner Parameter]',
                'param_name': 'Opportunity Owner Parameter',
                'position': {'x': 0, 'y': 0, 'w': 200, 'h': 40},
            }
            converted = {
                'parameters': [
                    {'name': '[Opportunity Owner Parameter]',
                     'caption': 'pSelectOpportunityOwner',
                     'allowable_values': []}
                ]
            }
            gen._create_visual_parameter_control(
                tmpdir, obj, 1.0, 1.0, 0, converted)
            visuals = glob.glob(os.path.join(tmpdir, '*', 'visual.json'))
            self.assertEqual(len(visuals), 0,
                             "Slicer for missing param table should be skipped")
        finally:
            shutil.rmtree(tmpdir)

    def test_existing_param_table_slicer_created(self):
        """If the parameter table exists, the slicer should be created."""
        import tempfile, shutil, glob
        gen = self._make_generator(
            bim_symbols={('pSelectOwner', 'Value'), ('pSelectOwner', 'Name')},
            bim_measures=set(),
        )
        tmpdir = tempfile.mkdtemp()
        try:
            obj = {
                'type': 'parameter_control',
                'name': 'param_pSelectOwner',
                'param': '[Parameters].[Owner Parameter]',
                'param_name': 'Owner Parameter',
                'position': {'x': 0, 'y': 0, 'w': 200, 'h': 40},
            }
            converted = {
                'parameters': [
                    {'name': '[Owner Parameter]',
                     'caption': 'pSelectOwner',
                     'allowable_values': []}
                ]
            }
            gen._create_visual_parameter_control(
                tmpdir, obj, 1.0, 1.0, 0, converted)
            visuals = glob.glob(os.path.join(tmpdir, '*', 'visual.json'))
            self.assertEqual(len(visuals), 1,
                             "Slicer for existing param table should be created")
        finally:
            shutil.rmtree(tmpdir)


class TestMetadataColLocalNameMap(unittest.TestCase):
    """Bug 14: Salesforce columns only in <metadata-record> (not <column>)
    should be mapped to their parent tables and added when referenced."""

    def _make_xml(self):
        """Build minimal datasource XML with metadata records."""
        import xml.etree.ElementTree as ET
        xml_str = '''<datasource name="ds1">
          <connection class="salesforce">
            <metadata-records>
              <metadata-record class="column">
                <local-name>[Opportunity ID]</local-name>
                <remote-name>Id</remote-name>
                <parent-name>[Opportunities]</parent-name>
                <local-type>string</local-type>
                <ordinal>0</ordinal>
                <contains-null>false</contains-null>
              </metadata-record>
              <metadata-record class="column">
                <local-name>[Probability (%)]</local-name>
                <remote-name>Probability</remote-name>
                <parent-name>[Opportunities]</parent-name>
                <local-type>real</local-type>
                <ordinal>1</ordinal>
                <contains-null>true</contains-null>
              </metadata-record>
              <metadata-record class="column">
                <local-name>[Name (Created By)]</local-name>
                <remote-name>Name</remote-name>
                <parent-name>[Created By]</parent-name>
                <local-type>string</local-type>
                <ordinal>0</ordinal>
                <contains-null>false</contains-null>
              </metadata-record>
            </metadata-records>
          </connection>
        </datasource>'''
        return ET.fromstring(xml_str)

    def test_extract_col_local_name_map(self):
        """_extract_col_local_name_map returns local-name → parent-table."""
        from tableau_export.datasource_extractor import _extract_col_local_name_map
        elem = self._make_xml()
        result = _extract_col_local_name_map(elem)
        self.assertEqual(result.get('Opportunity ID'), 'Opportunities')
        self.assertEqual(result.get('Probability (%)'), 'Opportunities')
        self.assertEqual(result.get('Name (Created By)'), 'Created By')

    def test_extract_col_type_map(self):
        """_extract_col_type_map returns local-name → datatype from metadata-records."""
        from tableau_export.datasource_extractor import _extract_col_type_map
        elem = self._make_xml()
        result = _extract_col_type_map(elem)
        self.assertEqual(result.get('Probability (%)'), 'real')
        self.assertEqual(result.get('Opportunity ID'), 'string')

    def test_ensure_calc_referenced_columns_adds_missing(self):
        """_ensure_calc_referenced_columns adds columns to parent tables."""
        from tableau_export.datasource_extractor import _ensure_calc_referenced_columns
        datasource = {
            'tables': [
                {'name': 'Opportunities', 'columns': [
                    {'name': 'Amount', 'datatype': 'real'},
                ]},
                {'name': 'Created By', 'columns': [
                    {'name': 'Id', 'datatype': 'string'},
                ]},
            ],
            'calculations': [
                {'formula': '[Opportunity ID]', 'name': 'calc1'},
                {'formula': '[Probability (%)]/100', 'name': 'calc2'},
            ],
            'col_local_name_map': {
                'Opportunity ID': 'Opportunities',
                'Probability (%)': 'Opportunities',
            },
            'col_type_map': {
                'Probability (%)': 'real',
            },
        }
        _ensure_calc_referenced_columns(datasource)
        opp_cols = {c['name'] for c in datasource['tables'][0]['columns']}
        self.assertIn('Opportunity ID', opp_cols)
        self.assertIn('Probability (%)', opp_cols)
        # Existing column should not be duplicated
        self.assertEqual(sum(1 for c in datasource['tables'][0]['columns']
                            if c['name'] == 'Amount'), 1)
        # Probability (%) should inherit type from col_type_map
        prob_col = [c for c in datasource['tables'][0]['columns']
                    if c['name'] == 'Probability (%)'][0]
        self.assertEqual(prob_col['datatype'], 'real')
        self.assertEqual(prob_col['role'], 'measure')
        # Opportunity ID has no type map entry → defaults to string
        oid_col = [c for c in datasource['tables'][0]['columns']
                   if c['name'] == 'Opportunity ID'][0]
        self.assertEqual(oid_col['datatype'], 'string')

    def test_ensure_calc_referenced_columns_skips_existing(self):
        """Columns already present in the table should not be re-added."""
        from tableau_export.datasource_extractor import _ensure_calc_referenced_columns
        datasource = {
            'tables': [
                {'name': 'Opportunities', 'columns': [
                    {'name': 'Opportunity ID', 'datatype': 'string'},
                ]},
            ],
            'calculations': [
                {'formula': '[Opportunity ID]', 'name': 'calc1'},
            ],
            'col_local_name_map': {
                'Opportunity ID': 'Opportunities',
            },
        }
        _ensure_calc_referenced_columns(datasource)
        self.assertEqual(
            sum(1 for c in datasource['tables'][0]['columns']
                if c['name'] == 'Opportunity ID'), 1)

    def test_column_table_map_supplement_enables_lookupvalue(self):
        """col_local_name_map entries enable cross-table LOOKUPVALUE in DAX."""
        from tableau_export.datasource_extractor import convert_tableau_formula_to_dax
        dax = convert_tableau_formula_to_dax(
            '[Opportunity ID]',
            column_name='calc1',
            table_name='Created By',
            column_table_map={'Opportunity ID': 'Opportunities'},
            measure_names=set(),
            is_calc_column=True,
        )
        # Should use cross-table reference, not 'Created By'[Opportunity ID]
        self.assertNotIn("'Created By'[Opportunity ID]", dax)
        self.assertIn("Opportunities", dax)
        self.assertIn("Opportunity ID", dax)


class TestBareCalcReferenceInlining(unittest.TestCase):
    """Bare (unbracketed) calc references should be inlined in calc columns."""

    def test_bare_param_value_inlined_in_calc_column(self):
        """__MyToday bare ref → DATE(2022,04,18) when is_calc_column=True."""
        from tableau_export.dax_converter import convert_tableau_formula_to_dax as convert_to_dax
        formula = '[Close Date]>DATEADD(\'month\',-36,__MyToday) AND [Close Date] <= __MyToday'
        dax = convert_to_dax(
            formula,
            column_name='Is Last N months',
            table_name='Owned By',
            calc_map={},
            param_map={},
            column_table_map={'Close Date': 'Owned By'},
            measure_names=set(),
            is_calc_column=True,
            param_values={'__MyToday': 'DATE(2022,04,18)'},
        )
        # Should NOT contain bare __MyToday — it should be inlined
        self.assertNotIn('__MyToday', dax)
        self.assertIn('DATE(2022,04,18)', dax)

    def test_bare_param_value_inlined_in_measure(self):
        """__MyToday bare ref → DATE(2022,04,18) even in measures."""
        from tableau_export.dax_converter import convert_tableau_formula_to_dax as convert_to_dax
        formula = '__MyToday'
        dax = convert_to_dax(
            formula,
            column_name='Today',
            table_name='Owned By',
            calc_map={},
            param_map={},
            column_table_map={},
            measure_names={'__MyToday'},
            is_calc_column=False,
            param_values={'__MyToday': 'DATE(2022,04,18)'},
        )
        # Should be inlined (literal values are always safe to inline)
        self.assertIn('DATE(2022,04,18)', dax)
        self.assertNotIn('MAX(', dax)

    def test_bare_ref_not_replaced_inside_string(self):
        """Bare ref inside a string literal should NOT be replaced."""
        from tableau_export.dax_converter import convert_tableau_formula_to_dax as convert_to_dax
        formula = 'IF [X]="__MyToday" THEN 1 ELSE 0 END'
        dax = convert_to_dax(
            formula,
            column_name='Check',
            table_name='T',
            calc_map={},
            param_map={},
            column_table_map={'X': 'T'},
            measure_names=set(),
            is_calc_column=True,
            param_values={'__MyToday': 'DATE(2022,04,18)'},
        )
        # The string literal should remain unchanged
        self.assertIn('"__MyToday"', dax)

    def test_bare_ref_not_replaced_inside_brackets(self):
        """Bare ref inside a [column name] should NOT be replaced."""
        from tableau_export.dax_converter import convert_tableau_formula_to_dax as convert_to_dax
        formula = 'if [Is Closed in Last x Days?] then "Last " + [Parameters].[pDays] + " days" else "Other" end'
        dax = convert_to_dax(
            formula,
            column_name='Review Key',
            table_name='T',
            calc_map={},
            param_map={'pDays': 'Last x Days'},
            column_table_map={'Is Closed in Last x Days?': 'T'},
            measure_names=set(),
            is_calc_column=True,
            param_values={'Last x Days': '"90"'},
        )
        # Column name must NOT have "90" substituted inside brackets
        self.assertIn('[Is Closed in Last x Days?]', dax)
        # But the parameter reference should be inlined
        self.assertIn('"90"', dax)


class TestComparisonOperatorSpacing(unittest.TestCase):
    """Comparison operators (>, <, >=, <=, <>) must have spaces in DAX output."""

    def test_greater_than_gets_spaced(self):
        """']>EDATE' → '] > EDATE' — prevents TMDL parsing issues."""
        from tableau_export.dax_converter import _ensure_comparison_spacing
        result = _ensure_comparison_spacing(
            "'T'[Col]>EDATE(DATE(2022,04,18), -36) && 'T'[Col] <= DATE(2022,04,18)"
        )
        self.assertIn('] > EDATE', result)
        self.assertIn('] <= DATE', result)

    def test_multi_char_operators_spaced(self):
        """>=, <=, <> all get spaces."""
        from tableau_export.dax_converter import _ensure_comparison_spacing
        result = _ensure_comparison_spacing("[A]>=0 && [B]<=100 && [C]<>0")
        self.assertIn('] >= 0', result)
        self.assertIn('] <= 100', result)
        self.assertIn('] <> 0', result)

    def test_already_spaced_preserved(self):
        """Operators that already have spaces are not double-spaced."""
        from tableau_export.dax_converter import _ensure_comparison_spacing
        result = _ensure_comparison_spacing("[A] > 0 && [B] <= 100")
        self.assertIn('] > 0', result)
        self.assertIn('] <= 100', result)
        self.assertNotIn('  ', result)

    def test_string_contents_not_modified(self):
        """Operators inside string literals are preserved."""
        from tableau_export.dax_converter import _ensure_comparison_spacing
        result = _ensure_comparison_spacing('IF([X]>0, "a>b", "c<=d")')
        self.assertIn('"a>b"', result)
        self.assertIn('"c<=d"', result)
        # But the comparison outside the string IS spaced
        self.assertIn('] > 0', result)

    def test_bracket_contents_not_modified(self):
        """Operators inside [column names] are preserved."""
        from tableau_export.dax_converter import _ensure_comparison_spacing
        result = _ensure_comparison_spacing("[Col>Name]>5")
        self.assertIn('[Col>Name]', result)
        self.assertIn('] > 5', result)

    def test_full_conversion_produces_spaced_comparisons(self):
        """End-to-end: DATEADD comparison formula gets properly spaced."""
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        formula = "[Created Date]>DATEADD('month',-36,DATE(2022,04,18)) AND [Created Date] <= DATE(2022,04,18)"
        dax = convert_tableau_formula_to_dax(
            formula, column_name='Filter', table_name='T', is_calc_column=True,
            column_table_map={'Created Date': 'T'},
        )
        self.assertIn('] > EDATE(', dax)
        self.assertIn('] <= DATE(', dax)
        self.assertIn('&&', dax)


if __name__ == '__main__':
    unittest.main()
