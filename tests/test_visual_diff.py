"""
Tests for visual_diff module — Sprint 56.

Covers:
  - generate_visual_diff HTML output
  - generate_visual_diff_json dict output
  - _diff_worksheet matching logic
  - _extract_pbi_visual_info
  - _load_pbi_visuals
  - Encoding gap detection
  - Field coverage calculation
  - Edge cases: empty worksheets, no PBI visuals, unknown mark types
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from powerbi_import.visual_diff import (
    generate_visual_diff,
    generate_visual_diff_json,
    _diff_worksheet,
    _extract_pbi_visual_info,
    _load_pbi_visuals,
    _MARK_TO_PBI,
    _ENCODING_TYPES,
    _esc,
)


class TestMarkToPbiMap(unittest.TestCase):
    def test_common_marks(self):
        self.assertEqual(_MARK_TO_PBI['bar'], 'clusteredBarChart')
        self.assertEqual(_MARK_TO_PBI['line'], 'lineChart')
        self.assertEqual(_MARK_TO_PBI['pie'], 'pieChart')
        self.assertEqual(_MARK_TO_PBI['map'], 'map')

    def test_map_not_empty(self):
        self.assertGreater(len(_MARK_TO_PBI), 10)


class TestEsc(unittest.TestCase):
    def test_html_escape(self):
        self.assertEqual(_esc('<script>'), '&lt;script&gt;')

    def test_none_returns_empty(self):
        self.assertEqual(_esc(None), '')


class TestEncodingTypes(unittest.TestCase):
    def test_expected_types(self):
        for t in ('color', 'size', 'shape', 'label', 'tooltip', 'detail'):
            self.assertIn(t, _ENCODING_TYPES)


class TestExtractPbiVisualInfo(unittest.TestCase):
    def test_basic_visual(self):
        v = {
            'visual': {
                'visualType': 'clusteredBarChart',
            },
            'title': {'text': 'Sales Chart'},
        }
        info = _extract_pbi_visual_info(v)
        self.assertEqual(info['visualType'], 'clusteredBarChart')
        self.assertEqual(info['title'], 'Sales Chart')

    def test_visual_with_query_fields(self):
        v = {
            'singleVisual': {'visualType': 'lineChart'},
            'query': {
                'Commands': [{
                    'SemanticQueryDataShapeCommand': {
                        'Query': {
                            'Select': [{
                                'Column': {
                                    'Expression': {
                                        'SourceRef': {'Entity': 'Sales'}
                                    },
                                    'Property': 'Revenue',
                                }
                            }],
                        },
                    },
                }],
            },
        }
        info = _extract_pbi_visual_info(v)
        self.assertIn('Sales[Revenue]', info['fields'])

    def test_empty_visual(self):
        info = _extract_pbi_visual_info({})
        self.assertEqual(info['visualType'], 'unknown')
        self.assertEqual(info['fields'], [])


class TestDiffWorksheet(unittest.TestCase):
    def test_exact_match(self):
        ws = {
            'name': 'Sales',
            'mark_type': 'bar',
            'fields': [{'name': 'Revenue', 'role': 'measure'}],
            'mark_encoding': {},
            'filters': [],
        }
        pbi = [{
            'visual': {'visualType': 'clusteredBarChart'},
            'title': {'text': 'Sales'},
        }]
        result = _diff_worksheet(ws, pbi)
        self.assertEqual(result['name'], 'Sales')
        self.assertEqual(result['status'], 'exact')

    def test_unmapped_when_no_pbi_visuals(self):
        ws = {
            'name': 'Empty',
            'mark_type': 'line',
            'fields': [],
            'mark_encoding': {},
            'filters': [],
        }
        result = _diff_worksheet(ws, [])
        self.assertEqual(result['status'], 'unmapped')
        self.assertFalse(result['pbi_matched'])

    def test_field_coverage_calculation(self):
        ws = {
            'name': 'Test',
            'mark_type': 'bar',
            'fields': [
                {'name': 'Revenue'},
                {'name': 'Cost'},
                {'name': 'Unmapped'},
            ],
            'mark_encoding': {},
            'filters': [],
        }
        pbi = [{
            'visual': {'visualType': 'clusteredBarChart'},
            'title': {'text': 'Test'},
            'query': {
                'Commands': [{
                    'SemanticQueryDataShapeCommand': {
                        'Query': {
                            'Select': [{
                                'Column': {
                                    'Expression': {'SourceRef': {'Entity': 'T'}},
                                    'Property': 'Revenue',
                                }
                            }],
                        },
                    },
                }],
            },
        }]
        result = _diff_worksheet(ws, pbi)
        self.assertGreater(result['field_coverage'], 0)
        self.assertLess(result['field_coverage'], 100)

    def test_encoding_detection(self):
        ws = {
            'name': 'Test',
            'mark_type': 'bar',
            'fields': [],
            'mark_encoding': {'color': 'Region', 'size': '', 'tooltip': 'Profit'},
            'filters': [],
        }
        result = _diff_worksheet(ws, [])
        self.assertTrue(result['tableau_encodings']['color'])
        self.assertFalse(result['tableau_encodings']['size'])
        self.assertTrue(result['tableau_encodings']['tooltip'])

    def test_mark_type_as_dict(self):
        ws = {
            'name': 'X',
            'mark_type': {'type': 'pie'},
            'fields': [],
            'mark_encoding': {},
            'filters': [],
        }
        result = _diff_worksheet(ws, [])
        self.assertEqual(result['mark_type'], 'pie')
        self.assertEqual(result['expected_pbi_type'], 'pieChart')

    def test_unknown_mark_defaults_to_tableex(self):
        ws = {
            'name': 'X',
            'mark_type': 'custom_unknown',
            'fields': [],
            'mark_encoding': {},
            'filters': [],
        }
        result = _diff_worksheet(ws, [])
        self.assertEqual(result['expected_pbi_type'], 'tableEx')

    def test_filter_count(self):
        ws = {
            'name': 'X',
            'mark_type': 'bar',
            'fields': [],
            'mark_encoding': {},
            'filters': [{'field': 'A'}, {'field': 'B'}],
        }
        result = _diff_worksheet(ws, [])
        self.assertEqual(result['tableau_filter_count'], 2)

    def test_string_fields(self):
        ws = {
            'name': 'X',
            'mark_type': 'bar',
            'fields': ['Revenue', 'Cost'],
            'mark_encoding': {},
            'filters': [],
        }
        result = _diff_worksheet(ws, [])
        self.assertEqual(len(result['tableau_fields']), 2)

    def test_100_percent_coverage_when_no_fields(self):
        ws = {
            'name': 'X',
            'mark_type': 'bar',
            'fields': [],
            'mark_encoding': {},
            'filters': [],
        }
        result = _diff_worksheet(ws, [])
        self.assertEqual(result['field_coverage'], 100)


class TestLoadPbiVisuals(unittest.TestCase):
    def test_load_from_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vdir = os.path.join(tmpdir, 'pages', 'page1', 'visuals', 'v1')
            os.makedirs(vdir)
            with open(os.path.join(vdir, 'visual.json'), 'w') as f:
                json.dump({'visual': {'visualType': 'card'}}, f)
            result = _load_pbi_visuals(tmpdir)
            self.assertEqual(len(result), 1)

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _load_pbi_visuals(tmpdir)
            self.assertEqual(len(result), 0)

    def test_invalid_json_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vdir = os.path.join(tmpdir, 'v')
            os.makedirs(vdir)
            with open(os.path.join(vdir, 'visual.json'), 'w') as f:
                f.write('not json')
            result = _load_pbi_visuals(tmpdir)
            self.assertEqual(len(result), 0)


class TestGenerateVisualDiffJson(unittest.TestCase):
    def test_empty_worksheets(self):
        result = generate_visual_diff_json({}, '/nonexistent')
        self.assertEqual(result['total'], 0)
        self.assertEqual(result['avg_field_coverage'], 100)

    def test_with_worksheets(self):
        data = {
            'worksheets': [
                {
                    'name': 'WS1',
                    'mark_type': 'bar',
                    'fields': [{'name': 'F1'}],
                    'mark_encoding': {},
                    'filters': [],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            result = generate_visual_diff_json(data, tmpdir)
        self.assertEqual(result['total'], 1)
        self.assertIn('visuals', result)

    def test_worksheets_as_dict(self):
        data = {
            'worksheets': {
                'worksheets': [
                    {
                        'name': 'WS1', 'mark_type': 'bar',
                        'fields': [], 'mark_encoding': {}, 'filters': [],
                    },
                ]
            },
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            result = generate_visual_diff_json(data, tmpdir)
        self.assertEqual(result['total'], 1)


class TestGenerateVisualDiffHtml(unittest.TestCase):
    def test_generates_html_file(self):
        data = {
            'worksheets': [
                {
                    'name': 'Sheet1', 'mark_type': 'bar',
                    'fields': [{'name': 'Revenue'}],
                    'mark_encoding': {'color': 'Region'},
                    'filters': [{'field': 'Year'}],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            pbip_dir = os.path.join(tmpdir, 'project.Report')
            os.makedirs(pbip_dir)
            output = os.path.join(tmpdir, 'diff.html')
            result = generate_visual_diff(data, pbip_dir, output_path=output)
            self.assertTrue(os.path.exists(result))
            with open(result, 'r') as f:
                html = f.read()
            self.assertIn('Visual Diff Report', html)
            self.assertIn('Sheet1', html)

    def test_default_output_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pbip_dir = os.path.join(tmpdir, 'MyProject.Report')
            os.makedirs(pbip_dir)
            result = generate_visual_diff({'worksheets': []}, pbip_dir)
            self.assertTrue(os.path.exists(result))
            self.assertTrue(result.endswith('.html'))

    def test_multiple_worksheets(self):
        data = {
            'worksheets': [
                {'name': f'WS{i}', 'mark_type': 'bar',
                 'fields': [], 'mark_encoding': {}, 'filters': []}
                for i in range(5)
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            pbip_dir = os.path.join(tmpdir, 'proj.Report')
            os.makedirs(pbip_dir)
            output = os.path.join(tmpdir, 'diff.html')
            result = generate_visual_diff(data, pbip_dir, output_path=output)
            with open(result, 'r') as f:
                html = f.read()
            for i in range(5):
                self.assertIn(f'WS{i}', html)


if __name__ == '__main__':
    unittest.main()
