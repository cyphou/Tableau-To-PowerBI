"""
Datasource extraction module for Tableau workbooks.

Parses Tableau XML datasource elements, extracting connections,
tables, columns, calculations, and relationships.
Re-exports DAX converter and M query builder functions for backward compatibility.
"""

import xml.etree.ElementTree as ET
import zipfile
import os
import csv
import re
import logging
from dax_converter import _reverse_tableau_bracket_escape

logger = logging.getLogger(__name__)

def _detect_csv_delimiter(header_line):
    """Detects the CSV delimiter from the first line (header).
    
    Uses csv.Sniffer if possible, otherwise heuristic by counting.
    Returns the detected delimiter (',' or ';' or '\t' etc.)
    """
    if not header_line:
        return ','
    
    # Try csv.Sniffer first
    try:
        dialect = csv.Sniffer().sniff(header_line, delimiters=',;\t|')
        return dialect.delimiter
    except csv.Error:
        pass
    
    # Heuristic: count occurrences of common delimiters
    candidates = [(',', header_line.count(',')),
                  (';', header_line.count(';')),
                  ('\t', header_line.count('\t')),
                  ('|', header_line.count('|'))]
    # Sort by descending occurrence count
    candidates.sort(key=lambda x: x[1], reverse=True)
    if candidates[0][1] > 0:
        return candidates[0][0]
    return ','


def _read_csv_header_from_twbx(twbx_path, directory, filename):
    """Reads the first line of a CSV file embedded in a .twbx.
    
    Returns the first line (header) or None if not found.
    """
    if not twbx_path or not os.path.exists(twbx_path):
        return None
    ext = os.path.splitext(twbx_path)[1].lower()
    if ext not in ('.twbx', '.tdsx'):
        return None
    
    # Build the expected path inside the archive
    if directory:
        csv_path = directory.rstrip('/') + '/' + filename
    else:
        csv_path = filename
    
    try:
        with zipfile.ZipFile(twbx_path, 'r') as z:
            # Search for the file (exact or partial match)
            for name in z.namelist():
                if name == csv_path or name.endswith('/' + filename):
                    with z.open(name) as f:
                        first_line = f.readline().decode('utf-8', errors='replace').strip()
                        return first_line
    except (zipfile.BadZipFile, OSError) as e:
        logger.debug('Could not read CSV from archive %s: %s', twbx_path, e)
    return None


def _extract_col_local_name_map(datasource_elem):
    """Build mapping of Tableau local-names to their parent table names.

    Uses ``<metadata-record class="column">`` elements which contain the
    authoritative local-name → parent-name association.  This captures
    columns that may not have a ``<column>`` element at the datasource
    level (e.g. Salesforce Id, Probability fields) but are referenced by
    calculations.

    Returns:
        dict mapping column local-name (without brackets) to parent table
        name, e.g. ``{'Opportunity ID': 'Opportunities'}``.
    """
    result = {}
    for mr in datasource_elem.findall('.//metadata-record[@class="column"]'):
        local_name = (mr.findtext('local-name') or '').strip().strip('[]')
        parent_name = (mr.findtext('parent-name') or '').strip().strip('[]')
        if local_name and parent_name and local_name not in result:
            result[local_name] = parent_name
    return result


def extract_datasource(datasource_elem, twbx_path=None):
    """
    Extracts the full details of a Tableau datasource
    
    Args:
        datasource_elem: XML element of the datasource
        twbx_path: Path to the .twbx file (for CSV delimiter detection)
    
    Returns:
        dict with connection, tables, columns, calculations, relationships
    """
    ds_name = datasource_elem.get('name', 'Unknown')
    ds_caption = datasource_elem.get('caption', ds_name)
    
    # Build the connection_name -> connection_details mapping
    connection_map = _build_connection_map(datasource_elem, twbx_path=twbx_path)
    
    calcs = extract_calculations(datasource_elem)
    for c in calcs:
        c['datasource_name'] = ds_name

    datasource = {
        'name': ds_name,
        'caption': ds_caption,
        'connection': extract_connection_details(datasource_elem),
        'connection_map': connection_map,
        'tables': extract_tables_with_columns(datasource_elem, connection_map),
        'calculations': calcs,
        'columns': extract_column_metadata(datasource_elem),
        'relationships': extract_relationships(datasource_elem),
        'col_local_name_map': _extract_col_local_name_map(datasource_elem),
    }

    # Ensure join columns referenced by relationships exist in their tables.
    # Connectors like Salesforce use internal primary keys (e.g. Id) for joins
    # that Tableau doesn't expose as visible columns.
    _ensure_relationship_columns(datasource)

    # Ensure columns referenced by calculations exist in their parent tables.
    # Salesforce connectors may have renamed columns (e.g. Id → "Opportunity ID")
    # that appear in <metadata-record> elements and <cols><map> but have no
    # <column> element, so they are not extracted by Phase 2.
    _ensure_calc_referenced_columns(datasource)
    
    return datasource


def _ensure_relationship_columns(datasource):
    """Add missing join columns to tables so relationships can be validated."""
    tables = datasource.get('tables', [])
    rels = datasource.get('relationships', [])
    if not tables or not rels:
        return

    table_map = {}
    for t in tables:
        tname = t.get('name', '')
        col_names = {c.get('name', '') for c in t.get('columns', [])}
        table_map[tname] = (t, col_names)

    for rel in rels:
        for side in ('left', 'right'):
            info = rel.get(side, {})
            tname = info.get('table', '')
            col = info.get('column', '')
            if not tname or not col or tname not in table_map:
                continue
            table_obj, col_names = table_map[tname]
            if col in col_names:
                continue
            # Check with table suffix (Salesforce pattern: 'Id' → 'Id (TableName)')
            suffixed = f"{col} ({tname})"
            if suffixed in col_names:
                # Update relationship to use the actual suffixed column name
                info['column'] = suffixed
                continue
            # Column truly missing — add it as a hidden key column
            table_obj.setdefault('columns', []).append({
                'name': col,
                'datatype': 'string',
                'role': 'dimension',
                'type': 'nominal',
                'hidden': True,
            })
            table_map[tname] = (table_obj, col_names | {col})


def _ensure_calc_referenced_columns(datasource):
    """Add missing columns to tables when calculations reference them.

    Salesforce and similar connectors rename physical columns via
    ``<metadata-record>`` (e.g. ``Id`` → ``Opportunity ID``).  These
    renamed columns often have no ``<column>`` element at the datasource
    level, so they are skipped during Phase 2 extraction.  When a
    calculation formula references such a column and
    ``col_local_name_map`` maps it to a specific table, this function
    adds the column to that table so the downstream TMDL generator can
    emit valid DAX (LOOKUPVALUE / RELATED).
    """
    tables = datasource.get('tables', [])
    calcs = datasource.get('calculations', [])
    col_map = datasource.get('col_local_name_map', {})
    if not tables or not calcs or not col_map:
        return

    # Build table lookup
    table_lookup = {}
    for t in tables:
        tname = t.get('name', '')
        col_names = {c.get('name', '') for c in t.get('columns', [])}
        table_lookup[tname] = (t, col_names)

    # Collect all column names referenced in calc formulas
    referenced_cols = set()
    for calc in calcs:
        formula = calc.get('formula', '')
        if formula:
            referenced_cols.update(re.findall(r'\[([^\]]+)\]', formula))

    # Add missing columns to their parent table
    for col_name in referenced_cols:
        parent_table = col_map.get(col_name)
        if not parent_table or parent_table not in table_lookup:
            continue
        table_obj, col_names = table_lookup[parent_table]
        if col_name in col_names:
            continue
        # Check with table suffix
        suffixed = f"{col_name} ({parent_table})"
        if suffixed in col_names:
            continue
        table_obj.setdefault('columns', []).append({
            'name': col_name,
            'datatype': 'string',
            'role': 'dimension',
            'type': 'nominal',
            'hidden': True,
        })
        table_lookup[parent_table] = (table_obj, col_names | {col_name})


def enrich_datasource_from_hyper(datasource, hyper_tables):
    """Enrich datasource metadata using data read from ``.hyper`` files.

    Bridges the gap between ``hyper_reader`` output and the datasource dict
    consumed by downstream generators.  Adds row counts, refines column types,
    and attaches hyper-specific metadata.

    Args:
        datasource: Datasource dict from ``extract_datasource()``.
        hyper_tables: list of table dicts from ``hyper_reader.read_hyper()``
            (the ``tables`` field of the reader result).

    Returns:
        datasource dict (mutated in-place for convenience).
    """
    if not hyper_tables:
        return datasource

    # Build lookup: normalised table name → hyper table info
    hyper_lookup = {}
    for ht in hyper_tables:
        raw_name = ht.get('table', '')
        # Normalise: strip schema prefix like "Extract.Extract" → "Extract"
        norm = raw_name.rsplit('.', 1)[-1].lower()
        hyper_lookup[norm] = ht
        hyper_lookup[raw_name.lower()] = ht

    for table in datasource.get('tables', []):
        tbl_name = table.get('name', '')
        norm_tbl = tbl_name.rsplit('.', 1)[-1].lower()
        ht = hyper_lookup.get(norm_tbl) or hyper_lookup.get(tbl_name.lower())
        if not ht:
            continue

        # Enrich row count
        if ht.get('row_count'):
            table['hyper_row_count'] = ht['row_count']

        # Refine column types from Hyper when XML type is missing or generic
        hyper_col_map = {
            c['name'].lower(): c for c in ht.get('columns', [])
        }
        for col in table.get('columns', []):
            hc = hyper_col_map.get(col.get('name', '').lower())
            if hc:
                existing = (col.get('datatype') or '').lower()
                hyper_type = (hc.get('hyper_type') or '').lower()
                if not existing or existing == 'string':
                    # Map common Hyper types to Tableau-style types
                    type_map = {
                        'bigint': 'integer', 'integer': 'integer',
                        'smallint': 'integer', 'int': 'integer',
                        'double': 'real', 'real': 'real', 'float': 'real',
                        'double precision': 'real', 'numeric': 'real',
                        'boolean': 'boolean', 'bool': 'boolean',
                        'date': 'date', 'timestamp': 'datetime',
                        'timestamp without time zone': 'datetime',
                        'timestamptz': 'datetime',
                    }
                    mapped = type_map.get(hyper_type)
                    if mapped:
                        col['datatype'] = mapped
                        col['hyper_type_source'] = hyper_type

        # Attach column statistics
        col_stats = ht.get('column_stats', {})
        if col_stats:
            table['hyper_column_stats'] = col_stats

    # Tag the datasource so downstream knows Hyper enrichment happened
    datasource['hyper_enriched'] = True
    datasource['hyper_table_count'] = len(hyper_tables)
    datasource['hyper_total_rows'] = sum(
        t.get('row_count', 0) for t in hyper_tables
    )

    return datasource


# ── Type coercion detection ────────────────────────────────────────────────────

# Tableau type patterns that look like auto-coerced values
_COERCION_PATTERNS = {
    ('string', 'date'): 'date',
    ('string', 'datetime'): 'datetime',
    ('string', 'integer'): 'integer',
    ('string', 'real'): 'real',
}


def detect_type_coercions(datasource):
    """Detect columns where Tableau may auto-coerce types.

    Compares the raw source type (from ``<relation>`` column metadata) against
    the semantic type (from ``<column>`` metadata).  When they differ in a way
    that indicates implicit coercion (e.g. string→date), returns a list of
    coercion hints that should be emitted as explicit ``Table.TransformColumnTypes``
    steps in Power Query M.

    Args:
        datasource: Datasource dict from ``extract_datasource()``.

    Returns:
        list of dicts ``{'table', 'column', 'from_type', 'to_type'}``
    """
    coercions = []
    col_metadata = {c['name']: c for c in datasource.get('columns', [])
                    if isinstance(c, dict)}

    for table in datasource.get('tables', []):
        tbl_name = table.get('name', '')
        for col in table.get('columns', []):
            col_name = col.get('name', '')
            raw_type = (col.get('datatype') or 'string').lower()
            # Check if metadata declares a different semantic type
            meta = col_metadata.get(col_name, {})
            semantic_type = (meta.get('datatype') or raw_type).lower()

            key = (raw_type, semantic_type)
            if key in _COERCION_PATTERNS:
                coercions.append({
                    'table': tbl_name,
                    'column': col_name,
                    'from_type': raw_type,
                    'to_type': semantic_type,
                })
    return coercions


def resolve_published_datasource(datasource, server_client=None):
    """Resolve a published (sqlproxy) datasource via Tableau Server API.

    If the datasource connection type is 'Tableau Server' (sqlproxy), and a
    ``server_client`` is provided, fetch the published datasource definition
    and merge its tables, columns, and connection info into the local datasource.

    Args:
        datasource: Datasource dict from extract_datasource().
        server_client: Optional TableauServerClient (from server_client.py).

    Returns:
        The datasource dict (mutated in place, or unchanged if not sqlproxy).
    """
    conn = datasource.get('connection', {})
    if conn.get('type') != 'Tableau Server':
        return datasource

    ds_name = conn.get('details', {}).get('server_ds_name', '')
    if not ds_name or server_client is None:
        # Mark as unresolved — caller can warn or skip
        datasource['_published_unresolved'] = True
        return datasource

    try:
        # Attempt to list datasources and find matching one
        remote_datasources = server_client.list_datasources()
        match = None
        for rds in remote_datasources:
            if rds.get('name', '') == ds_name:
                match = rds
                break

        if not match:
            datasource['_published_unresolved'] = True
            logger.warning('Published datasource %r not found on server', ds_name)
            return datasource

        # Download and extract the remote datasource
        ds_id = match.get('id', '')
        if ds_id and hasattr(server_client, 'download_datasource'):
            import tempfile
            tmp_path = server_client.download_datasource(ds_id)
            if tmp_path and os.path.exists(tmp_path):
                try:
                    remote_ds = _parse_published_datasource_file(tmp_path)
                    if remote_ds:
                        # Merge: take connection, tables, columns from remote
                        if remote_ds.get('connection'):
                            datasource['connection'] = remote_ds['connection']
                        if remote_ds.get('tables'):
                            datasource['tables'] = remote_ds['tables']
                        if remote_ds.get('columns'):
                            datasource['columns'] = remote_ds['columns']
                        if remote_ds.get('relationships'):
                            datasource['relationships'] = remote_ds['relationships']
                        if remote_ds.get('connection_map'):
                            datasource['connection_map'] = remote_ds['connection_map']
                        datasource['_published_resolved'] = True
                finally:
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
    except Exception as e:
        logger.warning('Failed to resolve published datasource %r: %s', ds_name, e)
        datasource['_published_unresolved'] = True

    return datasource


def _parse_published_datasource_file(file_path):
    """Parse a downloaded .tdsx/.tds file into a datasource dict."""
    try:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.tdsx':
            with zipfile.ZipFile(file_path, 'r') as z:
                tds_names = [n for n in z.namelist() if n.endswith('.tds')]
                if not tds_names:
                    return None
                with z.open(tds_names[0]) as f:
                    tree = ET.parse(f)
        else:
            tree = ET.parse(file_path)

        root = tree.getroot()
        ds_elem = root.find('.//datasource')
        if ds_elem is None:
            ds_elem = root if root.tag == 'datasource' else None
        if ds_elem is None:
            return None
        return extract_datasource(ds_elem, twbx_path=file_path if ext == '.tdsx' else None)
    except Exception as e:
        logger.warning('Could not parse published datasource file %s: %s', file_path, e)
        return None


def _parse_connection_class(inner_conn, named_conn=None, twbx_path=None):
    """Parses a single Tableau <connection> element into {type, details}.
    
    This is the single source of truth for mapping Tableau connection XML
    attributes to the normalized {type, details} dicts used downstream.
    
    Args:
        inner_conn: XML <connection> element
        named_conn: Optional XML <named-connection> parent (for caption/name)
        twbx_path: Optional .twbx path (for CSV delimiter auto-detection)
    
    Returns:
        dict: {type: str, details: dict}
    """
    conn_class = inner_conn.get('class', 'unknown')

    # ── Dispatch table for simple attribute-mapping connectors ──────────────
    # Each entry: conn_class → (type_name, {detail_key: xml_attr_or_default, ...})
    _SIMPLE_CONNECTORS = {
        'excel-direct': ('Excel', {
            'filename': ('filename', ''),
            'cleaning': ('cleaning', 'no'),
            'compat': ('compat', 'no'),
        }),
        'ogrdirect': ('GeoJSON', {
            'filename': ('filename', ''),
            'directory': ('directory', ''),
        }),
        'sqlserver': ('SQL Server', {
            'server': ('server', ''),
            'database': ('dbname', ''),
            'authentication': ('authentication', 'sspi'),
            'username': ('username', ''),
        }),
        'postgres': ('PostgreSQL', {
            'server': ('server', ''),
            'port': ('port', '5432'),
            'database': ('dbname', ''),
            'username': ('username', ''),
            'sslmode': ('sslmode', 'require'),
        }),
        'bigquery': ('BigQuery', {
            'project': ('project', ''),
            'dataset': ('dataset', ''),
            'service_account': ('service-account-email', ''),
        }),
        'oracle': ('Oracle', {
            'server': ('server', ''),
            'service': ('service', ''),
            'port': ('port', '1521'),
            'username': ('username', ''),
        }),
        'mysql': ('MySQL', {
            'server': ('server', ''),
            'port': ('port', '3306'),
            'database': ('dbname', ''),
            'username': ('username', ''),
        }),
        'snowflake': ('Snowflake', {
            'server': ('server', ''),
            'database': ('dbname', ''),
            'schema': ('schema', ''),
            'warehouse': ('warehouse', ''),
            'role': ('role', ''),
        }),
        'sapbw': ('SAP BW', {
            'server': ('server', ''),
            'system_number': ('systemNumber', '00'),
            'client_id': ('clientId', ''),
            'language': ('language', 'EN'),
            'cube': ('cube', ''),
            'catalog': ('catalog', ''),
        }),
    }

    # ── Special cases (need extra logic) ────────────────────────────────────
    if conn_class == 'excel-direct':
        result = _build_from_dispatch(inner_conn, _SIMPLE_CONNECTORS['excel-direct'])
        result['details']['caption'] = named_conn.get('caption', '') if named_conn is not None else ''
        return result

    if conn_class == 'textscan':
        csv_filename = inner_conn.get('filename', '')
        csv_directory = inner_conn.get('directory', '')
        delimiter = inner_conn.get('separator', '')
        if not delimiter:
            header = _read_csv_header_from_twbx(twbx_path, csv_directory, csv_filename)
            delimiter = _detect_csv_delimiter(header) if header else ','
        return {
            'type': 'CSV',
            'details': {
                'filename': csv_filename,
                'directory': csv_directory,
                'delimiter': delimiter,
                'encoding': inner_conn.get('charset', 'utf-8')
            }
        }

    # ── Dispatch simple connectors ──────────────────────────────────────────
    if conn_class in _SIMPLE_CONNECTORS:
        return _build_from_dispatch(inner_conn, _SIMPLE_CONNECTORS[conn_class])

    # ── sqlproxy: Tableau Server Published Datasource ──────────────────────
    if conn_class == 'sqlproxy':
        return {
            'type': 'Tableau Server',
            'details': {
                'server': inner_conn.get('server', ''),
                'port': inner_conn.get('port', '443'),
                'dbname': inner_conn.get('dbname', ''),
                'channel': inner_conn.get('channel', 'https'),
                'server_ds_name': inner_conn.get('server-ds-friendly-name', ''),
            }
        }

    # ── Fallback for unknown connector types ────────────────────────────────
    return {
        'type': conn_class.upper(),
        'details': dict(inner_conn.attrib)
    }


def _build_from_dispatch(inner_conn, spec):
    """Build a {type, details} dict from a dispatch table spec."""
    type_name, attr_map = spec
    details = {}
    for detail_key, (xml_attr, default) in attr_map.items():
        details[detail_key] = inner_conn.get(xml_attr, default)
    return {'type': type_name, 'details': details}


def _build_connection_map(datasource_elem, twbx_path=None):
    """Builds a connection_name -> {type, details} mapping from named-connections.
    
    Each physical table in Tableau references a named-connection via its
    'connection' attribute. This function extracts the details of each named-connection
    to generate the correct M queries per table.
    """
    conn_map = {}
    
    connection_elem = datasource_elem.find('.//connection[@class="federated"]')
    if connection_elem is None:
        connection_elem = datasource_elem.find('.//connection')
    if connection_elem is None:
        return conn_map
    
    for named_conn in connection_elem.findall('.//named-connection'):
        nc_name = named_conn.get('name', '')
        inner_conn = named_conn.find('.//connection')
        if inner_conn is None or not nc_name:
            continue
        conn_map[nc_name] = _parse_connection_class(inner_conn, named_conn, twbx_path)
    
    return conn_map


def extract_connection_details(datasource_elem):
    """Extracts connection details (Excel, SQL, etc.)"""
    connection_elem = datasource_elem.find('.//connection[@class="federated"]')
    if connection_elem is None:
        connection_elem = datasource_elem.find('.//connection')
    if connection_elem is None:
        return {'type': 'Unknown', 'details': {}}
    
    named_conn = connection_elem.find('.//named-connection')
    if named_conn is not None:
        inner_conn = named_conn.find('.//connection')
        if inner_conn is not None:
            return _parse_connection_class(inner_conn, named_conn)
    
    # Direct connection (no named-connection wrapper) — e.g. sqlproxy
    conn_class = connection_elem.get('class', '')
    if conn_class and conn_class != 'federated':
        return _parse_connection_class(connection_elem)

    return {'type': 'Unknown', 'details': {}}


def extract_tables_with_columns(datasource_elem, connection_map=None):
    """Extracts only physical tables (type='table') with their columns.
    
    IMPORTANT: Do NOT extract 'join' nodes which created fictitious tables
    with duplicated columns from all joined tables ('Unknown' table bug).
    
    Deduplicates by table name (keeps the version with the most columns)
    and stores per-table connection details.
    
    For SQL Server and similar connections where <relation> elements are
    self-closing (no nested <columns>), falls back to the datasource-level
    <cols> mapping and <column> definitions to populate table columns.
    """
    if connection_map is None:
        connection_map = {}
    
    # Phase 1: Collect all physical tables
    raw_tables = {}  # name -> best table dict
    
    for relation in datasource_elem.findall('.//relation'):
        # ONLY physical tables, NOT joins
        table_type = relation.get('type', '')
        if table_type != 'table':
            continue
        
        table_name = relation.get('name', '')
        if not table_name:
            continue
        
        conn_ref = relation.get('connection', '')
        
        columns = []
        for col_elem in relation.findall('./columns/column'):
            raw_name = col_elem.get('name', '')
            datatype = col_elem.get('datatype', 'string')
            column = {
                'name': _reverse_tableau_bracket_escape(raw_name),
                'datatype': datatype,
                'role': 'measure' if datatype in ('real', 'integer') else 'dimension',
                'ordinal': int(col_elem.get('ordinal', 0)),
                'length': col_elem.get('length', None),
                'nullable': col_elem.get('nullable', 'true') == 'true',
                'default_format': col_elem.get('default-format', ''),
            }
            columns.append(column)
        
        # Deduplicate: keep the version with the most columns
        if table_name not in raw_tables or len(columns) > len(raw_tables[table_name].get('columns', [])):
            # Resolve connection details for this table
            table_connection = connection_map.get(conn_ref, {})
            
            raw_tables[table_name] = {
                'name': table_name,
                'type': 'table',
                'columns': columns,
                'connection': conn_ref,
                'connection_details': table_connection,
                'caption': relation.get('caption', ''),
            }
    
    # Phase 2: For tables with no nested columns (SQL Server, etc.),
    # populate from datasource-level <cols> mapping + <column> elements.
    tables_needing_columns = [t for t in raw_tables.values() if not t['columns']]
    if tables_needing_columns:
        # Build mapping: table_name -> [column_name, ...] from <cols><map> entries
        # e.g. <map key='[OrderID]' value='[Orders].[OrderID]' />
        table_col_names = {}  # table_name -> [col_key, ...]
        cols_elem = datasource_elem.find('.//connection/cols')
        if cols_elem is not None:
            for map_elem in cols_elem.findall('map'):
                key = map_elem.get('key', '')       # e.g. "[OrderID]"
                value = map_elem.get('value', '')    # e.g. "[Orders].[OrderID]"
                if '.' in value:
                    parts = value.split('.', 1)
                    tbl = parts[0].strip('[]')
                    if tbl in raw_tables:
                        table_col_names.setdefault(tbl, []).append(key)
        
        # Build mapping: column_name -> column attributes from datasource-level <column> elements
        ds_columns = {}  # "[ColName]" -> {datatype, role, type, ...}
        for col_elem in datasource_elem.findall('./column'):
            col_name = col_elem.get('name', '')
            # Skip calculated columns (they have a <calculation> child)
            if col_elem.find('.//calculation') is not None:
                continue
            # Skip user-filter columns
            if col_elem.get('user:auto-column', '') == 'sheet_link':
                continue
            datatype = col_elem.get('datatype', 'string')
            # Infer role: explicit role attribute takes precedence,
            # otherwise numeric types default to 'measure' (Tableau convention)
            explicit_role = col_elem.get('role', '')
            if explicit_role:
                role = explicit_role
            elif datatype in ('real', 'integer'):
                role = 'measure'
            else:
                role = 'dimension'
            ds_columns[col_name] = {
                'name': col_name.strip('[]'),
                'datatype': datatype,
                'role': role,
                'ordinal': 0,
                'length': None,
                'nullable': True,
                'default_format': col_elem.get('default-format', ''),
            }
        
        # Populate columns for each table that needs them
        for table in tables_needing_columns:
            tname = table['name']
            col_keys = table_col_names.get(tname, [])
            ordinal = 0
            for key in col_keys:
                if key in ds_columns:
                    col = dict(ds_columns[key])
                    col['ordinal'] = ordinal
                    ordinal += 1
                    table['columns'].append(col)
    
    # Phase 2.5: Override column roles from datasource-level <column> elements.
    # Users may override Tableau's default role (e.g. set an integer column
    # like "Row ID" to dimension). These overrides are stored at the
    # datasource level as explicit role attributes.
    ds_role_overrides = {}
    for col_elem in datasource_elem.findall('./column'):
        col_name = col_elem.get('name', '').strip('[]')
        explicit_role = col_elem.get('role', '')
        if col_name and explicit_role:
            ds_role_overrides[col_name] = explicit_role
    if ds_role_overrides:
        for table in raw_tables.values():
            for col in table.get('columns', []):
                cname = col.get('name', '')
                if cname in ds_role_overrides:
                    col['role'] = ds_role_overrides[cname]

    # Phase 3: For tables STILL with no columns, extract from
    # <metadata-records><metadata-record class='column'>.
    # This is the primary column source for SQL Server and similar
    # connections where <relation> elements are self-closing (no nested
    # <columns>) and no <cols><map> entries exist.
    still_needing = [t for t in raw_tables.values() if not t['columns']]
    if still_needing:
        metadata_table_cols = {}
        for mr in datasource_elem.findall('.//metadata-record[@class="column"]'):
            remote_name = (mr.findtext('remote-name') or '').strip()
            local_name = (mr.findtext('local-name') or '').strip()
            parent_name = (mr.findtext('parent-name') or '').strip().strip('[]')
            local_type = (mr.findtext('local-type') or 'string').strip()
            ordinal_text = (mr.findtext('ordinal') or '0').strip()
            contains_null = (mr.findtext('contains-null') or 'true').strip()

            col_name = local_name.strip('[]') if local_name else remote_name
            if not col_name or not parent_name:
                continue

            try:
                ordinal_val = int(ordinal_text)
            except ValueError:
                ordinal_val = 0

            col = {
                'name': col_name,
                'datatype': local_type,
                'role': 'measure' if local_type in ('real', 'integer') else 'dimension',
                'ordinal': ordinal_val,
                'length': None,
                'nullable': contains_null == 'true',
            }
            metadata_table_cols.setdefault(parent_name, []).append(col)

        for table in still_needing:
            tname = table['name']
            meta_cols = metadata_table_cols.get(tname, [])
            if meta_cols:
                meta_cols.sort(key=lambda c: c['ordinal'])
                table['columns'] = meta_cols

    # Phase 4: Last-resort fallback — if a table still has no columns,
    # populate from datasource-level <column> elements that are NOT
    # calculations (physical columns only).
    final_needing = [t for t in raw_tables.values() if not t['columns']]
    if final_needing:
        ds_phys_cols = []
        ordinal = 0
        for col_elem in datasource_elem.findall('./column'):
            if col_elem.find('.//calculation') is not None:
                continue
            if col_elem.get('user:auto-column', '') == 'sheet_link':
                continue
            col_name = col_elem.get('name', '').strip('[]')
            if not col_name:
                continue
            ds_phys_cols.append({
                'name': col_name,
                'datatype': col_elem.get('datatype', 'string'),
                'role': 'measure' if col_elem.get('datatype', 'string') in ('real', 'integer') else 'dimension',
                'ordinal': ordinal,
                'length': None,
                'nullable': True,
            })
            ordinal += 1

        if ds_phys_cols:
            for table in final_needing:
                table['columns'] = list(ds_phys_cols)

    # Filter out 0-column tables when other tables have columns
    # (e.g. Tableau extract artifacts like 'Extract' tables in .twbx files)
    tables = list(raw_tables.values())
    has_populated = any(t['columns'] for t in tables)
    if has_populated:
        tables = [t for t in tables if t['columns']]
    return tables


def extract_table_extensions(datasource_elem):
    """Extracts Tableau 2024.2+ table extensions (Einstein Discovery, external API data).

    Table extensions allow Tableau to augment datasources with data from
    external APIs or Einstein Discovery predictions. This function extracts
    their configuration for migration to Power Query Web.Contents() or
    placeholder notes.

    Returns:
        list of dicts with extension_type, name, endpoint, schema, config.
    """
    extensions = []
    for ext_elem in datasource_elem.findall('.//table-extension'):
        ext_type = ext_elem.get('type', 'unknown')
        ext_name = ext_elem.get('name', ext_elem.get('caption', ''))

        # Extract API endpoint if present
        endpoint = ''
        config_elem = ext_elem.find('.//connection')
        if config_elem is not None:
            endpoint = config_elem.get('url', config_elem.get('server', ''))

        # Extract schema (output columns)
        schema = []
        for col_elem in ext_elem.findall('.//column'):
            schema.append({
                'name': col_elem.get('name', '').strip('[]'),
                'datatype': col_elem.get('datatype', 'string'),
            })

        # Extract extension configuration
        config = {}
        for attr in ext_elem.attrib:
            if attr not in ('type', 'name', 'caption'):
                config[attr] = ext_elem.get(attr)

        # Check for nested config elements
        for cfg_elem in ext_elem.findall('.//configuration/*'):
            config[cfg_elem.tag] = cfg_elem.text or cfg_elem.get('value', '')

        extensions.append({
            'name': ext_name or f'Extension_{len(extensions) + 1}',
            'extension_type': ext_type,
            'endpoint': endpoint,
            'schema': schema,
            'config': config,
        })

    return extensions


def extract_column_metadata(datasource_elem):
    """Extracts complete column metadata"""
    columns = []
    
    for col_elem in datasource_elem.findall('.//column'):
        column = {
            'name': col_elem.get('name', ''),
            'caption': col_elem.get('caption', ''),
            'datatype': col_elem.get('datatype', 'string'),
            'role': col_elem.get('role', 'dimension'),
            'type': col_elem.get('type', 'nominal'),
            'hidden': col_elem.get('hidden', 'false') == 'true',
            'semantic_role': col_elem.get('semantic-role', ''),
            'default_aggregation': col_elem.get('default-type', ''),
            'default_format': col_elem.get('default-format', ''),
            'description': col_elem.get('desc', ''),
            'calculation': None
        }
        
        # Check if it is a calculation
        calc_elem = col_elem.find('.//calculation')
        if calc_elem is not None:
            column['calculation'] = {
                'class': calc_elem.get('class', 'tableau'),
                'formula': calc_elem.get('formula', '')
            }
        
        columns.append(column)
    
    return columns


def extract_calculations(datasource_elem):
    """Extracts Tableau calculations with formulas.
    
    Also extracts <table-calc> elements for COMPUTE USING (addressing)
    so that DAX generation can use proper filter context.
    """
    calculations = []
    
    for col_elem in datasource_elem.findall('.//column'):
        calc_elem = col_elem.find('.//calculation')
        if calc_elem is not None:
            calc_class = calc_elem.get('class', 'tableau')
            # Skip categorical-bin calculations — they are handled by group
            # extraction and have no formula, which would produce empty measures.
            if calc_class == 'categorical-bin':
                continue
            calc_formula = calc_elem.get('formula', '')
            # Skip calculations with no formula to avoid empty measures
            if not calc_formula.strip():
                continue
            calculation = {
                'name': col_elem.get('name', ''),
                'caption': col_elem.get('caption', col_elem.get('name', '')),
                'formula': calc_formula,
                'class': calc_class,
                'datatype': col_elem.get('datatype', 'real'),
                'role': col_elem.get('role', 'measure'),
                'type': col_elem.get('type', 'quantitative'),
                'description': col_elem.get('desc', '')
            }
            
            # Extract table-calc addressing (COMPUTE USING dimensions)
            table_calc = calc_elem.find('.//table-calc')
            if table_calc is not None:
                addressing_fields = []
                for addr in table_calc.findall('.//addressing-field'):
                    field_name = addr.get('name', addr.text or '')
                    if field_name:
                        # Clean [datasource].[field] format
                        match = re.search(r'\[([^\]]+)\]$', field_name)
                        addressing_fields.append(match.group(1) if match else field_name)
                
                partition_fields = []
                for part in table_calc.findall('.//partitioning-field'):
                    field_name = part.get('name', part.text or '')
                    if field_name:
                        match = re.search(r'\[([^\]]+)\]$', field_name)
                        partition_fields.append(match.group(1) if match else field_name)
                
                if addressing_fields or partition_fields:
                    calculation['table_calc_addressing'] = addressing_fields
                    calculation['table_calc_partitioning'] = partition_fields
                    calculation['table_calc_type'] = table_calc.get('type', '')
                    calculation['table_calc_ordering'] = table_calc.get('ordering-type', '')
            
            calculations.append(calculation)
    
    return calculations


def extract_relationships(datasource_elem):
    """Extracts relationships between tables from Tableau joins.
    
    Handles two Tableau column reference formats in join clauses:
    - [Table].[Column] — explicit table prefix
    - [Column]          — bare column, table inferred from child relations
    """
    relationships = []
    seen = set()  # Avoid duplicates
    
    # Search for joins in relations
    for relation in datasource_elem.findall('.//relation[@type="join"]'):
        join_type = relation.get('join', 'inner')
        
        # Collect direct child relation names for table inference
        # (first child = left table, second child = right table)
        child_relations = []
        for child in relation:
            if child.tag == 'relation':
                child_name = child.get('name', '')
                if child_name:
                    child_relations.append(child_name)
                else:
                    # Nested join — recurse into its children to find the first table
                    for gc in child:
                        if gc.tag == 'relation' and gc.get('name'):
                            child_relations.append(gc.get('name'))
                            break
                        elif gc.tag == 'relation' and gc.get('type') == 'join':
                            # Deeper nesting: find leftmost leaf table
                            for ggc in gc:
                                if ggc.tag == 'relation' and ggc.get('name'):
                                    child_relations.append(ggc.get('name'))
                                    break
                            if child_relations:
                                break
        
        # Extract columns from clause expressions
        for clause in relation.findall('./clause'):
            pairs = []
            eq_expr = clause.find('./expression[@op="="]')
            if eq_expr is not None:
                for sub_expr in eq_expr.findall('./expression'):
                    op = sub_expr.get('op', '')
                    # Try [Table].[Column] format first
                    matches = re.findall(r'\[([^\]]+)\]\.\[([^\]]+)\]', op)
                    if matches:
                        pairs.append({'table': matches[0][0], 'column': matches[0][1]})
                    else:
                        # Bare [Column] format — table inferred from child relations
                        bare = re.findall(r'\[([^\]]+)\]', op)
                        if bare:
                            pairs.append({'table': '', 'column': bare[0]})
            
            # Resolve bare table names from child relation order
            if len(pairs) == 2:
                for i, pair in enumerate(pairs):
                    if not pair['table'] and i < len(child_relations):
                        pair['table'] = child_relations[i]
                    elif not pair['table']:
                        # Fallback: use the other pair's table info to guess
                        other_idx = 1 - i
                        if child_relations:
                            # Use the first child relation that isn't the other pair's table
                            for cr in child_relations:
                                if cr != pairs[other_idx].get('table', ''):
                                    pair['table'] = cr
                                    break

                if pairs[0]['table'] and pairs[1]['table']:
                    key = (pairs[0]['table'], pairs[0]['column'],
                           pairs[1]['table'], pairs[1]['column'])
                    if key not in seen:
                        seen.add(key)
                        relationships.append({
                            'type': join_type,
                            'left': {'table': pairs[0]['table'], 'column': pairs[0]['column']},
                            'right': {'table': pairs[1]['table'], 'column': pairs[1]['column']}
                        })
    
    # --- New format: Object Model relationships (modern Tableau) ---
    for elem in datasource_elem.iter():
        if elem.tag and elem.tag.endswith('object-graph'):
            # Build object-id → table caption map
            obj_id_to_name = {}
            for obj_elem in elem.findall('.//object'):
                obj_id = obj_elem.get('id', '')
                obj_caption = obj_elem.get('caption', '')
                if obj_id and obj_caption:
                    obj_id_to_name[obj_id] = obj_caption

            for rel_elem in elem.findall('.//relationship'):
                # Try attribute-based expression (some formats)
                expr = rel_elem.get('expression', '')
                join_type = rel_elem.get('type', 'Left').lower()

                # Method 1: expression attribute with [Table].[Column] format
                matches = re.findall(r'\[([^\]]+)\]\.\[([^\]]+)\]', expr)
                if len(matches) >= 2:
                    left_table, left_col = matches[0]
                    right_table, right_col = matches[1]
                    key = (left_table, left_col, right_table, right_col)
                    if key not in seen:
                        seen.add(key)
                        relationships.append({
                            'type': join_type,
                            'left': {'table': left_table, 'column': left_col},
                            'right': {'table': right_table, 'column': right_col}
                        })
                    continue

                # Method 2: nested <expression> child elements + endpoint object-ids
                expr_elem = rel_elem.find('expression')
                if expr_elem is None:
                    continue
                col_ops = []
                for sub_expr in expr_elem.findall('expression'):
                    op = sub_expr.get('op', '')
                    col_match = re.findall(r'\[([^\]]+)\]', op)
                    if col_match:
                        col_ops.append(col_match[0])
                if len(col_ops) < 2:
                    continue

                # Resolve endpoint object-ids to table names
                first_ep = rel_elem.find('first-end-point')
                second_ep = rel_elem.find('second-end-point')
                if first_ep is None or second_ep is None:
                    continue
                first_table = obj_id_to_name.get(first_ep.get('object-id', ''), '')
                second_table = obj_id_to_name.get(second_ep.get('object-id', ''), '')
                if not first_table or not second_table:
                    continue

                # Column names may have "(TableName)" suffix — strip it
                left_col = col_ops[0]
                right_col = col_ops[1]
                # Strip " (TableName)" suffix if it matches the endpoint table
                suffix_first = f' ({first_table})'
                suffix_second = f' ({second_table})'
                if left_col.endswith(suffix_first):
                    left_col = left_col[:-len(suffix_first)]
                if right_col.endswith(suffix_second):
                    right_col = right_col[:-len(suffix_second)]
                # Also strip the other table's suffix (in case of reversed naming)
                if left_col.endswith(suffix_second):
                    left_col = left_col[:-len(suffix_second)]
                if right_col.endswith(suffix_first):
                    right_col = right_col[:-len(suffix_first)]

                key = (first_table, left_col, second_table, right_col)
                if key not in seen:
                    seen.add(key)
                    relationships.append({
                        'type': join_type,
                        'left': {'table': first_table, 'column': left_col},
                        'right': {'table': second_table, 'column': right_col}
                    })
    
    return relationships


# â”€â”€ Re-exports from extracted modules â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# These functions were extracted for maintainability but are re-exported here
# so that ALL existing imports remain valid (backward compatibility).

from dax_converter import (              # noqa: E402
    convert_tableau_formula_to_dax,
    map_tableau_to_powerbi_type,
)

from m_query_builder import (            # noqa: E402
    generate_power_query_m,
    map_tableau_to_m_type,
    inject_m_steps,
    m_transform_rename,
    m_transform_remove_columns,
    m_transform_select_columns,
    m_transform_filter_values,
    m_transform_filter_nulls,
    m_transform_aggregate,
    m_transform_unpivot,
    m_transform_unpivot_other,
    m_transform_pivot,
    m_transform_join,
    m_transform_union,
    m_transform_sort,
    m_transform_add_column,
    m_transform_conditional_column,
)
