"""Refresh schedule and subscription migration generator (Sprint 73).

Converts Tableau Server extract-refresh schedules and email subscriptions
to Power BI REST API configuration JSON.

Tableau schedule → PBI scheduled refresh
Tableau subscription → PBI subscription (alert/email)
"""

import logging
import re

logger = logging.getLogger(__name__)

# ── Frequency mapping ─────────────────────────────────────────────

FREQUENCY_MAP = {
    'Hourly': 'Daily',          # PBI minimum is daily for Pro
    'Daily': 'Daily',
    'Weekly': 'Weekly',
    'Monthly': 'Monthly',
}


def _parse_time(time_str):
    """Extract hour and minute from HH:MM or ISO time string.

    Returns:
        tuple: (hour, minute) or (0, 0) if parse fails.
    """
    if not time_str:
        return (0, 0)
    m = re.match(r'(\d{1,2}):(\d{2})', time_str)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return (0, 0)


def _map_weekday(tableau_day):
    """Map Tableau weekday name to PBI day index.

    PBI: Sunday=1, Monday=2, ..., Saturday=7.
    """
    mapping = {
        'Sunday': 1, 'Monday': 2, 'Tuesday': 3, 'Wednesday': 4,
        'Thursday': 5, 'Friday': 6, 'Saturday': 7,
    }
    return mapping.get(tableau_day, 2)  # default Monday


def generate_refresh_config(extract_tasks, schedules=None):
    """Generate PBI scheduled refresh configuration from Tableau extract tasks.

    Args:
        extract_tasks: list[dict] — Tableau extract tasks for a workbook.
            Each has: id, schedule (with frequency, time, weekDay), priority.
        schedules: list[dict] — optional full schedule objects for enrichment.

    Returns:
        dict: PBI refresh schedule config with:
            - enabled (bool)
            - frequency (str): Daily/Weekly/Monthly
            - days (list[str]): for Weekly
            - times (list[str]): UTC time slots
            - localTimeZoneId (str)
            - notifyOption (str)
            - notes (list[str]): migration warnings
    """
    if not extract_tasks:
        return {
            'enabled': False,
            'notes': ['No Tableau extract tasks found — refresh not configured.'],
        }

    schedule_lookup = {}
    if schedules:
        for s in schedules:
            sid = s.get('id', '')
            if sid:
                schedule_lookup[sid] = s

    times = []
    days = set()
    frequency = 'Daily'
    notes = []

    for task in extract_tasks:
        sched = task.get('schedule', {})
        if not sched and task.get('schedule_id') and schedule_lookup:
            sched = schedule_lookup.get(task['schedule_id'], {})

        freq_details = sched.get('frequencyDetails', sched)
        freq_type = sched.get('frequency', sched.get('type', 'Daily'))
        mapped_freq = FREQUENCY_MAP.get(freq_type, 'Daily')

        if freq_type == 'Hourly':
            notes.append(
                f'Tableau schedule "{sched.get("name", "?")}" is Hourly. '
                'Power BI Pro supports max 8×/day. Premium supports 48×/day. '
                'Mapped to Daily.'
            )

        frequency = mapped_freq

        # Extract time
        start_time = freq_details.get('start', freq_details.get('time', ''))
        intervals = freq_details.get('intervals', {})
        if isinstance(intervals, dict):
            hours = intervals.get('hours', [])
            weekdays = intervals.get('weekDay', [])
        elif isinstance(intervals, list):
            hours = []
            weekdays = []
            for iv in intervals:
                if 'hours' in iv:
                    hours.append(iv['hours'])
                if 'weekDay' in iv:
                    weekdays.append(iv['weekDay'])
        else:
            hours = []
            weekdays = []

        if start_time:
            h, m = _parse_time(start_time)
            times.append(f'{h:02d}:{m:02d}')
        for h in hours:
            try:
                times.append(f'{int(h):02d}:00')
            except (ValueError, TypeError):
                pass

        for wd in weekdays:
            if isinstance(wd, str):
                days.add(wd)

    # Deduplicate and sort times
    times = sorted(set(times)) or ['06:00']

    # PBI Pro: max 8 refresh times per day
    if len(times) > 8:
        notes.append(
            f'Tableau has {len(times)} refresh times. '
            'PBI Pro supports max 8/day — truncated. '
            'Use Premium for up to 48.'
        )
        times = times[:8]

    config = {
        'enabled': True,
        'frequency': frequency,
        'times': times,
        'localTimeZoneId': 'UTC',
        'notifyOption': 'MailOnFailure',
        'notes': notes,
    }

    if frequency == 'Weekly' and days:
        config['days'] = sorted(days)
    elif frequency == 'Weekly':
        config['days'] = ['Monday']

    return config


def generate_subscription_config(subscriptions):
    """Generate PBI subscription configuration from Tableau subscriptions.

    Args:
        subscriptions: list[dict] — Tableau subscription objects.
            Each has: id, subject, user (name, email), schedule, content.

    Returns:
        list[dict]: PBI-compatible subscription configs with:
            - title (str)
            - recipients (list[str])
            - frequency (str)
            - time (str)
            - enabled (bool)
            - notes (list[str])
    """
    if not subscriptions:
        return []

    results = []
    for sub in subscriptions:
        subject = sub.get('subject', sub.get('name', 'Untitled'))
        user = sub.get('user', {})
        email = user.get('email', user.get('name', ''))
        sched = sub.get('schedule', {})
        freq = sched.get('frequency', 'Daily')

        notes = []
        if freq == 'Hourly':
            notes.append(
                'Tableau subscription was Hourly — PBI subscriptions '
                'support Daily/Weekly/After Data Refresh.'
            )

        start_time = sched.get('frequencyDetails', {}).get(
            'start', sched.get('time', '08:00')
        )
        h, m = _parse_time(start_time)

        config = {
            'title': subject,
            'recipients': [email] if email else [],
            'frequency': FREQUENCY_MAP.get(freq, 'Daily'),
            'time': f'{h:02d}:{m:02d}',
            'enabled': True,
            'notes': notes,
        }
        results.append(config)

    return results


def generate_refresh_json(extract_tasks, subscriptions=None, schedules=None):
    """Generate combined refresh + subscription JSON artifact.

    Args:
        extract_tasks: Tableau extract tasks for a workbook.
        subscriptions: Tableau subscriptions for a workbook.
        schedules: Full schedule objects for enrichment.

    Returns:
        dict: Combined config with 'refresh' and 'subscriptions' keys.
    """
    refresh = generate_refresh_config(extract_tasks, schedules)
    subs = generate_subscription_config(subscriptions or [])

    return {
        'refresh': refresh,
        'subscriptions': subs,
        'migration_notes': [
            'Power BI Pro: max 8 refreshes/day. Premium: max 48/day.',
            'Verify gateway configuration for on-premises sources.',
            'Email subscriptions require recipients to have PBI Pro licenses.',
        ],
    }
