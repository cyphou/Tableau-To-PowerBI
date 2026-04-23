"""Tests for powerbi_import.llm_client (Sprint 112).

Covers: provider config, token estimation, schema context, MigrationNote
extraction, dry-run mode, retry logic, multi-provider request bodies,
DAX syntax validation gate (112.4), refinement pipeline targeting,
markdown-fence stripping, cost tracking, and report generation.

All HTTP is mocked at urllib.request.urlopen — no live API calls.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

# Ensure project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from powerbi_import.llm_client import (
    LLMClient,
    estimate_tokens,
    refine_approximated_measures,
    generate_llm_report,
    _build_schema_context,
    _extract_migration_note,
    _validate_refined_dax,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _mock_openai_response(text, in_tokens=10, out_tokens=20):
    """Build an OpenAI-format mock urlopen response."""
    payload = {
        'choices': [{'message': {'content': text}}],
        'usage': {'prompt_tokens': in_tokens, 'completion_tokens': out_tokens},
    }
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode('utf-8')
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _mock_anthropic_response(text, in_tokens=10, out_tokens=20):
    payload = {
        'content': [{'text': text}],
        'usage': {'input_tokens': in_tokens, 'output_tokens': out_tokens},
    }
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode('utf-8')
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ── Token estimation ────────────────────────────────────────────────


class TestEstimateTokens(unittest.TestCase):

    def test_empty(self):
        self.assertEqual(estimate_tokens(''), 0)
        self.assertEqual(estimate_tokens(None), 0)

    def test_short(self):
        # "hello" is 5 chars → max(1, 1) = 1
        self.assertEqual(estimate_tokens('hello'), 1)

    def test_long(self):
        text = 'x' * 400  # ~100 tokens
        self.assertEqual(estimate_tokens(text), 100)


# ── Client construction & configuration ─────────────────────────────


class TestLLMClientConstruction(unittest.TestCase):

    def test_default_openai(self):
        c = LLMClient(api_key='sk-test')
        self.assertEqual(c.provider, 'openai')
        self.assertEqual(c.model, 'gpt-4o')
        self.assertEqual(c.calls_remaining, 100)

    def test_anthropic(self):
        c = LLMClient(provider='anthropic', api_key='sk-ant')
        self.assertEqual(c.model, 'claude-sonnet-4-20250514')

    def test_unknown_provider_raises(self):
        with self.assertRaises(ValueError):
            LLMClient(provider='bogus', api_key='x')

    def test_azure_requires_endpoint(self):
        with self.assertRaises(ValueError):
            LLMClient(provider='azure_openai', api_key='x')

    def test_azure_with_endpoint(self):
        c = LLMClient(provider='azure_openai', api_key='x',
                      endpoint='https://my.openai.azure.com')
        self.assertIn('openai.azure.com', c._build_url())

    def test_api_key_from_env(self):
        with patch.dict(os.environ, {'LLM_API_KEY': 'env-key'}):
            c = LLMClient()
            self.assertEqual(c.api_key, 'env-key')

    def test_max_calls_budget(self):
        c = LLMClient(api_key='x', max_calls=3)
        self.assertEqual(c.calls_remaining, 3)


# ── Request body building (provider-specific) ───────────────────────


class TestRequestBodyBuilding(unittest.TestCase):

    def test_openai_body_format(self):
        c = LLMClient(provider='openai', api_key='x', model='gpt-4o')
        body = json.loads(c._build_body('sys', 'user'))
        self.assertEqual(body['model'], 'gpt-4o')
        self.assertEqual(body['messages'][0]['role'], 'system')
        self.assertEqual(body['messages'][1]['role'], 'user')
        self.assertIn('temperature', body)

    def test_anthropic_body_format(self):
        c = LLMClient(provider='anthropic', api_key='x')
        body = json.loads(c._build_body('sys', 'user'))
        self.assertEqual(body['system'], 'sys')
        self.assertEqual(body['messages'][0]['content'], 'user')
        # Anthropic doesn't use the system role inline
        self.assertEqual(body['messages'][0]['role'], 'user')

    def test_anthropic_headers(self):
        c = LLMClient(provider='anthropic', api_key='sk-ant')
        h = c._build_headers()
        self.assertIn('anthropic-version', h)
        self.assertEqual(h['x-api-key'], 'sk-ant')

    def test_openai_headers(self):
        c = LLMClient(provider='openai', api_key='sk-x')
        h = c._build_headers()
        self.assertEqual(h['Authorization'], 'Bearer sk-x')


# ── Dry-run mode ─────────────────────────────────────────────────────


class TestDryRun(unittest.TestCase):

    def test_dry_run_no_http(self):
        c = LLMClient(api_key='x', dry_run=True)
        with patch('powerbi_import.llm_client.urlopen') as mock_open:
            result = c.call('sys', 'user')
            mock_open.assert_not_called()
        self.assertTrue(result.get('dry_run'))
        self.assertEqual(result['cost'], 0)
        self.assertEqual(c._call_count, 1)

    def test_dry_run_estimates_tokens(self):
        c = LLMClient(api_key='x', dry_run=True)
        result = c.call('hello', 'world')
        self.assertGreater(result['input_tokens'], 0)


# ── Live API call (mocked) ───────────────────────────────────────────


class TestCall(unittest.TestCase):

    def test_openai_call_success(self):
        c = LLMClient(provider='openai', api_key='x')
        with patch('powerbi_import.llm_client.urlopen',
                   return_value=_mock_openai_response('SUM(\'T\'[X])')):
            r = c.call('sys', 'user')
        self.assertEqual(r['text'], "SUM('T'[X])")
        self.assertEqual(r['input_tokens'], 10)
        self.assertEqual(r['output_tokens'], 20)
        self.assertGreater(r['cost'], 0)
        self.assertEqual(c._call_count, 1)

    def test_anthropic_call_success(self):
        c = LLMClient(provider='anthropic', api_key='x')
        with patch('powerbi_import.llm_client.urlopen',
                   return_value=_mock_anthropic_response('AVERAGE([Y])')):
            r = c.call('sys', 'user')
        self.assertEqual(r['text'], 'AVERAGE([Y])')
        self.assertEqual(r['input_tokens'], 10)

    def test_call_limit_enforced(self):
        c = LLMClient(api_key='x', max_calls=1)
        with patch('powerbi_import.llm_client.urlopen',
                   return_value=_mock_openai_response('X')):
            c.call('s', 'u')
            r2 = c.call('s', 'u')
        self.assertEqual(r2.get('error'), 'call_limit_reached')

    def test_http_error_returned(self):
        c = LLMClient(api_key='x', max_retries=0)
        err = HTTPError('http://x', 500, 'boom', {}, None)
        with patch('powerbi_import.llm_client.urlopen', side_effect=err):
            r = c.call('s', 'u')
        self.assertEqual(r.get('error'), 'http_500')

    def test_retry_on_429(self):
        c = LLMClient(api_key='x', max_retries=1)
        err = HTTPError('http://x', 429, 'rate', {'Retry-After': '0'}, None)
        ok = _mock_openai_response('SUM([X])')
        with patch('powerbi_import.llm_client.urlopen', side_effect=[err, ok]), \
             patch('time.sleep'):
            r = c.call('s', 'u')
        self.assertEqual(r['text'], 'SUM([X])')

    def test_cost_accumulates(self):
        c = LLMClient(api_key='x')
        with patch('powerbi_import.llm_client.urlopen',
                   return_value=_mock_openai_response('X', 100, 100)):
            c.call('s', 'u')
            c.call('s', 'u')
        # 2 calls × (100/1000 × 0.0025 + 100/1000 × 0.01) = 2 × 0.00125 = 0.0025
        self.assertAlmostEqual(c.total_cost, 0.0025, places=5)


# ── DAX syntax validation gate (Sprint 112.4) ───────────────────────


class TestValidateRefinedDax(unittest.TestCase):

    def test_empty_rejected(self):
        self.assertEqual(_validate_refined_dax(''), ['empty refinement'])

    def test_balanced_passes(self):
        self.assertEqual(_validate_refined_dax('SUM([Sales])'), [])

    def test_unbalanced_open_rejected(self):
        issues = _validate_refined_dax('SUM([Sales]')
        self.assertTrue(any('open' in i.lower() or 'unmatched' in i.lower()
                            for i in issues))

    def test_unbalanced_close_rejected(self):
        issues = _validate_refined_dax('SUM([Sales]))')
        self.assertTrue(any('clos' in i.lower() or 'unmatched' in i.lower()
                            for i in issues))


# ── Schema context & MigrationNote extraction ────────────────────────


class TestHelpers(unittest.TestCase):

    def test_schema_context_empty(self):
        out = _build_schema_context([])
        self.assertIn('no schema', out.lower())

    def test_schema_context_with_columns(self):
        tables = [{'name': 'Sales', 'columns': [
            {'name': 'Amount', 'dataType': 'decimal'},
            {'name': 'Region', 'dataType': 'string'},
        ]}]
        out = _build_schema_context(tables)
        self.assertIn("'Sales'", out)
        self.assertIn('[Amount]', out)
        self.assertIn('[Region]', out)

    def test_schema_context_truncates_at_30_columns(self):
        cols = [{'name': f'C{i}'} for i in range(50)]
        out = _build_schema_context([{'name': 'T', 'columns': cols}])
        # Only 30 should be included
        self.assertIn('[C29]', out)
        self.assertNotIn('[C30]', out)

    def test_extract_note_from_dict_annotations(self):
        m = {'annotations': [
            {'name': 'OtherNote', 'value': 'ignore'},
            {'name': 'MigrationNote', 'value': 'approximated LOD'},
        ]}
        self.assertEqual(_extract_migration_note(m), 'approximated LOD')

    def test_extract_note_from_dict_field(self):
        m = {'migration_note': 'approximated table calc'}
        self.assertEqual(_extract_migration_note(m), 'approximated table calc')

    def test_extract_note_from_inline_comment(self):
        dax = 'SUM([X]) /* MigrationNote: approximated WINDOW_SUM */'
        self.assertIn('approximated', _extract_migration_note(dax))

    def test_extract_note_missing(self):
        self.assertEqual(_extract_migration_note({}), '')


# ── Refinement pipeline ──────────────────────────────────────────────


class TestRefinementPipeline(unittest.TestCase):

    def test_skips_non_approximated(self):
        c = LLMClient(api_key='x', dry_run=True)
        measures = [
            {'name': 'NoNote', 'expression': 'SUM([X])', 'annotations': []},
        ]
        with patch('powerbi_import.llm_client.urlopen') as mock_open:
            results = refine_approximated_measures(c, measures)
            mock_open.assert_not_called()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['status'], 'skipped')

    def test_targets_approximated(self):
        c = LLMClient(provider='openai', api_key='x')
        measures = [
            {'name': 'M1', 'expression': 'SUM([X])',
             'annotations': [{'name': 'MigrationNote',
                              'value': 'approximated LOD'}]},
        ]
        with patch('powerbi_import.llm_client.urlopen',
                   return_value=_mock_openai_response("CALCULATE(SUM('T'[X]))")):
            results = refine_approximated_measures(c, measures)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['status'], 'refined')
        self.assertEqual(results[0]['refined_dax'], "CALCULATE(SUM('T'[X]))")
        self.assertGreater(results[0]['confidence'], 0.5)

    def test_strips_markdown_fences(self):
        c = LLMClient(provider='openai', api_key='x')
        measures = [{'name': 'M', 'expression': 'SUM([X])',
                     'annotations': [{'name': 'MigrationNote',
                                      'value': 'approximated'}]}]
        fenced = "```dax\nSUM('T'[X])\n```"
        with patch('powerbi_import.llm_client.urlopen',
                   return_value=_mock_openai_response(fenced)):
            results = refine_approximated_measures(c, measures)
        self.assertEqual(results[0]['refined_dax'], "SUM('T'[X])")
        self.assertNotIn('```', results[0]['refined_dax'])

    def test_unchanged_when_llm_returns_same(self):
        c = LLMClient(provider='openai', api_key='x')
        measures = [{'name': 'M', 'expression': 'SUM([X])',
                     'annotations': [{'name': 'MigrationNote',
                                      'value': 'approximated'}]}]
        with patch('powerbi_import.llm_client.urlopen',
                   return_value=_mock_openai_response('SUM([X])')):
            results = refine_approximated_measures(c, measures)
        self.assertEqual(results[0]['status'], 'unchanged')
        self.assertEqual(results[0]['confidence'], 1.0)

    def test_rejects_malformed_dax(self):
        """Sprint 112.4: LLM responses with unbalanced parens are rejected."""
        c = LLMClient(provider='openai', api_key='x')
        measures = [{'name': 'M', 'expression': 'SUM([X])',
                     'annotations': [{'name': 'MigrationNote',
                                      'value': 'approximated'}]}]
        # LLM hallucinates broken syntax
        with patch('powerbi_import.llm_client.urlopen',
                   return_value=_mock_openai_response('SUM([X]')):
            results = refine_approximated_measures(c, measures)
        self.assertEqual(results[0]['status'], 'rejected')
        self.assertEqual(results[0]['refined_dax'], 'SUM([X])')  # original kept
        self.assertIn('validation_issues', results[0])

    def test_stops_at_call_limit(self):
        c = LLMClient(provider='openai', api_key='x', max_calls=1)
        measures = [
            {'name': f'M{i}', 'expression': 'SUM([X])',
             'annotations': [{'name': 'MigrationNote',
                              'value': 'approximated'}]}
            for i in range(3)
        ]
        with patch('powerbi_import.llm_client.urlopen',
                   return_value=_mock_openai_response('SUM([Y])')):
            results = refine_approximated_measures(c, measures)
        # First call succeeds; subsequent ones should hit the budget cap
        statuses = [r['status'] for r in results]
        self.assertIn('refined', statuses)
        self.assertTrue(any(r.get('error') == 'call_limit_reached'
                            for r in results))

    def test_http_error_keeps_original(self):
        c = LLMClient(provider='openai', api_key='x', max_retries=0)
        measures = [{'name': 'M', 'expression': 'SUM([X])',
                     'annotations': [{'name': 'MigrationNote',
                                      'value': 'approximated'}]}]
        err = HTTPError('http://x', 500, 'boom', {}, None)
        with patch('powerbi_import.llm_client.urlopen', side_effect=err):
            results = refine_approximated_measures(c, measures)
        self.assertEqual(results[0]['status'], 'error')
        self.assertEqual(results[0]['refined_dax'], 'SUM([X])')


# ── Report generation ────────────────────────────────────────────────


class TestReport(unittest.TestCase):

    def _sample_results(self):
        return [
            {'name': 'A', 'status': 'refined', 'original_dax': 'x',
             'refined_dax': 'y', 'confidence': 0.85, 'cost': 0.01,
             'tokens': {'input': 5, 'output': 5}},
            {'name': 'B', 'status': 'unchanged', 'original_dax': 'x',
             'refined_dax': 'x', 'confidence': 1.0, 'cost': 0.005,
             'tokens': {'input': 5, 'output': 5}},
            {'name': 'C', 'status': 'skipped', 'original_dax': 'x',
             'refined_dax': 'x', 'confidence': 1.0, 'cost': 0,
             'tokens': {'input': 0, 'output': 0}},
            {'name': 'D', 'status': 'rejected', 'original_dax': 'x',
             'refined_dax': 'x', 'confidence': 0, 'cost': 0.005,
             'tokens': {'input': 5, 'output': 5},
             'validation_issues': ['unmatched paren']},
            {'name': 'E', 'status': 'error', 'original_dax': 'x',
             'refined_dax': 'x', 'confidence': 0, 'cost': 0,
             'tokens': {'input': 0, 'output': 0}, 'error': 'http_500'},
        ]

    def test_summary_counts(self):
        c = LLMClient(api_key='x', dry_run=True)
        report = generate_llm_report(c, self._sample_results())
        s = report['summary']
        self.assertEqual(s['total_measures'], 5)
        self.assertEqual(s['refined'], 1)
        self.assertEqual(s['unchanged'], 1)
        self.assertEqual(s['skipped'], 1)
        self.assertEqual(s['rejected'], 1)
        self.assertEqual(s['errors'], 1)

    def test_report_writes_to_disk(self):
        c = LLMClient(api_key='x', dry_run=True)
        with tempfile.TemporaryDirectory() as tmp:
            report = generate_llm_report(c, self._sample_results(),
                                         output_dir=tmp)
            path = os.path.join(tmp, 'llm_refinement_report.json')
            self.assertTrue(os.path.exists(path))
            with open(path, encoding='utf-8') as f:
                loaded = json.load(f)
            self.assertEqual(loaded['summary']['total_measures'], 5)
        self.assertEqual(report['provider'], 'openai')


if __name__ == '__main__':
    unittest.main()
