"""
Tests for thin_report_generator module — Sprint 56.

Covers:
  - ThinReportGenerator instantiation
  - generate_thin_report directory creation
  - definition.pbir byPath wiring
  - .pbip file content
  - .platform file content
  - Field remapping for namespaced measures
  - Edge cases: empty workbook, no field_mapping
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from powerbi_import.thin_report_generator import ThinReportGenerator, _write_json


class TestThinReportGeneratorInit(unittest.TestCase):
    def test_instantiation(self):
        gen = ThinReportGenerator('SharedModel', '/tmp/output')
        self.assertEqual(gen.semantic_model_name, 'SharedModel')
        self.assertIn('output', gen.output_dir)

    def test_output_dir_absolute(self):
        gen = ThinReportGenerator('SM', 'relative/path')
        self.assertTrue(os.path.isabs(gen.output_dir))


class TestWritePlatform(unittest.TestCase):
    def test_platform_file_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = ThinReportGenerator('SM', tmpdir)
            report_dir = os.path.join(tmpdir, 'TestReport.Report')
            os.makedirs(report_dir)
            gen._write_platform(report_dir, 'TestReport')
            path = os.path.join(report_dir, '.platform')
            self.assertTrue(os.path.exists(path))
            with open(path, 'r') as f:
                data = json.load(f)
            self.assertIn('$schema', data)
            self.assertEqual(data['metadata']['type'], 'Report')
            self.assertEqual(data['metadata']['displayName'], 'TestReport')
            self.assertIn('logicalId', data['config'])


class TestWriteDefinitionPbir(unittest.TestCase):
    def test_pbir_bypath_wiring(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = ThinReportGenerator('SharedSales', tmpdir)
            report_dir = os.path.join(tmpdir, 'Report.Report')
            os.makedirs(report_dir)
            gen._write_definition_pbir(report_dir)
            path = os.path.join(report_dir, 'definition.pbir')
            self.assertTrue(os.path.exists(path))
            with open(path, 'r') as f:
                data = json.load(f)
            self.assertEqual(data['version'], '4.0')
            self.assertEqual(
                data['datasetReference']['byPath']['path'],
                '../SharedSales.SemanticModel')

    def test_pbir_schema_reference(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = ThinReportGenerator('SM', tmpdir)
            report_dir = os.path.join(tmpdir, 'R.Report')
            os.makedirs(report_dir)
            gen._write_definition_pbir(report_dir)
            with open(os.path.join(report_dir, 'definition.pbir'), 'r') as f:
                data = json.load(f)
            self.assertIn('definitionProperties', data['$schema'])


class TestWritePbip(unittest.TestCase):
    def test_pbip_file_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = ThinReportGenerator('SM', tmpdir)
            gen._write_pbip('SalesOverview')
            pbip_path = os.path.join(tmpdir, 'SalesOverview.pbip')
            self.assertTrue(os.path.exists(pbip_path))
            with open(pbip_path, 'r') as f:
                data = json.load(f)
            self.assertIn('$schema', data)
            self.assertEqual(data['version'], '1.0')
            self.assertEqual(
                data['artifacts'][0]['report']['path'],
                'SalesOverview.Report')
            self.assertTrue(data['settings']['enableAutoRecovery'])


class TestRemapFields(unittest.TestCase):
    def test_worksheet_column_remap(self):
        gen = ThinReportGenerator('SM', '/tmp')
        co = {
            'worksheets': [
                {
                    'name': 'Sheet1',
                    'columns': [{'name': 'OldMeasure'}],
                    'filters': [],
                    'mark_encoding': {},
                },
            ],
        }
        mapping = {'OldMeasure': 'NewMeasure (wb1)'}
        result = gen._remap_fields(co, mapping)
        self.assertEqual(result['worksheets'][0]['columns'][0]['name'],
                         'NewMeasure (wb1)')

    def test_filter_field_remap(self):
        gen = ThinReportGenerator('SM', '/tmp')
        co = {
            'worksheets': [
                {
                    'name': 'S1',
                    'columns': [],
                    'filters': [{'field': 'OldField'}],
                    'mark_encoding': {},
                },
            ],
            'filters': [{'field': 'OldField'}],
        }
        mapping = {'OldField': 'NewField'}
        result = gen._remap_fields(co, mapping)
        self.assertEqual(result['worksheets'][0]['filters'][0]['field'], 'NewField')
        self.assertEqual(result['filters'][0]['field'], 'NewField')

    def test_mark_encoding_dict_remap(self):
        gen = ThinReportGenerator('SM', '/tmp')
        co = {
            'worksheets': [
                {
                    'name': 'S1',
                    'columns': [],
                    'filters': [],
                    'mark_encoding': {'color': {'field': 'OldColor'}},
                },
            ],
        }
        mapping = {'OldColor': 'NewColor'}
        result = gen._remap_fields(co, mapping)
        self.assertEqual(
            result['worksheets'][0]['mark_encoding']['color']['field'],
            'NewColor')

    def test_mark_encoding_list_remap(self):
        gen = ThinReportGenerator('SM', '/tmp')
        co = {
            'worksheets': [
                {
                    'name': 'S1',
                    'columns': [],
                    'filters': [],
                    'mark_encoding': {'tooltip': [{'field': 'OldTip'}]},
                },
            ],
        }
        mapping = {'OldTip': 'NewTip'}
        result = gen._remap_fields(co, mapping)
        self.assertEqual(
            result['worksheets'][0]['mark_encoding']['tooltip'][0]['field'],
            'NewTip')

    def test_action_field_remap(self):
        gen = ThinReportGenerator('SM', '/tmp')
        co = {
            'actions': [{'source_field': 'OldAction'}],
            'worksheets': [],
        }
        mapping = {'OldAction': 'NewAction'}
        result = gen._remap_fields(co, mapping)
        self.assertEqual(result['actions'][0]['source_field'], 'NewAction')

    def test_no_mapping_returns_unchanged(self):
        gen = ThinReportGenerator('SM', '/tmp')
        co = {'worksheets': [{'name': 'S1', 'columns': [{'name': 'C1'}],
                               'filters': [], 'mark_encoding': {}}]}
        result = gen._remap_fields(co, None)
        self.assertEqual(result, co)

    def test_empty_mapping(self):
        gen = ThinReportGenerator('SM', '/tmp')
        co = {'worksheets': [{'name': 'S1', 'columns': [{'name': 'C1'}],
                               'filters': [], 'mark_encoding': {}}]}
        result = gen._remap_fields(co, {})
        self.assertEqual(result, co)

    def test_sort_field_remap(self):
        gen = ThinReportGenerator('SM', '/tmp')
        co = {
            'worksheets': [
                {
                    'name': 'S1',
                    'columns': [],
                    'filters': [],
                    'mark_encoding': {},
                    'sort_fields': [{'field': 'OldSort'}],
                },
            ],
        }
        mapping = {'OldSort': 'NewSort'}
        result = gen._remap_fields(co, mapping)
        self.assertEqual(
            result['worksheets'][0]['sort_fields'][0]['field'], 'NewSort')

    def test_calculation_caption_remap(self):
        gen = ThinReportGenerator('SM', '/tmp')
        co = {
            'calculations': [{'caption': 'OldCalc'}],
            'worksheets': [],
        }
        mapping = {'OldCalc': 'NewCalc'}
        result = gen._remap_fields(co, mapping)
        self.assertEqual(result['calculations'][0]['caption'], 'NewCalc')

    def test_deep_copy_no_mutation(self):
        gen = ThinReportGenerator('SM', '/tmp')
        co = {'worksheets': [{'name': 'S', 'columns': [{'name': 'A'}],
                               'filters': [], 'mark_encoding': {}}]}
        mapping = {'A': 'B'}
        gen._remap_fields(co, mapping)
        self.assertEqual(co['worksheets'][0]['columns'][0]['name'], 'A')


class TestGenerateThinReport(unittest.TestCase):
    @patch('powerbi_import.thin_report_generator.ThinReportGenerator._generate_report_content')
    def test_creates_report_dir(self, mock_gen_content):
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = ThinReportGenerator('SM', tmpdir)
            result = gen.generate_thin_report('Sales', {'worksheets': []})
            self.assertTrue(os.path.isdir(result))
            self.assertTrue(result.endswith('.Report'))

    @patch('powerbi_import.thin_report_generator.ThinReportGenerator._generate_report_content')
    def test_creates_platform_and_pbir(self, mock_gen_content):
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = ThinReportGenerator('SM', tmpdir)
            result = gen.generate_thin_report('Dash', {'worksheets': []})
            self.assertTrue(os.path.exists(
                os.path.join(result, '.platform')))
            self.assertTrue(os.path.exists(
                os.path.join(result, 'definition.pbir')))
            self.assertTrue(os.path.exists(
                os.path.join(tmpdir, 'Dash.pbip')))

    @patch('powerbi_import.thin_report_generator.ThinReportGenerator._generate_report_content')
    def test_with_field_mapping(self, mock_gen_content):
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = ThinReportGenerator('SM', tmpdir)
            co = {
                'worksheets': [
                    {'name': 'S', 'columns': [{'name': 'Old'}],
                     'filters': [], 'mark_encoding': {}},
                ],
            }
            mapping = {'Old': 'New'}
            gen.generate_thin_report('R', co, field_mapping=mapping)
            # Verify _generate_report_content was called with remapped data
            call_args = mock_gen_content.call_args
            remapped_co = call_args[0][2]
            self.assertEqual(
                remapped_co['worksheets'][0]['columns'][0]['name'], 'New')


class TestWriteJson(unittest.TestCase):
    def test_write_json_creates_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'sub', 'dir', 'file.json')
            _write_json(path, {'key': 'value'})
            self.assertTrue(os.path.exists(path))
            with open(path, 'r') as f:
                self.assertEqual(json.load(f), {'key': 'value'})


if __name__ == '__main__':
    unittest.main()
