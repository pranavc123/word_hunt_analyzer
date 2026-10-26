# PROGRESS

Current sprint: **S0** → `docs/sprints/S0-bootstrap-feasibility.md`

| Sprint | Status | Gate |
| --- | --- | --- |
| S0 Bootstrap + feasibility | in progress | — |
| S1 Core + oracle | todo | — |
| S2 Capture app | todo | — |
| S3 Ingest + live | todo | — |
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

## Blockers / waiting on human
<!-- [HUMAN] items currently blocking, with what's needed -->
- S0.T8: label ≥8 boards in $WH_DATA/labels/review.html → boards.csv (unblocks T9–T13). S0.T15 device run needs Signing.xcconfig + Config.xcconfig.
