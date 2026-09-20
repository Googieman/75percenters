const LEGACY_PREFIXES = ["srm-tracker:dashboard:", "srm-tracker:account:"];
const LEGACY_KEYS = new Set(["studentData", "studentNetId", "studentTimetable", "studentCalendar"]);

export function clearLegacyAttendanceStorage(): void {
  try {
    for (const key of Object.keys(localStorage)) {
      if (LEGACY_KEYS.has(key) || LEGACY_PREFIXES.some((prefix) => key.startsWith(prefix))) {
        localStorage.removeItem(key);
      }
    }
  } catch {
    // Storage can be unavailable in private browsing; it is not required by the app.
  }
}
