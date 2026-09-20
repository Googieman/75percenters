# SRM Attendance Tracker API

The backend is a FastAPI service for one personal attendance account. It stores only structured attendance totals and cumulative history; it never receives SRM passwords, cookies, browser profiles, or raw portal HTML.

## Local PostgreSQL

From the repository root, start the local database and install the backend:

```powershell
docker compose up -d postgres
Set-Location backend
Copy-Item ..\.env.example .env
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Copy `.env.example` to `.env` if you want to override the development defaults. The development Compose service listens on `localhost:5433`; `.env` is ignored by Git.

Create the first and only account with an interactive prompt:

```powershell
.\.venv\Scripts\python.exe -m srm_tracker.admin bootstrap
```

Start the API with `uvicorn srm_tracker.main:create_app --factory --reload` from `backend`. The health endpoint is `GET /api/v1/health` and does not require the database.

## Tests and checks

The integration suite uses the disposable `postgres-test` Compose service:

```powershell
Set-Location C:\Users\varug\Attendance-extractor
docker compose up -d postgres-test
Set-Location backend
$env:SRM_TRACKER_TEST_DATABASE_URL = "postgresql+psycopg://srm_tracker:srm_tracker@localhost:55432/srm_tracker_test"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pip check
```

The migration test explicitly upgrades from empty, downgrades to `base`, and upgrades again. Stop the disposable service with `docker compose stop postgres-test` when finished.

## Phone-first hosted foundation

The server exposes safe connection status, durable refresh queueing, owned sync-job reads, disconnect, authentication attempts, and Web Push subscription endpoints under `/api/v1`. A separate worker claims PostgreSQL-backed jobs with leases and fencing generations, schedules connected accounts hourly, and dispatches VAPID notices. The fixed CampusWeb Student Portal adapter uses only the observed Student Portal routes and remains disabled by default with `SRM_TRACKER_ACQUISITION_ENABLED=false` until the evidence gates in `docs/PHONE_FIRST_ACQUISITION.md` pass.

Production must provide `SRM_TRACKER_SESSION_ENCRYPTION_KEY` as a separately managed URL-safe base64 key containing 32 bytes. Optional retained read keys are supplied as a JSON object in `SRM_TRACKER_SESSION_ENCRYPTION_READ_KEYS`, for example `{"1":"<base64-key>"}`. Run `python scripts/rotate_session_keys.py` repeatedly until it prints `0` before retiring an old key. Keys encrypt provider session/challenge state with AES-GCM and are never stored in PostgreSQL.

Start the hosted worker separately from the API after migrations:

```powershell
.\.venv\Scripts\python.exe -m srm_tracker.worker_entrypoint
```

The Render Blueprint at `../render.yaml` defines separate API and worker processes plus PostgreSQL. It contains no production secrets. Set the same active/read encryption keys and VAPID settings on both processes; keep acquisition disabled until the manual CampusWeb checkpoint and pilot are complete.

## API security model

- Browser login creates a seven-day opaque HTTP-only session cookie and returns a session-bound CSRF token. Browser writes send that token in `X-CSRF-Token`.
- Connector pairing codes expire after ten minutes and can be exchanged once. The resulting device bearer token is returned only from the exchange response and is stored only as a hash.
- Connector tokens can only upload structured attendance records. They cannot read attendance, change settings, list devices, or revoke devices.
- Attendance uploads validate every subject before a transaction writes anything. Subject totals are snapshotted only when totals change; omitted existing subjects remain.
- Production requires an HTTPS configured frontend origin and marks session/CSRF cookies as `Secure`. CORS allows only the exact configured origin.
- Hosted SRM session material is owner/provider/generation-bound authenticated ciphertext. Disconnect removes active state and invalidates queued work while preserving attendance history.

The concrete hosted provider and deployment remain gated milestones. Do not run the retained legacy `scraper.py`.
