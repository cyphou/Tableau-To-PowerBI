"""
Script for extracting Tableau objects from .twb, .twbx, .tds, .tdsx files

This script extracts metadata and structures from Tableau workbooks
and exports them in JSON format for conversion to Power BI.
"""

import os
import sys
import json
import logging
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
import re
from datasource_extractor import extract_datasource
from hyper_reader import read_hyper_from_twbx

logger = logging.getLogger(__name__)


def _safe_int(val, default=0):
    """Safely convert a value to int, handling floats and non-numeric strings."""
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default

# Ensure Unicode output on Windows consoles (✓, →, ❌, etc.)
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        pass


# ── Pre-compiled shared regex patterns ────────────────────────────────────────

_RE_FIELD_REF = re.compile(r'\[([^\]]+)\]\.\[([^\]]+)\]')
_RE_DERIVATION_PREFIX = re.compile(
    r'^(none|sum|avg|count|min|max|usr|yr|mn|dy|qr|wk|attr|md|mdy|hms|hr|mt|sc|thr|trunc|tyr|tqr|tmn|tdy|twk):'
)
_RE_TABLE_CALC_PREFIX = re.compile(
    r'^(pcto|pctd|diff|running_sum|running_avg|running_count|running_min|running_max|rank|rank_unique|rank_dense):(sum|avg|count|min|max|countd)?:?'
)
_RE_TYPE_SUFFIX = re.compile(r':(nk|qk|ok|fn|tn)$')


def _clean_field_ref(raw):
    """Strip Tableau derivation prefixes, table calc prefixes, and type suffixes.

    Handles patterns like ``yr:Order Date:ok`` → ``Order Date``,
    ``none:Ship Mode:nk`` → ``Ship Mode``, ``tyr:Date:qk`` → ``Date``,
    ``pcto:sum:Sales:nk`` → ``Sales``.
    """
    clean = _RE_DERIVATION_PREFIX.sub('', raw)
    clean = _RE_TYPE_SUFFIX.sub('', clean)
    clean = _RE_TABLE_CALC_PREFIX.sub('', clean)
    return clean


def _strip_brackets(s):
    """Remove Tableau bracket notation from a field/table name."""
    return s.replace('[', '').replace(']', '')


def _split_sql_values(values_str):
    """Split a SQL VALUES tuple string into individual values.

    Handles quoted strings that contain commas, e.g.::

        ``"'hello, world', 42, NULL"`` → ``["'hello, world'", "42", "NULL"]``
    """
    result = []
    current = []
    in_quote = False
    for ch in values_str:
        if ch == "'" and not in_quote:
            in_quote = True
            current.append(ch)
        elif ch == "'" and in_quote:
            in_quote = False
            current.append(ch)
        elif ch == ',' and not in_quote:
            result.append(''.join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        result.append(''.join(current).strip())
    return result


def _scan_delimited_sample(text_chunk, col_names, max_rows):
    """Attempt to extract sample rows from tab- or comma-delimited blocks.

    Some Hyper files embed small data blocks.  This does a best-effort
    scan for consistent delimiter lines that match the expected column
    count.

    Returns:
        list[dict]: Up to *max_rows* dicts ``{col_name: value}``.
    """
    ncols = len(col_names) if col_names else 0
    if ncols < 2:
        return []
    samples = []
    for delim in ('\t', '|'):
        lines = text_chunk.split('\n')
        for line in lines:
            parts = line.split(delim)
            # Accept lines whose column count matches ±1
            if abs(len(parts) - ncols) <= 1 and len(parts) >= ncols:
                row = {}
                for i in range(ncols):
                    val = parts[i].strip() if i < len(parts) else ''
                    row[col_names[i]] = val
                # Skip if every value is empty or looks like binary
                if all(v == '' or v.startswith('\x00') for v in row.values()):
                    continue
                samples.append(row)
                if len(samples) >= max_rows:
                    return samples
        if samples:
            return samples
    return samples


class TableauExtractor:
    """Tableau objects extractor"""
    
    def __init__(self, tableau_file, output_dir='tableau_export/'):
        self.tableau_file = tableau_file
        self.output_dir = output_dir
        self.workbook_data = {}
        
        os.makedirs(self.output_dir, exist_ok=True)
    
    def extract_all(self):
        """Extracts all objects from the Tableau workbook"""
        
        print(f"Extracting {self.tableau_file}...")
        
        # Read the Tableau file
        xml_content = self.read_tableau_file()
        
        if not xml_content:
            print("❌ Unable to read the Tableau file")
            return False
        
        # Parse the XML
        root = ET.fromstring(xml_content)
        
        # Extract the different objects
        self.extract_worksheets(root)
        self.extract_dashboards(root)
        self.extract_datasources(root)
        self.extract_calculations(root)
        self.extract_parameters(root)
        self.extract_filters(root)
        self.extract_stories(root)
        self.extract_workbook_actions(root)
        self.extract_sets(root)
        self.extract_groups(root)
        self.extract_bins(root)
        self.extract_hierarchies(root)
        self.extract_sort_orders(root)
        self.extract_aliases(root)
        self.extract_custom_sql(root)
        self.extract_user_filters(root)
        self.extract_datasource_filters(root)
        self.extract_custom_geocoding(root)
        self.extract_published_datasources(root)
        self.extract_data_blending(root)
        self.extract_hyper_metadata()
        
        # Save the exports
        self.save_extractions()
        
        print("✓ Extraction complete")
        return True
    
    def read_tableau_file(self):
        """Reads the XML content of the Tableau file"""
        
        file_ext = os.path.splitext(self.tableau_file)[1].lower()
        
        if file_ext in ['.twb', '.tds']:
            # Direct XML file
            with open(self.tableau_file, 'r', encoding='utf-8') as f:
                return f.read()
        
        elif file_ext in ['.twbx', '.tdsx']:
            # Packaged file (ZIP)
            with zipfile.ZipFile(self.tableau_file, 'r') as z:
                # Find the .twb or .tds file
                for name in z.namelist():
                    if name.endswith('.twb') or name.endswith('.tds'):
                        with z.open(name) as f:
                            return f.read().decode('utf-8')
        
        return None
    
    def extract_worksheets(self, root):
        """Extracts worksheets"""
        
        worksheets = []
        
        for worksheet in root.findall('.//worksheet'):
            ws_data = {
                'name': worksheet.get('name', ''),
                'title': worksheet.findtext('.//title', ''),
                'chart_type': self.determine_chart_type(worksheet),
                'original_mark_class': self._extract_mark_class(worksheet),
                'fields': self.extract_worksheet_fields(worksheet),
                'filters': self.extract_worksheet_filters(worksheet),
                'formatting': self.extract_formatting(worksheet),
                'tooltips': self.extract_tooltips(worksheet),
                'actions': self.extract_actions(worksheet),
                'sort_orders': self.extract_worksheet_sort_orders(worksheet),
                'mark_encoding': self.extract_mark_encoding(worksheet),
                'axes': self.extract_axes(worksheet),
                'reference_lines': self.extract_reference_lines(worksheet),
                'annotations': self.extract_annotations(worksheet),
                'trend_lines': self.extract_trend_lines(worksheet),
                'pages_shelf': self.extract_pages_shelf(worksheet),
                'table_calcs': self.extract_table_calcs(worksheet),
                'forecasting': self.extract_forecasting(worksheet),
                'map_options': self.extract_map_options(worksheet),
                'clustering': self.extract_clustering(worksheet),
                'dual_axis': self.extract_dual_axis_sync(worksheet),
                'totals': self.extract_totals_subtotals(worksheet),
                'description': self.extract_worksheet_description(worksheet),
                'show_hide_headers': self.extract_show_hide_headers(worksheet),
                'dynamic_title': self.extract_dynamic_title(worksheet),
                'analytics_stats': self.extract_analytics_pane_stats(worksheet),
            }
            worksheets.append(ws_data)
        
        self.workbook_data['worksheets'] = worksheets
        print(f"  ✓ {len(worksheets)} worksheets extracted")
    
    def extract_dashboards(self, root):
        """Extracts dashboards"""
        
        dashboards = []
        
        for dashboard in root.findall('.//dashboard'):
            db_data = {
                'name': dashboard.get('name', ''),
                'title': dashboard.findtext('.//title', ''),
                'size': {
                    'width': _safe_int(dashboard.get('width', 1280)),
                    'height': _safe_int(dashboard.get('height', 720)),
                },
                'objects': self.extract_dashboard_objects(dashboard),
                'filters': self.extract_dashboard_filters(dashboard),
                'parameters': self.extract_dashboard_parameters(dashboard),
                'theme': self.extract_theme(dashboard),
                'layout_containers': self.extract_layout_containers(dashboard),
                'device_layouts': self.extract_device_layouts(dashboard),
                'containers': self.extract_dashboard_containers(dashboard),
                'show_hide_containers': self.extract_show_hide_containers(dashboard),
                'dynamic_zone_visibility': self.extract_dynamic_zone_visibility(dashboard),
                'floating_tiled': self.extract_floating_tiled(dashboard),
            }
            dashboards.append(db_data)
        
        self.workbook_data['dashboards'] = dashboards
        print(f"  ✓ {len(dashboards)} dashboards extracted")
    
    def extract_datasources(self, root):
        """Extracts datasources with enhanced extraction.
        
        Filters out empty datasources and deduplicates by name to keep
        only the most complete version (with the most tables/calculations).
        """
        
        raw_datasources = []
        
        for datasource in root.findall('.//datasource'):
            ds_data = extract_datasource(datasource, twbx_path=self.tableau_file)
            raw_datasources.append(ds_data)
        
        # Deduplicate: keep the richest DS by name
        best_ds = {}  # ds_name -> ds_data
        for ds in raw_datasources:
            ds_name = ds.get('name', '')
            tables = ds.get('tables', [])
            calcs = ds.get('calculations', [])
            richness = len(tables) + len(calcs)
            
            if ds_name not in best_ds or richness > (len(best_ds[ds_name].get('tables', [])) + len(best_ds[ds_name].get('calculations', []))):
                best_ds[ds_name] = ds
        
        # Filter: keep only DSs with real content
        datasources = []
        for ds in best_ds.values():
            has_tables = len(ds.get('tables', [])) > 0
            has_calcs = len(ds.get('calculations', [])) > 0
            has_rels = len(ds.get('relationships', [])) > 0
            if has_tables or has_calcs or has_rels:
                datasources.append(ds)
        
        self.workbook_data['datasources'] = datasources
        print(f"  ✓ {len(datasources)} datasources extracted (filtered from {len(raw_datasources)} raw)")
    
    def extract_calculations(self, root):
        """Extracts calculated fields - now integrated in enhanced datasource extraction.

        Also captures worksheet-level calculations defined inside
        ``<datasource-dependencies>`` blocks (common for LOD ratio formulas
        that Tableau auto-generates per worksheet).
        """
        
        # Calculations are now extracted directly in extract_datasource
        # This method maintains backward compatibility
        calculations = []
        seen_names = set()
        
        for datasource in root.findall('.//datasource'):
            ds_data = extract_datasource(datasource, twbx_path=self.tableau_file)
            for calc in ds_data.get('calculations', []):
                cname = calc.get('name', '')
                if cname not in seen_names:
                    seen_names.add(cname)
                    calculations.append(calc)
        
        # Capture worksheet-level calculations from <datasource-dependencies>
        # These are calculations scoped to a specific worksheet (e.g. LOD
        # ratio formulas) that are NOT part of the main datasource definition.
        # Also inject them into the parent datasource's calculations list so
        # the TMDL generator can route them to the correct table.
        ds_by_name = {ds.get('name', ''): ds
                      for ds in self.workbook_data.get('datasources', [])}
        ds_seen = {}  # datasource_name -> set of calc names already present
        for ds_name, ds in ds_by_name.items():
            ds_seen[ds_name] = {c.get('name', '') for c in ds.get('calculations', [])}

        for ws in root.findall('.//worksheet'):
            for dep in ws.findall('.//datasource-dependencies'):
                ds_ref = dep.get('datasource', '')
                for col_elem in dep.findall('column'):
                    calc_elem = col_elem.find('calculation')
                    if calc_elem is None:
                        continue
                    calc_formula = calc_elem.get('formula', '').strip()
                    if not calc_formula:
                        continue
                    calc_class = calc_elem.get('class', 'tableau')
                    if calc_class == 'categorical-bin':
                        continue
                    cname = col_elem.get('name', '')
                    if cname in seen_names:
                        continue
                    seen_names.add(cname)
                    raw_caption = col_elem.get('caption', cname)
                    # If caption looks like a formula (auto-generated by
                    # Tableau), sanitize: strip brackets for a cleaner name
                    if '[' in raw_caption and ']' in raw_caption:
                        raw_caption = raw_caption.replace('[', '').replace(']', '')
                    calc_entry = {
                        'name': cname,
                        'caption': raw_caption,
                        'formula': calc_formula,
                        'class': calc_class,
                        'datatype': col_elem.get('datatype', 'real'),
                        'role': col_elem.get('role', 'measure'),
                        'type': col_elem.get('type', 'quantitative'),
                    }
                    calculations.append(calc_entry)
                    # Also inject into the parent datasource so the TMDL
                    # generator picks it up during per-datasource processing
                    if ds_ref in ds_by_name and cname not in ds_seen.get(ds_ref, set()):
                        ds_by_name[ds_ref].setdefault('calculations', []).append(calc_entry)
                        ds_seen.setdefault(ds_ref, set()).add(cname)
        
        self.workbook_data['calculations'] = calculations
        print(f"  ✓ {len(calculations)} calculations extracted")
    
    def extract_parameters(self, root):
        """Extracts parameters (deduplicated by name).
        Handles both XML formats:
        - Old: <column param-domain-type="..."> (Tableau Desktop classic)
        - New: <parameters><parameter> (Tableau Desktop modern)
        """
        
        parameters = []
        seen_names = set()
        
        # Format 1: Old-style column-based parameters
        for param in root.findall('.//column[@param-domain-type]'):
            param_name = param.get('name', '')
            if param_name in seen_names:
                continue
            seen_names.add(param_name)
            
            param_data = {
                'name': param_name,
                'caption': param.get('caption', ''),
                'datatype': param.get('datatype', ''),
                'value': param.get('value', ''),
                'domain_type': param.get('param-domain-type', ''),
                'allowable_values': self.extract_allowable_values(param),
            }

            # Detect dynamic (database-query-driven) parameters in old format
            if param.get('param-domain-type') == 'database':
                param_data['domain_type'] = 'database'
                query_elem = param.find('.//query')
                if query_elem is None:
                    query_elem = param.find('.//calculation')
                if query_elem is not None:
                    param_data['query'] = query_elem.get('formula', '') or query_elem.text or ''
                conn_elem = param.find('.//connection')
                if conn_elem is not None:
                    param_data['query_connection'] = conn_elem.get('class', '')
                    param_data['query_dbname'] = conn_elem.get('dbname', '')
                param_data['refresh_on_open'] = True

            parameters.append(param_data)
        
        # Format 2: New-style <parameters><parameter> elements
        for param in root.findall('.//parameters/parameter'):
            param_name = param.get('name', '')
            if param_name in seen_names:
                continue
            seen_names.add(param_name)
            
            # Determine domain type from children
            domain_type = 'any'
            if param.find('range') is not None:
                domain_type = 'range'
            elif param.find('domain') is not None:
                domain_type = 'list'
            
            param_data = {
                'name': param_name,
                'caption': param.get('caption', ''),
                'datatype': param.get('datatype', ''),
                'value': param.get('value', ''),
                'domain_type': domain_type,
                'allowable_values': self.extract_allowable_values(param),
            }

            # Detect dynamic (database-query-driven) parameters (Tableau 2024.3+)
            query_elem = param.find('.//query')
            if query_elem is not None:
                param_data['domain_type'] = 'database'
                param_data['query'] = query_elem.text or query_elem.get('value', '')
                conn_elem = param.find('.//query-connection')
                if conn_elem is None:
                    conn_elem = param.find('.//connection')
                if conn_elem is not None:
                    param_data['query_connection'] = conn_elem.get('class', '')
                    param_data['query_dbname'] = conn_elem.get('dbname', '')
                param_data['refresh_on_open'] = (
                    param.get('refresh-on-open', 'false').lower() == 'true'
                )
            elif param.get('param-domain-type') == 'database':
                # Column-style dynamic parameter
                param_data['domain_type'] = 'database'
                sql_elem = param.find('.//query')
                if sql_elem is None:
                    sql_elem = param.find('.//calculation')
                if sql_elem is not None:
                    param_data['query'] = sql_elem.get('formula', '') or sql_elem.text or ''
                param_data['refresh_on_open'] = True

            parameters.append(param_data)
        
        self.workbook_data['parameters'] = parameters
        print(f"  ✓ {len(parameters)} parameters extracted")
    
    def extract_filters(self, root):
        """Extracts filters"""
        
        filters = []
        
        for filt in root.findall('.//filter'):
            filter_data = {
                'field': filt.get('column', ''),
                'type': filt.get('type', ''),
                'values': [v.text for v in filt.findall('.//value') if v.text is not None],
            }
            filters.append(filter_data)
        
        self.workbook_data['filters'] = filters
        print(f"  ✓ {len(filters)} filters extracted")
    
    def extract_stories(self, root):
        """Extracts stories"""
        
        stories = []
        
        for story in root.findall('.//story'):
            story_data = {
                'name': story.get('name', ''),
                'title': story.findtext('.//title', ''),
                'story_points': self.extract_story_points(story),
            }
            stories.append(story_data)
        
        self.workbook_data['stories'] = stories
        print(f"  ✓ {len(stories)} stories extracted")
    
    # Helper methods
    
    def _extract_mark_class(self, worksheet):
        """Returns the raw Tableau mark class string (e.g. 'Bar', 'Gantt Bar').

        Used downstream by the PBIR generator to look up custom visual
        GUIDs for mark types that have AppSource equivalents.
        """
        for pane in worksheet.findall('.//pane'):
            mark = pane.find('.//mark')
            if mark is not None and mark.get('class'):
                return mark.get('class')
        for mark in worksheet.findall('.//style/mark'):
            if mark.get('class'):
                return mark.get('class')
        return None

    def determine_chart_type(self, worksheet):
        """Determines the chart type from the Tableau mark type.
        
        When the mark class is 'Automatic', infers the visual type from
        field shelf assignments (columns/rows/color) instead of defaulting
        to 'table'.
        """
        mark_class = None
        # Search for the mark class in panes
        for pane in worksheet.findall('.//pane'):
            mark = pane.find('.//mark')
            if mark is not None and mark.get('class'):
                mark_class = mark.get('class')
                break
        
        # Search in style/mark
        if mark_class is None:
            for mark in worksheet.findall('.//style/mark'):
                if mark.get('class'):
                    mark_class = mark.get('class')
                    break
        
        # Fallback: map encoding
        if mark_class is None:
            if worksheet.find('.//encoding/map') is not None:
                return 'map'
            return 'bar'
        
        # For explicit mark types, use the mapping directly
        if mark_class != 'Automatic':
            return self._map_tableau_mark_to_type(mark_class)
        
        # Automatic: infer from field shelf assignments
        return self._infer_automatic_chart_type(worksheet)
    
    def _infer_automatic_chart_type(self, worksheet):
        """Infers the chart type when Tableau uses 'Automatic' mark.
        
        Uses field shelf assignments (columns/rows) and field names to
        determine the most appropriate Power BI visual type.
        """
        date_words = {'date', 'time', 'year', 'month', 'day', 'week', 'quarter',
                      'datetime', 'timestamp', 'period', 'yr', 'mois',
                      # French
                      'année', 'annee', 'jour', 'semaine', 'trimestre',
                      'commande', 'expédition', 'expedition', 'livraison'}
        measure_words = {'sales', 'profit', 'revenue', 'amount', 'quantity', 'qty',
                         'count', 'sum', 'total', 'price', 'cost', 'margin',
                         'budget', 'forecast', 'actual', 'target', 'value',
                         'weight', 'height', 'distance', 'rate', 'ratio',
                         'score', 'index', 'number', 'num', 'avg', 'average',
                         # French
                         'ventes', 'vente', 'bénéfice', 'bénéfices', 'benefice',
                         'coût', 'cout', 'quantité', 'quantite', 'montant',
                         'prix', 'marge', 'remise', 'objectif', 'prévision',
                         'prevision', 'chiffre', 'recette', 'dépense', 'depense'}
        geo_words = {'latitude', 'longitude', 'lat', 'lon', 'lng',
                     'zip', 'postal', 'geo', 'geolocation'}
        # Geographic pairs that strongly indicate a map
        geo_pairs = {('latitude', 'longitude'), ('lat', 'lon'), ('lat', 'lng')}

        col_fields = []
        row_fields = []

        # Parse rows/cols shelf text for field references
        for shelf_tag, target in [('cols', col_fields), ('rows', row_fields)]:
            shelf = worksheet.find(f'./table/{shelf_tag}')
            if shelf is not None and shelf.text:
                refs = re.findall(r'\[([^\]]+)\]\.\[([^\]]+)\]', shelf.text)
                for _, field_ref in refs:
                    # Strip derivation/aggregation prefixes
                    clean = _clean_field_ref(field_ref)
                    target.append(clean)

        def _is_date(name):
            return any(w in name.lower().split() for w in date_words)

        def _is_measure(name):
            return any(w in name.lower().split() for w in measure_words)

        # Check for map encoding
        if worksheet.find('.//encoding/map') is not None:
            return 'map'
        # Check for geographic field pairs (lat+lon)
        all_field_words = set()
        for f in col_fields + row_fields:
            all_field_words.update(f.lower().split())
        for w1, w2 in geo_pairs:
            if w1 in all_field_words and w2 in all_field_words:
                return 'map'

        all_row_measures = all(_is_measure(f) for f in row_fields) if row_fields else False
        all_col_measures = all(_is_measure(f) for f in col_fields) if col_fields else False
        has_date_col = any(_is_date(f) for f in col_fields)
        has_date_row = any(_is_date(f) for f in row_fields)

        # Two measures on rows + columns → scatter
        if col_fields and row_fields and all_col_measures and all_row_measures:
            return 'scatterChart'
        # Date on columns/rows with a measure → line
        if has_date_col and row_fields:
            return 'lineChart'
        if has_date_row and col_fields:
            return 'lineChart'
        # Dimension + measure → bar chart
        if col_fields and row_fields:
            return 'clusteredBarChart'
        # Only has fields on one axis → table
        if not col_fields and not row_fields:
            return 'table'
        return 'clusteredBarChart'
    
    def _map_tableau_mark_to_type(self, mark_class):
        """Maps Tableau mark types to Power BI visual types.

        Covers all Tableau mark classes and maps them to the closest
        Power BI visual type string expected by PBIR v4.0.
        """
        mark_map = {
            # ── Standard mark classes ──────────────────────────────
            'Automatic': 'clusteredBarChart',  # fallback; usually handled by _infer_automatic_chart_type
            'Bar': 'clusteredBarChart',
            'Stacked Bar': 'stackedBarChart',
            'Line': 'lineChart',
            'Area': 'areaChart',
            'Square': 'treemap',
            'Circle': 'scatterChart',
            'Shape': 'scatterChart',
            'Text': 'tableEx',
            'Map': 'map',
            'Pie': 'pieChart',
            'Gantt Bar': 'clusteredBarChart',
            'Polygon': 'map',
            'Multipolygon': 'map',
            'Density': 'map',
            # ── Extended mark/chart types (Tableau 2020+) ───────────
            'SemiCircle': 'donutChart',
            'Hex': 'treemap',
            'Histogram': 'clusteredColumnChart',
            'Box Plot': 'boxAndWhisker',
            'Box-and-Whisker': 'boxAndWhisker',
            'Bullet': 'gauge',
            'Waterfall': 'waterfallChart',
            'Funnel': 'funnel',
            'Treemap': 'treemap',
            'Heat Map': 'matrix',
            'Highlight Table': 'matrix',
            'Packed Bubble': 'scatterChart',
            'Packed Bubbles': 'scatterChart',
            'Word Cloud': 'wordCloud',
            'Radial': 'gauge',
            'Dual Axis': 'lineClusteredColumnComboChart',
            'Combo': 'lineClusteredColumnComboChart',
            'Combined Axis': 'lineClusteredColumnComboChart',
            'Line and Bar': 'lineClusteredColumnComboChart',
            'Reference Line': 'lineChart',
            'Reference Band': 'lineChart',
            'Trend Line': 'lineChart',
            'Dot Plot': 'scatterChart',
            'Strip Plot': 'scatterChart',
            'Lollipop': 'clusteredBarChart',
            'Bump Chart': 'lineChart',
            'Slope Chart': 'lineChart',
            'Butterfly Chart': 'hundredPercentStackedBarChart',
            'Pareto Chart': 'lineClusteredColumnComboChart',
            'Sankey': 'decompositionTree',
            'Chord': 'decompositionTree',
            'Network': 'decompositionTree',
            'Calendar': 'matrix',
            'Timeline': 'lineChart',
            'KPI': 'card',
            'Sparkline': 'lineChart',
            'Donut': 'donutChart',
            'Ring': 'donutChart',
            'Rose Chart': 'donutChart',
            'Waffle': 'hundredPercentStackedBarChart',
            'Gauge': 'gauge',
            'Speedometer': 'gauge',
            'Image': 'image',
        }
        return mark_map.get(mark_class, 'clusteredBarChart')
    
    def extract_worksheet_fields(self, worksheet):
        """Extracts fields used in the worksheet"""
        fields = []
        
        # Regex for Tableau derivation prefixes (none, sum, avg, count, usr, yr, etc.)
        derivation_re = r'^(none|sum|avg|count|min|max|usr|yr|mn|dy|qr|wk|attr|md|mdy|hms|hr|mt|sc|thr|trunc):'
        suffix_re = r':(nk|qk|ok|fn|tn)$'
        # Quick table calc prefixes (pcto = % of total, pctd = % difference, running_*)
        table_calc_re = r'^(pcto|pctd|diff|running_sum|running_avg|running_count|running_min|running_max|rank|rank_unique|rank_dense):(sum|avg|count|min|max|countd)?:?'
        
        # Extract from <table><rows> and <table><cols> (text content with field refs)
        for shelf_name, shelf_tag in [('columns', 'cols'), ('rows', 'rows')]:
            shelf = worksheet.find(f'./table/{shelf_tag}')
            if shelf is not None and shelf.text:
                # Text contains refs like [datasource].[field:type]
                # or three-part [datasource].[column].[aggregation:instance:suffix]
                # Use a regex that captures 2 or 3 bracket groups.
                three_part_re = r'\[([^\]]+)\]\.\[([^\]]+)\](?:\.\[([^\]]+)\])?'
                refs = re.findall(three_part_re, shelf.text)
                for match in refs:
                    ds_ref, field_ref, instance_ref = match[0], match[1], match[2]

                    # Three-part ref: [ds].[__tableau_internal_object_id__].[cnt:...:qk]
                    # means COUNT(*) on the table rows.
                    if '__tableau_internal' in field_ref and instance_ref:
                        inst_agg = re.match(r'^(cnt|sum|avg|min|max|countd|median):', instance_ref)
                        if inst_agg:
                            fields.append({
                                'name': 'Number of Records',
                                'shelf': shelf_name,
                                'datasource': ds_ref,
                                'aggregation': inst_agg.group(1),
                            })
                            continue
                        # No aggregation on internal field → skip it entirely
                        continue

                    # Detect quick table calc prefix before cleaning
                    table_calc_match = re.match(table_calc_re, field_ref)
                    table_calc_type = None
                    table_calc_agg = None
                    if table_calc_match:
                        table_calc_type = table_calc_match.group(1)
                        table_calc_agg = table_calc_match.group(2) or 'sum'

                    # Detect aggregation prefix (cnt:, sum:, avg:, etc.)
                    agg_prefix_match = re.match(r'^(cnt|sum|avg|min|max|countd|median|attr|stdev|stdevp|var|varp):', field_ref)
                    shelf_agg = agg_prefix_match.group(1) if agg_prefix_match else None

                    # Clean the field name (remove derivation prefix and type suffix)
                    clean_name = re.sub(table_calc_re, '', field_ref)
                    clean_name = re.sub(derivation_re, '', clean_name)
                    clean_name = re.sub(suffix_re, '', clean_name)

                    # COUNT on __tableau_internal_object_id__ = COUNT(*)
                    # Convert to synthetic "Number of Records" measure.
                    if '__tableau_internal' in clean_name and shelf_agg:
                        field_data = {
                            'name': 'Number of Records',
                            'shelf': shelf_name,
                            'datasource': ds_ref,
                            'aggregation': shelf_agg,
                        }
                        fields.append(field_data)
                        continue
                    
                    field_data = {
                        'name': clean_name,
                        'shelf': shelf_name,
                        'datasource': ds_ref
                    }
                    if table_calc_type:
                        field_data['table_calc'] = table_calc_type
                        field_data['table_calc_agg'] = table_calc_agg
                    if shelf_agg:
                        field_data['aggregation'] = shelf_agg
                    fields.append(field_data)
        
        # Extract from encodings (color, size, detail, tooltip, label, text)
        for encoding in worksheet.findall('.//encodings'):
            for enc_type in ['color', 'size', 'detail', 'tooltip', 'label', 'text']:
                for enc_elem in encoding.findall(f'./{enc_type}'):
                    column = enc_elem.get('column', '')
                    if column:
                        # Extract [datasource].[field]
                        col_refs = re.findall(r'\[([^\]]+)\]\.\[([^\]]+)\]', column)
                        if col_refs:
                            clean = re.sub(derivation_re, '', col_refs[0][1])
                            clean = re.sub(suffix_re, '', clean)
                            fields.append({
                                'name': clean,
                                'shelf': enc_type,
                                'datasource': col_refs[0][0]
                            })

        # ── Expand :Measure Names / Multiple Values ───────────────
        # When a worksheet uses these virtual fields, the actual measures
        # are listed in <datasource-dependencies> <column-instance> entries
        # with aggregation derivations (Sum, Avg, Count, CountD, User, ...).
        # We cross-reference with <column role='measure'> to only include
        # columns that are truly measures (not CountD on dimension columns).
        has_measure_names = any(
            f.get('name', '') in (':Measure Names', 'Measure Names')
            for f in fields
        )
        if has_measure_names:
            agg_derivations = {
                'Sum', 'Avg', 'Count', 'CountD', 'Min', 'Max',
                'Median', 'Stdev', 'Var', 'User', 'Attribute',
            }
            # Collect existing field names to avoid duplicates
            existing_names = {f.get('name', '') for f in fields}
            for dep in worksheet.findall('.//datasource-dependencies'):
                ds_ref = dep.get('datasource', '')
                # Build a set of column names with role='measure'
                measure_cols = set()
                for col_elem in dep.findall('column'):
                    if col_elem.get('role', '') == 'measure':
                        measure_cols.add(col_elem.get('name', '').strip('[]'))
                # Also include calculation columns (User derivation) —
                # they may have role='measure' in column definition
                for ci in dep.findall('column-instance'):
                    deriv = ci.get('derivation', '')
                    if deriv not in agg_derivations:
                        continue
                    col_name = ci.get('column', '').strip('[]')
                    # Skip internal Tableau columns
                    if col_name.startswith('__tableau_internal'):
                        continue
                    # Only include columns that are measures (or User-derived calcs)
                    if col_name not in measure_cols and deriv != 'User':
                        continue
                    if col_name in existing_names:
                        continue
                    existing_names.add(col_name)
                    fields.append({
                        'name': col_name,
                        'shelf': 'measure_value',
                        'datasource': ds_ref,
                    })

        return fields
    
    def extract_worksheet_filters(self, worksheet):
        """Extracts worksheet filters from <filter> elements"""
        filters = []
        for filt in worksheet.findall('.//filter'):
            column_ref = filt.get('column', '')
            # Extract field name from [datasource].[field]
            col_match = re.findall(r'\[([^\]]+)\]\.\[([^\]]+)\]', column_ref)
            if col_match:
                ds_ref, field_ref = col_match[0]
                clean_name = _clean_field_ref(field_ref)
            else:
                ds_ref = ''
                field_ref = column_ref
                clean_name = _strip_brackets(column_ref)

            # Detect date-part filters (yr:, qr:, mn:, dy:, wk:, etc.)
            _date_part_match = re.match(
                r'^(yr|qr|mn|dy|wk|tyr|tqr|tmn|tdy|twk|hr|mt|sc|trunc):',
                field_ref)
            _date_part = _date_part_match.group(1) if _date_part_match else None

            filter_type = ''
            filter_values = []
            filter_min = None
            filter_max = None
            include_null = False
            exclude_mode = False
            
            # Determine the filter type
            groupfilter = filt.find('.//groupfilter')
            if groupfilter is not None:
                func = groupfilter.get('function', '')
                if func == 'member':
                    # Filter by exact value
                    filter_type = 'categorical'
                    val = groupfilter.get('member', '')
                    if val:
                        filter_values.append(val.replace('&quot;', '"'))
                elif func == 'union':
                    filter_type = 'categorical'
                    for gf in groupfilter.findall('.//groupfilter[@function="member"]'):
                        val = gf.get('member', '')
                        if val:
                            filter_values.append(val.replace('&quot;', '"'))
                elif func == 'range':
                    from_val = groupfilter.get('from', '')
                    to_val = groupfilter.get('to', '')
                    # Detect text-range vs numeric/date range.
                    # Tableau uses func="range" on categorical text fields
                    # (e.g. from="Shipped Early" to="Shipped On Time")
                    # to mean "keep only these categories".  In PBI this
                    # should be a categorical In filter, not an Advanced >=/<= filter.
                    _is_numeric_range = False
                    for _rv in (from_val, to_val):
                        if _rv:
                            try:
                                float(_rv)
                                _is_numeric_range = True
                            except (ValueError, TypeError):
                                pass
                    if _is_numeric_range:
                        filter_type = 'range'
                        filter_min = from_val if from_val else None
                        filter_max = to_val if to_val else None
                    else:
                        # Text range → effectively "all selected" on a
                        # categorical field.  Tableau uses an alphabetical
                        # range (from="A" to="Z") to keep all values.
                        # Skip: no real filtering intended.
                        filter_type = 'all'
                elif func == 'level-members':
                    filter_type = 'all'  # filter "all selected"
                elif func == 'crossjoin':
                    filter_type = 'all'  # multi-field action filter → skip
                elif func == 'except' or func == 'not':
                    exclude_mode = True
                    filter_type = 'categorical'
                    for gf in groupfilter.findall('.//groupfilter[@function="member"]'):
                        val = gf.get('member', '')
                        if val:
                            filter_values.append(val.replace('&quot;', '"'))
            
            # Values from <value>
            for v in filt.findall('.//value'):
                if v.text:
                    filter_values.append(v.text)
            
            filters.append({
                'field': clean_name,
                'datasource': ds_ref,
                'type': filter_type,
                'values': filter_values,
                'min': filter_min,
                'max': filter_max,
                'exclude': exclude_mode,
                'include_null': include_null,
                'is_context': filt.get('context', '') == 'true',
                'date_part': _date_part
            })
        return filters
    
    def extract_formatting(self, element):
        """Extracts formatting information (colors, fonts, backgrounds, borders)"""
        formatting = {}
        
        # Extract styles from <style-rule>  
        for style_rule in element.findall('.//style-rule'):
            rule_element = style_rule.get('element', '')
            format_elem = style_rule.find('.//format')
            if format_elem is not None:
                attrs = dict(format_elem.attrib)
                if attrs:
                    formatting[rule_element] = attrs
            # Also collect all format children (some style-rules have multiple formats)
            for fmt in style_rule.findall('.//format'):
                attr_name = fmt.get('attr', '')
                attr_val = fmt.get('value', '')
                if attr_name and attr_val and rule_element:
                    formatting.setdefault(rule_element, {})[attr_name] = attr_val
        
        # Extract format encodings from <format>
        for fmt in element.findall('.//format'):
            field = fmt.get('field', '')
            fmt_str = fmt.get('value', '')
            if field and fmt_str:
                formatting.setdefault('field_formats', {})[field] = fmt_str
        
        # Background color
        for pane_fmt in element.findall('.//pane/format'):
            if pane_fmt.get('attr') == 'fill-color':
                formatting['background_color'] = pane_fmt.get('value', '')
        
        # Table/header formatting depth (font sizes, weights, colors, borders, banding)
        for fmt_attr in ('font-size', 'font-family', 'font-weight', 'font-color',
                         'text-align', 'border-style', 'border-color', 'border-width',
                         'band-color', 'band-size'):
            for fmt in element.findall(f'.//format[@attr="{fmt_attr}"]'):
                scope = fmt.get('scope', 'worksheet')
                val = fmt.get('value', '')
                if val:
                    formatting.setdefault(f'{scope}_style', {})[fmt_attr] = val
        
        # Legend position and formatting
        legend_elem = element.find('.//legend')
        if legend_elem is not None:
            legend_info = {}
            legend_pos = legend_elem.get('position', '')
            if legend_pos:
                legend_info['position'] = legend_pos
            legend_title = legend_elem.get('title', '')
            if legend_title:
                legend_info['title'] = legend_title
            # Check for legend style attributes
            for attr in ('font-size', 'font-family', 'font-weight', 'font-color'):
                val = legend_elem.get(attr, '')
                if val:
                    legend_info[attr] = val
            if legend_info:
                formatting['legend'] = legend_info
        
        # Also check legend style rule 
        if 'legend-title' in formatting:
            formatting.setdefault('legend', {})['title_style'] = formatting['legend-title']
        if 'color-legend' in formatting:
            formatting.setdefault('legend', {}).update({
                k: v for k, v in formatting['color-legend'].items()
                if k not in formatting.get('legend', {})
            })
        
        return formatting
    
    def extract_tooltips(self, worksheet):
        """Extracts tooltips (fields, viz-in-tooltip, and custom formatting per run)"""
        tooltips = []
        
        # Text tooltip from <formatted-text>
        for tooltip_elem in worksheet.findall('.//tooltip'):
            formatted = tooltip_elem.find('.//formatted-text')
            if formatted is not None:
                # Reconstruct the text with per-run formatting
                parts = []
                runs = []
                for run in formatted.findall('.//run'):
                    if run.text:
                        parts.append(run.text)
                        run_data = {'text': run.text}
                        bold = run.get('bold', run.get('fontweight', ''))
                        if bold and bold.lower() in ('true', 'bold'):
                            run_data['bold'] = True
                        color = run.get('fontcolor', run.get('color', ''))
                        if color:
                            run_data['color'] = color
                        font_size = run.get('fontsize', '')
                        if font_size:
                            run_data['font_size'] = font_size
                        # Detect field references <run>[field]</run>
                        field_match = re.match(r'^\s*\[([^\]]+)\]\s*$', run.text)
                        if field_match:
                            run_data['field_ref'] = field_match.group(1)
                        runs.append(run_data)
                if parts:
                    tt = {'type': 'text', 'content': ''.join(parts)}
                    if runs:
                        tt['runs'] = runs
                    tooltips.append(tt)
            
            # Viz in tooltip (reference to another worksheet)
            viz_ref = tooltip_elem.get('viz', '')
            if viz_ref:
                tooltips.append({'type': 'viz_in_tooltip', 'worksheet': viz_ref})
        
        return tooltips
    
    def extract_actions(self, worksheet):
        """Extracts actions referenced in this worksheet"""
        # Actions are at the workbook level, not worksheet
        # This method remains for backward compatibility
        return []
    
    def extract_dashboard_objects(self, dashboard):
        """Extracts all dashboard objects: worksheets, text, images, web, filters, blank.
        
        Also detects floating vs tiled mode.
        """
        objects = []
        seen_names = set()
        
        for zone in dashboard.findall('.//zone'):
            zone_name = zone.get('name', '')
            zone_type = zone.get('type', '')
            zone_id = zone.get('id', '')
            is_fixed = zone.get('is-fixed') == 'true' or zone.get('type-v2') == 'fix'
            is_floating = zone.get('is-floating') == 'true'
            
            pos = {
                'x': _safe_int(zone.get('x', 0)),
                'y': _safe_int(zone.get('y', 0)),
                'w': _safe_int(zone.get('w', 300)),
                'h': _safe_int(zone.get('h', 200)),
            }
            
            layout_mode = 'floating' if is_floating else ('fixed' if is_fixed else 'tiled')
            
            # Texte
            if zone_type == 'text' or zone.get('type-v2') == 'text':
                text_content = ''
                text_runs = []
                formatted = zone.find('.//formatted-text')
                if formatted is not None:
                    parts = []
                    for run in formatted.findall('.//run'):
                        if run.text:
                            parts.append(run.text)
                            run_data = {'text': run.text}
                            if run.get('bold', run.get('fontweight', '')).lower() in ('true', 'bold'):
                                run_data['bold'] = True
                            if run.get('italic', run.get('fontstyle', '')).lower() in ('true', 'italic'):
                                run_data['italic'] = True
                            color = run.get('fontcolor', run.get('color', ''))
                            if color:
                                run_data['color'] = color
                            font_size = run.get('fontsize', '')
                            if font_size:
                                run_data['font_size'] = font_size
                            url = run.get('href', run.get('url', ''))
                            if url:
                                run_data['url'] = url
                            text_runs.append(run_data)
                    text_content = ''.join(parts)
                objects.append({
                    'type': 'text',
                    'name': zone_name or f'text_{zone_id}',
                    'content': text_content,
                    'text_runs': text_runs,
                    'position': pos,
                    'layout': layout_mode
                })
                continue
            
            # Image
            if zone_type == 'bitmap' or zone.get('type-v2') == 'bitmap':
                img_src = ''
                img_elem = zone.find('.//zone-style/format[@attr="image"]')
                if img_elem is not None:
                    img_src = img_elem.get('value', '')
                objects.append({
                    'type': 'image',
                    'name': zone_name or f'image_{zone_id}',
                    'source': img_src,
                    'position': pos,
                    'layout': layout_mode
                })
                continue
            
            # Page web
            if zone_type == 'web' or zone.get('type-v2') == 'web':
                url = zone.get('url', '') or zone.findtext('.//url', '')
                objects.append({
                    'type': 'web',
                    'name': zone_name or f'web_{zone_id}',
                    'url': url,
                    'position': pos,
                    'layout': layout_mode
                })
                continue
            
            # Blank / spacer
            if zone_type == 'empty' or zone.get('type-v2') == 'empty':
                objects.append({
                    'type': 'blank',
                    'name': f'blank_{zone_id}',
                    'position': pos,
                    'layout': layout_mode
                })
                continue
            
            # Navigation button
            if zone_type == 'nav' or zone.get('type-v2') == 'nav' or zone.get('type-v2') == 'button':
                target = zone.get('target-sheet', zone.get('param', ''))
                objects.append({
                    'type': 'navigation_button',
                    'name': zone_name or f'nav_{zone_id}',
                    'target_sheet': target,
                    'position': pos,
                    'layout': layout_mode
                })
                continue
            
            # Download button (export)
            if zone_type == 'export' or zone.get('type-v2') == 'export':
                objects.append({
                    'type': 'download_button',
                    'name': zone_name or f'download_{zone_id}',
                    'position': pos,
                    'layout': layout_mode
                })
                continue
            
            # Extension object
            if zone_type == 'extension' or zone.get('type-v2') == 'extension':
                ext_id = zone.get('extension-id', '')
                objects.append({
                    'type': 'extension',
                    'name': zone_name or f'ext_{zone_id}',
                    'extension_id': ext_id,
                    'position': pos,
                    'layout': layout_mode
                })
                continue
            
            # Per-object padding/margins from zone-style format elements
            obj_padding = {}
            zone_style = zone.find('zone-style')
            if zone_style is not None:
                for fmt in zone_style.findall('format'):
                    attr_name = fmt.get('attr', '')
                    attr_val = fmt.get('value', '')
                    if attr_name.startswith(('padding-', 'margin-')):
                        try:
                            obj_padding[attr_name] = int(attr_val)
                        except (ValueError, TypeError):
                            pass
                    elif attr_name.startswith('border-'):
                        key = attr_name.replace('-', '_')
                        obj_padding[key] = attr_val
            # Also check direct zone attributes
            for pad_attr in ('padding-top', 'padding-bottom', 'padding-left', 'padding-right',
                             'margin-top', 'margin-bottom', 'margin-left', 'margin-right'):
                val = zone.get(pad_attr, '')
                if val and pad_attr not in obj_padding:
                    try:
                        obj_padding[pad_attr] = int(val)
                    except (ValueError, TypeError):
                        pass
            
            # Filtre (quick filter / parameter control)
            if zone_type == 'filter' or zone.get('type-v2') == 'filter':
                param_ref = zone.get('param', '')
                # Deduplicate by param (nested zones create duplicates)
                dedup_key = f"fc_{param_ref}" if param_ref else f"fc_{zone_name}_{zone_id}"
                if dedup_key not in seen_names:
                    seen_names.add(dedup_key)
                    # Extract the column/calculation name from the param
                    calc_column_name = ''
                    if 'none:' in param_ref:
                        calc_id = param_ref.split('none:')[1].split(':')[0]
                        calc_column_name = calc_id
                    objects.append({
                        'type': 'filter_control',
                        'name': zone_name or f'filter_{zone_id}',
                        'field': zone_name,
                        'param': param_ref,
                        'calc_column_id': calc_column_name,
                        'position': pos,
                        'layout': layout_mode
                    })
                continue
            
            # Worksheet reference (the default case)
            if zone_name and zone_name not in seen_names:
                seen_names.add(zone_name)
                ws_obj = {
                    'type': 'worksheetReference',
                    'name': zone_name,
                    'worksheetName': zone_name,
                    'position': pos,
                    'layout': layout_mode
                }
                if obj_padding:
                    ws_obj['padding'] = obj_padding
                objects.append(ws_obj)
        
        return objects
    
    def extract_dashboard_filters(self, dashboard):
        """Extracts dashboard filters from <filter> elements"""
        filters = []
        for filt in dashboard.findall('.//filter'):
            column_ref = filt.get('column', '')
            col_match = re.findall(r'\[([^\]]+)\]\.\[([^\]]+)\]', column_ref)
            if col_match:
                ds_ref, field_ref = col_match[0]
                clean_name = _clean_field_ref(field_ref)
            else:
                ds_ref = ''
                clean_name = _strip_brackets(column_ref)
            
            filter_values = [v.text for v in filt.findall('.//value') if v.text]
            filters.append({
                'field': clean_name,
                'datasource': ds_ref,
                'values': filter_values
            })
        return filters
    
    def extract_dashboard_parameters(self, dashboard):
        """Extracts parameter controls from the dashboard"""
        params = []
        for zone in dashboard.findall('.//zone'):
            param_ref = zone.get('param', '')
            if param_ref:
                params.append({
                    'name': param_ref,
                    'zone_name': zone.get('name', ''),
                    'position': {
                        'x': _safe_int(zone.get('x', 0)),
                        'y': _safe_int(zone.get('y', 0)),
                        'w': _safe_int(zone.get('w', 200)),
                        'h': _safe_int(zone.get('h', 30)),
                    }
                })
        return params
    
    def extract_layout_containers(self, dashboard):
        """Extracts layout container hierarchy (horizontal/vertical nesting).
        
        Tableau uses <layout-container> elements to organize zones
        into horizontal and vertical groups with spacing.
        """
        containers = []
        for lc in dashboard.findall('.//layout-container'):
            container = {
                'orientation': lc.get('orientation', 'vertical'),  # horizontal or vertical
                'position': {
                    'x': _safe_int(lc.get('x', 0)),
                    'y': _safe_int(lc.get('y', 0)),
                    'w': _safe_int(lc.get('w', 0)),
                    'h': _safe_int(lc.get('h', 0)),
                },
                'children': [],
            }
            # Extract child zone references
            for child in lc.findall('.//zone'):
                child_name = child.get('name', '')
                if child_name:
                    container['children'].append(child_name)
            containers.append(container)
        return containers
    
    def extract_device_layouts(self, dashboard):
        """Extracts device-specific layouts (phone, tablet, desktop).
        
        Tableau dashboards can have different layouts per device type,
        with different zone visibility and positioning.
        """
        layouts = []
        for dl in dashboard.findall('.//device-layout'):
            device_type = dl.get('device-type', 'default')
            
            # Get zones visible in this device layout
            visible_zones = []
            for zone in dl.findall('.//zone'):
                zone_name = zone.get('name', '')
                if zone_name:
                    visible_zones.append({
                        'name': zone_name,
                        'position': {
                            'x': _safe_int(zone.get('x', 0)),
                            'y': _safe_int(zone.get('y', 0)),
                            'w': _safe_int(zone.get('w', 0)),
                            'h': _safe_int(zone.get('h', 0)),
                        }
                    })
            
            layouts.append({
                'device_type': device_type,  # phone, tablet, desktop
                'zones': visible_zones,
                'auto_generated': dl.get('auto-generated', 'false') == 'true',
            })
        return layouts
    
    def extract_theme(self, dashboard):
        """Extracts the theme (colors, fonts, custom color palettes) from the dashboard or workbook"""
        theme = {}
        
        # Palette colors from dashboard preferences
        for prefs in dashboard.findall('.//preferences'):
            colors = []
            for color in prefs.findall('.//color-palette/color'):
                if color.text:
                    colors.append(color.text)
            if colors:
                theme['color_palette'] = colors
        
        # Custom color palettes (named palettes)
        custom_palettes = {}
        for palette in dashboard.findall('.//color-palette'):
            palette_name = palette.get('name', '')
            palette_type = palette.get('type', '')
            palette_colors = []
            for color in palette.findall('.//color'):
                if color.text:
                    palette_colors.append(color.text)
            if palette_name and palette_colors:
                custom_palettes[palette_name] = {
                    'type': palette_type,
                    'colors': palette_colors,
                }
        if custom_palettes:
            theme['custom_palettes'] = custom_palettes
        
        # Global formatting style
        for style in dashboard.findall('.//style'):
            for rule in style.findall('.//style-rule'):
                elem = rule.get('element', '')
                for fmt in rule.findall('.//format'):
                    attrs = dict(fmt.attrib)
                    if attrs:
                        theme.setdefault('styles', {})[elem] = attrs
        
        # Font family from formatting
        for fmt in dashboard.findall('.//format[@attr="font-family"]'):
            theme['font_family'] = fmt.get('value', '')
        
        # Extract global workbook-level color palette from parent
        parent = dashboard
        for color_pal in parent.findall('.//preferences/color-palette'):
            pal_name = color_pal.get('name', 'default')
            pal_colors = [c.text for c in color_pal.findall('.//color') if c.text]
            if pal_colors:
                theme.setdefault('custom_palettes', {})[pal_name] = {
                    'type': color_pal.get('type', 'regular'),
                    'colors': pal_colors,
                }
        
        return theme
    
    def extract_allowable_values(self, param):
        """Extracts the allowed values for a parameter (list, range).
        Handles both old (<members><member>) and new (<domain><member>) formats.
        """
        result = []
        
        # List values — old format: <members><member>
        for member in param.findall('.//members/member'):
            val = member.get('value', '')
            alias = member.get('alias', val)
            if val:
                result.append({'value': val, 'alias': alias})
        
        # List values — new format: <domain><member>
        for member in param.findall('.//domain/member'):
            val = member.get('value', '')
            alias = member.get('alias', val)
            if val:
                # Strip surrounding quotes from string values (e.g., '"All"' → 'All')
                clean_val = val.strip('"')
                clean_alias = alias.strip('"') if alias else clean_val
                result.append({'value': clean_val, 'alias': clean_alias})
        
        # Range (min/max/step)
        range_elem = param.find('.//range')
        if range_elem is not None:
            min_val = range_elem.get('min', '')
            max_val = range_elem.get('max', '')
            step = range_elem.get('granularity', '')
            if min_val or max_val:
                result.append({
                    'type': 'range',
                    'min': min_val,
                    'max': max_val,
                    'step': step
                })
        
        return result
    
    def extract_story_points(self, story):
        """Extracts story points (= slides of a story)"""
        story_points = []
        for sp in story.findall('.//story-point'):
            caption = sp.get('captured-sheet', '')
            sp_data = {
                'caption': sp.findtext('.//caption', '') or caption,
                'captured_sheet': caption,
                'description': sp.findtext('.//description', ''),
                'filters_state': []
            }
            # Capture active filters at the time of the story point
            for filt in sp.findall('.//filter'):
                col = _strip_brackets(filt.get('column', ''))
                vals = [v.text for v in filt.findall('.//value') if v.text]
                if col:
                    sp_data['filters_state'].append({'field': col, 'values': vals})
            story_points.append(sp_data)
        return story_points
    
    def extract_worksheet_sort_orders(self, worksheet):
        """Extracts sort orders of a worksheet including computed sorts."""
        sorts = []
        for sort in worksheet.findall('.//sort'):
            col = _strip_brackets(sort.get('column', ''))
            direction = sort.get('direction', 'ASC')
            sort_entry = {'field': col, 'direction': direction.upper()}
            
            # Computed sort: sort by another field/measure
            sort_using = sort.get('using', '')
            if sort_using:
                sort_entry['sort_by'] = _strip_brackets(sort_using)
            
            # Sort type: alphabetic, manual, computed
            sort_type = sort.get('type', '')
            if sort_type:
                sort_entry['sort_type'] = sort_type
            
            sorts.append(sort_entry)
        return sorts
    
    def extract_mark_encoding(self, worksheet):
        """Extracts visual mark encodings (color, size, shape, label)"""
        encoding = {}
        
        for enc_elem in worksheet.findall('.//encodings'):
            # Use module-level _clean_field_ref for derivation prefix cleaning
            
            # Color
            color = enc_elem.find('.//color')
            if color is not None:
                column = color.get('column', '')
                palette = color.get('palette', '')
                col_refs = re.findall(r'\[([^\]]+)\]\.\[([^\]]+)\]', column)
                
                # Detect quantitative vs categorical color encoding
                # quantitative = `:qk` suffix or explicit `type="quantitative"`
                color_type = color.get('type', '')
                if not color_type and ':qk' in column:
                    color_type = 'quantitative'
                elif not color_type and ':nk' in column:
                    color_type = 'categorical'
                
                color_data = {
                    'field': _clean_field_ref(col_refs[0][1]) if col_refs else _strip_brackets(column),
                    'palette': palette,
                    'type': color_type,
                }
                
                # Extract palette colors from <color-palette> within the encoding
                palette_colors = []
                for cp in enc_elem.findall('.//color-palette/color'):
                    if cp.text:
                        palette_colors.append(cp.text)
                # Also check parent worksheet for palette-specific colors
                if not palette_colors:
                    for cp in worksheet.findall(f'.//color-palette[@name="{palette}"]/color'):
                        if cp.text:
                            palette_colors.append(cp.text)
                if palette_colors:
                    color_data['palette_colors'] = palette_colors
                
                # Stepped color thresholds from <bucket> elements
                thresholds = []
                for bucket in color.findall('.//bucket'):
                    thresh = {'color': bucket.get('color', '')}
                    val = bucket.get('value', bucket.get('low', ''))
                    if val:
                        try:
                            thresh['value'] = float(val)
                        except (ValueError, TypeError):
                            pass
                    if thresh.get('color'):
                        thresholds.append(thresh)
                if thresholds:
                    color_data['thresholds'] = thresholds
                
                # Legend position
                legend = color.find('.//legend')
                if legend is not None:
                    color_data['legend_position'] = legend.get('position', 'right')
                
                encoding['color'] = color_data
            
            # Size
            size = enc_elem.find('.//size')
            if size is not None:
                column = size.get('column', '')
                col_refs = re.findall(r'\[([^\]]+)\]\.\[([^\]]+)\]', column)
                encoding['size'] = {
                    'field': _clean_field_ref(col_refs[0][1]) if col_refs else _strip_brackets(column)
                }
            
            # Shape
            shape = enc_elem.find('.//shape')
            if shape is not None:
                column = shape.get('column', '')
                col_refs = re.findall(r'\[([^\]]+)\]\.\[([^\]]+)\]', column)
                encoding['shape'] = {
                    'field': _clean_field_ref(col_refs[0][1]) if col_refs else _strip_brackets(column)
                }
            
            # Label (with position, font, orientation)
            label = enc_elem.find('.//label')
            if label is not None:
                column = label.get('column', '')
                col_refs = re.findall(r'\[([^\]]+)\]\.\[([^\]]+)\]', column)
                show_labels = label.get('show-label', 'false') == 'true'
                encoding['label'] = {
                    'field': _clean_field_ref(col_refs[0][1]) if col_refs else _strip_brackets(column),
                    'show': show_labels,
                    'position': label.get('label-position', ''),  # top, center, bottom, left, right
                    'orientation': label.get('label-orientation', ''),  # horizontal, vertical, diagonal
                    'font_size': label.get('font-size', ''),
                    'font_weight': label.get('font-weight', ''),  # bold, normal
                    'font_color': label.get('font-color', ''),
                    'content_type': label.get('content-type', ''),  # value, percent, category
                }
        
        return encoding
    
    def extract_axes(self, worksheet):
        """Extracts axis configuration including continuous/discrete detection and dual-axis."""
        axes = {}
        axis_elements = worksheet.findall('.//axis')
        
        for axis in axis_elements:
            axis_type = axis.get('type', '')  # x, y
            
            # Detect continuous vs discrete
            # Continuous axes have numeric/date ranges; discrete have categories  
            is_continuous = axis.get('auto-range', 'true') != '' or axis.get('range-min') is not None
            
            axes[axis_type] = {
                'auto_range': axis.get('auto-range', 'true') == 'true',
                'range_min': axis.get('range-min', None),
                'range_max': axis.get('range-max', None),
                'scale': axis.get('scale', 'linear'),
                'title': axis.findtext('.//title', ''),
                'reversed': axis.get('reversed', 'false') == 'true',
                'continuous': is_continuous,
            }
        
        # Detect dual axis: multiple y-axis definitions or sync flag
        y_axes = [a for a in axis_elements if a.get('type') == 'y']
        if len(y_axes) > 1:
            axes['dual_axis'] = True
            # Check for synchronized dual axis (range synced)
            axes['dual_axis_sync'] = any(a.get('synchronized', 'false') == 'true' for a in y_axes)
        else:
            axes['dual_axis'] = False
            axes['dual_axis_sync'] = False
        
        return axes
    
    def extract_reference_lines(self, worksheet):
        """Extracts reference lines, bands, and distributions"""
        ref_lines = []
        for rl in worksheet.findall('.//reference-line'):
            # Value may be on the element or in a child <reference-line-value>
            value = rl.get('value', '')
            rl_vals = rl.findall('reference-line-value')
            if not value and rl_vals:
                value = rl_vals[0].get('value', '')
            # Label may be on the element or in a child <reference-line-label>
            label = rl.get('label', '')
            rl_lbl = rl.find('reference-line-label')
            if not label and rl_lbl is not None:
                label = rl_lbl.get('value', '')
            # Color fallback: element attribute or line-color
            line_color = rl.get('color', rl.get('line-color', '#666666'))
            # Detect band (2+ reference-line-value children = band)
            is_band = len(rl_vals) >= 2
            entry = {
                'type': 'band' if is_band else 'line',
                'value': value,
                'label': label,
                'label_type': rl.get('label-type', 'value'),
                'scope': rl.get('scope', ''),
                'axis': rl.get('axis', 'y'),
                'color': line_color,
                'line_color': line_color,
                'style': rl.get('style', rl.get('line-style', 'solid')),
                'computation': rl.get('computation', 'constant'),
                'field': rl.get('column', ''),
                'is_band': is_band,
            }
            if is_band:
                entry['value_from'] = rl_vals[0].get('value', rl_vals[0].get('column', ''))
                entry['value_to'] = rl_vals[1].get('value', rl_vals[1].get('column', ''))
            ref_lines.append(entry)
        for rb in worksheet.findall('.//reference-band'):
            ref_lines.append({
                'type': 'band',
                'value_from': rb.get('value-from', ''),
                'value_to': rb.get('value-to', ''),
                'label': rb.get('label', ''),
                'scope': rb.get('scope', 'per-pane'),
                'axis': rb.get('axis', 'y'),
                'color': rb.get('color', '#E0E0E0'),
                'fill_above': rb.get('fill-above', ''),
                'fill_below': rb.get('fill-below', ''),
            })
        for rd in worksheet.findall('.//reference-distribution'):
            ref_lines.append({
                'type': 'distribution',
                'computation': rd.get('computation', ''),
                'scope': rd.get('scope', 'per-pane'),
                'axis': rd.get('axis', 'y'),
                'color': rd.get('color', '#666666'),
                'label': rd.get('label', ''),
                'percentile': rd.get('percentile', ''),
            })
        return ref_lines
    
    def extract_annotations(self, worksheet):
        """Extracts annotations (text callouts on charts).
        
        Parses <annotation> elements containing point/area annotations with text.
        """
        annotations = []
        
        for ann in worksheet.findall('.//annotation'):
            ann_data = {
                'type': ann.get('type', 'point'),  # point, area, mark
                'text': '',
                'position': {},
            }
            
            # Annotation text
            formatted = ann.find('.//formatted-text')
            if formatted is not None:
                parts = []
                for run in formatted.findall('.//run'):
                    if run.text:
                        parts.append(run.text)
                ann_data['text'] = ''.join(parts)
            
            # Position
            pos = ann.find('.//point')
            if pos is not None:
                ann_data['position'] = {
                    'x': pos.get('x', '0'),
                    'y': pos.get('y', '0'),
                }
            
            if ann_data['text']:
                annotations.append(ann_data)
        
        return annotations
    
    def extract_workbook_actions(self, root):
        """Extracts actions at the workbook level (filter, highlight, url, navigate, param, set)"""
        actions = []
        
        for action in root.findall('.//action'):
            action_type = action.get('type', '')  # filter, highlight, url, sheet-navigate, param, set-value
            action_name = action.get('name', '')
            
            action_data = {
                'name': action_name,
                'type': action_type,
                'source_worksheets': [],
                'target_worksheets': [],
                'command': action.get('command', ''),
            }
            
            # Source sheets
            for source in action.findall('.//source'):
                ws = source.get('worksheet', '')
                if ws:
                    action_data['source_worksheets'].append(ws)
            
            # Target sheets
            for target in action.findall('.//target'):
                ws = target.get('worksheet', '')
                if ws:
                    action_data['target_worksheets'].append(ws)
            
            # URL action
            if action_type == 'url':
                action_data['url'] = action.get('url', '')
            
            # Clearing behavior (what happens when selection is cleared)
            clearing = action.get('clearing', '')
            if clearing:
                action_data['clearing'] = clearing
            run_on = action.get('run-on', action.get('activation', ''))
            if run_on:
                action_data['run_on'] = run_on
            
            # Filter action: filtered fields
            if action_type == 'filter':
                field_mappings = []
                for fm in action.findall('.//field-mapping'):
                    src = _strip_brackets(fm.get('source-field', ''))
                    tgt = _strip_brackets(fm.get('target-field', ''))
                    field_mappings.append({'source': src, 'target': tgt})
                action_data['field_mappings'] = field_mappings
            
            # Highlight action: field mappings
            if action_type == 'highlight':
                field_mappings = []
                for fm in action.findall('.//field-mapping'):
                    src = _strip_brackets(fm.get('source-field', ''))
                    tgt = _strip_brackets(fm.get('target-field', ''))
                    field_mappings.append({'source': src, 'target': tgt})
                if field_mappings:
                    action_data['field_mappings'] = field_mappings
            
            # Parameter action
            if action_type == 'param':
                action_data['parameter'] = action.get('param', '')
                action_data['source_field'] = _strip_brackets(action.get('source-field', ''))
            
            # Set-value action: parse target set details
            if action_type == 'set-value':
                set_elem = action.find('.//set')
                if set_elem is not None:
                    action_data['target_set'] = set_elem.get('name', '').replace('[', '').replace(']', '')
                    action_data['target_field'] = set_elem.get('field', '').replace('[', '').replace(']', '')
                    action_data['assign_behavior'] = set_elem.get('behavior', 'assign')
                # Also capture from attributes
                action_data['set_name'] = action.get('set', action.get('set-name', '')).replace('[', '').replace(']', '')
                action_data['set_field'] = action.get('set-field', '').replace('[', '').replace(']', '')

            actions.append(action_data)
        
        self.workbook_data['actions'] = actions
        print(f"  ✓ {len(actions)} actions extracted")
    
    def extract_sets(self, root):
        """Extracts sets (IN/OUT sets)"""
        sets = []
        
        for ds in root.findall('.//datasource'):
            for col in ds.findall('.//column'):
                # Sets have a set attribute or a <set> element
                set_elem = col.find('.//set')
                if set_elem is not None or '-set-' in col.get('name', ''):
                    set_data = {
                        'name': _strip_brackets(col.get('caption', col.get('name', ''))),
                        'raw_name': _strip_brackets(col.get('name', '')),
                        'datatype': col.get('datatype', 'boolean'),
                    }
                    
                    if set_elem is not None:
                        # Conditional set (formula)
                        formula = set_elem.get('formula', '')
                        if formula:
                            set_data['formula'] = formula
                        
                        # Set by list of members
                        members = []
                        for member in set_elem.findall('.//member'):
                            val = member.get('value', '')
                            if val:
                                members.append(val)
                        if members:
                            set_data['members'] = members
                    
                    sets.append(set_data)
        
        self.workbook_data['sets'] = sets
        print(f"  ✓ {len(sets)} sets extracted")
    
    def extract_groups(self, root):
        """Extracts manual groups (value grouping)
        
        Two types of Tableau groups:
        1. crossjoin/level-members: combined field
           → calculated columns concatenating the sources
        2. union/member: value grouping into categories
           → calculated columns with SWITCH
        """
        groups = []
        
        for ds in root.findall('.//datasource'):
            for group_elem in ds.findall('.//group'):
                group_name = _strip_brackets(group_elem.get('caption', group_elem.get('name', '')))
                if not group_name:
                    continue
                
                top_gf = group_elem.find('./groupfilter')
                if top_gf is None:
                    continue
                
                func = top_gf.get('function', '')
                
                if func == 'crossjoin':
                    # Combined Field — extract source fields
                    levels = []
                    for lm in group_elem.findall('.//groupfilter[@function="level-members"]'):
                        level = _strip_brackets(lm.get('level', ''))
                        # Clean all Tableau derivation prefixes (yr:, mn:, none:, etc.)
                        level = _clean_field_ref(level)
                        levels.append(level)
                    
                    groups.append({
                        'name': group_name,
                        'group_type': 'combined',
                        'source_fields': levels,
                        'source_field': '',
                        'members': {}
                    })
                
                elif func == 'union':
                    # Value grouping — extract members
                    source_field = ''
                    first_member = group_elem.find('.//groupfilter[@function="member"]')
                    if first_member is not None:
                        level = first_member.get('level', '')
                        source_field = _clean_field_ref(_strip_brackets(level))
                    
                    members = {}
                    for child_gf in top_gf.findall('./groupfilter'):
                        if child_gf.get('function') == 'union':
                            group_label = ''
                            group_values = []
                            for member_gf in child_gf.findall('./groupfilter'):
                                if member_gf.get('function') == 'member':
                                    member_val = member_gf.get('member', '')
                                    if member_gf.get('user:ui-marker') == 'true':
                                        group_label = member_gf.get('user:ui-marker-value', member_val)
                                    if member_val:
                                        group_values.append(member_val)
                            if not group_label and group_values:
                                group_label = group_values[0]
                            if group_label:
                                members[group_label] = group_values
                        elif child_gf.get('function') == 'member':
                            member_val = child_gf.get('member', '')
                            marker = child_gf.get('user:ui-marker-value', member_val)
                            if member_val:
                                if marker not in members:
                                    members[marker] = []
                                members[marker].append(member_val)
                    
                    groups.append({
                        'name': group_name,
                        'group_type': 'values',
                        'source_field': source_field,
                        'source_fields': [],
                        'members': members
                    })
                
                else:
                    # Other types — record as-is
                    groups.append({
                        'name': group_name,
                        'group_type': func or 'unknown',
                        'source_field': '',
                        'source_fields': [],
                        'members': {}
                    })
        
        self.workbook_data['groups'] = groups
        print(f"  ✓ {len(groups)} groups extracted")
    
    def extract_bins(self, root):
        """Extracts bins (intervals)"""
        bins = []
        
        for ds in root.findall('.//datasource'):
            for col in ds.findall('.//column'):
                bin_elem = col.find('.//bin')
                if bin_elem is not None:
                    bins.append({
                        'name': _strip_brackets(col.get('caption', col.get('name', ''))),
                        'source_field': _strip_brackets(bin_elem.get('source', '')),
                        'size': bin_elem.get('size', '10'),
                        'datatype': col.get('datatype', 'integer')
                    })
        
        self.workbook_data['bins'] = bins
        print(f"  ✓ {len(bins)} bins extracted")
    
    def extract_hierarchies(self, root):
        """Extracts hierarchies (drill-paths) from datasources"""
        hierarchies = []
        
        for ds in root.findall('.//datasource'):
            for drill_path in ds.findall('.//drill-path'):
                h_name = drill_path.get('name', '')
                levels = []
                for field in drill_path.findall('.//field'):
                    level_name = _strip_brackets(field.get('name', ''))
                    if level_name:
                        levels.append(level_name)
                
                if h_name and levels:
                    hierarchies.append({
                        'name': h_name,
                        'levels': levels
                    })
        
        self.workbook_data['hierarchies'] = hierarchies
        print(f"  ✓ {len(hierarchies)} hierarchies extracted")
    
    def extract_sort_orders(self, root):
        """Extracts global sort orders (datasource-level, manual, and computed sorts)"""
        sorts = []
        
        for ds in root.findall('.//datasource'):
            for sort in ds.findall('.//sort'):
                col = _strip_brackets(sort.get('column', ''))
                direction = sort.get('direction', 'ASC')
                sort_type = sort.get('type', 'data')  # data, manual, field, computed
                sort_data = {
                    'field': col,
                    'direction': direction.upper(),
                    'key': sort.get('key', ''),
                    'sort_type': sort_type,
                }
                # Manual sort: capture ordered values
                if sort_type == 'manual':
                    manual_values = []
                    for val in sort.findall('.//value'):
                        if val.text:
                            manual_values.append(val.text)
                    if manual_values:
                        sort_data['manual_values'] = manual_values
                # Computed sort: capture the expression
                if sort_type in ('computed', 'field'):
                    sort_data['sort_using'] = sort.get('sort-using', '')
                if col:
                    sorts.append(sort_data)
        
        self.workbook_data['sort_orders'] = sorts
        print(f"  ✓ {len(sorts)} sort orders extracted")
    
    def extract_aliases(self, root):
        """Extracts aliases (display name overrides for values)"""
        aliases = {}
        
        for ds in root.findall('.//datasource'):
            for col in ds.findall('.//column'):
                col_name = _strip_brackets(col.get('name', ''))
                aliases_elem = col.find('.//aliases')
                if aliases_elem is not None:
                    col_aliases = {}
                    for alias in aliases_elem.findall('.//alias'):
                        key = alias.get('key', '')
                        value = alias.get('value', '')
                        if key and value:
                            col_aliases[key] = value
                    if col_aliases:
                        aliases[col_name] = col_aliases
        
        self.workbook_data['aliases'] = aliases
        print(f"  ✓ {len(aliases)} columns with aliases extracted")
    
    def extract_custom_sql(self, root):
        """Extracts custom SQL queries from datasources"""
        custom_sql = []
        
        for ds in root.findall('.//datasource'):
            ds_name = ds.get('name', '')
            for relation in ds.findall('.//relation[@type=\"text\"]'):
                query = relation.text or ''
                if query.strip():
                    custom_sql.append({
                        'datasource': ds_name,
                        'name': relation.get('name', 'Custom SQL Query'),
                        'query': query.strip()
                    })
        
        self.workbook_data['custom_sql'] = custom_sql
        print(f"  ✓ {len(custom_sql)} custom SQL queries extracted")
    
    def extract_user_filters(self, root):
        """Extracts user filters and security-related calculations for RLS migration.
        
        Parses:
        1. <user-filter> elements (explicit user-to-row mappings)
        2. <group-filter> elements within user filters
        3. Calculations using USERNAME(), FULLNAME(), USERDOMAIN(), ISMEMBEROF()
        
        These are converted to Power BI Row-Level Security (RLS) roles.
        """
        user_filters = []
        
        # ---- 1. Explicit user filters (<user-filter> elements) ----
        for ds in root.findall('.//datasource'):
            ds_name = ds.get('caption', ds.get('name', ''))
            
            for uf in ds.findall('.//user-filter'):
                filter_name = _strip_brackets(uf.get('name', ''))
                filter_column = _strip_brackets(uf.get('column', ''))
                
                # Extract user-to-value mappings
                user_mappings = []
                for member in uf.findall('.//member'):
                    user = member.get('user', '')
                    value = member.get('value', '')
                    if user or value:
                        user_mappings.append({
                            'user': user,
                            'value': value
                        })
                
                # Extract group-filter if present
                group_filter = uf.find('.//groupfilter')
                gf_data = None
                if group_filter is not None:
                    gf_func = group_filter.get('function', '')
                    gf_member = group_filter.get('member', '')
                    gf_level = _strip_brackets(group_filter.get('level', ''))
                    gf_data = {
                        'function': gf_func,
                        'member': gf_member,
                        'level': gf_level
                    }
                
                if filter_name or filter_column:
                    user_filters.append({
                        'type': 'user_filter',
                        'name': filter_name,
                        'column': filter_column,
                        'datasource': ds_name,
                        'user_mappings': user_mappings,
                        'group_filter': gf_data
                    })
            
            # ---- 2. Calculation-based user filters ----
            # Look for calculations that reference USERNAME(), FULLNAME(), USERDOMAIN(), ISMEMBEROF()
            user_func_pattern = re.compile(
                r'\b(USERNAME|FULLNAME|USERDOMAIN|ISMEMBEROF)\s*\(', re.IGNORECASE
            )
            
            for col in ds.findall('.//column'):
                calc = col.find('.//calculation')
                if calc is not None:
                    formula = calc.get('formula', '')
                    if formula and user_func_pattern.search(formula):
                        col_name = _strip_brackets(col.get('caption', col.get('name', '')))
                        raw_name = _strip_brackets(col.get('name', ''))
                        
                        # Detect which user functions are used
                        functions_used = list(set(
                            m.upper() for m in user_func_pattern.findall(formula)
                        ))
                        
                        # Extract ISMEMBEROF group names if present
                        ismemberof_groups = re.findall(
                            r'ISMEMBEROF\s*\(\s*["\']([^"\']+)["\']\s*\)', formula, re.IGNORECASE
                        )
                        
                        user_filters.append({
                            'type': 'calculated_security',
                            'name': col_name,
                            'raw_name': raw_name,
                            'datasource': ds_name,
                            'formula': formula,
                            'functions_used': functions_used,
                            'ismemberof_groups': ismemberof_groups
                        })
        
        self.workbook_data['user_filters'] = user_filters
        print(f"  ✓ {len(user_filters)} user filters/security rules extracted")

    def extract_datasource_filters(self, root):
        """Extract data source-level (extract) filters baked into connections.

        These are filters defined on the data source itself (not on worksheets)
        and they restrict what data is imported.  In Tableau XML they appear as
        ``<filter>`` elements directly under ``<datasource>`` or inside
        ``<extract>``/``<connection>`` blocks, distinguished from worksheet
        filters by the ``class="categorical"``/``class="quantitative"``
        attribute and the ``column`` attribute referencing a fully-qualified
        field ``[datasource].[column]``.
        """
        ds_filters = []

        for ds in root.findall('.//datasource'):
            ds_name = ds.get('caption', ds.get('name', ''))
            ds_raw_name = ds.get('name', '')

            # 1. Top-level <filter> elements on the datasource
            for filt in ds.findall('./filter'):
                fdata = self._parse_datasource_filter(filt, ds_name)
                if fdata:
                    ds_filters.append(fdata)

            # 2. Filters inside <extract><connection>
            extract_el = ds.find('.//extract')
            if extract_el is not None:
                for filt in extract_el.findall('.//filter'):
                    fdata = self._parse_datasource_filter(filt, ds_name)
                    if fdata:
                        ds_filters.append(fdata)

            # 3. Filters inside <connection> (named/federated connections)
            for conn in ds.findall('.//connection'):
                for filt in conn.findall('./filter'):
                    fdata = self._parse_datasource_filter(filt, ds_name)
                    if fdata:
                        ds_filters.append(fdata)

        # Deduplicate by (datasource, column, type)
        seen = set()
        unique = []
        for f in ds_filters:
            key = (f['datasource'], f['column'], f['filter_class'])
            if key not in seen:
                seen.add(key)
                unique.append(f)

        self.workbook_data['datasource_filters'] = unique
        print(f"  [OK] {len(unique)} datasource-level filters extracted")

    @staticmethod
    def _parse_datasource_filter(filt_element, ds_name):
        """Parse a single ``<filter>`` element from a datasource context.

        Returns a dict or ``None`` if the element is not a meaningful
        datasource filter (e.g. missing column).
        """
        column = filt_element.get('column', '')
        if not column:
            return None

        # Clean brackets
        clean_col = _strip_brackets(column)

        filter_class = filt_element.get('class', '')  # categorical / quantitative
        filter_type = filt_element.get('type', '')      # e.g. included, excluded

        # Categorical values: <groupfilter member="..."> or <member> elements
        values = []
        for gf in filt_element.findall('.//groupfilter'):
            member = gf.get('member', '')
            if member:
                values.append(member)
        for member_el in filt_element.findall('.//member'):
            val = member_el.get('value', member_el.text or '')
            if val:
                values.append(val)
        # Plain <value> children (overlap with global filters format)
        for val_el in filt_element.findall('.//value'):
            if val_el.text:
                values.append(val_el.text)

        # Quantitative range
        range_min = None
        range_max = None
        min_el = filt_element.find('.//min')
        max_el = filt_element.find('.//max')
        if min_el is not None:
            range_min = min_el.get('value', min_el.text)
        if max_el is not None:
            range_max = max_el.get('value', max_el.text)

        return {
            'datasource': ds_name,
            'column': clean_col,
            'filter_class': filter_class,
            'filter_type': filter_type,
            'values': values,
            'range_min': range_min,
            'range_max': range_max,
        }

    # ── New extraction methods (ported from Fabric) ──────────────────────

    def extract_trend_lines(self, worksheet):
        """Extracts trend lines from a worksheet"""
        trend_lines = []
        for tl in worksheet.findall('.//trend-line'):
            trend_lines.append({
                'type': tl.get('type', 'linear'),
                'field': tl.get('column', ''),
                'color': tl.get('color', ''),
                'show_confidence': tl.get('show-confidence', 'false') == 'true',
                'show_equation': tl.get('show-equation', 'false') == 'true',
                'show_r_squared': tl.get('show-r-squared', 'false') == 'true',
                'per_color': tl.get('per-color', 'false') == 'true',
            })
        # Also check <trend-lines><trend-line> nested format
        for tl_container in worksheet.findall('.//trend-lines'):
            for tl in tl_container.findall('.//trend-line'):
                if not any(t.get('type') == tl.get('type', 'linear') for t in trend_lines):
                    trend_lines.append({
                        'type': tl.get('type', 'linear'),
                        'field': tl.get('column', ''),
                        'color': tl.get('color', ''),
                        'show_confidence': tl.get('show-confidence', 'false') == 'true',
                        'show_equation': tl.get('show-equation', 'false') == 'true',
                        'show_r_squared': tl.get('show-r-squared', 'false') == 'true',
                        'per_color': tl.get('per-color', 'false') == 'true',
                    })
        return trend_lines

    def extract_pages_shelf(self, worksheet):
        """Extracts the Pages shelf field (animation shelf in Tableau)"""
        pages = {}
        pages_elem = worksheet.find('.//pages')
        if pages_elem is not None and pages_elem.text:
            refs = re.findall(r'\[([^\]]+)\]\.\[([^\]]+)\]', pages_elem.text)
            if refs:
                pages['field'] = refs[0][1]
                pages['datasource'] = refs[0][0]
            else:
                pages['field'] = pages_elem.text.strip().replace('[', '').replace(']', '')
        return pages

    def extract_table_calcs(self, worksheet):
        """Extracts table calculation addressing/partitioning from <table-calc> elements"""
        table_calcs = []
        for tc in worksheet.findall('.//table-calc'):
            calc_data = {
                'field': tc.get('column', '').replace('[', '').replace(']', ''),
                'type': tc.get('type', ''),
                'ordering_type': tc.get('ordering-type', 'Rows'),
                'compute_using': [],
                'direction': tc.get('direction', ''),
                'at_level': tc.get('at-level', ''),
            }
            # Compute-using dimensions
            for dim in tc.findall('.//compute-using'):
                val = dim.text or dim.get('column', '')
                if val:
                    clean = val.strip().replace('[', '').replace(']', '')
                    calc_data['compute_using'].append(clean)
            # Also check <order-by> for secondary sort
            for ob in tc.findall('.//order-by'):
                field = ob.get('column', '').replace('[', '').replace(']', '')
                direction = ob.get('direction', 'ASC')
                calc_data.setdefault('order_by', []).append({
                    'field': field, 'direction': direction
                })
            table_calcs.append(calc_data)
        return table_calcs

    def extract_dashboard_containers(self, dashboard):
        """Extracts horizontal/vertical layout containers with nesting and padding"""
        containers = []
        for lc in dashboard.findall('.//layout-container'):
            orientation = lc.get('orientation', '')
            container = {
                'orientation': orientation,
                'name': lc.get('name', ''),
                'position': {
                    'x': _safe_int(lc.get('x', 0)),
                    'y': _safe_int(lc.get('y', 0)),
                    'w': _safe_int(lc.get('w', 0)),
                    'h': _safe_int(lc.get('h', 0)),
                },
                'padding': {
                    'top': _safe_int(lc.get('padding-top', lc.get('margin-top', 0))),
                    'bottom': _safe_int(lc.get('padding-bottom', lc.get('margin-bottom', 0))),
                    'left': _safe_int(lc.get('padding-left', lc.get('margin-left', 0))),
                    'right': _safe_int(lc.get('padding-right', lc.get('margin-right', 0))),
                },
                'children': [],
            }
            for child in lc:
                if child.tag == 'zone':
                    container['children'].append({
                        'type': 'zone',
                        'name': child.get('name', ''),
                        'position': {
                            'x': _safe_int(child.get('x', 0)),
                            'y': _safe_int(child.get('y', 0)),
                            'w': _safe_int(child.get('w', 0)),
                            'h': _safe_int(child.get('h', 0)),
                        }
                    })
            containers.append(container)
        return containers

    def extract_forecasting(self, worksheet):
        """Extracts forecast configuration from <forecast> elements."""
        forecasts = []
        for fc in worksheet.findall('.//forecast'):
            forecasts.append({
                'enabled': True,
                'periods': _safe_int(fc.get('forecast-forward', fc.get('periods', 5))),
                'periods_back': _safe_int(fc.get('forecast-backward', 0)),
                'prediction_interval': fc.get('prediction-interval', '95'),
                'ignore_last': fc.get('ignore-last', '0'),
                'model': fc.get('model', 'automatic'),
                'show_prediction_bands': fc.get('show-prediction-bands', 'true') == 'true',
                'fill_between': fc.get('fill-between', 'true') == 'true',
            })
        # Also check <forecast-model> fallback
        for fm in worksheet.findall('.//forecast-model'):
            if not forecasts:
                forecasts.append({
                    'enabled': True,
                    'periods': _safe_int(fm.get('periods', 5)),
                    'periods_back': 0,
                    'prediction_interval': fm.get('prediction-interval', '95'),
                    'ignore_last': '0',
                    'model': fm.get('model', 'automatic'),
                    'show_prediction_bands': True,
                    'fill_between': True,
                })
        return forecasts

    def extract_map_options(self, worksheet):
        """Extracts map configuration (washout, style, layers, pan/zoom)."""
        map_opts = {}
        mo = worksheet.find('.//map-options')
        if mo is not None:
            map_opts = {
                'washout': mo.get('washout', '0.0'),
                'style': mo.get('map-style', mo.get('style', 'normal')),
                'show_map_search': mo.get('show-map-search', 'false') == 'true',
                'pan_zoom': mo.get('pan-zoom', 'true') == 'true',
                'unit': mo.get('unit', 'miles'),
            }
            # Map layers
            layers = []
            for ml in mo.findall('.//map-layer'):
                layers.append({
                    'name': ml.get('name', ''),
                    'enabled': ml.get('enabled', 'true') == 'true',
                })
            if layers:
                map_opts['layers'] = layers
        # Also check for <mapsources>
        for ms in worksheet.findall('.//mapsources/mapsource'):
            if 'provider' not in map_opts:
                map_opts['provider'] = ms.get('provider', 'mapbox')
        return map_opts

    def extract_clustering(self, worksheet):
        """Extracts clustering configuration (no direct PBI equivalent)."""
        clusters = []
        for cl in worksheet.findall('.//cluster'):
            clusters.append({
                'num_clusters': cl.get('num-clusters', 'auto'),
                'variables': [v.get('column', '').replace('[', '').replace(']', '')
                              for v in cl.findall('.//variable') if v.get('column')],
                'seed': cl.get('seed', ''),
            })
        # Also check <cluster-analysis>
        for ca in worksheet.findall('.//cluster-analysis'):
            if not clusters:
                clusters.append({
                    'num_clusters': ca.get('num-clusters', 'auto'),
                    'variables': [],
                    'seed': ca.get('seed', ''),
                })
        return clusters

    def extract_dual_axis_sync(self, worksheet):
        """Detects dual-axis and synchronization settings."""
        dual_axis = {}
        axes = list(worksheet.findall('.//axis'))
        if len(axes) >= 2:
            dual_axis['enabled'] = True
            # Check for synchronized axes
            for axis in axes:
                if axis.get('synchronized', '') == 'true':
                    dual_axis['synchronized'] = True
                    break
            else:
                dual_axis['synchronized'] = False
        return dual_axis

    def extract_custom_shapes(self):
        """Extracts custom shape references from .twbx package.

        Also extracts binary shape files into ``<output_dir>/shapes/``
        so the generator can embed them as ``RegisteredResources/``.
        """
        shapes = []
        file_ext = os.path.splitext(self.tableau_file)[1].lower()
        if file_ext in ['.twbx', '.tdsx']:
            try:
                shapes_dir = os.path.join(self.output_dir, 'shapes')
                with zipfile.ZipFile(self.tableau_file, 'r') as z:
                    for name in z.namelist():
                        if '/Shapes/' in name or '/shapes/' in name:
                            filename = os.path.basename(name)
                            shapes.append({
                                'path': name,
                                'filename': filename,
                            })
                            # Extract binary shape file
                            if filename and not name.endswith('/'):
                                os.makedirs(shapes_dir, exist_ok=True)
                                target = os.path.join(shapes_dir, filename)
                                with z.open(name) as src, open(target, 'wb') as dst:
                                    dst.write(src.read())
            except (zipfile.BadZipFile, OSError, KeyError) as exc:
                logger.debug("Could not read shapes from archive: %s", exc)
        return shapes

    def extract_embedded_fonts(self):
        """Extracts embedded font references from .twbx package."""
        fonts = []
        file_ext = os.path.splitext(self.tableau_file)[1].lower()
        if file_ext in ['.twbx', '.tdsx']:
            try:
                with zipfile.ZipFile(self.tableau_file, 'r') as z:
                    for name in z.namelist():
                        lower_name = name.lower()
                        if lower_name.endswith(('.ttf', '.otf', '.woff', '.woff2')):
                            fonts.append({
                                'path': name,
                                'filename': os.path.basename(name),
                                'format': os.path.splitext(name)[1].lstrip('.'),
                            })
            except (zipfile.BadZipFile, OSError, KeyError) as exc:
                logger.debug("Could not read fonts from archive: %s", exc)
        return fonts

    def extract_custom_geocoding(self, root):
        """Extracts custom geocoding CSV references."""
        geocoding = []
        for geo in root.findall('.//geocoding'):
            for role in geo.findall('.//geographic-role'):
                geocoding.append({
                    'role': role.get('name', ''),
                    'field': role.get('field', ''),
                })
        # Also look for custom geocoding files in .twbx
        file_ext = os.path.splitext(self.tableau_file)[1].lower()
        if file_ext in ['.twbx', '.tdsx']:
            try:
                with zipfile.ZipFile(self.tableau_file, 'r') as z:
                    for name in z.namelist():
                        if 'geocoding' in name.lower() and name.endswith('.csv'):
                            geocoding.append({
                                'type': 'custom_file',
                                'path': name,
                            })
            except (zipfile.BadZipFile, OSError, KeyError) as exc:
                logger.debug("Could not read geocoding from archive: %s", exc)
        self.workbook_data['custom_geocoding'] = geocoding
        print(f"  ✓ {len(geocoding)} custom geocoding refs extracted")

    def extract_published_datasources(self, root):
        """Extracts references to published (server-hosted) datasources."""
        pub_ds = []
        for ds in root.findall('.//datasource'):
            # Published datasources have a repository-location attribute
            repo = ds.find('.//repository-location')
            if repo is not None:
                pub_ds.append({
                    'name': ds.get('caption', ds.get('name', '')),
                    'server': repo.get('site', ''),
                    'path': repo.get('path', ''),
                    'id': repo.get('id', ''),
                    'derived_from': repo.get('derived-from', ''),
                })
            # Also check for <connection class="sqlproxy"> (published DS indicator)
            for conn in ds.findall('.//connection[@class="sqlproxy"]'):
                if not any(p['name'] == ds.get('caption', '') for p in pub_ds):
                    pub_ds.append({
                        'name': ds.get('caption', ds.get('name', '')),
                        'server': conn.get('server', ''),
                        'path': conn.get('dbname', ''),
                        'id': '',
                        'derived_from': '',
                    })
        self.workbook_data['published_datasources'] = pub_ds
        print(f"  ✓ {len(pub_ds)} published datasource refs extracted")

    def extract_data_blending(self, root):
        """Extracts data blending link fields between primary and secondary datasources."""
        blending = []
        for ds in root.findall('.//datasource'):
            ds_name = ds.get('caption', ds.get('name', ''))
            # Data blending relationships appear as <relation join="..."> cross-datasource
            for col in ds.findall('.//column'):
                link = col.find('.//link')
                if link is not None:
                    expression = link.get('expression', '')
                    key = link.get('key', '')
                    blending.append({
                        'datasource': ds_name,
                        'column': col.get('name', '').replace('[', '').replace(']', ''),
                        'link_expression': expression,
                        'link_key': key,
                    })
            # Also check <datasource-dependencies> for cross-ds links
            for dep in ds.findall('.//datasource-dependencies'):
                dep_ds = dep.get('datasource', '')
                for col in dep.findall('.//column'):
                    col_name = col.get('name', '').replace('[', '').replace(']', '')
                    if dep_ds and col_name:
                        # Check if this is a blending key
                        key = col.get('key', '')
                        if key or dep_ds != ds.get('name', ''):
                            if not any(b['column'] == col_name and b['datasource'] == ds_name for b in blending):
                                blending.append({
                                    'datasource': ds_name,
                                    'secondary_datasource': dep_ds,
                                    'column': col_name,
                                    'link_expression': '',
                                    'link_key': key,
                                })
        self.workbook_data['data_blending'] = blending
        print(f"  ✓ {len(blending)} data blending links extracted")

    def extract_hyper_metadata(self):
        """Extracts .hyper file metadata from .twbx packages (file names, sizes, and column info).

        Reads the first bytes of each ``.hyper`` file to detect the Hyper
        format signature and extract table/column metadata when possible.
        When INSERT statements are present in the header region, sample
        data rows are also extracted (up to ``max_sample_rows`` per table).

        Column type mapping: 0=bool, 1=bigint, 2=smallint, 3=int, 4=double,
        5=oid, 6=bytes, 7=text, 8=varchar, 9=char, 10=json, 11=date,
        12=interval, 13=time, 14=timestamp, 15=timestamptz, 16=geography,
        17=numeric.
        """
        # Hyper type-id → friendly name
        _hyper_type_map = {
            0: 'boolean', 1: 'bigint', 2: 'smallint', 3: 'integer',
            4: 'double', 5: 'oid', 6: 'bytes', 7: 'text', 8: 'varchar',
            9: 'char', 10: 'json', 11: 'date', 12: 'interval', 13: 'time',
            14: 'timestamp', 15: 'timestamptz', 16: 'geography', 17: 'numeric',
        }
        max_sample_rows = 5  # number of sample rows to extract per table

        hyper_files = []
        file_ext = os.path.splitext(self.tableau_file)[1].lower()
        if file_ext in ['.twbx', '.tdsx']:
            try:
                with zipfile.ZipFile(self.tableau_file, 'r') as z:
                    for info in z.infolist():
                        if info.filename.lower().endswith('.hyper'):
                            entry = {
                                'path': info.filename,
                                'filename': os.path.basename(info.filename),
                                'size_bytes': info.file_size,
                                'compressed_size': info.compress_size,
                            }
                            # Attempt to parse header for column metadata
                            try:
                                raw = z.read(info.filename)
                                header_str = raw[:min(4096, len(raw))]
                                # Detect format signature
                                if header_str[:4] == b'HyPe':
                                    entry['format'] = 'hyper'
                                elif header_str[:6] == b'SQLite':
                                    entry['format'] = 'sqlite'
                                # Scan a larger region for SQL patterns
                                scan_limit = min(262144, len(raw))
                                text_region = raw[:scan_limit]
                                try:
                                    text_chunk = text_region.decode('utf-8', errors='replace')
                                except (UnicodeDecodeError, AttributeError):
                                    text_chunk = ''
                                creates = re.findall(
                                    r'CREATE\s+TABLE\s+"?([^"\s(]+)"?\s*\(([^)]+)\)',
                                    text_chunk, re.IGNORECASE
                                )
                                if creates:
                                    tables_info = []
                                    for tname, cols_str in creates:
                                        cols = []
                                        for col_def in cols_str.split(','):
                                            col_def = col_def.strip()
                                            parts = col_def.split()
                                            if len(parts) >= 2:
                                                cname = parts[0].strip('"')
                                                ctype = ' '.join(parts[1:]).lower()
                                                cols.append({
                                                    'name': cname,
                                                    'hyper_type': ctype,
                                                })
                                        tbl_entry = {
                                            'table': tname,
                                            'columns': cols,
                                            'column_count': len(cols),
                                        }
                                        # --- Sample-row extraction ---
                                        samples = self._extract_hyper_sample_rows(
                                            text_chunk, tname, cols, max_sample_rows
                                        )
                                        if samples:
                                            tbl_entry['sample_rows'] = samples
                                            tbl_entry['sample_row_count'] = len(samples)
                                        tables_info.append(tbl_entry)
                                    entry['tables'] = tables_info
                                # Estimate row count from file size and column count
                                if entry.get('tables'):
                                    tbl0 = entry['tables'][0]
                                    ncols = tbl0.get('column_count', 1)
                                    avg_bytes_per_col = 20
                                    estimated = entry['size_bytes'] // max(ncols * avg_bytes_per_col, 1)
                                    entry['estimated_row_count'] = max(estimated, 0)
                            except Exception as exc:
                                logger.debug("Could not parse hyper header: %s", exc)
                            hyper_files.append(entry)
            except (zipfile.BadZipFile, OSError, KeyError) as exc:
                logger.debug("Could not read hyper files from archive: %s", exc)
        self.workbook_data['hyper_files'] = hyper_files
        if hyper_files:
            total_tables = sum(len(h.get('tables', [])) for h in hyper_files)
            total_rows = sum(
                h.get('estimated_row_count', 0, ) for h in hyper_files
            )
            msg = f"  ✓ {len(hyper_files)} .hyper extract files detected"
            if total_tables:
                msg += f" ({total_tables} tables parsed)"
            if total_rows:
                msg += f" (~{total_rows:,} rows estimated)"
            print(msg)

        # Attempt deeper reading via SQLite (hyper_reader module)
        file_ext = os.path.splitext(self.tableau_file)[1].lower()
        if file_ext in ['.twbx', '.tdsx']:
            try:
                deep_results = read_hyper_from_twbx(
                    self.tableau_file, max_rows=20,
                )
                if deep_results:
                    # Merge deep data (actual row counts, richer sample rows)
                    deep_map = {}
                    for dr in deep_results:
                        key = dr.get('original_filename', '')
                        deep_map[key] = dr
                    for entry in hyper_files:
                        fname = entry.get('filename', '')
                        deep = deep_map.get(fname)
                        if deep and deep.get('tables'):
                            entry['hyper_reader_tables'] = deep['tables']
                            entry['hyper_reader_format'] = deep.get('format', 'unknown')
                            # Update row count from actual COUNT(*)
                            total = sum(
                                t.get('row_count', 0) for t in deep['tables']
                            )
                            if total > 0:
                                entry['actual_row_count'] = total
                    logger.debug("Hyper reader enriched %d file(s)", len(deep_results))
            except Exception as exc:
                logger.debug("Hyper reader enrichment failed: %s", exc)

    # ------------------------------------------------------------------
    # Helpers for Hyper sample-row extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_hyper_sample_rows(text_chunk, table_name, columns, max_rows):
        """Extract sample data rows from INSERT statements in a Hyper text region.

        Some Hyper files contain SQL-style INSERT statements in their
        headers.  This method scans for ``INSERT INTO "table" VALUES
        (...)`` patterns and returns up to *max_rows* dicts mapping
        column names to string values.

        Args:
            text_chunk: The decoded text region of the .hyper file.
            table_name: The target table name (matched against INSERT).
            columns: Column info list, each with a 'name' key.
            max_rows: Maximum sample rows to return.

        Returns:
            list[dict]: Up to *max_rows* dicts ``{col_name: value}``.
        """
        # Escape table name for regex
        esc_name = re.escape(table_name)
        # Match INSERT INTO "table" VALUES (...), (...)
        insert_pat = re.compile(
            r'INSERT\s+INTO\s+"?' + esc_name + r'"?\s+VALUES\s*'
            r'(\([^)]*\)(?:\s*,\s*\([^)]*\))*)',
            re.IGNORECASE,
        )
        col_names = [c.get('name', f'col{i}') for i, c in enumerate(columns)]
        samples = []
        for m in insert_pat.finditer(text_chunk):
            values_block = m.group(1)
            # Split into individual value tuples
            tuples = re.findall(r'\(([^)]*)\)', values_block)
            for tup in tuples:
                vals = _split_sql_values(tup)
                row = {}
                for i, v in enumerate(vals):
                    name = col_names[i] if i < len(col_names) else f'col{i}'
                    row[name] = v.strip().strip("'")
                samples.append(row)
                if len(samples) >= max_rows:
                    return samples
        # Fallback: try to detect CSV-like or TSV-like data blocks
        if not samples:
            samples = _scan_delimited_sample(text_chunk, col_names, max_rows)
        return samples

    def extract_totals_subtotals(self, worksheet):
        """Extracts grand-total and sub-total settings from a worksheet."""
        totals = {'grand_totals': [], 'subtotals': []}
        for gt in worksheet.findall('.//grandtotals/grand-total'):
            totals['grand_totals'].append({
                'type': gt.get('type', ''),
                'position': gt.get('position', ''),
                'enabled': gt.get('enabled', 'true') == 'true',
            })
        for st in worksheet.findall('.//subtotals/subtotal'):
            totals['subtotals'].append({
                'type': st.get('type', ''),
                'position': st.get('position', ''),
                'enabled': st.get('enabled', 'true') == 'true',
            })
        # Also check <rows-total> and <cols-total> shorthand
        for tag in ['rows-total', 'cols-total']:
            el = worksheet.find(f'.//{tag}')
            if el is not None:
                totals['grand_totals'].append({
                    'type': tag.replace('-total', ''),
                    'position': el.get('position', 'bottom'),
                    'enabled': el.get('enabled', 'true') == 'true',
                })
        return totals

    def extract_worksheet_description(self, worksheet):
        """Extracts the description/caption text of a worksheet."""
        desc = worksheet.get('description', '')
        if not desc:
            desc_el = worksheet.find('.//description')
            if desc_el is not None:
                desc = desc_el.text or ''
        return desc

    def extract_show_hide_headers(self, worksheet):
        """Extracts show/hide header settings for rows and columns."""
        headers = {'rows': True, 'columns': True}
        style = worksheet.find('.//style')
        if style is not None:
            show_row = style.get('show-row-headers', 'true')
            show_col = style.get('show-col-headers', 'true')
            headers['rows'] = show_row == 'true'
            headers['columns'] = show_col == 'true'
        # Alternative: table/view element
        table = worksheet.find('.//table')
        if table is not None:
            if table.get('show-header') == 'false':
                headers['rows'] = False
                headers['columns'] = False
        return headers

    def extract_dynamic_title(self, worksheet):
        """Extracts dynamic title info — detects field references in title text."""
        title_el = worksheet.find('.//title')
        if title_el is None:
            return None
        runs = title_el.findall('.//run')
        parts = []
        is_dynamic = False
        for run in runs:
            text = run.text or ''
            # Check for field reference
            field_ref = run.find('.//field')
            if field_ref is not None:
                ref_name = field_ref.get('name', field_ref.text or '')
                parts.append({'type': 'field', 'value': ref_name})
                is_dynamic = True
            else:
                # Check for <pageField> or parameter reference in text
                if '<' in text or '[' in text:
                    is_dynamic = True
                parts.append({'type': 'text', 'value': text})
        if not parts:
            # Fallback: read raw text
            title_text = ''.join(title_el.itertext())
            if title_text:
                parts.append({'type': 'text', 'value': title_text})
        return {'is_dynamic': is_dynamic, 'parts': parts} if parts else None

    def extract_show_hide_containers(self, dashboard):
        """Extracts show/hide button containers from a dashboard."""
        containers = []
        for zone in dashboard.findall('.//zone'):
            btn = zone.find('.//show-hide-button')
            if btn is not None:
                containers.append({
                    'zone_name': zone.get('name', ''),
                    'zone_id': zone.get('id', ''),
                    'default_state': btn.get('default-state', 'show'),
                    'button_style': btn.get('style', ''),
                })
        return containers

    def extract_dynamic_zone_visibility(self, dashboard):
        """Extracts dynamic zone visibility settings (Tableau 2024.3+).

        Dynamic zone visibility allows zones to show/hide based on a parameter
        or calculated field value. In PBI this maps to bookmark toggle groups.
        """
        zones = []
        for zone in dashboard.findall('.//zone'):
            dz = zone.find('.//dynamic-zone-visibility')
            if dz is None:
                dz = zone.find('dynamic-zone-visibility')
            if dz is not None:
                zones.append({
                    'zone_name': zone.get('name', ''),
                    'zone_id': zone.get('id', ''),
                    'field': dz.get('field', dz.get('column', '')),
                    'value': dz.get('value', ''),
                    'condition': dz.get('condition', 'equals'),
                    'default_visible': dz.get('default', 'true') == 'true',
                })
        return zones

    def extract_floating_tiled(self, dashboard):
        """Extracts floating vs tiled layout info for each dashboard zone."""
        layout_info = []
        for zone in dashboard.findall('.//zone'):
            is_floating = zone.get('is-floating', 'false') == 'true'
            layout_info.append({
                'zone_name': zone.get('name', ''),
                'zone_id': zone.get('id', ''),
                'is_floating': is_floating,
                'x': _safe_int(zone.get('x', 0)),
                'y': _safe_int(zone.get('y', 0)),
                'w': _safe_int(zone.get('w', 0)),
                'h': _safe_int(zone.get('h', 0)),
            })
        return layout_info

    def extract_analytics_pane_stats(self, worksheet):
        """Extracts analytics pane statistics (mean, median, CI, distribution bands)."""
        stats = []
        # Analytics pane objects appear as <stat-line>, <distribution-band>, etc.
        for stat_line in worksheet.findall('.//stat-line'):
            stats.append({
                'type': 'stat_line',
                'stat': stat_line.get('stat', ''),
                'scope': stat_line.get('scope', 'per-pane'),
                'value': stat_line.get('value', ''),
            })
        for band in worksheet.findall('.//distribution-band'):
            stats.append({
                'type': 'distribution_band',
                'computation': band.get('computation', ''),
                'value_from': band.get('value-from', ''),
                'value_to': band.get('value-to', ''),
                'scope': band.get('scope', 'per-pane'),
            })
        for ci in worksheet.findall('.//confidence-interval'):
            stats.append({
                'type': 'confidence_interval',
                'level': ci.get('level', '95'),
                'scope': ci.get('scope', 'per-pane'),
            })
        # Average/median/constant lines from <reference-line>
        for ref in worksheet.findall('.//reference-line'):
            comp = ref.get('computation', '')
            if comp in ('mean', 'median', 'mode', 'constant', 'percentile', 'quantile'):
                stats.append({
                    'type': 'stat_reference',
                    'computation': comp,
                    'value': ref.get('value', ''),
                    'scope': ref.get('scope', 'per-pane'),
                })
        return stats

    def save_extractions(self):
        """Saves extractions to JSON"""
        
        for obj_type, data in self.workbook_data.items():
            output_path = os.path.join(self.output_dir, f'{obj_type}.json')
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"  → {output_path}")


def main():
    """Main entry point"""
    
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python extract_tableau_data.py <tableau_file.twbx>")
        sys.exit(1)
    
    tableau_file = sys.argv[1]
    
    if not os.path.exists(tableau_file):
        print(f"❌ File not found: {tableau_file}")
        sys.exit(1)
    
    extractor = TableauExtractor(tableau_file)
    extractor.extract_all()


if __name__ == '__main__':
    main()
