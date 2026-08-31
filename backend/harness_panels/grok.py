"""Grok Build panel — credit meter, plugin jobs, worktrees, trust.

The headline item costs almost nothing: Grok logs its own billing state into
`logs/unified.jsonl` as a `"billing: fetched credits config"` record, which
carries `creditUsagePercent`, the subscription tier and the current period
bounds. TokenTelemetry already parses this file for token usage and filters for
a single message type, so the credit meter is one more filter over bytes we
were reading anyway.

`unified.jsonl` is one ever-growing file shared by every project and session
(12.7k lines here). It is read **backwards** — the newest billing record wins
and older ones are stale by definition, so there is no reason to walk from the
top and no reason for cost to grow with the log.

Not read: `sessions/**/prompts/*.txt`, `chat_history.jsonl`, `last-copy.txt` and
`rewind_points.jsonl` all hold raw user text or whole file contents.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from .base import (
    HOME, dir_size, field, human_bytes, iso, meter, newest_mtime, not_installed,
    panel, ro_sqlite, safe, section, table_exists, tilde, unavailable, live_quota,
)

GROK_DIR = Path(os.environ.get("GROK_HOME") or (HOME / ".grok")).expanduser()
UNIFIED_LOG = GROK_DIR / "logs" / "unified.jsonl"

BILLING_MSG = "billing: fetched credits config"

# Statuses that mean a plugin job is over. Observed vocabulary on disk is
# {finished, failed}; the rest are defensive. Anything not in here is treated as
# still in flight, so an unknown status shows up rather than being counted as done.
_TERMINAL_JOB_STATES = frozenset({
    "finished", "failed", "completed", "cancelled", "canceled", "error", "done",
})

# How far back to look for a billing record before giving up. Billing is logged
# on roughly every startup, so the newest one is almost always within a few
# hundred lines of the tail; this bound keeps a pathological log from turning a
# page open into a full-file read.
TAIL_BYTES = 2 * 1024 * 1024


def _tail_lines(path: Path, max_bytes: int = TAIL_BYTES) -> Iterator[str]:
    """Yield lines from the end of a file backwards, reading at most max_bytes."""
    size = path.stat().st_size
    start = max(0, size - max_bytes)
    with path.open("rb") as fh:
        fh.seek(start)
        chunk = fh.read(size - start)
    # A partial first line is likely when we seek into the middle of the file.
    text = chunk.decode("utf-8", errors="replace")
    lines = text.split("\n")
    if start > 0 and lines:
        lines = lines[1:]
    for line in reversed(lines):
        line = line.strip()
        if line:
            yield line


def _credits() -> Optional[Dict[str, Any]]:
    if not UNIFIED_LOG.exists():
        return None
    record = None
    for line in _tail_lines(UNIFIED_LOG):
        # Cheap substring reject before paying for a JSON parse; the vast
        # majority of lines are tool and inference events.
        if BILLING_MSG not in line:
            continue
        try:
            doc = json.loads(line)
        except ValueError:
            continue
        if doc.get("msg") == BILLING_MSG:
            record = doc
            break
    if not record:
        return None

    ctx = record.get("ctx") or {}
    cfg = ctx.get("config") or {}
    pct = cfg.get("creditUsagePercent")
    if pct is None:
        return None

    period = cfg.get("currentPeriod") or {}
    # USAGE_PERIOD_TYPE_WEEKLY -> "weekly"
    ptype = str(period.get("type") or "").replace("USAGE_PERIOD_TYPE_", "").lower()

    # The tier is rendered as its own field below, so it stays out of the meter
    # detail rather than appearing twice on the same card.
    meters = [meter(
        f"Credit usage ({ptype})" if ptype else "Credit usage",
        float(pct),
        resets_at=period.get("end") or cfg.get("billingPeriodEnd"),
    )]

    fields = []
    tier = ctx.get("subscriptionTier")
    if tier:
        fields.append(field("Subscription", str(tier)))
    for label, key in (("On-demand cap", "onDemandCap"),
                       ("On-demand used", "onDemandUsed"),
                       ("Prepaid balance", "prepaidBalance")):
        node = cfg.get(key)
        if isinstance(node, dict) and node.get("val"):
            fields.append(field(label, node["val"]))

    return section(
        "meter", "Credit usage", tilde(UNIFIED_LOG) + f' → "{BILLING_MSG}"',
        meters=meters, fields=fields or None,
        note=f"Recorded by Grok at {record.get('ts')}. Read from the tail of the "
             "log, which TokenTelemetry already parses for token usage.",
    )


def _plugin_jobs() -> Optional[Dict[str, Any]]:
    """Background jobs launched through the grok:* Claude Code plugin skills."""
    root = GROK_DIR / "cc-plugin" / "jobs"
    if not root.is_dir():
        return None
    rows: List[List[Any]] = []
    for group in root.iterdir():
        if not group.is_dir():
            continue
        for jf in group.glob("job-*.json"):
            rec = safe(lambda p=jf: json.loads(p.read_text(encoding="utf-8")), "grok job")
            if not isinstance(rec, dict):
                continue
            rows.append([
                str(rec.get("kind") or "—"),
                str(rec.get("status") or "—"),
                str(rec.get("model") or "—"),
                group.name,
                rec.get("startedAt"),
                rec.get("finishedAt"),
            ])
    if not rows:
        return None
    rows.sort(key=lambda r: str(r[4] or ""), reverse=True)

    # Grok writes "finished", not "completed" — treating only the latter as
    # terminal reported every finished job as still running. Match on the
    # statuses this store actually uses, and let anything unrecognised count as
    # in-flight rather than silently as done.
    failed = sum(1 for r in rows if r[1] == "failed")
    running = sum(1 for r in rows if r[1] not in _TERMINAL_JOB_STATES)

    if running:
        headline, severity = running, None
    else:
        # Nothing is in flight, so the failure rate is the story. Eight of
        # fourteen failing is worth seeing at a glance.
        headline, severity = failed, ("warn" if failed else None)

    note = ("Invocations of grok:rescue / grok:search launched from Claude Code. "
            "Prompt text is stored alongside and is not read.")
    if failed and not running:
        note = f"{failed} of {len(rows)} failed. " + note

    return section(
        "jobs", "Plugin jobs", tilde(root) + "/<group>/job-<id>.json",
        columns=["Kind", "Status", "Model", "Group", "Started", "Finished"],
        rows=rows[:30], count=headline, total=len(rows), severity=severity,
        note=note,
    )


def _worktrees() -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    conn = ro_sqlite(GROK_DIR / "worktrees.db")
    if conn is None:
        return None, None
    try:
        if not table_exists(conn, "worktrees"):
            return None, None
        rows = [
            [Path(str(r["path"])).name, r["repo_name"] or "—", r["kind"] or "—",
             r["git_ref"] or "—", r["status"] or "—", r["last_accessed_at"]]
            for r in conn.execute(
                "SELECT path, repo_name, kind, git_ref, status, last_accessed_at "
                "FROM worktrees ORDER BY last_accessed_at DESC LIMIT 20")
        ]
    finally:
        conn.close()
    if not rows:
        return None, unavailable(
            "worktrees",
            "Grok tracks git worktree lifecycle in worktrees.db, but none are "
            "recorded on this machine.")
    return section(
        "table", "Worktrees", tilde(GROK_DIR / "worktrees.db"),
        columns=["Name", "Repo", "Kind", "Ref", "Status", "Last used"], rows=rows,
    ), None


def _trust_and_live() -> Optional[Dict[str, Any]]:
    fields = []
    trusted = GROK_DIR / "trusted_folders.toml"
    if trusted.exists():
        try:
            import tomllib
            with open(trusted, "rb") as fh:
                data = tomllib.load(fh)
            # Shape varies by version; count whatever collection it holds rather
            # than assuming a key name.
            n = 0
            for value in data.values():
                if isinstance(value, (list, dict)):
                    n += len(value)
            fields.append(field("Trusted folders", n))
        except Exception:
            pass

    active = safe(
        lambda: json.loads((GROK_DIR / "active_sessions.json").read_text(encoding="utf-8")),
        "grok active")
    if isinstance(active, list):
        fields.append(field("Live sessions", len(active),
                            severity="ok" if active else None))

    version = safe(
        lambda: json.loads((GROK_DIR / "version.json").read_text(encoding="utf-8")),
        "grok version")
    if isinstance(version, dict) and version.get("version"):
        fields.append(field("Version", str(version["version"])))

    if not fields:
        return None
    return section("fields", "Workspace trust", tilde(GROK_DIR), fields=fields)


def _skills() -> Optional[Dict[str, Any]]:
    """User-authored Grok skills.

    Worth surfacing specifically because the main scanner never collects skills
    for Grok the way it does for other agents, so these are otherwise invisible.
    """
    root = GROK_DIR / "skills"
    if not root.is_dir():
        return None
    names = sorted(p.name for p in root.iterdir()
                   if p.is_dir() and (p / "SKILL.md").exists())
    if not names:
        return None
    return section(
        "chips", "Skills", tilde(root) + "/<name>/SKILL.md",
        columns=["Name"], rows=[[n] for n in names],
    )


def _disk() -> Optional[Dict[str, Any]]:
    if not GROK_DIR.is_dir():
        return None
    parts, total, complete = [], 0, True
    for child in GROK_DIR.iterdir():
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
        if size > 1024 * 1024:
            parts.append({"label": child.name, "bytes": size})
    parts.sort(key=lambda p: -p["bytes"])

    # downloads/ caches self-update binaries for versions already installed.
    reclaimable, _ = dir_size(GROK_DIR / "downloads") if (GROK_DIR / "downloads").is_dir() else (0, True)
    return {
        "total_bytes": total, "total_human": human_bytes(total),
        "parts": parts[:8], "complete": complete,
        "reclaimable_bytes": reclaimable,
        "reclaimable_note": "Cached self-update binaries for versions already "
                            "installed (downloads/)." if reclaimable else None,
    }


def build(*, with_disk: bool = True) -> Dict[str, Any]:
    if not GROK_DIR.is_dir():
        return not_installed("grok")

    sections: List[Dict[str, Any]] = []
    not_avail: List[Dict[str, Any]] = []

    quota = safe(lambda: live_quota("grok"), "grok quota")
    if quota:
        sections.append(quota)

    for step, what in ((_credits, "credits"), (_plugin_jobs, "jobs"),
                       (_trust_and_live, "trust"), (_skills, "skills")):
        s = safe(step, f"grok {what}")
        if s:
            sections.append(s)

    wt, wt_missing = safe(_worktrees, "grok worktrees") or (None, None)
    if wt:
        sections.append(wt)
    if wt_missing:
        not_avail.append(wt_missing)

    not_avail.append(unavailable(
        "memory",
        "Grok's memory store is opt-in (GROK_MEMORY=1) and is not enabled here, "
        "so there is no memory directory to read."))

    version = None
    v = safe(lambda: json.loads((GROK_DIR / "version.json").read_text(encoding="utf-8")),
             "grok version")
    if isinstance(v, dict):
        version = v.get("version")

    last = newest_mtime([UNIFIED_LOG, GROK_DIR / "sessions"])

    return panel(
        "grok", GROK_DIR,
        sections=sections, not_available=not_avail,
        version=version, last_active=iso(last), disk=safe(_disk, "grok disk") if with_disk else None,
    )
