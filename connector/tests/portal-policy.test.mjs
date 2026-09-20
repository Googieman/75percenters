import assert from "node:assert/strict";
import { test } from "node:test";

import { isAllowedPortalUrl } from "../src/portal-policy.mjs";

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
