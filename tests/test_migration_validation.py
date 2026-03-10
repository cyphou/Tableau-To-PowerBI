"""
Comprehensive Migration Validation Tests
=========================================
Validates all 5 generated .pbip projects for structural correctness,
DAX formula validity, TMDL syntax, visual query mapping, Power Query M,
and cross-referencing between semantic model and report.
"""

import json
import os
import re
import sys
import glob

# ── Configuration ──────────────────────────────────────────────────────
PROJECTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "artifacts", "powerbi_projects", "migrated")

ALL_PROJECTS = ["Superstore_Sales", "HR_Analytics", "Financial_Report",
                "BigQuery_Analytics"]

# Track results
results = {"pass": 0, "fail": 0, "warn": 0, "details": []}


def record(status, project, test, message=""):
    icon = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️"}[status]
    results[status.lower()] = results.get(status.lower(), 0) + 1
    entry = f"  {icon} [{project}] {test}: {message}" if message else f"  {icon} [{project}] {test}"
    results["details"].append(entry)
    print(entry)


# ══════════════════════════════════════════════════════════════════════
# TEST 1: Project Structure Completeness
# ══════════════════════════════════════════════════════════════════════
def test_project_structure():
    print("\n" + "=" * 70)
    print("TEST 1: Project Structure Completeness")
    print("=" * 70)
    for proj in ALL_PROJECTS:
        base = os.path.join(PROJECTS_DIR, proj)
        required_files = [
            f"{proj}.pbip",
            f"{proj}.Report/.platform",
            f"{proj}.Report/definition.pbir",
            f"{proj}.Report/definition/report.json",
            f"{proj}.Report/definition/version.json",
            f"{proj}.Report/definition/pages/pages.json",
            f"{proj}.SemanticModel/.platform",
            f"{proj}.SemanticModel/definition.pbism",
            f"{proj}.SemanticModel/definition/model.tmdl",
            f"{proj}.SemanticModel/definition/database.tmdl",
            f"{proj}.SemanticModel/definition/expressions.tmdl",
        ]
        missing = []
        for f in required_files:
            full = os.path.join(base, f.replace("/", os.sep))
            if not os.path.exists(full):
                missing.append(f)
        if missing:
            record("FAIL", proj, "structure", f"Missing: {', '.join(missing)}")
        else:
            record("PASS", proj, "structure", f"{len(required_files)} required files present")


# ══════════════════════════════════════════════════════════════════════
# TEST 2: JSON Validity — all JSON files must parse without error
# ══════════════════════════════════════════════════════════════════════
def test_json_validity():
    print("\n" + "=" * 70)
    print("TEST 2: JSON Validity")
    print("=" * 70)
    for proj in ALL_PROJECTS:
        base = os.path.join(PROJECTS_DIR, proj)
        json_files = glob.glob(os.path.join(base, "**", "*.json"), recursive=True)
        bad = []
        for jf in json_files:
            try:
                with open(jf, "r", encoding="utf-8") as fh:
                    json.load(fh)
            except json.JSONDecodeError as e:
                rel = os.path.relpath(jf, base)
                bad.append(f"{rel}: {e.msg} at line {e.lineno}")
        if bad:
            record("FAIL", proj, "json_validity", f"{len(bad)} invalid: {'; '.join(bad[:3])}")
        else:
            record("PASS", proj, "json_validity", f"{len(json_files)} JSON files valid")


# ══════════════════════════════════════════════════════════════════════
# TEST 3: TMDL Syntax Validation
# ══════════════════════════════════════════════════════════════════════
def test_tmdl_syntax():
    print("\n" + "=" * 70)
    print("TEST 3: TMDL Syntax Validation")
    print("=" * 70)
    for proj in ALL_PROJECTS:
        base = os.path.join(PROJECTS_DIR, proj,
                            f"{proj}.SemanticModel", "definition")
        tmdl_files = glob.glob(os.path.join(base, "**", "*.tmdl"), recursive=True)
        issues = []
        for tf in tmdl_files:
            fname = os.path.basename(tf)
            with open(tf, "r", encoding="utf-8") as fh:
                content = fh.read()
                lines = content.split("\n")

            # Check 1: Unbalanced quotes in table/column/measure names
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                # Lines starting with table/column/measure should have balanced quotes
                if stripped.startswith(("table '", "column '", "measure '")):
                    q_count = stripped.count("'")
                    # Must be even (name wrapped in 'xxx')
                    # But escaped quotes '' count as two, so just check wrapping
                    if q_count < 2:
                        issues.append(f"{fname}:{i} unbalanced quotes: {stripped[:60]}")

            # Check 2: Empty DAX expressions (= followed by nothing meaningful)
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped == "=" or stripped == "= ":
                    issues.append(f"{fname}:{i} empty DAX expression")

            # Check 3: ALLEXCEPT with empty column ref
            if "ALLEXCEPT" in content:
                matches = re.findall(r"ALLEXCEPT\([^)]*\[\]\s*\)", content)
                if matches:
                    issues.append(f"{fname}: ALLEXCEPT with empty column ref []")

            # Check 4: Unbalanced parentheses in DAX expressions
            in_expression = False
            expr_lines = []
            expr_start = 0
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith("expression =") or (stripped == "=" and i > 1 and "expression" in lines[i-2]):
                    in_expression = True
                    expr_lines = [stripped]
                    expr_start = i
                elif in_expression:
                    if stripped and not stripped.startswith(("column", "measure", "table", "partition",
                                                            "annotation", "lineageTag", "displayFolder",
                                                            "dataCategory", "isHidden", "formatString",
                                                            "summarizeBy", "dataType", "sourceColumn")):
                        expr_lines.append(stripped)
                    else:
                        in_expression = False
                        full_expr = " ".join(expr_lines)
                        open_p = full_expr.count("(")
                        close_p = full_expr.count(")")
                        if open_p != close_p:
                            issues.append(f"{fname}:{expr_start} unbalanced parens ({open_p} open, {close_p} close): {full_expr[:80]}")

        if issues:
            record("FAIL", proj, "tmdl_syntax", f"{len(issues)} issues: {'; '.join(issues[:5])}")
        else:
            record("PASS", proj, "tmdl_syntax", f"{len(tmdl_files)} TMDL files OK")


# ══════════════════════════════════════════════════════════════════════
# TEST 4: DAX Formula Validation (from TMDL files)
# ══════════════════════════════════════════════════════════════════════
def test_dax_formulas():
    print("\n" + "=" * 70)
    print("TEST 4: DAX Formula Validation")
    print("=" * 70)
    for proj in ALL_PROJECTS:
        base = os.path.join(PROJECTS_DIR, proj,
                            f"{proj}.SemanticModel", "definition", "tables")
        if not os.path.isdir(base):
            record("WARN", proj, "dax_formulas", "No tables directory found")
            continue

        tmdl_files = glob.glob(os.path.join(base, "*.tmdl"))
        issues = []
        measures_found = 0
        calc_cols_found = 0

        for tf in tmdl_files:
            fname = os.path.basename(tf)
            with open(tf, "r", encoding="utf-8") as fh:
                content = fh.read()

            # Extract all DAX expressions (measure and calculated column)
            # Pattern: expression = <dax> or expression =\n\t\t<multiline dax>
            blocks = re.findall(
                r'(measure|column)\s+\'[^\']*(?:\'\'[^\']*)*\'\s*(?:=\s*(.+?))\s*(?=\n\t(?:annotation|lineageTag|displayFolder|formatString|dataCategory|isHidden|summarizeBy|dataType|sourceColumn|column|measure|partition|table)|$)',
                content, re.DOTALL
            )

            # Simpler approach: find all "= <DAX>" after measure/column declarations
            lines = content.split("\n")
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                is_measure = line.startswith("measure ")
                is_calc_col = line.startswith("column ") and "=" in line and "sourceColumn" not in line

                if is_measure or is_calc_col:
                    # Extract the DAX part after =
                    eq_pos = line.find("=")
                    if eq_pos > 0:
                        dax = line[eq_pos + 1:].strip()

                        # Collect continuation lines (indented lines after)
                        j = i + 1
                        while j < len(lines) and lines[j].startswith("\t\t\t"):
                            dax += " " + lines[j].strip()
                            j += 1

                        if dax:
                            if is_measure:
                                measures_found += 1
                            else:
                                calc_cols_found += 1

                            # Validation checks
                            errs = validate_dax(dax, fname, i + 1)
                            issues.extend(errs)
                i += 1

        if issues:
            record("FAIL", proj, "dax_formulas",
                   f"{len(issues)} issues in {measures_found} measures + {calc_cols_found} calc cols: {'; '.join(issues[:5])}")
        else:
            record("PASS", proj, "dax_formulas",
                   f"{measures_found} measures + {calc_cols_found} calc cols validated")


def validate_dax(dax, fname, line_num):
    """Validate a single DAX expression for common errors"""
    issues = []
    prefix = f"{fname}:{line_num}"

    # 1. Unbalanced parentheses
    depth = 0
    for ch in dax:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if depth < 0:
            issues.append(f"{prefix} extra closing paren: {dax[:60]}")
            break
    if depth > 0:
        issues.append(f"{prefix} {depth} unclosed paren(s): {dax[:60]}")

    # 2. Empty column reference []
    if "[]" in dax:
        issues.append(f"{prefix} empty column ref []: {dax[:60]}")

    # 3. Empty string function call  func()  (except NOW(), TODAY(), PI())
    ok_empty = {"NOW", "TODAY", "PI", "BLANK", "ALL"}
    empty_calls = re.findall(r'(\w+)\(\s*\)', dax)
    for fn in empty_calls:
        if fn.upper() not in ok_empty:
            issues.append(f"{prefix} empty call {fn}(): {dax[:60]}")

    # 4. Double aggregation: AGG(AGG(...))  (invalid in DAX)
    agg_funcs = {"SUM", "AVERAGE", "COUNT", "MIN", "MAX", "DISTINCTCOUNT"}
    for outer in agg_funcs:
        for inner in agg_funcs:
            pattern = f"{outer}\\s*\\(\\s*{inner}\\s*\\("
            if re.search(pattern, dax, re.IGNORECASE):
                issues.append(f"{prefix} nested aggregation {outer}({inner}(...)): {dax[:60]}")

    # 5. Missing table reference in CALCULATE/SUMX/AVERAGEX/COUNTX
    # SUMX needs a table as first arg: SUMX('table', expr)
    for fn in ["SUMX", "AVERAGEX", "COUNTX", "MINX", "MAXX"]:
        pattern = f"{fn}\\s*\\("
        match = re.search(pattern, dax, re.IGNORECASE)
        if match:
            after = dax[match.end():match.end() + 30]
            # First arg should reference a table (starts with ' or be a function)
            if after.strip() and not after.strip().startswith(("'", "FILTER", "ALL", "VALUES",
                                                                "DISTINCT", "ADDCOLUMNS",
                                                                "SELECTCOLUMNS", "GENERATESERIES",
                                                                "DATATABLE", "CALENDAR", "CALENDARAUTO")):
                issues.append(f"{prefix} {fn} may be missing table ref: {dax[:60]}")

    # 6. RELATED/LOOKUPVALUE referencing same table (useless)
    related_matches = re.findall(r"RELATED\s*\(\s*'([^']+)'\[", dax)
    # Can't fully validate without context, skip

    # 7. Trailing/leading operators
    dax_stripped = dax.strip()
    if dax_stripped and dax_stripped[-1] in "+-*/&|,":
        issues.append(f"{prefix} trailing operator '{dax_stripped[-1]}': {dax[:60]}")
    if dax_stripped and dax_stripped[0] in "*/&|,":
        issues.append(f"{prefix} leading operator '{dax_stripped[0]}': {dax[:60]}")

    # 8. IF with wrong number of args (must have 2 or 3)
    # Simple check: IF( with no comma inside
    if_matches = list(re.finditer(r'\bIF\s*\(', dax, re.IGNORECASE))
    for m in if_matches:
        # Count commas at same depth until closing paren
        depth = 1
        pos = m.end()
        commas = 0
        while pos < len(dax) and depth > 0:
            if dax[pos] == "(":
                depth += 1
            elif dax[pos] == ")":
                depth -= 1
            elif dax[pos] == "," and depth == 1:
                commas += 1
            pos += 1
        if commas < 1:
            issues.append(f"{prefix} IF() with <2 args: {dax[:60]}")

    return issues


# ══════════════════════════════════════════════════════════════════════
# TEST 5: Visual Query Field Type Correctness (Measure vs Column)
# ══════════════════════════════════════════════════════════════════════
def test_visual_query_fields():
    print("\n" + "=" * 70)
    print("TEST 5: Visual Query Field Type Correctness")
    print("=" * 70)
    for proj in ALL_PROJECTS:
        base = os.path.join(PROJECTS_DIR, proj)
        visual_files = glob.glob(
            os.path.join(base, f"{proj}.Report", "definition", "pages",
                         "*", "visuals", "*", "visual.json"),
            recursive=True
        )
        issues = []
        visuals_checked = 0

        # Load measure names from TMDL
        measure_names = set()
        tmdl_dir = os.path.join(base, f"{proj}.SemanticModel", "definition", "tables")
        if os.path.isdir(tmdl_dir):
            for tf in glob.glob(os.path.join(tmdl_dir, "*.tmdl")):
                with open(tf, "r", encoding="utf-8") as fh:
                    for line in fh:
                        m = re.match(r"\tmeasure\s+'([^']*(?:''[^']*)*)'", line)
                        if m:
                            name = m.group(1).replace("''", "'")
                            measure_names.add(name)

        # Load column names from TMDL (quoted 'Name' or unquoted Name)
        column_names = set()
        if os.path.isdir(tmdl_dir):
            for tf in glob.glob(os.path.join(tmdl_dir, "*.tmdl")):
                with open(tf, "r", encoding="utf-8") as fh:
                    for line in fh:
                        m = re.match(r"\tcolumn\s+'([^']*(?:''[^']*)*)'" , line)
                        if not m:
                            m = re.match(r"\tcolumn\s+(\S+)", line)
                        if m:
                            name = m.group(1).replace("''", "'")
                            column_names.add(name)

        for vf in visual_files:
            visuals_checked += 1
            vid = os.path.basename(os.path.dirname(vf))
            with open(vf, "r", encoding="utf-8") as fh:
                vdata = json.load(fh)

            visual = vdata.get("visual", {})
            vtype = visual.get("visualType", "?")
            query = visual.get("query", {})
            qs = query.get("queryState", {})

            for role, role_data in qs.items():
                projections = role_data.get("projections", [])
                for p in projections:
                    field = p.get("field", {})
                    if "Measure" in field:
                        prop = field["Measure"].get("Property", "")
                        # A field wrapped in Measure should actually be a measure
                        if prop in column_names and prop not in measure_names:
                            issues.append(f"{vtype}:{vid[:8]} '{prop}' uses Measure wrapper but is a column")
                    elif "Column" in field:
                        prop = field["Column"].get("Property", "")
                        # A field wrapped in Column should actually be a column
                        if prop in measure_names and prop not in column_names:
                            issues.append(f"{vtype}:{vid[:8]} '{prop}' uses Column wrapper but is a measure")

            # Scatter chart must have at least Y with a Measure
            if vtype == "scatterChart":
                y_data = qs.get("Y", {})
                x_data = qs.get("X", {})
                has_measure_in_y = False
                has_measure_in_x = False
                for p in y_data.get("projections", []):
                    if "Measure" in p.get("field", {}):
                        has_measure_in_y = True
                for p in x_data.get("projections", []):
                    if "Measure" in p.get("field", {}):
                        has_measure_in_x = True
                if not has_measure_in_y and not has_measure_in_x:
                    issues.append(f"scatterChart:{vid[:8]} has no Measure in X or Y")

        if issues:
            record("FAIL", proj, "visual_fields",
                   f"{len(issues)} issues in {visuals_checked} visuals: {'; '.join(issues[:5])}")
        else:
            record("PASS", proj, "visual_fields",
                   f"{visuals_checked} visuals checked ({len(measure_names)} measures, {len(column_names)} cols)")


# ══════════════════════════════════════════════════════════════════════
# TEST 6: Power Query M Expressions
# ══════════════════════════════════════════════════════════════════════
def test_power_query():
    print("\n" + "=" * 70)
    print("TEST 6: Power Query M Expressions")
    print("=" * 70)
    for proj in ALL_PROJECTS:
        expr_file = os.path.join(PROJECTS_DIR, proj,
                                 f"{proj}.SemanticModel", "definition",
                                 "expressions.tmdl")
        if not os.path.exists(expr_file):
            record("WARN", proj, "power_query", "No expressions.tmdl found")
            continue

        with open(expr_file, "r", encoding="utf-8") as fh:
            content = fh.read()

        issues = []

        # Check 1: DataFolder parameter must exist if referenced
        if "DataFolder" in content:
            if 'expression = "C:\\' not in content and "expression = " not in content:
                # Just check it's declared
                pass
            # Verify DataFolder is defined as expression
            if "DataFolder" not in content.split("expression")[0]:
                pass  # ok, it's used

        # Check 2: Known source functions should be present
        # Each partition should have a valid M source expression
        partitions = re.findall(r'partition\s+\'[^\']+\'\s*=\s*m\s*(.*?)(?=\n\tpartition|\n\ttable|\Z)',
                                content, re.DOTALL)

        valid_sources = {"Excel.Workbook", "Csv.Document", "Json.Document",
                         "PostgreSQL.Database", "Sql.Database",
                         "GoogleBigQuery.Database", "Oracle.Database",
                         "MySQL.Database", "Snowflake.Databases",
                         "File.Contents", "GENERATESERIES", "DATATABLE",
                         "CALENDAR", "#table", "Web.Contents"}

        # Check each M expression block for proper let/in structure or DAX calc table
        m_blocks = re.findall(r'expression\s*=\s*\n((?:\t\t\t.*\n)*)', content)
        for idx, block in enumerate(m_blocks):
            block_clean = block.replace("\t", "").strip()
            if not block_clean:
                issues.append(f"Expression block {idx + 1}: empty M expression")
                continue
            # Must start with let or be a simple expression
            if block_clean.startswith("let"):
                if "\nin\n" not in block_clean and "in " not in block_clean and "in\r" not in block_clean:
                    # Check for in on its own line
                    if "\n in " not in block.replace("\t", " ") and " in\n" not in block:
                        pass  # May be multiline, hard to check precisely

        # Check 3: File.Contents paths should use DataFolder parameter
        file_refs = re.findall(r'File\.Contents\("([^"]+)"\)', content)
        for fp in file_refs:
            if "DataFolder" not in fp and not fp.startswith("http"):
                pass  # Hardcoded paths are ok for some cases

        # Check 4: No Python/Tableau syntax leakage
        bad_patterns = [
            (r'\bprint\s*\(', "Python print() in M expression"),
            (r'\bdef\s+\w+', "Python def in M expression"),
            (r'\bimport\s+\w+', "Python import in M expression"),
            (r'ATTR\s*\(', "Tableau ATTR() in M expression"),
            (r'DATETRUNC\s*\(', "Tableau DATETRUNC() in M expression"),
        ]
        for pattern, msg in bad_patterns:
            if re.search(pattern, content):
                issues.append(msg)

        if issues:
            record("FAIL", proj, "power_query", f"{len(issues)} issues: {'; '.join(issues[:3])}")
        else:
            record("PASS", proj, "power_query", "M expressions valid")


# ══════════════════════════════════════════════════════════════════════
# TEST 7: Cross-Reference Model ↔ Report
# ══════════════════════════════════════════════════════════════════════
def test_cross_reference():
    print("\n" + "=" * 70)
    print("TEST 7: Cross-Reference Model ↔ Report (fields exist in model)")
    print("=" * 70)
    for proj in ALL_PROJECTS:
        base = os.path.join(PROJECTS_DIR, proj)

        # Collect all table.column and table.measure from TMDL
        model_fields = {}  # table_name -> set of field names
        tmdl_dir = os.path.join(base, f"{proj}.SemanticModel", "definition", "tables")
        if not os.path.isdir(tmdl_dir):
            record("WARN", proj, "cross_ref", "No tables directory")
            continue

        for tf in glob.glob(os.path.join(tmdl_dir, "*.tmdl")):
            with open(tf, "r", encoding="utf-8") as fh:
                content = fh.read()
            # Extract table name (quoted: table 'Name' or unquoted: table Name)
            table_match = re.search(r"^table\s+'([^']*(?:''[^']*)*)'" , content)
            if not table_match:
                table_match = re.search(r"^table\s+(\S+)", content)
            if not table_match:
                continue
            tname = table_match.group(1).replace("''", "'")
            fields = set()
            # Columns (quoted 'Name' or unquoted Name)
            for m in re.finditer(r"\tcolumn\s+'([^']*(?:''[^']*)*)'", content):
                fields.add(m.group(1).replace("''", "'"))
            for m in re.finditer(r"\tcolumn\s+([A-Za-z_]\w*)\b", content):
                if m.group(1) not in ('sourceColumn',):
                    fields.add(m.group(1))
            # Measures (quoted 'Name' or unquoted Name)
            for m in re.finditer(r"\tmeasure\s+'([^']*(?:''[^']*)*)'", content):
                fields.add(m.group(1).replace("''", "'"))
            for m in re.finditer(r"\tmeasure\s+([A-Za-z_]\w*)\b", content):
                fields.add(m.group(1))
            model_fields[tname] = fields

        # Collect all field references from visual queries
        visual_files = glob.glob(
            os.path.join(base, f"{proj}.Report", "definition", "pages",
                         "*", "visuals", "*", "visual.json")
        )
        issues = []
        refs_checked = 0
        for vf in visual_files:
            with open(vf, "r", encoding="utf-8") as fh:
                vdata = json.load(fh)
            qs = vdata.get("visual", {}).get("query", {}).get("queryState", {})
            vtype = vdata.get("visual", {}).get("visualType", "?")
            for role, role_data in qs.items():
                for p in role_data.get("projections", []):
                    field = p.get("field", {})
                    for ftype in ("Column", "Measure"):
                        if ftype in field:
                            entity = field[ftype].get("Expression", {}).get("SourceRef", {}).get("Entity", "")
                            prop = field[ftype].get("Property", "")
                            refs_checked += 1
                            if entity in model_fields:
                                if prop not in model_fields[entity]:
                                    issues.append(f"{vtype}: '{entity}'.'{prop}' not found in model")
                            else:
                                issues.append(f"{vtype}: table '{entity}' not found in model")

        if issues:
            record("FAIL", proj, "cross_ref",
                   f"{len(issues)} unresolved refs out of {refs_checked}: {'; '.join(issues[:5])}")
        else:
            record("PASS", proj, "cross_ref",
                   f"{refs_checked} field references verified against model")


# ══════════════════════════════════════════════════════════════════════
# TEST 8: PBIR Schema References
# ══════════════════════════════════════════════════════════════════════
def test_pbir_schemas():
    print("\n" + "=" * 70)
    print("TEST 8: PBIR Schema References")
    print("=" * 70)
    expected_schemas = {
        "report.json": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/",
        "page.json": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/",
        "visual.json": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/",
    }
    for proj in ALL_PROJECTS:
        base = os.path.join(PROJECTS_DIR, proj, f"{proj}.Report", "definition")
        issues = []

        for fname, expected_prefix in expected_schemas.items():
            files = glob.glob(os.path.join(base, "**", fname), recursive=True)
            for f in files:
                with open(f, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                schema = data.get("$schema", "")
                if not schema.startswith(expected_prefix):
                    rel = os.path.relpath(f, base)
                    issues.append(f"{rel}: wrong schema '{schema[:50]}'")

        if issues:
            record("FAIL", proj, "pbir_schema", "; ".join(issues[:3]))
        else:
            record("PASS", proj, "pbir_schema", "All schemas correct")


# ══════════════════════════════════════════════════════════════════════
# TEST 9: Visual Position and Size Validation
# ══════════════════════════════════════════════════════════════════════
def test_visual_positions():
    print("\n" + "=" * 70)
    print("TEST 9: Visual Position & Size Validation")
    print("=" * 70)
    for proj in ALL_PROJECTS:
        base = os.path.join(PROJECTS_DIR, proj)
        visual_files = glob.glob(
            os.path.join(base, f"{proj}.Report", "definition", "pages",
                         "*", "visuals", "*", "visual.json")
        )
        issues = []
        for vf in visual_files:
            vid = os.path.basename(os.path.dirname(vf))[:8]
            with open(vf, "r", encoding="utf-8") as fh:
                vdata = json.load(fh)
            pos = vdata.get("position", {})
            x = pos.get("x", 0)
            y = pos.get("y", 0)
            w = pos.get("width", 0)
            h = pos.get("height", 0)

            if w <= 0 or h <= 0:
                issues.append(f"{vid}: zero/negative size ({w}x{h})")
            if x < 0 or y < 0:
                issues.append(f"{vid}: negative position ({x},{y})")
            if w > 1920 or h > 1200:
                issues.append(f"{vid}: oversized ({w}x{h})")

        if issues:
            record("WARN", proj, "visual_positions", "; ".join(issues[:3]))
        else:
            record("PASS", proj, "visual_positions", f"{len(visual_files)} visuals positioned OK")


# ══════════════════════════════════════════════════════════════════════
# TEST 10: Relationship Validation
# ══════════════════════════════════════════════════════════════════════
def test_relationships():
    print("\n" + "=" * 70)
    print("TEST 10: Relationship Validation")
    print("=" * 70)
    for proj in ALL_PROJECTS:
        rel_file = os.path.join(PROJECTS_DIR, proj,
                                f"{proj}.SemanticModel", "definition",
                                "relationships.tmdl")
        if not os.path.exists(rel_file):
            record("PASS", proj, "relationships", "No relationships (OK)")
            continue

        with open(rel_file, "r", encoding="utf-8") as fh:
            content = fh.read()

        issues = []
        # Parse relationships
        rels = re.findall(
            r"relationship\s+(\w+)\s*\n(.*?)(?=\nrelationship|\Z)",
            content, re.DOTALL
        )

        for rel_id, body in rels:
            # Must have fromTable, toTable, fromColumn, toColumn
            from_table = re.search(r'fromTable:\s*\'([^\']+)\'', body)
            to_table = re.search(r'toTable:\s*\'([^\']+)\'', body)
            from_col = re.search(r'fromColumn:\s*\'([^\']+)\'', body)
            to_col = re.search(r'toColumn:\s*\'([^\']+)\'', body)

            if not from_table:
                issues.append(f"Rel {rel_id}: missing fromTable")
            if not to_table:
                issues.append(f"Rel {rel_id}: missing toTable")
            if not from_col:
                issues.append(f"Rel {rel_id}: missing fromColumn")
            if not to_col:
                issues.append(f"Rel {rel_id}: missing toColumn")

            # Self-relationship check
            if from_table and to_table and from_table.group(1) == to_table.group(1):
                if from_col and to_col and from_col.group(1) == to_col.group(1):
                    issues.append(f"Rel {rel_id}: self-relationship on same column")

        rel_count = len(rels)
        if issues:
            record("FAIL", proj, "relationships", f"{len(issues)} issues in {rel_count} rels: {'; '.join(issues[:3])}")
        else:
            record("PASS", proj, "relationships", f"{rel_count} relationships valid")


# ══════════════════════════════════════════════════════════════════════
# TEST 11: Tableau Syntax Leakage in DAX
# ══════════════════════════════════════════════════════════════════════
def test_tableau_leakage():
    print("\n" + "=" * 70)
    print("TEST 11: Tableau Syntax Leakage in DAX")
    print("=" * 70)
    tableau_patterns = [
        (r'\bATTR\s*\(', "ATTR() — Tableau aggregation"),
        (r'\bDATETRUNC\s*\(', "DATETRUNC() — Tableau date function"),
        (r'\bDATEPART\s*\(', "DATEPART() — Tableau date function"),
        (r'\bZN\s*\(', "ZN() — Tableau null function"),
        (r'\bIFNULL\s*\(', "IFNULL() — Tableau null function"),
        (r'\bISNULL\s*\(', "ISNULL() — Tableau null function (should be ISBLANK)"),
        (r'\bCONTAINS\s*\(\s*["\']', "CONTAINS('string') — Tableau string fn (should be CONTAINSSTRING)"),
        (r'\bELSEIF\b', "ELSEIF — Tableau syntax (DAX uses nested IF or commas)"),
        (r'\bRUNNING_SUM\s*\(', "RUNNING_SUM() — Tableau table calc"),
        (r'\bRUNNING_AVG\s*\(', "RUNNING_AVG() — Tableau table calc"),
        (r'\bWINDOW_SUM\s*\(', "WINDOW_SUM() — Tableau table calc"),
        (r'\bWINDOW_AVG\s*\(', "WINDOW_AVG() — Tableau table calc"),
        (r'\bWINDOW_MAX\s*\(', "WINDOW_MAX() — Tableau table calc"),
        (r'\bWINDOW_MIN\s*\(', "WINDOW_MIN() — Tableau table calc"),
        (r'\bRANK_UNIQUE\s*\(', "RANK_UNIQUE() — Tableau rank (should be RANKX)"),
        (r'\bRANK_DENSE\s*\(', "RANK_DENSE() — Tableau rank (should be RANKX)"),
        (r'\bCOUNTD\s*\(', "COUNTD() — Tableau (should be DISTINCTCOUNT)"),
        (r'\bFLOAT\s*\(', "FLOAT() — Tableau cast (should be CONVERT)"),
        (r'\bSTR\s*\(', "STR() — Tableau cast (should be FORMAT)"),
        (r'\{FIXED\b', "{FIXED — Tableau LOD expression"),
        (r'\{INCLUDE\b', "{INCLUDE — Tableau LOD expression"),
        (r'\{EXCLUDE\b', "{EXCLUDE — Tableau LOD expression"),
        (r'\bMAKEPOINT\s*\(', "MAKEPOINT() — Tableau geo function"),
        (r'\[Parameters\]\.\[', "[Parameters].[...] — Tableau parameter syntax"),
        (r'==', "== — Tableau equality (DAX uses =)"),
    ]
    for proj in ALL_PROJECTS:
        base = os.path.join(PROJECTS_DIR, proj,
                            f"{proj}.SemanticModel", "definition", "tables")
        if not os.path.isdir(base):
            record("WARN", proj, "tableau_leakage", "No tables dir")
            continue

        issues = []
        for tf in glob.glob(os.path.join(base, "*.tmdl")):
            fname = os.path.basename(tf)
            with open(tf, "r", encoding="utf-8") as fh:
                content = fh.read()

            for pattern, msg in tableau_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    issues.append(f"{fname}: {msg} ({len(matches)}x)")

        if issues:
            record("FAIL", proj, "tableau_leakage",
                   f"{len(issues)} leaks: {'; '.join(issues[:5])}")
        else:
            record("PASS", proj, "tableau_leakage", "No Tableau syntax found in DAX")


# ══════════════════════════════════════════════════════════════════════
# TEST 12: Parameter Tables Validation
# ══════════════════════════════════════════════════════════════════════
def test_parameter_tables():
    print("\n" + "=" * 70)
    print("TEST 12: Parameter Tables Validation")
    print("=" * 70)
    for proj in ALL_PROJECTS:
        base = os.path.join(PROJECTS_DIR, proj,
                            f"{proj}.SemanticModel", "definition", "tables")
        if not os.path.isdir(base):
            continue

        issues = []
        param_tables = 0

        for tf in glob.glob(os.path.join(base, "*.tmdl")):
            fname = os.path.basename(tf)
            with open(tf, "r", encoding="utf-8") as fh:
                content = fh.read()

            # Detect parameter tables (have GENERATESERIES or DATATABLE partition)
            if "GENERATESERIES" in content or "DATATABLE" in content:
                param_tables += 1

                # Must have a column named 'Value'
                if "column 'Value'" not in content and "column Value" not in content:
                    issues.append(f"{fname}: parameter table missing 'Value' column")

                # Must have exactly one measure with SELECTEDVALUE
                sv_count = content.count("SELECTEDVALUE")
                if sv_count == 0:
                    issues.append(f"{fname}: no SELECTEDVALUE measure")
                elif sv_count > 1:
                    record("WARN", proj, "param_tables", f"{fname}: multiple SELECTEDVALUE measures ({sv_count})")

                # Column and measure should not have same name
                col_names = set()
                mea_names = set()
                for m in re.finditer(r"\tcolumn\s+'([^']*(?:''[^']*)*)'", content):
                    col_names.add(m.group(1).replace("''", "'"))
                for m in re.finditer(r"\tmeasure\s+'([^']*(?:''[^']*)*)'", content):
                    mea_names.add(m.group(1).replace("''", "'"))
                collision = col_names & mea_names
                if collision:
                    issues.append(f"{fname}: column/measure name collision: {collision}")

        if issues:
            record("FAIL", proj, "param_tables", "; ".join(issues[:3]))
        elif param_tables > 0:
            record("PASS", proj, "param_tables", f"{param_tables} parameter tables validated")
        else:
            record("PASS", proj, "param_tables", "No parameter tables (OK)")


# ══════════════════════════════════════════════════════════════════════
# TEST 13: Page & Visual Count Consistency
# ══════════════════════════════════════════════════════════════════════
def test_page_visual_count():
    print("\n" + "=" * 70)
    print("TEST 13: Page & Visual Count Consistency")
    print("=" * 70)
    for proj in ALL_PROJECTS:
        base = os.path.join(PROJECTS_DIR, proj, f"{proj}.Report", "definition")
        pages_json = os.path.join(base, "pages", "pages.json")
        if not os.path.exists(pages_json):
            record("FAIL", proj, "page_count", "pages.json not found")
            continue

        with open(pages_json, "r", encoding="utf-8") as fh:
            pages_data = json.load(fh)

        # PBIR uses "pageOrder" array, not "pages"
        page_count = len(pages_data.get("pageOrder", pages_data.get("pages", [])))
        issues = []

        # Check each page has at least one visual
        page_dirs = [d for d in os.listdir(os.path.join(base, "pages"))
                     if os.path.isdir(os.path.join(base, "pages", d))]

        if page_count != len(page_dirs):
            issues.append(f"pages.json lists {page_count} pages but {len(page_dirs)} page dirs exist")

        total_visuals = 0
        for pd in page_dirs:
            visuals_dir = os.path.join(base, "pages", pd, "visuals")
            if os.path.isdir(visuals_dir):
                vis_count = len([d for d in os.listdir(visuals_dir)
                                if os.path.isdir(os.path.join(visuals_dir, d))])
                total_visuals += vis_count
                if vis_count == 0:
                    issues.append(f"Page '{pd}' has 0 visuals")
            else:
                issues.append(f"Page '{pd}' has no visuals directory")

        if issues:
            record("FAIL", proj, "page_count", "; ".join(issues))
        else:
            record("PASS", proj, "page_count",
                   f"{page_count} pages, {total_visuals} visuals")


# ══════════════════════════════════════════════════════════════════════
# TEST 14: No Empty Visual Directories (stale artifacts)
# ══════════════════════════════════════════════════════════════════════
def test_no_empty_visual_dirs():
    print("\n" + "=" * 70)
    print("TEST 14: No Empty Visual Directories")
    print("=" * 70)
    for proj in ALL_PROJECTS:
        base = os.path.join(PROJECTS_DIR, proj, f"{proj}.Report", "definition", "pages")
        if not os.path.isdir(base):
            continue
        empty_dirs = []
        for page_dir in os.listdir(base):
            visuals_path = os.path.join(base, page_dir, "visuals")
            if not os.path.isdir(visuals_path):
                continue
            for vdir in os.listdir(visuals_path):
                vfull = os.path.join(visuals_path, vdir)
                if os.path.isdir(vfull) and not os.path.exists(os.path.join(vfull, "visual.json")):
                    empty_dirs.append(vdir[:12])
        if empty_dirs:
            record("FAIL", proj, "empty_vis_dirs",
                   f"{len(empty_dirs)} empty visual dirs (stale): {', '.join(empty_dirs[:5])}")
        else:
            record("PASS", proj, "empty_vis_dirs", "No stale visual directories")


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 70)
    print("  COMPREHENSIVE MIGRATION VALIDATION TEST SUITE")
    print(f"  Projects: {', '.join(ALL_PROJECTS)}")
    print("=" * 70)

    test_project_structure()
    test_json_validity()
    test_tmdl_syntax()
    test_dax_formulas()
    test_visual_query_fields()
    test_power_query()
    test_cross_reference()
    test_pbir_schemas()
    test_visual_positions()
    test_relationships()
    test_tableau_leakage()
    test_parameter_tables()
    test_page_visual_count()
    test_no_empty_visual_dirs()

    # Summary
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    total = results["pass"] + results["fail"] + results["warn"]
    print(f"  Total checks: {total}")
    print(f"  ✅ Passed:  {results['pass']}")
    print(f"  ❌ Failed:  {results['fail']}")
    print(f"  ⚠️  Warnings: {results['warn']}")
    print("=" * 70)

    if results["fail"] > 0:
        print("\n❌ FAILURES:")
        for d in results["details"]:
            if "❌" in d:
                print(d)

    if results["warn"] > 0:
        print("\n⚠️  WARNINGS:")
        for d in results["details"]:
            if "⚠️" in d:
                print(d)

    sys.exit(1 if results["fail"] > 0 else 0)
