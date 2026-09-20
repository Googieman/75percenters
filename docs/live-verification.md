# Task 6 — Live Verification Record

Status: prepared; live SRM verification has not been performed.

This record contains structural observations and pass/fail outcomes only. It must never contain SRM passwords, tracker passwords, pairing codes, bearer tokens, cookies, CSRF values, raw authenticated HTML, HAR files, student identifiers, or personal attendance totals.

## Scope

- Repository branch: `codex/verify-local-attendance-flow`
- Preparation commit: `1565548` (`test: verify local connector to dashboard flow`)
- Verification date: not yet performed
- Chrome version: not yet recorded
- Connector version: `0.1.0`

## Local services

The live-verification database is separate from the disposable test database:

- Container: `srm-tracker-live-postgres`
- Image: `postgres:16`
- Database: `srm_tracker`
- Loopback binding: `127.0.0.1:5433` → container port `5432`
- Persistent volume: `srm-tracker-live-postgres-data`
- Migration state: `head`
- Runtime settings: ignored `backend/.env`
- API origin: `http://127.0.0.1:8000`
- Dashboard origin: `http://127.0.0.1:5173`
- Connector API origin: `http://127.0.0.1:8000`

The database container is user data. Stop it when the local verification session ends; do not remove the container or volume unless explicitly requested.

## Task 5 coverage limitation

The automated browser suite loaded the packaged popup at its `chrome-extension://` URL. That exercised the real MV3 popup, service worker, `scripting.executeScript`, main-world collector, and upload path. It did not prove that a toolbar click alone supplies the intended `activeTab` boundary. The live run must use the actual Chrome toolbar icon and record that separately.

## Live portal contract

Record descriptions only; do not copy values or private identifiers.

| Observation | Result | Sanitized notes |
| --- | --- | --- |
| Report visible URL | Pending |  |
| Attendance POST endpoint | Pending |  |
| Request method | Pending |  |
| Top-level or framed report | Pending |  |
| Required form controls | Pending | Names only, no values |
| CSRF field provenance | Pending | Presence/source only, no value |
| Attendance table headings | Pending | Header text only |
| Login/expiry response | Pending | Shape/status only |

## Live flow evidence

| Check | Result | Notes |
| --- | --- | --- |
| Extension loaded from built package | Pending |  |
| Toolbar icon opened the real popup | Pending |  |
| Pairing completed | Pending | No code/token recorded |
| Installation/status caused no attendance upload | Pending |  |
| One explicit Sync succeeded | Pending |  |
| API body contained only structured subject records | Pending | Pass/fail only |
| Dashboard matched the visible report | Pending | No totals recorded here |
| History was created | Pending |  |
| Unchanged Sync advanced timestamp without new snapshot | Pending |  |
| Sync from unrelated tab was rejected | Pending |  |
| Portal expiry behavior | Pending or intentionally untested |  |

## Commands

Start the local database if it is stopped:

```powershell
docker start srm-tracker-live-postgres
```

From `backend`, apply migrations and create the first tracker account if the database has no account. Enter the tracker password interactively; do not place it in this document:

```powershell
$env:SRM_TRACKER_DATABASE_URL = "postgresql+psycopg://srm_tracker:srm_tracker@127.0.0.1:5433/srm_tracker"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m srm_tracker.admin bootstrap
```

Run the API and dashboard with the origins above. From `connector`, build the unpacked package:

From `backend`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn srm_tracker.main:create_app --factory --app-dir src --host 127.0.0.1 --port 8000
```

From `frontend`:

```powershell
npm run dev -- --host 127.0.0.1 --port 5173
```

From `connector`:

```powershell
npm run build -- http://127.0.0.1:8000
```

Stop only the live-verification processes and container when finished:

```powershell
docker stop srm-tracker-live-postgres
```

## Remaining uncertainties

- Live compatibility is unverified until normal Chrome loads the report and the user presses Sync.
- The exact live report URL, frame context, CSRF provenance, and response heading spelling remain pending.
- The live tracker account and attendance values are intentionally absent from this file.
