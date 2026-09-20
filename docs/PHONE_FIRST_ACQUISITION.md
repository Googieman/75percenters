# Phone-first hosted acquisition

## Decision

The production shape is Android PWA → hosted FastAPI → an evidence-approved SRM acquisition provider → the existing PostgreSQL attendance/history store. Render will run the API and a separate background worker; the PWA origin will proxy `/api/v1/*` to FastAPI. The worker is durable and PostgreSQL-backed, so refresh does not depend on an open phone, browser tab, or in-process API task.

The CampusWeb Student Portal adapter is implemented but remains feature-gated until authorized own-account and hosted-runtime evidence is complete. No SCOPE or hosted-browser fallback is used.

## Implemented foundation

- Alembic migration `0002_hosted_acquisition` adds owner-scoped SRM connections, expiring authentication attempts, leased/fenced sync jobs, Web Push subscriptions, and a deduplicated notification outbox. Existing attendance/history tables and connector devices remain intact.
- `User.last_successful_sync_at` is backfilled from existing connector activity and is now the source-independent freshness field.
- Attendance ingestion is shared by the connector and hosted worker. Owner locking, duplicate suppression, downward corrections, omitted-subject behavior, transaction rollback, connection generations, and job fencing are preserved.
- The fixed-destination CampusWeb adapter uses only the Student Portal routes at `campusapi.fly.dev`, bounded HTTPX requests, identity/semester evidence, encrypted cookie state, and strict structured attendance mapping. It never attempts the Academia route.
- Provider state is encrypted with AES-GCM, bound to owner/provider/generation/attempt context, versioned with active/read keys, rotated resumably, and kept server-side. Passwords and OTP/challenge answers are not stored, queued, or returned.
- `AcquisitionProvider` and `HostedSyncResult` define the narrow adapter boundary. Provider HTML, cookies, and tokens do not enter attendance schemas or the dashboard.
- The worker claims jobs with expiring leases, recovers abandoned claims, schedules connected accounts hourly, coalesces manual/initial refreshes, retries transient failures after 5/15 minutes with bounded `Retry-After`, pauses on source-contract changes, and creates one reauthentication notice per generation.
- The `/api/v1/srm/*` and `/api/v1/push-subscriptions/*` interfaces expose safe status, queue, job-read, disconnect, authentication, and push CRUD behavior. The provider and acquisition flag are still disabled by default.
- The PWA shows Connected, Refreshing, Reconnect required, Source changed, and unavailable states; polls active jobs every five seconds; supports phone Connect/Reconnect; and stores no attendance or authentication data in browser storage. The service worker never caches authenticated API responses and opens the reconnect screen from a data-free push notice.
- `render.yaml` defines separate API and worker services with PostgreSQL; `vercel.json` defines the same-origin API rewrite. Provisioning and secret entry remain manual deployment steps.

## Feasibility evidence gate

| Candidate | Current state | Production decision |
| --- | --- | --- |
| CampusWeb Student Portal ordinary HTTP | Public Student Portal login/attendance paths are implemented as a fixed, fail-closed adapter. Own-account login, restoration, expiry, attendance equivalence, and hosted-runtime evidence are still not recorded here. | Selected for gated staging only |
| SCOPE | Official SRMIST listing exists, but no documented backend API or equivalent authenticated attendance contract is recorded. | Not selected |
| Hosted browser | No persistent hosted worker/VM and no manual phone-controlled login evidence are available in this repository. | Not selected |
| Existing Chrome connector | Normal authenticated Chrome flow is verified locally and retained as an optional fallback. | Not the phone-first production source |

Required next evidence is the bounded own-account checkpoint: successful Student Portal login without Academia fallback; restart-and-restore; three sanitized comparisons across two teaching days including a change; natural expiry and recovery; and a hosted-runtime read without retained passwords. Record only field names/statuses/timings and never commit authenticated response bodies. Until that evidence exists, keep `SRM_TRACKER_ACQUISITION_ENABLED=false`.

## Security boundary

The backend accepts a CampusWeb password only during an explicit Connect/Reconnect request. It never stores, queues, logs, traces, or returns the password, cookies, tokens, challenge answers, or raw upstream responses. The provider adapter receives the password only as an active call argument and returns normalized records plus verified source context. Disconnect cancels pending work and notices, clears active/challenge ciphertext, increments the connection generation, and preserves attendance history. CampusWeb has no verified logout endpoint in the observed contract, so no guessed logout request is sent.

The browser still uses only the app session cookie and CSRF token. It never receives SRM cookies, tokens, raw responses, or device-attestation material.
