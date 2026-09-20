# SRM Attendance Tracker — Project Status

Last updated: 2026-09-20 (Asia/Kolkata)

## Current milestone

**Task 6 — live connector verification** is in progress. Task 5 established the local flow; Task 6 is prepared with a separate persistent local database and a sanitized evidence record, pending normal Chrome/SRM interaction.

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
- Added the TypeScript/Vite PWA with cookie-authenticated API access, sign-in, pairing-code display, dashboard totals, sync status, subject cards, and history rendering.
- Added the packaged Manifest V3 connector with `activeTab`, user-triggered main-world collection, strict response validation, stable collector error codes, exact popup-message provenance checks, pairing, revocation handling, and duplicate-sync protection.
- Added `scripts/run_local_e2e.ps1` and `npm run test:e2e`. Each run creates a uniquely named loopback-only PostgreSQL 16 container with temporary storage, applies migrations, bootstraps a synthetic account, starts real API/PWA processes, builds the connector into a run-owned directory, and tears down only its own resources.
- Test-drove collector regressions for both `Att. hours` and `Attended hours`, body-read timeout coverage, ambiguous controls, frame and navigation changes, malformed results, exact popup URLs, and upload payloads containing only structured subjects.
- Prepared the Task 6 live-verification record at `docs/live-verification.md` and a dedicated persistent PostgreSQL 16 container on loopback port 5433. The database is migrated but has no tracker account yet.

## Architecture decisions

- React + TypeScript + Vite PWA frontend; FastAPI + PostgreSQL backend; SQLAlchemy/Alembic migrations.
- A Chrome Manifest V3 extension performs a user-triggered, packaged main-world request while the user is logged in normally to SRM. It sends only validated subject totals to the API.
- Pairing uses a short-lived code exchanged for a revocable, device-scoped ingestion credential. No SRM password, cookie, browser profile, token, or raw HTML is stored or sent to the API.
- `scraper.py` is retained locally as an inspected legacy reference only and intentionally excluded from Git. It will not be run, extended, or used in the production path.
- The observed request fields (`iden`, `filter`, `hdnFormDetails`, and optionally `csrfPreventionSalt`) are documented as user-reported network observations, not as directly inspected DOM facts. The collector reads only unique named controls from the verified top-level form; the precise DOM source of the CSRF field remains unverified.
- The local response contract accepts the observed `Att. hours` spelling and the earlier `Attended hours` spelling. Passing local fixtures establish integration behavior only; they do not establish live SRM compatibility.

## Remaining milestones

1. Expand the PWA with offline cached-data labeling and the remaining production-facing dashboard polish.
2. Task 6: perform the one live portal verification in normal Chrome while already logged into SRM, then record the confirmed live DOM/request details in `docs/live-verification.md`.
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

Task 5 local flow command:

```powershell
Set-Location C:\Users\varug\Attendance-extractor\frontend
$env:SRM_TRACKER_E2E_PYTHON = "..\backend\.venv\Scripts\python.exe"
npm run test:e2e
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

## Task 5 verification results

| Check | Result | Notes |
| --- | --- | --- |
| Backend tests | Passed | 45 passed against the disposable PostgreSQL service. |
| Backend Ruff | Passed | `ruff check .` exited 0. |
| Backend mypy | Passed | Strict check of 18 source files exited 0. |
| Backend dependency integrity | Passed | `pip check` reported no broken requirements. |
| Connector tests | Passed | 9 Node tests passed. |
| Frontend tests | Passed | 2 Vitest tests passed; the Playwright suite is run separately. |
| Frontend typecheck/lint/build | Passed | TypeScript, ESLint, and Vite production build all exited 0. |
| Local browser flow | Passed | 6 Playwright tests passed serially with one worker and zero retries; teardown removed the run-owned processes/container. |

The six local browser scenarios cover bootstrap/login, real popup pairing and sync, persistence/history rendering, unchanged idempotency, upward/downward corrections, omitted subjects, malformed portal responses, invalid mixed-batch rollback, revocation, expired tracker sessions, explicit-action boundaries, and structured upload payloads.

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
- Live SRM syncing is prepared but intentionally unverified. Task 6 must use normal Chrome with the user completing SRM login/CAPTCHA themselves: create the local tracker account, build the connector for the local API origin, pair it from the PWA, open the attendance report, press the actual toolbar popup's **Sync**, and confirm the dashboard receives the reported totals. Do not use the legacy scraper or a Playwright-launched SRM login.
- Production deployment will require Render account authorization, a durable PostgreSQL plan approved by the user, secure secret entry, and (if not already connected) source-host authorization.
