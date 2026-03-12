# Comprehensive Gap Analysis — Tableau to Power BI Migration Tool

**Date:** 2026-07-16 — updated through v10.0.0 (Sprints 13-34)  
**Scope:** Every source file, test file, CI/CD, docs, config, and cross-project comparison with TableauToFabric  
**Status:** 3,342 tests passing across 60 test files, 93.08% coverage

### Implementation Coverage

```
 EXTRACTION          GENERATION         INFRA / CI         DOCUMENTATION
+----------------+  +----------------+  +----------------+  +----------------+
| 20 object types|  | PBIR v4.0      |  | 5-stage CI/CD  |  | 13 doc files   |
| .twb/.twbx/.tfl|  | TMDL semantic  |  | 3,342 tests    |  | DAX reference  |
| 180+ DAX conv  |  | 60+ visuals    |  | Artifact valid |  | M query ref    |
| 33 connectors  |  | Drill-through  |  | Fabric deploy  |  | Prep ref       |
| 40+ transforms |  | Slicer modes   |  | Env configs    |  | Architecture   |
| Prep flow DAG  |  | Cond. format   |  | Settings valid |  | Gap analysis   |
| Ref lines/bands|  | RLS roles      |  | --dry-run      |  | Migration guide|
| Datasrc filters|  | Calendar/culture|  | --culture      |  | FAQ + more     |
| 22 new methods |  | Quick table cal|  | --assess       |  |                |
+-------+--------+  +-------+--------+  +-------+--------+  +-------+--------+
        |                    |                    |                    |
        +--------------------+--------------------+--------------------+
                                     |
                           v9.0.0 → v10.0.0
                     +-------------------------------+
                     | Plugin system & examples      |
                     | PyPI auto-publish workflow    |
                     | PBIR schema forward-compat    |
                     | Fractional deploy timeouts    |
                     +-------------------------------+
```

---

## 1. Extraction Layer (`tableau_export/`)

### What IS implemented
- **20 object types extracted**: worksheets, dashboards, datasources, calculations, parameters (old+new XML format), filters, stories, actions (filter/highlight/url/param/set-value), sets, groups (combined+value), bins, hierarchies, sort_orders, aliases, custom_sql, user_filters, **custom_geocoding**, **published_datasources**, **data_blending**, **hyper_metadata**
- **File formats**: `.twb`, `.twbx`, `.tds`, `.tdsx` (Tableau Desktop) + `.tfl`/`.tflx` (Tableau Prep)
- **Connection parsing** (`datasource_extractor.py`): 10 connection types fully parsed (Excel, CSV, GeoJSON, SQL Server, PostgreSQL, BigQuery, Oracle, MySQL, Snowflake, SAP BW) + fallback for unknown types; **metadata-records fallback** for SQL Server connections with self-closing `<relation>` elements; **last-resort column fallback** from datasource-level `<column>` elements; **default_format** extracted per column
- **Relationship extraction**: Both old `[Table].[Column]` join-clause format and new Object Model relationships; bare `[Column]` refs inferred from child relation order
- **Table deduplication**: Only physical tables (`type="table"`), deduplicated by name; SQL Server fallback via datasource-level `<cols>` mapping
- **Mark-to-visual mapping** (`_map_tableau_mark_to_type`): 50+ entries covering standard marks, extended chart types (Tableau 2020+)
- **Dashboard objects**: worksheetReference, text, image, web, blank, filter_control, **navigation_button**, **download_button**, **extension** with floating/tiled/fixed layout modes; **padding, margin, and border** extracted from `<zone-style>` format elements; **text_runs** with bold/italic/color/font_size/url for rich text
- **Mark encoding**: color (quantitative/categorical type detection via `:qk`/`:nk` suffixes, palette colors from `<color-palette>`, **stepped color thresholds**), size, shape, label (position/font/orientation), tooltips (text + viz-in-tooltip), **legend_position**
- **Story points**: Captured with filter state per story point
- **Actions**: 6 types (filter, highlight, url, navigate, parameter, set-value) with **run_on/activation**, **clearing behavior**, **highlight field_mappings**, **set-value target_set/target_field/assign_behavior/set_name/set_field**
- **User filters**: User-filter XML elements, calculated security (USERNAME/FULLNAME/ISMEMBEROF)
- **CSV delimiter auto-detection**: Attempts `csv.Sniffer` on embedded CSV from `.twbx` archives
- **Prep flow parsing** (`prep_flow_parser.py`): Full DAG traversal (Kahn's topological sort), 5 input types, 15+ Clean action types, Aggregate, Join (6 types), Union, Pivot; **new handlers**: ExtractValues (regex/pattern), CustomCalculation (expression→M), Script/RunCommand (warning column), Prediction/TabPy/Einstein (warning column), CrossJoin (Table.Join + FullOuter), PublishedDataSource (external ref); **5 new connection mappings**: odata, google-analytics, azure-blob, adls, wasbs; `merge_prep_with_workbook()` for TWB+Prep integration; **connection/connection_map/is_prep_source** metadata on all datasource emission sites
- **Reference lines, bands & distributions**: Reference lines (constant/average/median/trend with style/color/thickness and child `<reference-line-value>`/`<reference-line-label>` element parsing), **reference bands** (auto-detected from 2+ `<reference-line-value>` children with `is_band` flag and `value_from`/`value_to`), **reference distributions** (computation/percentile), trend lines with type/degree/confidence/R², and annotations (point/area type with text and position)
- **Legend extraction**: Position, title, font from `<legend>` element + `legend-title`/`color-legend` style-rule merging
- **Layout containers**: `<layout-container>` parsed for orientation (horizontal/vertical), position, and child zone names
- **Device layouts**: `<device-layout>` parsed for device type (phone/tablet), zone visibility/positions, auto-generated flag
- **Formatting depth**: Table/header formatting attributes (font-size, font-weight, color, align, border, banding) from `<format>` elements with scope; style-rule sub-format collection
- **Axis detection**: Continuous vs discrete type detection, dual-axis detection (multiple y-axes), `dual_axis_sync` from `synchronized` attribute; axis range (min/max), log scale, reversed orientation
- **Sort order depth**: Computed sort (sort-by field via `using` attribute), sort type detection (manual/computed/alphabetic), **manual_values**, **sort_using** field
- **Table calc field detection**: Regex for `pcto`, `pctd`, `diff`, `running_*`, `rank*` prefixed field names; addressing/partitioning field extraction from `<table-calc>` elements
- **Tooltips**: Per-run formatting extraction (**bold**, **color**, **font_size**, **field_ref**) with proper runs list structure
- **Theme extraction**: Dashboard colors, **custom_palettes**, **font_family**, workbook-level palette extraction
- **22 new extraction methods** (ported from Fabric): `extract_trend_lines`, `extract_pages_shelf`, `extract_table_calcs`, `extract_dashboard_containers`, `extract_forecasting`, `extract_map_options`, `extract_clustering`, `extract_dual_axis_sync`, `extract_custom_shapes`, `extract_embedded_fonts`, `extract_custom_geocoding`, `extract_published_datasources`, `extract_data_blending`, `extract_hyper_metadata`, `extract_totals_subtotals`, `extract_worksheet_description`, `extract_show_hide_headers`, `extract_dynamic_title`, `extract_show_hide_containers`, `extract_dynamic_zone_visibility`, `extract_floating_tiled`, `extract_analytics_pane_stats`
- **Worksheet enrichment**: 12 new keys per worksheet: `trend_lines`, `pages_shelf`, `table_calcs`, `forecasting`, `map_options`, `clustering`, `dual_axis`, `totals`, `description`, `show_hide_headers`, `dynamic_title`, `analytics_stats`
- **Dashboard enrichment**: 4 new keys per dashboard: `containers`, `show_hide_containers`, `dynamic_zone_visibility`, `floating_tiled`
- **Filter enrichment**: `is_context` flag on filters from `context='true'` attribute

### What is MISSING or INCOMPLETE
- **Tableau Server/Cloud connection types**: ✅ IMPLEMENTED — `TableauServerClient` in `server_client.py` provides PAT/password auth, workbook download, datasource listing, batch download, regex search via `--server` CLI flag
- **`.hyper` file parsing**: ✅ IMPLEMENTED — `hyper_reader.py` reads `.hyper` files via SQLite interface (column metadata + row data), schema discovery, type mapping to M/TMDL types; row data injected into M `#table()` expressions
- **Tableau extensions/LOD filters**: LOD calc extraction relies on text-based `{FIXED ...}` parsing (can miss edge cases with nested LODs or LOD inside LOD)
- **Dashboard layout containers**: Layout containers are extracted but deeply nested containers may lose relative positioning when mapped to PBI
- **Tableau 2024.3+ features**: ✅ IMPLEMENTED — Dynamic parameters with database queries fully extracted and converted to M partition with `Value.NativeQuery()` for dynamic parameter refresh
- **Connection credentials/OAuth**: Credential metadata is stripped (by design), but OAuth redirect configs aren't migrated
- **Multiple data sources per worksheet**: The extractor handles this, but the downstream TMDL generator may place all calculations on the "main" table, losing the datasource context
- **Tooltip formatting**: Rich tooltip formatting (HTML, custom layout) — basic run-level formatting now extracted but complex HTML layouts are not preserved

### What is APPROXIMATED
- **Prep VAR/VARP aggregations**: Mapped to `sum` in `_PREP_AGG_MAP` (not mathematically correct)
- **Prep `notInner` join type**: Mapped to `full` join (an approximation — should ideally be left-anti)
- **Dashboard positions**: Positions are relative to the Tableau canvas, scaled proportionally to PBI page dimensions — pixel-perfect reproduction is not guaranteed
- **CSV delimiter detection**: Falls back to comma if `csv.Sniffer` fails

---

## 2. Generation Layer (`powerbi_import/`)

### What IS implemented
- **Complete .pbip project structure**: `.pbip`, `.gitignore`, SemanticModel (`.platform`, `definition.pbism`, TMDL), Report (PBIR v4.0), migration metadata JSON
- **12-phase TMDL model** (`tmdl_generator.py`, 2741 lines):
  1. Table deduplication
  2. Main table identification, column metadata, DAX context
  3. Tables with columns, M queries, measures, calculated columns — **M-first approach**: calculated columns use Power Query M `Table.AddColumn` steps via `_dax_to_m_expression()` converter with DAX fallback for cross-table references
  4. Relationships (cross-datasource dedup, validation, type mismatch fixing)
  5. Sets/groups/bins as M-based calculated columns (with DAX fallback)
  6. Auto date table (M partition, not DAX calculated) **with Date Hierarchy** (Year → Quarter → Month → Day) — date hierarchies also use M-based columns
  7. Hierarchies from drill-paths
  8. What-If parameter tables (range → `GENERATESERIES`, list → `DATATABLE`, any → measure)
  9. RLS roles (user filter → USERPRINCIPALNAME, USERNAME/FULLNAME → DAX, ISMEMBEROF → per-group role)
  9b. Quick table calc measures (pcto → DIVIDE, running_sum → CALCULATE, rank → RANKX)
  10. Infer missing relationships from cross-table DAX refs
  10b. Cardinality detection (manyToOne vs manyToMany based on join type + column ratio)
  10c. RELATED() → LOOKUPVALUE() conversion for manyToMany
  11. Deactivate ambiguous relationship paths (Union-Find cycle detection)
  12. Auto-generate perspectives
  13. Calculation groups from param-swap actions
  14. Field parameters with NAMEOF
- **DAX-to-M expression converter** (`_dax_to_m_expression()`, `_split_dax_args()`, `_extract_function_body()`): Converts DAX calculated column expressions to Power Query M `Table.AddColumn` steps — supports IF, SWITCH, UPPER/LOWER/TRIM/LEN/LEFT/RIGHT/MID, ISBLANK, INT/VALUE, CONCATENATE, IN, &, arithmetic operators, column references
- **M step injection** (`_inject_m_steps_into_partition()`, `_build_m_transform_steps()`): Composes multiple M column steps into the table's M partition expression, chaining via `{prev}` placeholder
- **TMDL file writers**: database.tmdl, model.tmdl, relationships.tmdl, expressions.tmdl, roles.tmdl, tables/*.tmdl, perspectives.tmdl, cultures/*.tmdl, diagramLayout.json
- **Visual generation** (`visual_generator.py`, 938 lines): 60+ visual type mappings, 30+ PBIR config templates, data role definitions for 30+ types, queryState builder, slicer sync groups, cross-filtering disable, action button navigation (page + URL), TopN/categorical visual-level filters, sort state, reference lines, **axis config** (range min/max, log scale, reversed)
- **PBIP generator** (`pbip_generator.py`, 2326 lines): Dashboard → pages, worksheet → visuals, text → textbox, image → image, filter_control → slicer, tooltip pages **with binding to parent visuals** (tooltip_page_map), bookmarks from stories, theme generation, **action button visuals** (URL WebUrl + sheet-navigate PageNavigation), **pages shelf slicer**, **number format conversion** (`_convert_number_format()`)
- **Power Query M generation** (`m_query_builder.py` in extraction layer): 25 connector types + 30+ transform functions
- **Pre-migration assessment** (`assessment.py`, 912 lines): 8-category readiness assessment (datasource compatibility, calculation readiness, visual coverage, filter complexity, data model complexity, interactivity, extract/packaging, migration scope) with pass/warn/fail severity scoring
- **Strategy advisor** (`strategy_advisor.py`, 334 lines): Recommends Import/DirectQuery/Composite connection mode based on 7 signals (datasource type, data volume, calculation complexity, real-time needs, cross-source joins, parameter usage, user count); classifies calculations by portability
- **Theme migration**: Tableau dashboard color palettes → PBI theme JSON (`RegisteredResources/TableauMigrationTheme.json`)
- **Conditional formatting**: Quantitative color encoding → PBI dataPoint gradient rules with **multi-stop support** (2-color min/max, 3+ color min/mid/max), proper `inputRole` structure
- **Reference lines**: Constant value lines AND dynamic reference lines (average/median/percentile/min/max) are migrated via `_build_dynamic_reference_line()`; distribution and trend-line reference lines are approximated
- **Legend config**: Dynamic position mapping (8 positions: right/top/bottom/left/topRight/topLeft/bottomRight/bottomLeft), title/showTitle, fontSize from formatting
- **Axis config**: Range (min/max), log scale, reversed axis; **dual-axis secondary axis** for combo charts with sync detection
- **Combo chart roles**: Proper `ColumnY`/`LineY` role names (not generic `Y`/`Y2`)
- **Sort state**: Worksheet sort orders → visual `sortDefinition` with **computed sort** (sort-by-measure via Aggregation expression)
- **Table/matrix formatting**: Column header styles (fontSize, bold, fontColor), row banding (alternating backColor), grid borders for tableEx/table/matrix visuals
- **Dashboard padding/borders**: Padding/margin/border extracted and applied to visual containers
- **Mobile layout pages**: Phone device layouts → 320×568 mobile pages with zone visibility
- **Deployment** (`deployer.py`): Fabric REST API deployment with retry logic, batch deployment, `FabricClient` with requests/urllib fallback
- **Authentication** (`auth.py`): Service Principal (ClientSecretCredential) + Managed Identity (DefaultAzureCredential), lazy import of azure-identity
- **Configuration** (`config/`): Environment-based (dev/staging/production), `_FallbackSettings` (stdlib) + optional pydantic-settings, .env file support
- **Validation** (`validator.py`): Validates .pbip file, report directory, JSON validity, TMDL syntax

### What is MISSING or INCOMPLETE
- **No semantic validation of generated TMDL**: ✅ IMPLEMENTED — `validate_semantic_references()` in validator.py collects table/column/measure symbols and validates `'Table'[Column]` DAX references
- **No incremental migration**: ✅ IMPLEMENTED — `IncrementalMerger` in `incremental.py` provides three-way merge preserving user edits; `--incremental DIR` CLI flag
- **No multi-language report support**: ✅ IMPLEMENTED — `--languages fr-FR,de-DE,ja-JP` generates multiple culture TMDL files with translated display folders (Dimensions→Dimensionen, Measures→Mesures, etc.) and translated calendar column names
- **No data bar / sparkline visuals**: ✅ PARTIALLY IMPLEMENTED — Data bars added in v4.0; sparkline generation added in v5.0
- **No drill-through pages**: ✅ IMPLEMENTED — `_create_drillthrough_pages()` in pbip_generator.py
- **No paginated reports**: ✅ IMPLEMENTED — Basic paginated report layout generation added in v5.0
- **Limited calendar table customization**: ✅ IMPLEMENTED — `--calendar-start`/`--calendar-end` CLI flags (default 2020–2030)
- **Deployment not end-to-end tested**: Integration test structure added in v5.0 (`test_fabric_integration.py`) — opt-in with `@pytest.mark.integration`
- **Stale file cleanup race conditions**: OneDrive lock leftovers handled via try/except but may still leave artifacts on Windows
- **`import_to_powerbi.py` loads JSON from hardcoded paths**: ✅ IMPLEMENTED — `source_dir` parameter allows configurable JSON source directory
- **No composite model support**: ✅ IMPLEMENTED — `--mode composite` enables DirectQuery + Import hybrid
- **No Small Multiples**: ✅ IMPLEMENTED — `_build_small_multiples_config()` auto-detects suitable fields
### What is APPROXIMATED
- **Visual positioning**: Dashboard objects are scaled proportionally from Tableau canvas to PBI page size. Not pixel-perfect; overlapping is possible
- **Slicer bindings**: ✅ IMPROVED — `_detect_slicer_mode()` auto-selects Dropdown/List/Between/Basic based on parameter domain_type and column datatype (date→Basic, numeric→Between, list→List, default→Dropdown)
- **Report-level filters**: ✅ IMPLEMENTED — Global filters and datasource-level filters are now promoted to report-level `filterConfig` via `_create_visual_filters()`. Parameters remain inlined as DAX measures.
- **Textbox/Image objects**: ✅ Rich text implemented via `_parse_rich_text_runs()` — supports bold, italic, color, font_size, URL formatting
- **Combo chart mapping**: Dual axis charts map to `lineClusteredColumnComboChart` with proper ColumnY/LineY roles; axis scale sync is detected but complex independent axis configurations may not fully transfer

---

## 3. Test Coverage

### What IS implemented
- **887 tests across 18 test files** (original) + **2,455 additional tests in v3.6–v10.0.0**, totaling **3,342 tests across 60 test files** including shared fixtures in `conftest.py`:

| Test File | Tests | Lines | Coverage Focus |
|-----------|-------|-------|----------------|
| `test_dax_converter.py` | 86 | 464 | Type mapping, bracket escape, empty inputs, simple functions, special functions, operators, structure (CASE/IF), LOD, column resolution, AGG(IF)→AGGX, table calcs, dates, references, math/stats, leakage detection, complex formulas |
| `test_m_query_builder.py` | 102 | 665 | Type mapping, M query generation for 7+ connectors, `inject_m_steps`, column/value/filter/aggregate/pivot/join/union/reshape/calculated transforms |
| `test_tmdl_generator.py` | 92 | 678 | `_quote_name`, `_tmdl_datatype`, `_tmdl_summarize`, `_safe_filename`, format strings, display folders, semantic role mapping, theme generation, `build_semantic_model` (single/multi table, measures, date table, perspectives, relationships, dedup), `_add_date_table` (sortByColumn, isKey, relationship), TMDL file writers (perspectives, culture, database, model, relationships, table, full model) |
| `test_visual_generator.py` | 65 | 397 | Visual type mapping (bar/column/line/pie/scatter/map/table/KPI/treemap/waterfall/combo/slicer/specialty/textbox/unknown), data roles, config templates, container creation, slicer sync groups, cross-filtering disable, action button navigation, visual filters (TopN/categorical), sort state, reference lines, query state builder |
| `test_pbip_generator.py` | 46 | 390 | `_clean_field_name`, `_make_visual_position`, `_is_measure_field`, `_build_visual_objects` (axes from axes_data, legend, labels, mark encoding) |
| `test_feature_gaps.py` | 44 | 870 | Reference lines, annotations, axes (basic/dual/log/reversed), legend (extraction/generation/position/title), mark labels, palette colors, dashboard padding, layout containers, device layouts, sort orders (basic/computed), combo chart roles, sort state, action buttons (URL/navigate/filter-skipped), table formatting, conditional formatting (2-color/3-color gradient), axis generation, formatting depth, padding application, quick table calc detection, table calc addressing (ALLEXCEPT), date hierarchy |
| `test_infrastructure.py` | 36 | 374 | ArtifactValidator (JSON/TMDL/project/directory), DeploymentReport, ArtifactCache, ConfigEnvironments, ConfigSettings, FabricAuthenticator, FabricClient, Deployer, MigrateCLI |
| `test_migration_report.py` | 36 | 245 | MigrationReport (pass/fail tracking, fidelity scoring, category breakdown, unsupported/approximate items, report formatting) |
| `test_extraction.py` | 29 | 225 | TableauExtractor initialization, TWB/TWBX parsing, worksheet/dashboard/datasource/calculation/parameter/filter/story/action/set/group/bin/hierarchy extraction |
| `test_prep_flow_parser.py` | 58 | 621 | Graph traversal (topological sort), step conversion (Clean/Join/Aggregate/Union/Pivot), expression conversion, merge with TWB datasources, edge cases |
| `test_migration.py` | 10 | 241 | Extraction file existence, conversion file existence, worksheets/dashboards/datasources/calculations/parameters/filters/stories conversion, data integrity |
| `test_non_regression.py` | 63 | 546 | Per-sample project tests (Superstore, HR Analytics, Financial Report, BigQuery, Enterprise Sales, Manufacturing IoT, Marketing Campaign, Security Test) + cross-sample consistency (metadata, model.tmdl, empty dirs, schema consistency) |
| `test_migration_validation.py` | 0 | 806 | Disabled — previously tested via non-regression pipeline |
| `test_gap_implementations.py` | 50 | 632 | DAX fixes (CORR/COVAR/LOD/ATTR), datasource filters, semantic validation, slicer modes, drill-through pages, number format conversion, settings validation, calendar customization, CLI args, reference bands, deployment edge cases |
| `test_assessment.py` | 55 | 450 | Pre-migration assessment: 8 category checks (datasource, calculation, visual, filter, data model, interactivity, extract, scope), severity scoring, report generation, JSON export |
| `test_strategy_advisor.py` | 26 | 178 | Strategy advisor: Import/DirectQuery/Composite recommendations, signal-based scoring, calculation classification, print output |
| `test_new_features.py` | 74 | 689 | Calculation groups, field parameters, pages shelf, number format, context filters, visual config, **DAX-to-M expression conversion** (14 tests: IF, SWITCH, UPPER/LOWER, ISBLANK, LEFT/RIGHT/MID, arithmetic, column refs, IN, concatenation, nested IF), **M-based columns** (7 tests: sets, groups, bins, date hierarchies, fallback for cross-table refs, step injection) |
| `conftest.py` | — | 132 | Shared test fixtures: `sample_datasources()`, `sample_worksheets()`, `sample_calculations()`, `sample_model()` for reuse across test files |
| `test_sprint_13.py` | 53 | ~450 | Sprint 13: custom visual GUIDs, stepped colors, dynamic reference lines, multi-DS routing, sortByColumn validation, nested LOD cleanup |
| `test_pbi_service.py` | 33 | ~350 | Sprint 14: PBIServiceClient, PBIXPackager, PBIWorkspaceDeployer — structural + integration tests |
| `test_server_client.py` | 26 | ~280 | Sprint 15: TableauServerClient — auth, list, download, batch, error handling (mock-based) |
| `test_telemetry.py` | 41 | ~286 | Sprint 33: Telemetry — enabled detection, collector init/start/finish/recording/save/send, version, read log, summary, get data |
| `test_comparison_report.py` | 20 | ~230 | Sprint 33: Comparison report — load JSON/extracted/PBIP, compare worksheets/calculations/datasources, generate report |
| `test_telemetry_dashboard.py` | 18 | ~230 | Sprint 33: Telemetry dashboard — escape, load reports, generate dashboard, main |
| `test_goals_generator.py` | 24 | ~190 | Sprint 33: Goals generator — cadence refresh, build goal, generate goals JSON, write artifact |
| `test_wizard.py` | 24 | ~180 | Sprint 33: Wizard — input helper, yes/no, choose, wizard_to_args, run_wizard |
| `test_import_to_powerbi.py` | 19 | ~185 | Sprint 33: Import orchestrator — init, load converted objects, import_all, generate project, main |

### What is MISSING or INCOMPLETE
- **No mocking of file I/O**: Tests write real files to tempdir — no mocking of file system operations
- **No negative/edge-case tests for deployment**: ✅ PARTIALLY ADDRESSED — `test_pbi_service.py` tests PBIServiceClient/PBIXPackager/PBIWorkspaceDeployer structure and error paths; real HTTP 429 retry not tested
- **No performance/stress tests**: ✅ IMPLEMENTED — `test_performance.py` with 9 benchmarks for large workbooks
- **No test for `--batch` mode**: ✅ IMPLEMENTED — Batch mode test in `test_integration.py`
- **DAX conversion coverage**: 86 tests covering common formula patterns out of 180+ documented conversions. LOD with multiple dimensions, nested LODs partially tested in v6.0.0 (Sprint 13 N.6)
- **No property-based or fuzzy testing**: ✅ IMPLEMENTED — `test_property_based.py` with 10+ fuzz tests (200 iterations each)

---

## 4. Visual Mapping Gaps

### What IS implemented
60+ Tableau mark types mapped to PBI visual types, including:
- Standard: Bar, Stacked Bar, Line, Area, Pie, Donut, Circle, Square, Text, Map, Polygon
- Extended: Histogram, Box Plot, Waterfall, Funnel, TreeMap, Bubble, Heat Map, Word Cloud
- Combo: Dual Axis, Pareto → `lineClusteredColumnComboChart`
- KPI/Gauge: Bullet, Radial, Gauge → `gauge`/`card`
- Tables: Text/Automatic → `tableEx`/`table`, Highlight Table → `matrix`

### What is MISSING or INCOMPLETE

| Tableau Visual | Current Mapping | Gap |
|---------------|----------------|-----|
| **Sankey / Chord / Network** | ✅ `sankeyDiagram` / `chordChart` / `networkNavigator` (custom visual GUIDs) | Custom visuals require AppSource installation in PBI Desktop |
| **Gantt Bar / Lollipop** | ✅ `ganttChart` (custom visual GUID) | Custom visual; time-axis semantics preserved |
| **Butterfly Chart / Waffle** | `hundredPercentStackedBarChart` | ✅ IMPROVED — approximation note suggests negating one measure to simulate symmetry |
| **Calendar Heat Map** | `matrix` | ✅ IMPROVED — auto-enables conditional formatting properties + migration note |
| **Packed Bubble / Strip Plot** | `scatterChart` | ✅ FIXED — size encoding from `mark_encoding` auto-injected into Size data role |
| **Bump Chart / Slope / Sparkline** | `lineChart` | Ranking semantics of bump charts are lost |
| **Motion chart (animated)** | Not handled | No PBI equivalent for play-axis animation |
| **Violin plot** | ✅ `boxAndWhisker` + custom visual (`ViolinPlot1.0.0`) | Maps to Box & Whisker; AppSource custom visual GUID available |
| **Parallel coordinates** | ✅ `lineChart` + custom visual (`ParallelCoordinates1.0.0`) | Maps to Line Chart; AppSource custom visual GUID available |
| **Small multiples (Tableau grid)** | ✅ IMPLEMENTED | `_build_small_multiples_config()` auto-detects and generates PBI Small Multiples |

### What is APPROXIMATED
- **Conditional formatting migration**: Quantitative color scales (gradient) are migrated with multi-stop support (2-color and 3-color gradients). ✅ **Discrete/stepped color scales** now implemented with sorted thresholds and `LessThanOrEqual`/`GreaterThan` operators. Shape-based formatting and custom color palettes per value are not replicated
- **Dual axis**: Both axes mapped to one combo chart with proper ColumnY/LineY roles; axis sync is detected and applied. Complex independent axis scale configurations may require manual adjustment
- **Reference lines**: ✅ **Constant AND dynamic reference lines** (average/median/percentile/min/max) are migrated. Distribution and trend-line reference lines are approximated
- **Tooltips**: Viz-in-tooltip creates separate tooltip pages and **binds them** to the parent visual via tooltip_page_map — functional but may need layout adjustments in PBI Desktop

---

## 5. DAX Conversion Gaps

### What IS implemented
- **~180+ function mappings** via pre-compiled regex and dedicated converters (ISNULL→ISBLANK, ZN→IF(ISBLANK), COUNTD→DISTINCTCOUNT, etc.)
- **30+ dedicated converters** for complex functions (DATEDIFF arg reorder, LOD→CALCULATE, RANK→RANKX, PREVIOUS_VALUE→OFFSET, LOOKUP→OFFSET, RUNNING_*→CALCULATE+FILTER(ALLSELECTED), TOTAL→CALCULATE+ALL, etc.)
- **`_extract_balanced_call()`**: Balanced-parenthesis extraction utility for handling nested function calls in ZN, IFNULL, and other wrappers
- **Operator conversion**: `==`→`=`, `!=`→`<>`, `or`→`||`, `and`→`&&`, `+`→`&` (string concat)
- **Structure conversion**: CASE/WHEN→SWITCH, IF/THEN/ELSEIF→nested IF
- **Column resolution**: `[col]`→`'Table'[col]`, cross-table `RELATED()`, `LOOKUPVALUE()` for M2M
- **AGG(IF)→AGGX**: SUM(IF())→SUMX, AVERAGE(IF())→AVERAGEX, etc.
- **AGG(expr)→AGGX**: SUM(a*b)→SUMX('T', a*b); also STDEV.S→STDEVX.S, MEDIAN→MEDIANX
- **Date literals**: `#YYYY-MM-DD#`→`DATE(Y, M, D)`
- **Security functions**: USERNAME()→USERPRINCIPALNAME(), FULLNAME()→USERPRINCIPALNAME()
- **`compute_using` (partition_fields)**: Backward-compatible parameter supporting ALLEXCEPT per-dimension partitioning with `column_table_map` resolution
- **`generate_combined_field_dax()`**: Utility for creating combined/concatenated field DAX expressions
- **PREVIOUS_VALUE(seed)**: Converted to OFFSET-based DAX pattern
- **LOOKUP(expr, offset)**: Converted to OFFSET-based DAX pattern
- **RUNNING_SUM/AVG/COUNT/MAX/MIN**: Converted to CALCULATE+FILTER(ALLSELECTED) pattern
- **TOTAL(expr)**: Converted to CALCULATE(expr, ALL('table')) pattern

### What is MISSING (no DAX equivalent)

| Tableau Function | Current Output | Issue |
|-----------------|----------------|-------|
| **MAKEPOINT, MAKELINE, DISTANCE, BUFFER, AREA, INTERSECTION** | `0` placeholder + comment | No spatial functions in DAX |
| **HEXBINX, HEXBINY** | `0` + comment | No hex-binning in DAX |
| **COLLECT** | `0` + comment | No spatial collection |
| **SCRIPT_BOOL/INT/REAL/STR** | ✅ `scriptVisual` (Python/R) + `BLANK()` DAX fallback | R/Python scripting → PBI Python/R visual containers with script text and input columns; BLANK() DAX measure for non-visual contexts |
| **SPLIT** | `BLANK()` + comment | No string split to array in DAX |
| **PREVIOUS_VALUE** | OFFSET-based DAX | ✅ IMPLEMENTED — uses OFFSET pattern for iterative seed-based calculations |
| **LOOKUP** | OFFSET-based DAX | ✅ IMPLEMENTED — uses OFFSET pattern for row-relative lookups |

### What is APPROXIMATED

| Tableau Function | DAX Output | Accuracy |
|-----------------|------------|----------|
| **REGEXP_MATCH** | Smart pattern detection: `LEFT`/`RIGHT`/`CONTAINSSTRING` | ✅ IMPROVED — Handles `^literal`, `literal$`, `pat1\|pat2`, simple substrings |
| **REGEXP_REPLACE** | Chained `SUBSTITUTE()` for common patterns | ✅ IMPROVED — character class expansion, dot→any via `CONTAINSSTRING`+`SUBSTITUTE` |
| **REGEXP_EXTRACT / REGEXP_EXTRACT_NTH** | `MID(field, SEARCH("prefix", field) + len, LEN(field))` | ✅ IMPROVED — fixed-prefix capture patterns converted; complex falls back to BLANK() |
| **CORR, COVAR, COVARP** | VAR/iterator DAX patterns | ✅ IMPLEMENTED — Pearson correlation formula with SUMX/VAR, proper N vs N-1 divisor |
| **RANK_PERCENTILE** | `DIVIDE(RANKX()-1, COUNTROWS()-1)` | Approximate — edge cases with ties |
| **RANK_MODIFIED** | `RANKX(..., ASC, SKIP)` | ✅ FIXED — uses SKIP parameter for modified competition ranking |
| **INDEX()** | `RANKX()` | Row number vs rank — different semantics |
| **SIZE()** | `COUNTROWS(ALLSELECTED())` | ✅ FIXED — simplified to COUNTROWS(ALLSELECTED()) for partition-aware row count |
| **RUNNING_SUM/AVG/COUNT** | `CALCULATE(AGG, FILTER(ALLSELECTED(...)))` | ✅ IMPROVED — now uses FILTER(ALLSELECTED) pattern with proper window semantics; supports partition fields via `compute_using` with ALLEXCEPT |
| **WINDOW_SUM/AVG/MAX/MIN** | `CALCULATE(inner, ALL/ALLEXCEPT('table'))` with OFFSET frame boundaries | ✅ IMPROVED — frame start/end positions generate OFFSET-based patterns; supports ALLEXCEPT with partition fields |
| **WINDOW_CORR/COVAR/COVARP** | VAR/iterator DAX patterns | ✅ IMPLEMENTED — proper VAR/SUMX patterns with CALCULATE windowing context (v5.3.0) |
| **ATTR()** | `SELECTEDVALUE()` | ✅ FIXED — Returns scalar value; empty string if multiple values |
| **LTRIM/RTRIM** | `TRIM()` | DAX TRIM removes all leading/trailing spaces, not just left/right |
| **ATAN2** | `ATAN2()` | Quadrant handling note — DAX ATAN2 uses (y,x) not (x,y) |
| **LOD with no dimensions** | `CALCULATE(AGG(...))` | ✅ FIXED — Uses balanced brace matching (depth counter) instead of global `}` → `)` replacement |
| **LOOKUP** | OFFSET-based DAX | ✅ IMPLEMENTED — handles offset parameter via OFFSET pattern |
| **String `+` → `&`** | All expression depths | ✅ FIXED — Converted at all nesting levels since v4.0 |

---

## 6. M Query Gaps

### What IS implemented
- **33 connector types**: Excel, SQL Server, PostgreSQL, CSV, BigQuery, MySQL, Oracle, Snowflake, GeoJSON, Teradata, SAP HANA, SAP BW, Amazon Redshift, Databricks, Spark SQL, Azure SQL, Azure Synapse, Google Sheets, SharePoint, JSON, XML, PDF, Salesforce, Web, Custom SQL, **OData**, **Google Analytics**, **Azure Blob Storage**, **ADLS (Azure Data Lake)**, **Vertica**, **Impala**, **Hadoop Hive (+ HDInsight)**, **Presto (+ Trino)**
- **30+ transform functions**: rename, remove/select columns, duplicate, reorder, split, merge, replace value/nulls, trim/clean/upper/lower/proper, fill up/down, filter (values/exclude/range/nulls/contains), distinct, top_n, aggregate (sum/avg/count/countd/min/max/median/stdev), unpivot/pivot, join (inner/left/right/full/leftanti/rightanti), union, wildcard_union, sort, transpose, add_index, skip_rows, remove_last/errors, promote/demote headers, add_column, conditional_column
- **Column rename injection**: TWB-embedded column captions auto-detected and injected as M rename steps
- **`inject_m_steps()` chaining**: Composable step injection with `{prev}` placeholder

### What is MISSING or INCOMPLETE

| Gap | Details |
|-----|---------|
| **OAuth / SSO connector auth** | ✅ IMPLEMENTED — `gateway_config.py` generates OAuth redirect templates and data gateway connection references |
| **Data gateway references** | ✅ IMPLEMENTED — Gateway connection config generated in v5.0 |
| **Incremental refresh** | ✅ IMPLEMENTED — `refreshPolicy` section in TMDL table partitions |
| **Query folding hints** | ✅ IMPLEMENTED — `m_transform_buffer()` + `m_transform_join(buffer_right=True)` for `Table.Buffer()` folding boundaries |
| **Parameterized data sources** | ✅ IMPLEMENTED — `_write_expressions_tmdl()` generates `ServerName`/`DatabaseName` M parameters |
| **Tableau Hyper extract data** | ✅ IMPLEMENTED — `hyper_reader.py` reads `.hyper` files via SQLite interface; row data injected into M `#table()` expressions |
| **Google Sheets authentication** | M query generated but no OAuth2 credential setup |
| **PDF connector** | Produces `Pdf.Tables(File.Contents(...))` — may need page/table index parameters |
| **Salesforce connector** | Basic `Salesforce.Data()` — may need object/API version specification |
| **Custom SQL with parameters** | ✅ IMPLEMENTED — `Value.NativeQuery()` with parameter record binding and `[EnableFolding=true]` |
| **Error handling in M steps** | ✅ IMPLEMENTED — `wrap_source_with_try_otherwise()` wired into `tmdl_generator.generate_table_bim()` after `inject_m_steps` |
| **Data type detection from Tableau metadata** | Type columns rely on Tableau's `datatype` attribute; complex types (duration, geographic) may mis-map |

### What is APPROXIMATED
- **`_gen_m_fallback`**: Unknown connection types generate `#table(columns, {})` with a `// TODO` comment — valid M but no data
- **BigQuery project/dataset**: Uses `GoogleBigQuery.Database([BillingProject=...])` — project ID must be manually corrected
- **Oracle connection**: Uses `Oracle.Database(server, [HierarchicalNavigation=true, Query=...])` — TNS vs Easy Connect format may need adjustment
- **SAP HANA / SAP BW**: Basic `SapHana.Database()` / `SapBusinessWarehouse.Cubes()` — MDX query not fully translated, may need manual tuning

---

## 7. Deployment & CI/CD Gaps

### What IS implemented
- **5-stage CI/CD pipeline** (`.github/workflows/ci.yml`):
  1. **Lint**: `flake8` + `ruff` on ubuntu-latest
  2. **Test**: `unittest discover` on Python 3.9–3.12
  3. **Validate**: Migrate all sample `.twb` AND `.twbx` files, **strict validation** (fail on ANY failure)
  4. **Deploy (staging)**: Auto-deploy on `develop` branch push to staging environment
  5. **Deploy (production)**: Manual trigger on `main` push, production environment with secrets
- **pip caching**: `actions/cache@v4` for pip packages across CI jobs
- **Matrix testing**: Python 3.9, 3.10, 3.11, 3.12
- **Fabric deployment**: `FabricDeployer.deploy_artifacts_batch()` with `DeploymentReport`
- **Auth**: Service Principal + Managed Identity from GitHub Secrets
- **Retry strategy**: Configurable retry attempts + delay in `FabricClient`

### What is MISSING or INCOMPLETE

| Gap | Details |
|-----|---------|
| **No staging deployment** | ✅ IMPLEMENTED — `deploy-staging` job on `develop` branch push |
| **No artifact caching** | ✅ IMPLEMENTED — `actions/cache@v4` for pip packages |
| **No code coverage reporting** | ✅ IMPLEMENTED — `.coveragerc` with 80% threshold, `coverage run` in CI |
| **No integration tests** | ✅ PARTIALLY — `test_fabric_integration.py` + `test_pbi_service.py` added (opt-in `@pytest.mark.integration`) |
| **No rollback mechanism** | ✅ IMPLEMENTED — `--rollback` flag backs up previous output before overwriting |
| **No PBIR schema validation** | ✅ IMPLEMENTED — `validate_pbir_structure()` checks required/optional keys and `$schema` URLs |
| **No `.twbx` sample in CI** | ✅ IMPLEMENTED — CI validate step processes both `.twb` and `.twbx` files |
| **No linting beyond flake8 basics** | ✅ PARTIALLY ADDRESSED — `ruff` linter added alongside flake8 in lint stage |
| **No release automation** | ✅ PARTIALLY — `scripts/version_bump.py` handles versioning; PyPI packaging via `pyproject.toml` |
| **Validate step uses `\|\| true`** | ✅ FIXED — Strict validation mode fails the build on ANY migration failure |
| **No Windows CI** | All CI runs on `ubuntu-latest`; Windows path handling (backslashes, OneDrive locks) is untested |
| **No PR preview / diff report** | No migration diff or report generated on PRs for review |

---

## 8. Documentation Gaps

### What IS implemented
- **7 docs files + 6 new docs**: FAQ.md, MAPPING_REFERENCE.md, POWERBI_PROJECT_GUIDE.md, README.md (docs), TABLEAU_PREP_TO_POWERQUERY_REFERENCE.md, TABLEAU_TO_DAX_REFERENCE.md, TABLEAU_TO_POWERQUERY_REFERENCE.md, ARCHITECTURE.md, KNOWN_LIMITATIONS.md, MIGRATION_CHECKLIST.md, DEPLOYMENT_GUIDE.md, TABLEAU_VERSION_COMPATIBILITY.md
- **Copilot instructions**: Comprehensive `.github/copilot-instructions.md` with architecture, object types, visual mappings, DAX conversions, M transforms, PBIR schemas, development rules
- **CHANGELOG.md**: Release history
- **Module READMEs**: tableau_export/README.md, powerbi_import/README.md, conversion/README.md, tests/README.md, artifacts/README.md

### What is MISSING or INCOMPLETE

| Gap | Details |
|-----|---------|
| **No API documentation** | No auto-generated API docs (sphinx/pdoc) for any module |
| **No architecture diagram** | ✅ IMPLEMENTED — `docs/ARCHITECTURE.md` with Mermaid pipeline diagram and module descriptions |
| **No known limitations page** | ✅ IMPLEMENTED — `docs/KNOWN_LIMITATIONS.md` comprehensive user-facing limitations reference |
| **No migration checklist** | ✅ IMPLEMENTED — `docs/MIGRATION_CHECKLIST.md` 10-section post-migration validation checklist |
| **No Tableau version compatibility matrix** | ✅ IMPLEMENTED — `docs/TABLEAU_VERSION_COMPATIBILITY.md` version support matrix |
| **No deployment guide** | ✅ IMPLEMENTED — `docs/DEPLOYMENT_GUIDE.md` Fabric REST API deployment guide |
| **No contribution guide** | ✅ IMPLEMENTED — `CONTRIBUTING.md` with dev setup, coding standards, testing, contribution workflow |
| **`conversion/` legacy folder not documented** | `conversion/` contains old per-object converters that are "not used in the current pipeline" but still present — no deprecation notice |

---

## 9. Config & Settings Gaps

### What IS implemented
- **Environment variables**: 11 settings via `os.getenv()` (FABRIC_WORKSPACE_ID, API_BASE_URL, TENANT_ID, CLIENT_ID, CLIENT_SECRET, USE_MANAGED_IDENTITY, LOG_LEVEL, LOG_FORMAT, DEPLOYMENT_TIMEOUT, RETRY_ATTEMPTS, RETRY_DELAY)
- **Pydantic fallback**: Optional `pydantic-settings` for typed config with `.env` file support; falls back to `_FallbackSettings` (stdlib only)
- **Environment configs** (`environments.py`): Development/staging/production with different timeouts, retries, log levels, approval requirements
- **Singleton pattern**: `get_settings()` returns cached instance
- **Structured logging** (`migrate.py`): `setup_logging()` with verbose/file options
- **CLI arguments**: `--output-dir`, `--verbose`, `--quiet`, `--batch`, `--prep`, `--no-pbip`, `--config`, `--dry-run`

### What is MISSING or INCOMPLETE

| Gap | Details |
|-----|---------|
| **No config file support** | ✅ IMPLEMENTED — `--config config.json` CLI flag with `config.example.json` template |
| **No output format selection** | ✅ IMPLEMENTED — `--output-format` CLI flag (pbip/tmdl/pbir) |
| **No source path parameterization** | ✅ IMPLEMENTED — `source_dir` parameter allows configurable JSON source directory |
| **No calendar table customization** | ✅ IMPLEMENTED — `--calendar-start`/`--calendar-end` CLI flags (default 2020–2030) |
| **No locale/culture override** | ✅ IMPLEMENTED — `--culture LOCALE` CLI flag for non-en-US linguistic metadata |
| **No connection string templating** | ✅ IMPLEMENTED — `apply_connection_template()` replaces `${ENV.*}` placeholders in M queries |
| **No `.env.example` file** | ✅ IMPLEMENTED — `.env.example` and `config.example.json` templates provided |
| **No validation of settings values** | ✅ IMPLEMENTED — `_FallbackSettings` validates LOG_LEVEL, RETRY_ATTEMPTS, DEPLOYMENT_TIMEOUT |
| **No dry-run mode** | ✅ IMPLEMENTED — `--dry-run` CLI flag previews migration without writing files |
| **`DEPLOYMENT_TIMEOUT` and `RETRY_DELAY` are int-only** | ✅ CLOSED — Sprint 31 added fractional (float) timeout support |

---

## Summary Priority Matrix

| Area | Implemented | Missing/Incomplete | Approximated | Priority |
|------|------------|-------------------|-------------|----------|
| **Extraction** | 20 object types (+4), 10+ connectors, 22 new methods, annotations, layout containers, device layouts, formatting depth, legend, axes, sort depth, **datasource filters**, **reference bands/distributions**, **number formatting**, **custom shapes/fonts/geocoding/hyper metadata**, **dynamic zone visibility**, **clustering/forecasting/trend lines**, **Hyper data loading** (sqlite3), **Tableau 2024.3+ dynamic params**, **Pulse metric extraction** | Composite connectors | Prep VAR/VARP, layout nesting depth | Low |
| **TMDL Generation** | 14 phases, full model, date hierarchy, quick table calcs, partition addressing, **semantic validation**, **calendar customization**, **culture config**, **M-based calc columns** (DAX→M converter), **calculation groups**, **field parameters**, **multi-language cultures** (`--languages`), **Goals/Scorecard** (`--goals`), **dynamic parameter M partitions** | Incremental, composite model | — | Low |
| **PBIR Generation** | 60+ visuals, filters, themes, mobile layout, tooltip binding, action buttons, conditional formatting, axis config, legend, sort state, table formatting, padding, **drill-through pages**, **slicer type variety**, **pages shelf**, **number format conversion**, **SCRIPT_* → Python/R script visuals** | Small Multiples | Position scaling | Low |
| **DAX Conversion** | ~180+ patterns, ALLEXCEPT for partitioned calcs, **CORR/COVAR/COVARP**, **ATTR→SELECTEDVALUE**, **LOD balanced braces**, **PREVIOUS_VALUE→OFFSET**, **LOOKUP→OFFSET**, **RUNNING_*→CALCULATE+FILTER(ALLSELECTED)**, **TOTAL→CALCULATE+ALL**, **SCRIPT_* → scriptVisual** | Spatial (6), SPLIT | REGEX (4), WINDOW_* frames | Medium |
| **M Query** | **33 connectors** (+8: OData, Google Analytics, Azure Blob/ADLS, Vertica, Impala, Hadoop Hive, Presto), 30+ transforms, **DAX-to-M expression converter** (calc columns as M steps), **Hyper data → M #table()** | OAuth, gateway, incremental refresh | Fallback #table, BigQuery/Oracle config | Low |
| **Prep Flow** | DAG traversal, 20+ action types, **ExtractValues**, **CustomCalculation**, **Script/Prediction/CrossJoin/PublishedDataSource** handlers, 5 new connection mappings, **Hyper data loading** | — | Prep VAR/VARP joins | Low |
| **Pre-Migration** | **Assessment** (8-category scoring: datasource/calculation/visual/filter/data model/interactivity/extract/scope), **Strategy advisor** (Import/DirectQuery/Composite), JSON report export | — | — | Low |
| **Test Coverage** | **3,342 tests across 60 files** (+conftest.py shared fixtures), 93.08% coverage | Perf tests, integration tests | — | Low |
| **CI/CD** | **5-stage pipeline** (lint+ruff, test, **strict validate+twbx**, **staging deploy**, production deploy), **pip caching**, **PBIR schema forward-compat check** (`--check-schema`), **PyPI auto-publish workflow** (`publish.yml`), **plugin system** (`plugins.py` + `examples/plugins/`) | Coverage reporting, Windows CI | — | Low |
| **Documentation** | **13 docs** + copilot instructions (ARCHITECTURE, KNOWN_LIMITATIONS, MIGRATION_CHECKLIST, DEPLOYMENT_GUIDE, TABLEAU_VERSION_COMPATIBILITY, CONTRIBUTING) | API docs | — | Low |
| **Config** | 11 env vars, 3 environments, **settings validation**, **dry-run**, **calendar/culture CLI**, **.env.example** | Config file, connection templating | — | Low |

---

## 10. Cross-Project Gap Analysis — TableauToFabric vs TableauToPowerBI

**Date:** 2026-03-07

### Architecture Differences

| Aspect | TableauToFabric | TableauToPowerBI |
|--------|----------------|------------------|
| **Storage mode** | DirectLake (compatibility 1604) | Import (compatibility 1550) |
| **Output artifacts** | 6: Lakehouse, Dataflow Gen2, Notebook, Pipeline, Semantic Model, PBI Report | 1: .pbip project (PBIR + TMDL) |
| **External dependencies** | `python-dateutil`, `azure-identity`, `requests`, `pydantic-settings`, `tableauserverclient` | None (stdlib only, optional azure-identity/requests) |
| **Extraction layer** | Shared (`tableau_export/`) — PBI is a **strict superset** (5 extra functions) | PBI has extra: `_infer_automatic_chart_type`, `_is_date`, `_is_measure`, `_strip_brackets`, `extract_layout_containers`, `_build_from_dispatch`, `_build_corr_covar_dax`, `_transform_func_call`, `_gen_m_schema_item`, `_m_text_transform` |

### Source File Comparison

| File | Fabric Lines | PBI Lines | PBI Delta | Notes |
|------|-------------|-----------|-----------|-------|
| `extract_tableau_data.py` | 2,263 | 2,403 | **+140** | PBI adds auto chart type inference, layout containers |
| `datasource_extractor.py` | 649 | 651 | **+2** | Near-identical |
| `dax_converter.py` | 1,676 | 1,259 | **-417** | PBI refactored into shared helpers (DRY) |
| `m_query_builder.py` | 1,165 | 865 | **-300** | PBI refactored into shared helpers (DRY) |
| `prep_flow_parser.py` | 1,106 | 945 | **-161** | Near-equivalent (minor refactoring) |
| `pbip_generator.py` | 1,842 | 2,326 | **+484** | PBI adds drill-through, slicer modes, bookmarks, pages shelf, number format |
| `tmdl_generator.py` | 2,280 | 2,741 | **+461** | PBI adds M-based calc columns, M transform steps, quick table calcs |
| `visual_generator.py` | 1,086 | 938 | **-148** | Near-equivalent; Fabric has `_make_column_proj()` |
| `validator.py` | 583 | 502 | **-81** | Fabric has notebook/lakehouse/dataflow/pipeline validators |
| `assessment.py` | 1,051 | 912 | **-139** | Near-identical (same 8 categories + scoring) |
| `strategy_advisor.py` | 348 | 334 | **-14** | Different focus: Fabric→ETL strategy, PBI→connection mode |

### Fabric-Only Components (not applicable to PBI)

| Component | Purpose | Portability |
|-----------|---------|-------------|
| `fabric_import/lakehouse_generator.py` (223 lines) | Lakehouse DDL + table metadata | Not applicable — PBI uses Import mode |
| `fabric_import/dataflow_generator.py` (304 lines) | Dataflow Gen2 M queries | Not applicable — PBI uses M query partitions in TMDL |
| `fabric_import/notebook_generator.py` (545 lines) | PySpark Notebook (.ipynb) for ETL | Not applicable — PBI has no notebook concept |
| `fabric_import/pipeline_generator.py` (229 lines) | Fabric Pipeline definitions | Not applicable — PBI uses Power BI Service refresh |
| `fabric_import/semantic_model_generator.py` (116 lines) | DirectLake semantic model wrapper | Not applicable — PBI creates TMDL directly |
| `fabric_import/calc_column_utils.py` (182 lines) | Calc column classification + M/PySpark | ✅ Superseded — PBI has `_dax_to_m_expression()` inline (more complete) |
| `fabric_import/constants.py` (130 lines) | Shared constants, GUIDs, Spark types | PBI inlines these — not needed |
| `fabric_import/naming.py` (108 lines) | Name sanitization | PBI uses `_clean_field_name` inline |
| `conversion/` (8 modules) | Per-object converters (intermediate) | Not needed — PBI converts directly from extraction JSON |
| `scripts/` (8 files) | PowerShell deployment scripts | Fabric-specific |

### Shared File Divergences (Output Generators)

#### `pbip_generator.py` (Fabric: 1,842 lines vs PBI: 2,326 lines)

| Feature | Fabric | PBI |
|---------|--------|-----|
| Slicer mode detection | Always Dropdown | ✅ PBI: `_detect_slicer_mode()` — Dropdown/List/Between/Basic |
| Bookmark creation | Inline in `create_report_structure` | ✅ PBI: Standalone `_create_bookmarks()` method |
| Report filters | From workbook-scope filters | ✅ PBI: Global + datasource filters promoted to report-level `filterConfig` |
| Drill-through pages | Not implemented | ✅ PBI: `_create_drillthrough_pages()` |
| Action buttons | `_create_visual_nav_button` + `_create_visual_action_button` | ✅ PBI: `_create_action_visuals()` (unified) |
| Pages shelf slicer | `_create_pages_shelf_slicer()` | ✅ PBI: `_create_pages_shelf_slicer()` |
| Number format conversion | `_convert_number_format()` | ✅ PBI: `_convert_number_format()` |
| Scatter axis projections | Not implemented | ✅ PBI: `_make_scatter_axis_projection()` + `_make_scatter_axis_entry()` |
| Visual object config | Trend lines, forecasting, map options, stepped colors, data bars, small multiples, analytics stats | Legend title/font-size, axis config (range/log/reversed), dual-axis combo, table/matrix grid, gradient min/mid/max |

#### `tmdl_generator.py` (Fabric: 2,280 lines vs PBI: 2,741 lines)

| Feature | Fabric | PBI |
|---------|--------|-----|
| Table partitions | DirectLake entity partitions | ✅ PBI: M query Import partitions |
| Date hierarchies | `_auto_date_hierarchies()` — auto Year>Quarter>Month>Day | ✅ PBI: M-based date hierarchies via `_dax_to_m_expression()` |
| Calculation groups | `_create_calculation_groups()` from param swap actions | ✅ PBI: `_create_calculation_groups()` (ported) |
| Field parameters | `_create_field_parameters()` with NAMEOF | ✅ PBI: `_create_field_parameters()` (ported) |
| **M-based calc columns** | Not applicable (DirectLake) | ✅ PBI: `_dax_to_m_expression()` converts DAX → M `Table.AddColumn` steps |
| **M step injection** | Not applicable | ✅ PBI: `_inject_m_steps_into_partition()` + `_build_m_transform_steps()` |
| Quick table calcs | Not implemented | ✅ PBI: `_create_quick_table_calc_measures()` |
| Column writing | Monolithic `_write_column` | ✅ PBI: `_write_column_properties()` + `_write_column_flags()` (refactored) |

#### `visual_generator.py` (Fabric: 1,086 lines vs PBI: 938 lines)

| Difference | Fabric | PBI |
|-----------|--------|-----|
| Sankey/Chord mapping | `sankeyChart`/`chordChart` (custom visuals) | `decompositionTree` (fallback) |
| Custom visual GUIDs | Defines `CUSTOM_VISUAL_GUIDS` dict | ✅ IMPLEMENTED — `resolve_custom_visual_type()` wired into `_create_visual_worksheet()` with `customVisualsRepository` in report.json |
| `_make_column_proj()` | Extra helper function | Not present (inlined) |

#### `strategy_advisor.py` (Fabric: 348 lines vs PBI: 334 lines)

| Difference | Fabric | PBI |
|-----------|--------|-----|
| Recommendation focus | ETL strategy (Dataflow/Notebook/Pipeline) | ✅ PBI: Connection mode (Import/DirectQuery/Composite) |
| `artifacts` property | Lists Fabric artifacts to produce | Not applicable |
| `recommend_etl_strategy()` | Fabric-specific ETL recommendation | Not applicable |
| `_classify_calculations()` | Not present | ✅ PBI: Classifies calcs by portability |
| `connection_mode` property | Not present | ✅ PBI: Returns recommended connection mode |

### Test Coverage Gap

| Metric | Fabric | PBI |
|--------|--------|-----|
| Test files | 40 | 37 (+conftest.py) |
| Total tests | ~1,205 | **1,889** |
| Coverage test files (Fabric-style) | 9 files, ~750 tests (e.g., `test_*_coverage.py`) | None |
| PBI-only broad-scope tests | None | 5 files (feature_gaps, gap_implementations, new_features, non_regression, migration_validation) |
| **Coverage ratio** | ~0.64× PBI test count | Baseline (PBI now has more tests than Fabric) |

### Portability Assessment — Remaining Items

| Item | Effort | Value | Status |
|------|--------|-------|--------|
| `assessment.py` (pre-migration assessment) | Medium | High | ✅ **Ported** — `powerbi_import/assessment.py` (912 lines) |
| `strategy_advisor.py` (migration strategy) | Medium | Medium | ✅ **Ported** — `powerbi_import/strategy_advisor.py` (334 lines, adapted for PBI) |
| `calc_column_utils.py` (calc classification) | Low | Medium | ✅ **Superseded** — `_dax_to_m_expression()` is more complete |
| Pages shelf slicer | Low | Low | ✅ **Ported** — `_create_pages_shelf_slicer()` |
| Number format conversion | Low | Medium | ✅ **Ported** — `_convert_number_format()` |
| Calculation groups | Medium | Medium | ✅ **Ported** — `_create_calculation_groups()` |
| Field parameters | Medium | Medium | ✅ **Ported** — `_create_field_parameters()` |
| Auto date hierarchies | Low | Medium | ✅ **Ported** — M-based date hierarchies |
| `conftest.py` (shared test fixtures) | Low | High | ✅ **Ported** — `tests/conftest.py` (132 lines) |
| `conversion/` (8 modular converters) | High | Medium | Skip — PBI converts directly from extraction JSON |
| `constants.py` + `naming.py` (shared utilities) | Low | Low | Skip — PBI inlines these |
| Fabric coverage tests (750 tests) | Medium | High | Consider — would significantly boost coverage |
| Context filter promotion | Low | Medium | ✅ **Implemented** — context filters promoted to page-level; global/datasource filters promoted to report-level |
