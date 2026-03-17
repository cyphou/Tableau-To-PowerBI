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
        'relationships': extract_relationships(datasource_elem)
    }
    
    return datasource


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
                'connection_details': table_connection
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
                'type': col_elem.get('type', 'quantitative')
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
