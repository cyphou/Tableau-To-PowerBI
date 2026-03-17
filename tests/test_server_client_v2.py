"""
Tests for Sprint 49 — Tableau Server Client Enhancement.

Covers:
  - Pagination helper (_paginated_get)
  - New endpoints: list_users, list_groups, list_views,
    get_workbook_connections, list_schedules, get_site_info,
    list_prep_flows, download_prep_flow, get_server_summary
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tableau_export.server_client import TableauServerClient, DEFAULT_PAGE_SIZE


class TestPaginatedGet(unittest.TestCase):
    """Test the _paginated_get helper."""

    def _make_client(self):
        c = TableauServerClient(server_url='https://tab.co')
        c._auth_token = 'tok'
        c._site_luid = 'site-1'
        return c

    def test_single_page(self):
        c = self._make_client()
        with patch.object(c, '_request') as mock_req:
            mock_req.return_value = {
                'workbooks': {'workbook': [
                    {'id': '1', 'name': 'WB1'},
                    {'id': '2', 'name': 'WB2'},
                ]},
                'pagination': {
                    'pageNumber': '1', 'pageSize': '100', 'totalAvailable': '2'
                }
            }
            result = c._paginated_get(
                'https://tab.co/api/3.21/sites/site-1/workbooks',
                'workbooks', 'workbook'
            )
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['name'], 'WB1')

    def test_multiple_pages(self):
        c = self._make_client()
        with patch.object(c, '_request') as mock_req:
            mock_req.side_effect = [
                {
                    'users': {'user': [{'id': '1'}, {'id': '2'}]},
                    'pagination': {'pageNumber': '1', 'pageSize': '2', 'totalAvailable': '4'}
                },
                {
                    'users': {'user': [{'id': '3'}, {'id': '4'}]},
                    'pagination': {'pageNumber': '2', 'pageSize': '2', 'totalAvailable': '4'}
                },
            ]
            result = c._paginated_get(
                'https://tab.co/api/3.21/sites/site-1/users',
                'users', 'user', page_size=2
            )
        self.assertEqual(len(result), 4)
        self.assertEqual(mock_req.call_count, 2)

    def test_empty_response(self):
        c = self._make_client()
        with patch.object(c, '_request') as mock_req:
            mock_req.return_value = {
                'users': {'user': []},
                'pagination': {'pageNumber': '1', 'pageSize': '100', 'totalAvailable': '0'}
            }
            result = c._paginated_get(
                'https://tab.co/api/3.21/sites/site-1/users',
                'users', 'user'
            )
        self.assertEqual(result, [])

    def test_pagination_with_existing_query_params(self):
        """URL with existing ?filter= should use & for pagination params."""
        c = self._make_client()
        with patch.object(c, '_request') as mock_req:
            mock_req.return_value = {
                'workbooks': {'workbook': [{'id': '1'}]},
                'pagination': {'pageNumber': '1', 'pageSize': '100', 'totalAvailable': '1'}
            }
            c._paginated_get(
                'https://tab.co/api/3.21/sites/site-1/workbooks?filter=name:eq:test',
                'workbooks', 'workbook'
            )
        url = mock_req.call_args[0][1]
        self.assertIn('&pageSize=', url)
        self.assertNotIn('?pageSize=', url)

    def test_no_pagination_key_in_response(self):
        """When no pagination key in response, return available items."""
        c = self._make_client()
        with patch.object(c, '_request') as mock_req:
            mock_req.return_value = {
                'groups': {'group': [{'id': '1'}, {'id': '2'}]}
            }
            result = c._paginated_get(
                'https://tab.co/api/3.21/sites/site-1/groups',
                'groups', 'group'
            )
        self.assertEqual(len(result), 2)


class TestListUsers(unittest.TestCase):
    """Test list_users endpoint."""

    def _make_client(self):
        c = TableauServerClient(server_url='https://tab.co')
        c._auth_token = 'tok'
        c._site_luid = 'site-1'
        return c

    def test_list_users(self):
        c = self._make_client()
        with patch.object(c, '_paginated_get') as mock_pg:
            mock_pg.return_value = [
                {'id': 'u1', 'name': 'admin', 'siteRole': 'SiteAdministrator'},
                {'id': 'u2', 'name': 'viewer', 'siteRole': 'Viewer'},
            ]
            result = c.list_users()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['name'], 'admin')
        mock_pg.assert_called_once()
        call_args = mock_pg.call_args
        self.assertIn('/users', call_args[0][0])


class TestListGroups(unittest.TestCase):
    """Test list_groups endpoint."""

    def _make_client(self):
        c = TableauServerClient(server_url='https://tab.co')
        c._auth_token = 'tok'
        c._site_luid = 'site-1'
        return c

    def test_list_groups(self):
        c = self._make_client()
        with patch.object(c, '_paginated_get') as mock_pg:
            mock_pg.return_value = [
                {'id': 'g1', 'name': 'Sales Team'},
            ]
            result = c.list_groups()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], 'Sales Team')


class TestListViews(unittest.TestCase):
    """Test list_views endpoint."""

    def _make_client(self):
        c = TableauServerClient(server_url='https://tab.co')
        c._auth_token = 'tok'
        c._site_luid = 'site-1'
        return c

    def test_list_views(self):
        c = self._make_client()
        with patch.object(c, '_paginated_get') as mock_pg:
            mock_pg.return_value = [
                {'id': 'v1', 'name': 'Sales Sheet', 'contentUrl': 'sales'},
            ]
            result = c.list_views()
        self.assertEqual(len(result), 1)
        self.assertIn('/views', mock_pg.call_args[0][0])


class TestGetWorkbookConnections(unittest.TestCase):
    """Test get_workbook_connections endpoint."""

    def _make_client(self):
        c = TableauServerClient(server_url='https://tab.co')
        c._auth_token = 'tok'
        c._site_luid = 'site-1'
        return c

    def test_get_connections(self):
        c = self._make_client()
        with patch.object(c, '_request') as mock_req:
            mock_req.return_value = {
                'connections': {'connection': [
                    {'type': 'postgres', 'serverAddress': 'db.co', 'serverPort': '5432'},
                ]}
            }
            result = c.get_workbook_connections('wb-123')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['type'], 'postgres')
        url = mock_req.call_args[0][1]
        self.assertIn('/workbooks/wb-123/connections', url)

    def test_get_connections_empty(self):
        c = self._make_client()
        with patch.object(c, '_request') as mock_req:
            mock_req.return_value = {'connections': {'connection': []}}
            result = c.get_workbook_connections('wb-123')
        self.assertEqual(result, [])


class TestListSchedules(unittest.TestCase):
    """Test list_schedules endpoint."""

    def _make_client(self):
        c = TableauServerClient(server_url='https://tab.co')
        c._auth_token = 'tok'
        c._site_luid = 'site-1'
        return c

    def test_list_schedules(self):
        c = self._make_client()
        with patch.object(c, '_paginated_get') as mock_pg:
            mock_pg.return_value = [
                {'id': 's1', 'name': 'Daily Extract', 'type': 'Extract'},
            ]
            result = c.list_schedules()
        self.assertEqual(len(result), 1)
        # Schedules are at base_url level (not site_url)
        url = mock_pg.call_args[0][0]
        self.assertIn('/schedules', url)


class TestGetSiteInfo(unittest.TestCase):
    """Test get_site_info endpoint."""

    def _make_client(self):
        c = TableauServerClient(server_url='https://tab.co')
        c._auth_token = 'tok'
        c._site_luid = 'site-1'
        return c

    def test_get_site_info(self):
        c = self._make_client()
        with patch.object(c, '_request') as mock_req:
            mock_req.return_value = {
                'site': {
                    'id': 'site-1', 'name': 'Default', 'contentUrl': '',
                    'state': 'Active'
                }
            }
            result = c.get_site_info()
        self.assertEqual(result['name'], 'Default')
        self.assertEqual(result['state'], 'Active')


class TestPrepFlows(unittest.TestCase):
    """Test Prep flow endpoints."""

    def _make_client(self):
        c = TableauServerClient(server_url='https://tab.co')
        c._auth_token = 'tok'
        c._site_luid = 'site-1'
        return c

    def test_list_prep_flows(self):
        c = self._make_client()
        with patch.object(c, '_paginated_get') as mock_pg:
            mock_pg.return_value = [
                {'id': 'f1', 'name': 'ETL Flow'},
            ]
            result = c.list_prep_flows()
        self.assertEqual(len(result), 1)
        self.assertIn('/flows', mock_pg.call_args[0][0])

    def test_download_prep_flow(self):
        c = self._make_client()
        with patch.object(c, '_request') as mock_req:
            mock_req.return_value = None
            with tempfile.TemporaryDirectory() as td:
                out = os.path.join(td, 'flow.tfl')
                with open(out, 'w') as f:
                    f.write('{}')
                result = c.download_prep_flow('f1', out)
                self.assertEqual(result, out)
                url = mock_req.call_args[0][1]
                self.assertIn('/flows/f1/content', url)


class TestGetServerSummary(unittest.TestCase):
    """Test get_server_summary aggregation."""

    def _make_client(self):
        c = TableauServerClient(server_url='https://tab.co')
        c._auth_token = 'tok'
        c._site_luid = 'site-1'
        return c

    def test_server_summary(self):
        c = self._make_client()
        with patch.object(c, 'get_site_info') as m_si, \
             patch.object(c, 'list_workbooks') as m_wb, \
             patch.object(c, 'list_datasources') as m_ds, \
             patch.object(c, 'list_users') as m_u, \
             patch.object(c, 'list_groups') as m_g, \
             patch.object(c, 'list_projects') as m_p, \
             patch.object(c, 'list_prep_flows') as m_f, \
             patch.object(c, 'list_schedules') as m_s, \
             patch.object(c, 'list_views') as m_v:
            m_si.return_value = {'name': 'Default'}
            m_wb.return_value = [{'id': '1'}, {'id': '2'}]
            m_ds.return_value = [{'id': 'd1'}]
            m_u.return_value = [{'id': 'u1'}, {'id': 'u2'}, {'id': 'u3'}]
            m_g.return_value = [{'id': 'g1'}]
            m_p.return_value = [{'id': 'p1'}, {'id': 'p2'}]
            m_f.return_value = []
            m_s.return_value = [{'id': 's1'}]
            m_v.return_value = [{'id': 'v1'}, {'id': 'v2'}]

            summary = c.get_server_summary()

        self.assertEqual(summary['workbook_count'], 2)
        self.assertEqual(summary['datasource_count'], 1)
        self.assertEqual(summary['user_count'], 3)
        self.assertEqual(summary['group_count'], 1)
        self.assertEqual(summary['project_count'], 2)
        self.assertEqual(summary['flow_count'], 0)
        self.assertEqual(summary['schedule_count'], 1)
        self.assertEqual(summary['view_count'], 2)
        self.assertEqual(summary['site_info']['name'], 'Default')


class TestPaginatedListWorkbooks(unittest.TestCase):
    """Test that list_workbooks now uses pagination."""

    def _make_client(self):
        c = TableauServerClient(server_url='https://tab.co')
        c._auth_token = 'tok'
        c._site_luid = 'site-1'
        return c

    def test_list_workbooks_uses_pagination(self):
        """list_workbooks should call _paginated_get instead of _request."""
        c = self._make_client()
        with patch.object(c, '_paginated_get') as mock_pg:
            mock_pg.return_value = [{'id': '1', 'name': 'WB1'}]
            result = c.list_workbooks()
        self.assertEqual(len(result), 1)
        mock_pg.assert_called_once()

    def test_list_workbooks_with_project_passes_filter(self):
        c = self._make_client()
        with patch.object(c, '_paginated_get') as mock_pg:
            mock_pg.return_value = []
            c.list_workbooks(project_name='Marketing')
        url = mock_pg.call_args[0][0]
        self.assertIn('filter=projectName:eq:Marketing', url)


class TestPaginatedListDatasources(unittest.TestCase):
    """Test that list_datasources now uses pagination."""

    def _make_client(self):
        c = TableauServerClient(server_url='https://tab.co')
        c._auth_token = 'tok'
        c._site_luid = 'site-1'
        return c

    def test_list_datasources_uses_pagination(self):
        c = self._make_client()
        with patch.object(c, '_paginated_get') as mock_pg:
            mock_pg.return_value = [{'id': 'd1'}]
            result = c.list_datasources()
        self.assertEqual(len(result), 1)
        mock_pg.assert_called_once()


class TestPaginatedListProjects(unittest.TestCase):
    """Test that list_projects now uses pagination."""

    def _make_client(self):
        c = TableauServerClient(server_url='https://tab.co')
        c._auth_token = 'tok'
        c._site_luid = 'site-1'
        return c

    def test_list_projects_uses_pagination(self):
        c = self._make_client()
        with patch.object(c, '_paginated_get') as mock_pg:
            mock_pg.return_value = [{'id': 'p1'}]
            result = c.list_projects()
        self.assertEqual(len(result), 1)
        mock_pg.assert_called_once()


if __name__ == '__main__':
    unittest.main()
