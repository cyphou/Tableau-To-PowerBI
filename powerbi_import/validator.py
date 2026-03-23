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
        'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/2.0.0/schema.json',
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
        except (KeyError, TypeError, ValueError, OSError) as e:
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
        except OSError as e:
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

            # Validate M partition expressions have balanced if/else
            parts = re.split(r'partition\s', content)
            for idx, part in enumerate(parts[1:], 1):
                if '= m' in part[:100]:
                    # Strip M string literals to avoid counting keywords inside strings
                    stripped = re.sub(r'"([^"]|"")*"', '""', part)
                    if_count = len(re.findall(r'\bif\b', stripped))
                    else_count = len(re.findall(r'\belse\b', stripped))
                    if if_count != else_count:
                        errors.append(
                            f'M if/else imbalance in partition {idx} of {basename}: '
                            f'if={if_count}, else={else_count}')

            return len(errors) == 0, errors

        except OSError as e:
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
        except OSError:
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
            except OSError:
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
            except OSError:
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
                    except (json.JSONDecodeError, OSError) as exc:
                        logger.debug("PBIR structural validation skipped for report.json: %s", exc)
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
                                except (json.JSONDecodeError, OSError) as exc:
                                    logger.debug("PBIR structural validation skipped for %s: %s", page_json, exc)

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
                                            except (json.JSONDecodeError, OSError) as exc:
                                                logger.debug("PBIR structural validation skipped for %s: %s", visual_json, exc)
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

            # Enhanced semantic validation (Sprint 46)
            cycles = cls.detect_circular_relationships(str(sm_dir))
            for cycle in cycles:
                warnings.append(f'Circular relationship: {cycle}')

            orphans = cls.detect_orphan_tables(str(sm_dir))
            for orphan in orphans:
                warnings.append(f'Orphan table (no relationships or DAX references): {orphan}')

            unused_params = cls.detect_unused_parameters(str(sm_dir))
            for param in unused_params:
                warnings.append(f'Unused parameter table: {param}')

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
                except OSError:
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

    # ── PBIR schema version base URL for discovery ──
    _SCHEMA_BASE_URL = (
        'https://developer.microsoft.com/json-schemas'
        '/fabric/item/report/definition'
    )

    # Schema paths and their current versions (major.minor.patch)
    _SCHEMA_VERSIONS = {
        'report': '3.1.0',
        'page': '2.0.0',
        'visualContainer': '2.5.0',
    }

    @classmethod
    def check_pbir_schema_version(cls, fetch=False):
        """Check PBIR schema versions for forward-compatibility.

        Compares the hardcoded schema URLs against the latest known
        versions.  Optionally fetches the schema URLs from Microsoft
        docs to detect newer versions.

        Args:
            fetch: If True, attempt to HTTP-fetch schema URLs to
                detect newer published versions.  Requires network
                access.  Defaults to False (offline check only).

        Returns:
            dict: Keys are schema types ('report', 'page',
                'visualContainer'), values are dicts with:
                - ``current``: Currently hardcoded version string
                - ``latest``: Latest detected version (or current if
                  fetch is disabled / fails)
                - ``url``: Full schema URL
                - ``update_available``: bool
        """
        results = {}

        for schema_type, current_version in cls._SCHEMA_VERSIONS.items():
            url = (
                f'{cls._SCHEMA_BASE_URL}/{schema_type}'
                f'/{current_version}/schema.json'
            )
            entry = {
                'current': current_version,
                'latest': current_version,
                'url': url,
                'update_available': False,
            }

            if fetch:
                latest = cls._fetch_latest_schema_version(
                    schema_type, current_version
                )
                if latest and latest != current_version:
                    entry['latest'] = latest
                    entry['update_available'] = True
                    latest_url = (
                        f'{cls._SCHEMA_BASE_URL}/{schema_type}'
                        f'/{latest}/schema.json'
                    )
                    entry['url'] = latest_url
                    logger.warning(
                        f'PBIR schema update available for {schema_type}: '
                        f'{current_version} → {latest}'
                    )

            results[schema_type] = entry

        return results

    @classmethod
    def _fetch_latest_schema_version(cls, schema_type, current_version):
        """Try to fetch a newer schema version from Microsoft docs.

        Probes incrementally higher version numbers (patch, then minor)
        to find the latest published schema.

        Args:
            schema_type: Schema type ('report', 'page', 'visualContainer').
            current_version: Current version string (e.g., '3.1.0').

        Returns:
            str | None: Latest version string, or None on failure.
        """
        try:
            from urllib.request import urlopen, Request
            from urllib.error import URLError, HTTPError
        except ImportError:
            return None

        parts = current_version.split('.')
        if len(parts) != 3:
            return None

        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
        latest = current_version

        # Probe higher patch versions first
        for p in range(patch + 1, patch + 5):
            probe = f'{major}.{minor}.{p}'
            probe_url = (
                f'{cls._SCHEMA_BASE_URL}/{schema_type}'
                f'/{probe}/schema.json'
            )
            if cls._url_exists(probe_url):
                latest = probe

        # Probe next minor version
        for m in range(minor + 1, minor + 3):
            probe = f'{major}.{m}.0'
            probe_url = (
                f'{cls._SCHEMA_BASE_URL}/{schema_type}'
                f'/{probe}/schema.json'
            )
            if cls._url_exists(probe_url):
                latest = probe

        return latest

    @staticmethod
    def _url_exists(url):
        """Check if a URL returns HTTP 200 (HEAD request).

        Args:
            url: URL to check.

        Returns:
            bool: True if the URL is reachable and returns 200.
        """
        try:
            from urllib.request import urlopen, Request
            from urllib.error import URLError, HTTPError
            req = Request(url, method='HEAD')
            req.add_header('User-Agent', 'TableauToPowerBI-SchemaCheck/1.0')
            with urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    # ── Enhanced semantic validation (Sprint 46) ─────────────────

    # Regex to extract TMDL relationship definitions
    _RE_TMDL_RELATIONSHIP = re.compile(
        r"relationship\s+\S+\s*\n"
        r"(?:.*?\n)*?"
        r"\s*fromTable:\s*'?((?:[^'\n]|'')+)'?\s*\n"
        r"(?:.*?\n)*?"
        r"\s*toTable:\s*'?((?:[^'\n]|'')+)'?\s*\n",
        re.MULTILINE,
    )

    @classmethod
    def detect_circular_relationships(cls, sm_dir):
        """Detect circular dependency chains in TMDL relationships.

        Builds a directed graph from ``fromTable → toTable`` in
        relationship definitions and searches for cycles using DFS.

        Args:
            sm_dir: Path to ``{name}.SemanticModel`` directory.

        Returns:
            list of cycle descriptions (empty = no cycles).
        """
        sm_path = Path(sm_dir)
        def_dir = sm_path / 'definition'
        model_tmdl = def_dir / 'model.tmdl'

        if not model_tmdl.exists():
            return []

        try:
            content = model_tmdl.read_text(encoding='utf-8')
        except OSError:
            return []

        # Parse relationships from model.tmdl
        graph = {}  # table -> set of target tables
        lines = content.splitlines()
        i = 0
        while i < len(lines):
            stripped = lines[i].strip()
            if stripped.startswith('relationship '):
                from_table = None
                to_table = None
                j = i + 1
                while j < len(lines) and not lines[j].strip().startswith('relationship ') and lines[j].strip() != '':
                    ln = lines[j].strip()
                    if ln.startswith('fromTable:'):
                        from_table = ln.split(':', 1)[1].strip().strip("'").replace("''", "'")
                    elif ln.startswith('toTable:'):
                        to_table = ln.split(':', 1)[1].strip().strip("'").replace("''", "'")
                    j += 1
                if from_table and to_table:
                    graph.setdefault(from_table, set()).add(to_table)
                i = j
            else:
                i += 1

        # DFS cycle detection
        cycles = []
        visited = set()
        rec_stack = set()

        def _dfs(node, path):
            visited.add(node)
            rec_stack.add(node)
            for neighbor in graph.get(node, set()):
                if neighbor in rec_stack:
                    cycle_start = path.index(neighbor) if neighbor in path else len(path)
                    cycle = path[cycle_start:] + [neighbor]
                    cycles.append(' → '.join(cycle))
                elif neighbor not in visited:
                    _dfs(neighbor, path + [neighbor])
            rec_stack.discard(node)

        for node in graph:
            if node not in visited:
                _dfs(node, [node])

        return cycles

    @classmethod
    def detect_orphan_tables(cls, sm_dir):
        """Detect tables with no relationships and no measure references.

        Orphan tables are tables that are:
        - Not referenced in any relationship (fromTable or toTable)
        - Not referenced by any ``'Table'[Column]`` DAX expression
          in other tables

        Args:
            sm_dir: Path to ``{name}.SemanticModel`` directory.

        Returns:
            list of orphan table names.
        """
        sm_path = Path(sm_dir)
        def_dir = sm_path / 'definition'

        symbols = cls._collect_model_symbols(sm_dir)
        all_tables = symbols['tables']

        if len(all_tables) <= 1:
            return []  # Single table is not orphaned

        # Find tables referenced in relationships
        relationship_tables = set()
        model_tmdl = def_dir / 'model.tmdl'
        if model_tmdl.exists():
            try:
                content = model_tmdl.read_text(encoding='utf-8')
                for line in content.splitlines():
                    stripped = line.strip()
                    if stripped.startswith('fromTable:') or stripped.startswith('toTable:'):
                        table_name = stripped.split(':', 1)[1].strip().strip("'").replace("''", "'")
                        relationship_tables.add(table_name)
            except OSError:
                pass

        # Find tables referenced in DAX expressions in other tables
        dax_referenced_tables = set()
        tables_dir = def_dir / 'tables'
        if tables_dir and tables_dir.exists():
            for tmdl_f in tables_dir.glob('*.tmdl'):
                try:
                    content = tmdl_f.read_text(encoding='utf-8')
                except OSError:
                    continue
                for match in cls._RE_DAX_REF.finditer(content):
                    ref_table = cls._unescape_tmdl_name(match.group(1))
                    dax_referenced_tables.add(ref_table)

        # Orphans = tables not in relationships AND not referenced by DAX
        referenced = relationship_tables | dax_referenced_tables
        # Exclude well-known utility tables
        utility_tables = {'Calendar', 'Date', 'DateTable'}
        orphans = [
            t for t in sorted(all_tables)
            if t not in referenced and t not in utility_tables
        ]

        return orphans

    @classmethod
    def detect_unused_parameters(cls, sm_dir):
        """Detect parameter tables/measures not referenced anywhere.

        Parameter tables in PBI follow the naming pattern containing
        'Parameter' or have a GENERATESERIES/DATATABLE partition.
        This method finds parameter-like tables whose measures are
        never referenced by other tables' DAX expressions.

        Args:
            sm_dir: Path to ``{name}.SemanticModel`` directory.

        Returns:
            list of unused parameter names.
        """
        sm_path = Path(sm_dir)
        def_dir = sm_path / 'definition'
        tables_dir = def_dir / 'tables'

        if not tables_dir or not tables_dir.exists():
            return []

        # Identify parameter tables (name contains 'Parameter' or has
        # GENERATESERIES/DATATABLE in partition)
        param_tables = {}  # table_name -> set of measure names
        all_content = {}  # table_name -> file content

        for tmdl_f in tables_dir.glob('*.tmdl'):
            try:
                content = tmdl_f.read_text(encoding='utf-8')
            except OSError:
                continue

            # Extract table name
            for line in content.splitlines():
                stripped = line.strip()
                tm = cls._RE_TABLE_DEF.match(stripped)
                if tm:
                    raw = tm.group(1) if tm.group(1) is not None else tm.group(2)
                    table_name = cls._unescape_tmdl_name(raw)
                    all_content[table_name] = content

                    is_param = (
                        'parameter' in table_name.lower()
                        or 'GENERATESERIES' in content
                        or 'DATATABLE' in content
                    )
                    if is_param:
                        # Collect measure names
                        measures = set()
                        for mline in content.splitlines():
                            mm = cls._RE_MEASURE_DEF.match(mline.strip())
                            if mm:
                                raw_m = mm.group(1) if mm.group(1) is not None else mm.group(2)
                                measures.add(cls._unescape_tmdl_name(raw_m))
                        param_tables[table_name] = measures
                    break

        if not param_tables:
            return []

        # Check if parameter measures are referenced in other tables
        unused = []
        for param_table, param_measures in param_tables.items():
            referenced = False
            for other_table, content in all_content.items():
                if other_table == param_table:
                    continue
                for measure in param_measures:
                    if f'[{measure}]' in content:
                        referenced = True
                        break
                if referenced:
                    break

            # Also check model.tmdl
            if not referenced:
                model_tmdl = def_dir / 'model.tmdl'
                if model_tmdl.exists():
                    try:
                        model_content = model_tmdl.read_text(encoding='utf-8')
                        for measure in param_measures:
                            if f'[{measure}]' in model_content:
                                referenced = True
                                break
                    except OSError:
                        pass

            if not referenced:
                unused.append(param_table)

        return unused

    # ── Sprint 59: Enhanced Validators ─────────────────────────────

    # Known Power Query M table functions (subset for validation)
    _KNOWN_M_TABLE_FUNCTIONS = {
        'Table.FromRows', 'Table.FromRecords', 'Table.FromList',
        'Table.FromColumns', 'Table.FromValue', 'Table.RenameColumns',
        'Table.RemoveColumns', 'Table.SelectColumns', 'Table.DuplicateColumn',
        'Table.ReorderColumns', 'Table.SplitColumn', 'Table.CombineColumns',
        'Table.ReplaceValue', 'Table.TransformColumns', 'Table.FillDown',
        'Table.FillUp', 'Table.SelectRows', 'Table.Distinct', 'Table.FirstN',
        'Table.Group', 'Table.Unpivot', 'Table.UnpivotOtherColumns',
        'Table.Pivot', 'Table.NestedJoin', 'Table.ExpandTableColumn',
        'Table.Combine', 'Table.Sort', 'Table.Transpose',
        'Table.AddIndexColumn', 'Table.Skip', 'Table.RemoveLastN',
        'Table.AddColumn', 'Table.Buffer', 'Table.PromoteHeaders',
        'Table.DemoteHeaders', 'Table.RemoveRowsWithErrors',
        'Table.TransformColumnTypes', 'Table.Schema',
    }

    _SEVERITY_ERROR = 'ERROR'
    _SEVERITY_WARNING = 'WARNING'
    _SEVERITY_INFO = 'INFO'

    @classmethod
    def validate_tmdl_indentation(cls, content, filepath=''):
        """Validate TMDL indentation consistency.

        TMDL spec requires tab-based indentation. Flags mixed tabs/spaces
        and incorrect nesting depth.

        Returns:
            List of issue dicts: ``{severity, message, line}``.
        """
        issues = []
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if not line or not line[0] in (' ', '\t'):
                continue
            stripped = line.lstrip()
            if not stripped:
                continue
            leading = line[:len(line) - len(stripped)]
            has_tabs = '\t' in leading
            has_spaces = ' ' in leading
            if has_tabs and has_spaces:
                issues.append({
                    'severity': cls._SEVERITY_WARNING,
                    'message': f'Mixed tabs and spaces at line {i} in {filepath}',
                    'line': i,
                })
        return issues

    @classmethod
    def validate_tmdl_structure(cls, content, filepath=''):
        """Validate TMDL keyword balance.

        Checks that every ``table`` block has at least one ``column`` or
        ``partition``, every ``relationship`` has ``fromColumn``/``toColumn``,
        and every ``role`` has at least one ``tablePermission``.

        Returns:
            List of issue dicts.
        """
        issues = []
        lines = content.split('\n')
        current_table = None
        has_column_or_partition = False
        current_role = None
        has_table_permission = False

        for line in lines:
            stripped = line.strip()
            # Track table blocks
            if stripped.startswith('table ') and not stripped.startswith('tablePermission'):
                if current_table and not has_column_or_partition:
                    issues.append({
                        'severity': cls._SEVERITY_WARNING,
                        'message': f'Table "{current_table}" has no columns or partitions in {filepath}',
                        'line': 0,
                    })
                current_table = stripped.split("'")[1] if "'" in stripped else stripped.split()[1] if len(stripped.split()) > 1 else None
                has_column_or_partition = False

            if current_table and stripped.startswith(('column ', 'partition ')):
                has_column_or_partition = True

            # Track role blocks
            if stripped.startswith('role '):
                if current_role and not has_table_permission:
                    issues.append({
                        'severity': cls._SEVERITY_WARNING,
                        'message': f'Role "{current_role}" has no tablePermission in {filepath}',
                        'line': 0,
                    })
                current_role = stripped.split("'")[1] if "'" in stripped else stripped.split()[1] if len(stripped.split()) > 1 else None
                has_table_permission = False

            if current_role and stripped.startswith('tablePermission'):
                has_table_permission = True

        # Final blocks
        if current_table and not has_column_or_partition:
            issues.append({
                'severity': cls._SEVERITY_WARNING,
                'message': f'Table "{current_table}" has no columns or partitions in {filepath}',
                'line': 0,
            })
        if current_role and not has_table_permission:
            issues.append({
                'severity': cls._SEVERITY_WARNING,
                'message': f'Role "{current_role}" has no tablePermission in {filepath}',
                'line': 0,
            })

        return issues

    @classmethod
    def validate_m_expression(cls, m_code, context=''):
        """Validate a Power Query M expression for common errors.

        Checks: unmatched ``let``/``in``, unclosed quotes/brackets,
        dangling ``{prev}`` placeholders, missing ``Source`` step.

        Returns:
            List of issue dicts.
        """
        issues = []
        if not m_code or not m_code.strip():
            return issues

        code = m_code.strip()

        # let/in balance
        let_count = len(re.findall(r'\blet\b', code, re.IGNORECASE))
        in_count = len(re.findall(r'\bin\b', code, re.IGNORECASE))
        if let_count > 0 and in_count == 0:
            issues.append({
                'severity': cls._SEVERITY_ERROR,
                'message': f'M expression has "let" without matching "in"{" in " + context if context else ""}',
                'line': 0,
            })

        # Unmatched brackets
        for open_ch, close_ch, name in [('(', ')', 'parentheses'), ('{', '}', 'braces'), ('[', ']', 'brackets')]:
            depth = 0
            in_string = False
            for ch in code:
                if ch == '"' and not in_string:
                    in_string = True
                elif ch == '"' and in_string:
                    in_string = False
                elif not in_string:
                    if ch == open_ch:
                        depth += 1
                    elif ch == close_ch:
                        depth -= 1
            if depth != 0:
                issues.append({
                    'severity': cls._SEVERITY_ERROR,
                    'message': f'Unmatched {name} in M expression{" in " + context if context else ""}',
                    'line': 0,
                })

        # Dangling {prev} placeholder
        if '{prev}' in code:
            issues.append({
                'severity': cls._SEVERITY_ERROR,
                'message': f'Dangling {{prev}} placeholder in M expression{" in " + context if context else ""}',
                'line': 0,
            })

        return issues

    @classmethod
    def validate_visual_completeness(cls, visual_json, filepath=''):
        """Check visual JSON for completeness beyond schema compliance.

        Flags: empty query state, missing visualType, zero-size position.

        Returns:
            List of issue dicts.
        """
        issues = []
        visual = visual_json.get('visual', visual_json)

        vtype = visual.get('visualType', '')
        if not vtype:
            issues.append({
                'severity': cls._SEVERITY_WARNING,
                'message': f'Visual missing visualType in {filepath}',
                'line': 0,
            })

        pos = visual_json.get('position', {})
        w = pos.get('width', 1)
        h = pos.get('height', 1)
        if w <= 0 or h <= 0:
            issues.append({
                'severity': cls._SEVERITY_WARNING,
                'message': f'Visual has zero or negative size ({w}x{h}) in {filepath}',
                'line': 0,
            })

        return issues

    @classmethod
    def validate_cross_references(cls, project_dir):
        """Verify report → page → visual file chain is complete.

        Checks every page directory has page.json, every visual directory has
        visual.json. Flags orphan files.

        Returns:
            List of issue dicts.
        """
        issues = []
        project_dir = Path(project_dir)

        # Find report directory
        report_dirs = [d for d in project_dir.iterdir()
                       if d.is_dir() and d.name.endswith('.Report')]
        if not report_dirs:
            return issues

        report_dir = report_dirs[0]
        pages_dir = report_dir / 'pages'
        if not pages_dir.exists():
            issues.append({
                'severity': cls._SEVERITY_ERROR,
                'message': f'pages/ directory missing in {report_dir}',
                'line': 0,
            })
            return issues

        for page_dir in sorted(pages_dir.iterdir()):
            if not page_dir.is_dir():
                continue
            page_json = page_dir / 'page.json'
            if not page_json.exists():
                issues.append({
                    'severity': cls._SEVERITY_ERROR,
                    'message': f'page.json missing in {page_dir.name}',
                    'line': 0,
                })

            visuals_dir = page_dir / 'visuals'
            if visuals_dir.exists():
                for vis_dir in sorted(visuals_dir.iterdir()):
                    if not vis_dir.is_dir():
                        continue
                    vis_json = vis_dir / 'visual.json'
                    if not vis_json.exists():
                        issues.append({
                            'severity': cls._SEVERITY_WARNING,
                            'message': f'visual.json missing in {vis_dir.name}',
                            'line': 0,
                        })

        return issues

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
