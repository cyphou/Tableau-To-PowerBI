"""
Tests for Sprint 76 — Dashboard Layout Engine.

Covers: zone hierarchy extraction (_parse_zone_node, extract_zone_hierarchy),
grid-snapping layout algorithm (_build_zone_layout_map, _layout_zone),
floating vs tiled distinction, responsive breakpoints (mobileState),
padding propagation, and real-world NBA layout validation.
"""

import json
import os
import sys
import tempfile
import shutil
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))

from tableau_export.extract_tableau_data import TableauExtractor
from powerbi_import.pbip_generator import PowerBIProjectGenerator


# ── Helpers ─────────────────────────────────────────────────────────

def _make_zone_xml(zone_str):
    """Parse a <zone ...> XML string into an Element."""
    return ET.fromstring(zone_str)


def _make_dashboard_xml(zones_xml, size_w=1000, size_h=800):
    """Build a minimal <dashboard> element with <zones> and <size>."""
    xml = f'''<dashboard name="Test">
        <size maxwidth="{size_w}" maxheight="{size_h}" />
        <zones>{zones_xml}</zones>
    </dashboard>'''
    return ET.fromstring(xml)


def _make_extractor():
    """Create a TableauExtractor with minimal args."""
    return TableauExtractor.__new__(TableauExtractor)


def _make_generator():
    """Create a PowerBIProjectGenerator with minimal args for layout testing."""
    gen = PowerBIProjectGenerator.__new__(PowerBIProjectGenerator)
    return gen


# ── Zone Hierarchy Extraction Tests ────────────────────────────────

class TestParseZoneNode(unittest.TestCase):
    """Tests for _parse_zone_node()."""

    def test_leaf_zone_worksheet(self):
        ext = _make_extractor()
        zone = _make_zone_xml('<zone id="10" name="Sales Chart" x="0" y="0" w="50000" h="50000" />')
        result = ext._parse_zone_node(zone)
        self.assertEqual(result['id'], '10')
        self.assertEqual(result['name'], 'Sales Chart')
        self.assertEqual(result['zone_type'], 'worksheet')
        self.assertEqual(result['position'], {'x': 0, 'y': 0, 'w': 50000, 'h': 50000})
        self.assertFalse(result['is_floating'])
        self.assertFalse(result['is_fixed'])
        self.assertEqual(result['children'], [])

    def test_leaf_zone_with_type_v2(self):
        ext = _make_extractor()
        zone = _make_zone_xml('<zone id="5" type-v2="text" x="10" y="20" w="100" h="50" />')
        result = ext._parse_zone_node(zone)
        self.assertEqual(result['zone_type'], 'text')

    def test_leaf_zone_with_type(self):
        ext = _make_extractor()
        zone = _make_zone_xml('<zone id="6" type="bitmap" x="0" y="0" w="100" h="100" />')
        result = ext._parse_zone_node(zone)
        self.assertEqual(result['zone_type'], 'bitmap')

    def test_floating_zone(self):
        ext = _make_extractor()
        zone = _make_zone_xml('<zone id="7" name="Floating" is-floating="true" x="100" y="200" w="300" h="400" />')
        result = ext._parse_zone_node(zone)
        self.assertTrue(result['is_floating'])
        self.assertFalse(result['is_fixed'])

    def test_fixed_zone(self):
        ext = _make_extractor()
        zone = _make_zone_xml('<zone id="8" name="Fixed" is-fixed="true" x="0" y="0" w="100" h="50" />')
        result = ext._parse_zone_node(zone)
        self.assertTrue(result['is_fixed'])
        self.assertFalse(result['is_floating'])

    def test_container_horizontal(self):
        ext = _make_extractor()
        zone = _make_zone_xml('''
        <zone id="3" param="horz" x="0" y="0" w="100000" h="20000">
            <zone id="10" name="Logo" x="0" y="0" w="30000" h="20000" />
            <zone id="11" name="Title" x="30000" y="0" w="70000" h="20000" />
        </zone>''')
        result = ext._parse_zone_node(zone)
        self.assertEqual(result['orientation'], 'horz')
        self.assertEqual(len(result['children']), 2)
        self.assertEqual(result['children'][0]['name'], 'Logo')
        self.assertEqual(result['children'][1]['name'], 'Title')

    def test_container_vertical(self):
        ext = _make_extractor()
        zone = _make_zone_xml('''
        <zone id="4" param="vert" x="0" y="0" w="100000" h="100000">
            <zone id="10" name="Header" x="0" y="0" w="100000" h="20000" />
            <zone id="11" name="Body" x="0" y="20000" w="100000" h="80000" />
        </zone>''')
        result = ext._parse_zone_node(zone)
        self.assertEqual(result['orientation'], 'vert')
        self.assertEqual(len(result['children']), 2)

    def test_deep_nesting(self):
        ext = _make_extractor()
        zone = _make_zone_xml('''
        <zone id="1" param="vert" x="0" y="0" w="100000" h="100000">
            <zone id="2" param="horz" x="0" y="0" w="100000" h="50000">
                <zone id="3" name="TopLeft" x="0" y="0" w="50000" h="50000" />
                <zone id="4" name="TopRight" x="50000" y="0" w="50000" h="50000" />
            </zone>
            <zone id="5" name="Bottom" x="0" y="50000" w="100000" h="50000" />
        </zone>''')
        result = ext._parse_zone_node(zone)
        self.assertEqual(len(result['children']), 2)
        self.assertEqual(len(result['children'][0]['children']), 2)
        self.assertEqual(result['children'][0]['children'][0]['name'], 'TopLeft')
        self.assertEqual(result['children'][1]['name'], 'Bottom')

    def test_padding_from_attributes(self):
        ext = _make_extractor()
        zone = _make_zone_xml('<zone id="9" name="Padded" padding-top="10" padding-left="5" x="0" y="0" w="100" h="100" />')
        result = ext._parse_zone_node(zone)
        self.assertIn('padding', result)
        self.assertEqual(result['padding']['top'], 10)
        self.assertEqual(result['padding']['left'], 5)

    def test_padding_from_zone_style(self):
        ext = _make_extractor()
        zone = _make_zone_xml('''
        <zone id="12" name="Styled" x="0" y="0" w="100" h="100">
            <zone-style>
                <format attr="padding-top" value="8" />
                <format attr="padding-bottom" value="4" />
            </zone-style>
        </zone>''')
        result = ext._parse_zone_node(zone)
        self.assertIn('padding', result)
        self.assertEqual(result['padding']['top'], 8)
        self.assertEqual(result['padding']['bottom'], 4)

    def test_empty_zone_no_crash(self):
        ext = _make_extractor()
        zone = _make_zone_xml('<zone id="1" />')
        result = ext._parse_zone_node(zone)
        self.assertEqual(result['id'], '1')
        self.assertEqual(result['children'], [])

    def test_container_auto_detect(self):
        """Container without type or param: has children with no name → layout-basic."""
        ext = _make_extractor()
        zone = _make_zone_xml('''
        <zone id="99" x="0" y="0" w="100" h="100">
            <zone id="100" name="A" x="0" y="0" w="50" h="100" />
            <zone id="101" name="B" x="50" y="0" w="50" h="100" />
        </zone>''')
        result = ext._parse_zone_node(zone)
        self.assertEqual(result['zone_type'], 'layout-basic')


class TestExtractZoneHierarchy(unittest.TestCase):
    """Tests for extract_zone_hierarchy()."""

    def test_empty_dashboard(self):
        ext = _make_extractor()
        db = ET.fromstring('<dashboard name="Empty" />')
        result = ext.extract_zone_hierarchy(db)
        self.assertEqual(result, {})

    def test_empty_zones(self):
        ext = _make_extractor()
        db = ET.fromstring('<dashboard name="NoRoot"><zones /></dashboard>')
        result = ext.extract_zone_hierarchy(db)
        self.assertEqual(result, {})

    def test_single_root(self):
        ext = _make_extractor()
        db = _make_dashboard_xml('<zone id="1" name="Sheet1" x="0" y="0" w="100000" h="100000" />')
        result = ext.extract_zone_hierarchy(db)
        self.assertEqual(result['id'], '1')
        self.assertEqual(result['name'], 'Sheet1')

    def test_tree_with_children(self):
        ext = _make_extractor()
        db = _make_dashboard_xml('''
        <zone id="1" param="vert" x="0" y="0" w="100000" h="100000">
            <zone id="2" name="Top" x="0" y="0" w="100000" h="30000" />
            <zone id="3" name="Bottom" x="0" y="30000" w="100000" h="70000" />
        </zone>''')
        result = ext.extract_zone_hierarchy(db)
        self.assertEqual(len(result['children']), 2)
        self.assertEqual(result['children'][0]['name'], 'Top')


# ── Grid-Snapping Layout Tests ─────────────────────────────────────

class TestBuildZoneLayoutMap(unittest.TestCase):
    """Tests for _build_zone_layout_map() and _layout_zone()."""

    def test_empty_hierarchy(self):
        gen = _make_generator()
        result = gen._build_zone_layout_map({}, 1280, 720)
        self.assertEqual(result, {})

    def test_single_leaf(self):
        gen = _make_generator()
        hierarchy = {
            'id': '1', 'name': 'Sheet1', 'zone_type': 'worksheet',
            'orientation': '', 'position': {'x': 0, 'y': 0, 'w': 100000, 'h': 100000},
            'is_floating': False, 'is_fixed': False, 'children': [],
        }
        result = gen._build_zone_layout_map(hierarchy, 1280, 720)
        self.assertIn('Sheet1', result)
        self.assertEqual(result['Sheet1']['x'], 0)
        self.assertEqual(result['Sheet1']['y'], 0)
        self.assertEqual(result['Sheet1']['w'], 1280)
        self.assertEqual(result['Sheet1']['h'], 720)

    def test_horizontal_split(self):
        gen = _make_generator()
        hierarchy = {
            'id': '1', 'name': '', 'zone_type': 'layout-flow',
            'orientation': 'horz',
            'position': {'x': 0, 'y': 0, 'w': 100000, 'h': 100000},
            'is_floating': False, 'is_fixed': False,
            'children': [
                {'id': '2', 'name': 'Left', 'zone_type': 'worksheet',
                 'orientation': '', 'position': {'x': 0, 'y': 0, 'w': 40000, 'h': 100000},
                 'is_floating': False, 'is_fixed': False, 'children': []},
                {'id': '3', 'name': 'Right', 'zone_type': 'worksheet',
                 'orientation': '', 'position': {'x': 40000, 'y': 0, 'w': 60000, 'h': 100000},
                 'is_floating': False, 'is_fixed': False, 'children': []},
            ],
        }
        result = gen._build_zone_layout_map(hierarchy, 1000, 500)
        # Left should get 40% of 1000 = 400
        self.assertEqual(result['Left']['w'], 400)
        self.assertEqual(result['Left']['x'], 0)
        # Right should get 60% of 1000 = 600
        self.assertEqual(result['Right']['w'], 600)
        self.assertEqual(result['Right']['x'], 400)
        # Both full height
        self.assertEqual(result['Left']['h'], 500)
        self.assertEqual(result['Right']['h'], 500)

    def test_vertical_split(self):
        gen = _make_generator()
        hierarchy = {
            'id': '1', 'name': '', 'zone_type': 'layout-flow',
            'orientation': 'vert',
            'position': {'x': 0, 'y': 0, 'w': 100000, 'h': 100000},
            'is_floating': False, 'is_fixed': False,
            'children': [
                {'id': '2', 'name': 'Top', 'zone_type': 'worksheet',
                 'orientation': '', 'position': {'x': 0, 'y': 0, 'w': 100000, 'h': 25000},
                 'is_floating': False, 'is_fixed': False, 'children': []},
                {'id': '3', 'name': 'Bottom', 'zone_type': 'worksheet',
                 'orientation': '', 'position': {'x': 0, 'y': 25000, 'w': 100000, 'h': 75000},
                 'is_floating': False, 'is_fixed': False, 'children': []},
            ],
        }
        result = gen._build_zone_layout_map(hierarchy, 800, 600)
        self.assertEqual(result['Top']['h'], 150)
        self.assertEqual(result['Top']['y'], 0)
        self.assertEqual(result['Bottom']['h'], 450)
        self.assertEqual(result['Bottom']['y'], 150)

    def test_nested_grid_2x2(self):
        """Two vertical rows, each split horizontally — produces 2×2 grid."""
        gen = _make_generator()
        hierarchy = {
            'id': '1', 'name': '', 'zone_type': '', 'orientation': 'vert',
            'position': {'x': 0, 'y': 0, 'w': 100000, 'h': 100000},
            'is_floating': False, 'is_fixed': False,
            'children': [
                {'id': '2', 'name': '', 'zone_type': '', 'orientation': 'horz',
                 'position': {'x': 0, 'y': 0, 'w': 100000, 'h': 50000},
                 'is_floating': False, 'is_fixed': False,
                 'children': [
                     {'id': '10', 'name': 'TL', 'zone_type': 'worksheet', 'orientation': '',
                      'position': {'x': 0, 'y': 0, 'w': 50000, 'h': 50000},
                      'is_floating': False, 'is_fixed': False, 'children': []},
                     {'id': '11', 'name': 'TR', 'zone_type': 'worksheet', 'orientation': '',
                      'position': {'x': 50000, 'y': 0, 'w': 50000, 'h': 50000},
                      'is_floating': False, 'is_fixed': False, 'children': []},
                 ]},
                {'id': '3', 'name': '', 'zone_type': '', 'orientation': 'horz',
                 'position': {'x': 0, 'y': 50000, 'w': 100000, 'h': 50000},
                 'is_floating': False, 'is_fixed': False,
                 'children': [
                     {'id': '12', 'name': 'BL', 'zone_type': 'worksheet', 'orientation': '',
                      'position': {'x': 0, 'y': 50000, 'w': 50000, 'h': 50000},
                      'is_floating': False, 'is_fixed': False, 'children': []},
                     {'id': '13', 'name': 'BR', 'zone_type': 'worksheet', 'orientation': '',
                      'position': {'x': 50000, 'y': 50000, 'w': 50000, 'h': 50000},
                      'is_floating': False, 'is_fixed': False, 'children': []},
                 ]},
            ],
        }
        result = gen._build_zone_layout_map(hierarchy, 1000, 800)
        self.assertEqual(result['TL'], {'x': 0, 'y': 0, 'w': 500, 'h': 400})
        self.assertEqual(result['TR'], {'x': 500, 'y': 0, 'w': 500, 'h': 400})
        self.assertEqual(result['BL'], {'x': 0, 'y': 400, 'w': 500, 'h': 400})
        self.assertEqual(result['BR'], {'x': 500, 'y': 400, 'w': 500, 'h': 400})

    def test_3x3_grid(self):
        """3 rows × 3 cols — verify even split."""
        gen = _make_generator()
        children_rows = []
        idx = 10
        for row in range(3):
            row_children = []
            for col in range(3):
                row_children.append({
                    'id': str(idx), 'name': f'R{row}C{col}', 'zone_type': 'worksheet',
                    'orientation': '',
                    'position': {'x': col * 33333, 'y': row * 33333, 'w': 33333, 'h': 33333},
                    'is_floating': False, 'is_fixed': False, 'children': [],
                })
                idx += 1
            children_rows.append({
                'id': str(row + 2), 'name': '', 'zone_type': '', 'orientation': 'horz',
                'position': {'x': 0, 'y': row * 33333, 'w': 99999, 'h': 33333},
                'is_floating': False, 'is_fixed': False, 'children': row_children,
            })
        hierarchy = {
            'id': '1', 'name': '', 'zone_type': '', 'orientation': 'vert',
            'position': {'x': 0, 'y': 0, 'w': 99999, 'h': 99999},
            'is_floating': False, 'is_fixed': False, 'children': children_rows,
        }
        result = gen._build_zone_layout_map(hierarchy, 900, 900)
        # Each cell: 300x300
        self.assertEqual(result['R0C0']['w'], 300)
        self.assertEqual(result['R0C0']['h'], 300)
        self.assertEqual(result['R1C1']['x'], 300)
        self.assertEqual(result['R1C1']['y'], 300)
        self.assertEqual(result['R2C2']['x'], 600)
        self.assertEqual(result['R2C2']['y'], 600)

    def test_uneven_split(self):
        """Left=25%, Right=75% horizontal split."""
        gen = _make_generator()
        hierarchy = {
            'id': '1', 'name': '', 'zone_type': '', 'orientation': 'horz',
            'position': {'x': 0, 'y': 0, 'w': 100000, 'h': 100000},
            'is_floating': False, 'is_fixed': False,
            'children': [
                {'id': '2', 'name': 'Narrow', 'zone_type': 'worksheet', 'orientation': '',
                 'position': {'x': 0, 'y': 0, 'w': 25000, 'h': 100000},
                 'is_floating': False, 'is_fixed': False, 'children': []},
                {'id': '3', 'name': 'Wide', 'zone_type': 'worksheet', 'orientation': '',
                 'position': {'x': 25000, 'y': 0, 'w': 75000, 'h': 100000},
                 'is_floating': False, 'is_fixed': False, 'children': []},
            ],
        }
        result = gen._build_zone_layout_map(hierarchy, 1200, 600)
        self.assertEqual(result['Narrow']['w'], 300)
        self.assertEqual(result['Wide']['w'], 900)
        self.assertEqual(result['Wide']['x'], 300)

    def test_minimum_size_enforcement(self):
        """Very small zone gets clamped to MIN_VISUAL_WIDTH/HEIGHT."""
        gen = _make_generator()
        hierarchy = {
            'id': '1', 'name': 'Tiny', 'zone_type': 'worksheet', 'orientation': '',
            'position': {'x': 0, 'y': 0, 'w': 100000, 'h': 100000},
            'is_floating': False, 'is_fixed': False, 'children': [],
        }
        # Page is extremely small
        result = gen._build_zone_layout_map(hierarchy, 10, 10)
        self.assertGreaterEqual(result['Tiny']['w'], gen.MIN_VISUAL_WIDTH)
        self.assertGreaterEqual(result['Tiny']['h'], gen.MIN_VISUAL_HEIGHT)


# ── Floating vs Tiled Tests ────────────────────────────────────────

class TestFloatingVsTiled(unittest.TestCase):
    """Floating zones get absolute-scaled positions; tiled use proportional subdivision."""

    def test_floating_absolute_position(self):
        gen = _make_generator()
        hierarchy = {
            'id': '1', 'name': '', 'zone_type': '', 'orientation': 'vert',
            'position': {'x': 0, 'y': 0, 'w': 100000, 'h': 100000},
            'is_floating': False, 'is_fixed': False,
            'children': [
                {'id': '2', 'name': 'Tiled', 'zone_type': 'worksheet', 'orientation': '',
                 'position': {'x': 0, 'y': 0, 'w': 100000, 'h': 100000},
                 'is_floating': False, 'is_fixed': False, 'children': []},
                {'id': '3', 'name': 'Floating', 'zone_type': 'worksheet', 'orientation': '',
                 'position': {'x': 20000, 'y': 10000, 'w': 30000, 'h': 20000},
                 'is_floating': True, 'is_fixed': False, 'children': []},
            ],
        }
        result = gen._build_zone_layout_map(hierarchy, 1000, 500)
        # Tiled child gets full space
        self.assertEqual(result['Tiled']['w'], 1000)
        self.assertEqual(result['Tiled']['h'], 500)
        # Floating child: scaled from 100000 → 1000px and 100000 → 500px
        self.assertEqual(result['Floating']['x'], 200)
        self.assertEqual(result['Floating']['y'], 50)
        self.assertEqual(result['Floating']['w'], 300)
        self.assertEqual(result['Floating']['h'], 100)

    def test_mixed_floating_tiled(self):
        gen = _make_generator()
        hierarchy = {
            'id': '1', 'name': '', 'zone_type': '', 'orientation': 'horz',
            'position': {'x': 0, 'y': 0, 'w': 100000, 'h': 100000},
            'is_floating': False, 'is_fixed': False,
            'children': [
                {'id': '2', 'name': 'Left', 'zone_type': 'worksheet', 'orientation': '',
                 'position': {'x': 0, 'y': 0, 'w': 50000, 'h': 100000},
                 'is_floating': False, 'is_fixed': False, 'children': []},
                {'id': '3', 'name': 'Right', 'zone_type': 'worksheet', 'orientation': '',
                 'position': {'x': 50000, 'y': 0, 'w': 50000, 'h': 100000},
                 'is_floating': False, 'is_fixed': False, 'children': []},
                {'id': '4', 'name': 'Overlay', 'zone_type': 'text', 'orientation': '',
                 'position': {'x': 25000, 'y': 25000, 'w': 50000, 'h': 50000},
                 'is_floating': True, 'is_fixed': False, 'children': []},
            ],
        }
        result = gen._build_zone_layout_map(hierarchy, 800, 400)
        # Tiled: two equal halves
        self.assertEqual(result['Left']['w'], 400)
        self.assertEqual(result['Right']['w'], 400)
        # Floating: absolute scaled
        self.assertIn('Overlay', result)
        self.assertAlmostEqual(result['Overlay']['x'], 200, delta=5)


# ── Resolve Visual Position Tests ──────────────────────────────────

class TestResolveVisualPosition(unittest.TestCase):
    """Tests for _resolve_visual_position() grid lookup + fallback."""

    def test_found_in_layout_map(self):
        gen = _make_generator()
        layout_map = {'MyChart': {'x': 100, 'y': 50, 'w': 400, 'h': 300}}
        obj = {'worksheetName': 'MyChart', 'position': {'x': 99999, 'y': 99999, 'w': 1, 'h': 1}}
        pos = gen._resolve_visual_position(obj, layout_map, 0.01, 0.01, 1, 1280, 720)
        self.assertEqual(pos['x'], 100)
        self.assertEqual(pos['y'], 50)
        self.assertEqual(pos['width'], 400)
        self.assertEqual(pos['height'], 300)

    def test_fallback_proportional(self):
        gen = _make_generator()
        obj = {'worksheetName': 'Unknown', 'position': {'x': 100, 'y': 200, 'w': 300, 'h': 400}}
        pos = gen._resolve_visual_position(obj, {}, 2.0, 1.5, 0, 1280, 720)
        self.assertEqual(pos['x'], 200)
        self.assertEqual(pos['y'], 300)

    def test_empty_layout_map(self):
        gen = _make_generator()
        obj = {'worksheetName': 'Sheet', 'position': {'x': 10, 'y': 20, 'w': 100, 'h': 200}}
        pos = gen._resolve_visual_position(obj, None, 1.0, 1.0, 0, 1280, 720)
        self.assertEqual(pos['x'], 10)

    def test_clamp_to_page_bounds(self):
        gen = _make_generator()
        layout_map = {'Wide': {'x': 1200, 'y': 600, 'w': 500, 'h': 500}}
        obj = {'worksheetName': 'Wide', 'position': {'x': 0, 'y': 0, 'w': 0, 'h': 0}}
        pos = gen._resolve_visual_position(obj, layout_map, 1.0, 1.0, 0, 1280, 720)
        # Width should be clamped: 1280 - 1200 = 80 (>MIN_VISUAL_WIDTH)
        self.assertEqual(pos['width'], 80)
        # Height should be clamped: 720 - 600 = 120
        self.assertEqual(pos['height'], 120)


# ── Padding Propagation Tests ──────────────────────────────────────

class TestPaddingPropagation(unittest.TestCase):
    """Tests for _apply_padding_to_visual() and _find_zone_padding()."""

    def test_find_padding_leaf(self):
        gen = _make_generator()
        hierarchy = {
            'id': '1', 'name': 'Padded', 'zone_type': 'worksheet',
            'orientation': '', 'position': {'x': 0, 'y': 0, 'w': 100, 'h': 100},
            'is_floating': False, 'is_fixed': False, 'children': [],
            'padding': {'top': 10, 'left': 5},
        }
        result = gen._find_zone_padding(hierarchy, 'Padded')
        self.assertEqual(result, {'top': 10, 'left': 5})

    def test_find_padding_nested(self):
        gen = _make_generator()
        hierarchy = {
            'id': '1', 'name': '', 'zone_type': '', 'orientation': 'vert',
            'position': {'x': 0, 'y': 0, 'w': 100, 'h': 100},
            'is_floating': False, 'is_fixed': False,
            'children': [
                {'id': '2', 'name': 'Deep', 'zone_type': 'worksheet', 'orientation': '',
                 'position': {'x': 0, 'y': 0, 'w': 100, 'h': 100},
                 'is_floating': False, 'is_fixed': False, 'children': [],
                 'padding': {'bottom': 12}},
            ],
        }
        result = gen._find_zone_padding(hierarchy, 'Deep')
        self.assertEqual(result, {'bottom': 12})

    def test_find_padding_not_found(self):
        gen = _make_generator()
        hierarchy = {
            'id': '1', 'name': 'NoPad', 'zone_type': 'worksheet',
            'orientation': '', 'position': {'x': 0, 'y': 0, 'w': 100, 'h': 100},
            'is_floating': False, 'is_fixed': False, 'children': [],
        }
        result = gen._find_zone_padding(hierarchy, 'NoPad')
        self.assertIsNone(result)

    def test_apply_padding_to_visual(self):
        gen = _make_generator()
        hierarchy = {
            'id': '1', 'name': 'PadVis', 'zone_type': 'worksheet',
            'orientation': '', 'position': {'x': 0, 'y': 0, 'w': 100, 'h': 100},
            'is_floating': False, 'is_fixed': False, 'children': [],
            'padding': {'top': 8, 'right': 6},
        }
        visual_json = {"visual": {"visualType": "clusteredBarChart"}}
        gen._apply_padding_to_visual(visual_json, hierarchy, 'PadVis')
        props = visual_json['visual']['objects']['general'][0]['properties']
        self.assertEqual(props['paddingTop'], 8)
        self.assertEqual(props['paddingRight'], 6)

    def test_apply_padding_no_hierarchy(self):
        gen = _make_generator()
        visual_json = {"visual": {"visualType": "lineChart"}}
        gen._apply_padding_to_visual(visual_json, None, 'Sheet1')
        # Should not crash, no objects added
        self.assertNotIn('objects', visual_json.get('visual', {}))

    def test_apply_padding_no_match(self):
        gen = _make_generator()
        hierarchy = {
            'id': '1', 'name': 'Other', 'zone_type': 'worksheet',
            'orientation': '', 'position': {'x': 0, 'y': 0, 'w': 100, 'h': 100},
            'is_floating': False, 'is_fixed': False, 'children': [],
        }
        visual_json = {"visual": {"visualType": "lineChart"}}
        gen._apply_padding_to_visual(visual_json, hierarchy, 'Sheet1')
        self.assertNotIn('objects', visual_json.get('visual', {}))


# ── Responsive Breakpoints Tests ───────────────────────────────────

class TestResponsiveBreakpoints(unittest.TestCase):
    """Tests for mobileState generation from device_layouts."""

    def _create_page_json(self, dashboard):
        """Run _create_dashboard_pages() and return the page.json dict."""
        gen = _make_generator()
        tmpdir = tempfile.mkdtemp()
        try:
            pages_dir = os.path.join(tmpdir, 'pages')
            os.makedirs(pages_dir, exist_ok=True)
            gen._find_worksheet = lambda ws_list, name: None
            gen._create_visual_filters = lambda filters: []
            gen._field_map = {}
            gen._create_dashboard_pages(pages_dir, [dashboard], [], {'calculations': []}, {})
            # Read back page.json
            page_dir = os.path.join(pages_dir, 'ReportSection')
            page_json_path = os.path.join(page_dir, 'page.json')
            with open(page_json_path, 'r') as f:
                return json.load(f)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_no_device_layouts(self):
        db = {
            'name': 'Test', 'objects': [], 'filters': [],
            'size': {'width': 1280, 'height': 720},
        }
        page = self._create_page_json(db)
        self.assertNotIn('mobileState', page)

    def test_phone_layout_generates_mobile_state(self):
        db = {
            'name': 'Test', 'objects': [], 'filters': [],
            'size': {'width': 1280, 'height': 720},
            'device_layouts': [
                {
                    'device_type': 'phone',
                    'zones': [
                        {'name': 'Sales', 'position': {'x': 0, 'y': 0, 'w': 500, 'h': 300}},
                        {'name': 'Profit', 'position': {'x': 0, 'y': 300, 'w': 500, 'h': 300}},
                    ],
                    'auto_generated': False,
                }
            ],
        }
        page = self._create_page_json(db)
        self.assertIn('mobileState', page)
        self.assertEqual(len(page['mobileState']['visuals']), 2)
        self.assertEqual(page['mobileState']['visuals'][0]['name'], 'Sales')

    def test_tablet_only_no_mobile_state(self):
        db = {
            'name': 'Test', 'objects': [], 'filters': [],
            'size': {'width': 1280, 'height': 720},
            'device_layouts': [
                {
                    'device_type': 'tablet',
                    'zones': [{'name': 'Data', 'position': {'x': 0, 'y': 0, 'w': 500, 'h': 500}}],
                    'auto_generated': False,
                }
            ],
        }
        page = self._create_page_json(db)
        self.assertNotIn('mobileState', page)


# ── Integration: Dashboard Pages with Grid Layout ──────────────────

class TestDashboardPagesGridLayout(unittest.TestCase):
    """Integration tests for _create_dashboard_pages() with zone_hierarchy."""

    def test_grid_layout_used_when_zone_hierarchy_present(self):
        """When zone_hierarchy is present, visuals should use grid-snapped positions."""
        gen = _make_generator()
        gen._field_map = {}
        gen._find_worksheet = lambda ws_list, name: {
            'name': name, 'fields': [], 'filters': [], 'mark_encoding': {},
        }

        tmpdir = tempfile.mkdtemp()
        try:
            pages_dir = os.path.join(tmpdir, 'pages')
            os.makedirs(pages_dir, exist_ok=True)

            db = {
                'name': 'GridTest',
                'size': {'width': 1000, 'height': 500},
                'filters': [],
                'zone_hierarchy': {
                    'id': '1', 'name': '', 'zone_type': '', 'orientation': 'horz',
                    'position': {'x': 0, 'y': 0, 'w': 100000, 'h': 100000},
                    'is_floating': False, 'is_fixed': False,
                    'children': [
                        {'id': '2', 'name': 'LeftChart', 'zone_type': 'worksheet',
                         'orientation': '',
                         'position': {'x': 0, 'y': 0, 'w': 50000, 'h': 100000},
                         'is_floating': False, 'is_fixed': False, 'children': []},
                        {'id': '3', 'name': 'RightChart', 'zone_type': 'worksheet',
                         'orientation': '',
                         'position': {'x': 50000, 'y': 0, 'w': 50000, 'h': 100000},
                         'is_floating': False, 'is_fixed': False, 'children': []},
                    ],
                },
                'objects': [
                    {'type': 'worksheetReference', 'worksheetName': 'LeftChart',
                     'position': {'x': 0, 'y': 0, 'w': 50000, 'h': 100000}},
                    {'type': 'worksheetReference', 'worksheetName': 'RightChart',
                     'position': {'x': 50000, 'y': 0, 'w': 50000, 'h': 100000}},
                ],
            }

            gen._create_dashboard_pages(
                pages_dir, [db],
                [{'name': 'LeftChart', 'fields': [], 'filters': [], 'mark_encoding': {}},
                 {'name': 'RightChart', 'fields': [], 'filters': [], 'mark_encoding': {}}],
                {'calculations': [], 'actions': []},
                {},
            )

            # Read visual.json files and verify positions
            visuals_dir = os.path.join(pages_dir, 'ReportSection', 'visuals')
            visual_dirs = os.listdir(visuals_dir)
            self.assertEqual(len(visual_dirs), 2)

            positions = []
            for vd in sorted(visual_dirs):
                with open(os.path.join(visuals_dir, vd, 'visual.json'), 'r') as f:
                    vj = json.load(f)
                    positions.append(vj.get('position', {}))

            # One at x=0 w=500, one at x=500 w=500
            xs = sorted([p['x'] for p in positions])
            ws = sorted([p['width'] for p in positions])
            self.assertEqual(xs, [0, 500])
            self.assertEqual(ws, [500, 500])
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_fallback_without_zone_hierarchy(self):
        """Without zone_hierarchy, old proportional scaling is used."""
        gen = _make_generator()
        gen._field_map = {}
        gen._find_worksheet = lambda ws_list, name: {
            'name': name, 'fields': [], 'filters': [], 'mark_encoding': {},
        }

        tmpdir = tempfile.mkdtemp()
        try:
            pages_dir = os.path.join(tmpdir, 'pages')
            os.makedirs(pages_dir, exist_ok=True)

            db = {
                'name': 'NoGrid',
                'size': {'width': 1000, 'height': 500},
                'filters': [],
                'objects': [
                    {'type': 'worksheetReference', 'worksheetName': 'Sheet1',
                     'position': {'x': 0, 'y': 0, 'w': 100, 'h': 100}},
                ],
            }

            gen._create_dashboard_pages(
                pages_dir, [db],
                [{'name': 'Sheet1', 'fields': [], 'filters': [], 'mark_encoding': {}}],
                {'calculations': [], 'actions': []},
                {},
            )

            visuals_dir = os.path.join(pages_dir, 'ReportSection', 'visuals')
            visual_dirs = os.listdir(visuals_dir)
            self.assertEqual(len(visual_dirs), 1)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ── NBA Real-World Layout Validation ───────────────────────────────

class TestNBALayoutValidation(unittest.TestCase):
    """Validate grid layout with NBA-like dashboard structure."""

    def test_nba_style_layout(self):
        """NBA dashboard: vert root → (horz header row, body worksheets)."""
        gen = _make_generator()
        hierarchy = {
            'id': '4', 'name': '', 'zone_type': 'layout-basic', 'orientation': 'vert',
            'position': {'x': 0, 'y': 0, 'w': 100000, 'h': 100000},
            'is_floating': False, 'is_fixed': False,
            'children': [
                # Header row: 10% height, two items side by side
                {'id': '5', 'name': '', 'zone_type': '', 'orientation': 'horz',
                 'position': {'x': 0, 'y': 0, 'w': 100000, 'h': 10000},
                 'is_floating': False, 'is_fixed': False,
                 'children': [
                     {'id': '6', 'name': 'Logo', 'zone_type': 'bitmap', 'orientation': '',
                      'position': {'x': 0, 'y': 0, 'w': 20000, 'h': 10000},
                      'is_floating': False, 'is_fixed': False, 'children': []},
                     {'id': '7', 'name': 'Title', 'zone_type': 'text', 'orientation': '',
                      'position': {'x': 20000, 'y': 0, 'w': 80000, 'h': 10000},
                      'is_floating': False, 'is_fixed': False, 'children': []},
                 ]},
                # Main chart: 60% height
                {'id': '21', 'name': 'Rebounds per Game', 'zone_type': 'worksheet',
                 'orientation': '',
                 'position': {'x': 0, 'y': 10000, 'w': 100000, 'h': 60000},
                 'is_floating': False, 'is_fixed': False, 'children': []},
                # Bottom row: 30% height
                {'id': '25', 'name': 'Player Stats', 'zone_type': 'worksheet',
                 'orientation': '',
                 'position': {'x': 0, 'y': 70000, 'w': 100000, 'h': 30000},
                 'is_floating': False, 'is_fixed': False, 'children': []},
            ],
        }
        result = gen._build_zone_layout_map(hierarchy, 1000, 1200)

        # Header row: 10% of 1200 = 120px
        # Logo: 20% of 1000 = 200px wide, 120px tall
        self.assertEqual(result['Logo']['w'], 200)
        self.assertEqual(result['Logo']['h'], 120)
        self.assertEqual(result['Logo']['x'], 0)
        self.assertEqual(result['Logo']['y'], 0)
        # Title: 80% of 1000 = 800px wide
        self.assertEqual(result['Title']['w'], 800)
        self.assertEqual(result['Title']['x'], 200)
        # Main chart: full width, 60% height = 720px, y at 120
        self.assertEqual(result['Rebounds per Game']['x'], 0)
        self.assertEqual(result['Rebounds per Game']['y'], 120)
        self.assertEqual(result['Rebounds per Game']['w'], 1000)
        self.assertEqual(result['Rebounds per Game']['h'], 720)
        # Bottom row: full width, 30% height = 360px, y at 840
        self.assertEqual(result['Player Stats']['x'], 0)
        self.assertEqual(result['Player Stats']['y'], 840)
        self.assertEqual(result['Player Stats']['w'], 1000)
        self.assertEqual(result['Player Stats']['h'], 360)


if __name__ == '__main__':
    unittest.main()
