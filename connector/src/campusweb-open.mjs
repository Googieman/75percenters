import { CAMPUSWEB_LOGIN_URL } from "./portal-policy.mjs";

const CAMPUSWEB_OPEN_SUCCESS_MESSAGE =
  "CampusWeb opened. Sign in there, then open the attendance report.";
const CAMPUSWEB_OPEN_FAILURE_MESSAGE = "Unable to open CampusWeb.";

export async function openCampusWeb(createTab = chrome.tabs.create) {
  try {
    await createTab({ url: CAMPUSWEB_LOGIN_URL });
    return { ok: true };
  } catch {
    return { ok: false, errorCode: "OPEN_FAILED" };
  }
}

export async function requestCampusWebOpen(sendMessage = chrome.runtime.sendMessage) {
  try {
    const result = await sendMessage({ type: "OPEN_CAMPUSWEB" });
    return result?.ok ? CAMPUSWEB_OPEN_SUCCESS_MESSAGE : CAMPUSWEB_OPEN_FAILURE_MESSAGE;
  } catch {
    return CAMPUSWEB_OPEN_FAILURE_MESSAGE;
  }
}
