"""Hermes Agent panel.

Hermes is the one agent that already owns a sub-dashboard (`/hermes/*`), so
this panel deliberately does not restate it. Sessions, kanban, memory, skills,
profiles, schedules, soul, tools and the gateway all have their own pages; what
follows is the material none of them read:

  state.db -> session_model_usage   Hermes' OWN billing record: per provider
                                    and model, the call count, every token
                                    class it counts (including reasoning
                                    tokens, which TokenTelemetry does not
                                    derive) and its own cost figure with a
                                    status saying how much it trusts it.
  spawn-ledger.json                 the processes Hermes currently believes it
                                    has running.

The panel carries a `dashboard` link so the page can hand the reader on to the
richer surface rather than competing with it.

Credentials are never opened. `~/.hermes/.env`, `auth.json`, `auth.json.bak`,
`google_client_secret.json` and `google_token.json` all sit at this root; they
are reported as present and never read. `spawn-ledger.json` records a full
argv containing absolute paths, so only the pid, purpose and start time are
surfaced.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import (
    dir_size, field, human_bytes, iso, newest_mtime, not_installed, panel,
    ro_sqlite, safe, section, table_exists, tilde, unavailable,
)
from . import paths

DASHBOARD = {
    "href": "/hermes",
    "label": "Open Hermes dashboard",
    "hint": "Sessions, kanban, memory, skills, profiles, schedules and the gateway "
            "each have their own page.",
}

#: Credential-shaped files at the Hermes root. Existence only — never opened.
_SECRET_FILES = (
    ".env", "auth.json", "auth.json.bak",
    "google_client_secret.json", "google_token.json",
)


def _usage() -> Optional[Dict[str, Any]]:
    """Hermes' own billing ledger, per provider.

    Worth surfacing because it is the only place an agent states what it
    actually paid rather than what a price list implies. On a subscription-
    routed install every row comes back at zero, which is itself the answer:
    the tokens are real and the money is not.
    """
    db = paths.HERMES_DIR / "state.db"
    conn = ro_sqlite(db)
    if conn is None:
        return None
    try:
        if not table_exists(conn, "session_model_usage"):
            return None
        rows = conn.execute(
            "SELECT billing_provider, billing_mode, COUNT(*) sessions, "
            "       SUM(api_call_count) calls, "
            "       SUM(input_tokens + output_tokens) tokens, "
            "       SUM(cache_read_tokens) cache, "
            "       SUM(reasoning_tokens) reasoning, "
            "       SUM(COALESCE(actual_cost_usd, 0)) actual "
            "FROM session_model_usage "
            "GROUP BY billing_provider, billing_mode "
            "ORDER BY tokens DESC"
        ).fetchall()
        statuses = conn.execute(
            "SELECT COALESCE(cost_status, 'unrecorded') s, COUNT(*) n "
            "FROM session_model_usage GROUP BY 1"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return None

    table: List[List[Any]] = []
    billed = 0.0
    for r in rows:
        billed += float(r["actual"] or 0)
        table.append([
            str(r["billing_provider"] or "—"),
            # An empty billing_mode is how Hermes records "not stated", which
            # is different from a mode it named.
            str(r["billing_mode"] or "not stated"),
            r["calls"] or 0,
            r["tokens"] or 0,
            r["cache"] or 0,
            r["reasoning"] or 0,
            f"${float(r['actual'] or 0):.2f}",
        ])

    mix = ", ".join(f"{r['n']} {r['s']}" for r in statuses)
    note = (
        f"Hermes' own figure, not a price-list estimate. Cost status across "
        f"rows: {mix}. Everything here bills through a subscription or a free "
        f"tier, so the tokens are real and the amount charged is $0.00 — which "
        f"is why the dashboard's API-equivalent cost reads far higher."
        if billed == 0 else
        f"Hermes' own figure, not a price-list estimate. Cost status across "
        f"rows: {mix}."
    )
    return section(
        "table", "Billing by provider", tilde(paths.HERMES_DIR / "state.db")
        + " → session_model_usage",
        columns=["Provider", "Billing mode", "Calls", "Tokens", "Cache read",
                 "Reasoning", "Hermes billed"],
        rows=table, count=len(table), note=note,
    )


def _models() -> Optional[Dict[str, Any]]:
    """Per-model call and token mix, including reasoning tokens."""
    conn = ro_sqlite(paths.HERMES_DIR / "state.db")
    if conn is None:
        return None
    try:
        if not table_exists(conn, "session_model_usage"):
            return None
        rows = conn.execute(
            "SELECT model, SUM(api_call_count) calls, "
            "       SUM(input_tokens) inp, SUM(output_tokens) out, "
            "       SUM(cache_read_tokens) cache, SUM(reasoning_tokens) reasoning "
            "FROM session_model_usage GROUP BY model "
            "ORDER BY calls DESC LIMIT 20"
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return None
    return section(
        "table", "Models routed", tilde(paths.HERMES_DIR / "state.db")
        + " → session_model_usage",
        columns=["Model", "Calls", "Input", "Output", "Cache read", "Reasoning"],
        rows=[[str(r["model"] or "—"), r["calls"] or 0, r["inp"] or 0,
               r["out"] or 0, r["cache"] or 0, r["reasoning"] or 0]
              for r in rows],
        count=len(rows),
        note="Hermes routes one session across several models. Reasoning tokens "
             "are counted by Hermes itself and are not derivable from the "
             "transcript.",
    )


def _processes() -> Optional[Dict[str, Any]]:
    """Processes Hermes believes it is running, from its spawn ledger.

    The ledger stores a full argv with absolute paths; only the pid, purpose,
    install id and start time are surfaced.
    """
    path = paths.HERMES_DIR / "spawn-ledger.json"
    if not path.exists():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    entries = doc if isinstance(doc, list) else doc.get("entries")
    if not isinstance(entries, list) or not entries:
        return None
    rows = []
    for e in entries[:25]:
        if not isinstance(e, dict):
            continue
        rows.append([
            str(e.get("purpose") or "—"),
            e.get("pid") or "—",
            str(e.get("install") or "—"),
            iso(e.get("create_time")),
        ])
    if not rows:
        return None
    return section(
        "jobs", "Registered processes", tilde(path),
        columns=["Purpose", "PID", "Install", "Started"], rows=rows,
        count=len(rows),
        note="What the ledger records, which is not proof the process is still "
             "alive. Command lines are not shown — they carry absolute paths.",
    )


def _security() -> Optional[Dict[str, Any]]:
    """Which credential stores exist. Existence only; none is opened."""
    root = paths.HERMES_DIR
    present = [n for n in _SECRET_FILES if (root / n).exists()]
    if not present:
        return None
    return section(
        "permissions", "Credential stores", tilde(root),
        fields=[
            field("Files present", len(present),
                  hint="Detected by name only. TokenTelemetry never reads them."),
            field("Names", ", ".join(present)),
        ],
        note="Hermes keeps provider keys and Google OAuth tokens at its root. "
             "They are listed so you know they are there, never opened.",
    )


def _disk() -> Optional[Dict[str, Any]]:
    root = paths.HERMES_DIR
    total, complete = dir_size(root)
    parts = []
    for name in ("hermes-agent", "sessions", "cache", "logs", "node",
                 "state-snapshots", "memories", "image_cache"):
        p = root / name
        if not p.is_dir():
            continue
        size, _ = dir_size(p)
        if size:
            parts.append({"label": name, "bytes": size})
    parts.sort(key=lambda x: -x["bytes"])
    reclaim = sum(p["bytes"] for p in parts
                  if p["label"] in ("cache", "image_cache", "logs"))
    return {
        "total_bytes": total,
        "total_human": human_bytes(total),
        "complete": complete,
        "parts": parts[:6],
        "reclaimable_bytes": reclaim or None,
        "reclaimable_note": ("Caches and logs. Hermes regenerates them; sessions, "
                             "memories and state snapshots are not included."
                             if reclaim else None),
    }


def build_hermes(*, with_disk: bool = True) -> Dict[str, Any]:
    root = paths.HERMES_DIR
    if not root.is_dir():
        return not_installed("hermes")

    sections = [s for s in (
        safe(_usage, "hermes usage"),
        safe(_models, "hermes models"),
        safe(_processes, "hermes processes"),
        safe(_security, "hermes security"),
    ) if s]

    return panel(
        "hermes", root, sections=sections,
        dashboard=DASHBOARD,
        not_available=[unavailable(
            "sessions",
            "Hermes sessions, kanban, memory, skills, profiles, schedules and "
            "the gateway each have a dedicated page under /hermes, so they are "
            "not duplicated here.")],
        last_active=iso(newest_mtime([root / "sessions", root / "state.db"])),
        disk=safe(_disk, "hermes disk") if with_disk else None,
    )
