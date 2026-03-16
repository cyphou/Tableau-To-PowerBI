"""
Shared Semantic Model — Core Merge Engine.

Merges multiple Tableau workbook extractions into a single unified
semantic model, enabling the Power BI "thin report" pattern where
N reports reference one shared semantic model.

Pipeline:
    1. Build table fingerprints (connection + physical name)
    2. Detect merge candidates (tables appearing in multiple workbooks)
    3. Merge tables (column union), measures, relationships, parameters, RLS
    4. Return a single merged converted_objects dict

Usage (programmatic)::

    from powerbi_import.shared_model import assess_merge, merge_semantic_models

    assessment = assess_merge(all_extracted, workbook_names)
    merged = merge_semantic_models(all_extracted, assessment, "SharedModel")

Usage (CLI)::

    python migrate.py --shared-model wb1.twbx wb2.twbx --model-name "Sales Analytics"
"""

from __future__ import annotations

import copy
import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  Data classes
# ═══════════════════════════════════════════════════════════════════

@dataclass
class TableFingerprint:
    """Uniquely identifies a physical table across workbooks."""
    connection_type: str
    server: str
    database: str
    schema: str
    table_name: str

    def fingerprint(self) -> str:
        """Normalized hash key for matching."""
        raw = '|'.join([
            self.connection_type.lower().strip(),
            self.server.lower().strip(),
            self.database.lower().strip(),
            self.schema.lower().strip(),
            self.table_name.lower().strip(),
        ])
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]

    def __eq__(self, other):
        if not isinstance(other, TableFingerprint):
            return NotImplemented
        return self.fingerprint() == other.fingerprint()

    def __hash__(self):
        return hash(self.fingerprint())


@dataclass
class MergeCandidate:
    """A table that appears in multiple workbooks."""
    fingerprint: TableFingerprint
    table_name: str
    sources: List[Tuple[str, dict, dict]]  # [(workbook_name, table_dict, connection_dict)]
    column_overlap: float = 0.0
    conflicts: List[str] = field(default_factory=list)


@dataclass
class MeasureConflict:
    """A measure with the same name but different DAX across workbooks."""
    name: str
    table: str
    variants: Dict[str, str]  # {workbook_name: formula}


@dataclass
class MergeAssessment:
    """Complete analysis of merge feasibility."""
    workbooks: List[str]
    merge_candidates: List[MergeCandidate] = field(default_factory=list)
    unique_tables: Dict[str, List[str]] = field(default_factory=dict)
    measure_conflicts: List[MeasureConflict] = field(default_factory=list)
    measure_duplicates_removed: int = 0
    relationship_duplicates_removed: int = 0
    parameter_conflicts: List[dict] = field(default_factory=list)
    parameter_duplicates_removed: int = 0
    rls_conflicts: List[dict] = field(default_factory=list)
    total_tables: int = 0
    unique_table_count: int = 0
    merge_score: int = 0
    recommendation: str = "separate"

    def to_dict(self) -> dict:
        """Serialize to a JSON-friendly dictionary."""
        return {
            "workbooks": self.workbooks,
            "total_tables": self.total_tables,
            "unique_table_count": self.unique_table_count,
            "tables_saved": self.total_tables - self.unique_table_count,
            "merge_candidates": [
                {
                    "table_name": mc.table_name,
                    "workbooks": [s[0] for s in mc.sources],
                    "column_overlap": round(mc.column_overlap, 2),
                    "conflicts": mc.conflicts,
                }
                for mc in self.merge_candidates
            ],
            "unique_tables": self.unique_tables,
            "measure_conflicts": [
                {"name": mc.name, "table": mc.table, "variants": mc.variants}
                for mc in self.measure_conflicts
            ],
            "measure_duplicates_removed": self.measure_duplicates_removed,
            "relationship_duplicates_removed": self.relationship_duplicates_removed,
            "parameter_conflicts": self.parameter_conflicts,
            "parameter_duplicates_removed": self.parameter_duplicates_removed,
            "rls_conflicts": self.rls_conflicts,
            "merge_score": self.merge_score,
            "recommendation": self.recommendation,
        }


# ═══════════════════════════════════════════════════════════════════
#  Table fingerprinting
# ═══════════════════════════════════════════════════════════════════

_SCHEMA_PATTERN = re.compile(r'^\[?([^\]]*)\]?\.\[?([^\]]*)\]?$')


def _parse_table_name(raw_name: str) -> Tuple[str, str]:
    """Parse '[schema].[table]' or 'table' into (schema, table)."""
    m = _SCHEMA_PATTERN.match(raw_name.strip())
    if m:
        return m.group(1), m.group(2)
    # No schema prefix
    clean = raw_name.strip().strip('[]')
    return 'dbo', clean


def build_table_fingerprints(datasources: list) -> Dict[str, Tuple[TableFingerprint, dict, dict]]:
    """Build fingerprints for all tables in a workbook's datasources.

    Returns:
        {physical_table_name: (fingerprint, table_dict, connection_dict)}
    """
    result = {}
    for ds in datasources:
        conn = ds.get('connection', {})
        conn_type = conn.get('type', 'unknown')
        details = conn.get('details', {})
        server = details.get('server', details.get('host', ''))
        database = details.get('database', details.get('db', ''))

        for table in ds.get('tables', []):
            ttype = table.get('type', 'table')
            if ttype != 'table':
                continue
            raw_name = table.get('name', '')
            schema, tname = _parse_table_name(raw_name)
            fp = TableFingerprint(
                connection_type=conn_type,
                server=server,
                database=database,
                schema=schema,
                table_name=tname,
            )
            result[raw_name] = (fp, table, conn)
    return result


# ═══════════════════════════════════════════════════════════════════
#  Column overlap
# ═══════════════════════════════════════════════════════════════════

def compute_column_overlap(table_a: dict, table_b: dict) -> float:
    """Compute Jaccard similarity of column names between two tables.

    Returns:
        Float 0.0–1.0 representing column name overlap.
    """
    cols_a = {c.get('name', '').lower() for c in table_a.get('columns', [])}
    cols_b = {c.get('name', '').lower() for c in table_b.get('columns', [])}

    if not cols_a and not cols_b:
        return 0.0

    intersection = cols_a & cols_b
    union = cols_a | cols_b

    if not union:
        return 0.0

    return len(intersection) / len(union)


# ═══════════════════════════════════════════════════════════════════
#  Merge assessment
# ═══════════════════════════════════════════════════════════════════

def assess_merge(all_extracted: List[dict],
                 workbook_names: List[str]) -> MergeAssessment:
    """Analyze multiple extracted workbook datasets for merge potential.

    Args:
        all_extracted: List of converted_objects dicts (one per workbook)
        workbook_names: List of workbook names (parallel with all_extracted)

    Returns:
        MergeAssessment with full analysis.
    """
    assessment = MergeAssessment(workbooks=list(workbook_names))

    # 1. Build fingerprints for all tables in all workbooks
    # fingerprint_hash → [(workbook_name, table_dict, connection_dict, raw_table_name)]
    fp_map: Dict[str, list] = {}
    all_table_count = 0

    for wb_name, extracted in zip(workbook_names, all_extracted):
        datasources = extracted.get('datasources', [])
        fps = build_table_fingerprints(datasources)
        for raw_name, (fp, table, conn) in fps.items():
            all_table_count += 1
            fp_hash = fp.fingerprint()
            if fp_hash not in fp_map:
                fp_map[fp_hash] = []
            fp_map[fp_hash].append((wb_name, table, conn, raw_name, fp))

    assessment.total_tables = all_table_count

    # 2. Identify merge candidates (tables appearing in 2+ workbooks)
    seen_tables = set()
    unique_per_workbook: Dict[str, List[str]] = {wb: [] for wb in workbook_names}

    for fp_hash, entries in fp_map.items():
        unique_wbs = {e[0] for e in entries}
        table_name = entries[0][3]  # raw_name from first entry
        fp = entries[0][4]

        if len(unique_wbs) >= 2:
            # Compute column overlap (pairwise — use first pair)
            overlap = 1.0
            if len(entries) >= 2:
                overlap = compute_column_overlap(entries[0][1], entries[1][1])

            # Check for column type conflicts
            conflicts = _detect_column_conflicts(entries)

            candidate = MergeCandidate(
                fingerprint=fp,
                table_name=table_name,
                sources=[(e[0], e[1], e[2]) for e in entries],
                column_overlap=overlap,
                conflicts=conflicts,
            )
            assessment.merge_candidates.append(candidate)
            seen_tables.add(fp_hash)
        else:
            # Unique to one workbook
            wb_name = entries[0][0]
            unique_per_workbook[wb_name].append(table_name)

    assessment.unique_tables = {
        wb: tables for wb, tables in unique_per_workbook.items() if tables
    }
    assessment.unique_table_count = (
        len(assessment.merge_candidates) +
        sum(len(v) for v in assessment.unique_tables.values())
    )

    # 3. Detect measure conflicts
    measure_conflicts, measure_dupes = _detect_measure_conflicts(all_extracted, workbook_names)
    assessment.measure_conflicts = measure_conflicts
    assessment.measure_duplicates_removed = measure_dupes

    # 4. Detect relationship duplicates
    assessment.relationship_duplicates_removed = _count_relationship_duplicates(
        all_extracted
    )

    # 5. Detect parameter conflicts
    param_conflicts, param_dupes = _detect_parameter_conflicts(all_extracted, workbook_names)
    assessment.parameter_conflicts = param_conflicts
    assessment.parameter_duplicates_removed = param_dupes

    # 6. Calculate merge score
    assessment.merge_score = calculate_merge_score(assessment)

    # 7. Set recommendation
    if assessment.merge_score >= 60:
        assessment.recommendation = "merge"
    elif assessment.merge_score >= 30:
        assessment.recommendation = "partial"
    else:
        assessment.recommendation = "separate"

    return assessment


def _detect_column_conflicts(entries: list) -> List[str]:
    """Detect column type mismatches across workbook instances of the same table."""
    conflicts = []
    # Build col_name → {wb_name: datatype}
    col_types: Dict[str, Dict[str, str]] = {}
    for wb_name, table, _conn, _raw, _fp in entries:
        for col in table.get('columns', []):
            cname = col.get('name', '')
            dtype = col.get('datatype', 'string')
            if cname not in col_types:
                col_types[cname] = {}
            col_types[cname][wb_name] = dtype

    for cname, wb_types in col_types.items():
        unique_types = set(wb_types.values())
        if len(unique_types) > 1:
            conflicts.append(
                f"Column '{cname}': type mismatch — " +
                ", ".join(f"{wb}={dt}" for wb, dt in wb_types.items())
            )

    return conflicts


def _detect_measure_conflicts(
    all_extracted: List[dict], workbook_names: List[str]
) -> Tuple[List[MeasureConflict], int]:
    """Detect measure conflicts and count deduplicatable measures."""
    # measure_key (name, datasource) → {wb_name: formula}
    measure_map: Dict[Tuple[str, str], Dict[str, str]] = {}

    for wb_name, extracted in zip(workbook_names, all_extracted):
        for ds in extracted.get('datasources', []):
            ds_name = ds.get('name', '')
            for calc in ds.get('calculations', []):
                role = calc.get('role', 'measure')
                if role != 'measure':
                    continue
                caption = calc.get('caption', calc.get('name', ''))
                formula = calc.get('formula', '').strip()
                key = (caption, ds_name)
                if key not in measure_map:
                    measure_map[key] = {}
                measure_map[key][wb_name] = formula

        # Also check standalone calculations
        for calc in extracted.get('calculations', []):
            role = calc.get('role', 'measure')
            if role != 'measure':
                continue
            caption = calc.get('caption', calc.get('name', ''))
            formula = calc.get('formula', '').strip()
            ds_name = calc.get('datasource_name', '')
            key = (caption, ds_name)
            if key not in measure_map:
                measure_map[key] = {}
            measure_map[key][wb_name] = formula

    conflicts = []
    duplicates = 0

    for (name, ds_name), wb_formulas in measure_map.items():
        if len(wb_formulas) <= 1:
            continue
        unique_formulas = set(wb_formulas.values())
        if len(unique_formulas) == 1:
            duplicates += 1
        else:
            conflicts.append(MeasureConflict(
                name=name, table=ds_name, variants=wb_formulas
            ))

    return conflicts, duplicates


def _count_relationship_duplicates(all_extracted: List[dict]) -> int:
    """Count relationship definitions that appear in multiple workbooks."""
    rel_keys = set()
    duplicates = 0
    for extracted in all_extracted:
        for ds in extracted.get('datasources', []):
            for rel in ds.get('relationships', []):
                key = _relationship_key(rel)
                if key in rel_keys:
                    duplicates += 1
                else:
                    rel_keys.add(key)
    return duplicates


def _relationship_key(rel: dict) -> Tuple[str, str, str, str]:
    """Deduplicate key for a relationship."""
    # Handle different relationship formats
    if 'left' in rel:
        return (
            rel['left'].get('table', '').lower(),
            rel['left'].get('column', '').lower(),
            rel['right'].get('table', '').lower(),
            rel['right'].get('column', '').lower(),
        )
    return (
        rel.get('from_table', '').lower(),
        rel.get('from_column', '').lower(),
        rel.get('to_table', '').lower(),
        rel.get('to_column', '').lower(),
    )


def _detect_parameter_conflicts(
    all_extracted: List[dict], workbook_names: List[str]
) -> Tuple[List[dict], int]:
    """Detect parameter conflicts and count deduplicatable parameters."""
    param_map: Dict[str, Dict[str, dict]] = {}
    for wb_name, extracted in zip(workbook_names, all_extracted):
        for param in extracted.get('parameters', []):
            pname = param.get('name', param.get('caption', ''))
            if pname not in param_map:
                param_map[pname] = {}
            param_map[pname][wb_name] = param

    conflicts = []
    duplicates = 0

    for pname, wb_params in param_map.items():
        if len(wb_params) <= 1:
            continue
        # Compare domain_type and datatype
        signatures = set()
        for wb, p in wb_params.items():
            sig = (p.get('datatype', ''), p.get('domain_type', ''),
                   str(p.get('current_value', '')))
            signatures.add(sig)
        if len(signatures) == 1:
            duplicates += 1
        else:
            conflicts.append({
                "name": pname,
                "variants": {
                    wb: {
                        "datatype": p.get('datatype'),
                        "domain_type": p.get('domain_type'),
                        "current_value": p.get('current_value'),
                    }
                    for wb, p in wb_params.items()
                },
            })

    return conflicts, duplicates


# ═══════════════════════════════════════════════════════════════════
#  Merge score
# ═══════════════════════════════════════════════════════════════════

def calculate_merge_score(assessment: MergeAssessment) -> int:
    """Calculate a 0-100 merge score.

    Dimensions:
        - Table overlap ratio (0-40 points)
        - Column match quality (0-20 points)
        - Measure conflict ratio (0-20 points)
        - Connection homogeneity (0-20 points)
    """
    score = 0

    # 1. Table overlap (0-40)
    if assessment.total_tables > 0:
        tables_saved = assessment.total_tables - assessment.unique_table_count
        overlap_ratio = tables_saved / assessment.total_tables
        score += int(overlap_ratio * 40)

    # 2. Column match quality (0-20)
    if assessment.merge_candidates:
        avg_overlap = sum(
            mc.column_overlap for mc in assessment.merge_candidates
        ) / len(assessment.merge_candidates)
        score += int(avg_overlap * 20)

    # 3. Measure conflict ratio (0-20) — fewer conflicts = higher score
    total_measures = (
        assessment.measure_duplicates_removed + len(assessment.measure_conflicts)
    )
    if total_measures > 0:
        clean_ratio = assessment.measure_duplicates_removed / total_measures
        score += int(clean_ratio * 20)
    else:
        score += 20  # No measures = no conflicts

    # 4. Connection homogeneity (0-20)
    if assessment.merge_candidates:
        conn_types = set()
        for mc in assessment.merge_candidates:
            conn_types.add(mc.fingerprint.connection_type.lower())
        if len(conn_types) == 1:
            score += 20
        elif len(conn_types) == 2:
            score += 10
        else:
            score += 5

    return min(score, 100)


# ═══════════════════════════════════════════════════════════════════
#  Semantic model merging
# ═══════════════════════════════════════════════════════════════════

def merge_semantic_models(all_extracted: List[dict],
                          assessment: MergeAssessment,
                          model_name: str) -> dict:
    """Merge multiple workbook extractions into a single unified dataset.

    Returns:
        A single converted_objects dict with merged datasources, calculations,
        parameters, relationships, etc. suitable for tmdl_generator.generate_tmdl().
    """
    merged = {
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

    workbook_names = assessment.workbooks

    # 1. Merge datasources (table-level deduplication)
    merged_datasource = _merge_datasources(
        all_extracted, workbook_names, assessment
    )
    merged['datasources'] = [merged_datasource]

    # 2. Merge calculations with conflict resolution
    merged['calculations'] = _merge_calculations(
        all_extracted, workbook_names, assessment
    )

    # 3. Merge parameters
    merged['parameters'] = _merge_parameters(all_extracted, workbook_names)

    # 4. Merge remaining objects (union, deduplicated by name)
    for key in ('sets', 'groups', 'bins', 'hierarchies', 'sort_orders',
                'custom_sql', 'user_filters', 'filters', 'stories', 'actions'):
        merged[key] = _merge_list_by_name(all_extracted, key)

    # 5. Merge aliases
    for extracted in all_extracted:
        aliases = extracted.get('aliases', {})
        if isinstance(aliases, dict):
            merged['aliases'].update(aliases)

    # 6. Collect all worksheets and dashboards (kept per-workbook for thin reports)
    for extracted in all_extracted:
        merged['worksheets'].extend(extracted.get('worksheets', []))
        merged['dashboards'].extend(extracted.get('dashboards', []))

    return merged


def _merge_datasources(all_extracted: List[dict],
                       workbook_names: List[str],
                       assessment: MergeAssessment) -> dict:
    """Merge all datasources into a single unified datasource.

    Tables are deduplicated by fingerprint. Columns are unioned.
    Relationships are deduplicated.
    """
    merged_ds = {
        'name': 'SharedModel',
        'caption': 'Shared Semantic Model',
        'connection': {},
        'connection_map': {},
        'tables': [],
        'columns': [],
        'calculations': [],
        'relationships': [],
    }

    # Track which tables have been added (by fingerprint hash)
    added_tables: Dict[str, dict] = {}  # fp_hash → merged_table

    # Track relationships for deduplication
    rel_keys_seen = set()

    for wb_name, extracted in zip(workbook_names, all_extracted):
        for ds in extracted.get('datasources', []):
            # Adopt connection info from first datasource
            if not merged_ds['connection']:
                merged_ds['connection'] = copy.deepcopy(ds.get('connection', {}))

            # Merge connection_map entries
            for k, v in ds.get('connection_map', {}).items():
                if k not in merged_ds['connection_map']:
                    merged_ds['connection_map'][k] = copy.deepcopy(v)

            # Process tables
            fps = build_table_fingerprints([ds])
            for raw_name, (fp, table, _conn) in fps.items():
                fp_hash = fp.fingerprint()
                if fp_hash in added_tables:
                    # Merge columns into existing table
                    _merge_columns_into(added_tables[fp_hash], table)
                else:
                    # Add new table
                    merged_table = copy.deepcopy(table)
                    added_tables[fp_hash] = merged_table
                    merged_ds['tables'].append(merged_table)

            # Merge relationships (deduplicate)
            for rel in ds.get('relationships', []):
                key = _relationship_key(rel)
                if key not in rel_keys_seen:
                    rel_keys_seen.add(key)
                    merged_ds['relationships'].append(copy.deepcopy(rel))

            # Merge datasource-level calculations
            for calc in ds.get('calculations', []):
                merged_ds['calculations'].append(copy.deepcopy(calc))

    return merged_ds


def _merge_columns_into(existing_table: dict, new_table: dict):
    """Merge columns from new_table into existing_table (union).

    Existing columns are kept. New columns not in existing are added.
    Type conflicts: wider type wins (string > real > integer).
    """
    existing_cols = {c.get('name', '').lower(): c
                     for c in existing_table.get('columns', [])}

    for col in new_table.get('columns', []):
        col_name = col.get('name', '').lower()
        if col_name in existing_cols:
            # Resolve type conflicts — wider type wins
            existing_type = existing_cols[col_name].get('datatype', 'string')
            new_type = col.get('datatype', 'string')
            if _type_width(new_type) > _type_width(existing_type):
                existing_cols[col_name]['datatype'] = new_type
            # Merge metadata: unhide if unhidden in any workbook
            if not col.get('hidden', False):
                existing_cols[col_name]['hidden'] = False
            # Take first non-empty semantic_role
            if col.get('semantic_role') and not existing_cols[col_name].get('semantic_role'):
                existing_cols[col_name]['semantic_role'] = col['semantic_role']
            # Take first non-empty format
            if col.get('default_format') and not existing_cols[col_name].get('default_format'):
                existing_cols[col_name]['default_format'] = col['default_format']
        else:
            existing_table.setdefault('columns', []).append(copy.deepcopy(col))
            existing_cols[col_name] = existing_table['columns'][-1]


_TYPE_WIDTH = {
    'boolean': 1,
    'integer': 2,
    'real': 3,
    'currency': 3,
    'datetime': 4,
    'string': 5,
}


def _type_width(dtype: str) -> int:
    """Return a width score for type conflict resolution."""
    return _TYPE_WIDTH.get(dtype.lower(), 5)


def _merge_calculations(all_extracted: List[dict],
                         workbook_names: List[str],
                         assessment: MergeAssessment) -> list:
    """Merge calculations with conflict resolution.

    Same name + same formula → keep one.
    Same name + different formula → namespace with workbook suffix.
    """
    # Build conflict set for fast lookup
    conflict_names = {mc.name for mc in assessment.measure_conflicts}

    # Collect all calculations
    seen: Dict[str, Tuple[str, dict]] = {}  # caption → (formula, calc_dict)
    result = []

    for wb_name, extracted in zip(workbook_names, all_extracted):
        for calc in extracted.get('calculations', []):
            caption = calc.get('caption', calc.get('name', ''))
            formula = calc.get('formula', '').strip()

            if caption in conflict_names:
                # Namespace it
                namespaced = copy.deepcopy(calc)
                new_caption = f"{caption} ({wb_name})"
                namespaced['caption'] = new_caption
                namespaced['_original_caption'] = caption
                namespaced['_source_workbook'] = wb_name
                result.append(namespaced)
            elif caption in seen:
                # Already seen — skip duplicate
                continue
            else:
                seen[caption] = (formula, calc)
                result.append(copy.deepcopy(calc))

    return result


def _merge_parameters(all_extracted: List[dict],
                      workbook_names: List[str]) -> list:
    """Merge parameters. Same name+type+default → deduplicate. Conflicts → namespace."""
    param_map: Dict[str, List[Tuple[str, dict]]] = {}

    for wb_name, extracted in zip(workbook_names, all_extracted):
        for param in extracted.get('parameters', []):
            pname = param.get('name', param.get('caption', ''))
            if pname not in param_map:
                param_map[pname] = []
            param_map[pname].append((wb_name, param))

    result = []
    for pname, entries in param_map.items():
        if len(entries) == 1:
            result.append(copy.deepcopy(entries[0][1]))
        else:
            # Check if all identical
            sigs = set()
            for wb, p in entries:
                sig = (p.get('datatype', ''), p.get('domain_type', ''),
                       str(p.get('current_value', '')))
                sigs.add(sig)
            if len(sigs) == 1:
                result.append(copy.deepcopy(entries[0][1]))
            else:
                # Namespace each
                for wb, p in entries:
                    namespaced = copy.deepcopy(p)
                    namespaced['name'] = f"{pname} ({wb})"
                    namespaced['caption'] = f"{pname} ({wb})"
                    namespaced['_source_workbook'] = wb
                    result.append(namespaced)

    return result


def _merge_list_by_name(all_extracted: List[dict], key: str) -> list:
    """Merge a list-type object by deduplicating on 'name' field."""
    seen_names = set()
    result = []
    for extracted in all_extracted:
        items = extracted.get(key, [])
        if not isinstance(items, list):
            continue
        for item in items:
            name = item.get('name', '')
            if name and name in seen_names:
                continue
            if name:
                seen_names.add(name)
            result.append(copy.deepcopy(item))
    return result


# ═══════════════════════════════════════════════════════════════════
#  Field remapping — for thin reports referencing namespaced measures
# ═══════════════════════════════════════════════════════════════════

def build_field_mapping(assessment: MergeAssessment,
                        workbook_name: str) -> Dict[str, str]:
    """Build a field name mapping for a specific workbook's thin report.

    Maps original measure names to their namespaced versions (if conflicts exist).

    Args:
        assessment: The merge assessment.
        workbook_name: Which workbook's report we're generating.

    Returns:
        {original_name: namespaced_name} — only for conflicting measures.
    """
    mapping = {}
    for conflict in assessment.measure_conflicts:
        if workbook_name in conflict.variants:
            mapping[conflict.name] = f"{conflict.name} ({workbook_name})"
    return mapping
