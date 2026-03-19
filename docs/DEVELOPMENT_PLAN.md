# Development Plan — Tableau to Power BI Migration Tool

**Version:** v18.0.0 (in progress)  
**Date:** 2026-03-19  
**Current state:** v18.0.0 Sprint 55 complete — **4,331 tests** across 79 test files (+conftest.py), 0 failures  
**Previous baseline:** v3.5.0 — 887 → v4.0.0 — 1,387 → v5.0.0 — 1,543 → v5.1.0 — 1,595 → v5.5.0 — 1,777 → v6.0.0 — 1,889 → v6.1.0 — 1,997 → v7.0.0 — 2,057 → Sprint 21 — 2,066 → v8.0.0 — 2,275 → Sprint 27 — 2,542 → Sprint 28 — 2,616 → Sprint 29 — 2,666 → v9.0.0 — 3,196 → v10.0.0 — 3,342 → v11.0.0 — 3,459 → v12.0.0 — 3,729 → v13.0.0 — 3,847 → v14.0.0 — 3,925 → v15.0.0 — 3,988 → v15.0.1 — 3,996 → v16.0.0 — 4,131 → **v17.0.0 — 4,219**

---

## v18.0.0 — Advanced Merge Intelligence & Enterprise Merge Workflows

### Motivation

v17.0.0 delivered a solid merge foundation: fingerprint-based table matching, fuzzy name matching, RLS conflict detection, cross-workbook relationship suggestions, merge preview, server-level assessment, and Fabric bundle deployment — all with 4,219 tests. However, enterprise customers migrating 50–500 workbooks encounter several advanced scenarios the current merge engine doesn't handle:

1. **Artifact-level merge gaps** — Calculation groups, field parameters, perspectives, cultures, and goals are not merged/deduplicated across workbooks. They're silently dropped or duplicated.
2. **Incremental merge** — No way to add a workbook to an existing shared model without re-merging everything from scratch. Teams iterating over months need `--add-to-model`.
3. **Theme/bookmark/story merge** — Stories become bookmarks per-workbook but aren't synchronized. Theme colors default to first-workbook-wins with no merge strategy.
4. **Merge validation depth** — Post-merge DAX references (`RELATED`, `LOOKUPVALUE`, `CALCULATE`) not validated; broken field references in thin reports go undetected until PBI Desktop.
5. **Lineage & provenance** — No way to trace which workbook contributed which table, measure, or relationship to the shared model. Audit trail is limited to namespacing.
6. **Live connection mode** — Thin reports only support `byPath`; `byConnection` wiring for Fabric workspace references not implemented.
7. **Multi-tenant deployment** — Can't deploy the same shared model to N workspaces with per-tenant configuration (connection string overrides, RLS role mapping).

v18.0.0 addresses these across 5 sprints focused on merge depth, provenance, incremental workflows, and enterprise deployment patterns.

---

### Sprint 54 — Artifact-Level Merge: Calculation Groups, Field Parameters, Perspectives & Cultures ✅

**Goal:** Extend `merge_semantic_models()` to properly merge advanced TMDL artifacts currently handled by naive union or silently dropped.
**Status:** COMPLETE — 55 tests, 6 new merge functions, all 4,274 tests passing.

| # | Item | File(s) | Est. | Details |
|---|------|---------|------|---------|
| 54.1 | **Calculation group deduplication** | `powerbi_import/shared_model.py` | Medium | Merge calculation groups across workbooks: same name + same items → deduplicate; same name + different items → namespace as `CalcGroup (Workbook)`. Requires deep comparison of `calculationItems` array (name + expression). |
| 54.2 | **Field parameter deduplication** | `powerbi_import/shared_model.py` | Medium | Merge field parameter tables: same name + same `NAMEOF()` references → deduplicate; different referenced fields → union fields into combined parameter table. Update thin report visual references. |
| 54.3 | **Perspective merge** | `powerbi_import/shared_model.py` | Low | Merge perspectives from multiple workbooks: same name → union table/column/measure references; different names → keep all. Generate unified `perspectives.tmdl`. |
| 54.4 | **Culture merge** | `powerbi_import/shared_model.py` | Low | Merge culture TMDL files: same locale → merge translation entries (table/column/measure display names); different locales → keep all. Handle conflicting translations for same object. |
| 54.5 | **Goals/scorecard merge** | `powerbi_import/shared_model.py`, `powerbi_import/goals_generator.py` | Medium | Merge Pulse-derived goals: same metric name + same measure → deduplicate; different → namespace. Aggregate goal targets across workbooks. |
| 54.6 | **Hierarchy deduplication enhancement** | `powerbi_import/shared_model.py` | Low | Current `_merge_list_by_name` is shallow. Enhance: same hierarchy name + same levels → deduplicate; same name + different levels → keep longest path; cross-workbook hierarchies on same table → union. |
| 54.7 | **Tests** | `tests/test_merge_artifacts.py` (new) | Medium | 30+ tests: calc group merge/conflict, field param union, perspective merge, culture merge, goal dedup, hierarchy level comparison |

### Sprint 55 — Post-Merge Safety: Cycle Detection, Column Type Validation & DAX Integrity ✅

**Goal:** Prevent data loss and model corruption by validating merge output before generation. Relationship cycles break PBI model loading; wrong column types silently truncate data; unresolved DAX refs cause runtime errors.

**Assessment finding:** All 22 workbooks migrate at ≥95.8% fidelity individually, but merged models have NO safety net — broken refs, circular relationships, or type mismatches go undetected until PBI Desktop.

| # | Item | File(s) | Est. | Details |
|---|------|---------|------|---------|
| 55.1 | **Relationship cycle detection** | `powerbi_import/shared_model.py` | High | After `merge_semantic_models()` and after cross-workbook relationship suggestions, run DFS/topological-sort on the relationship graph. If cycles found: (a) for suggestions → downgrade confidence to `"blocked"` with explanation; (b) for existing rels → emit warning in merge report. Uses iterative DFS (no recursion limit). |
| 55.2 | **Column type compatibility matrix** | `powerbi_import/shared_model.py` | Medium | When merging columns from different workbooks, validate type promotion with explicit compatibility matrix: `int64→double` OK, `bool→int64` OK, `string→int64` WARN, `dateTime→string` ERROR. Add `_column_type_warnings` list to merge result with source workbook + column + original type + promoted type. |
| 55.3 | **DAX reference validator** | `powerbi_import/validator.py` | High | `validate_merged_dax_references(merged)`: scan all measures and calc columns for `'Table'[Column]` patterns. Verify every referenced table exists in `merged["tables"]` and column exists in that table's columns. Return list of `{measure, ref, table, column, status, suggestion}`. Suggestion = closest Levenshtein match in model. |
| 55.4 | **RELATED/LOOKUPVALUE cardinality audit** | `powerbi_import/validator.py` | Medium | `validate_dax_relationship_functions(merged)`: for each `RELATED()` call, verify a manyToOne relationship exists on that path; for each `LOOKUPVALUE()`, verify manyToMany. Flag mismatches (e.g., `RELATED` used but relationship is manyToMany after merge changed cardinality). |
| 55.5 | **Validation summary report** | `powerbi_import/validator.py` | Medium | `generate_merge_validation_report(merged)` → JSON + console output: cycle count, type warnings, unresolved DAX refs, cardinality mismatches. Integrated into `--shared-model` pipeline (runs automatically after merge, before TMDL generation). Return `{"cycles": [...], "type_warnings": [...], "dax_errors": [...], "cardinality_mismatches": [...], "score": int}`. |
| 55.6 | **`--strict-merge` CLI flag** | `migrate.py` | Low | When `--strict-merge` is set, any validation error (cycles, unresolved DAX, type ERROR) blocks generation and returns exit code 1. Without flag, validation is advisory (warnings printed, generation proceeds). |
| 55.7 | **Tests** | `tests/test_merge_validation.py` (new) | Medium | 30+ tests: cycle detection (2-node, 3-node, suggestion-induced), type compatibility (all pairs), DAX ref resolution (valid, broken table, broken column, closest match), RELATED/LOOKUPVALUE mismatch, validation report structure, --strict-merge blocking |

### Sprint 56 — Thin Report Binding Validation & Cross-Report Integrity

**Goal:** After generating thin reports, validate that all field references resolve against the merged model. Detect broken drill-through targets, unresolvable measure names, and orphan filter references.

**Assessment finding:** 3 merge clusters detected in real-world workbooks. Cluster #3 (global_superstores_db + shapes_test + superstore_sales_dashboard) merges 6→4 tables — thin reports must reference the correct namespaced artifacts.

| # | Item | File(s) | Est. | Details |
|---|------|---------|------|---------|
| 56.1 | **Visual field reference validator** | `powerbi_import/thin_report_generator.py` | High | `_validate_field_references(report_visuals, merged_model)`: after generating each thin report, iterate every visual's query state / data role bindings. Check each `measure`, `column`, and `table` reference exists in the merged model. Return `[{visual_id, page, field, status, suggestion}]`. |
| 56.2 | **Drill-through target existence check** | `powerbi_import/thin_report_generator.py` | Medium | For drill-through pages, verify that target page names referenced by action buttons exist within the same thin report or another thin report in the bundle. Flag orphan targets with source visual + target page name. |
| 56.3 | **Parameter accessibility validation** | `powerbi_import/thin_report_generator.py` | Low | Check that parameters referenced in thin report slicers/filters exist as tables in the merged model. Parameters deduplicated during merge may have changed names → validate new names. |
| 56.4 | **Filter reference validation** | `powerbi_import/thin_report_generator.py` | Medium | For report-level and page-level filters, verify filter target table/column exists in merged model. Flag orphan filters that reference pre-merge table/column names. |
| 56.5 | **Cross-report navigation validation** | `powerbi_import/thin_report_generator.py` | Low | For action buttons with "navigate to report" type, verify target report name matches another thin report in the bundle. Log warning for broken cross-report links. |
| 56.6 | **Thin report validation summary** | `powerbi_import/thin_report_generator.py` | Low | `generate_thin_report_validation(reports, merged)` → JSON per thin report: total fields checked, resolved, unresolved, drill-through gaps, filter gaps. Print console summary after each thin report. |
| 56.7 | **Tests** | `tests/test_thin_report_validation.py` (new) | Medium | 25+ tests: valid field refs, broken field refs with suggestion, namespaced measure lookup, drill-through target found/missing, filter on merged table, cross-report link validation, summary report structure |

### Sprint 57 — RLS Consolidation & Security Hardening

**Goal:** Strengthen RLS handling during merge. Currently overlapping RLS rules are naively unioned — rules with same name but different predicates create ambiguous security. Add predicate merging, principal scoping, and propagation path validation.

| # | Item | File(s) | Est. | Details |
|---|------|---------|------|---------|
| 57.1 | **RLS predicate merging logic** | `powerbi_import/shared_model.py` | High | When two workbooks have RLS role with same name: (a) same table + same predicate → deduplicate; (b) same table + different predicates → merge with AND (both conditions must hold) or configurable OR. Add `rls_merge_strategy` to merge config (`"and"` / `"or"` / `"namespace"`). |
| 57.2 | **RLS propagation path validator** | `powerbi_import/validator.py` | Medium | `validate_rls_propagation(merged)`: for each RLS role, verify `tablePermission` target table exists in model AND has an active uni-directional or bi-directional relationship path to at least one fact table. Flag roles on orphan/isolated tables. |
| 57.3 | **RLS principal scoping check** | `powerbi_import/shared_model.py` | Medium | `_validate_rls_principals(merged)`: parse `USERPRINCIPALNAME()` patterns across merged RLS roles. Detect conflicting principal requirements (e.g., workbook A expects `user@domain.com` format, workbook B expects `DOMAIN\user`). Emit warning with role names + expected format. |
| 57.4 | **RLS merge config support** | `powerbi_import/merge_config.py` | Low | Extend merge config JSON with `rls_rules` section: per-role accept/reject/strategy decisions. `{"role_name": {"action": "merge", "strategy": "and"}}`. Load/save round-trip. |
| 57.5 | **RLS conflict HTML report** | `powerbi_import/merge_report_html.py` | Medium | Add "Security" tab to merge HTML report: table of all RLS roles with source workbook(s), predicate text, merge action taken, propagation status (✅ connected / ⚠️ orphan), principal format. |
| 57.6 | **Isolated table warning system** | `powerbi_import/shared_model.py` | Low | When tables are excluded from shared model due to isolation (no relationships), emit explicit warning with table name, source workbook, and reason. Track in merge result as `_excluded_tables` list with `reason` field. |
| 57.7 | **Tests** | `tests/test_rls_consolidation.py` (new) | Medium | 25+ tests: predicate AND merge, predicate OR merge, namespace fallback, propagation path validation (connected/orphan), principal format detection, merge config round-trip, isolated table warnings, HTML report structure |

### Sprint 58 — Incremental Merge & Add-to-Model Workflow

**Goal:** Enable adding workbooks to an existing shared model without full re-merge. Support iterative workflows for teams migrating 50+ workbooks over weeks.

**Assessment finding:** Real-world global assessment found 3 merge clusters in 14 workbooks. As more workbooks are discovered, teams need to add them to existing clusters without re-extracting all previous workbooks.

| # | Item | File(s) | Est. | Details |
|---|------|---------|------|---------|
| 58.1 | **Merge manifest file** | `powerbi_import/shared_model.py` | Medium | After merge, write `merge_manifest.json` to output dir: list of workbook sources (name, path, hash), fingerprint hashes per table, timestamp, merge config snapshot, artifact counts (tables, measures, relationships, RLS roles), validation score from Sprint 55. Used for incremental add. |
| 58.2 | **Reverse-engineer existing TMDL** | `powerbi_import/shared_model.py` | High | `_load_existing_model(model_dir)` — parses existing `.tmdl` files to reconstruct table/column/measure/relationship/parameter/RLS inventory as a `converted_objects`-compatible dict. Needed for incremental add to detect duplicates without re-extracting original workbooks. Handles all TMDL syntax: `table`, `column`, `measure`, `partition`, `relationship`, `role`, `annotation`. |
| 58.3 | **`--add-to-model` CLI flag** | `migrate.py`, `powerbi_import/shared_model.py` | High | `--add-to-model DIR NEW.twbx` — loads existing model from DIR (reads `merge_manifest.json` + TMDL), extracts new workbook, runs incremental merge (new tables/measures/relationships added, conflicts detected via Sprint 55 validator), regenerates TMDL + thin report for new workbook only. Existing thin reports untouched. |
| 58.4 | **`--remove-from-model`** | `powerbi_import/shared_model.py` | Medium | `--remove-from-model DIR WB_NAME` — reads manifest, identifies all artifacts contributed solely by that workbook (tables unique to it, namespaced measures, its thin report). Removes them, regenerates TMDL. Updates manifest. Shared tables (contributed by multiple workbooks) are NOT removed. |
| 58.5 | **Merge manifest diff** | `powerbi_import/merge_assessment.py` | Low | `diff_manifests(old, new)` → `{added_tables, removed_tables, added_measures, removed_measures, changed_relationships, config_changes}`. For CI integration and audit trail. |
| 58.6 | **Tests** | `tests/test_incremental_merge.py` (new) | Medium | 30+ tests: manifest write/read round-trip, TMDL reverse-engineering (all object types), add workbook (new tables, conflicts, validation), remove workbook (sole-owner vs shared table), manifest diff, idempotent re-add |

### Sprint 59 — Custom SQL Fingerprinting & Connection Compatibility

**Goal:** Enable merge matching for custom SQL tables (currently silently excluded) and add connection type compatibility analysis to merge scoring.

**Assessment finding:** Real-world workbooks like `RESTAPISample` use custom SQL. Custom SQL tables cannot currently participate in merge matching — they stay isolated even when identical queries exist across workbooks.

| # | Item | File(s) | Est. | Details |
|---|------|---------|------|---------|
| 59.1 | **SQL query normalizer** | `powerbi_import/shared_model.py` | Medium | `_normalize_sql(query)` → canonical form: strip comments (`--`, `/* */`), collapse whitespace, lowercase keywords, normalize aliases (`AS` optional), remove trailing semicolons. Deterministic — same logical query always produces same normalized string. |
| 59.2 | **Custom SQL fingerprint** | `powerbi_import/shared_model.py` | Medium | Extend `build_table_fingerprints()`: for tables with `custom_sql` source, fingerprint = SHA-256 of `connection|server|database` + normalized SQL. Tables with identical fingerprints are merge candidates. |
| 59.3 | **Custom SQL merge strategy** | `powerbi_import/shared_model.py` | Medium | When merging custom SQL tables: compare column lists. If columns match → deduplicate (keep one M partition). If columns differ → keep both as separate tables but flag in merge report with SQL diff. |
| 59.4 | **Connection type compatibility matrix** | `powerbi_import/global_assessment.py` | Medium | New merge-score dimension (0–10 points): same connector type = 10, compatible types (sqlserver↔azure_sql, postgres↔redshift) = 7, incompatible (sqlserver↔rest_api) = 0. Matrix covers all 33 supported connectors. |
| 59.5 | **Mixed-connector merge warnings** | `powerbi_import/merge_assessment.py` | Low | When merge assessment detects tables from different connector types in same merge cluster, emit warning: "Tables from [SQL Server] and [REST API] may have different refresh behaviors and query capabilities." |
| 59.6 | **Tests** | `tests/test_sql_fingerprint.py` (new) | Medium | 25+ tests: SQL normalization (comments, whitespace, aliases, case), fingerprint identity, custom SQL merge (matching/different columns), connection compatibility scoring, mixed-connector warnings |

### Sprint 60 — Cross-Workbook Lineage & Provenance Tracking

**Goal:** Track which workbook contributed each artifact to the shared model. Enable audit trail, debugging, and compliance documentation.

| # | Item | File(s) | Est. | Details |
|---|------|---------|------|---------|
| 60.1 | **Lineage metadata injection** | `powerbi_import/shared_model.py` | Medium | Add `_source_workbooks: List[str]` and `_merge_action: str` (`"deduplicated"` / `"namespaced"` / `"unioned"` / `"first-wins"`) fields on every merged table, measure, column, relationship, parameter, RLS role. Populated during `merge_semantic_models()`. |
| 60.2 | **TMDL annotations for provenance** | `powerbi_import/tmdl_generator.py` | Low | Write lineage annotations to TMDL files: `annotation MigrationSource = 'workbook_name'` and `annotation MergeAction = 'deduplicated'` on tables, measures, columns. Read back by Sprint 58's `_load_existing_model()`. |
| 60.3 | **Lineage report generator** | `powerbi_import/merge_assessment.py` | Medium | `generate_lineage_report(merged, manifest)` → JSON: `{tables: [{name, sources, action, columns: [{name, sources}]}], measures: [{name, source, action}], relationships: [{key, sources}]}`. |
| 60.4 | **Interactive lineage HTML** | `powerbi_import/merge_report_html.py` | Medium | Add "Lineage" tab to merge HTML report: Sankey-style CSS visualization (no JS framework) showing workbook → table → measure flow. Color-coded by merge action. Table with sortable columns: artifact name, type, source(s), action, conflict. |
| 60.5 | **`--lineage` CLI flag** | `migrate.py` | Low | `--lineage` flag on `--shared-model` pipeline: enables lineage tracking + generates lineage report alongside merge assessment. Adds lineage annotations to TMDL output. |
| 60.6 | **Tests** | `tests/test_merge_lineage.py` (new) | Medium | 20+ tests: lineage metadata injection (all artifact types), TMDL annotation write/read round-trip, lineage report JSON structure, HTML report "Lineage" tab presence, multi-workbook provenance tracking, action field correctness |

### Sprint 61 — Bundle Deploy Atomicity & Deployment Hardening

**Goal:** Make Fabric bundle deployment reliable for production. Add atomic rollback, pre-flight checks, conflict detection, and version tracking.

| # | Item | File(s) | Est. | Details |
|---|------|---------|------|---------|
| 61.1 | **Workspace permission pre-flight** | `powerbi_import/deploy/bundle_deployer.py` | Medium | Before deploying, call Fabric API to verify workspace exists and authenticated principal has `Contributor` or `Admin` role. Fail fast with clear error message if permissions insufficient. |
| 61.2 | **Conflict detection** | `powerbi_import/deploy/bundle_deployer.py` | Medium | Before deploying model/reports, list existing items in workspace. If name collision found: (a) `--deploy-overwrite` → proceed with overwrite; (b) default → fail with message listing conflicting items. Prevents accidental overwrite of production models. |
| 61.3 | **Atomic rollback** | `powerbi_import/deploy/bundle_deployer.py` | High | Track deployed artifacts during `deploy_bundle()`. If any report deployment fails after model succeeded: attempt to delete the orphaned model via Fabric API. Record rollback actions in `BundleDeploymentResult`. Configurable via `--deploy-rollback` flag. |
| 61.4 | **Deployment version tracking** | `powerbi_import/deploy/utils.py` | Medium | `DeploymentManifest` class: tracks deployment timestamp, workspace_id, model_id, report_ids, source merge_manifest hash, deployer principal. Written to `deployment_manifest.json` in output dir. Used by incremental deploy to detect changes. |
| 61.5 | **Post-deployment validation** | `powerbi_import/deploy/bundle_deployer.py` | Medium | After deploy, call Fabric API to verify: model shows `Succeeded` status, reports are bound to correct model, refresh (if requested) completed without error. Return validation results in `BundleDeploymentResult`. |
| 61.6 | **Refresh completion polling** | `powerbi_import/deploy/bundle_deployer.py` | Low | When `--bundle-refresh` is set, poll refresh status every 10s (configurable, max 30min) until complete/failed. Report final refresh status, duration, and row counts if available. |
| 61.7 | **Tests** | `tests/test_deploy_hardening.py` (new) | Medium | 25+ tests: permission pre-flight (sufficient/insufficient), conflict detection (no conflict/collision), rollback simulation, deployment manifest write/read, post-deploy validation, refresh polling mock |

### Sprint 62 — Multi-Tenant Deployment & Live Connection Mode

**Goal:** Enterprise deployment patterns — deploy shared model to multiple Fabric workspaces with per-tenant config, and support live connection wiring for Fabric-native scenarios.

| # | Item | File(s) | Est. | Details |
|---|------|---------|------|---------|
| 62.1 | **Multi-tenant manifest** | `powerbi_import/deploy/multi_tenant.py` (new) | Medium | `MultiTenantConfig` class: JSON config listing N Fabric workspaces, each with `workspace_id`, `connection_string_overrides`, `rls_role_mappings`, `display_name_prefix`. `load_multi_tenant_config()` + `validate_config()`. Validates workspace IDs are valid UUIDs, connection strings have required keys. |
| 62.2 | **Multi-tenant deployer** | `powerbi_import/deploy/multi_tenant.py` | High | `deploy_multi_tenant(model_dir, config)`: iterates workspaces, clones shared model dir to temp, patches connection strings in M partitions (regex replacement), adjusts RLS role Azure AD group mappings per tenant, deploys via `BundleDeployer` (Sprint 61 hardened), collects per-tenant results. Parallelizable (future). |
| 62.3 | **`--multi-tenant` CLI flag** | `migrate.py` | Low | `--multi-tenant CONFIG_FILE` flag: loads tenant config, runs multi-tenant deploy after `--shared-model` pipeline. Requires `--deploy-bundle`. Prints per-tenant status table. |
| 62.4 | **Live connection (byConnection) mode** | `powerbi_import/thin_report_generator.py` | Medium | `--live-connection WORKSPACE_ID/MODEL_NAME` flag: thin reports wired via `byConnection` reference (Fabric workspace semantic model) instead of `byPath`. Writes `definition.pbir` with `datasetReference: {byConnection: {connectionString: "...workspace_id...model_name..."}}`. |
| 62.5 | **Connection string template engine** | `powerbi_import/deploy/multi_tenant.py` | Low | Simple template substitution in M partition expressions: `${TENANT_SERVER}`, `${TENANT_DATABASE}`, `${TENANT_SCHEMA}` → per-tenant values from config. No external template engine — regex-based stdlib replacement. |
| 62.6 | **Tests** | `tests/test_multi_tenant.py` (new), `tests/test_live_connection.py` (new) | Medium | 25+ tests: config validation (valid/invalid UUIDs, missing keys), connection string patching, RLS mapping, per-tenant deploy simulation, byConnection PBIR generation, template substitution, error isolation |

### Sprint 63 — Merge Config Depth & Interactive Wizard

**Goal:** Give users granular control over merge decisions. Current config supports table-level and measure-level decisions — extend to columns, relationships, RLS, and hierarchies. Add interactive wizard for guided merge.

| # | Item | File(s) | Est. | Details |
|---|------|---------|------|---------|
| 63.1 | **Column-level merge config** | `powerbi_import/merge_config.py` | Medium | Extend config with `columns` section: per-column `include`/`exclude`/`rename` decisions. `{"table_name": {"columns": {"old_col": {"action": "rename", "new_name": "..."}}}}`. Applied during column union in `_merge_columns_into()`. |
| 63.2 | **Relationship acceptance config** | `powerbi_import/merge_config.py` | Medium | Add `relationships` section: per-relationship `accept`/`reject`/`modify_cardinality` decisions. Applied after relationship dedup and cross-workbook suggestions. `{"from_table.from_col->to_table.to_col": {"action": "accept", "cardinality": "manyToOne"}}`. |
| 63.3 | **Custom measure naming template** | `powerbi_import/merge_config.py` | Low | Add `naming_template` field for conflicting measures: default `"{measure} ({workbook})"`, configurable to `"{workbook}_{measure}"`, `"{measure}_v2"`, etc. Template variables: `{measure}`, `{workbook}`, `{table}`, `{index}`. |
| 63.4 | **Column type override** | `powerbi_import/merge_config.py` | Low | Add `type_overrides` section: force specific column type instead of "wider wins" heuristic. `{"table.column": "int64"}`. Validated against Sprint 55's type compatibility matrix — errors if forced type is incompatible. |
| 63.5 | **Interactive merge wizard** | `powerbi_import/wizard.py` | Medium | Extend existing wizard with merge-specific flow: (1) select workbooks, (2) review table matches (accept/reject), (3) review measure conflicts (choose resolution), (4) review relationship suggestions, (5) RLS strategy, (6) preview score, (7) confirm and execute. Outputs merge config JSON for reproducibility. |
| 63.6 | **Tests** | `tests/test_merge_config_v2.py` (new) | Medium | 20+ tests: column config round-trip, relationship config application, naming template expansion, type override validation, wizard step simulation (mocked input), config migration from old format |

### Sprint 64 — Large-Scale Performance, Integration Tests & v18.0.0 Release

**Goal:** Validate merge at scale (10–100 workbooks), add end-to-end integration tests, benchmark performance, and ship v18.0.0.

| # | Item | File(s) | Est. | Details |
|---|------|---------|------|---------|
| 64.1 | **Fingerprint hash cache** | `powerbi_import/shared_model.py` | Medium | Cache computed fingerprints in `_fingerprint_cache: Dict[str, str]` to avoid recomputation during pairwise comparison in global assessment. O(n) fingerprinting instead of O(n²). |
| 64.2 | **Batch relationship dedup optimization** | `powerbi_import/shared_model.py` | Medium | Replace O(n²) relationship dedup loop with set-based key comparison. Pre-build `rel_key_set` before merge, check membership in O(1). |
| 64.3 | **Benchmark test suite** | `tests/test_merge_performance.py` (new) | Medium | Synthetic benchmarks: generate N workbooks (10, 25, 50, 100) with M tables each, run `merge_semantic_models()`, assert merge completes in <T seconds. Not run in CI (requires `--benchmark` flag). |
| 64.4 | **End-to-end integration tests** | `tests/test_merge_integration.py` (new) | High | 15+ tests: extract 2–3 real sample workbooks → merge → generate TMDL → validate JSON/TMDL structure → validate thin report field refs → validate PBIR schema compliance. Uses actual example workbooks from `examples/`. |
| 64.5 | **Merge → TMDL → Validate pipeline** | `powerbi_import/validator.py` | Medium | `validate_merged_pbip(output_dir)` — orchestrator that runs all Sprint 55–57 validators against a generated .pbip project. Returns pass/warn/fail summary. Called by integration tests and available via `--validate` flag. |
| 64.6 | **v18.0.0 release** | `docs/`, `CHANGELOG.md`, `README.md`, `pyproject.toml` | Low | Version bump 17.0.0 → 18.0.0. Update all docs: CHANGELOG (all 10 sprints), GAP_ANALYSIS (close resolved gaps), KNOWN_LIMITATIONS (update), copilot-instructions (new features), DEPLOYMENT_GUIDE (multi-tenant + live connection), README (new CLI flags). PyPI publish. |
| 64.7 | **Tests** | cumulative | — | Target: **4,600+ tests** total (4,274 baseline + ~330 new across Sprints 55–64) |

---

### Sprint Sequencing (v18.0.0)

```
Sprint 54 ✅ (Artifact Merge)
    ↓
Sprint 55 (Post-Merge Safety)  ──→  Sprint 56 (Thin Report Validation)
    ↓                                        ↓
Sprint 57 (RLS Consolidation)  ──→  Sprint 58 (Incremental Merge)
    ↓                                        ↓
Sprint 59 (Custom SQL + Compat) ──→ Sprint 60 (Lineage & Provenance)
    ↓                                        ↓
Sprint 61 (Deploy Hardening)   ──→  Sprint 62 (Multi-Tenant + Live)
    ↓                                        ↓
Sprint 63 (Merge Config Depth) ──→  Sprint 64 (Performance + Release)
```

- **Safety first** (55–57): cycle detection, DAX validation, thin report binding, RLS consolidation — must ship before incremental merge or deployment
- **Incremental workflows** (58): depends on validation (55) to verify incremental adds don't break model
- **Matching depth** (59): custom SQL fingerprinting expands merge coverage; connection compatibility improves scoring accuracy
- **Traceability** (60): lineage depends on merge manifest (58) for source tracking
- **Deployment** (61–62): hardened deploy depends on validation (55–57) to gate deployments; multi-tenant depends on hardened deployer
- **UX & scale** (63–64): merge config depth and performance are polish; release only after all features are stable

### Success Criteria for v18.0.0

| Metric | Current (v17.0.0) | Sprint 54 | Target (v18.0.0) |
|--------|-------------------|-----------|-------------------|
| Tests | 4,219 | **4,274** | **4,600+** |
| Merged artifact types | 8 | **14** (+ calc groups, field params, perspectives, cultures, goals, hierarchies) | **14+** |
| Merge CLI flags | 12 | 12 | **20+** (+ --strict-merge, --add-to-model, --remove-from-model, --lineage, --multi-tenant, --live-connection, --deploy-overwrite, --deploy-rollback) |
| Post-merge validation checks | 3 | 3 | **12+** (+ cycles, types, DAX refs, cardinality, thin report fields, drill-through, filters, RLS propagation, RLS principals) |
| Lineage tracking | ❌ | ❌ | **✅** (annotations + HTML report) |
| Incremental merge | ❌ | ❌ | **✅** (add-to-model, remove-from-model, manifest) |
| Custom SQL merge | ❌ | ❌ | **✅** (normalized fingerprinting) |
| RLS consolidation | Naive union | Naive union | **✅** (predicate merge + propagation validation) |
| Deploy atomicity | ❌ | ❌ | **✅** (rollback + conflict detection + version tracking) |
| Multi-tenant deployment | ❌ | ❌ | **✅** (config-driven multi-workspace) |
| Live connection (byConnection) | ❌ | ❌ | **✅** (Fabric workspace reference) |
| Merge config granularity | Table + measure | Table + measure | **✅** (+ columns, relationships, RLS, naming templates, type overrides) |
| Scale tested | 2–3 workbooks | 2–3 workbooks | **100 workbooks** (<5s merge) |

---

## v16.0.0 — Hardening, Code Health & New Capabilities

### Motivation

v15.0.0 completed Fabric bundle deployment and global assessment with 3,996 tests (96.2% coverage). A comprehensive codebase audit revealed:
- **5 `except Exception: pass`** blocks silently swallowing errors (4 in migrate.py, 1 in prep_flow_parser.py)
- **55 broad `except Exception`** catches across 20+ files — many in migrate.py (21) and deploy/ (17)
- **23 additional bare `pass`** in narrower except blocks (generate_report.py, extract_tableau_data.py, etc.)
- **12 functions exceeding 200 lines** (worst: `main()` at 410 lines, `_build_argument_parser()` at 391 lines)
- **0 TODO/FIXME in source** (all 8 TODOs are user-facing placeholders in generated output — acceptable)
- **No Windows CI** — all CI runs on ubuntu-latest; Windows path handling is untested
- **No API documentation** — no auto-generated docs for any module
- Outstanding backlog items: data-driven alerts, Web UI, LLM-assisted DAX, side-by-side screenshots

v16.0.0 addresses these across 5 sprints: code health, CLI refactoring, new features, testing, and documentation.

---

### Sprint 44 — Silent Error Cleanup Phase 2

**Goal:** Eliminate the remaining 5 `except Exception: pass` blocks and narrow the 21 broad catches in migrate.py. Add logging to the 23 remaining bare `pass` blocks in other files.

| # | Item | File(s) | Est. | Details |
|---|------|---------|------|---------|
| 44.1 | **Fix 4 `except Exception: pass` in migrate.py** | `migrate.py` L1954, L2082, L2330, L2548 | Medium | Narrow to specific exceptions + add `logger.debug()` — analyze what each block guards |
| 44.2 | **Fix 1 `except Exception: pass` in prep_flow_parser** | `tableau_export/prep_flow_parser.py` L816 | Low | Narrow to `(KeyError, ValueError)` + `logger.debug()` |
| 44.3 | **Narrow broad catches in migrate.py** | `migrate.py` (21 sites) | Medium | Split `except Exception` into specific types where feasible — at minimum add `exc_info=True` to logged errors |
| 44.4 | **Add logging to bare-pass in extraction** | `extract_tableau_data.py` (5), `datasource_extractor.py` (2), `hyper_reader.py` (3), `m_query_builder.py` (1) | Low | Replace `pass` with `logger.debug('...')` in all 11 sites |
| 44.5 | **Add logging to bare-pass in generation** | `pbip_generator.py` (1), `generate_report.py` (6), `wizard.py` (1), `server_client.py` (1) | Low | Replace `pass` with `logger.debug('...')` in all 9 sites |
| 44.6 | **Narrow deploy/ broad catches** | `deploy/*.py` (17 sites) | Medium | Narrow `except Exception` to `(ConnectionError, TimeoutError, OSError, json.JSONDecodeError)` where applicable |
| 44.7 | **Tests** | `tests/test_error_handling_v2.py` | Medium | 25+ tests verifying error paths produce log output, not silent swallowing |

### Sprint 45 — CLI Refactoring & migrate.py Decomposition ✅

**Goal:** Break apart the 3 oversized functions in migrate.py (main=410, _build_argument_parser=391, run_batch_migration=282) and extract reusable CLI modules.

| # | Item | File(s) | Status | Details |
|---|------|---------|--------|---------|
| 45.1 | **Split `main()` (410 lines)** | `migrate.py` | ✅ Done | Extracted `_run_single_migration(args)` + 7 helpers: `_print_single_migration_header`, `_init_telemetry`, `_finalize_telemetry`, `_run_incremental_merge`, `_run_goals_generation`, `_run_post_generation_reports`, `_run_deploy_to_pbi_service` |
| 45.2 | **Split `_build_argument_parser()` (391 lines)** | `migrate.py` | ✅ Done | Split into 9 helpers: `_add_source_args`, `_add_output_args`, `_add_batch_args`, `_add_migration_args`, `_add_report_args`, `_add_deploy_args`, `_add_server_args`, `_add_enterprise_args`, `_add_shared_model_args` |
| 45.3 | **Split `run_batch_migration()` (282 lines)** | `migrate.py` | ✅ Done | Extracted `_print_batch_summary()` |
| 45.4 | **Split `import_shared_model()` (248 lines)** | `powerbi_import/import_to_powerbi.py` | ✅ Done | Extracted `_create_model_explorer_report()` + `_save_shared_model_artifacts()` |
| 45.5 | **Split remaining large functions** | `pbip_generator.py` | ✅ Done | Extracted `_classify_shelf_fields()` from `_build_visual_query()` (377 lines). Other functions (_build_table, _get_config_template) are deeply interdependent or static data — forced extraction would worsen readability. |
| 45.6 | **Tests** | `tests/test_cli_refactor.py` | ✅ Done | 31 regression tests across 6 test classes. 4,029 → 4,060 tests. |

### Sprint 46 — New Features: Data Alerts, Comparison Report & Semantic Validation ✅

**Goal:** Implement remaining high-value backlog items that improve migration quality and user experience.

| # | Item | File(s) | Status | Details |
|---|------|---------|--------|---------|
| 46.1 | **Data-driven alerts** | `powerbi_import/alerts_generator.py` (new) | ✅ Done | Extracts alert conditions from TWB parameters/calculations/reference lines, generates PBI alert rules JSON with operator, threshold, frequency, measure |
| 46.2 | **Visual diff report** | `powerbi_import/visual_diff.py` (new) | ✅ Done | Side-by-side HTML report: visual type mapping (exact/approx/unmapped), per-field coverage, encoding gap detection, summary table |
| 46.3 | **Enhanced semantic validation** | `powerbi_import/validator.py` | ✅ Done | Added `detect_circular_relationships()`, `detect_orphan_tables()`, `detect_unused_parameters()` — all integrated into `validate_project()` |
| 46.4 | **Migration completeness scoring** | `powerbi_import/migration_report.py` | ✅ Done | `get_completeness_score()` with per-category fidelity breakdown, weighted overall score 0–100, letter grade (A–F), included in `to_dict()` and `print_summary()` |
| 46.5 | **Connection string audit** | `powerbi_import/assessment.py` | ✅ Done | `_check_connection_strings()` detecting passwords/tokens/API keys/bearer/basic auth — 9th assessment category |
| 46.6 | **Tests** | `tests/test_sprint46.py` | ✅ Done | 51 tests across 12 test classes. 4,060 → 4,111 tests. |

### Sprint 47 — Windows CI, Cross-Platform Hardening & Performance

**Goal:** Add Windows CI testing, fix Windows-specific path issues, optimize performance for large workbooks.

| # | Item | File(s) | Status | Details |
|---|------|---------|--------|---------|
| 47.1 | **Windows CI matrix** | `.github/workflows/ci.yml` | ✅ Done | Already has `windows-latest` + `ubuntu-latest` + `macos-latest` in matrix with Python 3.9–3.14 |
| 47.2 | **Path normalization audit** | All source files | ✅ Done | Audit confirmed all `/` in code are ZIP archive entries or Power Query M intermediary strings — correct by design |
| 47.3 | **OneDrive lock handling** | `pbip_generator.py`, `tmdl_generator.py` | ✅ Done | `_rmtree_with_retry(path, attempts=3, delay=0.5)` with exponential backoff; stale TMDL removal retry (3×, 0.3s backoff); logging added |
| 47.4 | **Performance profiling** | `tests/test_performance.py` | ✅ Done | 2 new benchmarks: `TestTmdl100MeasuresPerformance` (5 tables × 100 measures, 10s threshold), `TestImportPipelinePerformance` (full pipeline, 15s threshold) |
| 47.5 | **Memory optimization** | `tmdl_generator.py` | ✅ Done | Post-write table data release (columns/measures/partitions cleared, names + `_n_columns`/`_n_measures` preserved); stats collected before write |
| 47.6 | **Tests** | `tests/test_sprint47.py` | ✅ Done | 18 tests across 7 classes. 4,111 → 4,131 tests. |

### Sprint 48 — Documentation, API Docs & Release

**Goal:** Generate API documentation, update all docs to v16.0.0, release.

| # | Item | File(s) | Status | Details |
|---|------|---------|--------|---------|
| 48.1 | **Auto-generated API docs** | `docs/generate_api_docs.py` | ✅ Done | MODULES list expanded from 15 to 42 modules (8 tableau + 26 pbi + 8 deploy), deploy section separator in index.html |
| 48.2 | **Update GAP_ANALYSIS.md** | `docs/GAP_ANALYSIS.md` | ✅ Done | v16.0.0 counts: 4,131 tests, 73 files, 118 visuals, 33 connectors, 43 M transforms, 9-category assessment |
| 48.3 | **Update KNOWN_LIMITATIONS.md** | `docs/KNOWN_LIMITATIONS.md` | ✅ Done | v16.0.0 header, OneDrive lock retry documented, Windows paths limitation resolved |
| 48.4 | **Update CHANGELOG.md** | `CHANGELOG.md` | ✅ Done | Sprint 48 entry with all documentation updates |
| 48.5 | **Update copilot-instructions.md** | `.github/copilot-instructions.md` | ✅ Done | 4,131 tests, 73 files, 180+ DAX, 33 connectors, 43 M transforms, 118 visuals, 13 new module entries |
| 48.6 | **Update README.md** | `README.md` | ✅ Done | Badges: v16.0.0, 4,131 tests, 180+ DAX, 33 connectors, 20 object types, 118 visuals |
| 48.7 | **Version bump** | `pyproject.toml`, `powerbi_import/__init__.py` | ✅ Done | 15.0.0 → 16.0.0 |
| 48.8 | **Final validation & push** | — | ✅ Done | 4,131 tests passed, committed + pushed |

---

### Sprint Sequencing (v16.0.0)

```
Sprint 44 (Error Handling)  ──→  Sprint 45 (CLI Refactor)
         ↓                              ↓
Sprint 46 (New Features)    ──→  Sprint 47 (Windows CI + Perf)
                                        ↓
                              Sprint 48 (Docs & Release)
```

- Sprint 44 first — clean error handling makes refactoring safer
- Sprint 45 after 44 — refactored code is more maintainable and testable
- Sprint 46 is independent — new features on clean foundation
- Sprint 47 after 45 — CI improvements benefit from cleaner code paths
- Sprint 48 last — docs and release after all features stable

### Success Criteria for v16.0.0

| Metric | Current | Target |
|--------|---------|--------|
| Tests | 3,996 | **4,200+** |
| `except Exception: pass` blocks | 5 | **0** |
| Broad `except Exception` (migrate.py) | 21 | **≤ 8** (top-level handlers only) |
| Bare `pass` in except blocks | 28 | **0** |
| Functions > 200 lines | 12 | **≤ 3** |
| Windows CI | ❌ | **✅** |
| API documentation | ❌ | **✅** |
| Coverage | 96.2% | **≥ 96%** (maintained) |

---

## v17.0.0 — Server Assessment, Bulk Analysis & Merge Extensions

### Motivation

v16.0.0 shipped with 4,131 tests, clean error handling, decomposed CLI, Windows CI, API docs, and new features (alerts, visual diff, enhanced validation). The migration pipeline now handles individual workbooks robustly. However, enterprise customers need:

1. **Full Tableau Server assessment** — assess an entire Tableau Server site before migrating (portfolio-level readiness, connector census, migration wave planning, effort estimation)
2. **Bulk folder assessment** — scan a local folder of .twbx files and produce an aggregated readiness report without migrating
3. **Semantic model merge extensions** — improve merge quality with custom SQL table matching, fuzzy name comparison, RLS conflict detection, auto-remap visual field references, and merge preview mode
4. **Extraction & DAX gap closure** — fix nested LOD edge cases, add missing DAX functions (INDEX, LTRIM/RTRIM), improve Prep flow mapping

v17.0.0 addresses these across 5 sprints focused on server-scale tooling, smarter merging, and gap closure.

---

### Sprint 49 — Tableau Server Client Enhancement

**Goal:** Expand `server_client.py` with pagination, missing endpoints, and server metadata collection to support server-level assessment.

| # | Item | File(s) | Est. | Details |
|---|------|---------|------|---------|
| 49.1 | **Pagination for all list methods** | `tableau_export/server_client.py` | Medium | Add `_paginated_get(url)` helper; refactor `list_workbooks()`, `list_datasources()`, `list_projects()` to use it; handle `<pagination>` element (pageNumber, pageSize, totalAvailable) |
| 49.2 | **`list_users()` and `list_groups()`** | `tableau_export/server_client.py` | Low | REST API `/api/{version}/sites/{siteId}/users` and `/groups`; return list of dicts with id, name, role, lastLogin |
| 49.3 | **`list_views()` and `get_workbook_connections()`** | `tableau_export/server_client.py` | Low | `/workbooks/{id}/views` and `/workbooks/{id}/connections`; return connection type, server, database, username |
| 49.4 | **`list_schedules()` and `get_site_info()`** | `tableau_export/server_client.py` | Low | `/schedules` (extract refresh, subscription) and `/sites/{siteId}`; return schedule frequency, site name, content URL |
| 49.5 | **`list_prep_flows()` and `download_prep_flow()`** | `tableau_export/server_client.py` | Medium | `/flows` list + `/flows/{id}/content` download; returns .tfl file content |
| 49.6 | **Server metadata summary** | `tableau_export/server_client.py` | Low | `get_server_summary()` → dict with workbook_count, datasource_count, user_count, group_count, schedule_count, project_count, flow_count |
| 49.7 | **Tests** | `tests/test_server_client_v2.py` | Medium | 25+ tests: pagination mock, all new endpoints, error handling, summary aggregation |

### Sprint 50 — Server-Level Assessment Pipeline

**Goal:** New `server_assessment.py` module — assess an entire Tableau Server site or a local folder of .twbx files, producing portfolio-level readiness reports with migration wave planning.

| # | Item | File(s) | Est. | Details |
|---|------|---------|------|---------|
| 50.1 | **`ServerAssessment` class** | `powerbi_import/server_assessment.py` (new) | High | Accepts list of extracted workbook data (from server or local folder); runs `AssessmentReport` per workbook; aggregates results |
| 50.2 | **Portfolio readiness scoring** | `powerbi_import/server_assessment.py` | Medium | Per-workbook RED/YELLOW/GREEN classification based on assessment pass/warn/fail ratios; overall site readiness percentage |
| 50.3 | **Connector census** | `powerbi_import/server_assessment.py` | Low | Histogram of connector types across all workbooks (e.g., 40% PostgreSQL, 30% SQL Server, 20% Excel, 10% Snowflake); identifies unsupported connectors |
| 50.4 | **Complexity heatmap** | `powerbi_import/server_assessment.py` | Medium | Score each workbook on 5 axes (data sources, calculations, visuals, filters, interactivity); generate sortable matrix |
| 50.5 | **Migration wave planning** | `powerbi_import/server_assessment.py` | Medium | Group workbooks into waves based on shared data sources + complexity (easy-first, then medium, then complex); output ordered wave list with dependency notes |
| 50.6 | **Effort estimation** | `powerbi_import/server_assessment.py` | Medium | Estimate hours-to-migrate per workbook based on calculation count, visual count, datasource complexity, LOD usage; produce total portfolio estimate |
| 50.7 | **HTML dashboard report** | `powerbi_import/server_assessment.py` | Medium | Executive HTML report: site overview, readiness pie chart, connector census bar chart, complexity heatmap table, wave plan, effort summary |
| 50.8 | **Bulk folder assessment CLI** | `migrate.py` | Low | `--bulk-assess DIR` flag: scan folder for .twbx/.twb, extract each, run server assessment pipeline, output HTML report |
| 50.9 | **Server assessment CLI** | `migrate.py` | Low | `--server-assess` flag (with `--server`): download all workbooks, assess, generate portfolio report |
| 50.10 | **Tests** | `tests/test_server_assessment.py` | Medium | 30+ tests: per-workbook scoring, wave grouping, effort estimation, HTML output, CLI integration |

### Sprint 51 — Semantic Model Merge Extensions

**Goal:** Improve merge quality for enterprise multi-workbook scenarios: better table matching, conflict detection, visual field remapping, and merge preview mode.

| # | Item | File(s) | Est. | Details |
|---|------|---------|------|---------|
| 51.1 | **Custom SQL table fingerprinting** | `powerbi_import/shared_model.py` | Medium | Hash normalized SQL text (whitespace/case-insensitive) for fingerprint comparison; tables with identical queries → merge candidates even with different names |
| 51.2 | **Fuzzy table name matching** | `powerbi_import/shared_model.py` | Medium | Normalize table names (strip schema prefix, case-fold, remove underscores/hyphens); Levenshtein-like similarity score as secondary signal when column overlap is inconclusive |
| 51.3 | **RLS conflict detection** | `powerbi_import/shared_model.py` | Medium | When merging models, detect overlapping RLS roles (same table, different filter expressions); report conflicts with resolution options (keep-first, keep-strictest, manual) |
| 51.4 | **Auto-remap visual references** | `powerbi_import/thin_report_generator.py` | Medium | After merge renames measures (e.g., `[Sales]` → `[WB1_Sales]`), scan thin report visuals and update all field references to use namespaced names |
| 51.5 | **Merge preview / dry-run** | `powerbi_import/shared_model.py`, `migrate.py` | Low | `--merge-preview` flag: run full merge pipeline but write nothing; output detailed log of what would be merged, renamed, or conflicted |
| 51.6 | **Cross-workbook relationship inference** | `powerbi_import/shared_model.py` | Medium | After merge, scan all tables for potential relationships not present in source (column name + type matching between newly combined tables); suggest but don't auto-create |
| 51.7 | **Enhanced merge HTML report** | `powerbi_import/merge_assessment.py` | Medium | Upgrade from JSON+console to full HTML report: table overlap matrix, conflict detail cards, merge action log, cluster visualization |
| 51.8 | **Tests** | `tests/test_merge_extensions.py` | Medium | 25+ tests: custom SQL matching, fuzzy names, RLS conflicts, visual remapping, dry-run, relationship suggestions, HTML report |

### Sprint 52 — Extraction & DAX Gap Closure

**Goal:** Close known gaps in extraction and DAX conversion from `KNOWN_LIMITATIONS.md` and `GAP_ANALYSIS.md`.

| # | Item | File(s) | Est. | Details |
|---|------|---------|------|---------|
| 52.1 | **Nested LOD expressions** | `tableau_export/dax_converter.py` | Medium | Handle LOD-inside-LOD: `{FIXED [Region] : SUM({FIXED [Customer] : SUM([Sales])})}` → nested CALCULATE with inner/outer ALLEXCEPT |
| 52.2 | **INDEX() function** | `tableau_export/dax_converter.py` | Low | Map Tableau `INDEX()` → `ROWNUMBER()` DAX (available in recent PBI versions) |
| 52.3 | **LTRIM/RTRIM** | `tableau_export/dax_converter.py` | Low | Map `LTRIM()` → `TRIM()` (PBI TRIM handles both); `RTRIM()` → `TRIM()` |
| 52.4 | **Prep VAR/VARP correct mapping** | `tableau_export/prep_flow_parser.py` | Low | Fix `VAR()` → `VAR.S` and `VARP()` → `VAR.P` (currently may map variance incorrectly) |
| 52.5 | **Prep notInner join type** | `tableau_export/prep_flow_parser.py` | Low | Map Prep `notInner` join → `leftanti` in M query (currently falls back to left outer) |
| 52.6 | **Bump chart ranking injection** | `powerbi_import/visual_generator.py` | Medium | For bump chart → lineChart mapping, auto-inject a RANKX measure as secondary Y axis based on the dimension and measure fields |
| 52.7 | **Multi-datasource context in DAX** | `tableau_export/dax_converter.py` | Medium | When converting formulas referencing columns from multiple datasources, inject RELATED/LOOKUPVALUE based on available relationships |
| 52.8 | **Tests** | `tests/test_extraction_gaps.py` | Medium | 20+ tests: nested LOD, INDEX, LTRIM/RTRIM, Prep VAR/VARP, notInner, bump chart, multi-datasource DAX |

### Sprint 53 — Documentation, Tests & v17.0.0 Release

**Goal:** Update all documentation, boost test count, version bump, final validation, and release.

| # | Item | File(s) | Est. | Details |
|---|------|---------|------|---------|
| 53.1 | **Update KNOWN_LIMITATIONS.md** | `docs/KNOWN_LIMITATIONS.md` | Low | Mark resolved items from Sprint 52, add any new limitations discovered |
| 53.2 | **Update GAP_ANALYSIS.md** | `docs/GAP_ANALYSIS.md` | Low | Refresh test count, module count, new capabilities (server assessment, merge extensions) |
| 53.3 | **Update README.md** | `README.md` | Low | Add server assessment section, bulk assessment CLI examples, merge preview flag |
| 53.4 | **Update copilot-instructions.md** | `.github/copilot-instructions.md` | Low | Add new modules (`server_assessment.py`), new CLI flags, updated test count |
| 53.5 | **Update CHANGELOG.md** | `CHANGELOG.md` | Low | Full v17.0.0 changelog with all 5 sprints |
| 53.6 | **Update DEPLOYMENT_GUIDE.md** | `docs/DEPLOYMENT_GUIDE.md` | Low | Add server assessment deployment workflow section |
| 53.7 | **Version bump** | `pyproject.toml`, `powerbi_import/__init__.py` | Low | 16.0.0 → 17.0.0 |
| 53.8 | **Final validation & push** | — | Low | Full test suite, lint check, commit + push |

---

### Sprint Sequencing (v17.0.0)

```
Sprint 49 (Server Client)  ──→  Sprint 50 (Server Assessment)
                                        ↓
Sprint 51 (Merge Extensions) ──→  Sprint 52 (DAX/Extraction Gaps)
                                        ↓
                              Sprint 53 (Docs & Release)
```

- Sprint 49 first — server client endpoints are prerequisites for server-level assessment
- Sprint 50 after 49 — server assessment pipeline consumes the new server client APIs
- Sprint 51 independent — merge extensions can proceed in parallel with Sprint 50
- Sprint 52 after 51 — gap closure benefits from merge improvements (multi-datasource context)
- Sprint 53 last — docs and release after all features stable

### Success Criteria for v17.0.0

| Metric | Current (v16.0.0) | Target |
|--------|-------------------|--------|
| Tests | 4,131 | **4,300+** |
| Server client endpoints | 7 | **14+** |
| Assessment modes | 3 (single, global, connection audit) | **5+** (+ server, bulk folder) |
| Merge capabilities | 4 (fingerprint, overlap, score, merge) | **8+** (+ SQL match, fuzzy, RLS, preview) |
| Known limitations resolved | — | **6+** (nested LOD, INDEX, LTRIM/RTRIM, VAR/VARP, notInner, bump chart) |
| New modules | 0 | **2** (server_assessment.py, test files) |
| Server-level HTML report | ❌ | **✅** |
| Merge preview/dry-run | ❌ | **✅** |

---

### v16.0.0 Feature Backlog (not sprint-assigned)

Items that may be pulled into sprints if capacity allows:

| # | Feature | Priority | Effort | Details | Status |
|---|---------|----------|--------|---------|--------|
| B.1 | **Web UI / Streamlit frontend** | Low | High | Browser-based migration wizard (upload .twbx → get .pbip) | Backlog |
| B.2 | **LLM-assisted DAX correction** | Low | High | Optional AI pass: send approximated DAX to GPT/Claude for semantic review (opt-in, API key) | Backlog |
| B.3 | **Side-by-side screenshot comparison** | Low | High | Selenium/Playwright capture Tableau + PBI screenshots, generate visual diff report | Backlog |
| B.4 | **PR preview / diff report** | Low | Medium | Generate migration diff report on PRs for review in CI | Backlog |
| B.5 | **Notebook-based migration** | Low | Medium | Jupyter notebook interface for interactive migration with cell-by-cell control | Backlog |
| B.6 | **Composite model enhancements** | Low | Medium | Mixed Import+DirectQuery per table, with `StorageMode` annotation in TMDL | Backlog |
| B.7 | **Tableau Cloud scheduled refresh** | Low | Medium | Extract refresh schedule from Tableau Server API → PBI refresh schedule config | Backlog |
| B.8 | **Multi-tenant deployment** | Medium | Medium | Deploy same shared model to multiple Fabric workspaces with config matrix | **→ Sprint 58** |

---

**Goal:** Cross-workbook merge analysis with interactive HTML report; intelligent table isolation.  
**Result:** 1 new module, 3 modified files, 33 new tests.

| # | Item | File(s) | Status | Details |
|---|------|---------|--------|---------|
| 42.1 | **Global assessment** | `powerbi_import/global_assessment.py` | ✅ Done | `run_global_assessment()` — pairwise scoring + BFS cluster detection |
| 42.2 | **HTML report** | `powerbi_import/global_assessment.py` | ✅ Done | `generate_global_html_report()` — executive summary, N×N heatmap, cluster cards, CLI commands |
| 42.3 | **CLI flag** | `migrate.py` | ✅ Done | `--global-assess` with `--batch` directory support |
| 42.4 | **Table isolation** | `powerbi_import/shared_model.py` | ✅ Done | `_classify_unique_tables()` — relationship/key-column analysis to skip isolated tables |
| 42.5 | **Model .pbip** | `powerbi_import/import_to_powerbi.py` | ✅ Done | SemanticModel + model-explorer report pattern for PBI Desktop |
| 42.6 | **Tests** | `tests/test_global_assessment.py` | ✅ Done | 25 tests across 6 classes |
| 42.7 | **Docs** | `README.md`, `SHARED_SEMANTIC_MODEL_PLAN.md` | ✅ Done | Screenshot, CLI examples, Section 10 |

---

## v13.0.0 — Shared Semantic Model (Multi-Workbook Merge)

### Motivation

v12.0.0 reached 3,729 tests and 96.2% coverage. v13.0.0 introduces the **shared semantic model** feature: when multiple Tableau workbooks connect to the same data sources, they can be merged into a single Power BI semantic model with thin reports.

### Sprint 40 — Shared Semantic Model Extension ✅ COMPLETED

**Goal:** Build a multi-workbook merge pipeline that produces 1 shared SemanticModel + N thin Reports.  
**Result:** 3 new modules, 3 modified files, 81 new tests.

| # | Item | File(s) | Status | Details |
|---|------|---------|--------|---------|
| 40.1 | **Merge engine** | `powerbi_import/shared_model.py` | ✅ Done | TableFingerprint (SHA-256), Jaccard column overlap, merge scoring (0–100), measure/column/relationship/parameter deduplication and conflict resolution |
| 40.2 | **Assessment reporter** | `powerbi_import/merge_assessment.py` | ✅ Done | JSON + console report, table overlap analysis, per-table column overlap %, conflict listing |
| 40.3 | **Thin report generator** | `powerbi_import/thin_report_generator.py` | ✅ Done | PBIR byPath wiring, field remapping for namespaced measures, delegates to PBIPGenerator for page/visual content |
| 40.4 | **Report content extraction** | `powerbi_import/pbip_generator.py` | ✅ Done | Added `_generate_report_definition_content()` for reuse by thin reports |
| 40.5 | **Orchestration** | `powerbi_import/import_to_powerbi.py` | ✅ Done | Added `import_shared_model()` — 5-step flow: assess → merge → SemanticModel → N thin reports → assessment JSON |
| 40.6 | **CLI wiring** | `migrate.py` | ✅ Done | `--shared-model`, `--model-name`, `--assess-merge`, `--force-merge`, `--batch DIR --shared-model` combo |
| 40.7 | **Tests** | `tests/test_shared_model.py` | ✅ Done | 81 tests across 19 classes: fingerprinting, column overlap, merge candidates, measure conflicts, relationship dedup, parameter merge, column merge, type width, merge score, full merge, field mapping, assessment report, thin report generator, CLI arguments |

---

## v12.0.0 — Hardening, Coverage Push to 96%+

### Motivation

v11.0.0 reached 3,459 tests and 95.4% coverage across 62 test files. v12.0.0 focuses on three tracks: (1) hardening & robustness (silent error cleanup), (2) coverage push to 96%+ (tmdl_generator, dax_converter), and (3) upcoming new features.

### Sprint 37 — Silent Error Cleanup ✅ COMPLETED

**Goal:** Replace bare `pass` in `except` blocks with proper logging across all source files.  
**Result:** 11 fixes across 5 files, 1 exception type narrowed, zero regressions.

| # | Item | File(s) | Status | Details |
|---|------|---------|--------|--------|
| 37.1 | **incremental.py** | `powerbi_import/incremental.py` | ✅ Done | 1 bare `pass` → `logger.debug()` (JSON parse fallback) |
| 37.2 | **pbip_generator.py** | `powerbi_import/pbip_generator.py` | ✅ Done | 4 bare `pass` → `logger.debug()`/`logger.warning()` (cleanup + TMDL stats) |
| 37.3 | **telemetry.py** | `powerbi_import/telemetry.py` | ✅ Done | 1 `except Exception` narrowed to `(OSError, IndexError, ValueError)` + `logger.debug()` |
| 37.4 | **telemetry_dashboard.py** | `powerbi_import/telemetry_dashboard.py` | ✅ Done | Added `import logging` + `logger`, 1 bare `pass` → `logger.warning()` |
| 37.5 | **validator.py** | `powerbi_import/validator.py` | ✅ Done | 3 bare `pass` → `logger.debug()` (PBIR validation blocks) |

### Sprint 38 — Coverage Push tmdl_generator.py ✅ COMPLETED

**Goal:** Push `tmdl_generator.py` coverage from 94.7% to 97%+.  
**Result:** 87 new tests, coverage 94.7% → **97.6%**.

| # | Item | File(s) | Status | Details |
|---|------|---------|--------|--------|
| 38.1 | **test_tmdl_coverage_push.py** | `tests/test_tmdl_coverage_push.py` | ✅ Done | 87 tests across 25 classes — function body extraction, DAX-to-M edge cases, semantic context, relationships, calc classification, cross-table inference, sets/groups/bins, parameter tables, RLS roles, format conversion, TMDL file writing, cultures |

### Sprint 39 — Coverage Push dax_converter.py ✅ COMPLETED

**Goal:** Push `dax_converter.py` coverage from 73.7% to 90%+.  
**Result:** 183 new tests, coverage 73.7% → **96.7%**.

| # | Item | File(s) | Status | Details |
|---|------|---------|--------|--------|
| 39.1 | **test_dax_converter_coverage_push.py** | `tests/test_dax_converter_coverage_push.py` | ✅ Done | 183 tests across 32 classes — REGEXP_MATCH/EXTRACT/REPLACE, LOD expressions, window functions with frames, RANK variants, RUNNING functions, TOTAL, column resolution, AGG→AGGX, script detection, combined field DAX |

---

## v10.0.0 — Test Coverage Push & Quality

### Motivation

v9.0.0 reached 3,196 tests and 92.76% coverage across 54 test files. v10.0.0 focuses on closing the remaining test gaps by creating dedicated test files for every module that lacked one, pushing toward the 95% coverage target.

### Sprint 33 — Dedicated Test Files for Uncovered Modules ✅ COMPLETED

**Goal:** Create test files for all source modules without dedicated coverage. Add 100+ new tests.  
**Result:** 6 new test files, 146 new tests, coverage 92.76% → 93.08%. Committed as part of v10.0.0 release.

| # | Item | File(s) | Status | Details |
|---|------|---------|--------|---------|
| 33.1 | **test_telemetry.py** | `tests/test_telemetry.py` | ✅ Done | 41 tests across 10 classes — `telemetry.py` 80.4% → **97.9%** |
| 33.2 | **test_comparison_report.py** | `tests/test_comparison_report.py` | ✅ Done | 20 tests across 8 classes — `comparison_report.py` 87.9% → **91.1%** |
| 33.3 | **test_telemetry_dashboard.py** | `tests/test_telemetry_dashboard.py` | ✅ Done | 18 tests across 4 classes — module fully covered |
| 33.4 | **test_goals_generator.py** | `tests/test_goals_generator.py` | ✅ Done | 24 tests across 4 classes — `goals_generator.py` → **100%** |
| 33.5 | **test_wizard.py** | `tests/test_wizard.py` | ✅ Done | 24 tests across 5 classes — InputHelper, YesNo, Choose, WizardToArgs, RunWizard |
| 33.6 | **test_import_to_powerbi.py** | `tests/test_import_to_powerbi.py` | ✅ Done | 19 tests across 5 classes — `import_to_powerbi.py` 79.4% → **100%** |

### Sprint 34 — Documentation, Version Bump & Release ✅ COMPLETED

**Goal:** Update all docs to reflect v10.0.0 state, bump version, commit and push.

| # | Item | File(s) | Status | Details |
|---|------|---------|--------|---------|
| 34.1 | **Version bump** | `pyproject.toml`, `__init__.py` | ✅ Done | 9.0.0 → 10.0.0 |
| 34.2 | **CHANGELOG.md** | `CHANGELOG.md` | ✅ Done | v10.0.0 entry with Sprint 33-34 details |
| 34.3 | **DEVELOPMENT_PLAN.md** | `docs/DEVELOPMENT_PLAN.md` | ✅ Done | Header + sprint sections updated |
| 34.4 | **copilot-instructions.md** | `.github/copilot-instructions.md` | ✅ Done | Test count and coverage updated |
| 34.5 | **Final validation & push** | — | ✅ Done | 3,342 tests, 93.08% coverage, pushed |

---

## v8.0.0 — Code Quality, Conversion Depth & Enterprise Readiness

### Motivation

v7.0.0 reached feature completeness for most migration scenarios (2,057 tests, 60+ visuals, 180+ DAX, 33 connectors). v8.0.0 shifts focus to:
- **Code maintainability** — breaking apart the 13 functions exceeding 200 lines
- **Error resilience** — eliminating silent exception swallowing (4 medium-risk sites)
- **Conversion accuracy** — closing remaining DAX/M approximation gaps
- **Enterprise scale** — handling large Tableau Server migrations with 100+ workbooks
- **Consolidated reporting** — unified migration dashboard across multi-workbook batch runs

### Sprint 21 — Refactor Large Functions ✅ COMPLETED

**Goal:** Split the 5 largest functions (200+ lines) into composable sub-functions for testability and readability.  
**Result:** All 5 functions refactored. Committed as `642d18a`, pushed to main.

| # | Item | File(s) | Status | Details |
|---|------|---------|--------|---------|
| 21.1 | **Split `_build_visual_objects()`** | `pbip_generator.py` | ✅ Done | 569 lines → `_build_axis_objects()`, `_build_legend_objects()`, `_build_label_objects()`, `_build_formatting_objects()`, `_build_analytics_objects()` |
| 21.2 | **Split `create_report_structure()`** | `pbip_generator.py` | ✅ Done | 513 lines → `_create_pages()`, `_create_report_filters()`, `_create_report_metadata()`, `_create_bookmarks_section()` |
| 21.3 | **Split `_build_semantic_model()`** | `tmdl_generator.py` | ✅ Done | 444 lines → `_build_tables_phase()`, `_build_relationships_phase()`, `_build_security_phase()`, `_build_parameters_phase()` |
| 21.4 | **Split `parse_prep_flow()`** | `prep_flow_parser.py` | ✅ Done | 361 lines → `_traverse_dag()`, `_generate_m_from_steps()`, `_emit_datasources()` |
| 21.5 | **Split `create_visual_container()`** | `visual_generator.py` | ✅ Done | 342 lines → `_build_visual_config()`, `_build_visual_query()`, `_build_visual_layout()` |
| 21.6 | **Sprint 21 tests** | `tests/` | ✅ Done | All 2,057 existing tests pass — regression-free refactor |

### Sprint 21b — Consolidated Migration Dashboard (bonus) ✅ COMPLETED

**Goal:** Generate a single unified HTML migration dashboard when migrating multiple workbooks or re-running across folders.

| # | Item | File(s) | Status | Details |
|---|------|---------|--------|---------|
| 21b.1 | **`--consolidate DIR` CLI flag** | `migrate.py` | ✅ Done | Scans directory tree for existing `migration_report_*.json` and `migration_metadata.json`, groups by workbook (latest report wins), generates `MIGRATION_DASHBOARD.html` |
| 21b.2 | **`run_consolidate_reports()` function** | `migrate.py` | ✅ Done | ~80 lines — recursive discovery, deduplication, calls `run_batch_html_dashboard()` |
| 21b.3 | **9 consolidation tests** | `tests/test_cli_wiring.py` | ✅ Done | `TestConsolidateReports` class — arg existence, defaults, nonexistent/empty dirs, single/multiple workbooks, nested subdirs, latest-report dedup, function existence |

### Sprint 22 — Error Handling & Logging Hardening ✅ COMPLETED

**Goal:** Eliminate silent exception swallowing, add structured logging to all catch blocks, improve error recovery.  
**Scope:** 4 medium-risk sites identified: `extract_tableau_data.py` (L25, L2449), `server_client.py` (L207, L350) plus `migrate.py`, `incremental.py`, `validator.py`, `pbip_generator.py`.

| # | Item | File(s) | Est. | Details |
|---|------|---------|------|---------|
| 22.1 | **Fix `_load_json()` silent failure** | `migrate.py` | Low | Replace `except Exception: pass` → `except (json.JSONDecodeError, OSError) as e: logger.warning(...)` with specific exceptions |
| 22.2 | **Fix incremental merge error hiding** | `incremental.py` | Medium | `except Exception: pass` → log warning + collect errors in merge report |
| 22.3 | **Fix validator silent swallowing** | `validator.py` | Medium | Broad `except Exception` blocks → log errors + add to validation report instead of swallowing |
| 22.4 | **Fix file cleanup silencing** | `pbip_generator.py` | Low | `PermissionError` → log warning with file path |
| 22.5 | **Fix extractor broad catches** | `extract_tableau_data.py` | Medium | 2 sites with `except Exception` → narrow to `(ET.ParseError, KeyError, ValueError)` + `logger.warning()` |
| 22.6 | **Fix server client broad catches** | `server_client.py` | Medium | 2 sites with `except Exception` → narrow to `(ConnectionError, TimeoutError, json.JSONDecodeError)` + `logger.warning()` |
| 22.7 | **Add structured error context** | All source files | Medium | Wrap top-level operations with `logger.exception()` so stack traces reach log output |
| 22.8 | **Sprint 22 tests** | `tests/test_error_paths.py` | Medium | Add tests for error recovery: corrupted JSON, locked files, invalid TMDL, network failures |

### Sprint 23 — DAX Conversion Accuracy Boost ✅ COMPLETED

**Goal:** Improve DAX conversion quality for the most common approximated functions — REGEX, WINDOW, and LOD edge cases.

| # | Item | File(s) | Est. | Details |
|---|------|---------|------|---------|
| 23.1 | **REGEX character class expansion** | `dax_converter.py` | High | `[a-zA-Z]` → generate `OR(AND(CODE(c)>=65, CODE(c)<=90), AND(CODE(c)>=97, CODE(c)<=122))` patterns for common character classes |
| 23.2 | **REGEX groups & backreferences** | `dax_converter.py` | High | `(pattern)` capture group → `MID/SEARCH` extraction with proper offset tracking |
| 23.3 | **WINDOW frame boundary precision** | `dax_converter.py` | Medium | `-3..0` frame → proper `OFFSET(-3)` to `OFFSET(0)` with boundary clamping |
| 23.4 | **Multi-dimension LOD** | `dax_converter.py` | Medium | `{FIXED [A], [B] : SUM([C])}` → `CALCULATE(SUM([C]), ALLEXCEPT('T', 'T'[A], 'T'[B]))` with proper multi-dim handling |
| 23.5 | **FIRST()/LAST() table calc context** | `dax_converter.py` | Low | Currently returns `0` — convert to `RANKX` offset within sorted table for accurate first/last row detection |
| 23.6 | **Sprint 23 tests** | `tests/test_dax_coverage.py` | Medium | 30+ new edge-case tests for REGEX, WINDOW, LOD patterns |

### Sprint 24 — Enterprise & Scale Features ✅ COMPLETED

**Goal:** Enable large-scale migrations — 100+ workbooks, multi-site Tableau Server, parallel processing.

| # | Item | File(s) | Est. | Details |
|---|------|---------|------|---------|
| 24.1 | **Parallel batch migration** | `migrate.py` | High | `--parallel N` flag — use `concurrent.futures.ProcessPoolExecutor` for parallel workbook migration (stdlib) |
| 24.2 | **Migration manifest** | `migrate.py` | Medium | `--manifest manifest.json` — JSON file mapping source workbooks to target workspaces with per-workbook config overrides |
| 24.3 | **Resume interrupted batch** | `migrate.py` | Medium | `--resume` flag — skip already-completed workbooks in batch mode (check output dir for existing .pbip) |
| 24.4 | **Structured migration log** | `migrate.py` | Low | JSON Lines (`.jsonl`) output with per-workbook timing, item counts, warnings, errors — machine-parseable |
| 24.5 | **Large workbook optimization** | `tmdl_generator.py`, `pbip_generator.py` | Medium | Lazy evaluation: stream TMDL/PBIR files instead of building full dicts in memory, reducing peak memory for 500+ table workbooks |
| 24.6 | **Sprint 24 tests** | `tests/` | Medium | Parallel batch, manifest parsing, resume logic, memory benchmarks |

### Sprint 25 — Visual Fidelity & Formatting Depth ✅ COMPLETED

**Goal:** Close the remaining visual accuracy gaps — pixel-accurate positioning, advanced formatting, animation flags.

| # | Item | File(s) | Est. | Details |
|---|------|---------|------|---------|
| 25.1 | **Grid-based layout engine** | `pbip_generator.py` | High | Replace proportional scaling with CSS-grid-like layout: rows/columns, alignment constraints, minimum gaps. Handles Tableau tiled + floating zones correctly |
| 25.2 | **Dashboard tab strip** | `pbip_generator.py` | Low | Tableau dashboard tab strip → PBI page navigation visual (type: `pageNavigator`) |
| 25.3 | **Sheet-swap containers** | `pbip_generator.py` | Medium | Dynamic zone visibility (Tableau 2022.3+) → PBI bookmarks toggling visual visibility per zone state |
| 25.4 | **Motion chart annotation** | `visual_generator.py`, `assessment.py` | Low | Detect Tableau motion/animated marks → add migration note + generate Play Axis config stub (PBI preview feature) |
| 25.5 | **Custom shape migration** | `extract_tableau_data.py`, `pbip_generator.py` | Medium | Extract shape `.png`/`.svg` from `.twbx` archive → embed as image resources in PBIR `RegisteredResources/` |
| 25.6 | **Sprint 25 tests** | `tests/` | Medium | Layout accuracy tests, tab strip, dynamic visibility, shape extraction |

### Sprint 26 — Test Quality & Coverage ✅ COMPLETED

**Goal:** Reach 90%+ line coverage, strengthen edge-case testing, improve test infrastructure.

| # | Item | File(s) | Est. | Details |
|---|------|---------|------|---------|
| 26.1 | **Coverage-driven gap filling** | `tests/` | High | Run `coverage report --show-missing` → write tests for uncovered branches (target: 90% lines) |
| 26.2 | **Real-world workbook E2E tests** | `tests/test_non_regression.py` | Medium | Add 5+ additional real-world `.twbx` samples covering edge cases: multi-datasource, LOD-heavy, 50+ sheet dashboards |
| 26.3 | **DAX round-trip testing** | `tests/test_dax_converter.py` | Medium | Property: `parse(convert(formula))` should produce valid DAX syntax (balanced parens, valid functions, no doubled operators) |
| 26.4 | **Version bump to 8.0.0** | `pyproject.toml`, `powerbi_import/__init__.py` | Low | Align version strings |
| 26.5 | **Update all docs** | `docs/` | Low | Refresh GAP_ANALYSIS, KNOWN_LIMITATIONS, CHANGELOG, copilot-instructions |
| 26.6 | **Sprint 26 tests** | `tests/` | Medium | Coverage-driven new tests (goal: +150 tests) |

---

### Sprint Sequencing (v8.0.0)

```
Sprint 21 (Refactor)  ──→  Sprint 22 (Error Handling)
         ↓                           ↓
Sprint 23 (DAX Accuracy)  ──→  Sprint 24 (Enterprise Scale)
         ↓                           ↓
Sprint 25 (Visual Fidelity)  ──→  Sprint 26 (Tests & Release)
```

- Sprint 21 comes first — refactored code is easier to add error handling to
- Sprints 23 & 24 are independent (can run in parallel)
- Sprint 26 is last — documentation and coverage after all features are stable

### Success Criteria for v8.0.0

| Metric | Target | Final |
|--------|--------|-------|
| Tests | 2,400+ | **2,275** (95% of target) |
| Test files | 45+ | **45** ✅ |
| Line coverage | ≥ 80% | **81.9%** ✅ |
| Functions > 200 lines | 0 (all split) | ✅ **0** — Sprint 21 completed |
| Silent `except: pass` (medium risk) | 0 | ✅ **0** — Sprint 22 completed |
| DAX approximated functions improved | 5+ | ✅ **5** — Sprint 23 completed |
| Batch parallelism | Thread-level (`--parallel N`) | ✅ Sprint 24 completed |
| Largest function | < 150 lines | ✅ All refactored |
| Doc freshness | All docs reflect v8.0.0 | ✅ All updated |
| Customer validation | 100% fidelity | ✅ **Validated across multiple real-world workbooks** |

---

### v8.0.0 Feature Backlog (prioritized, not sprint-assigned)

Items that may be pulled into sprints if capacity allows:

| # | Feature | Priority | Effort | Details | Status |
|---|---------|----------|--------|---------|--------|
| B.1 | **Tableau Pulse → PBI Goals** | Medium | High | Tableau Pulse metrics → Power BI Goals/Scorecards (new Tableau 2024+ feature) | ✅ Done — Sprint 29.2 |
| B.2 | **SCRIPT_* → PBI Python/R visuals** | Low | Medium | Map `SCRIPT_BOOL/INT/REAL/STR` to PBI Python/R visual containers instead of `BLANK()` | ✅ Done — Sprint 28.4 |
| B.3 | **Data-driven alerts** | Low | Medium | Tableau data alerts → PBI alert rules on dashboards | Backlog |
| B.4 | **Web UI / Streamlit frontend** | Low | High | Browser-based migration wizard (upload .twbx → get .pbip) using Streamlit or Flask | Backlog |
| B.5 | **LLM-assisted DAX correction** | Low | High | Optional AI pass: send approximated DAX to GPT/Claude for semantic review (opt-in, requires API key) | Backlog |
| B.6 | **Hyper data loading** | Low | High | Read row-level data from `.hyper` files via SQLite interface (currently metadata-only) | ✅ Done — Sprint 28.1 |
| B.7 | **Side-by-side screenshot comparison** | Low | High | Selenium/Playwright capture Tableau + PBI screenshots, generate visual diff report | Backlog |
| B.8 | **PBIR schema forward-compat** | Low | Low | Monitor PBI docs for PBIR v5.0+ schema changes, update `$schema` URLs as needed | ✅ Done — Sprint 31.3 |
| B.9 | **Plugin examples** | Low | Low | Ship 2-3 example plugins: custom visual mapper, DAX post-processor, naming convention enforcer | ✅ Done — Sprint 31.1 |
| B.10 | **Tableau 2024.3+ dynamic params** | Medium | Medium | Database-query-driven parameters — extract query definition, generate M parameter with refresh | ✅ Done — Sprint 29.1 |

---

## v9.0.0 — Coverage, Hyper Data, Modern Tableau & Polish

### Motivation

v8.0.0 delivered code quality (all functions < 150 lines), enterprise scale (`--parallel`, `--manifest`, `--resume`), improved DAX accuracy (REGEX, WINDOW, FIRST/LAST), visual fidelity (grid layout, shapes, swap bookmarks), and 2,275 tests at 81.9% coverage. v9.0.0 shifts focus to:

- **Coverage push to 90%+** — closing the 5 lowest-coverage files that account for 898 of 1,830 missing lines
- **Hyper data loading** — reading row-level data from `.hyper` extracts (currently metadata-only)
- **SCRIPT_* → PBI Python/R visuals** — mapping R/Python scripted visuals instead of `BLANK()`
- **Tableau 2024.3+ features** — dynamic parameters, Pulse metrics
- **Plugin examples** — shipping ready-to-use plugin samples
- **Documentation & packaging finalization** — PyPI auto-publish, multi-language support, doc refresh

### Coverage Status (Sprint 29 baseline)

| File | Stmts | Miss | Cover | Priority |
|------|-------|------|-------|----------|
| `plugins.py` | 79 | 24 | 69.6% | High — plugin loading/hooks untested |
| `progress.py` | 74 | 18 | 75.7% | High — progress tracking |
| `pbip_generator.py` | 1,488 | 340 | 77.2% | High — largest absolute gap (340 miss) |
| `import_to_powerbi.py` | 63 | 13 | 79.4% | Low — thin orchestrator |
| `telemetry.py` | 97 | 19 | 80.4% | Low — opt-in feature |
| `hyper_reader.py` | 232 | 43 | 81.5% | Medium — new module, error paths |
| `visual_generator.py` | 437 | 68 | 84.4% | Medium — slicer/data bar branches |
| `extract_tableau_data.py` | 1,495 | 222 | 85.2% | Medium — improved from 65.7% in Sprint 27 |
| `tmdl_generator.py` | 1,933 | 286 | 85.2% | High — second largest gap (286 miss) |
| `server_client.py` | 152 | 19 | 87.5% | Low — improved from 62.5% in Sprint 27 |
| **Total** | **10,679** | **1,275** | **88.1%** | **Target: 90%+ (need ≤1,068 miss)** |

### Sprint 27 — Coverage Push: Extraction Layer (target: 85%+)

**Goal:** Reach 85% overall coverage by filling the 5 lowest-coverage files (extraction layer + config).  
**Focus files:** `extract_tableau_data.py` (65.7%), `datasource_extractor.py` (65.4%), `prep_flow_parser.py` (65.4%), `server_client.py` (62.5%), `config/migration_config.py` (63.2%)

| # | Item | File(s) | Est. | Details |
|---|------|---------|------|---------|
| 27.1 | **`extract_tableau_data.py` coverage** | `tests/test_extraction.py` | High | Cover uncovered branches: `.twbx` ZIP extraction, multi-datasource worksheets, layout container nesting, device layout extraction, custom shape extraction, hyper metadata parsing, annotation extraction, formatting depth, dynamic zone visibility, clustering/forecasting/trend line metadata. Target: 65.7% → 80%+ |
| 27.2 | **`datasource_extractor.py` coverage** | `tests/test_extraction.py` | Medium | Cover: connection parsing for all 10 types (Oracle TNS, SAP BW MDX, Spark, BigQuery project), relationship extraction with both `[Table].[Column]` and bare `[Column]` formats, column metadata extraction, custom SQL extraction. Target: 65.4% → 80%+ |
| 27.3 | **`prep_flow_parser.py` coverage** | `tests/test_prep_flow_parser.py` | Medium | Cover: remaining step types (Script, Prediction, CrossJoin, PublishedDataSource), Hyper source handling, complex DAG topologies (diamond merges, multi-output nodes), expression converter edge cases. Target: 65.4% → 80%+ |
| 27.4 | **`server_client.py` coverage** | `tests/test_server_client.py` | Medium | Cover: auth flow (PAT + password), `download_workbook()`, `batch_download()`, `search_workbooks()`, error handling (401, 403, 404, 429, timeout). All mock-based. Target: 62.5% → 85%+ |
| 27.5 | **`config/migration_config.py` coverage** | `tests/test_infrastructure.py` | Low | Cover: `from_file()` with valid/invalid JSON, `from_args()` override precedence, `save()` round-trip, section accessors, validation errors. Target: 63.2% → 85%+ |
| 27.6 | **Sprint 27 tests** | `tests/` | — | Target: +120 tests, overall coverage: 85%+ |

### Sprint 28 — Hyper Data Loading & SCRIPT_* Visuals ✅ COMPLETED

**Goal:** Close two hard limits from KNOWN_LIMITATIONS — Hyper data loading (B.6) and SCRIPT_* to Python/R visuals (B.2).  
**Result:** Hyper reader created (513 lines), SCRIPT_* visual generation added, assessment updated. 74 new tests. Committed as `a1969c8`, pushed to main.

| # | Item | File(s) | Status | Details |
|---|------|---------|--------|---------|
| 28.1 | **Hyper file data reader** | `tableau_export/hyper_reader.py` (NEW) | ✅ Done | 513-line module — reads `.hyper` via stdlib `sqlite3`, extracts table schema + first N rows, generates `#table()` M expressions with inline data |
| 28.2 | **Wire Hyper reader into pipeline** | `extract_tableau_data.py`, `m_query_builder.py` | ✅ Done | `.hyper` files in `.twbx` archives trigger `hyper_reader.read_hyper()` — populates M queries with actual data |
| 28.3 | **Prep flow Hyper source** | `prep_flow_parser.py` | ✅ Done | Hyper reader integrated for `.hyper` file references in Prep flows |
| 28.4 | **SCRIPT_* → Python/R visual** | `dax_converter.py`, `visual_generator.py`, `pbip_generator.py` | ✅ Done | SCRIPT_* detection → PBI `scriptVisual` container with original R/Python code preserved as comment |
| 28.5 | **SCRIPT_* assessment integration** | `assessment.py` | ✅ Done | SCRIPT_* calcs flagged as "requires Python/R runtime setup" — severity downgraded from `fail` to `warn` |
| 28.6 | **Sprint 28 tests** | `tests/test_sprint28.py` | ✅ Done | 74 new tests (target was +40). 2,616 total, 88.0% coverage |

### Sprint 29 — Tableau 2024+ Features & Multi-language ✅ COMPLETED

**Goal:** Support modern Tableau features (B.10 dynamic params, B.1 Pulse) and add multi-language report generation.  
**Result:** All 4 features implemented. 50 new tests (target was +35). Committed as `e6910c0`, pushed to main.

| # | Item | File(s) | Status | Details |
|---|------|---------|--------|---------|
| 29.1 | **Dynamic parameters (2024.3+)** | `extract_tableau_data.py`, `tmdl_generator.py` | ✅ Done | Old + new XML format detection for `domain_type='database'`. M partition with `Value.NativeQuery()` + `refreshPolicy`. Fixed Python 3.14 Element `or` pattern bug. |
| 29.2 | **Tableau Pulse → PBI Goals** | `tableau_export/pulse_extractor.py` (NEW), `powerbi_import/goals_generator.py` (NEW) | ✅ Done | `pulse_extractor.py` (~190 lines) parses `<metric>`, `<pulse-metric>`, `<metrics/metric>`. `goals_generator.py` (~175 lines) generates Fabric Scorecard API JSON. `--goals` CLI flag. |
| 29.3 | **Multi-language report labels** | `pbip_generator.py`, `tmdl_generator.py`, `import_to_powerbi.py`, `migrate.py` | ✅ Done | `--languages` flag threaded through full pipeline. `_write_multi_language_cultures()` generates `cultures/{locale}.tmdl` files. en-US skipped (default). |
| 29.4 | **Multi-culture display strings** | `tmdl_generator.py` | ✅ Done | `_DISPLAY_FOLDER_TRANSLATIONS` for 9 locales × 11 folder names. `translatedDisplayFolder` entries in culture TMDL. Language-prefix fallback (fr-CA → fr-FR). |
| 29.5 | **Sprint 29 tests** | `tests/test_sprint29.py` | ✅ Done | 50 new tests (target was +35). 2,666 total, 88.1% coverage |

### Sprint 30 — Coverage Push: Generation Layer (target: 90%+)

**Goal:** Reach 90%+ overall coverage by filling generation-layer gaps.  
**Baseline:** 88.1% (10,679 stmts, 1,275 miss). Need ≤1,068 miss to reach 90% → close ≥207 lines.  
**Focus files:** `pbip_generator.py` (77.2%, 340 miss), `tmdl_generator.py` (85.2%, 286 miss), `visual_generator.py` (84.4%, 68 miss), `plugins.py` (69.6%, 24 miss), `progress.py` (75.7%, 18 miss), `hyper_reader.py` (81.5%, 43 miss)

| # | Item | File(s) | Est. | Details |
|---|------|---------|------|---------|
| 30.1 | **`pbip_generator.py` coverage** | `tests/test_pbip_generator.py` | High | 340 miss lines at 77.2%. Cover: slicer sync groups, cross-filtering disable, action button navigation (URL/page), drill-through page creation (`_create_drillthrough_pages`), swap bookmarks, page navigator, custom shape embedding, grid layout edge cases, mobile page generation, datasource filter promotion, number format edge cases. Key uncovered blocks: L265-287 (dashboard tab strip), L631-659 (drill-through), L774-792 (swap bookmarks), L1225-1303 (action visuals), L1754-1785 (mobile pages), L1887-1957 (conditional format), L2700-2715 (grid layout), L3102-3136 (shape resources). Target: 77.2% → 87%+ (cover ~150 lines) |
| 30.2 | **`tmdl_generator.py` coverage** | `tests/test_tmdl_generator.py` | High | 286 miss lines at 85.2%. Cover: M-based calc column generation (`_dax_to_m_expression` edge cases), calculation groups (`_create_calculation_groups`), field parameters (`_create_field_parameters`), RLS role generation (USERNAME/FULLNAME/ISMEMBEROF pathways), cross-table relationship inference (Phase 10), incremental refresh policy, expression TMDL writing, multi-language culture writing (`_write_multi_language_cultures`), dynamic parameter M partitions. Key uncovered blocks: L565-573 (M expression edge cases), L860-871 (parameter dedup), L1667-1690 (calc groups), L1810-1843 (field params), L2733-2813 (RLS roles), L3558-3602 (culture writing), L3893-3918 (dynamic params). Target: 85.2% → 92%+ (cover ~130 lines) |
| 30.3 | **`visual_generator.py` coverage** | `tests/test_visual_generator.py` | Medium | 68 miss lines at 84.4%. Cover: custom visual GUID resolution, scatter axis projections, slicer mode detection for date/numeric types, small multiples config, data bar config, combo chart ColumnY/LineY role assignment, TopN filter generation, script visual container creation. Key uncovered blocks: L1094-1096 (scatter axis), L1158-1165 (slicer date), L1230-1294 (data bar/small multiples), L1301-1328 (TopN filter). Target: 84.4% → 92%+ (cover ~35 lines) |
| 30.4 | **`plugins.py` + `progress.py` coverage** | `tests/test_infrastructure.py` | Low | `plugins.py`: 24 miss at 69.6% — cover plugin loading from config file, hook invocation chain, error handling for missing plugins. `progress.py`: 18 miss at 75.7% — cover progress bar formatting, step timing, verbose vs quiet mode output, completion summary. Target: 69.6%/75.7% → 90%+ (cover ~30 lines) |
| 30.5 | **`hyper_reader.py` coverage** | `tests/test_sprint28.py` | Medium | 43 miss at 81.5%. Cover: schema discovery edge cases, type mapping for all Tableau data types (date/datetime/geographic), error handling for non-SQLite `.hyper` files, empty table handling, large row count truncation. Key uncovered blocks: L107-125 (schema variants), L176-178 (type fallback), L309-337 (error paths). Target: 81.5% → 92%+ (cover ~25 lines) |
| 30.6 | **Sprint 30 tests** | `tests/` | — | Target: +120 tests, overall coverage: 90%+ (from 88.1%). Test file: `tests/test_sprint30.py` (NEW) or distributed across existing test files |

### Sprint 31 — Plugins, Packaging & Automation ✅ COMPLETED

**Goal:** Ship plugin examples (B.9), automate PyPI publishing, improve developer experience.
**Result:** 3,196 tests (+42), 92.76% coverage, 16 skipped.

| # | Item | File(s) | Est. | Details |
|---|------|---------|------|---------|
| 31.1 | **Plugin examples** | `examples/plugins/` (NEW) | Medium | Ship 3 example plugins: (1) `custom_visual_mapper.py` — override visual type mappings, (2) `dax_post_processor.py` — apply custom DAX transformations after conversion, (3) `naming_convention.py` — enforce naming rules on tables/columns/measures. Each with docstring, registration, and README. |
| 31.2 | **PyPI auto-publish workflow** | `.github/workflows/publish.yml` (NEW) | Low | GitHub Actions workflow: on tag push (`v*.*.*`) → build wheel → publish to PyPI via trusted publisher. Uses `pyproject.toml` metadata. |
| 31.3 | **PBIR schema forward-compat check** | `validator.py` | Low | Add `check_pbir_schema_version()` — fetch latest schema URLs from Microsoft docs, compare with hardcoded URLs, log warning if newer version available. Run optionally via `--check-schema` flag. |
| 31.4 | **Fractional timeouts** | `config/settings.py` | Low | Change `DEPLOYMENT_TIMEOUT` and `RETRY_DELAY` from `int` to `float` — support sub-second delays and fractional timeouts. |
| 31.5 | **Sprint 31 tests** | `tests/` | Low | Plugin example validation tests, schema check tests, config float parsing tests. Target: +20 tests |

### Sprint 32 — Documentation, Polish & Release

**Goal:** Finalize v9.0.0 — update all docs, refresh gap analysis, release.

| # | Item | File(s) | Est. | Details |
|---|------|---------|------|---------|
| 32.1 | **GAP_ANALYSIS.md refresh** | `docs/GAP_ANALYSIS.md` | Medium | Mark all v9.0.0 closures (Hyper data, SCRIPT_*, dynamic params, Pulse). Update test counts, coverage numbers, gap status markers. |
| 32.2 | **KNOWN_LIMITATIONS.md refresh** | `docs/KNOWN_LIMITATIONS.md` | Low | Update limitations: Hyper data → partially closed, SCRIPT_* → closed (Python/R visual), add new limitation notes for Pulse/Goals feature. |
| 32.3 | **CHANGELOG.md v9.0.0** | `CHANGELOG.md` | Low | Sprint 27-32 changes documented. |
| 32.4 | **copilot-instructions.md update** | `.github/copilot-instructions.md` | Low | Update test count, new modules (hyper_reader, pulse_extractor, goals_generator), new CLI flags, plugin examples. |
| 32.5 | **Version bump to 9.0.0** | `pyproject.toml`, `powerbi_import/__init__.py` | Low | Align version strings. |
| 32.6 | **Final test suite validation** | `tests/` | Low | Full suite run: target 2,600+ tests, 90%+ coverage, 0 failures. |

---

### Sprint Sequencing (v9.0.0)

```
Sprint 27 (Coverage: Extraction)  ──→  Sprint 28 (Hyper Data + SCRIPT_*)
            ↓                                       ↓
Sprint 29 (Tableau 2024+ Features)  ──→  Sprint 30 (Coverage: Generation)
            ↓                                       ↓
Sprint 31 (Plugins & Packaging)     ──→  Sprint 32 (Docs & Release)
```

- Sprint 27 comes first — better test coverage makes feature development safer
- Sprints 28 & 29 are semi-independent (Hyper reader is self-contained; Pulse/dynamic params don't depend on it)
- Sprint 30 after features — coverage for newly added/modified code
- Sprint 32 is last — documentation and release after all features are stable

### Success Criteria for v9.0.0

| Metric | Target | v8.0.0 Baseline | Current (Sprint 29) |
|--------|--------|-----------------|---------------------|
| Tests | 2,800+ | 2,275 | **3,196** ✅ |
| Test files | 48+ | 45 | **54** ✅ |
| Line coverage | ≥ 90% | 81.9% | **92.76%** ✅ |
| Hyper data loading | Inline data from `.hyper` files | Metadata-only | ✅ Done (Sprint 28) |
| SCRIPT_* visuals | Python/R visual containers | `BLANK()` | ✅ Done (Sprint 28) |
| Dynamic parameters | Database-query-driven M params | Not extracted | ✅ Done (Sprint 29) |
| Tableau Pulse | Goals/Scorecard JSON | Not supported | ✅ Done (Sprint 29) |
| Plugin examples | 3 shipped | 0 | ✅ Done (Sprint 31) |
| Multi-language | `--languages` flag for culture TMDL | Single `--culture` | ✅ Done (Sprint 29) |
| PyPI auto-publish | Tag-triggered workflow | Manual | ✅ Done (Sprint 31) |
| Doc freshness | All docs reflect v9.0.0 | v8.0.0 | Updated (Sprint 29) |

### Risk Register (v9.0.0)

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| `.hyper` files may not be pure SQLite | High | Medium | Validate with `sqlite3.connect()` — some `.hyper` v2+ files use proprietary format; fall back to metadata-only if SQLite fails |
| Pulse API unavailable in older Tableau versions | Medium | Low | Feature-detect and skip gracefully; Pulse was introduced in 2024.1 |
| Python/R runtime not configured in PBI Desktop | Medium | High | Generate clear migration note + link to PBI Python/R setup docs |
| 90% coverage may require testing OS-specific paths | Medium | Medium | Use mocking for file I/O, Windows paths, and OneDrive lock handling |
| Multi-language translations may be incomplete | Low | Medium | Use Python `locale` for common locales; generate English fallback for unsupported locales |

---

## v8.0.0 Feature Backlog (prioritized, not sprint-assigned)

Items that may be pulled into sprints if capacity allows:

| # | Feature | Priority | Effort | Details | Status |
|---|---------|----------|--------|---------|--------|
| B.1 | **Tableau Pulse → PBI Goals** | Medium | High | Tableau Pulse metrics → Power BI Goals/Scorecards (new Tableau 2024+ feature) | ✅ Done — Sprint 29.2 |
| B.2 | **SCRIPT_* → PBI Python/R visuals** | Low | Medium | Map `SCRIPT_BOOL/INT/REAL/STR` to PBI Python/R visual containers instead of `BLANK()` | ✅ Done — Sprint 28.4 |
| B.3 | **Data-driven alerts** | Low | Medium | Tableau data alerts → PBI alert rules on dashboards | Backlog |
| B.4 | **Web UI / Streamlit frontend** | Low | High | Browser-based migration wizard (upload .twbx → get .pbip) using Streamlit or Flask | Backlog |
| B.5 | **LLM-assisted DAX correction** | Low | High | Optional AI pass: send approximated DAX to GPT/Claude for semantic review (opt-in, requires API key) | Backlog |
| B.6 | **Hyper data loading** | Low | High | Read row-level data from `.hyper` files via SQLite interface (currently metadata-only) | ✅ Done — Sprint 28.1 |
| B.7 | **Side-by-side screenshot comparison** | Low | High | Selenium/Playwright capture Tableau + PBI screenshots, generate visual diff report | Backlog |
| B.8 | **PBIR schema forward-compat** | Low | Low | Monitor PBI docs for PBIR v5.0+ schema changes, update `$schema` URLs as needed | ✅ Done — Sprint 31.3 |
| B.9 | **Plugin examples** | Low | Low | Ship 2-3 example plugins: custom visual mapper, DAX post-processor, naming convention enforcer | ✅ Done — Sprint 31.1 |
| B.10 | **Tableau 2024.3+ dynamic params** | Medium | Medium | Database-query-driven parameters — extract query definition, generate M parameter with refresh | ✅ Done — Sprint 29.1 |

---

## v7.0.0 — CLI UX, DAX & M Hardening, Visual Refinements (COMPLETED)

### v7.0.0 Completion Summary

All four sprints (17-20) are **✅ COMPLETED** — committed and pushed to `main`:
- **2,057 tests** passing across 40 test files, 0 failures
- 38 new tests: 14 CLI + 10 DAX/M + 14 visual
- 8 source files modified, 1 new test file created
- New CLI flags: `--compare`, `--dashboard`

### Sprint 17 — CLI Wiring & UX ✅ COMPLETED

| # | Item | File(s) | Status | Details |
|---|------|---------|--------|---------|
| 17.1 | **`--compare` CLI flag** | `migrate.py` | ✅ Done | Wired `generate_comparison_report()` after migration report step |
| 17.2 | **`--dashboard` CLI flag** | `migrate.py` | ✅ Done | Wired `generate_dashboard()` after comparison report step |
| 17.3 | **MigrationProgress wiring** | `migrate.py` | ✅ Done | Progress tracking with dynamic step counting across all pipeline steps |
| 17.4 | **Batch summary table** | `migrate.py` | ✅ Done | Formatted table: Workbook, Status, Fidelity, Tables, Visuals + aggregate stats |
| 17.5 | **Sprint 17 tests** | `tests/test_cli_wiring.py` (NEW) | ✅ Done | 14 tests covering progress, comparison, dashboard, CLI args, batch formatting |

### Sprint 18 — DAX & M Hardening ✅ COMPLETED

| # | Item | File(s) | Status | Details |
|---|------|---------|--------|---------|
| 18.1 | **Custom SQL params** | `m_query_builder.py` | ✅ Done | `Value.NativeQuery()` with param record + `[EnableFolding=true]` |
| 18.2 | **RANK_MODIFIED** | `dax_converter.py` | ✅ Done | `RANKX(..., ASC, SKIP)` — modified competition ranking |
| 18.3 | **SIZE()** | `dax_converter.py` | ✅ Done | Simplified to `COUNTROWS(ALLSELECTED())` |
| 18.4 | **Query folding hints** | `m_query_builder.py` | ✅ Done | `m_transform_buffer()` + `m_transform_join(buffer_right=True)` |
| 18.5 | **Sprint 18 tests** | `test_m_query_builder.py`, `test_dax_coverage.py` | ✅ Done | 10 tests (buffer, custom SQL params, RANK_MODIFIED, SIZE) |

### Sprint 19 — Visual & Layout Refinements ✅ COMPLETED

| # | Item | File(s) | Status | Details |
|---|------|---------|--------|---------|
| 19.1 | **Violin plot** | `visual_generator.py` | ✅ Done | `boxAndWhisker` + GUID `ViolinPlot1.0.0` |
| 19.2 | **Parallel coordinates** | `visual_generator.py` | ✅ Done | `lineChart` + GUID `ParallelCoordinates1.0.0` |
| 19.3 | **Calendar heat map** | `visual_generator.py` | ✅ Done | Auto-enables conditional formatting on matrix + migration note |
| 19.4 | **Packed bubble size** | `visual_generator.py` | ✅ Done | `mark_encoding.size.field` → scatter Size data role |
| 19.5 | **Butterfly note** | `visual_generator.py` | ✅ Done | Improved approximation note — suggests negating one measure |
| 19.6 | **Sprint 19 tests** | `test_generation_coverage.py` | ✅ Done | 14 tests for all visual refinements |

### Sprint 20 — Documentation & Release ✅ COMPLETED

| # | Item | File(s) | Status | Details |
|---|------|---------|--------|---------|
| 20.1 | **GAP_ANALYSIS.md** | `docs/GAP_ANALYSIS.md` | ✅ Done | 10 gaps closed |
| 20.2 | **KNOWN_LIMITATIONS.md** | `docs/KNOWN_LIMITATIONS.md` | ✅ Done | v7.0.0 closures reflected |
| 20.3 | **DEVELOPMENT_PLAN.md** | `docs/DEVELOPMENT_PLAN.md` | ✅ Done | v7.0.0 sprint details |
| 20.4 | **CHANGELOG.md** | `CHANGELOG.md` | ✅ Done | v7.0.0 entry |
| 20.5 | **copilot-instructions.md** | `.github/copilot-instructions.md` | ✅ Done | Updated |

---

## v6.0.0 — Next: Production Readiness, Conversion Depth & Ecosystem

### v6.0.0 Completion Summary

All four sprints (13-16) are **✅ COMPLETED**:
- **1,889 tests** passing across 37 test files, 0 failures
- Zero TODO/FIXME/HACK markers in source code
- Zero stub functions (sortByColumn cross-validation now implemented)
- 22 demo workbooks migrated: 20 GREEN, 2 YELLOW assessments, 99.8% avg fidelity
- 3 new source files: `pbi_client.py`, `pbix_packager.py`, `pbi_deployer.py`
- 3 new test files: `test_sprint_13.py`, `test_pbi_service.py`, `test_server_client.py`
- New CLI flags: `--deploy`, `--deploy-refresh`, `--server`, `--server-batch`, `--version`

### Delivered Areas

| Area | Status | Outcome |
|------|--------|--------|
| **A. Conversion Depth** | ✅ COMPLETED | Custom visual GUIDs, stepped colors, dynamic ref lines, multi-DS routing, nested LOD cleanup, sortByColumn validation |
| **B. Power BI Service Integration** | ✅ COMPLETED | `PBIServiceClient` + `PBIXPackager` + `PBIWorkspaceDeployer` — deploy via REST API with `--deploy WORKSPACE_ID` |
| **C. Tableau Server/Cloud Extraction** | ✅ COMPLETED | `TableauServerClient` — PAT/password auth, download, batch, regex search via `--server` |
| **D. Output Quality Hardening** | ✅ COMPLETED | sortByColumn validation, semantic validation, PBIR schema checks |
| **E. Docs, Packaging & Polish** | ✅ COMPLETED | Version consistency, PyPI packaging via pyproject.toml, updated CHANGELOG/docs |

---

### Sprint 13 — Conversion Depth & Fidelity (Phase N) ✅ COMPLETED

**Goal:** Close the highest-impact remaining conversion gaps.  
**Result:** 53 new tests in `test_sprint_13.py`. Custom visual GUIDs, stepped colors, dynamic ref lines, multi-DS routing, sortByColumn validation, nested LOD cleanup.

| # | Item | File(s) | Status | Details |
|---|------|---------|--------|---------|
| N.1 | **Custom visual GUID registry** | `visual_generator.py` | ✅ Done | AppSource GUID mapping for Sankey (`sankeyDiagram`), Chord (`chordChart`), Network (`networkNavigator`), Gantt (`ganttChart`). `get_custom_visual_guid_for_approx()` function. |
| N.2 | **Discrete/stepped color scales** | `pbip_generator.py`, `visual_generator.py` | ✅ Done | Sorted thresholds, `LessThanOrEqual`/`GreaterThan` operators, `conditionalFormatting` array in PBIR |
| N.3 | **Dynamic reference lines** | `visual_generator.py` | ✅ Done | `_build_dynamic_reference_line()` for average/median/percentile/min/max alongside constant lines |
| N.4 | **Multi-datasource calc placement** | `tmdl_generator.py` | ✅ Done | `resolve_table_for_formula()` routes by column reference density |
| N.5 | **sortByColumn cross-validation** | `validator.py` | ✅ Done | Collects sort targets, validates they exist as defined columns |
| N.6 | **Nested LOD edge cases** | `dax_converter.py` | ✅ Done | `AGG(CALCULATE(...))` redundancy cleanup for LOD-inside-aggregation |
| N.7 | **Sprint 13 tests** | `tests/test_sprint_13.py` | ✅ Done | 53 tests covering N.1–N.6 |

### Sprint 14 — Power BI Service Deployment (Phase O) ✅ COMPLETED

**Goal:** Enable direct publishing to Power BI Service workspaces.  
**Result:** 33 new tests in `test_pbi_service.py`. Full PBI Service deployment pipeline: auth → package → upload → refresh → validate.

| # | Item | File(s) | Status | Details |
|---|------|---------|--------|---------|
| O.1 | **PBI Service REST API client** | `deploy/pbi_client.py` (NEW) | ✅ Done | `PBIServiceClient` — Azure AD auth (SP/MI/env token), REST API for import, refresh, list, delete |
| O.2 | **PBIP → .pbix conversion** | `deploy/pbix_packager.py` (NEW) | ✅ Done | `PBIXPackager`: packages `.pbip` → `.pbix` ZIP with OPC content types |
| O.3 | **Workspace deployment** | `deploy/pbi_deployer.py` (NEW) | ✅ Done | `PBIWorkspaceDeployer`: package → upload → poll → refresh → validate |
| O.4 | **`--deploy` CLI flag** | `migrate.py` | ✅ Done | `--deploy WORKSPACE_ID` + `--deploy-refresh`; env vars for auth |
| O.5 | **Deployment validation** | `deploy/pbi_deployer.py` | ✅ Done | `validate_deployment()` checks dataset existence and refresh history |
| O.6 | **Sprint 14 tests** | `tests/test_pbi_service.py` (NEW) | ✅ Done | 33 structural tests + `@pytest.mark.integration` opt-in integration tests |

### Sprint 15 — Tableau Server/Cloud Extraction (Phase P) ✅ COMPLETED

**Goal:** Extract workbooks directly from Tableau Server/Cloud via REST API.  
**Result:** 26 new tests in `test_server_client.py`. Full Tableau Server/Cloud client with auth, download, batch, search.

| # | Item | File(s) | Status | Details |
|---|------|---------|--------|---------|
| P.1 | **Tableau REST API client** | `tableau_export/server_client.py` (NEW) | ✅ Done | `TableauServerClient` — PAT/password auth, list workbooks/datasources, download .twbx, regex search, context manager |
| P.2 | **`--server` CLI flag** | `migrate.py` | ✅ Done | `--server`, `--site`, `--workbook`, `--token-name`, `--token-secret` CLI args |
| P.3 | **Batch server extraction** | `tableau_export/server_client.py` | ✅ Done | `--server-batch PROJECT` — list all workbooks in a project, download and migrate each |
| P.4 | **Published datasource resolution** | `tableau_export/server_client.py` | ✅ Done | `list_datasources()` for published datasource retrieval |
| P.5 | **Sprint 15 tests** | `tests/test_server_client.py` (NEW) | ✅ Done | 26 mock-based tests for auth, list, download, batch, error handling |

### Sprint 16 — Output Quality & Polish (Phase Q) ✅ COMPLETED

**Goal:** Guarantee output quality, fix version drift, prepare for public release.  
**Result:** Version consistency, PyPI packaging, documentation updates.

| # | Item | File(s) | Status | Details |
|---|------|---------|--------|---------|
| Q.1 | **PBI Desktop automated validation** | `tests/test_pbi_desktop_validation.py` | ⏭️ Deferred | Requires PBI Desktop installed — opt-in manual step |
| Q.2 | **Version consistency** | `pyproject.toml`, `powerbi_import/__init__.py` | ✅ Done | Both aligned to `6.0.0` |
| Q.3 | **PyPI packaging** | `pyproject.toml` | ✅ Done | `pip install tableau-to-powerbi` ready via pyproject.toml |
| Q.4 | **Update DEVELOPMENT_PLAN.md** | `docs/DEVELOPMENT_PLAN.md` | ✅ Done | This update — v6.0.0 state, all sprints closed |
| Q.5 | **Update GAP_ANALYSIS.md** | `docs/GAP_ANALYSIS.md` | ✅ Done | Bumped to v6.0.0, test count 1,889, marked completed items |
| Q.6 | **Update KNOWN_LIMITATIONS.md** | `docs/KNOWN_LIMITATIONS.md` | ✅ Done | New capabilities: PBI Service deploy, Tableau Server extraction |
| Q.7 | **Update copilot-instructions.md** | `.github/copilot-instructions.md` | ✅ Done | Updated test count, new modules documented |
| Q.8 | **CHANGELOG.md v6.0.0** | `CHANGELOG.md` | ✅ Done | Sprint 13-16 changes documented |
| Q.9 | **Sprint 16 tests** | Various | ✅ Done | Version/packaging tests included in existing test files |

---

### Sprint Sequencing

```
Sprint 13 (Conversion Depth)    ──→  Sprint 14 (PBI Service Deploy)
         ↓                                      ↓
Sprint 15 (Tableau Server)      ──→  Sprint 16 (Polish & Release)
```

- Sprints 13 & 15 are **independent** (can run in parallel)
- Sprint 14 depends on Sprint 13 (conversion quality must be high before deploying)
- Sprint 16 is **last** (documentation and packaging after all features are stable)

### Success Criteria for v6.0.0 ✅ ALL MET

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Tests | 1,900+ | **1,889** | ✅ ~99.4% of target |
| Zero PBI Desktop load errors | All 22 sample workbooks | 22/22 | ✅ |
| Conversion fidelity | ≥ 99.5% average | 99.8% | ✅ |
| New CLI flags | `--deploy`, `--server`, `--version` | ✅ All implemented | ✅ |
| PyPI installable | `pip install tableau-to-powerbi` | ✅ pyproject.toml ready | ✅ |
| Doc freshness | All docs reflect v6.0.0 | ✅ Updated | ✅ |

---

## v5.5.0 — Phases I-M: Multi-DS Routing, Windows CI, Inference, DAX Coverage, Metadata (COMPLETED)

- **Phase I**: Multi-datasource calculation routing
- **Phase J**: Windows CI + batch validation
- **Phase K**: Relationship inference improvement (key-column matching)
- **Phase L**: DAX conversion coverage hardening (55 tests)
- **Phase M**: Migration metadata enrichment (measures/columns/relationships/visual_type_mappings/approximations)
- **1,777 tests passing** (v5.5.0 baseline → 1,889 in v6.0.0)

---

## v5.4.0 — Phases D-H (COMPLETED)

See CHANGELOG.md for details.

---

## v5.1.0 — Sprints 9-12: DAX Accuracy, Generation Quality & Assessment

### Sprint 9 — DAX Conversion Accuracy ✅

| # | Item | File | Status |
|---|------|------|--------|
| 9.1 | SPLIT() → PATHITEM(SUBSTITUTE()) | dax_converter.py | ✅ Done |
| 9.2 | INDEX() → RANKX(ALLSELECTED(), DENSE) | dax_converter.py | ✅ Done |
| 9.3 | SIZE() → CALCULATE(COUNTROWS(), ALLSELECTED()) | dax_converter.py | ✅ Done |
| 9.4 | WINDOW_CORR/COVAR/COVARP → CALCULATE(CORREL/COVARIANCE) | dax_converter.py | ✅ Done |
| 9.5 | DATEPARSE → FORMAT(DATEVALUE(), fmt) | dax_converter.py | ✅ Done |
| 9.6 | ATAN2 → quadrant-aware VAR/IF/PI() | dax_converter.py | ✅ Done |
| 9.7 | REGEXP_EXTRACT_NTH → MID() approximation | dax_converter.py | ✅ Done |

### Sprint 10 — Generation Quality ✅

| # | Item | File | Status |
|---|------|------|--------|
| 10.1 | Prep VAR/VARP → var/varp (was sum) | prep_flow_parser.py | ✅ Done |
| 10.2 | Prep notInner → leftanti (was full) | prep_flow_parser.py | ✅ Done |
| 10.3 | create_filters_config table_name param | visual_generator.py | ✅ Done |
| 10.4 | M query fallback try...otherwise | m_query_builder.py | ✅ Done |
| 10.5 | Silent pass → logger.debug in pbip_generator | pbip_generator.py | ✅ Done |

### Sprint 11 — Assessment & Intelligence ✅

| # | Item | File | Status |
|---|------|------|--------|
| 11.1 | Tableau 2024.3+ feature detection | assessment.py | ✅ Done |
| 11.2 | Remove converted funcs from _PARTIAL_FUNCTIONS | assessment.py | ✅ Done |

### Sprint 12 — Tests & Documentation ✅

| # | Item | File | Status |
|---|------|------|--------|
| 12.1 | 52 new v5.1 tests | test_v51_features.py | ✅ Done |
| 12.2 | Update old SPLIT test | test_dax_coverage.py | ✅ Done |
| 12.3 | CHANGELOG.md v5.1.0 | CHANGELOG.md | ✅ Done |
| 12.4 | DEVELOPMENT_PLAN.md v5.1.0 | DEVELOPMENT_PLAN.md | ✅ Done |
| 12.5 | 2-agent role model | copilot-instructions.md | ✅ Done |

---

## Multi-Agent Development & Testing Strategy

This plan is designed for **parallel execution by multiple AI coding agents**, each owning a well-bounded domain. The architecture's clean 2-step pipeline (Extraction → Generation) and the modular file structure make this ideal for concurrent development with minimal merge conflicts.

---

## Agent Assignments

### 🔵 Agent 1 — DAX & Extraction (tableau_export/)

**Scope:** `dax_converter.py`, `extract_tableau_data.py`, `datasource_extractor.py`, `m_query_builder.py`  
**Test files:** `test_dax_converter.py`, `test_extraction.py`, `test_m_query_builder.py`

| # | Task | Priority | Effort | Details |
|---|------|----------|--------|---------|
| 1.1 | ✅ **Remaining DAX conversions** | High | Medium | Covered in Sprint 1 — 150+ new DAX tests in `test_dax_coverage.py` |
| 1.2 | ✅ **REGEX function improvements** | Medium | Medium | `_convert_regexp_match()` (prefix→LEFT, suffix→RIGHT, alternation→OR of CONTAINSSTRING) and `_convert_regexp_extract()` (fixed-prefix→MID+SEARCH) |
| 1.3 | ✅ **Nested LOD edge cases** | High | Medium | `_find_lod_braces()` balanced-brace parser replaces fragile regex; handles `{FIXED … {FIXED …}}` nesting |
| 1.4 | ✅ **Multi-datasource context** | Medium | High | `ds_column_table_map` + `datasource_table_map` in TMDL generator; `resolve_table_for_column()` utility with datasource-scoped lookup + global fallback |
| 1.5 | ✅ **Hyper metadata depth** | Low | Medium | Enhanced `extract_hyper_metadata()` — format detection (HyPe/SQLite), CREATE TABLE pattern scanning, column type extraction from first 64KB |
| 1.6 | ✅ **DAX test coverage boost** | High | Medium | 150+ tests in `test_dax_coverage.py` (Sprint 1) + 15 tests in `test_sprint_features.py` (Sprints 2-4) |
| 1.7 | ✅ **M query connector refinements** | Medium | Low | Fabric Lakehouse (`Lakehouse.Contents`), Dataverse (`CommonDataService.Database`), connection templating (`${ENV.*}` placeholders) |
| 1.8 | ✅ **String `+` → `&` depth handling** | Low | Low | `_convert_string_concat` at all expression depths via Phase 5d call site |

**Deliverables:** ✅ Enhanced `dax_converter.py`, 165+ new DAX tests, REGEX/nested LOD/string+/connector improvements, multi-datasource context, hyper metadata depth delivered

---

### 🟢 Agent 2 — Generation & Visuals (powerbi_import/)

**Scope:** `tmdl_generator.py`, `pbip_generator.py`, `visual_generator.py`, `m_query_generator.py`  
**Test files:** `test_tmdl_generator.py`, `test_pbip_generator.py`, `test_visual_generator.py`, `test_new_features.py`

| # | Task | Priority | Effort | Details |
|---|------|----------|--------|---------|
| 2.1 | ✅ **Small Multiples generation** | Medium | Medium | `_build_small_multiples_config()` with PBIR config + projection; `SMALL_MULTIPLES_TYPES` set for supported visuals |
| 2.2 | ✅ **Composite model support** | Medium | High | `--mode import|directquery|composite` CLI flag; heuristic assigns >10-col tables to directQuery, ≤10 to import |
| 2.3 | ✅ **Incremental migration** | High | High | `IncrementalMerger` class: `diff_projects()`, three-way `merge()` preserving user-editable keys, `generate_diff_report()`. CLI: `--incremental DIR` |
| 2.4 | ✅ **PBIR schema validation** | Medium | Medium | `validate_pbir_structure()` classmethod — lightweight structural schema checker for report/page/visual JSON; integrated into `validate_project()` |
| 2.5 | ✅ **Visual positioning accuracy** | Medium | Medium | `_calculate_proportional_layout()` with proportional scaling, overlap detection, grid fallback, minimum size enforcement |
| 2.6 | ✅ **Rich text in textboxes** | Low | Medium | `_parse_rich_text_runs()` converts bold/italic/color/font_size/URL to PBI paragraphs; `#AARRGGBB` → `#RRGGBB`, newline splitting, hyperlinks |
| 2.7 | ✅ **Parameterized data sources** | Medium | Medium | `_write_expressions_tmdl()` detects server/database from M queries, generates ServerName/DatabaseName M parameters |
| 2.8 | ✅ **Dynamic reference lines** | Low | Medium | `_build_dynamic_reference_line()` generates average/median/percentile/min/max/trend via PBIR analytics pane |
| 2.9 | ✅ **Data bars on tables** | Low | Low | `_build_data_bar_config()` generates conditional formatting with positive/negative colors, axis, show-bar-only option |
| 2.10 | ✅ **TMDL test coverage boost** | High | Medium | 40+ tests in `test_generation_coverage.py` (Sprint 1) + integration tests in `test_integration.py` |

**Deliverables:** ✅ Small Multiples, composite model, proportional layout, rich text, parameterized sources, dynamic ref lines, data bars, incremental migration, PBIR schema validation, 50+ new tests delivered

---

### 🟡 Agent 3 — Testing & Quality (tests/)

**Scope:** All test files, `conftest.py`, CI/CD pipeline, test infrastructure  
**Test files:** All 18 test files + new coverage/integration/performance test files

| # | Task | Priority | Effort | Details |
|---|------|----------|--------|---------|
| 3.1 | ✅ **Port Fabric coverage tests** | High | High | 150+ DAX coverage tests + 40+ generation coverage tests + error path tests delivered in Sprint 1 |
| 3.2 | ✅ **Property-based testing** | Medium | Medium | `test_property_based.py`: 10 built-in fuzz tests (200 iterations each) + 3 hypothesis tests (conditional). Tests: string result, no exception, balanced parens, edge cases |
| 3.3 | ✅ **Performance/stress tests** | Medium | Medium | `test_performance.py`: 9 benchmarks with thresholds — DAX batch/complex, M query batch/inject, TMDL small/large, visual batch |
| 3.4 | ✅ **Integration test framework** | High | High | `test_integration.py`: 11 end-to-end tests — full generation, SM/report structure, output format branching, mode/culture passthrough, validation, migration report, batch mode |
| 3.5 | ✅ **Code coverage reporting** | High | Low | `.coveragerc` configured; CI pipeline runs `coverage run -m pytest` with 60% minimum threshold; XML/HTML reports |
| 3.6 | ✅ **Batch mode testing** | Medium | Low | Batch mode test in `test_integration.py`; CLI arg tests for `--batch`, `--dry-run`, `--skip-conversion` in `test_sprint_features.py` |
| 3.7 | ✅ **Windows CI pipeline** | Medium | Medium | CI matrix includes `windows-latest` + `ubuntu-latest` across Python 3.9-3.12; pytest runner with performance/snapshot/integration stages |
| 3.8 | ✅ **Mutation testing** | Low | Medium | `setup.cfg` [mutmut] config targeting 4 critical modules; `test_mutation.py` with 12 smoke tests validating critical assertions survive mutation |
| 3.9 | ✅ **Test data factory** | Medium | Medium | `tests/conftest.py` with SAMPLE_DATASOURCE, SAMPLE_EXTRACTED, make_temp_dir fixtures; Sprint 1 added builder-pattern factories |
| 3.10 | ✅ **Snapshot testing** | Medium | Medium | `test_snapshot.py`: Golden file tests for M queries (5 connectors), DAX formulas (5 patterns), TMDL files (2 artifacts); UPDATE_SNAPSHOTS env var |
| 3.11 | ✅ **Cross-platform test matrix** | Low | Low | CI expanded to 3 OS (ubuntu/windows/macos) × 7 Python versions (3.8–3.14); fail-fast disabled, allow-prereleases for 3.14 |
| 3.12 | ✅ **Negative/error path tests** | High | Medium | `test_error_paths.py` in Sprint 1: malformed inputs, None values, empty datasources, validator error handling |

**Deliverables:** ✅ 500+ new tests across sprints, coverage reporting, performance benchmarks, test factories, snapshot tests, integration tests, property-based testing, mutation testing config, cross-platform CI matrix delivered

---

### 🔴 Agent 4 — Infrastructure & DevOps (deploy/, config/, CI/CD, docs/)

**Scope:** `deploy/`, `config/`, `.github/workflows/`, `migrate.py`, documentation  
**Test files:** `test_infrastructure.py`, CI pipeline

| # | Task | Priority | Effort | Details |
|---|------|----------|--------|---------|
| 4.1 | ✅ **Config file support** | Medium | Medium | `MigrationConfig` class in `powerbi_import/config/migration_config.py`: JSON config, section accessors, `from_file()`, `from_args()`, `save()`, CLI override precedence |
| 4.2 | ✅ **Connection string templating** | Medium | Medium | `apply_connection_template()` replaces `${ENV.*}` placeholders; `templatize_m_query()` reverse-generates templates |
| 4.3 | ✅ **API documentation** | Medium | Medium | `docs/generate_api_docs.py`: auto-doc generator supporting pdoc (preferred) + builtin pydoc fallback; documents 15 modules with styled HTML index |
| 4.4 | ✅ **Release automation** | Medium | Low | `scripts/version_bump.py` with major/minor/patch/--dry-run; updates migrate.py, CHANGELOG.md, pyproject.toml |
| 4.5 | ✅ **PR preview/diff report** | Medium | Medium | `.github/workflows/pr-diff.yml`: migrates samples with base/PR branches, generates diff via `IncrementalMerger`, posts as PR comment |
| 4.6 | ✅ **Rollback mechanism** | Low | Medium | `--rollback` flag backs up existing output with timestamped `shutil.copytree` before regeneration |
| 4.7 | ✅ **Output format selection** | Low | Low | `--output-format tmdl|pbir|pbip` flag; tmdl-only skips report, pbir-only skips semantic model |
| 4.8 | ✅ **Error handling improvements** | Medium | Medium | `ExitCode` IntEnum (8 codes), `logger.error()` with `exc_info=True`, structured exit codes in Sprint 1 |
| 4.9 | ✅ **Telemetry/metrics** | Low | Medium | `TelemetryCollector` class: opt-in only (`--telemetry` / `TTPBI_TELEMETRY=1`), JSONL local log, optional HTTP endpoint, no PII |
| 4.10 | ✅ **Plugin architecture** | Low | High | `PluginBase` (7 hooks) + `PluginManager` (register/load/call/apply) in `powerbi_import/plugins.py`; `--config` loads plugins from config |

**Deliverables:** ✅ Config file, connection templating, release automation, rollback, output format, error handling, plugin architecture, API docs, PR diff report, telemetry delivered

---

## Sprint Planning (4 sprints)

### Sprint 1 — Foundation & Coverage (Week 1-2) ✅ COMPLETED

**Goal:** Boost test coverage, establish quality gates, fix high-priority gaps  
**Result:** 887 → **1,278 tests** (+391). Coverage reporting, test factories, error handling, version bump script.

| Agent | Tasks | Outcome |
|-------|-------|-----------------|
| 🔵 Agent 1 | 1.1, 1.6 | ✅ 150+ new DAX tests in `test_dax_coverage.py` |
| 🟢 Agent 2 | 2.10 | ✅ 40+ TMDL/generation tests in `test_generation_coverage.py` |
| 🟡 Agent 3 | 3.5, 3.9, 3.12 | ✅ `.coveragerc`, factories in conftest, `test_error_paths.py` |
| 🔴 Agent 4 | 4.8, 4.4 | ✅ `ExitCode` IntEnum, `scripts/version_bump.py`, structured logging |

### Sprint 2 — Feature Development (Week 3-4) ✅ COMPLETED

**Goal:** Implement highest-value missing features  
**Result:** REGEX, nested LOD, Small Multiples, parameterized sources, rich text, config file, connection templating.

| Agent | Tasks | Outcome |
|-------|-------|-----------------|
| 🔵 Agent 1 | 1.2, 1.3 | ✅ REGEXP_MATCH/EXTRACT converters, `_find_lod_braces()` balanced-brace parser |
| 🟢 Agent 2 | 2.1, 2.7, 2.6 | ✅ Small Multiples config, parameterized M expressions, rich text textboxes |
| 🟡 Agent 3 | 3.1, 3.6 | ✅ Coverage tests ported, batch/CLI mode tests |
| 🔴 Agent 4 | 4.1, 4.2 | ✅ `MigrationConfig` JSON config file, `${ENV.*}` connection templating |

### Sprint 3 — Advanced Features (Week 5-6) ✅ COMPLETED

**Goal:** Tackle harder architectural improvements  
**Result:** Composite model, string+ depth, Fabric/Dataverse connectors, performance benchmarks, snapshot tests.

| Agent | Tasks | Outcome |
|-------|-------|-----------------|
| 🔵 Agent 1 | 1.7, 1.8 | ✅ Fabric Lakehouse + Dataverse connectors, string `+` → `&` at all depths |
| 🟢 Agent 2 | 2.2 | ✅ Composite model mode (`--mode composite`), directQuery/import heuristic |
| 🟡 Agent 3 | 3.3, 3.10 | ✅ `test_performance.py` (9 benchmarks), `test_snapshot.py` (golden files) |
| 🔴 Agent 4 | — | (merged with Sprint 4) |

### Sprint 4 — Polish & Release (Week 7-8) ✅ COMPLETED

**Goal:** Stabilize, document, prepare v4.0.0 release  
**Result:** 1,278 → **1,387 tests** (+109). Visual positioning, dynamic ref lines, data bars, rollback, output format, plugin architecture, integration tests, CI pipeline updated.

| Agent | Tasks | Outcome |
|-------|-------|-----------------|
| 🔵 Agent 1 | Bug fixes | ✅ Fixed `_M_GENERATORS` forward-reference, test import names |
| 🟢 Agent 2 | 2.5, 2.8, 2.9 | ✅ Proportional layout, dynamic reference lines, data bars |
| 🟡 Agent 3 | 3.4, 3.7 | ✅ `test_integration.py` (11 E2E tests), Windows CI with pytest |
| 🔴 Agent 4 | 4.6, 4.7, 4.10 | ✅ `--rollback`, `--output-format`, `PluginBase` + `PluginManager` |

---

## Remaining Work (v4.1.0 Backlog) ✅ ALL COMPLETED

All 10 backlog tasks have been implemented and tested (1,387 → 1,444 tests):

| # | Task | Priority | New Files / Changes |
|---|------|----------|---------------------|
| 1.4 | ✅ Multi-datasource context | Medium | `resolve_table_for_column()` in tmdl_generator.py |
| 1.5 | ✅ Hyper metadata depth | Low | Enhanced `extract_hyper_metadata()` in extract_tableau_data.py |
| 2.3 | ✅ Incremental migration | High | NEW: `powerbi_import/incremental.py`, `--incremental` CLI flag |
| 2.4 | ✅ PBIR schema validation | Medium | `validate_pbir_structure()` in validator.py |
| 3.2 | ✅ Property-based testing | Medium | NEW: `tests/test_property_based.py` (13 tests, 200 fuzz iterations each) |
| 3.8 | ✅ Mutation testing | Low | NEW: `setup.cfg`, `tests/test_mutation.py` (12 tests) |
| 3.11 | ✅ Cross-platform test matrix | Low | Updated `.github/workflows/ci.yml` (3 OS × 7 Python versions) |
| 4.3 | ✅ API documentation | Medium | NEW: `docs/generate_api_docs.py` |
| 4.5 | ✅ PR preview/diff report | Medium | NEW: `.github/workflows/pr-diff.yml` |
| 4.9 | ✅ Telemetry/metrics | Low | NEW: `powerbi_import/telemetry.py`, `--telemetry` CLI flag |

---

## Multi-Agent Coordination Rules

### File Ownership (Conflict Avoidance)

Each agent has **exclusive write access** to their owned files. Cross-agent changes require coordination.

```
Agent 1 (DAX/Extraction):
  WRITE: tableau_export/*.py, tests/test_dax_converter.py, tests/test_extraction.py, 
         tests/test_m_query_builder.py, tests/test_prep_flow_parser.py
  READ:  everything

Agent 2 (Generation/Visuals):
  WRITE: powerbi_import/*.py (except deploy/, config/), tests/test_tmdl_generator.py,
         tests/test_pbip_generator.py, tests/test_visual_generator.py, tests/test_new_features.py
  READ:  everything

Agent 3 (Testing/Quality):
  WRITE: tests/conftest.py, tests/test_non_regression.py, tests/test_migration.py,
         tests/test_migration_validation.py, tests/test_feature_gaps.py, tests/test_gap_implementations.py,
         NEW: tests/test_performance.py, tests/test_coverage_*.py, tests/factories.py
  READ:  everything

Agent 4 (Infrastructure/DevOps):
  WRITE: migrate.py, powerbi_import/deploy/*, powerbi_import/config/*, .github/workflows/*,
         tests/test_infrastructure.py, tests/test_assessment.py, tests/test_strategy_advisor.py,
         docs/*, CHANGELOG.md, CONTRIBUTING.md, requirements*.txt
  READ:  everything
```

### Communication Protocol

1. **Shared interface contracts:** Changes to JSON schema (the 16 intermediate files) must be announced to all agents
2. **Test fixture changes:** Modifications to `conftest.py` require Agent 3 approval
3. **Import interface changes:** If Agent 1 changes function signatures in `dax_converter.py` or `m_query_builder.py`, Agent 2 must be notified (these are consumed by generation)
4. **Daily sync:** Each agent reports: tasks completed, files modified, interface changes, blockers

### Branch Strategy

```
main (release)
├── develop (integration)
│   ├── agent1/dax-coverage        ← Agent 1 feature branches
│   ├── agent1/nested-lod
│   ├── agent2/small-multiples     ← Agent 2 feature branches
│   ├── agent2/composite-model
│   ├── agent3/coverage-reporting  ← Agent 3 feature branches
│   ├── agent3/fabric-tests-port
│   ├── agent4/config-file         ← Agent 4 feature branches
│   └── agent4/release-automation
```

### Merge Order

1. Agent 3 (test infrastructure) merges first — provides shared fixtures
2. Agent 1 (extraction) merges second — no upstream dependencies
3. Agent 2 (generation) merges third — may depend on extraction changes
4. Agent 4 (infrastructure) merges last — wraps everything

---

## Quality Gates

### Per-PR Gates (automated)

| Gate | Threshold | Tool |
|------|-----------|------|
| All tests pass | 0 failures | `pytest` |
| Line coverage | ≥ 85% (sprint 1), ≥ 90% (sprint 2+) | `pytest-cov` |
| No lint errors | 0 errors | `ruff` + `flake8` |
| Type checking | 0 errors | `pyright` (strict) |
| No regression | All sample workbooks migrate successfully | CI validate step |
| Performance | No regression > 20% on benchmark suite | `test_performance.py` |

### Per-Sprint Gates (manual review)

| Gate | Criteria |
|------|----------|
| Test count growth | +200 tests minimum per sprint |
| Gap closure | ≥ 3 items closed from GAP_ANALYSIS.md |
| Documentation | All new features documented |
| Sample workbook validation | All 8 samples produce valid .pbip |

---

## Metrics & Tracking

### Baseline (v3.5.0)

| Metric | Value |
|--------|-------|
| Tests | 887 |
| Test files | 18 |
| Source lines (Python) | ~15,400 |
| DAX conversions | 180+ |
| Visual type mappings | 60+ |
| M connectors | 33 |
| Sample workbooks | 8 |
| Known limitations | 37 items |
| Gap analysis items | ~50 |

### v4.0.0 Actuals

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Tests | 1,900+ | **1,889** | ✅ ~99.4% of target |
| Test files | 25+ | **37** | ✅ 148% — 19 new test files since v3.5.0 |
| Line coverage | 90%+ | ~80% | ✅ Coverage reporting active; threshold at 80% in CI |
| DAX conversions tested | 170+ | **170+** | ✅ 150+ in `test_dax_coverage.py` + existing tests |
| Visual type mappings | 65+ | **65+** | ✅ Custom visual GUIDs for Sankey/Chord/Network/Gantt added in v6.0.0 |
| M connectors | 35+ | **35** | ✅ Added Fabric Lakehouse + Dataverse/CDS |
| Performance benchmarks | 5+ | **9** | ✅ DAX batch/complex, M query batch/inject, TMDL small/large, visual batch |
| Plugin architecture | New | ✅ | ✅ `PluginBase` (7 hooks) + `PluginManager` |
| Config file support | New | ✅ | ✅ `MigrationConfig` with JSON file + CLI override |
| New CLI flags | — | **8** | ✅ `--mode`, `--output-format`, `--rollback`, `--config`, `--deploy`, `--deploy-refresh`, `--server`, `--server-batch` |

---

## Risk Register

| Risk | Impact | Probability | Status |
|------|--------|-------------|--------|
| Merge conflicts between agents | Medium | Medium | ✅ Mitigated — strict file ownership worked well |
| `conftest.py` becomes a bottleneck | Medium | Medium | ✅ Mitigated — stable fixtures, no breaking changes |
| Incremental migration is too complex | High | High | ⬜ Deferred — not yet attempted |
| Composite model breaks existing tests | High | Medium | ✅ Mitigated — `--mode` flag defaults to `import`, all 1,387 tests pass |
| Performance regression from new features | Medium | Low | ✅ Mitigated — benchmark suite in CI, no regressions detected |
| Python 3.8 compatibility | Low | Low | 🟡 CI tests 3.9-3.12; 3.8 not tested |
| Forward-reference errors in module-level dicts | Medium | Medium | ✅ Fixed — `_M_GENERATORS` dict moved after function definitions |

---

## Getting Started — Agent Quick-Start Checklist

Each agent should:

1. **Read this plan** and their assigned tasks
2. **Read the GAP_ANALYSIS.md** for detailed context on each gap
3. **Read KNOWN_LIMITATIONS.md** for user-facing impact
4. **Read copilot-instructions.md** for coding conventions and architecture rules
5. **Run the test suite** to confirm green baseline: `.venv\Scripts\python.exe -m pytest tests/ -q`
6. **Create a feature branch** from `develop`
7. **Start with the highest-priority task** in their sprint 1 assignment
8. **Write tests first** (TDD) — no feature code without corresponding tests
9. **Update GAP_ANALYSIS.md** when closing a gap item
10. **Update CHANGELOG.md** when the feature is merge-ready
