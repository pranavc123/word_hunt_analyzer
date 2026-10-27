import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { apiGet } from "../api/client";
import type { SessionSummary } from "../api/types";
import { n, pct, when } from "./format";

export function Sessions() {
  const q = useQuery({ queryKey: ["sessions"], queryFn: () => apiGet<SessionSummary[]>("/v1/sessions") });
  if (q.isPending) return <Page title="Sessions" headline="Loading your sessions…" />;
  if (q.isError) return <Page title="Sessions" headline={(q.error as Error).message} />;
  if (q.data.length === 0) return <Page title="Sessions" headline="Your first session shows up here after you play." />;
  const latest = q.data[0];
  return (
    <Page
      title="Sessions"
      headline={`Last session: ${latest.played_count} played, ${latest.count_30k} at 30k+, ${latest.verified_count} verified.`}
    >
      <ul className="list">
        {q.data.map((s) => (
          <li key={s.id}>
            <Link className="card row-link" to={`/sessions/${s.id}`}>
              <div>
                <strong>{when(s.started_at)}</strong>
                <div className="muted">
                  {s.board_count} boards · keep {pct(s.keep_rate)} · best {n(s.best_board?.final_score ?? s.best_board?.extracted_score)}
                </div>
              </div>
              {s.needs_letter_fix > 0 && <span className="chip chip--warn">{s.needs_letter_fix} to fix</span>}
            </Link>
          </li>
        ))}
      </ul>
    </Page>
  );
}

export function Page({ title, headline, children }: { title: string; headline: string; children?: React.ReactNode }) {
  return (
    <main className="page">
      <h1>{title}</h1>
      <p className="headline">{headline}</p>
      {children}
    </main>
  );
}
