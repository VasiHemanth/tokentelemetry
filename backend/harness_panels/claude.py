"""Claude Code panel — subscription quota, background jobs, workflows, adoption.

The session scan already reads `~/.claude/projects/**/*.jsonl`. Everything here
comes from stores beside it:

  ~/.claude.json  cachedUsageUtilization   5h / 7d subscription utilisation
                  skillUsage / pluginUsage  feature adoption counters
  jobs/<id>/state.json                      background-agent fleet
  daemon/roster.json, sessions/<pid>.json   which of those are alive right now
  projects/**/workflows/wf_*.json           phased multi-agent runs

Two things are deliberately NOT read. `~/.claude/history.jsonl` and
`paste-cache/` hold raw user text, and `sessions/<pid>.<hash>.key`,
`daemon/control.key`, `rvAuth` and `ptyAuth` are local-socket secrets. Nothing in
this module opens them.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import (
    HOME, dir_size, field, human_bytes, iso, iso_ms, meter, newest_mtime,
    not_installed, panel, preview, safe, section, tilde, unavailable,
)

CLAUDE_DIR = HOME / ".claude"
CLAUDE_JSON = HOME / ".claude.json"

JOB_ROWS = 30
WORKFLOW_ROWS = 15

# Job dirs carry a multi-gigabyte `tmp/` scratch tree (git clones, node_modules)
# that is not data. Sizing it on every page open would dominate the request, so
# the disk section reports it as one reclaimable line without walking it.
_JOB_STATE_KEYS = ("state", "detail", "tokens", "name", "intent", "cwd",
                   "createdAt", "updatedAt", "children", "template", "fan")


def _read_json(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _quota() -> Optional[Dict[str, Any]]:
    """Subscription utilisation, straight off disk.

    `cachedUsageUtilization` is written by the CLI after it asks the API, so it
    costs us nothing and needs no network of our own. It is a cache: if it's
    stale we say when it was fetched rather than presenting it as live.
    """
    data = _read_json(CLAUDE_JSON)
    if not isinstance(data, dict):
        return None
    cached = data.get("cachedUsageUtilization")
    if not isinstance(cached, dict):
        return None
    util = cached.get("utilization")
    if not isinstance(util, dict):
        return None

    labels = {"five_hour": "5-hour window", "seven_day": "7-day window",
              "seven_day_opus": "7-day Opus"}
    meters = []
    for key, label in labels.items():
        window = util.get(key)
        if not isinstance(window, dict):
            continue
        pct = window.get("utilization")
        if pct is None:
            continue
        used = window.get("used_dollars")
        limit = window.get("limit_dollars")
        detail = None
        if isinstance(used, (int, float)) and isinstance(limit, (int, float)) and limit:
            detail = f"${used:,.2f} of ${limit:,.2f} used"
        meters.append(meter(label, float(pct),
                            detail=detail, resets_at=window.get("resets_at")))
    if not meters:
        return None

    fetched = cached.get("fetchedAtMs")
    note = None
    if isinstance(fetched, (int, float)):
        age_min = (datetime.now(timezone.utc).timestamp() - fetched / 1000.0) / 60.0
        if age_min > 60:
            note = (f"Cached by Claude Code {age_min / 60:.0f}h ago — it refreshes "
                    "when the CLI next talks to the API.")
    return section("meter", "Subscription usage",
                   tilde(CLAUDE_JSON) + " → cachedUsageUtilization",
                   meters=meters, note=note)


def _live_job_ids() -> set[str]:
    """Job ids with a live worker, from the daemon roster and process registry."""
    live: set[str] = set()
    roster = safe(lambda: _read_json(CLAUDE_DIR / "daemon" / "roster.json"), "roster")
    if isinstance(roster, dict):
        workers = roster.get("workers")
        if isinstance(workers, dict):
            live.update(str(k) for k in workers)
    sessions_dir = CLAUDE_DIR / "sessions"
    if sessions_dir.is_dir():
        for f in sessions_dir.glob("*.json"):
            rec = safe(lambda p=f: _read_json(p), "session reg")
            if isinstance(rec, dict) and rec.get("jobId"):
                live.add(str(rec["jobId"]))
    return live


def _jobs() -> Optional[Dict[str, Any]]:
    root = CLAUDE_DIR / "jobs"
    if not root.is_dir():
        return None
    live = safe(_live_job_ids, "live jobs") or set()

    records: List[Dict[str, Any]] = []
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        state = safe(lambda e=entry: _read_json(e / "state.json"), "job state")
        if not isinstance(state, dict):
            continue
        # `children` links a job to the PRs and issues it produced — the single
        # most useful column here, because it turns "an agent ran" into "an
        # agent shipped this".
        children = state.get("children")
        links = []
        if isinstance(children, list):
            for c in children[:4]:
                if isinstance(c, dict) and c.get("id"):
                    kind = str(c.get("kind") or "link")
                    links.append(f"{kind} #{c['id']}")
        records.append({
            "id": entry.name,
            "name": preview(state.get("name") or state.get("intent") or entry.name),
            "state": str(state.get("state") or "—"),
            "tokens": state.get("tokens") or 0,
            "project": Path(str(state.get("cwd") or "")).name or "—",
            "links": ", ".join(links) or "—",
            "updated": state.get("updatedAt"),
            "live": entry.name in live,
        })
    if not records:
        return None

    records.sort(key=lambda r: (not r["live"], str(r["updated"] or "")), reverse=False)
    records.sort(key=lambda r: str(r["updated"] or ""), reverse=True)
    records.sort(key=lambda r: not r["live"])

    rows = [[r["name"], r["state"], r["tokens"], r["project"], r["links"],
             r["updated"], r["live"]] for r in records[:JOB_ROWS]]
    running = sum(1 for r in records if r["live"])
    return section(
        "jobs", "Background jobs", tilde(root / "<id>" / "state.json"),
        columns=["Name", "State", "Tokens", "Project", "Links", "Updated", "Live"],
        rows=rows, count=running, total=len(records),
        note=f"{len(records)} jobs on disk, {running} with a live worker."
             + ("" if len(records) <= JOB_ROWS else f" Showing {JOB_ROWS} most recent."),
    )


def _workflows() -> Optional[Dict[str, Any]]:
    """Phased multi-agent runs, distinct from ordinary Task-tool subagents."""
    projects = CLAUDE_DIR / "projects"
    if not projects.is_dir():
        return None
    runs: List[Dict[str, Any]] = []
    # One glob over the sidecar dirs; most sessions have none, so this is far
    # cheaper than it looks.
    for wf in projects.glob("*/*/workflows/wf_*.json"):
        rec = safe(lambda p=wf: _read_json(p), "workflow")
        if not isinstance(rec, dict):
            continue
        runs.append({
            "name": preview(rec.get("workflowName")),
            "status": str(rec.get("status") or "—"),
            "agents": rec.get("agentCount") or 0,
            "tokens": rec.get("totalTokens") or 0,
            "calls": rec.get("totalToolCalls") or 0,
            "ms": rec.get("durationMs") or 0,
            "ts": rec.get("timestamp") or "",
        })
    if not runs:
        return None
    runs.sort(key=lambda r: str(r["ts"]), reverse=True)

    def dur(ms: float) -> str:
        s = ms / 1000.0
        return f"{s:.0f}s" if s < 60 else f"{int(s // 60)}m {int(s % 60):02d}s"

    rows = [[r["name"], r["status"], r["agents"], r["tokens"], r["calls"],
             dur(r["ms"]), r["ts"]] for r in runs[:WORKFLOW_ROWS]]
    return section(
        "table", "Workflows", tilde(projects) + "/**/workflows/wf_*.json",
        columns=["Name", "Status", "Agents", "Tokens", "Tool calls", "Duration", "When"],
        rows=rows, total=len(runs),
        note=None if len(runs) <= WORKFLOW_ROWS
             else f"Showing {WORKFLOW_ROWS} most recent of {len(runs)} runs.",
    )


def _adoption() -> Optional[Dict[str, Any]]:
    data = _read_json(CLAUDE_JSON)
    if not isinstance(data, dict):
        return None
    rows: List[List[Any]] = []
    for bucket, kind in (("skillUsage", "skill"), ("pluginUsage", "plugin")):
        usage = data.get(bucket)
        if not isinstance(usage, dict):
            continue
        for name, rec in usage.items():
            if not isinstance(rec, dict):
                continue
            # lastUsedAt is epoch milliseconds, not an ISO string — passed
            # through raw it rendered as an em dash in every row.
            rows.append([str(name), kind, rec.get("usageCount") or 0,
                         iso_ms(rec.get("lastUsedAt"))])
    if not rows:
        return None
    rows.sort(key=lambda r: -(r[2] or 0))
    return section(
        "table", "Feature adoption", tilde(CLAUDE_JSON) + " → skillUsage / pluginUsage",
        columns=["Name", "Kind", "Uses", "Last used"], rows=rows[:20],
        total=len(rows),
    )


def _checkpoints() -> Optional[Dict[str, Any]]:
    """File-history checkpoint volume per session.

    The blobs themselves are raw file contents and are never read — only their
    names, which encode `<content-hash>@v<N>`. That's enough for "how much did
    this session rewrite", which is the useful signal.
    """
    root = CLAUDE_DIR / "file-history"
    if not root.is_dir():
        return None
    rows: List[List[Any]] = []
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        names = [p.name for p in entry.iterdir() if p.is_file()]
        if not names:
            continue
        distinct = {n.split("@", 1)[0] for n in names}
        mtime = safe(lambda e=entry: e.stat().st_mtime, "ckpt mtime")
        rows.append([entry.name[:8], len(distinct), len(names), iso(mtime)])
    if not rows:
        return None
    rows.sort(key=lambda r: str(r[3] or ""), reverse=True)
    return section(
        "checkpoints", "Edit checkpoints", tilde(root) + "/<session>/<hash>@v<N>",
        columns=["Session", "Files", "Snapshots", "Last write"], rows=rows[:20],
        total=len(rows),
        note="Snapshot counts only — the blobs hold file contents and are never read.",
    )


def _disk() -> Optional[Dict[str, Any]]:
    if not CLAUDE_DIR.is_dir():
        return None
    parts: List[Dict[str, Any]] = []
    total = 0
    complete = True
    for child in CLAUDE_DIR.iterdir():
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

    # jobs/*/tmp is scratch: repo clones and dependency trees a finished job left
    # behind. Naming it is the difference between "Claude Code is using 4 GB" and
    # "3 GB of that is deletable".
    reclaimable = 0
    jobs = CLAUDE_DIR / "jobs"
    if jobs.is_dir():
        for entry in jobs.iterdir():
            tmp = entry / "tmp"
            if tmp.is_dir():
                size, ok = dir_size(tmp)
                complete = complete and ok
                reclaimable += size
    return {
        "total_bytes": total, "total_human": human_bytes(total),
        "parts": parts[:8], "complete": complete,
        "reclaimable_bytes": reclaimable,
        "reclaimable_note": "Scratch workspaces left behind by finished background "
                            "jobs (jobs/*/tmp) — clones and dependency trees, not data."
                            if reclaimable else None,
    }


def build() -> Dict[str, Any]:
    if not CLAUDE_DIR.is_dir():
        return not_installed("claude")

    sections: List[Dict[str, Any]] = []
    for step, what in ((_quota, "quota"), (_jobs, "jobs"), (_workflows, "workflows"),
                       (_checkpoints, "checkpoints"), (_adoption, "adoption")):
        s = safe(step, f"claude {what}")
        if s:
            sections.append(s)

    not_avail = [unavailable(
        "schedules",
        "Claude Code Routines are scheduled in the cloud. Only a fired-watermark "
        "is stored locally, so there is no schedule list to read.")]

    settings = safe(lambda: _read_json(CLAUDE_DIR / "settings.json"), "settings")
    version = None
    if isinstance(settings, dict):
        version = settings.get("version")

    last = newest_mtime([CLAUDE_DIR / "projects", CLAUDE_JSON, CLAUDE_DIR / "jobs"])

    return panel(
        "claude", CLAUDE_DIR,
        sections=sections, not_available=not_avail,
        version=version, last_active=iso(last),
        disk=safe(_disk, "claude disk"),
    )
