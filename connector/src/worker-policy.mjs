import { CAMPUSWEB_LOGIN_URL } from "./portal-policy.mjs";

export function getCampusWebOpenUrl(message) {
  if (
    !message ||
    typeof message !== "object" ||
    Array.isArray(message) ||
    Object.keys(message).length !== 1 ||
    message.type !== "OPEN_CAMPUSWEB"
  ) {
    return null;
  }
  return CAMPUSWEB_LOGIN_URL;
}
