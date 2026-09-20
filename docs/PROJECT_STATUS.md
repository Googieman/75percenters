# SRM Attendance Tracker — Project Status

Last updated: 2026-09-20 (Asia/Kolkata)

## Current milestone

**Milestone 2 — persistence, authentication, secure pairing, and ingestion** is complete. The backend now has a PostgreSQL/Alembic schema, first-account bootstrap, protected browser sessions, one-time connector pairing, transactional uploads, protected reads, and subject history.

## Completed work

- Inspected the initial workspace. It contained only `scraper.py`, two local Chrome-profile directories, and a Python virtual environment; no Git repository, attendance fixture, Chrome extension, frontend, backend, or test suite existed.
- Initialized Git and added a safety-focused `.gitignore`. Local Chrome profiles, portal output, secrets, virtual environments, and build artifacts are excluded.
- Recorded the approved architecture and phased implementation plan.
- Added the executable, test-first Milestone 1 plan at `docs/superpowers/plans/2026-09-09-backend-foundation.md`.
- Created the reproducible backend package at `backend/`, a Python 3.13 lock file, non-secret `.env.example`, and strict test/lint/type-check configuration.
- Test-drove the settings contract. It reads `SRM_TRACKER_` values, normalizes a trailing frontend-origin slash, and rejects non-HTTPS frontend origins in production.
- Diagnosed a transient Windows installer file lock caused by an earlier still-running package installation. A single retry after the process exited installed the missing packages; `pip check` reported no broken requirements.
- Removed generated editable-install `.egg-info` metadata from Git and added an ignore rule so future package setup does not pollute commits.
- Test-drove the strict, local HTML parser with sanitized fixtures. It finds the documented six-column table by exact normalized headers and returns typed cumulative subject records.
- Added rejection tests for login markup, missing attendance tables, fractional/invalid source hours, and inconsistent attended-plus-absent totals. No live SRM request has been made.
- Test-drove target calculations for empty totals, exact/below/above target, 100% edge cases, invalid targets, and two-decimal display rounding. Guidance uses unrounded totals for decisions: 16 attended out of 23 needs 5 attended hours to reach 75% and displays 69.57%.
- Added the FastAPI application factory and a versioned, database-free `GET /api/v1/health` endpoint. Its HTTP behavior is tested with HTTPX’s ASGI transport, avoiding deprecated test-wrapper warnings.
- Added PostgreSQL/Alembic persistence for users, sessions, subjects, snapshots, pairing codes, connector devices, and database-backed rate-limit buckets, with a local Compose service and a tested upgrade/downgrade/re-upgrade migration.
- Added Argon2 bootstrap authentication, opaque hashed seven-day sessions, HTTP-only/Secure cookie policy, session-bound CSRF, exact CORS, login/pairing rate limits, one-time pairing, device revocation, strict transactional connector uploads, owner-serialized snapshot history, target settings, and protected attendance reads.

## Architecture decisions

- React + TypeScript + Vite PWA frontend; FastAPI + PostgreSQL backend; SQLAlchemy/Alembic migrations.
- A Chrome Manifest V3 extension performs a user-triggered, packaged main-world request while the user is logged in normally to SRM. It sends only validated subject totals to the API.
- Pairing uses a short-lived code exchanged for a revocable, device-scoped ingestion credential. No SRM password, cookie, browser profile, token, or raw HTML is stored or sent to the API.
- `scraper.py` is retained locally as an inspected legacy reference only and intentionally excluded from Git. It will not be run, extended, or used in the production path.

## Remaining milestones

1. Build the PWA dashboard, subject history, offline cached-data labeling, and component/end-to-end tests.
2. Build and package the MV3 extension; verify its portal behavior manually while the user is logged in normally.
3. Complete production checks, Render Blueprint, and secure environment configuration.
4. Provision and verify Render deployment after the user authorizes the account connection, database plan, and production secrets.

## Exact commands to resume

```powershell
Set-Location C:\Users\varug\Attendance-extractor
Get-Content -Raw docs\PROJECT_STATUS.md
Get-Content -Raw docs\IMPLEMENTATION_PLAN.md
Get-Content -Raw docs\superpowers\plans\2026-09-09-backend-foundation.md
git status --short
git log --oneline -5
```

After dependencies are created, use the commands recorded in the relevant milestone of `docs/IMPLEMENTATION_PLAN.md`; do not run the legacy Playwright scraper.

Current backend commands:

```powershell
Set-Location C:\Users\varug\Attendance-extractor\backend
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy src
```

## Milestone 2 verification results

| Check | Result | Notes |
| --- | --- | --- |
| Initial repository inspection | Completed | No existing test suite or application manifests were found. |
| Legacy dependency inspection | Completed | Local virtual environment contains Playwright 1.62.0 and Beautiful Soup 4.15.0. |
| Baseline automated tests | Not available | No test files or test runner configuration existed at inspection time. |
| Backend tests | Passed | 45 passed against disposable PostgreSQL: baseline domain/health behavior, migrations, bootstrap/auth, CSRF/CORS/rate limits, pairing/concurrency/revocation, ingestion/history, rollback-facing validation, fixture flow, HTTPS enforcement, and cross-user isolation. |
| Ruff | Passed | `ruff check .` exited 0. |
| Mypy | Passed | Strict check of 18 source files exited 0. |
| Dependency integrity | Passed | `pip check` reported no broken requirements. |
| Git ignore safety check | Passed | Chrome profiles, legacy scraper, root virtual environment, and backend virtual environment are ignored. |

Last Milestone 2 verification commands:

```powershell
Set-Location C:\Users\varug\Attendance-extractor\backend
Set-Location ..
docker compose up -d postgres-test
Set-Location backend
$env:SRM_TRACKER_TEST_DATABASE_URL = "postgresql+psycopg://srm_tracker:srm_tracker@localhost:55432/srm_tracker_test"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pip check
Set-Location ..
docker compose stop postgres-test
```

## Deployment state

Not started. No Render resources, paid plans, GitHub remote, live URL, or production secrets have been created.

## Blockers and manual verification

- The successful attendance HTML fixture is locally authored and sanitized to reflect the confirmed six-column contract; a real response must never be committed.
- Live SRM syncing is intentionally unverified until the extension exists. The only required later manual test is: log into SRM in normal Chrome, pair the extension from the web app, press **Sync**, and confirm the dashboard receives the reported totals.
- Production deployment will require Render account authorization, a durable PostgreSQL plan approved by the user, secure secret entry, and (if not already connected) source-host authorization.
