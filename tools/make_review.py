"""Segment boards in sampled recordings and build the labelling page (S0.T7).

uv run python tools/make_review.py [session1 allwords1 ...]
→ $WH_DATA/labels/auto_boards.csv, $WH_DATA/labels/review.html (self-contained; crops also in review_img/)
"""

from __future__ import annotations

import argparse
import base64
import csv
import gzip
import html
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "tools"))

from extract_frames import frame_at  # noqa: E402

from whcore.calibration import load_calibration  # noqa: E402
from whcore.oracle.screens import (  # noqa: E402
    all_words_runs,
    classify,
    segment_boards,
    smooth,
    tile_state_counts,
)

WH_DATA = Path(os.environ.get("WH_DATA", ROOT / "wordhunt-data"))
CAL = load_calibration(ROOT / "fixtures/calibration/iphone-1206x2622.json")
LABELS = WH_DATA / "labels"
IMG = LABELS / "review_img"
SETTLE_FRAMES = 24  # 0.8 s at 30 fps: the board slides in from the right for ~0.6 s
FIELDS = [
    "recording", "seq", "status", "t_start_ms", "t_end_ms", "view_ms",
    "board_frame_ms", "end_t_ms", "all_words_t_ms",
]  # fmt: skip


def load_rows(name: str) -> list[dict]:
    with gzip.open(WH_DATA / "frames" / name / "samples.csv.gz", "rt") as f:
        return [{k: float(v) for k, v in r.items()} for r in csv.DictReader(f)]


def board_box() -> tuple[int, int, int, int]:
    (x0, y0), (x1, y1) = CAL["tile_centers"][0], CAL["tile_centers"][-1]
    m = CAL["pitch"][0] / 2
    return round(x0 - m), round(y0 - m), round(x1 + m), round(y1 + m)


def save_jpg(img: np.ndarray, box, path: Path, width: int) -> None:
    x0, y0, x1, y1 = box
    crop = img[y0:y1, x0:x1]
    h = round(crop.shape[0] * width / crop.shape[1])
    crop = cv2.resize(crop, (width, h), interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(path), cv2.cvtColor(crop, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 85])


def segment(name: str) -> list[dict]:
    rows = load_rows(name)
    t = [int(r["t_ms"]) for r in rows]
    labels = smooth(classify(rows))
    boards = segment_boards(labels, t)
    aw = all_words_runs(labels, t)
    resting = tile_state_counts(rows, CAL["resting_rgb_video"])
    out = []
    for b in boards:
        # clearest board frame: after the ~0.6 s slide-in, most resting tiles (ties → earliest);
        # boards left before the slide settles use their last frame
        settled = b.first + SETTLE_FRAMES
        best = (
            settled + int(np.argmax(resting[settled : b.last + 1])) if settled <= b.last else b.last
        )
        nxt = boards[b.seq + 1].first if b.seq + 1 < len(boards) else len(rows)
        cap = next((a for a, _ in aw if b.last < a < nxt), None)
        out.append(
            {
                "recording": name,
                "seq": b.seq,
                "status": b.status,
                "t_start_ms": b.t_start_ms,
                "t_end_ms": b.t_end_ms,
                "view_ms": b.view_ms,
                "board_frame_ms": t[best],
                "end_t_ms": b.end_t_ms if b.end_t_ms is not None else "",
                "all_words_t_ms": t[cap] if cap is not None else "",
            }
        )
    return out


def data_uri(path: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode()


def render(boards: list[dict]) -> str:
    cards = []
    for b in boards:
        key = f"{b['recording']}-{b['seq']}"
        end = (
            f'<img class="end" src="{data_uri(IMG / f"{key}-end.jpg")}" alt="end screen">'
            if b["end_t_ms"] != ""
            else ""
        )
        status_opts = "".join(
            f"<option{' selected' if s == b['status'] else ''}>{s}</option>"
            for s in ("played", "skipped")
        )
        cards.append(
            f"""<section class="card" data-key="{key}" data-rec="{b["recording"]}"
  data-seq="{b["seq"]}">
  <h2>{html.escape(b["recording"])} #{b["seq"]} <small>{b["t_start_ms"] / 1000:.1f}s –
  {b["t_end_ms"] / 1000:.1f}s · viewed {b["view_ms"] / 1000:.1f}s</small></h2>
  <div class="row"><img class="board" src="{data_uri(IMG / f"{key}-board.jpg")}" alt="board">{end}
  <div class="form">
    <label>Letters (16, row-major)<input class="letters" maxlength="16"
      autocomplete="off" spellcheck="false"></label>
    <div class="grid"></div>
    <label>Status <select class="status">{status_opts}</select></label>
    <div class="msg"></div>
  </div></div>
</section>"""
        )
    return PAGE.replace("{{CARDS}}", "\n".join(cards)).replace("{{N}}", str(len(boards)))


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Board labels</title>
<style>
:root { color-scheme: dark; --bg:#101412; --card:#181e1b; --line:#2c3630; --text:#e9eee9;
  --muted:#93a097; --ok:#3ecf8e; --bad:#e5675c; --tile:#e7c98f; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--text); font:15px/1.4 system-ui, sans-serif; }
header { position:sticky; top:0; z-index:1; background:var(--bg); border-bottom:1px solid var(--line);
  padding:12px 16px; display:flex; gap:12px; align-items:center; flex-wrap:wrap; }
header p { margin:0; color:var(--muted); flex:1 1 300px; }
button { background:var(--ok); color:#06120c; border:0; border-radius:8px; padding:10px 14px;
  font-weight:600; cursor:pointer; }
main { padding:16px; display:grid; gap:16px; max-width:1100px; margin:0 auto; }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px; }
.card h2 { margin:0 0 8px; font-size:16px; } .card h2 small { color:var(--muted); font-weight:400; }
.row { display:flex; gap:12px; flex-wrap:wrap; align-items:flex-start; }
img.board { width:300px; max-width:100%; border-radius:8px; }
img.end { width:220px; max-width:100%; border-radius:8px; }
.form { display:grid; gap:8px; min-width:220px; }
input.letters { font:20px ui-monospace, monospace; letter-spacing:3px; text-transform:uppercase;
  width:100%; padding:6px 8px; background:#0b0e0c; color:var(--text); border:1px solid var(--line);
  border-radius:6px; }
.grid { display:grid; grid-template-columns:repeat(4, 34px); gap:4px; }
.grid span { height:34px; display:grid; place-items:center; background:var(--tile); color:#1c1a14;
  border-radius:6px; font-weight:700; }
.msg { color:var(--muted); font-size:13px; } .msg.ok { color:var(--ok); } .msg.bad { color:var(--bad); }
select { background:#0b0e0c; color:var(--text); border:1px solid var(--line); border-radius:6px;
  padding:4px; }
</style></head><body>
<header>
  <p>Type the 16 letters of at least 8 boards (left to right, top to bottom), and fix any wrong
  played/skipped flag. Progress is kept in this browser. Then download and save as
  <code>wordhunt-data/labels/boards.csv</code>.</p>
  <span id="count"></span>
  <button id="dl">Download boards.csv</button>
</header>
<main>
{{CARDS}}
</main>
<script>
const KEY = "wh-review-v1";
let saved = {};
try { saved = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
const cards = [...document.querySelectorAll(".card")];
function update(card) {
  const inp = card.querySelector(".letters"), st = card.querySelector(".status");
  const v = inp.value.toUpperCase().replace(/[^A-Z]/g, "");
  if (inp.value !== v) inp.value = v;
  card.querySelector(".grid").innerHTML = [...v.padEnd(16, " ")].map(c => `<span>${c}</span>`).join("");
  const msg = card.querySelector(".msg");
  msg.textContent = v.length === 16 ? "complete" : v.length ? `${v.length}/16` : "";
  msg.className = "msg " + (v.length === 16 ? "ok" : v.length ? "bad" : "");
  saved[card.dataset.key] = { letters: v, status: st.value };
  try { localStorage.setItem(KEY, JSON.stringify(saved)); } catch (e) {}
  const done = cards.filter(c => c.querySelector(".letters").value.length === 16).length;
  document.getElementById("count").textContent = `${done} / {{N}} labelled`;
}
for (const card of cards) {
  const s = saved[card.dataset.key];
  if (s) { card.querySelector(".letters").value = s.letters || "";
           if (s.status) card.querySelector(".status").value = s.status; }
  card.querySelector(".letters").addEventListener("input", () => update(card));
  card.querySelector(".status").addEventListener("change", () => update(card));
  update(card);
}
document.getElementById("dl").addEventListener("click", () => {
  const lines = ["recording,seq,letters,status"];
  for (const c of cards) {
    const l = c.querySelector(".letters").value, st = c.querySelector(".status").value;
    if (l.length === 16 || st !== c.querySelector("option[selected]")?.value)
      lines.push([c.dataset.rec, c.dataset.seq, l.length === 16 ? l : "", st].join(","));
  }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([lines.join("\\n") + "\\n"], { type: "text/csv" }));
  a.download = "boards.csv"; a.click();
});
</script>
</body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("recordings", nargs="*", default=["session1", "allwords1"])
    args = ap.parse_args()
    IMG.mkdir(parents=True, exist_ok=True)
    boards = [b for name in args.recordings for b in segment(name)]
    with open(LABELS / "auto_boards.csv", "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=FIELDS)
        wr.writeheader()
        wr.writerows(boards)
    end_box = (40, 840, 566, 2040)  # player banner + found-word list (left half)
    for b in boards:
        key = f"{b['recording']}-{b['seq']}"
        save_jpg(
            frame_at(b["recording"], b["board_frame_ms"]),
            board_box(),
            IMG / f"{key}-board.jpg",
            300,
        )
        if b["end_t_ms"] != "":
            save_jpg(frame_at(b["recording"], b["end_t_ms"]), end_box, IMG / f"{key}-end.jpg", 220)
    (LABELS / "review.html").write_text(render(boards))
    summary = {
        name: {
            "boards": sum(b["recording"] == name for b in boards),
            "played": sum(b["recording"] == name and b["status"] == "played" for b in boards),
            "played_with_end": sum(
                b["recording"] == name and b["status"] == "played" and b["end_t_ms"] != ""
                for b in boards
            ),
            "all_words_after": sum(
                b["recording"] == name and b["all_words_t_ms"] != "" for b in boards
            ),
        }
        for name in args.recordings
    }
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
