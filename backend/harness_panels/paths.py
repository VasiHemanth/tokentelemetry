"""Harness directory resolution, mirroring main.py's scanner contracts.

Panels must look in exactly the same places the session scan does, or an agent
whose data dir has been relocated shows sessions with no panel behind them —
which reads as a bug rather than as a relocated install.

These constants are duplicated rather than imported from main.py because main.py
imports this package; importing back would be circular. Any change to a
relocation env var in main.py belongs here too.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List

HOME = Path.home()


def _env_path(*names: str) -> Path | None:
    for n in names:
        v = os.environ.get(n)
        if v:
            return Path(v).expanduser()
    return None


def _xdg_data() -> Path:
    return _env_path("XDG_DATA_HOME") or (HOME / ".local" / "share")


CLAUDE_DIR = HOME / ".claude"
CLAUDE_JSON = HOME / ".claude.json"
CODEX_DIR = HOME / ".codex"
COPILOT_DIR = HOME / ".copilot"
GROK_DIR = _env_path("GROK_HOME") or (HOME / ".grok")
GEMINI_DIR = HOME / ".gemini"
QWEN_DIR = HOME / ".qwen"
VIBE_DIR = HOME / ".vibe"
CURSOR_DIR = HOME / ".cursor"
PI_DIR = HOME / ".pi" / "agent"
DSH_DIR = _env_path("DSH_HOME") or (HOME / ".dsh")
CLINE_DIR = _env_path("TT_CLINE_DIR") or (HOME / ".cline")
# Same contract as main.py's QODER_DIR / QODER_IDE_DIR. Qoder keeps its CLI
# transcripts under ~/.qoder and a separate Electron store in Application
# Support; the panel spans both because neither alone is the agent's footprint.
QODER_DIR = _env_path("QODER_HOME") or (HOME / ".qoder")
QODER_IDE_DIR = (_env_path("QODER_IDE_HOME")
                 or (HOME / "Library" / "Application Support" / "com.qoder.app.stable"))
# Same contract as main.py's HERMES_DIR.
HERMES_DIR = _env_path("HERMES_HOME") or (HOME / ".hermes")

MUSE_SESSIONS_DIR = _env_path("TT_MUSE_SESSIONS_DIR") or (_xdg_data() / "muse" / "sessions")
MUSE_DIR = MUSE_SESSIONS_DIR.parent

PRIME_SESSIONS_DIR = (
    _env_path("TT_PRIME_SESSIONS_DIR", "PRIME_AGENT_SESSION_DIR")
    or (HOME / ".prime" / "agent" / "sessions")
)
PRIME_DIR = PRIME_SESSIONS_DIR.parent

# Antigravity ships three surfaces sharing one layout; `antigravity-backup` is
# deliberately excluded because counting it duplicates every conversation.
ANTIGRAVITY_SURFACES = [
    (GEMINI_DIR / "antigravity-cli", "cli"),
    (GEMINI_DIR / "antigravity-ide", "ide"),
    (GEMINI_DIR / "antigravity", "app"),
]


def opencode_data_dir() -> Path:
    """OpenCode's data dir, probing the same candidates main.py does.

    OpenCode honours $OPENCODE_DATA_DIR and $XDG_DATA_HOME with a per-OS
    default, so a single hardcoded path silently misses relocated installs.
    """
    candidates: List[Path] = []
    env = _env_path("OPENCODE_DATA_DIR")
    if env:
        candidates.append(env)
    candidates.append(_xdg_data() / "opencode")
    if sys.platform == "darwin":
        candidates.append(HOME / "Library" / "Application Support" / "opencode")
    candidates.append(HOME / ".local" / "share" / "opencode")
    for c in candidates:
        try:
            if c.is_dir():
                return c
        except OSError:
            continue
    return HOME / ".local" / "share" / "opencode"


def smallcode_roots() -> List[Path]:
    """Project directories that contain a `.smallcode/traces` folder.

    SmallCode is project-local, not home-dir based, so there is nothing to scan
    without knowing which repositories to look in. `TT_SMALLCODE_ROOTS` is the
    same contract main.py uses, split on both os.pathsep and comma.
    """
    raw = os.environ.get("TT_SMALLCODE_ROOTS") or ""
    parts: List[str] = []
    for chunk in raw.split(os.pathsep):
        parts.extend(chunk.split(","))
    out: List[Path] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        root = Path(p).expanduser()
        if (root / ".smallcode" / "traces").is_dir():
            out.append(root)
    return out
