"""Tests for Sprint 44 — Silent Error Cleanup Phase 2.

Validates that narrowed exception handlers and added logging behave
correctly in error paths.
"""

import json
import logging
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project roots are importable
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TABLEAU_DIR = os.path.join(_PROJECT_ROOT, 'tableau_export')
_PBI_DIR = os.path.join(_PROJECT_ROOT, 'powerbi_import')
for _p in (_PROJECT_ROOT, _TABLEAU_DIR, _PBI_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _read_source(module):
    """Read module source as UTF-8."""
    with open(module.__file__, encoding='utf-8') as f:
        return f.read()


# ---------------------------------------------------------------------------
# hyper_reader — DatabaseError on sample rows
# ---------------------------------------------------------------------------

class TestHyperReaderErrorPaths(unittest.TestCase):
    """Error paths in tableau_export/hyper_reader.py."""

    def test_sample_rows_database_error_is_logged(self):
        """sqlite3.DatabaseError on SELECT is caught; source confirms pattern."""
        from tableau_export import hyper_reader
        source = _read_source(hyper_reader)
        # Verify the catch exists and uses DatabaseError (not broad Exception)
        idx = source.find('Failed to read sample rows')
        self.assertGreater(idx, 0)
        block = source[max(0, idx - 200):idx]
        self.assertIn('except sqlite3.DatabaseError', block)
        self.assertNotIn('except Exception', block)

    def test_nonexistent_file_returns_empty(self):
        """read_hyper on a nonexistent file returns empty tables."""
        from tableau_export.hyper_reader import read_hyper

        bad_path = os.path.join(tempfile.gettempdir(), 'nonexistent_hyper_test_v2.hyper')
        if os.path.exists(bad_path):
            os.unlink(bad_path)

        result = read_hyper(bad_path, max_rows=5)
        self.assertEqual(result.get('tables', []), [])


# ---------------------------------------------------------------------------
# datasource_extractor — BadZipFile / OSError
# ---------------------------------------------------------------------------

class TestDatasourceExtractorErrorPaths(unittest.TestCase):
    """Error paths in tableau_export/datasource_extractor.py."""

    def test_bad_zip_file_logged(self):
        """BadZipFile when reading CSV from archive is caught and logged."""
        from tableau_export.datasource_extractor import _read_csv_header_from_twbx

        fd, bad_path = tempfile.mkstemp(suffix='.twbx')
        try:
            os.write(fd, b'not a zip file at all')
            os.close(fd)

            with self.assertLogs('tableau_export.datasource_extractor', level='DEBUG') as cm:
                result = _read_csv_header_from_twbx(bad_path, None, 'data.csv')
            self.assertIsNone(result)
            self.assertTrue(any('archive' in m.lower() or 'csv' in m.lower()
                                for m in cm.output))
        finally:
            os.unlink(bad_path)

    def test_missing_twbx_returns_none(self):
        """Missing .twbx returns None (pre-check, no exception)."""
        from tableau_export.datasource_extractor import _read_csv_header_from_twbx

        result = _read_csv_header_from_twbx('/nonexistent/path.twbx', None, 'data.csv')
        self.assertIsNone(result)

    def test_non_twbx_returns_none(self):
        """Non-twbx extension returns None without error."""
        from tableau_export.datasource_extractor import _read_csv_header_from_twbx

        result = _read_csv_header_from_twbx('file.twb', None, 'data.csv')
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# m_query_builder — hyper read fallback
# ---------------------------------------------------------------------------

class TestMQueryBuilderHyperFallback(unittest.TestCase):
    """Error paths in tableau_export/m_query_builder.py hyper fallback."""

    def test_import_error_falls_back_to_template(self):
        """ImportError for hyper_reader produces fallback M query."""
        from tableau_export.m_query_builder import _gen_m_hyper

        details = {'filename': '/fake.hyper'}
        columns = [{'name': 'Col1'}, {'name': 'Col2'}]
        with self.assertLogs('tableau_export.m_query_builder', level='DEBUG') as cm:
            # Force ImportError by patching the import inside
            with patch.dict('sys.modules', {'hyper_reader': None}):
                result = _gen_m_hyper(details, 'TestTable', columns)
        self.assertIn('#table', result)
        self.assertIn('Col1', result)

    def test_missing_file_falls_back_to_template(self):
        """Missing hyper file falls back to template M query."""
        from tableau_export.m_query_builder import _gen_m_hyper

        details = {'filename': '/nonexistent/file.hyper'}
        columns = [{'name': 'A'}, {'name': 'B'}]
        result = _gen_m_hyper(details, 'T1', columns)
        self.assertIn('#table', result)


# ---------------------------------------------------------------------------
# prep_flow_parser — hyper read fallback
# ---------------------------------------------------------------------------

class TestPrepFlowParserHyperFallback(unittest.TestCase):
    """Error paths in tableau_export/prep_flow_parser.py hyper read."""

    def test_hyper_catch_is_narrowed(self):
        """Hyper fallback uses specific exceptions, not broad Exception."""
        from tableau_export import prep_flow_parser
        source = _read_source(prep_flow_parser)
        idx = source.find('Hyper read failed for')
        self.assertGreater(idx, 0)
        block = source[max(0, idx - 200):idx]
        self.assertIn('except (ImportError, OSError, KeyError, ValueError)', block)
        self.assertNotIn('except Exception', block)

    def test_hyper_catch_logs_debug(self):
        """Hyper fallback logs at DEBUG level."""
        from tableau_export import prep_flow_parser
        source = _read_source(prep_flow_parser)
        self.assertIn("logger.debug('Hyper read failed for %s: %s'", source)


# ---------------------------------------------------------------------------
# deploy/bundle_deployer — UnicodeDecodeError binary fallback
# ---------------------------------------------------------------------------

class TestBundleDeployerBinaryFallback(unittest.TestCase):
    """Error paths in powerbi_import/deploy/bundle_deployer.py."""

    def test_binary_file_hex_encoded(self):
        """UnicodeDecodeError triggers hex encoding fallback."""
        from powerbi_import.deploy.bundle_deployer import BundleDeployer

        deployer = BundleDeployer.__new__(BundleDeployer)

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / 'Test.SemanticModel'
            defn_dir = artifact_dir / 'definition'
            defn_dir.mkdir(parents=True)

            # Write a binary file
            (defn_dir / 'model.bim').write_bytes(b'\x80\x81\x82\xff\xfe')

            payload = deployer._read_artifact_definition(artifact_dir)
            # Should hex-encode the binary content
            self.assertEqual(payload['definition']['model.bim'], b'\x80\x81\x82\xff\xfe'.hex())


# ---------------------------------------------------------------------------
# deploy/deployer — UnicodeDecodeError binary fallback
# ---------------------------------------------------------------------------

class TestDeployerBinaryFallback(unittest.TestCase):
    """Error paths in powerbi_import/deploy/deployer.py."""

    def test_binary_file_hex_encoded(self):
        """UnicodeDecodeError during definition read triggers hex fallback."""
        from powerbi_import.deploy.deployer import FabricDeployer

        deployer = FabricDeployer.__new__(FabricDeployer)

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / 'MyModel.SemanticModel'
            defn_dir = artifact_dir / 'definition'
            defn_dir.mkdir(parents=True)

            # Write binary content
            binary_data = bytes(range(256))
            (defn_dir / 'data.bin').write_bytes(binary_data)

            config = deployer._read_artifact_config(artifact_dir)
            self.assertEqual(config['definition']['data.bin'], binary_data.hex())


# ---------------------------------------------------------------------------
# deploy/config/settings — pydantic fallback
# ---------------------------------------------------------------------------

class TestSettingsFallback(unittest.TestCase):
    """Error paths in powerbi_import/deploy/config/settings.py."""

    def test_fallback_to_env_settings(self):
        """ImportError on pydantic triggers fallback settings."""
        import powerbi_import.deploy.config.settings as settings_mod

        # Reset singleton
        settings_mod._settings_instance = None

        with patch.object(settings_mod, '_make_pydantic_settings',
                          side_effect=ImportError('no pydantic')):
            s = settings_mod.get_settings()
        self.assertIsNotNone(s)
        # Should be fallback type
        self.assertIsInstance(s, settings_mod._FallbackSettings)

        # Reset singleton for other tests
        settings_mod._settings_instance = None


# ---------------------------------------------------------------------------
# deploy/pbi_deployer — validation logging
# ---------------------------------------------------------------------------

class TestPBIDeployerValidationLogging(unittest.TestCase):
    """Error paths in powerbi_import/deploy/pbi_deployer.py validation."""

    def test_dataset_check_failure_logged(self):
        """Exception during dataset existence check is logged at DEBUG."""
        from powerbi_import.deploy.pbi_deployer import PBIWorkspaceDeployer

        deployer = PBIWorkspaceDeployer.__new__(PBIWorkspaceDeployer)
        deployer.workspace_id = 'ws-123'
        deployer.client = MagicMock()
        deployer.client.list_datasets.side_effect = RuntimeError('API error')
        deployer.client.get_refresh_history.return_value = []

        with self.assertLogs('powerbi_import.deploy.pbi_deployer', level='DEBUG') as cm:
            result = deployer.validate_deployment('ds-456')
        self.assertEqual(result['overall'], 'failed')
        self.assertTrue(any('dataset existence' in m.lower() for m in cm.output))

    def test_refresh_check_failure_logged(self):
        """Exception during refresh history check is logged at DEBUG."""
        from powerbi_import.deploy.pbi_deployer import PBIWorkspaceDeployer

        deployer = PBIWorkspaceDeployer.__new__(PBIWorkspaceDeployer)
        deployer.workspace_id = 'ws-123'
        deployer.client = MagicMock()
        deployer.client.list_datasets.return_value = [{'id': 'ds-789'}]
        deployer.client.get_refresh_history.side_effect = ConnectionError('timeout')

        with self.assertLogs('powerbi_import.deploy.pbi_deployer', level='DEBUG') as cm:
            result = deployer.validate_deployment('ds-789')
        # Dataset check passes, refresh check fails
        checks = {c['check']: c for c in result['checks']}
        self.assertTrue(checks['dataset_exists']['passed'])
        self.assertFalse(checks['latest_refresh']['passed'])
        self.assertTrue(any('refresh history' in m.lower() for m in cm.output))


# ---------------------------------------------------------------------------
# MigrationConfig — config loading error paths
# ---------------------------------------------------------------------------

class TestMigrateConfigErrors(unittest.TestCase):
    """Error paths for config file loading."""

    def test_bad_json_config_raises(self):
        """Malformed JSON config file raises JSONDecodeError."""
        from powerbi_import.config.migration_config import MigrationConfig

        fd, config_path = tempfile.mkstemp(suffix='.json')
        try:
            os.write(fd, b'{bad json!!!}')
            os.close(fd)
            with self.assertRaises((json.JSONDecodeError, ValueError)):
                MigrationConfig.from_file(config_path)
        finally:
            os.unlink(config_path)

    def test_missing_config_file_raises(self):
        """Missing config file raises FileNotFoundError."""
        from powerbi_import.config.migration_config import MigrationConfig

        with self.assertRaises(FileNotFoundError):
            MigrationConfig.from_file('/nonexistent/config.json')


# ---------------------------------------------------------------------------
# migrate.py — source-level verification of narrowed catches
# ---------------------------------------------------------------------------

class TestMigrateSourceNarrowing(unittest.TestCase):
    """Verify migrate.py exception handlers are narrowed (source inspection)."""

    @classmethod
    def setUpClass(cls):
        import migrate
        cls.source = _read_source(migrate)

    def test_no_except_exception_pass(self):
        """No 'except Exception: pass' remaining in migrate.py."""
        self.assertNotIn('except Exception:\n                pass', self.source)

    def test_telemetry_init_narrowed(self):
        """Telemetry init uses (ImportError, OSError, ValueError)."""
        self.assertIn(
            "except (ImportError, OSError, ValueError) as e:\n            logger.debug('Telemetry init",
            self.source,
        )

    def test_telemetry_finalize_narrowed(self):
        """Telemetry finalization uses (OSError, ValueError)."""
        self.assertIn(
            "except (OSError, ValueError) as e:\n            logger.debug('Telemetry finalization",
            self.source,
        )

    def test_temp_dir_cleanup_uses_oserror(self):
        """Temp dir cleanup blocks use OSError."""
        count = self.source.count(
            "except OSError as e:\n                logger.debug('Temp dir cleanup"
        )
        self.assertGreaterEqual(count, 2, "Expected at least 2 temp cleanup blocks")

    def test_incremental_merge_narrowed(self):
        """Incremental merge uses (ImportError, OSError, ValueError)."""
        idx = self.source.find('Incremental merge failed')
        self.assertGreater(idx, 0)
        block = self.source[max(0, idx - 200):idx]
        self.assertIn('except (ImportError, OSError, ValueError)', block)

    def test_goals_generation_narrowed(self):
        """Goals generation uses (ImportError, OSError, ValueError)."""
        idx = self.source.find('Goals generation failed')
        self.assertGreater(idx, 0)
        block = self.source[max(0, idx - 200):idx]
        self.assertIn('except (ImportError, OSError, ValueError)', block)

    def test_comparison_report_narrowed(self):
        """Comparison report uses (ImportError, OSError, ValueError)."""
        idx = self.source.find('Comparison report generation failed')
        self.assertGreater(idx, 0)
        block = self.source[max(0, idx - 200):idx]
        self.assertIn('except (ImportError, OSError, ValueError)', block)

    def test_telemetry_dashboard_narrowed(self):
        """Telemetry dashboard uses (ImportError, OSError, ValueError)."""
        idx = self.source.find('Telemetry dashboard generation failed')
        self.assertGreater(idx, 0)
        block = self.source[max(0, idx - 200):idx]
        self.assertIn('except (ImportError, OSError, ValueError)', block)

    def test_deployment_uses_percent_style_logging(self):
        """Deployment error uses %-style logger, not f-string."""
        self.assertIn(
            'logger.error("Deployment failed: %s", exc, exc_info=True)',
            self.source,
        )

    def test_config_loading_narrowed(self):
        """Config file loading uses (OSError, json.JSONDecodeError, ValueError)."""
        idx = self.source.find('Failed to load config file')
        self.assertGreater(idx, 0)
        block = self.source[max(0, idx - 200):idx]
        self.assertIn('except (OSError, json.JSONDecodeError, ValueError)', block)


# ---------------------------------------------------------------------------
# deploy/ — narrowed catches verification (source inspection)
# ---------------------------------------------------------------------------

class TestDeployNarrowedCatches(unittest.TestCase):
    """Verify deploy/ module catches are properly narrowed."""

    def test_bundle_deployer_not_broad_exception(self):
        """bundle_deployer binary fallback doesn't use broad Exception."""
        import powerbi_import.deploy.bundle_deployer as mod
        source = _read_source(mod)
        idx = source.find('hex-encoding')
        self.assertGreater(idx, 0)
        block = source[max(0, idx - 200):idx]
        self.assertIn('except (UnicodeDecodeError, ValueError)', block)
        self.assertNotIn('except Exception', block)

    def test_deployer_not_broad_exception(self):
        """deployer binary fallback doesn't use broad Exception."""
        import powerbi_import.deploy.deployer as mod
        source = _read_source(mod)
        idx = source.find('hex-encoding')
        self.assertGreater(idx, 0)
        block = source[max(0, idx - 200):idx]
        self.assertIn('except (UnicodeDecodeError, ValueError)', block)

    def test_settings_not_broad_exception(self):
        """settings pydantic fallback doesn't use broad Exception."""
        import powerbi_import.deploy.config.settings as mod
        source = _read_source(mod)
        idx = source.find('Settings loaded via environment fallback')
        self.assertGreater(idx, 0)
        block = source[max(0, idx - 200):idx]
        self.assertIn('except (ImportError, ValueError, TypeError)', block)


# ---------------------------------------------------------------------------
# extraction modules — bare-pass → logging verification
# ---------------------------------------------------------------------------

class TestExtractionLoggingAdded(unittest.TestCase):
    """Verify extraction modules have loggers and log on catch."""

    def test_datasource_extractor_has_logger(self):
        from tableau_export import datasource_extractor
        self.assertTrue(hasattr(datasource_extractor, 'logger'))

    def test_m_query_builder_has_logger(self):
        from tableau_export import m_query_builder
        self.assertTrue(hasattr(m_query_builder, 'logger'))

    def test_prep_flow_parser_has_logger(self):
        from tableau_export import prep_flow_parser
        self.assertTrue(hasattr(prep_flow_parser, 'logger'))

    def test_hyper_reader_has_logger(self):
        from tableau_export import hyper_reader
        self.assertTrue(hasattr(hyper_reader, 'logger'))


if __name__ == '__main__':
    unittest.main()
