# CampusWeb staging verification checklist

This checklist is the gate between the implemented CampusWeb adapter and a
staging pilot. It records behavior without recording credentials, cookies,
tokens, raw portal responses, student identifiers, or attendance totals.

Keep `SRM_TRACKER_ACQUISITION_ENABLED=false` until every required checkpoint
below is complete. Enable it only in an isolated staging deployment with the
same encryption keyring and VAPID configuration on the API and worker. The
free-tier deployment has no worker: it uses
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
- [ ] Set `SRM_TRACKER_ACQUISITION_ENABLED=true` only for this staging run.
- [ ] For free staging, start the API and verify the health endpoint before
  attempting a connection. For the later export, start the API and separate
  worker from the same release.
- [ ] Confirm logs contain statuses and fixed error categories only. Do not
  enter a CampusWeb password into a shell, test fixture, issue, or chat.

## Required CampusWeb checkpoint

Record only `pass`/`fail`, UTC timestamps, duration ranges, and fixed error
codes. A successful result must not include a copied response body or a
private account value.

| Check | Expected result | Result | Timestamp / fixed code |
| --- | --- | --- | --- |
| Student Portal login | Explicit Connect succeeds through the fixed Student Portal routes; no Academia request occurs |  |  |
| Verified identity | Provider identity is accepted and pending NetID is promoted only after verification |  |  |
| Attendance equivalence | Normalized subjects match the visible Student Portal report |  |  |
| Session persistence | API/worker restart restores encrypted session state and a later refresh succeeds |  |  |
| Teaching-day comparison 1 | First sanitized comparison recorded |  |  |
| Teaching-day comparison 2 | Second comparison recorded |  |  |
| Attendance change | A later comparison reflects one real source change |  |  |
| Natural expiry | Expired upstream state produces `Reconnect required` without exposing provider details |  |  |
| Recovery | Reconnect restores refresh and preserves attendance history |  |  |
| Secret handling | Password is absent from storage, jobs, logs, responses, and notification payloads |  |  |

If any check fails, leave acquisition disabled, record the fixed error code,
and correct the implementation or provider contract before retrying.

## Seven-day Android pilot

Start only after the CampusWeb checkpoint passes. Keep the PWA closed for the
scheduled refresh portions only after exporting to a worker-capable platform.
On the free tier, keep the PWA open for the on-demand refresh portions.

- [ ] Install the staging PWA on one Android device.
- [ ] Free tier: confirm one refresh starts when the PWA opens and completes
  while the PWA remains open.
- [ ] Worker-capable export: confirm an hourly refresh occurs while the PWA is
  closed and a worker restart recovers leases and scheduled work.
- [ ] Confirm a reauthentication notification uses the stable reconnect tag,
  contains no account or attendance identifiers, and opens the reconnect view.
- [ ] Confirm a 404/410 push endpoint is removed and temporary delivery errors
  retry without duplicate notices.
- [ ] Confirm offline use shows `Connection unavailable. Reconnect to load attendance.`
  and does not display stored attendance.
- [ ] Confirm disconnect cancels pending work and notices while preserving
  attendance history.

## Staging result

| Gate | Status | Evidence reference |
| --- | --- | --- |
| Own-account CampusWeb checkpoint |  |  |
| Hosted restart and recovery |  |  |
| Seven-day Android pilot |  |  |
| Ready for production planning |  |  |

Free-tier limitation: temporary PostgreSQL does not replace backups. Export a
database dump before expiry or migration, and do not treat this staging mode as
the regular-use release.

Remove or redact any local notes containing sensitive values before committing
or sharing results.
