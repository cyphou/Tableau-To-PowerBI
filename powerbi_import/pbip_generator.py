"""
Power BI Project (.pbip) generator from converted Tableau objects

This module automatically creates the complete structure of a Power BI Project,
including all the files needed to open the project in Power BI Desktop.
"""

import os
import json
import logging
import shutil
import time
from datetime import datetime
import uuid
import re
import sys

logger = logging.getLogger(__name__)

# Pre-compiled patterns for field name cleaning
_RE_DERIVATION_PREFIX = re.compile(
    r'^(none|sum|avg|count|cnt|ctd|countd|min|max|usr|yr|mn|dy|qr|wk|attr|md|mdy|hms|hr|mt|sc|thr|trunc|tyr|tqr|tmn|tdy|twk):'
)
_RE_TABLE_CALC_PREFIX = re.compile(
    r'^(pcto|pctd|diff|running_sum|running_avg|running_count|running_min|running_max|rank|rank_unique|rank_dense):(sum|avg|count|min|max|countd)?:?'
)
_RE_TYPE_SUFFIX = re.compile(r':(nk|qk|ok|fn|tn)$')

# Tableau shelf aggregation prefix → PBI Aggregation Function ID
# 0=Sum, 1=Avg, 2=Count, 3=Min, 4=Max, 5=CountNonNull, 6=DistinctCount
_TABLEAU_AGG_TO_PBI_FUNC = {
    'sum': 0, 'avg': 1, 'cnt': 2, 'count': 2,
    'min': 3, 'max': 4, 'ctd': 6, 'countd': 6,
    'median': 0, 'attr': 0,
}

# ── PBIR schema constants ──────────────────────────────────────────────
SCHEMA_REPORT = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/2.0.0/schema.json"
SCHEMA_PAGE = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.0.0/schema.json"
SCHEMA_VISUAL = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.5.0/schema.json"
SCHEMA_BOOKMARK = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/bookmark/1.1.0/schema.json"
SCHEMA_PAGES_METADATA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json"
SCHEMA_VERSION = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json"
SCHEMA_DEFINITION_PBIR = "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json"
SCHEMA_PLATFORM = "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json"
SCHEMA_PBIP = "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json"

# Theme baseline — updated when PBI Desktop ships new monthly theme
PBI_BASE_THEME_NAME = "CY24SU06"
PBI_REPORT_VERSION_AT_IMPORT = "5.55"

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Generator imports
import m_query_generator
import tmdl_generator


def _write_json(filepath, data, ensure_ascii=True):
    """Write a JSON file, creating parent directories as needed."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=ensure_ascii)


def _rmtree_with_retry(path, attempts=3, delay=0.5):
    """Remove a directory tree with retry and exponential backoff.

    OneDrive and other sync tools may hold brief locks on files,
    causing ``PermissionError`` during cleanup.  This function
    retries up to *attempts* times with increasing delay.

    Returns:
        True if successfully removed, False otherwise.
    """
    for attempt in range(attempts):
        try:
            shutil.rmtree(path)
            return True
        except PermissionError:
            if attempt < attempts - 1:
                time.sleep(delay * (2 ** attempt))
                logger.debug(
                    "Retry %d/%d removing %s (PermissionError)",
                    attempt + 1, attempts, path,
                )
            else:
                logger.warning("Cannot remove %s after %d attempts (locked)", path, attempts)
                return False
        except OSError as exc:
            logger.debug("Cannot remove %s: %s", path, exc)
            return False
    return False


def _L(v):
    """PBIR expression literal wrapper."""
    return {"expr": {"Literal": {"Value": v}}}


def _pbi_literal(v):
    """Convert a filter value to a PBI literal string.

    PBI PBIR filter JSON uses different formats for different types:
    - Strings:  ``"'some text'"`` (single-quoted)
    - Booleans: ``"true"`` / ``"false"`` (unquoted)
    - Numbers:  ``"123"`` or ``"1.5"`` (unquoted)

    Without this, boolean filter values like ``true``/``false`` are
    wrapped as strings ``'true'``/``'false'`` causing a type mismatch
    with boolean columns (``Broken_Filters`` error in PBI Desktop).
    """
    v_str = str(v)
    v_lower = v_str.lower().strip()
    # Boolean
    if v_lower in ('true', 'false', 'vrai', 'faux'):
        return v_lower.replace('vrai', 'true').replace('faux', 'false')
    # Numeric
    try:
        float(v_str)
        return v_str
    except (ValueError, TypeError):
        pass
    # String (default)
    return f"'{v_str}'"


class PowerBIProjectGenerator:
    """Generates Power BI Project (.pbip) files"""
    
    def __init__(self, output_dir='artifacts/powerbi_projects/'):
        self.output_dir = os.path.abspath(output_dir)
        
        os.makedirs(self.output_dir, exist_ok=True)
    
    def generate_project(self, report_name, converted_objects, calendar_start=None,
                         calendar_end=None, culture=None, model_mode='import',
                         output_format='pbip', paginated=False, languages=None,
                         composite_threshold=None, agg_tables='none'):
        """
        Generates a complete Power BI Project
        
        Args:
            report_name: Report name
            converted_objects: Dict containing all converted objects
            calendar_start: Start year for Calendar table (default: 2020)
            calendar_end: End year for Calendar table (default: 2030)
            culture: Override culture/locale for semantic model
            paginated: If True, generate a paginated report layout alongside interactive report
        
        Returns:
            str: Path to the generated project
        """
        
        print(f"\n🔨 Generating Power BI Project: {report_name}")
        
        # Store options for downstream use
        self._calendar_start = calendar_start
        self._calendar_end = calendar_end
        self._culture = culture
        self._model_mode = model_mode or 'import'
        self._output_format = output_format or 'pbip'
        self._paginated = paginated
        self._languages = languages
        self._composite_threshold = composite_threshold
        self._agg_tables = agg_tables
        
        # Detect datasource-only mode (.tds — no worksheets/dashboards)
        self._datasource_only = not bool(
            converted_objects.get('worksheets') or converted_objects.get('dashboards')
        )
        
        # Create project structure
        project_dir = os.path.join(self.output_dir, report_name)
        os.makedirs(project_dir, exist_ok=True)
        
        # 1. Create the .pbip file
        pbip_file = self.create_pbip_file(project_dir, report_name)
        print(f"  ✓ .pbip file created: {pbip_file}")
        
        # 2. Create the SemanticModel structure
        if self._output_format in ('pbip', 'tmdl'):
            sm_dir = self.create_semantic_model_structure(project_dir, report_name, converted_objects)
            print(f"  ✓ SemanticModel created: {sm_dir}")
        
        # 3. Create the Report structure (skip for datasource-only .tds migrations)
        has_visuals = bool(converted_objects.get('worksheets') or converted_objects.get('dashboards'))
        if self._output_format in ('pbip', 'pbir') and has_visuals:
            report_dir = self.create_report_structure(project_dir, report_name, converted_objects)
            print(f"  ✓ Report created: {report_dir}")
        elif not has_visuals:
            print(f"  ℹ Datasource-only mode: SemanticModel generated (no Report)")
        
        # 4. Create metadata
        self.create_metadata(project_dir, report_name, converted_objects)
        print(f"  ✓ Metadata created")
        
        # 5. Create paginated report layout (if requested)
        if self._paginated:
            pag_dir = self._create_paginated_report(project_dir, report_name, converted_objects)
            print(f"  ✓ Paginated report layout created: {pag_dir}")
        
        # 6. Generate post-migration automation artifacts
        self._generate_automation_artifacts(project_dir, report_name, converted_objects)
        
        print(f"\n✅ Power BI Project generated: {project_dir}")
        print(f"   📂 Open in Power BI Desktop: {pbip_file}")
        
        return project_dir
    
    def create_pbip_file(self, project_dir, report_name):
        """Creates the main .pbip file — format identical to PBI Hero reference"""
        
        pbip_content = {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
            "version": "1.0",
            "artifacts": [
                {
                    "report": {
                        "path": f"{report_name}.Report"
                    }
                }
            ],
            "settings": {
                "enableAutoRecovery": True
            }
        }
        
        # For datasource-only migrations (.tds), remove report artifact
        # and reference only the SemanticModel.
        if hasattr(self, '_datasource_only') and self._datasource_only:
            pbip_content["artifacts"] = [
                {
                    "report": {
                        "path": f"{report_name}.SemanticModel"
                    }
                }
            ]
        
        pbip_file = os.path.join(project_dir, f"{report_name}.pbip")
        
        _write_json(pbip_file, pbip_content)
        
        # Also create the .gitignore
        gitignore = os.path.join(project_dir, '.gitignore')
        with open(gitignore, 'w', encoding='utf-8') as f:
            f.write(".pbi/\n")
        
        return pbip_file
    
    def create_semantic_model_structure(self, project_dir, report_name, converted_objects):
        """Creates the SemanticModel structure (format identical to PBI Hero reference)"""
        
        sm_dir = os.path.join(project_dir, f"{report_name}.SemanticModel")
        os.makedirs(sm_dir, exist_ok=True)
        
        # 1. Create .platform
        platform = {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {
                "type": "SemanticModel",
                "displayName": report_name
            },
            "config": {
                "version": "2.0",
                "logicalId": str(uuid.uuid4())
            }
        }
        _write_json(os.path.join(sm_dir, '.platform'), platform)
        
        # 2. Create definition.pbism
        pbism_definition = {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
            "version": "4.2",
            "settings": {
                "qnaEnabled": True
            }
        }
        pbism_file = os.path.join(sm_dir, 'definition.pbism')
        _write_json(pbism_file, pbism_definition)
        
        # 3. Create SemanticModel in TMDL (format identical to PBI Hero reference)
        self.create_tmdl_model(sm_dir, report_name, converted_objects)
        
        return sm_dir
    
    def create_tmdl_model(self, sm_dir, report_name, converted_objects):
        """Creates the semantic model in TMDL format (Tabular Model Definition Language)
        
        Directly converts extracted Tableau data to TMDL files.
        """
        
        datasources = converted_objects.get('datasources', [])
        
        # Collect additional objects
        extra_objects = {
            'hierarchies': converted_objects.get('hierarchies', []),
            'sets': converted_objects.get('sets', []),
            'groups': converted_objects.get('groups', []),
            'bins': converted_objects.get('bins', []),
            'aliases': converted_objects.get('aliases', {}),
            'parameters': converted_objects.get('parameters', []),
            'user_filters': converted_objects.get('user_filters', []),
            '_datasources': converted_objects.get('datasources', []),
            '_worksheets': converted_objects.get('worksheets', []),
            'hyper_files': converted_objects.get('hyper_files', []),
        }
        
        try:
            # Direct Tableau -> TMDL generation (no intermediate BIM layer)
            stats = tmdl_generator.generate_tmdl(
                datasources=datasources,
                report_name=report_name,
                extra_objects=extra_objects,
                output_dir=sm_dir,
                calendar_start=getattr(self, '_calendar_start', None),
                calendar_end=getattr(self, '_calendar_end', None),
                culture=getattr(self, '_culture', None),
                model_mode=getattr(self, '_model_mode', 'import'),
                languages=getattr(self, '_languages', None),
                composite_threshold=getattr(self, '_composite_threshold', None),
                agg_tables=getattr(self, '_agg_tables', 'none'),
            )
            
            print(f"  \u2713 TMDL model created with:")
            print(f"    - {stats['tables']} tables")
            print(f"    - {stats['columns']} columns")
            print(f"    - {stats['measures']} DAX measures")
            print(f"    - {stats['relationships']} relationships")
            if stats['hierarchies']:
                print(f"    - {stats['hierarchies']} hierarchies")
            if stats['roles']:
                print(f"    - {stats['roles']} RLS roles")

            # Store actual BIM measure names for report visual generation.
            # This set reflects the TMDL generator's 3-factor classification
            # (aggregation, column refs, role) and may differ from Tableau's
            # role='measure' metadata — a calculated column like DATEDIFF()
            # has role='measure' in Tableau but is a column in the BIM model.
            self._actual_bim_measure_names = stats.get('actual_bim_measures', set())
            self._actual_bim_symbols = stats.get('actual_bim_symbols', set())

            # Write lineage map alongside the project for traceability
            lineage = stats.get('lineage')
            if lineage:
                lineage_path = os.path.join(os.path.dirname(sm_dir), 'lineage_map.json')
                _write_json(lineage_path, lineage)
            
        except Exception as e:
            print(f"  \u26a0 Error during TMDL generation: {e}")
            import traceback
            traceback.print_exc()
    
    def _create_basic_model_bim(self, report_name, datasources):
        """Basic BIM generation in case of error (fallback)"""
        
        tables = []
        
        # Create a simple sample table
        m_expression = m_query_generator.generate_sample_data_query('SampleData', None)
        
        tables.append({
            "name": "SampleData",
            "columns": [
                {"name": "ID", "dataType": "int64", "sourceColumn": "ID"},
                {"name": "Name", "dataType": "string", "sourceColumn": "Name"},
                {"name": "Value", "dataType": "int64", "sourceColumn": "Value"}
            ],
            "partitions": [{
                "name": "SampleData",
                "mode": "import",
                "source": {
                    "type": "m",
                    "expression": m_expression
                }
            }]
        })
        
        return {
            "name": report_name,
            "compatibilityLevel": 1567,
            "model": {
                "culture": "en-US",
                "defaultPowerBIDataSourceVersion": "powerBI_V3",
                "tables": tables
            }
        }
    
    # ── Visual creation helpers (extracted from create_report_structure) ─────

    # Layout constants
    MIN_VISUAL_WIDTH = 60
    MIN_VISUAL_HEIGHT = 40
    MIN_GAP = 4  # pixels between adjacent visuals

    def _make_visual_position(self, pos, scale_x, scale_y, z_index,
                               page_width=None, page_height=None):
        """Create a standard PBIR position dict from Tableau coordinates.

        Applies minimum size constraints, clamps to page bounds, and enforces
        a minimum gap between the visual edge and the page boundary.
        """
        if page_width is None:
            page_width = getattr(self, '_current_page_width', 1280)
        if page_height is None:
            page_height = getattr(self, '_current_page_height', 720)
        x = round(pos.get('x', 0) * scale_x)
        y = round(pos.get('y', 0) * scale_y)
        w = max(round(pos.get('w', 300) * scale_x), self.MIN_VISUAL_WIDTH)
        h = max(round(pos.get('h', 200) * scale_y), self.MIN_VISUAL_HEIGHT)

        # Clamp within page bounds
        if x + w > page_width:
            w = max(page_width - x, self.MIN_VISUAL_WIDTH)
        if y + h > page_height:
            h = max(page_height - y, self.MIN_VISUAL_HEIGHT)
        x = max(x, 0)
        y = max(y, 0)

        return {
            "x": x,
            "y": y,
            "z": z_index * 1000,
            "height": h,
            "width": w,
            "tabOrder": z_index * 1000
        }

    # ── Grid-snapping layout engine (Sprint 76) ────────────────────────────

    def _build_zone_layout_map(self, zone_hierarchy, page_width, page_height):
        """Build a flat map of zone-name/zone-id → PBI pixel rect from zone hierarchy.

        Recursively subdivides the page according to container orientation
        (horizontal splits width, vertical splits height) and proportional
        zone sizes from Tableau's 0-100 000 coordinate system.

        Returns:
            dict mapping zone ``name`` (or ``id`` when unnamed) to
            ``{'x': int, 'y': int, 'w': int, 'h': int}``.
        """
        layout_map = {}
        if not zone_hierarchy:
            return layout_map
        root_pos = zone_hierarchy.get('position', {})
        root_w = max(root_pos.get('w', 0), root_pos.get('x', 0) + root_pos.get('w', 0))
        root_h = max(root_pos.get('h', 0), root_pos.get('y', 0) + root_pos.get('h', 0))
        if root_w == 0:
            root_w = 100000
        if root_h == 0:
            root_h = 100000
        self._layout_zone(zone_hierarchy, 0, 0, page_width, page_height,
                          root_w, root_h, layout_map)
        return layout_map

    def _layout_zone(self, zone, px_x, px_y, px_w, px_h,
                     coord_w, coord_h, layout_map):
        """Recursively lay out a zone and its children into PBI pixel space.

        For leaf zones the full allocated rectangle is recorded.
        For container zones with explicit orientation (horz/vert), children
        are subdivided along the orientation axis.  For containers without
        explicit orientation (common for layout-flow with 2-D grids), each
        child's Tableau coordinates are mapped proportionally into the
        parent's pixel space so side-by-side layouts are preserved.
        """
        key = zone.get('name') or zone.get('id', '')
        children = zone.get('children', [])

        if not children:
            # Leaf zone — record its pixel rectangle.
            # Skip filter/paramctrl zones: their name is the filtered worksheet,
            # not a unique identifier, so they'd overwrite the worksheet entry.
            zone_type = zone.get('zone_type', '')
            if key and zone_type not in ('filter', 'paramctrl'):
                layout_map[key] = {
                    'x': round(px_x), 'y': round(px_y),
                    'w': max(round(px_w), self.MIN_VISUAL_WIDTH),
                    'h': max(round(px_h), self.MIN_VISUAL_HEIGHT),
                }
            return

        orientation = zone.get('orientation', '')

        # Separate floating children (absolute position) from tiled children
        tiled = [c for c in children if not c.get('is_floating', False)]
        floating = [c for c in children if c.get('is_floating', False)]

        if tiled:
            if orientation == 'horz':
                total = sum(c.get('position', {}).get('w', 1) for c in tiled) or 1
                cursor = px_x
                for child in tiled:
                    cw = child.get('position', {}).get('w', 1)
                    alloc_w = px_w * cw / total
                    self._layout_zone(child, cursor, px_y, alloc_w, px_h,
                                      coord_w, coord_h, layout_map)
                    cursor += alloc_w
            elif orientation == 'vert':
                total = sum(c.get('position', {}).get('h', 1) for c in tiled) or 1
                cursor = px_y
                for child in tiled:
                    ch = child.get('position', {}).get('h', 1)
                    alloc_h = px_h * ch / total
                    self._layout_zone(child, px_x, cursor, px_w, alloc_h,
                                      coord_w, coord_h, layout_map)
                    cursor += alloc_h
            else:
                # No explicit orientation — use proportional coordinate mapping
                # to preserve 2-D grid layouts (e.g. side-by-side + stacked).
                child_max_x = max((c.get('position', {}).get('x', 0)
                                   + c.get('position', {}).get('w', 1)
                                   for c in tiled), default=1) or 1
                child_max_y = max((c.get('position', {}).get('y', 0)
                                   + c.get('position', {}).get('h', 1)
                                   for c in tiled), default=1) or 1
                for child in tiled:
                    cpos = child.get('position', {})
                    cx = px_x + (cpos.get('x', 0) / child_max_x) * px_w
                    cy = px_y + (cpos.get('y', 0) / child_max_y) * px_h
                    cw = (cpos.get('w', 1) / child_max_x) * px_w
                    ch = (cpos.get('h', 1) / child_max_y) * px_h
                    self._layout_zone(child, cx, cy, cw, ch,
                                      coord_w, coord_h, layout_map)

        # Floating children get absolute-scaled positions
        for child in floating:
            cpos = child.get('position', {})
            sx = px_w / max(coord_w, 1)
            sy = px_h / max(coord_h, 1)
            fx = px_x + cpos.get('x', 0) * sx
            fy = px_y + cpos.get('y', 0) * sy
            fw = cpos.get('w', 300) * sx
            fh = cpos.get('h', 200) * sy
            self._layout_zone(child, fx, fy, fw, fh,
                              coord_w, coord_h, layout_map)

        # Record the container itself (useful for padding propagation)
        if key:
            layout_map[key] = {
                'x': round(px_x), 'y': round(px_y),
                'w': max(round(px_w), self.MIN_VISUAL_WIDTH),
                'h': max(round(px_h), self.MIN_VISUAL_HEIGHT),
            }

    def _resolve_visual_position(self, obj, layout_map, scale_x, scale_y,
                                  z_index, page_width, page_height):
        """Resolve visual position using the grid layout map if available.

        Falls back to proportional scaling when the object is not found
        in the layout map (preserves backward compatibility).
        """
        ws_name = obj.get('worksheetName', '') or obj.get('name', '')
        mapped = layout_map.get(ws_name) if layout_map else None
        if mapped:
            x = max(mapped['x'], 0)
            y = max(mapped['y'], 0)
            w = max(mapped['w'], self.MIN_VISUAL_WIDTH)
            h = max(mapped['h'], self.MIN_VISUAL_HEIGHT)
            if x + w > page_width:
                w = max(page_width - x, self.MIN_VISUAL_WIDTH)
            if y + h > page_height:
                h = max(page_height - y, self.MIN_VISUAL_HEIGHT)
            return {
                "x": x, "y": y,
                "z": z_index * 1000,
                "height": h, "width": w,
                "tabOrder": z_index * 1000,
            }
        # Fallback to proportional scaling
        pos = obj.get('position', {})
        return self._make_visual_position(pos, scale_x, scale_y, z_index,
                                          page_width, page_height)

    def _apply_padding_to_visual(self, visual_json, zone_hierarchy, obj_name):
        """Add padding properties to visual from zone hierarchy padding data."""
        if not zone_hierarchy:
            return
        padding = self._find_zone_padding(zone_hierarchy, obj_name)
        if not padding:
            return
        general_props = visual_json.setdefault("visual", {}).setdefault(
            "objects", {}).setdefault("general", [{}])[0].setdefault("properties", {})
        for side in ('top', 'bottom', 'left', 'right'):
            if side in padding:
                general_props[f"padding{side.capitalize()}"] = padding[side]

    def _find_zone_padding(self, zone, name):
        """Recursively find padding for a named zone in the hierarchy."""
        zone_name = zone.get('name', '') or zone.get('id', '')
        if zone_name == name and zone.get('padding'):
            return zone['padding']
        for child in zone.get('children', []):
            result = self._find_zone_padding(child, name)
            if result:
                return result
        return None

    def _create_visual_worksheet(self, visuals_dir, ws_data, obj, scale_x, scale_y,
                                  visual_count, worksheets, converted_objects,
                                  tooltip_page_map=None):
        """Create a worksheet-type visual (chart, table, etc.).

        If the worksheet uses SCRIPT_* analytics extensions, generates a
        PBI Python or R script visual instead of a standard chart.
        """
        visual_id = uuid.uuid4().hex[:20]
        visual_dir = os.path.join(visuals_dir, visual_id)

        pos = obj.get('position', {})
        ws_name = obj.get('worksheetName', '')

        # ── SCRIPT_* detection ────────────────────────────────
        script_info = self._detect_script_visual(ws_data, converted_objects)
        if script_info:
            from visual_generator import generate_script_visual
            position = self._make_visual_position(pos, scale_x, scale_y, visual_count)
            field_names = [self._clean_field_name(f.get('name', ''))
                           for f in (ws_data or {}).get('fields', [])
                           if f.get('name')]
            container = generate_script_visual(
                visual_name=ws_name,
                script_info=script_info,
                fields=field_names,
                x=position.get('x', 10),
                y=position.get('y', 10),
                width=position.get('width', 400),
                height=position.get('height', 300),
                z_index=visual_count,
            )
            os.makedirs(visual_dir, exist_ok=True)
            _write_json(os.path.join(visual_dir, 'visual.json'), container, ensure_ascii=False)
            return

        visual_type = ws_data.get('chart_type', 'clusteredBarChart') if ws_data else 'clusteredBarChart'

        # Check for custom visual GUID (higher-fidelity AppSource visual)
        guid_info = None
        mark_type = ws_data.get('original_mark_class') if ws_data else None
        if mark_type and hasattr(self, '_used_custom_guids'):
            from visual_generator import resolve_custom_visual_type
            custom_vtype, guid_info = resolve_custom_visual_type(mark_type)
            if guid_info:
                visual_type = custom_vtype
                key = mark_type.lower().replace(' ', '').replace('_', '')
                self._used_custom_guids[key] = guid_info

        # Validate scatter chart: needs at least one measure for X/Y axes.
        # Circle/Shape marks sometimes produce scatterChart but lack measures.
        if visual_type == 'scatterChart' and ws_data:
            skip_names = {'Measure Names', 'Measure Values', 'Multiple Values',
                          ':Measure Names', ':Measure Values'}
            fields = ws_data.get('fields', [])
            has_measure = any(
                self._is_measure_field(self._clean_field_name(f.get('name', '')))
                for f in fields
                if self._clean_field_name(f.get('name', '')) not in skip_names
            )
            if not has_measure:
                visual_type = 'table'
            else:
                # Detect :Measure Names + Multiple Values pattern (strip/dot plot)
                # → clusteredBarChart shows multiple measures per category better
                has_measure_names = any(
                    f.get('name', '') in (':Measure Names', 'Measure Names')
                    for f in fields
                )
                has_multiple_values = any(
                    f.get('name', '') == 'Multiple Values'
                    for f in fields
                )
                if has_measure_names and has_multiple_values:
                    visual_type = 'clusteredBarChart'

                # Detect placeholder scatter: all row measures are min(1) dummies
                # (Tableau shape marks use min(1) for positioning, no real data)
                if visual_type == 'scatterChart':
                    calc_formulas = {}
                    for c in converted_objects.get('calculations', []):
                        cname = self._clean_field_name(c.get('name', '')).strip('[]')
                        calc_formulas[cname] = (c.get('formula', '') or '').strip().lower()
                    row_meas = [
                        f for f in fields
                        if f.get('shelf') == 'rows'
                        and self._is_measure_field(self._clean_field_name(f.get('name', '')))
                    ]
                    if row_meas and all(
                        calc_formulas.get(self._clean_field_name(f.get('name', '')).strip('[]'), '') == 'min(1)'
                        for f in row_meas
                    ):
                        visual_type = 'multiRowCard'

        # Spatial detection: map visuals with lat/lon fields → azureMap
        if visual_type in ('map', 'scatterChart') and ws_data:
            fields = ws_data.get('fields', [])
            has_lat = any(
                f.get('semantic_role', '').lower() in ('latitude', 'lat')
                or 'latitude' in f.get('name', '').lower()
                for f in fields
            )
            has_lon = any(
                f.get('semantic_role', '').lower() in ('longitude', 'lon', 'lng')
                or 'longitude' in f.get('name', '').lower()
                for f in fields
            )
            if has_lat and has_lon:
                visual_type = 'azureMap'

        # Sync overridden visual type back to ws_data so _build_visual_query
        # generates the correct data-role assignments.
        if ws_data and ws_data.get('chart_type') != visual_type:
            ws_data['chart_type'] = visual_type

        visual_json = {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.5.0/schema.json",
            "name": visual_id,
            "position": self._make_visual_position(pos, scale_x, scale_y, visual_count),
            "visual": {
                "visualType": visual_type,
                "drillFilterOtherVisuals": True
            }
        }

        # Add query if fields are available
        if ws_data and ws_data.get('fields'):
            query = self._build_visual_query(ws_data)
            if query:
                # If _build_visual_query detected an all-measures worksheet
                # and set an override visual type, apply it
                override_vt = ws_data.pop('_override_visual_type', None)
                if override_vt:
                    visual_type = override_vt
                    visual_json["visual"]["visualType"] = visual_type
                visual_json["visual"]["query"] = query
                # Apply sort state from extraction
                sort_orders = ws_data.get('sort_orders', [])
                if sort_orders and isinstance(sort_orders, list) and len(sort_orders) > 0:
                    sort_def = sort_orders[0]
                    sort_field = sort_def.get('field', '')
                    sort_dir = sort_def.get('direction', 'ASC')
                    sort_by = sort_def.get('sort_by', '')

                    # Clean Tableau notation: strip "DatasourceName." prefix
                    if '.' in sort_field:
                        sort_field = sort_field.split('.', 1)[1]
                    if '.' in sort_by:
                        sort_by = sort_by.split('.', 1)[1]
                    # Strip aggregation prefixes (sum:, avg:, etc.) and type suffixes (:qk, :nk)
                    sort_field = self._clean_field_name(sort_field)
                    sort_by = self._clean_field_name(sort_by)
                    if sort_field:
                        # Resolve sort field and sort_by through _field_map for correct Entity/Property
                        sort_entity = self._main_table
                        sort_prop = sort_field
                        if hasattr(self, '_field_map') and sort_field in self._field_map:
                            sort_entity, sort_prop = self._field_map[sort_field]

                        sort_entry = {
                            "direction": "Descending" if sort_dir.upper() == 'DESC' else "Ascending"
                        }
                        if sort_by:
                            # Resolve sort_by measure through _field_map
                            by_entity = self._main_table
                            by_prop = sort_by
                            if hasattr(self, '_field_map') and sort_by in self._field_map:
                                by_entity, by_prop = self._field_map[sort_by]
                            # Detect aggregation from the original sort_by Tableau name
                            raw_sort_by = sort_def.get('sort_by', '')
                            if '.' in raw_sort_by:
                                raw_sort_by = raw_sort_by.split('.', 1)[1]
                            sort_agg_match = _RE_DERIVATION_PREFIX.match(raw_sort_by)
                            sort_agg_func = _TABLEAU_AGG_TO_PBI_FUNC.get(
                                sort_agg_match.group(1), 0) if sort_agg_match else 0
                            # Computed sort: sort category by a measure
                            sort_entry["field"] = {
                                "Aggregation": {
                                    "Expression": {"Column": {"Expression": {"SourceRef": {"Entity": by_entity}}, "Property": by_prop}},
                                    "Function": sort_agg_func
                                }
                            }
                        else:
                            sort_entry["field"] = {
                                "Column": {"Expression": {"SourceRef": {"Entity": sort_entity}}, "Property": sort_prop}
                            }
                        query["queryState"] = query.get("queryState", {})
                        query["sortDefinition"] = {"sort": [sort_entry]}

        # Visual container title (visualContainerObjects per PBIR schema)
        # Prefer the worksheet's extracted title (from Tableau <title><run>)
        # over the raw worksheet name.
        display_title = (ws_data.get('title', '') if ws_data else '') or ws_name
        # Resolve parameter references like <[Parameters].[Parameter 1]>
        display_title = self._resolve_parameter_title(display_title, converted_objects)
        # Escape single quotes for PBI literal
        display_title = display_title.replace("'", "''")
        title_props = {
            "show": _L("true"),
            "text": _L(f"'{display_title}'")
        }
        # Apply Tableau title formatting (font size, color, bold, italic, underline, alignment)
        title_fmt = ws_data.get('title_format', {}) if ws_data else {}
        if title_fmt.get('font_size'):
            try:
                title_props["fontSize"] = _L(f"{int(title_fmt['font_size'])}D")
            except (ValueError, TypeError):
                pass
        if title_fmt.get('font_color'):
            title_props["fontColor"] = {"solid": {"color": _L(f"'{title_fmt['font_color']}'")}}
        if title_fmt.get('bold'):
            title_props["bold"] = _L("true")
        if title_fmt.get('italic'):
            title_props["italic"] = _L("true")
        if title_fmt.get('underline'):
            title_props["underline"] = _L("true")
        if title_fmt.get('alignment'):
            # Tableau: 0=left, 1=center, 2=right → PBI: 'left', 'center', 'right'
            align_map = {'0': 'left', '1': 'center', '2': 'right'}
            pbi_align = align_map.get(str(title_fmt['alignment']), 'left')
            title_props["alignment"] = _L(f"'{pbi_align}'")
        visual_json["visual"]["visualContainerObjects"] = {
            "title": [{"properties": title_props}]
        }

        # Visual objects: encodings (labels, legend, axes, colors)
        visual_objects = self._build_visual_objects(ws_name, ws_data, visual_type)
        visual_json["visual"]["objects"] = visual_objects

        # Visual filters
        if ws_data and ws_data.get('filters'):
            visual_filters = self._create_visual_filters(ws_data['filters'])
            if visual_filters:
                visual_json["filterConfig"] = {"filters": visual_filters}

        # Tooltip page binding (viz-in-tooltip → Power BI Report Page tooltip)
        if tooltip_page_map and ws_data:
            # Check if this worksheet has a viz-in-tooltip reference
            tooltips = ws_data.get('tooltips', [])
            if isinstance(tooltips, list):
                for tip in tooltips:
                    if isinstance(tip, dict) and tip.get('type') == 'viz_in_tooltip':
                        tip_ws_name = tip.get('worksheet', '')
                        tip_page_name = tooltip_page_map.get(tip_ws_name)
                        if tip_page_name:
                            visual_json["visual"].setdefault("objects", {})
                            visual_json["visual"]["objects"]["tooltips"] = [{
                                "properties": {
                                    "type": _L("'ReportPage'"),
                                    "page": _L(f"'{tip_page_name}'")
                                }
                            }]
                            break

        # Apply padding from dashboard zone
        obj_padding = obj.get('padding', {})
        if obj_padding:
            pad_props = {}
            for side in ('left', 'right', 'top', 'bottom'):
                pad_key = f'padding-{side}'
                if pad_key in obj_padding:
                    pad_props[side] = _L(f"{obj_padding[pad_key]}D")
            if pad_props:
                visual_json["visual"].setdefault("objects", {})
                visual_json["visual"]["objects"]["padding"] = [{"properties": pad_props}]
            # Apply border if extracted
            if obj_padding.get('border_style') and obj_padding['border_style'] != 'none':
                border_props = {
                    "show": _L("true")
                }
                if obj_padding.get('border_color'):
                    border_props["color"] = {
                        "solid": {"color": _L(f"'{obj_padding['border_color']}'")}
                    }
                visual_json["visual"].setdefault("objects", {})
                visual_json["visual"]["objects"]["border"] = [{"properties": border_props}]

        _write_json(os.path.join(visual_dir, 'visual.json'), visual_json, ensure_ascii=False)

    @staticmethod
    def _parse_rich_text_runs(obj):
        """Parse Tableau text runs into PBI paragraphs with formatting.

        Converts Tableau <formatted-text><run> elements (bold, italic, color,
        font_size, url) into PBI textRuns with textStyle properties.

        Args:
            obj: Dashboard text object with 'text_runs' and 'content' fields

        Returns:
            list: PBI paragraphs array for textbox visual
        """
        text_runs = obj.get('text_runs', [])
        if not text_runs:
            # Fallback: single plain run from content
            return [{"textRuns": [{"value": obj.get('content', '')}]}]

        # Group runs into paragraphs by newline characters
        paragraphs = []
        current_runs = []
        for run in text_runs:
            text = run.get('text', '')
            # Split on newlines to create separate paragraphs
            lines = text.split('\n')
            for i, line in enumerate(lines):
                if i > 0:
                    # Newline = new paragraph
                    paragraphs.append({"textRuns": current_runs if current_runs else [{"value": ""}]})
                    current_runs = []
                if line or i == 0:
                    pbi_run = {"value": line}
                    # Build textStyle from Tableau run formatting
                    style = {}
                    if run.get('bold'):
                        style['fontWeight'] = 'bold'
                    if run.get('italic'):
                        style['fontStyle'] = 'italic'
                    if run.get('color'):
                        color = run['color']
                        if color.startswith('#') and len(color) == 7:
                            style['color'] = color
                        elif color.startswith('#') and len(color) == 9:
                            # Tableau uses #AARRGGBB, PBI uses #RRGGBB
                            style['color'] = '#' + color[3:]
                    if run.get('font_size'):
                        try:
                            pts = float(run['font_size'])
                            style['fontSize'] = f"{pts}pt"
                        except (ValueError, TypeError):
                            logger.debug("Could not parse font_size: %s", run.get('font_size'))
                    if style:
                        pbi_run['textStyle'] = style
                    # URL → hyperlink
                    if run.get('url'):
                        pbi_run['url'] = run['url']
                    current_runs.append(pbi_run)

        # Flush last paragraph
        if current_runs:
            paragraphs.append({"textRuns": current_runs})

        return paragraphs if paragraphs else [{"textRuns": [{"value": ""}]}]

    def _create_visual_textbox(self, visuals_dir, obj, scale_x, scale_y, visual_count):
        """Create a textbox visual from a Tableau text object.

        Supports rich text with bold, italic, color, font_size, and URLs
        from Tableau <formatted-text><run> elements.
        """
        visual_id = uuid.uuid4().hex[:20]
        visual_dir = os.path.join(visuals_dir, visual_id)

        pos = obj.get('position', {})
        paragraphs = self._parse_rich_text_runs(obj)

        visual_json = {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.5.0/schema.json",
            "name": visual_id,
            "position": self._make_visual_position(pos, scale_x, scale_y, visual_count),
            "visual": {
                "visualType": "textbox",
                "objects": {
                    "general": [{
                        "properties": {
                            "paragraphs": paragraphs
                        }
                    }]
                }
            }
        }
        _write_json(os.path.join(visual_dir, 'visual.json'), visual_json, ensure_ascii=False)

    def _create_visual_image(self, visuals_dir, obj, scale_x, scale_y, visual_count):
        """Create an image visual from a Tableau image object."""
        visual_id = uuid.uuid4().hex[:20]
        visual_dir = os.path.join(visuals_dir, visual_id)

        pos = obj.get('position', {})
        img_source = obj.get('source', '')

        # For embedded TWBX images, convert to base64 data URI
        if img_source and not img_source.startswith(('http://', 'https://', 'data:')):
            # Track for later resolution by _extract_twbx_data_files
            if not hasattr(self, '_embedded_image_paths'):
                self._embedded_image_paths = {}
            self._embedded_image_paths[visual_id] = {
                'relative_path': img_source,
                'visual_dir': visual_dir,
            }

        visual_json = {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.5.0/schema.json",
            "name": visual_id,
            "position": self._make_visual_position(pos, scale_x, scale_y, visual_count),
            "visual": {
                "visualType": "image",
                "objects": {
                    "general": [{
                        "properties": {
                            "imageUrl": _L(f"'{img_source}'")
                        }
                    }]
                }
            }
        }
        _write_json(os.path.join(visual_dir, 'visual.json'), visual_json, ensure_ascii=False)

    def _create_visual_filter_control(self, visuals_dir, obj, scale_x, scale_y,
                                       visual_count, calc_id_to_caption, converted_objects):
        """Create a slicer visual from a Tableau filter control."""
        visual_id = uuid.uuid4().hex[:20]
        visual_dir = os.path.join(visuals_dir, visual_id)

        pos = obj.get('position', {})
        calc_col_id = obj.get('calc_column_id', '')
        column_name = calc_id_to_caption.get(calc_col_id, '')
        if not column_name:
            # Try the raw calc_column_id as a physical column name
            column_name = calc_col_id if calc_col_id else obj.get('field', obj.get('name', ''))

        # Resolve table via _field_map first (more reliable), then _find_column_table
        table_name = ''
        if hasattr(self, '_field_map') and column_name in self._field_map:
            table_name, column_name = self._field_map[column_name]
        if not table_name:
            table_name = self._find_column_table(column_name, converted_objects)

        vpos = self._make_visual_position(pos, scale_x, scale_y, visual_count)
        vx, vy, vw, vh = vpos['x'], vpos['y'], vpos['width'], vpos['height']

        # Determine slicer mode from parameter/field data type
        slicer_mode = self._detect_slicer_mode(obj, column_name, converted_objects)

        slicer_json = self._create_slicer_visual(visual_id, vx, vy, vw, vh,
                                                  column_name, table_name, visual_count,
                                                  slicer_mode=slicer_mode,
                                                  title=column_name)
        _write_json(os.path.join(visual_dir, 'visual.json'), slicer_json, ensure_ascii=False)

    def _create_visual_parameter_control(self, visuals_dir, obj, scale_x, scale_y,
                                          visual_count, converted_objects):
        """Create a slicer visual from a Tableau parameter control (paramctrl zone).

        Maps the parameter to its What-If table in the semantic model.  The
        slicer references the parameter table's Value column so users can pick
        a parameter value from a dropdown.
        """
        visual_id = uuid.uuid4().hex[:20]
        visual_dir = os.path.join(visuals_dir, visual_id)

        pos = obj.get('position', {})
        param_name = obj.get('param_name', '')

        # Resolve param_name (e.g., "Parameter 1") to caption via parameters list
        param_caption = param_name
        has_aliases = False
        for p in converted_objects.get('parameters', []):
            pname = p.get('name', '').strip('[]')
            if pname == param_name:
                param_caption = p.get('caption', param_name)
                # Check if aliases exist (for display name column)
                avs = p.get('allowable_values', [])
                has_aliases = any(
                    v.get('alias') and str(v.get('alias')) != str(v.get('value', ''))
                    for v in avs if v.get('type') != 'range'
                )
                break

        # The What-If table uses the caption as table name
        # Use "Name" column when aliases exist, "Value" otherwise
        table_name = param_caption
        column_name = "Name" if has_aliases else "Value"

        vpos = self._make_visual_position(pos, scale_x, scale_y, visual_count)
        vx, vy, vw, vh = vpos['x'], vpos['y'], vpos['width'], vpos['height']

        slicer_json = self._create_slicer_visual(visual_id, vx, vy, vw, vh,
                                                  column_name, table_name, visual_count,
                                                  slicer_mode='Dropdown',
                                                  title=param_caption)
        _write_json(os.path.join(visual_dir, 'visual.json'), slicer_json, ensure_ascii=False)

    def _create_action_visuals(self, visuals_dir, actions, scale_x, scale_y,
                                visual_count, page_display_name):
        """Create action button visuals from Tableau actions.
        
        Generates:
        - URL actions → actionButton visuals with WebUrl type
        - sheet-navigate actions → actionButton visuals with PageNavigation type
        
        Returns the number of visuals created.
        """
        created = 0
        for action in actions:
            action_type = action.get('type', '')
            
            if action_type == 'url':
                visual_id = uuid.uuid4().hex[:20]
                visual_dir = os.path.join(visuals_dir, visual_id)
                
                url = action.get('url', '')
                action_name = action.get('name', 'URL Action')
                
                btn_json = {
                    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.5.0/schema.json",
                    "name": visual_id,
                    "position": {
                        "x": 10, "y": 10 + created * 50,
                        "z": (visual_count + created) * 1000,
                        "height": 40, "width": 200,
                        "tabOrder": (visual_count + created) * 1000
                    },
                    "visual": {
                        "visualType": "actionButton",
                        "objects": {
                            "icon": [{"properties": {"shapeType": _L("'ArrowRight'")}}],
                            "outline": [{"properties": {"show": _L("false")}}],
                            "text": [{"properties": {
                                "show": _L("true"),
                                "text": _L(f"'{action_name}'")
                            }}],
                            "action": [{"properties": {
                                "type": _L("'WebUrl'"),
                                "webUrl": _L(f"'{url}'")
                            }}]
                        }
                    }
                }
                _write_json(os.path.join(visual_dir, 'visual.json'), btn_json, ensure_ascii=False)
                created += 1
            
            elif action_type == 'sheet-navigate':
                visual_id = uuid.uuid4().hex[:20]
                visual_dir = os.path.join(visuals_dir, visual_id)
                
                target_ws = action.get('target_worksheet', '')
                action_name = action.get('name', target_ws or 'Navigate')
                
                btn_json = {
                    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.5.0/schema.json",
                    "name": visual_id,
                    "position": {
                        "x": 10, "y": 10 + created * 50,
                        "z": (visual_count + created) * 1000,
                        "height": 40, "width": 200,
                        "tabOrder": (visual_count + created) * 1000
                    },
                    "visual": {
                        "visualType": "actionButton",
                        "objects": {
                            "icon": [{"properties": {"shapeType": _L("'ArrowRight'")}}],
                            "outline": [{"properties": {"show": _L("false")}}],
                            "text": [{"properties": {
                                "show": _L("true"),
                                "text": _L(f"'{action_name}'")
                            }}],
                            "action": [{"properties": {
                                "type": _L("'PageNavigation'")
                            }}]
                        }
                    }
                }
                _write_json(os.path.join(visual_dir, 'visual.json'), btn_json, ensure_ascii=False)
                created += 1
        
        return created

    def create_report_structure(self, project_dir, report_name, converted_objects):
        """Creates the Report structure in PBIR v4.0 format (identical to PBI Hero reference)
        
        Structure:
          Report/
            .platform
            definition.pbir
            definition/
              version.json
              report.json
              pages/
                pages.json
                {pageName}/
                  page.json
                  visuals/
                    {visualId}/
                      visual.json
        """
        import shutil
        import time
        
        # Build field mapping from Tableau to Power BI model
        self._build_field_mapping(converted_objects)
        
        report_dir = os.path.join(project_dir, f"{report_name}.Report")
        
        # Clean previous content (with retries for OneDrive sync locks)
        if os.path.exists(report_dir):
            for attempt in range(5):
                try:
                    shutil.rmtree(report_dir)
                    break
                except PermissionError:
                    if attempt < 4:
                        time.sleep(0.5 * (attempt + 1))
                    else:
                        # Last resort: remove files individually, skip locked ones
                        for root, dirs, files in os.walk(report_dir, topdown=False):
                            for name in files:
                                try:
                                    os.remove(os.path.join(root, name))
                                except PermissionError as exc:
                                    logger.debug("Could not remove locked file %s: %s", os.path.join(root, name), exc)
                            for name in dirs:
                                try:
                                    os.rmdir(os.path.join(root, name))
                                except (PermissionError, OSError) as exc:
                                    logger.debug("Could not remove directory %s: %s", os.path.join(root, name), exc)
        os.makedirs(report_dir, exist_ok=True)
        
        # 1. .platform
        platform = {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {
                "type": "Report",
                "displayName": report_name
            },
            "config": {
                "version": "2.0",
                "logicalId": str(uuid.uuid4())
            }
        }
        _write_json(os.path.join(report_dir, '.platform'), platform)
        
        # 2. definition.pbir (PBIR v4.0, schema 2.0.0, points to SemanticModel)
        report_definition = {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
            "version": "4.0",
            "datasetReference": {
                "byPath": {
                    "path": f"../{report_name}.SemanticModel"
                }
            }
        }
        _write_json(os.path.join(report_dir, 'definition.pbir'), report_definition)
        
        # 3. definition/ folder
        def_dir = os.path.join(report_dir, 'definition')
        os.makedirs(def_dir, exist_ok=True)
        
        # 3a. version.json
        version_json = {
            "$schema": SCHEMA_VERSION,
            "version": "2.0.0"
        }
        _write_json(os.path.join(def_dir, 'version.json'), version_json)
        
        # 3b. report.json — generate custom theme from extracted Tableau dashboard colors
        theme_data = None
        dashboards = converted_objects.get('dashboards', [])
        for db in dashboards:
            t = db.get('theme')
            if t and t.get('colors'):
                theme_data = t
                break

        custom_theme = tmdl_generator.generate_theme_json(theme_data)

        report_json = {
            "$schema": SCHEMA_REPORT,
            "themeCollection": {
                "baseTheme": {
                    "name": PBI_BASE_THEME_NAME,
                    "reportVersionAtImport": PBI_REPORT_VERSION_AT_IMPORT,
                    "type": "SharedResources"
                }
            },
            "resourcePackages": [
                {
                    "name": "SharedResources",
                    "type": "SharedResources",
                    "items": [
                        {
                            "name": PBI_BASE_THEME_NAME,
                            "path": f"BaseThemes/{PBI_BASE_THEME_NAME}.json",
                            "type": "BaseTheme"
                        }
                    ]
                }
            ],
            "settings": {
                "hideVisualContainerHeader": True,
                "useStylableVisualContainerHeader": True,
                "exportDataMode": "None",
                "defaultDrillFilterOtherVisuals": True,
                "allowChangeFilterTypes": True,
                "useEnhancedTooltips": True
            }
        }

        # Add custom theme reference if theme data was found
        if theme_data:
            report_json["resourcePackages"].append({
                "name": "MigrationTheme",
                "type": "RegisteredResources",
                "items": [
                    {
                        "name": "TableauMigrationTheme",
                        "path": "RegisteredResources/TableauMigrationTheme.json",
                        "type": "CustomTheme"
                    }
                ]
            })
            report_json["themeCollection"]["customTheme"] = {
                "name": "TableauMigrationTheme",
                "reportVersionAtImport": PBI_REPORT_VERSION_AT_IMPORT,
                "type": "RegisteredResources"
            }
        
        # Promote global filters and datasource-level filters to report level
        all_report_filters = list(converted_objects.get('filters', []))
        all_report_filters += list(converted_objects.get('datasource_filters', []))
        if all_report_filters:
            report_level_filters = self._create_visual_filters(all_report_filters)
            if report_level_filters:
                report_json["filterConfig"] = {"filters": report_level_filters}
        
        # Defer writing report.json until after pages — custom visual
        # GUIDs are discovered during visual creation and must be added
        # to report.json before it is persisted.
        self._used_custom_guids = {}  # key → guid_info dict
        
        # Write custom theme file if theme data was found
        if theme_data:
            res_dir = os.path.join(def_dir, 'RegisteredResources')
            _write_json(os.path.join(res_dir, 'TableauMigrationTheme.json'), custom_theme)

        # Copy custom shapes from extraction output to RegisteredResources
        self._copy_custom_shapes(def_dir, converted_objects)
        
        # 4. Create pages with visuals
        pages_dir = os.path.join(def_dir, 'pages')
        os.makedirs(pages_dir, exist_ok=True)
        
        worksheets = converted_objects.get('worksheets', [])
        
        page_names = []
        
        # Pre-build tooltip page mapping for viz-in-tooltip binding
        # tooltip_page_map: worksheet_name → tooltip_page_name
        tooltip_page_map = {}
        
        if dashboards:
            page_names = self._create_dashboard_pages(
                pages_dir, dashboards, worksheets, converted_objects, tooltip_page_map)
        
        # Collect bookmarks: from stories + from dynamic zone visibility (sheet-swap)
        all_bookmarks = []
        stories = converted_objects.get('stories', [])
        if stories:
            all_bookmarks.extend(self._create_bookmarks(stories))
        # Dynamic zone visibility → swap bookmarks (per dashboard)
        if dashboards:
            for db_idx, db in enumerate(dashboards):
                dz_vis = db.get('dynamic_zone_visibility', [])
                if dz_vis:
                    pg_name = page_names[db_idx] if db_idx < len(page_names) else ''
                    all_bookmarks.extend(self._create_swap_bookmarks(dz_vis, pg_name))
        if all_bookmarks:
            self._write_bookmark_files(def_dir, all_bookmarks)

        # Fallback: default page
        if not page_names or (dashboards and all(len(d.get('objects', [])) == 0 for d in dashboards)):
            page_names = self._create_fallback_page(pages_dir, worksheets, converted_objects)
        
        # 5b. Tooltip pages
        self._create_tooltip_pages(pages_dir, page_names, worksheets, converted_objects)

        # 5c. Mobile layout pages
        if dashboards:
            self._create_mobile_pages(pages_dir, page_names, dashboards, worksheets, converted_objects)

        # 5d. Drill-through pages — from filter actions targeting specific worksheets
        self._create_drillthrough_pages(pages_dir, page_names, worksheets,
                                        converted_objects)
        pages_metadata = {
            "$schema": SCHEMA_PAGES_METADATA,
            "pageOrder": page_names,
            "activePageName": page_names[0] if page_names else ""
        }
        _write_json(os.path.join(pages_dir, 'pages.json'), pages_metadata)
        
        # Post-generation cleanup: remove stale page and visual directories
        # (from previous migration runs or OneDrive lock leftovers)
        valid_page_set = set(page_names)
        stale_count = 0
        if os.path.isdir(pages_dir):
            for entry in os.listdir(pages_dir):
                entry_path = os.path.join(pages_dir, entry)
                if not os.path.isdir(entry_path):
                    continue
                # Remove entire stale page directories that are not in current
                # page_names AND don't have a page.json (i.e., truly orphaned)
                if (entry.startswith('ReportSection')
                        and entry not in valid_page_set
                        and not os.path.isfile(os.path.join(entry_path, 'page.json'))):
                    if not _rmtree_with_retry(entry_path):
                        stale_count += 1
                    continue
                # For valid pages, remove stale visual subdirs without visual.json
                visuals_dir = os.path.join(entry_path, 'visuals')
                if os.path.isdir(visuals_dir):
                    for vdir in os.listdir(visuals_dir):
                        vpath = os.path.join(visuals_dir, vdir)
                        if os.path.isdir(vpath) and not os.path.exists(os.path.join(vpath, 'visual.json')):
                            _rmtree_with_retry(vpath)
        if stale_count:
            logger.warning(
                "%d stale page directories could not be removed "
                "(OneDrive lock or permission issue)", stale_count
            )
            print(f"  ⚠ {stale_count} stale page directories could not be removed (OneDrive lock)")
        
        _write_json(os.path.join(def_dir, 'report.json'), report_json)
        
        return report_dir
    
    def _generate_report_definition_content(self, report_dir, report_name,
                                              converted_objects):
        """Generate report definition content (pages, visuals, theme) inside an
        existing report directory.

        This is the content-only portion of ``create_report_structure`` — it does
        **not** write ``.platform`` or ``definition.pbir``, making it suitable for
        thin reports that already have those files pointing to a shared semantic model.
        """
        def_dir = os.path.join(report_dir, 'definition')
        os.makedirs(def_dir, exist_ok=True)

        # version.json
        version_json = {
            "$schema": SCHEMA_VERSION,
            "version": "2.0.0",
        }
        _write_json(os.path.join(def_dir, 'version.json'), version_json)

        # Theme extraction
        theme_data = None
        dashboards = converted_objects.get('dashboards', [])
        for db in dashboards:
            t = db.get('theme')
            if t and t.get('colors'):
                theme_data = t
                break

        custom_theme = tmdl_generator.generate_theme_json(theme_data)

        report_json = {
            "$schema": SCHEMA_REPORT,
            "themeCollection": {
                "baseTheme": {
                    "name": PBI_BASE_THEME_NAME,
                    "reportVersionAtImport": PBI_REPORT_VERSION_AT_IMPORT,
                    "type": "SharedResources",
                },
            },
            "resourcePackages": [
                {
                    "name": "SharedResources",
                    "type": "SharedResources",
                    "items": [{"name": PBI_BASE_THEME_NAME, "path": f"BaseThemes/{PBI_BASE_THEME_NAME}.json", "type": "BaseTheme"}],
                },
            ],
            "settings": {
                "hideVisualContainerHeader": True,
                "useStylableVisualContainerHeader": True,
                "exportDataMode": "None",
                "defaultDrillFilterOtherVisuals": True,
                "allowChangeFilterTypes": True,
                "useEnhancedTooltips": True,
            },
        }

        if theme_data:
            report_json["resourcePackages"].append({
                "name": "MigrationTheme", "type": "RegisteredResources",
                "items": [{"name": "TableauMigrationTheme",
                           "path": "RegisteredResources/TableauMigrationTheme.json",
                           "type": "CustomTheme"}],
            })
            report_json["themeCollection"]["customTheme"] = {
                "name": "TableauMigrationTheme",
                "reportVersionAtImport": PBI_REPORT_VERSION_AT_IMPORT,
                "type": "RegisteredResources",
            }
            res_dir = os.path.join(def_dir, 'RegisteredResources')
            _write_json(os.path.join(res_dir, 'TableauMigrationTheme.json'), custom_theme)

        # Report-level filters
        all_report_filters = list(converted_objects.get('filters', []))
        all_report_filters += list(converted_objects.get('datasource_filters', []))
        if all_report_filters:
            report_level_filters = self._create_visual_filters(all_report_filters)
            if report_level_filters:
                report_json["filterConfig"] = {"filters": report_level_filters}

        self._used_custom_guids = {}

        # Pages
        pages_dir = os.path.join(def_dir, 'pages')
        os.makedirs(pages_dir, exist_ok=True)
        worksheets = converted_objects.get('worksheets', [])
        page_names = []
        tooltip_page_map = {}

        if dashboards:
            page_names = self._create_dashboard_pages(
                pages_dir, dashboards, worksheets, converted_objects, tooltip_page_map)

        # Bookmarks
        all_bookmarks = []
        stories = converted_objects.get('stories', [])
        if stories:
            all_bookmarks.extend(self._create_bookmarks(stories))
        if dashboards:
            for db_idx, db in enumerate(dashboards):
                dz_vis = db.get('dynamic_zone_visibility', [])
                if dz_vis:
                    pg_name = page_names[db_idx] if db_idx < len(page_names) else ''
                    all_bookmarks.extend(self._create_swap_bookmarks(dz_vis, pg_name))
        if all_bookmarks:
            self._write_bookmark_files(def_dir, all_bookmarks)

        if not page_names or (dashboards and all(len(d.get('objects', [])) == 0 for d in dashboards)):
            page_names = self._create_fallback_page(pages_dir, worksheets, converted_objects)

        self._create_tooltip_pages(pages_dir, page_names, worksheets, converted_objects)
        if dashboards:
            self._create_mobile_pages(pages_dir, page_names, dashboards, worksheets, converted_objects)
        self._create_drillthrough_pages(pages_dir, page_names, worksheets, converted_objects)

        pages_metadata = {
            "$schema": SCHEMA_PAGES_METADATA,
            "pageOrder": page_names,
            "activePageName": page_names[0] if page_names else "",
        }
        _write_json(os.path.join(pages_dir, 'pages.json'), pages_metadata)

        _write_json(os.path.join(def_dir, 'report.json'), report_json)

    # ── Report page sub-methods (extracted from create_report_structure) ──

    def _create_dashboard_pages(self, pages_dir, dashboards, worksheets, converted_objects,
                                tooltip_page_map):
        """Creates report pages from Tableau dashboards. Returns list of page_names."""
        page_names = []
        for db_idx, db in enumerate(dashboards):
            page_name = f"ReportSection{uuid.uuid4().hex[:20]}" if db_idx > 0 else "ReportSection"
            page_display_name = db.get('name', f'Page {db_idx + 1}')
            page_names.append(page_name)

            # Create the page folder
            page_dir = os.path.join(pages_dir, page_name)
            os.makedirs(page_dir, exist_ok=True)

            # Get the size
            size = db.get('size', {})
            page_width = size.get('width', 1280)
            page_height = size.get('height', 720)

            # Store for _make_visual_position clamping
            self._current_page_width = page_width
            self._current_page_height = page_height

            page_json = {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.0.0/schema.json",
                "name": page_name,
                "displayName": page_display_name,
                "displayOption": "FitToPage",
                "height": page_height,
                "width": page_width
            }

            # Add page-level filters from dashboard filters
            db_filters = list(db.get('filters', []))
            # Also promote context filters from worksheets to page level
            for ws in worksheets:
                for f in ws.get('filters', []):
                    if f.get('is_context', False):
                        db_filters.append(f)
            if db_filters:
                page_filters = self._create_visual_filters(db_filters)
                if page_filters:
                    page_json["filterConfig"] = {"filters": page_filters}

            # Responsive breakpoints from Tableau device layouts
            device_layouts = db.get('device_layouts', [])
            phone_layout = next((dl for dl in device_layouts
                                 if dl.get('device_type') == 'phone'), None)
            if phone_layout:
                mobile_visuals = []
                for viz in phone_layout.get('zones', []):
                    vname = viz.get('name', '')
                    vpos = viz.get('position', {})
                    # Scale phone layout to PBI mobile dimensions (320×568)
                    mob_w = 320
                    mob_h = 568
                    dl_max_w = max((z.get('position', {}).get('x', 0)
                                    + z.get('position', {}).get('w', 0)
                                    for z in phone_layout.get('zones', [])),
                                   default=mob_w) or mob_w
                    dl_max_h = max((z.get('position', {}).get('y', 0)
                                    + z.get('position', {}).get('h', 0)
                                    for z in phone_layout.get('zones', [])),
                                   default=mob_h) or mob_h
                    sx = mob_w / max(dl_max_w, 1)
                    sy = mob_h / max(dl_max_h, 1)
                    mobile_visuals.append({
                        "name": vname,
                        "position": {
                            "x": round(vpos.get('x', 0) * sx),
                            "y": round(vpos.get('y', 0) * sy),
                            "width": max(round(vpos.get('w', 200) * sx), 60),
                            "height": max(round(vpos.get('h', 100) * sy), 40),
                        }
                    })
                if mobile_visuals:
                    page_json["mobileState"] = {"visuals": mobile_visuals}

            _write_json(os.path.join(page_dir, 'page.json'), page_json)

            # Create visuals
            visuals_dir = os.path.join(page_dir, 'visuals')
            os.makedirs(visuals_dir, exist_ok=True)

            db_objects = db.get('objects', [])
            visual_count = 0

            # Build a calc_id → caption lookup for slicers
            calcs = converted_objects.get('calculations', [])
            calc_id_to_caption = {}
            for c in calcs:
                cname = c.get('name', '').strip('[]')
                ccaption = c.get('caption', '')
                if cname and ccaption:
                    calc_id_to_caption[cname] = ccaption

            # Build grid layout map from zone hierarchy when available
            zone_hierarchy = db.get('zone_hierarchy', {})
            layout_map = self._build_zone_layout_map(zone_hierarchy, page_width, page_height)

            # Compute scale factor from Tableau to Power BI pixels (fallback)
            max_x = max((o.get('position', {}).get('x', 0) + o.get('position', {}).get('w', 0) for o in db_objects), default=page_width)
            max_y = max((o.get('position', {}).get('y', 0) + o.get('position', {}).get('h', 0) for o in db_objects), default=page_height)
            scale_x = page_width / max(max_x, 1)
            scale_y = page_height / max(max_y, 1)

            for obj in db_objects:
                # Resolve position: grid layout map (preferred) or proportional (fallback)
                obj_type = obj.get('type', '')
                obj_name = obj.get('worksheetName', '') or obj.get('name', '') or obj.get('param_name', '')
                # Filter/parameter controls use their own position (their 'name'
                # refers to the filtered worksheet, not themselves).
                grid_pos = None
                if obj_type not in ('filter_control', 'parameter_control') and layout_map and obj_name:
                    grid_pos = layout_map.get(obj_name)
                if grid_pos:
                    eff_obj = dict(obj, position=grid_pos)
                    eff_sx, eff_sy = 1.0, 1.0
                else:
                    eff_obj = obj
                    eff_sx, eff_sy = scale_x, scale_y

                if obj.get('type') == 'worksheetReference':
                    ws_name = obj.get('worksheetName', '')
                    ws_data = self._find_worksheet(worksheets, ws_name)
                    self._create_visual_worksheet(visuals_dir, ws_data, eff_obj,
                                                   eff_sx, eff_sy, visual_count,
                                                   worksheets, converted_objects,
                                                   tooltip_page_map=tooltip_page_map)
                    visual_count += 1

                elif obj.get('type') == 'text':
                    self._create_visual_textbox(visuals_dir, eff_obj, eff_sx, eff_sy, visual_count)
                    visual_count += 1

                elif obj.get('type') == 'image':
                    self._create_visual_image(visuals_dir, eff_obj, eff_sx, eff_sy, visual_count)
                    visual_count += 1

                elif obj.get('type') == 'filter_control':
                    self._create_visual_filter_control(visuals_dir, eff_obj, eff_sx, eff_sy,
                                                        visual_count, calc_id_to_caption,
                                                        converted_objects)
                    visual_count += 1

                elif obj.get('type') == 'parameter_control':
                    self._create_visual_parameter_control(visuals_dir, eff_obj, eff_sx, eff_sy,
                                                           visual_count, converted_objects)
                    visual_count += 1

            # Create action buttons for URL and sheet-navigate actions
            actions = converted_objects.get('actions', [])
            if actions:
                # Filter actions relevant to this dashboard
                db_name = db.get('name', '')
                db_actions = [a for a in actions if a.get('type') in ('url', 'sheet-navigate')
                              and (not a.get('source_worksheet') or a.get('source_worksheet') == db_name
                                   or any(o.get('worksheetName') == a.get('source_worksheet') for o in db_objects))]
                if db_actions:
                    created = self._create_action_visuals(visuals_dir, db_actions,
                                                           scale_x, scale_y, visual_count,
                                                           page_display_name)
                    visual_count += created

            # Create slicer for Pages shelf (Tableau play-axis animation)
            pages_shelf = db.get('pages_shelf', {})
            if pages_shelf:
                self._create_pages_shelf_slicer(
                    visuals_dir, pages_shelf, scale_x, scale_y,
                    visual_count, converted_objects)
                visual_count += 1

            # Add page navigator when multiple dashboards exist (Tableau tab strip)
            if len(dashboards) > 1:
                self._create_page_navigator(visuals_dir, page_width, page_height, visual_count)
                visual_count += 1

            print(f"  📊 Page '{page_display_name}': {visual_count} visuals created")

        return page_names

    def _create_fallback_page(self, pages_dir, worksheets, converted_objects):
        """Creates pages when no dashboards exist — one page per worksheet. Returns page_names list."""
        page_names = []

        if not worksheets:
            # No worksheets either — create a single empty page
            page_name = "ReportSection"
            page_names.append(page_name)
            page_dir = os.path.join(pages_dir, page_name)
            os.makedirs(page_dir, exist_ok=True)
            page_json = {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.0.0/schema.json",
                "name": page_name,
                "displayName": "Tableau Migration",
                "displayOption": "FitToPage",
                "height": 720,
                "width": 1280
            }
            _write_json(os.path.join(page_dir, 'page.json'), page_json)
            os.makedirs(os.path.join(page_dir, 'visuals'), exist_ok=True)
            print(f"  📊 Default page: 0 visuals created")
            return page_names

        for idx, ws in enumerate(worksheets):
            page_name = "ReportSection" if idx == 0 else f"ReportSection{uuid.uuid4().hex[:20]}"
            page_names.append(page_name)

            ws_name = ws.get('name', f'Sheet {idx+1}')
            page_dir = os.path.join(pages_dir, page_name)
            os.makedirs(page_dir, exist_ok=True)

            page_json = {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.0.0/schema.json",
                "name": page_name,
                "displayName": ws_name,
                "displayOption": "FitToPage",
                "height": 720,
                "width": 1280
            }
            _write_json(os.path.join(page_dir, 'page.json'), page_json)

            visuals_dir = os.path.join(page_dir, 'visuals')
            os.makedirs(visuals_dir, exist_ok=True)

            visual_id = uuid.uuid4().hex[:20]
            visual_dir = os.path.join(visuals_dir, visual_id)

            visual_type = ws.get('chart_type', 'clusteredBarChart')
            ws_name = ws.get('name', f'Visual {idx+1}')

            # Check for custom visual GUID
            mark_type = ws.get('original_mark_class')
            if mark_type and hasattr(self, '_used_custom_guids'):
                from visual_generator import resolve_custom_visual_type
                custom_vtype, guid_info = resolve_custom_visual_type(mark_type)
                if guid_info:
                    visual_type = custom_vtype
                    key = mark_type.lower().replace(' ', '').replace('_', '')
                    self._used_custom_guids[key] = guid_info

            # Validate scatter chart has measures for X/Y
            if visual_type == 'scatterChart':
                skip_names = {'Measure Names', 'Measure Values', 'Multiple Values',
                              ':Measure Names', ':Measure Values'}
                fields = ws.get('fields', [])
                has_measure = any(
                    self._is_measure_field(self._clean_field_name(f.get('name', '')))
                    for f in fields
                    if self._clean_field_name(f.get('name', '')) not in skip_names
                )
                if not has_measure:
                    visual_type = 'table'
                else:
                    # Detect :Measure Names + Multiple Values pattern (strip/dot plot)
                    has_measure_names = any(
                        f.get('name', '') in (':Measure Names', 'Measure Names')
                        for f in fields
                    )
                    has_multiple_values = any(
                        f.get('name', '') == 'Multiple Values'
                        for f in fields
                    )
                    if has_measure_names and has_multiple_values:
                        visual_type = 'clusteredBarChart'

                    # Detect placeholder scatter: all row measures are min(1) dummies
                    if visual_type == 'scatterChart':
                        calc_formulas = {}
                        for c in converted_objects.get('calculations', []):
                            cname = self._clean_field_name(c.get('name', '')).strip('[]')
                            calc_formulas[cname] = (c.get('formula', '') or '').strip().lower()
                        row_meas = [
                            f for f in fields
                            if f.get('shelf') == 'rows'
                            and self._is_measure_field(self._clean_field_name(f.get('name', '')))
                        ]
                        if row_meas and all(
                            calc_formulas.get(self._clean_field_name(f.get('name', '')).strip('[]'), '') == 'min(1)'
                            for f in row_meas
                        ):
                            visual_type = 'multiRowCard'

            visual_json = {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.5.0/schema.json",
                "name": visual_id,
                "position": {
                    "x": 10,
                    "y": 10,
                    "z": 0,
                    "height": 700,
                    "width": 1260,
                    "tabOrder": 0
                },
                "visual": {
                    "visualType": visual_type,
                    "drillFilterOtherVisuals": True
                }
            }

            if ws.get('fields'):
                query = self._build_visual_query(ws)
                if query:
                    visual_json["visual"]["query"] = query

            _write_json(os.path.join(visual_dir, 'visual.json'), visual_json, ensure_ascii=False)

        print(f"  📊 {len(worksheets)} worksheet pages created (1 visual each)")
        return page_names

    def _create_tooltip_pages(self, pages_dir, page_names, worksheets, converted_objects):
        """Creates tooltip pages from worksheets with viz_in_tooltip data."""
        tooltip_page_map = {}
        tooltip_worksheets = [ws for ws in worksheets if ws.get('tooltip', {}).get('viz_in_tooltip')]
        # Also check tooltips list for viz_in_tooltip entries
        if not tooltip_worksheets:
            tooltip_worksheets = []
            for ws in worksheets:
                tooltips = ws.get('tooltips', [])
                if isinstance(tooltips, list):
                    for tip in tooltips:
                        if isinstance(tip, dict) and tip.get('type') == 'viz_in_tooltip':
                            tooltip_worksheets.append(ws)
                            break

        for tip_ws in tooltip_worksheets:
            tip_name = f"Tooltip_{uuid.uuid4().hex[:12]}"
            tip_display = f"Tooltip - {tip_ws.get('name', 'Tooltip')}"
            page_names.append(tip_name)
            # Track tooltip page for visual binding
            tooltip_page_map[tip_ws.get('name', '')] = tip_name
            # Also map from viz_in_tooltip references
            tooltips = tip_ws.get('tooltips', [])
            if isinstance(tooltips, list):
                for tip in tooltips:
                    if isinstance(tip, dict) and tip.get('type') == 'viz_in_tooltip':
                        tooltip_page_map[tip.get('worksheet', '')] = tip_name

            tip_dir = os.path.join(pages_dir, tip_name)
            os.makedirs(tip_dir, exist_ok=True)

            tip_page = {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.0.0/schema.json",
                "name": tip_name,
                "displayName": tip_display,
                "displayOption": "FitToPage",
                "height": 320,
                "width": 480,
                "pageType": "Tooltip"
            }
            _write_json(os.path.join(tip_dir, 'page.json'), tip_page)

            # Create a visual for the tooltip
            tip_visuals_dir = os.path.join(tip_dir, 'visuals')
            os.makedirs(tip_visuals_dir, exist_ok=True)
            self._create_visual_worksheet(
                tip_visuals_dir, tip_ws,
                {'type': 'worksheetReference', 'worksheetName': tip_ws.get('name', ''),
                 'position': {'x': 0, 'y': 0, 'w': 480, 'h': 320}},
                1.0, 1.0, 0, worksheets, converted_objects
            )
            print(f"  💡 Tooltip page '{tip_display}' created")

    def _create_mobile_pages(self, pages_dir, page_names, dashboards, worksheets, converted_objects):
        """Creates mobile layout pages from phone device layouts."""
        for db_idx, db in enumerate(dashboards):
            device_layouts = db.get('device_layouts', [])
            for dl in device_layouts:
                device_type = dl.get('device_type', '')
                if device_type == 'phone' and not dl.get('auto_generated', False):
                    mobile_page_name = f"MobileLayout_{uuid.uuid4().hex[:12]}"
                    mobile_display = f"{db.get('name', 'Dashboard')} (Phone)"
                    page_names.append(mobile_page_name)

                    mobile_dir = os.path.join(pages_dir, mobile_page_name)
                    os.makedirs(mobile_dir, exist_ok=True)

                    mobile_page = {
                        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.0.0/schema.json",
                        "name": mobile_page_name,
                        "displayName": mobile_display,
                        "displayOption": "FitToPage",
                        "height": 568,
                        "width": 320,
                    }
                    _write_json(os.path.join(mobile_dir, 'page.json'), mobile_page)

                    # Create visuals for visible zones
                    mobile_visuals_dir = os.path.join(mobile_dir, 'visuals')
                    os.makedirs(mobile_visuals_dir, exist_ok=True)

                    vis_count = 0
                    for zone in dl.get('zones', []):
                        zone_name = zone.get('name', '')
                        ws_data = self._find_worksheet(worksheets, zone_name)
                        if ws_data:
                            self._create_visual_worksheet(
                                mobile_visuals_dir, ws_data,
                                {'type': 'worksheetReference', 'worksheetName': zone_name,
                                 'position': zone.get('position', {'x': 0, 'y': vis_count * 200, 'w': 320, 'h': 200})},
                                1.0, 1.0, vis_count, worksheets, converted_objects
                            )
                            vis_count += 1

                    print(f"  📱 Mobile layout page '{mobile_display}': {vis_count} visuals")

    def _build_field_mapping(self, converted_objects):
        """Builds the mapping from Tableau fields to the Power BI model.
        
        Solves 2 problems:
        1. Visuals reference the Tableau internal ID (e.g. federated.xxx) instead
           of the Power BI table name (e.g. CORN, cities.csv)
        2. Visuals reference Tableau calculation IDs (e.g. Calculation_114...)
           instead of the Power BI measure name (e.g. Filiere, Lat_upgrade)
        
        Tables are now all real physical tables.
        Measures are on the main table (the one with the most columns).
        
        Creates self._field_map: {raw_field_name: (table_name, property_name)}
        """
        self._field_map = {}
        
        datasources = converted_objects.get('datasources', [])
        
        # Phase 1: Collect deduplicated physical tables
        best_tables = {}
        for ds in datasources:
            tables = ds.get('tables', [])
            # Extract physical columns from datasource-level list (excluding calculations)
            ds_cols = [c for c in ds.get('columns', []) if not c.get('calculation')]
            for table in tables:
                tname = table.get('name', '?')
                if not tname or tname == 'Unknown':
                    continue
                # Inherit datasource-level columns into tables that have none
                # (common for Tableau Extracts: single table with columns at DS level)
                if not table.get('columns') and ds_cols and len(tables) == 1:
                    # Clean DS-level columns: strip bracket notation and skip special columns
                    cleaned_cols = []
                    for c in ds_cols:
                        raw = c.get('name', '')
                        if raw.startswith('[:') or not raw:
                            continue  # Skip special Tableau columns (e.g. [:Measure Names])
                        clean = dict(c)
                        clean['name'] = raw.strip('[]')
                        cleaned_cols.append(clean)
                    table['columns'] = cleaned_cols
                if tname not in best_tables or len(table.get('columns', [])) > len(best_tables[tname].get('columns', [])):
                    best_tables[tname] = table
        
        # Phase 2: Identify the main table (the one with the most columns)
        main_table = None
        max_cols = 0
        for tname, t in best_tables.items():
            ncols = len(t.get('columns', []))
            if ncols > max_cols:
                max_cols = ncols
                main_table = tname
        self._main_table = main_table or 'Table'
        self._datasources_ref = datasources
        
        # Phase 3: Map columns of each physical table
        #   Also track physical measure columns (role='measure' from Tableau)
        #   When a column name exists in multiple tables, prefer the main table
        #   so visual field references resolve to the primary data table.
        for tname, t in best_tables.items():
            for col in t.get('columns', []):
                cname = col.get('name', '?')
                # Only overwrite if: (a) not yet mapped, or
                # (b) this IS the main table (main table wins ties)
                if cname not in self._field_map or tname == main_table:
                    self._field_map[cname] = (tname, cname)
                # Also index by caption for visual references using display name
                caption = col.get('caption', '')
                if caption:
                    if caption not in self._field_map or tname == main_table:
                        self._field_map[caption] = (tname, cname)
        
        # Phase 4: Map Tableau calculations (rawID -> caption/friendly name)
        # Measures are on the main table
        measures_table = main_table or 'Table'
        self._measure_names = set()  # Track which fields are measures (not dimensions) — for bucket assignment

        # _bim_measure_names: authoritative set of DAX measures in the BIM
        # model.  If the TMDL generator populated _actual_bim_measure_names
        # (the real model output), we use that; otherwise we fall back to
        # Tableau metadata (role='measure') which is less accurate because
        # Tableau can label a calculated column (e.g. DATEDIFF) as a measure.
        if hasattr(self, '_actual_bim_measure_names') and self._actual_bim_measure_names:
            self._bim_measure_names = set(self._actual_bim_measure_names)
        else:
            self._bim_measure_names = set()

        # Phase 4a: Physical columns with role='measure' (from Tableau XML)
        #   These go into _measure_names for visual bucket classification (Y not Category)
        #   but NOT into _bim_measure_names (they're physical columns, not DAX measures)
        for tname, t in best_tables.items():
            for col in t.get('columns', []):
                if col.get('role', '') == 'measure':
                    cname = col.get('name', '?')
                    self._measure_names.add(cname)

        # Phase 4b: Calculated measures — index in _field_map and _measure_names
        for ds in datasources:
            for calc in ds.get('calculations', []):
                raw_name = calc.get('name', '').replace('[', '').replace(']', '')
                caption = (calc.get('caption', '') or raw_name).replace('[', '').replace(']', '')
                if raw_name not in self._field_map:
                    self._field_map[raw_name] = (measures_table, caption)
                # Also index by caption for filters using the readable name
                if caption and caption not in self._field_map:
                    self._field_map[caption] = (measures_table, caption)
                # Track measure names for Category vs Y assignment
                if calc.get('role', '') == 'measure':
                    self._measure_names.add(raw_name)
                    if caption:
                        self._measure_names.add(caption)
        
        # Also gather measure names from top-level calculations
        for calc in converted_objects.get('calculations', []):
            if calc.get('role', '') == 'measure':
                raw_name = calc.get('name', '').replace('[', '').replace(']', '')
                caption = (calc.get('caption', '') or raw_name).replace('[', '').replace(']', '')
                self._measure_names.add(raw_name)
                if caption:
                    self._measure_names.add(caption)
        
        # Phase 5: Map extracted groups (BIM-generated calculated columns)
        groups = converted_objects.get('groups', [])
        for g in groups:
            group_name = g.get('name', '').replace('[', '').replace(']', '')
            if group_name and group_name not in self._field_map:
                self._field_map[group_name] = (measures_table, group_name)

        # Phase 6: Detect synthetic "Number of Records" fields in worksheets.
        # These are generated by the extractor when Tableau uses COUNT(*) on
        # __tableau_internal_object_id__.  Register as a BIM measure.
        worksheets = converted_objects.get('worksheets', [])
        for ws in worksheets:
            for f in ws.get('fields', []):
                if f.get('name') == 'Number of Records':
                    self._field_map['Number of Records'] = (measures_table, 'Number of Records')
                    self._measure_names.add('Number of Records')
                    self._bim_measure_names.add('Number of Records')
                    break

        # Save the main table for fallback
        self._main_table = measures_table
    
    def _is_measure_field(self, field_name):
        """Check if a field is a measure (aggregate) vs a dimension"""
        clean = field_name.replace('[', '').replace(']', '')
        if hasattr(self, '_measure_names') and clean in self._measure_names:
            return True
        # Resolve via field_map and check the resolved name
        if hasattr(self, '_field_map') and clean in self._field_map:
            _, prop = self._field_map[clean]
            if hasattr(self, '_measure_names') and prop in self._measure_names:
                return True
        return False
    
    def _clean_field_name(self, name):
        """Strip all known Tableau derivation prefixes from a field name"""
        clean = _RE_DERIVATION_PREFIX.sub('', name)
        clean = _RE_TABLE_CALC_PREFIX.sub('', clean)
        clean = _RE_TYPE_SUFFIX.sub('', clean)
        return clean

    _RE_PARAM_REF = re.compile(r'<\[Parameters\]\.\[([^\]]+)\]>')

    def _resolve_parameter_title(self, title, converted_objects):
        """Replace <[Parameters].[Name]> references in titles with parameter captions."""
        if not title or '[Parameters]' not in title:
            return title
        params = converted_objects.get('parameters', [])
        param_caption_map = {}
        for p in params:
            pname = p.get('name', '').strip('[]')
            caption = p.get('caption', pname)
            param_caption_map[pname] = caption
        def _repl(m):
            pname = m.group(1)
            return param_caption_map.get(pname, pname)
        return self._RE_PARAM_REF.sub(_repl, title)

    # ── PBIR data-role names per visual type ─────────────────────
    # (dimension_roles, measure_roles) — must match PBI Desktop expectations
    _VISUAL_DATA_ROLES = {
        "card":                              ([], ["Fields"]),
        "multiRowCard":                      ([], ["Values"]),
        "kpi":                               ([], ["Indicator", "TrendAxis"]),
        "clusteredBarChart":                 (["Category", "Series"], ["Y"]),
        "stackedBarChart":                   (["Category", "Series"], ["Y"]),
        "hundredPercentStackedBarChart":      (["Category", "Series"], ["Y"]),
        "clusteredColumnChart":              (["Category", "Series"], ["Y"]),
        "stackedColumnChart":                (["Category", "Series"], ["Y"]),
        "hundredPercentStackedColumnChart":   (["Category", "Series"], ["Y"]),
        "lineChart":                         (["Category", "Series"], ["Y"]),
        "areaChart":                         (["Category", "Series"], ["Y"]),
        "stackedAreaChart":                  (["Category", "Series"], ["Y"]),
        "hundredPercentStackedAreaChart":     (["Category", "Series"], ["Y"]),
        "pieChart":                          (["Category"], ["Y"]),
        "donutChart":                        (["Category"], ["Y"]),
        "waterfallChart":                    (["Category", "Breakdown"], ["Y"]),
        "funnel":                            (["Category"], ["Y"]),
        "gauge":                             ([], ["Y", "MinValue", "MaxValue", "TargetValue"]),
        "treemap":                           (["Group"], ["Values"]),
        "sunburst":                          (["Group"], ["Values"]),
        "scatterChart":                      (["Category"], ["X", "Y", "Size"]),
        "tableEx":                           (["Values"], ["Values"]),
        "table":                             (["Values"], ["Values"]),
        "matrix":                            (["Rows", "Columns"], ["Values"]),
        "pivotTable":                        (["Rows", "Columns"], ["Values"]),
        "slicer":                            (["Values"], []),
        "lineStackedColumnComboChart":       (["Category", "Series"], ["ColumnY", "LineY"]),
        "lineClusteredColumnComboChart":     (["Category", "Series"], ["ColumnY", "LineY"]),
        "map":                               (["Category", "Series"], ["Size"]),
        "filledMap":                         (["Category", "Series"], ["Size"]),
        "shapeMap":                          (["Location"], ["Color"]),
        "ribbonChart":                       (["Category", "Series"], ["Y"]),
        "boxAndWhisker":                     (["Category", "Sampling"], ["Value"]),
        "decompositionTree":                 (["TreeItems"], ["Values"]),
        "wordCloud":                         (["Category"], ["Values"]),
    }

    # Date-related words for treemap Group ordering (prefer non-date dims)
    _DATE_WORDS = frozenset({
        'date', 'time', 'datetime', 'timestamp',
        'year', 'month', 'quarter', 'week', 'day',
        'heure', 'année', 'mois', 'trimestre', 'semaine', 'jour',
    })

    def _is_date_field(self, name):
        """Heuristic: does *name* look like a date / time column?"""
        lower = name.lower()
        return any(w in lower for w in self._DATE_WORDS)

    def _classify_shelf_fields(self, cleaned_fields):
        """Classify cleaned fields by shelf into role buckets.

        Returns a dict with keys: rows_dims, rows_meas, cols_dims, cols_meas,
        color_dims, color_meas, size_fields, tooltip_fields, text_fields,
        expanded_meas, other_dims, other_meas.
        """
        result = {
            'rows_dims': [], 'rows_meas': [],
            'cols_dims': [], 'cols_meas': [],
            'color_dims': [], 'color_meas': [],
            'size_fields': [], 'tooltip_fields': [], 'text_fields': [],
            'expanded_meas': [], 'other_dims': [], 'other_meas': [],
        }
        for f in cleaned_fields:
            shelf = f.get('shelf', '')
            is_mea = (shelf == 'measure_value'
                      or self._is_measure_field(f['name']))

            if shelf == 'measure_value':
                result['expanded_meas'].append(f)
            elif shelf == 'tooltip':
                result['tooltip_fields'].append(f)
            elif shelf == 'size':
                result['size_fields'].append(f)
            elif shelf == 'text':
                result['text_fields'].append(f)
            elif shelf == 'color':
                (result['color_meas'] if is_mea else result['color_dims']).append(f)
            elif shelf == 'rows':
                (result['rows_meas'] if is_mea else result['rows_dims']).append(f)
            elif shelf == 'columns':
                (result['cols_meas'] if is_mea else result['cols_dims']).append(f)
            else:
                (result['other_meas'] if is_mea else result['other_dims']).append(f)
        return result

    def _build_visual_query(self, ws_data):
        """Builds a query with queryState for a visual (PBIR v4.0 format).

        Uses shelf-aware field classification to assign Tableau fields to
        the correct PBIR data roles for each visual type so Power BI Desktop
        binds fields to the right data wells.

        Shelf mapping logic:
        - rows/columns dims  → primary axis (Category/Group/Location/Rows)
        - rows/columns meas  → value axis (Y/Values/Size)
        - color dims         → Series / Legend (secondary grouping)
        - color meas         → Tooltips (data for conditional formatting)
        - tooltip fields     → Tooltips
        - size fields        → Size
        - measure_value      → expanded measures (from :Measure Names)
        """
        fields = ws_data.get('fields', [])
        if not fields:
            return None

        # ── Clean & de-duplicate field names ─────────────────────
        skip_names = {'Measure Names', 'Measure Values', 'Multiple Values',
                      ':Measure Names', ':Measure Values',
                      'Longitude (generated)', 'Latitude (generated)'}
        cleaned_fields = []
        seen_names = set()
        for f in fields:
            raw_name = f.get('name', '')
            clean = self._clean_field_name(raw_name)
            if clean in skip_names or raw_name in skip_names:
                continue
            # Skip Tableau internal fields (e.g. __tableau_internal_object_id__)
            if clean.startswith('__tableau_internal') or raw_name.startswith('__tableau_internal'):
                continue
            # Deduplicate: same field from different shelves
            if clean in seen_names:
                continue
            seen_names.add(clean)
            cleaned_fields.append({**f, 'name': clean})

        if not cleaned_fields:
            return None

        # ── Shelf-aware field classification ──────────────────────
        classified = self._classify_shelf_fields(cleaned_fields)
        rows_dims = classified['rows_dims']
        rows_meas = classified['rows_meas']
        cols_dims = classified['cols_dims']
        cols_meas = classified['cols_meas']
        color_dims = classified['color_dims']
        color_meas = classified['color_meas']
        size_fields = classified['size_fields']
        tooltip_fields = classified['tooltip_fields']
        text_fields = classified['text_fields']
        expanded_meas = classified['expanded_meas']
        other_dims = classified['other_dims']
        other_meas = classified['other_meas']

        # Combined views (order matters for role assignment)
        # Default ordering: columns dims first (typically x-axis), then rows
        axis_dims = cols_dims + rows_dims + other_dims
        # For treemap: rows dims first (primary hierarchy grouping)
        hier_dims = rows_dims + cols_dims + other_dims
        # All axis measures (rows + columns + expanded from :Measure Names)
        axis_meas = rows_meas + cols_meas + expanded_meas + other_meas

        # Promote text-shelf measures to axis_meas when there are no axis
        # measures yet (e.g. pie/donut charts where the value sits on text
        # shelf in Tableau).
        text_meas = [f for f in text_fields if self._is_measure_field(f['name'])]
        text_dims = [f for f in text_fields if not self._is_measure_field(f['name'])]
        if not axis_meas and text_meas:
            axis_meas = text_meas
            text_fields = text_dims

        # Tooltip-grade fields: explicit tooltips + color measures + remaining text dims
        tip_fields = tooltip_fields + color_meas + text_fields
        # Legacy combined lists (for fallback logic)
        all_dims = axis_dims + color_dims
        all_meas = axis_meas + size_fields

        visual_type = ws_data.get('chart_type', 'clusteredBarChart')
        query_state = {}

        # ── Per-visual-type role assignment ───────────────────────

        if visual_type == 'scatterChart':
            # Scatter: all dims → Category (detail grouping)
            #          cols measures → X, rows measures → Y, 3rd → Size
            scatter_dims = axis_dims + color_dims
            if scatter_dims:
                query_state["Category"] = {
                    "projections": [self._make_projection_entry(d)
                                    for d in scatter_dims]
                }
            # In Tableau: columns = X-axis, rows = Y-axis.
            # Use cols_meas first for X, rows_meas for Y.
            scatter_meas = (cols_meas + rows_meas + expanded_meas
                            + other_meas + size_fields)
            if len(scatter_meas) >= 2:
                query_state["X"] = self._make_scatter_axis_projection(scatter_meas[0])
                query_state["Y"] = self._make_scatter_axis_projection(scatter_meas[1])
            elif len(scatter_meas) == 1:
                query_state["Y"] = self._make_scatter_axis_projection(scatter_meas[0])
            # Size: 3rd axis measure or explicit size field or color measure
            size_f = scatter_meas[2:3] or color_meas[:1]
            if size_f:
                query_state["Size"] = self._make_scatter_axis_projection(size_f[0])
            if tip_fields:
                query_state["Tooltips"] = {
                    "projections": [self._make_projection_entry(f)
                                    for f in tip_fields[:5]]
                }

        elif visual_type in ('tableEx', 'table'):
            # Table: all fields (dims + measures) → Values
            table_fields = all_dims + all_meas
            if table_fields:
                query_state["Values"] = {
                    "projections": [self._make_projection_entry(f)
                                    for f in table_fields[:10]]
                }

        elif visual_type == 'matrix':
            # Matrix: first dim → Rows, second dim or color dim → Columns,
            #         measures → Values
            matrix_dims = axis_dims + color_dims
            if matrix_dims:
                query_state["Rows"] = self._make_projection(matrix_dims[0])
            if len(matrix_dims) >= 2:
                query_state["Columns"] = self._make_projection(matrix_dims[1])
            if axis_meas:
                query_state["Values"] = {
                    "projections": [self._make_projection_entry(m)
                                    for m in axis_meas[:6]]
                }

        elif visual_type == 'card':
            targets = axis_meas if axis_meas else all_dims
            if targets:
                query_state["Fields"] = {
                    "projections": [self._make_projection_entry(f)
                                    for f in targets[:6]]
                }

        elif visual_type == 'multiRowCard':
            # Prefer text fields + dims over placeholder measures (e.g. min(1))
            targets = text_fields + all_dims if text_fields else (axis_meas if axis_meas else all_dims)
            if targets:
                query_state["Values"] = {
                    "projections": [self._make_projection_entry(f)
                                    for f in targets[:6]]
                }

        elif visual_type in ('gauge', 'kpi'):
            if axis_meas:
                query_state["Y"] = self._make_projection(axis_meas[0])
            if len(axis_meas) >= 2:
                query_state["TargetValue"] = self._make_projection(axis_meas[1])
            if axis_dims:
                query_state["Category"] = self._make_projection(axis_dims[0])

        elif visual_type in ('treemap', 'sunburst'):
            # Treemap: dims → Group (multiple levels, non-date first)
            tree_dims = hier_dims + color_dims
            non_date = [d for d in tree_dims
                        if not self._is_date_field(d['name'])]
            date = [d for d in tree_dims
                    if self._is_date_field(d['name'])]
            ordered = non_date + date
            if ordered:
                query_state["Group"] = {
                    "projections": [self._make_projection_entry(d)
                                    for d in ordered]
                }
            # Values: axis measures, or color measures (Tableau uses color
            # encoding for value on treemaps), or size fields
            tree_meas = axis_meas or color_meas or size_fields
            if tree_meas:
                query_state["Values"] = self._make_projection(tree_meas[0])
                # Remove used measure from tip_fields to avoid duplicate
                used = tree_meas[0]
                tip_fields = [f for f in tip_fields if f is not used]
            if tip_fields:
                query_state["Tooltips"] = {
                    "projections": [self._make_projection_entry(f)
                                    for f in tip_fields[:5]]
                }

        elif visual_type in ('filledMap', 'shapeMap'):
            # Filled/shape map: dims → Category (Location well),
            #                   color dim → Series, measure → Size/Color.
            # PBI Desktop (2025+) auto-converts filledMap → map;
            # the map visual uses PBIR role "Category" for its Location well.
            # Tableau maps often use generated Lat/Lon (which we skip)
            # and put the real geo field on the tooltip shelf.
            loc_dims = axis_dims
            if not loc_dims:
                # Pull non-measure tooltip fields as Location fallback
                loc_dims = [f for f in tooltip_fields
                            if not self._is_measure_field(f['name'])]
                # Remove them from tip_fields so they're not duplicated
                tip_fields = [f for f in tip_fields if f not in loc_dims]
            loc_role = "Category"  # map visual PBIR role for Location well
            if loc_dims:
                query_state[loc_role] = {
                    "projections": [self._make_projection_entry(d)
                                    for d in loc_dims]
                }
            if color_dims:
                query_state["Series"] = self._make_projection(color_dims[0])
            value_role = "Color" if visual_type == 'shapeMap' else "Size"
            # For maps, Tableau's color measure → PBI Size (data magnitude).
            val_src = axis_meas or color_meas
            if val_src:
                query_state[value_role] = self._make_projection(val_src[0])
                # Remove the used color_meas from tooltips to avoid duplication
                if val_src[0] in color_meas:
                    tip_fields = [f for f in tip_fields if f is not val_src[0]]
            if tip_fields:
                query_state["Tooltips"] = {
                    "projections": [self._make_projection_entry(f)
                                    for f in tip_fields[:5]]
                }

        elif visual_type == 'map':
            # Bubble map: dims → Category (Location well),
            #             color dim → Series, measure → Size.
            # The map visual uses PBIR role "Category" for its Location well.
            # Same fallback as filledMap for generated Lat/Lon.
            loc_dims = axis_dims
            if not loc_dims:
                loc_dims = [f for f in tooltip_fields
                            if not self._is_measure_field(f['name'])]
                tip_fields = [f for f in tip_fields if f not in loc_dims]
            if loc_dims:
                query_state["Category"] = {
                    "projections": [self._make_projection_entry(d)
                                    for d in loc_dims]
                }
            if color_dims:
                query_state["Series"] = self._make_projection(color_dims[0])
            # For maps, Tableau's color measure → PBI Size (data magnitude).
            sz = axis_meas or size_fields or color_meas
            if sz:
                query_state["Size"] = self._make_projection(sz[0])
                # Remove the used color_meas from tooltips to avoid duplication
                if sz[0] in color_meas:
                    tip_fields = [f for f in tip_fields if f is not sz[0]]
            if tip_fields:
                query_state["Tooltips"] = {
                    "projections": [self._make_projection_entry(f)
                                    for f in tip_fields[:5]]
                }

        elif visual_type in ('lineClusteredColumnComboChart',
                             'lineStackedColumnComboChart'):
            if axis_dims:
                query_state["Category"] = self._make_projection(axis_dims[0])
            if color_dims:
                query_state["Series"] = self._make_projection(color_dims[0])
            elif len(axis_dims) >= 2:
                query_state["Series"] = self._make_projection(axis_dims[1])
            if axis_meas:
                query_state["ColumnY"] = self._make_projection(axis_meas[0])
            if len(axis_meas) >= 2:
                query_state["LineY"] = self._make_projection(axis_meas[1])

        elif visual_type == 'waterfallChart':
            if axis_dims:
                query_state["Category"] = self._make_projection(axis_dims[0])
            if axis_meas:
                query_state["Y"] = self._make_projection(axis_meas[0])
            if len(axis_dims) >= 2:
                query_state["Breakdown"] = self._make_projection(axis_dims[1])

        elif visual_type == 'boxAndWhisker':
            if axis_dims:
                query_state["Category"] = self._make_projection(axis_dims[0])
            if axis_meas:
                query_state["Value"] = self._make_projection(axis_meas[0])

        elif visual_type == 'wordCloud':
            if axis_dims:
                query_state["Category"] = self._make_projection(axis_dims[0])
            if axis_meas:
                query_state["Values"] = self._make_projection(axis_meas[0])

        elif visual_type == 'decompositionTree':
            if axis_dims:
                query_state["TreeItems"] = self._make_projection(axis_dims[0])
            if axis_meas:
                query_state["Values"] = self._make_projection(axis_meas[0])

        else:
            # ── Standard charts (bar, column, line, area, pie, donut,
            #    funnel, ribbon, stacked variants) ────────────────
            if axis_dims:
                query_state["Category"] = self._make_projection(axis_dims[0])
            elif color_dims:
                # No axis dims — promote first color dim to Category
                query_state["Category"] = self._make_projection(color_dims[0])
                color_dims = color_dims[1:]  # consume it

            # Series: color dim (highest priority) or second axis dim
            # that isn't a date when the first dim already is.
            # Only promote axis dim to Series when there are measures for Y.
            if color_dims:
                query_state["Series"] = self._make_projection(color_dims[0])
            elif len(axis_dims) >= 2 and axis_meas:
                candidates = axis_dims[1:]
                non_date = [d for d in candidates
                            if not self._is_date_field(d['name'])]
                series_dim = non_date[0] if non_date else candidates[0]
                query_state["Series"] = self._make_projection(series_dim)

            if axis_meas:
                query_state["Y"] = {
                    "projections": [self._make_projection_entry(m)
                                    for m in axis_meas]
                }
            elif size_fields:
                # Tableau size-shelf measures (e.g. line chart thickness) → Y
                query_state["Y"] = {
                    "projections": [self._make_projection_entry(m)
                                    for m in size_fields]
                }
            # If no measures, use last dim as pseudo-measure (only when
            # Series hasn't consumed it yet)
            elif len(axis_dims) > 1 and "Series" not in query_state:
                query_state["Y"] = self._make_projection(axis_dims[-1])

            if tip_fields:
                query_state["Tooltips"] = {
                    "projections": [self._make_projection_entry(f)
                                    for f in tip_fields[:5]]
                }

        # ── Fallback: only measures, no dimensions at all ────────────────
        # Convert to card (1-2 measures) or multiRowCard (3+).
        # Note: if color_dims were promoted to Category in the standard
        # charts branch above, query_state already has "Category";
        # we must NOT override in that case.  We check query_state instead
        # of color_dims because the branch consumes color_dims via slicing.
        if (axis_meas and not axis_dims
                and "Category" not in query_state
                and visual_type in (
                    'clusteredBarChart', 'stackedBarChart',
                    'clusteredColumnChart',
                )):
            query_state.clear()
            card_meas = axis_meas + color_meas
            if len(card_meas) <= 2:
                query_state["Fields"] = {
                    "projections": [self._make_projection_entry(m)
                                    for m in card_meas[:6]]
                }
                ws_data['_override_visual_type'] = 'card'
            else:
                query_state["Values"] = {
                    "projections": [self._make_projection_entry(m)
                                    for m in card_meas[:6]]
                }
                ws_data['_override_visual_type'] = 'multiRowCard'

        return {"queryState": query_state} if query_state else None
    
    def _make_projection(self, field):
        """Creates a simple projection for a field"""
        return {
            "projections": [self._make_projection_entry(field)]
        }

    def _make_scatter_axis_projection(self, field):
        """Creates a projection for scatter chart X/Y/Size axes.
        BIM measures use Measure wrapper; physical columns use Aggregation
        wrapper (Sum) since scatter axes require explicit aggregation."""
        return {
            "projections": [self._make_scatter_axis_entry(field)]
        }

    def _make_scatter_axis_entry(self, field):
        """Creates projection entry for scatter chart axes.
        Named DAX measures → Measure wrapper.
        Physical columns → Aggregation wrapper with shelf-aware Function ID."""
        raw_name = field.get('name', 'Field')
        clean_name = self._clean_field_name(raw_name)

        if hasattr(self, '_field_map') and clean_name in self._field_map:
            entity, prop = self._field_map[clean_name]
        else:
            entity = getattr(self, '_main_table', 'Table')
            prop = clean_name
            for ds in getattr(self, '_datasources_ref', []):
                for calc in ds.get('calculations', []):
                    calc_id = calc.get('name', '').replace('[', '').replace(']', '')
                    if calc_id == clean_name:
                        prop = calc.get('caption', clean_name)
                        self._field_map[clean_name] = (entity, prop)
                        break

        is_bim_measure = hasattr(self, '_bim_measure_names') and (
            clean_name in self._bim_measure_names or prop in self._bim_measure_names
        )

        shelf_agg = field.get('aggregation', '')
        agg_func = _TABLEAU_AGG_TO_PBI_FUNC.get(shelf_agg, 0)

        if is_bim_measure:
            field_ref = {
                "Measure": {
                    "Expression": {"SourceRef": {"Entity": entity}},
                    "Property": prop
                }
            }
        else:
            # Physical column: wrap as Aggregation with shelf-aware Function ID
            field_ref = {
                "Aggregation": {
                    "Expression": {
                        "Column": {
                            "Expression": {"SourceRef": {"Entity": entity}},
                            "Property": prop
                        }
                    },
                    "Function": agg_func
                }
            }

        return {
            "field": field_ref,
            "queryRef": f"{entity}.{prop}",
            "active": True
        }
    
    def _make_projection_entry(self, field):
        """Creates a projection entry for a field, resolved to the Power BI model.

        Wrapper selection:
        - Named DAX measures (in _bim_measure_names) → ``Measure`` wrapper
        - Physical columns with explicit Tableau aggregation (cnt, avg, etc.)
          → ``Aggregation`` wrapper with the corresponding PBI Function ID
        - Physical numeric columns treated as measures by Tableau
          (in _measure_names but NOT in _bim_measure_names) → ``Aggregation``
          wrapper with Function 0 (Sum) so PBI shows explicit aggregation
        - Everything else (dimension columns) → ``Column`` wrapper
        """
        raw_name = field.get('name', 'Field')

        # Clean all known Tableau prefixes
        clean_name = self._clean_field_name(raw_name)

        # Resolve via mapping
        if hasattr(self, '_field_map') and clean_name in self._field_map:
            entity, prop = self._field_map[clean_name]
        else:
            # Fallback: use main table (not raw Tableau datasource name) as Entity
            entity = getattr(self, '_main_table', 'Table')
            prop = clean_name
            # Try to resolve Tableau calculation IDs to captions
            for ds in getattr(self, '_datasources_ref', []):
                for calc in ds.get('calculations', []):
                    calc_id = calc.get('name', '').replace('[', '').replace(']', '')
                    if calc_id == clean_name:
                        prop = calc.get('caption', clean_name)
                        self._field_map[clean_name] = (entity, prop)
                        break

        shelf_agg = field.get('aggregation', '')
        explicit_agg_func = _TABLEAU_AGG_TO_PBI_FUNC.get(shelf_agg)

        # Determine wrapper type
        is_bim_measure = hasattr(self, '_bim_measure_names') and (
            clean_name in self._bim_measure_names or prop in self._bim_measure_names
        )
        is_physical_measure = (
            not is_bim_measure
            and hasattr(self, '_measure_names')
            and (clean_name in self._measure_names or prop in self._measure_names)
        )

        if is_bim_measure:
            # Named DAX measure → Measure wrapper
            field_ref = {
                "Measure": {
                    "Expression": {"SourceRef": {"Entity": entity}},
                    "Property": prop
                }
            }
        elif is_physical_measure or explicit_agg_func is not None:
            # Physical column with aggregation — use shelf aggregation if present
            agg_func = explicit_agg_func if explicit_agg_func is not None else 0
            field_ref = {
                "Aggregation": {
                    "Expression": {
                        "Column": {
                            "Expression": {"SourceRef": {"Entity": entity}},
                            "Property": prop
                        }
                    },
                    "Function": agg_func
                }
            }
        else:
            # Dimension column → Column wrapper
            field_ref = {
                "Column": {
                    "Expression": {"SourceRef": {"Entity": entity}},
                    "Property": prop
                }
            }

        return {
            "field": field_ref,
            "queryRef": f"{entity}.{prop}",
            "active": True
        }
    
    def _create_bookmarks(self, stories):
        """Converts Tableau stories to Power BI bookmarks (PBIR format)."""
        bookmarks = []
        for story in stories:
            story_name = story.get('name', 'Story')
            for sp_idx, sp in enumerate(story.get('story_points', [])):
                caption = sp.get('caption', f'{story_name} - Point {sp_idx + 1}')
                active_section = sp.get('captured_sheet', 'ReportSection')
                bookmark = {
                    "name": f"Bookmark_{uuid.uuid4().hex[:12]}",
                    "displayName": caption,
                    "explorationState": {
                        "version": "1.0",
                        "activeSection": active_section,
                        "sections": {
                            active_section: {"visualContainers": {}}
                        },
                    }
                }
                bookmarks.append(bookmark)
        return bookmarks

    def _create_swap_bookmarks(self, dynamic_zones, page_name):
        """Create bookmarks from dynamic zone visibility (sheet-swap containers).

        Each dynamic zone maps to a bookmark that toggles visual visibility
        for its zone. This simulates Tableau's show/hide sheet feature.

        Args:
            dynamic_zones: List from extract_dynamic_zone_visibility
            page_name: The PBI page name these bookmarks belong to

        Returns:
            List of PBI bookmark dicts
        """
        bookmarks = []
        zone_names = [dz.get('zone_name', '') for dz in dynamic_zones if dz.get('zone_name')]

        for dz in dynamic_zones:
            zone_name = dz.get('zone_name', 'Zone')
            field = dz.get('field', '')
            value = dz.get('value', '')
            label = f"Show {zone_name}" if zone_name else f"Swap: {field}={value}"
            section = page_name or 'ReportSection'

            # Build visual container state: show target zone, hide others
            visual_containers = {}
            for zn in zone_names:
                if zn == zone_name:
                    continue
                visual_containers[zn] = {
                    "singleVisual": {},
                    "display": {"mode": "hidden"},
                }

            bookmark = {
                "name": f"Swap_{uuid.uuid4().hex[:12]}",
                "displayName": label,
                "explorationState": {
                    "version": "1.0",
                    "activeSection": section,
                    "sections": {
                        section: {"visualContainers": visual_containers}
                    },
                },
                "options": {
                    "applyOnlyToTargetVisuals": True,
                    "targetVisualNames": [zone_name],
                },
            }
            bookmarks.append(bookmark)
        return bookmarks

    def _write_bookmark_files(self, def_dir, bookmarks):
        """Write bookmarks as individual PBIR bookmark files.

        Each bookmark gets its own directory under ``definition/bookmarks/``.
        """
        bookmarks_dir = os.path.join(def_dir, 'bookmarks')
        for bm in bookmarks:
            bm_name = bm["name"]
            bm_dir = os.path.join(bookmarks_dir, bm_name)
            os.makedirs(bm_dir, exist_ok=True)
            bookmark_json = {
                "$schema": SCHEMA_BOOKMARK,
                "name": bm["name"],
                "displayName": bm["displayName"],
                "explorationState": bm["explorationState"],
            }
            if bm.get("options"):
                bookmark_json["options"] = bm["options"]
            _write_json(os.path.join(bm_dir, 'bookmark.json'), bookmark_json)

    def _copy_custom_shapes(self, def_dir, converted_objects):
        """Copy extracted custom shape files to RegisteredResources/.

        Shape images are extracted from .twbx during the extraction phase
        into ``<extraction_output_dir>/shapes/``.  This method copies them
        into the PBIR ``RegisteredResources/`` folder so that Power BI
        Desktop can reference them.
        """
        import shutil
        shapes = converted_objects.get('custom_shapes', [])
        if not shapes:
            return

        # Determine source shapes directory — typically tableau_export/shapes/
        # Search common extraction output locations
        search_dirs = [
            os.path.join('tableau_export', 'shapes'),
            os.path.join(os.path.dirname(def_dir), '..', 'tableau_export', 'shapes'),
        ]
        shapes_src = None
        for sd in search_dirs:
            if os.path.isdir(sd):
                shapes_src = sd
                break

        if not shapes_src:
            return

        res_dir = os.path.join(def_dir, 'RegisteredResources')
        os.makedirs(res_dir, exist_ok=True)

        copied = 0
        for shape in shapes:
            filename = shape.get('filename', '')
            if not filename:
                continue
            src_path = os.path.join(shapes_src, filename)
            if os.path.isfile(src_path):
                dst_path = os.path.join(res_dir, filename)
                try:
                    shutil.copy2(src_path, dst_path)
                    copied += 1
                except (OSError, PermissionError) as exc:
                    logger.debug("Could not copy shape %s: %s", filename, exc)

        if copied:
            print(f"  🖼️  Copied {copied} custom shape(s) to RegisteredResources/")

    def _create_report_filters(self, converted_objects):
        """Creates report-level filters from parameters"""
        report_filters = []
        
        params = converted_objects.get('parameters', [])
        for param in params:
            # Support both extracted (caption/value) and converted (displayName/currentValue) format
            param_name = param.get('displayName', param.get('caption', param.get('name', '')))
            if not param_name:
                continue
            param_name = param_name.replace('[', '').replace(']', '')
            
            current_value = param.get('currentValue', param.get('value', ''))
            if not current_value:
                continue
            
            # Clean quotes
            if isinstance(current_value, str):
                current_value = current_value.strip('"')
            
            # Resolve Entity via _field_map (parameters = measures on main table)
            entity, prop = self._resolve_field_entity(param_name)
            
            filter_obj = {
                "name": f"Filter_{uuid.uuid4().hex[:12]}",
                "type": "Categorical",
                "field": {
                    "Column": {
                        "Expression": {"SourceRef": {"Entity": entity}},
                        "Property": prop
                    }
                },
                "filter": {
                    "Version": 2,
                    "From": [{"Name": "p", "Entity": entity, "Type": 0}],
                    "Where": [{
                        "Condition": {
                            "In": {
                                "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "p"}}, "Property": prop}}],
                                "Values": [[{"Literal": {"Value": _pbi_literal(current_value)}}]]
                            }
                        }
                    }]
                }
            }
            report_filters.append(filter_obj)
        
        return report_filters
    
    def _resolve_field_entity(self, field_name):
        """Resolves a field name to (entity_table, property_name) via _field_map"""
        clean = field_name.replace('[', '').replace(']', '')
        if hasattr(self, '_field_map'):
            # Direct match
            if clean in self._field_map:
                return self._field_map[clean]
            # Try without attr:/ prefix
            for prefix in ('attr:', ':'):
                if clean.startswith(prefix) and clean[len(prefix):] in self._field_map:
                    return self._field_map[clean[len(prefix):]]
            # Partial match (calc ID may contain Calculation_xxx)
            for key, val in self._field_map.items():
                if key == clean or val[1] == clean:
                    return val
        # Fallback: use main table (all calc columns are there)
        main = getattr(self, '_main_table', clean)
        return (main, clean)

    def _create_visual_filters(self, filters):
        """Creates visual-level filters from worksheet filters"""
        visual_filters = []
        
        # Tableau virtual fields that have no PBI equivalent
        skip_fields = {'Measure Names', 'Measure Values', 'Multiple Values',
                       ':Measure Names', ':Measure Values'}
        
        for f in filters:
            field = f.get('field', '')
            if not field:
                continue
            
            # Clean field name (remove Tableau brackets)
            clean_field = field.replace('[', '').replace(']', '')
            
            # Skip Tableau virtual fields (no PBI column exists)
            if clean_field in skip_fields or field.replace('[', '').replace(']', '') in skip_fields:
                continue

            # Skip date-part filters (yr:, qr:, etc.) — PBI cannot filter
            # a DateTime column with categorical date-part string values
            if f.get('date_part'):
                continue

            # Skip "all selected" and action filters (no data filtering needed)
            if f.get('type') == 'all':
                continue
            if clean_field.startswith('Action '):
                continue
            
            # Resolve Entity (table) and Property (column) via mapping
            entity, prop = self._resolve_field_entity(clean_field)
            
            filter_type = f.get('type', 'categorical')
            filter_mode = f.get('filter_mode', '')

            # Sprint 77: Relative date filter
            if filter_mode == 'relative-date':
                period = f.get('period', 'day')
                period_map = {'day': 0, 'week': 1, 'month': 2,
                              'quarter': 3, 'year': 4}
                period_type_map = {'last': 0, 'this': 1, 'next': 2}
                pbi_filter = {
                    "name": f"Filter_{uuid.uuid4().hex[:12]}",
                    "type": "RelativeDate",
                    "field": {
                        "Column": {
                            "Expression": {"SourceRef": {"Entity": entity}},
                            "Property": prop
                        }
                    },
                    "filter": {
                        "Version": 2,
                        "From": [{"Name": "t", "Entity": entity, "Type": 0}],
                        "Where": [{
                            "Condition": {
                                "RelativeDate": {
                                    "Expression": {
                                        "Column": {
                                            "Expression": {"SourceRef": {"Source": "t"}},
                                            "Property": prop
                                        }
                                    },
                                    "TimeUnit": period_map.get(period, 0),
                                    "TimeUnitCount": f.get('period_count', 1),
                                    "RelativeDateFilterType": period_type_map.get(
                                        f.get('period_type', 'last'), 0),
                                    "IncludeToday": True,
                                }
                            }
                        }]
                    }
                }
                visual_filters.append(pbi_filter)
                continue

            # Sprint 77: Context filter → report-level (emit as normal filter
            # with annotation — PBI evaluates all filters simultaneously)
            if filter_mode == 'context' and f.get('values'):
                pass  # fall through to categorical handling below

            if filter_type == 'range' or f.get('min') is not None:
                # Range filter (dates, numbers)
                pbi_filter = {
                    "name": f"Filter_{uuid.uuid4().hex[:12]}",
                    "type": "Advanced",
                    "field": {
                        "Column": {
                            "Expression": {"SourceRef": {"Entity": entity}},
                            "Property": prop
                        }
                    },
                    "filter": {
                        "Version": 2,
                        "From": [{"Name": "t", "Entity": entity, "Type": 0}],
                        "Where": []
                    }
                }
                conditions = []
                if f.get('min') is not None:
                    conditions.append({
                        "Comparison": {
                            "ComparisonKind": 2,  # >=
                            "Left": {"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": prop}},
                            "Right": {"Literal": {"Value": f"'{f['min']}'"}} 
                        }
                    })
                if f.get('max') is not None:
                    conditions.append({
                        "Comparison": {
                            "ComparisonKind": 3,  # <=
                            "Left": {"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": prop}},
                            "Right": {"Literal": {"Value": f"'{f['max']}'"}} 
                        }
                    })
                if conditions:
                    pbi_filter["filter"]["Where"] = [{"Condition": c} for c in conditions]
                    visual_filters.append(pbi_filter)
            else:
                # Categorical filter
                values = f.get('values', [])
                is_exclude = f.get('exclude', False)
                
                # Skip categorical filters with no values (empty Where breaks PBI)
                if not values:
                    continue
                
                pbi_filter = {
                    "name": f"Filter_{uuid.uuid4().hex[:12]}",
                    "type": "Categorical",
                    "field": {
                        "Column": {
                            "Expression": {"SourceRef": {"Entity": entity}},
                            "Property": prop
                        }
                    },
                    "filter": {
                        "Version": 2,
                        "From": [{"Name": "t", "Entity": entity, "Type": 0}],
                        "Where": []
                    }
                }
                
                condition = {
                    "In": {
                        "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": prop}}],
                        "Values": [[{"Literal": {"Value": _pbi_literal(v)}}] for v in values[:100]]
                    }
                }
                if is_exclude:
                    condition = {"Not": {"Expression": condition}}
                pbi_filter["filter"]["Where"].append({"Condition": condition})
                
                visual_filters.append(pbi_filter)
        
        return visual_filters
    
    def _build_visual_objects(self, ws_name, ws_data, visual_type):
        """Builds visual objects (title, colors, labels, legend, axes).

        Orchestrator that delegates to focused sub-methods.
        """
        objects = {}

        if not ws_data:
            return objects

        formatting = ws_data.get('formatting', {})
        mark_encoding = ws_data.get('mark_encoding', {})

        self._build_label_objects(objects, formatting, mark_encoding)
        self._build_legend_objects(objects, mark_encoding, formatting)
        self._build_axis_objects(objects, ws_data, visual_type)
        self._build_visual_styling_objects(objects, ws_data, visual_type, formatting, mark_encoding)
        self._build_color_encoding_objects(objects, ws_data, visual_type, mark_encoding)
        self._build_analytics_objects(objects, ws_data, visual_type, formatting)

        return objects

    # ── Visual-object sub-methods (extracted from _build_visual_objects) ──

    def _build_label_objects(self, objects, formatting, mark_encoding):
        """Data labels, label color, and font formatting."""
        # Data labels — from formatting.mark.mark-labels-show OR mark_encoding.label
        show_labels = False
        mark_fmt = formatting.get('mark', {})
        if isinstance(mark_fmt, dict):
            show_labels = mark_fmt.get('mark-labels-show', '').lower() == 'true'
        if mark_encoding.get('label', {}).get('show'):
            show_labels = True

        if show_labels:
            label_props = {
                "show": _L("true")
            }
            # Apply label font size
            label_info = mark_encoding.get('label', {})
            if label_info.get('font_size'):
                label_props["fontSize"] = _L(f"{label_info['font_size']}D")
            if label_info.get('font_color'):
                label_props["color"] = {
                    "solid": {"color": _L(f"'{label_info['font_color']}'")}
                }
            # Map label position (Tableau → PBI)
            pos_map = {'top': "'OutsideEnd'", 'center': "'InsideCenter'",
                       'bottom': "'InsideBase'", 'left': "'Left'", 'right': "'Right'"}
            if label_info.get('position') and label_info['position'] in pos_map:
                label_props["labelPosition"] = _L(pos_map[label_info['position']])
            objects["labels"] = [{"properties": label_props}]

        # Label color (from formatting.label.color)
        label_fmt = formatting.get('label', {})
        if isinstance(label_fmt, dict) and label_fmt.get('color'):
            if "labels" not in objects:
                objects["labels"] = [{"properties": {}}]
            objects["labels"][0]["properties"]["color"] = {
                "solid": {"color": _L(f"'{label_fmt['color']}'")}
            }

        # Font formatting (family + size from extracted formatting)
        font_props = formatting.get('font', {})
        if isinstance(font_props, dict):
            font_family = font_props.get('family', '')
            font_size = font_props.get('size', '')
            if font_family or font_size:
                if "labels" not in objects:
                    objects["labels"] = [{"properties": {}}]
                if font_family:
                    objects["labels"][0]["properties"]["fontFamily"] = _L(f"'{font_family}'")
                if font_size:
                    try:
                        fs_val = int(float(str(font_size).replace('pt', '').replace('px', '').strip()))
                        objects["labels"][0]["properties"]["fontSize"] = _L(f"{fs_val}D")
                    except (ValueError, TypeError):
                        logger.debug("Could not parse label fontSize: %s", font_size)

        # Number format mapping on labels
        fmt_info = formatting.get('number_format', formatting.get('format_string', ''))
        if fmt_info:
            pbi_fmt = self._convert_number_format(fmt_info)
            if pbi_fmt and "labels" in objects:
                objects["labels"][0]["properties"]["labelDisplayUnits"] = _L(f"'{pbi_fmt}'")

    def _build_legend_objects(self, objects, mark_encoding, formatting):
        """Legend configuration from color encoding."""
        color_field = mark_encoding.get('color', {}).get('field', '')
        if color_field and color_field != 'Multiple Values':
            legend_props = {
                "show": _L("true"),
            }
            # Extract legend position from formatting
            legend_fmt = formatting.get('legend', formatting.get('color-legend', {}))
            if isinstance(legend_fmt, dict):
                legend_pos = legend_fmt.get('position', legend_fmt.get('legend-position', ''))
                legend_pos_map = {
                    'right': "'Right'", 'left': "'Left'",
                    'top': "'Top'", 'bottom': "'Bottom'",
                    'top-right': "'TopRight'", 'bottom-right': "'BottomRight'",
                    'top-left': "'TopLeft'", 'bottom-left': "'BottomLeft'",
                }
                if legend_pos.lower() in legend_pos_map:
                    legend_props["position"] = _L(legend_pos_map[legend_pos.lower()])
                else:
                    legend_props["position"] = _L("'Right'")
                # Legend title
                legend_title = legend_fmt.get('title', '')
                if legend_title:
                    legend_props["titleText"] = _L(f"'{legend_title}'")
                    legend_props["showTitle"] = _L("true")
                # Legend font size
                legend_font_size = legend_fmt.get('font-size', '')
                if legend_font_size:
                    legend_props["fontSize"] = _L(f"{legend_font_size}D")
            else:
                legend_props["position"] = _L("'Right'")
            objects["legend"] = [{"properties": legend_props}]

    def _build_axis_objects(self, objects, ws_data, visual_type):
        """Axis display, explicit axes, dual axis, enhanced config, continuous/discrete, sync."""
        formatting = ws_data.get('formatting', {})

        # Axis display (formatting.axis.display)
        axis_fmt = formatting.get('axis', {})
        if isinstance(axis_fmt, dict):
            axis_display = axis_fmt.get('display', 'true')
            show_axis = axis_display.lower() != 'none' if axis_display else True
            if show_axis:
                objects["categoryAxis"] = [{
                    "properties": {
                        "show": _L("true")
                    }
                }]
                objects["valueAxis"] = [{
                    "properties": {
                        "show": _L("true")
                    }
                }]

        # Explicit axes (if extracted)
        axes_data = ws_data.get('axes', {})
        if axes_data:
            x_axis = axes_data.get('x', {})
            if x_axis:
                cat_props = {
                    "show": _L("true")
                }
                if x_axis.get('title'):
                    cat_props["titleText"] = _L(f"'{x_axis['title']}'")
                    cat_props["showAxisTitle"] = _L("true")
                if x_axis.get('reversed'):
                    cat_props["reverseOrder"] = _L("true")
                objects["categoryAxis"] = [{"properties": cat_props}]

            y_axis = axes_data.get('y', {})
            if y_axis:
                val_props = {
                    "show": _L("true")
                }
                if y_axis.get('title'):
                    val_props["titleText"] = _L(f"'{y_axis['title']}'")
                    val_props["showAxisTitle"] = _L("true")
                # Apply axis range (min/max)
                if not y_axis.get('auto_range', True):
                    if y_axis.get('range_min') is not None:
                        val_props["start"] = _L(f"{y_axis['range_min']}D")
                    if y_axis.get('range_max') is not None:
                        val_props["end"] = _L(f"{y_axis['range_max']}D")
                # Apply log scale
                if y_axis.get('scale') == 'log':
                    val_props["axisScale"] = _L("'Log'")
                # Apply reversed axis
                if y_axis.get('reversed'):
                    val_props["reverseOrder"] = _L("true")
                objects["valueAxis"] = [{"properties": val_props}]

            # Dual-axis / combo-chart secondary axis
            if axes_data.get('dual_axis') and visual_type in ('lineClusteredColumnComboChart', 'lineStackedColumnComboChart'):
                y2_props = {
                    "show": _L("true")
                }
                # If synced, set same scale properties
                if axes_data.get('dual_axis_sync'):
                    if not y_axis.get('auto_range', True):
                        if y_axis.get('range_min') is not None:
                            y2_props["start"] = val_props.get("start", {})
                        if y_axis.get('range_max') is not None:
                            y2_props["end"] = val_props.get("end", {})
                    if y_axis.get('scale') == 'log':
                        y2_props["axisScale"] = _L("'Log'")
                objects["y1AxisReferenceLine"] = [{"properties": {}}]  # Marker for combo secondary axis

        # Enhanced axis config (label rotation, show toggles)
        axes_detail = ws_data.get('axes', {})
        if axes_detail:
            for axis_key, axis_obj_key in [('x', 'categoryAxis'), ('y', 'valueAxis')]:
                ax = axes_detail.get(axis_key, {})
                if not ax:
                    continue
                if axis_obj_key in objects:
                    props = objects[axis_obj_key][0].get("properties", {})
                else:
                    props = {"show": _L("true")}
                if ax.get('show_title') is False:
                    props["showAxisTitle"] = _L("false")
                if ax.get('show_label') is False:
                    props["show"] = _L("false")
                if ax.get('label_rotation'):
                    try:
                        rot = int(float(ax['label_rotation']))
                        if rot != 0:
                            props["labelAngle"] = _L(f"{rot}L")
                    except (ValueError, TypeError):
                        logger.debug("Could not parse axis label_rotation: %s", ax.get('label_rotation'))
                if ax.get('format'):
                    props["labelDisplayUnits"] = _L("'0L'")
                objects[axis_obj_key] = [{"properties": props}]

        # Continuous vs discrete axis scale
        for axis_key, axis_obj_key in [('x', 'categoryAxis'), ('y', 'valueAxis')]:
            ax = axes_detail.get(axis_key, {})
            if ax.get('is_continuous') is True:
                if axis_obj_key in objects:
                    objects[axis_obj_key][0]["properties"]["axisType"] = _L("'Continuous'")
            elif ax.get('is_continuous') is False and axis_obj_key in objects:
                objects[axis_obj_key][0]["properties"]["axisType"] = _L("'Categorical'")

        # Dual-axis synchronization (secShow / secAxisLabel)
        dual_axis = ws_data.get('dual_axis', {})
        if isinstance(dual_axis, dict) and dual_axis.get('enabled'):
            if "valueAxis" not in objects:
                objects["valueAxis"] = [{"properties": {"show": _L("true")}}]
            if dual_axis.get('synchronized'):
                objects["valueAxis"][0]["properties"]["secShow"] = _L("true")
                objects["valueAxis"][0]["properties"]["secAxisLabel"] = _L("true")

    def _build_visual_styling_objects(self, objects, ws_data, visual_type, formatting, mark_encoding):
        """Background, table formatting, data bars, totals, padding."""
        color_enc = mark_encoding.get('color', {})

        # Background color
        bg_color = formatting.get('background_color', '')
        if not bg_color and isinstance(formatting.get('pane', {}), dict):
            bg_color = formatting.get('pane', {}).get('background-color', '')
        if bg_color:
            objects["visualContainerStyle"] = [{
                "properties": {
                    "background": {
                        "solid": {"color": _L(f"'{bg_color}'")}
                    }
                }
            }]

        # Table/matrix-specific formatting (header font, row banding, grid)
        if visual_type in ('tableEx', 'table', 'matrix'):
            header_style = formatting.get('header_style', formatting.get('column-header_style', {}))
            if isinstance(header_style, dict):
                col_headers_props = {}
                if header_style.get('font-size'):
                    col_headers_props["fontSize"] = _L(f"{header_style['font-size']}D")
                if header_style.get('font-weight') == 'bold':
                    col_headers_props["bold"] = _L("true")
                if header_style.get('font-color'):
                    col_headers_props["fontColor"] = {
                        "solid": {"color": _L(f"'{header_style['font-color']}'")}
                    }
                if col_headers_props:
                    objects["columnHeaders"] = [{"properties": col_headers_props}]

            # Row banding (alternating row colors)
            row_style = formatting.get('worksheet_style', {})
            if isinstance(row_style, dict) and row_style.get('band-color'):
                objects["values"] = [{
                    "properties": {
                        "backColor": {
                            "solid": {"color": _L(f"'{row_style['band-color']}'")}
                        }
                    }
                }]

            # Grid/border
            if isinstance(header_style, dict) and header_style.get('border-style', 'none') != 'none':
                grid_props = {"show": _L("true")}
                if header_style.get('border-color'):
                    grid_props["color"] = {
                        "solid": {"color": _L(f"'{header_style['border-color']}'")}
                    }
                objects["gridlines"] = [{"properties": grid_props}]

        # Data bars for table/matrix columns
        if visual_type in ('tableEx', 'matrix', 'pivotTable', 'table'):
            value_fields = [f for f in ws_data.get('fields', [])
                            if f.get('role') == 'measure']
            if value_fields and color_enc.get('type') == 'quantitative':
                data_bar_props = {
                    "show": _L("true"),
                    "positiveColor": {"solid": {"color": _L("'#4472C4'")}},
                    "negativeColor": {"solid": {"color": _L("'#ED7D31'")}},
                }
                objects["dataBar"] = [{"properties": data_bar_props}]

            # Default row banding fallback
            if "values" not in objects:
                objects["values"] = [{
                    "properties": {
                        "backColor": {"solid": {"color": _L("'#F2F2F2'")}}
                    }
                }]

            # Totals and subtotals
            totals = ws_data.get('totals', {})
            if totals and (totals.get('grand_totals') or totals.get('subtotals')):
                objects.setdefault("total", [{"properties": {}}])
                objects["total"][0]["properties"]["totals"] = _L("true")
                if totals.get('subtotals'):
                    objects.setdefault("subTotals", [{"properties": {}}])
                    objects["subTotals"][0]["properties"]["rowSubtotals"] = _L("true")

        # Per-object padding
        padding = ws_data.get('padding', {})
        if isinstance(padding, dict) and padding:
            pad_props = {}
            for side in ('top', 'bottom', 'left', 'right'):
                val = padding.get(f'padding_{side}', padding.get(f'margin_{side}', 0))
                if val:
                    pad_props[side] = _L(f"{val}L")
            if pad_props:
                objects["visualContainerPadding"] = [{"properties": pad_props}]

    def _build_color_encoding_objects(self, objects, ws_data, visual_type, mark_encoding):
        """Conditional formatting gradient, per-value colors, stepped thresholds."""
        color_enc = mark_encoding.get('color', {})
        color_mode = color_enc.get('type', '')  # 'quantitative' → gradient, 'categorical' → distinct
        if color_mode == 'quantitative' or color_enc.get('palette', ''):
            # Data-driven color scale
            palette_colors = color_enc.get('palette_colors', [])
            if len(palette_colors) >= 2:
                # Generate proper PBI gradient rule with min/max/mid colors
                gradient_rule = {
                    "properties": {
                        "fill": {
                            "solid": {"color": _L(f"'{palette_colors[0]}'")}
                        }
                    },
                    "rules": [{
                        "inputRole": "Y",
                        "gradient": {
                            "min": {
                                "color": _L(f"'{palette_colors[0]}'")
                            },
                            "max": {
                                "color": _L(f"'{palette_colors[-1]}'")
                            }
                        }
                    }]
                }
                # Add midpoint color if 3+ colors
                if len(palette_colors) >= 3:
                    mid_color = palette_colors[len(palette_colors) // 2]
                    gradient_rule["rules"][0]["gradient"]["mid"] = {
                        "color": _L(f"'{mid_color}'")
                    }
                objects["dataPoint"] = [gradient_rule]
            elif len(palette_colors) == 1:
                objects["dataPoint"] = [{
                    "properties": {
                        "fill": {
                            "solid": {"color": _L(f"'{palette_colors[0]}'")}
                        }
                    }
                }]

        # Per-value color assignments (categorical color map)
        if not objects.get("dataPoint"):
            color_values = color_enc.get('color_values', {})
            if color_values:
                dp_rules = []
                for val, clr in list(color_values.items())[:20]:
                    dp_rules.append({
                        "properties": {
                            "fill": {"solid": {"color": _L(f"'{clr}'")}}
                        }
                    })
                if dp_rules:
                    objects["dataPoint"] = dp_rules

        # Stepped color thresholds (discrete conditional formatting)
        # Produces PBI rules-based conditional formatting with numeric thresholds
        if not objects.get("dataPoint"):
            color_thresholds = color_enc.get('thresholds', [])
            if color_thresholds and len(color_thresholds) >= 2:
                # Sort thresholds by value for proper rule ordering
                sorted_thresh = sorted(
                    [t for t in color_thresholds if t.get('value') is not None],
                    key=lambda t: float(t['value']),
                )
                # Add thresholds without values (catch-all) at end
                no_value = [t for t in color_thresholds if t.get('value') is None]
                all_thresh = sorted_thresh + no_value

                # Build rules-based conditional formatting
                cf_rules = []
                for idx, thresh in enumerate(all_thresh):
                    color = thresh.get('color', '#cccccc')
                    rule = {
                        "properties": {
                            "fill": {"solid": {"color": _L(f"'{color}'")}}
                        }
                    }
                    if thresh.get('value') is not None:
                        rule["properties"]["inputValue"] = _L(f"{thresh['value']}D")
                        # Add comparison operator for stepped ranges
                        if idx < len(sorted_thresh) - 1:
                            rule["properties"]["operator"] = _L("'LessThanOrEqual'")
                        else:
                            rule["properties"]["operator"] = _L("'GreaterThan'")
                    cf_rules.append(rule)
                objects["dataPoint"] = cf_rules

                # Also set up the conditionalFormatting array for the visual
                color_field = color_enc.get('field', '')
                if color_field and cf_rules:
                    objects["conditionalFormatting"] = [{
                        "properties": {
                            "show": _L("true"),
                            "colorStyle": _L("'rulesGradient'"),
                        }
                    }]

    def _build_analytics_objects(self, objects, ws_data, visual_type, formatting):
        """Reference lines, trend lines, annotations, forecast, map, analytics stats, small multiples."""
        main_table = getattr(self, '_main_table', 'Table')

        # Reference lines (Tableau reference lines/bands → PBI constant + dynamic lines)
        ref_lines = ws_data.get('reference_lines', [])
        if ref_lines:
            y_ref_lines = []
            dynamic_ref_lines = []
            for ref in ref_lines:
                ref_value = ref.get('value', 0)
                ref_label = ref.get('label', '')
                ref_color = ref.get('color', '#666666')
                ref_style = ref.get('style', 'dashed')
                ref_type = ref.get('computation', ref.get('type', 'constant')).lower()

                if ref_type in ('average', 'median', 'percentile', 'min', 'max'):
                    # Dynamic reference line (analytics pane)
                    from visual_generator import _build_dynamic_reference_line
                    dyn_line = _build_dynamic_reference_line(
                        ref_type=ref_type,
                        field_name=ref.get('field'),
                        table_name=main_table,
                        label=ref_label,
                        color=ref_color,
                        style=ref_style,
                    )
                    if dyn_line:
                        dynamic_ref_lines.append(dyn_line)
                else:
                    # Constant reference line
                    line_def = {
                        "type": "Constant",
                        "value": str(ref_value),
                        "show": _L("true"),
                        "displayName": _L(f"'{ref_label}'"),
                        "color": {"solid": {"color": _L(f"'{ref_color}'")}},
                        "style": _L(f"'{ref_style}'") if ref_style in ('solid', 'dashed', 'dotted') else _L("'dashed'"),
                    }
                    y_ref_lines.append(line_def)

            if y_ref_lines or dynamic_ref_lines:
                if "valueAxis" not in objects:
                    objects["valueAxis"] = [{"properties": {"show": _L("true")}}]
                all_lines = y_ref_lines + dynamic_ref_lines
                objects["valueAxis"][0]["properties"]["referenceLine"] = all_lines

        # Trend lines (analytics pane)
        trend_lines = ws_data.get('trend_lines', [])
        if trend_lines:
            trend_objs = []
            for tl in trend_lines:
                trend_type = tl.get('type', 'linear').capitalize()
                if trend_type not in ('Linear', 'Exponential', 'Logarithmic',
                                      'Polynomial', 'Power', 'MovingAverage'):
                    trend_type = 'Linear'
                trend_obj = {
                    "show": _L("true"),
                    "lineColor": {"solid": {"color": _L(f"'{tl.get('color', '#666666')}'")}}
                }
                if tl.get('show_equation'):
                    trend_obj["displayEquation"] = _L("true")
                if tl.get('show_r_squared'):
                    trend_obj["displayRSquared"] = _L("true")
                trend_objs.append({"properties": trend_obj})
            objects["trend"] = trend_objs

        # Annotations → subtitle text
        annotations = ws_data.get('annotations', [])
        if annotations:
            anno_texts = [a.get('text', '') for a in annotations if a.get('text')]
            if anno_texts:
                subtitle_text = "; ".join(anno_texts[:3])
                objects.setdefault("subTitle", [{"properties": {}}])
                objects["subTitle"][0]["properties"]["show"] = _L("true")
                objects["subTitle"][0]["properties"]["text"] = _L(json.dumps(subtitle_text))

        # Forecast config (analytics pane)
        forecasts = ws_data.get('forecasting', [])
        if forecasts:
            fc = forecasts[0]
            forecast_obj = {
                "show": _L("true"),
                "forecastLength": _L(f"{fc.get('periods', 5)}L"),
                "confidenceBandStyle": _L("'fill'"),
            }
            ci = fc.get('prediction_interval', '95')
            forecast_obj["confidenceLevel"] = _L(f"'{ci}'")
            if fc.get('ignore_last', '0') != '0':
                forecast_obj["ignoreLast"] = _L(f"{fc['ignore_last']}L")
            objects["forecast"] = [{"properties": forecast_obj}]

        # Map options (washout/transparency + style)
        map_opts = ws_data.get('map_options', {})
        if map_opts and visual_type in ('map', 'filledMap'):
            map_props = {}
            washout = map_opts.get('washout', '0.0')
            try:
                wo_val = float(washout)
                if wo_val > 0:
                    map_props["transparency"] = _L(f"{int(wo_val * 100)}L")
            except (ValueError, TypeError):
                logger.debug("Could not parse map washout: %s", washout)
            style = map_opts.get('style', 'road')
            style_map = {'normal': "'road'", 'light': "'grayscale'",
                         'dark': "'darkGrayscale'", 'satellite': "'aerial'",
                         'streets': "'road'"}
            pbi_style = style_map.get(style.lower(), "'road'")
            map_props["mapStyle"] = _L(pbi_style)
            if map_props:
                objects["mapControl"] = [{"properties": map_props}]

        # Reference bands and statistical reference lines (analytics_stats)
        analytics_stats = ws_data.get('analytics_stats', [])
        for stat in analytics_stats:
            if stat.get('type') == 'distribution_band':
                band_from = stat.get('value_from', '')
                band_to = stat.get('value_to', '')
                if band_from and band_to:
                    if "valueAxis" not in objects:
                        objects["valueAxis"] = [{"properties": {"show": _L("true")}}]
                    objects["valueAxis"][0]["properties"].setdefault("referenceLine", [])
                    objects["valueAxis"][0]["properties"]["referenceLine"].append({
                        "type": "Band",
                        "lowerBound": str(band_from),
                        "upperBound": str(band_to),
                        "transparency": _L("50L"),
                        "show": _L("true"),
                    })
            elif stat.get('type') in ('stat_line', 'stat_reference'):
                comp = stat.get('computation', stat.get('stat', ''))
                stat_map = {'mean': 'Average', 'median': 'Median',
                            'constant': 'Constant', 'percentile': 'Percentile',
                            'mode': 'Average'}
                stat_type = stat_map.get(comp.lower(), 'Average')
                if "valueAxis" not in objects:
                    objects["valueAxis"] = [{"properties": {"show": _L("true")}}]
                objects["valueAxis"][0]["properties"].setdefault("referenceLine", [])
                objects["valueAxis"][0]["properties"]["referenceLine"].append({
                    "type": stat_type,
                    "show": _L("true"),
                    "style": _L("'dashed'"),
                })

        # Small multiples formatting
        sm_field = ws_data.get('small_multiples', '')
        if not sm_field:
            pages_shelf = ws_data.get('pages_shelf', {})
            if isinstance(pages_shelf, dict):
                sm_field = pages_shelf.get('field', '')
        if sm_field:
            objects["smallMultiple"] = [{"properties": {
                "layoutMode": _L("'Flow'"),
                "showChartTitle": _L("true"),
            }}]
    
    def _create_slicer_visual(self, visual_id, x, y, w, h, field_name, table_name, z_order,
                               slicer_mode='Dropdown', title=None):
        """Creates a slicer visual for a filter/parameter control with field binding.

        Args:
            slicer_mode: PBI slicer mode string — ``'Dropdown'``, ``'List'``,
                ``'Between'`` (range/slider), ``'Basic'`` (relative date),
                ``'Date'`` (date picker), or ``'Search'`` (wildcard text).
            title: Display title for the slicer. Defaults to field_name.
        """
        clean_field = field_name.replace('[', '').replace(']', '')
        clean_table = table_name.replace("'", "''") if table_name else getattr(self, '_main_table', 'Table')
        
        # Map extended modes to PBI mode strings
        pbi_mode = slicer_mode
        if slicer_mode == 'Search':
            pbi_mode = 'Dropdown'  # Dropdown with search enabled
        elif slicer_mode == 'Date':
            pbi_mode = 'Basic'  # Basic = date picker in PBI

        # Build objects with the correct mode
        slicer_objects = {
            "data": [{
                "properties": {
                    "mode": _L(f"'{pbi_mode}'")
                }
            }],
            "header": [{
                "properties": {
                    "show": _L("true")
                }
            }]
        }

        # For slider / range mode, add numericInputStyle
        if slicer_mode == 'Between':
            slicer_objects["numericInputStyle"] = [{
                "properties": {
                    "show": _L("true")
                }
            }]

        # For Search/wildcard mode, enable search box
        if slicer_mode == 'Search':
            slicer_objects["selection"] = [{
                "properties": {
                    "selectAllCheckboxEnabled": _L("true")
                }
            }]
            slicer_objects["search"] = [{
                "properties": {
                    "enabled": _L("true")
                }
            }]

        # For relative date mode, add relative date config
        if slicer_mode == 'Basic':
            slicer_objects["relativeDate"] = [{
                "properties": {
                    "includeToday": _L("true")
                }
            }]

        slicer = {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.5.0/schema.json",
            "name": visual_id,
            "position": {
                "x": x, "y": y, "z": z_order * 1000,
                "height": h, "width": w,
                "tabOrder": z_order * 1000
            },
            "visual": {
                "visualType": "slicer",
                "objects": slicer_objects,
                "visualContainerObjects": {
                    "title": [{
                        "properties": {
                            "show": _L("true"),
                            "text": _L(f"'{title or clean_field or clean_table}'")
                        }
                    }]
                },
                "drillFilterOtherVisuals": True
            }
        }
        
        # Add query binding (PBIR queryState format with RoleProjection)
        if clean_field and clean_table:
            slicer["visual"]["query"] = {
                "queryState": {
                    "Values": {
                        "projections": [{
                            "field": {
                                "Column": {
                                    "Expression": {"SourceRef": {"Entity": clean_table}},
                                    "Property": clean_field
                                }
                            },
                            "queryRef": f"{clean_table}.{clean_field}"
                        }]
                    }
                }
            }
        
        return slicer
    
    def _detect_slicer_mode(self, obj, column_name, converted_objects):
        """Detect the best PBI slicer mode for a Tableau filter control.

        Returns one of: ``'Dropdown'``, ``'List'``, ``'Between'``, ``'Basic'``,
            ``'Date'``, ``'Search'``.
        """
        param_ref = obj.get('param', '')

        # Sprint 77: Check filter_mode from classified filter data
        filter_mode = obj.get('filter_mode', '')
        if filter_mode == 'relative-date':
            return 'Basic'
        if filter_mode == 'wildcard':
            return 'Search'
        if filter_mode == 'top-n':
            return 'List'
        if filter_mode == 'range':
            return 'Between'

        # Check if this is a range parameter → slider (Between)
        for param in converted_objects.get('parameters', []):
            p_name = param.get('name', '').replace('[', '').replace(']', '')
            if p_name and (p_name in param_ref or p_name == column_name):
                if param.get('domain_type') == 'range':
                    return 'Between'
                if param.get('domain_type') == 'list':
                    return 'List'

        # Check column data type across datasources
        col_lower = column_name.lower()
        value_count = 0
        for ds in converted_objects.get('datasources', []):
            for table in ds.get('tables', []):
                for col in table.get('columns', []):
                    name = (col.get('caption', '') or col.get('name', '')).lower()
                    if name == col_lower:
                        dtype = col.get('datatype', '').lower()
                        if dtype in ('date', 'datetime'):
                            return 'Date'
                        if dtype in ('integer', 'real', 'float', 'number'):
                            return 'Between'
                        # Track cardinality hint
                        card = col.get('cardinality', 0)
                        if card:
                            value_count = card

        # High cardinality (>20) → Dropdown, low → List
        if value_count and value_count <= 20:
            return 'List'

        # Default to Dropdown for categorical text fields
        return 'Dropdown'

    def _create_page_navigator(self, visuals_dir, page_width, page_height, z_index):
        """Create a pageNavigator visual (Tableau dashboard tab strip equivalent).

        Places a horizontal page navigator bar at the bottom of the page.
        """
        visual_id = uuid.uuid4().hex[:20]
        visual_dir = os.path.join(visuals_dir, visual_id)
        os.makedirs(visual_dir, exist_ok=True)

        nav_height = 40
        visual_json = {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.5.0/schema.json",
            "name": visual_id,
            "position": {
                "x": 0,
                "y": page_height - nav_height,
                "z": z_index * 1000,
                "height": nav_height,
                "width": page_width,
                "tabOrder": z_index * 1000,
            },
            "visual": {
                "visualType": "pageNavigator",
                "objects": {
                    "content": [{
                        "properties": {
                            "navigationStyle": {"expr": {"Literal": {"Value": "'Tabs'"}}},
                            "showTooltips": {"expr": {"Literal": {"Value": "true"}}},
                        }
                    }]
                }
            },
        }
        _write_json(os.path.join(visual_dir, 'visual.json'), visual_json)

    def _create_pages_shelf_slicer(self, visuals_dir, pages_shelf, scale_x, scale_y,
                                    visual_count, converted_objects):
        """Create an animation-hint slicer from Tableau Pages shelf.

        In Tableau the Pages shelf allows playback through dimension values;
        Power BI has no direct equivalent.  We create a standard slicer bound
        to the same field and annotate it with a comment so that the user
        knows it originated from a Pages shelf.
        """
        field = pages_shelf.get('field', '')
        if not field:
            return
        table_name = self._find_column_table(field, converted_objects)
        visual_id = uuid.uuid4().hex[:20]
        visual_dir = os.path.join(visuals_dir, visual_id)
        os.makedirs(visual_dir, exist_ok=True)
        slicer = self._create_slicer_visual(
            visual_id, 10, 10, 400, 50, field, table_name, visual_count)
        slicer.setdefault('visual', {}).setdefault('objects', {})
        slicer['visual']['objects']['general'] = [{
            'properties': {
                'comments': _L("'Pages Shelf / Play Axis: animate through values'")
            }
        }]
        _write_json(os.path.join(visual_dir, 'visual.json'), slicer)

    @staticmethod
    def _convert_number_format(tableau_format):
        """Convert Tableau number format string to PBI display units / format.

        Common Tableau patterns::

            ###,###    → #,0
            $#,#00.00  → $#,0.00
            0.0%       → 0.0%
            0.00       → 0.00
        """
        if not tableau_format or not isinstance(tableau_format, str):
            return ''
        fmt = tableau_format.strip()
        # Already a PBI-compatible format
        if fmt in ('0', '0.0', '0.00', '#,0', '#,0.0', '#,0.00',
                   '0%', '0.0%', '0.00%'):
            return fmt
        # Currency
        if '$' in fmt:
            return fmt.replace('#,#', '#,0').replace('##', '#0')
        # Percentage
        if '%' in fmt:
            return fmt
        # Thousands separator
        if ',' in fmt:
            return fmt.replace('#,#', '#,0')
        return fmt

    def _create_drillthrough_pages(self, pages_dir, page_names, worksheets,
                                    converted_objects):
        """Create drill-through pages from Tableau filter/set actions.

        Inspects actions for ``filter`` or ``set-value`` types that target
        specific worksheets.  Each unique target becomes a PBI drill-through
        page with ``pageType: "Drillthrough"`` and a drillthrough filter on
        the source field.
        """
        actions = converted_objects.get('actions', [])
        if not actions:
            return

        # Collect unique target worksheets from filter/set actions
        drillthrough_targets = {}  # target_ws_name → source_field
        for action in actions:
            a_type = action.get('type', '')
            if a_type not in ('filter', 'set-value'):
                continue
            target_sheets = action.get('target_worksheets', [])
            if not target_sheets:
                target = action.get('target_worksheet', '')
                if target:
                    target_sheets = [target]
            source_field = action.get('field', action.get('source_field', ''))

            for ts in target_sheets:
                # Skip if the target is already a dashboard page (not drill-through)
                if ts not in drillthrough_targets:
                    drillthrough_targets[ts] = source_field

        if not drillthrough_targets:
            return

        for target_ws, source_field in drillthrough_targets.items():
            ws_data = self._find_worksheet(worksheets, target_ws)
            if not ws_data:
                continue

            dt_page_name = f"Drillthrough_{uuid.uuid4().hex[:12]}"
            dt_display = f"Drillthrough - {target_ws}"
            page_names.append(dt_page_name)

            dt_dir = os.path.join(pages_dir, dt_page_name)
            os.makedirs(dt_dir, exist_ok=True)

            dt_page = {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.0.0/schema.json",
                "name": dt_page_name,
                "displayName": dt_display,
                "displayOption": "FitToPage",
                "height": 720,
                "width": 1280,
                "pageType": "Drillthrough"
            }

            # Add drill-through filter if source field is known
            if source_field:
                clean_field = source_field.replace('[', '').replace(']', '')
                table_name = self._find_column_table(clean_field, converted_objects)
                if table_name:
                    dt_page["drillthrough"] = {
                        "filters": [{
                            "name": f"Filter_{clean_field}",
                            "field": {
                                "Column": {
                                    "Expression": {"SourceRef": {"Entity": table_name}},
                                    "Property": clean_field
                                }
                            },
                            "type": "Categorical"
                        }]
                    }

            _write_json(os.path.join(dt_dir, 'page.json'), dt_page)

            # Create visuals on the drill-through page
            dt_visuals_dir = os.path.join(dt_dir, 'visuals')
            os.makedirs(dt_visuals_dir, exist_ok=True)
            self._create_visual_worksheet(
                dt_visuals_dir, ws_data,
                {'type': 'worksheetReference', 'worksheetName': target_ws,
                 'position': {'x': 0, 'y': 0, 'w': 1280, 'h': 720}},
                1.0, 1.0, 0, worksheets, converted_objects
            )
            print(f"  [Drillthrough] page '{dt_display}' created")

    def _find_column_table(self, column_name, converted_objects):
        """Finds the table containing a given column"""
        datasources = converted_objects.get('datasources', [])
        for ds in datasources:
            for table in ds.get('tables', []):
                for col in table.get('columns', []):
                    col_caption = col.get('caption', col.get('name', ''))
                    if col_caption == column_name or col.get('name', '') == column_name:
                        return table.get('name', '')
                # Also search in calculations
                for calc in ds.get('calculations', []):
                    calc_caption = calc.get('caption', '')
                    if calc_caption == column_name:
                        # The calculation is in the main table of this datasource
                        tables = ds.get('tables', [])
                        if tables:
                            return tables[0].get('name', '')
        return ''
    
    def _detect_script_visual(self, ws_data, converted_objects):
        """Check if a worksheet uses SCRIPT_* analytics extensions.

        Scans the worksheet's fields against the project's calculation
        formulas.  Returns the first ``script_info`` dict (from
        ``detect_script_functions``) if a SCRIPT_* call is found, else
        ``None``.
        """
        if not ws_data:
            return None

        # Gather all raw formulas for this worksheet's fields
        field_names = set()
        for f in ws_data.get('fields', []):
            fname = self._clean_field_name(f.get('name', ''))
            if fname:
                field_names.add(fname)

        # Search calculations for SCRIPT_* usage
        try:
            from dax_converter import detect_script_functions
        except ImportError:
            return None

        if field_names:
            calcs = converted_objects.get('calculations', [])
            for calc in calcs:
                calc_name = calc.get('caption', calc.get('name', '')).strip('[]')
                raw_formula = calc.get('formula', '')
                if not raw_formula:
                    continue
                # Check if this calculation is used in the worksheet
                if calc_name in field_names or calc.get('name', '').strip('[]') in field_names:
                    scripts = detect_script_functions(raw_formula)
                    if scripts:
                        return scripts[0]

        # Also check fields directly for embedded SCRIPT_* in mark_encoding
        mark_enc = ws_data.get('mark_encoding', {})
        for enc_key, enc_val in mark_enc.items():
            if isinstance(enc_val, dict):
                formula = enc_val.get('formula', '')
                if formula:
                    scripts = detect_script_functions(formula)
                    if scripts:
                        return scripts[0]

        return None

    def _find_worksheet(self, worksheets, name):
        """Finds a worksheet by name"""
        for ws in worksheets:
            if ws.get('name') == name:
                return ws
        return None
    
    def _generate_automation_artifacts(self, project_dir, report_name, converted_objects):
        """Generate post-migration automation artifacts (RLS script, credential template)."""
        try:
            from powerbi_import.permission_mapper import (
                generate_rls_powershell, generate_credential_template,
            )
        except ImportError:
            return

        # RLS PowerShell script — only if user_filters / RLS roles exist
        user_filters = converted_objects.get('user_filters', [])
        if user_filters:
            rls_path = os.path.join(project_dir, 'assign_rls_roles.ps1')
            roles = []
            for uf in user_filters:
                roles.append({
                    'name': uf.get('role_name', uf.get('name', 'DefaultRole')),
                    'members': uf.get('users', uf.get('members', [])),
                })
            result = generate_rls_powershell(roles, rls_path, dataset_name=report_name)
            if result:
                print(f"  ✓ RLS PowerShell script: {rls_path}")

        # Credential template — always generate if datasources have connections
        datasources = converted_objects.get('datasources', [])
        if datasources:
            cred_path = os.path.join(project_dir, 'credentials_template.json')
            result = generate_credential_template(datasources, cred_path)
            if result:
                print(f"  ✓ Credential template: {cred_path}")

    def create_metadata(self, project_dir, report_name, converted_objects):
        """Creates migration metadata file for documentation."""
        # Count visuals and pages from the generated report
        pages_count = 0
        visuals_count = 0
        report_def = os.path.join(project_dir, f"{report_name}.Report", "definition", "pages")
        if os.path.isdir(report_def):
            for entry in os.listdir(report_def):
                entry_path = os.path.join(report_def, entry)
                # Only count pages that have page.json (skip stale leftovers)
                if (os.path.isdir(entry_path) and entry.startswith('ReportSection')
                        and os.path.isfile(os.path.join(entry_path, 'page.json'))):
                    pages_count += 1
                    vis_dir = os.path.join(entry_path, 'visuals')
                    if os.path.isdir(vis_dir):
                        # Only count visual dirs that have visual.json
                        visuals_count += len([d for d in os.listdir(vis_dir)
                                              if os.path.isdir(os.path.join(vis_dir, d))
                                              and os.path.isfile(os.path.join(vis_dir, d, 'visual.json'))])

        # Check for theme
        theme_applied = os.path.exists(os.path.join(
            project_dir, f"{report_name}.Report", "definition",
            "RegisteredResources", "TableauMigrationTheme.json"
        ))

        # Read TMDL stats
        tmdl_stats = {}
        tables_dir = os.path.join(project_dir, f"{report_name}.SemanticModel",
                                  "definition", "tables")
        if os.path.isdir(tables_dir):
            tmdl_stats['tables'] = len([f for f in os.listdir(tables_dir) if f.endswith('.tmdl')])

        # Count measures and relationships from TMDL files
        measures_count = 0
        columns_count = 0
        if os.path.isdir(tables_dir):
            for tmdl_file in os.listdir(tables_dir):
                if tmdl_file.endswith('.tmdl'):
                    try:
                        with open(os.path.join(tables_dir, tmdl_file), 'r', encoding='utf-8') as f:
                            content = f.read()
                        measures_count += content.count('\n\tmeasure ')
                        columns_count += content.count('\n\tcolumn ')
                    except (IOError, OSError) as exc:
                        logger.warning("Could not read TMDL file %s for stats: %s", tmdl_file, exc)
        tmdl_stats['measures'] = measures_count
        tmdl_stats['columns'] = columns_count

        relationships_count = 0
        rels_path = os.path.join(project_dir, f"{report_name}.SemanticModel",
                                 "definition", "relationships.tmdl")
        if os.path.isfile(rels_path):
            try:
                with open(rels_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                relationships_count = content.count('\nrelationship ')
            except (IOError, OSError) as exc:
                logger.warning("Could not read relationships.tmdl for stats: %s", exc)
        tmdl_stats['relationships'] = relationships_count

        # Collect visual type mappings used (Tableau mark → PBI visual)
        visual_types_used = {}
        visual_details = []  # per-worksheet detail for HTML report
        for ws in converted_objects.get('worksheets', []):
            ws_name = ws.get('name', 'Unknown')
            mark = ws.get('mark_type', 'Automatic')
            pbi_type = ws.get('chart_type', 'clusteredBarChart')
            visual_types_used[ws_name] = mark

            # Collect field names and classify as dim/measure
            ws_fields = ws.get('fields', [])
            dim_names = []
            mea_names = []
            for f in ws_fields:
                fname = f.get('name', '')
                # Strip Tableau derivation prefixes
                fname = _RE_DERIVATION_PREFIX.sub('', fname)
                if not fname or fname in (':Measure Names', 'Measure Names',
                                          ':Measure Values', 'Measure Values',
                                          'Multiple Values',
                                          'Longitude (generated)', 'Latitude (generated)'):
                    continue
                if f.get('shelf') == 'measure_value' or (
                    hasattr(self, '_measure_names') and fname in self._measure_names
                ):
                    mea_names.append(fname)
                else:
                    dim_names.append(fname)
            visual_details.append({
                'worksheet': ws_name,
                'tableau_mark': mark,
                'pbi_visual': pbi_type,
                'dimensions': dim_names,
                'measures': mea_names,
                'field_count': len(dim_names) + len(mea_names),
            })

        # Collect approximation warnings from visual generation
        from powerbi_import.visual_generator import get_approximation_note
        approximations = []
        for ws_name, mark in visual_types_used.items():
            note = get_approximation_note(mark)
            if note:
                approximations.append({"worksheet": ws_name, "source_type": mark, "note": note})

        # Theme detail
        theme_detail = {}
        if theme_applied:
            theme_detail['status'] = 'applied'
        else:
            has_colors = any(
                d.get('formatting', {}).get('background_color')
                for d in converted_objects.get('dashboards', [])
            )
            theme_detail['status'] = 'skipped'
            theme_detail['reason'] = 'no dashboard colors detected' if not has_colors else 'generation error'

        metadata = {
            "generated_at": datetime.now().isoformat(),
            "source": "Tableau Migration",
            "report_name": report_name,
            "objects_converted": {
                "worksheets": len(converted_objects.get('worksheets', [])),
                "dashboards": len(converted_objects.get('dashboards', [])),
                "datasources": len(converted_objects.get('datasources', [])),
                "calculations": len(converted_objects.get('calculations', [])),
                "parameters": len(converted_objects.get('parameters', [])),
                "filters": len(converted_objects.get('filters', [])),
                "stories": len(converted_objects.get('stories', [])),
                "sets": len(converted_objects.get('sets', [])),
                "groups": len(converted_objects.get('groups', [])),
                "bins": len(converted_objects.get('bins', [])),
                "hierarchies": len(converted_objects.get('hierarchies', [])),
                "user_filters": len(converted_objects.get('user_filters', [])),
                "actions": len(converted_objects.get('actions', [])),
                "custom_sql": len(converted_objects.get('custom_sql', []))
            },
            "generated_output": {
                "pages": pages_count,
                "visuals": visuals_count,
                "theme_applied": theme_applied,
                "theme_detail": theme_detail
            },
            "tmdl_stats": tmdl_stats,
            "visual_type_mappings": visual_types_used,
            "visual_details": visual_details,
            "approximations": approximations,
        }
        metadata_file = os.path.join(project_dir, 'migration_metadata.json')
        _write_json(metadata_file, metadata)

    # ═══════════════════════════════════════════════════════════════════
    # Paginated Report Generation
    # ═══════════════════════════════════════════════════════════════════

    def _create_paginated_report(self, project_dir, report_name, converted_objects):
        """Generate a paginated report layout (RDL-style) for print-oriented output.

        Creates a ``PaginatedReport/`` directory inside the project with:
        - ``report.json``: Paginated report definition with fixed page dimensions
        - ``pages/``: One ``pageN.json`` per worksheet with tabular layout
        - ``header.json`` / ``footer.json``: Placeholder header/footer definitions

        Paginated reports use fixed positioning (inches/cm) rather than
        responsive layout.  This is a starting point that users can refine
        in Power BI Report Builder.
        """
        pag_dir = os.path.join(project_dir, 'PaginatedReport')
        pages_dir = os.path.join(pag_dir, 'pages')
        os.makedirs(pages_dir, exist_ok=True)

        # --- Report-level definition ---
        report_def = {
            "$schema": "paginated-report/1.0.0",
            "name": f"{report_name}_Paginated",
            "description": f"Paginated report generated from Tableau workbook '{report_name}'",
            "pageWidth": "8.5in",
            "pageHeight": "11in",
            "marginTop": "0.5in",
            "marginBottom": "0.5in",
            "marginLeft": "0.75in",
            "marginRight": "0.75in",
            "orientation": "Portrait",
            "pageCount": 0,
            "dataSource": report_name,
        }

        # --- Header / Footer ---
        header_def = {
            "height": "0.75in",
            "items": [
                {
                    "type": "textbox",
                    "value": report_name,
                    "style": {"fontSize": "14pt", "fontWeight": "bold"},
                    "position": {"left": "0in", "top": "0.1in", "width": "5in", "height": "0.4in"},
                },
                {
                    "type": "textbox",
                    "value": "=Globals!ExecutionTime",
                    "style": {"fontSize": "8pt", "textAlign": "right"},
                    "position": {"left": "5in", "top": "0.1in", "width": "2in", "height": "0.3in"},
                },
            ],
        }
        footer_def = {
            "height": "0.5in",
            "items": [
                {
                    "type": "textbox",
                    "value": "=Globals!PageNumber & \" of \" & Globals!TotalPages",
                    "style": {"fontSize": "8pt", "textAlign": "center"},
                    "position": {"left": "2.5in", "top": "0.05in", "width": "2in", "height": "0.3in"},
                },
            ],
        }

        _write_json(os.path.join(pag_dir, 'header.json'), header_def)
        _write_json(os.path.join(pag_dir, 'footer.json'), footer_def)

        # --- One page per worksheet showing a table of the worksheet's fields ---
        worksheets = converted_objects.get('worksheets', [])
        page_num = 0
        for ws in worksheets:
            ws_name = ws.get('name', f'Sheet{page_num + 1}')
            fields = ws.get('fields', [])
            if not fields:
                continue
            page_num += 1

            # Build column definitions from fields
            col_width = min(2.0, 7.0 / max(len(fields), 1))
            columns = []
            for idx, field in enumerate(fields):
                fname = field if isinstance(field, str) else field.get('name', f'Column{idx}')
                columns.append({
                    "name": fname,
                    "width": f"{col_width:.2f}in",
                    "header": fname,
                    "style": {"fontSize": "9pt"},
                })

            page_def = {
                "pageNumber": page_num,
                "name": ws_name,
                "body": {
                    "height": "9in",
                    "items": [
                        {
                            "type": "tablix",
                            "name": f"Table_{ws_name}",
                            "position": {"left": "0in", "top": "0in",
                                         "width": f"{min(col_width * len(fields), 7.0):.2f}in",
                                         "height": "2in"},
                            "columns": columns,
                            "dataSetName": ws_name,
                            "headerRow": True,
                            "repeatHeaderOnNewPage": True,
                        }
                    ],
                },
            }
            _write_json(os.path.join(pages_dir, f'page{page_num}.json'), page_def)

        report_def['pageCount'] = page_num
        _write_json(os.path.join(pag_dir, 'report.json'), report_def)

        return pag_dir
