import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { JSDOM } from "jsdom";

import {
  COLLECTOR_ERROR_CODES,
  collectAttendance,
  parseCollectorResponse,
} from "../src/collector.mjs";

globalThis.DOMParser = new JSDOM().window.DOMParser;

const ENDPOINT =
  "https://sp.srmist.edu.in/srmiststudentportal/students/report/studentAttendanceDetails.jsp";
const PAGE_COLLECTOR_SOURCE = await readFile(
  new URL("../src/page-collector.js", import.meta.url),
  "utf8",
);

function portalPage({ csrf = "", duplicateIden = false } = {}) {
  return `<!doctype html><html><body>
    <form id="attendance-form">
      <input name="iden" value="9">
      ${duplicateIden ? '<input name="iden" value="9">' : ""}
      <input name="filter" value="">
      <input name="hdnFormDetails" value="1">
      <input name="csrfPreventionSalt" value="${csrf}">
    </form>
    <table><tr>
      <th>Code</th><th>Description</th><th>Max. hours</th><th>Att. hours</th>
      <th>Absent hours</th><th>Total Percentage</th>
    </tr><tr><td>FIXTURE1</td><td>Fixture Subject</td><td>10</td><td>8</td><td>2</td><td>80.00</td></tr></table>
  </body></html>`;
}

function livePortalPage({ includeReport = true } = {}) {
  return `<!doctype html><html><body>
    <form method="post" action="/srmiststudentportal/students/template/HRDSystem.jsp">
      <input type="hidden" name="hidchkHostelOpen" value="0">
      <input type="hidden" name="hdnFormStatus" value="active">
      <input type="hidden" name="hdnFormId" value="attendance">
      <input type="hidden" name="hdnFormDetails" value="1">
      <input type="hidden" name="hdnFilename" value="studentAttendanceDetails.jsp">
      <input type="hidden" name="csrfPreventionSalt" value="fixture-csrf">
    </form>
    ${
      includeReport
        ? `<table><tr>
      <th>Code</th><th>Description</th><th>Max. hours</th><th>Att. hours</th>
      <th>Absent hours</th><th>Total Percentage</th>
    </tr><tr><td>FIXTURE1</td><td>Fixture Subject</td><td>10</td><td>8</td><td>2</td><td>80.00</td></tr></table>`
        : ""
    }
  </body></html>`;
}

function attendanceResponse(header = "Attended hours") {
  return `<!doctype html><html><body><table><tr>
    <th>Code</th><th>Description</th><th>Max. hours</th><th>${header}</th>
    <th>Absent hours</th><th>Total Percentage</th>
  </tr><tr><td>CSE1</td><td>Algorithms</td><td>23</td><td>16</td><td>7</td><td>69.57</td></tr>
  </table></body></html>`;
}

function documentFor(html, url = "https://sp.srmist.edu.in/srmiststudentportal/home.jsp") {
  return new JSDOM(html, { url }).window.document;
}

test("accepts the documented Att. hours spelling", () => {
  const result = parseCollectorResponse(attendanceResponse("Att. hours"));
  assert.deepEqual(result, [
    {
      code: "CSE1",
      subject: "Algorithms",
      total_hours: 23,
      attended_hours: 16,
      absent_hours: 7,
      source_percentage: "69.57",
    },
  ]);
});

test("collects from the current live SRM attendance form contract", async () => {
  const page = new JSDOM(livePortalPage(), {
    url: "https://sp.srmist.edu.in/srmiststudentportal/students/template/HRDSystem.jsp",
    runScripts: "dangerously",
  });
  let request;
  page.window.fetch = async (url, options) => {
    request = { url, options };
    return { ok: true, text: async () => attendanceResponse() };
  };
  page.window.eval(PAGE_COLLECTOR_SOURCE);

  const result = await page.window.__srmTrackerCollectAttendance();

  assert.equal(result.ok, true);
  assert.equal(request.url, ENDPOINT);
  assert.equal(request.options.method, "POST");
  assert.deepEqual(
    [...new URLSearchParams(request.options.body).keys()],
    [
      "hidchkHostelOpen",
      "hdnFormStatus",
      "hdnFormId",
      "hdnFormDetails",
      "hdnFilename",
      "csrfPreventionSalt",
    ],
  );
});

test("rejects the same-origin portal shell when the attendance report is absent", async () => {
  const page = new JSDOM(livePortalPage({ includeReport: false }), {
    url: "https://sp.srmist.edu.in/srmiststudentportal/students/template/HRDSystem.jsp",
    runScripts: "dangerously",
  });
  let requestStarted = false;
  page.window.fetch = async () => {
    requestStarted = true;
    return { ok: true, text: async () => attendanceResponse() };
  };
  page.window.eval(PAGE_COLLECTOR_SOURCE);

  const result = await page.window.__srmTrackerCollectAttendance();

  assert.equal(result.ok, false);
  assert.equal(result.errorCode, "CONTEXT_INVALID");
  assert.equal(requestStarted, false);
});

test("keeps the 30-second timeout active while reading the response body", async () => {
  const page = documentFor(portalPage());
  let aborted = false;
  const fetchImpl = async (_url, options) => {
    options.signal.addEventListener("abort", () => {
      aborted = true;
    });
    return {
      ok: true,
      text: () => new Promise(() => {}),
    };
  };

  const result = await collectAttendance({
    document: page,
    locationHref: () => page.defaultView.location.href,
    fetchImpl,
    timeoutMs: 10,
  });
  assert.deepEqual(result, { ok: false, errorCode: COLLECTOR_ERROR_CODES.TIMEOUT });
  assert.equal(aborted, true);
});

test("rejects ambiguous portal form controls", async () => {
  const page = documentFor(portalPage({ duplicateIden: true }));
  const result = await collectAttendance({
    document: page,
    locationHref: () => page.defaultView.location.href,
    fetchImpl: async () => ({ ok: true, text: async () => attendanceResponse() }),
  });
  assert.deepEqual(result, { ok: false, errorCode: COLLECTOR_ERROR_CODES.AMBIGUOUS_FORM });
});

test("rejects collection from an incorrect frame context", async () => {
  const page = documentFor(portalPage());
  const result = await collectAttendance({
    document: page,
    isTopLevel: () => false,
    locationHref: () => page.defaultView.location.href,
    fetchImpl: async () => ({ ok: true, text: async () => attendanceResponse() }),
  });
  assert.deepEqual(result, { ok: false, errorCode: COLLECTOR_ERROR_CODES.WRONG_FRAME });
});

test("rejects a navigation change before and after the response body", async () => {
  const page = documentFor(portalPage());
  let currentUrl = page.defaultView.location.href;
  let calls = 0;
  const result = await collectAttendance({
    document: page,
    locationHref: () => {
      calls += 1;
      if (calls === 2) currentUrl = "https://sp.srmist.edu.in/login";
      return currentUrl;
    },
    fetchImpl: async () => ({ ok: true, text: async () => attendanceResponse() }),
  });
  assert.deepEqual(result, { ok: false, errorCode: COLLECTOR_ERROR_CODES.NAVIGATION_CHANGED });
});

test("returns a fixed response error for malformed attendance results", () => {
  assert.deepEqual(parseCollectorResponse("<html><body>login</body></html>"), {
    ok: false,
    errorCode: COLLECTOR_ERROR_CODES.RESPONSE_INVALID,
  });
});
