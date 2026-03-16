"""
Tests for the Shared Semantic Model extension.

Covers:
- TableFingerprint creation and matching
- Column overlap scoring
- Merge candidate detection
- Measure conflict detection and resolution
- Relationship deduplication
- Parameter merging
- Table column merging
- Merge score calculation
- Full merge_semantic_models() flow
- Merge assessment reporting
- Thin report generation
- Field remapping
- CLI argument wiring
"""

import copy
import json
import os
import tempfile
import shutil
import unittest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))

from powerbi_import.shared_model import (
    TableFingerprint,
    MergeCandidate,
    MeasureConflict,
    MergeAssessment,
    build_table_fingerprints,
    compute_column_overlap,
    assess_merge,
    merge_semantic_models,
    calculate_merge_score,
    build_field_mapping,
    _parse_table_name,
    _type_width,
    _merge_columns_into,
    _merge_calculations,
    _merge_parameters,
    _merge_list_by_name,
    _relationship_key,
    _detect_measure_conflicts,
    _count_relationship_duplicates,
    _detect_parameter_conflicts,
    _detect_column_conflicts,
)
from powerbi_import.merge_assessment import (
    generate_merge_report,
    print_merge_summary,
)


# ═══════════════════════════════════════════════════════════════════
#  Test helpers — factory functions
# ═══════════════════════════════════════════════════════════════════

def _make_ds(name='DS1', conn_type='SQL Server', server='srv', database='db',
             tables=None, calculations=None, relationships=None):
    """Create a minimal datasource dict."""
    return {
        'name': name,
        'caption': name,
        'connection': {
            'type': conn_type,
            'details': {'server': server, 'database': database},
        },
        'connection_map': {},
        'tables': tables or [],
        'columns': [],
        'calculations': calculations or [],
        'relationships': relationships or [],
    }


def _make_table(name, columns=None):
    """Create a minimal table dict with columns."""
    cols = []
    for c in (columns or []):
        if isinstance(c, str):
            parts = c.split(':')
            cols.append({'name': parts[0], 'datatype': parts[1] if len(parts) > 1 else 'string'})
        else:
            cols.append(c)
    return {'name': name, 'type': 'table', 'columns': cols}


def _make_calc(caption, formula, role='measure', datatype='real', ds_name=''):
    """Create a minimal calculation dict."""
    return {
        'name': f'[Calc_{caption}]', 'caption': caption, 'formula': formula,
        'role': role, 'datatype': datatype, 'datasource_name': ds_name,
    }


def _make_extracted(datasources=None, calculations=None, parameters=None,
                    worksheets=None, dashboards=None, **kwargs):
    """Build a converted_objects dict."""
    data = {
        'datasources': datasources or [],
        'worksheets': worksheets or [],
        'dashboards': dashboards or [],
        'calculations': calculations or [],
        'parameters': parameters or [],
        'filters': [],
        'stories': [],
        'actions': [],
        'sets': [],
        'groups': [],
        'bins': [],
        'hierarchies': [],
        'sort_orders': [],
        'aliases': {},
        'custom_sql': [],
        'user_filters': [],
    }
    data.update(kwargs)
    return data


# ═══════════════════════════════════════════════════════════════════
#  TableFingerprint tests
# ═══════════════════════════════════════════════════════════════════

class TestTableFingerprint(unittest.TestCase):
    """Tests for TableFingerprint identity and matching."""

    def test_same_table_same_fingerprint(self):
        fp1 = TableFingerprint('SQL Server', 'myserver', 'SalesDB', 'dbo', 'Orders')
        fp2 = TableFingerprint('SQL Server', 'myserver', 'SalesDB', 'dbo', 'Orders')
        self.assertEqual(fp1.fingerprint(), fp2.fingerprint())
        self.assertEqual(fp1, fp2)
        self.assertEqual(hash(fp1), hash(fp2))

    def test_different_server_different_fingerprint(self):
        fp1 = TableFingerprint('SQL Server', 'server1', 'DB', 'dbo', 'Orders')
        fp2 = TableFingerprint('SQL Server', 'server2', 'DB', 'dbo', 'Orders')
        self.assertNotEqual(fp1.fingerprint(), fp2.fingerprint())
        self.assertNotEqual(fp1, fp2)

    def test_different_database_different_fingerprint(self):
        fp1 = TableFingerprint('SQL Server', 'srv', 'DB1', 'dbo', 'Orders')
        fp2 = TableFingerprint('SQL Server', 'srv', 'DB2', 'dbo', 'Orders')
        self.assertNotEqual(fp1.fingerprint(), fp2.fingerprint())

    def test_different_table_different_fingerprint(self):
        fp1 = TableFingerprint('SQL Server', 'srv', 'DB', 'dbo', 'Orders')
        fp2 = TableFingerprint('SQL Server', 'srv', 'DB', 'dbo', 'Customers')
        self.assertNotEqual(fp1.fingerprint(), fp2.fingerprint())

    def test_case_insensitive_matching(self):
        fp1 = TableFingerprint('SQL Server', 'MyServer', 'SalesDB', 'DBO', 'Orders')
        fp2 = TableFingerprint('sql server', 'myserver', 'salesdb', 'dbo', 'orders')
        self.assertEqual(fp1.fingerprint(), fp2.fingerprint())

    def test_schema_normalization(self):
        fp1 = TableFingerprint('SQL Server', 'srv', 'db', 'dbo', 'Orders')
        fp2 = TableFingerprint('SQL Server', 'srv', 'db', 'DBO', 'Orders')
        self.assertEqual(fp1, fp2)

    def test_whitespace_handled(self):
        fp1 = TableFingerprint('SQL Server', ' srv ', 'db', 'dbo', 'Orders')
        fp2 = TableFingerprint('SQL Server', 'srv', 'db', 'dbo', 'Orders')
        self.assertEqual(fp1.fingerprint(), fp2.fingerprint())

    def test_not_equal_to_non_fingerprint(self):
        fp = TableFingerprint('SQL Server', 'srv', 'db', 'dbo', 'Orders')
        self.assertEqual(fp.__eq__("not a fingerprint"), NotImplemented)


class TestParseTableName(unittest.TestCase):
    """Tests for _parse_table_name."""

    def test_schema_dot_table(self):
        schema, table = _parse_table_name('[dbo].[Orders]')
        self.assertEqual(schema, 'dbo')
        self.assertEqual(table, 'Orders')

    def test_bare_table_name(self):
        schema, table = _parse_table_name('Orders')
        self.assertEqual(schema, 'dbo')
        self.assertEqual(table, 'Orders')

    def test_no_brackets(self):
        schema, table = _parse_table_name('sales.Orders')
        self.assertEqual(schema, 'sales')
        self.assertEqual(table, 'Orders')

    def test_bracket_wrapped(self):
        schema, table = _parse_table_name('[Orders]')
        self.assertEqual(schema, 'dbo')
        self.assertEqual(table, 'Orders')


# ═══════════════════════════════════════════════════════════════════
#  Build table fingerprints
# ═══════════════════════════════════════════════════════════════════

class TestBuildTableFingerprints(unittest.TestCase):
    """Tests for build_table_fingerprints."""

    def test_single_datasource_tables(self):
        ds = _make_ds(tables=[
            _make_table('[dbo].[Orders]', ['ID:integer', 'Amount:real']),
            _make_table('Products', ['ProdID:integer']),
        ])
        fps = build_table_fingerprints([ds])
        self.assertEqual(len(fps), 2)
        self.assertIn('[dbo].[Orders]', fps)
        self.assertIn('Products', fps)

    def test_skips_non_table_type(self):
        ds = _make_ds(tables=[
            {'name': 'calc_table', 'type': 'calculated', 'columns': []},
            _make_table('Real', ['A:string']),
        ])
        fps = build_table_fingerprints([ds])
        self.assertEqual(len(fps), 1)
        self.assertIn('Real', fps)

    def test_empty_datasources(self):
        fps = build_table_fingerprints([])
        self.assertEqual(len(fps), 0)

    def test_multiple_datasources(self):
        ds1 = _make_ds(name='DS1', server='s1', tables=[_make_table('T1')])
        ds2 = _make_ds(name='DS2', server='s2', tables=[_make_table('T2')])
        fps = build_table_fingerprints([ds1, ds2])
        self.assertEqual(len(fps), 2)


# ═══════════════════════════════════════════════════════════════════
#  Column overlap
# ═══════════════════════════════════════════════════════════════════

class TestColumnOverlap(unittest.TestCase):
    """Tests for compute_column_overlap."""

    def test_identical_columns_returns_1(self):
        t1 = _make_table('T', ['A:int', 'B:string', 'C:real'])
        t2 = _make_table('T', ['A:int', 'B:string', 'C:real'])
        self.assertAlmostEqual(compute_column_overlap(t1, t2), 1.0)

    def test_disjoint_columns_returns_0(self):
        t1 = _make_table('T', ['A:int'])
        t2 = _make_table('T', ['X:int'])
        self.assertAlmostEqual(compute_column_overlap(t1, t2), 0.0)

    def test_partial_overlap_correct_ratio(self):
        t1 = _make_table('T', ['A', 'B', 'C'])
        t2 = _make_table('T', ['A', 'B', 'D'])
        # Intersection: A, B (2). Union: A, B, C, D (4). Jaccard = 0.5
        self.assertAlmostEqual(compute_column_overlap(t1, t2), 0.5)

    def test_empty_table_returns_0(self):
        t1 = _make_table('T', [])
        t2 = _make_table('T', ['A'])
        self.assertAlmostEqual(compute_column_overlap(t1, t2), 0.0)

    def test_both_empty_returns_0(self):
        t1 = _make_table('T', [])
        t2 = _make_table('T', [])
        self.assertAlmostEqual(compute_column_overlap(t1, t2), 0.0)

    def test_case_insensitive(self):
        t1 = _make_table('T', [{'name': 'OrderID', 'datatype': 'int'}])
        t2 = _make_table('T', [{'name': 'orderid', 'datatype': 'int'}])
        self.assertAlmostEqual(compute_column_overlap(t1, t2), 1.0)

    def test_superset(self):
        t1 = _make_table('T', ['A', 'B', 'C'])
        t2 = _make_table('T', ['A', 'B'])
        # Intersection: 2, Union: 3. Jaccard = 2/3
        self.assertAlmostEqual(compute_column_overlap(t1, t2), 2/3)


# ═══════════════════════════════════════════════════════════════════
#  Merge candidate detection
# ═══════════════════════════════════════════════════════════════════

class TestMergeCandidateDetection(unittest.TestCase):
    """Tests for assess_merge merge candidate identification."""

    def test_two_workbooks_shared_table(self):
        ds = _make_ds(tables=[_make_table('Orders', ['ID:integer', 'Amt:real'])])
        wb1 = _make_extracted(datasources=[ds])
        wb2 = _make_extracted(datasources=[copy.deepcopy(ds)])
        assessment = assess_merge([wb1, wb2], ['WB1', 'WB2'])
        self.assertEqual(len(assessment.merge_candidates), 1)
        self.assertEqual(assessment.merge_candidates[0].table_name, 'Orders')

    def test_no_overlap_returns_empty(self):
        ds1 = _make_ds(server='s1', tables=[_make_table('Orders')])
        ds2 = _make_ds(server='s2', tables=[_make_table('Customers')])
        wb1 = _make_extracted(datasources=[ds1])
        wb2 = _make_extracted(datasources=[ds2])
        assessment = assess_merge([wb1, wb2], ['WB1', 'WB2'])
        self.assertEqual(len(assessment.merge_candidates), 0)

    def test_multiple_shared_tables(self):
        ds = _make_ds(tables=[
            _make_table('Orders', ['ID']),
            _make_table('Customers', ['CustID']),
        ])
        wb1 = _make_extracted(datasources=[ds])
        wb2 = _make_extracted(datasources=[copy.deepcopy(ds)])
        assessment = assess_merge([wb1, wb2], ['WB1', 'WB2'])
        self.assertEqual(len(assessment.merge_candidates), 2)

    def test_different_connections_not_merged(self):
        ds1 = _make_ds(server='server1', tables=[_make_table('Orders', ['ID'])])
        ds2 = _make_ds(server='server2', tables=[_make_table('Orders', ['ID'])])
        wb1 = _make_extracted(datasources=[ds1])
        wb2 = _make_extracted(datasources=[ds2])
        assessment = assess_merge([wb1, wb2], ['WB1', 'WB2'])
        self.assertEqual(len(assessment.merge_candidates), 0)

    def test_three_workbooks_partial_overlap(self):
        ds_shared = _make_ds(tables=[_make_table('Orders', ['ID'])])
        ds_unique = _make_ds(server='other', tables=[_make_table('Forecast', ['F'])])
        wb1 = _make_extracted(datasources=[ds_shared])
        wb2 = _make_extracted(datasources=[copy.deepcopy(ds_shared)])
        wb3 = _make_extracted(datasources=[ds_unique])
        assessment = assess_merge([wb1, wb2, wb3], ['WB1', 'WB2', 'WB3'])
        self.assertEqual(len(assessment.merge_candidates), 1)
        self.assertIn('WB3', assessment.unique_tables)

    def test_assessment_to_dict(self):
        ds = _make_ds(tables=[_make_table('Orders', ['ID'])])
        wb1 = _make_extracted(datasources=[ds])
        wb2 = _make_extracted(datasources=[copy.deepcopy(ds)])
        assessment = assess_merge([wb1, wb2], ['WB1', 'WB2'])
        d = assessment.to_dict()
        self.assertIn('merge_candidates', d)
        self.assertIn('merge_score', d)
        self.assertIn('recommendation', d)


# ═══════════════════════════════════════════════════════════════════
#  Measure conflict detection
# ═══════════════════════════════════════════════════════════════════

class TestMeasureConflictDetection(unittest.TestCase):
    """Tests for measure conflict detection and resolution."""

    def test_identical_measures_deduplicated(self):
        ds1 = _make_ds(calculations=[_make_calc('Total', 'SUM([Amt])')])
        ds2 = _make_ds(calculations=[_make_calc('Total', 'SUM([Amt])')])
        wb1 = _make_extracted(datasources=[ds1])
        wb2 = _make_extracted(datasources=[ds2])
        conflicts, dupes = _detect_measure_conflicts([wb1, wb2], ['WB1', 'WB2'])
        self.assertEqual(dupes, 1)
        self.assertEqual(len(conflicts), 0)

    def test_conflicting_measures_detected(self):
        ds1 = _make_ds(calculations=[_make_calc('Total', 'SUM([Amt])')])
        ds2 = _make_ds(calculations=[_make_calc('Total', 'SUMX(T, [Qty]*[Price])')])
        wb1 = _make_extracted(datasources=[ds1])
        wb2 = _make_extracted(datasources=[ds2])
        conflicts, dupes = _detect_measure_conflicts([wb1, wb2], ['WB1', 'WB2'])
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].name, 'Total')
        self.assertEqual(dupes, 0)

    def test_unique_measures_no_conflict(self):
        ds1 = _make_ds(calculations=[_make_calc('Revenue', 'SUM([Rev])')])
        ds2 = _make_ds(calculations=[_make_calc('Profit', 'SUM([Prof])')])
        wb1 = _make_extracted(datasources=[ds1])
        wb2 = _make_extracted(datasources=[ds2])
        conflicts, dupes = _detect_measure_conflicts([wb1, wb2], ['WB1', 'WB2'])
        self.assertEqual(len(conflicts), 0)
        self.assertEqual(dupes, 0)


# ═══════════════════════════════════════════════════════════════════
#  Relationship deduplication
# ═══════════════════════════════════════════════════════════════════

class TestRelationshipDeduplication(unittest.TestCase):
    """Tests for relationship deduplication."""

    def test_duplicate_relationships_counted(self):
        rel = {'left': {'table': 'Orders', 'column': 'CustID'},
               'right': {'table': 'Customers', 'column': 'ID'}}
        ds1 = _make_ds(relationships=[rel])
        ds2 = _make_ds(relationships=[copy.deepcopy(rel)])
        wb1 = _make_extracted(datasources=[ds1])
        wb2 = _make_extracted(datasources=[ds2])
        dupes = _count_relationship_duplicates([wb1, wb2])
        self.assertEqual(dupes, 1)

    def test_unique_relationships_no_duplicates(self):
        rel1 = {'left': {'table': 'A', 'column': 'X'}, 'right': {'table': 'B', 'column': 'Y'}}
        rel2 = {'left': {'table': 'C', 'column': 'P'}, 'right': {'table': 'D', 'column': 'Q'}}
        ds1 = _make_ds(relationships=[rel1])
        ds2 = _make_ds(relationships=[rel2])
        wb1 = _make_extracted(datasources=[ds1])
        wb2 = _make_extracted(datasources=[ds2])
        dupes = _count_relationship_duplicates([wb1, wb2])
        self.assertEqual(dupes, 0)

    def test_relationship_key_alt_format(self):
        rel = {'from_table': 'A', 'from_column': 'X', 'to_table': 'B', 'to_column': 'Y'}
        key = _relationship_key(rel)
        self.assertEqual(key, ('a', 'x', 'b', 'y'))


# ═══════════════════════════════════════════════════════════════════
#  Parameter merging
# ═══════════════════════════════════════════════════════════════════

class TestParameterMerging(unittest.TestCase):
    """Tests for parameter merge logic."""

    def test_identical_params_deduplicated(self):
        p = {'name': 'TopN', 'datatype': 'integer', 'domain_type': 'range', 'current_value': '10'}
        wb1 = _make_extracted(parameters=[p])
        wb2 = _make_extracted(parameters=[copy.deepcopy(p)])
        result = _merge_parameters([wb1, wb2], ['WB1', 'WB2'])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], 'TopN')

    def test_conflicting_params_namespaced(self):
        p1 = {'name': 'TopN', 'datatype': 'integer', 'domain_type': 'range', 'current_value': '10'}
        p2 = {'name': 'TopN', 'datatype': 'integer', 'domain_type': 'list', 'current_value': '5'}
        wb1 = _make_extracted(parameters=[p1])
        wb2 = _make_extracted(parameters=[p2])
        result = _merge_parameters([wb1, wb2], ['WB1', 'WB2'])
        self.assertEqual(len(result), 2)
        names = {r['name'] for r in result}
        self.assertIn('TopN (WB1)', names)
        self.assertIn('TopN (WB2)', names)

    def test_unique_params_kept(self):
        p1 = {'name': 'ParamA', 'datatype': 'string', 'domain_type': 'list', 'current_value': 'x'}
        p2 = {'name': 'ParamB', 'datatype': 'integer', 'domain_type': 'range', 'current_value': '1'}
        wb1 = _make_extracted(parameters=[p1])
        wb2 = _make_extracted(parameters=[p2])
        result = _merge_parameters([wb1, wb2], ['WB1', 'WB2'])
        self.assertEqual(len(result), 2)


class TestParameterConflictDetection(unittest.TestCase):

    def test_identical_params_counted_as_duplicates(self):
        p = {'name': 'N', 'datatype': 'integer', 'domain_type': 'range', 'current_value': '5'}
        conflicts, dupes = _detect_parameter_conflicts(
            [_make_extracted(parameters=[p]), _make_extracted(parameters=[copy.deepcopy(p)])],
            ['WB1', 'WB2']
        )
        self.assertEqual(dupes, 1)
        self.assertEqual(len(conflicts), 0)

    def test_different_params_detected_as_conflict(self):
        p1 = {'name': 'N', 'datatype': 'integer', 'domain_type': 'range', 'current_value': '5'}
        p2 = {'name': 'N', 'datatype': 'string', 'domain_type': 'list', 'current_value': 'A'}
        conflicts, dupes = _detect_parameter_conflicts(
            [_make_extracted(parameters=[p1]), _make_extracted(parameters=[p2])],
            ['WB1', 'WB2']
        )
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(dupes, 0)


# ═══════════════════════════════════════════════════════════════════
#  Column merging
# ═══════════════════════════════════════════════════════════════════

class TestColumnMerging(unittest.TestCase):
    """Tests for _merge_columns_into."""

    def test_column_union(self):
        t1 = _make_table('T', ['A:string', 'B:integer'])
        t2 = _make_table('T', ['B:integer', 'C:real'])
        _merge_columns_into(t1, t2)
        col_names = {c['name'] for c in t1['columns']}
        self.assertEqual(col_names, {'A', 'B', 'C'})

    def test_type_mismatch_wider_wins(self):
        t1 = _make_table('T', [{'name': 'X', 'datatype': 'integer'}])
        t2 = _make_table('T', [{'name': 'X', 'datatype': 'string'}])
        _merge_columns_into(t1, t2)
        x_col = [c for c in t1['columns'] if c['name'] == 'X'][0]
        self.assertEqual(x_col['datatype'], 'string')

    def test_hidden_unhidden_if_any_visible(self):
        t1 = _make_table('T', [{'name': 'X', 'datatype': 'string', 'hidden': True}])
        t2 = _make_table('T', [{'name': 'X', 'datatype': 'string', 'hidden': False}])
        _merge_columns_into(t1, t2)
        x_col = [c for c in t1['columns'] if c['name'] == 'X'][0]
        self.assertFalse(x_col['hidden'])

    def test_semantic_role_merged(self):
        t1 = _make_table('T', [{'name': 'City', 'datatype': 'string'}])
        t2 = _make_table('T', [{'name': 'City', 'datatype': 'string', 'semantic_role': 'City'}])
        _merge_columns_into(t1, t2)
        city_col = [c for c in t1['columns'] if c['name'] == 'City'][0]
        self.assertEqual(city_col.get('semantic_role'), 'City')


class TestTypeWidth(unittest.TestCase):

    def test_string_widest(self):
        self.assertGreater(_type_width('string'), _type_width('real'))
        self.assertGreater(_type_width('string'), _type_width('integer'))

    def test_real_wider_than_integer(self):
        self.assertGreater(_type_width('real'), _type_width('integer'))

    def test_unknown_type_defaults_to_5(self):
        self.assertEqual(_type_width('unknown_type'), 5)


# ═══════════════════════════════════════════════════════════════════
#  Column conflict detection
# ═══════════════════════════════════════════════════════════════════

class TestColumnConflictDetection(unittest.TestCase):

    def test_no_conflict(self):
        entries = [
            ('WB1', _make_table('T', ['A:integer']), {}, 'T', None),
            ('WB2', _make_table('T', ['A:integer']), {}, 'T', None),
        ]
        self.assertEqual(_detect_column_conflicts(entries), [])

    def test_type_mismatch_detected(self):
        entries = [
            ('WB1', _make_table('T', ['A:integer']), {}, 'T', None),
            ('WB2', _make_table('T', ['A:string']), {}, 'T', None),
        ]
        conflicts = _detect_column_conflicts(entries)
        self.assertEqual(len(conflicts), 1)
        self.assertIn("'A'", conflicts[0])


# ═══════════════════════════════════════════════════════════════════
#  Merge score
# ═══════════════════════════════════════════════════════════════════

class TestMergeScore(unittest.TestCase):
    """Tests for calculate_merge_score."""

    def test_high_overlap_high_score(self):
        ds = _make_ds(tables=[_make_table('Orders', ['ID', 'Amt'])])
        wb1 = _make_extracted(datasources=[ds])
        wb2 = _make_extracted(datasources=[copy.deepcopy(ds)])
        assessment = assess_merge([wb1, wb2], ['WB1', 'WB2'])
        self.assertGreaterEqual(assessment.merge_score, 60)
        self.assertEqual(assessment.recommendation, 'merge')

    def test_no_overlap_low_score(self):
        ds1 = _make_ds(server='s1', tables=[_make_table('A', ['X'])])
        ds2 = _make_ds(server='s2', tables=[_make_table('B', ['Y'])])
        wb1 = _make_extracted(datasources=[ds1])
        wb2 = _make_extracted(datasources=[ds2])
        assessment = assess_merge([wb1, wb2], ['WB1', 'WB2'])
        self.assertLess(assessment.merge_score, 30)
        self.assertEqual(assessment.recommendation, 'separate')

    def test_score_capped_at_100(self):
        assessment = MergeAssessment(workbooks=['WB1', 'WB2'])
        assessment.merge_score = 150
        score = calculate_merge_score(assessment)
        self.assertLessEqual(score, 100)

    def test_no_measures_gives_full_measure_points(self):
        assessment = MergeAssessment(
            workbooks=['WB1', 'WB2'],
            total_tables=4,
            unique_table_count=2,  # 50% saved
            merge_candidates=[
                MergeCandidate(
                    fingerprint=TableFingerprint('SQL', 's', 'd', 'dbo', 'T'),
                    table_name='T', sources=[], column_overlap=1.0,
                )
            ],
            measure_duplicates_removed=0,
            measure_conflicts=[],
        )
        score = calculate_merge_score(assessment)
        # Table: 50% * 40 = 20, Column: 1.0 * 20 = 20, Measure: 20, Conn: 20
        self.assertGreaterEqual(score, 60)


# ═══════════════════════════════════════════════════════════════════
#  Full merge_semantic_models
# ═══════════════════════════════════════════════════════════════════

class TestMergeSemanticModels(unittest.TestCase):
    """Tests for the full merge pipeline."""

    def _two_workbooks_same_table(self):
        """Helper: 2 workbooks with the same Orders table."""
        ds1 = _make_ds(
            tables=[_make_table('Orders', ['ID:integer', 'Amount:real'])],
            calculations=[_make_calc('Total', 'SUM([Amount])')],
            relationships=[],
        )
        ds2 = _make_ds(
            tables=[_make_table('Orders', ['ID:integer', 'Amount:real', 'Region:string'])],
            calculations=[_make_calc('Total', 'SUM([Amount])')],
            relationships=[],
        )
        wb1 = _make_extracted(
            datasources=[ds1],
            calculations=[_make_calc('Total', 'SUM([Amount])')],
            worksheets=[{'name': 'Sheet1', 'type': 'worksheet', 'columns': []}],
        )
        wb2 = _make_extracted(
            datasources=[ds2],
            calculations=[_make_calc('Total', 'SUM([Amount])')],
            worksheets=[{'name': 'Sheet2', 'type': 'worksheet', 'columns': []}],
        )
        return wb1, wb2

    def test_merged_has_one_datasource(self):
        wb1, wb2 = self._two_workbooks_same_table()
        assessment = assess_merge([wb1, wb2], ['WB1', 'WB2'])
        merged = merge_semantic_models([wb1, wb2], assessment, 'TestModel')
        self.assertEqual(len(merged['datasources']), 1)

    def test_merged_table_column_union(self):
        wb1, wb2 = self._two_workbooks_same_table()
        assessment = assess_merge([wb1, wb2], ['WB1', 'WB2'])
        merged = merge_semantic_models([wb1, wb2], assessment, 'TestModel')
        tables = merged['datasources'][0]['tables']
        orders = [t for t in tables if t['name'] == 'Orders'][0]
        col_names = {c['name'] for c in orders['columns']}
        # Union: ID, Amount from wb1 + Region from wb2
        self.assertIn('ID', col_names)
        self.assertIn('Amount', col_names)
        self.assertIn('Region', col_names)

    def test_merged_deduplicates_identical_calculations(self):
        wb1, wb2 = self._two_workbooks_same_table()
        assessment = assess_merge([wb1, wb2], ['WB1', 'WB2'])
        merged = merge_semantic_models([wb1, wb2], assessment, 'TestModel')
        # "Total" appears in both workbooks with same formula → one instance
        total_calcs = [c for c in merged['calculations'] if c['caption'] == 'Total']
        self.assertEqual(len(total_calcs), 1)

    def test_merged_namespaces_conflicting_measures(self):
        ds1 = _make_ds(calculations=[_make_calc('Revenue', 'SUM([A])')])
        ds2 = _make_ds(calculations=[_make_calc('Revenue', 'SUM([B])')])
        wb1 = _make_extracted(datasources=[ds1], calculations=[_make_calc('Revenue', 'SUM([A])')])
        wb2 = _make_extracted(datasources=[ds2], calculations=[_make_calc('Revenue', 'SUM([B])')])
        assessment = assess_merge([wb1, wb2], ['WB1', 'WB2'])
        merged = merge_semantic_models([wb1, wb2], assessment, 'Test')
        revenue_calcs = [c for c in merged['calculations'] if 'Revenue' in c['caption']]
        captions = {c['caption'] for c in revenue_calcs}
        self.assertIn('Revenue (WB1)', captions)
        self.assertIn('Revenue (WB2)', captions)

    def test_merged_preserves_all_worksheets(self):
        wb1, wb2 = self._two_workbooks_same_table()
        assessment = assess_merge([wb1, wb2], ['WB1', 'WB2'])
        merged = merge_semantic_models([wb1, wb2], assessment, 'Test')
        ws_names = [ws['name'] for ws in merged['worksheets']]
        self.assertIn('Sheet1', ws_names)
        self.assertIn('Sheet2', ws_names)

    def test_merged_deduplicates_relationships(self):
        rel = {'left': {'table': 'O', 'column': 'CID'}, 'right': {'table': 'C', 'column': 'ID'}}
        ds1 = _make_ds(tables=[_make_table('O'), _make_table('C')], relationships=[rel])
        ds2 = _make_ds(tables=[_make_table('O'), _make_table('C')], relationships=[copy.deepcopy(rel)])
        wb1 = _make_extracted(datasources=[ds1])
        wb2 = _make_extracted(datasources=[ds2])
        assessment = assess_merge([wb1, wb2], ['WB1', 'WB2'])
        merged = merge_semantic_models([wb1, wb2], assessment, 'Test')
        rels = merged['datasources'][0]['relationships']
        self.assertEqual(len(rels), 1)


# ═══════════════════════════════════════════════════════════════════
#  Merge list by name
# ═══════════════════════════════════════════════════════════════════

class TestMergeListByName(unittest.TestCase):

    def test_deduplicates_by_name(self):
        wb1 = {'sets': [{'name': 'TopCustomers', 'table': 'C'}]}
        wb2 = {'sets': [{'name': 'TopCustomers', 'table': 'C'}]}
        result = _merge_list_by_name([wb1, wb2], 'sets')
        self.assertEqual(len(result), 1)

    def test_keeps_unique(self):
        wb1 = {'sets': [{'name': 'Set1'}]}
        wb2 = {'sets': [{'name': 'Set2'}]}
        result = _merge_list_by_name([wb1, wb2], 'sets')
        self.assertEqual(len(result), 2)

    def test_handles_missing_key(self):
        result = _merge_list_by_name([{}, {}], 'sets')
        self.assertEqual(result, [])

    def test_handles_non_list(self):
        result = _merge_list_by_name([{'aliases': {'a': 'b'}}], 'aliases')
        self.assertEqual(result, [])


# ═══════════════════════════════════════════════════════════════════
#  Field mapping
# ═══════════════════════════════════════════════════════════════════

class TestBuildFieldMapping(unittest.TestCase):

    def test_conflict_creates_mapping(self):
        assessment = MergeAssessment(
            workbooks=['WB1', 'WB2'],
            measure_conflicts=[
                MeasureConflict(name='Revenue', table='T',
                                variants={'WB1': 'SUM(A)', 'WB2': 'SUM(B)'}),
            ],
        )
        mapping = build_field_mapping(assessment, 'WB1')
        self.assertEqual(mapping, {'Revenue': 'Revenue (WB1)'})

    def test_no_conflict_empty_mapping(self):
        assessment = MergeAssessment(workbooks=['WB1', 'WB2'])
        mapping = build_field_mapping(assessment, 'WB1')
        self.assertEqual(mapping, {})

    def test_mapping_only_for_relevant_workbook(self):
        assessment = MergeAssessment(
            workbooks=['WB1', 'WB2'],
            measure_conflicts=[
                MeasureConflict(name='Total', table='T',
                                variants={'WB1': 'X', 'WB2': 'Y'}),
            ],
        )
        mapping_wb2 = build_field_mapping(assessment, 'WB2')
        self.assertEqual(mapping_wb2, {'Total': 'Total (WB2)'})


# ═══════════════════════════════════════════════════════════════════
#  Merge assessment report
# ═══════════════════════════════════════════════════════════════════

class TestMergeAssessmentReport(unittest.TestCase):

    def test_generate_report_returns_dict(self):
        assessment = MergeAssessment(workbooks=['WB1'], merge_score=75, recommendation='merge')
        report = generate_merge_report(assessment)
        self.assertEqual(report['merge_score'], 75)
        self.assertEqual(report['recommendation'], 'merge')
        self.assertIn('timestamp', report)

    def test_generate_report_writes_json(self):
        assessment = MergeAssessment(workbooks=['WB1'])
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, 'report.json')
            generate_merge_report(assessment, output_path=path)
            self.assertTrue(os.path.exists(path))
            with open(path, 'r') as f:
                data = json.load(f)
            self.assertIn('workbooks', data)

    def test_print_summary_does_not_crash(self):
        ds = _make_ds(tables=[_make_table('T', ['A'])])
        wb1 = _make_extracted(datasources=[ds])
        wb2 = _make_extracted(datasources=[copy.deepcopy(ds)])
        assessment = assess_merge([wb1, wb2], ['WB1', 'WB2'])
        # Just ensure it doesn't throw
        print_merge_summary(assessment)

    def test_print_summary_with_conflicts(self):
        assessment = MergeAssessment(
            workbooks=['WB1', 'WB2'],
            merge_candidates=[MergeCandidate(
                fingerprint=TableFingerprint('SQL', 's', 'd', 'dbo', 'T'),
                table_name='T', sources=[('WB1', {}, {}), ('WB2', {}, {})],
                column_overlap=0.5,
                conflicts=['Column X: type mismatch'],
            )],
            measure_conflicts=[MeasureConflict(
                name='Rev', table='T', variants={'WB1': 'A', 'WB2': 'B'},
            )],
            unique_tables={'WB1': ['Forecast']},
            total_tables=4, unique_table_count=3,
            merge_score=45, recommendation='partial',
        )
        print_merge_summary(assessment)


# ═══════════════════════════════════════════════════════════════════
#  Thin report generator
# ═══════════════════════════════════════════════════════════════════

class TestThinReportGenerator(unittest.TestCase):

    def test_definition_pbir_bypath(self):
        from powerbi_import.thin_report_generator import ThinReportGenerator
        with tempfile.TemporaryDirectory() as td:
            gen = ThinReportGenerator('SharedModel', td)
            gen._write_definition_pbir(os.path.join(td, 'Test.Report'))
            pbir_path = os.path.join(td, 'Test.Report', 'definition.pbir')
            self.assertTrue(os.path.exists(pbir_path))
            with open(pbir_path, 'r') as f:
                data = json.load(f)
            self.assertEqual(
                data['datasetReference']['byPath']['path'],
                '../SharedModel.SemanticModel'
            )

    def test_pbip_file_created(self):
        from powerbi_import.thin_report_generator import ThinReportGenerator
        with tempfile.TemporaryDirectory() as td:
            gen = ThinReportGenerator('SharedModel', td)
            gen._write_pbip('TestReport')
            pbip_path = os.path.join(td, 'TestReport.pbip')
            self.assertTrue(os.path.exists(pbip_path))
            with open(pbip_path, 'r') as f:
                data = json.load(f)
            self.assertEqual(data['artifacts'][0]['report']['path'], 'TestReport.Report')

    def test_platform_file_created(self):
        from powerbi_import.thin_report_generator import ThinReportGenerator
        with tempfile.TemporaryDirectory() as td:
            report_dir = os.path.join(td, 'Test.Report')
            os.makedirs(report_dir)
            gen = ThinReportGenerator('SM', td)
            gen._write_platform(report_dir, 'Test')
            with open(os.path.join(report_dir, '.platform'), 'r') as f:
                data = json.load(f)
            self.assertEqual(data['metadata']['type'], 'Report')
            self.assertEqual(data['metadata']['displayName'], 'Test')

    def test_remap_fields(self):
        from powerbi_import.thin_report_generator import ThinReportGenerator
        gen = ThinReportGenerator('SM', '/tmp')
        converted = {
            'worksheets': [
                {'name': 'S', 'columns': [{'name': 'Revenue'}],
                 'filters': [{'field': 'Revenue'}],
                 'mark_encoding': {'color': {'field': 'Revenue'}}},
            ],
            'calculations': [{'caption': 'Revenue', 'formula': 'SUM(A)'}],
            'filters': [{'field': 'Revenue'}],
            'dashboards': [],
        }
        mapping = {'Revenue': 'Revenue (WB1)'}
        result = gen._remap_fields(converted, mapping)
        self.assertEqual(result['worksheets'][0]['columns'][0]['name'], 'Revenue (WB1)')
        self.assertEqual(result['worksheets'][0]['filters'][0]['field'], 'Revenue (WB1)')
        self.assertEqual(result['worksheets'][0]['mark_encoding']['color']['field'], 'Revenue (WB1)')
        self.assertEqual(result['calculations'][0]['caption'], 'Revenue (WB1)')
        self.assertEqual(result['filters'][0]['field'], 'Revenue (WB1)')

    def test_remap_empty_mapping_returns_same(self):
        from powerbi_import.thin_report_generator import ThinReportGenerator
        gen = ThinReportGenerator('SM', '/tmp')
        converted = {'worksheets': [], 'filters': [], 'dashboards': [], 'calculations': []}
        result = gen._remap_fields(converted, {})
        self.assertEqual(result, converted)

    def test_remap_none_mapping_returns_original(self):
        from powerbi_import.thin_report_generator import ThinReportGenerator
        gen = ThinReportGenerator('SM', '/tmp')
        converted = {'worksheets': []}
        result = gen._remap_fields(converted, None)
        self.assertIs(result, converted)


# ═══════════════════════════════════════════════════════════════════
#  CLI argument wiring
# ═══════════════════════════════════════════════════════════════════

class TestCLIArguments(unittest.TestCase):

    def test_shared_model_argument_exists(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        # Import the parser builder
        import importlib
        import migrate
        importlib.reload(migrate)
        parser = migrate._build_argument_parser()
        # Parse with --shared-model
        args = parser.parse_args(['--shared-model', 'a.twbx', 'b.twbx'])
        self.assertEqual(args.shared_model, ['a.twbx', 'b.twbx'])

    def test_model_name_argument(self):
        import migrate
        parser = migrate._build_argument_parser()
        args = parser.parse_args(['--shared-model', 'a.twbx', '--model-name', 'Sales'])
        self.assertEqual(args.model_name, 'Sales')

    def test_assess_merge_flag(self):
        import migrate
        parser = migrate._build_argument_parser()
        args = parser.parse_args(['--shared-model', 'a.twbx', '--assess-merge'])
        self.assertTrue(args.assess_merge)

    def test_force_merge_flag(self):
        import migrate
        parser = migrate._build_argument_parser()
        args = parser.parse_args(['--shared-model', 'a.twbx', '--force-merge'])
        self.assertTrue(args.force_merge)

    def test_shared_model_no_args(self):
        import migrate
        parser = migrate._build_argument_parser()
        args = parser.parse_args(['--shared-model'])
        self.assertEqual(args.shared_model, [])


if __name__ == '__main__':
    unittest.main()
