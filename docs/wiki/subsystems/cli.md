---
type: Subsystem
title: CLI launcher
description: bin/cli.js starts backend (default port 8000) and frontend (3000); flags for ports, host, origins, auth token, data dir.
resource: /bin/cli.js
tags: [subsystem, cli]
timestamp: 2026-07-02
---

# CLI launcher

`bin/cli.js` starts the FastAPI backend (default port **8000**) and the
Next.js frontend (port 3000). Install via `install.sh` / `install.ps1` or
`start.sh` / `start.bat` from a clone.

- **Flags:** `--port`, `--api-port`, `--host`, `--allowed-origins`,
  `--auth-token`, `--insecure-no-auth`, `--data-dir`, `--quiet`, `--flag`,
  `--help`.
- The frontend derives its API base from `window.location` +
  `NEXT_PUBLIC_API_PORT` at runtime (set by `bin/cli.js` from `--api-port`),
  so non-default ports work automatically. `NEXT_PUBLIC_API_BASE` remains an
  explicit override to pin a fixed host, but is not needed just to change
  ports.
- Remote access (`--host` non-loopback) turns on the token gate; see
  [remote auth](remote-auth.md). Envs: `TT_HOST`, `TT_ALLOWED_ORIGINS`,
  `TT_AUTH_TOKEN`.
- Data dir override: `--data-dir` / `TOKENTELEMETRY_DATA_DIR` (used by the
  [history store](history-store.md); path logic in `backend/tt_paths.py`).
