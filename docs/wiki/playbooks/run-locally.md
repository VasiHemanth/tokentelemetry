---
type: Playbook
title: Run TokenTelemetry locally
description: Start backend and frontend for development; default ports 8000/3000, data dir override, common env vars.
tags: [playbook, dev]
timestamp: 2026-07-02
---

# Run locally

- **Users:** `curl -fsSL https://tokentelemetry.com/install.sh | bash`, or
  `start.sh` / `start.bat` from a clone. Everything is fronted by
  [`bin/cli.js`](../subsystems/cli.md): backend on 8000, frontend on 3000.
- **Dev:** run the FastAPI backend from `backend/` (deps in
  `backend/requirements.txt`) and `frontend/` with the usual Next.js dev
  server. Non-default API port needs only `--api-port` (frontend derives the
  base at runtime).
- Useful envs: `TOKENTELEMETRY_DATA_DIR` (isolate `history.db` while
  testing), `TT_CLINE_DIR` / `HERMES_HOME` (relocated agent stores),
  `DO_NOT_TRACK=1`, `TT_<BACKEND>_TIMEOUT` (summarizers).
- Cleanup traps: remove `~/.tokentelemetry/.update-check.json` if you seeded
  it; never point a test run's data dir at your real one when exercising
  retention/deletion paths.
- Backend tests: `pytest backend -q`. Frontend type-checks via
  `npm run build` in `frontend/`.
