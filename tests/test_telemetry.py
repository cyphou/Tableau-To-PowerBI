"""Tests for powerbi_import.telemetry — TelemetryCollector class.

Covers save(), send(), read_log(), summary(), _get_tool_version(),
is_telemetry_enabled(), and edge cases for record_stats/record_error
when disabled.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))

from telemetry import TelemetryCollector, is_telemetry_enabled, TELEMETRY_VERSION


class TestIsTelemetryEnabled(unittest.TestCase):
    """Test is_telemetry_enabled() function."""

    def test_not_set(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop('TTPBI_TELEMETRY', None)
            self.assertFalse(is_telemetry_enabled())

    def test_set_to_1(self):
        with patch.dict(os.environ, {'TTPBI_TELEMETRY': '1'}):
            self.assertTrue(is_telemetry_enabled())

    def test_set_to_true(self):
        with patch.dict(os.environ, {'TTPBI_TELEMETRY': 'true'}):
            self.assertTrue(is_telemetry_enabled())

    def test_set_to_yes(self):
        with patch.dict(os.environ, {'TTPBI_TELEMETRY': 'yes'}):
            self.assertTrue(is_telemetry_enabled())

    def test_set_to_0(self):
        with patch.dict(os.environ, {'TTPBI_TELEMETRY': '0'}):
            self.assertFalse(is_telemetry_enabled())

    def test_set_to_no(self):
        with patch.dict(os.environ, {'TTPBI_TELEMETRY': 'no'}):
            self.assertFalse(is_telemetry_enabled())

    def test_set_to_True_uppercase(self):
        with patch.dict(os.environ, {'TTPBI_TELEMETRY': 'TRUE'}):
            self.assertTrue(is_telemetry_enabled())


class TestTelemetryCollectorInit(unittest.TestCase):
    """Test TelemetryCollector initialization."""

    def test_default_disabled(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop('TTPBI_TELEMETRY', None)
            t = TelemetryCollector()
            self.assertFalse(t.enabled)

    def test_explicit_enabled(self):
        t = TelemetryCollector(enabled=True)
        self.assertTrue(t.enabled)

    def test_explicit_disabled(self):
        t = TelemetryCollector(enabled=False)
        self.assertFalse(t.enabled)

    def test_custom_log_path(self):
        t = TelemetryCollector(log_path='/tmp/test_telem.json')
        self.assertEqual(t.log_path, '/tmp/test_telem.json')

    def test_custom_endpoint(self):
        t = TelemetryCollector(endpoint='https://example.com/api')
        self.assertEqual(t.endpoint, 'https://example.com/api')

    def test_data_has_required_fields(self):
        t = TelemetryCollector(enabled=True)
        data = t.get_data()
        self.assertEqual(data['telemetry_version'], TELEMETRY_VERSION)
        self.assertIn('session_id', data)
        self.assertIn('python_version', data)
        self.assertIn('platform', data)
        self.assertIn('tool_version', data)
        self.assertIsInstance(data['stats'], dict)
        self.assertIsInstance(data['errors'], list)


class TestTelemetryCollectorStartFinish(unittest.TestCase):
    """Test start() / finish() timing."""

    def test_start_sets_timestamp(self):
        t = TelemetryCollector(enabled=True)
        t.start()
        data = t.get_data()
        self.assertIsNotNone(data['timestamp'])

    def test_finish_records_duration(self):
        t = TelemetryCollector(enabled=True)
        t.start()
        t.finish()
        data = t.get_data()
        self.assertIsNotNone(data['duration_seconds'])
        self.assertGreaterEqual(data['duration_seconds'], 0)

    def test_finish_without_start(self):
        t = TelemetryCollector(enabled=True)
        t.finish()
        data = t.get_data()
        self.assertIsNone(data['duration_seconds'])


class TestTelemetryRecording(unittest.TestCase):
    """Test record_stats() and record_error()."""

    def test_record_stats_when_enabled(self):
        t = TelemetryCollector(enabled=True)
        t.record_stats(tables=5, columns=20, measures=10)
        data = t.get_data()
        self.assertEqual(data['stats']['tables'], 5)
        self.assertEqual(data['stats']['columns'], 20)

    def test_record_stats_when_disabled(self):
        t = TelemetryCollector(enabled=False)
        t.record_stats(tables=5)
        data = t.get_data()
        self.assertEqual(data['stats'], {})

    def test_record_error_when_enabled(self):
        t = TelemetryCollector(enabled=True)
        t.record_error('dax_conversion', 'ZN not converted')
        data = t.get_data()
        self.assertEqual(len(data['errors']), 1)
        self.assertEqual(data['errors'][0]['category'], 'dax_conversion')

    def test_record_error_when_disabled(self):
        t = TelemetryCollector(enabled=False)
        t.record_error('dax_conversion', 'ZN not converted')
        data = t.get_data()
        self.assertEqual(len(data['errors']), 0)

    def test_record_error_truncates_long_message(self):
        t = TelemetryCollector(enabled=True)
        long_msg = 'x' * 500
        t.record_error('test', long_msg)
        data = t.get_data()
        self.assertLessEqual(len(data['errors'][0]['message']), 200)


class TestTelemetrySave(unittest.TestCase):
    """Test save() method — writing to JSONL file."""

    def test_save_creates_file(self):
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
            tmp_path = tmp.name

        try:
            # Remove file so save() creates it
            os.unlink(tmp_path)

            t = TelemetryCollector(enabled=True, log_path=tmp_path)
            t.start()
            t.record_stats(tables=3)
            t.finish()
            t.save()

            self.assertTrue(os.path.exists(tmp_path))
            with open(tmp_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            entry = json.loads(content)
            self.assertEqual(entry['stats']['tables'], 3)
            self.assertIsNotNone(entry['duration_seconds'])
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_save_appends_multiple_entries(self):
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
            tmp_path = tmp.name
        os.unlink(tmp_path)

        try:
            for i in range(3):
                t = TelemetryCollector(enabled=True, log_path=tmp_path)
                t.start()
                t.record_stats(run=i)
                t.finish()
                t.save()

            with open(tmp_path, 'r', encoding='utf-8') as f:
                lines = [l.strip() for l in f if l.strip()]
            self.assertEqual(len(lines), 3)
            for i, line in enumerate(lines):
                entry = json.loads(line)
                self.assertEqual(entry['stats']['run'], i)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_save_disabled_does_nothing(self):
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
            tmp_path = tmp.name
        os.unlink(tmp_path)

        try:
            t = TelemetryCollector(enabled=False, log_path=tmp_path)
            t.save()
            self.assertFalse(os.path.exists(tmp_path))
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_save_handles_write_error(self):
        """save() silently handles write errors."""
        t = TelemetryCollector(enabled=True, log_path='/nonexistent/dir/file.json')
        # Should not raise
        t.save()


class TestTelemetrySend(unittest.TestCase):
    """Test send() method — HTTP POST."""

    def test_send_disabled(self):
        t = TelemetryCollector(enabled=False, endpoint='https://example.com')
        # Should not raise, should not make any HTTP call
        t.send()

    def test_send_no_endpoint(self):
        t = TelemetryCollector(enabled=True, endpoint='')
        # Should not raise
        t.send()

    def test_send_success(self):
        t = TelemetryCollector(enabled=True, endpoint='https://example.com/api')
        t.start()
        t.finish()
        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_urlopen.return_value = MagicMock()
            t.send()
            mock_urlopen.assert_called_once()

    def test_send_handles_error(self):
        t = TelemetryCollector(enabled=True, endpoint='https://example.com/api')
        with patch('urllib.request.urlopen', side_effect=Exception('network error')):
            # Should not raise
            t.send()


class TestTelemetryGetToolVersion(unittest.TestCase):
    """Test _get_tool_version() static method."""

    def test_returns_string(self):
        version = TelemetryCollector._get_tool_version()
        self.assertIsInstance(version, str)

    def test_returns_version_or_unknown(self):
        version = TelemetryCollector._get_tool_version()
        # Should be either a version string like "9.0.0" or "unknown"
        self.assertTrue(version == 'unknown' or version[0].isdigit())

    def test_returns_unknown_when_changelog_missing(self):
        with patch('builtins.open', side_effect=FileNotFoundError):
            version = TelemetryCollector._get_tool_version()
            self.assertEqual(version, 'unknown')


class TestTelemetryReadLog(unittest.TestCase):
    """Test read_log() class method."""

    def test_read_existing_log(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                         delete=False, encoding='utf-8') as tmp:
            tmp.write(json.dumps({'session_id': 'a1', 'stats': {}}) + '\n')
            tmp.write(json.dumps({'session_id': 'b2', 'stats': {}}) + '\n')
            tmp_path = tmp.name

        try:
            entries = TelemetryCollector.read_log(tmp_path)
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0]['session_id'], 'a1')
            self.assertEqual(entries[1]['session_id'], 'b2')
        finally:
            os.unlink(tmp_path)

    def test_read_nonexistent_log(self):
        entries = TelemetryCollector.read_log('/nonexistent/file.json')
        self.assertEqual(entries, [])

    def test_read_empty_log(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                         delete=False, encoding='utf-8') as tmp:
            tmp.write('')
            tmp_path = tmp.name

        try:
            entries = TelemetryCollector.read_log(tmp_path)
            self.assertEqual(entries, [])
        finally:
            os.unlink(tmp_path)

    def test_read_log_with_blank_lines(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                         delete=False, encoding='utf-8') as tmp:
            tmp.write(json.dumps({'session_id': 'x1'}) + '\n')
            tmp.write('\n')
            tmp.write(json.dumps({'session_id': 'x2'}) + '\n')
            tmp_path = tmp.name

        try:
            entries = TelemetryCollector.read_log(tmp_path)
            self.assertEqual(len(entries), 2)
        finally:
            os.unlink(tmp_path)


class TestTelemetrySummary(unittest.TestCase):
    """Test summary() class method."""

    def test_summary_empty_log(self):
        result = TelemetryCollector.summary('/nonexistent/file.json')
        self.assertEqual(result, {'sessions': 0})

    def test_summary_with_entries(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                         delete=False, encoding='utf-8') as tmp:
            e1 = {'session_id': 'a', 'duration_seconds': 10, 'errors': [],
                   'platform': 'win32'}
            e2 = {'session_id': 'b', 'duration_seconds': 20,
                   'errors': [{'category': 'dax', 'message': 'err'}],
                   'platform': 'linux'}
            e3 = {'session_id': 'c', 'duration_seconds': 30, 'errors': [],
                   'platform': 'win32'}
            tmp.write(json.dumps(e1) + '\n')
            tmp.write(json.dumps(e2) + '\n')
            tmp.write(json.dumps(e3) + '\n')
            tmp_path = tmp.name

        try:
            result = TelemetryCollector.summary(tmp_path)
            self.assertEqual(result['sessions'], 3)
            self.assertEqual(result['total_duration_seconds'], 60)
            self.assertEqual(result['avg_duration_seconds'], 20)
            self.assertEqual(result['total_errors'], 1)
            self.assertEqual(result['platforms']['win32'], 2)
            self.assertEqual(result['platforms']['linux'], 1)
        finally:
            os.unlink(tmp_path)

    def test_summary_null_duration(self):
        """Handles entries with null duration_seconds."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                         delete=False, encoding='utf-8') as tmp:
            tmp.write(json.dumps({'session_id': 'a', 'duration_seconds': None,
                                   'errors': [], 'platform': 'win32'}) + '\n')
            tmp_path = tmp.name

        try:
            result = TelemetryCollector.summary(tmp_path)
            self.assertEqual(result['sessions'], 1)
            self.assertEqual(result['total_duration_seconds'], 0)
        finally:
            os.unlink(tmp_path)


class TestTelemetryGetData(unittest.TestCase):
    """Test get_data() returns a copy."""

    def test_returns_dict(self):
        t = TelemetryCollector(enabled=True)
        data = t.get_data()
        self.assertIsInstance(data, dict)

    def test_full_lifecycle(self):
        """End-to-end: start → record → finish → save → read → summary."""
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
            tmp_path = tmp.name
        os.unlink(tmp_path)

        try:
            t = TelemetryCollector(enabled=True, log_path=tmp_path)
            t.start()
            t.record_stats(tables=5, columns=20)
            t.record_error('m_query', 'unsupported transform')
            t.finish()
            t.save()

            entries = TelemetryCollector.read_log(tmp_path)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]['stats']['tables'], 5)

            summary = TelemetryCollector.summary(tmp_path)
            self.assertEqual(summary['sessions'], 1)
            self.assertEqual(summary['total_errors'], 1)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


if __name__ == '__main__':
    unittest.main()
