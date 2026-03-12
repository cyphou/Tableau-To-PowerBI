# Known Limitations

This document lists known limitations and approximations in the Tableau to Power BI migration tool.

> **Last updated:** v9.0.0 (Sprint 29) — many previous limitations have been addressed in Sprints 27-29. See below for current status.

---

## Extraction Limitations

| Area | Limitation | Impact |
|------|-----------|--------|
| **Hyper files** | ✅ `.hyper` file column metadata AND row-level data are now loaded via SQLite interface (`hyper_reader.py`). Some `.hyper` v2+ files may use a proprietary format that SQLite cannot read — falls back to metadata-only extraction | Tables from unsupported Hyper formats will have structure but no inline data |
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
| **Windows paths** | OneDrive file locks may leave stale artifacts (handled via try/except) |

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
