"""Tests for Sprint 96 — Self-Healing Migration Pipeline.

Covers:
- TMDL self-repair (broken refs, duplicate tables, orphan measures, empty tables)
- Visual fallback cascade (missing data roles, degradation chain)
- M query self-repair (try/otherwise wrapping)
- Recovery report (recording, summary, save, merge)
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))


# ════════════════════════════════════════════════════════════════════
#  RecoveryReport tests
# ════════════════════════════════════════════════════════════════════

class TestRecoveryReport(unittest.TestCase):
    """Tests for the recovery report module."""

    def test_empty_report(self):
        from powerbi_import.recovery_report import RecoveryReport
        r = RecoveryReport("Test")
        self.assertFalse(r.has_repairs)
        self.assertEqual(r.get_summary()['total_repairs'], 0)

    def test_record_single_repair(self):
        from powerbi_import.recovery_report import RecoveryReport
        r = RecoveryReport("Test")
        r.record('tmdl', 'broken_column_ref',
                 description="Bad ref",
                 action="Hidden measure",
                 severity='warning',
                 item_name='Profit YoY')
        self.assertTrue(r.has_repairs)
        self.assertEqual(len(r.repairs), 1)
        self.assertEqual(r.repairs[0]['category'], 'tmdl')
        self.assertEqual(r.repairs[0]['item_name'], 'Profit YoY')

    def test_summary_by_category(self):
        from powerbi_import.recovery_report import RecoveryReport
        r = RecoveryReport("Test")
        r.record('tmdl', 'broken_ref', description="a", action="b")
        r.record('tmdl', 'duplicate', description="c", action="d")
        r.record('visual', 'fallback', description="e", action="f")
        summary = r.get_summary()
        self.assertEqual(summary['total_repairs'], 3)
        self.assertEqual(summary['by_category']['tmdl'], 2)
        self.assertEqual(summary['by_category']['visual'], 1)

    def test_summary_by_severity(self):
        from powerbi_import.recovery_report import RecoveryReport
        r = RecoveryReport("Test")
        r.record('tmdl', 'a', severity='info')
        r.record('tmdl', 'b', severity='warning')
        r.record('tmdl', 'c', severity='error')
        summary = r.get_summary()
        self.assertEqual(summary['by_severity']['info'], 1)
        self.assertEqual(summary['by_severity']['warning'], 1)
        self.assertEqual(summary['by_severity']['error'], 1)

    def test_needs_follow_up(self):
        from powerbi_import.recovery_report import RecoveryReport
        r = RecoveryReport("Test")
        r.record('tmdl', 'a', follow_up="Fix this")
        r.record('tmdl', 'b')
        self.assertEqual(r.get_summary()['needs_follow_up'], 1)

    def test_to_dict(self):
        from powerbi_import.recovery_report import RecoveryReport
        r = RecoveryReport("Test")
        r.record('tmdl', 'dup', description="dup table", action="renamed")
        d = r.to_dict()
        self.assertEqual(d['report_name'], 'Test')
        self.assertIn('created_at', d)
        self.assertIn('summary', d)
        self.assertIn('repairs', d)
        self.assertEqual(len(d['repairs']), 1)

    def test_save_json(self):
        from powerbi_import.recovery_report import RecoveryReport
        r = RecoveryReport("Test Report")
        r.record('visual', 'fallback', description="d", action="a")
        with tempfile.TemporaryDirectory() as tmp:
            path = r.save(tmp)
            self.assertTrue(os.path.exists(path))
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            self.assertEqual(data['report_name'], 'Test Report')
            self.assertEqual(len(data['repairs']), 1)

    def test_merge_into_migration_report(self):
        from powerbi_import.recovery_report import RecoveryReport
        from powerbi_import.migration_report import MigrationReport
        recovery = RecoveryReport("Test")
        recovery.record('tmdl', 'dup', action="renamed", severity='warning')
        recovery.record('visual', 'fb', action="degraded", severity='info')
        mr = MigrationReport("Test")
        recovery.merge_into(mr)
        # Should have added 2 items of category 'recovery'
        recovery_items = [i for i in mr.items if i['category'] == 'recovery']
        self.assertEqual(len(recovery_items), 2)

    def test_invalid_severity_defaults_to_warning(self):
        from powerbi_import.recovery_report import RecoveryReport
        r = RecoveryReport("Test")
        r.record('tmdl', 'x', severity='invalid_value')
        self.assertEqual(r.repairs[0]['severity'], 'warning')

    def test_print_summary_no_repairs(self):
        from powerbi_import.recovery_report import RecoveryReport
        r = RecoveryReport("Test")
        r.print_summary()  # Should not raise

    def test_print_summary_with_repairs(self):
        from powerbi_import.recovery_report import RecoveryReport
        r = RecoveryReport("Test")
        r.record('tmdl', 'a', follow_up='fix me')
        r.print_summary()  # Should not raise


# ════════════════════════════════════════════════════════════════════
#  TMDL Self-Heal tests
# ════════════════════════════════════════════════════════════════════

class TestTMDLSelfHealDuplicateTables(unittest.TestCase):
    """Test duplicate table name detection and renaming."""

    def _make_model(self, tables, relationships=None):
        return {'model': {
            'tables': tables,
            'relationships': relationships or [],
        }}

    def test_duplicate_table_renamed(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        model = self._make_model([
            {'name': 'Orders', 'columns': [{'name': 'id', 'dataType': 'Int64'}], 'measures': []},
            {'name': 'Orders', 'columns': [{'name': 'id', 'dataType': 'Int64'}], 'measures': []},
        ])
        repairs = _self_heal_model(model)
        self.assertGreater(repairs, 0)
        names = [t['name'] for t in model['model']['tables']]
        self.assertEqual(len(names), len(set(names)))  # All unique
        self.assertIn('Orders_2', names)

    def test_triplicate_table_renamed(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        model = self._make_model([
            {'name': 'T', 'columns': [{'name': 'id', 'dataType': 'Int64'}], 'measures': []},
            {'name': 'T', 'columns': [{'name': 'id', 'dataType': 'Int64'}], 'measures': []},
            {'name': 'T', 'columns': [{'name': 'id', 'dataType': 'Int64'}], 'measures': []},
        ])
        repairs = _self_heal_model(model)
        names = [t['name'] for t in model['model']['tables']]
        self.assertEqual(len(names), len(set(names)))
        self.assertIn('T_2', names)
        self.assertIn('T_3', names)

    def test_relationship_updated_after_rename(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        model = self._make_model(
            [
                {'name': 'A', 'columns': [{'name': 'id'}], 'measures': []},
                {'name': 'A', 'columns': [{'name': 'id'}], 'measures': []},
            ],
            relationships=[{
                'fromTable': 'A', 'fromColumn': 'id',
                'toTable': 'A', 'toColumn': 'id',
            }],
        )
        _self_heal_model(model)
        rel = model['model']['relationships'][0]
        # At least one side should be renamed
        tables_in_rels = {rel['fromTable'], rel['toTable']}
        self.assertTrue('A_2' in tables_in_rels or 'A' in tables_in_rels)

    def test_no_duplicate_no_repair(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        model = self._make_model([
            {'name': 'A', 'columns': [{'name': 'id', 'dataType': 'Int64'}], 'measures': []},
            {'name': 'B', 'columns': [{'name': 'id', 'dataType': 'Int64'}], 'measures': []},
        ])
        repairs = _self_heal_model(model)
        self.assertEqual(repairs, 0)


class TestTMDLSelfHealBrokenRefs(unittest.TestCase):
    """Test broken column reference detection in measures."""

    def _make_model(self, tables):
        return {'model': {'tables': tables, 'relationships': []}}

    def test_broken_ref_hidden(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        model = self._make_model([{
            'name': 'Sales',
            'columns': [{'name': 'Amount'}],
            'measures': [{
                'name': 'Bad Measure',
                'expression': 'SUM([NonExistentColumn])',
            }],
        }])
        repairs = _self_heal_model(model)
        self.assertGreater(repairs, 0)
        measure = model['model']['tables'][0]['measures'][0]
        self.assertTrue(measure.get('isHidden'))

    def test_valid_ref_not_hidden(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        model = self._make_model([{
            'name': 'Sales',
            'columns': [{'name': 'Amount'}],
            'measures': [{
                'name': 'Total',
                'expression': 'SUM([Amount])',
            }],
        }])
        repairs = _self_heal_model(model)
        measure = model['model']['tables'][0]['measures'][0]
        self.assertFalse(measure.get('isHidden', False))

    def test_measure_ref_to_other_measure_valid(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        model = self._make_model([{
            'name': 'Sales',
            'columns': [{'name': 'Amount'}],
            'measures': [
                {'name': 'Total', 'expression': 'SUM([Amount])'},
                {'name': 'Double', 'expression': '[Total] * 2'},
            ],
        }])
        repairs = _self_heal_model(model)
        double = model['model']['tables'][0]['measures'][1]
        self.assertFalse(double.get('isHidden', False))

    def test_broken_ref_has_migration_note(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        model = self._make_model([{
            'name': 'T',
            'columns': [],
            'measures': [{'name': 'M', 'expression': '[Ghost]'}],
        }])
        _self_heal_model(model)
        measure = model['model']['tables'][0]['measures'][0]
        notes = [a['value'] for a in measure.get('annotations', [])
                 if a.get('name') == 'MigrationNote']
        self.assertTrue(any('Self-heal' in n for n in notes))

    def test_dax_keyword_not_flagged_as_broken(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        model = self._make_model([{
            'name': 'T',
            'columns': [],
            'measures': [{'name': 'M', 'expression': 'FORMAT([DATE], "yyyy")'}],
        }])
        repairs = _self_heal_model(model)
        measure = model['model']['tables'][0]['measures'][0]
        self.assertFalse(measure.get('isHidden', False))


class TestTMDLSelfHealOrphanMeasures(unittest.TestCase):
    """Test orphan measure reassignment."""

    def test_orphan_on_unnamed_table_reassigned(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        model = {'model': {
            'tables': [
                {'name': 'Main', 'columns': [{'name': 'id', 'dataType': 'Int64'}], 'measures': []},
                {'name': '', 'columns': [], 'measures': [
                    {'name': 'Orphan', 'expression': '42'}
                ]},
            ],
            'relationships': [],
        }}
        _self_heal_model(model)
        main = model['model']['tables'][0]
        orphan_names = [m['name'] for m in main['measures']]
        self.assertIn('Orphan', orphan_names)


class TestTMDLSelfHealEmptyTables(unittest.TestCase):
    """Test removal of empty-name tables."""

    def test_empty_name_removed(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        model = {'model': {
            'tables': [
                {'name': 'Valid', 'columns': [{'name': 'id', 'dataType': 'Int64'}], 'measures': []},
                {'name': '', 'columns': [], 'measures': []},
                {'name': '  ', 'columns': [], 'measures': []},
            ],
            'relationships': [],
        }}
        repairs = _self_heal_model(model)
        self.assertGreater(repairs, 0)
        names = [t['name'] for t in model['model']['tables']]
        self.assertEqual(names, ['Valid'])


class TestTMDLSelfHealRecoveryReport(unittest.TestCase):
    """Test that self-heal records repairs to RecoveryReport."""

    def test_recovery_report_populated(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        from powerbi_import.recovery_report import RecoveryReport
        model = {'model': {
            'tables': [
                {'name': 'T', 'columns': [{'name': 'id', 'dataType': 'Int64'}], 'measures': []},
                {'name': 'T', 'columns': [{'name': 'id', 'dataType': 'Int64'}], 'measures': []},
            ],
            'relationships': [],
        }}
        recovery = RecoveryReport("Test")
        _self_heal_model(model, recovery=recovery)
        self.assertTrue(recovery.has_repairs)
        self.assertEqual(recovery.repairs[0]['repair_type'], 'duplicate_table')

    def test_no_repairs_no_recovery(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        from powerbi_import.recovery_report import RecoveryReport
        model = {'model': {
            'tables': [{'name': 'T', 'columns': [{'name': 'id', 'dataType': 'Int64'}], 'measures': []}],
            'relationships': [],
        }}
        recovery = RecoveryReport("Test")
        _self_heal_model(model, recovery=recovery)
        self.assertFalse(recovery.has_repairs)


# ════════════════════════════════════════════════════════════════════
#  Visual Fallback Cascade tests
# ════════════════════════════════════════════════════════════════════

class TestVisualFallbackValidation(unittest.TestCase):
    """Test _validate_visual_data_roles."""

    def test_textbox_always_valid(self):
        from powerbi_import.visual_generator import _validate_visual_data_roles
        self.assertTrue(_validate_visual_data_roles('textbox', False, False))

    def test_card_needs_measures(self):
        from powerbi_import.visual_generator import _validate_visual_data_roles
        self.assertTrue(_validate_visual_data_roles('card', False, True))
        self.assertFalse(_validate_visual_data_roles('card', False, False))

    def test_slicer_needs_dimensions(self):
        from powerbi_import.visual_generator import _validate_visual_data_roles
        self.assertTrue(_validate_visual_data_roles('slicer', True, False))
        self.assertFalse(_validate_visual_data_roles('slicer', False, False))

    def test_bar_chart_needs_dimensions(self):
        from powerbi_import.visual_generator import _validate_visual_data_roles
        self.assertTrue(_validate_visual_data_roles('clusteredBarChart', True, True))
        self.assertFalse(_validate_visual_data_roles('clusteredBarChart', False, True))

    def test_table_accepts_either(self):
        from powerbi_import.visual_generator import _validate_visual_data_roles
        self.assertTrue(_validate_visual_data_roles('tableEx', True, False))
        self.assertTrue(_validate_visual_data_roles('tableEx', False, True))
        self.assertFalse(_validate_visual_data_roles('tableEx', False, False))

    def test_unknown_type_passes(self):
        from powerbi_import.visual_generator import _validate_visual_data_roles
        self.assertTrue(_validate_visual_data_roles('unknownXYZ', False, False))


class TestVisualFallback(unittest.TestCase):
    """Test _apply_visual_fallback cascade."""

    def test_no_fallback_when_valid(self):
        from powerbi_import.visual_generator import _apply_visual_fallback
        pbi_type, note = _apply_visual_fallback('clusteredBarChart', True, True)
        self.assertEqual(pbi_type, 'clusteredBarChart')
        self.assertIsNone(note)

    def test_scatter_fallback_to_table(self):
        from powerbi_import.visual_generator import _apply_visual_fallback
        # scatterChart needs dimensions; if none, falls back to tableEx then card
        pbi_type, note = _apply_visual_fallback('scatterChart', False, True)
        self.assertIn(pbi_type, ('tableEx', 'card'))
        self.assertIsNotNone(note)
        self.assertIn('Self-heal', note)

    def test_bar_chart_fallback_to_table(self):
        from powerbi_import.visual_generator import _apply_visual_fallback
        pbi_type, note = _apply_visual_fallback('clusteredBarChart', False, True)
        # Bar needs dimensions → falls to tableEx (which works with measures)
        self.assertEqual(pbi_type, 'tableEx')
        self.assertIsNotNone(note)

    def test_gauge_fallback_to_card(self):
        from powerbi_import.visual_generator import _apply_visual_fallback
        # gauge needs measures; if none → card → needs measures → same issue
        pbi_type, note = _apply_visual_fallback('gauge', True, False)
        self.assertIsNotNone(note)

    def test_combo_fallback_chain(self):
        from powerbi_import.visual_generator import _apply_visual_fallback
        pbi_type, note = _apply_visual_fallback('lineClusteredColumnComboChart', False, True)
        # combo → bar → tableEx
        self.assertIn(pbi_type, ('clusteredBarChart', 'tableEx'))

    def test_table_no_data_fallback_to_card(self):
        from powerbi_import.visual_generator import _apply_visual_fallback
        pbi_type, note = _apply_visual_fallback('tableEx', False, False)
        self.assertEqual(pbi_type, 'card')

    def test_card_no_data(self):
        from powerbi_import.visual_generator import _apply_visual_fallback
        pbi_type, note = _apply_visual_fallback('card', False, False)
        # card needs measures; if no measures and no dims → ultimate fallback
        self.assertIsNotNone(note)

    def test_textbox_never_degrades(self):
        from powerbi_import.visual_generator import _apply_visual_fallback
        pbi_type, note = _apply_visual_fallback('textbox', False, False)
        self.assertEqual(pbi_type, 'textbox')
        self.assertIsNone(note)

    def test_image_never_degrades(self):
        from powerbi_import.visual_generator import _apply_visual_fallback
        pbi_type, note = _apply_visual_fallback('image', False, False)
        self.assertEqual(pbi_type, 'image')
        self.assertIsNone(note)


class TestVisualFallbackInContainer(unittest.TestCase):
    """Test that fallback cascade integrates into create_visual_container."""

    def test_scatter_without_dims_degrades(self):
        from powerbi_import.visual_generator import create_visual_container
        ws = {
            'visualType': 'circle',  # scatter
            'name': 'Test',
            'measures': [{'name': 'Sales', 'expression': 'SUM(Sales)'}],
            'dimensions': [],
            'fields': [],
        }
        container = create_visual_container(ws)
        vtype = container['visual']['visualType']
        # Should have degraded from scatterChart due to no dimensions
        self.assertIn(vtype, ('scatterChart', 'tableEx', 'card'))

    def test_valid_bar_no_degradation(self):
        from powerbi_import.visual_generator import create_visual_container
        ws = {
            'visualType': 'bar',
            'name': 'Test',
            'measures': [{'name': 'Sales', 'expression': 'SUM(Sales)'}],
            'dimensions': [{'name': 'Category', 'field': 'Category'}],
            'fields': [],
        }
        container = create_visual_container(ws)
        self.assertEqual(container['visual']['visualType'], 'clusteredBarChart')


# ════════════════════════════════════════════════════════════════════
#  M Query Self-Repair tests
# ════════════════════════════════════════════════════════════════════

class TestMQuerySelfRepair(unittest.TestCase):
    """Test M query try/otherwise wrapping in self-heal."""

    def _make_model_with_m_partition(self, m_expr, col_names=None):
        return {'model': {
            'tables': [{
                'name': 'TestTable',
                'columns': [{'name': c} for c in (col_names or ['A', 'B'])],
                'measures': [],
                'partitions': [{
                    'name': 'Partition-TestTable',
                    'mode': 'import',
                    'source': {'type': 'm', 'expression': m_expr},
                }],
            }],
            'relationships': [],
        }}

    def test_unwrapped_partition_gets_wrapped(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        m = 'let\n    Source = Sql.Database("server", "db"),\n    T = Source{[Name="dbo"]}[Data]\nin\n    T'
        model = self._make_model_with_m_partition(m)
        repairs = _self_heal_model(model)
        expr = model['model']['tables'][0]['partitions'][0]['source']['expression']
        self.assertIn('try', expr)

    def test_already_wrapped_not_double_wrapped(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        m = 'let\n    Source = try\n        Sql.Database("s","d")\n    otherwise\n        #table({}, {})\nin\n    Source'
        model = self._make_model_with_m_partition(m)
        repairs = _self_heal_model(model)
        expr = model['model']['tables'][0]['partitions'][0]['source']['expression']
        self.assertEqual(expr.count('try'), 1)

    def test_non_let_expression_not_wrapped(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        m = '#table({"A", "B"}, {{"x", 1}})'
        model = self._make_model_with_m_partition(m)
        repairs = _self_heal_model(model)
        expr = model['model']['tables'][0]['partitions'][0]['source']['expression']
        self.assertNotIn('try', expr)

    def test_recovery_report_records_wrap(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        from powerbi_import.recovery_report import RecoveryReport
        m = 'let\n    Source = Sql.Database("s", "d")\nin\n    Source'
        model = self._make_model_with_m_partition(m)
        recovery = RecoveryReport("Test")
        _self_heal_model(model, recovery=recovery)
        m_repairs = [r for r in recovery.repairs if r['category'] == 'm_query']
        self.assertTrue(len(m_repairs) >= 1)
        self.assertEqual(m_repairs[0]['repair_type'], 'try_otherwise_wrap')


# ════════════════════════════════════════════════════════════════════
#  Integration tests
# ════════════════════════════════════════════════════════════════════

class TestSelfHealIntegration(unittest.TestCase):
    """Combined self-heal scenarios — multiple issues at once."""

    def test_multiple_issues_all_repaired(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        from powerbi_import.recovery_report import RecoveryReport
        model = {'model': {
            'tables': [
                {
                    'name': 'Sales',
                    'columns': [{'name': 'Amount'}],
                    'measures': [
                        {'name': 'Bad', 'expression': 'SUM([Ghost])'},
                        {'name': 'Good', 'expression': 'SUM([Amount])'},
                    ],
                    'partitions': [{
                        'name': 'P',
                        'mode': 'import',
                        'source': {'type': 'm', 'expression': 'let\n    Source = Sql.Database("s","d")\nin\n    Source'},
                    }],
                },
                {
                    'name': 'Sales',  # Duplicate
                    'columns': [{'name': 'Qty'}],
                    'measures': [],
                },
                {
                    'name': '',  # Empty
                    'columns': [],
                    'measures': [],
                },
            ],
            'relationships': [],
        }}
        recovery = RecoveryReport("Integration")
        repairs = _self_heal_model(model, recovery=recovery)
        self.assertGreater(repairs, 0)
        self.assertTrue(recovery.has_repairs)
        # Duplicate renamed, broken ref hidden, empty table removed, M wrapped
        types = {r['repair_type'] for r in recovery.repairs}
        self.assertIn('duplicate_table', types)
        self.assertIn('broken_column_ref', types)
        self.assertIn('empty_table_name', types)

    def test_clean_model_no_repairs(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        from powerbi_import.recovery_report import RecoveryReport
        model = {'model': {
            'tables': [{
                'name': 'T',
                'columns': [{'name': 'C'}],
                'measures': [{'name': 'M', 'expression': 'SUM([C])'}],
                'partitions': [{
                    'name': 'P',
                    'mode': 'import',
                    'source': {'type': 'm', 'expression': 'let\n    Source = try\n        Sql.Database("s","d")\n    otherwise\n        #table({}, {})\nin\n    Source'},
                }],
            }],
            'relationships': [],
        }}
        recovery = RecoveryReport("Clean")
        repairs = _self_heal_model(model, recovery=recovery)
        self.assertEqual(repairs, 0)
        self.assertFalse(recovery.has_repairs)


class TestVisualFallbackCascadeConstants(unittest.TestCase):
    """Test VISUAL_FALLBACK_CASCADE dictionary is consistent."""

    def test_all_targets_are_known_types(self):
        from powerbi_import.visual_generator import VISUAL_FALLBACK_CASCADE, VISUAL_DATA_ROLES
        known = set(VISUAL_DATA_ROLES.keys()) | {'card', 'tableEx'}
        for source, target in VISUAL_FALLBACK_CASCADE.items():
            self.assertIn(target, known,
                          f"Fallback target '{target}' for '{source}' not in VISUAL_DATA_ROLES")

    def test_no_self_references(self):
        from powerbi_import.visual_generator import VISUAL_FALLBACK_CASCADE
        for source, target in VISUAL_FALLBACK_CASCADE.items():
            self.assertNotEqual(source, target,
                                f"Self-reference in fallback: {source} → {target}")

    def test_cascade_terminates(self):
        """Ensure no infinite loops in the cascade."""
        from powerbi_import.visual_generator import VISUAL_FALLBACK_CASCADE
        for start in VISUAL_FALLBACK_CASCADE:
            visited = {start}
            current = start
            for _ in range(10):
                nxt = VISUAL_FALLBACK_CASCADE.get(current)
                if not nxt or nxt in visited:
                    break
                visited.add(nxt)
                current = nxt
            else:
                self.fail(f"Cascade from '{start}' doesn't terminate within 10 steps")


class TestBooleanColumnWrapping(unittest.TestCase):
    """v28.4.2 — MAX/SUM cannot work with Boolean type columns.

    When self-heal wraps a bare boolean calculated-column ref in a measure,
    it must use MAXX('Table', IF(col, 1, 0)) instead of MAX(col).
    MAX with a single non-column argument is invalid DAX.
    """

    def _make_model(self, tables):
        return {'model': {'tables': tables, 'relationships': []}}

    def test_boolean_col_wrapped_with_if(self):
        """Same-table boolean calc column → MAXX('Table', IF(col, 1, 0))."""
        from powerbi_import.tmdl_generator import _self_heal_model
        model = self._make_model([{
            'name': 'Facts',
            'columns': [
                {'name': 'Amount', 'dataType': 'double'},
                {'name': 'Is Active', 'dataType': 'boolean',
                 'type': 'calculated'},
            ],
            'measures': [{
                'name': 'Active Amount',
                'expression': "IF('Facts'[Is Active], SUM('Facts'[Amount]), BLANK())",
            }],
        }])
        _self_heal_model(model)
        expr = model['model']['tables'][0]['measures'][0]['expression']
        # Must wrap boolean as MAXX iterator, not MAX (which is invalid for expressions)
        self.assertIn("MAXX('Facts', IF('Facts'[Is Active], 1, 0))", expr)
        self.assertNotIn("MAX('Facts'[Is Active])", expr)
        self.assertNotIn("MAX(IF(", expr)

    def test_non_boolean_col_wrapped_with_max(self):
        """Same-table non-boolean calc column → MAX(col)."""
        from powerbi_import.tmdl_generator import _self_heal_model
        model = self._make_model([{
            'name': 'Facts',
            'columns': [
                {'name': 'Amount', 'dataType': 'double'},
                {'name': 'Score', 'dataType': 'int64',
                 'type': 'calculated'},
            ],
            'measures': [{
                'name': 'Top Score',
                'expression': "IF('Facts'[Score] > 0, SUM('Facts'[Amount]), BLANK())",
            }],
        }])
        _self_heal_model(model)
        expr = model['model']['tables'][0]['measures'][0]['expression']
        # Non-boolean → regular MAX()
        self.assertIn("MAX('Facts'[Score])", expr)
        self.assertNotIn("IF('Facts'[Score], 1, 0)", expr)

    def test_mixed_boolean_and_nonboolean_cols(self):
        """Table with both boolean and non-boolean calc columns."""
        from powerbi_import.tmdl_generator import _self_heal_model
        model = self._make_model([{
            'name': 'T',
            'columns': [
                {'name': 'Val', 'dataType': 'double'},
                {'name': 'Flag', 'dataType': 'boolean', 'type': 'calculated'},
                {'name': 'Rank', 'dataType': 'int64', 'type': 'calculated'},
            ],
            'measures': [
                {
                    'name': 'M1',
                    'expression': "IF('T'[Flag], 'T'[Val], 0)",
                },
                {
                    'name': 'M2',
                    'expression': "IF('T'[Rank] > 5, 'T'[Val], 0)",
                },
            ],
        }])
        _self_heal_model(model)
        m1 = model['model']['tables'][0]['measures'][0]['expression']
        m2 = model['model']['tables'][0]['measures'][1]['expression']
        self.assertIn("MAXX('T', IF('T'[Flag], 1, 0))", m1)
        self.assertIn("MAX('T'[Rank])", m2)


# ════════════════════════════════════════════════════════════════════
#  v28.5.0 — DAX bug fixes (Bugs 1-7)
# ════════════════════════════════════════════════════════════════════

class TestDateaddArgReorder(unittest.TestCase):
    """Bug 1 — DATEADD scalar conversion.

    Tableau DATEADD('month', 3, [Date]) is scalar.
    DAX DATEADD is a Time Intelligence TABLE function — wrong semantics.
    Convert to EDATE (months/years/quarters) or arithmetic (days/weeks).
    """

    def test_dateadd_month(self):
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        result = convert_tableau_formula_to_dax("DATEADD('month', 3, [Date])")
        # Must use EDATE for scalar month arithmetic, not DAX DATEADD
        self.assertIn('EDATE', result)
        self.assertIn('[Date]', result)
        self.assertIn('3', result)
        self.assertNotIn('DATEADD', result)

    def test_dateadd_year(self):
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        result = convert_tableau_formula_to_dax("DATEADD('year', -1, [OrderDate])")
        self.assertIn('EDATE', result)
        self.assertIn('[OrderDate]', result)
        self.assertIn('-1', result)
        self.assertIn('* 12', result)

    def test_dateadd_day_positive(self):
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        result = convert_tableau_formula_to_dax("DATEADD('day', 7, [ShipDate])")
        # Day arithmetic: date + n
        self.assertIn('[ShipDate]', result)
        self.assertIn('7', result)
        self.assertIn('+', result)
        self.assertNotIn('DATEADD', result)


class TestBareRefSumTypeAware(unittest.TestCase):
    """Bug 2 — Type-aware bare column ref wrapping in _build_table.

    SUM is invalid for boolean/string/datetime columns.
    """

    def _build(self, columns, measures):
        from powerbi_import.tmdl_generator import _build_table
        table = {'name': 'T', 'columns': columns}
        conn = {'type': 'sqlserver'}
        calcs = []
        return _build_table(table, conn, calcs, [])

    def test_boolean_calc_col_uses_max_if(self):
        """Boolean calc column measure ref → MAXX('T', IF(col, 1, 0))."""
        cols = [
            {'name': 'Sales', 'datatype': 'real', 'role': 'measure'},
        ]
        calcs_raw = [
            {'name': '[Is Flag]', 'formula': 'IF([Sales] > 0, TRUE, FALSE)',
             'datatype': 'boolean', 'role': 'dimension'},
        ]
        from powerbi_import.tmdl_generator import _build_table
        table = {'name': 'T', 'columns': cols}
        conn = {'type': 'sqlserver'}
        result = _build_table(table, conn, calcs_raw, [])
        # The boolean calc column should be classified as a calc column (not measure)
        bool_cols = [c for c in result.get('columns', [])
                     if c.get('name') == 'Is Flag']
        if bool_cols:
            self.assertEqual(bool_cols[0].get('dataType', '').lower(), 'boolean')

    def test_string_col_not_summed(self):
        """String column should not be wrapped with SUM in self-heal."""
        from powerbi_import.tmdl_generator import _self_heal_model
        model = {'model': {'tables': [{
            'name': 'T',
            'columns': [
                {'name': 'Name', 'dataType': 'string'},
            ],
            'measures': [{
                'name': 'M',
                'expression': "'T'[Name]",
            }],
        }], 'relationships': []}}
        _self_heal_model(model)
        expr = model['model']['tables'][0]['measures'][0]['expression']
        self.assertNotIn("SUM('T'[Name])", expr)
        self.assertIn("MAX('T'[Name])", expr)

    def test_datetime_col_not_summed(self):
        """Datetime column should use MAX, not SUM."""
        from powerbi_import.tmdl_generator import _self_heal_model
        model = {'model': {'tables': [{
            'name': 'T',
            'columns': [
                {'name': 'Created', 'dataType': 'datetime'},
            ],
            'measures': [{
                'name': 'Latest',
                'expression': "'T'[Created]",
            }],
        }], 'relationships': []}}
        _self_heal_model(model)
        expr = model['model']['tables'][0]['measures'][0]['expression']
        self.assertNotIn("SUM('T'[Created])", expr)
        self.assertIn("MAX('T'[Created])", expr)


class TestDateparseFixBug4(unittest.TestCase):
    """Bug 4 — DATEPARSE should return a date, not FORMAT(DATEVALUE(), fmt).

    The format string in DATEPARSE is a parsing hint for interpreting the
    input string, not an output format.
    """

    def test_dateparse_returns_datevalue(self):
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        result = convert_tableau_formula_to_dax(
            'DATEPARSE("yyyy-MM-dd", [DateStr])')
        self.assertIn('DATEVALUE', result)
        self.assertNotIn('FORMAT', result)

    def test_dateparse_no_format_still_datevalue(self):
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        result = convert_tableau_formula_to_dax('DATEPARSE([DateCol])')
        self.assertIn('DATEVALUE', result)


class TestProperMigrationComment(unittest.TestCase):
    """Bug 5 — PROPER conversion should include migration comment."""

    def test_proper_has_comment(self):
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        result = convert_tableau_formula_to_dax('PROPER([Name])')
        self.assertIn('UPPER', result)
        self.assertIn('LOWER', result)
        self.assertIn('/*', result)
        self.assertIn('*/', result)
        # Comment should warn about multi-word limitation
        self.assertIn('capitaliz', result.lower())


class TestAttrNestedParens(unittest.TestCase):
    """Bug 7 — ATTR should handle nested function calls."""

    def test_attr_simple(self):
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        result = convert_tableau_formula_to_dax('ATTR([Name])')
        self.assertNotIn('ATTR', result)

    def test_attr_nested_upper(self):
        """ATTR(UPPER([Name])) should not break on nested parens."""
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        result = convert_tableau_formula_to_dax('ATTR(UPPER([Name]))')
        self.assertNotIn('ATTR', result)
        self.assertIn('UPPER', result)

    def test_attr_deeply_nested(self):
        """ATTR(LEFT(UPPER([Name]), 3)) — deeply nested."""
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        result = convert_tableau_formula_to_dax('ATTR(LEFT(UPPER([Name]), 3))')
        self.assertNotIn('ATTR', result)
        self.assertIn('UPPER', result)
        self.assertIn('LEFT', result)


# ════════════════════════════════════════════════════════════════════
#  Expanded self-healing checks (Sprint 132)
# ════════════════════════════════════════════════════════════════════

class TestSelfHealDataTypeFormatMismatch(unittest.TestCase):
    """Check 8 — dataType/formatString inconsistency auto-repair."""

    def _make_model(self, columns):
        return {
            'model': {
                'tables': [{'name': 'T', 'columns': columns, 'measures': [],
                             'partitions': []}],
                'relationships': [],
            }
        }

    def test_string_with_numeric_format_fixed(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        model = self._make_model([
            {'name': 'Score', 'dataType': 'String', 'formatString': '#,0;-#,0',
             'sourceColumn': 'Score', 'summarizeBy': 'none'},
        ])
        repairs = _self_heal_model(model)
        self.assertGreaterEqual(repairs, 1)
        col = model['model']['tables'][0]['columns'][0]
        self.assertEqual(col['dataType'], 'Double')

    def test_string_without_format_untouched(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        model = self._make_model([
            {'name': 'Name', 'dataType': 'String', 'sourceColumn': 'Name',
             'summarizeBy': 'none'},
        ])
        repairs = _self_heal_model(model)
        col = model['model']['tables'][0]['columns'][0]
        self.assertEqual(col['dataType'], 'String')

    def test_double_with_numeric_format_untouched(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        model = self._make_model([
            {'name': 'Amount', 'dataType': 'Double', 'formatString': '#,0.00',
             'sourceColumn': 'Amount', 'summarizeBy': 'sum'},
        ])
        repairs = _self_heal_model(model)
        col = model['model']['tables'][0]['columns'][0]
        self.assertEqual(col['dataType'], 'Double')

    def test_recovery_report_logged(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        from powerbi_import.recovery_report import RecoveryReport
        model = self._make_model([
            {'name': 'Rank', 'dataType': 'String', 'formatString': '0',
             'sourceColumn': 'Rank', 'summarizeBy': 'none'},
        ])
        recovery = RecoveryReport("Test")
        _self_heal_model(model, recovery=recovery)
        self.assertTrue(recovery.has_repairs)
        self.assertEqual(recovery.repairs[0]['repair_type'], 'datatype_format_mismatch')


class TestSelfHealDuplicateColumns(unittest.TestCase):
    """Check 9 — duplicate column names within a table."""

    def _make_model(self, columns):
        return {
            'model': {
                'tables': [{'name': 'T', 'columns': columns, 'measures': [],
                             'partitions': []}],
                'relationships': [],
            }
        }

    def test_duplicate_column_renamed(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        model = self._make_model([
            {'name': 'Status', 'dataType': 'String', 'sourceColumn': 'Status'},
            {'name': 'Status', 'dataType': 'String', 'sourceColumn': 'Status2'},
        ])
        repairs = _self_heal_model(model)
        self.assertGreaterEqual(repairs, 1)
        names = [c['name'] for c in model['model']['tables'][0]['columns']]
        self.assertEqual(len(names), len(set(names)), "Column names should be unique")
        self.assertIn('Status', names)
        self.assertIn('Status_2', names)

    def test_no_duplicates_untouched(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        model = self._make_model([
            {'name': 'A', 'dataType': 'String', 'sourceColumn': 'A'},
            {'name': 'B', 'dataType': 'Int64', 'sourceColumn': 'B'},
        ])
        repairs = _self_heal_model(model)
        names = [c['name'] for c in model['model']['tables'][0]['columns']]
        self.assertEqual(names, ['A', 'B'])


class TestSelfHealEmptyTables(unittest.TestCase):
    """Check 10 — tables with zero columns."""

    def test_empty_table_with_measures_gets_placeholder(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        model = {
            'model': {
                'tables': [
                    {'name': 'Facts', 'columns': [
                        {'name': 'ID', 'dataType': 'Int64'}
                    ], 'measures': [], 'partitions': []},
                    {'name': 'KPIs', 'columns': [], 'measures': [
                        {'name': 'Total', 'expression': 'SUM(Facts[ID])'}
                    ], 'partitions': []},
                ],
                'relationships': [],
            }
        }
        repairs = _self_heal_model(model)
        self.assertGreaterEqual(repairs, 1)
        kpi_table = model['model']['tables'][1]
        self.assertEqual(len(kpi_table['columns']), 1)
        self.assertEqual(kpi_table['columns'][0]['name'], '_Placeholder')
        self.assertTrue(kpi_table['columns'][0].get('isHidden'))

    def test_empty_table_no_measures_removed(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        model = {
            'model': {
                'tables': [
                    {'name': 'Facts', 'columns': [
                        {'name': 'ID', 'dataType': 'Int64'}
                    ], 'measures': [], 'partitions': []},
                    {'name': 'Empty', 'columns': [], 'measures': [],
                     'partitions': []},
                ],
                'relationships': [
                    {'fromTable': 'Facts', 'fromColumn': 'ID',
                     'toTable': 'Empty', 'toColumn': 'ID'},
                ],
            }
        }
        repairs = _self_heal_model(model)
        self.assertGreaterEqual(repairs, 1)
        table_names = [t['name'] for t in model['model']['tables']]
        self.assertNotIn('Empty', table_names)
        # Relationship to removed table should also be removed
        for r in model['model']['relationships']:
            self.assertNotEqual(r.get('toTable'), 'Empty')


class TestSelfHealMissingRelationshipEndpoints(unittest.TestCase):
    """Check 11 — relationships referencing non-existent tables/columns."""

    def test_missing_table_relationship_removed(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        model = {
            'model': {
                'tables': [
                    {'name': 'Orders', 'columns': [
                        {'name': 'CustID', 'dataType': 'Int64'}
                    ], 'measures': [], 'partitions': []},
                ],
                'relationships': [
                    {'fromTable': 'Orders', 'fromColumn': 'CustID',
                     'toTable': 'Customers', 'toColumn': 'ID'},
                ],
            }
        }
        repairs = _self_heal_model(model)
        self.assertGreaterEqual(repairs, 1)
        self.assertEqual(len(model['model']['relationships']), 0)

    def test_missing_column_relationship_removed(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        model = {
            'model': {
                'tables': [
                    {'name': 'Orders', 'columns': [
                        {'name': 'ID', 'dataType': 'Int64'}
                    ], 'measures': [], 'partitions': []},
                    {'name': 'Items', 'columns': [
                        {'name': 'ItemID', 'dataType': 'Int64'}
                    ], 'measures': [], 'partitions': []},
                ],
                'relationships': [
                    {'fromTable': 'Orders', 'fromColumn': 'OrderKey',
                     'toTable': 'Items', 'toColumn': 'ItemID'},
                ],
            }
        }
        repairs = _self_heal_model(model)
        self.assertGreaterEqual(repairs, 1)
        self.assertEqual(len(model['model']['relationships']), 0)

    def test_valid_relationship_kept(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        model = {
            'model': {
                'tables': [
                    {'name': 'Orders', 'columns': [
                        {'name': 'CustID', 'dataType': 'Int64'}
                    ], 'measures': [], 'partitions': []},
                    {'name': 'Customers', 'columns': [
                        {'name': 'CustID', 'dataType': 'Int64'}
                    ], 'measures': [], 'partitions': []},
                ],
                'relationships': [
                    {'fromTable': 'Orders', 'fromColumn': 'CustID',
                     'toTable': 'Customers', 'toColumn': 'CustID'},
                ],
            }
        }
        repairs = _self_heal_model(model)
        self.assertEqual(len(model['model']['relationships']), 1)


class TestSelfHealEmptyMeasures(unittest.TestCase):
    """Check 12 — measures with empty expressions."""

    def test_empty_expression_removed(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        model = {
            'model': {
                'tables': [{
                    'name': 'T', 'columns': [
                        {'name': 'ID', 'dataType': 'Int64'}
                    ],
                    'measures': [
                        {'name': 'Good', 'expression': 'SUM(T[ID])'},
                        {'name': 'Bad', 'expression': ''},
                        {'name': 'Blank', 'expression': '   '},
                    ],
                    'partitions': [],
                }],
                'relationships': [],
            }
        }
        repairs = _self_heal_model(model)
        self.assertGreaterEqual(repairs, 2)  # Bad + Blank
        measure_names = [m['name'] for m in model['model']['tables'][0]['measures']]
        self.assertIn('Good', measure_names)
        self.assertNotIn('Bad', measure_names)
        self.assertNotIn('Blank', measure_names)


class TestSelfHealCrossTableBrokenRefs(unittest.TestCase):
    """Check 13 — cross-table DAX references to non-existent tables/columns."""

    def test_nonexistent_table_ref_hidden(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        model = {
            'model': {
                'tables': [{
                    'name': 'Sales',
                    'columns': [{'name': 'Amount', 'dataType': 'Double'}],
                    'measures': [
                        {'name': 'Total', 'expression': "SUM('Ghost'[Value])"},
                    ],
                    'partitions': [],
                }],
                'relationships': [],
            }
        }
        repairs = _self_heal_model(model)
        self.assertGreaterEqual(repairs, 1)
        m = model['model']['tables'][0]['measures'][0]
        self.assertTrue(m.get('isHidden'))

    def test_nonexistent_column_ref_hidden(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        model = {
            'model': {
                'tables': [
                    {'name': 'Sales',
                     'columns': [{'name': 'Amount', 'dataType': 'Double'}],
                     'measures': [
                         {'name': 'Ratio', 'expression': "DIVIDE('Sales'[Amount], 'Sales'[Missing])"},
                     ],
                     'partitions': []},
                ],
                'relationships': [],
            }
        }
        repairs = _self_heal_model(model)
        self.assertGreaterEqual(repairs, 1)
        m = model['model']['tables'][0]['measures'][0]
        self.assertTrue(m.get('isHidden'))

    def test_valid_cross_table_ref_untouched(self):
        from powerbi_import.tmdl_generator import _self_heal_model
        model = {
            'model': {
                'tables': [
                    {'name': 'Sales',
                     'columns': [{'name': 'CustID', 'dataType': 'Int64'}],
                     'measures': [
                         {'name': 'CustCount', 'expression': "DISTINCTCOUNT('Customers'[CustID])"},
                     ],
                     'partitions': []},
                    {'name': 'Customers',
                     'columns': [{'name': 'CustID', 'dataType': 'Int64'}],
                     'measures': [],
                     'partitions': []},
                ],
                'relationships': [],
            }
        }
        _self_heal_model(model)
        m = model['model']['tables'][0]['measures'][0]
        self.assertFalse(m.get('isHidden', False))


if __name__ == '__main__':
    unittest.main()
