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

# ── Auto-generated measures (e.g. RANKX for bump charts) ─────────────────────
# Populated during visual generation; consumed by tmdl_generator to emit
# the corresponding DAX measures in the semantic model.
_AUTO_GENERATED_MEASURES = []


def get_auto_generated_measures():
    """Return list of measures auto-generated during visual creation.

    Each entry is a dict with keys: name, table, expression, description.
    Call ``clear_auto_generated_measures()`` before a new generation run.
    """
    return list(_AUTO_GENERATED_MEASURES)


def clear_auto_generated_measures():
    """Reset the auto-generated measures list for a fresh run."""
    _AUTO_GENERATED_MEASURES.clear()


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
    "polygon": "map",
    "multipolygon": "map",
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
    "sankey": "sankeyDiagram",
    "chord": "chordChart",
    "network": "networkNavigator",
    "ganttbar": "ganttChart",
    "bumpchart": "lineChart",
    "slopechart": "lineChart",
    "timeline": "lineChart",
    "butterfly": "hundredPercentStackedBarChart",
    "waffle": "hundredPercentStackedBarChart",
    "pareto": "lineClusteredColumnComboChart",
    "dualaxis": "lineClusteredColumnComboChart",
    "violin": "boxAndWhisker",
    "violinplot": "boxAndWhisker",
    "parallelcoordinates": "lineChart",
    "parallel-coordinates": "lineChart",
    "calendarheatmap": "matrix",

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
# Custom Visual GUID Registry — AppSource custom visual package IDs
# ═══════════════════════════════════════════════════════════════════
# Maps Tableau visual types that have no built-in PBI equivalent to
# AppSource custom visual GUIDs.  When a GUID is available, the
# generator produces a ``customVisual`` visualType referencing the
# GUID instead of the generic PBI fallback above.

CUSTOM_VISUAL_GUIDS = {
    "sankey": {
        "guid": "ChicagoITSankey1.1.0",
        "name": "Sankey Diagram",
        "class": "sankeyDiagram",
        "roles": {"Source": "dimension", "Destination": "dimension", "Weight": "measure"},
    },
    "chord": {
        "guid": "ChicagoITChord1.0.0",
        "name": "Chord Diagram",
        "class": "chordChart",
        "roles": {"From": "dimension", "To": "dimension", "Values": "measure"},
    },
    "network": {
        "guid": "NetworkNavigator1.0.0",
        "name": "Network Navigator",
        "class": "networkNavigator",
        "roles": {"Source": "dimension", "Target": "dimension", "Weight": "measure"},
    },
    "wordcloud": {
        "guid": "WordCloud1633006498960",
        "name": "Word Cloud",
        "class": "wordCloud",
        "roles": {"Category": "dimension", "Values": "measure"},
    },
    "ganttbar": {
        "guid": "GanttByMAQSoftware1.0.0",
        "name": "Gantt Chart",
        "class": "ganttChart",
        "roles": {"Task": "dimension", "Start": "measure", "Duration": "measure"},
    },
    "histogram": {
        "guid": "Histogram1.0.0",
        "name": "Histogram Chart",
        "class": "histogram",
        "roles": {"Values": "measure"},
    },
    "boxplot": {
        "guid": "BoxAndWhisker1.0.0",
        "name": "Box and Whisker",
        "class": "boxAndWhisker",
        "roles": {"Category": "dimension", "Value": "measure"},
    },
    "radial": {
        "guid": "RadialGauge1.0.0",
        "name": "Radial Gauge",
        "class": "radialGauge",
        "roles": {"Value": "measure", "Target": "measure"},
    },
    "bullet": {
        "guid": "BulletChart1.0.0",
        "name": "Bullet Chart",
        "class": "bulletChart",
        "roles": {"Value": "measure", "Target": "measure", "Category": "dimension"},
    },
    "violin": {
        "guid": "ViolinPlot1.0.0",
        "name": "Violin Plot",
        "class": "violinPlot",
        "roles": {"Category": "dimension", "Value": "measure"},
    },
    "parallelcoordinates": {
        "guid": "ParallelCoordinates1.0.0",
        "name": "Parallel Coordinates",
        "class": "parallelCoordinates",
        "roles": {"Category": "dimension", "Value": "measure"},
    },
}


def resolve_custom_visual_type(tableau_mark, use_custom_visuals=True):
    """Resolve a Tableau mark type to a PBI visual type with custom visual support.

    If *use_custom_visuals* is True and a custom visual GUID is
    available, returns a tuple ``(visual_type, guid_info)`` where
    ``guid_info`` is a dict from ``CUSTOM_VISUAL_GUIDS``; otherwise
    ``guid_info`` is ``None``.
    """
    key = (tableau_mark or '').lower().replace(' ', '').replace('_', '')
    if use_custom_visuals and key in CUSTOM_VISUAL_GUIDS:
        guid_info = CUSTOM_VISUAL_GUIDS[key]
        return guid_info.get('class', key), guid_info
    pbi_type = VISUAL_TYPE_MAP.get(key, 'tableEx')
    return pbi_type, None


# ═══════════════════════════════════════════════════════════════════
# Sparkline Configuration Builder
# ═══════════════════════════════════════════════════════════════════

def _build_sparkline_config(measure_name, table_name, date_column='Date',
                            sparkline_type='line', color='#4472C4'):
    """Build a sparkline conditional formatting config for table/matrix cells.

    Power BI supports inline sparklines in table/matrix visuals via
    the ``sparkline`` property in ``conditionalFormatting``.

    Args:
        measure_name: Name of the measure column to sparkline.
        table_name: Source table name.
        date_column: X-axis date/category column.
        sparkline_type: 'line' or 'column'.
        color: Sparkline line/fill color.

    Returns:
        dict: PBIR-compatible sparkline configuration.
    """
    return {
        "id": f"sparkline_{measure_name}",
        "type": "sparkline",
        "sparklineType": sparkline_type,
        "field": {
            "Column": {
                "Expression": {
                    "SourceRef": {"Entity": table_name}
                },
                "Property": measure_name,
            }
        },
        "dateAxis": {
            "Column": {
                "Expression": {
                    "SourceRef": {"Entity": table_name}
                },
                "Property": date_column,
            }
        },
        "lineColor": {"solid": {"color": color}},
        "markerColor": {"solid": {"color": color}},
        "showHighPoint": True,
        "showLowPoint": True,
        "showLastPoint": False,
        "showFirstPoint": False,
        "lineWidth": 2,
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
        "hundredPercentStackedAreaChart": {
            "objects": {
                "categoryAxis": [{"properties": {"show": _L("true")}}],
                "valueAxis": [{"properties": {"show": _L("true")}}],
                "legend": [{"properties": {"show": _L("true")}}],
            },
        },
        "sunburst": {
            "objects": {
                "group": [{"properties": {"fontSize": _L("10D")}}],
                "legend": [{"properties": {"show": _L("true")}}],
            },
        },
        "decompositionTree": {
            "objects": {
                "tree": [{"properties": {"fontSize": _L("12D")}}],
            },
        },
        "shapeMap": {
            "objects": {
                "legend": [{"properties": {"show": _L("true")}}],
                "dataPoint": [{"properties": {"showAllDataPoints": _L("true")}}],
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

# ═══════════════════════════════════════════════════════════════════
# Approximation Map — Tableau visuals mapped to approximate PBI types
# ═══════════════════════════════════════════════════════════════════
# When a Tableau visual has no exact PBI equivalent, the closest native type
# is used.  This map records the approximation so that a migration note
# can be attached to the generated visual.

APPROXIMATION_MAP = {
    "mekko":       ("stackedBarChart",                   "Mekko chart mapped to Stacked Bar — variable-width bars are not supported"),
    "sankey":      ("sankeyDiagram",                     "Sankey diagram mapped to custom visual (ChicagoITSankey1.1.0) — install from AppSource"),
    "chord":       ("chordChart",                        "Chord diagram mapped to custom visual (ChicagoITChord1.0.0) — install from AppSource"),
    "network":     ("networkNavigator",                  "Network graph mapped to custom visual (NetworkNavigator1.0.0) — install from AppSource"),
    "ganttbar":    ("ganttChart",                         "Gantt bar mapped to custom visual (GanttByMAQSoftware1.0.0) — install from AppSource"),
    "bumpchart":   ("lineChart",                         "Bump chart mapped to Line Chart with auto-generated RANKX measure for ranking"),
    "slopechart":  ("lineChart",                         "Slope chart mapped to Line Chart — period comparison semantics lost"),
    "timeline":    ("lineChart",                         "Timeline mapped to Line Chart — event markers not supported"),
    "butterfly":   ("hundredPercentStackedBarChart",     "Butterfly chart mapped to 100% Stacked Bar — negate one measure to simulate symmetry"),
    "violin":      ("boxAndWhisker",                     "Violin plot mapped to Box and Whisker — distribution shape lost, use custom visual from AppSource (ViolinPlot1.0.0)"),
    "parallelcoordinates": ("lineChart",               "Parallel coordinates mapped to Line Chart — multi-axis layout lost, use custom visual from AppSource (ParallelCoordinates1.0.0)"),
    "calendarheatmap": ("matrix",                       "Calendar heat map mapped to Matrix with conditional formatting — configure color rules manually"),
    "waffle":      ("hundredPercentStackedBarChart",     "Waffle chart mapped to 100% Stacked Bar — grid layout lost"),
    "pareto":      ("lineClusteredColumnComboChart",     "Pareto mapped to Line+Column Combo — cumulative line may need adjustment"),
    "dualaxis":    ("lineClusteredColumnComboChart",     "Dual axis mapped to Line+Column Combo"),
}


def resolve_visual_type(source_type):
    """Resolve a source visualization type to a Power BI visual type.

    Checks ``VISUAL_TYPE_MAP`` first, then ``APPROXIMATION_MAP`` so that
    approximate types (e.g. Sankey → custom visual) are resolved correctly.
    """
    if not source_type:
        return "tableEx"
    key = source_type.lower()
    if key in VISUAL_TYPE_MAP:
        return VISUAL_TYPE_MAP[key]
    approx = APPROXIMATION_MAP.get(key)
    if approx:
        return approx[0]
    return "tableEx"


def get_approximation_note(source_type):
    """Return a migration note if the visual type is an approximation, else None."""
    if not source_type:
        return None
    entry = APPROXIMATION_MAP.get(source_type.lower())
    return entry[1] if entry else None


def get_custom_visual_guid_for_approx(source_type):
    """Return the GUID info dict if an approximation maps to a custom visual.

    Returns None if the approximation uses a built-in PBI visual type.
    """
    if not source_type:
        return None
    key = source_type.lower()
    approx = APPROXIMATION_MAP.get(key)
    if not approx:
        return None
    pbi_class = approx[0]
    # Check if the approximation target matches any custom visual class
    for cv_key, cv_info in CUSTOM_VISUAL_GUIDS.items():
        if cv_info.get('class') == pbi_class:
            return cv_info
    return None


# ═══════════════════════════════════════════════════════════════════
# Small Multiples support — visual types that support this feature
# ═══════════════════════════════════════════════════════════════════

SMALL_MULTIPLES_TYPES = {
    'clusteredBarChart', 'stackedBarChart', 'hundredPercentStackedBarChart',
    'clusteredColumnChart', 'stackedColumnChart', 'hundredPercentStackedColumnChart',
    'lineChart', 'areaChart', 'stackedAreaChart', 'hundredPercentStackedAreaChart',
    'lineStackedColumnComboChart', 'lineClusteredColumnComboChart',
}


def _build_small_multiples_config(field_name, table_name, layout_mode='flow',
                                   max_items_per_row=3, show_empty=False):
    """Build Small Multiples configuration for a visual.

    Args:
        field_name: Dimension field to split by
        table_name: Table containing the field
        layout_mode: 'flow' (auto-wrap) or 'fixed' (grid)
        max_items_per_row: Max panels per row (default 3)
        show_empty: Whether to show empty panels

    Returns:
        dict: Small Multiples config for PBIR visual
    """
    sm_config = {
        "showMultiplesCard": {
            "properties": {
                "show": _L("true"),
            }
        },
        "smallMultiple": [{
            "properties": {
                "show": _L("true"),
                "layoutMode": _L(f"'{layout_mode}'"),
                "maxItemsPerRow": _L(f"{max_items_per_row}L"),
                "showEmptyItems": _L("true" if show_empty else "false"),
            }
        }],
    }
    sm_projection = {
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
    return sm_config, sm_projection


def _calculate_proportional_layout(worksheets, page_width=1280, page_height=720,
                                    source_positions=None, padding=10):
    """Calculate proportional visual positions from Tableau dashboard layout.

    Improves on simple grid layout by using source positions when available,
    with overlap detection and padding adjustments.

    Args:
        worksheets: List of worksheet dicts
        page_width: Target page width in px
        page_height: Target page height in px
        source_positions: List of {x, y, w, h} from Tableau dashboard zones
        padding: Minimum padding between visuals

    Returns:
        List of (x, y, width, height) tuples
    """
    n = len(worksheets)
    if not n:
        return []

    # If source positions are available, scale proportionally
    if source_positions and len(source_positions) >= n:
        # Find bounding box of all source positions
        src_positions = source_positions[:n]
        min_x = min(p.get('x', 0) for p in src_positions)
        min_y = min(p.get('y', 0) for p in src_positions)
        max_r = max(p.get('x', 0) + p.get('w', 100) for p in src_positions)
        max_b = max(p.get('y', 0) + p.get('h', 100) for p in src_positions)
        src_w = max(max_r - min_x, 1)
        src_h = max(max_b - min_y, 1)

        scale_x = (page_width - 2 * padding) / src_w
        scale_y = (page_height - 2 * padding) / src_h

        positions = []
        for p in src_positions:
            x = padding + (p.get('x', 0) - min_x) * scale_x
            y = padding + (p.get('y', 0) - min_y) * scale_y
            w = max(p.get('w', 100) * scale_x, 60)
            h = max(p.get('h', 100) * scale_y, 40)
            positions.append((int(x), int(y), int(w), int(h)))

        # Overlap detection and correction
        for i in range(len(positions)):
            for j in range(i + 1, len(positions)):
                xi, yi, wi, hi = positions[i]
                xj, yj, wj, hj = positions[j]
                # Check horizontal overlap
                if (xi < xj + wj and xi + wi > xj and
                        yi < yj + hj and yi + hi > yj):
                    # Shift j to the right of i
                    positions[j] = (xi + wi + padding, yj, wj, hj)

        return positions

    # Fallback: smart grid layout based on visual count
    if n <= 2:
        cols = n
    elif n <= 4:
        cols = 2
    elif n <= 9:
        cols = 3
    else:
        cols = 4

    rows = (n + cols - 1) // cols
    cell_w = (page_width - padding * (cols + 1)) // cols
    cell_h = (page_height - padding * (rows + 1)) // rows
    # Enforce minimum size
    cell_w = max(cell_w, 150)
    cell_h = max(cell_h, 120)

    positions = []
    for idx in range(n):
        r, c = divmod(idx, cols)
        x = padding + c * (cell_w + padding)
        y = padding + r * (cell_h + padding)
        positions.append((x, y, cell_w, cell_h))

    return positions


def _build_dynamic_reference_line(ref_type, field_name=None, table_name=None,
                                   label='', color='#FF0000', style='dashed'):
    """Build a dynamic reference line (percentile, median, average, trend).

    Args:
        ref_type: 'average', 'median', 'percentile', 'min', 'max'
        field_name: Measure or column name
        table_name: Table containing the field
        label: Display label for the line
        color: Line color (hex)
        style: 'solid', 'dashed', 'dotted'

    Returns:
        dict: Reference line config for PBIR visual objects
    """
    style_map = {'solid': "'solid'", 'dashed': "'dashed'", 'dotted': "'dotted'"}
    pbi_style = style_map.get(style, "'dashed'")

    if ref_type == 'constant':
        return None  # Handled by existing constant line logic

    ref_config = {
        "properties": {
            "show": _L("true"),
            "displayName": _L(json.dumps(label or ref_type.capitalize())),
            "color": {"solid": {"color": color}},
            "style": _L(pbi_style),
        }
    }

    # Dynamic reference lines use analytics pane patterns
    if ref_type == 'average':
        ref_config["properties"]["type"] = _L("'Average'")
    elif ref_type == 'median':
        ref_config["properties"]["type"] = _L("'Median'")
    elif ref_type == 'percentile':
        ref_config["properties"]["type"] = _L("'Percentile'")
        ref_config["properties"]["percentile"] = _L("50D")
    elif ref_type == 'min':
        ref_config["properties"]["type"] = _L("'Min'")
    elif ref_type == 'max':
        ref_config["properties"]["type"] = _L("'Max'")
    elif ref_type == 'trend':
        ref_config["properties"]["type"] = _L("'Trend'")

    return ref_config


def _build_data_bar_config(column_name, table_name, min_color='#FFFFFF',
                            max_color='#4472C4', show_bar_only=False):
    """Build data bar conditional formatting for table/matrix columns.

    Args:
        column_name: Column to apply data bars to
        table_name: Table containing the column
        min_color: Color for minimum value (default white)
        max_color: Color for maximum value (default blue)
        show_bar_only: If True, hide the value and only show the bar

    Returns:
        dict: Data bar rule for conditional formatting
    """
    return {
        "id": f"dataBar_{column_name}",
        "field": {
            "Column": {
                "Expression": {"SourceRef": {"Entity": table_name}},
                "Property": column_name,
            },
        },
        "positiveColor": {"solid": {"color": max_color}},
        "negativeColor": {"solid": {"color": "#FF4444"}},
        "axisColor": {"solid": {"color": "#CCCCCC"}},
        "showBarOnly": show_bar_only,
        "minimumValue": None,
        "maximumValue": None,
    }


def generate_visual_containers(converted_worksheets, report_name="Report",
                               col_table_map=None, measure_lookup=None,
                               page_width=1280, page_height=720,
                               source_positions=None):
    """
    Generate visualContainers for definition.pbir

    Args:
        converted_worksheets: List of worksheets converted by worksheet_converter
        report_name: Report name (used for ID generation)
        col_table_map: {column_name: table_name} lookup
        measure_lookup: {measure_name: (table, dax_expr)} lookup
        page_width: Page width in pixels
        page_height: Page height in pixels
        source_positions: Optional list of {x, y, w, h} from Tableau dashboard

    Returns:
        List of visualContainers in Power BI Report Definition format
    """
    visual_containers = []
    ctm = col_table_map or {}
    ml = measure_lookup or {}

    worksheets = converted_worksheets[:20]
    positions = _calculate_proportional_layout(
        worksheets, page_width, page_height, source_positions,
    )

    for idx, worksheet in enumerate(worksheets):
        visual_id = _short_id(f"viz_{idx}_{report_name}")

        if idx < len(positions):
            x_pos, y_pos, width, height = positions[idx]
        else:
            x_pos, y_pos, width, height = 10, 10, 300, 200

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

    return visual_containers


def create_visual_container(worksheet, visual_id=None, x=10, y=10,
                            width=300, height=200, z_index=0,
                            col_table_map=None, measure_lookup=None):
    """
    Create a Power BI visualContainer from a converted worksheet.

    Supports:
    - All 118+ visual types via VISUAL_TYPE_MAP
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

    # Sprint 78: Dual-axis detection → combo chart override
    axes_data = worksheet.get('axes', {})
    if isinstance(axes_data, dict) and axes_data.get('dual_axis') and pbi_type not in (
            'lineClusteredColumnComboChart', 'lineStackedColumnComboChart'):
        pbi_type = 'lineClusteredColumnComboChart'

    # Check for approximation note
    approx_note = get_approximation_note(visual_type)

    # Generate a unique GUID for the visual
    vid = visual_id or _new_guid()

    # ── Build visual object ───────────────────────────────────
    visual_obj = {
        "visualType": pbi_type,
        "drillFilterOtherVisuals": True,
    }

    # Attach migration note for approximation-mapped visuals
    if approx_note:
        visual_obj["annotations"] = [
            {"name": "MigrationNote", "value": approx_note}
        ]

    # Apply PBIR-native config template
    config = _get_config_template(pbi_type)
    if "autoSelectVisualType" in config:
        visual_obj["autoSelectVisualType"] = config["autoSelectVisualType"]
    if "objects" in config:
        visual_obj["objects"] = config["objects"]

    # Build query state from dimensions/measures
    _build_visual_query_state(worksheet, pbi_type, ctm, ml, visual_obj)

    # Apply decorations: title, subtitle, formatting, filters, sort, reference lines, etc.
    _apply_visual_decorations(worksheet, visual_type, pbi_type, visual_name, ctm, visual_obj)

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

    # ── Visual-level filters → filterConfig ─────────────────
    # PBIR v4.0 does not allow "filters" as a top-level property
    # on the visual object or the container.  Filters go inside
    # container["filterConfig"]["filters"].
    viz_filters = worksheet.get('filters', [])
    if viz_filters:
        filter_list = _build_visual_filters(viz_filters, ctm)
        if filter_list:
            fc = container.setdefault("filterConfig", {})
            fc.setdefault("filters", []).extend(filter_list)

    return container


def _build_visual_query_state(worksheet, pbi_type, ctm, ml, visual_obj):
    """Build query state from dimensions, measures, and data fields."""
    data_fields = worksheet.get('dataFields', [])
    dimensions = worksheet.get('dimensions', [])
    measures = list(worksheet.get('measures', []))

    # ── Packed bubble / scatter: inject size from mark_encoding ─
    mark_enc = worksheet.get('mark_encoding', {})
    size_enc = mark_enc.get('size', {})
    if pbi_type == 'scatterChart' and size_enc.get('field'):
        size_field = size_enc['field']
        # Ensure size field appears as 3rd measure (→ Size data role)
        existing = [m.get('name', m.get('label', '')) for m in measures]
        if size_field not in existing:
            measures.append({'name': size_field, 'label': size_field,
                             'expression': f'SUM({size_field})'})

    # ── Bump chart: inject RANKX measure for ranking semantics ─
    source_type = (worksheet.get('visualType', '') or '').lower().replace(' ', '').replace('_', '')
    if source_type in ('bumpchart', 'bump chart', 'bump') and measures:
        # Use the first measure as the basis for ranking
        base_measure = measures[0]
        base_name = base_measure.get('label') or base_measure.get('name', 'Measure')
        rank_name = f'_bump_rank_{base_name}'
        # Determine table for RANKX (from col_table_map or first available)
        rank_table = ''
        if ctm:
            rank_table = next(iter(ctm.values()), 'Table')
        rank_expr = f'RANKX(ALL(\'{rank_table}\'), [{base_name}],, ASC, Dense)'
        # Add rank measure to the visual's Y axis (replaces original for rank positioning)
        measures.append({'name': rank_name, 'label': rank_name,
                         'expression': rank_expr})
        # Register as auto-generated so tmdl_generator can emit the DAX
        _AUTO_GENERATED_MEASURES.append({
            'name': rank_name,
            'table': rank_table,
            'expression': rank_expr,
            'description': f'Auto-generated RANKX measure for bump chart (ranks by [{base_name}])',
        })
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


def _apply_visual_decorations(worksheet, visual_type, pbi_type, visual_name, ctm, visual_obj):
    """Apply all visual decorations: title, subtitle, formatting, filters, sort, reference lines,
    data bars, small multiples, and axis config."""

    # ── Title ─────────────────────────────────────────────────
    visual_obj.setdefault("visualContainerObjects", {})
    visual_obj["visualContainerObjects"]["title"] = [{
        "properties": {
            "show": _L("true"),
            "text": _L(json.dumps(visual_name)),
        }
    }]

    # ── Subtitle ──────────────────────────────────────────────
    subtitle = worksheet.get('subtitle', '')
    if subtitle:
        visual_obj["visualContainerObjects"]["subTitle"] = [{
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

    # ── Calendar heat map: auto-enable conditional formatting ─
    source_key = (visual_type or '').lower().replace(' ', '').replace('_', '')
    if source_key in ('calendar', 'calendarheatmap', 'highlighttable') and pbi_type == 'matrix':
        visual_obj.setdefault("objects", {})
        visual_obj["objects"]["values"] = [{
            "properties": {
                "backColorConditionalFormatting": _L("true"),
                "fontColorConditionalFormatting": _L("true"),
            }
        }]
        if not visual_obj.get("annotations"):
            visual_obj["annotations"] = []
        visual_obj["annotations"].append({
            "name": "MigrationNote",
            "value": "Calendar/heat map: enable Background Color conditional formatting rules on the Values well in Power BI Desktop"
        })

    # ── Conditional formatting rules (explicit) ───────────────
    cond_format = worksheet.get('conditionalFormatting', [])
    if cond_format:
        visual_obj.setdefault("objects", {})
        visual_obj["objects"]["dataPoint"] = [{
            "properties": {"showAllDataPoints": _L("true")}
        }]

    # ── Sprint 79: Advanced conditional formatting from color encoding ──
    mark_enc_color = worksheet.get('mark_encoding', {}).get('color', {})
    if mark_enc_color and mark_enc_color.get('type'):
        visual_obj.setdefault("objects", {})
        color_type = mark_enc_color['type']
        thresholds = mark_enc_color.get('thresholds', [])
        palette_colors = mark_enc_color.get('palette_colors', [])

        if color_type == 'quantitative' and len(palette_colors) >= 3:
            # Diverging color scale (3-stop gradient: min → center → max)
            visual_obj["objects"]["dataPoint"] = [{
                "properties": {
                    "showAllDataPoints": _L("true"),
                    "fillRule": {
                        "linearGradient3": {
                            "min": {"color": palette_colors[0]},
                            "mid": {"color": palette_colors[len(palette_colors) // 2]},
                            "max": {"color": palette_colors[-1]},
                        }
                    }
                }
            }]
        elif color_type == 'quantitative' and len(palette_colors) == 2:
            # Sequential gradient (2-stop: min → max)
            visual_obj["objects"]["dataPoint"] = [{
                "properties": {
                    "showAllDataPoints": _L("true"),
                    "fillRule": {
                        "linearGradient2": {
                            "min": {"color": palette_colors[0]},
                            "max": {"color": palette_colors[-1]},
                        }
                    }
                }
            }]
        elif color_type == 'quantitative' and thresholds:
            # Stepped color (N discrete bins from thresholds)
            rules = []
            for th in thresholds:
                rule = {}
                if th.get('value') is not None:
                    rule["inputValue"] = th['value']
                if th.get('color'):
                    rule["color"] = th['color']
                rules.append(rule)
            if rules:
                visual_obj["objects"]["dataPoint"] = [{
                    "properties": {
                        "showAllDataPoints": _L("true"),
                        "fillRule": {
                            "steppedColor": {
                                "steps": rules,
                            }
                        }
                    }
                }]
        elif color_type == 'categorical' and palette_colors:
            # Categorical color assignment (explicit color per category)
            visual_obj["objects"]["dataPoint"] = [{
                "properties": {
                    "showAllDataPoints": _L("true"),
                }
            }]
            # Store per-category colors as separate data point entries
            for i, color in enumerate(palette_colors[:20]):
                visual_obj["objects"].setdefault("sentimentColors", [{
                    "properties": {}
                }])
                visual_obj["objects"]["sentimentColors"][0]["properties"][
                    f"color{i+1}"] = {"solid": {"color": color}}

    # ── Visual-level filters ─────────────────────────────────
    # NOTE: visual-level filters are applied in create_visual_container()
    # on container["filterConfig"] — PBIR v4.0 does not allow "filters"
    # as a top-level property on the visual object.

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
                    "direction": "Ascending" if direction.lower() == 'ascending' else "Descending",
                })
        if sort_state:
            visual_obj.setdefault("query", {})
            visual_obj["query"]["sortDefinition"] = {"sort": sort_state}

    # ── Reference lines and bands (constant + dynamic) ──────────
    ref_lines = worksheet.get('referenceLines', worksheet.get('reference_lines', []))
    if ref_lines:
        constant_lines = []
        dynamic_lines = []
        reference_bands = []
        for rl in ref_lines:
            ref_type = rl.get('type', 'constant')
            # Sprint 78: Reference band (shaded region between two values)
            if ref_type == 'band':
                band_values = rl.get('values', [])
                band_color = rl.get('color', rl.get('fill_color', '#4472C4'))
                band_opacity = rl.get('opacity', 0.2)
                if len(band_values) >= 2:
                    reference_bands.append({
                        "show": _L("true"),
                        "startValue": _L(f"{band_values[0]}D"),
                        "endValue": _L(f"{band_values[1]}D"),
                        "displayName": _L(json.dumps(rl.get('label', 'Band'))),
                        "color": {"solid": {"color": band_color}},
                        "transparency": _L(f"{round((1 - band_opacity) * 100)}D"),
                    })
                continue
            if ref_type in ('average', 'median', 'percentile', 'min', 'max', 'trend'):
                drl = _build_dynamic_reference_line(
                    ref_type=ref_type,
                    field_name=rl.get('field', ''),
                    table_name=ctm.get(rl.get('field', ''), 'Table'),
                    label=rl.get('label', ''),
                    color=rl.get('color', rl.get('line_color', '#FF0000')),
                    style=rl.get('style', 'dashed'),
                )
                if drl:
                    dynamic_lines.append(drl)
            else:
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
        if dynamic_lines:
            visual_obj.setdefault("objects", {})
            visual_obj["objects"]["referenceLine"] = dynamic_lines
        if reference_bands:
            visual_obj.setdefault("objects", {})
            visual_obj["objects"]["referenceBand"] = [
                {"properties": rb} for rb in reference_bands
            ]

    # ── Sprint 78: Data label formatting from mark encoding ───
    mark_enc = worksheet.get('mark_encoding', {})
    label_enc = mark_enc.get('label', {})
    if label_enc and label_enc.get('show'):
        visual_obj.setdefault("objects", {})
        label_props = {"show": _L("true")}
        if label_enc.get('font_size'):
            try:
                label_props["fontSize"] = _L(f"{int(label_enc['font_size'])}D")
            except (ValueError, TypeError):
                pass
        if label_enc.get('font_color'):
            label_props["color"] = {"solid": {"color": label_enc['font_color']}}
        if label_enc.get('position'):
            pos_map = {'top': "'OutsideEnd'", 'center': "'InsideCenter'",
                       'bottom': "'InsideBase'", 'left': "'Left'", 'right': "'Right'"}
            pbi_pos = pos_map.get(label_enc['position'], "'OutsideEnd'")
            label_props["labelPosition"] = _L(pbi_pos)
        if label_enc.get('orientation') == 'vertical':
            label_props["orientation"] = _L("'Vertical'")
        visual_obj["objects"]["labels"] = [{"properties": label_props}]

    # ── Sprint 78: Trend line from analytics ──────────────────
    trend_lines = worksheet.get('trendLines', worksheet.get('trend_lines', []))
    if trend_lines:
        visual_obj.setdefault("objects", {})
        for tl in trend_lines:
            reg_type = tl.get('regression_type', 'linear')
            reg_map = {'linear': "'Linear'", 'logarithmic': "'Logarithmic'",
                       'exponential': "'Exponential'", 'power': "'Power'",
                       'polynomial': "'Polynomial'", 'moving_average': "'MovingAverage'"}
            tl_props = {
                "show": _L("true"),
                "lineColor": {"solid": {"color": tl.get('color', '#666666')}},
                "style": _L("'dashed'"),
                "regressionType": _L(reg_map.get(reg_type, "'Linear'")),
            }
            if reg_type == 'polynomial':
                order = tl.get('order', 2)
                tl_props["polynomialOrder"] = _L(f"{order}D")
            visual_obj["objects"]["trend"] = [{"properties": tl_props}]

    # ── Sprint 78: Mark size encoding → bubble size config ────
    size_enc = mark_enc.get('size', {})
    if size_enc.get('field') and pbi_type in ('scatterChart',):
        visual_obj.setdefault("objects", {})
        bubble_props = visual_obj["objects"].get("bubbles", [{}])[0].get("properties", {})
        bubble_props["show"] = _L("true")
        bubble_props["bubbleSizeBy"] = _L("'Value'")
        visual_obj["objects"]["bubbles"] = [{"properties": bubble_props}]

    # ── Data bars for table/matrix columns ─────────────────────
    if pbi_type in ('tableEx', 'matrix'):
        data_bars = worksheet.get('dataBars', worksheet.get('data_bars', []))
        if data_bars:
            bar_rules = []
            for db in data_bars:
                col_name = db.get('column', db.get('field', ''))
                tbl_name = ctm.get(col_name, 'Table')
                bar_rules.append(_build_data_bar_config(
                    col_name, tbl_name,
                    min_color=db.get('minColor', '#FFFFFF'),
                    max_color=db.get('maxColor', '#4472C4'),
                    show_bar_only=db.get('showBarOnly', False),
                ))
            if bar_rules:
                visual_obj.setdefault("objects", {})
                visual_obj["objects"]["values"] = [{
                    "properties": {
                        "dataBar": bar_rules,
                    }
                }]

    # ── Small Multiples ───────────────────────────────────────
    sm_field = worksheet.get('smallMultiples', worksheet.get('small_multiples', {}))
    if isinstance(sm_field, dict) and sm_field.get('field') and pbi_type in SMALL_MULTIPLES_TYPES:
        sm_config, sm_proj = _build_small_multiples_config(
            field_name=sm_field['field'],
            table_name=ctm.get(sm_field['field'], 'Table'),
            layout_mode=sm_field.get('layout', 'flow'),
            max_items_per_row=sm_field.get('maxPerRow', 3),
            show_empty=sm_field.get('showEmpty', False),
        )
        visual_obj.setdefault("objects", {})
        visual_obj["objects"].update(sm_config)
        # Add SmallMultiple role to query state
        visual_obj.setdefault("query", {})
        visual_obj["query"].setdefault("queryState", {})
        visual_obj["query"]["queryState"]["SmallMultiple"] = {
            "projections": [sm_proj]
        }

    # ── Axis config (min/max, log, reversed) ──────────────────
    axes_data = worksheet.get('axes', {})
    if isinstance(axes_data, dict) and axes_data:
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

        # Sprint 78: Secondary Y axis for dual-axis / combo charts
        if axes_data.get('dual_axis') and pbi_type in (
                'lineClusteredColumnComboChart', 'lineStackedColumnComboChart'):
            y2_props = {"show": _L("true")}
            sync = axes_data.get('dual_axis_sync', False)
            if not sync:
                y2_props["secShow"] = _L("true")
            visual_obj["objects"]["y1AxisReferenceLine"] = []
            visual_obj["objects"]["valueAxis2"] = [{"properties": y2_props}]

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
                "values": [[{"Literal": {"Value": f"'{v}'"}}] for v in values],
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


def create_filters_config(filters, table_name=None):
    """
    Create the filter configuration for a visual
    """
    filters_config = []
    # Resolve table name from context; fall back to 'Table1'
    entity_name = table_name if table_name else 'Table1'

    for filt in filters:
        filter_config = {
            "expression": {
                "Column": {
                    "Expression": {
                        "SourceRef": {"Entity": entity_name}
                    },
                    "Property": filt.get('field', 'Field')
                }
            },
            "filter": {
                "Version": 2,
                "From": [{"Name": "t", "Entity": entity_name, "Type": 0}],
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


# ═══════════════════════════════════════════════════════════════════
# Python / R Script Visual Generator
# ═══════════════════════════════════════════════════════════════════

def generate_script_visual(visual_name, script_info, fields=None,
                           x=10, y=10, width=400, height=300, z_index=0):
    """Generate a Power BI Python or R script visual container.

    Power BI Desktop supports ``scriptVisual`` (Python) and
    ``scriptRVisual`` (R) visual types that execute user-provided
    scripts against a dataframe built from the selected fields.

    Args:
        visual_name: Display name for the visual.
        script_info: Dict from ``dax_converter.detect_script_functions()``
            with keys ``language``, ``code``, ``function``, ``return_type``.
        fields: Optional list of field names used by the script.
        x, y, width, height, z_index: Layout positioning.

    Returns:
        dict: PBIR-compatible visualContainer.
    """
    language = script_info.get('language', 'python')
    original_code = script_info.get('code', '')
    func_name = script_info.get('function', 'SCRIPT_REAL')

    # Map Tableau _argN references to PBI dataset column references
    adapted_code = original_code
    if fields:
        for i, field_name in enumerate(fields, start=1):
            clean_name = field_name.split('[')[-1].rstrip(']') if '[' in field_name else field_name
            if language == 'python':
                adapted_code = adapted_code.replace(f'_arg{i}', f'dataset["{clean_name}"]')
            else:
                adapted_code = adapted_code.replace(f'_arg{i}', f'dataset${clean_name}')

    if language == 'python':
        pbi_visual_type = 'scriptVisual'
        runtime_label = 'Python'
        script_content = (
            f"# Migrated from Tableau {func_name}\n"
            f"# Power BI provides a 'dataset' pandas DataFrame with your selected fields.\n"
            f"import matplotlib.pyplot as plt\n"
            f"import pandas as pd\n\n"
        )
        if adapted_code != original_code:
            # Successfully mapped args — include adapted code
            script_content += f"# Adapted script (original _argN mapped to dataset columns):\n"
            for line in adapted_code.split('\n'):
                script_content += f"{line}\n"
            script_content += "\nplt.show()\n"
        else:
            # Could not map — include original as comments with scaffold
            for line in original_code.split('\n'):
                script_content += f"# {line}\n"
            script_content += (
                "\n# TODO: Adapt the commented Tableau script above for PBI dataset DataFrame.\n"
                "fig, ax = plt.subplots()\n"
                "ax.text(0.5, 0.5, 'Adapt Tableau script for PBI',\n"
                "        ha='center', va='center', fontsize=14)\n"
                "plt.show()\n"
            )
    else:
        pbi_visual_type = 'scriptRVisual'
        runtime_label = 'R'
        script_content = (
            f"# Migrated from Tableau {func_name}\n"
            f"# Power BI provides a 'dataset' data.frame with your selected fields.\n\n"
        )
        if adapted_code != original_code:
            script_content += f"# Adapted script (original _argN mapped to dataset columns):\n"
            for line in adapted_code.split('\n'):
                script_content += f"{line}\n"
        else:
            for line in original_code.split('\n'):
                script_content += f"# {line}\n"
            script_content += (
                "\n# TODO: Adapt the commented Tableau script above for PBI dataset data.frame.\n"
                "plot(1, type='n', main='Adapt Tableau script for PBI')\n"
                "text(1, 1, 'Adapt the commented script above', cex=1.2)\n"
            )

    vid = _new_guid()

    visual_obj = {
        "visualType": pbi_visual_type,
        "drillFilterOtherVisuals": True,
        "script": {
            "scriptProviderDefault": language,
            "scriptOutputType": "static",
            "scriptText": script_content.rstrip(),
        },
        "annotations": [
            {
                "name": "MigrationNote",
                "value": (
                    f"Converted from Tableau {func_name}. "
                    f"Requires {runtime_label} runtime configured in PBI Desktop "
                    f"(File → Options → {runtime_label} scripting). "
                    f"Original script preserved as comments."
                ),
            }
        ],
    }

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

    return container
