"""Codex panel — schedules, blast radius, threads, delegation.

Codex is the densest harness on disk. The generic session scan reads
`~/.codex/sessions/**/rollout-*.jsonl`; everything here comes from the Electron
app's sibling stores, which the scan never opens:

  automations/<id>/automation.toml   cron + heartbeat schedules (RFC-5545 rrule)
  config.toml                        approval policy, sandbox mode, per-project trust
  state_5.sqlite   threads           the thread registry, with tokens and git context
                   thread_spawn_edges  parent -> child delegation
  thread_history_1.sqlite thread_turns  per-turn duration and error state
  goals_1.sqlite   thread_goals      token budgets (usage_limited / budget_limited)

`~/.codex/sqlite/*dev.db` are development duplicates of these databases and are
deliberately not read — including them double-counts every thread.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import (
    HOME, dir_size, field, human_bytes, iso, iso_ms, meter, newest_mtime,
    not_installed, panel, preview, ro_sqlite, rrule_human, safe, section,
    table_exists, tilde, unavailable,
)

CODEX_DIR = HOME / ".codex"

# Rows rendered inline. The full count always travels alongside as `total` so a
# truncated table never reads as the whole story.
THREAD_ROWS = 25

# Values of approval_policy / sandbox_mode that hand Codex unrestricted reach.
# Surfacing these is the point of the security section: a user who set
# `danger-full-access` months ago has no other place to be reminded of it.
_RISKY_APPROVAL = {"never"}
_RISKY_SANDBOX = {"danger-full-access"}


def _load_toml(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    import tomllib
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def _schedules() -> Optional[Dict[str, Any]]:
    """Codex automations: the answer to 'what does this agent run without me?'"""
    root = CODEX_DIR / "automations"
    if not root.is_dir():
        return None

    rows: List[List[Any]] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        cfg = _load_toml(entry / "automation.toml")
        if not cfg:
            continue

        rule = str(cfg.get("rrule") or "")
        # `cwds` is a list of absolute repo paths; show the leaf so the column
        # stays readable, and fall back to the target type for thread-scoped
        # automations which carry no cwd at all.
        cwds = cfg.get("cwds")
        if isinstance(cwds, list) and cwds:
            project = Path(str(cwds[0])).name
        else:
            target = cfg.get("target")
            project = str(target.get("type")) if isinstance(target, dict) else "—"

        # A sibling memory.md accumulates notes across runs, so its mtime is the
        # only local evidence of when an automation last actually fired.
        last_run = iso(safe(lambda: (entry / "memory.md").stat().st_mtime, "memory.md"))

        rows.append([
            preview(cfg.get("name") or entry.name),
            rrule_human(rule) or "—",
            str(cfg.get("kind") or "—"),
            str(cfg.get("model") or "—"),
            project,
            str(cfg.get("status") or "—").upper(),
            last_run,
        ])

    if not rows:
        return None

    active = sum(1 for r in rows if r[5] == "ACTIVE")
    return section(
        "schedules", "Scheduled automations",
        tilde(root / "<id>" / "automation.toml"),
        columns=["Name", "Schedule", "Kind", "Model", "Project", "Status", "Last run"],
        rows=rows, count=active,
        note="Times come from the RRULE as written and are not timezone-converted. "
             "`last run` is inferred from the automation's memory.md mtime.",
    )


def _security() -> Optional[Dict[str, Any]]:
    cfg = _load_toml(CODEX_DIR / "config.toml")
    if not cfg:
        return None

    approval = str(cfg.get("approval_policy") or "—")
    sandbox = str(cfg.get("sandbox_mode") or "—")
    # config.toml carries a [projects."<abs path>"] table per directory the user
    # has ever trusted. The count is the useful number; the paths are not.
    projects = cfg.get("projects")
    trusted = 0
    if isinstance(projects, dict):
        trusted = sum(
            1 for v in projects.values()
            if isinstance(v, dict) and str(v.get("trust_level", "")).lower() == "trusted"
        )

    approval_risky = approval.lower() in _RISKY_APPROVAL
    sandbox_risky = sandbox.lower() in _RISKY_SANDBOX

    fields = [
        field("Approval policy", approval,
              severity="crit" if approval_risky else None,
              hint="Codex runs commands without asking." if approval_risky else None),
        field("Sandbox mode", sandbox,
              severity="crit" if sandbox_risky else None,
              hint="No filesystem or network restriction." if sandbox_risky else None),
        field("Reviewer", str(cfg.get("approvals_reviewer") or "—")),
        field("Trusted projects", trusted),
    ]

    servers = cfg.get("mcpServers")
    if isinstance(servers, dict) and servers:
        fields.append(field("MCP servers", ", ".join(sorted(servers)[:8])))

    return section(
        "permissions", "Security posture", tilde(CODEX_DIR / "config.toml"),
        fields=fields,
        severity="crit" if (approval_risky and sandbox_risky) else
                 "warn" if (approval_risky or sandbox_risky) else "ok",
    )


def _threads_and_spawns() -> List[Dict[str, Any]]:
    """Thread registry plus the delegation graph, from one database handle."""
    conn = ro_sqlite(CODEX_DIR / "state_5.sqlite")
    if conn is None:
        return []
    out: List[Dict[str, Any]] = []
    try:
        if not table_exists(conn, "threads"):
            return []

        # Count separately from the page query so `total` is the real total.
        total = conn.execute("SELECT COUNT(*) FROM threads").fetchone()[0]

        # Spawn counts are joined in rather than fetched per row: 132 threads
        # would otherwise be 132 extra queries on a locked database.
        spawn_counts: Dict[str, int] = {}
        if table_exists(conn, "thread_spawn_edges"):
            for row in conn.execute(
                "SELECT parent_thread_id, COUNT(*) c FROM thread_spawn_edges "
                "GROUP BY parent_thread_id"
            ):
                spawn_counts[row[0]] = row[1]

        rows: List[List[Any]] = []
        for r in conn.execute(
            "SELECT id, title, name, model, reasoning_effort, tokens_used, "
            "       git_branch, archived, updated_at, updated_at_ms "
            "FROM threads ORDER BY COALESCE(updated_at_ms/1000, updated_at) DESC "
            "LIMIT ?", (THREAD_ROWS,)
        ):
            rows.append([
                preview(r["name"] or r["title"]),
                r["model"] or "—",
                r["reasoning_effort"] or "—",
                r["tokens_used"] or 0,
                r["git_branch"] or "—",
                spawn_counts.get(r["id"], 0),
                bool(r["archived"]),
                iso_ms(r["updated_at_ms"]) or iso_ms(r["updated_at"]),
            ])

        if rows:
            out.append(section(
                "table", "Threads", tilde(CODEX_DIR / "state_5.sqlite") + " → threads",
                columns=["Title", "Model", "Effort", "Tokens", "Branch",
                         "Spawns", "Archived", "Updated"],
                rows=rows, total=total,
                # Codex's tokens_used is cumulative across the thread and is
                # dominated by cache reads — on this machine 95% of the total.
                # Without saying so, a 70-million-token thread reads like a bug.
                # Cross-checked against TokenTelemetry's own transcript-derived
                # figure for the same agent: the two agree within 0.4%.
                note="Tokens are Codex's own cumulative per-thread counter, which "
                     "includes cached reads — most of the total for a long thread. "
                     "Not billable volume."
                     + ("" if total <= THREAD_ROWS
                        else f" Showing the {THREAD_ROWS} most recent of {total} threads."),
            ))

        # Delegation is rendered as parent -> children, so a thread that spawned
        # nothing never appears. Threads whose parent was deleted are skipped
        # rather than shown as orphans under a missing title.
        if spawn_counts and table_exists(conn, "thread_spawn_edges"):
            titles = {
                r["id"]: preview(r["name"] or r["title"])
                for r in conn.execute("SELECT id, title, name FROM threads")
            }
            edges = 0
            tree: List[Dict[str, Any]] = []
            for parent, count in sorted(spawn_counts.items(),
                                        key=lambda kv: -kv[1])[:8]:
                if parent not in titles:
                    continue
                children = [
                    {"label": titles.get(c["child_thread_id"], "—"),
                     "status": c["status"] or "—"}
                    for c in conn.execute(
                        "SELECT child_thread_id, status FROM thread_spawn_edges "
                        "WHERE parent_thread_id=? LIMIT 20", (parent,))
                ]
                edges += count
                tree.append({"label": titles[parent], "children": children})
            if tree:
                out.append(section(
                    "tree", "Delegation",
                    tilde(CODEX_DIR / "state_5.sqlite") + " → thread_spawn_edges",
                    tree=tree, count=edges,
                    note="Parent threads that spawned children, busiest first.",
                ))
    finally:
        conn.close()
    return out


def _turn_latency() -> Optional[Dict[str, Any]]:
    """Per-turn wall-clock, which the power model would otherwise have to infer."""
    conn = ro_sqlite(CODEX_DIR / "thread_history_1.sqlite")
    if conn is None:
        return None
    try:
        if not table_exists(conn, "thread_turns"):
            return None
        durations = [
            r[0] for r in conn.execute(
                "SELECT duration_ms FROM thread_turns WHERE duration_ms IS NOT NULL "
                "AND duration_ms > 0")
        ]
        errored = conn.execute(
            "SELECT COUNT(*) FROM thread_turns WHERE error_json IS NOT NULL"
        ).fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM thread_turns").fetchone()[0]
    finally:
        conn.close()

    if not durations:
        return None
    durations.sort()
    median = durations[len(durations) // 2]
    # Index-based p95 on a small sample; with 19 turns this is the 18th value,
    # which is honest enough for a summary card and needs no numpy.
    p95 = durations[min(len(durations) - 1, int(len(durations) * 0.95))]

    def secs(ms: float) -> str:
        s = ms / 1000.0
        return f"{s:.1f} s" if s < 60 else f"{int(s // 60)}m {int(s % 60):02d}s"

    fields = [
        field("Median turn", secs(median)),
        field("p95 turn", secs(p95)),
        field("Turns recorded", total),
    ]
    if errored:
        pct = round(errored * 100 / total) if total else 0
        fields.append(field("Errored", f"{errored} ({pct}%)", severity="warn"))
    return section(
        "fields", "Turn latency",
        tilde(CODEX_DIR / "thread_history_1.sqlite") + " → thread_turns",
        fields=fields,
    )


def _budgets() -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Codex token budgets. Returns (section, unavailable) — exactly one is set.

    The table exists on every install but is usually empty. That's the
    "installed, zero rows" case: the feature is real and worth telling the user
    about, so we emit an `unavailable` entry naming it rather than staying silent.
    """
    conn = ro_sqlite(CODEX_DIR / "goals_1.sqlite")
    if conn is None:
        return None, None
    try:
        if not table_exists(conn, "thread_goals"):
            return None, None
        rows = list(conn.execute(
            "SELECT objective, status, token_budget, tokens_used, time_used_seconds "
            "FROM thread_goals ORDER BY updated_at_ms DESC LIMIT 20"))
    finally:
        conn.close()

    if not rows:
        return None, unavailable(
            "quota",
            "Codex tracks per-thread token budgets in goals_1.sqlite, including "
            "usage_limited and budget_limited states, but none are set on this machine.")

    meters = []
    for r in rows:
        budget = r["token_budget"] or 0
        used = r["tokens_used"] or 0
        pct = (used * 100.0 / budget) if budget else 0.0
        meters.append(meter(
            preview(r["objective"], 60), pct,
            detail=f"{used:,} of {budget:,} tokens" if budget else f"{used:,} tokens",
            severity="crit" if r["status"] in ("usage_limited", "budget_limited") else None,
        ))
    return section(
        "meter", "Goal budgets",
        tilde(CODEX_DIR / "goals_1.sqlite") + " → thread_goals",
        meters=meters,
    ), None


def _disk() -> Optional[Dict[str, Any]]:
    """Top-level breakdown, with the genuinely reclaimable part called out.

    Only one level deep: a full walk of ~/.codex is 9.5k files and this runs on
    every page open.
    """
    if not CODEX_DIR.is_dir():
        return None
    parts: List[Dict[str, Any]] = []
    total = 0
    complete = True
    for child in CODEX_DIR.iterdir():
        try:
            if child.is_dir():
                size, ok = dir_size(child)
                complete = complete and ok
            elif child.is_file():
                size, ok = child.lstat().st_size, True
            else:
                continue
        except OSError:
            continue
        total += size
        if size > 1024 * 1024:
            parts.append({"label": child.name, "bytes": size})
    parts.sort(key=lambda p: -p["bytes"])
    return {
        "total_bytes": total,
        "total_human": human_bytes(total),
        "parts": parts[:8],
        "complete": complete,
    }


def build(*, with_disk: bool = True) -> Dict[str, Any]:
    if not CODEX_DIR.is_dir():
        return not_installed("codex")

    version = None
    v = safe(lambda: __import__("json").loads(
        (CODEX_DIR / "version.json").read_text(encoding="utf-8")), "version.json")
    if isinstance(v, dict):
        version = v.get("latest_version")

    sections: List[Dict[str, Any]] = []
    not_avail: List[Dict[str, Any]] = []

    for step, what in ((_schedules, "schedules"), (_security, "security")):
        s = safe(step, f"codex {what}")
        if s:
            sections.append(s)

    budget_section, budget_missing = safe(_budgets, "codex budgets") or (None, None)
    if budget_section:
        sections.append(budget_section)
    if budget_missing:
        not_avail.append(budget_missing)

    for s in (safe(_threads_and_spawns, "codex threads") or []):
        sections.append(s)

    latency = safe(_turn_latency, "codex latency")
    if latency:
        sections.append(latency)

    not_avail.append(unavailable(
        "checkpoints",
        "Codex keeps full session history in rollout files but exposes no rewind "
        "points, so there is no checkpoint list to show."))

    last = newest_mtime([
        CODEX_DIR / "state_5.sqlite",
        CODEX_DIR / "history.jsonl",
        CODEX_DIR / "sessions",
    ])

    return panel(
        "codex", CODEX_DIR,
        sections=sections,
        not_available=not_avail,
        version=version,
        last_active=iso(last),
        disk=safe(_disk, "codex disk") if with_disk else None,
    )
