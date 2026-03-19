# Known Limitations

This document lists known limitations and approximations in the Tableau to Power BI migration tool.

> **Last updated:** v18.0.0 (Sprint 64) — many previous limitations have been addressed in Sprints 27-64. See below for current status.
>
> **v18.0.0 notes:** Report schema downgraded from 3.1.0 to 2.0.0 for backward compatibility with PBI Desktop April 2025+. Post-merge safety: cycle detection, column type validation, DAX reference integrity checks. RLS predicate merging & propagation validation. Deploy hardening: permission pre-flight, conflict detection, rollback, refresh polling. Hyper file 3-tier reader (tableauhyperapi + SQLite + header scan). ResourcePackageType fix for custom themes. **Sprint 64**: Incremental merge workflow — `--add-to-model` / `--remove-from-model` CLI flags, `MergeManifest` provenance, TMDL reverse-engineering parser, manifest diff for CI audit.

---

## Extraction Limitations

| Area | Limitation | Impact |
|------|-----------|--------|
| **Hyper files** | ✅ `.hyper` file column metadata AND row-level data loaded via 3-tier reader chain: (1) `tableauhyperapi` optional package for full v2+ support, (2) SQLite fallback for older formats, (3) header-only scan. Multi-schema discovery (`Extract`, `public`, `stg`). Configurable sample rows via `--hyper-rows N`. Column stats (distinct_count, min, max) and metadata enrichment with DirectQuery recommendations | Requires optional `tableauhyperapi` pip package for proprietary v2+ Hyper formats; without it, some v2+ files still fall back to metadata-only |
| **Tableau Server/Cloud** | ✅ `--server` CLI flag enables direct extraction from Tableau Server/Cloud via REST API (PAT or password auth). Live connections still need reconfiguration in PBI |
| **Tableau 2024.3+** | ✅ Dynamic parameters with database queries are now fully extracted and converted to M partition with `Value.NativeQuery()`. Dynamic zone visibility may still be partially handled | Newer dynamic zone features may need manual adjustment |
| **Custom shapes** | Shape encoding extracts the field reference only — actual image files are not migrated | Custom shape visuals will show default markers |
| **OAuth credentials** | Credential metadata is stripped by design | Data source connections need re-authentication in Power BI |
| **Nested layout containers** | Deeply nested containers may lose relative positioning | Some dashboard layouts may need manual adjustment |
| **Rich tooltips** | HTML/custom layout tooltips are converted to run-level text (bold, color, font_size extracted) | Complex HTML tooltip layouts are not preserved |

## Generation Limitations

| Area | Limitation | Impact |
|------|-----------|--------|
| **Visual positioning** | Dashboard objects are scaled proportionally with overlap detection, but not pixel-perfect | Some manual layout adjustment may be needed |
| **Sparklines** | Table/matrix sparkline columns are generated as lineChart sparkline configs | Limited to basic line sparklines; area/bar sparklines not supported |

## DAX Conversion Limitations

### Functions with No DAX Equivalent

| Tableau Function | Output | Reason |
|-----------------|--------|--------|
| MAKEPOINT, MAKELINE, DISTANCE, BUFFER, AREA, INTERSECTION | `0` + comment | No spatial functions in DAX |
| HEXBINX, HEXBINY | `0` + comment | No hex-binning in DAX |
| COLLECT | `0` + comment | No spatial collection |
| SCRIPT_BOOL/INT/REAL/STR | ✅ `scriptVisual` (Python or R) + `BLANK()` DAX fallback | R/Python scripting → PBI Python/R visual containers with script text and input columns. `BLANK()` DAX measure generated for non-visual contexts. Requires Python/R runtime configured in PBI Desktop |
| SPLIT | `BLANK()` + comment | No string split to array in DAX |

### Approximated Functions

| Tableau Function | DAX Output | Accuracy |
|-----------------|------------|----------|
| REGEXP_MATCH | Smart pattern detection: `LEFT`/`RIGHT`/`CONTAINSSTRING`/`OR` | Handles `^literal`, `literal$`, `pat1\|pat2`, simple substrings; complex regex falls back to `CONTAINSSTRING` |
| REGEXP_REPLACE | Chained `SUBSTITUTE()` for common patterns; `CONTAINSSTRING`+`SUBSTITUTE` for character classes | No true regex groups or backreferences |
| REGEXP_EXTRACT | `MID(field, SEARCH("prefix", field) + len, LEN(field))` for fixed-prefix patterns | Falls back to `BLANK()` for complex patterns |
| REGEXP_EXTRACT_NTH | Delimiter→PATHITEM, prefix→MID/SEARCH, alternation→IF/CONTAINSSTRING | Falls back to `BLANK()` for complex patterns (v5.3.0) |
| RANK_PERCENTILE | `DIVIDE(RANKX()-1, COUNTROWS()-1)` | Edge cases with ties |
| RUNNING_SUM/AVG/COUNT | `CALCULATE(AGG, FILTER(ALLSELECTED(...)))` | Proper window semantics with partition support |
| WINDOW_SUM/AVG/MAX/MIN | `CALCULATE(inner, ALL/ALLEXCEPT)` with OFFSET-based frame boundaries | Frame start/end positions approximated via OFFSET for specific patterns |
| LTRIM/RTRIM | `TRIM()` | DAX TRIM removes all leading/trailing spaces |
| String `+` → `&` | All expression depths | Converted at all nesting levels since v4.0 |

## Visual Mapping Approximations

| Tableau Visual | PBI Mapping | Gap |
|---------------|------------|-----|
| Sankey / Chord / Network | ✅ Custom visual GUID (`sankeyDiagram`, `chordChart`, `networkNavigator`) or `decompositionTree` fallback | Custom visuals require AppSource installation in PBI Desktop |
| Gantt Bar / Lollipop | ✅ `ganttChart` (custom visual GUID) | Custom visual; time-axis semantics preserved |
| Butterfly / Waffle | hundredPercentStackedBarChart | ✅ IMPROVED — negate-one-measure hint in approximation note |
| Calendar Heat Map | matrix | ✅ IMPROVED — auto-enables conditional formatting properties + migration note |
| Packed Bubble / Strip Plot | scatterChart | ✅ FIXED — size encoding from `mark_encoding` auto-injected into Size data role |
| Bump Chart / Slope | lineChart | Ranking semantics lost |
| Motion chart (animated) | Not handled | No PBI play-axis animation |
| Violin plot | ✅ `boxAndWhisker` + custom visual (`ViolinPlot1.0.0`) | Maps to Box & Whisker; AppSource custom visual GUID available |
| Parallel coordinates | ✅ `lineChart` + custom visual (`ParallelCoordinates1.0.0`) | Maps to Line Chart; AppSource custom visual GUID available |

## Power Query M Limitations

| Area | Limitation |
|------|-----------|
| **Custom SQL params** | ✅ IMPLEMENTED — `Value.NativeQuery()` with parameter record binding and `[EnableFolding=true]` |
| **Hyper data** | ✅ `.hyper` files are now loaded via SQLite interface — row data injected into M `#table()` expressions. Some proprietary `.hyper` v2+ formats may fall back to metadata-only |
| **Query folding** | ✅ IMPLEMENTED — `m_transform_buffer()` + `m_transform_join(buffer_right=True)` for `Table.Buffer()` folding boundaries |

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
| **Custom SQL tables** | Tables defined by custom SQL are not matched by fingerprint (no table name) |
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
