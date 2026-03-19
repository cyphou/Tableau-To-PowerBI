"""Unit tests for multi-tenant deployment configuration and connection patching."""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from powerbi_import.deploy.multi_tenant import (
    TenantConfig,
    MultiTenantConfig,
    TenantDeploymentResult,
    MultiTenantDeploymentResult,
    _apply_connection_overrides,
)

VALID_GUID = '12345678-1234-1234-1234-123456789abc'
VALID_GUID_2 = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'


class TestTenantConfigValidation(unittest.TestCase):
    """Validate individual tenant configs."""

    def test_valid_tenant(self):
        t = TenantConfig(name='Contoso', workspace_id=VALID_GUID)
        self.assertEqual(t.validate(), [])

    def test_missing_name(self):
        t = TenantConfig(name='', workspace_id=VALID_GUID)
        errors = t.validate()
        self.assertTrue(any('name' in e.lower() for e in errors))

    def test_missing_workspace_id(self):
        t = TenantConfig(name='T', workspace_id='')
        errors = t.validate()
        self.assertTrue(len(errors) >= 1)

    def test_invalid_guid_format(self):
        t = TenantConfig(name='T', workspace_id='not-a-guid')
        errors = t.validate()
        self.assertTrue(any('GUID' in e for e in errors))

    def test_valid_guid_uppercase(self):
        t = TenantConfig(name='T', workspace_id=VALID_GUID.upper())
        self.assertEqual(t.validate(), [])

    def test_connection_overrides_stored(self):
        t = TenantConfig(
            name='T', workspace_id=VALID_GUID,
            connection_overrides={'${TENANT_SERVER}': 'myserver.database.windows.net'}
        )
        self.assertEqual(t.connection_overrides['${TENANT_SERVER}'], 'myserver.database.windows.net')

    def test_rls_mappings_stored(self):
        t = TenantConfig(
            name='T', workspace_id=VALID_GUID,
            rls_mappings={'Admin': ['user1@example.com']}
        )
        self.assertEqual(t.rls_mappings['Admin'], ['user1@example.com'])


class TestMultiTenantConfigValidation(unittest.TestCase):
    """Validate multi-tenant configuration."""

    def test_empty_tenants(self):
        cfg = MultiTenantConfig(tenants=[])
        errors = cfg.validate()
        self.assertTrue(any('No tenants' in e for e in errors))

    def test_valid_config(self):
        cfg = MultiTenantConfig(tenants=[
            TenantConfig(name='A', workspace_id=VALID_GUID),
            TenantConfig(name='B', workspace_id=VALID_GUID_2),
        ])
        self.assertEqual(cfg.validate(), [])

    def test_duplicate_names(self):
        cfg = MultiTenantConfig(tenants=[
            TenantConfig(name='Same', workspace_id=VALID_GUID),
            TenantConfig(name='Same', workspace_id=VALID_GUID_2),
        ])
        errors = cfg.validate()
        self.assertTrue(any('Duplicate tenant name' in e for e in errors))

    def test_duplicate_workspace_ids(self):
        cfg = MultiTenantConfig(tenants=[
            TenantConfig(name='A', workspace_id=VALID_GUID),
            TenantConfig(name='B', workspace_id=VALID_GUID),
        ])
        errors = cfg.validate()
        self.assertTrue(any('Duplicate workspace_id' in e for e in errors))

    def test_propagates_tenant_errors(self):
        cfg = MultiTenantConfig(tenants=[
            TenantConfig(name='', workspace_id='bad'),
        ])
        errors = cfg.validate()
        self.assertGreater(len(errors), 0)


class TestMultiTenantConfigSaveLoad(unittest.TestCase):
    """Save/load round-trip for config files."""

    def test_save_and_load(self):
        cfg = MultiTenantConfig(tenants=[
            TenantConfig(
                name='Contoso',
                workspace_id=VALID_GUID,
                connection_overrides={'${TENANT_SERVER}': 'contoso.sql.net'},
                rls_mappings={'Manager': ['user@contoso.com']},
            ),
        ])
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'tenants.json')
            cfg.save(path)
            self.assertTrue(os.path.isfile(path))

            loaded = MultiTenantConfig.load(path)
            self.assertEqual(len(loaded.tenants), 1)
            self.assertEqual(loaded.tenants[0].name, 'Contoso')
            self.assertEqual(loaded.tenants[0].workspace_id, VALID_GUID)
            self.assertEqual(loaded.tenants[0].connection_overrides['${TENANT_SERVER}'], 'contoso.sql.net')
            self.assertEqual(loaded.tenants[0].rls_mappings['Manager'], ['user@contoso.com'])

    def test_load_empty_tenants(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'empty.json')
            with open(path, 'w') as f:
                json.dump({'tenants': []}, f)
            loaded = MultiTenantConfig.load(path)
            self.assertEqual(len(loaded.tenants), 0)

    def test_load_minimal_tenant(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'minimal.json')
            with open(path, 'w') as f:
                json.dump({'tenants': [{'name': 'T', 'workspace_id': VALID_GUID}]}, f)
            loaded = MultiTenantConfig.load(path)
            self.assertEqual(loaded.tenants[0].name, 'T')
            self.assertEqual(loaded.tenants[0].connection_overrides, {})

    def test_save_creates_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'sub', 'dir', 'tenants.json')
            cfg = MultiTenantConfig(tenants=[
                TenantConfig(name='X', workspace_id=VALID_GUID),
            ])
            cfg.save(path)
            self.assertTrue(os.path.isfile(path))


class TestConnectionOverrides(unittest.TestCase):
    """Test _apply_connection_overrides function."""

    def _create_model_dir(self, tmpdir, files=None):
        """Create a fake model directory with files."""
        model_dir = os.path.join(tmpdir, 'model')
        os.makedirs(model_dir, exist_ok=True)
        files = files or {}
        for name, content in files.items():
            fpath = os.path.join(model_dir, name)
            os.makedirs(os.path.dirname(fpath), exist_ok=True)
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(content)
        return model_dir

    def test_substitutes_placeholders_in_tmdl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = self._create_model_dir(tmpdir, {
                'definition/tables/Sales.tmdl': 'source = "${TENANT_SERVER}" database="${TENANT_DATABASE}"'
            })
            output_dir = os.path.join(tmpdir, 'output')
            _apply_connection_overrides(model_dir, {
                '${TENANT_SERVER}': 'contoso.sql.net',
                '${TENANT_DATABASE}': 'sales_db',
            }, output_dir)

            result = os.path.join(output_dir, 'definition', 'tables', 'Sales.tmdl')
            with open(result, 'r') as f:
                content = f.read()
            self.assertIn('contoso.sql.net', content)
            self.assertIn('sales_db', content)
            self.assertNotIn('${TENANT_SERVER}', content)

    def test_no_overrides_copies_unchanged(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = self._create_model_dir(tmpdir, {
                'model.tmdl': 'original content'
            })
            output_dir = os.path.join(tmpdir, 'output')
            _apply_connection_overrides(model_dir, {}, output_dir)

            with open(os.path.join(output_dir, 'model.tmdl'), 'r') as f:
                content = f.read()
            self.assertEqual(content, 'original content')

    def test_json_files_substituted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = self._create_model_dir(tmpdir, {
                'config.json': '{"server": "${TENANT_SERVER}"}'
            })
            output_dir = os.path.join(tmpdir, 'output')
            _apply_connection_overrides(model_dir, {
                '${TENANT_SERVER}': 'myserver'
            }, output_dir)

            with open(os.path.join(output_dir, 'config.json'), 'r') as f:
                content = f.read()
            self.assertIn('myserver', content)

    def test_non_text_files_ignored(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = self._create_model_dir(tmpdir, {
                'data.csv': '${TENANT_SERVER},value'
            })
            output_dir = os.path.join(tmpdir, 'output')
            _apply_connection_overrides(model_dir, {
                '${TENANT_SERVER}': 'replaced'
            }, output_dir)

            # .csv is not in the extension list, so should be unchanged
            with open(os.path.join(output_dir, 'data.csv'), 'r') as f:
                content = f.read()
            self.assertIn('${TENANT_SERVER}', content)

    def test_m_files_substituted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = self._create_model_dir(tmpdir, {
                'definition/tables/Query.m': 'Source = Sql.Database("${TENANT_SERVER}", "${TENANT_DATABASE}")'
            })
            output_dir = os.path.join(tmpdir, 'output')
            _apply_connection_overrides(model_dir, {
                '${TENANT_SERVER}': 'prod.sql.net',
                '${TENANT_DATABASE}': 'prod_db',
            }, output_dir)

            with open(os.path.join(output_dir, 'definition', 'tables', 'Query.m'), 'r') as f:
                content = f.read()
            self.assertIn('prod.sql.net', content)
            self.assertIn('prod_db', content)

    def test_multiple_placeholders_in_one_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = self._create_model_dir(tmpdir, {
                'model.tmdl': '${A} and ${B} and ${A} again'
            })
            output_dir = os.path.join(tmpdir, 'output')
            _apply_connection_overrides(model_dir, {
                '${A}': 'alpha',
                '${B}': 'beta',
            }, output_dir)

            with open(os.path.join(output_dir, 'model.tmdl'), 'r') as f:
                content = f.read()
            self.assertEqual(content, 'alpha and beta and alpha again')


class TestDeploymentResults(unittest.TestCase):
    """Test result dataclasses."""

    def test_tenant_result_to_dict(self):
        r = TenantDeploymentResult(
            tenant_name='T1',
            workspace_id=VALID_GUID,
            success=True,
            model_id='m1',
            report_count=3,
        )
        d = r.to_dict()
        self.assertEqual(d['tenant_name'], 'T1')
        self.assertTrue(d['success'])
        self.assertEqual(d['report_count'], 3)

    def test_multi_tenant_result(self):
        r = MultiTenantDeploymentResult()
        r.results.append(TenantDeploymentResult(
            tenant_name='T1', workspace_id=VALID_GUID, success=True,
        ))
        r.results.append(TenantDeploymentResult(
            tenant_name='T2', workspace_id=VALID_GUID_2, success=False, error='Network error',
        ))
        d = r.to_dict()
        self.assertEqual(len(d['tenants']), 2)
        self.assertTrue(d['tenants'][0]['success'])
        self.assertFalse(d['tenants'][1]['success'])

    def test_multi_tenant_result_to_json(self):
        r = MultiTenantDeploymentResult()
        r.results.append(TenantDeploymentResult(
            tenant_name='T1', workspace_id=VALID_GUID, success=True,
        ))
        j = r.to_json()
        parsed = json.loads(j)
        self.assertEqual(len(parsed['tenants']), 1)

    def test_multi_tenant_result_save(self):
        r = MultiTenantDeploymentResult()
        r.results.append(TenantDeploymentResult(
            tenant_name='T1', workspace_id=VALID_GUID, success=True,
        ))
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'deploy_result.json')
            r.save(path)
            self.assertTrue(os.path.isfile(path))
            with open(path, 'r') as f:
                data = json.load(f)
            self.assertEqual(len(data['tenants']), 1)


if __name__ == '__main__':
    unittest.main()
