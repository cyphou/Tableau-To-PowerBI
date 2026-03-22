"""
Tests for Sprint 99 — Governance Framework.

Tests cover:
1. Naming convention enforcement (table, column, measure)
2. PII detection and data classification
3. Audit trail (JSONL append-only log)
4. Sensitivity label mapping
5. GovernanceEngine configuration
6. Auto-rename in enforce mode
7. Classification annotations
8. run_governance convenience function
9. Name length enforcement
10. Edge cases
"""

import json
import os
import sys
import tempfile

import pytest

# ── Setup import paths ──────────────────────────────────────────────

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, 'powerbi_import'))
sys.path.insert(0, os.path.join(ROOT_DIR, 'tableau_export'))

from governance import (
    GovernanceEngine,
    GovernanceReport,
    GovernanceIssue,
    AuditTrail,
    run_governance,
    DEFAULT_GOVERNANCE_CONFIG,
    _is_snake_case,
    _is_camel_case,
    _is_pascal_case,
    _to_snake_case,
    _to_camel_case,
    _to_pascal_case,
)


# ═══════════════════════════════════════════════════════════════════
#  Helper fixtures
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def sample_tables():
    """Sample TMDL table data for governance checks."""
    return [
        {
            "name": "Sales_Data",
            "columns": [
                {"name": "OrderDate"},
                {"name": "customer_email"},
                {"name": "CustomerName"},
                {"name": "phone_number"},
                {"name": "SSN"},
                {"name": "Revenue"},
                {"name": "ip_address"},
            ],
            "measures": [
                {"name": "Total Revenue", "expression": "SUM('Sales_Data'[Revenue])"},
                {"name": "Count", "expression": "COUNTROWS('Sales_Data')"},
            ],
        },
        {
            "name": "product_catalog",
            "columns": [
                {"name": "ProductID"},
                {"name": "ProductName"},
                {"name": "Price"},
            ],
            "measures": [
                {"name": "Avg Price", "expression": "AVERAGE('product_catalog'[Price])"},
            ],
        },
    ]


@pytest.fixture
def enforce_config():
    """Governance config in enforce mode with naming rules."""
    return {
        "mode": "enforce",
        "naming": {
            "measure_prefix": "m_",
            "column_style": "snake_case",
            "table_style": "PascalCase",
            "max_name_length": 50,
        },
        "pii_detection": True,
    }


@pytest.fixture
def warn_config():
    """Governance config in warn mode."""
    return {
        "mode": "warn",
        "naming": {
            "measure_prefix": "m_",
            "column_style": "camelCase",
            "table_style": "PascalCase",
        },
        "pii_detection": True,
    }


# ═══════════════════════════════════════════════════════════════════
#  1. Naming style helpers
# ═══════════════════════════════════════════════════════════════════

class TestNamingStyleHelpers:
    """Test naming style detection and conversion functions."""

    def test_is_snake_case_valid(self):
        assert _is_snake_case("order_date")
        assert _is_snake_case("customer_email")
        assert _is_snake_case("id")

    def test_is_snake_case_invalid(self):
        assert not _is_snake_case("OrderDate")
        assert not _is_snake_case("customerEmail")
        assert not _is_snake_case("Sales_Data")
        assert not _is_snake_case("UPPER")

    def test_is_camel_case_valid(self):
        assert _is_camel_case("orderDate")
        assert _is_camel_case("customerEmail")
        assert _is_camel_case("id")

    def test_is_camel_case_invalid(self):
        assert not _is_camel_case("OrderDate")
        assert not _is_camel_case("order_date")
        assert not _is_camel_case("UPPER")

    def test_is_pascal_case_valid(self):
        assert _is_pascal_case("OrderDate")
        assert _is_pascal_case("SalesData")
        assert _is_pascal_case("Id")

    def test_is_pascal_case_invalid(self):
        assert not _is_pascal_case("orderDate")
        assert not _is_pascal_case("order_date")
        assert not _is_pascal_case("id")

    def test_to_snake_case(self):
        assert _to_snake_case("OrderDate") == "order_date"
        assert _to_snake_case("SalesData") == "sales_data"
        assert _to_snake_case("customerEmail") == "customer_email"

    def test_to_camel_case(self):
        assert _to_camel_case("order_date") == "orderDate"
        assert _to_camel_case("Sales Data") == "salesData"

    def test_to_pascal_case(self):
        assert _to_pascal_case("order_date") == "OrderDate"
        assert _to_pascal_case("sales data") == "SalesData"


# ═══════════════════════════════════════════════════════════════════
#  2. GovernanceEngine — Naming checks
# ═══════════════════════════════════════════════════════════════════

class TestGovernanceNaming:
    """Test naming convention enforcement."""

    def test_table_naming_pascal_case(self, sample_tables, warn_config):
        engine = GovernanceEngine(warn_config)
        report = engine.check(sample_tables)
        # "product_catalog" violates PascalCase → should have a naming issue
        naming_issues = [i for i in report.issues if i.category == "naming" and i.artifact_type == "table"]
        assert any("product_catalog" in i.artifact_name for i in naming_issues)

    def test_table_naming_no_issue_for_pascal(self, sample_tables, warn_config):
        engine = GovernanceEngine(warn_config)
        report = engine.check(sample_tables)
        # "Sales_Data" is not PascalCase either, but it has underscores
        naming_issues = [i for i in report.issues if i.category == "naming" and i.artifact_type == "table"]
        assert any("Sales_Data" in i.artifact_name for i in naming_issues)

    def test_measure_prefix_enforcement(self, sample_tables, warn_config):
        engine = GovernanceEngine(warn_config)
        report = engine.check(sample_tables)
        measure_issues = [i for i in report.issues if i.category == "naming" and i.artifact_type == "measure"]
        # All measures lack "m_" prefix
        assert len(measure_issues) >= 3  # Total Revenue, Count, Avg Price

    def test_measure_prefix_passes_when_present(self):
        tables = [{"name": "T", "columns": [], "measures": [{"name": "m_Revenue"}]}]
        engine = GovernanceEngine({"naming": {"measure_prefix": "m_"}})
        report = engine.check(tables)
        measure_issues = [i for i in report.issues if i.artifact_type == "measure"]
        assert len(measure_issues) == 0

    def test_column_style_camel_case(self, sample_tables, warn_config):
        engine = GovernanceEngine(warn_config)
        report = engine.check(sample_tables)
        col_issues = [i for i in report.issues if i.category == "naming" and i.artifact_type == "column"]
        # "OrderDate" is PascalCase not camelCase → should have issue
        assert any("OrderDate" in i.artifact_name for i in col_issues)

    def test_warn_mode_severity(self, sample_tables, warn_config):
        engine = GovernanceEngine(warn_config)
        report = engine.check(sample_tables)
        for issue in report.issues:
            if issue.category == "naming":
                assert issue.severity == "warn"

    def test_enforce_mode_severity(self, sample_tables, enforce_config):
        engine = GovernanceEngine(enforce_config)
        report = engine.check(sample_tables)
        for issue in report.issues:
            if issue.category == "naming":
                assert issue.severity == "fail"

    def test_no_naming_rules_no_issues(self, sample_tables):
        engine = GovernanceEngine({"naming": {}})
        report = engine.check(sample_tables)
        naming_issues = [i for i in report.issues if i.category == "naming"]
        assert len(naming_issues) == 0

    def test_max_name_length(self):
        tables = [{"name": "T", "columns": [{"name": "a" * 200}], "measures": []}]
        engine = GovernanceEngine({"naming": {"max_name_length": 100}})
        report = engine.check(tables)
        length_issues = [i for i in report.issues if "exceeds max length" in i.message]
        assert len(length_issues) == 1

    def test_max_name_length_passes(self):
        tables = [{"name": "T", "columns": [{"name": "short"}], "measures": []}]
        engine = GovernanceEngine({"naming": {"max_name_length": 100}})
        report = engine.check(tables)
        length_issues = [i for i in report.issues if "exceeds max length" in i.message]
        assert len(length_issues) == 0


# ═══════════════════════════════════════════════════════════════════
#  3. GovernanceEngine — PII detection
# ═══════════════════════════════════════════════════════════════════

class TestGovernancePII:
    """Test PII detection and data classification."""

    def test_pii_email_detected(self, sample_tables):
        engine = GovernanceEngine({"pii_detection": True})
        report = engine.check(sample_tables)
        assert "Sales_Data.customer_email" in report.classifications
        assert report.classifications["Sales_Data.customer_email"] == "email"

    def test_pii_phone_detected(self, sample_tables):
        engine = GovernanceEngine({"pii_detection": True})
        report = engine.check(sample_tables)
        assert "Sales_Data.phone_number" in report.classifications
        assert report.classifications["Sales_Data.phone_number"] == "phone"

    def test_pii_ssn_detected(self, sample_tables):
        engine = GovernanceEngine({"pii_detection": True})
        report = engine.check(sample_tables)
        assert "Sales_Data.SSN" in report.classifications
        assert report.classifications["Sales_Data.SSN"] == "ssn"

    def test_pii_ip_address_detected(self, sample_tables):
        engine = GovernanceEngine({"pii_detection": True})
        report = engine.check(sample_tables)
        assert "Sales_Data.ip_address" in report.classifications
        assert report.classifications["Sales_Data.ip_address"] == "ipAddress"

    def test_pii_name_detected(self, sample_tables):
        # "CustomerName" doesn't match PII — the pattern requires first_name/last_name/etc.
        # Update sample to use "first_name" instead
        sample_tables[0]["columns"][2] = {"name": "first_name"}
        engine = GovernanceEngine({"pii_detection": True})
        report = engine.check(sample_tables)
        assert "Sales_Data.first_name" in report.classifications
        assert report.classifications["Sales_Data.first_name"] == "name"

    def test_pii_not_detected_for_safe_columns(self, sample_tables):
        engine = GovernanceEngine({"pii_detection": True})
        report = engine.check(sample_tables)
        assert "Sales_Data.Revenue" not in report.classifications
        assert "product_catalog.Price" not in report.classifications

    def test_pii_detection_disabled(self, sample_tables):
        engine = GovernanceEngine({"pii_detection": False})
        report = engine.check(sample_tables)
        pii_issues = [i for i in report.issues if i.category == "pii"]
        assert len(pii_issues) == 0

    def test_pii_classification_applied(self, sample_tables):
        engine = GovernanceEngine({"pii_detection": True})
        report = engine.check(sample_tables)
        count = engine.apply_classifications(sample_tables, report)
        assert count >= 4  # email, phone, SSN, ip
        # Check annotations on columns
        email_col = next(c for c in sample_tables[0]["columns"] if c["name"] == "customer_email")
        annotations = email_col.get("annotations", [])
        assert any(a["name"] == "dataClassification" and a["value"] == "email" for a in annotations)


# ═══════════════════════════════════════════════════════════════════
#  4. GovernanceEngine — Sensitivity labels
# ═══════════════════════════════════════════════════════════════════

class TestGovernanceSensitivity:
    """Test sensitivity label mapping from Tableau permissions."""

    def test_default_sensitivity(self):
        engine = GovernanceEngine()
        label = engine.map_sensitivity_label(None)
        assert label == "General"

    def test_viewer_maps_to_general(self):
        engine = GovernanceEngine()
        label = engine.map_sensitivity_label(["Viewer"])
        assert label == "General"

    def test_editor_maps_to_confidential(self):
        engine = GovernanceEngine()
        label = engine.map_sensitivity_label(["Editor"])
        assert label == "Confidential"

    def test_highest_sensitivity_wins(self):
        engine = GovernanceEngine()
        label = engine.map_sensitivity_label(["Viewer", "Project Leader"])
        assert label == "Highly Confidential"


# ═══════════════════════════════════════════════════════════════════
#  5. GovernanceEngine — Auto-rename
# ═══════════════════════════════════════════════════════════════════

class TestGovernanceAutoRename:
    """Test auto-rename in enforce mode."""

    def test_apply_renames_in_enforce_mode(self, enforce_config):
        tables = [{"name": "sales_data", "columns": [], "measures": [
            {"name": "Revenue", "expression": "SUM([Revenue])"},
        ]}]
        engine = GovernanceEngine(enforce_config)
        report = engine.check(tables)
        count = engine.apply_renames(tables, report)
        assert count >= 1
        # Table should be renamed to PascalCase
        assert tables[0]["name"] == "SalesData"
        # Measure should get prefix
        assert tables[0]["measures"][0]["name"] == "m_Revenue"

    def test_apply_renames_noop_in_warn_mode(self, warn_config):
        tables = [{"name": "sales_data", "columns": [], "measures": [
            {"name": "Revenue"},
        ]}]
        engine = GovernanceEngine(warn_config)
        report = engine.check(tables)
        count = engine.apply_renames(tables, report)
        assert count == 0
        assert tables[0]["name"] == "sales_data"  # unchanged


# ═══════════════════════════════════════════════════════════════════
#  6. AuditTrail
# ═══════════════════════════════════════════════════════════════════

class TestAuditTrail:
    """Test append-only JSONL audit log."""

    def test_record_and_save(self, tmp_path):
        log_path = str(tmp_path / "audit.jsonl")
        audit = AuditTrail(log_path=log_path)
        entry = audit.record(
            source_file="test.twbx",
            workbook_name="TestWB",
            output_dir="/output/TestWB",
            source_hash="abc123",
        )
        assert entry["workbook"] == "TestWB"
        assert entry["source_hash"] == "abc123"
        assert "id" in entry
        assert "timestamp" in entry

        saved = audit.save()
        assert saved == 1
        assert os.path.isfile(log_path)

        # Read back
        entries = audit.read()
        assert len(entries) == 1
        assert entries[0]["workbook"] == "TestWB"

    def test_append_only(self, tmp_path):
        log_path = str(tmp_path / "audit.jsonl")
        audit = AuditTrail(log_path=log_path)
        audit.record(workbook_name="WB1")
        audit.save()

        audit2 = AuditTrail(log_path=log_path)
        audit2.record(workbook_name="WB2")
        audit2.save()

        entries = AuditTrail(log_path=log_path).read()
        assert len(entries) == 2
        assert entries[0]["workbook"] == "WB1"
        assert entries[1]["workbook"] == "WB2"

    def test_compute_file_hash(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        h = AuditTrail.compute_file_hash(str(f))
        assert len(h) == 64  # SHA-256 hex digest

    def test_compute_file_hash_nonexistent(self):
        h = AuditTrail.compute_file_hash("/nonexistent/file.txt")
        assert h == ""

    def test_compute_dir_hash(self, tmp_path):
        (tmp_path / "a.txt").write_text("aaa")
        (tmp_path / "b.txt").write_text("bbb")
        h = AuditTrail.compute_dir_hash(str(tmp_path))
        assert len(h) == 64

    def test_read_empty_log(self, tmp_path):
        log_path = str(tmp_path / "empty.jsonl")
        entries = AuditTrail(log_path=log_path).read()
        assert entries == []


# ═══════════════════════════════════════════════════════════════════
#  7. run_governance convenience function
# ═══════════════════════════════════════════════════════════════════

class TestRunGovernance:
    """Test the run_governance convenience function."""

    def test_run_governance_warn_mode(self, sample_tables):
        report = run_governance(sample_tables)
        assert isinstance(report, GovernanceReport)
        assert report.mode == "warn"

    def test_run_governance_enforce_mode(self, sample_tables, enforce_config):
        report = run_governance(sample_tables, config=enforce_config)
        assert report.mode == "enforce"
        assert report.issue_count > 0

    def test_run_governance_with_permissions(self, sample_tables):
        report = run_governance(
            sample_tables,
            tableau_permissions=["Editor", "Viewer"]
        )
        assert report.sensitivity_label == "Confidential"

    def test_run_governance_applies_classifications(self, sample_tables):
        report = run_governance(sample_tables, config={"pii_detection": True})
        # Classifications should be applied in warn mode too
        email_col = next(c for c in sample_tables[0]["columns"] if c["name"] == "customer_email")
        assert any(
            a.get("name") == "dataClassification"
            for a in email_col.get("annotations", [])
        )


# ═══════════════════════════════════════════════════════════════════
#  8. GovernanceReport
# ═══════════════════════════════════════════════════════════════════

class TestGovernanceReport:
    """Test GovernanceReport data class."""

    def test_to_dict(self):
        report = GovernanceReport(timestamp="2026-03-22T00:00:00", mode="warn")
        report.issues.append(GovernanceIssue(
            category="naming", severity="warn",
            artifact_type="table", artifact_name="t",
            message="test"
        ))
        d = report.to_dict()
        assert d["issue_count"] == 1
        assert d["warn_count"] == 1
        assert d["fail_count"] == 0
        assert len(d["issues"]) == 1

    def test_empty_report(self):
        report = GovernanceReport()
        assert report.issue_count == 0
        assert report.warn_count == 0
        assert report.fail_count == 0


# ═══════════════════════════════════════════════════════════════════
#  9. Configuration
# ═══════════════════════════════════════════════════════════════════

class TestGovernanceConfig:
    """Test GovernanceEngine configuration handling."""

    def test_default_config(self):
        engine = GovernanceEngine()
        assert engine.mode == "warn"
        assert engine.config["pii_detection"] is True

    def test_custom_config_merges(self):
        engine = GovernanceEngine({"mode": "enforce", "naming": {"measure_prefix": "m_"}})
        assert engine.mode == "enforce"
        assert engine.config["naming"]["measure_prefix"] == "m_"
        # Default naming values should still be present
        assert "column_style" in engine.config["naming"]

    def test_empty_tables(self):
        engine = GovernanceEngine()
        report = engine.check([])
        assert report.issue_count == 0

    def test_none_tables(self):
        engine = GovernanceEngine()
        report = engine.check(None)
        assert report.issue_count == 0


# ═══════════════════════════════════════════════════════════════════
#  10. Edge cases
# ═══════════════════════════════════════════════════════════════════

class TestGovernanceEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_column_as_string(self):
        """Columns can be plain strings (not dicts)."""
        tables = [{"name": "T", "columns": ["email_address", "Revenue"], "measures": []}]
        engine = GovernanceEngine({"pii_detection": True})
        report = engine.check(tables)
        assert "T.email_address" in report.classifications

    def test_measure_as_string(self):
        """Measures can be plain strings."""
        tables = [{"name": "T", "columns": [], "measures": ["Revenue"]}]
        engine = GovernanceEngine({"naming": {"measure_prefix": "m_"}})
        report = engine.check(tables)
        measure_issues = [i for i in report.issues if i.artifact_type == "measure"]
        assert len(measure_issues) == 1

    def test_empty_column_name_skipped(self):
        tables = [{"name": "T", "columns": [{"name": ""}], "measures": []}]
        engine = GovernanceEngine({"pii_detection": True, "naming": {"column_style": "snake_case"}})
        report = engine.check(tables)
        # Should not crash
        assert isinstance(report, GovernanceReport)

    def test_credit_card_pii(self):
        tables = [{"name": "T", "columns": [{"name": "credit_card_number"}], "measures": []}]
        report = run_governance(tables)
        assert "T.credit_card_number" in report.classifications
        assert report.classifications["T.credit_card_number"] == "creditCard"

    def test_dob_pii(self):
        tables = [{"name": "T", "columns": [{"name": "date_of_birth"}], "measures": []}]
        report = run_governance(tables)
        assert "T.date_of_birth" in report.classifications
        assert report.classifications["T.date_of_birth"] == "dateOfBirth"

    def test_passport_pii(self):
        tables = [{"name": "T", "columns": [{"name": "passport_number"}], "measures": []}]
        report = run_governance(tables)
        assert "T.passport_number" in report.classifications
