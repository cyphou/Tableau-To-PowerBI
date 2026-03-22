"""
Shapefile/GeoJSON Passthrough — extract geographic boundary files from
Tableau .twbx packages and configure Power BI Shape Map visuals.

Supports:
- .geojson / .json (GeoJSON)
- .topojson
- .shp + .shx + .dbf (Shapefile components)

Extracted files are placed in the PBI project's ``RegisteredResources/``
directory and wired into shape map visual configurations.

Usage:
    from powerbi_import.geo_passthrough import GeoExtractor
    extractor = GeoExtractor(twbx_path, output_dir)
    geo_files = extractor.extract()
    config = extractor.build_shape_map_config(geo_files, key_column="Region")
"""

import json
import logging
import os
import zipfile

logger = logging.getLogger('tableau_to_powerbi.geo_passthrough')

# File extensions we recognise as geographic boundary data
_GEO_EXTENSIONS = frozenset({
    '.geojson', '.topojson', '.json', '.shp', '.shx', '.dbf', '.prj', '.cpg',
})

# Shapefile component extensions (must travel together)
_SHP_COMPONENTS = frozenset({'.shp', '.shx', '.dbf', '.prj', '.cpg'})


class GeoExtractor:
    """Extract geographic files from a Tableau .twbx/.tdsx archive."""

    def __init__(self, tableau_file, output_dir):
        self.tableau_file = tableau_file
        self.output_dir = output_dir

    def extract(self):
        """Scan the archive and extract geographic files.

        Returns:
            list of dicts, each with:
                - ``filename``: basename of the extracted file
                - ``format``: 'geojson' | 'topojson' | 'shapefile'
                - ``output_path``: absolute path where the file was written
                - ``zip_path``: original path inside the archive
        """
        ext = os.path.splitext(self.tableau_file)[1].lower()
        if ext not in ('.twbx', '.tdsx'):
            logger.debug("Not an archive file — skipping geo extraction")
            return []

        results = []
        geo_dir = os.path.join(self.output_dir, 'geo')

        try:
            with zipfile.ZipFile(self.tableau_file, 'r') as z:
                for entry in z.namelist():
                    if entry.endswith('/'):
                        continue
                    file_ext = os.path.splitext(entry)[1].lower()
                    if file_ext not in _GEO_EXTENSIONS:
                        continue

                    filename = os.path.basename(entry)
                    if not filename:
                        continue

                    # Determine format
                    fmt = _classify_format(file_ext, filename)

                    # Extract safely
                    os.makedirs(geo_dir, exist_ok=True)
                    target = os.path.join(geo_dir, filename)
                    # Prevent path traversal
                    real_geo = os.path.realpath(geo_dir)
                    real_target = os.path.realpath(target)
                    if not real_target.startswith(real_geo):
                        logger.warning("Skipped suspicious path: %s", entry)
                        continue

                    with z.open(entry) as src:
                        data = src.read()
                    with open(target, 'wb') as dst:
                        dst.write(data)

                    results.append({
                        'filename': filename,
                        'format': fmt,
                        'output_path': target,
                        'zip_path': entry,
                        'size_bytes': len(data),
                    })
                    logger.info("Extracted geo file: %s (%s)", filename, fmt)

        except (zipfile.BadZipFile, OSError) as exc:
            logger.error("Failed to extract geo files: %s", exc)

        return results

    def build_shape_map_config(self, geo_files, key_column=None):
        """Build Power BI shapeMap visual configuration from extracted files.

        Args:
            geo_files: list from ``extract()``
            key_column: column name to use as shape key binding

        Returns:
            dict suitable for embedding in a visual container's config
        """
        # Prefer GeoJSON/TopoJSON over Shapefile
        geojson_files = [g for g in geo_files
                         if g['format'] in ('geojson', 'topojson')]
        if not geojson_files:
            # If only shapefiles, convert to GeoJSON reference
            shp_files = [g for g in geo_files if g['format'] == 'shapefile']
            if shp_files:
                geojson_files = shp_files[:1]

        if not geojson_files:
            return {}

        primary = geojson_files[0]
        resource_name = primary['filename']

        # Read GeoJSON to extract property keys for binding suggestion
        properties = _extract_geojson_properties(primary['output_path'])

        config = {
            'visualType': 'shapeMap',
            'shapeMapConfig': {
                'mapSource': 'custom',
                'customMapUrl': f'RegisteredResources/{resource_name}',
                'resourceName': resource_name,
                'keyProperty': key_column or (properties[0] if properties else 'name'),
                'availableProperties': properties,
            },
            'registeredResource': {
                'name': resource_name,
                'path': primary['output_path'],
            },
        }
        return config

    def copy_to_registered_resources(self, geo_files, pbip_dir):
        """Copy geo files into the PBI project's RegisteredResources directory.

        Args:
            geo_files: list from ``extract()``
            pbip_dir: root of the .pbip project

        Returns:
            list of copied file paths
        """
        res_dir = os.path.join(pbip_dir, 'RegisteredResources')
        os.makedirs(res_dir, exist_ok=True)
        copied = []
        for gf in geo_files:
            src = gf['output_path']
            dst = os.path.join(res_dir, gf['filename'])
            if os.path.exists(src):
                with open(src, 'rb') as f_in:
                    data = f_in.read()
                with open(dst, 'wb') as f_out:
                    f_out.write(data)
                copied.append(dst)
        return copied


def _classify_format(file_ext, filename):
    """Classify a geo file by its extension."""
    lower = filename.lower()
    if file_ext == '.geojson' or (file_ext == '.json' and 'geo' in lower):
        return 'geojson'
    if file_ext == '.topojson' or (file_ext == '.json' and 'topo' in lower):
        return 'topojson'
    if file_ext in _SHP_COMPONENTS:
        return 'shapefile'
    if file_ext == '.json':
        return 'geojson'  # default assumption for .json in geo context
    return 'unknown'


def _extract_geojson_properties(filepath):
    """Read a GeoJSON file and return the property keys from the first feature."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        features = data.get('features', [])
        if features and isinstance(features[0], dict):
            props = features[0].get('properties', {})
            return list(props.keys())
    except (json.JSONDecodeError, OSError, KeyError, IndexError):
        pass
    return []


def geojson_to_shape_map_resource(geojson_path, resource_name=None):
    """Create a PBI RegisteredResources entry from a standalone GeoJSON file.

    Args:
        geojson_path: path to the .geojson file
        resource_name: optional name (defaults to filename)

    Returns:
        dict with resource metadata
    """
    fname = resource_name or os.path.basename(geojson_path)
    properties = _extract_geojson_properties(geojson_path)
    size = os.path.getsize(geojson_path) if os.path.exists(geojson_path) else 0
    return {
        'name': fname,
        'path': geojson_path,
        'format': 'geojson',
        'properties': properties,
        'size_bytes': size,
    }
