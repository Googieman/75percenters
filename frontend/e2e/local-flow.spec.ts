import { execFileSync } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { chromium, expect, test, type BrowserContext, type Page, type Route } from "@playwright/test";

const FRONTEND_URL = process.env.E2E_FRONTEND_URL || "http://127.0.0.1:5173";
const PORTAL_PAGE_URL =
  "https://sp.srmist.edu.in/srmiststudentportal/students/report/studentAttendanceDetails.jsp";
const ATTENDANCE_ENDPOINT =
  "https://sp.srmist.edu.in/srmiststudentportal/students/report/studentAttendanceDetails.jsp";
const EMAIL = process.env.E2E_ACCOUNT_EMAIL || "e2e-owner@example.com";
const PASSWORD = process.env.E2E_ACCOUNT_PASSWORD || "e2e-password-1234";

test.describe.configure({ mode: "serial" });

let context: BrowserContext;
let app: Page;
let portal: Page;
let popup: Page;
let portalAttendance = attendanceHtml([
  ["CSE1", "Algorithms", 23, 16, 7, "69.57"],
  ["MAT1", "Mathematics", 10, 8, 2, "80"],
]);
let portalMode: "attendance" | "login" = "attendance";
let attendanceRequests = 0;

test.beforeAll(async () => {
  const extensionDir = process.env.E2E_CONNECTOR_DIR;
  if (!extensionDir) throw new Error("E2E_CONNECTOR_DIR is required; connector build was not provided");
  context = await chromium.launchPersistentContext(mkdtempSync(join(tmpdir(), "srm-e2e-profile-")), {
    args: [`--disable-extensions-except=${extensionDir}`, `--load-extension=${extensionDir}`],
    headless: false,
  });
  portal = await context.newPage();
  await portal.route("**/*", portalRoute);
  await portal.goto(PORTAL_PAGE_URL);
  const worker = context.serviceWorkers()[0] || await context.waitForEvent("serviceworker");
  const extensionId = new URL(worker.url()).host;
  popup = await context.newPage();
  await popup.goto(`chrome-extension://${extensionId}/popup.html`);
  app = await context.newPage();
  await app.goto(FRONTEND_URL);
});

test.afterAll(async () => {
  await context?.close();
});

test("complete flow pairs the real popup and renders persisted attendance/history", async () => {
  await expect(app.getByTestId("login-button")).toBeVisible();
  await app.getByTestId("email").fill(EMAIL);
  await app.getByTestId("password").fill(PASSWORD);
  await app.getByTestId("login-button").click();
  await expect(app.getByTestId("generate-pairing")).toBeVisible();

  await app.getByTestId("generate-pairing").click();
  const code = await app.getByTestId("pairing-code").textContent();
  expect(code).toBeTruthy();
  await popup.getByTestId("pairing-code").fill(code!);
  await popup.getByTestId("pair-button").click();
  await expect(popup.getByTestId("connector-status")).toHaveText("Connector paired.");
  expect(attendanceRequests).toBe(0);

  await portal.bringToFront();
  await popup.getByTestId("sync-button").click();
  await expect(popup.getByTestId("message")).toHaveText("Attendance synced.");
  expect(attendanceRequests).toBe(1);

  const state = support("state");
  expect(state.snapshots).toBe(2);
  await app.reload();
  await expect(app.getByTestId("overall-percentage")).toHaveText("72.73%");
  await expect(app.getByTestId("subject-CSE1")).toContainText("16/23");
  await expect(app.getByTestId("last-sync")).not.toHaveText("Not synced yet");
  await app.getByTestId("history-button-CSE1").click();
  await expect(app.getByTestId("history-CSE1")).toContainText("16/23");
});

test("unchanged and duplicate sync actions do not create duplicate snapshots", async () => {
  const before = attendanceRequests;
  await portal.bringToFront();
  await popup.evaluate(() => {
    const button = document.querySelector("[data-testid=sync-button]")!;
    button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  await expect(popup.getByTestId("message")).toHaveText("Attendance synced.");
  expect(attendanceRequests - before).toBe(1);
  expect(support("state").snapshots).toBe(2);
});

test("changed and corrected attendance creates one history snapshot per change", async () => {
  portalAttendance = attendanceHtml([
    ["CSE1", "Algorithms", 24, 17, 7, "70.83"],
    ["MAT1", "Mathematics", 10, 8, 2, "80"],
  ]);
  await portal.bringToFront();
  await popup.getByTestId("sync-button").click();
  await expect(popup.getByTestId("message")).toHaveText("Attendance synced.");
  portalAttendance = attendanceHtml([
    ["CSE1", "Algorithms", 24, 15, 9, "62.5"],
    ["MAT1", "Mathematics", 10, 8, 2, "80"],
  ]);
  await popup.getByTestId("sync-button").click();
  await expect(popup.getByTestId("message")).toHaveText("Attendance synced.");
  expect(support("state").snapshots).toBe(4);
  await app.reload();
  await expect(app.getByTestId("subject-CSE1")).toContainText("15/24");
});

test("omitted subjects remain stored and malformed portal data is not uploaded", async () => {
  portalAttendance = attendanceHtml([["CSE1", "Algorithms", 24, 15, 9, "62.5"]]);
  await portal.bringToFront();
  await popup.getByTestId("sync-button").click();
  await app.reload();
  await expect(app.getByTestId("subject-CSE1")).toBeVisible();
  await expect(app.getByTestId("subject-MAT1")).toBeVisible();

  const beforeRequests = attendanceRequests;
  const beforeSnapshots = support("state").snapshots;
  portalMode = "login";
  await popup.getByTestId("sync-button").click();
  await expect(popup.getByTestId("message")).toHaveText("Log into SRM in the active tab, then try again.");
  expect(attendanceRequests).toBe(beforeRequests + 1);
  expect(support("state").snapshots).toBe(beforeSnapshots);
  portalMode = "attendance";
});

test("invalid mixed batches roll back and revocation leaves attendance unchanged", async () => {
  const before = support("state");
  const code = await createPairingCodeInApp();
  const token = await app.evaluate(async (pairingCode) => {
    const csrf = document.cookie.split("; ").find((value) => value.startsWith("srm_tracker_csrf="))?.split("=")[1];
    const response = await fetch("/api/v1/connector/pair", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: pairingCode }),
    });
    if (!response.ok || !csrf) throw new Error("direct test pairing failed");
    return (await response.json()).device_token as string;
  }, code);
  const invalid = await app.evaluate(async (deviceToken) => {
    const response = await fetch("/api/v1/connector/attendance", {
      method: "POST",
      headers: { Authorization: `Bearer ${deviceToken}`, "Content-Type": "application/json" },
      body: JSON.stringify({ subjects: [
        { code: "NEW1", subject: "New", total_hours: 2, attended_hours: 1, absent_hours: 1, source_percentage: "50" },
        { code: "BAD1", subject: "Bad", total_hours: 2, attended_hours: 2, absent_hours: 2, source_percentage: "100" },
      ] }),
    });
    return response.status;
  }, token);
  expect(invalid).toBe(422);
  expect(support("state").snapshots).toBe(before.snapshots);

  const devices = await app.evaluate(async () => (await fetch("/api/v1/devices")).json());
  const connectorId = (devices as Array<{ device_id: number }>).at(-1)!.device_id;
  await app.evaluate(async (deviceId) => {
    const csrf = document.cookie.split("; ").find((value) => value.startsWith("srm_tracker_csrf="))?.split("=")[1];
    await fetch(`/api/v1/devices/${deviceId}`, { method: "DELETE", headers: { "X-CSRF-Token": decodeURIComponent(csrf || "") } });
  }, connectorId);
  await portal.bringToFront();
  await popup.getByTestId("sync-button").click();
  await expect(popup.getByTestId("message")).toHaveText("This connector was revoked. Pair it again from the dashboard.");
  expect(support("state").snapshots).toBe(before.snapshots);
});

test("expired tracker sessions require sign-in after reload", async () => {
  support("expire-session");
  await app.reload();
  await expect(app.getByTestId("login-button")).toBeVisible();
});

async function portalRoute(route: Route) {
  const url = route.request().url();
  if (url === ATTENDANCE_ENDPOINT && route.request().method() === "POST") {
    attendanceRequests += 1;
    if (portalMode === "login") {
      await route.fulfill({ status: 200, contentType: "text/html", body: "<title>Login</title><form><input type='password'></form>" });
      return;
    }
    await route.fulfill({ status: 200, contentType: "text/html", body: portalAttendance });
    return;
  }
  if (url === PORTAL_PAGE_URL) {
    await route.fulfill({ status: 200, contentType: "text/html", body: portalPageHtml() });
    return;
  }
  await route.abort();
}

function portalPageHtml() {
  return `<!doctype html><html><body><form id="attendance-form">
    <input name="iden" value="9"><input name="filter" value=""><input name="hdnFormDetails" value="1"><input name="csrfPreventionSalt" value="synthetic-csrf">
  </form><table><tr>
    <th>Code</th><th>Description</th><th>Max. hours</th><th>Att. hours</th>
    <th>Absent hours</th><th>Total Percentage</th>
  </tr><tr><td>FIXTURE1</td><td>Fixture Subject</td><td>10</td><td>8</td><td>2</td><td>80.00</td></tr></table></body></html>`;
}

function attendanceHtml(records: Array<[string, string, number, number, number, string]>) {
  const rows = records.map(([code, subject, total, attended, absent, percentage]) =>
    `<tr><td>${code}</td><td>${subject}</td><td>${total}</td><td>${attended}</td><td>${absent}</td><td>${percentage}</td></tr>`,
  ).join("");
  return `<!doctype html><html><body><table><tr><th>Code</th><th>Description</th><th>Max. hours</th><th>Att. hours</th><th>Absent hours</th><th>Total Percentage</th></tr>${rows}</table></body></html>`;
}

function support(command: string) {
  const python = process.env.E2E_SUPPORT_PYTHON || "python";
  const output = execFileSync(python, ["backend/scripts/e2e_support.py", command], {
    cwd: process.env.E2E_REPO_ROOT,
    env: process.env,
    encoding: "utf8",
  });
  return JSON.parse(output);
}

async function createPairingCodeInApp() {
  await app.getByTestId("generate-pairing").click();
  return (await app.getByTestId("pairing-code").textContent())!;
}
