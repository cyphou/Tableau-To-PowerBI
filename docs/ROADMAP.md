# Development Roadmap — v22.0.0 → v28.0.0

**Date:** 2026-03-23
**Baseline:** v27.1.0 — 6,532 tests across 138 test files, 0 failures
**Current state:** v28.0.0 Phase 1 shipped (Sprints 108–111). 6,714 tests.

---

## Executive Summary

The migration engine is **feature-complete for core single-workbook scenarios**. v22–v24 shift focus to:

| Version | Theme | Target Date | Status |
|---------|-------|-------------|--------|
| **v22.0.0** | Real-World Fidelity & Layout Intelligence | Sprints 76–80 | ✅ Shipped |
| **v23.0.0** | Conversion Accuracy & Fidelity Perfection | Sprints 81–85 | ✅ Shipped |
| **v24.0.0** | Composite Models, Live Sync & Enterprise Scale | Sprints 86–90 | ✅ Shipped |
| **v25.0.0** | Semantic Intelligence & Cross-Platform Parity | Sprints 91–95 | ✅ Shipped |
| **v26.0.0** | Autonomous Migration & Production Hardening | Sprints 96–100 | ✅ Shipped |
| **v27.0.0** | Advanced Intelligence & Marketplace | Sprints 101–106 | ✅ Shipped |
| **v27.1.0** | Unified HTML Report Template | Sprint 107 | ✅ Shipped |
| **v28.0.0** | Extensibility, Web UI & AI-Assisted Migration | Sprints 108–117 | In Progress |

---

## Agent Ownership Matrix

| Agent | v22.0.0 Sprints | v23.0.0 Sprints | v24.0.0 Sprints | v25.0.0 Sprints | v26.0.0 Sprints |
|-------|----------------|----------------|----------------|----------------|----------------|
| **@orchestrator** | 76, 80 | 81, 83 | 86, 90 | 91, 95 | 96, 97, 98, 100 |
| **@extractor** | 76, 77 | — | 87 | 92 | 97 |
| **@converter** | 78 | 82 | 87 | 92, 93 | 99 |
| **@generator** | 76, 77, 78, 79 | 82 | 86, 87 | 91, 93 | 96, 99 |
| **@assessor** | 79 | — | 88 | 94 | 99 |
| **@merger** | — | — | 88, 89 | — | 98 |
| **@deployer** | — | 83 | 89, 90 | 94 | 97, 99, 100 |
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
| 96 | **TMDL self-repair** (broken refs, circular rels, orphan measures) ✅ | P0 |
| 96 | **Visual fallback cascade** (degrade to simpler type on error) ✅ | P1 |
| 99 | **Spatial → Azure Maps visual** (lat/lon data roles) | P1 |

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
| 99 | **Naming convention enforcement** (configurable rules, warn/enforce) | P1 |
| 99 | **Data classification annotations** (PII detection → dataClassification) | P1 |

**Key files:** `assessment.py`, `server_assessment.py`, `global_assessment.py`, `equivalence_tester.py` (new), `governance.py` (new)

---

### @merger — Model Consolidation Intelligence

| Sprint | Deliverable | Priority |
|--------|------------|----------|
| 88 | **Consolidation recommender** (standalone vs shared decision) | P1 |
| 89 | **Source change detection** (Server API hash comparison) | P0 |
| 89 | **Incremental diff generation** (changed artifacts only) | P0 |
| 98 | **Shared model Fabric branch** (`--shared-model --output-format fabric`) ✅ | P0 |
| v27 | **Pattern registry** (migration marketplace with versioned patterns) | P0 |
| v27 | **DAX recipe overrides** (industry-specific measure templates) | P1 |

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
| 97 | **Multi-tenant path traversal defense** (template substitution hardening) ✅ | P0 |
| 99 | **Sensitivity label assignment** (Tableau permissions → PBI labels) | P1 |
| 99 | **Audit trail** (immutable JSONL migration log) | P1 |
| 100 | **Endorsement & certification** (`--endorse promoted|certified`) | P2 |
| v27 | **Industry model templates** (Healthcare/Finance/Retail skeletons) | P1 |
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
| 96–100 | **v26 test files**: self_healing ✅, security_hardening ✅, merged_fabric ✅, governance, production_scale | P0 |
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
  Sprint 96 (Self-Healing) ✅ ──→  Sprint 97 (Security) ✅
           ↓                           ↓
  Sprint 98 (Merged Fabric) ✅ ──→  Sprint 99 (Governance + Formulas)
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

### Sprint 91 — Fabric-Native Artifact Generation (@generator, @orchestrator) ✅ SHIPPED

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

### Sprint 92 — Deep Extraction: Tableau 2024+ Features (@extractor, @converter) ✅ SHIPPED

**Goal:** Complete coverage of Tableau 2024.1–2024.3+ features: dynamic zone visibility with conditions, table extensions, Explain Data config, and multi-connection worksheet resolution.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 92.1 | **Dynamic zone visibility conditions** | @extractor | `extract_tableau_data.py` | High | Parse `<dynamic-zone-visibility>` with `<calculation>` conditions on `<zone>` elements. Extract show/hide field refs and threshold logic. Map to PBI bookmark visibility toggles or selection pane bindings. |
| 92.2 | **Table extensions** | @extractor | `datasource_extractor.py` | Medium | Tableau 2024.2+ table extensions (Einstein Discovery, external API data). Extract extension config, API endpoint, schema. Generate M `Web.Contents()` query or placeholder with migration note. |
| 92.3 | **Multi-connection worksheet resolution** | @converter | `m_query_builder.py` | Medium | When a single worksheet references columns from 2+ datasources (multi-connection blend), generate separate M partitions per connection and a merge-append M step that combines them. Track blend relationships. |
| 92.4 | **Explain Data / Ask Data metadata** | @extractor | `extract_tableau_data.py` | Low | Extract `<ask-data>` and `<explain-data>` configs → PBI Q&A linguistic schema hints. Generate `linguisticSchema.xml` with synonyms from Tableau field captions. |
| 92.5 | **Tests** | @tester | `tests/test_tableau_2024.py` (new) | Medium | 25+ tests: dynamic zone conditions, table extensions, multi-connection blends, linguistic schema generation. |

---

### Sprint 93 — Semantic DAX Optimization (@converter, @generator) ✅ SHIPPED

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

### Sprint 94 — Cross-Platform Validation & Regression (@assessor, @deployer) ✅ SHIPPED

**Goal:** Automated equivalence testing: run the same queries against Tableau and Power BI to verify that migrated reports produce identical data.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 94.1 | **Query equivalence framework** | @assessor | `powerbi_import/equivalence_tester.py` (new) | High | For each migrated measure: extract expected values from Tableau (via Server REST API or Hyper data) → execute equivalent DAX query against deployed PBI dataset → compare results within tolerance threshold. Report pass/fail per measure. |
| 94.2 | **Visual screenshot comparison** | @assessor | `powerbi_import/equivalence_tester.py` | High | Optional: capture Tableau view PNG via Server REST API (`/views/{id}/image`) → capture PBI report page via PBI REST API (`/reports/{id}/pages/{page}/exportToFile`) → pixel-diff with configurable tolerance (SSIM ≥ 0.85). |
| 94.3 | **Regression test suite generator** | @deployer | `powerbi_import/regression_suite.py` (new) | Medium | Auto-generate a regression test JSON capturing all visual values, filter states, and data row counts. Re-run after re-migration to detect quality drift. |
| 94.4 | **Data validation CLI** | @orchestrator | `migrate.py` | Low | `--validate-data SERVER_URL`: Post-migration data validation comparing actual Tableau query results against PBI output. Requires both Server access and deployed dataset. |
| 94.5 | **Tests** | @tester | `tests/test_equivalence.py` (new) | Medium | 25+ tests: query construction, value comparison with tolerance, screenshot diffing (SSIM mock), regression JSON generation. |

---

### Sprint 95 — v25.0.0 Integration & Release (@orchestrator, @tester) ✅ SHIPPED

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

### Sprint 96 — Self-Healing Migration Pipeline (@generator, @orchestrator) ✅ SHIPPED

**Goal:** When the migration engine encounters an error (TMDL validation failure, missing column reference, unsupported visual), it automatically applies corrective strategies instead of producing a broken artifact.

| # | Item | Owner | File(s) | Status | Details |
|---|------|-------|---------|--------|---------|
| 96.1 | **TMDL self-repair** | @generator | `tmdl_generator.py` | High | After generation, run semantic validation. For each failure: broken column ref → remove from measure/hide with MigrationNote; circular relationship → deactivate weakest link; duplicate table name → auto-suffix; orphan measure → reassign to main table. |
| 96.2 | **Visual fallback cascade** | @generator | `visual_generator.py` | Medium | If a visual config is invalid (missing required data role), apply fallback: remove optional roles first, then degrade to simpler visual type (scatter→table, combo→bar), then emit placeholder card. Log each degradation in migration report. |
| 96.3 | **M query self-repair** | @orchestrator | `m_query_builder.py` | Medium | Wrap each generated M partition in `try/otherwise #table({}, {})` at the outermost expression. If M evaluation fails in PBI Desktop, the table loads empty instead of blocking the entire model. |
| 96.4 | **Error recovery report** | @orchestrator | `powerbi_import/recovery_report.py` (new) | Low | JSON report listing every self-repair action taken: what failed, what intervention was applied, recommended manual follow-up. Append to migration_report JSON. |
| 96.5 | **Tests** | @tester | `tests/test_self_healing.py` (new) | Medium | 30+ tests: broken refs, circular rels, missing data roles, M parse errors, fallback cascade, recovery report structure. |

**Success:** A deliberately broken .twbx with missing columns and circular joins still produces a valid, openable .pbip with degraded-but-functional visuals.

---

### Sprint 97 — Security Hardening (@extractor, @orchestrator, @deployer) ✅ SHIPPED

**Goal:** OWASP Top 10 defense across the pipeline: path traversal, ZIP slip, XXE, credential exposure, injection via template substitution. Replaces originally-planned "Advanced Formula Intelligence" (deferred to v27.0.0).

| # | Item | Owner | File(s) | Status | Details |
|---|------|-------|---------|--------|---------|
| 97.1 | **Security validator module** | @generator | `security_validator.py` | ✅ | Centralized utilities: path validation (null byte, traversal, extension whitelist), ZIP slip defense (`safe_zip_extract_member`), XXE protection (`safe_parse_xml`), credential redaction (10 patterns), M query scrubbing, template sanitization |
| 97.2 | **ZIP slip + XXE defense** | @extractor | `extract_tableau_data.py` | ✅ | `read_tableau_file()` validates ZIP entries, `safe_parse_xml()` blocks DOCTYPE+ENTITY |
| 97.3 | **Input validation** | @orchestrator | `migrate.py` | ✅ | File path validation (null bytes, extension whitelist), `TABLEAU_TOKEN_SECRET` env var |
| 97.4 | **Multi-tenant injection defense** | @deployer | `deploy/multi_tenant.py` | ✅ | Placeholder validation, null byte blocking, context-aware escaping (JSON/M/TMDL) |
| 97.5 | **Wizard input hardening** | @orchestrator | `wizard.py` | ✅ | `getpass` for sensitive input, `_validate_file_path()`, extension whitelist |
| 97.6 | **Tests** | @tester | `tests/test_security.py` | ✅ | 64 tests: path (11), ZIP (7), XXE (6), credentials (14), sanitization (6), multi-tenant (7), wizard (4), scanning (4), integration (5) |

**Success:** All inputs validated, no credential leaks in output, ZIP/XXE attacks blocked.

---

### Sprint 98 — Merged Lakehouse / Fabric Output (@merger, @orchestrator) ✅ SHIPPED

**Goal:** Enable `--shared-model` multi-workbook merge to produce Fabric-native output (Lakehouse + Dataflow Gen2 + Notebook + DirectLake SemanticModel + Pipeline) instead of only PBIP format. Replaces originally-planned "Governance & Compliance" (deferred to Sprint 99).

| # | Item | Owner | File(s) | Status | Details |
|---|------|-------|---------|--------|---------|
| 98.1 | **Fabric branch in import_shared_model** | @orchestrator | `import_to_powerbi.py` | ✅ | `output_format='fabric'` routes merged data to `FabricProjectGenerator.generate_project()` |
| 98.2 | **CLI wiring** | @orchestrator | `migrate.py` | ✅ | `run_shared_model_migration()` forwards `output_format` from CLI args |
| 98.3 | **Thin reports in Fabric mode** | @merger | `import_to_powerbi.py` | ✅ | Thin reports placed inside Fabric project dir with `byPath` to DirectLake SemanticModel |
| 98.4 | **No model-explorer for Fabric** | @orchestrator | `import_to_powerbi.py` | ✅ | Fabric output skips `.pbip` model-explorer wrapper |
| 98.5 | **Tests** | @tester | `tests/test_shared_model_fabric.py` | ✅ | 12 tests: Fabric artifacts (5), thin reports (3), merged content (2), parameters (2) |

**Success:** `--shared-model wb1.twbx wb2.twbx --output-format fabric` produces complete merged Fabric project.

---

### Sprint 99 — Governance & Advanced Formulas (@assessor, @deployer, @converter) ✅ SHIPPED

**Goal:** Enterprise governance framework (naming conventions, data classification, audit trail) combined with the highest-priority formula intelligence items deferred from Sprint 97.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 99.1 | **Naming convention enforcement** | @assessor | `powerbi_import/governance.py` (new) | Medium | Configurable rules: measure prefix (`m_`), column naming (snake_case/camelCase), table naming (PascalCase). Auto-rename on generation or warn-only mode. Rules defined in `config.json` governance section. |
| 99.2 | **Data classification annotations** | @assessor | `powerbi_import/governance.py` | Medium | Scan TMDL columns for PII patterns (email, SSN, phone, name) → add `dataClassification` annotation. Generate classification report. |
| 99.3 | **Audit trail** | @deployer | `powerbi_import/governance.py` | Medium | Immutable JSON audit log: who migrated what, when, source hash, output hash, deployment target. Append-only `migration_audit.jsonl`. |
| 99.4 | **Sensitivity label assignment** | @deployer | `deploy/deployer.py` | Medium | Map Tableau project permissions → PBI sensitivity labels (Public/General/Confidential/Highly Confidential). Apply via PBI REST API. |
| 99.5 | **LOOKUP / PREVIOUS_VALUE** | @converter | `dax_converter.py` | High | `LOOKUP([Measure], -1)` → `CALCULATE([Measure], OFFSET(-1, ...))`. `PREVIOUS_VALUE(start)` → VAR/RETURN with OFFSET fallback. |
| 99.6 | **Window function PARTITIONBY** | @converter | `dax_converter.py` | Medium | Extract `compute-using`/`addressing` from table calc XML → WINDOW/OFFSET `PARTITIONBY` and `ORDERBY` clauses. Currently uses `ALL/ALLSELECTED` approximation. |
| 99.7 | **Spatial → Azure Maps visual** | @generator | `visual_generator.py` | Medium | Tableau MAKEPOINT coordinates → PBI `azureMap` visual with lat/lon data roles. Replace `0+comment` DAX. |
| 99.8 | **Tests** | @tester | `tests/test_governance.py` (new), `tests/test_advanced_formulas.py` (new) | Medium | 50+ tests: naming rules (10), PII detection (8), audit log (6), sensitivity mapping (4), LOOKUP/PREVIOUS_VALUE (10), PARTITIONBY (8), Azure Maps (4) |

**Success:** Enterprise customers can enforce naming standards and PII classification. LOOKUP/PREVIOUS_VALUE formulas convert to OFFSET-based DAX.

---

### Sprint 100 — Production Hardening & v26.0.0 Release (@orchestrator, @deployer, @tester) ✅ SHIPPED

**Goal:** Harden for production enterprise use: rolling deployments, monitoring integration, migration SLA tracking, 1000-workbook stress test, and v26.0.0 release.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 100.1 | **Rolling deployment** | @deployer | `deploy/pbi_deployer.py` | High | `--rolling`: Deploy updated dataset first, validate refresh success, then swap reports. Automatic rollback on validation failure. Blue/green deployment with canary phase. |
| 100.2 | **Migration SLA tracking** | @orchestrator | `powerbi_import/sla_tracker.py` (new) | Medium | Per-workbook SLAs: max migration time, min fidelity score, required data validation pass. Track compliance across batch migrations. Alert on SLA breach. |
| 100.3 | **Monitoring integration** | @deployer | `powerbi_import/monitoring.py` (new) | Medium | Export migration metrics to Azure Monitor (custom metrics), Application Insights (traces/events), or Prometheus (push gateway). `--monitor azure|prometheus|none`. |
| 100.4 | **Endorsement & certification** | @deployer | `deploy/deployer.py` | Low | `--endorse promoted|certified`: Set endorsement status on deployed datasets/reports via PBI REST API. |
| 100.5 | **1000-workbook stress test** | @tester | `tests/test_production_scale.py` (new) | High | Synthetic: 1000 workbooks × 3 tables × 5 measures. Assert: total < 120s, peak memory < 2GB, 0 broken artifacts, SLA compliance ≥ 99%. |
| 100.6 | **v26.0.0 release** | @orchestrator | `pyproject.toml`, docs | Low | Version bump, CHANGELOG, README, GAP_ANALYSIS, KNOWN_LIMITATIONS, copilot-instructions. |

### v26.0.0 Success Criteria

| Metric | v25.0.0 | Target v26.0.0 | v26.0.0 Actual |
|--------|---------|----------------|----------------|
| Tests | ~6,192 | **7,000+** | **6,400+** across 134 files |
| Self-healing pipeline | ❌ | **Auto-repair TMDL, visuals, M queries** | ✅ Sprint 96 |
| Security hardening | ❌ | **ZIP slip, XXE, credential redaction** | ✅ Sprint 97 |
| Merged Fabric output | ❌ | **--shared-model + --output-format fabric** | ✅ Sprint 98 |
| Governance framework | ❌ | **Naming, PII classification, audit** | ✅ Sprint 99 |
| LOOKUP/PREVIOUS_VALUE | ❌ | **OFFSET-based conversion** | ✅ Sprint 99 |
| Rolling deployment | ❌ | **Blue/green with auto-rollback** | ✅ Sprint 100 |
| Scale tested | 500 workbooks | **1000 workbooks** (<120s) | ✅ Sprint 100 |
| SLA tracking | ❌ | **Per-workbook SLA compliance** | ✅ Sprint 100 |

---

## v27.0.0 — Advanced Intelligence & Marketplace (Sprints 101–106)

### Sprint 101: Recursive LOD Parser ✅ SHIPPED

**Owner:** @converter  
**Goal:** Replace the iterative 50-iteration LOD parser with a true recursive descent parser for arbitrary nesting depth.

| # | Item | Owner | Status |
|---|------|-------|--------|
| 101.1 | Recursive descent `_parse_lod_recursive()` in `dax_converter.py` | @converter | ✅ |
| 101.2 | Nested LOD depth 3+ support (FIXED→INCLUDE→EXCLUDE chains) | @converter | ✅ |
| 101.3 | Sibling LOD support at same level | @converter | ✅ |
| 101.4 | Tests: 12 tests (basic, nested, depth-5, siblings, multi-table) | @tester | ✅ |

### Sprint 102: Window Function Depth ✅ SHIPPED

**Owner:** @converter  
**Goal:** Multi-level PARTITIONBY + multi-column ORDERBY + MATCHBY for DAX window functions.

| # | Item | Owner | Status |
|---|------|-------|--------|
| 102.1 | `_build_window_clauses()` helper — unified ORDERBY/PARTITIONBY/MATCHBY builder | @converter | ✅ |
| 102.2 | `partition_fields` dict: `order_by`, `partition_by`, `match_by` | @converter | ✅ |
| 102.3 | Multi-column ORDERBY with sort direction (ASC/DESC) | @converter | ✅ |
| 102.4 | Tests: 10 tests (basic, frame, partition_by, orderby, matchby, combined) | @tester | ✅ |

### Sprint 103: Migration Marketplace ✅ SHIPPED

**Owner:** @orchestrator  
**Goal:** Versioned pattern registry for community DAX recipes, visual mappings, and M query templates.

| # | Item | Owner | Status |
|---|------|-------|--------|
| 103.1 | `marketplace.py` — PatternRegistry, Pattern, PatternMetadata classes | @orchestrator | ✅ |
| 103.2 | JSON-file catalogue loader with versioned search/filter | @orchestrator | ✅ |
| 103.3 | `apply_dax_recipes()` — inject/replace DAX measures from patterns | @orchestrator | ✅ |
| 103.4 | `apply_visual_overrides()` — override visual type mappings | @orchestrator | ✅ |
| 103.5 | `examples/marketplace/` — 3 built-in patterns (revenue_ytd, yoy_growth, map_override) | @orchestrator | ✅ |
| 103.6 | Tests: 12 tests (metadata, registry, search, versioning, apply, export) | @tester | ✅ |

### Sprint 104: DAX Recipe Overrides ✅ SHIPPED

**Owner:** @converter  
**Goal:** Industry-specific KPI measure templates for Healthcare, Finance, and Retail.

| # | Item | Owner | Status |
|---|------|-------|--------|
| 104.1 | `dax_recipes.py` — HEALTHCARE_RECIPES (6 KPIs), FINANCE_RECIPES (8 KPIs), RETAIL_RECIPES (7 KPIs) | @converter | ✅ |
| 104.2 | `apply_recipes()` — inject/replace/overwrite modes | @converter | ✅ |
| 104.3 | `recipes_to_marketplace_format()` — bridge to PatternRegistry | @converter | ✅ |
| 104.4 | Tests: 12 tests (industries, apply, overwrite, replace, marketplace format) | @tester | ✅ |

### Sprint 105: Industry Model Templates ✅ SHIPPED

**Owner:** @generator  
**Goal:** Pre-built semantic model skeletons for Healthcare, Finance, and Retail.

| # | Item | Owner | Status |
|---|------|-------|--------|
| 105.1 | `model_templates.py` — Healthcare star schema (Encounters, Patients, Providers, Facilities) | @generator | ✅ |
| 105.2 | Finance star schema (Financials, Accounts, CostCenters, AR) | @generator | ✅ |
| 105.3 | Retail star schema (Sales, Products, Stores, Customers) | @generator | ✅ |
| 105.4 | `apply_template()` — merge template into migrated tables (enrich columns, add relationships) | @generator | ✅ |
| 105.5 | Tests: 13 tests (list, get, apply, enrich, relationships, deep copy) | @tester | ✅ |

### Sprint 106: Shapefile/GeoJSON Passthrough ✅ SHIPPED

**Owner:** @extractor  
**Goal:** Extract .shp/.geojson/.topojson from .twbx → PBI shape map configuration.

| # | Item | Owner | Status |
|---|------|-------|--------|
| 106.1 | `geo_passthrough.py` — GeoExtractor (ZIP extraction with path traversal defense) | @extractor | ✅ |
| 106.2 | Format classification (.geojson, .topojson, .shp components) | @extractor | ✅ |
| 106.3 | `build_shape_map_config()` — PBI shapeMap visual configuration | @generator | ✅ |
| 106.4 | `copy_to_registered_resources()` — deploy geo files into .pbip project | @generator | ✅ |
| 106.5 | GeoJSON property extraction for key binding | @extractor | ✅ |
| 106.6 | Tests: 13 tests (classify, extract, build config, copy, integration) | @tester | ✅ |

### v27.0.0 Success Criteria

| Metric | Target | v27.0.0 Actual |
|--------|--------|----------------|
| LOD nesting depth | Unlimited (recursive) | ✅ Recursive descent, tested to depth 5+ |
| Window function clauses | ORDERBY + PARTITIONBY + MATCHBY | ✅ All three supported |
| Marketplace patterns | Versioned registry with search | ✅ PatternRegistry with semver |
| Industry DAX recipes | 3 verticals, 20+ KPIs | ✅ 21 KPIs across 3 industries |
| Model templates | 3 star schemas | ✅ Healthcare, Finance, Retail |
| Geo passthrough | .geojson + .shp extraction | ✅ 8 file types, shape map config |
| Tests | 6,400+ | ✅ 6,454 passed |

### Sprint 107: Unified HTML Report Template ✅ SHIPPED

**Owner:** @generator  
**Goal:** Centralize CSS/JS across all 9 HTML report generators into a shared template module with Fluent/PBI design.

| # | Item | Owner | Status |
|---|------|-------|--------|
| 107.1 | `html_template.py` — shared CSS/JS template module with design tokens, components | @generator | ✅ |
| 107.2 | Upgrade `generate_report.py` (batch migration dashboard) | @generator | ✅ |
| 107.3 | Upgrade `server_assessment.py` (server portfolio assessment) | @assessor | ✅ |
| 107.4 | Upgrade `global_assessment.py` (global + governance reports) | @assessor | ✅ |
| 107.5 | Upgrade `merge_report_html.py` (shared model merge report) | @merger | ✅ |
| 107.6 | Upgrade `telemetry_dashboard.py` (observability dashboard) | @deployer | ✅ |
| 107.7 | Upgrade `visual_diff.py`, `comparison_report.py`, `merge_assessment.py` | @assessor | ✅ |
| 107.8 | Dark mode support (`prefers-color-scheme: dark`) | @generator | ✅ |
| 107.9 | Unit tests for html_template.py | @tester | ✅ |

### v27.1.0 Success Criteria

| Metric | Target | v27.1.0 Actual |
|--------|--------|----------------|
| HTML reports unified | 9/9 generators | ✅ All 9 upgraded |
| Shared CSS/JS module | 1 template file | ✅ `html_template.py` (640+ lines) |
| Duplicate CSS removed | >1,000 lines | ✅ ~1,230 lines removed |
| Dark mode | CSS `prefers-color-scheme` | ✅ Full dark theme |
| Tests | 6,454+ | ✅ 6,454+ passed |

---

## v28.0.0 — Extensibility, Web UI & AI-Assisted Migration (Sprints 108–117)

### Sprint 108: TDS/TDSX Standalone Datasource Migration ✅ SHIPPED

**Owner:** @extractor, @generator  
**Goal:** Migrate Tableau `.tds`/`.tdsx` data source files to Power BI SemanticModel-only projects.

| # | Item | Owner | Status |
|---|------|-------|--------|
| 108.1 | Extract `<datasource>` root → synthetic `<workbook>` wrapper | @extractor | ✅ |
| 108.2 | Datasource-only detection in PBIPGenerator (skip Report folder) | @generator | ✅ |
| 108.3 | `.pbip` artifacts reference SemanticModel for datasource-only | @generator | ✅ |
| 108.4 | Batch scanner includes `.tds`/`.tdsx` extensions | @orchestrator | ✅ |
| 108.5 | E2E test updates for `DATASOURCE_ONLY_WORKBOOKS` | @tester | ✅ |

---

### Phase 1 — Core Extensibility (Sprints 109–111) ✅ SHIPPED

| Sprint | Theme | Owner(s) | Priority | Status | Deliverables |
|--------|-------|----------|----------|--------|--------------|
| **109** | **TDSX with Hyper data inlining** | @extractor, @generator | P1 | ✅ | `hyper_files.json` loaded as 17th artifact. `tmdl_generator` inlines Hyper row data into M `#table()`/`Csv.Document()` partitions via `generate_m_from_hyper()`. 15 tests. |
| **110** | **REST API endpoint** | @orchestrator, @deployer | P1 | ✅ | stdlib `http.server` API: `POST /migrate`, `GET /status/{id}`, `GET /download/{id}`, `GET /health`, `GET /jobs`. Thread-safe job store, multipart upload, Dockerfile. 21 tests. |
| **111** | **Incremental schema drift detection** | @extractor, @assessor | P2 | ✅ | `schema_drift.py`: compare extraction snapshots (tables, columns, calculations, worksheets, relationships, parameters, filters). `--check-drift SNAPSHOT_DIR` CLI. JSON + summary output. 25 tests. |

### Phase 2 — Intelligence & UX (Sprints 112–114)

---

#### Sprint 112 — LLM-Assisted DAX Correction (@converter, @orchestrator)

**Goal:** Optional AI-powered refinement for approximated DAX formulas — send measures tagged with `MigrationNote` containing "approximated" to an LLM for semantic correction. Pluggable backend (Azure OpenAI, OpenAI, local/Ollama). Original DAX preserved as annotation.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 112.1 | **LLM client module** | @converter | `powerbi_import/llm_client.py` (new) | High | Pluggable backend: Azure OpenAI (`urllib`+managed identity), OpenAI (`urllib`+API key), local/Ollama (`localhost:11434`). Token counting (tiktoken-compatible estimation), cost tracking, exponential retry with backoff, `--llm-max-calls N` budget cap. No external deps (stdlib `urllib.request` + `json`). |
| 112.2 | **DAX refinement prompt engine** | @converter | `powerbi_import/llm_client.py` | High | Structured prompt: Tableau formula + current approximated DAX + table schema (columns, types) + relationship context → refined DAX + confidence score (0–1) + explanation. System prompt enforces DAX syntax rules and Power BI compatibility. |
| 112.3 | **Selective targeting** | @generator | `tmdl_generator.py` | Medium | Post-generation pass: scan all measures for `MigrationNote` containing "approximated", "fallback", or "no equivalent". Queue for LLM refinement. Skip exact conversions. Cap at `--llm-max-calls` (default 50). |
| 112.4 | **Accept/reject validation** | @converter | `powerbi_import/llm_client.py` | Medium | Parse LLM response → validate DAX syntax (balanced parens, known function names, valid column refs) → accept if valid, reject and keep original if malformed. Log accepted/rejected ratio. |
| 112.5 | **CLI integration** | @orchestrator | `migrate.py` | Low | `--llm-refine`, `--llm-provider azure-openai|openai|local`, `--llm-model gpt-4o`, `--llm-endpoint URL`, `--llm-max-calls N`. Env vars: `LLM_API_KEY`, `AZURE_OPENAI_ENDPOINT`. |
| 112.6 | **Cost & refinement report** | @converter | `powerbi_import/llm_client.py` | Low | JSON report: per-measure original → approximated → refined, confidence, tokens used, estimated cost. Summary: total measures refined, acceptance rate, total tokens. |
| 112.7 | **Tests** | @tester | `tests/test_llm_client.py` (new) | Medium | 30+ tests: client init (3 backends), prompt construction, response parsing, DAX validation, cost tracking, rate limiting, mock API responses, budget cap, selective targeting, accept/reject logic. |

**Agent work:**
- **@converter** — owns `llm_client.py`: prompt engine, response parsing, DAX validation, cost tracking
- **@generator** — selective targeting in `tmdl_generator.py`: scan MigrationNotes, queue approximated measures
- **@orchestrator** — CLI flags in `migrate.py`, env var wiring
- **@tester** — 30+ tests with mock LLM responses

---

#### Sprint 113 — Streamlit Web UI Phase 1 (@orchestrator, @generator)

**Goal:** Browser-based migration wizard for users who prefer GUI over CLI. 6-step wizard wrapping the existing pipeline. Streamlit is an **optional dependency** — core migration remains stdlib-only.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 113.1 | **App scaffold & routing** | @orchestrator | `web/app.py` (new) | High | 6-step wizard: Upload (.twb/.twbx/.tds) → Configure (output format, culture, calendar range) → Assess (readiness radar chart) → Migrate (real-time progress) → Validate (artifact summary) → Download (.pbip ZIP). Streamlit session state for temp dirs, cleanup on session end. |
| 113.2 | **File upload & extraction** | @orchestrator | `web/app.py` | Medium | Drag-and-drop with `st.file_uploader`. Save to temp dir. Call `read_tableau_file()` + `extract_tableau_data()`. Display extraction summary (tables, measures, visuals count). Security: validate file extension + size limit (500MB). |
| 113.3 | **Assessment preview** | @orchestrator | `web/app.py` | Medium | Call `assess_migration_readiness()`. Render 9-category pass/warn/fail table. Strategy recommendation (Import/DirectQuery/Composite). Show connection string audit warnings. |
| 113.4 | **Migration execution with progress** | @orchestrator | `web/app.py` | Medium | Call `import_to_powerbi()` in background thread. `st.progress()` bar linked to `ProgressTracker`. Real-time log streaming to `st.expander`. Fidelity score display on completion. |
| 113.5 | **Download & artifact preview** | @generator | `web/app.py` | Medium | ZIP the output directory. `st.download_button` for `.pbip` project. Preview: list generated pages, visuals per page, measure count, relationship diagram (Mermaid in `st.markdown`). |
| 113.6 | **Docker packaging** | @orchestrator | `web/Dockerfile` (new) | Low | `python:3.12-slim` + `pip install streamlit`. `docker-compose.yml` for one-command startup. Health check endpoint. Volume mount for input/output. |
| 113.7 | **Tests** | @tester | `tests/test_web_app.py` (new) | Medium | 25+ tests: upload validation, config→args mapping, pipeline integration (mock Streamlit), ZIP generation, session cleanup. |

**Agent work:**
- **@orchestrator** — owns `web/app.py`: scaffold, upload, config, pipeline execution, Docker
- **@generator** — artifact preview, relationship diagram rendering
- **@tester** — 25+ tests with mock Streamlit session

---

#### Sprint 114 — Streamlit Web UI Phase 2 (@orchestrator, @assessor, @merger)

**Goal:** Extend Web UI with batch mode, shared-model merge UI, side-by-side visual diff, DAX formula editor, and Fabric deployment button.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 114.1 | **Batch mode page** | @orchestrator | `web/pages/batch.py` (new) | Medium | Multi-file upload or folder path. Progress table (workbook name, status, fidelity). Batch summary dashboard reusing `generate_report.py` HTML. Download all as ZIP. |
| 114.2 | **Shared model merge page** | @merger | `web/pages/merge.py` (new) | High | Multi-workbook upload → merge heatmap (table overlap scores), conflict list, force-merge toggle, model name input. Preview merged table list. Download shared model + thin reports. |
| 114.3 | **Visual diff viewer** | @assessor | `web/pages/diff.py` (new) | Medium | Side-by-side: Tableau worksheet list (from extraction JSON) vs PBI page/visual list. Per-visual field coverage, encoding gaps. Reuses `visual_diff.py` output. |
| 114.4 | **DAX formula editor** | @orchestrator | `web/pages/editor.py` (new) | Medium | Select a measure → view Tableau formula + converted DAX side-by-side. In-place edit DAX. Re-validate with `dax_optimizer.py`. Save overrides to `config.json`. |
| 114.5 | **Fabric deployment button** | @deployer | `web/pages/deploy.py` (new) | Medium | Workspace ID input + auth (token or SP). One-click deploy via `deploy/deployer.py`. Status polling. Deployment report display. |
| 114.6 | **Tests** | @tester | `tests/test_web_app_v2.py` (new) | Medium | 25+ tests: batch upload, merge UI flows, diff rendering, DAX edit round-trip, deploy mock. |

**Agent work:**
- **@orchestrator** — batch page, DAX editor, page routing
- **@merger** — merge page with heatmap and conflict resolution
- **@assessor** — visual diff viewer page
- **@deployer** — Fabric deployment page with auth flow
- **@tester** — 25+ tests

---

### Phase 3 — Production & Enterprise (Sprints 115–117)

---

#### Sprint 115 — PDF Export & Report Packaging (@generator, @assessor)

**Goal:** Generate PDF versions of all HTML migration/assessment reports for offline distribution and executive review. Optional dependency (`weasyprint` or stdlib HTML-to-PDF via `html2pdf`).

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 115.1 | **PDF renderer module** | @generator | `powerbi_import/pdf_renderer.py` (new) | High | Pluggable backend: (1) `weasyprint` (optional), (2) stdlib fallback generating a simplified paginated HTML with `@media print` CSS. `render_html_to_pdf(html_content, output_path)` API. |
| 115.2 | **Print-optimized CSS** | @generator | `powerbi_import/html_template.py` | Medium | Add `@media print` styles to shared template: page breaks, margin control, hide interactive elements (sort buttons, search), expand collapsed sections. A4/Letter page size support. |
| 115.3 | **CLI integration** | @orchestrator | `migrate.py` | Low | `--pdf` flag on `--assess`, `--global-assess`, `--assess-merge`, server assessment. `--pdf-only` to skip HTML. |
| 115.4 | **Report packaging** | @assessor | `powerbi_import/assessment.py` | Medium | `--report-package` generates a ZIP containing: HTML report + PDF + extraction JSON + fidelity summary CSV. Single deliverable for stakeholders. |
| 115.5 | **Tests** | @tester | `tests/test_pdf_export.py` (new) | Medium | 20+ tests: PDF render (mock weasyprint), print CSS validation, CLI flag wiring, package ZIP structure. |

**Agent work:**
- **@generator** — PDF renderer module + print CSS in html_template.py
- **@assessor** — report packaging (HTML + PDF + data ZIP)
- **@orchestrator** — CLI flags
- **@tester** — 20+ tests

---

#### Sprint 116 — Workspace-Level Migration Planner (@assessor, @deployer, @extractor)

**Goal:** Given a Tableau Server site (via `--server` + REST API), generate a complete enterprise migration plan: dependency graph, wave assignments, effort estimates, Fabric workspace mapping, RLS group mapping, refresh schedule migration plan.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 116.1 | **Server site discovery** | @extractor | `tableau_export/server_client.py` | Medium | New endpoint: `get_site_topology()` → all workbooks + datasources + published datasources + users + groups + schedules + subscriptions. Build adjacency map (workbook↔datasource dependencies). |
| 116.2 | **Migration plan generator** | @assessor | `powerbi_import/migration_planner.py` (new) | High | Input: site topology + per-workbook assessment. Output: dependency-ordered migration waves, per-wave effort estimate (hours), team assignment suggestions, critical-path identification. Respects datasource dependencies (shared datasources migrate first). |
| 116.3 | **Fabric workspace mapper** | @deployer | `powerbi_import/migration_planner.py` | Medium | Map Tableau Projects → Fabric Workspaces. Tableau Sites → Fabric Capacities. Suggest workspace partitioning based on content groups and RLS boundaries. Output: workspace mapping JSON. |
| 116.4 | **RLS group mapping** | @deployer | `powerbi_import/migration_planner.py` | Medium | Map Tableau user-filters + groups → Azure AD group assignments for PBI RLS roles. Output: mapping CSV (Tableau group → Azure AD group → RLS role). |
| 116.5 | **Refresh schedule mapping** | @deployer | `powerbi_import/refresh_generator.py` | Low | Extend existing refresh migration: map entire site's extract-refresh schedules to PBI refresh configs. Detect conflicts (>8 daily refreshes on Pro). Output: schedule migration report. |
| 116.6 | **Migration plan HTML report** | @assessor | `powerbi_import/migration_planner.py` | Medium | Interactive HTML: wave timeline (Gantt-style), dependency graph, workspace map, effort heatmap, RLS mapping table. Uses shared `html_template.py`. |
| 116.7 | **CLI integration** | @orchestrator | `migrate.py` | Low | `--plan-migration` flag (requires `--server`). Output: migration plan JSON + HTML report. |
| 116.8 | **Tests** | @tester | `tests/test_migration_planner.py` (new) | Medium | 30+ tests: topology parsing, wave ordering, effort calculation, workspace mapping, RLS mapping, schedule conflicts, HTML report structure. |

**Agent work:**
- **@extractor** — site topology discovery in server_client.py
- **@assessor** — migration plan generator + HTML report
- **@deployer** — workspace mapper, RLS mapper, refresh schedule extension
- **@orchestrator** — CLI flag
- **@tester** — 30+ tests

---

#### Sprint 117 — v28.0.0 Release & Hardening (All Agents)

**Goal:** Version bump, comprehensive integration testing, documentation update, PyPI publish, and codebase hardening.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 117.1 | **Version bump** | @orchestrator | `pyproject.toml` | Low | `27.1.0` → `28.0.0`. Update all version references. |
| 117.2 | **CHANGELOG update** | @orchestrator | `CHANGELOG.md` | Medium | Document all Phase 1–3 sprints (108–117) with per-sprint summaries. |
| 117.3 | **Cross-phase E2E tests** | @tester | `tests/test_v28_e2e.py` (new) | High | End-to-end: extract → LLM refine (mock) → generate → validate → deploy (mock) → plan (mock). 15+ integration tests spanning all new v28 features. |
| 117.4 | **Documentation refresh** | @orchestrator | `README.md`, `docs/*.md` | Medium | Update GAP_ANALYSIS, KNOWN_LIMITATIONS, MAPPING_REFERENCE, FAQ with v28 features. Update copilot-instructions.md agent table. |
| 117.5 | **Real-world validation** | @tester | `tests/test_real_world_e2e.py` | Medium | Re-run all 27 real-world + sample workbooks. Assert 100% fidelity, 0 regressions vs v27.1.0 baseline. |
| 117.6 | **PyPI publish** | @deployer | `.github/workflows/publish.yml` | Low | Tag `v28.0.0` → auto-publish wheel to PyPI via OIDC trusted publisher. |
| 117.7 | **Test baseline** | @tester | — | — | Target: **6,900+** total tests. |

---

### v28.0.0 Success Criteria

| Metric | Target | Phase 1 Actual |
|--------|--------|----------------|
| TDS standalone migration | ✅ | ✅ Shipped (Sprint 108) |
| TDSX with embedded Hyper data | ✅ | ✅ Shipped (Sprint 109) |
| REST API with Docker | ✅ | ✅ Shipped (Sprint 110) |
| Schema drift detection | ✅ | ✅ Shipped (Sprint 111) |
| LLM-assisted DAX | Sprint 112 | — |
| Web UI (Streamlit) | Sprints 113–114 | — |
| PDF report export | Sprint 115 | — |
| Migration planner | Sprint 116 | — |
| Tests | **6,900+** | 6,714 |

### v28.0.0 Agent Ownership Matrix

| Agent | Phase 1 (108–111) | Phase 2 (112–114) | Phase 3 (115–117) |
|-------|-------------------|-------------------|-------------------|
| **@orchestrator** | 108, 110 | 112, 113, 114 | 115, 116, 117 |
| **@extractor** | 108, 109, 111 | — | 116 |
| **@converter** | — | 112 | — |
| **@generator** | 108, 109 | 113 | 115 |
| **@assessor** | 111 | 114 | 115, 116 |
| **@merger** | — | 114 | — |
| **@deployer** | 110 | 114 | 116, 117 |
| **@tester** | 108–111 (cross-cutting) | 112–114 (cross-cutting) | 115–117 (cross-cutting) |
