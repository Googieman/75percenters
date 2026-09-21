# Staging deployment record

This project is configured for a free-tier staging run. The deployment is
deliberately provider-gated: `SRM_TRACKER_ACQUISITION_ENABLED=false` remains
the default until the manual CampusWeb checkpoint passes.

## Free-tier topology

| Component | Platform | Configuration | Cost before usage limits |
| --- | --- | --- | --- |
| PWA | Vercel Hobby | Static Vite build, same-origin API rewrite | $0 |
| API | Render | Free Python web service | $0 |
| PostgreSQL | Render | Free PostgreSQL, staging only | $0 |
| Worker | None in free staging | API runs one fenced refresh on demand | $0 |

The free mode cannot provide closed-app hourly refresh or durable worker
restart scheduling. The PWA requests one refresh when the dashboard opens and
should remain open while the request completes. The worker entry point remains
available for a later worker-capable platform export.

No paid worker or database has been provisioned. Before upgrading, recheck
the provider pricing pages and approve the current amounts. The previously
planned paid Render worker and Basic PostgreSQL resources are intentionally not
present in `render.yaml`.

## Render settings

`render.yaml` creates `srm-attendance-api-staging` and
`srm-attendance-db-staging`. The API uses `python -m alembic upgrade head`
before startup and runs with:

```text
SRM_TRACKER_ENVIRONMENT=staging
SRM_TRACKER_SYNC_EXECUTION_MODE=on_demand
SRM_TRACKER_ACQUISITION_ENABLED=false
```

Set these values through Render's secret/environment UI rather than committing
them:

- `SRM_TRACKER_FRONTEND_ORIGIN`: the exact HTTPS Vercel deployment origin,
  without a trailing slash.
- `SRM_TRACKER_SESSION_ENCRYPTION_KEY`: a URL-safe base64 key containing 32
  bytes.
- `SRM_TRACKER_WEB_PUSH_PUBLIC_KEY`, `SRM_TRACKER_WEB_PUSH_PRIVATE_KEY`, and
  `SRM_TRACKER_WEB_PUSH_SUBJECT`: optional until push is configured.

The service must remain on the staging database. Free PostgreSQL is not a
production backup strategy; export it before expiry or before any migration
that needs rollback. Render may provide `postgres://` or bare `postgresql://`
connection strings; the API settings and Alembic environment normalize these
to the installed `postgresql+psycopg://` dialect while preserving TLS query
parameters such as `sslmode=require`.

The Render start command runs migrations and then starts Uvicorn in one process
command:

```text
python -m alembic upgrade head && exec python -m uvicorn srm_tracker.main:create_app --factory --host 0.0.0.0 --port $PORT
```

`PYTHON_VERSION=3.13.14` is an explicit released Python pin. Verify the
provider's current runtime list before changing it.

## Vercel settings

`vercel.json` explicitly installs from `frontend/package-lock.json`, pins the
build runtime to Node 24 through `frontend/package.json`, builds the PWA, and
rewrites `/api/v1/*` to the planned Render API hostname:

```text
https://srm-attendance-api-staging.onrender.com/api/v1/*
```

If Render assigns a different hostname, update the rewrite before publishing.
After the first Vercel deployment, copy its actual origin into
`SRM_TRACKER_FRONTEND_ORIGIN` and redeploy the API. On-demand staging never
advertises Web Push notifications because no process dispatches them.

## URLs and verification

| Item | Result |
| --- | --- |
| Render API URL | Not provisioned |
| Render health URL | Not provisioned |
| Vercel PWA URL | Not provisioned |
| HTTPS/cookie/CSRF check | Pending live deployment |
| Synthetic attendance/history check | Passed locally; pending public URL |
| CampusWeb acquisition | Disabled |

The tracker account is created without Render shell access. After the database
is provisioned, set `SRM_TRACKER_DATABASE_URL` only in the current local
process to the TLS external URL, restrict the Render database IP allow list to
the operator's current public IP, run migrations from `backend`, and run the
interactive bootstrap command:

```powershell
Set-Location C:\Users\varug\Attendance-extractor\backend
$env:SRM_TRACKER_DATABASE_URL = "<temporary TLS Render external URL>"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m srm_tracker.admin bootstrap
Remove-Item Env:SRM_TRACKER_DATABASE_URL
```

Enter the tracker password only at the hidden interactive prompt. Do not save
the external URL, password, encryption key, or dump path in the repository or
chat.

The public verification order is: health check, login, cookie and CSRF write,
dashboard load, logout, synthetic ingestion/history, then only the authorized
CampusWeb staging checkpoint. Do not enter CampusWeb credentials into a shell,
repository, issue, or chat.

## Export to a worker-capable platform

Use the same backend image/source and PostgreSQL migration history. Set
`SRM_TRACKER_SYNC_EXECUTION_MODE=worker`, keep the API and worker on the same
active/read encryption keyring, and run this command as a separate durable
worker process:

```powershell
python -m srm_tracker.worker_entrypoint
```

Run migrations before switching traffic. Roll back the application to the
previous verified release if needed; do not downgrade a live database unless a
tested restore point and migration-specific procedure exist. Keep the Chrome
connector available as a fallback during the migration.

## Backup and restore before expiry

Use a private local path outside the repository and keep the database dump
separate from the session encryption key. With the temporary TLS URL in the
current process only:

```powershell
$env:PGSSLMODE = "require"
$env:PGPASSWORD = "<temporary database password>"
pg_dump --format=custom --file="<private backup path>" "<temporary TLS Render external URL>"
Remove-Item Env:PGPASSWORD
Remove-Item Env:PGSSLMODE
```

Restore the dump into disposable PostgreSQL, apply any required migrations in
a throwaway copy, and verify that attendance subjects and history read
correctly. Keep the encryption key in a separate private store; a database
dump without that key cannot decrypt hosted provider state. Record the actual
database expiry date and restore result in this document after provisioning.

## Rollback

If a deployment fails, use the last verified commit and redeploy the API/PWA
pair, keeping the database schema at its current migration head. Revert the
Vercel rewrite and `SRM_TRACKER_FRONTEND_ORIGIN` together if the frontend/API
origins are mismatched. Do not downgrade a live database without restoring a
tested dump first. Revoke any temporary database credentials and encryption
keys if they were exposed, and keep acquisition disabled until the live checks
pass.
