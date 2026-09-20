import { afterEach, describe, expect, it, vi } from "vitest";

const registerPush = vi.hoisted(() => vi.fn());
vi.mock("../src/api", () => ({ api: { registerPush } }));

import { requestAndRegisterPush } from "../src/push";

describe("web push registration", () => {
  afterEach(() => vi.restoreAllMocks());

  it("requests permission only after the app action and registers the owned subscription", async () => {
    const requestPermission = vi.fn().mockResolvedValue("granted");
    Object.defineProperty(window, "Notification", { configurable: true, value: { requestPermission } });
    const subscription = { toJSON: () => ({ endpoint: "https://push.example/1", keys: { p256dh: "p", auth: "a" } }) };
    const subscribe = vi.fn().mockResolvedValue(subscription);
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: { ready: Promise.resolve({ pushManager: { subscribe } }) },
    });

    const result = await requestAndRegisterPush("B".repeat(32));

    expect(result).toBe("registered");
    expect(requestPermission).toHaveBeenCalledTimes(1);
    expect(subscribe).toHaveBeenCalledTimes(1);
    expect(registerPush).toHaveBeenCalledWith(subscription.toJSON());
  });
});
