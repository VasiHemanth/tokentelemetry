"""Per-agent transcript-retention metadata + TT archive opt-in flags.

Coding agents prune their own on-disk transcripts on different schedules. The
Settings page surfaces each agent's default so a user understands *why* old
sessions vanish from analytics — and can opt into having TokenTelemetry keep a
durable copy (tier-2 archive in ``history_store``) past that window.

The numbers below are the **published defaults** at time of writing (verified
2026-06); where an agent has no documented auto-cleanup we say so rather than
guess. Claude Code and Gemini CLI expose the period in their own settings.json,
so we read the user's *actual* value when present and fall back to the default.

Sources:
  - Claude Code  ``cleanupPeriodDays`` default 30 — code.claude.com/docs/en/data-usage
  - Gemini CLI   chat-history retention default 30d (cleanup enabled) — gemini-cli PR #20853
  - Codex CLI    indefinite, no auto-cleanup — openai/codex issue #6015
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from tt_paths import data_dir

_log = logging.getLogger("tokentelemetry.retention")

HOME = Path.home()
RETENTION_FILE = data_dir() / "retention.json"

# Static per-agent retention description. ``default_days``:
#   int  → auto-deletes after N days (a documented default).
#   None → no documented auto-cleanup (kept until the user clears it).
# ``configurable`` flags whether the agent lets users change the window, and
# ``settings_hint`` tells the UI where. ``note`` carries any caveat.
_RETENTION: Dict[str, Dict[str, Any]] = {
    "claude": {
        "label": "Claude Code",
        "default_days": 30,
        "configurable": True,
        "settings_hint": "~/.claude/settings.json → cleanupPeriodDays",
        "note": "Purges transcripts older than the window on every startup.",
    },
    "gemini": {
        "label": "Gemini CLI",
        "default_days": 30,
        "configurable": True,
        "settings_hint": "~/.gemini/settings.json → chat history maxAge",
        "note": "Cleanup enabled by default; also supports a maxCount cap.",
    },
    "qwen": {
        "label": "Qwen Code",
        "default_days": 30,
        "configurable": True,
        "settings_hint": "~/.qwen/settings.json (Gemini-CLI fork)",
        "note": "Gemini-CLI fork — inherits the same 30-day cleanup default.",
    },
    "codex": {
        "label": "Codex CLI",
        "default_days": None,
        "configurable": False,
        "settings_hint": None,
        "note": "No auto-cleanup today — sessions accumulate in ~/.codex/sessions.",
    },
    "opencode": {
        "label": "OpenCode",
        "default_days": None,
        "configurable": False,
        "settings_hint": None,
        "note": "Stored in a local SQLite DB; no automatic pruning.",
    },
    "hermes": {
        "label": "Hermes",
        "default_days": None,
        "configurable": False,
        "settings_hint": None,
        "note": "Stored in a local SQLite DB; no automatic pruning.",
    },
    "grok": {
        "label": "Grok CLI",
        "default_days": None,
        "configurable": False,
        "settings_hint": None,
        "note": "Append-only JSONL logs; no automatic pruning.",
    },
    "antigravity": {
        "label": "Antigravity",
        "default_days": None,
        "configurable": False,
        "settings_hint": None,
        "note": "Retention behaviour not documented — treated as kept until cleared.",
    },
    "cursor": {
        "label": "Cursor",
        "default_days": None,
        "configurable": False,
        "settings_hint": None,
        "note": "Retention behaviour not documented — treated as kept until cleared.",
    },
    "copilot": {
        "label": "GitHub Copilot",
        "default_days": None,
        "configurable": False,
        "settings_hint": None,
        "note": "Retention behaviour not documented — treated as kept until cleared.",
    },
    "vibe": {
        "label": "Vibe",
        "default_days": None,
        "configurable": False,
        "settings_hint": None,
        "note": "Retention behaviour not documented — treated as kept until cleared.",
    },
}

# Which agents we can actually archive (single-file resolvable transcript).
# Must stay in sync with main._resolve_transcript_path.
_ARCHIVABLE = {"claude", "codex"}


def _read_claude_cleanup_days() -> Optional[int]:
    """The user's real cleanupPeriodDays from ~/.claude/settings.json, else None."""
    f = HOME / ".claude" / "settings.json"
    if not f.exists():
        return None
    try:
        with open(f, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        v = raw.get("cleanupPeriodDays")
        return int(v) if isinstance(v, (int, float)) else None
    except Exception:  # noqa: BLE001
        return None


# ── archive opt-in flags (persisted) ─────────────────────────────────────────

def _load_flags() -> Dict[str, bool]:
    if not RETENTION_FILE.exists():
        return {}
    try:
        with open(RETENTION_FILE, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except Exception:  # noqa: BLE001
        return {}
    archive = raw.get("archive") if isinstance(raw, dict) else None
    if not isinstance(archive, dict):
        return {}
    return {k: bool(v) for k, v in archive.items() if isinstance(k, str)}


def _save_flags(flags: Dict[str, bool]) -> None:
    import os
    import tempfile
    RETENTION_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(RETENTION_FILE.parent),
                               prefix="retention.json.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"archive": flags}, fh, indent=2)
        os.replace(tmp, RETENTION_FILE)
    except Exception:  # noqa: BLE001
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def archive_enabled(agent: str) -> bool:
    """Has the user opted into archiving this agent's transcripts in TT?"""
    return bool(_load_flags().get(agent, False)) and agent in _ARCHIVABLE


def set_archive(agent: str, enabled: bool) -> Dict[str, bool]:
    """Toggle the archive opt-in for one agent. Returns the full flag map."""
    flags = _load_flags()
    flags[agent] = bool(enabled)
    _save_flags(flags)
    return flags


def describe_agents(available: Optional[list] = None) -> Dict[str, Any]:
    """Per-agent retention info + the user's archive opt-in + detected overrides.

    ``available`` (from main._list_available_agents) limits the output to agents
    actually present on this machine; omitted → describe all known agents."""
    flags = _load_flags()
    claude_actual = _read_claude_cleanup_days()
    out: Dict[str, Any] = {}
    names = available if available is not None else list(_RETENTION.keys())
    for agent in names:
        meta = _RETENTION.get(agent, {
            "label": agent, "default_days": None, "configurable": False,
            "settings_hint": None, "note": "Unknown agent.",
        })
        effective = meta.get("default_days")
        detected_override = None
        if agent == "claude" and claude_actual is not None:
            detected_override = claude_actual
            effective = claude_actual
        out[agent] = {
            **meta,
            "effective_days": effective,
            "detected_override": detected_override,
            "archivable": agent in _ARCHIVABLE,
            "archive_enabled": bool(flags.get(agent, False)),
        }
    return out
