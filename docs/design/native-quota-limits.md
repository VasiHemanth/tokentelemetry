# Native Provider Quotas and Limits

## Objective

TokenTelemetry will natively collect live provider quota, credit, and reset-window data from
existing local coding-agent credentials. It will not depend on OpenUsage, request credentials from
the user, or store provider secrets. Historical TokenTelemetry budgets remain separate from live
provider-account allowances.

## Contract

`GET /quotas` returns a `tokentelemetry.quotas.v1` envelope. Each provider has a display name,
optional plan, successful-fetch timestamp, expiry timestamp, staleness flag, and typed resources.
A resource is either bounded consumption (`used`, `limit`, `remaining`, `utilization`, optional
reset/window) or a balance (`available`). Missing data is omitted; it is never represented as zero.
Per-provider errors are returned separately while a last-good snapshot remains available.

The additive `capabilities` map lists every coding agent the dashboard knows about, so an agent is
never silently absent from the page. Each entry has a `displayName`, a state, and, when it is not
available, an explanation of what the user can do about it. It never infers a quota from a
directory, session transcript, token count, or spend estimate.

| State | Meaning |
| --- | --- |
| `available` | A live provider reading is present in `providers`. |
| `notSignedIn` | No local credentials were found for this agent. |
| `sessionExpired` | Credentials exist but the session has lapsed and could not be renewed. The detail names the command to run. |
| `notEntitled` | The account is valid but has no plan quota to report (for example a retired free tier). |
| `refreshFailed` | The provider was asked and the request failed. |
| `notSupported` | This agent has no account-quota API to read. |

The three middle states matter because they are not faults. Only `refreshFailed` adds a row to
`errors`, so the dashboard's refresh warning keeps meaning "a fetch actually broke" rather than
lighting up for an agent the user simply is not signed in to.

`POST /quotas/refresh` performs a native forced refresh. It is protected by the existing remote
access middleware and has no provider-side mutation behavior.

## Provider Scope

Every agent in `frontend/src/lib/agents.ts` has an entry. Seven have a native account-quota API;
the rest are listed with the reason they do not. `backend/test_quotas.py` asserts the two sets match
exactly, so adding an agent to the roster without a quota entry fails the suite.

| Provider | Local credential source | Native quota endpoint |
| --- | --- | --- |
| Codex | `$CODEX_HOME/auth.json`, `~/.codex/auth.json`, or `~/.config/codex/auth.json` | ChatGPT `wham/usage` and reset-credit endpoint |
| Claude Code | `$CLAUDE_CONFIG_DIR/.credentials.json`, `~/.claude/.credentials.json`, or the macOS login Keychain | Anthropic OAuth usage |
| Cursor | `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb` | Cursor dashboard current-period usage |
| OpenCode Go | `$OPENCODE_DATA_DIR/auth.json`, XDG data, or `~/.local/share/opencode/auth.json` | OpenCode Go usage |
| GitHub Copilot | editor `apps.json`/`hosts.json`, GitHub CLI `hosts.yml`, or OpenCode's `github-copilot` entry | GitHub Copilot internal user quota |
| Grok Code Fast | `~/.grok/auth.json` | Grok CLI billing credits |
| Gemini CLI | `~/.gemini/oauth_creds.json` or `~/.config/gemini/oauth_creds.json` | Google Code Assist user quota |

All credential paths are local-only probes. They are read only immediately before a provider
request; credentials are neither cached, emitted by the API, nor logged.

Three details are worth recording because each one looked like a different bug:

- **Claude Code stores its session in the macOS Keychain**, and writes no credentials file there.
  A file-only probe therefore reported a signed-in user as signed out, which is why Claude Code was
  missing from the dashboard entirely. Both sources are read, file first. The Keychain read is
  bounded by a timeout so an unanswered consent dialog degrades to "no credentials" rather than
  hanging the request thread. `~/.claude.json`'s `cachedUsageUtilization` is deliberately not used
  as a live source: the CLI only rewrites it when it next calls the API, and it is routinely days old.
- **OpenCode sits behind Cloudflare**, which answers the standard library's default
  `Python-urllib/x.y` agent with a 1010 browser-signature ban. That arrives as HTTP 403 and is
  indistinguishable from a rejected login. Every request now identifies itself with a `User-Agent`.
- **Expired sessions are detected before they are spent** where the credential says so: Cursor's
  token carries its own `exp` claim, and Grok's and Gemini's credential files carry an expiry plus a
  refresh token. Grok and Gemini renew in memory; neither agent's session file is ever rewritten,
  because mutating it could log the user out of their own CLI.

Renewing Gemini's token needs the installed CLI's OAuth client secret. Google issues installed-app
clients a "secret" that is not confidential, but committing one to a public repository trips secret
scanning and reads like a real leak, so it is located in the installed CLI bundle at run time rather
than vendored. No Gemini CLI on the machine means no renewal, and the lapsed session is reported as
`sessionExpired`.

## Tech Stack and Structure

- `backend/quotas.py` owns the typed internal model, five-minute cache, safe credential probes,
  provider refreshers, and external-response validation.
- `backend/main.py` exposes thin FastAPI routes and keeps remote access enforcement unchanged.
- `backend/test_quotas.py` covers parsing, status reporting, stale-while-revalidate cache behavior,
  and API results.
- `frontend/src/lib/quotas.ts` owns the API type contract.
- `frontend/src/components/QuotaOverview.tsx` renders read-only live-allowance cards.

The backend uses the Python standard library for HTTP so the feature adds no dependency. Blocking
file and HTTP work runs off FastAPI's event loop.

## Commands

```sh
cd backend && ./venv/bin/python -m pytest test_quotas.py
cd backend && ./venv/bin/python -m pytest
cd frontend && npx tsc --noEmit
cd frontend && npm run lint
```

## Testing Strategy

- Unit tests use injected fetchers, clocks, and temporary credential files; no real provider request
  or credential is used.
- API tests assert the public envelope, no-data state, refresh behavior, and that errors retain the
  previous successful result.
- Frontend type checking and linting validate the additive UI client.

## Boundaries

- Always: validate provider responses at the boundary, redact errors, retain last-good data, and
  keep quota collection independent of session scanning.
- Ask first: adding a dependency, changing existing budget semantics, persisting credentials, or
  adding a provider-side mutation.
- Never: log, serialize, cache, or return access tokens, refresh tokens, API keys, raw provider
  responses, or user prompts.

## Success Criteria

1. TokenTelemetry exposes native live quota data without OpenUsage being installed or running.
2. Available providers use existing local credentials only and normalize bounded limits, balances,
   reset times, and expiry/staleness into one API contract.
3. Failed refreshes keep a last-good snapshot and surface a safe provider error.
4. The dashboard matches vendor “percent left” language for percentage quotas and identifies provider
   quotas as distinct from TokenTelemetry budgets.
5. Every supported coding agent is visible with a live reading or a stated reason; no unavailable
   quota is fabricated, and an account state is never reported as a refresh failure.
5. Focused backend tests, the full backend suite, frontend type checking, and frontend lint pass.
