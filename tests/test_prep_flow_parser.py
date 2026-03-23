"""
Unit tests for Tableau Prep flow parser (prep_flow_parser.py).

Tests flow reading, node type detection, topological sort, step conversion,
expression conversion, join/union/pivot/aggregate parsing, and the merge logic.
"""

import io
import json
import os
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tableau_export'))

from prep_flow_parser import read_prep_flow
from prep_flow_parser import _get_node_type
from prep_flow_parser import _topological_sort
from prep_flow_parser import _convert_prep_expression_to_m
from prep_flow_parser import _parse_clean_actions
from prep_flow_parser import _convert_action_to_m_step
from prep_flow_parser import _parse_aggregate_node
from prep_flow_parser import _parse_join_node
from prep_flow_parser import _parse_union_node
from prep_flow_parser import _parse_pivot_node
from prep_flow_parser import _parse_input_node
from prep_flow_parser import _clean_m_table_ref
from prep_flow_parser import _process_prep_node
from prep_flow_parser import _process_transform_node
from prep_flow_parser import _collect_prep_datasources
from prep_flow_parser import merge_prep_with_workbook
from prep_flow_parser import parse_prep_flow
from prep_flow_parser import _PREP_CONNECTION_MAP
from prep_flow_parser import _PREP_TYPE_MAP
from prep_flow_parser import _PREP_AGG_MAP
from prep_flow_parser import _PREP_JOIN_MAP


# ═══════════════════════════════════════════════════════════════════
# Helper — build minimal flow JSON
# ═══════════════════════════════════════════════════════════════════

def _make_flow(nodes, connections=None):
    """Create a minimal Prep flow dict."""
    return {
        'nodes': nodes,
        'connections': connections or {},
    }


def _input_node(name='Table1', conn_id='conn1', fields=None, next_ids=None):
    """Create an input node."""
    node = {
        'baseType': 'input',
        'nodeType': '.v1.LoadCsv',
        'name': name,
        'connectionId': conn_id,
        'connectionAttributes': {'class': 'csv', 'filename': f'{name}.csv'},
        'fields': fields or [
            {'name': 'ID', 'type': 'integer'},
            {'name': 'Name', 'type': 'string'},
            {'name': 'Amount', 'type': 'real'},
        ],
        'nextNodes': [{'nextNodeId': nid} for nid in (next_ids or [])],
    }
    return node


def _clean_node(name='Clean', actions=None, next_ids=None):
    """Create a SuperTransform (clean) node."""
    return {
        'baseType': 'transform',
        'nodeType': '.v2018_3_3.SuperTransform',
        'name': name,
        'beforeActionGroup': {'actions': actions or []},
        'nextNodes': [{'nextNodeId': nid} for nid in (next_ids or [])],
    }


def _output_node(name='Output'):
    """Create an output node."""
    return {
        'baseType': 'output',
        'nodeType': '.v1.PublishExtract',
        'name': name,
        'nextNodes': [],
    }


# ═══════════════════════════════════════════════════════════════════
# Flow reading
# ═══════════════════════════════════════════════════════════════════

class TestReadPrepFlow(unittest.TestCase):
    """Test read_prep_flow for .tfl files."""

    def test_read_tfl_file(self):
        flow_data = _make_flow({'n1': _input_node()})
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tfl', delete=False,
                                         encoding='utf-8') as f:
            json.dump(flow_data, f)
            path = f.name
        try:
            result = read_prep_flow(path)
            self.assertIn('nodes', result)
            self.assertIn('n1', result['nodes'])
        finally:
            os.unlink(path)

    def test_unsupported_extension_raises(self):
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
            path = f.name
        try:
            with self.assertRaises(ValueError):
                read_prep_flow(path)
        finally:
            os.unlink(path)

    def test_read_tflx_zip(self):
        """read_prep_flow handles .tflx ZIP archives with a .tfl entry."""
        flow_data = _make_flow({'n1': _input_node()})
        with tempfile.NamedTemporaryFile(suffix='.tflx', delete=False) as tmp:
            path = tmp.name
        try:
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr('flow.tfl', json.dumps(flow_data))
            result = read_prep_flow(path)
            self.assertIn('nodes', result)
            self.assertIn('n1', result['nodes'])
        finally:
            os.unlink(path)

    def test_read_tfl_zip_autodetect(self):
        """read_prep_flow auto-detects ZIP archives with a .tfl extension."""
        flow_data = _make_flow({'n1': _input_node()})
        with tempfile.NamedTemporaryFile(suffix='.tfl', delete=False) as tmp:
            path = tmp.name
        try:
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr('flow', json.dumps(flow_data))
            result = read_prep_flow(path)
            self.assertIn('nodes', result)
        finally:
            os.unlink(path)

    def test_read_tflx_flow_entry_fallback(self):
        """read_prep_flow finds a 'flow' entry when no .tfl entry exists."""
        flow_data = _make_flow({'n2': _input_node('T2')})
        with tempfile.NamedTemporaryFile(suffix='.tflx', delete=False) as tmp:
            path = tmp.name
        try:
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr('flow', json.dumps(flow_data))
                z.writestr('maestroMetadata', '{}')
            result = read_prep_flow(path)
            self.assertIn('n2', result['nodes'])
        finally:
            os.unlink(path)


# ═══════════════════════════════════════════════════════════════════
# Node type detection
# ═══════════════════════════════════════════════════════════════════

class TestGetNodeType(unittest.TestCase):
    """Test _get_node_type extraction."""

    def test_versioned_node_type(self):
        node = {'nodeType': '.v2018_3_3.SuperTransform'}
        self.assertEqual(_get_node_type(node), 'SuperTransform')

    def test_simple_node_type(self):
        node = {'nodeType': '.v1.LoadCsv'}
        self.assertEqual(_get_node_type(node), 'LoadCsv')

    def test_empty_node_type(self):
        node = {'nodeType': ''}
        self.assertEqual(_get_node_type(node), '')


# ═══════════════════════════════════════════════════════════════════
# Topological sort
# ═══════════════════════════════════════════════════════════════════

class TestTopologicalSort(unittest.TestCase):
    """Test _topological_sort for DAG traversal."""

    def test_linear_chain(self):
        nodes = {
            'a': {'nextNodes': [{'nextNodeId': 'b'}]},
            'b': {'nextNodes': [{'nextNodeId': 'c'}]},
            'c': {'nextNodes': []},
        }
        result = _topological_sort(nodes)
        self.assertEqual(result, ['a', 'b', 'c'])

    def test_diamond_graph(self):
        nodes = {
            'a': {'nextNodes': [{'nextNodeId': 'b'}, {'nextNodeId': 'c'}]},
            'b': {'nextNodes': [{'nextNodeId': 'd'}]},
            'c': {'nextNodes': [{'nextNodeId': 'd'}]},
            'd': {'nextNodes': []},
        }
        result = _topological_sort(nodes)
        self.assertEqual(result[0], 'a')
        self.assertEqual(result[-1], 'd')
        self.assertEqual(len(result), 4)

    def test_single_node(self):
        nodes = {'a': {'nextNodes': []}}
        result = _topological_sort(nodes)
        self.assertEqual(result, ['a'])

    def test_empty_graph(self):
        result = _topological_sort({})
        self.assertEqual(result, [])


# ═══════════════════════════════════════════════════════════════════
# Expression conversion
# ═══════════════════════════════════════════════════════════════════

class TestConvertPrepExpression(unittest.TestCase):
    """Test _convert_prep_expression_to_m."""

    def test_if_then_else(self):
        result = _convert_prep_expression_to_m('IF [X] > 10 THEN "High" ELSE "Low" END')
        self.assertIn('if', result)
        self.assertIn('then', result)
        self.assertIn('else', result)
        self.assertNotIn('END', result)

    def test_elseif_conversion(self):
        result = _convert_prep_expression_to_m('IF [X] > 10 THEN "A" ELSEIF [X] > 5 THEN "B" ELSE "C" END')
        self.assertIn('else if', result)

    def test_logical_operators(self):
        result = _convert_prep_expression_to_m('[A] > 1 AND [B] < 2 OR NOT [C]')
        self.assertIn('and', result)
        self.assertIn('or', result)
        self.assertIn('not', result)

    def test_comparison_operators(self):
        result = _convert_prep_expression_to_m('[A] != [B] AND [C] == [D]')
        self.assertIn('<>', result)
        self.assertNotIn('!=', result)
        # == becomes = in M
        self.assertIn('=', result)

    def test_string_functions(self):
        result = _convert_prep_expression_to_m('CONTAINS([Name], "test")')
        self.assertIn('Text.Contains', result)

    def test_len_function(self):
        result = _convert_prep_expression_to_m('LEN([Name])')
        self.assertIn('Text.Length', result)

    def test_upper_lower(self):
        self.assertIn('Text.Upper', _convert_prep_expression_to_m('UPPER([X])'))
        self.assertIn('Text.Lower', _convert_prep_expression_to_m('LOWER([X])'))

    def test_empty_returns_empty_string_literal(self):
        result = _convert_prep_expression_to_m('')
        self.assertEqual(result, '""')

    def test_none_returns_empty_string_literal(self):
        result = _convert_prep_expression_to_m(None)
        self.assertEqual(result, '""')

    def test_isnull_conversion(self):
        result = _convert_prep_expression_to_m('ISNULL([X])')
        self.assertIn('null', result)


# ═══════════════════════════════════════════════════════════════════
# Clean action conversion
# ═══════════════════════════════════════════════════════════════════

class TestCleanActions(unittest.TestCase):
    """Test _parse_clean_actions and _convert_action_to_m_step."""

    def test_rename_column(self):
        node = _clean_node(actions=[
            {'actionType': '.v1.RenameColumn', 'columnName': 'OldName', 'newColumnName': 'NewName'},
        ])
        steps = _parse_clean_actions(node)
        self.assertEqual(len(steps), 1)
        step_name, step_expr = steps[0]
        self.assertIn('RenameColumns', step_expr)
        self.assertIn('OldName', step_expr)
        self.assertIn('NewName', step_expr)

    def test_batched_renames(self):
        node = _clean_node(actions=[
            {'actionType': '.v1.RenameColumn', 'columnName': 'A', 'newColumnName': 'X'},
            {'actionType': '.v1.RenameColumn', 'columnName': 'B', 'newColumnName': 'Y'},
        ])
        steps = _parse_clean_actions(node)
        # Both renames should be batched into one step
        self.assertEqual(len(steps), 1)
        _, expr = steps[0]
        self.assertIn('A', expr)
        self.assertIn('X', expr)
        self.assertIn('B', expr)
        self.assertIn('Y', expr)

    def test_remove_column(self):
        node = _clean_node(actions=[
            {'actionType': '.v1.RemoveColumn', 'columnName': 'DropMe'},
        ])
        steps = _parse_clean_actions(node)
        self.assertEqual(len(steps), 1)
        _, expr = steps[0]
        self.assertIn('RemoveColumns', expr)
        self.assertIn('DropMe', expr)

    def test_duplicate_column(self):
        node = _clean_node(actions=[
            {'actionType': '.v1.DuplicateColumn', 'columnName': 'Col', 'newColumnName': 'Col_copy'},
        ])
        steps = _parse_clean_actions(node)
        self.assertEqual(len(steps), 1)
        _, expr = steps[0]
        self.assertIn('DuplicateColumn', expr)

    def test_change_column_type(self):
        node = _clean_node(actions=[
            {'actionType': '.v1.ChangeColumnType', 'columnName': 'Amount', 'newType': 'integer'},
        ])
        steps = _parse_clean_actions(node)
        self.assertEqual(len(steps), 1)
        _, expr = steps[0]
        self.assertIn('TransformColumnTypes', expr)
        self.assertIn('number', expr)

    def test_filter_values_keep(self):
        node = _clean_node(actions=[
            {'actionType': '.v1.FilterValues', 'columnName': 'Status',
             'values': ['Active', 'Pending'], 'filterType': 'keep'},
        ])
        steps = _parse_clean_actions(node)
        self.assertEqual(len(steps), 1)

    def test_filter_values_remove(self):
        node = _clean_node(actions=[
            {'actionType': '.v1.FilterValues', 'columnName': 'Status',
             'values': ['Deleted'], 'filterType': 'remove'},
        ])
        steps = _parse_clean_actions(node)
        self.assertEqual(len(steps), 1)

    def test_replace_values(self):
        node = _clean_node(actions=[
            {'actionType': '.v1.ReplaceValues', 'columnName': 'Region',
             'oldValue': 'NA', 'newValue': 'North America'},
        ])
        steps = _parse_clean_actions(node)
        self.assertEqual(len(steps), 1)
        _, expr = steps[0]
        self.assertIn('ReplaceValue', expr)

    def test_split_column(self):
        node = _clean_node(actions=[
            {'actionType': '.v1.SplitColumn', 'columnName': 'FullName', 'delimiter': ' '},
        ])
        steps = _parse_clean_actions(node)
        self.assertEqual(len(steps), 1)
        _, expr = steps[0]
        self.assertIn('SplitColumn', expr)

    def test_add_column(self):
        node = _clean_node(actions=[
            {'actionType': '.v1.AddColumn', 'columnName': 'Total',
             'expression': '[Amount] * 1.1'},
        ])
        steps = _parse_clean_actions(node)
        self.assertEqual(len(steps), 1)
        _, expr = steps[0]
        self.assertIn('AddColumn', expr)

    def test_clean_operation_trim(self):
        node = _clean_node(actions=[
            {'actionType': '.v1.CleanOperation', 'columnName': 'Name', 'operation': 'trim'},
        ])
        steps = _parse_clean_actions(node)
        self.assertEqual(len(steps), 1)
        _, expr = steps[0]
        self.assertIn('Trim', expr)

    def test_fill_down(self):
        node = _clean_node(actions=[
            {'actionType': '.v1.FillValues', 'columnName': 'Region', 'direction': 'down'},
        ])
        steps = _parse_clean_actions(node)
        self.assertEqual(len(steps), 1)
        _, expr = steps[0]
        self.assertIn('FillDown', expr)

    def test_fill_up(self):
        node = _clean_node(actions=[
            {'actionType': '.v1.FillValues', 'columnName': 'Region', 'direction': 'up'},
        ])
        steps = _parse_clean_actions(node)
        self.assertEqual(len(steps), 1)
        _, expr = steps[0]
        self.assertIn('FillUp', expr)

    def test_group_replace(self):
        node = _clean_node(actions=[
            {'actionType': '.v1.GroupReplace', 'columnName': 'Category',
             'groupings': [
                 {'from': 'Cat A', 'to': 'Category A'},
                 {'from': 'Cat B', 'to': 'Category B'},
             ]},
        ])
        steps = _parse_clean_actions(node)
        self.assertEqual(len(steps), 2)  # One replace step per grouping

    def test_unknown_action_returns_nothing(self):
        node = _clean_node(actions=[
            {'actionType': '.v1.FutureAction', 'columnName': 'X'},
        ])
        steps = _parse_clean_actions(node)
        self.assertEqual(len(steps), 0)

    def test_rename_flush_before_other_action(self):
        """Renames should flush before a non-rename action."""
        node = _clean_node(actions=[
            {'actionType': '.v1.RenameColumn', 'columnName': 'A', 'newColumnName': 'X'},
            {'actionType': '.v1.RemoveColumn', 'columnName': 'B'},
        ])
        steps = _parse_clean_actions(node)
        self.assertEqual(len(steps), 2)
        # First step should be rename, second should be remove
        self.assertIn('RenameColumns', steps[0][1])
        self.assertIn('RemoveColumns', steps[1][1])


# ═══════════════════════════════════════════════════════════════════
# Aggregate step
# ═══════════════════════════════════════════════════════════════════

class TestAggregateNode(unittest.TestCase):
    """Test _parse_aggregate_node."""

    def test_basic_aggregation(self):
        node = {
            'groupByFields': [{'name': 'Region'}],
            'aggregateFields': [
                {'name': 'Sales', 'aggregation': 'SUM', 'newColumnName': 'Total Sales'},
            ],
        }
        result = _parse_aggregate_node(node)
        self.assertIsNotNone(result)
        assert result is not None
        step_name, step_expr = result
        self.assertIn('Table.Group', step_expr)

    def test_empty_fields_returns_none(self):
        node = {'groupByFields': [], 'aggregateFields': []}
        result = _parse_aggregate_node(node)
        self.assertIsNone(result)


# ═══════════════════════════════════════════════════════════════════
# Join step
# ═══════════════════════════════════════════════════════════════════

class TestJoinNode(unittest.TestCase):
    """Test _parse_join_node."""

    def test_inner_join(self):
        node = {
            'joinType': 'inner',
            'joinConditions': [
                {'leftColumn': 'ID', 'rightColumn': 'CustID'},
            ],
        }
        right_fields = [
            {'name': 'CustID'}, {'name': 'CustName'},
        ]
        result = _parse_join_node(node, 'Customers', right_fields)
        self.assertIsNotNone(result)
        assert result is not None
        # Should return list of steps (join + expand)
        self.assertIsInstance(result, list)
        self.assertTrue(len(result) >= 1)

    def test_no_conditions_returns_none(self):
        node = {'joinType': 'inner', 'joinConditions': []}
        result = _parse_join_node(node, 'Table', [])
        self.assertIsNone(result)


# ═══════════════════════════════════════════════════════════════════
# Union step
# ═══════════════════════════════════════════════════════════════════

class TestUnionNode(unittest.TestCase):
    """Test _parse_union_node."""

    def test_union_two_tables(self):
        node = {}
        result = _parse_union_node(node, ['TableA', 'TableB'])
        self.assertIsNotNone(result)
        assert result is not None
        step_name, step_expr = result
        self.assertIn('Table.Combine', step_expr)

    def test_empty_tables_returns_none(self):
        result = _parse_union_node({}, [])
        self.assertIsNone(result)


# ═══════════════════════════════════════════════════════════════════
# Pivot step
# ═══════════════════════════════════════════════════════════════════

class TestPivotNode(unittest.TestCase):
    """Test _parse_pivot_node."""

    def test_unpivot(self):
        node = {
            'pivotType': 'columnsToRows',
            'pivotFields': [{'name': 'Q1'}, {'name': 'Q2'}],
            'pivotValuesName': 'Value',
            'pivotNamesName': 'Quarter',
        }
        result = _parse_pivot_node(node)
        self.assertIsNotNone(result)
        assert result is not None
        _, expr = result
        self.assertIn('Unpivot', expr)

    def test_pivot(self):
        node = {
            'pivotType': 'rowsToColumns',
            'pivotKeyField': {'name': 'Category'},
            'pivotValueField': {'name': 'Sales'},
            'aggregation': 'SUM',
        }
        result = _parse_pivot_node(node)
        self.assertIsNotNone(result)
        assert result is not None
        _, expr = result
        self.assertIn('Pivot', expr)

    def test_unknown_pivot_type_returns_none(self):
        result = _parse_pivot_node({'pivotType': 'somethingElse'})
        self.assertIsNone(result)


# ═══════════════════════════════════════════════════════════════════
# Input node parsing
# ═══════════════════════════════════════════════════════════════════

class TestParseInputNode(unittest.TestCase):
    """Test _parse_input_node."""

    def test_csv_input(self):
        node = _input_node('sales', 'c1')
        connections = {
            'c1': {'connectionAttributes': {'class': 'csv', 'filename': 'sales.csv'}},
        }
        conn, table = _parse_input_node(node, connections)
        self.assertEqual(conn['type'], 'textscan')
        self.assertEqual(table['name'], 'sales')
        self.assertEqual(len(table['columns']), 3)

    def test_postgres_input(self):
        node = {
            'baseType': 'input',
            'nodeType': '.v1.LoadSql',
            'name': 'Orders',
            'connectionId': 'c1',
            'connectionAttributes': {'table': 'public.orders'},
            'fields': [{'name': 'id', 'type': 'integer'}],
            'nextNodes': [],
        }
        connections = {
            'c1': {'connectionAttributes': {
                'class': 'postgres',
                'server': 'localhost',
                'dbname': 'mydb',
            }},
        }
        conn, table = _parse_input_node(node, connections)
        self.assertEqual(conn['type'], 'postgres')
        self.assertEqual(conn['details']['server'], 'localhost')
        self.assertEqual(conn['details']['database'], 'mydb')


# ═══════════════════════════════════════════════════════════════════
# M table ref cleaning
# ═══════════════════════════════════════════════════════════════════

class TestCleanMTableRef(unittest.TestCase):
    """Test _clean_m_table_ref."""

    def test_strips_csv_extension(self):
        self.assertEqual(_clean_m_table_ref('sales.csv'), 'sales')

    def test_strips_xlsx_extension(self):
        self.assertEqual(_clean_m_table_ref('data.xlsx'), 'data')

    def test_replaces_spaces(self):
        self.assertEqual(_clean_m_table_ref('my table'), 'my_table')

    def test_no_extension(self):
        self.assertEqual(_clean_m_table_ref('RawTable'), 'RawTable')


# ═══════════════════════════════════════════════════════════════════
# Merge prep with workbook
# ═══════════════════════════════════════════════════════════════════

class TestMergePrepWithWorkbook(unittest.TestCase):
    """Test merge_prep_with_workbook."""

    def _run_merge(self, prep, twb):
        """Run merge_prep_with_workbook with stdout redirected to avoid
        Unicode encoding errors on Windows cp1252 consoles."""
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            return merge_prep_with_workbook(prep, twb)
        finally:
            sys.stdout = old_stdout

    def test_no_prep_data_returns_combined(self):
        prep = [{'name': 'prep.Out', 'tables': [{'name': 'Out'}],
                 'm_query_override': ''}]
        twb = [{'name': 'ds1', 'tables': [{'name': 'T1'}]}]
        result = self._run_merge(prep, twb)
        # With no m_query_override, prep is appended
        self.assertGreaterEqual(len(result), 1)

    def test_matching_table_merges_m_query(self):
        prep = [{'name': 'prep.Orders', 'caption': 'Orders',
                 'tables': [{'name': 'Orders'}],
                 'm_query_override': 'let Source = Csv.Document() in Source'}]
        twb = [{'name': 'ds1', 'tables': [{'name': 'Orders'}]}]
        result = self._run_merge(prep, twb)
        # TWB datasource should have the override
        ds = result[0]
        self.assertIn('m_query_overrides', ds)
        self.assertIn('Orders', ds['m_query_overrides'])

    def test_unmatched_prep_added_standalone(self):
        prep = [{'name': 'prep.NewTable', 'caption': 'NewTable',
                 'tables': [{'name': 'NewTable'}],
                 'm_query_override': 'let Source = #table({}) in Source'}]
        twb = [{'name': 'ds1', 'tables': [{'name': 'OtherTable'}]}]
        result = self._run_merge(prep, twb)
        # Should have both the TWB datasource and the Prep standalone
        self.assertEqual(len(result), 2)


# ═══════════════════════════════════════════════════════════════════
# End-to-end flow parsing (minimal flow)
# ═══════════════════════════════════════════════════════════════════

class TestParseFlowEndToEnd(unittest.TestCase):
    """Test parse_prep_flow with a minimal synthetic flow."""

    def test_simple_input_to_output(self):

        flow = {
            'nodes': {
                'n1': {
                    'baseType': 'input',
                    'nodeType': '.v1.LoadCsv',
                    'name': 'Sales',
                    'connectionId': 'c1',
                    'connectionAttributes': {'class': 'csv', 'filename': 'sales.csv'},
                    'fields': [
                        {'name': 'Product', 'type': 'string'},
                        {'name': 'Amount', 'type': 'real'},
                    ],
                    'nextNodes': [{'nextNodeId': 'n2'}],
                },
                'n2': {
                    'baseType': 'output',
                    'nodeType': '.v1.PublishExtract',
                    'name': 'SalesOut',
                    'nextNodes': [],
                },
            },
            'connections': {
                'c1': {'connectionAttributes': {'class': 'csv', 'filename': 'sales.csv'}},
            },
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.tfl', delete=False,
                                         encoding='utf-8') as f:
            json.dump(flow, f)
            path = f.name

        try:
            # Suppress print output
            _old = sys.stdout
            sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding='utf-8')
            try:
                result = parse_prep_flow(path)
            finally:
                sys.stdout = _old

            self.assertIsInstance(result, list)
            self.assertGreater(len(result), 0)
            ds = result[0]
            self.assertIn('m_query_override', ds)
            self.assertTrue(ds['m_query_override'])  # Should have M query
        finally:
            os.unlink(path)


# ═══════════════════════════════════════════════════════════════════
# Type mapping
# ═══════════════════════════════════════════════════════════════════

class TestPrepTypeMaps(unittest.TestCase):
    """Test mapping dictionaries."""

    def test_connection_map_coverage(self):
        # Core connectors should be mapped
        for key in ['csv', 'excel', 'sqlserver', 'postgres', 'mysql', 'bigquery']:
            self.assertIn(key, _PREP_CONNECTION_MAP, f'Missing connector: {key}')

    def test_type_map_coverage(self):
        for key in ['string', 'integer', 'real', 'date', 'datetime', 'boolean']:
            self.assertIn(key, _PREP_TYPE_MAP, f'Missing type: {key}')

    def test_agg_map_coverage(self):
        for key in ['SUM', 'AVG', 'COUNT', 'COUNTD', 'MIN', 'MAX']:
            self.assertIn(key, _PREP_AGG_MAP, f'Missing agg: {key}')

    def test_join_map_coverage(self):
        for key in ['inner', 'left', 'right', 'full', 'leftOnly', 'rightOnly']:
            self.assertIn(key, _PREP_JOIN_MAP, f'Missing join type: {key}')


# ═══════════════════════════════════════════════════════════════════
# Additional clean action coverage (uncovered action types)
# ═══════════════════════════════════════════════════════════════════

class TestCleanActionsExtended(unittest.TestCase):
    """Cover _convert_action_to_m_step paths not tested by TestCleanActions."""

    def _step(self, action_type, action_dict):
        """Call _convert_action_to_m_step directly."""
        return _convert_action_to_m_step(action_type, action_dict, {})

    # --- FilterOperation ---
    def test_filter_operation_keep(self):
        step = self._step('FilterOperation', {
            'filterExpression': '[Amount] > 100', 'filterType': 'keep'})
        self.assertIsNotNone(step)
        _, expr = step
        self.assertIn('Table.SelectRows', expr)
        self.assertNotIn('not', expr)

    def test_filter_operation_remove(self):
        step = self._step('FilterOperation', {
            'filterExpression': '[Status] = "Deleted"', 'filterType': 'remove'})
        self.assertIsNotNone(step)
        _, expr = step
        self.assertIn('not', expr)

    def test_filter_operation_counter_increments(self):
        counter = {}
        s1 = _convert_action_to_m_step('FilterOperation',
                                        {'filterExpression': '[X]>1'}, counter)
        s2 = _convert_action_to_m_step('FilterOperation',
                                        {'filterExpression': '[Y]>2'}, counter)
        self.assertIsNotNone(s1)
        self.assertIsNotNone(s2)
        self.assertNotEqual(s1[0], s2[0])  # distinct step names

    # --- FilterRange ---
    def test_filter_range(self):
        step = self._step('FilterRange', {
            'columnName': 'Price', 'min': 10, 'max': 100})
        self.assertIsNotNone(step)

    def test_filter_range_no_column(self):
        step = self._step('FilterRange', {'min': 0, 'max': 10})
        self.assertIsNone(step)

    # --- ReplaceNulls ---
    def test_replace_nulls(self):
        step = self._step('ReplaceNulls', {'columnName': 'Region', 'replacement': 'Unknown'})
        self.assertIsNotNone(step)

    def test_replace_nulls_no_column(self):
        step = self._step('ReplaceNulls', {'replacement': 'X'})
        self.assertIsNone(step)

    # --- MergeColumns ---
    def test_merge_columns(self):
        step = self._step('MergeColumns', {
            'columns': ['First', 'Last'], 'separator': ' ', 'newColumnName': 'FullName'})
        self.assertIsNotNone(step)

    def test_merge_columns_no_columns(self):
        step = self._step('MergeColumns', {'columns': [], 'separator': ','})
        self.assertIsNone(step)

    # --- CleanOperation variants ---
    def test_clean_operation_upper(self):
        step = self._step('CleanOperation', {'columnName': 'Name', 'operation': 'upper'})
        self.assertIsNotNone(step)

    def test_clean_operation_lower(self):
        step = self._step('CleanOperation', {'columnName': 'Name', 'operation': 'lower'})
        self.assertIsNotNone(step)

    def test_clean_operation_proper(self):
        step = self._step('CleanOperation', {'columnName': 'Name', 'operation': 'proper'})
        self.assertIsNotNone(step)

    def test_clean_operation_removeletters(self):
        step = self._step('CleanOperation', {'columnName': 'Code', 'operation': 'removeletters'})
        self.assertIsNotNone(step)

    def test_clean_operation_no_column(self):
        step = self._step('CleanOperation', {'operation': 'trim'})
        self.assertIsNone(step)

    # --- FillValues up ---
    def test_fill_values_up(self):
        node = _clean_node(actions=[
            {'actionType': '.v1.FillValues', 'columnName': 'X', 'direction': 'up'},
        ])
        steps = _parse_clean_actions(node)
        self.assertEqual(len(steps), 1)
        _, expr = steps[0]
        self.assertIn('FillUp', expr)

    # --- ConditionalColumn ---
    def test_conditional_column(self):
        step = self._step('ConditionalColumn', {
            'newColumnName': 'Tier',
            'rules': [
                {'condition': '[Amount] > 1000', 'value': 'High'},
                {'condition': '[Amount] > 500', 'value': 'Medium'},
            ],
            'defaultValue': 'Low',
        })
        self.assertIsNotNone(step)
        # The generated M must NOT have double 'each' (each if each ...)
        name, expr = step
        self.assertNotIn('each if each', expr)
        # Must have proper if...then...else
        self.assertIn('if', expr)
        self.assertIn('then', expr)
        self.assertIn('else', expr)

    def test_conditional_column_no_rules(self):
        step = self._step('ConditionalColumn', {'newColumnName': 'X', 'rules': []})
        self.assertIsNone(step)

    # --- ExtractValues ---
    def test_extract_values(self):
        step = self._step('ExtractValues', {
            'columnName': 'Email', 'pattern': '@.*$', 'newColumnName': 'Domain'})
        self.assertIsNotNone(step)
        name, expr = step
        self.assertIn('AddColumn', expr)

    def test_extract_values_no_column(self):
        step = self._step('ExtractValues', {'pattern': '.*'})
        self.assertIsNone(step)

    def test_extract_values_counter(self):
        counter = {}
        s1 = _convert_action_to_m_step('ExtractValues',
                                        {'columnName': 'A', 'pattern': '.'}, counter)
        s2 = _convert_action_to_m_step('ExtractValues',
                                        {'columnName': 'B', 'pattern': '.'}, counter)
        self.assertNotEqual(s1[0], s2[0])

    # --- CustomCalculation ---
    def test_custom_calculation(self):
        step = self._step('CustomCalculation', {
            'columnName': 'Profit', 'expression': '[Sales] - [Cost]'})
        self.assertIsNotNone(step)

    def test_custom_calculation_default_name(self):
        step = self._step('CustomCalculation', {'expression': '42'})
        self.assertIsNotNone(step)

    # --- afterActionGroup ---
    def test_after_action_group_actions(self):
        """afterActionGroup actions should be included."""
        node = {
            'baseType': 'transform',
            'nodeType': '.v2018_3_3.SuperTransform',
            'name': 'Clean',
            'beforeActionGroup': {'actions': [
                {'actionType': '.v1.RemoveColumn', 'columnName': 'Drop1'},
            ]},
            'afterActionGroup': {'actions': [
                {'actionType': '.v1.RemoveColumn', 'columnName': 'Drop2'},
            ]},
            'nextNodes': [],
        }
        steps = _parse_clean_actions(node)
        self.assertEqual(len(steps), 2)


# ═══════════════════════════════════════════════════════════════════
# Transform node dispatch (process_transform_node branches)
# ═══════════════════════════════════════════════════════════════════

class TestProcessTransformNode(unittest.TestCase):
    """Test _process_transform_node and _process_prep_node dispatch branches."""

    def _suppress(self):
        """Redirect stdout to suppress print output."""
        import io as _io
        self._old_stdout = sys.stdout
        sys.stdout = _io.StringIO()

    def _restore(self):
        sys.stdout = self._old_stdout

    def setUp(self):
        self._suppress()

    def tearDown(self):
        self._restore()

    def _base_input_result(self, name='Input1'):
        """Return a basic node_results entry simulating an input node."""
        return {
            'connection': {'type': 'textscan', 'details': {}},
            'table': {'name': name, 'columns': []},
            'name': name,
            'm_query': 'let\n    Source = Csv.Document(File.Contents("data.csv"))\nin\n    Source',
            'fields': [{'name': 'ID', 'type': 'integer'}, {'name': 'Val', 'type': 'real'}],
        }

    # --- Aggregate ---
    def test_aggregate_transform(self):
        nid = 'agg1'
        node = {
            'baseType': 'transform', 'nodeType': '.v1.Aggregate', 'name': 'GroupBy',
            'groupByFields': [{'name': 'Region'}],
            'aggregateFields': [{'name': 'Sales', 'aggregation': 'SUM', 'newColumnName': 'TotalSales'}],
            'nextNodes': [],
        }
        nodes = {'inp': _input_node(next_ids=[nid]), nid: node}
        node_results = {'inp': self._base_input_result()}
        secondary = set()
        _process_transform_node(nid, node, nodes, ['inp'], 'Aggregate',
                                node_results, secondary, 'GroupBy')
        self.assertIn(nid, node_results)
        self.assertIn('Table.Group', node_results[nid]['m_query'])

    # --- Join with leftNodeId / rightNodeId ---
    def test_join_transform_with_explicit_ids(self):
        nid = 'join1'
        node = {
            'baseType': 'transform', 'nodeType': '.v1.Join', 'name': 'JoinStep',
            'leftNodeId': 'left', 'rightNodeId': 'right',
            'joinType': 'inner',
            'joinConditions': [{'leftColumn': 'ID', 'rightColumn': 'CID'}],
            'nextNodes': [],
        }
        nodes = {'left': _input_node('Left'), 'right': _input_node('Right'), nid: node}
        node_results = {
            'left': self._base_input_result('Left'),
            'right': {**self._base_input_result('Right'),
                      'fields': [{'name': 'CID'}, {'name': 'Name'}]},
        }
        secondary = set()
        _process_transform_node(nid, node, nodes, ['left', 'right'], 'Join',
                                node_results, secondary, 'JoinStep')
        self.assertIn(nid, node_results)
        self.assertIn('right', secondary)  # right branch marked secondary

    def test_join_transform_fallback_single_upstream(self):
        """Join with only 1 upstream, no leftNodeId → left_id = upstream[0]."""
        nid = 'join1'
        node = {
            'baseType': 'transform', 'nodeType': '.v1.Join', 'name': 'JoinStep',
            'joinType': 'left',
            'joinConditions': [{'leftColumn': 'ID', 'rightColumn': 'CID'}],
            'nextNodes': [],
        }
        nodes = {'inp': _input_node(next_ids=[nid]), nid: node}
        node_results = {'inp': self._base_input_result()}
        secondary = set()
        _process_transform_node(nid, node, nodes, ['inp'], 'Join',
                                node_results, secondary, 'JoinStep')
        self.assertIn(nid, node_results)

    # --- Union ---
    def test_union_transform(self):
        nid = 'union1'
        node = {'baseType': 'transform', 'nodeType': '.v1.Union', 'name': 'UnionStep',
                'nextNodes': []}
        nodes = {'a': _input_node('A'), 'b': _input_node('B'), nid: node}
        node_results = {
            'a': self._base_input_result('A'),
            'b': self._base_input_result('B'),
        }
        secondary = set()
        _process_transform_node(nid, node, nodes, ['a', 'b'], 'Union',
                                node_results, secondary, 'UnionStep')
        self.assertIn(nid, node_results)
        self.assertIn('Table.Combine', node_results[nid]['m_query'])
        # Union marks all upstream as secondary
        self.assertIn('a', secondary)
        self.assertIn('b', secondary)

    # --- Pivot ---
    def test_pivot_transform_unpivot(self):
        nid = 'piv1'
        node = {
            'baseType': 'transform', 'nodeType': '.v1.Pivot', 'name': 'Unpivot',
            'pivotType': 'columnsToRows',
            'pivotFields': [{'name': 'Q1'}, {'name': 'Q2'}],
            'pivotValuesName': 'Value', 'pivotNamesName': 'Quarter',
            'nextNodes': [],
        }
        nodes = {'inp': _input_node(next_ids=[nid]), nid: node}
        node_results = {'inp': self._base_input_result()}
        secondary = set()
        _process_transform_node(nid, node, nodes, ['inp'], 'Pivot',
                                node_results, secondary, 'Unpivot')
        self.assertIn(nid, node_results)
        self.assertIn('Unpivot', node_results[nid]['m_query'])

    # --- Script ---
    def test_script_transform(self):
        nid = 'scr1'
        node = {
            'baseType': 'transform', 'nodeType': '.v1.RunScript', 'name': 'PyScript',
            'scriptLanguage': 'Python', 'nextNodes': [],
        }
        nodes = {'inp': _input_node(next_ids=[nid]), nid: node}
        node_results = {'inp': self._base_input_result()}
        secondary = set()
        _process_transform_node(nid, node, nodes, ['inp'], 'Script',
                                node_results, secondary, 'PyScript')
        self.assertIn(nid, node_results)
        self.assertIn('script_warning', node_results[nid]['m_query'])

    def test_run_script_variant(self):
        nid = 'scr2'
        node = {'baseType': 'transform', 'nodeType': '.v1.RunCommand', 'name': 'RCmd',
                'language': 'R', 'nextNodes': []}
        nodes = {'inp': _input_node(next_ids=[nid]), nid: node}
        node_results = {'inp': self._base_input_result()}
        _process_transform_node(nid, node, nodes, ['inp'], 'RunCommand',
                                node_results, set(), 'RCmd')
        self.assertIn(nid, node_results)

    # --- Prediction ---
    def test_prediction_transform(self):
        nid = 'pred1'
        node = {'baseType': 'transform', 'nodeType': '.v1.Prediction', 'name': 'ML',
                'nextNodes': []}
        nodes = {'inp': _input_node(next_ids=[nid]), nid: node}
        node_results = {'inp': self._base_input_result()}
        _process_transform_node(nid, node, nodes, ['inp'], 'Prediction',
                                node_results, set(), 'ML')
        self.assertIn(nid, node_results)
        self.assertIn('prediction_warning', node_results[nid]['m_query'])

    def test_tabpy_variant(self):
        nid = 'tp1'
        node = {'baseType': 'transform', 'nodeType': '.v1.TabPy', 'name': 'TabPy',
                'nextNodes': []}
        nodes = {'inp': _input_node(next_ids=[nid]), nid: node}
        node_results = {'inp': self._base_input_result()}
        _process_transform_node(nid, node, nodes, ['inp'], 'TabPy',
                                node_results, set(), 'TabPy')
        self.assertIn(nid, node_results)

    # --- CrossJoin ---
    def test_cross_join_transform(self):
        nid = 'cj1'
        node = {'baseType': 'transform', 'nodeType': '.v1.CrossJoin', 'name': 'Cross',
                'nextNodes': []}
        nodes = {'a': _input_node('A'), 'b': _input_node('B'), nid: node}
        node_results = {
            'a': self._base_input_result('A'),
            'b': self._base_input_result('B'),
        }
        secondary = set()
        _process_transform_node(nid, node, nodes, ['a', 'b'], 'CrossJoin',
                                node_results, secondary, 'Cross')
        self.assertIn(nid, node_results)
        self.assertIn('Table.Join', node_results[nid]['m_query'])
        self.assertIn('b', secondary)

    # --- PublishedDataSource ---
    def test_published_datasource_transform(self):
        nid = 'pub1'
        node = {'baseType': 'transform', 'nodeType': '.v1.LoadPublishedDataSource',
                'name': 'PubDS', 'publishedDatasourceName': 'SharedSales',
                'fields': [{'name': 'Revenue', 'type': 'real'}], 'nextNodes': []}
        nodes = {nid: node}
        node_results = {}
        _process_transform_node(nid, node, nodes, [], 'PublishedDataSource',
                                node_results, set(), 'PubDS')
        self.assertIn(nid, node_results)
        self.assertIn('SharedSales', node_results[nid]['m_query'])
        self.assertEqual(node_results[nid]['connection']['type'], 'published')

    def test_load_published_datasource_variant(self):
        nid = 'pub2'
        node = {'baseType': 'transform', 'nodeType': '.v1.LoadPublishedDataSource',
                'name': 'PDS', 'datasourceName': 'MyDS', 'nextNodes': []}
        nodes = {nid: node}
        node_results = {}
        _process_transform_node(nid, node, nodes, [], 'LoadPublishedDataSource',
                                node_results, set(), 'PDS')
        self.assertIn(nid, node_results)
        self.assertIn('MyDS', node_results[nid]['m_query'])

    # --- Unknown transform → pass through ---
    def test_unknown_transform_passthrough(self):
        nid = 'unk1'
        node = {'baseType': 'transform', 'nodeType': '.v1.FutureStep', 'name': 'Future',
                'nextNodes': []}
        nodes = {'inp': _input_node(next_ids=[nid]), nid: node}
        node_results = {'inp': self._base_input_result()}
        _process_transform_node(nid, node, nodes, ['inp'], 'FutureStep',
                                node_results, set(), 'Future')
        self.assertIn(nid, node_results)
        self.assertEqual(node_results[nid]['name'], 'Future')


# ═══════════════════════════════════════════════════════════════════
# Output node handling (_process_prep_node)
# ═══════════════════════════════════════════════════════════════════

class TestProcessPrepNode(unittest.TestCase):
    """Test _process_prep_node for output nodes."""

    def setUp(self):
        self._old = sys.stdout
        sys.stdout = io.StringIO()

    def tearDown(self):
        sys.stdout = self._old

    def test_output_node_copies_upstream(self):
        nodes = {
            'inp': _input_node('Data', next_ids=['out']),
            'out': _output_node('FinalOutput'),
        }
        connections = {'conn1': {'connectionAttributes': {'class': 'csv', 'filename': 'x.csv'}}}
        node_results = {}
        secondary = set()
        # Process input first
        _process_prep_node('inp', nodes, connections, node_results, secondary)
        self.assertIn('inp', node_results)
        # Then output
        _process_prep_node('out', nodes, connections, node_results, secondary)
        self.assertIn('out', node_results)
        self.assertTrue(node_results['out'].get('is_output'))
        self.assertEqual(node_results['out']['name'], 'FinalOutput')

    def test_output_node_no_upstream_skipped(self):
        """Output with no upstream in node_results is silently skipped."""
        nodes = {'out': _output_node('Orphan')}
        node_results = {}
        _process_prep_node('out', nodes, {}, node_results, set())
        self.assertNotIn('out', node_results)


# ═══════════════════════════════════════════════════════════════════
# _collect_prep_datasources
# ═══════════════════════════════════════════════════════════════════

class TestCollectPrepDatasources(unittest.TestCase):
    """Test _collect_prep_datasources secondary branches, output nodes, and leaf fallback."""

    def setUp(self):
        self._old = sys.stdout
        sys.stdout = io.StringIO()

    def tearDown(self):
        sys.stdout = self._old

    def _base_result(self, name, is_output=False, fields=None):
        return {
            'connection': {'type': 'textscan', 'details': {}},
            'table': {'name': name, 'columns': []},
            'name': name,
            'm_query': f'let Source = #"{name}" in Source',
            'fields': fields or [{'name': 'Col1', 'type': 'string'}],
            'is_output': is_output,
        }

    def test_secondary_branch_emitted(self):
        """Secondary branch nodes (right side of joins) are emitted first."""
        sorted_ids = ['left', 'right', 'join', 'out']
        nodes = {
            'left': _input_node('Left'),
            'right': _input_node('Right'),
            'join': {'baseType': 'transform', 'nextNodes': [{'nextNodeId': 'out'}]},
            'out': _output_node('Result'),
        }
        node_results = {
            'left': self._base_result('Left'),
            'right': self._base_result('Right'),
            'join': self._base_result('Join'),
            'out': self._base_result('Result', is_output=True),
        }
        secondary = {'right'}
        ds = _collect_prep_datasources(sorted_ids, nodes, node_results, secondary)
        # Should have secondary (Right) + output (Result)
        self.assertEqual(len(ds), 2)
        names = [d['name'] for d in ds]
        self.assertTrue(any('Right' in n for n in names))

    def test_output_nodes_collected(self):
        sorted_ids = ['inp', 'out']
        nodes = {'inp': _input_node('Data'), 'out': _output_node('Out')}
        node_results = {
            'inp': self._base_result('Data'),
            'out': self._base_result('Out', is_output=True,
                                     fields=[{'name': 'F1', 'type': 'integer'}]),
        }
        ds = _collect_prep_datasources(sorted_ids, nodes, node_results, set())
        self.assertEqual(len(ds), 1)
        self.assertEqual(ds[0]['tables'][0]['columns'][0]['name'], 'F1')

    def test_leaf_fallback_when_no_outputs(self):
        """When no output nodes exist, leaf nodes (no nextNodes) are used."""
        sorted_ids = ['inp', 'clean']
        nodes = {
            'inp': _input_node('Data', next_ids=['clean']),
            'clean': {'baseType': 'transform', 'nextNodes': [],
                      'nodeType': '.v1.SuperTransform', 'name': 'Clean'},
        }
        node_results = {
            'inp': self._base_result('Data'),
            'clean': self._base_result('Cleaned'),
        }
        ds = _collect_prep_datasources(sorted_ids, nodes, node_results, set())
        # clean has no nextNodes and no is_output → leaf fallback
        self.assertGreater(len(ds), 0)

    def test_empty_results_returns_empty(self):
        ds = _collect_prep_datasources(['n1'], {'n1': _input_node()}, {}, set())
        self.assertEqual(ds, [])


# ═══════════════════════════════════════════════════════════════════
# Merge prep with workbook — extended coverage
# ═══════════════════════════════════════════════════════════════════

class TestMergePrepExtended(unittest.TestCase):
    """Extended merge_prep_with_workbook coverage."""

    def _run(self, prep, twb):
        old = sys.stdout
        sys.stdout = io.StringIO()
        try:
            return merge_prep_with_workbook(prep, twb)
        finally:
            sys.stdout = old

    def test_caption_based_matching(self):
        """Prep table matched via caption (not just table name)."""
        prep = [{'name': 'prep.Orders', 'caption': 'Sales Orders',
                 'tables': [{'name': 'Orders'}],
                 'm_query_override': 'let S = 1 in S'}]
        twb = [{'name': 'ds1', 'tables': [{'name': 'Sales_Orders'}]}]
        result = self._run(prep, twb)
        # caption converted with replace(' ', '_') → 'Sales_Orders' matches
        ds = result[0]
        self.assertIn('m_query_overrides', ds)
        self.assertIn('Sales_Orders', ds['m_query_overrides'])

    def test_empty_prep_returns_twb(self):
        twb = [{'name': 'ds1', 'tables': [{'name': 'T'}]}]
        result = self._run([], twb)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], 'ds1')

    def test_multiple_matches(self):
        """Multiple TWB tables matching different Prep tables."""
        prep = [
            {'name': 'p1', 'caption': 'Orders', 'tables': [{'name': 'Orders'}],
             'm_query_override': 'let O = 1 in O'},
            {'name': 'p2', 'caption': 'Customers', 'tables': [{'name': 'Customers'}],
             'm_query_override': 'let C = 1 in C'},
        ]
        twb = [
            {'name': 'ds1', 'tables': [{'name': 'Orders'}]},
            {'name': 'ds2', 'tables': [{'name': 'Customers'}]},
        ]
        result = self._run(prep, twb)
        self.assertEqual(len(result), 2)
        self.assertIn('m_query_overrides', result[0])
        self.assertIn('m_query_overrides', result[1])


# ═══════════════════════════════════════════════════════════════════
# parse_prep_flow — extended end-to-end flows
# ═══════════════════════════════════════════════════════════════════

class TestParseFlowExtended(unittest.TestCase):
    """End-to-end parse_prep_flow with more complex topologies."""

    def _write_flow(self, flow_data):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.tfl', delete=False,
                                        encoding='utf-8')
        json.dump(flow_data, f)
        f.close()
        return f.name

    def _parse(self, path):
        old = sys.stdout
        sys.stdout = io.StringIO()
        try:
            return parse_prep_flow(path)
        finally:
            sys.stdout = old

    def test_empty_flow_returns_empty(self):
        path = self._write_flow({'nodes': {}, 'connections': {}})
        try:
            result = self._parse(path)
            self.assertEqual(result, [])
        finally:
            os.unlink(path)

    def test_input_clean_output_chain(self):
        flow = {
            'nodes': {
                'n1': {
                    'baseType': 'input', 'nodeType': '.v1.LoadCsv',
                    'name': 'Data', 'connectionId': 'c1',
                    'connectionAttributes': {'class': 'csv', 'filename': 'data.csv'},
                    'fields': [{'name': 'A', 'type': 'string'}],
                    'nextNodes': [{'nextNodeId': 'n2'}],
                },
                'n2': {
                    'baseType': 'transform', 'nodeType': '.v2018_3_3.SuperTransform',
                    'name': 'CleanStep',
                    'beforeActionGroup': {'actions': [
                        {'actionType': '.v1.RenameColumn', 'columnName': 'A', 'newColumnName': 'B'},
                    ]},
                    'nextNodes': [{'nextNodeId': 'n3'}],
                },
                'n3': {
                    'baseType': 'output', 'nodeType': '.v1.PublishExtract',
                    'name': 'Output', 'nextNodes': [],
                },
            },
            'connections': {
                'c1': {'connectionAttributes': {'class': 'csv', 'filename': 'data.csv'}},
            },
        }
        path = self._write_flow(flow)
        try:
            result = self._parse(path)
            self.assertGreater(len(result), 0)
            # Output should have M query with rename
            self.assertIn('RenameColumns', result[-1].get('m_query_override', ''))
        finally:
            os.unlink(path)

    def test_join_flow_emits_secondary_table(self):
        flow = {
            'nodes': {
                'left': {
                    'baseType': 'input', 'nodeType': '.v1.LoadCsv',
                    'name': 'Orders', 'connectionId': 'c1',
                    'connectionAttributes': {'class': 'csv', 'filename': 'orders.csv'},
                    'fields': [{'name': 'ID', 'type': 'integer'}, {'name': 'CustID', 'type': 'integer'}],
                    'nextNodes': [{'nextNodeId': 'join'}],
                },
                'right': {
                    'baseType': 'input', 'nodeType': '.v1.LoadCsv',
                    'name': 'Customers', 'connectionId': 'c2',
                    'connectionAttributes': {'class': 'csv', 'filename': 'customers.csv'},
                    'fields': [{'name': 'CustID', 'type': 'integer'}, {'name': 'Name', 'type': 'string'}],
                    'nextNodes': [{'nextNodeId': 'join'}],
                },
                'join': {
                    'baseType': 'transform', 'nodeType': '.v1.Join', 'name': 'JoinStep',
                    'joinType': 'inner',
                    'joinConditions': [{'leftColumn': 'CustID', 'rightColumn': 'CustID'}],
                    'nextNodes': [{'nextNodeId': 'out'}],
                },
                'out': {
                    'baseType': 'output', 'nodeType': '.v1.PublishExtract',
                    'name': 'JoinedOut', 'nextNodes': [],
                },
            },
            'connections': {
                'c1': {'connectionAttributes': {'class': 'csv', 'filename': 'orders.csv'}},
                'c2': {'connectionAttributes': {'class': 'csv', 'filename': 'customers.csv'}},
            },
        }
        path = self._write_flow(flow)
        try:
            result = self._parse(path)
            # Should have secondary (Customers) + output (JoinedOut)
            self.assertGreaterEqual(len(result), 2)
        finally:
            os.unlink(path)


if __name__ == '__main__':
    unittest.main()
