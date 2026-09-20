# Task 6 — Live Verification Record

Status: verified with focused live fixes; live SRM portal expiry remains intentionally untested.

This record contains structural observations and pass/fail outcomes only. It must never contain SRM passwords, tracker passwords, pairing codes, bearer tokens, cookies, CSRF values, raw authenticated HTML, HAR files, student identifiers, or personal attendance totals.

## Scope

- Repository branch: `codex/verify-local-attendance-flow`
- Preparation commit: `1565548` (`test: verify local connector to dashboard flow`)
- Verification date: 2026-09-20 (Asia/Kolkata)
- Chrome version: not captured from the UI
- Connector version: `0.1.0`

## Local services

The live-verification database is separate from the disposable test database:

- Container: `srm-tracker-live-postgres`
- Image: `postgres:16`
- Database: `srm_tracker`
- Loopback binding: `127.0.0.1:55433` → container port `5432`
- Persistent volume: `srm-tracker-live-postgres-data`
- Migration state: `head`
- Runtime settings: ignored `backend/.env`
- API origin: `http://127.0.0.1:8000`
- Dashboard origin: `http://127.0.0.1:5173`
- Connector API origin: `http://127.0.0.1:8000`

The database container is user data. Stop it when the local verification session ends; do not remove the container or volume unless explicitly requested.

## Task 5 coverage limitation

The automated browser suite loaded the packaged popup at its `chrome-extension://` URL. That exercised the real MV3 popup, service worker, `scripting.executeScript`, main-world collector, and upload path. It did not prove that a toolbar click alone supplies the intended `activeTab` boundary. The live run must use the actual Chrome toolbar icon and record that separately.

Focused live fixes: the worker now permits the verified SRM shell URL and the collector uses the current hidden-form contract, while requiring the visible attendance table before any portal request. Same-origin non-report pages therefore fail closed.

## Live portal contract

Record descriptions only; do not copy values or private identifiers.

| Observation | Result | Sanitized notes |
| --- | --- | --- |
| Report visible URL | Pass | `/srmiststudentportal/students/template/HRDSystem.jsp` |
| Attendance POST endpoint | Pass | `/srmiststudentportal/students/report/studentAttendanceDetails.jsp` |
| Request method | Pass | `POST`; confirmed by the known portal contract and successful live collection |
| Top-level or framed report | Pass | Top-level document; no frames observed |
| Required form controls | Pass | Current form uses `hdnFormDetails` plus the observed hidden request controls; legacy `iden`/`filter` are absent |
| CSRF field provenance | Pass | `csrfPreventionSalt` is a unique hidden control; its value was never recorded |
| Attendance table headings | Pass | `Code`, `Description`, `Max. hours`, `Att. hours`, `Absent hours`, `Total Percentage` |
| Login/expiry response | Intentionally untested live | Synthetic login-response coverage remains in the connector tests |

## Live flow evidence

| Check | Result | Notes |
| --- | --- | --- |
| Extension loaded from built package | Pass | Unpacked `connector/dist`, enabled, version `0.1.0` |
| Toolbar icon opened the real popup | Pass | Chrome Extensions toolbar menu opened the real popup |
| Pairing completed | Pass | No code/token recorded |
| Installation/status caused no attendance upload | Pass | Initial live database had zero subjects and zero snapshots |
| One explicit Sync succeeded | Pass | Popup reported `Attendance synced.` |
| API body contained only structured subject records | Pass | Worker/API contract and persisted structured tables; no raw portal response path |
| Dashboard matched the visible report | Pass | Reloaded dashboard populated all five reported subjects; private totals omitted here |
| History was created | Pass | Initial live snapshot persisted |
| Unchanged Sync advanced timestamp without new snapshot | Pass | Repeat popup sync succeeded; subject and snapshot counts remained `5` and `5` |
| Sync from unrelated tab was rejected | Pass | Same-origin SRM dashboard returned the context error with no database count change |
| Portal expiry behavior | Intentionally untested | Would require logging out through the portal; synthetic expiry coverage remains |

## Commands

Start the local database if it is stopped:

```powershell
docker start srm-tracker-live-postgres
```

From `backend`, apply migrations and create the first tracker account if the database has no account. Enter the tracker password interactively; do not place it in this document:

```powershell
$env:SRM_TRACKER_DATABASE_URL = "postgresql+psycopg://srm_tracker:srm_tracker@127.0.0.1:55433/srm_tracker"
$python = "C:\Users\varug\Attendance-extractor\backend\.venv\Scripts\python.exe"
& $python -m alembic upgrade head
& $python -m srm_tracker.admin bootstrap
```

Use the Python interpreter configured for this checkout if it differs from the path above.

Run the API and dashboard with the origins above. From `connector`, build the unpacked package:

From `backend`:

```powershell
$python = "C:\Users\varug\Attendance-extractor\backend\.venv\Scripts\python.exe"
& $python -m uvicorn srm_tracker.main:create_app --factory --app-dir src --host 127.0.0.1 --port 8000
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

- Live compatibility is verified for the authenticated report flow and same-origin non-report rejection.
- Chrome version was not captured; live portal expiry behavior remains intentionally untested.
- The live tracker account and attendance values are intentionally absent from this file.
