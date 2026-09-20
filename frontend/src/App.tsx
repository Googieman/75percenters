import { FormEvent, useEffect, useState } from "react";

import { api, ApiError, Attendance, History, User } from "./api";
import { formatGuidance, formatPercentage, formatSyncTime } from "./format";
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
        <p className="muted">The connector uses your normal signed-in Chrome tab. It never needs your SRM password.</p>
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
  const [pairingCode, setPairingCode] = useState<string | null>(null);
  const [history, setHistory] = useState<Record<number, History>>({});
  const [message, setMessage] = useState<string | null>(null);

  async function refresh() {
    try {
      setAttendance(await api.attendance());
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 401) onLogout();
      else setMessage(reason instanceof Error ? reason.message : "Unable to load attendance.");
    }
  }

  useEffect(() => { void refresh(); }, []);

  async function generatePairingCode() {
    try {
      setPairingCode((await api.createPairingCode()).code);
      setMessage("Copy this code into the Chrome connector popup.");
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

  async function logout() {
    try { await api.logout(); } finally { onLogout(); }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div><p className="eyebrow">SRM Attendance Tracker</p><h1>Welcome back</h1><p className="muted">{user.email}</p></div>
        <button className="secondary" onClick={logout}>Sign out</button>
      </header>
      {message && <p className="notice" role="status">{message}</p>}
      <section className="toolbar panel">
        <div><strong>Connector</strong><p className="muted">Pair Chrome, then sync only when you choose.</p></div>
        <button onClick={generatePairingCode} data-testid="generate-pairing">Generate pairing code</button>
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
