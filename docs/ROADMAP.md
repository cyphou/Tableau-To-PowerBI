# Development Roadmap — v24.0.0 → v26.0.0

**Date:** 2025-07-24
**Baseline:** v24.0.0 — 5,897+ tests across 121 test files, 0 failures
**Current state:** v24.0.0 shipped. Composite models, live sync, enterprise portfolio intelligence, and 500-workbook scale validation complete.

---

## Executive Summary

The migration engine is **feature-complete for core single-workbook scenarios**. v22–v24 shift focus to:

| Version | Theme | Target Date | Status |
|---------|-------|-------------|--------|
| **v22.0.0** | Real-World Fidelity & Layout Intelligence | Sprints 76–80 | ✅ Shipped |
| **v23.0.0** | Conversion Accuracy & Fidelity Perfection | Sprints 81–85 | ✅ Shipped |
| **v24.0.0** | Composite Models, Live Sync & Enterprise Scale | Sprints 86–90 | ✅ Shipped |
| **v25.0.0** | Semantic Intelligence & Cross-Platform Parity | Sprints 91–95 | Planned |
| **v26.0.0** | Autonomous Migration & Production Hardening | Sprints 96–100 | Planned |

---

## Agent Ownership Matrix

| Agent | v22.0.0 Sprints | v23.0.0 Sprints | v24.0.0 Sprints | v25.0.0 Sprints | v26.0.0 Sprints |
|-------|----------------|----------------|----------------|----------------|----------------|
| **@orchestrator** | 76, 80 | 81, 83 | 86, 90 | 91, 95 | 96, 100 |
| **@extractor** | 76, 77 | — | 87 | 92 | 97 |
| **@converter** | 78 | 82 | 87 | 92, 93 | 97 |
| **@generator** | 76, 77, 78, 79 | 82 | 86, 87 | 91, 93 | 96, 97 |
| **@assessor** | 79 | — | 88 | 94 | 98 |
| **@merger** | — | — | 88, 89 | — | 99 |
| **@deployer** | — | 83 | 89, 90 | 94 | 98, 99, 100 |
| **@tester** | 76–80 (cross-cutting) | 81–85 (cross-cutting) | 86–90 (cross-cutting) | 91–95 (cross-cutting) | 96–100 (cross-cutting) |

---

## v22.0.0 — Real-World Fidelity & Layout Intelligence

### Motivation

Real-world migrations (NBA, Superstore, Feedback Dashboard) exposed gaps that synthetic tests don't catch: dashboard layout doesn't preserve Tableau's grid structure, advanced slicer modes are lost, stacked/grouped bar orientation is ambiguous, conditional formatting rules are shallow, and complex Tableau containers (show/hide, floating) produce misaligned PBI layouts. v22.0.0 focuses on **pixel-level layout fidelity** and **real-world visual accuracy**.

---

### Sprint 76 — Dashboard Layout Engine ✅ SHIPPED

**Goal:** Replace proportional scaling with a constraint-based layout engine that preserves Tableau's grid structure, container nesting, and alignment relationships.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 76.1 | **Container hierarchy extraction** | @extractor | `extract_tableau_data.py` | High | Parse `<layout-zone>` nesting: tiled containers → PBI alignment groups. Extract `is-fixed`, `auto-subscribe`, `min-size`, `max-size` constraints. Build parent→child tree. |
| 76.2 | **Grid-snapping layout algorithm** | @generator | `pbip_generator.py` | High | Replace `scale_x / scale_y` with grid-based layout: divide page into rows/columns based on Tableau zone positions. Snap visuals to nearest grid cell. Preserve relative proportions while respecting PBI minimum visual sizes. |
| 76.3 | **Floating vs tiled distinction** | @generator | `pbip_generator.py` | Medium | Floating zones → PBI `tabOrder` layering with precise x/y/w/h. Tiled zones → row/column-based relative positioning. Mixed dashboards maintain both. |
| 76.4 | **Responsive breakpoints** | @generator | `pbip_generator.py` | Medium | Extract `<device-layout>` from Tableau (phone, tablet). Generate PBI page `viewMode` variants with adjusted visual positions. Store device-specific overrides in page.json `mobileState`. |
| 76.5 | **Dashboard padding/margin extraction** | @extractor | `extract_tableau_data.py` | Low | Parse `inner-padding`, `outer-padding`, `border-style`, `border-color` attributes on zones. Propagate to PBI visual `padding` properties in `visualContainerObjects`. |
| 76.6 | **Tests** | @tester | `tests/test_layout_engine.py` (new) | Medium | 35+ tests: container nesting (1-level, 2-level, 3-level), grid snapping (2×2, 3×3, mixed), floating z-order, responsive breakpoints, padding propagation, real-world NBA layout validation |

**Success:** NBA dashboard opens in PBI Desktop with visuals in correct relative positions (2×4 grid).

---

### Sprint 77 — Advanced Slicer & Filter Intelligence ✅ SHIPPED

**Goal:** Fully migrate Tableau filter controls (dropdown, slider, relative date, wildcard, top-N, context filters) to PBI slicer equivalents with correct configuration.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 77.1 | **Filter type classification** | @extractor | `extract_tableau_data.py` | Medium | Classify extracted filters: `categorical` (list/dropdown), `range` (slider/between), `relative-date`, `wildcard` (contains/starts-with), `top-n`, `context` (pre-filter). Add `filter_mode` to filter JSON. |
| 77.2 | **Dropdown vs list slicer** | @generator | `pbip_generator.py` | Medium | `categorical` + high cardinality (>20 values) → dropdown slicer. Low cardinality → list slicer. Preserve `all_values_selected` default state and `exclude` mode (invert filter). |
| 77.3 | **Range slicer with bounds** | @generator | `pbip_generator.py` | Medium | `range` filters → PBI between slicer with `min`/`max` bounds from filter domain. Numeric: slider mode. Date: date picker mode. Preserve step size from Tableau parameter domain. |
| 77.4 | **Relative date slicer** | @generator | `pbip_generator.py` | Medium | Tableau "relative date" filters (last N days/weeks/months/years) → PBI relative date slicer with `anchorDate: today`, `relativePeriod`, `periodCount`. Handle "year to date", "quarter to date" presets. |
| 77.5 | **Wildcard filter** | @generator | `pbip_generator.py` | Low | Tableau wildcard match (contains, starts with, ends with) → PBI text slicer with search mode enabled. Set `search: true` on slicer config. |
| 77.6 | **Context filter → report-level filter** | @generator | `pbip_generator.py` | Low | Tableau context filters (applied before other filters) → PBI report-level filters. Emit `MigrationNote` explaining PBI evaluates all filters simultaneously. |
| 77.7 | **Tests** | @tester | `tests/test_slicer_intelligence.py` (new) | Medium | 30+ tests: filter classification (all types), dropdown vs list threshold, range bounds (numeric/date), relative date presets, wildcard search mode, context filter promotion, multi-filter interaction |

---

### Sprint 78 — Visual Fidelity Depth ✅ SHIPPED

**Goal:** Close the remaining visual accuracy gaps: stacked/grouped bar orientation, dual-axis combo charts, reference band shading, data label formatting, mark size encoding, and trend line preservation.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 78.1 | **Stacked bar orientation detection** | @generator | `visual_generator.py` | Medium | Extend `_detect_bar_orientation()` to stacked and 100% stacked variants: `Stacked Bar` + dim on cols → `stackedColumnChart`, `Stacked Bar` + measure on cols → `stackedBarChart`. Same for 100% variants. |
| 78.2 | **Dual-axis → combo chart** | @generator | `visual_generator.py` | High | Detect `dual_axis: true` in worksheet data → `lineClusteredColumnComboChart`. Map primary axis to column Y, secondary to line Y2. Preserve independent axis scaling (`isSecondaryAxis` on Y2 measures). Sync shared vs independent axis from Tableau config. |
| 78.3 | **Reference band shading** | @generator | `visual_generator.py` | Medium | Tableau reference bands (shaded region between two values) → PBI `constantLine` pairs with `shadeArea: true`. Map band color/opacity. Currently only reference lines are converted. |
| 78.4 | **Data label formatting** | @generator | `pbip_generator.py` | Medium | Propagate Tableau label font size, color, orientation (horizontal/vertical/rotated) → PBI `labels` properties. Handle mark-level label controls (show on specific marks only). |
| 78.5 | **Mark size encoding → bubble size** | @generator | `visual_generator.py` | Medium | Tableau `size` encoding shelf → PBI `Size` data role on scatter/bubble charts. Map continuous size range to PBI `bubbleSizes` min/max configuration. Detect discrete vs continuous size. |
| 78.6 | **Trend line preservation** | @converter | `dax_converter.py`, `visual_generator.py` | Medium | Tableau trend lines (linear, logarithmic, exponential, polynomial, power) → PBI analytics pane `trendLine` configuration with `regressionType`. Extract R² and p-value annotations from Tableau if present. |
| 78.7 | **Tests** | @tester | `tests/test_visual_fidelity_v2.py` (new) | Medium | 35+ tests: stacked orientation (4 variants), dual-axis decomposition, reference bands, label formatting, size encoding, trend line regression types, real-world visual comparison |

---

### Sprint 79 — Conditional Formatting & Theme Depth ✅ SHIPPED

**Goal:** Fully map Tableau quantitative/categorical color encoding to PBI conditional formatting rules, and deepen theme migration for background, border, and font styles.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 79.1 | **Diverging color scale** | @generator | `pbip_generator.py` | Medium | Tableau diverging palette (min→center→max, e.g. red→white→green) → PBI 3-stop gradient rule with min/mid/max colors and values. Detect diverging vs sequential from palette configuration. |
| 79.2 | **Stepped color (bins)** | @generator | `pbip_generator.py` | Medium | Tableau stepped color encoding (N discrete color bins from continuous measure) → PBI rules-based conditional formatting with N threshold conditions. Map bin boundaries from palette step count. |
| 79.3 | **Categorical color assignment** | @generator | `pbip_generator.py` | Medium | Tableau explicit color assignments (dimension value → specific color) → PBI `dataPoint.fill.solid.color` rules per category. Preserve exact hex colors from Tableau `<color-palette>`. |
| 79.4 | **Icon sets** | @generator | `pbip_generator.py` | Low | Tableau shape encoding with standard icons → PBI KPI icon conditional formatting. Map icon sets (arrows, circles, flags) to PBI `icon` format rules. |
| 79.5 | **Theme background & border** | @generator | `pbip_generator.py` | Medium | Extract dashboard background color, visual border color/width/radius from Tableau theme → PBI `background`, `border`, `visualHeader` properties in theme JSON and per-visual `visualContainerObjects`. |
| 79.6 | **Font style migration** | @generator | `pbip_generator.py` | Low | Tableau font family/size/bold/italic on titles, labels, axes → PBI `textClasses` in theme JSON. Map common Tableau fonts (Tableau Book, Tableau Light) to web-safe equivalents. |
| 79.7 | **Assessment: formatting coverage** | @assessor | `assessment.py` | Low | New sub-check in `_check_visual()`: count color-encoded fields, conditional formatting rules, and custom fonts. Score formatting migration coverage as a sub-metric. |
| 79.8 | **Tests** | @tester | `tests/test_conditional_formatting.py` (new) | Medium | 30+ tests: diverging scale, stepped color, categorical assignment, icon sets, background/border, font mapping, formatting assessment score |

---

### Sprint 80 — Integration Testing & v22.0.0 Release ✅ SHIPPED

**Goal:** End-to-end validation against all 16 real-world workbooks, performance regression suite, documentation update, and v22.0.0 release.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 80.1 | **Real-world E2E test suite** | @tester | `tests/test_real_world_e2e.py` (new) | High | For each of 16 real_world workbooks: extract → generate → validate → open in PBI Desktop (headless validation). Assert: no JSON errors, no TMDL errors, no missing visuals, page size matches dashboard. |
| 80.2 | **Layout regression tests** | @tester | `tests/test_layout_regression.py` (new) | Medium | Golden file comparison: store expected visual positions for 3 key workbooks (NBA, Superstore, Feedback). Fail if positions drift beyond tolerance. |
| 80.3 | **Performance regression** | @tester | `tests/test_performance_regression.py` (new) | Medium | Benchmark: 16 workbooks batch migration must complete in <30s. Single workbook <3s. Assert no regression vs v21 baseline. |
| 80.4 | **v22.0.0 release prep** | @orchestrator | `CHANGELOG.md`, `pyproject.toml`, docs | Low | Version bump 21.0.0 → 22.0.0. Update CHANGELOG, GAP_ANALYSIS, KNOWN_LIMITATIONS, README, copilot-instructions. |
| 80.5 | **Tests** | @tester | across above | — | Target: **5,500+** total tests (330+ new in v22) |

### v22.0.0 Success Criteria — ✅ ALL MET

| Metric | v21.0.0 | Target v22.0.0 | Actual |
|--------|---------|----------------|--------|
| Tests | 5,170 | **5,500+** | **5,683** ✅ |
| Visual layout accuracy | Proportional scaling | **Grid-snapped** | **Grid-snapped** ✅ |
| Slicer modes | Basic dropdown | **7 modes** (dropdown, list, slider, date picker, relative date, search, between) | **7 modes** ✅ |
| Conditional formatting types | Gradient only | **4 types** (gradient, diverging, stepped, categorical) | **4 types** ✅ |
| Stacked bar orientation | Always horizontal | **Orientation-aware** | **Orientation-aware** ✅ |
| Dual-axis combo charts | Mapped to lineChart | **lineClusteredColumnComboChart** with Y2 | **Combo chart** ✅ |
| Reference bands | Not migrated | **Shaded region pairs** | **Shaded** ✅ |
| Real-world E2E tests | Manual | **16 automated tests** | **26 workbooks, 369 tests** ✅ |

---

## v23.0.0 — Web UI, AI-Assisted Migration & CI Maturity

### Sprint 81 — Streamlit Web UI (@orchestrator)

**Goal:** Browser-based migration wizard for non-CLI users.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 81.1 | **Streamlit app scaffold** | @orchestrator | `web/app.py` (new) | High | 6-step wizard: Upload → Configure → Assess → Migrate → Validate → Download. Session state, temp dir management, error handling. |
| 81.2 | **Assessment view** | @orchestrator | `web/app.py` | Medium | 14-category radar chart, pass/warn/fail breakdown, strategy recommendation. Reuses `assessment.py`. |
| 81.3 | **Migration execution** | @orchestrator | `web/app.py` | Medium | Progress bar via `progress.py`, real-time log, fidelity score. ZIP download for `.pbip` project. |
| 81.4 | **Shared-model mode** | @orchestrator | `web/app.py` | Medium | Multi-file upload, merge heatmap, conflict list, force-merge toggle. |
| 81.5 | **Docker packaging** | @orchestrator | `web/Dockerfile` (new) | Low | Python 3.11 + Streamlit. `docker-compose.yml` for one-command startup. |
| 81.6 | **Tests** | @tester | `tests/test_web_app.py` (new) | Medium | 25+ tests: upload, config→args, pipeline integration, ZIP generation. |

---

### Sprint 82 — LLM-Assisted DAX Correction (@converter, @generator)

**Goal:** Optional AI-powered refinement for approximated DAX formulas.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 82.1 | **LLM client** | @converter | `powerbi_import/llm_client.py` (new) | High | OpenAI + Anthropic via `urllib`. Token counting, cost estimation, rate limiting. |
| 82.2 | **DAX refinement prompt** | @converter | `powerbi_import/llm_client.py` | High | Structured prompt: Tableau formula + current DAX + table/column context → refined DAX + confidence. |
| 82.3 | **Selective targeting** | @generator | `tmdl_generator.py` | Medium | Queue measures with `MigrationNote` containing "approximated" for LLM pass. Skip exact conversions. |
| 82.4 | **CLI integration** | @orchestrator | `migrate.py` | Low | `--llm-refine`, `--llm-provider`, `--llm-model`, `--llm-key`, `--llm-max-calls` flags. |
| 82.5 | **Cost report** | @converter | `powerbi_import/llm_client.py` | Low | Per-formula: original → approximated → refined, confidence, tokens, cost. JSON report. |
| 82.6 | **Tests** | @tester | `tests/test_llm_client.py` (new) | Medium | 25+ tests: client init, prompt construction, response parsing, cost tracking, rate limiting, mock API. |

---

### Sprint 83 — CI/CD Maturity & PR Preview (@orchestrator, @deployer)

**Goal:** PR-level migration diff, automated release pipeline, coverage gates.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 83.1 | **PR migration preview** | @orchestrator | `.github/workflows/pr-preview.yml` (new) | High | On PR: detect changed samples → migrate → diff report → PR comment. |
| 83.2 | **Release automation** | @deployer | `.github/workflows/release.yml` (new) | Medium | Tag push → test → build wheel → GitHub Release → PyPI publish. |
| 83.3 | **Coverage gate** | @tester | `.github/workflows/ci.yml` | Low | `--fail-under=95`. Coverage badge in README. |
| 83.4 | **Test annotations** | @tester | `.github/workflows/ci.yml` | Low | JUnit XML → GitHub Actions inline failure annotations. |
| 83.5 | **Dependency scanning** | @deployer | `.github/workflows/ci.yml` | Low | `pip-audit` for optional deps. Fail on HIGH severity. |
| 83.6 | **Tests** | @tester | `tests/test_ci_workflows.py` (new) | Medium | 15+ tests: diff generation, release metadata, coverage threshold, YAML structure. |

---

### Sprint 84 — Conversion Accuracy Depth (@converter)

**Goal:** Close remaining approximation gaps in DAX and M conversion.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 84.1 | **Prep VAR/VARP** | @converter | `prep_flow_parser.py` | Low | Fix: `"var"` → `List.Variance`, `"varp"` → population variance. |
| 84.2 | **Prep notInner → leftanti** | @converter | `prep_flow_parser.py` | Low | Fix: `JoinKind.LeftAnti` instead of `JoinKind.FullOuter`. |
| 84.3 | **Bump chart RANKX** | @generator | `visual_generator.py` | Medium | Auto-inject `_bump_rank_{measure}` RANKX measure for bump chart → lineChart mapping. |
| 84.4 | **PDF connector depth** | @converter | `m_query_builder.py` | Medium | Page index, `[StartPage=N, EndPage=M]`, table selection. |
| 84.5 | **Salesforce SOQL depth** | @converter | `m_query_builder.py` | Medium | SOQL passthrough, API version, relationship traversal. |
| 84.6 | **REGEX_* → M fallback** | @converter | `dax_converter.py`, `m_query_builder.py` | Medium | When DAX REGEX is approximated, generate M `Text.RegexExtract` step as alternative. |
| 84.7 | **Tests** | @tester | `tests/test_conversion_accuracy.py` (new) | Medium | 30+ tests covering all fixes. |

---

### Sprint 85 — v23.0.0 Integration & Release (@orchestrator, @tester)

**Goal:** Cross-feature integration testing, documentation, release.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 85.1 | ~~Web UI + LLM integration~~ | @orchestrator | — | — | _Deferred (Sprint 81/82 on hold)_ |
| 85.2 | ~~E2E Web UI tests~~ | @tester | — | — | _Deferred (Sprint 81/82 on hold)_ |
| 85.3 | **v23.0.0 release** ✅ | @orchestrator | `pyproject.toml`, docs | Low | Version bump 22→23, CHANGELOG, README, copilot-instructions. |

### v23.0.0 Success Criteria

| Metric | v22.0.0 | v23.0.0 Actual |
|--------|---------|----------------|
| Tests | ~5,500 | **5,782 (116 files)** ✅ |
| Prep VAR/VARP | Approximated | **Correct** ✅ |
| Prep notInner | Approximated | **leftanti** ✅ |
| Bump chart RANKX | ❌ | **Auto-injected** ✅ |
| PDF connector depth | Basic | **Page range + table select** ✅ |
| Salesforce SOQL | Basic | **API version + SOQL passthrough** ✅ |
| REGEX → M fallback | ❌ | **Text.RegexMatch/Extract/Replace** ✅ |
| LTRIM/RTRIM | Both → TRIM | **Proper left/right trim** ✅ |
| INDEX | RANKX approx | **ROWNUMBER() (DAX 2024+)** ✅ |
| Fidelity scoring | Skipped penalized | **Skipped excluded, 100% avg** ✅ |
| Web UI | ❌ | _Deferred_ |
| LLM-assisted DAX | ❌ | _Deferred_ |
| PR migration preview | ❌ | _Deferred_ |
| Release automation | Manual | _Deferred_ |

---

## v24.0.0 — Composite Models, Live Sync & Enterprise Scale

### Sprint 86 — Composite Model Depth (@generator, @orchestrator) ✅ SHIPPED

**Goal:** Per-table StorageMode, aggregation tables, hybrid relationship validation.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 86.1 | **Per-table StorageMode** | @generator | `tmdl_generator.py` | High | `--mode composite`: classify tables (large→DirectQuery, small→Import). TMDL `mode` property on partitions. |
| 86.2 | **Aggregation table generation** | @generator | `tmdl_generator.py` | High | Auto-generate Import-mode agg tables with `alternateOf` annotations linking to detail columns. |
| 86.3 | **Hybrid relationship constraints** | @generator | `tmdl_generator.py` | Medium | Cross-storage-mode relationships → auto-set `oneDirection`. Warn on bi-directional cross-mode. |
| 86.4 | **Composite CLI flags** | @orchestrator | `migrate.py` | Low | `--composite-threshold ROWS`: tables above threshold → DirectQuery. `--agg-tables auto|none`. |
| 86.5 | **Tests** | @tester | `tests/test_composite_model.py` (new) | Medium | 30+ tests. |

---

### Sprint 87 — Extraction & Conversion Hardening (@extractor, @converter, @generator) ✅ SHIPPED

**Goal:** Handle edge cases discovered in real-world migrations: multi-connection workbooks, nested LOD expressions, complex join graphs, published datasource resolution.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 87.1 | **Published datasource resolution** | @extractor | `datasource_extractor.py` | High | When workbook uses published datasource (no embedded XML), call Tableau Server API to fetch full datasource definition. Merge into extraction pipeline. |
| 87.2 | **Nested LOD (LOD within LOD)** | @converter | `dax_converter.py` | High | Handle `{FIXED X : SUM({FIXED Y : COUNT([Z])})}` → nested CALCULATE with proper ALLEXCEPT nesting. Currently only single-level LOD supported. |
| 87.3 | **Complex join graphs** | @generator | `tmdl_generator.py` | Medium | Multi-hop join paths (A→B→C) → chain of TMDL relationships. Detect diamond joins (A→B→D, A→C→D) and emit warning. |
| 87.4 | **Multi-connection M queries** | @converter | `m_query_builder.py` | Medium | Workbooks connecting to multiple databases → separate M partitions per connection. Generate connection-specific Power Query parameters. |
| 87.5 | **Data type coercion rules** | @extractor | `datasource_extractor.py` | Low | Tableau auto-coercion (string→date, string→number) → explicit M `Table.TransformColumnTypes` step to prevent PBI type errors. |
| 87.6 | **Tests** | @tester | `tests/test_edge_cases.py` (new) | Medium | 30+ tests. |

---

### Sprint 88 — Enterprise Portfolio Intelligence (@assessor, @merger) ✅ SHIPPED

**Goal:** Cross-workbook optimization: detect shared data patterns, recommend model consolidation, estimate org-wide migration effort with resource allocation.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 88.1 | **Data lineage graph** | @assessor | `global_assessment.py` | High | Build cross-workbook data lineage: datasource → tables → calculations → visuals. HTML interactive graph (D3.js force-directed or Sankey). |
| 88.2 | **Consolidation recommender** | @merger | `shared_model.py` | Medium | Beyond merge scoring: recommend which workbooks should share models vs remain standalone based on data overlap, update frequency, audience segmentation. |
| 88.3 | **Resource allocation planner** | @assessor | `server_assessment.py` | Medium | Based on complexity scores and wave plan: recommend team size, skill mix (DAX expert, M expert, visual designer), timeline per wave. |
| 88.4 | **Governance report** | @assessor | `server_assessment.py` | Medium | Executive summary: total workbooks, migration waves, estimated effort (hours), risk matrix, recommended sequence, dependency map. HTML + PDF export. |
| 88.5 | **Tests** | @tester | `tests/test_portfolio_intelligence.py` (new) | Medium | 25+ tests. |

---

### Sprint 89 — Live Sync & Incremental Refresh (@merger, @deployer) ✅ SHIPPED

**Goal:** Keep migrated PBI artifacts in sync with evolving Tableau workbooks. Detect source changes, compute incremental diff, auto-deploy updates.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 89.1 | **Source change detection** | @merger | `incremental.py` | High | Compare Tableau workbook hash (from Server API `updatedAt`) against last migration manifest. Flag modified workbooks. |
| 89.2 | **Incremental diff generation** | @merger | `incremental.py` | High | For modified workbooks: extract → diff against previous extraction → generate only changed artifacts (new measures, modified visuals, updated M queries). |
| 89.3 | **Auto-deploy updates** | @deployer | `deploy/pbi_deployer.py` | Medium | `--sync` mode: detect changes → incremental migrate → deploy updated dataset/reports. Preserve existing refresh schedules and sharing. |
| 89.4 | **Change notification** | @deployer | `telemetry.py` | Low | Emit structured events for detected changes: `{workbook, change_type, affected_artifacts}`. Optionally post to webhook (Teams, Slack). |
| 89.5 | **Tests** | @tester | `tests/test_live_sync.py` (new) | Medium | 25+ tests. |

---

### Sprint 90 — Enterprise Scale & v24.0.0 Release (@orchestrator, @deployer, @tester) ✅ SHIPPED

**Goal:** Validate at 500+ workbook scale, optimize memory/CPU, document enterprise deployment patterns, ship v24.0.0.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 90.1 | **Memory optimization** | @orchestrator | `migrate.py`, pipeline | Medium | Stream extraction instead of loading all XML into memory. Generator writes TMDL files incrementally. Target: <500MB RAM for 100-workbook batch. |
| 90.2 | **Parallel batch processing** | @orchestrator | `migrate.py` | Medium | `--workers N` for parallel workbook extraction/generation. Thread pool for CPU-bound (DAX conversion) and I/O-bound (file write) phases. |
| 90.3 | **500-workbook benchmark** | @tester | `tests/test_enterprise_scale.py` (new) | High | Synthetic: generate 500 workbooks × 5 tables × 10 measures. Assert merge + deploy < 60s. Memory < 1GB. |
| 90.4 | **Enterprise deployment guide** | @deployer | `docs/ENTERPRISE_GUIDE.md` (new) | Medium | Step-by-step guide: discovery → assessment → wave planning → pilot migration → batch migration → validation → deployment → sync. |
| 90.5 | **v24.0.0 release** | @orchestrator | `pyproject.toml`, docs | Low | Version bump, CHANGELOG, README, GAP_ANALYSIS, copilot-instructions. |

### v24.0.0 Success Criteria

| Metric | v23.0.0 | Target v24.0.0 |
|--------|---------|----------------|
| Tests | ~5,800 | **6,200+** |
| Composite model | ❌ | **Per-table StorageMode + agg tables** |
| Published datasource | ❌ | **Server API resolution** |
| Nested LOD | Single level | **Multi-level** |
| Live sync | ❌ | **`--sync` auto-deploy** |
| Scale tested | 100 workbooks | **500 workbooks** (<60s) |
| Parallel batch | Sequential | **`--workers N`** |

---

## Per-Agent Detailed Roadmap

### @orchestrator — Pipeline & User Experience

| Sprint | Deliverable | Priority |
|--------|------------|----------|
| 76 | Dashboard layout engine pipeline integration | P0 |
| 80 | v22.0.0 release, docs update | P0 |
| 81 | **Streamlit Web UI** (6-step wizard, Docker) | P0 |
| 83 | PR preview workflow, CI flags | P1 |
| 86 | Composite model CLI flags (`--composite-threshold`, `--agg-tables`) | P1 |
| 90 | Memory optimization, parallel batch (`--workers N`), v24.0.0 | P0 |
| 91 | **Lakehouse notebook scaffold**, output format selection (`--output-format`) | P1 |
| 95 | v25.0.0 integration & release | P0 |
| 96 | **M query self-repair** (try/otherwise), error recovery report | P1 |
| 100 | **SLA tracking**, monitoring integration, v26.0.0 release | P0 |

**Key files:** `migrate.py`, `import_to_powerbi.py`, `wizard.py`, `progress.py`, `web/app.py` (new), `sla_tracker.py` (new)

---

### @extractor — Tableau XML Intelligence

| Sprint | Deliverable | Priority |
|--------|------------|----------|
| 76 | **Container hierarchy extraction** (zone nesting, constraints, padding) | P0 |
| 77 | **Filter type classification** (7 filter modes → filter JSON) | P0 |
| 87 | **Published datasource resolution** (Server API fetch) | P1 |
| 87 | **Data type coercion rules** (auto-type → explicit M cast) | P2 |
| 92 | **Dynamic zone visibility conditions** (show/hide with calculation conditions) | P1 |
| 92 | **Table extensions** (Einstein Discovery, external API data) | P1 |
| 97 | **Shapefile/GeoJSON passthrough** (extract from .twbx → shape map) | P2 |

**Key files:** `extract_tableau_data.py`, `datasource_extractor.py`, `server_client.py`

---

### @converter — Formula Translation Accuracy

| Sprint | Deliverable | Priority |
|--------|------------|----------|
| 78 | **Trend line DAX patterns** (regression types) | P1 |
| 82 | **LLM client** (OpenAI/Anthropic, prompt engine, cost tracking) | P0 |
| 84 | **Prep VAR/VARP**, **notInner→leftanti**, **PDF/Salesforce depth**, **REGEX→M fallback** | P1 |
| 87 | **Nested LOD** (LOD within LOD → nested CALCULATE) | P0 |
| 87 | **Multi-connection M** (per-connection partitions) | P1 |
| 92 | **Multi-connection worksheet resolution** (blend → merge-append M) | P1 |
| 93 | **DAX optimizer engine** (AST rewriter, IF→SWITCH, COALESCE, VAR/RETURN) | P0 |
| 93 | **Measure dependency DAG** (circular ref detection, unused measures) | P1 |
| 97 | **Nested LOD depth 3+** (recursive parser, depth 5 limit) | P0 |
| 97 | **LOOKUP/PREVIOUS_VALUE** (OFFSET-based conversion) | P0 |
| 97 | **Window function PARTITIONBY** (compute-using → PARTITIONBY/ORDERBY) | P1 |

**Key files:** `dax_converter.py`, `m_query_builder.py`, `prep_flow_parser.py`, `llm_client.py` (new), `dax_optimizer.py` (new)

---

### @generator — TMDL & PBIR Fidelity

| Sprint | Deliverable | Priority |
|--------|------------|----------|
| 76 | **Grid-snapping layout**, floating/tiled distinction, responsive breakpoints | P0 |
| 77 | **7 slicer modes** (dropdown, list, slider, date picker, relative date, search, between) | P0 |
| 78 | **Stacked bar orientation**, dual-axis combo, reference bands, data labels, mark size, trend lines | P0 |
| 79 | **Diverging/stepped/categorical conditional formatting**, icon sets, theme depth | P1 |
| 82 | LLM selective targeting (queue approximated measures) | P1 |
| 86 | **Per-table StorageMode**, aggregation tables, hybrid relationship constraints | P1 |
| 87 | Complex join graph handling | P2 |
| 91 | **Direct Lake semantic model** (`mode: directLake` partitions) | P0 |
| 91 | **Dataflow Gen2 generation** (M→Dataflow JSON mashup) | P1 |
| 93 | **Time Intelligence auto-injection** (YTD, QTD, PY, YoY%, MoM%) | P0 |
| 96 | **TMDL self-repair** (broken refs, circular rels, orphan measures) | P0 |
| 96 | **Visual fallback cascade** (degrade to simpler type on error) | P1 |
| 97 | **Spatial → Azure Maps visual** (lat/lon data roles) | P1 |

**Key files:** `pbip_generator.py`, `visual_generator.py`, `tmdl_generator.py`, `dataflow_generator.py` (new)

---

### @assessor — Migration Intelligence

| Sprint | Deliverable | Priority |
|--------|------------|----------|
| 79 | Formatting coverage sub-metric in visual assessment | P2 |
| 88 | **Data lineage graph** (cross-workbook D3.js/Sankey) | P1 |
| 88 | **Resource allocation planner** (team size, skill mix, timeline) | P1 |
| 88 | **Governance report** (executive summary, risk matrix, HTML+PDF) | P0 |
| 94 | **Query equivalence framework** (Tableau vs PBI value comparison) | P0 |
| 94 | **Visual screenshot comparison** (SSIM-based pixel diff) | P1 |
| 98 | **Naming convention enforcement** (configurable rules, warn/enforce) | P1 |
| 98 | **Data classification annotations** (PII detection → dataClassification) | P1 |

**Key files:** `assessment.py`, `server_assessment.py`, `global_assessment.py`, `equivalence_tester.py` (new), `governance.py` (new)

---

### @merger — Model Consolidation Intelligence

| Sprint | Deliverable | Priority |
|--------|------------|----------|
| 88 | **Consolidation recommender** (standalone vs shared decision) | P1 |
| 89 | **Source change detection** (Server API hash comparison) | P0 |
| 89 | **Incremental diff generation** (changed artifacts only) | P0 |
| 99 | **Pattern registry** (migration marketplace with versioned patterns) | P0 |
| 99 | **DAX recipe overrides** (industry-specific measure templates) | P1 |

**Key files:** `shared_model.py`, `incremental.py`, `merge_config.py`, `marketplace.py` (new)

---

### @deployer — Enterprise Deployment & Sync

| Sprint | Deliverable | Priority |
|--------|------------|----------|
| 83 | **Release automation** (tag → build → publish pipeline) | P0 |
| 83 | **Dependency scanning** (pip-audit) | P2 |
| 89 | **Auto-deploy updates** (`--sync` mode) | P0 |
| 89 | **Change notification** (webhook: Teams/Slack) | P2 |
| 90 | **Enterprise deployment guide** | P1 |
| 94 | **Regression test suite generator** (auto-capture visual values for drift detection) | P1 |
| 98 | **Sensitivity label assignment** (Tableau permissions → PBI labels) | P1 |
| 98 | **Endorsement & certification** (`--endorse promoted|certified`) | P2 |
| 98 | **Audit trail** (immutable JSONL migration log) | P1 |
| 99 | **Industry model templates** (Healthcare/Finance/Retail skeletons) | P1 |
| 100 | **Rolling deployment** (blue/green with auto-rollback) | P0 |
| 100 | **Monitoring integration** (Azure Monitor/App Insights/Prometheus) | P1 |

**Key files:** `deploy/*.py`, `telemetry.py`, `gateway_config.py`, `governance.py` (new), `monitoring.py` (new)

---

### @tester — Quality Gates & Coverage

| Sprint | Deliverable | Priority |
|--------|------------|----------|
| 76–80 | **v22 test files**: layout_engine, slicer_intelligence, visual_fidelity_v2, conditional_formatting, real_world_e2e, layout_regression, performance_regression | P0 |
| 81–85 | **v23 test files**: web_app, llm_client, ci_workflows, conversion_accuracy, web_e2e | P0 |
| 86–90 | **v24 test files**: composite_model, edge_cases, portfolio_intelligence, live_sync, enterprise_scale | P0 |
| 91–95 | **v25 test files**: fabric_native, tableau_2024, dax_optimizer, equivalence, fabric_e2e, optimization_e2e | P0 |
| 96–100 | **v26 test files**: self_healing, advanced_formulas, governance, marketplace, production_scale | P0 |
| 83 | **Coverage gate** (95% threshold in CI) | P1 |
| 83 | **Test annotations** (JUnit XML → inline PR comments) | P2 |

**Target test counts:** v22: 5,500+ → v23: 5,800+ → v24: 6,200+ → v25: 6,600+ → v26: 7,000+

---

## Sprint Sequencing (v22–v26)

```
v22.0.0 — Real-World Fidelity
  Sprint 76 (Layout Engine)  ──→  Sprint 77 (Slicers)
           ↓                           ↓
  Sprint 78 (Visual Fidelity) ──→  Sprint 79 (Cond. Formatting)
                                       ↓
                             Sprint 80 (E2E + Release)

v23.0.0 — Web UI & AI
  Sprint 81 (Web UI)         ──→  Sprint 82 (LLM DAX)
           ↓                           ↓
  Sprint 83 (CI/CD)          ──→  Sprint 84 (Conversion Fixes) ✅
                                       ↓
                             Sprint 85 (Integration + Release)

v24.0.0 — Enterprise Scale
  Sprint 86 (Composite)      ──→  Sprint 87 (Hardening)
           ↓                           ↓
  Sprint 88 (Portfolio Intel) ──→  Sprint 89 (Live Sync)
                                       ↓
                             Sprint 90 (Scale + Release)

v25.0.0 — Semantic Intelligence
  Sprint 91 (Fabric-Native)  ──→  Sprint 92 (Tableau 2024+)
           ↓                           ↓
  Sprint 93 (DAX Optimizer)  ──→  Sprint 94 (Cross-Platform Validation)
                                       ↓
                             Sprint 95 (Integration + Release)

v26.0.0 — Autonomous Migration
  Sprint 96 (Self-Healing)   ──→  Sprint 97 (Formula Intelligence)
           ↓                           ↓
  Sprint 98 (Governance)     ──→  Sprint 99 (Marketplace)
                                       ↓
                             Sprint 100 (Production + Release)
```

---

## Risk Matrix

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Streamlit adds external dependency | Medium | Keep as optional `web/` module; core migration remains stdlib-only |
| LLM API costs for large migrations | High | Selective targeting (approximated only), cost cap (`--llm-max-calls`), dry-run mode |
| PBI Desktop layout validation requires GUI | Medium | Headless PBIR JSON validation; screenshot comparison optional |
| Nested LOD complexity explosion | High | Limit nesting to 3 levels; emit MigrationNote for deeper nesting |
| Published datasource requires Server access | Medium | Graceful fallback: extract available metadata, warn about missing columns |
| 500-workbook scale memory pressure | High | Streaming extraction, incremental TMDL writes, GC between workbooks |
| Fabric-native generation adds complexity | Medium | Keep as optional output format; TMDL core remains unchanged |
| Dynamic zone visibility parsing fragility | Medium | Feature-detect Tableau version; degrade to static zone on parse failure |
| DAX optimizer changing semantics | High | Before/after equivalence tests; opt-in only (`--optimize-dax`); preserve original as annotation |
| Governance rules blocking migration | Medium | Warn-only mode by default; enforce-mode requires explicit `--strict-governance` |
| Self-healing masking real issues | Medium | Recovery report documents every intervention; `--no-self-heal` disables |
| Marketplace pattern quality control | Medium | Patterns include validation tests; community rating + download count signals |

---

## v25.0.0 — Semantic Intelligence & Cross-Platform Parity

### Motivation

v22–v24 delivered layout fidelity, AI-assisted DAX, and enterprise-scale deployment. v25.0.0 shifts to **semantic intelligence** — making the migration engine deeply understand what a Tableau workbook _means_ (not just its XML structure), enabling automatic optimization, cross-platform equivalence testing, and intelligent data lineage. This version also targets **complete Tableau 2024.3+ feature coverage** and **Fabric-native artifact generation**.

---

### Sprint 91 — Fabric-Native Artifact Generation (@generator, @orchestrator)

**Goal:** Generate Fabric Lakehouse notebooks, Dataflows Gen2, and Direct Lake semantic models as first-class output formats alongside .pbip.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 91.1 | **Direct Lake semantic model** | @generator | `tmdl_generator.py` | High | `--mode direct-lake`: Generate TMDL with `mode: directLake` partitions pointing to Delta tables in a Lakehouse. Auto-map Tableau tables → Lakehouse table names. Emit `defaultPowerBIDataSourceVersion: powerBI_V3`. |
| 91.2 | **Dataflow Gen2 generation** | @generator | `powerbi_import/dataflow_generator.py` (new) | High | Convert Power Query M expressions to Dataflow Gen2 JSON mashup format. Support staging-to-lakehouse table output destinations. Handle connection references. |
| 91.3 | **Lakehouse notebook scaffold** | @orchestrator | `powerbi_import/notebook_generator.py` (new) | Medium | Generate PySpark notebooks for Tableau data transformations too complex for M (custom SQL, SCRIPT_*, complex Prep flows). Output as `.ipynb` or Fabric notebook JSON. |
| 91.4 | **Output format selection** | @orchestrator | `migrate.py` | Low | `--output-format pbip|fabric-lakehouse|dataflow-gen2`: Select generation target. Default remains `pbip`. Multiple formats can be combined. |
| 91.5 | **Tests** | @tester | `tests/test_fabric_native.py` (new) | Medium | 30+ tests: Direct Lake TMDL, Dataflow JSON structure, notebook generation, format selection, M→Dataflow mashup conversion. |

**Success:** A Superstore-class workbook generates a Lakehouse notebook + Direct Lake model that refreshes in Fabric without manual config.

---

### Sprint 92 — Deep Extraction: Tableau 2024+ Features (@extractor, @converter)

**Goal:** Complete coverage of Tableau 2024.1–2024.3+ features: dynamic zone visibility with conditions, table extensions, Explain Data config, and multi-connection worksheet resolution.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 92.1 | **Dynamic zone visibility conditions** | @extractor | `extract_tableau_data.py` | High | Parse `<dynamic-zone-visibility>` with `<calculation>` conditions on `<zone>` elements. Extract show/hide field refs and threshold logic. Map to PBI bookmark visibility toggles or selection pane bindings. |
| 92.2 | **Table extensions** | @extractor | `datasource_extractor.py` | Medium | Tableau 2024.2+ table extensions (Einstein Discovery, external API data). Extract extension config, API endpoint, schema. Generate M `Web.Contents()` query or placeholder with migration note. |
| 92.3 | **Multi-connection worksheet resolution** | @converter | `m_query_builder.py` | Medium | When a single worksheet references columns from 2+ datasources (multi-connection blend), generate separate M partitions per connection and a merge-append M step that combines them. Track blend relationships. |
| 92.4 | **Explain Data / Ask Data metadata** | @extractor | `extract_tableau_data.py` | Low | Extract `<ask-data>` and `<explain-data>` configs → PBI Q&A linguistic schema hints. Generate `linguisticSchema.xml` with synonyms from Tableau field captions. |
| 92.5 | **Tests** | @tester | `tests/test_tableau_2024.py` (new) | Medium | 25+ tests: dynamic zone conditions, table extensions, multi-connection blends, linguistic schema generation. |

---

### Sprint 93 — Semantic DAX Optimization (@converter, @generator)

**Goal:** Post-conversion DAX optimization pass that rewrites verbose converted formulas into idiomatic Power BI DAX, improving readability and performance.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 93.1 | **DAX optimizer engine** | @converter | `powerbi_import/dax_optimizer.py` (new) | High | AST-based DAX rewriter: simplify nested IF→SWITCH, collapse redundant CALCULATE, fold constant expressions, merge duplicate SUMX/AVERAGEX, convert IF(ISBLANK(x),0,x)→COALESCE, normalize variable extraction (VAR/RETURN). |
| 93.2 | **Time Intelligence auto-injection** | @generator | `tmdl_generator.py` | High | Auto-detect date-based measures and inject standard TI measures: YTD, QTD, MTD, PY, YoY%, MoM%, rolling 12-month. Configurable via `--time-intelligence auto|none|full`. Uses DATESINPERIOD, SAMEPERIODLASTYEAR, TOTALYTD. |
| 93.3 | **Measure dependency DAG** | @converter | `powerbi_import/dax_optimizer.py` | Medium | Build directed acyclic graph of measure-to-measure references. Detect circular refs (emit warning), unused measures (mark hidden), and recommend measure folders by dependency clusters. |
| 93.4 | **Optimization report** | @converter | `powerbi_import/dax_optimizer.py` | Low | JSON report: per-measure before/after comparison, simplification type applied, estimated performance impact (fewer nested IFs, reduced CALCULATE wrappers). |
| 93.5 | **Tests** | @tester | `tests/test_dax_optimizer.py` (new) | Medium | 35+ tests: each rewrite rule, circular ref detection, TI injection, measure DAG, before/after equivalence. |

**Success:** Complex_Enterprise measures are auto-optimized: nested IFs→SWITCH, redundant CALCULATEs removed, YoY% auto-generated.

---

### Sprint 94 — Cross-Platform Validation & Regression (@assessor, @deployer)

**Goal:** Automated equivalence testing: run the same queries against Tableau and Power BI to verify that migrated reports produce identical data.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 94.1 | **Query equivalence framework** | @assessor | `powerbi_import/equivalence_tester.py` (new) | High | For each migrated measure: extract expected values from Tableau (via Server REST API or Hyper data) → execute equivalent DAX query against deployed PBI dataset → compare results within tolerance threshold. Report pass/fail per measure. |
| 94.2 | **Visual screenshot comparison** | @assessor | `powerbi_import/equivalence_tester.py` | High | Optional: capture Tableau view PNG via Server REST API (`/views/{id}/image`) → capture PBI report page via PBI REST API (`/reports/{id}/pages/{page}/exportToFile`) → pixel-diff with configurable tolerance (SSIM ≥ 0.85). |
| 94.3 | **Regression test suite generator** | @deployer | `powerbi_import/regression_suite.py` (new) | Medium | Auto-generate a regression test JSON capturing all visual values, filter states, and data row counts. Re-run after re-migration to detect quality drift. |
| 94.4 | **Data validation CLI** | @orchestrator | `migrate.py` | Low | `--validate-data SERVER_URL`: Post-migration data validation comparing actual Tableau query results against PBI output. Requires both Server access and deployed dataset. |
| 94.5 | **Tests** | @tester | `tests/test_equivalence.py` (new) | Medium | 25+ tests: query construction, value comparison with tolerance, screenshot diffing (SSIM mock), regression JSON generation. |

---

### Sprint 95 — v25.0.0 Integration & Release (@orchestrator, @tester)

**Goal:** Cross-feature integration testing, Fabric-native + optimization + validation E2E, documentation, release.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 95.1 | **Fabric-native E2E** | @tester | `tests/test_fabric_e2e.py` (new) | High | Full pipeline: TWB → extract → generate Direct Lake → deploy → refresh → validate data. Integration test (opt-in). |
| 95.2 | **Optimization + validation E2E** | @tester | `tests/test_optimization_e2e.py` (new) | Medium | Extract → generate → optimize DAX → deploy → regression validate. 15+ tests. |
| 95.3 | **Docs update** | @orchestrator | `docs/`, `README.md`, `CHANGELOG.md` | Low | Document Fabric-native, DAX optimizer, TI injection, equivalence testing, Tableau 2024+ features. |
| 95.4 | **v25.0.0 release** | @orchestrator | `pyproject.toml`, docs | Low | Version bump, CHANGELOG, README, GAP_ANALYSIS, copilot-instructions. |

### v25.0.0 Success Criteria

| Metric | v24.0.0 | Target v25.0.0 |
|--------|---------|----------------|
| Tests | ~6,200 | **6,600+** |
| Fabric-native output | ❌ | **Direct Lake + Dataflow Gen2 + notebooks** |
| DAX optimization | ❌ | **AST rewriter + TI auto-injection** |
| Tableau 2024+ | Partial | **Dynamic zones, table extensions, multi-blend** |
| Data validation | ❌ | **Query equivalence + visual SSIM** |
| Linguistic schema (Q&A) | ❌ | **Auto-generated from field captions** |

---

## v26.0.0 — Autonomous Migration & Production Hardening

### Motivation

v26.0.0 targets **zero-touch autonomous migration** for standard workbooks: upload a .twbx, receive a production-ready .pbip with optimized DAX, proper governance, and deployed to Fabric — with no human intervention. This requires self-healing error recovery, governance policy enforcement, comprehensive audit logging, and a migration marketplace for community-contributed patterns.

---

### Sprint 96 — Self-Healing Migration Pipeline (@generator, @orchestrator)

**Goal:** When the migration engine encounters an error (TMDL validation failure, missing column reference, unsupported visual), it automatically applies corrective strategies instead of producing a broken artifact.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 96.1 | **TMDL self-repair** | @generator | `tmdl_generator.py` | High | After generation, run semantic validation. For each failure: broken column ref → remove from measure/hide with MigrationNote; circular relationship → deactivate weakest link; duplicate table name → auto-suffix; orphan measure → reassign to main table. |
| 96.2 | **Visual fallback cascade** | @generator | `visual_generator.py` | Medium | If a visual config is invalid (missing required data role), apply fallback: remove optional roles first, then degrade to simpler visual type (scatter→table, combo→bar), then emit placeholder card. Log each degradation in migration report. |
| 96.3 | **M query self-repair** | @orchestrator | `m_query_builder.py` | Medium | Wrap each generated M partition in `try/otherwise #table({}, {})` at the outermost expression. If M evaluation fails in PBI Desktop, the table loads empty instead of blocking the entire model. |
| 96.4 | **Error recovery report** | @orchestrator | `powerbi_import/recovery_report.py` (new) | Low | JSON report listing every self-repair action taken: what failed, what intervention was applied, recommended manual follow-up. Append to migration_report JSON. |
| 96.5 | **Tests** | @tester | `tests/test_self_healing.py` (new) | Medium | 30+ tests: broken refs, circular rels, missing data roles, M parse errors, fallback cascade, recovery report structure. |

**Success:** A deliberately broken .twbx with missing columns and circular joins still produces a valid, openable .pbip with degraded-but-functional visuals.

---

### Sprint 97 — Advanced Formula Intelligence (@extractor, @converter, @generator)

**Goal:** Handle the last 5% of formula edge cases: deeply nested LODs, window function partitioning, table calc addressing with LOOKUP/PREVIOUS_VALUE, and spatial-to-map formula conversion.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 97.1 | **Nested LOD depth 3+** | @converter | `dax_converter.py` | High | Recursive LOD parser with depth tracking: `{FIXED X : SUM({FIXED Y : COUNT({FIXED Z : MIN([A])})})}` → nested CALCULATE with layered ALLEXCEPT. Limit to depth 5 with MigrationNote for deeper. |
| 97.2 | **LOOKUP / PREVIOUS_VALUE** | @converter | `dax_converter.py` | High | `LOOKUP([Measure], -1)` → `CALCULATE([Measure], OFFSET(-1, ...))`. `PREVIOUS_VALUE(start)` → `VAR _prev = CALCULATE([Measure], OFFSET(-1, ...)) RETURN IF(ISBLANK(_prev), start, _prev)`. Requires partition-by context from table calc addressing. |
| 97.3 | **Window function partitioning** | @converter | `dax_converter.py` | Medium | Extract `compute-using`/`addressing` fields from table calc XML → translate to WINDOW/OFFSET `PARTITIONBY` and `ORDERBY` clauses. Currently uses `ALL/ALLSELECTED` approximation. |
| 97.4 | **Spatial → Azure Maps visual** | @generator | `visual_generator.py` | Medium | Tableau MAKEPOINT/MAKELINE/DISTANCE coordinates → PBI `azureMap` visual type with latitude/longitude data roles. Replace `0+comment` DAX with proper lat/lon column references. |
| 97.5 | **Shapefile/GeoJSON passthrough** | @extractor | `extract_tableau_data.py` | Low | Detect `.shp`/`.geojson` files in `.twbx` archive → extract to output directory → reference in PBI shape map visual `shapeMapGeoData`. |
| 97.6 | **Tests** | @tester | `tests/test_advanced_formulas.py` (new) | Medium | 35+ tests: nested LOD (depth 2,3,4,5), LOOKUP offsets, PREVIOUS_VALUE, PARTITIONBY translation, Azure Maps visual, shapefile extraction. |

---

### Sprint 98 — Governance & Compliance Framework (@assessor, @deployer)

**Goal:** Enterprise governance: enforce naming conventions, data classification labels, sensitivity labels, endorsement status, and audit trails for regulated industries.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 98.1 | **Naming convention enforcement** | @assessor | `powerbi_import/governance.py` (new) | Medium | Configurable rules: measure prefix (`m_`), column naming (snake_case/camelCase), table naming (PascalCase). Auto-rename on generation or warn-only mode. Rules defined in `config.json` governance section. |
| 98.2 | **Sensitivity label assignment** | @deployer | `deploy/deployer.py` | Medium | Map Tableau project permissions → PBI sensitivity labels (Public/General/Confidential/Highly Confidential). Apply via PBI REST API `PATCH /datasets/{id}` with label GUID. Configurable in `config.json`. |
| 98.3 | **Data classification annotations** | @assessor | `powerbi_import/governance.py` | Medium | Scan TMDL columns for PII patterns (email, SSN, phone, name) → add `dataClassification` annotation. Generate classification report. |
| 98.4 | **Endorsement & certification** | @deployer | `deploy/deployer.py` | Low | `--endorse promoted|certified`: Set endorsement status on deployed datasets/reports. Certified requires admin approval flag. |
| 98.5 | **Audit trail** | @deployer | `powerbi_import/governance.py` | Medium | Immutable JSON audit log: who migrated what, when, source hash, output hash, approvals, deployment target. Append-only log in `migration_audit.jsonl`. |
| 98.6 | **Tests** | @tester | `tests/test_governance.py` (new) | Medium | 30+ tests: naming rules, sensitivity mapping, PII detection, endorsement API, audit log structure, config validation. |

---

### Sprint 99 — Migration Marketplace & Community Patterns (@merger, @deployer)

**Goal:** A pattern library where teams can share and reuse migration solutions: custom visual mappings, DAX recipe overrides, connector templates, and industry-specific model patterns.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 99.1 | **Pattern registry** | @merger | `powerbi_import/marketplace.py` (new) | High | JSON-based pattern catalog: each pattern has metadata (name, author, Tableau source type, PBI target, rating, download count), a set of override files (DAX overrides, visual-type map, M templates), and versioning. Local file-system registry with import/export. |
| 99.2 | **DAX recipe overrides** | @merger | `powerbi_import/marketplace.py` | Medium | Named recipes: "Healthcare KPIs", "Financial Variance Analysis", "Retail RFM Model". Each recipe provides measure templates that override default DAX conversion for specific Tableau calculation patterns. Applied via `--recipe healthcare` CLI flag. |
| 99.3 | **Industry model templates** | @deployer | `powerbi_import/marketplace.py` | Medium | Pre-built semantic model skeletons for common domains: Healthcare (Patient, Encounter, Diagnosis), Finance (GL, AP, AR), Retail (Customer, Product, Transaction). When detected, auto-map Tableau tables to template tables with pre-configured relationships, hierarchies, and display folders. |
| 99.4 | **Pattern import/export** | @deployer | `powerbi_import/marketplace.py` | Low | `--export-pattern NAME` exports the current migration's overrides as a reusable pattern JSON. `--import-pattern FILE` applies a pattern before generation. |
| 99.5 | **Tests** | @tester | `tests/test_marketplace.py` (new) | Medium | 25+ tests: registry CRUD, recipe application, template matching, import/export round-trip, version conflicts. |

---

### Sprint 100 — Production Hardening & v26.0.0 Release (@orchestrator, @deployer, @tester)

**Goal:** Harden for production enterprise use: comprehensive error handling, monitoring integration, rolling deployments, migration SLA tracking, and v26.0.0 release.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 100.1 | **Rolling deployment** | @deployer | `deploy/pbi_deployer.py` | High | `--rolling`: Deploy updated dataset first, validate refresh success, then swap reports. Automatic rollback if validation fails. Blue/green deployment with canary phase. |
| 100.2 | **Migration SLA tracking** | @orchestrator | `powerbi_import/sla_tracker.py` (new) | Medium | Define per-workbook SLAs: max migration time, min fidelity score, required data validation pass. Track SLA compliance across batch migrations. Alert on SLA breach. |
| 100.3 | **Monitoring integration** | @deployer | `powerbi_import/monitoring.py` (new) | Medium | Export migration metrics to Azure Monitor (custom metrics), Application Insights (traces/events), or Prometheus (push gateway). Configurable via `--monitor azure|prometheus|none`. |
| 100.4 | **1000-workbook stress test** | @tester | `tests/test_production_scale.py` (new) | High | Synthetic: 1000 workbooks × 3 tables × 5 measures. Assert: total < 120s, peak memory < 2GB, 0 broken artifacts, SLA compliance ≥ 99%. |
| 100.5 | **v26.0.0 release** | @orchestrator | `pyproject.toml`, docs | Low | Version bump, CHANGELOG, README, GAP_ANALYSIS, KNOWN_LIMITATIONS, copilot-instructions. |

### v26.0.0 Success Criteria

| Metric | v25.0.0 | Target v26.0.0 |
|--------|---------|----------------|
| Tests | ~6,600 | **7,000+** |
| Self-healing pipeline | ❌ | **Auto-repair TMDL, visuals, M queries** |
| Nested LOD depth | 1 level | **5 levels** |
| LOOKUP/PREVIOUS_VALUE | ❌ | **OFFSET-based conversion** |
| Governance framework | ❌ | **Naming, sensitivity, PII, audit** |
| Migration marketplace | ❌ | **Pattern registry + recipes** |
| Rolling deployment | ❌ | **Blue/green with auto-rollback** |
| Scale tested | 500 workbooks | **1000 workbooks** (<120s) |
| SLA tracking | ❌ | **Per-workbook SLA compliance** |
