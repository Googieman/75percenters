import { FormEvent, useEffect, useState } from "react";

import { api, ApiError, Attendance, Connection, History, User } from "./api";
import { formatGuidance, formatPercentage, formatSyncTime } from "./format";
import { loadDashboardCache, saveDashboardCache } from "./offline";
import { requestAndRegisterPush } from "./push";
import "./styles.css";

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
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
      setBusy(false);
    }
  }

  return (
    <main className="shell narrow">
      <section className="panel">
        <p className="eyebrow">SRM Attendance Tracker</p>
        <h1>Sign in to your dashboard</h1>
        <p className="muted">SRM authentication is completed through the hosted connection flow. This app never stores your SRM password.</p>
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
  const cached = loadDashboardCache(user.id);
  const [attendance, setAttendance] = useState<Attendance | null>(cached?.attendance ?? null);
  const [cachedAt, setCachedAt] = useState<string | null>(cached?.cachedAt ?? null);
  const [offline, setOffline] = useState(Boolean(cached));
  const [connection, setConnection] = useState<Connection | null>(null);
  const [pairingCode, setPairingCode] = useState<string | null>(null);
  const [history, setHistory] = useState<Record<number, History>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [target, setTarget] = useState(String(user.attendance_target));

  useEffect(() => {
    let active = true;
    Promise.allSettled([api.attendance(), api.connection()]).then(([attendanceResult, connectionResult]) => {
      if (!active) return;
      if (attendanceResult.status === "fulfilled") {
        const fetched = attendanceResult.value;
        setAttendance(fetched);
        setCachedAt(fetched.last_successful_sync ?? new Date().toISOString());
        setOffline(false);
        saveDashboardCache(user.id, fetched, fetched.last_successful_sync ?? undefined);
      } else if (attendanceResult.reason instanceof ApiError && attendanceResult.reason.status === 401) {
        onLogout();
      } else if (!cached) {
        setMessage("Unable to load attendance. Try again when the connection is available.");
      }
      if (connectionResult.status === "fulfilled") setConnection(connectionResult.value);
    });
    return () => { active = false; };
  }, [onLogout, user.id]);

  async function refresh() {
    setBusy(true);
    setMessage(null);
    try {
      await api.queueSync();
      setConnection((current) => current ? { ...current, status: "refreshing" } : current);
      setMessage("Refresh queued. The hosted worker will update attendance in the background.");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Unable to queue refresh.");
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    setBusy(true);
    try {
      await api.disconnectSrm();
      setConnection((current) => current ? { ...current, status: "disconnected" } : current);
      setMessage("SRM disconnected. Your attendance history is still available.");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Unable to disconnect SRM.");
    } finally {
      setBusy(false);
    }
  }

  function reconnect() {
    setMessage("Reconnect is required, but no verified hosted provider is enabled yet. No SRM password has been stored.");
  }

  async function enableNotifications() {
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
      const response = await api.updateSettings(value);
      setAttendance((current) => current ? { ...current, attendance_target: response.attendance_target } : current);
      setMessage("Attendance target saved.");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Unable to save target.");
    }
  }

  async function logout() {
    try { await api.logout(); } finally { onLogout(); }
  }

  const connectionLabel = connection?.status === "connected"
    ? "Connected"
    : connection?.status === "refreshing"
      ? "Refreshing"
      : connection?.status === "reauth_required"
        ? "Reconnect required"
        : connection?.status === "paused"
          ? "Source changed"
          : "Temporarily unavailable";

  return (
    <main className="shell">
      <header className="topbar">
        <div><p className="eyebrow">SRM Attendance Tracker</p><h1>Welcome back</h1><p className="muted">{user.email}</p></div>
        <button className="secondary" onClick={logout}>Sign out</button>
      </header>
      {offline && cachedAt && <p className="notice" role="status">Saved data from {formatSyncTime(cachedAt)}. You are viewing cached attendance.</p>}
      {message && <p className="notice" role="status">{message}</p>}
      <section className="connection-panel panel" aria-label="SRM connection">
        <div>
          <p className="eyebrow">SRM connection</p>
          <h2>{connectionLabel}</h2>
          <p className="muted">{connection?.netid_hint ? `Linked account ${connection.netid_hint}. ` : ""}Attendance refresh runs on the hosted worker; this PWA does not read an SRM tab.</p>
        </div>
        <div className="button-row">
          {connection?.status === "connected" && <button onClick={() => void refresh()} disabled={busy}>Refresh now</button>}
          {connection?.status !== "connected" && <button onClick={reconnect}>Reconnect SRM</button>}
          {connection?.status === "connected" && <button className="secondary" onClick={() => void disconnect()} disabled={busy}>Disconnect SRM</button>}
          <button className="secondary" onClick={() => void enableNotifications()}>Enable notifications</button>
        </div>
      </section>
      <section className="toolbar panel">
        <div><strong>Attendance target</strong><p className="muted">Guidance uses this target without changing stored history.</p></div>
        <form className="inline-form" onSubmit={saveTarget}><label htmlFor="target">Target %</label><input id="target" type="number" min="1" max="100" step="0.01" value={target} onChange={(event) => setTarget(event.target.value)} /><button>Save</button></form>
      </section>
      <section className="toolbar panel">
        <div><strong>Optional legacy Chrome connector</strong><p className="muted">Use only if hosted acquisition is unavailable; it still requires a normal authenticated Chrome session.</p></div>
        <button onClick={() => void generatePairingCode()} data-testid="generate-pairing">Generate pairing code</button>
        {pairingCode && <code data-testid="pairing-code" className="pairing-code">{pairingCode}</code>}
      </section>
      {!attendance ? <section className="panel"><p>Loading attendance…</p></section> : <>
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
