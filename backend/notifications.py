"""TokenTelemetry notification center: SQLite-backed, app-owned event store.

This is the first *persisted user-state* TokenTelemetry writes beyond JSON
config. It lives in its own database (`~/.tokentelemetry/notifications.db`),
separate from `summaries.db`, and is deliberately generic: the `kind` column
lets any feature post notifications (budget alerts today; "summary ready" /
"update available" later).

Lifecycle of a notification:
  - A detector inserts a row keyed by a stable `dedup_key` (INSERT OR IGNORE),
    so the same real-world event never creates two rows — even across restarts.
  - `toasted=0` means "not yet actively surfaced". The frontend shows each such
    row once (a one-time top banner) then calls mark_toasted(); it never
    actively re-surfaces.
  - `read=0` drives the bell's unread badge; opening the bell marks read.
  - `cleared=1` hides a row from the bell ("Clear all"). A still-true condition
    does NOT re-fire — only a NEW dedup_key (new threshold / new period) does.

Design rules mirror summaries.py / harness_config.py:
  - Dir created lazily; reads never raise; schema via CREATE TABLE IF NOT EXISTS.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

TT_HOME = Path(os.environ.get("TOKENTELEMETRY_HOME") or (Path.home() / ".tokentelemetry"))
_DB_PATH = TT_HOME / "notifications.db"


def _ensure_dir() -> None:
    TT_HOME.mkdir(parents=True, exist_ok=True)


def _connect() -> sqlite3.Connection:
    _ensure_dir()
    conn = sqlite3.connect(_DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS notifications (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            kind        TEXT NOT NULL,
            dedup_key   TEXT NOT NULL UNIQUE,
            severity    TEXT NOT NULL DEFAULT 'info',
            title       TEXT NOT NULL,
            body        TEXT,
            href        TEXT,
            created_at  TEXT NOT NULL,
            toasted     INTEGER NOT NULL DEFAULT 0,
            read        INTEGER NOT NULL DEFAULT 0,
            cleared     INTEGER NOT NULL DEFAULT 0
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_notifications_live "
        "ON notifications (cleared, created_at)"
    )
    conn.commit()


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "kind": row["kind"],
        "dedup_key": row["dedup_key"],
        "severity": row["severity"],
        "title": row["title"],
        "body": row["body"],
        "href": row["href"],
        "created_at": row["created_at"],
        "toasted": bool(row["toasted"]),
        "read": bool(row["read"]),
        "cleared": bool(row["cleared"]),
    }


def emit(kind: str, dedup_key: str, title: str, *,
         severity: str = "info", body: Optional[str] = None,
         href: Optional[str] = None) -> bool:
    """Create a notification if its dedup_key is new. Returns True if inserted.

    INSERT OR IGNORE keeps this idempotent: re-running the detector for an event
    that's already recorded is a no-op (no duplicate, no re-toast).
    """
    if not kind or not dedup_key or not title:
        return False
    now = datetime.now(timezone.utc).isoformat()
    try:
        conn = _connect()
        try:
            cur = conn.execute(
                """INSERT OR IGNORE INTO notifications
                   (kind, dedup_key, severity, title, body, href, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (kind, dedup_key, severity, title, body, href, now),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()
    except Exception:
        return False


def list_live() -> Dict[str, Any]:
    """Return non-cleared notifications (newest first) plus derived counts.

    `to_toast` is the subset that hasn't been actively surfaced yet — the
    frontend shows these once, then calls mark_toasted().
    """
    try:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT * FROM notifications WHERE cleared=0 ORDER BY datetime(created_at) DESC, id DESC"
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        return {"notifications": [], "unread_count": 0, "to_toast": []}

    items = [_row_to_dict(r) for r in rows]
    unread = sum(1 for it in items if not it["read"])
    to_toast = [it for it in items if not it["toasted"]]
    return {"notifications": items, "unread_count": unread, "to_toast": to_toast}


def mark_toasted(ids: Optional[List[int]] = None) -> int:
    """Flag notifications as actively surfaced so they never re-toast.
    None → all currently un-toasted. Returns rows affected."""
    return _set_flag("toasted", ids, where_extra="toasted=0")


def mark_read(ids: Optional[List[int]] = None) -> int:
    """Mark read (clears the unread badge). None → all unread."""
    return _set_flag("read", ids, where_extra="read=0")


def clear(ids: Optional[List[int]] = None) -> int:
    """Clear (hide from bell). None → all non-cleared. Rows are kept so the
    dedup_key stays reserved — a still-true condition won't re-fire."""
    return _set_flag("cleared", ids, where_extra="cleared=0")


def _set_flag(col: str, ids: Optional[List[int]], *, where_extra: str) -> int:
    # `col` is never user-supplied — only the three callers above pass literals.
    try:
        conn = _connect()
        try:
            if ids:
                clean = [int(i) for i in ids]
                placeholders = ",".join("?" for _ in clean)
                cur = conn.execute(
                    f"UPDATE notifications SET {col}=1 WHERE id IN ({placeholders}) AND {where_extra}",
                    clean,
                )
            else:
                cur = conn.execute(
                    f"UPDATE notifications SET {col}=1 WHERE {where_extra}"
                )
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()
    except Exception:
        return 0
