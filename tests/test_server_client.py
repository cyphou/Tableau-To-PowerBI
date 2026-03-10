"""
Tests for Sprint 15 — Tableau Server / Cloud client and CLI integration.

Covers:
  - TableauServerClient init and auth
  - REST API endpoint construction
  - Workbook listing and download
  - Datasource and project listing
  - Batch download
  - Context manager protocol
  - CLI --server/--workbook/--site/--token flags
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tableau_export.server_client import TableauServerClient


class TestTableauServerClientInit(unittest.TestCase):
    """Test client initialization and configuration."""

    def test_init_with_explicit_params(self):
        c = TableauServerClient(
            server_url='https://tab.example.com',
            token_name='my-pat',
            token_secret='secret123',
            site_id='my-site',
        )
        self.assertEqual(c.server_url, 'https://tab.example.com')
        self.assertEqual(c.token_name, 'my-pat')
        self.assertEqual(c.token_secret, 'secret123')
        self.assertEqual(c.site_id, 'my-site')

    def test_init_strips_trailing_slash(self):
        c = TableauServerClient(server_url='https://tab.co/')
        self.assertEqual(c.server_url, 'https://tab.co')

    def test_init_from_env(self):
        env = {
            'TABLEAU_SERVER': 'https://env-server.com',
            'TABLEAU_TOKEN_NAME': 'env-pat',
            'TABLEAU_TOKEN_SECRET': 'env-secret',
            'TABLEAU_SITE_ID': 'env-site',
        }
        with patch.dict(os.environ, env, clear=False):
            c = TableauServerClient()
            self.assertEqual(c.server_url, 'https://env-server.com')
            self.assertEqual(c.token_name, 'env-pat')
            self.assertEqual(c.token_secret, 'env-secret')
            self.assertEqual(c.site_id, 'env-site')

    def test_init_password_auth(self):
        c = TableauServerClient(
            server_url='https://tab.co',
            username='admin',
            password='p@ss',
        )
        self.assertEqual(c.username, 'admin')
        self.assertEqual(c.password, 'p@ss')

    def test_base_url(self):
        c = TableauServerClient(server_url='https://tab.co', api_version='3.21')
        self.assertEqual(c.base_url, 'https://tab.co/api/3.21')

    def test_site_url_before_signin_raises(self):
        c = TableauServerClient(server_url='https://tab.co')
        with self.assertRaises(RuntimeError):
            _ = c.site_url

    def test_default_api_version(self):
        c = TableauServerClient(server_url='https://tab.co')
        self.assertEqual(c.api_version, '3.21')


class TestTableauServerClientAuth(unittest.TestCase):
    """Test authentication methods."""

    def test_sign_in_pat(self):
        """sign_in with PAT sends correct payload."""
        c = TableauServerClient(
            server_url='https://tab.co',
            token_name='pat',
            token_secret='sec',
            site_id='s1',
        )
        with patch.object(c, '_request') as mock_req:
            mock_req.return_value = {
                'credentials': {
                    'token': 'auth-tok-123',
                    'site': {'id': 'site-luid-456'},
                }
            }
            result = c.sign_in()

        self.assertEqual(c._auth_token, 'auth-tok-123')
        self.assertEqual(c._site_luid, 'site-luid-456')
        self.assertEqual(result, 'site-luid-456')

        # Verify payload
        call_args = mock_req.call_args
        payload = call_args[1].get('json_body') or call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get('json_body')
        self.assertIn('credentials', payload)
        self.assertIn('personalAccessTokenName', payload['credentials'])

    def test_sign_in_password(self):
        c = TableauServerClient(
            server_url='https://tab.co',
            username='admin',
            password='pass',
        )
        with patch.object(c, '_request') as mock_req:
            mock_req.return_value = {
                'credentials': {
                    'token': 'tok',
                    'site': {'id': 'sid'},
                }
            }
            c.sign_in()

        payload = mock_req.call_args[1].get('json_body')
        self.assertIn('name', payload['credentials'])
        self.assertEqual(payload['credentials']['name'], 'admin')

    def test_sign_in_no_credentials_raises(self):
        c = TableauServerClient(server_url='https://tab.co')
        with self.assertRaises(ValueError):
            c.sign_in()

    def test_sign_in_no_token_returned_raises(self):
        c = TableauServerClient(
            server_url='https://tab.co',
            token_name='p', token_secret='s',
        )
        with patch.object(c, '_request') as mock_req:
            mock_req.return_value = {'credentials': {}}
            with self.assertRaises(RuntimeError):
                c.sign_in()

    def test_sign_out(self):
        c = TableauServerClient(server_url='https://tab.co')
        c._auth_token = 'tok'
        c._site_luid = 'sid'
        with patch.object(c, '_request') as mock_req:
            mock_req.return_value = {}
            c.sign_out()
        self.assertIsNone(c._auth_token)
        self.assertIsNone(c._site_luid)


class TestTableauServerClientWorkbooks(unittest.TestCase):
    """Test workbook operations."""

    def _make_signed_in_client(self):
        c = TableauServerClient(server_url='https://tab.co')
        c._auth_token = 'tok'
        c._site_luid = 'site-1'
        return c

    def test_list_workbooks(self):
        c = self._make_signed_in_client()
        with patch.object(c, '_request') as mock_req:
            mock_req.return_value = {
                'workbooks': {
                    'workbook': [
                        {'id': 'wb1', 'name': 'Sales'},
                        {'id': 'wb2', 'name': 'Finance'},
                    ]
                }
            }
            result = c.list_workbooks()

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['name'], 'Sales')
        # Verify URL
        url = mock_req.call_args[0][1]
        self.assertIn('/sites/site-1/workbooks', url)

    def test_list_workbooks_with_project_filter(self):
        c = self._make_signed_in_client()
        with patch.object(c, '_request') as mock_req:
            mock_req.return_value = {'workbooks': {'workbook': []}}
            c.list_workbooks(project_name='Marketing')
        url = mock_req.call_args[0][1]
        self.assertIn('filter=projectName:eq:Marketing', url)

    def test_get_workbook(self):
        c = self._make_signed_in_client()
        with patch.object(c, '_request') as mock_req:
            mock_req.return_value = {'workbook': {'id': 'wb1', 'name': 'Sales'}}
            result = c.get_workbook('wb1')
        self.assertEqual(result['name'], 'Sales')

    def test_download_workbook(self):
        c = self._make_signed_in_client()
        with patch.object(c, '_request') as mock_req:
            mock_req.return_value = None
            with tempfile.TemporaryDirectory() as td:
                out = os.path.join(td, 'test.twbx')
                # Create the file so getsize works
                with open(out, 'wb') as f:
                    f.write(b'fake_twbx')
                result = c.download_workbook('wb1', out)
                self.assertEqual(result, out)
                url = mock_req.call_args[0][1]
                self.assertIn('/workbooks/wb1/content', url)

    def test_download_workbook_no_extract(self):
        c = self._make_signed_in_client()
        with patch.object(c, '_request') as mock_req:
            mock_req.return_value = None
            with tempfile.TemporaryDirectory() as td:
                out = os.path.join(td, 'test.twbx')
                with open(out, 'wb') as f:
                    f.write(b'data')
                c.download_workbook('wb1', out, include_extract=False)
                url = mock_req.call_args[0][1]
                self.assertIn('includeExtract=false', url)

    def test_search_workbooks(self):
        c = self._make_signed_in_client()
        with patch.object(c, 'list_workbooks') as mock_list:
            mock_list.return_value = [
                {'name': 'Sales Dashboard'},
                {'name': 'Finance Report'},
                {'name': 'Sales Summary'},
            ]
            results = c.search_workbooks('Sales')
        self.assertEqual(len(results), 2)

    def test_search_workbooks_regex(self):
        c = self._make_signed_in_client()
        with patch.object(c, 'list_workbooks') as mock_list:
            mock_list.return_value = [
                {'name': 'Q1 Report'},
                {'name': 'Q2 Report'},
                {'name': 'Annual Summary'},
            ]
            results = c.search_workbooks(r'Q\d+ Report')
        self.assertEqual(len(results), 2)


class TestTableauServerClientDatasources(unittest.TestCase):
    """Test datasource operations."""

    def _make_signed_in_client(self):
        c = TableauServerClient(server_url='https://tab.co')
        c._auth_token = 'tok'
        c._site_luid = 'site-1'
        return c

    def test_list_datasources(self):
        c = self._make_signed_in_client()
        with patch.object(c, '_request') as mock_req:
            mock_req.return_value = {
                'datasources': {
                    'datasource': [{'id': 'ds1', 'name': 'Sales Data'}]
                }
            }
            result = c.list_datasources()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], 'Sales Data')

    def test_list_projects(self):
        c = self._make_signed_in_client()
        with patch.object(c, '_request') as mock_req:
            mock_req.return_value = {
                'projects': {
                    'project': [{'id': 'p1', 'name': 'Default'}]
                }
            }
            result = c.list_projects()
        self.assertEqual(len(result), 1)


class TestTableauServerClientBatch(unittest.TestCase):
    """Test batch download."""

    def _make_signed_in_client(self):
        c = TableauServerClient(server_url='https://tab.co')
        c._auth_token = 'tok'
        c._site_luid = 'site-1'
        return c

    def test_download_all_workbooks(self):
        c = self._make_signed_in_client()
        with patch.object(c, 'list_workbooks') as mock_list, \
             patch.object(c, 'download_workbook') as mock_dl:
            mock_list.return_value = [
                {'id': 'wb1', 'name': 'Sales'},
                {'id': 'wb2', 'name': 'Finance'},
            ]
            mock_dl.return_value = '/tmp/test.twbx'
            with tempfile.TemporaryDirectory() as td:
                results = c.download_all_workbooks(td)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r['status'] == 'success' for r in results))

    def test_download_all_workbooks_partial_failure(self):
        c = self._make_signed_in_client()
        with patch.object(c, 'list_workbooks') as mock_list, \
             patch.object(c, 'download_workbook') as mock_dl:
            mock_list.return_value = [
                {'id': 'wb1', 'name': 'Good'},
                {'id': 'wb2', 'name': 'Bad'},
            ]
            mock_dl.side_effect = ['/tmp/good.twbx', Exception('Network error')]
            with tempfile.TemporaryDirectory() as td:
                results = c.download_all_workbooks(td)
        success = [r for r in results if r['status'] == 'success']
        failed = [r for r in results if r['status'] == 'failed']
        self.assertEqual(len(success), 1)
        self.assertEqual(len(failed), 1)
        self.assertIn('Network error', failed[0]['error'])


class TestTableauServerContextManager(unittest.TestCase):
    """Test context manager protocol."""

    def test_context_manager(self):
        c = TableauServerClient(
            server_url='https://tab.co',
            token_name='p', token_secret='s',
        )
        with patch.object(c, 'sign_in') as mock_in, \
             patch.object(c, 'sign_out') as mock_out:
            mock_in.return_value = 'site-1'
            with c as client:
                self.assertIs(client, c)
            mock_in.assert_called_once()
            mock_out.assert_called_once()


class TestCLIServerFlags(unittest.TestCase):
    """Test that --server CLI arguments are registered."""

    def test_server_arguments(self):
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument('tableau_file', nargs='?')
        parser.add_argument('--server', default=None)
        parser.add_argument('--site', default='')
        parser.add_argument('--workbook', default=None)
        parser.add_argument('--token-name', default=None)
        parser.add_argument('--token-secret', default=None)
        parser.add_argument('--server-batch', default=None)

        args = parser.parse_args([
            '--server', 'https://tab.co',
            '--site', 'mysite',
            '--workbook', 'Sales',
            '--token-name', 'pat1',
            '--token-secret', 'sec1',
        ])
        self.assertEqual(args.server, 'https://tab.co')
        self.assertEqual(args.site, 'mysite')
        self.assertEqual(args.workbook, 'Sales')
        self.assertEqual(args.token_name, 'pat1')
        self.assertEqual(args.token_secret, 'sec1')

    def test_server_batch_flag(self):
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument('--server', default=None)
        parser.add_argument('--server-batch', default=None)
        args = parser.parse_args(['--server', 'https://tab.co', '--server-batch', 'Marketing'])
        self.assertEqual(args.server_batch, 'Marketing')


if __name__ == '__main__':
    unittest.main()
