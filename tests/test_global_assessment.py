"""Tests for global_assessment.py — cross-workbook merge analysis."""

import json
import os
import tempfile
import unittest

from powerbi_import.global_assessment import (
    GlobalAssessment,
    MergeCluster,
    PairwiseScore,
    WorkbookProfile,
    _build_profile,
    generate_global_html_report,
    print_global_summary,
    run_global_assessment,
    save_global_assessment_json,
)


def _make_extracted(tables=None, calculations=None, worksheets=None,
                    dashboards=None, parameters=None, connection_type="postgres"):
    """Build a minimal extracted-data dict for testing."""
    if tables is None:
        tables = []
    ds_tables = []
    for name, columns in tables:
        ds_tables.append({
            "name": name,
            "type": "table",
            "columns": [{"name": c, "datatype": "string"} for c in columns],
        })
    ds = {
        "name": "TestDS",
        "connection": {
            "type": connection_type,
            "details": {"server": "localhost", "database": "testdb"},
        },
        "tables": ds_tables,
        "calculations": calculations or [],
        "relationships": [],
    }
    return {
        "datasources": [ds],
        "worksheets": worksheets or [],
        "dashboards": dashboards or [],
        "calculations": calculations or [],
        "parameters": parameters or [],
    }


class TestBuildProfile(unittest.TestCase):
    """Test WorkbookProfile building."""

    def test_empty_workbook(self):
        ext = {"datasources": [], "worksheets": [], "dashboards": []}
        p = _build_profile("empty", ext)
        self.assertEqual(p.name, "empty")
        self.assertEqual(p.tables, 0)
        self.assertEqual(p.measures, 0)

    def test_with_tables_and_measures(self):
        ext = _make_extracted(
            tables=[("orders", ["id", "amount"]), ("customers", ["id", "name"])],
            calculations=[
                {"name": "Total", "role": "measure", "formula": "SUM(amount)"},
                {"name": "Flag", "role": "dimension", "formula": "IF(...)"},
            ],
        )
        p = _build_profile("sales", ext)
        self.assertEqual(p.tables, 2)
        self.assertEqual(p.columns, 4)
        # measures counted from both datasource calcs + top-level calcs
        self.assertEqual(p.measures, 2)
        self.assertEqual(p.calc_columns, 2)
        self.assertIn("orders", p.table_names)
        self.assertIn("customers", p.table_names)

    def test_connection_types(self):
        ext = _make_extracted(tables=[("t1", ["a"])], connection_type="sqlserver")
        p = _build_profile("wb", ext)
        self.assertEqual(p.connection_types, ["sqlserver"])


class TestRunGlobalAssessment(unittest.TestCase):
    """Test the core global assessment engine."""

    def _shared_pair(self):
        """Two workbooks sharing a table."""
        ext_a = _make_extracted(
            tables=[("orders", ["id", "amount", "date"]),
                    ("regions", ["id", "name"])],
        )
        ext_b = _make_extracted(
            tables=[("orders", ["id", "amount", "date"]),
                    ("products", ["id", "product_name"])],
        )
        return [ext_a, ext_b], ["SalesWB", "ProductsWB"]

    def _no_overlap(self):
        """Two workbooks with no shared tables."""
        ext_a = _make_extracted(
            tables=[("orders", ["id", "amount"])],
        )
        ext_b = _make_extracted(
            tables=[("employees", ["id", "name"])],
            connection_type="mysql",
        )
        return [ext_a, ext_b], ["Sales", "HR"]

    def test_profiles_count(self):
        data, names = self._shared_pair()
        result = run_global_assessment(data, names)
        self.assertEqual(result.total_workbooks, 2)
        self.assertEqual(len(result.workbook_profiles), 2)
        self.assertEqual(result.workbook_profiles[0].name, "SalesWB")

    def test_shared_tables_detected(self):
        data, names = self._shared_pair()
        result = run_global_assessment(data, names)
        self.assertEqual(len(result.pairwise_scores), 1)
        ps = result.pairwise_scores[0]
        self.assertGreater(ps.merge_score, 0)
        self.assertGreater(ps.shared_tables, 0)

    def test_merge_cluster_formed(self):
        data, names = self._shared_pair()
        result = run_global_assessment(data, names)
        # Should form one cluster since score >= 30
        self.assertGreaterEqual(len(result.merge_clusters), 1)
        cluster = result.merge_clusters[0]
        self.assertIn("SalesWB", cluster.workbooks)
        self.assertIn("ProductsWB", cluster.workbooks)

    def test_no_overlap_both_isolated(self):
        data, names = self._no_overlap()
        result = run_global_assessment(data, names)
        self.assertEqual(len(result.merge_clusters), 0)
        self.assertEqual(len(result.isolated_workbooks), 2)
        self.assertIn("Sales", result.isolated_workbooks)
        self.assertIn("HR", result.isolated_workbooks)

    def test_three_workbooks_partial_overlap(self):
        """A shares with B but not C → cluster(A,B) + isolated(C)."""
        ext_a = _make_extracted(
            tables=[("orders", ["id", "amount"])],
        )
        ext_b = _make_extracted(
            tables=[("orders", ["id", "amount"]),
                    ("products", ["id", "name"])],
        )
        ext_c = _make_extracted(
            tables=[("employees", ["id", "name"])],
            connection_type="mysql",
        )
        result = run_global_assessment(
            [ext_a, ext_b, ext_c], ["WBA", "WBB", "WBC"]
        )
        self.assertEqual(result.total_workbooks, 3)
        # WBA and WBB should cluster
        cluster_wbs = set()
        for c in result.merge_clusters:
            cluster_wbs.update(c.workbooks)
        self.assertIn("WBA", cluster_wbs)
        self.assertIn("WBB", cluster_wbs)
        self.assertIn("WBC", result.isolated_workbooks)

    def test_transitive_clustering(self):
        """A shares with B, B shares with C → all three in one cluster."""
        # A and B share "orders"
        ext_a = _make_extracted(tables=[("orders", ["id", "amount"])])
        ext_b = _make_extracted(
            tables=[("orders", ["id", "amount"]),
                    ("products", ["id", "name"])],
        )
        # B and C share "products"
        ext_c = _make_extracted(tables=[("products", ["id", "name"])])
        result = run_global_assessment(
            [ext_a, ext_b, ext_c], ["WBA", "WBB", "WBC"]
        )
        # All three should be in one cluster
        self.assertEqual(len(result.merge_clusters), 1)
        self.assertEqual(sorted(result.merge_clusters[0].workbooks),
                         ["WBA", "WBB", "WBC"])
        self.assertEqual(len(result.isolated_workbooks), 0)

    def test_pairwise_scores_complete(self):
        """N workbooks should produce N*(N-1)/2 pairwise scores."""
        exts = [
            _make_extracted(tables=[(f"t{i}", ["id"])]) for i in range(4)
        ]
        names = [f"WB{i}" for i in range(4)]
        result = run_global_assessment(exts, names)
        expected = 4 * 3 // 2  # C(4,2) = 6
        self.assertEqual(len(result.pairwise_scores), expected)

    def test_to_dict_serializable(self):
        data, names = self._shared_pair()
        result = run_global_assessment(data, names)
        d = result.to_dict()
        # Must be JSON-serializable
        json_str = json.dumps(d)
        self.assertIn("total_workbooks", json_str)
        self.assertIn("merge_clusters", json_str)
        self.assertIn("pairwise_scores", json_str)
        self.assertIn("isolated_workbooks", json_str)


class TestGlobalHTMLReport(unittest.TestCase):
    """Test HTML report generation."""

    def _make_result(self):
        ext_a = _make_extracted(
            tables=[("orders", ["id", "amount", "date"]),
                    ("regions", ["id", "name"])],
            calculations=[
                {"name": "Total Sales", "role": "measure",
                 "formula": "SUM(amount)"},
            ],
        )
        ext_b = _make_extracted(
            tables=[("orders", ["id", "amount", "date"]),
                    ("products", ["id", "product_name"])],
            calculations=[
                {"name": "Total Sales", "role": "measure",
                 "formula": "SUM(amount)"},
            ],
        )
        ext_c = _make_extracted(
            tables=[("employees", ["id", "name"])],
            connection_type="mysql",
        )
        return run_global_assessment(
            [ext_a, ext_b, ext_c],
            ["SalesWB", "ProductsWB", "HRWorkbook"],
        )

    def test_html_generated(self):
        result = self._make_result()
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "report.html")
            out = generate_global_html_report(result, output_path=path)
            self.assertTrue(os.path.isfile(out))
            content = open(out, encoding="utf-8").read()
            self.assertIn("Global Assessment", content)

    def test_html_has_workbook_names(self):
        result = self._make_result()
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "report.html")
            out = generate_global_html_report(result, output_path=path)
            content = open(out, encoding="utf-8").read()
            self.assertIn("SalesWB", content)
            self.assertIn("ProductsWB", content)
            self.assertIn("HRWorkbook", content)

    def test_html_has_matrix(self):
        result = self._make_result()
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "report.html")
            out = generate_global_html_report(result, output_path=path)
            content = open(out, encoding="utf-8").read()
            self.assertIn("Pairwise Merge Score Matrix", content)

    def test_html_has_clusters(self):
        result = self._make_result()
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "report.html")
            out = generate_global_html_report(result, output_path=path)
            content = open(out, encoding="utf-8").read()
            self.assertIn("Merge Clusters", content)
            self.assertIn("Cluster #1", content)

    def test_html_has_isolated(self):
        result = self._make_result()
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "report.html")
            out = generate_global_html_report(result, output_path=path)
            content = open(out, encoding="utf-8").read()
            self.assertIn("Isolated Workbooks", content)
            self.assertIn("HRWorkbook", content)

    def test_html_has_commands(self):
        result = self._make_result()
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "report.html")
            out = generate_global_html_report(result, output_path=path)
            content = open(out, encoding="utf-8").read()
            self.assertIn("python migrate.py", content)
            self.assertIn("--shared-model", content)

    def test_html_escapes_special_chars(self):
        """Workbook names with special chars should be escaped."""
        ext = _make_extracted(tables=[("t1", ["id"])])
        result = run_global_assessment(
            [ext, ext], ['Book<A>', 'Book"B"']
        )
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "report.html")
            out = generate_global_html_report(result, output_path=path)
            content = open(out, encoding="utf-8").read()
            self.assertIn("Book&lt;A&gt;", content)
            self.assertIn("Book&quot;B&quot;", content)


class TestGlobalAssessmentJSON(unittest.TestCase):
    """Test JSON serialization."""

    def test_json_saved(self):
        ext_a = _make_extracted(tables=[("orders", ["id", "amount"])])
        ext_b = _make_extracted(tables=[("orders", ["id", "amount"])])
        result = run_global_assessment([ext_a, ext_b], ["WBA", "WBB"])
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "out.json")
            save_global_assessment_json(result, output_path=path)
            self.assertTrue(os.path.isfile(path))
            data = json.loads(open(path, encoding="utf-8").read())
            self.assertIn("timestamp", data)
            self.assertIn("total_workbooks", data)
            self.assertEqual(data["total_workbooks"], 2)


class TestConsoleSummary(unittest.TestCase):
    """Test console output (smoke test — no crash)."""

    def test_print_summary(self):
        ext_a = _make_extracted(tables=[("orders", ["id"])])
        ext_b = _make_extracted(tables=[("orders", ["id"])])
        result = run_global_assessment([ext_a, ext_b], ["WBA", "WBB"])
        # Should not raise
        print_global_summary(result)

    def test_print_summary_all_isolated(self):
        ext_a = _make_extracted(tables=[("t1", ["id"])])
        ext_b = _make_extracted(
            tables=[("t2", ["id"])], connection_type="mysql"
        )
        result = run_global_assessment([ext_a, ext_b], ["WBA", "WBB"])
        print_global_summary(result)


class TestDataclassSerialize(unittest.TestCase):
    """Test dataclass to_dict methods."""

    def test_workbook_profile_to_dict(self):
        p = WorkbookProfile(name="test", tables=3, measures=5)
        d = p.to_dict()
        self.assertEqual(d["name"], "test")
        self.assertEqual(d["tables"], 3)

    def test_pairwise_score_to_dict(self):
        ps = PairwiseScore(wb_a="A", wb_b="B", merge_score=75,
                           shared_tables=2, recommendation="merge")
        d = ps.to_dict()
        self.assertEqual(d["merge_score"], 75)
        self.assertEqual(d["recommendation"], "merge")

    def test_merge_cluster_to_dict(self):
        mc = MergeCluster(cluster_id=0, workbooks=["A", "B"],
                          shared_tables=["orders"], avg_score=80,
                          recommendation="merge")
        d = mc.to_dict()
        self.assertEqual(d["cluster_id"], 0)
        self.assertEqual(d["workbooks"], ["A", "B"])

    def test_global_assessment_to_dict(self):
        ga = GlobalAssessment(
            total_workbooks=3,
            total_tables=10,
            total_measures=5,
            isolated_workbooks=["X"],
        )
        d = ga.to_dict()
        self.assertEqual(d["total_workbooks"], 3)
        self.assertEqual(d["isolated_workbooks"], ["X"])


if __name__ == '__main__':
    unittest.main()
