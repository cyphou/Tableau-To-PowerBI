"""Power BI Goals/Scorecard JSON generator.

Converts Tableau Pulse metrics into Fabric Scorecard API-compatible
JSON artifacts for manual import into a Power BI workspace.

Usage:
    from goals_generator import generate_goals_json, write_goals_artifact
    goals = generate_goals_json(pulse_metrics, report_name)
    write_goals_artifact(goals, output_dir)
"""

import json
import os
import uuid
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# PBI Goals cadence → refresh schedule hint
_CADENCE_REFRESH = {
    'Daily': 'P1D',
    'Weekly': 'P7D',
    'Monthly': 'P1M',
    'Quarterly': 'P3M',
    'Yearly': 'P1Y',
}


def generate_goals_json(pulse_metrics, report_name='Report',
                        workspace_id=None):
    """Convert Tableau Pulse metrics to PBI Goals/Scorecard JSON.

    Generates a Fabric Scorecard API-compatible JSON artifact that
    can be manually imported into a Power BI workspace.

    Args:
        pulse_metrics: List of metric dicts from pulse_extractor
        report_name: Name of the report (used as scorecard name)
        workspace_id: Optional Fabric workspace ID

    Returns:
        dict: Scorecard JSON ready for serialization or API upload
    """
    if not pulse_metrics:
        return None

    scorecard_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    goals = []
    for idx, metric in enumerate(pulse_metrics):
        goal = _build_goal(metric, idx, scorecard_id)
        if goal:
            goals.append(goal)

    scorecard = {
        'id': scorecard_id,
        'name': f'{report_name} Scorecard',
        'description': f'Migrated from Tableau Pulse — {len(goals)} goals',
        'createdTime': now,
        'lastModifiedTime': now,
        'goals': goals,
    }

    if workspace_id:
        scorecard['workspaceId'] = workspace_id

    return scorecard


def _build_goal(metric, ordinal, scorecard_id):
    """Convert a single Pulse metric into a PBI Goal definition.

    Args:
        metric: dict from pulse_extractor
        ordinal: ordering index
        scorecard_id: parent scorecard UUID

    Returns:
        dict: Goal definition
    """
    name = metric.get('name', '')
    if not name:
        return None

    goal_id = str(uuid.uuid4())
    cadence = metric.get('time_grain', 'Monthly')

    goal = {
        'id': goal_id,
        'scorecardId': scorecard_id,
        'name': name,
        'description': metric.get('description', ''),
        'ordinal': ordinal,
        'cadence': cadence,
        'refreshSchedule': _CADENCE_REFRESH.get(cadence, 'P1M'),
    }

    # Target value
    target_value = metric.get('target_value')
    if target_value is not None:
        goal['target'] = {
            'value': target_value,
            'label': metric.get('target_label', ''),
        }

    # Connected measure reference
    measure_field = metric.get('measure_field', '')
    aggregation = metric.get('aggregation', 'SUM')
    if measure_field:
        goal['connectedMeasure'] = {
            'measure': measure_field,
            'aggregation': aggregation,
        }

    # Time dimension
    time_dim = metric.get('time_dimension', '')
    if time_dim:
        goal['timeDimension'] = time_dim

    # Filters → goal status rules
    filters = metric.get('filters', [])
    if filters:
        goal['filters'] = [
            {
                'field': f.get('field', ''),
                'operator': f.get('operator', 'In'),
                'values': f.get('values', []),
            }
            for f in filters
        ]

    # Number format
    number_format = metric.get('number_format', '')
    if number_format:
        goal['numberFormat'] = number_format

    # Migration note
    goal['annotations'] = [{
        'name': 'MigrationNote',
        'value': (
            f'Migrated from Tableau Pulse metric "{name}". '
            f'Aggregation: {aggregation}. '
            f'Connect to a Power BI dataset measure for live updates.'
        ),
    }]

    return goal


def write_goals_artifact(scorecard, output_dir):
    """Write scorecard JSON to the output directory.

    Creates a ``goals/`` subfolder with the scorecard JSON file.

    Args:
        scorecard: Scorecard dict from generate_goals_json()
        output_dir: Base output directory (e.g. the .pbip project folder)

    Returns:
        str: Path to the written JSON file, or None if no scorecard
    """
    if not scorecard:
        return None

    goals_dir = os.path.join(output_dir, 'goals')
    os.makedirs(goals_dir, exist_ok=True)

    filename = 'scorecard.json'
    filepath = os.path.join(goals_dir, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(scorecard, f, indent=2, ensure_ascii=False)

    logger.info("Goals scorecard written to %s (%d goals)",
                filepath, len(scorecard.get('goals', [])))
    return filepath
