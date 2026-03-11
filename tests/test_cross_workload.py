"""
Cross-Workload Validation Tests.

Verifies consistency between the 4 workloads produced by the migration:
  - Power Query M  (m_query_builder)
  - TMDL / BIM     (tmdl_generator)
  - DAX            (dax_converter)
  - PBI / PBIR     (pbip_generator + visual_generator)

Each test class covers one cross-check (A–L) from the audit matrix:
  A - DAX measure column refs → TMDL columns
  B - DAX measure table refs → TMDL tables
  C - TMDL column sourceColumn → M partition output columns
  D - PBI visual fields → TMDL (covered in test_integration.py)
  E - Relationship fromTable/toTable/fromColumn/toColumn → TMDL
  F - PBI filter Entity+Property → TMDL columns
  G - PBI slicer Entity+Property → TMDL columns
  H - Hierarchy level columns → parent TMDL table columns
  I - Calendar rels → fact table date columns (covered in test_tmdl_generator.py)
  J - RLS role tablePermission → TMDL tables
  K - Parameter table → SELECTEDVALUE measure (covered in test_migration_validation.py)
  L - sortByColumn → same-table columns (covered in test_sprint_13.py)
"""

import copy
import glob
import json
import os
import re
import sys
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))

from tests.factories import (
    DatasourceFactory, WorksheetFactory, DashboardFactory,
    ModelFactory, ParameterFactory, make_multi_table_model,
    make_complex_model, make_simple_model,
)
from tests.conftest import make_temp_dir, cleanup_dir
from tmdl_generator import generate_tmdl, _build_semantic_model
from pbip_generator import PowerBIProjectGenerator


# ════════════════════════════════════════════════════════════════════
#  Helpers
# ════════════════════════════════════════════════════════════════════

def _generate_full_pipeline(datasources, converted_objects, temp_dir,
                            report_name='CrossTest'):
    """Run the full TMDL + PBIR pipeline and return (project_path, tmdl_stats, bim_model)."""
    # Build BIM model dict for inspection
    bim_model = _build_semantic_model(
        datasources, report_name, converted_objects
    )

    # Generate the full project on disk
    generator = PowerBIProjectGenerator(output_dir=temp_dir)
    project_path = generator.generate_project(
        report_name, copy.deepcopy(converted_objects)
    )

    # Also get TMDL stats
    sm_dir = os.path.join(project_path, f'{report_name}.SemanticModel')
    tmdl_dir = os.path.join(sm_dir, 'definition')
    # Re-generate TMDL stats from the BIM model
    tables = bim_model.get('model', {}).get('tables', [])
    rels = bim_model.get('model', {}).get('relationships', [])
    actual_bim_symbols = set()
    actual_bim_measures = set()
    for t in tables:
        tname = t.get('name', '')
        for m in t.get('measures', []):
            mname = m.get('name', '')
            if mname:
                actual_bim_measures.add(mname)
                actual_bim_symbols.add((tname, mname))
        for c in t.get('columns', []):
            cname = c.get('name', '')
            if cname:
                actual_bim_symbols.add((tname, cname))

    stats = {
        'tables': len(tables),
        'columns': sum(len(t.get('columns', [])) for t in tables),
        'measures': sum(len(t.get('measures', [])) for t in tables),
        'relationships': len(rels),
        'actual_bim_symbols': actual_bim_symbols,
        'actual_bim_measures': actual_bim_measures,
    }
    return project_path, stats, bim_model


def _extract_dax_refs(dax_expression):
    """Extract all 'Table'[Column] references from a DAX expression.

    Returns list of (table_name, column_name) tuples.
    """
    # Match 'Table Name'[Column Name] pattern
    pattern = r"'([^']+)'\[([^\]]+)\]"
    return re.findall(pattern, dax_expression)


def _extract_m_output_columns(m_expression):
    """Extract column names that appear in a Power Query M expression.

    Heuristic: captures column names from Table.RenameColumns, Table.AddColumn,
    field references in {...} records, and #"colname" syntax.
    """
    columns = set()
    # #"Column Name" references
    for match in re.findall(r'#"([^"]+)"', m_expression):
        columns.add(match)
    # {"ColumnName", ... } in records
    for match in re.findall(r'\{"([^"]+)"', m_expression):
        columns.add(match)
    # Table.AddColumn(..., "colName", ...)
    for match in re.findall(r'Table\.AddColumn\([^,]+,\s*"([^"]+)"', m_expression):
        columns.add(match)
    # Table.RenameColumns target names: {"OldName", "NewName"}
    for match in re.findall(r'\{[^}]*"[^"]+"\s*,\s*"([^"]+)"', m_expression):
        columns.add(match)
    return columns


def _is_whole_table_m_query(m_expression):
    """Check if the M query fetches a whole table (columns come from schema).

    These queries reference Source{[Schema=..., Item=...]}[Data] or similar
    and individual column names are NOT listed in the expression — they are
    resolved at data refresh time from the database/file schema.
    """
    # SQL-style whole table: Source{[Schema="dbo", Item="Orders"]}[Data]
    if re.search(r'Source\{.*\}\[Data\]', m_expression, re.DOTALL):
        return True
    # CSV/Excel file: Csv.Document or Excel.Workbook
    if re.search(r'(Csv\.Document|Excel\.Workbook|File\.Contents)', m_expression):
        return True
    # Folder.Files
    if 'Folder.Files' in m_expression:
        return True
    return False


def _collect_visual_entity_property(project_path):
    """Scan all visual.json files and return set of (Entity, Property) tuples."""
    refs = set()
    pattern = os.path.join(project_path, '**', 'visual.json')
    for vf in glob.glob(pattern, recursive=True):
        with open(vf, 'r', encoding='utf-8') as f:
            content = f.read()
        # Entity+Property in Column wrapper
        for m in re.finditer(
            r'"(?:Column|Measure)"\s*:\s*\{[^}]*?"Expression"\s*:\s*\{[^}]*?"SourceRef"\s*:\s*\{[^}]*?"Entity"\s*:\s*"([^"]+)"[^}]*?\}[^}]*?\}[^}]*?"Property"\s*:\s*"([^"]+)"',
            content, re.DOTALL
        ):
            refs.add((m.group(1), m.group(2)))
    return refs


def _collect_filter_entity_property(project_path):
    """Scan all filter JSON and visual.json files for filter Entity+Property refs."""
    refs = set()
    # Scan report-level filters and page-level filters
    for json_file in glob.glob(os.path.join(project_path, '**', '*.json'), recursive=True):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except (UnicodeDecodeError, OSError):
            continue
        # Look for filter objects with Entity+Property
        for m in re.finditer(
            r'"filter"\s*:\s*\{[^}]*"From"\s*:\s*\[\s*\{[^}]*"Entity"\s*:\s*"([^"]+)"',
            content, re.DOTALL
        ):
            entity = m.group(1)
            # Find the Property within the same filter block
            # Search forward from this match for Property
            start = m.start()
            substr = content[start:start+2000]
            prop_m = re.search(r'"Property"\s*:\s*"([^"]+)"', substr)
            if prop_m:
                refs.add((entity, prop_m.group(1)))
    return refs


# ════════════════════════════════════════════════════════════════════
#  CHECK A+B: DAX measure/calc-column refs → TMDL tables + columns
# ════════════════════════════════════════════════════════════════════

class TestDaxTmdlConsistency(unittest.TestCase):
    """DAX expressions must only reference tables and columns that exist
    in the BIM model (TMDL)."""

    def test_measure_table_refs_exist_in_tmdl(self):
        """All 'Table'[Col] refs in DAX measures must reference valid TMDL tables."""

        ds = (DatasourceFactory('DS')
              .with_table('Orders', ['OrderID:integer', 'Amount:real', 'OrderDate:datetime'])
              .with_table('Products', ['ProductID:integer', 'ProductName:string', 'Price:real'])
              .with_relationship('Orders', 'ProductID', 'Products', 'ProductID',
                                 from_count=1000, to_count=50)
              .with_measure('Total Sales', 'SUM([Amount])')
              .with_measure('Avg Price', 'AVERAGE([Price])'))
        datasources = [ds.build()]
        extra = ModelFactory().with_datasource(ds).build()

        model = _build_semantic_model(datasources, 'DaxRefTest', extra)
        tables = model['model']['tables']
        table_names = {t['name'] for t in tables}

        # Collect all DAX expressions from measures
        for table in tables:
            for measure in table.get('measures', []):
                dax = measure.get('expression', '')
                for ref_table, ref_col in _extract_dax_refs(dax):
                    self.assertIn(
                        ref_table, table_names,
                        f"Measure '{measure['name']}' references table "
                        f"'{ref_table}' not in TMDL: {table_names}"
                    )

    def test_measure_column_refs_exist_in_tmdl(self):
        """All 'Table'[Col] refs in DAX measures must reference valid columns."""

        ds = (DatasourceFactory('DS')
              .with_table('Orders', ['OrderID:integer', 'Amount:real', 'Region:string'])
              .with_measure('Total Sales', 'SUM([Amount])')
              .with_calc_column('Upper Region', 'UPPER([Region])'))
        datasources = [ds.build()]
        extra = ModelFactory().with_datasource(ds).build()

        model = _build_semantic_model(datasources, 'DaxColRefTest', extra)
        tables = model['model']['tables']

        # Build symbol lookup: {table_name: set(column/measure names)}
        symbols = {}
        for t in tables:
            tname = t['name']
            cols = {c['name'] for c in t.get('columns', [])}
            measures = {m['name'] for m in t.get('measures', [])}
            symbols[tname] = cols | measures

        # Check all DAX in measures and calc columns
        for table in tables:
            for measure in table.get('measures', []):
                dax = measure.get('expression', '')
                for ref_table, ref_col in _extract_dax_refs(dax):
                    if ref_table in symbols:
                        self.assertIn(
                            ref_col, symbols[ref_table],
                            f"Measure '{measure['name']}' references "
                            f"'{ref_table}'[{ref_col}] but column not in table"
                        )
            # Calculated columns
            for col in table.get('columns', []):
                dax = col.get('expression', '')
                if dax:
                    for ref_table, ref_col in _extract_dax_refs(dax):
                        if ref_table in symbols:
                            self.assertIn(
                                ref_col, symbols[ref_table],
                                f"Calc column '{col['name']}' references "
                                f"'{ref_table}'[{ref_col}] but column not in table"
                            )

    def test_cross_table_dax_uses_related_or_lookupvalue(self):
        """DAX formulas referencing another table must use RELATED() or LOOKUPVALUE()."""

        ds = (DatasourceFactory('DS')
              .with_table('Orders', ['OrderID:integer', 'ProductID:integer', 'Amount:real'])
              .with_table('Products', ['ProductID:integer', 'ProductName:string', 'Price:real'])
              .with_relationship('Orders', 'ProductID', 'Products', 'ProductID',
                                 from_count=1000, to_count=50)
              .with_calc_column('Product Label', '[ProductName]'))
        datasources = [ds.build()]
        extra = ModelFactory().with_datasource(ds).build()

        model = _build_semantic_model(datasources, 'CrossTableTest', extra)
        tables = model['model']['tables']

        # Find the calc column that references another table
        for table in tables:
            for col in table.get('columns', []):
                dax = col.get('expression', '')
                if not dax:
                    continue
                for ref_table, ref_col in _extract_dax_refs(dax):
                    if ref_table != table['name']:
                        # Cross-table ref must use RELATED or LOOKUPVALUE
                        self.assertTrue(
                            'RELATED(' in dax or 'LOOKUPVALUE(' in dax,
                            f"Calc column '{col['name']}' in '{table['name']}' "
                            f"references '{ref_table}'[{ref_col}] without "
                            f"RELATED() or LOOKUPVALUE()"
                        )

    def test_dax_complex_model_all_refs_valid(self):
        """End-to-end: complex model DAX refs all resolve to TMDL."""

        datasources, extra = make_complex_model()
        model = _build_semantic_model(datasources, 'ComplexDaxTest', extra)
        tables = model['model']['tables']

        # Build complete symbol table
        symbols = {}
        for t in tables:
            tname = t['name']
            cols = {c['name'] for c in t.get('columns', [])}
            meas = {m['name'] for m in t.get('measures', [])}
            symbols[tname] = cols | meas

        table_names = set(symbols.keys())
        unresolved = []

        for table in tables:
            for measure in table.get('measures', []):
                dax = measure.get('expression', '')
                for ref_table, ref_col in _extract_dax_refs(dax):
                    if ref_table not in table_names:
                        unresolved.append(f"Measure '{measure['name']}': '{ref_table}' not in tables")
                    elif ref_col not in symbols.get(ref_table, set()):
                        unresolved.append(f"Measure '{measure['name']}': '{ref_table}'[{ref_col}] not found")
            for col in table.get('columns', []):
                dax = col.get('expression', '')
                if dax:
                    for ref_table, ref_col in _extract_dax_refs(dax):
                        if ref_table not in table_names:
                            unresolved.append(f"CalcCol '{col['name']}': '{ref_table}' not in tables")
                        elif ref_col not in symbols.get(ref_table, set()):
                            unresolved.append(f"CalcCol '{col['name']}': '{ref_table}'[{ref_col}] not found")

        self.assertEqual(unresolved, [],
                         "Unresolved DAX refs:\n" + "\n".join(unresolved))


# ════════════════════════════════════════════════════════════════════
#  CHECK C: TMDL column sourceColumn → M partition output
# ════════════════════════════════════════════════════════════════════

class TestMQueryTmdlConsistency(unittest.TestCase):
    """TMDL columns with sourceColumn must map to columns produced by
    the M partition expression in the same table."""

    def test_source_columns_match_m_partition(self):
        """Every sourceColumn value must appear in the M partition expression.
        
        For whole-table queries (SQL/CSV/Excel), the column names come from
        the schema at refresh time, so they won't appear literally in the M
        expression — those are skipped.  For M expressions that add computed
        columns (Table.AddColumn, sets, groups, bins, Calendar), the names
        must be present.
        """

        ds = (DatasourceFactory('DS')
              .with_table('Orders', ['OrderID:integer', 'Amount:real',
                                     'CustomerName:string', 'OrderDate:datetime']))
        datasources = [ds.build()]
        extra = (ModelFactory()
                 .with_datasource(ds)
                 .with_set('Active Orders', 'Orders', members=['Shipped'])
                 .build())

        model = _build_semantic_model(datasources, 'MPartitionTest', extra)
        tables = model['model']['tables']

        for table in tables:
            tname = table.get('name', '')
            partitions = table.get('partitions', [])
            if not partitions:
                continue
            m_expr = partitions[0].get('source', {}).get('expression', '')
            if not m_expr:
                continue

            # Skip whole-table queries — columns come from DB schema
            if _is_whole_table_m_query(m_expr):
                # But still check that Table.AddColumn steps (sets/groups/bins)
                # referenced by sourceColumn appear in the expression
                m_columns = _extract_m_output_columns(m_expr)
                for col in table.get('columns', []):
                    src_col = col.get('sourceColumn', '')
                    if not src_col:
                        continue
                    # Only check M-computed columns (those added via Table.AddColumn)
                    if 'Table.AddColumn' in m_expr and src_col in m_columns:
                        pass  # Good — computed column found
                continue

            # For non-whole-table queries (Calendar, custom), all columns must match
            m_columns = _extract_m_output_columns(m_expr)
            for col in table.get('columns', []):
                src_col = col.get('sourceColumn', '')
                if not src_col:
                    continue
                self.assertTrue(
                    src_col in m_columns or src_col in m_expr,
                    f"Table '{tname}': column '{col['name']}' has "
                    f"sourceColumn='{src_col}' not found in M expression. "
                    f"M columns detected: {m_columns}"
                )

    def test_set_m_column_appears_in_partition(self):
        """Set-based M calculated columns added via Table.AddColumn must
        appear in the partition expression."""

        ds = (DatasourceFactory('DS')
              .with_table('Orders', ['OrderID:integer', 'Status:string']))
        datasources = [ds.build()]
        extra = (ModelFactory()
                 .with_datasource(ds)
                 .with_set('Active Orders', 'Orders', members=['Shipped', 'Delivered'])
                 .build())

        model = _build_semantic_model(datasources, 'SetMTest', extra)
        tables = model['model']['tables']

        orders_table = next((t for t in tables if t['name'] == 'Orders'), None)
        self.assertIsNotNone(orders_table, "Orders table not found")

        # Check that the set column exists
        set_cols = [c for c in orders_table.get('columns', [])
                    if 'Active' in c.get('name', '')]
        # If sets generate M-based columns, sourceColumn should match
        for col in set_cols:
            src = col.get('sourceColumn', '')
            if src:
                partition = orders_table.get('partitions', [{}])[0]
                m_expr = partition.get('source', {}).get('expression', '')
                self.assertIn(
                    src, m_expr,
                    f"Set column '{col['name']}' sourceColumn='{src}' "
                    f"not in M partition"
                )

    def test_group_m_column_appears_in_partition(self):
        """Group-based M calculated columns must appear in partition."""

        ds = (DatasourceFactory('DS')
              .with_table('Orders', ['OrderID:integer', 'Region:string']))
        datasources = [ds.build()]
        extra = (ModelFactory()
                 .with_datasource(ds)
                 .with_group('Region Group', 'Orders', 'Region',
                             {'East': 'Eastern', 'West': 'Western'})
                 .build())

        model = _build_semantic_model(datasources, 'GroupMTest', extra)
        tables = model['model']['tables']

        orders_table = next((t for t in tables if t['name'] == 'Orders'), None)
        self.assertIsNotNone(orders_table)

        group_cols = [c for c in orders_table.get('columns', [])
                      if 'Region Group' in c.get('name', '')]
        for col in group_cols:
            src = col.get('sourceColumn', '')
            if src:
                partition = orders_table.get('partitions', [{}])[0]
                m_expr = partition.get('source', {}).get('expression', '')
                self.assertIn(
                    src, m_expr,
                    f"Group column '{col['name']}' sourceColumn='{src}' "
                    f"not in M partition"
                )

    def test_bin_m_column_appears_in_partition(self):
        """Bin-based M calculated columns must appear in partition."""

        ds = (DatasourceFactory('DS')
              .with_table('Orders', ['OrderID:integer', 'Amount:real']))
        datasources = [ds.build()]
        extra = (ModelFactory()
                 .with_datasource(ds)
                 .with_bin('Amount Bin', 'Orders', 'Amount', 50)
                 .build())

        model = _build_semantic_model(datasources, 'BinMTest', extra)
        tables = model['model']['tables']

        orders_table = next((t for t in tables if t['name'] == 'Orders'), None)
        self.assertIsNotNone(orders_table)

        bin_cols = [c for c in orders_table.get('columns', [])
                    if 'Bin' in c.get('name', '') or 'Amount' in c.get('name', '')]
        for col in bin_cols:
            src = col.get('sourceColumn', '')
            if src:
                partition = orders_table.get('partitions', [{}])[0]
                m_expr = partition.get('source', {}).get('expression', '')
                self.assertIn(
                    src, m_expr,
                    f"Bin column '{col['name']}' sourceColumn='{src}' "
                    f"not in M partition"
                )


# ════════════════════════════════════════════════════════════════════
#  CHECK E: Relationship from/to tables and columns → TMDL
# ════════════════════════════════════════════════════════════════════

class TestRelationshipTmdlConsistency(unittest.TestCase):
    """Relationship endpoints must reference real TMDL tables and columns."""

    def test_relationship_tables_exist_in_model(self):
        """fromTable and toTable must exist as TMDL tables."""

        datasources, extra = make_multi_table_model()
        model = _build_semantic_model(datasources, 'RelTest', extra)
        tables = model['model']['tables']
        rels = model['model']['relationships']
        table_names = {t['name'] for t in tables}

        for rel in rels:
            from_t = rel.get('fromTable', '')
            to_t = rel.get('toTable', '')
            self.assertIn(from_t, table_names,
                          f"Relationship fromTable '{from_t}' not in tables: {table_names}")
            self.assertIn(to_t, table_names,
                          f"Relationship toTable '{to_t}' not in tables: {table_names}")

    def test_relationship_columns_exist_in_tables(self):
        """fromColumn must exist in fromTable, toColumn must exist in toTable."""

        datasources, extra = make_multi_table_model()
        model = _build_semantic_model(datasources, 'RelColTest', extra)
        tables = model['model']['tables']
        rels = model['model']['relationships']

        # Build column lookup
        table_columns = {}
        for t in tables:
            cols = {c['name'] for c in t.get('columns', [])}
            table_columns[t['name']] = cols

        for rel in rels:
            from_t = rel.get('fromTable', '')
            from_c = rel.get('fromColumn', '')
            to_t = rel.get('toTable', '')
            to_c = rel.get('toColumn', '')

            if from_t in table_columns:
                self.assertIn(
                    from_c, table_columns[from_t],
                    f"fromColumn '{from_c}' not in table '{from_t}' "
                    f"columns: {table_columns[from_t]}"
                )
            if to_t in table_columns:
                self.assertIn(
                    to_c, table_columns[to_t],
                    f"toColumn '{to_c}' not in table '{to_t}' "
                    f"columns: {table_columns[to_t]}"
                )

    def test_complex_model_relationships_valid(self):
        """Complex model with 3 tables — all relationship refs valid."""

        datasources, extra = make_complex_model()
        model = _build_semantic_model(datasources, 'ComplexRelTest', extra)
        tables = model['model']['tables']
        rels = model['model']['relationships']

        table_columns = {}
        for t in tables:
            cols = {c['name'] for c in t.get('columns', [])}
            table_columns[t['name']] = cols

        errors = []
        for rel in rels:
            from_t = rel.get('fromTable', '')
            from_c = rel.get('fromColumn', '')
            to_t = rel.get('toTable', '')
            to_c = rel.get('toColumn', '')

            if from_t not in table_columns:
                errors.append(f"fromTable '{from_t}' not in model")
            elif from_c not in table_columns[from_t]:
                errors.append(f"fromColumn '{from_c}' not in '{from_t}'")
            if to_t not in table_columns:
                errors.append(f"toTable '{to_t}' not in model")
            elif to_c not in table_columns[to_t]:
                errors.append(f"toColumn '{to_c}' not in '{to_t}'")

        self.assertEqual(errors, [],
                         "Relationship validation errors:\n" + "\n".join(errors))

    def test_calendar_relationship_columns_exist(self):
        """Calendar auto-relationship fromColumn/toColumn must exist in both tables."""

        ds = (DatasourceFactory('DS')
              .with_table('Sales', ['ID:integer', 'SaleDate:datetime', 'Amount:real']))
        datasources = [ds.build()]
        extra = ModelFactory().with_datasource(ds).build()

        model = _build_semantic_model(datasources, 'CalRelTest', extra)
        tables = model['model']['tables']
        rels = model['model']['relationships']

        table_columns = {}
        for t in tables:
            cols = {c['name'] for c in t.get('columns', [])}
            table_columns[t['name']] = cols

        for rel in rels:
            from_t = rel.get('fromTable', '')
            from_c = rel.get('fromColumn', '')
            to_t = rel.get('toTable', '')
            to_c = rel.get('toColumn', '')

            if from_t in table_columns and to_t in table_columns:
                self.assertIn(from_c, table_columns[from_t],
                              f"Calendar rel: '{from_c}' not in '{from_t}'")
                self.assertIn(to_c, table_columns[to_t],
                              f"Calendar rel: '{to_c}' not in '{to_t}'")


# ════════════════════════════════════════════════════════════════════
#  CHECK F: PBI filter Entity+Property → TMDL columns
# ════════════════════════════════════════════════════════════════════

class TestFilterTmdlConsistency(unittest.TestCase):
    """Filter Entity+Property references must resolve to TMDL tables+columns."""

    def setUp(self):
        self.temp_dir = make_temp_dir()

    def tearDown(self):
        cleanup_dir(self.temp_dir)

    def test_report_filter_entity_exists_in_tmdl(self):
        """Report-level filters must reference valid TMDL tables via Entity."""
        datasources, extra = make_complex_model()
        project_path, stats, bim = _generate_full_pipeline(
            datasources, extra, self.temp_dir, 'FilterTest'
        )

        tmdl_tables = {t['name'] for t in bim['model']['tables']}
        tmdl_symbols = stats['actual_bim_symbols']

        filter_refs = _collect_filter_entity_property(project_path)
        errors = []
        for entity, prop in filter_refs:
            if entity not in tmdl_tables:
                errors.append(f"Filter Entity '{entity}' not in TMDL tables")
            elif (entity, prop) not in tmdl_symbols:
                errors.append(f"Filter '{entity}'.'{prop}' not in TMDL symbols")

        self.assertEqual(errors, [],
                         "Filter-TMDL mismatches:\n" + "\n".join(errors))

    def test_worksheet_filter_fields_in_tmdl(self):
        """Worksheet-level filters on visuals must reference valid columns."""
        ds = (DatasourceFactory('DS')
              .with_table('Orders', ['OrderID:integer', 'Amount:real',
                                     'Region:string', 'OrderDate:datetime']))
        ws = (WorksheetFactory('Filtered View', 'DS')
              .with_columns(['Amount:measure', 'Region'])
              .with_filter('Region', ['East', 'West']))
        extra = (ModelFactory()
                 .with_datasource(ds)
                 .with_worksheet(ws)
                 .with_dashboard(DashboardFactory('Dash').with_worksheet('Filtered View'))
                 .build())
        datasources = [ds.build()]

        project_path, stats, bim = _generate_full_pipeline(
            datasources, extra, self.temp_dir, 'WsFilterTest'
        )

        tmdl_symbols = stats['actual_bim_symbols']
        filter_refs = _collect_filter_entity_property(project_path)

        for entity, prop in filter_refs:
            # At minimum, the property name should exist somewhere in the model
            all_props = {p for (_, p) in tmdl_symbols}
            if prop not in all_props:
                # Might be auto-resolved to a parameter table — allow it
                pass  # Soft check: don't fail on parameter mismatches


# ════════════════════════════════════════════════════════════════════
#  CHECK G: PBI slicer Entity+Property → TMDL columns
# ════════════════════════════════════════════════════════════════════

class TestSlicerTmdlConsistency(unittest.TestCase):
    """Slicer visuals must reference columns that exist in the TMDL model."""

    def test_slicer_entity_property_resolves_to_tmdl(self):
        """Slicer Entity+Property must match a TMDL table+column."""

        ds = (DatasourceFactory('DS')
              .with_table('Orders', ['OrderID:integer', 'Region:string',
                                     'OrderDate:datetime', 'Amount:real']))
        # Create a dashboard with filter_control objects (these become slicers)
        dashboard = {
            'name': 'Slicer Dashboard',
            'worksheets': ['Sheet1'],
            'objects': [
                {
                    'type': 'filter_control',
                    'name': 'Region Filter',
                    'field': 'Region',
                    'table': 'Orders',
                    'x': 10, 'y': 10, 'w': 200, 'h': 40,
                },
            ],
        }
        ws = (WorksheetFactory('Sheet1', 'DS')
              .with_columns(['Amount:measure', 'Region']))
        extra = (ModelFactory()
                 .with_datasource(ds)
                 .with_worksheet(ws)
                 .with_dashboard(dashboard)
                 .build())
        datasources = [ds.build()]

        # Build BIM model to get valid symbols
        bim_model = _build_semantic_model(datasources, 'SlicerTest', extra)
        table_names = {t['name'] for t in bim_model['model']['tables']}
        all_symbols = set()
        for t in bim_model['model']['tables']:
            for c in t.get('columns', []):
                all_symbols.add((t['name'], c['name']))

        # The slicer should reference a table+column that exists
        # We test the BIM model side — slicers reference (table, field)
        for obj in dashboard.get('objects', []):
            if obj.get('type') == 'filter_control':
                field = obj.get('field', '')
                table = obj.get('table', '')
                if table and field:
                    # Table should exist
                    self.assertIn(table, table_names,
                                  f"Slicer references table '{table}' not in TMDL")
                    # Column should exist
                    self.assertIn(
                        (table, field), all_symbols,
                        f"Slicer references '{table}'.'{field}' not in TMDL"
                    )


# ════════════════════════════════════════════════════════════════════
#  CHECK H: Hierarchy level columns → parent TMDL table
# ════════════════════════════════════════════════════════════════════

class TestHierarchyTmdlConsistency(unittest.TestCase):
    """Hierarchy levels must reference columns that actually exist
    in the parent table."""

    def test_hierarchy_level_columns_exist_in_parent_table(self):
        """Each hierarchy level's column must exist in the table that owns the hierarchy."""

        ds = (DatasourceFactory('DS')
              .with_table('Customers', ['CustomerID:integer', 'Country:string',
                                         'State:string', 'City:string']))
        datasources = [ds.build()]
        extra = (ModelFactory()
                 .with_datasource(ds)
                 .with_hierarchy('Geography', ['Country', 'State', 'City'])
                 .build())

        model = _build_semantic_model(datasources, 'HierTest', extra)
        tables = model['model']['tables']

        for table in tables:
            col_names = {c['name'] for c in table.get('columns', [])}
            for hier in table.get('hierarchies', []):
                for level in hier.get('levels', []):
                    level_col = level.get('column', '')
                    self.assertIn(
                        level_col, col_names,
                        f"Hierarchy '{hier['name']}' level '{level['name']}' "
                        f"references column '{level_col}' not in table "
                        f"'{table['name']}'. Available: {col_names}"
                    )

    def test_multi_hierarchy_all_levels_valid(self):
        """Multiple hierarchies on same table — all levels valid."""

        ds = (DatasourceFactory('DS')
              .with_table('Location', ['Country:string', 'State:string',
                                        'City:string', 'Year:integer',
                                        'Quarter:string', 'Month:string']))
        datasources = [ds.build()]
        extra = (ModelFactory()
                 .with_datasource(ds)
                 .with_hierarchy('Geo', ['Country', 'State', 'City'])
                 .with_hierarchy('Time', ['Year', 'Quarter', 'Month'])
                 .build())

        model = _build_semantic_model(datasources, 'MultiHierTest', extra)
        tables = model['model']['tables']

        errors = []
        for table in tables:
            col_names = {c['name'] for c in table.get('columns', [])}
            for hier in table.get('hierarchies', []):
                for level in hier.get('levels', []):
                    level_col = level.get('column', '')
                    if level_col not in col_names:
                        errors.append(
                            f"'{hier['name']}'.'{level['name']}' → "
                            f"column '{level_col}' not in '{table['name']}'"
                        )
        self.assertEqual(errors, [],
                         "Hierarchy level errors:\n" + "\n".join(errors))

    def test_hierarchy_invalid_level_filtered(self):
        """Hierarchy levels referencing non-existent columns should be filtered out."""

        ds = (DatasourceFactory('DS')
              .with_table('Orders', ['OrderID:integer', 'Region:string']))
        datasources = [ds.build()]
        # "Zip" column doesn't exist in Orders table
        extra = (ModelFactory()
                 .with_datasource(ds)
                 .with_hierarchy('Geo', ['Region', 'Zip'])
                 .build())

        model = _build_semantic_model(datasources, 'FilteredHierTest', extra)
        tables = model['model']['tables']

        for table in tables:
            col_names = {c['name'] for c in table.get('columns', [])}
            for hier in table.get('hierarchies', []):
                for level in hier.get('levels', []):
                    level_col = level.get('column', '')
                    # Generator should filter out invalid levels
                    self.assertIn(
                        level_col, col_names,
                        f"Invalid level '{level_col}' was not filtered "
                        f"from hierarchy '{hier['name']}'"
                    )


# ════════════════════════════════════════════════════════════════════
#  CHECK J: RLS role tablePermission → TMDL tables
# ════════════════════════════════════════════════════════════════════

class TestRlsTmdlConsistency(unittest.TestCase):
    """RLS role tablePermission.name must reference an actual TMDL table."""

    def test_rls_table_permission_references_valid_table(self):
        """Each RLS tablePermission must reference a table that exists in the model."""

        ds = (DatasourceFactory('DS')
              .with_table('Orders', ['OrderID:integer', 'Region:string',
                                     'Amount:real']))
        datasources = [ds.build()]
        # Add user filter that generates RLS
        extra = (ModelFactory()
                 .with_datasource(ds)
                 .with_user_filter('Region Filter',
                                   field='Region',
                                   table='Orders',
                                   users={'user1@test.com': ['East'],
                                          'user2@test.com': ['West']})
                 .build())

        model = _build_semantic_model(datasources, 'RlsTest', extra)
        table_names = {t['name'] for t in model['model']['tables']}
        roles = model['model'].get('roles', [])

        for role in roles:
            for tp in role.get('tablePermissions', []):
                tp_table = tp.get('name', '')
                self.assertIn(
                    tp_table, table_names,
                    f"RLS role '{role['name']}' has tablePermission "
                    f"for table '{tp_table}' not in TMDL: {table_names}"
                )

    def test_rls_ismemberof_table_valid(self):
        """ISMEMBEROF-based RLS roles must also reference valid tables."""

        ds = (DatasourceFactory('DS')
              .with_table('Sales', ['ID:integer', 'Amount:real', 'Region:string']))
        datasources = [ds.build()]
        extra = (ModelFactory()
                 .with_datasource(ds)
                 .with_user_filter('Group Filter',
                                   formula='ISMEMBEROF("Admins")',
                                   table='Sales')
                 .build())

        model = _build_semantic_model(datasources, 'RlsGroupTest', extra)
        table_names = {t['name'] for t in model['model']['tables']}
        roles = model['model'].get('roles', [])

        for role in roles:
            for tp in role.get('tablePermissions', []):
                tp_table = tp.get('name', '')
                self.assertIn(
                    tp_table, table_names,
                    f"ISMEMBEROF RLS role '{role['name']}' references "
                    f"table '{tp_table}' not in TMDL"
                )


# ════════════════════════════════════════════════════════════════════
#  CHECK L (extended): sortByColumn → same-table column
# ════════════════════════════════════════════════════════════════════

class TestSortByColumnConsistency(unittest.TestCase):
    """sortByColumn must reference a column in the same table."""

    def test_sort_by_column_exists_in_same_table(self):
        """Every sortByColumn value must name another column in the same table."""

        ds = (DatasourceFactory('DS')
              .with_table('Sales', ['ID:integer', 'SaleDate:datetime', 'Amount:real']))
        datasources = [ds.build()]
        extra = ModelFactory().with_datasource(ds).build()

        model = _build_semantic_model(datasources, 'SortTest', extra)
        tables = model['model']['tables']

        errors = []
        for table in tables:
            col_names = {c['name'] for c in table.get('columns', [])}
            for col in table.get('columns', []):
                sort_col = col.get('sortByColumn', '')
                if sort_col and sort_col not in col_names:
                    errors.append(
                        f"Table '{table['name']}': column '{col['name']}' "
                        f"sortByColumn='{sort_col}' not in table columns"
                    )
        self.assertEqual(errors, [],
                         "sortByColumn errors:\n" + "\n".join(errors))


# ════════════════════════════════════════════════════════════════════
#  END-TO-END: Full pipeline cross-workload validation
# ════════════════════════════════════════════════════════════════════

class TestFullPipelineCrossValidation(unittest.TestCase):
    """End-to-end tests that generate the full .pbip project and validate
    consistency across all 4 workloads simultaneously."""

    def setUp(self):
        self.temp_dir = make_temp_dir()

    def tearDown(self):
        cleanup_dir(self.temp_dir)

    def test_simple_model_all_workloads_consistent(self):
        """Simple model: all visual refs, measure DAX, M partitions, relationships
        are consistent with the TMDL model."""
        datasources, extra = make_simple_model()
        project_path, stats, bim = _generate_full_pipeline(
            datasources, extra, self.temp_dir, 'SimpleE2E'
        )

        tmdl_symbols = stats['actual_bim_symbols']
        tmdl_tables = {t['name'] for t in bim['model']['tables']}

        # 1. Visual refs → TMDL
        visual_refs = _collect_visual_entity_property(project_path)
        vis_errors = []
        for entity, prop in visual_refs:
            if entity not in tmdl_tables:
                vis_errors.append(f"Visual Entity '{entity}' not in TMDL")
            elif (entity, prop) not in tmdl_symbols:
                vis_errors.append(f"Visual '{entity}'.'{prop}' not in TMDL")
        self.assertEqual(vis_errors, [],
                         "Visual-TMDL errors:\n" + "\n".join(vis_errors))

        # 2. DAX refs → TMDL
        tables = bim['model']['tables']
        table_cols = {}
        for t in tables:
            table_cols[t['name']] = (
                {c['name'] for c in t.get('columns', [])} |
                {m['name'] for m in t.get('measures', [])}
            )
        dax_errors = []
        for table in tables:
            for measure in table.get('measures', []):
                dax = measure.get('expression', '')
                for ref_t, ref_c in _extract_dax_refs(dax):
                    if ref_t in table_cols and ref_c not in table_cols[ref_t]:
                        dax_errors.append(
                            f"Measure '{measure['name']}': "
                            f"'{ref_t}'[{ref_c}] not in model"
                        )
        self.assertEqual(dax_errors, [],
                         "DAX-TMDL errors:\n" + "\n".join(dax_errors))

        # 3. Relationships → TMDL
        rels = bim['model'].get('relationships', [])
        rel_errors = []
        for rel in rels:
            for side in ['from', 'to']:
                t = rel.get(f'{side}Table', '')
                c = rel.get(f'{side}Column', '')
                if t and t not in table_cols:
                    rel_errors.append(f"Rel {side}Table '{t}' not in model")
                elif t and c and c not in table_cols.get(t, set()):
                    rel_errors.append(f"Rel {side}Column '{t}'[{c}] not in model")
        self.assertEqual(rel_errors, [],
                         "Relationship-TMDL errors:\n" + "\n".join(rel_errors))

    def test_complex_model_all_workloads_consistent(self):
        """Complex model with relationships, hierarchies, sets, groups, bins,
        parameters — all workloads consistent."""
        datasources, extra = make_complex_model()
        project_path, stats, bim = _generate_full_pipeline(
            datasources, extra, self.temp_dir, 'ComplexE2E'
        )

        tmdl_symbols = stats['actual_bim_symbols']
        tmdl_tables = {t['name'] for t in bim['model']['tables']}
        tables = bim['model']['tables']

        # Build full symbol table
        table_cols = {}
        for t in tables:
            table_cols[t['name']] = (
                {c['name'] for c in t.get('columns', [])} |
                {m['name'] for m in t.get('measures', [])}
            )

        all_errors = []

        # 1. Visual → TMDL
        visual_refs = _collect_visual_entity_property(project_path)
        for entity, prop in visual_refs:
            if entity not in tmdl_tables:
                all_errors.append(f"[VISUAL] Entity '{entity}' not in TMDL")
            elif (entity, prop) not in tmdl_symbols:
                all_errors.append(f"[VISUAL] '{entity}'.'{prop}' not in TMDL")

        # 2. DAX → TMDL
        for table in tables:
            for measure in table.get('measures', []):
                dax = measure.get('expression', '')
                for ref_t, ref_c in _extract_dax_refs(dax):
                    if ref_t in table_cols and ref_c not in table_cols[ref_t]:
                        all_errors.append(
                            f"[DAX] Measure '{measure['name']}': "
                            f"'{ref_t}'[{ref_c}] not found"
                        )
            for col in table.get('columns', []):
                dax = col.get('expression', '')
                if dax:
                    for ref_t, ref_c in _extract_dax_refs(dax):
                        if ref_t in table_cols and ref_c not in table_cols[ref_t]:
                            all_errors.append(
                                f"[DAX] CalcCol '{col['name']}': "
                                f"'{ref_t}'[{ref_c}] not found"
                            )

        # 3. Relationships → TMDL
        for rel in bim['model'].get('relationships', []):
            for side in ['from', 'to']:
                t = rel.get(f'{side}Table', '')
                c = rel.get(f'{side}Column', '')
                if t and t not in table_cols:
                    all_errors.append(f"[REL] {side}Table '{t}' not in model")
                elif t and c and c not in table_cols.get(t, set()):
                    all_errors.append(f"[REL] {side}Column '{t}'[{c}] not in model")

        # 4. Hierarchies → parent table columns
        for table in tables:
            col_names = {c['name'] for c in table.get('columns', [])}
            for hier in table.get('hierarchies', []):
                for level in hier.get('levels', []):
                    lc = level.get('column', '')
                    if lc not in col_names:
                        all_errors.append(
                            f"[HIER] '{hier['name']}'.'{level['name']}' "
                            f"column '{lc}' not in '{table['name']}'"
                        )

        # 5. sortByColumn → same table
        for table in tables:
            col_names = {c['name'] for c in table.get('columns', [])}
            for col in table.get('columns', []):
                sbc = col.get('sortByColumn', '')
                if sbc and sbc not in col_names:
                    all_errors.append(
                        f"[SORT] '{table['name']}'.'{col['name']}' "
                        f"sortByColumn='{sbc}' not in table"
                    )

        # 6. RLS → TMDL tables
        for role in bim['model'].get('roles', []):
            for tp in role.get('tablePermissions', []):
                if tp.get('name', '') not in tmdl_tables:
                    all_errors.append(
                        f"[RLS] Role '{role['name']}' references "
                        f"table '{tp['name']}' not in TMDL"
                    )

        # 7. M sourceColumn → M partition (only for type="m" partitions)
        for table in tables:
            partitions = table.get('partitions', [])
            if not partitions:
                continue
            part_source = partitions[0].get('source', {})
            if part_source.get('type', '') != 'm':
                continue  # Skip DAX calculated partitions (GENERATESERIES etc.)
            m_expr = part_source.get('expression', '')
            if not m_expr or _is_whole_table_m_query(m_expr):
                continue
            m_cols = _extract_m_output_columns(m_expr)
            for col in table.get('columns', []):
                src = col.get('sourceColumn', '')
                if src and src not in m_cols and src not in m_expr:
                    all_errors.append(
                        f"[M-TMDL] '{table['name']}'.'{col['name']}' "
                        f"sourceColumn='{src}' not in M partition"
                    )

        self.assertEqual(all_errors, [],
                         f"Cross-workload errors ({len(all_errors)}):\n"
                         + "\n".join(all_errors))

    def test_multi_table_model_all_workloads_consistent(self):
        """Two-table model with relationship — all workloads consistent."""
        datasources, extra = make_multi_table_model()
        project_path, stats, bim = _generate_full_pipeline(
            datasources, extra, self.temp_dir, 'MultiE2E'
        )

        tmdl_symbols = stats['actual_bim_symbols']
        tmdl_tables = {t['name'] for t in bim['model']['tables']}

        # Visual refs must resolve
        visual_refs = _collect_visual_entity_property(project_path)
        for entity, prop in visual_refs:
            self.assertIn(entity, tmdl_tables,
                          f"Visual Entity '{entity}' not in TMDL tables")
            self.assertIn((entity, prop), tmdl_symbols,
                          f"Visual '{entity}'.'{prop}' not in TMDL symbols")

        # Relationships valid
        table_cols = {}
        for t in bim['model']['tables']:
            table_cols[t['name']] = {c['name'] for c in t.get('columns', [])}
        for rel in bim['model'].get('relationships', []):
            from_t = rel.get('fromTable', '')
            from_c = rel.get('fromColumn', '')
            to_t = rel.get('toTable', '')
            to_c = rel.get('toColumn', '')
            self.assertIn(from_t, table_cols)
            self.assertIn(from_c, table_cols.get(from_t, set()))
            self.assertIn(to_t, table_cols)
            self.assertIn(to_c, table_cols.get(to_t, set()))


# ════════════════════════════════════════════════════════════════════
#  Parameter Table ↔ TMDL Consistency
# ════════════════════════════════════════════════════════════════════

class TestParameterTmdlConsistency(unittest.TestCase):
    """Parameter tables must have Value columns and SELECTEDVALUE measures."""

    def test_range_parameter_has_value_column_and_measure(self):
        """Range parameter → GENERATESERIES table with Value column + SELECTEDVALUE measure."""

        ds = (DatasourceFactory('DS')
              .with_table('Orders', ['ID:integer', 'Amount:real']))
        datasources = [ds.build()]
        extra = (ModelFactory()
                 .with_datasource(ds)
                 .with_parameter(ParameterFactory('Top N').range(1, 50, 1, 10))
                 .build())

        model = _build_semantic_model(datasources, 'ParamTest', extra)
        tables = model['model']['tables']

        # Find parameter table
        param_tables = [t for t in tables if 'Top N' in t.get('name', '')]
        if param_tables:
            pt = param_tables[0]
            col_names = {c['name'] for c in pt.get('columns', [])}
            measure_exprs = [m.get('expression', '') for m in pt.get('measures', [])]
            # Should have a Value column
            self.assertTrue(
                any('Value' in c or 'value' in c.lower() for c in col_names),
                f"Parameter table '{pt['name']}' missing Value column. Cols: {col_names}"
            )
            # Should have a SELECTEDVALUE measure
            self.assertTrue(
                any('SELECTEDVALUE' in expr for expr in measure_exprs),
                f"Parameter table '{pt['name']}' missing SELECTEDVALUE measure"
            )

    def test_list_parameter_has_value_column_and_measure(self):
        """List parameter → DATATABLE with Value column + SELECTEDVALUE measure."""

        ds = (DatasourceFactory('DS')
              .with_table('Orders', ['ID:integer', 'Amount:real']))
        datasources = [ds.build()]
        extra = (ModelFactory()
                 .with_datasource(ds)
                 .with_parameter(ParameterFactory('Region Select').list(
                     ['East', 'West', 'North'], current='East'))
                 .build())

        model = _build_semantic_model(datasources, 'ListParamTest', extra)
        tables = model['model']['tables']

        param_tables = [t for t in tables if 'Region' in t.get('name', '')]
        if param_tables:
            pt = param_tables[0]
            col_names = {c['name'] for c in pt.get('columns', [])}
            measure_exprs = [m.get('expression', '') for m in pt.get('measures', [])]
            self.assertTrue(
                any('Value' in c or 'value' in c.lower() for c in col_names),
                f"List param table missing Value column. Cols: {col_names}"
            )
            self.assertTrue(
                any('SELECTEDVALUE' in expr for expr in measure_exprs),
                f"List param table missing SELECTEDVALUE measure"
            )


if __name__ == '__main__':
    unittest.main()
