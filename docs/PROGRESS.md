# PROGRESS

Current sprint: **S3** → `docs/sprints/S3-ingest-live.md`

| Sprint | Status | Gate |
| --- | --- | --- |
| S0 Bootstrap + feasibility | done | PASS 2026-10-26 |
| S1 Core + oracle | done | PASS 2026-10-26 |
| S2 Capture app | done | PASS 2026-10-26 |
| S3 Ingest + live | in progress | — |
| S4 Review app | todo | — |
| S5 Dictionary + patterns | todo | — |
| S6 Triage | todo | — |
| S7 Perception + strategy | todo | — |

## Done tasks
<!-- one line each: S0.T1 ✓ <date> — note (≤2 lines) -->
- S0.T1 ✓ 2026-10-24 — repo root = ~/Projects/wordhunt (clone's .git moved up); uv on Python 3.15; words_small = 335 board words + 80 random YAWL.
- S0.T2 ✓ 2026-10-24 — solver matches measurements (YAWL 335/262,800; ENABLE 251/196,500), ~10 ms/solve.
- S0.T3 ✓ 2026-10-24 — schema v1 exported to fixtures/schema/v1.json; examples in fixtures/schema/*_example.json.
- S0.T4 ✓ 2026-10-24 — calibration in fixtures/calibration/iphone-1206x2622.json; seed templates in $WH_DATA/templates/seed.npz.
- S0.T14 ✓ 2026-10-24 — probe builds unsigned; server has GET /v1/health + POST /diag (Bearer WH_TOKEN if set).
- S2.T1 ✓ 2026-10-24 (early) — Swift Codable models + SchemaTests on fixtures/schema examples; picks up fixtures/expected/*.json automatically.
- S4.T3 ✓ 2026-10-24 (early) — Vite+React 19 PWA shell, dark tokens, 5-tab bottom nav, typed openapi-fetch client; 3 vitest tests.
- S0.T6 ✓ 2026-10-26 — samples.csv.gz for session1 + allwords1 (streamed, no PNG dump); video resting RGB (247,209,151) added to calibration.
- S0.T7 ✓ 2026-10-26 — session1: 21 boards (6 played, 15 skipped; count < 35 because session is 10 min); allwords1: 6 played + 6 all-words captures. review.html built.
- S0.T8 ✓ 2026-10-26 — user labelled all 27 boards.
- S0.T10 ✓ 2026-10-26 — LOBO 99.55%; digit templates read SCORE/WORDS on all 12 played boards (live == end).
- S0.T9 ✓ 2026-10-26 — traces for 12 played boards; accepted (WORDS rise at release) == end WORDS on 12/12.
- S0.T11 ✓ 2026-10-26 — 11/12 played boards verified; OOV words accepted by the game: DORES, DOSAS, TASES.
- S0.T12 ✓ 2026-10-26 — 6/6 all-words captures matched; game list ≈ YAWL (+BAWK, TEC); only first 20 found words revealed; max tracked shift 1423 px/frame.
- S0.T13 ✓ 2026-10-26 — 15 fps: segmentation + all-words identical; traces 7/12, reconciliation 1/12 → need 30 fps in play.
- S0.T15 ✓ 2026-10-26 — 31-min device run: 8.3 MB peak, ~60 fps, 10 drops; buffers 884×1920 420f.
- S0.T16 ✓ 2026-10-26 — tools/report.py --gate s0 → PASS (GO recorded in measurements.md).
- S1.T1 ✓ 2026-10-26 — sample contract (fixtures/samples/README.md) + `words` and `list_shift`; Sampler class; samples re-extracted.
- S1.T2 ✓ 2026-10-26 — streaming state machine (machine.py): 27/27 statuses, 1490/1491 attempts = S0 traces, 12/12 accepted == WORDS; 0.2 s per recording.
- S1.T3 ✓ 2026-10-26 — 6 fixture segments (4 played, 2 skipped, 2 all-words) + expected + labels.json; fixtures 1.7 MB (PNG→JPEG).
- S1.T4 ✓ 2026-10-26 — read_letters/build_words/reconcile/process_allwords on fixtures; phone-style crops reproduce S0 all-words counts 6/6; coverage ≥ 84%.
- S1.T5 ✓ 2026-10-26 — .github/workflows/ci.yml (python: ruff+schema+pytest+fixture size; web: test+build; swift: WHCapture tests); actionlint clean.
- S1.T6 ✓ 2026-10-26 — gate s1 PASS: oracle 27/27 vs labels, fixtures 1.47 MB, CI green (python, web, swift) on a700610.
- S2.T2 ✓ 2026-10-26 — Machine.swift (+ Screens, TileStates, uuid5): output identical to Python on all 6 fixtures (records + crops).
- S2.T3 ✓ 2026-10-26 — Sampler.swift (BGRA + 420f, matrix-aware, scaled rects, ROI stride 2, optional profile), DigitReader (exact on 5 crops), parity ±2 vs Python.
- S2.T4 ✓ 2026-10-26 — CropStore (live + ring crops, JPEG), RecordQueue (atomic, ordered, idempotent), Uploader (multipart, bearer, backoff); 7 tests; crop refs now .jpg.
- S2.T5 ✓ 2026-10-26 — extension wired: Sampler(420f, phone states) → Machine → CropStore → RecordQueue → Uploader; diag adds ROI sample + queue; iOS build OK.
- S2.T6 ✓ 2026-10-26 — companion app: health, last-session line (S3 endpoint), signing countdown (Provisioning parser, 4 tests), Tailscale/Focus reminders. Uploader: 404/405 retry; queue key 64-bit fix.
- S2.T7 ✓ 2026-10-26 — gate s2 PASS: 25 Swift tests (machine + sampler parity), iOS build OK. Phone thresholds provisional until the S3 live session.
- S3.T1 ✓ 2026-10-26 — SQLModel tables (PLAN §5 + worker fields), Alembic baseline, SQLite WAL at $WH_DATA/wh.db.
- S3.T2 ✓ 2026-10-26 — POST /v1/boards + /v1/allwords (multipart, bearer, idempotent → 200 duplicate), images under $WH_DATA/images/<session>/, GET /v1/sessions/latest.

## Blockers / waiting on human
<!-- [HUMAN] items currently blocking, with what's needed -->
