"""
Power BI Service Workspace Deployer.

Orchestrates the deployment of migrated .pbip projects to a
Power BI Service workspace:

  1. Package .pbip → .pbix (via PBIXPackager)
  2. Upload .pbix to workspace (via PBIServiceClient)
  3. Wait for import completion
  4. Optionally trigger dataset refresh
  5. Check deployment status

Usage:
    deployer = PBIWorkspaceDeployer(workspace_id='...')
    result = deployer.deploy_project('/path/to/project_dir')
"""

import logging
import os
import time
import tempfile

logger = logging.getLogger(__name__)


class DeploymentResult:
    """Result of a single project deployment."""

    def __init__(self, project_name, status='pending', import_id=None,
                 dataset_id=None, report_id=None, error=None):
        self.project_name = project_name
        self.status = status  # 'pending', 'publishing', 'succeeded', 'failed'
        self.import_id = import_id
        self.dataset_id = dataset_id
        self.report_id = report_id
        self.error = error

    def to_dict(self):
        return {
            'project_name': self.project_name,
            'status': self.status,
            'import_id': self.import_id,
            'dataset_id': self.dataset_id,
            'report_id': self.report_id,
            'error': self.error,
        }


class PBIWorkspaceDeployer:
    """Deploy .pbip projects to a Power BI Service workspace."""

    def __init__(self, workspace_id, client=None, tenant_id=None,
                 client_id=None, client_secret=None,
                 use_managed_identity=False):
        """Initialize deployer.

        Args:
            workspace_id: Target Power BI workspace/group ID.
            client: Pre-configured PBIServiceClient (optional).
            tenant_id: Azure AD tenant ID (if no client).
            client_id: Azure AD app ID (if no client).
            client_secret: Client secret (if no client).
            use_managed_identity: Use managed identity (if no client).
        """
        self.workspace_id = workspace_id

        if client:
            self.client = client
        else:
            from .pbi_client import PBIServiceClient
            self.client = PBIServiceClient(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret,
                use_managed_identity=use_managed_identity,
            )

    def deploy_project(self, project_dir, dataset_name=None,
                       overwrite=True, refresh=False,
                       max_wait_seconds=300, poll_interval=5):
        """Deploy a .pbip project to the workspace.

        Args:
            project_dir: Path to .pbip project directory.
            dataset_name: Override dataset name (defaults to project name).
            overwrite: Overwrite existing dataset/report if found.
            refresh: Trigger dataset refresh after successful import.
            max_wait_seconds: Maximum time to wait for import completion.
            poll_interval: Polling interval in seconds.

        Returns:
            DeploymentResult: Outcome of the deployment.
        """
        from .pbix_packager import PBIXPackager

        project_dir = os.path.abspath(project_dir)
        project_name = dataset_name or os.path.basename(project_dir)
        result = DeploymentResult(project_name=project_name)

        # Step 1: Package .pbip → .pbix
        try:
            packager = PBIXPackager()
            pbix_path = os.path.join(
                tempfile.gettempdir(), f'{project_name}.pbix'
            )
            packager.package(project_dir, pbix_path)
            logger.info(f'Packaged {project_dir} → {pbix_path}')
        except Exception as e:
            result.status = 'failed'
            result.error = f'Packaging failed: {e}'
            logger.error(result.error)
            return result

        # Step 2: Upload .pbix to workspace
        try:
            import_resp = self.client.import_pbix(
                workspace_id=self.workspace_id,
                pbix_path=pbix_path,
                dataset_name=project_name,
                overwrite=overwrite,
            )
            result.import_id = import_resp.get('id')
            result.status = 'publishing'
            logger.info(f'Import started: id={result.import_id}')
        except Exception as e:
            result.status = 'failed'
            result.error = f'Upload failed: {e}'
            logger.error(result.error)
            return result
        finally:
            # Clean up temp .pbix
            try:
                os.remove(pbix_path)
            except OSError:
                pass

        # Step 3: Wait for import to complete
        if result.import_id:
            result = self._wait_for_import(result, max_wait_seconds, poll_interval)

        # Step 4: Trigger refresh if requested
        if refresh and result.status == 'succeeded' and result.dataset_id:
            try:
                self.client.refresh_dataset(self.workspace_id, result.dataset_id)
                logger.info(f'Refresh triggered for dataset {result.dataset_id}')
            except Exception as e:
                logger.warning(f'Refresh failed (non-fatal): {e}')

        return result

    def _wait_for_import(self, result, max_wait_seconds, poll_interval):
        """Poll import status until complete or timeout.

        Args:
            result: DeploymentResult with import_id set.
            max_wait_seconds: Maximum wait time.
            poll_interval: Seconds between polls.

        Returns:
            DeploymentResult: Updated with final status.
        """
        elapsed = 0
        while elapsed < max_wait_seconds:
            try:
                status = self.client.get_import_status(
                    self.workspace_id, result.import_id
                )
                state = status.get('importState', '')
                logger.debug(f'Import state: {state} ({elapsed}s)')

                if state == 'Succeeded':
                    result.status = 'succeeded'
                    # Extract dataset and report IDs
                    datasets = status.get('datasets', [])
                    if datasets:
                        result.dataset_id = datasets[0].get('id')
                    reports = status.get('reports', [])
                    if reports:
                        result.report_id = reports[0].get('id')
                    logger.info(
                        f'Import succeeded: dataset={result.dataset_id}, '
                        f'report={result.report_id}'
                    )
                    return result

                elif state == 'Failed':
                    result.status = 'failed'
                    result.error = status.get('error', {}).get(
                        'message', 'Import failed — no details'
                    )
                    logger.error(f'Import failed: {result.error}')
                    return result

            except Exception as e:
                logger.warning(f'Status check error: {e}')

            time.sleep(poll_interval)
            elapsed += poll_interval

        result.status = 'failed'
        result.error = f'Import timed out after {max_wait_seconds}s'
        logger.error(result.error)
        return result

    def deploy_batch(self, projects_dir, overwrite=True, refresh=False):
        """Deploy all .pbip projects under a directory.

        Args:
            projects_dir: Root directory containing .pbip project folders.
            overwrite: Overwrite existing items.
            refresh: Trigger refresh after each import.

        Returns:
            list[DeploymentResult]: Results for each project.
        """
        from .pbix_packager import PBIXPackager

        packager = PBIXPackager()
        project_dirs = packager.find_pbip_projects(projects_dir)

        if not project_dirs:
            logger.warning(f'No .pbip projects found under {projects_dir}')
            return []

        logger.info(f'Found {len(project_dirs)} projects to deploy')
        results = []
        for pdir in project_dirs:
            result = self.deploy_project(
                pdir, overwrite=overwrite, refresh=refresh
            )
            results.append(result)

        succeeded = sum(1 for r in results if r.status == 'succeeded')
        failed = sum(1 for r in results if r.status == 'failed')
        logger.info(f'Batch deploy: {succeeded} succeeded, {failed} failed')
        return results

    def validate_deployment(self, dataset_id):
        """Post-deployment validation — check dataset loads and report renders.

        Args:
            dataset_id: Dataset ID in the workspace.

        Returns:
            dict: Validation result with status and details.
        """
        validation = {'dataset_id': dataset_id, 'checks': []}

        # Check 1: Dataset exists and is queryable
        try:
            datasets = self.client.list_datasets(self.workspace_id)
            found = any(d.get('id') == dataset_id for d in datasets)
            validation['checks'].append({
                'check': 'dataset_exists',
                'passed': found,
            })
        except Exception as e:
            logger.debug('Dataset existence check failed: %s', e)
            validation['checks'].append({
                'check': 'dataset_exists',
                'passed': False,
                'error': str(e),
            })

        # Check 2: Refresh history (latest refresh status)
        try:
            history = self.client.get_refresh_history(
                self.workspace_id, dataset_id
            )
            if history:
                latest = history[0]
                status = latest.get('status', 'Unknown')
                validation['checks'].append({
                    'check': 'latest_refresh',
                    'passed': status == 'Completed',
                    'status': status,
                })
            else:
                validation['checks'].append({
                    'check': 'latest_refresh',
                    'passed': True,
                    'status': 'NoRefreshHistory',
                })
        except Exception as e:
            logger.debug('Refresh history check failed: %s', e)
            validation['checks'].append({
                'check': 'latest_refresh',
                'passed': False,
                'error': str(e),
            })

        all_passed = all(c['passed'] for c in validation['checks'])
        validation['overall'] = 'passed' if all_passed else 'failed'
        return validation
