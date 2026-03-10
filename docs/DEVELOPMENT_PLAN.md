# Development Plan — Tableau to Power BI Migration Tool

**Version:** v5.1.0  
**Date:** 2026-03-10  
**Current state:** v5.1.0 — **1,595 tests**, 0 failures, ~19,000 lines of Python  
**Previous baseline:** v3.5.0 — 887 tests → v3.6.0 — 1,278 tests → v4.0.0 — 1,387 tests → v4.1.0 — 1,444 tests → v5.0.0 — 1,543 tests → **v5.1.0 — 1,595 tests**

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
| Tests | 1,900+ | **1,387** | 🟡 73% of target (strong foundation, room for property-based/mutation tests) |
| Test files | 25+ | **22** | 🟡 88% — 4 new test files added (sprint_features, performance, snapshot, integration) |
| Line coverage | 90%+ | ~75% | 🟡 Coverage reporting active; threshold set at 60% in CI |
| DAX conversions tested | 170+ | **170+** | ✅ 150+ in `test_dax_coverage.py` + existing tests |
| Visual type mappings | 65+ | **60+** | 🟡 No new visual types added; Small Multiples + data bars enhance existing |
| M connectors | 35+ | **35** | ✅ Added Fabric Lakehouse + Dataverse/CDS |
| Performance benchmarks | 5+ | **9** | ✅ DAX batch/complex, M query batch/inject, TMDL small/large, visual batch |
| Plugin architecture | New | ✅ | ✅ `PluginBase` (7 hooks) + `PluginManager` |
| Config file support | New | ✅ | ✅ `MigrationConfig` with JSON file + CLI override |
| New CLI flags | — | **4** | ✅ `--mode`, `--output-format`, `--rollback`, `--config` |

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
