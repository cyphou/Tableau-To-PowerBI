"""
Tests for Sprint 100 — Production Hardening.

Tests cover:
1. Rolling deployment (deploy_rolling, phases, rollback)
2. SLA tracker (compliance, breach detection, report)
3. Monitoring integration (backends, metrics, events, flush)
4. Endorsement & certification (endorse_item)
5. Production scale stress test (1000 workbooks, synthetic)
"""

import json
import os
import sys
import time
import tempfile

import pytest

# ── Setup import paths ──────────────────────────────────────────────

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, 'powerbi_import'))
sys.path.insert(0, os.path.join(ROOT_DIR, 'powerbi_import', 'deploy'))
sys.path.insert(0, os.path.join(ROOT_DIR, 'tableau_export'))


# ═══════════════════════════════════════════════════════════════════
#  1. SLA Tracker
# ═══════════════════════════════════════════════════════════════════

from sla_tracker import SLATracker, SLAResult, SLAReport, DEFAULT_SLA_CONFIG


class TestSLATracker:
    """Test SLA tracking and compliance evaluation."""

    def test_default_config(self):
        tracker = SLATracker()
        assert tracker.config["max_migration_seconds"] == 60
        assert tracker.config["min_fidelity_score"] == 80.0

    def test_custom_config(self):
        tracker = SLATracker({"max_migration_seconds": 30, "min_fidelity_score": 90})
        assert tracker.config["max_migration_seconds"] == 30
        assert tracker.config["min_fidelity_score"] == 90

    def test_compliant_workbook(self):
        tracker = SLATracker({"max_migration_seconds": 60, "min_fidelity_score": 80})
        tracker.start("wb.twbx")
        result = tracker.record_result("wb.twbx", fidelity=95.0, validation_passed=True)
        assert result.compliant
        assert len(result.breaches) == 0

    def test_fidelity_breach(self):
        tracker = SLATracker({"max_migration_seconds": 60, "min_fidelity_score": 90})
        tracker.start("wb.twbx")
        result = tracker.record_result("wb.twbx", fidelity=75.0, validation_passed=True)
        assert not result.fidelity_compliant
        assert not result.compliant
        assert any("Fidelity" in b for b in result.breaches)

    def test_validation_breach(self):
        tracker = SLATracker({"require_validation_pass": True})
        tracker.start("wb.twbx")
        result = tracker.record_result("wb.twbx", fidelity=95.0, validation_passed=False)
        assert not result.validation_compliant
        assert not result.compliant

    def test_time_breach(self):
        tracker = SLATracker({"max_migration_seconds": 0.001})
        tracker.start("wb.twbx")
        time.sleep(0.01)
        result = tracker.record_result("wb.twbx", fidelity=95.0, validation_passed=True)
        assert not result.time_compliant

    def test_report_generation(self):
        tracker = SLATracker()
        tracker.start("wb1")
        tracker.record_result("wb1", fidelity=95, validation_passed=True)
        tracker.start("wb2")
        tracker.record_result("wb2", fidelity=50, validation_passed=True)
        report = tracker.get_report()
        assert report.total_workbooks == 2
        assert report.compliant_count == 1
        assert report.breach_count == 1
        assert report.compliance_rate == 50.0

    def test_report_save(self, tmp_path):
        tracker = SLATracker()
        tracker.start("wb1")
        tracker.record_result("wb1", fidelity=95, validation_passed=True)
        report = tracker.get_report()
        path = str(tmp_path / "sla.json")
        report.save(path)
        assert os.path.isfile(path)
        with open(path) as f:
            data = json.load(f)
        assert data["total_workbooks"] == 1

    def test_report_to_dict(self):
        report = SLAReport(total_workbooks=0)
        d = report.to_dict()
        assert d["compliance_rate"] == 100.0

    def test_result_to_dict(self):
        r = SLAResult(workbook="test", fidelity_score=90.5)
        d = r.to_dict()
        assert d["workbook"] == "test"
        assert d["fidelity_score"] == 90.5

    def test_reset(self):
        tracker = SLATracker()
        tracker.start("wb1")
        tracker.record_result("wb1", fidelity=95, validation_passed=True)
        tracker.reset()
        report = tracker.get_report()
        assert report.total_workbooks == 0

    def test_no_timer_graceful(self):
        """record_result without start() → 0 elapsed."""
        tracker = SLATracker({"max_migration_seconds": 0})
        result = tracker.record_result("wb", fidelity=95, validation_passed=True)
        assert result.migration_seconds == 0.0


# ═══════════════════════════════════════════════════════════════════
#  2. Monitoring Integration
# ═══════════════════════════════════════════════════════════════════

from monitoring import MigrationMonitor, _JsonBackend, _NoneBackend


class TestMonitoring:
    """Test monitoring backends and MigrationMonitor."""

    def test_json_backend_record_and_flush(self, tmp_path):
        log_path = str(tmp_path / "metrics.jsonl")
        backend = _JsonBackend(log_path=log_path)
        backend.record_metric("test_metric", 42.0, {"workbook": "wb1"})
        backend.record_event("test_event", {"key": "value"})
        count = backend.flush()
        assert count == 2
        assert os.path.isfile(log_path)
        with open(log_path) as f:
            lines = f.readlines()
        assert len(lines) == 2
        entry = json.loads(lines[0])
        assert entry["type"] == "metric"
        assert entry["name"] == "test_metric"

    def test_json_backend_empty_flush(self, tmp_path):
        backend = _JsonBackend(log_path=str(tmp_path / "empty.jsonl"))
        result = backend.flush()
        assert result is None

    def test_none_backend(self):
        backend = _NoneBackend()
        backend.record_metric("x", 1)
        backend.record_event("y")
        backend.flush()  # no-op, no error

    def test_monitor_json(self, tmp_path):
        log_path = str(tmp_path / "mon.jsonl")
        monitor = MigrationMonitor(backend="json", log_path=log_path)
        monitor.record_metric("test", 1.0, workbook="wb")
        monitor.record_event("done", workbook="wb")
        monitor.flush()
        with open(log_path) as f:
            lines = f.readlines()
        assert len(lines) == 2

    def test_monitor_none(self):
        monitor = MigrationMonitor(backend="none")
        monitor.record_metric("x", 1)
        monitor.flush()  # no-op

    def test_record_migration(self, tmp_path):
        log_path = str(tmp_path / "mig.jsonl")
        monitor = MigrationMonitor(backend="json", log_path=log_path)
        monitor.record_migration("wb", 12.5, 95.0, tables=3, measures=5)
        monitor.flush()
        with open(log_path) as f:
            lines = f.readlines()
        # 6 metrics + 1 event = 7 entries
        assert len(lines) == 7

    def test_backend_selection(self):
        m = MigrationMonitor(backend="json")
        assert m.backend_name == "json"
        m = MigrationMonitor(backend="none")
        assert m.backend_name == "none"


# ═══════════════════════════════════════════════════════════════════
#  3. Rolling Deployment
# ═══════════════════════════════════════════════════════════════════

from pbi_deployer import PBIWorkspaceDeployer, DeploymentResult


class TestRollingDeployment:
    """Test rolling deployment exists and has correct structure."""

    def test_deploy_rolling_method_exists(self):
        from powerbi_import.deploy.pbi_deployer import PBIWorkspaceDeployer
        assert hasattr(PBIWorkspaceDeployer, 'deploy_rolling')

    def test_deploy_rolling_signature(self):
        import inspect
        from powerbi_import.deploy.pbi_deployer import PBIWorkspaceDeployer
        sig = inspect.signature(PBIWorkspaceDeployer.deploy_rolling)
        params = list(sig.parameters.keys())
        assert 'project_dir' in params
        assert 'dataset_name' in params
        assert 'max_wait_seconds' in params

    def test_wait_for_refresh_method_exists(self):
        from powerbi_import.deploy.pbi_deployer import PBIWorkspaceDeployer
        assert hasattr(PBIWorkspaceDeployer, '_wait_for_refresh')

    def test_cleanup_dataset_method_exists(self):
        from powerbi_import.deploy.pbi_deployer import PBIWorkspaceDeployer
        assert hasattr(PBIWorkspaceDeployer, '_cleanup_dataset')


# ═══════════════════════════════════════════════════════════════════
#  4. Endorsement
# ═══════════════════════════════════════════════════════════════════

from deployer import FabricDeployer


class MockFabricClient:
    """Mock Fabric REST client."""

    def __init__(self):
        self.last_patch = None

    def patch(self, endpoint, data=None):
        self.last_patch = {"endpoint": endpoint, "data": data}
        return {"status": "ok"}

    def list_items(self, workspace_id, item_type=None):
        return {"value": []}


class TestEndorsement:
    """Test endorsement and certification."""

    def test_endorse_promoted(self):
        client = MockFabricClient()
        deployer = FabricDeployer(client=client)
        result = deployer.endorse_item("ws-1", "item-1", "promoted")
        assert result["status"] == "succeeded"
        assert result["endorsement"] == "promoted"
        assert client.last_patch is not None
        assert "promoted" in json.dumps(client.last_patch["data"])

    def test_endorse_certified(self):
        client = MockFabricClient()
        deployer = FabricDeployer(client=client)
        result = deployer.endorse_item("ws-1", "item-1", "certified")
        assert result["endorsement"] == "certified"

    def test_endorse_none(self):
        client = MockFabricClient()
        deployer = FabricDeployer(client=client)
        result = deployer.endorse_item("ws-1", "item-1", "none")
        assert result["endorsement"] == "none"

    def test_endorse_invalid(self):
        client = MockFabricClient()
        deployer = FabricDeployer(client=client)
        with pytest.raises(ValueError, match="must be one of"):
            deployer.endorse_item("ws-1", "item-1", "bad_value")

    def test_endorse_api_failure(self):
        class FailClient:
            def patch(self, endpoint, data=None):
                raise Exception("API error")
        deployer = FabricDeployer(client=FailClient())
        result = deployer.endorse_item("ws-1", "item-1", "promoted")
        assert result["status"] == "failed"
        assert "API error" in result["error"]


# ═══════════════════════════════════════════════════════════════════
#  5. Production Scale Stress Test
# ═══════════════════════════════════════════════════════════════════

from tmdl_generator import generate_tmdl
from dax_converter import convert_tableau_formula_to_dax


class TestProductionScale:
    """Stress test: 1000 synthetic workbooks."""

    @pytest.fixture
    def synthetic_workbooks(self):
        """Generate 1000 minimal synthetic workbook data sets."""
        workbooks = []
        for i in range(1000):
            wb = {
                "datasources": [{
                    "name": f"DS_{i}",
                    "tables": [
                        {"name": f"Sales_{i}", "columns": [
                            {"name": "OrderDate", "type": "datetime"},
                            {"name": "Revenue", "type": "real"},
                            {"name": "Category", "type": "string"},
                        ]},
                        {"name": f"Products_{i}", "columns": [
                            {"name": "ProductID", "type": "integer"},
                            {"name": "ProductName", "type": "string"},
                            {"name": "Price", "type": "real"},
                        ]},
                        {"name": f"Regions_{i}", "columns": [
                            {"name": "RegionID", "type": "integer"},
                            {"name": "RegionName", "type": "string"},
                        ]},
                    ],
                    "relationships": [{
                        "from_table": f"Sales_{i}", "from_column": "Category",
                        "to_table": f"Products_{i}", "to_column": "ProductName",
                        "join_type": "left",
                    }],
                }],
                "calculations": [
                    {"name": f"Total Revenue {i}", "formula": "SUM([Revenue])",
                     "role": "measure", "caption": f"Total Revenue {i}"},
                    {"name": f"Avg Price {i}", "formula": "AVG([Price])",
                     "role": "measure", "caption": f"Avg Price {i}"},
                    {"name": f"Count Orders {i}", "formula": "COUNTD([OrderDate])",
                     "role": "measure", "caption": f"Count Orders {i}"},
                    {"name": f"Rev Running {i}", "formula": "RUNNING_SUM(SUM([Revenue]))",
                     "role": "measure", "caption": f"Rev Running {i}"},
                    {"name": f"Cat Upper {i}", "formula": "UPPER([Category])",
                     "role": "dimension", "caption": f"Cat Upper {i}"},
                ],
                "worksheets": [],
                "dashboards": [],
                "parameters": [],
                "filters": [],
            }
            workbooks.append(wb)
        return workbooks

    def test_1000_dax_conversions(self, synthetic_workbooks):
        """Convert 5000 formulas (5 per workbook × 1000) in under 30s."""
        start = time.monotonic()
        total_conversions = 0
        for wb in synthetic_workbooks:
            for calc in wb["calculations"]:
                convert_tableau_formula_to_dax(
                    calc["formula"],
                    column_name=calc["caption"],
                    table_name="Sales",
                )
                total_conversions += 1
        elapsed = time.monotonic() - start
        assert total_conversions == 5000
        assert elapsed < 30, f"5000 DAX conversions took {elapsed:.1f}s (limit: 30s)"

    def test_1000_tmdl_generations(self, synthetic_workbooks):
        """Generate 1000 TMDL semantic models in under 120s, 0 errors."""
        start = time.monotonic()
        errors = []
        with tempfile.TemporaryDirectory() as tmpdir:
            for i, wb in enumerate(synthetic_workbooks):
                try:
                    out = os.path.join(tmpdir, f"wb_{i}", f"Model_{i}.SemanticModel", "definition")
                    os.makedirs(out, exist_ok=True)
                    generate_tmdl(
                        datasources=wb["datasources"],
                        report_name=f"Model_{i}",
                        extra_objects={
                            "hierarchies": [], "sets": [], "groups": [],
                            "bins": [], "aliases": [], "parameters": [],
                            "user_filters": [], "_datasources": wb["datasources"],
                            "worksheets": wb.get("worksheets", []),
                        },
                        output_dir=out,
                    )
                except Exception as e:
                    errors.append(f"wb_{i}: {e}")
        elapsed = time.monotonic() - start
        assert len(errors) == 0, f"{len(errors)} errors: {errors[:5]}"
        assert elapsed < 120, f"1000 TMDL generations took {elapsed:.1f}s (limit: 120s)"

    def test_sla_tracking_1000_workbooks(self, synthetic_workbooks):
        """SLA tracker handles 1000 results without issues."""
        tracker = SLATracker({"max_migration_seconds": 999,
                              "min_fidelity_score": 50})
        for i, wb in enumerate(synthetic_workbooks):
            tracker.start(f"wb_{i}")
            tracker.record_result(f"wb_{i}", fidelity=90.0 + (i % 10),
                                  validation_passed=True)
        report = tracker.get_report()
        assert report.total_workbooks == 1000
        assert report.compliance_rate >= 99.0

    def test_monitoring_1000_events(self, tmp_path):
        """Monitor 1000 migration events without issues."""
        log_path = str(tmp_path / "scale_test.jsonl")
        monitor = MigrationMonitor(backend="json", log_path=log_path)
        for i in range(1000):
            monitor.record_metric("test", float(i), workbook=f"wb_{i}")
        monitor.flush()
        with open(log_path) as f:
            lines = f.readlines()
        assert len(lines) == 1000


# ═══════════════════════════════════════════════════════════════════
#  6. DeploymentResult
# ═══════════════════════════════════════════════════════════════════

class TestDeploymentResult:
    """Test DeploymentResult data class."""

    def test_to_dict(self):
        r = DeploymentResult("TestProject", status="succeeded",
                             dataset_id="ds-1")
        d = r.to_dict()
        assert d["project_name"] == "TestProject"
        assert d["status"] == "succeeded"
        assert d["dataset_id"] == "ds-1"

    def test_defaults(self):
        r = DeploymentResult("P")
        assert r.status == "pending"
        assert r.error is None
