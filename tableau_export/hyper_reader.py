"""
Hyper file data reader — reads row-level data from Tableau ``.hyper`` extracts.

Reader chain (tried in order):
1. Optional ``tableauhyperapi`` package — reads 100% of ``.hyper`` files
   including proprietary v2+ format.  Install via ``pip install tableauhyperapi``.
2. Stdlib ``sqlite3`` — works for older SQLite-compatible ``.hyper`` files.
   Now supports **multi-schema** tables (``Extract.Extract``, ``public.Orders``).
3. Binary header scanning — last resort for metadata-only extraction.

Configurable via ``max_rows`` parameter (default 20, overridable with ``--hyper-rows``).
Returns schema + sample rows + column statistics, and can generate Power Query M
``#table()`` or ``Csv.Document()`` expressions.

No external dependencies required — ``tableauhyperapi`` is optional.
"""

import logging
import os
import re
import sqlite3
import struct
import tempfile
import zipfile

logger = logging.getLogger(__name__)

# ── Hyper column type  →  Power Query M type mapping ────────────────

_HYPER_TO_M_TYPE = {
    'boolean': 'Logical.Type',
    'bool': 'Logical.Type',
    'bigint': 'Int64.Type',
    'smallint': 'Int64.Type',
    'integer': 'Int64.Type',
    'int': 'Int64.Type',
    'double': 'Number.Type',
    'double precision': 'Number.Type',
    'real': 'Number.Type',
    'float': 'Number.Type',
    'numeric': 'Number.Type',
    'text': 'Text.Type',
    'varchar': 'Text.Type',
    'char': 'Text.Type',
    'character varying': 'Text.Type',
    'json': 'Text.Type',
    'date': 'Date.Type',
    'timestamp': 'DateTime.Type',
    'timestamp without time zone': 'DateTime.Type',
    'timestamptz': 'DateTimeZone.Type',
    'timestamp with time zone': 'DateTimeZone.Type',
    'time': 'Time.Type',
    'time without time zone': 'Time.Type',
    'interval': 'Duration.Type',
    'bytes': 'Binary.Type',
    'oid': 'Int64.Type',
    'geography': 'Text.Type',
}


def _m_type_for(hyper_type):
    """Map a Hyper SQL type string to a Power Query M type literal."""
    key = hyper_type.strip().lower()
    return _HYPER_TO_M_TYPE.get(key, 'Any.Type')


def _m_literal(value, m_type='Any.Type'):
    """Convert a Python value to a Power Query M literal string."""
    if value is None:
        return 'null'
    if m_type == 'Logical.Type':
        return 'true' if value else 'false'
    if m_type in ('Int64.Type', 'Number.Type'):
        return str(value)
    if m_type == 'Date.Type':
        s = str(value)
        # Try ISO date: YYYY-MM-DD
        m = re.match(r'(\d{4})-(\d{1,2})-(\d{1,2})', s)
        if m:
            return f'#date({m.group(1)}, {m.group(2)}, {m.group(3)})'
        return f'"{s}"'
    if m_type in ('DateTime.Type', 'DateTimeZone.Type'):
        s = str(value)
        m = re.match(r'(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2}):(\d{2})', s)
        if m:
            return (f'#datetime({m.group(1)}, {m.group(2)}, {m.group(3)}, '
                    f'{m.group(4)}, {m.group(5)}, {m.group(6)})')
        return f'"{s}"'
    # Default — text
    escaped = str(value).replace('"', '""')
    return f'"{escaped}"'


# ── tableauhyperapi-based reading (Option A) ───────────────────────

def _read_hyper_api(file_path, max_rows=20):
    """Read a ``.hyper`` file using the optional ``tableauhyperapi`` package.

    This handles 100% of ``.hyper`` files including proprietary v2+ format.
    Returns ``None`` if the package is not installed.
    """
    try:
        from tableauhyperapi import HyperProcess, Telemetry, Connection, TableName
    except ImportError:
        return None

    tables = []
    try:
        with HyperProcess(telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hyper:
            with Connection(endpoint=hyper.endpoint, database=file_path) as conn:
                # Enumerate all schemas and tables
                schema_names = conn.catalog.get_schema_names()
                for schema in schema_names:
                    table_names = conn.catalog.get_table_names(schema)
                    for tbl in table_names:
                        tname = str(tbl)
                        # Get column definitions
                        table_def = conn.catalog.get_table_definition(tbl)
                        columns = []
                        for col in table_def.columns:
                            columns.append({
                                'name': col.name.unescaped,
                                'hyper_type': str(col.type),
                            })

                        # Get row count
                        row_count = conn.execute_scalar_query(
                            f'SELECT COUNT(*) FROM {tbl}'
                        )

                        # Fetch sample rows
                        sample_rows = []
                        if columns and max_rows > 0:
                            with conn.execute_query(
                                f'SELECT * FROM {tbl} LIMIT {max_rows}'
                            ) as result:
                                for row in result:
                                    sample = {}
                                    for i, col_info in enumerate(columns):
                                        sample[col_info['name']] = row[i]
                                    sample_rows.append(sample)

                        # Column statistics (Option D)
                        col_stats = _compute_column_stats_hyper_api(
                            conn, tbl, columns
                        )

                        tables.append({
                            'table': tname,
                            'columns': columns,
                            'column_count': len(columns),
                            'sample_rows': sample_rows,
                            'sample_row_count': len(sample_rows),
                            'row_count': row_count,
                            'column_stats': col_stats,
                        })
    except Exception as exc:
        logger.debug('tableauhyperapi read failed for %s: %s', file_path, exc)
        return None

    return tables if tables else None


def _compute_column_stats_hyper_api(conn, table_ref, columns):
    """Compute per-column statistics via tableauhyperapi."""
    stats = {}
    for col in columns:
        cname = col['name']
        try:
            distinct = conn.execute_scalar_query(
                f'SELECT COUNT(DISTINCT "{cname}") FROM {table_ref}'
            )
            stats[cname] = {'distinct_count': distinct}
        except Exception:
            stats[cname] = {'distinct_count': None}
    return stats


# ── SQLite-based reading ────────────────────────────────────────────

def _read_hyper_sqlite(file_path, max_rows=20):
    """Attempt to read a ``.hyper`` file using ``sqlite3``.

    Supports multi-schema tables (Option B): queries both ``sqlite_master``
    and schema-qualified tables like ``Extract.Extract``.

    Args:
        file_path: Path to the ``.hyper`` file on disk.
        max_rows: Maximum sample rows to fetch per table.

    Returns:
        list[dict] | None:
            Each dict represents a table with keys:
            ``table``, ``columns`` (list of {name, hyper_type}),
            ``sample_rows`` (list of dicts), ``row_count``,
            ``column_stats`` (dict of per-column stats).
            Returns ``None`` if the file is not SQLite-compatible.
    """
    try:
        conn = sqlite3.connect(f'file:{file_path}?mode=ro', uri=True)
    except (sqlite3.DatabaseError, sqlite3.OperationalError):
        return None

    try:
        cursor = conn.cursor()
        # List user tables (skip internal/sqlite tables)
        try:
            cursor.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        except sqlite3.DatabaseError:
            conn.close()
            return None

        table_names = [row[0] for row in cursor.fetchall()]

        # Option B: Also discover schema-qualified tables
        # Many Hyper files use "Extract"."Extract" schema convention
        _HYPER_SCHEMAS = ['Extract', 'public', 'stg']
        for schema in _HYPER_SCHEMAS:
            try:
                cursor.execute(
                    f'SELECT name FROM "{schema}".sqlite_master '
                    f"WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
                for row in cursor.fetchall():
                    qualified = f'{schema}.{row[0]}'
                    if qualified not in table_names and row[0] not in table_names:
                        table_names.append(qualified)
            except sqlite3.DatabaseError:
                pass

        if not table_names:
            conn.close()
            return None

        tables = []
        for tname in table_names:
            # Determine quoted name for queries
            if '.' in tname:
                parts = tname.split('.', 1)
                quoted = f'"{parts[0]}"."{parts[1]}"'
                pragma_table = parts[1]
            else:
                quoted = f'"{tname}"'
                pragma_table = tname

            # Get column info via PRAGMA
            try:
                cursor.execute(f'PRAGMA table_info({quoted})')
                col_info = cursor.fetchall()
                if not col_info and '.' in tname:
                    # Try schema-qualified PRAGMA
                    cursor.execute(f'PRAGMA "{tname.split(".", 1)[0]}".table_info("{pragma_table}")')
                    col_info = cursor.fetchall()
                # col_info rows: (cid, name, type, notnull, dflt_value, pk)
                columns = []
                for ci in col_info:
                    columns.append({
                        'name': ci[1],
                        'hyper_type': ci[2] if ci[2] else 'text',
                    })
            except sqlite3.DatabaseError:
                columns = []

            # Get row count
            try:
                cursor.execute(f'SELECT COUNT(*) FROM {quoted}')
                row_count = cursor.fetchone()[0]
            except sqlite3.DatabaseError:
                row_count = 0

            # Fetch sample rows
            sample_rows = []
            if columns and max_rows > 0:
                try:
                    cursor.execute(
                        f'SELECT * FROM {quoted} LIMIT {max_rows}'
                    )
                    for row in cursor.fetchall():
                        sample = {}
                        for i, col in enumerate(columns):
                            sample[col['name']] = row[i] if i < len(row) else None
                        sample_rows.append(sample)
                except sqlite3.DatabaseError as e:
                    logger.debug('Failed to read sample rows from %s: %s', tname, e)

            # Option D: Column statistics
            col_stats = _compute_column_stats_sqlite(cursor, quoted, columns)

            tables.append({
                'table': tname,
                'columns': columns,
                'column_count': len(columns),
                'sample_rows': sample_rows,
                'sample_row_count': len(sample_rows),
                'row_count': row_count,
                'column_stats': col_stats,
            })

        conn.close()
        return tables
    except Exception:
        conn.close()
        return None


def _compute_column_stats_sqlite(cursor, quoted_table, columns):
    """Compute per-column statistics via SQLite (Option D).

    Returns a dict: ``{column_name: {distinct_count, min, max}}``.
    """
    stats = {}
    for col in columns:
        cname = col['name']
        try:
            cursor.execute(
                f'SELECT COUNT(DISTINCT "{cname}"), MIN("{cname}"), MAX("{cname}") '
                f'FROM {quoted_table}'
            )
            row = cursor.fetchone()
            if row:
                stats[cname] = {
                    'distinct_count': row[0],
                    'min': row[1],
                    'max': row[2],
                }
            else:
                stats[cname] = {}
        except sqlite3.DatabaseError:
            stats[cname] = {}
    return stats


# ── Header-region text scanning fallback ────────────────────────────

def _read_hyper_header(raw_bytes, max_rows=20):
    """Fall back to scanning the binary header for CREATE TABLE + INSERT.

    This is the same heuristic used by ``extract_hyper_metadata()`` in
    ``extract_tableau_data.py``, pulled into a reusable function.

    Returns:
        list[dict] | None: Same shape as ``_read_hyper_sqlite``, or ``None``.
    """
    scan_limit = min(262_144, len(raw_bytes))
    try:
        text_chunk = raw_bytes[:scan_limit].decode('utf-8', errors='replace')
    except (UnicodeDecodeError, AttributeError):
        return None

    creates = re.findall(
        r'CREATE\s+TABLE\s+"?([^"\s(]+)"?\s*\(([^)]+)\)',
        text_chunk, re.IGNORECASE,
    )
    if not creates:
        return None

    tables = []
    for tname, cols_str in creates:
        columns = []
        for col_def in cols_str.split(','):
            col_def = col_def.strip()
            parts = col_def.split()
            if len(parts) >= 2:
                cname = parts[0].strip('"')
                ctype = ' '.join(parts[1:]).lower()
                columns.append({'name': cname, 'hyper_type': ctype})

        # Look for INSERT rows
        sample_rows = _parse_inserts(text_chunk, tname, columns, max_rows)

        tables.append({
            'table': tname,
            'columns': columns,
            'column_count': len(columns),
            'sample_rows': sample_rows,
            'sample_row_count': len(sample_rows),
            'row_count': len(sample_rows),  # best-effort
        })
    return tables


def _parse_inserts(text, table_name, columns, max_rows):
    """Extract sample rows from INSERT INTO statements in text."""
    samples = []
    pattern = re.compile(
        rf'INSERT\s+INTO\s+"?{re.escape(table_name)}"?\s+VALUES\s*',
        re.IGNORECASE,
    )
    for m in pattern.finditer(text):
        rest = text[m.end():]
        # Parse value tuples: (v1, v2), (v3, v4), ...
        for tm in re.finditer(r'\(([^)]+)\)', rest):
            if len(samples) >= max_rows:
                break
            parts = _split_values(tm.group(1))
            row = {}
            for i, col in enumerate(columns):
                val = parts[i].strip().strip("'") if i < len(parts) else None
                if val == 'NULL':
                    val = None
                row[col['name']] = val
            samples.append(row)
        if len(samples) >= max_rows:
            break
    return samples


def _split_values(s):
    """Split a SQL VALUES tuple respecting quoted strings."""
    result = []
    current = []
    in_quote = False
    for ch in s:
        if ch == "'" and not in_quote:
            in_quote = True
            current.append(ch)
        elif ch == "'" and in_quote:
            in_quote = False
            current.append(ch)
        elif ch == ',' and not in_quote:
            result.append(''.join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        result.append(''.join(current).strip())
    return result


# ── Public API ──────────────────────────────────────────────────────

def read_hyper(file_path, max_rows=20):
    """Read schema and sample data from a ``.hyper`` file.

    Reader chain: tableauhyperapi → SQLite → header scan.

    Args:
        file_path: Path to the ``.hyper`` file.
        max_rows: Max sample rows per table (configurable via ``--hyper-rows``).

    Returns:
        dict with keys:
            ``tables`` — list of table dicts (see ``_read_hyper_sqlite``),
            ``format`` — ``'hyper_api'`` | ``'sqlite'`` | ``'hyper'`` | ``'unknown'``,
            ``file_path`` — original path,
            ``metadata`` — file-level metadata (size, mtime).
        Returns empty ``tables`` list on failure.
    """
    result = {
        'file_path': file_path,
        'tables': [],
        'format': 'unknown',
        'metadata': {},
    }

    if not file_path or not os.path.isfile(file_path):
        return result

    # Option D: File-level metadata
    try:
        stat = os.stat(file_path)
        result['metadata'] = {
            'file_size_bytes': stat.st_size,
            'last_modified': stat.st_mtime,
        }
    except OSError:
        pass

    # Detect format from magic bytes
    try:
        with open(file_path, 'rb') as f:
            magic = f.read(16)
    except OSError:
        return result

    if magic[:6] == b'SQLite':
        result['format'] = 'sqlite'
    elif magic[:4] == b'HyPe':
        result['format'] = 'hyper'

    # Option A: Try tableauhyperapi first (handles all formats)
    tables = _read_hyper_api(file_path, max_rows=max_rows)
    if tables:
        result['tables'] = tables
        result['format'] = 'hyper_api'
        return result

    # Try SQLite (with multi-schema support)
    tables = _read_hyper_sqlite(file_path, max_rows=max_rows)
    if tables:
        result['tables'] = tables
        if result['format'] == 'unknown':
            result['format'] = 'sqlite'
        return result

    # Fall back to header scan
    try:
        with open(file_path, 'rb') as f:
            raw = f.read()
        tables = _read_hyper_header(raw, max_rows=max_rows)
        if tables:
            result['tables'] = tables
            if result['format'] == 'unknown':
                result['format'] = 'hyper'
    except OSError as e:
        logger.debug('Hyper header scan failed for %s: %s', file_path, e)

    return result


def read_hyper_from_twbx(twbx_path, hyper_filename=None, max_rows=20):
    """Extract and read ``.hyper`` file(s) from a ``.twbx`` archive.

    Args:
        twbx_path: Path to the ``.twbx`` (or ``.tdsx``) file.
        hyper_filename: Optional — specific ``.hyper`` entry name to read.
            If ``None``, reads all ``.hyper`` entries.
        max_rows: Max sample rows per table.

    Returns:
        list[dict]: One ``read_hyper()`` result per ``.hyper`` entry found.
    """
    results = []
    if not twbx_path or not os.path.isfile(twbx_path):
        return results

    try:
        with zipfile.ZipFile(twbx_path, 'r') as z:
            entries = [
                name for name in z.namelist()
                if name.lower().endswith('.hyper')
            ]
            if hyper_filename:
                entries = [
                    e for e in entries
                    if os.path.basename(e).lower() == hyper_filename.lower()
                    or e.lower().endswith(hyper_filename.lower())
                ]

            for entry_name in entries:
                # Extract to temp file for sqlite3.connect()
                raw = z.read(entry_name)
                with tempfile.NamedTemporaryFile(
                    suffix='.hyper', delete=False
                ) as tmp:
                    tmp.write(raw)
                    tmp_path = tmp.name

                try:
                    hyper_data = read_hyper(tmp_path, max_rows=max_rows)
                    hyper_data['archive_path'] = entry_name
                    hyper_data['original_filename'] = os.path.basename(entry_name)
                    results.append(hyper_data)
                finally:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
    except (zipfile.BadZipFile, OSError, KeyError) as exc:
        logger.debug("Could not read hyper from archive: %s", exc)

    return results


# ── M expression generators ─────────────────────────────────────────

def generate_m_inline_table(table_info):
    """Generate a Power Query M ``#table()`` expression with inline data.

    Suitable for small extracts (< ~1000 rows).

    Args:
        table_info: dict with ``columns`` and ``sample_rows`` keys.

    Returns:
        str: M expression text.
    """
    columns = table_info.get('columns', [])
    rows = table_info.get('sample_rows', [])
    table_name = table_info.get('table', 'Extract')

    if not columns:
        return f'// No columns found for table "{table_name}"\n#table({{}}, {{}})'

    # Column type list: {{"ColName", type Text.Type}, ...}
    type_entries = []
    for col in columns:
        m_type = _m_type_for(col.get('hyper_type', 'text'))
        type_entries.append(f'{{"{col["name"]}", type {m_type}}}')
    type_list = ', '.join(type_entries)

    # Row data
    if not rows:
        return (
            f'let\n'
            f'    Source = #table(\n'
            f'        type table [{", ".join(f"[{c["name"]}]" for c in columns)}],\n'
            f'        {{}}\n'
            f'    )\n'
            f'in\n'
            f'    Source'
        )

    row_lines = []
    for row in rows:
        vals = []
        for col in columns:
            m_type = _m_type_for(col.get('hyper_type', 'text'))
            val = row.get(col['name'])
            vals.append(_m_literal(val, m_type))
        row_lines.append(f'        {{{", ".join(vals)}}}')
    rows_block = ',\n'.join(row_lines)

    return (
        f'let\n'
        f'    Source = #table(\n'
        f'        {{{type_list}}},\n'
        f'        {{\n{rows_block}\n'
        f'        }}\n'
        f'    )\n'
        f'in\n'
        f'    Source'
    )


def generate_m_csv_reference(table_info, csv_filename=None):
    """Generate a Power Query M ``Csv.Document()`` reference for large data.

    Used when the Hyper extract is too large to inline.

    Args:
        table_info: dict with ``columns`` and ``table`` keys.
        csv_filename: Optional CSV filename. If ``None``, derives from table name.

    Returns:
        str: M expression text.
    """
    columns = table_info.get('columns', [])
    table_name = table_info.get('table', 'Extract')
    fname = csv_filename or f'{table_name}.csv'

    col_type_entries = []
    for col in columns:
        m_type = _m_type_for(col.get('hyper_type', 'text'))
        col_type_entries.append(f'{{"{col["name"]}", type {m_type}}}')
    col_spec = f'{{{", ".join(col_type_entries)}}}'

    return (
        f'let\n'
        f'    // TODO: Update the file path to the exported CSV data\n'
        f'    Source = Csv.Document(\n'
        f'        File.Contents("{fname}"),\n'
        f'        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]\n'
        f'    ),\n'
        f'    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),\n'
        f'    #"Changed Types" = Table.TransformColumnTypes(\n'
        f'        #"Promoted Headers",\n'
        f'        {col_spec}\n'
        f'    )\n'
        f'in\n'
        f'    #"Changed Types"'
    )


# ── Threshold for inline vs CSV reference ───────────────────────────

INLINE_ROW_THRESHOLD = 500  # Below this → #table(), above → Csv.Document()


def generate_m_for_hyper_table(table_info, csv_filename=None, row_limit=None):
    """Auto-select inline or CSV M expression based on row count.

    Args:
        table_info: dict with ``columns``, ``sample_rows``, ``row_count``.
        csv_filename: Optional CSV filename for large tables.
        row_limit: Override for ``INLINE_ROW_THRESHOLD`` (from ``--hyper-rows``).

    Returns:
        str: M expression text.
    """
    threshold = row_limit if row_limit is not None else INLINE_ROW_THRESHOLD
    row_count = table_info.get('row_count', 0)
    if row_count <= threshold:
        return generate_m_inline_table(table_info)
    return generate_m_csv_reference(table_info, csv_filename)


# ── Metadata enrichment (Option D) ──────────────────────────────────

def get_hyper_metadata(file_path, max_rows=0):
    """Extract enriched metadata from a ``.hyper`` file for assessment.

    Returns a summary dict with:
    - ``total_rows``: Sum of row counts across all tables.
    - ``total_tables``: Number of tables in the file.
    - ``file_size_bytes``: File size on disk.
    - ``last_modified``: File modification timestamp.
    - ``tables``: Per-table detail (name, row_count, column_count, column_stats).
    - ``format``: Which reader succeeded.
    - ``recommendations``: List of actionable strings (e.g., DirectQuery hint).
    """
    data = read_hyper(file_path, max_rows=max_rows)
    tables = data.get('tables', [])
    total_rows = sum(t.get('row_count', 0) for t in tables)
    metadata = data.get('metadata', {})

    recommendations = []
    if total_rows > 10_000_000:
        recommendations.append(
            'Over 10M rows — consider DirectQuery mode instead of Import'
        )
    elif total_rows > 1_000_000:
        recommendations.append(
            'Over 1M rows — monitor model refresh times in Import mode'
        )

    for t in tables:
        col_stats = t.get('column_stats', {})
        for cname, st in col_stats.items():
            dc = st.get('distinct_count')
            if dc is not None and dc > 1_000_000:
                recommendations.append(
                    f'Column "{cname}" in "{t["table"]}" has {dc:,} distinct values '
                    f'— high cardinality may impact performance'
                )

    return {
        'file_path': file_path,
        'format': data.get('format', 'unknown'),
        'total_tables': len(tables),
        'total_rows': total_rows,
        'file_size_bytes': metadata.get('file_size_bytes', 0),
        'last_modified': metadata.get('last_modified'),
        'tables': [
            {
                'name': t.get('table', ''),
                'row_count': t.get('row_count', 0),
                'column_count': t.get('column_count', 0),
                'column_stats': t.get('column_stats', {}),
            }
            for t in tables
        ],
        'recommendations': recommendations,
    }
