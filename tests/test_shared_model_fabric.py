"""
Tests for Shared Semantic Model + Fabric-native output (Sprint 98).

Validates that --shared-model --output-format fabric produces:
- Lakehouse definition with merged tables from multiple workbooks
- Dataflow Gen2 queries for all merged datasources
- PySpark Notebook for transformations
- DirectLake SemanticModel from merged data
- Data Pipeline orchestrating all above
- Thin reports referencing the DirectLake model via byPath
"""

import json
import os
import sys
import tempfile
import shutil

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, 'powerbi_import'))
sys.path.insert(0, ROOT_DIR)


# ── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp(prefix='fabric_merge_test_')
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _make_ds(name, conn_type='SQL Server', server='srv', database='db',
             tables=None, relationships=None):
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
        'calculations': [],
        'relationships': relationships or [],
    }


def _make_table(name, columns):
    return {
        'name': name,
        'columns': [{'name': c, 'datatype': 'string'} for c in columns],
    }


def _make_converted(datasources, calculations=None, worksheets=None,
                    parameters=None):
    return {
        'datasources': datasources,
        'worksheets': worksheets or [],
        'dashboards': [],
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


@pytest.fixture
def two_workbooks():
    """Two workbooks with overlapping tables (Orders shared, Products unique)."""
    wb1 = _make_converted([
        _make_ds('Sales', tables=[
            _make_table('Orders', ['OrderID', 'Product', 'Amount']),
            _make_table('Customers', ['CustID', 'Name']),
        ]),
    ], calculations=[
        {'name': 'Total Sales', 'caption': 'Total Sales',
         'formula': 'SUM([Amount])', 'role': 'measure', 'datatype': 'real'},
    ])
    wb2 = _make_converted([
        _make_ds('Sales', tables=[
            _make_table('Orders', ['OrderID', 'Product', 'Quantity']),
            _make_table('Products', ['ProductID', 'Category']),
        ]),
    ], calculations=[
        {'name': 'Total Qty', 'caption': 'Total Qty',
         'formula': 'SUM([Quantity])', 'role': 'measure', 'datatype': 'integer'},
    ])
    return [wb1, wb2], ['SalesReport', 'InventoryReport']


# ═══════════════════════════════════════════════════════════════════
#  Tests
# ═══════════════════════════════════════════════════════════════════

class TestSharedModelFabricIntegration:
    """Integration: import_shared_model with output_format='fabric'."""

    def test_fabric_output_creates_lakehouse(self, temp_dir, two_workbooks):
        """Fabric output must include a .Lakehouse directory."""
        all_converted, wb_names = two_workbooks
        from import_to_powerbi import PowerBIImporter

        importer = PowerBIImporter()
        result = importer.import_shared_model(
            model_name='MergedModel',
            all_converted_objects=all_converted,
            workbook_names=wb_names,
            output_dir=temp_dir,
            output_format='fabric',
            force_merge=True,
        )

        assert result.get('model_path') or result.get('assessment')
        # Check Lakehouse artifact exists
        project_dir = os.path.join(temp_dir, 'MergedModel')
        lakehouse_dirs = [
            d for d in os.listdir(project_dir)
            if d.endswith('.Lakehouse')
        ] if os.path.exists(project_dir) else []
        assert len(lakehouse_dirs) >= 1, "Expected .Lakehouse directory"

    def test_fabric_output_creates_semantic_model(self, temp_dir, two_workbooks):
        """Fabric output must include a .SemanticModel directory."""
        all_converted, wb_names = two_workbooks
        from import_to_powerbi import PowerBIImporter

        importer = PowerBIImporter()
        result = importer.import_shared_model(
            model_name='MergedModel',
            all_converted_objects=all_converted,
            workbook_names=wb_names,
            output_dir=temp_dir,
            output_format='fabric',
            force_merge=True,
        )

        project_dir = os.path.join(temp_dir, 'MergedModel')
        sm_dirs = [
            d for d in os.listdir(project_dir)
            if d.endswith('.SemanticModel')
        ] if os.path.exists(project_dir) else []
        assert len(sm_dirs) >= 1, "Expected .SemanticModel directory"

    def test_fabric_output_creates_dataflow(self, temp_dir, two_workbooks):
        """Fabric output must include a .Dataflow directory."""
        all_converted, wb_names = two_workbooks
        from import_to_powerbi import PowerBIImporter

        importer = PowerBIImporter()
        importer.import_shared_model(
            model_name='MergedModel',
            all_converted_objects=all_converted,
            workbook_names=wb_names,
            output_dir=temp_dir,
            output_format='fabric',
            force_merge=True,
        )

        project_dir = os.path.join(temp_dir, 'MergedModel')
        df_dirs = [
            d for d in os.listdir(project_dir)
            if d.endswith('.Dataflow')
        ] if os.path.exists(project_dir) else []
        assert len(df_dirs) >= 1, "Expected .Dataflow directory"

    def test_fabric_output_creates_pipeline(self, temp_dir, two_workbooks):
        """Fabric output must include a .Pipeline directory."""
        all_converted, wb_names = two_workbooks
        from import_to_powerbi import PowerBIImporter

        importer = PowerBIImporter()
        importer.import_shared_model(
            model_name='MergedModel',
            all_converted_objects=all_converted,
            workbook_names=wb_names,
            output_dir=temp_dir,
            output_format='fabric',
            force_merge=True,
        )

        project_dir = os.path.join(temp_dir, 'MergedModel')
        pipe_dirs = [
            d for d in os.listdir(project_dir)
            if d.endswith('.Pipeline')
        ] if os.path.exists(project_dir) else []
        assert len(pipe_dirs) >= 1, "Expected .Pipeline directory"

    def test_fabric_output_creates_notebook(self, temp_dir, two_workbooks):
        """Fabric output must include a .Notebook directory."""
        all_converted, wb_names = two_workbooks
        from import_to_powerbi import PowerBIImporter

        importer = PowerBIImporter()
        importer.import_shared_model(
            model_name='MergedModel',
            all_converted_objects=all_converted,
            workbook_names=wb_names,
            output_dir=temp_dir,
            output_format='fabric',
            force_merge=True,
        )

        project_dir = os.path.join(temp_dir, 'MergedModel')
        nb_dirs = [
            d for d in os.listdir(project_dir)
            if d.endswith('.Notebook')
        ] if os.path.exists(project_dir) else []
        assert len(nb_dirs) >= 1, "Expected .Notebook directory"


class TestFabricThinReports:
    """Thin reports must be generated inside the Fabric project with byPath."""

    def test_thin_reports_generated(self, temp_dir, two_workbooks):
        """Each workbook gets a thin report inside the Fabric project."""
        all_converted, wb_names = two_workbooks
        from import_to_powerbi import PowerBIImporter

        importer = PowerBIImporter()
        result = importer.import_shared_model(
            model_name='MergedModel',
            all_converted_objects=all_converted,
            workbook_names=wb_names,
            output_dir=temp_dir,
            output_format='fabric',
            force_merge=True,
        )

        report_paths = result.get('report_paths', [])
        assert len(report_paths) == 2
        for rp in report_paths:
            assert os.path.exists(rp), f"Report path should exist: {rp}"

    def test_thin_report_bypath_references_semantic_model(self, temp_dir, two_workbooks):
        """Thin report definition.pbir must reference the SemanticModel via byPath."""
        all_converted, wb_names = two_workbooks
        from import_to_powerbi import PowerBIImporter

        importer = PowerBIImporter()
        result = importer.import_shared_model(
            model_name='MergedModel',
            all_converted_objects=all_converted,
            workbook_names=wb_names,
            output_dir=temp_dir,
            output_format='fabric',
            force_merge=True,
        )

        report_paths = result.get('report_paths', [])
        assert len(report_paths) >= 1
        for rp in report_paths:
            pbir_path = os.path.join(rp, 'definition.pbir')
            assert os.path.exists(pbir_path), f"definition.pbir missing in {rp}"
            with open(pbir_path, 'r') as f:
                pbir = json.load(f)
            ds_ref = pbir.get('datasetReference', {})
            by_path = ds_ref.get('byPath', {}).get('path', '')
            assert 'MergedModel.SemanticModel' in by_path, \
                f"byPath should reference MergedModel.SemanticModel, got: {by_path}"

    def test_no_model_explorer_report_for_fabric(self, temp_dir, two_workbooks):
        """Fabric output should NOT create a .pbip model-explorer wrapper."""
        all_converted, wb_names = two_workbooks
        from import_to_powerbi import PowerBIImporter

        importer = PowerBIImporter()
        importer.import_shared_model(
            model_name='MergedModel',
            all_converted_objects=all_converted,
            workbook_names=wb_names,
            output_dir=temp_dir,
            output_format='fabric',
            force_merge=True,
        )

        project_dir = os.path.join(temp_dir, 'MergedModel')
        # Only the model-explorer .pbip should be absent; thin report .pbip files are expected
        model_explorer_pbip = os.path.join(project_dir, 'MergedModel.pbip')
        assert not os.path.exists(model_explorer_pbip), \
            "Fabric output should not create model-explorer .pbip file"


class TestFabricMergedContent:
    """Verify the merged data flows through to Fabric artifacts correctly."""

    def test_lakehouse_has_merged_tables(self, temp_dir, two_workbooks):
        """Lakehouse should contain tables from both workbooks."""
        all_converted, wb_names = two_workbooks
        from import_to_powerbi import PowerBIImporter

        importer = PowerBIImporter()
        importer.import_shared_model(
            model_name='MergedModel',
            all_converted_objects=all_converted,
            workbook_names=wb_names,
            output_dir=temp_dir,
            output_format='fabric',
            force_merge=True,
        )

        project_dir = os.path.join(temp_dir, 'MergedModel')
        # Find table metadata
        metadata_path = None
        for root, dirs, files in os.walk(project_dir):
            for f in files:
                if f == 'table_metadata.json':
                    metadata_path = os.path.join(root, f)
                    break

        assert metadata_path is not None, "table_metadata.json should exist"
        with open(metadata_path) as f:
            meta = json.load(f)
        # table_metadata.json is {lakehouse_name, tables: [{name, ...}, ...]}
        tables_list = meta.get('tables', meta) if isinstance(meta, dict) else meta
        table_names = [t.get('name', '') for t in tables_list] if isinstance(tables_list, list) else list(tables_list.keys())
        # Orders should be merged from both workbooks
        assert any('order' in t.lower() for t in table_names), \
            f"Expected 'Orders' table in merged lakehouse, got: {table_names}"

    def test_pbip_output_format_unchanged(self, temp_dir, two_workbooks):
        """Default (pbip) format should still work and produce .SemanticModel."""
        all_converted, wb_names = two_workbooks
        from import_to_powerbi import PowerBIImporter

        importer = PowerBIImporter()
        result = importer.import_shared_model(
            model_name='PbipModel',
            all_converted_objects=all_converted,
            workbook_names=wb_names,
            output_dir=temp_dir,
            output_format='pbip',
            force_merge=True,
        )

        assert result.get('model_path') is not None
        # Should NOT have Lakehouse artifacts
        project_dir = os.path.join(temp_dir, 'PbipModel')
        lakehouse_dirs = [
            d for d in os.listdir(project_dir)
            if d.endswith('.Lakehouse')
        ] if os.path.exists(project_dir) else []
        assert len(lakehouse_dirs) == 0, "PBIP format should not create Lakehouse"


class TestRunSharedModelMigrationFabric:
    """Test run_shared_model_migration with output_format='fabric'."""

    def test_output_format_parameter_accepted(self):
        """run_shared_model_migration should accept output_format parameter."""
        import inspect
        from migrate import run_shared_model_migration
        sig = inspect.signature(run_shared_model_migration)
        assert 'output_format' in sig.parameters

    def test_import_shared_model_accepts_output_format(self):
        """import_shared_model should accept output_format parameter."""
        import inspect
        from import_to_powerbi import PowerBIImporter
        sig = inspect.signature(PowerBIImporter.import_shared_model)
        assert 'output_format' in sig.parameters
        # Default should be 'pbip'
        assert sig.parameters['output_format'].default == 'pbip'
