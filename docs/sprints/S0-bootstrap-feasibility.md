# S0 — Bootstrap + feasibility

Goal: prove that every signal in PLAN §2–§3 is readable, writing the code straight into
`whcore` so nothing is thrown away.
Inputs (in `$WH_DATA`):
- `recordings/IMG_0717.PNG`: board screen at 00:01, all tiles unselected (calibration + letters).
- `recordings/IMG_0718.PNG`: end screen of the same game (65 words, 44,700 points).
- `recordings/session1.mov`: one full session WITHOUT "VIEW ALL WORDS" (arrives later; T5).
- `recordings/allwords1.mov`: VIEW ALL WORDS on 5+ games of session1 after opponents played (arrives later; T5).
gate: `uv run python tools/report.py --gate s0` prints PASS. That means board segmentation is
≥95% vs labels, ≥4 of 5 played games reconcile (§3.3), ≥3 all-words captures matched to the
right board (§3.6), extension memory peak <45 MB over 30 min, and the max overlapping flick
speed is recorded. On FAIL, write the go/no-go note in `docs/measurements.md` and ask the user.

Order without recordings: T1 → T2, T3 [parallel] → T4 → T14. Then S2.T1 and S4.T3 can start
early (they only need the schema).

- [x] **S0.T1** Scaffold repo
  - files: `pyproject.toml` (uv; deps: pydantic, numpy, opencv-python-headless, pillow, pytesseract, fastapi, uvicorn, pytest, ruff), `.gitignore`, `server/whcore/__init__.py`, `server/tests/test_smoke.py`, `fixtures/words_small.txt` (~400 words incl. all YAWL words on the IMG_0717 board), `fixtures/boards/img0717.json`, `dictionaries/` (copied from `$WH_DATA/dictionaries/`), `dictionaries/SOURCES.md`
  - .gitignore: `wordhunt-data/`, `*.mov`, `*.MOV`, `ios/App/*.xcodeproj`, `ios/App/Signing.xcconfig`, `ios/App/Config.xcconfig`, `node_modules`, `.venv`, `*.db`
  - fixture `img0717.json`: `{"letters":"LCMEORSIETRATDIM","word_count":65,"score":44700,"top15":[["CLOTTERS",2200],["CLOTTED",1800],...]}` in screen order: CLOTTERS 2200; CLOTTED, CLOTTER, COTTERS, LOTTERS, RITTERS 1800; COTTER, LOTTER, MASTED, MASTER, MISTED, MISTER, MITERS, RASTER, RIDERS 1400.
  - SOURCES.md: YAWL (github.com/elasticdog/yawl, public domain, 264,097 words) and ENABLE (public domain, 172,823 words).
  - done: `uv run pytest -q server/tests && uv run ruff check server tools && git check-ignore -q wordhunt-data && wc -l dictionaries/yawl.txt | grep -q 264097`
  - deps: —

- [x] **S0.T2** Scoring + trie solver `[parallel]`
  - files: `server/whcore/scoring.py`, `server/whcore/solver.py`, `server/tests/test_solver.py`
  - do: PLAN §1 scoring; trie from a word file; DFS returns {word: [paths]} plus the best path (fewest direction changes); loader normalises per §6.
  - test (real board LCMEORSIETRATDIM): with `dictionaries/yawl.txt`, 335 words and 262,800 max points; with `enable1.txt`, 251 words and 196,500 max points; all 15 top words are in the YAWL result; 4 of them (CLOTTER, CLOTTERS, LOTTER, LOTTERS) are absent from ENABLE. Each solve < 100 ms after load.
  - done: `uv run pytest -q server/tests/test_solver.py`
  - deps: T1

- [x] **S0.T3** Event schema v1 `[parallel]`
  - files: `server/whcore/schema.py`, `tools/export_schema.py`, `fixtures/schema/v1.json`, `server/tests/test_schema.py`
  - do: implement PLAN §4 exactly (BoardRecord + AllWordsRecord, discriminated on `kind`); export the JSON Schema; round-trip test.
  - done: `uv run pytest -q server/tests/test_schema.py && uv run python tools/export_schema.py --check`
  - deps: T1

- [x] **S0.T4** Calibration from screenshots
  - files: `server/whcore/calibration.py`, `tools/calibrate.py`, `fixtures/calibration/iphone-1206x2622.json`, `fixtures/crops/img0717_tiles.png` (downscaled), `server/tests/test_calibration.py`
  - do: from IMG_0717, detect the 4x4 tile grid (uniform beige blobs on the green board) → 16 tile centres and a patch size; locate the banner ROI (WORDS/SCORE) and the timer ROI. From IMG_0718, locate the end-screen banner and the left word-list column. Save resting-tile RGB in the calibration. Seed letter templates from the 16 IMG_0717 tiles (letters known). You may view ONE downscaled crop to confirm the grid.
  - done: `uv run pytest -q server/tests/test_calibration.py` (16 centres on a regular grid, spacing variance < 3%; re-reading IMG_0717 tiles with the seed templates returns LCMEORSIETRATDIM)
  - deps: T1

- [x] **S0.T5** `[HUMAN]` Recordings
  - Play one normal session with screen recording on and the Focus on; don't open VIEW ALL WORDS. Save as `$WH_DATA/recordings/session1.mov`.
  - On one played game, tap "(N more)" on the end screen and note whether the full found list opens (tell the agent).
  - After opponents have played back 5+ of those games: start a short screen recording, open each game, tap VIEW ALL WORDS, and flick to the bottom at varied speeds (gentle to hardest). Save as `$WH_DATA/recordings/allwords1.mov`.
  - deps: —

- [x] **S0.T6** Frame extraction + numeric sampling
  - files: `tools/extract_frames.py`, `server/whcore/oracle/sampler.py`
  - do: ffmpeg → 30 fps PNG frames to `$WH_DATA/frames/<recording>/`. Record native resolution and fps in measurements.md; if not 1206×2622, rescale the calibration. Write `samples.csv`: frame, t_ms, 16×(r,g,b), ROI means, 64-bin row profile.
  - done: `samples.csv` exists for session1; tile samples on a known board frame match the calibration's resting RGB within ±12
  - deps: T4, T5 (session1.mov)

- [x] **S0.T7** Screen classifier + board segmenter
  - files: `server/whcore/oracle/screens.py`, `tools/make_review.py`
  - do: classify `board|end|all_words|other` from ROI stats; segment boards; played = reaches `end`. Write `$WH_DATA/labels/auto_boards.csv` and `$WH_DATA/labels/review.html` (per board: board crop, timestamps, status, an empty letters field, and the end-screen crop for played boards).
  - done: board count 35–60; every played board has an end-screen frame
  - deps: T6

- [x] **S0.T8** `[HUMAN]` Label boards (~15 min)
  - Open `review.html`. For 8+ boards, type the 16 letters (row-major). Fix any wrong played/skipped flags. Save as `$WH_DATA/labels/boards.csv`.
  - deps: T7

- [ ] **S0.T9** Tile colour states + trace segmenter
  - files: `server/whcore/oracle/traces.py`, `server/tests/test_traces.py`
  - do: cluster tile colours across board frames into resting + 3 selected states; log RGB centroids to measurements.md. Segment attempts; record `tiles_seen`, `release_state`, and the banner word count after release (digit templates from the banner ROI).
  - done: on every labelled played board, accepted attempts == the end screen's WORDS count
  - deps: T7, T8

- [x] **S0.T10** Letter recognizer
  - files: `server/whcore/letters.py`, `$WH_DATA/templates/`
  - do: extend the T4 seed templates with the labelled boards; nearest-template with a confidence margin; digit templates for SCORE/WORDS.
  - done: leave-one-board-out tile accuracy ≥ 99%; SCORE and WORDS read correctly on all played boards
  - deps: T4, T8

- [ ] **S0.T11** Words + reconciliation
  - files: `server/whcore/words.py`, `server/whcore/reconcile.py`, `server/tests/test_reconcile.py`
  - do: path → word; gap-fill non-adjacent steps with solver paths; reconcile per §3.3 (score, word count, visible top words via tesseract with an A–Z allow-list, snapped to the nearest solver word; points column checked against the formula). Unit test on IMG_0718: the 15 visible words and their points are read correctly.
  - done: `uv run pytest -q server/tests/test_reconcile.py` and ≥ 4 of 5 labelled played boards reconcile
  - deps: T2, T9, T10

- [ ] **S0.T12** All-words feasibility + matching
  - files: `server/whcore/allwords.py`, `server/tests/test_allwords.py`
  - do: per §3.5–3.7 on allwords1.mov: stitch rows with 1-D profile shifts, count `?` per row, OCR unmasked rows, run the self-checks, compute per-length counts, match each capture to its session1 board (§3.6), and slot-match. Measure the largest per-frame shift that still overlaps, at 30 and 15 fps.
  - done: ≥ 3 captures matched to the right board; per-length totals compared with YAWL and ENABLE solver counts and logged; max safe shift in measurements.md
  - deps: T9, T11, T5 (allwords1.mov)

- [ ] **S0.T13** fps sweep
  - do: re-run T7/T9 on every 2nd frame (15 fps). Record segmentation and trace accuracy at both rates in measurements.md.
  - done: table in measurements.md
  - deps: T9, T11

- [x] **S0.T14** Minimal device probe
  - files: `ios/App/project.yml` (XcodeGen), `ios/App/Signing.example.xcconfig`, `ios/App/Config.example.xcconfig`, `ios/App/CompanionApp/*`, `ios/App/BroadcastExtension/SampleHandler.swift`, `server/app/main.py` (`POST /diag` → append to `$WH_DATA/diag.jsonl`; `GET /v1/health`)
  - do: CompanionApp with an `RPSystemBroadcastPickerView` preset to the extension and a health check of the compiled server URL. The extension samples the 16 patches from each `CVPixelBuffer` (tile centres compiled from the T4 calibration) and every 10 s POSTs {fps_processed, frames_dropped, mem_mb (task_vm_info phys_footprint), app_group_available}. No App Groups dependency.
  - done: `xcodegen generate --spec ios/App/project.yml && xcodebuild ... -quiet build` succeeds
  - deps: T4

- [ ] **S0.T15** `[HUMAN]` Device run (~35 min)
  - Copy `Signing.example.xcconfig` → `Signing.xcconfig` (set your team ID) and `Config.example.xcconfig` → `Config.xcconfig` (your `https://<mac>.<tailnet>.ts.net` URL and `$WH_TOKEN`). Start the server and `tailscale serve --bg 8000`. Run on the iPhone from Xcode, turn on the Focus, start the broadcast, play 30+ minutes normally, then stop.
  - deps: T14

- [ ] **S0.T16** Go/no-go report
  - files: `tools/report.py` (with `--gate s0`)
  - do: summarise diag.jsonl (memory peak, fps distribution, drops, App Groups) and T7–T13 numbers; write the decision to measurements.md.
  - done: the gate command prints PASS or FAIL with reasons
  - deps: T11, T12, T13, T15
