# PLAN — compact spec (source of truth for agents)

Human-readable version: the "Word Hunt Analyzer — Project Plan" doc (exported copy in
`wordhunt_docs/`). If this file and the doc disagree, this file wins for implementation;
flag the mismatch in decisions.md.

## §1 Game facts (confirmed)
- 4x4 board, 80 s timer, 8-way adjacency, each tile once per word, min 3 letters, no Qu tile.
- Scoring: 3→100, 4→400, 5→800, 6→1400, then +400 per extra letter (9→2600).
- Session = 40–50 boards. User previews each board 5–10 s and either plays all 80 s or
  LEAVES the game. Leaving voids the board: no end screen, nothing sent to the opponent.
- Board screen (during play): banner "WORDS: n" + "SCORE: s" updates live; timer pill below.
- End screen: "WORDS: n", "SCORE: s", and the TOP 15 found words with points (sorted by points
  desc, then alphabetical), followed by "(N more)". Whether "(N more)" expands is unconfirmed (S0).
  The opponent column shows "?" until the opponent plays.
- "VIEW ALL WORDS" becomes available only AFTER the opponent plays the board back, possibly hours
  later and in a different session. It lists every valid word: longest first, then alphabetical
  within each length. Unfound words are masked with one `?` per letter. Never pay to reveal.
- Device: iPhone screen 1206×2622 px (from screenshots).

## §2 Capture split
Phone (extension) records WHAT HAPPENED; server decides WHAT IT MEANS. No video leaves the phone.
Per frame (target 15–30 processed fps, drop frames when busy, ONE frame in flight):
1. Sample mean RGB of 16 tile-centre patches + ROIs: banner (words + score), timer. Coordinates come from a calibration file.
2. Classify the screen: `board` | `end` | `all_words` | `other`.
3. Board opens on its first `board` frame: save a grayscale crop of the board once and hash the tile pattern.
4. Traces: an attempt starts when any tile is selected. Record the order of `tiles_seen`, the
   release colour state (`valid_new` | `already_found` | `not_a_word`), and the banner word count after release.
5. Board closes: an `end` frame means `played` (save crops of the end-screen banner and the visible
   found-words list); leaving `board` without `end` means `skipped` (record `view_ms`).
6. `all_words` can appear in ANY capture and is NOT tied to the board just played. Emit a separate
   `AllWordsRecord`: estimate the scroll shift between frames from a 1-D row-intensity profile,
   save a grayscale crop every ~0.5 viewport, and flag a gap if shift > viewport − margin.
7. Append records to an on-disk buffer and upload directly to the server over HTTPS with retry
   and backoff. No App Groups dependency.

## §3 Server pipeline
Per BoardRecord:
1. Letters: template-match 16 tiles against 26 templates, producing a confidence per tile. Low confidence → `needs_letter_fix`.
2. Words: map `tiles_seen` → letters. Where consecutive tiles aren't adjacent, gap-fill with
   solver paths consistent with the observed subsequence and result.
3. Reconcile (played boards) → `verified` only if ALL hold: Σ accepted points == end SCORE;
   count of accepted attempts == end WORDS; every visible end-screen word ∈ accepted set
   (read with OCR, snapped to the nearest solver word; points column must match the formula).
   Otherwise `needs_review`.
4. Solve: trie DFS over the effective dictionary → every word with best path (fewest direction changes).
   Store counts per length (base list, and base ∩ ENABLE).
Per AllWordsRecord:
5. Stitch crops, split rows; mask length = count of `?`; unmasked rows = found words (OCR, snap).
   Self-checks: lengths non-increasing; within a length, rows alphabetical; end = bounce.
   Output `masked_counts_by_length`, `status` (`complete`|`partial`), `complete_down_to`
   (each length is complete once the next shorter one starts).
6. Match to a board: candidate = played boards whose accepted set ⊇ all unmasked rows and whose
   per-length found counts equal the unmasked counts per length; prefer the most recent. Unique
   match → attach; none or ambiguous → `unmatched` (kept, retried when new boards arrive).
   Boards wait in `all_words_status = pending` until a match arrives.
7. Slot matching: within a length, a masked row between two known words → candidate solver words
   that sort into that slot. Exactly one candidate → evidence "accepted"; solver words that fit no
   slot → evidence "rejected".

## §4 Event schema v1 (Pydantic; exported JSON Schema)
```
BoardRecord {
  schema: "v1", kind: "board", board_id: uuid, session_id: uuid, seq: int, device: str,
  app_version: str, calibration_version: str, opened_at: datetime, view_ms: int,
  status: "played" | "skipped",
  board_image: str, end_banner_image?: str, end_list_image?: str,
  attempts: [ { seq:int, t_start_ms:int, t_end_ms:int, tiles_seen:int[], release_state:str,
                banner_words_after?:int, confidence:float } ],
  diagnostics: { fps_processed: float, frames_dropped: int, mem_peak_mb: float }
}
AllWordsRecord {
  schema: "v1", kind: "all_words", record_id: uuid, session_id: uuid, captured_at: datetime,
  frames: str[], shifts_px: int[], gap_flags: bool[], bounced_at_end: bool
}
```
Images go up in the same multipart request; refs are filenames.

## §5 Data model (SQLite via SQLModel + Alembic)
sessions(id, started_at, ended_at, device, app_version, calibration_id, board_count)
calibrations(id, device_model, width, height, tile_centers, roi_banner, roi_timer, color_thresholds, version)
boards(id, session_id, seq, opened_at, view_ms, status, letters, letters_confirmed, board_hash,
  image_path, final_score, final_word_count, extracted_score, reconciled, end_visible_words,
  all_words_status pending|complete|partial|none, all_words_id, masked_counts_by_length,
  all_words_complete_down_to)
all_words_captures(id, session_id, captured_at, status, board_id NULL, match_state matched|unmatched|ambiguous,
  rows JSON, frames_path)
attempts(id, board_id, seq, t_start_ms, t_end_ms, tiles_seen, path, word, result, points, confidence)
board_words(board_id, word, best_path, points, found, found_at_ms, in_enable, features JSON)
board_features(board_id, max_points, word_count, count_5plus, top10_points, suffix_slots,
  vowel_count, rare_letters, predicted_score)
words(word, in_base, in_enable, in_reference JSON, status confirmed|rejected|unverified|conflict,
  accept_count, reject_count, slot_evidence, first_seen_board, zipf_freq)
dictionary_versions(id, name, sha256, uploaded_at, word_count)
insights(id, computed_at, kind, payload JSON, sample_size)

## §6 Dictionary
- Base = `dictionaries/yawl.txt` (YAWL, 264,097 words, public domain; superset of ENABLE).
  `dictionaries/enable1.txt` (ENABLE, 172,823) marks common/core words (`in_enable`).
  Normalise: lowercase a–z, 3–16 letters. Store a `dictionary_versions` row keyed by sha256.
- Evidence (2026-10-24 screenshot board LCMEORSIETRATDIM): GamePigeon accepted CLOTTER, CLOTTERS,
  LOTTER, LOTTERS, which are in YAWL but not ENABLE. YAWL finds 335 words on that board, ENABLE 251.
  So GamePigeon's list is larger than ENABLE; YAWL is the better base.
- Ledger effects: accepted + in base → confirm; accepted + not in base → add; rejected + in base →
  remove after 1 clear rejection; duplicate → no signal; slot evidence (§3.7) counts as weaker
  evidence than a trace. Seen both ways → `conflict`.
- Reference lists (wordhunt.org `/wordlist.json`, others): `tools/fetch_reference_list.py`
  downloads on demand to `$WH_DATA/reference/`, stores the ETag, and is never called at runtime.
- Per-board check: all-words counts per length vs. solver counts per length.
- Report precision = base words accepted / base words tested; recall = accepted words in base / accepted seen.

## §7 Analytics
- Per game: % of max points, length funnel, top misses by points (YAWL-only misses shown as "maybe"
  until confirmed), wasted seconds, find rate per 10 s.
- Per session: boards, keep rate, 30k+ count, skip seconds, score by board position.
- Patterns: suffix/prefix families, start-position heatmap, path shape, zipf frequency, repeat misses (3+ boards).
- Models: logistic P(found | word features + games_played); Cox time-to-find (censored at 80 s);
  priming P(find B within 5 s | found A, shared stem/path). Show an insight only if its CI excludes no-effect.
- Word features: length, points, zipf, in_enable, start class (corner/edge/centre), direction changes,
  diagonal steps, longest straight run, suffix family, prefix family, related word found, letter rarity, double letter.

## §8 Triage
- Board features (all boards) → interpretable regression of the user's score on played boards (+ session position)
  → predicted score for every board, including skipped ones.
- Grade vs. bar (default 30000): good_keep, bad_keep, missed_opportunity, good_skip.
- Outputs: scorecard, top keep signals as plain rules, threshold tuner (30k games/hour), look-time check,
  exploration goal (play out ~1 in 10 would-skip boards; shown in the summary, never mid-play).

## §9 Strategy
Points/second model from the user's trace times. Per board: theoretical max, achievable target
(greedy within 80 s), biggest coachable miss. Up to 3 ranked recommendations, each with gain (pts/game),
sample size, and tracking-since; retire one if its metric doesn't move in 3 sessions.

## §10 UX
Loop: start capture → play → stop → review. No prompts during play. Dark by default, original
tile style (no GamePigeon art), one headline sentence per screen, thumb-reachable actions,
low-sample insights muted with a sample-size badge.
Screens: Companion (start, server status, signing-expiry countdown) · Session summary ·
Board confirm (batch letter fixes) · Game review (SVG board, trace scrubber, Found/Missed/Wasted,
tap word → path) · Triage · Patterns · Strategy · Dictionary (incl. boards awaiting their
all-words list) · Settings.

## §11 Free-tier and fork rules
Free Personal Team signing (7-day profiles; re-install via Xcode, or SideStore/AltStore).
The companion app reads its own `embedded.mobileprovision` expiry and shows a countdown.
Forks set `Signing.xcconfig` (team + bundle prefix) and `Config.xcconfig` (server URL + token).
Dictionaries are committed, so server/web contributors need only the repo and fixtures.
