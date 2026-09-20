export type Guidance = {
  current_percentage: number | null;
  additional_attended_hours: number;
  additional_absences_allowed: number;
  target_reachable: boolean;
};

export type User = { id: number; email: string; attendance_target: number };
export type AuthResponse = { user: User; csrf_token: string };
export type Subject = {
  id: number;
  code: string;
  subject: string;
  total_hours: number;
  attended_hours: number;
  absent_hours: number;
  source_percentage: number;
  guidance: Guidance;
};
export type Attendance = {
  attendance_target: number;
  subjects: Subject[];
  overall: Guidance;
  last_successful_sync: string | null;
};
export type HistoryItem = {
  id: number;
  recorded_at: string;
  total_hours: number;
  attended_hours: number;
  absent_hours: number;
  source_percentage: number;
  guidance: Guidance;
};
export type History = { items: HistoryItem[]; next_cursor: string | null };

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

let csrfToken: string | null = null;

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (csrfToken && init.method && init.method !== "GET") headers.set("X-CSRF-Token", csrfToken);
  const response = await fetch(path, { ...init, headers, credentials: "include" });
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // 204 responses have no body.
  }
  if (!response.ok) {
    const detail = typeof body === "object" && body && "detail" in body ? body.detail : "Request failed";
    throw new ApiError(response.status, String(detail));
  }
  if (typeof body === "object" && body && "csrf_token" in body) {
    csrfToken = String(body.csrf_token);
  }
  return body as T;
}

export const api = {
  login: (email: string, password: string) =>
    request<AuthResponse>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<AuthResponse>("/api/v1/auth/me"),
  logout: () => request<void>("/api/v1/auth/logout", { method: "POST" }),
  attendance: () => request<Attendance>("/api/v1/attendance"),
  createPairingCode: () => request<{ code: string; expires_at: string }>("/api/v1/pairing-codes", { method: "POST" }),
  history: (subjectId: number) => request<History>(`/api/v1/subjects/${subjectId}/history`),
};
