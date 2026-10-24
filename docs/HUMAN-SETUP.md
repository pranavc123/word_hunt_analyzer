# Human setup

Status (2026-10-24): steps 1–9 done. Remaining: recordings (step 10) and copying this pack in (step 11).

1. ✅ Xcode installed and opened once; signed in with your Apple ID (Personal Team).
2. ✅ iPhone paired with Xcode, Developer Mode on, "Connect via network" enabled.
3. ✅ `brew install ffmpeg git uv fnm pnpm xcodegen tesseract gh`
4. ✅ Node via fnm (shell hook in `~/.zshrc`, `fnm install --lts`, `fnm default <version>`); pnpm from Homebrew, not corepack.
5. ✅ Claude Code installed and logged in. Run it from the repo root.
6. ✅ GitHub repo; `gh auth login`.
7. ✅ Tailscale on Mac + iPhone; MagicDNS + HTTPS certificates enabled. Note your Mac's `<name>.<tailnet>.ts.net` address.
8. ✅ Env vars in `~/.zshrc`:
   ```
   export WH_DATA="$HOME/Projects/wordhunt/wordhunt-data"
   export WH_DICT="$WH_DATA/dictionaries/yawl.txt"
   export WH_TOKEN="<output of: openssl rand -hex 32>"
   ```
   Folders `dictionaries/`, `recordings/`, `labels/` exist; `yawl.txt` and `enable1.txt` are in `dictionaries/`.
   `wordhunt-data/` sits inside the repo folder and must stay git-ignored (S0.T1 does this).
9. ✅ Phone: "Word Hunt" Focus; Screen Recording in Control Center.
10. Recordings (two parts, because VIEW ALL WORDS unlocks only after your opponent plays):
    - `session1.mov`: one normal session (40–50 boards) with screen recording + Focus on.
      Don't open VIEW ALL WORDS. On one game, tap "(N more)" on the end screen and note whether
      the full found-words list opens. AirDrop to `$WH_DATA/recordings/session1.mov`.
    - `allwords1.mov`: once opponents have played back 5+ of those games, start a short recording,
      open each game, tap VIEW ALL WORDS, flick to the bottom at varied speeds (gentle → hardest).
      Save to `$WH_DATA/recordings/allwords1.mov`.
    - Already there: `IMG_0717.PNG` (board at 00:01) and `IMG_0718.PNG` (end screen).
11. Unzip this pack into `~/Projects/wordhunt` (repo root), commit, push.

## Kickoff prompt (tonight, before recordings)
> Read CLAUDE.md and docs/PROGRESS.md. The session recordings aren't ready yet. Do S0.T1,
> then S0.T2 and S0.T3, then S0.T4 (calibration from the two screenshots), then S0.T14.
> If time remains, do S2.T1 and S4.T3. Skip anything that needs session1.mov or
> allwords1.mov, and tell me what you need from me when you stop.

## Kickoff prompt (once recordings exist)
> Read CLAUDE.md and docs/PROGRESS.md, then work through the current sprint. Stop when only
> [HUMAN] tasks remain and tell me exactly what to do.

## Your touchpoints (everything else is the agent's)
S0: recordings · label ~8 boards (15 min) · 30-min device run · S3: first live session ·
S4+: play, open the app, and now and then do a short VIEW ALL WORDS review capture of finished
games. Re-install from Xcode weekly (free signing).
