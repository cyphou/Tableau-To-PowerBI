# Known Limitations

This document lists known limitations and approximations in the Tableau to Power BI migration tool.

> **Last updated:** v5.0.0 — many previous limitations have been addressed.

---

## Extraction Limitations

| Area | Limitation | Impact |
|------|-----------|--------|
| **Hyper files** | `.hyper` file headers and table structure are extracted (column names/types), but row-level data is not loaded | Tables from Hyper extracts will have structure but no inline data preview |
| **Tableau Server/Cloud** | Live connections to Tableau Server are not reconnected | Connection strings reference the original server; must be reconfigured in PBI |
| **Tableau 2024.3+** | Dynamic zone visibility and database-query parameters not fully extracted | These newer features may be ignored during migration |
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
| SCRIPT_BOOL/INT/REAL/STR | `BLANK()` + comment | R/Python scripting has no DAX equivalent |
| SPLIT | `BLANK()` + comment | No string split to array in DAX |

### Approximated Functions

| Tableau Function | DAX Output | Accuracy |
|-----------------|------------|----------|
| REGEXP_MATCH | Smart pattern detection: `LEFT`/`RIGHT`/`CONTAINSSTRING`/`OR` | Handles `^literal`, `literal$`, `pat1\|pat2`, simple substrings; complex regex falls back to `CONTAINSSTRING` |
| REGEXP_REPLACE | Chained `SUBSTITUTE()` for common patterns; `CONTAINSSTRING`+`SUBSTITUTE` for character classes | No true regex groups or backreferences |
| REGEXP_EXTRACT | `MID(field, SEARCH("prefix", field) + len, LEN(field))` for fixed-prefix patterns | Falls back to `BLANK()` for complex patterns |
| RANK_PERCENTILE | `DIVIDE(RANKX()-1, COUNTROWS()-1)` | Edge cases with ties |
| RUNNING_SUM/AVG/COUNT | `CALCULATE(AGG, FILTER(ALLSELECTED(...)))` | Proper window semantics with partition support |
| WINDOW_SUM/AVG/MAX/MIN | `CALCULATE(inner, ALL/ALLEXCEPT)` with OFFSET-based frame boundaries | Frame start/end positions approximated via OFFSET for specific patterns |
| LTRIM/RTRIM | `TRIM()` | DAX TRIM removes all leading/trailing spaces |
| String `+` → `&` | All expression depths | Converted at all nesting levels since v4.0 |

## Visual Mapping Approximations

| Tableau Visual | PBI Mapping | Gap |
|---------------|------------|-----|
| Sankey / Chord / Network | Custom visual GUID (if available) or decompositionTree | Custom visuals provide better fidelity when AppSource GUIDs are registered |
| Gantt Bar / Lollipop | clusteredBarChart | Loses time-axis semantics |
| Butterfly / Waffle | hundredPercentStackedBarChart | Loses symmetry |
| Calendar Heat Map | matrix | Lacks calendar grid structure |
| Packed Bubble / Strip Plot | scatterChart | Size encoding may not transfer |
| Bump Chart / Slope | lineChart | Ranking semantics lost |
| Motion chart (animated) | Not handled | No PBI play-axis animation |
| Violin plot | Not handled | No standard PBI visual |
| Parallel coordinates | Not handled | No standard PBI visual |

## Power Query M Limitations

| Area | Limitation |
|------|-----------|
| **Custom SQL params** | `Value.NativeQuery()` generated but parameter binding not supported |
| **Hyper data** | `.hyper` files referenced in Prep flows produce empty `#table` (metadata is extracted) |
| **Query folding** | No `Table.Buffer()` or `Value.NativeQuery()` optimization hints |

## Deployment Limitations

| Area | Limitation |
|------|-----------|
| **No real integration tests** | Deployment code is structurally tested but not against a real Fabric workspace |
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
