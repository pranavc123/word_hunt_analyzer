import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { apiGet } from "../api/client";
import type { SessionSummary as Summary } from "../api/types";
import { n, pct, secs, STATUS_LABEL, when } from "./format";
import { Page } from "./Sessions";

export function SessionSummary() {
  const { id } = useParams();
  const q = useQuery({ queryKey: ["session", id], queryFn: () => apiGet<Summary>(`/v1/sessions/${id}`) });
  if (q.isPending) return <Page title="Session" headline="Loading…" />;
  if (q.isError) return <Page title="Session" headline={(q.error as Error).message} />;
  const s = q.data;
  const best = s.best_board;
  const headline =
    s.played_count === 0
      ? `${s.board_count} boards looked at, none played out.`
      : `${s.played_count} of ${s.board_count} boards played; best ${n(best?.final_score ?? best?.extracted_score)}, ${s.count_30k} at 30k+.`;
  return (
    <Page title={when(s.started_at)} headline={headline}>
      <div className="stats">
        <Stat label="Boards seen" value={String(s.board_count)} />
        <Stat label="Keep rate" value={pct(s.keep_rate)} />
        <Stat label="30k+ games" value={String(s.count_30k)} />
        <Stat label="Skip time" value={`${s.skip_seconds.toFixed(0)}s`} />
      </div>
      {best && (
        <Link className="card row-link" to={`/boards/${best.id}`}>
          <div>
            <div className="muted">Best board</div>
            <strong>
              #{best.seq + 1} · {n(best.final_score ?? best.extracted_score)} of {n(best.max_points)}
            </strong>
          </div>
          <span aria-hidden>›</span>
        </Link>
      )}
      {s.biggest_miss && (
        <Link className="card row-link" to={`/boards/${s.biggest_miss.board_id}`}>
          <div>
            <div className="muted">Biggest miss</div>
            <strong>
              {s.biggest_miss.word.toUpperCase()} · {n(s.biggest_miss.points)}
            </strong>
          </div>
          <span aria-hidden>›</span>
        </Link>
      )}
      {s.needs_letter_fix > 0 && (
        <Link className="card row-link card--warn" to={`/sessions/${s.id}/confirm`}>
          <strong>
            {s.needs_letter_fix} board{s.needs_letter_fix > 1 ? "s" : ""} need letters checked
          </strong>
          <span aria-hidden>›</span>
        </Link>
      )}
      <h2>Boards</h2>
      <ul className="list">
        {(s.boards ?? []).map((b) => (
          <li key={b.id}>
            <Link className="card row-link" to={`/boards/${b.id}`}>
              <div>
                <strong>
                  #{b.seq + 1} {b.status === "played" ? n(b.final_score ?? b.extracted_score) : `skipped after ${secs(b.view_ms)}`}
                </strong>
                <div className="muted mono">{b.letters ?? "????????????????"}</div>
              </div>
              <span className={`chip chip--${b.review_status}`}>{STATUS_LABEL[b.review_status] ?? b.review_status}</span>
            </Link>
          </li>
        ))}
      </ul>
    </Page>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat">
      <div className="stat__value">{value}</div>
      <div className="stat__label">{label}</div>
    </div>
  );
}
