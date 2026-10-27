import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiGet } from "../api/client";
import type { Attempt, BoardDetail } from "../api/types";
import { Board } from "../components/Board";
import { n, secs, STATUS_LABEL } from "./format";
import { Page } from "./Sessions";

type Tab = "found" | "missed" | "wasted";

export function GameReview() {
  const { id } = useParams();
  const q = useQuery({ queryKey: ["board", id], queryFn: () => apiGet<BoardDetail>(`/v1/boards/${id}`) });
  if (q.isPending) return <Page title="Game" headline="Loading…" />;
  if (q.isError) return <Page title="Game" headline={(q.error as Error).message} />;
  return <Review board={q.data} />;
}

export function Review({ board }: { board: BoardDetail }) {
  const [tab, setTab] = useState<Tab>("found");
  const [shown, setShown] = useState<{ path: number[]; kind: Tab; label: string } | null>(null);
  const [step, setStep] = useState(-1); // scrubber position over attempts (time order)
  const [playing, setPlaying] = useState(false);
  const attempts = useMemo(() => [...board.attempts].sort((a, b) => a.t_start_ms - b.t_start_ms), [board.attempts]);
  const found = board.words.filter((w) => w.found).sort((a, b) => (a.found_at_ms ?? 0) - (b.found_at_ms ?? 0));
  const missed = board.words.filter((w) => !w.found && w.in_base).sort((a, b) => b.points - a.points || a.word.localeCompare(b.word));
  const wasted = attempts.filter((a) => a.result !== "valid_new");
  const wastedMs = wasted.reduce((t, a) => t + (a.t_end_ms - a.t_start_ms), 0);
  const t0 = attempts[0]?.t_start_ms ?? 0;

  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(() => setStep((s) => (s + 1 < attempts.length ? s + 1 : (setPlaying(false), s))), 350);
    return () => clearInterval(timer);
  }, [playing, attempts.length]);

  const current: Attempt | undefined = step >= 0 ? attempts[step] : undefined;
  const boardPath = shown?.path ?? (current ? current.path ?? current.tiles_seen : null);
  const kind: Tab = shown?.kind ?? (current ? (current.result === "valid_new" ? "found" : "wasted") : "found");
  const score = board.final_score ?? board.extracted_score;
  const headline =
    board.status === "played"
      ? `${n(score)} of ${n(board.max_points)} possible · ${found.length} words found, ${missed.length} missed.`
      : `Skipped after ${secs(board.view_ms)}; ${n(board.max_points)} points were on the board.`;

  return (
    <Page title={`Board #${board.seq + 1}`} headline={headline}>
      <div className="review__status">
        <span className={`chip chip--${board.review_status}`}>{STATUS_LABEL[board.review_status] ?? board.review_status}</span>
        {board.fixes.map((f) => (
          <span key={f} className="chip">auto-fix: {f}</span>
        ))}
        {board.review_status === "needs_letter_fix" && <Link to={`/sessions/${board.session_id}/confirm`}>Check letters ›</Link>}
      </div>
      <Board letters={board.letters} path={boardPath} pathKind={kind} label={shown?.label ?? current?.word ?? undefined} />
      {attempts.length > 0 && (
        <div className="scrubber">
          <button className="btn btn--small" onClick={() => setPlaying(!playing)} aria-label={playing ? "Pause replay" : "Play replay"}>
            {playing ? "❚❚" : "▶"}
          </button>
          <input
            type="range"
            min={-1}
            max={attempts.length - 1}
            value={step}
            aria-label="Replay position"
            onChange={(e) => {
              setShown(null);
              setStep(Number(e.target.value));
            }}
          />
          <span className="mono scrubber__label">
            {current ? `${secs(current.t_start_ms - t0)} ${current.word ?? "—"} ${current.result === "valid_new" ? "✓" : "✗"}` : "start"}
          </span>
        </div>
      )}
      <div className="tabs" role="tablist">
        {(["found", "missed", "wasted"] as Tab[]).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "tab tab--on" : "tab"} onClick={() => setTab(t)}>
            {t === "found" ? `Found ${found.length}` : t === "missed" ? `Missed ${missed.length}` : `Wasted ${secs(wastedMs)}`}
          </button>
        ))}
      </div>
      <ul className="words" role="tabpanel">
        {tab === "found" &&
          found.map((w) => (
            <WordRow key={w.word} word={w.word} points={w.points} note={w.found_at_ms != null ? secs(w.found_at_ms - t0) : ""}
              onClick={() => setShown({ path: w.path, kind: "found", label: w.word })} />
          ))}
        {tab === "missed" &&
          missed.map((w) => (
            <WordRow key={w.word} word={w.word} points={w.points} note={w.in_enable ? "" : "rare"}
              onClick={() => setShown({ path: w.path, kind: "missed", label: w.word })} />
          ))}
        {tab === "wasted" &&
          wasted.map((a) => (
            <WordRow key={a.seq} word={a.result === "already_found" ? "(again)" : "(not a word)"} points={0}
              note={secs(a.t_end_ms - a.t_start_ms)} onClick={() => setShown({ path: a.tiles_seen, kind: "wasted", label: "wasted" })} />
          ))}
      </ul>
      <nav className="pager">
        {board.prev_id ? <Link to={`/boards/${board.prev_id}`}>‹ Previous</Link> : <span />}
        <Link to={`/sessions/${board.session_id}`}>Session</Link>
        {board.next_id ? <Link to={`/boards/${board.next_id}`}>Next ›</Link> : <span />}
      </nav>
    </Page>
  );
}

function WordRow({ word, points, note, onClick }: { word: string; points: number; note: string; onClick: () => void }) {
  return (
    <li>
      <button className="word" onClick={onClick}>
        <span className="mono">{word.toUpperCase()}</span>
        <span className="muted">{note}</span>
        <span>{points ? n(points) : ""}</span>
      </button>
    </li>
  );
}
