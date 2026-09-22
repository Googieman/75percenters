import assert from "node:assert/strict";
import { test } from "node:test";

import { CAMPUSWEB_LOGIN_URL } from "../src/portal-policy.mjs";
import { getCampusWebOpenUrl } from "../src/worker-policy.mjs";

test("resolves only the exact opener message to the fixed CampusWeb URL", () => {
  assert.equal(
    getCampusWebOpenUrl({ type: "OPEN_CAMPUSWEB" }),
    CAMPUSWEB_LOGIN_URL,
  );
  assert.equal(
    getCampusWebOpenUrl({
      type: "OPEN_CAMPUSWEB",
      url: "https://example.test/steal-this-navigation",
    }),
    null,
  );
});
