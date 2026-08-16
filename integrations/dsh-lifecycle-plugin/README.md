# DSH plugin-lifecycle probe

Records DeepSeek Harness **plugin lifecycle transitions** so TokenTelemetry can
show them. Optional: DSH sessions are tracked without it; this only adds the
plugin-graph view.

## Why it's needed

DSH writes each session to `~/.dsh/sessions/<slug>/<id>/session.jsonl.zstd`, but
that log has a closed vocabulary — `KNOWN_SESSION_EVENT_TYPES` lists 44 event
types and the persistence layer rejects anything outside it. None of the 44
describes the plugin graph.

Cordis, the framework DSH is built on, *does* emit lifecycle transitions:
`internal/status`, fired from `Fiber#_updateState` with `(fiber, oldState)`.
But it goes to an in-memory event bus that nothing bridges to disk. DSH also
exposes a `pluginInventory/list` RPC while `dsh web` is running, which reports
each entry's *current* `fiberPhase` — a point-in-time snapshot with no history
or subscription.

So the current state is observable live; a **transition** is not observable at
all after the fact. That includes the two worth having:

- a plugin **failed** to activate and its effects were rolled back
- a plugin **reloaded** because its dependencies changed mid-flight

This plugin subscribes to the bus and appends transitions to a sidecar file.

## What it writes

Append-only JSONL at `~/.tokentelemetry/dsh_lifecycle.jsonl` (honours
`TOKENTELEMETRY_DATA_DIR` / `TOKENTELEMETRY_HOME`), one object per transition:

```json
{"ts":1786881908606,"plugin":"@deepseek-ai/dsh-host-apiproxy","entry_id":"api-gateway","uid":42,"from":"loading","to":"active"}
{"ts":1786881908771,"plugin":"@example/broken","entry_id":"broken","uid":43,"from":"loading","to":"failed","error":"TypeError: ..."}
```

`from`/`to` are Cordis `FiberState` names: `pending`, `loading`, `active`,
`failed`, `disposed`, `unloading`.

It writes **nothing else** — no prompts, no file contents, no tool output, no
model traffic. Just which plugin changed state, when, and the error text when
one failed.

## Install

The plugin is plain ESM with no build step. From a DSH profile directory
(`~/.dsh/profiles/<name>/`, e.g. `web`):

1. Add it as a dependency, pointing at this directory:

   ```bash
   cd ~/.dsh/profiles/web
   pnpm add file:/path/to/tokentelemetry/integrations/dsh-lifecycle-plugin
   ```

2. Register it in that profile's `cordis.patch.yml`. The file is a top-level
   YAML array of patch entries; a patch with `insert` and no `id` appends at the
   root of the composition:

   ```yaml
   - insert:
       - id: tt-lifecycle
         name: '@tokentelemetry/dsh-lifecycle'
   ```

3. Restart DSH. Confirm it loaded:

   ```bash
   dsh --dump-config | grep tt-lifecycle
   tail -f ~/.tokentelemetry/dsh_lifecycle.jsonl
   ```

### Config

Both optional, passed as the entry's `config`:

```yaml
- insert:
    - id: tt-lifecycle
      name: '@tokentelemetry/dsh-lifecycle'
      config:
        path: /custom/path/lifecycle.jsonl   # default: <tt-data-dir>/dsh_lifecycle.jsonl
        flushMs: 250                          # batching interval
```

## Uninstall

Remove the `cordis.patch.yml` entry and restart. The sidecar file is left in
place; delete it yourself if you want the history gone.

## Design notes

- **Observational only.** Registers no services, injects nothing, and swallows
  every error, so a problem here can never take down a DSH run. If the file
  can't be written it stops trying rather than throwing on each transition.
- **No `inject: ['loader']`.** Injecting the loader would delay this plugin
  until the loader is active and lose the earliest transitions; the loader is
  read opportunistically for the entry id, and identity degrades to the plugin
  name when it isn't available.
- **Writes are batched** (one append per interval, not per transition) because
  transitions burst at boot as every plugin moves pending → loading → active.
- **No session attribution.** Cordis fibers are runtime-global and carry no
  session id, so a transition can't be tied to a session here. TokenTelemetry
  correlates by time window and labels that correlation approximate.
- Same push-based shape as TokenTelemetry's Omnigent integration
  (`backend/omnigent_policy.py`).
