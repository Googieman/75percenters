import { describe, expect, it } from "vitest";

import { Attendance } from "../src/api";
import { loadDashboardCache, saveDashboardCache } from "../src/offline";

const attendance: Attendance = {
  attendance_target: 75,
  subjects: [],
  overall: {
    current_percentage: null,
    additional_attended_hours: 0,
    additional_absences_allowed: 0,
    target_reachable: true,
  },
  last_successful_sync: null,
};

describe("account-scoped offline dashboard cache", () => {
  it("round-trips cached data with a visible cache timestamp", () => {
    saveDashboardCache(7, attendance, "2026-09-21T10:00:00.000Z");

    expect(loadDashboardCache(7)).toEqual({
      attendance,
      cachedAt: "2026-09-21T10:00:00.000Z",
    });
  });

  it("does not expose one account's cache to another account", () => {
    saveDashboardCache(7, attendance, "2026-09-21T10:00:00.000Z");

    expect(loadDashboardCache(8)).toBeNull();
  });
});
