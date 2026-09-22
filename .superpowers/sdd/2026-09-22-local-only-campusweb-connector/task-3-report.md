# Task 3 report — documentation for the local-only CampusWeb connector

## Task objective

Document the approved local-only CampusWeb connector flow without changing the
four deployment and verification documents, the repository instructions, or the
implementation plan. The documentation must keep tracker authentication separate
from CampusWeb authentication, keep hosted acquisition disabled, and preserve the
existing staging deployment, backup, rollback, and expiry details.

## Implementation

- Commit: `37603c06fcd8200f024ab11a5e40be9a7bd8a95d`
- Commit subject: `docs: document local-only CampusWeb connector`
- Files changed:
  - `docs/DEPLOYMENT.md`
  - `docs/STAGING_VERIFICATION_CHECKLIST.md`
  - `docs/PROJECT_STATUS.md`
  - `docs/IMPLEMENTATION_PLAN.md`

## Audits

The stale hosted-credential audit was run exactly as follows:

```powershell
rg -n "CampusWeb password|srmPassword|startAuth|completeAuth|forwarded to CampusWeb" frontend/src docs/DEPLOYMENT.md docs/STAGING_VERIFICATION_CHECKLIST.md
```

Result: exit code `1` and no matches. No stale hosted CampusWeb credential
instructions were found.

The positive local-only marker audit was run exactly as follows:

```powershell
rg -n "Open CampusWeb|local-only|Chrome connector|SRM_TRACKER_ACQUISITION_ENABLED=false" frontend/src connector/src docs/DEPLOYMENT.md docs/STAGING_VERIFICATION_CHECKLIST.md
```

Result: exit code `0`, with positive matches for `Open CampusWeb`, `local-only`,
`Chrome connector`, and `SRM_TRACKER_ACQUISITION_ENABLED=false` in the requested
frontend, connector, and documentation paths.

The documentation diff check was run as follows:

```powershell
git diff --check 37603c0^ 37603c0
```

Result: exit code `0`; no whitespace errors were reported.

## Self-review

Self-review confirmed that the four requested documents are the only files in the
documentation commit, the tracker account remains distinct from CampusWeb, the
CampusWeb password is entered only on the normal portal page, no CampusWeb
credentials or session tokens are directed to the backend, and
`SRM_TRACKER_ACQUISITION_ENABLED=false` remains documented for staging. The
untracked `AGENTS.md` and approved plan file were not modified.

## Tests

No tests were run beyond the documentation audits listed above.

## Concerns and pending public verification

Public staging verification remains pending. The deployed PWA/API still need the
operator’s public checks for tracker login, pairing, opening CampusWeb, explicit
attendance sync, synthetic history, cookies, CSRF, cold starts, reconnect and
interrupted-refresh behavior, and Chrome connector behavior. CampusWeb syncing
must remain disabled for hosted acquisition until the separate own-account
verification gate passes.
