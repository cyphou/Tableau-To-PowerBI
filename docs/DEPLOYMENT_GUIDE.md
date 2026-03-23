# Deployment Guide — Fabric REST API

This guide covers deploying generated Power BI projects to Microsoft Fabric workspaces using the tool's built-in deployment pipeline.

---

## Prerequisites

1. **Microsoft Fabric workspace** with capacity assigned
2. **Azure AD App Registration** with the following API permissions:
   - `Power BI Service` → `Dataset.ReadWrite.All`
   - `Power BI Service` → `Report.ReadWrite.All`
   - `Power BI Service` → `Workspace.ReadWrite.All`
3. **Admin consent** granted for the above permissions
4. **Client secret** created for the app registration

## Environment Variables

Create a `.env` file (or set environment variables) based on `.env.example`:

```bash
# Required
FABRIC_WORKSPACE_ID=<your-workspace-guid>
FABRIC_TENANT_ID=<your-azure-ad-tenant-guid>
FABRIC_CLIENT_ID=<your-app-registration-client-id>
FABRIC_CLIENT_SECRET=<your-client-secret>

# Optional
FABRIC_API_BASE_URL=https://api.fabric.microsoft.com/v1
FABRIC_USE_MANAGED_IDENTITY=false
FABRIC_LOG_LEVEL=INFO
FABRIC_LOG_FORMAT=text
FABRIC_DEPLOYMENT_TIMEOUT=300
FABRIC_RETRY_ATTEMPTS=3
FABRIC_RETRY_DELAY=5
```

## Authentication Methods

### Service Principal (Recommended for CI/CD)

Set `FABRIC_TENANT_ID`, `FABRIC_CLIENT_ID`, and `FABRIC_CLIENT_SECRET`. The tool uses `azure-identity`'s `ClientSecretCredential`.

```bash
pip install azure-identity
```

### Managed Identity (For Azure-hosted runners)

Set `FABRIC_USE_MANAGED_IDENTITY=true`. Uses `DefaultAzureCredential` which automatically picks up managed identity credentials.

### No Authentication (Local Dev)

Skip the deployment step and open generated `.pbip` files directly in Power BI Desktop.

## Deployment Pipeline

### Manual Deployment

```bash
# Generate the project
python migrate.py workbook.twbx --output-dir ./output

# Deploy to Fabric (requires azure-identity and requests)
python -c "
from powerbi_import.deployer import FabricDeployer
deployer = FabricDeployer()
report = deployer.deploy_artifacts_batch('./output')
print(report.summary())
"
```

### CI/CD Deployment (GitHub Actions)

The project includes a 5-stage CI/CD pipeline in `.github/workflows/ci.yml`:

1. **Lint** — flake8 + ruff
2. **Test** — unittest on Python 3.9–3.12
3. **Validate** — migrate all sample .twb files, validate artifacts
4. **Deploy Staging** — auto-deploys on `develop` branch push
5. **Deploy Production** — auto-deploys on `main` branch push

#### GitHub Secrets Required

| Secret | Description |
|--------|------------|
| `FABRIC_WORKSPACE_ID` | Target Fabric workspace GUID |
| `FABRIC_TENANT_ID` | Azure AD tenant GUID |
| `FABRIC_CLIENT_ID` | App registration client ID |
| `FABRIC_CLIENT_SECRET` | App registration client secret |
| `STAGING_WORKSPACE_ID` | Staging workspace GUID (for staging deploy) |

#### Staging vs Production

- **Staging** (`deploy-staging` job): Triggered on pushes to `develop` branch. Deploys to the staging workspace.
- **Production** (`deploy-production` job): Triggered on pushes to `main` branch. Deploys to the production workspace with environment approval.

## Environment Configurations

Three pre-configured environments in `powerbi_import/config/environments.py`:

| Setting | Development | Staging | Production |
|---------|------------|---------|------------|
| Log level | DEBUG | INFO | WARNING |
| Timeout (s) | 120 | 300 | 600 |
| Retry attempts | 1 | 3 | 5 |
| Retry delay (s) | 1 | 5 | 10 |
| Approval required | No | No | Yes |

## Retry & Error Handling

The `FabricClient` includes built-in retry logic:

- **HTTP 429** (Rate Limited): Respects `Retry-After` header, waits and retries
- **HTTP 5xx** (Server Error): Retries up to `RETRY_ATTEMPTS` times with `RETRY_DELAY` between attempts
- **Timeout**: Operations time out after `DEPLOYMENT_TIMEOUT` seconds

## REST API Server (Docker)

The migration tool can run as a REST API server for programmatic/headless migration.

### Docker

```bash
docker build -t tableau-to-pbi .
docker run -p 8000:8000 tableau-to-pbi
```

Or run directly:

```bash
python -m powerbi_import.api_server --port 8000
```

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/migrate` | POST | Submit a workbook (multipart upload) for migration |
| `/status/{id}` | GET | Check migration job status |
| `/download/{id}` | GET | Download completed .pbip project as ZIP |
| `/health` | GET | Health check |
| `/jobs` | GET | List all migration jobs |

### Usage Example

```bash
# Upload a workbook for migration
curl -X POST -F "file=@workbook.twbx" http://localhost:8000/migrate
# Returns: {"job_id": "abc123", "status": "queued"}

# Check status
curl http://localhost:8000/status/abc123
# Returns: {"job_id": "abc123", "status": "completed"}

# Download result
curl -o output.zip http://localhost:8000/download/abc123
```

## Validation Before Deployment

Always validate generated artifacts before deploying:

```bash
python -c "
from powerbi_import.validator import ArtifactValidator
results = ArtifactValidator.validate_directory('./output')
for name, result in results.items():
    status = 'OK' if result['valid'] else 'FAIL'
    print(f'{status}: {name} ({result[\"files_checked\"]} files, {len(result[\"warnings\"])} warnings)')
"
```

## Troubleshooting

| Issue | Solution |
|-------|---------|
| `401 Unauthorized` | Check tenant ID, client ID, and client secret. Ensure admin consent is granted. |
| `403 Forbidden` | Verify the service principal has workspace access (Admin/Member role). |
| `429 Too Many Requests` | Retry logic handles this automatically. Reduce batch size if persistent. |
| `ImportError: azure-identity` | Install with `pip install azure-identity`. Required for authentication. |
| `ImportError: requests` | Install with `pip install requests`. Falls back to `urllib` if not available. |
| Stale files on Windows | OneDrive may lock generated files. Close OneDrive sync or use `--output-dir` outside synced folders. |

---

## Multi-Tenant Deployment

Deploy a shared semantic model to multiple Fabric workspaces with per-tenant connection string overrides.

### Configuration File

Create a `tenants.json`:

```json
{
  "tenants": [
    {
      "name": "Contoso",
      "workspace_id": "aaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
      "connection_overrides": {
        "${TENANT_SERVER}": "contoso-sql.database.windows.net",
        "${TENANT_DATABASE}": "contoso_sales"
      },
      "rls_mappings": {
        "RegionManager": ["user1@contoso.com"]
      }
    },
    {
      "name": "Fabrikam",
      "workspace_id": "1111-2222-3333-4444-555555555555",
      "connection_overrides": {
        "${TENANT_SERVER}": "fabrikam-sql.database.windows.net",
        "${TENANT_DATABASE}": "fabrikam_sales"
      }
    }
  ]
}
```

### Usage

```bash
python migrate.py --shared-model wb1.twbx wb2.twbx --multi-tenant tenants.json
```

The pipeline copies the model for each tenant, substitutes `${TENANT_SERVER}` / `${TENANT_DATABASE}` placeholders in all `.tmdl`, `.m`, `.json`, and `.pbir` files, then deploys each copy to the tenant's workspace.

---

## Live Connection (byConnection) Mode

Wire thin reports to reference a published semantic model via Power BI connection string instead of local `byPath`.

### Usage

```bash
python migrate.py --shared-model wb1.twbx wb2.twbx --live-connection WORKSPACE_ID/ModelName
```

This generates thin reports with `definition.pbir` containing a `byConnection` reference:

```
Data Source=powerbi://api.powerbi.com/v1.0/myorg/{workspace_id};Initial Catalog={model_name}
```

Use this when the semantic model is already published to a Fabric workspace and thin reports should connect remotely.
