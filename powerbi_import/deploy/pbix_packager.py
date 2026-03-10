"""
PBIP → .pbix Packager

Packages a Power BI Project (.pbip) directory into a .pbix file
suitable for upload via the Power BI REST API ``/imports`` endpoint.

A .pbix file is a ZIP archive containing:
  - DataModelSchema     (BIM JSON or TMDL → converted to BIM JSON)
  - Report/Layout       (PBIR report definition serialized)
  - [Content_Types].xml (required OPC content types)
  - *.json metadata     (report settings, etc.)

Note: The PBI REST API accepts .pbix files for import. This packager
creates a *compatible* archive from the .pbip project structure.
"""

import json
import logging
import os
import zipfile
import io
import glob

logger = logging.getLogger(__name__)


class PBIXPackager:
    """Package a .pbip project directory into a .pbix ZIP archive."""

    # OPC content types required for a .pbix
    _CONTENT_TYPES_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="json" ContentType="application/json" />
  <Default Extension="tmdl" ContentType="text/plain" />
  <Default Extension="pbir" ContentType="application/json" />
  <Default Extension="xml" ContentType="application/xml" />
</Types>
"""

    def __init__(self):
        pass

    def package(self, pbip_dir, output_path=None):
        """Package a .pbip project directory into a .pbix file.

        Args:
            pbip_dir: Path to the root project directory containing
                ``{name}.Report/`` and ``{name}.SemanticModel/``.
            output_path: Output .pbix file path. If None, creates
                ``{name}.pbix`` next to the project directory.

        Returns:
            str: Path to the created .pbix file.

        Raises:
            FileNotFoundError: If required project files are missing.
        """
        pbip_dir = os.path.abspath(pbip_dir)
        if not os.path.isdir(pbip_dir):
            raise FileNotFoundError(f'Project directory not found: {pbip_dir}')

        # Find .Report and .SemanticModel subdirectories
        report_dir = None
        sm_dir = None
        for entry in os.listdir(pbip_dir):
            full = os.path.join(pbip_dir, entry)
            if os.path.isdir(full):
                if entry.endswith('.Report'):
                    report_dir = full
                elif entry.endswith('.SemanticModel'):
                    sm_dir = full

        if not report_dir:
            raise FileNotFoundError(
                f'No .Report directory found in {pbip_dir}'
            )
        if not sm_dir:
            raise FileNotFoundError(
                f'No .SemanticModel directory found in {pbip_dir}'
            )

        project_name = os.path.basename(report_dir).replace('.Report', '')

        if not output_path:
            output_path = os.path.join(
                os.path.dirname(pbip_dir), f'{project_name}.pbix'
            )

        logger.info(f'Packaging {pbip_dir} → {output_path}')

        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Content types
            zf.writestr('[Content_Types].xml', self._CONTENT_TYPES_XML)

            # Semantic Model — include all TMDL and JSON files
            self._add_directory(zf, sm_dir, 'DataModelSchema')

            # Report — include all report definition files
            self._add_directory(zf, report_dir, 'Report')

            # Project metadata (.pbip file)
            pbip_file = os.path.join(pbip_dir, f'{project_name}.pbip')
            if os.path.exists(pbip_file):
                zf.write(pbip_file, f'{project_name}.pbip')

        logger.info(f'Created .pbix: {output_path} '
                     f'({os.path.getsize(output_path):,} bytes)')
        return output_path

    def _add_directory(self, zf, dir_path, archive_prefix):
        """Recursively add a directory to the ZIP archive.

        Args:
            zf: ZipFile object.
            dir_path: Source directory on disk.
            archive_prefix: Path prefix inside the archive.
        """
        for root, _dirs, files in os.walk(dir_path):
            for fname in files:
                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, dir_path)
                archive_path = os.path.join(archive_prefix, rel_path)
                # Normalize path separators
                archive_path = archive_path.replace('\\', '/')
                zf.write(full_path, archive_path)

    def package_to_bytes(self, pbip_dir):
        """Package a .pbip project into an in-memory bytes buffer.

        Useful for direct upload without writing to disk.

        Args:
            pbip_dir: Path to the project directory.

        Returns:
            bytes: ZIP archive content.
        """
        pbip_dir = os.path.abspath(pbip_dir)
        if not os.path.isdir(pbip_dir):
            raise FileNotFoundError(f'Project directory not found: {pbip_dir}')

        report_dir = None
        sm_dir = None
        for entry in os.listdir(pbip_dir):
            full = os.path.join(pbip_dir, entry)
            if os.path.isdir(full):
                if entry.endswith('.Report'):
                    report_dir = full
                elif entry.endswith('.SemanticModel'):
                    sm_dir = full

        if not report_dir or not sm_dir:
            raise FileNotFoundError('Missing .Report or .SemanticModel directory')

        project_name = os.path.basename(report_dir).replace('.Report', '')

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('[Content_Types].xml', self._CONTENT_TYPES_XML)
            self._add_directory(zf, sm_dir, 'DataModelSchema')
            self._add_directory(zf, report_dir, 'Report')

            pbip_file = os.path.join(pbip_dir, f'{project_name}.pbip')
            if os.path.exists(pbip_file):
                zf.write(pbip_file, f'{project_name}.pbip')

        return buf.getvalue()

    @staticmethod
    def find_pbip_projects(directory):
        """Find all .pbip project directories under a root directory.

        A project directory is identified by having a ``.pbip`` file.

        Args:
            directory: Root directory to search.

        Returns:
            list[str]: Paths to project directories.
        """
        projects = []
        for pbip_file in glob.glob(os.path.join(directory, '**', '*.pbip'),
                                    recursive=True):
            projects.append(os.path.dirname(pbip_file))
        return sorted(set(projects))
