# Free Staging Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the verified SRM Attendance Tracker source and deploy a secure, free-tier Render/Vercel staging environment with bounded on-demand refresh and synthetic history verification.

**Architecture:** Keep the existing FastAPI/PostgreSQL, React PWA, and Chrome connector boundaries. Normalize provider database URLs at configuration and migration entry points, secure all hosted cookies, keep Render free staging API-only with migrations in the startup command, and make the PWA refresh on open/focus without polling a job that has no worker.

**Tech Stack:** FastAPI, SQLAlchemy/Alembic, Psycopg 3, PostgreSQL 16, React/TypeScript/Vite, Vitest, pytest, Render Blueprint, Vercel Hobby.

**Spec:** User deployment request; `docs/PROJECT_STATUS.md`; `docs/DEPLOYMENT.md`; `docs/STAGING_VERIFICATION_CHECKLIST.md`.

## Global Constraints

- Keep `SRM_TRACKER_ACQUISITION_ENABLED=false` in the published Blueprint and live staging environment until the separate authorized CampusWeb checkpoint passes.
- Never commit or transmit SRM passwords, cookies, tokens, Chrome profiles, raw authenticated portal responses, database credentials, encryption keys, or local `AGENTS.md`.
- Use the existing Chrome connector for SRM collection; do not enable the hosted credential flow or legacy Playwright login.
- Use only free Vercel Hobby, free Render web service, and temporary free Render PostgreSQL; create no worker or paid resource.
- Run migrations before Uvicorn in the Render startup command and normalize every Render PostgreSQL URL to `postgresql+psycopg://` for both API and Alembic.
- Back up the temporary database privately before expiry and keep the encryption key separate from the dump.

## Review Focus

- Hosted staging login must set both session and CSRF cookies with `Secure`, while local development remains usable over HTTP.
- Render `postgres://` and `postgresql://` connection strings must work through both the API engine and Alembic without requiring an uninstalled driver.
- Returning to an on-demand PWA must coalesce concurrent refresh requests, honor the server cooldown, and stop without polling when the API cannot run a worker.
- A failed or reauthentication refresh must expose a reconnect/retry action without claiming success or retaining credentials.
- Public Git history and tracked files must contain no local profiles, secrets, raw portal data, or `AGENTS.md`.

---

### Task 1: Secure hosted sessions and Psycopg URL normalization

**Files:**
- Modify: `backend/src/srm_tracker/auth.py`
- Modify: `backend/src/srm_tracker/config.py`
- Modify: `backend/migrations/env.py`
- Test: `backend/tests/test_config.py`
- Test: `backend/tests/test_security_regressions.py`

**Interfaces:**
- Produces `normalize_database_url(value: str) -> str`, converting `postgres://` and bare `postgresql://` to `postgresql+psycopg://` while preserving credentials, host, path, and query parameters.
- `Settings.database_url` is normalized before API engine creation.
- Alembic uses the same normalization before creating its migration engine.
- Staging and production session/CSRF cookies are `Secure`; development/test cookies remain non-secure.

- [ ] **Step 1: Write failing tests**

Add tests with these assertions:

```python
def test_normalizes_render_postgres_urls() -> None:
    assert normalize_database_url("postgres://user:pass@host/db?sslmode=require") == "postgresql+psycopg://user:pass@host/db?sslmode=require"
    assert normalize_database_url("postgresql://user:pass@host/db") == "postgresql+psycopg://user:pass@host/db"
    assert normalize_database_url("postgresql+psycopg://user:pass@host/db") == "postgresql+psycopg://user:pass@host/db"
```

Add a staging login regression test that constructs `Settings(environment="staging", frontend_origin="https://dashboard.example", session_encryption_key=<valid-32-byte-key>)`, logs in over HTTPS, and asserts both `Set-Cookie` values contain `Secure`; assert the existing development login response does not contain `Secure`.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
Set-Location C:\Users\varug\Attendance-extractor\backend
..\.venv\Scripts\python.exe -m pytest tests/test_config.py tests/test_security_regressions.py -q
```

Expected: the new URL-normalization test fails because the helper is absent and the staging cookie assertion fails because cookies are currently secure only in production.

- [ ] **Step 3: Implement the smallest change**

Add the pure URL helper and a Pydantic `database_url` validator, call the helper for `SRM_TRACKER_DATABASE_URL` in `migrations/env.py`, and change both cookie helpers to use `settings.environment in {"staging", "production"}`. Do not log or parse secrets beyond the URL scheme.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the same pytest command. Expected: all focused tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/src/srm_tracker/auth.py backend/src/srm_tracker/config.py backend/migrations/env.py backend/tests/test_config.py backend/tests/test_security_regressions.py
git commit -m "fix: secure staging sessions and normalize database urls"
```

### Task 2: Bounded on-demand refresh recovery

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/api.ts`
- Test: `frontend/tests/App.test.tsx`
- Test: `frontend/tests/api.test.ts`

**Interfaces:**
- `api.queueSync()` exposes HTTP 429 retry timing through `ApiError` and retains `Retry-After` when present.
- Dashboard refresh requests are keyed by the current dashboard lifecycle, with one in-flight request shared by open/focus/online events.
- On-demand mode handles terminal jobs immediately and does not start interval polling for a queued job; worker mode retains existing polling.

- [ ] **Step 1: Write failing tests**

Add tests that:

```typescript
it("coalesces open and focus refreshes while a request is in flight", async () => {
  const pending = deferred<SyncJob>();
  apiMock.connection.mockResolvedValue(connectedOnDemand);
  apiMock.queueSync.mockReturnValue(pending.promise);
  render(<App />);
  window.dispatchEvent(new Event("focus"));
  await waitFor(() => expect(apiMock.queueSync).toHaveBeenCalledTimes(1));
  pending.resolve({ job_id: 9, status: "succeeded" });
});
```

Also add coverage for a `429` response showing a cooldown/retry message, an on-demand `queued` response showing “keep this app open” without calling `syncJob`, and a terminal `reauth_required` response showing a reconnect action. Add an API-client assertion that `Retry-After` is available on `ApiError`.

- [ ] **Step 2: Run the focused frontend tests and verify RED**

Run:

```powershell
Set-Location C:\Users\varug\Attendance-extractor\frontend
npm test -- --run tests/App.test.tsx tests/api.test.ts
```

Expected: the new coalescing, cooldown, no-worker polling, and retry/reconnect tests fail against the current implementation.

- [ ] **Step 3: Implement the smallest change**

Add `retryAfterSeconds` to `ApiError`, parse the response header, coalesce one automatic request per refresh lifecycle, trigger the lifecycle again on focus/online only after the existing cooldown, and branch job handling by `sync_mode`. In on-demand mode, render terminal results directly and leave queued jobs in a reconnect/retry state without an interval. Preserve explicit worker-mode polling and clear the CampusWeb password in every reconnect path.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the same frontend command. Expected: all focused tests pass.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/App.tsx frontend/src/api.ts frontend/tests/App.test.tsx frontend/tests/api.test.ts
git commit -m "fix: make free-tier refresh recovery bounded"
```

### Task 3: Render/Vercel manifests and clean dependency verification

**Files:**
- Modify: `render.yaml`
- Modify: `vercel.json`
- Modify: `frontend/package.json`
- Modify: `docs/DEPLOYMENT.md`
- Test: `scripts/verify_staging_config.ps1`

**Interfaces:**
- Render defines exactly one free API and one temporary free PostgreSQL database, with no `preDeployCommand`, worker, notification dispatcher, or paid resource.
- Render startup runs `python -m alembic upgrade head` and then Uvicorn in the same process command.
- Vercel installs from `frontend/package-lock.json`, builds from the repository root, and uses the actual Render API origin placeholder only until the first deployment assigns the final hostname.
- Node 24.x and pinned Python 3.13 are explicitly verified against the current provider documentation and local toolchain.

- [ ] **Step 1: Add manifest verification checks**

Create a PowerShell script that parses `render.yaml` and `vercel.json`, asserts the free API/database count, absence of `preDeployCommand`, presence of the migration-before-Uvicorn startup sequence, `on_demand`, acquisition disabled, `npm --prefix frontend ci`, `frontend/dist`, and Node 24. It must scan tracked files for common secret markers and fail if `AGENTS.md` is tracked.

- [ ] **Step 2: Run the check before fixing manifests and verify RED**

Run:

```powershell
Set-Location C:\Users\varug\Attendance-extractor
.
scripts\verify_staging_config.ps1
```

Expected: it fails on the existing `preDeployCommand`, stale Render rewrite, or missing manifest assertions.

- [ ] **Step 3: Correct manifests and documentation**

Replace the paid-only pre-deploy migration with the startup migration sequence, normalize the Render database URL through the application/migration code, set the final Render service hostname in Vercel after it is known, retain `SRM_TRACKER_ACQUISITION_ENABLED=false`, explicitly document that notifications are unavailable in free staging, and add the clean-install commands.

- [ ] **Step 4: Run clean dependency and build checks**

Run:

```powershell
Set-Location C:\Users\varug\Attendance-extractor\frontend
npm ci
npm test
npm run typecheck
npm run lint
npm run build
Set-Location ..\connector
npm ci
npm test
npm run build -- https://srm-attendance-api-staging.onrender.com
Set-Location ..
.\scripts\verify_staging_config.ps1
```

Expected: clean installs, frontend checks, connector checks, and staging policy validation exit 0.

- [ ] **Step 5: Commit**

```powershell
git add render.yaml vercel.json frontend/package.json docs/DEPLOYMENT.md scripts/verify_staging_config.ps1
git commit -m "chore: make free staging manifests deployable"
```

### Task 4: Public-source audit and documentation checkpoint

**Files:**
- Modify: `docs/PROJECT_STATUS.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`
- Modify: `docs/STAGING_VERIFICATION_CHECKLIST.md`
- Modify: `docs/DEPLOYMENT.md`

- [ ] **Step 1: Audit tracked files and history**

Run `git ls-files`, `git grep` for secret/key/password/token/profile markers, `git log --all --name-status`, and `git log --all -- <sensitive paths>`. Confirm `AGENTS.md`, profiles, `.env`, raw portal output, and build artifacts are absent from the tracked tree and history. Preserve history only if the audit is clean; do not force-push a rewritten history.

- [ ] **Step 2: Record the verified local checkpoint**

Record the exact local commands/results, free-tier limitations, no-worker notification state, backup/expiry procedure, rollback instructions, and an explicit pending-authorization section without inventing URLs or live results.

- [ ] **Step 3: Commit documentation**

```powershell
git add docs/PROJECT_STATUS.md docs/IMPLEMENTATION_PLAN.md docs/STAGING_VERIFICATION_CHECKLIST.md docs/DEPLOYMENT.md
git commit -m "docs: record free staging deployment checkpoint"
```

### Task 5: Publish the verified source and provision hosting

Use the selected public repository `https://github.com/Googieman/75percenters` as `origin`, verify the Git identity has write access, push the audited `main` branch without force, then use the Render and Vercel account authorization flows to import that repository. Create only the free staging API and temporary PostgreSQL resources from the corrected Blueprint and the Vercel Hobby project. Enter the database/encryption secrets only in provider secret UIs. Keep acquisition disabled and notifications unavailable.

If GitHub, Render, or Vercel requires an interactive sign-in, stop at that exact flow and ask the user to complete only the sign-in; never request passwords, tokens, or encryption keys in chat.

### Task 6: Live verification, bootstrap, backup, and final record

After the providers return actual URLs, update the Vercel rewrite and Render frontend origin, redeploy, and verify HTTPS health, migrations, secure cookies, CSRF rejection, dashboard, logout, synthetic connector ingestion/history, cooldown/reconnect behavior, cold start, and reopening/focus refresh. Run the interactive local bootstrap command against the TLS database URL while its inbound access is restricted to the operator’s IP; the user enters the tracker password at the hidden prompt. Run `pg_dump` to a private local backup, restore it to disposable PostgreSQL, and verify history. Record actual URLs, deployed commit, verification results, rollback steps, and the database expiry date in the docs. Do not enable CampusWeb acquisition or claim the seven-day pilot is complete.

## Self-review

The plan covers the requested code blockers, free-tier topology, source publication, provider authorization, tracker bootstrap, live verification, backup/restore, documentation, and the explicit CampusWeb/notification gates. The only actions that may pause execution are interactive account sign-ins, secret/password entry, or a provider capability that cannot satisfy the requested free staging topology; those are recorded as external gates rather than guessed around.
