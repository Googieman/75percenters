# Task 6 — Live SRM Verification Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. The user performs normal SRM login, CAPTCHA, and explicit live Sync actions.

**Goal:** Verify that the packaged connector collects attendance from the user's normal authenticated Chrome session and persists accurate totals/history in the local tracker.

**Architecture:** Continue from Task 5 commit `1565548` on `codex/verify-local-attendance-flow`. Run the existing FastAPI, PostgreSQL, and React application locally. Inspect the real portal contract before adapting the isolated connector, then exercise the actual toolbar popup.

**Tech Stack:** Normal Google Chrome, Manifest V3 connector, FastAPI, PostgreSQL 16, React/TypeScript/Vite; synthetic tests use the existing test toolchains.

**Spec:** `docs/PROJECT_STATUS.md` (live-verification requirement and security boundary), `docs/IMPLEMENTATION_PLAN.md` (connector milestone). This Task 6 means live portal verification, not the older document's deployment Milestone 6.

## Global constraints

- No SRM password collection, automated login/CAPTCHA, cookie/session/profile export, fingerprint changes, or legacy scraper execution.
- Do not save raw authenticated HTML, HAR exports, tokens, or screenshots containing private portal information to the repository or reports.
- Preserve public API and schema. Store only validated structured attendance in the user's local tracker database.
- Keep destructive database-reset tests on the disposable test database. Never point them at the live-verification database.
- No deployment, merge, or push is part of this plan. Continue in the existing Task 5 worktree.
- A mismatch stops collection without upload. Fix only a contract supported by observed evidence; do not weaken validation or widen portal permissions to force success.

## Review focus

1. The visible portal URL may differ from the attendance POST endpoint; verify both separately in Task 2.
2. The attendance report may be nested in a frame; verify frame ownership in Task 2 and retain fail-closed behavior if the current top-level design cannot support it.
3. CSRF controls may be absent, duplicated, or supplied through another legitimate page mechanism; establish provenance without recording the value in Task 2.
4. Synthetic tests currently use a direct popup URL and persistent portal host permission; they do not establish a toolbar-granted activeTab boundary. Verify actual toolbar behavior and audit permissions in Tasks 1 and 3.
5. A successful popup message can hide stale or incomplete data; compare every visible subject and repeat unchanged sync with timestamp/snapshot assertions in Task 3.

## Task 1: Prepare a reproducible local verification environment

**Files:** Read `backend/README.md`, `backend/src/srm_tracker/admin.py`, `backend/src/srm_tracker/config.py`, `docker-compose.yml`, `frontend/vite.config.ts`, `connector/scripts/build.mjs`, `connector/src/manifest.json`. Record sanitized setup in `docs/live-verification.md`.

- [x] Read current status and plan; inspect Git changes and confirm `1565548` is present. Preserve unrelated changes.
- [x] Audit Task 5 evidence before relying on it. The E2E opens `popup.html` directly; the manifest also grants portal host access, so the previous claim that activeTab was proved is too strong. Record this limitation and inspect actual permission needs. Do not treat manual testing as retroactive satisfaction of the original automated-action requirement.
- [x] Inspect existing local database resources before starting anything. Use a dedicated, named PostgreSQL 16 database/container with persistent storage and an explicit loopback binding for personal attendance. Record its exact identity and connection configuration in ignored local settings. Do not use the disposable E2E runner for this database.
- [x] Configure backend frontend origin as `http://127.0.0.1:5173`, frontend API proxy as `http://127.0.0.1:8000`, and connector API origin as `http://127.0.0.1:8000`; if ports are occupied, choose and record a consistent alternative.
- [x] Install missing locked dependencies, apply `python -m alembic upgrade head` from `backend`, and verify database connectivity. Bootstrap the tracker account with `python -m srm_tracker.admin bootstrap` only if no account exists. The user enters a distinct tracker password in the hidden prompt.
- [x] Start API and frontend bound to loopback. Verify API health, tracker sign-in, empty/existing dashboard state, and pairing-code generation. Keep live-verification services available through the manual test.
- [x] From `connector`, run `npm run build -- http://127.0.0.1:8000`. Inspect the built manifest and worker for the exact configured API origin and no unexpected hosts.
- [x] In normal Chrome, load the built `connector/dist` directory through Extensions → Developer mode → Load unpacked. Pin its toolbar icon. Pair using a freshly generated tracker code; record only success, never the code or credential.

## Task 2: Establish the real portal contract and make focused fixes

**Files:** Inspect `connector/src/worker.mjs`, `connector/src/collector.mjs`, `connector/src/page-collector.js`, `connector/src/message-policy.mjs`; if necessary modify these and their tests. Create sanitized structural fixtures under `connector/tests/fixtures/`. Document evidence in `docs/live-verification.md`.

- [x] The user logs into SRM normally, completes CAPTCHA, and opens attendance through normal portal navigation. Do not navigate directly to the POST endpoint as a substitute for opening the report.
- [x] Inspect only the attendance-related structure: top-level URL, frame nesting, the report form, named control uniqueness, table headings, and response shape. Record structural descriptions; omit student identifiers, secrets, values of CSRF/session fields, and private URL parameters.
- [x] Confirm the legitimate attendance request method/endpoint and field names from a normal user-triggered report request. Inspect CSRF provenance locally without copying its value. No full page dumps or network exports.
- [x] Compare observations to the worker's exact URL check, which currently assumes the visible page equals `studentAttendanceDetails.jsp`, and to its top-level form assumptions. This is an unresolved assumption, not a verified live contract.
- [x] If a mismatch exists, pause live sync and implement the smallest supported connector fix. For nested-frame or different-origin designs that materially change the security boundary, document the issue and resolve the design before enabling collection.
- [x] Build synthetic fixtures from the observed structure using invented subject data and token placeholders. Add a failing regression for each actual mismatch before fixing it. Test the code that is actually injected; avoid covering only the parallel Node parser implementation.
- [x] Run connector tests and packaging checks after connector changes. Run the synthetic E2E after changing the collection/upload path; update its synthetic portal structure to match the verified contract without any live data. Keep failure conditions fail-closed.
- [x] Rebuild and reload the unpacked extension. Re-pair only if storage or extension identity changed.

## Task 3: Verify the real toolbar-to-dashboard flow

**Files:** Record sanitized outcomes in `docs/live-verification.md`; inspect attendance through existing authenticated reads and read-only database queries. Do not reuse the destructive disposable-database test helper on this database.

- [x] Establish initial subject/snapshot counts and last successful sync. Observe that extension installation, popup status, and pairing cause no connector attendance POST; distinguish these from requests the portal itself makes while displaying its report.
- [x] With the authenticated attendance tab active, the user clicks the actual Chrome toolbar icon and presses Sync once. Observe popup result, collector outcome, API status, and committed counts without logging credentials or raw bodies.
- [x] Check the outgoing API body locally for only the allowed structured subject fields. Confirm no portal cookie, CSRF marker, raw HTML, or student/session metadata is included. Record a pass/fail statement, not the payload.
- [x] Reload the PWA. Compare every current subject's code and cumulative totals with the visible portal report. Verify overall calculations, last-sync update, and initial history. Keep individual personal totals out of committed verification notes.
- [x] Perform one explicit unchanged Sync. Verify the successful-sync timestamp advances while snapshot counts remain unchanged. If portal data changed naturally, account for that change and do not falsely label it an idempotency failure.
- [x] Switch to an unrelated tab and press Sync: expect a clear rejection, no connector attendance request, and no database writes.
- [x] Verify an unauthenticated portal result if the user is ready to log out through normal portal controls. Otherwise retain synthetic expiry coverage and explicitly mark live expiry untested; do not delete cookies or force logout to manufacture the test.
- [x] If a live attempt fails, classify the fixed error code and inspect the relevant contract only. Stop repeated live retries until a concrete cause has been fixed and checked offline. Do not fabricate portal totals to test correction cases live.

## Task 4: Record evidence and hand off

**Files:** Update `docs/PROJECT_STATUS.md`, `docs/live-verification.md`, and `backend/README.md` where setup descriptions are stale; commit any focused connector fixes and their synthetic regressions.

- [x] Record date, commit, Chrome/extension versions, local origins, structural contract findings, checks performed, and remaining uncertainties. Distinguish observed facts, user reports, and untested assumptions.
- [x] Correct Task 5 documentation where its automated coverage was overstated. Record manual toolbar verification separately; do not claim the direct popup test proved activeTab permission necessity.
- [x] Run checks proportional to the final diff: connector tests/build for connector fixes; frontend checks for UI changes; backend tests/Ruff/mypy if backend code changes; synthetic E2E for any changed integration path. Database-reset suites remain sequential and disposable.
- [x] Review the Git diff for sensitive data, unintended permission expansion, and unrelated edits; run `git diff --check`.
- [x] Commit the verified outcome as `test: verify live SRM connector flow`. If live compatibility is blocked, commit accurate findings/fixes and leave Task 6 incomplete rather than claiming success.
- [x] Document service stop/restart instructions and preserve the user's attendance database. Only stop resources started for this task; do not remove its persistent data.

## Completion criteria

Task 6's successful live-flow checkpoint requires normal authenticated Chrome, a real toolbar Sync, validated upload, accurate persisted dashboard/history, and a verified unchanged repeat. All remaining manual checks and any Task 5 automated-coverage gaps must be explicit. A fixture pass alone cannot complete this checkpoint. Production deployment and broader offline/dashboard work remain separate.
