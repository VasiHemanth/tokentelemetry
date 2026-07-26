"""Codex Goal Mode (`/goal`) telemetry.

Codex is the only supported agent that keeps first-class goal state on disk, and
the only one that counts a goal's tokens and wall-clock *itself*. Everything here
is therefore **reported**, never inferred: we copy Codex's own numbers and its
own status string, and we never synthesise a status it didn't write.

Design notes in `docs/design/goal-telemetry.md`. Two of them matter for reading
this file:

1. **Two copies of the DB exist at different migration levels**, and on this
   machine the *populated* one is on the OLDER schema (v1, no
   `thread_goal_continuation_deferrals`). So pick the DB by row count rather than
   by path, and probe `sqlite_master` before touching the v2-only table.
2. **Goal status is live mutable state** (`active -> paused -> complete`). The
   caller must attach it outside the session cache, the way loop lifecycle is
   recomputed per request, or a stale `active` sticks forever.

Reads never raise: a missing, locked, or unexpected DB yields no goals.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Relative to ~/.codex. Order is only a tie-break; row count decides.
_DB_CANDIDATES = ("sqlite/goals_1.sqlite", "goals_1.sqlite")

_GOALS_TABLE = "thread_goals"
_DEFERRALS_TABLE = "thread_goal_continuation_deferrals"

# Codex's own vocabulary, normalised. Anything we don't recognise becomes
# "unknown" rather than being guessed at, but the raw string is kept in
# evidence.status_raw so the UI can still show what Codex actually said.
_STATUS_MAP = {
    "active": "active",
    "running": "active",
    "in_progress": "active",
    "paused": "paused",
    "complete": "complete",
    "completed": "complete",
    "done": "complete",
    "blocked": "blocked",
}

OBJECTIVE_MAX = 200


def _connect(path: Path) -> Optional[sqlite3.Connection]:
    """Read-only connection, or None if the file is missing/unreadable."""
    try:
        if not path.is_file():
            return None
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        con.execute("PRAGMA busy_timeout=500")
        return con
    except (sqlite3.Error, OSError):
        return None


def _tables(con: sqlite3.Connection) -> set:
    try:
        return {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    except sqlite3.Error:
        return set()


def _pick_db(codex_dir: Path) -> Optional[Path]:
    """Choose the goals DB that actually has rows.

    Codex leaves an empty newer-schema DB alongside a populated older-schema one,
    so "newest path wins" and "first path wins" both pick the wrong file. Fall
    back to any readable DB (so a fresh install with zero goals still resolves)
    and finally None.
    """
    fallback: Optional[Path] = None
    for rel in _DB_CANDIDATES:
        path = codex_dir / rel
        con = _connect(path)
        if con is None:
            continue
        try:
            if _GOALS_TABLE not in _tables(con):
                continue
            if fallback is None:
                fallback = path
            try:
                if con.execute(f"SELECT 1 FROM {_GOALS_TABLE} LIMIT 1").fetchone():
                    return path
            except sqlite3.Error:
                continue
        finally:
            con.close()
    return fallback


def _iso(ms: Any) -> Optional[str]:
    """Epoch milliseconds -> aware UTC ISO string."""
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _int_or_none(v: Any) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _deferral_counts(con: sqlite3.Connection) -> Optional[Dict[str, int]]:
    """thread_id -> deferral count, or None when the table predates migration v2.

    None and 0 mean different things here: 0 is "Codex recorded no deferrals",
    None is "this Codex version cannot record them", and the UI must not show
    a confident zero for the latter.
    """
    if _DEFERRALS_TABLE not in _tables(con):
        return None
    try:
        return {str(tid): int(n) for tid, n in con.execute(
            f"SELECT thread_id, COUNT(*) FROM {_DEFERRALS_TABLE} GROUP BY thread_id")}
    except sqlite3.Error:
        return None


def read_goals(codex_dir: Path) -> Dict[str, List[Dict[str, Any]]]:
    """Map Codex `thread_id` -> list of goals, oldest first.

    The thread id is exactly the session id `_scan_sessions_sync` builds for
    Codex (it rebuilds the same UUID from the rollout filename), so callers can
    join on it directly with no translation.
    """
    out: Dict[str, List[Dict[str, Any]]] = {}
    db = _pick_db(codex_dir)
    if db is None:
        return out
    con = _connect(db)
    if con is None:
        return out
    try:
        deferrals = _deferral_counts(con)
        try:
            rows = con.execute(
                f"SELECT thread_id, goal_id, objective, status, token_budget, "
                f"tokens_used, time_used_seconds, created_at_ms, updated_at_ms "
                f"FROM {_GOALS_TABLE}"
            ).fetchall()
        except sqlite3.Error:
            return out

        for (thread_id, goal_id, objective, status, budget,
             tokens_used, time_used, created_ms, updated_ms) in rows:
            if not thread_id:
                continue
            raw = (str(status).strip().lower() if status is not None else "")
            obj = str(objective or "").strip()
            goal = {
                "source": "codex",
                "goal_id": str(goal_id) if goal_id else None,
                "objective": obj[:OBJECTIVE_MAX],
                "objective_truncated": len(obj) > OBJECTIVE_MAX,
                "created_at": _iso(created_ms),
                "updated_at": _iso(updated_ms),
                # Codex wrote this down; we are not guessing.
                "state": _STATUS_MAP.get(raw, "unknown"),
                "state_source": "reported",
                "tokens": _int_or_none(tokens_used),
                "duration_seconds": _int_or_none(time_used),
                "token_budget": _int_or_none(budget),
                # Native counts: a SHARE OF the session total, never an addition.
                "cost_basis": "native",
                "evidence": {
                    "status_raw": str(status) if status is not None else None,
                    "deferrals": (deferrals.get(str(thread_id), 0)
                                  if deferrals is not None else None),
                },
            }
            out.setdefault(str(thread_id), []).append(goal)
    finally:
        con.close()

    for goals in out.values():
        goals.sort(key=lambda g: (g.get("created_at") or "", g.get("goal_id") or ""))
    return out
