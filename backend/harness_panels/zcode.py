"""ZCode (Z.ai) harness panel.

The session scan already shows ZCode's sessions, tokens, models and cost by
reading `session` / `message` / `part` — the OpenCode-family tables. What it
does not read is the separate *telemetry ledger* ZCode keeps alongside them:

    model_usage   one row per model request: latency, time-to-first-token,
                  reasoning variant, retries, finish reason, context overflow
    turn_usage    one row per user turn: how many model requests and tool calls
                  a single turn actually cost
    tool_usage    one row per tool call, classified read-only / destructive and
                  carrying the approval it was granted
    local_setting the permission ruleset and mode in force per project
    workflow_*    scripted multi-agent runs

Two of those are unique to ZCode across every agent TokenTelemetry supports. No
other harness records a per-request reasoning level, and none classifies each
tool call as destructive and stores the approval decision next to it. That is
the panel: reliability, latency and trust posture, none of which the generic
session view can show.

Token totals are deliberately absent here — the session scan owns those, and a
panel that re-derived them from `model_usage` would disagree with the dashboard
the moment either side changed. This is the same split `base.live_quota` exists
to enforce for plan gauges.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import paths
from .base import (
    dir_size, field, human_bytes, iso, iso_ms, live_quota, newest_mtime,
    not_installed, panel, ro_sqlite, safe, section, table_exists, tilde,
    unavailable,
)


def _ms(value: Any) -> str:
    """Render a millisecond duration at a human scale, or an em dash."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "—"
    if n < 0:
        return "—"
    if n < 1000:
        return f"{n:.0f} ms"
    if n < 60_000:
        return f"{n / 1000:.1f} s"
    return f"{n / 60_000:.1f} min"


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


# ZCode's reasoning levels as they appear in `model_usage.variant`. "disabled"
# is a real setting, not missing data, so it is rendered rather than blanked.
_VARIANTS = {"high": "high", "medium": "medium", "low": "low",
             "disabled": "off", "": "—", None: "—"}


def _model_requests(conn: sqlite3.Connection, db: Path) -> Optional[Dict[str, Any]]:
    """Per model and reasoning level: throughput, latency and failures.

    Grouped by `variant` as well as `model_id` because the same model answers at
    a different speed and cost per level, and collapsing them hides exactly the
    trade-off a user would change their settings over.
    """
    if not table_exists(conn, "model_usage"):
        return None
    rows: List[List[Any]] = []
    total = 0
    for r in conn.execute(
        """SELECT model_id, variant, COUNT(*) AS n,
                  AVG(duration_ms) AS avg_ms,
                  AVG(time_to_first_token_ms) AS avg_ttft,
                  SUM(retry_count) AS retries,
                  SUM(CASE WHEN status <> 'completed' THEN 1 ELSE 0 END) AS incomplete
             FROM model_usage
            GROUP BY model_id, variant
            ORDER BY n DESC
            LIMIT 30"""
    ):
        total += _int(r["n"])
        rows.append([
            str(r["model_id"] or "—"),
            _VARIANTS.get(r["variant"], str(r["variant"])),
            _int(r["n"]),
            _ms(r["avg_ms"]),
            _ms(r["avg_ttft"]),
            _int(r["retries"]) or "—",
            _int(r["incomplete"]) or "—",
        ])
    if not rows:
        return None
    return section(
        "table", "Model requests", tilde(db) + " → model_usage",
        columns=["Model", "Reasoning", "Requests", "Avg latency",
                 "Avg first token", "Retries", "Incomplete"],
        rows=rows, count=total,
        note="ZCode is the only supported agent that records the reasoning "
             "level of each individual request, so the same model appears once "
             "per level it answered at.",
    )


def _turns(conn: sqlite3.Connection, db: Path) -> Optional[Dict[str, Any]]:
    """Turn-level shape: what one user message actually costs to answer."""
    if not table_exists(conn, "turn_usage"):
        return None
    r = conn.execute(
        """SELECT COUNT(*) AS n,
                  AVG(duration_ms) AS avg_ms,
                  AVG(time_to_first_token_ms) AS avg_ttft,
                  AVG(model_request_count) AS avg_reqs,
                  AVG(tool_call_count) AS avg_tools,
                  SUM(tool_error_count) AS tool_errors,
                  SUM(model_retry_count) AS retries,
                  SUM(context_exceeded) AS ctx,
                  SUM(cancelled_by_user) AS cancelled,
                  SUM(CASE WHEN status <> 'completed' THEN 1 ELSE 0 END) AS unfinished
             FROM turn_usage"""
    ).fetchone()
    if r is None or not _int(r["n"]):
        return None

    ctx, cancelled = _int(r["ctx"]), _int(r["cancelled"])
    fields = [
        field("Turns recorded", _int(r["n"])),
        field("Average turn", _ms(r["avg_ms"]),
              hint="A mean: the ledger stores per-turn durations, not percentiles."),
        field("Time to first token", _ms(r["avg_ttft"])),
        field("Model requests per turn", f"{float(r['avg_reqs'] or 0):.1f}"),
        field("Tool calls per turn", f"{float(r['avg_tools'] or 0):.1f}"),
        field("Tool errors", _int(r["tool_errors"]) or "—"),
        field("Model retries", _int(r["retries"]) or "—"),
        field("Context overflows", ctx or "—",
              severity="warn" if ctx else None,
              hint="Turns where the conversation outgrew the context window."
                   if ctx else None),
        field("Cancelled by you", cancelled or "—"),
        field("Unfinished", _int(r["unfinished"]) or "—"),
    ]
    return section(
        "fields", "Turn cost and latency", tilde(db) + " → turn_usage",
        fields=fields, count=_int(r["n"]),
        severity="warn" if ctx else None,
        note="A turn is one user message and everything ZCode did to answer "
             "it. The session view shows totals; this shows what each round "
             "trip took.",
    )


def _tools(conn: sqlite3.Connection, db: Path) -> Optional[Dict[str, Any]]:
    """Per-tool ledger, including the safety classification ZCode records.

    `read_only` / `destructive` / `approval_status` are ZCode's own labels, not
    ours — worth surfacing because they are the harness's account of what it was
    permitted to do, which no other agent writes down.
    """
    if not table_exists(conn, "tool_usage"):
        return None
    rows: List[List[Any]] = []
    total = 0
    for r in conn.execute(
        """SELECT tool_name,
                  COUNT(*) AS n,
                  SUM(read_only) AS ro,
                  SUM(destructive) AS destructive,
                  AVG(duration_ms) AS avg_ms,
                  SUM(output_bytes) AS bytes,
                  SUM(truncated) AS truncated,
                  SUM(CASE WHEN status <> 'completed' THEN 1 ELSE 0 END) AS failed
             FROM tool_usage
            GROUP BY tool_name
            ORDER BY n DESC
            LIMIT 40"""
    ):
        total += _int(r["n"])
        rows.append([
            str(r["tool_name"] or "—"),
            _int(r["n"]),
            _int(r["ro"]) or "—",
            _int(r["destructive"]) or "—",
            _ms(r["avg_ms"]),
            human_bytes(_int(r["bytes"])),
            _int(r["truncated"]) or "—",
            _int(r["failed"]) or "—",
        ])
    if not rows:
        return None

    destructive = sum(1 for row in rows if row[3] != "—")
    return section(
        "table", "Tool calls", tilde(db) + " → tool_usage",
        columns=["Tool", "Calls", "Read-only", "Destructive", "Avg duration",
                 "Output", "Truncated", "Failed"],
        rows=rows, count=total,
        severity="warn" if destructive else None,
        note="ZCode labels every call read-only or destructive as it makes it. "
             "Only the byte totals of tool output are read here, never the "
             "output itself.",
    )


def _approvals(conn: sqlite3.Connection, db: Path) -> Optional[Dict[str, Any]]:
    """How tool calls were authorised, in ZCode's own vocabulary."""
    if not table_exists(conn, "tool_usage"):
        return None
    rows = [
        [str(r["approval_status"] or "—"), _int(r["n"])]
        for r in conn.execute(
            """SELECT approval_status, COUNT(*) AS n FROM tool_usage
                GROUP BY approval_status ORDER BY n DESC LIMIT 10""")
    ]
    if not rows or (len(rows) == 1 and rows[0][0] in ("none", "—")):
        # A single "none" bucket means nothing was ever gated, which the
        # permission-mode section already says more directly.
        return None
    return section(
        "table", "Tool approvals", tilde(db) + " → tool_usage",
        columns=["Approval", "Calls"], rows=rows,
        count=sum(r[1] for r in rows))


# Values the permission ruleset may carry that are user-authored paths or
# commands. Only the SHAPE of the ruleset is reported — counts and the mode —
# never a rule's text, which routinely contains project paths.
def _permissions(conn: sqlite3.Connection, db: Path) -> Optional[Dict[str, Any]]:
    """Permission mode and ruleset size per scope, without the rule text."""
    if not table_exists(conn, "local_setting"):
        return None
    modes: List[str] = []
    allow = deny = ask = 0
    scopes = 0
    for r in conn.execute(
        """SELECT scope, namespace, key, value FROM local_setting
            WHERE namespace = 'permission' LIMIT 200"""
    ):
        try:
            payload = json.loads(r["value"] or "{}")
        except (TypeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        if r["key"] == "mode":
            mode = payload.get("mode")
            if isinstance(mode, str) and mode and mode not in modes:
                modes.append(mode)
        elif r["key"] == "ruleset":
            scopes += 1
            for bucket, name in ((payload.get("allow"), "allow"),
                                 (payload.get("deny"), "deny"),
                                 (payload.get("ask"), "ask")):
                n = len(bucket) if isinstance(bucket, list) else 0
                if name == "allow":
                    allow += n
                elif name == "deny":
                    deny += n
                else:
                    ask += n
    if not modes and not scopes:
        return None

    # "yolo" is ZCode's own name for its unrestricted mode; flagging it is the
    # point of showing this at all.
    risky = any(m.lower() in ("yolo", "auto", "full") for m in modes)
    fields = [
        field("Mode", ", ".join(modes) if modes else "—",
              severity="warn" if risky else None,
              hint="ZCode runs tools without asking in this mode."
                   if risky else None),
        field("Scopes with a ruleset", scopes or "—"),
        field("Allow rules", allow or "—"),
        field("Deny rules", deny or "—"),
        field("Ask rules", ask or "—"),
    ]
    return section(
        "permissions", "Permission posture", tilde(db) + " → local_setting",
        fields=fields, severity="warn" if risky else None,
        note="Rule counts only. The rules themselves name commands and project "
             "paths, so their text is not read.",
    )


def _workflows(conn: sqlite3.Connection, db: Path) -> Optional[Dict[str, Any]]:
    """Scripted multi-agent runs, if this install has any."""
    if not table_exists(conn, "workflow_run"):
        return None
    rows: List[List[Any]] = []
    for r in conn.execute(
        """SELECT name, kind, status, current_phase, budget_spent, time_created
             FROM workflow_run ORDER BY time_created DESC LIMIT 20"""
    ):
        rows.append([
            str(r["name"] or "—"),
            str(r["kind"] or "—"),
            str(r["status"] or "—"),
            str(r["current_phase"] or "—"),
            _int(r["budget_spent"]) or "—",
            iso_ms(r["time_created"]),
        ])
    total = conn.execute("SELECT COUNT(*) FROM workflow_run").fetchone()[0]
    defs = 0
    if table_exists(conn, "workflow_definition"):
        defs = conn.execute("SELECT COUNT(*) FROM workflow_definition").fetchone()[0]
    return section(
        "table", "Workflow runs", tilde(db) + " → workflow_run",
        columns=["Name", "Kind", "Status", "Phase", "Tokens", "Started"],
        rows=rows, count=len(rows) or None, total=_int(total) or None,
        empty_reason=(None if rows else (
            f"ZCode can run scripted multi-agent workflows. {defs} are defined "
            "here and none has run yet." if defs else
            "ZCode can run scripted multi-agent workflows. None are defined "
            "here yet.")),
    )


def build(*, with_disk: bool = True) -> Dict[str, Any]:
    root = paths.zcode_dir()
    db = paths.zcode_db()
    if not root.is_dir():
        return not_installed("zcode")

    sections: List[Dict[str, Any]] = []
    quota = safe(lambda: live_quota("zcode"), "zcode quota")
    if quota:
        sections.append(quota)

    conn = ro_sqlite(db)
    if conn is not None:
        try:
            for step, what in (
                (_model_requests, "zcode model_usage"),
                (_turns, "zcode turn_usage"),
                (_tools, "zcode tool_usage"),
                (_approvals, "zcode approvals"),
                (_permissions, "zcode permissions"),
                (_workflows, "zcode workflows"),
            ):
                built = safe(lambda s=step: s(conn, db), what)
                if built:
                    sections.append(built)
        finally:
            conn.close()

    not_available = [unavailable(
        "schedules", "ZCode has no local scheduling store.")]
    if not quota:
        not_available.append(unavailable(
            "quota",
            "ZCode's coding-plan usage lives in the Z.ai account API; nothing "
            "local reports it."))

    return panel(
        "zcode", root, sections=sections,
        not_available=not_available,
        last_active=iso(newest_mtime([db, root / "cli", root])),
        disk=safe(lambda: _disk(root), "zcode disk") if with_disk else None,
    )


def _disk(root: Path, floor: int = 256 * 1024) -> Optional[Dict[str, Any]]:
    """Bytes ZCode keeps, broken down by top-level child.

    Same shape and threshold as the other CLI panels use, so the disk card
    renders identically for every agent.
    """
    if not root.is_dir():
        return None
    parts: List[Dict[str, Any]] = []
    total = 0
    complete = True
    for child in root.iterdir():
        try:
            if child.is_dir():
                size, ok = dir_size(child)
                complete = complete and ok
            elif child.is_file():
                size = child.lstat().st_size
            else:
                continue
        except OSError:
            continue
        total += size
        if size > floor:
            parts.append({"label": child.name, "bytes": size})
    parts.sort(key=lambda p: -p["bytes"])
    return {"total_bytes": total, "total_human": human_bytes(total),
            "parts": parts[:8], "complete": complete}
