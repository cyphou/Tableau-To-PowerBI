# Changelog

## v3.5.0 — March 2026

### Full Gap Implementation Sprint — DAX, Extraction, Generation, Docs, CI/CD (Phase 13)

Comprehensive implementation of all items identified in the gap analysis (sessions 8-9).

#### DAX Converter Fixes (`tableau_export/dax_converter.py`)
- **CORR / COVAR / COVARP**: Statistical functions now fully converted (not just passed through)
- **LOD balanced braces**: `{FIXED ...}` expressions with nested braces now parsed correctly
- **ATTR → SELECTEDVALUE**: `ATTR([col])` converted to `SELECTEDVALUE('Table'[col])` instead of leaving as-is
- **DATEPARSE → FORMAT**: `DATEPARSE(fmt, expr)` now mapped to `FORMAT(expr, fmt)`
- **MAKEDATE / MAKEDATETIME / MAKETIME**: Proper DAX equivalents (`DATE()`, `DATE()+TIME()`, `TIME()`)

#### Extraction Enhancements (`tableau_export/extract_tableau_data.py`)
- **Datasource filters**: Extract-level filters baked into connections now extracted and emitted as report-level filters
- **Reference bands**: Reference band detection from worksheet XML (in addition to existing reference lines)
- **Number format patterns**: Tableau custom number formats extracted and converted to PBI `formatString`

#### Generation Enhancements
- **Semantic TMDL validation** (`powerbi_import/validator.py`): DAX syntax checks (balanced parentheses/quotes, known functions) on measures and calculated columns
- **Slicer type variety** (`powerbi_import/pbip_generator.py`): Dropdown, list, between (range), and relative date slicer modes based on filter control type
- **Drill-through pages** (`powerbi_import/pbip_generator.py`): Worksheets with drill-through filters generate `pageType: "Drillthrough"` pages with target filter fields
- **Calendar customization**: `--calendar-start YEAR` and `--calendar-end YEAR` CLI flags for date table range
- **Culture/locale config**: `--culture LOCALE` CLI flag generates locale-specific `cultures/{locale}.tmdl`

#### Configuration & Infrastructure
- **Settings validation** (`powerbi_import/config/settings.py`): `validate()` method checks required fields, UUID format, URL format
- **`.env.example`**: Template for all environment variables with descriptions
- **`--dry-run`**: Preview migration stats without writing files
- **5-stage CI/CD pipeline**: lint+ruff → test → strict validate+twbx → staging deploy → production deploy

#### Documentation (6 new files)
- **`docs/ARCHITECTURE.md`**: Pipeline overview with ASCII + Mermaid diagrams, module tables, TMDL phases
- **`docs/KNOWN_LIMITATIONS.md`**: Categorized list of current limitations with workarounds
- **`docs/MIGRATION_CHECKLIST.md`**: Step-by-step pre/during/post migration checklist
- **`docs/DEPLOYMENT_GUIDE.md`**: Fabric deployment setup (Service Principal, env config, CI/CD)
- **`docs/TABLEAU_VERSION_COMPATIBILITY.md`**: Version-specific feature support matrix
- **`CONTRIBUTING.md`**: Development setup, coding standards, PR workflow

#### Tests
- **`tests/test_feature_gaps.py`**: 44 tests for feature gap coverage (LOD, parameters, RLS, etc.)
- **`tests/test_gap_implementations.py`**: 50 tests for all gap implementations (DAX fixes, validation, config)
- **Total: 717 tests, 0 failures, 2 skipped** (up from 500 in v3.4.0)

---

## v3.4.0 — February 2026

### QlikToPowerBI Feature Parity — Infrastructure & Visual Generator (Phase 12)

Ported remaining infrastructure and visual generator features from QlikToPowerBI to reach full feature parity.

#### CLI Enhancements (`migrate.py`)
- **`--output-dir DIR`**: Specify custom output directory for generated .pbip projects
- **`--verbose` / `-v`**: Enable verbose console logging (DEBUG level)
- **`--log-file FILE`**: Write logs to a file
- **`--batch DIR`**: Batch-migrate all .twb/.twbx files in a directory
- **`--skip-conversion`**: Skip extraction and run generation only (re-use existing JSONs)
- **Structured logging**: `setup_logging()` function with configurable log levels and handlers

#### Visual Generator Enhancements (`powerbi_import/visual_generator.py`)
- **60+ visual type mappings**: Comprehensive `VISUAL_TYPE_MAP` covering all Tableau mark types
- **VISUAL_DATA_ROLES**: Per-visual-type data role definitions (dimension/measure role names)
- **PBIR-native config templates**: 30+ visual types with proper PBIR expression objects (not plain booleans)
- **`build_query_state()`**: Role-based query projections using data roles, aggregation functions, and measure lookup
- **Slicer sync groups**: `syncGroup` property on slicer containers for cross-page slicer synchronization
- **Cross-filtering disable**: `filterConfig.disabled` for visuals that should not participate in cross-filtering
- **Action button navigation**: PageNavigation and WebUrl action types for button visuals
- **TopN visual filters**: Visual-level TopN and categorical filter construction
- **Sort state migration**: `sortDefinition` with ascending/descending direction in query state
- **Reference lines**: Tableau reference lines → constant line objects on value axis
- **Conditional formatting**: Color-by-measure and color-by-dimension modes → dataPoint objects

#### Artifact Validation (`powerbi_import/validator.py`)
- **`ArtifactValidator`** class with static validation methods
- **`validate_project()`**: Full .pbip project validation — checks .pbip file, Report dir (report.json, definition.pbir, page/visual JSONs), SemanticModel dir (model.tmdl, table TMDLs)
- **`validate_directory()`**: Batch-validate all projects in a directory
- **`validate_tmdl_file()`**: TMDL structure validation (model.tmdl starts with "model Model")

#### Fabric Deployment Layer (new modules)
- **`powerbi_import/auth.py`**: Azure AD authentication — Service Principal (ClientSecretCredential) and Managed Identity (DefaultAzureCredential) via optional `azure-identity`
- **`powerbi_import/client.py`**: Fabric REST API client — auto-detects `requests` library with retry strategy (429/5xx backoff), falls back to `urllib` (stdlib)
- **`powerbi_import/deployer.py`**: Deployment orchestrator — deploy datasets, reports, and batch directories; overwrite support; item search
- **`powerbi_import/utils.py`**: `DeploymentReport` (pass/fail tracking, JSON export) and `ArtifactCache` (metadata cache for incremental deployment)
- **`powerbi_import/config/settings.py`**: Centralized config via env vars (FABRIC_WORKSPACE_ID, FABRIC_TENANT_ID, etc.) with optional pydantic-settings support
- **`powerbi_import/config/environments.py`**: Per-environment configs (development/staging/production) with log levels, timeouts, retries, approval gates

#### CI/CD Pipeline
- **`.github/workflows/ci.yml`**: 4-stage GitHub Actions pipeline (lint → test → validate → deploy)
- Multi-Python matrix testing (3.9–3.12)
- Sample migration validation with artifact checker
- Production deployment to Fabric workspace via secrets

#### Tests
- **`tests/test_visual_generator.py`**: 67 tests covering visual type mapping, data roles, config templates, container creation, slicer sync, cross-filtering, action buttons, TopN filters, sort state, reference lines, query state builder
- **`tests/test_infrastructure.py`**: 34 tests covering validator, utils, config, auth, client, deployer, CLI extensions
- **Total: 500 tests, 0 failures, 2 skipped**

---

## v3.3.0 — February 2026

### Feature Parity with QlikToPowerBI (Phase 11)

Ported missing features from the QlikToPowerBI v3.0.0 project to reach feature parity.

#### Semantic Model Enhancements
- **sortByColumn on Calendar**: MonthName sorted by Month, DayName sorted by DayOfWeek — prevents alphabetical month ordering in visuals
- **sortByColumn and isKey** property support in `_write_column()` for all column types (physical and calculated)
- **Perspectives**: auto-generated "Full Model" perspective referencing all tables (`perspectives.tmdl`, `ref perspective` in model.tmdl)
- **Cultures/translations**: culture TMDL file with linguistic metadata for non-en-US locales (`cultures/{locale}.tmdl`, `ref culture` in model.tmdl)
- **diagramLayout.json**: empty diagram layout file — Power BI Desktop auto-fills on first open

#### Report Enhancements
- **Custom theme generation**: extracts dashboard background/text colors from Tableau and generates a PBI theme JSON (`RegisteredResources/TableauMigrationTheme.json`) with dataColors, textClasses (callout/title/header/label), and visualStyles
- **Conditional formatting**: quantitative color encoding on marks → PBI dataPoint gradient (min/max color rules)
- **Reference lines**: Tableau reference lines → PBI constant lines on valueAxis (dashed style, labeled)
- **Tooltip pages**: worksheets with `viz_in_tooltip` flag → PBI Tooltip pages (480×320, `pageType: Tooltip`)

#### Migration Report
- **MigrationStats class** (`migrate.py`): tracks 30+ metrics across extraction, generation, and warnings
- **Enhanced extraction summary**: counts for all 14 object types (worksheets, dashboards, datasources, calculations, parameters, filters, stories, actions, sets, groups, bins, hierarchies, sort_orders, aliases)
- **Enhanced generation summary**: tables, relationships, measures, pages, visuals, theme applied, RLS roles
- **Improved migration metadata**: `migration_metadata.json` now includes full object counts and generated output stats

## v3.2.0 — February 2026

### Tableau Prep Flow Parser (.tfl/.tflx) — Phase 10

- **Tableau Prep flow parser** (`tableau_export/prep_flow_parser.py`, ~900 lines):
  - Reads `.tfl` (JSON) and `.tflx` (ZIP→JSON) Tableau Prep flow files
  - DAG traversal via topological sort (Kahn's algorithm) for correct step ordering
  - Converts all step types to Power Query M expressions using existing transform generators
- **Supported Prep step types**:
  - **Input**: LoadCsv, LoadExcel, LoadSql, LoadJson, LoadHyper (16 connector types mapped)
  - **Clean (SuperTransform)**: RenameColumn (batched), RemoveColumn, DuplicateColumn, ChangeColumnType, FilterOperation, FilterValues, FilterRange, ReplaceValues, ReplaceNulls, SplitColumn, MergeColumns, AddColumn, CleanOperation (trim/upper/lower/proper), FillValues, GroupReplace, ConditionalColumn
  - **Aggregate**: GROUP BY with SUM/AVG/COUNT/COUNTD/MIN/MAX/MEDIAN/STDEV
  - **Join**: inner/left/right/full/leftOnly/rightOnly with auto-expand of right-table fields
  - **Union**: multi-input table combine
  - **Pivot**: columnsToRows (unpivot), rowsToColumns (pivot)
  - **Output**: PublishExtract, SaveToFile, SaveToDatabase
- **Prep expression converter**: Tableau Prep calc syntax → Power Query M (IF/THEN/ELSE, AND/OR/NOT, string functions, NULL handling, operators)
- **`--prep` CLI flag** on `migrate.py`: `python migrate.py workbook.twb --prep flow.tfl`
  - Step 1b merges Prep flow M queries into TWB datasources before generation
  - Matching by table name: Prep outputs replace TWB source queries with transformation-enriched M
  - Unmatched Prep outputs added as standalone tables in the semantic model
- **`inject_m_steps` improved**: now handles repeated calls correctly (strips previous Result terminators)
- **Sample flow**: `examples/tableau_samples/Sales_Prep_Flow.tfl` — Input→Clean→Join→Aggregate→Output pipeline

### Bug Fix
- Fixed `!=` operator not converting to `<>` in DAX expressions (Enterprise_Sales)

## v3.1.0 — February 2026

### Tableau Prep Transformations → Power Query M (Phase 9)

- **165 Tableau Prep operation mappings**: complete reference doc (`docs/TABLEAU_PREP_TO_POWERQUERY_REFERENCE.md`)
  - 18 categories: Input Steps, Clean-Columns, Clean-Values, Filter, Calculated Fields, Aggregate, Pivot, Join, Union, Reshape, String/Date/Numeric/Logic/Conversion Functions, Script, Output, TWB Embedded
  - 4 complete M query patterns (Clean & Filter, Join & Aggregate, Pivot, Wildcard Union)
- **40+ Power Query M transformation generators** in `m_query_builder.py`:
  - Column ops: rename, remove, select, duplicate, reorder, split, merge
  - Value ops: replace, replace nulls, trim, clean, upper/lower/proper, fill down/up
  - Filter ops: filter values, exclude, range, nulls, contains, distinct, top N
  - Aggregate: group by with sum/avg/count/countd/min/max/median/stdev
  - Pivot: unpivot, unpivot other columns, pivot
  - Join: inner/left/right/full/leftanti/rightanti with auto-expand
  - Union: append tables, wildcard union (folder source)
  - Reshape: sort, transpose, add index, skip/remove rows, promote/demote headers
  - Calculated: add custom column, conditional column
- **Chainable step injection**: `inject_m_steps()` inserts transform steps into any M query with `{prev}` placeholder pattern
- **TWB-embedded transforms auto-detected**: column renames from Tableau captions are now injected as `Table.RenameColumns` M steps in generated queries (visible in Enterprise_Sales output)

## v3.0.0 — February 2026

### Visual & Relationship Expansion (Phase 8)

- **60+ Tableau visual type mappings**: expanded mark→visual mapping from 14 to 60+ types
  - Covers all Tableau mark types: bar, line, area, pie, donut, scatter, treemap, map, filled map, gauge, KPI, box plot, waterfall, funnel, word cloud, combo charts, matrix, decomposition tree, and more
  - Visual config templates expanded from 7 to 30+ in `visual_generator.py`
  - Query state building expanded to handle gauge, KPI, card, pie/donut/funnel, combo, waterfall, box plot role assignments
- **Relationship extraction fix**: `datasource_extractor.py` now handles bare `[Column]` references in join clauses
  - Tableau nested joins often use `[column]` without table prefix on the left side
  - New logic infers table from child `<relation>` elements (including nested joins)
  - Manufacturing_IoT now correctly extracts 3 relationships (was only 1 Calendar auto-generated)
- **8 sample workbooks**: all migrate successfully (Superstore_Sales, HR_Analytics, Financial_Report, BigQuery_Analytics, Manufacturing_IoT, Enterprise_Sales, Marketing_Campaign, Security_Test)

### Reference Documentation (Phase 7)

- **172 DAX function mappings**: complete Tableau→DAX conversion reference (`docs/TABLEAU_TO_DAX_REFERENCE.md`)
- **108 Power Query property mappings**: Tableau connection→M query reference (`docs/TABLEAU_TO_POWERQUERY_REFERENCE.md`)
- **26 connector types** in `m_query_builder.py`: Excel, CSV, SQL Server, PostgreSQL, BigQuery, Oracle, MySQL, Snowflake, GeoJSON, Teradata, SAP HANA, SAP BW, Redshift, Databricks, Spark, Azure SQL/Synapse, Google Sheets, SharePoint, JSON, XML, PDF, Salesforce, Web, and more

## v2.0.0 — February 2026

### Complete pipeline overhaul

- **PBIR v4.0 format**: `.pbip` projects compliant with Power BI Desktop December 2025 format
  - Schemas: `report/3.1.0`, `page/2.0.0`, `visualContainer/2.5.0`
  - SemanticModel in TMDL format (Tabular Model Definition Language)
- **TMDL model**: `database.tmdl`, `model.tmdl`, `relationships.tmdl`, `tables/*.tmdl`
- **Enhanced extractor** (`enhanced_datasource_extractor.py`):
  - Per-table connections (Excel, CSV, GeoJSON, SQL Server, PostgreSQL)
  - Table deduplication (eliminates duplicates and false union tables)
  - Empty datasource filtering
- **Contextual DAX conversion**:
  - Resolution of `[Calculation_xxx]` to readable captions
  - Resolution of `[Parameters].[Parameter X]` to parameter names
  - `ISNULL` → `ISBLANK`, `CONTAINS` → `CONTAINSSTRING`, `ASCII` → `UNICODE`
  - `IF/THEN/ELSEIF/ELSE/END` → nested `IF()`
  - `==` → `=`, `or`/`and` → `||`/`&&`, `+` strings → `&`
- **Calculated columns**: calculations with `role=dimension` become calculated columns (row-level)
  - Automatic `RELATED()` for columns from related tables
  - Parameter values inlined in calculated columns
- **Column names preserved**: double spaces, special characters (`§`, `€`, `)`) kept intact
- **`MAKEPOINT()`**: ignored (no DAX equivalent, lat/lon used directly)

### Cleanup

- Removed obsolete migration reports/logs/test results
- Removed resolved historical documentation
- Documentation reorganization
- `requirements.txt`: no more external dependencies

## v1.0.0 — February 2026

### Initial version

- Extraction of Tableau objects (worksheets, dashboards, datasources, calculations, parameters, filters, stories)
- Per-object-type converters (`conversion/`)
- Basic `.pbip` project generation
- Main script `migrate.py` with 4 steps
- Documentation and examples
