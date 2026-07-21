"""Org mode: the self-hosted collector's config + store.

Org mode lets a small team aggregate usage across machines without any
third-party service: one TokenTelemetry instance acts as the collector, and
each teammate's machine ships metrics-only session rollups to it (session id,
agent, project, timestamp, token counts, optional model/cost). Prompt content,
transcripts, and file paths never leave the source machine, and the collector
never reaches out to anything.

Config lives at ``<data_dir()>/org.json``:

    {"machines": [{"label": "kyle-laptop", "token": "<random hex>"}]}

Org mode is "enabled" when that file exists and lists at least one machine.
Rollups are stored in SQLite at ``<data_dir()>/org.db``, one row per
(machine, session_id), so re-shipping the same sessions upserts instead of
double-counting. Both paths resolve through ``tt_paths.data_dir()`` and are
created lazily on first write.
"""
from __future__ import annotations

import hmac
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from tt_paths import data_dir


def _config_path() -> Path:
    return data_dir() / "org.json"


def _db_path() -> Path:
    return data_dir() / "org.db"


def read_org_config() -> Dict[str, Any]:
    """Load org.json. Missing or corrupt config means org mode is disabled, so
    both cases return ``{"machines": []}`` rather than raising."""
    try:
        raw = json.loads(_config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"machines": []}
    machines = raw.get("machines") if isinstance(raw, dict) else None
    if not isinstance(machines, list):
        return {"machines": []}
    clean = [
        m for m in machines
        if isinstance(m, dict)
        and isinstance(m.get("label"), str) and m["label"].strip()
        and isinstance(m.get("token"), str) and m["token"]
    ]
    return {"machines": clean}


def resolve_machine(token: str) -> Optional[str]:
    """Map a presented machine token to its configured label, or None.

    Every configured token is compared with hmac.compare_digest and the loop
    never exits early, so response timing does not reveal which (if any) entry
    matched or how far down the list it sits. Comparison is on bytes: header
    values reach us latin-1 decoded and compare_digest raises TypeError on a
    non-ASCII str, which would turn a garbage token into a 500 instead of 401.
    """
    if not token:
        return None
    token_bytes = token.encode("utf-8")
    matched: Optional[str] = None
    for m in read_org_config()["machines"]:
        if hmac.compare_digest(token_bytes, m["token"].encode("utf-8")) and matched is None:
            matched = m["label"]
    return matched


_SCHEMA = """
CREATE TABLE IF NOT EXISTS org_sessions (
    machine        TEXT NOT NULL,
    session_id     TEXT NOT NULL,
    agent          TEXT NOT NULL,
    project        TEXT NOT NULL,
    timestamp      TEXT NOT NULL,
    input_tokens   INTEGER NOT NULL DEFAULT 0,
    output_tokens  INTEGER NOT NULL DEFAULT 0,
    cached_tokens  INTEGER NOT NULL DEFAULT 0,
    total_tokens   INTEGER NOT NULL DEFAULT 0,
    model          TEXT,
    cost           REAL,
    received_at    TEXT NOT NULL,
    PRIMARY KEY (machine, session_id)
)
"""


def _connect() -> sqlite3.Connection:
    """Open org.db, creating the directory and schema on first use."""
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(_SCHEMA)
    return conn


def upsert_sessions(machine: str, sessions: List[Dict[str, Any]]) -> Tuple[int, int]:
    """Upsert one machine's rollups; returns (accepted, updated).

    accepted = rows new to the store, updated = rows that already existed and
    were re-upserted. Keyed on (machine, session_id) so re-shipping the same
    batch is idempotent: totals never double-count.
    """
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        existing: set = set()
        ids = [str(s.get("id", "")) for s in sessions]
        # SQLite caps bound parameters (999 in older builds); chunk the
        # existence probe so arbitrarily large batches still work.
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            marks = ",".join("?" * len(chunk))
            rows = conn.execute(
                f"SELECT session_id FROM org_sessions WHERE machine = ? AND session_id IN ({marks})",
                [machine, *chunk],
            ).fetchall()
            existing.update(r[0] for r in rows)
        accepted = updated = 0
        for s in sessions:
            tokens = s.get("tokens") or {}
            conn.execute(
                """
                INSERT INTO org_sessions (machine, session_id, agent, project, timestamp,
                    input_tokens, output_tokens, cached_tokens, total_tokens,
                    model, cost, received_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(machine, session_id) DO UPDATE SET
                    agent = excluded.agent,
                    project = excluded.project,
                    timestamp = excluded.timestamp,
                    input_tokens = excluded.input_tokens,
                    output_tokens = excluded.output_tokens,
                    cached_tokens = excluded.cached_tokens,
                    total_tokens = excluded.total_tokens,
                    model = excluded.model,
                    cost = excluded.cost,
                    received_at = excluded.received_at
                """,
                (
                    machine, str(s.get("id", "")), str(s.get("agent", "")),
                    str(s.get("project", "")), str(s.get("timestamp", "")),
                    int(tokens.get("input") or 0), int(tokens.get("output") or 0),
                    int(tokens.get("cached") or 0), int(tokens.get("total") or 0),
                    s.get("model"), s.get("cost"), now,
                ),
            )
            if str(s.get("id", "")) in existing:
                updated += 1
            else:
                accepted += 1
                existing.add(str(s.get("id", "")))
        conn.commit()
        return accepted, updated
    finally:
        conn.close()


def _enabled() -> bool:
    return len(read_org_config()["machines"]) > 0


def status() -> Dict[str, Any]:
    cfg = read_org_config()
    sessions = 0
    if _db_path().exists():
        conn = _connect()
        try:
            sessions = conn.execute("SELECT COUNT(*) FROM org_sessions").fetchone()[0]
        finally:
            conn.close()
    return {
        "enabled": len(cfg["machines"]) > 0,
        "machines": len(cfg["machines"]),
        "sessions": sessions,
    }


def _empty_summary(enabled: bool) -> Dict[str, Any]:
    return {
        "enabled": enabled,
        "totals": {"sessions": 0, "tokens": 0, "cost": 0.0},
        "by_machine": [],
        "by_agent": [],
        "by_project": [],
        "recent": [],
    }


def summary() -> Dict[str, Any]:
    """Org-wide rollup for the dashboard. Always returns every key (zeros and
    empty lists when disabled or empty) so the frontend never branches on
    missing fields."""
    if not _enabled() or not _db_path().exists():
        return _empty_summary(_enabled())
    conn = _connect()
    try:
        total_row = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(total_tokens), 0), COALESCE(SUM(cost), 0.0) FROM org_sessions"
        ).fetchone()
        by_machine = [
            {"machine": r[0], "sessions": r[1], "tokens": r[2], "cost": r[3], "last_seen": r[4]}
            for r in conn.execute(
                """
                SELECT machine, COUNT(*), COALESCE(SUM(total_tokens), 0),
                       COALESCE(SUM(cost), 0.0), MAX(received_at)
                FROM org_sessions GROUP BY machine
                ORDER BY COALESCE(SUM(total_tokens), 0) DESC
                """
            ).fetchall()
        ]
        def _grouped(col: str, key: str) -> List[Dict[str, Any]]:
            return [
                {key: r[0], "sessions": r[1], "tokens": r[2], "cost": r[3]}
                for r in conn.execute(
                    f"""
                    SELECT {col}, COUNT(*), COALESCE(SUM(total_tokens), 0),
                           COALESCE(SUM(cost), 0.0)
                    FROM org_sessions GROUP BY {col}
                    ORDER BY COALESCE(SUM(total_tokens), 0) DESC
                    """
                ).fetchall()
            ]
        # Timestamps are stored verbatim with each machine's own UTC offset, so
        # lexical order misranks mixed offsets; datetime() normalizes to UTC
        # (unparseable values become NULL and sort last under DESC).
        recent = [
            {"id": r[0], "machine": r[1], "agent": r[2], "project": r[3],
             "timestamp": r[4], "tokens_total": r[5], "cost": r[6]}
            for r in conn.execute(
                """
                SELECT session_id, machine, agent, project, timestamp, total_tokens, cost
                FROM org_sessions ORDER BY datetime(timestamp) DESC LIMIT 20
                """
            ).fetchall()
        ]
        return {
            "enabled": True,
            "totals": {
                "sessions": total_row[0],
                "tokens": total_row[1],
                "cost": float(total_row[2]),
            },
            "by_machine": by_machine,
            "by_agent": _grouped("agent", "agent"),
            "by_project": _grouped("project", "project"),
            "recent": recent,
        }
    finally:
        conn.close()
