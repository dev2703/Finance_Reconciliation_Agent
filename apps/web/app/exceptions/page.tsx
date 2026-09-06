"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

type ExceptionItem = {
  status: string;
  confidence?: string;
  reason_codes?: string[];
  source_record_ids?: string[];
  target_record_ids?: string[];
};

type Run = {
  id: string;
  created_at: string;
  status: string;
  result_count: number;
  exception_count: number;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export default function ExceptionsPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [selectedRun, setSelectedRun] = useState<string>("");
  const [exceptions, setExceptions] = useState<ExceptionItem[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "unavailable">("loading");

  const load = useCallback(async () => {
    setState("loading");
    try {
      const response = await fetch(`${API_URL}/reconciliation/runs`, { cache: "no-store" });
      if (!response.ok) throw new Error("unavailable");
      const payload = (await response.json()) as { runs: Run[] };
      setRuns(payload.runs);
      const first = payload.runs[0]?.id ?? "";
      setSelectedRun(first);
      if (first) {
        const exceptionsResponse = await fetch(
          `${API_URL}/reconciliation/runs/${first}/exceptions`,
          { cache: "no-store" },
        );
        if (!exceptionsResponse.ok) throw new Error("unavailable");
        const exceptionsPayload = (await exceptionsResponse.json()) as {
          exceptions: ExceptionItem[];
        };
        setExceptions(exceptionsPayload.exceptions);
      } else {
        setExceptions([]);
      }
      setState("ready");
    } catch {
      setState("unavailable");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function onSelectRun(runId: string) {
    setSelectedRun(runId);
    if (!runId) {
      setExceptions([]);
      return;
    }
    const response = await fetch(`${API_URL}/reconciliation/runs/${runId}/exceptions`, {
      cache: "no-store",
    });
    if (!response.ok) return;
    const payload = (await response.json()) as { exceptions: ExceptionItem[] };
    setExceptions(payload.exceptions);
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Exceptions</p>
          <h1>Exception queue</h1>
        </div>
        <nav aria-label="Primary navigation">
          <Link href="/dashboard">Dashboard</Link>
          <Link href="/reconciliation">Reconciliation</Link>
          <Link href="/reviews">Reviews</Link>
          <Link href="/">Documents</Link>
        </nav>
      </header>

      {state === "unavailable" ? (
        <section className="notice" role="status">
          <span>Exception API is unavailable.</span>
          <button type="button" onClick={() => void load()}>
            Retry
          </button>
        </section>
      ) : null}

      <section className="panel">
        <label className="field">
          <span>Reconciliation run</span>
          <select
            value={selectedRun}
            onChange={(event) => void onSelectRun(event.target.value)}
            disabled={runs.length === 0}
          >
            {runs.length === 0 ? <option value="">No runs</option> : null}
            {runs.map((run) => (
              <option key={run.id} value={run.id}>
                {new Date(run.created_at).toLocaleString("en-AU")} · {run.exception_count}{" "}
                exceptions
              </option>
            ))}
          </select>
        </label>
      </section>

      {state === "ready" && exceptions.length === 0 ? (
        <section className="worklist">
          <div>
            <p className="eyebrow">Clear</p>
            <h2>No open exceptions for this run.</h2>
          </div>
          <Link className="primary-action" href="/reconciliation">
            Open workspace
          </Link>
        </section>
      ) : null}

      {exceptions.length > 0 ? (
        <section>
          <h2>Open exceptions</h2>
          <table>
            <thead>
              <tr>
                <th>Status</th>
                <th>Confidence</th>
                <th>Reason codes</th>
                <th>Sources</th>
                <th>Targets</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {exceptions.map((item, index) => (
                <tr key={`${item.status}-${index}`}>
                  <td>{item.status}</td>
                  <td>{item.confidence ?? "—"}</td>
                  <td>{(item.reason_codes ?? []).join(", ") || "—"}</td>
                  <td>{(item.source_record_ids ?? []).length}</td>
                  <td>{(item.target_record_ids ?? []).length}</td>
                  <td>
                    <Link href={`/investigation/${selectedRun}?index=${index}`}>Investigate</Link>
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
