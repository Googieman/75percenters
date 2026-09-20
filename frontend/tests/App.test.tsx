import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const apiMock = vi.hoisted(() => ({
  me: vi.fn(),
  attendance: vi.fn(),
  connection: vi.fn(),
  queueSync: vi.fn(),
  syncJob: vi.fn(),
  logout: vi.fn(),
  createPairingCode: vi.fn(),
  history: vi.fn(),
  updateSettings: vi.fn(),
  disconnectSrm: vi.fn(),
  registerPush: vi.fn(),
}));

vi.mock("../src/api", () => ({
  api: apiMock,
  ApiError: class ApiError extends Error {
    constructor(public status: number, message: string) {
      super(message);
    }
  },
}));

import App from "../src/App";

const user = { id: 7, email: "owner@example.com", attendance_target: 75 };
const attendance = {
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

describe("phone-first dashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    apiMock.me.mockResolvedValue({ user, csrf_token: "csrf" });
    apiMock.attendance.mockResolvedValue(attendance);
    apiMock.connection.mockResolvedValue({
      status: "reauth_required",
      provider: "student_portal",
      netid_hint: "AB****4",
      last_authenticated_at: null,
      last_refreshed_at: null,
      last_successful_sync: null,
    });
  });

  it("shows reconnect required without exposing portal credentials", async () => {
    render(<App />);

    expect(await screen.findByText("Reconnect required")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reconnect srm/i })).toBeInTheDocument();
    expect(screen.queryByLabelText(/srm password/i)).not.toBeInTheDocument();
  });

  it("queues a hosted refresh from an explicit phone action", async () => {
    apiMock.connection.mockResolvedValue({
      status: "connected",
      provider: "student_portal",
      netid_hint: "AB****4",
      last_authenticated_at: null,
      last_refreshed_at: null,
      last_successful_sync: null,
    });
    apiMock.queueSync.mockResolvedValue({ job_id: 4, status: "queued" });
    render(<App />);

    const button = await screen.findByRole("button", { name: /refresh now/i });
    button.click();

    await waitFor(() => expect(apiMock.queueSync).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/refresh queued/i)).toBeInTheDocument();
  });
});
