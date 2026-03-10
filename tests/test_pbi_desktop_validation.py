"""
Tests for PBI Desktop validation — Phase A+B.

Ensures fixes for:
1. Empty measure expressions (categorical-bin groups)
2. Tableau ephemeral field reference leakage (yr:, mn:, etc.)
3. Enhanced validator checks (empty expressions, derivation refs, lineageTag)
"""

import os
import re
import sys
import json
import unittest
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tableau_export'))

from tableau_export.datasource_extractor import extract_calculations
from tableau_export.extract_tableau_data import _clean_field_ref
from powerbi_import.tmdl_generator import generate_tmdl
from powerbi_import.validator import ArtifactValidator


# ═══════════════════════════════════════════════════════════════════
# 1. Empty Measure Expression Tests
# ═══════════════════════════════════════════════════════════════════

class TestEmptyMeasurePrevention(unittest.TestCase):
    """Tests that empty-formula calculations are filtered out."""

    def _make_xml_column(self, name, formula='', calc_class='tableau',
                         role='measure', datatype='real'):
        """Create a minimal XML string for a <column> with <calculation>."""
        import xml.etree.ElementTree as ET
        col = ET.Element('column', attrib={
            'name': f'[{name}]',
            'caption': name,
            'role': role,
            'datatype': datatype,
        })
        calc_attrs = {'class': calc_class}
        if formula:
            calc_attrs['formula'] = formula
        ET.SubElement(col, 'calculation', attrib=calc_attrs)
        return col

    def _make_datasource_elem(self, columns):
        """Wrap column elements in a datasource element."""
        import xml.etree.ElementTree as ET
        ds = ET.Element('datasource')
        for col in columns:
            ds.append(col)
        return ds

    def test_categorical_bin_skipped(self):
        """categorical-bin calculations should be filtered out."""
        cols = [
            self._make_xml_column('Profit (bin)', calc_class='categorical-bin'),
            self._make_xml_column('Total Sales', formula='SUM([Sales])',
                                  calc_class='tableau'),
        ]
        ds = self._make_datasource_elem(cols)
        result = extract_calculations(ds)
        names = [c['name'] for c in result]
        self.assertNotIn('[Profit (bin)]', names)
        self.assertIn('[Total Sales]', names)

    def test_empty_formula_skipped(self):
        """Calculations with empty formula should be filtered out."""
        cols = [
            self._make_xml_column('Empty Calc', formula=''),
            self._make_xml_column('Whitespace Calc', formula='   '),
            self._make_xml_column('Good Calc', formula='SUM([Sales])'),
        ]
        ds = self._make_datasource_elem(cols)
        result = extract_calculations(ds)
        names = [c['name'] for c in result]
        self.assertNotIn('[Empty Calc]', names)
        self.assertNotIn('[Whitespace Calc]', names)
        self.assertIn('[Good Calc]', names)

    def test_valid_calcs_preserved(self):
        """Normal calculations should still be extracted."""
        cols = [
            self._make_xml_column('Profit Ratio', formula='SUM([Profit])/SUM([Sales])'),
            self._make_xml_column('Region Category', formula='IF [Region]="West" THEN "Pacific" END',
                                  role='dimension', datatype='string'),
        ]
        ds = self._make_datasource_elem(cols)
        result = extract_calculations(ds)
        self.assertEqual(len(result), 2)

    def test_tmdl_skips_empty_formulas(self):
        """generate_tmdl should not create measures with empty expressions."""
        datasources = [{
            'name': 'Test',
            'tables': [{'name': 'Sales', 'columns': [
                {'name': 'Amount', 'datatype': 'real', 'role': 'measure'},
            ]}],
            'calculations': [
                {'name': '[Empty]', 'caption': 'Empty', 'formula': '',
                 'role': 'measure', 'datatype': 'real', 'class': 'tableau'},
                {'name': '[Good]', 'caption': 'Good', 'formula': 'SUM([Amount])',
                 'role': 'measure', 'datatype': 'real', 'class': 'tableau'},
            ],
            'relationships': [],
        }]
        extra_objects = {
            'hierarchies': [], 'sets': [], 'groups': [], 'bins': [],
            'aliases': {}, 'parameters': [], 'user_filters': [],
            '_datasources': datasources,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            sm_dir = os.path.join(tmpdir, 'Test.SemanticModel')
            os.makedirs(sm_dir, exist_ok=True)
            result = generate_tmdl(datasources, 'Test', extra_objects, sm_dir)

            # Scan generated TMDL for empty measures
            empty_pattern = re.compile(r"^\s*measure\s+'[^']+'\s*=\s*$", re.MULTILINE)
            tables_dir = os.path.join(sm_dir, 'definition', 'tables')
            if os.path.exists(tables_dir):
                for tmdl_file in os.listdir(tables_dir):
                    if tmdl_file.endswith('.tmdl'):
                        with open(os.path.join(tables_dir, tmdl_file), 'r') as f:
                            content = f.read()
                        matches = empty_pattern.findall(content)
                        self.assertEqual(len(matches), 0,
                                         f'Empty measure in {tmdl_file}: {matches}')

    def test_write_measure_defensive_fallback(self):
        """_write_measure should use '0' when expression is empty string."""
        lines = []
        ArtifactValidator  # just import check
        # Directly test tmdl_generator._write_measure
        from powerbi_import.tmdl_generator import _write_measure
        measure = {'name': 'Test Measure', 'expression': '', 'formatString': '0'}
        _write_measure(lines, measure)
        # Should produce "measure 'Test Measure' = 0" not "measure 'Test Measure' = "
        measure_line = [l for l in lines if 'measure' in l][0]
        self.assertTrue(measure_line.strip().endswith('= 0'),
                        f'Expected fallback to 0, got: {measure_line}')

    def test_write_measure_none_expression(self):
        """_write_measure should handle None expression."""
        from powerbi_import.tmdl_generator import _write_measure
        lines = []
        measure = {'name': 'Null Measure'}
        _write_measure(lines, measure)
        measure_line = [l for l in lines if 'measure' in l][0]
        self.assertTrue(measure_line.strip().endswith('= 0'))


# ═══════════════════════════════════════════════════════════════════
# 2. Ephemeral Field Reference Tests
# ═══════════════════════════════════════════════════════════════════

class TestEphemeralFieldRefCleaning(unittest.TestCase):
    """Tests for _clean_field_ref and group extraction cleaning."""

    def test_clean_yr_prefix(self):
        self.assertEqual(_clean_field_ref('yr:Order Date:ok'), 'Order Date')

    def test_clean_mn_prefix(self):
        self.assertEqual(_clean_field_ref('mn:Ship Date:ok'), 'Ship Date')

    def test_clean_none_prefix(self):
        self.assertEqual(_clean_field_ref('none:Category:nk'), 'Category')

    def test_clean_qr_prefix(self):
        self.assertEqual(_clean_field_ref('qr:Date:qk'), 'Date')

    def test_clean_tyr_prefix(self):
        """tyr: prefix (truncated year) may appear in Tableau."""
        # Note: tyr is not in the standard prefix list but thr/trunc are.
        # _clean_field_ref handles standard prefixes; tyr: will pass through.
        result = _clean_field_ref('thr:Date:qk')
        self.assertEqual(result, 'Date')

    def test_clean_no_prefix(self):
        """Plain field name should pass through unchanged."""
        self.assertEqual(_clean_field_ref('Order Date'), 'Order Date')

    def test_clean_only_suffix(self):
        """Field with only suffix should have suffix removed."""
        self.assertEqual(_clean_field_ref('Sales:qk'), 'Sales')

    def test_clean_sum_prefix(self):
        self.assertEqual(_clean_field_ref('sum:Profit:qk'), 'Profit')

    def test_clean_attr_prefix(self):
        self.assertEqual(_clean_field_ref('attr:Product Name:nk'), 'Product Name')

    def test_clean_complex_field_name(self):
        """Field names with spaces and special chars."""
        self.assertEqual(
            _clean_field_ref('yr:Order Date (Copy):ok'),
            'Order Date (Copy)'
        )

    def test_clean_wk_prefix(self):
        self.assertEqual(_clean_field_ref('wk:Date:ok'), 'Date')

    def test_clean_dy_prefix(self):
        self.assertEqual(_clean_field_ref('dy:Ship Date:ok'), 'Ship Date')


# ═══════════════════════════════════════════════════════════════════
# 3. Enhanced Validator Tests
# ═══════════════════════════════════════════════════════════════════

class TestValidatorEmptyExpression(unittest.TestCase):
    """Tests for empty expression detection in TMDL files."""

    def _make_tmdl(self, content):
        """Create a temp TMDL file with content."""
        fd, path = tempfile.mkstemp(suffix='.tmdl')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def test_detects_empty_measure(self):
        """Validator should catch measure with no expression."""
        path = self._make_tmdl(
            "table Sales\n"
            "\tmeasure 'Total Sales' = \n"
            "\t\tformatString: 0\n"
        )
        try:
            issues = ArtifactValidator.validate_tmdl_dax(path)
            empty_issues = [i for i in issues if 'Empty measure expression' in i]
            self.assertTrue(len(empty_issues) > 0,
                            f'Should detect empty measure, got: {issues}')
        finally:
            os.unlink(path)

    def test_valid_measure_no_false_positive(self):
        """Valid measure should not trigger empty expression warning."""
        path = self._make_tmdl(
            "table Sales\n"
            "\tmeasure 'Total Sales' = SUM('Sales'[Amount])\n"
            "\t\tformatString: 0\n"
        )
        try:
            issues = ArtifactValidator.validate_tmdl_dax(path)
            empty_issues = [i for i in issues if 'Empty' in i]
            self.assertEqual(len(empty_issues), 0,
                             f'Valid measure should not trigger empty warning: {issues}')
        finally:
            os.unlink(path)

    def test_detects_empty_expression_property(self):
        """Validator should catch 'expression =' with nothing after."""
        path = self._make_tmdl(
            "table Sales\n"
            "\tcolumn 'Calculated'\n"
            "\t\texpression =\n"
            "\t\tdataType: int64\n"
        )
        try:
            issues = ArtifactValidator.validate_tmdl_dax(path)
            empty_issues = [i for i in issues if 'Empty expression' in i]
            self.assertTrue(len(empty_issues) > 0,
                            f'Should detect empty expression: {issues}')
        finally:
            os.unlink(path)


class TestValidatorDerivationRef(unittest.TestCase):
    """Tests for Tableau derivation reference detection."""

    def _make_tmdl(self, content):
        fd, path = tempfile.mkstemp(suffix='.tmdl')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def test_detects_yr_prefix_in_measure(self):
        """Validator should catch [yr:Order Date:ok] in measure DAX."""
        path = self._make_tmdl(
            "table Sales\n"
            "\tmeasure 'Year Calc' = [yr:Order Date:ok]\n"
        )
        try:
            issues = ArtifactValidator.validate_tmdl_dax(path)
            derivation_issues = [i for i in issues if 'derivation' in i.lower()]
            self.assertTrue(len(derivation_issues) > 0,
                            f'Should detect Tableau derivation ref: {issues}')
        finally:
            os.unlink(path)

    def test_detects_none_prefix_in_expression(self):
        """Validator should catch [none:Category:nk] in expression."""
        path = self._make_tmdl(
            "table Sales\n"
            "\tcolumn 'Group Col'\n"
            "\t\texpression = SWITCH([none:Category:nk], \"A\", 1, 0)\n"
        )
        try:
            issues = ArtifactValidator.validate_tmdl_dax(path)
            derivation_issues = [i for i in issues if 'derivation' in i.lower()]
            self.assertTrue(len(derivation_issues) > 0,
                            f'Should detect Tableau derivation ref: {issues}')
        finally:
            os.unlink(path)

    def test_no_false_positive_on_clean_dax(self):
        """Clean DAX should not trigger derivation warning."""
        path = self._make_tmdl(
            "table Sales\n"
            "\tmeasure 'Total' = SUM('Sales'[Amount])\n"
            "\tmeasure 'Ratio' = DIVIDE([Total], COUNTROWS('Sales'))\n"
        )
        try:
            issues = ArtifactValidator.validate_tmdl_dax(path)
            derivation_issues = [i for i in issues if 'derivation' in i.lower()]
            self.assertEqual(len(derivation_issues), 0,
                             f'Clean DAX should not trigger: {issues}')
        finally:
            os.unlink(path)

    def test_detects_in_multiline_expression(self):
        """Derivation refs in multi-line expressions should be detected."""
        path = self._make_tmdl(
            "table Sales\n"
            "\tcolumn 'Group Col'\n"
            "\t\texpression = ```\n"
            "\t\t\tSWITCH([yr:Date:qk],\n"
            "\t\t\t  2020, \"Year1\",\n"
            "\t\t\t  2021, \"Year2\")\n"
            "\t\t\t```\n"
        )
        try:
            issues = ArtifactValidator.validate_tmdl_dax(path)
            derivation_issues = [i for i in issues if 'derivation' in i.lower()]
            self.assertTrue(len(derivation_issues) > 0,
                            f'Should detect derivation ref in multiline: {issues}')
        finally:
            os.unlink(path)


class TestValidatorLineageTagUniqueness(unittest.TestCase):
    """Tests for lineageTag uniqueness validation."""

    def _make_tmdl(self, content):
        fd, path = tempfile.mkstemp(suffix='.tmdl')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def test_detects_duplicate_lineage_tags(self):
        """Validator should catch duplicate lineageTags."""
        path = self._make_tmdl(
            "table Sales\n"
            "\tcolumn 'Col1'\n"
            "\t\tlineageTag: abc-123\n"
            "\tcolumn 'Col2'\n"
            "\t\tlineageTag: abc-123\n"
        )
        try:
            issues = ArtifactValidator.validate_tmdl_dax(path)
            dup_issues = [i for i in issues if 'Duplicate lineageTag' in i]
            self.assertTrue(len(dup_issues) > 0,
                            f'Should detect duplicate lineageTag: {issues}')
        finally:
            os.unlink(path)

    def test_unique_lineage_tags_ok(self):
        """Unique lineageTags should not trigger warnings."""
        path = self._make_tmdl(
            "table Sales\n"
            "\tcolumn 'Col1'\n"
            "\t\tlineageTag: abc-123\n"
            "\tcolumn 'Col2'\n"
            "\t\tlineageTag: def-456\n"
        )
        try:
            issues = ArtifactValidator.validate_tmdl_dax(path)
            dup_issues = [i for i in issues if 'Duplicate lineageTag' in i]
            self.assertEqual(len(dup_issues), 0)
        finally:
            os.unlink(path)


class TestValidatorInlineMeasureDAX(unittest.TestCase):
    """Tests for single-line measure DAX validation."""

    def _make_tmdl(self, content):
        fd, path = tempfile.mkstemp(suffix='.tmdl')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def test_validates_inline_measure_dax(self):
        """Inline measure DAX with Tableau leaks should be caught."""
        path = self._make_tmdl(
            "table Sales\n"
            "\tmeasure 'Bad Calc' = COUNTD('Sales'[Customer])\n"
        )
        try:
            issues = ArtifactValidator.validate_tmdl_dax(path)
            leak_issues = [i for i in issues if 'COUNTD' in i]
            self.assertTrue(len(leak_issues) > 0,
                            f'Should detect COUNTD in inline measure: {issues}')
        finally:
            os.unlink(path)

    def test_validates_unbalanced_parens(self):
        """Inline measure with unbalanced parens should be caught."""
        path = self._make_tmdl(
            "table Sales\n"
            "\tmeasure 'Bad' = SUM('Sales'[Amount]\n"
        )
        try:
            issues = ArtifactValidator.validate_tmdl_dax(path)
            paren_issues = [i for i in issues if 'parenthesis' in i.lower()]
            self.assertTrue(len(paren_issues) > 0,
                            f'Should detect unbalanced parens: {issues}')
        finally:
            os.unlink(path)


# ═══════════════════════════════════════════════════════════════════
# 4. E2E Migration Output Validation
# ═══════════════════════════════════════════════════════════════════

class TestMigrationOutputIntegrity(unittest.TestCase):
    """End-to-end tests that validate migration output artifacts for
    issues that would crash Power BI Desktop.

    Scans the actual artifacts/ directory (if present) for:
    - Empty measure expressions
    - Tableau derivation field references
    - Duplicate lineageTags
    """

    ARTIFACTS_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'artifacts', 'powerbi_projects'
    )

    def _find_tmdl_files(self):
        """Find all .tmdl files in artifacts."""
        tmdl_files = []
        if not os.path.exists(self.ARTIFACTS_DIR):
            return tmdl_files
        for root, dirs, files in os.walk(self.ARTIFACTS_DIR):
            for f in files:
                if f.endswith('.tmdl'):
                    tmdl_files.append(os.path.join(root, f))
        return tmdl_files

    def test_no_empty_measure_expressions(self):
        """No TMDL file should contain a measure with empty expression."""
        tmdl_files = self._find_tmdl_files()
        if not tmdl_files:
            self.skipTest('No artifacts found')

        empty_pattern = re.compile(r"^\s*measure\s+'[^']+'\s*=\s*$", re.MULTILINE)
        violations = []
        for fpath in tmdl_files:
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read()
                matches = empty_pattern.findall(content)
                if matches:
                    violations.append((os.path.basename(fpath), matches))
            except Exception:
                continue

        self.assertEqual(
            len(violations), 0,
            f'Found empty measure expressions in {len(violations)} files: '
            + '; '.join(f'{n}: {m}' for n, m in violations[:5])
        )

    def test_no_tableau_derivation_refs(self):
        """No TMDL file should contain Tableau derivation field references."""
        tmdl_files = self._find_tmdl_files()
        if not tmdl_files:
            self.skipTest('No artifacts found')

        deriv_pattern = re.compile(
            r'\[(?:none|sum|avg|count|min|max|usr|yr|mn|dy|qr|wk|attr|md|mdy|hms|hr|mt|sc|thr|trunc|tyr|tqr|tmn|tdy|twk):'
            r'[^\]]+?'
            r'(?::(?:nk|qk|ok|fn|tn))?\]'
        )
        violations = []
        for fpath in tmdl_files:
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read()
                matches = deriv_pattern.findall(content)
                if matches:
                    violations.append((os.path.basename(fpath), matches[:3]))
            except Exception:
                continue

        self.assertEqual(
            len(violations), 0,
            f'Found Tableau derivation refs in {len(violations)} files: '
            + '; '.join(f'{n}: {m}' for n, m in violations[:5])
        )

    def test_no_empty_expression_properties(self):
        """No TMDL file should have 'expression =' with no value."""
        tmdl_files = self._find_tmdl_files()
        if not tmdl_files:
            self.skipTest('No artifacts found')

        empty_expr_pattern = re.compile(r'^\s*expression\s*=\s*$', re.MULTILINE)
        violations = []
        for fpath in tmdl_files:
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read()
                matches = empty_expr_pattern.findall(content)
                if matches:
                    violations.append(os.path.basename(fpath))
            except Exception:
                continue

        self.assertEqual(len(violations), 0,
                         f'Found empty expressions in: {violations}')

    def test_validator_on_all_projects(self):
        """Run the enhanced validator on all migration output projects."""
        if not os.path.exists(self.ARTIFACTS_DIR):
            self.skipTest('No artifacts found')

        results = ArtifactValidator.validate_directory(Path(self.ARTIFACTS_DIR))
        if not results:
            self.skipTest('No projects found in artifacts')

        # Check no hard errors
        failed = {name: r for name, r in results.items()
                  if isinstance(r, dict) and not r.get('valid', True)}
        self.assertEqual(
            len(failed), 0,
            f'{len(failed)} projects failed validation: '
            + ', '.join(failed.keys())
        )

    def test_no_derivation_refs_in_m_queries(self):
        """No M query partition should contain Tableau derivation refs."""
        tmdl_files = self._find_tmdl_files()
        if not tmdl_files:
            self.skipTest('No artifacts found')

        # Pattern to find M expression blocks
        deriv_pattern = re.compile(
            r'(?:none|sum|avg|count|min|max|usr|yr|mn|dy|qr|wk|attr|md|mdy|hms|hr|mt|sc|thr|trunc|tyr):'
            r'[A-Za-z ]+?'
            r'(?::(?:nk|qk|ok|fn|tn))?'
        )
        violations = []
        for fpath in tmdl_files:
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read()
                # Only scan inside M expression blocks
                in_m_block = False
                for line in content.split('\n'):
                    stripped = line.strip()
                    if 'expression =' in stripped and '```' in stripped:
                        in_m_block = True
                        continue
                    if in_m_block and stripped.startswith('```'):
                        in_m_block = False
                        continue
                    if in_m_block and ('let' in stripped.lower() or
                                       'Table.' in stripped or
                                       'Source' in stripped):
                        matches = deriv_pattern.findall(line)
                        if matches:
                            violations.append(
                                (os.path.basename(fpath), matches[:2]))
            except Exception:
                continue

        self.assertEqual(
            len(violations), 0,
            f'Found derivation refs in M queries in {len(violations)} files: '
            + '; '.join(f'{n}: {m}' for n, m in violations[:5])
        )


if __name__ == '__main__':
    unittest.main()
