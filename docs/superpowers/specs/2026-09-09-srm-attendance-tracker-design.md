# SRM Attendance Tracker Design

## Scope

Build a personal, installable attendance viewer for SRM student totals. It supports cross-device viewing, manual Chrome-based refresh, cumulative history, and target calculations. Direct phone-to-SRM sync and absence-detail extraction are out of scope for this release.

## Architecture

The frontend is a React/TypeScript/Vite PWA. The FastAPI API persists application accounts, subjects, cumulative attendance snapshots, pairing codes, and device credentials in PostgreSQL. The dashboard reads only its authenticated owner’s records.

A Chrome Manifest V3 extension is the sole SRM connector. After an explicit user action, packaged code executes in the authenticated SRM page context and makes the documented attendance POST request with dynamic CSRF data when legitimately required. It parses and validates the six-column table locally, then sends structured records to the API over HTTPS using a device credential created by a short-lived pairing code. The API never receives SRM passwords, cookies, browser profile contents, or raw HTML.

## Data and history

`User` owns `Subject`, `AttendanceSnapshot`, `PairingCode`, and `ConnectorDevice` records. Subject codes are unique per user. Each successful sync is normalized to integer source totals and stored only when a subject’s totals change; unchanged submissions update the device’s last-seen metadata without fabricating history. Source percentage may be retained for audit but dashboard calculations derive from attended and total hours.

For target `T` (0 < T <= 100), current attendance is `A / H` where `A` is attended hours and `H` is total hours. The displayed percentage is rounded half-up to two decimal places, but target decisions use unrounded totals. Additional attended hours to reach target are `max(0, ceil((T*H-A)/(1-T)))` for T < 100; at 100%, a non-perfect record is impossible to repair with finite additional attended hours. Additional absences allowed are `max(0, floor(A/T-H))`. Zero total hours has no percentage or target recommendation.

## Security

Application sessions are secure, HTTP-only cookies with CSRF validation for state-changing browser requests. Passwords use a maintained Argon2-capable library; initial registration is disabled after the configured bootstrap/invite path. Device tokens are high-entropy opaque values stored hashed server-side, limited to ingestion, revocable, and never placed in URLs/logs. API inputs use explicit schemas; ownership checks apply to every query; malformed uploads are rejected transactionally. Production configuration uses HTTPS, exact CORS origins, secrets from environment variables, and rate limiting.

## UX and offline behavior

The mobile-first dashboard presents overall attendance, subject indicators, shortage warnings, sync recency, and clear loading/error/empty states. The Sync affordance explains that a paired Chrome extension is required and is unavailable for direct mobile portal refresh. The service worker caches the app shell and last successful attendance responses; offline data is visibly labeled saved/cached rather than current.

## Verification boundaries

Parser, math, persistence, authorization, pairing, and UI behavior are tested locally with sanitized fixtures. A real SRM request is verified manually by the user while normally logged into Chrome, after extension packaging. Render deployment and billing require authorization and a durable-database selection before provisioning.
