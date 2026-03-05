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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tableau_export'))


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
        from prep_flow_parser import read_prep_flow
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
        from prep_flow_parser import read_prep_flow
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
            path = f.name
        try:
            with self.assertRaises(ValueError):
                read_prep_flow(path)
        finally:
            os.unlink(path)


# ═══════════════════════════════════════════════════════════════════
# Node type detection
# ═══════════════════════════════════════════════════════════════════

class TestGetNodeType(unittest.TestCase):
    """Test _get_node_type extraction."""

    def test_versioned_node_type(self):
        from prep_flow_parser import _get_node_type
        node = {'nodeType': '.v2018_3_3.SuperTransform'}
        self.assertEqual(_get_node_type(node), 'SuperTransform')

    def test_simple_node_type(self):
        from prep_flow_parser import _get_node_type
        node = {'nodeType': '.v1.LoadCsv'}
        self.assertEqual(_get_node_type(node), 'LoadCsv')

    def test_empty_node_type(self):
        from prep_flow_parser import _get_node_type
        node = {'nodeType': ''}
        self.assertEqual(_get_node_type(node), '')


# ═══════════════════════════════════════════════════════════════════
# Topological sort
# ═══════════════════════════════════════════════════════════════════

class TestTopologicalSort(unittest.TestCase):
    """Test _topological_sort for DAG traversal."""

    def test_linear_chain(self):
        from prep_flow_parser import _topological_sort
        nodes = {
            'a': {'nextNodes': [{'nextNodeId': 'b'}]},
            'b': {'nextNodes': [{'nextNodeId': 'c'}]},
            'c': {'nextNodes': []},
        }
        result = _topological_sort(nodes)
        self.assertEqual(result, ['a', 'b', 'c'])

    def test_diamond_graph(self):
        from prep_flow_parser import _topological_sort
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
        from prep_flow_parser import _topological_sort
        nodes = {'a': {'nextNodes': []}}
        result = _topological_sort(nodes)
        self.assertEqual(result, ['a'])

    def test_empty_graph(self):
        from prep_flow_parser import _topological_sort
        result = _topological_sort({})
        self.assertEqual(result, [])


# ═══════════════════════════════════════════════════════════════════
# Expression conversion
# ═══════════════════════════════════════════════════════════════════

class TestConvertPrepExpression(unittest.TestCase):
    """Test _convert_prep_expression_to_m."""

    def test_if_then_else(self):
        from prep_flow_parser import _convert_prep_expression_to_m
        result = _convert_prep_expression_to_m('IF [X] > 10 THEN "High" ELSE "Low" END')
        self.assertIn('if', result)
        self.assertIn('then', result)
        self.assertIn('else', result)
        self.assertNotIn('END', result)

    def test_elseif_conversion(self):
        from prep_flow_parser import _convert_prep_expression_to_m
        result = _convert_prep_expression_to_m('IF [X] > 10 THEN "A" ELSEIF [X] > 5 THEN "B" ELSE "C" END')
        self.assertIn('else if', result)

    def test_logical_operators(self):
        from prep_flow_parser import _convert_prep_expression_to_m
        result = _convert_prep_expression_to_m('[A] > 1 AND [B] < 2 OR NOT [C]')
        self.assertIn('and', result)
        self.assertIn('or', result)
        self.assertIn('not', result)

    def test_comparison_operators(self):
        from prep_flow_parser import _convert_prep_expression_to_m
        result = _convert_prep_expression_to_m('[A] != [B] AND [C] == [D]')
        self.assertIn('<>', result)
        self.assertNotIn('!=', result)
        # == becomes = in M
        self.assertIn('=', result)

    def test_string_functions(self):
        from prep_flow_parser import _convert_prep_expression_to_m
        result = _convert_prep_expression_to_m('CONTAINS([Name], "test")')
        self.assertIn('Text.Contains', result)

    def test_len_function(self):
        from prep_flow_parser import _convert_prep_expression_to_m
        result = _convert_prep_expression_to_m('LEN([Name])')
        self.assertIn('Text.Length', result)

    def test_upper_lower(self):
        from prep_flow_parser import _convert_prep_expression_to_m
        self.assertIn('Text.Upper', _convert_prep_expression_to_m('UPPER([X])'))
        self.assertIn('Text.Lower', _convert_prep_expression_to_m('LOWER([X])'))

    def test_empty_returns_empty_string_literal(self):
        from prep_flow_parser import _convert_prep_expression_to_m
        result = _convert_prep_expression_to_m('')
        self.assertEqual(result, '""')

    def test_none_returns_empty_string_literal(self):
        from prep_flow_parser import _convert_prep_expression_to_m
        result = _convert_prep_expression_to_m(None)
        self.assertEqual(result, '""')

    def test_isnull_conversion(self):
        from prep_flow_parser import _convert_prep_expression_to_m
        result = _convert_prep_expression_to_m('ISNULL([X])')
        self.assertIn('null', result)


# ═══════════════════════════════════════════════════════════════════
# Clean action conversion
# ═══════════════════════════════════════════════════════════════════

class TestCleanActions(unittest.TestCase):
    """Test _parse_clean_actions and _convert_action_to_m_step."""

    def test_rename_column(self):
        from prep_flow_parser import _parse_clean_actions
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
        from prep_flow_parser import _parse_clean_actions
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
        from prep_flow_parser import _parse_clean_actions
        node = _clean_node(actions=[
            {'actionType': '.v1.RemoveColumn', 'columnName': 'DropMe'},
        ])
        steps = _parse_clean_actions(node)
        self.assertEqual(len(steps), 1)
        _, expr = steps[0]
        self.assertIn('RemoveColumns', expr)
        self.assertIn('DropMe', expr)

    def test_duplicate_column(self):
        from prep_flow_parser import _parse_clean_actions
        node = _clean_node(actions=[
            {'actionType': '.v1.DuplicateColumn', 'columnName': 'Col', 'newColumnName': 'Col_copy'},
        ])
        steps = _parse_clean_actions(node)
        self.assertEqual(len(steps), 1)
        _, expr = steps[0]
        self.assertIn('DuplicateColumn', expr)

    def test_change_column_type(self):
        from prep_flow_parser import _parse_clean_actions
        node = _clean_node(actions=[
            {'actionType': '.v1.ChangeColumnType', 'columnName': 'Amount', 'newType': 'integer'},
        ])
        steps = _parse_clean_actions(node)
        self.assertEqual(len(steps), 1)
        _, expr = steps[0]
        self.assertIn('TransformColumnTypes', expr)
        self.assertIn('number', expr)

    def test_filter_values_keep(self):
        from prep_flow_parser import _parse_clean_actions
        node = _clean_node(actions=[
            {'actionType': '.v1.FilterValues', 'columnName': 'Status',
             'values': ['Active', 'Pending'], 'filterType': 'keep'},
        ])
        steps = _parse_clean_actions(node)
        self.assertEqual(len(steps), 1)

    def test_filter_values_remove(self):
        from prep_flow_parser import _parse_clean_actions
        node = _clean_node(actions=[
            {'actionType': '.v1.FilterValues', 'columnName': 'Status',
             'values': ['Deleted'], 'filterType': 'remove'},
        ])
        steps = _parse_clean_actions(node)
        self.assertEqual(len(steps), 1)

    def test_replace_values(self):
        from prep_flow_parser import _parse_clean_actions
        node = _clean_node(actions=[
            {'actionType': '.v1.ReplaceValues', 'columnName': 'Region',
             'oldValue': 'NA', 'newValue': 'North America'},
        ])
        steps = _parse_clean_actions(node)
        self.assertEqual(len(steps), 1)
        _, expr = steps[0]
        self.assertIn('ReplaceValue', expr)

    def test_split_column(self):
        from prep_flow_parser import _parse_clean_actions
        node = _clean_node(actions=[
            {'actionType': '.v1.SplitColumn', 'columnName': 'FullName', 'delimiter': ' '},
        ])
        steps = _parse_clean_actions(node)
        self.assertEqual(len(steps), 1)
        _, expr = steps[0]
        self.assertIn('SplitColumn', expr)

    def test_add_column(self):
        from prep_flow_parser import _parse_clean_actions
        node = _clean_node(actions=[
            {'actionType': '.v1.AddColumn', 'columnName': 'Total',
             'expression': '[Amount] * 1.1'},
        ])
        steps = _parse_clean_actions(node)
        self.assertEqual(len(steps), 1)
        _, expr = steps[0]
        self.assertIn('AddColumn', expr)

    def test_clean_operation_trim(self):
        from prep_flow_parser import _parse_clean_actions
        node = _clean_node(actions=[
            {'actionType': '.v1.CleanOperation', 'columnName': 'Name', 'operation': 'trim'},
        ])
        steps = _parse_clean_actions(node)
        self.assertEqual(len(steps), 1)
        _, expr = steps[0]
        self.assertIn('Trim', expr)

    def test_fill_down(self):
        from prep_flow_parser import _parse_clean_actions
        node = _clean_node(actions=[
            {'actionType': '.v1.FillValues', 'columnName': 'Region', 'direction': 'down'},
        ])
        steps = _parse_clean_actions(node)
        self.assertEqual(len(steps), 1)
        _, expr = steps[0]
        self.assertIn('FillDown', expr)

    def test_fill_up(self):
        from prep_flow_parser import _parse_clean_actions
        node = _clean_node(actions=[
            {'actionType': '.v1.FillValues', 'columnName': 'Region', 'direction': 'up'},
        ])
        steps = _parse_clean_actions(node)
        self.assertEqual(len(steps), 1)
        _, expr = steps[0]
        self.assertIn('FillUp', expr)

    def test_group_replace(self):
        from prep_flow_parser import _parse_clean_actions
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
        from prep_flow_parser import _parse_clean_actions
        node = _clean_node(actions=[
            {'actionType': '.v1.FutureAction', 'columnName': 'X'},
        ])
        steps = _parse_clean_actions(node)
        self.assertEqual(len(steps), 0)

    def test_rename_flush_before_other_action(self):
        """Renames should flush before a non-rename action."""
        from prep_flow_parser import _parse_clean_actions
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
        from prep_flow_parser import _parse_aggregate_node
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
        from prep_flow_parser import _parse_aggregate_node
        node = {'groupByFields': [], 'aggregateFields': []}
        result = _parse_aggregate_node(node)
        self.assertIsNone(result)


# ═══════════════════════════════════════════════════════════════════
# Join step
# ═══════════════════════════════════════════════════════════════════

class TestJoinNode(unittest.TestCase):
    """Test _parse_join_node."""

    def test_inner_join(self):
        from prep_flow_parser import _parse_join_node
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
        from prep_flow_parser import _parse_join_node
        node = {'joinType': 'inner', 'joinConditions': []}
        result = _parse_join_node(node, 'Table', [])
        self.assertIsNone(result)


# ═══════════════════════════════════════════════════════════════════
# Union step
# ═══════════════════════════════════════════════════════════════════

class TestUnionNode(unittest.TestCase):
    """Test _parse_union_node."""

    def test_union_two_tables(self):
        from prep_flow_parser import _parse_union_node
        node = {}
        result = _parse_union_node(node, ['TableA', 'TableB'])
        self.assertIsNotNone(result)
        assert result is not None
        step_name, step_expr = result
        self.assertIn('Table.Combine', step_expr)

    def test_empty_tables_returns_none(self):
        from prep_flow_parser import _parse_union_node
        result = _parse_union_node({}, [])
        self.assertIsNone(result)


# ═══════════════════════════════════════════════════════════════════
# Pivot step
# ═══════════════════════════════════════════════════════════════════

class TestPivotNode(unittest.TestCase):
    """Test _parse_pivot_node."""

    def test_unpivot(self):
        from prep_flow_parser import _parse_pivot_node
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
        from prep_flow_parser import _parse_pivot_node
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
        from prep_flow_parser import _parse_pivot_node
        result = _parse_pivot_node({'pivotType': 'somethingElse'})
        self.assertIsNone(result)


# ═══════════════════════════════════════════════════════════════════
# Input node parsing
# ═══════════════════════════════════════════════════════════════════

class TestParseInputNode(unittest.TestCase):
    """Test _parse_input_node."""

    def test_csv_input(self):
        from prep_flow_parser import _parse_input_node
        node = _input_node('sales', 'c1')
        connections = {
            'c1': {'connectionAttributes': {'class': 'csv', 'filename': 'sales.csv'}},
        }
        conn, table = _parse_input_node(node, connections)
        self.assertEqual(conn['type'], 'textscan')
        self.assertEqual(table['name'], 'sales')
        self.assertEqual(len(table['columns']), 3)

    def test_postgres_input(self):
        from prep_flow_parser import _parse_input_node
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
        from prep_flow_parser import _clean_m_table_ref
        self.assertEqual(_clean_m_table_ref('sales.csv'), 'sales')

    def test_strips_xlsx_extension(self):
        from prep_flow_parser import _clean_m_table_ref
        self.assertEqual(_clean_m_table_ref('data.xlsx'), 'data')

    def test_replaces_spaces(self):
        from prep_flow_parser import _clean_m_table_ref
        self.assertEqual(_clean_m_table_ref('my table'), 'my_table')

    def test_no_extension(self):
        from prep_flow_parser import _clean_m_table_ref
        self.assertEqual(_clean_m_table_ref('RawTable'), 'RawTable')


# ═══════════════════════════════════════════════════════════════════
# Merge prep with workbook
# ═══════════════════════════════════════════════════════════════════

class TestMergePrepWithWorkbook(unittest.TestCase):
    """Test merge_prep_with_workbook."""

    def _run_merge(self, prep, twb):
        """Run merge_prep_with_workbook with stdout redirected to avoid
        Unicode encoding errors on Windows cp1252 consoles."""
        from prep_flow_parser import merge_prep_with_workbook
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
        import io
        from prep_flow_parser import parse_prep_flow

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
        from prep_flow_parser import _PREP_CONNECTION_MAP
        # Core connectors should be mapped
        for key in ['csv', 'excel', 'sqlserver', 'postgres', 'mysql', 'bigquery']:
            self.assertIn(key, _PREP_CONNECTION_MAP, f'Missing connector: {key}')

    def test_type_map_coverage(self):
        from prep_flow_parser import _PREP_TYPE_MAP
        for key in ['string', 'integer', 'real', 'date', 'datetime', 'boolean']:
            self.assertIn(key, _PREP_TYPE_MAP, f'Missing type: {key}')

    def test_agg_map_coverage(self):
        from prep_flow_parser import _PREP_AGG_MAP
        for key in ['SUM', 'AVG', 'COUNT', 'COUNTD', 'MIN', 'MAX']:
            self.assertIn(key, _PREP_AGG_MAP, f'Missing agg: {key}')

    def test_join_map_coverage(self):
        from prep_flow_parser import _PREP_JOIN_MAP
        for key in ['inner', 'left', 'right', 'full', 'leftOnly', 'rightOnly']:
            self.assertIn(key, _PREP_JOIN_MAP, f'Missing join type: {key}')


if __name__ == '__main__':
    unittest.main()
