# S1 — Core library + oracle

Goal: harden S0 code into the reference implementation that the Swift port must match.
Starting point (S0, 2026-10-26): `whcore/oracle/{sampler,screens,traces}.py`, `letters.py`,
`words.py`, `reconcile.py`, `allwords.py` exist and pass on the real recordings; the tools
`extract_frames`, `make_review`, `build_templates`, `trace_boards`, `reconcile_boards`,
`allwords_report` produce the S0 labels in `$WH_DATA/labels/` (boards.csv, traces.json,
reconciled.json, allwords.json). S1 turns the offline tools into one pure state machine + fixtures.
Key idea: split the phone logic into **sampler** (pixels → per-frame numbers) and
**state machine** (numbers → events). Fixtures are then tiny CSVs instead of video, and
Python and Swift run the identical state machine on identical inputs.
gate: `uv run python tools/report.py --gate s1` → PASS (oracle events match the labels on session1;
CI green; fixtures < 2 MB).

- [x] **S1.T1** Sampler contract
  - files: `server/whcore/oracle/sampler.py`, `fixtures/samples/README.md`
  - do: freeze the per-frame sample record. S0 already writes `t_ms, tiles[16][3]` (top-strip patches), mean RGB + std for `banner, banner_words, banner_score, timer, end_banner, end_list`, and a 64-bin profile. Add what the machine needs and the phone can compute: `words` (live WORDS count from digit templates, blank if unreadable) and `list_shift` (all-words scroll shift from the full-resolution list-band profile with a velocity prior, blank off-screen). Document it in the README, which is the Swift contract (colour values are in the source's domain: recording vs phone).
  - done: `uv run pytest -q server/tests -k sampler`
  - deps: S0

- [x] **S1.T2** State machine (pure function)
  - files: `server/whcore/oracle/machine.py`, `server/tests/test_machine.py`
  - do: `run(samples, calibration) -> list[BoardRecord | AllWordsRecord]` implementing PLAN §2 steps 2–6 as updated after S0 (screen thresholds from `screens.py`; board crop request ≥ 0.8 s after open; attempts from tile colours; accepted = WORDS rose after release; end-list crop requested ~3 frames before the end screen leaves; all-words shifts/gap flags), with no I/O. Image crops are emitted as requests (frame index + rect), not pixels.
  - done: on `fixtures/samples/session1_*.csv`, output == `fixtures/expected/session1_events.json`; on all 27 S0 boards, board status matches `boards.csv` and accepted counts match the end WORDS
  - deps: T1

- [x] **S1.T3** Fixtures `[parallel]`
  - files: `tools/make_fixtures.py`, `fixtures/samples/*.csv.gz`, `fixtures/expected/*.json`, `fixtures/crops/*.png`
  - do: export samples for 6 boards (4 played, 2 skipped; session1 + allwords1) and 2 all-words captures (from allwords1) plus their expected events (from the S0 labels: traces.json, reconciled.json, allwords.json). Include tile and score crops for 3 boards, and export `fixtures/templates/{letters,digits}.npz` also as JSON for Swift. Keep the total under 2 MB (S0 fixtures are ~0.85 MB).
  - done: `du -sh fixtures` < 2M; `uv run pytest -q server/tests`
  - deps: T1

- [x] **S1.T4** Server-side modules final shape `[parallel]`
  - files: `server/whcore/{letters,words,reconcile,allwords,solver}.py` + tests
  - do: give them clean signatures, starting from the S0 functions — `letters.read_board(img, cal, templates) -> (letters, margins[16])`, `words.resolve_board(observed, solution, letters, end_score, visible)`, `reconcile.reconcile(words, end_words, end_score, visible)`, `allwords.stitch/summarise(frames) -> rows + counts`, `allwords.match_revealed(revealed, boards)`, `allwords.slot_evidence(rows, accepted, solver)`. Move the orchestration now in `tools/*_boards.py` into whcore so the worker can call it. Tests use only fixtures.
  - done: `uv run pytest -q server/tests` and coverage of these modules ≥ 80% (`--cov`)
  - deps: T1

- [x] **S1.T5** CI
  - files: `.github/workflows/ci.yml`
  - do: uv + ruff + pytest on push; cache uv.
  - done: workflow file passes `actionlint` (or a manual dry-run note in PROGRESS)
  - deps: T3, T4

- [ ] **S1.T6** Gate report
  - files: `tools/report.py` (`--gate s1`)
  - done: the gate prints PASS
  - deps: T2, T3, T4, T5
