"""
Tests for Sprint 58 — Script Visual Migration.

Covers:
  - Python script visual with _arg mapping
  - R script visual with _arg mapping
  - Script visual with no fields (fallback scaffold)
  - Script visual with no _arg references (original as comments)
  - Visual container structure (PBIR schema, position, annotations)
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from powerbi_import.visual_generator import generate_script_visual


class TestScriptVisualPython(unittest.TestCase):
    def test_arg_mapping(self):
        script_info = {
            'language': 'python',
            'code': 'result = _arg1 * _arg2',
            'function': 'SCRIPT_REAL',
        }
        v = generate_script_visual('test', script_info, fields=['Sales[Revenue]', 'Sales[Cost]'])
        script = v['visual']['script']['scriptText']
        self.assertIn('dataset["Revenue"]', script)
        self.assertIn('dataset["Cost"]', script)
        self.assertNotIn('_arg1', script)
        self.assertNotIn('_arg2', script)

    def test_no_fields_fallback(self):
        script_info = {
            'language': 'python',
            'code': 'x = _arg1 + 1',
            'function': 'SCRIPT_INT',
        }
        v = generate_script_visual('test', script_info, fields=None)
        script = v['visual']['script']['scriptText']
        # Without fields, _arg1 not replaced → code in comments
        self.assertIn('_arg1', script)
        self.assertIn('TODO', script)

    def test_no_arg_refs_in_code(self):
        script_info = {
            'language': 'python',
            'code': 'import numpy as np\nresult = np.pi',
            'function': 'SCRIPT_REAL',
        }
        v = generate_script_visual('test', script_info, fields=['Sales[X]'])
        script = v['visual']['script']['scriptText']
        # No _arg in code → adapted_code == original_code → fallback path
        self.assertIn('TODO', script)

    def test_visual_type(self):
        script_info = {'language': 'python', 'code': '_arg1', 'function': 'SCRIPT_REAL'}
        v = generate_script_visual('test', script_info, fields=['Sales[X]'])
        self.assertEqual(v['visual']['visualType'], 'scriptVisual')

    def test_import_pandas(self):
        script_info = {'language': 'python', 'code': '_arg1 + 1', 'function': 'SCRIPT_INT'}
        v = generate_script_visual('test', script_info, fields=['Sales[Val]'])
        script = v['visual']['script']['scriptText']
        self.assertIn('import pandas as pd', script)
        self.assertIn('import matplotlib.pyplot as plt', script)


class TestScriptVisualR(unittest.TestCase):
    def test_arg_mapping_r(self):
        script_info = {
            'language': 'r',
            'code': 'result <- _arg1 * _arg2',
            'function': 'SCRIPT_REAL',
        }
        v = generate_script_visual('test', script_info, fields=['T[A]', 'T[B]'])
        script = v['visual']['script']['scriptText']
        self.assertIn('dataset$A', script)
        self.assertIn('dataset$B', script)
        self.assertNotIn('_arg1', script)

    def test_visual_type_r(self):
        script_info = {'language': 'r', 'code': '_arg1', 'function': 'SCRIPT_INT'}
        v = generate_script_visual('test', script_info, fields=['T[X]'])
        self.assertEqual(v['visual']['visualType'], 'scriptRVisual')

    def test_no_args_fallback_r(self):
        script_info = {'language': 'r', 'code': 'plot(1)', 'function': 'SCRIPT_REAL'}
        v = generate_script_visual('test', script_info, fields=['T[X]'])
        script = v['visual']['script']['scriptText']
        self.assertIn('TODO', script)


class TestScriptVisualContainer(unittest.TestCase):
    def test_pbir_schema(self):
        script_info = {'language': 'python', 'code': 'x=1', 'function': 'SCRIPT_REAL'}
        v = generate_script_visual('test', script_info, x=20, y=30, width=500, height=400)
        self.assertIn('$schema', v)
        self.assertEqual(v['position']['x'], 20)
        self.assertEqual(v['position']['y'], 30)
        self.assertEqual(v['position']['width'], 500)
        self.assertEqual(v['position']['height'], 400)

    def test_annotation(self):
        script_info = {'language': 'python', 'code': 'x=1', 'function': 'SCRIPT_BOOL'}
        v = generate_script_visual('test', script_info)
        annotations = v['visual'].get('annotations', [])
        note = [a for a in annotations if a['name'] == 'MigrationNote']
        self.assertEqual(len(note), 1)
        self.assertIn('SCRIPT_BOOL', note[0]['value'])

    def test_script_provider(self):
        script_info = {'language': 'python', 'code': 'x=1', 'function': 'SCRIPT_REAL'}
        v = generate_script_visual('test', script_info)
        self.assertEqual(v['visual']['script']['scriptProviderDefault'], 'python')
        self.assertEqual(v['visual']['script']['scriptOutputType'], 'static')

    def test_bare_field_name(self):
        """Fields without brackets should still map correctly."""
        script_info = {'language': 'python', 'code': '_arg1 + 1', 'function': 'SCRIPT_INT'}
        v = generate_script_visual('test', script_info, fields=['Revenue'])
        script = v['visual']['script']['scriptText']
        self.assertIn('dataset["Revenue"]', script)


if __name__ == '__main__':
    unittest.main()
