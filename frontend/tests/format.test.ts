import { describe, expect, it } from "vitest";

import { formatPercentage, formatSyncTime } from "../src/format";

describe("dashboard formatting", () => {
  it("formats percentages without changing numeric precision", () => {
    expect(formatPercentage(72.73)).toBe("72.73%");
  });

  it("labels a missing sync time clearly", () => {
    expect(formatSyncTime(null)).toBe("Not synced yet");
  });
});
