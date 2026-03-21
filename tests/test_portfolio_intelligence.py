"""
Sprint 88 — Enterprise Portfolio Intelligence Tests.

Validates data lineage graph, consolidation recommender,
resource allocation planner, and governance report generation.
"""

import os
import shutil
import tempfile
import unittest
from dataclasses import dataclass, field
from typing import List

from powerbi_import.global_assessment import (
    GlobalAssessment,
    MergeCluster,
    WorkbookProfile,
    build_data_lineage,
    recommend_consolidation,
    plan_resource_allocation,
    generate_governance_report,
)


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _sample_extracted(name='WB1', n_tables=2, n_calcs=1, n_worksheets=1):
    """Build a minimal extracted dict for testing."""
    tables = [{'name': f'Table{i}', 'columns': [{'name': 'Col1', 'datatype': 'string'}]}
              for i in range(n_tables)]
    calcs = [{'name': f'Calc{i}', 'formula': 'SUM([Col1])'}
             for i in range(n_calcs)]
    worksheets = [{'name': f'Sheet{i}', 'fields': ['Col1', f'Calc0']}
                  for i in range(n_worksheets)]
    return {
        'datasources': [{
            'name': f'DS_{name}',
            'caption': f'DataSource {name}',
            'connection': {'type': 'SQL Server'},
            'tables': tables,
            'calculations': calcs,
        }],
        'worksheets': worksheets,
        'calculations': calcs,
        'parameters': [],
    }


def _sample_global_assessment(n_clusters=1, n_isolated=1, avg_score=65):
    """Build a minimal GlobalAssessment for testing."""
    clusters = []
    for i in range(n_clusters):
        clusters.append(MergeCluster(
            cluster_id=i + 1,
            workbooks=[f'WB{i*2+1}', f'WB{i*2+2}'],
            shared_tables=[f'SharedTable{i}'],
            avg_score=avg_score,
            recommendation='merge' if avg_score >= 60 else 'review',
        ))
    isolated = [f'WB_iso_{i}' for i in range(n_isolated)]
    return GlobalAssessment(
        total_workbooks=n_clusters * 2 + n_isolated,
        total_tables=10,
        total_measures=5,
        merge_clusters=clusters,
        isolated_workbooks=isolated,
    )


@dataclass
class MockWave:
    wave_number: int = 1
    label: str = 'Easy (quick wins)'
    workbooks: list = field(default_factory=lambda: ['WB1'])
    total_effort: float = 8.0


@dataclass
class MockServerAssessment:
    waves: list = field(default_factory=list)
    total_effort_hours: float = 0
    green_count: int = 0
    yellow_count: int = 0
    red_count: int = 0


# ═══════════════════════════════════════════════════════════════════
# 1. Data lineage graph (88.1)
# ═══════════════════════════════════════════════════════════════════

class TestDataLineage(unittest.TestCase):
    """88.1 — Build cross-workbook data lineage graph."""

    def test_single_workbook_lineage(self):
        ext = _sample_extracted('WB1')
        lineage = build_data_lineage([ext], ['WB1'])
        self.assertIn('nodes', lineage)
        self.assertIn('edges', lineage)
        self.assertGreater(len(lineage['nodes']), 0)

    def test_lineage_node_types(self):
        ext = _sample_extracted('WB1')
        lineage = build_data_lineage([ext], ['WB1'])
        types = {n['type'] for n in lineage['nodes']}
        self.assertIn('datasource', types)
        self.assertIn('table', types)

    def test_cross_workbook_shared_table(self):
        ext1 = _sample_extracted('WB1')
        ext2 = _sample_extracted('WB2')
        lineage = build_data_lineage([ext1, ext2], ['WB1', 'WB2'])
        # Table0 exists in both workbooks
        table_nodes = [n for n in lineage['nodes'] if n['type'] == 'table' and n['name'] == 'Table0']
        self.assertEqual(len(table_nodes), 1)  # Deduplicated
        self.assertEqual(len(table_nodes[0]['workbooks']), 2)

    def test_edges_datasource_to_table(self):
        ext = _sample_extracted('WB1')
        lineage = build_data_lineage([ext], ['WB1'])
        contains_edges = [e for e in lineage['edges'] if e['type'] == 'contains']
        self.assertGreater(len(contains_edges), 0)

    def test_empty_workbooks(self):
        lineage = build_data_lineage([], [])
        self.assertEqual(lineage['nodes'], [])
        self.assertEqual(lineage['edges'], [])

    def test_calculation_nodes(self):
        ext = _sample_extracted('WB1', n_calcs=2)
        lineage = build_data_lineage([ext], ['WB1'])
        calc_nodes = [n for n in lineage['nodes'] if n['type'] == 'calculation']
        self.assertGreaterEqual(len(calc_nodes), 1)


# ═══════════════════════════════════════════════════════════════════
# 2. Consolidation recommender (88.2)
# ═══════════════════════════════════════════════════════════════════

class TestConsolidationRecommender(unittest.TestCase):
    """88.2 — Recommend shared model vs standalone."""

    def test_high_overlap_recommends_shared(self):
        ga = _sample_global_assessment(n_clusters=1, avg_score=75)
        recs = recommend_consolidation(ga)
        shared = [r for r in recs if r['action'] == 'shared_model']
        self.assertEqual(len(shared), 1)

    def test_moderate_overlap_recommends_partial(self):
        ga = _sample_global_assessment(n_clusters=1, avg_score=50)
        recs = recommend_consolidation(ga)
        partial = [r for r in recs if r['action'] == 'partial_merge']
        self.assertEqual(len(partial), 1)

    def test_low_overlap_recommends_review(self):
        ga = _sample_global_assessment(n_clusters=1, avg_score=35)
        recs = recommend_consolidation(ga)
        review = [r for r in recs if r['action'] == 'review']
        self.assertEqual(len(review), 1)

    def test_isolated_recommends_standalone(self):
        ga = _sample_global_assessment(n_clusters=0, n_isolated=3)
        recs = recommend_consolidation(ga)
        standalone = [r for r in recs if r['action'] == 'standalone']
        self.assertEqual(len(standalone), 3)

    def test_mixed_clusters_and_isolated(self):
        ga = _sample_global_assessment(n_clusters=2, n_isolated=1, avg_score=80)
        recs = recommend_consolidation(ga)
        self.assertEqual(len(recs), 3)  # 2 clusters + 1 isolated

    def test_recommendation_has_reason(self):
        ga = _sample_global_assessment(n_clusters=1, avg_score=70)
        recs = recommend_consolidation(ga)
        for r in recs:
            self.assertIn('reason', r)
            self.assertGreater(len(r['reason']), 10)


# ═══════════════════════════════════════════════════════════════════
# 3. Resource allocation planner (88.3)
# ═══════════════════════════════════════════════════════════════════

class TestResourceAllocationPlanner(unittest.TestCase):
    """88.3 — Plan team allocation based on wave complexity."""

    def test_basic_allocation(self):
        sa = MockServerAssessment(
            waves=[MockWave(1, 'Easy (quick wins)', ['WB1'], 8.0)],
            total_effort_hours=8.0,
        )
        alloc = plan_resource_allocation(sa, team_size=3)
        self.assertEqual(alloc['team_size'], 3)
        self.assertEqual(alloc['total_effort_hours'], 8.0)
        self.assertEqual(len(alloc['waves']), 1)

    def test_complex_wave_skill_mix(self):
        sa = MockServerAssessment(
            waves=[MockWave(2, 'Complex (manual review)', ['WB1', 'WB2'], 40.0)],
            total_effort_hours=40.0,
        )
        alloc = plan_resource_allocation(sa, team_size=4)
        wave = alloc['waves'][0]
        self.assertEqual(wave['skill_mix']['dax_expert'], 1)
        self.assertEqual(wave['skill_mix']['m_expert'], 1)

    def test_easy_wave_all_designers(self):
        sa = MockServerAssessment(
            waves=[MockWave(1, 'Easy (quick wins)', ['WB1'], 4.0)],
            total_effort_hours=4.0,
        )
        alloc = plan_resource_allocation(sa, team_size=3)
        wave = alloc['waves'][0]
        self.assertEqual(wave['skill_mix']['dax_expert'], 0)
        self.assertEqual(wave['skill_mix']['visual_designer'], 3)

    def test_empty_waves(self):
        sa = MockServerAssessment(waves=[], total_effort_hours=0)
        alloc = plan_resource_allocation(sa)
        self.assertEqual(len(alloc['waves']), 0)

    def test_estimated_weeks(self):
        sa = MockServerAssessment(
            waves=[MockWave(1, 'Medium (standard)', ['WB1'], 120.0)],
            total_effort_hours=120.0,
        )
        alloc = plan_resource_allocation(sa, team_size=3)
        wave = alloc['waves'][0]
        self.assertGreater(wave['estimated_weeks'], 0)


# ═══════════════════════════════════════════════════════════════════
# 4. Governance report (88.4)
# ═══════════════════════════════════════════════════════════════════

class TestGovernanceReport(unittest.TestCase):
    """88.4 — Generate executive governance HTML report."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_generates_html_file(self):
        ga = _sample_global_assessment(1, 1, 65)
        path = os.path.join(self.tmp, 'gov.html')
        result = generate_governance_report(ga, output_path=path)
        self.assertTrue(os.path.isfile(result))

    def test_html_contains_title(self):
        ga = _sample_global_assessment(1, 0, 70)
        path = os.path.join(self.tmp, 'gov.html')
        generate_governance_report(ga, output_path=path)
        with open(path, encoding='utf-8') as f:
            html = f.read()
        self.assertIn('Governance Report', html)

    def test_html_with_server_assessment(self):
        ga = _sample_global_assessment(1, 0, 70)
        sa = MockServerAssessment(
            waves=[MockWave(1, 'Easy', ['WB1'], 8.0)],
            total_effort_hours=8.0,
            green_count=1,
        )
        path = os.path.join(self.tmp, 'gov.html')
        generate_governance_report(ga, server_assessment=sa, output_path=path)
        with open(path, encoding='utf-8') as f:
            html = f.read()
        self.assertIn('GREEN', html)

    def test_html_without_server_assessment(self):
        ga = _sample_global_assessment(0, 2, 0)
        path = os.path.join(self.tmp, 'gov.html')
        generate_governance_report(ga, output_path=path)
        self.assertTrue(os.path.isfile(path))

    def test_html_contains_clusters(self):
        ga = _sample_global_assessment(2, 0, 60)
        path = os.path.join(self.tmp, 'gov.html')
        generate_governance_report(ga, output_path=path)
        with open(path, encoding='utf-8') as f:
            html = f.read()
        self.assertIn('Cluster 1', html)
        self.assertIn('Cluster 2', html)


if __name__ == '__main__':
    unittest.main()
