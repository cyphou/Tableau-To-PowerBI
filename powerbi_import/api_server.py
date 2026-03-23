"""REST API server for Tableau-to-Power BI migration.

Sprint 110: Lightweight HTTP wrapper around the migration pipeline.

Endpoints:
    POST /migrate          Upload .twb/.twbx/.tds/.tdsx → returns job ID
    GET  /status/{id}      Check migration job status
    GET  /download/{id}    Download generated .pbip project as ZIP
    GET  /health           Health check

Uses Python stdlib ``http.server`` — zero external dependencies.
Optional: ``pip install fastapi uvicorn`` for production-grade server.

Usage:
    python -m powerbi_import.api_server --port 8000
    python -m powerbi_import.api_server --host 0.0.0.0 --port 8080
"""

import argparse
import io
import json
import logging
import os
import shutil
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)

# Add paths for project imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tableau_export'))

# ── Job store ─────────────────────────────────────────────────────────────────

_jobs = {}  # job_id -> {status, created, input_path, output_dir, error, stats}
_lock = threading.Lock()

MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500 MB


def _new_job(input_path):
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _jobs[job_id] = {
            'status': 'queued',
            'created': time.time(),
            'input_path': input_path,
            'output_dir': None,
            'error': None,
            'stats': None,
        }
    return job_id


def _get_job(job_id):
    with _lock:
        return _jobs.get(job_id)


def _update_job(job_id, **kwargs):
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)


# ── Migration worker ──────────────────────────────────────────────────────────

def _run_migration(job_id, input_path, options=None):
    """Run migration in a background thread."""
    options = options or {}
    _update_job(job_id, status='running')

    try:
        output_dir = tempfile.mkdtemp(prefix=f'pbi_api_{job_id}_')
        _update_job(job_id, output_dir=output_dir)

        # Import migration modules
        from tableau_export.extract_tableau_data import TableauExtractor
        from powerbi_import.import_to_powerbi import PowerBIImporter

        # Step 1: Extract
        extractor = TableauExtractor(input_path)
        extractor.extract_all()

        # Step 2: Generate
        report_name = os.path.splitext(os.path.basename(input_path))[0]
        src_dir = os.path.dirname(os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', 'tableau_export')
        ))
        importer = PowerBIImporter(os.path.join(src_dir, 'tableau_export'))

        converted = importer._load_converted_objects()
        importer.generate_powerbi_project(
            report_name=report_name,
            converted_objects=converted,
            output_dir=output_dir,
            calendar_start=options.get('calendar_start'),
            calendar_end=options.get('calendar_end'),
            culture=options.get('culture'),
            model_mode=options.get('model_mode', 'import'),
        )

        _update_job(job_id, status='completed', stats={
            'report_name': report_name,
            'output_dir': output_dir,
        })

    except Exception as exc:
        logger.exception("Migration failed for job %s", job_id)
        _update_job(job_id, status='failed', error=str(exc))


# ── HTTP Handler ──────────────────────────────────────────────────────────────

class MigrationHandler(BaseHTTPRequestHandler):
    """HTTP request handler for migration API."""

    def _send_json(self, data, status=200):
        body = json.dumps(data, indent=2).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status, message):
        self._send_json({'error': message}, status=status)

    def _get_path(self):
        parsed = urlparse(self.path)
        return parsed.path.rstrip('/')

    def do_GET(self):
        path = self._get_path()

        # GET /health
        if path == '/health':
            self._send_json({'status': 'ok', 'version': _get_version()})
            return

        # GET /status/{id}
        if path.startswith('/status/'):
            job_id = path.split('/status/')[-1]
            job = _get_job(job_id)
            if not job:
                self._send_error(404, f'Job {job_id} not found')
                return
            self._send_json({
                'job_id': job_id,
                'status': job['status'],
                'error': job['error'],
                'created': job['created'],
            })
            return

        # GET /download/{id}
        if path.startswith('/download/'):
            job_id = path.split('/download/')[-1]
            job = _get_job(job_id)
            if not job:
                self._send_error(404, f'Job {job_id} not found')
                return
            if job['status'] != 'completed':
                self._send_error(400, f'Job {job_id} is {job["status"]}, not completed')
                return
            output_dir = job.get('output_dir')
            if not output_dir or not os.path.isdir(output_dir):
                self._send_error(500, 'Output directory not found')
                return

            # Create ZIP from output directory
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root, _dirs, files in os.walk(output_dir):
                    for fname in files:
                        full = os.path.join(root, fname)
                        arcname = os.path.relpath(full, output_dir)
                        zf.write(full, arcname)
            zip_bytes = buf.getvalue()

            self.send_response(200)
            self.send_header('Content-Type', 'application/zip')
            self.send_header('Content-Disposition',
                             f'attachment; filename="{job_id}.zip"')
            self.send_header('Content-Length', str(len(zip_bytes)))
            self.end_headers()
            self.wfile.write(zip_bytes)
            return

        # GET /jobs
        if path == '/jobs':
            with _lock:
                jobs_list = [
                    {'job_id': jid, 'status': j['status'], 'created': j['created']}
                    for jid, j in _jobs.items()
                ]
            self._send_json({'jobs': jobs_list})
            return

        self._send_error(404, 'Not found')

    def do_POST(self):
        path = self._get_path()

        # POST /migrate
        if path == '/migrate':
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > MAX_UPLOAD_SIZE:
                self._send_error(413, 'File too large (max 500 MB)')
                return
            if content_length == 0:
                self._send_error(400, 'No file uploaded')
                return

            # Read uploaded file
            body = self.rfile.read(content_length)

            # Parse multipart or raw file upload
            content_type = self.headers.get('Content-Type', '')
            filename = 'upload.twbx'
            file_data = body

            if 'multipart/form-data' in content_type:
                # Parse multipart boundary
                parts = content_type.split('boundary=')
                if len(parts) < 2:
                    self._send_error(400, 'Invalid multipart boundary')
                    return
                boundary = parts[1].strip().encode()
                parsed = _parse_multipart(body, boundary)
                if not parsed:
                    self._send_error(400, 'No file found in multipart data')
                    return
                filename, file_data = parsed
            elif 'application/json' in content_type:
                # JSON body with base64-encoded file
                try:
                    import base64
                    payload = json.loads(body)
                    filename = payload.get('filename', 'upload.twbx')
                    file_data = base64.b64decode(payload['file'])
                except (json.JSONDecodeError, KeyError, Exception) as exc:
                    self._send_error(400, f'Invalid JSON payload: {exc}')
                    return

            # Validate extension
            ext = os.path.splitext(filename)[1].lower()
            if ext not in ('.twb', '.twbx', '.tds', '.tdsx'):
                self._send_error(400,
                    f'Unsupported file type: {ext}. Use .twb, .twbx, .tds, or .tdsx')
                return

            # Save to temp file
            tmp = tempfile.NamedTemporaryFile(
                suffix=ext, prefix='migration_', delete=False
            )
            tmp.write(file_data)
            tmp.close()

            # Parse migration options from query string
            parsed_url = urlparse(self.path)
            params = parse_qs(parsed_url.query)
            options = {
                'calendar_start': _int_param(params, 'calendar_start'),
                'calendar_end': _int_param(params, 'calendar_end'),
                'culture': params.get('culture', [None])[0],
                'model_mode': params.get('model_mode', ['import'])[0],
            }

            # Create job and start migration
            job_id = _new_job(tmp.name)
            thread = threading.Thread(
                target=_run_migration,
                args=(job_id, tmp.name, options),
                daemon=True,
            )
            thread.start()

            self._send_json({
                'job_id': job_id,
                'status': 'queued',
                'filename': filename,
            }, status=202)
            return

        self._send_error(404, 'Not found')

    def log_message(self, format, *args):
        logger.info(format, *args)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_multipart(body, boundary):
    """Extract first file from multipart/form-data body."""
    parts = body.split(b'--' + boundary)
    for part in parts:
        if b'filename=' not in part:
            continue
        # Extract filename
        header_end = part.find(b'\r\n\r\n')
        if header_end < 0:
            continue
        headers = part[:header_end].decode('utf-8', errors='replace')
        data = part[header_end + 4:]
        # Trim trailing \r\n
        if data.endswith(b'\r\n'):
            data = data[:-2]

        filename = 'upload.twbx'
        for line in headers.split('\r\n'):
            if 'filename=' in line:
                parts2 = line.split('filename=')
                if len(parts2) > 1:
                    filename = parts2[1].strip('"').strip("'")
                    # Security: strip path components
                    filename = os.path.basename(filename)
                break
        return filename, data
    return None


def _int_param(params, key):
    vals = params.get(key, [None])
    val = vals[0]
    if val is not None:
        try:
            return int(val)
        except (ValueError, TypeError):
            pass
    return None


def _get_version():
    try:
        from powerbi_import import __version__
        return __version__
    except ImportError:
        return 'unknown'


# ── Server entry point ────────────────────────────────────────────────────────

def run_server(host='127.0.0.1', port=8000):
    """Start the migration API server."""
    server = HTTPServer((host, port), MigrationHandler)
    print(f"Migration API server running on http://{host}:{port}")
    print(f"  POST /migrate     Upload .twb/.twbx/.tds/.tdsx for migration")
    print(f"  GET  /status/{{id}} Check job status")
    print(f"  GET  /download/{{id}} Download result as ZIP")
    print(f"  GET  /health      Health check")
    print(f"  GET  /jobs        List all jobs")
    print()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description='Migration REST API server')
    parser.add_argument('--host', default='127.0.0.1',
                        help='Bind address (default: 127.0.0.1)')
    parser.add_argument('--port', type=int, default=8000,
                        help='Port number (default: 8000)')
    args = parser.parse_args()
    run_server(args.host, args.port)


if __name__ == '__main__':
    main()
