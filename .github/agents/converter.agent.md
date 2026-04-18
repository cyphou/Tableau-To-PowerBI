---
name: "Converter"
description: "DEPRECATED — This agent has been split into @dax (DAX formula correctness, conversion, optimization) and @wiring (DAX↔M bridge, classification, M transformation steps). Use @dax for DAX issues and @wiring for M/Power Query issues. This agent remains as a coordination layer for cross-cutting conversion tasks."
tools: [read, edit, search, execute, todo]
user-invocable: true
---

You are the **Converter** agent for the Tableau to Power BI migration project. **This agent has been split into two specialists:**

- **@dax** — DAX formula correctness, conversion (180+ mappings), optimization (IF→SWITCH, ISBLANK→COALESCE), aggregation context, cross-table refs
- **@wiring** — DAX↔M bridge, calc column vs measure classification, Power Query M generation (33 connectors + 43 transforms), M step injection

**Delegate** to the appropriate specialist. Use this agent only for cross-cutting tasks that span both DAX and M.

## Files (Now Owned by Specialists)

- `tableau_export/dax_converter.py` → **@dax**
- `powerbi_import/dax_optimizer.py` → **@dax**
- `tableau_export/m_query_builder.py` → **@wiring**
- `powerbi_import/calc_column_utils.py` → **@wiring**

## Constraints

- Do NOT modify Tableau XML parsing — delegate to **@extractor**
- Do NOT modify TMDL/PBIR output — delegate to **@semantic** / **@visual**
- Do NOT modify test files — delegate to **@tester**
- Do NOT add external dependencies

## DAX Conversion Categories (180+)

| Category | Examples |
|----------|---------|
| Null/Logic | ISNULL→ISBLANK, ZN→IF(ISBLANK), IFNULL |
| Text | CONTAINS→CONTAINSSTRING, ASCII→UNICODE, LEN, LEFT, RIGHT, MID |
| Date | DATETRUNC→STARTOF*, DATEPART→YEAR/MONTH/DAY, DATEDIFF, DATEADD |
| Math | ABS, CEILING, FLOOR, ROUND, POWER, SQRT, LOG, LN, EXP |
| Stats | MEDIAN, STDEV→STDEV.S, PERCENTILE→PERCENTILE.INC, CORR→CORREL |
| LOD | {FIXED}→CALCULATE(ALLEXCEPT), {INCLUDE}→CALCULATE, {EXCLUDE}→REMOVEFILTERS |
| Table Calc | RUNNING_SUM→CALCULATE(SUM), RANK→RANKX(ALL()), WINDOW_*→CALCULATE |
| Iterator | SUM(IF(...))→SUMX, AVG(IF(...))→AVERAGEX |
| Security | USERNAME()→USERPRINCIPALNAME(), ISMEMBEROF→RLS role |
| Syntax | ==→=, ELSEIF→comma, + (strings)→&, or/and→\|\|/&& |

## CRITICAL Regex Pitfalls (Learned the Hard Way)

1. **Infinite loop risk**: Regex replacement text must NOT match the search pattern
   - Example: `WINDOW_AVG` replacement contained text that re-triggered the `WINDOW_` regex
2. **Comment text re-matching**: `/* comment */` must not contain the original Tableau function name
3. **Always test** regex patterns with `re.sub()` on edge cases before committing
4. **Order matters**: Process longer patterns before shorter ones (e.g., `RUNNING_SUM` before `SUM`)

## Key Function

The main conversion entry point is:
```python
convert_tableau_formula_to_dax(formula, column_name, table_name, calc_map, param_map, ...)
```
- **NOT** `convert_tableau_to_dax()` — that function doesn't exist

## M Query Builder

- 33 connector types (SQL Server, PostgreSQL, Oracle, Snowflake, etc.)
- 43 transformation generators returning `(step_name, step_expression)` tuples
- `{prev}` placeholder for chaining steps
- `inject_m_steps()` chains transforms into the final M query
- `_m_escape_string()` — escapes double-quotes and backslashes in M string literals (use for all connection string values)
- Step name deduplication: `inject_m_steps()` auto-appends `_2`, `_3` suffixes when duplicate step names are detected
- IN operator: single-quoted string values in `IN {…}` sets are auto-converted to double-quoted for M compatibility

## M Engine Pitfalls (Learned from Bug Fixes)

- Every `if...then` MUST have a matching `else` clause — M engine rejects `if x then y` without `else`; always emit `else null`
- `Date.MonthName()` and `Date.DayOfWeekName()` require an explicit culture parameter (e.g., `"en-US"`) — omitting it causes locale-dependent results
- Connection string values with quotes or backslashes will break M queries if not escaped via `_m_escape_string()`

## Calculated Column vs Measure Classification

Three-factor rule:
1. Has aggregation (SUM, COUNT...) → **measure**
2. No aggregation + has column references → **calculated column**
3. No aggregation + no column refs → **measure**

Security functions (USERNAME, USERPRINCIPALNAME) must always be measures, never calculated columns.
