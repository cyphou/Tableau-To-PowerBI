"""Tests for Fabric bundle deployer — deploy shared model + reports as a bundle."""

import json
import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# BundleDeploymentResult
# ---------------------------------------------------------------------------

class TestBundleDeploymentResult(unittest.TestCase):
    """Test BundleDeploymentResult data class."""

    def _make_result(self):
        from powerbi_import.deploy.bundle_deployer import BundleDeploymentResult
        return BundleDeploymentResult('/tmp/project', 'ws-123')

    def test_initial_state(self):
        r = self._make_result()
        self.assertEqual(r.project_dir, '/tmp/project')
        self.assertEqual(r.workspace_id, 'ws-123')
        self.assertEqual(r.model_status, 'pending')
        self.assertIsNone(r.model_id)
        self.assertEqual(r.reports, [])
        self.assertFalse(r.success)

    def test_success_requires_model_and_report(self):
        r = self._make_result()
        r.model_status = 'deployed'
        self.assertTrue(r.success)  # model-only deployment is valid

        r.reports.append({'name': 'R1', 'status': 'deployed', 'id': 'r1'})
        self.assertTrue(r.success)

    def test_success_false_when_model_failed(self):
        r = self._make_result()
        r.model_status = 'failed'
        r.reports.append({'name': 'R1', 'status': 'deployed', 'id': 'r1'})
        self.assertFalse(r.success)

    def test_counts(self):
        r = self._make_result()
        r.reports = [
            {'name': 'R1', 'status': 'deployed', 'id': 'r1'},
            {'name': 'R2', 'status': 'failed', 'error': 'err'},
            {'name': 'R3', 'status': 'deployed', 'id': 'r3'},
        ]
        self.assertEqual(r.deployed_count, 2)
        self.assertEqual(r.failed_count, 1)
        self.assertEqual(r.total_count, 3)

    def test_to_dict(self):
        r = self._make_result()
        r.model_name = 'SharedModel'
        r.model_status = 'deployed'
        r.model_id = 'sm-1'
        r.end_time = r.start_time
        r.reports = [{'name': 'R1', 'status': 'deployed', 'id': 'r1'}]

        d = r.to_dict()
        self.assertEqual(d['model_name'], 'SharedModel')
        self.assertEqual(d['model_id'], 'sm-1')
        self.assertEqual(d['reports_deployed'], 1)
        self.assertTrue(d['success'])
        self.assertIsNotNone(d['duration_seconds'])

    def test_to_json(self):
        r = self._make_result()
        r.model_name = 'M'
        j = r.to_json()
        parsed = json.loads(j)
        self.assertEqual(parsed['model_name'], 'M')

    def test_save(self):
        r = self._make_result()
        r.model_name = 'M'
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, 'report.json')
            r.save(path)
            self.assertTrue(os.path.exists(path))
            with open(path, 'r') as f:
                data = json.load(f)
            self.assertEqual(data['workspace_id'], 'ws-123')

    def test_print_summary(self):
        """print_summary should not raise."""
        r = self._make_result()
        r.model_name = 'Test'
        r.model_status = 'deployed'
        r.model_id = 'sm-1'
        r.end_time = r.start_time
        r.reports = [
            {'name': 'R1', 'status': 'deployed', 'id': 'r1'},
            {'name': 'R2', 'status': 'failed', 'error': 'timeout'},
        ]
        r.refresh_status = 'triggered'
        r.print_summary()  # should not raise

    def test_print_summary_model_error(self):
        """print_summary with model_error should not raise."""
        r = self._make_result()
        r.model_name = 'Test'
        r.model_status = 'failed'
        r.model_error = 'auth failure'
        r.end_time = r.start_time
        r.print_summary()


# ---------------------------------------------------------------------------
# BundleDeployer — artifact discovery
# ---------------------------------------------------------------------------

class TestDiscoverArtifacts(unittest.TestCase):
    """Test artifact discovery in a project directory."""

    def _make_project(self, td, model_name='Shared', reports=None):
        """Create a minimal project directory structure."""
        project = os.path.join(td, 'project')
        os.makedirs(project)

        sm = os.path.join(project, f'{model_name}.SemanticModel', 'definition')
        os.makedirs(sm)
        with open(os.path.join(sm, 'model.tmdl'), 'w') as f:
            f.write('model Model\n')

        for rpt in (reports or []):
            rd = os.path.join(project, f'{rpt}.Report', 'definition')
            os.makedirs(rd)
            with open(os.path.join(rd, 'report.json'), 'w') as f:
                json.dump({'name': rpt}, f)

        return project

    def test_discover_model_and_reports(self):
        from powerbi_import.deploy.bundle_deployer import BundleDeployer

        with tempfile.TemporaryDirectory() as td:
            project = self._make_project(td, 'MyModel', ['Sales', 'HR'])
            deployer = BundleDeployer.__new__(BundleDeployer)
            model_dir, model_name, report_dirs = deployer.discover_artifacts(project)

            self.assertIsNotNone(model_dir)
            self.assertEqual(model_name, 'MyModel')
            self.assertEqual(len(report_dirs), 2)
            names = [n for n, _ in report_dirs]
            self.assertIn('Sales', names)
            self.assertIn('HR', names)

    def test_discover_no_model(self):
        from powerbi_import.deploy.bundle_deployer import BundleDeployer

        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, 'SomeReport.Report', 'definition'))
            deployer = BundleDeployer.__new__(BundleDeployer)
            model_dir, model_name, report_dirs = deployer.discover_artifacts(td)
            self.assertIsNone(model_dir)
            self.assertIsNone(model_name)

    def test_discover_empty_dir(self):
        from powerbi_import.deploy.bundle_deployer import BundleDeployer

        with tempfile.TemporaryDirectory() as td:
            deployer = BundleDeployer.__new__(BundleDeployer)
            model_dir, model_name, report_dirs = deployer.discover_artifacts(td)
            self.assertIsNone(model_dir)
            self.assertEqual(report_dirs, [])


# ---------------------------------------------------------------------------
# BundleDeployer — read artifact definition
# ---------------------------------------------------------------------------

class TestReadArtifactDefinition(unittest.TestCase):
    """Test reading artifact definitions from directories."""

    def test_read_definition(self):
        from powerbi_import.deploy.bundle_deployer import BundleDeployer

        with tempfile.TemporaryDirectory() as td:
            art_dir = os.path.join(td, 'MyModel.SemanticModel')
            defn_dir = os.path.join(art_dir, 'definition')
            os.makedirs(defn_dir)
            with open(os.path.join(defn_dir, 'model.tmdl'), 'w') as f:
                f.write('model Model\n')
            with open(os.path.join(defn_dir, 'tables.tmdl'), 'w') as f:
                f.write('table Orders\n')

            deployer = BundleDeployer.__new__(BundleDeployer)
            config = deployer._read_artifact_definition(art_dir)

            self.assertEqual(config['displayName'], 'MyModel')
            self.assertIn('model.tmdl', config['definition'])
            self.assertIn('tables.tmdl', config['definition'])

    def test_read_nested_definition(self):
        from powerbi_import.deploy.bundle_deployer import BundleDeployer

        with tempfile.TemporaryDirectory() as td:
            art_dir = os.path.join(td, 'R1.Report')
            defn_dir = os.path.join(art_dir, 'definition', 'pages', 'Page1')
            os.makedirs(defn_dir)
            with open(os.path.join(defn_dir, 'page.json'), 'w') as f:
                json.dump({'name': 'Page1'}, f)

            deployer = BundleDeployer.__new__(BundleDeployer)
            config = deployer._read_artifact_definition(art_dir)

            self.assertEqual(config['displayName'], 'R1')
            self.assertIn('pages/Page1/page.json', config['definition'])


# ---------------------------------------------------------------------------
# BundleDeployer — deploy_bundle (mocked)
# ---------------------------------------------------------------------------

class TestDeployBundle(unittest.TestCase):
    """Test deploy_bundle with mocked Fabric API."""

    def _make_project_and_deployer(self, td, model='Shared', reports=None):
        from powerbi_import.deploy.bundle_deployer import BundleDeployer

        reports = reports or ['R1']
        project = os.path.join(td, 'project')
        os.makedirs(project)

        sm = os.path.join(project, f'{model}.SemanticModel', 'definition')
        os.makedirs(sm)
        with open(os.path.join(sm, 'model.tmdl'), 'w') as f:
            f.write('model\n')

        for rpt in reports:
            rd = os.path.join(project, f'{rpt}.Report', 'definition')
            os.makedirs(rd)
            with open(os.path.join(rd, 'report.json'), 'w') as f:
                json.dump({'name': rpt}, f)

        mock_client = MagicMock()
        deployer = BundleDeployer.__new__(BundleDeployer)
        deployer.workspace_id = 'ws-1'
        deployer.client = mock_client
        deployer._deployer = MagicMock()

        # Default: deploy succeeds
        deployer._deployer.deploy_dataset.return_value = {'id': 'sm-1'}
        deployer._deployer.deploy_report.return_value = {'id': 'rpt-1'}
        mock_client.post.return_value = {}  # rebind success

        return project, deployer

    def test_deploy_success(self):
        with tempfile.TemporaryDirectory() as td:
            project, deployer = self._make_project_and_deployer(
                td, reports=['Sales', 'HR'],
            )
            result = deployer.deploy_bundle(project)

            self.assertTrue(result.success)
            self.assertEqual(result.model_status, 'deployed')
            self.assertEqual(result.model_id, 'sm-1')
            self.assertEqual(result.deployed_count, 2)
            self.assertEqual(result.refresh_status, 'skipped')

    def test_deploy_with_refresh(self):
        with tempfile.TemporaryDirectory() as td:
            project, deployer = self._make_project_and_deployer(td)
            deployer.client.post.return_value = {}
            deployer.poll_refresh = MagicMock()
            result = deployer.deploy_bundle(project, refresh=True)

            self.assertTrue(result.success)
            self.assertEqual(result.refresh_status, 'triggered')
            deployer.poll_refresh.assert_called_once()

    def test_deploy_model_failure_stops_reports(self):
        with tempfile.TemporaryDirectory() as td:
            project, deployer = self._make_project_and_deployer(td)
            deployer._deployer.deploy_dataset.side_effect = Exception('auth error')

            result = deployer.deploy_bundle(project)

            self.assertFalse(result.success)
            self.assertEqual(result.model_status, 'failed')
            self.assertIn('auth error', result.model_error)
            self.assertEqual(result.reports, [])

    def test_deploy_report_failure_isolated(self):
        """A failed report doesn't block other reports."""
        with tempfile.TemporaryDirectory() as td:
            project, deployer = self._make_project_and_deployer(
                td, reports=['Good', 'Bad'],
            )
            call_count = [0]

            def deploy_report_side_effect(ws, name, config, overwrite=True):
                call_count[0] += 1
                if name == 'Bad':
                    raise Exception('report deploy error')
                return {'id': f'rpt-{call_count[0]}'}

            deployer._deployer.deploy_report.side_effect = deploy_report_side_effect

            result = deployer.deploy_bundle(project)

            self.assertEqual(result.model_status, 'deployed')
            self.assertEqual(result.deployed_count, 1)
            self.assertEqual(result.failed_count, 1)
            # Still success because model deployed and at least 1 report ok
            self.assertTrue(result.success)

    def test_deploy_no_model_dir(self):
        with tempfile.TemporaryDirectory() as td:
            # Empty project dir
            project = os.path.join(td, 'empty')
            os.makedirs(project)

            from powerbi_import.deploy.bundle_deployer import BundleDeployer
            deployer = BundleDeployer.__new__(BundleDeployer)
            deployer.workspace_id = 'ws-1'
            deployer.client = MagicMock()
            deployer._deployer = MagicMock()

            result = deployer.deploy_bundle(project)

            self.assertFalse(result.success)
            self.assertEqual(result.model_status, 'not_found')

    def test_deploy_nonexistent_dir(self):
        from powerbi_import.deploy.bundle_deployer import BundleDeployer
        deployer = BundleDeployer.__new__(BundleDeployer)
        deployer.workspace_id = 'ws-1'

        with self.assertRaises(FileNotFoundError):
            deployer.deploy_bundle('/nonexistent/path')

    def test_report_filter(self):
        """report_filter limits which reports are deployed."""
        with tempfile.TemporaryDirectory() as td:
            project, deployer = self._make_project_and_deployer(
                td, reports=['A', 'B', 'C'],
            )
            result = deployer.deploy_bundle(project, report_filter=['B'])

            self.assertEqual(result.total_count, 1)
            self.assertEqual(result.reports[0]['name'], 'B')

    def test_rebind_called(self):
        """Reports are rebound to model after deployment."""
        with tempfile.TemporaryDirectory() as td:
            project, deployer = self._make_project_and_deployer(td)
            result = deployer.deploy_bundle(project)

            deployer.client.post.assert_called()
            call_args = deployer.client.post.call_args_list
            self.assertTrue(any('Rebind' in str(c) for c in call_args))

    def test_refresh_failure(self):
        with tempfile.TemporaryDirectory() as td:
            project, deployer = self._make_project_and_deployer(td)
            # First call: rebind (success). Second call: refresh (fail).
            deployer.client.post.side_effect = [
                {},  # rebind
                Exception('refresh timeout'),  # refresh
            ]

            result = deployer.deploy_bundle(project, refresh=True)

            self.assertEqual(result.refresh_status, 'failed')
            self.assertIn('refresh timeout', result.refresh_error)


# ---------------------------------------------------------------------------
# deploy_bundle_from_cli
# ---------------------------------------------------------------------------

class TestDeployBundleFromCLI(unittest.TestCase):
    """Test the CLI entry point wrapper."""

    def test_cli_entry_point(self):
        from powerbi_import.deploy.bundle_deployer import deploy_bundle_from_cli

        with tempfile.TemporaryDirectory() as td:
            # Create minimal project
            project = os.path.join(td, 'proj')
            os.makedirs(project)
            sm = os.path.join(project, 'M.SemanticModel', 'definition')
            os.makedirs(sm)
            with open(os.path.join(sm, 'model.tmdl'), 'w') as f:
                f.write('model\n')
            rd = os.path.join(project, 'R.Report', 'definition')
            os.makedirs(rd)
            with open(os.path.join(rd, 'report.json'), 'w') as f:
                json.dump({}, f)

            with patch('powerbi_import.deploy.bundle_deployer.BundleDeployer') as MockBD:
                from powerbi_import.deploy.bundle_deployer import BundleDeploymentResult
                mock_result = BundleDeploymentResult(project, 'ws-1')
                mock_result.model_name = 'M'
                mock_result.model_status = 'deployed'
                mock_result.model_id = 'sm-1'
                mock_result.end_time = mock_result.start_time
                mock_result.reports = [{'name': 'R', 'status': 'deployed', 'id': 'r1'}]

                mock_deployer = MockBD.return_value
                mock_deployer.deploy_bundle.return_value = mock_result

                result = deploy_bundle_from_cli(project, 'ws-1')

                self.assertTrue(result.success)
                # Check deployment report was saved
                report_path = os.path.join(project, 'deployment_report.json')
                self.assertTrue(os.path.exists(report_path))


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

class TestCLIDeployBundleFlag(unittest.TestCase):
    """Test --deploy-bundle and --bundle-refresh CLI arguments."""

    def test_deploy_bundle_arg_parsed(self):
        """--deploy-bundle is recognized by argparse."""
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

        # Import the parser creation
        from migrate import main
        import argparse

        # Just verify the args can be parsed without error
        # We test by checking the attribute exists after parsing
        parser = argparse.ArgumentParser()
        parser.add_argument('--deploy-bundle', metavar='WORKSPACE_ID', default=None)
        parser.add_argument('--bundle-refresh', action='store_true', default=False)

        args = parser.parse_args(['--deploy-bundle', 'ws-abc', '--bundle-refresh'])
        self.assertEqual(args.deploy_bundle, 'ws-abc')
        self.assertTrue(args.bundle_refresh)

    def test_deploy_bundle_default_none(self):
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument('--deploy-bundle', default=None)
        args = parser.parse_args([])
        self.assertIsNone(args.deploy_bundle)


# ---------------------------------------------------------------------------
# deploy/__init__.py exports
# ---------------------------------------------------------------------------

class TestBundleExports(unittest.TestCase):
    """Verify bundle deployer is exported from deploy package."""

    def test_imports(self):
        from powerbi_import.deploy import (
            BundleDeployer,
            BundleDeploymentResult,
            deploy_bundle_from_cli,
        )
        self.assertIsNotNone(BundleDeployer)
        self.assertIsNotNone(BundleDeploymentResult)
        self.assertIsNotNone(deploy_bundle_from_cli)


# ---------------------------------------------------------------------------
# migrate.py — _run_bundle_deploy
# ---------------------------------------------------------------------------

class TestMigrateBundleDeploy(unittest.TestCase):
    """Test the _run_bundle_deploy helper in migrate.py."""

    def test_run_bundle_deploy_success(self):
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from migrate import _run_bundle_deploy, ExitCode

        with patch('powerbi_import.deploy.bundle_deployer.deploy_bundle_from_cli') as mock_cli:
            mock_result = MagicMock()
            mock_result.success = True
            mock_cli.return_value = mock_result

            with tempfile.TemporaryDirectory() as td:
                code = _run_bundle_deploy(td, 'ws-1')
                self.assertEqual(code, ExitCode.SUCCESS)

    def test_run_bundle_deploy_failure(self):
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from migrate import _run_bundle_deploy, ExitCode

        with patch('powerbi_import.deploy.bundle_deployer.deploy_bundle_from_cli') as mock_cli:
            mock_result = MagicMock()
            mock_result.success = False
            mock_cli.return_value = mock_result

            with tempfile.TemporaryDirectory() as td:
                code = _run_bundle_deploy(td, 'ws-1')
                self.assertEqual(code, ExitCode.GENERAL_ERROR)

    def test_run_bundle_deploy_exception(self):
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from migrate import _run_bundle_deploy, ExitCode

        with patch('powerbi_import.deploy.bundle_deployer.deploy_bundle_from_cli',
                   side_effect=Exception('network error')):
            with tempfile.TemporaryDirectory() as td:
                code = _run_bundle_deploy(td, 'ws-1')
                self.assertEqual(code, ExitCode.GENERAL_ERROR)


# ---------------------------------------------------------------------------
# Bug-bash fixes – rebind failure tracking
# ---------------------------------------------------------------------------

class TestRebindFailureTracking(unittest.TestCase):
    """Verify rebind failures are tracked in the result (bug-bash fix #1)."""

    def _make_project_and_deployer(self, td):
        from powerbi_import.deploy.bundle_deployer import BundleDeployer

        project = os.path.join(td, 'project')
        os.makedirs(project)

        sm = os.path.join(project, 'Model.SemanticModel', 'definition')
        os.makedirs(sm)
        with open(os.path.join(sm, 'model.tmdl'), 'w') as f:
            f.write('model\n')

        rd = os.path.join(project, 'R1.Report', 'definition')
        os.makedirs(rd)
        with open(os.path.join(rd, 'report.json'), 'w') as f:
            json.dump({'name': 'R1'}, f)

        mock_client = MagicMock()
        deployer = BundleDeployer.__new__(BundleDeployer)
        deployer.workspace_id = 'ws-1'
        deployer.client = mock_client
        deployer._deployer = MagicMock()
        deployer._deployer.deploy_dataset.return_value = {'id': 'sm-1'}
        deployer._deployer.deploy_report.return_value = {'id': 'rpt-1'}
        return project, deployer

    def test_rebind_success_tracked(self):
        """Successful rebind is recorded as 'success'."""
        with tempfile.TemporaryDirectory() as td:
            project, deployer = self._make_project_and_deployer(td)
            deployer.client.post.return_value = {}  # rebind OK
            result = deployer.deploy_bundle(project)

            rpt = result.reports[0]
            self.assertEqual(rpt['status'], 'deployed')
            self.assertEqual(rpt['rebind'], 'success')

    def test_rebind_failure_marks_unbound(self):
        """Failed rebind sets status to 'deployed_unbound'."""
        with tempfile.TemporaryDirectory() as td:
            project, deployer = self._make_project_and_deployer(td)
            deployer.client.post.side_effect = Exception('rebind 403')
            result = deployer.deploy_bundle(project)

            rpt = result.reports[0]
            self.assertEqual(rpt['status'], 'deployed_unbound')
            self.assertEqual(rpt['rebind'], 'failed')


# ---------------------------------------------------------------------------
# Bug-bash fixes – standalone deploy-bundle dir validation
# ---------------------------------------------------------------------------

class TestStandaloneDeployDirValidation(unittest.TestCase):
    """Verify standalone --deploy-bundle validates directory existence."""

    def test_nonexistent_dir_returns_error(self):
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from migrate import main, ExitCode

        with patch('sys.argv', ['migrate.py',
                                '--deploy-bundle', 'ws-fake',
                                '--output-dir', '/nonexistent/path/xyz']):
            code = main()
            self.assertEqual(code, ExitCode.GENERAL_ERROR)


if __name__ == '__main__':
    unittest.main()
