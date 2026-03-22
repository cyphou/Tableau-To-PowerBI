"""
Migration SLA Tracker (Sprint 100).

Per-workbook SLAs: max migration time, min fidelity score, required data
validation pass.  Track compliance across batch migrations with alerting
on SLA breaches.

Usage:
    tracker = SLATracker(config)
    tracker.start('workbook.twbx')
    ...
    tracker.record_result('workbook.twbx', fidelity=92.5, validation_passed=True)
    report = tracker.get_report()
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ── Default SLA Config ────────────────────────────────────────────────────────

DEFAULT_SLA_CONFIG = {
    "max_migration_seconds": 60,        # Per-workbook time limit
    "min_fidelity_score": 80.0,         # Minimum fidelity % to pass
    "require_validation_pass": True,     # Validation must pass
    "alert_on_breach": True,             # Print alert on SLA breach
}


# ── Data Classes ──────────────────────────────────────────────────────────────

@dataclass
class SLAResult:
    """Result of SLA evaluation for a single workbook."""
    workbook: str
    migration_seconds: float = 0.0
    fidelity_score: float = 0.0
    validation_passed: bool = False
    time_compliant: bool = True
    fidelity_compliant: bool = True
    validation_compliant: bool = True
    breaches: list = field(default_factory=list)

    @property
    def compliant(self):
        return self.time_compliant and self.fidelity_compliant and self.validation_compliant

    def to_dict(self):
        return {
            "workbook": self.workbook,
            "migration_seconds": round(self.migration_seconds, 2),
            "fidelity_score": round(self.fidelity_score, 1),
            "validation_passed": self.validation_passed,
            "compliant": self.compliant,
            "breaches": self.breaches,
        }


@dataclass
class SLAReport:
    """Aggregate SLA compliance report across all workbooks."""
    timestamp: str = ""
    total_workbooks: int = 0
    compliant_count: int = 0
    breach_count: int = 0
    results: list = field(default_factory=list)
    config: dict = field(default_factory=dict)

    @property
    def compliance_rate(self):
        if self.total_workbooks == 0:
            return 100.0
        return round(self.compliant_count / self.total_workbooks * 100, 1)

    def to_dict(self):
        return {
            "timestamp": self.timestamp,
            "total_workbooks": self.total_workbooks,
            "compliant_count": self.compliant_count,
            "breach_count": self.breach_count,
            "compliance_rate": self.compliance_rate,
            "sla_config": self.config,
            "results": [r.to_dict() for r in self.results],
        }

    def save(self, output_path):
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)


# ── SLA Tracker ───────────────────────────────────────────────────────────────

class SLATracker:
    """Track and enforce per-workbook migration SLAs."""

    def __init__(self, config=None):
        self.config = dict(DEFAULT_SLA_CONFIG)
        if config:
            self.config.update(config)
        self._timers = {}       # workbook → start_time
        self._results = []      # list of SLAResult

    def start(self, workbook_name):
        """Record migration start time for a workbook."""
        self._timers[workbook_name] = time.monotonic()

    def record_result(self, workbook_name, fidelity=0.0, validation_passed=False):
        """Record the migration outcome and evaluate SLA compliance.

        Args:
            workbook_name: Name of the migrated workbook.
            fidelity: Fidelity score (0-100).
            validation_passed: Whether post-generation validation passed.

        Returns:
            SLAResult for this workbook.
        """
        elapsed = 0.0
        if workbook_name in self._timers:
            elapsed = time.monotonic() - self._timers.pop(workbook_name)

        result = SLAResult(
            workbook=workbook_name,
            migration_seconds=elapsed,
            fidelity_score=fidelity,
            validation_passed=validation_passed,
        )

        max_time = self.config["max_migration_seconds"]
        min_fidelity = self.config["min_fidelity_score"]
        require_val = self.config["require_validation_pass"]

        # Time compliance
        if max_time > 0 and elapsed > max_time:
            result.time_compliant = False
            result.breaches.append(
                f"Migration took {elapsed:.1f}s (SLA: {max_time}s)"
            )

        # Fidelity compliance
        if min_fidelity > 0 and fidelity < min_fidelity:
            result.fidelity_compliant = False
            result.breaches.append(
                f"Fidelity {fidelity:.1f}% below threshold {min_fidelity}%"
            )

        # Validation compliance
        if require_val and not validation_passed:
            result.validation_compliant = False
            result.breaches.append("Post-migration validation failed")

        if result.breaches and self.config.get("alert_on_breach"):
            for breach in result.breaches:
                logger.warning("SLA BREACH [%s]: %s", workbook_name, breach)

        self._results.append(result)
        return result

    def get_report(self):
        """Generate an aggregate SLA compliance report.

        Returns:
            SLAReport with all tracked workbooks.
        """
        report = SLAReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_workbooks=len(self._results),
            compliant_count=sum(1 for r in self._results if r.compliant),
            breach_count=sum(1 for r in self._results if not r.compliant),
            results=list(self._results),
            config=dict(self.config),
        )
        return report

    def reset(self):
        """Clear all tracked results and timers."""
        self._timers.clear()
        self._results.clear()
