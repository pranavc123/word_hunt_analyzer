import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { apiGet, apiPatch, useAuthedImage } from "../api/client";
import type { BoardDetail, SessionSummary } from "../api/types";
import { Board, type TileMark } from "../components/Board";
import { Page } from "./Sessions";

const LOW = 0.05; // letters_conf below this is highlighted

export function BoardConfirm() {
  const { id } = useParams();
  const session = useQuery({ queryKey: ["session", id], queryFn: () => apiGet<SessionSummary>(`/v1/sessions/${id}`) });
  const ids = (session.data?.boards ?? []).filter((b) => b.review_status === "needs_letter_fix").map((b) => b.id);
  const boards = useQueries({
    queries: ids.map((bid) => ({ queryKey: ["board", bid], queryFn: () => apiGet<BoardDetail>(`/v1/boards/${bid}`) })),
  });
  if (session.isPending) return <Page title="Check letters" headline="Loading…" />;
  if (ids.length === 0) return <Page title="Check letters" headline="Nothing to fix in this session." />;
  return (
    <Page title="Check letters" headline="Type the 16 letters (or tap a tile and type over it), then save.">
      {boards.map((q, k) => (q.data ? <ConfirmCard key={ids[k]} board={q.data} /> : <div key={ids[k]} className="card">Loading…</div>))}
    </Page>
  );
}

export function ConfirmCard({ board }: { board: BoardDetail }) {
  const qc = useQueryClient();
  const [letters, setLetters] = useState((board.letters ?? "").padEnd(16, "?").slice(0, 16));
  const [selected, setSelected] = useState<number | null>(null);
  const field = useRef<HTMLInputElement>(null);
  const image = useAuthedImage(board.images.board);
  const save = useMutation({
    mutationFn: () => apiPatch<BoardDetail>(`/v1/boards/${board.id}/letters`, { letters }),
    onSuccess: (data) => {
      qc.setQueryData(["board", board.id], data);
      qc.invalidateQueries({ queryKey: ["session", board.session_id] });
    },
  });
  const marks: Partial<Record<number, TileMark>> = {};
  (board.letters_conf ?? []).forEach((c, i) => {
    if (c < LOW) marks[i] = "low";
  });
  for (let i = 0; i < 16; i++) if (letters[i] === "?") marks[i] = "low";
  const complete = /^[A-Z]{16}$/.test(letters);

  // tapping a tile selects its letter in the field, so the next key overwrites it
  const pick = (i: number) => {
    setSelected(i);
    const el = field.current;
    if (el) {
      el.focus();
      el.setSelectionRange(i, i + 1);
    }
  };

  return (
    <section className="card confirm">
      <div className={board.images.board ? "confirm__row" : "confirm__row confirm__row--single"}>
        {board.images.board &&
          (image ? <img className="confirm__photo" src={image} alt="Board as captured" /> : <div className="confirm__photo muted">loading…</div>)}
        <Board letters={letters} marks={marks} selected={selected} onTileClick={pick} />
      </div>
      <label className="confirm__input">
        Letters, row by row (? = unknown)
        <input
          ref={field}
          className="mono"
          autoCapitalize="characters"
          autoComplete="off"
          spellCheck={false}
          value={letters}
          onChange={(e) => {
            const el = e.target;
            const caret = el.selectionStart ?? 0;
            const next = el.value.toUpperCase().replace(/[^A-Z?]/g, "").slice(0, 16).padEnd(16, "?");
            setLetters(next);
            const i = Math.min(caret, 15);
            setSelected(i);
            requestAnimationFrame(() => el.setSelectionRange(i, i + 1)); // keep overwriting forward
          }}
        />
      </label>
      <button className="btn" disabled={!complete || save.isPending} onClick={() => save.mutate()}>
        {save.isPending ? "Saving…" : save.isSuccess ? `Saved · ${save.data.review_status.replace("_", " ")}` : "Save letters"}
      </button>
      {save.isError && <p className="error">{(save.error as Error).message}</p>}
    </section>
  );
}
