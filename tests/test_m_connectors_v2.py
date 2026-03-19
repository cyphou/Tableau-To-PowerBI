"""
Tests for Sprint 61 — M Connector Expansion.

Covers:
  - MongoDB connector (Atlas + collection)
  - Cosmos DB connector (SQL API)
  - Amazon Athena connector (ODBC + custom SQL)
  - IBM DB2 connector
  - Connector alias mapping
  - Fallback for unknown connectors
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tableau_export.m_query_builder import (
    generate_power_query_m,
    _gen_m_mongodb,
    _gen_m_cosmosdb,
    _gen_m_athena,
    _gen_m_db2,
    _M_GENERATORS,
)


class TestMongoDBConnector(unittest.TestCase):
    def test_basic(self):
        details = {'server': 'cluster0.mongodb.net', 'database': 'mydb'}
        m = _gen_m_mongodb(details, 'users', [])
        self.assertIn('MongoDBAtlas.Database', m)
        self.assertIn('cluster0.mongodb.net', m)
        self.assertIn('"mydb"', m)
        self.assertIn('"users"', m)

    def test_custom_collection(self):
        details = {'server': 'srv', 'database': 'db', 'collection': 'orders'}
        m = _gen_m_mongodb(details, 'T1', [])
        self.assertIn('"orders"', m)

    def test_alias_mapping(self):
        self.assertIn('MongoDB', _M_GENERATORS)
        self.assertIn('MongoDB Atlas', _M_GENERATORS)
        self.assertIn('mongodb', _M_GENERATORS)


class TestCosmosDBConnector(unittest.TestCase):
    def test_basic(self):
        details = {'server': 'https://myaccount.documents.azure.com:443/', 'database': 'mydb'}
        m = _gen_m_cosmosdb(details, 'items', [])
        self.assertIn('DocumentDB.Contents', m)
        self.assertIn('myaccount', m)
        self.assertIn('"mydb"', m)

    def test_custom_container(self):
        details = {'server': 'ep', 'database': 'db', 'collection': 'mycontainer'}
        m = _gen_m_cosmosdb(details, 'T', [])
        self.assertIn('"mycontainer"', m)

    def test_alias_mapping(self):
        self.assertIn('Cosmos DB', _M_GENERATORS)
        self.assertIn('Azure Cosmos DB', _M_GENERATORS)
        self.assertIn('cosmosdb', _M_GENERATORS)
        self.assertIn('DocumentDB', _M_GENERATORS)


class TestAthenaConnector(unittest.TestCase):
    def test_catalog_mode(self):
        details = {'region': 'us-west-2', 'database': 'MyCatalog'}
        m = _gen_m_athena(details, 'events', [])
        self.assertIn('Odbc.DataSource', m)
        self.assertIn('us-west-2', m)
        self.assertIn('"MyCatalog"', m)

    def test_custom_sql_mode(self):
        details = {'region': 'eu-west-1', 'custom_sql': 'SELECT * FROM logs'}
        m = _gen_m_athena(details, 'logs', [])
        self.assertIn('Odbc.Query', m)
        self.assertIn('SELECT * FROM logs', m)

    def test_alias_mapping(self):
        self.assertIn('Amazon Athena', _M_GENERATORS)
        self.assertIn('Athena', _M_GENERATORS)
        self.assertIn('athena', _M_GENERATORS)


class TestDB2Connector(unittest.TestCase):
    def test_basic(self):
        details = {'server': 'db2host', 'database': 'SAMPLE', 'schema': 'PROD'}
        m = _gen_m_db2(details, 'orders', [])
        self.assertIn('DB2.Database', m)
        self.assertIn('db2host', m)
        self.assertIn('"SAMPLE"', m)
        self.assertIn('"PROD"', m)

    def test_default_schema(self):
        details = {'server': 'host', 'database': 'DB'}
        m = _gen_m_db2(details, 'T', [])
        self.assertIn('"DB2INST1"', m)

    def test_alias_mapping(self):
        self.assertIn('IBM DB2', _M_GENERATORS)
        self.assertIn('DB2', _M_GENERATORS)
        self.assertIn('db2', _M_GENERATORS)


class TestConnectorDispatch(unittest.TestCase):
    def test_mongodb_dispatch(self):
        conn = {'type': 'MongoDB', 'server': 's', 'database': 'd'}
        table = {'name': 'T', 'columns': []}
        m = generate_power_query_m(conn, table)
        self.assertIn('MongoDBAtlas', m)

    def test_cosmosdb_dispatch(self):
        conn = {'type': 'Cosmos DB', 'server': 'ep', 'database': 'd'}
        table = {'name': 'T', 'columns': []}
        m = generate_power_query_m(conn, table)
        self.assertIn('DocumentDB', m)

    def test_unknown_fallback(self):
        conn = {'type': 'UnknownDB', 'server': 's', 'database': 'd'}
        table = {'name': 'T', 'columns': []}
        m = generate_power_query_m(conn, table)
        self.assertIn('let', m.lower())  # Should still produce valid M


if __name__ == '__main__':
    unittest.main()
