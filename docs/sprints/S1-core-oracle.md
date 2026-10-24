# S1 — Core library + oracle

Goal: harden S0 code into the reference implementation that the Swift port must match.
Key idea: split the phone logic into **sampler** (pixels → per-frame numbers) and
**state machine** (numbers → events). Fixtures are then tiny CSVs instead of video, and
Python and Swift run the identical state machine on identical inputs.
gate: `uv run python tools/report.py --gate s1` → PASS (oracle events match the labels on session1;
CI green; fixtures < 2 MB).

- [ ] **S1.T1** Sampler contract
  - files: `server/whcore/oracle/sampler.py`, `fixtures/samples/README.md`
  - do: freeze the per-frame sample record: `t_ms, tiles[16][3], roi_score[3], roi_timer[3], roi_banner[3], profile[64]` (64-bin row-intensity profile of the list area). Document it in the README, which is the Swift contract.
  - done: `uv run pytest -q server/tests -k sampler`
  - deps: S0

- [ ] **S1.T2** State machine (pure function)
  - files: `server/whcore/oracle/machine.py`, `server/tests/test_machine.py`
  - do: `run(samples, calibration) -> list[BoardRecord | AllWordsRecord]` implementing PLAN §2 steps 2–6, with no I/O. Image crops are emitted as requests (frame index + rect), not pixels.
  - done: on `fixtures/samples/session1_*.csv`, output == `fixtures/expected/session1_events.json`
  - deps: T1

- [ ] **S1.T3** Fixtures `[parallel]`
  - files: `tools/make_fixtures.py`, `fixtures/samples/*.csv.gz`, `fixtures/expected/*.json`, `fixtures/crops/*.png`
  - do: export samples for 6 boards (4 played, 2 skipped) and 2 all-words captures (from allwords1) plus their expected events. Include tile and score crops for 3 boards. Keep the total under 2 MB.
  - done: `du -sh fixtures` < 2M; `uv run pytest -q server/tests`
  - deps: T1

- [ ] **S1.T4** Server-side modules final shape `[parallel]`
  - files: `server/whcore/{letters,words,reconcile,allwords,solver}.py` + tests
  - do: give them clean signatures — `read_letters(img, cal) -> (letters, conf[16])`, `build_words(attempts, letters, solver)`, `reconcile(board, score, word_count, visible_words)`, `process_allwords(frames, shifts) -> rows`, `match_allwords(rows, candidate_boards)`. Tests use only fixtures.
  - done: `uv run pytest -q server/tests` and coverage of these modules ≥ 80% (`--cov`)
  - deps: T1

- [ ] **S1.T5** CI
  - files: `.github/workflows/ci.yml`
  - do: uv + ruff + pytest on push; cache uv.
  - done: workflow file passes `actionlint` (or a manual dry-run note in PROGRESS)
  - deps: T3, T4

- [ ] **S1.T6** Gate report
  - files: `tools/report.py` (`--gate s1`)
  - done: the gate prints PASS
  - deps: T2, T3, T4, T5
