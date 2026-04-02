"""
Comprehensive tests for Prep Flow Lineage pipeline.

Creates realistic .tfl/.tflx test fixtures simulating a real-world
Tableau Prep portfolio with:
- Simple single-source flows (CSV, Excel, SQL)
- Complex multi-join/union/pivot flows
- Cross-flow interactions (Flow A output → Flow B input)
- Published datasource references
- Script/prediction steps (manual migration warnings)
- Isolated flows (no cross-flow edges)

Tests cover:
- Phase 1: prep_flow_analyzer (FlowProfile extraction)
- Phase 2: prep_lineage (cross-flow graph building)
- Phase 3: prep_lineage_report (merge recommendations + HTML/JSON)
- Phase 4: CLI integration (--prep-lineage)
"""

import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch, MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tableau_export'))
sys.path.insert(0, os.path.join(ROOT, 'powerbi_import'))

from prep_flow_analyzer import (
    FlowProfile, FlowInput, FlowOutput, FlowTransform,
    analyze_flow, analyze_flows_bulk, _fingerprint,
    _extract_inputs, _extract_outputs, _extract_transforms,
    _build_node_graph, _compute_dag_depth, _count_calcs,
)
from prep_lineage import (
    PrepLineageGraph, LineageEdge, SourceEndpoint, SinkEndpoint,
    build_lineage_graph, _match_outputs_to_inputs,
    _identify_external_sources, _identify_final_sinks,
    _compute_flow_layers, _detect_chains, _find_isolated_flows,
    _fuzzy_match_name, _normalize_name,
)
from prep_lineage_report import (
    MergeRecommendation, compute_merge_recommendations,
    generate_prep_lineage_report, save_lineage_json,
    print_lineage_summary,
    _source_overlap, _transform_similarity, _column_overlap,
)


# ═══════════════════════════════════════════════════════════════════════════════
#  FLOW FIXTURE BUILDERS
# ═══════════════════════════════════════════════════════════════════════════════

def _conn(cls='csv', server='', dbname='', schema='', table='', filename=''):
    """Build a connection definition."""
    return {'connectionAttributes': {
        'class': cls, 'server': server, 'dbname': dbname,
        'schema': schema, 'table': table, 'filename': filename,
    }}


def _input_node(name, conn_id='c1', fields=None, next_ids=None, **conn_attrs):
    """Input node with configurable connection attributes."""
    node = {
        'baseType': 'input',
        'nodeType': '.v1.LoadCsv',
        'name': name,
        'connectionId': conn_id,
        'connectionAttributes': conn_attrs,
        'fields': fields or [
            {'name': 'ID', 'type': 'integer'},
            {'name': 'Name', 'type': 'string'},
            {'name': 'Value', 'type': 'real'},
        ],
        'nextNodes': [{'nextNodeId': nid} for nid in (next_ids or [])],
    }
    return node


def _clean_node(name='Clean', actions=None, next_ids=None, fields=None):
    """SuperTransform (clean) node."""
    node = {
        'baseType': 'transform',
        'nodeType': '.v2018_3_3.SuperTransform',
        'name': name,
        'beforeActionGroup': {'actions': actions or []},
        'nextNodes': [{'nextNodeId': nid} for nid in (next_ids or [])],
    }
    if fields:
        node['fields'] = fields
    return node


def _join_node(name='Join', join_type='inner', conditions=None, next_ids=None):
    """Join node."""
    return {
        'baseType': 'transform',
        'nodeType': '.v2018_3_3.SuperJoin',
        'name': name,
        'joinType': join_type,
        'joinConditions': conditions or [
            {'leftColumn': 'ID', 'rightColumn': 'ID'},
        ],
        'nextNodes': [{'nextNodeId': nid} for nid in (next_ids or [])],
    }


def _aggregate_node(name='Aggregate', group_fields=None, agg_fields=None, next_ids=None):
    """Aggregate node."""
    return {
        'baseType': 'transform',
        'nodeType': '.v2018_3_3.SuperAggregate',
        'name': name,
        'groupByFields': [{'name': f} for f in (group_fields or ['Category'])],
        'aggregateFields': agg_fields or [
            {'name': 'Amount', 'aggregation': 'SUM', 'newColumnName': 'Total'},
        ],
        'nextNodes': [{'nextNodeId': nid} for nid in (next_ids or [])],
    }


def _union_node(name='Union', next_ids=None):
    """Union node."""
    return {
        'baseType': 'transform',
        'nodeType': '.v2018_3_3.SuperUnion',
        'name': name,
        'nextNodes': [{'nextNodeId': nid} for nid in (next_ids or [])],
    }


def _pivot_node(name='Pivot', pivot_type='columnsToRows', pivot_fields=None, next_ids=None):
    """Pivot node."""
    return {
        'baseType': 'transform',
        'nodeType': '.v2018_3_3.Pivot',
        'name': name,
        'pivotType': pivot_type,
        'pivotFields': [{'name': f} for f in (pivot_fields or ['Q1', 'Q2', 'Q3', 'Q4'])],
        'pivotValuesName': 'Revenue',
        'pivotNamesName': 'Quarter',
        'nextNodes': [{'nextNodeId': nid} for nid in (next_ids or [])],
    }


def _script_node(name='PythonScript', lang='Python', next_ids=None):
    """Script node (Python/R)."""
    return {
        'baseType': 'transform',
        'nodeType': '.v2018_3_3.Script',
        'name': name,
        'scriptLanguage': lang,
        'nextNodes': [{'nextNodeId': nid} for nid in (next_ids or [])],
    }


def _output_node(name='Output', output_type='.v1.PublishExtract', fields=None, **conn_attrs):
    """Output node."""
    node = {
        'baseType': 'output',
        'nodeType': output_type,
        'name': name,
        'connectionAttributes': conn_attrs,
        'fields': fields or [],
        'nextNodes': [],
    }
    return node


def _published_ds_node(name, ds_name=None, next_ids=None):
    """Published datasource input node."""
    return {
        'baseType': 'transform',
        'nodeType': '.v2018_3_3.PublishedDataSource',
        'name': name,
        'publishedDatasourceName': ds_name or name,
        'fields': [{'name': 'ID', 'type': 'integer'}, {'name': 'Value', 'type': 'real'}],
        'nextNodes': [{'nextNodeId': nid} for nid in (next_ids or [])],
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  REALISTIC FLOW DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════

def flow_01_sales_clean():
    """Flow 1: Simple sales data cleaning.
    CSV → Clean (rename, filter, trim) → Output (PublishExtract "Sales_Clean")
    """
    return {
        'nodes': {
            'in1': _input_node('sales_raw', 'c1',
                               fields=[
                                   {'name': 'OrderID', 'type': 'integer'},
                                   {'name': 'Product', 'type': 'string'},
                                   {'name': 'Amount', 'type': 'real'},
                                   {'name': 'Region', 'type': 'string'},
                                   {'name': 'OrderDate', 'type': 'date'},
                               ],
                               next_ids=['clean1'],
                               **{'class': 'csv', 'filename': 'sales_2024.csv'}),
            'clean1': _clean_node('Sales Cleansing', actions=[
                {'actionType': '.v1.RenameColumn', 'columnName': 'Amount',
                 'newColumnName': 'Revenue'},
                {'actionType': '.v1.FilterOperation',
                 'filterExpression': '[Revenue] > 0', 'filterType': 'keep'},
                {'actionType': '.v1.CleanOperation',
                 'columnName': 'Product', 'operation': 'trim'},
            ], next_ids=['out1']),
            'out1': _output_node('Sales_Clean',
                                 fields=[
                                     {'name': 'OrderID', 'type': 'integer'},
                                     {'name': 'Product', 'type': 'string'},
                                     {'name': 'Revenue', 'type': 'real'},
                                     {'name': 'Region', 'type': 'string'},
                                     {'name': 'OrderDate', 'type': 'date'},
                                 ],
                                 server='tableau.company.com',
                                 table='Sales_Clean'),
        },
        'connections': {
            'c1': _conn('csv', filename='sales_2024.csv'),
        },
    }


def flow_02_products_clean():
    """Flow 2: Product master data cleaning.
    Excel → Clean → Output (PublishExtract "Products_Master")
    """
    return {
        'nodes': {
            'in1': _input_node('products', 'c1',
                               fields=[
                                   {'name': 'ProductID', 'type': 'integer'},
                                   {'name': 'ProductName', 'type': 'string'},
                                   {'name': 'Category', 'type': 'string'},
                                   {'name': 'UnitPrice', 'type': 'real'},
                                   {'name': 'Supplier', 'type': 'string'},
                               ],
                               next_ids=['clean1'],
                               **{'class': 'excel-direct', 'filename': 'products.xlsx'}),
            'clean1': _clean_node('Product Cleanup', actions=[
                {'actionType': '.v1.CleanOperation',
                 'columnName': 'ProductName', 'operation': 'proper'},
                {'actionType': '.v1.ReplaceNulls',
                 'columnName': 'Category', 'replacement': 'Unknown'},
            ], next_ids=['out1']),
            'out1': _output_node('Products_Master',
                                 fields=[
                                     {'name': 'ProductID', 'type': 'integer'},
                                     {'name': 'ProductName', 'type': 'string'},
                                     {'name': 'Category', 'type': 'string'},
                                     {'name': 'UnitPrice', 'type': 'real'},
                                     {'name': 'Supplier', 'type': 'string'},
                                 ],
                                 server='tableau.company.com',
                                 table='Products_Master'),
        },
        'connections': {
            'c1': _conn('excel-direct', filename='products.xlsx'),
        },
    }


def flow_03_returns_clean():
    """Flow 3: Returns data cleaning — shares same CSV source pattern as sales.
    CSV → Clean → Output (PublishExtract)
    Uses SAME source server pattern as flow_01 to test source dedup detection.
    """
    return {
        'nodes': {
            'in1': _input_node('returns_raw', 'c1',
                               fields=[
                                   {'name': 'ReturnID', 'type': 'integer'},
                                   {'name': 'OrderID', 'type': 'integer'},
                                   {'name': 'Reason', 'type': 'string'},
                                   {'name': 'Amount', 'type': 'real'},
                               ],
                               next_ids=['clean1'],
                               **{'class': 'csv', 'filename': 'returns_2024.csv'}),
            'clean1': _clean_node('Returns Cleanup', actions=[
                {'actionType': '.v1.FilterOperation',
                 'filterExpression': '[Amount] > 0', 'filterType': 'keep'},
            ], next_ids=['out1']),
            'out1': _output_node('Returns_Clean',
                                 fields=[
                                     {'name': 'ReturnID', 'type': 'integer'},
                                     {'name': 'OrderID', 'type': 'integer'},
                                     {'name': 'Reason', 'type': 'string'},
                                     {'name': 'Amount', 'type': 'real'},
                                 ],
                                 server='tableau.company.com',
                                 table='Returns_Clean'),
        },
        'connections': {
            'c1': _conn('csv', filename='returns_2024.csv'),
        },
    }


def flow_04_combined_analytics():
    """Flow 4: COMPLEX — combines Sales_Clean + Products_Master + Returns_Clean.
    This flow CONSUMES outputs from flows 1, 2, and 3 (cross-flow edges).

    Sales_Clean (input) + Products_Master (input) → Join → Aggregate →
                Returns_Clean (input) → Join → Output "Analytics_Summary"
    """
    return {
        'nodes': {
            # Input: Sales_Clean (output of flow_01)
            'in_sales': _input_node('Sales_Clean', 'c_sales',
                                    fields=[
                                        {'name': 'OrderID', 'type': 'integer'},
                                        {'name': 'Product', 'type': 'string'},
                                        {'name': 'Revenue', 'type': 'real'},
                                        {'name': 'Region', 'type': 'string'},
                                        {'name': 'OrderDate', 'type': 'date'},
                                    ],
                                    next_ids=['join1'],
                                    **{'class': 'sqlserver',
                                       'server': 'tableau.company.com',
                                       'table': 'Sales_Clean'}),
            # Input: Products_Master (output of flow_02)
            'in_products': _input_node('Products_Master', 'c_products',
                                       fields=[
                                           {'name': 'ProductID', 'type': 'integer'},
                                           {'name': 'ProductName', 'type': 'string'},
                                           {'name': 'Category', 'type': 'string'},
                                           {'name': 'UnitPrice', 'type': 'real'},
                                       ],
                                       next_ids=['join1'],
                                       **{'class': 'sqlserver',
                                          'server': 'tableau.company.com',
                                          'table': 'Products_Master'}),
            # Join Sales + Products
            'join1': _join_node('Sales-Products Join', 'left',
                                conditions=[{'leftColumn': 'Product', 'rightColumn': 'ProductName'}],
                                next_ids=['agg1']),
            # Aggregate by Region
            'agg1': _aggregate_node('Revenue by Region',
                                    group_fields=['Region', 'Category'],
                                    agg_fields=[
                                        {'name': 'Revenue', 'aggregation': 'SUM',
                                         'newColumnName': 'TotalRevenue'},
                                        {'name': 'OrderID', 'aggregation': 'COUNTD',
                                         'newColumnName': 'OrderCount'},
                                    ],
                                    next_ids=['join2']),
            # Input: Returns_Clean (output of flow_03)
            'in_returns': _input_node('Returns_Clean', 'c_returns',
                                      fields=[
                                          {'name': 'ReturnID', 'type': 'integer'},
                                          {'name': 'OrderID', 'type': 'integer'},
                                          {'name': 'Reason', 'type': 'string'},
                                          {'name': 'Amount', 'type': 'real'},
                                      ],
                                      next_ids=['join2'],
                                      **{'class': 'sqlserver',
                                         'server': 'tableau.company.com',
                                         'table': 'Returns_Clean'}),
            # Join aggregated results with returns
            'join2': _join_node('Add Returns', 'left',
                                conditions=[{'leftColumn': 'Region', 'rightColumn': 'Region'}],
                                next_ids=['out1']),
            # Final output
            'out1': _output_node('Analytics_Summary',
                                 fields=[
                                     {'name': 'Region', 'type': 'string'},
                                     {'name': 'Category', 'type': 'string'},
                                     {'name': 'TotalRevenue', 'type': 'real'},
                                     {'name': 'OrderCount', 'type': 'integer'},
                                     {'name': 'ReturnAmount', 'type': 'real'},
                                 ],
                                 server='tableau.company.com',
                                 table='Analytics_Summary'),
        },
        'connections': {
            'c_sales': _conn('sqlserver', server='tableau.company.com',
                             table='Sales_Clean'),
            'c_products': _conn('sqlserver', server='tableau.company.com',
                                table='Products_Master'),
            'c_returns': _conn('sqlserver', server='tableau.company.com',
                               table='Returns_Clean'),
        },
    }


def flow_05_quarterly_pivot():
    """Flow 5: Pivot quarterly data + union with prior year.
    CSV (Q data) → Pivot → Union with CSV (prior year) → Output
    This is an ISOLATED flow (no cross-flow edges).
    """
    return {
        'nodes': {
            'in1': _input_node('quarterly_data', 'c1',
                               fields=[
                                   {'name': 'Product', 'type': 'string'},
                                   {'name': 'Q1', 'type': 'real'},
                                   {'name': 'Q2', 'type': 'real'},
                                   {'name': 'Q3', 'type': 'real'},
                                   {'name': 'Q4', 'type': 'real'},
                               ],
                               next_ids=['pivot1'],
                               **{'class': 'csv', 'filename': 'quarterly_2024.csv'}),
            'pivot1': _pivot_node('Unpivot Quarters',
                                  pivot_type='columnsToRows',
                                  pivot_fields=['Q1', 'Q2', 'Q3', 'Q4'],
                                  next_ids=['union1']),
            'in2': _input_node('prior_year', 'c2',
                               fields=[
                                   {'name': 'Product', 'type': 'string'},
                                   {'name': 'Quarter', 'type': 'string'},
                                   {'name': 'Revenue', 'type': 'real'},
                               ],
                               next_ids=['union1'],
                               **{'class': 'csv', 'filename': 'quarterly_2023.csv'}),
            'union1': _union_node('Combine Years', next_ids=['out1']),
            'out1': _output_node('Quarterly_Combined',
                                 fields=[
                                     {'name': 'Product', 'type': 'string'},
                                     {'name': 'Quarter', 'type': 'string'},
                                     {'name': 'Revenue', 'type': 'real'},
                                 ]),
        },
        'connections': {
            'c1': _conn('csv', filename='quarterly_2024.csv'),
            'c2': _conn('csv', filename='quarterly_2023.csv'),
        },
    }


def flow_06_ml_scoring():
    """Flow 6: ML scoring flow with Python script.
    Postgres → Clean → Python Script → Output
    Tests script step handling (manual migration warning).
    """
    return {
        'nodes': {
            'in1': _input_node('customer_features', 'c1',
                               fields=[
                                   {'name': 'CustomerID', 'type': 'integer'},
                                   {'name': 'Recency', 'type': 'integer'},
                                   {'name': 'Frequency', 'type': 'integer'},
                                   {'name': 'Monetary', 'type': 'real'},
                               ],
                               next_ids=['clean1'],
                               **{'class': 'postgres', 'server': 'analytics-db',
                                  'dbname': 'customers', 'table': 'rfm_features'}),
            'clean1': _clean_node('Normalize', actions=[
                {'actionType': '.v1.AddColumn', 'columnName': 'Score',
                 'expression': '[Recency] * 0.3 + [Frequency] * 0.3 + [Monetary] * 0.4'},
            ], next_ids=['script1']),
            'script1': _script_node('Sklearn Scoring', 'Python', next_ids=['out1']),
            'out1': _output_node('ML_Scores',
                                 fields=[
                                     {'name': 'CustomerID', 'type': 'integer'},
                                     {'name': 'Score', 'type': 'real'},
                                     {'name': 'Segment', 'type': 'string'},
                                 ],
                                 server='analytics-db',
                                 table='ml_scores'),
        },
        'connections': {
            'c1': _conn('postgres', server='analytics-db',
                         dbname='customers', table='rfm_features'),
        },
    }


def flow_07_executive_dashboard():
    """Flow 7: Consumes Analytics_Summary (flow_04 output) → further aggregation.
    Creates a 3-level chain: flow_01/02/03 → flow_04 → flow_07
    """
    return {
        'nodes': {
            'in1': _input_node('Analytics_Summary', 'c1',
                               fields=[
                                   {'name': 'Region', 'type': 'string'},
                                   {'name': 'Category', 'type': 'string'},
                                   {'name': 'TotalRevenue', 'type': 'real'},
                                   {'name': 'OrderCount', 'type': 'integer'},
                               ],
                               next_ids=['agg1'],
                               **{'class': 'sqlserver',
                                  'server': 'tableau.company.com',
                                  'table': 'Analytics_Summary'}),
            'agg1': _aggregate_node('Top-Level Summary',
                                    group_fields=['Region'],
                                    agg_fields=[
                                        {'name': 'TotalRevenue', 'aggregation': 'SUM',
                                         'newColumnName': 'GrandTotal'},
                                        {'name': 'OrderCount', 'aggregation': 'SUM',
                                         'newColumnName': 'TotalOrders'},
                                    ],
                                    next_ids=['out1']),
            'out1': _output_node('Executive_KPIs',
                                 fields=[
                                     {'name': 'Region', 'type': 'string'},
                                     {'name': 'GrandTotal', 'type': 'real'},
                                     {'name': 'TotalOrders', 'type': 'integer'},
                                 ]),
        },
        'connections': {
            'c1': _conn('sqlserver', server='tableau.company.com',
                         table='Analytics_Summary'),
        },
    }


def flow_08_shared_source_postgres():
    """Flow 8: Reads same Postgres source as flow_06 (rfm_features).
    Tests source dedup detection (same source across 2+ flows).
    """
    return {
        'nodes': {
            'in1': _input_node('customer_features', 'c1',
                               fields=[
                                   {'name': 'CustomerID', 'type': 'integer'},
                                   {'name': 'Recency', 'type': 'integer'},
                                   {'name': 'Frequency', 'type': 'integer'},
                                   {'name': 'Monetary', 'type': 'real'},
                               ],
                               next_ids=['clean1'],
                               **{'class': 'postgres', 'server': 'analytics-db',
                                  'dbname': 'customers', 'table': 'rfm_features'}),
            'clean1': _clean_node('Filter VIP', actions=[
                {'actionType': '.v1.FilterOperation',
                 'filterExpression': '[Monetary] > 10000', 'filterType': 'keep'},
            ], next_ids=['out1']),
            'out1': _output_node('VIP_Customers',
                                 fields=[
                                     {'name': 'CustomerID', 'type': 'integer'},
                                     {'name': 'Monetary', 'type': 'real'},
                                 ]),
        },
        'connections': {
            'c1': _conn('postgres', server='analytics-db',
                         dbname='customers', table='rfm_features'),
        },
    }


def flow_09_snowflake_warehouse():
    """Flow 9: Snowflake → Clean (type change, split, dedup) → Output to Snowflake.
    Tests Snowflake connector on both source and target side.
    """
    return {
        'nodes': {
            'in1': _input_node('web_events', 'c1',
                               fields=[
                                   {'name': 'EVENT_ID', 'type': 'string'},
                                   {'name': 'USER_ID', 'type': 'integer'},
                                   {'name': 'EVENT_TYPE', 'type': 'string'},
                                   {'name': 'EVENT_TS', 'type': 'datetime'},
                                   {'name': 'PAGE_URL', 'type': 'string'},
                                   {'name': 'DEVICE_INFO', 'type': 'string'},
                               ],
                               next_ids=['clean1'],
                               **{'class': 'snowflake',
                                  'server': 'acme.snowflakecomputing.com',
                                  'dbname': 'ANALYTICS',
                                  'schema': 'RAW',
                                  'table': 'WEB_EVENTS'}),
            'clean1': _clean_node('Parse Events', actions=[
                {'actionType': '.v1.ChangeColumnType', 'columnName': 'EVENT_TS',
                 'newType': 'date'},
                {'actionType': '.v1.SplitColumn', 'columnName': 'DEVICE_INFO',
                 'separator': '|', 'splitCount': 2},
                {'actionType': '.v1.RemoveColumn', 'columnName': 'PAGE_URL'},
                {'actionType': '.v1.FilterOperation',
                 'filterExpression': '[EVENT_TYPE] != "bot"', 'filterType': 'keep'},
            ], next_ids=['out1']),
            'out1': _output_node('Web_Events_Clean',
                                 output_type='.v1.PublishExtract',
                                 fields=[
                                     {'name': 'EVENT_ID', 'type': 'string'},
                                     {'name': 'USER_ID', 'type': 'integer'},
                                     {'name': 'EVENT_TYPE', 'type': 'string'},
                                     {'name': 'EVENT_TS', 'type': 'date'},
                                 ],
                                 **{'class': 'snowflake',
                                    'server': 'acme.snowflakecomputing.com',
                                    'dbname': 'ANALYTICS',
                                    'schema': 'CLEAN',
                                    'table': 'WEB_EVENTS_CLEAN'}),
        },
        'connections': {
            'c1': _conn('snowflake', server='acme.snowflakecomputing.com',
                         dbname='ANALYTICS', schema='RAW', table='WEB_EVENTS'),
        },
    }


def flow_10_bigquery_to_oracle():
    """Flow 10: BigQuery + JSON API → CrossJoin → Clean → Output to Oracle.
    Tests BigQuery source, JSON source, CrossJoin transform, Oracle target.
    """
    return {
        'nodes': {
            'in_bq': _input_node('ad_impressions', 'c_bq',
                                 fields=[
                                     {'name': 'campaign_id', 'type': 'string'},
                                     {'name': 'impression_count', 'type': 'integer'},
                                     {'name': 'click_count', 'type': 'integer'},
                                     {'name': 'spend', 'type': 'real'},
                                     {'name': 'date', 'type': 'date'},
                                 ],
                                 next_ids=['cross1'],
                                 **{'class': 'bigquery',
                                    'server': 'project-123',
                                    'dbname': 'marketing',
                                    'table': 'ad_impressions'}),
            'in_json': _input_node('campaign_meta', 'c_json',
                                   fields=[
                                       {'name': 'campaign_id', 'type': 'string'},
                                       {'name': 'campaign_name', 'type': 'string'},
                                       {'name': 'channel', 'type': 'string'},
                                       {'name': 'budget', 'type': 'real'},
                                   ],
                                   next_ids=['cross1'],
                                   **{'class': 'json',
                                      'filename': 'campaigns.json'}),
            'cross1': {
                'baseType': 'transform',
                'nodeType': '.v2018_3_3.CrossJoin',
                'name': 'CrossJoin Campaigns',
                'nextNodes': [{'nextNodeId': 'clean1'}],
            },
            'clean1': _clean_node('Calc CTR', actions=[
                {'actionType': '.v1.AddColumn', 'columnName': 'CTR',
                 'expression': '[click_count] / [impression_count]'},
                {'actionType': '.v1.AddColumn', 'columnName': 'CPC',
                 'expression': '[spend] / [click_count]'},
            ], next_ids=['out1']),
            'out1': _output_node('Ad_Performance',
                                 fields=[
                                     {'name': 'campaign_id', 'type': 'string'},
                                     {'name': 'campaign_name', 'type': 'string'},
                                     {'name': 'CTR', 'type': 'real'},
                                     {'name': 'CPC', 'type': 'real'},
                                     {'name': 'spend', 'type': 'real'},
                                 ],
                                 **{'class': 'oracle',
                                    'server': 'ora-dwh.corp.local',
                                    'dbname': 'DWH',
                                    'schema': 'MARKETING',
                                    'table': 'AD_PERFORMANCE'}),
        },
        'connections': {
            'c_bq': _conn('bigquery', server='project-123',
                           dbname='marketing', table='ad_impressions'),
            'c_json': _conn('json', filename='campaigns.json'),
        },
    }


def flow_11_salesforce_to_redshift():
    """Flow 11: Salesforce + OData API → Join → Aggregate → Output to Redshift.
    Tests Salesforce CRM source, OData API source, Redshift target.
    """
    return {
        'nodes': {
            'in_sf': _input_node('sf_opportunities', 'c_sf',
                                 fields=[
                                     {'name': 'OpportunityId', 'type': 'string'},
                                     {'name': 'AccountId', 'type': 'string'},
                                     {'name': 'Amount', 'type': 'real'},
                                     {'name': 'Stage', 'type': 'string'},
                                     {'name': 'CloseDate', 'type': 'date'},
                                     {'name': 'OwnerId', 'type': 'string'},
                                 ],
                                 next_ids=['join1'],
                                 **{'class': 'salesforce',
                                    'server': 'acme.my.salesforce.com',
                                    'table': 'Opportunity'}),
            'in_odata': _input_node('erp_accounts', 'c_odata',
                                    fields=[
                                        {'name': 'AccountId', 'type': 'string'},
                                        {'name': 'AccountName', 'type': 'string'},
                                        {'name': 'Industry', 'type': 'string'},
                                        {'name': 'AnnualRevenue', 'type': 'real'},
                                    ],
                                    next_ids=['join1'],
                                    **{'class': 'odata',
                                       'server': 'https://erp.corp.com/odata/v4',
                                       'table': 'Accounts'}),
            'join1': _join_node('Enriched Opps', 'left',
                                conditions=[{'leftColumn': 'AccountId',
                                             'rightColumn': 'AccountId'}],
                                next_ids=['agg1']),
            'agg1': _aggregate_node('Pipeline by Industry',
                                    group_fields=['Industry', 'Stage'],
                                    agg_fields=[
                                        {'name': 'Amount', 'aggregation': 'SUM',
                                         'newColumnName': 'PipelineValue'},
                                        {'name': 'OpportunityId', 'aggregation': 'COUNTD',
                                         'newColumnName': 'DealCount'},
                                    ],
                                    next_ids=['out1']),
            'out1': _output_node('Pipeline_Summary',
                                 fields=[
                                     {'name': 'Industry', 'type': 'string'},
                                     {'name': 'Stage', 'type': 'string'},
                                     {'name': 'PipelineValue', 'type': 'real'},
                                     {'name': 'DealCount', 'type': 'integer'},
                                 ],
                                 **{'class': 'redshift',
                                    'server': 'dwh-cluster.us-east-1.redshift.amazonaws.com',
                                    'dbname': 'analytics',
                                    'schema': 'sales',
                                    'table': 'pipeline_summary'}),
        },
        'connections': {
            'c_sf': _conn('salesforce', server='acme.my.salesforce.com',
                           table='Opportunity'),
            'c_odata': _conn('odata', server='https://erp.corp.com/odata/v4',
                              table='Accounts'),
        },
    }


def flow_12_sap_hana_teradata_merge():
    """Flow 12: SAP HANA + Teradata → Join → Clean → Output (Hyper extract).
    Tests SAP HANA source, Teradata source, Hyper target.
    Multi-join with different key columns.
    """
    return {
        'nodes': {
            'in_sap': _input_node('sap_materials', 'c_sap',
                                  fields=[
                                      {'name': 'MATNR', 'type': 'string'},
                                      {'name': 'MAKTX', 'type': 'string'},
                                      {'name': 'MTART', 'type': 'string'},
                                      {'name': 'MEINS', 'type': 'string'},
                                      {'name': 'ERSDA', 'type': 'date'},
                                  ],
                                  next_ids=['join1'],
                                  **{'class': 'saphana',
                                     'server': 'hana-prod.corp.local:30015',
                                     'dbname': 'S4H',
                                     'schema': 'MARA',
                                     'table': 'MARA'}),
            'in_td': _input_node('td_inventory', 'c_td',
                                 fields=[
                                     {'name': 'MATERIAL_ID', 'type': 'string'},
                                     {'name': 'WAREHOUSE', 'type': 'string'},
                                     {'name': 'QTY_ON_HAND', 'type': 'integer'},
                                     {'name': 'LAST_RECEIPT_DT', 'type': 'date'},
                                 ],
                                 next_ids=['join1'],
                                 **{'class': 'teradata',
                                    'server': 'td-prod.corp.local',
                                    'dbname': 'DW',
                                    'table': 'INVENTORY'}),
            'join1': _join_node('Material-Inventory', 'inner',
                                conditions=[{'leftColumn': 'MATNR',
                                             'rightColumn': 'MATERIAL_ID'}],
                                next_ids=['clean1']),
            'clean1': _clean_node('Enrich', actions=[
                {'actionType': '.v1.RenameColumn', 'columnName': 'MAKTX',
                 'newColumnName': 'MaterialDescription'},
                {'actionType': '.v1.RenameColumn', 'columnName': 'QTY_ON_HAND',
                 'newColumnName': 'QuantityOnHand'},
                {'actionType': '.v1.AddColumn', 'columnName': 'DaysSinceReceipt',
                 'expression': 'DATEDIFF("day", [LAST_RECEIPT_DT], TODAY())'},
            ], next_ids=['out1']),
            'out1': _output_node('Material_Inventory',
                                 output_type='.v1.WriteToHyper',
                                 fields=[
                                     {'name': 'MATNR', 'type': 'string'},
                                     {'name': 'MaterialDescription', 'type': 'string'},
                                     {'name': 'WAREHOUSE', 'type': 'string'},
                                     {'name': 'QuantityOnHand', 'type': 'integer'},
                                     {'name': 'DaysSinceReceipt', 'type': 'integer'},
                                 ],
                                 **{'class': 'hyper',
                                    'filename': 'material_inventory.hyper'}),
        },
        'connections': {
            'c_sap': _conn('saphana', server='hana-prod.corp.local:30015',
                            dbname='S4H', schema='MARA', table='MARA'),
            'c_td': _conn('teradata', server='td-prod.corp.local',
                           dbname='DW', table='INVENTORY'),
        },
    }


def flow_13_azure_datalake_ingest():
    """Flow 13: Azure Blob + ADLS → Union → Clean → Output (Databricks).
    Tests Azure cloud source connectors and Databricks target.
    """
    return {
        'nodes': {
            'in_blob': _input_node('blob_logs_2024', 'c_blob',
                                   fields=[
                                       {'name': 'timestamp', 'type': 'datetime'},
                                       {'name': 'level', 'type': 'string'},
                                       {'name': 'message', 'type': 'string'},
                                       {'name': 'service', 'type': 'string'},
                                       {'name': 'trace_id', 'type': 'string'},
                                   ],
                                   next_ids=['union1'],
                                   **{'class': 'azure-blob',
                                      'server': 'mystorageaccount.blob.core.windows.net',
                                      'filename': 'logs/2024/*.parquet'}),
            'in_adls': _input_node('adls_logs_2023', 'c_adls',
                                   fields=[
                                       {'name': 'timestamp', 'type': 'datetime'},
                                       {'name': 'level', 'type': 'string'},
                                       {'name': 'message', 'type': 'string'},
                                       {'name': 'service', 'type': 'string'},
                                       {'name': 'trace_id', 'type': 'string'},
                                   ],
                                   next_ids=['union1'],
                                   **{'class': 'adls',
                                      'server': 'mydatalake.dfs.core.windows.net',
                                      'filename': 'logs/2023/*.parquet'}),
            'union1': _union_node('Combine Years', next_ids=['clean1']),
            'clean1': _clean_node('Normalize Logs', actions=[
                {'actionType': '.v1.FilterValues', 'columnName': 'level',
                 'values': ['ERROR', 'WARN', 'FATAL'], 'filterType': 'keep'},
                {'actionType': '.v1.CleanOperation',
                 'columnName': 'message', 'operation': 'trim'},
                {'actionType': '.v1.ConditionalColumn', 'columnName': 'severity',
                 'conditions': [
                     {'test': '[level] = "FATAL"', 'value': '1'},
                     {'test': '[level] = "ERROR"', 'value': '2'},
                 ], 'elseValue': '3'},
            ], next_ids=['out1']),
            'out1': _output_node('Unified_Logs',
                                 fields=[
                                     {'name': 'timestamp', 'type': 'datetime'},
                                     {'name': 'level', 'type': 'string'},
                                     {'name': 'message', 'type': 'string'},
                                     {'name': 'service', 'type': 'string'},
                                     {'name': 'severity', 'type': 'integer'},
                                 ],
                                 **{'class': 'databricks',
                                    'server': 'adb-1234567890.azuredatabricks.net',
                                    'dbname': 'observability',
                                    'table': 'unified_logs'}),
        },
        'connections': {
            'c_blob': _conn('azure-blob',
                             server='mystorageaccount.blob.core.windows.net',
                             filename='logs/2024/*.parquet'),
            'c_adls': _conn('adls',
                             server='mydatalake.dfs.core.windows.net',
                             filename='logs/2023/*.parquet'),
        },
    }


def flow_14_mysql_google_sheets():
    """Flow 14: MySQL + Google Sheets → Join → R Script → Output (Azure SQL DW).
    Tests MySQL source, Google Sheets source, R script step, Azure SQL DW target.
    """
    return {
        'nodes': {
            'in_mysql': _input_node('orders', 'c_mysql',
                                    fields=[
                                        {'name': 'order_id', 'type': 'integer'},
                                        {'name': 'customer_id', 'type': 'integer'},
                                        {'name': 'product_id', 'type': 'integer'},
                                        {'name': 'quantity', 'type': 'integer'},
                                        {'name': 'total', 'type': 'real'},
                                        {'name': 'order_date', 'type': 'date'},
                                    ],
                                    next_ids=['join1'],
                                    **{'class': 'mysql',
                                       'server': 'mysql-prod.corp.local',
                                       'dbname': 'ecommerce',
                                       'table': 'orders'}),
            'in_gsheet': _input_node('manual_adjustments', 'c_gs',
                                     fields=[
                                         {'name': 'order_id', 'type': 'integer'},
                                         {'name': 'adjustment', 'type': 'real'},
                                         {'name': 'reason', 'type': 'string'},
                                     ],
                                     next_ids=['join1'],
                                     **{'class': 'google-sheets',
                                        'filename': '1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms'}),
            'join1': _join_node('Apply Adjustments', 'left',
                                conditions=[{'leftColumn': 'order_id',
                                             'rightColumn': 'order_id'}],
                                next_ids=['script1']),
            'script1': _script_node('R Forecast', 'R', next_ids=['out1']),
            'out1': _output_node('Adjusted_Orders',
                                 fields=[
                                     {'name': 'order_id', 'type': 'integer'},
                                     {'name': 'customer_id', 'type': 'integer'},
                                     {'name': 'total', 'type': 'real'},
                                     {'name': 'adjustment', 'type': 'real'},
                                     {'name': 'forecast', 'type': 'real'},
                                 ],
                                 **{'class': 'azure_sql_dw',
                                    'server': 'synapse-prod.sql.azuresynapse.net',
                                    'dbname': 'analytics_dw',
                                    'schema': 'sales',
                                    'table': 'adjusted_orders'}),
        },
        'connections': {
            'c_mysql': _conn('mysql', server='mysql-prod.corp.local',
                              dbname='ecommerce', table='orders'),
            'c_gs': _conn('google-sheets',
                           filename='1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms'),
        },
    }


def flow_15_published_ds_consumer():
    """Flow 15: PublishedDataSource (reads Sales_Clean) → Clean → Output.
    Tests published datasource input path (match_type='published_ds').
    Simulates consuming a Tableau Server published datasource.
    """
    return {
        'nodes': {
            'pub1': _published_ds_node('Sales_Clean', ds_name='Sales_Clean',
                                       next_ids=['clean1']),
            'clean1': _clean_node('Add Margin', actions=[
                {'actionType': '.v1.AddColumn', 'columnName': 'Margin',
                 'expression': '[Value] * 0.35'},
            ], next_ids=['out1']),
            'out1': _output_node('Sales_Margin',
                                 fields=[
                                     {'name': 'ID', 'type': 'integer'},
                                     {'name': 'Value', 'type': 'real'},
                                     {'name': 'Margin', 'type': 'real'},
                                 ]),
        },
        'connections': {},
    }


# All flow builders indexed by name
ALL_FLOWS = {
    'flow_01_sales_clean': flow_01_sales_clean,
    'flow_02_products_clean': flow_02_products_clean,
    'flow_03_returns_clean': flow_03_returns_clean,
    'flow_04_combined_analytics': flow_04_combined_analytics,
    'flow_05_quarterly_pivot': flow_05_quarterly_pivot,
    'flow_06_ml_scoring': flow_06_ml_scoring,
    'flow_07_executive_dashboard': flow_07_executive_dashboard,
    'flow_08_shared_source_postgres': flow_08_shared_source_postgres,
    'flow_09_snowflake_warehouse': flow_09_snowflake_warehouse,
    'flow_10_bigquery_to_oracle': flow_10_bigquery_to_oracle,
    'flow_11_salesforce_to_redshift': flow_11_salesforce_to_redshift,
    'flow_12_sap_hana_teradata_merge': flow_12_sap_hana_teradata_merge,
    'flow_13_azure_datalake_ingest': flow_13_azure_datalake_ingest,
    'flow_14_mysql_google_sheets': flow_14_mysql_google_sheets,
    'flow_15_published_ds_consumer': flow_15_published_ds_consumer,
}


def _write_flow_tfl(directory, name, flow_data):
    """Write a flow dict to a .tfl file. Returns file path."""
    path = os.path.join(directory, f'{name}.tfl')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(flow_data, f, indent=2)
    return path


def _write_flow_tflx(directory, name, flow_data):
    """Write a flow dict to a .tflx ZIP archive. Returns file path."""
    path = os.path.join(directory, f'{name}.tflx')
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('flow.tfl', json.dumps(flow_data, indent=2))
    return path


def _create_all_flows(directory):
    """Write all 15 test flows as .tfl files. Returns list of paths."""
    paths = []
    for name, builder in ALL_FLOWS.items():
        paths.append(_write_flow_tfl(directory, name, builder()))
    return paths


# ═══════════════════════════════════════════════════════════════════════════════
#  PHASE 1 TESTS — prep_flow_analyzer
# ═══════════════════════════════════════════════════════════════════════════════

class TestFingerprint(unittest.TestCase):
    """Test _fingerprint hashing."""

    def test_deterministic(self):
        fp1 = _fingerprint('csv', '', '', '', 'sales.csv')
        fp2 = _fingerprint('csv', '', '', '', 'sales.csv')
        self.assertEqual(fp1, fp2)

    def test_case_insensitive(self):
        fp1 = _fingerprint('CSV', 'Server', 'DB', '', 'Table')
        fp2 = _fingerprint('csv', 'server', 'db', '', 'table')
        self.assertEqual(fp1, fp2)

    def test_different_inputs_differ(self):
        fp1 = _fingerprint('csv', '', '', '', 'sales.csv')
        fp2 = _fingerprint('csv', '', '', '', 'returns.csv')
        self.assertNotEqual(fp1, fp2)


class TestAnalyzeFlowSimple(unittest.TestCase):
    """Test analyze_flow on simple single-source flows."""

    def test_sales_clean_flow(self):
        """Flow 1: CSV → Clean → Output."""
        with tempfile.TemporaryDirectory() as td:
            path = _write_flow_tfl(td, 'sales', flow_01_sales_clean())
            profile = analyze_flow(path)

        self.assertEqual(profile.name, 'sales')
        self.assertEqual(len(profile.inputs), 1)
        self.assertEqual(profile.inputs[0].connection_type, 'textscan')
        self.assertEqual(len(profile.outputs), 1)
        self.assertEqual(profile.outputs[0].name, 'Sales_Clean')
        self.assertGreater(len(profile.transforms), 0)
        self.assertEqual(profile.node_count, 3)

    def test_products_clean_flow(self):
        """Flow 2: Excel → Clean → Output."""
        with tempfile.TemporaryDirectory() as td:
            path = _write_flow_tfl(td, 'products', flow_02_products_clean())
            profile = analyze_flow(path)

        self.assertEqual(len(profile.inputs), 1)
        self.assertEqual(profile.inputs[0].connection_type, 'excel-direct')
        self.assertEqual(len(profile.outputs), 1)

    def test_tflx_archive(self):
        """Analyze a .tflx (ZIP) archive."""
        with tempfile.TemporaryDirectory() as td:
            path = _write_flow_tflx(td, 'sales', flow_01_sales_clean())
            profile = analyze_flow(path)

        self.assertEqual(profile.name, 'sales')
        self.assertEqual(len(profile.inputs), 1)


class TestAnalyzeFlowComplex(unittest.TestCase):
    """Test analyze_flow on complex multi-step flows."""

    def test_combined_analytics_flow(self):
        """Flow 4: 3 inputs → 2 joins → aggregate → output."""
        with tempfile.TemporaryDirectory() as td:
            path = _write_flow_tfl(td, 'combined', flow_04_combined_analytics())
            profile = analyze_flow(path)

        self.assertEqual(len(profile.inputs), 3)
        self.assertEqual(len(profile.outputs), 1)
        self.assertEqual(profile.join_count, 2)
        self.assertGreater(profile.dag_depth, 2)
        # 2 joins×3 + 7 nodes×0.5 = 9.5 → Low (threshold is >10 for Medium)
        self.assertGreaterEqual(profile.complexity_score, 9)

    def test_quarterly_pivot_flow(self):
        """Flow 5: 2 inputs → pivot → union → output."""
        with tempfile.TemporaryDirectory() as td:
            path = _write_flow_tfl(td, 'quarterly', flow_05_quarterly_pivot())
            profile = analyze_flow(path)

        self.assertEqual(len(profile.inputs), 2)
        self.assertEqual(profile.union_count, 1)
        # Pivot is a transform
        pivot_transforms = [t for t in profile.transforms if t.transform_type == 'Pivot']
        self.assertGreaterEqual(len(pivot_transforms), 1)

    def test_ml_scoring_with_script(self):
        """Flow 6: Postgres → Clean → Python Script → Output."""
        with tempfile.TemporaryDirectory() as td:
            path = _write_flow_tfl(td, 'ml', flow_06_ml_scoring())
            profile = analyze_flow(path)

        self.assertEqual(profile.script_count, 1)
        self.assertEqual(profile.inputs[0].connection_type, 'postgres')
        script_transforms = [t for t in profile.transforms if t.transform_type == 'Script']
        self.assertEqual(len(script_transforms), 1)

    def test_snowflake_flow(self):
        """Flow 9: Snowflake → Clean → Snowflake output."""
        with tempfile.TemporaryDirectory() as td:
            path = _write_flow_tfl(td, 'snow', flow_09_snowflake_warehouse())
            profile = analyze_flow(path)

        self.assertEqual(len(profile.inputs), 1)
        self.assertEqual(profile.inputs[0].connection_type, 'snowflake')
        self.assertEqual(profile.inputs[0].server, 'acme.snowflakecomputing.com')
        self.assertEqual(profile.inputs[0].database, 'ANALYTICS')
        self.assertEqual(len(profile.outputs), 1)
        self.assertEqual(profile.outputs[0].name, 'Web_Events_Clean')

    def test_bigquery_json_crossjoin(self):
        """Flow 10: BigQuery + JSON → CrossJoin → Oracle output."""
        with tempfile.TemporaryDirectory() as td:
            path = _write_flow_tfl(td, 'bq', flow_10_bigquery_to_oracle())
            profile = analyze_flow(path)

        self.assertEqual(len(profile.inputs), 2)
        input_types = {i.connection_type for i in profile.inputs}
        self.assertIn('bigquery', input_types)
        self.assertIn('json', input_types)
        join_transforms = [t for t in profile.transforms if t.transform_type == 'Join']
        self.assertGreaterEqual(len(join_transforms), 1)  # CrossJoin maps to Join

    def test_salesforce_odata_to_redshift(self):
        """Flow 11: Salesforce + OData → Join → Aggregate → Redshift."""
        with tempfile.TemporaryDirectory() as td:
            path = _write_flow_tfl(td, 'sf', flow_11_salesforce_to_redshift())
            profile = analyze_flow(path)

        self.assertEqual(len(profile.inputs), 2)
        input_types = {i.connection_type for i in profile.inputs}
        self.assertIn('salesforce', input_types)
        self.assertIn('OData', input_types)
        self.assertEqual(profile.join_count, 1)

    def test_sap_hana_teradata_to_hyper(self):
        """Flow 12: SAP HANA + Teradata → Join → Hyper extract."""
        with tempfile.TemporaryDirectory() as td:
            path = _write_flow_tfl(td, 'sap', flow_12_sap_hana_teradata_merge())
            profile = analyze_flow(path)

        self.assertEqual(len(profile.inputs), 2)
        input_types = {i.connection_type for i in profile.inputs}
        self.assertIn('saphana', input_types)
        self.assertIn('teradata', input_types)
        self.assertEqual(profile.join_count, 1)

    def test_azure_blob_adls_to_databricks(self):
        """Flow 13: Azure Blob + ADLS → Union → Databricks."""
        with tempfile.TemporaryDirectory() as td:
            path = _write_flow_tfl(td, 'azure', flow_13_azure_datalake_ingest())
            profile = analyze_flow(path)

        self.assertEqual(len(profile.inputs), 2)
        input_types = {i.connection_type for i in profile.inputs}
        self.assertIn('Azure Blob', input_types)
        self.assertIn('ADLS', input_types)
        self.assertEqual(profile.union_count, 1)

    def test_mysql_google_sheets_r_script(self):
        """Flow 14: MySQL + Google Sheets → Join → R Script → Azure SQL DW."""
        with tempfile.TemporaryDirectory() as td:
            path = _write_flow_tfl(td, 'mysql_gs', flow_14_mysql_google_sheets())
            profile = analyze_flow(path)

        self.assertEqual(len(profile.inputs), 2)
        input_types = {i.connection_type for i in profile.inputs}
        self.assertIn('mysql', input_types)
        self.assertIn('google-sheets', input_types)
        self.assertEqual(profile.script_count, 1)  # R script
        self.assertEqual(profile.join_count, 1)

    def test_published_datasource_flow(self):
        """Flow 15: PublishedDataSource → Clean → Output."""
        with tempfile.TemporaryDirectory() as td:
            path = _write_flow_tfl(td, 'pub', flow_15_published_ds_consumer())
            profile = analyze_flow(path)

        # Published DS node is a transform, not an input
        self.assertGreater(len(profile.transforms), 0)
        pub_transforms = [t for t in profile.transforms
                          if t.transform_type == 'PublishedDS']
        self.assertGreaterEqual(len(pub_transforms), 1)


class TestAnalyzeFlowsBulk(unittest.TestCase):
    """Test analyze_flows_bulk directory scanning."""

    def test_scans_all_tfl_files(self):
        with tempfile.TemporaryDirectory() as td:
            _create_all_flows(td)
            profiles = analyze_flows_bulk(td)

        self.assertEqual(len(profiles), 15)
        names = {p.name for p in profiles}
        self.assertIn('flow_01_sales_clean', names)
        self.assertIn('flow_04_combined_analytics', names)
        self.assertIn('flow_08_shared_source_postgres', names)
        self.assertIn('flow_09_snowflake_warehouse', names)
        self.assertIn('flow_12_sap_hana_teradata_merge', names)
        self.assertIn('flow_15_published_ds_consumer', names)

    def test_includes_tflx_files(self):
        with tempfile.TemporaryDirectory() as td:
            _write_flow_tfl(td, 'a', flow_01_sales_clean())
            _write_flow_tflx(td, 'b', flow_02_products_clean())
            profiles = analyze_flows_bulk(td)

        self.assertEqual(len(profiles), 2)

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as td:
            profiles = analyze_flows_bulk(td)
        self.assertEqual(len(profiles), 0)

    def test_skips_bad_files(self):
        with tempfile.TemporaryDirectory() as td:
            _write_flow_tfl(td, 'good', flow_01_sales_clean())
            # Write an invalid .tfl
            bad_path = os.path.join(td, 'bad.tfl')
            with open(bad_path, 'w') as f:
                f.write('NOT JSON')
            profiles = analyze_flows_bulk(td)
        self.assertEqual(len(profiles), 1)


class TestFlowProfileProperties(unittest.TestCase):
    """Test FlowProfile computed properties."""

    def test_complexity_score(self):
        p = FlowProfile(name='test', file_path='test.tfl',
                         node_count=10, join_count=2, union_count=1,
                         script_count=1, calc_count=3)
        # 2*3 + 1*2 + 1*5 + 3*1 + 10*0.5 = 6+2+5+3+5 = 21
        self.assertEqual(p.complexity_score, 21)

    def test_complexity_label_low(self):
        p = FlowProfile(name='t', file_path='', node_count=2)
        self.assertEqual(p.complexity_label, 'Low')

    def test_complexity_label_high(self):
        p = FlowProfile(name='t', file_path='', node_count=20,
                         join_count=5, script_count=3)
        self.assertEqual(p.complexity_label, 'High')

    def test_to_dict(self):
        p = FlowProfile(name='test', file_path='/tmp/test.tfl', node_count=5)
        d = p.to_dict()
        self.assertEqual(d['name'], 'test')
        self.assertIn('complexity_score', d)
        self.assertIn('complexity_label', d)


class TestExtractHelpers(unittest.TestCase):
    """Test _extract_inputs, _extract_outputs, _extract_transforms helpers."""

    def test_extract_inputs(self):
        flow = flow_04_combined_analytics()
        inputs = _extract_inputs(flow['nodes'], flow['connections'])
        self.assertEqual(len(inputs), 3)
        names = {i.name for i in inputs}
        self.assertIn('Sales_Clean', names)
        self.assertIn('Products_Master', names)

    def test_extract_outputs(self):
        flow = flow_04_combined_analytics()
        outputs = _extract_outputs(flow['nodes'])
        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0].name, 'Analytics_Summary')

    def test_extract_outputs_leaf_fallback(self):
        """When no baseType=output, use leaf nodes."""
        flow = {
            'n1': _input_node('A', next_ids=['n2']),
            'n2': _clean_node('B'),  # leaf, no nextNodes
        }
        outputs = _extract_outputs(flow)
        self.assertGreaterEqual(len(outputs), 1)

    def test_extract_transforms(self):
        flow = flow_04_combined_analytics()
        from prep_flow_parser import _topological_sort
        sorted_ids = _topological_sort(flow['nodes'])
        transforms = _extract_transforms(sorted_ids, flow['nodes'])
        join_transforms = [t for t in transforms if t.transform_type == 'Join']
        self.assertEqual(len(join_transforms), 2)

    def test_dag_depth(self):
        flow = flow_04_combined_analytics()
        depth = _compute_dag_depth(flow['nodes'])
        self.assertGreater(depth, 2)

    def test_count_calcs(self):
        # _count_calcs looks for node['actions'] with type=AddColumn/etc.
        # Our fixtures use beforeActionGroup, so we test with direct actions
        nodes = {
            'n1': {'baseType': 'transform', 'actions': [
                {'type': 'AddColumn', 'columnName': 'Score'},
                {'type': 'RemoveColumn'},
            ]},
        }
        count = _count_calcs(nodes)
        self.assertEqual(count, 1)


# ═══════════════════════════════════════════════════════════════════════════════
#  PHASE 2 TESTS — prep_lineage (cross-flow graph)
# ═══════════════════════════════════════════════════════════════════════════════

class TestNormalizeName(unittest.TestCase):
    def test_spaces_and_dashes(self):
        self.assertEqual(_normalize_name('Sales-Report  V2'), 'sales_report__v2')

    def test_already_clean(self):
        self.assertEqual(_normalize_name('sales'), 'sales')


class TestFuzzyMatchName(unittest.TestCase):
    def test_identical(self):
        self.assertEqual(_fuzzy_match_name('Sales', 'Sales'), 1.0)

    def test_case_insensitive(self):
        self.assertEqual(_fuzzy_match_name('sales', 'SALES'), 1.0)

    def test_substring(self):
        score = _fuzzy_match_name('Sales', 'Sales_Clean')
        self.assertGreaterEqual(score, 0.7)

    def test_no_match(self):
        score = _fuzzy_match_name('Apple', 'Zebra')
        self.assertLess(score, 0.5)

    def test_empty(self):
        self.assertEqual(_fuzzy_match_name('', 'Sales'), 0.0)


class TestMatchOutputsToInputs(unittest.TestCase):
    """Test cross-flow fingerprint matching."""

    def _build_profiles(self, flow_builders):
        profiles = []
        with tempfile.TemporaryDirectory() as td:
            for name, builder in flow_builders.items():
                path = _write_flow_tfl(td, name, builder())
                profiles.append(analyze_flow(path))
        return profiles

    def test_detects_sales_to_combined_edge(self):
        """Flow 01 output Sales_Clean should match Flow 04 input Sales_Clean."""
        profiles = self._build_profiles({
            'sales_clean': flow_01_sales_clean,
            'combined': flow_04_combined_analytics,
        })
        edges = _match_outputs_to_inputs(profiles)
        # Should find at least one edge from sales_clean → combined
        src_flows = {e.source_flow for e in edges}
        tgt_flows = {e.target_flow for e in edges}
        self.assertTrue(
            any(e.target_flow == 'combined' for e in edges),
            f'Expected edge to combined, got: {[(e.source_flow, e.target_flow) for e in edges]}'
        )

    def test_combined_to_executive_chain(self):
        """Flow 04 → Flow 07 should form a chain via Analytics_Summary."""
        profiles = self._build_profiles({
            'combined': flow_04_combined_analytics,
            'executive': flow_07_executive_dashboard,
        })
        edges = _match_outputs_to_inputs(profiles)
        chain_edges = [e for e in edges
                       if e.source_flow == 'combined' and e.target_flow == 'executive']
        self.assertGreaterEqual(len(chain_edges), 1)

    def test_isolated_flow_no_edges(self):
        """Flow 05 (quarterly pivot) should not match any other flow."""
        profiles = self._build_profiles({
            'sales': flow_01_sales_clean,
            'quarterly': flow_05_quarterly_pivot,
        })
        edges = _match_outputs_to_inputs(profiles)
        quarterly_edges = [e for e in edges
                           if e.source_flow == 'quarterly' or e.target_flow == 'quarterly']
        self.assertEqual(len(quarterly_edges), 0)


class TestBuildLineageGraph(unittest.TestCase):
    """Test build_lineage_graph with the full 8-flow portfolio."""

    @classmethod
    def setUpClass(cls):
        cls._td = tempfile.mkdtemp()
        _create_all_flows(cls._td)
        cls.profiles = analyze_flows_bulk(cls._td)
        cls.graph = build_lineage_graph(cls.profiles)

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls._td, ignore_errors=True)

    def test_total_flows(self):
        self.assertEqual(self.graph.total_flows, 15)

    def test_has_cross_flow_edges(self):
        self.assertGreater(self.graph.total_cross_flow_edges, 0)

    def test_has_external_sources(self):
        self.assertGreater(len(self.graph.external_sources), 0)

    def test_has_final_sinks(self):
        self.assertGreater(len(self.graph.final_sinks), 0)

    def test_isolated_flows_detected(self):
        # Flows with no cross-flow edges: 05 (quarterly), 09-14 (new tech flows)
        self.assertIn('flow_05_quarterly_pivot', self.graph.isolated_flows)
        self.assertIn('flow_09_snowflake_warehouse', self.graph.isolated_flows)
        self.assertIn('flow_12_sap_hana_teradata_merge', self.graph.isolated_flows)
        self.assertIn('flow_13_azure_datalake_ingest', self.graph.isolated_flows)

    def test_layers_not_empty(self):
        self.assertGreater(len(self.graph.layers), 0)

    def test_chains_detected(self):
        # The 8-flow portfolio has fan-in (3 flows → flow_04), so no linear chains.
        # Chain detection is tested directly in TestDetectChains.
        self.assertIsInstance(self.graph.chains, list)

    def test_to_dict(self):
        d = self.graph.to_dict()
        self.assertIn('flows', d)
        self.assertIn('edges', d)
        self.assertIn('total_flows', d)
        self.assertEqual(d['total_flows'], 15)


class TestIdentifyExternalSources(unittest.TestCase):
    """Test external source detection."""

    def test_csv_sources_are_external(self):
        profiles = []
        with tempfile.TemporaryDirectory() as td:
            path = _write_flow_tfl(td, 'sales', flow_01_sales_clean())
            profiles.append(analyze_flow(path))

        edges = []  # no cross-flow edges for single flow
        sources = _identify_external_sources(profiles, edges)
        self.assertGreater(len(sources), 0)
        self.assertTrue(any(s.connection_type == 'textscan' for s in sources))

    def test_fed_inputs_excluded(self):
        """Inputs that are fed by another flow's output should not appear as external."""
        with tempfile.TemporaryDirectory() as td:
            profiles = []
            for name, builder in [('sales', flow_01_sales_clean),
                                   ('combined', flow_04_combined_analytics)]:
                path = _write_flow_tfl(td, name, builder())
                profiles.append(analyze_flow(path))

        edges = _match_outputs_to_inputs(profiles)
        sources = _identify_external_sources(profiles, edges)
        # Sales_Clean input in combined should not be external (it's fed by sales flow)
        source_tables = {s.table_name for s in sources}
        # The CSV source (sales_2024.csv) IS external
        # But Sales_Clean (fed by flow output) should be excluded
        for s in sources:
            if s.table_name == 'Sales_Clean':
                # It should not be in external sources since it's fed by an edge
                fed_edges = [e for e in edges
                             if 'sales_clean' in _normalize_name(e.source_output)]
                if fed_edges:
                    self.fail('Sales_Clean appears as external but is fed by an edge')


class TestFinalSinks(unittest.TestCase):
    """Test final sink detection."""

    def test_terminal_outputs_are_sinks(self):
        with tempfile.TemporaryDirectory() as td:
            profiles = []
            path = _write_flow_tfl(td, 'quarterly', flow_05_quarterly_pivot())
            profiles.append(analyze_flow(path))

        sinks = _identify_final_sinks(profiles, [])
        self.assertGreater(len(sinks), 0)


class TestFlowLayers(unittest.TestCase):
    """Test topological layering."""

    def test_layers_cover_all_flows(self):
        profiles = []
        with tempfile.TemporaryDirectory() as td:
            for name in ['sales', 'combined']:
                builder = {'sales': flow_01_sales_clean,
                           'combined': flow_04_combined_analytics}[name]
                path = _write_flow_tfl(td, name, builder())
                profiles.append(analyze_flow(path))

        edges = _match_outputs_to_inputs(profiles)
        layers = _compute_flow_layers(profiles, edges)
        all_in_layers = [f for layer in layers for f in layer]
        self.assertEqual(set(all_in_layers), {p.name for p in profiles})


class TestDetectChains(unittest.TestCase):
    """Test linear chain detection."""

    def test_finds_chain(self):
        # Create a simple A→B chain
        fp_a = FlowProfile(name='A', file_path='a.tfl')
        fp_b = FlowProfile(name='B', file_path='b.tfl')
        edges = [LineageEdge(source_flow='A', source_output='out',
                             target_flow='B', target_input='in',
                             match_type='exact')]
        chains = _detect_chains([fp_a, fp_b], edges)
        self.assertGreaterEqual(len(chains), 1)
        self.assertIn(['A', 'B'], chains)

    def test_fan_out_not_chain(self):
        """A→B and A→C is fan-out, not a chain."""
        profiles = [FlowProfile(name=n, file_path=f'{n}.tfl') for n in ['A', 'B', 'C']]
        edges = [
            LineageEdge('A', 'out', 'B', 'in', 'exact'),
            LineageEdge('A', 'out', 'C', 'in', 'exact'),
        ]
        chains = _detect_chains(profiles, edges)
        # A fans out to B and C, so no linear chain from A
        for chain in chains:
            self.assertNotIn('A', chain)


# ═══════════════════════════════════════════════════════════════════════════════
#  PHASE 3 TESTS — prep_lineage_report (merge recommendations + report)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSourceOverlap(unittest.TestCase):
    def test_identical_sets(self):
        self.assertAlmostEqual(_source_overlap({'a', 'b'}, {'a', 'b'}), 1.0)

    def test_disjoint_sets(self):
        self.assertAlmostEqual(_source_overlap({'a'}, {'b'}), 0.0)

    def test_partial_overlap(self):
        score = _source_overlap({'a', 'b', 'c'}, {'b', 'c', 'd'})
        self.assertAlmostEqual(score, 0.5)

    def test_empty_sets(self):
        self.assertAlmostEqual(_source_overlap(set(), set()), 0.0)


class TestTransformSimilarity(unittest.TestCase):
    def test_identical_sequences(self):
        self.assertAlmostEqual(_transform_similarity(
            ['Clean', 'Join', 'Aggregate'],
            ['Clean', 'Join', 'Aggregate']), 1.0)

    def test_subsequence(self):
        score = _transform_similarity(
            ['Clean', 'Join', 'Aggregate'],
            ['Clean', 'Aggregate'])
        self.assertGreater(score, 0.5)

    def test_disjoint(self):
        score = _transform_similarity(['Join', 'Join'], ['Pivot', 'Pivot'])
        self.assertAlmostEqual(score, 0.0)

    def test_empty(self):
        self.assertAlmostEqual(_transform_similarity([], []), 0.0)


class TestColumnOverlap(unittest.TestCase):
    def test_identical(self):
        self.assertAlmostEqual(
            _column_overlap({'a', 'b', 'c'}, {'a', 'b', 'c'}), 1.0)

    def test_partial(self):
        self.assertAlmostEqual(
            _column_overlap({'a', 'b'}, {'b', 'c'}), 1/3)


class TestMergeRecommendation(unittest.TestCase):
    def test_strong_merge(self):
        r = MergeRecommendation('source_consolidation', ['A', 'B'], '', '', score=80)
        self.assertEqual(r.level, 'green')
        self.assertEqual(r.label, 'Strong merge')

    def test_possible_merge(self):
        r = MergeRecommendation('chain_collapse', ['A', 'B'], '', '', score=55)
        self.assertEqual(r.level, 'yellow')

    def test_keep_separate(self):
        r = MergeRecommendation('isolated', ['A'], '', '', score=10)
        self.assertEqual(r.level, 'gray')

    def test_to_dict(self):
        r = MergeRecommendation('source_dedup', ['A', 'B', 'C'],
                                 'desc', 'impact', score=72)
        d = r.to_dict()
        self.assertEqual(d['type'], 'source_dedup')
        self.assertEqual(d['level'], 'green')


class TestComputeMergeRecommendations(unittest.TestCase):
    """Test merge recommendation engine on the full 8-flow portfolio."""

    @classmethod
    def setUpClass(cls):
        cls._td = tempfile.mkdtemp()
        _create_all_flows(cls._td)
        cls.profiles = analyze_flows_bulk(cls._td)
        cls.graph = build_lineage_graph(cls.profiles)
        cls.recs = compute_merge_recommendations(cls.graph)

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls._td, ignore_errors=True)

    def test_has_recommendations(self):
        self.assertGreater(len(self.recs), 0)

    def test_chain_collapse_not_present_with_fan_in(self):
        # No linear chains in our 8-flow portfolio (flow_04 has fan-in from 3 flows)
        chain_recs = [r for r in self.recs if r.rec_type == 'chain_collapse']
        self.assertEqual(len(chain_recs), 0)

    def test_isolated_detected(self):
        isolated_recs = [r for r in self.recs if r.rec_type == 'isolated']
        isolated_names = {r.flows[0] for r in isolated_recs}
        self.assertIn('flow_05_quarterly_pivot', isolated_names)

    def test_sorted_by_score_desc(self):
        scores = [r.score for r in self.recs]
        self.assertEqual(scores, sorted(scores, reverse=True))


class TestGenerateHTMLReport(unittest.TestCase):
    """Test HTML report generation."""

    @classmethod
    def setUpClass(cls):
        cls._td = tempfile.mkdtemp()
        _create_all_flows(cls._td)
        cls.profiles = analyze_flows_bulk(cls._td)
        cls.graph = build_lineage_graph(cls.profiles)
        cls.recs = compute_merge_recommendations(cls.graph)

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls._td, ignore_errors=True)

    def test_generates_html_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, 'report.html')
            result = generate_prep_lineage_report(self.graph, self.recs, path)
            self.assertTrue(os.path.exists(result))
            with open(result, encoding='utf-8') as f:
                html = f.read()
            self.assertIn('Lineage Report', html)
            self.assertIn('Flow Inventory', html)
            self.assertIn('Source Inventory', html)
            self.assertIn('Merge Recommendations', html)

    def test_html_contains_mermaid(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, 'report.html')
            generate_prep_lineage_report(self.graph, self.recs, path)
            with open(path, encoding='utf-8') as f:
                html = f.read()
            self.assertIn('mermaid', html)
            self.assertIn('graph LR', html)

    def test_html_has_stat_cards(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, 'report.html')
            generate_prep_lineage_report(self.graph, self.recs, path)
            with open(path, encoding='utf-8') as f:
                html = f.read()
            self.assertIn('stat-card', html)
            self.assertIn('Total Flows', html)


class TestSaveLineageJSON(unittest.TestCase):
    """Test JSON export."""

    def test_generates_json_file(self):
        with tempfile.TemporaryDirectory() as td:
            profiles = []
            path = _write_flow_tfl(td, 'sales', flow_01_sales_clean())
            profiles.append(analyze_flow(path))
            graph = build_lineage_graph(profiles)
            recs = compute_merge_recommendations(graph)

            json_path = os.path.join(td, 'lineage.json')
            save_lineage_json(graph, recs, json_path)

            self.assertTrue(os.path.exists(json_path))
            with open(json_path, encoding='utf-8') as f:
                data = json.load(f)
            self.assertIn('flows', data)
            self.assertIn('edges', data)
            self.assertIn('recommendations', data)
            self.assertIn('timestamp', data)


class TestPrintLineageSummary(unittest.TestCase):
    """Test console summary output."""

    def test_prints_without_error(self):
        with tempfile.TemporaryDirectory() as td:
            _create_all_flows(td)
            profiles = analyze_flows_bulk(td)
            graph = build_lineage_graph(profiles)
            recs = compute_merge_recommendations(graph)

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            print_lineage_summary(graph, recs)
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        self.assertIn('Lineage Analysis', output)
        self.assertIn('Total flows:', output)


# ═══════════════════════════════════════════════════════════════════════════════
#  PHASE 4 TESTS — CLI integration
# ═══════════════════════════════════════════════════════════════════════════════

class TestCLIPrepLineageArg(unittest.TestCase):
    """Test --prep-lineage CLI argument."""

    def test_arg_registered(self):
        from migrate import _build_argument_parser
        parser = _build_argument_parser()
        args = parser.parse_args(['--prep-lineage', 'dir1', 'dir2'])
        self.assertEqual(args.prep_lineage, ['dir1', 'dir2'])

    def test_arg_no_paths(self):
        from migrate import _build_argument_parser
        parser = _build_argument_parser()
        args = parser.parse_args(['--prep-lineage'])
        self.assertEqual(args.prep_lineage, [])

    def test_arg_default_none(self):
        from migrate import _build_argument_parser
        parser = _build_argument_parser()
        args = parser.parse_args([])
        self.assertIsNone(args.prep_lineage)


class TestRunPrepLineageMode(unittest.TestCase):
    """Test run_prep_lineage_mode end-to-end."""

    def test_full_pipeline(self):
        from migrate import run_prep_lineage_mode, ExitCode
        with tempfile.TemporaryDirectory() as td:
            _create_all_flows(td)
            out_dir = os.path.join(td, 'output')

            args = MagicMock()
            args.prep_lineage = [td]
            args.output_dir = out_dir
            args.batch = None

            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            try:
                result = run_prep_lineage_mode(args)
            finally:
                sys.stdout = old_stdout

            self.assertEqual(result, ExitCode.SUCCESS)
            self.assertTrue(os.path.exists(os.path.join(out_dir, 'prep_lineage_report.html')))
            self.assertTrue(os.path.exists(os.path.join(out_dir, 'prep_lineage.json')))

    def test_empty_directory(self):
        from migrate import run_prep_lineage_mode, ExitCode
        with tempfile.TemporaryDirectory() as td:
            args = MagicMock()
            args.prep_lineage = [td]
            args.output_dir = os.path.join(td, 'out')
            args.batch = None

            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            try:
                result = run_prep_lineage_mode(args)
            finally:
                sys.stdout = old_stdout

            self.assertEqual(result, ExitCode.GENERAL_ERROR)

    def test_no_paths_error(self):
        from migrate import run_prep_lineage_mode, ExitCode
        args = MagicMock()
        args.prep_lineage = []
        args.batch = None

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            result = run_prep_lineage_mode(args)
        finally:
            sys.stdout = old_stdout

        self.assertEqual(result, ExitCode.GENERAL_ERROR)

    def test_specific_files(self):
        from migrate import run_prep_lineage_mode, ExitCode
        with tempfile.TemporaryDirectory() as td:
            p1 = _write_flow_tfl(td, 'sales', flow_01_sales_clean())
            p2 = _write_flow_tfl(td, 'products', flow_02_products_clean())
            out_dir = os.path.join(td, 'out')

            args = MagicMock()
            args.prep_lineage = [p1, p2]
            args.output_dir = out_dir
            args.batch = None

            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            try:
                result = run_prep_lineage_mode(args)
            finally:
                sys.stdout = old_stdout

            self.assertEqual(result, ExitCode.SUCCESS)


# ═══════════════════════════════════════════════════════════════════════════════
#  EDGE CASE TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases(unittest.TestCase):
    """Edge cases and boundary conditions."""

    def test_single_flow_isolated(self):
        """A single flow should be classified as isolated."""
        with tempfile.TemporaryDirectory() as td:
            path = _write_flow_tfl(td, 'single', flow_01_sales_clean())
            profiles = [analyze_flow(path)]
            graph = build_lineage_graph(profiles)

        self.assertEqual(graph.total_flows, 1)
        self.assertEqual(graph.total_cross_flow_edges, 0)
        self.assertEqual(len(graph.isolated_flows), 1)

    def test_two_flows_no_overlap(self):
        """Two unrelated flows should have no edges."""
        with tempfile.TemporaryDirectory() as td:
            profiles = []
            path = _write_flow_tfl(td, 'sales', flow_01_sales_clean())
            profiles.append(analyze_flow(path))
            path = _write_flow_tfl(td, 'qtr', flow_05_quarterly_pivot())
            profiles.append(analyze_flow(path))

            graph = build_lineage_graph(profiles)

        self.assertEqual(graph.total_cross_flow_edges, 0)
        self.assertEqual(len(graph.isolated_flows), 2)

    def test_lineage_edge_serialization(self):
        e = LineageEdge('A', 'out', 'B', 'in', 'exact', 1.0)
        d = e.to_dict()
        self.assertEqual(d['source_flow'], 'A')
        self.assertEqual(d['confidence'], 1.0)

    def test_source_endpoint_serialization(self):
        s = SourceEndpoint('fp123', 'csv', consumed_by=[('flow1', 'in1')])
        d = s.to_dict()
        self.assertEqual(d['consumed_by'][0]['flow'], 'flow1')

    def test_sink_endpoint_serialization(self):
        s = SinkEndpoint('fp456', 'PublishExtract', produced_by=('flow1', 'out1'))
        d = s.to_dict()
        self.assertEqual(d['produced_by']['flow'], 'flow1')

    def test_merge_rec_no_actionable(self):
        """Empty graph produces only isolated recommendations."""
        profiles = []
        with tempfile.TemporaryDirectory() as td:
            path = _write_flow_tfl(td, 'solo', flow_05_quarterly_pivot())
            profiles.append(analyze_flow(path))
        graph = build_lineage_graph(profiles)
        recs = compute_merge_recommendations(graph)
        actionable = [r for r in recs if r.score > 0]
        self.assertEqual(len(actionable), 0)


if __name__ == '__main__':
    unittest.main()
