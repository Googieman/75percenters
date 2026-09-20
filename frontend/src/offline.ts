import { Attendance } from "./api";

export type DashboardCache = {
  attendance: Attendance;
  cachedAt: string;
};

function cacheKey(userId: number): string {
  return `srm-tracker:dashboard:${userId}`;
}

export function saveDashboardCache(userId: number, attendance: Attendance, cachedAt = new Date().toISOString()): void {
  try {
    localStorage.setItem(cacheKey(userId), JSON.stringify({ attendance, cachedAt } satisfies DashboardCache));
  } catch {
    // Private browsing and quota limits must not make the authenticated dashboard fail.
  }
}

export function loadDashboardCache(userId: number): DashboardCache | null {
  try {
    const raw = localStorage.getItem(cacheKey(userId));
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || !("attendance" in parsed) || !("cachedAt" in parsed)) {
      return null;
    }
    const cache = parsed as DashboardCache;
    return typeof cache.cachedAt === "string" ? cache : null;
  } catch {
    return null;
  }
}

export function clearDashboardCache(userId: number): void {
  try {
    localStorage.removeItem(cacheKey(userId));
  } catch {
    // Cache cleanup is best effort.
  }
}
