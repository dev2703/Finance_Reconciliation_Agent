"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

type ExceptionItem = {
  status: string;
  confidence?: string;
  reason_codes?: string[];
  source_record_ids?: string[];
  target_record_ids?: string[];
  evidence?: Array<{ locator?: string; excerpt?: string }>;
};

type Run = {
  id: string;
  exceptions: ExceptionItem[];
};

type Investigation = {
  id: string;
  output: {
    root_cause?: string;
    proposed_resolution?: string;
    confidence: string;
    unresolved_questions: string[];
  };
  telemetry: {
    model: string;
    prompt_tokens: number;
    completion_tokens: number;
    latency_ms: number;
  };
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

function InvestigationContent() {
  const params = useParams<{ runId: string }>();
  const search = useSearchParams();
  const index = Number(search.get("index") ?? "0");
  const [item, setItem] = useState<ExceptionItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [investigation, setInvestigation] = useState<Investigation | null>(null);
  const [investigating, setInvestigating] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        const response = await fetch(`${API_URL}/reconciliation/runs/${params.runId}`, {
          cache: "no-store",
        });
        if (!response.ok) throw new Error("Run not found");
        const run = (await response.json()) as Run;
        const safeIndex = Number.isFinite(index) ? index : 0;
        setItem(run.exceptions[safeIndex] ?? run.exceptions[0] ?? null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unavailable");
      }
    }
    void load();
  }, [params.runId, index]);

  async function investigate() {
    setInvestigating(true);
    setError(null);
    try {
      const response = await fetch(
        `${API_URL}/reconciliation/runs/${params.runId}/investigate`,
        { method: "POST" },
      );
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Investigation failed");
      setInvestigation(payload as Investigation);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Investigation failed");
    } finally {
      setInvestigating(false);
    }
  }

  return (
    <>
      {error ? (
        <section className="notice" role="status">
          <span>{error}</span>
        </section>
      ) : null}
      {item ? (
        <section className="split">
          <article className="panel">
            <p className="eyebrow">Symptom</p>
            <h2>{item.status}</h2>
            <p>Confidence {item.confidence ?? "0"}</p>
            <p>Reason codes: {(item.reason_codes ?? []).join(", ") || "none"}</p>
          </article>
          <article className="panel">
            <p className="eyebrow">Lineage</p>
            <h2>Record graph</h2>
            <p>Sources: {(item.source_record_ids ?? []).join(", ") || "none"}</p>
            <p>Targets: {(item.target_record_ids ?? []).join(", ") || "none"}</p>
          </article>
          <article className="panel">
            <p className="eyebrow">Evidence</p>
            <h2>Supporting excerpts</h2>
            {(item.evidence ?? []).length === 0 ? (
              <p>No evidence excerpts attached to this match result yet.</p>
            ) : (
              <ul>
                {(item.evidence ?? []).map((evidence, evidenceIndex) => (
                  <li key={`${evidence.locator}-${evidenceIndex}`}>
                    <strong>{evidence.locator}</strong>: {evidence.excerpt}
                  </li>
                ))}
              </ul>
            )}
          </article>
          <article className="panel">
            <p className="eyebrow">GLM investigation</p>
            <h2>{investigation?.output.root_cause ?? "Unresolved"}</h2>
            {investigation ? (
              <>
                <p>{investigation.output.proposed_resolution ?? "No resolution proposed"}</p>
                <p>Confidence {investigation.output.confidence}</p>
                <p>
                  {investigation.telemetry.model} · {investigation.telemetry.prompt_tokens + investigation.telemetry.completion_tokens} tokens · {investigation.telemetry.latency_ms} ms
                </p>
              </>
            ) : (
              <button type="button" onClick={() => void investigate()} disabled={investigating}>
                {investigating ? "Investigating…" : "Investigate with GLM"}
              </button>
            )}
            <p>Review evidence before making a decision.</p>
            <Link className="primary-action" href="/reviews">
              Open reviews
            </Link>
          </article>
        </section>
      ) : null}
    </>
  );
}

export default function InvestigationPage() {
  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Investigation</p>
          <h1>Exception detail</h1>
        </div>
        <nav aria-label="Primary navigation">
          <Link href="/exceptions">Exception queue</Link>
          <Link href="/reviews">Reviews</Link>
          <Link href="/reconciliation">Runs</Link>
        </nav>
      </header>
      <Suspense fallback={<p>Loading investigation…</p>}>
        <InvestigationContent />
      </Suspense>
    </main>
  );
}
