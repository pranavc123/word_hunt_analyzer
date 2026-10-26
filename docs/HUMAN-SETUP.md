# Human setup

Status (2026-10-26): everything below is done; Sprint 0 passed its gate (GO). This file now doubles
as the reference for re-doing a step (new Mac, new phone, weekly re-install).

## One-time Mac setup ✅
1. Xcode installed and opened once; Apple ID added in **Xcode → Settings → Accounts** (Personal Team).
2. iPhone paired with Xcode, Developer Mode on, "Connect via network" enabled.
3. `brew install ffmpeg git uv fnm pnpm xcodegen tesseract gh`
4. Node via fnm (shell hook in `~/.zshrc`, `fnm install --lts`, `fnm default <version>`); pnpm from Homebrew.
5. Claude Code installed and logged in; run it from the repo root (`~/Projects/wordhunt`).
6. GitHub repo `pranavc123/word_hunt_analyzer`; `gh auth login`.
7. Tailscale on Mac + iPhone; MagicDNS + HTTPS certificates enabled. Mac name:
   `pranavs-macbook-pro.taile078e1.ts.net`.
   - The App Store Tailscale has no `tailscale` on the PATH; use
     `/Applications/Tailscale.app/Contents/MacOS/Tailscale` (or add an alias).
   - **Serve** had to be enabled once for the tailnet (link printed by `… serve --bg 8000`). Done.
8. Env vars in `~/.zshrc` (no angle brackets around the token — it is 64 hex characters):
   ```
   export WH_DATA="$HOME/Projects/wordhunt/wordhunt-data"
   export WH_DICT="$WH_DATA/dictionaries/yawl.txt"
   export WH_TOKEN="<64 hex chars from: openssl rand -hex 32>"
   ```
   `wordhunt-data/` sits inside the repo folder and is git-ignored.
9. Phone: "Word Hunt" Focus; Screen Recording in Control Center; Tailscale app with **Use Tailscale DNS** on.

## Signing + config (git-ignored files in `ios/App/`) ✅
- `Signing.xcconfig` (copy of `Signing.example.xcconfig`):
  - `DEVELOPMENT_TEAM` = your **team ID**: the 10-character `OU=` value of your Apple Development
    certificate, **not** the code in the certificate's name. Create the certificate in
    Xcode → Settings → Accounts → (Personal Team) → Manage Certificates → + → Apple Development, then:
    `security find-certificate -c "Apple Development" -p | openssl x509 -noout -subject`
  - `WH_BUNDLE_PREFIX = com.pranavc123` (must be unique to you).
  - `CODE_SIGNING_ALLOWED = YES`. App Group lines stay commented unless testing App Groups.
- `Config.xcconfig` (copy of `Config.example.xcconfig`):
  - `WH_SERVER_URL = https:/$()/pranavs-macbook-pro.taile078e1.ts.net` — `//` starts a comment in
    xcconfig files, `$()` keeps the URL intact.
  - `WH_TOKEN = ` the same 64 characters as `$WH_TOKEN`.
- First install on a free team: the phone must be connected so Xcode can register it
  (`-allowProvisioningUpdates -allowProvisioningDeviceRegistration`). Then on the phone:
  **Settings → General → VPN & Device Management → Apple Development: … → Trust** (once).

## Each play session
1. Mac: start the server and the tunnel (the agent can do this in a Terminal tab):
   ```
   cd ~/Projects/wordhunt && uv run uvicorn app.main:app --app-dir server
   /Applications/Tailscale.app/Contents/MacOS/Tailscale serve --bg 8000
   ```
   (S3 turns these into launchd services — see `docs/RUNNING.md` once it exists.)
2. Phone: Tailscale **Connected**. Open **Word Hunt** → "server reachable" (tap Re-check if not).
3. Tap **Start / stop capture** → **Start Broadcast**. Turn on the Focus. Play.
4. Stop from the red status-bar indicator (or the same button).

## Weekly (free signing expires after 7 days; current profile: 2026-11-02)
Ask the agent to rebuild and reinstall (it runs `xcodebuild … -allowProvisioningUpdates` and
`xcrun devicectl device install app`), or press Run in Xcode. The developer stays trusted.

## Recordings used in S0 (in `$WH_DATA/recordings/`, never committed)
- `IMG_0717.PNG` / `IMG_0718.PNG`: board at 00:01 and its end screen.
- `session1.mov`: 10.4 min, 21 boards (6 played, 15 skipped). Labels in `labels/boards.csv`.
- `allwords1.mov`: 6 boards played second, each followed by VIEW ALL WORDS.

## Your touchpoints (everything else is the agent's)
S3: first live session with the services running · S4+: play, open the review app, and now and then
a short VIEW ALL WORDS capture of finished games (only your first 20 found words are revealed, which
is fine) · weekly re-install · occasional letter fixes in the Board confirm screen.

## Kickoff prompt (any session)
> Read CLAUDE.md and docs/PROGRESS.md, then work through the current sprint. Stop when only
> [HUMAN] tasks remain and tell me exactly what to do.
