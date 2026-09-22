import assert from "node:assert/strict";
import { test } from "node:test";

import {
  openCampusWeb,
  requestCampusWebOpen,
} from "../src/campusweb-open.mjs";

test("opens CampusWeb with the fixed URL", async () => {
  let tabOptions;
  const result = await openCampusWeb(async (options) => {
    tabOptions = options;
  });

  assert.deepEqual(tabOptions, {
    url: "https://sp.srmist.edu.in/srmiststudentportal/",
  });
  assert.deepEqual(result, { ok: true });
});

test("returns OPEN_FAILED when CampusWeb cannot be opened", async () => {
  const result = await openCampusWeb(async () => {
    throw new Error("tab creation failed");
  });

  assert.deepEqual(result, { ok: false, errorCode: "OPEN_FAILED" });
});

test("requests CampusWeb with the exact worker message and returns success text", async () => {
  let message;
  const result = await requestCampusWebOpen(async (request) => {
    message = request;
    return { ok: true };
  });

  assert.deepEqual(message, { type: "OPEN_CAMPUSWEB" });
  assert.equal(result, "CampusWeb opened. Sign in there, then open the attendance report.");
});

test("returns failure text when the worker cannot open CampusWeb", async () => {
  const result = await requestCampusWebOpen(async () => ({
    ok: false,
    errorCode: "OPEN_FAILED",
  }));

  assert.equal(result, "Unable to open CampusWeb.");
});
