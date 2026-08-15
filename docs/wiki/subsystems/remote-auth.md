---
type: Subsystem
title: Remote access auth
description: Token gate for non-loopback access; RemoteAuthMiddleware requires a bearer token on remote requests, loopback always exempt, CORS is not the boundary.
resource: /backend/main.py
tags: [subsystem, backend, security]
timestamp: 2026-07-02
---

# Remote access auth

Default is loopback-only. For tailnet/remote use (`--host` /
`--allowed-origins`, envs `TT_HOST` / `TT_ALLOWED_ORIGINS`):

- A non-loopback `--host` auto-generates `TT_AUTH_TOKEN` (printed once at
  startup). `RemoteAuthMiddleware` in `backend/main.py` then requires it on
  every remote request; loopback is always exempt, so the local experience is
  unchanged.
- **CORS is not the security boundary** (it only restrains browsers); the
  token is. The middleware registers BEFORE CORS so CORS stays outermost
  (answers OPTIONS preflight, decorates the 401). Keep that order.
- Frontend carries the token via `Authorization: Bearer`, and `?token=` for
  artifact `<img>`/`<a>` loads: `frontend/src/lib/api.ts` +
  `TokenGate.tsx`.
- Overrides: `--auth-token` to pin, `--insecure-no-auth` for a trusted
  tailnet.
- History: hardened after issue #91, which also produced the
  [pre-push gates](../conventions/pre-push-gates.md).
- Tests: `backend/test_remote_auth.py`.
