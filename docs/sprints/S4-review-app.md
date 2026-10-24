# S4 — MVP review app

Goal: a finished session is worth opening. Build the Session summary first.
Develop against a seeded fixture DB so no live data is needed.
gate: `uv run python tools/report.py --gate s4` → PASS (≥ 3 live sessions, ≥ 95% of played boards
verified, ≥ 90% of boards need no letter fix) AND `pnpm -C web build` succeeds.

- [ ] **S4.T1** Seed DB from fixtures `[parallel]`
  - files: `tools/seed_fixture_db.py`
  - do: build `$WH_DATA/dev.db` from fixtures (2 sessions, 12 boards) through the real worker path.
  - done: script runs; `GET /v1/sessions` on dev.db returns 2
  - deps: S3

- [ ] **S4.T2** Read API `[parallel]`
  - files: `server/app/api_read.py`, `server/tests/test_read.py`
  - do: `GET /v1/sessions`, `/v1/sessions/{id}` (summary metrics PLAN §7 per-session), `/v1/boards/{id}` (letters, conf, attempts, solver words + paths, found flags), `PATCH /v1/boards/{id}/letters` (re-solve + re-reconcile). Serve `web/dist` at `/`.
  - done: `uv run pytest -q server/tests/test_read.py`
  - deps: S3

- [x] **S4.T3** Web scaffold `[parallel]`
  - files: `web/*` (Vite React TS, vite-plugin-pwa, react-router, TanStack Query, vitest)
  - do: app shell, dark theme tokens, bottom nav, typed API client generated from FastAPI OpenAPI (`openapi-typescript`).
  - done: `pnpm -C web build && pnpm -C web test --run`
  - deps: —

- [ ] **S4.T4** Board component
  - files: `web/src/components/Board.tsx`, test
  - do: SVG 4x4 board with an original tile style; draws a path (array of tile indices) with an arrowed polyline; highlight states.
  - done: `pnpm -C web test --run Board`
  - deps: T3

- [ ] **S4.T5** Session summary screen
  - do: headline sentence, boards seen, keep rate, 30k+ count, best board, biggest miss, letter-fix count → link to the confirm screen.
  - done: `pnpm -C web test --run Summary` (renders from fixture JSON)
  - deps: T2, T4

- [ ] **S4.T6** Board confirm screen
  - do: list boards needing a letter fix; low-confidence tiles highlighted; tap a tile → letter input → PATCH.
  - done: `pnpm -C web test --run Confirm`
  - deps: T2, T4

- [ ] **S4.T7** Game review screen
  - do: board + scrubber that replays attempts in time order; tabs for Found (with times), Missed (by points), Wasted (rejected + duplicate seconds); tap a word → draw its path.
  - done: `pnpm -C web test --run Review`
  - deps: T2, T4

- [ ] **S4.T8** `[HUMAN]` Play 2 more sessions; use the app on the phone (add to Home Screen via the Tailscale URL) and note any friction in PROGRESS.
  - deps: T5, T6, T7

- [ ] **S4.T9** Gate
  - done: gate PASS; fix tasks added for any friction notes that block daily use
  - deps: T8
