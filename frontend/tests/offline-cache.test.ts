import { describe, expect, it } from "vitest";

import { clearLegacyAttendanceStorage } from "../src/legacy-cache-cleanup";

describe("legacy attendance storage cleanup", () => {
  it("removes old attendance and account-selection keys", () => {
    localStorage.setItem("srm-tracker:dashboard:7", "old attendance");
    localStorage.setItem("studentData", "old portal data");
    localStorage.setItem("studentNetId", "old account");
    localStorage.setItem("unrelated-preference", "keep");

    clearLegacyAttendanceStorage();

    expect(localStorage.getItem("srm-tracker:dashboard:7")).toBeNull();
    expect(localStorage.getItem("studentData")).toBeNull();
    expect(localStorage.getItem("studentNetId")).toBeNull();
    expect(localStorage.getItem("unrelated-preference")).toBe("keep");
  });
});
