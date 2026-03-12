"""Sprint 29 tests — Tableau 2024+ Features & Multi-language.

Tests for:
- 29.1: Dynamic parameters (database-query-driven, 2024.3+)
- 29.2: Tableau Pulse → PBI Goals/Scorecard
- 29.3: Multi-language culture TMDL files
- 29.4: Translated display folders
"""

import json
import os
import sys
import tempfile
import unittest
import uuid
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))


# ═══════════════════════════════════════════════════════════════════════
# 29.1 — Dynamic Parameters
# ═══════════════════════════════════════════════════════════════════════

class TestDynamicParameterExtraction(unittest.TestCase):
    """Test dynamic (database-query-driven) parameter extraction."""

    def _make_extractor(self):
        from extract_tableau_data import TableauExtractor
        ext = TableauExtractor.__new__(TableauExtractor)
        ext.workbook_data = {}
        ext.file_path = 'test.twb'
        return ext

    def test_new_format_database_domain(self):
        """<parameters><parameter> with <query> child → domain_type='database'."""
        xml_str = '''<workbook>
          <parameters>
            <parameter name='[Param1]' caption='Region Filter' datatype='string' value='"East"'>
              <query>SELECT DISTINCT region FROM sales</query>
              <query-connection class='sqlserver' dbname='mydb'/>
            </parameter>
          </parameters>
        </workbook>'''
        root = ET.fromstring(xml_str)
        ext = self._make_extractor()
        ext.extract_parameters(root)

        params = ext.workbook_data['parameters']
        self.assertEqual(len(params), 1)
        p = params[0]
        self.assertEqual(p['domain_type'], 'database')
        self.assertEqual(p['query'], 'SELECT DISTINCT region FROM sales')
        self.assertEqual(p['query_connection'], 'sqlserver')
        self.assertEqual(p['query_dbname'], 'mydb')

    def test_new_format_refresh_on_open(self):
        """refresh-on-open attribute is captured."""
        xml_str = '''<workbook>
          <parameters>
            <parameter name='[P2]' caption='Cities' datatype='string' value='"NYC"'
                       refresh-on-open='true'>
              <query>SELECT city FROM geo</query>
            </parameter>
          </parameters>
        </workbook>'''
        root = ET.fromstring(xml_str)
        ext = self._make_extractor()
        ext.extract_parameters(root)
        self.assertTrue(ext.workbook_data['parameters'][0]['refresh_on_open'])

    def test_new_format_non_dynamic_unchanged(self):
        """Normal list/range parameters are NOT marked as database."""
        xml_str = '''<workbook>
          <parameters>
            <parameter name='[P3]' caption='Year' datatype='integer' value='2024'>
              <range min='2000' max='2030' granularity='1'/>
            </parameter>
          </parameters>
        </workbook>'''
        root = ET.fromstring(xml_str)
        ext = self._make_extractor()
        ext.extract_parameters(root)
        p = ext.workbook_data['parameters'][0]
        self.assertEqual(p['domain_type'], 'range')
        self.assertNotIn('query', p)

    def test_old_format_database_param(self):
        """Old-format column with param-domain-type='database'."""
        xml_str = '''<workbook>
          <column name='[Param_DB]' caption='DB Param' datatype='string'
                  value='"x"' param-domain-type='database'>
            <calculation formula='SELECT code FROM ref'/>
          </column>
        </workbook>'''
        root = ET.fromstring(xml_str)
        ext = self._make_extractor()
        ext.extract_parameters(root)
        p = ext.workbook_data['parameters'][0]
        self.assertEqual(p['domain_type'], 'database')
        self.assertEqual(p['query'], 'SELECT code FROM ref')
        self.assertTrue(p['refresh_on_open'])


class TestDynamicParameterTMDL(unittest.TestCase):
    """Test dynamic parameter M expression generation in TMDL."""

    def _build_model(self, params):
        from tmdl_generator import _create_parameter_tables
        model = {
            "model": {
                "tables": [{"name": "Sales", "columns": [], "measures": []}],
            }
        }
        _create_parameter_tables(model, params, "Sales")
        return model

    def test_database_param_creates_m_partition(self):
        """Dynamic param → M partition with Value.NativeQuery()."""
        params = [{
            'caption': 'Region',
            'datatype': 'string',
            'value': '"East"',
            'domain_type': 'database',
            'query': 'SELECT DISTINCT region FROM sales',
            'query_connection': 'sqlserver',
            'query_dbname': 'mydb',
            'refresh_on_open': True,
            'allowable_values': [],
        }]
        model = self._build_model(params)
        tables = model['model']['tables']
        param_table = next((t for t in tables if t['name'] == 'Region'), None)
        self.assertIsNotNone(param_table)

        # Check partition is M-type with native query
        partition = param_table['partitions'][0]
        self.assertEqual(partition['source']['type'], 'm')
        self.assertIn('Value.NativeQuery', partition['source']['expression'])
        self.assertIn('SELECT DISTINCT region FROM sales', partition['source']['expression'])

    def test_database_param_has_selectedvalue_measure(self):
        """Dynamic param table gets a SELECTEDVALUE measure."""
        params = [{
            'caption': 'Country',
            'datatype': 'string',
            'value': '"US"',
            'domain_type': 'database',
            'query': 'SELECT c FROM t',
            'allowable_values': [],
        }]
        model = self._build_model(params)
        param_table = next((t for t in model['model']['tables'] if t['name'] == 'Country'), None)
        self.assertIsNotNone(param_table)
        measure = param_table['measures'][0]
        self.assertIn('SELECTEDVALUE', measure['expression'])

    def test_database_param_refresh_policy(self):
        """Dynamic param with refresh_on_open → refreshPolicy."""
        params = [{
            'caption': 'Zone',
            'datatype': 'string',
            'value': '"A"',
            'domain_type': 'database',
            'query': 'SELECT z FROM zones',
            'refresh_on_open': True,
            'allowable_values': [],
        }]
        model = self._build_model(params)
        param_table = next((t for t in model['model']['tables'] if t['name'] == 'Zone'), None)
        self.assertIsNotNone(param_table)
        self.assertIn('refreshPolicy', param_table)
        self.assertEqual(param_table['refreshPolicy']['type'], 'automatic')

    def test_database_param_no_query_fallback(self):
        """Dynamic param without query → fallback #table expression."""
        params = [{
            'caption': 'Fallback',
            'datatype': 'string',
            'value': '"default"',
            'domain_type': 'database',
            'query': '',
            'allowable_values': [],
        }]
        model = self._build_model(params)
        param_table = next((t for t in model['model']['tables'] if t['name'] == 'Fallback'), None)
        self.assertIsNotNone(param_table)
        partition = param_table['partitions'][0]
        self.assertIn('#table', partition['source']['expression'])

    def test_database_param_migration_note(self):
        """Dynamic param tables have MigrationNote annotation."""
        params = [{
            'caption': 'Dept',
            'datatype': 'string',
            'value': '"IT"',
            'domain_type': 'database',
            'query': 'SELECT d FROM dept',
            'allowable_values': [],
        }]
        model = self._build_model(params)
        param_table = next((t for t in model['model']['tables'] if t['name'] == 'Dept'), None)
        self.assertIsNotNone(param_table)
        annotations = param_table.get('annotations', [])
        note = next((a for a in annotations if a['name'] == 'MigrationNote'), None)
        self.assertIsNotNone(note)
        self.assertIn('dynamic parameter', note['value'])


# ═══════════════════════════════════════════════════════════════════════
# 29.2 — Tableau Pulse → PBI Goals/Scorecard
# ═══════════════════════════════════════════════════════════════════════

class TestPulseExtractor(unittest.TestCase):
    """Test Pulse metric extraction from workbook XML."""

    def test_extract_basic_metric(self):
        """Extract a simple <metric> element."""
        from pulse_extractor import extract_pulse_metrics
        xml_str = '''<workbook>
          <metric name='Revenue' measure='[Sales]' time-dimension='[Order Date]'
                  time-grain='month' aggregation='SUM'>
            <target value='1000000' label='Annual Target'/>
          </metric>
        </workbook>'''
        root = ET.fromstring(xml_str)
        metrics = extract_pulse_metrics(root)
        self.assertEqual(len(metrics), 1)
        m = metrics[0]
        self.assertEqual(m['name'], 'Revenue')
        self.assertEqual(m['measure_field'], 'Sales')
        self.assertEqual(m['time_dimension'], 'Order Date')
        self.assertEqual(m['time_grain'], 'Monthly')
        self.assertEqual(m['aggregation'], 'SUM')
        self.assertEqual(m['target_value'], 1000000.0)
        self.assertEqual(m['target_label'], 'Annual Target')

    def test_extract_pulse_metric_element(self):
        """Extract a <pulse-metric> element."""
        from pulse_extractor import extract_pulse_metrics
        xml_str = '''<workbook>
          <pulse-metric name='UserGrowth' measure='[Users]' time-grain='week'
                        aggregation='COUNT'/>
        </workbook>'''
        root = ET.fromstring(xml_str)
        metrics = extract_pulse_metrics(root)
        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0]['name'], 'UserGrowth')
        self.assertEqual(metrics[0]['time_grain'], 'Weekly')

    def test_extract_metrics_collection(self):
        """Extract <metrics><metric> nested structure."""
        from pulse_extractor import extract_pulse_metrics
        xml_str = '''<workbook>
          <metrics>
            <metric name='KPI1' measure='[M1]' time-grain='quarter'/>
            <metric name='KPI2' measure='[M2]' time-grain='year'/>
          </metrics>
        </workbook>'''
        root = ET.fromstring(xml_str)
        metrics = extract_pulse_metrics(root)
        self.assertEqual(len(metrics), 2)
        self.assertEqual(metrics[0]['time_grain'], 'Quarterly')
        self.assertEqual(metrics[1]['time_grain'], 'Yearly')

    def test_no_metrics_returns_empty(self):
        """Workbook with no metrics → empty list."""
        from pulse_extractor import extract_pulse_metrics
        root = ET.fromstring('<workbook><worksheets/></workbook>')
        self.assertEqual(extract_pulse_metrics(root), [])

    def test_none_root_returns_empty(self):
        """None root → empty list (no crash)."""
        from pulse_extractor import extract_pulse_metrics
        self.assertEqual(extract_pulse_metrics(None), [])

    def test_metric_with_filters(self):
        """Metric with filter children."""
        from pulse_extractor import extract_pulse_metrics
        xml_str = '''<workbook>
          <metric name='Regional Revenue' measure='[Sales]' time-grain='month'>
            <filter column='[Region]' type='categorical'>
              <value>East</value>
              <value>West</value>
            </filter>
          </metric>
        </workbook>'''
        root = ET.fromstring(xml_str)
        metrics = extract_pulse_metrics(root)
        self.assertEqual(len(metrics[0]['filters']), 1)
        f = metrics[0]['filters'][0]
        self.assertEqual(f['field'], 'Region')
        self.assertEqual(f['values'], ['East', 'West'])

    def test_deduplication_by_name(self):
        """Duplicate metric names are deduplicated."""
        from pulse_extractor import extract_pulse_metrics
        xml_str = '''<workbook>
          <metric name='Rev' measure='[Sales]'/>
          <pulse-metric name='Rev' measure='[Revenue]'/>
        </workbook>'''
        root = ET.fromstring(xml_str)
        metrics = extract_pulse_metrics(root)
        self.assertEqual(len(metrics), 1)

    def test_has_pulse_metrics_true(self):
        """has_pulse_metrics returns True when metrics exist."""
        from pulse_extractor import has_pulse_metrics
        root = ET.fromstring('<workbook><metric name="X"/></workbook>')
        self.assertTrue(has_pulse_metrics(root))

    def test_has_pulse_metrics_false(self):
        """has_pulse_metrics returns False for empty workbook."""
        from pulse_extractor import has_pulse_metrics
        root = ET.fromstring('<workbook/>')
        self.assertFalse(has_pulse_metrics(root))


class TestGoalsGenerator(unittest.TestCase):
    """Test PBI Goals/Scorecard JSON generation."""

    def _sample_metrics(self):
        return [
            {
                'name': 'Revenue',
                'description': 'Total revenue',
                'measure_field': 'Sales',
                'time_dimension': 'Order Date',
                'time_grain': 'Monthly',
                'aggregation': 'SUM',
                'target_value': 1000000.0,
                'target_label': 'Annual Target',
                'filters': [{'field': 'Region', 'operator': 'In', 'values': ['East']}],
                'definition_formula': '',
                'number_format': '$#,##0',
            },
            {
                'name': 'Customers',
                'description': 'Customer count',
                'measure_field': 'CustomerID',
                'time_dimension': '',
                'time_grain': 'Quarterly',
                'aggregation': 'DISTINCTCOUNT',
                'target_value': None,
                'target_label': '',
                'filters': [],
                'definition_formula': '',
                'number_format': '',
            },
        ]

    def test_generate_scorecard(self):
        """generate_goals_json returns valid scorecard dict."""
        from goals_generator import generate_goals_json
        metrics = self._sample_metrics()
        scorecard = generate_goals_json(metrics, report_name='TestReport')
        self.assertIsNotNone(scorecard)
        self.assertEqual(scorecard['name'], 'TestReport Scorecard')
        self.assertEqual(len(scorecard['goals']), 2)

    def test_goal_has_target(self):
        """Goal with target_value has target section."""
        from goals_generator import generate_goals_json
        scorecard = generate_goals_json(self._sample_metrics())
        goal = scorecard['goals'][0]
        self.assertIn('target', goal)
        self.assertEqual(goal['target']['value'], 1000000.0)

    def test_goal_without_target(self):
        """Goal without target_value has no target section."""
        from goals_generator import generate_goals_json
        scorecard = generate_goals_json(self._sample_metrics())
        goal = scorecard['goals'][1]
        self.assertNotIn('target', goal)

    def test_goal_connected_measure(self):
        """Goal has connectedMeasure with field and aggregation."""
        from goals_generator import generate_goals_json
        scorecard = generate_goals_json(self._sample_metrics())
        goal = scorecard['goals'][0]
        self.assertEqual(goal['connectedMeasure']['measure'], 'Sales')
        self.assertEqual(goal['connectedMeasure']['aggregation'], 'SUM')

    def test_goal_cadence_mapping(self):
        """Goal cadence matches metric time_grain."""
        from goals_generator import generate_goals_json
        scorecard = generate_goals_json(self._sample_metrics())
        self.assertEqual(scorecard['goals'][0]['cadence'], 'Monthly')
        self.assertEqual(scorecard['goals'][1]['cadence'], 'Quarterly')

    def test_goal_filters(self):
        """Goal with filters includes them."""
        from goals_generator import generate_goals_json
        scorecard = generate_goals_json(self._sample_metrics())
        goal = scorecard['goals'][0]
        self.assertEqual(len(goal['filters']), 1)
        self.assertEqual(goal['filters'][0]['field'], 'Region')

    def test_empty_metrics_returns_none(self):
        """No metrics → None."""
        from goals_generator import generate_goals_json
        self.assertIsNone(generate_goals_json([]))
        self.assertIsNone(generate_goals_json(None))

    def test_workspace_id_included(self):
        """workspace_id is included when provided."""
        from goals_generator import generate_goals_json
        scorecard = generate_goals_json(self._sample_metrics(), workspace_id='ws-123')
        self.assertEqual(scorecard['workspaceId'], 'ws-123')

    def test_goal_migration_note(self):
        """Each goal has a MigrationNote annotation."""
        from goals_generator import generate_goals_json
        scorecard = generate_goals_json(self._sample_metrics())
        for goal in scorecard['goals']:
            notes = [a for a in goal['annotations'] if a['name'] == 'MigrationNote']
            self.assertEqual(len(notes), 1)
            self.assertIn('Tableau Pulse', notes[0]['value'])

    def test_write_goals_artifact(self):
        """write_goals_artifact creates goals/scorecard.json."""
        from goals_generator import generate_goals_json, write_goals_artifact
        scorecard = generate_goals_json(self._sample_metrics())
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = write_goals_artifact(scorecard, tmpdir)
            self.assertIsNotNone(filepath)
            self.assertTrue(os.path.isfile(filepath))
            with open(filepath, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            self.assertEqual(loaded['name'], 'Report Scorecard')
            self.assertEqual(len(loaded['goals']), 2)

    def test_write_goals_none_scorecard(self):
        """write_goals_artifact with None returns None."""
        from goals_generator import write_goals_artifact
        self.assertIsNone(write_goals_artifact(None, '/tmp'))


# ═══════════════════════════════════════════════════════════════════════
# 29.3 — Multi-language Culture TMDL Files
# ═══════════════════════════════════════════════════════════════════════

class TestWriteCultureTMDL(unittest.TestCase):
    """Test culture TMDL file writing with linguistic metadata."""

    def test_culture_file_created(self):
        """_write_culture_tmdl creates a .tmdl file."""
        from tmdl_generator import _write_culture_tmdl
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_culture_tmdl(tmpdir, 'fr-FR', [])
            path = os.path.join(tmpdir, 'fr-FR.tmdl')
            self.assertTrue(os.path.isfile(path))
            content = open(path, 'r', encoding='utf-8').read()
            self.assertIn("culture 'fr-FR'", content)
            self.assertIn('linguisticMetadata', content)

    def test_culture_has_language_metadata(self):
        """Culture file includes Language in metadata JSON."""
        from tmdl_generator import _write_culture_tmdl
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_culture_tmdl(tmpdir, 'de-DE', [])
            content = open(os.path.join(tmpdir, 'de-DE.tmdl'), 'r', encoding='utf-8').read()
            self.assertIn('"Language": "de-DE"', content)

    def test_culture_translated_display_folders(self):
        """Culture file includes translated display folders for measures."""
        from tmdl_generator import _write_culture_tmdl
        tables = [{
            'name': 'Sales',
            'columns': [],
            'measures': [{
                'name': 'Total Revenue',
                'expression': 'SUM([Revenue])',
                'annotations': [{'name': 'displayFolder', 'value': 'Measures'}],
            }],
        }]
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_culture_tmdl(tmpdir, 'fr-FR', tables)
            content = open(os.path.join(tmpdir, 'fr-FR.tmdl'), 'r', encoding='utf-8').read()
            self.assertIn('translatedDisplayFolder', content)
            self.assertIn('Mesures', content)

    def test_culture_no_translations_for_en(self):
        """en-US culture doesn't need display folder translations."""
        from tmdl_generator import _get_display_folder_translations
        result = _get_display_folder_translations('en-US')
        self.assertEqual(result, {})


class TestWriteMultiLanguageCultures(unittest.TestCase):
    """Test _write_multi_language_cultures for multiple locales."""

    def test_multiple_languages_create_files(self):
        """Multiple comma-separated locales each get a .tmdl file."""
        from tmdl_generator import _write_multi_language_cultures
        tables = [{'name': 'T', 'columns': [], 'measures': []}]
        with tempfile.TemporaryDirectory() as tmpdir:
            def_dir = tmpdir
            _write_multi_language_cultures(def_dir, 'fr-FR,de-DE', tables)
            cultures_dir = os.path.join(def_dir, 'cultures')
            self.assertTrue(os.path.isfile(os.path.join(cultures_dir, 'fr-FR.tmdl')))
            self.assertTrue(os.path.isfile(os.path.join(cultures_dir, 'de-DE.tmdl')))

    def test_en_us_skipped(self):
        """en-US is not generated as a separate culture file."""
        from tmdl_generator import _write_multi_language_cultures
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_multi_language_cultures(tmpdir, 'en-US,fr-FR', [])
            cultures_dir = os.path.join(tmpdir, 'cultures')
            self.assertFalse(os.path.exists(os.path.join(cultures_dir, 'en-US.tmdl')))
            self.assertTrue(os.path.isfile(os.path.join(cultures_dir, 'fr-FR.tmdl')))

    def test_empty_languages_no_files(self):
        """Empty string → no culture files."""
        from tmdl_generator import _write_multi_language_cultures
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_multi_language_cultures(tmpdir, '', [])
            cultures_dir = os.path.join(tmpdir, 'cultures')
            self.assertFalse(os.path.isdir(cultures_dir))

    def test_none_languages_no_crash(self):
        """None → no crash, no files."""
        from tmdl_generator import _write_multi_language_cultures
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_multi_language_cultures(tmpdir, None, [])
            cultures_dir = os.path.join(tmpdir, 'cultures')
            self.assertFalse(os.path.isdir(cultures_dir))


# ═══════════════════════════════════════════════════════════════════════
# 29.4 — Display Folder Translations
# ═══════════════════════════════════════════════════════════════════════

class TestDisplayFolderTranslations(unittest.TestCase):
    """Test _get_display_folder_translations and translation data."""

    def test_fr_fr_translations(self):
        """French translations exist for standard folders."""
        from tmdl_generator import _get_display_folder_translations
        tr = _get_display_folder_translations('fr-FR')
        self.assertEqual(tr['Measures'], 'Mesures')
        self.assertEqual(tr['Parameters'], 'Paramètres')
        self.assertEqual(tr['Calculations'], 'Calculs')

    def test_de_de_translations(self):
        """German translations exist."""
        from tmdl_generator import _get_display_folder_translations
        tr = _get_display_folder_translations('de-DE')
        self.assertEqual(tr['Measures'], 'Kennzahlen')
        self.assertEqual(tr['Groups'], 'Gruppen')

    def test_es_es_translations(self):
        """Spanish translations exist."""
        from tmdl_generator import _get_display_folder_translations
        tr = _get_display_folder_translations('es-ES')
        self.assertEqual(tr['Measures'], 'Medidas')

    def test_ja_jp_translations(self):
        """Japanese translations exist."""
        from tmdl_generator import _get_display_folder_translations
        tr = _get_display_folder_translations('ja-JP')
        self.assertEqual(tr['Measures'], 'メジャー')

    def test_zh_cn_translations(self):
        """Chinese translations exist."""
        from tmdl_generator import _get_display_folder_translations
        tr = _get_display_folder_translations('zh-CN')
        self.assertEqual(tr['Measures'], '度量')

    def test_language_fallback(self):
        """fr-CA falls back to fr-FR translations."""
        from tmdl_generator import _get_display_folder_translations
        tr = _get_display_folder_translations('fr-CA')
        self.assertEqual(tr['Measures'], 'Mesures')

    def test_unknown_locale_empty(self):
        """Unknown locale returns empty dict."""
        from tmdl_generator import _get_display_folder_translations
        tr = _get_display_folder_translations('xx-YY')
        self.assertEqual(tr, {})

    def test_all_standard_folders_covered(self):
        """All standard display folders have translations in each locale."""
        from tmdl_generator import _DISPLAY_FOLDER_TRANSLATIONS
        standard_folders = {'Dimensions', 'Measures', 'Parameters', 'Calculations',
                           'Groups', 'Sets', 'Bins', 'Time Intelligence', 'Flags'}
        for locale, translations in _DISPLAY_FOLDER_TRANSLATIONS.items():
            for folder in standard_folders:
                self.assertIn(folder, translations,
                              f"Missing '{folder}' translation for {locale}")


# ═══════════════════════════════════════════════════════════════════════
# CLI Wiring
# ═══════════════════════════════════════════════════════════════════════

class TestCLIFlags(unittest.TestCase):
    """Test --languages and --goals CLI argument existence."""

    def test_languages_flag_exists(self):
        """--languages flag is registered in argparse."""
        import migrate
        parser = migrate._build_parser() if hasattr(migrate, '_build_parser') else None
        if parser is None:
            # Fall back: parse known args
            import argparse
            # Check the source for the argument
            import inspect
            source = inspect.getsource(migrate)
            self.assertIn("'--languages'", source)

    def test_goals_flag_exists(self):
        """--goals flag is registered in argparse."""
        import migrate
        import inspect
        source = inspect.getsource(migrate)
        self.assertIn("'--goals'", source)

    def test_languages_in_run_generation(self):
        """run_generation accepts languages parameter."""
        import migrate
        import inspect
        sig = inspect.signature(migrate.run_generation)
        self.assertIn('languages', sig.parameters)


# ═══════════════════════════════════════════════════════════════════════
# Integration: generate_tmdl with languages
# ═══════════════════════════════════════════════════════════════════════

class TestGenerateTMDLWithLanguages(unittest.TestCase):
    """Test that generate_tmdl writes culture files when languages is passed."""

    def test_languages_produces_culture_files(self):
        """generate_tmdl with languages='fr-FR,de-DE' creates culture TMDL files."""
        from tmdl_generator import generate_tmdl
        datasources = [{
            'name': 'DS1',
            'connection': {'type': 'sqlserver', 'server': 'srv', 'database': 'db'},
            'tables': [{
                'name': 'Sales',
                'columns': [
                    {'name': 'Revenue', 'datatype': 'real', 'role': 'measure'},
                    {'name': 'Region', 'datatype': 'string', 'role': 'dimension'},
                ],
            }],
            'calculations': [],
        }]
        with tempfile.TemporaryDirectory() as tmpdir:
            stats = generate_tmdl(
                datasources=datasources,
                report_name='TestReport',
                extra_objects={},
                output_dir=tmpdir,
                languages='fr-FR,de-DE',
            )
            cultures_dir = os.path.join(tmpdir, 'definition', 'cultures')
            self.assertTrue(os.path.isdir(cultures_dir))
            self.assertTrue(os.path.isfile(os.path.join(cultures_dir, 'fr-FR.tmdl')))
            self.assertTrue(os.path.isfile(os.path.join(cultures_dir, 'de-DE.tmdl')))

    def test_no_languages_no_extra_cultures(self):
        """generate_tmdl without languages doesn't create extra culture files."""
        from tmdl_generator import generate_tmdl
        datasources = [{
            'name': 'DS1',
            'connection': {'type': 'sqlserver', 'server': 'srv', 'database': 'db'},
            'tables': [{'name': 'T1', 'columns': [{'name': 'Col', 'datatype': 'string'}]}],
            'calculations': [],
        }]
        with tempfile.TemporaryDirectory() as tmpdir:
            generate_tmdl(datasources=datasources, report_name='Test',
                          extra_objects={}, output_dir=tmpdir)
            cultures_dir = os.path.join(tmpdir, 'definition', 'cultures')
            # No culture dir should exist since default is en-US
            if os.path.isdir(cultures_dir):
                files = os.listdir(cultures_dir)
                self.assertEqual(len(files), 0,
                                 f"Unexpected culture files: {files}")


if __name__ == '__main__':
    unittest.main()
