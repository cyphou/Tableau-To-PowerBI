# Comprehensive Gap Analysis — Tableau to Power BI Migration Tool

**Date:** 2026-03-06 — updated after Fabric feature port + cross-project gap analysis  
**Scope:** Every source file, test file, CI/CD, docs, config, and cross-project comparison with TableauToFabric  
**Status:** 732 tests passing (2 skipped)

### Implementation Coverage

```
 EXTRACTION          GENERATION         INFRA / CI         DOCUMENTATION
+----------------+  +----------------+  +----------------+  +----------------+
| 20 object types|  | PBIR v4.0      |  | 5-stage CI/CD  |  | 13 doc files   |
| .twb/.twbx/.tfl|  | TMDL semantic  |  | 732 tests      |  | DAX reference  |
| 180+ DAX conv  |  | 60+ visuals    |  | Artifact valid |  | M query ref    |
| 33 connectors  |  | Drill-through  |  | Fabric deploy  |  | Prep ref       |
| 40+ transforms |  | Slicer modes   |  | Env configs    |  | Architecture   |
| Prep flow DAG  |  | Cond. format   |  | Settings valid |  | Gap analysis   |
| Ref lines/bands|  | RLS roles      |  | --dry-run      |  | Migration guide|
| Datasrc filters|  | Calendar/culture|  | --culture      |  | FAQ + more     |
| 22 new methods |  | Quick table cal|  |                |  |                |
+-------+--------+  +-------+--------+  +-------+--------+  +-------+--------+
        |                    |                    |                    |
        +--------------------+--------------------+--------------------+
                                     |
                              ALL IMPLEMENTED
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
- **Tableau Server/Cloud connection types**: No support for Tableau Server live connections or Extract (.hyper) reconnection — only reads the XML metadata
- **`.hyper` file parsing**: Prep `LoadHyper` emits an empty `#table` — Hyper file data is not read (metadata extraction added but not data)
- **Tableau extensions/LOD filters**: LOD calc extraction relies on text-based `{FIXED ...}` parsing (can miss edge cases with nested LODs or LOD inside LOD)
- **Dashboard layout containers**: Layout containers are extracted but deeply nested containers may lose relative positioning when mapped to PBI
- **Tableau 2024.3+ features**: Dynamic parameters with database queries not fully extracted
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
- **12-phase TMDL model** (`tmdl_generator.py`, 2220 lines):
  1. Table deduplication
  2. Main table identification, column metadata, DAX context
  3. Tables with columns, M queries, measures, calculated columns
  4. Relationships (cross-datasource dedup, validation, type mismatch fixing)
  5. Sets/groups/bins as calculated columns
  6. Auto date table (M partition, not DAX calculated) **with Date Hierarchy** (Year → Quarter → Month → Day)
  7. Hierarchies from drill-paths
  8. What-If parameter tables (range → `GENERATESERIES`, list → `DATATABLE`, any → measure)
  9. RLS roles (user filter → USERPRINCIPALNAME, USERNAME/FULLNAME → DAX, ISMEMBEROF → per-group role)
  9b. Quick table calc measures (pcto → DIVIDE, running_sum → CALCULATE, rank → RANKX)
  10. Infer missing relationships from cross-table DAX refs
  10b. Cardinality detection (manyToOne vs manyToMany based on join type + column ratio)
  10c. RELATED() → LOOKUPVALUE() conversion for manyToMany
  11. Deactivate ambiguous relationship paths (Union-Find cycle detection)
  12. Auto-generate perspectives
- **TMDL file writers**: database.tmdl, model.tmdl, relationships.tmdl, expressions.tmdl, roles.tmdl, tables/*.tmdl, perspectives.tmdl, cultures/*.tmdl, diagramLayout.json
- **Visual generation** (`visual_generator.py`, 939 lines): 60+ visual type mappings, 30+ PBIR config templates, data role definitions for 30+ types, queryState builder, slicer sync groups, cross-filtering disable, action button navigation (page + URL), TopN/categorical visual-level filters, sort state, reference lines, **axis config** (range min/max, log scale, reversed)
- **PBIP generator** (`pbip_generator.py`, 1801 lines): Dashboard → pages, worksheet → visuals, text → textbox, image → image, filter_control → slicer, tooltip pages **with binding to parent visuals** (tooltip_page_map), bookmarks from stories, theme generation, **action button visuals** (URL WebUrl + sheet-navigate PageNavigation)
- **Power Query M generation** (`m_query_builder.py` in extraction layer): 25 connector types + 30+ transform functions
- **Theme migration**: Tableau dashboard color palettes → PBI theme JSON (`RegisteredResources/TableauMigrationTheme.json`)
- **Conditional formatting**: Quantitative color encoding → PBI dataPoint gradient rules with **multi-stop support** (2-color min/max, 3+ color min/mid/max), proper `inputRole` structure
- **Reference lines**: Tableau reference lines → PBI constant lines on valueAxis
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
- **No incremental migration**: Re-running the migration for the same workbook regenerates everything from scratch; no diffing or merging with existing .pbip projects
- **No multi-language report support**: Single-culture output only (model.tmdl culture ref)
- **No data bar / sparkline visuals**: These PBI visual types have no Tableau equivalent and are not generated
- **No drill-through pages**: ✅ IMPLEMENTED — `_create_drillthrough_pages()` in pbip_generator.py creates pageType:"Drillthrough" pages from filter/set-value actions with drill-through filter binding
- **No paginated reports**: Only interactive .pbip reports
- **Limited calendar table customization**: ✅ IMPLEMENTED — Calendar start/end years configurable via `--calendar-start`/`--calendar-end` CLI flags and `model['_calendar_start']`/`model['_calendar_end']` (default 2020–2030); Time Intelligence measures still auto-included
- **Deployment not end-to-end tested**: `deployer.py` and `client.py` have structural tests but no integration tests against a real Fabric workspace
- **Stale file cleanup race conditions**: OneDrive lock leftovers handled via try/except but may still leave artifacts on Windows
- **`import_to_powerbi.py` loads JSON from hardcoded paths**: ✅ IMPLEMENTED — `source_dir` parameter in `PowerBIImporter.__init__()` allows configurable JSON source directory
- **No composite model support**: All tables use import mode; no DirectQuery or dual mode generation
- **No Small Multiples**: PBI small multiples feature exists but is not auto-generated from Tableau grid layouts

### What is APPROXIMATED
- **Visual positioning**: Dashboard objects are scaled proportionally from Tableau canvas to PBI page size. Not pixel-perfect; overlapping is possible
- **Slicer bindings**: ✅ IMPROVED — `_detect_slicer_mode()` auto-selects Dropdown/List/Between/Basic based on parameter domain_type and column datatype (date→Basic, numeric→Between, list→List, default→Dropdown)
- **Report filters from parameters**: Parameters are converted to measures (SELECTEDVALUE), but the report filter generated has `Categorical` type which may not match the parameter's domain
- **Textbox/Image objects**: Minimal HTML → plain text conversion; rich text formatting is lost
- **Combo chart mapping**: Dual axis charts map to `lineClusteredColumnComboChart` with proper ColumnY/LineY roles; axis scale sync is detected but complex independent axis configurations may not fully transfer

---

## 3. Test Coverage

### What IS implemented
- **667 tests across 12 test files + 50 new gap implementation tests + 15 Fabric port validation tests = 732 tests** (2 skipped):

| Test File | Tests | Coverage Focus |
|-----------|-------|----------------|
| `test_dax_converter.py` | 86 | Type mapping, bracket escape, empty inputs, simple functions, special functions, operators, structure (CASE/IF), LOD, column resolution, AGG(IF)→AGGX, table calcs, dates, references, math/stats, leakage detection, complex formulas |
| `test_m_query_builder.py` | 102 | Type mapping, M query generation for 7+ connectors, `inject_m_steps`, column/value/filter/aggregate/pivot/join/union/reshape/calculated transforms |
| `test_tmdl_generator.py` | 92 | `_quote_name`, `_tmdl_datatype`, `_tmdl_summarize`, `_safe_filename`, format strings, display folders, semantic role mapping, theme generation, `build_semantic_model` (single/multi table, measures, date table, perspectives, relationships, dedup), `_add_date_table` (sortByColumn, isKey, relationship), TMDL file writers (perspectives, culture, database, model, relationships, table, full model) |
| `test_visual_generator.py` | 65 | Visual type mapping (bar/column/line/pie/scatter/map/table/KPI/treemap/waterfall/combo/slicer/specialty/textbox/unknown), data roles, config templates, container creation, slicer sync groups, cross-filtering disable, action button navigation, visual filters (TopN/categorical), sort state, reference lines, query state builder |
| `test_pbip_generator.py` | 46 | `_clean_field_name`, `_make_visual_position`, `_is_measure_field`, `_build_visual_objects` (axes from axes_data, legend, labels, mark encoding) |
| `test_feature_gaps.py` | 44 | Reference lines, annotations, axes (basic/dual/log/reversed), legend (extraction/generation/position/title), mark labels, palette colors, dashboard padding, layout containers, device layouts, sort orders (basic/computed), combo chart roles, sort state, action buttons (URL/navigate/filter-skipped), table formatting, conditional formatting (2-color/3-color gradient), axis generation, formatting depth, padding application, quick table calc detection, table calc addressing (ALLEXCEPT), date hierarchy |
| `test_infrastructure.py` | 36 | ArtifactValidator (JSON/TMDL/project/directory), DeploymentReport, ArtifactCache, ConfigEnvironments, ConfigSettings, FabricAuthenticator, FabricClient, Deployer, MigrateCLI |
| `test_migration_report.py` | 36 | MigrationReport (pass/fail tracking, fidelity scoring, category breakdown, unsupported/approximate items, report formatting) |
| `test_extraction.py` | 29 | TableauExtractor initialization, TWB/TWBX parsing, worksheet/dashboard/datasource/calculation/parameter/filter/story/action/set/group/bin/hierarchy extraction |
| `test_prep_flow_parser.py` | 58 | Graph traversal (topological sort), step conversion (Clean/Join/Aggregate/Union/Pivot), expression conversion, merge with TWB datasources, edge cases |
| `test_migration.py` | 10 | Extraction file existence, conversion file existence, worksheets/dashboards/datasources/calculations/parameters/filters/stories conversion, data integrity |
| `test_non_regression.py` | 63 | Per-sample project tests (Superstore, HR Analytics, Financial Report, BigQuery, Enterprise Sales, Manufacturing IoT, Marketing Campaign, Security Test) + cross-sample consistency (metadata, model.tmdl, empty dirs, schema consistency) |
| `test_migration_validation.py` | 0 | Disabled — previously tested via non-regression pipeline |
| `test_gap_implementations.py` | 50 | DAX fixes (CORR/COVAR/LOD/ATTR), datasource filters, semantic validation, slicer modes, drill-through pages, number format conversion, settings validation, calendar customization, CLI args, reference bands, deployment edge cases |

### What is MISSING or INCOMPLETE
- **No mocking of file I/O**: Tests write real files to tempdir — no mocking of file system operations
- **No negative/edge-case tests for deployment**: `deployer.py` tested only for constructor/types, not for error handling, retry logic, or HTTP 429 handling
- **No performance/stress tests**: No tests for large workbooks (100+ worksheets, 1000+ calculations)
- **No test for `--batch` mode**: Batch migration is tested only via CI/CD `validate` step
- **DAX conversion coverage**: 86 tests covering common formula patterns out of 172 documented conversions. LOD with multiple dimensions, nested LODs, WINDOW_CORR/COVAR are not unit-tested
- **No property-based or fuzzy testing**: All tests are example-based; no generative testing for formula conversion robustness

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
| **Sankey / Chord / Network** | `decompositionTree` | Structurally different — decomposition tree is hierarchical, not a flow diagram |
| **Gantt Bar / Lollipop** | `clusteredBarChart` | Loses time-axis semantics; no timeline visual in standard PBI |
| **Butterfly Chart / Waffle** | `hundredPercentStackedBarChart` | Loses symmetry of butterfly layout |
| **Calendar Heat Map** | `matrix` | PBI matrix can show colors but lacks calendar grid structure |
| **Packed Bubble / Strip Plot** | `scatterChart` | Size encoding may not transfer correctly |
| **Bump Chart / Slope / Sparkline** | `lineChart` | Ranking semantics of bump charts are lost |
| **Motion chart (animated)** | Not handled | No PBI equivalent for play-axis animation |
| **Violin plot** | Not handled | No standard PBI visual |
| **Parallel coordinates** | Not handled | No standard PBI visual |
| **Small multiples (Tableau grid)** | Not handled | PBI has Small Multiples feature but it's not auto-generated |

### What is APPROXIMATED
- **Conditional formatting migration**: Quantitative color scales (gradient) are migrated with multi-stop support (2-color and 3-color gradients). Discrete/stepped color scales, shape-based formatting, and custom color palettes per value are not replicated
- **Dual axis**: Both axes mapped to one combo chart with proper ColumnY/LineY roles; axis sync is detected and applied. Complex independent axis scale configurations may require manual adjustment
- **Reference lines**: Only constant value lines are migrated; dynamic (percentile, trend, distribution) reference lines are not migrated
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
| **SCRIPT_BOOL/INT/REAL/STR** | `BLANK()` + comment | R/Python scripting has no direct DAX equivalent |
| **SPLIT** | `BLANK()` + comment | No string split to array in DAX |
| **PREVIOUS_VALUE** | OFFSET-based DAX | ✅ IMPLEMENTED — uses OFFSET pattern for iterative seed-based calculations |
| **LOOKUP** | OFFSET-based DAX | ✅ IMPLEMENTED — uses OFFSET pattern for row-relative lookups |

### What is APPROXIMATED

| Tableau Function | DAX Output | Accuracy |
|-----------------|------------|----------|
| **REGEXP_MATCH** | `CONTAINSSTRING()` | Partial — only simple substring, not true regex |
| **REGEXP_REPLACE** | `SUBSTITUTE()` | Only literal replacement, no regex groups |
| **REGEXP_EXTRACT / REGEXP_EXTRACT_NTH** | `BLANK()` | Placeholder — no DAX regex extract |
| **CORR, COVAR, COVARP** | VAR/iterator DAX patterns | ✅ IMPLEMENTED — Pearson correlation formula with SUMX/VAR, proper N vs N-1 divisor |
| **RANK_PERCENTILE** | `DIVIDE(RANKX()-1, COUNTROWS()-1)` | Approximate — edge cases with ties |
| **RANK_MODIFIED** | `RANKX()` + comment | Standard ranking, not modified competition ranking |
| **INDEX()** | `RANKX()` | Row number vs rank — different semantics |
| **SIZE()** | `COUNTROWS()` | Counts all rows, not partition size |
| **RUNNING_SUM/AVG/COUNT** | `CALCULATE(AGG, FILTER(ALLSELECTED(...)))` | ✅ IMPROVED — now uses FILTER(ALLSELECTED) pattern with proper window semantics; supports partition fields via `compute_using` with ALLEXCEPT |
| **WINDOW_SUM/AVG/MAX/MIN** | `CALCULATE(inner, ALL/ALLEXCEPT('table'))` | Loses window frame boundaries (start/end offset); supports **ALLEXCEPT with partition fields** for partitioned calculations |
| **WINDOW_CORR/COVAR/COVARP** | `0` | Full placeholder |
| **ATTR()** | `SELECTEDVALUE()` | ✅ FIXED — Returns scalar value; empty string if multiple values |
| **LTRIM/RTRIM** | `TRIM()` | DAX TRIM removes all leading/trailing spaces, not just left/right |
| **ATAN2** | `ATAN2()` | Quadrant handling note — DAX ATAN2 uses (y,x) not (x,y) |
| **LOD with no dimensions** | `CALCULATE(AGG(...))` | ✅ FIXED — Uses balanced brace matching (depth counter) instead of global `}` → `)` replacement |
| **LOOKUP** | OFFSET-based DAX | ✅ IMPLEMENTED — handles offset parameter via OFFSET pattern |
| **String `+` → `&`** | Only at depth 0 | Arithmetic `+` inside string concatenation contexts may be incorrectly preserved |

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
| **OAuth / SSO connector auth** | M queries use hardcoded connection strings; no OAuth token or SSO configuration |
| **Data gateway references** | No on-premises data gateway configuration in output |
| **Incremental refresh** | No incremental refresh policy generated |
| **Query folding hints** | No `Table.Buffer()` or `Value.NativeQuery()` optimization hints |
| **Parameterized data sources** | M queries use hardcoded server/database names; no PBI parameters for data source switching |
| **Tableau Hyper extract data** | `.hyper` files referenced in Prep flows produce empty `#table` |
| **Google Sheets authentication** | M query generated but no OAuth2 credential setup |
| **PDF connector** | Produces `Pdf.Tables(File.Contents(...))` — may need page/table index parameters |
| **Salesforce connector** | Basic `Salesforce.Data()` — may need object/API version specification |
| **Custom SQL with parameters** | Custom SQL uses `Value.NativeQuery()` but parameter binding is not supported |
| **Error handling in M steps** | No `try...otherwise` patterns for graceful error handling |
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
| **No code coverage reporting** | No `pytest-cov` or coverage badge |
| **No integration tests** | Deployment tested structurally (constructor/types) but never against a real Fabric workspace |
| **No rollback mechanism** | If deployment fails partway through a batch, there's no undo |
| **No PBIR schema validation** | Generated JSON isn't validated against Microsoft's published JSON schemas |
| **No `.twbx` sample in CI** | ✅ IMPLEMENTED — CI validate step processes both `.twb` and `.twbx` files |
| **No linting beyond flake8 basics** | ✅ PARTIALLY ADDRESSED — `ruff` linter added alongside flake8 in lint stage |
| **No release automation** | No version bumping, CHANGELOG generation, or PyPI publishing |
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
- **CLI arguments**: `--output-dir`, `--verbose`, `--batch`, `--prep`, `--no-pbip`

### What is MISSING or INCOMPLETE

| Gap | Details |
|-----|---------|
| **No config file support** | No YAML/TOML/JSON config file for project-level settings (e.g., custom visual mappings, DAX overrides) |
| **No output format selection** | Cannot choose between TMDL-only, PBIR-only, or full .pbip output |
| **No source path parameterization** | `import_to_powerbi.py` hardcodes `tableau_export/*.json` paths — not configurable |
| **No calendar table customization** | Date range (2020–2030), fiscal year start, included columns are all hardcoded |
| **No locale/culture override** | Culture defaults to `en-US` unless the Tableau model specifies otherwise — no CLI flag to override |
| **No connection string templating** | M queries embed hardcoded server/database — no config for dev/staging/prod data sources |
| **No `.env.example` file** | No template for required environment variables |
| **No validation of settings values** | `_FallbackSettings` doesn't validate (e.g., invalid LOG_LEVEL or negative RETRY_ATTEMPTS) |
| **No dry-run mode** | Cannot preview what the migration would produce without writing files |
| **`DEPLOYMENT_TIMEOUT` and `RETRY_DELAY` are int-only** | Cannot specify sub-second delays or fractional timeouts |

---

## Summary Priority Matrix

| Area | Implemented | Missing/Incomplete | Approximated | Priority |
|------|------------|-------------------|-------------|----------|
| **Extraction** | 20 object types (+4), 10+ connectors, 22 new methods, annotations, layout containers, device layouts, formatting depth, legend, axes, sort depth, **datasource filters**, **reference bands/distributions**, **number formatting**, **custom shapes/fonts/geocoding/hyper metadata**, **dynamic zone visibility**, **clustering/forecasting/trend lines** | Hyper data parsing, composite connectors | Prep VAR/VARP, layout nesting depth | Low |
| **TMDL Generation** | 12+ phases, full model, date hierarchy, quick table calcs, partition addressing, **semantic validation**, **calendar customization**, **culture config** | Incremental, composite model | — | Low |
| **PBIR Generation** | 60+ visuals, filters, themes, mobile layout, tooltip binding, action buttons, conditional formatting, axis config, legend, sort state, table formatting, padding, **drill-through pages**, **slicer type variety** | Small Multiples | Position scaling | Low |
| **DAX Conversion** | ~180+ patterns, ALLEXCEPT for partitioned calcs, **CORR/COVAR/COVARP**, **ATTR→SELECTEDVALUE**, **LOD balanced braces**, **PREVIOUS_VALUE→OFFSET**, **LOOKUP→OFFSET**, **RUNNING_*→CALCULATE+FILTER(ALLSELECTED)**, **TOTAL→CALCULATE+ALL** | Spatial (6), SCRIPT (4), SPLIT | REGEX (4), WINDOW_* frames | Medium |
| **M Query** | **33 connectors** (+8: OData, Google Analytics, Azure Blob/ADLS, Vertica, Impala, Hadoop Hive, Presto), 30+ transforms | OAuth, gateway, incremental refresh | Fallback #table, BigQuery/Oracle config | Low |
| **Prep Flow** | DAG traversal, 20+ action types, **ExtractValues**, **CustomCalculation**, **Script/Prediction/CrossJoin/PublishedDataSource** handlers, 5 new connection mappings | Hyper data loading | Prep VAR/VARP joins | Low |
| **Test Coverage** | **732 tests across 14 files** | Perf tests, integration tests, coverage files (Fabric has 750+ additional) | — | Medium |
| **CI/CD** | **5-stage pipeline** (lint+ruff, test, **strict validate+twbx**, **staging deploy**, production deploy), **pip caching** | Coverage reporting, Windows CI, schema validation | — | Medium |
| **Documentation** | **13 docs** + copilot instructions (ARCHITECTURE, KNOWN_LIMITATIONS, MIGRATION_CHECKLIST, DEPLOYMENT_GUIDE, TABLEAU_VERSION_COMPATIBILITY, CONTRIBUTING) | API docs | — | Low |
| **Config** | 11 env vars, 3 environments, **settings validation**, **dry-run**, **calendar/culture CLI**, **.env.example** | Config file, connection templating | — | Low |

---

## 10. Cross-Project Gap Analysis — TableauToFabric vs TableauToPowerBI

**Date:** 2026-03-06

### Architecture Differences

| Aspect | TableauToFabric | TableauToPowerBI |
|--------|----------------|------------------|
| **Storage mode** | DirectLake (compatibility 1604) | Import (compatibility 1550) |
| **Output artifacts** | 6: Lakehouse, Dataflow Gen2, Notebook, Pipeline, Semantic Model, PBI Report | 1: .pbip project (PBIR + TMDL) |
| **External dependencies** | `python-dateutil`, `azure-identity`, `requests`, `pydantic-settings`, `tableauserverclient` | None (stdlib only, optional azure-identity/requests) |
| **Extraction layer** | Shared (`tableau_export/`) — now synced | Shared (`tableau_export/`) — now synced |

### Fabric-Only Components (not applicable to PBI)

| Component | Purpose | Portability |
|-----------|---------|-------------|
| `fabric_import/lakehouse_generator.py` | Lakehouse definition | Not applicable — PBI uses Import mode |
| `fabric_import/dataflow_generator.py` | Dataflow Gen2 JSON | Not applicable — PBI uses M query partitions |
| `fabric_import/notebook_generator.py` | PySpark Notebook (.ipynb) | Not applicable — PBI has no notebook concept |
| `fabric_import/pipeline_generator.py` | Data Pipeline JSON | Not applicable — PBI uses Power BI Service |
| `fabric_import/semantic_model_generator.py` | DirectLake semantic model | Not applicable — PBI uses TMDL directly |
| `fabric_import/assessment.py` | Pre-migration assessment | **Portable** — could adapt for PBI |
| `fabric_import/strategy_advisor.py` | Migration strategy advisor | **Portable** — could adapt for PBI |
| `fabric_import/calc_column_utils.py` | Calc column classification | Partially ported (inline in PBI's tmdl_generator) |
| `fabric_import/constants.py` | Shared constants (visual IDs, Z-index) | PBI defines these inline |
| `fabric_import/naming.py` | Naming conventions | PBI uses `_clean_field_name` inline |
| `conversion/` (8 modules) | Per-object converters (intermediate representation) | **Portable** — modular conversion layer |
| `scripts/` (8 files) | PowerShell deployment scripts + TaskFlow configs | Fabric-specific deployment |

### Shared File Divergences (Output Generators)

#### `pbip_generator.py` (Fabric: 1843 lines vs PBI: 2115 lines)

| Feature | Fabric | PBI |
|---------|--------|-----|
| Slicer mode detection | Always Dropdown | `_detect_slicer_mode()` — Dropdown/List/Between/Basic |
| Bookmark creation | Inline in `create_report_structure` | Standalone `_create_bookmarks()` method |
| Report filters | From workbook-scope filters | From parameters via `_create_report_filters()` |
| Drill-through pages | Not implemented | `_create_drillthrough_pages()` |
| Action buttons | `_create_visual_nav_button` + `_create_visual_action_button` | `_create_action_visuals()` |
| Pages shelf | `_create_pages_shelf_slicer()` (animation hint) | Not implemented |
| Context filter promotion | Worksheet context → page level | Not implemented |
| Number format conversion | `_convert_number_format()` static helper | Not implemented |
| Measure classification | Single `is_measure` check | Two-set system (`_bim_measure_names` + `_measure_names`) |
| Visual object config | Trend lines, forecasting, map options, stepped colors, data bars, dual-axis sync, padding, row banding, reference bands, small multiples, analytics stats | Legend title/font-size, axis range min/max, log scale, reversed, dual-axis combo config, table/matrix grid, gradient min/mid/max |

#### `tmdl_generator.py` (Fabric: ~2100 lines vs PBI: ~2450 lines)

| Feature | Fabric | PBI |
|---------|--------|-----|
| Table partitions | DirectLake entity partitions | M query Import partitions |
| Date hierarchies | `_auto_date_hierarchies()` — auto Year>Quarter>Month>Day | Manual date table with M partition |
| Calculation groups | `_create_calculation_groups()` from param swap actions | Not implemented |
| Field parameters | `_create_field_parameters()` with NAMEOF | Not implemented |
| Expressions TMDL | `DatabaseQuery` + M parameters for connections | `DataFolder` parameter for file sources |
| Quick table calcs | Not implemented | `_create_quick_table_calc_measures()` |
| M transform steps | Not applicable (DirectLake) | `_build_m_transform_steps()` |

#### `visual_generator.py` (Fabric: 1087 lines vs PBI: 1053 lines)

| Difference | Detail |
|-----------|--------|
| Sankey/Chord mapping | Fabric: `sankeyChart`/`chordChart` (custom visuals) | PBI: `decompositionTree` (fallback) |
| Custom visual GUIDs | Fabric defines `CUSTOM_VISUAL_GUIDS` dict | PBI relies on PBI Desktop built-in |
| `_L` import | From `.constants` | From `powerbi_import.pbip_generator` |

#### `validator.py` (Fabric: 584 lines vs PBI: 601 lines)

| Fabric-only validators | PBI-only features |
|----------------------|------------------|
| `validate_notebook()` | `REQUIRED_PROJECT_FILES` / `REQUIRED_DIRS` class constants |
| `validate_lakehouse_definition()` | Explicit expected artifact lists |
| `validate_dataflow_definition()` | — |
| `validate_pipeline_definition()` | — |

### Test Coverage Gap

| Metric | Fabric | PBI |
|--------|--------|-----|
| Test files | 39 | 16 |
| Total tests (shared files) | 455 | 449 |
| Coverage test files | 9 files, 750 tests | None |
| **Grand total** | **~1,205** | **732** |
| Coverage ratio | ~2.4× PBI's test count | Baseline |

### Portability Assessment — What Could Be Brought to PBI

| Item | Effort | Value | Recommendation |
|------|--------|-------|----------------|
| `assessment.py` (pre-migration assessment) | Medium | High | **Port** — valuable for estimating migration complexity |
| `strategy_advisor.py` (migration strategy) | Medium | Medium | **Port** — helps users choose migration approach |
| `conversion/` (8 modular converters) | High | Medium | Consider — PBI already does this inline |
| Fabric coverage tests (750 tests) | Medium | High | **Port** — significant test coverage improvement |
| `calc_column_utils.py` (shared calc classification) | Low | Medium | **Port** — cleaner separation of concerns |
| `constants.py` + `naming.py` (shared utilities) | Low | Low | Optional — PBI inlines these |
| Pages shelf slicer | Low | Low | Optional — niche feature |
| Context filter promotion | Low | Medium | **Port** — improves filter fidelity |
| Number format conversion | Low | Medium | **Port** — `_convert_number_format()` utility |
| Calculation groups | Medium | Medium | Consider — useful for advanced scenarios |
| Field parameters | Medium | Medium | Consider — useful for dynamic axis switching |
| Auto date hierarchies | Low | Medium | **Port** — auto Year>Quarter>Month>Day for all date columns |
| `conftest.py` (shared test fixtures) | Low | High | **Port** — reduces test boilerplate |
