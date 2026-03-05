"""
Power BI visual generation module for .pbir files
Generates visualContainers from converted Tableau worksheets

Features:
- 60+ visual type mappings (all Tableau chart types)
- 30+ PBIR-native visual config templates
- Data role definitions per visual type
- Deep per-type query state building
- Grid layout positioning from Tableau dashboard coordinates
- Slicer sync groups
- Cross-filtering disable per visual
- Action button navigation (page + URL)
- TopN and categorical visual-level filters
- Sort state migration
- Reference lines (constant lines)
- Conditional formatting rules
"""

import uuid
import json
import hashlib
import logging

from powerbi_import.pbip_generator import _L

logger = logging.getLogger(__name__)


def _new_guid():
    return str(uuid.uuid4())


def _short_id(seed=""):
    return hashlib.sha1((seed or _new_guid()).encode()).hexdigest()[:20]


# ═══════════════════════════════════════════════════════════════════
# 60+ Visual Type Mappings
# ═══════════════════════════════════════════════════════════════════

VISUAL_TYPE_MAP = {
    # ── Bar charts ────────────────────────────────────────────
    "barchart": "clusteredBarChart",
    "bar": "clusteredBarChart",
    "stackedbarchart": "stackedBarChart",
    "stacked-bar": "stackedBarChart",
    "100stackedbarchart": "hundredPercentStackedBarChart",
    "100-stacked-bar": "hundredPercentStackedBarChart",

    # ── Column charts ─────────────────────────────────────────
    "columnchart": "clusteredColumnChart",
    "column": "clusteredColumnChart",
    "stackedcolumnchart": "stackedColumnChart",
    "stacked-column": "stackedColumnChart",
    "100stackedcolumnchart": "hundredPercentStackedColumnChart",
    "100-stacked-column": "hundredPercentStackedColumnChart",
    "histogram": "clusteredColumnChart",

    # ── Line / Area ───────────────────────────────────────────
    "linechart": "lineChart",
    "line": "lineChart",
    "areachart": "areaChart",
    "area": "areaChart",
    "stackedareachart": "stackedAreaChart",
    "stacked-area": "stackedAreaChart",
    "100stackedareachart": "hundredPercentStackedAreaChart",
    "sparkline": "lineChart",

    # ── Combo ─────────────────────────────────────────────────
    "combo": "lineStackedColumnComboChart",
    "combochart": "lineStackedColumnComboChart",
    "linecolumnchart": "lineStackedColumnComboChart",
    "lineclusteredcolumncombochart": "lineClusteredColumnComboChart",

    # ── Pie / Donut / Funnel ──────────────────────────────────
    "piechart": "pieChart",
    "pie": "pieChart",
    "donutchart": "donutChart",
    "donut": "donutChart",
    "funnel": "funnel",
    "funnelchart": "funnel",
    "semicircle": "donutChart",
    "ring": "donutChart",

    # ── Scatter / Bubble ──────────────────────────────────────
    "scatter": "scatterChart",
    "scatterplot": "scatterChart",
    "scatterchart": "scatterChart",
    "bubble": "scatterChart",
    "bubblechart": "scatterChart",
    "circle": "scatterChart",
    "shape": "scatterChart",
    "dot": "scatterChart",
    "dotplot": "scatterChart",
    "packedbubble": "scatterChart",
    "stripplot": "scatterChart",

    # ── Map visualizations ────────────────────────────────────
    "map": "map",
    "geomap": "map",
    "density": "map",
    "filledmap": "filledMap",
    "polygon": "filledMap",
    "multipolygon": "filledMap",
    "shapemap": "shapeMap",

    # ── Table / Matrix ────────────────────────────────────────
    "table": "tableEx",
    "text": "tableEx",
    "automatic": "tableEx",
    "straight-table": "tableEx",
    "straighttable": "tableEx",
    "tableex": "tableEx",
    "pivot-table": "pivotTable",
    "pivottable": "pivotTable",
    "pivot": "pivotTable",
    "matrix": "matrix",
    "heatmap": "matrix",
    "highlighttable": "matrix",
    "calendar": "matrix",

    # ── KPI / Card / Gauge ────────────────────────────────────
    "kpi": "card",
    "card": "card",
    "multirowcard": "multiRowCard",
    "multi-kpi": "multiRowCard",
    "gauge": "gauge",
    "meter": "gauge",
    "bullet": "gauge",
    "radial": "gauge",
    "lollipop": "clusteredBarChart",

    # ── Treemap / Hierarchy ───────────────────────────────────
    "treemap": "treemap",
    "square": "treemap",
    "hex": "treemap",
    "sunburst": "sunburst",
    "decompositiontree": "decompositionTree",

    # ── Waterfall / Box / Ribbon ──────────────────────────────
    "waterfall": "waterfallChart",
    "waterfallchart": "waterfallChart",
    "boxplot": "boxAndWhisker",
    "box-and-whisker": "boxAndWhisker",
    "bulletchart": "bulletChart",

    # ── Text / Image / Container ──────────────────────────────
    "text-image": "textbox",
    "textbox": "textbox",
    "image": "image",
    "container": "actionButton",
    "tabcontainer": "actionButton",
    "button": "actionButton",
    "actionbutton": "actionButton",

    # ── Filter / Slicer ──────────────────────────────────────
    "filterpane": "slicer",
    "slicer": "slicer",
    "listbox": "slicer",
    "filter_control": "slicer",

    # ── Specialty ─────────────────────────────────────────────
    "wordcloud": "wordCloud",
    "word-cloud": "wordCloud",
    "ribbonchart": "ribbonChart",
    "ribbon": "ribbonChart",
    "mekko": "stackedBarChart",
    "sankey": "decompositionTree",
    "chord": "decompositionTree",
    "network": "decompositionTree",
    "ganttbar": "clusteredBarChart",
    "bumpchart": "lineChart",
    "slopechart": "lineChart",
    "timeline": "lineChart",
    "butterfly": "hundredPercentStackedBarChart",
    "waffle": "hundredPercentStackedBarChart",
    "pareto": "lineClusteredColumnComboChart",
    "dualaxis": "lineClusteredColumnComboChart",

    # ── PBI pass-through (already correct) ─────────────────
    "clusteredbarchart": "clusteredBarChart",
    "stackedbarchart": "stackedBarChart",
    "clusteredcolumnchart": "clusteredColumnChart",
    "stackedcolumnchart": "stackedColumnChart",
    "piechart": "pieChart",
    "areachart": "areaChart",
    "stackedareachart": "stackedAreaChart",
    "donutchart": "donutChart",
    "waterfallchart": "waterfallChart",
    "lineStackedColumnComboChart": "lineStackedColumnComboChart",
}


# ═══════════════════════════════════════════════════════════════════
# Data Role Definitions per Visual Type
# ═══════════════════════════════════════════════════════════════════

VISUAL_DATA_ROLES = {
    # (dimension_roles, measure_roles)
    "card":                              ([], ["Fields"]),
    "multiRowCard":                      ([], ["Values"]),
    "kpi":                               ([], ["Indicator", "TrendAxis"]),
    "clusteredBarChart":                 (["Category"], ["Y"]),
    "stackedBarChart":                   (["Category", "Series"], ["Y"]),
    "hundredPercentStackedBarChart":     (["Category", "Series"], ["Y"]),
    "clusteredColumnChart":              (["Category"], ["Y"]),
    "stackedColumnChart":                (["Category", "Series"], ["Y"]),
    "hundredPercentStackedColumnChart":  (["Category", "Series"], ["Y"]),
    "lineChart":                         (["Category"], ["Y"]),
    "areaChart":                         (["Category"], ["Y"]),
    "stackedAreaChart":                  (["Category", "Series"], ["Y"]),
    "hundredPercentStackedAreaChart":    (["Category", "Series"], ["Y"]),
    "pieChart":                          (["Category"], ["Y"]),
    "donutChart":                        (["Category"], ["Y"]),
    "waterfallChart":                    (["Category"], ["Y"]),
    "funnel":                            (["Category"], ["Y"]),
    "gauge":                             ([], ["Y", "MinValue", "MaxValue", "TargetValue"]),
    "treemap":                           (["Group"], ["Values"]),
    "sunburst":                          (["Group"], ["Values"]),
    "scatterChart":                      (["Category", "Details"], ["X", "Y", "Size"]),
    "tableEx":                           (["Values"], ["Values"]),
    "matrix":                            (["Rows", "Columns"], ["Values"]),
    "pivotTable":                        (["Rows", "Columns"], ["Values"]),
    "slicer":                            (["Values"], []),
    "lineStackedColumnComboChart":       (["Category"], ["ColumnY", "LineY"]),
    "lineClusteredColumnComboChart":     (["Category"], ["ColumnY", "LineY"]),
    "map":                               (["Category", "Location"], ["Size", "Color"]),
    "filledMap":                         (["Location"], ["Color"]),
    "shapeMap":                          (["Location"], ["Color"]),
    "ribbonChart":                       (["Category", "Series"], ["Y"]),
    "boxAndWhisker":                     (["Category", "Sampling"], ["Value"]),
    "bulletChart":                       (["Category"], ["Value", "TargetValue", "Minimum",
                                          "NeedsImprovement", "Satisfactory", "Good",
                                          "VeryGood", "Maximum"]),
    "decompositionTree":                 (["TreeItems"], ["Values"]),
    "wordCloud":                         (["Category"], ["Values"]),
    "textbox":                           ([], []),
    "image":                             ([], []),
    "actionButton":                      ([], []),
}


# ═══════════════════════════════════════════════════════════════════
# 30+ PBIR-Native Visual Config Templates
# ═══════════════════════════════════════════════════════════════════

def _get_config_template(visual_type):
    """Return per-type visual configuration template with PBIR-native objects."""

    templates = {
        "tableEx": {
            "autoSelectVisualType": True,
            "objects": {
                "values": [{"properties": {"bold": _L("false")}}],
            },
        },
        "pivotTable": {
            "autoSelectVisualType": True,
        },
        "matrix": {
            "autoSelectVisualType": True,
            "objects": {
                "rowHeaders": [{"properties": {"fontSize": _L("10D")}}],
            },
        },
        "clusteredBarChart": {
            "objects": {
                "categoryAxis": [{"properties": {"show": _L("true")}}],
                "valueAxis": [{"properties": {"show": _L("true")}}],
                "legend": [{"properties": {"show": _L("false")}}],
                "dataPoint": [{"properties": {"showAllDataPoints": _L("true")}}],
            },
        },
        "stackedBarChart": {
            "objects": {
                "categoryAxis": [{"properties": {"show": _L("true")}}],
                "valueAxis": [{"properties": {"show": _L("true")}}],
                "legend": [{"properties": {"show": _L("true")}}],
            },
        },
        "hundredPercentStackedBarChart": {
            "objects": {
                "categoryAxis": [{"properties": {"show": _L("true")}}],
                "valueAxis": [{"properties": {"show": _L("true")}}],
                "legend": [{"properties": {"show": _L("true")}}],
            },
        },
        "clusteredColumnChart": {
            "objects": {
                "categoryAxis": [{"properties": {"show": _L("true")}}],
                "valueAxis": [{"properties": {"show": _L("true")}}],
                "dataPoint": [{"properties": {"showAllDataPoints": _L("true")}}],
            },
        },
        "stackedColumnChart": {
            "objects": {
                "categoryAxis": [{"properties": {"show": _L("true")}}],
                "valueAxis": [{"properties": {"show": _L("true")}}],
                "legend": [{"properties": {"show": _L("true")}}],
            },
        },
        "hundredPercentStackedColumnChart": {
            "objects": {
                "categoryAxis": [{"properties": {"show": _L("true")}}],
                "valueAxis": [{"properties": {"show": _L("true")}}],
                "legend": [{"properties": {"show": _L("true")}}],
            },
        },
        "lineChart": {
            "objects": {
                "categoryAxis": [{"properties": {"show": _L("true")}}],
                "valueAxis": [{"properties": {"show": _L("true")}}],
                "dataPoint": [{"properties": {"showMarkers": _L("true")}}],
                "legend": [{"properties": {"show": _L("false")}}],
            },
        },
        "areaChart": {
            "objects": {
                "categoryAxis": [{"properties": {"show": _L("true")}}],
                "valueAxis": [{"properties": {"show": _L("true")}}],
            },
        },
        "stackedAreaChart": {
            "objects": {
                "categoryAxis": [{"properties": {"show": _L("true")}}],
                "valueAxis": [{"properties": {"show": _L("true")}}],
                "legend": [{"properties": {"show": _L("true")}}],
            },
        },
        "pieChart": {
            "objects": {
                "legend": [{"properties": {"show": _L("true")}}],
                "labels": [{"properties": {"show": _L("true"),
                             "labelStyle": _L("'Category, percent of total'")}}],
            },
        },
        "donutChart": {
            "objects": {
                "legend": [{"properties": {"show": _L("true")}}],
                "labels": [{"properties": {"show": _L("true")}}],
            },
        },
        "scatterChart": {
            "objects": {
                "categoryAxis": [{"properties": {"show": _L("true"),
                                   "showAxisTitle": _L("true")}}],
                "valueAxis": [{"properties": {"show": _L("true"),
                                "showAxisTitle": _L("true")}}],
            },
        },
        "gauge": {
            "objects": {
                "axis": [{"properties": {"min": _L("0L"), "max": _L("100L")}}],
                "target": [{"properties": {"show": _L("true")}}],
            },
        },
        "card": {
            "objects": {
                "labels": [{"properties": {"show": _L("true"),
                             "fontSize": _L("27D")}}],
                "categoryLabels": [{"properties": {"show": _L("true")}}],
            },
        },
        "multiRowCard": {
            "objects": {
                "dataLabels": [{"properties": {"fontSize": _L("15D")}}],
                "cardTitle": [{"properties": {"fontSize": _L("12D")}}],
            },
        },
        "treemap": {
            "objects": {
                "legend": [{"properties": {"show": _L("true")}}],
                "labels": [{"properties": {"show": _L("true")}}],
            },
        },
        "waterfallChart": {
            "objects": {
                "sentimentColors": [{"properties": {
                    "increaseFill": {"solid": {"color": "#4CAF50"}},
                    "decreaseFill": {"solid": {"color": "#F44336"}},
                    "totalFill": {"solid": {"color": "#2196F3"}},
                }}],
                "categoryAxis": [{"properties": {"show": _L("true")}}],
            },
        },
        "funnel": {
            "objects": {
                "labels": [{"properties": {"show": _L("true")}}],
            },
        },
        "boxAndWhisker": {
            "objects": {
                "general": [{"properties": {"orientation": _L("'Vertical'")}}],
            },
        },
        "map": {
            "objects": {
                "legend": [{"properties": {"show": _L("true")}}],
            },
        },
        "filledMap": {
            "objects": {
                "legend": [{"properties": {"show": _L("true")}}],
            },
        },
        "ribbonChart": {
            "objects": {
                "categoryAxis": [{"properties": {"show": _L("true")}}],
                "valueAxis": [{"properties": {"show": _L("true")}}],
                "legend": [{"properties": {"show": _L("true")}}],
            },
        },
        "lineStackedColumnComboChart": {
            "objects": {
                "categoryAxis": [{"properties": {"show": _L("true")}}],
                "valueAxis": [{"properties": {"show": _L("true")}}],
                "lineStyles": [{"properties": {"showMarker": _L("true")}}],
                "legend": [{"properties": {"show": _L("true")}}],
            },
        },
        "lineClusteredColumnComboChart": {
            "objects": {
                "categoryAxis": [{"properties": {"show": _L("true")}}],
                "valueAxis": [{"properties": {"show": _L("true")}}],
                "legend": [{"properties": {"show": _L("true")}}],
            },
        },
        "wordCloud": {
            "objects": {
                "general": [{"properties": {"maxNumberOfWords": _L("100L")}}],
            },
        },
        "bulletChart": {
            "objects": {
                "axis": [{"properties": {"show": _L("true")}}],
            },
        },
        "slicer": {
            "objects": {
                "data": [{"properties": {"mode": _L("'Basic'")}}],
            },
        },
    }

    return templates.get(visual_type, {})


# Aggregation function mapping
_AGG_FUNC_MAP = {
    "sum": 1, "min": 2, "max": 3, "count": 4,
    "countnonnull": 5, "avg": 6, "average": 6,
    "distinctcount": 7,
}


# ═══════════════════════════════════════════════════════════════════
# Visual Container Generation
# ═══════════════════════════════════════════════════════════════════

def resolve_visual_type(source_type):
    """Resolve a source visualization type to a Power BI visual type."""
    if not source_type:
        return "tableEx"
    return VISUAL_TYPE_MAP.get(source_type.lower(), "tableEx")


def generate_visual_containers(converted_worksheets, report_name="Report",
                               col_table_map=None, measure_lookup=None,
                               page_width=1280, page_height=720):
    """
    Generate visualContainers for definition.pbir

    Args:
        converted_worksheets: List of worksheets converted by worksheet_converter
        report_name: Report name (used for ID generation)
        col_table_map: {column_name: table_name} lookup
        measure_lookup: {measure_name: (table, dax_expr)} lookup
        page_width: Page width in pixels
        page_height: Page height in pixels

    Returns:
        List of visualContainers in Power BI Report Definition format
    """
    visual_containers = []
    ctm = col_table_map or {}
    ml = measure_lookup or {}

    # Initial position (x, y) and dimensions
    x_pos = 10
    y_pos = 10
    width = 300
    height = 200
    spacing = 20

    for idx, worksheet in enumerate(converted_worksheets[:20]):
        visual_id = _short_id(f"viz_{idx}_{report_name}")

        # Create a visual container for each worksheet
        visual_container = create_visual_container(
            worksheet=worksheet,
            visual_id=visual_id,
            x=x_pos,
            y=y_pos,
            width=width,
            height=height,
            z_index=idx,
            col_table_map=ctm,
            measure_lookup=ml,
        )

        visual_containers.append(visual_container)

        # Calculate position for the next visual (grid layout)
        x_pos += width + spacing
        if x_pos > 1000:  # Wrap after 3 visuals
            x_pos = 10
            y_pos += height + spacing

    return visual_containers


def create_visual_container(worksheet, visual_id=None, x=10, y=10,
                            width=300, height=200, z_index=0,
                            col_table_map=None, measure_lookup=None):
    """
    Create a Power BI visualContainer from a converted worksheet.

    Supports:
    - All 60+ visual types via VISUAL_TYPE_MAP
    - PBIR-native config templates
    - Slicer sync groups
    - Cross-filtering disable
    - Action button navigation (page + URL)
    - TopN and categorical visual filters
    - Sort state migration
    - Reference lines (constant lines)
    - Conditional formatting
    """
    ctm = col_table_map or {}
    ml = measure_lookup or {}

    visual_type = worksheet.get('visualType', 'table')
    visual_name = worksheet.get('name', f'Visual{z_index}')

    # Resolve visual type through the map
    pbi_type = resolve_visual_type(visual_type)

    # Generate a unique GUID for the visual
    vid = visual_id or _new_guid()

    # ── Build visual object ───────────────────────────────────
    visual_obj = {
        "visualType": pbi_type,
        "drillFilterOtherVisuals": True,
    }

    # Apply PBIR-native config template
    config = _get_config_template(pbi_type)
    if "autoSelectVisualType" in config:
        visual_obj["autoSelectVisualType"] = config["autoSelectVisualType"]
    if "objects" in config:
        visual_obj["objects"] = config["objects"]

    # ── Build query state ─────────────────────────────────────
    data_fields = worksheet.get('dataFields', [])
    dimensions = worksheet.get('dimensions', [])
    measures = worksheet.get('measures', [])

    if dimensions or measures:
        query_state = build_query_state(
            pbi_type, dimensions, measures, ctm, ml,
        )
        if query_state:
            visual_obj["query"] = {"queryState": query_state}
    elif data_fields:
        # Legacy field-based projections
        projections = create_projections(worksheet)
        proto_query = create_prototype_query(worksheet)
        visual_obj["projections"] = projections
        visual_obj["prototypeQuery"] = proto_query

    # ── Title ─────────────────────────────────────────────────
    visual_obj.setdefault("vcObjects", {})
    visual_obj["vcObjects"]["title"] = [{
        "properties": {
            "show": _L("true"),
            "text": _L(json.dumps(visual_name)),
        }
    }]

    # ── Subtitle ──────────────────────────────────────────────
    subtitle = worksheet.get('subtitle', '')
    if subtitle:
        visual_obj["vcObjects"]["subTitle"] = [{
            "properties": {
                "show": _L("true"),
                "text": _L(json.dumps(subtitle)),
            }
        }]

    # ── Conditional formatting (color by mode) ────────────────
    color_by = worksheet.get('colorBy', worksheet.get('color', {}))
    if isinstance(color_by, dict) and color_by.get('mode'):
        mode = color_by['mode']
        visual_obj.setdefault("objects", {})
        if mode in ('byMeasure', 'measure'):
            visual_obj["objects"]["dataPoint"] = [{
                "properties": {"showAllDataPoints": _L("true")}
            }]
        elif mode in ('byDimension', 'dimension'):
            visual_obj["objects"].setdefault("dataPoint", [{}])

    # ── Conditional formatting rules (explicit) ───────────────
    cond_format = worksheet.get('conditionalFormatting', [])
    if cond_format:
        visual_obj.setdefault("objects", {})
        visual_obj["objects"]["dataPoint"] = [{
            "properties": {"showAllDataPoints": _L("true")}
        }]

    # ── Visual-level filters ─────────────────────────────────
    viz_filters = worksheet.get('filters', [])
    if viz_filters:
        filter_list = _build_visual_filters(viz_filters, ctm)
        if filter_list:
            visual_obj["filters"] = filter_list

    # ── Sort order ────────────────────────────────────────────
    sort_by = worksheet.get('sortBy', worksheet.get('sorting', []))
    if sort_by:
        sort_defs = sort_by if isinstance(sort_by, list) else [sort_by]
        sort_state = []
        for sd in sort_defs:
            if isinstance(sd, dict):
                sort_field = sd.get('field', sd.get('column', ''))
                direction = sd.get('direction', 'ascending')
                st = ctm.get(sort_field, 'Table')
                sort_state.append({
                    "field": {
                        "Column": {
                            "Expression": {"SourceRef": {"Entity": st}},
                            "Property": sort_field,
                        }
                    },
                    "direction": 1 if direction.lower() == 'ascending' else 2,
                })
        if sort_state:
            visual_obj.setdefault("query", {})
            visual_obj["query"]["sortDefinition"] = {"sort": sort_state}

    # ── Reference lines ───────────────────────────────────────
    ref_lines = worksheet.get('referenceLines', worksheet.get('reference_lines', []))
    if ref_lines:
        constant_lines = []
        for rl in ref_lines:
            constant_lines.append({
                "show": _L("true"),
                "value": _L(f"{rl.get('value', 0)}D"),
                "displayName": _L(json.dumps(rl.get('label', ''))),
                "color": {"solid": {"color": rl.get('color', rl.get('line_color', '#FF0000'))}},
                "style": _L("'dashed'"),
            })
        if constant_lines:
            visual_obj.setdefault("objects", {})
            visual_obj["objects"]["constantLine"] = [
                {"properties": cl} for cl in constant_lines
            ]

    # ── Axis config (min/max, log, reversed) ──────────────────
    axes_data = worksheet.get('axes', {})
    if axes_data:
        visual_obj.setdefault("objects", {})
        y_axis = axes_data.get('y', {})
        if y_axis:
            va_props = visual_obj["objects"].get("valueAxis", [{}])[0].get("properties", {})
            va_props["show"] = _L("true")
            if not y_axis.get('auto_range', True):
                if y_axis.get('range_min') is not None:
                    va_props["start"] = _L(f"{y_axis['range_min']}D")
                if y_axis.get('range_max') is not None:
                    va_props["end"] = _L(f"{y_axis['range_max']}D")
            if y_axis.get('scale') == 'log':
                va_props["axisScale"] = _L("'Log'")
            if y_axis.get('reversed'):
                va_props["reverseOrder"] = _L("true")
            if y_axis.get('title'):
                va_props["titleText"] = _L(json.dumps(y_axis['title']))
                va_props["showAxisTitle"] = _L("true")
            visual_obj["objects"]["valueAxis"] = [{"properties": va_props}]
        x_axis = axes_data.get('x', {})
        if x_axis:
            ca_props = visual_obj["objects"].get("categoryAxis", [{}])[0].get("properties", {})
            ca_props["show"] = _L("true")
            if x_axis.get('reversed'):
                ca_props["reverseOrder"] = _L("true")
            if x_axis.get('title'):
                ca_props["titleText"] = _L(json.dumps(x_axis['title']))
                ca_props["showAxisTitle"] = _L("true")
            visual_obj["objects"]["categoryAxis"] = [{"properties": ca_props}]

    # ── Assemble container ────────────────────────────────────
    container = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.5.0/schema.json",
        "name": vid,
        "position": {
            "x": x,
            "y": y,
            "z": z_index * 1000,
            "height": height,
            "width": width,
            "tabOrder": z_index * 1000,
        },
        "visual": visual_obj,
    }

    # ── Action button navigation ──────────────────────────────
    if pbi_type == "actionButton":
        nav_target = worksheet.get('navigation', worksheet.get('action', {}))
        if isinstance(nav_target, dict):
            target_page = nav_target.get('sheet', nav_target.get('pageName', ''))
            nav_url = nav_target.get('url', '')
            if target_page:
                visual_obj.setdefault("objects", {})
                visual_obj["objects"]["action"] = [{
                    "properties": {
                        "show": _L("true"),
                        "type": _L("'PageNavigation'"),
                        "destination": _L(json.dumps(target_page)),
                    }
                }]
            elif nav_url:
                visual_obj.setdefault("objects", {})
                visual_obj["objects"]["action"] = [{
                    "properties": {
                        "show": _L("true"),
                        "type": _L("'WebUrl'"),
                        "destination": _L(json.dumps(nav_url)),
                    }
                }]

    # ── Slicer sync group ─────────────────────────────────────
    if pbi_type == "slicer":
        sync_group = worksheet.get('syncGroup', worksheet.get('filterScope', ''))
        if sync_group:
            container["syncGroup"] = {
                "groupName": sync_group,
                "syncField": True,
                "syncFilters": True,
            }

    # ── Cross-filtering behavior ──────────────────────────────
    interactions = worksheet.get('interactions', worksheet.get('crossFilter', {}))
    if isinstance(interactions, dict) and interactions.get('disabled'):
        container["filterConfig"] = {
            "filters": [],
            "disabled": True,
        }

    # Add filters if present (legacy format)
    filters = worksheet.get('filters', [])
    if filters and 'filters' not in visual_obj:
        container_filters = create_filters_config(filters)
        if container_filters:
            container["filters"] = json.dumps(container_filters)

    return container


def _build_visual_filters(viz_filters, col_table_map):
    """Build visual-level filter entries including TopN support.

    Args:
        viz_filters: List of filter dicts from worksheet
        col_table_map: {column: table} lookup

    Returns:
        List of filter objects for PBIR visual
    """
    filter_list = []
    for vf in viz_filters:
        field_name = vf.get('field', '')
        filter_type = vf.get('type', 'basic')
        values = vf.get('values', [])
        table_name = col_table_map.get(field_name, 'Table')

        if filter_type == 'topN':
            # TopN filter
            filter_entry = {
                "type": "TopN",
                "expression": {
                    "Column": {
                        "Expression": {"SourceRef": {"Entity": table_name}},
                        "Property": field_name,
                    }
                },
                "itemCount": vf.get('count', 10),
                "orderBy": [{"Direction": 2}],  # Descending
            }
            filter_list.append(filter_entry)
        elif values:
            # Categorical filter
            filter_entry = {
                "type": "Categorical",
                "expression": {
                    "Column": {
                        "Expression": {"SourceRef": {"Entity": table_name}},
                        "Property": field_name,
                    }
                },
                "values": [[{"Literal": {"Value": json.dumps(v)}} for v in values]],
            }
            filter_list.append(filter_entry)

    return filter_list


def create_projections(worksheet):
    """
    Create projections (field bindings to visual roles)
    """
    projections = {}

    data_fields = worksheet.get('dataFields', [])

    for field in data_fields:
        role = field.get('role', 'values')
        field_name = field.get('name', 'Field')

        if role not in projections:
            projections[role] = []

        projections[role].append({
            "queryRef": field_name,
            "active": True
        })

    if 'values' not in projections:
        projections['values'] = [{
            "queryRef": "Count",
            "active": True
        }]

    return projections


def create_prototype_query(worksheet):
    """
    Create the prototype query (field definitions used)
    """
    data_fields = worksheet.get('dataFields', [])
    field_names = list(set([f.get('name', 'Field') for f in data_fields]))

    query = {
        "Version": 2,
        "From": [{"Name": "t", "Entity": "Table1", "Type": 0}],
        "Select": []
    }

    for field_name in field_names:
        query["Select"].append({
            "Column": {
                "Expression": {"SourceRef": {"Source": "t"}},
                "Property": field_name
            },
            "Name": field_name
        })

    return query


def build_query_state(pbi_type, dimensions, measures, col_table_map,
                      measure_lookup):
    """Build PBIR queryState with role-based projections.

    Args:
        pbi_type: Power BI visual type
        dimensions: List of dimension dicts
        measures: List of measure dicts
        col_table_map: {column: table} lookup
        measure_lookup: {measure_name: (table, dax)} lookup

    Returns:
        queryState dict or None
    """
    import re

    roles = VISUAL_DATA_ROLES.get(pbi_type)
    if not roles:
        return None

    dim_roles, meas_roles = roles

    # ── Resolve dimension projections ─────────────────────────
    dim_projections = []
    for dim in (dimensions or []):
        field_name = dim.get('field', '') or dim.get('name', '')
        table_name = col_table_map.get(field_name, '')
        if not table_name and col_table_map:
            table_name = next(iter(col_table_map.values()), 'Table')
        if table_name and field_name:
            proj = {
                "field": {
                    "Column": {
                        "Expression": {"SourceRef": {"Entity": table_name}},
                        "Property": field_name,
                    },
                },
                "queryRef": f"{table_name}.{field_name}",
                "nativeQueryRef": field_name,
                "active": True,
            }
            display_name = dim.get('label') or dim.get('name')
            if display_name:
                proj["displayName"] = display_name
            dim_projections.append(proj)

    # ── Resolve measure projections ───────────────────────────
    meas_projections = []
    for meas in (measures or []):
        measure_label = meas.get('label') or meas.get('name', 'Measure')

        # Try named measure from BIM model
        bim_info = measure_lookup.get(measure_label)
        if bim_info:
            tbl_name, _dax_expr = bim_info
            proj = {
                "field": {
                    "Measure": {
                        "Expression": {"SourceRef": {"Entity": tbl_name}},
                        "Property": measure_label,
                    },
                },
                "queryRef": f"{tbl_name}.{measure_label}",
                "nativeQueryRef": measure_label,
            }
            if measure_label:
                proj["displayName"] = measure_label
            meas_projections.append(proj)
            continue

        # Fallback: inline aggregation from expression
        expr = meas.get('expression', '')
        m = re.match(r'(\w+)\((\w+)\)', expr.strip()) if expr else None
        if m:
            func_name, col_name = m.group(1).lower(), m.group(2)
        else:
            func_name, col_name = '', expr.strip() if expr else ''

        func_id = _AGG_FUNC_MAP.get(func_name, 1)
        table_name = col_table_map.get(col_name, '')
        if not table_name and col_table_map:
            table_name = next(iter(col_table_map.values()), 'Table')
        if table_name and col_name:
            agg_name = func_name.capitalize() if func_name else 'Sum'
            proj = {
                "field": {
                    "Aggregation": {
                        "Expression": {
                            "Column": {
                                "Expression": {"SourceRef": {"Entity": table_name}},
                                "Property": col_name,
                            },
                        },
                        "Function": func_id,
                    },
                },
                "queryRef": f"{agg_name}({table_name}.{col_name})",
                "nativeQueryRef": col_name,
            }
            if measure_label:
                proj["displayName"] = measure_label
            meas_projections.append(proj)

    if not dim_projections and not meas_projections:
        return None

    query_state = {}

    # tableEx uses a single "Values" role
    if pbi_type == "tableEx":
        all_projs = dim_projections + meas_projections
        if all_projs:
            query_state["Values"] = {"projections": all_projs}
        return query_state if query_state else None

    # Assign dimensions to dimension roles
    for role_name in dim_roles:
        if dim_projections:
            query_state[role_name] = {"projections": list(dim_projections)}

    # Assign measures to measure roles
    for i, role_name in enumerate(meas_roles):
        if i < len(meas_projections):
            query_state[role_name] = {"projections": [meas_projections[i]]}
        elif meas_projections:
            query_state[role_name] = {"projections": [meas_projections[0]]}

    return query_state if query_state else None


def create_filters_config(filters):
    """
    Create the filter configuration for a visual
    """
    filters_config = []

    for filt in filters:
        filter_config = {
            "expression": {
                "Column": {
                    "Expression": {
                        "SourceRef": {"Entity": "Table1"}
                    },
                    "Property": filt.get('field', 'Field')
                }
            },
            "filter": {
                "Version": 2,
                "From": [{"Name": "t", "Entity": "Table1", "Type": 0}],
                "Where": [{
                    "Condition": {
                        "In": {
                            "Expressions": [{
                                "Column": {
                                    "Expression": {"SourceRef": {"Source": "t"}},
                                    "Property": filt.get('field', 'Field')
                                }
                            }],
                            "Values": [
                                [{"Literal": {"Value": f"'{v}'"}}]
                                for v in filt.get('values', [])
                            ]
                        }
                    }
                }]
            }
        }
        filters_config.append(filter_config)

    return filters_config


def create_page_layout(worksheets):
    """
    Create the page layout to organize visuals
    """
    return {
        "displayOption": 0,  # FitToPage
        "width": 1280,
        "height": 720
    }
