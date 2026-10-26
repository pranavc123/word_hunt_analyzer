# S3 — Ingest + first live session

Goal: live play → stored, processed, verified boards.
gate: `uv run python tools/report.py --gate s3` → PASS on the latest live session (no crash
record, every board arrived — seq contiguous — and ≥ 95% of played boards verified).

- [x] **S3.T1** Database `[parallel]`
  - files: `server/app/db.py`, `server/app/models.py`, `server/alembic/*`, `server/tests/test_db.py`
  - do: SQLModel tables per PLAN §5; Alembic baseline; SQLite at `$WH_DATA/wh.db`.
  - done: `uv run alembic -c server/alembic.ini upgrade head && uv run pytest -q server/tests/test_db.py`
  - deps: S1

- [x] **S3.T2** Ingest API `[parallel]`
  - files: `server/app/main.py`, `server/app/api_ingest.py`, `server/tests/test_ingest.py`
  - do: `POST /v1/boards` and `POST /v1/allwords` (multipart: JSON + images; bearer token; idempotent on board_id / record_id; images to `$WH_DATA/images/<session>/`), `GET /v1/health`, `GET /v1/sessions/latest`. Keep `/diag` from S0.
  - done: `uv run pytest -q server/tests/test_ingest.py` (posts a fixture record twice → stored once)
  - deps: S1

- [x] **S3.T3** Worker
  - files: `server/app/worker.py`, `server/tests/test_worker.py`
  - do: Huey (SqliteHuey) task per board running PLAN §3.1–3.4 with whcore; write boards, attempts, board_words; set `needs_letter_fix` / `needs_review` / `verified`; played boards start with `all_words_status = pending`. Task per AllWordsRecord running §3.5–3.7; unmatched captures are retried whenever a new played board is verified.
  - done: `uv run pytest -q server/tests/test_worker.py` (fixture board → verified; fixture all-words capture → matched to its board, even when uploaded before the board)
  - deps: T1, T2

- [ ] **S3.T4** Run-as-service
  - files: `tools/launchd/com.wordhunt.server.plist`, `tools/launchd/com.wordhunt.worker.plist`, `docs/RUNNING.md`
  - do: launchd agents with env vars and logs to `$WH_DATA/logs/`. RUNNING.md covers install, `tailscale serve --bg 8000` (App Store Tailscale: the CLI is `/Applications/Tailscale.app/Contents/MacOS/Tailscale`; Serve is already enabled on the tailnet since S0), the phone's Tailscale + "Use Tailscale DNS", and how to check health (`curl https://<mac>.<tailnet>.ts.net/v1/health`).
  - done: `plutil -lint tools/launchd/*.plist`
  - deps: T2

- [ ] **S3.T5** Debug capture toggle
  - files: `ios/WHCapture/Sources/WHCapture/Debug.swift`, `ios/App/Config.example.xcconfig`
  - do: when `WH_DEBUG=1` is compiled in, save 160-px-wide grayscale frames ±0.5 s around low-confidence events (cap 20 MB per session) and upload them with the record.
  - done: `swift test --package-path ios/WHCapture` green
  - deps: S2

- [ ] **S3.T6** `[HUMAN]` First live session (~50 min)
  - Install the services (RUNNING.md). The agent builds and installs the app (`xcodebuild … -allowProvisioningUpdates` + `xcrun devicectl device install app`); the user turns on Tailscale on the phone, opens Word Hunt (server reachable), taps Start / stop capture → Start Broadcast, turns on the Focus, plays a normal session, then stops.
  - deps: T3, T4, T5

- [ ] **S3.T7** Live analysis + fixes
  - files: `tools/report.py` (`--gate s3`)
  - do: run the gate; for each failure, look at the debug frames numerically first, add fix tasks, and re-run on the stored records (the worker can reprocess).
  - done: gate PASS (if a fix touches the state machine, update the oracle, the Swift port, and fixtures together)
  - deps: T6
