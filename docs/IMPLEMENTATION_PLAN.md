# SRM Attendance Tracker Implementation Plan

This plan is intentionally milestone-based so every session can end at a clean, verified, committed checkpoint.

## Non-negotiable constraints

- Never automate login, CAPTCHA, browser fingerprint changes, or cookie/profile export. Do not run `scraper.py`.
- Do not commit sensitive portal responses, browser profiles, `.env` files, credentials, session tokens, or device credentials.
- Tests use sanitized fixtures and a disposable local PostgreSQL database only; live SRM validation is a separate manual action.
- Each milestone must update `docs/PROJECT_STATUS.md`, run its stated checks, and be committed before moving on.

## Milestone 0 — Repository control plane

**Deliverable:** A safe Git baseline, architecture record, status handoff, and complete implementation map.

1. Initialize Git, create `.gitignore`, and inspect the pre-existing scraper without executing it.
2. Record the architecture and milestones in `docs/superpowers/specs/` and this plan.
3. Verify ignored sensitive directories and whitespace; commit the checkpoint.

## Milestone 1 — Domain core and backend foundation

**Deliverable:** A Python package with a strict SRM table parser, target calculations, FastAPI health endpoint, sanitized fixtures, and a test/lint/type-check toolchain.

1. Create backend dependency lock/configuration, application layout, `.env.example`, and test commands.
2. Test-drive table-header matching, numeric parsing, login/malformed response rejection, and known-good attendance parsing.
3. Test-drive target calculations for zero totals, exact target, below target, above target, and impossible targets.
4. Add FastAPI configuration and a health endpoint; run backend tests, linting, type checks, and a production import/build check.
5. Update status and commit.

## Milestone 2 — Persistence, secure API, and connector pairing — complete

**Deliverable:** PostgreSQL/Alembic data model with user isolation, snapshot idempotency, first-user bootstrap, protected reads, one-time pairing, device revocation, and validated ingestion. Verified with 44 integration tests against disposable PostgreSQL, Ruff, mypy, pip check, and the migration upgrade/downgrade/re-upgrade cycle.

1. Test-drive models and services for subject ownership, snapshots, duplicate handling, and genuine change history.
2. Add Alembic migrations and local PostgreSQL Compose workflow.
3. Add Argon2 password hashing/session support, CSRF protection for cookie-authenticated writes, database-backed rate limits, strict configured CORS, and secure environment validation.
4. Test-drive pairing expiry, device-token hashing, revocation, malformed ingestion rejection, concurrent serialization, and cross-user authorization failures.
5. Run the fixture bootstrap → login → pair → upload → history → revoke flow against a disposable database; update status and commit.

## Milestone 3 — Responsive PWA dashboard

**Deliverable:** Accessible installable dashboard and subject-detail views with theme support, target setting, historical cumulative snapshots, explicit connector guidance, and safely labeled offline cached data.

1. Scaffold React/Vite/TypeScript with component tests, linting, type checks, PWA manifest, icons, and service worker.
2. Test-drive dashboard cards, shortage states, empty/loading/error states, and no-mobile-direct-sync behavior.
3. Implement authenticated API client and protected app routes without placing session credentials in browser storage.
4. Add runtime caching for latest authenticated attendance data and offline/saved-data indicators.
5. Add fixture-backed end-to-end flow; verify production build; update status and commit.

## Milestone 4 — Chrome connector

**Deliverable:** A packaged Manifest V3 extension with minimal fixed host permissions, polished popup, explicit pairing confirmation, user-triggered SRM request, validated portal response, and revocation/error states.

1. Test parser boundary and extension data validation with fixtures; keep all request code packaged with the extension.
2. Implement main-world, same-origin request execution only after a popup Sync action. Obtain a CSRF value from the page only if legitimately present and needed.
3. Implement pairing code exchange and encrypted-at-rest-where-supported extension storage for device credential; never log it or include it in a URL.
4. Build popup status/error UI and package ZIP.
5. Perform the single manual live SRM verification described in the status file; update status and commit.

## Milestone 5 — Release preparation and Render configuration

**Deliverable:** Complete README, deployment checklist, `render.yaml`, production CORS/environment design, migration command, and pre-deploy verification record.

1. Confirm current official Render documentation, plans, database durability, costs, and limits before provisioning.
2. Test the production configuration locally, build the frontend, and verify the API health and fixture ingestion/read flow.
3. Document local setup, extension loading/pairing, limitations, troubleshooting, and rollback/credential revocation.
4. Update status and commit.

## Milestone 6 — Authorized deployment and live verification

**Deliverable:** A live PWA/API backed by durable PostgreSQL, or a precisely documented authorization/billing blocker.

1. Obtain only the required Render account, durable database plan, secrets, and source-host authorization from the user.
2. Provision through Render’s secure workflow, run migrations, configure exact production origins, and deploy.
3. Verify public PWA, API health, database connectivity, authentication, migrations, and fixture-based ingestion/read flow.
4. Record confirmed URLs, deployment state, package location, final test evidence, limitations, and any remaining manual SRM test.
