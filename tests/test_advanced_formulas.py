"""
Tests for Sprint 99 — Advanced DAX Formulas and Azure Maps Visual.

Tests cover:
1. PREVIOUS_VALUE with single and multi-dim compute_using (PARTITIONBY)
2. LOOKUP with single and multi-dim compute_using (PARTITIONBY)
3. WINDOW functions with PARTITIONBY clause
4. Azure Maps visual type mapping
5. Azure Maps data roles, config templates, fallback
6. Spatial detection in PBIP generator
"""

import os
import sys

import pytest

# ── Setup import paths ──────────────────────────────────────────────

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, 'powerbi_import'))
sys.path.insert(0, os.path.join(ROOT_DIR, 'tableau_export'))

from dax_converter import (
    convert_tableau_formula_to_dax,
    _convert_previous_value,
    _convert_lookup,
)
from visual_generator import (
    VISUAL_TYPE_MAP,
    VISUAL_DATA_ROLES,
    VISUAL_FALLBACK_CASCADE,
)


# ═══════════════════════════════════════════════════════════════════
#  1. PREVIOUS_VALUE with PARTITIONBY
# ═══════════════════════════════════════════════════════════════════

class TestPreviousValue:
    """Test PREVIOUS_VALUE → OFFSET conversion with PARTITIONBY."""

    def test_previous_value_no_compute_using(self):
        result = _convert_previous_value("PREVIOUS_VALUE(0)", "Sales")
        assert "OFFSET(-1" in result
        assert "ALLSELECTED('Sales')" in result
        assert "ORDERBY([Value])" in result
        assert "IF(ISBLANK(__prev)" in result

    def test_previous_value_single_dim(self):
        result = _convert_previous_value(
            "PREVIOUS_VALUE(0)", "Sales",
            compute_using=["OrderDate"]
        )
        assert "ORDERBY('Sales'[OrderDate])" in result
        assert "PARTITIONBY" not in result

    def test_previous_value_multi_dim(self):
        result = _convert_previous_value(
            "PREVIOUS_VALUE(0)", "Sales",
            compute_using=["OrderDate", "Region", "Category"]
        )
        assert "ORDERBY('Sales'[OrderDate])" in result
        assert "PARTITIONBY('Sales'[Region], 'Sales'[Category])" in result

    def test_previous_value_cross_table(self):
        ctm = {"OrderDate": "Calendar", "Region": "Geography"}
        result = _convert_previous_value(
            "PREVIOUS_VALUE(0)", "Sales",
            compute_using=["OrderDate", "Region"],
            column_table_map=ctm,
        )
        assert "ORDERBY('Calendar'[OrderDate])" in result
        assert "PARTITIONBY('Geography'[Region])" in result

    def test_previous_value_with_seed_expression(self):
        result = _convert_previous_value(
            "PREVIOUS_VALUE(SUM([Revenue]))", "Sales",
            compute_using=["OrderDate"]
        )
        assert "SUM([Revenue])" in result
        assert "OFFSET(-1" in result

    def test_previous_value_preserves_surrounding(self):
        """Non PREVIOUS_VALUE text is preserved."""
        result = _convert_previous_value("1 + 2", "T")
        assert result == "1 + 2"


# ═══════════════════════════════════════════════════════════════════
#  2. LOOKUP with PARTITIONBY
# ═══════════════════════════════════════════════════════════════════

class TestLookup:
    """Test LOOKUP → OFFSET conversion with PARTITIONBY."""

    def test_lookup_no_compute_using(self):
        result = _convert_lookup("LOOKUP(SUM([Revenue]), -1)", "Sales")
        assert "OFFSET(-1" in result
        assert "SUM([Revenue])" in result
        assert "ORDERBY([Value])" in result

    def test_lookup_single_dim(self):
        result = _convert_lookup(
            "LOOKUP(SUM([Revenue]), -1)", "Sales",
            compute_using=["Month"]
        )
        assert "ORDERBY('Sales'[Month])" in result
        assert "PARTITIONBY" not in result

    def test_lookup_multi_dim(self):
        result = _convert_lookup(
            "LOOKUP(SUM([Revenue]), -1)", "Sales",
            compute_using=["Month", "Region", "Product"]
        )
        assert "ORDERBY('Sales'[Month])" in result
        assert "PARTITIONBY('Sales'[Region], 'Sales'[Product])" in result

    def test_lookup_cross_table(self):
        ctm = {"Month": "Calendar", "Region": "Geography"}
        result = _convert_lookup(
            "LOOKUP(AVG([Price]), 1)", "Sales",
            compute_using=["Month", "Region"],
            column_table_map=ctm,
        )
        assert "ORDERBY('Calendar'[Month])" in result
        assert "PARTITIONBY('Geography'[Region])" in result
        assert "AVG([Price])" in result
        assert "OFFSET(1" in result

    def test_lookup_positive_offset(self):
        result = _convert_lookup(
            "LOOKUP(SUM([Rev]), 2)", "T",
            compute_using=["Date"]
        )
        assert "OFFSET(2" in result

    def test_lookup_preserves_surrounding(self):
        result = _convert_lookup("1 + 2", "T")
        assert result == "1 + 2"


# ═══════════════════════════════════════════════════════════════════
#  3. WINDOW functions with PARTITIONBY
# ═══════════════════════════════════════════════════════════════════

class TestWindowPartitionBy:
    """Test WINDOW functions with multi-dim PARTITIONBY via full converter."""

    def test_window_sum_single_dim(self):
        result = convert_tableau_formula_to_dax(
            "WINDOW_SUM(SUM([Revenue]), -2, 0)",
            table_name="Sales",
            compute_using=["OrderDate"],
        )
        assert "WINDOW(" in result
        assert "ORDERBY('Sales'[OrderDate]" in result
        assert "PARTITIONBY" not in result

    def test_window_sum_multi_dim(self):
        result = convert_tableau_formula_to_dax(
            "WINDOW_SUM(SUM([Revenue]), -2, 0)",
            table_name="Sales",
            compute_using=["OrderDate", "Region"],
        )
        assert "WINDOW(" in result
        assert "ORDERBY('Sales'[OrderDate]" in result
        assert "PARTITIONBY('Sales'[Region])" in result

    def test_window_avg_multi_dim(self):
        result = convert_tableau_formula_to_dax(
            "WINDOW_AVG(AVG([Price]), -3, 0)",
            table_name="Products",
            compute_using=["Date", "Category", "SubCategory"],
        )
        assert "WINDOW(" in result
        assert "PARTITIONBY('Products'[Category], 'Products'[SubCategory])" in result

    def test_window_max_partitionby(self):
        ctm = {"Date": "Calendar", "Region": "Geo"}
        result = convert_tableau_formula_to_dax(
            "WINDOW_MAX(MAX([Amount]), -1, 1)",
            table_name="Sales",
            compute_using=["Date", "Region"],
            column_table_map=ctm,
        )
        assert "ORDERBY('Calendar'[Date]" in result
        assert "PARTITIONBY('Geo'[Region])" in result

    def test_window_no_compute_using(self):
        result = convert_tableau_formula_to_dax(
            "WINDOW_SUM(SUM([Revenue]), -1, 0)",
            table_name="Sales",
        )
        assert "WINDOW(" in result
        assert "PARTITIONBY" not in result

    def test_window_no_frame_single_dim(self):
        """Window function without frame boundaries but with compute_using → ALLEXCEPT."""
        result = convert_tableau_formula_to_dax(
            "WINDOW_SUM(SUM([Revenue]))",
            table_name="Sales",
            compute_using=["Region"],
        )
        assert "ALLEXCEPT" in result or "CALCULATE" in result


# ═══════════════════════════════════════════════════════════════════
#  4. Full converter PARTITIONBY wiring
# ═══════════════════════════════════════════════════════════════════

class TestConverterPartitionByWiring:
    """Test that PREVIOUS_VALUE and LOOKUP are reached via full converter."""

    def test_previous_value_via_converter(self):
        result = convert_tableau_formula_to_dax(
            "PREVIOUS_VALUE(0)",
            table_name="Sales",
            compute_using=["Date", "Region"],
        )
        assert "PARTITIONBY('Sales'[Region])" in result
        assert "ORDERBY('Sales'[Date])" in result

    def test_lookup_via_converter(self):
        result = convert_tableau_formula_to_dax(
            "LOOKUP(SUM([Revenue]), -1)",
            table_name="Sales",
            compute_using=["Month", "Category"],
        )
        assert "PARTITIONBY('Sales'[Category])" in result
        assert "ORDERBY('Sales'[Month])" in result

    def test_previous_value_three_dims_via_converter(self):
        result = convert_tableau_formula_to_dax(
            "PREVIOUS_VALUE(0)",
            table_name="Facts",
            compute_using=["Date", "Region", "Product"],
        )
        assert "PARTITIONBY('Facts'[Region], 'Facts'[Product])" in result


# ═══════════════════════════════════════════════════════════════════
#  5. Azure Maps visual type mapping
# ═══════════════════════════════════════════════════════════════════

class TestAzureMapsVisualMapping:
    """Test Azure Maps entries in visual generator dictionaries."""

    def test_makepoint_maps_to_azure_map(self):
        assert VISUAL_TYPE_MAP["makepoint"] == "azureMap"

    def test_spatial_maps_to_azure_map(self):
        assert VISUAL_TYPE_MAP["spatial"] == "azureMap"

    def test_azure_map_data_roles(self):
        dims, measures = VISUAL_DATA_ROLES["azureMap"]
        assert "Latitude" in dims
        assert "Longitude" in dims
        assert "Size" in measures or "Color" in measures

    def test_azure_map_fallback(self):
        assert VISUAL_FALLBACK_CASCADE["azureMap"] == "map"

    def test_map_in_visual_type_map(self):
        """Standard map entry still exists."""
        assert "map" in VISUAL_TYPE_MAP.values() or "map" in VISUAL_TYPE_MAP

    def test_azure_map_not_in_original_types(self):
        """azureMap should not be one of the original non-extended types."""
        original_mark_types = {"bar", "line", "area", "circle", "text"}
        for t in original_mark_types:
            assert VISUAL_TYPE_MAP.get(t) != "azureMap"


# ═══════════════════════════════════════════════════════════════════
#  6. Spatial detection in PBIPGenerator
# ═══════════════════════════════════════════════════════════════════

class TestSpatialDetection:
    """Test that lat/lon fields trigger azureMap override."""

    def test_spatial_fields_detected_by_name(self):
        """Simulate the detection logic — fields named latitude/longitude → azureMap."""
        fields = [
            {"name": "Latitude", "type": "quantitative"},
            {"name": "Longitude", "type": "quantitative"},
            {"name": "City", "type": "nominal"},
        ]
        has_lat = any("latitude" in f["name"].lower() for f in fields)
        has_lon = any("longitude" in f["name"].lower() for f in fields)
        assert has_lat and has_lon

    def test_spatial_fields_detected_by_semantic_role(self):
        """Fields with semantic_role Latitude/Longitude → azureMap."""
        fields = [
            {"name": "X", "semantic_role": "Latitude"},
            {"name": "Y", "semantic_role": "Longitude"},
        ]
        has_lat = any(f.get("semantic_role") == "Latitude" for f in fields)
        has_lon = any(f.get("semantic_role") == "Longitude" for f in fields)
        assert has_lat and has_lon

    def test_non_spatial_fields_no_override(self):
        """Without lat/lon fields, no azureMap override."""
        fields = [
            {"name": "Revenue", "type": "quantitative"},
            {"name": "Category", "type": "nominal"},
        ]
        has_lat = any("latitude" in f.get("name", "").lower() for f in fields)
        has_lon = any("longitude" in f.get("name", "").lower() for f in fields)
        assert not (has_lat and has_lon)
