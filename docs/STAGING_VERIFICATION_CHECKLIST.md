# CampusWeb staging verification checklist

This checklist is the gate for the local-only CampusWeb Chrome connector and a
staging pilot. It records behavior without recording credentials, cookies,
tokens, raw portal responses, student identifiers, or attendance totals.

Keep `SRM_TRACKER_ACQUISITION_ENABLED=false` in free staging. The operator
enters CampusWeb credentials only on the normal Student Portal page, and the
connector sends only validated structured attendance to the API. The free-tier
deployment has no worker: it uses
`SRM_TRACKER_SYNC_EXECUTION_MODE=on_demand` and refreshes when the PWA opens.

## Prepare the staging runtime

- [ ] Use an isolated staging PostgreSQL database and a non-production PWA/API
  origin.
- [ ] Apply migrations with `python -m alembic upgrade head`.
- [ ] Configure a 32-byte active `SRM_TRACKER_SESSION_ENCRYPTION_KEY`.
- [ ] Configure `SRM_TRACKER_SESSION_ENCRYPTION_READ_KEYS` as needed for a
  rotation test; do not retire a key while ciphertext still depends on it.
- [ ] Configure the same VAPID public key, private key, and subject on the API
  and worker, or leave push disabled for the free-tier on-demand run.
- [ ] Keep `SRM_TRACKER_ACQUISITION_ENABLED=false`; hosted CampusWeb acquisition
  is outside this free-staging checkpoint.
- [ ] For free staging, start the API and verify the health endpoint before
  attempting a connection. For the later export, start the API and separate
  worker from the same release.
- [ ] Confirm logs contain statuses and fixed error categories only. Do not
  enter CampusWeb credentials into a shell, test fixture, issue, or chat.

## Free-tier deployment checks

- [ ] Source `main` is pushed to `Googieman/75percenters` without force-push; deployed commit `2f19977aa26d7996f66669973d7c6a8a1216b559` is recorded.
- [ ] Render creates exactly one free API and one temporary free PostgreSQL database; no worker or paid resource exists.
- [ ] API startup runs `alembic upgrade head` before Uvicorn and connects through the normalized Psycopg URL.
- [ ] Vercel installs with `npm --prefix frontend ci`, uses Node 24, and rewrites `/api/v1/*` to the actual Render hostname.
- [ ] The deployed staging URLs are `https://75percenters.vercel.app` and `https://srm-attendance-api-staging.onrender.com`; the temporary database expires 2026-10-22.
- [ ] Staging login sets `Secure` session and CSRF cookies; a write without the CSRF header is rejected.
- [ ] Dashboard load, logout, synthetic connector upload, subject history, and cross-user ownership checks pass over public HTTPS.
- [ ] Opening and returning to the PWA coalesces refreshes, respects cooldowns, shows retry/reconnect states, and never polls a queued job without a worker.
- [ ] Notifications remain unavailable in free on-demand staging.
- [ ] `pg_dump` is restored into disposable PostgreSQL and history is verified before the database expiry date.
- [ ] The tracker account is separate from CampusWeb. The connector's `Open CampusWeb` action opens the fixed Student Portal root; credentials are entered only there, and `Sync attendance` is explicit.
- [ ] The connector sends only validated structured subject records; it does not read, export, persist, or transmit cookies or session tokens.

## Required local-only Chrome connector checkpoint

Record only `pass`/`fail`, UTC timestamps, duration ranges, and fixed error
codes. A successful result must not include a copied response body or a
private account value. Keep hosted acquisition disabled throughout this
checkpoint.

| Check | Expected result | Result | Timestamp / fixed code |
| --- | --- | --- | --- |
| Tracker login | Separate tracker account signs in to the staging PWA |  |  |
| Connector pairing | Dashboard pairing code creates the connector device without exposing its credential in a URL |  |  |
| Open CampusWeb | `Open CampusWeb` opens the fixed Student Portal root |  |  |
| Student Portal login | Operator enters credentials and completes any challenge only on the normal portal page |  |  |
| Explicit sync | Operator opens the verified attendance report and presses `Sync attendance` |  |  |
| Attendance equivalence | Normalized subjects match the visible Student Portal report |  |  |
| Structured upload | API receives only validated subject records and history renders them |  |  |
| Failure boundary | Non-report pages, redirects, or malformed responses fail closed without an upload |  |  |
| Secret handling | Credentials, cookies, and session tokens are absent from extension storage, API payloads, logs, and docs |  |  |
| Hosted acquisition | Remains disabled throughout this local-only checkpoint |  |  |

If any check fails, leave acquisition disabled, record the fixed error code,
and correct the implementation or provider contract before retrying.

## Seven-day Android pilot

Start only after the local-only connector checkpoint passes. On the free tier,
keep the PWA open for the on-demand refresh portions. Closed-app refresh and
notifications are unavailable without a worker.

- [ ] Install the staging PWA on one Android device.
- [ ] Free tier: confirm one refresh starts when the PWA opens and completes
  while the PWA remains open.
- [ ] Worker-capable export: confirm an hourly refresh occurs while the PWA is
  closed and a worker restart recovers leases and scheduled work.
- [ ] Confirm notifications are unavailable in free on-demand staging; defer
  push and reauthentication-notice checks to a worker-capable export.
- [ ] Confirm offline use shows `Connection unavailable. Reconnect to load attendance.`
  and does not display stored attendance.
- [ ] Confirm disconnect cancels pending work and notices while preserving
  attendance history.

## Staging result

| Gate | Status | Evidence reference |
| --- | --- | --- |
| Local Chrome connector checkpoint |  |  |
| Hosted CampusWeb acquisition | Intentionally disabled |  |
| Hosted restart and recovery |  |  |
| Seven-day Android pilot |  |  |
| Ready for production planning |  |  |

Free-tier limitation: temporary PostgreSQL does not replace backups. Export a
database dump before expiry or migration, and do not treat this staging mode as
the regular-use release.

Remove or redact any local notes containing sensitive values before committing
or sharing results.
