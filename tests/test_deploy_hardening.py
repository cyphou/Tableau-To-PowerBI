"""Tests for Sprint 63 — Deploy Hardening & Fabric Reliability."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from powerbi_import.deploy.bundle_deployer import (
    BundleDeployer,
    BundleDeploymentResult,
)
from powerbi_import.deploy.utils import DeploymentManifest


# ── BundleDeploymentResult tests ──

class TestBundleDeploymentResultFields(unittest.TestCase):

    def test_new_fields_present(self):
        r = BundleDeploymentResult('/tmp', 'ws-1')
        self.assertEqual(r.rollback_actions, [])
        self.assertEqual(r.validation, [])
        self.assertEqual(r.conflicts, [])

    def test_to_dict_includes_new_fields(self):
        r = BundleDeploymentResult('/tmp', 'ws-1')
        r.rollback_actions.append({'action': 'delete_model', 'artifact': 'M', 'status': 'success'})
        r.validation.append({'check': 'model_status', 'status': 'ok', 'detail': ''})
        r.conflicts.append({'name': 'M', 'type': 'SemanticModel', 'existing_id': 'x'})
        d = r.to_dict()
        self.assertEqual(len(d['rollback_actions']), 1)
        self.assertEqual(len(d['validation']), 1)
        self.assertEqual(len(d['conflicts']), 1)


# ── Permission pre-flight tests ──

class TestCheckWorkspacePermissions(unittest.TestCase):

    def _make_deployer(self, ws_response=None, ws_error=None):
        client = MagicMock()
        if ws_error:
            client.get.side_effect = ws_error
        else:
            client.get.return_value = ws_response or {}
        d = BundleDeployer('ws-1', client=client)
        return d

    def test_admin_ok(self):
        d = self._make_deployer({'role': 'Admin'})
        result = d.check_workspace_permissions()
        self.assertTrue(result['ok'])
        self.assertEqual(result['role'], 'Admin')

    def test_contributor_ok(self):
        d = self._make_deployer({'role': 'Contributor'})
        result = d.check_workspace_permissions()
        self.assertTrue(result['ok'])

    def test_member_ok(self):
        d = self._make_deployer({'role': 'Member'})
        result = d.check_workspace_permissions()
        self.assertTrue(result['ok'])

    def test_viewer_rejected(self):
        d = self._make_deployer({'role': 'Viewer'})
        result = d.check_workspace_permissions()
        self.assertFalse(result['ok'])
        self.assertIn('Insufficient', result['detail'])

    def test_network_error(self):
        d = self._make_deployer(ws_error=ConnectionError('timeout'))
        result = d.check_workspace_permissions()
        self.assertFalse(result['ok'])
        self.assertIn('timeout', result['detail'])

    def test_missing_role_passes(self):
        """When role field is absent, we assume sufficient permissions."""
        d = self._make_deployer({'id': 'ws-1', 'displayName': 'Test'})
        result = d.check_workspace_permissions()
        self.assertTrue(result['ok'])


# ── Conflict detection tests ──

class TestDetectConflicts(unittest.TestCase):

    def _make_deployer(self, items=None):
        client = MagicMock()
        client.get.return_value = {'value': items or []}
        return BundleDeployer('ws-1', client=client)

    def test_no_conflicts(self):
        d = self._make_deployer([
            {'displayName': 'Other', 'type': 'Report', 'id': '1'},
        ])
        conflicts = d.detect_conflicts('MyModel', ['Report1'])
        self.assertEqual(conflicts, [])

    def test_model_conflict(self):
        d = self._make_deployer([
            {'displayName': 'MyModel', 'type': 'SemanticModel', 'id': 'x'},
        ])
        conflicts = d.detect_conflicts('MyModel', [])
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]['name'], 'MyModel')

    def test_report_conflict(self):
        d = self._make_deployer([
            {'displayName': 'R1', 'type': 'Report', 'id': 'r1'},
        ])
        conflicts = d.detect_conflicts('Model', ['R1'])
        self.assertEqual(len(conflicts), 1)

    def test_multiple_conflicts(self):
        d = self._make_deployer([
            {'displayName': 'Model', 'type': 'SemanticModel', 'id': 'm'},
            {'displayName': 'R1', 'type': 'Report', 'id': 'r1'},
            {'displayName': 'R2', 'type': 'Report', 'id': 'r2'},
        ])
        conflicts = d.detect_conflicts('Model', ['R1', 'R2'])
        self.assertEqual(len(conflicts), 3)

    def test_api_error_returns_empty(self):
        client = MagicMock()
        client.get.side_effect = Exception('API error')
        d = BundleDeployer('ws-1', client=client)
        conflicts = d.detect_conflicts('Model', ['R1'])
        self.assertEqual(conflicts, [])


# ── Rollback tests ──

class TestRollback(unittest.TestCase):

    def test_rollback_model(self):
        client = MagicMock()
        d = BundleDeployer('ws-1', client=client)
        result = BundleDeploymentResult('/tmp', 'ws-1')
        result.model_id = 'model-id'
        result.model_status = 'deployed'
        result.model_name = 'TestModel'
        d.rollback(result)
        client.delete.assert_called_once()
        self.assertEqual(len(result.rollback_actions), 1)
        self.assertEqual(result.rollback_actions[0]['status'], 'success')

    def test_rollback_model_and_reports(self):
        client = MagicMock()
        d = BundleDeployer('ws-1', client=client)
        result = BundleDeploymentResult('/tmp', 'ws-1')
        result.model_id = 'model-id'
        result.model_status = 'deployed'
        result.model_name = 'M'
        result.reports = [
            {'name': 'R1', 'status': 'deployed', 'id': 'r1'},
            {'name': 'R2', 'status': 'failed', 'id': None},
        ]
        d.rollback(result)
        # model + 1 deployed report = 2 delete calls
        self.assertEqual(client.delete.call_count, 2)
        self.assertEqual(len(result.rollback_actions), 2)

    def test_rollback_failure(self):
        client = MagicMock()
        client.delete.side_effect = Exception('delete fail')
        d = BundleDeployer('ws-1', client=client)
        result = BundleDeploymentResult('/tmp', 'ws-1')
        result.model_id = 'model-id'
        result.model_status = 'deployed'
        result.model_name = 'M'
        d.rollback(result)
        self.assertIn('failed', result.rollback_actions[0]['status'])

    def test_no_rollback_if_not_deployed(self):
        client = MagicMock()
        d = BundleDeployer('ws-1', client=client)
        result = BundleDeploymentResult('/tmp', 'ws-1')
        result.model_status = 'failed'
        d.rollback(result)
        client.delete.assert_not_called()


# ── Validation tests ──

class TestValidateDeployment(unittest.TestCase):

    def _make_deployer(self, status_resp=None):
        client = MagicMock()
        deployer_mock = MagicMock()
        deployer_mock.get_deployment_status.return_value = status_resp or {'status': 'Succeeded'}
        d = BundleDeployer('ws-1', client=client)
        d._deployer = deployer_mock
        return d

    def test_model_ok(self):
        d = self._make_deployer({'status': 'Succeeded'})
        result = BundleDeploymentResult('/tmp', 'ws-1')
        result.model_id = 'm1'
        d.validate_deployment(result)
        self.assertEqual(result.validation[0]['status'], 'ok')

    def test_model_failed(self):
        d = self._make_deployer({'status': 'Failed'})
        result = BundleDeploymentResult('/tmp', 'ws-1')
        result.model_id = 'm1'
        d.validate_deployment(result)
        self.assertEqual(result.validation[0]['status'], 'fail')

    def test_report_bound(self):
        d = self._make_deployer()
        result = BundleDeploymentResult('/tmp', 'ws-1')
        result.model_id = 'm1'
        result.reports = [{'name': 'R1', 'status': 'deployed', 'rebind': 'success'}]
        d.validate_deployment(result)
        bound_checks = [v for v in result.validation if 'report_bound' in v['check']]
        self.assertEqual(bound_checks[0]['status'], 'ok')

    def test_report_unbound(self):
        d = self._make_deployer()
        result = BundleDeploymentResult('/tmp', 'ws-1')
        result.model_id = 'm1'
        result.reports = [{'name': 'R1', 'status': 'deployed', 'rebind': 'failed'}]
        d.validate_deployment(result)
        bound_checks = [v for v in result.validation if 'report_bound' in v['check']]
        self.assertEqual(bound_checks[0]['status'], 'warn')


# ── Refresh polling tests ──

class TestPollRefresh(unittest.TestCase):

    def test_completed(self):
        client = MagicMock()
        client.get.return_value = {'value': [{'status': 'Completed'}]}
        d = BundleDeployer('ws-1', client=client)
        result = BundleDeploymentResult('/tmp', 'ws-1')
        d.poll_refresh('m1', result, interval=0, timeout=5)
        self.assertEqual(result.refresh_status, 'completed')

    def test_failed(self):
        client = MagicMock()
        client.get.return_value = {'value': [{'status': 'Failed', 'error': 'bad'}]}
        d = BundleDeployer('ws-1', client=client)
        result = BundleDeploymentResult('/tmp', 'ws-1')
        d.poll_refresh('m1', result, interval=0, timeout=5)
        self.assertEqual(result.refresh_status, 'failed')

    def test_timeout(self):
        client = MagicMock()
        client.get.return_value = {'value': [{'status': 'InProgress'}]}
        d = BundleDeployer('ws-1', client=client)
        result = BundleDeploymentResult('/tmp', 'ws-1')
        d.poll_refresh('m1', result, interval=0, timeout=0)
        self.assertEqual(result.refresh_status, 'timeout')


# ── DeploymentManifest tests ──

class TestDeploymentManifest(unittest.TestCase):

    def test_create_and_serialize(self):
        m = DeploymentManifest('ws-1', 'SharedModel')
        m.model_id = 'mid'
        m.report_ids = ['r1', 'r2']
        m.source_hash = 'abc123'
        m.principal = 'user@test.com'
        m.version = '19.0.0'
        d = m.to_dict()
        self.assertEqual(d['workspace_id'], 'ws-1')
        self.assertEqual(d['model_name'], 'SharedModel')
        self.assertEqual(len(d['report_ids']), 2)

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'manifest.json')
            m = DeploymentManifest('ws-1', 'Model')
            m.model_id = 'x'
            m.report_ids = ['a']
            m.source_hash = 'hash'
            m.save(path)
            loaded = DeploymentManifest.load(path)
            self.assertEqual(loaded.workspace_id, 'ws-1')
            self.assertEqual(loaded.model_id, 'x')
            self.assertEqual(loaded.report_ids, ['a'])
            self.assertEqual(loaded.source_hash, 'hash')


# ── Integration: deploy_bundle with pre-flight ──

class TestDeployBundleIntegration(unittest.TestCase):

    def _make_project(self, tmpdir):
        proj = Path(tmpdir) / 'proj'
        proj.mkdir()
        model = proj / 'Test.SemanticModel' / 'definition'
        model.mkdir(parents=True)
        (model / 'model.tmdl').write_text('model Test')
        report = proj / 'Report1.Report' / 'definition'
        report.mkdir(parents=True)
        (report / 'report.json').write_text('{}')
        return proj

    def test_permission_failure_aborts(self):
        client = MagicMock()
        client.get.side_effect = ConnectionError('no access')
        d = BundleDeployer('ws-1', client=client)
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = self._make_project(tmpdir)
            result = d.deploy_bundle(str(proj))
            self.assertEqual(result.model_status, 'failed')
            self.assertIn('Permission', result.model_error)

    def test_conflict_blocks_without_overwrite(self):
        client = MagicMock()
        # First call = get_workspace (permissions), second = list_items (conflicts)
        client.get.side_effect = [
            {'role': 'Admin'},
            {'value': [{'displayName': 'Test', 'type': 'SemanticModel', 'id': 'x'}]},
        ]
        d = BundleDeployer('ws-1', client=client)
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = self._make_project(tmpdir)
            result = d.deploy_bundle(str(proj), overwrite=False)
            self.assertEqual(result.model_status, 'failed')
            self.assertIn('conflict', result.model_error.lower())
            self.assertEqual(len(result.conflicts), 1)


if __name__ == '__main__':
    unittest.main()
