"""
Script for extracting Tableau objects from .twb, .twbx, .tds, .tdsx files

This script extracts metadata and structures from Tableau workbooks
and exports them in JSON format for conversion to Power BI.
"""

import os
import sys
import json
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
import re
from datasource_extractor import extract_datasource

# Ensure Unicode output on Windows consoles (✓, →, ❌, etc.)
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


# ── Pre-compiled shared regex patterns ────────────────────────────────────────

_RE_FIELD_REF = re.compile(r'\[([^\]]+)\]\.\[([^\]]+)\]')
_RE_DERIVATION_PREFIX = re.compile(
    r'^(none|sum|avg|count|min|max|usr|yr|mn|dy|qr|wk|attr|md|mdy|hms|hr|mt|sc|thr|trunc):'
)
_RE_TYPE_SUFFIX = re.compile(r':(nk|qk|ok|fn|tn)$')


def _strip_brackets(s):
    """Remove Tableau bracket notation from a field/table name."""
    return s.replace('[', '').replace(']', '')


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
                    'width': int(dashboard.get('width', 1280)),
                    'height': int(dashboard.get('height', 720)),
                },
                'objects': self.extract_dashboard_objects(dashboard),
                'filters': self.extract_dashboard_filters(dashboard),
                'parameters': self.extract_dashboard_parameters(dashboard),
                'theme': self.extract_theme(dashboard),
                'layout_containers': self.extract_layout_containers(dashboard),
                'device_layouts': self.extract_device_layouts(dashboard),
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
        """Extracts calculated fields - now integrated in enhanced datasource extraction"""
        
        # Calculations are now extracted directly in extract_datasource
        # This method maintains backward compatibility
        calculations = []
        
        for datasource in root.findall('.//datasource'):
            ds_data = extract_datasource(datasource, twbx_path=self.tableau_file)
            calculations.extend(ds_data.get('calculations', []))
        
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
                'values': [v.text for v in filt.findall('.//value')],
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
                      'datetime', 'timestamp', 'period', 'yr', 'mois'}
        measure_words = {'sales', 'profit', 'revenue', 'amount', 'quantity', 'qty',
                         'count', 'sum', 'total', 'price', 'cost', 'margin',
                         'budget', 'forecast', 'actual', 'target', 'value',
                         'weight', 'height', 'distance', 'rate', 'ratio',
                         'score', 'index', 'number', 'num', 'avg', 'average'}
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
                    clean = re.sub(r'^(none|sum|avg|count|min|max|usr|yr|mn|dy|qr|wk|attr|md|mdy|hms|hr|mt|sc|thr|trunc):', '', field_ref)
                    clean = re.sub(r':(nk|qk|ok|fn|tn)$', '', clean)
                    clean = re.sub(r'^(pcto|pctd|diff|running_sum|running_avg|running_count|running_min|running_max|rank|rank_unique|rank_dense):(sum|avg|count|min|max|countd)?:?', '', clean)
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
            'Polygon': 'filledMap',
            'Multipolygon': 'filledMap',
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
                refs = re.findall(r'\[([^\]]+)\]\.\[([^\]]+)\]', shelf.text)
                for ds_ref, field_ref in refs:
                    # Detect quick table calc prefix before cleaning
                    table_calc_match = re.match(table_calc_re, field_ref)
                    table_calc_type = None
                    table_calc_agg = None
                    if table_calc_match:
                        table_calc_type = table_calc_match.group(1)
                        table_calc_agg = table_calc_match.group(2) or 'sum'
                    
                    # Clean the field name (remove derivation prefix and type suffix)
                    clean_name = re.sub(table_calc_re, '', field_ref)
                    clean_name = re.sub(derivation_re, '', clean_name)
                    clean_name = re.sub(suffix_re, '', clean_name)
                    
                    field_data = {
                        'name': clean_name,
                        'shelf': shelf_name,
                        'datasource': ds_ref
                    }
                    if table_calc_type:
                        field_data['table_calc'] = table_calc_type
                        field_data['table_calc_agg'] = table_calc_agg
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
                clean_name = re.sub(r'^(none|sum|avg|count|min|max):', '', field_ref)
                clean_name = re.sub(r':(nk|qk|ok|fn|tn)$', '', clean_name)
            else:
                ds_ref = ''
                clean_name = _strip_brackets(column_ref)
            
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
                    filter_type = 'range'
                    from_val = groupfilter.get('from', '')
                    to_val = groupfilter.get('to', '')
                    filter_min = from_val if from_val else None
                    filter_max = to_val if to_val else None
                elif func == 'level-members':
                    filter_type = 'all'  # filter "all selected"
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
                'include_null': include_null
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
        """Extracts tooltips (fields and viz-in-tooltip)"""
        tooltips = []
        
        # Text tooltip from <formatted-text>
        for tooltip_elem in worksheet.findall('.//tooltip'):
            formatted = tooltip_elem.find('.//formatted-text')
            if formatted is not None:
                # Reconstruct the text
                parts = []
                for run in formatted.findall('.//run'):
                    if run.text:
                        parts.append(run.text)
                if parts:
                    tooltips.append({'type': 'text', 'content': ''.join(parts)})
            
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
                'x': int(zone.get('x', 0)),
                'y': int(zone.get('y', 0)),
                'w': int(zone.get('w', 300)),
                'h': int(zone.get('h', 200)),
            }
            
            layout_mode = 'floating' if is_floating else ('fixed' if is_fixed else 'tiled')
            
            # Extract padding/margins from zone-style
            padding = {}
            zone_style = zone.find('.//zone-style')
            if zone_style is not None:
                for fmt in zone_style.findall('.//format'):
                    attr = fmt.get('attr', '')
                    val = fmt.get('value', '')
                    if attr in ('padding-left', 'padding-right', 'padding-top', 'padding-bottom',
                                'margin-left', 'margin-right', 'margin-top', 'margin-bottom'):
                        try:
                            padding[attr] = int(val)
                        except (ValueError, TypeError):
                            pass
                    elif attr == 'border-style':
                        padding['border_style'] = val
                    elif attr == 'border-color':
                        padding['border_color'] = val
                    elif attr == 'border-width':
                        try:
                            padding['border_width'] = int(val)
                        except (ValueError, TypeError):
                            pass
            
            # Texte
            if zone_type == 'text' or zone.get('type-v2') == 'text':
                text_content = ''
                formatted = zone.find('.//formatted-text')
                if formatted is not None:
                    parts = []
                    for run in formatted.findall('.//run'):
                        if run.text:
                            parts.append(run.text)
                    text_content = ''.join(parts)
                objects.append({
                    'type': 'text',
                    'name': zone_name or f'text_{zone_id}',
                    'content': text_content,
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
                objects.append({
                    'type': 'worksheetReference',
                    'name': zone_name,
                    'worksheetName': zone_name,
                    'position': pos,
                    'layout': layout_mode,
                    'padding': padding,
                })
        
        return objects
    
    def extract_dashboard_filters(self, dashboard):
        """Extracts dashboard filters from <filter> elements"""
        filters = []
        for filt in dashboard.findall('.//filter'):
            column_ref = filt.get('column', '')
            col_match = re.findall(r'\[([^\]]+)\]\.\[([^\]]+)\]', column_ref)
            if col_match:
                ds_ref, field_ref = col_match[0]
                clean_name = re.sub(r'^(none|sum|avg|count|min|max):', '', field_ref)
                clean_name = re.sub(r':(nk|qk|ok|fn|tn)$', '', clean_name)
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
                        'x': int(zone.get('x', 0)),
                        'y': int(zone.get('y', 0)),
                        'w': int(zone.get('w', 200)),
                        'h': int(zone.get('h', 30)),
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
                    'x': int(lc.get('x', 0)),
                    'y': int(lc.get('y', 0)),
                    'w': int(lc.get('w', 0)),
                    'h': int(lc.get('h', 0)),
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
                            'x': int(zone.get('x', 0)),
                            'y': int(zone.get('y', 0)),
                            'w': int(zone.get('w', 0)),
                            'h': int(zone.get('h', 0)),
                        }
                    })
            
            layouts.append({
                'device_type': device_type,  # phone, tablet, desktop
                'zones': visible_zones,
                'auto_generated': dl.get('auto-generated', 'false') == 'true',
            })
        return layouts
    
    def extract_theme(self, dashboard):
        """Extracts the theme (colors, fonts) from the dashboard or workbook"""
        theme = {}
        
        # Palette colors
        for prefs in dashboard.findall('.//preferences'):
            colors = []
            for color in prefs.findall('.//color-palette/color'):
                if color.text:
                    colors.append(color.text)
            if colors:
                theme['color_palette'] = colors
        
        # Global formatting style
        for style in dashboard.findall('.//style'):
            for rule in style.findall('.//style-rule'):
                elem = rule.get('element', '')
                fmt = rule.find('.//format')
                if fmt is not None and elem:
                    attrs = dict(fmt.attrib)
                    theme.setdefault('styles', {})[elem] = attrs
        
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
            # Helper to clean Tableau derivation prefixes from field refs
            def _clean_field_ref(raw):
                clean = re.sub(r'^(none|sum|avg|count|min|max|usr|yr|mn|dy|qr|wk|attr|md|mdy|hms|hr|mt|sc|thr|trunc):', '', raw)
                return re.sub(r':(nk|qk|ok|fn|tn)$', '', clean)
            
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
                
                encoding['color'] = {
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
                    encoding['color']['palette_colors'] = palette_colors
            
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
        """Extracts reference lines, bands, and analytics pane items.
        
        Parses <reference-line> elements which contain constant lines,
        average/median lines, trend lines, and reference bands.
        """
        ref_lines = []
        
        for ref in worksheet.findall('.//reference-line'):
            ref_data = {
                'scope': ref.get('scope', 'per-pane'),  # per-pane, per-cell, per-table
                'value_column': '',
                'value': None,
                'label': '',
                'label_type': ref.get('label-type', 'value'),  # value, computation, custom, none
                'line_style': ref.get('line-style', 'dashed'),
                'line_color': '',
                'line_thickness': ref.get('line-thickness', '1'),
                'fill_above': ref.get('fill-above', ''),
                'fill_below': ref.get('fill-below', ''),
                'computation': ref.get('computation', 'constant'),  # constant, average, median, sum, min, max, total, percentile, quantile
            }
            
            # Value (constant or formula)
            value_elem = ref.find('.//reference-line-value')
            if value_elem is not None:
                ref_data['value_column'] = value_elem.get('column', '')
                ref_data['value'] = value_elem.get('value', value_elem.text)
            
            # Second value (for reference bands — range between two values)
            value_elems = ref.findall('.//reference-line-value')
            if len(value_elems) >= 2:
                ref_data['is_band'] = True
                ref_data['value2_column'] = value_elems[1].get('column', '')
                ref_data['value2'] = value_elems[1].get('value', value_elems[1].text)
            else:
                ref_data['is_band'] = bool(ref_data['fill_above'] or ref_data['fill_below'])
            
            # Label
            label_elem = ref.find('.//reference-line-label')
            if label_elem is not None:
                ref_data['label'] = label_elem.get('value', label_elem.text or '')
            
            # Style
            style_elem = ref.find('.//format')
            if style_elem is not None:
                ref_data['line_color'] = style_elem.get('color', style_elem.get('stroke-color', ''))
                ref_data['line_style'] = style_elem.get('stroke-style', ref_data['line_style'])
            
            # Also check for color at top level
            if not ref_data['line_color']:
                ref_data['line_color'] = ref.get('color', '#666666')
            
            ref_lines.append(ref_data)
        
        # Also check for trend lines
        for trend in worksheet.findall('.//trend-line'):
            ref_lines.append({
                'scope': 'per-pane',
                'computation': 'trend',
                'trend_type': trend.get('type', 'linear'),  # linear, logarithmic, exponential, polynomial, power
                'trend_degree': trend.get('degree', '1'),
                'show_confidence': trend.get('show-confidence-bands', 'false') == 'true',
                'show_equation': trend.get('show-equation', 'false') == 'true',
                'show_r_squared': trend.get('show-r-squared', 'false') == 'true',
                'line_color': trend.get('color', '#C0504D'),
                'line_style': 'dashed',
                'label': 'Trend Line',
                'value': None,
                'value_column': '',
                'label_type': 'custom',
                'line_thickness': '1',
                'fill_above': '',
                'fill_below': '',
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
            
            # Filter action: filtered fields
            if action_type == 'filter':
                field_mappings = []
                for fm in action.findall('.//field-mapping'):
                    src = _strip_brackets(fm.get('source-field', ''))
                    tgt = _strip_brackets(fm.get('target-field', ''))
                    field_mappings.append({'source': src, 'target': tgt})
                action_data['field_mappings'] = field_mappings
            
            # Parameter action
            if action_type == 'param':
                action_data['parameter'] = action.get('param', '')
                action_data['source_field'] = _strip_brackets(action.get('source-field', ''))
            
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
                        # Clean the prefixes none:xxx:nk/qk
                        if level.startswith('none:') and ':' in level[5:]:
                            level = level[5:level.rfind(':')]
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
                        source_field = _strip_brackets(level)
                    
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
        """Extracts global sort orders"""
        sorts = []
        
        for ds in root.findall('.//datasource'):
            for sort in ds.findall('.//sort'):
                col = _strip_brackets(sort.get('column', ''))
                direction = sort.get('direction', 'ASC')
                if col:
                    sorts.append({
                        'field': col,
                        'direction': direction.upper(),
                        'key': sort.get('key', '')
                    })
        
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
