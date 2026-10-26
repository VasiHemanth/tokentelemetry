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

import base64
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from .base import (
    HOME, dir_size, field, human_bytes, iso, iso_ms, meter,
    newest_mtime, not_installed, panel, ro_sqlite, safe, section, table_exists,
    tilde, unavailable, live_quota,
)

GROK_DIR = Path(os.environ.get("GROK_HOME") or (HOME / ".grok")).expanduser()
UNIFIED_LOG = GROK_DIR / "logs" / "unified.jsonl"

# --- Grok Bot (the desktop app) --------------------------------------------
# A different product from the `grok` CLI above, with its own stores:
#   ~/.grokbot/                              local-exec daemon, computer-use gate
#   <Electron userData>/Grok Bot/            app state + sand-client-persistence
# The app persists small JSON "slices" under sand-client-persistence/ with
# base32-encoded names. Two carry data the CLI never sees: the weekly plan
# meter and the bot roster. Transcript slices live in the same directory and
# are deliberately never opened — they hold raw conversation text.
GROK_BOT_DIR = Path(os.environ.get("TT_GROK_BOT_DIR") or (HOME / ".grokbot")).expanduser()
GROK_BOT_COMPUTER_USE_DIR = HOME / "Library" / "Application Support" / "grok-bot-computer-use"

if sys.platform == "darwin":
    _GROK_BOT_APP_DEFAULT = HOME / "Library" / "Application Support" / "Grok Bot"
elif os.name == "nt":
    _GROK_BOT_APP_DEFAULT = Path(os.environ.get("APPDATA") or (HOME / "AppData" / "Roaming")) / "Grok Bot"
else:
    _GROK_BOT_APP_DEFAULT = Path(os.environ.get("XDG_CONFIG_HOME") or (HOME / ".config")) / "Grok Bot"

GROK_BOT_APP_DIR = Path(os.environ.get("TT_GROK_BOT_APP_DIR") or _GROK_BOT_APP_DEFAULT).expanduser()
GROK_BOT_SLICES_DIR = GROK_BOT_APP_DIR / "sand-client-persistence"
GROK_BOT_USAGE_SUFFIX = ".weekly-usage.cache"
GROK_BOT_ROSTER_SUFFIX = ".roster.last-roster"
GROK_BOT_LOG = GROK_BOT_DIR / "local-exec-daemon.log"

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


def _billing_record() -> Optional[Dict[str, Any]]:
    """Newest `billing: fetched credits config` record in the CLI log."""
    if not UNIFIED_LOG.exists():
        return None
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
            return doc
    return None


def _credits(record: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    record = record if record is not None else _billing_record()
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


# --- Grok Bot desktop app ---------------------------------------------------
# Everything below reads at most three tiny slices plus the executor's own
# state files. Transcript slices share the directory but are never opened: they
# contain raw conversation text, and the roster already carries what the panel
# needs (agent name + last activity).

def _read_json(path: Optional[Path]) -> Any:
    if path is None:
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _dt(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _is_newer(a: Optional[str], b: Optional[str]) -> bool:
    """True when ISO timestamp `a` is strictly newer than `b`."""
    da, db = _dt(a), _dt(b)
    if da is None:
        return False
    if db is None:
        return True
    return da > db


def _recent(value: Optional[str], seconds: int) -> bool:
    parsed = _dt(value)
    if parsed is None:
        return False
    return (datetime.now(timezone.utc) - parsed).total_seconds() <= seconds


def _blob_key(name: str) -> Optional[str]:
    """Decode a sand-client-persistence filename back to its storage key."""
    if not name.endswith(".blob"):
        return None
    raw = name[:-len(".blob")].upper()
    try:
        return base64.b32decode(raw + "=" * (-len(raw) % 8)).decode("utf-8", "replace")
    except Exception:
        return None


def _bot_slices() -> Dict[str, Path]:
    """The two readable state slices, matched by decoded key suffix.

    Filenames are base32-encoded storage keys, and the account-scoped prefix
    differs per login, so the suffix is the stable part. Newest wins if an
    account switch left two sets behind.
    """
    found: Dict[str, Path] = {}
    if not GROK_BOT_SLICES_DIR.is_dir():
        return found
    try:
        blobs = list(GROK_BOT_SLICES_DIR.glob("*.blob"))
    except OSError:
        return found
    for path in blobs:
        key = _blob_key(path.name)
        if not key:
            continue
        tag = "usage" if key.endswith(GROK_BOT_USAGE_SUFFIX) else (
            "roster" if key.endswith(GROK_BOT_ROSTER_SUFFIX) else None)
        if not tag:
            continue
        try:
            if tag not in found or path.stat().st_mtime > found[tag].stat().st_mtime:
                found[tag] = path
        except OSError:
            continue
    return found


def _bot_usage(path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Weekly plan meter cached by the desktop app.

    Worth reading because the CLI only refreshes its own billing record when it
    runs: on a machine driven through Grok Bot, `unified.jsonl` can describe a
    week that already ended. This cache is written by the app itself.
    """
    path = path or _bot_slices().get("usage")
    doc = _read_json(path)
    value = doc.get("value") if isinstance(doc, dict) else None
    if not isinstance(value, dict):
        return None
    reading = value.get("reading") if isinstance(value.get("reading"), dict) else {}
    usage = reading.get("usage") if isinstance(reading.get("usage"), dict) else {}
    pct = usage.get("percentUsed")
    if not isinstance(pct, (int, float)) or isinstance(pct, bool):
        return None

    reset = iso_ms(usage.get("nextResetMs"))
    read_at = iso_ms(reading.get("readAtMs"))
    expires = iso_ms(value.get("expiresAtMs"))
    plan = usage.get("grokPlanLabel")

    fields = []
    if isinstance(plan, str) and plan:
        fields.append(field("Plan", plan))
    if read_at:
        fields.append(field("Read at", read_at))
    if expires:
        fields.append(field("Cache expires", expires))

    stale = bool(expires and _dt(expires) and _dt(expires) < datetime.now(timezone.utc))
    note = ("Recorded by the Grok Bot desktop app" +
            (f" at {read_at}" if read_at else "") +
            ". This is the app's own weekly window; it can differ from the CLI's "
            "plan meter because the two clients do not share a billing cycle.")
    if stale:
        note += " The app's cache has expired; it refreshes on next launch."

    return section(
        "meter", "Grok Bot plan usage",
        tilde(GROK_BOT_SLICES_DIR) + "/…" + GROK_BOT_USAGE_SUFFIX,
        meters=[meter("Weekly usage", float(pct), resets_at=reset)],
        fields=fields or None, note=note,
    )


def _bot_roster(path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """The desktop app's bot fleet: name, kind, last activity, unread count."""
    path = path or _bot_slices().get("roster")
    doc = _read_json(path)
    value = doc.get("value") if isinstance(doc, dict) else None
    rows_in = value.get("rows") if isinstance(value, dict) else None
    if not isinstance(rows_in, list):
        return None

    rows: List[List[Any]] = []
    for agent in rows_in:
        if not isinstance(agent, dict) or not agent.get("name"):
            continue
        rows.append([
            str(agent["name"]),
            "group" if agent.get("isGroup") else "bot",
            iso_ms(agent.get("lastActivityAt")) or "—",
            agent.get("unreadCount") if isinstance(agent.get("unreadCount"), int) else 0,
        ])
    if not rows:
        return None
    rows.sort(key=lambda row: _dt(row[2]) or datetime.min.replace(tzinfo=timezone.utc),
              reverse=True)

    return section(
        "table", "Bot agents", tilde(GROK_BOT_SLICES_DIR) + "/…" + GROK_BOT_ROSTER_SUFFIX,
        columns=["Agent", "Kind", "Last used", "Unread"], rows=rows,
        note="The desktop app's own roster. Message text is never read; only "
             "each bot's name, kind and last activity.",
    )


def _bot_log_health(path: Path, max_bytes: int = 256 * 1024) -> tuple:
    """(recent outage count, last reconnect timestamp) from the executor log."""
    outages, last_connect = 0, None
    try:
        lines = _tail_lines(path, max_bytes=max_bytes)
        for line in lines:
            if "watch_outage" in line:
                outages += 1
            if last_connect is None and " connected after " in line:
                match = re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", line)
                if match:
                    last_connect = match.group(0)
    except OSError:
        return 0, None
    return outages, last_connect


def _bot_executor() -> Optional[Dict[str, Any]]:
    """Is the local executor actually running, and is it healthy?"""
    fields: List[Dict[str, Any]] = []

    app = _read_json(GROK_BOT_APP_DIR / "desktop-status.json")
    if isinstance(app, dict):
        if app.get("appVersion"):
            fields.append(field("App version", str(app["appVersion"])))
        if isinstance(app.get("signedIn"), bool):
            fields.append(field("Signed in", "Yes" if app["signedIn"] else "No",
                                severity=None if app["signedIn"] else "warn"))

    daemon = _read_json(GROK_BOT_DIR / "local-exec-daemon.json")
    if isinstance(daemon, dict):
        serving = iso_ms(daemon.get("servingAt"))
        started = iso_ms(daemon.get("startedAt"))
        state = "running" if _recent(serving, 600) else "idle"
        fields.append(field("Executor", state, severity="ok" if state == "running" else None))
        if started:
            fields.append(field("Started", started))
        if serving:
            fields.append(field("Last serving", serving))
        if isinstance(daemon.get("inflightCount"), int):
            fields.append(field("In flight", daemon["inflightCount"]))
        if isinstance(daemon.get("pid"), int):
            fields.append(field("Daemon pid", daemon["pid"]))

    if GROK_BOT_LOG.exists():
        outages, last_connect = _bot_log_health(GROK_BOT_LOG)
        fields.append(field("Recent watch outages", outages,
                            severity="warn" if outages else None))
        if last_connect:
            fields.append(field("Last reconnect", last_connect))

    if not fields:
        return None
    return section(
        "fields", "Local executor", tilde(GROK_BOT_DIR),
        fields=fields,
        note="Grok Bot runs tools on this Mac through a local executor daemon. "
             "Read from its own state files; the log tail covers the last 256 KB.",
    )


def _bot_storage() -> Optional[Dict[str, Any]]:
    entries = []
    for path in (GROK_BOT_DIR, GROK_BOT_APP_DIR, GROK_BOT_COMPUTER_USE_DIR):
        if not path.is_dir():
            continue
        size, complete = dir_size(path)
        entries.append((size, tilde(path), complete))
    if not entries:
        return None
    entries.sort(key=lambda e: -e[0])
    total = sum(size for size, _, _ in entries)
    rows = [[label, human_bytes(size) + ("" if complete else "+")]
            for size, label, complete in entries]
    return section(
        "table", "Grok Bot storage", tilde(GROK_BOT_DIR),
        columns=["Location", "Size"], rows=rows,
        note=f"{human_bytes(total)} across the desktop app and its executor. "
             "Conversation transcripts are not read.",
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
    has_cli = GROK_DIR.is_dir()
    has_bot = GROK_BOT_DIR.is_dir() or GROK_BOT_APP_DIR.is_dir()
    if not has_cli and not has_bot:
        return not_installed("grok")

    sections: List[Dict[str, Any]] = []
    not_avail: List[Dict[str, Any]] = []

    # The CLI and the desktop app can sit on different billing windows — the
    # live quota above resets Oct 30 here while the app's cache resets Nov 1 —
    # so they are reported separately rather than merged into one number.
    bot_slices = safe(_bot_slices, "grok bot slices") or {}
    bot_usage = safe(lambda: _bot_usage(bot_slices.get("usage")), "grok bot usage")
    quota = safe(lambda: live_quota("grok"), "grok quota")
    if quota:
        sections.append(quota)
    if bot_usage:
        sections.append(bot_usage)
    usage_path = bot_slices.get("usage")
    bot_usage_at = iso(usage_path.stat().st_mtime) if usage_path else None

    # `_credits` describes the same weekly credit window from the CLI log, and
    # it is only written when the CLI runs. Drop it when the bot meter above is
    # newer, rather than showing two percentages 10 points apart.
    billing = safe(_billing_record, "grok billing record")
    credits = safe(lambda: _credits(billing), "grok credits")
    billing_ts = billing.get("ts") if isinstance(billing, dict) else None
    if credits and bot_usage and _is_newer(bot_usage_at, billing_ts):
        credits = None
    if credits:
        sections.append(credits)

    for step, what in (
        (lambda: _bot_roster(bot_slices.get("roster")), "roster"),
        (_bot_executor, "executor"),
        (_bot_storage, "storage"),
        (_plugin_jobs, "jobs"),
        (_trust_and_live, "trust"),
        (_skills, "skills"),
    ):
        s = safe(step, f"grok {what}")
        if s:
            sections.append(s)

    wt, wt_missing = safe(_worktrees, "grok worktrees") or (None, None)
    if wt:
        sections.append(wt)
    if wt_missing:
        not_avail.append(wt_missing)

    if has_cli:
        not_avail.append(unavailable(
            "memory",
            "Grok's memory store is opt-in (GROK_MEMORY=1) and is not enabled here, "
            "so there is no memory directory to read."))

    version = None
    v = safe(lambda: json.loads((GROK_DIR / "version.json").read_text(encoding="utf-8")),
             "grok version")
    if isinstance(v, dict):
        version = v.get("version")
    if not version:
        app = _read_json(GROK_BOT_APP_DIR / "desktop-status.json")
        if isinstance(app, dict) and app.get("appVersion"):
            version = f"bot {app['appVersion']}"

    last = newest_mtime([UNIFIED_LOG, GROK_DIR / "sessions",
                         GROK_BOT_DIR, GROK_BOT_APP_DIR])

    return panel(
        "grok", GROK_DIR if has_cli else GROK_BOT_DIR,
        sections=sections, not_available=not_avail,
        version=version, last_active=iso(last),
        disk=safe(_disk, "grok disk") if with_disk and has_cli else None,
    )
