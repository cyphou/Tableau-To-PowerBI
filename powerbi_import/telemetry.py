"""
Optional anonymous usage telemetry for the TableauToPowerBI migration tool.

Collects anonymous, aggregate migration statistics to help improve the tool.
**Disabled by default** — opt-in via ``--telemetry`` CLI flag or
``TTPBI_TELEMETRY=1`` environment variable.

No personally identifiable information (PII) is ever collected.
No workbook content, file paths, or server names are transmitted.

Data collected (when enabled):
    - Migration duration (seconds)
    - Object counts (tables, columns, measures, visuals, pages)
    - Error counts by category
    - Python version
    - Platform (win32 / linux / darwin)
    - Tool version

Data is written to a local JSON log file (``~/.ttpbi_telemetry.json``)
and can optionally be sent to a configurable endpoint.
"""

import json
import os
import sys
import time
import uuid
import platform
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Telemetry version — bump when schema changes
# v3 (Sprint 131): adds 'decisions' and 'validations' buckets for
# per-conversion-branch and per-gate observability.
TELEMETRY_VERSION = 3

# Default local log location
DEFAULT_LOG_PATH = os.path.join(
    os.path.expanduser('~'), '.ttpbi_telemetry.json'
)


def is_telemetry_enabled():
    """Check if telemetry is enabled via environment variable.

    Returns:
        bool: True if ``TTPBI_TELEMETRY`` is set to ``1``, ``true``, or ``yes``.
    """
    val = os.environ.get('TTPBI_TELEMETRY', '').lower().strip()
    return val in ('1', 'true', 'yes')


class TelemetryCollector:
    """Collects and records anonymous migration metrics.

    Usage::

        t = TelemetryCollector()
        t.start()
        # ... run migration ...
        t.record_stats(tables=5, columns=20, measures=10)
        t.record_error('dax_conversion', 'ZN not converted')
        t.finish()
        t.save()
    """

    def __init__(self, enabled=None, log_path=None, endpoint=None):
        """Initialize the telemetry collector.

        Args:
            enabled: Override enabled state (None = check env var).
            log_path: Path to local JSON log file.
            endpoint: Optional HTTP endpoint URL for remote telemetry.
        """
        if enabled is None:
            enabled = is_telemetry_enabled()
        self.enabled = enabled
        self.log_path = log_path or DEFAULT_LOG_PATH
        self.endpoint = endpoint or os.environ.get('TTPBI_TELEMETRY_ENDPOINT', '')
        self._session_id = str(uuid.uuid4())[:8]
        self._start_time = None
        self._data = {
            'telemetry_version': TELEMETRY_VERSION,
            'session_id': self._session_id,
            'timestamp': None,
            'duration_seconds': None,
            'python_version': platform.python_version(),
            'platform': sys.platform,
            'tool_version': self._get_tool_version(),
            'stats': {},
            'errors': [],
            'events': [],
            # Sprint 131.1: per-decision counter (category → choice → count)
            'decisions': {},
            # Sprint 131.2: per-gate validation counter
            #   {gate: {pass: N, fail: N, repaired: N, by_issue: {category: N}}}
            'validations': {},
        }

    def start(self):
        """Record the start time of a migration."""
        self._start_time = time.time()
        self._data['timestamp'] = datetime.now().isoformat()

    def record_stats(self, **kwargs):
        """Record migration statistics.

        Args:
            **kwargs: Arbitrary stat key-value pairs (e.g., tables=5).
        """
        if not self.enabled:
            return
        self._data['stats'].update(kwargs)

    def record_error(self, category, message=''):
        """Record an error occurrence (category only, no PII).

        Args:
            category: Error category (e.g., 'dax_conversion', 'm_query').
            message: Brief error description (no paths or user data).
        """
        if not self.enabled:
            return
        self._data['errors'].append({
            'category': category,
            'message': message[:200],  # truncate to avoid large payloads
        })

    def record_event(self, event_type, **data):
        """Record a structured event with granular detail.

        Supports per-workbook, per-visual, and per-measure events.

        Args:
            event_type: Event type string, e.g. ``'workbook_start'``,
                ``'visual_converted'``, ``'measure_converted'``,
                ``'dax_accuracy'``, ``'workbook_end'``.
            **data: Arbitrary key-value pairs for the event.
                No PII — use anonymized identifiers only.
        """
        if not self.enabled:
            return
        event = {
            'type': event_type,
            'ts': datetime.now().isoformat(),
        }
        # Sanitize: truncate string values, skip None
        for k, v in data.items():
            if v is None:
                continue
            if isinstance(v, str):
                event[k] = v[:200]
            else:
                event[k] = v
        self._data['events'].append(event)

    def record_decision(self, category, choice, reason=''):
        """Record a single conversion decision (Sprint 131.1).

        Aggregated as ``decisions[category][choice]`` count, plus a
        rolling sample of reasons (capped to avoid log bloat).

        Args:
            category: Decision domain — e.g. 'classification',
                'cardinality', 'connector', 'visual_mapping',
                'repair_strategy', 'parameter_inlining'.
            choice: The branch taken — e.g. 'measure', 'calc_column',
                'manyToOne', 'manyToMany', 'RELATED', 'LOOKUPVALUE'.
            reason: Short free-text reason (truncated to 200 chars).
        """
        if not self.enabled:
            return
        decisions = self._data.setdefault('decisions', {})
        bucket = decisions.setdefault(category, {})
        leaf = bucket.setdefault(choice, {'count': 0, 'sample_reasons': []})
        leaf['count'] += 1
        if reason and len(leaf['sample_reasons']) < 5:
            leaf['sample_reasons'].append(reason[:200])

    def record_validation(self, gate, status, issue_category=''):
        """Record a single validation outcome (Sprint 131.2).

        Args:
            gate: Validation gate name — e.g. 'dax', 'm', 'tmdl',
                'pbir', 'llm_repair'.
            status: One of 'pass', 'fail', 'repaired'.
            issue_category: Optional issue subcategory (e.g.
                'paren_balance', 'tableau_leak', 'unknown_column').
        """
        if not self.enabled:
            return
        if status not in ('pass', 'fail', 'repaired'):
            status = 'fail'
        validations = self._data.setdefault('validations', {})
        bucket = validations.setdefault(gate, {
            'pass': 0, 'fail': 0, 'repaired': 0, 'by_issue': {},
        })
        bucket[status] = bucket.get(status, 0) + 1
        if issue_category:
            bucket['by_issue'][issue_category] = (
                bucket['by_issue'].get(issue_category, 0) + 1
            )

    def get_decision_summary(self):
        """Return aggregated decision counters (Sprint 131.1).

        Convenience for dashboards/tests:
            {category: {choice: count}}
        """
        out = {}
        for cat, choices in self._data.get('decisions', {}).items():
            out[cat] = {ch: leaf['count'] for ch, leaf in choices.items()}
        return out

    def get_validation_summary(self):
        """Return aggregated gate counters (Sprint 131.2)."""
        return dict(self._data.get('validations', {}))

    def finish(self):
        """Record the end of migration and compute duration."""
        if self._start_time:
            self._data['duration_seconds'] = round(
                time.time() - self._start_time, 2
            )

    def save(self):
        """Save telemetry data to local log file.

        Appends one JSON object per line (JSONL format).
        """
        if not self.enabled:
            return

        try:
            with open(self.log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(self._data, ensure_ascii=False) + '\n')
            logger.debug("Telemetry saved to %s", self.log_path)
        except Exception as exc:
            logger.debug("Failed to save telemetry: %s", exc)

    def send(self):
        """Send telemetry to remote endpoint (if configured).

        Uses ``urllib`` (standard library) — no external dependency.
        Silently fails on any error (telemetry must never break migration).
        """
        if not self.enabled or not self.endpoint:
            return

        try:
            import urllib.request
            data = json.dumps(self._data).encode('utf-8')
            req = urllib.request.Request(
                self.endpoint,
                data=data,
                headers={'Content-Type': 'application/json'},
                method='POST',
            )
            urllib.request.urlopen(req, timeout=5)
            logger.debug("Telemetry sent to %s", self.endpoint)
        except Exception as exc:
            logger.debug("Failed to send telemetry: %s", exc)

    def get_data(self):
        """Return the collected telemetry data dict (for testing)."""
        return dict(self._data)

    @staticmethod
    def _get_tool_version():
        """Read tool version from CHANGELOG or return unknown."""
        try:
            changelog = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'CHANGELOG.md'
            )
            with open(changelog, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('## v'):
                        return line.strip().split()[1].lstrip('v').split('—')[0].strip()
        except (OSError, IndexError, ValueError) as exc:
            logger.debug("Could not determine version from CHANGELOG.md: %s", exc)
        return 'unknown'

    @classmethod
    def read_log(cls, log_path=None):
        """Read all telemetry entries from the local log file.

        Args:
            log_path: Path to log file (default: ``~/.ttpbi_telemetry.json``).

        Returns:
            list[dict]: List of telemetry entries.
        """
        log_path = log_path or DEFAULT_LOG_PATH
        entries = []
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
        except FileNotFoundError:
            pass
        except Exception as exc:
            logger.debug("Failed to read telemetry log: %s", exc)
        return entries

    @classmethod
    def summary(cls, log_path=None):
        """Generate a summary of telemetry data.

        Returns:
            dict with aggregate stats.
        """
        entries = cls.read_log(log_path)
        if not entries:
            return {'sessions': 0}

        total_duration = sum(e.get('duration_seconds', 0) or 0 for e in entries)
        total_errors = sum(len(e.get('errors', [])) for e in entries)
        platforms = {}
        for e in entries:
            p = e.get('platform', 'unknown')
            platforms[p] = platforms.get(p, 0) + 1

        return {
            'sessions': len(entries),
            'total_duration_seconds': round(total_duration, 2),
            'avg_duration_seconds': round(total_duration / len(entries), 2),
            'total_errors': total_errors,
            'platforms': platforms,
        }


# ══════════════════════════════════════════════════════════════════════════════
# Sprint 89 — Change Notification
# ══════════════════════════════════════════════════════════════════════════════

class ChangeNotifier:
    """Emit structured events for detected workbook changes.

    Optionally posts to a webhook URL (Teams/Slack compatible JSON payload).
    """

    def __init__(self, webhook_url=None, telemetry_collector=None):
        self._webhook_url = webhook_url
        self._telemetry = telemetry_collector

    def notify(self, workbook_name, change_type, affected_artifacts=None):
        """Emit a change notification event.

        Args:
            workbook_name: Name of the changed workbook.
            change_type: 'new', 'modified', 'deleted'.
            affected_artifacts: list of artifact names/paths affected.

        Returns:
            dict with the event payload.
        """
        payload = {
            'workbook': workbook_name,
            'change_type': change_type,
            'affected_artifacts': affected_artifacts or [],
            'timestamp': _iso_now(),
        }

        # Record in telemetry
        if self._telemetry:
            self._telemetry.record_event(
                'source_change_detected',
                workbook=workbook_name,
                change_type=change_type,
                artifact_count=len(affected_artifacts or []),
            )

        # Post to webhook (best effort)
        if self._webhook_url:
            self._post_webhook(payload)

        return payload

    def _post_webhook(self, payload):
        """Post to Teams/Slack webhook. Best-effort, no exceptions raised."""
        import json as _json
        try:
            import urllib.request
            data = _json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                self._webhook_url,
                data=data,
                headers={'Content-Type': 'application/json'},
                method='POST',
            )
            urllib.request.urlopen(req, timeout=10)
        except Exception as e:
            logging.getLogger(__name__).debug('Webhook post failed: %s', e)


def _iso_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
