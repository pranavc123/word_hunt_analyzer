# S7 — Perception model + strategy + handoff docs

Goal: ranked, tracked advice from the user's misses. PLAN §7 models + §9.
gate: `uv run python tools/report.py --gate s7` → PASS (models fit with reported CIs; ≥ 1
recommendation in tracking; README + CONTRIBUTING exist; full test suites green).

- [ ] **S7.T1** Word features `[parallel]`
  - files: `server/whcore/analytics/word_features.py`, tests
  - do: PLAN §7 feature list into `board_words.features`; zipf from `wordfreq`; backfill.
  - done: `uv run pytest -q server/tests -k word_features`
  - deps: S6

- [ ] **S7.T2** Models
  - files: `server/whcore/analytics/models.py`, tests
  - do: logistic P(found) with games_played; Cox time-to-find (`lifelines`, censored at 80 s); priming test. Cache to `insights` only when the CI excludes no-effect; store n.
  - done: `uv run pytest -q server/tests -k models`
  - deps: T1

- [ ] **S7.T3** Strategy engine `[parallel]`
  - files: `server/whcore/analytics/strategy.py`, tests
  - do: per-length trace time and search cost from attempts; per-board max, achievable target (greedy within 80 s), biggest coachable miss; candidate recommendations from model + pattern insights ranked by est. pts/game; tracking table with a baseline; auto-retire after 3 sessions with no movement.
  - done: `uv run pytest -q server/tests -k strategy`
  - deps: T1

- [ ] **S7.T4** Strategy screen + review additions
  - do: Strategy screen (3 recommendations: gain, n, tracking since, status); achievable-target overlay in Game review.
  - done: `pnpm -C web test --run Strategy`
  - deps: T2, T3

- [ ] **S7.T5** Handoff docs `[parallel]`
  - files: `README.md`, `CONTRIBUTING.md`, `docs/RUNNING.md`
  - do: what the project is; quick start per area; free-signing setup (Signing/Config xcconfig), fixtures-only dev, no word lists in git, gate commands.
  - done: files exist; every command in them was run once (note in PROGRESS)
  - deps: —

- [ ] **S7.T6** Gate
  - done: gate PASS → mark the project v1 complete in PROGRESS; list stretch ideas (trainer mode) as backlog only
  - deps: T4, T5
