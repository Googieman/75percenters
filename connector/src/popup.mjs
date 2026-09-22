import { requestCampusWebOpen } from "./campusweb-open.mjs";

const status = document.querySelector("#status");
const pairing = document.querySelector("#pairing");
const pairingCode = document.querySelector("#pairing-code");
const pairButton = document.querySelector("#pair");
const openCampusWebButton = document.querySelector("#open-campusweb");
const syncButton = document.querySelector("#sync");
const message = document.querySelector("#message");
let syncInFlight = false;

document.addEventListener("DOMContentLoaded", refreshStatus, { once: true });
pairButton.addEventListener("click", pair);
openCampusWebButton.addEventListener("click", openCampusWeb);
syncButton.addEventListener("click", sync);

async function refreshStatus() {
  const result = await chrome.runtime.sendMessage({ type: "GET_STATUS" });
  if (!result?.ok) return showMessage("Connector status unavailable.");
  pairing.hidden = result.paired;
  syncButton.disabled = !result.paired;
  status.textContent = result.paired ? "Connector paired." : "Pair this connector with your account.";
}

async function pair() {
  pairButton.disabled = true;
  const result = await chrome.runtime.sendMessage({ type: "PAIR", code: pairingCode.value });
  pairButton.disabled = false;
  if (!result?.ok) return showMessage("Pairing failed. Check the code and try again.");
  pairing.hidden = true;
  syncButton.disabled = false;
  status.textContent = "Connector paired.";
  showMessage("Paired successfully.");
}

async function openCampusWeb() {
  openCampusWebButton.disabled = true;
  try {
    showMessage(await requestCampusWebOpen());
  } finally {
    openCampusWebButton.disabled = false;
  }
}

async function sync() {
  if (syncInFlight) return;
  syncInFlight = true;
  syncButton.disabled = true;
  try {
    showMessage("Collecting attendance…");
    const result = await chrome.runtime.sendMessage({ type: "SYNC" });
    if (!result?.ok) {
      showMessage(errorMessage(result?.errorCode));
      return;
    }
    showMessage("Attendance synced.");
  } finally {
    syncButton.disabled = false;
    syncInFlight = false;
  }
}

function showMessage(value) {
  message.textContent = value;
}

function errorMessage(code) {
  const messages = {
    AMBIGUOUS_FORM: "SRM returned more than one matching attendance form.",
    CONTEXT_INVALID: "The active SRM page does not contain the verified attendance form.",
    LOGIN_REQUIRED: "Log into SRM in the active tab, then try again.",
    NAVIGATION_CHANGED: "SRM changed pages during collection. Open the report and try again.",
    PORTAL_TAB_INVALID: "Open the SRM attendance report in the active tab first.",
    REQUEST_FAILED: "SRM did not return an attendance response. Try again from the report.",
    TIMEOUT: "SRM took too long to respond. Try again.",
    REVOKED: "This connector was revoked. Pair it again from the dashboard.",
    API_FAILED: "The tracker API rejected the sync without changing saved data.",
    RESULT_INVALID: "SRM returned an attendance response the connector could not verify.",
    RESPONSE_INVALID: "SRM returned an attendance response the connector could not verify.",
    WRONG_FRAME: "Open the SRM attendance report in the top-level tab and try again.",
  };
  return messages[code] || "Attendance sync failed without changing saved data.";
}
