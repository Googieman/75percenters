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
    constructor(public status: number, message: string, public retryAfterSeconds: number | null = null) {
      super(message);
    }
  },
}));

import App from "../src/App";
import { ApiError } from "../src/api";

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

const connectedOnDemand = {
  status: "connected",
  sync_mode: "on_demand",
  provider: "student_portal",
  netid_hint: "AB****4",
  last_authenticated_at: null,
  last_refreshed_at: null,
  last_successful_sync: null,
  active_job_id: null,
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((complete) => {
    resolve = complete;
  });
  return { promise, resolve };
}

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

  it("guides disconnected accounts to the connector without exposing portal credentials", async () => {
    apiMock.connection.mockResolvedValue({
      status: "disconnected",
      provider: null,
      netid_hint: null,
      last_authenticated_at: null,
      last_refreshed_at: null,
      last_successful_sync: null,
    });
    render(<App />);

    expect(await screen.findByText("Disconnected")).toBeInTheDocument();
    expect(screen.getByText(/open campusweb in the chrome connector/i)).toBeInTheDocument();
    expect(screen.getByTestId("generate-pairing")).toBeInTheDocument();
    expect(screen.queryByLabelText("CampusWeb password")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("CampusWeb NetID")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /connect securely/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /reconnect srm/i })).not.toBeInTheDocument();
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

  it("refreshes attendance once when the free-tier dashboard opens", async () => {
    apiMock.connection.mockResolvedValue(connectedOnDemand);
    apiMock.queueSync.mockResolvedValue({ job_id: 4, status: "succeeded" });
    render(<App />);

    await waitFor(() => expect(apiMock.queueSync).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("Attendance refreshed.")).toBeInTheDocument();
    expect(apiMock.syncJob).not.toHaveBeenCalled();
  });

  it("coalesces open and focus refreshes while a request is in flight", async () => {
    const pending = deferred<{ job_id: number; status: string }>();
    apiMock.connection.mockResolvedValue(connectedOnDemand);
    apiMock.queueSync.mockReturnValue(pending.promise);
    render(<App />);

    await waitFor(() => expect(apiMock.queueSync).toHaveBeenCalledTimes(1));
    window.dispatchEvent(new Event("focus"));
    await waitFor(() => expect(apiMock.queueSync).toHaveBeenCalledTimes(1));

    pending.resolve({ job_id: 9, status: "succeeded" });
  });

  it("does not poll a queued on-demand job when no worker is running", async () => {
    apiMock.connection.mockResolvedValue(connectedOnDemand);
    apiMock.queueSync.mockResolvedValue({ job_id: 9, status: "queued" });
    render(<App />);

    expect(await screen.findByText(/keep this app open/i)).toBeInTheDocument();
    expect(apiMock.syncJob).not.toHaveBeenCalled();
  });

  it("shows the server cooldown after an automatic refresh is rejected", async () => {
    apiMock.connection.mockResolvedValue(connectedOnDemand);
    apiMock.queueSync.mockRejectedValue(new ApiError(429, "a refresh was completed too recently", 17));
    render(<App />);

    expect(await screen.findByText(/refresh is on cooldown/i)).toBeInTheDocument();
  });

  it("shows reconnect state after a terminal reauthentication result", async () => {
    apiMock.connection.mockResolvedValueOnce(connectedOnDemand).mockResolvedValue({
      ...connectedOnDemand,
      status: "reauth_required",
    });
    apiMock.queueSync.mockResolvedValue({ job_id: 10, status: "reauth_required" });
    render(<App />);

    await waitFor(() => expect(apiMock.queueSync).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("Reconnect required")).toBeInTheDocument();
    expect(await screen.findByText(/reconnect required before attendance/i)).toBeInTheDocument();
    expect(screen.getByText(/open campusweb in the chrome connector/i)).toBeInTheDocument();
    expect(screen.getByTestId("generate-pairing")).toBeInTheDocument();
    expect(screen.queryByLabelText("CampusWeb password")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("CampusWeb NetID")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /connect securely/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /reconnect srm/i })).not.toBeInTheDocument();
  });

  it("does not show or persist attendance when the connection is unavailable", async () => {
    apiMock.attendance.mockRejectedValue(new Error("offline"));
    apiMock.connection.mockResolvedValue({
      status: "disconnected",
      provider: null,
      netid_hint: null,
      last_authenticated_at: null,
      last_refreshed_at: null,
      last_successful_sync: null,
    });
    render(<App />);

    expect((await screen.findAllByText("Connection unavailable. Reconnect to load attendance.")).length).toBeGreaterThan(0);
    expect(screen.queryByTestId("overall-percentage")).not.toBeInTheDocument();
    expect(localStorage.length).toBe(0);
  });

  it("does not render a hosted CampusWeb credential form", async () => {
    render(<App />);

    expect(await screen.findByText("Reconnect required")).toBeInTheDocument();
    expect(screen.queryByLabelText("CampusWeb password")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("CampusWeb NetID")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /connect securely/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /reconnect srm/i })).not.toBeInTheDocument();
  });
});
