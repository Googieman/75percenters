import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError, Attendance, Connection, History, User } from "./api";
import { formatGuidance, formatPercentage, formatSyncTime } from "./format";
import { clearLegacyAttendanceStorage } from "./legacy-cache-cleanup";
import { requestAndRegisterPush } from "./push";
import "./styles.css";

const UNAVAILABLE_MESSAGE = "Connection unavailable. Reconnect to load attendance.";
const DEFAULT_REFRESH_COOLDOWN_SECONDS = 300;

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    clearLegacyAttendanceStorage();
    api.me()
      .then((response) => setUser(response.user))
      .catch((reason: unknown) => {
        if (!(reason instanceof ApiError && reason.status === 401)) setError("Unable to contact the tracker.");
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <main className="shell"><p>Loading…</p></main>;
  if (!user) return <Login onLogin={setUser} error={error} />;
  return <Dashboard user={user} onLogout={() => setUser(null)} />;
}

function Login({ onLogin, error }: { onLogin: (user: User) => void; error: string | null }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState(error);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const response = await api.login(email, password);
      onLogin(response.user);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Sign-in failed.");
    } finally {
      setPassword("");
      setBusy(false);
    }
  }

  return (
    <main className="shell narrow">
      <section className="panel">
        <p className="eyebrow">SRM Attendance Tracker</p>
        <h1>Sign in to your dashboard</h1>
        <p className="muted">SRM credentials are used only during an explicit CampusWeb connection. The tracker never stores this password.</p>
        <form onSubmit={submit} className="stack">
          <label>Email<input data-testid="email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
          <label>Password<input data-testid="password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
          <button data-testid="login-button" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        </form>
        {message && <p className="error" data-testid="login-error">{message}</p>}
      </section>
    </main>
  );
}

function Dashboard({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [attendance, setAttendance] = useState<Attendance | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [connection, setConnection] = useState<Connection | null>(null);
  const [activeJobId, setActiveJobId] = useState<number | null>(null);
  const [pairingCode, setPairingCode] = useState<string | null>(null);
  const [history, setHistory] = useState<Record<number, History>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showReconnect, setShowReconnect] = useState(false);
  const [netid, setNetid] = useState("");
  const [srmPassword, setSrmPassword] = useState("");
  const [target, setTarget] = useState(String(user.attendance_target));
  const loadDataInFlight = useRef<Promise<void> | null>(null);
  const refreshInFlight = useRef<Promise<void> | null>(null);
  const automaticRefreshCooldownUntil = useRef(0);
  const initialRefreshStarted = useRef(false);
  const lastReturnRefreshTrigger = useRef(0);
  const [returnRefreshTrigger, setReturnRefreshTrigger] = useState(0);

  const loadData = useCallback(async () => {
    if (loadDataInFlight.current) {
      await loadDataInFlight.current;
      return;
    }
    const request = (async () => {
      const [attendanceResult, connectionResult] = await Promise.allSettled([api.attendance(), api.connection()]);
      if (attendanceResult.status === "fulfilled") {
        setAttendance(attendanceResult.value);
        setUnavailable(false);
      } else if (attendanceResult.reason instanceof ApiError && attendanceResult.reason.status === 401) {
        onLogout();
        return;
      } else {
        setAttendance(null);
        setUnavailable(true);
        setMessage(UNAVAILABLE_MESSAGE);
      }
      if (connectionResult.status === "fulfilled") {
        setConnection(connectionResult.value);
        setActiveJobId(connectionResult.value.active_job_id ?? null);
      }
    })();
    loadDataInFlight.current = request;
    try {
      await request;
    } finally {
      if (loadDataInFlight.current === request) loadDataInFlight.current = null;
    }
  }, [onLogout]);

  const refresh = useCallback(async (automatic = false) => {
    if (refreshInFlight.current) {
      await refreshInFlight.current;
      return;
    }
    if (automatic && Date.now() < automaticRefreshCooldownUntil.current) {
      const remaining = Math.ceil((automaticRefreshCooldownUntil.current - Date.now()) / 1000);
      setMessage(`Refresh is on cooldown. Try again in ${remaining} seconds.`);
      return;
    }

    const request = (async () => {
      setBusy(true);
      setMessage(null);
      try {
        const job = await api.queueSync();
        if (job.status === "succeeded") {
          setActiveJobId(null);
          setMessage("Attendance refreshed.");
          await loadData();
          return;
        }
        if (["reauth_required", "paused", "failed", "canceled"].includes(job.status)) {
          setActiveJobId(null);
          setMessage(
            job.status === "reauth_required"
              ? "Reconnect required before attendance can refresh."
              : "Attendance refresh could not complete.",
          );
          await loadData();
          return;
        }
        if (connection?.sync_mode === "on_demand") {
          setActiveJobId(null);
          setMessage("Refresh is still queued. Keep this app open and retry if attendance does not update.");
          return;
        }
        setActiveJobId(job.job_id);
        setConnection((current) => current ? { ...current, status: "refreshing", active_job_id: job.job_id } : current);
        setMessage("Refresh queued. The hosted worker will update attendance in the background.");
      } catch (reason) {
        if (reason instanceof ApiError && reason.status === 429) {
          const retryAfter = reason.retryAfterSeconds ?? DEFAULT_REFRESH_COOLDOWN_SECONDS;
          automaticRefreshCooldownUntil.current = Date.now() + retryAfter * 1000;
          setMessage(`Refresh is on cooldown. Try again in ${retryAfter} seconds.`);
        } else if (reason instanceof ApiError && reason.status === 409) {
          setMessage("Reconnect required before refreshing attendance.");
        } else {
          setMessage(reason instanceof Error ? reason.message : "Unable to queue refresh.");
        }
      } finally {
        setBusy(false);
      }
    })();
    refreshInFlight.current = request;
    try {
      await request;
    } finally {
      if (refreshInFlight.current === request) refreshInFlight.current = null;
    }
  }, [connection?.sync_mode, loadData]);

  useEffect(() => {
    clearLegacyAttendanceStorage();
    void loadData();
    if (new URLSearchParams(window.location.search).get("reconnect") === "1") setShowReconnect(true);
    const retry = () => {
      void loadData().then(() => setReturnRefreshTrigger((current) => current + 1));
    };
    window.addEventListener("online", retry);
    window.addEventListener("focus", retry);
    return () => {
      window.removeEventListener("online", retry);
      window.removeEventListener("focus", retry);
    };
  }, [loadData]);

  useEffect(() => {
    if (connection?.status !== "connected" || connection.sync_mode !== "on_demand") return;
    const initialRefresh = returnRefreshTrigger === 0 && !initialRefreshStarted.current;
    const returnRefresh = returnRefreshTrigger > lastReturnRefreshTrigger.current;
    if (!initialRefresh && !returnRefresh) return;
    initialRefreshStarted.current = true;
    if (returnRefresh) lastReturnRefreshTrigger.current = returnRefreshTrigger;
    void refresh(true);
  }, [connection?.status, connection?.sync_mode, refresh, returnRefreshTrigger]);

  useEffect(() => {
    if (activeJobId === null || connection?.sync_mode === "on_demand") return;
    let active = true;
    const poll = async () => {
      try {
        const job = await api.syncJob(activeJobId);
        if (!active) return;
        if (job.status === "succeeded") {
          setActiveJobId(null);
          setMessage("Attendance refreshed.");
          await loadData();
        } else if (["reauth_required", "paused", "failed", "canceled"].includes(job.status)) {
          setActiveJobId(null);
          await loadData();
        }
      } catch (reason) {
        if (active && reason instanceof ApiError && reason.status === 401) onLogout();
      }
    };
    const timer = window.setInterval(() => void poll(), 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [activeJobId, connection?.sync_mode, loadData, onLogout]);

  async function reconnect(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const attempt = await api.startAuth(netid);
      await api.completeAuth(attempt.attempt_id, srmPassword);
      setShowReconnect(false);
      setNetid("");
      setMessage("CampusWeb connected. Your first refresh is queued.");
      await loadData();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Unable to connect CampusWeb.");
    } finally {
      setSrmPassword("");
      setBusy(false);
    }
  }

  async function disconnect() {
    setBusy(true);
    try {
      await api.disconnectSrm();
      setConnection((current) => current ? { ...current, status: "disconnected", active_job_id: null } : current);
      setActiveJobId(null);
      setAttendance(null);
      setUnavailable(true);
      setMessage(UNAVAILABLE_MESSAGE);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Unable to disconnect SRM.");
    } finally {
      setBusy(false);
    }
  }

  async function enableNotifications() {
    if (!connection?.notifications_available) {
      setMessage("Notifications are not configured on this deployment yet.");
      return;
    }
    try {
      const result = await requestAndRegisterPush(import.meta.env.VITE_WEB_PUSH_PUBLIC_KEY);
      setMessage(
        result === "registered"
          ? "Notifications enabled for this device."
          : result === "unconfigured"
            ? "Notifications are not configured on this deployment yet."
            : result === "unsupported"
              ? "This browser does not support push notifications."
              : "Notifications remain disabled.",
      );
      if (result === "registered") {
        setConnection((current) => current ? { ...current, notifications_available: true } : current);
      }
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Unable to enable notifications.");
    }
  }

  async function generatePairingCode() {
    try {
      setPairingCode((await api.createPairingCode()).code);
      setMessage("Copy this code into the optional legacy Chrome connector popup.");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Unable to create a pairing code.");
    }
  }

  async function showHistory(subjectId: number) {
    try {
      const loaded = await api.history(subjectId);
      setHistory((current) => ({ ...current, [subjectId]: loaded }));
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Unable to load history.");
    }
  }

  async function saveTarget(event: FormEvent) {
    event.preventDefault();
    const value = Number(target);
    if (!Number.isFinite(value) || value <= 0 || value > 100) {
      setMessage("Attendance target must be between 1 and 100.");
      return;
    }
    try {
      await api.updateSettings(value);
      const refreshed = await api.attendance();
      setAttendance(refreshed);
      setMessage("Attendance target saved.");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Unable to save target.");
    }
  }

  async function logout() {
    try { await api.logout(); } finally { clearLegacyAttendanceStorage(); onLogout(); }
  }

  const connectionLabel = unavailable
    ? "Temporarily unavailable"
    : activeJobId !== null || connection?.status === "refreshing"
      ? "Refreshing"
      : connection?.status === "connected"
        ? "Connected"
        : connection?.status === "authenticating"
          ? "Connecting"
        : connection?.status === "reauth_required"
          ? "Reconnect required"
          : connection?.status === "paused"
            ? "Source changed"
            : connection?.status === "disconnected"
              ? "Disconnected"
              : "Temporarily unavailable";

  return (
    <main className="shell">
      <header className="topbar">
        <div><p className="eyebrow">SRM Attendance Tracker</p><h1>Welcome back</h1><p className="muted">{user.email}</p></div>
        <button className="secondary" onClick={() => void logout()}>Sign out</button>
      </header>
      {message && <p className="notice" role="status">{message}</p>}
      <section className="connection-panel panel" aria-label="SRM connection">
        <div>
          <p className="eyebrow">SRM connection</p>
          <h2>{connectionLabel}</h2>
          <p className="muted">{connection?.netid_hint ? `Linked account ${connection.netid_hint}. ` : ""}{connection?.sync_mode === "on_demand" ? "Attendance refresh runs when this app opens; keep it open while the refresh completes." : "Attendance refresh runs on the hosted worker; this PWA does not read an SRM tab."}</p>
        </div>
        <div className="button-row">
          {unavailable && <button className="secondary" onClick={() => void loadData()}>Retry connection</button>}
          {connection?.status === "connected" && <button onClick={() => void refresh()} disabled={busy}>Refresh now</button>}
          {connection?.status !== "connected" && <button onClick={() => setShowReconnect(true)}>Reconnect SRM</button>}
          {connection?.status === "connected" && <button className="secondary" onClick={() => void disconnect()} disabled={busy}>Disconnect SRM</button>}
          <button className="secondary" onClick={() => void enableNotifications()} disabled={!connection?.notifications_available}>Enable notifications</button>
        </div>
      </section>
      {showReconnect && <section className="panel" aria-label="CampusWeb connection form">
        <h2>Connect to CampusWeb</h2>
        <p className="muted">Your credentials are forwarded to CampusWeb only for this request. The tracker does not retain your password.</p>
        <form className="stack" onSubmit={(event) => void reconnect(event)}>
          <label>CampusWeb NetID<input value={netid} onChange={(event) => setNetid(event.target.value)} autoComplete="username" required /></label>
          <label>CampusWeb password<input aria-label="CampusWeb password" type="password" value={srmPassword} onChange={(event) => setSrmPassword(event.target.value)} autoComplete="current-password" required /></label>
          <button disabled={busy}>{busy ? "Connecting…" : "Connect securely"}</button>
        </form>
      </section>}
      <section className="toolbar panel">
        <div><strong>Attendance target</strong><p className="muted">Guidance uses this target without changing stored history.</p></div>
        <form className="inline-form" onSubmit={(event) => void saveTarget(event)}><label htmlFor="target">Target %</label><input id="target" type="number" min="1" max="100" step="0.01" value={target} onChange={(event) => setTarget(event.target.value)} /><button>Save</button></form>
      </section>
      <section className="toolbar panel">
        <div><strong>Optional legacy Chrome connector</strong><p className="muted">Use only if hosted acquisition is unavailable; it still requires a normal authenticated Chrome session.</p></div>
        <button onClick={() => void generatePairingCode()} data-testid="generate-pairing">Generate pairing code</button>
        {pairingCode && <code data-testid="pairing-code" className="pairing-code">{pairingCode}</code>}
      </section>
      {unavailable ? <section className="panel" role="alert"><h2>{UNAVAILABLE_MESSAGE}</h2><p className="muted">Attendance is intentionally not available offline.</p></section> : !attendance ? <section className="panel"><p>Loading attendance…</p></section> : <>
        <section className="summary-grid">
          <article className="panel"><span className="muted">Overall attendance</span><strong className="metric" data-testid="overall-percentage">{formatPercentage(attendance.overall.current_percentage)}</strong><span>Target {attendance.attendance_target}%</span></article>
          <article className="panel"><span className="muted">Last successful sync</span><strong data-testid="last-sync">{formatSyncTime(attendance.last_successful_sync)}</strong></article>
          <article className="panel"><span className="muted">Subjects</span><strong className="metric">{attendance.subjects.length}</strong></article>
        </section>
        <section className="subject-grid" aria-label="Subjects">
          {attendance.subjects.map((subject) => <article className="panel subject" key={subject.id} data-testid={`subject-${subject.code}`}>
            <div><span className="eyebrow">{subject.code}</span><h2>{subject.subject}</h2></div>
            <strong className="metric">{subject.attended_hours}/{subject.total_hours}</strong>
            <p>{formatPercentage(subject.source_percentage)} · {subject.absent_hours} absent</p>
            <p className={subject.guidance.target_reachable ? "success" : "error"}>{formatGuidance(subject.guidance)}</p>
            <button className="secondary" onClick={() => void showHistory(subject.id)} data-testid={`history-button-${subject.code}`}>View history</button>
            {history[subject.id] && <div data-testid={`history-${subject.code}`} className="history"><strong>History</strong>{history[subject.id].items.map((item) => <div key={item.id}>{item.attended_hours}/{item.total_hours} · {formatSyncTime(item.recorded_at)}</div>)}</div>}
          </article>)}
        </section>
      </>}
    </main>
  );
}
