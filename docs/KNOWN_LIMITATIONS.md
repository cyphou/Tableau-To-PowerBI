# Known Limitations

This document lists known limitations and approximations in the Tableau to Power BI migration tool.

---

## Extraction Limitations

| Area | Limitation | Impact |
|------|-----------|--------|
| **Hyper files** | `.hyper` extract data is not parsed — only XML metadata is read | Tables from Hyper extracts will have structure but no inline data |
| **Tableau Server/Cloud** | Live connections to Tableau Server are not reconnected | Connection strings reference the original server; must be reconfigured in PBI |
| **Tableau 2024.3+** | Dynamic zone visibility and database-query parameters not extracted | These newer features are ignored during migration |
| **Custom shapes** | Shape encoding extracts the field reference only — actual image files are not migrated | Custom shape visuals will show default markers |
| **OAuth credentials** | Credential metadata is stripped by design | Data source connections need re-authentication in Power BI |
| **Nested layout containers** | Deeply nested containers may lose relative positioning | Some dashboard layouts may need manual adjustment |
| **Rich tooltips** | HTML/custom layout tooltips are converted to plain text | Tooltip formatting is lost |
| **Multiple data sources** | All calculations are placed on the "main" table | Multi-datasource worksheets may lose datasource context |

## Generation Limitations

| Area | Limitation | Impact |
|------|-----------|--------|
| **No incremental migration** | Re-running regenerates everything from scratch | Manual edits to the .pbip project are overwritten |
| **No composite models** | All tables use Import mode | No DirectQuery or dual-mode tables |
| **No paginated reports** | Only interactive .pbip reports are generated | Paginated report layouts are not supported |
| **No data bars / sparklines** | These PBI visual types have no Tableau equivalent | |
| **No Small Multiples** | PBI Small Multiples feature is not auto-generated | Grid layouts need manual configuration |
| **Visual positioning** | Dashboard objects are scaled proportionally from Tableau canvas to PBI page size | Not pixel-perfect; overlapping is possible |
| **Textbox/Image** | Minimal HTML → plain text conversion | Rich text formatting is lost |

## DAX Conversion Limitations

### Functions with No DAX Equivalent

| Tableau Function | Output | Reason |
|-----------------|--------|--------|
| MAKEPOINT, MAKELINE, DISTANCE, BUFFER, AREA, INTERSECTION | `0` + comment | No spatial functions in DAX |
| HEXBINX, HEXBINY | `0` + comment | No hex-binning in DAX |
| COLLECT | `0` + comment | No spatial collection |
| SCRIPT_BOOL/INT/REAL/STR | `BLANK()` + comment | R/Python scripting has no DAX equivalent |
| SPLIT | `BLANK()` + comment | No string split to array in DAX |
| PREVIOUS_VALUE | Comment | Requires iterative patterns not available in DAX |

### Approximated Functions

| Tableau Function | DAX Output | Accuracy |
|-----------------|------------|----------|
| REGEXP_MATCH | `CONTAINSSTRING()` | Substring only, not true regex |
| REGEXP_REPLACE | `SUBSTITUTE()` | Literal replacement, no regex groups |
| REGEXP_EXTRACT | `BLANK()` | Placeholder |
| RANK_PERCENTILE | `DIVIDE(RANKX()-1, COUNTROWS()-1)` | Edge cases with ties |
| RUNNING_SUM/AVG/COUNT | `CALCULATE(AGG, ...)` | No window frame specification |
| WINDOW_SUM/AVG/MAX/MIN | `CALCULATE(inner, ALL/ALLEXCEPT)` | Loses window frame boundaries |
| LTRIM/RTRIM | `TRIM()` | Removes all leading/trailing spaces |
| LOOKUP | `LOOKUPVALUE()` | Doesn't handle offset parameter |
| String `+` → `&` | Only at depth 0 | Arithmetic `+` in string contexts may be preserved |

## Visual Mapping Approximations

| Tableau Visual | PBI Mapping | Gap |
|---------------|------------|-----|
| Sankey / Chord / Network | decompositionTree | Structurally different — hierarchical vs flow |
| Gantt Bar / Lollipop | clusteredBarChart | Loses time-axis semantics |
| Butterfly / Waffle | hundredPercentStackedBarChart | Loses symmetry |
| Calendar Heat Map | matrix | Lacks calendar grid structure |
| Packed Bubble / Strip Plot | scatterChart | Size encoding may not transfer |
| Bump Chart / Slope / Sparkline | lineChart | Ranking semantics lost |
| Motion chart (animated) | Not handled | No PBI play-axis animation |
| Violin plot | Not handled | No standard PBI visual |
| Parallel coordinates | Not handled | No standard PBI visual |

## Power Query M Limitations

| Area | Limitation |
|------|-----------|
| **OAuth/SSO** | M queries use hardcoded connection strings; no OAuth configuration |
| **Data gateway** | No on-premises data gateway configuration generated |
| **Incremental refresh** | No incremental refresh policy |
| **Parameterized sources** | Server/database names hardcoded; no PBI parameters for switching |
| **Hyper data** | `.hyper` files referenced in Prep flows produce empty `#table` |
| **Custom SQL params** | `Value.NativeQuery()` generated but parameter binding not supported |

## Deployment Limitations

| Area | Limitation |
|------|-----------|
| **No rollback** | If deployment fails mid-batch, there's no automatic undo |
| **No integration tests** | Deployment code is structurally tested but never against a real Fabric workspace |
| **PBIR schema** | Generated JSON isn't validated against Microsoft's published JSON schemas |
| **Windows paths** | OneDrive file locks may leave stale artifacts (handled via try/except) |

## Workarounds

For most limitations, the recommended workflow is:

1. Run the migration to generate the .pbip project
2. Open in Power BI Desktop
3. Review the migration metadata JSON for conversion notes
4. Manually adjust unsupported features (spatial, custom shapes, advanced formatting)
5. Re-authenticate data source connections
6. Validate measures and relationships in Model view
