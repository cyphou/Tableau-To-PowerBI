"""
Thin Report Generator — creates report-only PBIR projects that reference
a shared semantic model via byPath.

Each thin report contains:
- {ReportName}.Report/ directory with PBIR visuals and pages
- definition.pbir → byPath pointing to the shared SemanticModel
- No SemanticModel directory (lives in the shared project)

Usage::

    from powerbi_import.thin_report_generator import ThinReportGenerator

    gen = ThinReportGenerator("SharedModel", "/output/dir")
    gen.generate_thin_report("SalesOverview", converted_objects, field_mapping)
"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import uuid

logger = logging.getLogger(__name__)


class ThinReportGenerator:
    """Generates a thin report (.Report/) referencing an external semantic model."""

    def __init__(self, semantic_model_name: str, output_dir: str):
        """
        Args:
            semantic_model_name: Name of the shared semantic model directory.
            output_dir: Root output directory where reports are created.
        """
        self.semantic_model_name = semantic_model_name
        self.output_dir = os.path.abspath(output_dir)

    def generate_thin_report(self, report_name: str,
                             converted_objects: dict,
                             field_mapping: dict = None) -> str:
        """Generate a thin report referencing the shared semantic model.

        Args:
            report_name: Name for the report.
            converted_objects: Original workbook's extracted objects.
            field_mapping: Optional mapping of original → namespaced field names.

        Returns:
            Path to the generated report directory.
        """
        # Apply field remapping if needed
        if field_mapping:
            converted_objects = self._remap_fields(converted_objects, field_mapping)

        report_dir = os.path.join(self.output_dir, f"{report_name}.Report")
        os.makedirs(report_dir, exist_ok=True)

        # 1. Create .platform
        self._write_platform(report_dir, report_name)

        # 2. Create definition.pbir → byPath to shared model
        self._write_definition_pbir(report_dir)

        # 3. Create .pbip file for this report
        self._write_pbip(report_name)

        # 4. Generate report content (pages, visuals, filters) using pbip_generator
        self._generate_report_content(report_dir, report_name, converted_objects)

        logger.info("Thin report generated: %s", report_dir)
        return report_dir

    def _write_platform(self, report_dir: str, report_name: str):
        """Write the .platform file for the report."""
        platform = {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {
                "type": "Report",
                "displayName": report_name,
            },
            "config": {
                "version": "2.0",
                "logicalId": str(uuid.uuid4()),
            },
        }
        _write_json(os.path.join(report_dir, '.platform'), platform)

    def _write_definition_pbir(self, report_dir: str):
        """Write definition.pbir with byPath reference to the shared semantic model."""
        report_definition = {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
            "version": "4.0",
            "datasetReference": {
                "byPath": {
                    "path": f"../{self.semantic_model_name}.SemanticModel",
                },
            },
        }
        _write_json(os.path.join(report_dir, 'definition.pbir'), report_definition)

    def _write_pbip(self, report_name: str):
        """Write a .pbip file for this thin report."""
        pbip_content = {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
            "version": "1.0",
            "artifacts": [
                {
                    "report": {
                        "path": f"{report_name}.Report",
                    },
                },
            ],
            "settings": {
                "enableAutoRecovery": True,
            },
        }
        pbip_path = os.path.join(self.output_dir, f"{report_name}.pbip")
        _write_json(pbip_path, pbip_content)

    def _generate_report_content(self, report_dir: str, report_name: str,
                                  converted_objects: dict):
        """Generate the report definition (pages, visuals, filters, theme).

        Reuses the existing PowerBIProjectGenerator's report content logic
        by importing and calling it with the external semantic model reference.
        """
        try:
            from powerbi_import.pbip_generator import PowerBIProjectGenerator
        except ImportError:
            from pbip_generator import PowerBIProjectGenerator

        # Create a temporary generator to reuse report content creation
        generator = PowerBIProjectGenerator(output_dir=self.output_dir)

        # Use the existing report creation method but with a custom byPath
        # The report_dir is already created, so we directly call the internal
        # content generation parts
        generator._generate_report_definition_content(
            report_dir, report_name, converted_objects
        )

    def _remap_fields(self, converted_objects: dict,
                      field_mapping: dict) -> dict:
        """Remap field names in worksheets, dashboards, and filters."""
        if not field_mapping:
            return converted_objects

        remapped = copy.deepcopy(converted_objects)

        # Remap worksheet column references
        for ws in remapped.get('worksheets', []):
            for col in ws.get('columns', []):
                name = col.get('name', '')
                if name in field_mapping:
                    col['name'] = field_mapping[name]
            # Remap filters
            for f in ws.get('filters', []):
                fname = f.get('field', '')
                if fname in field_mapping:
                    f['field'] = field_mapping[fname]
            # Remap mark encoding
            for channel, enc in ws.get('mark_encoding', {}).items():
                if isinstance(enc, dict):
                    efield = enc.get('field', '')
                    if efield in field_mapping:
                        enc['field'] = field_mapping[efield]

        # Remap calculation references in standalone calculations
        for calc in remapped.get('calculations', []):
            caption = calc.get('caption', '')
            if caption in field_mapping:
                calc['caption'] = field_mapping[caption]

        # Remap filter fields
        for f in remapped.get('filters', []):
            fname = f.get('field', '')
            if fname in field_mapping:
                f['field'] = field_mapping[fname]

        return remapped


def _write_json(filepath: str, data: dict):
    """Write JSON to file with consistent formatting."""
    os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
