# Phone-first hosted acquisition

## Decision

The production shape is Android PWA → hosted FastAPI → an evidence-approved SRM acquisition provider → the existing PostgreSQL attendance/history store. Render will run the API and a separate background worker; the PWA origin will proxy `/api/v1/*` to FastAPI. The worker is durable and PostgreSQL-backed, so refresh does not depend on an open phone, browser tab, or in-process API task.

The concrete provider remains feature-gated. No code assumes that direct Student Portal HTTP, SCOPE, or a hosted browser is accepted by SRM.

## Implemented foundation

- Alembic migration `0002_hosted_acquisition` adds owner-scoped SRM connections, expiring authentication attempts, leased/fenced sync jobs, Web Push subscriptions, and a deduplicated notification outbox. Existing attendance/history tables and connector devices remain intact.
- `User.last_successful_sync_at` is backfilled from existing connector activity and is now the source-independent freshness field.
- Attendance ingestion is shared by the connector and hosted worker. Owner locking, duplicate suppression, downward corrections, omitted-subject behavior, transaction rollback, connection generations, and job fencing are preserved.
- Provider state is encrypted with AES-GCM, bound to owner/provider/generation context, versioned for rotation, and kept server-side. Passwords and OTP/challenge answers are not stored, queued, or returned.
- `AcquisitionProvider` and `HostedSyncResult` define the narrow adapter boundary. Provider HTML, cookies, and tokens do not enter attendance schemas or the dashboard.
- The worker claims jobs with expiring leases, recovers abandoned claims, retries transient failures after 5/15 minutes, pauses on source-contract changes, and creates one reauthentication notice per connection generation.
- The `/api/v1/srm/*` and `/api/v1/push-subscriptions/*` interfaces are present. Status, queue, job-read, disconnect, and push CRUD are live; authentication start/complete returns a safe `503` until a provider passes the evidence gates.
- The PWA shows Connected, Refreshing, Reconnect required, Source changed, and unavailable states; refresh is explicit; cached attendance is account-scoped and labeled; notification permission is requested only after a button action. The service worker never caches authenticated API responses.

## Feasibility evidence gate

| Candidate | Current state | Production decision |
| --- | --- | --- |
| Student Portal ordinary HTTP | Public login contract is documented in the supplied investigation, but no own-account credential submission, session restoration, expiry, or hosted-runtime test is recorded here. | Not selected |
| SCOPE | Official SRMIST listing exists, but no documented backend API or equivalent authenticated attendance contract is recorded. | Not selected |
| Hosted browser | No persistent hosted worker/VM and no manual phone-controlled login evidence are available in this repository. | Not selected |
| Existing Chrome connector | Normal authenticated Chrome flow is verified locally and retained as an optional fallback. | Not the phone-first production source |

Required next evidence is the bounded Gate A/B/C experiment from the supplied redesign plan. It must use the user's own normal authentication and manual CAPTCHA/OTP actions where required, record only sanitized field names/statuses/timings, and prove repeated hosted reads, session restoration, expiry recovery, and (for SCOPE) three paired equivalence observations. Until that evidence exists, keep `SRM_TRACKER_ACQUISITION_ENABLED=false`.

## Security boundary

The backend never accepts an SRM password into a durable record, queue, log, trace, or error body. The provider adapter must receive a password only as an active call argument and must return normalized records plus verified source context. Disconnect cancels pending work, increments the connection generation, removes active encrypted state, and preserves attendance history. Backup retention and upstream logout behavior remain deployment/provider-specific.

The browser still uses only the app session cookie and CSRF token. It never receives SRM cookies, tokens, raw responses, or device-attestation material.
