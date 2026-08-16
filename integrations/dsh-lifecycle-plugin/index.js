/**
 * TokenTelemetry plugin-lifecycle probe for DeepSeek Harness.
 *
 * WHY THIS EXISTS
 * DSH persists sessions to `~/.dsh/sessions/<slug>/<id>/session.jsonl.zstd`,
 * but that log has a CLOSED vocabulary: `KNOWN_SESSION_EVENT_TYPES` lists 44
 * event types and the persistence read path rejects anything outside it. None
 * of the 44 describes the plugin graph. Cordis does emit component lifecycle
 * transitions -- `internal/status`, fired from Fiber#_updateState with
 * `(fiber, oldState)` -- but only on its in-memory event bus, which nothing
 * bridges to disk. So after a run finishes there is no record that a plugin
 * loaded, reloaded, or failed.
 *
 * This plugin subscribes to that bus and appends each transition as JSONL to a
 * TokenTelemetry-owned sidecar. It is purely observational: it registers no
 * services, injects nothing, and swallows every error, so a TT problem can
 * never take down a DSH run. Same shape as TokenTelemetry's Omnigent policy
 * module (backend/omnigent_policy.py).
 *
 * WHAT IT CANNOT DO
 * Cordis fibers are runtime-global and carry no session id, so a transition
 * cannot be attributed to a session here. TokenTelemetry correlates by time
 * window and labels that correlation approximate.
 *
 * INSTALL: see README.md in this directory.
 */

import { appendFileSync, mkdirSync } from 'node:fs'
import { homedir } from 'node:os'
import { dirname, join } from 'node:path'

/**
 * Cordis FiberState is a `const enum`, so at runtime it arrives as an ordinal.
 * Mirrored from vendor/cordis/src/fiber.ts; the same table the harness's own
 * plugin-inventory package mirrors for its RPC projection.
 */
const FIBER_STATE_NAMES = {
  0: 'pending',
  1: 'loading',
  2: 'active',
  3: 'failed',
  4: 'disposed',
  5: 'unloading',
}

/** Resolve TokenTelemetry's data dir with the same precedence the backend uses. */
function dataDir() {
  if (process.env.TOKENTELEMETRY_DATA_DIR) return process.env.TOKENTELEMETRY_DATA_DIR
  if (process.env.TOKENTELEMETRY_HOME) return join(process.env.TOKENTELEMETRY_HOME, '.tokentelemetry')
  return join(homedir(), '.tokentelemetry')
}

/** Best-effort plugin identity. Nothing here is guaranteed present. */
function identify(fiber, ctx) {
  const name = fiber?.runtime?.name || null
  let entryId = null
  // The Loader knows the configured entry id, which is what a user recognises
  // from cordis.yml. Read it opportunistically: injecting `loader` would delay
  // this plugin until the loader is up and lose the earliest transitions.
  try {
    const entries = ctx?.loader?.entries?.()
    if (entries) {
      for (const entry of entries) {
        if (entry?.fiber === fiber) {
          entryId = entry.id ?? null
          break
        }
      }
    }
  } catch {
    // loader absent or mid-mutation; identity degrades to the runtime name
  }
  return { name, entryId }
}

/** Extract a short error string for a FAILED arrival, if one is attached. */
function errorText(fiber) {
  try {
    const err = fiber?._error
    if (!err) return null
    const text = err instanceof Error ? (err.stack || err.message) : String(err)
    return text.slice(0, 500)
  } catch {
    return null
  }
}

export const name = 'tokentelemetry-lifecycle'

/**
 * @param ctx - the Cordis context this plugin was loaded into.
 * @param config - `{ path?: string, flushMs?: number }`; `path` overrides the
 *   sidecar location, `flushMs` the batching interval.
 */
export function apply(ctx, config = {}) {
  const file = config.path || join(dataDir(), 'dsh_lifecycle.jsonl')
  const flushMs = Number.isFinite(config.flushMs) ? config.flushMs : 250

  let buffer = []
  let timer = null
  let broken = false

  /**
   * Write buffered rows in one append. Transitions burst at boot (every plugin
   * moves pending->loading->active), so batching keeps this to one syscall per
   * interval instead of one per transition.
   */
  function flush() {
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
    if (!buffer.length || broken) return
    const rows = buffer
    buffer = []
    try {
      mkdirSync(dirname(file), { recursive: true })
      appendFileSync(file, rows.map(r => JSON.stringify(r)).join('\n') + '\n')
    } catch {
      // Disk full, permissions, read-only home: stop trying rather than
      // throwing on every subsequent transition inside the harness's hot path.
      broken = true
    }
  }

  function schedule() {
    if (timer || broken) return
    timer = setTimeout(flush, flushMs)
    // Never hold the process open just to flush telemetry.
    if (typeof timer.unref === 'function') timer.unref()
  }

  ctx.on('internal/status', (fiber, oldState) => {
    try {
      const { name: pluginName, entryId } = identify(fiber, ctx)
      // Skip our own transitions: recording them would append on every one of
      // our own reloads and say nothing about the harness.
      if (pluginName === name) return
      const to = FIBER_STATE_NAMES[fiber?.state] ?? null
      const row = {
        ts: Date.now(),
        plugin: pluginName || `fiber#${fiber?.uid ?? '?'}`,
        entry_id: entryId,
        uid: fiber?.uid ?? null,
        from: FIBER_STATE_NAMES[oldState] ?? null,
        to,
      }
      if (to === 'failed') {
        const err = errorText(fiber)
        if (err) row.error = err
      }
      buffer.push(row)
      schedule()
    } catch {
      // Observation must never break the transition being observed.
    }
  })

  // `ctx.on` is owned by this fiber and is disposed with it, but the buffer is
  // ours: flush what we hold before going away, and on process exit.
  ctx.effect(() => {
    const onExit = () => flush()
    process.once('exit', onExit)
    return () => {
      process.removeListener('exit', onExit)
      flush()
    }
  })
}

export default { name, apply }
