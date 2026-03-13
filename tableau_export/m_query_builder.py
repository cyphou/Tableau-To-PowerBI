"""
Power Query M Query Builder — Generates M queries from Tableau connections.

Extracted from datasource_extractor.py for maintainability.
Each connector type has its own generator function dispatched via _M_GENERATORS.
"""


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
    return _M_TYPE_MAP.get(datatype.lower(), 'type text')


def _m_escape_col_name(name):
    """Escape column names for M queries (double-quote any internal quotes)."""
    return name.replace('"', '""')


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
    filename = details.get('filename') or (table_name + '.xlsx')
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
    m_query = 'let\n'
    m_query += f'    // Source {comment}\n'
    m_query += f'    Source = {pq_func}("{server_arg}", "{db_arg}"),\n'
    m_query += f'    {safe} = Source{{[Schema="{schema}", Item="{table_name}"]}}[Data],\n'
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
    filename = details.get('filename') or (table_name + '.csv')
    directory = details.get('directory', '')
    full_path = f"{directory}/{filename}" if directory else filename
    delimiter = details.get('delimiter', ',')
    encoding = details.get('encoding', 'utf-8').upper()
    encoding_code = {'UTF-8': '65001', 'UTF8': '65001'}.get(encoding, '65001')
    file_path_bs = full_path.replace('/', '\\')

    m_query = f'''let
    // Source CSV: {full_path}
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
    server = details.get('server', 'localhost')
    service = details.get('service', 'ORCL')
    port = details.get('port', '1521')
    safe = '#"' + table_name + ' Table"'

    m_query = 'let\n'
    m_query += f'    // Source Oracle: {server}:{port}/{service}\n'
    m_query += f'    Source = Oracle.Database("{server}:{port}/{service}"),\n'
    m_query += f'    {safe} = Source{{[Schema="DBO", Item="{table_name}"]}}[Data],\n'
    m_query += f'    Result = {safe}\nin\n    Result'
    return m_query


def _gen_m_snowflake(details, table_name, columns):
    server = details.get('server', 'account.snowflakecomputing.com')
    database = details.get('database', 'MY_DB')
    warehouse = details.get('warehouse', 'MY_WH')
    schema = details.get('schema', 'PUBLIC')
    safe = '#"' + table_name + ' Table"'

    m_query = 'let\n'
    m_query += f'    // Source Snowflake: {server}\n'
    m_query += f'    Source = Snowflake.Databases("{server}", "{warehouse}"),\n'
    m_query += f'    #"{database}" = Source{{[Name="{database}"]}}[Data],\n'
    m_query += f'    #"{schema}" = #"{database}"{{[Name="{schema}"]}}[Data],\n'
    m_query += f'    {safe} = #"{schema}"{{[Name="{table_name}"]}}[Data],\n'
    m_query += f'    Result = {safe}\nin\n    Result'
    return m_query


def _gen_m_geojson(details, table_name, columns):
    filename = details.get('filename', 'file.geojson')
    directory = details.get('directory', '')
    full_path = f"{directory}/{filename}" if directory else filename
    full_path_bs = full_path.replace('/', '\\')

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
    Source = Json.Document(File.Contents(DataFolder & "\\{full_path_bs}")),
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
    filename = details.get('filename', table_name + '.json')
    directory = details.get('directory', '')
    full_path = f"{directory}/{filename}" if directory else filename
    full_path_bs = full_path.replace('/', '\\')

    m_query = 'let\n'
    m_query += f'    // Source JSON: {filename}\n'
    m_query += f'    Source = Json.Document(File.Contents(DataFolder & "\\{full_path_bs}")),\n'
    m_query += '    #"Converted to Table" = if Value.Is(Source, type list) then Table.FromRecords(Source) else Table.FromRecords({Source}),\n'
    m_query += '    #"Promoted Headers" = #"Converted to Table",\n'
    return _append_type_step(m_query, columns)


def _gen_m_xml(details, table_name, columns):
    filename = details.get('filename', table_name + '.xml')
    directory = details.get('directory', '')
    full_path = f"{directory}/{filename}" if directory else filename
    full_path_bs = full_path.replace('/', '\\')

    m_query = 'let\n'
    m_query += f'    // Source XML: {filename}\n'
    m_query += f'    Source = Xml.Tables(File.Contents(DataFolder & "\\{full_path_bs}")),\n'
    m_query += '    #"Promoted Headers" = Source,\n'
    return _append_type_step(m_query, columns)


def _gen_m_pdf(details, table_name, columns):
    filename = details.get('filename', table_name + '.pdf')
    directory = details.get('directory', '')
    full_path = f"{directory}/{filename}" if directory else filename
    full_path_bs = full_path.replace('/', '\\')

    m_query = 'let\n'
    m_query += f'    // Source PDF: {filename}\n'
    m_query += f'    Source = Pdf.Tables(File.Contents(DataFolder & "\\{full_path_bs}")),\n'
    m_query += '    Table1 = Source{{0}}[Data],\n'
    m_query += '    #"Promoted Headers" = Table.PromoteHeaders(Table1, [PromoteAllScalars=true]),\n'
    return _append_type_step(m_query, columns)


def _gen_m_salesforce(details, table_name, columns):
    safe = '#"' + table_name + ' Table"'

    m_query = 'let\n'
    m_query += '    // Source Salesforce\n'
    m_query += '    Source = Salesforce.Data(),\n'
    m_query += f'    {safe} = Source{{[Name="{table_name}"]}}[Data],\n'
    m_query += f'    Result = {safe}\nin\n    Result'
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
    server = details.get('server', 'localhost')
    database = details.get('database', 'MyDatabase')
    sql_query = details.get('sql_query', f'SELECT * FROM {table_name}')
    params = details.get('params', {})  # {name: default_value}
    # Escape quotes in SQL for M string
    sql_escaped = sql_query.replace('"', '""')

    m_query = 'let\n'
    m_query += '    // Source: Custom SQL Query\n'
    if params:
        # Build parameter record:  [Param1="value1", Param2="value2"]
        param_items = ', '.join(f'{k}="{v}"' for k, v in params.items())
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
    server = details.get('server', 'vertica-server')
    database = details.get('database', 'MyDatabase')
    schema = details.get('schema', 'public')
    m_query = 'let\n'
    m_query += f'    // Source Vertica: {server}/{database}\n'
    m_query += f'    Source = Odbc.DataSource("DSN=Vertica;Server={server};Database={database}"),\n'
    m_query += f'    SchemaTable = Source{{[Schema="{schema}",Item="{table_name}"]}}[Data],\n'
    m_query += '    #"Promoted Headers" = SchemaTable,\n'
    return _append_type_step(m_query, columns)


def _gen_m_impala(details, table_name, columns):
    """Generate M query for Apache Impala."""
    server = details.get('server', 'impala-server')
    port = details.get('port', '21050')
    m_query = 'let\n'
    m_query += f'    // Source Impala: {server}:{port}\n'
    m_query += f'    Source = Odbc.DataSource("Driver={{Cloudera ODBC Driver for Impala}};Host={server};Port={port}"),\n'
    m_query += f'    Table = Source{{[Name="{table_name}"]}}[Data],\n'
    m_query += '    #"Promoted Headers" = Table,\n'
    return _append_type_step(m_query, columns)


def _gen_m_hadoop_hive(details, table_name, columns):
    """Generate M query for Hadoop Hive / HDInsight."""
    server = details.get('server', 'hive-server')
    port = details.get('port', '443')
    m_query = 'let\n'
    m_query += f'    // Source Hadoop Hive: {server}:{port}\n'
    m_query += f'    Source = Odbc.DataSource("Driver={{Microsoft Hive ODBC Driver}};Host={server};Port={port}"),\n'
    m_query += f'    Table = Source{{[Name="{table_name}"]}}[Data],\n'
    m_query += '    #"Promoted Headers" = Table,\n'
    return _append_type_step(m_query, columns)


def _gen_m_presto(details, table_name, columns):
    """Generate M query for Presto / Trino (via ODBC)."""
    server = details.get('server', 'presto-server')
    catalog = details.get('database', details.get('catalog', 'hive'))
    schema = details.get('schema', 'default')
    m_query = 'let\n'
    m_query += f'    // Source Presto/Trino: {server}/{catalog}.{schema}\n'
    m_query += f'    Source = Odbc.DataSource("Driver={{Starburst Presto ODBC Driver}};Host={server};Catalog={catalog};Schema={schema}"),\n'
    m_query += f'    Table = Source{{[Name="{table_name}"]}}[Data],\n'
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
        from hyper_reader import read_hyper, generate_m_for_hyper_table
        filename = details.get('filename', '')
        if filename and os.path.isfile(filename):
            result = read_hyper(filename, max_rows=20)
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
                return generate_m_for_hyper_table(target)
    except Exception:
        pass

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

    # Build the chain — replace {prev} with actual previous step name
    prev_step = last_step
    new_lines = []
    for step_name, step_expr_template in steps:
        step_expr = step_expr_template.replace('{prev}', prev_step)
        new_lines.append(f'    {step_name} = {step_expr},')
        prev_step = step_name

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
    new_repr = f'"{new_value}"' if isinstance(new_value, str) else str(new_value)
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


def m_transform_remove_errors():
    """Remove rows with errors."""
    return ('#"Removed Errors"', 'Table.RemoveRowsWithErrors({prev})')


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
        expr += f'if {cond} then {val} else '
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
    source_lines = []
    remaining_idx = len(lines)
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if idx > 0 and (stripped.startswith('#"') or stripped.startswith('Result')
                        or stripped == 'in' or _re.match(r'\w+\s*=', stripped)):
            remaining_idx = idx
            break
        source_lines.append(line)

    source_expr = '\n'.join(source_lines).rstrip().rstrip(',')
    remaining_start = len('\n'.join(source_lines))

    # Build fallback table
    if empty_table_columns:
        col_list = ', '.join([f'"{c}"' for c in empty_table_columns])
        fallback = f'#table({{{col_list}}}, {{}})'
    else:
        fallback = '#table({}, {})'

    # Check if there are more steps after Source (before 'in')
    has_more_steps = remaining_idx < len(lines) and lines[remaining_idx].strip() != 'in'
    trailing = ',' if has_more_steps else ''

    # Wrap with try...otherwise
    new_source = f'{indent}{source_assign}try\n{indent}    {source_expr.strip()}\n{indent}otherwise\n{indent}    {fallback}{trailing}'

    return m_query[:match.start()] + new_source + after_assign[remaining_start:]


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
