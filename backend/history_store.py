"""Durable, local history store for TokenTelemetry.

TokenTelemetry is otherwise a pure live-scanner: every request re-reads the
coding agents' on-disk transcripts and keeps the result only in a 30s in-RAM
cache. But agents prune their own transcripts (Claude Code deletes
``~/.claude/projects`` after ``cleanupPeriodDays``, default 30), so any analytics
window older than that retention silently loses data.

This module gives TT its own SQLite store under the resolved data dir (see
``tt_paths``) that it upserts on every scan, so a *summary* of each session
outlives the agent's own pruning. It is deliberately tiered:

  - ``sessions``     core rollup — tiny, always kept (one row per session).
  - ``transcripts``  opt-in, compressed full transcript blobs — user-deletable.
  - ``summaries``    generated summaries — persist even after a transcript is gone.

Design rules (mirroring ``harness_config``):
  - The DB and its directory are created lazily on first write, never on read.
  - Reads never raise; a missing/locked DB yields empty results.
  - One short-lived connection per call — safe to call from the scan worker
    thread and from request handlers. WAL mode lets reads run during a write.
  - ``query()`` returns rows shaped *exactly* like live session dicts so the
    existing ``/analytics`` aggregation loop can consume stored + live uniformly.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from tt_paths import data_dir

_log = logging.getLogger("tokentelemetry.history")

SCHEMA_VERSION = 1

# Sub-dicts folded into ``ecosystem_json`` and expanded back out on read. These
# are the keys the analytics aggregation + delegation views consume beyond the
# core rollup columns.
_ECOSYSTEM_KEYS = (
    "skills_used", "mcp_usage", "delegation", "subagent_info", "parent_session_id",
)


def _db_path() -> Path:
    # Resolved per call so a process that relocates the data dir (or a test that
    # monkeypatches TOKENTELEMETRY_DATA_DIR) always hits the right file.
    return data_dir() / "history.db"


def _connect() -> sqlite3.Connection:
    """Open the DB, creating the dir + schema lazily. Caller closes."""
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), timeout=5.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=5000")
    _migrate(con)
    return con


def _migrate(con: sqlite3.Connection) -> None:
    ver = con.execute("PRAGMA user_version").fetchone()[0]
    if ver < 1:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                agent           TEXT NOT NULL,
                id              TEXT NOT NULL,
                project         TEXT,
                model           TEXT,
                provider        TEXT,
                endpoint        TEXT,
                billing_mode    TEXT,
                first_ts        TEXT,
                last_ts         TEXT,
                input           INTEGER DEFAULT 0,
                output          INTEGER DEFAULT 0,
                cached          INTEGER DEFAULT 0,
                total           INTEGER DEFAULT 0,
                cost            REAL    DEFAULT 0.0,
                tok_per_sec     REAL,
                ecosystem_json  TEXT,
                first_seen_at   TEXT,
                last_seen_at    TEXT,
                source_present  INTEGER DEFAULT 1,
                transcript_archived INTEGER DEFAULT 0,
                summary_present INTEGER DEFAULT 0,
                PRIMARY KEY (agent, id)
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_last_ts ON sessions(last_ts);
            CREATE INDEX IF NOT EXISTS idx_sessions_agent   ON sessions(agent);
            CREATE INDEX IF NOT EXISTS idx_sessions_model   ON sessions(model);

            CREATE TABLE IF NOT EXISTS transcripts (
                agent       TEXT NOT NULL,
                id          TEXT NOT NULL,
                blob        BLOB,
                bytes       INTEGER DEFAULT 0,
                archived_at TEXT,
                PRIMARY KEY (agent, id)
            );

            CREATE TABLE IF NOT EXISTS summaries (
                agent      TEXT NOT NULL,
                id         TEXT NOT NULL,
                summary    TEXT,
                created_at TEXT,
                PRIMARY KEY (agent, id)
            );
            """
        )
        con.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        con.commit()


# ── serialization helpers ────────────────────────────────────────────────────

def _to_utc_iso(ts: Any) -> str:
    """Normalize a session timestamp to UTC ISO-8601 for lexicographic range
    filtering. Accepts a datetime or an ISO string; falls back to now()."""
    if isinstance(ts, datetime):
        dt = ts
    elif isinstance(ts, str) and ts:
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            dt = datetime.now(timezone.utc)
    else:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _ecosystem_blob(row: Dict[str, Any]) -> Optional[str]:
    eco = {k: row[k] for k in _ECOSYSTEM_KEYS if row.get(k) is not None}
    return json.dumps(eco, default=str) if eco else None


# ── write path ───────────────────────────────────────────────────────────────

def upsert_sessions(rows: Sequence[Dict[str, Any]]) -> int:
    """Idempotently persist the core rollup for each live session dict.

    Keyed by (agent, id): a session that grows between scans overwrites its row
    (never duplicates). ``first_ts`` / ``first_seen_at`` are preserved across
    upserts; ``last_*`` and the token/cost columns track the freshest scan, and
    ``source_present`` is (re)set to 1 because we just saw the file on disk.
    Returns the number of rows written. Never raises — a store failure must not
    break the scan that called it."""
    valid = [r for r in rows if r.get("id") and r.get("agent")]
    if not valid:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    written = 0
    try:
        con = _connect()
        try:
            for r in valid:
                tok = r.get("tokens") or {}
                ts = _to_utc_iso(r.get("timestamp"))
                con.execute(
                    """
                    INSERT INTO sessions (
                        agent, id, project, model, provider, endpoint, billing_mode,
                        first_ts, last_ts, input, output, cached, total, cost,
                        tok_per_sec, ecosystem_json, first_seen_at, last_seen_at,
                        source_present
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
                    ON CONFLICT(agent, id) DO UPDATE SET
                        project=excluded.project,
                        model=excluded.model,
                        provider=excluded.provider,
                        endpoint=excluded.endpoint,
                        billing_mode=excluded.billing_mode,
                        first_ts=MIN(sessions.first_ts, excluded.first_ts),
                        last_ts=MAX(sessions.last_ts, excluded.last_ts),
                        input=excluded.input,
                        output=excluded.output,
                        cached=excluded.cached,
                        total=excluded.total,
                        cost=excluded.cost,
                        tok_per_sec=excluded.tok_per_sec,
                        ecosystem_json=excluded.ecosystem_json,
                        last_seen_at=excluded.last_seen_at,
                        source_present=1
                    """,
                    (
                        r.get("agent"), r.get("id"), r.get("project"), r.get("model"),
                        r.get("provider"), r.get("endpoint"), r.get("billing_mode"),
                        ts, ts,
                        int(tok.get("input", 0) or 0), int(tok.get("output", 0) or 0),
                        int(tok.get("cached", 0) or 0), int(tok.get("total", 0) or 0),
                        float(r.get("cost", 0.0) or 0.0),
                        r.get("tok_per_sec"),
                        _ecosystem_blob(r), now, now,
                    ),
                )
                written += 1
            con.commit()
        finally:
            con.close()
    except Exception as e:  # noqa: BLE001 — store must never break the scan
        _log.exception("history upsert failed: %s", e)
    return written


def mark_absent(seen_keys: Set[Tuple[str, str]]) -> None:
    """Flag rows whose (agent, id) was NOT in the latest scan as no longer on
    disk (``source_present=0``). Never deletes — the rollup is what survives
    agent pruning, so those rows are exactly the ones we must keep."""
    try:
        con = _connect()
        try:
            present = con.execute(
                "SELECT agent, id FROM sessions WHERE source_present=1"
            ).fetchall()
            gone = [(a, i) for (a, i) in ((r["agent"], r["id"]) for r in present)
                    if (a, i) not in seen_keys]
            if gone:
                con.executemany(
                    "UPDATE sessions SET source_present=0 WHERE agent=? AND id=?", gone
                )
                con.commit()
        finally:
            con.close()
    except Exception as e:  # noqa: BLE001
        _log.exception("history mark_absent failed: %s", e)


# ── read path ────────────────────────────────────────────────────────────────

def _rehydrate(r: sqlite3.Row) -> Dict[str, Any]:
    """Turn a stored row back into a live-session-shaped dict."""
    try:
        ts = datetime.fromisoformat(r["last_ts"]) if r["last_ts"] else datetime.now(timezone.utc)
    except (ValueError, TypeError):
        ts = datetime.now(timezone.utc)
    out: Dict[str, Any] = {
        "id": r["id"],
        "agent": r["agent"],
        "project": r["project"],
        "model": r["model"],
        "provider": r["provider"],
        "endpoint": r["endpoint"],
        "billing_mode": r["billing_mode"],
        "timestamp": ts,
        "tokens": {
            "input": r["input"], "output": r["output"],
            "cached": r["cached"], "total": r["total"],
        },
        "cost": r["cost"],
        "tok_per_sec": r["tok_per_sec"],
        "source_present": bool(r["source_present"]),
        "transcript_archived": bool(r["transcript_archived"]),
        "summary_present": bool(r["summary_present"]),
        "from_history": True,
    }
    if r["ecosystem_json"]:
        try:
            eco = json.loads(r["ecosystem_json"])
            for k in _ECOSYSTEM_KEYS:
                if k in eco:
                    out[k] = eco[k]
        except (ValueError, TypeError):
            pass
    return out


def query(
    from_: Optional[str] = None,
    to: Optional[str] = None,
    agents: Optional[Iterable[str]] = None,
    models: Optional[Iterable[str]] = None,
    projects: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    """Return stored sessions as live-session-shaped dicts.

    ``from_`` / ``to`` are UTC ISO bounds compared against ``last_ts`` in SQL
    (indexed), so only in-window rows load — never the whole history. Each of
    ``agents`` / ``models`` / ``projects`` is an optional allow-list; an empty
    or omitted list means "no filter" (i.e. All). Never raises."""
    where: List[str] = []
    params: List[Any] = []
    if from_:
        where.append("last_ts >= ?"); params.append(from_)
    if to:
        where.append("last_ts <= ?"); params.append(to)
    for col, vals in (("agent", agents), ("model", models), ("project", projects)):
        vals = [v for v in (vals or []) if v]
        if vals:
            where.append(f"{col} IN ({','.join('?' * len(vals))})")
            params.extend(vals)
    sql = "SELECT * FROM sessions"
    if where:
        sql += " WHERE " + " AND ".join(where)
    try:
        con = _connect()
        try:
            return [_rehydrate(r) for r in con.execute(sql, params).fetchall()]
        finally:
            con.close()
    except Exception as e:  # noqa: BLE001
        _log.exception("history query failed: %s", e)
        return []


def coverage() -> Dict[str, Any]:
    """Earliest stored date + per-agent present/pruned counts, for the UI's
    data-availability notice."""
    out: Dict[str, Any] = {"earliest": None, "by_agent": {}, "total_sessions": 0}
    try:
        con = _connect()
        try:
            row = con.execute("SELECT MIN(first_ts) AS e, COUNT(*) AS n FROM sessions").fetchone()
            out["earliest"] = row["e"]
            out["total_sessions"] = row["n"] or 0
            for r in con.execute(
                """SELECT agent,
                          SUM(source_present) AS present,
                          SUM(CASE WHEN source_present=0 THEN 1 ELSE 0 END) AS pruned,
                          SUM(summary_present) AS summarized
                   FROM sessions GROUP BY agent"""
            ).fetchall():
                out["by_agent"][r["agent"]] = {
                    "present": r["present"] or 0,
                    "pruned": r["pruned"] or 0,
                    "summarized": r["summarized"] or 0,
                }
        finally:
            con.close()
    except Exception as e:  # noqa: BLE001
        _log.exception("history coverage failed: %s", e)
    return out


def storage_stats() -> Dict[str, Any]:
    """Row counts + bytes per tier per agent, for the Settings storage readout."""
    out: Dict[str, Any] = {"by_agent": {}, "transcript_bytes": 0, "total_sessions": 0}

    def _agent_row(a: str) -> Dict[str, Any]:
        return out["by_agent"].setdefault(
            a, {"sessions": 0, "transcripts": 0, "transcript_bytes": 0, "summaries": 0}
        )
    try:
        con = _connect()
        try:
            for r in con.execute("SELECT agent, COUNT(*) AS n FROM sessions GROUP BY agent"):
                _agent_row(r["agent"])["sessions"] = r["n"]
                out["total_sessions"] += r["n"]
            for r in con.execute(
                "SELECT agent, COUNT(*) AS n, COALESCE(SUM(bytes),0) AS b FROM transcripts GROUP BY agent"
            ):
                row = _agent_row(r["agent"])
                row["transcripts"] = r["n"]; row["transcript_bytes"] = r["b"]
                out["transcript_bytes"] += r["b"]
            for r in con.execute("SELECT agent, COUNT(*) AS n FROM summaries GROUP BY agent"):
                _agent_row(r["agent"])["summaries"] = r["n"]
        finally:
            con.close()
    except Exception as e:  # noqa: BLE001
        _log.exception("history storage_stats failed: %s", e)
    return out


# ── tier 2: transcript archive ───────────────────────────────────────────────

def put_transcript(agent: str, id: str, text: str) -> int:
    """Archive (or replace) a compressed transcript blob. Returns stored bytes."""
    blob = zlib.compress(text.encode("utf-8", errors="replace"))
    now = datetime.now(timezone.utc).isoformat()
    try:
        con = _connect()
        try:
            con.execute(
                """INSERT INTO transcripts (agent, id, blob, bytes, archived_at)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(agent, id) DO UPDATE SET
                       blob=excluded.blob, bytes=excluded.bytes, archived_at=excluded.archived_at""",
                (agent, id, blob, len(blob), now),
            )
            con.execute(
                "UPDATE sessions SET transcript_archived=1 WHERE agent=? AND id=?", (agent, id)
            )
            con.commit()
        finally:
            con.close()
        return len(blob)
    except Exception as e:  # noqa: BLE001
        _log.exception("history put_transcript failed: %s", e)
        return 0


def get_transcript(agent: str, id: str) -> Optional[str]:
    try:
        con = _connect()
        try:
            r = con.execute(
                "SELECT blob FROM transcripts WHERE agent=? AND id=?", (agent, id)
            ).fetchone()
        finally:
            con.close()
        if r and r["blob"] is not None:
            return zlib.decompress(r["blob"]).decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        _log.exception("history get_transcript failed: %s", e)
    return None


def delete_transcripts(agent: Optional[str] = None, older_than_days: Optional[int] = None) -> int:
    """Purge tier-2 transcript blobs (freeing space) while leaving the core
    rollup and any summaries intact. Optionally scoped by agent and/or age.
    Returns the number of blobs deleted."""
    where: List[str] = []
    params: List[Any] = []
    if agent:
        where.append("agent=?"); params.append(agent)
    if older_than_days is not None:
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()
        where.append("archived_at < ?"); params.append(cutoff)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    try:
        con = _connect()
        try:
            doomed = con.execute(
                "SELECT agent, id FROM transcripts" + clause, params
            ).fetchall()
            con.execute("DELETE FROM transcripts" + clause, params)
            for r in doomed:
                con.execute(
                    "UPDATE sessions SET transcript_archived=0 WHERE agent=? AND id=?",
                    (r["agent"], r["id"]),
                )
            con.commit()
            return len(doomed)
        finally:
            con.close()
    except Exception as e:  # noqa: BLE001
        _log.exception("history delete_transcripts failed: %s", e)
        return 0


# ── tier 3: summaries ────────────────────────────────────────────────────────

def put_summary(agent: str, id: str, summary: str) -> None:
    """Persist a generated summary; survives even after the transcript is gone."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        con = _connect()
        try:
            con.execute(
                """INSERT INTO summaries (agent, id, summary, created_at) VALUES (?,?,?,?)
                   ON CONFLICT(agent, id) DO UPDATE SET summary=excluded.summary, created_at=excluded.created_at""",
                (agent, id, summary, now),
            )
            con.execute(
                "UPDATE sessions SET summary_present=1 WHERE agent=? AND id=?", (agent, id)
            )
            con.commit()
        finally:
            con.close()
    except Exception as e:  # noqa: BLE001
        _log.exception("history put_summary failed: %s", e)


def get_summary(agent: str, id: str) -> Optional[str]:
    try:
        con = _connect()
        try:
            r = con.execute(
                "SELECT summary FROM summaries WHERE agent=? AND id=?", (agent, id)
            ).fetchone()
        finally:
            con.close()
        return r["summary"] if r else None
    except Exception as e:  # noqa: BLE001
        _log.exception("history get_summary failed: %s", e)
        return None
