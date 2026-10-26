# Running the server

The server (FastAPI) and the worker (Huey) run as two user-level launchd agents on the Mac, start
at login, and restart if they crash. The phone reaches them through `tailscale serve` (HTTPS,
tailnet only).

## Install (once, and after pulling server changes)

1. Stop anything already on port 8000 (e.g. a `uvicorn` left running in a terminal: Ctrl-C).
2. Make sure `WH_DATA`, `WH_DICT` and `WH_TOKEN` are set in `~/.zshrc` (see HUMAN-SETUP.md).
3. Install / reload both agents (this also syncs dependencies and migrates the database):
   ```
   zsh tools/launchd/install.sh
   ```
4. Expose the server on your tailnet (persists across reboots; already enabled since S0):
   ```
   /Applications/Tailscale.app/Contents/MacOS/Tailscale serve --bg 8000
   ```

Uninstall: `zsh tools/launchd/uninstall.sh`.

## Check

```
curl http://127.0.0.1:8000/v1/health                                   # local
curl https://pranavs-macbook-pro.taile078e1.ts.net/v1/health          # through Tailscale
launchctl print gui/$(id -u)/com.wordhunt.server | grep -E "state|pid"
launchctl print gui/$(id -u)/com.wordhunt.worker | grep -E "state|pid"
tail -f $WH_DATA/logs/server.log $WH_DATA/logs/worker.log
```

Latest session summary (needs the token):
```
curl -H "Authorization: Bearer $WH_TOKEN" http://127.0.0.1:8000/v1/sessions/latest
```

## Where things go

| what | where |
| --- | --- |
| database | `$WH_DATA/wh.db` (SQLite, WAL) |
| task queue | `$WH_DATA/huey.db` |
| uploaded crops | `$WH_DATA/images/<session>/<board_id>/…`, `…/allwords_<record_id>/…` |
| device diagnostics | `$WH_DATA/diag.jsonl` |
| logs | `$WH_DATA/logs/server.log`, `worker.log` |

## Reprocess

The worker is idempotent (re-running replaces a board's attempts and word list). After a pipeline
change, reprocess everything (or one session) with:
```
uv run python tools/reprocess.py [--session <id>] [--allwords]
```

## Phone side (each session)

Tailscale connected → open **Word Hunt** ("server reachable") → **Start / stop capture** →
**Start Broadcast** → Word Hunt Focus on → play → stop from the red status-bar indicator.
Records queue on the phone if the server is unreachable and upload later.
