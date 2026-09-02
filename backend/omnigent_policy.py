"""TokenTelemetry policy module for Omnigent.

Hooks into Omnigent's policy event stream to write per-session telemetry
(tokens, cost, tool calls, harness, model) into a TT-owned SQLite database
at ~/.tokentelemetry/omnigent_sessions.db.

TT's scanner (_scan_omnigent_sessions in main.py) reads that file on each
refresh so Omnigent sessions appear in the dashboard alongside Claude, Codex,
Cursor, and other native harnesses.

Registration (add to Omnigent's server_config.yaml or agent YAML):

    policy_modules:
      - tokentelemetry.omnigent_policy   # or: the dotted path where you install this

    policies:
      tt_telemetry:
        type: function
        function: tokentelemetry.omnigent_policy.record_telemetry

The callable always returns ALLOW — it is purely observational. It writes
on every "llm_response" event (one per model round-trip) so data is flushed
continuously rather than only at session end.

If the DB or data directory is unavailable the callable silently returns ALLOW
so a TT installation problem never blocks Omnigent work.
"""

from __future__ import annotations

import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Data directory (mirrors tt_paths.data_dir() without importing TT internals)
# ---------------------------------------------------------------------------

def _data_dir() -> Path:
    if d := os.environ.get("TOKENTELEMETRY_DATA_DIR"):
        return Path(d).expanduser()
    if h := os.environ.get("TOKENTELEMETRY_HOME"):
        return Path(h).expanduser() / ".tokentelemetry"
    return Path.home() / ".tokentelemetry"


def _db_path() -> Path:
    return _data_dir() / "omnigent_sessions.db"


# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id               TEXT    PRIMARY KEY,
    created_at       INTEGER NOT NULL,
    updated_at       INTEGER NOT NULL,
    harness          TEXT,
    model            TEXT,
    actor            TEXT,
    project          TEXT,
    input_tokens     INTEGER DEFAULT 0,
    output_tokens    INTEGER DEFAULT 0,
    total_tokens     INTEGER DEFAULT 0,
    total_cost_usd   REAL    DEFAULT 0.0,
    tool_calls       INTEGER DEFAULT 0,
    display          TEXT,
    parent_session_id TEXT
);
"""

_CONN: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _CONN
    if _CONN is not None:
        return _CONN
    db = _db_path()
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db), check_same_thread=False, timeout=5.0)
    conn.executescript(_SCHEMA)
    conn.commit()
    _CONN = conn
    return conn


# ---------------------------------------------------------------------------
# Session-state key — written back via state_updates on first call
# ---------------------------------------------------------------------------

_STATE_KEY = "tt_session_id"


# ---------------------------------------------------------------------------
# Policy callable
# ---------------------------------------------------------------------------

def record_telemetry(event: dict[str, Any]) -> dict[str, Any]:
    """Omnigent policy callable — observational, always ALLOW.

    Fires on every policy event. Writes/updates the session row on
    "llm_response" events (one per model round-trip) where the
    per-call usage dict is available in event["data"]["usage"].
    """
    try:
        _record(event)
    except Exception:
        pass  # never block Omnigent work
    return {"result": "ALLOW"}


def _record(event: dict[str, Any]) -> None:
    # Only capture on llm_response — that's where per-call token counts live.
    if event.get("type") != "llm_response":
        return

    ctx = event.get("context") or {}
    state = event.get("session_state") or {}
    data = event.get("data") or {}

    # Per-call usage from the llm_response data payload (delta for this round-trip).
    call_usage = data.get("usage") or {}
    call_in  = int(call_usage.get("input_tokens")  or 0)
    call_out = int(call_usage.get("output_tokens") or 0)

    # Cumulative usage from context (running session total).
    ctx_usage = ctx.get("usage") or {}
    cum_in    = int(ctx_usage.get("input_tokens")  or 0)
    cum_out   = int(ctx_usage.get("output_tokens") or 0)
    cum_cost  = float(ctx_usage.get("total_cost_usd") or 0.0)

    model   = data.get("model") or ctx.get("model") or "unknown"
    harness = ctx.get("harness") or "unknown"
    actor   = (ctx.get("actor") or {}).get("run_as") or ""

    # Project: derive from CWD label in session_state if the policy module
    # stamped it, else fall back to the actor identity.
    project = state.get("tt_project") or actor or "unknown"

    # First user message captured by a sibling "request" policy — use it as display.
    display = state.get("tt_first_message") or ""

    now = int(time.time())
    conn = _get_conn()

    # Stable session ID: generated on first call, stored in Omnigent session state.
    sess_id = state.get(_STATE_KEY)
    if not sess_id:
        sess_id = str(uuid.uuid4())

    conn.execute(
        """
        INSERT INTO sessions
            (id, created_at, updated_at, harness, model, actor, project,
             input_tokens, output_tokens, total_tokens, total_cost_usd,
             tool_calls, display)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
        ON CONFLICT(id) DO UPDATE SET
            updated_at    = excluded.updated_at,
            model         = excluded.model,
            input_tokens  = excluded.input_tokens,
            output_tokens = excluded.output_tokens,
            total_tokens  = excluded.total_tokens,
            total_cost_usd = excluded.total_cost_usd,
            display       = CASE WHEN display = '' THEN excluded.display ELSE display END
        """,
        (
            sess_id, now, now, harness, model, actor, project,
            cum_in or call_in,
            cum_out or call_out,
            (cum_in + cum_out) or (call_in + call_out),
            cum_cost,
            display[:200] if display else "",
        ),
    )
    conn.commit()


def record_request(event: dict[str, Any]) -> dict[str, Any]:
    """Capture first user message for display — register on 'request' phase.

    Optional companion callable. If registered, it stores the first user
    message in session_state so record_telemetry can use it as the session
    display name. Register alongside record_telemetry:

        policies:
          tt_telemetry_request:
            type: function
            function: tokentelemetry.omnigent_policy.record_request
          tt_telemetry:
            type: function
            function: tokentelemetry.omnigent_policy.record_telemetry
    """
    try:
        state = event.get("session_state") or {}
        if not state.get("tt_first_message"):
            msg = event.get("data") or ""
            if isinstance(msg, str) and msg.strip():
                return {
                    "result": "ALLOW",
                    "state_updates": [
                        {"key": "tt_first_message", "action": "set",
                         "value": msg.strip()[:200]},
                        {"key": _STATE_KEY, "action": "set",
                         "value": str(uuid.uuid4())},
                    ],
                }
    except Exception:
        pass
    return {"result": "ALLOW"}
