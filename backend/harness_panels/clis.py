"""Panels for the smaller CLI harnesses.

One module rather than eight files, because each of these agents keeps only a
couple of stores worth surfacing and the extractors are short. Grouped by what
they actually record:

  qwen      todos per session, a Bash allowlist, live VS Code attach
  opencode  a real todo table, per-session diffs, project sandbox config
  cline     exit codes — one of the few harnesses that records whether a run
            succeeded — plus its teams/spawn flags
  vibe      tool-call outcomes, and an auth-health signal from its own log
  muse      a rich session index (provider, model, branch, prompt count, status)
  prime     persisted Python kernel state, unique to this agent
  pi        MCP inventory and per-directory trust
  dsh       sandbox profiles and the workspace registry

Nothing here reads a credential value or a prompt body. `~/.vibe/.env` holds a
plaintext API key at the harness root, and `~/.qwen/ide/<port>.lock` carries a
bearer token; both are reported as existing and never opened.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import (
    dir_size, field, human_bytes, iso, iso_ms, meter, newest_mtime,
    not_installed, panel, preview, ro_sqlite, safe, section, table_exists,
    tilde, unavailable, live_quota,
)
from . import paths


def _json(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _simple_disk(root: Path, floor: int = 256 * 1024) -> Optional[Dict[str, Any]]:
    if not root.is_dir():
        return None
    parts, total, complete = [], 0, True
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


# --- Qwen Code --------------------------------------------------------------

def build_qwen(*, with_disk: bool = True) -> Dict[str, Any]:
    root = paths.QWEN_DIR
    if not root.is_dir():
        return not_installed("qwen")
    sections: List[Dict[str, Any]] = []

    todos_dir = root / "todos"
    if todos_dir.is_dir():
        rows: List[List[Any]] = []
        for f in sorted(todos_dir.glob("*.json")):
            doc = safe(lambda p=f: _json(p), "qwen todos")
            items = (doc or {}).get("todos") if isinstance(doc, dict) else None
            if not isinstance(items, list):
                continue
            for it in items:
                if isinstance(it, dict):
                    rows.append([preview(it.get("content")),
                                 str(it.get("status") or "—"),
                                 f.stem[:8]])
        if rows:
            open_n = sum(1 for r in rows if r[1] not in ("completed", "done"))
            sections.append(section(
                "todos", "Todos", tilde(todos_dir) + "/<session>.json",
                columns=["Task", "Status", "Session"], rows=rows[:40],
                # With nothing open, "0 of 50" reads as "no todos"; fall back to
                # the total so the headline stays a count of what exists.
                count=open_n or None, total=len(rows),
                note=f"{open_n} still open across {len(list(todos_dir.glob('*.json')))} sessions.",
            ))

    settings = safe(lambda: _json(root / "settings.json"), "qwen settings")
    if isinstance(settings, dict):
        fields = []
        perms = settings.get("permissions")
        if isinstance(perms, dict) and isinstance(perms.get("allow"), list):
            allow = perms["allow"]
            fields.append(field("Auto-approved commands", len(allow),
                                hint=", ".join(str(a) for a in allow[:4]) or None))
        sec = settings.get("security")
        if isinstance(sec, dict):
            auth = (sec.get("auth") or {}).get("selectedType") if isinstance(sec.get("auth"), dict) else None
            if auth:
                fields.append(field("Auth method", str(auth)))
        ide = settings.get("ide")
        if isinstance(ide, dict) and ide.get("enabled") is not None:
            fields.append(field("IDE integration", bool(ide["enabled"])))
        if fields:
            sections.append(section(
                "permissions", "Configuration", tilde(root / "settings.json"),
                fields=fields))

    ide_dir = root / "ide"
    if ide_dir.is_dir():
        locks = list(ide_dir.glob("*.lock"))
        if locks:
            rows = []
            for lk in locks:
                doc = safe(lambda p=lk: _json(p), "qwen ide lock")
                if isinstance(doc, dict):
                    # authToken lives in this file and is deliberately not read.
                    rows.append([str(doc.get("ideName") or "—"),
                                 preview(doc.get("workspacePath")),
                                 str(doc.get("port") or lk.stem)])
            if rows:
                sections.append(section(
                    "table", "Editor attachments", tilde(ide_dir) + "/<port>.lock",
                    columns=["Editor", "Workspace", "Port"], rows=rows,
                    note="Left behind while an editor is connected; a stale lock "
                         "means the editor exited without cleaning up. The bearer "
                         "token in this file is never read.",
                ))

    return panel(
        "qwen", root, sections=sections,
        not_available=[unavailable(
            "quota", "Qwen Code keeps no local record of plan or credit usage.")],
        last_active=iso(newest_mtime([root / "projects", root / "todos"])),
        disk=safe(lambda: _simple_disk(root), "qwen disk") if with_disk else None,
    )


# --- OpenCode ---------------------------------------------------------------

def build_opencode(*, with_disk: bool = True) -> Dict[str, Any]:
    data = paths.opencode_data_dir()
    db = data / "opencode.db"
    if not data.is_dir():
        return not_installed("opencode")
    sections: List[Dict[str, Any]] = []

    quota = safe(lambda: live_quota("opencode"), "opencode quota")
    if quota:
        sections.append(quota)


    conn = ro_sqlite(db)
    if conn is not None:
        try:
            if table_exists(conn, "todo"):
                cols = {r[1] for r in conn.execute("PRAGMA table_info(todo)")}
                # Schema varies by release; only select what this DB actually has.
                text_col = next((c for c in ("content", "text", "title") if c in cols), None)
                status_col = "status" if "status" in cols else None
                if text_col:
                    q = f"SELECT {text_col}" + (f", {status_col}" if status_col else "") + " FROM todo LIMIT 60"
                    rows = [[preview(r[0]), str(r[1]) if status_col else "—"]
                            for r in conn.execute(q)]
                    if rows:
                        total = conn.execute("SELECT COUNT(*) FROM todo").fetchone()[0]
                        open_n = sum(1 for r in rows if r[1] not in ("completed", "done"))
                        sections.append(section(
                            "todos", "Todo board", tilde(db) + " → todo",
                            columns=["Task", "Status"], rows=rows,
                            count=open_n or None, total=total,
                            note="OpenCode is one of the few agents with a "
                                 "first-class todo table rather than per-session files.",
                        ))
            if table_exists(conn, "project"):
                cols = {r[1] for r in conn.execute("PRAGMA table_info(project)")}
                want = [c for c in ("name", "worktree", "vcs", "sandboxes", "time_updated") if c in cols]
                if want:
                    rows = []
                    for r in conn.execute(f"SELECT {', '.join(want)} FROM project LIMIT 30"):
                        rec = dict(zip(want, r))
                        rows.append([
                            preview(rec.get("name") or Path(str(rec.get("worktree") or "")).name),
                            str(rec.get("vcs") or "—"),
                            # `sandboxes` is a JSON blob; show whether any exist,
                            # not its contents.
                            "yes" if (rec.get("sandboxes") or "").strip() not in ("", "[]", "{}", "null") else "—",
                            iso_ms(rec.get("time_updated")),
                        ])
                    if rows:
                        sections.append(section(
                            "table", "Projects", tilde(db) + " → project",
                            columns=["Name", "VCS", "Sandboxes", "Updated"], rows=rows))
        finally:
            conn.close()

    diffs = data / "storage" / "session_diff"
    if diffs.is_dir():
        files = list(diffs.glob("*.json"))
        if files:
            size = sum(safe(lambda p=f: p.lstat().st_size, "diff size") or 0 for f in files)
            sections.append(section(
                "fields", "Session diffs", tilde(diffs) + "/<session>.json",
                fields=[field("Sessions with a recorded diff", len(files)),
                        field("Stored", human_bytes(size))],
                note="Changed files per session, recorded by OpenCode itself — "
                     "no git required. File contents are not read.",
            ))

    snap = data / "snapshot"
    if snap.is_dir():
        size, ok = dir_size(snap)
        if size:
            sections.append(section(
                "checkpoints", "Snapshot store", tilde(snap),
                columns=["Metric", "Value"],
                rows=[["Objects on disk", human_bytes(size) + ("" if ok else " or more")]],
                note="A content-addressed object store OpenCode uses for "
                     "checkpoints. There is no manifest, so only its size is known.",
            ))

    return panel(
        "opencode", data, sections=sections,
        not_available=[unavailable(
            "schedules", "OpenCode has no local scheduling store.")],
        last_active=iso(newest_mtime([db, data / "storage"])),
        disk=safe(lambda: _simple_disk(data), "opencode disk") if with_disk else None,
    )


# --- Cline ------------------------------------------------------------------

_CLINE_DONE = frozenset({"completed", "finished", "done", "failed", "error", "cancelled"})


def build_cline(*, with_disk: bool = True) -> Dict[str, Any]:
    root = paths.CLINE_DIR
    if not root.is_dir():
        return not_installed("cline")
    sections: List[Dict[str, Any]] = []

    sess_dir = root / "data" / "sessions"
    rows: List[List[Any]] = []
    teams = 0
    if sess_dir.is_dir():
        for d in sorted(sess_dir.iterdir(), reverse=True):
            if not d.is_dir():
                continue
            meta = next((f for f in d.glob("*.json") if not f.name.endswith(".messages.json")), None)
            if meta is None:
                continue
            doc = safe(lambda p=meta: _json(p), "cline session")
            if not isinstance(doc, dict):
                continue
            if doc.get("enable_teams"):
                teams += 1
            code = doc.get("exit_code")
            rows.append([
                Path(str(doc.get("cwd") or "")).name or "—",
                str(doc.get("model") or "—"),
                str(doc.get("provider") or "—"),
                str(doc.get("status") or "—"),
                # exit_code 0 is success; rendering it as the integer 0 would be
                # mistaken for "no data", so it becomes an explicit verdict.
                ("ok" if code == 0 else f"exit {code}") if code is not None else "—",
                doc.get("started_at"),
            ])
    if rows:
        failed = sum(1 for r in rows if r[4].startswith("exit") and r[4] != "exit 0")
        sections.append(section(
            "table", "Runs", tilde(sess_dir) + "/<id>/<id>.json",
            columns=["Project", "Model", "Provider", "Status", "Result", "Started"],
            rows=rows[:30], count=failed or len(rows), total=len(rows),
            severity="warn" if failed else None,
            note=("Cline records an exit code, which most harnesses do not — "
                  f"{failed} of {len(rows)} runs ended non-zero." if failed else
                  "Cline records an exit code for each run, which most harnesses do not."),
        ))

    providers = safe(lambda: _json(root / "data" / "settings" / "providers.json"), "cline providers")
    if isinstance(providers, dict):
        configured = providers.get("providers")
        fields = [field("Last used provider", str(providers.get("lastUsedProvider") or "—"))]
        if isinstance(configured, (dict, list)):
            fields.append(field("Configured providers", len(configured)))
        if teams:
            fields.append(field("Sessions using teams", teams))
        sections.append(section(
            "permissions", "Providers",
            tilde(root / "data" / "settings" / "providers.json"),
            fields=fields,
            note="API keys live in this file and are not read."))

    not_avail = []
    cron = root / "cron"
    if cron.is_dir() and not any(cron.iterdir()):
        not_avail.append(unavailable(
            "schedules",
            "Cline has a cron directory but it is empty — the feature exists and "
            "nothing is scheduled yet."))

    return panel(
        "cline", root, sections=sections, not_available=not_avail,
        last_active=iso(newest_mtime([sess_dir])),
        disk=safe(lambda: _simple_disk(root), "cline disk") if with_disk else None,
    )


# --- Mistral Vibe -----------------------------------------------------------

_HTTP_STATUS = re.compile(r"\b([1-5]\d\d)\b")


def build_vibe(*, with_disk: bool = True) -> Dict[str, Any]:
    root = paths.VIBE_DIR
    if not root.is_dir():
        return not_installed("vibe")
    sections: List[Dict[str, Any]] = []

    # Auth health: the last HTTP status in the app log tells you whether this
    # agent still works. On this machine it stopped at two 401s in April and was
    # never used again — something a user would otherwise never notice.
    log = root / "vibe.log"
    if log.exists():
        last_status = None
        last_line_no_status = True
        try:
            tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-400:]
            for line in reversed(tail):
                if "api.mistral.ai" in line or "HTTP" in line or "status" in line.lower():
                    m = _HTTP_STATUS.search(line)
                    if m:
                        last_status = int(m.group(1))
                        last_line_no_status = False
                        break
        except OSError:
            pass
        if last_status is not None:
            ok = 200 <= last_status < 300
            sections.append(section(
                "permissions", "Connection health", tilde(log),
                fields=[
                    field("Last API status", last_status,
                          severity=None if ok else "crit",
                          hint=None if ok else "Requests are being rejected — the API key has likely expired."),
                    field("Log last written", iso(safe(lambda: log.stat().st_mtime, "vibe log mtime"))),
                ],
                severity="ok" if ok else "crit",
                note="Read from the log's status lines only; the API key in "
                     "~/.vibe/.env is never opened.",
            ))

    # Per-session tool outcomes: TokenTelemetry already opens these files for
    # token counts and throws the approval/failure breakdown away.
    sess_dir = root / "logs" / "session"
    if sess_dir.is_dir():
        rows: List[List[Any]] = []
        for f in sorted(sess_dir.glob("session_*.json"), reverse=True)[:20]:
            doc = safe(lambda p=f: _json(p), "vibe session")
            meta = (doc or {}).get("metadata") if isinstance(doc, dict) else None
            stats = (meta or {}).get("stats") if isinstance(meta, dict) else None
            if not isinstance(stats, dict):
                continue
            rows.append([
                (meta.get("start_time") or f.stem),
                stats.get("tool_calls_agreed") or 0,
                stats.get("tool_calls_rejected") or 0,
                stats.get("tool_calls_succeeded") or 0,
                stats.get("tool_calls_failed") or 0,
                round(float(stats.get("session_cost") or 0), 4),
            ])
        if rows:
            sections.append(section(
                "table", "Tool-call outcomes", tilde(sess_dir) + "/session_*.json",
                columns=["Session", "Agreed", "Rejected", "Succeeded", "Failed", "Cost"],
                rows=rows, total=len(rows),
                note="Vibe computes its own session cost from the per-model "
                     "prices in config.toml, so this is its figure rather than "
                     "TokenTelemetry's — useful as a cross-check.",
            ))

    return panel(
        "vibe", root, sections=sections,
        not_available=[unavailable(
            "subagents",
            "Vibe is a single-agent loop with no delegation, MCP servers, "
            "checkpoints or todos — there is nothing of that kind on disk.")],
        last_active=iso(newest_mtime([sess_dir, log])),
        disk=safe(lambda: _simple_disk(root), "vibe disk") if with_disk else None,
    )


# --- Muse Code --------------------------------------------------------------

def build_muse(*, with_disk: bool = True) -> Dict[str, Any]:
    root = paths.MUSE_DIR
    if not root.is_dir():
        return not_installed("muse")
    sections: List[Dict[str, Any]] = []

    conn = ro_sqlite(root / "session-index.db")
    if conn is not None:
        try:
            if table_exists(conn, "sessions"):
                total = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
                rows = [
                    [preview(r["title"]),
                     str(r["provider_id"] or "—"),
                     str(r["model_id"] or "—"),
                     str(r["git_branch"] or "—"),
                     r["prompt_count"] or 0,
                     str(r["status"] or "—"),
                     iso_ms((r["updated_at_us"] or 0) / 1000 if r["updated_at_us"] else None)]
                    for r in conn.execute(
                        "SELECT title, provider_id, model_id, git_branch, prompt_count, "
                        "       status, updated_at_us FROM sessions "
                        "ORDER BY updated_at_us DESC LIMIT 25")
                ]
                if rows:
                    sections.append(section(
                        "table", "Sessions",
                        tilde(root / "session-index.db") + " → sessions",
                        columns=["Title", "Provider", "Model", "Branch",
                                 "Prompts", "Status", "Updated"],
                        rows=rows, total=total,
                        note="Muse maintains its own session index, so this needs "
                             "no transcript parsing. `first_user_prompt` is stored "
                             "alongside and is not read.",
                    ))
        finally:
            conn.close()

    skills = root / "skills"
    if skills.is_dir():
        names = sorted(p.name for p in (skills / "bundled").iterdir()
                       if (skills / "bundled").is_dir() and p.is_dir())
        if names:
            sections.append(section(
                "chips", "Bundled skills", tilde(skills / "bundled"),
                columns=["Name"], rows=[[n] for n in names]))

    cat = root / "model-catalog"
    if cat.is_dir():
        files = list(cat.glob("*.json"))
        if files:
            sections.append(section(
                "fields", "Model catalogue", tilde(cat),
                fields=[field("Cached catalogues", len(files))],
                note="Filenames are hex-encoded provider keys."))

    return panel(
        "muse", root, sections=sections,
        last_active=iso(newest_mtime([root / "session-index.db", paths.MUSE_SESSIONS_DIR])),
        disk=safe(lambda: _simple_disk(root), "muse disk") if with_disk else None,
    )


# --- Prime Agent ------------------------------------------------------------

def build_prime(*, with_disk: bool = True) -> Dict[str, Any]:
    root = paths.PRIME_DIR
    if not root.is_dir():
        return not_installed("prime")
    sections: List[Dict[str, Any]] = []

    # The distinctive thing about Prime: a Python kernel that survives between
    # turns. kernel-state.json lists which variables were persisted. The sibling
    # .dill is a pickle and is never opened.
    art = root / "session-artifacts"
    if art.is_dir():
        rows: List[List[Any]] = []
        for d in sorted(art.iterdir(), reverse=True):
            if not d.is_dir():
                continue
            doc = safe(lambda p=d: _json(p / "kernel-state.json"), "prime kernel")
            if not isinstance(doc, dict):
                continue
            names = doc.get("savedNames")
            rows.append([
                d.name[:8],
                len(names) if isinstance(names, list) else 0,
                ", ".join(str(n) for n in names[:6]) if isinstance(names, list) else "—",
                human_bytes(float(doc.get("bytes") or 0)),
                str(doc.get("pythonVersion") or "—"),
            ])
        if rows:
            sections.append(section(
                "checkpoints", "Persisted kernel state",
                tilde(art) + "/<session>/kernel-state.json",
                columns=["Session", "Variables", "Names", "Size", "Python"],
                rows=rows[:20], total=len(rows),
                note="Prime keeps a live Python kernel per session, so variables "
                     "survive between turns. No other supported agent does this. "
                     "The pickled values themselves are never loaded.",
            ))

    workers = root / "daemon-workers"
    if workers.is_dir():
        live = [d.name for d in workers.iterdir() if d.is_dir()]
        sections.append(section(
            "fields", "Daemon", tilde(workers),
            fields=[field("Registered workers", len(live))],
            note="Prime runs a supervisor daemon with one worker per session; "
                 "these directories are populated only while it is running."))

    settings = safe(lambda: _json(root / "settings.json"), "prime settings")
    if isinstance(settings, dict):
        fields = [f for f in (
            field("Provider", str(settings["defaultProvider"])) if settings.get("defaultProvider") else None,
            field("Model", str(settings["defaultModel"])) if settings.get("defaultModel") else None,
            field("Thinking level", str(settings["defaultThinkingLevel"])) if settings.get("defaultThinkingLevel") else None,
        ) if f]
        if fields:
            sections.append(section(
                "fields", "Configuration", tilde(root / "settings.json"), fields=fields))

    return panel(
        "prime", root, sections=sections,
        last_active=iso(newest_mtime([paths.PRIME_SESSIONS_DIR, root / "logs"])),
        disk=safe(lambda: _simple_disk(root), "prime disk") if with_disk else None,
    )


# --- pi ---------------------------------------------------------------------

def build_pi(*, with_disk: bool = True) -> Dict[str, Any]:
    root = paths.PI_DIR
    if not root.is_dir():
        return not_installed("pi")
    sections: List[Dict[str, Any]] = []

    mcp = safe(lambda: _json(root / "mcp.json"), "pi mcp")
    servers = (mcp or {}).get("mcpServers") if isinstance(mcp, dict) else None
    if isinstance(servers, dict) and servers:
        rows = []
        for name, cfg in sorted(servers.items()):
            cmd = cfg.get("command") if isinstance(cfg, dict) else None
            args = cfg.get("args") if isinstance(cfg, dict) else None
            rows.append([name, str(cmd or "—"),
                         " ".join(str(a) for a in args[:3]) if isinstance(args, list) else "—"])
        sections.append(section(
            "table", "MCP servers", tilde(root / "mcp.json"),
            columns=["Name", "Command", "Args"], rows=rows,
            note="Environment values in this file may hold secrets and are not read."))

    trust = safe(lambda: _json(root / "trust.json"), "pi trust")
    settings = safe(lambda: _json(root / "settings.json"), "pi settings")
    fields = []
    if isinstance(trust, dict):
        fields.append(field("Trusted directories",
                            sum(1 for v in trust.values() if v)))
    if isinstance(settings, dict):
        for label, key in (("Provider", "defaultProvider"), ("Model", "defaultModel"),
                           ("Thinking level", "defaultThinkingLevel")):
            if settings.get(key):
                fields.append(field(label, str(settings[key])))
    if fields:
        sections.append(section(
            "permissions", "Configuration", tilde(root), fields=fields))

    return panel(
        "pi", root, sections=sections,
        not_available=[unavailable(
            "quota",
            "pi transcripts carry no token or usage events, so neither cost nor "
            "quota can be derived from local files.")],
        last_active=iso(newest_mtime([root / "sessions"])),
        disk=safe(lambda: _simple_disk(root), "pi disk") if with_disk else None,
    )


# --- DeepSeek Harness -------------------------------------------------------

def build_dsh(*, with_disk: bool = True) -> Dict[str, Any]:
    root = paths.DSH_DIR
    if not root.is_dir():
        return not_installed("dsh")
    sections: List[Dict[str, Any]] = []

    # Sandbox profiles are DSH's environment-as-code feature: named dev
    # environments it can launch an agent into.
    prof = root / "profiles"
    if prof.is_dir():
        rows = []
        for d in sorted(prof.iterdir()):
            if not d.is_dir() or d.name == "node_modules":
                continue
            has_base = (d / "cordis.yml").exists()
            has_patch = (d / "cordis.patch.yml").exists()
            rows.append([d.name,
                         "yes" if has_base else "—",
                         "yes" if has_patch else "—"])
        if rows:
            sections.append(section(
                "plans", "Sandbox profiles", tilde(prof) + "/<name>/cordis.yml",
                columns=["Profile", "Base", "Patch"], rows=rows,
                note="Reusable environment definitions DSH can spin an agent into.",
            ))

    ws = safe(lambda: _json(root / "storages" / "workspace.json"), "dsh workspace")
    if isinstance(ws, dict):
        tables = ws.get("tables")
        spaces = (tables or {}).get("workspaces") if isinstance(tables, dict) else None
        if isinstance(spaces, dict) and spaces:
            rows = []
            for wid, rec in list(spaces.items())[:25]:
                if not isinstance(rec, dict):
                    continue
                ids = rec.get("sessionIds")
                rows.append([
                    preview(rec.get("title") or Path(str(rec.get("path") or "")).name),
                    len(ids) if isinstance(ids, list) else 0,
                    iso_ms(rec.get("updatedAt")),
                ])
            if rows:
                sections.append(section(
                    "table", "Workspaces",
                    tilde(root / "storages" / "workspace.json"),
                    columns=["Title", "Sessions", "Updated"], rows=rows,
                    note="DSH keeps its own workspace registry with human titles, "
                         "which the cwd-derived project list cannot provide."))

    try:
        import yaml  # already a backend dependency
        s = root / "settings.yaml"
        if s.exists():
            doc = yaml.safe_load(s.read_text(encoding="utf-8")) or {}
            model = doc.get("agent-default-model") if isinstance(doc, dict) else None
            if isinstance(model, dict):
                sections.append(section(
                    "fields", "Default model", tilde(s),
                    fields=[field("Provider", str(model.get("provider") or "—")),
                            field("Model", str(model.get("model") or "—"))],
                    note="Credentials live in .credentials.yaml and are not read."))
    except Exception:
        pass

    # DSH is the one harness whose transcripts need a third-party codec, and
    # the scanner skips them silently when it's absent. The visible result is a
    # contradiction with nothing on screen to explain it: the agent reports
    # hundreds of megabytes of sessions on disk and zero sessions counted. Name
    # the cause rather than leaving the gap unexplained.
    not_avail: List[Dict[str, Any]] = []
    try:
        import zstandard  # noqa: F401
    except ImportError:
        sess_dir = root / "sessions"
        found = (len(list(sess_dir.glob("*/*/session.jsonl.zstd")))
                 if sess_dir.is_dir() else 0)
        not_avail.append(unavailable(
            "sessions",
            f"DSH compresses transcripts with zstd, and the `zstandard` package "
            f"is missing from this backend's environment. {found} session file"
            f"{'' if found == 1 else 's'} on disk cannot be read, so DSH counts "
            f"zero sessions everywhere in TokenTelemetry. Reinstalling backend "
            f"dependencies (./start.sh) restores them."))

    return panel(
        "dsh", root, sections=sections, not_available=not_avail,
        last_active=iso(newest_mtime([root / "sessions"])),
        disk=safe(lambda: _simple_disk(root), "dsh disk") if with_disk else None,
    )


# --- Qoder ------------------------------------------------------------------
#
# These readers duplicate a little of main._qoder_parse_session on purpose: this
# package is imported BY main, so importing back would be circular — the same
# reason paths.py restates the directory constants.

_QODER_REMINDER_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)


def _qoder_stats(path: Path) -> Optional[Dict[str, Any]]:
    """Session id, model, branch, turn count and credit total for one transcript."""
    out: Dict[str, Any] = {
        "id": path.stem, "model": None, "branch": "", "turns": 0,
        "credits": 0.0, "display": "", "version": None, "mtime": None,
    }
    try:
        out["mtime"] = path.stat().st_mtime
    except OSError:
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if not isinstance(row, dict):
                    continue
                if isinstance(row.get("sessionId"), str) and row["sessionId"]:
                    out["id"] = row["sessionId"]
                if isinstance(row.get("gitBranch"), str) and row["gitBranch"]:
                    out["branch"] = row["gitBranch"]
                if isinstance(row.get("version"), str) and row["version"]:
                    out["version"] = row["version"]
                rtype = row.get("type")
                if rtype == "assistant":
                    msg = row.get("message") or {}
                    out["turns"] += 1
                    if isinstance(msg.get("model"), str) and msg["model"]:
                        out["model"] = msg["model"]
                    usage = msg.get("usage")
                    if isinstance(usage, dict):
                        credits = usage.get("credits")
                        if isinstance(credits, (int, float)) and not isinstance(credits, bool):
                            out["credits"] += float(credits)
                elif rtype == "user" and not out["display"]:
                    # Only a human turn, and only after stripping the plugin
                    # block Qoder splices onto the opening prompt.
                    if (row.get("origin") or {}).get("kind") == "human":
                        text = "".join(
                            b.get("text") or ""
                            for b in ((row.get("message") or {}).get("content") or [])
                            if isinstance(b, dict) and b.get("type") == "text"
                        )
                        out["display"] = _QODER_REMINDER_RE.sub("", text).strip()
    except OSError:
        return None
    return out


def _qoder_child_stats(session_dir: Path) -> List[Dict[str, Any]]:
    """Subagent transcripts for one session, with their credit spend."""
    sub = session_dir / "subagents"
    if not sub.is_dir():
        return []
    kids: List[Dict[str, Any]] = []
    for transcript in sorted(sub.glob("*.jsonl")):
        stats = _qoder_stats(transcript)
        if not stats:
            continue
        # Children carry the parent's sessionId, so the filename is the only
        # thing that tells two spawns apart.
        stats["id"] = transcript.stem
        meta = _json(transcript.with_suffix(".meta.json"))
        if isinstance(meta, dict):
            stats["agent_type"] = meta.get("agentType") or "subagent"
            stats["description"] = meta.get("description") or ""
        kids.append(stats)
    return kids


def _qoder_ide_titles() -> Dict[str, Dict[str, Any]]:
    """Human-readable session titles from the IDE's mirror database.

    The IDE projects the same sessions into SQLite (rows are marked
    source="sdk-projection" and reuse the JSONL uuids), so it is used only to
    name them — never counted as sessions of its own. Opened read-only and
    best-effort; the app holds a large WAL while running.
    """
    db = paths.QODER_IDE_DIR / "main.sqlite"
    conn = ro_sqlite(db)
    if conn is None:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    try:
        if not table_exists(conn, "chat_sessions"):
            return {}
        for sid, title, kind in conn.execute(
            "SELECT session_id, title, session_kind FROM chat_sessions "
            "WHERE deleted_at IS NULL"
        ):
            if isinstance(sid, str) and sid:
                out[sid] = {"title": (title or "").strip(), "kind": kind or "standard"}
    except Exception:
        return out
    finally:
        conn.close()
    return out


def _qoder_disk(cli: Path, ide: Path) -> Optional[Dict[str, Any]]:
    """Footprint across BOTH Qoder roots.

    The CLI tree under ~/.qoder is the smaller half; the Electron store in
    Application Support is usually twice its size. Reporting only the dotfile
    root would understate the agent by about two thirds.
    """
    doc = _simple_disk(cli)
    if doc is None:
        return None
    if ide.is_dir():
        size, complete = dir_size(ide)
        doc["total_bytes"] += size
        doc["total_human"] = human_bytes(doc["total_bytes"])
        doc["complete"] = doc.get("complete", True) and complete
        doc["parts"].append({"label": "IDE (Application Support)", "bytes": size})
        doc["parts"].sort(key=lambda p: -p["bytes"])
        doc["parts"] = doc["parts"][:8]
    return doc


def build_qoder(*, with_disk: bool = True) -> Dict[str, Any]:
    """Qoder: credits, sessions and delegation from its Claude-shaped JSONL.

    Everything money-shaped here is denominated in CREDITS. Qoder writes an
    Anthropic-shaped `usage` block whose token counters are all zero and puts
    the real figure in `credits`, so a credit total is the only spend this
    harness actually records.

    Reads no credential: ~/.qoder/.auth, auth.v1.dat, auth.machine-id and the
    IDE's byok_model_credentials / mcp_oauth_credentials tables are never
    opened. `.qoder-app-status.json` holds the account holder's name and email
    and is deliberately not read at all.
    """
    root = paths.QODER_DIR
    projects = root / "projects"
    if not projects.is_dir():
        return not_installed("qoder")

    sections: List[Dict[str, Any]] = []
    ide_titles = safe(lambda: _qoder_ide_titles(), "qoder ide titles") or {}

    rows: List[List[Any]] = []
    total_credits = 0.0
    delegated_credits = 0.0
    spawns = 0
    version = None
    for transcript in sorted(projects.glob("*/*.jsonl")):
        stats = safe(lambda p=transcript: _qoder_stats(p), "qoder session")
        if not stats:
            continue
        version = stats.get("version") or version
        kids = safe(lambda p=transcript: _qoder_child_stats(p.parent / p.stem),
                    "qoder subagents") or []
        kid_credits = round(sum(k["credits"] for k in kids), 4)
        total_credits += stats["credits"]
        delegated_credits += kid_credits
        spawns += len(kids)
        meta = ide_titles.get(stats["id"]) or {}
        rows.append([
            preview(meta.get("title") or stats["display"] or stats["id"][-8:]),
            stats["model"] or "—",
            stats["branch"] or "—",
            stats["turns"],
            round(stats["credits"], 3),
            kid_credits or 0,
            iso(stats["mtime"]),
        ])

    if rows:
        rows.sort(key=lambda r: r[6] or "", reverse=True)
        sections.append(section(
            "table", "Sessions", tilde(projects),
            columns=["Session", "Model", "Branch", "Turns", "Credits",
                     "Delegated", "Updated"],
            rows=rows[:40], total=len(rows),
            note="Credits are Qoder's own billing unit, read from each turn's "
                 "usage record. Delegated credits are spent by subagents and "
                 "are additional to the parent's own.",
        ))

    if total_credits or delegated_credits:
        combined = total_credits + delegated_credits
        share = (delegated_credits / combined * 100.0) if combined else 0.0
        sections.append(section(
            "meter", "Credit spend", tilde(projects),
            meters=[
                meter("Delegated to subagents", share,
                      detail=f"{delegated_credits:.2f} of {combined:.2f} credits "
                             f"across {spawns} spawn{'' if spawns == 1 else 's'}"),
            ],
            count=round(combined, 2),
            note=f"{combined:.2f} credits total — {total_credits:.2f} in the "
                 f"main sessions, {delegated_credits:.2f} in subagents. Qoder "
                 f"publishes no credit-to-currency rate locally, so this is "
                 f"deliberately not converted to dollars.",
        ))

    plugins = safe(lambda: _json(root / "plugins" / "installed_plugins_v2.json"),
                   "qoder plugins")
    fields: List[Dict[str, Any]] = []
    if version:
        fields.append(field("CLI version", version))
    if isinstance(plugins, dict) and isinstance(plugins.get("plugins"), dict):
        names = sorted(plugins["plugins"].keys())
        fields.append(field("Installed plugins", len(names),
                            hint=", ".join(names[:6]) if names else None))
    settings = safe(lambda: _json(root / "settings.json"), "qoder settings")
    if isinstance(settings, dict) and isinstance(settings.get("enabledPlugins"), dict):
        fields.append(field("Enabled plugins",
                            sum(1 for v in settings["enabledPlugins"].values() if v)))
    for name, label in ((".auth", "Credential store"),
                        (".qoder-app-status.json", "Account status file")):
        target = root / name
        if target.exists():
            fields.append(field(label, "present",
                                hint="Existence only — never opened."))
    if fields:
        sections.append(section("fields", "Install", tilde(root), fields=fields))

    not_avail = [
        unavailable("tokens",
            "Qoder records no token counts. Every turn carries an "
            "Anthropic-shaped usage block whose input, output and cache "
            "counters are all zero, and bills in credits instead — so the "
            "0 tokens and $0.00 shown elsewhere are what Qoder reports, not a "
            "failed scan. The credit figures above are the real spend."),
        unavailable("models",
            "Model ids stay opaque. Qoder reports internal names such as "
            "qmodel_38max, and its catalogue at .models/<uid>/catalog-v6 is "
            "encrypted at rest, so there is no offline mapping to a real "
            "model — and no published price list to cost it against."),
        unavailable("session state",
            "Per-session state.json is encrypted (each item carries a "
            "ciphertext payload and an auth tag), so resumable context, "
            "compaction state and todos cannot be read. Opaque by design, "
            "not a missing store."),
    ]

    return panel(
        "qoder", root, sections=sections, not_available=not_avail,
        version=version,
        last_active=iso(newest_mtime([projects])),
        disk=(safe(lambda: _qoder_disk(root, paths.QODER_IDE_DIR), "qoder disk")
              if with_disk else None),
    )


# --- SmallCode --------------------------------------------------------------

def build_smallcode(*, with_disk: bool = True) -> Dict[str, Any]:
    roots = paths.smallcode_roots()
    if not roots:
        # SmallCode is project-local, so absence here usually means the roots
        # env var is unset rather than that the agent isn't installed.
        doc = not_installed("smallcode")
        doc["planned"] = False
        return doc

    rows: List[List[Any]] = []
    for root in roots:
        traces = root / ".smallcode" / "traces"
        for f in sorted(traces.glob("*.json"), reverse=True)[:40]:
            doc = safe(lambda p=f: _json(p), "smallcode trace")
            if not isinstance(doc, dict):
                continue
            steps = doc.get("steps")
            rows.append([
                preview(doc.get("name") or f.stem),
                str(doc.get("model") or "—"),
                len(steps) if isinstance(steps, list) else 0,
                root.name,
                iso(safe(lambda p=f: p.stat().st_mtime, "trace mtime")),
            ])
    sections = []
    if rows:
        sections.append(section(
            "table", "Traces", "<project>/.smallcode/traces/*.json",
            columns=["Name", "Model", "Steps", "Project", "When"],
            rows=rows[:40], total=len(rows),
            note="SmallCode stores traces inside each repository rather than in "
                 "your home directory, so only projects listed in "
                 "TT_SMALLCODE_ROOTS are visible here."))

    return panel(
        "smallcode", roots[0] / ".smallcode", sections=sections,
        last_active=iso(newest_mtime([r / ".smallcode" / "traces" for r in roots])),
        disk=None,
    )
