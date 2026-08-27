"""Panels for Gemini CLI, Antigravity and Cursor.

  gemini       trusted folders, MCP config, and the project-hash resolver
  antigravity  a conversation index that avoids protobuf entirely, agent
               "battles", plan artifacts, and the code tracker
  cursor       per-commit AI-vs-human attribution

Antigravity ships three surfaces (`antigravity`, `antigravity-ide`,
`antigravity-cli`) with the same layout under `~/.gemini`. They are labelled by
surface rather than merged, because merging would triple-count a conversation
that exists in more than one. `antigravity-backup` is excluded for the same
reason. Note that the two top-level `~/.antigravity*` directories hold VS Code
extensions, not agent data, and are ignored.

Cursor's `state.vscdb` keeps live auth tokens in the same key-value table as
ordinary UI state, so nothing here reads that table.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import (
    dir_size, drop_empty_columns, field, human_bytes, iso, iso_ms, newest_mtime,
    not_installed, panel, preview, ro_sqlite, safe, section, table_exists,
    tilde, unavailable,
)
from . import paths


def _json(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _workspace_name(raw: Any) -> str:
    """Leaf directory name from Antigravity's workspace_uris.

    Stored as a JSON array of file:// URIs, e.g. `["file:///a/b/repo"]`.
    Splitting the raw string on "/" leaves a trailing `"]` on the name.
    """
    if not raw:
        return "—"
    text = str(raw)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list) and parsed:
            text = str(parsed[0])
    except ValueError:
        pass
    text = text.split("://", 1)[-1].rstrip("/")
    return text.rsplit("/", 1)[-1] or "—"


def _disk(root: Path, floor: int = 1024 * 1024) -> Optional[Dict[str, Any]]:
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


# --- Gemini CLI -------------------------------------------------------------

def build_gemini(*, with_disk: bool = True) -> Dict[str, Any]:
    root = paths.GEMINI_DIR
    if not root.is_dir():
        return not_installed("gemini")
    sections: List[Dict[str, Any]] = []

    trusted = safe(lambda: _json(root / "trustedFolders.json"), "gemini trust")
    fields = []
    if isinstance(trusted, dict):
        fields.append(field("Trusted folders", len(trusted)))
    settings = safe(lambda: _json(root / "settings.json"), "gemini settings")
    if isinstance(settings, dict):
        ide = settings.get("ide")
        if isinstance(ide, dict) and ide.get("enabled") is not None:
            fields.append(field("IDE integration", bool(ide["enabled"])))
    if (root / "GEMINI.md").exists():
        size = safe(lambda: (root / "GEMINI.md").stat().st_size, "gemini md") or 0
        fields.append(field("Global instructions", human_bytes(size)))
    if fields:
        sections.append(section(
            "permissions", "Configuration", tilde(root), fields=fields,
            note="oauth_creds.json and google_accounts.json sit alongside these "
                 "and are never opened."))

    mcp = safe(lambda: _json(root / "config" / "mcp_config.json"), "gemini mcp")
    servers = mcp.get("mcpServers") if isinstance(mcp, dict) else None
    if isinstance(servers, dict) and servers:
        sections.append(section(
            "chips", "MCP servers", tilde(root / "config" / "mcp_config.json"),
            columns=["Name"], rows=[[n] for n in sorted(servers)]))

    ext = root / "extensions"
    if ext.is_dir():
        names = sorted(p.name for p in ext.iterdir() if p.is_dir())
        if names:
            sections.append(section(
                "chips", "Extensions", tilde(ext),
                columns=["Name"], rows=[[n] for n in names[:30]], total=len(names)))

    # tmp/<sha256-of-project-path> is unreadable on its own; history/<slug>/
    # .project_root maps a slug back to the real repository.
    hist = root / "history"
    if hist.is_dir():
        rows = []
        for d in sorted(hist.iterdir()):
            pr = d / ".project_root"
            if pr.exists():
                target = safe(lambda p=pr: p.read_text(encoding="utf-8").strip(), "proj root")
                rows.append([d.name, Path(str(target or "")).name or "—"])
        if rows:
            sections.append(section(
                "table", "Known projects", tilde(hist) + "/<slug>/.project_root",
                columns=["Slug", "Repository"], rows=rows[:30], total=len(rows),
                note="Gemini names its per-project scratch directories by a hash "
                     "of the path; this file is what maps them back."))

    return panel(
        "gemini", root, sections=sections,
        not_available=[unavailable(
            "quota", "Gemini CLI keeps no local record of quota or credit usage."),
            unavailable("schedules", "Gemini CLI has no scheduling feature.")],
        last_active=iso(newest_mtime([root / "tmp", root / "history"])),
        # ~/.gemini is 13 GB, nearly all of it Antigravity and a Chrome profile.
        # Sizing it here would attribute that to the CLI.
        disk=None,
    )


# --- Antigravity ------------------------------------------------------------

def build_antigravity(*, with_disk: bool = True) -> Dict[str, Any]:
    present = [(d, label) for d, label in paths.ANTIGRAVITY_SURFACES if d.is_dir()]
    if not present:
        return not_installed("antigravity")
    root = present[0][0]
    sections: List[Dict[str, Any]] = []

    # conversation_summaries.db is a derived index over the .pb conversation
    # files, so it gives us everything without parsing protobuf.
    convo_rows: List[List[Any]] = []
    battles: Dict[str, List[Dict[str, Any]]] = {}
    total_convos = 0
    for surface_dir, label in present:
        conn = ro_sqlite(surface_dir / "conversation_summaries.db")
        if conn is None:
            continue
        try:
            if not table_exists(conn, "conversation_summaries"):
                continue
            total_convos += conn.execute(
                "SELECT COUNT(*) FROM conversation_summaries").fetchone()[0]
            for r in conn.execute(
                "SELECT conversation_id, title, preview, step_count, status, "
                "       agent_name, workspace_uris, killed, nesting_depth, "
                "       battle_id, winning_conversation_id, last_modified_time "
                "FROM conversation_summaries ORDER BY last_modified_time DESC LIMIT 25"
            ):
                convo_rows.append([
                    # `title` is empty on every row in practice; `preview` is
                    # the label Antigravity actually shows the user.
                    preview(r["title"] or r["preview"]),
                    label,
                    str(r["agent_name"] or "—"),
                    r["step_count"] or 0,
                    r["nesting_depth"] or 0,
                    "killed" if r["killed"] else str(r["status"] or "—"),
                    _workspace_name(r["workspace_uris"]),
                    str(r["last_modified_time"] or ""),
                ])
            for r in conn.execute(
                "SELECT battle_id, conversation_id, title, preview, "
                "       winning_conversation_id "
                "FROM conversation_summaries WHERE battle_id != ''"
            ):
                battles.setdefault(r["battle_id"], []).append({
                    "id": r["conversation_id"],
                    "title": preview(r["title"] or r["preview"]),
                    "winner": r["winning_conversation_id"],
                })
        finally:
            conn.close()

    if convo_rows:
        cols, convo_rows = drop_empty_columns(
            ["Title", "Surface", "Agent", "Steps", "Depth", "Status",
             "Workspace", "Updated"],
            convo_rows, keep=("Title", "Surface", "Steps", "Updated"))
        sections.append(section(
            "table", "Conversations",
            tilde(root / "conversation_summaries.db"),
            columns=cols,
            rows=convo_rows, total=total_convos,
            note="Read from Antigravity's own index rather than the protobuf "
                 "conversation files, which have no public schema. Surfaces are "
                 "labelled instead of merged so a conversation is not counted twice.",
        ))

    if battles:
        tree = []
        for bid, members in list(battles.items())[:8]:
            winner = next((m["winner"] for m in members if m["winner"]), None)
            tree.append({
                "label": f"battle {bid[:8]}",
                "children": [
                    {"label": m["title"],
                     "status": "winner" if winner and m["id"] == winner else "attempt"}
                    for m in members
                ],
            })
        sections.append(section(
            "subagents", "Agent battles",
            tilde(root / "conversation_summaries.db") + " → battle_id",
            tree=tree, count=len(battles),
            note="Antigravity can run competing attempts at the same task and "
                 "record which one won. No other supported agent does this.",
        ))

    # brain/<uuid>/ holds the plan and walkthrough markdown the agent wrote,
    # plus episodic screenshots. Only counts and names are surfaced.
    plan_rows: List[List[Any]] = []
    for surface_dir, label in present:
        brain = surface_dir / "brain"
        if not brain.is_dir():
            continue
        for d in sorted(brain.iterdir(), reverse=True)[:15]:
            if not d.is_dir():
                continue
            docs = [n for n in ("task.md", "implementation_plan.md", "walkthrough.md")
                    if (d / n).exists()]
            shots = len(list(d.glob("ep*_screenshot_*.webp")))
            if docs or shots:
                plan_rows.append([d.name[:8], label, ", ".join(docs) or "—", shots,
                                  iso(safe(lambda p=d: p.stat().st_mtime, "brain mtime"))])
    if plan_rows:
        sections.append(section(
            "plans", "Plan artifacts", tilde(root / "brain") + "/<conversation>/",
            columns=["Conversation", "Surface", "Documents", "Screenshots", "Updated"],
            rows=plan_rows, total=len(plan_rows),
            note="Antigravity writes a task, an implementation plan and a "
                 "walkthrough per conversation, alongside screenshots of what it "
                 "did. Captured page DOM sits in the same folder and is not read.",
        ))

    # code_tracker/active/<repo>_<sha>/ holds pre-edit file snapshots.
    tracker_rows: List[List[Any]] = []
    for surface_dir, label in present:
        active = surface_dir / "code_tracker" / "active"
        if not active.is_dir():
            continue
        for d in sorted(active.iterdir()):
            if not d.is_dir():
                continue
            n = sum(1 for _ in d.iterdir())
            repo = d.name.rsplit("_", 1)[0]
            tracker_rows.append([repo, label, n])
    if tracker_rows:
        sections.append(section(
            "checkpoints", "Code tracker",
            tilde(root / "code_tracker" / "active") + "/<repo>_<sha>/",
            columns=["Repository", "Surface", "Files"], rows=tracker_rows,
            total=len(tracker_rows),
            note="Snapshots of files before the agent edited them, keyed by "
                 "repository and commit. Counts only — contents are not read.",
        ))

    # This cluster is the largest on disk of any agent, and most of it is
    # reclaimable, which is worth telling the user plainly.
    disk = None
    if with_disk:
        parts, total = [], 0
        reclaimable = 0
        for name in ("antigravity", "antigravity-ide", "antigravity-cli",
                     "antigravity-backup", "antigravity-browser-profile"):
            d = paths.GEMINI_DIR / name
            if not d.is_dir():
                continue
            size, _ok = dir_size(d)
            total += size
            parts.append({"label": name, "bytes": size})
            if name in ("antigravity-backup", "antigravity-browser-profile"):
                reclaimable += size
        parts.sort(key=lambda p: -p["bytes"])
        if total:
            disk = {
                "total_bytes": total, "total_human": human_bytes(total),
                "parts": parts, "complete": True,
                "reclaimable_bytes": reclaimable,
                "reclaimable_note": "A cached browser profile and a backup copy of "
                                    "the conversation store — neither is needed to "
                                    "keep your history." if reclaimable else None,
            }

    return panel(
        "antigravity", root, sections=sections,
        not_available=[unavailable(
            "quota", "Antigravity's plan and usage state is held server-side.")],
        last_active=iso(newest_mtime([d / "conversation_summaries.db" for d, _ in present]
                                     + [d / "brain" for d, _ in present])),
        disk=disk,
    )


# --- Cursor -----------------------------------------------------------------

def build_cursor(*, with_disk: bool = True) -> Dict[str, Any]:
    root = paths.CURSOR_DIR
    if not root.is_dir():
        return not_installed("cursor")
    sections: List[Dict[str, Any]] = []
    not_avail: List[Dict[str, Any]] = []

    db = root / "ai-tracking" / "ai-code-tracking.db"
    conn = ro_sqlite(db)
    if conn is not None:
        try:
            if table_exists(conn, "scored_commits"):
                total = conn.execute("SELECT COUNT(*) FROM scored_commits").fetchone()[0]
                if total:
                    rows = [
                        [preview(r["commitMessage"]),
                         str(r["branchName"] or "—"),
                         r["linesAdded"] or 0,
                         r["humanLinesAdded"] or 0,
                         (r["tabLinesAdded"] or 0) + (r["composerLinesAdded"] or 0),
                         str(r["v2AiPercentage"] or r["v1AiPercentage"] or "—"),
                         str(r["commitDate"] or "")]
                        for r in conn.execute(
                            "SELECT commitMessage, branchName, linesAdded, "
                            "       humanLinesAdded, tabLinesAdded, composerLinesAdded, "
                            "       v1AiPercentage, v2AiPercentage, commitDate "
                            "FROM scored_commits ORDER BY scoredAt DESC LIMIT 25")
                    ]
                    sections.append(section(
                        "table", "AI-authored code", tilde(db) + " → scored_commits",
                        columns=["Commit", "Branch", "Lines added", "By you",
                                 "By Cursor", "AI %", "Date"],
                        rows=rows, total=total,
                        note="Cursor scores each commit by splitting added lines "
                             "into tab-completion, composer and human. No other "
                             "supported agent measures this.",
                    ))
                else:
                    sections.append(section(
                        "table", "AI-authored code", tilde(db) + " → scored_commits",
                        columns=["Commit", "Branch", "Lines added", "By you",
                                 "By Cursor", "AI %", "Date"], rows=[],
                        empty_reason="Cursor scores each commit for how much of it "
                                     "the agent wrote, but nothing has been scored on "
                                     "this machine — the CLI has to run with commits "
                                     "in the loop to populate it.",
                    ))
            if table_exists(conn, "conversation_summaries"):
                rows = [
                    [preview(r["title"]), preview(r["tldr"]), str(r["model"] or "—"),
                     str(r["mode"] or "—"), iso_ms(r["updatedAt"])]
                    for r in conn.execute(
                        "SELECT title, tldr, model, mode, updatedAt "
                        "FROM conversation_summaries ORDER BY updatedAt DESC LIMIT 20")
                ]
                if rows:
                    sections.append(section(
                        "table", "Conversation summaries",
                        tilde(db) + " → conversation_summaries",
                        columns=["Title", "Summary", "Model", "Mode", "Updated"],
                        rows=rows))
        finally:
            conn.close()

    skills = root / "skills-cursor"
    if skills.is_dir():
        names = sorted(p.name for p in skills.iterdir() if p.is_dir())
        if names:
            sections.append(section(
                "chips", "Cursor skills", tilde(skills),
                columns=["Name"], rows=[[n] for n in names]))

    mcp = safe(lambda: _json(root / "mcp.json"), "cursor mcp")
    servers = mcp.get("mcpServers") if isinstance(mcp, dict) else None
    if isinstance(servers, dict) and servers:
        sections.append(section(
            "chips", "MCP servers", tilde(root / "mcp.json"),
            columns=["Name"], rows=[[n] for n in sorted(servers)]))

    not_avail.append(unavailable(
        "quota",
        "Cursor's plan and request limits are enforced in its cloud; no local "
        "file records them."))

    return panel(
        "cursor", root, sections=sections, not_available=not_avail,
        last_active=iso(newest_mtime([root / "projects", db])),
        disk=safe(lambda: _disk(root, floor=64 * 1024), "cursor disk") if with_disk else None,
    )
