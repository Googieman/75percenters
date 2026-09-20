import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../src/api";

describe("phone acquisition API client", () => {
  afterEach(() => vi.restoreAllMocks());

  it("queues a hosted refresh through the relative API without portal access", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ job_id: 4, status: "queued" }), { status: 202 }),
    );

    const result = await api.queueSync();

    expect(result.job_id).toBe(4);
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/srm/sync",
      expect.objectContaining({ method: "POST", credentials: "include" }),
    );
  });
});
