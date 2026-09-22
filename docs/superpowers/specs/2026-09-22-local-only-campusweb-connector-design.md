# Local-only CampusWeb connector design

## Intent

Allow the operator to use CampusWeb credentials to obtain attendance without
ever placing those credentials in the tracker PWA, API request body, database,
logs, extension storage, or repository. The tracker account remains a
separate dashboard-access account.

## Constraints

- The operator enters CampusWeb credentials and completes any CAPTCHA only on
  the normal SRM Student Portal page.
- The extension may use the authenticated tab's same-origin browser session,
  but it must not read, export, persist, or transmit cookies or session tokens.
- Attendance collection remains an explicit user action from the connector.
- The backend receives only the validated structured attendance payload already
  defined by the connector ingestion API.
- Hosted CampusWeb acquisition remains disabled in staging. Its existing
  backend code is retained behind the feature flag for a separately reviewed
  future decision.

## User flow

1. The operator signs in to the tracker with the separate tracker account.
2. The operator pairs the Chrome connector from the dashboard.
3. The connector popup offers `Open CampusWeb`, which opens the fixed Student
   Portal origin in a new tab.
4. The operator enters CampusWeb credentials directly on that portal page and
   completes any portal challenge.
5. The operator navigates to the verified attendance report page.
6. The operator presses `Sync attendance` in the connector popup.
7. The connector performs its existing bounded same-origin report request,
   validates the response, and sends only structured subject records to the
   authenticated tracker API.

## Changes

### Connector

- Define one fixed Student Portal login/root URL in the portal policy module.
- Add a popup `Open CampusWeb` action and a worker message handler that calls
  `chrome.tabs.create` with that fixed URL.
- Do not add credential fields, credential storage, cookie permissions, or
  automatic login behavior.
- Keep the existing exact report URL allow-list and explicit sync boundary.

### PWA

- Remove the CampusWeb NetID/password state, form, and API calls from the
  dashboard.
- Replace reconnect prompts with clear connector instructions and the
  existing pairing-code workflow.
- Keep tracker login, logout, attendance reads, history, and target settings
  unchanged.
- Keep notifications and hosted refresh unavailable in free on-demand
  staging.

### Documentation and tests

- Document the local-only flow, credential boundary, pairing, and recovery
  behavior in the connector and staging docs.
- Add connector tests for the fixed login URL and popup-to-worker open action.
- Replace the PWA hosted-credential test with an assertion that CampusWeb
  password controls and hosted credential calls are absent from staging UI.
- Run connector and frontend unit/build checks plus the existing backend suite.

## Failure handling

- If the operator is not on an exact allowed attendance report URL, Sync
  fails closed with the existing portal-tab error.
- If the portal redirects to login or returns malformed data, the connector
  shows the existing fixed error category and sends no upload.
- If the tracker API rejects the upload, the connector reports an API failure
  without retrying credentials or retaining the report response.

## Security review points

- No CampusWeb password appears in tracker API calls, frontend state sent to
  the backend, extension storage, logs, tests, fixtures, or docs.
- `chrome.tabs.create` is the only new browser capability; no `cookies`,
  `webRequest`, profile, or session-token permission is added.
- The hosted `/api/v1/srm/auth-attempts` routes stay unreachable while
  `SRM_TRACKER_ACQUISITION_ENABLED=false`.
