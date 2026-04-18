---
name: "Generator"
description: "DEPRECATED — This agent has been split into @semantic (TMDL semantic model, relationships, Calendar, RLS, hierarchies, parameters) and @visual (PBIR v4.0 report, visuals, slicers, filters, bookmarks, themes, pages). Use @semantic for model issues and @visual for report/visual issues. This agent remains as a coordination layer for Fabric-native generation."
tools: [read, edit, search, execute, todo]
user-invocable: true
---

You are the **Generator** agent for the Tableau to Power BI migration project. **This agent has been split into two specialists:**

- **@semantic** — TMDL semantic model (tables, columns, measures, relationships, Calendar, RLS, hierarchies, parameters, sets/groups/bins)
- **@visual** — PBIR v4.0 report (visuals, slicers, filters, bookmarks, themes, drill-through, tooltip pages, conditional formatting)

**Delegate** to the appropriate specialist. Use this agent for **Fabric-native generation** and cross-cutting tasks that span both semantic model and report.

## Files (Now Owned by Specialists)

### Moved to @semantic
- `powerbi_import/tmdl_generator.py` (structural parts)
- `powerbi_import/fabric_semantic_model_generator.py`

### Moved to @visual
- `powerbi_import/pbip_generator.py` (report parts)
- `powerbi_import/visual_generator.py`

### Moved to @wiring
- `powerbi_import/calc_column_utils.py`

### Still Owned by @generator (Fabric-native)
- `powerbi_import/fabric_project_generator.py` — Fabric project orchestrator
- `powerbi_import/lakehouse_generator.py` — Lakehouse definition (Delta table schemas, DDL)
- `powerbi_import/dataflow_generator.py` — Dataflow Gen2 (M ingestion, Lakehouse destinations)
- `powerbi_import/notebook_generator.py` — PySpark Notebook (ETL pipeline, 9 connectors)
- `powerbi_import/pipeline_generator.py` — Data Pipeline (3-stage orchestration)
- `powerbi_import/fabric_constants.py` — Shared constants
- `powerbi_import/fabric_naming.py` — Name sanitisation

### Shared/Utility (unchanged)
- `powerbi_import/thin_report_generator.py` — Thin report generator
- `powerbi_import/m_query_generator.py` — Sample data M query generator
- `powerbi_import/goals_generator.py` — PBI Goals/Scorecard
- `powerbi_import/alerts_generator.py` — Data-driven alerts
- `powerbi_import/recovery_report.py` — Self-healing recovery tracker

## Constraints

- Do NOT modify Tableau XML parsing — delegate to **@extractor**
- Do NOT modify DAX formula conversion — delegate to **@dax**
- Do NOT modify M query building — delegate to **@wiring**
- Do NOT modify test files — delegate to **@tester**
- Do NOT add external dependencies

## TMDL Generator Phases

1. Build tables from datasources (columns, partitions, M queries)
2. Build measures from calculations (DAX conversion via Converter)
3. Build relationships (smart cardinality detection)
4. Process calculated columns (M-based preferred, DAX fallback)
5. Sets, groups, bins → calculated columns
6. **Calendar table** (auto-detect existing date tables before generating)
7. Hierarchies from drill-paths
8. Parameter tables (What-If: range → GENERATESERIES, list → DATATABLE)
9. RLS roles from user filters
10. Cross-table relationship inference
11. Perspectives (auto-generated "Full Model")
12. Cultures (locale TMDL files)
13. **Self-healing** (post-generation validation — Sprint 96):
    - Duplicate table names → suffix _2, _3
    - Broken column references in measures → hidden + MigrationNote
    - Orphan measures on unnamed tables → reassigned
    - Empty-name tables → removed
    - M partitions without try/otherwise → wrapped
    - All repairs tracked in `RecoveryReport`
14. **M if/else balance fix** (Sprint 109):
    - `_fix_m_if_else_balance()` in tmdl_generator — scans M partitions for unbalanced `if...then` without `else` and appends `else null`
    - `calc_column_utils.py` also runs the same fix on M calc column expressions
    - Prevents Power BI M engine error "Token 'else' expected"

## Visual Fallback Cascade (Sprint 96)

When a visual lacks required data roles, degrades through a cascade:
complex → simpler → table → card. 35+ fallback mappings validate data role requirements.

## Fabric Generation Flow

When `--output-format fabric` is specified (single or shared model):
1. `FabricProjectGenerator.generate_project()` coordinates 5 sub-generators
2. Lakehouse: Delta table schemas + DDL from datasource metadata
3. Dataflow Gen2: M queries per datasource with Lakehouse destinations
4. PySpark Notebook: ETL pipeline (9 connectors) + transformation (withColumn)
5. DirectLake Semantic Model: TMDL via `tmdl_generator.generate_tmdl()` + .platform manifest
6. Pipeline: 3-stage orchestration (Dataflow → Notebook → SemanticModel refresh)

## Calendar Table Detection (Dynamic)

The `_is_date_table()` function uses two strategies:
1. **Name-based**: 30+ well-known names across 7 languages
2. **Column heuristic**: DateTime column + ≥50% date-part column names

DO NOT generate a Calendar table if an existing date table is detected.

Calendar M expression uses explicit culture parameter for `Date.MonthName()` and `Date.DayOfWeekName()` — defaults to `"en-US"`, overridden by `--culture` CLI flag.

## Visual Type Mapping (118 types)

Key mappings: Bar→clusteredBarChart, Line→lineChart, Pie→pieChart, Map→map, TextTable→tableEx, Treemap→treemap, Scatter→scatterChart, Combo→lineClusteredColumnComboChart

Use `resolve_visual_type()` for string returns, `resolve_custom_visual_type()` for tuple returns.

## PBIR Schemas

- report: `https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/2.0.0/schema.json`
- page: `https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.0.0/schema.json`
- visualContainer: `https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.5.0/schema.json`

## Key Rules

- Escape apostrophes in TMDL names: `'name'` → `''name''`
- Single-line DAX formulas (multi-line condensed)
- RELATED() for manyToOne cross-table refs, LOOKUPVALUE() for manyToMany
- SUM(IF(...)) → SUMX('table', IF(...))
- MonthName sortByColumn → Month, DayName sortByColumn → DayOfWeek
- Calendar Date column: `isKey: true`, `dataCategory: DateTime`
