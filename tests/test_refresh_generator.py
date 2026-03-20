"""Tests for the refresh_generator module (Sprint 73).

Covers: schedule frequency mapping, time parsing, refresh config generation,
subscription config, combined JSON output, edge cases.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from powerbi_import.refresh_generator import (
    FREQUENCY_MAP,
    _parse_time,
    _map_weekday,
    generate_refresh_config,
    generate_subscription_config,
    generate_refresh_json,
)


# ── Frequency Mapping ─────────────────────────────────────

class TestFrequencyMap(unittest.TestCase):
    def test_daily(self):
        self.assertEqual(FREQUENCY_MAP['Daily'], 'Daily')

    def test_weekly(self):
        self.assertEqual(FREQUENCY_MAP['Weekly'], 'Weekly')

    def test_monthly(self):
        self.assertEqual(FREQUENCY_MAP['Monthly'], 'Monthly')

    def test_hourly_maps_to_daily(self):
        self.assertEqual(FREQUENCY_MAP['Hourly'], 'Daily')


# ── Time Parsing ──────────────────────────────────────────

class TestParseTime(unittest.TestCase):
    def test_hhmm(self):
        self.assertEqual(_parse_time('06:30'), (6, 30))

    def test_iso_prefix(self):
        self.assertEqual(_parse_time('14:00'), (14, 0))

    def test_empty(self):
        self.assertEqual(_parse_time(''), (0, 0))

    def test_none(self):
        self.assertEqual(_parse_time(None), (0, 0))

    def test_single_digit_hour(self):
        self.assertEqual(_parse_time('8:15'), (8, 15))


# ── Weekday Mapping ───────────────────────────────────────

class TestMapWeekday(unittest.TestCase):
    def test_sunday(self):
        self.assertEqual(_map_weekday('Sunday'), 1)

    def test_monday(self):
        self.assertEqual(_map_weekday('Monday'), 2)

    def test_friday(self):
        self.assertEqual(_map_weekday('Friday'), 6)

    def test_unknown_default(self):
        self.assertEqual(_map_weekday('Holiday'), 2)


# ── Generate Refresh Config ──────────────────────────────

class TestGenerateRefreshConfig(unittest.TestCase):
    def test_empty_tasks(self):
        config = generate_refresh_config([])
        self.assertFalse(config['enabled'])
        self.assertIn('notes', config)

    def test_none_tasks(self):
        config = generate_refresh_config(None)
        self.assertFalse(config['enabled'])

    def test_basic_daily(self):
        tasks = [{
            'id': 't1',
            'schedule': {
                'frequency': 'Daily',
                'frequencyDetails': {'start': '06:00'},
            }
        }]
        config = generate_refresh_config(tasks)
        self.assertTrue(config['enabled'])
        self.assertEqual(config['frequency'], 'Daily')
        self.assertIn('06:00', config['times'])

    def test_weekly_with_days(self):
        tasks = [{
            'id': 't1',
            'schedule': {
                'frequency': 'Weekly',
                'frequencyDetails': {
                    'start': '08:00',
                    'intervals': {'weekDay': ['Monday', 'Wednesday']},
                },
            }
        }]
        config = generate_refresh_config(tasks)
        self.assertEqual(config['frequency'], 'Weekly')
        self.assertIn('days', config)
        self.assertIn('Monday', config['days'])
        self.assertIn('Wednesday', config['days'])

    def test_hourly_produces_warning(self):
        tasks = [{
            'id': 't1',
            'schedule': {
                'name': 'Hourly Refresh',
                'frequency': 'Hourly',
                'frequencyDetails': {
                    'start': '00:00',
                    'intervals': {'hours': ['0', '4', '8', '12', '16', '20']},
                },
            }
        }]
        config = generate_refresh_config(tasks)
        self.assertTrue(config['enabled'])
        self.assertTrue(any('Hourly' in n for n in config['notes']))

    def test_multiple_times_deduped(self):
        tasks = [
            {'id': 't1', 'schedule': {'frequency': 'Daily', 'frequencyDetails': {'start': '06:00'}}},
            {'id': 't2', 'schedule': {'frequency': 'Daily', 'frequencyDetails': {'start': '06:00'}}},
        ]
        config = generate_refresh_config(tasks)
        self.assertEqual(config['times'].count('06:00'), 1)

    def test_times_sorted(self):
        tasks = [
            {'id': 't1', 'schedule': {'frequency': 'Daily', 'frequencyDetails': {'start': '18:00'}}},
            {'id': 't2', 'schedule': {'frequency': 'Daily', 'frequencyDetails': {'start': '06:00'}}},
        ]
        config = generate_refresh_config(tasks)
        self.assertEqual(config['times'], ['06:00', '18:00'])

    def test_max_8_times_pro(self):
        tasks = [
            {'id': f't{i}', 'schedule': {
                'frequency': 'Daily',
                'frequencyDetails': {'start': f'{i:02d}:00'},
            }}
            for i in range(0, 24, 2)  # 12 tasks
        ]
        config = generate_refresh_config(tasks)
        self.assertLessEqual(len(config['times']), 8)
        self.assertTrue(any('truncated' in n.lower() or 'max' in n.lower()
                           for n in config['notes']))

    def test_schedule_lookup_enrichment(self):
        tasks = [{
            'id': 't1',
            'schedule_id': 'sched-123',
            'schedule': {},
        }]
        schedules = [{
            'id': 'sched-123',
            'frequency': 'Daily',
            'frequencyDetails': {'start': '07:30'},
        }]
        config = generate_refresh_config(tasks, schedules=schedules)
        self.assertTrue(config['enabled'])
        self.assertIn('07:30', config['times'])

    def test_intervals_as_list(self):
        tasks = [{
            'id': 't1',
            'schedule': {
                'frequency': 'Weekly',
                'frequencyDetails': {
                    'start': '09:00',
                    'intervals': [
                        {'weekDay': 'Tuesday'},
                        {'weekDay': 'Thursday'},
                    ],
                },
            },
        }]
        config = generate_refresh_config(tasks)
        self.assertEqual(config['frequency'], 'Weekly')
        self.assertIn('Tuesday', config['days'])
        self.assertIn('Thursday', config['days'])

    def test_default_time_fallback(self):
        tasks = [{'id': 't1', 'schedule': {'frequency': 'Daily'}}]
        config = generate_refresh_config(tasks)
        self.assertEqual(config['times'], ['06:00'])


# ── Generate Subscription Config ──────────────────────────

class TestGenerateSubscriptionConfig(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(generate_subscription_config([]), [])

    def test_none(self):
        self.assertEqual(generate_subscription_config(None), [])

    def test_basic_subscription(self):
        subs = [{
            'subject': 'Daily Sales Report',
            'user': {'name': 'alice', 'email': 'alice@company.com'},
            'schedule': {
                'frequency': 'Daily',
                'frequencyDetails': {'start': '08:00'},
            },
        }]
        result = generate_subscription_config(subs)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['title'], 'Daily Sales Report')
        self.assertEqual(result[0]['recipients'], ['alice@company.com'])
        self.assertEqual(result[0]['frequency'], 'Daily')
        self.assertEqual(result[0]['time'], '08:00')
        self.assertTrue(result[0]['enabled'])

    def test_hourly_subscription_warning(self):
        subs = [{
            'subject': 'Alert',
            'user': {'email': 'bob@co.com'},
            'schedule': {'frequency': 'Hourly'},
        }]
        result = generate_subscription_config(subs)
        self.assertTrue(any('Hourly' in n for n in result[0]['notes']))

    def test_no_email_fallback(self):
        subs = [{
            'subject': 'Test',
            'user': {'name': 'charlie'},
            'schedule': {'frequency': 'Daily'},
        }]
        result = generate_subscription_config(subs)
        # Falls back to name if no email
        self.assertEqual(result[0]['recipients'], ['charlie'])

    def test_multiple_subscriptions(self):
        subs = [
            {'subject': 'A', 'user': {'email': 'a@co.com'}, 'schedule': {'frequency': 'Daily'}},
            {'subject': 'B', 'user': {'email': 'b@co.com'}, 'schedule': {'frequency': 'Weekly'}},
        ]
        result = generate_subscription_config(subs)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['title'], 'A')
        self.assertEqual(result[1]['title'], 'B')


# ── Generate Refresh JSON (Combined) ─────────────────────

class TestGenerateRefreshJson(unittest.TestCase):
    def test_combined_output_keys(self):
        result = generate_refresh_json([], [])
        self.assertIn('refresh', result)
        self.assertIn('subscriptions', result)
        self.assertIn('migration_notes', result)

    def test_combined_with_data(self):
        tasks = [{'id': 't1', 'schedule': {'frequency': 'Daily', 'frequencyDetails': {'start': '06:00'}}}]
        subs = [{'subject': 'Report', 'user': {'email': 'x@co.com'}, 'schedule': {'frequency': 'Daily'}}]
        result = generate_refresh_json(tasks, subs)
        self.assertTrue(result['refresh']['enabled'])
        self.assertEqual(len(result['subscriptions']), 1)

    def test_migration_notes_present(self):
        result = generate_refresh_json([])
        notes = result['migration_notes']
        self.assertTrue(any('Pro' in n for n in notes))
        self.assertTrue(any('gateway' in n.lower() for n in notes))

    def test_no_subs_default(self):
        result = generate_refresh_json([], None)
        self.assertEqual(result['subscriptions'], [])

    def test_serializable(self):
        tasks = [{'id': 't1', 'schedule': {'frequency': 'Weekly', 'frequencyDetails': {'start': '12:00', 'intervals': {'weekDay': ['Monday']}}}}]
        result = generate_refresh_json(tasks, [])
        # Must be JSON-serializable
        serialized = json.dumps(result)
        self.assertIsInstance(serialized, str)


# ── Server Client Extensions ─────────────────────────────

class TestServerClientMethods(unittest.TestCase):
    """Test that server_client has the new methods."""

    def test_has_get_workbook_extract_tasks(self):
        from tableau_export.server_client import TableauServerClient
        self.assertTrue(hasattr(TableauServerClient, 'get_workbook_extract_tasks'))

    def test_has_get_workbook_subscriptions(self):
        from tableau_export.server_client import TableauServerClient
        self.assertTrue(hasattr(TableauServerClient, 'get_workbook_subscriptions'))


# ── PBI Deployer Extensions ──────────────────────────────

class TestPBIDeployerScheduleMethod(unittest.TestCase):
    """Test that pbi_deployer has the new method."""

    def test_has_deploy_refresh_schedule(self):
        from powerbi_import.deploy.pbi_deployer import PBIWorkspaceDeployer
        self.assertTrue(hasattr(PBIWorkspaceDeployer, 'deploy_refresh_schedule'))


if __name__ == '__main__':
    unittest.main()
