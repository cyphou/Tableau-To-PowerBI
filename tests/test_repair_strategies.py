"""Sprint 130.4 — Tests for powerbi_import.repair_strategies."""

import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from powerbi_import.repair_strategies import (
    RepairResult,
    RepairStrategy,
    RepairRegistry,
    balanced_paren_strategy,
    tableau_leak_strip_strategy,
    parameter_resolution_strategy,
    llm_dax_repair_strategy,
    default_dax_registry,
    default_m_registry,
)
from powerbi_import.recovery_report import RecoveryReport


# ── Helpers ──────────────────────────────────────────────────────────


def _paren_validator(text):
    depth = 0
    for ch in text:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth < 0:
                return ['unmatched closing paren']
    if depth > 0:
        return [f'unmatched opening paren ({depth} unclosed)']
    return []


# ── balanced_paren_strategy ─────────────────────────────────────────


class TestBalancedParenStrategy(unittest.TestCase):

    def test_repairs_missing_close(self):
        ctx = {'validator': _paren_validator}
        res = balanced_paren_strategy.attempt(
            'SUM([X]', ['unmatched opening paren (1 unclosed)'], ctx
        )
        self.assertEqual(res.status, 'repaired')
        self.assertEqual(res.artifact, 'SUM([X])')
        self.assertIn('appended', res.notes)

    def test_repairs_two_missing_closes(self):
        ctx = {'validator': _paren_validator}
        res = balanced_paren_strategy.attempt(
            'CALCULATE(SUM([X])', ['unmatched opening paren (1 unclosed)'], ctx
        )
        self.assertEqual(res.status, 'repaired')
        self.assertTrue(res.artifact.endswith(')'))

    def test_unchanged_when_balanced(self):
        ctx = {'validator': _paren_validator}
        res = balanced_paren_strategy.attempt('SUM([X])', [], ctx)
        self.assertEqual(res.status, 'unchanged')

    def test_does_not_apply_when_other_issues(self):
        # If there's a non-paren issue, the strategy refuses to touch it
        ctx = {'validator': _paren_validator}
        res = balanced_paren_strategy.attempt(
            'IFNULL([X], 0', ['Tableau function leak: IFNULL',
                              'unmatched opening paren'], ctx
        )
        self.assertEqual(res.status, 'unchanged')


# ── tableau_leak_strip_strategy ─────────────────────────────────────


class TestTableauLeakStripStrategy(unittest.TestCase):

    def _no_op_validator(self, text):
        return []

    def test_strips_attr(self):
        ctx = {'validator': self._no_op_validator}
        res = tableau_leak_strip_strategy.attempt(
            'SUM(ATTR([Region]))',
            ['Tableau function leak: ATTR'],
            ctx,
        )
        self.assertEqual(res.status, 'repaired')
        self.assertNotIn('ATTR', res.artifact)
        self.assertIn('[Region]', res.artifact)

    def test_rewrites_ifnull(self):
        ctx = {'validator': self._no_op_validator}
        res = tableau_leak_strip_strategy.attempt(
            'IFNULL([Sales], 0)',
            ['Tableau function leak: IFNULL'],
            ctx,
        )
        self.assertEqual(res.status, 'repaired')
        self.assertIn('IF(ISBLANK', res.artifact)
        self.assertNotIn('IFNULL', res.artifact)

    def test_rewrites_zn(self):
        ctx = {'validator': self._no_op_validator}
        res = tableau_leak_strip_strategy.attempt(
            'ZN([Sales])',
            ['Tableau function leak: ZN'],
            ctx,
        )
        self.assertEqual(res.status, 'repaired')
        self.assertIn('IF(ISBLANK', res.artifact)
        self.assertIn(', 0,', res.artifact)

    def test_unchanged_when_no_leak_issue(self):
        ctx = {'validator': self._no_op_validator}
        res = tableau_leak_strip_strategy.attempt('SUM([X])', [], ctx)
        self.assertEqual(res.status, 'unchanged')


# ── parameter_resolution_strategy ────────────────────────────────────


class TestParameterResolutionStrategy(unittest.TestCase):

    def _ok(self, _):
        return []

    def test_inlines_string_param(self):
        ctx = {'validator': self._ok, 'parameters': {'Region': 'EMEA'}}
        res = parameter_resolution_strategy.attempt(
            'IF([Region] = [Parameters].[Region], 1, 0)',
            ['Unresolved parameter reference: [Parameters].[Region]'],
            ctx,
        )
        self.assertEqual(res.status, 'repaired')
        self.assertIn('"EMEA"', res.artifact)
        self.assertNotIn('[Parameters]', res.artifact)

    def test_inlines_numeric_param(self):
        ctx = {'validator': self._ok, 'parameters': {'Threshold': 100}}
        res = parameter_resolution_strategy.attempt(
            'IF([X] > [Parameters].[Threshold], 1, 0)',
            ['Unresolved parameter reference'],
            ctx,
        )
        self.assertEqual(res.status, 'repaired')
        self.assertIn('100', res.artifact)

    def test_escapes_quotes_in_string_param(self):
        ctx = {'validator': self._ok,
               'parameters': {'Label': 'with "quote"'}}
        res = parameter_resolution_strategy.attempt(
            '[Parameters].[Label]',
            ['Unresolved parameter reference'],
            ctx,
        )
        self.assertEqual(res.status, 'repaired')
        # DAX escapes inner " by doubling
        self.assertIn('""quote""', res.artifact)

    def test_unchanged_when_no_param_in_context(self):
        ctx = {'validator': self._ok, 'parameters': {}}
        res = parameter_resolution_strategy.attempt(
            '[Parameters].[X]',
            ['Unresolved parameter reference'],
            ctx,
        )
        self.assertEqual(res.status, 'unchanged')


# ── LLM repair (mocked client) ──────────────────────────────────────


class TestLLMRepairStrategy(unittest.TestCase):

    def _ok(self, _):
        return []

    def test_uses_llm_when_client_present(self):
        client = MagicMock()
        client.call.return_value = {
            'text': 'SUM([X])', 'cost': 0.01, 'input_tokens': 10,
            'output_tokens': 5,
        }
        ctx = {'validator': self._ok, 'llm_client': client}
        res = llm_dax_repair_strategy.attempt(
            'SUM([X]', ['unmatched opening paren'], ctx
        )
        client.call.assert_called_once()
        self.assertEqual(res.status, 'repaired')
        self.assertEqual(res.artifact, 'SUM([X])')
        self.assertEqual(res.cost, 0.01)

    def test_strips_markdown_fences(self):
        client = MagicMock()
        client.call.return_value = {
            'text': '```dax\nSUM([X])\n```', 'cost': 0.005,
            'input_tokens': 10, 'output_tokens': 5,
        }
        ctx = {'validator': self._ok, 'llm_client': client}
        res = llm_dax_repair_strategy.attempt(
            'SUM([X]', ['paren'], ctx
        )
        self.assertEqual(res.status, 'repaired')
        self.assertEqual(res.artifact, 'SUM([X])')
        self.assertNotIn('```', res.artifact)

    def test_unchanged_without_client(self):
        ctx = {'validator': self._ok}  # no llm_client
        res = llm_dax_repair_strategy.attempt(
            'SUM([X]', ['paren'], ctx
        )
        self.assertEqual(res.status, 'unchanged')

    def test_handles_llm_error(self):
        client = MagicMock()
        client.call.return_value = {
            'text': '', 'error': 'http_500', 'cost': 0,
            'input_tokens': 0, 'output_tokens': 0,
        }
        ctx = {'validator': self._ok, 'llm_client': client}
        res = llm_dax_repair_strategy.attempt(
            'SUM([X]', ['paren'], ctx
        )
        self.assertEqual(res.status, 'unchanged')
        self.assertIn('LLM error', res.notes)

    def test_rejected_when_llm_output_still_invalid(self):
        client = MagicMock()
        client.call.return_value = {
            'text': 'SUM([X]', 'cost': 0.01,  # Still missing close paren
            'input_tokens': 10, 'output_tokens': 5,
        }
        # Validator rejects unbalanced parens
        ctx = {'validator': _paren_validator, 'llm_client': client}
        # But LLM returned same as input — strategy returns unchanged
        res = llm_dax_repair_strategy.attempt(
            'SUM([X]', ['paren'], ctx
        )
        self.assertEqual(res.status, 'unchanged')


# ── Strategy base class ──────────────────────────────────────────────


class TestStrategyBase(unittest.TestCase):

    def test_strategy_never_raises(self):
        def boom(_a, _i, _c):
            raise RuntimeError('intentional')
        s = RepairStrategy('boom', boom)
        ctx = {'validator': _paren_validator}
        res = s.attempt('SUM([X]', ['paren'], ctx)
        self.assertEqual(res.status, 'error')
        self.assertIn('intentional', res.notes)


# ── Registry orchestration ───────────────────────────────────────────


class TestRegistryOrdering(unittest.TestCase):

    def test_deterministic_runs_before_llm(self):
        order = []
        def det_fn(a, _i, _c):
            order.append('det')
            return a, ''  # no-op
        def llm_fn(a, _i, _c):
            order.append('llm')
            return a, ''
        det = RepairStrategy('det', det_fn,
                             category=RepairStrategy.DETERMINISTIC)
        llm = RepairStrategy('llm', llm_fn, category=RepairStrategy.LLM)
        # Insert LLM first to prove it gets reordered
        reg = RepairRegistry([llm, det])
        reg.run('SUM([X]', ['paren'], {'validator': _paren_validator})
        self.assertEqual(order, ['det', 'llm'])

    def test_stops_at_first_success(self):
        order = []
        def succeed(a, _i, _c):
            order.append('succeed')
            return a + ')', 'closed'
        def never(a, _i, _c):
            order.append('never')
            return a, ''
        s1 = RepairStrategy('succeed', succeed)
        s2 = RepairStrategy('never', never)
        reg = RepairRegistry([s1, s2])
        results = reg.run('SUM([X]',
                          ['unmatched opening paren'],
                          {'validator': _paren_validator})
        self.assertEqual(order, ['succeed'])
        self.assertEqual(results[-1].status, 'repaired')

    def test_records_to_recovery_report(self):
        report = RecoveryReport('test_wb')
        ctx = {'validator': _paren_validator, 'artifact_kind': 'dax'}
        reg = default_dax_registry()
        reg.run('SUM([X]', ['unmatched opening paren'], ctx,
                recovery_report=report, item_name='Measure1')
        self.assertTrue(report.has_repairs)
        # At least one recorded with item_name
        self.assertTrue(
            any(r.get('item_name') == 'Measure1' for r in report.repairs)
        )


# ── Default registries ──────────────────────────────────────────────


class TestDefaultRegistries(unittest.TestCase):

    def test_default_dax_registry_no_llm(self):
        reg = default_dax_registry()
        names = [s.name for s in reg.strategies]
        self.assertIn('balanced_paren', names)
        self.assertIn('tableau_leak_strip', names)
        self.assertNotIn('llm_dax_repair', names)

    def test_default_dax_registry_with_llm(self):
        client = MagicMock()
        reg = default_dax_registry(llm_client=client)
        names = [s.name for s in reg.strategies]
        self.assertIn('llm_dax_repair', names)

    def test_default_m_registry(self):
        reg = default_m_registry()
        self.assertEqual(len(reg.strategies), 1)
        self.assertEqual(reg.strategies[0].applies_to, 'm')


# ── End-to-end repair scenarios ──────────────────────────────────────


class TestEndToEnd(unittest.TestCase):

    def test_full_chain_repairs_paren_then_done(self):
        ctx = {'validator': _paren_validator, 'artifact_kind': 'dax'}
        reg = default_dax_registry()
        results = reg.run('SUM([X]', _paren_validator('SUM([X]'), ctx)
        winner = results[-1]
        self.assertEqual(winner.status, 'repaired')
        self.assertEqual(winner.artifact, 'SUM([X])')

    def test_unrepairable_returns_no_success(self):
        # No strategy in default registry handles a Tableau LOD braces
        ctx = {'validator': _paren_validator, 'artifact_kind': 'dax'}
        reg = default_dax_registry()
        artifact = '{FIXED [Region] : SUM([Sales])}'
        # Validator passes (parens balance) but artifact is "wrong" —
        # the registry has nothing to do.
        results = reg.run(artifact, [], ctx)
        # All strategies report unchanged
        self.assertTrue(all(r.status == 'unchanged' for r in results))


if __name__ == '__main__':
    unittest.main()
