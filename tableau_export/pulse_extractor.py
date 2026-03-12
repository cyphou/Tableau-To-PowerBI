"""Tableau Pulse metric extractor.

Parses Tableau Pulse metric definitions from workbook XML (2024+).
Pulse metrics define KPIs with time grains, targets, and filters
that map to Power BI Goals/Scorecards.

Usage:
    metrics = extract_pulse_metrics(root)
    # Returns list of metric dicts ready for goals_generator
"""

import xml.etree.ElementTree as ET
import re
import logging

logger = logging.getLogger(__name__)

# Tableau Pulse time grain → PBI cadence mapping
_TIME_GRAIN_MAP = {
    'day': 'Daily',
    'week': 'Weekly',
    'month': 'Monthly',
    'quarter': 'Quarterly',
    'year': 'Yearly',
}


def extract_pulse_metrics(root):
    """Extract Tableau Pulse metric definitions from workbook XML.

    Pulse metrics appear in Tableau 2024+ workbooks as
    ``<metric>`` or ``<pulse-metric>`` elements.

    Args:
        root: ElementTree root of the .twb XML

    Returns:
        list of dicts with keys:
            name, description, measure_field, time_dimension,
            time_grain, aggregation, target_value, target_label,
            filters (list of {field, operator, values}),
            definition_formula, number_format
    """
    if root is None:
        return []

    metrics = []

    # Search for <metric> and <pulse-metric> elements
    metric_elements = (
        root.findall('.//metric') +
        root.findall('.//pulse-metric') +
        root.findall('.//metrics/metric')
    )

    seen_names = set()
    for elem in metric_elements:
        metric = _parse_metric_element(elem)
        if metric and metric['name'] not in seen_names:
            seen_names.add(metric['name'])
            metrics.append(metric)

    if metrics:
        logger.info("Extracted %d Pulse metrics", len(metrics))

    return metrics


def _parse_metric_element(elem):
    """Parse a single ``<metric>`` or ``<pulse-metric>`` XML element.

    Args:
        elem: ElementTree element

    Returns:
        dict or None if the element doesn't represent a valid metric
    """
    name = (
        elem.get('name', '') or
        elem.get('caption', '') or
        elem.findtext('.//name', '') or
        elem.findtext('.//caption', '')
    ).strip()

    if not name:
        return None

    description = (
        elem.get('description', '') or
        elem.findtext('.//description', '')
    ).strip()

    # Measure/KPI field
    measure_field = (
        elem.get('measure', '') or
        elem.get('column', '') or
        elem.findtext('.//measure', '') or
        elem.findtext('.//measure-field', '')
    ).strip().strip('[]')

    # Time dimension
    time_dim = (
        elem.get('time-dimension', '') or
        elem.findtext('.//time-dimension', '') or
        elem.findtext('.//date-column', '')
    ).strip().strip('[]')

    # Time grain
    time_grain_raw = (
        elem.get('time-grain', '') or
        elem.get('granularity', '') or
        elem.findtext('.//time-grain', '') or
        elem.findtext('.//granularity', '')
    ).strip().lower()
    time_grain = _TIME_GRAIN_MAP.get(time_grain_raw, 'Monthly')

    # Aggregation
    aggregation = (
        elem.get('aggregation', '') or
        elem.findtext('.//aggregation', '')
    ).strip().upper() or 'SUM'

    # Target
    target_value = None
    target_label = ''
    target_elem = elem.find('.//target')
    if target_elem is not None:
        target_label = target_elem.get('label', '') or target_elem.findtext('.//label', '')
        raw_val = target_elem.get('value', '') or target_elem.text or ''
        try:
            target_value = float(raw_val) if raw_val else None
        except (ValueError, TypeError):
            target_value = None

    # Definition formula (Tableau calculation)
    definition_formula = (
        elem.get('formula', '') or
        elem.findtext('.//formula', '') or
        elem.findtext('.//definition', '')
    ).strip()

    # Number format
    number_format = (
        elem.get('number-format', '') or
        elem.findtext('.//number-format', '')
    ).strip()

    # Filters
    filters = []
    for filt_elem in elem.findall('.//filter'):
        field = (filt_elem.get('column', '') or filt_elem.get('field', '')).strip('[]')
        operator = filt_elem.get('type', 'categorical')
        values = [v.text for v in filt_elem.findall('.//value') if v.text]
        if field:
            filters.append({
                'field': field,
                'operator': operator,
                'values': values,
            })

    return {
        'name': name,
        'description': description,
        'measure_field': measure_field,
        'time_dimension': time_dim,
        'time_grain': time_grain,
        'aggregation': aggregation,
        'target_value': target_value,
        'target_label': target_label,
        'filters': filters,
        'definition_formula': definition_formula,
        'number_format': number_format,
    }


def has_pulse_metrics(root):
    """Quick check: does this workbook contain any Pulse metric definitions?"""
    if root is None:
        return False
    return bool(
        root.findall('.//metric') or
        root.findall('.//pulse-metric') or
        root.findall('.//metrics/metric')
    )
