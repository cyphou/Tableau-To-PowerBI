"""
Tests for Fabric-native artifact generation (Sprint 91).

Tests cover:
- fabric_constants: type maps, AGG_PATTERN
- fabric_naming: sanitisation functions
- calc_column_utils: classification, M/PySpark conversion
- LakehouseGenerator: table schemas, DDL, metadata
- DataflowGenerator: M queries, mashup, definitions
- NotebookGenerator: PySpark ETL notebooks
- PipelineGenerator: 3-stage pipeline orchestration
- FabricSemanticModelGenerator: DirectLake metadata
- FabricProjectGenerator: full orchestration
"""

import json
import os
import sys
import tempfile
import shutil
import pytest

# Ensure powerbi_import is importable
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'powerbi_import'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__))))


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def temp_dir():
    """Create a temporary directory for test output."""
    d = tempfile.mkdtemp(prefix='fabric_test_')
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def sample_extracted_data():
    """Minimal extracted Tableau data for testing."""
    return {
        'datasources': [
            {
                'name': 'Sample DS',
                'connection': {
                    'type': 'SQL Server',
                    'details': {
                        'server': 'myserver.database.windows.net',
                        'database': 'SalesDB',
                    },
                },
                'tables': [
                    {
                        'name': 'Orders',
                        'columns': [
                            {'name': 'OrderID', 'datatype': 'integer'},
                            {'name': 'CustomerName', 'datatype': 'string'},
                            {'name': 'OrderDate', 'datatype': 'datetime'},
                            {'name': 'Amount', 'datatype': 'real'},
                            {'name': 'Region', 'datatype': 'string'},
                        ],
                    },
                    {
                        'name': 'Customers',
                        'columns': [
                            {'name': 'CustomerID', 'datatype': 'integer'},
                            {'name': 'Name', 'datatype': 'string'},
                            {'name': 'City', 'datatype': 'string'},
                        ],
                    },
                ],
            },
        ],
        'calculations': [
            {
                'name': 'Profit Ratio',
                'caption': 'Profit Ratio',
                'formula': '[Profit] / [Sales]',
                'role': 'dimension',
                'datatype': 'real',
            },
            {
                'name': 'Total Sales',
                'caption': 'Total Sales',
                'formula': 'SUM([Sales])',
                'role': 'measure',
                'datatype': 'real',
            },
        ],
        'custom_sql': [
            {
                'name': 'Custom Query 1',
                'query': 'SELECT * FROM vw_Sales WHERE Year = 2024',
                'datasource': 'Sample DS',
            },
        ],
        'worksheets': [],
        'dashboards': [{'name': 'Sales Dashboard'}],
        'parameters': [],
        'filters': [],
        'stories': [],
        'actions': [],
        'sets': [],
        'groups': [],
        'bins': [],
        'hierarchies': [],
        'sort_orders': [],
        'aliases': {},
        'user_filters': [],
    }


@pytest.fixture
def sample_extracted_no_calcs():
    """Extracted data without calculations."""
    return {
        'datasources': [
            {
                'name': 'Simple DS',
                'connection': {'type': 'CSV', 'details': {'filename': 'data.csv'}},
                'tables': [
                    {
                        'name': 'Products',
                        'columns': [
                            {'name': 'ProductID', 'datatype': 'integer'},
                            {'name': 'ProductName', 'datatype': 'string'},
                        ],
                    },
                ],
            },
        ],
        'calculations': [],
        'custom_sql': [],
        'worksheets': [],
        'dashboards': [],
        'parameters': [],
        'filters': [],
        'stories': [],
        'actions': [],
        'sets': [],
        'groups': [],
        'bins': [],
        'hierarchies': [],
        'sort_orders': [],
        'aliases': {},
        'user_filters': [],
    }


# ════════════════════════════════════════════════════════════════════
#  fabric_constants
# ════════════════════════════════════════════════════════════════════

class TestFabricConstants:
    """Tests for fabric_constants module."""

    def test_spark_type_map_string(self):
        from powerbi_import.fabric_constants import map_to_spark_type
        assert map_to_spark_type('string') == 'STRING'

    def test_spark_type_map_integer(self):
        from powerbi_import.fabric_constants import map_to_spark_type
        assert map_to_spark_type('integer') == 'INT'

    def test_spark_type_map_datetime(self):
        from powerbi_import.fabric_constants import map_to_spark_type
        assert map_to_spark_type('datetime') == 'TIMESTAMP'

    def test_spark_type_map_unknown_defaults_to_string(self):
        from powerbi_import.fabric_constants import map_to_spark_type
        assert map_to_spark_type('unknown_type') == 'STRING'

    def test_spark_type_map_case_insensitive(self):
        from powerbi_import.fabric_constants import map_to_spark_type
        assert map_to_spark_type('INTEGER') == 'INT'

    def test_pyspark_type_map_exists(self):
        from powerbi_import.fabric_constants import PYSPARK_TYPE_MAP
        assert 'string' in PYSPARK_TYPE_MAP
        assert PYSPARK_TYPE_MAP['string'] == 'StringType()'

    def test_agg_pattern_matches_sum(self):
        from powerbi_import.fabric_constants import AGG_PATTERN
        assert AGG_PATTERN.search('SUM([Sales])')

    def test_agg_pattern_matches_count(self):
        from powerbi_import.fabric_constants import AGG_PATTERN
        assert AGG_PATTERN.search('COUNT([Orders])')

    def test_agg_pattern_no_match_simple_ref(self):
        from powerbi_import.fabric_constants import AGG_PATTERN
        assert not AGG_PATTERN.search('[Region]')

    def test_fabric_artifacts_list(self):
        from powerbi_import.fabric_constants import FABRIC_ARTIFACTS
        assert 'lakehouse' in FABRIC_ARTIFACTS
        assert 'dataflow' in FABRIC_ARTIFACTS
        assert 'notebook' in FABRIC_ARTIFACTS
        assert 'semanticmodel' in FABRIC_ARTIFACTS
        assert 'pipeline' in FABRIC_ARTIFACTS

    def test_spark_type_map_currency(self):
        from powerbi_import.fabric_constants import map_to_spark_type
        assert map_to_spark_type('currency') == 'DECIMAL(19,4)'

    def test_spark_type_map_boolean(self):
        from powerbi_import.fabric_constants import map_to_spark_type
        assert map_to_spark_type('boolean') == 'BOOLEAN'

    def test_spark_type_map_date(self):
        from powerbi_import.fabric_constants import map_to_spark_type
        assert map_to_spark_type('date') == 'DATE'

    def test_spark_type_map_real(self):
        from powerbi_import.fabric_constants import map_to_spark_type
        assert map_to_spark_type('real') == 'DOUBLE'

    def test_agg_pattern_matches_running_sum(self):
        from powerbi_import.fabric_constants import AGG_PATTERN
        assert AGG_PATTERN.search('RUNNING_SUM(SUM([Sales]))')

    def test_agg_pattern_matches_rankx(self):
        from powerbi_import.fabric_constants import AGG_PATTERN
        assert AGG_PATTERN.search('RANKX(ALL(Table), [Measure])')


# ════════════════════════════════════════════════════════════════════
#  fabric_naming
# ════════════════════════════════════════════════════════════════════

class TestFabricNaming:
    """Tests for fabric_naming module."""

    def test_sanitize_table_name_basic(self):
        from powerbi_import.fabric_naming import sanitize_table_name
        assert sanitize_table_name('My Table') == 'my_table'

    def test_sanitize_table_name_brackets(self):
        from powerbi_import.fabric_naming import sanitize_table_name
        assert sanitize_table_name('[dbo].[Orders]') == 'orders'

    def test_sanitize_table_name_leading_digits(self):
        from powerbi_import.fabric_naming import sanitize_table_name
        assert sanitize_table_name('123table') == 'table'

    def test_sanitize_table_name_empty(self):
        from powerbi_import.fabric_naming import sanitize_table_name
        assert sanitize_table_name('') == 'table'

    def test_sanitize_column_name_basic(self):
        from powerbi_import.fabric_naming import sanitize_column_name
        assert sanitize_column_name('Order Date') == 'Order_Date'

    def test_sanitize_column_name_empty(self):
        from powerbi_import.fabric_naming import sanitize_column_name
        assert sanitize_column_name('') == 'column'

    def test_sanitize_query_name_allows_spaces(self):
        from powerbi_import.fabric_naming import sanitize_query_name
        assert sanitize_query_name('My Query') == 'My Query'

    def test_sanitize_pipeline_name(self):
        from powerbi_import.fabric_naming import sanitize_pipeline_name
        assert sanitize_pipeline_name('My Pipeline!') == 'My_Pipeline'

    def test_make_python_var(self):
        from powerbi_import.fabric_naming import make_python_var
        assert make_python_var('Order Table') == 'order_table'

    def test_make_python_var_leading_digit(self):
        from powerbi_import.fabric_naming import make_python_var
        assert make_python_var('123data') == 'data'

    def test_sanitize_filesystem_name(self):
        from powerbi_import.fabric_naming import sanitize_filesystem_name
        result = sanitize_filesystem_name('My:Report<test>')
        assert ':' not in result
        assert '<' not in result
        assert '>' not in result

    def test_sanitize_table_name_schema_prefix(self):
        from powerbi_import.fabric_naming import sanitize_table_name
        assert sanitize_table_name('schema.TableName') == 'tablename'

    def test_sanitize_column_name_special_chars(self):
        from powerbi_import.fabric_naming import sanitize_column_name
        result = sanitize_column_name('[Order-ID]')
        assert result.isidentifier() or result.replace('_', '').isalnum()


# ════════════════════════════════════════════════════════════════════
#  calc_column_utils
# ════════════════════════════════════════════════════════════════════

class TestCalcColumnUtils:
    """Tests for calc_column_utils module."""

    def test_classify_calc_columns_vs_measures(self):
        from powerbi_import.calc_column_utils import classify_calculations
        calcs = [
            {'name': 'cc1', 'formula': '[A] + [B]', 'role': 'dimension', 'datatype': 'real'},
            {'name': 'm1', 'formula': 'SUM([Sales])', 'role': 'measure', 'datatype': 'real'},
        ]
        cc, measures = classify_calculations(calcs)
        assert len(cc) == 1
        assert cc[0]['name'] == 'cc1'
        assert cc[0]['spark_type'] == 'DOUBLE'
        assert len(measures) == 1
        assert measures[0]['name'] == 'm1'

    def test_classify_empty_formula_skipped(self):
        from powerbi_import.calc_column_utils import classify_calculations
        calcs = [{'name': 'empty', 'formula': '', 'role': 'dimension'}]
        cc, measures = classify_calculations(calcs)
        assert len(cc) == 0
        assert len(measures) == 0

    def test_classify_literal_as_measure(self):
        from powerbi_import.calc_column_utils import classify_calculations
        calcs = [{'name': 'lit', 'formula': '42', 'role': 'measure', 'datatype': 'integer'}]
        cc, measures = classify_calculations(calcs)
        assert len(cc) == 0
        assert len(measures) == 1

    def test_sanitize_calc_col_name(self):
        from powerbi_import.calc_column_utils import sanitize_calc_col_name
        assert sanitize_calc_col_name('Profit Ratio (%)') == 'profit_ratio'

    def test_sanitize_calc_col_name_empty(self):
        from powerbi_import.calc_column_utils import sanitize_calc_col_name
        assert sanitize_calc_col_name('') == 'calc_col'

    def test_tableau_formula_to_m_if_then(self):
        from powerbi_import.calc_column_utils import tableau_formula_to_m
        result = tableau_formula_to_m('IF [A] > 0 THEN "Yes" ELSE "No" END')
        assert 'if' in result
        assert 'then' in result
        assert 'else' in result
        assert 'END' not in result

    def test_tableau_formula_to_m_upper(self):
        from powerbi_import.calc_column_utils import tableau_formula_to_m
        result = tableau_formula_to_m('UPPER([Name])')
        assert 'Text.Upper' in result

    def test_tableau_formula_to_m_left(self):
        from powerbi_import.calc_column_utils import tableau_formula_to_m
        result = tableau_formula_to_m('LEFT([Code], 3)')
        assert 'Text.Start' in result

    def test_make_m_add_column_step(self):
        from powerbi_import.calc_column_utils import make_m_add_column_step
        line, step_name = make_m_add_column_step('[A] + [B]', 'Total', 'PrevStep')
        assert 'Table.AddColumn' in line
        assert 'PrevStep' in line
        assert 'Total' in line
        assert step_name.startswith('CalcCol_')

    def test_tableau_formula_to_pyspark_if(self):
        from powerbi_import.calc_column_utils import tableau_formula_to_pyspark
        result = tableau_formula_to_pyspark('IF [A] > 0 THEN 1 ELSE 0 END', 'Flag')
        assert 'withColumn' in result
        assert 'F.when' in result

    def test_tableau_formula_to_pyspark_column_ref(self):
        from powerbi_import.calc_column_utils import tableau_formula_to_pyspark
        result = tableau_formula_to_pyspark('[Region]', 'RegionCopy')
        assert 'F.col("Region")' in result

    def test_tableau_formula_to_pyspark_arithmetic(self):
        from powerbi_import.calc_column_utils import tableau_formula_to_pyspark
        result = tableau_formula_to_pyspark('[A] * [B]', 'Product')
        assert 'withColumn' in result

    def test_classify_dimension_without_agg(self):
        from powerbi_import.calc_column_utils import classify_calculations
        calcs = [{'name': 'dim', 'formula': '[A]', 'role': 'dimension', 'datatype': 'string'}]
        cc, _ = classify_calculations(calcs)
        assert len(cc) == 1

    def test_classify_measure_with_window_func(self):
        from powerbi_import.calc_column_utils import classify_calculations
        calcs = [{'name': 'w', 'formula': 'WINDOW_SUM(SUM([Sales]), -2, 0)', 'role': 'measure', 'datatype': 'real'}]
        _, measures = classify_calculations(calcs)
        assert len(measures) == 1


# ════════════════════════════════════════════════════════════════════
#  LakehouseGenerator
# ════════════════════════════════════════════════════════════════════

class TestLakehouseGenerator:
    """Tests for LakehouseGenerator."""

    def test_generate_creates_lakehouse_dir(self, temp_dir, sample_extracted_data):
        from powerbi_import.lakehouse_generator import LakehouseGenerator
        gen = LakehouseGenerator(temp_dir, 'TestProject')
        gen.generate(sample_extracted_data)
        assert os.path.isdir(os.path.join(temp_dir, 'TestProject.Lakehouse'))

    def test_generate_creates_definition_json(self, temp_dir, sample_extracted_data):
        from powerbi_import.lakehouse_generator import LakehouseGenerator
        gen = LakehouseGenerator(temp_dir, 'TestProject')
        gen.generate(sample_extracted_data)
        def_path = os.path.join(temp_dir, 'TestProject.Lakehouse', 'lakehouse_definition.json')
        assert os.path.isfile(def_path)
        with open(def_path, 'r') as f:
            data = json.load(f)
        assert '$schema' in data
        assert 'tables' in data

    def test_generate_returns_stats(self, temp_dir, sample_extracted_data):
        from powerbi_import.lakehouse_generator import LakehouseGenerator
        gen = LakehouseGenerator(temp_dir, 'TestProject')
        stats = gen.generate(sample_extracted_data)
        assert stats['tables'] >= 2  # Orders + Customers
        assert stats['columns'] > 0

    def test_generate_includes_calc_columns(self, temp_dir, sample_extracted_data):
        from powerbi_import.lakehouse_generator import LakehouseGenerator
        gen = LakehouseGenerator(temp_dir, 'TestProject')
        stats = gen.generate(sample_extracted_data)
        assert stats['calc_columns'] >= 1

    def test_generate_creates_ddl(self, temp_dir, sample_extracted_data):
        from powerbi_import.lakehouse_generator import LakehouseGenerator
        gen = LakehouseGenerator(temp_dir, 'TestProject')
        gen.generate(sample_extracted_data)
        ddl_dir = os.path.join(temp_dir, 'TestProject.Lakehouse', 'ddl')
        assert os.path.isdir(ddl_dir)
        sql_files = [f for f in os.listdir(ddl_dir) if f.endswith('.sql')]
        assert len(sql_files) >= 1

    def test_generate_creates_table_metadata(self, temp_dir, sample_extracted_data):
        from powerbi_import.lakehouse_generator import LakehouseGenerator
        gen = LakehouseGenerator(temp_dir, 'TestProject')
        gen.generate(sample_extracted_data)
        meta_path = os.path.join(temp_dir, 'TestProject.Lakehouse', 'table_metadata.json')
        assert os.path.isfile(meta_path)

    def test_generate_deduplicates_tables(self, temp_dir):
        from powerbi_import.lakehouse_generator import LakehouseGenerator
        data = {
            'datasources': [
                {
                    'name': 'DS1',
                    'connection': {'type': 'CSV', 'details': {}},
                    'tables': [
                        {'name': 'Sales', 'columns': [{'name': 'ID', 'datatype': 'integer'}]},
                        {'name': 'Sales', 'columns': [{'name': 'ID', 'datatype': 'integer'}]},
                    ],
                },
            ],
            'calculations': [],
            'custom_sql': [],
        }
        gen = LakehouseGenerator(temp_dir, 'Dedup')
        stats = gen.generate(data)
        assert stats['tables'] == 1

    def test_generate_handles_custom_sql(self, temp_dir, sample_extracted_data):
        from powerbi_import.lakehouse_generator import LakehouseGenerator
        gen = LakehouseGenerator(temp_dir, 'TestProject')
        stats = gen.generate(sample_extracted_data)
        # custom_sql should add another table
        assert stats['tables'] >= 3

    def test_no_calcs_no_crash(self, temp_dir, sample_extracted_no_calcs):
        from powerbi_import.lakehouse_generator import LakehouseGenerator
        gen = LakehouseGenerator(temp_dir, 'NoCalcs')
        stats = gen.generate(sample_extracted_no_calcs)
        assert stats['calc_columns'] == 0

    def test_ddl_contains_delta(self, temp_dir, sample_extracted_data):
        from powerbi_import.lakehouse_generator import LakehouseGenerator
        gen = LakehouseGenerator(temp_dir, 'TestProject')
        gen.generate(sample_extracted_data)
        combined = os.path.join(temp_dir, 'TestProject.Lakehouse', 'ddl', '_all_tables.sql')
        if os.path.exists(combined):
            with open(combined) as f:
                content = f.read()
            assert 'USING DELTA' in content


# ════════════════════════════════════════════════════════════════════
#  DataflowGenerator
# ════════════════════════════════════════════════════════════════════

class TestDataflowGenerator:
    """Tests for DataflowGenerator."""

    def test_generate_creates_dataflow_dir(self, temp_dir, sample_extracted_data):
        from powerbi_import.dataflow_generator import DataflowGenerator
        gen = DataflowGenerator(temp_dir, 'TestProject')
        gen.generate(sample_extracted_data)
        assert os.path.isdir(os.path.join(temp_dir, 'TestProject.Dataflow'))

    def test_generate_creates_definition_json(self, temp_dir, sample_extracted_data):
        from powerbi_import.dataflow_generator import DataflowGenerator
        gen = DataflowGenerator(temp_dir, 'TestProject')
        gen.generate(sample_extracted_data)
        def_path = os.path.join(temp_dir, 'TestProject.Dataflow', 'dataflow_definition.json')
        assert os.path.isfile(def_path)
        with open(def_path) as f:
            data = json.load(f)
        assert data['$schema'].endswith('schema.json')
        assert 'queries' in data

    def test_generate_returns_stats(self, temp_dir, sample_extracted_data):
        from powerbi_import.dataflow_generator import DataflowGenerator
        gen = DataflowGenerator(temp_dir, 'TestProject')
        stats = gen.generate(sample_extracted_data)
        assert stats['queries'] >= 2
        assert 'calc_columns' in stats

    def test_generate_creates_m_query_files(self, temp_dir, sample_extracted_data):
        from powerbi_import.dataflow_generator import DataflowGenerator
        gen = DataflowGenerator(temp_dir, 'TestProject')
        gen.generate(sample_extracted_data)
        queries_dir = os.path.join(temp_dir, 'TestProject.Dataflow', 'queries')
        assert os.path.isdir(queries_dir)
        m_files = [f for f in os.listdir(queries_dir) if f.endswith('.m')]
        assert len(m_files) >= 1

    def test_generate_creates_mashup_file(self, temp_dir, sample_extracted_data):
        from powerbi_import.dataflow_generator import DataflowGenerator
        gen = DataflowGenerator(temp_dir, 'TestProject')
        gen.generate(sample_extracted_data)
        mashup_path = os.path.join(temp_dir, 'TestProject.Dataflow', 'mashup.pq')
        assert os.path.isfile(mashup_path)

    def test_definition_has_lakehouse_destination(self, temp_dir, sample_extracted_data):
        from powerbi_import.dataflow_generator import DataflowGenerator
        gen = DataflowGenerator(temp_dir, 'TestProject')
        gen.generate(sample_extracted_data)
        def_path = os.path.join(temp_dir, 'TestProject.Dataflow', 'dataflow_definition.json')
        with open(def_path) as f:
            data = json.load(f)
        for q in data['queries']:
            assert q['destination']['type'] == 'Lakehouse'
            assert q['destination']['updateMethod'] == 'Replace'

    def test_no_calcs_no_crash(self, temp_dir, sample_extracted_no_calcs):
        from powerbi_import.dataflow_generator import DataflowGenerator
        gen = DataflowGenerator(temp_dir, 'NoCalcs')
        stats = gen.generate(sample_extracted_no_calcs)
        assert stats['calc_columns'] == 0

    def test_custom_sql_query_generated(self, temp_dir, sample_extracted_data):
        from powerbi_import.dataflow_generator import DataflowGenerator
        gen = DataflowGenerator(temp_dir, 'TestProject')
        stats = gen.generate(sample_extracted_data)
        assert stats['queries'] >= 3  # 2 tables + 1 custom SQL


# ════════════════════════════════════════════════════════════════════
#  NotebookGenerator
# ════════════════════════════════════════════════════════════════════

class TestNotebookGenerator:
    """Tests for NotebookGenerator."""

    def test_generate_creates_notebook_dir(self, temp_dir, sample_extracted_data):
        from powerbi_import.notebook_generator import NotebookGenerator
        gen = NotebookGenerator(temp_dir, 'TestProject')
        gen.generate(sample_extracted_data)
        assert os.path.isdir(os.path.join(temp_dir, 'TestProject.Notebook'))

    def test_generate_creates_etl_notebook(self, temp_dir, sample_extracted_data):
        from powerbi_import.notebook_generator import NotebookGenerator
        gen = NotebookGenerator(temp_dir, 'TestProject')
        gen.generate(sample_extracted_data)
        etl_path = os.path.join(temp_dir, 'TestProject.Notebook', 'etl_pipeline.ipynb')
        assert os.path.isfile(etl_path)
        with open(etl_path) as f:
            nb = json.load(f)
        assert nb['nbformat'] == 4
        assert nb['metadata']['kernelspec']['name'] == 'synapse_pyspark'

    def test_generate_creates_transformations_notebook(self, temp_dir, sample_extracted_data):
        from powerbi_import.notebook_generator import NotebookGenerator
        gen = NotebookGenerator(temp_dir, 'TestProject')
        gen.generate(sample_extracted_data)
        transform_path = os.path.join(temp_dir, 'TestProject.Notebook', 'transformations.ipynb')
        assert os.path.isfile(transform_path)

    def test_generate_returns_stats(self, temp_dir, sample_extracted_data):
        from powerbi_import.notebook_generator import NotebookGenerator
        gen = NotebookGenerator(temp_dir, 'TestProject')
        stats = gen.generate(sample_extracted_data)
        assert stats['notebooks'] >= 2
        assert stats['cells'] > 0
        assert stats['calc_columns'] >= 1

    def test_etl_notebook_has_lakehouse_metadata(self, temp_dir, sample_extracted_data):
        from powerbi_import.notebook_generator import NotebookGenerator
        gen = NotebookGenerator(temp_dir, 'TestProject')
        gen.generate(sample_extracted_data)
        etl_path = os.path.join(temp_dir, 'TestProject.Notebook', 'etl_pipeline.ipynb')
        with open(etl_path) as f:
            nb = json.load(f)
        trident = nb['metadata'].get('trident', {})
        assert 'lakehouse' in trident
        assert 'TestProject_Lakehouse' in trident['lakehouse']['default_lakehouse_name']

    def test_no_calcs_single_notebook(self, temp_dir, sample_extracted_no_calcs):
        from powerbi_import.notebook_generator import NotebookGenerator
        gen = NotebookGenerator(temp_dir, 'NoCalcs')
        stats = gen.generate(sample_extracted_no_calcs)
        assert stats['notebooks'] == 1
        assert stats['calc_columns'] == 0

    def test_etl_has_code_cells(self, temp_dir, sample_extracted_data):
        from powerbi_import.notebook_generator import NotebookGenerator
        gen = NotebookGenerator(temp_dir, 'TestProject')
        gen.generate(sample_extracted_data)
        etl_path = os.path.join(temp_dir, 'TestProject.Notebook', 'etl_pipeline.ipynb')
        with open(etl_path) as f:
            nb = json.load(f)
        code_cells = [c for c in nb['cells'] if c['cell_type'] == 'code']
        assert len(code_cells) >= 2


# ════════════════════════════════════════════════════════════════════
#  PipelineGenerator
# ════════════════════════════════════════════════════════════════════

class TestPipelineGenerator:
    """Tests for PipelineGenerator."""

    def test_generate_creates_pipeline_dir(self, temp_dir, sample_extracted_data):
        from powerbi_import.pipeline_generator import PipelineGenerator
        gen = PipelineGenerator(temp_dir, 'TestPipeline')
        gen.generate(sample_extracted_data)
        assert os.path.isdir(os.path.join(temp_dir, 'TestPipeline.Pipeline'))

    def test_generate_creates_definition_json(self, temp_dir, sample_extracted_data):
        from powerbi_import.pipeline_generator import PipelineGenerator
        gen = PipelineGenerator(temp_dir, 'TestPipeline')
        gen.generate(sample_extracted_data)
        def_path = os.path.join(temp_dir, 'TestPipeline.Pipeline', 'pipeline_definition.json')
        assert os.path.isfile(def_path)
        with open(def_path) as f:
            data = json.load(f)
        assert data['$schema'].endswith('schema.json')
        assert 'activities' in data['properties']

    def test_generate_returns_stats(self, temp_dir, sample_extracted_data):
        from powerbi_import.pipeline_generator import PipelineGenerator
        gen = PipelineGenerator(temp_dir, 'TestPipeline')
        stats = gen.generate(sample_extracted_data)
        assert stats['activities'] >= 3  # dataflow + notebook + semantic model
        assert stats['stages'] >= 2

    def test_pipeline_has_3_stage_activities(self, temp_dir, sample_extracted_data):
        from powerbi_import.pipeline_generator import PipelineGenerator
        gen = PipelineGenerator(temp_dir, 'TestPipeline')
        gen.generate(sample_extracted_data)
        def_path = os.path.join(temp_dir, 'TestPipeline.Pipeline', 'pipeline_definition.json')
        with open(def_path) as f:
            data = json.load(f)
        activities = data['properties']['activities']
        types = [a['type'] for a in activities]
        assert 'RefreshDataflow' in types
        assert 'TridentNotebook' in types
        assert 'TridentDatasetRefresh' in types

    def test_pipeline_creates_platform_file(self, temp_dir, sample_extracted_data):
        from powerbi_import.pipeline_generator import PipelineGenerator
        gen = PipelineGenerator(temp_dir, 'TestPipeline')
        gen.generate(sample_extracted_data)
        platform_path = os.path.join(temp_dir, 'TestPipeline.Pipeline', '.platform')
        assert os.path.isfile(platform_path)
        with open(platform_path) as f:
            data = json.load(f)
        assert data['metadata']['type'] == 'DataPipeline'

    def test_pipeline_metadata_json(self, temp_dir, sample_extracted_data):
        from powerbi_import.pipeline_generator import PipelineGenerator
        gen = PipelineGenerator(temp_dir, 'TestPipeline')
        gen.generate(sample_extracted_data)
        meta_path = os.path.join(temp_dir, 'TestPipeline.Pipeline', 'pipeline_metadata.json')
        assert os.path.isfile(meta_path)

    def test_notebook_depends_on_dataflow(self, temp_dir, sample_extracted_data):
        from powerbi_import.pipeline_generator import PipelineGenerator
        gen = PipelineGenerator(temp_dir, 'TestPipeline')
        gen.generate(sample_extracted_data)
        def_path = os.path.join(temp_dir, 'TestPipeline.Pipeline', 'pipeline_definition.json')
        with open(def_path) as f:
            data = json.load(f)
        activities = data['properties']['activities']
        nb = [a for a in activities if a['type'] == 'TridentNotebook'][0]
        assert len(nb['dependsOn']) > 0

    def test_semantic_model_depends_on_notebook(self, temp_dir, sample_extracted_data):
        from powerbi_import.pipeline_generator import PipelineGenerator
        gen = PipelineGenerator(temp_dir, 'TestPipeline')
        gen.generate(sample_extracted_data)
        def_path = os.path.join(temp_dir, 'TestPipeline.Pipeline', 'pipeline_definition.json')
        with open(def_path) as f:
            data = json.load(f)
        activities = data['properties']['activities']
        sm = [a for a in activities if a['type'] == 'TridentDatasetRefresh'][0]
        dep_names = [d['activity'] for d in sm['dependsOn']]
        assert 'Run_ETL_Notebook' in dep_names


# ════════════════════════════════════════════════════════════════════
#  FabricSemanticModelGenerator
# ════════════════════════════════════════════════════════════════════

class TestFabricSemanticModelGenerator:
    """Tests for FabricSemanticModelGenerator."""

    def test_generate_creates_sm_dir(self, temp_dir, sample_extracted_data):
        from powerbi_import.fabric_semantic_model_generator import FabricSemanticModelGenerator
        gen = FabricSemanticModelGenerator(temp_dir, 'TestModel')
        gen.generate(sample_extracted_data)
        assert os.path.isdir(os.path.join(temp_dir, 'TestModel.SemanticModel'))

    def test_generate_creates_definition_dir(self, temp_dir, sample_extracted_data):
        from powerbi_import.fabric_semantic_model_generator import FabricSemanticModelGenerator
        gen = FabricSemanticModelGenerator(temp_dir, 'TestModel')
        gen.generate(sample_extracted_data)
        def_dir = os.path.join(temp_dir, 'TestModel.SemanticModel', 'definition')
        assert os.path.isdir(def_dir)

    def test_generate_creates_platform_file(self, temp_dir, sample_extracted_data):
        from powerbi_import.fabric_semantic_model_generator import FabricSemanticModelGenerator
        gen = FabricSemanticModelGenerator(temp_dir, 'TestModel')
        gen.generate(sample_extracted_data)
        platform = os.path.join(temp_dir, 'TestModel.SemanticModel', '.platform')
        assert os.path.isfile(platform)
        with open(platform) as f:
            data = json.load(f)
        assert data['metadata']['type'] == 'SemanticModel'

    def test_generate_creates_metadata_with_directlake(self, temp_dir, sample_extracted_data):
        from powerbi_import.fabric_semantic_model_generator import FabricSemanticModelGenerator
        gen = FabricSemanticModelGenerator(temp_dir, 'TestModel')
        gen.generate(sample_extracted_data)
        meta = os.path.join(temp_dir, 'TestModel.SemanticModel', 'semantic_model_metadata.json')
        assert os.path.isfile(meta)
        with open(meta) as f:
            data = json.load(f)
        assert data['mode'] == 'DirectLake'

    def test_generate_returns_stats(self, temp_dir, sample_extracted_data):
        from powerbi_import.fabric_semantic_model_generator import FabricSemanticModelGenerator
        gen = FabricSemanticModelGenerator(temp_dir, 'TestModel')
        stats = gen.generate(sample_extracted_data)
        assert isinstance(stats, dict)
        assert 'tables' in stats

    def test_custom_lakehouse_name(self, temp_dir, sample_extracted_data):
        from powerbi_import.fabric_semantic_model_generator import FabricSemanticModelGenerator
        gen = FabricSemanticModelGenerator(temp_dir, 'TestModel', lakehouse_name='MyLakehouse')
        gen.generate(sample_extracted_data)
        meta = os.path.join(temp_dir, 'TestModel.SemanticModel', 'semantic_model_metadata.json')
        with open(meta) as f:
            data = json.load(f)
        assert data['lakehouse'] == 'MyLakehouse'


# ════════════════════════════════════════════════════════════════════
#  FabricProjectGenerator (orchestrator)
# ════════════════════════════════════════════════════════════════════

class TestFabricProjectGenerator:
    """Tests for FabricProjectGenerator end-to-end orchestration."""

    def test_generate_project_creates_all_artifacts(self, temp_dir, sample_extracted_data):
        from powerbi_import.fabric_project_generator import FabricProjectGenerator
        gen = FabricProjectGenerator(output_dir=temp_dir)
        results = gen.generate_project('TestProject', sample_extracted_data)

        project_dir = results['project_path']
        assert os.path.isdir(project_dir)
        assert os.path.isdir(os.path.join(project_dir, 'TestProject.Lakehouse'))
        assert os.path.isdir(os.path.join(project_dir, 'TestProject.Dataflow'))
        assert os.path.isdir(os.path.join(project_dir, 'TestProject.Notebook'))
        assert os.path.isdir(os.path.join(project_dir, 'TestProject.SemanticModel'))
        assert os.path.isdir(os.path.join(project_dir, 'TestProject.Pipeline'))

    def test_generate_project_returns_full_stats(self, temp_dir, sample_extracted_data):
        from powerbi_import.fabric_project_generator import FabricProjectGenerator
        gen = FabricProjectGenerator(output_dir=temp_dir)
        results = gen.generate_project('TestProject', sample_extracted_data)

        assert 'artifacts' in results
        assert 'lakehouse' in results['artifacts']
        assert 'dataflow' in results['artifacts']
        assert 'notebook' in results['artifacts']
        assert 'semantic_model' in results['artifacts']
        assert 'pipeline' in results['artifacts']

    def test_generate_project_creates_metadata(self, temp_dir, sample_extracted_data):
        from powerbi_import.fabric_project_generator import FabricProjectGenerator
        gen = FabricProjectGenerator(output_dir=temp_dir)
        results = gen.generate_project('TestProject', sample_extracted_data)
        meta_path = os.path.join(results['project_path'], 'fabric_project_metadata.json')
        assert os.path.isfile(meta_path)

    def test_generate_project_with_culture(self, temp_dir, sample_extracted_data):
        from powerbi_import.fabric_project_generator import FabricProjectGenerator
        gen = FabricProjectGenerator(output_dir=temp_dir)
        results = gen.generate_project('TestProject', sample_extracted_data,
                                       culture='fr-FR')
        assert results['project_path']

    def test_generate_project_with_no_data(self, temp_dir):
        from powerbi_import.fabric_project_generator import FabricProjectGenerator
        gen = FabricProjectGenerator(output_dir=temp_dir)
        empty = {
            'datasources': [], 'calculations': [], 'custom_sql': [],
            'worksheets': [], 'dashboards': [], 'parameters': [],
            'filters': [], 'stories': [], 'actions': [],
            'sets': [], 'groups': [], 'bins': [],
            'hierarchies': [], 'sort_orders': [], 'aliases': {},
            'user_filters': [],
        }
        results = gen.generate_project('Empty', empty)
        assert results['artifacts']['lakehouse']['tables'] == 0

    def test_project_metadata_has_generated_at(self, temp_dir, sample_extracted_data):
        from powerbi_import.fabric_project_generator import FabricProjectGenerator
        gen = FabricProjectGenerator(output_dir=temp_dir)
        results = gen.generate_project('TestProject', sample_extracted_data)
        assert 'generated_at' in results


# ════════════════════════════════════════════════════════════════════
#  CLI integration (--output-format fabric)
# ════════════════════════════════════════════════════════════════════

class TestCLIFabricFormat:
    """Tests that the CLI argument parser accepts 'fabric' as output-format."""

    def test_parser_accepts_fabric_format(self):
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        import migrate
        parser = migrate._build_argument_parser()
        args = parser.parse_args(['dummy.twbx', '--output-format', 'fabric'])
        assert args.output_format == 'fabric'

    def test_parser_still_accepts_pbip(self):
        import migrate
        parser = migrate._build_argument_parser()
        args = parser.parse_args(['dummy.twbx', '--output-format', 'pbip'])
        assert args.output_format == 'pbip'

    def test_parser_default_is_pbip(self):
        import migrate
        parser = migrate._build_argument_parser()
        args = parser.parse_args(['dummy.twbx'])
        assert args.output_format == 'pbip'
