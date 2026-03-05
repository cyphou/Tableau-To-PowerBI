# Comprehensive Gap Analysis — Tableau to Power BI Migration Tool

**Date:** 2026-03-04 — updated after full gap implementation sprint (sessions 1-8)  
**Scope:** Every source file, test file, CI/CD, docs, and config
**Status:** 717 tests passing (2 skipped)

### Implementation Coverage

```
 EXTRACTION          GENERATION         INFRA / CI         DOCUMENTATION
+----------------+  +----------------+  +----------------+  +----------------+
| 16 object types|  | PBIR v4.0      |  | 5-stage CI/CD  |  | 13 doc files   |
| .twb/.twbx/.tfl|  | TMDL semantic  |  | 717 tests      |  | DAX reference  |
| 172+ DAX conv  |  | 60+ visuals    |  | Artifact valid |  | M query ref    |
| 26 connectors  |  | Drill-through  |  | Fabric deploy  |  | Prep ref       |
| 40+ transforms |  | Slicer modes   |  | Env configs    |  | Architecture   |
| Prep flow DAG  |  | Cond. format   |  | Settings valid |  | Gap analysis   |
| Ref lines/bands|  | RLS roles      |  | --dry-run      |  | Migration guide|
| Datasrc filters|  | Calendar/culture|  | --culture      |  | FAQ + more     |
+-------+--------+  +-------+--------+  +-------+--------+  +-------+--------+
        |                    |                    |                    |
        +--------------------+--------------------+--------------------+
                                     |
                              ALL IMPLEMENTED
```

---

## 1. Extraction Layer (`tableau_export/`)

### What IS implemented
- **16 object types extracted**: worksheets, dashboards, datasources, calculations, parameters (old+new XML format), filters, stories, actions (filter/highlight/url/param/set-value), sets, groups (combined+value), bins, hierarchies, sort_orders, aliases, custom_sql, user_filters
- **File formats**: `.twb`, `.twbx`, `.tds`, `.tdsx` (Tableau Desktop) + `.tfl`/`.tflx` (Tableau Prep)
- **Connection parsing** (`datasource_extractor.py`): 10 connection types fully parsed (Excel, CSV, GeoJSON, SQL Server, PostgreSQL, BigQuery, Oracle, MySQL, Snowflake, SAP BW) + fallback for unknown types
- **Relationship extraction**: Both old `[Table].[Column]` join-clause format and new Object Model relationships; bare `[Column]` refs inferred from child relation order
- **Table deduplication**: Only physical tables (`type="table"`), deduplicated by name; SQL Server fallback via datasource-level `<cols>` mapping
- **Mark-to-visual mapping** (`_map_tableau_mark_to_type`): 50+ entries covering standard marks, extended chart types (Tableau 2020+)
- **Dashboard objects**: worksheetReference, text, image, web, blank, filter_control with floating/tiled/fixed layout modes; **padding, margin, and border** extracted from `<zone-style>` format elements
- **Mark encoding**: color (quantitative/categorical type detection via `:qk`/`:nk` suffixes, palette colors from `<color-palette>`), size, shape, label (position/font/orientation), tooltips (text + viz-in-tooltip)
- **Story points**: Captured with filter state per story point
- **Actions**: 6 types (filter, highlight, url, navigate, parameter, set-value)
- **User filters**: User-filter XML elements, calculated security (USERNAME/FULLNAME/ISMEMBEROF)
- **CSV delimiter auto-detection**: Attempts `csv.Sniffer` on embedded CSV from `.twbx` archives
- **Prep flow parsing** (`prep_flow_parser.py`): Full DAG traversal (Kahn's topological sort), 5 input types, 15+ Clean action types, Aggregate, Join (6 types), Union, Pivot; `merge_prep_with_workbook()` for TWB+Prep integration
- **Reference lines & annotations**: Reference lines (constant/average/median/trend with style/color/thickness), trend lines with type/degree/confidence/R², and annotations (point/area type with text and position) extracted from worksheet XML
- **Legend extraction**: Position, title, font from `<legend>` element + `legend-title`/`color-legend` style-rule merging
- **Layout containers**: `<layout-container>` parsed for orientation (horizontal/vertical), position, and child zone names
- **Device layouts**: `<device-layout>` parsed for device type (phone/tablet), zone visibility/positions, auto-generated flag
- **Formatting depth**: Table/header formatting attributes (font-size, font-weight, color, align, border, banding) from `<format>` elements with scope; style-rule sub-format collection
- **Axis detection**: Continuous vs discrete type detection, dual-axis detection (multiple y-axes), `dual_axis_sync` from `synchronized` attribute; axis range (min/max), log scale, reversed orientation
- **Sort order depth**: Computed sort (sort-by field via `using` attribute), sort type detection (manual/computed/alphabetic)
- **Table calc field detection**: Regex for `pcto`, `pctd`, `diff`, `running_*`, `rank*` prefixed field names; addressing/partitioning field extraction from `<table-calc>` elements

### What is MISSING or INCOMPLETE
- **Tableau Server/Cloud connection types**: No support for Tableau Server live connections or Extract (.hyper) reconnection — only reads the XML metadata
- **`.hyper` file parsing**: Prep `LoadHyper` emits an empty `#table` — Hyper file data is not read
- **Tableau extensions/LOD filters**: LOD calc extraction relies on text-based `{FIXED ...}` parsing (can miss edge cases with nested LODs or LOD inside LOD)
- **Dashboard layout containers**: Layout containers are extracted but deeply nested containers may lose relative positioning when mapped to PBI
- **Tableau 2024.3+ features**: New features (dynamic zone visibility, dynamic parameters with database queries) are not extracted
- **Data source filters** (extract-level filters baked into the connection): Not extracted as separate objects
- **Reference bands**: Reference bands are not extracted (reference lines and annotations are)
- **Custom shapes / images on marks**: Shape encoding is extracted as a field reference only — actual custom shape files are not migrated
- **Connection credentials/OAuth**: Credential metadata is stripped (by design), but OAuth redirect configs aren't migrated
- **Multiple data sources per worksheet**: The extractor handles this, but the downstream TMDL generator may place all calculations on the "main" table, losing the datasource context
- **Number formatting patterns**: Tableau custom number formats are not extracted or converted to PBI format strings
- **Tooltip formatting**: Rich tooltip formatting (HTML, custom layout) is not preserved

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
- **667 tests across 12 test files + 50 new gap implementation tests = 717 tests** (2 skipped):

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
- **~100+ simple function mappings** via pre-compiled regex (ISNULL→ISBLANK, ZN→IF(ISBLANK), COUNTD→DISTINCTCOUNT, etc.)
- **20+ dedicated converters** for complex functions (DATEDIFF arg reorder, LOD→CALCULATE, RANK→RANKX, etc.)
- **Operator conversion**: `==`→`=`, `!=`→`<>`, `or`→`||`, `and`→`&&`, `+`→`&` (string concat)
- **Structure conversion**: CASE/WHEN→SWITCH, IF/THEN/ELSEIF→nested IF
- **Column resolution**: `[col]`→`'Table'[col]`, cross-table `RELATED()`, `LOOKUPVALUE()` for M2M
- **AGG(IF)→AGGX**: SUM(IF())→SUMX, AVERAGE(IF())→AVERAGEX, etc.
- **AGG(expr)→AGGX**: SUM(a*b)→SUMX('T', a*b); also STDEV.S→STDEVX.S, MEDIAN→MEDIANX
- **Date literals**: `#YYYY-MM-DD#`→`DATE(Y, M, D)`
- **Security functions**: USERNAME()→USERPRINCIPALNAME(), FULLNAME()→USERPRINCIPALNAME()

### What is MISSING (no DAX equivalent)

| Tableau Function | Current Output | Issue |
|-----------------|----------------|-------|
| **MAKEPOINT, MAKELINE, DISTANCE, BUFFER, AREA, INTERSECTION** | `0` placeholder + comment | No spatial functions in DAX |
| **HEXBINX, HEXBINY** | `0` + comment | No hex-binning in DAX |
| **COLLECT** | `0` + comment | No spatial collection |
| **SCRIPT_BOOL/INT/REAL/STR** | `BLANK()` + comment | R/Python scripting has no direct DAX equivalent |
| **SPLIT** | `BLANK()` + comment | No string split to array in DAX |
| **PREVIOUS_VALUE** | Comment suggesting manual rewrite | Requires iterative patterns not available in DAX |

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
| **RUNNING_SUM/AVG/COUNT** | `CALCULATE(AGG, ...)` | Simplified — no window frame specification; uses ALL or ALLEXCEPT (when partition_fields are provided) for context |
| **WINDOW_SUM/AVG/MAX/MIN** | `CALCULATE(inner, ALL/ALLEXCEPT('table'))` | Loses window frame boundaries (start/end offset); supports **ALLEXCEPT with partition fields** for partitioned calculations |
| **WINDOW_CORR/COVAR/COVARP** | `0` | Full placeholder |
| **ATTR()** | `SELECTEDVALUE()` | ✅ FIXED — Returns scalar value; empty string if multiple values |
| **LTRIM/RTRIM** | `TRIM()` | DAX TRIM removes all leading/trailing spaces, not just left/right |
| **ATAN2** | `ATAN2()` | Quadrant handling note — DAX ATAN2 uses (y,x) not (x,y) |
| **LOD with no dimensions** | `CALCULATE(AGG(...))` | ✅ FIXED — Uses balanced brace matching (depth counter) instead of global `}` → `)` replacement |
| **LOOKUP** | `LOOKUPVALUE()` | Only partial — doesn't handle offset parameter (row-relative lookup) |
| **String `+` → `&`** | Only at depth 0 | Arithmetic `+` inside string concatenation contexts may be incorrectly preserved |

---

## 6. M Query Gaps

### What IS implemented
- **25 connector types**: Excel, SQL Server, PostgreSQL, CSV, BigQuery, MySQL, Oracle, Snowflake, GeoJSON, Teradata, SAP HANA, SAP BW, Amazon Redshift, Databricks, Spark SQL, Azure SQL, Azure Synapse, Google Sheets, SharePoint, JSON, XML, PDF, Salesforce, Web, Custom SQL
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
| **Extraction** | 16 object types, 10 connectors, annotations, layout containers, device layouts, formatting depth, legend, axes, sort depth, **datasource filters**, **reference bands**, **number formatting** | Hyper parsing, 2024+ features | Prep VAR/VARP, layout nesting depth | Low |
| **TMDL Generation** | 12+ phases, full model, date hierarchy, quick table calcs, partition addressing, **semantic validation**, **calendar customization**, **culture config** | Incremental, composite model | — | Low |
| **PBIR Generation** | 60+ visuals, filters, themes, mobile layout, tooltip binding, action buttons, conditional formatting, axis config, legend, sort state, table formatting, padding, **drill-through pages**, **slicer type variety** | Small Multiples | Position scaling | Low |
| **DAX Conversion** | ~100+ patterns, ALLEXCEPT for partitioned calcs, **CORR/COVAR/COVARP**, **ATTR→SELECTEDVALUE**, **LOD balanced braces** | Spatial (6), SCRIPT (4), SPLIT, PREVIOUS_VALUE | REGEX (4), RUNNING_* frames, WINDOW_* frames | Medium |
| **M Query** | 25 connectors, 30+ transforms | OAuth, gateway, incremental refresh | Fallback #table, BigQuery/Oracle config | Low |
| **Test Coverage** | **717 tests across 13 files** | Perf tests, integration tests | — | Low |
| **CI/CD** | **5-stage pipeline** (lint+ruff, test, **strict validate+twbx**, **staging deploy**, production deploy), **pip caching** | Coverage, Windows CI, schema validation | — | Medium |
| **Documentation** | **13 docs** + copilot instructions (ARCHITECTURE, KNOWN_LIMITATIONS, MIGRATION_CHECKLIST, DEPLOYMENT_GUIDE, TABLEAU_VERSION_COMPATIBILITY, CONTRIBUTING) | API docs | — | Low |
| **Config** | 11 env vars, 3 environments, **settings validation**, **dry-run**, **calendar/culture CLI**, **.env.example** | Config file, connection templating | — | Low |
