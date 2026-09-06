"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

type DashboardMetrics = {
  transactions_processed: number;
  reconciled_count: number;
  reconciliation_rate: number;
  exception_count: number;
  amount_at_risk: string;
  pending_reviews: number;
  automation_rate: number;
  updated_at?: string;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

const emptyMetrics: DashboardMetrics = {
  transactions_processed: 0,
  reconciled_count: 0,
  reconciliation_rate: 0,
  exception_count: 0,
  amount_at_risk: "0.00",
  pending_reviews: 0,
  automation_rate: 0,
};

function number(value: number) {
  return new Intl.NumberFormat("en-AU").format(value);
}

function percent(value: number) {
  return new Intl.NumberFormat("en-AU", { style: "percent", maximumFractionDigits: 1 }).format(value / 100);
}

function money(value: string) {
  return new Intl.NumberFormat("en-AU", { style: "currency", currency: "AUD" }).format(Number(value));
}

export default function DashboardPage() {
  const [metrics, setMetrics] = useState<DashboardMetrics>(emptyMetrics);
  const [state, setState] = useState<"loading" | "ready" | "unavailable">("loading");

  const loadMetrics = useCallback(async () => {
    setState("loading");
    try {
      const response = await fetch(`${API_URL}/dashboard/metrics`, { cache: "no-store" });
      if (!response.ok) throw new Error("Dashboard metrics are not available");
      const payload = (await response.json()) as Partial<DashboardMetrics>;
      setMetrics({ ...emptyMetrics, ...payload });
      setState("ready");
    } catch {
      // The dashboard is deployable before its API route: show an honest empty state.
      setMetrics(emptyMetrics);
      setState("unavailable");
    }
  }, []);

  useEffect(() => {
    void loadMetrics();
  }, [loadMetrics]);

  const cards = [
    { label: "Transactions processed", value: number(metrics.transactions_processed), detail: "Imported records", tone: "neutral" },
    { label: "Reconciled", value: percent(metrics.reconciliation_rate), detail: `${number(metrics.reconciled_count)} records matched`, tone: "positive" },
    { label: "Exceptions", value: number(metrics.exception_count), detail: "Need investigation", tone: "warning" },
    { label: "Amount at risk", value: money(metrics.amount_at_risk), detail: "Unresolved financial exposure", tone: "critical" },
    { label: "Pending reviews", value: number(metrics.pending_reviews), detail: "Awaiting a decision", tone: "warning" },
    { label: "Automation rate", value: percent(metrics.automation_rate), detail: "Resolved without review", tone: "positive" },
  ];

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Finance operations</p>
          <h1>Reconciliation overview</h1>
        </div>
        <nav aria-label="Primary navigation">
          <Link href="/dashboard" aria-current="page">Dashboard</Link>
          <Link href="/">Documents</Link>
          <Link href="/reconciliation">Reconciliation</Link>
        </nav>
      </header>

      {state === "unavailable" ? (
        <section className="notice" role="status">
          <div><strong>Dashboard data is not connected yet.</strong> Uploads remain available while the reconciliation API is being integrated.</div>
          <button type="button" onClick={() => void loadMetrics()}>Retry</button>
        </section>
      ) : null}

      <section className="metrics" aria-label="Reconciliation metrics" aria-busy={state === "loading"}>
        {cards.map((card) => (
          <article className={`metric-card ${card.tone}`} key={card.label}>
            <p>{card.label}</p>
            <strong>{state === "loading" ? "—" : card.value}</strong>
            <span>{card.detail}</span>
          </article>
        ))}
      </section>

      <section className="worklist">
        <div>
          <p className="eyebrow">Workflow</p>
          <h2>Start with a source document</h2>
          <p>Upload a bank, ledger, invoice, payment, or settlement file. Parsed records are reviewed before import.</p>
        </div>
        <Link className="primary-action" href="/">Upload a document</Link>
      </section>

      <section className="dashboard-grid" aria-label="Operational insight">
        <article className="insight-card">
          <p className="eyebrow">Close health</p>
          <h2>Reconciliation coverage</h2>
          <div className="progress-row">
            <span>Matched records</span>
            <div className="progress-track"><i style={{ width: `${Math.min(100, metrics.reconciliation_rate)}%` }} /></div>
            <b>{state === "loading" ? "—" : percent(metrics.reconciliation_rate)}</b>
          </div>
          <div className="progress-row">
            <span>Automation</span>
            <div className="progress-track"><i style={{ width: `${Math.min(100, metrics.automation_rate)}%` }} /></div>
            <b>{state === "loading" ? "—" : percent(metrics.automation_rate)}</b>
          </div>
          <div className="mini-legend" aria-label="Status legend">
            <span><i className="dot-mint" />cleared automatically</span>
            <span><i className="dot-blue" />matched with evidence</span>
            <span><i className="dot-amber" />requires review</span>
          </div>
        </article>
        <aside className="run-card">
          <p className="eyebrow">Today&apos;s focus</p>
          <h2>Work requiring attention</h2>
          <div className="run-list">
            <div><span><i className="status-dot risk" />Financial exposure</span><strong>{state === "loading" ? "—" : money(metrics.amount_at_risk)}</strong></div>
            <div><span><i className="status-dot watch" />Awaiting reviewer</span><strong>{state === "loading" ? "—" : number(metrics.pending_reviews)}</strong></div>
            <div><span><i className="status-dot good" />Records reconciled</span><strong>{state === "loading" ? "—" : number(metrics.reconciled_count)}</strong></div>
          </div>
        </aside>
      </section>

      {metrics.updated_at ? <p className="updated">Updated {new Date(metrics.updated_at).toLocaleString("en-AU")}</p> : null}
    </main>
  );
}
