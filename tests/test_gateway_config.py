"""
Tests for gateway_config module — Sprint 56.

Covers:
  - GatewayConfigGenerator instantiation
  - Connection mapping for major connector types
  - Gateway requirement detection
  - OAuth configuration detection
  - write_config file I/O
  - generate_and_write convenience method
  - Edge cases: empty datasources, missing connection info
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from powerbi_import.gateway_config import (
    GatewayConfigGenerator,
    OAUTH_CONNECTORS,
    GATEWAY_CONNECTORS,
)


class TestGatewayConfigGeneratorInit(unittest.TestCase):
    def test_instantiation(self):
        gen = GatewayConfigGenerator()
        self.assertIsNotNone(gen)


class TestGenerateGatewayConfig(unittest.TestCase):
    def setUp(self):
        self.gen = GatewayConfigGenerator()

    def test_empty_datasources(self):
        config = self.gen.generate_gateway_config([])
        self.assertEqual(config['connections'], [])
        self.assertFalse(config['gateway']['required'])
        self.assertEqual(config['oauth'], [])

    def test_none_datasources(self):
        config = self.gen.generate_gateway_config(None)
        self.assertEqual(config['connections'], [])

    def test_sqlserver_requires_gateway(self):
        ds = [{'connection_type': 'sqlserver', 'name': 'SQL DS',
               'connection': {'server': 'myserver', 'database': 'mydb'}}]
        config = self.gen.generate_gateway_config(ds)
        self.assertTrue(config['gateway']['required'])
        self.assertTrue(config['connections'][0]['requires_gateway'])

    def test_postgresql_requires_gateway(self):
        ds = [{'connection_type': 'postgresql', 'name': 'PG DS',
               'connection': {'server': 'pgserver', 'database': 'pgdb'}}]
        config = self.gen.generate_gateway_config(ds)
        self.assertTrue(config['gateway']['required'])

    def test_oracle_requires_gateway(self):
        ds = [{'connection_type': 'oracle', 'name': 'ORA DS'}]
        config = self.gen.generate_gateway_config(ds)
        self.assertTrue(config['gateway']['required'])

    def test_bigquery_uses_oauth(self):
        ds = [{'connection_type': 'bigquery', 'name': 'BQ DS'}]
        config = self.gen.generate_gateway_config(ds)
        self.assertEqual(len(config['oauth']), 1)
        self.assertEqual(config['oauth'][0]['provider'], 'Google')
        self.assertEqual(config['connections'][0]['auth_type'], 'OAuth2')

    def test_snowflake_uses_oauth(self):
        ds = [{'connection_type': 'snowflake', 'name': 'SF DS'}]
        config = self.gen.generate_gateway_config(ds)
        self.assertEqual(len(config['oauth']), 1)
        self.assertEqual(config['oauth'][0]['provider'], 'Snowflake')

    def test_salesforce_uses_oauth(self):
        ds = [{'connection_type': 'salesforce', 'name': 'SFDC DS'}]
        config = self.gen.generate_gateway_config(ds)
        self.assertEqual(len(config['oauth']), 1)

    def test_azure_sql_uses_oauth(self):
        ds = [{'connection_type': 'azure_sql', 'name': 'AzSQL DS'}]
        config = self.gen.generate_gateway_config(ds)
        self.assertEqual(len(config['oauth']), 1)
        self.assertEqual(config['oauth'][0]['provider'], 'AzureAD')

    def test_cloud_connector_no_gateway(self):
        ds = [{'connection_type': 'bigquery', 'name': 'BQ DS',
               'connection': {'server': 'https://bigquery.googleapis.com'}}]
        config = self.gen.generate_gateway_config(ds)
        self.assertFalse(config['connections'][0]['requires_gateway'])

    def test_multiple_datasources(self):
        ds = [
            {'connection_type': 'sqlserver', 'name': 'SQL1',
             'connection': {'server': 'srv1', 'database': 'db1'}},
            {'connection_type': 'bigquery', 'name': 'BQ1'},
            {'connection_type': 'csv', 'name': 'CSV1'},
        ]
        config = self.gen.generate_gateway_config(ds)
        self.assertEqual(len(config['connections']), 3)
        self.assertTrue(config['gateway']['required'])

    def test_connection_entry_has_id(self):
        ds = [{'connection_type': 'csv', 'name': 'Test'}]
        config = self.gen.generate_gateway_config(ds)
        self.assertIn('id', config['connections'][0])
        self.assertGreater(len(config['connections'][0]['id']), 0)

    def test_connection_entry_has_name(self):
        ds = [{'connection_type': 'csv', 'name': 'My CSV'}]
        config = self.gen.generate_gateway_config(ds)
        self.assertEqual(config['connections'][0]['name'], 'My CSV')

    def test_fallback_name_when_missing(self):
        ds = [{'connection_type': 'csv'}]
        config = self.gen.generate_gateway_config(ds)
        self.assertIn('Datasource_1', config['connections'][0]['name'])

    def test_caption_fallback_for_name(self):
        ds = [{'connection_type': 'csv', 'caption': 'My Caption'}]
        config = self.gen.generate_gateway_config(ds)
        self.assertEqual(config['connections'][0]['name'], 'My Caption')

    def test_server_from_top_level(self):
        ds = [{'connection_type': 'postgresql', 'name': 'PG',
               'server': 'top-level-server'}]
        config = self.gen.generate_gateway_config(ds)
        self.assertEqual(config['connections'][0]['server'], 'top-level-server')

    def test_type_fallback(self):
        ds = [{'type': 'mysql', 'name': 'MySQL DS'}]
        config = self.gen.generate_gateway_config(ds)
        self.assertTrue(config['gateway']['required'])

    def test_gateway_placeholder_values(self):
        ds = [{'connection_type': 'sqlserver', 'name': 'SQL',
               'connection': {'server': 'srv', 'database': 'db'}}]
        config = self.gen.generate_gateway_config(ds)
        self.assertEqual(config['gateway']['gateway_id'], '${GATEWAY_ID}')
        self.assertEqual(config['gateway']['gateway_name'], '${GATEWAY_NAME}')

    def test_no_gateway_cloud_only(self):
        ds = [{'connection_type': 'csv', 'name': 'CSV'}]
        config = self.gen.generate_gateway_config(ds)
        self.assertFalse(config['gateway']['required'])
        self.assertIsNone(config['gateway']['gateway_id'])

    def test_oauth_has_client_placeholders(self):
        ds = [{'connection_type': 'bigquery', 'name': 'BQ'}]
        config = self.gen.generate_gateway_config(ds)
        oauth = config['oauth'][0]
        self.assertEqual(oauth['client_id'], '${CLIENT_ID}')
        self.assertEqual(oauth['client_secret'], '${CLIENT_SECRET}')
        self.assertIn('redirect_uri', oauth)

    def test_databricks_pat_auth(self):
        ds = [{'connection_type': 'databricks', 'name': 'DB DS'}]
        config = self.gen.generate_gateway_config(ds)
        self.assertEqual(len(config['oauth']), 1)
        self.assertEqual(config['oauth'][0]['auth_type'], 'PersonalAccessToken')


class TestWriteConfig(unittest.TestCase):
    def test_write_creates_files(self):
        gen = GatewayConfigGenerator()
        config = {
            'connections': [{'id': '1', 'name': 'Test'}],
            'gateway': {'required': False},
            'oauth': [],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            result = gen.write_config(tmpdir, config)
            self.assertTrue(os.path.isdir(result))
            gateway_file = os.path.join(result, 'gateway_config.json')
            self.assertTrue(os.path.exists(gateway_file))
            with open(gateway_file, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            self.assertEqual(loaded['connections'][0]['name'], 'Test')

    def test_write_oauth_templates(self):
        gen = GatewayConfigGenerator()
        config = {
            'connections': [],
            'gateway': {'required': False},
            'oauth': [
                {'datasource_name': 'BQ Source', 'provider': 'Google',
                 'auth_type': 'OAuth2'},
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            result = gen.write_config(tmpdir, config)
            oauth_files = [f for f in os.listdir(result) if f.startswith('oauth_')]
            self.assertEqual(len(oauth_files), 1)


class TestGenerateAndWrite(unittest.TestCase):
    def test_convenience_method(self):
        gen = GatewayConfigGenerator()
        ds = [{'connection_type': 'csv', 'name': 'Test CSV'}]
        with tempfile.TemporaryDirectory() as tmpdir:
            result = gen.generate_and_write(tmpdir, ds)
            self.assertTrue(os.path.isdir(result))
            self.assertTrue(os.path.exists(
                os.path.join(result, 'gateway_config.json')))


class TestConnectorConstants(unittest.TestCase):
    def test_oauth_connectors_non_empty(self):
        self.assertGreater(len(OAUTH_CONNECTORS), 0)

    def test_gateway_connectors_non_empty(self):
        self.assertGreater(len(GATEWAY_CONNECTORS), 0)

    def test_sqlserver_in_gateway(self):
        self.assertIn('sqlserver', GATEWAY_CONNECTORS)

    def test_bigquery_in_oauth(self):
        self.assertIn('bigquery', OAUTH_CONNECTORS)


if __name__ == '__main__':
    unittest.main()
