# SRM Attendance Tracker Implementation Plan

This plan is intentionally milestone-based so every session can end at a clean, verified, committed checkpoint.

## Non-negotiable constraints

- Never automate login, CAPTCHA, browser fingerprint changes, or cookie/profile export. Do not run `scraper.py`.
- Do not commit sensitive portal responses, browser profiles, `.env` files, credentials, session tokens, or device credentials.
- Tests use sanitized fixtures and a disposable local PostgreSQL database only; live SRM validation is a separate manual action.
- Each milestone must update `docs/PROJECT_STATUS.md`, run its stated checks, and be committed before moving on.

## Phone-first redesign addendum — provider-gated

The phone-first redesign in `docs/PHONE_FIRST_ACQUISITION.md` supersedes the assumption that the desktop connector is the production acquisition path. The existing connector remains an optional, verified fallback. The hosted foundation is implemented behind `SRM_TRACKER_ACQUISITION_ENABLED=false` by default.

The next implementation gate is authorized evidence for the implemented CampusWeb Student Portal adapter: complete the own-account login, restart restoration, attendance equivalence, expiry/recovery, and hosted-runtime checkpoint. Do not store SRM passwords, cookies, profiles, raw responses, CAPTCHA answers, OTPs, or browser fingerprint values. Do not claim hourly hosted refresh or Android reauthentication until the seven-day staging pilot proves it.

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

**Deliverable:** Accessible installable dashboard and subject-detail views with theme support, target setting, historical cumulative snapshots, explicit connector guidance, and a clear unavailable state when attendance cannot be loaded.

1. Scaffold React/Vite/TypeScript with component tests, linting, type checks, PWA manifest, icons, and service worker.
2. Test-drive dashboard cards, shortage states, empty/loading/error states, and no-mobile-direct-sync behavior.
3. Implement authenticated API client and protected app routes without placing session credentials in browser storage.
4. Cache only the app shell and known legacy cache keys. Never cache authenticated API responses or attendance/authentication state; offline attendance must show the unavailable message.
5. Add fixture-backed end-to-end flow; verify production build; update status and commit.

## Milestone 4 — Chrome connector

**Deliverable:** A packaged Manifest V3 extension with minimal fixed host permissions, polished popup, explicit pairing confirmation, user-triggered SRM request, validated portal response, and revocation/error states.

1. Test parser boundary and extension data validation with fixtures; keep all request code packaged with the extension.
2. Implement main-world, same-origin request execution only after a popup Sync action. Obtain a CSRF value from the page only if legitimately present and needed.
3. Implement pairing code exchange and encrypted-at-rest-where-supported extension storage for device credential; never log it or include it in a URL.
4. Build popup status/error UI and package ZIP.
5. Perform the single manual live SRM verification described in the status file; update status and commit.

## Milestone 5 — Free-tier staging preparation and Render configuration

**Deliverable:** Complete README, [staging verification checklist](STAGING_VERIFICATION_CHECKLIST.md), free-tier `render.yaml`, Vercel install/build settings, staging CORS/environment design, migration command, and pre-deploy verification record.

1. Confirm current official Render documentation, plans, database durability, costs, and limits before provisioning.
2. For free staging, use the tested on-demand API execution path and one PWA refresh on dashboard open; reserve the durable worker for later export.
3. Test the staging configuration locally, build the frontend, and verify the API health and fixture ingestion/read flow.
4. Document local setup, extension loading/pairing, limitations, troubleshooting, rollback/credential revocation, and free-database export.
5. Update status and commit.

## Milestone 6 — Authorized deployment and live verification

**Deliverable:** A live free staging PWA/API backed by temporary PostgreSQL, or a precisely documented authorization/source-host blocker. Regular use requires a later durable database and worker-capable export.

1. Obtain only the required Render/Vercel account connection, private source-host authorization, staging secrets, and free-tier resource authorization from the user.
2. Provision through Render’s secure workflow, run migrations, configure exact production origins, and deploy.
3. Verify public PWA, API health, database connectivity, authentication, migrations, HTTPS cookies, CSRF, logout, and fixture-based ingestion/read flow.
4. Record confirmed URLs, deployment state, package location, final test evidence, limitations, and remaining manual SRM test. Export the database before free-tier expiry.

The code/configuration gate for this milestone is complete: staging cookies are
`Secure`, application and Alembic URLs use Psycopg 3, Render migrations run
from the startup command, Vercel uses the staging API hostname, the PWA refresh
lifecycle is bounded for no-worker hosting, and on-demand staging does not
advertise notifications. The external deployment and database bootstrap gates
remain open.
