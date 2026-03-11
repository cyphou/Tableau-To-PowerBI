"""
Artifact validator for generated Power BI projects.

Validates generated PBIR report files and TMDL semantic model files
against required schemas and structure rules before opening in
Power BI Desktop.  Includes semantic DAX validation (paren matching,
Tableau function leakage, unresolved references).

Usage:
    from validator import ArtifactValidator
    results = ArtifactValidator.validate_directory(Path('artifacts/powerbi_projects/MyReport'))
"""

import os
import json
import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ArtifactValidator:
    """Validate generated Power BI project (.pbip) artifacts."""

    # Required files in a valid .pbip project
    REQUIRED_PROJECT_FILES = [
        '{name}.pbip',
    ]

    # Required directories
    REQUIRED_DIRS = [
        '{name}.Report',
        '{name}.SemanticModel',
    ]

    # Required PBIR report files
    REQUIRED_REPORT_FILES = [
        'definition.pbir',
        'report.json',
    ]

    # Required TMDL files
    REQUIRED_TMDL_FILES = [
        'model.tmdl',
    ]

    # Valid PBIR schemas
    VALID_REPORT_SCHEMAS = [
        'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.1.0/schema.json',
    ]

    VALID_PAGE_SCHEMAS = [
        'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.0.0/schema.json',
    ]

    VALID_VISUAL_SCHEMAS = [
        'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.5.0/schema.json',
    ]

    # ── PBIR structural schemas (lightweight, no external dependency) ──
    # These define required/optional keys and allowed types for each schema,
    # validated by ``validate_pbir_structure``.

    PBIR_REPORT_REQUIRED_KEYS = {'$schema'}
    PBIR_REPORT_OPTIONAL_KEYS = {
        'datasetReference', 'reportId', 'theme', 'themeUri',
        'resourcePackages', 'objects', 'filters', 'bookmarks',
        'config', 'layoutOptimization', 'podBookmarks',
        'publicCustomVisuals', 'registeredResources',
    }

    PBIR_PAGE_REQUIRED_KEYS = {'$schema', 'name', 'displayName'}
    PBIR_PAGE_OPTIONAL_KEYS = {
        'displayOption', 'width', 'height', 'visualContainers',
        'filters', 'ordinal', 'pageType', 'background', 'wallpaper',
        'config', 'objects', 'tabOrder',
    }

    PBIR_VISUAL_REQUIRED_KEYS = {'$schema'}
    PBIR_VISUAL_OPTIONAL_KEYS = {
        'name', 'position', 'visual', 'filters', 'query',
        'dataTransforms', 'objects', 'howCreated', 'isHidden',
        'tabOrder', 'parentGroupName', 'drillFilterOtherVisuals',
        'config', 'title', 'singleVisual', 'singleVisualGroup',
    }

    @classmethod
    def validate_pbir_structure(cls, json_data, schema_url):
        """Validate a JSON object against a PBIR structural schema.

        This is a lightweight validator that checks required/optional keys
        and ``$schema`` values without requiring an external JSON-Schema
        library.

        Args:
            json_data: Parsed JSON dict.
            schema_url: The ``$schema`` URL from the JSON file.

        Returns:
            list of error strings (empty = valid).
        """
        errors = []
        if not isinstance(json_data, dict):
            errors.append('PBIR file must be a JSON object')
            return errors

        # Determine which structural schema to apply
        if 'report/' in schema_url and 'page' not in schema_url and 'visualContainer' not in schema_url:
            required = cls.PBIR_REPORT_REQUIRED_KEYS
            allowed = required | cls.PBIR_REPORT_OPTIONAL_KEYS
            label = 'report'
        elif '/page/' in schema_url:
            required = cls.PBIR_PAGE_REQUIRED_KEYS
            allowed = required | cls.PBIR_PAGE_OPTIONAL_KEYS
            label = 'page'
        elif 'visualContainer' in schema_url:
            required = cls.PBIR_VISUAL_REQUIRED_KEYS
            allowed = required | cls.PBIR_VISUAL_OPTIONAL_KEYS
            label = 'visual'
        else:
            # Unknown schema — skip structural validation
            return errors

        # Check required keys
        for key in required:
            if key not in json_data:
                errors.append(f'Missing required key "{key}" in {label} JSON')

        # Check $schema value
        actual_schema = json_data.get('$schema', '')
        if actual_schema:
            matching_schemas = {
                'report': cls.VALID_REPORT_SCHEMAS,
                'page': cls.VALID_PAGE_SCHEMAS,
                'visual': cls.VALID_VISUAL_SCHEMAS,
            }.get(label, [])
            if matching_schemas and actual_schema not in matching_schemas:
                errors.append(
                    f'Unexpected $schema "{actual_schema}" for {label} '
                    f'(expected one of: {matching_schemas})'
                )

        return errors

    # Valid Fabric artifact types
    VALID_ARTIFACT_TYPES = {
        'Dataset',
        'Dataflow',
        'Report',
        'Notebook',
        'Lakehouse',
        'Warehouse',
        'Pipeline',
        'SemanticModel',
    }

    @staticmethod
    def validate_artifact(artifact_path):
        """
        Validate a single artifact JSON file.

        Args:
            artifact_path: Path to artifact JSON file

        Returns:
            Tuple of (is_valid, error_messages)
        """
        artifact_path = Path(artifact_path)
        errors = []

        try:
            if not artifact_path.exists():
                return False, [f'File not found: {artifact_path}']

            with open(artifact_path, 'r', encoding='utf-8') as f:
                artifact = json.load(f)

            if not isinstance(artifact, dict):
                errors.append('Artifact must be a JSON object')
                return False, errors

            # Check for $schema if present
            schema = artifact.get('$schema', '')
            if schema and 'developer.microsoft.com' in schema:
                # This is a PBIR file — validate schema
                pass  # Schema presence is enough

            # Validate type field if present
            artifact_type = artifact.get('type')
            if artifact_type and artifact_type not in ArtifactValidator.VALID_ARTIFACT_TYPES:
                errors.append(f'Invalid artifact type: {artifact_type}')

            return len(errors) == 0, errors

        except json.JSONDecodeError as e:
            return False, [f'Invalid JSON: {str(e)}']
        except Exception as e:
            return False, [f'Validation error: {str(e)}']

    @staticmethod
    def validate_json_file(filepath):
        """Validate that a file contains valid JSON.

        Args:
            filepath: Path to JSON file

        Returns:
            Tuple of (is_valid, error_message_or_None)
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                json.load(f)
            return True, None
        except json.JSONDecodeError as e:
            return False, f'Invalid JSON in {filepath}: {e}'
        except Exception as e:
            return False, f'Error reading {filepath}: {e}'

    @staticmethod
    def validate_tmdl_file(filepath):
        """Validate a TMDL file has valid structure.

        Args:
            filepath: Path to .tmdl file

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            if not content.strip():
                errors.append(f'Empty TMDL file: {filepath}')
                return False, errors

            # model.tmdl must start with "model Model"
            basename = os.path.basename(filepath)
            if basename == 'model.tmdl':
                if not content.strip().startswith('model Model'):
                    errors.append(f'model.tmdl must start with "model Model"')

            return len(errors) == 0, errors

        except Exception as e:
            return False, [f'Error reading {filepath}: {e}']

    # ── Tableau derivation field reference pattern ────────────────
    # Matches patterns like [yr:Order Date:ok], [tyr:Date:qk], [none:Ship Mode:nk]
    _RE_TABLEAU_DERIVATION_REF = re.compile(
        r'\[(?:none|sum|avg|count|min|max|usr|yr|mn|dy|qr|wk|attr|md|mdy|hms|hr|mt|sc|thr|trunc|tyr|tqr|tmn|tdy|twk):'
        r'[^\]]+?'
        r'(?::(?:nk|qk|ok|fn|tn))?\]'
    )

    # ── Semantic DAX validation ────────────────────────────────────

    # Tableau functions that should never appear in valid DAX
    _TABLEAU_FUNCTION_LEAK_PATTERNS = [
        (r'\bCOUNTD\s*\(', 'COUNTD (use DISTINCTCOUNT)'),
        (r'\bZN\s*\(', 'ZN (use IF(ISBLANK(...)))'),
        (r'\bIFNULL\s*\(', 'IFNULL (use IF(ISBLANK(...)))'),
        (r'\bATTR\s*\(', 'ATTR (use VALUES)'),
        (r'(?<![<>!])={2}(?!=)', 'Double-equals == (use single =)'),
        (r'\bELSEIF\b', 'ELSEIF (use nested IF)'),
        (r'(?<!\{)\{(?:FIXED|INCLUDE|EXCLUDE)\s', 'LOD expression {FIXED/INCLUDE/EXCLUDE}'),
        (r'\bDATETRUNC\s*\(', 'DATETRUNC (use STARTOF*)'),
        (r'\bDATEPART\s*\(', 'DATEPART (use YEAR/MONTH/DAY)'),
        (r'\bMAKEPOINT\s*\(', 'MAKEPOINT (spatial — no DAX equivalent)'),
        (r'\bSCRIPT_(?:BOOL|INT|REAL|STR)\s*\(', 'SCRIPT_* analytics extension'),
    ]

    @classmethod
    def validate_dax_formula(cls, formula, context=''):
        """
        Validate a single DAX formula for common issues.

        Checks:
        - Balanced parentheses
        - Tableau function leakage
        - Unresolved [Parameters].[X] references

        Args:
            formula: DAX formula string
            context: Optional context label (measure/column name) for error messages

        Returns:
            list of error/warning strings (empty = valid)
        """
        issues = []
        if not formula or not formula.strip():
            return issues

        ctx = f' in {context}' if context else ''

        # 1. Balanced parentheses
        depth = 0
        for ch in formula:
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth < 0:
                    issues.append(f'Unmatched closing parenthesis{ctx}')
                    break
        if depth > 0:
            issues.append(f'Unmatched opening parenthesis ({depth} unclosed){ctx}')

        # 2. Tableau function leakage
        for pattern, description in cls._TABLEAU_FUNCTION_LEAK_PATTERNS:
            if re.search(pattern, formula):
                issues.append(f'Tableau function leak: {description}{ctx}')

        # 3. Unresolved parameter references [Parameters].[X]
        if re.search(r'\[Parameters\]\s*\.\s*\[', formula):
            issues.append(f'Unresolved parameter reference [Parameters].[...]{ctx}')

        return issues

    @classmethod
    def validate_tmdl_dax(cls, filepath):
        """
        Validate all DAX formulas inside a TMDL file.

        Scans for 'expression =' and 'expression =\\n' patterns to extract
        DAX from table/measure/column definitions.

        Args:
            filepath: Path to .tmdl file

        Returns:
            list of issue strings
        """
        issues = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception:
            return issues

        basename = os.path.basename(filepath)
        current_object = basename
        lineage_tags = []  # (tag, object_context, line_number)
        sort_by_columns = []  # (sort_col, object_context, line_number)
        known_columns = set()  # Column names found in this TMDL file

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Track current object name
            for prefix in ('measure ', 'column ', 'table '):
                if stripped.startswith(prefix):
                    current_object = stripped
            # Collect column names for sortByColumn cross-validation
            col_def = cls._RE_TMDL_COL_DEF.match(stripped)
            if col_def:
                known_columns.add(col_def.group(1).strip())

            # --- Empty measure/column detection ---
            # Pattern: ``measure 'Name' = `` with no expression after ``=``
            m_measure = cls._RE_TMDL_EMPTY_MEASURE.match(line)
            if m_measure:
                issues.append(f'Empty measure expression in {current_object} ({basename}:{i+1})')

            # Pattern: ``column 'Name' = `` with no expression after ``=``
            m_col_expr = cls._RE_TMDL_EMPTY_COL_EXPR.match(line)
            if m_col_expr:
                issues.append(f'Empty column expression in {current_object} ({basename}:{i+1})')

            # --- Single-line measure DAX (``measure 'Name' = <dax>``) ---
            m_inline = cls._RE_TMDL_INLINE_MEASURE.match(line)
            if m_inline:
                formula = m_inline.group(1).strip()
                if formula and not formula.endswith('```'):
                    issues.extend(cls.validate_dax_formula(formula, current_object))
                    # Check for Tableau derivation references
                    derivation_matches = cls._RE_TABLEAU_DERIVATION_REF.findall(formula)
                    if derivation_matches:
                        issues.append(
                            f'Tableau derivation field reference {derivation_matches[0]} '
                            f'in {current_object} ({basename}:{i+1})'
                        )

            # --- lineageTag tracking ---
            lt_match = cls._RE_TMDL_LINEAGE_TAG.match(stripped)
            if lt_match:
                lineage_tags.append((lt_match.group(1), current_object, i + 1))

            # --- sortByColumn validation ---
            sbc_match = cls._RE_TMDL_SORT_BY_COL.match(stripped)
            if sbc_match:
                sort_col = sbc_match.group(1).strip().strip("'")
                sort_by_columns.append((sort_col, current_object, i + 1))

            # Single-line expression
            if stripped.startswith('expression =') and not stripped.endswith('```'):
                formula = stripped[len('expression ='):].strip()
                if not formula:
                    issues.append(f'Empty expression in {current_object} ({basename}:{i+1})')
                # Skip M expressions (Power Query)
                elif not formula.lstrip().startswith('let') and not formula.lstrip().startswith('//'):
                    issues.extend(cls.validate_dax_formula(formula, current_object))
                    # Check for Tableau derivation references in DAX
                    derivation_matches = cls._RE_TABLEAU_DERIVATION_REF.findall(formula)
                    if derivation_matches:
                        issues.append(
                            f'Tableau derivation field reference {derivation_matches[0]} '
                            f'in {current_object} ({basename}:{i+1})'
                        )

            # Multi-line expression block (``` delimited)
            if stripped.startswith('expression =') and stripped.endswith('```'):
                formula_lines = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith('```'):
                    formula_lines.append(lines[i])
                    i += 1
                formula = '\n'.join(formula_lines)
                # Check for Tableau derivation references in any expression (DAX or M)
                derivation_matches = cls._RE_TABLEAU_DERIVATION_REF.findall(formula)
                if derivation_matches:
                    issues.append(
                        f'Tableau derivation field reference {derivation_matches[0]} '
                        f'in {current_object} ({basename})'
                    )
                # Skip M expressions
                if not formula.lstrip().startswith('let') and not formula.lstrip().startswith('//'):
                    issues.extend(cls.validate_dax_formula(formula, current_object))

            i += 1

        # --- lineageTag uniqueness ---
        seen_tags = {}
        for tag, obj, lineno in lineage_tags:
            if tag in seen_tags:
                prev_obj, prev_line = seen_tags[tag]
                issues.append(
                    f'Duplicate lineageTag {tag} in {obj} (line {lineno}) '
                    f'and {prev_obj} (line {prev_line}) in {basename}'
                )
            else:
                seen_tags[tag] = (obj, lineno)

        # --- sortByColumn cross-validation ---
        for sort_col, obj, lineno in sort_by_columns:
            if known_columns and sort_col not in known_columns:
                issues.append(
                    f'sortByColumn target \'{sort_col}\' not found as a column '
                    f'in {obj} ({basename}:{lineno})'
                )

        return issues

    # ── Semantic model validation ──────────────────────────────────

    # Regex to match TMDL table definition:  ``table 'Name'`` or ``table Name``
    _RE_TABLE_DEF = re.compile(r"^table\s+'((?:[^']|'')+)'|^table\s+(\w+)(?:\s|$)")
    # Regex to match TMDL column definition:  ``column 'Name'`` or ``column Name``
    # Handles escaped apostrophes ('') inside quoted names and optional ``= expression``.
    _RE_COL_DEF = re.compile(r"^column\s+'((?:[^']|'')+)'|^column\s+(\w+)(?:\s|$)")
    # Regex to match TMDL measure definition:  ``measure 'Name'`` or ``measure Name``
    # Handles escaped apostrophes ('') inside quoted names and optional ``= expression``.
    _RE_MEASURE_DEF = re.compile(r"^measure\s+'((?:[^']|'')+)'|^measure\s+(\w+)(?:\s|$)")
    # Regex to extract DAX column/measure references: 'Table'[Column]
    # Handles escaped apostrophes ('') inside table names.
    _RE_DAX_REF = re.compile(r"'((?:[^']|'')+)'\[([^\]]+)\]")

    # Pre-compiled patterns for validate_tmdl_dax hot loop
    _RE_TMDL_COL_DEF = re.compile(r"^\s*column\s+'?([^'=]+?)'?\s*$")
    _RE_TMDL_EMPTY_MEASURE = re.compile(r"^\s*measure\s+'[^']+'\s*=\s*$")
    _RE_TMDL_EMPTY_COL_EXPR = re.compile(r"^\s*column\s+'[^']+'\s*=\s*$")
    _RE_TMDL_INLINE_MEASURE = re.compile(r"^\s*measure\s+'[^']+'\s*=\s*(.+)$")
    _RE_TMDL_LINEAGE_TAG = re.compile(r'^\s*lineageTag:\s*(\S+)')
    _RE_TMDL_SORT_BY_COL = re.compile(r'^\s*sortByColumn:\s*(.+)')

    @classmethod
    def _collect_model_symbols(cls, sm_dir):
        """Collect all table names, column names, and measure names
        from the SemanticModel TMDL files.

        Args:
            sm_dir: Path to ``{name}.SemanticModel`` directory.

        Returns:
            dict with keys ``tables`` (set of table names),
            ``columns`` (dict: table_name -> set of column names),
            ``measures`` (dict: table_name -> set of measure names).
        """
        tables = set()
        columns = {}  # table -> {col1, col2, ...}
        measures = {}  # table -> {meas1, ...}

        def _scan_tmdl(filepath):
            """Read a single TMDL file and populate tables/columns/measures."""
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            except Exception:
                return
            current_table = None
            for line in lines:
                stripped = line.strip()
                tm = cls._RE_TABLE_DEF.match(stripped)
                if tm:
                    raw = tm.group(1) if tm.group(1) is not None else tm.group(2)
                    current_table = cls._unescape_tmdl_name(raw)
                    tables.add(current_table)
                    columns.setdefault(current_table, set())
                    measures.setdefault(current_table, set())
                    continue
                if current_table:
                    cm = cls._RE_COL_DEF.match(stripped)
                    if cm:
                        raw = cm.group(1) if cm.group(1) is not None else cm.group(2)
                        columns[current_table].add(cls._unescape_tmdl_name(raw))
                        continue
                    mm = cls._RE_MEASURE_DEF.match(stripped)
                    if mm:
                        raw = mm.group(1) if mm.group(1) is not None else mm.group(2)
                        measures[current_table].add(cls._unescape_tmdl_name(raw))
                        continue

        sm_path = Path(sm_dir)
        def_dir = sm_path / 'definition'

        # model.tmdl
        model_tmdl = def_dir / 'model.tmdl'
        if model_tmdl.exists():
            _scan_tmdl(str(model_tmdl))

        # tables/*.tmdl
        tables_dir = def_dir / 'tables'
        if tables_dir.exists():
            for tmdl_f in tables_dir.glob('*.tmdl'):
                _scan_tmdl(str(tmdl_f))

        return {'tables': tables, 'columns': columns, 'measures': measures}

    @classmethod
    def validate_semantic_references(cls, sm_dir):
        """Validate that DAX column references (``'Table'[Column]``) in TMDL
        files actually exist in the model.

        Args:
            sm_dir: Path to ``{name}.SemanticModel`` directory.

        Returns:
            list of warning strings for unresolved references.
        """
        symbols = cls._collect_model_symbols(sm_dir)
        known_tables = symbols['tables']
        known_cols = symbols['columns']
        known_measures = symbols['measures']
        warnings_list = []

        sm_path = Path(sm_dir)
        def_dir = sm_path / 'definition'

        # Gather all TMDL files to scan
        tmdl_files = []
        model_tmdl = def_dir / 'model.tmdl'
        if model_tmdl.exists():
            tmdl_files.append(model_tmdl)
        tables_dir = def_dir / 'tables'
        if tables_dir.exists():
            tmdl_files.extend(tables_dir.glob('*.tmdl'))
        roles_file = def_dir / 'roles.tmdl'
        if roles_file.exists():
            tmdl_files.append(roles_file)

        for tmdl_file in tmdl_files:
            try:
                content = tmdl_file.read_text(encoding='utf-8')
            except Exception:
                continue
            basename = tmdl_file.name
            for match in cls._RE_DAX_REF.finditer(content):
                table_ref = cls._unescape_tmdl_name(match.group(1))
                col_ref = match.group(2)
                if table_ref not in known_tables:
                    warnings_list.append(
                        f'Unknown table reference \'{table_ref}\' in {basename}'
                    )
                else:
                    all_fields = known_cols.get(table_ref, set()) | known_measures.get(table_ref, set())
                    if col_ref not in all_fields:
                        warnings_list.append(
                            f'Unknown column/measure [{col_ref}] in table \'{table_ref}\' ({basename})'
                        )

        return warnings_list

    @classmethod
    def validate_project(cls, project_dir):
        """
        Validate a complete .pbip project directory.

        Args:
            project_dir: Path to the .pbip project directory

        Returns:
            Dict with 'valid' (bool), 'errors' (list), 'warnings' (list),
            'files_checked' (int)
        """
        project_dir = Path(project_dir)
        errors = []
        warnings = []
        files_checked = 0

        if not project_dir.exists():
            return {
                'valid': False,
                'errors': [f'Project directory not found: {project_dir}'],
                'warnings': [],
                'files_checked': 0,
            }

        report_name = project_dir.name

        # Check .pbip file
        pbip_file = project_dir / f'{report_name}.pbip'
        if pbip_file.exists():
            files_checked += 1
            valid, err = cls.validate_json_file(pbip_file)
            if not valid:
                errors.append(err)
        else:
            errors.append(f'Missing .pbip file: {pbip_file.name}')

        # Check Report directory
        report_dir = project_dir / f'{report_name}.Report'
        if report_dir.exists():
            # PBIR v4.0 places report.json under definition/
            definition_dir = report_dir / 'definition'

            # Validate report.json (check both legacy root and PBIR definition/ path)
            report_json = definition_dir / 'report.json' if definition_dir.exists() else None
            if report_json is None or not report_json.exists():
                report_json = report_dir / 'report.json'  # legacy fallback
            if report_json.exists():
                files_checked += 1
                valid, err = cls.validate_json_file(report_json)
                if not valid:
                    errors.append(err)
                else:
                    # PBIR structural validation on report.json
                    try:
                        with open(report_json, 'r', encoding='utf-8') as f:
                            rj = json.load(f)
                        schema_url = rj.get('$schema', '') if isinstance(rj, dict) else ''
                        if schema_url:
                            pbir_errs = cls.validate_pbir_structure(rj, schema_url)
                            warnings.extend(pbir_errs)
                    except Exception:
                        pass
            else:
                errors.append('Missing report.json in Report directory')

            # Validate definition.pbir
            pbir_file = report_dir / 'definition.pbir'
            if pbir_file.exists():
                files_checked += 1
                valid, err = cls.validate_json_file(pbir_file)
                if not valid:
                    errors.append(err)
            else:
                warnings.append('Missing definition.pbir (may be optional)')

            # Validate page and visual JSON files
            # PBIR v4.0: pages live under definition/pages/
            pages_dir = definition_dir / 'pages' if definition_dir.exists() else None
            if pages_dir is None or not pages_dir.exists():
                pages_dir = report_dir / 'pages'  # legacy fallback
            if pages_dir.exists():
                for page_dir in pages_dir.iterdir():
                    if page_dir.is_dir():
                        page_json = page_dir / 'page.json'
                        if page_json.exists():
                            files_checked += 1
                            valid, err = cls.validate_json_file(page_json)
                            if not valid:
                                errors.append(err)
                            else:
                                # PBIR structural validation on page.json
                                try:
                                    with open(page_json, 'r', encoding='utf-8') as f:
                                        pj = json.load(f)
                                    schema_url = pj.get('$schema', '') if isinstance(pj, dict) else ''
                                    if schema_url:
                                        pbir_errs = cls.validate_pbir_structure(pj, schema_url)
                                        warnings.extend(pbir_errs)
                                except Exception:
                                    pass

                        # Validate visuals
                        visuals_dir = page_dir / 'visuals'
                        if visuals_dir.exists():
                            for visual_dir in visuals_dir.iterdir():
                                if visual_dir.is_dir():
                                    visual_json = visual_dir / 'visual.json'
                                    if visual_json.exists():
                                        files_checked += 1
                                        valid, err = cls.validate_json_file(visual_json)
                                        if not valid:
                                            errors.append(err)
                                        else:
                                            # PBIR structural validation on visual.json
                                            try:
                                                with open(visual_json, 'r', encoding='utf-8') as f:
                                                    vj = json.load(f)
                                                schema_url = vj.get('$schema', '') if isinstance(vj, dict) else ''
                                                if schema_url:
                                                    pbir_errs = cls.validate_pbir_structure(vj, schema_url)
                                                    warnings.extend(pbir_errs)
                                            except Exception:
                                                pass
        else:
            errors.append(f'Missing Report directory: {report_dir.name}')

        # Check SemanticModel directory
        sm_dir = project_dir / f'{report_name}.SemanticModel'
        if sm_dir.exists():
            # Validate model.tmdl
            model_tmdl = sm_dir / 'definition' / 'model.tmdl'
            if model_tmdl.exists():
                files_checked += 1
                valid, errs = cls.validate_tmdl_file(model_tmdl)
                if not valid:
                    errors.extend(errs)
                # Semantic DAX validation on model.tmdl
                dax_issues = cls.validate_tmdl_dax(str(model_tmdl))
                if dax_issues:
                    warnings.extend(dax_issues)
            else:
                errors.append('Missing model.tmdl in SemanticModel/definition/')

            # Validate table TMDL files
            tables_dir = sm_dir / 'definition' / 'tables'
            if tables_dir.exists():
                for tmdl_file in tables_dir.glob('*.tmdl'):
                    files_checked += 1
                    valid, errs = cls.validate_tmdl_file(tmdl_file)
                    if not valid:
                        errors.extend(errs)
                    # Semantic DAX validation on each table TMDL
                    dax_issues = cls.validate_tmdl_dax(str(tmdl_file))
                    if dax_issues:
                        warnings.extend(dax_issues)
            else:
                warnings.append('No tables/ directory in SemanticModel (may be empty model)')

            # Validate roles TMDL (RLS DAX expressions)
            roles_tmdl = sm_dir / 'definition' / 'roles.tmdl'
            if roles_tmdl.exists():
                files_checked += 1
                dax_issues = cls.validate_tmdl_dax(str(roles_tmdl))
                if dax_issues:
                    warnings.extend(dax_issues)

            # Semantic reference validation (check 'Table'[Column] refs)
            sem_warnings = cls.validate_semantic_references(str(sm_dir))
            if sem_warnings:
                warnings.extend(sem_warnings)

        # Visual → TMDL cross-validation (check Entity+Property in visuals)
        if sm_dir.exists() and report_dir.exists():
            visual_errors = cls.validate_visual_references(project_dir)
            if visual_errors:
                warnings.extend(visual_errors)

        if not sm_dir.exists():
            errors.append(f'Missing SemanticModel directory: {sm_dir.name}')

        is_valid = len(errors) == 0

        result = {
            'valid': is_valid,
            'errors': errors,
            'warnings': warnings,
            'files_checked': files_checked,
        }

        # Log results
        status = '[OK]' if is_valid else '[FAIL]'
        logger.info(f'{status} {report_name}: {files_checked} files checked, '
                     f'{len(errors)} errors, {len(warnings)} warnings')
        for e in errors:
            logger.warning(f'  ERROR: {e}')
        for w in warnings:
            logger.info(f'  WARN: {w}')

        return result

    # ── Visual → TMDL cross-validation ─────────────────────────────

    # Regex to extract Entity/Property from PBIR visual JSON "Column" or "Measure" refs
    _RE_VISUAL_FIELD_REF = re.compile(
        r'"(?:Column|Measure)"\s*:\s*\{\s*'
        r'"Expression"\s*:\s*\{\s*"SourceRef"\s*:\s*\{\s*"Entity"\s*:\s*"([^"]+)"\s*\}\s*\}\s*,\s*'
        r'"Property"\s*:\s*"([^"]+)"',
        re.DOTALL
    )

    @classmethod
    def _unescape_tmdl_name(cls, name):
        """Unescape TMDL doubled apostrophes: ``''`` → ``'``."""
        return name.replace("''", "'")

    @classmethod
    def validate_visual_references(cls, project_dir):
        """Validate that all Entity+Property field references in visual.json
        files resolve to an actual table+column or table+measure in the
        TMDL semantic model.

        Args:
            project_dir: Path to the .pbip project directory.

        Returns:
            list of error strings for unresolved visual field references.
        """
        project_dir = Path(project_dir)
        report_name = project_dir.name

        sm_dir = project_dir / f'{report_name}.SemanticModel'
        report_dir = project_dir / f'{report_name}.Report'

        if not sm_dir.exists() or not report_dir.exists():
            return []  # nothing to validate

        # Collect all symbols from TMDL (already unescaped)
        symbols = cls._collect_model_symbols(str(sm_dir))
        known_tables = symbols['tables']
        known_cols = symbols['columns']    # table -> {col names}
        known_measures = symbols['measures']  # table -> {measure names}

        # Build combined field lookup (no extra unescaping needed — done at collection)
        all_fields_by_table = {}
        for t in known_tables:
            all_fields_by_table[t] = known_cols.get(t, set()) | known_measures.get(t, set())

        # Scan visual.json files for Entity+Property references
        errors = []
        definition_dir = report_dir / 'definition'
        pages_dir = definition_dir / 'pages' if definition_dir.exists() else report_dir / 'pages'
        if not pages_dir.exists():
            return []

        for page_dir in sorted(pages_dir.iterdir()):
            if not page_dir.is_dir():
                continue
            visuals_dir = page_dir / 'visuals'
            if not visuals_dir.exists():
                continue
            for visual_dir in sorted(visuals_dir.iterdir()):
                if not visual_dir.is_dir():
                    continue
                visual_json = visual_dir / 'visual.json'
                if not visual_json.exists():
                    continue
                try:
                    content = visual_json.read_text(encoding='utf-8')
                except Exception:
                    continue

                # Extract all Entity+Property pairs from JSON text
                for match in cls._RE_VISUAL_FIELD_REF.finditer(content):
                    entity = match.group(1)
                    prop = match.group(2)

                    if entity not in known_tables:
                        errors.append(
                            f'Visual {visual_dir.name}: unknown Entity '
                            f'"{entity}" (not in TMDL model)'
                        )
                    else:
                        fields = all_fields_by_table.get(entity, set())
                        if prop not in fields:
                            errors.append(
                                f'Visual {visual_dir.name}: unknown Property '
                                f'"{prop}" in Entity "{entity}" '
                                f'(not a column or measure in TMDL)'
                            )

        return errors

    @classmethod
    def validate_directory(cls, artifacts_dir):
        """
        Validate all .pbip projects in a directory.

        Args:
            artifacts_dir: Directory containing .pbip project folders

        Returns:
            Dictionary mapping project names to validation results
        """
        artifacts_dir = Path(artifacts_dir)
        results = {}

        if not artifacts_dir.exists():
            logger.error(f'Directory not found: {artifacts_dir}')
            return results

        # Find project directories (contain a .pbip file)
        for item in sorted(artifacts_dir.iterdir()):
            if item.is_dir():
                pbip_files = list(item.glob('*.pbip'))
                if pbip_files:
                    result = cls.validate_project(item)
                    results[item.name] = result

        # Also validate standalone JSON artifacts
        for json_file in sorted(artifacts_dir.glob('*.json')):
            is_valid, errors = cls.validate_artifact(json_file)
            results[json_file.name] = {
                'valid': is_valid,
                'errors': errors,
                'warnings': [],
                'files_checked': 1,
            }

        return results
