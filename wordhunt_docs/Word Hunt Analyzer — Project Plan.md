# Word Hunt Analyzer — Project Plan

Oct 23, 2026 · @Pranav

## Summary

Build a personal Word Hunt analytics system that captures whole play sessions: one tap at the start, one at the end, with no per-game recording and no video uploads. A small iOS companion app uses a screen-broadcast extension to watch the game live and turn every board into compact event data, which syncs to a server. A web app then shows what you miss, how well you triage boards, and how to score more.

**Refined goal, in four outcomes:**

1. **Every board becomes data automatically.** Each of your 40–50 boards per session is logged with its letters, whether you played it out or skipped it, and how long you looked. Played boards also log every word you traced (accepted, rejected, or duplicate) with its path and timestamp. Played games must reconcile exactly with the final score.
2. **Board triage becomes measurable.** Your 5–10 second keep-or-skip call is a decision the app can grade: how often kept boards reach your 30k bar, and how often skipped boards likely would have.
3. **You see your blind spots.** You get per-game missed-word reports, plus a model of which words you find. It factors in length, position on the board, path shape, word frequency, and suffix family.
4. **The dictionary becomes trustworthy.** Your uploaded NWL list is the starting point, and every accept or reject observed in play corrects it.

**What success looks like after \~5 sessions (200+ boards):** boards are extracted with no manual fixes in 95%+ of cases. Played games reconcile with the final score 98%+ of the time. The app can say how accurate your triage is and name your top three costly habits, each with a points-per-game estimate.

## Constraints and the decisions they force

Per-game recording is out. With 40–50 boards a session, most skipped within 5–10 seconds, starting and stopping a recording for each board is impossible, and trimming clips by hand is worse. Capture must run once per session, find board boundaries on its own, and never ship raw video.

| Constraint | Decision it forces |
| --- | --- |
| 40–50 boards per session, many skipped after 5–10 s | Capture runs for the whole session from one tap. Software detects where each board starts and ends, and whether you played it out or skipped it. |
| A whole-session video would be very large, and uploading or trimming it would kill the habit | Process frames live on the phone and keep only events: tile states, timings, and one small image per board. That's tens of kilobytes per board, not gigabytes per session. |
| An iOS web app can't see another app's screen | Build a native iOS companion app with a ReplayKit **Broadcast Upload Extension**, the iOS mechanism that lets an app receive live screen frames. The web app stays, for review and analysis. |
| The broadcast extension has a hard memory limit of about 50 MB and is terminated if it goes over | The extension only does cheap work: it samples pixel colors at 16 tile centers and a few small regions, and drops frames when busy. Heavy work (letters, solving, models) runs on the server. |
| Installing your own app needs Xcode on a Mac, and free signing expires every 7 days | Stay on free Personal Team signing for good. Re-install from Xcode weekly (about a minute), or let SideStore or AltStore refresh it over Wi-Fi. The companion app counts down to expiry. The extension uploads its own events, so nothing depends on capabilities free signing may lack, such as App Groups. |
| GamePigeon's word list isn't published | Start from the NWL list you upload. Compare it offline with reference lists such as wordhunt.org's, and let every accept or reject observed in play settle the differences. |
| Confirmed rules: 80-second timer; 3 letters = 100, 4 = 400, 5 = 800, 6 = 1400, then +400 per extra letter (7 = 1800, 8 = 2200, 9 = 2600, …) | Hardcode it as a formula and use it to check extraction. |

Focus mode still matters, because a notification banner over the board corrupts frames. The companion app reminds you when you start a session.

## System architecture

Use three parts: a native capture app on the phone, a Python server for recognition and analysis, and a web app for review. The phone does only what has to happen live, so the server never receives video.

&#91;embedded content: system architecture · phone, server, storage\]

Events move down the right column. Played boards are saved only after their points match the final score; skipped boards have no score to check and are saved as they are.

| Layer | Choice | Why |
| --- | --- | --- |
| Capture | Swift iOS app + ReplayKit Broadcast Upload Extension, sampling pixels with Core Video and Accelerate | The only way to watch GamePigeon live. Sampling 16 points per frame fits the memory limit. |
| Phone storage and sync | The extension buffers events in its own storage and uploads each board's record directly over HTTPS | Works with free signing (no App Group needed), and nothing is lost when offline |
| API | FastAPI (Python) | Same language as the vision and stats code |
| Recognition | OpenCV + NumPy on board and score images | Runs on a couple of stills per board, not on video |
| Solver and stats | Python trie solver; pandas, statsmodels, scikit-learn, lifelines | Interpretable models whose coefficients are the insight |
| Database | SQLite via SQLModel | Single user, single file, easy backup and export |
| Review UI | React + Vite + TypeScript PWA, board drawn in SVG | Fast to iterate; works on phone and laptop, and the companion app can open it in a web view |
| Hosting and access | Your Mac or a small VPS, reached privately through Tailscale | No public accounts or auth system to build |

**Alternatives considered**

- **Whole-session screen recording, auto-imported to a Mac.** Record with Control Center; iCloud Photos syncs the clip, and a watcher on the Mac (e.g. osxphotos) processes it. It needs no Xcode and keeps video for reprocessing, but the files are huge, fill iCloud storage, and need the Mac awake. Use it as the spike's data source and as the fallback.
- **Streaming board crops to the server.** The extension would send downscaled crops at \~10 fps, avoiding computer vision in Swift. But it costs bandwidth and battery for 40+ minutes and fails offline.
- **Recording each game separately:** rejected, because it doesn't fit how you play.

## Capture and extraction pipeline

The work splits at the phone. The extension runs a small state machine on live frames and records *what happened*; the server works out *what it means*. Everything on the phone is pixel sampling at fixed coordinates, which is cheap enough for the memory limit and simple to prototype in Python first.

**On the phone (broadcast extension), for each frame:**

1. **Sample.** Read the mean color of 16 tile-center patches, plus small regions for the score, timer, and word banner. Coordinates come from a one-time calibration. When the extension falls behind, it skips frames; 15–30 processed frames per second should be enough, and the spike will confirm it.
2. **Classify the screen.** Label each frame as board in play, end screen, or other (iMessage, menus). The first in-play frame opens a board; leaving that state closes it.
3. **Capture the board once.** On the first clean in-play frame, save a small grayscale crop of the board for letter recognition on the server. Hash the tile pattern so the same board isn't logged twice.
4. **Record traces.** When any tile turns selected, an attempt starts. Log the order in which tiles light up, plus their color state on the last frame before release (valid-new, already-found, or not-a-word).
5. **Close the board.** If the end screen appears, save crops of the final score and the found-words list and mark the board *played*. If you leave before the 80 seconds are up, mark it *skipped* and record the viewing time. Leaving voids the board in GamePigeon, so a board that closes without an end screen is always a skip.
6. **Write and send events.** Append one JSON record per board to a small buffer in the extension's own storage, then upload it straight to the server. Failed uploads stay buffered and retry. This avoids depending on App Groups, which free signing may not support.

**On the server, for each board:**

7. **Read letters.** Template-match the 16 tiles from the board crop against 26 single-letter templates (there's no Qu tile). Templates bootstrap from a few hand-confirmed boards. Low-confidence tiles prompt a one-tap fix in the web app, batched per session.
8. **Build words.** Map each trace's tile path to letters. If a fast swipe skipped a tile between frames (consecutive tiles that aren't adjacent), fill the gap with the solver's valid paths that fit the trace and its result.
9. **Reconcile played boards.** Accepted points under the confirmed scoring table must equal the final score read from the end-screen crop. The end screen also lists the words you found, so the accepted attempts must match that list word for word. When both checks pass, the board is marked verified; any mismatch flags it for review.
10. **Solve and store.** Run the trie solver over the board (played and skipped alike), join its output to the traces, and save.

**Why reconciliation matters:** it's a free, exact correctness check on every played game. It also catches GamePigeon UI changes the moment they break extraction.

**Prototype in Python, then port.** Write the phone-side state machine in Python against one ordinary screen recording of a full session, and check it against hand labels. Then port the proven logic to Swift. Keep the Python version as a test oracle: run both on the same recording and diff their events. A debug toggle in the companion app saves low-resolution frames around uncertain moments, so failures can be inspected without full video.

## Dictionary and verification ledger

Treat the dictionary as a hypothesis that every game tests. Start from a base list, then keep a per-word ledger of what GamePigeon actually accepted or rejected. The "effective dictionary" used for missed-word reports is the base list, corrected by the ledger.

**Base list: NWL, uploaded by you.** Upload it in the web app's Dictionary settings as a plain text file with one word per line. NWL is NASPA's copyrighted list, so keep it on your machine and never commit it. The server normalizes it (uppercase, letters only, 3–16 letters, since a 4×4 board can't hold longer words). It's stored as a versioned base list, so a newer or different list can be swapped in and compared later. Add a word-frequency score per word (for example, the Python `wordfreq` package) to separate common words from obscure ones. Frequency is one of the strongest predictors of what you miss.

**How each attempt updates the ledger:**

| Observed | Word in base list? | Ledger effect | What it tells you |
| --- | --- | --- | --- |
| Accepted | Yes | +1 confirmed | Base list agrees |
| Accepted | No | Flag **missing from base** | Add to effective dictionary |
| Rejected (not-a-word color) | Yes | Flag **base false positive** | Remove from effective dictionary after 1 clear rejection |
| Rejected | No | +1 confirmed absent | Base list agrees |
| Already found | Either | No dictionary signal | Counts as wasted time only |

**Word status values:** `confirmed`, `rejected`, `unverified`, `conflict` (seen both ways, which usually means a pipeline bug). Every missed-word report shows how many of its words are verified versus assumed. That way you know when a "miss" might not even be playable.

**Speeding up verification.** You can only test words that appear on boards you get. A Dictionary screen lists the unverified words on your current board's solution, so you can deliberately try obscure ones in casual games. Track coverage weighted by frequency: verifying the 20k most common words matters far more than the obscure tail.

**Accuracy metrics to report:** precision (base words GamePigeon accepts / base words tested) and recall (game-accepted words in base / game-accepted words seen). If precision falls below \~97%, switch which base list you use.

**Reference lists, fetched once and never at runtime.** wordhunt.org has no dictionary API. Its solver downloads one static file, `wordhunt.org/wordlist.json`: a plain JSON array of about 198k lowercase words (2.9 MB, including 1–2 letter words), and solves boards in the browser. A small manual script, `fetch_reference_list`, downloads such a list on demand into a git-ignored folder and records its ETag so it can be refreshed occasionally. The pipeline only reads the local copy. Open-source solver repos on GitHub use other lists (for example, dwyl/english-words), and those can be added the same way.

**How reference lists are used:**

- **Disagreement words become priority tests.** Words in your Scrabble list but not the reference list, or the reverse, top the "words to try" list, since they're the likeliest to be wrong.
- **A second opinion, not ground truth.** Third-party lists are other people's guesses too. Only GamePigeon's own accept or reject settles a word's status.
- **Personal use only.** The site states no license for its list, so don't commit or redistribute it. If you lean on it heavily, ask the site's author first; the About page lists a contact.

**GamePigeon's own word count, from the "More words" view.** The end screen can list every valid word on the board, with the ones you didn't find masked as ???. You never pay to reveal anything, but the masks may still say a lot. The spike confirms how much:

- **If a mask shows the word's length**, the count of valid words at each length is GamePigeon's exact answer for that board. Compare it with the solver's count per length. A gap means your NWL-based list has extra or missing words of that length on this board.
- **If the list is sorted alphabetically**, each masked entry sits between two words you found. Usually only one or two solver candidates of the right length fit that slot, which pins down which words GamePigeon accepts.
- **It costs one tap per board.** Open "More words" (and scroll if the list is long) on the boards you choose. The extension is already watching, so it captures the list with no extra step.

This turns dictionary verification from "wait until I happen to trace that word" into a check on every reviewed board. The effective dictionary should then converge within a few sessions instead of months.

## Data model

Store events, not conclusions. Keep the raw facts (every board, every trace, every possible word) and compute missed words, features, triage grades, and stats from them. That way, a better dictionary or model can recompute your whole history.

| Table | Key columns | Notes |
| --- | --- | --- |
| `sessions` | id, started\_at, ended\_at, device, app\_version, calibration\_id, board\_count | One row per broadcast |
| `calibrations` | id, device\_model, width, height, tile\_centers, roi\_score, roi\_timer, roi\_banner, color\_thresholds, version | One active row per device and GamePigeon UI version |
| `boards` | id, session\_id, seq\_in\_session, seen\_at, view\_ms, status (`played`/`skipped`), letters, letters\_confirmed, board\_hash, image\_path, final\_score, extracted\_score, reconciled, end\_screen\_words, masked\_counts\_by\_length | Every board you saw, played or not |
| `attempts` | id, board\_id, seq, t\_start\_ms, t\_end\_ms, tiles\_seen (int\[\]), path (int\[\]), word, result (`accepted`/`rejected`/`duplicate`), points, confidence | `tiles_seen` is raw, `path` is gap-filled |
| `board_words` | board\_id, word, best\_path, points, found, found\_at\_ms, features (json) | Solver output, skipped boards included |
| `board_features` | board\_id, max\_points, word\_count, count\_5plus, top10\_points, suffix\_slots, vowel\_count, rare\_letters, predicted\_score | Inputs and output for triage |
| `words` | word, in\_base, in\_reference (per list), status, accept\_count, reject\_count, first\_seen\_board, zipf\_freq | The verification ledger |
| `dictionary_versions` | id, name, uploaded\_at, word\_count | Your uploaded base lists |
| `insights` | id, computed\_at, kind, payload (json), sample\_size | Cached findings |

**Volume:** a session is roughly 45 boards × \~200 solver words, so about 10k word rows. SQLite handles years of that comfortably.

**Feature fields per board word** (the perception model's input): length, points, zipf frequency, start tile class (corner, edge, or center), path direction changes, diagonal steps, longest straight run, suffix family (`-S`, `-ED`, `-ER`, `-ING`, `-Y`, none), prefix family (`RE-`, `UN-`, …), whether a related shorter or longer word was found, letter rarity, and whether it has a double letter.

## Analytics and the perception model

Two datasets now grow at once: every board, played or skipped, feeds triage; every playable word on played boards feeds perception. At 40–50 boards a session, data piles up in days, not months. Engineering, not data, now limits the analytics phases.

**Level 1: per game (from the first session)**

- Score, % of available points captured, and words found versus available by length (a length funnel)
- Top missed words ranked by points, each with its path drawn on the board
- Seconds lost to rejected and duplicate attempts
- Find rate across the 80 seconds, in 10-second buckets

**Level 1b: per session (from the first session)**

- Boards seen, keep rate, mean score of kept boards, and count of 30k+ games
- Total seconds spent looking at boards you skipped
- Score by board position in the session, which shows warm-up and fatigue

**Level 2: patterns across games (from \~2–3 sessions)**

- **Missed families:** find rate by suffix and prefix family, e.g. "you found PLAY but missed PLAYS 64% of the time" (illustrative)
- **Spatial bias:** heatmaps of where your traces start versus where high-value words start, which reveals neglected rows and corners
- **Path shape:** find rate by direction changes and diagonal steps
- **Familiarity:** find rate by word frequency, which separates "didn't see it" from "didn't know it"
- **Repeat misses:** words available on 3+ boards that you never found, which makes a personal study list

**Level 3: the model (from \~3–5 sessions, depending on your keep rate)**

- **Found-or-missed:** logistic regression on the word features, P(found | word, board). Its coefficients *are* the insight. Add a term for games played to measure learning over time.
- **Time to find:** a survival model (Cox, via `lifelines`) on found\_at\_ms, with misses censored at 80 s
- **Priming:** P(find word B within 5 s | just found word A) when A and B share a stem or path

Refit on each session upload, which takes seconds at this scale. Show an insight only when its confidence interval excludes "no effect," and always show its sample size.

## Strategy feedback engine

Feedback has two kinds of "optimal." The theoretical optimum for a board (every word) needs only the solver and works from game 1. A *personal* optimal strategy needs your data: it accounts for how fast you trace, what you reliably see, and what that costs. Lead with the personal one, because "find all 212 words" isn't advice.

**Core idea: points per second.** With the confirmed scoring, a 6-letter word (1400) is worth fourteen 3-letter words (100 each). Your data supplies the other side of the trade: seconds to trace each length, and seconds of searching per find at each length. From those, the engine computes your expected points per second for each tactic.

**Per-board review (from game 1):**

- **Theoretical maximum** and your % of it
- **Achievable target:** a greedy plan that uses your measured trace times to pick the highest-value words that fit in the round. It shows what a realistic great game on this board looked like.
- **Biggest single miss:** the highest-points word that your model rated likely findable (high P(found) features), which marks the most coachable miss

**Personal strategy insights (from \~50 games)**, each stated with its estimated points per game (numbers below are illustrative):

- **Suffix sweep:** "After any word, try +S / +ED / +ER on the same path. You miss these 60% of the time, worth \~900 pts/game."
- **Region neglect:** "You start 8% of traces in the bottom row, which holds 25% of available points."
- **Wasted time:** "Rejected and duplicate traces cost 11 s per game. Skip guesses you're unsure of before the 60-second mark."
- **Pacing:** "Your find rate drops 40% after 50 s. Switch to short, sure words in the last 20 s." Test this against your own data before recommending it.
- **Study list:** high-frequency, high-value words you've missed 3+ times

**Keep the engine honest.** Every recommendation shows its sample size and the estimated gain. Once you act on one, the app tracks whether that metric actually moved over your next 20 games, so advice that doesn't pay off gets retired.

**Stretch: a trainer mode.** The app has a solver, a dictionary, and your weakness model, so it can generate practice boards that over-represent your weak patterns. You play them in-app with the same 4×4 swipe mechanic, and they feed the same dataset.

## Board triage coaching

Your 5–10 second keep-or-skip call is the highest-leverage decision in a session. Every skipped board can still be scored after the fact, because the solver sees the whole board. So treat triage as a prediction the app can grade.

**How it works**

1. **Describe every board.** From the solver: total points available, the number of 5+ letter words, points in the top 10 words, open suffix slots (-S, -ED, -ER, -ING), vowel count, rare letters, and how clustered the valuable letters are.
2. **Predict your score on it.** Fit a regression of your actual scores on played boards against those features, plus your position in the session. That gives an expected score for every board, including ones you skipped.
3. **Grade each call against your 30k bar.** Each board lands in one of four outcomes: a good keep (kept, reached 30k), a bad keep (kept, fell short), a missed opportunity (skipped, predicted 30k+), or a good skip (skipped, predicted under).

**What you get**

- **A triage scorecard per session:** the share of keeps that reached 30k, estimated missed 30k boards, and total seconds spent on skips
- **Your personal keep signals:** the 3–5 board features that best predict a 30k game for you, written as rules you can check in 5 seconds. These are learned from your data, not assumed.
- **A threshold tuner:** given your skip time and score distribution, the keep rule that maximizes 30k games per hour of play
- **A look-time check:** whether deciding at 8 seconds is actually more accurate than deciding at 4

**One caveat: selection bias.** If you only play boards you like, the model never learns how you score on the boards you skip. To fix it, the app can suggest occasionally playing out a board you'd normally skip, about 1 in 10, which gives the predictor honest data across the full range of board quality.

## UX and screen design

Design around the session, not the game: **start capture → play as usual → stop → review.** During play, the app asks for no attention at all. Afterward, the first screen should land a useful insight in under a minute.

**Design principles**

- **Zero touch during play:** no prompts, overlays, or per-board actions. Corrections wait for the session summary and come as one batch.
- **Board-centric:** the 4×4 board is the main visual on every game screen, and words appear as paths drawn on it.
- **One headline per screen:** each screen leads with one sentence, like "3 of your 11 skips looked like 30k boards."
- **Thumb-first and dark by default:** primary actions sit in the bottom third, with large tap targets.
- **Original visual identity:** use your own tile style, colors, and type. Don't copy GamePigeon's art or branding.
- **Honest uncertainty:** unverified words and low-sample insights appear muted, with a sample-size badge.

| Screen | Purpose | Key elements |
| --- | --- | --- |
| Companion app (native) | Start and stop capture | Start session button (opens the system broadcast picker; Control Center works too), Focus reminder, live board count, upload queue status, calibration |
| Session summary | First stop after a session | Boards seen, keep rate, 30k+ count, triage scorecard, best board and biggest missed opportunity, any letter fixes needed |
| Board confirm | Fix recognition errors fast | Only boards with low-confidence tiles, all at once. Tap a tile and type the letter. |
| Game review | Learn from one game | Board with a scrubber that replays traces in order. Tabs for Found, Missed (by points), and Wasted. Tap a word to draw its path. |
| Triage | Learn your keep signals | Predicted vs. actual score for kept boards, missed-opportunity boards to replay, and your keep rules |
| Patterns | See habits across games | Missed families, start-position heatmap, length funnel, find rate over 80 s, repeat-miss study list |
| Strategy | Know what to change | 3 ranked recommendations, each with gain (pts/game), sample size, and a "tracking since" status |
| Dictionary | Trust the word list | Upload or replace your base list, precision and recall, conflicts, words to try on upcoming boards |
| Settings | Rare housekeeping | Recalibrate, debug capture toggle, data export |

**Prototype the Session summary and Triage screens first.** They carry the product's value now. If they don't feel worth opening after a session, pipeline accuracy won't fix that.

## Roadmap

Build in six gated phases, and prove live capture before anything else. Because a session yields 40–50 boards, the analytics phases unlock within a few sessions of the MVP rather than months.

&#91;embedded content: roadmap · 6 phases, 5 gates\]

The new critical path is Phases 0–1: if the broadcast extension can't hold a full session, switch to the session-recording fallback before writing any UI. Keep the spike's full-session recording permanently, as the regression test for every change to the capture logic.

## Contributing without paying

No one needs the paid Apple Developer Program to build, run, or improve this project. Each contributor signs the iOS app with their own free Apple ID, and most contributions need no Apple account at all.

| Contribution area | What they need | Cost |
| --- | --- | --- |
| iOS capture app (extension, companion app) | A Mac with Xcode, an iPhone, a free Apple ID | Free; re-install every 7 days |
| Server, solver, recognition, analytics | Python and the recorded fixtures in the repo | Free; no Apple account or iPhone |
| Web app (review UI) | Node and the same fixtures | Free |
| Dictionary tooling | Their own word lists, fetched or uploaded locally | Free |

The paid program only matters for handing a ready-built app to people who won't build it themselves (TestFlight or the App Store). That isn't part of this plan.

**Repo setup that keeps it free:**

- **Signing in one ignored file.** `Signing.xcconfig` holds the developer team and bundle ID prefix, and the repo commits `Signing.example.xcconfig`. Bundle IDs must be unique per Apple ID, so each fork sets its own prefix without touching the Xcode project file.
- **Configurable server address.** The companion app and extension read the server URL from settings, so a fork points at its own server.
- **Fixtures in the repo.** A few recorded sessions are stored as event JSON, board images, and expected outputs. Server and web contributors can test without a phone, and the Python oracle diffs against them in CI.
- **No licensed word lists in the repo.** Scrabble lists and wordhunt.org's list aren't redistributable. The repo ships the upload and fetch scripts plus a tiny public-domain test list.

## Risks, open questions, and the first spike

The riskiest new piece is the broadcast extension: can it run a full 40+ minute session inside its memory limit and see enough frames to follow fast swipes? Prove that, and the board-reading logic, before building any UI.

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| The extension exceeds \~50 MB and is killed mid-session | Medium | Sample pixels without copying frames, keep one frame in flight, drop frames when behind. Soak-test a 60-minute session. |
| iOS delivers too few frames for fast swipes | Medium | Gap-fill with solver paths. The score change and release color still give each attempt's result. |
| A skip is misread, e.g. an iMessage screen taken for a board | Low | Leaving voids the board, so no end screen means a skip. The spike checks that other screens are never misread as a board. |
| Free signing lapses weekly and capture silently stops | Medium | The companion app shows days left and alerts on the last day. SideStore or AltStore can refresh it automatically; otherwise, re-install from Xcode. |
| A GamePigeon UI update breaks extraction | Medium | Calibration check each session, alerts on reconciliation failures, and debug capture |
| The Swift port drifts from the Python prototype | Medium | Diff both against the same recorded session in CI |
| Triage predictions are biased by which boards you play | High | Occasionally play out a board you'd normally skip (exploration) |
| Your Scrabble list diverges from GamePigeon's | Low–medium | The ledger corrects it; precision and recall are reported |

**Decisions from your answers**

- **Skipping means leaving the game.** GamePigeon voids that board, so a board that closes without an end screen is logged as skipped, with its viewing time.
- **Mac and Swift: yes.** The native capture app stays the main path. Session recording is used only for the spike and as a fallback.
- **Dictionary: NWL,** which you source and keep local. It's copyrighted and is never committed.
- **No Qu tile, 4×4 only.** Letter recognition needs just 26 single-letter templates, and nothing supports other board sizes.
- **The end screen lists your found words.** That's a word-level check on extraction. The "More words" view also gives GamePigeon's own per-board word count (see Dictionary).

**Spike checklist (1–2 weekends, no app yet)**

- [ ] With Focus on, use ordinary screen recording to capture one full session of 40–50 boards, played as usual
- [ ] Note the file size and length; this also sizes the fallback path
- [ ] Hand-label each board's start, end, and played or skipped status
- [ ] Plot tile-center colors for two played boards, and confirm the selected-state colors
- [ ] Prototype the phone-side state machine in Python at 15 and 30 fps, and compare it with the hand labels
- [ ] Build letter templates from 5 boards, plus the trie solver over your Scrabble list
- [ ] Reconcile 5 played games with their final scores and found-word lists. On those boards, open "More words" and check whether masked entries show word length and sit in sorted order.
- [ ] Build a minimal broadcast extension, signed with your free Personal Team, that only logs frame rate and memory for 30 minutes during real play. Also check whether App Groups are available.
- [ ] Decide go or no-go on live capture. On no-go, fall back to session recording with automatic import to a Mac.

## Sources

- Scoring table and 80-second timer: confirmed from your own play, and matching the scoring reference in the [WordHunt.org solver](https://www.wordhunt.org/solver)
- [WordHunt.org](https://www.wordhunt.org): solver loads a static `/wordlist.json` (inspected Oct 23, 2026: \~198k words, no API, no stated license)
- [Apple: Choosing a membership](https://developer.apple.com/support/compare-memberships): free Personal Team signing (7-day profiles, 3 devices, 10 App IDs per 7 days)
- [Twilio ReplayKit example](https://github.com/twilio/video-quickstart-ios/blob/master/ReplayKitExample) and [Apple Developer Forums thread](https://developer.apple.com/forums/thread/651367): the \~50 MB memory limit on Broadcast Upload Extensions
- [notrandomath/wordhunt-solver](https://github.com/notrandomath/wordhunt-solver): an open-source Word Hunt solver that credits dwyl/english-words as its word list
