# Free-Tier On-Open Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make staging usable on free hosting by running one bounded CampusWeb refresh inside the authenticated API request when the PWA opens, while preserving the existing durable worker mode for later migration.

**Architecture:** Add an explicit `worker`/`on_demand` sync execution setting. In `on_demand` mode, the existing sync endpoint queues the same fenced PostgreSQL job and then runs the existing `SyncWorker` once in the API process; the response reports the terminal job state. The PWA requests one refresh after a connected on-demand status is loaded, and never stores or submits CampusWeb credentials except during the existing reconnect form.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL/Alembic, React/TypeScript/Vite, Vitest, pytest, Render Blueprint, Vercel static deployment.

**Spec:** `docs/PHONE_FIRST_ACQUISITION.md`, `docs/STAGING_VERIFICATION_CHECKLIST.md`, and the free-tier deployment decision in the user request.

## Global Constraints

- Keep `SRM_TRACKER_ACQUISITION_ENABLED=false` by default; enable it only for the authorized staging checkpoint.
- Never store or log CampusWeb passwords, cookies, tokens, CAPTCHA answers, browser profiles, or raw portal responses.
- The PWA must not communicate directly with CampusWeb; it may call only the relative tracker API.
- On-demand refresh is synchronous and bounded by the existing provider timeouts; it is not a replacement for reliable background scheduling.
- Free PostgreSQL is temporary staging only because it expires after 30 days and has no backups; preserve the worker-ready deployment path for later export.
- Use the existing API, worker, provider, ingestion, fencing, and encrypted-session boundaries rather than creating a second acquisition implementation.

## Review Focus

- A connected account opening the on-demand PWA should trigger exactly one refresh per dashboard mount, not a refresh loop.
- A terminal `succeeded` job returned directly from the API must update the dashboard without waiting for a worker poll.
- A reauthentication, paused, or failed terminal job must not be presented as a successful refresh.
- Worker mode must retain the existing queue-only API behavior and explicit refresh flow.
- CampusWeb credentials must remain absent from the on-open path and from all client storage.

---

### Task 1: Backend on-demand execution mode

**Files:**
- Modify: `backend/src/srm_tracker/config.py`
- Modify: `backend/src/srm_tracker/campusweb_worker.py`
- Modify: `backend/src/srm_tracker/srm_api.py`
- Test: `backend/tests/test_config.py`
- Test: `backend/tests/test_srm_api.py`

**Interfaces:**
- Produces `Settings.sync_execution_mode: Literal["worker", "on_demand"]` from `SRM_TRACKER_SYNC_EXECUTION_MODE`.
- Produces `SrmConnectionResponse.sync_mode` with the configured execution mode.
- In `on_demand` mode, `POST /api/v1/srm/sync` returns the existing job response after one `SyncWorker.run_once()` pass.

- [x] **Step 1: Add failing configuration and API tests**

Add a settings assertion for `sync_execution_mode="on_demand"` and an integration test that enables the existing test provider, completes authentication, sets on-demand mode, posts `/api/v1/srm/sync`, and expects the returned job to be `succeeded` with one stored subject.

- [x] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
Set-Location C:\Users\varug\Attendance-extractor
docker compose up -d --force-recreate postgres-test
Set-Location backend
$env:SRM_TRACKER_TEST_DATABASE_URL = "postgresql+psycopg://srm_tracker:srm_tracker@localhost:55432/srm_tracker_test"
.\.venv\Scripts\python.exe -m pytest tests/test_config.py tests/test_srm_api.py -q
Set-Location ..
docker compose stop postgres-test
```

Expected: the new settings/API assertions fail because the mode and request-driven execution do not yet exist.

- [x] **Step 3: Implement the smallest backend change**

Add the literal setting, pass the mode through connection status, generalize `CampusWebSyncExecutor` to the existing acquisition-provider interface, and make `queue_sync` invoke one configured `SyncWorker.run_once()` pass only when the mode is `on_demand`. Refresh the job from the request session before returning it. Preserve the existing 202 response and worker-mode behavior.

- [x] **Step 4: Run the focused tests and verify GREEN**

Run the same focused command from Step 2. Expected: all focused tests pass, including the new on-demand integration flow.

- [x] **Step 5: Commit the backend task**

```powershell
git add backend/src/srm_tracker/config.py backend/src/srm_tracker/campusweb_worker.py backend/src/srm_tracker/srm_api.py backend/tests/test_config.py backend/tests/test_srm_api.py
git commit -m "feat: support request-driven staging refreshes"
```

### Task 2: PWA refresh on open

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.tsx`
- Test: `frontend/tests/App.test.tsx`

**Interfaces:**
- Consumes `Connection.sync_mode` and terminal `SyncJobResponse.status` from Task 1.
- Produces one automatic `api.queueSync()` call when the loaded connection has `sync_mode === "on_demand"` and `status === "connected"`.

- [x] **Step 1: Add failing frontend tests**

Add tests that a connected on-demand dashboard calls `queueSync` once on mount and that a directly returned `succeeded` job displays the refreshed state without calling `syncJob`; retain the existing explicit worker-mode refresh test.

- [x] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
Set-Location C:\Users\varug\Attendance-extractor\frontend
npm test -- --run tests/App.test.tsx
```

Expected: the new tests fail because `sync_mode` is not exposed or acted upon.

- [x] **Step 3: Implement the smallest frontend change**

Add the optional connection mode type, use a mount-scoped ref to prevent duplicate automatic refreshes, handle terminal job responses immediately, and describe on-demand refresh accurately in the dashboard. Keep the CampusWeb password field clearing behavior unchanged.

- [x] **Step 4: Run the focused tests and verify GREEN**

Run the same focused command from Step 2. Expected: all App tests pass.

- [x] **Step 5: Commit the frontend task**

```powershell
git add frontend/src/api.ts frontend/src/App.tsx frontend/tests/App.test.tsx
git commit -m "feat: refresh attendance when free-tier PWA opens"
```

### Task 3: Free-tier deployment configuration

**Files:**
- Modify: `render.yaml`
- Modify: `vercel.json`
- Modify: `frontend/package.json`
- Modify: `.env.example`
- Modify: `backend/README.md`

**Interfaces:**
- Render staging uses `SRM_TRACKER_SYNC_EXECUTION_MODE=on_demand` and keeps acquisition disabled until the manual gate.
- Vercel installs `frontend/package-lock.json` dependencies explicitly and builds `frontend/dist` on Node 24.x.
- The future worker Blueprint remains documented and can switch the mode back to `worker` when moved to a platform with an always-on process.

- [x] **Step 1: Update deployment configuration**

Pin Render to Python 3.13.14, set the staging API to the free plan, remove the paid worker from the free-tier staging topology, use a free temporary Postgres database, set the actual staging API rewrite target, and configure Vercel to run `npm --prefix frontend ci` before the build. Keep all secret values unset and acquisition disabled.

- [x] **Step 2: Validate configuration locally**

Run JSON/YAML parsing, frontend dependency installation, frontend build, and connector build with the staging API origin. Expected: configuration parses and all builds exit 0; no secret values are present in tracked files.

- [x] **Step 3: Commit deployment configuration**

```powershell
git add render.yaml vercel.json frontend/package.json .env.example backend/README.md
git commit -m "chore: prepare free-tier staging deployment"
```

### Task 4: Documentation and verification record

**Files:**
- Modify: `docs/PROJECT_STATUS.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`
- Modify: `docs/STAGING_VERIFICATION_CHECKLIST.md`

**Interfaces:**
- Documents that on-demand mode is staging-only and that hourly closed-app refresh requires a future paid/always-on worker or another platform.
- Records the exact local verification commands and any hosting/account blockers without inventing URLs or manual CampusWeb results.

- [x] **Step 1: Update status and staging instructions**

Record the free-tier mode, its 30-day/no-backup database limitation, the on-open refresh behavior, the manual acquisition gate, and the remaining GitHub/Vercel account steps.

- [x] **Step 2: Run the complete verification suite**

Run backend tests/checks against disposable PostgreSQL, frontend tests/typecheck/lint/build, and connector tests/build with the staging API origin. Expected: all checks pass and only sanitized fixtures are used.

- [x] **Step 3: Commit documentation**

```powershell
git add docs/PROJECT_STATUS.md docs/IMPLEMENTATION_PLAN.md docs/STAGING_VERIFICATION_CHECKLIST.md
git commit -m "docs: record free-tier staging workflow"
```
