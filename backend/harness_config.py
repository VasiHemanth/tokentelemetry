"""TokenTelemetry config: aliases + hidden projects + budgets.

Lives at the resolved data dir (default ~/.tokentelemetry/; see tt_paths). Files:
  - aliases.json   {"/old/path": "/new/path", ...}   one-way, no chains
  - hidden.json    ["/path", ...]                    projects excluded from dashboard
  - budgets.json   {"budgets": [ {...}, ... ]}        observational spend/token budgets
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
import uuid
from pathlib import Path
from typing import Any, Dict, List, Set

from tt_paths import data_dir

# Resolved once at import. The data dir is an install-time setting (exported via
# TOKENTELEMETRY_DATA_DIR / TOKENTELEMETRY_HOME before the backend launches), so
# reading it once here is correct; see tt_paths.data_dir for the precedence rules.
HARNESS_DIR = data_dir()
ALIASES_FILE = HARNESS_DIR / "aliases.json"
HIDDEN_FILE = HARNESS_DIR / "hidden.json"
BUDGETS_FILE = HARNESS_DIR / "budgets.json"
PREFERENCES_FILE = HARNESS_DIR / "preferences.json"
VERSION_FILE = HARNESS_DIR / "VERSION"
SCHEMA_VERSION = 1

# App preferences with their defaults. Only keys listed here are ever read from
# or written to disk, so a stale/garbage file can't inject unknown settings.
#   update_check: whether the dashboard may fetch the latest version + release
#                 notes from GitHub.
#   telemetry:    whether the app sends anonymous, content-free feature-usage
#                 events (see telemetry.py + docs/design/product-telemetry.md).
#                 ON by default (opt-out); DO_NOT_TRACK / TT_NO_TELEMETRY / CI
#                 force it off regardless.
DEFAULT_PREFERENCES: Dict[str, Any] = {
    "update_check": True,
    "telemetry": True,
    "telemetry_notice_ack": False,
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


# ---------------------------------------------------------------------------
# Budgets
#
# A budget is OBSERVATIONAL — TokenTelemetry reads logs after the fact and
# cannot block a running agent, so a budget never caps spend; it only powers
# threshold alerts and (later) burn-rate forecasts.
#
# Scope is a *filter object*, not a single enum. A budget applies to the
# sessions matching ALL present filter keys, so one mechanism covers every
# combination the UI needs:
#   {}                          -> global
#   {"project": "/p"}           -> whole project, all agents
#   {"project": "/p", "agent":"claude"} -> just Claude on that project
#   {"agent": "claude"}         -> Claude everywhere
#   {"model": "..."}            -> one model
#
# Stored shape (budgets.json):
#   {"budgets": [
#     {"id", "filters": {project?,agent?,model?}, "period", "limit_type",
#      "limit_value", "thresholds": [..], "enabled"}
#   ]}
# ---------------------------------------------------------------------------

BUDGET_PERIODS = ("monthly", "weekly", "rolling_30d")
BUDGET_LIMIT_TYPES = ("usd", "tokens")
BUDGET_FILTER_KEYS = ("project", "agent", "model")
_DEFAULT_THRESHOLDS = [0.8, 1.0]


def _sanitize_budget(raw: Any) -> Dict[str, Any] | None:
    """Coerce one raw entry into a valid budget dict, or None if unsalvageable.

    Lenient on storage quirks (missing id, stray keys) but strict on the
    fields that drive computation (period, limit_type, positive limit_value).
    """
    if not isinstance(raw, dict):
        return None

    period = raw.get("period")
    if period not in BUDGET_PERIODS:
        return None

    limit_type = raw.get("limit_type")
    if limit_type not in BUDGET_LIMIT_TYPES:
        return None

    try:
        limit_value = float(raw.get("limit_value"))
    except (TypeError, ValueError):
        return None
    if limit_value <= 0:
        return None

    # Filters: keep only known keys with non-empty string values.
    raw_filters = raw.get("filters") or {}
    filters: Dict[str, str] = {}
    if isinstance(raw_filters, dict):
        for k in BUDGET_FILTER_KEYS:
            v = raw_filters.get(k)
            if isinstance(v, str) and v:
                filters[k] = v

    # Thresholds: positive fractions, sorted, de-duped; fall back to default.
    raw_thresholds = raw.get("thresholds")
    thresholds: List[float] = []
    if isinstance(raw_thresholds, list):
        for t in raw_thresholds:
            try:
                tf = round(float(t), 4)
            except (TypeError, ValueError):
                continue
            if 0 < tf <= 2 and tf not in thresholds:
                thresholds.append(tf)
    thresholds = sorted(thresholds) or list(_DEFAULT_THRESHOLDS)

    bid = raw.get("id")
    if not isinstance(bid, str) or not bid:
        bid = uuid.uuid4().hex

    enabled = raw.get("enabled")
    enabled = True if enabled is None else bool(enabled)

    return {
        "id": bid,
        "filters": filters,
        "period": period,
        "limit_type": limit_type,
        "limit_value": limit_value,
        "thresholds": thresholds,
        "enabled": enabled,
    }


def load_budgets() -> List[Dict[str, Any]]:
    """Return the list of stored budgets. Invalid entries are dropped silently."""
    if not BUDGETS_FILE.exists():
        return []
    try:
        with open(BUDGETS_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return []
    items = raw.get("budgets") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return []
    out: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()
    for entry in items:
        b = _sanitize_budget(entry)
        if not b:
            continue
        if b["id"] in seen_ids:
            b["id"] = uuid.uuid4().hex
        seen_ids.add(b["id"])
        out.append(b)
    return out


def save_budgets(budgets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Validate + overwrite budgets.json. Returns the cleaned list that was saved."""
    cleaned: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()
    for entry in budgets or []:
        b = _sanitize_budget(entry)
        if not b:
            continue
        if b["id"] in seen_ids:
            b["id"] = uuid.uuid4().hex
        seen_ids.add(b["id"])
        cleaned.append(b)
    _atomic_write_json(BUDGETS_FILE, {"budgets": cleaned})
    return cleaned
