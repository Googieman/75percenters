import { api } from "./api";

export type PushRegistrationResult = "registered" | "denied" | "unsupported" | "unconfigured";

function decodeKey(value: string): ArrayBuffer {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
  const binary = atob(padded);
  const output = new Uint8Array(new ArrayBuffer(binary.length));
  for (let index = 0; index < binary.length; index += 1) output[index] = binary.charCodeAt(index);
  return output.buffer as ArrayBuffer;
}

export async function requestAndRegisterPush(publicKey: string | undefined): Promise<PushRegistrationResult> {
  if (!("Notification" in window) || !("serviceWorker" in navigator)) return "unsupported";
  if (!publicKey) return "unconfigured";
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return "denied";
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: decodeKey(publicKey),
  });
  await api.registerPush(subscription.toJSON());
  return "registered";
}
