"""Shared helpers for per-agent harness panels.

Every extractor in this package answers one question: what does THIS harness keep
on disk that the generic session scan can't show? The output is a small, uniform
document (see `panel`) that one frontend renderer can draw for any agent.

Three rules hold everywhere in this package, and the helpers here exist to make
them the path of least resistance:

1. **Read-only, always.** We never write into an agent's directory, and every
   SQLite handle is opened through `ro_sqlite` — Codex, Cursor, VS Code, LM Studio
   and Hermes all hold live WAL locks while their app is running, and a plain
   `sqlite3.connect` on a locked DB can block or, worse, create a stray `-wal`.
2. **Never read credential values.** Panels report that a credential file exists,
   never what's in it. Two traps worth remembering: Cursor keeps live tokens in
   the same key-value table as ordinary UI state, and `~/.vibe/.env` sits at the
   harness root rather than under a `credentials/` dir — so a filename-based skip
   list misses both. Prefer an allowlist of keys you actually want.
3. **Never surface bulk content.** Whole-file snapshots (Grok rewind points),
   raw model I/O (Cursor `agentKv:blob:*`), captured page DOM, and voice
   transcripts stay out entirely: report counts, paths and timestamps instead.

   Short labels the user wrote themselves — a thread title, a job name, an
   automation's display name — are a different matter, and the dashboard already
   shows them elsewhere (`main.py` truncates display text to 120 characters in
   half a dozen places). Panels follow that same convention via `preview`, so a
   title stays a title and never becomes an accidental transcript dump. Codex in
   particular auto-titles a thread with the user's entire first message, which is
   how a 900-character "title" reaches a table column if nothing trims it.

Extractors must also never raise. A malformed config or a half-written DB is
normal on a live machine; `safe` turns any failure into an omitted section rather
than a 500 that takes the whole page down.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

logger = logging.getLogger("tokentelemetry.harness_panels")

HOME = Path.home()

# Walking a harness root is unbounded in principle — ~/.claude is 182k files and
# ~/.hermes is 156k. The cap has to clear the largest real harness, because a
# truncated byte total is worse than no total: it reported ~/.claude as 964 MB
# when it is 4.0 GB, which reads as fact rather than as a floor. Sized to cover
# the biggest store we know of with headroom; `dir_size` still returns a
# completeness flag so anything past it is labelled, never silently truncated.
MAX_WALK_ENTRIES = 400_000


def tilde(path: Path | str) -> str:
    """Render a path with ~ so panels don't leak the home directory name."""
    text = str(path)
    home = str(HOME)
    return "~" + text[len(home):] if text.startswith(home) else text


def safe(fn: Callable[[], Any], what: str) -> Any:
    """Run an extractor step, swallowing failure.

    A panel is a nice-to-have view over someone else's data format. If Codex
    ships a config change tomorrow we want that one section to disappear, not
    the agent page to 500.
    """
    try:
        return fn()
    except Exception:
        logger.debug("harness panel step failed: %s", what, exc_info=True)
        return None


def ro_sqlite(path: Path) -> Optional[sqlite3.Connection]:
    """Open a SQLite file strictly read-only, or return None.

    `mode=ro` matters for more than politeness: it guarantees we can't create a
    `-wal`/`-shm` pair next to an agent's database, and it lets us read a file
    the owning app currently has open. `immutable=1` would be faster but is
    wrong here — these databases are being written while we read.
    """
    if not path.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2.0)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception:
        logger.debug("could not open %s read-only", path, exc_info=True)
        return None


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (name,)
    ).fetchone()
    return row is not None


# Matches the display truncation main.py already applies to session titles and
# prompt previews. Anything longer than this in a label column is not a label.
PREVIEW_CHARS = 120


def preview(text: Any, limit: int = PREVIEW_CHARS) -> str:
    """Trim a user-authored label to display length, collapsing whitespace.

    Codex titles a thread with the user's whole first message, so an untrimmed
    `title` column turns into a transcript dump — multi-line, hundreds of
    characters, complete with pasted paths. Newlines are collapsed first so a
    truncated label can't smuggle in the shape of the original text.
    """
    if text is None:
        return "—"
    s = " ".join(str(text).split())
    if not s:
        return "—"
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def drop_empty_columns(columns: List[str], rows: List[List[Any]],
                       keep: Optional[Sequence[str]] = None) -> tuple[List[str], List[List[Any]]]:
    """Remove columns whose every value is empty.

    Agents declare columns their schema supports but does not always populate —
    Antigravity's `conversation_summaries` has `agent_name` and `status` columns
    that are empty on every one of 131 rows. Rendering those as a wall of em
    dashes suggests the data is missing rather than that the agent never fills
    them in. `keep` pins columns that should survive even when empty.
    """
    if not rows:
        return columns, rows
    keep_set = set(keep or ())
    live = [
        i for i, name in enumerate(columns)
        if name in keep_set or any(
            r[i] not in (None, "", "—", 0, False) for r in rows if i < len(r)
        )
    ]
    if len(live) == len(columns):
        return columns, rows
    return ([columns[i] for i in live],
            [[r[i] for i in live if i < len(r)] for r in rows])


def human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def dir_size(path: Path, cap: int = MAX_WALK_ENTRIES) -> tuple[int, bool]:
    """Sum a directory's file sizes, stopping at `cap` entries.

    Returns (bytes, complete). `complete=False` means we bailed early and the
    number is a floor, which callers must say out loud rather than presenting a
    truncated total as fact.

    This is *apparent* size (`st_size`), so it reads a little under `du`, which
    counts allocated blocks — about 0.5 GB lower across ~/.claude's 182k files.
    Apparent size is the right choice here because the question a user is asking
    is "how much data is this agent keeping", not "how many blocks did the
    filesystem reserve"; the gap is block slack, not content.

    Symlinks are never followed, so a harness that links into a shared model or
    skill store can't inflate its own total with someone else's bytes.
    """
    total = 0
    seen = 0
    stack = [path]
    # os.scandir over os.walk: DirEntry carries the stat data already fetched
    # while reading the directory, so a 182k-file tree costs one syscall per
    # entry instead of two. That is the difference between ~2s and ~200ms here.
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        # Skip symlinks outright rather than counting the link
                        # itself: several harnesses link into a shared skill or
                        # model store, and neither the target's bytes nor the
                        # link's own few bytes belong in this agent's total.
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                            continue
                        seen += 1
                        if seen > cap:
                            return total, False
                        total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total, True


def newest_mtime(paths: Sequence[Path]) -> Optional[float]:
    """Latest mtime across the given paths, ignoring ones that don't exist.

    Used for "is this agent still in use?". Directory mtimes are deliberately
    included: for stores that only ever add files (session dirs), the parent's
    mtime is a cheap proxy that avoids walking the whole tree.
    """
    best: Optional[float] = None
    for p in paths:
        try:
            m = p.stat().st_mtime
        except OSError:
            continue
        if best is None or m > best:
            best = m
    return best


def iso(ts: Optional[float]) -> Optional[str]:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def iso_ms(value: Any) -> Optional[str]:
    """Convert a timestamp that may be in seconds or milliseconds.

    Codex mixes both in the same database — some columns are epoch seconds and
    the `_ms` suffixed ones are milliseconds — so callers can't assume. Anything
    past the year 2286 in seconds is treated as milliseconds.
    """
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    if n > 1e11:
        n /= 1000.0
    return iso(n)


# --- document builders ------------------------------------------------------

def section(
    kind: str,
    title: str,
    source: str,
    *,
    columns: Optional[List[str]] = None,
    rows: Optional[List[List[Any]]] = None,
    fields: Optional[List[Dict[str, Any]]] = None,
    meters: Optional[List[Dict[str, Any]]] = None,
    tree: Optional[List[Dict[str, Any]]] = None,
    count: Optional[int] = None,
    total: Optional[int] = None,
    severity: Optional[str] = None,
    note: Optional[str] = None,
    empty_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Build one panel section.

    `kind` selects the frontend renderer (table / meter / fields / tree). `total`
    exists so a truncated table can say "showing 3 of 132" instead of quietly
    implying 3 is all there is — silent truncation reads as completeness.

    `empty_reason` marks the "installed, zero rows" state, which is genuinely
    different from "not installed" and from "not available": the capability is
    real and the user could use it, they just haven't. Hiding the section would
    teach them the feature doesn't exist.
    """
    doc: Dict[str, Any] = {"kind": kind, "title": title, "source": source}
    if columns is not None:
        doc["columns"] = columns
    if rows is not None:
        doc["rows"] = rows
    # An explicit count wins for every section kind. Deriving it only from rows
    # silently dropped the headline number on tree and meter sections, which
    # have no rows at all.
    if count is not None:
        doc["count"] = count
    elif rows is not None:
        doc["count"] = len(rows)
    if fields is not None:
        doc["fields"] = fields
    if meters is not None:
        doc["meters"] = meters
    if tree is not None:
        doc["tree"] = tree
    if total is not None:
        doc["total"] = total
    if severity:
        doc["severity"] = severity
    if note:
        doc["note"] = note
    if empty_reason:
        doc["empty_reason"] = empty_reason
    return doc


def field(label: str, value: Any, *, severity: Optional[str] = None,
          hint: Optional[str] = None) -> Dict[str, Any]:
    """One row of a key/value section. `severity` drives the warning pill."""
    doc: Dict[str, Any] = {"label": label, "value": value}
    if severity:
        doc["severity"] = severity
    if hint:
        doc["hint"] = hint
    return doc


def meter(label: str, pct: float, *, detail: Optional[str] = None,
          resets_at: Optional[str] = None, severity: Optional[str] = None) -> Dict[str, Any]:
    """A proportional gauge. `pct` is 0-100 and is clamped, not trusted."""
    p = max(0.0, min(100.0, float(pct)))
    doc: Dict[str, Any] = {"label": label, "pct": round(p, 1)}
    if detail:
        doc["detail"] = detail
    if resets_at:
        doc["resets_at"] = resets_at
    doc["severity"] = severity or ("crit" if p >= 90 else "warn" if p >= 70 else "ok")
    return doc


def unavailable(kind: str, reason: str) -> Dict[str, Any]:
    """Name a capability we are NOT showing, and why.

    Mirrors `_FEATURES_NOT_DETECTABLE` in main.py. Absence must read as "not
    exposed locally", never as "we forgot to build it" — so an extractor that
    knows a feature exists but has nothing to show should say so here rather
    than omitting the section silently.
    """
    return {"kind": kind, "reason": reason}


def panel(
    agent: str,
    root: Path,
    *,
    sections: List[Dict[str, Any]],
    not_available: Optional[List[Dict[str, Any]]] = None,
    version: Optional[str] = None,
    last_active: Optional[str] = None,
    disk: Optional[Dict[str, Any]] = None,
    file_count: Optional[int] = None,
) -> Dict[str, Any]:
    """Assemble the panel document returned by GET /agents/{agent}/panel."""
    return {
        "agent": agent,
        "installed": True,
        "root": tilde(root),
        "version": version,
        "last_active": last_active,
        "disk": disk,
        "file_count": file_count,
        "sections": [s for s in sections if s],
        "not_available": not_available or [],
    }


def not_installed(agent: str) -> Dict[str, Any]:
    return {"agent": agent, "installed": False, "sections": [], "not_available": []}


# --- RRULE ------------------------------------------------------------------

_DAYS = {"MO": "Monday", "TU": "Tuesday", "WE": "Wednesday", "TH": "Thursday",
         "FR": "Friday", "SA": "Saturday", "SU": "Sunday"}
_FREQ = {"HOURLY": "hour", "DAILY": "day", "WEEKLY": "week", "MONTHLY": "month",
         "MINUTELY": "minute", "YEARLY": "year"}


def rrule_human(rule: str) -> str:
    """Render an RFC-5545 RRULE as a short English phrase.

    Deliberately not a full RFC-5545 implementation — Codex automations use a
    narrow slice (FREQ, INTERVAL, BYDAY, BYHOUR, BYMINUTE) and a real rrule
    dependency isn't worth it for one label. Anything we don't recognise falls
    through to the raw rule string, which is still more useful to a user than a
    wrong guess.

    BYHOUR/BYMINUTE are UTC-naive in the source and rendered as-is; the caller
    labels them so nobody reads a wall-clock time that isn't theirs.
    """
    if not rule:
        return ""
    body = rule.split("RRULE:", 1)[-1]
    parts: Dict[str, str] = {}
    for chunk in body.split(";"):
        if "=" in chunk:
            k, v = chunk.split("=", 1)
            parts[k.strip().upper()] = v.strip().upper()

    freq = parts.get("FREQ", "")
    if freq not in _FREQ:
        return rule

    interval = parts.get("INTERVAL", "1")
    try:
        n = max(1, int(interval))
    except ValueError:
        n = 1

    unit = _FREQ[freq]
    base = f"Every {unit}" if n == 1 else f"Every {n} {unit}s"

    days = parts.get("BYDAY")
    if days:
        names = [_DAYS.get(d, d) for d in days.split(",")]
        if freq == "WEEKLY":
            base = "Every " + ", ".join(names) if n == 1 else f"{base} on " + ", ".join(names)
        else:
            base = f"{base} on " + ", ".join(names)

    hour = parts.get("BYHOUR")
    minute = parts.get("BYMINUTE", "0")
    if hour is not None:
        try:
            base += f" at {int(hour):02d}:{int(minute):02d}"
        except ValueError:
            pass
    return base
