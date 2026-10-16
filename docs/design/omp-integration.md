# Design: Oh My Pi (OMP) session telemetry

Adding Oh My Pi — a local, terminal-first coding agent — as a newly supported,
locally-scanned harness, read entirely from the session files it already writes.

Status: **Planned**

## What OMP is

OMP ("omp", Oh My Pi) is a terminal-first local coding agent: a CLI plus a TUI,
MIT-licensed, built by Stencil Labs as a fork of Pi. It installs with
`curl -fsSL https://omp.sh/install | sh` or `brew install can1357/tap/omp`, and
its source lives at `github.com/can1357/oh-my-pi`.

It is a local tool, not a hosted service. Everything TokenTelemetry needs sits in
a directory OMP writes under the user's home, which is exactly the contract every
other supported agent already meets: no SDK, no cloud, no API key.

OMP is a **new, separate agent** — key `omp` — not an alias of the existing `pi`
agent. The two are forks with different on-disk formats, so sharing a key or a
scanner would be wrong. This mirrors the rule that already separates `muse` from
`prime`, or `dsh` from `kimi`.

## Local store layout

Verified against a real install (omp/18.10.2). Root is `~/.omp/agent/` (created
with mode `0700`). Only the default profile was present on the verified machine.

```
~/.omp/agent/
  sessions/
    <encoded-cwd>/                       # path separators stripped/dashed,
      <ISO-ts>_<session-uuidv7>.jsonl    #   e.g. "-tokentelemetry"
    <encoded-cwd>/                       # sibling dir of the same basename
      ...                                #   per-tool artifact logs (NOT read in v1)
  agent.db                               # SQLite: model_perf / model_usage (panel)
  config.yml                             # scalar settings (panel)
  mcp.json                               # MCP server definitions (panel)
  models.yml                             # provider definitions incl. apiKey (panel)
```

Sessions are **one JSONL file per session**, bucketed by the encoded working
directory, exactly like Pi. Each bucket has a sibling directory of the same
basename holding per-tool artifact logs.

v1 reads **only the depth-1 `*.jsonl` session files** directly under
`sessions/<bucket>/`; subagent session files sit one level deeper, inside those
sibling artifact directories.

## Records we read

Each session file is a stream of newline-delimited JSON records. The header
records appear first, in order: `title`, `session`, then `model_change`.

| Record (`type`) | Where | Field paths used |
| --- | --- | --- |
| `session` | header | `id`, `cwd`, `timestamp` |
| `model_change` | header | `model` (a combined string; not authoritative — see below) |
| `message` (`role:"assistant"`) | turn | `message.model`, `message.provider`, `message.usage.input`, `message.usage.output`, `message.usage.cacheRead`, `message.usage.cacheWrite`, `message.usage.cost.total`, `message.duration`, `message.ttft`, `message.contextSnapshot` |
| `message` (`role:"user"`) | turn | `message.content[].text` (display only) |
| `message` (`role:"toolResult"`) | turn | — (counted as a message; nothing surfaced) |
| `custom` (`customType:"tool_execution_start"`) | event | `data.toolName`, `data.toolCallId` |
| `custom` (other `customType`s) | event | ignored in v1 (`session_exit`, `skill-prompt`, `system-prompt-digest`, …) |
| `custom_message` | event | ignored in v1 |
| `compaction` | event | ignored in v1 (`.tokensBefore/.tokensAfter/.method`) |
| `thinking_level_change` | event | ignored in v1 (`.thinkingLevel`) |
| `branch_summary` | event | ignored in v1 |
| `session_init` | subagent files only | ignored in v1 (depth-1 files only) |
| `title` | header | ignored in v1 |

The parser must tolerate every record type above and simply skip the ones it does
not use, so an OMP version that adds new record types does not break the scan.

Two format facts drive the design:

- **Per-message fields are authoritative.** `model_change` carries only a
  combined `model` string, so the scanner reads `message.model` and
  `message.provider` from each assistant turn rather than trusting the header.
- **MCP tool names are bare.** OMP stores tool names with no server attribution
  and no `mcp__*` prefix, so TokenTelemetry cannot tell which MCP server (if any)
  a call belongs to — see "What v1 does not capture".

## What v1 captures

- Session identity: `id`, encoded-`cwd` project (through project aliases), and a
  timestamp.
- Token totals, summed across every assistant turn: `input`, `output`, `cached`
  (from `usage.cacheRead`) and `cache_creation` (from `usage.cacheWrite`).
- Cost, reported verbatim by OMP (see "Cost semantics").
- Model and provider, taken per assistant turn.
- Tool counts, from `custom` / `tool_execution_start` records.
- A display label: the first user message, truncated to 120 characters.
- A per-session `omp` blob with provider, models used, message count, mean
  time-to-first-token, mean turn duration, and the last context snapshot.
- The session file itself as a single `document` artifact.

## What v1 does not capture

- **Reasoning split.** OMP records no separate reasoning token count, so
  `reasoning` is always `0`; it is kept in the canonical token shape only for
  uniformity with other agents.
- **MCP server attribution.** As above, OMP stores no server field, so
  `mcp_tools` is an empty list and the agent panel reports per-call MCP
  attribution/usage as `not_available`. Deriving server names from bare tool names
  would be a guess, and guesses do not ship.
- **Plans / mode.** `has_plan` is `False` and `plans` is `[]`; OMP's mode is
  ignored in v1.
- **Skills.** `skills_used` is not captured in v1.
- **Subagents / delegation.** Records in the deeper sibling artifact directories
  are not read in v1, so delegated work never appears in the trace view.
- **Latency as a first-class field.** v1 adds no new session-schema fields;
  time-to-first-token and duration live only in the `omp` blob.

## Data model

The scanner returns one session dict per file, in the same shape every other
agent uses, plus an agent-specific `omp` blob:

```jsonc
{
  "id": "019…uuidv7",
  "agent": "omp",
  "project": "/path/to/repo",          // header cwd, via _load_project_aliases(); else "unknown"
  "timestamp": "…",                     // latest message ts → header ts → file mtime
  "display": "first user message, ≤120 chars",
  "text": "…",                          // the same display text
  "tokens": {"input": 0, "output": 0, "cached": 0,
             "cache_creation": 0, "reasoning": 0, "total": 0},
  "mcp_tools": [],                      // OMP stores no server attribution
  "has_plan": false,
  "plans": [],
  "model": "<model>",                   // last assistant turn's message.model
  "artifacts": [{"name": "<file>.jsonl", "path": "…", "type": "document"}],
  "cost": 0.0,                          // sum of message.usage.cost.total
  "cost_source": "reported",
  "omp": {
    "provider": "<provider>",           // last seen
    "models_used": ["<model>", "…"],
    "num_messages": 42,
    "ttft_ms": 0,                       // mean of message.ttft
    "duration_ms": 0,                   // mean of message.duration
    "context_snapshot": {}              // last message.contextSnapshot dict
  }
}
```

`_attach_tool_usage(sess, tool_counts)` is called last, so `tool_counts` (and any
derived `mcp_usage`, which will be empty here) are attached in the same way as
every other scanner. `total` is computed as `input + output + cached`, the same
formula Pi uses.

## Detection

Path constants mirror the `PI_DIR` / `PI_SESSIONS_DIR` pattern
(`backend/main.py` ~359–365) and add the env-override contract used by
`PRIME_SESSIONS_DIR`:

```python
OMP_DIR = Path(os.environ.get("TT_OMP_DIR") or (HOME / ".omp" / "agent")).expanduser()
OMP_SESSIONS_DIR = Path(os.environ.get("TT_OMP_SESSIONS_DIR") or (OMP_DIR / "sessions")).expanduser()
```

The same constants are mirrored in `backend/harness_panels/paths.py`, because
main.py imports that package and cannot be imported back (see the module's own
note on circular imports).

Availability is a single line in `_list_available_agents()`
(`backend/main.py` ~3252–3286), beside the existing `pi` line at ~3268:

```python
if OMP_SESSIONS_DIR.exists():
    agents.append("omp")
```

**Scanner.** A new `_scan_omp_sessions()` in `backend/main.py`, modeled on
`_scan_pi_sessions()` (~4495–4666) but deliberately **not** sharing code with it
— the two formats differ enough that a shared reader would need per-format
branches, and the repo's convention is one scanner per agent. It is appended in
`_scan_sessions_sync` next to the Pi extend at ~9205:

```python
sessions.extend(_scan_omp_sessions())
```

## Cost semantics

TokenTelemetry reports OMP's recorded cost **verbatim**: the sum of
`message.usage.cost.total` across the session's assistant turns, and nothing
else. The session carries `"cost_source": "reported"`.

Unlike Pi, the scanner does **not** recompute cost and does **not** annotate the
value. The number on screen is the number OMP wrote down.

## Surfaces

1. **Scanner** — `_scan_omp_sessions()` in `backend/main.py`, appended in
   `_scan_sessions_sync`.
2. **Trace / waterfall view** — a minimal `omp` branch in `get_session_detail`
   (modeled on the `pi` branch at ~10033–10139) that normalizes OMP records into
   the Claude-shaped events the existing `EventCard` renderer draws, so OMP
   sessions open in the trace view.
3. **Harness panel** — `build_omp()` in `backend/harness_panels/clis.py`,
   registered as `"omp": clis.build_omp` in `BUILDERS`
   (`backend/harness_panels/__init__.py`). See "Harness panel" below.
4. **Frontend registry** — add `omp` to the `AgentKey` union and to the `AGENTS`
   record in `frontend/src/lib/agents.ts`:
   `{ key: "omp", label: "Oh My Pi", hex: "#e4e4e7", icon: OmpIcon }`. The icon
   is a dedicated `OmpIcon` component
   (`frontend/src/components/icons/OmpIcon.tsx`) carrying Oh My Pi's real brand
   mark, mirroring how `PiIcon` is a custom brand mark rather than a lucide
   glyph. This follows the monochrome/theme-aware treatment already used by
   `qoder` and `zcode`, which retints a near-white glyph in the light theme.
   That treatment is not contained in `agents.ts`, so `omp` must be
   wired into all three places it lives: `frontend/src/app/globals.css` (a
   `--agent-omp` custom property in **both** the dark and light blocks, mirroring
   `--agent-qoder` / `--agent-zcode`),
   `frontend/src/components/icons/AgentLogo.tsx` (the `isLightBrand` set), and
   `frontend/src/components/ui/Badge.tsx` (its `isLightBrand`-equivalent gating).
   Without the variable and both `isLightBrand` entries the `#e4e4e7` glyph is
   invisible on the light theme. The generic agent page needs no other change.
5. **Telemetry registry** — add `"omp"` to `_KNOWN_AGENTS` in
   `backend/telemetry.py`. That set is test-enforced to equal
   `harness_panels.BUILDERS | PLANNED` (see `backend/test_telemetry_harness_coverage.py`),
   and the joined agent list must stay under `_AGENTS_FIELD_MAX`; adding one more
   name is what that test exists to police.
6. **Billing** — add `"omp": "api"` to `DEFAULT_MODES` in
   `backend/billing_mode.py`. OMP is bring-your-own-key across providers.
7. **Quota provider** — add a `StaticQuotaProvider("omp", "Oh My Pi", …)` entry
   to `backend/quotas.py`, mirroring the `pi` wording (~line 1476). OMP reports no
   local quota, so it is a static `not_available`-style provider consistent with
   its peers. The ordered roster is pinned by `backend/test_quotas.py`
   (~lines 941–958), which must be updated in step.

## Harness panel

`build_omp()` in `backend/harness_panels/clis.py`, modeled on `build_pi()`
(~536–579) and registered in `BUILDERS`. It must never raise, and it honours the
three package rules in `base.py`: read-only always, never read credential
values, never surface bulk content.

Sections:

1. **MCP servers** — a table of the MCP servers *defined/configured* in
   `~/.omp/agent/mcp.json` (server name and command only). Environment blocks may
   hold secrets; they are never read. Same contract as the Pi panel's MCP table.
   This table lists configuration; it is distinct from per-call MCP
   *attribution/usage*, which is `not_available` (see the note below).
2. **Configuration** — scalar settings from `config.yml` (default model role,
   theme, and a couple of other scalar settings).
3. **Model usage / performance** — a table read **read-only** from
   `~/.omp/agent/agent.db` via `ro_sqlite`, joining `model_perf` (samples,
   `gen_ms`, `ttft_ms`, `output_tokens`) with `model_usage` (`last_used_at`) by
   `model_key`. From `models.yml`, report the provider **count** only; its
   `apiKey` values are never read.

Following the `build_pi` precedent, the panel marks quota as `not_available`
(OMP exposes no local usage/limit source). It additionally marks per-call MCP
*attribution/usage* as `not_available`, because OMP stores tool names with no
server namespace: the table above lists the configured servers, but the panel
cannot attribute any call to one. It sets `last_active` and `disk` like the other
CLI panels.

## Caching

The OMP scanner does **not** use `backend/scan_cache.py`, and `CACHE_VERSION` is
**not** bumped. The session shape is additive (a new agent key), so no existing
cached shape changes.

## Tests

- `backend/test_omp_scan.py`, modeled on `backend/test_pi_scan.py`: fixture
  builders write real JSONL into a temporary `sessions/<bucket>/` directory, and
  the test patches `main.OMP_SESSIONS_DIR` and
  `main._load_project_aliases` (to `lambda: {}`). Asserts cover agent, id,
  project, model, token sums, reported cost, tool counts, display text, and the
  blob; detection presence and absence; a missing directory yielding `[]`;
  corrupt-line resilience; and the `get_session_detail` shape.
- The panel is covered by `backend/test_harness_panels_agents.py`. The
  parametrized `test_missing_directory_yields_not_installed` iterates `BUILDERS`,
  so a new builder is exercised automatically once registered. **However**,
  `test_every_supported_agent_has_a_builder` in the same file also asserts a
  literal `supported = {…}` set (≈ lines 43–47) equal to
  `harness_panels.BUILDERS | PLANNED`, so `"omp"` must be added to that literal
  set as well or the test fails.
- The telemetry list is covered by `backend/test_telemetry_harness_coverage.py`,
  which pins `_KNOWN_AGENTS` to the panel registry.

## Files touched

Implementation (when this design ships):

- `backend/main.py` — `OMP_DIR` / `OMP_SESSIONS_DIR`, `_scan_omp_sessions()`, the
  `_scan_sessions_sync` extend, the `_list_available_agents()` line, and the
  `get_session_detail` `omp` branch.
- `backend/harness_panels/paths.py` — mirrored `OMP_DIR` / `OMP_SESSIONS_DIR`.
- `backend/harness_panels/clis.py` — `build_omp()`.
- `backend/harness_panels/__init__.py` — register `"omp": clis.build_omp`.
- `frontend/src/lib/agents.ts` — `AgentKey` union and `AGENTS` entry.
- `frontend/src/app/globals.css` — `--agent-omp` in the dark and light blocks.
- `frontend/src/components/icons/AgentLogo.tsx` — `omp` in the `isLightBrand` set.
- `frontend/src/components/ui/Badge.tsx` — `omp` in its `isLightBrand` gating.
- `backend/telemetry.py` — `"omp"` in `_KNOWN_AGENTS`.
- `backend/billing_mode.py` — `"omp": "api"` in `DEFAULT_MODES`.
- `backend/quotas.py` — `StaticQuotaProvider("omp", "Oh My Pi", …)`.
- `backend/test_omp_scan.py` — new.
- `backend/test_harness_panels_agents.py` — add `"omp"` to the literal supported
  set.
- `backend/test_quotas.py` — add `"omp"` to the pinned roster.

Shipped-feature docs and release:

- `website/content/docs/supported-agents.mdx` — add an OMP row to the
  coding-agents table, bump the frontmatter agent count (currently "19 coding
  agents"), and add an `### Oh My Pi (OMP)` detection note.
- Other user-facing rosters that enumerate the agents or the agent count go stale
  when the agent ships and must be updated too: `README.md` (agent list, ~line 3),
  `llms.txt` (~line 7), `website/public/llms.txt` (~line 7),
  `website/content/docs/index.mdx` (~line 8), and `website/src/app/layout.tsx`
  (~line 15, which also states the "19 coding agents" count).
- `UPDATE.json` — adding an agent is a `feat:` change, so the implementation
  adds a release entry at the top of `releases[]` with a `title` of 50
  characters or fewer.

See [ADR-0005](../adr/0005-omp-reported-cost-as-native-unit.md) for the decision
to report OMP's recorded cost verbatim rather than recompute it.
