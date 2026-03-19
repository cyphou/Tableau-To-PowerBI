"""
Deployment utilities and helpers.

Provides deployment reporting and artifact metadata caching
for Fabric workspace deployments.
"""

import os
import json
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class DeploymentReport:
    """Generate deployment reports with pass/fail tracking."""

    def __init__(self, workspace_id=''):
        """Initialize report.

        Args:
            workspace_id: Target Fabric workspace ID
        """
        self.workspace_id = workspace_id
        self.timestamp = datetime.now()
        self.results = []

    def add_result(self, artifact_name, artifact_type, status,
                   item_id=None, error=None):
        """Add a deployment result.

        Args:
            artifact_name: Name of the artifact
            artifact_type: Type (Dataset, Report, SemanticModel, etc.)
            status: 'success' or 'failed'
            item_id: Fabric item ID (if deployed)
            error: Error message (if failed)
        """
        self.results.append({
            'timestamp': datetime.now().isoformat(),
            'artifact_name': artifact_name,
            'artifact_type': artifact_type,
            'status': status,
            'item_id': item_id,
            'error': error,
        })

    def to_dict(self):
        """Export as dictionary."""
        return {
            'workspace_id': self.workspace_id,
            'deployment_time': self.timestamp.isoformat(),
            'total_artifacts': len(self.results),
            'successful': sum(1 for r in self.results if r['status'] == 'success'),
            'failed': sum(1 for r in self.results if r['status'] == 'failed'),
            'results': self.results,
        }

    def to_json(self):
        """Export as formatted JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    def save(self, output_path):
        """Save report to a JSON file.

        Args:
            output_path: Path to save the report
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(self.to_json())
        logger.info(f'Report saved: {output_path}')

    def print_summary(self):
        """Print deployment summary to console."""
        total = len(self.results)
        successful = sum(1 for r in self.results if r['status'] == 'success')
        failed = total - successful

        print(f'\n{"=" * 60}')
        print(f'  Deployment Summary')
        print(f'{"=" * 60}')
        print(f'  Workspace: {self.workspace_id}')
        print(f'  Time:      {self.timestamp}')
        print(f'  Total:     {total} | Success: {successful} | Failed: {failed}')

        if failed > 0:
            print(f'\n  Failed Artifacts:')
            for result in self.results:
                if result['status'] == 'failed':
                    print(f"    [FAIL] {result['artifact_name']}: {result['error']}")
        print()


class ArtifactCache:
    """Simple JSON-based cache for artifact metadata.

    Stores deployment metadata (item IDs, last-modified timestamps)
    to enable incremental deployment.
    """

    def __init__(self, cache_file=None):
        """Initialize cache.

        Args:
            cache_file: Path to cache file (default: .fabric_cache)
        """
        self.cache_file = Path(cache_file or '.fabric_cache')
        self.cache = {}
        self.load()

    def load(self):
        """Load cache from disk."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    self.cache = json.load(f)
            except (json.JSONDecodeError, Exception):
                self.cache = {}

    def save(self):
        """Persist cache to disk."""
        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(self.cache, f, indent=2, default=str)

    def get(self, key):
        """Get a cached value.

        Args:
            key: Cache key

        Returns:
            Cached dict or None
        """
        return self.cache.get(key)

    def set(self, key, value):
        """Set a cached value and persist.

        Args:
            key: Cache key
            value: Dict to cache
        """
        self.cache[key] = value
        self.save()

    def clear(self):
        """Clear all cached entries."""
        self.cache = {}
        self.save()


class DeploymentManifest:
    """Track deployment metadata for reproducibility and auditing."""

    def __init__(self, workspace_id, model_name=''):
        self.workspace_id = workspace_id
        self.model_name = model_name
        self.timestamp = datetime.now().isoformat()
        self.model_id = None
        self.report_ids = []
        self.source_hash = None
        self.principal = None
        self.version = None

    def to_dict(self):
        return {
            'workspace_id': self.workspace_id,
            'model_name': self.model_name,
            'timestamp': self.timestamp,
            'model_id': self.model_id,
            'report_ids': self.report_ids,
            'source_hash': self.source_hash,
            'principal': self.principal,
            'version': self.version,
        }

    def save(self, output_path):
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info('Deployment manifest saved: %s', output_path)

    @classmethod
    def load(cls, path):
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        m = cls(data.get('workspace_id', ''), data.get('model_name', ''))
        m.timestamp = data.get('timestamp', '')
        m.model_id = data.get('model_id')
        m.report_ids = data.get('report_ids', [])
        m.source_hash = data.get('source_hash')
        m.principal = data.get('principal')
        m.version = data.get('version')
        return m
