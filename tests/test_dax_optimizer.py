"""Tests for Sprint 93 — Semantic DAX Optimization.

Covers:
- DAX optimizer rules (ISBLANK→COALESCE, nested IF→SWITCH, redundant CALCULATE,
  constant folding, SUMX simplification, whitespace normalization)
- Time Intelligence auto-injection (YTD, PY, YoY%)
- Measure dependency DAG (edges, circular refs, unused, roots)
- Optimization report generation
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))


class TestISBLANKToCoalesce(unittest.TestCase):
    """Tests for IF(ISBLANK(x),...) → COALESCE conversion."""

    def test_basic_isblank_coalesce(self):
        from powerbi_import.dax_optimizer import optimize_dax
        formula = 'IF(ISBLANK([Sales]), 0, [Sales])'
        opt, rules = optimize_dax(formula)
        self.assertIn('COALESCE', opt)
        self.assertNotIn('ISBLANK', opt)
        self.assertIn('isblank_coalesce', rules)

    def test_isblank_reverse_branch(self):
        from powerbi_import.dax_optimizer import optimize_dax
        formula = 'IF(ISBLANK([X]), [X], 100)'
        opt, rules = optimize_dax(formula)
        self.assertIn('COALESCE', opt)

    def test_no_change_for_different_branches(self):
        from powerbi_import.dax_optimizer import optimize_dax
        formula = 'IF(ISBLANK([A]), [B], [C])'
        opt, rules = optimize_dax(formula)
        # Neither branch matches the ISBLANK argument, so no COALESCE
        self.assertNotIn('isblank_coalesce', rules)

    def test_empty_formula(self):
        from powerbi_import.dax_optimizer import optimize_dax
        opt, rules = optimize_dax('')
        self.assertEqual(opt, '')
        self.assertEqual(rules, [])

    def test_none_formula(self):
        from powerbi_import.dax_optimizer import optimize_dax
        opt, rules = optimize_dax(None)
        self.assertIsNone(opt)


class TestNestedIFToSwitch(unittest.TestCase):
    """Tests for nested IF → SWITCH conversion."""

    def test_three_level_if_to_switch(self):
        from powerbi_import.dax_optimizer import optimize_dax
        formula = 'IF([Status] = "A", 1, IF([Status] = "B", 2, IF([Status] = "C", 3, 0)))'
        opt, rules = optimize_dax(formula)
        self.assertIn('SWITCH', opt)
        self.assertIn('nested_if_to_switch', rules)
        self.assertIn('"A"', opt)
        self.assertIn('"B"', opt)
        self.assertIn('"C"', opt)

    def test_two_level_if_stays(self):
        """Two-level IF doesn't necessarily convert — needs 3+ cases."""
        from powerbi_import.dax_optimizer import optimize_dax
        formula = 'IF([X] = 1, "a", IF([X] = 2, "b", "c"))'
        opt, rules = optimize_dax(formula)
        # Two cases may or may not convert — but should not error
        self.assertIsNotNone(opt)

    def test_different_fields_no_switch(self):
        from powerbi_import.dax_optimizer import optimize_dax
        formula = 'IF([A] = 1, "x", IF([B] = 2, "y", "z"))'
        opt, rules = optimize_dax(formula)
        # Different fields → can't become SWITCH
        self.assertNotIn('nested_if_to_switch', rules)


class TestRedundantCalculate(unittest.TestCase):
    """Tests for CALCULATE(AGG(x)) → AGG(x) simplification."""

    def test_calculate_sum(self):
        from powerbi_import.dax_optimizer import optimize_dax
        formula = 'CALCULATE(SUM([Sales]))'
        opt, rules = optimize_dax(formula)
        self.assertEqual(opt, 'SUM([Sales])')
        self.assertIn('redundant_calculate', rules)

    def test_calculate_with_filter_preserved(self):
        from powerbi_import.dax_optimizer import optimize_dax
        formula = 'CALCULATE(SUM([Sales]), FILTER(ALL(Sales), [Region] = "West"))'
        opt, rules = optimize_dax(formula)
        # With filter argument → should NOT be simplified
        self.assertNotIn('redundant_calculate', rules)


class TestConstantFolding(unittest.TestCase):
    """Tests for constant arithmetic folding."""

    def test_addition(self):
        from powerbi_import.dax_optimizer import optimize_dax
        formula = '10 + 5'
        opt, rules = optimize_dax(formula)
        self.assertEqual(opt, '15')
        self.assertIn('constant_fold', rules)

    def test_multiplication(self):
        from powerbi_import.dax_optimizer import optimize_dax
        formula = '6 * 7'
        opt, rules = optimize_dax(formula)
        self.assertEqual(opt, '42')

    def test_subtraction(self):
        from powerbi_import.dax_optimizer import optimize_dax
        formula = '100 - 30'
        opt, rules = optimize_dax(formula)
        self.assertEqual(opt, '70')

    def test_integer_division(self):
        from powerbi_import.dax_optimizer import optimize_dax
        formula = '100 / 5'
        opt, rules = optimize_dax(formula)
        self.assertEqual(opt, '20')

    def test_non_integer_division_preserved(self):
        from powerbi_import.dax_optimizer import optimize_dax
        formula = '10 / 3'
        opt, rules = optimize_dax(formula)
        self.assertEqual(opt, '10 / 3')  # Not evenly divisible


class TestSumxSimplification(unittest.TestCase):
    """Tests for SUMX('T', 'T'[Col]) → SUM('T'[Col])."""

    def test_basic_sumx(self):
        from powerbi_import.dax_optimizer import optimize_dax
        formula = "SUMX('Orders', 'Orders'[Amount])"
        opt, rules = optimize_dax(formula)
        self.assertEqual(opt, "SUM('Orders'[Amount])")
        self.assertIn('simplify_sumx', rules)

    def test_sumx_different_tables_preserved(self):
        from powerbi_import.dax_optimizer import optimize_dax
        formula = "SUMX('Orders', 'Products'[Price])"
        opt, rules = optimize_dax(formula)
        self.assertNotIn('simplify_sumx', rules)


class TestWhitespace(unittest.TestCase):
    """Tests for whitespace normalization."""

    def test_double_spaces(self):
        from powerbi_import.dax_optimizer import optimize_dax
        formula = 'SUM(  [Sales]  )'
        opt, rules = optimize_dax(formula)
        self.assertNotIn('  ', opt)

    def test_leading_trailing(self):
        from powerbi_import.dax_optimizer import optimize_dax
        formula = '  SUM([A])  '
        opt, rules = optimize_dax(formula)
        self.assertEqual(opt, 'SUM([A])')


class TestRuleSetSelection(unittest.TestCase):
    """Tests for selective rule application."""

    def test_only_coalesce_rule(self):
        from powerbi_import.dax_optimizer import optimize_dax
        formula = 'IF(ISBLANK([X]), 0, [X])'
        opt, rules = optimize_dax(formula, rule_set=['isblank_coalesce'])
        self.assertIn('isblank_coalesce', rules)
        self.assertNotIn('trim_whitespace', rules)

    def test_no_matching_rules(self):
        from powerbi_import.dax_optimizer import optimize_dax
        formula = 'SUM([Sales])'
        opt, rules = optimize_dax(formula, rule_set=['nonexistent_rule'])
        self.assertEqual(opt, formula)
        self.assertEqual(rules, [])


class TestTimeIntelligence(unittest.TestCase):
    """Tests for Time Intelligence auto-injection."""

    def test_generate_ti_for_sum_measure(self):
        from powerbi_import.dax_optimizer import generate_time_intelligence_measures
        measures = [{'name': 'Total Sales', 'expression': "SUM('Sales'[Amount])"}]
        ti = generate_time_intelligence_measures(measures)
        self.assertEqual(len(ti), 3)
        names = [m['name'] for m in ti]
        self.assertIn('Total Sales YTD', names)
        self.assertIn('Total Sales PY', names)
        self.assertIn('Total Sales YoY %', names)

    def test_ti_uses_totalytd(self):
        from powerbi_import.dax_optimizer import generate_time_intelligence_measures
        measures = [{'name': 'Revenue', 'expression': "SUM('T'[Rev])"}]
        ti = generate_time_intelligence_measures(measures)
        ytd = next(m for m in ti if 'YTD' in m['name'])
        self.assertIn('TOTALYTD', ytd['expression'])

    def test_ti_uses_sameperiodlastyear(self):
        from powerbi_import.dax_optimizer import generate_time_intelligence_measures
        measures = [{'name': 'Rev', 'expression': "SUM('T'[Amount])"}]
        ti = generate_time_intelligence_measures(measures)
        py = next(m for m in ti if ' PY' in m['name'])
        self.assertIn('SAMEPERIODLASTYEAR', py['expression'])

    def test_no_ti_for_non_agg_measures(self):
        from powerbi_import.dax_optimizer import generate_time_intelligence_measures
        measures = [{'name': 'Ratio', 'expression': '[A] / [B]'}]
        ti = generate_time_intelligence_measures(measures)
        self.assertEqual(len(ti), 0)

    def test_ti_display_folder(self):
        from powerbi_import.dax_optimizer import generate_time_intelligence_measures
        measures = [{'name': 'X', 'expression': "COUNT('T'[ID])"}]
        ti = generate_time_intelligence_measures(measures)
        for m in ti:
            self.assertEqual(m['displayFolder'], 'Time Intelligence')

    def test_custom_date_column(self):
        from powerbi_import.dax_optimizer import generate_time_intelligence_measures
        measures = [{'name': 'Sales', 'expression': "SUM('Fact'[Amount])"}]
        ti = generate_time_intelligence_measures(measures, date_column="'DateDim'[DateKey]")
        ytd = next(m for m in ti if 'YTD' in m['name'])
        self.assertIn("'DateDim'[DateKey]", ytd['expression'])


class TestMeasureDependencyDAG(unittest.TestCase):
    """Tests for measure dependency graph construction."""

    def test_basic_dependency(self):
        from powerbi_import.dax_optimizer import build_measure_dependency_dag
        measures = [
            {'name': 'Sales', 'expression': "SUM('T'[Amount])"},
            {'name': 'Profit', 'expression': '[Sales] - [Cost]'},
            {'name': 'Cost', 'expression': "SUM('T'[Cost])"},
        ]
        dag = build_measure_dependency_dag(measures)
        self.assertIn(('Profit', 'Sales'), dag['edges'])
        self.assertIn(('Profit', 'Cost'), dag['edges'])

    def test_unused_measures(self):
        from powerbi_import.dax_optimizer import build_measure_dependency_dag
        measures = [
            {'name': 'A', 'expression': "SUM('T'[X])"},
            {'name': 'B', 'expression': '[A] + 1'},
        ]
        dag = build_measure_dependency_dag(measures)
        self.assertIn('B', dag['unused'])  # B not referenced by anything
        self.assertNotIn('A', dag['unused'])  # A referenced by B

    def test_root_measures(self):
        from powerbi_import.dax_optimizer import build_measure_dependency_dag
        measures = [
            {'name': 'Base', 'expression': "SUM('T'[V])"},
            {'name': 'Derived', 'expression': '[Base] * 2'},
        ]
        dag = build_measure_dependency_dag(measures)
        self.assertIn('Base', dag['roots'])

    def test_circular_detection(self):
        from powerbi_import.dax_optimizer import build_measure_dependency_dag
        measures = [
            {'name': 'X', 'expression': '[Y] + 1'},
            {'name': 'Y', 'expression': '[X] - 1'},
        ]
        dag = build_measure_dependency_dag(measures)
        self.assertTrue(len(dag['circular']) > 0)

    def test_empty_measures(self):
        from powerbi_import.dax_optimizer import build_measure_dependency_dag
        dag = build_measure_dependency_dag([])
        self.assertEqual(dag['edges'], [])
        self.assertEqual(dag['circular'], [])
        self.assertEqual(dag['unused'], [])
        self.assertEqual(dag['roots'], [])


class TestOptimizationReport(unittest.TestCase):
    """Tests for optimization report generation."""

    def test_report_structure(self):
        from powerbi_import.dax_optimizer import generate_optimization_report
        measures = [
            {'name': 'Sales', 'expression': 'IF(ISBLANK([X]), 0, [X])'},
            {'name': 'Cost', 'expression': "SUM('T'[Cost])"},
        ]
        report = generate_optimization_report(measures)
        self.assertEqual(report['total_measures'], 2)
        self.assertGreater(report['optimized_count'], 0)
        self.assertEqual(len(report['measures']), 2)

    def test_report_writes_json(self):
        from powerbi_import.dax_optimizer import generate_optimization_report
        measures = [{'name': 'M1', 'expression': '10 + 5'}]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'report.json')
            report = generate_optimization_report(measures, output_path=path)
            self.assertTrue(os.path.exists(path))
            with open(path) as f:
                data = json.load(f)
            self.assertEqual(data['total_measures'], 1)

    def test_report_per_measure_details(self):
        from powerbi_import.dax_optimizer import generate_optimization_report
        measures = [{'name': 'M', 'expression': 'CALCULATE(SUM([A]))'}]
        report = generate_optimization_report(measures)
        entry = report['measures'][0]
        self.assertEqual(entry['name'], 'M')
        self.assertTrue(entry['changed'])
        self.assertIn('redundant_calculate', entry['rules_applied'])

    def test_unchanged_measure_in_report(self):
        from powerbi_import.dax_optimizer import generate_optimization_report
        measures = [{'name': 'Clean', 'expression': "SUM('T'[X])"}]
        report = generate_optimization_report(measures)
        self.assertEqual(report['optimized_count'], 0)
        self.assertFalse(report['measures'][0]['changed'])


class TestCLIFlags(unittest.TestCase):
    """Tests for --optimize-dax and --time-intelligence CLI arguments."""

    def test_optimize_dax_flag_exists(self):
        import migrate
        parser = migrate._build_argument_parser()
        args = parser.parse_args(['test.twbx', '--optimize-dax'])
        self.assertTrue(args.optimize_dax)

    def test_time_intelligence_auto(self):
        import migrate
        parser = migrate._build_argument_parser()
        args = parser.parse_args(['test.twbx', '--time-intelligence', 'auto'])
        self.assertEqual(args.time_intelligence, 'auto')

    def test_time_intelligence_default_none(self):
        import migrate
        parser = migrate._build_argument_parser()
        args = parser.parse_args(['test.twbx'])
        self.assertEqual(args.time_intelligence, 'none')


if __name__ == '__main__':
    unittest.main()
