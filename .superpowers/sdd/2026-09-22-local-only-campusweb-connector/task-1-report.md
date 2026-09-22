# Task 1 report: explicit local CampusWeb opener

Date: 2026-09-22

## Result

Implemented the local-only CampusWeb opener for the Chrome connector. The
popup opens CampusWeb only through the fixed Student Portal root, keeps the
root excluded from valid attendance collection contexts, and preserves the
existing explicit Sync flow and structured upload boundary.

## Files changed

- `connector/src/portal-policy.mjs` — exports the fixed
  `CAMPUSWEB_LOGIN_URL`.
- `connector/src/worker-policy.mjs` — accepts only the exact opener message
  and resolves it to the fixed URL; messages containing a caller-supplied URL
  are rejected.
- `connector/src/worker.mjs` — handles trusted `OPEN_CAMPUSWEB` messages with
  `chrome.tabs.create({ url: CAMPUSWEB_LOGIN_URL })`, returning `OPEN_FAILED`
  on failure.
- `connector/src/popup.html` — adds the `Open CampusWeb` action with
  `data-testid="open-campusweb"`.
- `connector/src/popup.mjs` — sends exactly `{ type: "OPEN_CAMPUSWEB" }` and
  displays the required success/failure messages.
- `connector/scripts/build.mjs` — packages the new worker policy module.
- `connector/tests/portal-policy.test.mjs` — covers the exact fixed URL and
  root-page rejection.
- `connector/tests/worker-policy.test.mjs` — covers exact-message acceptance
  and caller-supplied URL rejection.
- This report.

`connector/src/popup.css` was unchanged because the existing popup grid
spacing applies to the new button. `AGENTS.md` and the pre-existing untracked
plan file were not modified or staged.

## TDD RED/GREEN evidence

1. Added the fixed-URL policy test before the production export. `npm test`
   failed as expected with:
   `SyntaxError: The requested module '../src/portal-policy.mjs' does not provide an export named 'CAMPUSWEB_LOGIN_URL'`.
   The run reported 11 passing tests and 1 failing test.
2. Added the pure worker-policy test before the worker policy module. The
   targeted run failed as expected with the missing export and
   `ERR_MODULE_NOT_FOUND` for `src/worker-policy.mjs`.
3. Added the minimal implementation. The targeted RED/GREEN verification
   `npm test -- --test-name-pattern="fixed Student Portal login|exact opener message"`
   passed with 15/15 tests.

## Verification

- `npm test` from `connector`: passed, 15/15 tests.
- `npm run build -- https://srm-attendance-api-staging.onrender.com` from
  `connector`: passed.
- Built manifest audit: permissions remain `activeTab,scripting,storage`;
  `cookies` and `webRequest` are absent; the built `worker-policy.mjs` is
  present.
- Isolated worker/popup runtime smoke check: passed. It verified fixed-URL
  `tabs.create`, `OPEN_FAILED`, rejection of a message URL, the exact popup
  message, and both required popup status strings.
- `git diff --check`: passed.

## Self-review

- `CAMPUSWEB_LOGIN_URL` is exactly
  `https://sp.srmist.edu.in/srmiststudentportal/`.
- The login/root URL remains false for `isAllowedPortalUrl`.
- The worker still requires the existing trusted popup sender check.
- No popup-supplied URL reaches `chrome.tabs.create`.
- Existing report allow-list, validation, explicit Sync behavior, and
  structured upload code are unchanged.
- No credentials, cookies, session tokens, automatic login, or new browser
  permissions were added.

## Commit

Created with the required subject:

`feat: open CampusWeb from the local connector`

## Concerns

No known implementation concerns. Live portal/browser verification was not
performed; this task uses sanitized local tests and runtime doubles and does
not require entering real CampusWeb credentials.

