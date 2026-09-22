import {
  createAttendanceUploadPayload,
  isTrustedPopupSender,
  validateCollectorResult,
} from "./message-policy.mjs";
import { openCampusWeb } from "./campusweb-open.mjs";
import { CAMPUSWEB_LOGIN_URL, isAllowedPortalUrl } from "./portal-policy.mjs";
import { getCampusWebOpenUrl } from "./worker-policy.mjs";

const API_ORIGIN = "__SRM_TRACKER_API_ORIGIN__";
const WORKER_ERROR_CODES = Object.freeze({
  API_FAILED: "API_FAILED",
  NOT_PAIRED: "NOT_PAIRED",
  OPEN_FAILED: "OPEN_FAILED",
  PORTAL_TAB_INVALID: "PORTAL_TAB_INVALID",
  REVOKED: "REVOKED",
  UNKNOWN: "UNKNOWN",
});

let syncInFlight = null;

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!isTrustedPopupSender(sender, chrome.runtime.getURL("/"), chrome.runtime.id)) {
    return false;
  }
  if (!message || typeof message.type !== "string") {
    sendResponse({ ok: false, errorCode: WORKER_ERROR_CODES.UNKNOWN });
    return false;
  }
  if (getCampusWebOpenUrl(message) === CAMPUSWEB_LOGIN_URL) {
    openCampusWeb().then(sendResponse);
    return true;
  }
  if (message.type === "GET_STATUS") {
    chrome.storage.local.get(["device_id"]).then(({ device_id }) => {
      sendResponse({ ok: true, paired: Number.isInteger(device_id) });
    });
    return true;
  }
  if (message.type === "PAIR") {
    pair(message.code).then(sendResponse);
    return true;
  }
  if (message.type === "SYNC") {
    if (!syncInFlight) syncInFlight = syncAttendance().finally(() => (syncInFlight = null));
    syncInFlight.then(sendResponse);
    return true;
  }
  sendResponse({ ok: false, errorCode: WORKER_ERROR_CODES.UNKNOWN });
  return false;
});

async function pair(code) {
  if (typeof code !== "string" || !code.trim()) {
    return { ok: false, errorCode: "PAIRING_CODE_INVALID" };
  }
  try {
    const response = await fetch(`${API_ORIGIN}/api/v1/connector/pair`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: code.trim(), name: "Chrome connector" }),
    });
    const body = await response.json();
    if (!response.ok || typeof body.device_token !== "string") {
      return { ok: false, errorCode: "PAIRING_FAILED" };
    }
    await chrome.storage.local.set({ device_id: body.device_id, device_token: body.device_token });
    return { ok: true };
  } catch {
    return { ok: false, errorCode: "PAIRING_FAILED" };
  }
}

async function syncAttendance() {
  const { device_token: token } = await chrome.storage.local.get(["device_token"]);
  if (typeof token !== "string" || !token) {
    return { ok: false, errorCode: WORKER_ERROR_CODES.NOT_PAIRED };
  }
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (tab?.id === undefined || !isAllowedPortalUrl(tab.url)) {
    return { ok: false, errorCode: WORKER_ERROR_CODES.PORTAL_TAB_INVALID };
  }
  let injected;
  try {
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      world: "MAIN",
      files: ["page-collector.js"],
    });
    injected = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      world: "MAIN",
      func: () => globalThis.__srmTrackerCollectAttendance?.(),
    });
  } catch {
    return { ok: false, errorCode: WORKER_ERROR_CODES.PORTAL_TAB_INVALID };
  }
  const result = validateCollectorResult(injected?.[0]?.result);
  if (!result.ok) return result;
  try {
    const response = await fetch(`${API_ORIGIN}/api/v1/connector/attendance`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: createAttendanceUploadPayload(result.records),
    });
    if (response.status === 401) return { ok: false, errorCode: WORKER_ERROR_CODES.REVOKED };
    if (!response.ok) return { ok: false, errorCode: WORKER_ERROR_CODES.API_FAILED };
    const body = await response.json();
    return { ok: true, syncedAt: body.synced_at, snapshotsCreated: body.snapshots_created };
  } catch {
    return { ok: false, errorCode: WORKER_ERROR_CODES.API_FAILED };
  }
}
