# Post-Migration Checklist

Use this checklist after running the migration tool to validate the generated Power BI project.

---

## 1. Open & Load

- [ ] Open the `.pbip` file in Power BI Desktop (March 2025+)
- [ ] Confirm the project loads without errors
- [ ] Check the notification bar for any warnings

## 2. Data Source Connections

- [ ] Go to **Transform Data** → verify each data source connection
- [ ] Re-enter credentials for each data source (OAuth, SQL auth, etc.)
- [ ] Refresh data to confirm connectivity
- [ ] For BigQuery: verify the billing project ID is correct
- [ ] For Oracle: verify the TNS/Easy Connect string format
- [ ] For on-premises sources: configure the data gateway

## 3. Semantic Model (Model View)

- [ ] Switch to **Model View** and review the diagram
- [ ] Verify all tables are present and populated
- [ ] Check relationship cardinalities (manyToOne vs manyToMany)
- [ ] Confirm relationship directions (single vs bi-directional)
- [ ] Look for inactive relationships (may need manual activation)
- [ ] Verify the Calendar table date range covers your data
- [ ] Check Date Hierarchy (Year → Quarter → Month → Day)

## 4. Measures & Calculated Columns

- [ ] In each table, review measures for correctness
- [ ] Check calculated columns compute expected values
- [ ] Look for `/* Migration note: ... */` comments in DAX formulas
- [ ] Verify cross-table references use `RELATED()` or `LOOKUPVALUE()` correctly
- [ ] Test time intelligence measures (YTD, PY, YoY%) if applicable
- [ ] Check What-If parameter slicers and connected measures

## 5. Report Pages

- [ ] Review each page layout — adjust visual positioning if needed
- [ ] Verify visual types match Tableau originals (check approximations)
- [ ] Click through slicers — confirm they filter correctly
- [ ] Test drill-through pages (right-click → Drill through)
- [ ] Check tooltip pages appear on hover
- [ ] Verify bookmarks (from Tableau stories) capture correct states
- [ ] Review mobile layout pages (if applicable)

## 6. Filters

- [ ] Check report-level filters in the Filters pane
- [ ] Verify page-level filters on each page
- [ ] Confirm visual-level filters work correctly
- [ ] Test TopN filters if present

## 7. Formatting & Theme

- [ ] Verify the custom theme colors match the Tableau originals
- [ ] Check conditional formatting (gradient colors)
- [ ] Review reference lines on axes
- [ ] Verify axis labels, legends, and data labels
- [ ] Check number formatting on measures and columns

## 8. Row-Level Security (RLS)

- [ ] Go to **Modeling** → **Manage Roles**
- [ ] Review each RLS role and its DAX filter expression
- [ ] Test with **View as Role** to confirm data filtering
- [ ] Assign Azure AD users/groups to roles after publishing

## 9. Performance

- [ ] Run **Performance Analyzer** on key pages
- [ ] Check for slow visuals or expensive DAX queries
- [ ] Consider adding aggregations for large datasets
- [ ] Review Direct Query performance if applicable

## 10. Publish & Share

- [ ] Publish to the correct Fabric workspace
- [ ] Configure scheduled refresh
- [ ] Set up RLS role assignments for end users
- [ ] Create a Power BI app for distribution (if needed)
- [ ] Compare key metrics between Tableau and Power BI outputs

## 11. Shared Semantic Model (Multi-Workbook)

If you used `--shared-model` to merge multiple workbooks:

- [ ] Open each `.pbip` thin report in Power BI Desktop and verify it loads
- [ ] Confirm all thin reports point to the same `.SemanticModel` folder
- [ ] In Model View, verify merged tables have all columns from all workbooks
- [ ] Check for namespaced measures (e.g., `Total Sales (WorkbookA)`) and verify correctness
- [ ] Review `merge_assessment.json` for conflict details
- [ ] If measures were namespaced, update visuals to use the correct measure
- [ ] Test cross-report consistency — same filter should produce same results in all thin reports

## 12. Tableau Prep Flows (Standalone)

If you used `--batch` on `.tfl`/`.tflx` files:

- [ ] Review each flow's `assessment.json` for grade (GREEN/YELLOW/RED)
- [ ] Import `.pq` Power Query M files into Power BI Desktop or Dataflow Gen2
- [ ] Verify source connection metadata in `Sources/*.json` matches your environment
- [ ] Review the cross-flow lineage report (`prep_lineage/prep_lineage_report.html`)
- [ ] Follow merge recommendations (chain collapse, source dedup) where applicable
- [ ] For YELLOW/RED flows: review script nodes and manual transformation steps
- [ ] If pairing with a workbook: use `python migrate.py workbook.twbx --prep flow.tfl`

## Quick Reference

| Tableau Feature | Where to Check in PBI |
|----------------|----------------------|
| Worksheets | Report pages → individual visuals |
| Dashboards | Report pages |
| Parameters | What-If parameter slicers |
| Calculated fields | Measures & calculated columns in Model view |
| Stories | Bookmarks |
| Filters | Filters pane (report/page/visual level) |
| User filters | Manage Roles (RLS) |
| Custom SQL | Transform Data → Advanced Editor |
| Actions | Action buttons, drill-through pages |
| Shared Semantic Model | All thin reports reference the same `.SemanticModel` folder via `definition.pbir` → `byPath` |
