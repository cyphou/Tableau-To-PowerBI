# Known Limitations

This document lists known limitations and approximations in the Tableau to Power BI migration tool.

> **Last updated:** v26.0.0 (Sprint 98) — many previous limitations have been addressed in Sprints 27-98. See below for current status.
>
> **v26.0.0 notes (Sprints 96–98):** Self-healing migration pipeline: TMDL self-repair (broken refs, circular relationships, orphan measures), visual fallback cascade (degrade to simpler type on error), M query self-repair, recovery report documenting every auto-repair action (S96, 76 tests). Security hardening: `security_validator.py` with path validation (null byte, traversal, extension whitelist), ZIP slip defense, XXE protection (`safe_parse_xml`), credential detection/redaction (10 patterns), M query credential scrubbing, multi-tenant template substitution hardening, wizard input sanitization (S97, 64 tests). Merged Lakehouse/Fabric output: `--shared-model --output-format fabric` generates Lakehouse + Dataflow Gen2 + PySpark Notebook + DirectLake Semantic Model + Pipeline for merged multi-workbook models, thin report Fabric branch (S98, 12 tests). 6,263 tests across 131 files.
>
> **v25.0.0 notes:** Fabric-native artifact generation — `--output-format fabric` generates Lakehouse, Dataflow Gen2, PySpark Notebook, DirectLake Semantic Model, and Data Pipeline (S91). Deep extraction of Tableau 2024+ features: dynamic zone visibility, table extensions, multi-connection blending, linguistic schema for Q&A (S92). DAX optimizer engine: IF→SWITCH, COALESCE, constant folding, Time Intelligence auto-injection (S93). Cross-platform validation: query equivalence framework, SSIM visual comparison, regression suite generator (S94). 6,192 tests across 128 files.
>
> **v24.0.0 notes:** Composite model support: per-table StorageMode, aggregation tables, hybrid relationship constraints (S86). Extraction hardening: published datasource resolution, nested LOD, complex join graphs, multi-connection M queries, data type coercion (S87). Enterprise portfolio intelligence: data lineage graph, consolidation recommender, resource allocation planner, governance report (S88). Live sync: source change detection, incremental diff, auto-deploy, change notification (S89). Enterprise scale: parallel batch, 500-workbook benchmark (S90).
>
> **v22.0.0 notes:** Grid-snapping dashboard layout engine (S76). 7 slicer modes: dropdown, list, slider, date picker, relative date, search, between (S77). Visual fidelity depth: stacked bar orientation, dual-axis combo charts, reference band shading, trend line preservation (S78). Conditional formatting: diverging, stepped, categorical color scales, icon sets (S79). Real-world E2E suite: 26 workbooks, layout/performance regression tests (S80). **Sprint 84:** Prep VAR/VARP proper M variance formulas, bump chart RANKX auto-injection, PDF connector page range, Salesforce SOQL/API depth, REGEX→M fallback.

---

## Extraction Limitations

| Area | Limitation | Impact |
|------|-----------|--------|
| **Hyper files** | ✅ `.hyper` file column metadata AND row-level data loaded via 3-tier reader chain: (1) `tableauhyperapi` optional package for full v2+ support, (2) SQLite fallback for older formats, (3) header-only scan. Multi-schema discovery (`Extract`, `public`, `stg`). Configurable sample rows via `--hyper-rows N`. Column stats (distinct_count, min, max) and metadata enrichment with DirectQuery recommendations | Requires optional `tableauhyperapi` pip package for proprietary v2+ Hyper formats; without it, some v2+ files still fall back to metadata-only |
| **Tableau Server/Cloud** | ✅ `--server` CLI flag enables direct extraction from Tableau Server/Cloud via REST API (PAT or password auth). Live connections still need reconfiguration in PBI |
| **Tableau 2024.3+** | ✅ Dynamic parameters with database queries fully extracted and converted to M partition with `Value.NativeQuery()`. Dynamic zone visibility (S92) parses conditions and maps to PBI bookmark visibility toggles. Table extensions (Einstein Discovery, external API) generate M `Web.Contents()` or placeholder. Linguistic schema extraction feeds PBI Q&A synonyms. | Some newer Tableau 2024.3+ features may still need manual adjustment |
| **Custom shapes** | Shape encoding extracts the field reference only — actual image files are not migrated | Custom shape visuals will show default markers |
| **OAuth credentials** | Credential metadata is stripped by design | Data source connections need re-authentication in Power BI |
| **Nested layout containers** | ✅ IMPROVED (v22/S76) — Grid-snapping engine handles 3-level nesting; 4+ levels may lose precision | Very deeply nested containers may need manual adjustment |
| **Rich tooltips** | HTML/custom layout tooltips are converted to run-level text (bold, color, font_size extracted) | Complex HTML tooltip layouts are not preserved |

## Generation Limitations

| Area | Limitation | Impact |
|------|-----------|--------|
| **Visual positioning** | ✅ IMPROVED (v22/S76) — Grid-snapping layout engine replaces proportional scaling. Container hierarchy extraction, row/column grid cells, floating z-order, responsive breakpoints. Not pixel-perfect but preserves grid structure | Some manual layout adjustment may still be needed for deeply nested containers |
| **Sparklines** | Table/matrix sparkline columns are generated as lineChart sparkline configs | Limited to basic line sparklines; area/bar sparklines not supported |
| **Bump charts** | ✅ IMPROVED (Sprint 84) — Auto-generated RANKX measure injected for ranking semantics | Maps to lineChart; ranking is approximated via `RANKX(ALL(), [measure],, ASC, Dense)` |
| **Fabric-native output** | ✅ NEW (v25/S91) — `--output-format fabric` generates Lakehouse, Dataflow Gen2, PySpark Notebook, DirectLake Semantic Model, and Data Pipeline. Activity IDs in pipelines are placeholders requiring workspace binding. | Fabric artifacts require Fabric workspace capacity to deploy and test |
| **DAX optimizer** | ✅ NEW (v25/S93) — `--optimize-dax` rewrites verbose DAX (IF→SWITCH, COALESCE, constant fold, SUMX simplify). `--time-intelligence auto` injects YTD/PY/YoY%. Opt-in only to preserve original semantics by default. | Optimized DAX may differ from direct Tableau→DAX conversion; original preserved as annotation |

## DAX Conversion Limitations

### Functions with No DAX Equivalent

| Tableau Function | Output | Reason |
|-----------------|--------|--------|
| MAKEPOINT, MAKELINE, DISTANCE, BUFFER, AREA, INTERSECTION | `0` + comment | No spatial functions in DAX |
| HEXBINX, HEXBINY | `0` + comment | No hex-binning in DAX |
| COLLECT | `0` + comment | No spatial collection |
| SCRIPT_BOOL/INT/REAL/STR | ✅ `scriptVisual` (Python or R) + `BLANK()` DAX fallback | R/Python scripting → PBI Python/R visual containers with script text and input columns. `BLANK()` DAX measure generated for non-visual contexts. Requires Python/R runtime configured in PBI Desktop |
| **SPLIT** | ✅ IMPLEMENTED — `SPLIT(string, delim, token)` → `PATHITEM(SUBSTITUTE(string, delim, "|"), token)`. Negative index → `PATHITEMREVERSE`. 2-arg form defaults to token 1 | Requires pipe character not present in data |

### Approximated Functions

| Tableau Function | DAX Output | Accuracy |
|-----------------|------------|----------|
| REGEXP_MATCH | Smart pattern detection: `LEFT`/`RIGHT`/`CONTAINSSTRING`/`OR` | ✅ IMPROVED — Handles `^literal$` exact match, `^literal`, `literal$`, `.+`/`.*` always-true, `pat1\|pat2`, simple substrings; complex regex falls back to `CONTAINSSTRING` |
| REGEXP_REPLACE | Chained `SUBSTITUTE()` for common patterns; `CONTAINSSTRING`+`SUBSTITUTE` for character classes | No true regex groups or backreferences |
| REGEXP_EXTRACT | `MID(field, SEARCH("prefix", field) + len, LEN(field))` for fixed-prefix patterns | Falls back to `BLANK()` for complex patterns |
| REGEXP_EXTRACT_NTH | Delimiter→PATHITEM, prefix→MID/SEARCH, alternation→IF/CONTAINSSTRING | Falls back to `BLANK()` for complex patterns (v5.3.0) |
| RANK_PERCENTILE | `DIVIDE(RANKX()-1, COUNTROWS()-1)` | Edge cases with ties |
| RUNNING_SUM/AVG/COUNT | `CALCULATE(AGG, FILTER(ALLSELECTED(...)))` | Proper window semantics with partition support |
| WINDOW_SUM/AVG/MAX/MIN | `CALCULATE(inner, ALL/ALLEXCEPT)` with OFFSET-based frame boundaries | Frame start/end positions approximated via OFFSET for specific patterns |
| LTRIM/RTRIM | ✅ FIXED — `LTRIM` → MID-based left-trim (preserves trailing spaces); `RTRIM` → LEFT-based right-trim (preserves leading spaces) | Distinct from TRIM which removes both sides |
| String `+` → `&` | All expression depths | Converted at all nesting levels since v4.0 |

## Visual Mapping Approximations

| Tableau Visual | PBI Mapping | Gap |
|---------------|------------|-----|
| Sankey / Chord / Network | ✅ Custom visual GUID (`sankeyDiagram`, `chordChart`, `networkNavigator`) or `decompositionTree` fallback | Custom visuals require AppSource installation in PBI Desktop |
| Gantt Bar / Lollipop | ✅ `ganttChart` (custom visual GUID) | Custom visual; time-axis semantics preserved |
| Butterfly / Waffle | hundredPercentStackedBarChart | ✅ IMPROVED — negate-one-measure hint in approximation note |
| Calendar Heat Map | matrix | ✅ IMPROVED — auto-enables conditional formatting properties + migration note |
| Packed Bubble / Strip Plot | scatterChart | ✅ FIXED — size encoding from `mark_encoding` auto-injected into Size data role |
| Bump Chart / Slope | lineChart | ✅ IMPROVED (S84) — Auto-generated RANKX measure for ranking semantics |
| Motion chart (animated) | Not handled | No PBI play-axis animation |
| Violin plot | ✅ `boxAndWhisker` + custom visual (`ViolinPlot1.0.0`) | Maps to Box & Whisker; AppSource custom visual GUID available |
| Parallel coordinates | ✅ `lineChart` + custom visual (`ParallelCoordinates1.0.0`) | Maps to Line Chart; AppSource custom visual GUID available |

## Power Query M Limitations

| Area | Limitation |
|------|-----------|
| **Custom SQL params** | ✅ IMPLEMENTED — `Value.NativeQuery()` with parameter record binding and `[EnableFolding=true]` |
| **Hyper data** | ✅ `.hyper` files are now loaded via SQLite interface — row data injected into M `#table()` expressions. Some proprietary `.hyper` v2+ formats may fall back to metadata-only |
| **Query folding** | ✅ IMPLEMENTED — `m_transform_buffer()` + `m_transform_join(buffer_right=True)` for `Table.Buffer()` folding boundaries |
| **PDF connector** | ✅ IMPROVED (Sprint 84) — `Pdf.Tables(File.Contents(...), [StartPage=N, EndPage=M])` with page range and table index selection |
| **Salesforce connector** | ✅ IMPROVED (Sprint 84) — SOQL passthrough via `Value.NativeQuery()`, API version specification, relationship traversal via `Table.ExpandRecordColumn()` |
| **REGEX in M** | ✅ IMPLEMENTED (Sprint 84) — `m_regex_match/extract/replace()` + `convert_tableau_regex_to_m()` dispatcher using `Text.RegexMatch/Extract/Replace` with `try/otherwise` |

## Deployment Limitations

| Area | Limitation |
|------|-----------|
| **PBI Service deployment** | ✅ `--deploy WORKSPACE_ID` deploys via REST API (Azure AD auth required). Integration tests are opt-in (`@pytest.mark.integration`) — not run in standard CI |
| **Fabric deployment** | Fabric deployment is structurally tested but not against a real workspace |
| **Windows paths** | ✅ OneDrive file locks handled via `_rmtree_with_retry()` with exponential backoff (3 attempts). Stale TMDL files retried with 0.3s backoff |

## Plugin System Limitations

| Area | Limitation |
|------|------------|
| **Plugin API stability** | The plugin hook interface (`plugins.py`) is functional but the API is not yet frozen — custom plugins may need updates across major versions |
| **Plugin discovery** | Plugins are auto-discovered from `examples/plugins/` via `importlib` — only `.py` files with a `register(hooks)` function are loaded |

## Schema Compatibility

| Area | Limitation |
|------|------------|
| **PBIR schema versions** | Generated output targets PBIR v4.0 with report schema 2.0.0, page schema 2.0.0, and visualContainer schema 2.5.0. Compatible with PBI Desktop April 2025+ (v2.142.928.0). Use `--check-schema` to verify forward-compatibility with newer PBI Desktop versions |

## Shared Semantic Model Limitations

| Area | Limitation |
|------|------------|
| **Table matching** | Tables are matched by physical fingerprint (`connection_type\|server\|database\|table_name`) — tables with the same name but from different servers are NOT merged |
| **Column type conflicts** | When the same column has different types across workbooks, the wider type is used (e.g., integer → string). Data may need type casting after migration |
| **Measure namespacing** | Conflicting measures (same name, different formula) are namespaced as `Measure (Workbook)`. Visuals referencing the original measure name may need manual update |
| **Custom SQL tables** | ✅ RESOLVED — Custom SQL tables are now fingerprinted by normalized SQL hash (`_normalize_sql()` + SHA-256). Identical queries across workbooks are merge candidates |
| **Cross-workbook RLS** | RLS roles from multiple workbooks are merged but may have overlapping rules. Review `Manage Roles` in PBI Desktop |
| **Post-merge validation** | Use `--strict-merge` to block generation on validation failures (relationship cycles, column type errors, broken DAX references). Without it, validation is advisory only |

## Workarounds

For most limitations, the recommended workflow is:

1. Run the migration to generate the .pbip project
2. Open in Power BI Desktop (December 2025+)
3. Review the migration metadata JSON for conversion notes
4. Manually adjust unsupported features (spatial, custom shapes, advanced formatting)
5. Re-authenticate data source connections
6. Validate measures and relationships in Model view
7. Use `--assess` flag for pre-migration readiness analysis
8. Use `--incremental` for iterative refinement without losing manual edits
9. Use `--deploy WORKSPACE_ID` to publish directly to Power BI Service
10. Use `--server` to extract workbooks directly from Tableau Server/Cloud
11. Use `--languages fr-FR,de-DE` to generate multi-language culture TMDL files with translated display folders
12. Use `--goals` to convert Tableau Pulse metrics to Power BI Goals/Scorecard artifacts
13. Use `--check-schema` to verify PBIR schema forward-compatibility before opening in newer PBI Desktop versions
14. Use `--shared-model wb1.twbx wb2.twbx` to merge multiple workbooks into a shared semantic model with thin reports
15. Use `--assess-merge` to preview merge feasibility before generating
16. Use `--migrate-schedules` (with `--server`) to extract Tableau refresh schedules and generate PBI refresh config JSON
17. Use `notebook_api.MigrationSession` for interactive Jupyter-based migration with DAX/visual override and notebook generation
