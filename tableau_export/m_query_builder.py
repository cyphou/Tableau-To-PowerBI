"""
Power Query M Query Builder — Generates M queries from Tableau connections.

Extracted from datasource_extractor.py for maintainability.
Each connector type has its own generator function dispatched via _M_GENERATORS.
"""

import logging

logger = logging.getLogger(__name__)

# ── Type mapping ──────────────────────────────────────────────────────────────

_M_TYPE_MAP = {
    'integer': 'Int64.Type',
    'int64': 'Int64.Type',
    'real': 'type number',
    'double': 'type number',
    'decimal': 'type number',
    'number': 'type number',
    'string': 'type text',
    'boolean': 'type logical',
    'date': 'type date',
    'datetime': 'type datetime',
    'time': 'type time',
    'spatial': 'type text',
    'binary': 'type binary',
    'currency': 'Currency.Type',
    'percentage': 'Percentage.Type',
}


def map_tableau_to_m_type(datatype):
    """Maps Tableau/BIM types to Power Query M types."""
    return _M_TYPE_MAP.get((datatype or '').lower(), 'type text')


def _file_basename(path):
    """Extract just the filename from a potentially full file path.

    DataFolder already contains the directory, so M expressions should only
    reference the filename (e.g. ``DataFolder & "\\file.xlsx"``), not repeat
    the full directory path.
    """
    # Normalise separators, then take the last component
    name = path.replace('\\', '/').rsplit('/', 1)[-1]
    return name if name else path


def _m_escape_col_name(name):
    """Escape column names for M queries (double-quote any internal quotes)."""
    return name.replace('"', '""')


def _m_escape_string(value):
    """Escape a value for embedding inside an M double-quoted string literal.

    Doubles any internal double-quote characters so that ``"server""name"``
    is produced for a value containing a literal quote.
    """
    return (value or '').replace('"', '""')


def _odbc_escape(value):
    """Sanitise a value for embedding inside an ODBC connection string.

    Strips semicolons to prevent DSN parameter injection.
    Also escapes double-quotes for M string safety.
    """
    return _m_escape_string((value or '').replace(';', ''))


# ── Column type change step (shared helper) ──────────────────────────────────

def _build_type_changes(columns):
    """Build a list of M type-change entries for a set of columns."""
    entries = []
    for col in columns:
        m_type = map_tableau_to_m_type(col['datatype'])
        col_name = _m_escape_col_name(col['name'])
        entries.append('{"' + col_name + '", ' + m_type + '}')
    return entries


def _append_type_step(m_query, columns, prev_step='#"Promoted Headers"'):
    """Append a #"Changed Types" step to an M query."""
    type_changes = _build_type_changes(columns)
    if type_changes:
        m_query += f'    #"Changed Types" = Table.TransformColumnTypes({prev_step}, {{\n        '
        m_query += ',\n        '.join(type_changes)
        m_query += '\n    }),\n'
        m_query += '    Result = #"Changed Types"\n'
    else:
        m_query += f'    Result = {prev_step}\n'
    m_query += 'in\n    Result'
    return m_query


# ── Per-connector generators ─────────────────────────────────────────────────

def _gen_m_excel(details, table_name, columns):
    filename = _file_basename(details.get('filename') or (table_name + '.xlsx'))
    file_path_bs = filename.replace('/', '\\')
    safe_step = '#"' + table_name + ' Sheet"'

    m_query = 'let\n'
    m_query += f'    // Source Excel: {filename}\n'
    m_query += f'    Source = Excel.Workbook(File.Contents(DataFolder & "\\{file_path_bs}"), null, true),\n'
    m_query += f'    {safe_step} = Source{{[Item="{table_name}",Kind="Sheet"]}}[Data],\n'
    m_query += f'    #"Promoted Headers" = Table.PromoteHeaders({safe_step}, [PromoteAllScalars=true]),\n'
    return _append_type_step(m_query, columns)


def _gen_m_schema_item(details, table_name, columns,
                      comment, pq_func, server_arg, db_arg, schema='dbo'):
    """Generic M generator for connectors using Schema+Item navigation."""
    safe = '#"' + table_name + ' Table"'
    srv = _m_escape_string(server_arg)
    db = _m_escape_string(db_arg)
    sch = _m_escape_string(schema)
    tbl = _m_escape_string(table_name)
    m_query = 'let\n'
    m_query += f'    // Source {comment}\n'
    m_query += f'    Source = {pq_func}("{srv}", "{db}"),\n'
    m_query += f'    {safe} = Source{{[Schema="{sch}", Item="{tbl}"]}}[Data],\n'
    m_query += f'    Result = {safe}\nin\n    Result'
    return m_query


def _gen_m_sql_server(details, table_name, columns):
    server = details.get('server', 'localhost')
    database = details.get('database', 'MyDatabase')
    return _gen_m_schema_item(details, table_name, columns,
                              'SQL Server', 'Sql.Database', server, database, 'dbo')


def _gen_m_postgresql(details, table_name, columns):
    server = details.get('server', 'localhost')
    port = details.get('port', '5432')
    database = details.get('database', 'postgres')
    return _gen_m_schema_item(details, table_name, columns,
                              'PostgreSQL', 'PostgreSQL.Database',
                              f'{server}:{port}', database, 'public')


def _gen_m_csv(details, table_name, columns):
    filename = _file_basename(details.get('filename') or (table_name + '.csv'))
    delimiter = details.get('delimiter', ',')
    encoding = details.get('encoding', 'utf-8').upper()
    encoding_code = {'UTF-8': '65001', 'UTF8': '65001'}.get(encoding, '65001')
    file_path_bs = filename.replace('/', '\\')

    m_query = f'''let
    // Source CSV: {filename}
    Source = Csv.Document(File.Contents(DataFolder & "\\{file_path_bs}"), [
        Delimiter="{delimiter}",
        Columns={len(columns)},
        Encoding={encoding_code},
        QuoteStyle=QuoteStyle.None
    ]),
    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
'''
    if columns:
        return _append_type_step(m_query, columns)
    else:
        m_query += '    Result = #"Promoted Headers"\nin\n    Result'
        return m_query


def _gen_m_bigquery(details, table_name, columns):
    project = details.get('project', 'my-project')
    dataset = details.get('dataset', 'my_dataset')
    safe = '#"' + table_name + ' Table"'

    m_query = 'let\n'
    m_query += f'    // Source Google BigQuery: {project}.{dataset}\n'
    m_query += f'    Source = GoogleBigQuery.Database([BillingProject="{project}"]),\n'
    m_query += f'    #"{dataset}" = Source{{[Name="{dataset}"]}}[Data],\n'
    m_query += f'    {safe} = #"{dataset}"{{[Name="{table_name}"]}}[Data],\n'
    m_query += f'    Result = {safe}\nin\n    Result'
    return m_query


def _gen_m_mysql(details, table_name, columns):
    server = details.get('server', 'localhost')
    port = details.get('port', '3306')
    database = details.get('database', 'mydb')
    return _gen_m_schema_item(details, table_name, columns,
                              f'MySQL: {server}:{port}', 'MySQL.Database',
                              f'{server}:{port}', database, database)


def _gen_m_oracle(details, table_name, columns):
    server = _m_escape_string(details.get('server', 'localhost'))
    service = _m_escape_string(details.get('service', 'ORCL'))
    port = details.get('port', '1521')
    tbl = _m_escape_string(table_name)
    safe = '#"' + table_name + ' Table"'

    m_query = 'let\n'
    m_query += f'    // Source Oracle: {server}:{port}/{service}\n'
    m_query += f'    Source = Oracle.Database("{server}:{port}/{service}"),\n'
    m_query += f'    {safe} = Source{{[Schema="DBO", Item="{tbl}"]}}[Data],\n'
    m_query += f'    Result = {safe}\nin\n    Result'
    return m_query


def _gen_m_snowflake(details, table_name, columns):
    server = _m_escape_string(details.get('server', 'account.snowflakecomputing.com'))
    database = _m_escape_string(details.get('database', 'MY_DB'))
    warehouse = _m_escape_string(details.get('warehouse', 'MY_WH'))
    schema = _m_escape_string(details.get('schema', 'PUBLIC'))
    tbl = _m_escape_string(table_name)
    safe = '#"' + table_name + ' Table"'

    m_query = 'let\n'
    m_query += f'    // Source Snowflake: {server}\n'
    m_query += f'    Source = Snowflake.Databases("{server}", "{warehouse}"),\n'
    m_query += f'    #"{database}" = Source{{[Name="{database}"]}}[Data],\n'
    m_query += f'    #"{schema}" = #"{database}"{{[Name="{schema}"]}}[Data],\n'
    m_query += f'    {safe} = #"{schema}"{{[Name="{tbl}"]}}[Data],\n'
    m_query += f'    Result = {safe}\nin\n    Result'
    return m_query


def _gen_m_geojson(details, table_name, columns):
    filename = _file_basename(details.get('filename', 'file.geojson'))
    file_path_bs = filename.replace('/', '\\')

    prop_cols = [col for col in columns if col.get('name', '') != 'Geometry']
    prop_names = ", ".join([f'"{_m_escape_col_name(col["name"])}"' for col in prop_cols])

    type_changes = []
    for col in columns:
        cname = col.get('name', '')
        if cname.lower() == 'geometry':
            continue
        m_type = map_tableau_to_m_type(col.get('datatype', 'string'))
        type_changes.append(f'{{"{_m_escape_col_name(cname)}", {m_type}}}')
    type_step = ',\n        '.join(type_changes)

    has_geometry = any(col.get('name', '').lower() == 'geometry' for col in columns)

    m_query = f'''let
    // Source GeoJSON: {filename}
    Source = Json.Document(File.Contents(DataFolder & "\\{file_path_bs}")),
    features = Source[features],
    #"Converted to Table" = Table.FromList(features, Splitter.SplitByNothing(), null, null, ExtraValues.Error),
    #"Expanded Column1" = Table.ExpandRecordColumn(#"Converted to Table", "Column1", {{"properties", "geometry"}}),
    #"Expanded properties" = Table.ExpandRecordColumn(#"Expanded Column1", "properties", {{{prop_names}}}),'''

    if has_geometry:
        m_query += '''
    #"Geometry to Text" = Table.TransformColumns(#"Expanded properties", {{"geometry", each Text.FromBinary(Json.FromValue(_)), type text}}),
    #"Renamed Geometry" = Table.RenameColumns(#"Geometry to Text", {{"geometry", "Geometry"}}),'''
        last_step = '#"Renamed Geometry"'
    else:
        last_step = '#"Expanded properties"'

    if type_changes:
        m_query += f'''
    #"Changed Types" = Table.TransformColumnTypes({last_step}, {{
        {type_step}
    }})
in
    #"Changed Types"'''
    else:
        m_query += f'''
in
    {last_step}'''

    return m_query


def _gen_m_fallback(details, table_name, columns):
    conn_type = details.get('_conn_type', 'Unknown')
    col_list = ", ".join([f'"{col["name"]}"' for col in columns if 'name' in col])
    sample1 = ", ".join([f'"Sample {i+1}"' if col.get('datatype') == 'string' else str(i+1) for i, col in enumerate(columns)])
    sample2 = ", ".join([f'"Sample {i+2}"' if col.get('datatype') == 'string' else str(i+2) for i, col in enumerate(columns)])
    return f'''let
    // TODO: Configure the data source for connector type: {conn_type}
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {{{col_list}}},
            {{
                {{{sample1}}},
                {{{sample2}}}
            }}
        )
    otherwise
        #table({{{col_list}}}, {{}})  // Empty table on error
in
    Source'''


# ── Additional connectors ────────────────────────────────────────────────────

def _gen_m_teradata(details, table_name, columns):
    server = details.get('server', 'localhost')
    database = details.get('database', 'MyDB')
    safe = '#"' + table_name + ' Table"'

    m_query = 'let\n'
    m_query += f'    // Source Teradata: {server}\n'
    m_query += f'    Source = Teradata.Database("{server}"),\n'
    m_query += f'    #"{database}" = Source{{[Name="{database}"]}}[Data],\n'
    m_query += f'    {safe} = #"{database}"{{[Name="{table_name}"]}}[Data],\n'
    m_query += f'    Result = {safe}\nin\n    Result'
    return m_query


def _gen_m_sap_hana(details, table_name, columns):
    server = details.get('server', 'localhost')
    port = details.get('port', '30015')
    safe = '#"' + table_name + ' Table"'

    m_query = 'let\n'
    m_query += f'    // Source SAP HANA: {server}:{port}\n'
    m_query += f'    Source = SapHana.Database("{server}:{port}"),\n'
    m_query += f'    {safe} = Source{{[Schema="PUBLIC", Name="{table_name}"]}}[Data],\n'
    m_query += f'    Result = {safe}\nin\n    Result'
    return m_query


def _gen_m_sap_bw(details, table_name, columns):
    server = details.get('server', 'sap-bw-server')
    system_number = details.get('system_number', '00')
    client_id = details.get('client_id', '')
    language = details.get('language', 'EN')
    cube = details.get('cube', table_name)
    catalog = details.get('catalog', '$INFOCUBE')

    m_query = 'let\n'
    m_query += f'    // Source SAP BW: {server} (System {system_number})\n'
    m_query += f'    Source = SapBusinessWarehouse.Cubes("{server}", "{system_number}", "{client_id}", [Language="{language}"]),\n'
    m_query += f'    #"{catalog}" = Source{{[Name="{catalog}"]}}[Data],\n'
    m_query += f'    #"{cube}" = #"{catalog}"{{[Name="{cube}"]}}[Data],\n'
    m_query += f'    Result = #"{cube}"\nin\n    Result'
    return m_query


def _gen_m_redshift(details, table_name, columns):
    server = details.get('server', 'cluster.redshift.amazonaws.com')
    port = details.get('port', '5439')
    database = details.get('database', 'mydb')
    return _gen_m_schema_item(details, table_name, columns,
                              f'Amazon Redshift: {server}:{port}',
                              'AmazonRedshift.Database',
                              f'{server}:{port}', database, 'public')


def _gen_m_databricks(details, table_name, columns):
    server = details.get('server', 'adb-xxxxx.azuredatabricks.net')
    http_path = details.get('http_path', '/sql/1.0/warehouses/xxxxx')
    catalog = details.get('catalog', 'main')
    schema = details.get('schema', 'default')
    safe = '#"' + table_name + ' Table"'

    m_query = 'let\n'
    m_query += f'    // Source Databricks: {server}\n'
    m_query += f'    Source = Databricks.Catalogs("{server}", "{http_path}"),\n'
    m_query += f'    #"{catalog}" = Source{{[Name="{catalog}"]}}[Data],\n'
    m_query += f'    #"{schema}" = #"{catalog}"{{[Name="{schema}"]}}[Data],\n'
    m_query += f'    {safe} = #"{schema}"{{[Name="{table_name}"]}}[Data],\n'
    m_query += f'    Result = {safe}\nin\n    Result'
    return m_query


def _gen_m_spark(details, table_name, columns):
    server = details.get('server', 'localhost')
    port = details.get('port', '10000')
    safe = '#"' + table_name + ' Table"'

    m_query = 'let\n'
    m_query += f'    // Source Spark SQL: {server}:{port}\n'
    m_query += f'    Source = SparkSql.Database("{server}", "{port}"),\n'
    m_query += f'    {safe} = Source{{[Name="{table_name}"]}}[Data],\n'
    m_query += f'    Result = {safe}\nin\n    Result'
    return m_query


def _gen_m_azure_sql(details, table_name, columns):
    server = details.get('server', 'myserver.database.windows.net')
    database = details.get('database', 'MyDatabase')
    return _gen_m_schema_item(details, table_name, columns,
                              'Azure SQL Database', 'AzureSQL.Database', server, database, 'dbo')


def _gen_m_synapse(details, table_name, columns):
    server = details.get('server', 'myworkspace.sql.azuresynapse.net')
    database = details.get('database', 'MyPool')
    return _gen_m_schema_item(details, table_name, columns,
                              'Azure Synapse Analytics', 'AzureSQL.Database', server, database, 'dbo')


def _gen_m_google_sheets(details, table_name, columns):
    spreadsheet_id = details.get('spreadsheet_id', 'SPREADSHEET_ID')
    sheet_name = details.get('sheet_name', table_name)

    m_query = 'let\n'
    m_query += f'    // Source Google Sheets: {spreadsheet_id}\n'
    m_query += f'    Source = Web.Contents("https://docs.google.com/spreadsheets/d/{spreadsheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}"),\n'
    m_query += '    Parsed = Csv.Document(Source, [Delimiter=",", Encoding=65001]),\n'
    m_query += '    #"Promoted Headers" = Table.PromoteHeaders(Parsed, [PromoteAllScalars=true]),\n'
    return _append_type_step(m_query, columns)


def _gen_m_sharepoint(details, table_name, columns):
    site_url = details.get('site_url', 'https://contoso.sharepoint.com/sites/mysite')
    filename = details.get('filename', table_name + '.xlsx')

    m_query = 'let\n'
    m_query += f'    // Source SharePoint: {site_url}\n'
    m_query += f'    Source = SharePoint.Files("{site_url}", [ApiVersion = 15]),\n'
    m_query += f'    FileRow = Table.SelectRows(Source, each [Name] = "{filename}"),\n'
    m_query += '    FileContent = FileRow{{0}}[Content],\n'
    m_query += '    Workbook = Excel.Workbook(FileContent, null, true),\n'
    m_query += f'    Sheet = Workbook{{[Item="{table_name}",Kind="Sheet"]}}[Data],\n'
    m_query += '    #"Promoted Headers" = Table.PromoteHeaders(Sheet, [PromoteAllScalars=true]),\n'
    return _append_type_step(m_query, columns)


def _gen_m_json(details, table_name, columns):
    filename = _file_basename(details.get('filename', table_name + '.json'))
    file_path_bs = filename.replace('/', '\\')

    m_query = 'let\n'
    m_query += f'    // Source JSON: {filename}\n'
    m_query += f'    Source = Json.Document(File.Contents(DataFolder & "\\{file_path_bs}")),\n'
    m_query += '    #"Converted to Table" = if Value.Is(Source, type list) then Table.FromRecords(Source) else Table.FromRecords({Source}),\n'
    m_query += '    #"Promoted Headers" = #"Converted to Table",\n'
    return _append_type_step(m_query, columns)


def _gen_m_xml(details, table_name, columns):
    filename = _file_basename(details.get('filename', table_name + '.xml'))
    file_path_bs = filename.replace('/', '\\')

    m_query = 'let\n'
    m_query += f'    // Source XML: {filename}\n'
    m_query += f'    Source = Xml.Tables(File.Contents(DataFolder & "\\{file_path_bs}")),\n'
    m_query += '    #"Promoted Headers" = Source,\n'
    return _append_type_step(m_query, columns)


def _gen_m_pdf(details, table_name, columns):
    filename = _file_basename(details.get('filename', table_name + '.pdf'))
    file_path_bs = filename.replace('/', '\\')

    # PDF connector depth: page range and table selection
    start_page = details.get('start_page')
    end_page = details.get('end_page')
    table_index = details.get('table_index', 0)

    options_parts = []
    if start_page is not None:
        options_parts.append(f'[StartPage={int(start_page)}]')
    if end_page is not None:
        options_parts.append(f'[EndPage={int(end_page)}]')
    options_str = ', '.join(options_parts)

    m_query = 'let\n'
    m_query += f'    // Source PDF: {filename}\n'
    if options_str:
        m_query += f'    Source = Pdf.Tables(File.Contents(DataFolder & "\\{file_path_bs}"), {options_str}),\n'
    else:
        m_query += f'    Source = Pdf.Tables(File.Contents(DataFolder & "\\{file_path_bs}")),\n'
    m_query += f'    Table1 = Source{{{{{table_index}}}}}[Data],\n'
    m_query += '    #"Promoted Headers" = Table.PromoteHeaders(Table1, [PromoteAllScalars=true]),\n'
    return _append_type_step(m_query, columns)


def _gen_m_salesforce(details, table_name, columns):
    safe = '#"' + table_name + ' Table"'
    soql = details.get('soql', '')
    api_version = details.get('api_version', '')
    include_relationships = details.get('include_relationships', False)

    m_query = 'let\n'
    m_query += '    // Source Salesforce\n'

    # Build Salesforce.Data options
    sf_options = []
    if api_version:
        sf_options.append(f'[ApiVersion="{api_version}"]')

    if soql:
        # SOQL passthrough query
        if sf_options:
            m_query += f'    Source = Salesforce.Data(null, {sf_options[0]}),\n'
        else:
            m_query += '    Source = Salesforce.Data(),\n'
        m_query += f'    {safe} = Value.NativeQuery(Source, "{soql}"),\n'
    else:
        # Standard table navigation
        if sf_options:
            m_query += f'    Source = Salesforce.Data(null, {sf_options[0]}),\n'
        else:
            m_query += '    Source = Salesforce.Data(),\n'
        m_query += f'    {safe} = Source{{[Name="{table_name}"]}}[Data],\n'

    # Relationship traversal: expand lookup columns
    relationships = details.get('relationships', [])
    prev_step = safe
    for i, rel in enumerate(relationships):
        rel_col = rel.get('column', '')
        expand_cols = rel.get('expand', [])
        if rel_col and expand_cols:
            expand_list = ', '.join([f'"{c}"' for c in expand_cols])
            step_name = f'#"Expanded {rel_col}"'
            m_query += (f'    {step_name} = Table.ExpandRecordColumn({prev_step}, '
                        f'"{rel_col}", {{{expand_list}}}),\n')
            prev_step = step_name

    m_query += f'    Result = {prev_step}\nin\n    Result'
    return m_query


def _gen_m_web(details, table_name, columns):
    url = details.get('url', 'https://api.example.com/data')

    m_query = 'let\n'
    m_query += f'    // Source Web: {url}\n'
    m_query += f'    Source = Web.Contents("{url}"),\n'
    m_query += '    Json = Json.Document(Source),\n'
    m_query += '    #"Converted to Table" = Table.FromRecords(if Value.Is(Json, type list) then Json else {Json}),\n'
    m_query += '    #"Promoted Headers" = #"Converted to Table",\n'
    return _append_type_step(m_query, columns)


def _gen_m_custom_sql(details, table_name, columns):
    """Generate M query using native SQL query (for Tableau custom SQL sources).

    Supports parameter binding via Value.NativeQuery's optional record argument.
    Parameters are extracted from the ``params`` key in *details*.
    """
    server = _m_escape_string(details.get('server', 'localhost'))
    database = _m_escape_string(details.get('database', 'MyDatabase'))
    sql_query = details.get('sql_query', f'SELECT * FROM {table_name}')
    params = details.get('params', {})  # {name: default_value}
    # Escape quotes in SQL for M string
    sql_escaped = sql_query.replace('"', '""')

    m_query = 'let\n'
    m_query += '    // Source: Custom SQL Query\n'
    if params:
        # Build parameter record:  [Param1="value1", Param2="value2"]
        param_items = ', '.join(f'{k}="{str(v).replace(chr(34), chr(34)+chr(34))}"' for k, v in params.items())
        m_query += f'    Source = Value.NativeQuery(Sql.Database("{server}", "{database}"), "'
        m_query += sql_escaped
        m_query += f'", [{param_items}], [EnableFolding=true]),\n'
    else:
        m_query += f'    Source = Sql.Database("{server}", "{database}", [Query="'
        m_query += sql_escaped
        m_query += '"]),\n'
    m_query += '    Result = Source\nin\n    Result'
    return m_query


def _gen_m_odata(details, table_name, columns):
    """Generate M query for OData feed."""
    url = details.get('server', details.get('url', 'https://services.odata.org/V4/Northwind/Northwind.svc'))
    m_query = 'let\n'
    m_query += f'    // Source OData: {url}\n'
    m_query += f'    Source = OData.Feed("{url}"),\n'
    m_query += f'    {table_name}_Table = Source{{[Name="{table_name}",Signature="table"]}}[Data],\n'
    m_query += f'    #"Promoted Headers" = {table_name}_Table,\n'
    return _append_type_step(m_query, columns)


def _gen_m_google_analytics(details, table_name, columns):
    """Generate M query for Google Analytics."""
    view_id = details.get('view_id', details.get('server', 'GA_VIEW_ID'))
    m_query = 'let\n'
    m_query += f'    // Source Google Analytics: View {view_id}\n'
    m_query += '    // Note: Requires Google Analytics connector in Power BI Desktop\n'
    m_query += f'    Source = GoogleAnalytics.Accounts(),\n'
    m_query += f'    ViewData = Source{{[Name="{view_id}"]}}[Data],\n'
    m_query += '    #"Promoted Headers" = ViewData,\n'
    return _append_type_step(m_query, columns)


def _gen_m_azure_blob(details, table_name, columns):
    """Generate M query for Azure Blob Storage / ADLS Gen2."""
    account = details.get('server', details.get('account', 'mystorageaccount'))
    container = details.get('database', details.get('container', 'mycontainer'))
    # Detect ADLS Gen2 vs Blob by URL pattern
    is_adls = 'dfs.core.windows.net' in account or 'adls' in account.lower()
    if is_adls:
        m_query = 'let\n'
        m_query += f'    // Source Azure Data Lake Storage Gen2: {account}\n'
        m_query += f'    Source = AzureStorage.DataLake("https://{account}.dfs.core.windows.net/{container}"),\n'
    else:
        m_query = 'let\n'
        m_query += f'    // Source Azure Blob Storage: {account}\n'
        m_query += f'    Source = AzureStorage.Blobs("https://{account}.blob.core.windows.net/{container}"),\n'
    m_query += f'    FileRow = Table.SelectRows(Source, each Text.Contains([Name], "{table_name}")),\n'
    m_query += '    FileContent = FileRow{{0}}[Content],\n'
    m_query += '    Parsed = Csv.Document(FileContent, [Delimiter=",", Encoding=65001]),\n'
    m_query += '    #"Promoted Headers" = Table.PromoteHeaders(Parsed, [PromoteAllScalars=true]),\n'
    return _append_type_step(m_query, columns)


def _gen_m_vertica(details, table_name, columns):
    """Generate M query for Vertica (via ODBC)."""
    server = _odbc_escape(details.get('server', 'vertica-server'))
    database = _odbc_escape(details.get('database', 'MyDatabase'))
    schema = _m_escape_string(details.get('schema', 'public'))
    m_query = 'let\n'
    m_query += f'    // Source Vertica: {server}/{database}\n'
    m_query += f'    Source = Odbc.DataSource("DSN=Vertica;Server={server};Database={database}"),\n'
    m_query += f'    SchemaTable = Source{{[Schema="{schema}",Item="{_m_escape_string(table_name)}"]}}[Data],\n'
    m_query += '    #"Promoted Headers" = SchemaTable,\n'
    return _append_type_step(m_query, columns)


def _gen_m_impala(details, table_name, columns):
    """Generate M query for Apache Impala."""
    server = _odbc_escape(details.get('server', 'impala-server'))
    port = _odbc_escape(details.get('port', '21050'))
    m_query = 'let\n'
    m_query += f'    // Source Impala: {server}:{port}\n'
    m_query += f'    Source = Odbc.DataSource("Driver={{Cloudera ODBC Driver for Impala}};Host={server};Port={port}"),\n'
    m_query += f'    Table = Source{{[Name="{_m_escape_string(table_name)}"]}}[Data],\n'
    m_query += '    #"Promoted Headers" = Table,\n'
    return _append_type_step(m_query, columns)


def _gen_m_hadoop_hive(details, table_name, columns):
    """Generate M query for Hadoop Hive / HDInsight."""
    server = _odbc_escape(details.get('server', 'hive-server'))
    port = _odbc_escape(details.get('port', '443'))
    m_query = 'let\n'
    m_query += f'    // Source Hadoop Hive: {server}:{port}\n'
    m_query += f'    Source = Odbc.DataSource("Driver={{Microsoft Hive ODBC Driver}};Host={server};Port={port}"),\n'
    m_query += f'    Table = Source{{[Name="{_m_escape_string(table_name)}"]}}[Data],\n'
    m_query += '    #"Promoted Headers" = Table,\n'
    return _append_type_step(m_query, columns)


def _gen_m_presto(details, table_name, columns):
    """Generate M query for Presto / Trino (via ODBC)."""
    server = _odbc_escape(details.get('server', 'presto-server'))
    catalog = _odbc_escape(details.get('database', details.get('catalog', 'hive')))
    schema = _odbc_escape(details.get('schema', 'default'))
    m_query = 'let\n'
    m_query += f'    // Source Presto/Trino: {server}/{catalog}.{schema}\n'
    m_query += f'    Source = Odbc.DataSource("Driver={{Starburst Presto ODBC Driver}};Host={server};Catalog={catalog};Schema={schema}"),\n'
    m_query += f'    Table = Source{{[Name="{_m_escape_string(table_name)}"]}}[Data],\n'
    m_query += '    #"Promoted Headers" = Table,\n'
    return _append_type_step(m_query, columns)


# ── Microsoft Fabric Lakehouse connector ─────────────────────────────────────

def _gen_m_fabric_lakehouse(details, table_name, columns):
    """Generate M query for Microsoft Fabric Lakehouse."""
    workspace_id = details.get('workspace_id', 'WORKSPACE_ID')
    lakehouse_id = details.get('lakehouse_id', 'LAKEHOUSE_ID')
    safe = '#"' + table_name + ' Table"'

    m_query = 'let\n'
    m_query += f'    // Source Microsoft Fabric Lakehouse\n'
    m_query += f'    Source = Lakehouse.Contents(null, "{workspace_id}", "{lakehouse_id}"),\n'
    m_query += f'    {safe} = Source{{[Id="{table_name}"]}}[Data],\n'
    m_query += f'    Result = {safe}\nin\n    Result'
    return m_query


def _gen_m_dataverse(details, table_name, columns):
    """Generate M query for Microsoft Dataverse (Common Data Service)."""
    org_url = details.get('server', details.get('org_url', 'https://org.crm.dynamics.com'))
    safe = '#"' + table_name + ' Table"'

    m_query = 'let\n'
    m_query += f'    // Source Dataverse: {org_url}\n'
    m_query += f'    Source = CommonDataService.Database("{org_url}"),\n'
    m_query += f'    {safe} = Source{{[Name="{table_name}"]}}[Data],\n'
    m_query += f'    Result = {safe}\nin\n    Result'
    return m_query


# ── Dispatch table ────────────────────────────────────────────────────────────

def _gen_m_hyper(details, table_name, columns):
    """Generate M query for a Hyper extract data source.

    Tries to load actual schema/data from hyper_reader; falls back to
    an inline #table() with the column list.
    """
    try:
        import os as _os
        from hyper_reader import read_hyper, generate_m_for_hyper_table
        filename = details.get('filename', '')
        hyper_rows = details.get('hyper_max_rows', 20)
        if filename and _os.path.isfile(filename):
            result = read_hyper(filename, max_rows=hyper_rows)
            tables = result.get('tables', [])
            # Find matching table or use the first
            target = None
            for t in tables:
                if t.get('table', '').lower() == table_name.lower():
                    target = t
                    break
            if target is None and tables:
                target = tables[0]
            if target and target.get('columns'):
                return generate_m_for_hyper_table(target, row_limit=hyper_rows)
    except (ImportError, OSError, KeyError, ValueError) as exc:
        logger.debug('Hyper read failed for %s: %s', table_name, exc)

    # Fallback: structured #table() with column names from metadata
    col_list = ', '.join([f'"{ col["name"] }"' for col in columns if 'name' in col])
    return f'''let
    // Hyper extract: {table_name}
    // TODO: Replace with actual data source or imported CSV.
    Source = #table(
        {{{col_list}}},
        {{}}
    )
in
    Source'''


def _gen_m_sqlproxy(details, table_name, columns):
    """Generate M query for a Tableau Server Published Datasource (sqlproxy).

    sqlproxy is Tableau's internal connector for published datasources on
    Tableau Server/Cloud.  The actual data lives behind the published
    datasource — typically a database like SQL Server, Oracle, PostgreSQL, etc.

    The generated M query includes:
    - The Tableau Server URL and published datasource name as comments
    - A placeholder SQL Server connection (most common backend)
    - Alternative connection templates for Oracle, PostgreSQL, and Snowflake
    - A sample #table() fallback so the report opens without errors
    """
    server = details.get('server', 'tableau-server')
    ds_name = details.get('server_ds_name', '') or details.get('dbname', table_name)
    port = details.get('port', '443')
    channel = details.get('channel', 'https')

    col_list = ', '.join([f'"{ col["name"] }"' for col in columns if 'name' in col])
    sample1 = ', '.join(
        [f'"Sample {i+1}"' if col.get('datatype') == 'string' else str(i + 1)
         for i, col in enumerate(columns)])
    sample2 = ', '.join(
        [f'"Sample {i+2}"' if col.get('datatype') == 'string' else str(i + 2)
         for i, col in enumerate(columns)])

    return f'''let
    // ================================================================
    // Tableau Server Published Datasource: {ds_name}
    // Server: {channel}://{server}:{port}
    // ================================================================
    // This table was sourced from a Tableau Server published datasource.
    // Replace the sample data below with your actual database connection.
    //
    // Option A — SQL Server:
    //   Source = Sql.Database("your-server", "your-database"){{[Schema="dbo", Item="{table_name}"]}}[Data]
    //
    // Option B — Oracle:
    //   Source = Oracle.Database("your-server:1521/service"){{[Schema="SCHEMA", Name="{table_name.upper()}"]}}[Data]
    //
    // Option C — PostgreSQL:
    //   Source = PostgreSQL.Database("your-server:5432", "your-database"){{[Schema="public", Name="{table_name}"]}}[Data]
    //
    // Option D — Snowflake:
    //   Source = Snowflake.Databases("account.snowflakecomputing.com", "WAREHOUSE"){{[Name="DB"]}}[Data]{{[Schema="PUBLIC", Name="{table_name.upper()}"]}}[Data]
    // ================================================================
    Source = #table(
        {{{col_list}}},
        {{
            {{{sample1}}},
            {{{sample2}}}
        }}
    )
in
    Source'''


# ── Sprint 61: New Connector Generators ───────────────────────────────────────

def _gen_m_mongodb(details, table_name, columns):
    """MongoDB Atlas / MongoDB BI connector."""
    server = details.get('server', 'cluster0.mongodb.net')
    database = details.get('database', 'mydb')
    collection = details.get('collection', table_name)
    m_query = 'let\n'
    m_query += f'    // Source MongoDB: {server}\n'
    m_query += f'    Source = MongoDBAtlas.Database("{server}", "{database}"),\n'
    m_query += f'    #"{collection}" = Source{{[Name="{collection}"]}}[Data],\n'
    m_query += f'    Result = #"{collection}"\nin\n    Result'
    return m_query


def _gen_m_cosmosdb(details, table_name, columns):
    """Azure Cosmos DB (SQL API or MongoDB API)."""
    endpoint = details.get('server', 'https://myaccount.documents.azure.com:443/')
    database = details.get('database', 'mydb')
    container = details.get('collection', table_name)
    m_query = 'let\n'
    m_query += f'    // Source Azure Cosmos DB: {endpoint}\n'
    m_query += f'    Source = DocumentDB.Contents("{endpoint}", "{database}"),\n'
    m_query += f'    #"{container}" = Source{{[Id="{container}"]}}[Data],\n'
    m_query += f'    Result = #"{container}"\nin\n    Result'
    return m_query


def _gen_m_athena(details, table_name, columns):
    """Amazon Athena via ODBC."""
    region = _odbc_escape(details.get('region', details.get('server', 'us-east-1')))
    s3_output = details.get('s3_output', 's3://my-bucket/athena-output/')
    catalog = _m_escape_string(details.get('catalog', details.get('database', 'AwsDataCatalog')))
    custom_sql = details.get('custom_sql', '')
    safe_table = _m_escape_string(table_name)
    if custom_sql:
        m_query = 'let\n'
        m_query += f'    // Source Amazon Athena: {region}\n'
        m_query += f'    Source = Odbc.Query("dsn=AmazonAthena;Region={region}",\n'
        m_query += f'        "{_m_escape_string(custom_sql)}")\n'
        m_query += 'in\n    Source'
    else:
        m_query = 'let\n'
        m_query += f'    // Source Amazon Athena: {region}\n'
        m_query += f'    Source = Odbc.DataSource("dsn=AmazonAthena;Region={region}"),\n'
        m_query += f'    #"{catalog}" = Source{{[Name="{catalog}"]}}[Data],\n'
        m_query += f'    #"{safe_table} Table" = #"{catalog}"{{[Name="{safe_table}"]}}[Data],\n'
        m_query += f'    Result = #"{safe_table} Table"\nin\n    Result'
    return m_query


def _gen_m_db2(details, table_name, columns):
    """IBM DB2 connector."""
    server = details.get('server', 'localhost')
    database = details.get('database', 'SAMPLE')
    schema = details.get('schema', 'DB2INST1')
    return _gen_m_schema_item(details, table_name, columns,
                              'IBM DB2', 'DB2.Database', server, database, schema)


_M_GENERATORS = {
    'Excel':            _gen_m_excel,
    'SQL Server':       _gen_m_sql_server,
    'PostgreSQL':       _gen_m_postgresql,
    'CSV':              _gen_m_csv,
    'BigQuery':         _gen_m_bigquery,
    'MySQL':            _gen_m_mysql,
    'Oracle':           _gen_m_oracle,
    'Snowflake':        _gen_m_snowflake,
    'GeoJSON':          _gen_m_geojson,
    'Teradata':         _gen_m_teradata,
    'SAP HANA':         _gen_m_sap_hana,
    'SAP BW':           _gen_m_sap_bw,
    'Amazon Redshift':  _gen_m_redshift,
    'Redshift':         _gen_m_redshift,
    'Databricks':       _gen_m_databricks,
    'Spark SQL':        _gen_m_spark,
    'Spark':            _gen_m_spark,
    'Azure SQL':        _gen_m_azure_sql,
    'Azure Synapse':    _gen_m_synapse,
    'Synapse':          _gen_m_synapse,
    'Google Sheets':    _gen_m_google_sheets,
    'SharePoint':       _gen_m_sharepoint,
    'JSON':             _gen_m_json,
    'XML':              _gen_m_xml,
    'PDF':              _gen_m_pdf,
    'Salesforce':       _gen_m_salesforce,
    'Web':              _gen_m_web,
    'Custom SQL':       _gen_m_custom_sql,
    'OData':            _gen_m_odata,
    'Google Analytics': _gen_m_google_analytics,
    'Azure Blob':       _gen_m_azure_blob,
    'Azure Blob Storage': _gen_m_azure_blob,
    'ADLS':             _gen_m_azure_blob,
    'Azure Data Lake':  _gen_m_azure_blob,
    'Vertica':          _gen_m_vertica,
    'Impala':           _gen_m_impala,
    'Hadoop Hive':      _gen_m_hadoop_hive,
    'Hive':             _gen_m_hadoop_hive,
    'HDInsight':        _gen_m_hadoop_hive,
    'Presto':           _gen_m_presto,
    'Trino':            _gen_m_presto,
    'Fabric Lakehouse': _gen_m_fabric_lakehouse,
    'Lakehouse':        _gen_m_fabric_lakehouse,
    'Dataverse':        _gen_m_dataverse,
    'Common Data Service': _gen_m_dataverse,
    'CDS':              _gen_m_dataverse,
    'hyper':            _gen_m_hyper,
    'Hyper':            _gen_m_hyper,
    'extract':          _gen_m_hyper,
    'Tableau Server':   _gen_m_sqlproxy,
    'sqlproxy':         _gen_m_sqlproxy,
    'SQLPROXY':         _gen_m_sqlproxy,
    # Sprint 61: New connectors
    'MongoDB':          _gen_m_mongodb,
    'MongoDB Atlas':    _gen_m_mongodb,
    'mongodb':          _gen_m_mongodb,
    'Cosmos DB':        _gen_m_cosmosdb,
    'Azure Cosmos DB':  _gen_m_cosmosdb,
    'cosmosdb':         _gen_m_cosmosdb,
    'DocumentDB':       _gen_m_cosmosdb,
    'Amazon Athena':    _gen_m_athena,
    'Athena':           _gen_m_athena,
    'athena':           _gen_m_athena,
    'IBM DB2':          _gen_m_db2,
    'DB2':              _gen_m_db2,
    'db2':              _gen_m_db2,
}


# ── Public API ────────────────────────────────────────────────────────────────

def generate_power_query_m(connection, table):
    """
    Generates a Power Query M query from a Tableau connection.

    Args:
        connection: Dict with connection type and details
        table: Dict with table name and columns

    Returns:
        str: Complete M query
    """
    conn_type = connection.get('type', 'Unknown')
    details = connection.get('details', {})
    table_name = table.get('name', 'Table1')
    columns = table.get('columns', [])

    generator = _M_GENERATORS.get(conn_type)
    if generator:
        return generator(details, table_name, columns)

    # Fallback — pass conn_type through details for the message
    details_copy = dict(details)
    details_copy['_conn_type'] = conn_type
    return _gen_m_fallback(details_copy, table_name, columns)


# ── Connection String Templating ─────────────────────────────────────────────

import re as _re

def apply_connection_template(m_query, env_vars=None):
    """Replace ${ENV.NAME} placeholders in M queries with environment variable values.

    Allows parameterizing M queries for different environments (dev/staging/prod).
    If env_vars is None, replaces with M parameter references instead.

    Supported placeholders:
        ${ENV.SERVER}     - Database server hostname
        ${ENV.DATABASE}   - Database name
        ${ENV.PORT}       - Port number
        ${ENV.USERNAME}   - Username
        ${ENV.PASSWORD}   - Password
        ${ENV.WAREHOUSE}  - Snowflake/Databricks warehouse
        ${ENV.SCHEMA}     - Database schema
        ${ENV.ACCOUNT}    - Storage account name
        ${ENV.CONTAINER}  - Blob/ADLS container
        ${ENV.CATALOG}    - Databricks/BigQuery catalog
        ${ENV.URL}        - Web/API URL
        Any custom ${ENV.XXXX} patterns

    Args:
        m_query: M query string potentially containing ${ENV.*} placeholders
        env_vars: Optional dict mapping env var names to values.
                  If None, generates M parameter references.

    Returns:
        str: M query with placeholders replaced
    """
    if not m_query or '${ENV.' not in m_query:
        return m_query

    def _replacer(match):
        var_name = match.group(1)
        if env_vars and var_name in env_vars:
            return env_vars[var_name]
        # Default: replace with M parameter reference
        return '" & ' + var_name + ' & "'

    return _re.sub(r'\$\{ENV\.([A-Za-z_]+)\}', _replacer, m_query)


def templatize_m_query(m_query, connection=None):
    """Convert hardcoded connection strings in an M query to ${ENV.*} templates.

    This is the reverse of apply_connection_template — it turns concrete
    server/database values into environment variable placeholders so the
    generated M queries can be parameterized per environment.

    Args:
        m_query: Concrete M query with hardcoded connection values
        connection: Optional connection dict with 'details' to identify values

    Returns:
        str: M query with connection values replaced by ${ENV.*} placeholders
    """
    if not m_query or not connection:
        return m_query

    details = connection.get('details', {})
    replacements = []

    # Build replacement list (longest values first to avoid partial matches)
    for key, env_var in [
        ('server', 'SERVER'), ('database', 'DATABASE'), ('port', 'PORT'),
        ('warehouse', 'WAREHOUSE'), ('schema', 'SCHEMA'),
        ('account', 'ACCOUNT'), ('container', 'CONTAINER'),
        ('catalog', 'CATALOG'), ('project', 'PROJECT'),
        ('dataset', 'DATASET'), ('http_path', 'HTTP_PATH'),
        ('site_url', 'SITE_URL'), ('url', 'URL'),
    ]:
        value = details.get(key, '')
        if value and len(value) > 2:
            replacements.append((value, f'${{ENV.{env_var}}}'))

    # Sort by length descending to replace longer values first
    replacements.sort(key=lambda x: -len(x[0]))

    result = m_query
    for old_val, new_val in replacements:
        result = result.replace(old_val, new_val)

    return result


# ══════════════════════════════════════════════════════════════════════════════
# Tableau Prep Transformation Helpers — Power Query M Step Generators
# ══════════════════════════════════════════════════════════════════════════════
# These functions generate Power Query M transformation steps corresponding
# to Tableau Prep operations. They return (step_name, step_expression) tuples
# that can be injected into any source query via inject_m_steps().
#
# Usage pattern:
#   m_query = generate_power_query_m(connection, table)
#   steps = []
#   steps.append(m_transform_rename({"old_name": "new_name"}))
#   steps.append(m_transform_filter_values("Status", ["Active"]))
#   m_query = inject_m_steps(m_query, steps)
# ══════════════════════════════════════════════════════════════════════════════


def inject_m_steps(m_query, steps):
    """
    Inject additional M transformation steps into an existing M query.
    Inserts steps before the final 'in' clause.

    Can be called multiple times on the same query — previous Result =
    terminators are stripped and re-created at the new end.

    Args:
        m_query: str — Complete M query (let ... in ...)
        steps: list[tuple[str, str]] — (step_name, step_expression) pairs.
            Use {prev} placeholder in expressions to reference the previous step.

    Returns:
        str — Modified M query with additional steps injected
    """
    if not steps:
        return m_query

    # Find the last 'in\n' in the query
    in_idx = m_query.rfind('\nin\n')
    if in_idx == -1:
        in_idx = m_query.rfind('\nin ')
    if in_idx == -1:
        return m_query  # malformed query, return as-is

    before_in = m_query[:in_idx]

    # Strip any existing "Result = ..." line (from previous inject_m_steps call)
    lines = before_in.split('\n')
    while lines and lines[-1].strip().startswith('Result'):
        lines.pop()
    # Strip trailing comma from the last real step.
    # Must account for // line comments — a comma inside a comment is NOT actual M syntax.
    if lines:
        last_line = lines[-1].rstrip()
        comment_idx = last_line.find('//')
        if comment_idx > 0:
            # Strip the comment; check if the code portion already has a trailing comma
            code_part = last_line[:comment_idx].rstrip()
            if not code_part.endswith(','):
                code_part += ','
            lines[-1] = code_part
        elif not last_line.endswith(','):
            lines[-1] = last_line + ','
    before_in = '\n'.join(lines)

    # Find the last step name referenced (skip Result and comments)
    last_step = None
    for line in reversed(lines):
        stripped = line.strip()
        if stripped.startswith('Result') or stripped.startswith('//') or not stripped:
            continue
        if '=' in stripped:
            last_step = stripped.split('=')[0].strip().rstrip(',')
            break
    if not last_step:
        last_step = 'Source'

    # Collect existing step names to avoid duplicates
    existing_steps = set()
    for line in lines:
        stripped = line.strip()
        if '=' in stripped and not stripped.startswith('//'):
            name = stripped.split('=')[0].strip().rstrip(',')
            existing_steps.add(name)

    # Build the chain — replace {prev} with actual previous step name
    prev_step = last_step
    new_lines = []
    for step_name, step_expr_template in steps:
        # Deduplicate step name — append numeric suffix if collision
        unique_name = step_name
        counter = 2
        while unique_name in existing_steps:
            unique_name = f'{step_name} {counter}'
            if step_name.startswith('#"') and step_name.endswith('"'):
                unique_name = f'{step_name[:-1]} {counter}"'
            counter += 1
        existing_steps.add(unique_name)
        step_expr = step_expr_template.replace('{prev}', prev_step)
        new_lines.append(f'    {unique_name} = {step_expr},')
        prev_step = unique_name

    injected = '\n'.join(new_lines)
    return before_in + '\n' + injected + '\n    Result = ' + prev_step + '\nin\n    Result'


# ── Column operations ─────────────────────────────────────────────────────────

def m_transform_rename(renames):
    """Rename columns. renames: dict {old_name: new_name}"""
    pairs = ', '.join([f'{{"{old}", "{new}"}}' for old, new in renames.items()])
    return ('#"Renamed Columns"', f'Table.RenameColumns({{prev}}, {{{pairs}}})')


def m_transform_remove_columns(columns):
    """Remove specified columns."""
    cols = ', '.join([f'"{c}"' for c in columns])
    return ('#"Removed Columns"', f'Table.RemoveColumns({{prev}}, {{{cols}}})')


def m_transform_select_columns(columns):
    """Keep only specified columns."""
    cols = ', '.join([f'"{c}"' for c in columns])
    return ('#"Selected Columns"', f'Table.SelectColumns({{prev}}, {{{cols}}})')


def m_transform_duplicate_column(source_col, new_col):
    """Duplicate a column."""
    return ('#"Duplicated Column"',
            f'Table.DuplicateColumn({{prev}}, "{source_col}", "{new_col}")')


def m_transform_reorder_columns(column_order):
    """Reorder columns."""
    cols = ', '.join([f'"{c}"' for c in column_order])
    return ('#"Reordered Columns"', f'Table.ReorderColumns({{prev}}, {{{cols}}})')


def m_transform_split_by_delimiter(column, delimiter, num_parts=None):
    """Split column by delimiter."""
    name = f'#"Split {column}"'
    if num_parts:
        return (name,
                f'Table.SplitColumn({{prev}}, "{column}", '
                f'Splitter.SplitTextByDelimiter("{delimiter}", QuoteStyle.None), {num_parts})')
    return (name,
            f'Table.SplitColumn({{prev}}, "{column}", '
            f'Splitter.SplitTextByDelimiter("{delimiter}", QuoteStyle.None))')


def m_transform_merge_columns(columns, new_name, separator=" "):
    """Merge multiple columns into one."""
    cols = ', '.join([f'"{c}"' for c in columns])
    return ('#"Merged Columns"',
            f'Table.CombineColumns({{prev}}, {{{cols}}}, '
            f'Combiner.CombineTextByDelimiter("{separator}", QuoteStyle.None), "{new_name}")')


# ── Value operations ──────────────────────────────────────────────────────────

def m_transform_replace_value(column, old_value, new_value, replace_text=True):
    """Replace values in a column."""
    replacer = 'Replacer.ReplaceText' if replace_text else 'Replacer.ReplaceValue'
    old_repr = f'"{old_value}"' if isinstance(old_value, str) else ('null' if old_value is None else str(old_value))
    new_repr = f'"{new_value}"' if isinstance(new_value, str) else ('null' if new_value is None else str(new_value))
    return ('#"Replaced Values"',
            f'Table.ReplaceValue({{prev}}, {old_repr}, {new_repr}, {replacer}, {{"{column}"}})')


def m_transform_replace_nulls(column, default_value):
    """Replace null values with a default."""
    val_repr = f'"{default_value}"' if isinstance(default_value, str) else str(default_value)
    return (f'#"Replaced Nulls in {column}"',
            f'Table.ReplaceValue({{prev}}, null, {val_repr}, Replacer.ReplaceValue, {{"{column}"}})')


def _m_text_transform(columns, m_func, step_label):
    """Generic text column transform — shared by trim/clean/upper/lower/proper."""
    transforms = ', '.join([f'{{"{c}", {m_func}}}' for c in columns])
    return (f'#"{step_label}"', f'Table.TransformColumns({{prev}}, {{{transforms}}})')


def m_transform_trim(columns):
    """Trim whitespace from text columns."""
    return _m_text_transform(columns, 'Text.Trim', 'Trimmed Text')


def m_transform_clean(columns):
    """Remove non-printable characters from text columns."""
    return _m_text_transform(columns, 'Text.Clean', 'Cleaned Text')


def m_transform_upper(columns):
    """Convert text columns to uppercase."""
    return _m_text_transform(columns, 'Text.Upper', 'Uppercased')


def m_transform_lower(columns):
    """Convert text columns to lowercase."""
    return _m_text_transform(columns, 'Text.Lower', 'Lowercased')


def m_transform_proper_case(columns):
    """Convert text columns to proper case (Title Case)."""
    return _m_text_transform(columns, 'Text.Proper', 'Proper Cased')


def m_transform_fill_down(columns):
    """Fill down null values in columns."""
    cols = ', '.join([f'"{c}"' for c in columns])
    return ('#"Filled Down"', f'Table.FillDown({{prev}}, {{{cols}}})')


def m_transform_fill_up(columns):
    """Fill up null values in columns."""
    cols = ', '.join([f'"{c}"' for c in columns])
    return ('#"Filled Up"', f'Table.FillUp({{prev}}, {{{cols}}})')


# ── Filter operations ─────────────────────────────────────────────────────────

def m_transform_filter_values(column, keep_values):
    """Keep only rows where column matches specified values (categorical)."""
    if not keep_values:
        return ('#"Filtered Rows"', '{prev}')
    if len(keep_values) == 1:
        condition = f'each [#"{column}"] = "{keep_values[0]}"'
    else:
        vals = ', '.join([f'"{v}"' for v in keep_values])
        condition = f'each List.Contains({{{vals}}}, [#"{column}"])'
    return ('#"Filtered Rows"', f'Table.SelectRows({{prev}}, {condition})')


def m_transform_exclude_values(column, exclude_values):
    """Exclude rows where column matches specified values."""
    if len(exclude_values) == 1:
        condition = f'each [#"{column}"] <> "{exclude_values[0]}"'
    else:
        vals = ', '.join([f'"{v}"' for v in exclude_values])
        condition = f'each not List.Contains({{{vals}}}, [#"{column}"])'
    return ('#"Excluded Rows"', f'Table.SelectRows({{prev}}, {condition})')


def m_transform_filter_range(column, min_val=None, max_val=None):
    """Keep rows in a numeric or date range."""
    conditions = []
    if min_val is not None:
        conditions.append(f'[#"{column}"] >= {min_val}')
    if max_val is not None:
        conditions.append(f'[#"{column}"] <= {max_val}')
    condition = ' and '.join(conditions) if conditions else 'true'
    return ('#"Filtered Range"', f'Table.SelectRows({{prev}}, each {condition})')


def m_transform_filter_nulls(column, keep_nulls=False):
    """Filter null or non-null values."""
    op = '=' if keep_nulls else '<>'
    return ('#"Filtered Nulls"', f'Table.SelectRows({{prev}}, each [#"{column}"] {op} null)')


def m_transform_filter_contains(column, text):
    """Keep rows where column contains text (wildcard match)."""
    return ('#"Filtered Contains"',
            f'Table.SelectRows({{prev}}, each Text.Contains([#"{column}"], "{text}"))')


def m_transform_distinct(columns=None):
    """Remove duplicates. If columns specified, deduplicate on those columns only."""
    if columns:
        cols = ', '.join([f'"{c}"' for c in columns])
        return ('#"Removed Duplicates"', f'Table.Distinct({{prev}}, {{{cols}}})')
    return ('#"Removed Duplicates"', 'Table.Distinct({prev})')


def m_transform_top_n(n, sort_column, descending=True):
    """Keep top N rows by a column."""
    order = 'Order.Descending' if descending else 'Order.Ascending'
    return ('#"Top N"',
            f'Table.FirstN(Table.Sort({{prev}}, {{{{"{sort_column}", {order}}}}}), {n})')


# ── Aggregate operations ──────────────────────────────────────────────────────

_M_AGG_MAP = {
    'sum':     ('List.Sum', 'type number'),
    'avg':     ('List.Average', 'type number'),
    'average': ('List.Average', 'type number'),
    'count':   ('Table.RowCount', 'Int64.Type'),
    'countd':  (None, 'Int64.Type'),  # special: List.Count(List.Distinct(...))
    'min':     ('List.Min', 'type number'),
    'max':     ('List.Max', 'type number'),
    'median':  ('List.Median', 'type number'),
    'stdev':   ('List.StandardDeviation', 'type number'),
    'var':     (None, 'type number'),   # special: List.StandardDeviation² (sample variance)
    'varp':    (None, 'type number'),   # special: population variance via custom formula
}


def m_transform_aggregate(group_by_columns, aggregations):
    """
    Aggregate / Group By.
    Args:
        group_by_columns: list of column names to group by
        aggregations: list of dicts [{"name": "Total", "column": "Sales", "agg": "sum"}, ...]
    """
    group_cols = ', '.join([f'"{c}"' for c in group_by_columns])
    agg_parts = []
    for a in aggregations:
        name = a['name']
        col = a['column']
        agg = a['agg'].lower()
        if agg == 'count':
            agg_parts.append(f'{{"{name}", each Table.RowCount(_), Int64.Type}}')
        elif agg == 'countd':
            agg_parts.append(f'{{"{name}", each List.Count(List.Distinct([{col}])), Int64.Type}}')
        elif agg == 'var':
            # Sample variance = StdDev² (M has no built-in List.Variance)
            agg_parts.append(f'{{"{name}", each Number.Power(List.StandardDeviation([{col}]), 2), type number}}')
        elif agg == 'varp':
            # Population variance = avg((x - mean)²)
            agg_parts.append(
                f'{{"{name}", each '
                f'List.Average(List.Transform([{col}], (x) => Number.Power(x - List.Average([{col}]), 2))), '
                f'type number}}'
            )
        else:
            mapping = _M_AGG_MAP.get(agg, ('List.Sum', 'type number'))
            func, m_type = mapping
            agg_parts.append(f'{{"{name}", each {func}([{col}]), {m_type}}}')

    aggs = ', '.join(agg_parts)
    return ('#"Grouped Rows"', f'Table.Group({{prev}}, {{{group_cols}}}, {{{aggs}}})')


# ── Pivot / Unpivot operations ────────────────────────────────────────────────

def m_transform_unpivot(columns, attribute_name="Attribute", value_name="Value"):
    """Unpivot specific columns (columns become rows). Tableau Prep: Pivot Columns to Rows."""
    cols = ', '.join([f'"{c}"' for c in columns])
    return ('#"Unpivoted Columns"',
            f'Table.Unpivot({{prev}}, {{{cols}}}, "{attribute_name}", "{value_name}")')


def m_transform_unpivot_other(keep_columns, attribute_name="Attribute", value_name="Value"):
    """Unpivot all columns except specified ones."""
    cols = ', '.join([f'"{c}"' for c in keep_columns])
    return ('#"Unpivoted Other Columns"',
            f'Table.UnpivotOtherColumns({{prev}}, {{{cols}}}, "{attribute_name}", "{value_name}")')


def m_transform_pivot(pivot_column, value_column, agg_function="List.Sum"):
    """Pivot rows to columns. Tableau Prep: Pivot Rows to Columns."""
    return ('#"Pivoted Column"',
            f'Table.Pivot({{prev}}, List.Distinct({{prev}}[{pivot_column}]), '
            f'"{pivot_column}", "{value_column}", {agg_function})')


# ── Join operations ───────────────────────────────────────────────────────────

_M_JOIN_KIND = {
    'inner':      'JoinKind.Inner',
    'left':       'JoinKind.LeftOuter',
    'leftouter':  'JoinKind.LeftOuter',
    'right':      'JoinKind.RightOuter',
    'rightouter': 'JoinKind.RightOuter',
    'full':       'JoinKind.FullOuter',
    'fullouter':  'JoinKind.FullOuter',
    'leftanti':   'JoinKind.LeftAnti',
    'rightanti':  'JoinKind.RightAnti',
}


def m_transform_buffer(table_ref=None):
    """Buffer a table to force query-folding boundary.

    Wrapping a table reference in Table.Buffer() forces the engine to
    materialise the table before the next step.  This is useful before
    joins to prevent the engine from sending un-foldable join predicates
    to the data source.

    Args:
        table_ref: Optional M table reference to buffer.  When *None*,
                   the ``{prev}`` placeholder is used so the step can be
                   chained via ``inject_m_steps()``.
    Returns:
        (step_name, step_expression) tuple.
    """
    ref = table_ref or '{prev}'
    return ('#"Buffered Table"', f'Table.Buffer({ref})')


def m_transform_join(right_table_ref, left_keys, right_keys, join_type='left',
                     expand_columns=None, joined_name="Joined",
                     buffer_right=False):
    """
    Join two tables.
    Args:
        right_table_ref: str — M reference to the right table
        left_keys / right_keys: list of str — key columns
        join_type: str — inner, left, right, full, leftanti, rightanti
        expand_columns: list of str — columns to expand (None = no expansion step)
        joined_name: str — name of the joined nested column
        buffer_right: bool — when True, wrap right_table_ref in Table.Buffer()
                      to create a query-folding boundary (prevents the engine from
                      sending un-foldable join predicates to the data source)
    Returns:
        list of (step_name, step_expression) tuples (join + optional expand)
    """
    kind = _M_JOIN_KIND.get(join_type.lower().replace(' ', ''), 'JoinKind.LeftOuter')
    if len(left_keys) == 1:
        lk, rk = f'"{left_keys[0]}"', f'"{right_keys[0]}"'
    else:
        lk = '{' + ', '.join([f'"{k}"' for k in left_keys]) + '}'
        rk = '{' + ', '.join([f'"{k}"' for k in right_keys]) + '}'

    effective_right = f'Table.Buffer({right_table_ref})' if buffer_right else right_table_ref

    steps = [(f'#"Joined {joined_name}"',
              f'Table.NestedJoin({{prev}}, {lk}, {effective_right}, {rk}, '
              f'"{joined_name}", {kind})')]
    if expand_columns:
        cols = ', '.join([f'"{c}"' for c in expand_columns])
        steps.append((f'#"Expanded {joined_name}"',
                       f'Table.ExpandTableColumn({{prev}}, "{joined_name}", {{{cols}}})'))
    return steps


# ── Union operations ──────────────────────────────────────────────────────────

def m_transform_union(table_refs):
    """Union (append) multiple tables. table_refs: list of M table references."""
    refs = ', '.join(table_refs)
    return ('#"Combined Tables"', f'Table.Combine({{{refs}}})')


def m_transform_wildcard_union(folder_path, file_extension=".csv", delimiter=","):
    """Union all matching files in a folder (Wildcard Union). Returns a complete M query."""
    folder_bs = folder_path.replace('/', '\\')
    return f'''let
    // Wildcard Union: all {file_extension} files in folder
    Source = Folder.Files("{folder_bs}"),
    #"Filtered Files" = Table.SelectRows(Source, each Text.EndsWith([Name], "{file_extension}")),
    #"Added Tables" = Table.AddColumn(#"Filtered Files", "ParsedTable",
        each Csv.Document([Content], [Delimiter="{delimiter}", Encoding=65001])),
    #"Combined" = Table.Combine(#"Added Tables"[ParsedTable]),
    #"Promoted Headers" = Table.PromoteHeaders(#"Combined", [PromoteAllScalars=true])
in
    #"Promoted Headers"'''


# ── Reshape operations ────────────────────────────────────────────────────────

def m_transform_sort(sort_specs):
    """Sort rows. sort_specs: list of (column, descending_bool) tuples."""
    sorts = ', '.join([
        f'{{"{col}", {"Order.Descending" if desc else "Order.Ascending"}}}'
        for col, desc in sort_specs
    ])
    return ('#"Sorted Rows"', f'Table.Sort({{prev}}, {{{sorts}}})')


def m_transform_transpose():
    """Transpose table (rows ↔ columns)."""
    return ('#"Transposed Table"', 'Table.Transpose({prev})')


def m_transform_add_index(column_name="Index", start=1, increment=1):
    """Add an index column."""
    return ('#"Added Index"',
            f'Table.AddIndexColumn({{prev}}, "{column_name}", {start}, {increment})')


def m_transform_skip_rows(n):
    """Remove first N rows."""
    return ('#"Skipped Rows"', f'Table.Skip({{prev}}, {n})')


def m_transform_remove_last_rows(n):
    """Remove last N rows."""
    return ('#"Removed Last Rows"', f'Table.RemoveLastN({{prev}}, {n})')


def m_transform_promote_headers():
    """Promote first row to headers."""
    return ('#"Promoted Headers"',
            'Table.PromoteHeaders({prev}, [PromoteAllScalars=true])')


def m_transform_demote_headers():
    """Demote headers to first row."""
    return ('#"Demoted Headers"', 'Table.DemoteHeaders({prev})')


# ── Calculated column ─────────────────────────────────────────────────────────

def m_transform_add_column(new_col_name, expression, col_type=None):
    """
    Add a calculated column.
    Args:
        new_col_name: str
        expression: str — M expression (e.g., 'each [Price] * [Qty]')
        col_type: str — optional M type (e.g., 'type number')
    """
    type_arg = f', {col_type}' if col_type else ''
    return (f'#"Added {new_col_name}"',
            f'Table.AddColumn({{prev}}, "{new_col_name}", {expression}{type_arg})')


def m_transform_conditional_column(new_col_name, conditions, default_value=None):
    """
    Add a conditional (IF/THEN/ELSE) column.
    Args:
        new_col_name: str
        conditions: list of (condition_expr, result_value) — e.g., [('[Sales] > 1000', '"High"')]
        default_value: str — default if no condition matches
    """
    expr = ""
    for cond, val in conditions:
        # Strip spurious 'each' prefix — each belongs in Table.AddColumn, not in conditions
        clean_cond = cond
        if clean_cond.startswith('each '):
            clean_cond = clean_cond[5:]
        expr += f'if {clean_cond} then {val} else '
    expr += str(default_value) if default_value is not None else 'null'
    return (f'#"Added {new_col_name}"',
            f'Table.AddColumn({{prev}}, "{new_col_name}", each {expr})')


# ── Error handling transforms ─────────────────────────────────────────────────

def m_transform_remove_errors(columns=None):
    """
    Remove rows containing errors.
    Args:
        columns: optional list of column names to check for errors.
                 If None, removes errors across all columns.
    """
    if columns:
        cols = ', '.join([f'"{c}"' for c in columns])
        return ('#"Removed Errors"',
                f'Table.RemoveRowsWithErrors({{prev}}, {{{cols}}})')
    return ('#"Removed Errors"', 'Table.RemoveRowsWithErrors({prev})')


def m_transform_replace_errors(columns, replacement=None):
    """
    Replace error values in specified columns with a replacement value.
    Args:
        columns: list of column names to process
        replacement: replacement value (default: null)
    """
    repl = str(replacement) if replacement is not None else 'null'
    transforms = ', '.join([f'{{"{c}", each {repl}}}' for c in columns])
    return ('#"Replaced Errors"',
            f'Table.ReplaceErrorValues({{prev}}, {{{transforms}}})')


# ── Regex → M fallback transforms ─────────────────────────────────────────────

def m_regex_match(column, pattern):
    """Generate M step for regex match (returns boolean column).

    Uses ``Text.RegexMatch`` available in Power Query (December 2024+).
    Falls back to a ``Text.Contains`` approximation comment for older engines.
    """
    safe_col = f'[{column}]' if not column.startswith('[') else column
    return (f'#"Regex Match {column}"',
            f'Table.AddColumn({{prev}}, "{column}_match", '
            f'each try Text.RegexMatch({safe_col}, "{pattern}") otherwise false, type logical)')


def m_regex_extract(column, pattern, new_column=None):
    """Generate M step for regex extract (captures first group).

    Uses ``Text.RegexExtract`` to pull the first capture group from *pattern*.
    """
    safe_col = f'[{column}]' if not column.startswith('[') else column
    out_col = new_column or f'{column}_extract'
    return (f'#"Regex Extract {column}"',
            f'Table.AddColumn({{prev}}, "{out_col}", '
            f'each try Text.RegexExtract({safe_col}, "{pattern}") otherwise null, type text)')


def m_regex_replace(column, pattern, replacement):
    """Generate M step for regex replace.

    Uses ``Text.RegexReplace`` to substitute all matches of *pattern*.
    """
    safe_col = f'[{column}]' if not column.startswith('[') else column
    return (f'#"Regex Replace {column}"',
            f'Table.TransformColumns({{prev}}, {{{{"{column}", '
            f'each try Text.RegexReplace({safe_col}, "{pattern}", "{replacement}") otherwise {safe_col}}}}})')


def convert_tableau_regex_to_m(formula, column_name):
    """Convert a Tableau REGEXP_* formula to a Power Query M step tuple.

    Recognises REGEXP_MATCH, REGEXP_EXTRACT, REGEXP_EXTRACT_NTH, and
    REGEXP_REPLACE.  Returns a ``(step_name, step_expression)`` tuple that
    can be injected via ``inject_m_steps()``, or *None* if the formula does
    not contain a recognised REGEXP function.
    """
    import re as _re

    # REGEXP_MATCH(field, "pattern")
    m = _re.search(r'REGEXP_MATCH\s*\(\s*\[?([^\],]+?)\]?\s*,\s*["\'](.+?)["\']\s*\)', formula, _re.IGNORECASE)
    if m:
        return m_regex_match(m.group(1).strip(), m.group(2))

    # REGEXP_EXTRACT(field, "pattern")
    m = _re.search(r'REGEXP_EXTRACT\s*\(\s*\[?([^\],]+?)\]?\s*,\s*["\'](.+?)["\']\s*\)', formula, _re.IGNORECASE)
    if m:
        return m_regex_extract(m.group(1).strip(), m.group(2), new_column=column_name)

    # REGEXP_EXTRACT_NTH(field, "pattern", n)
    m = _re.search(r'REGEXP_EXTRACT_NTH\s*\(\s*\[?([^\],]+?)\]?\s*,\s*["\'](.+?)["\']\s*,\s*(\d+)\s*\)',
                    formula, _re.IGNORECASE)
    if m:
        pat_with_group = m.group(2)
        return m_regex_extract(m.group(1).strip(), pat_with_group,
                               new_column=column_name)

    # REGEXP_REPLACE(field, "pattern", "replacement")
    m = _re.search(r'REGEXP_REPLACE\s*\(\s*\[?([^\],]+?)\]?\s*,\s*["\'](.+?)["\']\s*,\s*["\'](.*)["\']\s*\)',
                    formula, _re.IGNORECASE)
    if m:
        return m_regex_replace(m.group(1).strip(), m.group(2), m.group(3))

    return None


def m_transform_try_otherwise(step_name, expression, fallback_expression):
    """
    Wrap a step expression in a try...otherwise block for graceful error handling.
    Args:
        step_name: the step name (e.g., '#"Connected Source"')
        expression: the primary M expression to attempt
        fallback_expression: the expression to use if the primary fails
    Returns:
        (step_name, wrapped_expression) tuple
    """
    return (step_name, f'try {expression} otherwise {fallback_expression}')


def wrap_source_with_try_otherwise(m_query, empty_table_columns=None):
    """
    Wrap the Source step of an M query with try...otherwise for graceful error handling.

    If the data source is unavailable, returns an empty table with the expected schema
    instead of failing with an error.

    When the step immediately after Source is a key-based navigation on Source
    (e.g. ``Source{[Item="Sheet1",Kind="Sheet"]}[Data]``), the navigation step is
    absorbed into the try block so the fallback replaces the full chain.

    Args:
        m_query: str — Complete M query (let ... in ...)
        empty_table_columns: optional list of column name strings for the fallback table
    Returns:
        str — Modified M query with Source wrapped in try...otherwise
    """
    import re as _re

    # Find "Source = ..." line
    match = _re.search(r'(\n\s*)(Source\s*=\s*)', m_query)
    if not match:
        return m_query

    indent = match.group(1)
    source_assign = match.group(2)
    after_assign = m_query[match.end():]

    # Skip if Source is already wrapped with try...otherwise
    if after_assign.strip().startswith('try'):
        return m_query

    # Find the end of the Source expression (next line starting with a step name or 'in')
    lines = after_assign.split('\n')
    # Find how many lines belong to the Source expression
    # Track nesting depth to avoid matching option keys inside [...] or (...)
    source_lines = []
    remaining_idx = len(lines)
    nesting = 0
    for idx, line in enumerate(lines):
        stripped = line.strip()
        # Update nesting based on brackets/parens in this line
        for ch in line:
            if ch in ('(', '['):
                nesting += 1
            elif ch in (')', ']'):
                nesting -= 1
        if idx > 0 and nesting <= 0 and (stripped.startswith('#"') or stripped.startswith('Result')
                        or stripped == 'in' or _re.match(r'\w+\s*=', stripped)):
            remaining_idx = idx
            break
        source_lines.append(line)

    source_expr = '\n'.join(source_lines).rstrip().rstrip(',')
    consumed_lines = len(source_lines)

    # Check if the NEXT step is a key-based navigation on Source.
    # Pattern: <step_name> = Source{[...]}[Data],
    # If so, absorb it into the try block so the fallback replaces both.
    nav_step_name = None
    if remaining_idx < len(lines):
        next_stripped = lines[remaining_idx].strip()
        nav_match = _re.match(
            r'(#"[^"]+"|[\w]+)\s*=\s*Source\s*\{',
            next_stripped,
        )
        if nav_match:
            nav_step_name = nav_match.group(1)
            # Find boundaries of the navigation step (it might span multiple lines)
            nav_lines = []
            nav_nesting = 0
            for nav_idx in range(remaining_idx, len(lines)):
                for ch in lines[nav_idx]:
                    if ch in ('(', '[', '{'):
                        nav_nesting += 1
                    elif ch in (')', ']', '}'):
                        nav_nesting -= 1
                nav_lines.append(lines[nav_idx])
                if nav_nesting <= 0:
                    break

            nav_expr = '\n'.join(nav_lines).rstrip().rstrip(',')
            # Combine Source + navigation into a single let...in expression
            # so the try wraps the full chain
            source_expr = (
                f'let\n'
                f'{indent}        _src = {source_expr.strip()},\n'
                f'{indent}        _nav = _src' +
                nav_expr[nav_expr.index('Source') + len('Source'):].strip() +
                f'\n{indent}    in _nav'
            )
            consumed_lines += len(nav_lines)
            remaining_idx += len(nav_lines)

    remaining_start = len('\n'.join(lines[:consumed_lines]))

    # Build fallback table
    if empty_table_columns:
        col_list = ', '.join([f'"{c}"' for c in empty_table_columns])
        fallback = f'#table({{{col_list}}}, {{}})'
    else:
        fallback = '#table({}, {})'

    # Check if there are more steps after Source (before 'in')
    has_more_steps = remaining_idx < len(lines) and lines[remaining_idx].strip() != 'in'
    trailing = ',' if has_more_steps else ''

    # When we absorbed a navigation step, downstream steps reference nav_step_name
    # instead of Source. Replace those references with Source.
    after_text = after_assign[remaining_start:]
    if nav_step_name:
        # Replace step references like #"Sheet1 Sheet" or TableName with Source
        after_text = after_text.replace(nav_step_name, 'Source')

    # Wrap with try...otherwise
    new_source = f'{indent}{source_assign}try\n{indent}    {source_expr.strip()}\n{indent}otherwise\n{indent}    {fallback}{trailing}'

    return m_query[:match.start()] + new_source + after_text


# ── Hyper data integration ────────────────────────────────────────────────────


def generate_m_from_hyper(hyper_tables, table_name=None):
    """Generate an M query using data from ``hyper_reader``.

    If the datasource has ``hyper_reader_tables`` (populated by
    ``extract_hyper_metadata``), this function produces an M expression
    with inline sample data or a CSV reference.

    Args:
        hyper_tables: list of table dicts from ``hyper_reader.read_hyper()``.
        table_name: Optional table name to match. If ``None``, uses the first.

    Returns:
        str | None: M expression, or ``None`` if no suitable data found.
    """
    if not hyper_tables:
        return None

    try:
        from hyper_reader import generate_m_for_hyper_table
    except ImportError:
        return None

    # Find matching table
    target = None
    for t in hyper_tables:
        if table_name and t.get('table', '').lower() == table_name.lower():
            target = t
            break
    if target is None:
        target = hyper_tables[0]

    if not target.get('columns'):
        return None

    return generate_m_for_hyper_table(target)


# ── Sprint 61: New Transform Generators ───────────────────────────────────────

def gen_extract_regex(column, pattern, group=0):
    """Regex extraction transform.

    Returns:
        Tuple (step_name, step_expression) with ``{prev}`` placeholder.
    """
    step_name = f'Regex_{column}'
    expr = (
        f'Table.TransformColumns({{prev}}, '
        f'{{{{"{column}", each try Text.RegexExtract(_, "{pattern}", {group}) otherwise null}}}}'
        f')'
    )
    return (step_name, expr)


def gen_parse_json(column):
    """JSON parsing + record expansion transform.

    Returns:
        Tuple (step_name, step_expression) with ``{prev}`` placeholder.
    """
    step_name = f'ParseJSON_{column}'
    expr = (
        f'Table.TransformColumns({{prev}}, '
        f'{{{{"{column}", Json.Document}}}}'
        f')'
    )
    return (step_name, expr)


def gen_parse_xml(column):
    """XML parsing transform.

    Returns:
        Tuple (step_name, step_expression) with ``{prev}`` placeholder.
    """
    step_name = f'ParseXML_{column}'
    expr = (
        f'Table.TransformColumns({{prev}}, '
        f'{{{{"{column}", Xml.Tables}}}}'
        f')'
    )
    return (step_name, expr)


def parameterize_connection(m_expression, param_map=None):
    """Replace hardcoded connection values with Power Query parameter references.

    Args:
        m_expression: Complete M query string.
        param_map: Dict mapping placeholder names to PBI parameter names,
            e.g. ``{"ServerName": "P_Server", "DatabaseName": "P_Database"}``.

    Returns:
        Modified M expression with parameter references.
    """
    if not param_map:
        return m_expression

    result = m_expression
    for placeholder, pq_param in param_map.items():
        # Replace quoted values with parameter references
        result = result.replace(f'"{placeholder}"', f'#"{pq_param}"')
    return result


def generate_connection_parameters(connection_map):
    """Generate Power Query parameter M expressions for multi-connection workbooks.

    When a workbook connects to multiple databases, each unique connection
    gets its own server/database parameters to allow independent configuration.

    Args:
        connection_map: Dict of connection_name -> connection_details
            from datasource_extractor.

    Returns:
        list of dicts with ``name`` and ``m_expression`` for PBI parameters.
    """
    params = []
    seen_servers = {}  # (server, database) -> param_prefix
    idx = 0

    for conn_name, conn in connection_map.items():
        details = conn.get('details', {})
        server = details.get('server', '')
        database = details.get('database', '')
        if not server:
            continue

        key = (server, database)
        if key in seen_servers:
            continue  # Same connection already parameterized

        idx += 1
        prefix = f"Conn{idx}" if idx > 1 else ""
        seen_servers[key] = prefix

        # Server parameter
        params.append({
            'name': f'{prefix}ServerName' if prefix else 'ServerName',
            'm_expression': f'"{server}" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]',
        })
        # Database parameter (if applicable)
        if database:
            params.append({
                'name': f'{prefix}DatabaseName' if prefix else 'DatabaseName',
                'm_expression': f'"{database}" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]',
            })

    return params


def generate_blend_merge_query(primary_query_name, secondary_query_name,
                                link_columns, join_kind='left'):
    """Generate a Power Query M merge step that blends two datasource queries.

    Simulates Tableau data blending by creating a Table.NestedJoin that links
    a primary query to a secondary query on the specified columns, then expands
    the secondary columns.

    Args:
        primary_query_name: Name of the primary M query (e.g. 'Orders')
        secondary_query_name: Name of the secondary M query (e.g. 'Returns')
        link_columns: List of dicts with 'primary' and 'secondary' column names
        join_kind: Join type — 'left' (default, matches Tableau blend), 'inner', 'full'

    Returns:
        str: Complete M query for the blended/merged result
    """
    if not link_columns:
        # No link columns — just combine (append)
        return (
            f'let\n'
            f'    Primary = {primary_query_name},\n'
            f'    Secondary = {secondary_query_name},\n'
            f'    Combined = Table.Combine({{Primary, Secondary}})\n'
            f'in\n'
            f'    Combined'
        )
    
    primary_keys = [lc.get('primary', lc.get('column', '')) for lc in link_columns]
    secondary_keys = [lc.get('secondary', lc.get('column', '')) for lc in link_columns]
    
    pk_list = ', '.join(f'"{k}"' for k in primary_keys)
    sk_list = ', '.join(f'"{k}"' for k in secondary_keys)
    
    kind_map = {
        'left': 'JoinKind.LeftOuter',
        'inner': 'JoinKind.Inner',
        'full': 'JoinKind.FullOuter',
        'right': 'JoinKind.RightOuter',
        'leftanti': 'JoinKind.LeftAnti',
    }
    m_join_kind = kind_map.get(join_kind, 'JoinKind.LeftOuter')
    
    return (
        f'let\n'
        f'    Primary = {primary_query_name},\n'
        f'    Secondary = {secondary_query_name},\n'
        f'    Merged = Table.NestedJoin(\n'
        f'        Primary, {{{pk_list}}},\n'
        f'        Secondary, {{{sk_list}}},\n'
        f'        "Blended", {m_join_kind}\n'
        f'    ),\n'
        f'    Expanded = Table.ExpandTableColumn(\n'
        f'        Merged, "Blended",\n'
        f'        Table.ColumnNames(Secondary)\n'
        f'    )\n'
        f'in\n'
        f'    Expanded'
    )


def generate_table_extension_query(extension):
    """Generate a Power Query M query for a Tableau table extension.

    Converts Tableau 2024.2+ table extensions (Einstein Discovery, external API)
    to Web.Contents() M queries or placeholder queries with migration notes.

    Args:
        extension: Dict from extract_table_extensions with name, extension_type,
                   endpoint, schema, config.

    Returns:
        str: M query string
    """
    name = extension.get('name', 'Extension')
    endpoint = extension.get('endpoint', '')
    ext_type = extension.get('extension_type', 'unknown')
    schema = extension.get('schema', [])

    if endpoint:
        # Generate Web.Contents query for API-based extensions
        col_types = []
        for col in schema:
            dt = col.get('datatype', 'string')
            m_type = {'integer': 'Int64.Type', 'real': 'Number.Type',
                      'boolean': 'Logical.Type', 'date': 'Date.Type',
                      'datetime': 'DateTime.Type'}.get(dt, 'Text.Type')
            col_types.append(f'{{"{col["name"]}", {m_type}}}')

        type_list = ', '.join(col_types) if col_types else ''
        lines = [
            'let',
            f'    // Table Extension: {name} (type: {ext_type})',
            f'    Source = Json.Document(Web.Contents("{endpoint}")),',
            '    AsTable = Table.FromRecords(Source)',
        ]
        if type_list:
            lines.append(f'    ,Typed = Table.TransformColumnTypes(AsTable, {{{type_list}}})')
            lines.append('in')
            lines.append('    Typed')
        else:
            lines.append('in')
            lines.append('    AsTable')
        return '\n'.join(lines)
    else:
        # Placeholder for extensions without a direct endpoint
        cols = [f'"{c["name"]}"' for c in schema] if schema else ['"Value"']
        return (
            f'let\n'
            f'    // MigrationNote: Tableau table extension "{name}" (type: {ext_type})\n'
            f'    // requires manual configuration — no direct endpoint available.\n'
            f'    Source = #table({{{", ".join(cols)}}}, {{}})\n'
            f'in\n'
            f'    Source'
        )

