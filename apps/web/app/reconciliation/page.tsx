"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

type Run = {
  id: string;
  created_at: string;
  status: string;
  result_count: number;
  exception_count: number;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export default function ReconciliationPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "unavailable">("loading");
  const [message, setMessage] = useState<string | null>(null);
  const [seeding, setSeeding] = useState(false);

  const load = useCallback(async () => {
    setState("loading");
    try {
      const response = await fetch(`${API_URL}/reconciliation/runs`, { cache: "no-store" });
      if (!response.ok) throw new Error("Runs are unavailable");
      setRuns((await response.json()).runs as Run[]);
      setState("ready");
    } catch {
      setState("unavailable");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function seedDemo() {
    setSeeding(true);
    setMessage(null);
    try {
      const response = await fetch(`${API_URL}/demo/seed-and-run`, { method: "POST" });
      if (!response.ok) throw new Error("Demo seed failed");
      const payload = await response.json();
      setMessage(
        `Demo run ${payload.run.id.slice(0, 8)} · matched ${payload.matched_count} · exceptions ${payload.exception_count}`,
      );
      await load();
    } catch {
      setMessage("Could not seed the demo reconciliation run.");
    } finally {
      setSeeding(false);
    }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Reconciliation</p>
          <h1>Run workspace</h1>
        </div>
        <nav aria-label="Primary navigation">
          <Link href="/dashboard">Dashboard</Link>
          <Link href="/exceptions">Exceptions</Link>
          <Link href="/reviews">Reviews</Link>
          <Link href="/">Documents</Link>
        </nav>
      </header>

      {message ? (
        <section className="notice" role="status">
          <span>{message}</span>
        </section>
      ) : null}

      {state === "unavailable" ? (
        <section className="notice" role="status">
          <span>Reconciliation API is unavailable.</span>
          <button type="button" onClick={() => void load()}>
            Retry
          </button>
        </section>
      ) : null}

      <section className="worklist">
        <div>
          <p className="eyebrow">Demo orchestration</p>
          <h2>Seed the 40-case pack and run reconciliation.</h2>
          <p>Creates a persisted run, exception queue entries, and an optional review.</p>
        </div>
        <button className="primary-action" type="button" disabled={seeding} onClick={() => void seedDemo()}>
          {seeding ? "Seeding…" : "Seed demo & reconcile"}
        </button>
      </section>

      {state === "ready" && runs.length === 0 ? (
        <section className="panel">
          <p className="eyebrow">No runs yet</p>
          <h2>Import records, then create a reconciliation run.</h2>
          <Link className="primary-action" href="/">
            Upload a document
          </Link>
        </section>
      ) : null}

      {runs.length > 0 ? (
        <section>
          <h2>Recent runs</h2>
          <table>
            <thead>
              <tr>
                <th>Created</th>
                <th>Status</th>
                <th>Results</th>
                <th>Exceptions</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id}>
                  <td>{new Date(run.created_at).toLocaleString("en-AU")}</td>
                  <td>{run.status}</td>
                  <td>{run.result_count}</td>
                  <td>{run.exception_count}</td>
                  <td>
                    <Link href={`/exceptions`}>Queue</Link> ·{" "}
                    <Link href={`/investigation/${run.id}`}>Investigate</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}
    </main>
  );
}
