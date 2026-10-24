# S6 — Triage coaching

Goal: grade every keep/skip call against the user's bar (default 30000). PLAN §8.
gate: `uv run python tools/report.py --gate s6` → PASS (predictor cross-validated MAE reported;
scorecard computed for every session; keep signals have n ≥ 30 each).

- [ ] **S6.T1** Board features `[parallel]`
  - files: `server/whcore/analytics/board_features.py`, tests
  - do: compute and store `board_features` for all boards (backfill + in worker).
  - done: `uv run pytest -q server/tests -k board_features`
  - deps: S5

- [ ] **S6.T2** Score predictor
  - files: `server/whcore/analytics/predictor.py`, tests
  - do: ridge regression (statsmodels/sklearn) on played boards; features + session position; 5-fold CV MAE logged to measurements.md; predict all boards; refit on each new session.
  - done: `uv run pytest -q server/tests -k predictor`
  - deps: T1

- [ ] **S6.T3** Grading + signals
  - files: `server/whcore/analytics/triage.py`, tests
  - do: four-way grades; scorecard per session; top keep signals as plain-language rules (thresholded single features, with n and lift); threshold tuner (30k games/hour); look-time check; exploration goal.
  - done: `uv run pytest -q server/tests -k triage`
  - deps: T2

- [ ] **S6.T4** Triage API + screen
  - do: `GET /v1/triage?session=` ; screen with headline, predicted-vs-actual scatter (kept), missed-opportunity list → game review, keep-signal rules, exploration goal also in Session summary.
  - done: `pytest -k triage_api` and `pnpm -C web test --run Triage`
  - deps: T3

- [ ] **S6.T5** Gate
  - done: gate PASS
  - deps: T4
