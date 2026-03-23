"""Sprint 110 — REST API endpoint tests.

Tests the HTTP migration API server (api_server.py) using stdlib TestClient
pattern with a threaded server on a random port.
"""

import io
import json
import os
import sys
import threading
import time
import unittest
import urllib.request
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'powerbi_import'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))

from api_server import (
    MigrationHandler, _jobs, _lock, _new_job, _get_job, _update_job,
    _parse_multipart, _int_param, run_server,
)
from http.server import HTTPServer


def _find_free_port():
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class _ServerTestBase(unittest.TestCase):
    """Base class that starts a test server on a random port."""

    @classmethod
    def setUpClass(cls):
        cls.port = _find_free_port()
        cls.base_url = f'http://127.0.0.1:{cls.port}'
        cls.server = HTTPServer(('127.0.0.1', cls.port), MigrationHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.1)  # Let server start

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        # Clear jobs between tests
        with _lock:
            _jobs.clear()

    def _get(self, path):
        url = self.base_url + path
        req = urllib.request.Request(url)
        try:
            resp = urllib.request.urlopen(req, timeout=5)
            return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def _post(self, path, data, content_type='application/octet-stream', headers=None):
        url = self.base_url + path
        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header('Content-Type', content_type)
        if headers:
            for k, v in headers.items():
                req.add_header(k, v)
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            body = resp.read()
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body
        except urllib.error.HTTPError as e:
            body = e.read()
            try:
                return e.code, json.loads(body)
            except json.JSONDecodeError:
                return e.code, body


class TestHealthEndpoint(_ServerTestBase):
    """GET /health returns ok."""

    def test_health_ok(self):
        status, data = self._get('/health')
        self.assertEqual(status, 200)
        self.assertEqual(data['status'], 'ok')
        self.assertIn('version', data)


class TestJobsEndpoint(_ServerTestBase):
    """GET /jobs returns job list."""

    def test_empty_jobs(self):
        status, data = self._get('/jobs')
        self.assertEqual(status, 200)
        self.assertEqual(data['jobs'], [])

    def test_jobs_after_create(self):
        _new_job('/tmp/test.twbx')
        status, data = self._get('/jobs')
        self.assertEqual(status, 200)
        self.assertEqual(len(data['jobs']), 1)


class TestStatusEndpoint(_ServerTestBase):
    """GET /status/{id} returns job status."""

    def test_status_not_found(self):
        status, data = self._get('/status/nonexistent')
        self.assertEqual(status, 404)

    def test_status_queued(self):
        job_id = _new_job('/tmp/test.twbx')
        status, data = self._get(f'/status/{job_id}')
        self.assertEqual(status, 200)
        self.assertEqual(data['status'], 'queued')
        self.assertEqual(data['job_id'], job_id)


class TestDownloadEndpoint(_ServerTestBase):
    """GET /download/{id} returns ZIP file or error."""

    def test_download_not_found(self):
        status, data = self._get('/download/nonexistent')
        self.assertEqual(status, 404)

    def test_download_not_completed(self):
        job_id = _new_job('/tmp/test.twbx')
        status, data = self._get(f'/download/{job_id}')
        self.assertEqual(status, 400)

    def test_download_completed(self):
        import tempfile
        tmpdir = tempfile.mkdtemp()
        # Create a dummy file
        with open(os.path.join(tmpdir, 'test.txt'), 'w') as f:
            f.write('hello')
        job_id = _new_job('/tmp/test.twbx')
        _update_job(job_id, status='completed', output_dir=tmpdir)

        url = self.base_url + f'/download/{job_id}'
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=5)
        self.assertEqual(resp.status, 200)
        self.assertIn('application/zip', resp.headers.get('Content-Type', ''))
        # Clean up
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


class TestMigrateEndpoint(_ServerTestBase):
    """POST /migrate validates input."""

    def test_no_body(self):
        status, data = self._post('/migrate', b'', content_type='application/octet-stream')
        self.assertEqual(status, 400)

    def test_unsupported_extension(self):
        # Send a small file with wrong extension (using JSON payload)
        import base64
        payload = json.dumps({
            'filename': 'test.xlsx',
            'file': base64.b64encode(b'fake data').decode(),
        }).encode()
        status, data = self._post('/migrate', payload,
                                   content_type='application/json')
        self.assertEqual(status, 400)
        self.assertIn('Unsupported', data.get('error', ''))


class TestNotFound(_ServerTestBase):
    """Unknown paths return 404."""

    def test_get_unknown(self):
        status, data = self._get('/unknown')
        self.assertEqual(status, 404)

    def test_post_unknown(self):
        status, data = self._post('/unknown', b'data')
        self.assertEqual(status, 404)


# ── Unit tests for helpers (no server needed) ────────────────────────────────

class TestJobStore(unittest.TestCase):
    """Job store CRUD operations."""

    def setUp(self):
        with _lock:
            _jobs.clear()

    def test_new_job(self):
        jid = _new_job('/tmp/test.twbx')
        self.assertEqual(len(jid), 12)
        job = _get_job(jid)
        self.assertEqual(job['status'], 'queued')

    def test_update_job(self):
        jid = _new_job('/tmp/test.twbx')
        _update_job(jid, status='running')
        self.assertEqual(_get_job(jid)['status'], 'running')

    def test_get_nonexistent(self):
        self.assertIsNone(_get_job('nope'))


class TestParseMultipart(unittest.TestCase):
    """Multipart form data parsing."""

    def test_parse_valid(self):
        boundary = b'----boundary123'
        body = (
            b'------boundary123\r\n'
            b'Content-Disposition: form-data; name="file"; filename="test.twbx"\r\n'
            b'Content-Type: application/octet-stream\r\n'
            b'\r\n'
            b'file content here\r\n'
            b'------boundary123--\r\n'
        )
        result = _parse_multipart(body, b'----boundary123')
        self.assertIsNotNone(result)
        filename, data = result
        self.assertEqual(filename, 'test.twbx')
        self.assertEqual(data, b'file content here')

    def test_parse_no_file(self):
        result = _parse_multipart(b'no file here', b'boundary')
        self.assertIsNone(result)

    def test_path_traversal_stripped(self):
        boundary = b'----b'
        body = (
            b'------b\r\n'
            b'Content-Disposition: form-data; name="file"; filename="../../etc/passwd"\r\n'
            b'\r\n'
            b'data\r\n'
            b'------b--\r\n'
        )
        result = _parse_multipart(body, b'----b')
        self.assertIsNotNone(result)
        filename, _ = result
        self.assertEqual(filename, 'passwd')  # path stripped to basename


class TestIntParam(unittest.TestCase):
    """Query parameter integer parsing."""

    def test_valid_int(self):
        self.assertEqual(_int_param({'x': ['42']}, 'x'), 42)

    def test_invalid_int(self):
        self.assertIsNone(_int_param({'x': ['abc']}, 'x'))

    def test_missing_key(self):
        self.assertIsNone(_int_param({}, 'x'))


if __name__ == '__main__':
    unittest.main()
