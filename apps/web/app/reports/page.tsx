"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

type Reports = {
  reconciliation: {
    item_count: number;
    matched_count: number;
    reconciliation_rate: string;
    run_count: number;
  };
  exceptions: { exception_count: number };
  audit: { event_count: number; event_types: string[] };
  automation: {
    automated_count: number;
    automation_rate: string;
    pending_reviews: number;
  };
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export default function ReportsPage() {
  const [reports, setReports] = useState<Reports | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "unavailable">("loading");

  const load = useCallback(async () => {
    setState("loading");
    try {
      const response = await fetch(`${API_URL}/reports/operational`, { cache: "no-store" });
      if (!response.ok) throw new Error("unavailable");
      setReports((await response.json()) as Reports);
      setState("ready");
    } catch {
      setState("unavailable");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Reporting</p>
          <h1>Operational reports</h1>
        </div>
        <nav aria-label="Primary navigation">
          <Link href="/dashboard">Dashboard</Link>
          <Link href="/reconciliation">Reconciliation</Link>
          <Link href="/reviews">Reviews</Link>
          <Link href="/traces">Agent traces</Link>
        </nav>
      </header>

      {state === "unavailable" ? (
        <section className="notice" role="status">
          <span>Reports API is unavailable.</span>
          <button type="button" onClick={() => void load()}>
            Retry
          </button>
        </section>
      ) : null}

      {reports ? (
        <section className="metrics">
          <article className="metric-card positive">
            <span>Reconciliation rate</span>
            <strong>{Number(reports.reconciliation.reconciliation_rate).toLocaleString("en-AU", { style: "percent" })}</strong>
            <p>
              {reports.reconciliation.matched_count} / {reports.reconciliation.item_count} across{" "}
              {reports.reconciliation.run_count} runs
            </p>
          </article>
          <article className="metric-card warning">
            <span>Exceptions</span>
            <strong>{reports.exceptions.exception_count}</strong>
            <p>Unresolved match outcomes</p>
          </article>
          <article className="metric-card">
            <span>Audit events</span>
            <strong>{reports.audit.event_count}</strong>
            <p>{reports.audit.event_types.slice(0, 4).join(", ") || "No events yet"}</p>
          </article>
          <article className="metric-card positive">
            <span>Automation</span>
            <strong>{Number(reports.automation.automation_rate).toLocaleString("en-AU", { style: "percent" })}</strong>
            <p>{reports.automation.pending_reviews} pending reviews</p>
          </article>
        </section>
      ) : null}
    </main>
  );
}
