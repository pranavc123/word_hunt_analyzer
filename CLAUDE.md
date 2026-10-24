# Word Hunt Analyzer — agent guide

Personal analytics for GamePigeon Word Hunt (4x4, 80 s). An iOS broadcast extension
watches live play and emits compact per-board events. A Python server reads letters,
reconciles scores, solves boards, and runs analytics. A React PWA shows the results.
Spec: `docs/PLAN.md`. Read only the section a task cites (`§N`).

## Every session
1. Read `docs/PROGRESS.md`, then ONLY the current sprint file in `docs/sprints/`.
2. Take the first unchecked task whose `deps` are done and whose inputs exist. Skip
   `[HUMAN]` tasks and tasks whose input files are missing: tell the user exactly what to
   do (one short list), then continue with other unblocked tasks. If none are left, stop.
3. Implement → run the task's `done:` command → fix until it passes.
4. Commit once per task: `S<n>.T<m>: <summary>`.
5. In `docs/PROGRESS.md`: tick the task and add at most 2 lines of notes or blockers.
6. For a choice not covered by `docs/PLAN.md`, pick the simplest option, log it in
   `docs/decisions.md` (1–3 lines), and keep going. Ask the user only if the choice is
   irreversible, changes the event schema, or costs money.
7. At sprint end, run the sprint's `gate:` check. If it passes, set the next sprint as
   current in PROGRESS.md. If it fails, add fix tasks to the current sprint.

## Token and time rules
- Never read video files or dump large images. Analyze frames numerically (mean colours,
  row profiles, CSV summaries). View at most 2 small crops per task, only when a task allows it.
- Find code with `rg` or glob. Read files in ranges. Don't print files over 200 lines.
- Run tests quietly (`-q`) and paste only failures.
- Keep committed fixtures under 2 MB in total. Real data lives in `$WH_DATA` (git-ignored).
- Write the smallest implementation that passes. No speculative abstractions or plugin layers.
- `[parallel]` tasks touch disjoint files and can run in separate sessions or worktrees.
  Nothing else should run in parallel.
- Reuse earlier output: read numbers already measured from `docs/measurements.md`
  instead of re-measuring.

## Repo layout (repo root = ~/Projects/wordhunt)
```
server/whcore/   pure Python library: schema, scoring, solver, oracle, recognition, analytics
server/app/      FastAPI app + worker (imports whcore)
server/tests/    pytest, using /fixtures
ios/WHCapture/   SwiftPM package holding ALL capture logic; builds and tests on macOS
ios/App/         XcodeGen spec + CompanionApp + BroadcastExtension (thin wrappers only)
web/             React + Vite + TypeScript PWA
tools/           CLI scripts (frame extraction, labelling, reference-list fetch, reports)
dictionaries/    yawl.txt (base) + enable1.txt (common-word marker), public domain, committed
fixtures/        small committed test data
docs/            PLAN.md, PROGRESS.md, decisions.md, measurements.md, sprints/
wordhunt-data/   = $WH_DATA: recordings, screenshots, labels, images, DB. Git-ignored. Never commit.
wordhunt_docs/   the user's exported plan doc (reference only; docs/PLAN.md wins)
```

## Commands
- Python: `uv sync` · `uv run pytest -q server/tests` · `uv run ruff check --fix server tools`
- Swift logic: `swift test --package-path ios/WHCapture`
- iOS compile: `xcodegen generate --spec ios/App/project.yml && xcodebuild -project ios/App/App.xcodeproj -scheme CompanionApp -destination 'generic/platform=iOS' -quiet build`
  (the `.xcodeproj` is generated and not committed; edit `project.yml`, never the project file)
- Web: `pnpm -C web install` · `pnpm -C web test --run` · `pnpm -C web build`
- Server: `uv run uvicorn app.main:app --app-dir server --reload`
- Gates: `uv run python tools/report.py --gate s<N>`

## Invariants (never break)
- The event schema lives in `server/whcore/schema.py` (Pydantic) and is exported to
  `fixtures/schema/v1.json`. Swift models must match it. Changing it means bumping the
  version and asking the user first.
- Tiles are indexed row-major 0–15, with 8-way adjacency, and each tile is used at most once per word. 26 letters, no "Qu" tile.
- Score(n) = {3:100, 4:400, 5:800, 6:1400}; for n ≥ 7, 1400 + 400·(n−6). Words of 3–16 letters.
- `WHCapture` must not import UIKit or ReplayKit, so `swift test` runs on macOS.
- Dictionaries: base = `dictionaries/yawl.txt`; `dictionaries/enable1.txt` only marks common
  words. Both are public domain and committed. Third-party lists (wordhunt.org, etc.) are
  fetched to `$WH_DATA/reference/` and never committed. Unit tests use `fixtures/words_small.txt` for speed.
- No paid Apple services. Signing uses a free Personal Team via the git-ignored
  `ios/App/Signing.xcconfig`; server URL and token via the git-ignored `ios/App/Config.xcconfig`.
- Config comes from env vars: `WH_DATA` (data dir), `WH_DICT` (base list path), `WH_TOKEN` (upload auth).
