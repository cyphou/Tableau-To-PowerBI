"""
Tableau Server / Tableau Cloud REST API client.

Supports downloading workbooks (.twbx) from Tableau Server or
Tableau Cloud for migration. Handles authentication via:
  - Personal Access Token (PAT)
  - Username + password

Usage:
    client = TableauServerClient(
        server_url='https://tableau.company.com',
        token_name='my-pat',
        token_secret='secret...',
        site_id='my-site',
    )
    client.sign_in()
    workbooks = client.list_workbooks()
    client.download_workbook(workbooks[0]['id'], '/tmp/output.twbx')
    client.sign_out()
"""

import json
import logging
import os
import re
import urllib.error

logger = logging.getLogger(__name__)

# Tableau REST API version
DEFAULT_API_VERSION = '3.21'

# Default page size for paginated requests
DEFAULT_PAGE_SIZE = 100


class TableauServerClient:
    """Lightweight Tableau Server REST API client (stdlib only)."""

    def __init__(self, server_url=None, token_name=None, token_secret=None,
                 username=None, password=None, site_id='',
                 api_version=None):
        """Initialize client.

        Auth priority:
          1. PAT (token_name + token_secret)
          2. Username + password
          3. Environment variables: TABLEAU_SERVER, TABLEAU_TOKEN_NAME,
             TABLEAU_TOKEN_SECRET, TABLEAU_SITE_ID

        Args:
            server_url: Tableau Server base URL (e.g., https://tableau.example.com).
            token_name: Personal Access Token name.
            token_secret: Personal Access Token secret.
            username: Tableau username (password auth).
            password: Tableau password.
            site_id: Site content URL (empty string for Default site).
            api_version: REST API version (default: 3.21).
        """
        self.server_url = (server_url or os.environ.get('TABLEAU_SERVER', '')).rstrip('/')
        self.token_name = token_name or os.environ.get('TABLEAU_TOKEN_NAME')
        self.token_secret = token_secret or os.environ.get('TABLEAU_TOKEN_SECRET')
        self.username = username or os.environ.get('TABLEAU_USERNAME')
        self.password = password or os.environ.get('TABLEAU_PASSWORD')
        self.site_id = site_id or os.environ.get('TABLEAU_SITE_ID', '')
        self.api_version = api_version or DEFAULT_API_VERSION

        self._auth_token = None
        self._site_luid = None

    @property
    def base_url(self):
        return f'{self.server_url}/api/{self.api_version}'

    @property
    def site_url(self):
        if not self._site_luid:
            raise RuntimeError('Not signed in — call sign_in() first')
        return f'{self.base_url}/sites/{self._site_luid}'

    def _request(self, method, url, headers=None, data=None, json_body=None,
                 stream_to=None):
        """Make an HTTP request using requests or urllib fallback.

        Args:
            method: HTTP method.
            url: Full URL.
            headers: Request headers.
            data: Raw body bytes.
            json_body: JSON body (dict).
            stream_to: If set, write response body to this file path.

        Returns:
            dict or None: Parsed JSON response, or None for downloads.
        """
        hdrs = dict(headers or {})
        if self._auth_token:
            hdrs['X-Tableau-Auth'] = self._auth_token

        try:
            import requests as req_lib
            kwargs = {'headers': hdrs}
            if json_body is not None:
                kwargs['json'] = json_body
            elif data is not None:
                kwargs['data'] = data

            if stream_to:
                kwargs['stream'] = True
                resp = req_lib.request(method, url, **kwargs)
                resp.raise_for_status()
                with open(stream_to, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            f.write(chunk)
                return None
            else:
                resp = req_lib.request(method, url, **kwargs)
                resp.raise_for_status()
                if resp.content:
                    return resp.json()
                return {}
        except ImportError:
            pass

        # urllib fallback
        import urllib.request
        import urllib.error

        body = None
        if json_body is not None:
            body = json.dumps(json_body).encode('utf-8')
            hdrs['Content-Type'] = 'application/json'
        elif data is not None:
            body = data

        req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                if stream_to:
                    with open(stream_to, 'wb') as f:
                        while True:
                            chunk = resp.read(1024 * 256)
                            if not chunk:
                                break
                            f.write(chunk)
                    return None
                raw = resp.read()
                if raw:
                    return json.loads(raw.decode('utf-8'))
                return {}
        except urllib.error.HTTPError as e:
            body_text = e.read().decode('utf-8', errors='replace')
            raise RuntimeError(
                f'Tableau API error {e.code}: {body_text}'
            ) from e

    # ── Pagination helper ─────────────────────────────────────

    def _paginated_get(self, url, root_key, item_key,
                       page_size=DEFAULT_PAGE_SIZE):
        """Fetch all pages of a paginated REST API endpoint.

        Tableau REST API returns pagination metadata as:
            {"pagination": {"pageNumber": "1", "pageSize": "100", "totalAvailable": "250"}}

        Args:
            url: Base URL (without pageSize/pageNumber params).
            root_key: Top-level JSON key (e.g., 'workbooks').
            item_key: Nested key containing items (e.g., 'workbook').
            page_size: Items per page.

        Returns:
            list[dict]: All items across all pages.
        """
        all_items = []
        page_number = 1
        separator = '&' if '?' in url else '?'

        while True:
            paged_url = f'{url}{separator}pageSize={page_size}&pageNumber={page_number}'
            resp = self._request('GET', paged_url)

            items = resp.get(root_key, {}).get(item_key, [])
            all_items.extend(items)

            pagination = resp.get('pagination', {})
            total = int(pagination.get('totalAvailable', len(items)))
            if len(all_items) >= total or not items:
                break
            page_number += 1

        return all_items

    # ── Authentication ────────────────────────────────────────

    def sign_in(self):
        """Authenticate and obtain an auth token.

        Uses PAT if token_name/token_secret are set, otherwise
        falls back to username/password.

        Returns:
            str: The site LUID.
        """
        url = f'{self.base_url}/auth/signin'

        if self.token_name and self.token_secret:
            payload = {
                'credentials': {
                    'personalAccessTokenName': self.token_name,
                    'personalAccessTokenSecret': self.token_secret,
                    'site': {'contentUrl': self.site_id},
                }
            }
        elif self.username and self.password:
            payload = {
                'credentials': {
                    'name': self.username,
                    'password': self.password,
                    'site': {'contentUrl': self.site_id},
                }
            }
        else:
            raise ValueError(
                'No credentials provided. Set token_name/token_secret '
                'or username/password (or TABLEAU_TOKEN_NAME/TABLEAU_TOKEN_SECRET env vars).'
            )

        resp = self._request('POST', url, json_body=payload)
        creds = resp.get('credentials', {})
        self._auth_token = creds.get('token')
        self._site_luid = creds.get('site', {}).get('id')

        if not self._auth_token:
            raise RuntimeError('Sign-in failed — no token returned')

        logger.info(f'Signed in to {self.server_url} (site={self._site_luid})')
        return self._site_luid

    def sign_out(self):
        """Sign out and invalidate the auth token."""
        if self._auth_token:
            try:
                url = f'{self.base_url}/auth/signout'
                self._request('POST', url)
                logger.info('Signed out')
            except (urllib.error.URLError, OSError, RuntimeError) as e:
                logger.warning(f'Sign-out failed: {e}')
            finally:
                self._auth_token = None
                self._site_luid = None

    # ── Site info ─────────────────────────────────────────────

    def get_site_info(self):
        """Get site metadata.

        Returns:
            dict: Site info (id, name, contentUrl, state, etc.)
        """
        url = f'{self.base_url}/sites/{self._site_luid}'
        resp = self._request('GET', url)
        return resp.get('site', resp)

    # ── Workbooks ─────────────────────────────────────────────

    def list_workbooks(self, project_name=None):
        """List workbooks on the site (paginated).

        Args:
            project_name: Optional — filter by project name.

        Returns:
            list[dict]: Workbook metadata (id, name, project, contentUrl, etc.)
        """
        url = f'{self.site_url}/workbooks'
        if project_name:
            url += f'?filter=projectName:eq:{project_name}'

        workbooks = self._paginated_get(url, 'workbooks', 'workbook')
        logger.info(f'Found {len(workbooks)} workbooks')
        return workbooks

    def get_workbook(self, workbook_id):
        """Get workbook metadata by ID.

        Args:
            workbook_id: Workbook LUID.

        Returns:
            dict: Workbook metadata.
        """
        url = f'{self.site_url}/workbooks/{workbook_id}'
        resp = self._request('GET', url)
        return resp.get('workbook', resp)

    def get_workbook_connections(self, workbook_id):
        """Get data connections for a workbook.

        Args:
            workbook_id: Workbook LUID.

        Returns:
            list[dict]: Connection metadata (type, serverAddress, serverPort,
                        userName, dbClass, etc.)
        """
        url = f'{self.site_url}/workbooks/{workbook_id}/connections'
        resp = self._request('GET', url)
        return resp.get('connections', {}).get('connection', [])

    def download_workbook(self, workbook_id, output_path,
                          include_extract=True):
        """Download a workbook as .twbx.

        Args:
            workbook_id: Workbook LUID.
            output_path: Local file path to save the .twbx.
            include_extract: Include the data extract in the download.

        Returns:
            str: Path to the downloaded file.
        """
        url = f'{self.site_url}/workbooks/{workbook_id}/content'
        if not include_extract:
            url += '?includeExtract=false'

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        self._request('GET', url, stream_to=output_path)
        size = os.path.getsize(output_path)
        logger.info(f'Downloaded workbook {workbook_id} → {output_path} ({size} bytes)')
        return output_path

    def search_workbooks(self, name_pattern):
        """Search workbooks by name pattern.

        Args:
            name_pattern: Regex pattern to match workbook names.

        Returns:
            list[dict]: Matching workbooks.
        """
        all_wb = self.list_workbooks()
        pattern = re.compile(name_pattern, re.IGNORECASE)
        matches = [w for w in all_wb if pattern.search(w.get('name', ''))]
        return matches

    # ── Views ─────────────────────────────────────────────────

    def list_views(self):
        """List all views (sheets) on the site (paginated).

        Returns:
            list[dict]: View metadata (id, name, contentUrl, workbook, etc.)
        """
        url = f'{self.site_url}/views'
        return self._paginated_get(url, 'views', 'view')

    # ── Datasources ───────────────────────────────────────────

    def list_datasources(self):
        """List published datasources on the site (paginated).

        Returns:
            list[dict]: Datasource metadata.
        """
        url = f'{self.site_url}/datasources'
        return self._paginated_get(url, 'datasources', 'datasource')

    def download_datasource(self, datasource_id, output_path):
        """Download a published datasource as .tdsx.

        Args:
            datasource_id: Datasource LUID.
            output_path: Local file path.

        Returns:
            str: Path to the downloaded file.
        """
        url = f'{self.site_url}/datasources/{datasource_id}/content'
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        self._request('GET', url, stream_to=output_path)
        logger.info(f'Downloaded datasource {datasource_id} → {output_path}')
        return output_path

    # ── Projects ──────────────────────────────────────────────

    def list_projects(self):
        """List projects on the site (paginated).

        Returns:
            list[dict]: Project metadata.
        """
        url = f'{self.site_url}/projects'
        return self._paginated_get(url, 'projects', 'project')

    # ── Users ─────────────────────────────────────────────────

    def list_users(self):
        """List all users on the site (paginated).

        Returns:
            list[dict]: User metadata (id, name, siteRole, lastLogin, etc.)
        """
        url = f'{self.site_url}/users'
        return self._paginated_get(url, 'users', 'user')

    # ── Groups ────────────────────────────────────────────────

    def list_groups(self):
        """List all groups on the site (paginated).

        Returns:
            list[dict]: Group metadata (id, name, domain, etc.)
        """
        url = f'{self.site_url}/groups'
        return self._paginated_get(url, 'groups', 'group')

    # ── Schedules ─────────────────────────────────────────────

    def list_schedules(self):
        """List all schedules on the server (paginated).

        Returns:
            list[dict]: Schedule metadata (id, name, type, frequency, etc.)
        """
        url = f'{self.base_url}/schedules'
        return self._paginated_get(url, 'schedules', 'schedule')

    # ── Prep Flows ────────────────────────────────────────────

    def list_prep_flows(self):
        """List Prep flows on the site (paginated).

        Returns:
            list[dict]: Flow metadata (id, name, project, etc.)
        """
        url = f'{self.site_url}/flows'
        return self._paginated_get(url, 'flows', 'flow')

    def download_prep_flow(self, flow_id, output_path):
        """Download a Prep flow file.

        Args:
            flow_id: Flow LUID.
            output_path: Local file path to save the .tfl / .tflx.

        Returns:
            str: Path to the downloaded file.
        """
        url = f'{self.site_url}/flows/{flow_id}/content'
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        self._request('GET', url, stream_to=output_path)
        logger.info(f'Downloaded flow {flow_id} → {output_path}')
        return output_path

    # ── Server summary ────────────────────────────────────────

    def get_server_summary(self):
        """Collect a high-level summary of the Tableau Server site.

        Returns:
            dict: {workbook_count, datasource_count, user_count, group_count,
                   project_count, flow_count, schedule_count, view_count,
                   site_info}
        """
        site_info = self.get_site_info()
        workbooks = self.list_workbooks()
        datasources = self.list_datasources()
        users = self.list_users()
        groups = self.list_groups()
        projects = self.list_projects()
        flows = self.list_prep_flows()
        schedules = self.list_schedules()
        views = self.list_views()

        summary = {
            'site_info': site_info,
            'workbook_count': len(workbooks),
            'datasource_count': len(datasources),
            'user_count': len(users),
            'group_count': len(groups),
            'project_count': len(projects),
            'flow_count': len(flows),
            'schedule_count': len(schedules),
            'view_count': len(views),
        }
        logger.info(
            f"Server summary: {summary['workbook_count']} workbooks, "
            f"{summary['datasource_count']} datasources, "
            f"{summary['user_count']} users"
        )
        return summary

    # ── Batch download ────────────────────────────────────────

    def download_all_workbooks(self, output_dir, project_name=None):
        """Download all workbooks to a directory.

        Args:
            output_dir: Directory to save .twbx files.
            project_name: Optional project filter.

        Returns:
            list[dict]: Download results [{name, path, status, error?}].
        """
        workbooks = self.list_workbooks(project_name=project_name)
        os.makedirs(output_dir, exist_ok=True)
        results = []

        for wb in workbooks:
            wb_name = wb.get('name', 'unknown')
            safe_name = re.sub(r'[^\w\-.]', '_', wb_name)
            output_path = os.path.join(output_dir, f'{safe_name}.twbx')

            try:
                self.download_workbook(wb['id'], output_path)
                results.append({
                    'name': wb_name,
                    'path': output_path,
                    'status': 'success',
                })
            except (urllib.error.URLError, OSError, RuntimeError) as e:
                logger.error(f'Failed to download {wb_name}: {e}')
                results.append({
                    'name': wb_name,
                    'path': output_path,
                    'status': 'failed',
                    'error': str(e),
                })

        succeeded = sum(1 for r in results if r['status'] == 'success')
        logger.info(f'Downloaded {succeeded}/{len(results)} workbooks')
        return results

    # ── Context manager ───────────────────────────────────────

    def __enter__(self):
        self.sign_in()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.sign_out()
        return False
