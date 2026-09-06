"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

type Review = {
  id: string;
  run_id: string;
  status: string;
  actor?: string | null;
  reason?: string | null;
  created_at: string;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export default function ReviewsPage() {
  const [reviews, setReviews] = useState<Review[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "unavailable">("loading");
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState("loading");
    try {
      const response = await fetch(`${API_URL}/reviews/pending`, { cache: "no-store" });
      if (!response.ok) throw new Error("unavailable");
      const payload = (await response.json()) as { reviews: Review[] };
      setReviews(payload.reviews);
      setState("ready");
    } catch {
      setState("unavailable");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function decide(reviewId: string, decision: "AUTO_APPROVE" | "REJECT" | "ESCALATE") {
    setMessage(null);
    const response = await fetch(`${API_URL}/reviews/${reviewId}/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        decision,
        actor: "reviewer",
        reason: `UI ${decision.toLowerCase()} after evidence review`,
      }),
    });
    if (!response.ok) {
      setMessage("Decision failed. Reload and try again.");
      return;
    }
    setMessage(`Recorded ${decision}.`);
    await load();
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Approvals</p>
          <h1>Human review queue</h1>
        </div>
        <nav aria-label="Primary navigation">
          <Link href="/exceptions">Exceptions</Link>
          <Link href="/reports">Reports</Link>
          <Link href="/dashboard">Dashboard</Link>
        </nav>
      </header>

      {message ? (
        <section className="notice" role="status">
          <span>{message}</span>
        </section>
      ) : null}

      {state === "unavailable" ? (
        <section className="notice" role="status">
          <span>Review API is unavailable.</span>
          <button type="button" onClick={() => void load()}>
            Retry
          </button>
        </section>
      ) : null}

      {state === "ready" && reviews.length === 0 ? (
        <section className="worklist">
          <div>
            <p className="eyebrow">Idle</p>
            <h2>No pending reviews.</h2>
          </div>
          <Link className="primary-action" href="/reconciliation">
            Seed or open a run
          </Link>
        </section>
      ) : null}

      {reviews.length > 0 ? (
        <section>
          <h2>Pending decisions</h2>
          <table>
            <thead>
              <tr>
                <th>Created</th>
                <th>Run</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {reviews.map((review) => (
                <tr key={review.id}>
                  <td>{new Date(review.created_at).toLocaleString("en-AU")}</td>
                  <td>
                    <Link href={`/investigation/${review.run_id}`}>{review.run_id.slice(0, 8)}</Link>
                  </td>
                  <td>{review.status}</td>
                  <td className="actions">
                    <button type="button" onClick={() => void decide(review.id, "AUTO_APPROVE")}>
                      Approve
                    </button>
                    <button type="button" onClick={() => void decide(review.id, "REJECT")}>
                      Reject
                    </button>
                    <button type="button" onClick={() => void decide(review.id, "ESCALATE")}>
                      Escalate
                    </button>
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
