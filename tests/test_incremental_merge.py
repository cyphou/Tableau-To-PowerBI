"""Tests for Sprint 64 — Incremental Merge & Add-to-Model Workflow.

Covers:
- MergeManifest save/load round-trip
- build_merge_manifest() from merge results
- TMDL reverse-engineering (_parse_tmdl_table, _parse_tmdl_relationships, etc.)
- load_existing_model() from a TMDL directory
- add_to_model() incremental add
- remove_from_model() incremental remove
- diff_manifests() comparison
- Edge cases: duplicate add, remove non-existent, empty model
"""

import json
import os
import tempfile
import shutil
import unittest


class TestMergeManifest(unittest.TestCase):
    """Test MergeManifest dataclass, save/load, serialization."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix='test_manifest_')

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_manifest_to_dict_roundtrip(self):
        from powerbi_import.shared_model import MergeManifest
        m = MergeManifest(
            model_name='TestModel',
            workbooks=[{'name': 'wb1', 'path': '/tmp/wb1.twbx', 'hash': 'abc123',
                        'tables': ['Orders'], 'measures': ['Total Sales'],
                        'exclusive_tables': ['Orders']}],
            table_fingerprints={'Orders': 'fp123'},
            artifact_counts={'tables': 1, 'measures': 1, 'relationships': 0,
                             'rls_roles': 0, 'parameters': 0},
            merge_config_snapshot={'force': True},
            validation_score=95,
            merge_score=80,
            timestamp='2025-01-01T00:00:00Z',
        )
        d = m.to_dict()
        self.assertEqual(d['schema_version'], '1.0')
        self.assertEqual(d['model_name'], 'TestModel')
        self.assertEqual(len(d['workbooks']), 1)
        self.assertEqual(d['workbooks'][0]['name'], 'wb1')

        m2 = MergeManifest.from_dict(d)
        self.assertEqual(m2.model_name, 'TestModel')
        self.assertEqual(m2.validation_score, 95)
        self.assertEqual(m2.merge_score, 80)

    def test_manifest_save_and_load(self):
        from powerbi_import.shared_model import MergeManifest
        m = MergeManifest(
            model_name='SaveLoad',
            workbooks=[{'name': 'wb1', 'path': '', 'hash': '',
                        'tables': ['T1'], 'measures': [], 'exclusive_tables': ['T1']}],
            table_fingerprints={'T1': 'fp1'},
            artifact_counts={'tables': 1},
            timestamp='2025-01-01T00:00:00Z',
        )
        path = m.save(self.tmpdir)
        self.assertTrue(os.path.isfile(path))
        self.assertTrue(path.endswith('merge_manifest.json'))

        m2 = MergeManifest.load(path)
        self.assertEqual(m2.model_name, 'SaveLoad')
        self.assertEqual(m2.table_fingerprints, {'T1': 'fp1'})

    def test_manifest_load_from_directory(self):
        from powerbi_import.shared_model import MergeManifest
        m = MergeManifest(model_name='DirLoad', workbooks=[], timestamp='2025-01-01')
        m.save(self.tmpdir)

        m2 = MergeManifest.load(self.tmpdir)
        self.assertEqual(m2.model_name, 'DirLoad')

    def test_find_workbook(self):
        from powerbi_import.shared_model import MergeManifest
        m = MergeManifest(
            model_name='T',
            workbooks=[
                {'name': 'Sales', 'path': '', 'hash': '', 'tables': ['A'],
                 'measures': [], 'exclusive_tables': ['A']},
                {'name': 'Marketing', 'path': '', 'hash': '', 'tables': ['B'],
                 'measures': [], 'exclusive_tables': ['B']},
            ],
        )
        self.assertIsNotNone(m.find_workbook('Sales'))
        self.assertIsNotNone(m.find_workbook('sales'))  # case insensitive
        self.assertIsNone(m.find_workbook('Finance'))

    def test_exclusive_tables(self):
        from powerbi_import.shared_model import MergeManifest
        m = MergeManifest(
            model_name='T',
            workbooks=[
                {'name': 'WB1', 'tables': ['A', 'B'], 'exclusive_tables': ['A']},
            ],
        )
        self.assertEqual(m.exclusive_tables('WB1'), ['A'])
        self.assertEqual(m.exclusive_tables('NonExistent'), [])

    def test_manifest_schema_version(self):
        from powerbi_import.shared_model import MergeManifest
        m = MergeManifest(model_name='V')
        d = m.to_dict()
        self.assertEqual(d['schema_version'], '1.0')


class TestBuildMergeManifest(unittest.TestCase):
    """Test build_merge_manifest() from merge results."""

    def test_build_manifest_basic(self):
        from powerbi_import.shared_model import (
            build_merge_manifest, MergeAssessment
        )
        extracted1 = {
            'datasources': [{
                'connection': {'type': 'sqlserver', 'details': {'server': 'srv', 'database': 'db'}},
                'tables': [{'name': 'Orders', 'type': 'table', 'columns': []}],
            }],
            'calculations': [
                {'caption': 'Total', '_classification': 'measure', 'role': 'measure'}
            ],
        }
        extracted2 = {
            'datasources': [{
                'connection': {'type': 'sqlserver', 'details': {'server': 'srv', 'database': 'db'}},
                'tables': [{'name': 'Products', 'type': 'table', 'columns': []}],
            }],
            'calculations': [],
        }
        all_extracted = [extracted1, extracted2]
        workbook_names = ['WB1', 'WB2']

        merged = {
            'datasources': [{
                'connection': {'type': 'sqlserver', 'details': {'server': 'srv', 'database': 'db'}},
                'tables': [
                    {'name': 'Orders', 'type': 'table', 'columns': []},
                    {'name': 'Products', 'type': 'table', 'columns': []},
                ],
                'relationships': [],
            }],
            'calculations': [
                {'caption': 'Total', '_classification': 'measure', 'role': 'measure'}
            ],
            'parameters': [],
            'user_filters': [],
        }

        assessment = MergeAssessment(workbooks=workbook_names, merge_score=75)

        manifest = build_merge_manifest(
            model_name='TestModel',
            all_extracted=all_extracted,
            workbook_names=workbook_names,
            workbook_paths=None,
            merged=merged,
            assessment=assessment,
            validation_score=90,
        )

        self.assertEqual(manifest.model_name, 'TestModel')
        self.assertEqual(len(manifest.workbooks), 2)
        self.assertEqual(manifest.workbooks[0]['name'], 'WB1')
        self.assertEqual(manifest.validation_score, 90)
        self.assertEqual(manifest.merge_score, 75)
        self.assertEqual(manifest.artifact_counts['tables'], 2)
        self.assertEqual(manifest.artifact_counts['measures'], 1)
        self.assertTrue(manifest.timestamp)

    def test_build_manifest_with_shared_tables(self):
        """Shared tables should not be in exclusive_tables."""
        from powerbi_import.shared_model import (
            build_merge_manifest, MergeAssessment
        )
        shared_table = {'name': 'DimDate', 'type': 'table', 'columns': []}
        ds = {
            'connection': {'type': 'sqlserver', 'details': {'server': 's', 'database': 'd'}},
            'tables': [shared_table],
        }
        ex1 = {'datasources': [ds], 'calculations': []}
        ex2 = {'datasources': [ds], 'calculations': []}

        merged = {'datasources': [ds], 'calculations': [], 'parameters': [], 'user_filters': []}
        assessment = MergeAssessment(workbooks=['A', 'B'], merge_score=90)

        m = build_merge_manifest('M', [ex1, ex2], ['A', 'B'], None, merged, assessment)
        # DimDate is shared, so exclusive_tables should be empty for both
        self.assertEqual(m.workbooks[0]['exclusive_tables'], [])
        self.assertEqual(m.workbooks[1]['exclusive_tables'], [])


class TestTMDLParsing(unittest.TestCase):
    """Test TMDL reverse-engineering functions."""

    def test_parse_tmdl_table_basic(self):
        from powerbi_import.shared_model import _parse_tmdl_table
        tmdl = """\
table Orders
\tlineageTag: abc-123

\tcolumn OrderID
\t\tdataType: int64
\t\tlineageTag: col-1
\t\tsummarizeBy: none
\t\tsourceColumn: OrderID

\tcolumn Amount
\t\tdataType: double
\t\tlineageTag: col-2
\t\tsummarizeBy: sum
\t\tsourceColumn: Amount

\tmeasure 'Total Sales' = SUM('Orders'[Amount])
\t\tformatString: $#,##0.00
\t\tdisplayFolder: Measures
\t\tlineageTag: meas-1

\tannotation PBI_ResultType = Table
"""
        result = _parse_tmdl_table(tmdl)
        self.assertEqual(result['name'], 'Orders')
        self.assertEqual(len(result['columns']), 2)
        self.assertEqual(result['columns'][0]['name'], 'OrderID')
        self.assertEqual(result['columns'][0]['dataType'], 'int64')
        self.assertEqual(result['columns'][1]['name'], 'Amount')
        self.assertEqual(len(result['measures']), 1)
        self.assertEqual(result['measures'][0]['name'], 'Total Sales')
        self.assertEqual(result['measures'][0]['expression'], "SUM('Orders'[Amount])")
        self.assertEqual(result['measures'][0]['formatString'], '$#,##0.00')

    def test_parse_tmdl_calculated_column(self):
        from powerbi_import.shared_model import _parse_tmdl_table
        tmdl = """\
table Products
\tlineageTag: abc-456

\tcolumn IsActive = IF([Status] = "Active", TRUE(), FALSE())
\t\tdataType: boolean
\t\tlineageTag: calc-1
\t\tsummarizeBy: none

\tannotation PBI_ResultType = Table
"""
        result = _parse_tmdl_table(tmdl)
        self.assertEqual(len(result['columns']), 1)
        col = result['columns'][0]
        self.assertEqual(col['name'], 'IsActive')
        self.assertTrue(col['isCalculated'])
        self.assertIn('IF([Status]', col['expression'])

    def test_parse_tmdl_multiline_measure(self):
        from powerbi_import.shared_model import _parse_tmdl_table
        tmdl = """\
table Facts
\tlineageTag: abc

\tmeasure Complex = ```
\t\t\tVAR x = SUM([Amount])
\t\t\tRETURN x * 1.1
\t\t\t```
\t\tformatString: 0.00
\t\tlineageTag: m1

\tannotation PBI_ResultType = Table
"""
        result = _parse_tmdl_table(tmdl)
        self.assertEqual(len(result['measures']), 1)
        m = result['measures'][0]
        self.assertEqual(m['name'], 'Complex')
        self.assertIn('VAR x', m['expression'])
        self.assertIn('RETURN', m['expression'])

    def test_parse_tmdl_hierarchy(self):
        from powerbi_import.shared_model import _parse_tmdl_table
        tmdl = """\
table DimGeo
\tlineageTag: abc

\thierarchy Geography
\t\tlevel Country
\t\t\tcolumn: Country
\t\tlevel State
\t\t\tcolumn: State
\t\tlevel City
\t\t\tcolumn: City

\tannotation PBI_ResultType = Table
"""
        result = _parse_tmdl_table(tmdl)
        self.assertEqual(len(result['hierarchies']), 1)
        h = result['hierarchies'][0]
        self.assertEqual(h['name'], 'Geography')
        self.assertEqual(len(h['levels']), 3)
        self.assertEqual(h['levels'][0]['name'], 'Country')
        self.assertEqual(h['levels'][2]['name'], 'City')

    def test_parse_tmdl_column_flags(self):
        from powerbi_import.shared_model import _parse_tmdl_table
        tmdl = """\
table Dim
\tlineageTag: abc

\tcolumn CityName
\t\tdataType: string
\t\tsourceColumn: CityName
\t\tisHidden
\t\tisKey
\t\tdataCategory: City
\t\tdescription: The city name
\t\tlineageTag: c1
\t\tsummarizeBy: none

\tannotation PBI_ResultType = Table
"""
        result = _parse_tmdl_table(tmdl)
        col = result['columns'][0]
        self.assertTrue(col['isHidden'])
        self.assertTrue(col['isKey'])
        self.assertEqual(col['dataCategory'], 'City')
        self.assertEqual(col['description'], 'The city name')

    def test_parse_relationships(self):
        from powerbi_import.shared_model import _parse_tmdl_relationships
        tmdl = """\
relationship abc-123
\tfromColumn: Orders.CustomerID
\ttoColumn: Customers.CustomerID
\tcrossFilteringBehavior: oneDirection

relationship def-456
\tfromColumn: Orders.ProductID
\ttoColumn: Products.ProductID
\tfromCardinality: many
\ttoCardinality: many
\tcrossFilteringBehavior: bothDirections
\tisActive: false
"""
        result = _parse_tmdl_relationships(tmdl)
        self.assertEqual(len(result), 2)

        r1 = result[0]
        self.assertEqual(r1['fromTable'], 'Orders')
        self.assertEqual(r1['fromColumn'], 'CustomerID')
        self.assertEqual(r1['toTable'], 'Customers')
        self.assertEqual(r1['toColumn'], 'CustomerID')
        self.assertEqual(r1['crossFilteringBehavior'], 'oneDirection')
        self.assertTrue(r1['isActive'])

        r2 = result[1]
        self.assertEqual(r2['fromCardinality'], 'many')
        self.assertEqual(r2['toCardinality'], 'many')
        self.assertFalse(r2['isActive'])

    def test_parse_roles(self):
        from powerbi_import.shared_model import _parse_tmdl_roles
        tmdl = """\
role 'Sales Team'
\tmodelPermission: read
\tannotation MigrationNote = "From Tableau user filter"

\ttablePermission Orders
\t\tfilterExpression = [Region] = "West"

role Admins
\tmodelPermission: read
"""
        result = _parse_tmdl_roles(tmdl)
        self.assertEqual(len(result), 2)

        r1 = result[0]
        self.assertEqual(r1['name'], 'Sales Team')
        self.assertEqual(r1['modelPermission'], 'read')
        self.assertEqual(r1['_migration_note'], 'From Tableau user filter')
        self.assertEqual(len(r1['tablePermissions']), 1)
        self.assertEqual(r1['tablePermissions'][0]['name'], 'Orders')
        self.assertIn('[Region]', r1['tablePermissions'][0]['filterExpression'])

        r2 = result[1]
        self.assertEqual(r2['name'], 'Admins')

    def test_parse_quoted_table_name(self):
        from powerbi_import.shared_model import _parse_tmdl_table
        tmdl = "table 'My Special Table'\n\tlineageTag: abc\n"
        result = _parse_tmdl_table(tmdl)
        self.assertEqual(result['name'], 'My Special Table')

    def test_parse_empty_tmdl(self):
        from powerbi_import.shared_model import _parse_tmdl_table
        result = _parse_tmdl_table('')
        self.assertEqual(result['name'], '')
        self.assertEqual(result['columns'], [])

    def test_unquote_name(self):
        from powerbi_import.shared_model import _unquote_name
        self.assertEqual(_unquote_name("'My Table'"), 'My Table')
        self.assertEqual(_unquote_name("SimpleName"), 'SimpleName')
        self.assertEqual(_unquote_name("'O''Brien'"), "O'Brien")


class TestLoadExistingModel(unittest.TestCase):
    """Test load_existing_model() from a TMDL directory."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix='test_load_model_')
        # Build a realistic TMDL directory structure
        self.model_dir = os.path.join(self.tmpdir, 'TestModel.SemanticModel', 'definition')
        self.tables_dir = os.path.join(self.model_dir, 'tables')
        os.makedirs(self.tables_dir)

        # Write a table TMDL
        with open(os.path.join(self.tables_dir, 'Orders.tmdl'), 'w') as f:
            f.write("table Orders\n\tlineageTag: abc\n\n")
            f.write("\tmeasure 'Total Sales' = SUM('Orders'[Amount])\n")
            f.write("\t\tformatString: $#,##0\n")
            f.write("\t\tlineageTag: m1\n\n")
            f.write("\tcolumn OrderID\n")
            f.write("\t\tdataType: int64\n")
            f.write("\t\tsourceColumn: OrderID\n")
            f.write("\t\tlineageTag: c1\n")
            f.write("\t\tsummarizeBy: none\n\n")
            f.write("\tcolumn Amount\n")
            f.write("\t\tdataType: double\n")
            f.write("\t\tsourceColumn: Amount\n")
            f.write("\t\tlineageTag: c2\n")
            f.write("\t\tsummarizeBy: sum\n\n")
            f.write("\tannotation PBI_ResultType = Table\n")

        with open(os.path.join(self.tables_dir, 'Customers.tmdl'), 'w') as f:
            f.write("table Customers\n\tlineageTag: def\n\n")
            f.write("\tcolumn CustomerID\n")
            f.write("\t\tdataType: int64\n")
            f.write("\t\tsourceColumn: CustomerID\n")
            f.write("\t\tlineageTag: c3\n")
            f.write("\t\tsummarizeBy: none\n\n")
            f.write("\tannotation PBI_ResultType = Table\n")

        # Write relationships TMDL
        with open(os.path.join(self.model_dir, 'relationships.tmdl'), 'w') as f:
            f.write("relationship rel-1\n")
            f.write("\tfromColumn: Orders.CustomerID\n")
            f.write("\ttoColumn: Customers.CustomerID\n")
            f.write("\tcrossFilteringBehavior: oneDirection\n\n")

        # Write roles TMDL
        with open(os.path.join(self.model_dir, 'roles.tmdl'), 'w') as f:
            f.write("role 'Sales Team'\n")
            f.write("\tmodelPermission: read\n\n")
            f.write("\ttablePermission Orders\n")
            f.write("\t\tfilterExpression = [Region] = \"West\"\n\n")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_load_model_from_project_dir(self):
        from powerbi_import.shared_model import load_existing_model
        result = load_existing_model(self.tmpdir)
        self.assertEqual(len(result['datasources']), 1)
        ds = result['datasources'][0]
        self.assertEqual(len(ds['tables']), 2)
        table_names = {t['name'] for t in ds['tables']}
        self.assertIn('Orders', table_names)
        self.assertIn('Customers', table_names)

    def test_load_model_tables(self):
        from powerbi_import.shared_model import load_existing_model
        result = load_existing_model(self.tmpdir)
        ds = result['datasources'][0]
        orders_table = next(t for t in ds['tables'] if t['name'] == 'Orders')
        self.assertEqual(len(orders_table['columns']), 2)

    def test_load_model_measures(self):
        from powerbi_import.shared_model import load_existing_model
        result = load_existing_model(self.tmpdir)
        measures = [c for c in result['calculations']
                    if c.get('_classification') == 'measure']
        self.assertEqual(len(measures), 1)
        self.assertEqual(measures[0]['caption'], 'Total Sales')
        self.assertIn("SUM('Orders'[Amount])", measures[0]['formula'])

    def test_load_model_relationships(self):
        from powerbi_import.shared_model import load_existing_model
        result = load_existing_model(self.tmpdir)
        ds = result['datasources'][0]
        self.assertEqual(len(ds['relationships']), 1)
        rel = ds['relationships'][0]
        self.assertEqual(rel['fromTable'], 'Orders')
        self.assertEqual(rel['toColumn'], 'CustomerID')

    def test_load_model_rls_roles(self):
        from powerbi_import.shared_model import load_existing_model
        result = load_existing_model(self.tmpdir)
        self.assertEqual(len(result['user_filters']), 1)
        uf = result['user_filters'][0]
        self.assertEqual(uf['name'], 'Sales Team')
        self.assertIn('[Region]', uf['filter_expression'])

    def test_load_model_from_definition_dir(self):
        from powerbi_import.shared_model import load_existing_model
        result = load_existing_model(self.model_dir)
        self.assertEqual(len(result['datasources']), 1)

    def test_load_model_nonexistent_dir(self):
        from powerbi_import.shared_model import load_existing_model
        result = load_existing_model('/nonexistent/path')
        self.assertEqual(result['datasources'], [])
        self.assertEqual(result['calculations'], [])


class TestAddToModel(unittest.TestCase):
    """Test add_to_model() incremental add workflow."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix='test_add_model_')
        # Create a minimal model with manifest
        from powerbi_import.shared_model import MergeManifest
        m = MergeManifest(
            model_name='TestModel',
            workbooks=[{
                'name': 'WB1', 'path': '', 'hash': '',
                'tables': ['Orders'], 'measures': ['Total Sales'],
                'exclusive_tables': ['Orders'],
            }],
            table_fingerprints={'Orders': 'fp1'},
            artifact_counts={'tables': 1, 'measures': 1, 'relationships': 0,
                             'rls_roles': 0, 'parameters': 0},
            merge_score=80,
            validation_score=95,
            timestamp='2025-01-01T00:00:00Z',
        )
        m.save(self.tmpdir)

        # Create minimal TMDL
        sm_dir = os.path.join(self.tmpdir, 'TestModel.SemanticModel', 'definition')
        tables_dir = os.path.join(sm_dir, 'tables')
        os.makedirs(tables_dir)
        with open(os.path.join(tables_dir, 'Orders.tmdl'), 'w') as f:
            f.write("table Orders\n\tlineageTag: abc\n\n")
            f.write("\tcolumn OrderID\n")
            f.write("\t\tdataType: int64\n")
            f.write("\t\tsourceColumn: OrderID\n")
            f.write("\t\tlineageTag: c1\n")
            f.write("\t\tsummarizeBy: none\n\n")
            f.write("\tmeasure 'Total Sales' = SUM([Amount])\n")
            f.write("\t\tlineageTag: m1\n\n")
            f.write("\tannotation PBI_ResultType = Table\n")
        with open(os.path.join(sm_dir, 'relationships.tmdl'), 'w') as f:
            f.write("")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_add_new_workbook(self):
        from powerbi_import.shared_model import add_to_model
        new_extracted = {
            'datasources': [{
                'connection': {'type': 'sqlserver', 'details': {'server': 'srv', 'database': 'db'}},
                'tables': [{'name': 'Products', 'type': 'table',
                           'columns': [{'name': 'ProductID'}]}],
                'relationships': [],
            }],
            'calculations': [],
            'parameters': [],
            'user_filters': [],
            'worksheets': [],
            'dashboards': [],
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
        }
        result = add_to_model(self.tmpdir, new_extracted, 'WB2', force=True)
        self.assertEqual(result['status'], 'added')
        self.assertIsNotNone(result['merged'])
        self.assertEqual(len(result['manifest'].workbooks), 2)
        self.assertIsNotNone(result['manifest'].find_workbook('WB2'))

    def test_add_duplicate_workbook_without_force(self):
        from powerbi_import.shared_model import add_to_model
        new_extracted = {
            'datasources': [],
            'calculations': [],
            'parameters': [],
            'user_filters': [],
            'worksheets': [],
            'dashboards': [],
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
        }
        with self.assertRaises(ValueError):
            add_to_model(self.tmpdir, new_extracted, 'WB1', force=False)

    def test_add_duplicate_workbook_with_force(self):
        from powerbi_import.shared_model import add_to_model
        new_extracted = {
            'datasources': [{
                'connection': {'type': 'sqlserver', 'details': {'server': 's', 'database': 'd'}},
                'tables': [{'name': 'Orders', 'type': 'table', 'columns': []}],
                'relationships': [],
            }],
            'calculations': [],
            'parameters': [],
            'user_filters': [],
            'worksheets': [],
            'dashboards': [],
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
        }
        result = add_to_model(self.tmpdir, new_extracted, 'WB1', force=True)
        self.assertEqual(result['status'], 'added')
        # Should replace, not duplicate
        wb1_entries = [wb for wb in result['manifest'].workbooks
                       if wb['name'] == 'WB1']
        self.assertEqual(len(wb1_entries), 1)

    def test_add_updates_manifest_counts(self):
        from powerbi_import.shared_model import add_to_model
        new_extracted = {
            'datasources': [{
                'connection': {'type': 'sqlserver', 'details': {'server': 's', 'database': 'd'}},
                'tables': [{'name': 'NewTable', 'type': 'table',
                           'columns': [{'name': 'ID'}]}],
                'relationships': [],
            }],
            'calculations': [
                {'caption': 'NewMeasure', 'name': '[NewMeasure]',
                 '_classification': 'measure', 'role': 'measure',
                 'formula': 'COUNT([ID])'}
            ],
            'parameters': [],
            'user_filters': [],
            'worksheets': [],
            'dashboards': [],
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
        }
        result = add_to_model(self.tmpdir, new_extracted, 'WB2', force=True)
        # Manifest should have been updated with timestamp and WB2 added
        self.assertEqual(result['status'], 'added')
        self.assertIsNotNone(result['manifest'].find_workbook('WB2'))
        self.assertTrue(result['manifest'].timestamp)


class TestRemoveFromModel(unittest.TestCase):
    """Test remove_from_model() incremental removal."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix='test_remove_model_')
        from powerbi_import.shared_model import MergeManifest
        m = MergeManifest(
            model_name='TestModel',
            workbooks=[
                {'name': 'WB1', 'path': '', 'hash': '',
                 'tables': ['Orders', 'DimDate'],
                 'measures': ['Total Sales'],
                 'exclusive_tables': ['Orders']},
                {'name': 'WB2', 'path': '', 'hash': '',
                 'tables': ['Products', 'DimDate'],
                 'measures': ['Product Count'],
                 'exclusive_tables': ['Products']},
            ],
            table_fingerprints={'Orders': 'fp1', 'Products': 'fp2', 'DimDate': 'fp3'},
            artifact_counts={'tables': 3, 'measures': 2, 'relationships': 0,
                             'rls_roles': 0, 'parameters': 0},
            merge_score=80,
            timestamp='2025-01-01T00:00:00Z',
        )
        m.save(self.tmpdir)

        # TMDL structure
        sm_dir = os.path.join(self.tmpdir, 'TestModel.SemanticModel', 'definition')
        tables_dir = os.path.join(sm_dir, 'tables')
        os.makedirs(tables_dir)
        for tname in ['Orders', 'Products', 'DimDate']:
            with open(os.path.join(tables_dir, f'{tname}.tmdl'), 'w') as f:
                f.write(f"table {tname}\n\tlineageTag: abc\n\n")
                f.write(f"\tcolumn ID\n")
                f.write(f"\t\tdataType: int64\n")
                f.write(f"\t\tsourceColumn: ID\n")
                f.write(f"\t\tlineageTag: c1\n")
                f.write(f"\t\tsummarizeBy: none\n\n")
                f.write(f"\tannotation PBI_ResultType = Table\n")
        with open(os.path.join(sm_dir, 'relationships.tmdl'), 'w') as f:
            f.write("")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_remove_workbook_exclusive_tables(self):
        from powerbi_import.shared_model import remove_from_model
        result = remove_from_model(self.tmpdir, 'WB1')
        self.assertEqual(result['status'], 'removed')
        self.assertIn('Orders', result['removed_tables'])
        # DimDate is shared, should be kept
        self.assertIn('DimDate', result['shared_tables_kept'])
        self.assertEqual(len(result['manifest'].workbooks), 1)
        self.assertIsNone(result['manifest'].find_workbook('WB1'))

    def test_remove_nonexistent_workbook(self):
        from powerbi_import.shared_model import remove_from_model
        result = remove_from_model(self.tmpdir, 'NonExistent')
        self.assertEqual(result['status'], 'not_found')

    def test_remove_updates_manifest(self):
        from powerbi_import.shared_model import remove_from_model
        result = remove_from_model(self.tmpdir, 'WB2')
        manifest = result['manifest']
        self.assertEqual(len(manifest.workbooks), 1)
        self.assertNotIn('Products', manifest.table_fingerprints)
        # DimDate should still be there (shared)
        self.assertIn('DimDate', manifest.table_fingerprints)

    def test_remove_preserves_shared_tables(self):
        """DimDate is in both WB1 and WB2 — removing WB1 should keep DimDate."""
        from powerbi_import.shared_model import remove_from_model
        result = remove_from_model(self.tmpdir, 'WB1')
        merged = result['merged']
        if merged and merged.get('datasources'):
            ds_tables = {t['name'] for t in merged['datasources'][0].get('tables', [])}
            self.assertIn('DimDate', ds_tables)


class TestDiffManifests(unittest.TestCase):
    """Test diff_manifests() for manifest comparison."""

    def test_diff_added_table(self):
        from powerbi_import.merge_assessment import diff_manifests
        old = {
            'workbooks': [{'name': 'WB1', 'measures': ['M1']}],
            'table_fingerprints': {'T1': 'fp1'},
            'artifact_counts': {'relationships': 2},
            'merge_config_snapshot': {},
            'merge_score': 80,
        }
        new = {
            'workbooks': [
                {'name': 'WB1', 'measures': ['M1']},
                {'name': 'WB2', 'measures': ['M2']},
            ],
            'table_fingerprints': {'T1': 'fp1', 'T2': 'fp2'},
            'artifact_counts': {'relationships': 3},
            'merge_config_snapshot': {},
            'merge_score': 85,
        }
        diff = diff_manifests(old, new)
        self.assertEqual(diff['added_tables'], ['T2'])
        self.assertEqual(diff['removed_tables'], [])
        self.assertEqual(diff['added_workbooks'], ['WB2'])
        self.assertEqual(diff['added_measures'], ['M2'])
        self.assertEqual(diff['relationship_count_change'], 1)

    def test_diff_removed_table(self):
        from powerbi_import.merge_assessment import diff_manifests
        old = {
            'workbooks': [{'name': 'WB1', 'measures': []}],
            'table_fingerprints': {'T1': 'fp1', 'T2': 'fp2'},
            'artifact_counts': {'relationships': 0},
            'merge_config_snapshot': {},
            'merge_score': 80,
        }
        new = {
            'workbooks': [{'name': 'WB1', 'measures': []}],
            'table_fingerprints': {'T1': 'fp1'},
            'artifact_counts': {'relationships': 0},
            'merge_config_snapshot': {},
            'merge_score': 80,
        }
        diff = diff_manifests(old, new)
        self.assertEqual(diff['removed_tables'], ['T2'])
        self.assertEqual(diff['added_tables'], [])

    def test_diff_config_changes(self):
        from powerbi_import.merge_assessment import diff_manifests
        old = {
            'workbooks': [],
            'table_fingerprints': {},
            'artifact_counts': {'relationships': 0},
            'merge_config_snapshot': {'force': False},
            'merge_score': 50,
        }
        new = {
            'workbooks': [],
            'table_fingerprints': {},
            'artifact_counts': {'relationships': 0},
            'merge_config_snapshot': {'force': True},
            'merge_score': 60,
        }
        diff = diff_manifests(old, new)
        self.assertIn('force', diff['config_changes'])
        self.assertEqual(diff['config_changes']['force'], {'old': False, 'new': True})

    def test_diff_identical_manifests(self):
        from powerbi_import.merge_assessment import diff_manifests
        m = {
            'workbooks': [{'name': 'WB1', 'measures': ['M1']}],
            'table_fingerprints': {'T1': 'fp1'},
            'artifact_counts': {'relationships': 1},
            'merge_config_snapshot': {},
            'merge_score': 80,
        }
        diff = diff_manifests(m, m)
        self.assertEqual(diff['added_tables'], [])
        self.assertEqual(diff['removed_tables'], [])
        self.assertEqual(diff['added_workbooks'], [])
        self.assertEqual(diff['removed_workbooks'], [])
        self.assertEqual(diff['relationship_count_change'], 0)

    def test_diff_with_manifest_objects(self):
        """diff_manifests should accept MergeManifest objects."""
        from powerbi_import.shared_model import MergeManifest
        from powerbi_import.merge_assessment import diff_manifests

        old = MergeManifest(
            model_name='M',
            workbooks=[{'name': 'A', 'measures': []}],
            table_fingerprints={'T1': 'fp1'},
            artifact_counts={'relationships': 0},
            merge_score=70,
        )
        new = MergeManifest(
            model_name='M',
            workbooks=[
                {'name': 'A', 'measures': []},
                {'name': 'B', 'measures': ['M1']},
            ],
            table_fingerprints={'T1': 'fp1', 'T2': 'fp2'},
            artifact_counts={'relationships': 1},
            merge_score=80,
        )
        diff = diff_manifests(old, new)
        self.assertEqual(diff['added_tables'], ['T2'])
        self.assertEqual(diff['added_workbooks'], ['B'])


class TestFindDefinitionDir(unittest.TestCase):
    """Test _find_definition_dir() path resolution."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix='test_find_def_')

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_from_project_dir_with_semantic_model(self):
        from powerbi_import.shared_model import _find_definition_dir
        def_dir = os.path.join(self.tmpdir, 'Model.SemanticModel', 'definition')
        os.makedirs(def_dir)
        result = _find_definition_dir(self.tmpdir)
        self.assertEqual(os.path.normpath(result), os.path.normpath(def_dir))

    def test_from_definition_dir_directly(self):
        from powerbi_import.shared_model import _find_definition_dir
        def_dir = os.path.join(self.tmpdir, 'definition')
        os.makedirs(os.path.join(def_dir, 'tables'))
        result = _find_definition_dir(def_dir)
        self.assertEqual(os.path.normpath(result), os.path.normpath(def_dir))

    def test_from_dir_with_tables_subdir(self):
        from powerbi_import.shared_model import _find_definition_dir
        os.makedirs(os.path.join(self.tmpdir, 'tables'))
        result = _find_definition_dir(self.tmpdir)
        self.assertEqual(os.path.normpath(result), os.path.normpath(self.tmpdir))

    def test_nonexistent_returns_none(self):
        from powerbi_import.shared_model import _find_definition_dir
        result = _find_definition_dir('/nonexistent/path')
        self.assertIsNone(result)


class TestManifestSaveAfterMerge(unittest.TestCase):
    """Test that manifest is properly written after import_shared_model."""

    def test_manifest_file_written(self):
        """Verify the manifest JSON file is valid."""
        from powerbi_import.shared_model import MergeManifest
        tmpdir = tempfile.mkdtemp(prefix='test_manifest_write_')
        try:
            m = MergeManifest(
                model_name='Integration',
                workbooks=[
                    {'name': 'A', 'path': 'a.twbx', 'hash': 'h1',
                     'tables': ['T1'], 'measures': ['M1'],
                     'exclusive_tables': ['T1']},
                ],
                table_fingerprints={'T1': 'fp1'},
                artifact_counts={'tables': 1, 'measures': 1,
                                 'relationships': 0, 'rls_roles': 0, 'parameters': 0},
                merge_score=65,
                validation_score=88,
                timestamp='2025-07-01T00:00:00+00:00',
            )
            path = m.save(tmpdir)

            with open(path, 'r') as f:
                data = json.load(f)

            self.assertEqual(data['model_name'], 'Integration')
            self.assertEqual(data['schema_version'], '1.0')
            self.assertEqual(len(data['workbooks']), 1)
            self.assertEqual(data['merge_score'], 65)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestIdempotentReAdd(unittest.TestCase):
    """Test that re-adding the same workbook is idempotent with force."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix='test_idempotent_')
        from powerbi_import.shared_model import MergeManifest
        m = MergeManifest(
            model_name='M',
            workbooks=[{
                'name': 'WB1', 'path': '', 'hash': '',
                'tables': ['T1'], 'measures': [],
                'exclusive_tables': ['T1'],
            }],
            table_fingerprints={'T1': 'fp1'},
            artifact_counts={'tables': 1, 'measures': 0, 'relationships': 0,
                             'rls_roles': 0, 'parameters': 0},
            merge_score=80,
            timestamp='2025-01-01',
        )
        m.save(self.tmpdir)

        sm_dir = os.path.join(self.tmpdir, 'M.SemanticModel', 'definition')
        tables_dir = os.path.join(sm_dir, 'tables')
        os.makedirs(tables_dir)
        with open(os.path.join(tables_dir, 'T1.tmdl'), 'w') as f:
            f.write("table T1\n\tlineageTag: abc\n\n")
            f.write("\tcolumn ID\n")
            f.write("\t\tdataType: int64\n")
            f.write("\t\tsourceColumn: ID\n")
            f.write("\t\tlineageTag: c1\n")
            f.write("\t\tsummarizeBy: none\n\n")
            f.write("\tannotation PBI_ResultType = Table\n")
        with open(os.path.join(sm_dir, 'relationships.tmdl'), 'w') as f:
            f.write("")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_readd_same_workbook_is_idempotent(self):
        from powerbi_import.shared_model import add_to_model
        extracted = {
            'datasources': [{
                'connection': {'type': 'sql', 'details': {'server': 's', 'database': 'd'}},
                'tables': [{'name': 'T1', 'type': 'table', 'columns': [{'name': 'ID'}]}],
                'relationships': [],
            }],
            'calculations': [],
            'parameters': [],
            'user_filters': [],
            'worksheets': [],
            'dashboards': [],
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
        }
        result = add_to_model(self.tmpdir, extracted, 'WB1', force=True)
        self.assertEqual(result['status'], 'added')
        # Should still have exactly 1 WB1 entry
        wb1_entries = [wb for wb in result['manifest'].workbooks
                       if wb['name'] == 'WB1']
        self.assertEqual(len(wb1_entries), 1)


class TestFileHash(unittest.TestCase):
    """Test _file_hash helper."""

    def test_file_hash_returns_hex(self):
        from powerbi_import.shared_model import _file_hash
        tmpfile = tempfile.NamedTemporaryFile(delete=False, suffix='.txt')
        try:
            tmpfile.write(b'hello world')
            tmpfile.close()
            h = _file_hash(tmpfile.name)
            self.assertEqual(len(h), 16)
            self.assertTrue(all(c in '0123456789abcdef' for c in h))
        finally:
            os.unlink(tmpfile.name)

    def test_file_hash_nonexistent(self):
        from powerbi_import.shared_model import _file_hash
        h = _file_hash('/nonexistent/file.twbx')
        self.assertEqual(h, '')


if __name__ == '__main__':
    unittest.main()
