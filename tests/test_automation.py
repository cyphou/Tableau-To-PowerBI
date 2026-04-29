"""Tests for Sprint 119 — Post-migration automation features.

Covers:
    1. Validator auto-fix for Tableau DAX leaks
    2. Lineage map generation
    3. Unified --qa flag
    4. Default-ON CLI flags
    5. RLS PowerShell script generation
    6. Credential template generation
    7. Governance enforcement with column renames
"""

import json
import os
import sys
import tempfile

import pytest

# ── Path setup ──────────────────────────────────────────────────────────
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, 'powerbi_import'))
sys.path.insert(0, ROOT_DIR)


# ════════════════════════════════════════════════════════════════════════
# 1. Validator auto-fix
# ════════════════════════════════════════════════════════════════════════

class TestValidatorAutoFix:
    """Test ArtifactValidator.auto_fix_dax_leaks and related methods."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from validator import ArtifactValidator
        self.V = ArtifactValidator

    # ── Individual replacements ───────────────────────────────────────

    def test_fix_countd(self):
        formula = "COUNTD([Customer])"
        fixed, repairs = self.V.auto_fix_dax_leaks(formula)
        assert "DISTINCTCOUNT(" in fixed
        assert "COUNTD" not in fixed
        assert len(repairs) == 1

    def test_fix_zn(self):
        formula = "ZN([Sales])"
        fixed, repairs = self.V.auto_fix_dax_leaks(formula)
        assert "IF(ISBLANK(" in fixed
        assert "ZN" not in fixed.upper().replace("IF(ISBLANK(", "")

    def test_fix_ifnull(self):
        formula = "IFNULL([Profit], 0)"
        fixed, repairs = self.V.auto_fix_dax_leaks(formula)
        assert "IF(ISBLANK(" in fixed

    def test_fix_attr(self):
        formula = "ATTR([Region])"
        fixed, repairs = self.V.auto_fix_dax_leaks(formula)
        assert "VALUES(" in fixed
        assert "ATTR" not in fixed

    def test_fix_double_equals(self):
        formula = "IF([Status] == 'Active', 1, 0)"
        fixed, repairs = self.V.auto_fix_dax_leaks(formula)
        assert "==" not in fixed
        assert "= 'Active'" in fixed

    def test_fix_elseif(self):
        formula = "IF([A] > 1, 'X' ELSEIF [A] > 0, 'Y', 'Z')"
        fixed, repairs = self.V.auto_fix_dax_leaks(formula)
        assert "ELSEIF" not in fixed
        # ELSEIF replaced with comma for DAX nested IF
        assert "," in fixed

    def test_fix_datetrunc_month(self):
        formula = "DATETRUNC('month', [Order Date])"
        fixed, repairs = self.V.auto_fix_dax_leaks(formula)
        assert "STARTOFMONTH(" in fixed
        assert "DATETRUNC" not in fixed

    def test_fix_datetrunc_quarter(self):
        formula = "DATETRUNC('quarter', [Date])"
        fixed, repairs = self.V.auto_fix_dax_leaks(formula)
        assert "STARTOFQUARTER(" in fixed

    def test_fix_datetrunc_year(self):
        formula = "DATETRUNC('year', [Date])"
        fixed, repairs = self.V.auto_fix_dax_leaks(formula)
        assert "STARTOFYEAR(" in fixed

    def test_fix_datepart_year(self):
        formula = "DATEPART('year', [Order Date])"
        fixed, repairs = self.V.auto_fix_dax_leaks(formula)
        assert "YEAR(" in fixed
        assert "DATEPART" not in fixed

    def test_fix_datepart_month(self):
        formula = "DATEPART('month', [Date])"
        fixed, repairs = self.V.auto_fix_dax_leaks(formula)
        assert "MONTH(" in fixed

    def test_fix_datepart_day(self):
        formula = "DATEPART('day', [Date])"
        fixed, repairs = self.V.auto_fix_dax_leaks(formula)
        assert "DAY(" in fixed

    def test_fix_datepart_quarter(self):
        formula = "DATEPART('quarter', [Date])"
        fixed, repairs = self.V.auto_fix_dax_leaks(formula)
        assert "QUARTER(" in fixed

    def test_fix_datepart_hour(self):
        formula = "DATEPART('hour', [Timestamp])"
        fixed, repairs = self.V.auto_fix_dax_leaks(formula)
        assert "HOUR(" in fixed

    def test_fix_datepart_minute(self):
        formula = "DATEPART('minute', [Timestamp])"
        fixed, repairs = self.V.auto_fix_dax_leaks(formula)
        assert "MINUTE(" in fixed

    def test_fix_datepart_second(self):
        formula = "DATEPART('second', [Timestamp])"
        fixed, repairs = self.V.auto_fix_dax_leaks(formula)
        assert "SECOND(" in fixed

    # ── Multiple leaks in one formula ─────────────────────────────────

    def test_fix_multiple_leaks(self):
        formula = "IF(COUNTD([Cust]) == 1, ZN([Sales]), 0)"
        fixed, repairs = self.V.auto_fix_dax_leaks(formula)
        assert "DISTINCTCOUNT(" in fixed
        assert "IF(ISBLANK(" in fixed
        assert "==" not in fixed
        assert len(repairs) == 3

    # ── No-op on clean formulas ───────────────────────────────────────

    def test_clean_formula_no_fix(self):
        formula = "SUM([Sales])"
        fixed, repairs = self.V.auto_fix_dax_leaks(formula)
        assert fixed == formula
        assert repairs == []

    def test_empty_formula(self):
        fixed, repairs = self.V.auto_fix_dax_leaks("")
        assert fixed == ""
        assert repairs == []

    def test_none_formula(self):
        fixed, repairs = self.V.auto_fix_dax_leaks(None)
        assert fixed is None
        assert repairs == []

    # ── TMDL file auto-fix ────────────────────────────────────────────

    def test_auto_fix_tmdl_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tmdl',
                                          delete=False, encoding='utf-8') as f:
            f.write("table 'Sales'\n")
            f.write("\tmeasure 'Count' = COUNTD([Customer])\n")
            f.write("\tcolumn 'Region'\n")
            f.write("\t\tdataType: string\n")
            tmp = f.name
        try:
            repairs = self.V.auto_fix_tmdl_file(tmp)
            assert len(repairs) > 0
            with open(tmp, 'r', encoding='utf-8') as f:
                content = f.read()
            assert "DISTINCTCOUNT(" in content
            assert "COUNTD(" not in content
        finally:
            os.unlink(tmp)

    def test_auto_fix_tmdl_dry_run(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tmdl',
                                          delete=False, encoding='utf-8') as f:
            f.write("table 'Test'\n")
            f.write("\tmeasure 'M' = ZN([Val])\n")
            tmp = f.name
        try:
            repairs = self.V.auto_fix_tmdl_file(tmp, dry_run=True)
            assert len(repairs) > 0
            # File should NOT be modified
            with open(tmp, 'r', encoding='utf-8') as f:
                content = f.read()
            assert "ZN(" in content
        finally:
            os.unlink(tmp)

    def test_auto_fix_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm_dir = os.path.join(tmpdir, 'Test.SemanticModel', 'definition', 'tables')
            os.makedirs(sm_dir)
            tmdl_path = os.path.join(sm_dir, 'Sales.tmdl')
            with open(tmdl_path, 'w', encoding='utf-8') as f:
                f.write("table 'Sales'\n")
                f.write("\tmeasure 'Total' = COUNTD([Customer])\n")
                f.write("\tmeasure 'Safe' = SUM([Amount])\n")

            result = self.V.auto_fix_project(tmpdir)
            assert result['total_repairs'] >= 1
            assert 'Sales.tmdl' in result['file_repairs']

    def test_auto_fix_skips_m_expressions(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tmdl',
                                          delete=False, encoding='utf-8') as f:
            f.write("table 'Data'\n")
            f.write("\texpression = let Source = Sql.Database(\"server\", \"db\") in Source\n")
            tmp = f.name
        try:
            repairs = self.V.auto_fix_tmdl_file(tmp)
            assert repairs == []
        finally:
            os.unlink(tmp)


# ════════════════════════════════════════════════════════════════════════
# 2. Lineage map generation
# ════════════════════════════════════════════════════════════════════════

class TestLineageMap:
    """Test lineage map generation from tmdl_generator."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from tmdl_generator import _build_lineage_map
        self._build = _build_lineage_map

    def test_basic_lineage(self):
        tables = [
            {'name': 'Orders', 'measures': [{'name': 'Total Sales'}], 'columns': []},
            {'name': 'Products', 'measures': [], 'columns': [{'name': 'Name', 'type': 'calculated'}]},
        ]
        rels = [{'fromTable': 'Orders', 'fromColumn': 'ProductID',
                 'toTable': 'Products', 'toColumn': 'ProductID',
                 'cardinality': 'manyToOne'}]
        extra = {
            'worksheets': [{'name': 'Sales Dashboard'}],
            'calculations': [{'caption': 'Total Sales', 'formula': 'SUM([Sales])'}],
        }
        datasources = [{'name': 'Sample', 'tables': [{'name': 'Orders'}, {'name': 'Products'}]}]

        lineage = self._build(tables, rels, extra, datasources)
        assert len(lineage['tables']) == 2
        assert lineage['tables'][0]['pbi_table'] == 'Orders'
        assert len(lineage['calculations']) >= 1
        assert lineage['calculations'][0]['pbi_type'] == 'measure'
        assert len(lineage['relationships']) == 1
        assert len(lineage['worksheets']) == 1
        assert lineage['worksheets'][0]['tableau_worksheet'] == 'Sales Dashboard'

    def test_empty_input(self):
        lineage = self._build([], [], {}, [])
        assert lineage['tables'] == []
        assert lineage['calculations'] == []
        assert lineage['relationships'] == []
        assert lineage['worksheets'] == []

    def test_calculated_column_lineage(self):
        tables = [{'name': 'T1', 'measures': [], 'columns': [
            {'name': 'CalcCol', 'type': 'calculated'},
            {'name': 'RegularCol', 'type': 'string'},
        ]}]
        lineage = self._build(tables, [], {}, [])
        calc_entries = [e for e in lineage['calculations'] if e['pbi_type'] == 'calculatedColumn']
        assert len(calc_entries) == 1
        assert calc_entries[0]['pbi_object'] == 'CalcCol'

    def test_datasource_tracking(self):
        tables = [{'name': 'Orders', 'measures': [], 'columns': []}]
        datasources = [{'name': 'MyDS', 'tables': [{'name': 'Orders'}]}]
        lineage = self._build(tables, [], {}, datasources)
        assert lineage['tables'][0]['tableau_datasource'] == 'MyDS'


# ════════════════════════════════════════════════════════════════════════
# 3. Unified --qa flag
# ════════════════════════════════════════════════════════════════════════

class TestQAFlag:
    """Test the --qa CLI argument is properly registered."""

    def test_qa_arg_exists(self):
        """The --qa flag should be registered in argparse."""
        import argparse
        # Quick regex scan of migrate.py for --qa
        migrate_path = os.path.join(ROOT_DIR, 'migrate.py')
        with open(migrate_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert "'--qa'" in content or '"--qa"' in content

    def test_qa_suite_function_exists(self):
        """_run_qa_suite should be defined in migrate.py."""
        migrate_path = os.path.join(ROOT_DIR, 'migrate.py')
        with open(migrate_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'def _run_qa_suite(' in content


# ════════════════════════════════════════════════════════════════════════
# 4. Default-ON CLI flags
# ════════════════════════════════════════════════════════════════════════

class TestDefaultONFlags:
    """Test that --optimize-dax and --compare default to True."""

    def test_optimize_dax_default_true(self):
        migrate_path = os.path.join(ROOT_DIR, 'migrate.py')
        with open(migrate_path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Find the --optimize-dax definition and check default=True
        import re
        match = re.search(r"'--optimize-dax'.*?default=(\w+)", content, re.DOTALL)
        assert match, "--optimize-dax arg not found"
        assert match.group(1) == "True", f"Expected default=True, got {match.group(1)}"

    def test_compare_default_true(self):
        migrate_path = os.path.join(ROOT_DIR, 'migrate.py')
        with open(migrate_path, 'r', encoding='utf-8') as f:
            content = f.read()
        import re
        match = re.search(r"'--compare'.*?default=(\w+)", content, re.DOTALL)
        assert match, "--compare arg not found"
        assert match.group(1) == "True", f"Expected default=True, got {match.group(1)}"

    def test_no_optimize_dax_flag_exists(self):
        migrate_path = os.path.join(ROOT_DIR, 'migrate.py')
        with open(migrate_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert "'--no-optimize-dax'" in content or '"--no-optimize-dax"' in content

    def test_no_compare_flag_exists(self):
        migrate_path = os.path.join(ROOT_DIR, 'migrate.py')
        with open(migrate_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert "'--no-compare'" in content or '"--no-compare"' in content


# ════════════════════════════════════════════════════════════════════════
# 5. RLS PowerShell script generation
# ════════════════════════════════════════════════════════════════════════

class TestRLSPowerShell:
    """Test generate_rls_powershell."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from permission_mapper import generate_rls_powershell
        self.gen = generate_rls_powershell

    def test_basic_generation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, 'assign_rls_roles.ps1')
            roles = [
                {'name': 'Sales Region', 'members': ['alice@corp.com', 'bob@corp.com']},
                {'name': 'Admin', 'members': []},
            ]
            result = self.gen(roles, out, dataset_name='TestDS')
            assert result == out
            assert os.path.isfile(out)

            with open(out, 'r', encoding='utf-8') as f:
                content = f.read()
            assert 'Sales Region' in content
            assert 'alice@corp.com' in content
            assert 'bob@corp.com' in content
            assert 'Connect-PowerBIServiceAccount' in content
            assert 'Invoke-PowerBIRestMethod' in content
            assert 'TestDS' in content

    def test_empty_roles(self):
        result = self.gen([], '/tmp/empty.ps1')
        assert result is None

    def test_none_roles(self):
        result = self.gen(None, '/tmp/none.ps1')
        assert result is None

    def test_member_email_conversion(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, 'test.ps1')
            roles = [{'name': 'R', 'members': ['jdoe']}]
            self.gen(roles, out)
            with open(out, 'r', encoding='utf-8') as f:
                content = f.read()
            # Non-email usernames get @yourdomain.com appended
            assert 'jdoe@yourdomain.com' in content

    def test_role_name_sanitized(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, 'test.ps1')
            roles = [{'name': 'Region-West (US)', 'members': []}]
            self.gen(roles, out)
            with open(out, 'r', encoding='utf-8') as f:
                content = f.read()
            # Variable names should be sanitized (no special chars)
            assert '$Role_Region_West__US_' in content

    def test_large_member_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, 'test.ps1')
            members = [f'user{i}@corp.com' for i in range(25)]
            roles = [{'name': 'BigRole', 'members': members}]
            self.gen(roles, out)
            with open(out, 'r', encoding='utf-8') as f:
                content = f.read()
            assert '... and 15 more' in content


# ════════════════════════════════════════════════════════════════════════
# 6. Credential template generation
# ════════════════════════════════════════════════════════════════════════

class TestCredentialTemplate:
    """Test generate_credential_template."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from permission_mapper import generate_credential_template
        self.gen = generate_credential_template

    def test_basic_template(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, 'creds.json')
            datasources = [{
                'name': 'MyDB',
                'connection': {
                    'class': 'sqlserver',
                    'server': 'myserver.database.windows.net',
                    'dbname': 'sales_db',
                    'port': '1433',
                    'authentication': 'sql',
                },
            }]
            result = self.gen(datasources, out)
            assert result == out

            with open(out, 'r', encoding='utf-8') as f:
                data = json.load(f)
            assert len(data['connections']) == 1
            conn = data['connections'][0]
            assert conn['server'] == 'myserver.database.windows.net'
            assert conn['database'] == 'sales_db'
            assert conn['username'] == 'YOUR_USERNAME'
            assert conn['password'] == 'YOUR_PASSWORD'

    def test_cloud_connector_oauth(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, 'creds.json')
            datasources = [{
                'name': 'BigQuery',
                'connection': {'class': 'bigquery', 'server': 'bq.googleapis.com'},
            }]
            self.gen(datasources, out)
            with open(out, 'r', encoding='utf-8') as f:
                data = json.load(f)
            conn = data['connections'][0]
            assert 'oauth_token' in conn
            assert 'service_account_key_path' in conn

    def test_deduplication(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, 'creds.json')
            ds = {
                'name': 'DS1',
                'connection': {'class': 'postgres', 'server': 'pg1', 'dbname': 'db1'},
            }
            self.gen([ds, ds], out)
            with open(out, 'r', encoding='utf-8') as f:
                data = json.load(f)
            assert len(data['connections']) == 1

    def test_empty_datasources(self):
        result = self.gen([], '/tmp/empty.json')
        assert result is None

    def test_connection_map_extraction(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, 'creds.json')
            datasources = [{
                'name': 'Multi',
                'connection_map': {
                    'conn1': {'class': 'sqlserver', 'server': 's1', 'dbname': 'd1'},
                    'conn2': {'class': 'postgres', 'server': 's2', 'dbname': 'd2'},
                },
            }]
            self.gen(datasources, out)
            with open(out, 'r', encoding='utf-8') as f:
                data = json.load(f)
            assert len(data['connections']) == 2


# ════════════════════════════════════════════════════════════════════════
# 7. Governance enforcement — column renames
# ════════════════════════════════════════════════════════════════════════

class TestGovernanceEnforcement:
    """Test enhanced governance apply_renames with column support."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from governance import GovernanceEngine, GovernanceReport, GovernanceIssue
        self.Engine = GovernanceEngine
        self.Report = GovernanceReport
        self.Issue = GovernanceIssue

    def test_column_rename_in_enforce_mode(self):
        engine = self.Engine({"mode": "enforce", "naming": {"column_style": "snake_case"}})
        tables = [{'name': 'Orders', 'columns': [
            {'name': 'OrderDate'},
            {'name': 'customer_id'},
        ], 'measures': []}]
        report = engine.check(tables)
        count = engine.apply_renames(tables, report)
        # OrderDate should be renamed to snake_case
        col_names = [c['name'] for c in tables[0]['columns']]
        assert 'order_date' in col_names
        assert 'customer_id' in col_names  # already snake_case, unchanged
        assert count >= 1

    def test_warn_mode_no_renames(self):
        engine = self.Engine({"mode": "warn", "naming": {"column_style": "snake_case"}})
        tables = [{'name': 'T', 'columns': [{'name': 'BadName'}], 'measures': []}]
        report = engine.check(tables)
        count = engine.apply_renames(tables, report)
        assert count == 0
        assert tables[0]['columns'][0]['name'] == 'BadName'

    def test_table_rename_enforce(self):
        engine = self.Engine({"mode": "enforce", "naming": {"table_style": "PascalCase"}})
        tables = [{'name': 'order_items', 'columns': [], 'measures': []}]
        report = engine.check(tables)
        count = engine.apply_renames(tables, report)
        assert tables[0]['name'] == 'OrderItems'
        assert count >= 1

    def test_measure_prefix_enforce(self):
        engine = self.Engine({"mode": "enforce", "naming": {"measure_prefix": "m_"}})
        tables = [{'name': 'T', 'columns': [], 'measures': [{'name': 'TotalSales'}]}]
        report = engine.check(tables)
        count = engine.apply_renames(tables, report)
        assert tables[0]['measures'][0]['name'] == 'm_TotalSales'
        assert count >= 1

    def test_pii_classification_applied(self):
        engine = self.Engine({"mode": "warn", "pii_detection": True})
        tables = [{'name': 'T', 'columns': [
            {'name': 'email_address'},
            {'name': 'order_total'},
        ], 'measures': []}]
        report = engine.check(tables)
        engine.apply_classifications(tables, report)
        email_col = tables[0]['columns'][0]
        assert any(a.get('name') == 'dataClassification' for a in email_col.get('annotations', []))
        # order_total should NOT have classification
        order_col = tables[0]['columns'][1]
        assert not order_col.get('annotations')


# ════════════════════════════════════════════════════════════════════════
# 8. Integration — permission_mapper module structure
# ════════════════════════════════════════════════════════════════════════

class TestPermissionMapperModule:
    """Test that the permission_mapper module is importable and complete."""

    def test_import(self):
        from permission_mapper import generate_rls_powershell, generate_credential_template
        assert callable(generate_rls_powershell)
        assert callable(generate_credential_template)

    def test_auto_fix_integration(self):
        """Validator auto-fix methods are accessible as class methods."""
        from validator import ArtifactValidator
        assert hasattr(ArtifactValidator, 'auto_fix_dax_leaks')
        assert hasattr(ArtifactValidator, 'auto_fix_tmdl_file')
        assert hasattr(ArtifactValidator, 'auto_fix_project')


# ════════════════════════════════════════════════════════════════════
#  Lineage Map — HTML Report Visualization
# ════════════════════════════════════════════════════════════════════

class TestLineageHTMLReport:
    """Tests for lineage map visualization in the HTML migration dashboard."""

    SAMPLE_LINEAGE = {
        'tables': [
            {'tableau_datasource': 'Sample - Superstore', 'tableau_table': 'Orders', 'pbi_table': 'Orders'},
            {'tableau_datasource': 'Sample - Superstore', 'tableau_table': 'People', 'pbi_table': 'People'},
        ],
        'calculations': [
            {'tableau_calculation': 'SUM([Sales])', 'pbi_table': 'Orders', 'pbi_object': 'Total Sales', 'pbi_type': 'measure'},
            {'tableau_calculation': 'Profit Ratio', 'pbi_table': 'Orders', 'pbi_object': 'Profit Ratio', 'pbi_type': 'calculatedColumn'},
        ],
        'relationships': [
            {'from': 'Orders[Region]', 'to': 'People[Region]', 'cardinality': 'manyToOne'},
        ],
        'worksheets': [
            {'tableau_worksheet': 'Sales Overview', 'pbi_page': 'Sales Overview'},
            {'tableau_worksheet': 'Profit Map', 'pbi_page': 'Profit Map'},
        ],
    }

    def test_generate_html_with_lineage(self):
        """generate_html() renders the Lineage Map section when lineage data is present."""
        from generate_report import generate_html
        html = generate_html({}, {}, {}, lineage={'Superstore': self.SAMPLE_LINEAGE})
        assert 'Lineage Map' in html
        assert 'lineage-tabs' in html
        assert 'Migration Flow' in html

    def test_flow_diagram_rendered(self):
        """Flow diagram shows table/calc/relationship/page counts."""
        from generate_report import generate_html
        html = generate_html({}, {}, {}, lineage={'WB1': self.SAMPLE_LINEAGE})
        assert 'flow-container' in html
        assert '2 tables' in html
        assert '2 pages' in html

    def test_table_lineage_tab(self):
        """Tables tab shows Tableau datasource to PBI table mapping."""
        from generate_report import generate_html
        html = generate_html({}, {}, {}, lineage={'WB1': self.SAMPLE_LINEAGE})
        assert 'lin-tbl' in html
        assert 'Orders' in html
        assert 'People' in html
        assert 'Sample - Superstore' in html

    def test_calculation_lineage_tab(self):
        """Calculations tab shows Tableau calc to PBI measure/column mapping."""
        from generate_report import generate_html
        html = generate_html({}, {}, {}, lineage={'WB1': self.SAMPLE_LINEAGE})
        assert 'lin-calc' in html
        assert 'Total Sales' in html
        assert 'measure' in html
        assert 'calculatedColumn' in html

    def test_relationship_lineage_tab(self):
        """Relationships tab shows from to to with cardinality."""
        from generate_report import generate_html
        html = generate_html({}, {}, {}, lineage={'WB1': self.SAMPLE_LINEAGE})
        assert 'lin-rel' in html
        assert 'Orders[Region]' in html
        assert 'People[Region]' in html
        assert 'manyToOne' in html

    def test_worksheet_lineage_tab(self):
        """Worksheets tab shows Tableau worksheet to PBI page mapping."""
        from generate_report import generate_html
        html = generate_html({}, {}, {}, lineage={'WB1': self.SAMPLE_LINEAGE})
        assert 'lin-ws' in html
        assert 'Sales Overview' in html
        assert 'Profit Map' in html

    def test_stat_cards_rendered(self):
        """Stat cards show counts for tables, calculations, relationships, worksheets."""
        from generate_report import generate_html
        html = generate_html({}, {}, {}, lineage={'WB1': self.SAMPLE_LINEAGE})
        assert 'Tables Mapped' in html
        assert 'Calculations Traced' in html
        assert 'Relationships' in html

    def test_no_lineage_section_when_empty(self):
        """Lineage Map section is omitted when no lineage data is provided."""
        from generate_report import generate_html
        html = generate_html({}, {}, {}, lineage={})
        assert 'Lineage Map' not in html

    def test_no_lineage_section_when_none(self):
        """Lineage Map section is omitted when lineage is None."""
        from generate_report import generate_html
        html = generate_html({}, {}, {}, lineage=None)
        assert 'Lineage Map' not in html

    def test_multi_workbook_lineage(self):
        """Lineage data from multiple workbooks is aggregated."""
        from generate_report import generate_html
        lin2 = {
            'tables': [{'tableau_datasource': 'DS2', 'tableau_table': 'Products', 'pbi_table': 'Products'}],
            'calculations': [],
            'relationships': [],
            'worksheets': [{'tableau_worksheet': 'Product View', 'pbi_page': 'Product View'}],
        }
        html = generate_html({}, {}, {}, lineage={'WB1': self.SAMPLE_LINEAGE, 'WB2': lin2})
        assert '3 tables' in html  # 2 from WB1 + 1 from WB2
        assert '3 pages' in html   # 2 from WB1 + 1 from WB2
        assert 'Products' in html
        assert 'Product View' in html

    def test_load_lineage_function(self):
        """load_lineage() reads lineage_map.json from project directories."""
        from generate_report import load_lineage
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = os.path.join(tmpdir, 'TestProject')
            os.makedirs(proj)
            lin_path = os.path.join(proj, 'lineage_map.json')
            with open(lin_path, 'w', encoding='utf-8') as f:
                json.dump(self.SAMPLE_LINEAGE, f)
            result = load_lineage(tmpdir)
            assert 'TestProject' in result
            assert len(result['TestProject']['tables']) == 2

    def test_generate_dashboard_loads_lineage(self):
        """generate_dashboard() reads lineage_map.json and includes lineage in HTML."""
        from generate_report import generate_dashboard
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = os.path.join(tmpdir, 'TestWB')
            os.makedirs(proj)
            with open(os.path.join(proj, 'lineage_map.json'), 'w', encoding='utf-8') as f:
                json.dump(self.SAMPLE_LINEAGE, f)
            with open(os.path.join(proj, 'migration_metadata.json'), 'w', encoding='utf-8') as f:
                json.dump({'tmdl_stats': {'tables': 2}, 'generated_output': {'pages': 2}}, f)
            result = generate_dashboard('TestWB', tmpdir)
            assert result is not None
            with open(result, encoding='utf-8') as f:
                html = f.read()
            assert 'Lineage Map' in html
            assert 'Orders' in html


class TestReportDaxSuppression:
    """DAX column suppressed when identical to source formula."""

    def test_conv_rows_suppresses_identical_dax(self):
        """generate_html _conv_rows suppresses DAX when it equals source."""
        from generate_report import generate_html

        reports = {
            'Test': {
                'items': [
                    {
                        'category': 'calculation',
                        'name': 'KPI_Desc',
                        'status': 'exact',
                        'source_formula': '"Some description text"',
                        'dax': '"Some description text"',
                    },
                    {
                        'category': 'calculation',
                        'name': 'Real Calc',
                        'status': 'exact',
                        'source_formula': 'SUM([Sales])',
                        'dax': 'SUM([Sales])',
                    },
                    {
                        'category': 'calculation',
                        'name': 'Converted',
                        'status': 'exact',
                        'source_formula': 'COUNTD([Customer ID])',
                        'dax': 'DISTINCTCOUNT([Customer ID])',
                    },
                ],
                'summary': {'exact': 3, 'approximate': 0, 'unsupported': 0, 'skipped': 0},
            }
        }
        # Note: generate_html signature is (assessments, reports, metadata, ...)
        html = generate_html({}, reports, {})
        # The identical string-literal and identical SUM should have DAX suppressed
        assert 'DISTINCTCOUNT([Customer ID])' in html  # different DAX is shown
        # Without suppression, identical source+dax renders twice per tab view
        # (once in source col, once in dax col).
        # With suppression, it only renders once per tab view (source col only).
        src_count = html.count('Some description text')
        # Also count how many times source formula appears for the DIFFERENT calc
        countd_src = html.count('COUNTD([Customer ID])')
        # Both source formulas should appear the same number of times (once per view)
        assert src_count == countd_src, (
            f"Identical-dax source and different-dax source should have "
            f"same occurrence count: {src_count} vs {countd_src}"
        )
