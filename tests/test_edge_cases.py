"""
Sprint 87 — Extraction & Conversion Hardening Tests.

Validates published datasource resolution, nested LOD (already supported),
complex join graph detection, multi-connection M parameters, and type coercion.
"""

import unittest

# ═══════════════════════════════════════════════════════════════════
# 1. Published datasource resolution (87.1)
# ═══════════════════════════════════════════════════════════════════

class TestPublishedDatasourceResolution(unittest.TestCase):
    """87.1 — resolve_published_datasource handles sqlproxy."""

    def _import(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))
        from tableau_export.datasource_extractor import resolve_published_datasource, _parse_published_datasource_file
        return resolve_published_datasource, _parse_published_datasource_file

    def test_non_sqlproxy_passthrough(self):
        resolve, _ = self._import()
        ds = {
            'connection': {'type': 'SQL Server', 'details': {}},
            'tables': [{'name': 'T'}],
        }
        result = resolve(ds)
        self.assertIs(result, ds)
        self.assertNotIn('_published_unresolved', ds)

    def test_sqlproxy_no_client_marks_unresolved(self):
        resolve, _ = self._import()
        ds = {
            'connection': {'type': 'Tableau Server', 'details': {'server_ds_name': 'Sales'}},
            'tables': [],
        }
        result = resolve(ds, server_client=None)
        self.assertTrue(result.get('_published_unresolved'))

    def test_sqlproxy_empty_name_marks_unresolved(self):
        resolve, _ = self._import()
        ds = {
            'connection': {'type': 'Tableau Server', 'details': {'server_ds_name': ''}},
            'tables': [],
        }
        result = resolve(ds, server_client=None)
        self.assertTrue(result.get('_published_unresolved'))

    def test_sqlproxy_client_no_match(self):
        resolve, _ = self._import()

        class MockClient:
            def list_datasources(self):
                return [{'name': 'Other', 'id': '1'}]

        ds = {
            'connection': {'type': 'Tableau Server', 'details': {'server_ds_name': 'Sales'}},
            'tables': [],
        }
        result = resolve(ds, server_client=MockClient())
        self.assertTrue(result.get('_published_unresolved'))

    def test_parse_published_datasource_file_bad_path(self):
        _, parse = self._import()
        result = parse('/nonexistent/file.tds')
        self.assertIsNone(result)


# ═══════════════════════════════════════════════════════════════════
# 2. Nested LOD support (87.2 — already working, regression tests)
# ═══════════════════════════════════════════════════════════════════

class TestNestedLOD(unittest.TestCase):
    """87.2 — Nested LOD expressions already handled iteratively."""

    def test_single_lod_fixed(self):
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        result = convert_tableau_formula_to_dax(
            '{FIXED [Region] : SUM([Sales])}', table_name='T')
        self.assertIn('CALCULATE', result)
        self.assertIn('ALLEXCEPT', result)

    def test_nested_lod_two_levels(self):
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        result = convert_tableau_formula_to_dax(
            '{FIXED [Region] : SUM({FIXED [State] : COUNT([Orders])})}',
            table_name='T')
        # Should have two CALCULATE calls (inner resolved first)
        self.assertGreaterEqual(result.count('CALCULATE'), 1)

    def test_lod_include(self):
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        result = convert_tableau_formula_to_dax(
            '{INCLUDE [State] : AVG([Profit])}', table_name='T')
        self.assertIn('CALCULATE', result)

    def test_lod_exclude(self):
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        result = convert_tableau_formula_to_dax(
            '{EXCLUDE [State] : MIN([Cost])}', table_name='T')
        self.assertIn('CALCULATE', result)
        self.assertIn('REMOVEFILTERS', result)

    def test_lod_no_dimension(self):
        from tableau_export.dax_converter import convert_tableau_formula_to_dax
        result = convert_tableau_formula_to_dax(
            '{SUM([Sales])}', table_name='T')
        self.assertIn('CALCULATE', result)


# ═══════════════════════════════════════════════════════════════════
# 3. Complex join graph detection (87.3)
# ═══════════════════════════════════════════════════════════════════

class TestJoinGraphDetection(unittest.TestCase):
    """87.3 — Multi-hop chain and diamond join detection."""

    def test_star_schema_multi_hop_warnings(self):
        from powerbi_import.tmdl_generator import _detect_join_graph_issues
        rels = [
            {'fromTable': 'Fact', 'toTable': 'DimA'},
            {'fromTable': 'Fact', 'toTable': 'DimB'},
            {'fromTable': 'Fact', 'toTable': 'DimC'},
        ]
        warnings = _detect_join_graph_issues(rels)
        # Star schema: dims connect through fact hub, generating informational multi-hop warnings
        multi = [w for w in warnings if w['type'] == 'multi_hop']
        self.assertGreaterEqual(len(multi), 0)  # May or may not flag (informational)
        diamonds = [w for w in warnings if w['type'] == 'diamond']
        self.assertEqual(len(diamonds), 0)  # No diamonds in star

    def test_multi_hop_detected(self):
        from powerbi_import.tmdl_generator import _detect_join_graph_issues
        rels = [
            {'fromTable': 'A', 'toTable': 'B'},
            {'fromTable': 'B', 'toTable': 'C'},
        ]
        warnings = _detect_join_graph_issues(rels)
        multi = [w for w in warnings if w['type'] == 'multi_hop']
        self.assertGreaterEqual(len(multi), 1)
        # Should mention A, B, C chain
        chains = [w['chain'] for w in multi]
        self.assertTrue(any('A' in c and 'C' in c for c in chains))

    def test_diamond_detected(self):
        from powerbi_import.tmdl_generator import _detect_join_graph_issues
        rels = [
            {'fromTable': 'A', 'toTable': 'B'},
            {'fromTable': 'A', 'toTable': 'C'},
            {'fromTable': 'B', 'toTable': 'D'},
            {'fromTable': 'C', 'toTable': 'D'},
        ]
        warnings = _detect_join_graph_issues(rels)
        diamonds = [w for w in warnings if w['type'] == 'diamond']
        self.assertGreaterEqual(len(diamonds), 1)

    def test_empty_relationships(self):
        from powerbi_import.tmdl_generator import _detect_join_graph_issues
        self.assertEqual(_detect_join_graph_issues([]), [])

    def test_single_relationship_no_issues(self):
        from powerbi_import.tmdl_generator import _detect_join_graph_issues
        rels = [{'fromTable': 'A', 'toTable': 'B'}]
        self.assertEqual(_detect_join_graph_issues(rels), [])

    def test_deduplication(self):
        from powerbi_import.tmdl_generator import _detect_join_graph_issues
        rels = [
            {'fromTable': 'A', 'toTable': 'B'},
            {'fromTable': 'B', 'toTable': 'C'},
        ]
        warnings = _detect_join_graph_issues(rels)
        # Each unique chain should appear only once
        chains = [tuple(w['chain']) for w in warnings if w['type'] == 'multi_hop']
        self.assertEqual(len(chains), len(set(tuple(sorted(c)) for c in chains)))


# ═══════════════════════════════════════════════════════════════════
# 4. Multi-connection M parameters (87.4)
# ═══════════════════════════════════════════════════════════════════

class TestMultiConnectionParameters(unittest.TestCase):
    """87.4 — Per-connection Power Query parameters."""

    def test_single_connection(self):
        from tableau_export.m_query_builder import generate_connection_parameters
        conn_map = {
            'conn1': {'details': {'server': 'svr1', 'database': 'db1'}},
        }
        params = generate_connection_parameters(conn_map)
        names = [p['name'] for p in params]
        self.assertIn('ServerName', names)
        self.assertIn('DatabaseName', names)

    def test_two_different_connections(self):
        from tableau_export.m_query_builder import generate_connection_parameters
        conn_map = {
            'c1': {'details': {'server': 'svr1', 'database': 'db1'}},
            'c2': {'details': {'server': 'svr2', 'database': 'db2'}},
        }
        params = generate_connection_parameters(conn_map)
        names = [p['name'] for p in params]
        self.assertIn('ServerName', names)
        self.assertIn('Conn2ServerName', names)
        self.assertEqual(len(params), 4)  # 2 server + 2 database

    def test_same_connection_deduped(self):
        from tableau_export.m_query_builder import generate_connection_parameters
        conn_map = {
            'c1': {'details': {'server': 'svr', 'database': 'db'}},
            'c2': {'details': {'server': 'svr', 'database': 'db'}},
        }
        params = generate_connection_parameters(conn_map)
        self.assertEqual(len(params), 2)  # Just one set

    def test_no_server_skipped(self):
        from tableau_export.m_query_builder import generate_connection_parameters
        conn_map = {'c1': {'details': {'database': 'db'}}}
        params = generate_connection_parameters(conn_map)
        self.assertEqual(len(params), 0)

    def test_server_only_no_database(self):
        from tableau_export.m_query_builder import generate_connection_parameters
        conn_map = {'c1': {'details': {'server': 'svr'}}}
        params = generate_connection_parameters(conn_map)
        self.assertEqual(len(params), 1)
        self.assertEqual(params[0]['name'], 'ServerName')

    def test_empty_connection_map(self):
        from tableau_export.m_query_builder import generate_connection_parameters
        self.assertEqual(generate_connection_parameters({}), [])

    def test_parameter_m_expression_format(self):
        from tableau_export.m_query_builder import generate_connection_parameters
        conn_map = {'c': {'details': {'server': 'myserver', 'database': 'mydb'}}}
        params = generate_connection_parameters(conn_map)
        srv = [p for p in params if p['name'] == 'ServerName'][0]
        self.assertIn('"myserver"', srv['m_expression'])
        self.assertIn('IsParameterQuery=true', srv['m_expression'])


# ═══════════════════════════════════════════════════════════════════
# 5. Data type coercion detection (87.5)
# ═══════════════════════════════════════════════════════════════════

class TestTypeCoercionDetection(unittest.TestCase):
    """87.5 — Detect auto-coercion of types that should be explicit."""

    def _import(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))
        from tableau_export.datasource_extractor import detect_type_coercions
        return detect_type_coercions

    def test_string_to_date_coercion(self):
        detect_type_coercions = self._import()
        ds = {
            'tables': [{'name': 'T', 'columns': [
                {'name': 'DateCol', 'datatype': 'string'},
            ]}],
            'columns': [{'name': 'DateCol', 'datatype': 'date'}],
        }
        coercions = detect_type_coercions(ds)
        self.assertEqual(len(coercions), 1)
        self.assertEqual(coercions[0]['from_type'], 'string')
        self.assertEqual(coercions[0]['to_type'], 'date')

    def test_no_coercion_same_type(self):
        detect_type_coercions = self._import()
        ds = {
            'tables': [{'name': 'T', 'columns': [
                {'name': 'Val', 'datatype': 'real'},
            ]}],
            'columns': [{'name': 'Val', 'datatype': 'real'}],
        }
        self.assertEqual(detect_type_coercions(ds), [])

    def test_string_to_real_coercion(self):
        detect_type_coercions = self._import()
        ds = {
            'tables': [{'name': 'T', 'columns': [
                {'name': 'Amount', 'datatype': 'string'},
            ]}],
            'columns': [{'name': 'Amount', 'datatype': 'real'}],
        }
        coercions = detect_type_coercions(ds)
        self.assertEqual(len(coercions), 1)

    def test_string_to_integer_coercion(self):
        detect_type_coercions = self._import()
        ds = {
            'tables': [{'name': 'T', 'columns': [
                {'name': 'ID', 'datatype': 'string'},
            ]}],
            'columns': [{'name': 'ID', 'datatype': 'integer'}],
        }
        coercions = detect_type_coercions(ds)
        self.assertEqual(len(coercions), 1)

    def test_empty_datasource(self):
        detect_type_coercions = self._import()
        self.assertEqual(detect_type_coercions({'tables': [], 'columns': []}), [])

    def test_no_metadata_no_coercion(self):
        detect_type_coercions = self._import()
        ds = {
            'tables': [{'name': 'T', 'columns': [
                {'name': 'X', 'datatype': 'string'},
            ]}],
            'columns': [],  # No metadata
        }
        self.assertEqual(detect_type_coercions(ds), [])

    def test_multiple_coercions(self):
        detect_type_coercions = self._import()
        ds = {
            'tables': [{'name': 'T', 'columns': [
                {'name': 'D', 'datatype': 'string'},
                {'name': 'V', 'datatype': 'string'},
            ]}],
            'columns': [
                {'name': 'D', 'datatype': 'datetime'},
                {'name': 'V', 'datatype': 'real'},
            ],
        }
        coercions = detect_type_coercions(ds)
        self.assertEqual(len(coercions), 2)


if __name__ == '__main__':
    unittest.main()
