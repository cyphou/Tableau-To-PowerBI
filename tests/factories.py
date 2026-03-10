"""
Test Data Factories — Builder patterns for creating complex test fixtures.

Provides reusable builders for constructing datasources, worksheets,
calculations, models, and complete migration objects with sensible defaults.
Each builder supports method chaining for concise test setup.

Usage:
    from tests.factories import DatasourceFactory, WorksheetFactory, ModelFactory

    ds = DatasourceFactory().with_table("Orders", ["ID:integer", "Amount:real"]).build()
    ws = WorksheetFactory("Sales View").with_columns(["Amount", "Region"]).build()
    model = ModelFactory().with_datasource(ds).with_worksheet(ws).build()
"""

import copy
import uuid


# ═══════════════════════════════════════════════════════════════════════
# Column Builder
# ═══════════════════════════════════════════════════════════════════════

def _parse_column_spec(spec):
    """Parse 'name:type' or 'name' column spec into a dict.
    
    Examples:
        'Amount:real' → {'name': 'Amount', 'datatype': 'real'}
        'Status' → {'name': 'Status', 'datatype': 'string'}
        'ID:integer:notnull' → {'name': 'ID', 'datatype': 'integer', 'nullable': False}
    """
    if isinstance(spec, dict):
        return spec
    parts = spec.split(':')
    col = {'name': parts[0], 'datatype': parts[1] if len(parts) > 1 else 'string'}
    if len(parts) > 2 and parts[2] == 'notnull':
        col['nullable'] = False
    return col


# ═══════════════════════════════════════════════════════════════════════
# Datasource Factory
# ═══════════════════════════════════════════════════════════════════════

class DatasourceFactory:
    """Builder for datasource dicts used in extraction/generation tests."""

    def __init__(self, name='TestDS'):
        self._ds = {
            'name': name,
            'caption': name,
            'connection': {'type': 'SQL Server', 'details': {
                'server': 'localhost', 'database': 'TestDB', 'port': '1433'}},
            'connection_map': {},
            'tables': [],
            'columns': [],
            'calculations': [],
            'relationships': [],
        }

    def with_connection(self, conn_type, **details):
        """Set connection type and details."""
        self._ds['connection'] = {'type': conn_type, 'details': details}
        return self

    def csv(self, filename='data.csv', delimiter=','):
        """Shorthand for CSV connection."""
        return self.with_connection('CSV', filename=filename, delimiter=delimiter)

    def excel(self, filename='data.xlsx'):
        """Shorthand for Excel connection."""
        return self.with_connection('Excel', filename=filename)

    def bigquery(self, project='my-project', dataset='my_dataset'):
        """Shorthand for BigQuery connection."""
        return self.with_connection('BigQuery', project=project, dataset=dataset)

    def postgres(self, server='localhost', database='db', port='5432'):
        """Shorthand for PostgreSQL connection."""
        return self.with_connection('PostgreSQL', server=server, database=database, port=port)

    def with_table(self, name, columns=None):
        """Add a table with columns. Columns can be 'name:type' strings or dicts."""
        cols = [_parse_column_spec(c) for c in (columns or ['ID:integer', 'Value:string'])]
        self._ds['tables'].append({'name': name, 'type': 'table', 'columns': cols})
        return self

    def with_calculation(self, caption, formula, role='measure', datatype='real', name=None):
        """Add a calculation (measure or calculated column)."""
        calc_name = name or f'[Calculation_{len(self._ds["calculations"]) + 1:03d}]'
        self._ds['calculations'].append({
            'name': calc_name, 'caption': caption, 'formula': formula,
            'role': role, 'datatype': datatype,
        })
        return self

    def with_measure(self, caption, formula, datatype='real'):
        """Shorthand for adding a measure."""
        return self.with_calculation(caption, formula, role='measure', datatype=datatype)

    def with_calc_column(self, caption, formula, datatype='string'):
        """Shorthand for adding a calculated column."""
        return self.with_calculation(caption, formula, role='dimension', datatype=datatype)

    def with_relationship(self, from_table, from_col, to_table, to_col,
                          join_type='left', from_count=1000, to_count=100):
        """Add a relationship between tables."""
        self._ds['relationships'].append({
            'join_type': join_type, 'from_table': from_table, 'to_table': to_table,
            'from_column': from_col, 'to_column': to_col,
            'raw_from_count': from_count, 'raw_to_count': to_count,
        })
        return self

    def build(self):
        """Return a deep copy of the datasource dict."""
        return copy.deepcopy(self._ds)


# ═══════════════════════════════════════════════════════════════════════
# Worksheet Factory
# ═══════════════════════════════════════════════════════════════════════

class WorksheetFactory:
    """Builder for worksheet dicts."""

    def __init__(self, name='Sheet 1', datasource='TestDS'):
        self._ws = {
            'name': name, 'type': 'worksheet', 'datasource': datasource,
            'columns': [], 'filters': [], 'mark_encoding': {},
            'axes': [], 'visual_type': None,
        }

    def with_column(self, name, col_type='dimension', datasource=None):
        """Add a column reference."""
        self._ws['columns'].append({
            'name': name, 'type': col_type,
            'datasource': datasource or self._ws['datasource'],
        })
        return self

    def with_columns(self, specs):
        """Add multiple columns. Each spec is 'name:type' or just 'name'."""
        for spec in specs:
            if isinstance(spec, str):
                parts = spec.split(':')
                name = parts[0]
                col_type = parts[1] if len(parts) > 1 else 'dimension'
            else:
                name, col_type = spec, 'dimension'
            self.with_column(name, col_type)
        return self

    def with_mark(self, mark_type='bar'):
        """Set the mark type (visual type)."""
        self._ws['visual_type'] = mark_type
        return self

    def with_filter(self, field, values=None, is_context=False):
        """Add a filter."""
        f = {'field': field, 'is_context': is_context}
        if values:
            f['values'] = values
        self._ws['filters'].append(f)
        return self

    def with_mark_encoding(self, channel, field, **kwargs):
        """Add mark encoding (color, size, shape, label)."""
        enc = {'field': field}
        enc.update(kwargs)
        self._ws['mark_encoding'][channel] = enc
        return self

    def with_axes(self, axes_data):
        """Set axes data."""
        self._ws['axes'] = axes_data
        return self

    def with_tooltip(self, viz_in_tooltip=True):
        """Mark as tooltip worksheet."""
        self._ws['viz_in_tooltip'] = viz_in_tooltip
        return self

    def with_pages_shelf(self, field):
        """Add pages shelf field."""
        self._ws['pages_shelf'] = {'field': field}
        return self

    def with_reference_line(self, value, label='Ref', style='dashed'):
        """Add a reference line."""
        if 'reference_lines' not in self._ws:
            self._ws['reference_lines'] = []
        self._ws['reference_lines'].append({
            'value': value, 'label': label, 'style': style,
        })
        return self

    def build(self):
        return copy.deepcopy(self._ws)


# ═══════════════════════════════════════════════════════════════════════
# Dashboard Factory
# ═══════════════════════════════════════════════════════════════════════

class DashboardFactory:
    """Builder for dashboard dicts."""

    def __init__(self, name='Dashboard 1'):
        self._db = {
            'name': name, 'worksheets': [], 'objects': [],
            'width': 1000, 'height': 800, 'theme': {},
        }

    def with_worksheet(self, ws_name):
        """Add a worksheet reference."""
        self._db['worksheets'].append(ws_name)
        return self

    def with_object(self, obj_type='worksheetReference', name=None, **kwargs):
        """Add a dashboard object."""
        obj = {'type': obj_type, 'name': name or f'obj_{len(self._db["objects"])}'}
        obj.update(kwargs)
        self._db['objects'].append(obj)
        return self

    def with_text(self, text='Sample text'):
        """Add a text box object."""
        return self.with_object('text', text=text)

    def with_image(self, url='logo.png'):
        """Add an image object."""
        return self.with_object('image', url=url)

    def with_theme(self, colors=None, font_family=None):
        """Set theme properties."""
        if colors:
            self._db['theme']['colors'] = colors
        if font_family:
            self._db['theme']['font_family'] = font_family
        return self

    def build(self):
        return copy.deepcopy(self._db)


# ═══════════════════════════════════════════════════════════════════════
# Calculation Factory
# ═══════════════════════════════════════════════════════════════════════

class CalculationFactory:
    """Builder for individual calculation dicts."""

    def __init__(self, caption='Calc1', formula='SUM([Value])'):
        self._calc = {
            'name': f'[Calculation_{id(self) % 10000:04d}]',
            'caption': caption, 'formula': formula,
            'role': 'measure', 'datatype': 'real',
        }

    def as_dimension(self):
        self._calc['role'] = 'dimension'
        return self

    def as_measure(self):
        self._calc['role'] = 'measure'
        return self

    def with_type(self, datatype):
        self._calc['datatype'] = datatype
        return self

    def with_name(self, name):
        self._calc['name'] = name
        return self

    def build(self):
        return copy.deepcopy(self._calc)


# ═══════════════════════════════════════════════════════════════════════
# Parameter Factory
# ═══════════════════════════════════════════════════════════════════════

class ParameterFactory:
    """Builder for parameter dicts."""

    def __init__(self, name='Parameter 1'):
        self._param = {
            'name': name, 'caption': name,
            'datatype': 'integer', 'domain_type': 'range',
            'current_value': '5', 'value': '5', 'values': [],
            'allowable_values': [{'type': 'range', 'min': '0', 'max': '100', 'step': '1'}],
        }

    def range(self, min_val=0, max_val=100, step=1, current=50):
        self._param['domain_type'] = 'range'
        self._param['datatype'] = 'integer'
        self._param['current_value'] = str(current)
        self._param['value'] = str(current)
        self._param['allowable_values'] = [
            {'type': 'range', 'min': str(min_val), 'max': str(max_val), 'step': str(step)},
        ]
        return self

    def list(self, values, current=None, datatype='string'):
        self._param['domain_type'] = 'list'
        self._param['datatype'] = datatype
        self._param['values'] = [{'value': v, 'alias': v} for v in values]
        self._param['current_value'] = current or values[0]
        self._param['value'] = current or values[0]
        self._param['allowable_values'] = [{'value': v, 'alias': v} for v in values]
        return self

    def any(self, current='default'):
        self._param['domain_type'] = 'any'
        self._param['current_value'] = current
        return self

    def build(self):
        return copy.deepcopy(self._param)


# ═══════════════════════════════════════════════════════════════════════
# Model Factory (full converted_objects builder)
# ═══════════════════════════════════════════════════════════════════════

class ModelFactory:
    """Builder for complete converted_objects dicts used in generation tests."""

    def __init__(self, name='TestReport'):
        self._name = name
        self._data = {
            'datasources': [],
            'worksheets': [],
            'dashboards': [],
            'calculations': [],
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

    def with_datasource(self, ds):
        """Add a datasource (dict or DatasourceFactory)."""
        if hasattr(ds, 'build'):
            ds = ds.build()
        self._data['datasources'].append(ds)
        return self

    def with_worksheet(self, ws):
        """Add a worksheet (dict or WorksheetFactory)."""
        if hasattr(ws, 'build'):
            ws = ws.build()
        self._data['worksheets'].append(ws)
        return self

    def with_dashboard(self, db):
        if hasattr(db, 'build'):
            db = db.build()
        self._data['dashboards'].append(db)
        return self

    def with_calculation(self, calc):
        if hasattr(calc, 'build'):
            calc = calc.build()
        self._data['calculations'].append(calc)
        return self

    def with_parameter(self, param):
        if hasattr(param, 'build'):
            param = param.build()
        self._data['parameters'].append(param)
        return self

    def with_filter(self, field, values=None):
        f = {'field': field}
        if values:
            f['values'] = values
        self._data['filters'].append(f)
        return self

    def with_story(self, name, points=None):
        self._data['stories'].append({'name': name, 'points': points or []})
        return self

    def with_action(self, name, action_type='filter', **kwargs):
        a = {'name': name, 'type': action_type}
        a.update(kwargs)
        self._data['actions'].append(a)
        return self

    def with_set(self, name, table='Orders', members=None, formula=None):
        s = {'name': name, 'table': table}
        if members:
            s['members'] = members
        if formula:
            s['formula'] = formula
        self._data['sets'].append(s)
        return self

    def with_group(self, name, table='Orders', field='Category', mapping=None):
        g = {'name': name, 'table': table, 'field': field,
             'members': mapping or {'A': 'Group1', 'B': 'Group2'}}
        self._data['groups'].append(g)
        return self

    def with_bin(self, name, table='Orders', field='Amount', size=10):
        b = {'name': name, 'table': table, 'field': field, 'size': size}
        self._data['bins'].append(b)
        return self

    def with_hierarchy(self, name, levels):
        h = {'name': name, 'levels': levels}
        self._data['hierarchies'].append(h)
        return self

    def with_user_filter(self, name, **kwargs):
        uf = {'name': name}
        uf.update(kwargs)
        self._data['user_filters'].append(uf)
        return self

    def with_custom_sql(self, name, query, datasource='TestDS'):
        self._data['custom_sql'].append({
            'name': name, 'query': query, 'datasource': datasource,
        })
        return self

    @property
    def name(self):
        return self._name

    def build(self):
        """Return a deep copy of the converted_objects dict."""
        return copy.deepcopy(self._data)


# ═══════════════════════════════════════════════════════════════════════
# Quick Builders — One-line helpers for common test scenarios
# ═══════════════════════════════════════════════════════════════════════

def make_simple_model(table_name='Orders', columns=None, measures=None):
    """Create a minimal model with one table and optional measures.
    
    Args:
        table_name: Name of the table
        columns: List of 'name:type' specs (default: ['ID:integer', 'Amount:real', 'Date:datetime'])
        measures: List of (caption, formula) tuples
    
    Returns:
        tuple: (datasources_list, converted_objects_dict)
    """
    cols = columns or ['ID:integer', 'Amount:real', 'Date:datetime']
    ds = DatasourceFactory('DS').with_table(table_name, cols)
    if measures:
        for caption, formula in measures:
            ds.with_measure(caption, formula)
    model = ModelFactory().with_datasource(ds)
    ws = WorksheetFactory('Sheet 1', 'DS').with_columns([c.split(':')[0] for c in cols])
    model.with_worksheet(ws)
    model.with_dashboard(DashboardFactory('Dashboard').with_worksheet('Sheet 1'))
    return [ds.build()], model.build()


def make_multi_table_model():
    """Create a model with Orders + Products tables and a relationship."""
    ds = (DatasourceFactory('DS')
          .with_table('Orders', ['OrderID:integer', 'ProductID:integer', 'Amount:real', 'OrderDate:datetime'])
          .with_table('Products', ['ProductID:integer', 'ProductName:string', 'Price:real'])
          .with_relationship('Orders', 'ProductID', 'Products', 'ProductID'))
    model = (ModelFactory()
             .with_datasource(ds)
             .with_worksheet(WorksheetFactory('Sales', 'DS').with_columns(['Amount:measure', 'ProductName'])))
    return [ds.build()], model.build()


def make_complex_model():
    """Create a complex model with multiple tables, calculations, parameters, and more."""
    ds = (DatasourceFactory('DS')
          .with_table('Orders', ['OrderID:integer', 'CustomerID:integer', 'Amount:real',
                                  'OrderDate:datetime', 'Status:string', 'Region:string'])
          .with_table('Customers', ['CustomerID:integer', 'Name:string', 'City:string',
                                     'Country:string', 'Latitude:real', 'Longitude:real'])
          .with_table('Products', ['ProductID:integer', 'ProductName:string', 'Category:string',
                                    'Price:real'])
          .with_relationship('Orders', 'CustomerID', 'Customers', 'CustomerID')
          .with_measure('Total Sales', 'SUM([Amount])')
          .with_measure('Order Count', 'COUNT([OrderID])')
          .with_calc_column('Status Label', 'IF [Status]="Active" THEN "Yes" ELSE "No" END'))

    model = (ModelFactory()
             .with_datasource(ds)
             .with_worksheet(WorksheetFactory('Overview', 'DS')
                             .with_columns(['Amount:measure', 'Region', 'OrderDate'])
                             .with_mark('bar'))
             .with_worksheet(WorksheetFactory('Details', 'DS')
                             .with_columns(['Name', 'Amount:measure'])
                             .with_mark('text'))
             .with_dashboard(DashboardFactory('Main Dashboard')
                             .with_worksheet('Overview')
                             .with_worksheet('Details'))
             .with_parameter(ParameterFactory('Top N').range(1, 50, 1, 10))
             .with_set('Active Customers', 'Customers', members=['Alice', 'Bob'])
             .with_group('Region Group', 'Orders', 'Region',
                         {'East': 'Eastern', 'West': 'Western'})
             .with_bin('Amount Bin', 'Orders', 'Amount', 50)
             .with_hierarchy('Geo', ['Country', 'City'])
             .with_story('Sales Story', [{'name': 'Point 1'}]))

    return [ds.build()], model.build()
