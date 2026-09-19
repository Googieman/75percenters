# Persistent Authenticated Attendance API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add PostgreSQL persistence, personal-account authentication, secure one-time connector pairing, validated transactional attendance ingestion, protected attendance reads, and migration/integration verification to the existing FastAPI backend.

**Architecture:** Keep the parser and calculation modules pure. Add synchronous SQLAlchemy 2 persistence behind FastAPI dependencies, with Alembic owning schema changes and PostgreSQL advisory/row locks serializing owner-scoped writes. Browser sessions use hashed opaque cookies plus hashed CSRF tokens; connector devices use separate hashed bearer tokens and have no read or account-management permissions.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2, Psycopg 3, Alembic, PostgreSQL 16, pwdlib Argon2, pytest, HTTPX, Ruff, and mypy.

**Spec:** `docs/superpowers/specs/2026-09-09-srm-attendance-tracker-design.md`, extended by the user's “Next milestone: persistent, authenticated attendance API” requirements.

## Global Constraints

- All routes remain under `/api/v1`; `GET /api/v1/health` must not require a database connection.
- Store server-generated UTC timestamps; keep snapshots only when attendance totals change, retain omitted existing subjects, and preserve downward corrections.
- Bootstrap creates exactly one personal account; there is no public signup, invitation, password reset, or multi-semester management.
- Passwords use Argon2 through `pwdlib`; sessions are opaque, server-side, hashed, HTTP-only, seven-day cookies with logout invalidation.
- Production requires HTTPS frontend origins and secure cookies; CORS uses exact configured origins; authenticated browser writes require a session-bound CSRF header.
- Pairing codes are one-use and valid for ten minutes; connector tokens are high entropy, returned only at exchange, stored only as hashes, ingestion-only, and immediately revocable.
- Uploads accept only explicit structured subject records, reject unknown fields/raw HTML, validate all records before writing, and commit or roll back as one transaction.
- Never log or put credentials, session tokens, device tokens, SRM credentials, cookies, or raw portal HTML in URLs, responses after creation, or repository files.
- Existing parser/calculation behavior and the Python 3.13 baseline remain intact.

## Review Focus

- Concurrent pairing exchanges must create at most one device; owned by Task 3 tests.
- A malformed record late in a batch must leave every subject, snapshot, and device timestamp unchanged; owned by Task 4 tests.
- A valid connector bearer token must not authenticate reads/settings/devices, and a browser session must not authenticate ingestion; owned by Task 4 tests.
- Expired sessions, revoked devices, expired/reused pairing codes, and foreign IDs must fail without leaking resource ownership; owned by Tasks 2–4 tests.
- Migration upgrade/downgrade/re-upgrade must work from an empty PostgreSQL database; owned by Task 1 and Task 5 tests.

---

### Task 1: Persistence foundation and migrations

**Files:**
- Create: `backend/src/srm_tracker/db.py`, `backend/src/srm_tracker/db_models.py`, `backend/src/srm_tracker/time.py`
- Create: `backend/alembic.ini`, `backend/migrations/env.py`, `backend/migrations/script.py.mako`, `backend/migrations/versions/0001_initial.py`
- Create: `docker-compose.yml`
- Modify: `backend/pyproject.toml`, `backend/requirements.lock`, `backend/src/srm_tracker/config.py`, `.env.example`, `.gitignore`
- Test: `backend/tests/test_persistence_models.py`, `backend/tests/test_migrations.py`

**Interfaces:**
- Produces `Base`, SQLAlchemy models `User`, `Session`, `Subject`, `AttendanceSnapshot`, `PairingCode`, `ConnectorDevice`, and `RateLimitBucket`.
- Produces `create_engine_from_settings(settings)`, `session_factory_for_engine(engine)`, and `utc_now()`.
- The model fields expose integer attendance totals, Decimal source/target percentages, owner foreign keys, server defaults, and revocation/consumption timestamps.

- [ ] Write tests for owner relationships, the per-user subject-code uniqueness constraint, UTC-aware timestamps, and migration upgrade/downgrade/re-upgrade.
- [ ] Run the focused tests and observe collection failures before the new persistence modules exist.
- [ ] Add SQLAlchemy/Psycopg/Alembic/pwdlib dependencies, settings defaults and production security fields, the Compose PostgreSQL service, and the normalized model/migration schema.
- [ ] Run model tests, migration tests against the disposable PostgreSQL service, Ruff, and mypy.
- [ ] Commit `feat: add persistent attendance schema`.

### Task 2: Account bootstrap, sessions, CSRF, CORS, and rate limits

**Files:**
- Create: `backend/src/srm_tracker/security.py`, `backend/src/srm_tracker/rate_limit.py`, `backend/src/srm_tracker/auth.py`, `backend/src/srm_tracker/admin.py`
- Create: `backend/tests/test_authentication.py`, `backend/tests/test_admin.py`
- Modify: `backend/src/srm_tracker/main.py`, `backend/src/srm_tracker/db.py`, `backend/src/srm_tracker/config.py`

**Interfaces:**
- Produces `bootstrap_account(session, email, password)`, `python -m srm_tracker.admin bootstrap`, `get_current_user`, `require_csrf`, `hash_opaque_token`, and `verify_password`.
- Adds `POST /api/v1/auth/login`, `POST /api/v1/auth/logout`, `GET /api/v1/auth/me`, and database-backed login rate limiting with `429`/`Retry-After`.

- [ ] Write failing tests for first-account-only bootstrap, Argon2 password verification, successful login/me/logout, seven-day expiry, logout invalidation, CSRF rejection, exact CORS headers, and login throttling.
- [ ] Run the focused auth tests and observe the expected missing-module/route failures.
- [ ] Implement hashed passwords, opaque hashed sessions, secure cookie policy, CSRF token issuance/validation, exact CORS, and atomic rate-limit buckets.
- [ ] Run auth/admin tests and the existing 20-test baseline; fix only production defects revealed by the tests.
- [ ] Commit `feat: add personal account sessions`.

### Task 3: One-time pairing and device management

**Files:**
- Create: `backend/src/srm_tracker/pairing.py`, `backend/tests/test_pairing.py`
- Modify: `backend/src/srm_tracker/main.py`, `backend/src/srm_tracker/auth.py`, `backend/src/srm_tracker/rate_limit.py`

**Interfaces:**
- Adds `POST /api/v1/pairing-codes`, `POST /api/v1/connector/pair`, `GET /api/v1/devices`, and `DELETE /api/v1/devices/{id}`.
- Produces atomic `create_pairing_code`, `exchange_pairing_code`, and `revoke_device` services; device tokens are returned only in the exchange response and never in list/delete responses.

- [ ] Write failing tests for ten-minute expiry, reuse rejection, concurrent exchange, pairing rate limiting, token scope, list ownership, foreign-ID 404s, and immediate revocation.
- [ ] Run the focused pairing tests and observe the expected missing route/service failures.
- [ ] Implement hashed pairing codes, row-lock consumption, high-entropy hashed device tokens, browser CSRF protection for creation/revocation, and connector-only bearer authentication.
- [ ] Run pairing tests plus auth and baseline tests.
- [ ] Commit `feat: add connector pairing and device revocation`.

### Task 4: Transactional ingestion and protected attendance reads

**Files:**
- Create: `backend/src/srm_tracker/schemas.py`, `backend/src/srm_tracker/attendance_service.py`, `backend/tests/test_attendance_api.py`
- Modify: `backend/src/srm_tracker/main.py`, `backend/src/srm_tracker/auth.py`, `backend/src/srm_tracker/attendance/calculations.py`

**Interfaces:**
- Adds `PATCH /api/v1/settings`, `GET /api/v1/attendance`, `GET /api/v1/subjects/{id}/history`, and `POST /api/v1/connector/attendance`.
- Produces strict Pydantic upload schemas using `code`, `subject`, `total_hours`, `attended_hours`, `absent_hours`, and `source_percentage`; responses include latest subject guidance, overall guidance, sync time, and opaque history cursors.

- [ ] Write failing tests for first upload, unchanged retry, concurrent duplicate uploads, changed totals, downward corrections, omitted-subject retention, malformed/unknown/raw-HTML batches, full rollback, pagination, settings validation, and browser/device auth separation.
- [ ] Run the focused attendance tests and observe expected missing route/schema/service failures.
- [ ] Implement strict schemas, owner-row serialization, atomic subject/snapshot updates, device last-seen updates, target settings, overall and subject guidance, newest-first cursor history, and 404 ownership behavior.
- [ ] Run attendance tests, all baseline/auth/pairing tests, Ruff, and mypy.
- [ ] Commit `feat: add validated attendance ingestion and reads`.

### Task 5: Fixture flow, documentation, and release verification

**Files:**
- Create: `backend/tests/test_fixture_flow.py`, `backend/tests/test_security_regressions.py`
- Modify: `backend/README.md`, `docs/PROJECT_STATUS.md`, `docs/IMPLEMENTATION_PLAN.md`

**Interfaces:**
- Documents local PostgreSQL startup, migration commands, bootstrap/login/pair/upload/read/revoke flow, environment variables, and the non-goals/boundaries from the milestone.

- [ ] Write the fixture-based end-to-end test for bootstrap → login → pair → upload → history → revoke → rejected upload, plus migration and dependency checks.
- [ ] Run the end-to-end test against disposable PostgreSQL and verify failure output before any documentation-only cleanup.
- [ ] Update setup/status docs with exact commands and the verified milestone state; do not document or include secrets.
- [ ] Run the full backend suite, Ruff, mypy, pip check, migration cycle, and `git diff --check`.
- [ ] Commit `docs: record persistent authenticated API milestone`.

