<!-- Copilot instructions for the Tableau to Power BI migration project -->

# Project: Tableau to Power BI Migration

Automated migration of Tableau workbooks (.twb/.twbx) to Power BI projects (.pbip) in PBIR v4.0 format with TMDL semantic model.

## Architecture — 2-Step Pipeline

```
.twbx --> [Extraction] --> 17 JSON files --> [Generation] --> .pbip (PBIR + TMDL)
```

1. **Extraction** (`tableau_export/`): Parses Tableau XML, extracts worksheets/dashboards/datasources/calculations/parameters/filters/stories/actions/sets/groups/bins/hierarchies/sort_orders/aliases/custom_sql
2. **Generation** (`powerbi_import/`): Produces the complete .pbip project (BIM → TMDL, PBIR v4.0 report, Power Query M, visuals, filters, bookmarks)

## Project Structure

- **tableau_export/**: Tableau XML extraction and parsing + DAX formula conversion
  - `extract_tableau_data.py`: Main orchestrator, parses TWB/TWBX, extracts 17 object types
  - `datasource_extractor.py`: Datasource extraction (connections, tables, columns, calculations, relationships)
  - `dax_converter.py`: 180+ Tableau → DAX formula conversions (LOD, table calcs, security, etc.)
  - `m_query_builder.py`: Power Query M generator (33 connector types + 43 transformation generators: rename, filter, aggregate, pivot/unpivot, join, union, sort, conditional columns — chainable via `inject_m_steps()`)
  - `prep_flow_parser.py`: Tableau Prep flow parser (.tfl/.tflx → Power Query M) — DAG traversal, Clean/Join/Aggregate/Union/Pivot steps, expression converter, merge with TWB datasources
  - `server_client.py`: Tableau Server/Cloud REST API client — PAT/password auth, workbook download, datasource listing, batch download, regex search, context manager, paginated API fetching (`_paginated_get`), 9 new endpoints: `list_users`, `list_groups`, `list_views`, `get_workbook_connections`, `list_schedules`, `get_site_info`, `list_prep_flows`, `download_prep_flow`, `get_server_summary`, `get_workbook_extract_tasks`, `get_workbook_subscriptions`
  - `hyper_reader.py`: Hyper file data loader — 3-tier reader chain (tableauhyperapi → sqlite3 → binary header scan), schema discovery, type mapping (28 types), M expression generation (#table inline / Csv.Document), CSV export (`export_hyper_to_csv`), relationship inference (`infer_hyper_relationships`), metadata enrichment with recommendations
  - `pulse_extractor.py`: Tableau Pulse metric extractor — parses Pulse metric definitions from TWB XML (metric name, measure, time dimension, filters, goals)
- **powerbi_import/**: Power BI project generation
  - `pbip_generator.py`: .pbip generator (PBIR v4.0, visuals, filters, bookmarks, slicers, textbox, image, pages shelf, number format conversion, drill-through pages)
  - `tmdl_generator.py`: Unified semantic model generator — direct Tableau → TMDL (tables, columns, measures, relationships, hierarchies, sets/groups/bins, parameters, RLS, dataCategory, isHidden, calculation groups, field parameters, M-based calculated columns)
  - `visual_generator.py`: Visual container generator — 118 visual type mappings, PBIR-native config templates, data role definitions, query state builder, slicer sync groups, cross-filtering disable, action button navigation, TopN filters, sort state, reference lines, conditional formatting
  - `import_to_powerbi.py`: Generation pipeline orchestrator (supports `--output-dir`, `--output-format fabric` for shared models)
  - `m_query_generator.py`: Sample data M query generator
  - `assessment.py`: Pre-migration readiness assessment — 9 categories (datasource, calculation, visual, filter, data model, interactivity, extract, scope, connection string audit), pass/warn/fail scoring
  - `server_assessment.py`: Server-level portfolio assessment — per-workbook GREEN/YELLOW/RED classification, 8-axis complexity computation, effort estimation, migration wave planning, connector census, HTML executive dashboard
  - `strategy_advisor.py`: Migration strategy advisor — recommends Import/DirectQuery/Composite based on 7 signals
  - `validator.py`: Artifact validator — validates .pbip projects (JSON, TMDL, report structure) before opening in PBI Desktop
  - `migration_report.py`: Per-item fidelity tracking and migration status reporting
  - `goals_generator.py`: PBI Goals/Scorecard generator — converts Tableau Pulse metrics to Power BI Goals JSON (goal name, current value measure, target, status rules, sparkline)
  - `shared_model.py`: Multi-workbook merge engine — fingerprint-based table matching (SHA-256), Jaccard column overlap scoring, 4-dimension merge scoring (0–100), measure/column/relationship/parameter conflict resolution and deduplication, custom SQL fingerprinting, fuzzy table matching, RLS conflict detection, cross-workbook relationship suggestions, merge preview
  - `merge_assessment.py`: Merge assessment reporter — JSON + console + HTML output with table overlap analysis, conflict listing, merge/partial/separate recommendation, RLS conflict table, relationship suggestions
  - `thin_report_generator.py`: Thin report generator — PBIR `byPath` wiring to shared SemanticModel, field remapping for namespaced measures, delegates to PBIPGenerator for page/visual content
  - `plugins.py`: Plugin system — auto-discovers and loads plugins from `examples/plugins/` via `importlib`, hook-based extension points for visual mapping, DAX post-processing, naming conventions
  - `alerts_generator.py`: Data-driven alert generator — extracts threshold/alert conditions from parameters, calculations, and reference lines → PBI alert rules JSON
  - `visual_diff.py`: Visual diff report — side-by-side HTML comparing Tableau vs PBI visuals, per-field coverage, encoding gap detection
  - `comparison_report.py`: Migration comparison report generator — detailed HTML/JSON comparison of source vs output artifacts
  - `gateway_config.py`: Gateway configuration generator — on-premises data gateway connection mapping
  - `global_assessment.py`: Global cross-workbook assessment — pairwise merge scoring, BFS clustering, HTML heatmap report
  - `merge_config.py`: Merge configuration — per-table merge rules, conflict resolution settings
  - `merge_report_html.py`: Merge assessment HTML report generator
  - `html_template.py`: Shared HTML report template — centralized CSS/JS for all 9 HTML generators. Fluent/PBI design with CSS custom properties, gradient headers, stat cards, collapsible sections, sortable tables, badges, fidelity bars, charts, tabs, flow diagrams. Reusable components: `html_open/close`, `stat_grid/card`, `section_open/close`, `badge`, `fidelity_bar`, `donut_chart`, `bar_chart`, `data_table`, `tab_bar/content`, `heatmap_table`, `flow_diagram`, `cmd_box`, `card`, `esc`
  - `telemetry.py`: Migration telemetry collector (v2) — timing, counts, version, `record_event()` for granular per-workbook/visual/measure event logging, opt-in reporting
  - `telemetry_dashboard.py`: Interactive observability dashboard — 4-tab layout (Overview/Portfolio/Bottlenecks/Telemetry), JS interactivity (sort/search/date filter), JSONL telemetry, portfolio progress tracker, bottleneck analyzer
  - `notebook_api.py`: Interactive Jupyter migration API — `MigrationSession` class with load/assess/preview_dax/preview_m/preview_visuals/edit_dax/override_visual_type/configure/generate/validate/deploy, notebook .ipynb generation
  - `refresh_generator.py`: Scheduled refresh migration — Tableau Server extract-refresh schedules → PBI refresh config JSON, subscription mapping, frequency/time/day-of-week conversion
  - `progress.py`: Progress tracking — real-time progress bar and ETA for batch migrations
  - `wizard.py`: Interactive migration wizard — guided step-by-step CLI for first-time users
  - `incremental.py`: Incremental migration — track changes, skip unchanged artifacts
  - **Fabric-native generators** (`--output-format fabric`):
    - `fabric_constants.py`: Shared constants — Spark type maps, PySpark type maps, aggregation detection regex, artifact list
    - `fabric_naming.py`: Name sanitisation for Lakehouse tables, Spark columns, Dataflow queries, Pipeline names, Python variables
    - `calc_column_utils.py`: Calculation classification (calc columns vs measures), Tableau→M formula conversion, Tableau→PySpark conversion, M Table.AddColumn step builder
    - `lakehouse_generator.py`: Lakehouse definition generator — Delta table schemas, DDL scripts, table metadata JSON
    - `dataflow_generator.py`: Dataflow Gen2 generator — Power Query M ingestion queries, mashup document, Lakehouse destination config per query, calculated column injection
    - `notebook_generator.py`: PySpark Notebook generator — ETL pipeline notebook (9 connector templates), transformations notebook (withColumn materialisation), Synapse PySpark kernel
    - `pipeline_generator.py`: Data Pipeline generator — 3-stage orchestration (Dataflow refresh → Notebook ETL → Semantic Model refresh), placeholder activity IDs
    - `fabric_semantic_model_generator.py`: DirectLake Semantic Model generator — delegates to tmdl_generator, wraps in .SemanticModel item with .platform manifest
    - `fabric_project_generator.py`: Fabric project orchestrator — coordinates all 5 generators (Lakehouse + Dataflow + Notebook + SemanticModel + Pipeline)
  - `dax_optimizer.py`: DAX optimizer engine — AST-based rewriter (nested IF→SWITCH, IF(ISBLANK)→COALESCE, redundant CALCULATE collapse, constant folding, SUMX simplification), Time Intelligence auto-injection (YTD, PY, YoY%), measure dependency DAG, optimization report
  - `equivalence_tester.py`: Cross-platform validation — measure value comparison with tolerance, SSIM-based screenshot comparison, validation report generation
  - `regression_suite.py`: Regression suite — snapshot generation (tables, measures, filters, formula hashes), snapshot comparison with drift detection
  - `recovery_report.py`: Self-healing recovery report — records every auto-repair action (category, severity, description, action, follow-up), JSON export, MigrationReport integration via `merge_into()`
  - `security_validator.py`: Centralized security utilities — path validation (null byte, traversal, extension whitelist), ZIP slip defense (`safe_zip_extract_member`), XML XXE protection (`safe_parse_xml`), credential detection/redaction (10 patterns), M query credential scrubbing, template substitution sanitization, migration artifact scanning
  - `governance.py`: Enterprise governance framework — `GovernanceEngine` (naming conventions, PII detection, sensitivity labels), `AuditTrail` (append-only JSONL with SHA-256 hashing), `run_governance()` convenience function, configurable warn/enforce modes
  - `sla_tracker.py`: Migration SLA tracker — per-workbook time/fidelity/validation compliance, `SLATracker` with `start()`/`record_result()`/`get_report()`, `SLAReport` with compliance rate and JSON export
  - `monitoring.py`: Monitoring integration — export metrics to Azure Monitor, Prometheus, or structured JSON. `MigrationMonitor` with `record_metric()`/`record_event()`/`record_migration()`/`flush()`. Backend system (json/azure/prometheus/none)
  - `marketplace.py`: Migration Marketplace — versioned pattern registry (`PatternRegistry`) for community DAX recipes, visual mappings, M templates. JSON-file catalogue, semver versioning, search by tags/category, `apply_dax_recipes()`, `apply_visual_overrides()`, export
  - `dax_recipes.py`: DAX recipe overrides — industry-specific KPI measure templates: Healthcare (6), Finance (8), Retail (7). `apply_recipes()` inject/replace/overwrite, `recipes_to_marketplace_format()` bridge
  - `model_templates.py`: Industry model templates — pre-built semantic model skeletons: Healthcare (Encounters/Patients/Providers/Facilities), Finance (Financials/Accounts/CostCenters/AR), Retail (Sales/Products/Stores/Customers). `apply_template()` merges into migrated tables
  - `geo_passthrough.py`: Shapefile/GeoJSON passthrough — `GeoExtractor` extracts .geojson/.topojson/.shp from .twbx, `build_shape_map_config()` for PBI shapeMap, `copy_to_registered_resources()`, ZIP slip protection
  - `api_server.py`: REST API server — stdlib `http.server`, `POST /migrate` (multipart upload), `GET /status/{id}`, `GET /download/{id}` (ZIP), `GET /health`, `GET /jobs`. Thread-safe job store, background migration workers.
  - `schema_drift.py`: Schema drift detection — `detect_schema_drift()` compares extraction snapshots (tables, columns, calculations, worksheets, relationships, parameters, filters). `load_snapshot()`, `save_snapshot()`. JSON + summary output.
  - `permission_mapper.py`: Post-migration automation — `generate_rls_powershell()` creates .ps1 scripts for Azure AD RLS role assignment via Power BI REST API, `generate_credential_template()` creates JSON credential placeholders per datasource connection
  - `deploy/`: Fabric deployment subpackage
    - `auth.py`: Azure AD authentication — Service Principal + Managed Identity (optional `azure-identity`)
    - `client.py`: Fabric REST API client — auto-detects `requests` with retry, falls back to `urllib`
    - `deployer.py`: Fabric deployment orchestrator — deploy datasets, reports, batch directories, `endorse_item()` for promoted/certified endorsement
    - `utils.py`: `DeploymentReport` (pass/fail tracking), `ArtifactCache` (incremental deployment metadata)
    - `config/settings.py`: Centralized config via env vars (FABRIC_WORKSPACE_ID, FABRIC_TENANT_ID, etc.)
    - `config/environments.py`: Per-environment configs (development/staging/production)
    - `pbi_client.py`: Power BI Service REST API client — Azure AD auth (SP/MI/token), import .pbix, refresh, list/delete datasets/reports
    - `pbix_packager.py`: .pbip → .pbix ZIP packager with OPC content types
    - `pbi_deployer.py`: PBI Service deployment orchestrator — package, upload, poll, refresh, validate, `deploy_refresh_schedule()` for PBI REST API refresh config, `deploy_rolling()` for blue/green deployment with canary validation and auto-rollback
    - `bundle_deployer.py`: Fabric bundle deployer — deploy shared model + thin reports as atomic bundle, artifact discovery, per-report error isolation, rebind, refresh, `BundleDeploymentResult`
    - `multi_tenant.py`: Multi-tenant deployment — `TenantConfig`/`MultiTenantConfig` (validate/load/save JSON), `_apply_connection_overrides()` (template substitution: `${TENANT_SERVER}`, `${TENANT_DATABASE}`, context-aware escaping, null byte blocking, placeholder validation), `deploy_multi_tenant()` orchestrator with per-tenant results
- **tests/**: Unit and integration tests (6,819+ tests across 141 test files + conftest.py shared fixtures)
- **docs/**: FAQ, PBI project guide, mapping reference, **ROADMAP.md** (v22–v28 development roadmap per agent)
- **.github/workflows/ci.yml**: CI/CD pipeline (lint → test → validate → deploy)
- **.github/workflows/publish.yml**: PyPI auto-publish workflow (tag-triggered, OIDC trusted publisher)
- **Dockerfile**: Production-ready container image for the REST API migration server
- **examples/plugins/**: Plugin examples (custom visual mapper, DAX post-processor, naming convention)
- **artifacts/**: Migration output (generated .pbip projects)

## Technologies

- Python 3.8+ (standard library only — no external dependencies for core migration)
- Optional dependencies: `azure-identity` (Fabric auth), `requests` (HTTP client with retry), `pydantic-settings` (typed config)
- Modules: xml.etree, json, os, uuid, re, zipfile, argparse, datetime, copy, logging, glob
- Power BI Desktop (December 2025+)
- Output format: PBIR v4.0 + TMDL (default), or Fabric-native (Lakehouse + Dataflow Gen2 + Notebook + DirectLake Semantic Model + Pipeline)

## Main Command

```bash
python migrate.py path/to/workbook.twbx
python migrate.py path/to/workbook.twbx --prep path/to/flow.tfl
python migrate.py path/to/workbook.twbx --output-dir /tmp/pbi_output --verbose
python migrate.py --batch examples/tableau_samples/ --output-dir /tmp/batch_output
python migrate.py path/to/workbook.twbx --dry-run
python migrate.py path/to/workbook.twbx --calendar-start 2018 --calendar-end 2028
python migrate.py path/to/workbook.twbx --culture fr-FR
python migrate.py path/to/workbook.twbx --assess
python migrate.py path/to/workbook.twbx --deploy WORKSPACE_ID --deploy-refresh
python migrate.py --server https://tableau.company.com --workbook "Sales Dashboard" --token-name my-pat --token-secret secret
python migrate.py --server https://tableau.company.com --server-batch Marketing --output-dir /tmp/batch
python migrate.py path/to/workbook.twbx --languages fr-FR,de-DE,ja-JP
python migrate.py path/to/workbook.twbx --goals
python migrate.py path/to/workbook.twbx --check-schema
python migrate.py --shared-model wb1.twbx wb2.twbx --model-name "Shared Sales"
python migrate.py --shared-model wb1.twbx wb2.twbx --assess-merge
python migrate.py --shared-model wb1.twbx wb2.twbx --force-merge
python migrate.py --batch examples/tableau_samples/ --shared-model
python migrate.py --global-assess --batch examples/tableau_samples/
python migrate.py --shared-model wb1.twbx wb2.twbx --deploy-bundle WORKSPACE_ID --bundle-refresh
python migrate.py --deploy-bundle WORKSPACE_ID --output-dir artifacts/shared/MyModel
python migrate.py --shared-model wb1.twbx wb2.twbx --multi-tenant tenants.json
python migrate.py --shared-model wb1.twbx wb2.twbx --live-connection WORKSPACE_ID/ModelName
python migrate.py --server https://tableau.company.com --workbook "Sales" --token-name pat --token-secret secret --migrate-schedules
python migrate.py --shared-model wb1.twbx wb2.twbx --output-format fabric
python migrate.py --shared-model wb1.twbx wb2.twbx --output-format fabric --output-dir /tmp/fabric_shared
python migrate.py path/to/workbook.twbx --output-format fabric
python migrate.py path/to/workbook.twbx --output-format fabric --output-dir /tmp/fabric_output
python migrate.py path/to/workbook.twbx --check-drift /path/to/snapshot_dir
python migrate.py path/to/workbook.twbx --qa
python migrate.py path/to/workbook.twbx --no-optimize-dax --no-compare
```

## Extracted Objects (17 types)

| Type | JSON File | Description |
|------|-----------|-------------|
| worksheets | worksheets.json | Sheets with fields, filters, formatting, mark_encoding, axes |
| dashboards | dashboards.json | Dashboards with objects (worksheet, text, image, filter_control) |
| datasources | datasources.json | Sources with tables, columns, relationships, connection_map |
| calculations | calculations.json | Tableau calculations (formulas, role, type) |
| parameters | parameters.json | Parameters with values, domain_type, and allowable_values (both XML formats) |
| filters | filters.json | Global filters with fields and values |
| stories | stories.json | Story points → converted to PBI bookmarks |
| actions | actions.json | Actions (filter/highlight/url/navigate/param/set) |
| sets | sets.json | Sets → boolean calculated columns |
| groups | groups.json | Manual groups → SWITCH columns |
| bins | bins.json | Intervals → FLOOR columns |
| hierarchies | hierarchies.json | Drill-paths → PBI hierarchies |
| sort_orders | sort_orders.json | Sort orders |
| aliases | aliases.json | Column aliases |
| custom_sql | custom_sql.json | Custom SQL queries |
| user_filters | user_filters.json | User filters, security rules → PBI RLS roles |
| hyper_files | hyper_files.json | Hyper file row data for M partition inlining |

## Key Model Files

The DAX context is managed in `tmdl_generator.py` via dictionaries:
- `calc_map`: calculation ID → DAX formula
- `param_map`: parameter name → value
- `column_table_map`: column name → table name
- `measure_names`: set of measure names
- `param_values`: parameter → inline value
- `col_metadata_map`: column name → {hidden, semantic_role, description}

## Supported DAX Conversions (180+)

| Category | Tableau | DAX |
|----------|---------|-----|
| Null/Logic | ISNULL, ZN, IFNULL | ISBLANK, IF(ISBLANK) |
| Text | CONTAINS, ASCII, LEN, LEFT, RIGHT, MID, UPPER, LOWER, REPLACE, TRIM | CONTAINSSTRING, UNICODE, LEN, LEFT, RIGHT, MID, UPPER, LOWER, SUBSTITUTE, TRIM |
| Date | DATETRUNC, DATEPART, DATEDIFF, DATEADD, TODAY, NOW | STARTOF*, YEAR/MONTH/DAY/etc, DATEDIFF, DATEADD, TODAY, NOW |
| Math | ABS, CEILING, FLOOR, ROUND, POWER, SQRT, LOG, LN, EXP, SIN, COS, TAN | identical or mapped |
| Stats | MEDIAN, STDEV, STDEVP, VAR, VARP, PERCENTILE, CORR, COVAR | MEDIAN, STDEV.S, STDEV.P, VAR.S, VAR.P, PERCENTILE.INC, CORREL, COVARIANCE.S |
| Conversion | INT, FLOAT, STR, DATE, DATETIME | INT, CONVERT, FORMAT, DATE, DATE |
| LOD | {FIXED dims : AGG} | CALCULATE(AGG, ALLEXCEPT) |
| LOD | {INCLUDE dims : AGG} | CALCULATE(AGG) |
| LOD | {EXCLUDE dims : AGG} | CALCULATE(AGG, REMOVEFILTERS) |
| Table Calc | RUNNING_SUM/AVG/COUNT | CALCULATE(SUM/AVERAGE/COUNT) |
| Table Calc | RANK, RANK_UNIQUE, RANK_DENSE | RANKX(ALL()) |
| Table Calc | WINDOW_SUM/AVG/MAX/MIN | CALCULATE() |
| Syntax | ==, or/and, ELSEIF, + (strings), multi-line IF | =, \|\|/&&, ,, &, condensed IF |
| Cross-table | Column refs from other tables | RELATED() (manyToOne) or LOOKUPVALUE() (manyToMany) |
| Iterator | SUM(IF(...)), AVG(IF(...)) | SUMX('table', IF(...)), AVERAGEX('table', IF(...)) |
| Aggregation | COUNTD | DISTINCTCOUNT |
| Security | USERNAME() | USERPRINCIPALNAME() |
| Security | FULLNAME() | USERPRINCIPALNAME() |
| Security | USERDOMAIN() | "" (no DAX equivalent — use RLS roles) |
| Security | ISMEMBEROF("group") | TRUE() + RLS role per group |

## Power Query M Transformation Generators (43)

All transform functions return `(step_name, step_expression)` tuples with `{prev}` placeholder, chained via `inject_m_steps()`.

| Category | Functions | Power Query M |
|----------|-----------|---------------|
| Column | rename, remove, select, duplicate, reorder, split, merge | Table.RenameColumns, RemoveColumns, SelectColumns, DuplicateColumn, ReorderColumns, SplitColumn, CombineColumns |
| Value | replace, replace_nulls, trim, clean, upper, lower, proper, fill_down, fill_up | Table.ReplaceValue, TransformColumns, FillDown, FillUp |
| Filter | filter_values, exclude, range, nulls, contains, distinct, top_n | Table.SelectRows, Table.Distinct, Table.FirstN |
| Aggregate | group by (sum/avg/count/countd/min/max/median/stdev) | Table.Group |
| Pivot | unpivot, unpivot_other, pivot | Table.Unpivot, UnpivotOtherColumns, Pivot |
| Join | inner, left, right, full, leftanti, rightanti | Table.NestedJoin + ExpandTableColumn |
| Union | append, wildcard_union | Table.Combine, Folder.Files |
| Reshape | sort, transpose, add_index, skip_rows, remove_last, remove_errors, promote/demote headers | Table.Sort, Transpose, AddIndexColumn, Skip, RemoveLastN |
| Calculated | add_column, conditional_column | Table.AddColumn |

TWB-embedded transforms (column renames from captions) are auto-detected and injected into M queries.

## PBIR Report Features

- **Visuals**: worksheetReference → visual.json with query, title, labels, legend, axes
- **Textbox**: dashboard text objects → visualType "textbox"
- **Image**: image objects → visualType "image"
- **Slicers**: filter_control --> visualType "slicer" (dropdown, list, between, relative date modes)
- **Filters**: 3 levels (report, page, visual) with categorical and range conditions
- **Bookmarks**: Tableau stories --> PBI bookmarks
- **Formatting**: labels on/off, label color, legend, axes, background
- **Layout**: positions and sizes calculated with scale factor
- **Custom theme**: Tableau dashboard colors --> PBI theme JSON (RegisteredResources/TableauMigrationTheme.json) with dataColors, textClasses, visualStyles
- **Conditional formatting**: quantitative color encoding --> PBI dataPoint gradient (min/max rules)
- **Reference lines**: Tableau reference lines --> PBI constant lines on valueAxis (dashed, labeled)
- **Tooltip pages**: worksheets with viz_in_tooltip --> PBI Tooltip pages (480x320, pageType: "Tooltip")
- **Drill-through pages**: drill-through filter fields --> PBI Drillthrough pages with target filters
- **Number formats**: Tableau number format patterns --> PBI formatString on measures/columns
- **Datasource filters**: Extract-level filters --> PBI report-level filter objects

## Visual Type Mapping (118 Tableau mark types)

| Tableau Mark | Power BI visualType | Notes |
|-------------|-------------------|-------|
| Bar | clusteredBarChart | Standard bar |
| Stacked Bar | stackedBarChart | |
| Line | lineChart | With markers |
| Area | areaChart | |
| Pie | pieChart | |
| SemiCircle / Donut / Ring | donutChart | |
| Circle / Shape / Dot Plot | scatterChart | |
| Square / Hex / Treemap | treemap | |
| Text | tableEx | Table with text |
| Automatic | table | Default table |
| Map / Density | map | |
| Polygon / Multipolygon | filledMap | Choropleth |
| Gantt Bar / Lollipop | clusteredBarChart | Approximation |
| Histogram | clusteredColumnChart | |
| Box Plot | boxAndWhisker | |
| Waterfall | waterfallChart | |
| Funnel | funnel | |
| Bullet / Radial / Gauge | gauge | |
| Heat Map / Highlight Table / Calendar | matrix | Conditional formatting |
| Packed Bubble / Strip Plot | scatterChart | Bubble variant; size encoding auto-injected |
| Word Cloud | wordCloud | |
| Dual Axis / Combo / Pareto | lineClusteredColumnComboChart | |
| Bump Chart / Slope Chart / Timeline / Sparkline | lineChart | |
| Butterfly Chart / Waffle | hundredPercentStackedBarChart | Negate one measure for symmetry |
| Sankey / Chord / Network | decompositionTree | |
| KPI | card | |
| Image | image | |
| Violin Plot | boxAndWhisker | Custom visual ViolinPlot1.0.0 |
| Parallel Coordinates | lineChart | Custom visual ParallelCoordinates1.0.0 |
| Calendar Heat Map | matrix | Auto-enables conditional formatting |

## Semantic Model Features

- **description (auto-generated)**: Every table, column, and measure gets an auto-generated `description` for Copilot/Q&A readiness. Tables: "{N} columns: {col1}, {col2}...". Columns: "{dataType} column [categorized as {category}] [(table key)]". Measures: "Migrated from Tableau: {original_formula} | DAX: {expression}". Explicit Tableau descriptions (`desc` attribute) take priority when present.
- **Copilot annotations**: `Copilot_DateTable = true` on Calendar table. `Copilot_Hidden = true` on technical columns (ending in ID, _id, _key, _sk, _fk, _pk). `Copilot_TableDescription` annotation on every table.
- **Linguistic schema depth**: CamelCase splitting ("OrderDate" → "Order Date"), underscore humanization ("customer_name" → "customer name"), plus Tableau captions, aliases, and descriptions as Q&A synonyms.
- **dataCategory**: Tableau semantic-role mapping → City, Latitude, Longitude, StateOrProvince, PostalCode, Country, County
- **isHidden**: columns hidden in Tableau → hidden in PBI
- **displayFolder**: Dimensions, Measures, Time Intelligence, Flags, Calculations, Groups, Sets, Bins
- **sortByColumn**: Calendar MonthName→Month, DayName→DayOfWeek (prevents alphabetical month sorting)
- **isKey**: Calendar Date column marked as table key
- **Hierarchies**: Tableau drill-paths → BIM hierarchies with levels
- **Sets**: → M-based boolean calculated columns (IN expression), with DAX fallback for cross-table refs
- **Groups**: → M-based SWITCH calculated columns (values→groups mapping), with DAX fallback
- **Bins**: → M-based FLOOR calculated columns (source, size), with DAX fallback
- **Calculation groups**: Tableau param-swap actions → PBI Calculation Group tables with CALCULATE(SELECTEDMEASURE())
- **Field parameters**: Tableau dimension-switching params → PBI Field Parameter tables with NAMEOF()
- **M-based calculated columns**: DAX calc column expressions converted to Power Query M Table.AddColumn steps via `_dax_to_m_expression()` converter — supports IF, SWITCH, UPPER/LOWER/TRIM/LEN/LEFT/RIGHT/MID, ISBLANK, INT/VALUE, CONCATENATE, IN, &, arithmetic; falls back to DAX for cross-table references (RELATED/LOOKUPVALUE)
- **Perspectives**: auto-generated "Full Model" perspective referencing all tables (`perspectives.tmdl`)
- **Cultures**: culture TMDL file with linguistic metadata for non-en-US locales (`cultures/{locale}.tmdl`)
- **Multi-language cultures**: `--languages fr-FR,de-DE` generates multiple culture TMDL files with translated display folders (Dimensions→Dimensionen, Measures→Mesures, etc.) and translated calendar column names
- **Tableau Pulse → PBI Goals**: `--goals` flag converts Tableau Pulse metric definitions to Power BI Goals/Scorecard JSON artifacts
- **Dynamic parameters**: Tableau 2024.3+ database-query-driven parameters → M partition with `Value.NativeQuery()` for dynamic parameter refresh
- **Hyper data loading**: `.hyper` files read via SQLite interface — column metadata + row data injected into M `#table()` expressions
- **SCRIPT_* → Python/R visuals**: `SCRIPT_BOOL/INT/REAL/STR` Tableau functions → PBI `scriptVisual` containers (Python or R) with script text and input columns
- **diagramLayout.json**: empty layout file — Power BI Desktop auto-fills on first open
- **Parameters**: Tableau parameters → PBI What-If parameter tables:
  - Range parameters (integer/real) → `GENERATESERIES(min, max, step)` table + `SELECTEDVALUE` measure
  - List parameters (string/boolean) → `DATATABLE` table + `SELECTEDVALUE` measure
  - Any-domain parameters (no values) → simple measure on main table with default value
  - Both XML formats supported: `<column[@param-domain-type]>` (classic) and `<parameters><parameter>` (modern)
  - Deduplication: old-format parameters that appear both as calculations and parameter tables are deduplicated
- **Date table**: auto-detection and generation if date columns are present
  - Uses a **Power Query M partition** (not DAX calculated) to generate the Calendar table — avoids "invalid column ID" errors when TMDL relationships reference columns inside calculated-table partitions
  - M expression: `List.Dates` + `Table.AddColumn` for Year, Month, Quarter, etc.
  - Auto-creates relationship: Calendar[Date] → fact_table[first_DateTime_column], `crossFilteringBehavior: oneDirection`
- **Relationships**: Smart cardinality detection using raw column count ratio:
  - Extraction handles both `[Table].[Column]` and bare `[Column]` join clause formats (infers table from child relation elements)
  - LEFT/INNER join + to-table < 70% of from-table columns → **manyToOne** (lookup)
  - LEFT/INNER join + to-table ≥ 70% of from-table columns → **manyToMany** (peer table)
  - FULL join → **manyToMany** (ambiguous direction)
  - manyToOne uses `RELATED()`, manyToMany uses `LOOKUPVALUE()`
  - **Cross-table inference** (Phase 10): when DAX measures, calc columns, or RLS roles reference `'TableName'[Column]` from another table but no relationship exists, the generator infers one by matching column names (exact, substring, prefix) and creates a manyToOne relationship
- **RLS Roles**: Tableau user filters → Power BI Row-Level Security:
  - `<user-filter>` elements → RLS role with `USERPRINCIPALNAME()` + inline OR-based DAX from actual user mappings
  - USERNAME()/FULLNAME() calculations → RLS role with converted DAX filter expression
    - If DAX references `'OtherTable'[Col]`, the `tablePermission` is placed on that table (not the main fact table) so RLS propagates via the relationship
  - ISMEMBEROF("group") → separate RLS role per group (assign Azure AD members)
  - USERDOMAIN() → empty string with comment (no DAX equivalent)
  - Output: `roles` array in BIM model, `roles.tmdl` file, `ref role` in `model.tmdl`
  - Migration notes preserved as `MigrationNote` annotations on each role

## Output Formats — PBIR Schemas

- report: `https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/2.0.0/schema.json`
- page: `https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.0.0/schema.json`
- visualContainer: `https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.5.0/schema.json`

## Development Rules

1. **No external dependencies** — everything uses Python standard library
2. **Deduplication** — tables are deduplicated in the extractor (`type="table"` filtering)
3. **Calculated columns vs measures** — 3-factor classification:
   - Has aggregation (SUM, COUNT...) → measure
   - No aggregation + has column references (needs row context) → calculated column
   - No aggregation + no column refs → measure (formula-only)
   - Literal-value measure references in calc columns are inlined
4. **RELATED()** — used for cross-table refs in manyToOne relationships only
5. **LOOKUPVALUE()** — used for cross-table refs in manyToMany relationships
6. **SUM(IF(...))** — converted to SUMX('table', IF(...)) (also AVG→AVERAGEX, etc.)
7. **MAKEPOINT** — ignored (no DAX equivalent)
8. **SemanticModel** — Power BI naming convention (not "Dataset")
9. **Apostrophes** — escaped in TMDL names (`'name'` → `''name''`)
10. **Single-line DAX formulas** — multi-line formulas are condensed
11. **Parameters** — two XML formats handled:
    - Old: `<column[@param-domain-type]>` (Tableau Desktop classic)
    - New: `<parameters><parameter>` (Tableau Desktop modern, e.g., Financial_Report)
    - `param_map` populated from both sources for DAX reference resolution
    - `[Parameters].[X]` → `[Caption]` (measure) or inlined literal (calc column)

## Best Practices

- Open the .pbip in Power BI Desktop to validate
- Check relationships in the Model view
- Compare Tableau visuals vs Power BI
- Refer to `docs/FAQ.md` for frequently asked questions

## Agent Architecture — 8-Agent Specialization Model

This project uses an **8-agent specialization model** with scoped domain knowledge and file ownership.

See `docs/AGENTS.md` for the full architecture diagram, data flow, and handoff protocol.

### Agent Summary

| Agent | Scope | Key Files |
|-------|-------|-----------|
| **@orchestrator** | Pipeline, CLI, batch, wizard | `migrate.py`, `import_to_powerbi.py`, `wizard.py`, `progress.py`, `api_server.py` |
| **@extractor** | Tableau XML parsing, Hyper, Prep, Server API | `tableau_export/*.py` |
| **@converter** | Tableau→DAX (180+), Power Query M (43 transforms) | `dax_converter.py`, `m_query_builder.py` |
| **@generator** | TMDL, PBIR v4.0, visuals, Calendar, RLS | `tmdl_generator.py`, `pbip_generator.py`, `visual_generator.py` |
| **@assessor** | Readiness scoring, strategy, diff reports | `assessment.py`, `server_assessment.py`, `strategy_advisor.py`, `schema_drift.py` |
| **@merger** | Shared semantic model, fingerprint matching | `shared_model.py`, `merge_config.py` |
| **@deployer** | Fabric/PBI deployment, auth, gateway | `deploy/*.py`, `gateway_config.py`, `telemetry.py` |
| **@tester** | Tests (6,819+), coverage, regression | `tests/*.py` |

### Rules

- **One owner per file** — only the owning agent modifies each source file
- **Read access is universal** — any agent can read any file for context
- **Tester is cross-cutting** — reads all source, writes only to `tests/`
- **Default agent** handles multi-domain tasks, docs, git, sprint planning
- **Roadmap**: See `docs/ROADMAP.md` for v22–v28 per-agent sprint assignments (Sprints 76–117)

### Agent Definitions

All agent files live in `.github/agents/`:
- `shared.instructions.md` — base rules all agents inherit
- `{name}.agent.md` — per-agent specialization (8 files)
