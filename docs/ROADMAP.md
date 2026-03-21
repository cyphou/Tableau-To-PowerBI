# Development Roadmap — v23.0.0 → v24.0.0

**Date:** 2026-03-21
**Baseline:** v22.0.0 — 5,683 tests across 113 test files, 0 failures
**Current state:** v22.0.0 shipped — dashboard layout engine, slicer intelligence (7 modes), visual fidelity depth (dual-axis, stacked bar orientation, trend lines), conditional formatting (diverging/stepped/categorical), real-world E2E suite (26 workbooks), layout regression tests, performance regression tests

---

## Executive Summary

The migration engine is **feature-complete for core single-workbook scenarios**. v22–v24 shift focus to:

| Version | Theme | Target Date | Status |
|---------|-------|-------------|--------|
| **v22.0.0** | Real-World Fidelity & Layout Intelligence | Sprints 76–80 | ✅ Shipped |
| **v23.0.0** | Web UI, AI-Assisted Migration & CI Maturity | Sprints 81–85 | 🔜 Next |
| **v24.0.0** | Composite Models, Live Sync & Enterprise Scale | Sprints 86–90 | Planned |

---

## Agent Ownership Matrix

| Agent | v22.0.0 Sprints | v23.0.0 Sprints | v24.0.0 Sprints |
|-------|----------------|----------------|----------------|
| **@orchestrator** | 76, 80 | 81, 83 | 86, 90 |
| **@extractor** | 76, 77 | — | 87 |
| **@converter** | 78 | 82 | 87 |
| **@generator** | 76, 77, 78, 79 | 82 | 86, 87 |
| **@assessor** | 79 | — | 88 |
| **@merger** | — | — | 88, 89 |
| **@deployer** | — | 83 | 89, 90 |
| **@tester** | 76–80 (cross-cutting) | 81–85 (cross-cutting) | 86–90 (cross-cutting) |

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
| 85.1 | **Web UI + LLM integration** | @orchestrator | `web/app.py` | Medium | LLM toggle in Web UI. Cost preview before refinement. |
| 85.2 | **E2E Web UI tests** | @tester | `tests/test_web_e2e.py` (new) | Medium | Upload → configure → migrate → download cycle. 15+ tests. |
| 85.3 | **v23.0.0 release** | @orchestrator | `pyproject.toml`, docs | Low | Version bump, CHANGELOG, README, copilot-instructions. |

### v23.0.0 Success Criteria

| Metric | v22.0.0 | Target v23.0.0 |
|--------|---------|----------------|
| Tests | ~5,500 | **5,800+** |
| Web UI | ❌ | **Streamlit wizard + Docker** |
| LLM-assisted DAX | ❌ | **Opt-in GPT/Claude** |
| PR migration preview | ❌ | **Auto-diff on PR** |
| Release automation | Manual | **Tag → publish pipeline** |
| Prep VAR/VARP | Approximated | **Correct** |
| Prep notInner | Approximated | **leftanti** |

---

## v24.0.0 — Composite Models, Live Sync & Enterprise Scale

### Sprint 86 — Composite Model Depth (@generator, @orchestrator)

**Goal:** Per-table StorageMode, aggregation tables, hybrid relationship validation.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 86.1 | **Per-table StorageMode** | @generator | `tmdl_generator.py` | High | `--mode composite`: classify tables (large→DirectQuery, small→Import). TMDL `mode` property on partitions. |
| 86.2 | **Aggregation table generation** | @generator | `tmdl_generator.py` | High | Auto-generate Import-mode agg tables with `alternateOf` annotations linking to detail columns. |
| 86.3 | **Hybrid relationship constraints** | @generator | `tmdl_generator.py` | Medium | Cross-storage-mode relationships → auto-set `oneDirection`. Warn on bi-directional cross-mode. |
| 86.4 | **Composite CLI flags** | @orchestrator | `migrate.py` | Low | `--composite-threshold ROWS`: tables above threshold → DirectQuery. `--agg-tables auto|none`. |
| 86.5 | **Tests** | @tester | `tests/test_composite_model.py` (new) | Medium | 30+ tests. |

---

### Sprint 87 — Extraction & Conversion Hardening (@extractor, @converter, @generator)

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

### Sprint 88 — Enterprise Portfolio Intelligence (@assessor, @merger)

**Goal:** Cross-workbook optimization: detect shared data patterns, recommend model consolidation, estimate org-wide migration effort with resource allocation.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 88.1 | **Data lineage graph** | @assessor | `global_assessment.py` | High | Build cross-workbook data lineage: datasource → tables → calculations → visuals. HTML interactive graph (D3.js force-directed or Sankey). |
| 88.2 | **Consolidation recommender** | @merger | `shared_model.py` | Medium | Beyond merge scoring: recommend which workbooks should share models vs remain standalone based on data overlap, update frequency, audience segmentation. |
| 88.3 | **Resource allocation planner** | @assessor | `server_assessment.py` | Medium | Based on complexity scores and wave plan: recommend team size, skill mix (DAX expert, M expert, visual designer), timeline per wave. |
| 88.4 | **Governance report** | @assessor | `server_assessment.py` | Medium | Executive summary: total workbooks, migration waves, estimated effort (hours), risk matrix, recommended sequence, dependency map. HTML + PDF export. |
| 88.5 | **Tests** | @tester | `tests/test_portfolio_intelligence.py` (new) | Medium | 25+ tests. |

---

### Sprint 89 — Live Sync & Incremental Refresh (@merger, @deployer)

**Goal:** Keep migrated PBI artifacts in sync with evolving Tableau workbooks. Detect source changes, compute incremental diff, auto-deploy updates.

| # | Item | Owner | File(s) | Est. | Details |
|---|------|-------|---------|------|---------|
| 89.1 | **Source change detection** | @merger | `incremental.py` | High | Compare Tableau workbook hash (from Server API `updatedAt`) against last migration manifest. Flag modified workbooks. |
| 89.2 | **Incremental diff generation** | @merger | `incremental.py` | High | For modified workbooks: extract → diff against previous extraction → generate only changed artifacts (new measures, modified visuals, updated M queries). |
| 89.3 | **Auto-deploy updates** | @deployer | `deploy/pbi_deployer.py` | Medium | `--sync` mode: detect changes → incremental migrate → deploy updated dataset/reports. Preserve existing refresh schedules and sharing. |
| 89.4 | **Change notification** | @deployer | `telemetry.py` | Low | Emit structured events for detected changes: `{workbook, change_type, affected_artifacts}`. Optionally post to webhook (Teams, Slack). |
| 89.5 | **Tests** | @tester | `tests/test_live_sync.py` (new) | Medium | 25+ tests. |

---

### Sprint 90 — Enterprise Scale & v24.0.0 Release (@orchestrator, @deployer, @tester)

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

**Key files:** `migrate.py`, `import_to_powerbi.py`, `wizard.py`, `progress.py`, `web/app.py` (new)

---

### @extractor — Tableau XML Intelligence

| Sprint | Deliverable | Priority |
|--------|------------|----------|
| 76 | **Container hierarchy extraction** (zone nesting, constraints, padding) | P0 |
| 77 | **Filter type classification** (7 filter modes → filter JSON) | P0 |
| 87 | **Published datasource resolution** (Server API fetch) | P1 |
| 87 | **Data type coercion rules** (auto-type → explicit M cast) | P2 |

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

**Key files:** `dax_converter.py`, `m_query_builder.py`, `prep_flow_parser.py`, `llm_client.py` (new)

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

**Key files:** `pbip_generator.py`, `visual_generator.py`, `tmdl_generator.py`

---

### @assessor — Migration Intelligence

| Sprint | Deliverable | Priority |
|--------|------------|----------|
| 79 | Formatting coverage sub-metric in visual assessment | P2 |
| 88 | **Data lineage graph** (cross-workbook D3.js/Sankey) | P1 |
| 88 | **Resource allocation planner** (team size, skill mix, timeline) | P1 |
| 88 | **Governance report** (executive summary, risk matrix, HTML+PDF) | P0 |

**Key files:** `assessment.py`, `server_assessment.py`, `global_assessment.py`

---

### @merger — Model Consolidation Intelligence

| Sprint | Deliverable | Priority |
|--------|------------|----------|
| 88 | **Consolidation recommender** (standalone vs shared decision) | P1 |
| 89 | **Source change detection** (Server API hash comparison) | P0 |
| 89 | **Incremental diff generation** (changed artifacts only) | P0 |

**Key files:** `shared_model.py`, `incremental.py`, `merge_config.py`

---

### @deployer — Enterprise Deployment & Sync

| Sprint | Deliverable | Priority |
|--------|------------|----------|
| 83 | **Release automation** (tag → build → publish pipeline) | P0 |
| 83 | **Dependency scanning** (pip-audit) | P2 |
| 89 | **Auto-deploy updates** (`--sync` mode) | P0 |
| 89 | **Change notification** (webhook: Teams/Slack) | P2 |
| 90 | **Enterprise deployment guide** | P1 |

**Key files:** `deploy/*.py`, `telemetry.py`, `gateway_config.py`

---

### @tester — Quality Gates & Coverage

| Sprint | Deliverable | Priority |
|--------|------------|----------|
| 76–80 | **v22 test files**: layout_engine, slicer_intelligence, visual_fidelity_v2, conditional_formatting, real_world_e2e, layout_regression, performance_regression | P0 |
| 81–85 | **v23 test files**: web_app, llm_client, ci_workflows, conversion_accuracy, web_e2e | P0 |
| 86–90 | **v24 test files**: composite_model, edge_cases, portfolio_intelligence, live_sync, enterprise_scale | P0 |
| 83 | **Coverage gate** (95% threshold in CI) | P1 |
| 83 | **Test annotations** (JUnit XML → inline PR comments) | P2 |

**Target test counts:** v22: 5,500+ → v23: 5,800+ → v24: 6,200+

---

## Sprint Sequencing (v22–v24)

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
  Sprint 83 (CI/CD)          ──→  Sprint 84 (Conversion Fixes)
                                       ↓
                             Sprint 85 (Integration + Release)

v24.0.0 — Enterprise Scale
  Sprint 86 (Composite)      ──→  Sprint 87 (Hardening)
           ↓                           ↓
  Sprint 88 (Portfolio Intel) ──→  Sprint 89 (Live Sync)
                                       ↓
                             Sprint 90 (Scale + Release)
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
