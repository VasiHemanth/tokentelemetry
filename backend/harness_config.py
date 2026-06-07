"""TokenTelemetry config: aliases + hidden projects.

Lives at ~/.tokentelemetry/. Three files:
  - aliases.json   {"/old/path": "/new/path", ...}   one-way, no chains
  - hidden.json    ["/path", ...]                    projects excluded from dashboard
  - VERSION        single integer for future migrations

Design rules:
  - Dir is created lazily on first write, never on read.
  - Writes are atomic (tmp + rename). A crash mid-write won't corrupt config.
  - Reads never raise; missing/malformed files return empty defaults.
  - Aliases are applied at read time only. Log files are never modified.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Set

HARNESS_DIR = Path.home() / ".tokentelemetry"
ALIASES_FILE = HARNESS_DIR / "aliases.json"
HIDDEN_FILE = HARNESS_DIR / "hidden.json"
PREFERENCES_FILE = HARNESS_DIR / "preferences.json"
VERSION_FILE = HARNESS_DIR / "VERSION"
SCHEMA_VERSION = 1

# App preferences with their defaults. Only keys listed here are ever read from
# or written to disk, so a stale/garbage file can't inject unknown settings.
#   update_check: whether the dashboard may fetch the latest version + release
#                 notes from GitHub (the only outbound call the app makes).
DEFAULT_PREFERENCES: Dict[str, Any] = {
    "update_check": True,
}


def _ensure_dir() -> None:
    HARNESS_DIR.mkdir(parents=True, exist_ok=True)
    if not VERSION_FILE.exists():
        VERSION_FILE.write_text(str(SCHEMA_VERSION))


def _atomic_write_json(path: Path, data) -> None:
    """Write JSON atomically. Crash during write can't corrupt the existing file."""
    _ensure_dir()
    fd, tmp = tempfile.mkstemp(dir=str(HARNESS_DIR), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        try: os.unlink(tmp)
        except Exception: pass
        raise


def load_aliases() -> Dict[str, str]:
    """Return old-path -> new-path map. One-way, no chains resolved.

    Invalid entries (non-string, self-referencing, chained) are skipped silently.
    """
    if not ALIASES_FILE.exists():
        return {}
    try:
        with open(ALIASES_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, str] = {}
    for k, v in raw.items():
        if not isinstance(k, str) or not isinstance(v, str): continue
        if not k or not v or k == v: continue
        # Reject chains: if v is itself a key, this alias is ambiguous.
        if v in raw: continue
        out[k] = v
    return out


def apply_alias(path: str, aliases: Dict[str, str]) -> str:
    """One-way, non-recursive lookup. Returns path unchanged if not aliased."""
    return aliases.get(path, path)


def load_hidden() -> Set[str]:
    """Return the set of project paths the user has chosen to hide."""
    if not HIDDEN_FILE.exists():
        return set()
    try:
        with open(HIDDEN_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return set()
    if not isinstance(raw, list):
        return set()
    return {p for p in raw if isinstance(p, str) and p}


def save_hidden(paths: Set[str]) -> None:
    _atomic_write_json(HIDDEN_FILE, sorted(paths))


def hide_project(path: str) -> Set[str]:
    current = load_hidden()
    current.add(path)
    save_hidden(current)
    return current


def unhide_project(path: str) -> Set[str]:
    current = load_hidden()
    current.discard(path)
    save_hidden(current)
    return current


def load_preferences() -> Dict[str, Any]:
    """Return app preferences, defaults filled in for anything missing/invalid.

    Never raises: a missing or malformed file yields the defaults. Unknown keys
    on disk are ignored so only recognised preferences ever take effect."""
    prefs = dict(DEFAULT_PREFERENCES)
    if not PREFERENCES_FILE.exists():
        return prefs
    try:
        with open(PREFERENCES_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return prefs
    if not isinstance(raw, dict):
        return prefs
    for key, default in DEFAULT_PREFERENCES.items():
        if key in raw and isinstance(raw[key], type(default)):
            prefs[key] = raw[key]
    return prefs


def save_preferences(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Merge `updates` (known keys only) over current prefs and persist.

    Returns the full preferences dict after the merge. Values whose type doesn't
    match the default are skipped, so a bad payload can't corrupt a setting."""
    prefs = load_preferences()
    for key, default in DEFAULT_PREFERENCES.items():
        if key in updates and isinstance(updates[key], type(default)):
            prefs[key] = updates[key]
    _atomic_write_json(PREFERENCES_FILE, prefs)
    return prefs


def list_aliases() -> Dict[str, str]:
    return load_aliases()


def save_aliases(aliases: Dict[str, str]) -> None:
    """Overwrite the alias file. Caller is responsible for validation."""
    _atomic_write_json(ALIASES_FILE, aliases)
