"""Phone state machine (PLAN §2.2–2.6) as a pure, streaming function: sample rows → records.

`Machine.feed(row)` consumes one sample row (fixtures/samples/README.md) at a time and never looks
ahead, so the Swift port (S2.T2) can mirror it line by line. Image crops are emitted as requests
(frame index + rect name), never pixels. `run()` is the batch wrapper.
"""

from __future__ import annotations

import math
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np

from ..schema import AllWordsRecord, Attempt, BoardRecord, Diagnostics
from .screens import classify_row
from .traces import RELEASE, SELECTED, STATES, tile_codes

CONFIRM_FRAMES = 3  # a new screen counts after this many consecutive frames
MERGE_GAP_MS = 700  # board interruptions shorter than this are the same board
END_WITHIN_MS = 4000  # an end screen this soon after a board closes → played
SETTLE_MS = 800  # board slide-in: crop the board at least this long after open
FIRST_CROP_MS = 200  # all-words list animates in: first crop no earlier than this
AFTER_FRAMES = 4  # read the WORDS count this many frames after a release
END_CROP_BACK = 3  # end list: crop this many frames before the end screen leaves
ALLWORDS_MERGE_MS = 1500
BAND_PX = 2600 - 612  # all-words list band height
CROP_EVERY_PX = BAND_PX // 2  # save a list crop every ~0.5 viewport of scrolling
GAP_PX = BAND_PX - 300  # a shift this big leaves too little overlap


@dataclass
class CropRequest:
    name: str  # image filename referenced by the record
    frame: int
    rect: str  # calibration key, or "board" for the tile area


@dataclass
class _Attempt:
    first: int
    last: int
    tiles: list[int]
    release: str
    words_before: float
    words_after: float | None = None


@dataclass
class _Board:
    seq: int
    first: int
    last: int
    attempts: list[_Attempt] = field(default_factory=list)
    open_attempt: _Attempt | None = None
    pending: _Attempt | None = None  # released, waiting for its WORDS read
    prev_codes: str | None = None
    words: float = 0.0
    crop_frame: int | None = None
    end_first: int | None = None
    end_last: int | None = None


@dataclass
class _AllWords:
    first: int
    last: int
    shifts: list[int] = field(default_factory=list)  # per frame (kept for the bounce check)
    offset: int = 0  # cumulative scroll since the first crop
    gap_since_crop: bool = False
    since_crop: int = 0
    crop_frames: list[int] = field(default_factory=list)
    crop_offsets: list[int] = field(default_factory=list)
    crop_gaps: list[bool] = field(default_factory=list)
    base: int = 0  # offset at the first crop
    stills: deque = field(default_factory=lambda: deque(maxlen=90))  # recent (frame, offset)


class Machine:
    def __init__(self, session_id: str, started_at: datetime, device: str = "oracle",
                 app_version: str = "oracle", calibration_version: str = "iphone-1206x2622@1",
                 states: dict | None = None):  # fmt: skip
        self.session_id = session_id
        self.started_at = started_at
        self.device, self.app_version, self.cal_version = device, app_version, calibration_version
        self.states = states or STATES
        self.screen = "other"
        self.candidate, self.candidate_n, self.candidate_first = "other", 0, 0
        self.board: _Board | None = None
        self.closed: _Board | None = None  # board waiting for a possible end screen
        self.aw: _AllWords | None = None
        self.seq = 0
        self.records: list[BoardRecord | AllWordsRecord] = []
        self.crops: list[CropRequest] = []
        self.t: list[int] = []
        self.recent: deque = deque(maxlen=CONFIRM_FRAMES)  # (i, row, label) awaiting confirmation

    # ---- screen confirmation ------------------------------------------------

    def _confirm(self, label: str, i: int) -> tuple[str, int] | None:
        """Hysteresis: (new_screen, first_frame) once a label has held CONFIRM_FRAMES frames."""
        if label == self.candidate:
            self.candidate_n += 1
        else:
            self.candidate, self.candidate_n, self.candidate_first = label, 1, i
        if self.candidate != self.screen and self.candidate_n >= CONFIRM_FRAMES:
            self.screen = self.candidate
            return self.screen, self.candidate_first
        return None

    # ---- main entry -----------------------------------------------------------

    def feed(self, row: dict) -> None:
        i = len(self.t)
        self.t.append(int(row["t_ms"]))
        label = classify_row(row)
        change = self._confirm(label, i)
        if change:
            self._on_screen_change(*change)
            # replay the frames that were held back while the new screen was being confirmed
            for j, r, lab in self.recent:
                if j >= change[1]:
                    self._dispatch(j, r, lab)
        self._dispatch(i, row, label)
        self.recent.append((i, row, label))
        self._maybe_finalise(i)

    def _dispatch(self, i: int, row: dict, label: str) -> None:
        if self.screen == "board" and self.board is not None:
            if label == "board":  # transition frames during confirmation are not board frames
                self._board_frame(i, row)
        elif self.screen == "end" and self.closed is not None and self.closed.end_first is not None:
            self.closed.end_last = i
        elif self.screen == "all_words" and self.aw is not None:
            self._allwords_frame(i, row)

    def _on_screen_change(self, screen: str, first: int) -> None:
        t0 = self.t[first]
        if screen == "board":
            if (
                self.closed is not None
                and self.closed.end_first is None
                and t0 - self.t[self.closed.last] < MERGE_GAP_MS
            ):
                self.board, self.closed = self.closed, None  # brief interruption: same board
            else:
                self._finalise_closed()
                self.board = _Board(seq=self.seq, first=first, last=first)
                self.seq += 1
            return
        if self.board is not None:  # leaving a board
            self._close_attempt(self.board, self.board.last)
            self.closed, self.board = self.board, None
        if screen == "end" and self.closed is not None and self.closed.end_first is None:
            if t0 - self.t[self.closed.last] <= END_WITHIN_MS:
                self.closed.end_first = self.closed.end_last = first
        if screen == "all_words":
            if self.aw is not None and t0 - self.t[self.aw.last] < ALLWORDS_MERGE_MS:
                pass
            else:
                self._finalise_allwords()
                self.aw = _AllWords(first=first, last=first)
        elif self.aw is not None and screen != "all_words":
            pass  # finalised once the merge window passes (_maybe_finalise)

    # ---- boards ---------------------------------------------------------------

    def _codes(self, row: dict) -> str:
        tiles = np.array([[row[f"t{k}_{c}"] for c in "rgb"] for k in range(16)], float)[None]
        return "".join(tile_codes(tiles, self.states)[0])

    def _board_frame(self, i: int, row: dict) -> None:
        b = self.board
        b.last = i
        if b.crop_frame is None and self.t[i] - self.t[b.first] >= SETTLE_MS:
            b.crop_frame = i
        words = row.get("words", math.nan)
        codes = self._codes(row)
        active = any(c in SELECTED for c in codes)
        # pending release: resolve the WORDS read AFTER_FRAMES later, or right before a new attempt
        if b.pending is not None and (i - b.pending.last >= AFTER_FRAMES or active):
            read_at = words if not active else b.words
            b.pending.words_after = read_at if not math.isnan(read_at) else None
            b.attempts.append(b.pending)
            b.pending = None
        if not math.isnan(words) and not active:
            b.words = words
        a = b.open_attempt
        if active:
            if a is None or i - a.last > 2:
                if a is not None:
                    self._close_attempt(b, a.last)
                a = b.open_attempt = _Attempt(
                    first=i, last=i, tiles=[], release="", words_before=b.words
                )
            a.last = i
            for tile, c in enumerate(codes):
                if tile in a.tiles:
                    continue
                fresh = c == "?" and b.prev_codes is not None and b.prev_codes[tile] == "R"
                if c in SELECTED or (fresh and i > a.first):
                    a.tiles.append(tile)
            rel = "".join(c for c in codes if c in SELECTED)
            a.release = max("GYWX", key=rel.count) if rel else "W"
        elif a is not None and i - a.last > 2:
            self._close_attempt(b, a.last)
        b.prev_codes = codes

    def _close_attempt(self, b: _Board, last: int) -> None:
        if b.open_attempt is not None:
            if b.pending is not None:
                b.pending.words_after = b.words
                b.attempts.append(b.pending)
            b.pending, b.open_attempt = b.open_attempt, None

    # ---- all words ------------------------------------------------------------

    def _allwords_frame(self, i: int, row: dict) -> None:
        aw = self.aw
        aw.last = i
        s = row.get("list_shift", math.nan)
        if math.isnan(s):
            return
        s = int(s)
        aw.shifts.append(s)
        aw.offset += s
        aw.gap_since_crop |= abs(s) > GAP_PX
        aw.since_crop += abs(s)
        # crop every ~0.5 viewport, preferring a still frame (sharp text); force one before rows
        # could scroll past unseen
        still = abs(s) <= 2
        if still:
            aw.stills.append((i, aw.offset))
        if not aw.crop_frames:
            # the list animates in: first crop on a still frame once it has settled
            if still and self.t[i] - self.t[aw.first] >= FIRST_CROP_MS:
                aw.base = aw.offset
                self._crop_allwords(aw, i, aw.offset)
            return
        if (aw.since_crop >= CROP_EVERY_PX and still) or aw.since_crop >= GAP_PX - 200:
            self._crop_allwords(aw, i, aw.offset)

    @staticmethod
    def _crop_allwords(aw: _AllWords, i: int, offset: int) -> None:
        aw.crop_frames.append(i)
        aw.crop_offsets.append(offset - aw.base)
        aw.crop_gaps.append(aw.gap_since_crop if aw.crop_frames[:-1] else False)
        aw.since_crop, aw.gap_since_crop = 0, False

    # ---- finalisation -----------------------------------------------------------

    def _maybe_finalise(self, i: int) -> None:
        if self.closed is not None and self.screen != "end" and self.screen != "board":
            waited = (
                self.t[i]
                - self.t[
                    self.closed.end_last if self.closed.end_first is not None else self.closed.last
                ]
            )
            if (
                self.closed.end_first is not None and self.screen != "end"
            ) or waited > END_WITHIN_MS:
                self._finalise_closed()
        if (
            self.aw is not None
            and self.screen != "all_words"
            and self.t[i] - self.t[self.aw.last] >= ALLWORDS_MERGE_MS
        ):
            self._finalise_allwords()

    def _finalise_closed(self) -> None:
        b, self.closed = self.closed, None
        if b is None:
            return
        if b.pending is not None:
            b.pending.words_after = b.words
            b.attempts.append(b.pending)
            b.pending = None
        played = b.end_first is not None
        bid = str(uuid.uuid5(uuid.UUID(self.session_id), f"board-{b.seq}"))
        crop = b.crop_frame if b.crop_frame is not None else b.last
        self.crops.append(CropRequest(f"board_{b.seq}.png", crop, "board"))
        end_banner = end_list = None
        if played:
            fe = max(b.end_first, b.end_last - END_CROP_BACK)
            end_banner, end_list = f"end_banner_{b.seq}.png", f"end_list_{b.seq}.png"
            self.crops.append(CropRequest(end_banner, fe, "roi_end_banner"))
            self.crops.append(CropRequest(end_list, fe, "roi_end_list"))
        attempts = []
        for k, a in enumerate(b.attempts):
            accepted = a.words_after is not None and a.words_after == a.words_before + 1
            state = (
                "valid_new"
                if accepted
                else (
                    "already_found" if RELEASE.get(a.release) == "already_found" else "not_a_word"
                )
            )
            colour_agrees = accepted == (RELEASE.get(a.release) == "valid_new")
            after = int(a.words_after) if a.words_after is not None else None
            attempts.append(
                Attempt(
                    seq=k,
                    t_start_ms=self.t[a.first],
                    t_end_ms=self.t[a.last],
                    tiles_seen=a.tiles,
                    release_state=state,
                    banner_words_after=after,
                    confidence=1.0 if colour_agrees else 0.5,
                )
            )
        n = b.last - b.first + 1
        dur = max(1, self.t[b.last] - self.t[b.first])
        self.records.append(
            BoardRecord(
                board_id=bid,
                session_id=self.session_id,
                seq=b.seq,
                device=self.device,
                app_version=self.app_version,
                calibration_version=self.cal_version,
                opened_at=self.started_at + timedelta(milliseconds=self.t[b.first]),
                view_ms=self.t[b.last] - self.t[b.first],
                status="played" if played else "skipped",
                board_image=f"board_{b.seq}.png",
                end_banner_image=end_banner,
                end_list_image=end_list,
                attempts=attempts,
                diagnostics=Diagnostics(
                    fps_processed=round(1000 * (n - 1) / dur, 1), frames_dropped=0, mem_peak_mb=0.0
                ),
            )  # fmt: skip
        )

    def _finalise_allwords(self) -> None:
        aw, self.aw = self.aw, None
        if aw is None:
            return
        # the list animates out at the end: the final crop is the last still frame at least
        # FIRST_CROP_MS before the run ends
        settled = [(f, o) for f, o in aw.stills if self.t[aw.last] - self.t[f] >= FIRST_CROP_MS]
        if settled and (not aw.crop_frames or aw.crop_frames[-1] < settled[-1][0]):
            self._crop_allwords(aw, *settled[-1])
        if not aw.crop_frames:
            return
        k = sum(isinstance(r, AllWordsRecord) for r in self.records)
        names = []
        for j, f in enumerate(aw.crop_frames):
            names.append(f"allwords_{k}_{j}.png")
            self.crops.append(CropRequest(names[-1], f, "list_band"))
        tail = aw.shifts[-60:]
        moved = [s for s in tail if s]
        bounced = len(moved) >= 2 and any(s > 0 for s in moved) and any(s < 0 for s in moved)
        rid = str(uuid.uuid5(uuid.UUID(self.session_id), f"allwords-{k}"))
        self.records.append(
            AllWordsRecord(
                record_id=rid,
                session_id=self.session_id,
                captured_at=self.started_at + timedelta(milliseconds=self.t[aw.first]),
                frames=names,
                shifts_px=aw.crop_offsets,  # offset of each crop from the first (px)
                gap_flags=aw.crop_gaps,  # a gap happened between crop k-1 and crop k
                bounced_at_end=bounced,
            )  # fmt: skip
        )

    def finish(self) -> None:
        if self.board is not None:
            self._close_attempt(self.board, self.board.last)
            self.closed, self.board = self.board, None
        self._finalise_closed()
        self._finalise_allwords()
        self.records.sort(
            key=lambda r: r.opened_at if isinstance(r, BoardRecord) else r.captured_at
        )


def run(rows, session_id: str, started_at: datetime, **kw):
    """Batch wrapper: (records, crop requests)."""
    m = Machine(session_id, started_at, **kw)
    for r in rows:
        m.feed(r)
    m.finish()
    return m.records, m.crops
