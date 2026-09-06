"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

type Trace = {
  id: string;
  reconciliation_run_id: string;
  created_at: string;
  telemetry: { model: string; prompt_tokens: number; completion_tokens: number; latency_ms: number; retry_count: number };
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export default function TracesPage() {
  const [traces, setTraces] = useState<Trace[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    fetch(`${API_URL}/agent-traces`, { cache: "no-store" })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error("Unavailable")))
      .then((payload) => setTraces(payload.traces as Trace[]))
      .catch(() => setError("Agent traces are unavailable."));
  }, []);
  return <main className="shell">
    <header className="topbar"><div><p className="eyebrow">Observability</p><h1>Agent traces</h1></div><nav><Link href="/reports">Reports</Link><Link href="/reconciliation">Runs</Link></nav></header>
    {error ? <section className="notice">{error}</section> : null}
    {traces.length === 0 && !error ? <section className="panel"><h2>No model calls yet</h2><p>Traces appear after an unresolved run is investigated.</p></section> : null}
    {traces.length ? <table><thead><tr><th>Run</th><th>Model</th><th>Tokens</th><th>Latency</th><th>Retries</th></tr></thead><tbody>{traces.map((trace) => <tr key={trace.id}><td>{trace.reconciliation_run_id}</td><td>{trace.telemetry.model}</td><td>{trace.telemetry.prompt_tokens + trace.telemetry.completion_tokens}</td><td>{trace.telemetry.latency_ms} ms</td><td>{trace.telemetry.retry_count}</td></tr>)}</tbody></table> : null}
  </main>;
}
