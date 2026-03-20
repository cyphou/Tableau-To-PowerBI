# Changelog

## v21.0.0 — Interactive Migration, Observability & Test Depth

### Sprint 72 — Notebook-Based Interactive Migration ✅
- **MigrationSession API** (`notebook_api.py`): New interactive migration API — `load()`, `assess()`, `preview_dax()`, `list_approximated()`, `edit_dax()`, `clear_dax_override()`, `preview_m()`, `preview_visuals()`, `override_visual_type()`, `configure()`, `generate()`, `validate()`, `deploy()`
- **DAX override persistence**: Edit/clear overrides reflected in previews, applied at generation time
- **Visual type override**: Override any worksheet's PBI visual mapping before generation
- **Jupyter notebook generation**: `generate_notebook()` creates 8-step .ipynb (load→assess→DAX preview→M preview→visual preview→generate→validate→deploy)
- **35 new tests** in `test_notebook_api.py`

### Sprint 73 — Scheduled Refresh & Subscription Migration ✅
- **Refresh generator** (`refresh_generator.py`): Converts Tableau Server extract-refresh schedules to PBI refresh config JSON — frequency mapping (Hourly→Daily with Pro/Premium warnings), time deduplication, max 8 time slots for Pro, weekly day mapping
- **Subscription config**: Tableau email subscriptions → PBI subscription JSON with recipient, frequency, licensing notes
- **Server client extensions** (`server_client.py`): `get_workbook_extract_tasks(workbook_id)` and `get_workbook_subscriptions(workbook_id)` — per-workbook schedule/subscription extraction via REST API
- **PBI deployer extension** (`pbi_deployer.py`): `deploy_refresh_schedule(dataset_id, refresh_config)` — configures scheduled refresh via PBI REST API PATCH
- **`--migrate-schedules` CLI flag**: Extract Tableau refresh schedules and generate `refresh_config.json` in the output project directory
- **38 new tests** in `test_refresh_generator.py`

### Sprint 74 — Migration Observability Dashboard ✅
- **Telemetry v2** (`telemetry.py`): `TELEMETRY_VERSION=2`, new `record_event(event_type, **data)` method for per-workbook, per-visual, and per-measure granular event logging; backward-compatible with v1 stats/errors
- **Interactive observability dashboard** (`telemetry_dashboard.py`): Complete rewrite — 4-tab layout (Overview, Portfolio, Bottlenecks, Telemetry), JavaScript interactivity (column sort, text search, date filter), JSONL telemetry integration, portfolio progress tracker with completion bar, bottleneck analyzer
- **JSONL telemetry loading**: `_load_telemetry_events()` reads `~/.ttpbi_telemetry.json` for session-level drill-down
- **Bottleneck analysis**: `_analyze_bottlenecks()` identifies partial/failed items and error categories sorted by impact
- **Portfolio progress**: `_compute_portfolio_progress()` classifies workbooks as completed (≥80% fidelity), partial, or pending
- **28 new tests** in `test_observability.py`

### Sprint 75 — Test Depth, Legacy Cleanup & v21.0.0 Release ✅
- **DAX test expansion**: 86→176 tests covering trig functions, expanded text (ASCII→UNICODE, MID, REPLACE→SUBSTITUTE, SPACE→REPT, CHAR→UNICHAR), expanded date (DATETRUNC quarter/month, DATEPART all units, MAKEDATE), stats (STDEVP, VARP, PERCENTILE, CORR, COVAR), converter functions (ATTR, ENDSWITH, STARTSWITH, PROPER, SPLIT, FIND, ISDATE, DATEPARSE), table calcs (RUNNING_COUNT/MAX/MIN, RANK_DENSE, WINDOW_AVG/MAX/MIN, INDEX, FIRST, LAST, SIZE, TOTAL), spatial, REGEXP, SCRIPT_, security, AGG(IF), output quality
- **M connector test expansion**: 114→148 tests covering 32 additional connectors (Oracle, Snowflake, Teradata, SAP HANA, Redshift, Databricks, Spark, Azure SQL, Synapse, Google Sheets, SharePoint, JSON, XML, PDF, Salesforce, Web, OData, Azure Blob, Vertica, Impala, Presto/Trino, Fabric Lakehouse, Dataverse, MongoDB, Cosmos DB, Athena, DB2, Hyper, Hive/HDInsight, Google Analytics, SAP BW, GeoJSON)
- **Version bump**: 19.0.0 → 21.0.0 (pyproject.toml + `__init__.py`)
- **Overall: 5,024+ tests**, 0 failures

## v19.0.0 — Lineage, Multi-Tenant Deployment & Performance

### Sprint 65 — Lineage, Multi-Tenant, Performance & v19.0.0 Release ✅
- **Lineage metadata injection** (`shared_model.py`): Every merged artifact (tables, calculations, parameters, hierarchies, relationships, calc groups, field parameters, perspectives, cultures, goals) now tagged with `_source_workbooks: List[str]` and `_merge_action: str` (`deduplicated`/`namespaced`/`unique`/`unioned`/`first-wins`); `extract_lineage(merged)` function returns structured lineage records for all artifact types
- **TMDL lineage annotations** (`tmdl_generator.py`): `annotation MigrationSource = ["WB1", "WB2"]` and `annotation MergeAction = deduplicated` written on tables and measures; lineage metadata propagated through `_build_table()` and measure creation pipeline
- **Lineage HTML report** (`merge_report_html.py`): New "Lineage" section with Sankey-style flow diagram (workbooks → merge actions → artifact types) and sortable detail table; `_build_lineage_section()` with `_ACTION_STYLE` color-coding for merge actions
- **Custom SQL fingerprinting** (`shared_model.py`): `build_table_fingerprints()` extended to handle custom SQL tables — tables with `custom_sql` or `query` field fingerprinted as `_custom_sql` schema with normalized SQL hash; identical queries across workbooks become merge candidates
- **Multi-tenant deployment** (`deploy/multi_tenant.py`): New module with `TenantConfig`, `MultiTenantConfig` (validate/load/save JSON), `_apply_connection_overrides()` (template substitution: `${TENANT_SERVER}`, `${TENANT_DATABASE}` in .tmdl/.m/.json/.pbir files), `deploy_multi_tenant()` orchestrator with per-tenant results; `--multi-tenant CONFIG_FILE` CLI flag
- **Live connection byConnection** (`thin_report_generator.py`): `--live-connection WORKSPACE_ID/MODEL_NAME` CLI flag; thin reports wired via `byConnection` reference with `powerbi://api.powerbi.com/v1.0/myorg/{workspace_id}` connection string instead of `byPath`
- **Fingerprint hash cache** (`global_assessment.py`): Pre-computes fingerprints in `_fingerprint_cache` dict before pairwise loop; `_find_shared_table_names_cached()` operates on pre-computed dicts; O(n) fingerprinting instead of O(n²)
- **E2E integration tests** (`test_merge_integration.py`): 15 tests using 3 real sample workbooks (Superstore_Sales, Financial_Report, Marketing_Campaign) — extraction validation, assessment scoring, merge pipeline, lineage metadata, TMDL generation, thin reports, validation report, merge manifest
- **Benchmark test suite** (`test_merge_performance.py`): 10 synthetic benchmarks (10/25/50/100 workbooks × 3-10 tables), assessment scaling, fingerprint cache speedup comparison, lineage at scale, merge manifest at scale; gated by `RUN_BENCHMARKS=1` env var
- **100 new tests** across 5 test files: `test_merge_lineage.py` (22), `test_multi_tenant.py` (31), `test_sql_fingerprint.py` (22), `test_merge_integration.py` (15), `test_merge_performance.py` (10)
- **Overall: 4,923 tests** (4,913 + 10 benchmark), 0 failures

## v18.0.0 — Advanced Merge Intelligence & Enterprise Merge Workflows

### Sprint 64 — Incremental Merge & Add-to-Model Workflow ✅
- **MergeManifest** (`shared_model.py`): `MergeManifest` dataclass with `save()`/`load()`/`from_dict()`/`to_dict()` — tracks workbook sources (name, path, SHA-256 hash), per-table fingerprints, artifact counts (tables, measures, relationships, RLS roles, parameters), validation score, merge score, timestamp; `build_merge_manifest()` populates from merge results with exclusive table detection
- **TMDL reverse-engineering** (`shared_model.py`): `load_existing_model(model_dir)` — parses `.tmdl` files into `converted_objects`-compatible dict; handles `table`, `column` (physical + calculated), `measure` (single + multi-line), `hierarchy` (with levels), `partition`, `relationship`, `role` (with tablePermissions); `_find_definition_dir()` resolves from project dir, SemanticModel dir, or definition dir
- **`--add-to-model`** (`migrate.py`, `shared_model.py`): `add_to_model(model_dir, new_extracted, wb_name)` — loads existing model via manifest + TMDL, performs incremental merge, updates manifest with new workbook entry, regenerates TMDL + thin report; duplicate detection with `force=True` override; `_run_add_to_model()` CLI handler with extraction + merge + generation pipeline
- **`--remove-from-model`** (`migrate.py`, `shared_model.py`): `remove_from_model(model_dir, wb_name)` — identifies exclusive tables (not shared with other workbooks), removes them from model, cleans up relationships involving removed tables, removes measures owned by workbook; shared tables preserved; `_run_remove_from_model()` CLI handler with TMDL regeneration + thin report cleanup
- **Manifest diff** (`merge_assessment.py`): `diff_manifests(old, new)` — compares two manifests returning added/removed tables, measures, workbooks, relationship count changes, config changes; accepts both dict and `MergeManifest` objects
- **Manifest auto-save** (`import_to_powerbi.py`): `import_shared_model()` now writes `merge_manifest.json` after merge completion; `workbook_paths` parameter threaded through pipeline for file hash tracking
- **46 new tests** in `test_incremental_merge.py` across 10 test classes: MergeManifest (6), build_merge_manifest (2), TMDL parsing (10), load_existing_model (7), add_to_model (4), remove_from_model (4), diff_manifests (5), find_definition_dir (4), idempotent re-add (1), file_hash (2), manifest save (1), TMDL duplicate column fix (5 in test_tmdl_generator.py from prior commit)
- **Overall: 4,813 tests**, 0 failures

### Sprint 63 — Deploy Hardening & Fabric Reliability ✅
- **Workspace permission pre-flight** (`bundle_deployer.py`): `check_workspace_permissions()` — verifies workspace exists and principal has Contributor+ role before deployment; blocks on Viewer-only or network errors
- **Name conflict detection** (`bundle_deployer.py`): `detect_conflicts(model_name, report_names)` — queries workspace items for collisions; `overwrite=True` parameter to proceed despite conflicts
- **Rollback on failure** (`bundle_deployer.py`): `rollback(result)` — deletes deployed semantic model and reports when `enable_rollback=True` and any report deployment fails; per-artifact rollback status tracking
- **Post-deployment validation** (`bundle_deployer.py`): `validate_deployment(result)` — checks model deployment status and report binding state; appends validation results to `BundleDeploymentResult`
- **Refresh polling** (`bundle_deployer.py`): `poll_refresh(model_id, result)` — polls dataset refresh status until completion/failure/timeout; replaces fire-and-forget refresh pattern
- **Deployment manifest** (`deploy/utils.py`): `DeploymentManifest` class — tracks workspace_id, model/report IDs, source_hash, principal, version; save/load JSON for audit trail
- **BundleDeploymentResult extended**: Added `rollback_actions`, `validation`, `conflicts` fields with `to_dict()` serialization
- **28 new tests** in `test_deploy_hardening.py`: permissions (6), conflicts (5), rollback (4), validation (4), polling (3), manifest (2), integration (2), result fields (2)
- **Existing test fix** (`test_bundle_deployer.py`): `test_deploy_with_refresh` updated to mock `poll_refresh` — was causing 30-minute hang
- **Overall: 4,762 tests** (21 Hyper + 28 deploy + fix), 0 failures

### Hyper File Improvements ✅
- **Option A — tableauhyperapi integration** (`hyper_reader.py`): `_read_hyper_api()` — tries optional `tableauhyperapi` package first for full .hyper format support (v2+); graceful fallback to SQLite reader when package not installed
- **Option B — Multi-schema support** (`hyper_reader.py`): Enhanced `_read_hyper_sqlite()` with `_HYPER_SCHEMAS` loop — discovers tables across `Extract`, `public`, and `stg` schemas; proper quoted name handling for schema-qualified queries
- **Option C — Configurable row limit** (`hyper_reader.py`, `migrate.py`): `--hyper-rows N` CLI flag controls sample data extraction; `row_limit` parameter on `generate_m_for_hyper_table()` overrides default thresholds; wired through full pipeline: migrate.py → extract_tableau_data.py → hyper_reader.py
- **Option D — Metadata enrichment** (`hyper_reader.py`): `_compute_column_stats_sqlite()` with distinct_count/min/max per column; `get_hyper_metadata()` summary function with recommendations (DirectQuery for >10M rows, cardinality warnings); file metadata (size, modified date) included in output
- **3-tier reader chain**: tableauhyperapi → SQLite → header scan (documented in module docstring)
- **21 new tests** in `test_hyper_improvements.py`: API reader (3), multi-schema (3), configurable rows (6), metadata (7), format detection (2)

### Backward Compatibility Fix — PBI Desktop April 2025 (v2.142.928.0) ✅
- **Report schema downgrade** (`pbip_generator.py`): Downgraded report.json `$schema` from `3.1.0` to `2.0.0` — PBI Desktop April 2025 cannot resolve report schema 3.x
- **ThemeVersion format fix** (`pbip_generator.py`): Changed `reportVersionAtImport` from object `{visual, report, page}` (schema 3.x) to string `"5.55"` (schema 2.x) per Microsoft PBIR documentation
- **Custom theme type fix** (`pbip_generator.py`): Changed `themeCollection.customTheme.type` from `"CustomTheme"` to `"RegisteredResources"` to match schema 2.0.0 `ThemeResourcePackageType` enum
- **Validator updated** (`validator.py`): `VALID_REPORT_SCHEMAS` now expects `report/2.0.0/schema.json`
- **All code paths fixed**: `pbip_generator.py` (2 sites), `import_to_powerbi.py`, `validator.py`, `test_backlog.py`

### Sprint 55 — Post-Merge Safety: Cycle Detection, Column Type Validation & DAX Integrity ✅
- **Relationship cycle detection** (`shared_model.py`): `detect_merge_cycles()` — iterative DFS on merged relationship graph; detects 2-node, 3-node, self-loop, and multi-component cycles; supports both `from_table/to_table` and `left/right` relationship formats
- **Column type compatibility matrix** (`shared_model.py`): `check_type_compatibility()` — explicit matrix for all type pairs (`ok`/`warn`/`error`); `_TYPE_COMPAT` covers boolean, integer, int64, real, double, decimal, currency, datetime, string; safe promotions (int→real), warnings (custom types), errors (datetime↔boolean)
- **Column type history tracking** (`shared_model.py`): `_merge_columns_into()` now populates `_column_type_history` dict on tables during merge; `detect_type_conflicts()` scans history for incompatible promotions
- **DAX reference validator** (`shared_model.py`): `validate_merged_dax_references()` — scans all measures/calc columns for `'Table'[Column]` patterns; verifies every referenced table and column exists in merged model; provides closest-match suggestions via `_find_closest()` (Levenshtein-like)
- **RELATED/LOOKUPVALUE cardinality audit** (`shared_model.py`): `validate_dax_relationship_functions()` — verifies `RELATED()` calls have manyToOne relationships; `LOOKUPVALUE()` used for manyToMany; flags mismatches (no relationship, wrong cardinality)
- **Validation summary report** (`shared_model.py`): `generate_merge_validation_report()` — aggregates all checks into structured JSON: cycles, type warnings, DAX errors, cardinality mismatches, score (0–100), passed flag; integrated into `import_shared_model()` pipeline
- **`--strict-merge` CLI flag** (`migrate.py`): When set, any validation failure (cycles, type errors) blocks PBIP generation with exit code 1; without flag, validation is advisory (warnings printed, generation proceeds)
- **Pipeline integration** (`import_to_powerbi.py`): Post-merge validation runs automatically after `merge_semantic_models()` in Step 2a; prints per-check status with ✓/⚠/✗ icons; validation result included in return dict
- **57 new tests** in `test_merge_validation.py` across 8 test classes: cycle detection (9), type compatibility (8), type conflicts (5), DAX refs (9), cardinality audit (6), validation report (9), find_closest (5), edge cases (4), type history (3)
- **Overall: 4,331 tests**, 0 failures

### Sprint 54 — Artifact-Level Merge: Calculation Groups, Field Parameters, Perspectives & Cultures ✅
- **Hierarchy level-aware deduplication** (`shared_model.py`): Replaces shallow `_merge_list_by_name` for hierarchies — same name + same levels → deduplicate; same name + different levels → keep longest path; three-workbook scenarios correctly resolved
- **Calculation group merge** (`shared_model.py`): `_merge_calculation_groups()` — signature-based deduplication of calc-group-like parameters across workbooks; same items → deduplicate; different items → namespace as `CalcGroup (Workbook)`; `_calc_group_signature()` for item-level comparison
- **Field parameter merge** (`shared_model.py`): `_merge_field_parameters()` — same values → deduplicate; different values → union all column references (order-preserved, wb1 first); `_merged_from` tracking for multi-workbook provenance
- **Perspective merge** (`shared_model.py`): `_merge_perspectives()` — same name → union table references (sorted); different names → keep all; empty perspectives handled
- **Culture merge** (`shared_model.py`): `_merge_cultures()` — same locale → merge translations (first-seen wins per key); different locales → keep all; collects from `_cultures`, `culture` field, and `_languages` field; en-US default skipped
- **Goals/scorecard merge** (`shared_model.py`): `_merge_goals()` — same metric name + same measure → deduplicate; different measures → namespace as `Goal (Workbook)`; supports `metric_name`/`measure_name` fallback keys
- **`merge_semantic_models()` updated**: Now produces 6 new artifact keys: `_calculation_groups`, `_field_parameters`, `_perspectives`, `_cultures`, `_goals`, and enhanced `hierarchies`
- **55 new tests** in `test_merge_artifacts.py` across 10 test classes
- **Overall: 4,274 tests**, 0 failures

## v17.0.0 — Server Assessment & Merge Intelligence

### Sprint 53 — Documentation & Release ✅
- **CHANGELOG.md**: Full v17.0.0 release notes across 5 sprints (49–53)
- **Version bump**: 16.0.0 → 17.0.0 in `pyproject.toml` and `powerbi_import/__init__.py`
- **GAP_ANALYSIS.md updated**: v17.0.0 counts — 4,219 tests, 77 test files
- **KNOWN_LIMITATIONS.md updated**: v17.0.0 — VAR/VARP M approximation documented
- **copilot-instructions.md updated**: New modules (server_assessment, server_client v2), CLI flags, merge extensions
- **Overall: 4,219 tests**, 0 failures

### Sprint 52 — Extraction & DAX Gap Closure ✅
- **VAR/VARP in M query builder**: Added `var` and `varp` entries to `_M_AGG_MAP` (approximated via `List.StandardDeviation`)
- **Verified existing mappings**: INDEX→RANKX comment, LTRIM→TRIM, RTRIM→TRIM already implemented; nested LOD with `_find_lod_braces()` already handles innermost-first; `notInner→leftanti` in prep flow parser
- **8 new tests** in `test_extraction_gaps.py` validating M aggregation map, DAX conversions, and prep flow mappings
- **Overall: 4,219 tests**, 0 failures

### Sprint 51 — Semantic Model Merge Extensions ✅
- **Custom SQL fingerprinting** (`shared_model.py`): `_normalize_sql()`, `_hash_sql()`, `build_custom_sql_fingerprints()` — SHA-256 fingerprint-based deduplication of custom SQL tables across workbooks
- **Fuzzy table matching** (`shared_model.py`): `_normalize_table_name_fuzzy()`, `fuzzy_table_match()` — schema-strip, separator-fold, bigram Jaccard similarity scoring (0.0–1.0)
- **RLS conflict detection** (`shared_model.py`): `detect_rls_conflicts()` — finds overlapping RLS roles with divergent filter expressions across workbooks
- **Cross-workbook relationship suggestions** (`shared_model.py`): `suggest_cross_workbook_relationships()` — scans `_id`/`_key`/`_code` columns for matches, skips existing relationships, returns high/medium confidence
- **Merge preview** (`shared_model.py`): `merge_preview()` — dry-run merge returning assessment + RLS conflicts + relationship suggestions + action plan
- **HTML merge report** (`merge_assessment.py`): `generate_merge_html_report()` — full HTML dashboard with candidate table, measure conflict table, RLS conflict table, relationship suggestions
- **Enhanced field remapping** (`thin_report_generator.py`): `_remap_fields()` now handles list-type mark encodings, sort field remapping, action target field remapping
- **CLI flags** (`migrate.py`): `--merge-preview`, `--bulk-assess DIR`, `--server-assess`
- **40 new tests** in `test_merge_extensions.py` across 11 test classes
- **Overall: 4,219 tests**, 0 failures

### Sprint 50 — Server-Level Assessment Pipeline ✅
- **Server assessment module** (`server_assessment.py`, new): Enterprise portfolio assessment for Tableau Server or local workbook folders
- **Data classes**: `WorkbookReadiness` (GREEN/YELLOW/RED + complexity + effort), `MigrationWave` (wave_number, label, workbooks, total_effort), `ServerAssessment` (aggregated results + readiness_pct)
- **Complexity computation** (`_compute_complexity()`): 8-axis analysis — visuals, dashboards, calculations, tables, LOD expressions, table calcs, filters, actions
- **Effort estimation** (`_estimate_effort()`): Weighted hours — base 1.0h + 0.15h/visual + 0.2h/calc + 0.5h/LOD + 0.4h/table_calc + 0.3h/datasource + 0.1h/table
- **Migration wave planning** (`_build_migration_waves()`): Automatic grouping into Easy/Medium/Complex waves based on complexity score
- **HTML dashboard** (`generate_server_html_report()`): Executive report with pie chart, connector census, wave table, workbook detail grid
- **21 new tests** in `test_server_assessment.py` across 9 test classes
- **Overall: 4,219 tests**, 0 failures

### Sprint 49 — Tableau Server Client Enhancement ✅
- **Pagination** (`server_client.py`): `_paginated_get()` helper auto-handles Tableau REST API pagination metadata (`totalAvailable`, `pageNumber`, `pageSize`)
- **Existing methods upgraded**: `list_workbooks()`, `list_datasources()`, `list_projects()` now use paginated fetching
- **9 new endpoints**: `list_users()`, `list_groups()`, `list_views()`, `get_workbook_connections(workbook_id)`, `list_schedules()`, `get_site_info()`, `list_prep_flows()`, `download_prep_flow(flow_id, output_path)`, `get_server_summary()`
- **`get_server_summary()`**: Aggregates all counts (workbooks, datasources, users, groups, views, projects, prep flows) + site info in a single call
- **19 new tests** in `test_server_client_v2.py` across 13 test classes
- **Overall: 4,219 tests**, 0 failures

## v16.0.0 — Code Quality & Maintainability

### Sprint 48 — Documentation, API Docs & Release ✅
- **Auto-generated API docs** (`docs/generate_api_docs.py`): MODULES list expanded from 15 to 42 modules covering all source files (8 tableau + 26 powerbi + 8 deploy), with deploy section separator in index.html
- **GAP_ANALYSIS.md updated**: v16.0.0 counts — 4,131 tests, 73 test files, 118 visual map entries, 33 connectors, 43 M transforms, 9-category assessment, Windows/macOS/Linux CI matrix
- **KNOWN_LIMITATIONS.md updated**: v16.0.0 — OneDrive lock retry now documented, Windows paths limitation resolved
- **README.md updated**: Badges → v16.0.0, 4,131 tests, 180+ DAX, 33 connectors, 20 object types, 118 visuals; new v16 features section
- **copilot-instructions.md updated**: Test count, new modules (alerts_generator, visual_diff, comparison_report), 43 M transform generators
- **Version bump**: 15.0.0 → 16.0.0 in `pyproject.toml` and `powerbi_import/__init__.py`
- **Overall: 4,131 tests**, 0 failures

### Sprint 47 — Windows CI, Cross-Platform Hardening & Performance ✅
- **OneDrive lock retry** (`pbip_generator.py`): New `_rmtree_with_retry(path, attempts=3, delay=0.5)` helper with exponential backoff for stale directory cleanup — replaces bare `except (PermissionError, OSError): pass` blocks
- **Stale TMDL retry** (`tmdl_generator.py`): Stale `.tmdl` file removal now retries 3 times with 0.3s×2^n backoff on PermissionError, with `logger.debug`/`logger.warning` messages
- **Memory optimization** (`tmdl_generator.py`): After writing table TMDL files, column/measure/partition data is released from table dicts (only names and lightweight `_n_columns`/`_n_measures` counts preserved) — reduces peak memory for large workbooks (50+ tables)
- **Pre-computed stats** (`tmdl_generator.py`): `generate_tmdl()` now collects BIM symbols and stat counts *before* writing (and memory release), ensuring accurate stats despite post-write cleanup
- **Performance benchmarks** (`test_performance.py`): 2 new benchmark tests — `TestTmdl100MeasuresPerformance` (5 tables × 100 measures, threshold 10s) and `TestImportPipelinePerformance` (full 16-JSON pipeline, threshold 15s)
- **18 new tests** in `test_sprint47.py` across 7 test classes: retry logic (success, PermissionError, give-up), stale TMDL cleanup, path handling (os.path.join verification), Unicode filenames (French, Japanese), long paths, memory optimization, CI compatibility (no external deps, UTF-8, cross-platform paths)
- **Overall: 4,111 → 4,131 tests**, 0 failures

### Sprint 46 — New Features: Data Alerts, Visual Diff & Semantic Validation ✅
- **Data-driven alerts** (`alerts_generator.py`, new): Extracts alert conditions from Tableau parameters (threshold/alert/target keywords), calculations with IF/threshold patterns, and reference lines with target labels → generates PBI alert rules JSON with operator, threshold, frequency, measure
- **Visual diff report** (`visual_diff.py`, new): Side-by-side HTML report comparing Tableau visuals to PBI visuals — visual type mapping status (exact/approximate/unmapped), per-field coverage tracking, encoding gap detection (color, size, tooltip, label, detail, path), summary table with coverage percentages
- **Enhanced semantic validation** (`validator.py`): 3 new validation methods: `detect_circular_relationships()` (DFS cycle detection in relationship graph), `detect_orphan_tables()` (tables with no relationships and no DAX references, excluding Calendar/Date), `detect_unused_parameters()` (parameter tables whose measures are never referenced) — all integrated into `validate_project()`
- **Migration completeness scoring** (`migration_report.py`): `get_completeness_score()` method with per-category fidelity breakdown (weighted: calculation 30%, visual 25%, datasource 15%, relationship 10%, etc.), overall weighted score 0–100, letter grade (A/B/C/D/F), included in `to_dict()` and `print_summary()`
- **Connection string audit** (`assessment.py`): New `_check_connection_strings()` assessment category detecting sensitive credentials (passwords, tokens, API keys, bearer auth, basic auth) in datasource connection properties — 6 regex patterns, integrated as 9th category in `run_assessment()`
- **51 new tests** in `test_sprint46.py` across 12 test classes
- **Overall: 4,060 → 4,111 tests**, 0 failures

### Sprint 45 — CLI Refactoring & Function Decomposition ✅
- **`_build_argument_parser()`** decomposed into 9 focused helpers (`_add_source_args`, `_add_output_args`, `_add_batch_args`, `_add_migration_args`, `_add_report_args`, `_add_deploy_args`, `_add_server_args`, `_add_enterprise_args`, `_add_shared_model_args`) + 12-line dispatcher
- **`main()`** decomposed: single-file pipeline extracted into `_run_single_migration(args)` + 7 helper functions (`_print_single_migration_header`, `_init_telemetry`, `_finalize_telemetry`, `_run_incremental_merge`, `_run_goals_generation`, `_run_post_generation_reports`, `_run_deploy_to_pbi_service`)
- **`run_batch_migration()`**: batch summary printing extracted into `_print_batch_summary()`
- **`import_shared_model()`**: model-explorer report creation extracted into `_create_model_explorer_report()`, artifact saving extracted into `_save_shared_model_artifacts()`
- **`_build_visual_query()`**: shelf field classification extracted into `_classify_shelf_fields()`
- **31 new regression tests** in `test_cli_refactor.py` covering all extracted helpers
- **Overall: 4,029 → 4,060 tests**, 0 failures

### Sprint 44 — Silent Error Cleanup Phase 2 ✅
- Eliminated all 5 `except Exception: pass` blocks across migrate.py and deploy/
- Narrowed broad `except Exception` catches to specific types
- Added logging to bare-pass exception handlers
- Added `logger` to `m_query_builder.py`
- **33 new error-path tests** validating narrowed exception handling
- **Overall: 3,996 → 4,029 tests**, 0 failures

## v15.0.0 — Global Assessment & Fabric Bundle Deployment

### Sprint 43 — Fabric Bundle Deployment ✅
- **Bundle deployer** (`deploy/bundle_deployer.py`): New module for deploying shared semantic model projects as a Fabric bundle — discovers `.SemanticModel` + `.Report` artifacts, deploys model first, then each report with error isolation, rebinds reports to model, optional dataset refresh
- **`BundleDeploymentResult`**: Rich result object with per-artifact status, timing, JSON export, and console summary
- **`BundleDeployer`**: Orchestrator class — `discover_artifacts()`, `deploy_bundle()`, `_rebind_report()`, `_trigger_refresh()`, report filtering
- **`deploy_bundle_from_cli()`**: CLI entry point with auto-save of `deployment_report.json`
- **CLI flags**: `--deploy-bundle WORKSPACE_ID`, `--bundle-refresh`
- **Pipeline integration**: Auto-deploys after `--shared-model` migration; standalone mode with `--output-dir`
- **30 new tests** in `test_bundle_deployer.py` across 8 test classes
- **Overall: 3,958 → 3,988 tests**, 0 failures

### Sprint 42 — Global Assessment & Table Isolation ✅
- **Global assessment** (`global_assessment.py`): Cross-workbook merge analysis with pairwise scoring, BFS cluster detection, and interactive HTML report — executive summary, workbook inventory, N×N heatmap matrix, merge cluster cards with CLI commands, isolated workbooks section
- **CLI flag**: `--global-assess` with `--batch` directory support
- **Intelligent table isolation**: `_classify_unique_tables()` in `shared_model.py` — classifies unique tables as linked or isolated by checking relationships and key-column overlaps; isolated tables excluded from shared model
- **SemanticModel .pbip generation**: Model-explorer report pattern so shared models can be opened in PBI Desktop
- **25 + 8 new tests** in `test_global_assessment.py` and `test_shared_model_v2.py`
- **Documentation**: README.md updated with `--global-assess` examples and screenshot; `SHARED_SEMANTIC_MODEL_PLAN.md` Section 10 added
- **Overall: 3,925 → 3,958 tests**, 0 failures

---

## v14.0.0 — Shared Semantic Model v2 (Advanced Merge Features)

### Sprint 41 — Shared Semantic Model Enhancements ✅
- **Merge config save/load** (`merge_config.py`): Export/import merge decisions to JSON for reproducible migrations — `save_merge_config()`, `load_merge_config()`, `apply_merge_config()`, force-merge override, table/measure/parameter-level decisions
- **Visual field validation**: `validate_thin_report_fields()` detects orphaned columns, filters, and mark encodings in thin reports before generation — prevents broken visuals referencing missing fields
- **Column lineage annotations**: `build_column_lineage()` + `generate_lineage_annotations()` track which workbooks contributed each table and column — TMDL-ready annotation strings for provenance tracking
- **Measure expression risk analyzer**: `analyze_measure_risk()` with `MeasureRiskAssessment` dataclass — parses DAX to classify conflicts as low/medium/high risk based on aggregation type and column references
- **RLS role consolidation**: `consolidate_rls_roles()` + `merge_rls_roles()` with `RLSConsolidation` dataclass — deduplicates identical roles, merges different filters with OR logic, keeps unique roles
- **Cross-report navigation**: `build_cross_report_navigation()` auto-generates navigation button configs between thin reports within a shared model
- **Plugin merge hooks**: 3 new hooks on `PluginBase` — `on_merge_conflict()`, `on_merge_complete()`, `transform_merged_dax()` for extensible conflict resolution
- **Fabric deployment orchestration**: `deploy_shared_model()` on `FabricDeployer` — deploys SemanticModel first, then each thin report, with per-report error isolation
- **CLI flags**: `--merge-config FILE`, `--save-merge-config`
- **Pipeline integration**: All features wired into `import_shared_model()` — risk analysis, RLS consolidation, lineage tracking, field validation, navigation, config save/load
- **54 new tests** in `test_shared_model_v2.py` across 9 test classes
- **Overall: 3,871 → 3,925 tests**, 0 failures

---

## v13.0.0 — Shared Semantic Model (Multi-Workbook Merge)

### Sprint 40 — Shared Semantic Model Extension ✅
- **Shared semantic model**: Merge multiple Tableau workbooks into one shared Power BI semantic model with N thin reports
- **New modules**: `shared_model.py` (merge engine), `merge_assessment.py` (assessment reporter), `thin_report_generator.py` (thin report generator)
- **Merge engine**: Fingerprint-based table matching (SHA-256 hash of connection_type|server|database|schema|table), Jaccard similarity for column overlap, 4-dimension merge scoring (0–100)
- **Conflict resolution**: Measures — identical formula = deduplicate, different formula = namespace as `Measure (Workbook)`; Columns — union with wider type wins; Relationships — deduplicated by (from,to) key; Parameters — same logic as measures
- **Thin reports**: PBIR `definition.pbir` with `byPath` reference to `../SharedModel.SemanticModel`; each report gets its own pages/visuals from the original workbook
- **Merge assessment**: JSON + console report with table overlap analysis, measure/column/parameter conflicts, merge score with thresholds (≥60 = merge, 30–59 = partial, <30 = separate)
- **CLI flags**: `--shared-model WB [WB ...]`, `--model-name NAME`, `--assess-merge`, `--force-merge`
- **Batch support**: `--batch DIR --shared-model` auto-discovers and merges all .twb/.twbx in a directory
- **Modified modules**: `pbip_generator.py` (added `_generate_report_definition_content()`), `import_to_powerbi.py` (added `import_shared_model()`), `migrate.py` (CLI wiring + `run_shared_model_migration()`)
- **81 new tests** in `test_shared_model.py` across 19 test classes
- **Overall: 3,729 → 3,847 tests**, coverage maintained at **96.2%**

---

## v12.0.0 — Hardening, Coverage Push to 96%+

### Sprint 39 — Coverage Push dax_converter.py ✅
- **dax_converter.py**: 73.7% → **96.7%** (302 → 38 missed lines)
- **183 new tests** in `test_dax_converter_coverage_push.py` across 32 test classes
- Coverage areas: `_reverse_tableau_bracket_escape` body, federated prefix strip, CASE/WHEN→SWITCH parsing, `_extract_balanced_call`, REGEXP_MATCH (12 branches), REGEXP_EXTRACT (5 branches), REGEXP_EXTRACT_NTH (6 branches), REGEXP_REPLACE (6 branches), LOD expressions (FIXED/INCLUDE/EXCLUDE, no-dims, nested, AGG cleanup), window functions with frame bounds, WINDOW_CORR/COVAR/COVARP, RANK_DENSE/MODIFIED/PERCENTILE, RUNNING_COUNT/MAX/MIN, TOTAL, column resolution internals, AGG(IF/SWITCH)→AGGX, STDEV→STDEVX, `generate_combined_field_dax`, `detect_script_functions`, `_detect_script_language`, `has_script_functions`
- **Overall: 3,546 → 3,729 tests**, coverage 95.9% → **96.2%**

### Sprint 38 — Coverage Push tmdl_generator.py ✅
- **tmdl_generator.py**: 94.7% → **97.6%** (103 → 47 missed lines)
- **87 new tests** in `test_tmdl_coverage_push.py` across 25 test classes
- Coverage areas: `_extract_function_body`, `_dax_to_m_expression` (SWITCH/FLOOR/IN), `resolve_table_for_formula`, `_collect_semantic_context` (Unknown table, Parameters DS, date params, multi-table DS), `_create_and_validate_relationships`, calc classification (security funcs, inline literals, geo, descriptions), `_infer_cross_table_relationships`, type mismatch fixing, sets/groups/bins, date hierarchy skip, parameter tables, field parameters, RLS roles, format conversion, ambiguous path deactivation, quick table calc measures, TMDL file writing, culture translations, multi-language support
- **Overall: 3,459 → 3,546 tests**, coverage 95.4% → **95.9%**

### Sprint 37 — Silent Error Cleanup ✅
- **11 bare `pass` statements** in `except` blocks replaced with proper `logger.debug()`/`logger.warning()` across 5 files
- **1 exception type narrowed**: `except Exception` → `except (OSError, IndexError, ValueError)` in `telemetry.py`
- Files modified: `incremental.py`, `pbip_generator.py`, `telemetry.py`, `telemetry_dashboard.py`, `validator.py`
- All 3,459 tests pass after changes — zero regressions

---

## v11.0.0 — Coverage Push to 95% & README Overhaul

### Sprint 36 — README Overhaul & Release ✅
- **36.1: README badges**: Added CI, coverage (95.4%), tests (3,459), Python, license, and version badges.
- **36.2: README stats update**: Updated all stats from v9/v10 to v11 (3,459 tests, 62 test files, 95.4% coverage).
- **36.3: Test table refresh**: Added `test_extract_coverage.py` (75 tests) and `test_pbip_coverage_push.py` (42 tests), "+24 more" rollup row for remaining files.
- **36.4: Known limitations refresh**: Updated hyper data (now loaded), dynamic zone visibility (now bookmark-based), dynamic parameters (now M-based).
- **36.5: Version bump**: `pyproject.toml` and `powerbi_import/__init__.py` bumped from 10.0.0 → 11.0.0.

### Sprint 35 — Coverage Push (93.08% → 95.4%) ✅
- **35.1: test_extract_coverage.py** (75 tests): Coverage-push tests for `extract_tableau_data.py` — stories, actions, sets, groups, bins, hierarchies, sort orders, aliases, custom SQL, user filters, datasource filters, hyper files, published datasources, custom geocoding, data blending. Coverage 85.2% → **95.2%**.
- **35.2: test_pbip_coverage_push.py** (42 tests): Coverage-push tests for `pbip_generator.py` — OneDrive retry logic, theme references, report-level filters, swap bookmarks, custom visual GUIDs, context filters, action buttons, pages shelf slicers, tooltip pages, custom shapes copy, field entity resolution, padding/border, sort definitions, rich text formatting, reference lines, number formats, dual axis sync, axes label rotation, continuous/discrete axis, DS column inheritance, migration metadata, stale visual cleanup, script visual detection, page navigator. Coverage 90.3% → **96.8%**.
- **Overall: 3,342 → 3,459 tests** (+117), coverage **93.08% → 95.4%**, 2 new test files, 62 total test files.

---

## v10.0.0 — Test Coverage Push & Quality

### Sprint 34 — Documentation, Version Bump & Release ✅
- **34.1: DEVELOPMENT_PLAN.md refresh**: Updated version header, test counts (3,342 across 60 files), coverage (93.08%).
- **34.2: CHANGELOG.md finalized**: Added v10.0.0 entry with Sprint 33-34 details.
- **34.3: copilot-instructions.md update**: Updated test count and coverage figures.
- **34.4: Version bump**: `pyproject.toml` and `powerbi_import/__init__.py` bumped from 9.0.0 → 10.0.0.
- **34.5: Final validation**: Full test suite pass (3,342 tests, 93.08% coverage).

### Sprint 33 — Dedicated Test Files for Uncovered Modules ✅
- **33.1: test_telemetry.py** (41 tests): Comprehensive tests for `telemetry.py` — `IsTelemetryEnabled` (7), `TelemetryCollectorInit` (6), `StartFinish` (3), `Recording` (5), `Save` (4), `Send` (4), `GetToolVersion` (3), `ReadLog` (4), `Summary` (3), `GetData` (2). Coverage 80.4% → **97.9%**.
- **33.2: test_comparison_report.py** (20 tests): Tests for `comparison_report.py` — `LoadJson` (3), `LoadExtracted` (2), `LoadPbip` (3), `CompareWorksheets` (3), `CompareCalculations` (2), `CompareDatasources` (3), `GenerateComparisonReport` (3), `Main` (1). Coverage 87.9% → **91.1%**.
- **33.3: test_telemetry_dashboard.py** (18 tests): Tests for `telemetry_dashboard.py` — `Esc` (5), `LoadReports` (5), `GenerateDashboard` (6), `Main` (2). Module now fully covered.
- **33.4: test_goals_generator.py** (24 tests): Tests for `goals_generator.py` — `CadenceRefresh` (2), `BuildGoal` (10), `GenerateGoalsJson` (8), `WriteGoalsArtifact` (4). Coverage → **100%**.
- **33.5: test_wizard.py** (24 tests): Tests for `wizard.py` — `InputHelper` (6), `YesNo` (8), `Choose` (5), `WizardToArgs` (3), `RunWizard` (2).
- **33.6: test_import_to_powerbi.py** (19 tests): Tests for `import_to_powerbi.py` — `Init` (2), `LoadConvertedObjects` (6), `ImportAll` (5), `GeneratePowerBIProject` (4), `Main` (2). Coverage 79.4% → **100%**.
- **Overall: 3,196 → 3,342 tests** (+146), coverage **92.76% → 93.08%**, 6 new test files, 60 total test files.

---

## v9.0.0 — Coverage, Hyper Data, Modern Tableau & Polish

### Sprint 32 — Documentation, Polish & Release ✅
- **32.1: GAP_ANALYSIS.md refresh**: Updated test count (3,196 across 54 files), sprint range (13-32), ASCII art box, closed settings gap (fractional timeouts), added Sprint 30-31 CI/CD closures (plugin system, PBIR schema check, PyPI workflow).
- **32.2: KNOWN_LIMITATIONS.md refresh**: Updated sprint header, removed int-only timeout limitation (fixed Sprint 31), added Plugin System Limitations and Schema Compatibility sections, added `--check-schema` workaround.
- **32.3: CHANGELOG.md finalized**: Removed "(in progress)" from v9.0.0 header, added Sprint 32 entry.
- **32.4: copilot-instructions.md update**: Updated test count (3,196+ across 54 files), added `plugins.py` module, `examples/plugins/` directory, `--check-schema` CLI flag, PyPI publish workflow reference.
- **32.5: Version bump**: `pyproject.toml` and `powerbi_import/__init__.py` bumped from 8.0.0 → 9.0.0.
- **32.6: Final validation**: Full test suite pass (3,196 tests, 92.76% coverage).

### Sprint 31 — Plugins, Packaging & Automation ✅
- **31.1: Plugin examples**: 3 example plugins in `examples/plugins/` — `custom_visual_mapper.py` (visual type overrides), `dax_post_processor.py` (regex-based DAX transforms + IFERROR wrapping), `naming_convention.py` (snake/pascal/camel case enforcement). Each with `Plugin` alias, docstrings, and README.
- **31.2: PyPI auto-publish workflow**: `.github/workflows/publish.yml` — tag-triggered (`v*.*.*`) GitHub Actions workflow: build wheel → `twine check` → publish via OIDC trusted publisher.
- **31.3: PBIR schema forward-compat**: `ArtifactValidator.check_pbir_schema_version()` probes Microsoft schema URLs for newer versions (patch +1..+4, minor +1..+2). `--check-schema` CLI flag for on-demand version check.
- **31.4: Fractional timeouts**: `deployment_timeout` and `retry_delay` changed from `int` to `float` in Pydantic settings — supports sub-second delays.
- **42 new tests** in `test_sprint31.py` — 3,196 total, 92.76% coverage

### Sprint 30 — Coverage Push: Generation Layer ✅
- **29.1: Dynamic parameters (2024.3+)**: Database-query-driven parameter extraction (old + new XML format), generate M partition with `Value.NativeQuery()` source and `refreshPolicy` for automatic refresh. Fixed Python 3.14 Element `or` pattern compatibility.
- **29.2: Tableau Pulse → PBI Goals**: New `pulse_extractor.py` parses `<metric>`, `<pulse-metric>`, and `<metrics/metric>` elements. New `goals_generator.py` generates Fabric Scorecard API JSON. `--goals` CLI flag for optional scorecard generation.
- **29.3: Multi-language report labels**: `_write_multi_language_cultures()` generates separate `cultures/{locale}.tmdl` files from comma-separated locales. `--languages` CLI flag threaded through full pipeline (`migrate.py` → `import_to_powerbi.py` → `pbip_generator.py` → `tmdl_generator.py`).
- **29.4: Translated display folders**: `_DISPLAY_FOLDER_TRANSLATIONS` for 9 locales (fr-FR, de-DE, es-ES, pt-BR, ja-JP, zh-CN, ko-KR, it-IT, nl-NL) with 11 display folder names. `translatedDisplayFolder` entries in culture TMDL files. Language-prefix fallback (e.g., fr-CA → fr-FR).
- **50 new tests** in `test_sprint29.py` — 2,666 total, 88.1% coverage

### Sprint 28 — Hyper Data Loading & SCRIPT_* Visuals ✅
- **28.1: Hyper file data reader**: New `hyper_reader.py` (513 lines) — reads `.hyper` files via stdlib `sqlite3`, extracts table schema + first N rows, generates `#table()` M expressions with inline data.
- **28.2: Pipeline wiring**: Hyper reader integrated into `extract_tableau_data.py` and `m_query_builder.py` — populates M queries with actual data instead of empty `#table()`.
- **28.3: Prep flow Hyper source**: Hyper reader integrated into `prep_flow_parser.py` for `.hyper` file references in Prep flows.
- **28.4: SCRIPT_* → Python/R visual**: `SCRIPT_BOOL/INT/REAL/STR` detection generates PBI Python/R visual containers (`scriptVisual`) with original code preserved as comments.
- **28.5: SCRIPT_* assessment**: Assessment flags SCRIPT_* calcs as "requires Python/R runtime setup" (severity downgraded from `fail` to `warn`).
- **74 new tests** in `test_sprint28.py` — 2,616 total, 88.0% coverage

### Sprint 27 — Coverage Push: Extraction Layer ✅
- **Overall coverage: 81.9% → 88.3%** (+6.4 percentage points)
- **267 new tests** (2,275 → 2,542), 0 failures, 15 skipped
- **5 files brought to 85%+ coverage:**
  - `config/migration_config.py`: 63.2% → **100%** (28 new tests in `test_migration_config.py`)
  - `prep_flow_parser.py`: 65.4% → **99.1%** (34 new tests added to `test_prep_flow_parser.py`)
  - `datasource_extractor.py`: 65.4% → **92.5%** (54 new tests in `test_datasource_extractor.py`)
  - `server_client.py`: 62.5% → **87.5%** (12 new tests added to `test_server_client.py`)
  - `extract_tableau_data.py`: 65.7% → **86.2%** (125 new tests in `test_extract_tableau_data.py`)
- 3 new test files, 2 extended test files

---

## v8.0.0 — Code Quality, Enterprise Readiness

### Sprint 21 — Refactor Large Functions ✅
- **5 major function splits**: All functions exceeding 200 lines refactored into composable sub-functions
  - `_build_visual_objects()` (569 lines) → 5 focused helpers: axis, legend, label, formatting, analytics
  - `create_report_structure()` (513 lines) → 4 helpers: pages, report filters, metadata, bookmarks
  - `_build_semantic_model()` (444 lines) → 4 helpers: tables, relationships, security, parameters
  - `parse_prep_flow()` (361 lines) → 3 helpers: DAG traversal, M generation, datasource emission
  - `create_visual_container()` (342 lines) → 3 helpers: visual config, query, layout
- Committed as `642d18a`, pushed to main

### Sprint 21b — Consolidated Migration Dashboard ✅
- **`--consolidate DIR` CLI flag**: Scans directory tree for existing migration reports, generates unified `MIGRATION_DASHBOARD.html`
- **`run_consolidate_reports()`**: Recursive discovery of `migration_report_*.json` and `migration_metadata.json`, groups by workbook (latest report wins)
- 9 new tests in `test_cli_wiring.py` (TestConsolidateReports class)

### Sprint 22 — Error Handling & Logging Hardening ✅
- **33 exception handlers narrowed** across 7 files: `except Exception` → specific types (`json.JSONDecodeError`, `OSError`, `KeyError`, `ValueError`, `ET.ParseError`, `urllib.error.URLError`, etc.)
- All catch blocks now log warnings with context instead of silently swallowing
- 16 new error recovery tests in `test_error_paths.py`

### Sprint 23 — DAX Conversion Accuracy Boost ✅
- **REGEX character class expansion**: `[a-zA-Z]` → `CODE()`-based checks using `||`/`&&` operators
- **REGEX extract improvements**: suffix capture, prefix+suffix, digit extraction patterns
- **WINDOW frame precision**: Proper DAX `WINDOW` function generation instead of comment placeholders
- **FIRST()/LAST()**: Changed from `0` to `RANKX`-based offsets for accurate first/last row detection
- 35+ new tests in `test_dax_coverage.py`

### Sprint 24 — Enterprise & Scale Features ✅
- **`--parallel N`**: Thread-based parallel batch migration via `ThreadPoolExecutor`
- **`--resume`**: Skip already-completed workbooks (checks output dir for existing `.pbip`)
- **`--manifest FILE`**: JSON manifest with per-workbook config overrides
- **`--jsonl-log FILE`**: Structured JSON Lines logging (batch_start/end, workbook_start/end, resume_skip)
- Extracted `_migrate_single_workbook()` helper for cleaner batch orchestration
- 21 new tests in `test_enterprise_features.py`

### Sprint 25 — Visual Fidelity & Formatting Depth ✅
- **Grid-based layout**: MIN_VISUAL_WIDTH=60, MIN_VISUAL_HEIGHT=40, MIN_GAP=4, page bounds clamping
- **Dashboard tab strip → page navigator**: `_create_page_navigator()` for multi-dashboard projects
- **Sheet-swap containers → bookmarks**: `_create_swap_bookmarks()` for dynamic zone visibility
- **Motion chart annotation**: Pages shelf detection + dynamic zone visibility checks in assessment
- **Custom shape migration**: Extracts shape files from `.twbx` → `RegisteredResources/`
- 20 new tests in `test_visual_fidelity.py`

### Sprint 26 — Test Quality & Coverage ✅
- **Coverage-driven gap filling**: 123 new tests covering M connectors (28 types), M transforms (33 edge cases), DAX round-trip (18), DAX edge cases (25), assessment (4), type mapping (2), additional connectors (8)
- **Coverage reached 81.9%** (up from 79.8%), passing the 80% threshold
- Version bumped to 8.0.0

### Stats
- **2,275 tests** across 45 test files, 0 failures, 15 skipped
- **81.9% line coverage** (10,083 statements, 1,830 missing)
- 209 new tests added across sprints 21b-26

---

## v7.0.0 — CLI UX, DAX & M Hardening, Visual Refinements

### Sprint 17 — CLI Wiring & UX
- **`--compare` flag**: Wired `comparison_report.generate_comparison_report()` into CLI — generates side-by-side HTML comparison of Tableau vs Power BI structures
- **`--dashboard` flag**: Wired `telemetry_dashboard.generate_dashboard()` into CLI — generates interactive HTML telemetry dashboard
- **`MigrationProgress` wiring**: Progress tracking with dynamic step counting integrated across extraction → prep flow → generation → report steps
- **Batch summary table**: Formatted console table with Workbook, Status, Fidelity, Tables, Visuals columns plus aggregate stats (avg/min/max fidelity)
- 14 new tests in `test_cli_wiring.py`

### Sprint 18 — DAX & M Hardening
- **Custom SQL parameter binding**: `_gen_m_custom_sql()` now generates `Value.NativeQuery()` with parameter record `[Param1="val1", ...]` and `[EnableFolding=true]` when `params` dict is present
- **RANK_MODIFIED**: Changed to `RANKX({table}, {expr},, ASC, SKIP)` — uses SKIP parameter for correct modified competition ranking
- **SIZE()**: Simplified to `COUNTROWS(ALLSELECTED())` — direct partition-aware row count without redundant `CALCULATE()` wrapper
- **Query folding hints**: New `m_transform_buffer()` function; `m_transform_join()` gained `buffer_right` parameter to wrap right table in `Table.Buffer()` for query folding boundaries
- 10 new tests (3 in `test_m_query_builder.py`, 2 in `test_dax_coverage.py` updated, 5 buffer/folding tests)

### Sprint 19 — Visual & Layout Refinements
- **Violin plot**: Mapped to `boxAndWhisker` + custom visual GUID `ViolinPlot1.0.0` — entries in `VISUAL_TYPE_MAP`, `CUSTOM_VISUAL_GUIDS`, `APPROXIMATION_MAP`
- **Parallel coordinates**: Mapped to `lineChart` + custom visual GUID `ParallelCoordinates1.0.0`
- **Calendar heat map**: Auto-enables conditional formatting properties (`backColorConditionalFormatting`, `fontColorConditionalFormatting`) on matrix visuals + migration note
- **Packed bubble size**: `mark_encoding.size.field` auto-injected as 3rd measure into scatter chart Size data role
- **Butterfly chart**: Improved approximation note — suggests negating one measure to simulate symmetry
- 14 new tests in `test_generation_coverage.py`

### Sprint 20 — Documentation & Release
- Updated `GAP_ANALYSIS.md`: 10 gaps closed (violin, parallel coords, butterfly, calendar heat map, packed bubble, RANK_MODIFIED, SIZE, custom SQL params, query folding, comparison report)
- Updated `KNOWN_LIMITATIONS.md`: v7.0.0 closures reflected
- Updated `DEVELOPMENT_PLAN.md`: v7.0.0 sprint details
- Updated `CHANGELOG.md` and `.github/copilot-instructions.md`

### Stats
- **38 new tests** (14 CLI + 10 DAX/M + 14 visual)
- 8 source files modified, 1 new test file created
- All phases non-breaking (additive changes only)

---

## v6.1.0 — Gap Closure & Batch Validation

### Prep Flow Parser
- **ZIP auto-detection**: `.tfl` files that are actually ZIP archives (PK header) are now auto-detected via `zipfile.is_zipfile()`. The `flow` entry (Prep 2020.3+ format) is also supported alongside `*.tfl` entries inside ZIP archives.
- 3 new tests in `test_prep_flow_parser.py` (61 total, up from 58)

### M Query Error Handling
- **`try...otherwise` wired**: `wrap_source_with_try_otherwise()` now called in `tmdl_generator.generate_table_bim()` after `inject_m_steps` — wraps Source step with `try...otherwise` error handling using column names

### Report-Level Filter Promotion
- **Global + datasource filter promotion**: `_create_visual_filters()` now generates report-level `filterConfig` from `converted_objects['filters']` and `converted_objects['datasource_filters']` in `report.json`

### Custom Visual GUID Wiring
- **`resolve_custom_visual_type()` integrated**: `_create_visual_worksheet()` now checks `original_mark_class` against `CUSTOM_VISUAL_GUIDS` registry (9 entries: sankey, chord, network, wordcloud, ganttbar, histogram, boxplot, radial, bullet)
- **`customVisualsRepository`** added to `report.json` when custom visuals are used
- Original Tableau mark class now extracted as `original_mark_class` field on worksheets

### Batch Validation
- 14/14 real-world workbooks pass at **100% fidelity**
- **1,983 tests passing**, 15 skipped

---

## v6.0.0 — Sprints 13-16: Conversion Depth, PBI Service Deploy, Tableau Server, Polish

### Sprint 13 — Conversion Depth (Phase N)

- **N.1: Custom Visual Mapping** — Updated `VISUAL_TYPE_MAP` to use AppSource custom visual class names (`sankeyDiagram`, `chordChart`, `networkNavigator`, `ganttChart`) instead of fallback standard types. Added `get_custom_visual_guid_for_approx()` function.
- **N.2: Stepped Color Scales** — Enhanced stepped color threshold handling with sorted thresholds, `LessThanOrEqual`/`GreaterThan` operators, and `conditionalFormatting` array in PBIR output.
- **N.3: Dynamic Reference Lines** — Integrated `_build_dynamic_reference_line()` for average, median, percentile, min, max computation types alongside constant reference lines.
- **N.4: Multi-DS Formula Routing** — Added `resolve_table_for_formula()` in `tmdl_generator.py` for formula-based table routing by column reference density.
- **N.5: sortByColumn Validation** — Implemented cross-validation in `validator.py` — collects sort targets and validates they exist as defined columns.
- **N.6: Nested LOD Cleanup** — Added `AGG(CALCULATE(...))` redundancy cleanup in `dax_converter.py` for LOD-inside-aggregation patterns.

### Sprint 14 — Power BI Service Deployment (Phase O)

- **O.1: `deploy/pbi_client.py`** (NEW) — `PBIServiceClient` with Azure AD auth (Service Principal / Managed Identity / env token), REST API for import, refresh, list, delete operations.
- **O.2: `deploy/pbix_packager.py`** (NEW) — `PBIXPackager`: packages `.pbip` project directories into `.pbix` ZIP files with OPC content types.
- **O.3: `deploy/pbi_deployer.py`** (NEW) — `PBIWorkspaceDeployer`: orchestrates package → upload → poll → refresh → validate end-to-end deployment.
- **O.4: `--deploy` CLI flag** — Added `--deploy WORKSPACE_ID` and `--deploy-refresh` arguments to `migrate.py`.
- **O.5: Post-deploy validation** — `validate_deployment()` checks dataset existence and refresh history after import.
- **Updated `deploy/__init__.py`** — Exports `PBIServiceClient`, `PBIXPackager`, `PBIWorkspaceDeployer`, `DeploymentResult`.

### Sprint 15 — Tableau Server Extraction (Phase P)

- **P.1: `tableau_export/server_client.py`** (NEW) — `TableauServerClient` with PAT or username/password auth, REST API for workbooks, datasources, projects. Includes batch download, regex search, context manager.
- **P.2: CLI flags** — Added `--server`, `--site`, `--workbook`, `--token-name`, `--token-secret`, `--server-batch` arguments to `migrate.py`.
- **P.3: Server download flow** — Integrated server download before extraction: single workbook by name/ID or batch by project.

### Sprint 16 — Polish & Release

- **Version consistency** — Aligned `pyproject.toml` and `powerbi_import/__init__.py` to `6.0.0`.
- **Updated CHANGELOG, copilot-instructions, docs**.

### Stats
- **1,889 tests passing** (53 Sprint 13 + 33 Sprint 14 + 26 Sprint 15 new tests)
- 3 new source files, 3 new test files
- All phases non-breaking (additive changes only)

---

## v5.5.0 — Phases I-M: Multi-DS Routing, Windows CI, Inference, DAX Coverage, Metadata

### Phase I — Multi-Datasource Calculation Routing

- **`datasource_extractor.py`**: Tagged each extracted calculation with `datasource_name` so calcs carry their source datasource identity.
- **`tmdl_generator.py`**: Built `ds_main_table` map (datasource → its largest table). Replaced global boolean gate with datasource-aware routing: each datasource's main table receives only its own calculations, while untagged (legacy) calcs fall back to the global main table.

### Phase J — Windows CI + Batch Validation

- **`ci.yml`**: Added `--batch` mode test step to CI validate job (copies `.twb` samples to temp dir, runs batch migration).
- **`ci.yml`**: Added Windows PowerShell validate step (`pwsh` shell) that loops over `.twb` samples and runs `migrate.py` with `--output-dir` on Windows runners.

### Phase K — Relationship Inference Improvement

- **`tmdl_generator.py`**: Added proactive key-column matching pass in `_infer_cross_table_relationships()`:
  - Scans all unconnected table pairs for columns with matching names ending in key-like suffixes (`id`, `key`, `code`, `number`, `pk`, `fk`, etc.).
  - Scoring: exact match=100, both key-suffix=80, substring=50, common prefix ≥3 chars=25. Threshold: score ≥ 50.
  - Creates `inferred_key_` prefixed relationships (manyToOne).

### Phase L — DAX Conversion Coverage Hardening

- **`tests/test_phase_l_dax_coverage.py`** (NEW): 55 tests across 10 classes covering edge cases:
  - Table calc compounds (INDEX/SIZE/FIRST/LAST in IF)
  - Table calc edge cases (RANK_MODIFIED, RANK_PERCENTILE, RUNNING_SUM with compute_using, TOTAL COUNTD, LOOKUP offset 0)
  - Window statistical functions (WINDOW_STDEVP, WINDOW_VARP, WINDOW_CORR, WINDOW_COVAR, WINDOW_COVARP)
  - Date converter edge cases (DATEDIFF second/quarter, DATENAME hour, DATEPARSE US)
  - String converter edge cases (STR expr, FLOAT nested, ENDSWITH/STARTSWITH, FIND 3-arg)
  - LOD combos (ratio, EXCLUDE, INCLUDE MEDIAN, date literal)
  - Operators & case insensitivity (lowercase functions, mixed case, all operators, deep nested IF)
  - Spatial placeholders (BUFFER, AREA, INTERSECTION)
  - Regexp smart patterns (REGEXP_MATCH, REGEXP_EXTRACT_NTH, REGEXP_REPLACE char class)
  - Multiple functions in formula (SUM+COUNTD, AGG(IF)→AGGX, percent-of-total)

### Phase M — Migration Metadata Enrichment

- **`pbip_generator.py`**: Enriched `migration_metadata.json` with:
  - `tmdl_stats.measures` — count of measures in generated TMDL files
  - `tmdl_stats.columns` — count of columns in generated TMDL files
  - `tmdl_stats.relationships` — count of relationships from `relationships.tmdl`
  - `visual_type_mappings` — dict mapping worksheet name → Tableau mark type
  - `approximations` — list of visuals using approximated type mappings with migration notes
  - `generated_output.theme_detail` — applied/skipped status with reason

### Stats
- **1,777 tests passing** (55 new in Phase L)
- All phases non-breaking (additive changes only)

---

## v5.4.0 — Phases D-H: Visual Fidelity, Coverage, CI/CD, Config & Docs

### Phase D — Visual Fidelity

#### New Config Templates (`visual_generator.py`)
- Added PBIR config templates for 4 visual types that previously fell back to empty configs:
  - `hundredPercentStackedAreaChart` (categoryAxis + valueAxis + legend)
  - `sunburst` (group + legend)
  - `decompositionTree` (tree)
  - `shapeMap` (legend + dataPoint)

#### Approximation Migration Notes (`visual_generator.py`)
- **New**: `APPROXIMATION_MAP` dict (12 entries) mapping Tableau types to `(pbi_type, migration_note)` tuples
- **New**: `get_approximation_note()` function returns human-readable migration notes for approximated visuals
- Approximation-mapped visuals now have `annotations: [{"name": "MigrationNote", "value": "..."}]` in their PBIR JSON
- Covers: mekko, sankey, chord, network, ganttbar, bumpchart, slopechart, timeline, butterfly, waffle, pareto, dualaxis

#### Fallback Partition Fix (`tmdl_generator.py`)
- Changed fallback M partition from `Source = null` (invalid M) to `Source = #table(type table [], {})` (valid empty table)

### Phase E — Test Coverage

#### New Test Suite (`tests/test_phase_d_e_coverage.py`)
- 46 new tests across 15 test classes covering previously untested functions:
  - `TestVisualConfigTemplates` (6): all 4 new templates + all-have-templates + existing unchanged
  - `TestApproximationMap` (6): known entries, tuples, note lookup, exact match, None, case insensitive
  - `TestMigrationNoteOnVisuals` (3): annotation presence/absence for approximated vs standard visuals
  - `TestFallbackPartition` (2): valid #table expression, TODO comment
  - `TestDeactivateAmbiguousPaths` (6): no rels, no cycle, cycle deactivates one, Calendar priority
  - `TestDetectManyToMany` (4): full→M2M, left/inner→M2O, default join type
  - `TestReplaceRelatedWithLookupvalue` (4): M2M replacement, non-M2M keep, multiple calls, empty
  - `TestFixRelatedForManyToMany` (2): replaces in measures, no M2M no change
  - `TestInferCrossTableRelationships` (2): infers from cross-ref, no inference when exists
  - `TestCreateReportFilters` (4): parameter-based filters, edge cases
  - `TestCreateVisualTextbox` (1), `TestCreateVisualImage` (1), `TestCreatePaginatedReport` (1)
  - `TestVisualTypeNonRegression` (4): bar, line, None, unknown

### Phase F — CI/CD Hardening

#### Lint & Type Checking (`.github/workflows/ci.yml`)
- **Removed `--exit-zero`** from ruff — lint violations now fail the build
- **Added pyright** type checking step after ruff (warnings-only initially)

#### Python Version Matrix
- **Dropped Python 3.8** (EOL October 2024)
- Matrix now covers Python 3.9, 3.10, 3.11, 3.12, 3.13, 3.14

#### Performance Check Fix
- Fixed function name: `convert_tableau_to_dax` → `convert_tableau_formula_to_dax` (correct public API)

### Phase G — Config & UX

#### Quiet Mode (`migrate.py`)
- **New**: `--quiet` / `-q` CLI flag suppresses all output except errors
- Useful for scripted/CI usage where only failures should be visible

#### Config Example File
- **New**: `config.example.json` — annotated template documenting the `--config` JSON schema
- Documents all keys: `tableau_file`, `prep_flow`, `output_dir`, `model_mode`, `culture`, `calendar_start`, `calendar_end`, `output_format`, `rollback`, `verbose`, `log_file`

### Phase H — Documentation

#### GAP_ANALYSIS.md Updates
- Updated version header to v5.4.0
- Updated test count: 1,725+ tests across 33 test files
- Marked WINDOW_CORR/COVAR/COVARP as ✅ IMPLEMENTED (v5.3.0 VAR/SUMX patterns)
- Marked config file support, output format selection, dry-run mode as ✅ IMPLEMENTED
- Updated CLI arguments list with `--quiet`, `--config`, `--dry-run`

#### KNOWN_LIMITATIONS.md Updates
- Updated version to v5.4.0
- Added REGEXP_EXTRACT_NTH approximation entry (v5.3.0)

#### Copilot Instructions Updates
- Updated test count from 887 to 1,725 across 33 test files

### Test Summary
- **1,722 tests** (1,722 passed, 3 skipped, 0 failures)

## v5.3.0 — Phase C: DAX & M Conversion Hardening

### DAX Conversion Improvements

#### WINDOW_CORR/COVAR/COVARP — Proper VAR/SUMX Pattern (`dax_converter.py`)
- **Previous**: Naive prefix swap to `CALCULATE(CORREL(` / `CALCULATE(COVARIANCE.S(` / `CALCULATE(COVARIANCE.P(` — **these are not real DAX functions** and would fail in PBI Desktop
- **New**: Dedicated converter inside `_convert_window_functions()` producing full `VAR _MeanX / _MeanY / SUMX / DIVIDE` iterator pattern wrapped in `CALCULATE(..., ALL/ALLEXCEPT)` for windowing context
- Reuses `_build_corr_covar_dax()` (Pearson correlation / sample covariance / population covariance)
- Supports `compute_using` dimensions for ALLEXCEPT partitioning

#### CORR/COVAR/COVARP — Table Name Parameter (`dax_converter.py`)
- **Previous**: Hardcoded `ALL('Table')` in all VAR/SUMX patterns
- **New**: `_build_corr_covar_dax()` accepts `table_name` parameter, properly escaping apostrophes
- `_convert_corr_covar()` now passes `table_name` through the conversion pipeline

#### REGEXP_EXTRACT_NTH — Dedicated Converter (`dax_converter.py`)
- **Previous**: Broken prefix swap `/* REGEXP_EXTRACT_NTH: ... */ MID(` — wrong semantics, no argument parsing
- **New**: `_convert_regexp_extract_nth()` using `_transform_func_call` with balanced-paren extraction:
  - Delimiter-based patterns `([^-]*)` → `PATHITEM(SUBSTITUTE(field, "-", "|"), index)`
  - Fixed-prefix capture `prefix(.*)` → `MID(field, SEARCH("prefix", field) + len, LEN(field))`
  - Alternation capture `(cat|dog|fish)` → IF chain with CONTAINSSTRING
  - Complex patterns → `BLANK()` with migration comment
  - 2-arg form defaults to index 1

#### Nested LOD — Parenthesis Depth Tracking (`dax_converter.py`)
- **Previous**: Colon-split in LOD parsing tracked brace depth only — colons inside function calls like `FORMAT(date, "HH:mm")` could be mis-split
- **New**: Added `paren_depth` tracking alongside `colon_depth` in `_find_lod_braces()` colon-split loop

### M Query Error Handling (`m_query_builder.py`)
- **New functions** for robust M queries:
  - `m_transform_remove_errors(columns)` — `Table.RemoveRowsWithErrors`
  - `m_transform_replace_errors(columns, replacement)` — `Table.ReplaceErrorValues`
  - `m_transform_try_otherwise(step_name, expr, fallback)` — `try ... otherwise` wrapper
  - `wrap_source_with_try_otherwise(m_query, columns)` — wraps Source step with fallback to empty table

### New Test Suite (`tests/test_phase_c_dax_m_hardening.py`)
- 47 new tests across 8 test classes:
  - `TestWindowCorrelationCovariance` (7 tests): VAR pattern output, compute_using, case-insensitivity, fallback, no infinite loop
  - `TestCorrCovarTableName` (4 tests): table_name parameter, apostrophe escaping
  - `TestRegexpExtractNth` (8 tests): delimiter, prefix, alternation, fallback, 2-arg, 1-arg
  - `TestNestedLODEdgeCases` (6 tests): paren depth, nested FIXED/INCLUDE, no-dim, EXCLUDE
  - `TestMQueryErrorHandling` (10 tests): remove/replace errors, try/otherwise, inject steps, wrap source
  - `TestWindowFunctionsNonRegression` (5 tests): WINDOW_SUM/AVG/MAX/MIN/COUNT
  - `TestRegexpNonRegression` (6 tests): REGEXP_MATCH/EXTRACT/REPLACE
  - `TestSplitNonRegression` (2 tests): SPLIT 2-arg and 3-arg

### Test Summary
- **1,676 tests** (1,676 passed, 3 skipped, 0 failures)

## v5.2.0 — PBI Desktop Validation & Bug Fixes

### Critical Bug Fixes (PBI Desktop Load Failures)

#### Empty Measure Expressions (Bug #1)
- **Root cause**: `categorical-bin` group calculations have no formula in Tableau XML → empty string propagated through classification → became measures with `expression: ""` → TMDL output `measure 'X' = ` with no body → **PBI Desktop refuses to load the entire model**
- **Fix (3 layers)**:
  - `datasource_extractor.py`: Skip `categorical-bin` calculations and empty formulas during extraction
  - `tmdl_generator.py`: Guard in calc loop — `if not formula: continue`
  - `tmdl_generator.py`: Defensive fallback in `_write_measure` — `measure.get('expression') or '0'`

#### Tableau Ephemeral Field References (Bug #2)
- **Root cause**: Tableau derivation names like `[yr:Order Date:ok]`, `[tyr:Date:qk]` leaked into DAX/M expressions — group extraction only cleaned `none:` prefix, not `yr:`, `mn:`, `tyr:`, etc.
- **Fix (3 layers)**:
  - `extract_tableau_data.py`: Promoted `_clean_field_ref()` to module-level function, applied during all group extraction (combined fields + value groups)
  - `extract_tableau_data.py`: Extended `_RE_DERIVATION_PREFIX` regex with truncated date prefixes (`tyr`, `tqr`, `tmn`, `tdy`, `twk`)
  - `tmdl_generator.py`: Added secondary defense `_clean_tableau_field_ref()` in `_process_sets_groups_bins` to catch any leaks

### Validator Enhancements (`powerbi_import/validator.py`)
- **Empty expression detection**: Catches `measure 'X' = ` and `expression =` with no body
- **Tableau derivation reference detection**: Flags `[yr:Field:ok]` patterns in DAX and M expressions
- **Inline measure DAX validation**: Now validates single-line `measure 'X' = <dax>` patterns (previously only checked `expression =` lines)
- **lineageTag uniqueness check**: Detects duplicate lineageTags within a TMDL file
- **Multi-line expression derivation check**: Scans ``` delimited blocks for Tableau field references

### New Test Suite (`tests/test_pbi_desktop_validation.py`)
- 34 new tests covering:
  - Empty measure prevention (extraction filter, TMDL guard, `_write_measure` fallback)
  - Ephemeral field reference cleaning (12 prefix variants)
  - Validator empty expression detection
  - Validator derivation reference detection
  - Validator lineageTag uniqueness
  - Validator inline measure DAX validation
  - E2E migration output integrity (no empty measures, no derivation refs, no empty expressions)

### Test Summary
- **1,629 tests** (1,629 passed, 3 skipped, 0 failures)
- All 22 sample workbooks migrate successfully (8 tableau_samples + 14 real_world)
- All projects pass enhanced validation

## v5.1.0 — Sprints 9-12: DAX Accuracy, Generation Quality & Assessment

### Sprint 9 — DAX Conversion Accuracy

#### Improved DAX Conversions (`tableau_export/dax_converter.py`)
- **SPLIT()**: Now generates `PATHITEM(SUBSTITUTE(s, delim, "|"), token)` instead of `BLANK()` placeholder
- **INDEX()**: Improved to `RANKX(ALLSELECTED(), [Value], , ASC, DENSE)` with partition context
- **SIZE()**: Improved to `CALCULATE(COUNTROWS(), ALLSELECTED())` with partition context
- **WINDOW_CORR**: Now generates `CALCULATE(CORREL(` instead of `0` placeholder
- **WINDOW_COVAR**: Now generates `CALCULATE(COVARIANCE.S(` instead of `0` placeholder
- **WINDOW_COVARP**: Now generates `CALCULATE(COVARIANCE.P(` instead of `0` placeholder
- **DATEPARSE()**: Now preserves format string — `FORMAT(DATEVALUE(expr), "fmt")` instead of discarding format
- **ATAN2()**: Proper quadrant-aware implementation using `VAR`/`IF`/`PI()` (5 quadrant cases)
- **REGEXP_EXTRACT_NTH**: Changed from `CONTAINSSTRING(` to `MID(` with improved approximation comment

### Sprint 10 — Generation Quality

#### Prep Flow Fixes (`tableau_export/prep_flow_parser.py`)
- **VAR/VARP aggregation**: Fixed from incorrect `sum` mapping to correct `var`/`varp`
- **notInner join**: Fixed from incorrect `full` mapping to correct `leftanti`

#### Visual Generator (`powerbi_import/visual_generator.py`)
- **`create_filters_config()`**: Added `table_name` parameter — uses actual table name instead of hardcoded `"Table1"`

#### M Query Builder (`tableau_export/m_query_builder.py`)
- **Fallback queries**: Now use `try...otherwise` error handling pattern with empty-table fallback
- **Connector type**: Included in TODO comment for better debugging

#### Observability (`powerbi_import/pbip_generator.py`)
- Added `logging` module import and logger instance
- Replaced 4 silent `pass` exception handlers with `logger.debug()` calls (font size, label fontSize, axis rotation, map washout)

### Sprint 11 — Assessment & Intelligence

#### Assessment Enhancements (`powerbi_import/assessment.py`)
- **Tableau 2024.3+ feature detection**: Dynamic Zone Visibility, Dynamic Parameters (DB query), Combined/Synchronized Axes, RAWSQL functions
- **Partial functions cleanup**: Removed INDEX, WINDOW_CORR, WINDOW_COVAR, WINDOW_COVARP from partial functions list (now fully converted)

### Sprint 12 — Tests & Documentation

#### Test Suite
- Added **52 new tests** in `tests/test_v51_features.py` covering all Sprint 9-11 features
- Updated `test_split_returns_blank` → `test_split_returns_pathitem` in `test_dax_coverage.py`
- **Total: 1,595 tests** (1,595 passed, 3 skipped)

#### Developer Workflow
- Added **2-agent role model** to `.github/copilot-instructions.md` (Planner/Reviewer + Developer/Tester)
- Documented learned rules: function naming, regex safety, API signatures

---

## v5.0.0 — Sprints 5-8: Docs, Conversion Accuracy, Enterprise & Observability

### Sprint 5 — Documentation Refresh & Migration Fidelity

#### Documentation Overhaul
- **`docs/KNOWN_LIMITATIONS.md`**: Rewritten with current limitation categories, severity levels, and workarounds
- **`docs/GAP_ANALYSIS.md`**: Refreshed gap analysis with v5.0 coverage metrics and remaining items
- **`CHANGELOG.md`**: Comprehensive v5.0.0 section documenting all 20 features across 4 sprints

#### Gateway Configuration (`powerbi_import/gateway_config.py`) — NEW MODULE
- **`GatewayConfigGenerator`**: Generates `ConnectionConfig/` directory with gateway connection metadata
- **`OAUTH_CONNECTORS`**: 9 cloud connectors (BigQuery, Snowflake, Salesforce, Google Sheets/Analytics, Azure SQL/Synapse, SharePoint, Databricks) with OAuth config
- **`GATEWAY_CONNECTORS`**: 11 on-prem connectors (SQL Server, PostgreSQL, MySQL, Oracle, SAP HANA/BW, Teradata, DB2, Informix, ODBC, OLEDB) requiring gateway
- **Methods**: `generate_gateway_config(datasources)`, `write_config(project_dir, config)`, `generate_and_write(project_dir, datasources)`

#### Incremental Refresh Policy (`powerbi_import/tmdl_generator.py`)
- **`_write_incremental_refresh_policy()`**: Detects date columns and generates TMDL `refreshPolicy` with `rollingWindowPeriod` and `incrementalWindow` for large datasets

#### Paginated Report Support (`powerbi_import/pbip_generator.py`)
- **Paginated report layout mode**: Worksheets flagged for paginated output generate `.rdl`-compatible page structure with fixed page dimensions

### Sprint 6 — Conversion Accuracy

#### Window Function Frame Boundaries (`tableau_export/dax_converter.py`)
- **`_convert_window_functions()`**: WINDOW_SUM, WINDOW_AVG, WINDOW_MAX, WINDOW_MIN, WINDOW_COUNT with explicit frame boundaries (start, end offsets) converted to `CALCULATE()` with `ALL()` context
- **Bug fix**: Fixed infinite loop where replacement comment text `WINDOW_AVG(...)` re-matched the search regex; comment tag now uses `WINDOW.AVG` format

#### REGEXP_REPLACE Depth Conversion (`tableau_export/dax_converter.py`)
- **`_convert_regexp_replace()`**: Enhanced to handle nested REGEXP_REPLACE calls with depth tracking and balanced-parenthesis parsing

#### Sparkline Config (`powerbi_import/visual_generator.py`)
- **`_build_sparkline_config()`**: Generates PBIR sparkline visual configuration for inline trend visualization in table/matrix cells

#### Custom Visual GUIDs (`powerbi_import/visual_generator.py`)
- **`CUSTOM_VISUAL_GUIDS`**: 9 custom visual entries (Word Cloud, Sankey, Chiclet Slicer, Bullet Chart, Tornado, Histogram, Sunburst, Radar, Infographic)
- **`resolve_custom_visual_type(tableau_mark, use_custom_visuals=True)`**: Returns `(visual_type, guid_info)` tuple; falls back to built-in mappings when `use_custom_visuals=False`

#### Hyper Sample Row Extraction (`tableau_export/extract_tableau_data.py`)
- **`_extract_hyper_sample_rows()`**: Reads `.hyper` file binary data and extracts sample row values for data preview without requiring Tableau Hyper API

### Sprint 7 — Enterprise Packaging

#### Modern Python Packaging (`pyproject.toml`) — NEW FILE
- **PEP 621 compliant**: `[project]` metadata (name, version=5.0.0, description, license, classifiers)
- **Console script entry point**: `tableau-to-pbi = migrate:main`
- **Optional dependencies**: `[deploy]` group for `azure-identity` and `requests`

#### GitHub Pages Documentation (`.github/workflows/gh-pages.yml`, `.github/scripts/build_docs.py`) — NEW FILES
- **Static site generator**: Converts all `docs/*.md` files to styled HTML with navigation sidebar
- **Automated deployment**: GitHub Actions workflow builds and deploys docs to `gh-pages` branch on push to main

#### Comparison Report (`powerbi_import/comparison_report.py`) — NEW MODULE
- **`generate_comparison_report()`**: Generates side-by-side HTML comparison of Tableau extraction vs Power BI generation
- **Visual diff**: Highlights mapping decisions, missing/added elements, and conversion notes

#### Batch Config File (`migrate.py`)
- **`--batch-config FILE`**: YAML/JSON configuration file for batch migrations with per-workbook overrides
- **`_run_batch_config()`**: Reads config and orchestrates multiple migrations with shared settings

#### Fabric Integration Tests (`tests/test_fabric_integration.py`) — NEW FILE
- **27 tests**: Mocked integration tests for FabricClient, FabricDeployer, DeploymentReport, ArtifactCache, FabricConfig, GatewayConfig, ComparisonReport
- **No Azure credentials required**: All API calls stubbed with `unittest.mock`

### Sprint 8 — UX & Observability

#### Interactive CLI Wizard (`powerbi_import/wizard.py`) — NEW MODULE
- **7-step wizard**: Source file selection → output directory → model mode → culture → calendar range → assessment → confirmation
- **`--wizard` CLI flag**: Launches interactive mode in `migrate.py`

#### Progress Tracking (`powerbi_import/progress.py`) — NEW MODULE
- **`MigrationProgress`**: Real-time progress reporting with step counts, elapsed time, and status messages
- **`NullProgress`**: No-op implementation for non-interactive/batch mode

#### Telemetry Dashboard (`powerbi_import/telemetry_dashboard.py`) — NEW MODULE
- **`generate_telemetry_dashboard()`**: Generates interactive HTML dashboard from migration report JSON files
- **Metrics visualization**: conversion rates, error categories, performance trends, per-workbook fidelity scores

#### Coverage Enforcement (`.coveragerc`, `.github/workflows/ci.yml`)
- **`fail_under = 80`**: CI fails if code coverage drops below 80%
- **HTML coverage reports**: Generated and available as CI artifacts

#### Performance Regression CI (`.github/workflows/ci.yml`)
- **Performance gate**: CI runs benchmark tests and fails on significant regression
- **Fabric integration test stage**: Separate CI stage for deploy pipeline tests

### Bug Fixes
- **Infinite loop in `_convert_window_functions`**: Replacement comment `/* WINDOW_AVG(expr, ...) */` contained the pattern `WINDOW_AVG(` which re-matched the search regex, causing an infinite loop. Fixed by using `WINDOW.AVG` format in comments
- **Duplicate `resolve_visual_type` function**: New v5.0 tuple-returning function at line 261 shadowed the existing single-string-returning function at line 594. Renamed to `resolve_custom_visual_type()`

### Testing
- **v5 feature tests** (`tests/test_v5_features.py`): 72 tests covering all Sprint 5-8 features — window frame boundaries, REGEXP_REPLACE depth, sparkline config, custom visual GUIDs, Hyper sample rows, gateway config, comparison report, pyproject.toml, progress tracker, telemetry dashboard, wizard helpers, batch config, coverage config, build docs script, incremental refresh, paginated report
- **Fabric integration tests** (`tests/test_fabric_integration.py`): 27 mocked integration tests for deploy pipeline
- **Test count**: 1444 → **1543** (99 new tests, all passing)

---

## v4.1.0 — Backlog: All 10 Deferred Items Implemented

### Multi-Datasource Context (`powerbi_import/tmdl_generator.py`)
- **`ds_column_table_map`**: Per-datasource column→table mapping built during semantic model generation (Phase 2c)
- **`datasource_table_map`**: Table→datasource reverse mapping for scoped resolution
- **`resolve_table_for_column()`**: New utility function with datasource-scoped lookup + global `column_table_map` fallback

### Hyper Metadata Depth (`tableau_export/extract_tableau_data.py`)
- **Enhanced `extract_hyper_metadata()`**: Reads `.hyper` file headers — format detection (HyPe/SQLite signatures), CREATE TABLE pattern scanning in first 64KB, column type extraction via `_hyper_type_map`

### Incremental Migration (`powerbi_import/incremental.py`) — NEW MODULE
- **`DiffEntry`**: Tracks file-level changes (ADDED / REMOVED / MODIFIED / UNCHANGED) with detail messages
- **`IncrementalMerger.diff_projects()`**: Compares two .pbip project trees, returns list of `DiffEntry` objects
- **`IncrementalMerger.merge()`**: Three-way merge preserving user-editable JSON keys (displayName, title, description, background, etc.); user-owned directories (staticResources/) preserved
- **`IncrementalMerger.generate_diff_report()`**: Human-readable diff report for PR comments
- **`--incremental DIR`**: New CLI flag in `migrate.py`; writes `.migration_merge_report.json`

### PBIR Schema Validation (`powerbi_import/validator.py`)
- **`validate_pbir_structure()`**: Lightweight structural schema checker for report/page/visual JSON — checks required/optional keys, validates `$schema` URLs
- **PBIR schema definitions**: `PBIR_REPORT_REQUIRED_KEYS`, `PBIR_PAGE_REQUIRED_KEYS`, `PBIR_VISUAL_REQUIRED_KEYS` + optional key sets
- **Integrated into `validate_project()`**: PBIR validation now runs automatically on report.json, page.json, and visual.json files

### Property-Based Testing (`tests/test_property_based.py`) — NEW TEST FILE
- **Built-in formula fuzzer**: `_random_formula()` / `_random_expr()` generates Tableau-like formulas using 45 function names, 14 operators, 8 column references
- **10 built-in fuzz tests** (200 iterations each): returns string, no exception, balanced parens, no empty result, edge cases (empty, deeply nested, special chars, very long, unicode)
- **3 hypothesis tests** (conditional on `hypothesis` install): never crashes, returns nonempty, arbitrary text

### Mutation Testing Config (`setup.cfg`, `tests/test_mutation.py`) — NEW FILES
- **`setup.cfg`**: `[mutmut]` section targeting `dax_converter.py`, `m_query_builder.py`, `tmdl_generator.py`, `validator.py`
- **12 smoke tests**: Validate critical assertions exist (SUM≠AVG, COUNTD→DISTINCTCOUNT, IF structure, operator mapping, paren checking)

### Cross-Platform Test Matrix (`.github/workflows/ci.yml`)
- **Expanded matrix**: 3 OS (ubuntu-latest, windows-latest, macos-latest) × 7 Python versions (3.8, 3.9, 3.10, 3.11, 3.12, 3.13, 3.14)
- **`fail-fast: false`**: All combinations run even if one fails
- **`allow-prereleases: true`** for Python 3.14; `exclude` macos + 3.8 (unavailable)

### API Documentation (`docs/generate_api_docs.py`) — NEW FILE
- **Auto-doc generator**: Supports `pdoc` (preferred) and builtin `pydoc` fallback
- **15 modules documented**: All tableau_export/ and powerbi_import/ public modules
- **Styled HTML output**: `index.html` linking all module documentation pages

### PR Preview/Diff Report (`.github/workflows/pr-diff.yml`) — NEW WORKFLOW
- **Triggered on PRs**: Checks out base and PR branches, migrates sample workbooks with each
- **Diff generation**: Uses `IncrementalMerger.diff_projects()` to compare outputs
- **PR commenting**: Creates or updates a migration diff comment on the PR

### Telemetry/Metrics (`powerbi_import/telemetry.py`) — NEW MODULE
- **`TelemetryCollector`**: Records duration, object counts, error counts, Python version, platform, tool version
- **Opt-in only**: Disabled by default; enabled via `--telemetry` flag or `TTPBI_TELEMETRY=1` env var
- **JSONL local log**: `~/.ttpbi_telemetry.json`; optional HTTP endpoint for centralized collection
- **No PII**: Only anonymous usage statistics collected

### Testing
- **Backlog integration tests** (`tests/test_backlog.py`): 36 tests covering all backlog features — multi-datasource context, incremental migration, PBIR validation, telemetry, API docs, mutation config
- **Property-based tests** (`tests/test_property_based.py`): 13 tests with built-in fuzzer + conditional hypothesis
- **Mutation smoke tests** (`tests/test_mutation.py`): 12 tests validating critical assertions
- **Test count**: 1387 → **1444** (57 new tests, all passing)

---

## v4.0.0 — Sprints 2-4: Advanced Features, Quality & Infrastructure

### DAX Converter Enhancements (`tableau_export/dax_converter.py`)
- **REGEXP_MATCH / REGEXP_EXTRACT**: New converters approximate regex patterns using DAX string functions (LEFT, RIGHT, CONTAINSSTRING, MID+SEARCH)
- **Nested LOD parser**: Balanced-brace `_find_lod_braces()` parser replaces fragile regex, correctly handles `{FIXED … {FIXED …}}` nesting
- **String concatenation `+`**: Tableau `+` between string fields converted to `&` at all expression depths (Phase 5d)

### Visual Generator Enhancements (`powerbi_import/visual_generator.py`)
- **Small Multiples**: `_build_small_multiples_config()` generates PBIR small multiples for bar, line, area, scatter, column charts; auto-detects suitable fields
- **Proportional layout**: `_calculate_proportional_layout()` scales Tableau dashboard zone positions to PBI page coordinates with overlap detection; grid fallback for missing positions
- **Dynamic reference lines**: `_build_dynamic_reference_line()` generates average, median, percentile, min, max, and trend lines via PBIR analytics pane config
- **Data bars**: `_build_data_bar_config()` generates conditional formatting data bars for table/matrix visuals with positive/negative colors

### PBIP Generator Enhancements (`powerbi_import/pbip_generator.py`)
- **Rich text textboxes**: `_parse_rich_text_runs()` converts Tableau formatted text (bold, italic, color, font_size, URL) to PBI paragraph textStyle format; handles `#AARRGGBB` → `#RRGGBB` conversion, newline paragraph splitting, hyperlinks
- **Output format control**: `--output-format` flag (pbip/tmdl/pbir) controls which artifacts are generated — tmdl-only skips report, pbir-only skips semantic model

### TMDL Generator Enhancements (`powerbi_import/tmdl_generator.py`)
- **Composite model mode**: `model_mode='composite'` enables DirectQuery + Import hybrid; heuristic assigns >10-column tables to directQuery, ≤10 to import
- **Parameterized sources**: `_write_expressions_tmdl()` detects server/database from M queries and generates `ServerName`/`DatabaseName` M parameters for environment portability

### M Query Builder Enhancements (`tableau_export/m_query_builder.py`)
- **Microsoft Fabric Lakehouse connector**: `_gen_m_fabric_lakehouse()` — `Lakehouse.Contents(null, workspace_id, lakehouse_id)`
- **Microsoft Dataverse connector**: `_gen_m_dataverse()` — `CommonDataService.Database(org_url)`
- **Connection templating**: `apply_connection_template()` replaces `${ENV.*}` placeholders in M queries; `templatize_m_query()` reverse-generates templates from hardcoded values

### CLI & Pipeline (`migrate.py`)
- **`--mode`**: Select model mode (import / directquery / composite)
- **`--output-format`**: Select output artifacts (pbip / tmdl / pbir)
- **`--rollback`**: Auto-backup previous output before regeneration (timestamped `shutil.copytree`)
- **`--config`**: Load migration settings from JSON config file with CLI override precedence

### Configuration & Plugin Architecture
- **`powerbi_import/config/migration_config.py`**: `MigrationConfig` class with JSON file support, section accessors (source, output, model, connections, plugins), `from_file()`, `from_args()`, `save()`
- **`powerbi_import/plugins.py`**: `PluginBase` with 7 hook methods (pre/post extraction/generation, transform_dax, transform_m_query, custom_visual_mapping); `PluginManager` with register/load/call/apply

### Testing
- **Sprint feature tests** (`tests/test_sprint_features.py`): 78 tests covering REGEXP, nested LOD, string+, Small Multiples, proportional layout, dynamic ref lines, data bars, rich text, composite model, new connectors, templating, config, plugins, CLI args
- **Performance benchmarks** (`tests/test_performance.py`): 9 tests with thresholds for DAX conversion, M query generation, TMDL generation, visual container batch creation
- **Snapshot tests** (`tests/test_snapshot.py`): Golden file tests for M queries (5 connectors), DAX formulas (5 patterns), TMDL files (2 artifacts)
- **Integration tests** (`tests/test_integration.py`): End-to-end pipeline tests — full generation, semantic model structure, report structure, output format branching, culture passthrough, mode passthrough, validation, migration report, batch mode
- **Test count**: 1278 → **1387** (109 new tests, all passing)

### CI/CD
- **Updated CI pipeline** (`.github/workflows/ci.yml`): Switched from `unittest discover` to `pytest`; added performance, snapshot, and integration test stages

---

## v3.6.0 — Sprint 1: Testing & Infrastructure Hardening

### Testing Framework

- **Test factories** (`tests/factories.py`): Builder-pattern factories for Datasource, Worksheet, Dashboard, Calculation, Parameter, and full Model fixtures. Quick builders: `make_simple_model()`, `make_multi_table_model()`, `make_complex_model()`
- **DAX coverage tests** (`tests/test_dax_coverage.py`): 150+ tests covering under-tested DAX converter paths — string, date, math, stats, LOD, table calc, RUNNING/TOTAL, special functions, R/Python script mappings, `_split_args`, `_extract_function_body`, `_dax_to_m_expression`
- **Generation coverage tests** (`tests/test_generation_coverage.py`): 40+ tests for visual type resolution, data roles, config templates, `build_query_state`, validator DAX formula checks, migration report classification/scoring, TMDL generation integration, visual container creation
- **Error path tests** (`tests/test_error_paths.py`): Negative and edge-case tests for malformed/empty/None inputs, validator error handling, Tableau function leak detection, factory edge cases
- **Test count**: 887 → **1278** (391 new tests, all passing)

### Infrastructure & DevOps

- **Coverage config** (`.coveragerc`): Targets `tableau_export/` and `powerbi_import/`; 80% minimum threshold; HTML report to `htmlcov/`
- **Version bump script** (`scripts/version_bump.py`): Automated `major`/`minor`/`patch` versioning with `--dry-run`; updates `migrate.py`, `CHANGELOG.md`, and `pyproject.toml`
- **Structured exit codes** (`migrate.py`): `ExitCode` IntEnum — SUCCESS(0), FILE_NOT_FOUND(2), EXTRACTION_FAILED(3), GENERATION_FAILED(4), VALIDATION_FAILED(5), ASSESSMENT_FAILED(6), BATCH_PARTIAL_FAIL(7), KEYBOARD_INTERRUPT(130)
- **Error logging**: `logger.error()` with `exc_info=True` on extraction and generation failures

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
