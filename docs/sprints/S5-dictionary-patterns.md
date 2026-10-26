# S5 — Dictionary + patterns

Goal: a trustworthy word list and the first cross-game habits.
gate: `uv run python tools/report.py --gate s5` → PASS (≥ 5 sessions / 200+ boards; ledger has
verdicts for ≥ 500 words; precision and recall reported; ≥ 5 boards with all_words_status=complete).

- [ ] **S5.T1** Dictionary versions + upload `[parallel]`
  - files: `server/whcore/dictionary.py`, `server/app/api_dict.py`, tests
  - do: load `dictionaries/yawl.txt` (base) and `dictionaries/enable1.txt` (`in_enable` flag) at startup → normalise (PLAN §6) → `dictionary_versions` keyed by sha256; solver cache rebuilt on change. Optional `POST /v1/dictionaries` to swap in another base list. CLI `tools/load_dict.py`.
  - done: `uv run pytest -q server/tests -k dictionary`
  - deps: S4

- [ ] **S5.T2** Ledger `[parallel]`
  - files: `server/whcore/ledger.py`, tests
  - do: update `words` from attempts per §6 rules (OOV traces confirmed by the end screen or all-words counts add words — S0 found DORES, DOSAS, TASES, BAWK, TEC); backfill over all stored boards; effective dictionary = base ± ledger; precision/recall functions.
  - done: `uv run pytest -q server/tests -k ledger`
  - deps: S4

- [ ] **S5.T3** Reference lists `[parallel]`
  - files: `tools/fetch_reference_list.py`, `server/whcore/reference.py`
  - do: download on demand to `$WH_DATA/reference/<name>.json|txt` with the ETag stored; skip if unchanged; never called by the server. Fill `words.in_reference`; build the disagreement list.
  - done: `uv run pytest -q server/tests -k reference` (uses a local file, no network in tests)
  - deps: S4

- [ ] **S5.T4** All-words in the worker
  - files: `server/app/worker.py`, `server/whcore/allwords.py`
  - do: feed matched all-words captures (§3.6, matched by the revealed list-order prefix — only 20 found words are revealed) into the ledger: store counts, status, and complete-down-to on the board; per-length count gaps vs the solver; slot-match only inside the revealed stretch → confirmed / likely_rejected (evidence weaker than a trace). Backfill over all matched captures.
  - done: `uv run pytest -q server/tests -k allwords`
  - deps: T2

- [ ] **S5.T5** Pattern analytics `[parallel]`
  - files: `server/whcore/analytics/patterns.py`, `server/app/api_analytics.py`, tests
  - do: PLAN §7 per-session + patterns (families, start heatmap 4x4 counts, length funnel, find rate per 10 s, repeat misses, board-position effect). Pure functions over DB rows.
  - done: `uv run pytest -q server/tests -k patterns`
  - deps: S4

- [ ] **S5.T6** Dictionary screen
  - do: active list, precision/recall, conflicts, YAWL-vs-ENABLE disagreements resolved so far, "words to test", all-words coverage, and a "boards awaiting VIEW ALL WORDS" list (played, opponent likely done) to nudge a quick review capture.
  - done: `pnpm -C web test --run Dictionary`
  - deps: T1, T2, T3, T4

- [ ] **S5.T7** Patterns screen
  - do: headline + charts (bars for families, 4x4 heatmap reusing Board, funnel, line for find rate, session trend); sample-size badges.
  - done: `pnpm -C web test --run Patterns`
  - deps: T5

- [ ] **S5.T8** Gate
  - done: gate PASS
  - deps: T6, T7
