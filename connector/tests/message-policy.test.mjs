import assert from "node:assert/strict";
import { test } from "node:test";

import {
  COLLECTOR_ERROR_CODES,
  createAttendanceUploadPayload,
  isTrustedPopupSender,
  validateCollectorResult,
} from "../src/message-policy.mjs";

test("accepts messages only from the exact extension popup URL", () => {
  const runtimeUrl = "chrome-extension://abc123/";
  assert.equal(
    isTrustedPopupSender(
      { id: "abc123", url: "chrome-extension://abc123/popup.html" },
      runtimeUrl,
      "abc123",
    ),
    true,
  );
  assert.equal(
    isTrustedPopupSender(
      { id: "abc123", url: "chrome-extension://abc123/options.html" },
      runtimeUrl,
      "abc123",
    ),
    false,
  );
  assert.equal(
    isTrustedPopupSender(
      { id: "other", url: "chrome-extension://abc123/popup.html" },
      runtimeUrl,
      "abc123",
    ),
    false,
  );
});

test("accepts only a strictly shaped successful collector result", () => {
  assert.deepEqual(
    validateCollectorResult({
      ok: true,
      records: [
        {
          code: "CSE1",
          subject: "Algorithms",
          total_hours: 23,
          attended_hours: 16,
          absent_hours: 7,
          source_percentage: "69.57",
        },
      ],
    }),
    { ok: true, records: [
      {
        code: "CSE1",
        subject: "Algorithms",
        total_hours: 23,
        attended_hours: 16,
        absent_hours: 7,
        source_percentage: "69.57",
      },
    ] },
  );
  assert.deepEqual(validateCollectorResult({ ok: true, records: [{ html: "portal" }] }), {
    ok: false,
    errorCode: COLLECTOR_ERROR_CODES.RESULT_INVALID,
  });
  assert.deepEqual(validateCollectorResult({ ok: false, errorCode: "arbitrary text" }), {
    ok: false,
    errorCode: COLLECTOR_ERROR_CODES.RESULT_INVALID,
  });
});

test("creates an upload containing only structured subject records", () => {
  const payload = JSON.parse(createAttendanceUploadPayload([
    {
      code: "CSE1",
      subject: "Algorithms",
      total_hours: 23,
      attended_hours: 16,
      absent_hours: 7,
      source_percentage: "69.57",
    },
  ]));
  assert.deepEqual(Object.keys(payload), ["subjects"]);
  assert.equal("csrfPreventionSalt" in payload, false);
  assert.equal("cookie" in payload, false);
});
