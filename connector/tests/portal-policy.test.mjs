import assert from "node:assert/strict";
import { test } from "node:test";

import { CAMPUSWEB_LOGIN_URL, isAllowedPortalUrl } from "../src/portal-policy.mjs";

test("defines the fixed CampusWeb login URL without allowing it as a report context", () => {
  assert.equal(CAMPUSWEB_LOGIN_URL, "https://sp.srmist.edu.in/srmiststudentportal/");
  assert.equal(isAllowedPortalUrl(CAMPUSWEB_LOGIN_URL), false);
});

test("allows the verified live portal report page", () => {
  assert.equal(
    isAllowedPortalUrl(
      "https://sp.srmist.edu.in/srmiststudentportal/students/template/HRDSystem.jsp",
    ),
    true,
  );
});

test("rejects unrelated portal pages and untrusted origins", () => {
  assert.equal(
    isAllowedPortalUrl("https://sp.srmist.edu.in/srmiststudentportal/students/template/Other.jsp"),
    false,
  );
  assert.equal(
    isAllowedPortalUrl("https://example.test/srmiststudentportal/students/template/HRDSystem.jsp"),
    false,
  );
});
