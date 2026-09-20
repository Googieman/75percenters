import { describe, expect, it } from "vitest";

import { formatGuidance, formatPercentage, formatSyncTime } from "../src/format";

describe("dashboard formatting", () => {
  it("formats percentages without changing numeric precision", () => {
    expect(formatPercentage(72.73)).toBe("72.73%");
  });

  it("labels a missing sync time clearly", () => {
    expect(formatSyncTime(null)).toBe("Not synced yet");
  });

  it("shows the number of absences still available as a margin", () => {
    expect(formatGuidance({ target_reachable: true, additional_absences_allowed: 2, additional_attended_hours: 0 })).toBe("2 Margin");
  });

  it("shows the number of attendance units still required when there is no margin", () => {
    expect(formatGuidance({ target_reachable: true, additional_absences_allowed: 0, additional_attended_hours: 4 })).toBe("4 Required");
  });

  it("keeps an exact-target subject at zero margin", () => {
    expect(formatGuidance({ target_reachable: true, additional_absences_allowed: 0, additional_attended_hours: 0 })).toBe("0 Margin");
  });

  it("keeps unreachable targets explicit", () => {
    expect(formatGuidance({ target_reachable: false, additional_absences_allowed: 0, additional_attended_hours: 0 })).toBe("Target is not reachable");
  });
});
