"""
Shared test fixtures and sample data for TableauToPowerBI tests.
"""

import os
import json
import tempfile
import shutil

# ── Sample extracted data (mimics tableau_export JSON output) ───────

SAMPLE_DATASOURCE = {
    'name': 'Sales Data',
    'connection': {
        'type': 'SQL Server',
        'details': {
            'server': 'myserver.database.windows.net',
            'database': 'SalesDB',
            'port': '1433',
        },
    },
    'connection_map': {},
    'tables': [
        {
            'name': '[dbo].[Orders]',
            'columns': [
                {'name': 'OrderID', 'datatype': 'integer', 'nullable': False},
                {'name': 'CustomerName', 'datatype': 'string', 'nullable': True},
                {'name': 'OrderDate', 'datatype': 'datetime', 'nullable': True},
                {'name': 'Amount', 'datatype': 'real', 'nullable': True},
                {'name': 'IsActive', 'datatype': 'boolean', 'nullable': True},
            ],
        },
        {
            'name': 'Products',
            'columns': [
                {'name': 'ProductID', 'datatype': 'integer', 'nullable': False},
                {'name': 'ProductName', 'datatype': 'string', 'nullable': True},
                {'name': 'Price', 'datatype': 'currency', 'nullable': True},
            ],
        },
    ],
}

SAMPLE_DATASOURCE_CSV = {
    'name': 'CSV Source',
    'connection': {
        'type': 'CSV',
        'details': {
            'filename': 'data.csv',
            'delimiter': ',',
        },
    },
    'connection_map': {},
    'tables': [
        {
            'name': 'data',
            'columns': [
                {'name': 'id', 'datatype': 'integer'},
                {'name': 'value', 'datatype': 'string'},
            ],
        },
    ],
}

SAMPLE_EXTRACTED = {
    'datasources': [SAMPLE_DATASOURCE],
    'worksheets': [
        {
            'name': 'Sheet 1',
            'type': 'worksheet',
            'datasource': 'Sales Data',
            'columns': [
                {'name': 'OrderDate', 'datasource': 'Sales Data', 'type': 'dimension'},
                {'name': 'Amount', 'datasource': 'Sales Data', 'type': 'measure'},
            ],
        },
    ],
    'dashboards': [{'name': 'Sales Dashboard', 'worksheets': ['Sheet 1']}],
    'calculations': [
        {
            'name': 'Total Sales',
            'caption': 'Total Sales',
            'formula': 'SUM([Amount])',
            'datatype': 'real',
            'role': 'measure',
        },
        {
            'name': 'Order Count',
            'caption': 'Order Count',
            'formula': 'COUNT([OrderID])',
            'datatype': 'integer',
            'role': 'measure',
        },
        # ── Calculated columns (row-level, no aggregation) ──────
        {
            'name': 'Revenue',
            'caption': 'Revenue',
            'formula': '[Amount] * [Price]',
            'datatype': 'real',
            'role': 'dimension',
        },
        {
            'name': 'Status Label',
            'caption': 'Status Label',
            'formula': 'IF [IsActive] THEN "Active" ELSE "Inactive" END',
            'datatype': 'string',
            'role': 'dimension',
        },
    ],
    'parameters': [],
    'filters': [],
    'stories': [],
    'actions': [],
    'sets': [],
    'groups': [],
    'bins': [],
    'hierarchies': [],
    'sort_orders': [],
    'aliases': {},
    'custom_sql': [],
    'user_filters': [],
}

SAMPLE_CUSTOM_SQL = [
    {
        'name': 'TopCustomers',
        'datasource': 'Sales Data',
        'query': 'SELECT TOP 10 * FROM Customers ORDER BY Revenue DESC',
    },
]


def make_temp_dir():
    """Create a temporary directory for test output."""
    return tempfile.mkdtemp(prefix='ttpbi_test_')


def cleanup_dir(path):
    """Remove a temporary directory."""
    if path and os.path.exists(path):
        shutil.rmtree(path, ignore_errors=True)
