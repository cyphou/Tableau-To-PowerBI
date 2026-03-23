"""Tests for v28 new features — LLM client, Web UI, Paginated Reports,
Extension Mapping, Multi-language TMDL, Prep→Dataflow, CLI flags.

Sprint 108–111 test coverage targeting 200+ new tests.
"""

import json
import os
import sys
import unittest
import tempfile
import shutil
from unittest.mock import patch, MagicMock
from datetime import datetime

# Ensure project root is on path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ════════════════════════════════════════════════════════════════════
#  LLM Client Tests (Sprint 82)
# ════════════════════════════════════════════════════════════════════

class TestLLMClient(unittest.TestCase):
    """Tests for powerbi_import.llm_client."""

    def test_import(self):
        from powerbi_import.llm_client import LLMClient
        self.assertIsNotNone(LLMClient)

    def test_init_openai(self):
        from powerbi_import.llm_client import LLMClient
        client = LLMClient(provider='openai', api_key='test-key', dry_run=True)
        self.assertEqual(client.provider, 'openai')
        self.assertEqual(client.api_key, 'test-key')
        self.assertTrue(client.dry_run)

    def test_init_anthropic(self):
        from powerbi_import.llm_client import LLMClient
        client = LLMClient(provider='anthropic', api_key='test', dry_run=True)
        self.assertEqual(client.provider, 'anthropic')

    def test_init_azure_openai_requires_endpoint(self):
        from powerbi_import.llm_client import LLMClient
        with self.assertRaises(ValueError):
            LLMClient(provider='azure_openai', api_key='test')

    def test_init_azure_openai_with_endpoint(self):
        from powerbi_import.llm_client import LLMClient
        client = LLMClient(provider='azure_openai', api_key='test',
                           endpoint='https://myresource.openai.azure.com', dry_run=True)
        self.assertEqual(client.provider, 'azure_openai')

    def test_invalid_provider(self):
        from powerbi_import.llm_client import LLMClient
        with self.assertRaises(ValueError):
            LLMClient(provider='invalid')

    def test_calls_remaining(self):
        from powerbi_import.llm_client import LLMClient
        client = LLMClient(provider='openai', api_key='test', max_calls=5, dry_run=True)
        self.assertEqual(client.calls_remaining, 5)
        client._call_count = 3
        self.assertEqual(client.calls_remaining, 2)

    def test_total_cost_initial(self):
        from powerbi_import.llm_client import LLMClient
        client = LLMClient(provider='openai', api_key='test', dry_run=True)
        self.assertEqual(client.total_cost, 0)

    def test_dry_run_call(self):
        from powerbi_import.llm_client import LLMClient
        client = LLMClient(provider='openai', api_key='test', dry_run=True)
        result = client.call('system prompt', 'user prompt')
        self.assertIn('[DRY RUN]', result['text'])
        self.assertTrue(result.get('dry_run'))
        self.assertEqual(client._call_count, 1)

    def test_call_limit_enforcement(self):
        from powerbi_import.llm_client import LLMClient
        client = LLMClient(provider='openai', api_key='test', max_calls=0, dry_run=True)
        result = client.call('sys', 'user')
        self.assertEqual(result['error'], 'call_limit_reached')

    def test_estimate_tokens(self):
        from powerbi_import.llm_client import estimate_tokens
        self.assertEqual(estimate_tokens(''), 0)
        self.assertGreater(estimate_tokens('Hello world, this is a test'), 0)

    def test_build_schema_context_empty(self):
        from powerbi_import.llm_client import _build_schema_context
        ctx = _build_schema_context([])
        self.assertEqual(ctx, '(no schema available)')

    def test_build_schema_context_with_tables(self):
        from powerbi_import.llm_client import _build_schema_context
        tables = [
            {'name': 'Sales', 'columns': [{'name': 'Amount', 'dataType': 'decimal'}]},
            {'name': 'Date', 'columns': [{'name': 'Year', 'dataType': 'int64'}]},
        ]
        ctx = _build_schema_context(tables)
        self.assertIn("'Sales'", ctx)
        self.assertIn('[Amount]', ctx)

    def test_extract_migration_note_from_dict(self):
        from powerbi_import.llm_client import _extract_migration_note
        m = {'annotations': [{'name': 'MigrationNote', 'value': 'approximated regex'}]}
        self.assertEqual(_extract_migration_note(m), 'approximated regex')

    def test_extract_migration_note_from_string(self):
        from powerbi_import.llm_client import _extract_migration_note
        dax = 'CONTAINSSTRING(x, "abc") /* MigrationNote: approximated from REGEXP_MATCH */'
        self.assertIn('approximated', _extract_migration_note(dax))

    def test_refine_skips_non_approximated(self):
        from powerbi_import.llm_client import LLMClient, refine_approximated_measures
        client = LLMClient(provider='openai', api_key='test', dry_run=True)
        measures = [{'name': 'M1', 'expression': 'SUM(x)', 'annotations': []}]
        results = refine_approximated_measures(client, measures)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['status'], 'skipped')

    def test_refine_targets_approximated(self):
        from powerbi_import.llm_client import LLMClient, refine_approximated_measures
        client = LLMClient(provider='openai', api_key='test', dry_run=True)
        measures = [{
            'name': 'RegexMatch',
            'expression': 'CONTAINSSTRING(x, "abc")',
            'annotations': [{'name': 'MigrationNote', 'value': 'approximated from REGEXP_MATCH'}],
        }]
        results = refine_approximated_measures(client, measures)
        self.assertEqual(results[0]['status'], 'refined')  # dry run returns text

    def test_generate_llm_report(self):
        from powerbi_import.llm_client import LLMClient, generate_llm_report
        client = LLMClient(provider='openai', api_key='test', dry_run=True)
        results = [
            {'name': 'M1', 'status': 'refined', 'tokens': {'input': 100, 'output': 50}, 'cost': 0.001,
             'original_dax': 'x', 'refined_dax': 'y', 'confidence': 0.85},
        ]
        report = generate_llm_report(client, results)
        self.assertEqual(report['summary']['refined'], 1)

    def test_generate_llm_report_to_file(self):
        from powerbi_import.llm_client import LLMClient, generate_llm_report
        client = LLMClient(provider='openai', api_key='test', dry_run=True)
        results = []
        with tempfile.TemporaryDirectory() as tmp:
            report = generate_llm_report(client, results, output_dir=tmp)
            self.assertTrue(os.path.exists(os.path.join(tmp, 'llm_refinement_report.json')))

    def test_build_url_openai(self):
        from powerbi_import.llm_client import LLMClient
        c = LLMClient(provider='openai', api_key='k', dry_run=True)
        self.assertIn('openai.com', c._build_url())

    def test_build_url_anthropic(self):
        from powerbi_import.llm_client import LLMClient
        c = LLMClient(provider='anthropic', api_key='k', dry_run=True)
        self.assertIn('anthropic.com', c._build_url())

    def test_build_url_azure(self):
        from powerbi_import.llm_client import LLMClient
        c = LLMClient(provider='azure_openai', api_key='k',
                       endpoint='https://test.openai.azure.com', dry_run=True)
        url = c._build_url()
        self.assertIn('test.openai.azure.com', url)
        self.assertIn('api-version', url)

    def test_build_headers_openai(self):
        from powerbi_import.llm_client import LLMClient
        c = LLMClient(provider='openai', api_key='sk-test', dry_run=True)
        h = c._build_headers()
        self.assertIn('Bearer sk-test', h.get('Authorization', ''))

    def test_build_headers_anthropic(self):
        from powerbi_import.llm_client import LLMClient
        c = LLMClient(provider='anthropic', api_key='ant-key', dry_run=True)
        h = c._build_headers()
        self.assertEqual(h.get('x-api-key'), 'ant-key')
        self.assertEqual(h.get('anthropic-version'), '2023-06-01')

    def test_parse_response_openai(self):
        from powerbi_import.llm_client import LLMClient
        c = LLMClient(provider='openai', api_key='k', dry_run=True)
        data = {'choices': [{'message': {'content': 'SUM(x)'}}]}
        self.assertEqual(c._parse_response(data), 'SUM(x)')

    def test_parse_response_anthropic(self):
        from powerbi_import.llm_client import LLMClient
        c = LLMClient(provider='anthropic', api_key='k', dry_run=True)
        data = {'content': [{'text': 'CALCULATE(SUM(x))'}]}
        self.assertEqual(c._parse_response(data), 'CALCULATE(SUM(x))')

    def test_parse_usage_openai(self):
        from powerbi_import.llm_client import LLMClient
        c = LLMClient(provider='openai', api_key='k', dry_run=True)
        data = {'usage': {'prompt_tokens': 100, 'completion_tokens': 50}}
        inp, out = c._parse_usage(data)
        self.assertEqual(inp, 100)
        self.assertEqual(out, 50)

    def test_parse_usage_anthropic(self):
        from powerbi_import.llm_client import LLMClient
        c = LLMClient(provider='anthropic', api_key='k', dry_run=True)
        data = {'usage': {'input_tokens': 80, 'output_tokens': 40}}
        inp, out = c._parse_usage(data)
        self.assertEqual(inp, 80)
        self.assertEqual(out, 40)

    def test_build_body_openai(self):
        from powerbi_import.llm_client import LLMClient
        c = LLMClient(provider='openai', api_key='k', dry_run=True)
        body = json.loads(c._build_body('sys', 'usr'))
        self.assertEqual(len(body['messages']), 2)
        self.assertEqual(body['messages'][0]['role'], 'system')

    def test_build_body_anthropic(self):
        from powerbi_import.llm_client import LLMClient
        c = LLMClient(provider='anthropic', api_key='k', dry_run=True)
        body = json.loads(c._build_body('sys', 'usr'))
        self.assertEqual(body['system'], 'sys')
        self.assertEqual(body['messages'][0]['role'], 'user')


# ════════════════════════════════════════════════════════════════════
#  Extension Mapping Tests (Sprint 108)
# ════════════════════════════════════════════════════════════════════

class TestExtensionMapping(unittest.TestCase):
    """Tests for Tableau Extension → PBI custom visual mapping."""

    def test_import_extension_map(self):
        from powerbi_import.visual_generator import TABLEAU_EXTENSION_MAP
        self.assertIsInstance(TABLEAU_EXTENSION_MAP, dict)
        self.assertGreater(len(TABLEAU_EXTENSION_MAP), 5)

    def test_resolve_extension_writeback(self):
        from powerbi_import.visual_generator import resolve_extension_visual
        vis_type, guid, note = resolve_extension_visual('com.tableau.extensions.writeback')
        self.assertIsNotNone(vis_type)
        self.assertIn('writeback', note.lower())

    def test_resolve_extension_mapbox(self):
        from powerbi_import.visual_generator import resolve_extension_visual
        vis_type, guid, note = resolve_extension_visual('com.mapbox.extensions.mapboxgl')
        self.assertEqual(vis_type, 'azureMap')

    def test_resolve_extension_unknown(self):
        from powerbi_import.visual_generator import resolve_extension_visual
        vis_type, guid, note = resolve_extension_visual('com.unknown.extension.xyz')
        self.assertEqual(vis_type, 'actionButton')
        self.assertIn('no PBI equivalent', note)

    def test_resolve_extension_empty(self):
        from powerbi_import.visual_generator import resolve_extension_visual
        vis_type, guid, note = resolve_extension_visual('')
        self.assertEqual(vis_type, 'actionButton')

    def test_resolve_extension_none(self):
        from powerbi_import.visual_generator import resolve_extension_visual
        vis_type, guid, note = resolve_extension_visual(None)
        self.assertEqual(vis_type, 'actionButton')

    def test_resolve_extension_with_custom_guid(self):
        from powerbi_import.visual_generator import resolve_extension_visual
        vis_type, guid, note = resolve_extension_visual('com.infotopics.wordcloud')
        self.assertIsNotNone(guid)
        self.assertEqual(guid['name'], 'Word Cloud')

    def test_custom_visual_guids_contains_new_entries(self):
        from powerbi_import.visual_generator import CUSTOM_VISUAL_GUIDS
        new_keys = ['writeback', 'calendar', 'orgchart', 'timeline', 'radarChart', 'sunburst']
        for key in new_keys:
            self.assertIn(key, CUSTOM_VISUAL_GUIDS, f"Missing: {key}")

    def test_custom_visual_guid_structure(self):
        from powerbi_import.visual_generator import CUSTOM_VISUAL_GUIDS
        for key, info in CUSTOM_VISUAL_GUIDS.items():
            self.assertIn('guid', info, f"{key} missing 'guid'")
            self.assertIn('name', info, f"{key} missing 'name'")
            self.assertIn('class', info, f"{key} missing 'class'")
            self.assertIn('roles', info, f"{key} missing 'roles'")


# ════════════════════════════════════════════════════════════════════
#  Multi-language TMDL Culture Tests (Sprint 108)
# ════════════════════════════════════════════════════════════════════

class TestMultiLanguageCultures(unittest.TestCase):
    """Tests for expanded TMDL culture translations."""

    def test_existing_cultures_preserved(self):
        from powerbi_import.tmdl_generator import _DISPLAY_FOLDER_TRANSLATIONS
        existing = ['fr-FR', 'de-DE', 'es-ES', 'pt-BR', 'ja-JP', 'zh-CN', 'ko-KR', 'it-IT', 'nl-NL']
        for c in existing:
            self.assertIn(c, _DISPLAY_FOLDER_TRANSLATIONS)

    def test_new_cultures_added(self):
        from powerbi_import.tmdl_generator import _DISPLAY_FOLDER_TRANSLATIONS
        new = ['sv-SE', 'da-DK', 'nb-NO', 'fi-FI', 'pl-PL', 'tr-TR', 'ru-RU', 'ar-SA', 'hi-IN', 'th-TH']
        for c in new:
            self.assertIn(c, _DISPLAY_FOLDER_TRANSLATIONS, f"Missing culture: {c}")

    def test_culture_keys_complete(self):
        from powerbi_import.tmdl_generator import _DISPLAY_FOLDER_TRANSLATIONS
        expected_keys = {'Dimensions', 'Measures', 'Time Intelligence', 'Flags',
                         'Calculations', 'Groups', 'Sets', 'Bins', 'Parameters',
                         'Field Parameters', 'Calculation Groups'}
        for culture, trans in _DISPLAY_FOLDER_TRANSLATIONS.items():
            for key in expected_keys:
                self.assertIn(key, trans, f"{culture} missing key '{key}'")

    def test_culture_values_not_empty(self):
        from powerbi_import.tmdl_generator import _DISPLAY_FOLDER_TRANSLATIONS
        for culture, trans in _DISPLAY_FOLDER_TRANSLATIONS.items():
            for key, val in trans.items():
                self.assertTrue(val, f"{culture}[{key}] is empty")

    def test_get_display_folder_translations_existing(self):
        from powerbi_import.tmdl_generator import _get_display_folder_translations
        result = _get_display_folder_translations('fr-FR')
        self.assertIn('Measures', result)
        self.assertEqual(result['Measures'], 'Mesures')

    def test_get_display_folder_translations_new(self):
        from powerbi_import.tmdl_generator import _get_display_folder_translations
        result = _get_display_folder_translations('sv-SE')
        self.assertIn('Measures', result)
        self.assertEqual(result['Measures'], 'Mått')

    def test_get_display_folder_translations_fallback(self):
        from powerbi_import.tmdl_generator import _get_display_folder_translations
        # fr-CA should fall back to fr-FR via language prefix
        result = _get_display_folder_translations('fr-CA')
        self.assertIn('Measures', result)

    def test_get_display_folder_translations_unknown(self):
        from powerbi_import.tmdl_generator import _get_display_folder_translations
        result = _get_display_folder_translations('xx-XX')
        self.assertEqual(result, {})

    def test_total_culture_count(self):
        from powerbi_import.tmdl_generator import _DISPLAY_FOLDER_TRANSLATIONS
        self.assertGreaterEqual(len(_DISPLAY_FOLDER_TRANSLATIONS), 19)


# ════════════════════════════════════════════════════════════════════
#  Paginated Report Generator Tests (Sprint 108)
# ════════════════════════════════════════════════════════════════════

class TestPaginatedReportGenerator(unittest.TestCase):
    """Tests for powerbi_import.paginated_generator."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_import(self):
        from powerbi_import.paginated_generator import PaginatedReportGenerator
        self.assertIsNotNone(PaginatedReportGenerator)

    def test_generate_empty_worksheets(self):
        from powerbi_import.paginated_generator import PaginatedReportGenerator
        gen = PaginatedReportGenerator(self.tmp_dir, 'TestReport')
        stats = gen.generate([])
        self.assertEqual(stats['pages'], 0)

    def test_generate_single_table_worksheet(self):
        from powerbi_import.paginated_generator import PaginatedReportGenerator
        gen = PaginatedReportGenerator(self.tmp_dir, 'TestReport')
        ws = [{'name': 'Sales Table', 'type': 'table', 'mark_type': 'table',
               'dimensions': [{'field': 'Region'}],
               'measures': [{'field': 'Revenue'}]}]
        stats = gen.generate(ws)
        self.assertEqual(stats['pages'], 1)
        self.assertEqual(stats['tablixes'], 1)

    def test_generate_chart_worksheet(self):
        from powerbi_import.paginated_generator import PaginatedReportGenerator
        gen = PaginatedReportGenerator(self.tmp_dir, 'TestReport')
        ws = [{'name': 'Bar Chart', 'type': 'barchart', 'mark_type': 'barchart',
               'dimensions': [{'field': 'Category'}],
               'measures': [{'field': 'Value'}]}]
        stats = gen.generate(ws)
        self.assertEqual(stats['charts'], 1)

    def test_generate_multi_page(self):
        from powerbi_import.paginated_generator import PaginatedReportGenerator
        gen = PaginatedReportGenerator(self.tmp_dir, 'TestReport')
        ws = [
            {'name': 'Page1', 'type': 'table'},
            {'name': 'Page2', 'type': 'linechart'},
            {'name': 'Page3', 'type': 'piechart'},
        ]
        stats = gen.generate(ws)
        self.assertEqual(stats['pages'], 3)

    def test_report_json_created(self):
        from powerbi_import.paginated_generator import PaginatedReportGenerator
        gen = PaginatedReportGenerator(self.tmp_dir, 'TestReport')
        gen.generate([{'name': 'Test', 'type': 'table'}])
        report_path = os.path.join(self.tmp_dir, 'PaginatedReport', 'report.json')
        self.assertTrue(os.path.exists(report_path))
        with open(report_path, 'r') as f:
            data = json.load(f)
        self.assertEqual(data['name'], 'TestReport')

    def test_header_footer_created(self):
        from powerbi_import.paginated_generator import PaginatedReportGenerator
        gen = PaginatedReportGenerator(self.tmp_dir, 'TestReport')
        gen.generate([{'name': 'Test', 'type': 'table'}])
        for fname in ('header.json', 'footer.json'):
            path = os.path.join(self.tmp_dir, 'PaginatedReport', fname)
            self.assertTrue(os.path.exists(path), f"Missing: {fname}")

    def test_page_files_created(self):
        from powerbi_import.paginated_generator import PaginatedReportGenerator
        gen = PaginatedReportGenerator(self.tmp_dir, 'TestReport')
        gen.generate([{'name': 'P1'}, {'name': 'P2'}])
        pages_dir = os.path.join(self.tmp_dir, 'PaginatedReport', 'pages')
        self.assertTrue(os.path.exists(os.path.join(pages_dir, 'page1.json')))
        self.assertTrue(os.path.exists(os.path.join(pages_dir, 'page2.json')))

    def test_portrait_orientation(self):
        from powerbi_import.paginated_generator import PaginatedReportGenerator
        gen = PaginatedReportGenerator(self.tmp_dir, 'TestReport')
        gen.generate([{'name': 'Test'}], orientation='portrait')
        report_path = os.path.join(self.tmp_dir, 'PaginatedReport', 'report.json')
        with open(report_path, 'r') as f:
            data = json.load(f)
        # Portrait swaps width/height
        self.assertIn('in', data['pageWidth'])
        self.assertIn('in', data['pageHeight'])

    def test_a4_page_size(self):
        from powerbi_import.paginated_generator import PaginatedReportGenerator
        gen = PaginatedReportGenerator(self.tmp_dir, 'TestReport')
        gen.generate([{'name': 'Test'}], page_size='a4')
        report_path = os.path.join(self.tmp_dir, 'PaginatedReport', 'report.json')
        with open(report_path, 'r') as f:
            data = json.load(f)
        # A4 landscape width ~ 11.69in
        self.assertIn('11.69', data['pageWidth'])

    def test_datasource_refs(self):
        from powerbi_import.paginated_generator import PaginatedReportGenerator
        gen = PaginatedReportGenerator(self.tmp_dir, 'TestReport')
        ds = [{'name': 'MyDS', 'connection': {'type': 'SQL Server'}}]
        gen.generate([{'name': 'Test'}], datasources=ds)
        ds_path = os.path.join(self.tmp_dir, 'PaginatedReport', 'datasources.json')
        self.assertTrue(os.path.exists(ds_path))

    def test_tablix_structure(self):
        from powerbi_import.paginated_generator import PaginatedReportGenerator
        gen = PaginatedReportGenerator(self.tmp_dir, 'TestReport')
        tablix = gen._create_tablix(
            {'name': 'Test', 'dimensions': [{'field': 'Category'}],
             'measures': [{'field': 'Amount'}]}, 1)
        self.assertEqual(tablix['type'], 'Tablix')
        self.assertEqual(len(tablix['columns']), 2)
        self.assertEqual(tablix['rowGroups'], ['Category'])

    def test_chart_structure(self):
        from powerbi_import.paginated_generator import PaginatedReportGenerator
        gen = PaginatedReportGenerator(self.tmp_dir, 'TestReport')
        chart = gen._create_chart(
            {'name': 'Test', 'dimensions': ['Cat'], 'measures': ['Val']},
            1, 'barchart')
        self.assertEqual(chart['type'], 'Chart')
        self.assertEqual(chart['chartType'], 'Column')


# ════════════════════════════════════════════════════════════════════
#  Prep → Dataflow Gen2 Tests (Sprint 108)
# ════════════════════════════════════════════════════════════════════

class TestPrepToDataflow(unittest.TestCase):
    """Tests for Prep flow → Dataflow Gen2 direct conversion."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_import(self):
        from powerbi_import.dataflow_generator import DataflowGenerator
        self.assertIsNotNone(DataflowGenerator)

    def test_generate_from_prep_flow_exists(self):
        from powerbi_import.dataflow_generator import DataflowGenerator
        gen = DataflowGenerator(self.tmp_dir, 'TestProject')
        self.assertTrue(hasattr(gen, 'generate_from_prep_flow'))

    def test_generate_from_prep_empty(self):
        from powerbi_import.dataflow_generator import DataflowGenerator
        gen = DataflowGenerator(self.tmp_dir, 'TestProject')
        result = gen.generate_from_prep_flow({'datasources': []})
        self.assertEqual(result['queries'], 0)
        self.assertEqual(result['prep_steps'], 0)

    def test_generate_from_prep_with_datasources(self):
        from powerbi_import.dataflow_generator import DataflowGenerator
        gen = DataflowGenerator(self.tmp_dir, 'TestProject')
        prep_data = {
            'datasources': [
                {
                    'name': 'Sales_Clean',
                    'm_query': 'let\n    Source = Csv.Document("sales.csv")\nin\n    Source',
                    'is_prep_source': True,
                    'connection': {'type': 'csv'},
                },
                {
                    'name': 'Products',
                    'm_query': 'let\n    Source = Sql.Database("srv", "db")\nin\n    Source',
                    'is_prep_source': False,
                    'connection': {'type': 'SQL Server'},
                },
            ],
        }
        result = gen.generate_from_prep_flow(prep_data)
        self.assertEqual(result['queries'], 2)
        self.assertEqual(result['prep_steps'], 1)

    def test_generate_from_prep_files_created(self):
        from powerbi_import.dataflow_generator import DataflowGenerator
        gen = DataflowGenerator(self.tmp_dir, 'TestProject')
        prep_data = {
            'datasources': [{
                'name': 'TestTable',
                'm_query': 'let Source = #table({}, {}) in Source',
                'connection': {'type': 'csv'},
            }],
        }
        gen.generate_from_prep_flow(prep_data)
        df_dir = os.path.join(self.tmp_dir, 'TestProject.Dataflow')
        self.assertTrue(os.path.exists(os.path.join(df_dir, 'dataflow_definition.json')))
        self.assertTrue(os.path.exists(os.path.join(df_dir, 'mashup.pq')))

    def test_generate_from_prep_dedup_names(self):
        from powerbi_import.dataflow_generator import DataflowGenerator
        gen = DataflowGenerator(self.tmp_dir, 'TestProject')
        prep_data = {
            'datasources': [
                {'name': 'Orders', 'm_query': 'let S=1 in S', 'connection': {'type': 'csv'}},
                {'name': 'Orders', 'm_query': 'let S=2 in S', 'connection': {'type': 'csv'}},
            ],
        }
        result = gen.generate_from_prep_flow(prep_data)
        self.assertEqual(result['queries'], 2)

    def test_generate_from_prep_no_m_query_skipped(self):
        from powerbi_import.dataflow_generator import DataflowGenerator
        gen = DataflowGenerator(self.tmp_dir, 'TestProject')
        prep_data = {
            'datasources': [
                {'name': 'Empty', 'm_query': '', 'connection': {'type': 'csv'}},
                {'name': 'Valid', 'm_query': 'let S=1 in S', 'connection': {'type': 'csv'}},
            ],
        }
        result = gen.generate_from_prep_flow(prep_data)
        self.assertEqual(result['queries'], 1)


# ════════════════════════════════════════════════════════════════════
#  Web UI Tests (Sprint 81)
# ════════════════════════════════════════════════════════════════════

class TestWebUI(unittest.TestCase):
    """Tests for web/app.py."""

    def test_import(self):
        from web.app import launch_web_ui, _zip_directory, _run_migration_pipeline
        self.assertIsNotNone(launch_web_ui)

    def test_zip_directory(self):
        from web.app import _zip_directory
        import zipfile
        with tempfile.TemporaryDirectory() as src:
            with open(os.path.join(src, 'test.txt'), 'w') as f:
                f.write('hello')
            zip_path = os.path.join(src, 'test.zip')
            _zip_directory(src, zip_path)
            self.assertTrue(os.path.exists(zip_path))
            with zipfile.ZipFile(zip_path, 'r') as zf:
                self.assertIn('test.txt', zf.namelist())

    def test_run_migration_pipeline_no_file(self):
        from web.app import _run_migration_pipeline
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_migration_pipeline('/nonexistent.twbx', {'output_dir': tmp})
            self.assertFalse(result['success'])
            self.assertGreater(len(result['errors']), 0)

    def test_generate_upload_html(self):
        from web.app import _generate_upload_html
        html = _generate_upload_html()
        self.assertIn('<form', html)
        self.assertIn('.twb', html)
        self.assertIn('method="POST"', html)

    def test_has_streamlit_flag(self):
        from web.app import _HAS_STREAMLIT
        self.assertIsInstance(_HAS_STREAMLIT, bool)


# ════════════════════════════════════════════════════════════════════
#  CLI Flag Tests (Sprint 108)
# ════════════════════════════════════════════════════════════════════

class TestCLIFlags(unittest.TestCase):
    """Tests for new CLI flags in migrate.py."""

    def _get_parser(self):
        sys.path.insert(0, _ROOT)
        from migrate import _build_argument_parser
        return _build_argument_parser()

    def test_llm_refine_flag(self):
        parser = self._get_parser()
        args = parser.parse_args(['test.twbx', '--llm-refine'])
        self.assertTrue(args.llm_refine)

    def test_llm_provider_default(self):
        parser = self._get_parser()
        args = parser.parse_args(['test.twbx'])
        self.assertEqual(args.llm_provider, 'openai')

    def test_llm_provider_anthropic(self):
        parser = self._get_parser()
        args = parser.parse_args(['test.twbx', '--llm-provider', 'anthropic'])
        self.assertEqual(args.llm_provider, 'anthropic')

    def test_llm_max_calls_default(self):
        parser = self._get_parser()
        args = parser.parse_args(['test.twbx'])
        self.assertEqual(args.llm_max_calls, 100)

    def test_llm_max_calls_custom(self):
        parser = self._get_parser()
        args = parser.parse_args(['test.twbx', '--llm-max-calls', '50'])
        self.assertEqual(args.llm_max_calls, 50)

    def test_llm_dry_run_flag(self):
        parser = self._get_parser()
        args = parser.parse_args(['test.twbx', '--llm-dry-run'])
        self.assertTrue(args.llm_dry_run)

    def test_web_ui_flag(self):
        parser = self._get_parser()
        args = parser.parse_args(['--web-ui'])
        self.assertTrue(args.web_ui)

    def test_web_port_default(self):
        parser = self._get_parser()
        args = parser.parse_args(['test.twbx'])
        self.assertEqual(args.web_port, 8501)

    def test_web_port_custom(self):
        parser = self._get_parser()
        args = parser.parse_args(['test.twbx', '--web-port', '9000'])
        self.assertEqual(args.web_port, 9000)

    def test_prep_to_dataflow_flag(self):
        parser = self._get_parser()
        args = parser.parse_args(['test.twbx', '--prep-to-dataflow'])
        self.assertTrue(args.prep_to_dataflow)

    def test_paginated_report_flag(self):
        parser = self._get_parser()
        args = parser.parse_args(['test.twbx', '--paginated-report'])
        self.assertTrue(args.paginated_report)

    def test_paginated_orientation_default(self):
        parser = self._get_parser()
        args = parser.parse_args(['test.twbx'])
        self.assertEqual(args.paginated_orientation, 'landscape')

    def test_paginated_orientation_portrait(self):
        parser = self._get_parser()
        args = parser.parse_args(['test.twbx', '--paginated-orientation', 'portrait'])
        self.assertEqual(args.paginated_orientation, 'portrait')

    def test_paginated_page_size_default(self):
        parser = self._get_parser()
        args = parser.parse_args(['test.twbx'])
        self.assertEqual(args.paginated_page_size, 'letter')

    def test_paginated_page_size_a4(self):
        parser = self._get_parser()
        args = parser.parse_args(['test.twbx', '--paginated-page-size', 'a4'])
        self.assertEqual(args.paginated_page_size, 'a4')

    def test_llm_endpoint_flag(self):
        parser = self._get_parser()
        args = parser.parse_args(['test.twbx', '--llm-endpoint', 'https://test.openai.azure.com'])
        self.assertEqual(args.llm_endpoint, 'https://test.openai.azure.com')

    def test_llm_model_flag(self):
        parser = self._get_parser()
        args = parser.parse_args(['test.twbx', '--llm-model', 'gpt-4-turbo'])
        self.assertEqual(args.llm_model, 'gpt-4-turbo')

    def test_all_existing_flags_preserved(self):
        """Verify existing flags are not broken by additions."""
        parser = self._get_parser()
        args = parser.parse_args([
            'test.twbx', '--verbose', '--culture', 'fr-FR',
            '--mode', 'import', '--output-format', 'pbip',
            '--optimize-dax', '--time-intelligence', 'auto',
        ])
        self.assertTrue(args.verbose)
        self.assertEqual(args.culture, 'fr-FR')
        self.assertEqual(args.mode, 'import')
        self.assertTrue(args.optimize_dax)


# ════════════════════════════════════════════════════════════════════
#  Integration Tests
# ════════════════════════════════════════════════════════════════════

class TestV28Integration(unittest.TestCase):
    """Cross-feature integration tests for v28."""

    def test_llm_client_with_optimizer(self):
        """LLM client and DAX optimizer should work together."""
        from powerbi_import.llm_client import LLMClient, refine_approximated_measures
        from powerbi_import.dax_optimizer import optimize_dax

        # Optimize first, then refine
        formula = 'IF(ISBLANK([Sales]), 0, [Sales])'
        optimized, rules = optimize_dax(formula)
        self.assertIn('COALESCE', optimized)

        # LLM should skip non-approximated
        client = LLMClient(provider='openai', api_key='test', dry_run=True)
        results = refine_approximated_measures(client, [
            {'name': 'Test', 'expression': optimized, 'annotations': []}
        ])
        self.assertEqual(results[0]['status'], 'skipped')

    def test_paginated_with_extension_type(self):
        """Paginated generator should handle extension types gracefully."""
        from powerbi_import.paginated_generator import PaginatedReportGenerator
        with tempfile.TemporaryDirectory() as tmp:
            gen = PaginatedReportGenerator(tmp, 'Test')
            # Extension type isn't in paginated map → fallback to Textbox placeholder
            ws = [{'name': 'Extension', 'type': 'extension', 'mark_type': 'extension'}]
            stats = gen.generate(ws)
            self.assertEqual(stats['pages'], 1)
            self.assertEqual(stats['textboxes'], 1)

    def test_cultures_cover_common_pbi_locales(self):
        """All common Power BI locales should have translation support."""
        from powerbi_import.tmdl_generator import _DISPLAY_FOLDER_TRANSLATIONS
        common_pbi_locales = [
            'en-US', 'fr-FR', 'de-DE', 'es-ES', 'pt-BR', 'ja-JP',
            'zh-CN', 'ko-KR', 'it-IT', 'nl-NL', 'sv-SE', 'da-DK',
            'nb-NO', 'fi-FI', 'pl-PL', 'tr-TR', 'ru-RU',
        ]
        # en-US doesn't need translation
        for locale in common_pbi_locales[1:]:
            self.assertIn(locale, _DISPLAY_FOLDER_TRANSLATIONS,
                          f"PBI locale {locale} missing translations")


if __name__ == '__main__':
    unittest.main()
