#!/usr/bin/env python3
"""PreToolUse hook: block edits/writes to secret and data files.

Why: the repo root carries a tracked `.env` (real credentials) and the app
writes SQLite databases (`*.db` — token telemetry, notifications). An
accidental Edit/Write to either is high-blast-radius: leaking secrets into a
commit, or corrupting a user's local telemetry store. Reads are fine; this
only guards mutations.

Fires on the Write / Edit / MultiEdit / NotebookEdit tools (wired via
.claude/settings.json). Reads the tool invocation as JSON on stdin (Claude
Code's hook contract) and communicates block decisions via JSON on stdout,
exit 0 always.

Allows the common-sense exceptions: `.env.example` / `.env.sample` /
`.env.template` are meant to be edited (they're the committed templates).

Bypass for a deliberate edit: re-run with `--no-hooks`.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Optional


# Basename suffixes that are safe to edit even though they start with `.env`.
ENV_TEMPLATE_SUFFIXES = (".example", ".sample", ".template", ".dist")

# Database / data-store extensions we never want a model edit to touch.
DB_EXTENSIONS = (".db", ".sqlite", ".sqlite3", ".db-wal", ".db-shm")


def _allow() -> None:
    """Allow the tool call. Hook contract: silent + exit 0."""
    sys.exit(0)


def _deny(reason: str) -> None:
    """Deny the tool call. Hook contract: structured JSON on stdout + exit 0."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(payload))
    sys.exit(0)


def _classify(path: str) -> Optional[str]:
    """Return a human-readable reason string if `path` is protected, else None."""
    if not path:
        return None
    base = os.path.basename(path).lower()

    # .env and .env.<env> (.env.local, .env.production, …) — but not templates.
    if base == ".env" or base.startswith(".env."):
        if any(base.endswith(suffix) for suffix in ENV_TEMPLATE_SUFFIXES):
            return None
        return (
            f"`{os.path.basename(path)}` holds environment secrets and is "
            "protected from automated edits — a stray change risks leaking "
            "credentials into a commit. Edit it by hand, or copy from "
            "`.env.example`. To override for this call, re-run with `--no-hooks`."
        )

    # SQLite / data stores.
    if any(base.endswith(ext) for ext in DB_EXTENSIONS):
        return (
            f"`{os.path.basename(path)}` is a local database file — editing it "
            "as text will corrupt the store (token telemetry / notifications). "
            "Change it through the app or a migration, not a direct write. To "
            "override for this call, re-run with `--no-hooks`."
        )

    return None


def _paths_from_input(tool_input: dict) -> list[str]:
    """Extract the target file path(s) from any of the edit/write tools."""
    paths: list[str] = []
    for key in ("file_path", "notebook_path", "path"):
        val = tool_input.get(key)
        if isinstance(val, str) and val:
            paths.append(val)
    return paths


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        _allow()
        return

    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        _allow()
        return

    for path in _paths_from_input(tool_input):
        reason = _classify(path)
        if reason:
            _deny(reason)
            return

    _allow()


if __name__ == "__main__":
    main()
