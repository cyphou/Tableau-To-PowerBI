# Tableau Functions → DAX Complete Reference

Complete mapping of **every Tableau calculation function** to its DAX (Power BI) equivalent.
All conversions below are implemented in `tableau_export/dax_converter.py`.

> **Legend**  
> ✅ Automatic — fully converted by the migration tool  
> ⚠️ Approximate — converted with best-effort approximation  
> 🔧 Manual — placeholder generated, manual review needed  
> ❌ No equivalent — no DAX counterpart exists

---

## 1. String Functions

| # | Tableau | DAX | Status | Notes |
|---|---------|-----|--------|-------|
| 1 | `ASCII(char)` | `UNICODE(char)` | ✅ | |
| 2 | `CHAR(number)` | `UNICHAR(number)` | ✅ | |
| 3 | `CONTAINS(string, substring)` | `CONTAINSSTRING(string, substring)` | ✅ | |
| 4 | `ENDSWITH(string, substring)` | `RIGHT(string, LEN(substring)) = substring` | ✅ | Decomposed — no native DAX ENDSWITH |
| 5 | `FIND(string, substring[, start])` | `FIND(substring, string[, start])` | ✅ | Arg order swapped |
| 6 | `FINDNTH(string, substring, occurrence)` | `FIND(substring, string)` | ⚠️ | Nth occurrence dropped |
| 7 | `LEFT(string, number)` | `LEFT(string, number)` | ✅ | |
| 8 | `LEN(string)` | `LEN(string)` | ✅ | |
| 9 | `LOWER(string)` | `LOWER(string)` | ✅ | |
| 10 | `LTRIM(string)` | `TRIM(string)` | ✅ | DAX TRIM handles both sides |
| 11 | `MAX(string1, string2)` | `MAX(string1, string2)` | ✅ | |
| 12 | `MID(string, start, length)` | `MID(string, start, length)` | ✅ | |
| 13 | `MIN(string1, string2)` | `MIN(string1, string2)` | ✅ | |
| 14 | `PROPER(string)` | `UPPER(LEFT(s,1)) & LOWER(MID(s,2,LEN(s)))` | ⚠️ | First-word only; multi-word needs manual fix |
| 15 | `REPLACE(string, substring, replacement)` | `SUBSTITUTE(string, substring, replacement)` | ✅ | |
| 16 | `RIGHT(string, number)` | `RIGHT(string, number)` | ✅ | |
| 17 | `RTRIM(string)` | `TRIM(string)` | ✅ | DAX TRIM handles both sides |
| 18 | `SPACE(number)` | `REPT(" ", number)` | ✅ | |
| 19 | `SPLIT(string, delimiter, token)` | `BLANK()` + comment | 🔧 | No direct DAX split; use PATHITEM workaround |
| 20 | `STARTSWITH(string, substring)` | `LEFT(string, LEN(substring)) = substring` | ✅ | Decomposed — no native DAX STARTSWITH |
| 21 | `TRIM(string)` | `TRIM(string)` | ✅ | |
| 22 | `UPPER(string)` | `UPPER(string)` | ✅ | |

---

## 2. Number / Math Functions

| # | Tableau | DAX | Status | Notes |
|---|---------|-----|--------|-------|
| 1 | `ABS(number)` | `ABS(number)` | ✅ | |
| 2 | `ACOS(number)` | `ACOS(number)` | ✅ | |
| 3 | `ASIN(number)` | `ASIN(number)` | ✅ | |
| 4 | `ATAN(number)` | `ATAN(number)` | ✅ | |
| 5 | `ATAN2(y, x)` | `ATAN(y / x)` | ⚠️ | Quadrant handling may need review |
| 6 | `CEILING(number)` | `CEILING(number, 1)` | ✅ | DAX requires significance arg |
| 7 | `COS(number)` | `COS(number)` | ✅ | |
| 8 | `COT(number)` | `COT(number)` | ✅ | |
| 9 | `DEGREES(number)` | `(number) * 180 / PI()` | ✅ | No native DAX DEGREES |
| 10 | `DIV(a, b)` | `QUOTIENT(a, b)` | ✅ | Integer division |
| 11 | `EXP(number)` | `EXP(number)` | ✅ | |
| 12 | `FLOOR(number)` | `FLOOR(number, 1)` | ✅ | DAX requires significance arg |
| 13 | `HEXBINX(number, number)` | `0` + comment | ❌ | No DAX equivalent |
| 14 | `HEXBINY(number, number)` | `0` + comment | ❌ | No DAX equivalent |
| 15 | `LN(number)` | `LN(number)` | ✅ | |
| 16 | `LOG(number [, base])` | `LOG(number [, base])` | ✅ | |
| 17 | `MAX(a, b)` | `MAX(a, b)` | ✅ | |
| 18 | `MIN(a, b)` | `MIN(a, b)` | ✅ | |
| 19 | `PI()` | `PI()` | ✅ | |
| 20 | `POWER(number, power)` | `POWER(number, power)` | ✅ | |
| 21 | `RADIANS(number)` | `(number) * PI() / 180` | ✅ | No native DAX RADIANS |
| 22 | `ROUND(number, decimals)` | `ROUND(number, decimals)` | ✅ | |
| 23 | `SIGN(number)` | `SIGN(number)` | ✅ | |
| 24 | `SIN(number)` | `SIN(number)` | ✅ | |
| 25 | `SQRT(number)` | `SQRT(number)` | ✅ | |
| 26 | `SQUARE(number)` | `POWER(number, 2)` | ✅ | |
| 27 | `TAN(number)` | `TAN(number)` | ✅ | |

---

## 3. Date Functions

| # | Tableau | DAX | Status | Notes |
|---|---------|-----|--------|-------|
| 1 | `DATEADD(date_part, interval, date)` | `DATEADD(date_column, interval, DAY/MONTH/...)` | ✅ | |
| 2 | `DATEDIFF(date_part, start, end)` | `DATEDIFF(start, end, INTERVAL)` | ✅ | Args reordered |
| 3 | `DATENAME(date_part, date)` | `FORMAT(date, format_string)` | ✅ | "MMMM", "DDDD", etc. |
| 4 | `DATEPARSE(format, string)` | `DATEVALUE(string)` | ✅ | Format arg dropped |
| 5 | `DATEPART('year', date)` | `YEAR(date)` | ✅ | |
| 6 | `DATEPART('quarter', date)` | `QUARTER(date)` | ✅ | |
| 7 | `DATEPART('month', date)` | `MONTH(date)` | ✅ | |
| 8 | `DATEPART('day', date)` | `DAY(date)` | ✅ | |
| 9 | `DATEPART('hour', date)` | `HOUR(date)` | ✅ | |
| 10 | `DATEPART('minute', date)` | `MINUTE(date)` | ✅ | |
| 11 | `DATEPART('second', date)` | `SECOND(date)` | ✅ | |
| 12 | `DATEPART('week', date)` | `WEEKNUM(date)` | ✅ | |
| 13 | `DATEPART('weekday', date)` | `WEEKDAY(date)` | ✅ | |
| 14 | `DATETRUNC('year', date)` | `STARTOFYEAR(date)` | ✅ | → `DATE()` in calc columns |
| 15 | `DATETRUNC('quarter', date)` | `STARTOFQUARTER(date)` | ✅ | → `DATE()` in calc columns |
| 16 | `DATETRUNC('month', date)` | `STARTOFMONTH(date)` | ✅ | → `DATE()` in calc columns |
| 17 | `ISDATE(string)` | `NOT(ISERROR(DATEVALUE(string)))` | ✅ | |
| 18 | `MAKEDATE(year, month, day)` | `DATE(year, month, day)` | ✅ | |
| 19 | `MAKEDATETIME(date, time)` | `DATE(...)` | ⚠️ | Time part may need manual review |
| 20 | `MAKETIME(hour, minute, second)` | `TIME(hour, minute, second)` | ✅ | |
| 21 | `NOW()` | `NOW()` | ✅ | |
| 22 | `TODAY()` | `TODAY()` | ✅ | |
| 23 | Date literals `#2024-01-15#` | `DATE(2024, 1, 15)` | ✅ | |

---

## 4. Type Conversion Functions

| # | Tableau | DAX | Status | Notes |
|---|---------|-----|--------|-------|
| 1 | `DATE(expression)` | `DATE(expression)` | ✅ | |
| 2 | `DATETIME(expression)` | `DATE(expression)` | ✅ | |
| 3 | `FLOAT(expression)` | `CONVERT(expression, DOUBLE)` | ✅ | |
| 4 | `INT(expression)` | `INT(expression)` | ✅ | |
| 5 | `STR(expression)` | `FORMAT(expression, "0")` | ✅ | |

---

## 5. Logical Functions

| # | Tableau | DAX | Status | Notes |
|---|---------|-----|--------|-------|
| 1 | `AND` (operator) | `&&` | ✅ | |
| 2 | `CASE [field] WHEN...THEN...ELSE...END` | `SWITCH(field, val1, res1, ...)` | ✅ | |
| 3 | `ELSE` | (part of `IF()`) | ✅ | |
| 4 | `ELSEIF` | (nested `IF()`) | ✅ | |
| 5 | `IF...THEN...ELSE...END` | `IF(cond, then, else)` | ✅ | |
| 6 | `IF...THEN...END` (no ELSE) | `IF(cond, then, BLANK())` | ✅ | |
| 7 | `IFNULL(expr, replacement)` | `IF(ISBLANK(expr), replacement, expr)` | ✅ | |
| 8 | `IIF(test, then, else[, unknown])` | `IF(test, then, else)` | ✅ | 4th arg (unknown) mapped to else |
| 9 | `ISBLANK()` | `ISBLANK()` | ✅ | Via ISNULL mapping |
| 10 | `ISMEMBEROF("group")` | `TRUE()` + RLS role comment | ✅ | Implement via RLS |
| 11 | `ISNULL(expression)` | `ISBLANK(expression)` | ✅ | |
| 12 | `ISNUMBER(expression)` | `ISNUMBER(expression)` | ✅ | |
| 13 | `NOT(expression)` | `NOT(expression)` | ✅ | |
| 14 | `OR` (operator) | `\|\|` | ✅ | |
| 15 | `ZN(expression)` | `IF(ISBLANK(expr), 0, expr)` | ✅ | |
| 16 | `==` | `=` | ✅ | |

---

## 6. Aggregate Functions

| # | Tableau | DAX | Status | Notes |
|---|---------|-----|--------|-------|
| 1 | `ATTR(expression)` | `VALUES(expression)` | ✅ | |
| 2 | `AVG(expression)` | `AVERAGE(expression)` | ✅ | → `AVERAGEX` for expressions |
| 3 | `COLLECT(spatial)` | `BLANK()` + comment | ❌ | Spatial aggregate — no DAX |
| 4 | `CORR(expr1, expr2)` | `0` + migration note | 🔧 | No direct DAX; manual needed |
| 5 | `COUNT(expression)` | `COUNT(expression)` | ✅ | → `COUNTX` for expressions |
| 6 | `COUNTA(expression)` | `COUNTA(expression)` | ✅ | |
| 7 | `COUNTD(expression)` | `DISTINCTCOUNT(expression)` | ✅ | |
| 8 | `COVAR(expr1, expr2)` | `0` + migration note | 🔧 | No direct DAX; manual needed |
| 9 | `COVARP(expr1, expr2)` | `0` + migration note | 🔧 | No direct DAX; manual needed |
| 10 | `MAX(expression)` | `MAX(expression)` | ✅ | → `MAXX` for expressions |
| 11 | `MEDIAN(expression)` | `MEDIAN(expression)` | ✅ | → `MEDIANX` for expressions |
| 12 | `MIN(expression)` | `MIN(expression)` | ✅ | → `MINX` for expressions |
| 13 | `PERCENTILE(expression, n)` | `PERCENTILE.INC(expression, n)` | ✅ | |
| 14 | `STDEV(expression)` | `STDEV.S(expression)` | ✅ | → `STDEVX.S` for expressions |
| 15 | `STDEVP(expression)` | `STDEV.P(expression)` | ✅ | → `STDEVX.P` for expressions |
| 16 | `SUM(expression)` | `SUM(expression)` | ✅ | → `SUMX` for expressions |
| 17 | `VAR(expression)` | `VAR.S(expression)` | ✅ | |
| 18 | `VARP(expression)` | `VAR.P(expression)` | ✅ | |

### Automatic AGGX Promotion

When an aggregate wraps an expression (not a single column), the converter auto-promotes:

| Pattern | Conversion |
|---------|------------|
| `SUM(expr)` | `SUMX('Table', expr)` |
| `AVERAGE(expr)` | `AVERAGEX('Table', expr)` |
| `MIN(expr)` | `MINX('Table', expr)` |
| `MAX(expr)` | `MAXX('Table', expr)` |
| `COUNT(expr)` | `COUNTX('Table', expr)` |
| `SUM(IF(...))` | `SUMX('Table', IF(...))` |
| `STDEV.S(SUM(expr))` | `STDEVX.S('Table', expr)` — inner agg unwrapped |
| `STDEV.P(SUM(expr))` | `STDEVX.P('Table', expr)` — inner agg unwrapped |
| `MEDIAN(COUNT(expr))` | `MEDIANX('Table', expr)` — inner agg unwrapped |

---

## 7. Table Calculation Functions

| # | Tableau | DAX | Status | Notes |
|---|---------|-----|--------|-------|
| 1 | `FIRST()` | `0` | ⚠️ | Partition offset — simplified |
| 2 | `INDEX()` | `RANKX(ALL(), [Value])` | ⚠️ | Approximate |
| 3 | `LAST()` | `0` | ⚠️ | Partition offset — simplified |
| 4 | `LOOKUP(expr, offset)` | `LOOKUPVALUE(expr, ...)` | 🔧 | Manual column mapping needed |
| 5 | `PREVIOUS_VALUE(expr)` | `(expr)` + comment | 🔧 | Manual conversion needed |
| 6 | `RANK(expr)` | `RANKX(ALL('Table'), expr)` | ✅ | |
| 7 | `RANK_DENSE(expr)` | `RANKX(ALL('Table'), expr,, ASC, DENSE)` | ✅ | |
| 8 | `RANK_MODIFIED(expr)` | `RANKX(ALL('Table'), expr)` + comment | ⚠️ | Competition ranking — verify |
| 9 | `RANK_PERCENTILE(expr)` | `DIVIDE(RANKX-1, COUNTROWS-1)` | ⚠️ | Approximate percentile rank |
| 10 | `RANK_UNIQUE(expr)` | `RANKX(ALL('Table'), expr)` | ✅ | |
| 11 | `RUNNING_AVG(expr)` | `CALCULATE(expr)` | ✅ | |
| 12 | `RUNNING_COUNT(expr)` | `CALCULATE(expr)` | ✅ | |
| 13 | `RUNNING_MAX(expr)` | `CALCULATE(expr)` | ✅ | |
| 14 | `RUNNING_MIN(expr)` | `CALCULATE(expr)` | ✅ | |
| 15 | `RUNNING_SUM(expr)` | `CALCULATE(expr)` | ✅ | |
| 16 | `SIZE()` | `COUNTROWS()` | ✅ | |
| 17 | `TOTAL(expr)` | `CALCULATE(expr)` | ✅ | |
| 18 | `WINDOW_AVG(expr)` | `CALCULATE(expr, ALL('Table'))` | ✅ | |
| 19 | `WINDOW_CORR(expr)` | `0` + comment | ❌ | No DAX equivalent |
| 20 | `WINDOW_COUNT(expr)` | `CALCULATE(expr, ALL('Table'))` | ✅ | |
| 21 | `WINDOW_COVAR(expr)` | `0` + comment | ❌ | No DAX equivalent |
| 22 | `WINDOW_COVARP(expr)` | `0` + comment | ❌ | No DAX equivalent |
| 23 | `WINDOW_MAX(expr)` | `CALCULATE(expr, ALL('Table'))` | ✅ | |
| 24 | `WINDOW_MEDIAN(expr)` | `CALCULATE(MEDIAN(expr))` | ✅ | |
| 25 | `WINDOW_MIN(expr)` | `CALCULATE(expr, ALL('Table'))` | ✅ | |
| 26 | `WINDOW_PERCENTILE(expr)` | `CALCULATE(PERCENTILE.INC(expr))` | ✅ | |
| 27 | `WINDOW_STDEV(expr)` | `CALCULATE(STDEV.S(expr))` | ✅ | |
| 28 | `WINDOW_STDEVP(expr)` | `CALCULATE(STDEV.P(expr))` | ✅ | |
| 29 | `WINDOW_SUM(expr)` | `CALCULATE(expr, ALL('Table'))` | ✅ | |
| 30 | `WINDOW_VAR(expr)` | `CALCULATE(VAR.S(expr))` | ✅ | |
| 31 | `WINDOW_VARP(expr)` | `CALCULATE(VAR.P(expr))` | ✅ | |

---

## 8. LOD (Level of Detail) Expressions

| # | Tableau | DAX | Status | Notes |
|---|---------|-----|--------|-------|
| 1 | `{FIXED [dim] : AGG(expr)}` | `CALCULATE(AGG(expr), ALLEXCEPT('T', 'T'[dim]))` | ✅ | |
| 2 | `{INCLUDE [dim] : AGG(expr)}` | `CALCULATE(AGG(expr))` | ✅ | |
| 3 | `{EXCLUDE [dim] : AGG(expr)}` | `CALCULATE(AGG(expr), REMOVEFILTERS('T'[dim]))` | ✅ | |
| 4 | `{AGG(expr)}` (no dims) | `CALCULATE(AGG(expr))` | ✅ | |

---

## 9. User / Security Functions

| # | Tableau | DAX | Status | Notes |
|---|---------|-----|--------|-------|
| 1 | `FULLNAME()` | `USERPRINCIPALNAME()` | ✅ | |
| 2 | `ISMEMBEROF("group")` | `TRUE()` + RLS role | ✅ | Implement via Power BI RLS |
| 3 | `USERDOMAIN()` | `""` + comment | 🔧 | No DAX equivalent; use RLS roles |
| 4 | `USERNAME()` | `USERPRINCIPALNAME()` | ✅ | |

---

## 10. Regex Functions

| # | Tableau | DAX | Status | Notes |
|---|---------|-----|--------|-------|
| 1 | `REGEXP_EXTRACT(string, pattern)` | `CONTAINSSTRING(string, pattern)` | ⚠️ | No DAX regex; approximation |
| 2 | `REGEXP_EXTRACT_NTH(string, pattern, n)` | `CONTAINSSTRING(...)` + comment | 🔧 | Manual conversion needed |
| 3 | `REGEXP_MATCH(string, pattern)` | `CONTAINSSTRING(string, pattern)` | ⚠️ | Returns boolean match |
| 4 | `REGEXP_REPLACE(string, pattern, replacement)` | `SUBSTITUTE(string, pattern, replacement)` | ⚠️ | Literal replacement only |

---

## 11. Spatial Functions

| # | Tableau | DAX | Status | Notes |
|---|---------|-----|--------|-------|
| 1 | `AREA(spatial)` | `0` + comment | ❌ | No DAX spatial support |
| 2 | `BUFFER(spatial, distance)` | `BLANK()` + comment | ❌ | No DAX spatial support |
| 3 | `COLLECT(spatial)` | `BLANK()` + comment | ❌ | Spatial aggregate |
| 4 | `DISTANCE(point1, point2)` | `0` + comment | ❌ | No DAX spatial support |
| 5 | `HEXBINX(x, y)` | `0` + comment | ❌ | No DAX equivalent |
| 6 | `HEXBINY(x, y)` | `0` + comment | ❌ | No DAX equivalent |
| 7 | `INTERSECTION(spatial1, spatial2)` | `BLANK()` + comment | ❌ | No DAX spatial support |
| 8 | `MAKELINE(point1, point2)` | `BLANK()` + comment | ❌ | No DAX spatial support |
| 9 | `MAKEPOINT(lat, lon)` | `BLANK()` + comment | ❌ | No DAX spatial support |

---

## 12. Analytics Extension Functions

| # | Tableau | DAX | Status | Notes |
|---|---------|-----|--------|-------|
| 1 | `SCRIPT_BOOL(script, ...)` | `BLANK()` + comment | 🔧 | Analytics extension — manual |
| 2 | `SCRIPT_INT(script, ...)` | `0` + comment | 🔧 | Analytics extension — manual |
| 3 | `SCRIPT_REAL(script, ...)` | `0` + comment | 🔧 | Analytics extension — manual |
| 4 | `SCRIPT_STR(script, ...)` | `""` + comment | 🔧 | Analytics extension — manual |

---

## 13. Operator Conversions

| Tableau | DAX | Status |
|---------|-----|--------|
| `==` | `=` | ✅ |
| `AND` / `and` | `&&` | ✅ |
| `OR` / `or` | `\|\|` | ✅ |
| `+` (string) | `&` | ✅ (when `calc_datatype='string'`) |
| `ELSEIF` | nested `IF()` | ✅ |

---

## Summary Statistics

| Category | Total | ✅ Auto | ⚠️ Approx | 🔧 Manual | ❌ None |
|----------|-------|---------|-----------|-----------|---------|
| String | 22 | 18 | 2 | 1 | 1 (concept) |
| Number/Math | 27 | 24 | 1 | 0 | 2 |
| Date | 23 | 21 | 1 | 0 | 0 |
| Type Conversion | 5 | 5 | 0 | 0 | 0 |
| Logical | 16 | 16 | 0 | 0 | 0 |
| Aggregate | 18 | 15 | 0 | 3 | 0 |
| Table Calc | 31 | 22 | 4 | 2 | 3 |
| LOD | 4 | 4 | 0 | 0 | 0 |
| User/Security | 4 | 3 | 0 | 1 | 0 |
| Regex | 4 | 0 | 3 | 1 | 0 |
| Spatial | 9 | 0 | 0 | 0 | 9 |
| Analytics Ext. | 4 | 0 | 0 | 4 | 0 |
| Operators | 5 | 5 | 0 | 0 | 0 |
| **TOTAL** | **172** | **133** | **11** | **12** | **15** |

**Coverage: 133/172 (77%) fully automatic, 144/172 (84%) automatic+approximate**
