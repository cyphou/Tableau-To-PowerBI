"""
Fabric artifact deployment module.

Deploys generated Power BI projects to a Microsoft Fabric workspace
via the Fabric REST API.

Requires:
    - azure-identity (pip install azure-identity)
    - requests (pip install requests) — optional, falls back to urllib

Usage:
    from deployer import FabricDeployer
    deployer = FabricDeployer()
    deployer.deploy_dataset(workspace_id, 'MyDataset', config)
"""

import os
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ArtifactType:
    """Supported Fabric artifact types."""
    DATASET = 'Dataset'
    DATAFLOW = 'Dataflow'
    REPORT = 'Report'
    NOTEBOOK = 'Notebook'
    LAKEHOUSE = 'Lakehouse'
    WAREHOUSE = 'Warehouse'
    PIPELINE = 'Pipeline'
    SEMANTIC_MODEL = 'SemanticModel'


class FabricDeployer:
    """Deploy Fabric artifacts to a workspace."""

    def __init__(self, client=None):
        """
        Initialize Fabric Deployer.

        Args:
            client: FabricClient instance (creates default if None)
        """
        if client is None:
            from .client import FabricClient
            client = FabricClient()
        self.client = client

    def deploy_dataset(self, workspace_id, dataset_name, dataset_config,
                       overwrite=True):
        """
        Deploy a dataset / semantic model to a workspace.

        Args:
            workspace_id: Target workspace ID
            dataset_name: Name of the dataset
            dataset_config: Dataset configuration dict
            overwrite: Overwrite if exists

        Returns:
            Deployment result dict
        """
        logger.info(f'Deploying dataset: {dataset_name}')

        existing = self._find_item(workspace_id, dataset_name,
                                    ArtifactType.DATASET)

        if existing and overwrite:
            logger.info(f'Overwriting existing dataset: {existing["id"]}')
            result = self.client.put(
                f'/workspaces/{workspace_id}/items/{existing["id"]}',
                data=dataset_config,
            )
        else:
            result = self.client.post(
                f'/workspaces/{workspace_id}/items',
                data={
                    'displayName': dataset_name,
                    'type': ArtifactType.DATASET,
                    'definition': dataset_config,
                },
            )

        logger.info(f'Dataset deployed: {result.get("id", "?")}')
        return result

    def deploy_report(self, workspace_id, report_name, report_config,
                      overwrite=True):
        """
        Deploy a report to a workspace.

        Args:
            workspace_id: Target workspace ID
            report_name: Name of the report
            report_config: Report configuration dict
            overwrite: Overwrite if exists

        Returns:
            Deployment result dict
        """
        logger.info(f'Deploying report: {report_name}')

        existing = self._find_item(workspace_id, report_name,
                                    ArtifactType.REPORT)

        if existing and overwrite:
            logger.info(f'Overwriting existing report: {existing["id"]}')
            result = self.client.put(
                f'/workspaces/{workspace_id}/items/{existing["id"]}',
                data=report_config,
            )
        else:
            result = self.client.post(
                f'/workspaces/{workspace_id}/items',
                data={
                    'displayName': report_name,
                    'type': ArtifactType.REPORT,
                    'definition': report_config,
                },
            )

        logger.info(f'Report deployed: {result.get("id", "?")}')
        return result

    def deploy_from_file(self, workspace_id, artifact_path, artifact_type,
                         overwrite=True):
        """
        Deploy an artifact from a JSON file.

        Args:
            workspace_id: Target workspace ID
            artifact_path: Path to artifact JSON file
            artifact_type: Type (Dataset, Report, etc.)
            overwrite: Overwrite if exists

        Returns:
            Deployment result dict
        """
        artifact_path = Path(artifact_path)
        logger.info(f'Loading artifact from: {artifact_path}')

        with open(artifact_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        artifact_name = config.get('displayName') or artifact_path.stem

        if artifact_type == ArtifactType.DATASET:
            return self.deploy_dataset(workspace_id, artifact_name, config,
                                        overwrite)
        elif artifact_type == ArtifactType.REPORT:
            return self.deploy_report(workspace_id, artifact_name, config,
                                       overwrite)
        else:
            raise ValueError(f'Unsupported artifact type: {artifact_type}')

    def deploy_artifacts_batch(self, workspace_id, artifacts_dir,
                               overwrite=True):
        """
        Deploy all artifacts from a directory.

        Args:
            workspace_id: Target workspace ID
            artifacts_dir: Directory containing artifact JSON files
            overwrite: Overwrite existing artifacts

        Returns:
            List of deployment results
        """
        artifacts_dir = Path(artifacts_dir)
        results = []

        for artifact_file in sorted(artifacts_dir.glob('*.json')):
            try:
                logger.info(f'Processing: {artifact_file.name}')
                with open(artifact_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)

                artifact_type = config.get('type', ArtifactType.DATASET)
                result = self.deploy_from_file(
                    workspace_id, artifact_file, artifact_type, overwrite,
                )
                results.append({'file': str(artifact_file), 'result': result})
            except Exception as e:
                logger.error(f'Failed to deploy {artifact_file.name}: {e}')
                results.append({'file': str(artifact_file), 'error': str(e)})

        return results

    def _find_item(self, workspace_id, item_name, item_type):
        """
        Find an item by name and type in a workspace.

        Args:
            workspace_id: Workspace ID
            item_name: Item name
            item_type: Item type

        Returns:
            Item dict if found, None otherwise
        """
        try:
            items = self.client.list_items(workspace_id, item_type)
            for item in items.get('value', []):
                if item.get('displayName') == item_name:
                    return item
            return None
        except Exception as e:
            logger.warning(f'Failed to search for item: {e}')
            return None

    def get_deployment_status(self, workspace_id, item_id):
        """
        Get deployment or item status.

        Args:
            workspace_id: Workspace ID
            item_id: Item ID

        Returns:
            Status dict
        """
        return self.client.get(
            f'/workspaces/{workspace_id}/items/{item_id}'
        )

    def deploy_shared_model(self, workspace_id, project_dir,
                             model_name, report_names,
                             overwrite=True):
        """Deploy a shared semantic model + thin reports atomically.

        Deploys the semantic model first, then each thin report.
        If any report fails, logs the error and continues with remaining.

        Args:
            workspace_id: Target workspace ID.
            project_dir: Root project directory containing model + reports.
            model_name: Name of the shared semantic model.
            report_names: List of thin report names to deploy.
            overwrite: Overwrite existing artifacts.

        Returns:
            DeploymentResult dict with status per artifact.
        """
        from pathlib import Path

        result = {
            'model_name': model_name,
            'workspace_id': workspace_id,
            'model_status': 'pending',
            'model_id': None,
            'reports': [],
            'success': True,
        }

        project_path = Path(project_dir)

        # Step 1: Deploy the semantic model first
        logger.info(
            "Deploying shared semantic model '%s' to workspace %s",
            model_name, workspace_id,
        )
        sm_dir = project_path / f"{model_name}.SemanticModel"
        if sm_dir.is_dir():
            try:
                sm_config = self._read_artifact_config(sm_dir)
                sm_result = self.deploy_dataset(
                    workspace_id, model_name, sm_config, overwrite,
                )
                result['model_status'] = 'deployed'
                result['model_id'] = sm_result.get('id')
                logger.info("Semantic model deployed: %s", result['model_id'])
            except Exception as e:
                logger.error("Failed to deploy semantic model: %s", e)
                result['model_status'] = 'failed'
                result['model_error'] = str(e)
                result['success'] = False
                return result  # Can't deploy reports without model
        else:
            logger.warning("SemanticModel directory not found: %s", sm_dir)
            result['model_status'] = 'not_found'
            result['success'] = False
            return result

        # Step 2: Deploy each thin report
        for report_name in report_names:
            report_result = {
                'name': report_name,
                'status': 'pending',
                'id': None,
            }

            report_dir = project_path / f"{report_name}.Report"
            if not report_dir.is_dir():
                report_result['status'] = 'not_found'
                result['reports'].append(report_result)
                logger.warning("Report directory not found: %s", report_dir)
                continue

            try:
                rpt_config = self._read_artifact_config(report_dir)
                rpt_result = self.deploy_report(
                    workspace_id, report_name, rpt_config, overwrite,
                )
                report_result['status'] = 'deployed'
                report_result['id'] = rpt_result.get('id')
                logger.info("Report deployed: %s (%s)",
                            report_name, report_result['id'])
            except Exception as e:
                logger.error(
                    "Failed to deploy report '%s': %s", report_name, e,
                )
                report_result['status'] = 'failed'
                report_result['error'] = str(e)
                result['success'] = False

            result['reports'].append(report_result)

        deployed_count = sum(
            1 for r in result['reports'] if r['status'] == 'deployed'
        )
        logger.info(
            "Shared model deployment: model=%s, reports=%d/%d",
            result['model_status'], deployed_count, len(report_names),
        )
        return result

    def _read_artifact_config(self, artifact_dir):
        """Read artifact configuration from a directory.

        Looks for definition files (*.json, *.pbir, *.pbism) in the directory.

        Args:
            artifact_dir: Path to the artifact directory.

        Returns:
            dict: Configuration suitable for deployment API.
        """
        from pathlib import Path

        artifact_dir = Path(artifact_dir)
        config = {'displayName': artifact_dir.stem.replace('.SemanticModel', '')
                                               .replace('.Report', '')}

        # Read definition files
        definition_dir = artifact_dir / 'definition'
        if definition_dir.is_dir():
            parts = {}
            for f in sorted(definition_dir.rglob('*')):
                if f.is_file():
                    rel = str(f.relative_to(definition_dir)).replace('\\', '/')
                    try:
                        parts[rel] = f.read_text(encoding='utf-8')
                    except Exception:
                        parts[rel] = f.read_bytes().hex()
            config['definition'] = parts

        return config
