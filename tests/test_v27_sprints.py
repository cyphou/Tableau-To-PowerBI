"""Tests for Sprint 101–106 (v27.0.0): Recursive LOD, Window depth,
Marketplace, DAX Recipes, Model Templates, Geo Passthrough."""

import json
import os
import sys
import tempfile
import unittest

# Ensure project root is on sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tableau_export.dax_converter import convert_tableau_formula_to_dax


# ════════════════════════════════════════════════════════════════════
# Sprint 101 — Recursive LOD Parser
# ════════════════════════════════════════════════════════════════════

class TestRecursiveLOD(unittest.TestCase):
    """Test the recursive descent LOD parser."""

    def _convert(self, formula, table='Sales', ctm=None):
        return convert_tableau_formula_to_dax(
            formula, table_name=table, column_table_map=ctm or {}
        )

    # -- Basic LOD (depth 1) --

    def test_fixed_basic(self):
        result = self._convert('{FIXED [Region] : SUM([Sales])}',
                               ctm={'Region': 'Sales', 'Sales': 'Sales'})
        self.assertIn('CALCULATE', result)
        self.assertIn('ALLEXCEPT', result)
        self.assertIn('[Region]', result)

    def test_include_basic(self):
        result = self._convert('{INCLUDE [State] : AVG([Profit])}')
        self.assertIn('CALCULATE', result)

    def test_exclude_basic(self):
        result = self._convert('{EXCLUDE [City] : COUNT([Order ID])}',
                               ctm={'City': 'Sales'})
        self.assertIn('REMOVEFILTERS', result)

    def test_fixed_no_dims(self):
        result = self._convert('{FIXED : SUM([Revenue])}')
        self.assertIn("ALL('Sales')", result)

    # -- Nested LOD (depth 2) --

    def test_nested_fixed_include(self):
        """FIXED wrapping INCLUDE — depth 2."""
        formula = '{FIXED [Region] : {INCLUDE [State] : SUM([Sales])}}'
        result = self._convert(formula,
                               ctm={'Region': 'Sales', 'State': 'Sales', 'Sales': 'Sales'})
        # Inner INCLUDE should be CALCULATE(…), outer FIXED should wrap it
        self.assertEqual(result.count('CALCULATE'), 2)
        self.assertIn('ALLEXCEPT', result)

    def test_nested_fixed_exclude(self):
        """FIXED wrapping EXCLUDE — depth 2."""
        formula = '{FIXED [Region] : {EXCLUDE [City] : AVG([Profit])}}'
        result = self._convert(formula,
                               ctm={'Region': 'Sales', 'City': 'Sales', 'Profit': 'Sales'})
        self.assertEqual(result.count('CALCULATE'), 2)
        self.assertIn('REMOVEFILTERS', result)

    # -- Deeply nested LOD (depth 3+) --

    def test_triple_nested_lod(self):
        """Three-level nesting: FIXED → INCLUDE → EXCLUDE."""
        formula = '{FIXED [Region] : {INCLUDE [State] : {EXCLUDE [City] : SUM([Sales])}}}'
        result = self._convert(formula,
                               ctm={'Region': 'Sales', 'State': 'Sales',
                                    'City': 'Sales', 'Sales': 'Sales'})
        # Three LOD levels = three CALCULATE calls
        self.assertEqual(result.count('CALCULATE'), 3)

    def test_quadruple_nested_lod(self):
        """Four-level nesting."""
        formula = (
            '{FIXED [A] : {FIXED [B] : {INCLUDE [C] : {EXCLUDE [D] : SUM([X])}}}}'
        )
        result = self._convert(formula,
                               ctm={'A': 'T', 'B': 'T', 'C': 'T', 'D': 'T', 'X': 'T'})
        self.assertEqual(result.count('CALCULATE'), 4)

    def test_sibling_lods(self):
        """Two LODs at the same level (siblings, not nested)."""
        formula = '{FIXED [Region] : SUM([Sales])} + {FIXED [State] : AVG([Profit])}'
        result = self._convert(formula,
                               ctm={'Region': 'Sales', 'State': 'Sales',
                                    'Sales': 'Sales', 'Profit': 'Sales'})
        self.assertEqual(result.count('CALCULATE'), 2)
        self.assertIn('+', result)

    def test_deeply_nested_depth_5(self):
        """Five-level nesting — tests recursion well beyond old 50-iteration limit."""
        formula = '{FIXED [A] : {FIXED [B] : {FIXED [C] : {FIXED [D] : {FIXED [E] : SUM([X])}}}}}'
        result = self._convert(formula,
                               ctm={'A': 'T', 'B': 'T', 'C': 'T', 'D': 'T', 'E': 'T', 'X': 'T'})
        self.assertEqual(result.count('CALCULATE'), 5)

    def test_lod_with_complex_agg(self):
        """LOD where the aggregate expression is itself complex."""
        formula = '{FIXED [Region] : SUM(IF [Status] = "Active" THEN [Revenue] ELSE 0 END)}'
        result = self._convert(formula,
                               ctm={'Region': 'Sales', 'Revenue': 'Sales'})
        self.assertIn('CALCULATE', result)

    def test_lod_multi_table_dims(self):
        """LOD with dimensions from different tables → REMOVEFILTERS per column."""
        formula = '{FIXED [Region], [Category] : SUM([Sales])}'
        result = self._convert(formula,
                               ctm={'Region': 'Geo', 'Category': 'Product', 'Sales': 'Sales'})
        self.assertIn('REMOVEFILTERS', result)


# ════════════════════════════════════════════════════════════════════
# Sprint 102 — Window Function Depth
# ════════════════════════════════════════════════════════════════════

class TestWindowFunctionDepth(unittest.TestCase):
    """Test multi-level PARTITIONBY, ORDERBY, MATCHBY support."""

    def _convert(self, formula, table='Sales', compute_using=None,
                 partition_fields=None, ctm=None):
        return convert_tableau_formula_to_dax(
            formula, table_name=table, compute_using=compute_using,
            partition_fields=partition_fields, column_table_map=ctm or {}
        )

    def test_window_sum_basic(self):
        result = self._convert('WINDOW_SUM(SUM([Sales]))')
        self.assertIn('CALCULATE', result)
        self.assertIn("ALL('Sales')", result)

    def test_window_sum_with_compute_using(self):
        result = self._convert('WINDOW_SUM(SUM([Sales]))',
                               compute_using=['Region'])
        self.assertIn('ALLEXCEPT', result)
        self.assertIn('[Region]', result)

    def test_window_with_frame_boundaries(self):
        result = self._convert('WINDOW_SUM(SUM([Sales]), -2, 0)',
                               compute_using=['Date'])
        self.assertIn('WINDOW(-2, REL, 0, REL', result)

    def test_window_with_explicit_partition_by(self):
        """Explicit partition_fields with partition_by list."""
        result = self._convert(
            'WINDOW_SUM(SUM([Sales]), -1, 1)',
            compute_using=['Date', 'Region'],
            partition_fields={'partition_by': ['Category']},
            ctm={'Date': 'Sales', 'Region': 'Sales', 'Category': 'Sales'},
        )
        self.assertIn('PARTITIONBY', result)
        self.assertIn('[Category]', result)

    def test_window_with_multi_column_orderby(self):
        """Multi-column ORDERBY with sort directions."""
        result = self._convert(
            'WINDOW_SUM(SUM([Sales]), -1, 1)',
            partition_fields={
                'order_by': [('Date', 'ASC'), ('Region', 'DESC')],
            },
            ctm={'Date': 'Sales', 'Region': 'Sales'},
        )
        self.assertIn('ORDERBY(', result)
        self.assertIn('ASC', result)
        self.assertIn('DESC', result)

    def test_window_with_matchby(self):
        """MATCHBY clause for grain disambiguation."""
        result = self._convert(
            'WINDOW_SUM(SUM([Sales]), -1, 1)',
            compute_using=['Date'],
            partition_fields={
                'match_by': ['OrderID'],
            },
            ctm={'Date': 'Sales', 'OrderID': 'Sales'},
        )
        self.assertIn('MATCHBY(', result)
        self.assertIn('[OrderID]', result)

    def test_window_avg_with_all_clauses(self):
        """Full spec: explicit order_by + partition_by + match_by."""
        result = self._convert(
            'WINDOW_AVG(AVG([Score]), -3, 3)',
            compute_using=['Employee'],
            partition_fields={
                'order_by': [('Date', 'ASC')],
                'partition_by': ['Department'],
                'match_by': ['EmployeeID'],
            },
            ctm={'Employee': 'HR', 'Date': 'HR', 'Department': 'HR',
                 'EmployeeID': 'HR', 'Score': 'HR'},
        )
        self.assertIn('ORDERBY(', result)
        self.assertIn('PARTITIONBY(', result)
        self.assertIn('MATCHBY(', result)
        self.assertIn('WINDOW(-3, REL, 3, REL', result)

    def test_window_no_frame_multi_partition(self):
        """No frame boundaries but multiple compute_using dims."""
        result = self._convert(
            'WINDOW_SUM(SUM([Sales]))',
            compute_using=['Region', 'Category'],
            ctm={'Region': 'Sales', 'Category': 'Sales'},
        )
        self.assertIn('ALLEXCEPT', result)
        self.assertIn('[Region]', result)
        self.assertIn('[Category]', result)

    def test_build_window_clauses_import(self):
        """Verify _build_window_clauses function exists."""
        from tableau_export.dax_converter import _build_window_clauses
        order, part, match, filt = _build_window_clauses(
            ['Date'], 'Sales', {'Date': 'Sales'}, None
        )
        self.assertIn('ORDERBY', order)
        self.assertEqual(part, '')
        self.assertEqual(match, '')
        self.assertIn('ALLEXCEPT', filt)


# ════════════════════════════════════════════════════════════════════
# Sprint 103 — Migration Marketplace
# ════════════════════════════════════════════════════════════════════

class TestMarketplace(unittest.TestCase):
    """Test PatternRegistry and marketplace functionality."""

    def test_pattern_metadata(self):
        from powerbi_import.marketplace import PatternMetadata
        meta = PatternMetadata({
            'name': 'test_pattern',
            'version': '1.2.0',
            'author': 'Test',
            'tags': ['finance', 'revenue'],
            'category': 'dax_recipe',
        })
        self.assertEqual(meta.name, 'test_pattern')
        self.assertEqual(meta.version, '1.2.0')
        self.assertTrue(meta.matches(tags=['finance']))
        self.assertFalse(meta.matches(tags=['healthcare']))
        self.assertTrue(meta.matches(category='dax_recipe'))
        self.assertFalse(meta.matches(category='visual_mapping'))

    def test_pattern_metadata_name_pattern(self):
        from powerbi_import.marketplace import PatternMetadata
        meta = PatternMetadata({'name': 'revenue_ytd', 'tags': []})
        self.assertTrue(meta.matches(name_pattern='revenue'))
        self.assertFalse(meta.matches(name_pattern='^xyz'))

    def test_registry_register_and_get(self):
        from powerbi_import.marketplace import PatternRegistry
        reg = PatternRegistry()
        reg.register({
            'metadata': {'name': 'my_recipe', 'version': '1.0.0', 'tags': ['test']},
            'payload': {'inject': {'name': 'M', 'dax': 'SUM(X)'}},
        })
        self.assertEqual(reg.count, 1)
        pat = reg.get('my_recipe')
        self.assertIsNotNone(pat)
        self.assertEqual(pat.name, 'my_recipe')

    def test_registry_version_pinning(self):
        from powerbi_import.marketplace import PatternRegistry
        reg = PatternRegistry()
        reg.register({
            'metadata': {'name': 'r1', 'version': '1.0.0', 'tags': []},
            'payload': {'inject': {'name': 'A', 'dax': 'V1'}},
        })
        reg.register({
            'metadata': {'name': 'r1', 'version': '2.0.0', 'tags': []},
            'payload': {'inject': {'name': 'A', 'dax': 'V2'}},
        })
        latest = reg.get('r1')
        self.assertEqual(latest.version, '2.0.0')
        pinned = reg.get('r1', version='1.0.0')
        self.assertEqual(pinned.version, '1.0.0')

    def test_registry_search(self):
        from powerbi_import.marketplace import PatternRegistry
        reg = PatternRegistry()
        reg.register({
            'metadata': {'name': 'fin1', 'version': '1.0.0', 'tags': ['finance'], 'category': 'dax_recipe'},
            'payload': {},
        })
        reg.register({
            'metadata': {'name': 'vis1', 'version': '1.0.0', 'tags': ['maps'], 'category': 'visual_mapping'},
            'payload': {},
        })
        fin = reg.search(tags=['finance'])
        self.assertEqual(len(fin), 1)
        vis = reg.search(category='visual_mapping')
        self.assertEqual(len(vis), 1)

    def test_load_from_directory(self):
        from powerbi_import.marketplace import PatternRegistry
        marketplace_dir = os.path.join(ROOT, 'examples', 'marketplace')
        if not os.path.isdir(marketplace_dir):
            self.skipTest("examples/marketplace not found")
        reg = PatternRegistry(marketplace_dir)
        count = reg.load()
        self.assertGreater(count, 0)
        self.assertGreater(reg.count, 0)

    def test_apply_dax_recipes_inject(self):
        from powerbi_import.marketplace import PatternRegistry
        reg = PatternRegistry()
        reg.register({
            'metadata': {'name': 'inject_test', 'version': '1.0.0',
                         'tags': ['test'], 'category': 'dax_recipe'},
            'payload': {'inject': {'name': 'New Measure', 'dax': 'SUM(X)'}},
        })
        measures = {'Existing': 'COUNT(Y)'}
        changes = reg.apply_dax_recipes(measures, tags=['test'])
        self.assertIn('New Measure', measures)
        self.assertEqual(changes['New Measure']['action'], 'injected')

    def test_apply_dax_recipes_replace(self):
        from powerbi_import.marketplace import PatternRegistry
        reg = PatternRegistry()
        reg.register({
            'metadata': {'name': 'replace_test', 'version': '1.0.0',
                         'tags': ['test'], 'category': 'dax_recipe'},
            'payload': {'match': r'OLD_FUNC\(', 'replacement': 'NEW_FUNC('},
        })
        measures = {'M1': 'OLD_FUNC(X)'}
        changes = reg.apply_dax_recipes(measures, tags=['test'])
        self.assertEqual(measures['M1'], 'NEW_FUNC(X)')
        self.assertEqual(changes['M1']['action'], 'replaced')

    def test_apply_visual_overrides(self):
        from powerbi_import.marketplace import PatternRegistry
        reg = PatternRegistry()
        reg.register({
            'metadata': {'name': 'map_override', 'version': '1.0.0',
                         'tags': ['maps'], 'category': 'visual_mapping'},
            'payload': {'overrides': {'treemap': 'decompositionTree'}},
        })
        vmap = {'treemap': 'treemap', 'bar': 'clusteredBarChart'}
        count = reg.apply_visual_overrides(vmap)
        self.assertEqual(count, 1)
        self.assertEqual(vmap['treemap'], 'decompositionTree')

    def test_export_catalogue(self):
        from powerbi_import.marketplace import PatternRegistry
        reg = PatternRegistry()
        reg.register({
            'metadata': {'name': 'exp1', 'version': '1.0.0', 'tags': []},
            'payload': {'data': 123},
        })
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'catalogue.json')
            count = reg.export(path)
            self.assertEqual(count, 1)
            with open(path) as f:
                data = json.load(f)
            self.assertEqual(len(data), 1)

    def test_to_dict(self):
        from powerbi_import.marketplace import PatternRegistry
        reg = PatternRegistry()
        reg.register({
            'metadata': {'name': 'x', 'version': '1.0.0', 'tags': [], 'category': 'dax_recipe'},
            'payload': {},
        })
        d = reg.to_dict()
        self.assertEqual(d['pattern_count'], 1)
        self.assertIn('dax_recipe', d['categories'])


# ════════════════════════════════════════════════════════════════════
# Sprint 104 — DAX Recipe Overrides
# ════════════════════════════════════════════════════════════════════

class TestDAXRecipes(unittest.TestCase):
    """Test industry-specific DAX recipe library."""

    def test_list_industries(self):
        from powerbi_import.dax_recipes import list_industries
        industries = list_industries()
        self.assertIn('healthcare', industries)
        self.assertIn('finance', industries)
        self.assertIn('retail', industries)

    def test_get_healthcare_recipes(self):
        from powerbi_import.dax_recipes import get_industry_recipes
        recipes = get_industry_recipes('healthcare')
        self.assertGreater(len(recipes), 0)
        names = [r['name'] for r in recipes]
        self.assertIn('Average Length of Stay', names)
        self.assertIn('Readmission Rate', names)

    def test_get_finance_recipes(self):
        from powerbi_import.dax_recipes import get_industry_recipes
        recipes = get_industry_recipes('finance')
        self.assertGreater(len(recipes), 0)
        names = [r['name'] for r in recipes]
        self.assertIn('Net Revenue', names)
        self.assertIn('Gross Margin %', names)

    def test_get_retail_recipes(self):
        from powerbi_import.dax_recipes import get_industry_recipes
        recipes = get_industry_recipes('retail')
        self.assertGreater(len(recipes), 0)
        names = [r['name'] for r in recipes]
        self.assertIn('Revenue Per Transaction', names)
        self.assertIn('Items Per Basket', names)

    def test_unknown_industry(self):
        from powerbi_import.dax_recipes import get_industry_recipes
        recipes = get_industry_recipes('aerospace')
        self.assertEqual(recipes, [])

    def test_apply_recipes_inject(self):
        from powerbi_import.dax_recipes import apply_recipes
        recipes = [{'name': 'Test KPI', 'dax': 'SUM(X)'}]
        measures = {}
        changes = apply_recipes(measures, recipes)
        self.assertIn('Test KPI', measures)
        self.assertEqual(changes['Test KPI']['action'], 'injected')

    def test_apply_recipes_no_overwrite(self):
        from powerbi_import.dax_recipes import apply_recipes
        recipes = [{'name': 'M1', 'dax': 'SUM(Y)'}]
        measures = {'M1': 'SUM(X)'}
        changes = apply_recipes(measures, recipes, overwrite=False)
        self.assertEqual(measures['M1'], 'SUM(X)')  # unchanged
        self.assertEqual(changes['M1']['action'], 'skipped')

    def test_apply_recipes_overwrite(self):
        from powerbi_import.dax_recipes import apply_recipes
        recipes = [{'name': 'M1', 'dax': 'SUM(Y)'}]
        measures = {'M1': 'SUM(X)'}
        changes = apply_recipes(measures, recipes, overwrite=True)
        self.assertEqual(measures['M1'], 'SUM(Y)')
        self.assertEqual(changes['M1']['action'], 'injected')

    def test_apply_recipes_replace_mode(self):
        from powerbi_import.dax_recipes import apply_recipes
        recipes = [{'name': 'cleanup', 'match': r'SUM\(', 'replacement': 'SUMX(T, '}]
        measures = {'M1': 'SUM([X])'}
        changes = apply_recipes(measures, recipes)
        self.assertIn('SUMX(T, ', measures['M1'])

    def test_get_all_recipes(self):
        from powerbi_import.dax_recipes import get_all_recipes
        all_r = get_all_recipes()
        self.assertGreater(len(all_r), 15)

    def test_recipes_to_marketplace_format(self):
        from powerbi_import.dax_recipes import recipes_to_marketplace_format
        patterns = recipes_to_marketplace_format('finance')
        self.assertGreater(len(patterns), 0)
        p = patterns[0]
        self.assertIn('metadata', p)
        self.assertIn('payload', p)
        self.assertEqual(p['metadata']['category'], 'dax_recipe')

    def test_recipe_dax_not_empty(self):
        """All recipes should have non-empty DAX."""
        from powerbi_import.dax_recipes import get_all_recipes
        for recipe in get_all_recipes():
            self.assertTrue(recipe.get('dax'), f"Recipe '{recipe.get('name')}' has empty DAX")
            self.assertTrue(recipe.get('name'), "Recipe has no name")


# ════════════════════════════════════════════════════════════════════
# Sprint 105 — Industry Model Templates
# ════════════════════════════════════════════════════════════════════

class TestModelTemplates(unittest.TestCase):
    """Test industry model template system."""

    def test_list_templates(self):
        from powerbi_import.model_templates import list_templates
        templates = list_templates()
        self.assertIn('healthcare', templates)
        self.assertIn('finance', templates)
        self.assertIn('retail', templates)

    def test_get_healthcare_template(self):
        from powerbi_import.model_templates import get_template
        tpl = get_template('healthcare')
        self.assertIsNotNone(tpl)
        self.assertEqual(tpl['name'], 'Healthcare')
        table_names = [t['name'] for t in tpl['tables']]
        self.assertIn('Encounters', table_names)
        self.assertIn('Patients', table_names)

    def test_get_finance_template(self):
        from powerbi_import.model_templates import get_template
        tpl = get_template('finance')
        self.assertIsNotNone(tpl)
        table_names = [t['name'] for t in tpl['tables']]
        self.assertIn('Financials', table_names)
        self.assertIn('Accounts', table_names)

    def test_get_retail_template(self):
        from powerbi_import.model_templates import get_template
        tpl = get_template('retail')
        self.assertIsNotNone(tpl)
        table_names = [t['name'] for t in tpl['tables']]
        self.assertIn('Sales', table_names)
        self.assertIn('Products', table_names)

    def test_unknown_template(self):
        from powerbi_import.model_templates import get_template
        tpl = get_template('aerospace')
        self.assertIsNone(tpl)

    def test_template_has_relationships(self):
        from powerbi_import.model_templates import get_template
        for industry in ('healthcare', 'finance', 'retail'):
            tpl = get_template(industry)
            self.assertGreater(len(tpl['relationships']), 0,
                               f"{industry} template has no relationships")

    def test_template_has_measures(self):
        from powerbi_import.model_templates import get_template
        for industry in ('healthcare', 'finance', 'retail'):
            tpl = get_template(industry)
            self.assertGreater(len(tpl['measures']), 0,
                               f"{industry} template has no measures")

    def test_template_has_hierarchies(self):
        from powerbi_import.model_templates import get_template
        for industry in ('healthcare', 'finance', 'retail'):
            tpl = get_template(industry)
            self.assertGreater(len(tpl['hierarchies']), 0,
                               f"{industry} template has no hierarchies")

    def test_apply_template_new_tables(self):
        from powerbi_import.model_templates import get_template, apply_template
        tpl = get_template('retail')
        existing = [{'name': 'Sales', 'columns': [{'name': 'Revenue', 'dataType': 'double'}]}]
        result = apply_template(tpl, existing)
        self.assertGreater(result['stats']['new_tables'], 0)

    def test_apply_template_enrich_columns(self):
        from powerbi_import.model_templates import get_template, apply_template
        tpl = get_template('retail')
        existing = [{'name': 'Sales', 'columns': [{'name': 'Revenue', 'dataType': 'double'}]}]
        result = apply_template(tpl, existing)
        # Sales table should have additional columns from template
        sales = [t for t in result['tables'] if t['name'] == 'Sales'][0]
        col_names = [c['name'] for c in sales['columns']]
        self.assertIn('Revenue', col_names)  # original
        self.assertIn('Quantity', col_names)  # from template

    def test_apply_template_relationships(self):
        from powerbi_import.model_templates import get_template, apply_template
        tpl = get_template('healthcare')
        existing = [
            {'name': 'Encounters', 'columns': [{'name': 'EncounterID', 'dataType': 'string'}]},
            {'name': 'Patients', 'columns': [{'name': 'PatientID', 'dataType': 'string'}]},
        ]
        result = apply_template(tpl, existing)
        self.assertGreater(len(result['relationships']), 0)

    def test_apply_template_returns_measures(self):
        from powerbi_import.model_templates import get_template, apply_template
        tpl = get_template('finance')
        result = apply_template(tpl, [])
        self.assertGreater(len(result['measures']), 0)

    def test_template_deep_copy(self):
        """get_template should return a deep copy."""
        from powerbi_import.model_templates import get_template
        tpl1 = get_template('retail')
        tpl2 = get_template('retail')
        tpl1['tables'][0]['name'] = 'MODIFIED'
        self.assertNotEqual(tpl2['tables'][0]['name'], 'MODIFIED')


# ════════════════════════════════════════════════════════════════════
# Sprint 106 — Shapefile/GeoJSON Passthrough
# ════════════════════════════════════════════════════════════════════

class TestGeoPassthrough(unittest.TestCase):
    """Test geographic file extraction and shape map configuration."""

    def test_classify_geojson(self):
        from powerbi_import.geo_passthrough import _classify_format
        self.assertEqual(_classify_format('.geojson', 'regions.geojson'), 'geojson')

    def test_classify_topojson(self):
        from powerbi_import.geo_passthrough import _classify_format
        self.assertEqual(_classify_format('.topojson', 'world.topojson'), 'topojson')

    def test_classify_shapefile(self):
        from powerbi_import.geo_passthrough import _classify_format
        self.assertEqual(_classify_format('.shp', 'counties.shp'), 'shapefile')
        self.assertEqual(_classify_format('.dbf', 'counties.dbf'), 'shapefile')

    def test_classify_json_geo(self):
        from powerbi_import.geo_passthrough import _classify_format
        self.assertEqual(_classify_format('.json', 'geo_states.json'), 'geojson')

    def test_classify_json_topo(self):
        from powerbi_import.geo_passthrough import _classify_format
        self.assertEqual(_classify_format('.json', 'topo_regions.json'), 'topojson')

    def test_extract_geojson_properties(self):
        from powerbi_import.geo_passthrough import _extract_geojson_properties
        with tempfile.NamedTemporaryFile(mode='w', suffix='.geojson', delete=False) as f:
            json.dump({
                'type': 'FeatureCollection',
                'features': [{
                    'type': 'Feature',
                    'properties': {'name': 'Region A', 'code': 'RA'},
                    'geometry': {'type': 'Polygon', 'coordinates': []}
                }]
            }, f)
            f.flush()
            props = _extract_geojson_properties(f.name)
        os.unlink(f.name)
        self.assertEqual(props, ['name', 'code'])

    def test_extract_geojson_properties_empty(self):
        from powerbi_import.geo_passthrough import _extract_geojson_properties
        props = _extract_geojson_properties('/nonexistent/file.geojson')
        self.assertEqual(props, [])

    def test_geo_extractor_non_archive(self):
        from powerbi_import.geo_passthrough import GeoExtractor
        with tempfile.TemporaryDirectory() as tmp:
            extractor = GeoExtractor('file.twb', tmp)
            result = extractor.extract()
            self.assertEqual(result, [])

    def test_geo_extractor_from_zip(self):
        """Create a .twbx with a GeoJSON file and extract it."""
        from powerbi_import.geo_passthrough import GeoExtractor
        with tempfile.TemporaryDirectory() as tmp:
            # Create a minimal .twbx (ZIP) with a GeoJSON inside
            twbx_path = os.path.join(tmp, 'test.twbx')
            geojson_content = json.dumps({
                'type': 'FeatureCollection',
                'features': [{
                    'type': 'Feature',
                    'properties': {'region': 'North'},
                    'geometry': {'type': 'Point', 'coordinates': [0, 0]}
                }]
            }).encode('utf-8')
            import zipfile
            with zipfile.ZipFile(twbx_path, 'w') as z:
                z.writestr('data/regions.geojson', geojson_content)
                z.writestr('workbook.twb', '<workbook/>')

            out_dir = os.path.join(tmp, 'output')
            extractor = GeoExtractor(twbx_path, out_dir)
            results = extractor.extract()
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]['format'], 'geojson')
            self.assertEqual(results[0]['filename'], 'regions.geojson')
            self.assertTrue(os.path.exists(results[0]['output_path']))

    def test_build_shape_map_config(self):
        from powerbi_import.geo_passthrough import GeoExtractor
        with tempfile.TemporaryDirectory() as tmp:
            # Write a GeoJSON file
            geo_path = os.path.join(tmp, 'test.geojson')
            with open(geo_path, 'w') as f:
                json.dump({
                    'type': 'FeatureCollection',
                    'features': [{
                        'type': 'Feature',
                        'properties': {'state': 'WA', 'pop': 7600000},
                        'geometry': {'type': 'Point', 'coordinates': [0, 0]}
                    }]
                }, f)

            geo_files = [{
                'filename': 'test.geojson',
                'format': 'geojson',
                'output_path': geo_path,
                'zip_path': 'data/test.geojson',
                'size_bytes': 100,
            }]
            extractor = GeoExtractor('dummy.twbx', tmp)
            config = extractor.build_shape_map_config(geo_files, key_column='state')
            self.assertEqual(config['visualType'], 'shapeMap')
            self.assertEqual(config['shapeMapConfig']['keyProperty'], 'state')
            self.assertIn('state', config['shapeMapConfig']['availableProperties'])

    def test_copy_to_registered_resources(self):
        from powerbi_import.geo_passthrough import GeoExtractor
        with tempfile.TemporaryDirectory() as tmp:
            geo_path = os.path.join(tmp, 'map.geojson')
            with open(geo_path, 'w') as f:
                f.write('{}')
            geo_files = [{'filename': 'map.geojson', 'output_path': geo_path,
                          'format': 'geojson'}]
            pbip_dir = os.path.join(tmp, 'project')
            os.makedirs(pbip_dir)
            extractor = GeoExtractor('dummy.twbx', tmp)
            copied = extractor.copy_to_registered_resources(geo_files, pbip_dir)
            self.assertEqual(len(copied), 1)
            self.assertTrue(os.path.exists(copied[0]))

    def test_geojson_to_shape_map_resource(self):
        from powerbi_import.geo_passthrough import geojson_to_shape_map_resource
        with tempfile.NamedTemporaryFile(mode='w', suffix='.geojson', delete=False) as f:
            json.dump({
                'type': 'FeatureCollection',
                'features': [{'type': 'Feature', 'properties': {'id': 1}, 'geometry': {}}]
            }, f)
            f.flush()
            result = geojson_to_shape_map_resource(f.name)
        os.unlink(f.name)
        self.assertEqual(result['format'], 'geojson')
        self.assertIn('id', result['properties'])


# ════════════════════════════════════════════════════════════════════
# Cross-sprint integration
# ════════════════════════════════════════════════════════════════════

class TestCrossSprintIntegration(unittest.TestCase):
    """Integration tests across Sprint 101-106 features."""

    def test_marketplace_with_industry_recipes(self):
        """Load industry recipes into marketplace and apply."""
        from powerbi_import.marketplace import PatternRegistry
        from powerbi_import.dax_recipes import recipes_to_marketplace_format
        reg = PatternRegistry()
        for pattern in recipes_to_marketplace_format('healthcare'):
            reg.register(pattern)
        self.assertGreater(reg.count, 0)
        measures = {}
        changes = reg.apply_dax_recipes(measures, tags=['healthcare'])
        self.assertGreater(len(measures), 0)

    def test_nested_lod_in_window(self):
        """LOD inside a window function — both parsers cooperate."""
        formula = 'WINDOW_SUM({FIXED [Region] : SUM([Sales])})'
        result = convert_tableau_formula_to_dax(
            formula, table_name='Sales',
            column_table_map={'Region': 'Sales', 'Sales': 'Sales'}
        )
        # LOD should be resolved first (CALCULATE), then window wraps it
        self.assertIn('CALCULATE', result)

    def test_template_and_recipes_together(self):
        """Apply template then inject recipes."""
        from powerbi_import.model_templates import get_template, apply_template
        from powerbi_import.dax_recipes import get_industry_recipes, apply_recipes
        tpl = get_template('retail')
        result = apply_template(tpl, [])
        # Now apply retail recipes on top
        measures = {m['name']: m['dax'] for m in result['measures']}
        recipes = get_industry_recipes('retail')
        changes = apply_recipes(measures, recipes)
        # Should have both template measures and recipe measures
        self.assertGreater(len(measures), len(result['measures']))


if __name__ == '__main__':
    unittest.main()
