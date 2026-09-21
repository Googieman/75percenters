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
that needs rollback.

## Vercel settings

`vercel.json` explicitly installs from `frontend/package-lock.json`, pins the
build runtime to Node 24 through `frontend/package.json`, builds the PWA, and
rewrites `/api/v1/*` to the planned Render API hostname:

```text
https://srm-attendance-api-staging.onrender.com/api/v1/*
```

If Render assigns a different hostname, update the rewrite before publishing.
After the first Vercel deployment, copy its actual origin into
`SRM_TRACKER_FRONTEND_ORIGIN` and redeploy the API.

## URLs and verification

| Item | Result |
| --- | --- |
| Render API URL | Not provisioned |
| Render health URL | Not provisioned |
| Vercel PWA URL | Not provisioned |
| HTTPS/cookie/CSRF check | Pending live deployment |
| Synthetic attendance/history check | Passed locally; pending public URL |
| CampusWeb acquisition | Disabled |

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
