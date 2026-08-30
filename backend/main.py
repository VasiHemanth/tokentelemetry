from fastapi import FastAPI, Body, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import re
import hmac
import json
import yaml
import sqlite3
from pathlib import Path
from typing import List, Optional, Dict, Any, Set, Iterable, Tuple
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta, time as _dtime
from urllib.parse import unquote, quote

from harness_config import (
    load_aliases, apply_alias,
    load_hidden, hide_project, unhide_project,
    list_aliases, save_aliases,
    load_budgets, save_budgets,
    load_preferences, save_preferences,
)
import notifications as notif
from tt_paths import canonical_project, data_dir
import scan_cache
import harness_panels
import codex_goals
import hermes_telemetry as _ht
import hashlib

def _aware(dt):
    """Ensure datetime is timezone-aware UTC. Naive inputs are assumed to be UTC."""
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def _now():
    return datetime.now(timezone.utc)

def _file_mtime_utc(path) -> datetime:
    """File mtime as UTC datetime, falling back to _now() only if the file
    is genuinely missing. Used as a historical timestamp fallback so
    sessions with bad source-data timestamps don't pile onto today.
    """
    try:
        return datetime.fromtimestamp(Path(path).stat().st_mtime, tz=timezone.utc)
    except Exception:
        return _now()

def _load_copilot_cli_events(events_file: Path) -> List[dict]:
    """Load a GitHub Copilot CLI session's append-only event log (#36)."""
    rows: List[dict] = []
    try:
        with open(events_file, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except OSError:
        pass
    return rows

def _parse_copilot_iso(ts) -> Optional[datetime]:
    """Copilot CLI timestamps are ISO-8601 with a trailing Z (e.g.
    '2026-06-04T11:45:07.548Z'). Returns None for anything unparseable."""
    if not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None

def _copilot_cli_tokens_from_metrics(metrics) -> Optional[dict]:
    """Best-effort precise token totals from a closed session's
    `session.shutdown.modelMetrics`. The exact shape varies by Copilot
    version, so we defensively sum any recognizable input/output/cache token
    counts found anywhere in the structure. Returns None when nothing usable
    is present (caller then falls back to the per-message estimate).

    Copilot's `usage.inputTokens` is GROSS: it already includes
    cacheReadTokens + cacheWriteTokens (verified against tokenDetails, whose
    net input.tokenCount + cache_read + cache_write sums exactly to
    inputTokens). So after collection, cache traffic is subtracted back out
    of input — otherwise it's billed twice across the input and cached
    buckets. The subtraction is guarded (only when input covers it) so an
    unknown future shape that reports net input can't go negative."""
    if not isinstance(metrics, (dict, list)):
        return None
    tot = {"input": 0, "output": 0, "cached": 0, "cache_creation": 0}
    found = False

    def grab(obj):
        nonlocal found
        if isinstance(obj, dict):
            for k, v in obj.items():
                kl = str(k).lower()
                if isinstance(v, (int, float)) and not isinstance(v, bool) and "token" in kl:
                    if "reasoning" in kl:
                        # Folded into outputTokens already; counting it (the
                        # old "in" match caught reasonINg) double-bills it.
                        continue
                    if "cache" in kl:
                        if "write" in kl or "creation" in kl:
                            tot["cache_creation"] += int(v); found = True
                        else:
                            tot["cached"] += int(v); found = True
                    elif "out" in kl or "completion" in kl or "output" in kl:
                        tot["output"] += int(v); found = True
                    elif "in" in kl or "prompt" in kl:
                        tot["input"] += int(v); found = True
                else:
                    grab(v)
        elif isinstance(obj, list):
            for x in obj:
                grab(x)

    grab(metrics)
    if not found:
        return None
    cache_total = tot["cached"] + tot["cache_creation"]
    if cache_total and tot["input"] >= cache_total:
        tot["input"] -= cache_total
    return tot

def _antigravity_surface_map() -> Dict[str, str]:
    """Map Antigravity session id → surface (cli / ide / app) from the brain dirs,
    so sessions discovered via the gemini-logs path can also be labelled. First
    match wins if an id somehow appears under more than one surface."""
    m: Dict[str, str] = {}
    for _bd, _src in ANTIGRAVITY_BRAIN_SOURCES:
        if not _bd.exists():
            continue
        try:
            for p in _bd.iterdir():
                if p.is_dir():
                    m.setdefault(p.name, _src)
        except OSError:
            continue
    return m

def _pid_alive(pid: int) -> bool:
    """Cross-platform process liveness probe.

    On POSIX, os.kill(pid, 0) is a cheap no-op signal that raises if the
    process is gone. On Windows, signal 0 is not honored — os.kill calls
    TerminateProcess and would actually kill the target — so we use
    OpenProcess via ctypes (PROCESS_QUERY_LIMITED_INFORMATION = 0x1000).
    """
    if os.name == "nt":
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            return False
    try:
        os.kill(int(pid), 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False

app = FastAPI(title="TokenTelemetry API")

# Enable CORS for the Next.js frontend.
#
# We use a regex over an explicit allowlist so the frontend can pick any local
# port (the user can pass --port to start.sh / bin/cli.js). Loopback is always
# allowed; additional hosts (IPs / hostnames) can be opted in for remote access
# via the TT_ALLOWED_ORIGINS env var (comma-separated) — bin/cli.js wires it up
# from --allowed-origins. Default behavior is unchanged: loopback-only.
def _cors_origin_regex() -> str:
    hosts = ["localhost", r"127\.0\.0\.1"]
    for h in os.environ.get("TT_ALLOWED_ORIGINS", "").split(","):
        h = h.strip()
        if h:
            hosts.append(re.escape(h))
    return r"^https?://(" + "|".join(hosts) + r"):\d+$"

# --- Remote-access auth gate -------------------------------------------------
# When TT_AUTH_TOKEN is set (bin/cli.js sets it automatically for a non-loopback
# --host, unless --insecure-no-auth), every *remote* request must present the
# token as `Authorization: Bearer <token>` or a `?token=<token>` query param.
# Loopback requests are always exempt, so the operator's own browser on the
# server — and the default loopback-only setup — is unaffected. With no token
# set the gate is a no-op: default behavior is byte-for-byte unchanged.
#
# IMPORTANT: this is registered BEFORE CORSMiddleware so CORS stays the
# *outermost* layer (Starlette wraps the most-recently-added middleware on the
# outside). That lets CORS answer OPTIONS preflight directly — browsers send no
# Authorization on preflight — and decorate our 401 with the Access-Control
# headers the browser needs to actually read the response instead of surfacing
# an opaque CORS error.
from starlette.middleware.base import BaseHTTPMiddleware

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _is_loopback(host: Optional[str]) -> bool:
    """True only for loopback source addresses. An unknown client is treated as
    remote (fail safe) so a missing peer can never bypass the gate."""
    if not host:
        return False
    h = host.strip("[]")  # normalise bracketed IPv6 literals
    if h in _LOOPBACK_HOSTS:
        return True
    # IPv4-mapped IPv6 form, e.g. ::ffff:127.0.0.1
    if h.startswith("::ffff:") and h[len("::ffff:"):] in _LOOPBACK_HOSTS:
        return True
    return False


def _presented_token(request: Request) -> str:
    """Pull the caller's token from the Authorization header, falling back to a
    `?token=` query param so browser-native resource loads (artifact <img>/<a>,
    which can't set headers) can authenticate too."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[len("Bearer "):].strip()
    return (request.query_params.get("token") or "").strip()


class RemoteAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        token = os.environ.get("TT_AUTH_TOKEN", "").strip()
        if not token:
            return await call_next(request)  # gate disabled (local default)
        client = request.client.host if request.client else None
        if _is_loopback(client):
            return await call_next(request)  # local is always exempt
        presented = _presented_token(request)
        if presented and hmac.compare_digest(presented, token):
            return await call_next(request)
        # Never echo the expected token; just say what's needed.
        return JSONResponse(
            status_code=401,
            content={"detail": "Remote access requires an access token.", "auth": "token"},
        )


app.add_middleware(RemoteAuthMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=_cors_origin_regex(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import sys

HOME = Path.home()

# Platform-specific base directories for VS Code and Cursor
if sys.platform == "darwin":  # macOS
    VSCODE_BASE = HOME / "Library/Application Support/Code"
    CURSOR_BASE = HOME / "Library/Application Support/Cursor"
elif sys.platform == "win32":  # Windows
    APPDATA = Path(os.environ.get("APPDATA", HOME / "AppData/Roaming"))
    VSCODE_BASE = APPDATA / "Code"
    CURSOR_BASE = APPDATA / "Cursor"
else:  # Linux and others
    CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config"))
    VSCODE_BASE = CONFIG / "Code"
    CURSOR_BASE = CONFIG / "Cursor"

# Common agent directories (usually in home)
CLAUDE_DIR = HOME / ".claude"
CODEX_DIR = HOME / ".codex"
GEMINI_DIR = HOME / ".gemini"
QWEN_DIR = HOME / ".qwen"
VIBE_DIR = HOME / ".vibe"
CURSOR_DIR = HOME / ".cursor"
OLLAMA_DIR = HOME / ".ollama"
# Pi Coding Agent (earendil-works) — stores one JSONL per session under
# ~/.pi/agent/sessions/<encoded-cwd>/<timestamp>_<uuid>.jsonl. Each file opens
# with a {"type":"session", cwd, timestamp} header, then message events whose
# assistant turns carry per-request usage + cost + provider/model. See
# _scan_pi_sessions.
PI_DIR = HOME / ".pi" / "agent"
PI_SESSIONS_DIR = PI_DIR / "sessions"
# DeepSeek Harness (DSH, npm @deepseek-ai/dsh, binary `dsh`) — plugin-based
# multi-provider coding agent CLI from DeepSeek AI. Sessions live one zstd-
# compressed JSONL per session under ~/.dsh/sessions/<slugged-cwd>/<id>/
# session.jsonl.zstd; each file's own header carries `cwd`, so we don't need
# to reverse DSH's lossy path-slugging to resolve the project. See
# _scan_dsh_sessions.
DSH_DIR = Path(os.environ.get("DSH_HOME") or (HOME / ".dsh")).expanduser()
DSH_SESSIONS_DIR = DSH_DIR / "sessions"
# Plugin-lifecycle sidecar. DSH's persisted session log has a CLOSED vocabulary
# (44 known event types; the read path rejects anything else), and Cordis emits
# component lifecycle transitions only on its in-memory `internal/status` bus.
# So a load/unload/failure is unobservable after the fact unless something
# subscribes live. integrations/dsh-lifecycle-plugin/ is a TT-authored DSH
# plugin that does exactly that and appends here — same push-based shape as
# backend/omnigent_policy.py. Absent file = plugin not installed, which is the
# normal case and must never be an error.
DSH_LIFECYCLE_FILE = data_dir() / "dsh_lifecycle.jsonl"
# Qoder (Alibaba) ships two surfaces over ONE set of sessions. The CLI writes
# Claude-Code-shaped JSONL under ~/.qoder/projects/<slugged-cwd>/<uuid>.jsonl;
# the Electron IDE keeps ~/Library/Application Support/com.qoder.app.stable/
# main.sqlite, whose chat_session_messages rows are marked source="sdk-projection"
# and carry the SAME message uuids. The DB is therefore a mirror, not a second
# store — scanning both would double-count every session. We read the JSONL and
# use the DB only to enrich (it has a human-readable title the JSONL lacks).
# Qoder has no relocation env var of its own (its launcher reads only HOME);
# QODER_HOME exists so tests can point the scan at a fixture tree.
QODER_DIR = Path(os.environ.get("QODER_HOME") or (HOME / ".qoder")).expanduser()
QODER_PROJECTS_DIR = QODER_DIR / "projects"
QODER_IDE_DIR = Path(
    os.environ.get("QODER_IDE_HOME")
    or (HOME / "Library/Application Support/com.qoder.app.stable")
).expanduser()
HF_DIR = HOME / ".cache/huggingface"
def _opencode_dbs_in(d: Path) -> List[Path]:
    """DB files OpenCode may have written inside data dir ``d``, canonical first.

    The filename is NOT fixed either: OpenCode picks it from the *release
    channel* it was built for. `latest`/`beta` (and builds with
    `OPENCODE_DISABLE_CHANNEL_DB`) get plain ``opencode.db``; every other
    channel gets ``opencode-<channel>.db``, e.g. the ``opencode-stable.db``
    a Nix install produces. Globbing is the only way to cover that — the
    channel string is arbitrary, so there's no finite list to hardcode.
    ``opencode*.db`` deliberately does not match the ``-wal``/``-shm``
    sidecars, which don't end in ``.db``.
    """
    canonical = d / "opencode.db"
    out = [canonical]
    try:
        out.extend(sorted(p for p in d.glob("opencode*.db") if p != canonical))
    except OSError:
        pass
    return out


def _opencode_db_candidates() -> List[Path]:
    """OpenCode SQLite DB locations to probe, highest-priority first.

    OpenCode does NOT use one fixed path: it resolves a data dir honoring
    ``$OPENCODE_DATA_DIR`` and ``$XDG_DATA_HOME`` with a per-OS default, then
    names the file after its release channel. We used to look only at
    ``~/.local/share/opencode/opencode.db`` and so silently missed relocated
    installs, non-Linux installs, and every non-`latest` channel — the scan is
    gated on ``.exists()`` inside a bare ``try/except``, so a wrong path means
    the whole agent vanishes with no error (discussion #170). Probe every place
    the agent could have written. Extra non-existent candidates are harmless.
    """
    dirs: List[Path] = []
    env = os.environ.get("OPENCODE_DATA_DIR")
    if env:
        dirs.append(Path(env).expanduser())
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        dirs.append(Path(xdg).expanduser() / "opencode")
    if sys.platform == "win32":
        for var in ("APPDATA", "LOCALAPPDATA"):
            base = os.environ.get(var)
            if base:
                dirs.append(Path(base) / "opencode")
    # Standard XDG data dir — the confirmed default on BOTH Linux and macOS
    # (OpenCode does not use ~/Library/Application Support, verified on 1.15.13).
    dirs.append(HOME / ".local/share/opencode")
    # macOS env-paths-style location, in case a build ever used it.
    if sys.platform == "darwin":
        dirs.append(HOME / "Library/Application Support/opencode")
    seen: set = set()
    out: List[Path] = []
    for d in dirs:
        for p in _opencode_dbs_in(d):
            if p not in seen:
                seen.add(p)
                out.append(p)
    return out


def _opencode_db_path() -> Path:
    """First existing OpenCode DB among the candidates, else the canonical XDG
    default (so a not-yet-created DB still has a stable path to display)."""
    for p in _opencode_db_candidates():
        try:
            if p.exists():
                return p
        except OSError:
            continue
    return HOME / ".local/share/opencode/opencode.db"


OPENCODE_DB = _opencode_db_path()


def _opencode_dbs() -> List[Path]:
    """Every OpenCode DB to actually read, primary (``OPENCODE_DB``) first.

    A user who has switched release channels ends up with several DBs side by
    side — e.g. an old ``opencode.db`` plus the live ``opencode-stable.db``.
    Reading only the first would show stale sessions and hide current ones, so
    scan them all. Derived from ``OPENCODE_DB.parent`` rather than re-probing
    every candidate dir, which keeps a monkeypatched ``OPENCODE_DB`` fully in
    control of what the scan sees.
    """
    out: List[Path] = []
    seen: set = set()
    for p in [OPENCODE_DB, *_opencode_dbs_in(OPENCODE_DB.parent)]:
        try:
            if p in seen or not p.exists():
                continue
        except OSError:
            continue
        seen.add(p)
        out.append(p)
    return out


def _opencode_db_for_session(session_id: str) -> Optional[Path]:
    """The channel DB that actually holds ``session_id``, or None.

    Detail endpoints can't assume the primary DB: with several channel DBs
    present, a session listed from ``opencode-stable.db`` would 404 if we only
    ever queried ``opencode.db``.
    """
    for db in _opencode_dbs():
        try:
            conn = sqlite3.connect(_sqlite_ro_uri(db), uri=True, timeout=1.0)
            try:
                if conn.execute("SELECT 1 FROM session WHERE id=?",
                                (session_id,)).fetchone():
                    return db
            finally:
                conn.close()
        except Exception:
            continue
    return None
# Hermes installs to ~/.hermes by default, but the agent honors HERMES_HOME for
# users who relocate their data dir (shared hosts, containerized setups, etc.).
# Mirror that contract so we read from wherever the agent actually writes.
HERMES_DIR = Path(os.environ.get("HERMES_HOME") or (HOME / ".hermes")).expanduser()
HERMES_DB = HERMES_DIR / "state.db"
HERMES_PROFILES_DIR = HERMES_DIR / "profiles"

# Grok Build (xAI) — the TUI/agent this conversation is running in.
# Stores rich per-session data under ~/.grok/sessions/<encoded-cwd>/<uuid>/
GROK_DIR = HOME / ".grok"
GROK_SESSIONS_DIR = GROK_DIR / "sessions"
# Per-turn billed usage (prompt / cached / completion) lives here, not in the
# session dir. Session files only expose a context-window footprint.
GROK_UNIFIED_LOG = GROK_DIR / "logs" / "unified.jsonl"

# Grok Build session file names (per <cwd-uuid> directory)
GROK_SUMMARY = "summary.json"
GROK_EVENTS = "events.jsonl"
GROK_UPDATES = "updates.jsonl"
GROK_CHAT_HISTORY = "chat_history.jsonl"
GROK_PLAN_MODE = "plan_mode.json"
GROK_SIGNALS = "signals.json"

# Specialized storage paths
VSCODE_STORAGE = VSCODE_BASE / "User/workspaceStorage"
CURSOR_STORAGE = CURSOR_BASE / "User/workspaceStorage"
# GitHub Copilot CLI / agent writes an append-only event log per session here,
# separate from the VS Code Copilot chat store above (#36).
COPILOT_CLI_DIR = HOME / ".copilot" / "session-state"
ANTIGRAVITY_BRAIN_DIR = GEMINI_DIR / "antigravity" / "brain"
# Antigravity ships as an IDE and a CLI, each with its own brain/ store; the bare
# `antigravity/` is the original app store. (dir, surface) so sessions can be
# labelled by where they came from. `antigravity-backup/` is intentionally excluded.
ANTIGRAVITY_BRAIN_SOURCES = [
    (GEMINI_DIR / "antigravity-cli" / "brain", "cli"),
    (GEMINI_DIR / "antigravity-ide" / "brain", "ide"),
    (GEMINI_DIR / "antigravity" / "brain", "app"),
]
ANTIGRAVITY_BRAIN_DIRS = [d for d, _ in ANTIGRAVITY_BRAIN_SOURCES]
# `agy` (the Antigravity CLI) additionally persists each session's full trajectory
# under antigravity-cli/conversations/<uuid>.db (SQLite; newer sessions) or
# <uuid>.pb (protobuf; older), plus a flat prompt log in history.jsonl. The brain/
# scanner above only reads derived markdown, so it falls back to a generic model
# name and a heuristic project. We mine these CLI-only stores for the real model
# display name and the exact project cwd — see _antigravity_cli_meta().
ANTIGRAVITY_CLI_DIR = GEMINI_DIR / "antigravity-cli"
PROJECT_ALIASES_FILE = data_dir() / "aliases.json"

# Cline — two stores. (a) CLI: SQLite sessions.db under ~/.cline/data/db/,
# overridable via TT_CLINE_DIR for relocated data dirs (containers, shared
# hosts). (b) VS Code extension: JSON state under globalStorage, overridable
# via TT_CLINE_VSCODE_DIR.
CLINE_DIR = Path(os.environ.get("TT_CLINE_DIR") or (HOME / ".cline")).expanduser()
CLINE_VSCODE_DIR = Path(
    os.environ.get("TT_CLINE_VSCODE_DIR")
    or (VSCODE_BASE / "User" / "globalStorage" / "saoudrizwan.claude-dev")
).expanduser()

# Meta Muse Code writes date-sharded event logs. Prime Agent writes one JSONL
# conversation tree per session. Both variables are overridable for containers
# and relocated home directories, matching the other scanner contracts.
MUSE_SESSIONS_DIR = Path(os.environ.get("TT_MUSE_SESSIONS_DIR") or (
    Path(os.environ.get("XDG_DATA_HOME")) if os.environ.get("XDG_DATA_HOME") else HOME / ".local/share"
) / "muse" / "sessions").expanduser()
PRIME_SESSIONS_DIR = Path(
    os.environ.get("TT_PRIME_SESSIONS_DIR")
    or os.environ.get("PRIME_AGENT_SESSION_DIR")
    or (HOME / ".prime" / "agent" / "sessions")
).expanduser()


def _split_roots_env(value: Optional[str]) -> List[str]:
    """Split a roots env var on BOTH os.pathsep and comma so it works whether
    the user quotes a single path list or a comma-separated one."""
    if not value:
        return []
    parts: List[str] = []
    for chunk in value.split(os.pathsep):
        for p in chunk.split(","):
            p = p.strip()
            if p:
                parts.append(p)
    return parts


def _usage_number(value: Any) -> int:
    """Return a safe non-negative integer from a log usage field."""
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def _muse_usage(event: Any) -> Optional[Dict[str, int]]:
    """Extract one *actual* Muse model-call usage event.

    Muse emits an adjacent ``record.quantity`` accounting event for the same
    call. Only model-tagged ``usage`` events are additive, so accepting the
    record form would double-count every turn.
    """
    if not isinstance(event, dict) or not event.get("model"):
        return None
    usage = event.get("usage")
    if not isinstance(usage, dict) or "input_tokens" not in usage:
        return None
    return {
        "input": _usage_number(usage.get("input_tokens")),
        "output": _usage_number(usage.get("output_tokens")),
        "cached": _usage_number(usage.get("cached_tokens", usage.get("cache_read_tokens"))),
        "cache_creation": _usage_number(usage.get("cache_write_tokens")),
        "reasoning": _usage_number(usage.get("reasoning_tokens")),
    }


def _muse_log_summary(path: Path) -> Dict[str, Any]:
    """Safely summarize one Muse JSONL file without trusting its contents."""
    result: Dict[str, Any] = {
        "cwd": None, "model": None, "display": None, "timestamp": _file_mtime_utc(path),
        "tokens": {"input": 0, "output": 0, "cached": 0, "cache_creation": 0, "reasoning": 0},
        "children": [], "tools": [],
    }
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(row, dict):
                    continue
                recorded_at = row.get("recorded_at")
                if isinstance(recorded_at, (int, float)) and recorded_at > 0:
                    result["timestamp"] = datetime.fromtimestamp(recorded_at / 1_000_000, tz=timezone.utc)
                payload = row.get("payload")
                event = payload.get("event") if isinstance(payload, dict) else None
                payload_record = payload.get("record") if isinstance(payload, dict) else None
                if isinstance(payload_record, dict):
                    if isinstance(payload_record.get("cwd"), str) and payload_record["cwd"].strip():
                        result["cwd"] = payload_record["cwd"]
                    elif isinstance(payload_record.get("workspace_root"), str) and payload_record["workspace_root"].strip():
                        result["cwd"] = payload_record["workspace_root"]
                    model_id = payload_record.get("model_id")
                    if isinstance(model_id, str) and model_id:
                        result["model"] = model_id
                    effective = payload_record.get("effective")
                    if isinstance(effective, dict) and isinstance(effective.get("model_id"), str) and effective["model_id"]:
                        result["model"] = effective["model_id"]
                if not isinstance(event, dict):
                    continue
                record = event.get("record")
                if isinstance(record, dict):
                    if isinstance(record.get("cwd"), str) and record["cwd"].strip():
                        result["cwd"] = record["cwd"]
                    elif isinstance(record.get("workspace_root"), str) and record["workspace_root"].strip():
                        result["cwd"] = record["workspace_root"]
                    model_id = record.get("model_id")
                    if isinstance(model_id, str) and model_id:
                        result["model"] = model_id
                if isinstance(event.get("model"), str) and event["model"]:
                    result["model"] = event["model"]
                usage = _muse_usage(event)
                if usage:
                    for key, value in usage.items():
                        result["tokens"][key] += value
                child = event.get("child_session_log_path")
                if isinstance(child, str) and child:
                    result["children"].append(child)
                kind = event.get("kind")
                if kind == "user_prompt_display" and isinstance(event.get("text"), str) and not result["display"]:
                    result["display"] = event["text"][:120]
                if kind == "assistant_tool_calls_committed":
                    for call in event.get("tool_calls") or []:
                        if isinstance(call, dict) and isinstance(call.get("name"), str):
                            result["tools"].append(call["name"])
    except OSError:
        pass
    result["tools"] = list(dict.fromkeys(result["tools"]))
    return result


def _scan_muse_sessions() -> List[Dict[str, Any]]:
    """Scan root Muse sessions; delegated children remain attributed to parents."""
    out: List[Dict[str, Any]] = []
    try:
        session_paths = sorted(MUSE_SESSIONS_DIR.glob("*/*/*/*/session.jsonl"))
    except OSError:
        return out
    for path in session_paths:
        summary = _muse_log_summary(path)
        tokens = summary["tokens"]
        total = sum(tokens.values())
        tokens["total"] = total
        tokens["cost"] = calculate_cost(summary["model"], tokens["input"], tokens["output"], tokens["cached"], cache_creation_tokens=tokens["cache_creation"], at=summary["timestamp"])
        subagents = []
        delegated = {"input": 0, "output": 0, "cached": 0, "cache_creation": 0, "reasoning": 0}
        root = path.parent.resolve()
        for rel in dict.fromkeys(summary["children"]):
            try:
                child_path = (path.parent / rel).resolve()
                if not child_path.is_relative_to(root) or not child_path.is_file():
                    continue
            except (OSError, ValueError):
                continue
            child = _muse_log_summary(child_path)
            child_tokens = child["tokens"]
            for key in delegated:
                delegated[key] += child_tokens[key]
            subagents.append({
                "agent_id": child_path.parent.name,
                "agent_type": "muse-subagent",
                "model": child["model"],
                "tokens": {**child_tokens, "total": sum(child_tokens.values())},
                "cost": calculate_cost(child["model"], child_tokens["input"], child_tokens["output"], child_tokens["cached"], cache_creation_tokens=child_tokens["cache_creation"], at=summary["timestamp"]),
            })
        delegated_total = sum(delegated.values())
        delegation = {"supported": True, "tokens_recorded": True, "spawn_count": len(subagents),
                      "subagents": subagents, "delegated_total": delegated_total,
                      "delegated_cost": sum(s["cost"] for s in subagents),
                      "by_type": {"muse-subagent": {"count": len(subagents), "total": delegated_total,
                                                        "cost": sum(s["cost"] for s in subagents)}} if subagents else {}}
        sid = path.parent.name
        out.append({
            "id": sid, "agent": "muse", "project": summary["cwd"] or "unknown",
            "timestamp": summary["timestamp"], "display": summary["display"] or f"Muse Code session {sid[:8]}",
            "tokens": tokens, "model": summary["model"], "mcp_tools": summary["tools"],
            "has_plan": False, "plans": [], "artifacts": [], "cost": tokens["cost"],
            "cost_source": "estimated",
            "delegation": delegation, "muse": {"session_path": str(path)},
        })
    return out


def _muse_trace_events(path: Path) -> List[Dict[str, Any]]:
    """Normalize Muse's event envelope into the shared trace-event contract."""
    events: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try: row = json.loads(line)
                except (json.JSONDecodeError, ValueError): continue
                payload = row.get("payload") if isinstance(row, dict) else None
                event = payload.get("event") if isinstance(payload, dict) else None
                if not isinstance(event, dict): continue
                recorded_at = row.get("recorded_at")
                ts_ms = recorded_at / 1000 if isinstance(recorded_at, (int, float)) else None
                base = {"timestamp": ts_ms, "normalized_timestamp": ts_ms}
                kind = event.get("kind")
                if kind == "user_prompt_display" and isinstance(event.get("text"), str):
                    events.append({"type": "user", "payload": {"content": event["text"]}, **base})
                elif kind == "assistant_message_committed" and isinstance(event.get("text"), str):
                    events.append({"type": "assistant", "payload": {"content": event["text"]}, **base})
                elif kind == "assistant_tool_calls_committed":
                    for call in event.get("tool_calls") or []:
                        if isinstance(call, dict):
                            events.append({"type": "tool_call", "payload": {"tool": call.get("name"),
                                           "args": call.get("arguments") or call.get("input")}, **base})
                elif _muse_usage(event):
                    events.append({"type": "usage", "payload": {"model": event.get("model"),
                                   "usage": _muse_usage(event)}, **base})
    except OSError:
        pass
    return events


def _prime_active_entries(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return the newest leaf's ancestry from Prime's in-file session tree."""
    entries = [r for r in rows if isinstance(r, dict) and isinstance(r.get("id"), str) and r.get("type") != "session"]
    by_id = {r["id"]: r for r in entries}
    parents = {r.get("parentId") for r in entries if isinstance(r.get("parentId"), str)}
    leaves = [r for r in entries if r["id"] not in parents]
    if not leaves:
        return []
    # A resumed tree appends to its selected branch, so its latest leaf is the
    # durable active path. Stable index breaks equal-timestamp ties.
    indexed = {id(r): i for i, r in enumerate(entries)}
    leaf = max(leaves, key=lambda r: (str(r.get("timestamp") or ""), indexed[id(r)]))
    chain: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    current: Optional[Dict[str, Any]] = leaf
    while current and current["id"] not in seen:
        seen.add(current["id"])
        chain.append(current)
        parent_id = current.get("parentId")
        current = by_id.get(parent_id) if isinstance(parent_id, str) else None
    return list(reversed(chain))


def _prime_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(part.get("text") or "") for part in content if isinstance(part, dict) and part.get("type") == "text")
    return ""


def _scan_prime_sessions() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    try:
        paths = sorted(PRIME_SESSIONS_DIR.glob("*.jsonl"))
    except OSError:
        return out
    for path in paths:
        rows: List[Dict[str, Any]] = []
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        row = json.loads(line)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    if isinstance(row, dict):
                        rows.append(row)
        except OSError:
            continue
        header = next((r for r in rows if r.get("type") == "session"), None)
        if not isinstance(header, dict) or not isinstance(header.get("id"), str):
            continue
        active = _prime_active_entries(rows)
        aggregate_by_target = {r.get("targetId"): r.get("aggregateUsage") for r in active
                               if r.get("type") == "child_usage_attributed" and isinstance(r.get("aggregateUsage"), dict)}
        tokens = {"input": 0, "output": 0, "cached": 0, "cache_creation": 0}
        cost = 0.0
        display = None
        model = None
        tools: List[str] = []
        last_ts = _file_mtime_utc(path)
        for row in active:
            ts = row.get("timestamp")
            if isinstance(ts, str):
                try: last_ts = _aware(datetime.fromisoformat(ts.replace("Z", "+00")))
                except ValueError: pass
            message = row.get("message")
            if not isinstance(message, dict):
                continue
            if message.get("role") == "user":
                # The active branch can inherit an earlier prompt. Its newest
                # user message is the most useful project-activity label.
                text = _prime_text(message.get("content"))
                if text:
                    display = text[:120]
            if message.get("role") != "assistant":
                continue
            usage = aggregate_by_target.get(row.get("id"), message.get("usage"))
            if not isinstance(usage, dict):
                continue
            tokens["input"] += _usage_number(usage.get("input"))
            tokens["output"] += _usage_number(usage.get("output"))
            tokens["cached"] += _usage_number(usage.get("cacheRead"))
            tokens["cache_creation"] += _usage_number(usage.get("cacheWrite"))
            usage_cost = usage.get("cost")
            if isinstance(usage_cost, dict):
                try: cost += max(0.0, float(usage_cost.get("total") or 0))
                except (TypeError, ValueError): pass
            if isinstance(message.get("model"), str): model = message["model"]
            for part in message.get("content") or []:
                if isinstance(part, dict) and part.get("type") == "toolCall" and isinstance(part.get("name"), str):
                    tools.append(part["name"])
        tokens["total"] = sum(tokens.values())
        tokens["cost"] = cost
        branches = len([r for r in rows if isinstance(r, dict) and isinstance(r.get("id"), str) and r.get("type") != "session" and r["id"] not in {e.get("parentId") for e in rows if isinstance(e, dict)}])
        out.append({
            "id": header["id"], "agent": "prime", "project": header.get("cwd") if isinstance(header.get("cwd"), str) else "unknown",
            "timestamp": last_ts, "display": display or f"Prime Agent session {header['id'][:8]}",
            "tokens": tokens, "model": model, "mcp_tools": list(dict.fromkeys(tools)),
            "has_plan": False, "plans": [], "artifacts": [], "cost": cost, "cost_source": "reported",
            "prime": {"session_path": str(path), "branch_count": branches},
            "delegation": {"supported": True, "tokens_recorded": True},
        })
    return out


# SmallCode traces are PROJECT-LOCAL (<project>/.smallcode/traces/*.json), not
# under a home dir, so there's no single directory to scan. We discover roots
# from projects already seen from other agents, plus any extra roots the user
# points us at via TT_SMALLCODE_ROOTS (pathsep- or comma-separated).
SMALLCODE_EXTRA_ROOTS: List[str] = _split_roots_env(os.environ.get("TT_SMALLCODE_ROOTS"))


def _sqlite_ro_uri(db_path) -> str:
    """Read-only sqlite URI that works on every OS.

    f"file:{path}" breaks on Windows — backslashes are not URI path
    separators, so sqlite fails to resolve the file and the scanner silently
    skips the agent. Forward-slash the path (no-op on POSIX) and
    percent-encode URI-special characters (spaces, '?', '#'); the drive
    colon stays literal, which sqlite's Windows URI parser expects.
    """
    from urllib.parse import quote
    p = db_path if hasattr(db_path, "as_posix") else Path(db_path)
    return "file:" + quote(p.as_posix(), safe="/:") + "?mode=ro"


def _load_project_aliases() -> Dict[str, str]:
    # Ensure directory exists
    PROJECT_ALIASES_FILE.parent.mkdir(parents=True, exist_ok=True)
    if PROJECT_ALIASES_FILE.exists():
        try:
            with open(PROJECT_ALIASES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception: pass
    return {}

# Sentinel project for Antigravity sessions whose real workspace can't be
# recovered (pure chat/research runs that never entered a project dir). It groups
# such sessions but is NOT a real workspace, so get_projects hides it from the
# Projects view — the sessions still appear in the dashboard and session lists.
ANTIGRAVITY_UNASSIGNED = "Antigravity / unassigned"

def _antigravity_infer_project(text: str) -> str:
    import re
    # Match absolute paths starting with the home directory or common root prefixes
    # This regex is more generic and works for /Users/, /home/, or C:\Users\
    home_prefix = str(HOME).replace("\\", "/")
    # Escape any special regex chars in home_prefix
    escaped_home = re.escape(home_prefix)
    
    # Also support common generic paths
    patterns = [
        rf'({escaped_home}/Documents/Developer/[A-Za-z0-9_./@-]+)',
        rf'({escaped_home}/[A-Za-z0-9_./@-]+)',
        r'(/[A-Za-z0-9_./@-]+)', # Generic Unix absolute path
    ]
    
    if sys.platform == "win32":
        patterns.insert(0, r'([A-Za-z]:/[A-Za-z0-9_./@-]+)') # Windows absolute path (text is slash-normalized above)

    for pattern in patterns:
        for m in re.finditer(pattern, (text or "").replace("\\", "/")):
            path = m.group(1).rstrip(".,:;)")
            parts = path.split("/")
            # Attempt to find a reasonably deep project folder
            if len(parts) >= 6: # e.g. /Users/name/Documents/Developer/proj
                return "/".join(parts[:6])
            if len(parts) >= 4:
                return "/".join(parts[:4])
            return path

    return ANTIGRAVITY_UNASSIGNED

def _estimate_antigravity_tokens(sess_dir: Path) -> dict:
    import logging
    tkns = {"input": 0, "output": 0, "cached": 0, "total": 0, "cost": 0.0}
    tf = sess_dir / ".system_generated" / "logs" / "transcript_full.jsonl"
    if not tf.exists():
        tf = sess_dir / ".system_generated" / "logs" / "transcript.jsonl"
    if not tf.exists():
        return tkns
        
    cache_file = sess_dir / ".system_generated" / "logs" / "tokens_cache.json"
    try:
        if cache_file.exists() and cache_file.stat().st_mtime >= tf.stat().st_mtime:
            with open(cache_file, "r", encoding="utf-8") as cf:
                return json.load(cf)
    except (OSError, json.JSONDecodeError) as e:
        logging.debug(f"Failed to read token cache for {sess_dir}: {e}")

    try:
        with open(tf, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    tokens = len(line) // 4
                    if data.get("source") == "MODEL":
                        tkns["output"] += tokens
                    else:
                        tkns["input"] += tokens
                except json.JSONDecodeError as e:
                    logging.debug(f"Failed to parse line in {tf}: {e}")
        tkns["total"] = tkns["input"] + tkns["output"]
        
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_file, "w", encoding="utf-8") as cf:
                json.dump(tkns, cf)
        except OSError as e:
            logging.debug(f"Failed to write token cache for {sess_dir}: {e}")
            
    except OSError as e:
        logging.debug(f"Failed to access transcript for {sess_dir}: {e}")

    return tkns

# Model display name as embedded (protobuf string field) in Antigravity CLI
# trajectories, e.g. "Gemini 3.1 Pro (High)". Deliberately strict — requires a
# version number + tier word — so it never matches prose like "Gemini API ..."
# or skill/plugin names ("Claude Code") that also appear in the blobs.
_AG_MODEL_DISPLAY_RE = re.compile(
    rb'\b((?:Gemini|Claude|GPT)[ ]\d[0-9.]*[ ]'
    rb'(?:Pro|Flash|Ultra|Nano|Opus|Sonnet|Haiku)(?:[ ]\([A-Za-z]+\))?)'
)

# Tool-call steps in an Antigravity CLI trajectory embed a clean JSON arg blob.
# Its Cwd/SearchPath fields are the session's real workspace root; the file-path
# fields point at files it touched. These are the authoritative, always-present
# record of *where* a session worked — unlike history.jsonl, a rolling log that
# ages out. Paths under the agent's own home (~/.gemini/...) are internal
# (brain/scratch/mcp), not user projects, and are ignored.
_AG_WORKSPACE_RE = re.compile(rb'"(?:Cwd|SearchPath)"\s*:\s*"((?:[^"\\]|\\.)+)"')
_AG_FILEPATH_RE = re.compile(rb'"(?:AbsolutePath|TargetFile|DirectoryPath)"\s*:\s*"((?:[^"\\]|\\.)+)"')


def _antigravity_db_meta(db_path: Path) -> Dict[str, Optional[str]]:
    """Read model + project for one Antigravity CLI session from its SQLite trajectory.

    Single read-only pass over the DB:
      - **model**: most common display name in the gen_metadata blobs (None for
        older .pb-only sessions, which don't embed it).
      - **project**: the workspace the session actually worked in, taken from the
        Cwd/SearchPath of its tool calls (falling back to the project root of a
        touched file). Paths under ~/.gemini are the agent's own internals and
        are skipped, so a pure chat/research session that never entered a project
        stays unattributed (project=None) instead of being mislabeled.

    Best-effort: returns {"model": None, "project": None} on any DB/IO error."""
    from collections import Counter
    models: "Counter[str]" = Counter()
    roots: "Counter[str]" = Counter()
    files: "Counter[str]" = Counter()
    gemini_home = str(GEMINI_DIR)
    try:
        con = sqlite3.connect(_sqlite_ro_uri(db_path), uri=True)
        try:
            for (blob,) in con.execute("SELECT data FROM gen_metadata WHERE data IS NOT NULL"):
                if blob:
                    for m in _AG_MODEL_DISPLAY_RE.findall(blob):
                        models[m.decode("ascii", "ignore")] += 1
            for (payload,) in con.execute("SELECT step_payload FROM steps WHERE step_payload IS NOT NULL"):
                if not payload:
                    continue
                for m in _AG_WORKSPACE_RE.findall(payload):
                    v = m.decode("utf-8", "ignore")
                    if not v.startswith(gemini_home):
                        roots[v] += 1
                for m in _AG_FILEPATH_RE.findall(payload):
                    v = m.decode("utf-8", "ignore")
                    if not v.startswith(gemini_home):
                        files[v] += 1
        finally:
            con.close()
    except (sqlite3.Error, OSError):
        return {"model": None, "project": None}

    model = models.most_common(1)[0][0] if models else None
    project: Optional[str] = None
    if roots:
        project = roots.most_common(1)[0][0]
    elif files:
        inferred = _antigravity_infer_project(files.most_common(1)[0][0])
        if "unassigned" not in inferred:  # only accept a real derived root
            project = inferred
    return {"model": model, "project": project}


# --- Antigravity CLI per-step trace -----------------------------------------
# agy stores each trajectory step as a protobuf blob in conversations/<id>.db.
# We have no .proto schema, so (like the metadata reader above) we pattern-match
# the readable text + tool call out of the bytes — robust enough for a scrubbable
# trace. step_type is a stable discriminator across recent agy builds.
_AG_STEP_USER = 14            # the user's prompt
_AG_STEP_REASONING = 15       # assistant reasoning narrative + a tool call
_AG_STEP_TOOL_OUTPUT = 21     # result of a tool call
_AG_STEP_SKIP = {90, 98, 23}  # system EPHEMERAL prompt, internal id, bare file ref
_AG_TOOLNAME_RE = re.compile(rb'\x12.([a-z_]{3,40})\x1a')
_AG_TEXT_RE = re.compile(rb'(?:[\x09\x0a\x20-\x7e]|[\xc2-\xf4][\x80-\xbf]+){10,}')
_AG_ARGJSON_RE = re.compile(rb'\{(?:[^{}\\]|\\.|\{(?:[^{}\\]|\\.)*\})*\}')


def _ag_log_warn(msg: str, *args: Any) -> None:
    """Lazy logger for Antigravity parsing paths (avoids import-order coupling)."""
    import logging
    logging.getLogger("tokentelemetry.antigravity").warning(msg, *args)


def _ag_text_runs(payload: bytes) -> List[str]:
    """Decoded readable text runs from a step blob, excluding JSON arg objects
    and long bare token / hex-id strings (e.g. session UUIDs)."""
    runs = [t.decode("utf-8", "ignore") for t in _AG_TEXT_RE.findall(payload or b"")]
    return [
        r for r in runs
        if not r.lstrip().startswith("{")
        and not re.match(r"^[a-f0-9\$-]{20,}$", r.strip(), re.IGNORECASE)
    ]


def _ag_best_text(payload: bytes) -> str:
    """Longest readable text run in a step blob, excluding JSON arg objects."""
    runs = _ag_text_runs(payload)
    if not runs:
        return ""
    # Trim a leading 1-2 char protobuf framing token ("k\nicheck…" → "icheck…").
    txt = max(runs, key=len).strip()
    txt = re.sub(r"^[a-zA-Z]{1,2}\n", "", txt)
    return txt.strip()


def _ag_tool_call(payload: bytes):
    """(tool_name, parsed_args|None) for a step blob, or (None, None)."""
    m = _AG_TOOLNAME_RE.search(payload or b"")
    if not m:
        return None, None
    name = m.group(1).decode("ascii", "ignore")
    args = None
    jm = _AG_ARGJSON_RE.search(payload or b"")
    if jm:
        try:
            args = json.loads(jm.group(0).decode("utf-8", "ignore"))
        except Exception:
            args = None
    return name, args


def _parse_gemini_chat_file(cf: Path) -> Optional[Dict[str, Any]]:
    """Parse a Gemini/Antigravity chat log file (.json or .jsonl) into a normalized session dict."""
    try:
        with open(cf, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read().strip()
        if not raw:
            return None
        # Try reading as single JSON object first
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and "sessionId" in data:
                return data
        except Exception:
            pass

        # Read as JSON Lines (.jsonl)
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        header: Dict[str, Any] = {}
        messages: List[Dict[str, Any]] = []
        for i, line in enumerate(lines):
            try:
                entry = json.loads(line)
            except Exception:
                continue
            if not isinstance(entry, dict):
                continue
            if "$set" in entry:
                if isinstance(entry.get("$set"), dict) and "lastUpdated" in entry["$set"] and header:
                    header["lastUpdated"] = entry["$set"]["lastUpdated"]
                continue
            if "sessionId" in entry and ("kind" in entry or "projectHash" in entry):
                header = entry
                continue

            msg_type = entry.get("type", "unknown")
            role = "user" if msg_type in ("user", "human") else ("gemini" if msg_type in ("gemini", "assistant", "model") else msg_type)
            ts_str = entry.get("timestamp")

            sid_str = header.get("sessionId", "msg")
            msg: Dict[str, Any] = {
                "id": entry.get("id", f"{sid_str}-{i}"),
                "type": role,
                "role": role,
                "content": entry.get("content", ""),
            }
            if ts_str:
                msg["timestamp"] = ts_str
            if "thoughts" in entry:
                msg["thoughts"] = entry["thoughts"]
            if "toolCalls" in entry:
                msg["toolCalls"] = entry["toolCalls"]
            if "model" in entry:
                msg["model"] = entry["model"]
            if "tokens" in entry:
                msg["tokens"] = entry["tokens"]
            messages.append(msg)

        if not header and not messages:
            return None

        return {
            "sessionId": header.get("sessionId", ""),
            "projectHash": header.get("projectHash", ""),
            "startTime": header.get("startTime"),
            "lastUpdated": header.get("lastUpdated"),
            "kind": header.get("kind", "main"),
            "messages": messages,
        }
    except Exception as exc:
        _ag_log_warn("failed to parse gemini chat file %s: %s", cf, exc)
        return None


def _ag_event(role: str, content: list, sid: str, idx: int, order: int) -> Dict[str, Any]:
    return {
        "id": f"{sid}-step-{idx}",
        "type": role,                       # "user" | "assistant"
        "role": role,
        "message": {"role": role, "content": content},
        "normalized_timestamp": order * 1000,
    }


def _antigravity_cli_trace(db_path: Path, session_id: str) -> List[Dict[str, Any]]:
    """Build a Claude-format per-step trace from an agy session's SQLite steps or transcript log."""
    # Try SQLite steps parsing first
    if db_path and db_path.exists():
        try:
            con = sqlite3.connect(_sqlite_ro_uri(db_path), uri=True)
            rows = con.execute(
                "SELECT idx, step_type, step_payload FROM steps ORDER BY idx"
            ).fetchall()
            con.close()

            msgs: List[Dict[str, Any]] = []
            order = 0
            for idx, stype, payload in rows:
                if stype in _AG_STEP_SKIP or not payload:
                    continue
                text = _ag_best_text(payload)
                if stype == _AG_STEP_USER:
                    if not text:
                        continue
                    order += 1
                    msgs.append(_ag_event("user", [{"type": "text", "text": text}], session_id, idx, order))
                elif stype == _AG_STEP_TOOL_OUTPUT:
                    if not text:
                        continue
                    order += 1
                    msgs.append(_ag_event("user", [{"type": "tool_result", "content": text[:6000]}], session_id, idx, order))
                else:
                    tool, args = _ag_tool_call(payload)
                    # Reasoning narrative and the tool call are split into separate steps
                    # so both are counted and render distinctly (thinking → reasoning, the
                    # call → tool).
                    if stype == _AG_STEP_REASONING and text and not text.lstrip().startswith(("{", "<")):
                        order += 1
                        msgs.append(_ag_event("assistant", [{"type": "thinking", "text": text}], session_id, idx, order))
                    if tool:
                        order += 1
                        msgs.append(_ag_event("assistant", [{"type": "tool_use", "name": tool, "input": args or {"preview": text[:600]}}], session_id, idx, order))
                    elif stype != _AG_STEP_REASONING and text:
                        order += 1
                        msgs.append(_ag_event("assistant", [{"type": "text", "text": text}], session_id, idx, order))
            if msgs:
                return msgs
        except Exception as exc:
            _ag_log_warn("sqlite trace parse failed for %s: %s", db_path, exc)

    # Fallback to structured transcript.jsonl log in brain/
    for brain_root in ANTIGRAVITY_BRAIN_DIRS:
        b_dir = brain_root / session_id / ".system_generated" / "logs"
        for tname in ["transcript_full.jsonl", "transcript.jsonl"]:
            tfile = b_dir / tname
            if tfile.exists():
                msgs: List[Dict[str, Any]] = []
                order = 0
                pending_tool_ids: List[str] = []
                try:
                    with open(tfile, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            if not line.strip(): continue
                            try: entry = json.loads(line)
                            except Exception: continue
                            stype = entry.get("type")
                            content = entry.get("content", "")
                            if stype == "USER_INPUT" and content:
                                clean = re.sub(r"<USER_REQUEST>\s*", "", str(content))
                                clean = re.sub(r"\s*</USER_REQUEST>.*", "", clean, flags=re.DOTALL).strip()
                                if clean:
                                    order += 1
                                    msgs.append(_ag_event("user", [{"type": "text", "text": clean}], session_id, order, order))
                            elif stype == "PLANNER_RESPONSE" or stype == "MODEL_RESPONSE":
                                if isinstance(content, str) and content.strip():
                                    order += 1
                                    msgs.append(_ag_event("assistant", [{"type": "text", "text": content.strip()}], session_id, order, order))
                                tool_calls = entry.get("tool_calls") or []
                                for tc in tool_calls:
                                    if isinstance(tc, dict) and tc.get("name"):
                                        order += 1
                                        tool_id = tc.get("id") or tc.get("tool_call_id") or f"call-{order}"
                                        pending_tool_ids.append(tool_id)
                                        msgs.append(_ag_event("assistant", [{
                                            "type": "tool_use",
                                            "id": tool_id,
                                            "name": tc.get("name"),
                                            "input": tc.get("args") or tc.get("arguments") or {}
                                        }], session_id, order, order))
                            elif stype == "TOOL_RESULT":
                                res = entry.get("output") or content or ""
                                tool_id = entry.get("tool_call_id") or entry.get("toolUseId")
                                if tool_id:
                                    try:
                                        pending_tool_ids.remove(tool_id)
                                    except ValueError:
                                        pass
                                elif pending_tool_ids:
                                    # Some transcript versions omit the result's
                                    # tool_call_id. Reuse the oldest pending call ID
                                    # so the UI can still pair the result with its call.
                                    tool_id = pending_tool_ids.pop(0)
                                order += 1
                                msgs.append(_ag_event("user", [{
                                    "type": "tool_result",
                                    "tool_use_id": tool_id or f"call-{order}",
                                    "content": str(res)[:6000]
                                }], session_id, order, order))
                    if msgs:
                        return msgs
                except Exception as exc:
                    _ag_log_warn("transcript parse failed for %s: %s", tfile, exc)

    return []


def _antigravity_first_prompt(sid: str, fallback_text: str = "") -> str:
    """Extract the first user prompt for an Antigravity session to use as display intent."""
    for brain_root in ANTIGRAVITY_BRAIN_DIRS:
        b_dir = brain_root / sid / ".system_generated" / "logs"
        for tname in ["transcript_full.jsonl", "transcript.jsonl"]:
            tfile = b_dir / tname
            if tfile.exists():
                try:
                    with open(tfile, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            if not line.strip(): continue
                            entry = json.loads(line)
                            if entry.get("type") == "USER_INPUT":
                                content = str(entry.get("content", ""))
                                clean = re.sub(r"<USER_REQUEST>\s*", "", content)
                                clean = re.sub(r"\s*</USER_REQUEST>.*", "", clean, flags=re.DOTALL).strip()
                                if clean:
                                    return clean[:100]
                except Exception as exc:
                    _ag_log_warn("first-prompt transcript read failed for %s: %s", tfile, exc)

    cli_db = ANTIGRAVITY_CLI_DIR / "conversations" / f"{sid}.db"
    if cli_db.exists():
        try:
            con = sqlite3.connect(_sqlite_ro_uri(cli_db), uri=True)
            rows = con.execute(
                "SELECT step_payload FROM steps WHERE step_type = ? ORDER BY idx ASC LIMIT 5",
                (_AG_STEP_USER,),
            ).fetchall()
            con.close()
            for (payload,) in rows:
                if payload:
                    runs = _ag_text_runs(payload)
                    if runs:
                        txt = max(runs, key=len).strip()
                        txt = re.sub(r"^[a-zA-Z]{1,2}\n", "", txt).strip()
                        if txt and not txt.startswith("command(") and not txt.startswith("./Users"):
                            return txt[:100]
        except Exception as exc:
            _ag_log_warn("first-prompt sqlite read failed for %s: %s", cli_db, exc)

    return (fallback_text or "Antigravity session")[:100]


def _antigravity_cli_meta(cli_dir: Path = ANTIGRAVITY_CLI_DIR) -> Dict[str, Dict[str, Any]]:
    """Enrich Antigravity CLI (`agy`) sessions from its own stores.

    The brain/ scanner only sees derived markdown, so it labels every CLI session
    with a generic model ("gemini (antigravity)") and a project heuristically
    guessed from the task/plan text. Here we recover the ground truth, preferring
    the per-session SQLite trajectory (permanent) over history.jsonl (a rolling
    log that ages out):

      1. model + project from each conversations/<uuid>.db (see _antigravity_db_meta);
      2. project from history.jsonl (conversationId -> workspace) as a fallback for
         sessions whose trajectory recorded no workspace (e.g. older .pb sessions).

    Session ids in brain/ are the conversation UUIDs, so the returned map keys
    line up 1:1. Returns {session_id: {"model": str, "project": str}} with each
    field present only when found. Best-effort — never raises."""
    meta: Dict[str, Dict[str, Any]] = {}
    # 1. Authoritative, permanent: each session's own SQLite trajectory.
    conv = cli_dir / "conversations"
    try:
        db_files = sorted(conv.glob("*.db")) if conv.exists() else []
    except OSError:
        db_files = []
    for db in db_files:
        dm = _antigravity_db_meta(db)
        entry: Dict[str, Any] = {}
        if dm.get("model"):
            entry["model"] = dm["model"]
        if dm.get("project"):
            entry["project"] = dm["project"]
        if entry:
            meta[db.stem] = entry
    # 2. Fallback project source: the flat prompt log. Build a last-wins map
    #    (newest cwd per conversation), then fill only sessions the .db didn't
    #    resolve — so a project from the authoritative .db always wins.
    hist_project: Dict[str, str] = {}
    hist = cli_dir / "history.jsonl"
    try:
        if hist.exists():
            with open(hist, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    cid, ws = rec.get("conversationId"), rec.get("workspace")
                    if cid and ws:
                        hist_project[cid] = ws  # last line wins => latest cwd
    except OSError:
        pass
    for cid, ws in hist_project.items():
        meta.setdefault(cid, {}).setdefault("project", ws)
    return meta

class TokenUsage(BaseModel):
    input: int = 0
    output: int = 0
    cached: int = 0
    total: int = 0

class PlanSnippet(BaseModel):
    session_id: str
    agent: str
    timestamp: datetime
    content: str

class Artifact(BaseModel):
    name: str
    path: str
    type: str # 'video', 'image', 'document', 'terminal'

class PublishedArtifact(BaseModel):
    """A user-facing artifact an agent produced as a deliverable, shown on the
    project Artifacts tab. Two kinds: "page" — a hosted claude.ai page from
    Claude Code's Artifact tool (has `url`); "document" — a local doc like
    Antigravity's task/plan/walkthrough (has `path`, served via
    /artifacts?path=). Unlike `Artifact`, entries carry display metadata
    (title/description) mined from the transcript or metadata sidecars."""
    kind: str = "page"
    url: Optional[str] = None
    path: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    favicon: Optional[str] = None
    file_name: Optional[str] = None
    session_id: Optional[str] = None
    agent: Optional[str] = None
    timestamp: Optional[str] = None

# class QualityMetrics(BaseModel):
#     edit_turns: int = 0
#     retry_turns: int = 0
#     measured: bool = False

class Session(BaseModel):
    id: str
    agent: str
    project: str
    timestamp: datetime
    display: Optional[str] = None
    text: Optional[str] = None
    mcp_tools: List[str] = []
    subagents: List[str] = []
    has_plan: bool = False
    tokens: TokenUsage = TokenUsage()
    plans: List[PlanSnippet] = []
    artifacts: List[Artifact] = []
    published_artifacts: List[PublishedArtifact] = []
    # quality: QualityMetrics = QualityMetrics()

# EDIT_TOOLS: Set[str] = {"Edit", "MultiEdit", "Write", "NotebookEdit"}

def _hermes_dbs_with_profiles() -> List[Tuple[Path, Optional[str]]]:
    """Every Hermes state.db paired with its owning profile (None = default).

    A Hermes profile (~/.hermes/profiles/<name>/) is a full parallel agent
    home — own config, SOUL.md, sessions, state.db, skills, cron, gateway.
    Hermes itself has no cross-profile usage view, so the profile tag is
    what lets TT attribute sessions to the profile that produced them.
    """
    dbs: List[Tuple[Path, Optional[str]]] = []
    if HERMES_DB.exists():
        dbs.append((HERMES_DB, None))
    if HERMES_PROFILES_DIR.is_dir():
        for p in sorted(HERMES_PROFILES_DIR.glob("*/state.db")):
            if p.exists():
                dbs.append((p, p.parent.name))
    return dbs


def _hermes_dbs() -> List[Path]:
    return [p for p, _ in _hermes_dbs_with_profiles()]


def _hermes_home(profile: Optional[str]) -> Path:
    """Root dir whose logs/gateway/cron belong to the given profile."""
    return (HERMES_PROFILES_DIR / profile) if profile else HERMES_DIR


_HERMES_CWD_RE = re.compile(r"\[(\d{8}_\d{6}_[a-f0-9]+)\][^\n]*cwd=([^\s,)]+)")

# Structured agent.log lines we parse (per HERMES_INTERNALS.md §2.3) now live in
# hermes_telemetry.py, which owns the cached whole-log index. Kept as aliases so
# nothing that reached for these names breaks.
_HERMES_API_CALL_RE = _ht.API_CALL_RE
_HERMES_TOOL_DONE_RE = _ht.TOOL_DONE_RE
_HERMES_TOOL_FAIL_RE = _ht.TOOL_FAIL_RE
_parse_hermes_log_ts = _ht.parse_log_ts


def _hermes_log_summary(session_id: str, profile: Optional[str] = None) -> Dict[str, Any]:
    """Per-session view of the owning home's logs/agent.log*.

    Each profile writes its own agent.log, so sessions recorded in a
    profile's state.db never appear in the root log — pass the profile
    or the overlay comes back empty.

    Reads from hermes_telemetry's cached index (every rotated log parsed once,
    oldest suffix first) rather than rescanning the file per session.

    Returns:
      api_calls: list of {ts, n, model, provider, in, out, total, latency_s, cache_hit_pct?, cache_read?}
      tool_calls: list of {ts, tool, duration_s, chars?, status, error?}
      model_journey: distinct models in temporal order
      summary: {api_call_count, total_latency_s, avg_latency_s, cache_hit_pct, models_used, log_coverage} | None
      log_coverage: "captured" when the logs carry API calls for this session
    """
    try:
        index, _files = _ht.get_log_index(_hermes_home(profile))
        entry = index.get(session_id) or _ht.EMPTY_ENTRY
    except Exception:
        entry = _ht.EMPTY_ENTRY
    api_calls = entry.get("api_calls") or []
    tool_calls = entry.get("tool_calls") or []
    return {
        "api_calls": api_calls,
        "tool_calls": tool_calls,
        "model_journey": _ht.model_journey(api_calls),
        "summary": _ht.summarize(api_calls),
        "log_coverage": "captured" if api_calls else "not_captured",
    }


def _hermes_log_index_all() -> Tuple[Dict[str, Any], List[str]]:
    """Merged log index across the root home and every profile home."""
    homes = []
    seen = set()
    for _db, profile in _hermes_dbs_with_profiles():
        home = _hermes_home(profile)
        if str(home) in seen:
            continue
        seen.add(str(home))
        homes.append((profile, home))
    parts = []
    for profile, home in homes:
        try:
            index, files = _ht.get_log_index(home)
        except Exception:
            continue
        parts.append((profile, index, files))
    return _ht.merge_indexes(parts)


def _hermes_memory_io(session_id: str) -> Dict[str, Any]:
    """Count memory tool invocations from messages.tool_calls JSON.

    Hermes's memory tool is a single tool (NOT memory_read/write/search/delete).
    Schema: `memory(action="add|replace|remove", target="memory|user", ...)`.
    """
    out = {
        "add_memory": 0, "add_user": 0,
        "replace_memory": 0, "replace_user": 0,
        "remove_memory": 0, "remove_user": 0,
        "total": 0,
    }
    for db_path in _hermes_dbs():
        try:
            uri = _sqlite_ro_uri(db_path)
            conn = sqlite3.connect(uri, uri=True, timeout=1.0)
            try:
                rows = conn.execute(
                    "SELECT tool_calls FROM messages WHERE session_id=? AND tool_calls IS NOT NULL",
                    (session_id,)
                ).fetchall()
                for (raw,) in rows:
                    if not raw: continue
                    try:
                        tcs = json.loads(raw)
                    except Exception: continue
                    if not isinstance(tcs, list): continue
                    for tc in tcs:
                        fn = (tc or {}).get("function") or {}
                        if (fn.get("name") or tc.get("name")) != "memory":
                            continue
                        args_raw = fn.get("arguments") or "{}"
                        try:
                            args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
                        except Exception: continue
                        action = (args.get("action") or "").lower()
                        target = (args.get("target") or "memory").lower()
                        if action in {"add", "replace", "remove"} and target in {"memory", "user"}:
                            out[f"{action}_{target}"] += 1
                            out["total"] += 1
            finally:
                conn.close()
        except Exception:
            continue
    return out


@app.get("/hermes/skills")
async def hermes_skills():
    """Walk .skills_prompt_snapshot.json + skills/ directory.

    Returns: {snapshot_loaded: int, skills: [{name, category, description, platforms, conditions}]}
    """
    snap_path = HERMES_DIR / ".skills_prompt_snapshot.json"
    if not snap_path.exists():
        return {"snapshot_loaded": 0, "skills": [], "categories": {}}
    try:
        with open(snap_path, "r", encoding="utf-8") as f:
            snap = json.load(f)
    except Exception:
        return {"snapshot_loaded": 0, "skills": [], "categories": {}}
    skills_list = snap.get("skills") or []
    if isinstance(skills_list, dict):
        # Older format: dict keyed by name
        skills_list = list(skills_list.values())
    out: List[Dict[str, Any]] = []
    for s in skills_list:
        if not isinstance(s, dict): continue
        out.append({
            "name": s.get("skill_name") or s.get("frontmatter_name"),
            "category": s.get("category"),
            "description": s.get("description"),
            "platforms": s.get("platforms") or [],
            "conditions": s.get("conditions") or {},
        })
    cats = snap.get("category_descriptions") or {}
    return {
        "snapshot_loaded": len(out),
        "skills": out,
        "categories": cats if isinstance(cats, dict) else {},
    }


def _parse_memory_md(path: Path) -> Dict[str, Any]:
    """Read MEMORY.md / USER.md; split on the `\\n§\\n` delimiter Hermes uses."""
    if not path.exists():
        return {"entries": [], "char_count": 0, "exists": False}
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {"entries": [], "char_count": 0, "exists": False}
    entries = [e.strip() for e in text.split("\n§\n") if e.strip()]
    return {"entries": entries, "char_count": len(text), "exists": True}


@app.get("/hermes/memory")
async def hermes_memory():
    mem_dir = HERMES_DIR / "memories"
    return {
        "memory": _parse_memory_md(mem_dir / "MEMORY.md"),
        "user":   _parse_memory_md(mem_dir / "USER.md"),
        # Hermes defaults from tools/memory_tool.py
        "memory_char_limit": 2200,
        "user_char_limit": 1375,
    }


@app.get("/hermes/soul")
async def hermes_soul():
    """Read the SOUL.md file."""
    soul_path = HERMES_DIR / "SOUL.md"
    if not soul_path.exists():
        return {"content": "No SOUL.md found.", "exists": False}
    try:
        content = soul_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        content = "Error reading SOUL.md"
    return {"content": content, "exists": True}


def _hermes_profile_meta(home: Path) -> Dict[str, Any]:
    """Cheap local reads only — never .env, auth.json, or full config.yaml."""
    description = None
    try:
        py = home / "profile.yaml"
        if py.exists():
            m = re.search(r"^description\s*:\s*(.+)$",
                          py.read_text(encoding="utf-8", errors="ignore"), re.M)
            if m:
                description = m.group(1).strip().strip("'\"") or None
    except Exception:
        pass
    skills_count = 0
    try:
        skills_dir = home / "skills"
        if skills_dir.is_dir():
            skills_count = sum(1 for d in skills_dir.iterdir()
                               if d.is_dir() and not d.name.startswith("."))
    except Exception:
        pass
    return {
        "description": description,
        "soul_exists": (home / "SOUL.md").exists(),
        "skills_count": skills_count,
        "cron_jobs": len(_hermes_cron_jobs(home)),
        "gateway": _hermes_gateway_state(home),
    }


@app.get("/hermes/profiles")
async def hermes_profiles():
    """Profiles with metadata and a per-profile usage rollup.

    A profile is a full parallel Hermes home; Hermes itself offers no
    combined usage/cost view across profiles, so TT aggregates one here.
    Usage comes from the shared session scan (grouped by the scan's
    hermes_profile tag) so the numbers match the rest of the dashboard.
    """
    if not HERMES_DIR.is_dir():
        return {"profiles": [], "active_profile": None}

    # `hermes profile use <name>` writes the sticky marker; absent = default.
    active = None
    try:
        marker = HERMES_DIR / "active_profile"
        if marker.exists():
            active = marker.read_text(encoding="utf-8").strip() or None
    except Exception:
        pass

    def _empty_usage() -> Dict[str, Any]:
        return {"sessions": 0, "input_tokens": 0, "output_tokens": 0,
                "total_tokens": 0, "cost": 0.0, "last_activity": None,
                "cost_7d": 0.0, "cost_prev_7d": 0.0, "unattended_cost_7d": 0.0,
                "daily": []}

    # Sessions nobody was watching when they spent — the runaway-swarm /
    # overnight-cron burn users get surprised by. Matches Hermes's own
    # autonomous source values.
    _UNATTENDED_SOURCES = {"cron", "subagent", "kanban", "tool"}

    now_local = datetime.now().astimezone()
    day_cost: Dict[str, Dict[str, float]] = {}
    usage: Dict[str, Dict[str, Any]] = {}
    try:
        for s in await get_sessions_cached():
            if s.get("agent") != "hermes":
                continue
            key = s.get("hermes_profile") or "default"
            u = usage.setdefault(key, _empty_usage())
            u["sessions"] += 1
            tk = s.get("tokens") or {}
            u["input_tokens"] += tk.get("input", 0) or 0
            u["output_tokens"] += tk.get("output", 0) or 0
            u["total_tokens"] += tk.get("total", 0) or 0
            cost = float(s.get("cost") or 0)
            u["cost"] += cost
            ts = s.get("timestamp")
            iso = ts.isoformat() if isinstance(ts, datetime) else ts
            if iso and (u["last_activity"] is None or iso > u["last_activity"]):
                u["last_activity"] = iso
            if isinstance(ts, datetime):
                ts_local = ts.astimezone()
                age_days = (now_local - ts_local).total_seconds() / 86400
                if age_days <= 7:
                    u["cost_7d"] += cost
                    if (s.get("source_subtype") or "") in _UNATTENDED_SOURCES:
                        u["unattended_cost_7d"] += cost
                elif age_days <= 14:
                    u["cost_prev_7d"] += cost
                # Day buckets are LOCAL days — build keys from local Y/M/D,
                # never toISOString/utc (see project rule on day bucketing).
                dkey = f"{ts_local.year:04d}-{ts_local.month:02d}-{ts_local.day:02d}"
                day_cost.setdefault(key, {})
                day_cost[key][dkey] = day_cost[key].get(dkey, 0.0) + cost
    except Exception:
        pass

    # Last 14 local days, oldest first, zero-filled so sparklines align.
    day_keys: List[str] = []
    for i in range(13, -1, -1):
        d = now_local - timedelta(days=i)
        day_keys.append(f"{d.year:04d}-{d.month:02d}-{d.day:02d}")

    def _usage_for(key: str) -> Dict[str, Any]:
        u = usage.get(key) or _empty_usage()
        per = day_cost.get(key, {})
        u["daily"] = [{"date": dk, "cost": round(per.get(dk, 0.0), 6)}
                      for dk in day_keys]
        return u

    profiles: List[Dict[str, Any]] = [{
        "name": "default",
        "is_default": True,
        "active": active is None,
        "usage": _usage_for("default"),
        **_hermes_profile_meta(HERMES_DIR),
    }]
    if HERMES_PROFILES_DIR.is_dir():
        for p in sorted(HERMES_PROFILES_DIR.iterdir()):
            if not p.is_dir():
                continue
            profiles.append({
                "name": p.name,
                "is_default": False,
                "active": active == p.name,
                "usage": _usage_for(p.name),
                **_hermes_profile_meta(p),
            })
    return {"profiles": profiles, "active_profile": active}


def _hermes_kanban_dbs() -> List[Tuple[Path, Optional[str], str]]:
    """(db_path, profile, board) for every Hermes kanban DB.

    Layout per home: the default board is <home>/kanban.db (back-compat with
    pre-boards installs); named boards live at <home>/kanban/boards/<slug>/kanban.db.
    """
    out: List[Tuple[Path, Optional[str], str]] = []
    homes: List[Tuple[Path, Optional[str]]] = [(HERMES_DIR, None)]
    if HERMES_PROFILES_DIR.is_dir():
        homes.extend((p, p.name) for p in sorted(HERMES_PROFILES_DIR.iterdir())
                     if p.is_dir())
    for home, profile in homes:
        default_db = home / "kanban.db"
        if default_db.exists():
            out.append((default_db, profile, "default"))
        boards_dir = home / "kanban" / "boards"
        if boards_dir.is_dir():
            for db in sorted(boards_dir.glob("*/kanban.db")):
                out.append((db, profile, db.parent.name))
    return out


def _connect_kanban_ro(db_path: Path) -> sqlite3.Connection:
    """mode=ro, falling back to immutable=1 — a kanban DB in WAL mode inside a
    0700 home can refuse a plain read-only open (no -shm access)."""
    uri = _sqlite_ro_uri(db_path)
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=1.0)
        conn.execute("SELECT 1 FROM sqlite_master LIMIT 1")
        return conn
    except sqlite3.OperationalError:
        return sqlite3.connect(uri + "&immutable=1", uri=True, timeout=1.0)


@app.get("/hermes/kanban")
async def hermes_kanban():
    """Kanban boards with per-task cost attribution.

    Hermes's swarm/board tracks tasks and runs but never costs them
    (per-goal cost attribution is a standing user ask). Newer Hermes links
    tasks to state.db sessions via tasks.session_id — where present we join
    the session's cost/tokens from the shared scan; task_runs.profile tells
    us which profile-worker did the work.
    """
    dbs = _hermes_kanban_dbs()
    if not dbs:
        return {"installed": False, "boards": []}

    # session id -> (cost, tokens) from the shared scan, so task costs match
    # every other number on the dashboard.
    sess_cost: Dict[str, Tuple[float, int]] = {}
    try:
        for s in await get_sessions_cached():
            if s.get("agent") == "hermes":
                sess_cost[s["id"]] = (float(s.get("cost") or 0),
                                      int((s.get("tokens") or {}).get("total", 0) or 0))
    except Exception:
        pass

    def _iso(unix) -> Optional[str]:
        try:
            if not unix:
                return None
            return datetime.fromtimestamp(float(unix), tz=timezone.utc).isoformat()
        except Exception:
            return None

    boards: List[Dict[str, Any]] = []
    for db_path, profile, board in dbs:
        try:
            conn = _connect_kanban_ro(db_path)
            conn.row_factory = sqlite3.Row
            try:
                cols = {r[1] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()}
                if "id" not in cols:
                    continue
                # session_id arrived via migration — older boards lack it.
                sid_col = "session_id" if "session_id" in cols else "NULL AS session_id"
                rows = conn.execute(
                    "SELECT id, title, status, assignee, priority, created_at, "
                    "started_at, completed_at, consecutive_failures, "
                    f"last_failure_error, {sid_col} FROM tasks"
                ).fetchall()
                runs_by_task: Dict[str, Dict[str, Any]] = {}
                try:
                    for r in conn.execute(
                        "SELECT task_id, profile, status, outcome FROM task_runs"
                    ):
                        agg = runs_by_task.setdefault(r["task_id"], {
                            "count": 0, "failed": 0, "profiles": []})
                        agg["count"] += 1
                        if (r["outcome"] or "") not in ("", "completed"):
                            agg["failed"] += 1
                        if r["profile"] and r["profile"] not in agg["profiles"]:
                            agg["profiles"].append(r["profile"])
                except Exception:
                    pass

                tasks: List[Dict[str, Any]] = []
                totals_cost = 0.0
                by_status: Dict[str, int] = {}
                by_assignee: Dict[str, Dict[str, Any]] = {}
                for row in rows:
                    sid = row["session_id"]
                    cost, toks = sess_cost.get(sid, (0.0, 0)) if sid else (0.0, 0)
                    status = row["status"] or "unknown"
                    assignee = row["assignee"] or "(unassigned)"
                    totals_cost += cost
                    by_status[status] = by_status.get(status, 0) + 1
                    a = by_assignee.setdefault(assignee, {"assignee": assignee,
                                                          "tasks": 0, "cost": 0.0})
                    a["tasks"] += 1
                    a["cost"] += cost
                    tasks.append({
                        "id": row["id"], "title": row["title"],
                        "status": status, "assignee": row["assignee"],
                        "priority": row["priority"] or 0,
                        "created_at": _iso(row["created_at"]),
                        "started_at": _iso(row["started_at"]),
                        "completed_at": _iso(row["completed_at"]),
                        "consecutive_failures": row["consecutive_failures"] or 0,
                        "last_failure_error": row["last_failure_error"],
                        "session_id": sid,
                        "cost": cost, "tokens": toks,
                        "runs": runs_by_task.get(row["id"]),
                    })
            finally:
                conn.close()
        except Exception:
            continue
        boards.append({
            "profile": profile, "board": board,
            "tasks": tasks,
            "totals": {
                "tasks": len(tasks), "cost": round(totals_cost, 6),
                "by_status": by_status,
                "by_assignee": sorted(by_assignee.values(),
                                      key=lambda x: -x["cost"]),
            },
        })
    return {"installed": True, "boards": boards}


@app.get("/hermes/tools")
async def hermes_tools():
    """List toolsets configured in config.yaml."""
    config_path = HERMES_DIR / "config.yaml"
    enabled_tools = []
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                content = f.read()
                import re
                match = re.search(r'platform_toolsets\s*:.*?\n\s+cli\s*:.*?\n((?:\s+-\s+\w+\s*\n)+)', content, re.DOTALL)
                if match:
                    tools_block = match.group(1)
                    enabled_tools = re.findall(r'-\s+(\w+)', tools_block)
        except Exception:
            pass
    return {"enabled_tools": enabled_tools}


@app.get("/sessions/{session_id}/grok-forensics")
async def grok_session_forensics(session_id: str):
    """Rich forensics payload for a Grok Build session (phases, permissions, tool lifecycle, token progression)."""
    sess_dir = None
    for bucket in GROK_SESSIONS_DIR.glob("*"):
        candidate = bucket / session_id
        if candidate.is_dir():
            sess_dir = candidate
            break
    if not sess_dir:
        return {"error": "Not found"}

    summary = {}
    try:
        with open(sess_dir / GROK_SUMMARY, "r", encoding="utf-8") as f:
            summary = json.load(f)
    except Exception:
        pass

    # Extract high-signal events
    tool_events = []
    permission_events = []
    phase_events = []
    token_progression = []

    events_path = sess_dir / GROK_EVENTS
    if events_path.exists():
        try:
            with open(events_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    try:
                        ev = json.loads(line)
                        t = ev.get("type")
                        if t in ("tool_started", "tool_completed"):
                            tool_events.append(ev)
                        elif t in ("permission_requested", "permission_resolved"):
                            permission_events.append(ev)
                        elif t == "phase_changed":
                            phase_events.append(ev)
                    except Exception:
                        continue
        except Exception:
            pass

    updates_path = sess_dir / GROK_UPDATES
    if updates_path.exists():
        try:
            with open(updates_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "totalTokens" in line:
                        try:
                            u = json.loads(line)
                            meta = (u.get("params") or {}).get("_meta") or {}
                            if "totalTokens" in meta:
                                token_progression.append({
                                    "ts": u.get("timestamp"),
                                    "totalTokens": meta["totalTokens"],
                                    "updateType": meta.get("updateType"),
                                })
                        except Exception:
                            continue
        except Exception:
            pass

    plan = {}
    try:
        with open(sess_dir / GROK_PLAN_MODE, "r", encoding="utf-8") as f:
            plan = json.load(f)
    except Exception:
        pass

    # signals.json — Grok's rich accurate metrics. Mapped to a fixed snake_case
    # shape the frontend reads; {} when the file is missing entirely.
    signals_block: Dict[str, Any] = {}
    raw_signals: Dict[str, Any] = {}
    signals_path = sess_dir / GROK_SIGNALS
    if signals_path.exists():
        try:
            with open(signals_path, "r", encoding="utf-8") as f:
                raw_signals = json.load(f) or {}
        except Exception:
            raw_signals = {}
        signals_block = {
            "context_tokens_used": raw_signals.get("contextTokensUsed", 0),
            "context_window_tokens": raw_signals.get("contextWindowTokens", 0),
            "context_window_usage_pct": raw_signals.get("contextWindowUsage", 0),
            "tool_call_count": raw_signals.get("toolCallCount", 0),
            "tools_used": raw_signals.get("toolsUsed", []) or [],
            "models_used": raw_signals.get("modelsUsed", []) or [],
            "session_duration_seconds": raw_signals.get("sessionDurationSeconds", 0),
            "turn_count": raw_signals.get("turnCount", 0),
            "user_message_count": raw_signals.get("userMessageCount", 0),
            "assistant_message_count": raw_signals.get("assistantMessageCount", 0),
            "error_count": raw_signals.get("errorCount", 0),
            "tool_failure_count": raw_signals.get("toolFailureCount", 0),
            "cancellation_count": raw_signals.get("cancellationCount", 0),
            "compaction_count": raw_signals.get("compactionCount", 0),
            "doom_loop_detections": raw_signals.get("doomLoopDetections", 0),
            "agent_lines_added": raw_signals.get("agentLinesAdded", 0),
            "agent_lines_removed": raw_signals.get("agentLinesRemoved", 0),
            "agent_files_touched": raw_signals.get("agentFilesTouched", 0),
            "avg_time_to_first_token_ms": raw_signals.get("avgTimeToFirstTokenMs", None),
            "avg_response_time_ms": raw_signals.get("avgResponseTimeMs", None),
        }

    return {
        "session_id": session_id,
        "summary": summary,
        "plan_mode": plan,
        "signals": signals_block,
        "tool_events": tool_events[-100:],          # cap for UI
        "permission_events": permission_events[-50:],
        "phase_events": phase_events[-30:],
        "token_progression": token_progression[-100:],
        "counts": {
            "tools": len(tool_events),
            "permissions": len(permission_events),
            "phases": len(phase_events),
            "token_samples": len(token_progression),
        }
    }


def _hermes_session_profile(session_id: str) -> Optional[str]:
    """Which profile's state.db holds this session (None = default root)."""
    for db_path, profile in _hermes_dbs_with_profiles():
        try:
            conn = sqlite3.connect(_sqlite_ro_uri(db_path), uri=True, timeout=1.0)
            try:
                row = conn.execute(
                    "SELECT 1 FROM sessions WHERE id=? LIMIT 1", (session_id,)
                ).fetchone()
            finally:
                conn.close()
            if row:
                return profile
        except Exception:
            continue
    return None


@app.get("/sessions/{session_id}/hermes-overlay")
async def hermes_session_overlay(session_id: str):
    """Per-session overlay derived from agent.log + memory tool calls."""
    profile = _hermes_session_profile(session_id)
    log = _hermes_log_summary(session_id, profile)
    mem = _hermes_memory_io(session_id)
    return {
        "session_id": session_id,
        "profile": profile,
        # "not_captured" is not the same as zero: Hermes rotates agent.log, and a
        # session whose lines have aged out (or that predates log capture) has NO
        # latency data — reporting 0s would invent a number.
        "log_coverage": log["log_coverage"],
        "performance": log["summary"],
        "api_calls": log["api_calls"],
        "tool_calls": log["tool_calls"],
        "model_journey": log["model_journey"],
        "memory_io": mem,
    }


def _hermes_cwd_by_session() -> Dict[str, str]:
    """Recover per-session cwd from agent.log (root home + every profile).

    Hermes doesn't persist cwd in its schema (it's a portable agent — no project
    concept). The cwd surfaces only as a side effect when the `terminal` tool
    initializes a sandbox. We parse the log line and attribute the *first* cwd
    seen per session id. Sessions that never invoked the terminal stay 'unknown'.
    Fidelity: inferred.
    """
    log_paths = [HERMES_DIR / "logs" / "agent.log"]
    if HERMES_PROFILES_DIR.is_dir():
        log_paths.extend(sorted(HERMES_PROFILES_DIR.glob("*/logs/agent.log")))
    out: Dict[str, str] = {}
    for log_path in log_paths:
        if not log_path.exists():
            continue
        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    m = _HERMES_CWD_RE.search(line)
                    if not m:
                        continue
                    sid, cwd = m.group(1), m.group(2)
                    if sid not in out:  # first wins
                        out[sid] = cwd
        except Exception:
            continue
    return out


def _hermes_gateway_state(home: Optional[Path] = None) -> Dict[str, Any]:
    """Read gateway_state.json + gateway.pid from a Hermes home (default root).

    Each profile runs its own gateway with its own pid/state files, so pass
    the profile's home to get that gateway's health.

    Returns dict with keys: state (str), pid (int|None), pid_alive (bool),
    active_agents (int), platforms (list[{name, state, error_code}]),
    updated_at (iso str|None). All-NULL if no gateway file present.
    """
    base = home or HERMES_DIR
    state_path = base / "gateway_state.json"
    pid_path = base / "gateway.pid"
    out: Dict[str, Any] = {
        "state": None, "pid": None, "pid_alive": False,
        "active_agents": 0, "platforms": [], "updated_at": None,
    }
    try:
        if state_path.exists():
            with open(state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            out["state"] = data.get("gateway_state")
            out["active_agents"] = int(data.get("active_agents") or 0)
            out["updated_at"] = data.get("updated_at")
            plats = data.get("platforms") or {}
            if isinstance(plats, dict):
                out["platforms"] = [
                    {"name": k, "state": (v or {}).get("state"),
                     "error_code": (v or {}).get("error_code")}
                    for k, v in plats.items()
                ]
    except Exception:
        pass
    try:
        if pid_path.exists():
            with open(pid_path, "r", encoding="utf-8") as f:
                raw = f.read().strip()
            try:
                pid_data = json.loads(raw)
                out["pid"] = pid_data.get("pid") if isinstance(pid_data, dict) else int(pid_data)
            except json.JSONDecodeError:
                out["pid"] = int(raw)
            # Cheap liveness check. On POSIX, kill(pid, 0) is a no-op probe.
            # On Windows, kill(pid, 0) actually terminates the process, so use
            # OpenProcess via ctypes instead.
            if out["pid"]:
                out["pid_alive"] = _pid_alive(out["pid"])
    except Exception:
        pass
    return out


def _hermes_cron_jobs(home: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Read cron/jobs.json from a Hermes home (default root) — the
    scheduled-job registry.

    Annotates each job with `at_risk` when next_run_at is past now (grace window
    applied per Hermes's own rule: daily=2h, hourly=30m, 10min=5m). Hermes itself
    fast-forwards past these but doesn't expose them — so we flag them.
    """
    jobs_path = (home or HERMES_DIR) / "cron" / "jobs.json"
    if not jobs_path.exists():
        return []
    try:
        with open(jobs_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    # Hermes writes {"jobs": [...], "updated_at": "..."} now; tolerate the
    # legacy top-level list shape too so this keeps working across versions.
    if isinstance(data, dict):
        data = data.get("jobs") or []
    if not isinstance(data, list):
        return []
    out: List[Dict[str, Any]] = []
    now = datetime.now(tz=timezone.utc)
    for j in data:
        if not isinstance(j, dict):
            continue
        nxt_raw = j.get("next_run_at")
        nxt_dt = None
        if nxt_raw:
            try:
                nxt_dt = datetime.fromisoformat(str(nxt_raw).replace("Z", "+00:00"))
                if nxt_dt.tzinfo is None:
                    nxt_dt = nxt_dt.replace(tzinfo=timezone.utc)
            except Exception:
                pass
        sched = (j.get("schedule") or {}) if isinstance(j.get("schedule"), dict) else {}
        kind = (sched.get("kind") or "").lower()
        grace_s = {"daily": 7200, "hourly": 1800}.get(kind, 300)
        at_risk = bool(nxt_dt and (now - nxt_dt).total_seconds() > grace_s)
        # `deliver` is sometimes a string, sometimes a list — normalize to list
        # so the UI doesn't have to special-case it.
        deliver_raw = j.get("deliver")
        if isinstance(deliver_raw, list):
            deliver = [str(x) for x in deliver_raw if x]
        elif deliver_raw:
            deliver = [str(deliver_raw)]
        else:
            deliver = ["local"]
        enabled = j.get("enabled") is not False
        state = j.get("state") or ("paused" if not enabled else "active")
        out.append({
            "id": j.get("id"),
            "name": j.get("name") or "(unnamed)",
            "schedule": sched,
            # `schedule_display` is the human-readable form Hermes itself uses
            # in `hermes cron list`; fall back to common keys if absent.
            "schedule_display": j.get("schedule_display")
                or sched.get("value") or sched.get("expr") or sched.get("kind") or "?",
            "prompt": j.get("prompt") or "",
            "deliver": deliver,
            "skills": j.get("skills") or ([j["skill"]] if j.get("skill") else []),
            "script": j.get("script") or None,
            "repeat": j.get("repeat") or None,
            "state": state,
            "enabled": enabled,
            "last_run_at": j.get("last_run_at"),
            "next_run_at": j.get("next_run_at"),
            "last_status": j.get("last_status"),
            "last_error": j.get("last_error"),
            "at_risk": at_risk,
        })
    return out


# --------------------------------------------------------------------------- #
# Hermes CLI mutations — DISABLED for now
#
# The full create/edit/pause/resume/run/remove + scripts surface was wired up
# (see git history on this branch) but is intentionally commented out below
# while the schedules page ships read-only. Re-enable by removing the
# `""" disabled""" ... """end-disabled"""` triple-quote markers and
# uncommenting the `import shutil` / `import subprocess` lines.
# --------------------------------------------------------------------------- #
# import shutil
# import subprocess


# DISABLED-MUTATIONS: def _find_hermes_cli() -> Optional[str]:
# DISABLED-MUTATIONS:     """Locate the `hermes` binary. PATH first, then a couple of known install spots."""
# DISABLED-MUTATIONS:     found = shutil.which("hermes")
# DISABLED-MUTATIONS:     if found:
# DISABLED-MUTATIONS:         return found
# DISABLED-MUTATIONS:     for candidate in (HOME / ".local" / "bin" / "hermes", HOME / ".hermes" / "bin" / "hermes"):
# DISABLED-MUTATIONS:         if candidate.exists():
# DISABLED-MUTATIONS:             return str(candidate)
# DISABLED-MUTATIONS:     return None


# DISABLED-MUTATIONS: def _run_hermes_cron(args: List[str]) -> Dict[str, Any]:
# DISABLED-MUTATIONS:     """Invoke `hermes cron <args>`. Returns {ok, output, error}."""
# DISABLED-MUTATIONS:     cli = _find_hermes_cli()
# DISABLED-MUTATIONS:     if not cli:
# DISABLED-MUTATIONS:         return {"ok": False, "output": "", "error": "hermes CLI not found in PATH"}
# DISABLED-MUTATIONS:     try:
# DISABLED-MUTATIONS:         # 15s timeout matches the desktop. `tick` can be long-running but we
# DISABLED-MUTATIONS:         # don't expose it here.
# DISABLED-MUTATIONS:         proc = subprocess.run(
# DISABLED-MUTATIONS:             [cli, "cron", *args],
# DISABLED-MUTATIONS:             capture_output=True, text=True, timeout=15,
# DISABLED-MUTATIONS:         )
# DISABLED-MUTATIONS:     except subprocess.TimeoutExpired:
# DISABLED-MUTATIONS:         return {"ok": False, "output": "", "error": "hermes cron timed out after 15s"}
# DISABLED-MUTATIONS:     except Exception as e:
# DISABLED-MUTATIONS:         return {"ok": False, "output": "", "error": str(e)}
# DISABLED-MUTATIONS:     if proc.returncode != 0:
# DISABLED-MUTATIONS:         return {"ok": False, "output": proc.stdout or "", "error": (proc.stderr or "").strip() or f"exit {proc.returncode}"}
# DISABLED-MUTATIONS:     # `hermes cron` exits 0 even on validation/lookup failures and prints
# DISABLED-MUTATIONS:     # "Failed to ..." to stdout. Treat that as the real error.
# DISABLED-MUTATIONS:     out = (proc.stdout or "").strip()
# DISABLED-MUTATIONS:     if out.startswith("Failed to"):
# DISABLED-MUTATIONS:         return {"ok": False, "output": out, "error": out}
# DISABLED-MUTATIONS:     return {"ok": True, "output": proc.stdout or "", "error": None}


# DISABLED-MUTATIONS: class CreateCronJobBody(BaseModel):
# DISABLED-MUTATIONS:     schedule: str  # "30m", "every 2h", "0 9 * * *", "daily 09:00", ...
# DISABLED-MUTATIONS:     prompt: Optional[str] = None
# DISABLED-MUTATIONS:     name: Optional[str] = None
# DISABLED-MUTATIONS:     deliver: Optional[str] = None
# DISABLED-MUTATIONS:     # Advanced — mirror the full `hermes cron create` surface.
# DISABLED-MUTATIONS:     skills: Optional[List[str]] = None         # repeated --skill
# DISABLED-MUTATIONS:     script: Optional[str] = None               # path relative to ~/.hermes/scripts/
# DISABLED-MUTATIONS:     no_agent: Optional[bool] = None            # --no-agent (watchdog mode)
# DISABLED-MUTATIONS:     repeat: Optional[int] = None               # --repeat N (None = forever)
# DISABLED-MUTATIONS:     workdir: Optional[str] = None              # absolute project path


# DISABLED-MUTATIONS: class EditCronJobBody(BaseModel):
# DISABLED-MUTATIONS:     """Edit fields. Any field set will be passed through; the rest are left alone.

# DISABLED-MUTATIONS:     Skills are *replaced* when `skills` is provided (mirrors `--skill` which
# DISABLED-MUTATIONS:     replaces). For incremental add/remove, callers can do their own diff and
# DISABLED-MUTATIONS:     invoke the dedicated endpoints later if needed.
# DISABLED-MUTATIONS:     """
# DISABLED-MUTATIONS:     schedule: Optional[str] = None
# DISABLED-MUTATIONS:     prompt: Optional[str] = None
# DISABLED-MUTATIONS:     name: Optional[str] = None
# DISABLED-MUTATIONS:     deliver: Optional[str] = None
# DISABLED-MUTATIONS:     skills: Optional[List[str]] = None
# DISABLED-MUTATIONS:     clear_skills: Optional[bool] = None        # --clear-skills
# DISABLED-MUTATIONS:     script: Optional[str] = None               # empty string clears
# DISABLED-MUTATIONS:     no_agent: Optional[bool] = None            # explicit True/False toggles; None leaves alone
# DISABLED-MUTATIONS:     repeat: Optional[int] = None
# DISABLED-MUTATIONS:     workdir: Optional[str] = None              # empty string clears


# DISABLED-MUTATIONS: def _common_create_edit_args(body, args: List[str]) -> None:
# DISABLED-MUTATIONS:     """Append `--skill`, `--script`, `--no-agent`, `--repeat`, `--workdir`
# DISABLED-MUTATIONS:     flags that are shared between create and edit. `body` is a pydantic model
# DISABLED-MUTATIONS:     with those optional fields."""
# DISABLED-MUTATIONS:     if body.skills:
# DISABLED-MUTATIONS:         for s in body.skills:
# DISABLED-MUTATIONS:             if s:
# DISABLED-MUTATIONS:                 args += ["--skill", s]
# DISABLED-MUTATIONS:     if body.script is not None:
# DISABLED-MUTATIONS:         args += ["--script", body.script]
# DISABLED-MUTATIONS:     if body.no_agent is True:
# DISABLED-MUTATIONS:         args += ["--no-agent"]
# DISABLED-MUTATIONS:     if body.repeat is not None:
# DISABLED-MUTATIONS:         args += ["--repeat", str(body.repeat)]
# DISABLED-MUTATIONS:     if body.workdir is not None:
# DISABLED-MUTATIONS:         args += ["--workdir", body.workdir]


# DISABLED-MUTATIONS: @app.post("/hermes/cron/jobs")
# DISABLED-MUTATIONS: async def create_cron_job(body: CreateCronJobBody):
# DISABLED-MUTATIONS:     from fastapi import HTTPException
# DISABLED-MUTATIONS:     if not body.schedule or not body.schedule.strip():
# DISABLED-MUTATIONS:         raise HTTPException(status_code=400, detail="schedule is required")
# DISABLED-MUTATIONS:     # Order matters: `hermes cron create` expects positionals (schedule, prompt)
# DISABLED-MUTATIONS:     # before flags. If a flag comes between them, the prompt bubbles up to the
# DISABLED-MUTATIONS:     # top-level parser and errors out as "unrecognized arguments".
# DISABLED-MUTATIONS:     args: List[str] = ["create", body.schedule]
# DISABLED-MUTATIONS:     if body.prompt:
# DISABLED-MUTATIONS:         args += [body.prompt]
# DISABLED-MUTATIONS:     if body.name:
# DISABLED-MUTATIONS:         args += ["--name", body.name]
# DISABLED-MUTATIONS:     if body.deliver:
# DISABLED-MUTATIONS:         args += ["--deliver", body.deliver]
# DISABLED-MUTATIONS:     _common_create_edit_args(body, args)
# DISABLED-MUTATIONS:     result = _run_hermes_cron(args)
# DISABLED-MUTATIONS:     if not result["ok"]:
# DISABLED-MUTATIONS:         raise HTTPException(status_code=502, detail=result["error"])
# DISABLED-MUTATIONS:     return {"ok": True, "output": result["output"]}


# DISABLED-MUTATIONS: @app.put("/hermes/cron/jobs/{job_id}")
# DISABLED-MUTATIONS: async def edit_cron_job(job_id: str, body: EditCronJobBody):
# DISABLED-MUTATIONS:     from fastapi import HTTPException
# DISABLED-MUTATIONS:     if not job_id:
# DISABLED-MUTATIONS:         raise HTTPException(status_code=400, detail="job id is required")
# DISABLED-MUTATIONS:     args: List[str] = ["edit", job_id]
# DISABLED-MUTATIONS:     if body.schedule is not None:
# DISABLED-MUTATIONS:         args += ["--schedule", body.schedule]
# DISABLED-MUTATIONS:     if body.prompt is not None:
# DISABLED-MUTATIONS:         args += ["--prompt", body.prompt]
# DISABLED-MUTATIONS:     if body.name is not None:
# DISABLED-MUTATIONS:         args += ["--name", body.name]
# DISABLED-MUTATIONS:     if body.deliver is not None:
# DISABLED-MUTATIONS:         args += ["--deliver", body.deliver]
# DISABLED-MUTATIONS:     if body.clear_skills:
# DISABLED-MUTATIONS:         args += ["--clear-skills"]
# DISABLED-MUTATIONS:     # --skill is "replace the set", which matches our edit-by-replace semantics.
# DISABLED-MUTATIONS:     if body.skills is not None and not body.clear_skills:
# DISABLED-MUTATIONS:         for s in body.skills:
# DISABLED-MUTATIONS:             if s:
# DISABLED-MUTATIONS:                 args += ["--skill", s]
# DISABLED-MUTATIONS:     if body.script is not None:
# DISABLED-MUTATIONS:         args += ["--script", body.script]
# DISABLED-MUTATIONS:     # On edit, `no_agent=True` enables, `False` disables (via --agent). None = leave alone.
# DISABLED-MUTATIONS:     if body.no_agent is True:
# DISABLED-MUTATIONS:         args += ["--no-agent"]
# DISABLED-MUTATIONS:     elif body.no_agent is False:
# DISABLED-MUTATIONS:         args += ["--agent"]
# DISABLED-MUTATIONS:     if body.repeat is not None:
# DISABLED-MUTATIONS:         args += ["--repeat", str(body.repeat)]
# DISABLED-MUTATIONS:     if body.workdir is not None:
# DISABLED-MUTATIONS:         args += ["--workdir", body.workdir]
# DISABLED-MUTATIONS:     result = _run_hermes_cron(args)
# DISABLED-MUTATIONS:     if not result["ok"]:
# DISABLED-MUTATIONS:         raise HTTPException(status_code=502, detail=result["error"])
# DISABLED-MUTATIONS:     return {"ok": True, "output": result["output"]}


# DISABLED-MUTATIONS: @app.get("/hermes/cron/scripts")
# DISABLED-MUTATIONS: async def list_cron_scripts():
# DISABLED-MUTATIONS:     """List user-defined scripts under ~/.hermes/scripts/ usable with --script.
# DISABLED-MUTATIONS:     Returns names relative to the scripts dir (Hermes resolves them itself)."""
# DISABLED-MUTATIONS:     scripts_dir = HERMES_DIR / "scripts"
# DISABLED-MUTATIONS:     if not scripts_dir.exists() or not scripts_dir.is_dir():
# DISABLED-MUTATIONS:         return {"scripts": []}
# DISABLED-MUTATIONS:     out: List[Dict[str, Any]] = []
# DISABLED-MUTATIONS:     for p in sorted(scripts_dir.iterdir()):
# DISABLED-MUTATIONS:         if not p.is_file():
# DISABLED-MUTATIONS:             continue
# DISABLED-MUTATIONS:         if p.name.startswith("."):
# DISABLED-MUTATIONS:             continue
# DISABLED-MUTATIONS:         out.append({
# DISABLED-MUTATIONS:             "name": p.name,
# DISABLED-MUTATIONS:             "size": p.stat().st_size,
# DISABLED-MUTATIONS:             # .sh/.bash run via bash per the CLI help; everything else via Python.
# DISABLED-MUTATIONS:             "kind": "bash" if p.suffix in (".sh", ".bash") else "python",
# DISABLED-MUTATIONS:         })
# DISABLED-MUTATIONS:     return {"scripts": out}


# DISABLED-MUTATIONS: def _cron_action(job_id: str, action: str) -> Dict[str, Any]:
# DISABLED-MUTATIONS:     from fastapi import HTTPException
# DISABLED-MUTATIONS:     if not job_id:
# DISABLED-MUTATIONS:         raise HTTPException(status_code=400, detail="job id is required")
# DISABLED-MUTATIONS:     result = _run_hermes_cron([action, job_id])
# DISABLED-MUTATIONS:     if not result["ok"]:
# DISABLED-MUTATIONS:         raise HTTPException(status_code=502, detail=result["error"])
# DISABLED-MUTATIONS:     return {"ok": True, "output": result["output"]}


# DISABLED-MUTATIONS: @app.delete("/hermes/cron/jobs/{job_id}")
# DISABLED-MUTATIONS: async def delete_cron_job(job_id: str):
# DISABLED-MUTATIONS:     return _cron_action(job_id, "remove")


# DISABLED-MUTATIONS: @app.post("/hermes/cron/jobs/{job_id}/pause")
# DISABLED-MUTATIONS: async def pause_cron_job(job_id: str):
# DISABLED-MUTATIONS:     return _cron_action(job_id, "pause")


# DISABLED-MUTATIONS: @app.post("/hermes/cron/jobs/{job_id}/resume")
# DISABLED-MUTATIONS: async def resume_cron_job(job_id: str):
# DISABLED-MUTATIONS:     return _cron_action(job_id, "resume")


# DISABLED-MUTATIONS: @app.post("/hermes/cron/jobs/{job_id}/run")
# DISABLED-MUTATIONS: async def trigger_cron_job(job_id: str):
# DISABLED-MUTATIONS:     return _cron_action(job_id, "run")


@app.get("/hermes/overview")
async def hermes_overview():
    """Lightweight Hermes-specific dashboard payload."""
    if not _hermes_dbs():
        return {"installed": False}
    return {
        "installed": True,
        "gateway": _hermes_gateway_state(),
        "cron_jobs": _hermes_cron_jobs(),
    }


@app.get("/hermes/telemetry")
async def hermes_telemetry():
    """Aggregate Hermes outcome / cost / latency / tool-reliability rollup.

    Every number is honest about its own provenance: cost carries the
    confidence bucket the dollar figure came from, latency separates sessions
    whose log lines still exist from those that rotated away, and an
    end_reason we don't recognise lands in `unknown` with its raw string
    intact rather than being counted as a completion.
    """
    if not _hermes_dbs():
        return {"available": False}
    sessions = [s for s in await get_sessions_cached() if s.get("agent") == "hermes"]
    index, files_read = _hermes_log_index_all()
    return _ht.build_telemetry(sessions, index, files_read)


_HERMES_SESSION_SORTS = {
    "newest", "oldest", "cost_desc", "cost_asc",
    "tokens_desc", "tokens_asc", "project", "model",
}

_HERMES_SESSION_PUBLIC_FIELDS = (
    "id", "agent", "project", "timestamp", "display", "text", "source_subtype",
    "model", "tokens", "cost", "cost_anomaly", "hermes_profile",
)


def _hermes_session_public_view(session: Dict[str, Any]) -> Dict[str, Any]:
    """Return only the session-list fields consumed by the Hermes explorer."""
    return {field: session[field] for field in _HERMES_SESSION_PUBLIC_FIELDS if field in session}


def _hermes_session_source(session: Dict[str, Any]) -> str:
    """Return the stable source label used by the Hermes explorer contract."""
    source = session.get("source_subtype") or session.get("source")
    return str(source or "unknown")


def _hermes_session_timestamp(session: Dict[str, Any]) -> datetime:
    timestamp = session.get("timestamp")
    if isinstance(timestamp, datetime):
        return _aware(timestamp)
    if isinstance(timestamp, str):
        try:
            return _aware(datetime.fromisoformat(timestamp.replace("Z", "+00:00")))
        except ValueError:
            pass
    return datetime.min.replace(tzinfo=timezone.utc)


def _hermes_session_number(session: Dict[str, Any], field: str) -> float:
    value = session.get(field)
    if field == "tokens":
        value = (session.get("tokens") or {}).get("total", 0)
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _hermes_session_matches(
    session: Dict[str, Any],
    *,
    search: Optional[str],
    project: Optional[str],
    source: Optional[str],
    model: Optional[str],
) -> bool:
    source_value = _hermes_session_source(session)
    searchable = " ".join(
        str(session.get(field) or "")
        for field in ("id", "display", "project", "model", "provider")
    ) + " " + source_value
    if search and search.casefold() not in searchable.casefold():
        return False
    for requested, actual in (
        (project, session.get("project")),
        (source, source_value),
        (model, session.get("model")),
    ):
        if requested and requested.casefold() not in str(actual or "").casefold():
            return False
    return True


def _hermes_session_sort_key(session: Dict[str, Any], sort: str):
    if sort in {"newest", "oldest"}:
        return (_hermes_session_timestamp(session), str(session.get("id") or ""))
    if sort in {"cost_desc", "cost_asc"}:
        return (_hermes_session_number(session, "cost"), str(session.get("id") or ""))
    if sort in {"tokens_desc", "tokens_asc"}:
        return (_hermes_session_number(session, "tokens"), str(session.get("id") or ""))
    if sort == "project":
        return (str(session.get("project") or "").casefold(), str(session.get("id") or ""))
    return (str(session.get("model") or "").casefold(), str(session.get("id") or ""))


@app.get("/hermes/sessions")
async def hermes_sessions(
    page: int = 1,
    page_size: int = 50,
    search: Optional[str] = None,
    project: Optional[str] = None,
    source: Optional[str] = None,
    model: Optional[str] = None,
    sort: str = "newest",
    fresh: bool = False,
):
    """Return a paginated, filterable Hermes session list.

    The endpoint deliberately reuses the canonical session scan, keeping its
    fields and timestamp/cost semantics aligned with ``/sessions``. Results
    are sorted deterministically, including the session id as a tie-breaker.
    """
    if page < 1:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="page must be at least 1")
    if page_size < 1 or page_size > 200:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="page_size must be between 1 and 200")
    if sort not in _HERMES_SESSION_SORTS:
        allowed = ", ".join(sorted(_HERMES_SESSION_SORTS))
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=f"sort must be one of: {allowed}")

    sessions = await get_sessions_cached(fresh=fresh)
    filtered = [
        session for session in sessions
        if session.get("agent") == "hermes"
        and _hermes_session_matches(
            session,
            search=search,
            project=project,
            source=source,
            model=model,
        )
    ]
    reverse = sort in {"newest", "cost_desc", "tokens_desc"}
    filtered.sort(key=lambda session: _hermes_session_sort_key(session, sort), reverse=reverse)

    total = len(filtered)
    start = (page - 1) * page_size
    page_sessions = filtered[start:start + page_size]
    total_pages = (total + page_size - 1) // page_size if total else 0
    public_sessions = []
    for session in page_sessions:
        public = _hermes_session_public_view(session)
        public.setdefault("source", _hermes_session_source(session))
        public_sessions.append(public)

    return {
        "sessions": public_sessions,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        },
    }


# --------------------------------------------------------------------------- #
# Update checker — compares local git HEAD to remote main, pulls curated
# highlights from UPDATE.json at the repo root. The "What's new" banner in
# the dashboard renders only when behind=true.
# --------------------------------------------------------------------------- #
import subprocess as _subprocess
import time as _upd_time
import urllib.request as _urlreq

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TT_HOME = data_dir()
_UPDATE_CACHE = _TT_HOME / ".update-check.json"
_REPO_OWNER = "VasiHemanth"
_REPO_NAME = "tokentelemetry"
_UPDATE_CACHE_TTL = 60 * 60       # 1 hour — quick enough that hotfixes
                                  # propagate same-day, infrequent enough to
                                  # not hammer GitHub on dashboard reloads.
_UPDATE_FETCH_TIMEOUT = 5         # seconds


def _local_commit() -> Optional[str]:
    """Current local commit. None if not a git checkout (zipball install)."""
    try:
        proc = _subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(_REPO_ROOT), capture_output=True, text=True, timeout=3,
        )
        if proc.returncode == 0:
            return proc.stdout.strip() or None
    except Exception:
        pass
    return None


def _looks_like_sha(s: Any) -> bool:
    """Real commit SHAs are 40 hex chars. Rejecting anything else guards
    against bogus dev-seeded cache values lingering on disk (e.g. literal
    "preview-local"), which would otherwise pin `behind=true` forever."""
    return isinstance(s, str) and len(s) == 40 and all(c in "0123456789abcdef" for c in s.lower())


def _read_cache() -> Optional[Dict[str, Any]]:
    if not _UPDATE_CACHE.exists():
        return None
    try:
        with open(_UPDATE_CACHE, "r", encoding="utf-8") as f:
            cached = json.load(f)
        if not isinstance(cached, dict):
            return None
        if not _looks_like_sha(cached.get("latest")):
            return None
        age = _upd_time.time() - float(cached.get("fetched_at", 0))
        # Reject both expired entries and future-dated ones (clock skew / DST):
        # a negative age would otherwise never expire.
        if age < 0 or age > _UPDATE_CACHE_TTL:
            return None
        return cached
    except Exception:
        return None


def _write_cache(payload: Dict[str, Any]) -> None:
    try:
        _TT_HOME.mkdir(parents=True, exist_ok=True)
        payload = {**payload, "fetched_at": _upd_time.time()}
        # Atomic write: serialize to a temp file then os.replace, so a concurrent
        # reader (the dashboard can fire several /version calls at once) never
        # observes a torn/half-written file.
        tmp = _UPDATE_CACHE.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.replace(tmp, _UPDATE_CACHE)
    except Exception:
        pass


def _fetch_remote() -> Optional[Dict[str, Any]]:
    """Hit GitHub for (a) latest commit on main, (b) curated UPDATE.json.
    Returns None on any network error — caller falls back to cache."""
    sha_url = f"https://api.github.com/repos/{_REPO_OWNER}/{_REPO_NAME}/commits/main"
    update_url = f"https://raw.githubusercontent.com/{_REPO_OWNER}/{_REPO_NAME}/main/UPDATE.json"
    try:
        req = _urlreq.Request(sha_url, headers={"User-Agent": "tokentelemetry-update-check"})
        with _urlreq.urlopen(req, timeout=_UPDATE_FETCH_TIMEOUT) as r:
            sha_data = json.loads(r.read().decode("utf-8"))
        latest_sha = sha_data.get("sha")
        # Validate on the fetch path too (the cache read already does). A bogus
        # non-40-hex value would otherwise be cached, then rejected on the next
        # read by _looks_like_sha → a fetch-every-call loop + a false `behind`.
        if not _looks_like_sha(latest_sha):
            return None
    except Exception:
        return None

    # Two supported shapes:
    #   - new style: {"releases": [{tag, title, highlights:[...]}, ...]}
    #   - legacy:    {"highlights": [...]} (one flat list — auto-wrapped into
    #                  a single synthetic release)
    # Inside `highlights`, items can be strings or {title, description, href}.
    # Normalize everything to a `releases` array so the frontend has one shape.
    releases: List[Dict[str, Any]] = []
    release_url = f"https://github.com/{_REPO_OWNER}/{_REPO_NAME}/commits/main"

    def _norm_hl(items) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for h in (items or [])[:5]:  # cap per release so noisy ones stay readable
            if isinstance(h, str) and h.strip():
                out.append({"title": h.strip(), "description": None, "href": None})
            elif isinstance(h, dict) and h.get("title"):
                out.append({
                    "title": str(h["title"]).strip(),
                    "description": (str(h["description"]).strip() if h.get("description") else None),
                    "href": (str(h["href"]).strip() if h.get("href") else None),
                })
        return out

    try:
        req2 = _urlreq.Request(update_url, headers={"User-Agent": "tokentelemetry-update-check"})
        with _urlreq.urlopen(req2, timeout=_UPDATE_FETCH_TIMEOUT) as r:
            upd = json.loads(r.read().decode("utf-8"))

        if isinstance(upd.get("releases"), list):
            for r in upd["releases"][:6]:  # show up to 6 prior releases
                if not isinstance(r, dict):
                    continue
                hls = _norm_hl(r.get("highlights"))
                if not hls and not r.get("title"):
                    continue
                releases.append({
                    "tag": (str(r["tag"]).strip() if r.get("tag") else None),
                    "title": (str(r["title"]).strip() if r.get("title") else None),
                    "highlights": hls,
                })
        elif upd.get("highlights"):
            # Legacy flat shape — wrap into one synthetic release.
            releases.append({"tag": None, "title": None, "highlights": _norm_hl(upd["highlights"])})

        release_url = upd.get("release_url") or release_url
    except Exception:
        # UPDATE.json missing or malformed: still report the commit diff.
        pass

    return {"latest": latest_sha, "releases": releases, "release_url": release_url}


def _is_behind(latest: Optional[str], current: Optional[str]) -> bool:
    """True only when the local checkout genuinely lacks `latest`.

    A plain `latest != current` can't tell "behind" from "ahead" — so anyone
    running the dashboard from a feature branch (or just after merging) saw a
    false "Update available". Instead: if `latest` is an ANCESTOR of local HEAD,
    we already contain it → not behind. This also clears the stale-cache case:
    right after `git pull`, the cached older `latest` is an ancestor of the new
    HEAD, so the banner stops nagging immediately.

    Falls back to inequality only when `latest` isn't in the local object store
    (e.g. on `main`, behind, and not yet fetched) — the genuinely-behind case.
    """
    if not latest or not current:
        return False
    if latest == current:
        return False
    try:
        proc = _subprocess.run(
            ["git", "merge-base", "--is-ancestor", latest, "HEAD"],
            cwd=str(_REPO_ROOT), capture_output=True, text=True, timeout=3,
        )
        if proc.returncode == 0:
            return False  # latest is reachable from HEAD → already have it
        if proc.returncode == 1:
            return True   # known locally but not an ancestor → behind/diverged
    except Exception:
        pass
    # rc 128 (unknown rev — not fetched) or git error → assume there's a commit
    # on main we don't have.
    return latest != current


def _release_id(releases: List[Dict[str, Any]], fallback: Optional[str]) -> Optional[str]:
    """Stable identity for the newest curated release, used to decide whether the
    banner has new *feature* content to show (UPDATE.json only gains an entry on
    feat: pushes — see CLAUDE.md). Keyed on tag|title so a fix:/chore: commit,
    which doesn't touch UPDATE.json, never re-surfaces the banner. Untagged/legacy
    feeds fall back to the commit SHA (prior behaviour)."""
    if not releases:
        return None
    top = releases[0]
    rid = "|".join(p for p in [top.get("tag"), top.get("title")] if p)
    return rid or fallback

def _update_check_enabled() -> bool:
    """Whether the dashboard may contact GitHub for version/release info.

    Two ways to turn it off, env var taking precedence so ops/enterprise can
    enforce it regardless of the in-app setting:
      - TT_NO_UPDATE_CHECK=1 (env) — hard off, not user-overridable; and
      - the `update_check` preference (Settings toggle), default on.
    This is the *only* outbound network call the app makes; it sends no logs,
    sessions, or usage data — just a version/UPDATE.json fetch."""
    if os.environ.get("TT_NO_UPDATE_CHECK"):
        return False
    return bool(load_preferences().get("update_check", True))


@app.get("/version")
async def get_version():
    """Banner data: how far behind the local checkout is + 1-3 curated bullets
    about what's in the update. Disable via the Settings toggle or, to enforce
    it for everyone, TT_NO_UPDATE_CHECK=1."""
    current = _local_commit()
    base: Dict[str, Any] = {
        "current": current,
        "latest": None,
        "behind": False,
        "releases": [],
        "latest_release": None,
        "release_url": f"https://github.com/{_REPO_OWNER}/{_REPO_NAME}",
        "source": "none",
        "repo": f"{_REPO_OWNER}/{_REPO_NAME}",
    }
    if not _update_check_enabled():
        base["source"] = "disabled"
        return base
    if not current:
        # Not a git checkout — nothing to compare against.
        return base

    cached = _read_cache()
    remote = cached if cached else _fetch_remote()
    if remote is None:
        base["source"] = "offline"
        return base
    if not cached:
        _write_cache(remote)

    latest = remote.get("latest")
    base["latest"] = latest
    # Tolerate both old-cache (highlights) and new-cache (releases) entries.
    if remote.get("releases"):
        base["releases"] = remote["releases"]
    elif remote.get("highlights"):
        base["releases"] = [{"tag": None, "title": None, "highlights": remote["highlights"]}]
    base["release_url"] = remote.get("release_url") or base["release_url"]
    base["behind"] = _is_behind(latest, current)
    base["latest_release"] = _release_id(base["releases"], latest)
    base["source"] = "cache" if cached else "github"
    return base


@app.get("/")
async def root():
    return {"message": "TokenTelemetry API is running"}

def _list_available_agents() -> list:
    agents = []
    if CLAUDE_DIR.exists(): agents.append("claude")
    if CODEX_DIR.exists(): agents.append("codex")
    if GEMINI_DIR.exists(): 
        agents.append("gemini")
        if (GEMINI_DIR / "antigravity").exists() or list((GEMINI_DIR / "tmp").glob("*")):
            agents.append("antigravity")
    if QWEN_DIR.exists(): agents.append("qwen")
    if VIBE_DIR.exists(): agents.append("vibe")
    if CURSOR_DIR.exists(): agents.append("cursor")
    if VSCODE_STORAGE.exists() or COPILOT_CLI_DIR.exists(): agents.append("copilot")
    if OPENCODE_DB.exists(): agents.append("opencode")
    if _hermes_dbs(): agents.append("hermes")
    if GROK_SESSIONS_DIR.exists(): agents.append("grok")
    if PI_SESSIONS_DIR.exists(): agents.append("pi")
    if (CLINE_DIR / "data" / "db" / "sessions.db").exists() or (CLINE_VSCODE_DIR / "state" / "taskHistory.json").exists():
        agents.append("cline")
    if MUSE_SESSIONS_DIR.is_dir(): agents.append("muse")
    if PRIME_SESSIONS_DIR.is_dir(): agents.append("prime")
    if DSH_DIR.exists(): agents.append("dsh")
    # projects/, not the root: Qoder's installer creates ~/.qoder before the
    # first session exists, so the root alone would advertise an empty agent.
    if QODER_PROJECTS_DIR.is_dir(): agents.append("qoder")
    # SmallCode traces are project-local; cheaply check only the explicitly
    # configured extra roots here (the full project-derived root set is only
    # known after _scan_sessions_sync runs the other scanners).
    if any((Path(r).expanduser() / ".smallcode" / "traces").is_dir() for r in SMALLCODE_EXTRA_ROOTS):
        agents.append("smallcode")
    # if OLLAMA_DIR.exists(): agents.append("ollama")
    return agents


@app.get("/agents")
async def get_available_agents():
    return _list_available_agents()


@app.get("/agents/panels")
async def get_agent_panel_summary():
    """How many harness panels sit behind each agent tile.

    Lets the dashboard link only the agents that have something to show, and put
    a "6 panels" hint on the tile, without fetching every panel up front.
    """
    return harness_panels.panel_summary()


@app.get("/agents/{agent}/panel")
async def get_agent_panel(agent: str, fresh: bool = False):
    """Everything THIS agent keeps on disk that the session scan doesn't show.

    Codex's cron schedules, Claude's background-job fleet and subscription
    quota, Copilot's premium-request billing units, Grok's credit balance — each
    harness stores something the others don't, and none of it reaches the
    dashboard today.

    Built lazily on request (never during the session scan) and cached briefly,
    because sizing a harness directory means walking up to ~180k files. Read-only
    throughout: no credential values are read and no prompt or file content is
    returned. An agent with no extractor reports `installed: false` with
    `planned: true`, which the frontend renders as an inert tile rather than an
    empty page.
    """
    return harness_panels.build_panel(agent, fresh=fresh)

# @app.get("/local-runtime")
# async def get_local_runtime():
#     import httpx
#     status = {"ollama": "offline", "models": [], "hf_usage": "0GB"}
#     try:
#         async with httpx.AsyncClient() as client:
#             resp = await client.get("http://localhost:11434/api/tags", timeout=1.0)
#             if resp.status_code == 200:
#                 status["ollama"] = "online"
#                 status["models"] = resp.json().get("models", [])
#     except: pass
#     if HF_DIR.exists():
#         try:
#             total_size = sum(f.stat().st_size for f in HF_DIR.rglob('*') if f.is_file())
#             status["hf_usage"] = f"{total_size / (1024**3):.1f}GB"
#         except: pass
#     return status


# Grok Build recurring loop ("Grok Tasks" / the `/loop <interval> <prompt>`
# command). A firing re-injects the prompt into the SAME session, tagged in
# chat_history.jsonl with synthetic_reason="scheduler_fired" and a reminder of
# the form: "scheduled task execution (task <id>, every <interval>, recurring)".
# This is the Grok analog of Claude's CronCreate/ScheduleWakeup loop.
_GROK_LOOP_RE = re.compile(
    r"scheduled task execution \(task\s+([0-9a-fA-F]+),\s*([^,]+?),\s*(recurring|once)\)",
    re.IGNORECASE,
)


def _grok_interval_to_seconds(text: Optional[str]) -> Optional[int]:
    """Parse a Grok scheduler interval to seconds.

    Handles both the expanded reminder form ("every 2 hours", "30 minutes",
    "45 seconds", "1 day") and Grok's compact input grammar ("2h", "5m", "60s",
    "1d"). Returns None when unparseable so lifecycle falls back to defaults.
    """
    if not text:
        return None
    t = text.strip().lower()
    if t.startswith("every"):
        t = t[len("every"):].strip()
    m = re.fullmatch(r"(\d+)\s*([smhd])", t)
    if m:
        return int(m.group(1)) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2)]
    m = re.fullmatch(r"(\d+)\s*(second|minute|hour|day)s?", t)
    if m:
        return int(m.group(1)) * {"second": 1, "minute": 60, "hour": 3600, "day": 86400}[m.group(2)]
    return None


def _grok_record_text(rec: Dict[str, Any]) -> str:
    """Flatten a Grok chat_history.jsonl record's content to plain text."""
    c = rec.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(
            b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def _grok_strip_reminder(text: str) -> str:
    """Strip the <user_query>/<system-reminder> scheduler wrapper, leaving the
    actual prompt the loop runs each fire."""
    t = re.sub(r"<system-reminder>.*?</system-reminder>", "", text, flags=re.DOTALL)
    t = t.replace("<user_query>", "").replace("</user_query>", "")
    return t.strip()


def _grok_loop_detect(
    sess_dir: Path, tools_used: List[str], created_iso: Optional[str], updated_iso: Optional[str]
) -> Optional[Dict[str, Any]]:
    """Detect a Grok Build recurring scheduler loop for one session.

    Gated on `scheduler_create` appearing in signals.toolsUsed (cheap — already
    loaded) so the fuller chat_history/events scan only runs for the rare
    session that actually set up a loop. Recurrence signature: scheduler_fired
    records in chat_history.jsonl whose reminder text names the task id +
    interval + "recurring". created_at and cancellation come from the
    timestamped scheduler_create / scheduler_delete events in events.jsonl.

    Grok exposes only a session-level context-token total (no per-turn split),
    so a per-fire footprint isn't computable — footprint_tokens/cost are 0 and
    the loop surfaces its cadence + fire count without a fabricated cost.
    Requires at least one firing (that's where the task id + interval live); a
    created-but-never-fired Grok task isn't detected.
    """
    if "scheduler_create" not in (tools_used or []):
        return None
    chat_path = sess_dir / GROK_CHAT_HISTORY
    if not chat_path.exists():
        return None

    task_id: Optional[str] = None
    interval_text: Optional[str] = None
    prompt_preview: Optional[str] = None
    iterations = 0
    try:
        with open(chat_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "scheduler_fired" not in line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("synthetic_reason") != "scheduler_fired":
                    continue
                text = _grok_record_text(rec)
                m = _GROK_LOOP_RE.search(text or "")
                if not m or m.group(3).lower() != "recurring":
                    continue
                iterations += 1
                if task_id is None:
                    task_id = m.group(1)
                    interval_text = (m.group(2) or "").strip()
                    prompt_preview = _grok_strip_reminder(text)
    except Exception:
        return None

    if iterations == 0 or not task_id:
        return None

    # created_at + cancellation from the timestamped scheduler_* tool events.
    created_at: Optional[str] = None
    cancelled = False
    cancelled_at: Optional[str] = None
    events_path = sess_dir / GROK_EVENTS
    if events_path.exists():
        try:
            with open(events_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "scheduler_" not in line:
                        continue
                    try:
                        ev = json.loads(line)
                    except Exception:
                        continue
                    name = ev.get("tool_name")
                    ets = ev.get("ts")
                    if name == "scheduler_create" and created_at is None:
                        created_at = ets
                    elif (name == "scheduler_delete" and ev.get("type") == "tool_completed"
                          and ev.get("outcome") == "success"):
                        cancelled = True
                        cancelled_at = ets
        except Exception:
            pass

    # Scope the cancellation by TIMING, not by task id: Grok's scheduler_delete
    # tool_completed record carries no task id ({ts, type, tool_name, duration_ms,
    # outcome}), so a delete can't be matched to the task it targeted. A session
    # may create/delete several tasks over its life; a delete that happened at or
    # before this loop's most recent firing cannot have cancelled a task that is
    # still firing. Keep cancelled=True only if the delete strictly post-dates the
    # last fire (updated_iso ≈ last activity ≈ last fire). If either timestamp is
    # missing or unparseable, treat as NOT cancelled — a live-firing loop is the
    # safer default than a false "cancelled".
    if cancelled and cancelled_at:
        try:
            del_dt = _aware(datetime.fromisoformat(str(cancelled_at).replace("Z", "+00:00")))
            fire_dt = _aware(datetime.fromisoformat(str(updated_iso).replace("Z", "+00:00")))
            if not (del_dt > fire_dt):
                cancelled = False
                cancelled_at = None
        except Exception:
            cancelled = False
            cancelled_at = None
    elif cancelled:
        # cancelled flagged but no timestamp to validate against -> be conservative.
        cancelled = False
        cancelled_at = None

    return {
        "is_loop": True,
        "mode": "scheduler",                 # Grok Tasks scheduler (fixed interval)
        "cadence": interval_text or "",
        "cadence_seconds": _grok_interval_to_seconds(interval_text),
        "recurring": True,
        "job_id": task_id,
        "source_signal": "grok_scheduler",
        "prompt_preview": (prompt_preview or "")[:160],
        "created_at": created_at or created_iso,
        "last_fired": updated_iso,           # grok fires carry no per-record ts; session's last activity ≈ last fire
        "iterations": iterations,
        "cancelled": cancelled,
        "cancelled_at": cancelled_at,
        "footprint_tokens": 0,               # grok has no per-turn token split
        "footprint_cost": 0,
    }


# Cached parse of ~/.grok/logs/unified.jsonl. Keyed by (resolved path, mtime, size)
# so a dashboard refresh does not re-read a multi-MB JSONL unless it changed.
_GROK_LOG_CACHE: Dict[str, Any] = {"key": None, "data": {}}


def _grok_usage_from_unified_log(path: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """Aggregate billed usage from Grok's unified inference log.

    Each ``shell.turn.inference_done`` row is one request:
      input  = prompt_tokens − cached_prompt_tokens
      cached = cached_prompt_tokens
      output = completion_tokens
    Turns retain their log timestamp so cost can apply both xAI's per-request
    200k long-context 2× and any price cutover that occurs mid-session.
    Missing / unreadable log → {}.
    """
    log_path = path if path is not None else GROK_UNIFIED_LOG
    if not log_path.exists() or not log_path.is_file():
        return {}
    try:
        st = log_path.stat()
        cache_key = (str(log_path.resolve()), st.st_mtime_ns, st.st_size)
    except OSError:
        return {}
    if _GROK_LOG_CACHE.get("key") == cache_key:
        return _GROK_LOG_CACHE["data"]

    by_sid: Dict[str, Dict[str, Any]] = {}
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "inference_done" not in line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("msg") != "shell.turn.inference_done":
                    continue
                sid = rec.get("sid")
                if not sid:
                    continue
                ctx = rec.get("ctx") or {}
                try:
                    prompt = int(ctx.get("prompt_tokens") or 0)
                    cached = int(ctx.get("cached_prompt_tokens") or 0)
                    completion = int(ctx.get("completion_tokens") or 0)
                    reasoning = int(ctx.get("reasoning_tokens") or 0)
                except (TypeError, ValueError):
                    continue
                if prompt < 0 or cached < 0 or completion < 0:
                    continue
                cached = min(cached, prompt)
                turn_ts = rec.get("ts")
                if not isinstance(turn_ts, str):
                    turn_ts = None
                else:
                    try:
                        datetime.fromisoformat(turn_ts.replace("Z", "+00:00"))
                    except ValueError:
                        turn_ts = None
                row = by_sid.get(sid)
                if row is None:
                    row = {
                        "input": 0,
                        "output": 0,
                        "cached": 0,
                        "reasoning": 0,
                        "turns": [],
                    }
                    by_sid[sid] = row
                row["input"] += prompt - cached
                row["output"] += completion
                row["cached"] += cached
                row["reasoning"] += max(reasoning, 0)
                row["turns"].append((prompt, cached, completion, turn_ts))
    except OSError:
        return {}

    _GROK_LOG_CACHE["key"] = cache_key
    _GROK_LOG_CACHE["data"] = by_sid
    return by_sid


def _grok_price_turns(model: str, turns, at=None) -> float:
    """Sum per-request xAI cost, using each log timestamp when it exists."""
    from pricing import calculate_xai_turn_cost
    total = 0.0
    for turn in turns:
        prompt, cached, completion = turn[:3]
        turn_at = turn[3] if len(turn) > 3 and turn[3] else at
        total += calculate_xai_turn_cost(model, prompt, completion, cached, at=turn_at)
    return total


def _scan_grok_sessions() -> List[Dict[str, Any]]:
    """Scan Grok Build sessions under ~/.grok/sessions/.

    Produces the standard TokenTelemetry session record with rich Grok-specific forensics.
    Prefers billed usage from ``unified.jsonl`` when the session appears there;
    otherwise falls back to the context-window footprint (output/cached n/a).
    """
    if not GROK_SESSIONS_DIR.exists():
        return []

    usage_by_sid = _grok_usage_from_unified_log()

    # Load aliases locally so this top-level function doesn't depend on closures inside _scan_sessions_sync
    aliases = _load_project_aliases()
    def _apply_alias(p: str) -> str:
        return aliases.get(p, p)

    out: List[Dict[str, Any]] = []

    for proj_bucket in GROK_SESSIONS_DIR.iterdir():
        if not proj_bucket.is_dir():
            continue

        try:
            from urllib.parse import unquote
            cwd = unquote(proj_bucket.name)
        except Exception:
            cwd = proj_bucket.name

        for sess_id_dir in proj_bucket.iterdir():
            if not sess_id_dir.is_dir():
                continue
            sid = sess_id_dir.name

            summary_path = sess_id_dir / GROK_SUMMARY
            if not summary_path.exists():
                continue

            try:
                with open(summary_path, "r", encoding="utf-8") as f:
                    summary = json.load(f)
            except Exception:
                continue

            info = summary.get("info", {}) or {}
            project_path = _apply_alias(info.get("cwd") or cwd or "unknown")

            created = summary.get("created_at")
            updated = summary.get("updated_at") or created
            try:
                ts = datetime.fromisoformat((updated or created).replace("Z", "+00:00"))
            except Exception:
                ts = _file_mtime_utc(summary_path)

            title = summary.get("generated_title") or summary.get("session_summary") or f"Grok session {sid[:8]}"
            display = title[:120]
            model = summary.get("current_model_id") or "grok-build"

            # Load signals.json — Grok's rich, accurate per-session metrics file.
            signals: Dict[str, Any] = {}
            signals_path = sess_id_dir / GROK_SIGNALS
            if signals_path.exists():
                try:
                    with open(signals_path, "r", encoding="utf-8") as f:
                        signals = json.load(f) or {}
                except Exception:
                    signals = {}

            # Resolve the model BEFORE pricing. signals.modelsUsed is the
            # fallback when summary.json carries no current_model_id; leaving
            # this below the token block meant a session could be priced as
            # "grok-build" while displaying the model it actually ran.
            models_used = signals.get("modelsUsed")
            if isinstance(models_used, list) and models_used:
                model = summary.get("current_model_id") or models_used[0] or model

            # Token forensics. Prefer billed per-turn usage from unified.jsonl.
            # Session files only record contextTokensUsed (current window
            # footprint) — that is not a prompt/completion split and must not
            # be shown as billed Input when the log has the real numbers.
            tokens = {"input": 0, "output": 0, "cached": 0, "total": 0, "source": "context"}
            usage = usage_by_sid.get(sid)
            if usage and usage.get("turns"):
                tokens["input"] = usage["input"]
                tokens["output"] = usage["output"]
                tokens["cached"] = usage["cached"]
                tokens["total"] = usage["input"] + usage["output"] + usage["cached"]
                tokens["source"] = "usage"
                tokens["cost"] = _grok_price_turns(model, usage["turns"], at=ts)
            else:
                ctx_used = signals.get("contextTokensUsed")
                if isinstance(ctx_used, (int, float)) and ctx_used > 0:
                    total = int(ctx_used)
                else:
                    # Fallback only when signals lacks a usable figure: scan the (large)
                    # updates.jsonl for the max cumulative totalTokens. Skipped entirely
                    # in the common case so the list scan stays cheap.
                    max_total = 0
                    updates_path = sess_id_dir / GROK_UPDATES
                    if updates_path.exists():
                        try:
                            with open(updates_path, "r", encoding="utf-8", errors="ignore") as f:
                                for line in f:
                                    if "totalTokens" not in line:
                                        continue
                                    try:
                                        u = json.loads(line)
                                        meta = (u.get("params") or {}).get("_meta") or {}
                                        val = meta.get("totalTokens")
                                        if isinstance(val, (int, float)) and val > max_total:
                                            max_total = int(val)
                                    except Exception:
                                        continue
                        except Exception:
                            pass
                    total = max_total

                # No billed split on disk: attribute the window footprint to
                # input and leave output/cached at 0. Frontend renders those
                # as "—" when source == "context". Cost is a lower bound.
                tokens["total"] = total
                tokens["input"] = total
                tokens["output"] = 0
                tokens["cached"] = 0
                tokens["source"] = "context"
                tokens["cost"] = calculate_cost(model, tokens.get("input", 0), tokens.get("output", 0), tokens.get("cached", 0), at=ts)

            # Tool names — prefer signals.toolsUsed (accurate, deduped) and avoid the
            # redundant full events.jsonl scan when it's available.
            mcp_tools: List[str] = []
            tools_used = signals.get("toolsUsed")
            if isinstance(tools_used, list) and tools_used:
                mcp_tools = [t for t in tools_used if t]
            else:
                events_path = sess_id_dir / GROK_EVENTS
                if events_path.exists():
                    try:
                        with open(events_path, "r", encoding="utf-8", errors="ignore") as f:
                            for line in f:
                                try:
                                    ev = json.loads(line)
                                except Exception:
                                    continue
                                t = ev.get("type")
                                if t in ("tool_started", "tool_completed"):
                                    name = ev.get("tool_name")
                                    if name and name not in mcp_tools:
                                        mcp_tools.append(name)
                    except Exception:
                        pass

            # Plan mode
            has_plan = False
            plans: List[Dict[str, Any]] = []
            plan_path = sess_id_dir / GROK_PLAN_MODE
            if plan_path.exists():
                try:
                    with open(plan_path, "r", encoding="utf-8") as f:
                        pm = json.load(f)
                    if pm.get("state") == "Active" or pm.get("was_previously_active"):
                        has_plan = True
                        plans.append({
                            "session_id": sid,
                            "agent": "grok",
                            "timestamp": ts,
                            "content": f"Plan mode was active (state={pm.get('state')})"
                        })
                except Exception:
                    pass

            artifacts: List[Dict[str, Any]] = []
            if plan_path.exists():
                artifacts.append({"name": "plan_mode.json", "path": str(plan_path), "type": "document"})
            artifacts.append({"name": "summary.json", "path": str(summary_path), "type": "document"})

            git_info = {
                "root": summary.get("git_root_dir"),
                "branch": summary.get("head_branch"),
                "commit": summary.get("head_commit"),
            }

            # Subagent spawns: Grok writes <session>/subagents/<id>/meta.json with
            # {subagent_type, description, status, duration_ms, tool_calls, turns,
            #  parent_session_id, child_session_id}. The child runs as its OWN
            # session dir (already counted above/below) — annotation only.
            grok_spawns = _grok_subagent_meta(sess_id_dir)

            sess = {
                "id": sid,
                "agent": "grok",
                "project": project_path,
                "timestamp": ts,
                "display": display,
                "text": summary.get("session_summary"),
                "tokens": tokens,
                "mcp_tools": mcp_tools,
                "has_plan": has_plan,
                "plans": plans,
                "model": model,
                "artifacts": artifacts,
                "cost": tokens.get("cost", 0.0),
                "grok": {
                    "cwd": info.get("cwd"),
                    "git": git_info,
                    "num_messages": summary.get("num_messages"),
                    "num_chat_messages": summary.get("num_chat_messages"),
                    "agent_name": summary.get("agent_name"),
                    "last_active_at": summary.get("last_active_at"),
                },
            }
            # Recurring loop (/loop / Grok Tasks scheduler). Gated on
            # scheduler_create in signals.toolsUsed so the deeper scan is skipped
            # for the vast majority of sessions.
            loop = _grok_loop_detect(
                sess_id_dir,
                tools_used if isinstance(tools_used, list) else [],
                created, updated,
            )
            if loop:
                sess["loop"] = loop

            goal = _grok_goal_detect(
                sess_id_dir,
                tools_used if isinstance(tools_used, list) else [],
                created, updated,
            )
            if goal:
                sess["goals"] = [goal]

            if grok_spawns:
                by_type: Dict[str, Dict[str, Any]] = {}
                for sp in grok_spawns:
                    bt = by_type.setdefault(sp.get("agent_type") or "unknown",
                                            {"count": 0, "child_session_ids": []})
                    bt["count"] += 1
                    # Child ids let /analytics attribute each child session's
                    # (already-counted) tokens to its subagent type.
                    if sp.get("child_session_id"):
                        bt["child_session_ids"].append(sp["child_session_id"])
                sess["delegation"] = {"supported": True, "tokens_recorded": False,
                                      "spawn_count": len(grok_spawns),
                                      "by_type": by_type}
                sess["child_session_ids"] = [sp["child_session_id"] for sp in grok_spawns
                                             if sp.get("child_session_id")]
            out.append(sess)

    # Children are full sessions in the same bucket — annotate them with their
    # parent (count-once: their tokens already stand on their own).
    grok_by_id = {s["id"]: s for s in out}
    for s in out:
        for cid in s.get("child_session_ids") or []:
            child = grok_by_id.get(cid)
            if child is not None:
                child["parent_session_id"] = s["id"]
    return out


def _grok_goal_detect(sess_dir: Path, tools_used: List[str],
                      created: Optional[str], updated: Optional[str]) -> Optional[Dict[str, Any]]:
    """Detect Grok Build's autonomous goal from `update_goal` tool calls.

    Grok reports progress through an `update_goal` tool rather than a stop
    condition, so the evidence is a stream of checkpoints, the last of which may
    carry `completed: true`.

    Two things this refuses to claim, both established from local data:

    - **The objective is not recoverable.** All 25 local sessions using
      `update_goal` did so with no `/goal` user message anywhere, i.e. the tool
      was in the toolset and the model drove it from skill instructions. So we
      surface the latest progress message and leave `objective` null rather than
      passing a status line off as the user's objective.
    - **No completion flag does not mean "still running".** A finished session
      that never reported `completed` is genuinely unknown, so it gets
      "unknown", not "active".

    Gated on `update_goal` appearing in signals.toolsUsed, so the file read is
    skipped for the overwhelming majority of sessions.
    """
    if "update_goal" not in (tools_used or []):
        return None
    path = sess_dir / GROK_CHAT_HISTORY
    checkpoints: List[str] = []
    completed = False
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if "update_goal" not in line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                for tc in rec.get("tool_calls") or []:
                    if not isinstance(tc, dict):
                        continue
                    name = tc.get("name") or (tc.get("function") or {}).get("name")
                    if name != "update_goal":
                        continue
                    args = tc.get("arguments")
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            args = {}
                    if not isinstance(args, dict):
                        continue
                    msg = str(args.get("message") or "").strip()
                    if msg:
                        checkpoints.append(msg)
                    if args.get("completed") is True:
                        completed = True
    except OSError:
        return None
    if not checkpoints and not completed:
        return None
    return {
        "source": "grok",
        "goal_id": None,
        "objective": None,
        "objective_truncated": False,
        "created_at": created,
        "updated_at": updated,
        "state": "complete" if completed else "unknown",
        "state_source": "inferred",
        # Checkpoints carry no timestamps and no token accounting, so there is
        # no per-goal boundary to cost. The session IS the goal here.
        "tokens": None,
        "duration_seconds": None,
        "token_budget": None,
        "cost_basis": "session",
        "evidence": {
            "checkpoints": len(checkpoints),
            "completed": completed,
            "latest_message": checkpoints[-1][:codex_goals.OBJECTIVE_MAX] if checkpoints else None,
            "objective_recoverable": False,
        },
    }


def _antigravity_goal_detect(transcript: Path) -> List[Dict[str, Any]]:
    """Detect Antigravity `/goal` markers.

    Antigravity's `/goal` is a prompt marker, not machinery: the request arrives
    wrapped as `<USER_REQUEST>/goal <text>/goal</USER_REQUEST>` and the agent's
    context explains it as work "intended to run for a long time without user
    input". There is no status and no completion signal, so every one of these
    is `unknown` by construction — but unlike Grok, the objective IS the marker
    text, so it can be shown.
    """
    out: List[Dict[str, Any]] = []
    seen: set = set()
    try:
        with open(transcript, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if "/goal" not in line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                blob = json.dumps(rec)
                for m in _ANTIGRAVITY_GOAL_RE.finditer(blob):
                    text = m.group(1).replace("\\n", " ").replace('\\"', '"').strip()
                    text = text.split("/goal")[0].strip()
                    key = text[:80]
                    if not text or key in seen:
                        continue
                    seen.add(key)
                    out.append({
                        "source": "antigravity",
                        "goal_id": None,
                        "objective": text[:codex_goals.OBJECTIVE_MAX],
                        "objective_truncated": len(text) > codex_goals.OBJECTIVE_MAX,
                        "created_at": rec.get("timestamp") or rec.get("ts"),
                        "updated_at": None,
                        "state": "unknown",
                        "state_source": "inferred",
                        "tokens": None,
                        "duration_seconds": None,
                        "token_budget": None,
                        "cost_basis": "session",
                        "evidence": {"marker_only": True},
                    })
    except OSError:
        return []
    return out


def _grok_subagent_meta(sess_dir: Path) -> List[Dict[str, Any]]:
    """Read Grok Build subagent spawn records for one session.

    Verified shape (grok 0.2.39): <session>/subagents/<spawn-id>/meta.json with
    subagent_type, description, prompt, status, started_at/completed_at,
    duration_ms, tool_calls, turns, effective_model_id, parent_session_id and
    child_session_id — the child is a full sibling session directory.
    """
    sub_dir = sess_dir / "subagents"
    entries: List[Dict[str, Any]] = []
    try:
        if not sub_dir.is_dir():
            return entries
        for meta_path in sorted(sub_dir.glob("*/meta.json")):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    m = json.load(f)
            except Exception:
                continue
            if not isinstance(m, dict):
                continue
            entries.append({
                "agent_id": m.get("subagent_id") or meta_path.parent.name,
                "agent_type": m.get("subagent_type") or "unknown",
                "description": m.get("description"),
                "status": m.get("status"),
                "duration_ms": m.get("duration_ms"),
                "tool_calls": m.get("tool_calls"),
                "turns": m.get("turns"),
                "model": m.get("effective_model_id"),
                "child_session_id": m.get("child_session_id"),
            })
    except Exception:
        pass
    return entries


def _scan_smallcode_sessions(roots: Iterable[str]) -> List[Dict[str, Any]]:
    """Scan SmallCode traces, which are PROJECT-LOCAL (not under a home dir).

    Verified shape (see testdata/cline_smallcode/smallcode/8fadca50.json):
    ``<project>/.smallcode/traces/<id>.json`` with
    ``{id, model, prompt, startedAt, endedAt, durationMs, steps, tokens:{prompt,completion}}``.
    """
    out: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()

    for root in roots:
        if not root or root == "unknown":
            continue
        root_path = Path(root).expanduser()
        traces_dir = root_path / ".smallcode" / "traces"
        if not traces_dir.is_dir():
            continue

        for trace_path in sorted(traces_dir.glob("*.json")):
            try:
                with open(trace_path, "r", encoding="utf-8") as f:
                    trace = json.load(f)
            except Exception:
                continue
            if not isinstance(trace, dict):
                continue

            sid = trace.get("id") or trace_path.stem
            if not sid or sid in seen_ids:
                continue
            seen_ids.add(sid)

            model = trace.get("model") or "unknown"
            started_at = trace.get("startedAt")
            try:
                ts = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
            except Exception:
                ts = _file_mtime_utc(trace_path)

            raw_tokens = trace.get("tokens") or {}
            input_tokens = int(raw_tokens.get("prompt") or 0)
            output_tokens = int(raw_tokens.get("completion") or 0)
            tokens = {
                "input": input_tokens, "output": output_tokens, "cached": 0,
                "total": input_tokens + output_tokens, "cost": 0.0,
            }
            tokens["cost"] = calculate_cost(model, tokens["input"], tokens["output"], tokens["cached"], at=ts)

            prompt = trace.get("prompt") or ""
            mcp_tools: List[str] = []
            for step in trace.get("steps") or []:
                if not isinstance(step, dict):
                    continue
                if step.get("type") == "tool_call":
                    name = step.get("name")
                    if name and name not in mcp_tools:
                        mcp_tools.append(name)

            out.append({
                "id": sid,
                "agent": "smallcode",
                "project": str(root_path),
                "timestamp": ts,
                "display": prompt[:120],
                "tokens": tokens,
                "model": model,
                "mcp_tools": mcp_tools,
                "has_plan": False,
                "plans": [],
                "artifacts": [{"name": trace_path.name, "path": str(trace_path), "type": "document"}],
                "cost": tokens["cost"],
            })

    return out


def _cline_loop_specs(db_path: Path) -> Dict[str, Dict[str, Any]]:
    """Read Cline "Scheduled Agents" from cron.db and return {anchor_session_id:
    loop_dict} for each genuinely recurring schedule.

    Cline's model differs from Claude/Grok: a recurring schedule is a row in
    `cron_specs` (trigger_kind='schedule'), and every firing spawns its OWN
    Cline session, recorded in `cron_runs` with a session_id. To reuse the
    session-based loop UI we anchor the loop to the LATEST run's session (the
    most recent fire) — the same "loop lives in the session that ran it" model
    Grok uses. A schedule that has never fired (no run with a session_id) has no
    anchor and isn't surfaced. one_off/event triggers are not loops.

    Cline's per-run sessions are each counted on their own, so the loop's
    footprint is left at 0 here (iterations + cadence carry the signal) rather
    than re-summing already-counted child sessions.
    """
    out: Dict[str, Dict[str, Any]] = {}
    if not db_path.exists():
        return out
    try:
        uri = _sqlite_ro_uri(db_path)
        conn = sqlite3.connect(uri, uri=True, timeout=1.0)
        conn.row_factory = sqlite3.Row
        try:
            specs = conn.execute(
                "SELECT * FROM cron_specs WHERE trigger_kind='schedule'"
            ).fetchall()
            for spec in specs:
                spec_id = spec["spec_id"]
                runs = conn.execute(
                    "SELECT session_id, status, completed_at, created_at FROM cron_runs "
                    "WHERE spec_id=? ORDER BY created_at DESC",
                    (spec_id,),
                ).fetchall()
                # Anchor to the most recent run that actually has a session.
                anchor = next((r["session_id"] for r in runs if r["session_id"]), None)
                if not anchor:
                    continue
                fired = [r for r in runs if r["status"] in ("done", "failed", "cancelled")]
                schedule_expr = spec["schedule_expr"]
                removed = bool(spec["removed"]) if "removed" in spec.keys() else False
                enabled = bool(spec["enabled"]) if "enabled" in spec.keys() else True
                cancelled = removed or not enabled
                out[anchor] = {
                    "is_loop": True,
                    "mode": "cron",                       # cron/interval schedule, NOT a Claude 7-day cron
                    "cadence": schedule_expr or "",
                    "cadence_seconds": _cron_to_seconds(schedule_expr) if schedule_expr else None,
                    "recurring": True,
                    "job_id": spec["external_id"] or spec_id,
                    "source_signal": "cline_schedule",
                    "prompt_preview": ((spec["prompt"] if "prompt" in spec.keys() else None)
                                       or spec["title"] or "")[:160],
                    "created_at": spec["created_at"] if "created_at" in spec.keys() else None,
                    "last_fired": (spec["last_run_at"] if "last_run_at" in spec.keys() else None),
                    "iterations": len(fired),
                    "cancelled": cancelled,
                    "cancelled_at": (spec["updated_at"] if cancelled and "updated_at" in spec.keys() else None),
                    "footprint_tokens": 0,                # each fire is its own already-counted session
                    "footprint_cost": 0,
                }
        finally:
            conn.close()
    except Exception:
        return out
    return out


def _scan_cline_sessions() -> List[Dict[str, Any]]:
    """Scan Cline sessions from BOTH stores it writes to, deduping by session id
    (the CLI row wins when a session id appears in both).

    (a) CLI: SQLite ``sessions.db`` under ``CLINE_DIR/data/db/`` — verified schema
    has a ``sessions`` table with session_id/started_at/.../metadata_json/messages_path.
    Token usage lives in ``metadata_json``, preferring ``aggregateUsage`` over
    ``usage``; if both are all-zero we fall back to summing each message's
    ``metrics`` in the ``messages_path`` JSON transcript.

    (b) VS Code extension: ``CLINE_VSCODE_DIR/state/taskHistory.json`` — an array
    of HistoryItems (id, ts epoch-ms, task, tokensIn/Out, cacheWrites/Reads,
    totalCost, size). This store is undocumented beyond that shape (the
    extension isn't installed on the machine this was written on), so the
    parser sticks to exactly those fields.
    """
    aliases = _load_project_aliases()
    def _apply_alias(p: str) -> str:
        return aliases.get(p, p)

    out: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()

    # (a) CLI SQLite store
    db_path = CLINE_DIR / "data" / "db" / "sessions.db"
    if db_path.exists():
        rows = []
        try:
            uri = _sqlite_ro_uri(db_path)
            conn = sqlite3.connect(uri, uri=True, timeout=1.0)
            conn.row_factory = sqlite3.Row
            try:
                # SELECT * (not a fixed column list) so older Cline DBs that
                # predate is_subagent/parent_session_id still scan — missing
                # columns are read defensively below rather than erroring the
                # whole query to an empty result.
                rows = conn.execute("SELECT * FROM sessions").fetchall()
            finally:
                conn.close()
        except Exception:
            rows = []

        # Cline spawns subagents/teams: each subagent is its OWN row with
        # is_subagent=1 and parent_session_id set, while the parent's
        # metadata.aggregateUsage already SUMS the children in. Counting both
        # the parent's aggregate AND each child row would double-count, so
        # parents are billed on their own `usage` and linked via
        # parent_session_id for the delegation view; children stay as their own
        # rows. Leaf/standalone sessions have usage == aggregateUsage.
        def _row_get(r, k, default=None):
            return r[k] if k in r.keys() else default
        parents_with_children = {
            _row_get(r, "parent_session_id")
            for r in rows
            if _row_get(r, "is_subagent") and _row_get(r, "parent_session_id")
        }

        for row in rows:
            sid = row["session_id"]
            if not sid or sid in seen_ids:
                continue

            model = row["model"] or "unknown"
            project_path = _apply_alias(row["workspace_root"] or row["cwd"] or "unknown")

            try:
                ts = datetime.fromisoformat(str(row["started_at"]).replace("Z", "+00:00"))
            except Exception:
                ts = _file_mtime_utc(db_path)

            try:
                metadata = json.loads(row["metadata_json"] or "{}") or {}
            except Exception:
                metadata = {}
            if not isinstance(metadata, dict):
                metadata = {}

            # Parents (sessions that spawned subagents) bill on their OWN usage
            # so the separately-counted child rows aren't double-counted; leaf
            # and standalone sessions use aggregateUsage (== usage with no
            # children).
            is_parent = sid in parents_with_children
            if is_parent:
                usage = metadata.get("usage") or metadata.get("aggregateUsage") or {}
            else:
                usage = metadata.get("aggregateUsage") or {}
            if not isinstance(usage, dict) or not any(
                usage.get(k) for k in ("inputTokens", "outputTokens", "cacheReadTokens")
            ):
                fallback_usage = metadata.get("usage")
                if isinstance(fallback_usage, dict):
                    usage = fallback_usage

            tokens = {
                "input": int((usage or {}).get("inputTokens") or 0),
                "output": int((usage or {}).get("outputTokens") or 0),
                "cached": int((usage or {}).get("cacheReadTokens") or 0),
                "total": 0, "cost": 0.0,
            }

            # Metadata usage is all zero (older/degenerate rows) — fall back to
            # summing per-message metrics in the messages_path transcript.
            messages_path = row["messages_path"]
            if tokens["input"] == 0 and tokens["output"] == 0 and tokens["cached"] == 0 and messages_path:
                mp = Path(messages_path)
                if mp.exists():
                    try:
                        with open(mp, "r", encoding="utf-8", errors="replace") as f:
                            mdata = json.load(f)
                        for m in (mdata.get("messages") or []):
                            if not isinstance(m, dict):
                                continue
                            metrics = m.get("metrics") or {}
                            if not isinstance(metrics, dict):
                                continue
                            tokens["input"] += int(metrics.get("inputTokens") or 0)
                            tokens["output"] += int(metrics.get("outputTokens") or 0)
                            tokens["cached"] += int(metrics.get("cacheReadTokens") or 0)
                    except Exception:
                        pass

            tokens["total"] = tokens["input"] + tokens["output"]

            # metadata.totalCost is the AGGREGATE (parent + children); for a
            # parent we switched to own-usage above, so derive own cost to match
            # rather than inheriting the children's cost.
            meta_cost = metadata.get("totalCost")
            if not is_parent and isinstance(meta_cost, (int, float)) and meta_cost > 0:
                tokens["cost"] = float(meta_cost)
            else:
                # sessions.db carries a `provider` column and no endpoint, so the
                # provider is the only routing signal available here. Passing it
                # reaches PRICING_BY_PROVIDER, the local-provider branch (ollama
                # and friends price by electricity, not cloud rates), and the
                # subscriptionProviders branch (cline-pass is flat monthly).
                tokens["cost"] = calculate_cost(model, tokens["input"], tokens["output"], tokens["cached"], provider=row["provider"], at=ts)

            display = (row["prompt"] or metadata.get("title") or "")[:120]

            artifacts: List[Dict[str, Any]] = [{"name": "sessions.db", "path": str(db_path), "type": "document"}]
            if messages_path:
                artifacts.append({"name": "messages", "path": str(messages_path), "type": "document"})

            is_subagent = bool(_row_get(row, "is_subagent"))
            parent_sid = _row_get(row, "parent_session_id")
            rec = {
                "id": sid,
                "agent": "cline",
                "project": project_path,
                "timestamp": ts,
                "display": display,
                "tokens": tokens,
                "model": model,
                "mcp_tools": [],
                "has_plan": False,
                "plans": [],
                "artifacts": artifacts,
                "cost": tokens["cost"],
                "cline": {
                    "source": "cli",
                    "provider": row["provider"],
                    "status": row["status"],
                    "messages_path": messages_path,
                    "is_subagent": is_subagent,
                    "agent_id": _row_get(row, "agent_id"),
                    "team_name": _row_get(row, "team_name"),
                    "spawned_children": sid in parents_with_children,
                },
            }
            # Link child -> parent so the delegation view attributes a spawned
            # subagent's (own-counted) tokens to the session that spawned it,
            # mirroring the Grok/Codex sibling-session model.
            if is_subagent and parent_sid:
                rec["parent_session_id"] = parent_sid
                rec["is_subagent"] = True
            out.append(rec)
            seen_ids.add(sid)

    # (b) VS Code extension store
    history_path = CLINE_VSCODE_DIR / "state" / "taskHistory.json"
    if history_path.exists():
        try:
            with open(history_path, "r", encoding="utf-8", errors="replace") as f:
                history = json.load(f)
        except Exception:
            history = []

        if isinstance(history, list):
            for item in history:
                if not isinstance(item, dict):
                    continue
                sid = str(item.get("id") or "")
                if not sid or sid in seen_ids:
                    continue

                ts_ms = item.get("ts")
                try:
                    ts = datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc)
                except Exception:
                    ts = _file_mtime_utc(history_path)

                tokens_in = int(item.get("tokensIn") or 0)
                tokens_out = int(item.get("tokensOut") or 0)
                cache_reads = int(item.get("cacheReads") or 0)
                model = item.get("model") or "unknown"
                tokens = {
                    "input": tokens_in, "output": tokens_out, "cached": cache_reads,
                    "total": tokens_in + tokens_out, "cost": 0.0,
                }
                total_cost = item.get("totalCost")
                if isinstance(total_cost, (int, float)) and total_cost > 0:
                    tokens["cost"] = float(total_cost)
                else:
                    # No provider here, unlike the CLI path above: taskHistory.json
                    # HistoryItems carry no provider or endpoint field, so there is
                    # nothing to pass. Left per-token deliberately.
                    tokens["cost"] = calculate_cost(model, tokens["input"], tokens["output"], tokens["cached"], at=ts)

                transcript_path = CLINE_VSCODE_DIR / "tasks" / sid / "api_conversation_history.json"
                artifacts: List[Dict[str, Any]] = []
                if transcript_path.exists():
                    artifacts.append({"name": "api_conversation_history.json", "path": str(transcript_path), "type": "document"})

                out.append({
                    "id": sid,
                    "agent": "cline",
                    "project": _apply_alias(item.get("cwd") or item.get("workspace") or "unknown"),
                    "timestamp": ts,
                    "display": (item.get("task") or "")[:120],
                    "tokens": tokens,
                    "model": model,
                    "mcp_tools": [],
                    "has_plan": False,
                    "plans": [],
                    "artifacts": artifacts,
                    "cost": tokens["cost"],
                    "cline": {
                        "source": "vscode",
                        "cache_writes": item.get("cacheWrites"),
                        "transcript_path": str(transcript_path) if transcript_path.exists() else None,
                    },
                })
                seen_ids.add(sid)

    # Recurring "Scheduled Agents" (cron.db) — anchor each schedule's loop to its
    # latest run session. Gated on the file existing; cheap SQLite read.
    loop_by_sid = _cline_loop_specs(CLINE_DIR / "data" / "db" / "cron.db")
    if loop_by_sid:
        for rec in out:
            lp = loop_by_sid.get(rec["id"])
            if lp:
                rec["loop"] = lp

    return out


def _scan_pi_sessions() -> List[Dict[str, Any]]:
    """Scan Pi Coding Agent sessions under ~/.pi/agent/sessions/.

    Layout: one JSONL per session, bucketed by encoded cwd:
        ~/.pi/agent/sessions/<encoded-cwd>/<ts>_<uuid>.jsonl

    Each file begins with a {"type":"session", id, cwd, timestamp} header, then a
    stream of events. The ones we read:
      - {"type":"model_change", provider, modelId}   -> current model/provider
      - {"type":"message", message:{...}}            -> a turn. For assistant turns
        `message` carries `provider`, `model` and a per-request `usage`:
          {input, output, cacheRead, cacheWrite, reasoning, totalTokens,
           cost:{...}}  (reasoning is a subset of output; totalTokens =
           input + output + cacheRead, so we never double-count it.)

    Cost is recomputed with TokenTelemetry's own pricing PER MESSAGE using that
    message's model+provider, so mixed-model sessions bill correctly and Pi→Ollama
    sessions fall through to the local-electricity branch in calculate_cost.
    """
    if not PI_SESSIONS_DIR.exists():
        return []

    aliases = _load_project_aliases()
    def _apply_alias(p: str) -> str:
        return aliases.get(p, p)

    out: List[Dict[str, Any]] = []

    for bucket in PI_SESSIONS_DIR.iterdir():
        if not bucket.is_dir():
            continue
        for sess_file in bucket.glob("*.jsonl"):
            try:
                sid = None
                project = None
                header_ts = None
                last_ts = None
                cur_model = None
                cur_provider = None
                sess_model = None
                sess_provider = None
                display = None
                msg_count = 0
                tokens = {"input": 0, "output": 0, "cached": 0,
                          "cache_creation": 0, "reasoning": 0, "total": 0}
                cost = 0.0
                tool_counts: Dict[str, int] = {}
                models_used: List[str] = []

                with open(sess_file, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            evt = json.loads(line)
                        except Exception:
                            continue
                        etype = evt.get("type")

                        if etype == "session":
                            sid = evt.get("id") or sid
                            cwd = evt.get("cwd")
                            if cwd:
                                project = _apply_alias(cwd)
                            ts_raw = evt.get("timestamp")
                            if ts_raw:
                                try:
                                    header_ts = _aware(datetime.fromisoformat(
                                        str(ts_raw).replace("Z", "+00:00")))
                                except Exception:
                                    header_ts = None
                            continue

                        if etype == "model_change":
                            cur_provider = evt.get("provider") or cur_provider
                            cur_model = evt.get("modelId") or cur_model
                            continue

                        if etype != "message":
                            continue

                        m = evt.get("message") or {}
                        role = m.get("role")

                        ts_raw = evt.get("timestamp")
                        if ts_raw:
                            try:
                                _ts = _aware(datetime.fromisoformat(
                                    str(ts_raw).replace("Z", "+00:00")))
                                if last_ts is None or _ts > last_ts:
                                    last_ts = _ts
                            except Exception:
                                pass

                        if role == "user" and display is None:
                            for c in (m.get("content") or []):
                                if isinstance(c, dict) and c.get("type") == "text":
                                    t = (c.get("text") or "").strip()
                                    preview = _strip_context_tags(t).strip()
                                    if preview:
                                        display = preview[:120]
                                        break

                        if role == "assistant":
                            msg_model = m.get("model") or cur_model
                            msg_provider = m.get("provider") or cur_provider
                            if msg_model:
                                sess_model = msg_model
                                sess_provider = msg_provider
                                if msg_model not in models_used:
                                    models_used.append(msg_model)
                            for c in (m.get("content") or []):
                                if isinstance(c, dict) and c.get("type") == "toolCall":
                                    _count_tool(tool_counts, c.get("name"))
                            u = m.get("usage")
                            if isinstance(u, dict):
                                in_t = u.get("input", 0) or 0
                                out_t = u.get("output", 0) or 0
                                cr = u.get("cacheRead", 0) or 0
                                cw = u.get("cacheWrite", 0) or 0
                                reas = u.get("reasoning", 0) or 0
                                tokens["input"] += in_t
                                tokens["output"] += out_t
                                tokens["cached"] += cr
                                tokens["cache_creation"] += cw
                                tokens["reasoning"] += reas
                                # Recompute per message with that turn's own model
                                # so mixed-model / local sessions price correctly.
                                cost += calculate_cost(
                                    msg_model, in_t, out_t, cr,
                                    cache_creation_tokens=cw,
                                    provider=msg_provider,
                                )
                            msg_count += 1
                        elif role in ("user", "toolResult"):
                            msg_count += 1
            except Exception:
                continue

            if sid is None:
                continue

            ts = last_ts or header_ts or _file_mtime_utc(sess_file)
            tokens["total"] = tokens["input"] + tokens["output"] + tokens["cached"]
            tokens["cost"] = cost

            sess = {
                "id": sid,
                "agent": "pi",
                "project": project or "unknown",
                "timestamp": ts,
                "display": display or f"Pi session {sid[:8]}",
                "text": display,
                "tokens": tokens,
                "mcp_tools": [t for t in tool_counts if isinstance(t, str) and t.startswith("mcp")],
                "has_plan": False,
                "plans": [],
                "model": sess_model or cur_model,
                "artifacts": [{"name": sess_file.name, "path": str(sess_file), "type": "document"}],
                "cost": cost,
                "pi": {
                    "provider": sess_provider or cur_provider,
                    "models_used": models_used,
                    "num_messages": msg_count,
                    "reasoning_tokens": tokens["reasoning"],
                },
            }
            _attach_tool_usage(sess, tool_counts)
            out.append(sess)

    return out


def _dsh_read_events(path: Path) -> Optional[List[Dict[str, Any]]]:
    """Decompress + parse one DSH session.jsonl.zstd into JSON rows.

    Returns None if the optional `zstandard` dependency isn't installed or the
    file can't be read/decoded -- callers must treat that as "skip this
    session", the same as every other harness whose store is simply absent.
    stream_reader decodes concatenated zstd frames as one logical stream
    (standard zstd framing), so an appended/resumed session file is handled
    without special-casing.
    """
    try:
        import zstandard
    except ImportError:
        return None
    try:
        with open(path, "rb") as fh:
            dctx = zstandard.ZstdDecompressor()
            with dctx.stream_reader(fh) as reader:
                text = reader.read().decode("utf-8", errors="replace")
    except Exception:
        return None
    rows: List[Dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _dsh_parse_session(path: Path) -> Optional[Dict[str, Any]]:
    """Parse one DSH session file into a summary dict, or None if unreadable.

    Usage accounting: DSH emits a per-(turn,step) usage sample on the
    streaming `assistant/chunk` event and again, identically, on the final
    `assistant/message` -- both are the SAME sample, not additive deltas (DSH's
    own usage-projection code replaces rather than sums same-(turn,step)
    values). We key a dict by (turn,step) and let the later event win, then
    sum across keys once -- summing every usage-bearing event naively would
    double count every turn.

    Cost: DSH has no cost/pricing concept anywhere (confirmed in its source --
    a NO_COST constant zeroes it before it ever reaches a consumer), and one
    session can span multiple providers/models (e.g. an ollama call that
    errors, retried on cerebras). So cost is recomputed per (turn,step) with
    that step's own provider+model via TokenTelemetry's own pricing, and
    summed -- never priced once from a single session-level model.
    """
    rows = _dsh_read_events(path)
    if not rows:
        return None
    header = rows[0]
    if header.get("type") != "session":
        return None
    sid = header.get("id")
    if not isinstance(sid, str) or not sid:
        return None

    usage_by_step: Dict[Tuple[Any, Any], Dict[str, Any]] = {}
    cur_provider = cur_model = None
    last_provider = last_model = None
    display = None
    last_ts: Optional[float] = None
    tool_counts: Dict[str, int] = {}
    # DSH loads skills/plugins/tools DYNAMICALLY at runtime, so what a session
    # actually had is only knowable from the session's own log -- a filesystem
    # scan can't answer it (and the catalog genuinely differs between sessions
    # in the same workspace). Both are captured from the log, never inferred.
    skills_catalog: Dict[str, str] = {}   # name -> description, last write wins
    tools_available: List[str] = []
    providers_used: List[str] = []
    # The header's agentPreset is only the STARTING preset. DSH can swap presets
    # mid-session (an `agent-preset/selected` event), and the preset determines
    # which skills/tools get loaded -- so reporting the header value alone
    # misdescribes the run. Verified on real data: a session whose header says
    # "standard" switched to "cordis" and ran with 8 skills / 32 tools instead
    # of 6 / 25. Track the whole chain and report the effective (last) one.
    preset_chain: List[str] = []
    if isinstance(header.get("agentPreset"), str) and header["agentPreset"]:
        preset_chain.append(header["agentPreset"])
    # Sandbox / approval posture. DSH runs every session under a file-sandbox
    # mode and an approval policy, and a delegated child INHERITS them with
    # `source: "delegation"` -- real example on this machine: a parent running
    # approval "ask" spawned a subagent running "never", i.e. the child could
    # act without prompting. That is a trust-boundary fact, so the source is
    # kept rather than flattened into the value.
    sandbox: Dict[str, Any] = {}
    # Latency breakdown. DSH's own UI footer shows these, and every formula
    # below was checked against it on a real session (TTFT 1.5s, LLM 3.8s,
    # tool 37.2s, 166 tok/s) before being written:
    #   TTFT      = first assistant chunk - step/start
    #   LLM time  = assistant finish - step/start          (per step, summed)
    #   gen time  = assistant finish - first chunk         (drives tok/s)
    #   tool time = tool/result - tool/call                (per call, summed)
    # Tool time is wall-clock and can dwarf LLM time (a 41s session here was 37s
    # of one subagent call), which is exactly why the split is worth keeping.
    step_start: Dict[Tuple[Any, Any], float] = {}
    step_first_chunk: Dict[Tuple[Any, Any], float] = {}
    step_finish: Dict[Tuple[Any, Any], float] = {}
    tool_call_at: Dict[str, float] = {}
    tool_ms_total = 0.0
    turns = steps = 0

    for row in rows[1:]:
        rtype = row.get("type")
        data = row.get("data")
        if not isinstance(data, dict):
            continue

        t = row.get("time")
        if isinstance(t, (int, float)) and t > 0 and (last_ts is None or t > last_ts):
            last_ts = t

        if rtype == "request/context":
            cur_provider = data.get("provider") or cur_provider
            cur_model = data.get("model") or cur_model
            if cur_provider and cur_provider not in providers_used:
                providers_used.append(cur_provider)

        elif rtype == "sandbox/mode":
            if isinstance(data.get("mode"), str):
                sandbox["mode"] = data["mode"]
                sandbox["mode_source"] = data.get("source") or "session"

        elif rtype == "approval/policy":
            if isinstance(data.get("policy"), str):
                sandbox["approval"] = data["policy"]
                sandbox["approval_source"] = data.get("source") or "session"

        elif rtype == "permission/preset":
            if isinstance(data.get("preset"), str):
                sandbox["permission_preset"] = data["preset"]

        elif rtype == "agent-preset/selected":
            preset = data.get("agentPreset")
            if isinstance(preset, str) and preset and (not preset_chain or preset_chain[-1] != preset):
                preset_chain.append(preset)

        elif rtype == "request/header":
            # The tool list handed to the model this request IS the runtime
            # capability set (DSH tools + any MCP-backed ones), so read it
            # rather than guessing from config on disk.
            for tool in ((data.get("header") or {}).get("tools") or []):
                name = tool.get("name") if isinstance(tool, dict) else None
                if isinstance(name, str) and name and name not in tools_available:
                    tools_available.append(name)

        elif rtype == "user/message":
            source = data.get("source") or {}
            if source.get("kind") == "skill-catalog":
                # DSH splices the live skill catalog into the conversation; this
                # is the only record of which skills the run could actually use.
                for entry in (source.get("entries") or []):
                    if isinstance(entry, dict) and isinstance(entry.get("name"), str):
                        skills_catalog[entry["name"]] = (entry.get("description") or "")[:200]
            if display is None:
                for block in data.get("content") or []:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = (block.get("text") or "").strip()
                        if text and not text.startswith("<system-reminder>"):
                            display = text[:120]
                            break

        elif rtype == "turn/start":
            turns += 1

        elif rtype == "step/start":
            steps += 1
            if isinstance(t, (int, float)):
                step_start[(data.get("turn"), data.get("step"))] = t

        elif rtype == "tool/call":
            name = data.get("name")
            if isinstance(name, str) and name:
                tool_counts[name] = tool_counts.get(name, 0) + 1
            call_id = data.get("callId")
            if isinstance(call_id, str) and isinstance(t, (int, float)):
                tool_call_at[call_id] = t

        elif rtype == "tool/result":
            call_id = ((data.get("message") or {}).get("source") or {}).get("callId")
            started = tool_call_at.pop(call_id, None) if isinstance(call_id, str) else None
            if started is not None and isinstance(t, (int, float)) and t >= started:
                tool_ms_total += t - started

        elif rtype == "assistant/chunk":
            chunk = data.get("chunk")
            key = (data.get("turn"), data.get("step"))
            if isinstance(t, (int, float)):
                # First chunk of the step marks time-to-first-token; the
                # terminal chunk marks the end of generation.
                step_first_chunk.setdefault(key, t)
                if isinstance(chunk, dict) and chunk.get("type") in ("finish", "usage"):
                    step_finish[key] = max(step_finish.get(key, 0.0), t)
            if isinstance(chunk, dict) and chunk.get("type") == "usage":
                usage_by_step[key] = {**(chunk.get("usage") or {}), "provider": cur_provider, "model": cur_model}
                last_provider, last_model = cur_provider, cur_model

        elif rtype == "assistant/message":
            usage = data.get("usage")
            if isinstance(usage, dict):
                key = (data.get("turn"), data.get("step"))
                source = ((data.get("message") or {}).get("source")) or {}
                msg_provider = source.get("provider") or cur_provider
                msg_model = source.get("model") or cur_model
                usage_by_step[key] = {**usage, "provider": msg_provider, "model": msg_model}
                last_provider, last_model = msg_provider, msg_model

    tokens = {"input": 0, "output": 0, "cached": 0, "cache_creation": 0, "reasoning": 0, "total": 0}
    # Resolve the session timestamp BEFORE the cost loop: calculate_cost prices
    # date-banded models by when the tokens were generated, and `ts` used to be
    # computed further down, after this loop had already run.
    if last_ts:
        ts = _aware(datetime.fromtimestamp(last_ts / 1000, tz=timezone.utc))
    elif isinstance(header.get("createdAt"), (int, float)) and header["createdAt"] > 0:
        ts = _aware(datetime.fromtimestamp(header["createdAt"] / 1000, tz=timezone.utc))
    else:
        ts = _file_mtime_utc(path)

    cost = 0.0
    models_used: List[str] = []
    for u in usage_by_step.values():
        in_t = int(u.get("inputTokens") or 0)
        out_t = int(u.get("outputTokens") or 0)
        cr = int(u.get("cacheReadTokens") or 0)
        cw = int(u.get("cacheWriteTokens") or 0)
        reas = int(u.get("reasoningTokens") or 0)
        tokens["input"] += in_t
        tokens["output"] += out_t
        tokens["cached"] += cr
        tokens["cache_creation"] += cw
        tokens["reasoning"] += reas
        model = u.get("model")
        if model and model not in models_used:
            models_used.append(model)
        cost += calculate_cost(model, in_t, out_t, cr, cache_creation_tokens=cw, provider=u.get("provider"), at=ts)
    tokens["total"] = tokens["input"] + tokens["output"] + tokens["cached"]

    # --- latency breakdown (formulas noted where the inputs are collected)
    ttfts = [step_first_chunk[k] - step_start[k]
             for k in step_first_chunk
             if k in step_start and step_first_chunk[k] >= step_start[k]]
    llm_ms = sum(step_finish[k] - step_start[k]
                 for k in step_finish
                 if k in step_start and step_finish[k] >= step_start[k])
    gen_ms = sum(step_finish[k] - step_first_chunk[k]
                 for k in step_finish
                 if k in step_first_chunk and step_finish[k] >= step_first_chunk[k])
    metrics: Dict[str, Any] = {
        "turns": turns,
        "steps": steps,
        "llm_ms": round(llm_ms) or None,
        "tool_ms": round(tool_ms_total) or None,
        "ttft_ms_avg": round(sum(ttfts) / len(ttfts)) if ttfts else None,
        # Output tokens over GENERATION time only -- dividing by total LLM time
        # would fold in time-to-first-token and understate throughput.
        "output_tok_per_sec": round(tokens["output"] / (gen_ms / 1000), 1)
                              if gen_ms > 0 and tokens["output"] else None,
    }
    # DSH counts cache reads as part of input -- that is how its own footer
    # reports "Input 16.5K" for an 8.3K + 8.2K split. Mirror it so the two agree.
    billed_input = tokens["input"] + tokens["cached"]
    metrics["cache_hit_pct"] = round(tokens["cached"] / billed_input * 100, 1) if billed_input else None

    return {
        "id": sid,
        "project": header.get("cwd") or "unknown",
        "origin": header.get("origin"),
        "parent_session": header.get("parentSession"),
        "delegation_depth": header.get("delegationDepth") or 0,
        "agent_preset": preset_chain[-1] if preset_chain else header.get("agentPreset"),
        "preset_chain": preset_chain,
        "sandbox": sandbox,
        "metrics": metrics,
        "timestamp": ts,
        "display": display,
        "tokens": tokens,
        "cost": cost,
        "model": last_model,
        "models_used": models_used,
        "provider": last_provider,
        "providers_used": providers_used,
        "tool_counts": tool_counts,
        "skills_catalog": [{"name": n, "description": d} for n, d in sorted(skills_catalog.items())],
        "tools_available": sorted(tools_available),
        "path": path,
    }


def _scan_dsh_sessions() -> List[Dict[str, Any]]:
    """Scan DeepSeek Harness (DSH) sessions under ~/.dsh/sessions/.

    Layout: ~/.dsh/sessions/<slugged-cwd>/<session-<uuid> | <uuid>>/session.jsonl.zstd
    Each file's own header carries `cwd`, so we glob for session files directly
    rather than reversing DSH's lossy (251-char-truncated) path slug. Requires
    the optional `zstandard` dependency; DSH is skipped silently, like any
    other absent harness, when it isn't installed or no sessions exist.

    Delegation: DSH stamps subagent children with an explicit
    origin="subagent" + parentSession in the header -- no directory-naming or
    timing inference needed. Children are folded into the parent's
    `delegation` block (subagents / delegated_total / delegated_cost),
    matching the convention used elsewhere (see _scan_muse_sessions) rather
    than surfaced as separate top-level sessions. A `session-`-prefixed id
    that carries a parentSession but no origin (an in-process "fork") has no
    observed example on real data -- left as a standalone top-level session
    rather than guessing at rollup semantics that can't be verified.
    """
    if not DSH_SESSIONS_DIR.exists():
        return []

    aliases = _load_project_aliases()

    by_id: Dict[str, Dict[str, Any]] = {}
    for sess_file in DSH_SESSIONS_DIR.glob("*/*/session.jsonl.zstd"):
        parsed = _dsh_parse_session(sess_file)
        if parsed:
            by_id[parsed["id"]] = parsed
    if not by_id:
        return []

    children_of: Dict[str, List[Dict[str, Any]]] = {}
    for parsed in by_id.values():
        parent_id = parsed.get("parent_session")
        if parsed.get("origin") == "subagent" and parent_id in by_id:
            children_of.setdefault(parent_id, []).append(parsed)

    out: List[Dict[str, Any]] = []
    for sid, parsed in by_id.items():
        if parsed.get("origin") == "subagent" and parsed.get("parent_session") in by_id:
            continue  # folded into its parent below, not a top-level session

        kids = children_of.get(sid, [])
        delegation = None
        if kids:
            subagents = [{
                "agent_id": kid["id"], "agent_type": "dsh-subagent", "model": kid["model"],
                "tokens": kid["tokens"], "cost": kid["cost"],
                # A child inherits its sandbox/approval posture from the parent
                # and can end up more permissive than it (approval "never" under
                # a parent on "ask"), so carry it per child rather than assuming
                # the parent's posture describes the whole tree.
                "sandbox": kid["sandbox"],
            } for kid in kids]
            delegated_tokens = {"input": 0, "output": 0, "cached": 0, "cache_creation": 0, "reasoning": 0}
            for kid in kids:
                for key in delegated_tokens:
                    delegated_tokens[key] += kid["tokens"][key]
            delegated_total = sum(delegated_tokens.values())
            delegated_cost = sum(s["cost"] for s in subagents)
            delegation = {
                "supported": True, "tokens_recorded": True, "spawn_count": len(subagents),
                "subagents": subagents, "delegated_total": delegated_total, "delegated_cost": delegated_cost,
                "by_type": {"dsh-subagent": {"count": len(subagents), "total": delegated_total, "cost": delegated_cost}},
            }

        tool_counts = parsed["tool_counts"]
        sess = {
            "id": sid,
            "agent": "dsh",
            "project": aliases.get(parsed["project"], parsed["project"]),
            "timestamp": parsed["timestamp"],
            "display": parsed["display"] or f"DeepSeek Harness session {sid[-8:]}",
            "text": parsed["display"],
            "tokens": parsed["tokens"],
            "mcp_tools": [t for t in tool_counts if isinstance(t, str) and t.startswith("mcp")],
            "has_plan": False,
            "plans": [],
            "model": parsed["model"],
            "provider": parsed["provider"],
            "artifacts": [{"name": "session.jsonl.zstd", "path": str(parsed["path"]), "type": "document"}],
            "cost": parsed["cost"],
            # Runtime capability set, read from this session's own log -- DSH
            # resolves skills/plugins/tools dynamically, so these are per-session
            # facts, NOT a filesystem scan of what happens to be installed now.
            "dsh": {
                "agent_preset": parsed["agent_preset"],
                "preset_chain": parsed["preset_chain"],
                "sandbox": parsed["sandbox"],
                "metrics": parsed["metrics"],
                "models_used": parsed["models_used"],
                "providers_used": parsed["providers_used"],
                "skills_catalog": parsed["skills_catalog"],
                "tools_available": parsed["tools_available"],
            },
        }
        if delegation:
            sess["delegation"] = delegation
        _attach_tool_usage(sess, tool_counts)
        out.append(sess)

    return out


# ------------------------------------------------------------------ Qoder --
#
# Qoder's CLI is a Claude Code derivative: identical JSONL record shape (cwd,
# gitBranch, isSidechain, parentUuid, sessionId, version, userType, entrypoint)
# plus five record types of its own -- workspace-directories, runtime-config,
# last-prompt, active-leaf and attachment.
#
# What makes it different is billing. Every assistant record carries an
# Anthropic-shaped `usage` object whose input_tokens, output_tokens,
# cache_read_input_tokens and cache_creation_input_tokens are ALL ZERO, with the
# real figure in `credits`. Tokens are not merely unread here, they are not
# recorded, and they cannot be reconstructed: `context_usage_ratio` is a
# fraction of an unknown denominator (runtime-config.contextWindow is null) and
# .models/<uid>/catalog-v6 is encrypted at rest, so even the model id stays
# opaque. See _scan_qoder_sessions.

# Context Qoder splices into the transcript as `attachment` records. None is a
# user turn. This is an ALLOWLIST on purpose: an unrecognised attachment type
# may carry file bodies or pasted content, and passing one through to the trace
# renderer would display it as conversation.
_QODER_ATTACHMENT_KINDS = frozenset({
    "skill_listing", "critical_system_reminder", "agent_listing_delta", "hook_output",
})

# Qoder prepends a plugin/system block to the first human prompt -- in both
# message.content[0].text and humanInput.text. Rendering it verbatim shows the
# harness's own instructions as if the user had typed them.
_QODER_REMINDER_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)


def _qoder_ts(value: Any) -> Optional[datetime]:
    """Qoder writes ISO strings on message records and epoch MILLIseconds on
    runtime-config, so both shapes turn up inside one file."""
    if isinstance(value, str) and value:
        try:
            return _aware(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        try:
            return _aware(datetime.fromtimestamp(value / 1000.0, tz=timezone.utc))
        except (OverflowError, OSError, ValueError):
            return None
    return None


def _qoder_num(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return float(value)


def _qoder_strip_reminder(text: Any) -> str:
    if not isinstance(text, str):
        return ""
    return _QODER_REMINDER_RE.sub("", text).strip()


def _qoder_human_text(row: Dict[str, Any]) -> str:
    """The words the user actually typed, or "" when this is not a human turn.

    `origin.kind` is the only reliable discriminator -- Qoder replays tool
    results and harness injections through the same `user` record type.
    """
    if (row.get("origin") or {}).get("kind") != "human":
        return ""
    human = row.get("humanInput")
    if isinstance(human, dict):
        direct = _qoder_strip_reminder(human.get("text"))
        if direct:
            return direct
    parts = [
        block.get("text") or ""
        for block in ((row.get("message") or {}).get("content") or [])
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return _qoder_strip_reminder("".join(parts))


def _qoder_fold_attachment(att: Any, skills: Set[str], servers: Set[str],
                           hooks: Dict[str, int]) -> None:
    """Mine one attachment for metadata. Unknown types are ignored entirely.

    These record what was AVAILABLE to the session, not what it used -- the
    skill catalog is injected whether or not a skill is ever invoked. Real
    usage comes from tool_use blocks instead, so this never feeds skills_used.
    """
    if not isinstance(att, dict):
        return
    kind = att.get("type")
    if kind not in _QODER_ATTACHMENT_KINDS:
        return
    if kind == "skill_listing":
        for name in (att.get("names") or []):
            if isinstance(name, str) and name:
                skills.add(name)
    elif kind == "critical_system_reminder":
        for name in (att.get("serverNames") or []):
            if isinstance(name, str) and name:
                servers.add(name)
    elif kind == "hook_output":
        event = att.get("hookEventName")
        if isinstance(event, str) and event:
            hooks[event] = hooks.get(event, 0) + 1


def _qoder_parse_session(path: Path) -> Optional[Dict[str, Any]]:
    """Parse one Qoder transcript. Returns None when the file yields no turns.

    Read defensively line by line: a live session is being appended to while we
    read, so the final line can be torn.
    """
    session_id = ""
    cwd = ""
    git_branch = ""
    version = ""
    entrypoint = ""
    model: Optional[str] = None
    credits = 0.0
    original_credits = 0.0
    billable_turns = 0
    assistant_turns = 0
    context_ratio: Optional[float] = None
    first_text = ""
    last_prompt = ""
    first_ts: Optional[datetime] = None
    last_ts: Optional[datetime] = None
    is_sidechain = False
    tool_counts: Dict[str, int] = {}
    skills: Set[str] = set()
    servers: Set[str] = set()
    hooks: Dict[str, int] = {}

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if not isinstance(row, dict):
                    continue

                if not session_id and isinstance(row.get("sessionId"), str):
                    session_id = row["sessionId"]
                if isinstance(row.get("cwd"), str) and row["cwd"]:
                    cwd = row["cwd"]
                if isinstance(row.get("gitBranch"), str) and row["gitBranch"]:
                    git_branch = row["gitBranch"]
                if isinstance(row.get("version"), str) and row["version"]:
                    version = row["version"]
                if isinstance(row.get("entrypoint"), str) and row["entrypoint"]:
                    entrypoint = row["entrypoint"]
                if row.get("isSidechain"):
                    is_sidechain = True

                stamp = _qoder_ts(row.get("timestamp"))
                if stamp:
                    first_ts = stamp if first_ts is None else min(first_ts, stamp)
                    last_ts = stamp if last_ts is None else max(last_ts, stamp)

                rtype = row.get("type")
                if rtype == "workspace-directories":
                    dirs = row.get("directories") or []
                    if not cwd and dirs and isinstance(dirs[0], str):
                        cwd = dirs[0]
                elif rtype == "runtime-config":
                    if isinstance(row.get("model"), str) and row["model"]:
                        model = row["model"]
                elif rtype == "last-prompt":
                    last_prompt = _qoder_strip_reminder(row.get("lastPrompt"))
                elif rtype == "attachment":
                    _qoder_fold_attachment(row.get("attachment"), skills, servers, hooks)
                elif rtype == "user":
                    if not first_text:
                        first_text = _qoder_human_text(row)
                elif rtype == "assistant":
                    msg = row.get("message") or {}
                    assistant_turns += 1
                    if isinstance(msg.get("model"), str) and msg["model"]:
                        model = msg["model"]
                    usage = msg.get("usage")
                    if isinstance(usage, dict):
                        credits += _qoder_num(usage.get("credits"))
                        original_credits += _qoder_num(usage.get("original_credits"))
                        if usage.get("billable"):
                            billable_turns += 1
                        ratio = usage.get("context_usage_ratio")
                        if isinstance(ratio, (int, float)) and not isinstance(ratio, bool):
                            context_ratio = float(ratio)
                    for block in (msg.get("content") or []):
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            name = block.get("name")
                            if isinstance(name, str) and name:
                                tool_counts[name] = tool_counts.get(name, 0) + 1
    except OSError:
        return None

    if last_ts is None:
        return None

    return {
        "id": session_id or path.stem,
        "path": path,
        "project": cwd or "unknown",
        "timestamp": last_ts,
        "started_at": first_ts,
        "display": first_text or last_prompt,
        "model": model,
        "credits": round(credits, 6),
        "original_credits": round(original_credits, 6),
        "billable_turns": billable_turns,
        "assistant_turns": assistant_turns,
        "context_usage_ratio": context_ratio,
        "git_branch": git_branch,
        "cli_version": version,
        "entrypoint": entrypoint,
        "is_sidechain": is_sidechain,
        "tool_counts": tool_counts,
        "skills_available": sorted(skills),
        "mcp_servers": sorted(servers),
        "hook_events": hooks,
    }


def _qoder_subagents(session_dir: Path) -> List[Dict[str, Any]]:
    """Child transcripts spawned by one Qoder session.

    Children live at <session-dir>/subagents/<name>.jsonl with a sibling
    <name>.meta.json naming the agent type and the task it was given. They are
    NOT top-level sessions -- counting the whole projects/ tree would return
    every child as a session of its own.
    """
    sub_dir = session_dir / "subagents"
    if not sub_dir.is_dir():
        return []
    kids: List[Dict[str, Any]] = []
    for transcript in sorted(sub_dir.glob("*.jsonl")):
        parsed = _qoder_parse_session(transcript)
        if not parsed:
            continue
        meta: Dict[str, Any] = {}
        try:
            meta_path = transcript.with_suffix(".meta.json")
            if meta_path.exists():
                loaded = json.loads(meta_path.read_text(encoding="utf-8", errors="replace"))
                if isinstance(loaded, dict):
                    meta = loaded
        except (OSError, ValueError):
            meta = {}
        # A child's records carry the PARENT's sessionId -- it is the same
        # session -- so the in-record id is identical for every child and
        # cannot identify one. Use the transcript's own filename, which
        # already encodes the agent type and a per-spawn hash.
        parsed["id"] = transcript.stem
        parsed["agent_type"] = meta.get("agentType") or meta.get("invocationName") or "subagent"
        parsed["description"] = meta.get("description") or ""
        kids.append(parsed)
    return kids


def _qoder_ide_sessions() -> Dict[str, Dict[str, Any]]:
    """Per-session enrichment from the IDE's mirror database, keyed by id.

    The IDE projects the same SDK sessions into SQLite (its message rows are
    marked source="sdk-projection" and reuse the JSONL uuids), so this is used
    ONLY to enrich -- never as a second source of sessions. What it adds is a
    human-readable title, which the JSONL has nowhere.

    Best-effort by design: opened read-only, and a missing, locked or
    schema-changed database degrades to CLI-only data rather than failing the
    scan. Credential tables are never touched.

    Known limitation: `session_kind` also admits `sideChat` and
    `automationExecution`. Every observed row is `standard` and its id matches a
    transcript, so there is no evidence either kind skips the JSONL -- but if
    one does, it would be invisible here. Unioning on session_id would cover it;
    that is deliberately not built against a shape nobody has seen yet.
    """
    db = QODER_IDE_DIR / "main.sqlite"
    if not db.exists():
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    conn = None
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=1.0)
        for row in conn.execute(
            "SELECT session_id, title, session_kind, product_mode, archived "
            "FROM chat_sessions WHERE deleted_at IS NULL"
        ):
            sid = row[0]
            if isinstance(sid, str) and sid:
                out[sid] = {
                    "title": (row[1] or "").strip(),
                    "session_kind": row[2] or "standard",
                    "product_mode": row[3] or "coding",
                    "archived": bool(row[4]),
                }
        for row in conn.execute(
            "SELECT session_id, "
            "       SUM(COALESCE(json_extract(payload_json,'$.durationMs'),0)), "
            "       COUNT(*) "
            "FROM chat_session_messages "
            "WHERE json_extract(payload_json,'$.role')='assistant' "
            "GROUP BY session_id"
        ):
            entry = out.get(row[0])
            if entry is not None:
                entry["duration_ms"] = int(row[1] or 0)
                entry["turn_count"] = int(row[2] or 0)
    except (sqlite3.Error, ValueError):
        return out
    finally:
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass
    return out


def _scan_qoder_sessions() -> List[Dict[str, Any]]:
    """Scan Qoder sessions under ~/.qoder/projects/.

    Layout: projects/<slugged-cwd>/<session-uuid>.jsonl, with child transcripts
    one level deeper at projects/<slugged-cwd>/<session-uuid>/subagents/*.jsonl.
    The glob is deliberately ROOT-LEVEL ONLY (`*/*.jsonl`): a recursive walk
    would return every subagent transcript as a session of its own, which on a
    two-session install already inflates the count to four.

    The directory slug is NOT reversible -- Qoder replaces "/" with "-" without
    escaping dashes already in the path, so
    "-Users-dev-Documents-Qoder-2026-08-30-d5db2e1b" has several valid readings.
    The project comes from the records' own `cwd` (or the workspace-directories
    header) instead.

    Tokens are reported as an honest zero. Qoder records none (see the module
    comment above) and bills in credits, which ride in the per-session "qoder"
    blob and drive the panel meter -- the same treatment Copilot's AIU gets.
    Under billing_mode "subscription" a $0.00 cost is the correct reading, not
    a missing value.
    """
    if not QODER_PROJECTS_DIR.is_dir():
        return []

    aliases = _load_project_aliases()
    ide = _qoder_ide_sessions()
    out: List[Dict[str, Any]] = []

    for transcript in sorted(QODER_PROJECTS_DIR.glob("*/*.jsonl")):
        parsed = _qoder_parse_session(transcript)
        if not parsed:
            continue
        # Belt and braces: the glob depth already excludes children, and the
        # records flag them too.
        if parsed["is_sidechain"]:
            continue

        sid = parsed["id"]
        meta = ide.get(sid) or {}
        kids = _qoder_subagents(transcript.parent / transcript.stem)

        display = (meta.get("title") or parsed["display"]
                   or f"Qoder session {sid[-8:]}")
        # Qoder titles a thread with the user's whole first message when the
        # IDE has not named it, so cap what is user-authored.
        if len(display) > 120:
            display = display[:117] + "..."

        blob: Dict[str, Any] = {
            "credits": parsed["credits"],
            "original_credits": parsed["original_credits"],
            "billable_turns": parsed["billable_turns"],
            "assistant_turns": parsed["assistant_turns"],
            "context_usage_ratio": parsed["context_usage_ratio"],
            "entrypoint": parsed["entrypoint"] or "cli",
            "git_branch": parsed["git_branch"],
            "cli_version": parsed["cli_version"],
            "skills_available": parsed["skills_available"],
            "mcp_servers": parsed["mcp_servers"],
            "hook_events": parsed["hook_events"],
        }
        for key in ("session_kind", "product_mode", "duration_ms", "turn_count"):
            if key in meta:
                blob[key] = meta[key]

        sess: Dict[str, Any] = {
            "id": sid,
            "agent": "qoder",
            "project": aliases.get(parsed["project"], parsed["project"]),
            "timestamp": parsed["timestamp"],
            "display": display,
            "text": parsed["display"],
            # Not a scan failure: Qoder records no token counts at all.
            "tokens": {"input": 0, "output": 0, "cached": 0,
                       "cache_creation": 0, "reasoning": 0, "total": 0},
            "cost": 0.0,
            "model": parsed["model"],
            "provider": "qoder",
            "mcp_tools": [t for t in parsed["tool_counts"] if t.startswith("mcp")],
            "has_plan": False,
            "plans": [],
            "artifacts": [{"name": transcript.name, "path": str(transcript),
                           "type": "document"}],
            "qoder": blob,
        }

        if kids:
            subagents = [{
                "agent_id": kid["id"],
                "agent_type": kid["agent_type"],
                "description": kid["description"],
                "model": kid["model"],
                "tokens": {"input": 0, "output": 0, "cached": 0,
                           "cache_creation": 0, "reasoning": 0, "total": 0},
                "cost": 0.0,
                "credits": kid["credits"],
            } for kid in kids]
            delegated_credits = round(sum(k["credits"] for k in kids), 6)
            by_type: Dict[str, Dict[str, Any]] = {}
            for kid in kids:
                slot = by_type.setdefault(
                    kid["agent_type"], {"count": 0, "total": 0, "cost": 0.0, "credits": 0.0})
                slot["count"] += 1
                slot["credits"] = round(slot["credits"] + kid["credits"], 6)
            sess["delegation"] = {
                "supported": True,
                # Credits, not tokens -- the delegated spend is real, it just
                # isn't denominated in tokens anywhere in Qoder.
                "tokens_recorded": False,
                "spawn_count": len(subagents),
                "subagents": subagents,
                "delegated_total": 0,
                "delegated_cost": 0.0,
                "delegated_credits": delegated_credits,
                "by_type": by_type,
            }
            blob["delegated_credits"] = delegated_credits
            blob["total_credits"] = round(parsed["credits"] + delegated_credits, 6)

        _attach_tool_usage(sess, parsed["tool_counts"])
        out.append(sess)

    return out


def _qoder_session_file(session_id: str) -> Optional[Path]:
    """Locate one Qoder transcript by session id."""
    if not QODER_PROJECTS_DIR.is_dir() or not session_id:
        return None
    if "/" in session_id or "\\" in session_id or ".." in session_id:
        return None
    for match in QODER_PROJECTS_DIR.glob(f"*/{session_id}.jsonl"):
        return match
    return None


def _qoder_trace_events(path: Path) -> List[Dict[str, Any]]:
    """Normalize a Qoder transcript into the Claude-shaped events the trace
    renderer expects.

    Qoder's records are already Claude-shaped, so this filters rather than
    converts. Three things are dropped or rewritten:

      * session metadata (workspace-directories, runtime-config, last-prompt,
        active-leaf) is not a turn;
      * `attachment` records are harness-injected context -- the renderer
        displays Event.attachment if present, so passing them through would
        show the harness's own prompt as conversation;
      * the first human prompt carries an injected <system-reminder> block,
        which is stripped so the user's words are what the trace shows.

    Per-step token chips are suppressed: Qoder's usage block is all zeros, so
    rendering it would imply a measurement that was never taken.
    """
    events: List[Dict[str, Any]] = []
    for row in _parse_session_jsonl_cached(path):
        rtype = row.get("type")
        if rtype == "user":
            # A `user` record is one of three things: a human turn, the result
            # of a tool the assistant called, or a harness injection. Only the
            # last is dropped -- tool results must survive or every tool_use in
            # the trace renders with nothing paired to it.
            content = (row.get("message") or {}).get("content") or []
            results = [b for b in content
                       if isinstance(b, dict) and b.get("type") == "tool_result"]
            if results:
                events.append({
                    "type": "user",
                    "uuid": row.get("uuid"),
                    "timestamp": row.get("timestamp"),
                    "normalized_timestamp": row.get("normalized_timestamp"),
                    "message": {"role": "user", "content": results},
                })
                continue
            text = _qoder_human_text(row)
            if not text:
                continue  # harness injection, not something the user typed
            events.append({
                "type": "user",
                "uuid": row.get("uuid"),
                "timestamp": row.get("timestamp"),
                "normalized_timestamp": row.get("normalized_timestamp"),
                "message": {"role": "user",
                            "content": [{"type": "text", "text": text}]},
            })
        elif rtype == "assistant":
            msg = row.get("message") or {}
            blocks = [b for b in (msg.get("content") or []) if isinstance(b, dict)]
            if not blocks:
                continue
            events.append({
                "type": "assistant",
                "uuid": row.get("uuid"),
                "timestamp": row.get("timestamp"),
                "normalized_timestamp": row.get("normalized_timestamp"),
                "message": {"role": "assistant",
                            "model": msg.get("model"),
                            "content": blocks},
            })
    return events




# Cordis FiberState (vendor/cordis/src/fiber.ts) -> readable names. It is a
# `const enum`, so it inlines to these ordinals at runtime.
_DSH_FIBER_STATES: Dict[int, str] = {
    0: "pending", 1: "loading", 2: "active",
    3: "failed", 4: "disposed", 5: "unloading",
}


def _dsh_lifecycle_events(since_ms: Optional[float] = None,
                          until_ms: Optional[float] = None,
                          limit: int = 500) -> List[Dict[str, Any]]:
    """Read plugin lifecycle transitions from the sidecar, newest last.

    The file is append-only JSONL written by the TT DSH plugin. It is read
    defensively: a missing file (plugin not installed) yields [], and a torn
    final line (we may read mid-append) is skipped rather than raising.

    `from`/`to` are Cordis FiberState values. They arrive as ints because
    FiberState is a `const enum` and inlines numerically, but the plugin writes
    the names too; we accept either and normalise to names.
    """
    if not DSH_LIFECYCLE_FILE.exists():
        return []
    out: List[Dict[str, Any]] = []
    try:
        with open(DSH_LIFECYCLE_FILE, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue  # torn/partial line
                if not isinstance(row, dict):
                    continue
                ts = row.get("ts")
                if not isinstance(ts, (int, float)):
                    continue
                if since_ms is not None and ts < since_ms:
                    continue
                if until_ms is not None and ts > until_ms:
                    continue

                def _state(v):
                    if isinstance(v, str) and v:
                        return v.lower()
                    return _DSH_FIBER_STATES.get(v) if isinstance(v, int) else None

                out.append({
                    "ts": ts,
                    "plugin": row.get("plugin") or row.get("name") or "unknown",
                    "entry_id": row.get("entry_id"),
                    "from": _state(row.get("from")),
                    "to": _state(row.get("to")),
                    "error": row.get("error") or None,
                })
    except OSError:
        return []
    out.sort(key=lambda r: r["ts"])
    return out[-limit:] if limit and len(out) > limit else out


def _dsh_lifecycle_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Roll transitions up into the numbers a UI wants.

    `failed` counts arrivals in the FAILED state -- the Cordis analogue of the
    paper's L-Raise (an activation whose effects were rolled back), which is the
    transition most worth surfacing and the one a state poll would miss.
    """
    plugins: Dict[str, Dict[str, Any]] = {}
    failed = reloads = unloads = 0
    for e in events:
        p = plugins.setdefault(e["plugin"], {"plugin": e["plugin"], "transitions": 0,
                                             "failed": 0, "final_state": None})
        p["transitions"] += 1
        p["final_state"] = e["to"]
        if e["to"] == "failed":
            p["failed"] += 1
            failed += 1
        elif e["to"] == "loading" and e["from"] in ("active", "failed", "disposed"):
            reloads += 1
        elif e["to"] == "unloading":
            unloads += 1
    return {
        "transitions": len(events),
        "plugins": sorted(plugins.values(), key=lambda p: (-p["failed"], p["plugin"])),
        "failed": failed,
        "reloads": reloads,
        "unloads": unloads,
        "first_ts": events[0]["ts"] if events else None,
        "last_ts": events[-1]["ts"] if events else None,
    }


@app.get("/dsh/lifecycle")
async def dsh_lifecycle(session_id: Optional[str] = None, limit: int = 500):
    """Plugin lifecycle transitions recorded by the TT DSH plugin.

    With `session_id`, the window is narrowed to that session's own span, since
    Cordis fibers are runtime-global and carry no session id -- correlation is
    by time and is therefore approximate, which `correlation` states outright
    rather than implying the events belong to the session.
    """
    since = until = None
    correlation = "none"
    if session_id:
        sess_file = _dsh_session_file(session_id)
        if sess_file is None:
            return {"error": "Not found"}
        parsed = _dsh_parse_session(sess_file)
        if parsed:
            rows = _dsh_read_events(sess_file) or []
            created = rows[0].get("createdAt") if rows else None
            if isinstance(created, (int, float)):
                since = created
            until = parsed["timestamp"].timestamp() * 1000
            correlation = "time-window"
    events = _dsh_lifecycle_events(since_ms=since, until_ms=until, limit=limit)
    return {
        "installed": DSH_LIFECYCLE_FILE.exists(),
        "correlation": correlation,
        "events": events,
        **_dsh_lifecycle_summary(events),
    }


def _dsh_session_file(session_id: str) -> Optional[Path]:
    """Locate one DSH session's log by id. The session dir IS the id, so a
    direct glob resolves it without reversing DSH's lossy cwd slug."""
    if not DSH_SESSIONS_DIR.exists() or not session_id or "/" in session_id:
        return None
    for match in DSH_SESSIONS_DIR.glob(f"*/{session_id}/session.jsonl.zstd"):
        return match
    return None


def _dsh_trace_events(path: Path) -> List[Dict[str, Any]]:
    """Normalize a DSH session log into the shared Claude-shaped trace events
    the EventCard renderer expects (same contract as the pi branch).

    DSH's `user/message` stream carries more than real user turns -- the
    harness splices in plugin snapshots (runtime context, sandbox policy) and
    skill catalogs as user-role messages. Only source.kind == "user" is a
    human turn, so the rest are dropped rather than dumped into the trace as
    if the user had typed them.
    """
    rows = _dsh_read_events(path)
    if not rows:
        return []

    events: List[Dict[str, Any]] = []
    for row in rows:
        rtype = row.get("type")
        data = row.get("data")
        if not isinstance(data, dict):
            continue
        norm: Optional[Dict[str, Any]] = None

        if rtype == "user/message":
            if (data.get("source") or {}).get("kind") != "user":
                continue  # plugin/skill-catalog injection, not a human turn
            text = "".join(
                c.get("text", "") for c in (data.get("content") or [])
                if isinstance(c, dict) and c.get("type") == "text"
            )
            if text.strip():
                norm = {"type": "user", "message": {"role": "user",
                        "content": [{"type": "text", "text": text}]}}

        elif rtype == "assistant/message":
            blocks: List[Dict[str, Any]] = []
            for c in ((data.get("message") or {}).get("content") or []):
                if not isinstance(c, dict):
                    continue
                ctype = c.get("type")
                txt = c.get("text") or ""
                if not txt.strip():
                    continue
                if ctype == "reasoning":
                    blocks.append({"type": "thinking", "thinking": txt})
                elif ctype == "text":
                    blocks.append({"type": "text", "text": txt})
            if blocks:
                norm = {"type": "assistant", "message": {"role": "assistant", "content": blocks}}

        elif rtype == "tool/call":
            raw_args = data.get("arguments")
            try:
                parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            except Exception:
                parsed_args = {"raw": raw_args}  # DSH stores args as an unparsed JSON string
            norm = {"type": "assistant", "message": {"role": "assistant", "content": [{
                "type": "tool_use",
                "id": data.get("callId"),
                "name": data.get("name"),
                "input": parsed_args,
            }]}}

        elif rtype == "tool/result":
            message = data.get("message") or {}
            call_id = ((message.get("source") or {}).get("callId"))
            text_parts: List[str] = []
            for block in (message.get("content") or []):
                if not isinstance(block, dict):
                    continue
                if call_id is None:
                    call_id = block.get("toolCallId")
                inner = block.get("content")
                if isinstance(inner, str):
                    text_parts.append(inner)
                elif isinstance(inner, list):
                    text_parts.extend(
                        b.get("text", "") for b in inner
                        if isinstance(b, dict) and b.get("type") == "text"
                    )
            norm = {"type": "user", "message": {"role": "user", "content": [{
                "type": "tool_result",
                "tool_use_id": call_id,
                "content": "".join(text_parts),
            }]}}

        if norm is None:
            continue
        t = row.get("time")
        if isinstance(t, (int, float)) and t > 0:
            norm["normalized_timestamp"] = t
        norm.setdefault("normalized_timestamp", len(events) * 1000)
        events.append(norm)

    return events


def _reconstruct_vscode_chat_jsonl(path) -> Dict[str, Any]:
    """Reconstruct a Copilot chat session object from VS Code's newer .jsonl
    delta-log format (VS Code ~1.100+ writes <id>.jsonl instead of <id>.json).

    The file is an append-only event log, not a single JSON object:
      - kind 0: full session snapshot (base state); v is the session dict.
      - kind 1: SET the value at key-path k (e.g. ["customTitle"]).
      - kind 2: APPEND/extend the array at key-path k (e.g. ["requests"]).
    Replaying these yields a dict shaped like the legacy single-object .json,
    so the existing per-request extraction below works unchanged.
    """
    data: Dict[str, Any] = {}

    def _navigate(root, keys):
        cur = root
        for key in keys:
            if isinstance(cur, dict):
                cur = cur.get(key)
            elif isinstance(cur, list) and isinstance(key, int) and 0 <= key < len(cur):
                cur = cur[key]
            else:
                return None
        return cur

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            kind = ev.get("kind")
            k = ev.get("k")
            v = ev.get("v")
            if kind == 0:
                if isinstance(v, dict):
                    data = v
                continue
            if kind not in (1, 2) or not isinstance(k, list) or not k:
                continue
            parent = _navigate(data, k[:-1]) if len(k) > 1 else data
            leaf = k[-1]
            if isinstance(parent, dict):
                if kind == 1:
                    parent[leaf] = v
                else:  # append/extend the array at leaf
                    arr = parent.get(leaf)
                    if not isinstance(arr, list):
                        arr = []
                        parent[leaf] = arr
                    arr.extend(v) if isinstance(v, list) else arr.append(v)
            elif isinstance(parent, list) and isinstance(leaf, int):
                if kind == 1 and 0 <= leaf < len(parent):
                    parent[leaf] = v
                elif kind == 2 and 0 <= leaf < len(parent) and isinstance(parent[leaf], list):
                    parent[leaf].extend(v) if isinstance(v, list) else parent[leaf].append(v)
    return data


def _opencode_resolve_model(val):
    """Resolve an OpenCode model name from a model payload.

    OpenCode stores the model in several shapes depending on provider and
    version: a dict (assistant/user message `model`, or the session-level
    `model` column), a JSON-encoded string of that dict, or a plain model
    string. The session-level blob uses the key ``id`` (e.g.
    ``{"id":"claude-opus-4.6","providerID":"github-copilot"}``) while message
    payloads use ``modelID`` — so we try both. Returns None if nothing usable.
    """
    if not val:
        return None
    if isinstance(val, str):
        s = val.strip()
        if s.startswith("{"):
            try:
                val = json.loads(s)
            except Exception:
                return s or None
        else:
            return s or None
    if isinstance(val, dict):
        return (val.get("id") or val.get("modelID") or val.get("modelId")
                or val.get("providerID"))
    return None


# Agents whose local logs record subagent/child-session spawns at all.
# claude: full token rollup; cursor: spawn count only (transcripts carry no
# usage fields); opencode/hermes: parent/child linkage between real sessions;
# grok: subagents/<id>/meta.json spawn records, children are sibling sessions;
# codex: child rollouts carry thread_source="subagent" + parent thread id;
# antigravity: parent brain transcript INVOKE_SUBAGENT steps name the child
# conversation ids. (All verified empirically by running the CLIs — see
# DESIGN.md "probe findings".)
# qoder: subagents/<name>.jsonl beside the parent transcript, with a sibling
# .meta.json naming the agent type and the task — spend per child is real, but
# denominated in credits rather than tokens.
_DELEGATION_CAPABLE_AGENTS = {"claude", "cursor", "opencode", "hermes",
                              "grok", "codex", "antigravity", "cline", "qoder"}


# content is JSON-escaped inside the INVOKE_SUBAGENT step record, so the quote
# before the uuid may appear as \" in the raw line.
_AG_CONVERSATION_ID_RE = re.compile(
    r'conversationId\\?["\']?\s*:\s*\\?["\']'
    r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})')


def _antigravity_subagent_children(sid: str) -> List[str]:
    """Child conversation ids spawned by an Antigravity session, from the
    INVOKE_SUBAGENT steps in its brain transcript. Empty when none/no transcript."""
    kids: List[str] = []
    for brain_dir in ANTIGRAVITY_BRAIN_DIRS:
        tpath = brain_dir / sid / ".system_generated" / "logs" / "transcript_full.jsonl"
        if not tpath.exists():
            tpath = brain_dir / sid / ".system_generated" / "logs" / "transcript.jsonl"
        try:
            if not tpath.exists():
                continue
            with open(tpath, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if "INVOKE_SUBAGENT" not in line:
                        continue
                    for cid in _AG_CONVERSATION_ID_RE.findall(line):
                        if cid != sid and cid not in kids:
                            kids.append(cid)
        except Exception:
            continue
    return kids


def _antigravity_link_subagents(sessions: List[Dict[str, Any]]) -> None:
    """Link Antigravity parent conversations to their spawned subagents.

    `agy` supports parallel subagents; each spawn creates a full sibling
    conversation. The parent's brain transcript
    (brain/<id>/.system_generated/logs/transcript.jsonl) records an
    INVOKE_SUBAGENT step whose content embeds the child's conversationId.
    Children are already counted as their own sessions — annotation only.
    """
    ag = {s["id"]: s for s in sessions if s.get("agent") == "antigravity"}
    if not ag:
        return
    for sid, sess in ag.items():
        kids = _antigravity_subagent_children(sid)
        if kids:
            sess["child_session_ids"] = kids
            sess["delegation"] = {"supported": True, "tokens_recorded": False,
                                  "linked_children": len(kids)}
            for cid in kids:
                child = ag.get(cid)
                if child is not None:
                    child["parent_session_id"] = sid


def _antigravity_attach_goals(sessions: List[Dict[str, Any]]) -> None:
    """Attach `/goal` markers to Antigravity sessions.

    `transcript.jsonl` and `transcript_full.jsonl` duplicate each other, so only
    the former is read; reading both would double every goal.
    """
    ag = [s for s in sessions if s.get("agent") == "antigravity"]
    if not ag:
        return
    for sess in ag:
        for brain_dir in ANTIGRAVITY_BRAIN_DIRS:
            tpath = brain_dir / sess["id"] / ".system_generated" / "logs" / "transcript.jsonl"
            try:
                if not tpath.exists():
                    continue
            except OSError:
                continue
            goals = _antigravity_goal_detect(tpath)
            if goals:
                sess["goals"] = goals
            break


# Brain dirs Antigravity itself manages — NOT user-facing artifacts.
_ANTIGRAVITY_INTERNAL_DIRS = {".system_generated", ".agents"}
_ANTIGRAVITY_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def _antigravity_brain_reports(sess_dir: Path, existing_paths: set) -> List[Dict[str, str]]:
    """Surface an Antigravity brain session's human-readable deliverables.

    Antigravity drops markdown reports at the session root and screenshots under
    one or more `screenshots*/` dirs. The base brain scanner only picks up the
    three canonical docs (task/plan/walkthrough) plus root-level media, so the
    audit/QA reports and the screenshot galleries are invisible in the UI. This
    collects them as artifacts:

      - every top-level `*.md` -> type "document"
      - every image under any sibling `screenshots*/` dir -> type "image",
        named "<dir>/<file>" when more than one screenshot dir exists (so the
        gallery they came from is legible), else just the filename.

    Internal Antigravity dirs (.system_generated, .agents) are skipped — they
    hold transcripts/agent state, not deliverables. `existing_paths` (abs path
    strings already added by the caller) dedups against the canonical docs so a
    `task.md` isn't surfaced twice. Sorted docs-first, then screenshots in
    (dir, filename) order. Best-effort — never raises."""
    docs: List[Dict[str, str]] = []
    images: List[Dict[str, str]] = []
    try:
        # Top-level markdown reports (anything beyond the canonical three).
        for md in sorted(sess_dir.glob("*.md")):
            if not md.is_file():
                continue
            ap = str(md)
            if ap in existing_paths:
                continue
            docs.append({"name": md.name, "path": ap, "type": "document"})
        # Screenshot galleries: every `screenshots*/` sibling dir.
        shot_dirs = sorted(
            d for d in sess_dir.iterdir()
            if d.is_dir()
            and d.name.startswith("screenshots")
            and d.name not in _ANTIGRAVITY_INTERNAL_DIRS
        )
        multi = len(shot_dirs) > 1
        for d in shot_dirs:
            for img in sorted(d.iterdir()):
                if not img.is_file() or img.suffix.lower() not in _ANTIGRAVITY_IMAGE_EXTS:
                    continue
                ap = str(img)
                if ap in existing_paths:
                    continue
                name = f"{d.name}/{img.name}" if multi else img.name
                images.append({"name": name, "path": ap, "type": "image"})
    except OSError:
        pass
    return docs + images


# Skill / slash-command invocations (Claude Code). Two structured signals:
#   - assistant tool_use named "Skill" with input.skill = "<name>";
#   - <command-name>/<name></command-name> tags echoed into user lines.
# The tag also fires for built-in CLI commands (/model, /usage, ...) which are
# NOT skills — counting those would drown real skill usage in noise.
_COMMAND_NAME_RE = re.compile(r"<command-name>/?([\w.:-]+)</command-name>")
_BUILTIN_CLI_COMMANDS = {
    "add-dir", "agents", "bashes", "bug", "clear", "compact", "config",
    "context", "cost", "doctor", "exit", "export", "fast", "help", "hooks",
    "ide", "install-github-app", "login", "logout", "mcp", "memory",
    "migrate-installer", "model", "output-style", "permissions", "plan", "plugin",
    "privacy-settings", "quit", "release-notes", "resume", "rewind", "status",
    "statusline", "terminal-setup", "theme", "todos", "upgrade", "usage", "vim",
}


# Codex records no structured skill event (verified on 0.136 by invoking a
# sample skill): activation shows up only as the agent READING the skill's
# SKILL.md through a tool call. The path inside function_call arguments is the
# one reliable breadcrumb — match ".../skills/<name>/SKILL.md" (either slash).
_CODEX_SKILL_RE = re.compile(r'skills[/\\]+([\w.-]+)[/\\]+SKILL\.md')


# IDE-originated Claude Code sessions (VS Code plugin, JetBrains/Rider) prefix
# the first user prompt with editor-context tags — <ide_selection>…,
# <ide_opened_file>…, <ide_diagnostics>… — so the raw first line makes a
# useless session preview (discussion #129). Strip every well-formed
# <ide_*>…</ide_*> block plus harness-injected <system-reminder> blocks
# before taking the preview.
_IDE_CONTEXT_TAG_RE = re.compile(r"<(ide_\w+)>.*?</\1>", re.DOTALL)
_SYSTEM_REMINDER_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)


def _strip_context_tags(text: str) -> str:
    """Remove harness/editor context blocks from a prompt so a preview shows
    what the user actually typed. Unclosed/malformed tags are left alone —
    better to show something than nothing."""
    text = _IDE_CONTEXT_TAG_RE.sub("", text)
    text = _SYSTEM_REMINDER_RE.sub("", text)
    return text.strip()


def _claude_user_prompt_preview(data: Dict[str, Any], limit: int = 200) -> Optional[str]:
    """Human-typed prompt preview from one Claude Code user JSONL line.

    Returns None when the line carries no usable prompt (meta lines, command
    echoes, tool results, or IDE-context-only messages) so callers keep
    scanning later user lines.
    """
    if data.get("isMeta"):
        return None
    msg = data.get("message") if isinstance(data.get("message"), dict) else {}
    uc = msg.get("content")
    if isinstance(uc, list):
        # IDE / attachment messages arrive as content-block lists.
        text = "\n".join(
            b.get("text", "") for b in uc
            if isinstance(b, dict) and b.get("type") == "text"
        )
    elif isinstance(uc, str):
        text = uc
    else:
        return None
    if not text.strip():
        return None
    text = _strip_context_tags(text)
    if (not text
            or text.startswith("<local-command-")
            or text.startswith("<command-name>")
            or text.startswith("Caveat:")):
        return None
    return text[:limit]


def _count_tool(tool_counts: Dict[str, int], name) -> None:
    if name:
        tool_counts[name] = tool_counts.get(name, 0) + 1


def _mcp_usage_from_counts(tool_counts: Dict[str, int]) -> Dict[str, Dict[str, int]]:
    """Group MCP tool-call counts by server. Non-MCP names skipped.

    Naming conventions differ per agent (both verified in real logs):
      - claude/cursor/qwen-style: mcp__<server>__<tool>  (double underscore)
      - gemini-style: mcp_<server>_<tool>, sometimes wrapped as
        default_api:mcp_<server>_<tool>; servers may contain dashes
        (local-server) so only the FIRST underscore after the server splits.
    """
    out: Dict[str, Dict[str, int]] = {}
    for name, n in tool_counts.items():
        if not isinstance(name, str):
            continue
        raw = name
        if raw.startswith("default_api:"):
            raw = raw[len("default_api:"):]
        server_name = tool = None
        if raw.startswith("mcp__"):
            parts = raw.split("__", 2)
            if len(parts) == 3 and parts[1] and parts[2]:
                server_name, tool = parts[1], parts[2]
        elif raw.startswith("mcp_"):
            rest = raw[len("mcp_"):]
            if "_" in rest:
                server_name, tool = rest.split("_", 1)
        if not server_name or not tool:
            continue
        server = out.setdefault(server_name, {})
        server[tool] = server.get(tool, 0) + n
    return out


def _attach_tool_usage(sess: Dict[str, Any], tool_counts: Dict[str, int],
                       skill_counts: Optional[Dict[str, int]] = None) -> None:
    """Attach tool_counts / mcp_usage / skills_used to a session dict (only when
    non-empty, so agents without the signal simply lack the keys)."""
    if tool_counts:
        sess["tool_counts"] = tool_counts
        mcp = _mcp_usage_from_counts(tool_counts)
        if mcp:
            sess["mcp_usage"] = mcp
    if skill_counts:
        sess["skills_used"] = [
            {"name": k, "count": v}
            for k, v in sorted(skill_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ]


def _rollup_agent_transcript(f: Path, agent_type: Optional[str] = None,
                             description: Optional[str] = None,
                             tool_use_id: Optional[str] = None,
                             extra: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Parse ONE Claude subagent/workflow transcript file into a usage entry.

    Each transcript runs its own context and often a DIFFERENT model than the
    parent (e.g. Explore on Haiku under an Opus session), so cost is computed
    per file with that file's model. ``cached`` remains the per-transcript
    high-water mark for display, while ``_cached_sum`` is the cumulative billed
    cache-read volume. Cache writes are billed per event and accumulate.
    Returns None if the file can't be read.

    Shared by _claude_subagent_usage (flat Task/Agent transcripts) and
    _claude_workflow_entries (dynamic-workflow agents) so the token/cost math
    can't drift between the two.
    """
    tokens = {"input": 0, "output": 0, "cached": 0, "_cached_sum": 0, "cache_creation": 0,
              "cache_creation_1h": 0, "total": 0}
    model = None
    seen_message_ids: set = set()
    try:
        with open(f, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    data = json.loads(line)
                except Exception:
                    continue
                if data.get("type") != "assistant":
                    continue
                msg = data.get("message", {}) if isinstance(data.get("message"), dict) else {}
                m = msg.get("model")
                if m and m != "<synthetic>" and not model:
                    model = m
                # Fallback identity when meta.json is missing/corrupt.
                if not agent_type and data.get("attributionAgent"):
                    agent_type = data.get("attributionAgent")
                usage = msg.get("usage", {}) if isinstance(msg.get("usage"), dict) else {}
                if not usage:
                    continue
                message_id = msg.get("id")
                if message_id:
                    if message_id in seen_message_ids:
                        continue
                    seen_message_ids.add(message_id)
                cr = usage.get("cache_read_input_tokens", 0) or 0
                cc = usage.get("cache_creation_input_tokens", 0) or 0
                cc_1h = (usage.get("cache_creation", {}) or {}).get("ephemeral_1h_input_tokens", 0) or 0
                tokens["input"] += usage.get("input_tokens", 0) or 0
                tokens["output"] += usage.get("output_tokens", 0) or 0
                tokens["cached"] = max(tokens["cached"], cr)
                tokens["_cached_sum"] += cr
                tokens["cache_creation"] += cc
                tokens["cache_creation_1h"] += cc_1h
    except Exception:
        return None
    tokens["total"] = tokens["input"] + tokens["output"] + tokens["cached"]
    cost = calculate_cost(model, tokens["input"], tokens["output"], tokens["_cached_sum"],
                          cache_creation_tokens=tokens["cache_creation"],
                          cache_creation_1h_tokens=tokens["cache_creation_1h"])
    entry = {
        "agent_id": f.stem[len("agent-"):],
        "agent_type": agent_type or "unknown",
        "description": description,
        "tool_use_id": tool_use_id,
        "model": model,
        "tokens": tokens,
        "cost": cost,
    }
    if extra:
        entry.update(extra)
    return entry


def _claude_workflow_entries(sub_dir: Path) -> List[Dict[str, Any]]:
    """Dynamic-workflow (Workflow tool) subagent usage for one Claude session.

    The Workflow tool writes each spawned agent one level deeper than a normal
    Task subagent:
      <sid>/subagents/workflows/wf_<id>/agent-<agentId>.jsonl
    with a sibling journal.jsonl whose {"type":"result", agentId, result} lines
    map an agent to a human label (its phase/area). These files are NEVER
    discovered as sessions (the session glob is non-recursive), and the flat
    subagents/ scanner only globs agent-*.jsonl one directory shallower, so
    without this pass their tokens and cost are counted NOWHERE — the parent
    trace, delegation overlay, and analytics all undercount by the full
    workflow. Count-once still holds: these are files inside the parent's dir,
    not sessions.
    """
    out: List[Dict[str, Any]] = []
    wf_root = sub_dir / "workflows"
    try:
        if not wf_root.is_dir():
            return out
    except Exception:
        return out
    for wf_dir in sorted(wf_root.glob("wf_*")):
        # journal maps agentId -> a human label. result is usually a dict
        # ({area, summary, ...}) but is a plain string for some agents, so
        # guard the type before .get() or it raises.
        labels: Dict[str, str] = {}
        try:
            with open(wf_dir / "journal.jsonl", "r", encoding="utf-8", errors="replace") as jf:
                for line in jf:
                    try:
                        j = json.loads(line)
                    except Exception:
                        continue
                    if j.get("type") != "result":
                        continue
                    aid = j.get("agentId")
                    res = j.get("result")
                    if isinstance(res, dict):
                        # Structured agent output — pull whatever human label the
                        # agent's schema happens to carry. Some (e.g. verify agents
                        # returning {results:[...]}) have none; that's fine, the row
                        # falls back to the agent id.
                        label = (res.get("area") or res.get("summary") or res.get("label")
                                 or res.get("title") or res.get("name"))
                    elif isinstance(res, str):
                        label = res[:80]
                    else:
                        label = None
                    if aid and label and aid not in labels:
                        labels[aid] = str(label)[:120]
        except Exception:
            pass
        wf_id = wf_dir.name
        for f in sorted(wf_dir.glob("agent-*.jsonl")):
            phase = labels.get(f.stem[len("agent-"):])
            e = _rollup_agent_transcript(
                f, agent_type="workflow-subagent", description=phase,
                extra={"kind": "workflow", "workflow_id": wf_id, "phase": phase},
            )
            if e:
                out.append(e)
    return out


def _claude_subagent_usage(session_file: Path, sid: str) -> Optional[Dict[str, Any]]:
    """Roll up subagent usage (Task/Agent tool AND dynamic workflows) for one
    Claude Code session.

    Claude Code writes each spawned Task subagent's full transcript to
      <project-dir>/<sessionId>/subagents/agent-<agentId>.jsonl
    with a sibling agent-<agentId>.meta.json {agentType, description, toolUseId},
    and each dynamic-workflow agent one level deeper under
      <sessionId>/subagents/workflows/wf_<id>/agent-<agentId>.jsonl.
    None of these are sessions — their usage is counted nowhere else, so this
    rollup is the only place it surfaces (count-once invariant: the parent's own
    token fields stay untouched; delegated usage is a separate bucket).

    Returns None when the session has no subagents/ dir and no workflow agents;
    otherwise {spawn_count, subagents: [...], totals: {...}, by_type, cost,
    workflow_count}.
    """
    sub_dir = session_file.parent / sid / "subagents"
    try:
        if not sub_dir.is_dir():
            return None
    except Exception:
        return None
    entries: List[Dict[str, Any]] = []
    for f in sorted(sub_dir.glob("agent-*.jsonl")):
        agent_type = None
        description = None
        tool_use_id = None
        try:
            with open(f.with_name(f.stem + ".meta.json"), "r", encoding="utf-8") as mf:
                meta = json.load(mf)
            if isinstance(meta, dict):
                agent_type = meta.get("agentType")
                description = meta.get("description")
                tool_use_id = meta.get("toolUseId")
        except Exception:
            pass
        e = _rollup_agent_transcript(f, agent_type=agent_type, description=description,
                                     tool_use_id=tool_use_id, extra={"kind": "task"})
        if e:
            entries.append(e)
    # Dynamic-workflow agents live under subagents/workflows/wf_*/ (see above).
    entries.extend(_claude_workflow_entries(sub_dir))
    if not entries:
        return None
    totals = {"input": 0, "output": 0, "cached": 0, "_cached_sum": 0, "cache_creation": 0,
              "cache_creation_1h": 0, "total": 0}
    by_type: Dict[str, Dict[str, Any]] = {}
    for e in entries:
        for k in totals:
            totals[k] += e["tokens"][k]
        bt = by_type.setdefault(e["agent_type"], {"count": 0, "total": 0, "cost": 0.0})
        bt["count"] += 1
        bt["total"] += e["tokens"]["total"]
        bt["cost"] = round(bt["cost"] + (e["cost"] or 0), 6)
    return {
        "spawn_count": len(entries),
        "workflow_count": sum(1 for e in entries if e.get("kind") == "workflow"),
        "subagents": entries,
        "totals": totals,
        "by_type": by_type,
        "cost": round(sum(e["cost"] or 0 for e in entries), 6),
    }


# --- /loop detection + lifecycle -------------------------------------------
# A loop is a session that scheduled a recurring/self-paced prompt. We detect
# it from the SCHEDULING TOOL CALLS, never the "/loop" marker: a /goal-launched
# loop leaves no /loop breadcrumb but still self-perpetuates via ScheduleWakeup.
# Claude: CronCreate (fixed cron) / ScheduleWakeup (dynamic) / CronDelete (stop).
# The job id lives in the CronCreate tool_RESULT, not its input (verified).
_LOOP_JOB_RE = re.compile(r"\bjob\s+([0-9a-fA-F]{6,})\b")

# Hosted artifact URL Claude Code's Artifact tool prints in its tool_result
# ("Published <path> at https://claude.ai/code/artifact/<uuid>").
_ARTIFACT_URL_RE = re.compile(r"https://claude\.ai/code/artifact/[0-9a-f-]{36}")


def _loop_parse_ts(ts: Any) -> Optional[datetime]:
    if not ts or not isinstance(ts, str):
        return None
    try:
        d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return None


def _cron_to_seconds(cron: Optional[str]) -> Optional[int]:
    """Coarse cadence in seconds for the common 5-field cron shapes we emit.
    Returns None when the expression isn't one we can bound (keeps lifecycle
    honest: an unknown cadence never fakes an 'active' staleness window)."""
    if not cron or not isinstance(cron, str):
        return None
    parts = cron.split()
    if len(parts) != 5:
        return None
    minute, hour, dom, mon, dow = parts
    try:
        if minute.startswith("*/") and hour == "*":
            return int(minute[2:]) * 60          # every N minutes
        if hour.startswith("*/"):
            return int(hour[2:]) * 3600           # every N hours
        if minute.isdigit() and hour == "*":
            return 3600                           # hourly at minute M
        if minute.isdigit() and hour.isdigit() and dom == "*" and mon == "*":
            return 604800 if dow != "*" else 86400  # weekly vs daily
    except (ValueError, IndexError):
        return None
    return None


def _cron_next_fire(expr: str, after: datetime) -> Optional[datetime]:
    """Next wall-clock fire of a 5-field cron STRICTLY after `after`.

    Minimal matcher for the shapes agents emit (*, N, */step, lists, ranges);
    evaluated minute-by-minute in the machine's LOCAL timezone, because that's
    the clock Claude Code's in-memory crons fire on. Scans at most 8 days
    (those crons auto-expire after 7). Returns an aware UTC datetime, or None
    when the expression is unparseable or never matches inside the window.
    """
    fields = str(expr or "").split()
    if len(fields) != 5:
        return None

    def _parse(field: str, lo: int, hi: int) -> Optional[set]:
        vals: set = set()
        for part in field.split(","):
            part, _, step_s = part.strip().partition("/")
            step = int(step_s) if step_s.isdigit() and int(step_s) >= 1 else (1 if not step_s else None)
            if step is None:
                return None
            if part in ("*", ""):
                rng = range(lo, hi + 1)
            elif "-" in part:
                a, _, b = part.partition("-")
                if not (a.isdigit() and b.isdigit()):
                    return None
                rng = range(int(a), int(b) + 1)
            elif part.isdigit():
                rng = range(int(part), int(part) + 1)
            else:
                return None
            vals.update(v for v in rng if lo <= v <= hi and (v - rng.start) % step == 0)
        return vals or None

    mins = _parse(fields[0], 0, 59)
    hours = _parse(fields[1], 0, 23)
    doms = _parse(fields[2], 1, 31)
    months = _parse(fields[3], 1, 12)
    dows = _parse(fields[4], 0, 6)
    if None in (mins, hours, doms, months, dows):
        return None
    t = after.astimezone().replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(8 * 24 * 60):
        # cron weekday: 0=Sunday; Python weekday(): 0=Monday.
        if (t.minute in mins and t.hour in hours and t.day in doms
                and t.month in months and ((t.weekday() + 1) % 7) in dows):
            return t.astimezone(timezone.utc)
        t += timedelta(minutes=1)
    return None


def _annotate_loop_lifecycle(sessions: List[Dict[str, Any]], now: datetime) -> None:
    """Recompute the VOLATILE loop lifecycle from now() for every loop session.

    Detection writes only raw, cacheable facts (mode/cadence/job_id/iterations/
    created_at/last_fired/cancelled). Liveness is wall-clock-derived and must be
    recomputed per request, never cached — an idle loop writes nothing, so a
    cached 'active' would stick forever. State machine, first match wins:
    cancelled -> one-shot-done -> cron-7d-expired -> stale(session ended) ->
    active -> unknown. "unknown" is only the never-fired case (no last_fired to
    age against); an idle dynamic loop with a known last_fired ages into
    "expired" via the cadence-relative grace, not "unknown". Claude crons are
    in-memory and auto-expire 7 days after creation; that ceiling is Claude-only."""
    for s in sessions:
        lp = s.get("loop")
        if not isinstance(lp, dict) or not lp.get("is_loop"):
            continue
        created = _loop_parse_ts(lp.get("created_at"))
        last = _loop_parse_ts(lp.get("last_fired")) or created
        cs = lp.get("cadence_seconds")
        recurring = bool(lp.get("recurring", True))
        expires_at = created + timedelta(days=7) if (recurring and lp.get("mode") == "fixed_cron" and created) else None
        lp["expires_at"] = expires_at.isoformat() if expires_at else None
        if lp.get("cancelled"):
            state, reason = "cancelled", "cancelled"
        elif not recurring and lp.get("iterations", 0) >= 1:
            state, reason = "expired", "one_shot_completed"
        elif expires_at and now > expires_at:
            state, reason = "expired", "cron_expired_7d"
        elif last:
            grace = (cs or 3600) + max(900, int(0.10 * (cs or 3600)))
            if (now - last).total_seconds() <= grace:
                state, reason = "active", None
            else:
                state, reason = "expired", "stale_session_ended"
        else:
            state, reason = "unknown", None
        lp["state"] = state
        lp["active"] = (state == "active")
        lp["expired_reason"] = reason
        # Next scheduled fire, only meaningful while the loop is live. Cron
        # loops project from the cron expression (kept in `cadence`); interval
        # loops project one cadence past the last fire — that instant may
        # already be in the past inside the grace window (wakeups lag their
        # schedule), which the UI renders as "due now" rather than hiding.
        nxt = None
        if state == "active":
            if lp.get("mode") == "fixed_cron":
                nxt = _cron_next_fire(lp.get("cadence") or "", now)
            elif last:
                nxt = last + timedelta(seconds=(cs or 3600))
        lp["next_fire_at"] = nxt.isoformat() if nxt else None


# --- /goal detection (Claude Code) -----------------------------------------
# `/goal` arms a session-scoped Stop hook: each time Claude tries to end its
# turn an evaluator checks the condition, and an unmet condition BLOCKS the
# stop so the agent keeps working. Claude persists no goal state anywhere
# (verified: no files, no DB under ~/.claude), so the transcript is the only
# evidence and all of it is text.
#
# The honesty constraint that shapes this code: there is NO terminal event.
# Nothing is ever written when a goal is met, cleared, or abandoned. So a
# Claude goal may only ever be "armed", "blocked" or "unknown" — never
# "complete". Inferring completion here would be inventing a fact.
# Antigravity wraps the request as <USER_REQUEST>\n/goal <text>/goal\n</...>.
# Matched against the json.dumps'd record, so the newline is the two characters
# \ and n rather than a real newline.
_ANTIGRAVITY_GOAL_RE = re.compile(r"<USER_REQUEST>(?:\\n|\s)*/goal\s+(.{1,400}?)</USER_REQUEST>", re.S)
_GOAL_ARM_RE = re.compile(
    r'session-scoped Stop hook is now active with condition:\s*"?(.{0,400})',
    re.S)
_GOAL_BLOCK_PREFIX = "Stop hook feedback"
# Blocks closer together than this belong to the same burst (the agent being
# pushed back repeatedly on one stop attempt) rather than to separate turns.
# Calibrated against real data rather than guessed: inside a genuine run the
# observed gaps are 42s and below, while the nearest true break is 169s. 120s
# separates them cleanly and makes the longest burst come out at exactly 8,
# which is the documented cap firing. A looser 300s merges the break and
# reports 9, i.e. a cap that appears to have been exceeded.
_GOAL_BURST_GAP_SEC = 120
# Claude Code ends the turn with a warning after this many CONSECUTIVE blocks
# (changelog; overridable in the CLI via CLAUDE_CODE_STOP_HOOK_BLOCK_CAP, and
# absent from the public hooks docs). Used only to flag a burst that looks like
# it hit the ceiling, never to age a goal out.
_GOAL_BLOCK_CAP = 8


def _goal_key(ts: Any, condition: str) -> str:
    """Identity for de-duplication.

    A compacted transcript replays earlier records, so the same arm shows up at
    two line numbers with an identical timestamp and condition.
    """
    return f"{ts}|{hashlib.sha1((condition or '').encode('utf-8', 'replace')).hexdigest()[:12]}"


def _claude_build_goals(arms: List[Dict[str, Any]],
                        blocks: List[Dict[str, Any]],
                        usage_by_arm: Dict[int, Dict[str, int]],
                        model: Optional[str]) -> List[Dict[str, Any]]:
    """Assemble Claude `/goal` records from arm + block breadcrumbs.

    `arms` are already de-duplicated and in file order; each block carries the
    index of the arm that was live when it fired, so a session that armed
    several goals attributes each block to the right one.
    """
    out: List[Dict[str, Any]] = []
    for i, arm in enumerate(arms):
        mine = [b for b in blocks if b.get("arm") == i]
        stamps = [b["ts"] for b in mine if b.get("ts")]
        stamps.sort()

        # Group into bursts: a run of blocks against one stop attempt.
        bursts: List[int] = []
        prev: Optional[datetime] = None
        for s in stamps:
            t = _loop_parse_ts(s)
            if t is None:
                continue
            if prev is not None and (t - prev).total_seconds() <= _GOAL_BURST_GAP_SEC:
                bursts[-1] += 1
            else:
                bursts.append(1)
            prev = t

        u = usage_by_arm.get(i) or {}
        tokens = (u.get("input", 0) + u.get("output", 0) + u.get("cached", 0)) or None
        cond = (arm.get("condition") or "").strip()
        created = arm.get("ts")
        out.append({
            "source": "claude",
            "goal_id": None,
            "objective": cond[:codex_goals.OBJECTIVE_MAX],
            "objective_truncated": len(cond) > codex_goals.OBJECTIVE_MAX,
            "created_at": created,
            "updated_at": (stamps[-1] if stamps else created),
            # Never "complete": Claude emits no terminal event to justify it.
            "state": ("unknown" if not created else ("blocked" if stamps else "armed")),
            "state_source": "inferred",
            "tokens": tokens,
            "duration_seconds": None,
            "token_budget": None,
            # Only the turns that exist BECAUSE a stop was blocked; this is
            # incremental, unlike Codex's whole-goal native count.
            "cost_basis": "attributed_turns",
            "cost": (calculate_cost(model, u.get("input", 0), u.get("output", 0),
                                    u.get("_cached_sum", u.get("cached", 0)),
                                    cache_creation_tokens=u.get("cache_creation", 0),
                                    cache_creation_1h_tokens=u.get("cache_creation_1h", 0))
                     if tokens else None),
            "evidence": {
                "blocks": len(stamps),
                "first_block": stamps[0] if stamps else None,
                "last_block": stamps[-1] if stamps else None,
                "block_bursts": bursts,
                "cap_hit": bool(bursts and max(bursts) >= _GOAL_BLOCK_CAP),
            },
        })
    return out


_CLAUDE_CACHE_FIELDS = (
    "tokens", "model", "cost", "mcp_tools", "has_plan", "plans",
    "delegation", "delegated_cost", "tool_counts", "mcp_usage", "skills_used",
    "loop", "published_artifacts", "goals", "untracked_background",
)


def _claude_cache_payload(sess: Dict[str, Any]) -> Dict[str, Any]:
    """Snapshot the expensive-to-reparse fields of a fully-parsed Claude
    session for the sidecar cache. Deliberately excludes `project` and
    `artifacts` (always recomputed fresh — `project` so project-alias edits
    apply retroactively, `artifacts` so Claude Project Memory files added or
    removed after the last full parse are still reflected) and `id`/`agent`
    (known from the cache key already). Only-if-present (not `.get()`)
    so sessions with no MCP/skill/delegation signal keep lacking those keys
    on a cache hit, same as a fresh parse — see `_attach_tool_usage`."""
    payload = {k: sess[k] for k in _CLAUDE_CACHE_FIELDS if k in sess}
    ts = sess.get("timestamp")
    payload["timestamp"] = ts.isoformat() if isinstance(ts, datetime) else ts
    payload["plans"] = [
        {**p, "timestamp": p["timestamp"].isoformat() if isinstance(p.get("timestamp"), datetime) else p.get("timestamp")}
        for p in (payload.get("plans") or [])
    ]
    return payload


def _apply_claude_cache_hit(sess: Dict[str, Any], cached: Dict[str, Any]) -> None:
    """Inverse of `_claude_cache_payload`: merge a cache hit back into `sess`."""
    for k in _CLAUDE_CACHE_FIELDS:
        if k in cached:
            sess[k] = cached[k]
    ts = cached.get("timestamp")
    if isinstance(ts, str):
        try:
            sess["timestamp"] = datetime.fromisoformat(ts)
        except ValueError:
            pass
    sess["plans"] = [
        {**p, "timestamp": datetime.fromisoformat(p["timestamp"]) if isinstance(p.get("timestamp"), str) else p.get("timestamp")}
        for p in (sess.get("plans") or [])
    ]


_CODEX_CACHE_FIELDS = (
    "tokens", "model", "models_used", "_provider", "cost", "mcp_tools", "has_plan", "plans",
    "text", "tokens_by_day", "tool_counts", "_skill_counts",
    "parent_session_id", "subagent_info", "_raw_cwd",
)


def _codex_cache_payload(sess: Dict[str, Any]) -> Dict[str, Any]:
    """Snapshot the expensive-to-reparse fields of a fully-parsed Codex
    session for the sidecar cache. Excludes `project` (always recomputed
    fresh) and `id`/`agent` (known from the cache key already). Includes
    the RAW `tool_counts`/`_skill_counts` dicts (not the derived
    `mcp_usage`/`skills_used`) because the unconditional post-processing
    loop in `_scan_sessions_sync` derives those from the raw counts for
    every session regardless of cache hit/miss."""
    payload = {k: sess[k] for k in _CODEX_CACHE_FIELDS if k in sess}
    payload["timestamp"] = sess["timestamp"].isoformat() if isinstance(sess.get("timestamp"), datetime) else sess.get("timestamp")
    payload["plans"] = [
        {**p, "timestamp": p["timestamp"].isoformat() if isinstance(p.get("timestamp"), datetime) else p.get("timestamp")}
        for p in (payload.get("plans") or [])
    ]
    return payload


def _apply_codex_cache_hit(sess: Dict[str, Any], cached: Dict[str, Any]) -> None:
    """Inverse of `_codex_cache_payload`: merge a cache hit back into `sess`."""
    for k in _CODEX_CACHE_FIELDS:
        if k in cached:
            sess[k] = cached[k]
    ts = cached.get("timestamp")
    if isinstance(ts, str):
        try:
            sess["timestamp"] = datetime.fromisoformat(ts)
        except ValueError:
            pass
    sess["plans"] = [
        {**p, "timestamp": datetime.fromisoformat(p["timestamp"]) if isinstance(p.get("timestamp"), str) else p.get("timestamp")}
        for p in (sess.get("plans") or [])
    ]


def _scan_sessions_sync():
    sessions = []
    aliases = _load_project_aliases()

    def apply_alias(path: str) -> str:
        return aliases.get(path, path)

    # 1. Claude
    # Modern Claude Code (v1+) writes sessions exclusively to
    #   ~/.claude/projects/<encoded-path>/<uuid>.jsonl
    # and no longer creates history.jsonl.  We therefore discover sessions
    # from the projects/ tree first (works on every OS), then overlay any
    # metadata from history.jsonl if it happens to exist (legacy installs).
    claude_history = CLAUDE_DIR / "history.jsonl"
    claude_sessions: dict = {}
    # Pre-index Claude session files to avoid recursive glob in loop
    claude_file_map: dict = {}
    try:
        for p_dir in (CLAUDE_DIR / "projects").iterdir():
            if p_dir.is_dir():
                for f in p_dir.glob("*.jsonl"):
                    claude_file_map[f.stem] = f
    except Exception: pass

    # Seed one stub per discovered session file (mtime as timestamp).
    for sid, f in claude_file_map.items():
        try:
            ts = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        except Exception:
            ts = _now()
        claude_sessions[sid] = {
            "id": sid, "agent": "claude", "project": "unknown",
            "timestamp": ts, "display": None,
            "tokens": {"input": 0, "output": 0, "cached": 0, "total": 0},
            "mcp_tools": [], "has_plan": False, "plans": [],
            "model": None, "artifacts": [], "stub": True,
        }

    # Optional enrichment: overlay project/display from legacy history.jsonl.
    if claude_history.exists():
        try:
            with open(claude_history, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        sid = data.get("sessionId")
                        if not sid: continue
                        ts = datetime.fromtimestamp(data.get("timestamp") / 1000, tz=timezone.utc) if data.get("timestamp") else _file_mtime_utc(claude_history)
                        if sid not in claude_sessions:
                            # Session only known from history.jsonl (no matching .jsonl file)
                            claude_sessions[sid] = {
                                "id": sid, "agent": "claude",
                                "project": apply_alias(data.get("project", "unknown")),
                                "timestamp": ts, "display": data.get("display"),
                                "tokens": {"input": 0, "output": 0, "cached": 0, "total": 0},
                                "mcp_tools": [], "has_plan": False, "plans": [],
                                "model": None, "artifacts": [], "stub": True,
                            }
                        else:
                            # Overlay metadata only; keep file-derived timestamp if newer
                            sess = claude_sessions[sid]
                            if ts > sess["timestamp"]:
                                sess["timestamp"] = ts
                            if data.get("project"):
                                sess["project"] = apply_alias(data["project"])
                            if data.get("display") and not sess.get("display"):
                                sess["display"] = data["display"]
                    except Exception: continue
        except Exception: pass

    # Derive project/display from session file content for stubs still unknown.
    for sid, sess in claude_sessions.items():
        if sess["project"] != "unknown" and sess.get("display"):
            continue
        session_file = claude_file_map.get(sid)
        if not session_file:
            continue
        try:
            with open(session_file, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        data = json.loads(line)
                    except Exception: continue
                    if sess["project"] == "unknown" and data.get("cwd"):
                        sess["project"] = apply_alias(data["cwd"])
                    if not sess.get("display"):
                        if data.get("type") == "summary" and data.get("summary"):
                            sess["display"] = str(data["summary"])[:120]
                        elif data.get("type") == "user":
                            preview = _claude_user_prompt_preview(data)
                            if preview:
                                sess["display"] = preview
                    if sess["project"] != "unknown" and sess.get("display"):
                        break
        except Exception: pass

    # Sort by recency (newest first) — every discovered session is parsed
    # (or cache-hit) below, no truncation. Sorting here only affects the
    # order sessions are processed in, not which ones are included.
    if claude_sessions:
        for sid, sess in sorted(claude_sessions.items(), key=lambda kv: kv[1]["timestamp"], reverse=True):
            session_file = claude_file_map.get(sid)
            if session_file:
                # Discover Claude Project Memory artifacts
                try:
                    memory_dir = session_file.parent.parent / "memory"
                    if memory_dir.exists():
                        for mf in memory_dir.glob("*.md"):
                            sess["artifacts"].append({"name": mf.name, "path": str(mf), "type": "document"})
                except Exception: pass

                cached = None
                source_mtime = None
                try:
                    source_mtime = session_file.stat().st_mtime
                    # Delegation usage comes from separate subagent transcript
                    # files (see _claude_subagent_usage), so freshness must key
                    # on them too: a background subagent can finish AFTER the
                    # parent's last write, and keying on the parent alone would
                    # serve its stale (undercounted) delegation totals forever.
                    sub_dir = session_file.parent / sid / "subagents"
                    if sub_dir.is_dir():
                        for sub_f in sub_dir.glob("agent-*.jsonl"):
                            try:
                                source_mtime = max(source_mtime, sub_f.stat().st_mtime)
                            except OSError:
                                continue
                        # Dynamic-workflow agents (subagents/workflows/wf_*/) run in
                        # the background and often finish AFTER the parent's last
                        # write; without them here the cache serves a stale
                        # undercount of delegated tokens forever.
                        for sub_f in sub_dir.glob("workflows/wf_*/agent-*.jsonl"):
                            try:
                                source_mtime = max(source_mtime, sub_f.stat().st_mtime)
                            except OSError:
                                continue
                    cached = scan_cache.read_cache("claude", sid, source_mtime)
                except OSError:
                    cached = None

                if cached is not None:
                    _apply_claude_cache_hit(sess, cached)
                    sess["stub"] = False
                else:
                    tool_counts: Dict[str, int] = {}
                    skill_counts: Dict[str, int] = {}
                    last_real_ts = None
                    loop_sched: List[Dict[str, Any]] = []   # scheduling tool calls (CronCreate/ScheduleWakeup)
                    loop_cancels: List[Dict[str, Any]] = []  # CronDelete / ScheduleWakeup stop
                    loop_prompts: set = set()                # loop prompt text, to count re-injected fires
                    loop_fires: List[str] = []               # ts of each re-injected fire
                    in_loop_span = False                     # inside a loop-fire response turn right now
                    loop_usage = {"input": 0, "output": 0, "cached": 0, "_cached_sum": 0,
                                  "cache_creation": 0, "cache_creation_1h": 0}  # loop's OWN footprint
                    artifact_calls: Dict[str, Dict[str, Any]] = {}  # Artifact tool_use_id -> input meta
                    published_arts: Dict[str, Dict[str, Any]] = {}  # hosted url -> published-artifact record
                    goal_arms: List[Dict[str, Any]] = []     # /goal arms, de-duplicated
                    goal_arm_keys: set = set()               # (ts, condition) seen — compaction replays them
                    goal_blocks: List[Dict[str, Any]] = []   # each blocked stop, tagged with its arm
                    goal_span_arm: Optional[int] = None      # arm index owning the current post-block span
                    goal_usage_by_arm: Dict[int, Dict[str, int]] = {}  # arm idx -> attributed footprint
                    seen_assistant_message_ids: set = set()
                    untracked_background = {"recaps": 0, "titles": 0, "compactions": 0}
                    try:
                        with open(session_file, "r", encoding="utf-8", errors="replace") as f:
                            for line in f:
                                try:
                                    data = json.loads(line)
                                except Exception: continue
                                if data.get("type") == "ai-title":
                                    untracked_background["titles"] += 1
                                elif data.get("type") == "system":
                                    if data.get("subtype") == "away_summary":
                                        untracked_background["recaps"] += 1
                                    elif data.get("subtype") == "compact_boundary":
                                        untracked_background["compactions"] += 1
                                if data.get("type") in ("user", "assistant") and data.get("timestamp"):
                                    last_real_ts = data["timestamp"]
                                if data.get("type") == "assistant":
                                    msg = data.get("message", {})
                                    m = msg.get("model")
                                    if m and m != "<synthetic>" and not sess.get("model"):
                                        sess["model"] = m
                                    usage = msg.get("usage", {})
                                    if usage:
                                        message_id = msg.get("id")
                                        if message_id:
                                            if message_id in seen_assistant_message_ids:
                                                continue
                                            seen_assistant_message_ids.add(message_id)
                                        cr = usage.get("cache_read_input_tokens", 0) or 0
                                        cc = usage.get("cache_creation_input_tokens", 0) or 0
                                        cc_1h = (usage.get("cache_creation", {}) or {}).get("ephemeral_1h_input_tokens", 0) or 0
                                        sess["tokens"]["input"]  += usage.get("input_tokens", 0) or 0
                                        sess["tokens"]["output"] += usage.get("output_tokens", 0) or 0
                                        sess["tokens"]["cached"] = max(sess["tokens"]["cached"], cr)
                                        sess["tokens"]["_cached_sum"] = sess["tokens"].get("_cached_sum", 0) + cr
                                        sess["tokens"]["cache_creation"] = sess["tokens"].get("cache_creation", 0) + cc
                                        sess["tokens"]["cache_creation_1h"] = sess["tokens"].get("cache_creation_1h", 0) + cc_1h
                                        if in_loop_span:
                                            # This assistant turn is answering a loop fire, so its
                                            # usage is the loop's OWN footprint (not the whole session).
                                            loop_usage["input"] += usage.get("input_tokens", 0) or 0
                                            loop_usage["output"] += usage.get("output_tokens", 0) or 0
                                            loop_usage["cached"] = max(loop_usage["cached"], cr)
                                            loop_usage["_cached_sum"] += cr
                                            loop_usage["cache_creation"] += cc
                                            loop_usage["cache_creation_1h"] += cc_1h
                                        if goal_span_arm is not None:
                                            # This turn exists only because a stop was BLOCKED, so
                                            # it is the goal's incremental cost. Same span technique
                                            # as the loop footprint above.
                                            gu = goal_usage_by_arm.setdefault(goal_span_arm, {
                                                "input": 0, "output": 0, "cached": 0, "_cached_sum": 0,
                                                "cache_creation": 0, "cache_creation_1h": 0})
                                            gu["input"] += usage.get("input_tokens", 0) or 0
                                            gu["output"] += usage.get("output_tokens", 0) or 0
                                            gu["cached"] = max(gu["cached"], cr)
                                            gu["_cached_sum"] += cr
                                            gu["cache_creation"] += cc
                                            gu["cache_creation_1h"] += cc_1h
                                    sess["tokens"]["total"] = sess["tokens"]["input"] + sess["tokens"]["output"] + sess["tokens"]["cached"]
                                    sess["cost"] = calculate_cost(sess.get("model"), sess["tokens"]["input"], sess["tokens"]["output"], sess["tokens"].get("_cached_sum", sess["tokens"]["cached"]), cache_creation_tokens=sess["tokens"].get("cache_creation", 0), cache_creation_1h_tokens=sess["tokens"].get("cache_creation_1h", 0), at=sess["timestamp"])
                                    for item in msg.get("content", []):
                                        if item.get("type") == "tool_use":
                                            tool = item.get("name")
                                            if tool not in sess["mcp_tools"]: sess["mcp_tools"].append(tool)
                                            _count_tool(tool_counts, tool)
                                            if tool == "Skill":
                                                skill = (item.get("input") or {}).get("skill")
                                                if skill:
                                                    skill_counts[skill] = skill_counts.get(skill, 0) + 1
                                            if tool == "ExitPlanMode":
                                                plan_text = (item.get("input") or {}).get("plan") or ""
                                                if plan_text:
                                                    sess["has_plan"] = True
                                                    sess["plans"].append({"session_id": sid, "agent": "claude", "timestamp": sess["timestamp"], "content": plan_text})
                                            if tool == "Artifact":
                                                ip = item.get("input") or {}
                                                # Publishes only — `action: "list"` enumerates existing
                                                # artifacts rather than creating one.
                                                if item.get("id") and ip.get("action") in (None, "publish"):
                                                    artifact_calls[item["id"]] = {
                                                        "title": ip.get("title"),
                                                        "description": ip.get("description"),
                                                        "favicon": ip.get("favicon"),
                                                        "file_path": ip.get("file_path"),
                                                        "ts": data.get("timestamp"),
                                                    }
                                            # /loop detection: scheduling tool calls (see _annotate_loop_lifecycle).
                                            if tool == "CronCreate":
                                                ip = item.get("input") or {}
                                                loop_sched.append({"source": "CronCreate", "mode": "fixed_cron",
                                                                   "cron": ip.get("cron"), "recurring": ip.get("recurring", True),
                                                                   "prompt": ip.get("prompt"), "tool_use_id": item.get("id"),
                                                                   "ts": data.get("timestamp")})
                                                if ip.get("prompt"): loop_prompts.add(str(ip["prompt"])[:120])
                                            elif tool == "ScheduleWakeup":
                                                ip = item.get("input") or {}
                                                if ip.get("stop"):
                                                    loop_cancels.append({"ts": data.get("timestamp")})
                                                else:
                                                    loop_sched.append({"source": "ScheduleWakeup", "mode": "dynamic",
                                                                       "delay": ip.get("delaySeconds"), "recurring": True,
                                                                       "prompt": ip.get("prompt"), "ts": data.get("timestamp")})
                                                    if ip.get("prompt"): loop_prompts.add(str(ip["prompt"])[:120])
                                            elif tool in ("CronDelete", "CronStop"):
                                                ip = item.get("input") or {}
                                                loop_cancels.append({"job_id": ip.get("id") or ip.get("job_id"), "ts": data.get("timestamp")})
                                        if item.get("type") == "thinking":
                                            t_text = item.get("thinking", "")
                                            if "plan" in t_text.lower() and len(t_text) > 100:
                                                sess["has_plan"] = True
                                                sess["plans"].append({"session_id": sid, "agent": "claude", "timestamp": sess["timestamp"], "content": t_text})
                                if data.get("type") == "user":
                                    u_msg = data.get("message", {})
                                    u_content = u_msg.get("content", "")
                                    # /goal breadcrumbs. Deliberately restricted to STRING content
                                    # on a user record: tool_result blocks arrive as lists and can
                                    # quote these markers verbatim (any session that greps its own
                                    # transcript), and assistant prose discussing the feature would
                                    # otherwise be counted as a real block.
                                    _goal_block_now = False
                                    if isinstance(u_content, str) and "Stop hook" in u_content:
                                        _gm = _GOAL_ARM_RE.search(u_content)
                                        if _gm:
                                            _gcond = _gm.group(1).split('". Briefly acknowledge')[0]
                                            _gkey = _goal_key(data.get("timestamp"), _gcond)
                                            if _gkey not in goal_arm_keys:
                                                goal_arm_keys.add(_gkey)
                                                goal_arms.append({"ts": data.get("timestamp"),
                                                                  "condition": _gcond})
                                            goal_span_arm = None
                                        elif u_content.lstrip().startswith(_GOAL_BLOCK_PREFIX) and goal_arms:
                                            # Attribute to the goal that was live at this point; a
                                            # session can arm several in sequence.
                                            goal_blocks.append({"ts": data.get("timestamp"),
                                                                "arm": len(goal_arms) - 1})
                                            goal_span_arm = len(goal_arms) - 1
                                            _goal_block_now = True
                                    if "/plan" in str(u_content):
                                        sess["has_plan"] = True
                                    for cmd in _COMMAND_NAME_RE.findall(str(u_content)):
                                        if cmd not in _BUILTIN_CLI_COMMANDS:
                                            skill_counts[cmd] = skill_counts.get(cmd, 0) + 1
                                    # Published Claude artifacts: pair each Artifact tool_use with
                                    # its tool_result, which carries the hosted URL ("Published
                                    # <path> at https://claude.ai/code/artifact/<uuid>"). Redeploys
                                    # keep the URL, so later publishes upsert the same entry.
                                    if artifact_calls and isinstance(u_content, list):
                                        for blk in u_content:
                                            if not isinstance(blk, dict) or blk.get("type") != "tool_result":
                                                continue
                                            meta = artifact_calls.get(blk.get("tool_use_id"))
                                            if not meta:
                                                continue
                                            rc = blk.get("content")
                                            rtext = rc if isinstance(rc, str) else (
                                                " ".join(b.get("text", "") for b in rc if isinstance(b, dict))
                                                if isinstance(rc, list) else "")
                                            m_url = _ARTIFACT_URL_RE.search(rtext or "")
                                            if not m_url:
                                                continue
                                            url = m_url.group(0)
                                            fname = os.path.basename(meta.get("file_path") or "")
                                            prev = published_arts.get(url, {})
                                            # Later publish wins; keep earlier metadata a redeploy omitted.
                                            published_arts[url] = {
                                                "kind": "page",
                                                "url": url,
                                                "path": meta.get("file_path") or prev.get("path"),
                                                "title": meta.get("title") or prev.get("title")
                                                         or (os.path.splitext(fname)[0] or None),
                                                "description": meta.get("description") or prev.get("description"),
                                                "favicon": meta.get("favicon") or prev.get("favicon"),
                                                "file_name": fname or prev.get("file_name"),
                                                "session_id": sid,
                                                "agent": "claude",
                                                "timestamp": data.get("timestamp") or meta.get("ts") or prev.get("timestamp"),
                                            }
                                    # Loop: pull the CronCreate job id from its tool_result, and
                                    # count each re-injected fire (Claude crons re-inject the prompt
                                    # into THIS same file, verified — so iterations are same-file).
                                    if loop_sched and isinstance(u_content, list):
                                        for blk in u_content:
                                            if not isinstance(blk, dict) or blk.get("type") != "tool_result":
                                                continue
                                            rc = blk.get("content")
                                            rtext = rc if isinstance(rc, str) else (
                                                " ".join(b.get("text", "") for b in rc if isinstance(b, dict))
                                                if isinstance(rc, list) else "")
                                            mjob = _LOOP_JOB_RE.search(rtext or "")
                                            if mjob:
                                                tuid = blk.get("tool_use_id")
                                                for sc in loop_sched:
                                                    if sc.get("tool_use_id") == tuid and not sc.get("job_id"):
                                                        sc["job_id"] = mjob.group(1)
                                    # Loop-fire attribution span. Match the loop prompt ONLY in
                                    # TEXT content — a tool_result that echoes the prompt (e.g. a
                                    # grep of the transcript) is NOT a fire. A fire opens the span;
                                    # a genuine user message closes it; tool_result / injected
                                    # context lines (no text) leave it open, so the whole
                                    # fire-response turn is attributed to the loop.
                                    u_text = u_content if isinstance(u_content, str) else (
                                        " ".join(b.get("text", "") for b in u_content
                                                 if isinstance(b, dict) and b.get("type") == "text")
                                        if isinstance(u_content, list) else "")
                                    is_fire = bool(loop_prompts) and any(lp and lp in u_text for lp in loop_prompts)
                                    if is_fire:
                                        loop_fires.append(data.get("timestamp"))
                                        in_loop_span = True
                                    elif _strip_context_tags(u_text).strip():
                                        in_loop_span = False
                                    # A real user message ends the goal's attributed span; the
                                    # block record itself must not close the span it just opened.
                                    if (not _goal_block_now and goal_span_arm is not None
                                            and _strip_context_tags(
                                                u_content if isinstance(u_content, str) else u_text).strip()):
                                        goal_span_arm = None
                    except Exception: continue
                    if last_real_ts:
                        try:
                            sess["timestamp"] = datetime.fromisoformat(last_real_ts.replace("Z", "+00:00"))
                        except ValueError:
                            pass
                    untracked_total = sum(untracked_background.values())
                    if untracked_total:
                        sess["untracked_background"] = {**untracked_background, "total": untracked_total}
                    if published_arts:
                        sess["published_artifacts"] = sorted(
                            published_arts.values(),
                            key=lambda a: str(a.get("timestamp") or ""), reverse=True)
                    if goal_arms:
                        # Static once the session is written (no wall-clock aging, unlike
                        # loops and unlike Codex's mutable goal status), so this is safe
                        # to cache.
                        sess["goals"] = _claude_build_goals(
                            goal_arms, goal_blocks, goal_usage_by_arm, sess.get("model"))
                    if loop_sched:
                        primary = loop_sched[0]
                        job_id = next((sc.get("job_id") for sc in loop_sched if sc.get("job_id")), None)
                        mode = primary.get("mode")
                        cron = primary.get("cron")
                        delay = primary.get("delay")
                        cadence = cron if mode == "fixed_cron" else (f"~{delay}s heartbeat" if delay else "self-paced")
                        cadence_seconds = _cron_to_seconds(cron) if mode == "fixed_cron" else (int(delay) if isinstance(delay, (int, float)) else None)
                        created_at = primary.get("ts")
                        fire_ts = [t for t in loop_fires if t] + [sc.get("ts") for sc in loop_sched if sc.get("ts")]
                        last_fired = max([t for t in fire_ts if t], default=created_at)
                        prompt = str(primary.get("prompt") or "")
                        # Loop's OWN footprint: usage from the fire-response turns only, NOT
                        # the whole session (a session may do lots of non-loop work).
                        lu = loop_usage
                        # Cost uses cumulative cache reads, while the visible cached count
                        # remains the context high-water mark used by the session header.
                        footprint_cost = calculate_cost(sess.get("model"), lu["input"], lu["output"],
                            lu.get("_cached_sum", lu["cached"]), cache_creation_tokens=lu["cache_creation"],
                            cache_creation_1h_tokens=lu["cache_creation_1h"])
                        # Billed tokens the loop's own turns produced/processed (input+output).
                        # Cache read/write is session context overhead, excluded — so this is the
                        # loop's actual work and is always <= the session's input+output.
                        footprint_tokens = lu["input"] + lu["output"]
                        # Scope cancels to THIS loop — a session may create and
                        # delete several jobs over its life (same hazard the Grok
                        # scanner guards by timing, but Claude deletes DO carry
                        # the target id, so match on it). A ScheduleWakeup stop
                        # (no job_id key at all) halts the session's own
                        # self-pacing, so it counts only for dynamic loops. An
                        # id-carrying delete counts when it names this loop's
                        # job id; when either id is unknown, fall back to the
                        # timing rule — a delete at or before the last fire
                        # cannot have cancelled a still-firing loop. Timestamps
                        # here are same-format Zulu ISO strings from the same
                        # transcript, so lexical order is chronological order.
                        def _cancel_hits(c: Dict[str, Any]) -> bool:
                            if "job_id" not in c:
                                return mode == "dynamic"
                            cid = c.get("job_id")
                            if cid and job_id:
                                return cid == job_id
                            return bool(c.get("ts") and last_fired and str(c["ts"]) > str(last_fired))
                        my_cancels = [c for c in loop_cancels if _cancel_hits(c)]
                        # Raw, cacheable facts only. Lifecycle (state/active/expires_at) is
                        # recomputed per request by _annotate_loop_lifecycle, never cached.
                        sess["loop"] = {
                            "is_loop": True,
                            "mode": mode,
                            "cadence": cadence,
                            "cadence_seconds": cadence_seconds,
                            "recurring": bool(primary.get("recurring", True)),
                            "job_id": job_id,
                            "source_signal": primary.get("source"),
                            "prompt_preview": _strip_context_tags(prompt)[:160],
                            "created_at": created_at,
                            "last_fired": last_fired,
                            "iterations": len(loop_fires),
                            "cancelled": bool(my_cancels),
                            "cancelled_at": (my_cancels[-1].get("ts") if my_cancels else None),
                            "footprint_tokens": footprint_tokens,
                            "footprint_cost": footprint_cost,
                        }
                    _attach_tool_usage(sess, tool_counts, skill_counts)
                    deleg = _claude_subagent_usage(session_file, sid)
                    sess["delegation"] = {
                        "supported": True,
                        "tokens_recorded": True,
                        "spawn_count": deleg["spawn_count"] if deleg else 0,
                        "delegated_total": deleg["totals"]["total"] if deleg else 0,
                    }
                    if deleg:
                        sess["delegation"]["by_type"] = deleg["by_type"]
                        sess["tokens"]["delegated_input"] = deleg["totals"]["input"]
                        sess["tokens"]["delegated_output"] = deleg["totals"]["output"]
                        sess["tokens"]["delegated_cached"] = deleg["totals"]["cached"]
                        sess["tokens"]["delegated_cache_creation"] = deleg["totals"]["cache_creation"]
                        sess["delegated_cost"] = deleg["cost"]

                    if source_mtime is not None:
                        scan_cache.write_cache("claude", sid, source_mtime, _claude_cache_payload(sess))
                    sess["stub"] = False
        sessions.extend(claude_sessions.values())
    # 2. Codex
    codex_index = CODEX_DIR / "session_index.jsonl"
    if codex_index.exists() or (CODEX_DIR / "sessions").is_dir():
        codex_sessions = {}
        # Pre-index Codex rollout files
        codex_file_map = {}
        try:
            for f in (CODEX_DIR / "sessions").rglob("rollout-*.jsonl"):
                parts = f.stem.split("-")
                if len(parts) >= 6:
                    sid = "-".join(parts[-5:])
                    if sid not in codex_file_map:
                        codex_file_map[sid] = []
                    codex_file_map[sid].append(f)
        except Exception: pass

        try:
            with open(codex_index, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        data = json.loads(line); sid = data.get("id")
                        if not sid: continue
                        ts = _aware(datetime.fromisoformat(data.get("updated_at").replace('Z', '+00:00'))) if data.get("updated_at") else _file_mtime_utc(codex_index)
                        if sid not in codex_sessions or ts > codex_sessions[sid]["timestamp"]:
                            codex_sessions[sid] = {"id": sid, "agent": "codex", "project": "unknown", "timestamp": ts, "text": data.get("thread_name"), "tokens": {"input": 0, "output": 0, "cached": 0, "total": 0}, "mcp_tools": [], "has_plan": False, "plans": [], "model": None, "artifacts": [], "stub": True}
                    except Exception: continue
        except Exception: pass

        # The index is no longer maintained by recent Codex versions (observed
        # frozen since codex 0.13x): exec runs and subagent threads never get
        # an entry, and neither do new interactive sessions. Discover every
        # session from the rollout files themselves; the index above only
        # contributes nicer thread names for legacy entries.
        for sid, files in codex_file_map.items():
            if sid in codex_sessions:
                continue
            try:
                ts = max(_file_mtime_utc(f) for f in files)
            except Exception:
                ts = _now()
            codex_sessions[sid] = {"id": sid, "agent": "codex", "project": "unknown", "timestamp": ts, "text": None, "tokens": {"input": 0, "output": 0, "cached": 0, "total": 0}, "mcp_tools": [], "has_plan": False, "plans": [], "model": None, "artifacts": [], "stub": True}
        
        for sid, sess in sorted(codex_sessions.items(), key=lambda kv: kv[1]["timestamp"], reverse=True):
            rollout_files = codex_file_map.get(sid, [])
            rollout_files.sort(key=lambda f: f.name)
            try:
                source_mtime = max(f.stat().st_mtime for f in rollout_files) if rollout_files else None
            except OSError:
                source_mtime = None

            cached = scan_cache.read_cache("codex", sid, source_mtime) if source_mtime is not None else None
            if cached is not None:
                _apply_codex_cache_hit(sess, cached)
                sess["project"] = apply_alias(sess.get("_raw_cwd", "unknown"))
                sess["stub"] = False
                continue

            day_snap = {}

            def record_codex_model(value: Any) -> None:
                """Keep full Codex model IDs in trace order, latest as primary."""
                if not isinstance(value, str) or not value.strip():
                    return
                model_id = value.strip()
                models = sess.setdefault("models_used", [])
                if model_id not in models:
                    models.append(model_id)
                # Codex logs model changes as later turn-context/settings events.
                # The current model is the final observed model, not its provider.
                sess["model"] = model_id

            for rollout_file in rollout_files:
                try:
                    with open(rollout_file, "r", encoding="utf-8", errors="replace") as f:
                        for line in f:
                            try:
                                data = json.loads(line)
                            except Exception: continue
                            if data.get("type") == "session_meta":
                                sess["_raw_cwd"] = data["payload"].get("cwd", "unknown")
                                sess["project"] = apply_alias(sess["_raw_cwd"])
                                record_codex_model(data["payload"].get("model"))
                                if not sess.get("_provider"):
                                    sess["_provider"] = data["payload"].get("model_provider")
                                # Subagent threads (multi_agent feature): the child
                                # rollout's session_meta carries thread_source ==
                                # "subagent" plus source.subagent.thread_spawn with
                                # the parent thread id, depth, role and nickname.
                                # forked_from_id alone is NOT enough — user-initiated
                                # `codex fork` sets it too with thread_source "user".
                                _src = data["payload"].get("source")
                                _spawn = (_src.get("subagent") or {}).get("thread_spawn") if isinstance(_src, dict) else None
                                if data["payload"].get("thread_source") == "subagent" or _spawn:
                                    _spawn = _spawn or {}
                                    _pid = _spawn.get("parent_thread_id") or data["payload"].get("forked_from_id")
                                    if _pid:
                                        sess["parent_session_id"] = _pid
                                    sess["subagent_info"] = {
                                        "role": _spawn.get("agent_role") or data["payload"].get("agent_role"),
                                        "nickname": _spawn.get("agent_nickname") or data["payload"].get("agent_nickname"),
                                        "depth": _spawn.get("depth"),
                                    }
                            if data.get("type") == "turn_context":
                                record_codex_model(data.get("payload", {}).get("model"))
                            if data.get("type") == "event_msg":
                                event_payload = data.get("payload") or {}
                                if event_payload.get("type") == "thread_settings_applied":
                                    settings = event_payload.get("thread_settings") or {}
                                    if isinstance(settings, dict):
                                        record_codex_model(settings.get("model"))
                                ts_str = data.get("timestamp")
                                event_day = None
                                if ts_str:
                                    try:
                                        event_dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                                        event_day = _aware(event_dt).strftime("%Y-%m-%d")
                                    except Exception: pass

                                # Sessions discovered from rollouts (not the stale
                                # index) have no thread_name; first user prompt is
                                # the natural display.
                                if not sess.get("text") and (data.get("payload") or {}).get("type") == "user_message":
                                    _um = data["payload"].get("message")
                                    if isinstance(_um, str) and _um.strip():
                                        sess["text"] = _um.strip()[:120]
                                usage = ((data.get("payload") or {}).get("info") or {}).get("total_token_usage") or {}
                                if usage:
                                    # OpenAI/Codex semantics differ from Anthropic:
                                    #   input_tokens is the GROSS input — it already includes cached_input_tokens.
                                    #   total_tokens = input_tokens + output_tokens (cached is a breakdown, not an
                                    #   independent bucket). Reasoning is typically already in output_tokens for
                                    #   Chat-Completions-style APIs; we add reasoning explicitly only if the record's
                                    #   total_tokens doesn't already account for it.
                                    gross_input = usage.get("input_tokens", 0) or 0
                                    cached_tok  = usage.get("cached_input_tokens", 0) or 0
                                    output      = usage.get("output_tokens", 0) or 0
                                    reasoning   = usage.get("reasoning_output_tokens", 0) or 0
                                    total_record = usage.get("total_tokens", 0) or 0
                                    net_input   = max(0, gross_input - cached_tok)
                                    # If total_tokens > gross_input + output, the API is reporting reasoning as
                                    # extra (not folded into output_tokens). Otherwise reasoning is implicit.
                                    output_billable = output + (reasoning if total_record > gross_input + output else 0)

                                    if event_day:
                                        day_snap[event_day] = (gross_input, cached_tok, output_billable)

                                    sess["tokens"]["input"]  = max(sess["tokens"]["input"],  net_input)
                                    sess["tokens"]["cached"] = max(sess["tokens"]["cached"], cached_tok)
                                    sess["tokens"]["output"] = max(sess["tokens"]["output"], output_billable)
                                    sess["tokens"]["total"]  = sess["tokens"]["input"] + sess["tokens"]["cached"] + sess["tokens"]["output"]
                                    # Codex/OpenAI usage has no cache-write field (only cached read); nothing to pass.
                                    # _provider comes from the rollout's session_meta (model_provider).
                                    # Without it the lookup can't reach PRICING_BY_PROVIDER, so a Codex
                                    # session routed to a non-OpenAI provider was priced off the flat
                                    # table — or by _default when the model id was unknown there.
                                    sess["cost"] = calculate_cost(sess.get("model"), sess["tokens"]["input"], sess["tokens"]["output"], sess["tokens"]["cached"], provider=sess.get("_provider"), at=sess["timestamp"])
                            if data.get("type") == "response_item":
                                if data.get("payload", {}).get("type") == "function_call":
                                    tool = data["payload"].get("name")
                                    if tool not in sess["mcp_tools"]: sess["mcp_tools"].append(tool)
                                    _count_tool(sess.setdefault("tool_counts", {}), tool)
                                    # Skill activation breadcrumb: the agent reads
                                    # <skills-dir>/<name>/SKILL.md (no structured event).
                                    for _skm in _CODEX_SKILL_RE.finditer(data["payload"].get("arguments") or ""):
                                        _sc = sess.setdefault("_skill_counts", {})
                                        _sc[_skm.group(1)] = _sc.get(_skm.group(1), 0) + 1
                                    if tool == "update_plan":
                                        try:
                                            args = json.loads(data["payload"].get("arguments") or "{}")
                                            steps = args.get("plan") or []
                                            if steps:
                                                content = (args.get("explanation") or "") + "\n\n" + "\n".join(
                                                    f"- [{s.get('status','?')}] {s.get('step','')}" for s in steps
                                                )
                                                sess["has_plan"] = True
                                                sess["plans"].append({"session_id": sid, "agent": "codex", "timestamp": sess["timestamp"], "content": content})
                                        except Exception: pass
                except Exception: pass
            
            if day_snap:
                tbd = {}
                pg = pc = po = 0
                # NB: no `or sess.get("_provider")` fallback here. That put a
                # provider id ("openai", "deepseek") into the MODEL slot, where it
                # either matched nothing and fell to _default anyway, or fuzzy-hit
                # an unrelated key. An unknown model should reach _default plainly.
                model_for_cost = sess.get("model")
                for day in sorted(day_snap.keys()):
                    g, c, o = day_snap[day]
                    dg, dc, do = max(0, g - pg), max(0, c - pc), max(0, o - po)
                    pg, pc, po = max(pg, g), max(pc, c), max(po, o)
                    net_in = max(0, dg - dc)
                    tbd[day] = {
                        "input": net_in,
                        "cached": dc,
                        "output": do,
                        "total": net_in + dc + do,
                        # `day` (not the session timestamp) is the right instant here:
                        # a session spanning a repricing gets each day at that day's
                        # rate. Caveat: "YYYY-MM-DD" parses as 00:00 UTC while
                        # DeepSeek's cutover was 16:00 UTC, so the cutover day bills
                        # entirely at the old rate. Deliberate: a day bucket has no
                        # finer timestamp to offer.
                        "cost": calculate_cost(model_for_cost, net_in, do, dc, provider=sess.get("_provider"), at=day)
                    }
                sess["tokens_by_day"] = tbd

            if source_mtime is not None:
                scan_cache.write_cache("codex", sid, source_mtime, _codex_cache_payload(sess))
                sess["stub"] = False
        for s in codex_sessions.values():
            if not s.get("model") and s.get("_provider"):
                s["model"] = s["_provider"]
            s.pop("_provider", None)
            s.pop("_raw_cwd", None)
            mcp = _mcp_usage_from_counts(s.get("tool_counts") or {})
            if mcp:
                s["mcp_usage"] = mcp
            _sc = s.pop("_skill_counts", None)
            if _sc:
                s["skills_used"] = [{"name": k, "count": v}
                                    for k, v in sorted(_sc.items(), key=lambda kv: (-kv[1], kv[0]))]
        # Annotate parents of subagent threads (children are full sessions with
        # their own usage — linkage only, never re-summed).
        for s in codex_sessions.values():
            pid = s.get("parent_session_id")
            if pid and pid in codex_sessions:
                codex_sessions[pid].setdefault("child_session_ids", []).append(s["id"])
        for s in codex_sessions.values():
            kids = s.get("child_session_ids") or []
            if kids:
                s["delegation"] = {"supported": True, "tokens_recorded": False,
                                   "linked_children": len(kids)}
        # Goal Mode (`/goal`). Attached HERE, after the per-session cache
        # branch, precisely because a goal's status is live mutable state
        # (active -> paused -> complete): caching it would freeze the first
        # status we ever saw, the same trap `_annotate_loop_lifecycle` exists
        # to avoid. `thread_id` is the session id verbatim, so this is a
        # straight join. One cheap SQLite read for the whole scan.
        try:
            goals_by_thread = codex_goals.read_goals(CODEX_DIR)
        except Exception:
            goals_by_thread = {}
        if goals_by_thread:
            for s in codex_sessions.values():
                g = goals_by_thread.get(s["id"])
                if g:
                    s["goals"] = g
        sessions.extend(codex_sessions.values())

    # 3 & 7. Gemini & Antigravity
    gemini_projects_file = GEMINI_DIR / "projects.json"
    if gemini_projects_file.exists():
        try:
            with open(gemini_projects_file, "r", encoding="utf-8", errors="replace") as f:
                pj_data = json.load(f).get("projects", {})
                gemini_slugs = set(pj_data.values())
                gemini_slug_to_path = {v: k for k, v in pj_data.items()}

            # Build SHA-256 reverse map: hash(project_path) -> project_path
            # Antigravity stores sessions in ~/.gemini/tmp/{sha256(cwd)}/ directories.
            import hashlib as _hashlib
            _hash_to_path: Dict[str, str] = {}
            for _p in pj_data.keys():
                _hash_to_path[_hashlib.sha256(_p.encode()).hexdigest()] = _p
            # Also scan common locations to resolve hashes for projects not in projects.json
            _scan_roots = [HOME / "Documents" / "Developer", HOME / "Documents", HOME]
            for _root in _scan_roots:
                try:
                    if not _root.is_dir(): continue
                    for _child in _root.iterdir():
                        if _child.is_dir():
                            _cp = str(_child)
                            _hash_to_path[_hashlib.sha256(_cp.encode()).hexdigest()] = _cp
                except Exception: pass

            # Pre-collect all chat session IDs globally to prevent cross-dir duplicates in logs.json
            _all_chat_sids: set = set()
            for _td in (GEMINI_DIR / "tmp").glob("*"):
                _cd = _td / "chats"
                if _cd.is_dir():
                    for _cf in list(_cd.glob("*.json")) + list(_cd.glob("*.jsonl")):
                        try:
                            _d = _parse_gemini_chat_file(_cf)
                            if _d and _d.get("sessionId"):
                                _all_chat_sids.add(_d["sessionId"])
                        except Exception: pass
            _ag_surface = _antigravity_surface_map()  # session id → cli/ide/app, for sub-labels
            _seen_antigravity: set = set()  # global dedup across chat + logs + brain; first discovery wins (ensures real token versions from tmp preferred over brain estimates; kills intra-tmp chat dupes for same sid)

            for tmp_dir in (GEMINI_DIR / "tmp").glob("*"):
                if not tmp_dir.is_dir(): continue
                slug = tmp_dir.name
                # Compute project path and agent type unconditionally (used by both chat and logs scans)
                _is_hash_slug = len(slug) >= 32 and slug not in gemini_slugs
                agent_type = "antigravity" if _is_hash_slug else ("gemini" if slug in gemini_slugs else "antigravity")
                if _is_hash_slug:
                    _resolved = _hash_to_path.get(slug)
                    project_path = apply_alias(_resolved if _resolved else f"System / {slug[:8]}")
                else:
                    project_path = apply_alias(gemini_slug_to_path.get(slug, f"System / {slug[:8]}"))
                chat_dir = tmp_dir / "chats"
                if chat_dir.exists():
                    for cf in list(chat_dir.glob("*.json")) + list(chat_dir.glob("*.jsonl")):
                        try:
                            data = _parse_gemini_chat_file(cf)
                            if not data: continue
                            sid = data.get("sessionId")
                            if not sid: continue
                            # kind="main" means Gemini CLI; absent/other means Antigravity
                            session_kind = data.get("kind")
                            effective_agent = agent_type if session_kind == "main" else "antigravity"
                            ts = _aware(datetime.fromisoformat(data.get("lastUpdated").replace('Z', '+00:00'))) if data.get("lastUpdated") else _file_mtime_utc(cf)
                            tokens = {"input": 0, "output": 0, "cached": 0, "total": 0}
                            mcp_tools = []; has_plan = False; first_msg = ""; plans = []
                            # Must reset per file: this is a plain function-scope local, so a
                            # stale True from an earlier chat file would disable the ghost
                            # filter below for every remaining file in the scan.
                            has_user = False
                            tool_counts: Dict[str, int] = {}
                            skill_counts: Dict[str, int] = {}
                            for msg in data.get("messages", []):
                                if msg.get("type") == "user":
                                    has_user = True
                                    txt = msg.get("content")[0].get("text", "") if isinstance(msg.get("content"), list) else str(msg.get("content"))
                                    if not first_msg: first_msg = txt
                                    if "/plan" in txt: has_plan = True
                                if msg.get("type") == "gemini":
                                    mt = msg.get("tokens", {})
                                    tokens["input"] += mt.get("input", 0); tokens["output"] += mt.get("output", 0)
                                    tokens["cached"] += mt.get("cached", 0); tokens["total"] += mt.get("total", 0)
                                if "toolCalls" in msg:
                                    for tc in msg["toolCalls"]:
                                        if tc.get("name") not in mcp_tools: mcp_tools.append(tc.get("name"))
                                        _count_tool(tool_counts, tc.get("name"))
                                        # Gemini's structured skill signal.
                                        if tc.get("name") == "activate_skill":
                                            _sk = (tc.get("args") or {}).get("name")
                                            if _sk:
                                                skill_counts[_sk] = skill_counts.get(_sk, 0) + 1
                                        if tc.get("name") == "exit_plan_mode":
                                            plan_text = ""
                                            pp = (tc.get("args") or {}).get("plan_path")
                                            if pp:
                                                try: 
                                                    with open(pp, "r", encoding="utf-8", errors="replace") as pf:
                                                        plan_text = pf.read()
                                                except Exception: plan_text = f"(plan stored at {pp})"
                                            if not plan_text:
                                                plan_text = (tc.get("args") or {}).get("plan") or tc.get("resultDisplay") or ""
                                            if plan_text:
                                                has_plan = True
                                                plans.append({"session_id": sid, "agent": effective_agent, "timestamp": ts, "content": plan_text})

                            # Skip "ghost" sessions
                            if not has_user and tokens["total"] == 0 and not mcp_tools:
                                continue

                            model = None
                            for msg in data.get("messages", []):
                                if msg.get("model"): model = msg.get("model"); break
                                if msg.get("modelVersion"): model = msg.get("modelVersion"); break

                            # Discover Antigravity chat-level media artifacts
                            artifacts = []
                            try:
                                art_dir = chat_dir.parent / "artifacts"
                                if art_dir.exists():
                                    for af in art_dir.iterdir():
                                        if af.suffix.lower() in (".mp4", ".mov"): artifacts.append({"name": af.name, "path": str(af), "type": "video"})
                                        elif af.suffix.lower() in (".png", ".webp", ".jpg", ".jpeg"): artifacts.append({"name": af.name, "path": str(af), "type": "image"})
                            except Exception: pass

                            # Antigravity/Gemini token records expose no cache-write field; nothing to pass.
                            tokens["cost"] = calculate_cost(model, tokens["input"], tokens["output"], tokens["cached"], at=ts)
                            if sid in _seen_antigravity: continue
                            _seen_antigravity.add(sid)
                            _g_sess = {"id": sid, "agent": effective_agent, "project": project_path, "timestamp": ts, "display": first_msg[:100], "tokens": tokens, "mcp_tools": mcp_tools, "has_plan": has_plan, "plans": plans, "model": model, "artifacts": artifacts, "antigravity_source": _ag_surface.get(sid), "cost": tokens["cost"]}
                            _attach_tool_usage(_g_sess, tool_counts, skill_counts)
                            sessions.append(_g_sess)
                        except Exception: continue
                # Scan logs.json for Antigravity sessions that have no chat JSON file
                _logs_file = tmp_dir / "logs.json"
                if _logs_file.exists():
                    try:
                        _logs = json.loads(_logs_file.read_text(encoding="utf-8", errors="replace"))
                        _session_msgs: Dict[str, list] = {}
                        _session_last_ts: Dict[str, str] = {}
                        for _le in _logs:
                            _lsid = _le.get("sessionId")
                            if not _lsid or _lsid in _all_chat_sids: continue
                            _session_last_ts[_lsid] = _le.get("timestamp", "")
                            if _le.get("type") == "user":
                                if _lsid not in _session_msgs: _session_msgs[_lsid] = []
                                _session_msgs[_lsid].append(_le)
                        for _lsid, _msgs in _session_msgs.items():
                            if not _msgs or _lsid in _seen_antigravity: continue
                            _first_msg = _msgs[0].get("message", "")
                            _last_ts_str = _session_last_ts.get(_lsid, "")
                            try: _lts = _aware(datetime.fromisoformat(_last_ts_str.replace('Z', '+00:00')))
                            except Exception: _lts = _now()
                            _plans = []; _has_plan = False
                            _plan_dir = tmp_dir / _lsid / "plans"
                            if _plan_dir.exists():
                                for _pf in sorted(_plan_dir.glob("*.md")):
                                    try:
                                        _pt = _pf.read_text(encoding="utf-8", errors="replace")
                                        _has_plan = True
                                        _plans.append({"session_id": _lsid, "agent": "antigravity", "timestamp": _lts, "content": _pt})
                                    except Exception: pass
                            _tkns = {"input": 0, "output": 0, "cached": 0, "total": 0, "cost": 0.0}
                            for _msg in _msgs:
                                toks = len(_msg.get("message", "")) // 4
                                msg_type = _msg.get("type", "")
                                if msg_type in ("assistant", "model"):
                                    _tkns["output"] += toks
                                else:
                                    _tkns["input"] += toks
                            _tkns["total"] = _tkns["input"] + _tkns["output"]
                            if _lsid in _seen_antigravity: continue
                            _seen_antigravity.add(_lsid)
                            sessions.append({"id": _lsid, "agent": "antigravity", "project": project_path, "timestamp": _lts, "display": _first_msg[:100], "tokens": _tkns, "mcp_tools": [], "has_plan": _has_plan, "plans": _plans, "model": None, "artifacts": [], "antigravity_source": _ag_surface.get(_lsid), "cost": 0.0})
                    except Exception: pass
        except Exception: pass

    # 3b. Antigravity brain/ folder — richer per-session artifacts (task/plan/walkthrough)
    _seen_brain_sids: set = set()
    # CLI (`agy`) ground truth: real model + exact project, keyed by session id.
    _ag_cli_meta = _antigravity_cli_meta()
    for _brain_dir in ANTIGRAVITY_BRAIN_DIRS:
        if not _brain_dir.exists(): continue
        for sess_dir in _brain_dir.iterdir():
            try:
                if not sess_dir.is_dir(): continue
                sid = sess_dir.name
                # Dedup: a session may already be captured via the gemini-logs/chat path (real tokens),
                # or appear under more than one brain surface. Skip those so we don't double-count.
                # _seen_antigravity covers prior chat/logs + earlier brain sources; _seen_brain_sids
                # handles overlaps within this brain SOURCES iteration.
                if sid in _seen_antigravity or sid in _seen_brain_sids: continue
                task = plan = walkthrough = ""
                latest_ts = None
                artifacts = []
                doc_arts: List[Dict[str, Any]] = []
                # Scan for base documents as artifacts. These are Antigravity's
                # first-class "Artifacts" (its UI shows them in an Artifacts
                # panel); each has a .metadata.json sidecar with a summary,
                # updatedAt and a userFacing flag. User-facing ones also become
                # `published_artifacts` entries (kind "document") so they show
                # on the project Artifacts tab alongside Claude's hosted pages.
                for fname in ("task.md", "implementation_plan.md", "walkthrough.md"):
                    fp = sess_dir / fname
                    mp = sess_dir / f"{fname}.metadata.json"
                    md_summary = None; md_updated = None; user_facing = True
                    if mp.exists():
                        try:
                            md = json.loads(mp.read_text(encoding="utf-8", errors="replace"))
                            md_summary = md.get("summary")
                            user_facing = md.get("userFacing", True)
                            md_updated = md.get("updatedAt")
                            if md_updated:
                                ts = _aware(datetime.fromisoformat(md_updated.replace("Z", "+00:00")))
                                if latest_ts is None or ts > latest_ts: latest_ts = ts
                        except Exception: pass
                    if fp.exists():
                        artifacts.append({"name": fname, "path": str(fp), "type": "document"})
                        try:
                            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                                body = f.read()
                        except Exception: body = ""
                        if fname == "task.md": task = body
                        elif fname == "implementation_plan.md": plan = body
                        else: walkthrough = body
                        if user_facing:
                            heading = next((ln.lstrip("#").strip() for ln in body.splitlines()
                                            if ln.strip().startswith("#")), None)
                            doc_arts.append({
                                "kind": "document",
                                "path": str(fp),
                                "file_name": fname,
                                "title": heading or {"task.md": "Task List",
                                                     "implementation_plan.md": "Implementation Plan",
                                                     "walkthrough.md": "Walkthrough"}[fname],
                                "description": md_summary,
                                "session_id": sid,
                                "agent": "antigravity",
                                "timestamp": md_updated,
                            })
                
                # Scan for media artifacts at the brain session root (Antigravity drops
                # previews/screenshots here) and optionally in an artifacts/ subdir.
                try:
                    media_dirs = [sess_dir]
                    sub = sess_dir / "artifacts"
                    if sub.exists(): media_dirs.append(sub)
                    for d in media_dirs:
                        for af in d.iterdir():
                            if not af.is_file(): continue
                            ext = af.suffix.lower()
                            if ext in (".mp4", ".mov", ".webm"):
                                artifacts.append({"name": af.name, "path": str(af), "type": "video"})
                            elif ext in (".png", ".webp", ".jpg", ".jpeg", ".gif"):
                                artifacts.append({"name": af.name, "path": str(af), "type": "image"})
                except Exception: pass

                # Markdown reports (giri_audit_report, qa_test_log, …) and the
                # screenshots*/ galleries Antigravity writes alongside the canonical
                # task/plan/walkthrough docs. Dedup against paths already added above.
                _existing_paths = {a["path"] for a in artifacts}
                artifacts.extend(_antigravity_brain_reports(sess_dir, _existing_paths))

                # Pull in a sampled slice of browser_recordings/<sid> frames
                try:
                    rec_dir = GEMINI_DIR / "antigravity" / "browser_recordings" / sid
                    if rec_dir.is_dir():
                        frames = sorted([p for p in rec_dir.iterdir() if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")])
                        total = len(frames)
                        if total:
                            step = max(1, total // 12)  # cap at ~12 thumbnails
                            for p in frames[::step]:
                                artifacts.append({"name": f"frame {p.name}", "path": str(p), "type": "image"})
                except Exception: pass

                # CLI sessions carry a transcript but often none of the IDE artifacts
                # above, so also keep a session if its transcript yields token usage —
                # otherwise it's an empty/aborted dir worth skipping. (computed once,
                # reused in the append below.)
                _ag_tokens = _estimate_antigravity_tokens(sess_dir)
                if not (task or plan or walkthrough or artifacts or _ag_tokens.get("total", 0) > 0): continue
                # Mark seen only now that we're actually appending — a content-less
                # mirror dir must not block the dir that holds this session's content.
                _seen_antigravity.add(sid)
                _seen_brain_sids.add(sid)
                # Prefer the CLI's own records (exact cwd from history.jsonl, real
                # model from the SQLite trajectory); fall back to brain heuristics.
                _cli = _ag_cli_meta.get(sid, {})
                project = apply_alias(_cli.get("project") or _antigravity_infer_project((task or "") + "\n" + (plan or "")))
                first_line = next((ln.strip() for ln in (task or plan or walkthrough).splitlines() if ln.strip() and not ln.strip().startswith("#")), "")
                display = _antigravity_first_prompt(sid, first_line)
                plans: List[dict] = []
                if plan:
                    plans.append({"session_id": sid, "agent": "antigravity", "timestamp": latest_ts or _now(), "content": plan})
                sessions.append({
                    "id": sid,
                    "agent": "antigravity",
                    "project": project,
                    "timestamp": latest_ts or datetime.fromtimestamp(sess_dir.stat().st_mtime, tz=timezone.utc),
                    "display": display,
                    "tokens": _ag_tokens,
                    "mcp_tools": [],
                    "has_plan": bool(plan),
                    "plans": plans,
                    "model": _cli.get("model") or "gemini (antigravity)",
                    "artifacts": artifacts,
                    "antigravity_source": _ag_surface.get(sid),
                    "cost": 0.0,
                    **({"published_artifacts": doc_arts} if doc_arts else {}),
                })
            except Exception: continue

    # 4. Qwen
    if QWEN_DIR.exists():
        for pd in QWEN_DIR.glob("projects/*"):
            if pd.is_dir():
                for cf in pd.glob("chats/*.jsonl"):
                    try:
                        sid = cf.stem; mcp_tools = []; has_plan = False; first_msg = ""; plans = []
                        tokens = {"input": 0, "output": 0, "cached": 0, "total": 0}
                        project_path = "unknown"; last_ts = _file_mtime_utc(cf); model = None
                        artifacts = []; tool_counts = {}; q_skill_counts = {}
                        with open(cf, "r", encoding="utf-8", errors="replace") as f:
                            for line in f:
                                try:
                                    data = json.loads(line); project_path = apply_alias(data.get("cwd", project_path))
                                    if data.get("timestamp"): last_ts = _aware(datetime.fromisoformat(data["timestamp"].replace('Z', '+00:00')))
                                    if data.get("type") == "user":
                                        txt = data.get("message", {}).get("content", "")
                                        if not first_msg and isinstance(txt, str): first_msg = txt
                                        if isinstance(txt, str) and "/plan" in txt: has_plan = True
                                    if data.get("type") == "assistant":
                                        if data.get("message", {}).get("model") and not model:
                                            model = data["message"]["model"]
                                        usage = data.get("message", {}).get("usage", {})
                                        cr = usage.get("cache_read_input_tokens", 0) or 0
                                        cc = usage.get("cache_creation_input_tokens", 0) or 0
                                        cc_1h = (usage.get("cache_creation", {}) or {}).get("ephemeral_1h_input_tokens", 0) or 0
                                        tokens["input"]  += usage.get("input_tokens", 0) or 0
                                        tokens["output"] += usage.get("output_tokens", 0) or 0
                                        tokens["cached"] = max(tokens["cached"], cr)
                                        tokens["_cached_sum"] = tokens.get("_cached_sum", 0) + cr
                                        # cache_creation (write) IS billed per event → cumulative, like input.
                                        tokens["cache_creation"] = tokens.get("cache_creation", 0) + cc
                                        tokens["cache_creation_1h"] = tokens.get("cache_creation_1h", 0) + cc_1h
                                        for item in data.get("message", {}).get("content", []):
                                            if item.get("type") == "tool_use":
                                                if item.get("name") not in mcp_tools: mcp_tools.append(item.get("name"))
                                                _count_tool(tool_counts, item.get("name"))
                                                # qwen is a gemini fork; same structured skill signal.
                                                if item.get("name") == "activate_skill":
                                                    _sk = (item.get("input") or {}).get("name")
                                                    if _sk:
                                                        q_skill_counts[_sk] = q_skill_counts.get(_sk, 0) + 1
                                            if item.get("type") == "thinking":
                                                t_text = item.get("thinking", "")
                                                if "plan" in t_text.lower() and len(t_text) > 100:
                                                    has_plan = True
                                                    plans.append({"session_id": sid, "agent": "qwen", "timestamp": last_ts, "content": t_text})
                                except Exception: continue
                        tokens["total"] = tokens["input"] + tokens["output"] + tokens["cached"]
                        tokens["cost"] = calculate_cost(model, tokens["input"], tokens["output"], tokens.get("_cached_sum", tokens["cached"]), cache_creation_tokens=tokens.get("cache_creation", 0), cache_creation_1h_tokens=tokens.get("cache_creation_1h", 0), at=last_ts)
                        _q_sess = {"id": sid, "agent": "qwen", "project": project_path, "timestamp": last_ts, "display": first_msg[:100], "tokens": tokens, "mcp_tools": mcp_tools, "has_plan": has_plan, "plans": plans, "model": model, "artifacts": artifacts, "cost": tokens["cost"]}
                        _attach_tool_usage(_q_sess, tool_counts, q_skill_counts)
                        sessions.append(_q_sess)
                    except Exception: continue

    # 5. Vibe
    if VIBE_DIR.exists():
        for cf in (VIBE_DIR / "logs" / "session").glob("*.json"):
            try:
                with open(cf, "r", encoding="utf-8", errors="replace") as f:
                    data = json.load(f); meta = data.get("metadata", {}); sid = meta.get("session_id")
                    if not sid: continue
                    ts = _aware(datetime.fromisoformat(meta.get("start_time"))) if meta.get("start_time") else _file_mtime_utc(cf)
                    stats = meta.get("stats", {})
                    tokens = {"input": stats.get("session_prompt_tokens", 0), "output": stats.get("session_completion_tokens", 0), "cached": stats.get("context_tokens", 0), "total": stats.get("session_total_llm_tokens", 0)}
                    mcp_tools = [t.get("function", {}).get("name") for t in meta.get("tools_available", []) if t.get("function", {}).get("name")]
                    model = meta.get("agent_config", {}).get("active_model")
                    project_path = apply_alias(meta.get("environment", {}).get("working_directory", "unknown"))
                    # Vibe stats expose no cache-write field; nothing to pass.
                    tokens["cost"] = calculate_cost(model, tokens["input"], tokens["output"], tokens["cached"], at=ts)
                    sessions.append({"id": sid, "agent": "vibe", "project": project_path, "timestamp": ts, "display": f"Vibe Session {sid[:8]}", "tokens": tokens, "mcp_tools": list(set(mcp_tools)), "has_plan": False, "plans": [], "model": model, "artifacts": [], "cost": tokens["cost"]})
            except Exception: continue

    # 6. Cursor
    if CURSOR_DIR.exists():
        cursor_map = {}
        if CURSOR_STORAGE.exists():
            for ws in CURSOR_STORAGE.glob("*/workspace.json"):
                try:
                    with open(ws, "r", encoding="utf-8", errors="replace") as f:
                        data = json.load(f)
                        folder = data.get("folder")
                        if folder:
                            cursor_map[ws.parent.name] = unquote(folder.replace("file://", ""))
                except Exception: continue

        for pd in (CURSOR_DIR / "projects").glob("*"):
            if pd.is_dir():
                project_path = cursor_map.get(pd.name)
                if not project_path:
                    # Try to match the slug against known paths in the map
                    for p in cursor_map.values():
                        if p.replace("/", "-").strip("-") == pd.name:
                            project_path = p
                            break
                
                if not project_path:
                    # Fallback to slug reconstruction
                    project_path = "/" + pd.name.replace("-", "/")
                
                for trans_dir in (pd / "agent-transcripts").glob("*"):
                    if trans_dir.is_dir():
                        sid = trans_dir.name
                        cf = trans_dir / f"{sid}.jsonl"
                        artifacts = []
                        # Discover Cursor Terminal artifacts
                        try:
                            term_dir = pd / "terminals"
                            if term_dir.exists():
                                for tf in term_dir.glob("*.txt"):
                                    artifacts.append({"name": f"Terminal: {tf.name}", "path": str(tf), "type": "terminal"})
                        except Exception: pass

                        if cf.exists():
                            try:
                                mtime = datetime.fromtimestamp(cf.stat().st_mtime, tz=timezone.utc)
                                first_msg = ""
                                tokens = {"input": 0, "output": 0, "cached": 0, "total": 0}
                                mcp_tools = []
                                tool_counts = {}
                                subagents = []
                                has_plan = False
                                plans = []
                                model = None
                                with open(cf, "r", encoding="utf-8", errors="replace") as f:
                                    for line in f:
                                        try:
                                            data = json.loads(line)
                                        except Exception: continue
                                        msg = data.get("message", {}) if isinstance(data.get("message"), dict) else {}
                                        if data.get("role") == "user" and not first_msg:
                                            c = msg.get("content", [])
                                            if isinstance(c, list) and c:
                                                first_msg = c[0].get("text", "") if isinstance(c[0], dict) else str(c[0])
                                            elif isinstance(c, str):
                                                first_msg = c
                                        if data.get("role") == "assistant":
                                            if msg.get("model") and not model: model = msg.get("model")
                                            usage = msg.get("usage", {}) if isinstance(msg.get("usage"), dict) else {}
                                            cr = usage.get("cache_read_input_tokens", 0) or 0
                                            cc = usage.get("cache_creation_input_tokens", 0) or 0
                                            cc_1h = (usage.get("cache_creation", {}) or {}).get("ephemeral_1h_input_tokens", 0) or 0
                                            tokens["input"]  += usage.get("input_tokens", 0) or 0
                                            tokens["output"] += usage.get("output_tokens", 0) or 0
                                            tokens["cached"] = max(tokens["cached"], cr)
                                            tokens["_cached_sum"] = tokens.get("_cached_sum", 0) + cr
                                            # cache_creation (write) IS billed per event → cumulative, like input.
                                            tokens["cache_creation"] = tokens.get("cache_creation", 0) + cc
                                            tokens["cache_creation_1h"] = tokens.get("cache_creation_1h", 0) + cc_1h
                                            for item in msg.get("content", []) if isinstance(msg.get("content"), list) else []:
                                                if item.get("type") == "tool_use":
                                                    name = item.get("name")
                                                    if name not in mcp_tools: mcp_tools.append(name)
                                                    _count_tool(tool_counts, name)
                                                    if name == "Subagent":
                                                        sub_input = item.get("input") or {}
                                                        sub_name = sub_input.get("name") or sub_input.get("subagent_type")
                                                        if sub_name and sub_name not in subagents:
                                                            subagents.append(sub_name)
                                                if item.get("type") == "thinking":
                                                    t_text = item.get("thinking", "")
                                                    if "plan" in t_text.lower() and len(t_text) > 100:
                                                        has_plan = True
                                                        plans.append({"session_id": sid, "agent": "cursor", "timestamp": mtime, "content": t_text})
                                tokens["total"] = tokens["input"] + tokens["output"] + tokens["cached"]
                                tokens["cost"] = calculate_cost(model, tokens["input"], tokens["output"], tokens.get("_cached_sum", tokens["cached"]), cache_creation_tokens=tokens.get("cache_creation", 0), cache_creation_1h_tokens=tokens.get("cache_creation_1h", 0), at=mtime)
                                # Cursor writes subagent transcripts to <sid>/subagents/
                                # but they carry NO usage fields (verified), so we can
                                # only count spawns — never estimate their tokens.
                                spawn_count = 0
                                try:
                                    spawn_count = sum(1 for _ in (trans_dir / "subagents").glob("*.jsonl"))
                                except Exception: pass
                                delegation = {"supported": True, "tokens_recorded": False,
                                              "spawn_count": max(spawn_count, len(subagents))}
                                _c_sess = {"id": sid, "agent": "cursor", "project": project_path, "timestamp": mtime, "display": first_msg[:100], "tokens": tokens, "mcp_tools": mcp_tools, "subagents": subagents, "has_plan": has_plan, "plans": plans, "model": model, "artifacts": artifacts, "cost": tokens["cost"], "delegation": delegation}
                                _attach_tool_usage(_c_sess, tool_counts)
                                sessions.append(_c_sess)
                            except Exception: continue

    # 7. Copilot
    if VSCODE_STORAGE.exists():
        for ws_folder in VSCODE_STORAGE.glob("*/chatSessions"):
            try:
                workspace_json = ws_folder.parent / "workspace.json"
                project_path = "unknown"
                if workspace_json.exists():
                    with open(workspace_json, "r", encoding="utf-8", errors="replace") as f:
                        wj = json.load(f); folder_url = wj.get("folder")
                        if folder_url: project_path = unquote(folder_url.replace("file://", ""))
                # VS Code ~1.100+ switched session files from <id>.json (single
                # object) to <id>.jsonl (append-only delta log). Scan both so
                # sessions created after that cutover aren't silently dropped.
                session_files = list(ws_folder.glob("*.json")) + list(ws_folder.glob("*.jsonl"))
                for cf in session_files:
                    try:
                        if cf.suffix == ".jsonl":
                            data = _reconstruct_vscode_chat_jsonl(cf)
                        else:
                            with open(cf, "r", encoding="utf-8", errors="replace") as f:
                                data = json.load(f)
                        # VS Code writes a chatSession file the moment the chat
                        # panel opens; files with no requests are phantom
                        # sessions — no prompt, no response, no tokens — that
                        # only pollute the list with empty intents (#129).
                        if not (data.get("requests") or data.get("pendingRequests")):
                            continue
                        sid = cf.stem; tokens = {"input": 0, "output": 0, "cached": 0, "total": 0}
                        first_msg = ""; plans = []; model = None

                        # Fallback to creation date if no requests
                        creation_ts = data.get("creationDate") or data.get("timestamp")
                        last_ts = datetime.fromtimestamp(creation_ts / 1000, tz=timezone.utc) if isinstance(creation_ts, (int, float)) else _file_mtime_utc(cf)

                        for req in data.get("requests", []):
                            msg_text = req.get("message", {}).get("text", "") or ""
                            if not first_msg: first_msg = msg_text
                            if req.get("modelId") and not model:
                                model = req.get("modelId").split("/")[-1]
                            if req.get("timestamp"):
                                ts_val = req.get("timestamp")
                                if isinstance(ts_val, (int, float)):
                                    req_ts = datetime.fromtimestamp(ts_val / 1000, tz=timezone.utc)
                                    if req_ts > last_ts: last_ts = req_ts
                            # Copilot doesn't record input tokens; estimate from prompt chars (~4 chars/token).
                            tokens["input"] += len(msg_text) // 4
                            if "thinking" in req:
                                tokens["output"] += req["thinking"].get("tokens", 0) or 0
                                t_text = req["thinking"].get("text", "")
                                if "plan" in t_text.lower() and len(t_text) > 100:
                                    plans.append({"session_id": sid, "agent": "copilot", "timestamp": last_ts, "content": t_text})
                            # New .jsonl schema records completionTokens per request directly.
                            if isinstance(req.get("completionTokens"), (int, float)):
                                tokens["output"] += int(req["completionTokens"])
                            elif "response" in req:
                                for part in req["response"]: tokens["output"] += part.get("tokens", 0) or 0
                        tokens["total"] = tokens["input"] + tokens["output"] + tokens["cached"]
                        # Copilot (VS Code) chat records expose no cache-write field; nothing to pass.
                        tokens["cost"] = calculate_cost(model, tokens["input"], tokens["output"], tokens["cached"], at=last_ts)
                        sessions.append({"id": sid, "agent": "copilot", "project": project_path, "timestamp": last_ts, "display": first_msg[:100], "tokens": tokens, "mcp_tools": [], "has_plan": len(plans) > 0, "plans": plans, "model": model, "artifacts": [], "copilot_source": "vscode", "cost": tokens["cost"]})
                    except Exception: continue
            except Exception: continue

    # 7b. GitHub Copilot CLI / agent — ~/.copilot/session-state/<id>/events.jsonl.
    # A separate store from the VS Code Copilot chat sessions above; the CLI
    # writes an append-only event log per session (#36). Token usage comes from
    # session.shutdown.modelMetrics when the session has ended, otherwise we sum
    # per-message outputTokens and estimate input from prompt length.
    if COPILOT_CLI_DIR.exists():
        for sess_dir in COPILOT_CLI_DIR.iterdir():
            try:
                if not sess_dir.is_dir(): continue
                ev_file = sess_dir / "events.jsonl"
                if not ev_file.exists(): continue
                rows = _load_copilot_cli_events(ev_file)
                if not rows: continue
                sid = sess_dir.name
                project_path = "unknown"; first_msg = ""; model = None
                models_used: List[str] = []
                out_tokens = 0; in_estimate = 0
                start_ts = None; last_ts = None; shutdown_metrics = None
                for r in rows:
                    et = r.get("type"); d = r.get("data") or {}
                    rts = _parse_copilot_iso(r.get("timestamp"))
                    if rts and (last_ts is None or rts > last_ts): last_ts = rts
                    if et == "session.start":
                        cwd = (d.get("context") or {}).get("cwd")
                        if cwd: project_path = cwd
                        start_ts = _parse_copilot_iso(d.get("startTime")) or rts
                    elif et == "user.message":
                        c = d.get("content") or ""
                        if c and not first_msg: first_msg = c
                        in_estimate += len(c) // 4
                    elif et == "assistant.message":
                        m = d.get("model")
                        if m:
                            if not model: model = m
                            if m not in models_used: models_used.append(m)
                        ot = d.get("outputTokens")
                        if isinstance(ot, (int, float)) and not isinstance(ot, bool):
                            out_tokens += int(ot)
                    elif et == "session.model_change":
                        nm = d.get("newModel")
                        if nm and nm not in models_used: models_used.append(nm)
                    elif et == "session.shutdown":
                        shutdown_metrics = d.get("modelMetrics")
                tokens = {"input": 0, "output": 0, "cached": 0, "total": 0}
                metr = _copilot_cli_tokens_from_metrics(shutdown_metrics)
                if metr:
                    tokens.update(metr)
                else:
                    tokens["input"] = in_estimate
                    tokens["output"] = out_tokens
                tokens["total"] = tokens["input"] + tokens["output"] + tokens["cached"]
                tokens["cost"] = calculate_cost(model, tokens["input"], tokens["output"], tokens["cached"],
                                                cache_creation_tokens=tokens.get("cache_creation", 0), at=ts)
                if model and model not in models_used: models_used.insert(0, model)
                ts = last_ts or start_ts or _file_mtime_utc(ev_file)
                sessions.append({
                    "id": sid, "agent": "copilot", "project": apply_alias(project_path),
                    "timestamp": ts, "display": first_msg[:100], "tokens": tokens,
                    "mcp_tools": [], "has_plan": False, "plans": [],
                    "model": model, "models_used": models_used, "artifacts": [],
                    "copilot_source": "cli", "cost": tokens["cost"],
                })
            except Exception: continue

    # 8. OpenCode (SQLite: session / message / part). One DB per release
    # channel, so a channel-switcher can have several side by side (#170).
    # Session ids are unique per DB but the same id could in principle appear
    # in two of them (a copied data dir); keep the count-once invariant.
    _oc_seen_ids: set = set()
    for _oc_db in _opencode_dbs():
        try:
            # mode=ro (via _sqlite_ro_uri) so we never take a write lock on the
            # live TUI's DB. It's a WAL database, so a read can still time out if
            # OpenCode is mid-write — that lands in the outer except, which now
            # logs instead of silently dropping the whole agent.
            uri = _sqlite_ro_uri(_oc_db)
            conn = sqlite3.connect(uri, uri=True, timeout=1.0)
            conn.row_factory = sqlite3.Row
            try:
                # OpenCode's schema drifts across versions (tables get added and
                # renamed). Detect which tables exist so one missing *peripheral*
                # table (e.g. `todo`) can't throw into the outer except and wipe
                # out every session — the failure mode behind discussion #170's
                # neighbours.
                try:
                    _tables = {r[0] for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'")}
                except Exception:
                    _tables = set()
                # Some OpenCode versions added a session-level `model` column
                # (e.g. the github-copilot provider stores the model only there,
                # not on assistant messages — see issue #39). Detect it so we can
                # fall back to it, without breaking older schemas that lack it.
                try:
                    _sess_cols = {r[1] for r in conn.execute("PRAGMA table_info(session)")}
                except Exception:
                    _sess_cols = set()
                _has_sess_model = "model" in _sess_cols
                # parent_id links child (delegated) sessions to their parent. Children
                # are full sessions already counted in aggregates, so hierarchy here is
                # annotation-only — never re-summed (count-once invariant).
                _has_parent = "parent_id" in _sess_cols
                _parent_sel = ", parent_id" if _has_parent else ""
                oc_by_id: Dict[str, Dict[str, Any]] = {}
                oc_parent_of: Dict[str, str] = {}
                rows = conn.execute(f"SELECT id, directory, title, time_created, time_updated{_parent_sel} FROM session").fetchall()
                for srow in rows:
                    sid = srow["id"]
                    if sid in _oc_seen_ids:
                        continue
                    _oc_seen_ids.add(sid)
                    ts = datetime.fromtimestamp((srow["time_updated"] or srow["time_created"] or 0) / 1000, tz=timezone.utc)
                    tokens = {"input": 0, "output": 0, "cached": 0, "total": 0}
                    model = None
                    provider_id = None   # OpenCode records the runtime (e.g. "ollama") → local detection
                    models_used: List[str] = []   # distinct models, in first-seen order (#39)
                    first_user = ""
                    mcp_tools: List[str] = []
                    oc_tool_counts: Dict[str, int] = {}
                    has_plan = False
                    plans: List[Dict[str, Any]] = []
                    # Model + tokens from assistant messages
                    for mrow in conn.execute("SELECT data FROM message WHERE session_id=? ORDER BY time_created", (sid,)):
                        try:
                            mdata = json.loads(mrow["data"] or "{}")
                        except Exception: continue
                        if mdata.get("role") == "assistant":
                            if not provider_id:
                                provider_id = mdata.get("providerID")
                            if not model:
                                model = mdata.get("modelID") or mdata.get("providerID")
                                if not model:
                                    mi = mdata.get("model")
                                    if isinstance(mi, dict):
                                        model = mi.get("modelID") or mi.get("providerID")
                                    elif isinstance(mi, str):
                                        model = mi
                            # Track every distinct model used this session (sessions can
                            # switch models mid-thread). Prefer the real model id over a
                            # bare providerID so the list stays meaningful.
                            _mm = mdata.get("modelID") or _opencode_resolve_model(mdata.get("model"))
                            if _mm and _mm not in models_used:
                                models_used.append(_mm)
                            if mdata.get("mode") == "plan":
                                has_plan = True
                    # Fallbacks for #39: some providers (e.g. github-copilot) carry
                    # no model on assistant messages. Try the session-level `model`
                    # column, then any message regardless of role.
                    if not model and _has_sess_model:
                        try:
                            mrow = conn.execute("SELECT model FROM session WHERE id=?", (sid,)).fetchone()
                            if mrow is not None:
                                model = _opencode_resolve_model(mrow["model"])
                        except Exception:
                            pass
                    if not model:
                        for mrow in conn.execute("SELECT data FROM message WHERE session_id=? ORDER BY time_created", (sid,)):
                            try:
                                mdata = json.loads(mrow["data"] or "{}")
                            except Exception:
                                continue
                            model = (_opencode_resolve_model(mdata.get("model"))
                                     or mdata.get("modelID") or mdata.get("providerID"))
                            if model:
                                break
                    # Keep the resolved primary model represented in the list (covers the
                    # fallback cases where it came from session.model, not a message).
                    if model and model not in models_used:
                        models_used.insert(0, model)
                    # Parts: first user text, tool names, token totals from step-finish
                    for prow in conn.execute("SELECT data FROM part WHERE session_id=? ORDER BY time_created", (sid,)):
                        try:
                            pdata = json.loads(prow["data"] or "{}")
                        except Exception: continue
                        ptype = pdata.get("type")
                        if ptype == "text" and not first_user:
                            # Editor-context prefixes (<system-reminder>, <ide_*>)
                            # make useless previews — strip them; if nothing
                            # remains, keep scanning to the next text part (#129).
                            txt = _strip_context_tags(pdata.get("text") or "")
                            if txt: first_user = txt
                        if ptype == "tool":
                            tname = pdata.get("tool")
                            if tname and tname not in mcp_tools: mcp_tools.append(tname)
                            _count_tool(oc_tool_counts, tname)
                        if ptype == "step-finish":
                            tk = pdata.get("tokens") or {}
                            cache = tk.get("cache") or {}
                            cache_write = (cache.get("write", 0) or 0)
                            tokens["input"]  += tk.get("input", 0) or 0
                            tokens["output"] += tk.get("output", 0) or 0
                            tokens["cached"] = max(tokens["cached"], cache.get("read", 0) or 0)
                            # cache writes ARE billed per event → cumulative; priced at 1.25x input.
                            tokens["cache_creation"] = tokens.get("cache_creation", 0) + cache_write
                    tokens["total"] = tokens["input"] + tokens["output"] + tokens["cached"]
                    tokens["cost"] = calculate_cost(model, tokens["input"], tokens["output"], tokens["cached"], cache_creation_tokens=tokens.get("cache_creation", 0), provider=provider_id, at=ts)
                    project_path = srow["directory"] or "unknown"
                    title = srow["title"] or ""
                    display = (first_user or title)[:100]
                    # Todos (opencode's plan-like artifact). Optional table —
                    # absent on older/newer schemas, so gate on its presence.
                    todo_rows = (conn.execute("SELECT content, status FROM todo WHERE session_id=? ORDER BY position", (sid,)).fetchall()
                                 if "todo" in _tables else [])
                    if todo_rows:
                        has_plan = True
                        plan_text = "\n".join(f"- [{r['status']}] {r['content']}" for r in todo_rows)
                        plans.append({"session_id": sid, "agent": "opencode", "timestamp": ts, "content": plan_text})
                    oc_sess = {
                        "id": sid, "agent": "opencode", "project": apply_alias(srow["directory"] or "unknown"), "timestamp": ts,
                        "display": display, "tokens": tokens, "mcp_tools": mcp_tools,
                        "has_plan": has_plan, "plans": plans, "model": model,
                        "models_used": models_used, "artifacts": [],
                        "provider": provider_id,  # expose runtime (e.g. "ollama") so analytics can detect local sessions
                        "cost": tokens["cost"],
                    }
                    if _has_parent and srow["parent_id"]:
                        oc_sess["parent_session_id"] = srow["parent_id"]
                        oc_parent_of[sid] = srow["parent_id"]
                    _attach_tool_usage(oc_sess, oc_tool_counts)
                    oc_by_id[sid] = oc_sess
                    sessions.append(oc_sess)
                # Annotate parents with their children (display-only; child tokens
                # are already counted as their own sessions).
                for child_id, parent_id in oc_parent_of.items():
                    parent = oc_by_id.get(parent_id)
                    if parent is None:
                        continue
                    parent.setdefault("child_session_ids", []).append(child_id)
                for oc_sess in oc_by_id.values():
                    kids = oc_sess.get("child_session_ids") or []
                    if kids:
                        oc_sess["delegation"] = {"supported": True, "tokens_recorded": False,
                                                 "linked_children": len(kids)}
            finally:
                conn.close()
        except Exception as e:
            # Don't let a schema/lock hiccup silently erase the whole agent —
            # log it at debug so "no OpenCode sessions" is diagnosable instead
            # of invisible (discussion #170).
            import logging
            logging.getLogger("tokentelemetry.opencode").debug(
                "OpenCode scan skipped (%s): %r", _oc_db, e)

    # 8. Grok Build (xAI) — rich per-session directory with events, updates, chat history
    sessions.extend(_scan_grok_sessions())

    # 8b. Cline — CLI SQLite store + VS Code extension JSON store
    sessions.extend(_scan_cline_sessions())

    # 8b2. Pi Coding Agent — one JSONL per session under ~/.pi/agent/sessions/
    sessions.extend(_scan_pi_sessions())

    # 8b3. DeepSeek Harness (DSH) — zstd-compressed JSONL under ~/.dsh/sessions/
    sessions.extend(_scan_dsh_sessions())

    # 8b4. Qoder — Claude-shaped JSONL under ~/.qoder/projects/. Bills in
    # credits and records no token counts at all; see _scan_qoder_sessions.
    sessions.extend(_scan_qoder_sessions())

    # 8c. Meta Muse Code + Prime Agent. Their root session records contain the
    # cwd, so they naturally participate in project/worktree navigation.
    for sess in _scan_muse_sessions() + _scan_prime_sessions():
        sess["project"] = apply_alias(sess.get("project") or "unknown")
        sessions.append(sess)

    # 8d. SmallCode — traces are PROJECT-LOCAL (<project>/.smallcode/traces/),
    # so discover roots from projects already seen from other agents (they ran
    # somewhere real) unioned with any user-configured extra roots, then scan.
    smallcode_roots = {
        s["project"] for s in sessions
        if s.get("project") and s["project"] != "unknown"
    }
    smallcode_roots.update(SMALLCODE_EXTRA_ROOTS)
    smallcode_roots = {r for r in smallcode_roots if r and Path(r).expanduser().is_dir()}
    sessions.extend(_scan_smallcode_sessions(smallcode_roots))

    # 9. Hermes Agent (SQLite: sessions / messages, pre-aggregated tokens)
    hermes_dbs = _hermes_dbs_with_profiles()
    hermes_cwd_map = _hermes_cwd_by_session() if hermes_dbs else {}
    hermes_by_id: Dict[str, Dict[str, Any]] = {}
    for db_path, h_profile in hermes_dbs:
        try:
            uri = _sqlite_ro_uri(db_path)
            conn = sqlite3.connect(uri, uri=True, timeout=1.0)
            conn.row_factory = sqlite3.Row
            try:
                # billing_base_url is newer; older Hermes DBs may lack it. Select
                # it only when present so the whole scan doesn't fail on legacy
                # schemas (the outer try/except would otherwise drop all sessions).
                _cols = {r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()}
                _base_url_col = "billing_base_url" if "billing_base_url" in _cols else "NULL AS billing_base_url"
                _cost_status_col = "cost_status" if "cost_status" in _cols else "NULL AS cost_status"
                _cost_source_col = "cost_source" if "cost_source" in _cols else "NULL AS cost_source"
                srows = conn.execute(
                    "SELECT id, source, model, parent_session_id, started_at, ended_at, "
                    "input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, "
                    "reasoning_tokens, estimated_cost_usd, actual_cost_usd, title, "
                    f"billing_provider, {_base_url_col}, {_cost_status_col}, {_cost_source_col}, end_reason "
                    "FROM sessions"
                ).fetchall()
                for srow in srows:
                    sid = srow["id"]
                    ts_unix = srow["ended_at"] or srow["started_at"] or 0
                    ts = datetime.fromtimestamp(ts_unix, tz=timezone.utc)
                    in_t  = srow["input_tokens"] or 0
                    out_t = srow["output_tokens"] or 0
                    reas  = srow["reasoning_tokens"] or 0
                    # Split cache read (cheap, ~0.1x input) from cache write (1.25x input).
                    # Do NOT sum them: they bill at wildly different rates.
                    cache_read  = srow["cache_read_tokens"] or 0
                    cache_write = srow["cache_write_tokens"] or 0
                    cached = cache_read
                    # Hermes does NOT price reasoning_tokens (verified). Keep them
                    # separate so we can surface MiMo-style silent-waste sessions.
                    tokens = {"input": in_t, "output": out_t, "cached": cached,
                              "cache_creation": cache_write,
                              "reasoning": reas,
                              "total": in_t + out_t + cached + cache_write + reas}
                    # Anomaly: reasoning dominates output AND is non-trivial in absolute terms.
                    # Cf. MiMo thinking-mode silent-waste (Hermes issue #27325).
                    cost_anomaly = bool(reas > 5000 and reas > out_t)
                    model = srow["model"]
                    # Prefer Hermes's own cost (it knows exotic models we may not price)
                    cost = srow["actual_cost_usd"] if srow["actual_cost_usd"] is not None else srow["estimated_cost_usd"]
                    # Where the dollar figure we end up REPORTING came from. Set
                    # by whichever branch below produces the final number — a
                    # Hermes estimate we throw away (issue #176) is not
                    # "provider-estimated", it's tt-computed.
                    _cost_status = None
                    if srow["actual_cost_usd"] is not None:
                        _cost_status = "provider-reported"
                    elif cost is not None:
                        _cost_status = "provider-estimated"
                    # Hermes stores estimated_cost_usd=0.0 (not NULL) with cost_status='unknown'
                    # / cost_source='none' when it couldn't price the session itself (proxied or
                    # unrecognized endpoint, subscription-included model). Don't take that 0.0 at
                    # face value — fall through to calculate_cost() below, which prices from the
                    # model + token counts and lets TT's own subscription config (not Hermes's)
                    # decide the framing. Only override the *estimate*; a real actual_cost_usd wins.
                    if srow["actual_cost_usd"] is None and (srow["cost_status"] == "unknown" or srow["cost_source"] == "none"):
                        cost = None
                        _cost_status = None
                    # Bind before the branch: it's referenced unconditionally in the
                    # session dict below, but only computed when cost must be derived.
                    _measured_tps = None
                    _is_local = False
                    if cost is None:
                        # Only when TT has to compute the cost itself AND the session
                        # is local do we parse the agent log for a MEASURED tok/s
                        # (out/latency per call). This keeps the common path cheap —
                        # most Hermes sessions carry their own cost and skip this.
                        try:
                            from power_config import is_local_session
                            _is_local = bool(is_local_session(model, srow["billing_base_url"], srow["billing_provider"]))
                            if _is_local:
                                _summ = _hermes_log_summary(sid, h_profile).get("summary")
                                if _summ and _summ.get("total_latency_s", 0) > 0 and out_t > 0:
                                    _measured_tps = out_t / _summ["total_latency_s"]
                        except Exception:
                            _measured_tps = None
                        cost = calculate_cost(
                            model, in_t, out_t, cached, at=ts,
                            provider=srow["billing_provider"],
                            cache_creation_tokens=cache_write,
                            endpoint=srow["billing_base_url"],
                            tok_per_sec=_measured_tps,
                        )
                        # A zero from calculate_cost is only meaningful when
                        # something DELIBERATELY prices at zero — a flat
                        # subscription (billed monthly) or a local model whose
                        # electricity draw rounds away. Otherwise a 0.0 means we
                        # couldn't price the session at all; keep cost None so the
                        # UI says "not captured" instead of a confident "$0.00".
                        if cost is None:
                            _cost_status = "unpriced"
                        elif cost > 0:
                            _cost_status = "tt-computed"
                        else:
                            # No tokens recorded means there was nothing to
                            # price in the first place. "Local model, so $0
                            # marginal" is a positive finding and would be a
                            # lie here — we measured nothing. Unpriced wins
                            # over deliberate-zero whenever the session is empty.
                            _nothing_to_price = tokens["total"] == 0
                            _deliberate_zero = _is_local and not _nothing_to_price
                            if not _deliberate_zero and not _nothing_to_price:
                                try:
                                    from power_config import is_subscription_endpoint, is_subscription_model
                                    _deliberate_zero = bool(
                                        (srow["billing_base_url"] and is_subscription_endpoint(srow["billing_base_url"]))
                                        or is_subscription_model(model)
                                    )
                                except Exception:
                                    _deliberate_zero = False
                            if _deliberate_zero:
                                # Priced successfully, and the answer is a real
                                # zero: local model, or a model/endpoint the
                                # user already pays a flat fee for. Keep the
                                # 0.0 (it IS the marginal cost, and aggregates
                                # sum it), but do NOT call it "tt-computed":
                                # that reads as "we priced these tokens and
                                # they cost $0.00", which is false. The API
                                # equivalent isn't zero; the MARGINAL cost is.
                                _cost_status = "zero-marginal"
                            else:
                                cost = None
                                _cost_status = "unpriced"
                    tokens["cost"] = cost
                    # First user message → display fallback when title is empty
                    first_user = ""
                    fu = conn.execute(
                        "SELECT content FROM messages WHERE session_id=? AND role='user' "
                        "AND content IS NOT NULL AND content != '' "
                        "ORDER BY timestamp LIMIT 1", (sid,)).fetchone()
                    if fu:
                        first_user = fu["content"] or ""
                    display = (srow["title"] or first_user)[:100]
                    # Tool names + call counts used in this session
                    h_tool_counts = {r[0]: r[1] for r in conn.execute(
                        "SELECT tool_name, COUNT(*) FROM messages "
                        "WHERE session_id=? AND tool_name IS NOT NULL AND tool_name != '' "
                        "GROUP BY tool_name",
                        (sid,)).fetchall()}
                    mcp_tools = list(h_tool_counts.keys())
                    cwd = hermes_cwd_map.get(sid)
                    hermes_by_id[sid] = {
                        "id": sid, "agent": "hermes",
                        "project": apply_alias(cwd or "unknown"),
                        "project_inferred": cwd is not None,
                        "timestamp": ts, "display": display, "tokens": tokens,
                        "mcp_tools": mcp_tools, "has_plan": False, "plans": [],
                        "model": model, "artifacts": [], "cost": cost,
                        "source_subtype": srow["source"],
                        "cost_anomaly": cost_anomaly,
                        "parent_session_id": srow["parent_session_id"],
                        "end_reason": srow["end_reason"],
                        # end_reason is an OPEN set (Hermes's own API lets a
                        # caller PATCH an arbitrary string). Anything we don't
                        # recognise buckets as "unknown" with the raw value
                        # preserved — never silently as a completion.
                        "outcome": _ht.classify_end_reason(srow["end_reason"]),
                        "outcome_raw": _ht.normalize_end_reason_raw(srow["end_reason"]),
                        "cost_status": _cost_status or "unpriced",
                        # Hermes's OWN cost_status column, verbatim and
                        # unmapped. Distinct from `cost_status` above (which
                        # describes where TT's dollar figure came from):
                        # 'included' means the session was billed under a flat
                        # plan, so the dollar figure we compute is an API
                        # equivalent, not money the user spent at the margin.
                        "_hermes_cost_status": srow["cost_status"],
                        "provider": srow["billing_provider"],
                        "endpoint": srow["billing_base_url"],
                        "tok_per_sec": _measured_tps,
                    }
                    if h_profile:
                        hermes_by_id[sid]["hermes_profile"] = h_profile
                    _attach_tool_usage(hermes_by_id[sid], h_tool_counts)
                    sessions.append(hermes_by_id[sid])
            finally:
                conn.close()
        except Exception:
            pass
    # Hermes hierarchy: children carry parent_session_id (pre-aggregated tokens
    # of their own, already in totals) — annotate parents, never re-sum.
    for h_sess in hermes_by_id.values():
        pid = h_sess.get("parent_session_id")
        if pid and pid in hermes_by_id:
            hermes_by_id[pid].setdefault("child_session_ids", []).append(h_sess["id"])
    for h_sess in hermes_by_id.values():
        kids = h_sess.get("child_session_ids") or []
        if kids:
            h_sess["delegation"] = {"supported": True, "tokens_recorded": False,
                                    "linked_children": len(kids)}

    # Antigravity subagent linkage (needs the full session list to pair ids).
    _antigravity_link_subagents(sessions)
    _antigravity_attach_goals(sessions)

    # Every session gets an explicit delegation marker: agents whose logs carry
    # no spawn signal report supported=False (an honest "n/a", never a fake 0).
    # Capability is per-agent — a claude session outside the parsed top-100 is
    # still "supported", just not scanned yet.
    for s in sessions:
        s.setdefault("delegation", {"supported": s.get("agent") in _DELEGATION_CAPABLE_AGENTS})

    # Loop lifecycle: recompute active/expired/cancelled from now() for every
    # loop session (raw facts were parsed above; liveness is never cached).
    _annotate_loop_lifecycle(sessions, datetime.now(timezone.utc))

    # One folder, one identity: agent CLIs disagree on separator style
    # (`C:\a\b` vs `C:/a/b`), which used to split real projects into duplicate
    # /projects cards. Canonicalise once here so every consumer downstream
    # (rollups, filters, durable history) sees the same string.
    for s in sessions:
        s["project"] = canonical_project(s["project"])

    # Global sort by timestamp descending
    sessions.sort(key=lambda x: x["timestamp"], reverse=True)
    return sessions


# ---------------------------------------------------------------------------
# Sessions cache
# ---------------------------------------------------------------------------
# Thousands of small JSON/JSONL file reads are expensive; /projects and
# /analytics internally reuse get_sessions, so one dashboard load used to
# trigger 3 full scans. A short TTL cache collapses that to 1 scan per window,
# and asyncio.to_thread keeps the event loop free while we scan.
import asyncio as _asyncio
import time as _time
from pricing import calculate_cost, PRICING, PRICING_UPDATED, PRICING_OVERLAY_UPDATED
import logging as _logging

_log = _logging.getLogger("tokentelemetry.cache")

SESSIONS_TTL_SEC = 30.0

_sessions_cache: Dict[str, Any] = {"data": None, "at": 0.0, "building": False}
_sessions_lock: Optional[_asyncio.Lock] = None  # lazy-init inside event loop


def _get_sessions_lock() -> _asyncio.Lock:
    global _sessions_lock
    if _sessions_lock is None:
        _sessions_lock = _asyncio.Lock()
    return _sessions_lock


def _archive_opted_in_transcripts(data: List[Dict[str, Any]]) -> None:
    """For agents the user opted into, copy each session's on-disk transcript
    into the durable store (tier 2) so it survives the agent's own pruning.
    Best-effort and only for agents whose transcript is a single resolvable
    file; everything else stays rollup-only. Runs on the scan worker thread."""
    import history_store
    from agent_retention import archive_enabled

    for s in data:
        agent, sid = s.get("agent"), s.get("id")
        if not agent or not sid or not archive_enabled(agent):
            continue
        if s.get("transcript_archived"):
            continue
        path = _resolve_transcript_path(agent, sid)
        if not path:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if text:
            history_store.put_transcript(agent, sid, text)


def _resolve_transcript_path(agent: str, session_id: str) -> Optional[Path]:
    """Best-effort single-file transcript path for archivable agents."""
    try:
        if agent == "claude":
            hits = list(CLAUDE_DIR.glob(f"projects/**/{session_id}.jsonl"))
            return hits[0] if hits else None
        if agent == "codex":
            hits = list(CODEX_DIR.glob(f"sessions/**/*{session_id}*.jsonl"))
            return hits[0] if hits else None
    except OSError:
        return None
    return None


def _persist_history_async(data: List[Dict[str, Any]]) -> None:
    """Schedule the durable-history write off the request path. Fire-and-forget:
    failures are logged inside the store and never surface to the caller."""
    import history_store

    def _work() -> None:
        try:
            history_store.upsert_sessions(data)
            history_store.mark_absent({(s.get("agent"), s.get("id")) for s in data
                                       if s.get("agent") and s.get("id")})
            _archive_opted_in_transcripts(data)
        except Exception as e:  # noqa: BLE001
            _log.exception("history persist failed: %s", e)

    try:
        _asyncio.get_running_loop().run_in_executor(None, _work)
    except RuntimeError:
        # No running loop (e.g. called from a sync context) — run inline.
        _work()


_harness_scan_reported = False


def _report_harness_scan(data: List[Dict[str, Any]]) -> None:
    """Emit one anonymous `harness.scanned` per detected agent, once per process.

    The `agents` context prop already says which harnesses are *installed*.
    Nothing said whether their readers actually returned anything, so a reader
    that silently found nothing on someone else's machine stayed invisible until
    a bug report arrived -- which is exactly how DeepSeek Harness shipped
    reporting zero sessions.

    Emitted after the first successful scan (the counts are free at that point)
    and never again: the scan re-runs on a 30s TTL and clients poll it, so a
    per-scan emit would be a firehose. Volume is an order-of-magnitude bucket,
    never a raw count. Best-effort throughout -- telemetry must never affect the
    scan's result.
    """
    global _harness_scan_reported
    if _harness_scan_reported:
        return
    _harness_scan_reported = True
    try:
        from collections import Counter
        counts = Counter(s.get("agent") for s in data)
        # The union of "detected on disk" and "actually produced sessions", not
        # just the former. The two disagree in both directions and each
        # disagreement is the signal:
        #   detected, 0 sessions -> the reader is broken (the DSH case);
        #   sessions, not detected -> the detector is broken. SmallCode is
        #     exactly this today: its traces are project-local, so
        #     _list_available_agents() only sees it via an env-configured extra
        #     root even while the scanner is finding its sessions.
        agents = {a for a in counts if isinstance(a, str) and a}
        agents.update(_list_available_agents())
        for agent in sorted(agents):
            _telemetry.emit("harness.scanned", {
                "agent": agent,
                "volume": _telemetry.volume_bucket(counts.get(agent, 0)),
            })
    except Exception:
        pass


async def get_sessions_cached(fresh: bool = False) -> List[Dict[str, Any]]:
    """Cached, non-blocking access to the session list.

    - TTL is SESSIONS_TTL_SEC (default 30s).
    - Scans run in a worker thread so the async event loop stays responsive.
    - Single-flight: concurrent callers share one scan via an asyncio.Lock.
    - `fresh=True` forces a re-scan.
    """
    now = _time.monotonic()
    cached = _sessions_cache.get("data")
    age = now - _sessions_cache.get("at", 0.0)
    if not fresh and cached is not None and age < SESSIONS_TTL_SEC:
        return cached

    lock = _get_sessions_lock()
    async with lock:
        # Double-check: another waiter may have just refreshed the cache.
        now = _time.monotonic()
        cached = _sessions_cache.get("data")
        age = now - _sessions_cache.get("at", 0.0)
        if not fresh and cached is not None and age < SESSIONS_TTL_SEC:
            return cached

        _sessions_cache["building"] = True
        try:
            t0 = _time.monotonic()
            data = await _asyncio.to_thread(_scan_sessions_sync)
            _sessions_cache["data"] = data
            _sessions_cache["at"] = _time.monotonic()
            _log.info("sessions scan: %d entries in %.0fms", len(data), (_time.monotonic() - t0) * 1000)
            _report_harness_scan(data)
            # Durable rollup: persist a tiny summary of each session so history
            # outlives the agents' own transcript pruning. Fire-and-forget on a
            # worker thread — a store failure must never break a request, and the
            # write must not add latency to this scan.
            _persist_history_async(data)
        except Exception as e:
            _log.exception("sessions scan failed: %s", e)
            # If we have a previous value, keep serving it rather than 500-ing.
            if cached is not None:
                return cached
            raise
        finally:
            _sessions_cache["building"] = False
        return _sessions_cache["data"]


@app.get("/sessions")
async def get_sessions(fresh: bool = False):
    """Return the session list. Pass ?fresh=1 to force a re-scan."""
    data = await get_sessions_cached(fresh=fresh)
    # `stub` is scan→persist plumbing (history_store.upsert_sessions keys its
    # conflict clause on it), not API surface. Strip it on shallow copies —
    # never mutate the cached dicts, which the async history persist may
    # still be reading.
    return [{k: v for k, v in s.items() if k != "stub"} for s in data]


@app.get("/pricing")
async def get_pricing():
    """Return the static pricing table and the dates its two layers were refreshed.

    ``updated`` is the curated inline table; ``overlay_updated`` is the bundled
    models.dev snapshot. They move independently, and the curated table is the
    one that wins on conflict, so reporting only the (usually newer) overlay
    date would overstate how fresh the authoritative rates are.
    """
    return {
        "updated": PRICING_UPDATED,
        "overlay_updated": PRICING_OVERLAY_UPDATED,
        "models": PRICING,
    }


@app.get("/remote-access")
async def get_remote_access(request: Request):
    """Connection info for the "connect a device" QR panel: the scan-to-open URL
    (host + frontend port + bootstrap token) that bin/cli.js precomputed into
    TT_REMOTE_CONNECT_URL. The token is a credential, so this is LOOPBACK-ONLY —
    a remote device (even one holding the token) gets 403, so the token can never
    be re-fetched over the network. Returns {enabled: false} when not exposed."""
    from fastapi import HTTPException
    client = request.client.host if request.client else None
    if not _is_loopback(client):
        raise HTTPException(status_code=403, detail="Not available remotely.")
    url = os.environ.get("TT_REMOTE_CONNECT_URL", "").strip()
    token = os.environ.get("TT_AUTH_TOKEN", "").strip()
    if not url or not token:
        return {"enabled": False}
    return {"enabled": True, "url": url, "token": token}


@app.get("/artifacts")
@app.head("/artifacts")  # the artifacts-tab preview HEAD-checks file existence
async def get_artifact(path: str):
    """Stream a local artifact file securely."""
    from fastapi.responses import FileResponse
    p = Path(path)
    # Security: only serve files from known agent directories. We compare the
    # *resolved* path (symlinks collapsed) against each resolved allow-root, so a
    # symlink planted inside an allowed dir that points outside it is rejected.
    # Antigravity's brain/CLI stores live under GEMINI_DIR already, but we list
    # them explicitly so the allow-list survives any future narrowing of that
    # root (and documents that those artifacts are intentionally served).
    allowed = [CLAUDE_DIR, CODEX_DIR, GEMINI_DIR, QWEN_DIR, VIBE_DIR, CURSOR_DIR,
               VSCODE_BASE, CURSOR_BASE, *ANTIGRAVITY_BRAIN_DIRS, ANTIGRAVITY_CLI_DIR]
    try:
        resolved = p.resolve()
    except Exception:
        resolved = None
    is_safe = False
    if resolved is not None:
        for a in allowed:
            try:
                if resolved.is_relative_to(a.resolve()):
                    is_safe = True; break
            except Exception: continue

    if not is_safe or resolved is None or not resolved.exists() or not resolved.is_file():
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Unauthorized or not found")

    # Serve the validated, resolved path (not the raw input) so the file we
    # checked is exactly the file we return — closes any symlink-swap window.
    return FileResponse(str(resolved))


@app.get("/cache/status")
async def cache_status():
    age = _time.monotonic() - _sessions_cache.get("at", 0.0) if _sessions_cache.get("data") is not None else None
    return {
        "cached": _sessions_cache.get("data") is not None,
        "age_sec": round(age, 2) if age is not None else None,
        "ttl_sec": SESSIONS_TTL_SEC,
        "entries": len(_sessions_cache["data"]) if _sessions_cache.get("data") is not None else 0,
        "building": _sessions_cache.get("building", False),
        "last_error": _sessions_cache.get("last_error")
    }


@app.post("/cache/invalidate")
async def invalidate_cache():
    """Drop the sessions cache so the next read triggers a fresh scan."""
    _sessions_cache["data"] = None
    _sessions_cache["at"] = 0.0
    # Harness panels read the same agent directories, so a manual refresh should
    # clear them too — otherwise a user who just changed a Codex automation
    # refreshes and still sees the old schedule for up to a minute.
    harness_panels.invalidate()
    return {"ok": True}


# --- Session-detail parse cache -------------------------------------------------
# get_session_detail re-reads and re-parses a session's full transcript on every
# open; large transcripts (tens of MB) made re-opens slow. Memoize the parsed
# event list on (mtime_ns, size) so an unchanged file is parsed only once. The key
# changes the instant the file is appended to, so a live session never goes stale.
_SESSION_DETAIL_CACHE: Dict[str, Tuple[Tuple[int, int], List[Dict[str, Any]]]] = {}
_SESSION_DETAIL_CACHE_MAX = 16


def _parse_session_jsonl_cached(path: Path) -> List[Dict[str, Any]]:
    """Parse a JSONL transcript into normalized event dicts, memoized on file
    identity + (mtime_ns, size). Returns the cached list on a hit (callers must
    treat it as read-only — the detail endpoint only serializes it)."""
    try:
        st = path.stat()
        stamp = (st.st_mtime_ns, st.st_size)
    except OSError:
        stamp = None
    key = str(path)
    if stamp is not None:
        hit = _SESSION_DETAIL_CACHE.get(key)
        if hit is not None and hit[0] == stamp:
            return hit[1]
    events: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                data = json.loads(line)
            except Exception:
                continue
            # Add a normalized_timestamp for the waterfall view.
            if data.get("timestamp"):
                try:
                    ts = _aware(datetime.fromisoformat(data["timestamp"].replace('Z', '+00:00')))
                    data["normalized_timestamp"] = ts.timestamp() * 1000
                except Exception:
                    pass
            events.append(data)
    if stamp is not None:
        if key not in _SESSION_DETAIL_CACHE and len(_SESSION_DETAIL_CACHE) >= _SESSION_DETAIL_CACHE_MAX:
            _SESSION_DETAIL_CACHE.pop(next(iter(_SESSION_DETAIL_CACHE)))
        _SESSION_DETAIL_CACHE[key] = (stamp, events)
    return events


def _codex_visible_signatures(event: Dict[str, Any]) -> List[tuple]:
    """Return visible-content signatures used to identify Codex mirrors.

    Codex rollouts can persist both a canonical ``response_item`` and a nearby
    ``event_msg`` projection for the same user, assistant, or reasoning text.
    Keep event-only records for older rollouts, and remove a projection only
    when its canonical counterpart is present nearby.
    """
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return []

    event_type = event.get("type")
    payload_type = payload.get("type")
    if event_type == "event_msg":
        if payload_type == "user_message":
            text, kind = payload.get("message"), "user"
        elif payload_type == "agent_message":
            text, kind = payload.get("message"), "assistant"
        elif payload_type == "agent_reasoning":
            text, kind = payload.get("text"), "reasoning"
        else:
            return []
        normalized = str(text or "").strip()
        return [(kind, normalized)] if normalized else []

    if event_type != "response_item":
        return []
    if payload_type == "reasoning":
        return [
            ("reasoning", str(item.get("text") or "").strip())
            for item in payload.get("summary") or []
            if isinstance(item, dict) and str(item.get("text") or "").strip()
        ]
    if payload_type != "message" or payload.get("role") not in {"user", "assistant"}:
        return []

    text = "".join(
        str(item.get("text") or "")
        for item in payload.get("content") or []
        if isinstance(item, dict) and item.get("type") in {"input_text", "output_text"}
    ).strip()
    return [(payload["role"], text)] if text else []


def _canonicalize_codex_trace(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return one visible Codex timeline from mirrored and streamed records."""
    canonical: Dict[tuple, List[tuple]] = {}
    for index, event in enumerate(events):
        if event.get("type") != "response_item":
            continue
        timestamp = event.get("normalized_timestamp")
        for signature in _codex_visible_signatures(event):
            canonical.setdefault(signature, []).append((index, timestamp))

    result = []
    for index, event in enumerate(events):
        signatures = _codex_visible_signatures(event)
        if event.get("type") == "event_msg" and signatures:
            timestamp = event.get("normalized_timestamp")
            matches_canonical = any(
                abs(index - canonical_index) <= 4
                and (
                    not isinstance(timestamp, (int, float))
                    or not isinstance(canonical_timestamp, (int, float))
                    or abs(timestamp - canonical_timestamp) <= 100
                )
                for signature in signatures
                for canonical_index, canonical_timestamp in canonical.get(signature, [])
            )
            if matches_canonical:
                continue
        result.append(event)

    # Reasoning is streamed as snapshots. A snapshot may repeat the previous
    # summary, extend it, or contain no visible text at all. The UI should show
    # the most complete nearby snapshot once, not one Step Index row per write.
    collapsed: List[Dict[str, Any]] = []
    for event in result:
        if event.get("type") != "response_item" or (event.get("payload") or {}).get("type") != "reasoning":
            collapsed.append(event)
            continue

        current_text = "\n\n".join(
            text for kind, text in _codex_visible_signatures(event) if kind == "reasoning" and text
        )
        if not current_text:
            continue

        previous_index = len(collapsed) - 1
        while previous_index >= 0:
            previous = collapsed[previous_index]
            previous_payload = previous.get("payload") or {}
            if previous.get("type") == "event_msg" and previous_payload.get("type") == "token_count":
                previous_index -= 1
                continue
            break

        if previous_index >= 0:
            previous = collapsed[previous_index]
            previous_payload = previous.get("payload") or {}
            if previous.get("type") == "response_item" and previous_payload.get("type") == "reasoning":
                previous_text = "\n\n".join(
                    text for kind, text in _codex_visible_signatures(previous) if kind == "reasoning" and text
                )
                if previous_text == current_text or previous_text.startswith(current_text) or current_text.startswith(previous_text):
                    if len(current_text) >= len(previous_text):
                        collapsed[previous_index] = event
                    continue

        collapsed.append(event)
    return collapsed


@app.get("/sessions/{session_id}")
async def get_session_detail(session_id: str, agent: str):
    if agent == "claude":
        files = list(CLAUDE_DIR.glob(f"projects/**/{session_id}.jsonl")) or list(CLAUDE_DIR.glob(f"sessions/{session_id}.json"))
        if not files: return {"error": "Not found"}
        return _parse_session_jsonl_cached(files[0])
    elif agent == "codex":
        files = list(CODEX_DIR.glob(f"sessions/**/rollout-*{session_id}*.jsonl"))
        if not files: return {"error": "Not found"}
        return _canonicalize_codex_trace(_parse_session_jsonl_cached(files[0]))
    elif agent == "grok":
        # Grok Build dialogue. chat_history.jsonl is the canonical conversation in
        # FILE ORDER and carries NO per-message timestamps, so we normalize each
        # entry into Claude-shaped message events (the mature EventCard path already
        # pairs assistant tool_use with the following user tool_result) and assign
        # synthetic, order-preserving timestamps. Lifecycle events from events.jsonl
        # are NOT merged here — they can't be aligned to the dialogue and are surfaced
        # in the grok-forensics card instead.
        sess_dir = None
        for bucket in GROK_SESSIONS_DIR.glob("*"):
            candidate = bucket / session_id
            if candidate.is_dir() and (candidate / GROK_SUMMARY).exists():
                sess_dir = candidate
                break
        if not sess_dir:
            return {"error": "Not found"}

        # Synthetic timeline base: summary.created_at -> epoch-ms, else dir mtime.
        base_ms = None
        summary = {}
        try:
            with open(sess_dir / GROK_SUMMARY, "r", encoding="utf-8") as f:
                summary = json.load(f)
        except Exception:
            summary = {}
        created = summary.get("created_at")
        if created:
            try:
                base_ms = _aware(datetime.fromisoformat(str(created).replace("Z", "+00:00"))).timestamp() * 1000
            except Exception:
                base_ms = None
        if base_ms is None:
            base_ms = _file_mtime_utc(sess_dir).timestamp() * 1000

        events: List[Dict[str, Any]] = []
        seq = 0
        chat_path = sess_dir / GROK_CHAT_HISTORY
        if chat_path.exists():
            try:
                with open(chat_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        try:
                            entry = json.loads(line)
                        except Exception:
                            continue
                        etype = entry.get("type")
                        norm = None  # set when we emit an event

                        if etype == "user":
                            parts = entry.get("content") or []
                            text = "".join(
                                p.get("text", "") for p in parts
                                if isinstance(p, dict) and p.get("type") == "text"
                            )
                            norm = {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": text}]}}

                        elif etype == "assistant":
                            content_blocks: List[Dict[str, Any]] = []
                            text = entry.get("content") or ""
                            if isinstance(text, str) and text.strip():
                                content_blocks.append({"type": "text", "text": text})
                            for tc in (entry.get("tool_calls") or []):
                                if not isinstance(tc, dict):
                                    continue
                                try:
                                    args = json.loads(tc.get("arguments") or "{}")
                                except Exception:
                                    args = {}
                                if not isinstance(args, dict):
                                    args = {}
                                content_blocks.append({
                                    "type": "tool_use",
                                    "id": tc.get("id"),
                                    "name": tc.get("name"),
                                    "input": args,
                                })
                            if content_blocks:
                                norm = {"type": "assistant", "message": {"role": "assistant", "content": content_blocks}}
                                # Surface the reasoning-effort setting so the
                                # session context panel can show it (grok records
                                # it per assistant turn; low/medium/high/xhigh).
                                _re = entry.get("reasoning_effort")
                                if isinstance(_re, str) and _re:
                                    norm["reasoning_effort"] = _re

                        elif etype == "reasoning":
                            summ = entry.get("summary") or []
                            thinking = "".join(
                                s.get("text", "") for s in summ
                                if isinstance(s, dict) and s.get("type") == "summary_text"
                            )
                            if thinking.strip():
                                norm = {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "thinking", "thinking": thinking}]}}

                        elif etype == "tool_result":
                            norm = {"type": "user", "message": {"role": "user", "content": [{
                                "type": "tool_result",
                                "tool_use_id": entry.get("tool_call_id"),
                                "content": entry.get("content") or "",
                            }]}}

                        # system / backend_tool_call and any empty entries are skipped.
                        if norm is None:
                            continue

                        # Synthetic order-preserving timestamp: Grok's chat_history has no
                        # per-message timestamps, so we space events 1s apart in file order.
                        norm["normalized_timestamp"] = base_ms + seq * 1000
                        seq += 1
                        events.append(norm)
            except Exception:
                pass

        # Already in file order (monotonic via seq).
        return events

    elif agent == "pi":
        # Pi Coding Agent JSONL. Normalize each message into Claude-shaped events
        # (role user/assistant, content blocks type text/thinking/tool_use/
        # tool_result) so the existing EventCard renderer handles it unchanged.
        # Pi carries real per-message timestamps, so no synthetic timeline needed.
        sess_file = None
        if PI_SESSIONS_DIR.exists():
            for bucket in PI_SESSIONS_DIR.iterdir():
                if not bucket.is_dir():
                    continue
                match = list(bucket.glob(f"*{session_id}*.jsonl"))
                if match:
                    sess_file = match[0]
                    break
        if not sess_file:
            return {"error": "Not found"}

        events: List[Dict[str, Any]] = []
        with open(sess_file, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                except Exception:
                    continue
                # pi records the thinking-level setting (off/medium/high) as
                # dedicated events; pass them through so the context panel can
                # show the reasoning effort the session ran at.
                if evt.get("type") == "thinking_level_change":
                    _tl = evt.get("thinkingLevel")
                    if isinstance(_tl, str) and _tl:
                        _tle = {"type": "thinking_level_change", "thinkingLevel": _tl}
                        _tlts = evt.get("timestamp")
                        if _tlts:
                            try:
                                _tle["normalized_timestamp"] = _aware(datetime.fromisoformat(str(_tlts).replace("Z", "+00:00"))).timestamp() * 1000
                            except Exception:
                                pass
                        _tle.setdefault("normalized_timestamp", len(events) * 1000)
                        events.append(_tle)
                    continue
                if evt.get("type") != "message":
                    continue
                m = evt.get("message") or {}
                role = m.get("role")
                norm = None

                if role == "user":
                    text = "".join(
                        c.get("text", "") for c in (m.get("content") or [])
                        if isinstance(c, dict) and c.get("type") == "text"
                    )
                    norm = {"type": "user", "message": {"role": "user",
                            "content": [{"type": "text", "text": text}]}}

                elif role == "assistant":
                    blocks: List[Dict[str, Any]] = []
                    for c in (m.get("content") or []):
                        if not isinstance(c, dict):
                            continue
                        ctype = c.get("type")
                        if ctype == "thinking":
                            think = c.get("thinking") or ""
                            if think.strip():
                                blocks.append({"type": "thinking", "thinking": think})
                        elif ctype == "text":
                            txt = c.get("text") or ""
                            if txt.strip():
                                blocks.append({"type": "text", "text": txt})
                        elif ctype == "toolCall":
                            blocks.append({
                                "type": "tool_use",
                                "id": c.get("id"),
                                "name": c.get("name"),
                                "input": c.get("arguments") or {},
                            })
                    if blocks:
                        norm = {"type": "assistant", "message":
                                {"role": "assistant", "content": blocks}}

                elif role == "toolResult":
                    content = m.get("content")
                    if isinstance(content, list):
                        content = "".join(
                            c.get("text", "") for c in content
                            if isinstance(c, dict) and c.get("type") == "text"
                        )
                    norm = {"type": "user", "message": {"role": "user", "content": [{
                        "type": "tool_result",
                        "tool_use_id": m.get("toolCallId"),
                        "content": content or "",
                    }]}}

                if norm is None:
                    continue
                ts_raw = evt.get("timestamp")
                if ts_raw:
                    try:
                        _ts = _aware(datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00")))
                        norm["normalized_timestamp"] = _ts.timestamp() * 1000
                    except Exception:
                        pass
                norm.setdefault("normalized_timestamp", len(events) * 1000)
                events.append(norm)
        return events

    elif agent == "dsh":
        # DeepSeek Harness — zstd-compressed JSONL; _dsh_trace_events normalizes
        # it into the same Claude-shaped events the pi branch above produces.
        # Subagent children are their own session files, so a delegated run is
        # traceable by requesting its own id.
        sess_file = _dsh_session_file(session_id)
        if not sess_file:
            return {"error": "Not found"}
        return _dsh_trace_events(sess_file)

    elif agent == "qoder":
        # Qoder writes Claude-shaped JSONL, so _qoder_trace_events filters
        # rather than converts: it drops the harness's own injected context and
        # strips the <system-reminder> prefix from the opening human prompt.
        sess_file = _qoder_session_file(session_id)
        if not sess_file:
            return {"error": "Not found"}
        return _qoder_trace_events(sess_file)

    elif agent in ["gemini", "antigravity"]:
        # Antigravity CLI (agy) sessions store the real per-step trajectory in
        # conversations/<id>.db — far richer than the brain markdown. Prefer it.
        if agent == "antigravity":
            cli_db = ANTIGRAVITY_CLI_DIR / "conversations" / f"{session_id}.db"
            if cli_db.exists():
                cli_msgs = _antigravity_cli_trace(cli_db, session_id)
                if cli_msgs:
                    return {
                        "sessionId": session_id,
                        "projectHash": "",
                        "kind": "antigravity_cli",
                        "messages": cli_msgs,
                    }
        # Antigravity brain-based session (has no .json file; synthesize from markdown artifacts)
        brain_dir = ANTIGRAVITY_BRAIN_DIR / session_id
        for _bd in ANTIGRAVITY_BRAIN_DIRS:
            if (_bd / session_id).is_dir():
                brain_dir = _bd / session_id
                break
        if agent == "antigravity" and brain_dir.is_dir():
            messages = []
            base_ts = None
            try: base_ts = brain_dir.stat().st_mtime * 1000
            except Exception: base_ts = 0
            for i, (fname, role, label) in enumerate([
                ("task.md", "user", "User task"),
                ("implementation_plan.md", "gemini", "Implementation plan"),
                ("walkthrough.md", "gemini", "Walkthrough"),
            ]):
                fp = brain_dir / fname
                if not fp.exists(): continue
                try: body = fp.read_text(errors="ignore")
                except Exception: continue
                text = f"**{label}**\n\n{body}"
                # User expects array form; assistant ("gemini") renderer expects a string.
                content = [{"type": "text", "text": text}] if role == "user" else text
                messages.append({
                    "id": f"{session_id}-{fname}",
                    "type": role,
                    "role": role,
                    "content": content,
                    "normalized_timestamp": (base_ts or 0) + i * 1000,
                })
            return {
                "sessionId": session_id,
                "projectHash": "",
                "startTime": datetime.fromtimestamp((base_ts or 0) / 1000, tz=timezone.utc).isoformat() if base_ts else None,
                "lastUpdated": datetime.fromtimestamp((base_ts or 0) / 1000, tz=timezone.utc).isoformat() if base_ts else None,
                "kind": "antigravity_brain",
                "messages": messages,
            }
        files = (
            list((GEMINI_DIR / "tmp").glob(f"**/chats/session-*{session_id[:8]}*.json*"))
            or list((GEMINI_DIR / "tmp").glob(f"**/chats/*{session_id}*.json*"))
        )
        if files:
            data = _parse_gemini_chat_file(files[0])
            if data:
                # Add normalized_timestamp to messages
                for msg in data.get("messages", []):
                    if msg.get("timestamp") and "normalized_timestamp" not in msg:
                        try:
                            ts = _aware(datetime.fromisoformat(msg["timestamp"].replace('Z', '+00:00')))
                            msg["normalized_timestamp"] = ts.timestamp() * 1000
                        except Exception: pass
                return data
        # Antigravity / Gemini log-only sessions: synthesize messages from the per-tmp-dir
        # logs.json that records every user/assistant turn with its sessionId.
        if agent in ("antigravity", "gemini"):
            log_messages = []
            log_base_ts = None
            for log_file in (GEMINI_DIR / "tmp").glob("*/logs.json"):
                try:
                    log_entries = json.loads(log_file.read_text(encoding="utf-8", errors="replace"))
                except Exception:
                    continue
                if not isinstance(log_entries, list):
                    continue
                matched = [e for e in log_entries if e.get("sessionId") == session_id]
                if not matched:
                    continue
                for i, e in enumerate(matched):
                    raw_role = (e.get("type") or "").lower()
                    if raw_role in ("user", "human"):
                        role = "user"
                        content = [{"type": "text", "text": e.get("message", "")}]
                    else:
                        # Anything not a user turn renders as the assistant ("gemini") side.
                        role = "gemini"
                        content = e.get("message", "")
                    msg = {
                        "id": f"{session_id}-{e.get('messageId', i)}",
                        "type": role,
                        "role": role,
                        "content": content,
                    }
                    ts_str = e.get("timestamp")
                    if ts_str:
                        try:
                            ts = _aware(datetime.fromisoformat(ts_str.replace('Z', '+00:00')))
                            ts_ms = ts.timestamp() * 1000
                            msg["normalized_timestamp"] = ts_ms
                            msg["timestamp"] = ts_str
                            log_base_ts = log_base_ts or ts_ms
                        except Exception:
                            pass
                    log_messages.append(msg)
                # Found the session in this logs.json — no need to scan further.
                break
            if log_messages:
                return {
                    "sessionId": session_id,
                    "projectHash": "",
                    "kind": "antigravity_logs",
                    "messages": log_messages,
                }
        return {"error": "Not found"}
    elif agent == "muse":
        path = next((p for p in MUSE_SESSIONS_DIR.glob("*/*/*/*/session.jsonl")
                     if p.parent.name == session_id), None)
        if path is None:
            return {"error": "Not found"}
        return _muse_trace_events(path)
    elif agent == "prime":
        path = None
        rows: List[Dict[str, Any]] = []
        for candidate in PRIME_SESSIONS_DIR.glob("*.jsonl"):
            try:
                with open(candidate, "r", encoding="utf-8", errors="replace") as f:
                    candidate_rows = [json.loads(line) for line in f if line.strip()]
            except (OSError, json.JSONDecodeError, ValueError):
                continue
            header = next((r for r in candidate_rows if isinstance(r, dict) and r.get("type") == "session"), None)
            if isinstance(header, dict) and header.get("id") == session_id:
                path, rows = candidate, [r for r in candidate_rows if isinstance(r, dict)]
                break
        if path is None:
            return {"error": "Not found"}
        events = []
        for row in _prime_active_entries(rows):
            message = row.get("message")
            if not isinstance(message, dict):
                continue
            ts = row.get("timestamp")
            try: ts_ms = _aware(datetime.fromisoformat(ts.replace("Z", "+00:00"))).timestamp() * 1000 if isinstance(ts, str) else None
            except ValueError: ts_ms = None
            base = {"timestamp": ts_ms, "normalized_timestamp": ts_ms}
            role = message.get("role")
            if role == "user":
                text = _prime_text(message.get("content"))
                if text: events.append({"type": "user", "payload": {"content": text}, **base})
            elif role == "assistant":
                for part in message.get("content") or []:
                    if not isinstance(part, dict): continue
                    if part.get("type") == "text" and isinstance(part.get("text"), str):
                        events.append({"type": "assistant", "payload": {"content": part["text"]}, **base})
                    elif part.get("type") == "thinking" and isinstance(part.get("thinking"), str):
                        events.append({"type": "assistant_thinking", "payload": {"text": part["thinking"]}, **base})
                    elif part.get("type") == "toolCall":
                        events.append({"type": "tool_call", "payload": {"tool": part.get("name"), "args": part.get("arguments")}, **base})
            elif role == "toolResult":
                text = _prime_text(message.get("content"))
                events.append({"type": "tool_result", "payload": {"tool": message.get("toolName"), "content": text}, **base})
        return events
    elif agent == "qwen":
        files = list(QWEN_DIR.glob(f"projects/**/chats/{session_id}.jsonl"))
        if not files: return {"error": "Not found"}
        events = []
        with open(files[0], "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if data.get("timestamp"):
                        try:
                            ts = _aware(datetime.fromisoformat(data["timestamp"].replace('Z', '+00:00')))
                            data["normalized_timestamp"] = ts.timestamp() * 1000
                        except Exception: pass
                    events.append(data)
                except Exception: continue
        return events
    elif agent == "vibe":
        short = (session_id or "").split("-")[0]
        files = list(VIBE_DIR.glob(f"logs/session/*{session_id}*.json"))
        if not files and short:
            files = list(VIBE_DIR.glob(f"logs/session/*{short}*.json"))
        if not files:
            for cf in (VIBE_DIR / "logs" / "session").glob("*.json"):
                try:
                    with open(cf, "r", encoding="utf-8", errors="replace") as f:
                        if json.load(f).get("metadata", {}).get("session_id") == session_id:
                            files = [cf]; break
                except Exception: continue
        if not files: return {"error": "Not found"}
        with open(files[0], "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
            events = []
            for m in data.get("messages", []):
                evt = {"type": m.get("role"), "payload": m, "timestamp": m.get("timestamp", data.get("metadata", {}).get("start_time"))}
                if evt["timestamp"]:
                    try:
                        ts = _aware(datetime.fromisoformat(evt["timestamp"]))
                        evt["normalized_timestamp"] = ts.timestamp() * 1000
                    except Exception: pass
                events.append(evt)
            return events
    elif agent == "cursor":
        files = list((CURSOR_DIR / "projects").glob(f"**/agent-transcripts/{session_id}/{session_id}.jsonl"))
        if not files: return {"error": "Not found"}
        events = []
        base_ts = None
        try: base_ts = files[0].stat().st_mtime * 1000
        except Exception: base_ts = 0
        with open(files[0], "r", encoding="utf-8", errors="replace") as f:
            idx = 0
            for line in f:
                try:
                    data = json.loads(line)
                    role = data.get("role")
                    data["type"] = role
                    # Ensure Claude-style renderers trigger by mirroring role inside message
                    if isinstance(data.get("message"), dict) and role:
                        data["message"]["role"] = role
                    data["normalized_timestamp"] = (base_ts or 0) + idx * 1000
                    events.append(data)
                    idx += 1
                except Exception: continue
        return events
    elif agent == "copilot":
        # GitHub Copilot CLI session (~/.copilot/session-state/<id>/events.jsonl)
        # takes priority — its ids are dir-named UUIDs distinct from VS Code (#36).
        cli_file = COPILOT_CLI_DIR / session_id / "events.jsonl"
        if cli_file.exists():
            events = []
            for r in _load_copilot_cli_events(cli_file):
                et = r.get("type"); d = r.get("data") or {}
                _p = _parse_copilot_iso(r.get("timestamp"))
                norm = int(_p.timestamp() * 1000) if _p else None
                base = {"timestamp": norm, "normalized_timestamp": norm}
                if et == "user.message":
                    events.append({"type": "user", "payload": {"content": d.get("content", "")}, **base})
                elif et == "assistant.message":
                    rt = d.get("reasoningText") or ""
                    if rt:
                        events.append({"type": "assistant_thinking", "payload": {"text": rt}, **base})
                    txt = d.get("content") or ""
                    if txt:
                        events.append({"type": "assistant", "payload": {"content": txt, "model": d.get("model")}, **base})
                    for tr in (d.get("toolRequests") or []):
                        events.append({"type": "tool_call", "payload": {
                            "tool": tr.get("name"), "callID": tr.get("toolCallId"),
                            "arguments": tr.get("arguments"),
                        }, **base})
                elif et == "session.model_change":
                    # Copilot records the reasoning-effort setting on model-change
                    # events (null on Claude models, which have no effort enum);
                    # surface it so the context panel can show it.
                    _ce = d.get("reasoningEffort")
                    if isinstance(_ce, str) and _ce:
                        events.append({"type": "reasoning_effort", "payload": {"effort": _ce}, **base})
            return events
        # VS Code ~1.100+ stores sessions as <id>.jsonl (delta log) instead of
        # <id>.json (single object); match both and reconstruct the .jsonl form.
        files = list(VSCODE_STORAGE.glob(f"**/chatSessions/{session_id}.json")) \
            + list(VSCODE_STORAGE.glob(f"**/chatSessions/{session_id}.jsonl"))
        if not files: return {"error": "Not found"}
        cf = files[0]
        if cf.suffix == ".jsonl":
            data = _reconstruct_vscode_chat_jsonl(cf)
        else:
            with open(cf, "r", encoding="utf-8", errors="replace") as f:
                data = json.load(f)
        events = []
        for req in data.get("requests", []):
            ts_val = req.get("timestamp")
            norm_ts = ts_val if isinstance(ts_val, (int, float)) else None
            events.append({"type": "user", "payload": req.get("message"), "timestamp": req.get("timestamp"), "normalized_timestamp": norm_ts})
            if "thinking" in req: events.append({"type": "assistant_thinking", "payload": req["thinking"], "timestamp": req.get("timestamp"), "normalized_timestamp": norm_ts})
            if "response" in req: events.append({"type": "assistant", "payload": req["response"], "timestamp": req.get("timestamp"), "normalized_timestamp": norm_ts})
        return events
    elif agent == "opencode":
        _oc_db = _opencode_db_for_session(session_id)
        if _oc_db is None: return {"error": "Not found"}
        uri = _sqlite_ro_uri(_oc_db)
        conn = sqlite3.connect(uri, uri=True, timeout=1.0)
        conn.row_factory = sqlite3.Row
        try:
            srow = conn.execute("SELECT id FROM session WHERE id=?", (session_id,)).fetchone()
            if not srow: return {"error": "Not found"}
            # Build a message_id → role map so each part can be tagged correctly.
            role_by_msg: Dict[str, str] = {}
            for mrow in conn.execute("SELECT id, data FROM message WHERE session_id=? ORDER BY time_created", (session_id,)):
                try:
                    md = json.loads(mrow["data"] or "{}")
                except Exception: md = {}
                role_by_msg[mrow["id"]] = md.get("role") or "assistant"
            events: List[Dict[str, Any]] = []
            for prow in conn.execute("SELECT message_id, time_created, data FROM part WHERE session_id=? ORDER BY time_created", (session_id,)):
                try:
                    p = json.loads(prow["data"] or "{}")
                except Exception: continue
                role = role_by_msg.get(prow["message_id"], "assistant")
                ts_ms = prow["time_created"]
                base = {"timestamp": ts_ms, "normalized_timestamp": ts_ms}
                ptype = p.get("type")
                if ptype == "text":
                    if role == "user":
                        events.append({"type": "user", "payload": {"content": p.get("text", "")}, **base})
                    else:
                        events.append({"type": "assistant", "payload": {"content": p.get("text", "")}, **base})
                elif ptype == "reasoning":
                    events.append({"type": "assistant_thinking", "payload": {"text": p.get("text", "")}, **base})
                elif ptype == "tool":
                    events.append({"type": "tool_call", "payload": {
                        "tool": p.get("tool"),
                        "callID": p.get("callID"),
                        "state": p.get("state"),
                    }, **base})
                elif ptype == "step-finish":
                    # Lifecycle marker, not its own trace event — but it carries
                    # the step's token usage, so attach it to the step's last
                    # emitted event for the per-step usage UI (#128).
                    tk = p.get("tokens")
                    if isinstance(tk, dict) and events:
                        events[-1]["tokens"] = tk
                # step-start is a lifecycle marker; skip in trace
            return events
        finally:
            conn.close()
    elif agent == "hermes":
        for db_path in _hermes_dbs():
            try:
                uri = _sqlite_ro_uri(db_path)
                conn = sqlite3.connect(uri, uri=True, timeout=1.0)
                conn.row_factory = sqlite3.Row
                try:
                    srow = conn.execute("SELECT id, model_config FROM sessions WHERE id=?", (session_id,)).fetchone()
                    if not srow:
                        continue
                    events: List[Dict[str, Any]] = []
                    # Surface the reasoning-effort setting (model_config.
                    # reasoning_config.effort) as a session-level meta event so the
                    # context panel can show it, mirroring the codex session_meta shape.
                    try:
                        _mc = json.loads(srow["model_config"] or "{}")
                        _rc = _mc.get("reasoning_config") or {}
                        if _rc.get("enabled") and isinstance(_rc.get("effort"), str) and _rc.get("effort"):
                            events.append({"type": "session_meta", "payload": {"effort": _rc["effort"]}})
                    except Exception:
                        pass
                    for mrow in conn.execute(
                        "SELECT role, content, tool_calls, tool_call_id, tool_name, "
                        "timestamp, reasoning_content FROM messages WHERE session_id=? "
                        "ORDER BY timestamp",
                        (session_id,)
                    ):
                        ts_ms = int((mrow["timestamp"] or 0) * 1000)
                        base = {"timestamp": ts_ms, "normalized_timestamp": ts_ms}
                        role = mrow["role"]
                        content = mrow["content"] or ""
                        if role == "user" and content:
                            events.append({"type": "user", "payload": {"content": content}, **base})
                        elif role == "assistant":
                            reasoning = mrow["reasoning_content"] or ""
                            if reasoning:
                                events.append({"type": "assistant_thinking", "payload": {"text": reasoning}, **base})
                            if content:
                                events.append({"type": "assistant", "payload": {"content": content}, **base})
                            tcs_raw = mrow["tool_calls"]
                            if tcs_raw:
                                try:
                                    tcs = json.loads(tcs_raw)
                                except Exception: tcs = []
                                if isinstance(tcs, list):
                                    for tc in tcs:
                                        if not isinstance(tc, dict): continue
                                        fn = tc.get("function") or {}
                                        # Parse args JSON when present so the frontend can render
                                        # delegate_task's `goal`, `context`, etc.
                                        args_raw = fn.get("arguments") or ""
                                        args: Any = None
                                        if isinstance(args_raw, str):
                                            try: args = json.loads(args_raw)
                                            except Exception: args = args_raw
                                        else:
                                            args = args_raw
                                        events.append({"type": "tool_call", "payload": {
                                            "tool": tc.get("name") or fn.get("name") or mrow["tool_name"],
                                            "callID": tc.get("call_id") or tc.get("id"),
                                            "args": args,
                                            "state": "completed",
                                        }, **base})
                        elif role == "tool":
                            # Hermes records tool results as role='tool'; surface as a separate
                            # event AND carry the originating call_id so the frontend can pair
                            # tool_call <-> tool_result (used by delegate_task subagent cards).
                            events.append({"type": "tool_result", "payload": {
                                "tool": mrow["tool_name"],
                                "content": content,
                                "callID": mrow["tool_call_id"],
                            }, **base})
                    return events
                finally:
                    conn.close()
            except Exception:
                continue
        return {"error": "Not found"}
    elif agent == "smallcode":
        # Traces are project-local; use the cached session list (populated by
        # GET /sessions, which any dashboard load already triggers) to find
        # which project this trace lives under, falling back to the
        # user-configured extra roots if the cache hasn't been built yet.
        candidate_roots: List[str] = list(SMALLCODE_EXTRA_ROOTS)
        cached_sessions = _sessions_cache.get("data")
        if cached_sessions:
            for s in cached_sessions:
                if s.get("agent") == "smallcode" and s.get("project"):
                    candidate_roots.append(s["project"])

        trace_path = None
        for root in dict.fromkeys(candidate_roots):  # dedupe, keep order
            p = Path(root).expanduser() / ".smallcode" / "traces" / f"{session_id}.json"
            if p.exists():
                trace_path = p
                break
        if trace_path is None:
            return {"error": "Not found"}

        try:
            with open(trace_path, "r", encoding="utf-8") as f:
                trace = json.load(f)
        except Exception:
            return {"error": "Not found"}

        base_ms = None
        started_at = trace.get("startedAt")
        if started_at:
            try:
                base_ms = _aware(datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))).timestamp() * 1000
            except Exception:
                base_ms = None
        if base_ms is None:
            base_ms = _file_mtime_utc(trace_path).timestamp() * 1000

        events = []
        prompt = trace.get("prompt")
        if prompt:
            events.append({"type": "user", "payload": {"content": prompt},
                            "timestamp": base_ms, "normalized_timestamp": base_ms})
        for i, step in enumerate(trace.get("steps") or [], start=1):
            if not isinstance(step, dict):
                continue
            ts_ms = step.get("timestamp")
            if not isinstance(ts_ms, (int, float)):
                ts_ms = base_ms + i * 1000
            base = {"timestamp": ts_ms, "normalized_timestamp": ts_ms}
            if step.get("type") == "tool_call":
                events.append({"type": "tool_call", "payload": {
                    "tool": step.get("name"), "args": step.get("args"),
                }, **base})
                events.append({"type": "tool_result", "payload": {
                    "tool": step.get("name"), "content": step.get("result"),
                }, **base})
            else:
                events.append({"type": step.get("type") or "assistant", "payload": step, **base})
        return events
    elif agent == "cline":
        # (a) CLI store: session row -> messages_path transcript.
        db_path = CLINE_DIR / "data" / "db" / "sessions.db"
        if db_path.exists():
            srow = None
            try:
                uri = _sqlite_ro_uri(db_path)
                conn = sqlite3.connect(uri, uri=True, timeout=1.0)
                conn.row_factory = sqlite3.Row
                try:
                    srow = conn.execute(
                        "SELECT messages_path FROM sessions WHERE session_id=?", (session_id,)
                    ).fetchone()
                finally:
                    conn.close()
            except Exception:
                srow = None
            if srow and srow["messages_path"]:
                mp = Path(srow["messages_path"])
                if mp.exists():
                    try:
                        with open(mp, "r", encoding="utf-8", errors="replace") as f:
                            mdata = json.load(f)
                        events = []
                        for i, m in enumerate(mdata.get("messages") or []):
                            if not isinstance(m, dict):
                                continue
                            ts_ms = m.get("ts")
                            if not isinstance(ts_ms, (int, float)):
                                ts_ms = i * 1000
                            base = {"timestamp": ts_ms, "normalized_timestamp": ts_ms}
                            role = m.get("role")
                            text_parts = []
                            for block in (m.get("content") or []):
                                if not isinstance(block, dict):
                                    continue
                                if block.get("type") == "text":
                                    text_parts.append(block.get("text") or "")
                                elif block.get("type") == "thinking":
                                    events.append({"type": "assistant_thinking",
                                                   "payload": {"text": block.get("thinking") or ""}, **base})
                            text = "".join(text_parts)
                            if role == "user" and text:
                                events.append({"type": "user", "payload": {"content": text}, **base})
                            elif role == "assistant" and text:
                                events.append({"type": "assistant", "payload": {"content": text}, **base})
                        return events
                    except Exception:
                        pass
        # (b) VS Code store: transcript at tasks/<id>/api_conversation_history.json
        transcript_path = CLINE_VSCODE_DIR / "tasks" / session_id / "api_conversation_history.json"
        if transcript_path.exists():
            try:
                with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
                    data = json.load(f)
            except Exception:
                data = None
            if isinstance(data, list):
                events = []
                for i, m in enumerate(data):
                    if not isinstance(m, dict):
                        continue
                    role = m.get("role")
                    content = m.get("content")
                    text = content if isinstance(content, str) else (json.dumps(content) if content else "")
                    base = {"timestamp": i * 1000, "normalized_timestamp": i * 1000}
                    events.append({"type": role or "assistant", "payload": {"content": text}, **base})
                return events
        return {"error": "Not found"}
    # elif agent == "ollama":
    #     if (OLLAMA_DIR / "history").exists():
    #         with open(OLLAMA_DIR / "history", "r") as f:
    #             prompts = [line.strip() for line in f if line.strip()]
    #             events = []
    #             for i, p in enumerate(reversed(prompts)):
    #                 events.append({
    #                     "type": "user",
    #                     "content": p,
    #                     "normalized_timestamp": i * 1000
    #                 })
    #             return events
    return {"error": "Invalid agent"}


def _jsonl_events(path: Path) -> List[Dict[str, Any]]:
    """Parse a transcript JSONL into the event list shape the trace UI expects
    (same normalization as the claude branch of get_session_detail)."""
    events: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                data = json.loads(line)
            except Exception:
                continue
            if data.get("timestamp"):
                try:
                    ts = _aware(datetime.fromisoformat(data["timestamp"].replace('Z', '+00:00')))
                    data["normalized_timestamp"] = ts.timestamp() * 1000
                except Exception:
                    pass
            events.append(data)
    return events


_SUBAGENT_ID_RE = re.compile(r"^[\w.-]+$")


@app.get("/sessions/{session_id}/subagents/{agent_id}/trace")
async def session_subagent_trace(session_id: str, agent_id: str, agent: str):
    """Raw trace of ONE subagent transcript, for the in-place drill-in viewer.

    Claude, Cursor, and Muse need this: their subagent transcripts are files
    inside the parent's session dir, NOT sessions of their own (grok/codex/
    opencode/hermes children are real sessions — fetch the normal detail
    endpoint for those instead)."""
    if not _SUBAGENT_ID_RE.match(agent_id or ""):
        return {"error": "Invalid subagent id"}
    if agent == "claude":
        files = list(CLAUDE_DIR.glob(f"projects/**/{session_id}.jsonl"))
        if not files:
            return {"error": "Not found"}
        sub_dir = files[0].parent / session_id / "subagents"
        t = sub_dir / f"agent-{agent_id}.jsonl"
        if not t.exists():
            # Dynamic-workflow agents live one level deeper, under workflows/wf_*/.
            t = next((sub_dir / "workflows").glob(f"wf_*/agent-{agent_id}.jsonl"), None)
        if not t or not t.exists():
            return {"error": "Not found"}
        return _jsonl_events(t)
    if agent == "cursor":
        for pd in (CURSOR_DIR / "projects").glob("*"):
            t = pd / "agent-transcripts" / session_id / "subagents" / f"{agent_id}.jsonl"
            if t.exists():
                return _jsonl_events(t)
        return {"error": "Not found"}
    if agent == "muse":
        parent = next((p for p in MUSE_SESSIONS_DIR.glob("*/*/*/*/session.jsonl")
                       if p.parent.name == session_id), None)
        if parent is None:
            return {"error": "Not found"}
        child = parent.parent / "subagent" / agent_id / "session.jsonl"
        try:
            if not child.resolve().is_relative_to(parent.parent.resolve()) or not child.is_file():
                return {"error": "Not found"}
        except OSError:
            return {"error": "Not found"}
        return _muse_trace_events(child)
    return {"error": "Invalid agent"}


@app.get("/sessions/{session_id}/delegation")
async def session_delegation(session_id: str, agent: str):
    """Per-session subagent/delegation breakdown (overlay, like hermes-overlay).

    claude: full per-subagent usage + cost from <sid>/subagents/agent-*.jsonl.
    cursor: spawn count only — its subagent transcripts carry no usage fields.
    opencode/hermes: parent/child session linkage from their SQLite hierarchies.
    Everything else: {"supported": False} — the agent's logs don't record spawns.
    """
    if agent == "claude":
        files = list(CLAUDE_DIR.glob(f"projects/**/{session_id}.jsonl"))
        if not files:
            return {"error": "Not found"}
        deleg = _claude_subagent_usage(files[0], session_id)
        if not deleg:
            return {"supported": True, "tokens_recorded": True, "spawn_count": 0,
                    "subagents": [], "totals": None, "cost": 0.0}
        return {"supported": True, "tokens_recorded": True, **deleg}

    if agent == "cursor":
        for pd in (CURSOR_DIR / "projects").glob("*"):
            trans_dir = pd / "agent-transcripts" / session_id
            if trans_dir.is_dir():
                sub_files = sorted((trans_dir / "subagents").glob("*.jsonl")) if (trans_dir / "subagents").is_dir() else []
                return {"supported": True, "tokens_recorded": False,
                        "spawn_count": len(sub_files),
                        "subagents": [{"agent_id": f.stem, "agent_type": "unknown",
                                       "tokens": None, "cost": None} for f in sub_files]}
        return {"error": "Not found"}

    if agent == "muse":
        parent = next((p for p in MUSE_SESSIONS_DIR.glob("*/*/*/*/session.jsonl")
                       if p.parent.name == session_id), None)
        if parent is None:
            return {"error": "Not found"}
        summary = _muse_log_summary(parent)
        subagents = []
        for rel in dict.fromkeys(summary["children"]):
            try:
                child = (parent.parent / rel).resolve()
                if not child.is_relative_to(parent.parent.resolve()) or not child.is_file():
                    continue
            except (OSError, ValueError):
                continue
            child_summary = _muse_log_summary(child)
            t = child_summary["tokens"]
            subagents.append({"agent_id": child.parent.name, "agent_type": "muse-subagent",
                              "model": child_summary["model"], "tokens": {**t, "total": sum(t.values())},
                              "cost": calculate_cost(child_summary["model"], t["input"], t["output"], t["cached"], cache_creation_tokens=t["cache_creation"])})
        totals = {key: sum(s["tokens"].get(key, 0) for s in subagents)
                  for key in ("input", "output", "cached", "cache_creation", "reasoning", "total")}
        return {"supported": True, "tokens_recorded": True, "spawn_count": len(subagents),
                "subagents": subagents, "totals": totals,
                "cost": sum(s["cost"] for s in subagents)}

    if agent == "qoder":
        # Qoder children sit beside the parent transcript, each with a
        # .meta.json naming the agent type and the task it was given. Their
        # spend is real but denominated in credits, so tokens_recorded is
        # False and the figure to read is delegated_credits.
        parent_file = _qoder_session_file(session_id)
        if parent_file is None:
            return {"error": "Not found"}
        kids = _qoder_subagents(parent_file.parent / parent_file.stem)
        subagents = [{
            "agent_id": kid["id"],
            "agent_type": kid["agent_type"],
            "description": kid["description"],
            "model": kid["model"],
            "tokens": {"input": 0, "output": 0, "cached": 0,
                       "cache_creation": 0, "reasoning": 0, "total": 0},
            "cost": 0.0,
            "credits": kid["credits"],
        } for kid in kids]
        return {"supported": True, "tokens_recorded": False,
                "spawn_count": len(subagents), "subagents": subagents,
                "totals": None, "cost": 0.0,
                "delegated_credits": round(sum(k["credits"] for k in kids), 6)}

    if agent == "dsh":
        # DSH children are their own session logs, linked by an explicit
        # parentSession header field, so per-subagent usage is real (not just a
        # spawn count) -- same contract as muse above.
        parent_file = _dsh_session_file(session_id)
        if parent_file is None:
            return {"error": "Not found"}
        subagents = []
        for child_file in DSH_SESSIONS_DIR.glob("*/*/session.jsonl.zstd"):
            if child_file == parent_file:
                continue
            child = _dsh_parse_session(child_file)
            if not child or child.get("origin") != "subagent" or child.get("parent_session") != session_id:
                continue
            subagents.append({"agent_id": child["id"], "agent_type": "dsh-subagent",
                              "model": child["model"], "tokens": child["tokens"],
                              "cost": child["cost"]})
        totals = {key: sum(s["tokens"].get(key, 0) for s in subagents)
                  for key in ("input", "output", "cached", "cache_creation", "reasoning", "total")}
        return {"supported": True, "tokens_recorded": True, "spawn_count": len(subagents),
                "subagents": subagents, "totals": totals,
                "cost": sum(s["cost"] for s in subagents)}

    if agent == "opencode":
        _oc_db = _opencode_db_for_session(session_id)
        if _oc_db is None:
            return {"error": "Not found"}
        try:
            conn = sqlite3.connect(_sqlite_ro_uri(_oc_db), uri=True, timeout=1.0)
            try:
                cols = {r[1] for r in conn.execute("PRAGMA table_info(session)")}
                if "parent_id" not in cols:
                    return {"supported": False}
                row = conn.execute("SELECT parent_id FROM session WHERE id=?", (session_id,)).fetchone()
                if row is None:
                    return {"error": "Not found"}
                children = [r[0] for r in conn.execute(
                    "SELECT id FROM session WHERE parent_id=?", (session_id,))]
                return {"supported": True, "tokens_recorded": False,
                        "parent_session_id": row[0],
                        "child_session_ids": children,
                        "linked_children": len(children)}
            finally:
                conn.close()
        except Exception:
            return {"error": "Not found"}

    if agent == "hermes":
        for db_path in _hermes_dbs():
            try:
                conn = sqlite3.connect(_sqlite_ro_uri(db_path), uri=True, timeout=1.0)
                try:
                    row = conn.execute("SELECT parent_session_id FROM sessions WHERE id=?", (session_id,)).fetchone()
                    if row is None:
                        continue
                    children = [r[0] for r in conn.execute(
                        "SELECT id FROM sessions WHERE parent_session_id=?", (session_id,))]
                    return {"supported": True, "tokens_recorded": False,
                            "parent_session_id": row[0],
                            "child_session_ids": children,
                            "linked_children": len(children)}
                finally:
                    conn.close()
            except Exception:
                continue
        return {"error": "Not found"}

    if agent == "grok":
        for bucket in GROK_SESSIONS_DIR.glob("*"):
            sess_dir = bucket / session_id
            if not (sess_dir.is_dir() and (sess_dir / GROK_SUMMARY).exists()):
                continue
            spawns = _grok_subagent_meta(sess_dir)
            # Parent linkage: the parent's spawn meta names this session as child.
            parent_id = None
            try:
                for other in bucket.iterdir():
                    if not other.is_dir() or other.name == session_id:
                        continue
                    for m in _grok_subagent_meta(other):
                        if m.get("child_session_id") == session_id:
                            parent_id = other.name
                            break
                    if parent_id:
                        break
            except Exception:
                pass
            return {"supported": True, "tokens_recorded": False,
                    "spawn_count": len(spawns), "subagents": spawns,
                    "parent_session_id": parent_id,
                    "child_session_ids": [m["child_session_id"] for m in spawns
                                          if m.get("child_session_id")],
                    "linked_children": len(spawns)}
        return {"error": "Not found"}

    if agent == "codex":
        def _spawn_meta(path):
            """(payload, thread_spawn) from a rollout's session_meta first line."""
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    first = json.loads(f.readline())
            except Exception:
                return None, None
            p = first.get("payload") or {}
            src = p.get("source")
            spawn = (src.get("subagent") or {}).get("thread_spawn") if isinstance(src, dict) else None
            if spawn is None and p.get("thread_source") == "subagent":
                spawn = {}
            return p, spawn

        own = list(CODEX_DIR.glob(f"sessions/**/rollout-*{session_id}*.jsonl"))
        if not own:
            return {"error": "Not found"}
        payload, spawn = _spawn_meta(own[0])
        parent_id = None
        info = None
        if spawn is not None:
            parent_id = spawn.get("parent_thread_id") or (payload or {}).get("forked_from_id")
            info = {"role": spawn.get("agent_role") or (payload or {}).get("agent_role"),
                    "nickname": spawn.get("agent_nickname") or (payload or {}).get("agent_nickname"),
                    "depth": spawn.get("depth")}
        children = []
        try:
            for f in (CODEX_DIR / "sessions").rglob("rollout-*.jsonl"):
                if session_id in f.name:
                    continue
                p, sp = _spawn_meta(f)
                if sp is None:
                    continue
                pid = sp.get("parent_thread_id") or (p or {}).get("forked_from_id")
                if pid != session_id:
                    continue
                parts = f.stem.split("-")
                children.append({
                    "child_session_id": "-".join(parts[-5:]) if len(parts) >= 6 else f.stem,
                    "agent_role": sp.get("agent_role") or (p or {}).get("agent_role"),
                    "nickname": sp.get("agent_nickname") or (p or {}).get("agent_nickname"),
                })
        except Exception:
            pass
        return {"supported": True, "tokens_recorded": False,
                "parent_session_id": parent_id, "subagent_info": info,
                "subagents": children,
                "child_session_ids": [c["child_session_id"] for c in children],
                "linked_children": len(children)}

    if agent == "antigravity":
        kids = _antigravity_subagent_children(session_id)
        return {"supported": True, "tokens_recorded": False,
                "child_session_ids": kids, "linked_children": len(kids)}

    return {"supported": False}


# ---------------------------------------------------------------------------
# Git-worktree canonicalisation
#
# A single logical repo can be checked out into several git worktrees, each at
# its own filesystem path (e.g. <repo>/.claude/worktrees/<name>). Every agent
# tags a session by its raw cwd, so the same repo fragments into many project
# cards. `canonical_repo()` maps a worktree path back to its main repo root so
# we can group them — without shelling out to git per session.
#
# A worktree's `.git` is a *file* (not a dir) containing
# `gitdir: <repo>/.git/worktrees/<name>`; the repo root is the grandparent of
# that worktrees/<name> dir. We read that file directly (cheap, only fires when
# `.git` is a file). When the worktree dir is gone we fall back to the
# conventional `.claude|.grok/worktrees/<name>` path shape.
# ---------------------------------------------------------------------------
_canonical_repo_cache: Dict[str, str] = {}
_WORKTREE_PATH_RE = re.compile(r"[/\\]\.(?:claude|grok)[/\\]worktrees[/\\][^/\\]+[/\\]?$")


def _repo_root_from_worktree_gitfile(git_file: Path) -> Optional[str]:
    """Given a worktree's `.git` *file*, return the main repo root, or None."""
    try:
        txt = git_file.read_text("utf-8", errors="ignore").strip()
    except Exception:
        return None
    if not txt.startswith("gitdir:"):
        return None
    gitdir = Path(txt[len("gitdir:"):].strip())
    # gitdir == <repo>/.git/worktrees/<name>  ->  repo root is <repo>
    if gitdir.parent.name == "worktrees" and gitdir.parent.parent.name == ".git":
        return str(gitdir.parent.parent.parent)
    return None


def canonical_repo(path: str) -> str:
    """Map a worktree (or a path *inside* a worktree) to its main repo root.

    Walks up the tree to the nearest `.git`. A `.git` *file* means a worktree —
    resolve to its main repo, so a session run from `<repo>/.claude/worktrees/x`
    OR from `<repo>/.claude/worktrees/x/backend` both fold to `<repo>`. A `.git`
    *dir* means the main checkout: the repo root and any plain subdirectory of it
    are left unchanged (they are the same working tree, not separate worktrees —
    folding every `frontend/`/`backend/` into the repo is not the intent here).
    Returns `path` unchanged when no worktree is found — in canonical form
    (see `tt_paths.canonical_project`) either way, so callers can compare the
    result against canonicalised card paths with startswith()/dict lookups.
    Memoised."""
    if not path:
        return path
    cached = _canonical_repo_cache.get(path)
    if cached is not None:
        return cached
    result = path
    try:
        cur = Path(path)
        for _ in range(40):  # bounded walk-up; real paths are far shallower
            git = cur / ".git"
            if git.is_file():
                result = _repo_root_from_worktree_gitfile(git) or str(cur)
                break
            if git.is_dir():
                break  # main checkout (root or plain subdir) — leave as-is
            parent = cur.parent
            if parent == cur:
                break
            cur = parent
        if result == path:
            # Backstop for a deleted/unreadable worktree that still matches the
            # conventional in-repo layout (folder gone, so the walk-up found no
            # .git). Only fires for the <repo>/.claude|.grok/worktrees/<name> shape.
            m = _WORKTREE_PATH_RE.search(path)
            if m:
                result = path[:m.start()]
    except Exception:
        result = path
    # `str(Path)` above yields native separators (`C:\repo` on Windows) while
    # card paths are forward-slashed; emit both in one identity space or the
    # worktree grouping below would synthesise duplicate repo cards.
    result = canonical_project(result)
    _canonical_repo_cache[path] = result
    return result


_worktree_registry_cache: Dict[str, List[str]] = {}
_GITDIR_TAIL_RE = re.compile(r"[/\\]\.git[/\\]?$")


def _repo_worktree_paths(repo: str) -> List[str]:
    """Every worktree path git has registered for `repo`, read from the repo-side
    registry `<repo>/.git/worktrees/*/gitdir`.

    This still lists worktrees whose folder was *deleted* (until `git worktree
    prune` runs), so it recovers the repo link for deleted/external worktrees
    that `canonical_repo()` (which reads the worktree's own `.git`) cannot."""
    cached = _worktree_registry_cache.get(repo)
    if cached is not None:
        return cached
    paths: List[str] = []
    try:
        wt_dir = Path(repo) / ".git" / "worktrees"
        if wt_dir.is_dir():
            for d in wt_dir.iterdir():
                gd = d / "gitdir"
                if not gd.is_file():
                    continue
                # gitdir points at <worktree>/.git — strip the trailing /.git
                wp = _GITDIR_TAIL_RE.sub("", gd.read_text("utf-8", errors="ignore").strip())
                if wp:
                    # Canonical form: these keys are looked up with card paths.
                    paths.append(canonical_project(wp))
    except Exception:
        pass
    _worktree_registry_cache[repo] = paths
    return paths


@app.get("/projects")
async def get_projects(include_hidden: bool = False):
    sessions = await get_sessions_cached(); projects = {}
    # Compare canonically: entries saved before project canonicalisation (or
    # by hand) may use another separator style than the cards do now.
    hidden = {canonical_project(p) for p in load_hidden()}
    for s in sessions:
        proj = s["project"]
        # The Antigravity "unassigned" sentinel isn't a real workspace — skip it
        # so it never shows as a project card. These sessions remain visible in
        # the dashboard and session lists, just not grouped as a project.
        if proj == ANTIGRAVITY_UNASSIGNED:
            continue
        if proj not in projects:
            # Basename that handles both POSIX (/) and Windows (\) separators
            proj_name = (os.path.basename((proj or "").replace("\\", "/").rstrip("/")) or proj or "unknown").strip()
            projects[proj] = {"name": proj_name, "path": proj, "session_count": 0, "agents": set(), "mcp_tools": set(), "subagent_count": 0, "plan_count": 0, "tokens": {"input": 0, "output": 0, "cached": 0, "total": 0, "cost": 0.0}, "plans": [], "artifacts": []}
        projects[proj]["session_count"] += 1; projects[proj]["agents"].add(s["agent"])
        for t in s.get("mcp_tools", []): projects[proj]["mcp_tools"].add(t)
        if s.get("has_plan"): projects[proj]["plan_count"] += 1
        projects[proj]["subagent_count"] += len(s.get("subagents", []))
        st = s.get("tokens", {})
        for k in ["input", "output", "cached", "total"]: projects[proj]["tokens"][k] += st.get(k, 0)
        # `cost` is None for an unpriced session (the key EXISTS, so a dict
        # default never fires). An unpriced session contributes 0 to a SUM
        # while still rendering individually as "not captured".
        projects[proj]["tokens"]["cost"] += s.get("cost") or 0.0
        projects[proj]["plans"].extend(s.get("plans", []))
        projects[proj]["artifacts"].extend(s.get("published_artifacts", []))
    for p in projects.values():
        p["agents"] = list(p["agents"])
        p["mcp_tools"] = list(p["mcp_tools"])
        p["plans"] = sorted(p["plans"], key=lambda x: str(x["timestamp"]), reverse=True)
        # One artifact, one card. `published_artifacts` is deduped by url
        # *within* a session, but a project sums several sessions and a resumed
        # or forked session replays the original publish record verbatim — same
        # url, same path, same timestamp, only a different session_id. Extending
        # without a dedupe therefore surfaced one publish once per session that
        # carried it, which rendered as duplicate cards (and duplicate React
        # keys, since the UI keys on the same identity).
        p["artifacts"] = _dedupe_artifacts(
            sorted(p["artifacts"], key=lambda x: str(x.get("timestamp") or ""), reverse=True))
        # Status: is this project folder still on disk?
        try:
            p["status"] = "active" if Path(p["path"]).exists() else "missing"
        except Exception:
            p["status"] = "missing"
        p["hidden"] = p["path"] in hidden
        # Count configured subagents on disk for this project path
        try:
            p["configured_subagent_count"] = 0
            # 1. Standard Claude agents
            claude_dir = Path(p["path"]) / ".claude" / "agents"
            if claude_dir.exists():
                p["configured_subagent_count"] += len(list(claude_dir.glob("*.md")))
            # 2. Cursor skills/agents
            cursor_dir = Path(p["path"]) / ".cursor" / "skills-cursor"
            if cursor_dir.exists():
                # For Cursor, we count directories that contain a SKILL.md
                p["configured_subagent_count"] += len(list(cursor_dir.glob("*/SKILL.md")))
            # 3. Generic .agents directory
            agents_dir = Path(p["path"]) / ".agents" / "skills"
            if agents_dir.exists():
                p["configured_subagent_count"] += len(list(agents_dir.glob("*/SKILL.md")))
        except Exception: pass
    # ----- Git-worktree grouping -------------------------------------------
    # Each worktree keeps its own card (non-destructive: its path stays the
    # identity used by routes/filters/aliases). We *additionally* tell each
    # card its canonical repo, then give the main-repo card a list of its
    # worktrees plus rolled-up "aggregate" metrics. The repo card is
    # synthesised when the root folder itself has no direct sessions.
    def _set_worktree(p: dict, repo: str) -> None:
        p["canonical_repo"] = repo
        p["is_worktree"] = repo != p["path"]
        if p["is_worktree"]:
            # Relative subpath for nested worktrees (e.g. .claude/worktrees/x);
            # basename for worktrees that live outside the repo dir (siblings).
            rel = (p["path"][len(repo):].replace("\\", "/").strip("/")
                   if p["path"].startswith(repo) else "")
            p["worktree_name"] = rel or p["name"]

    for p in projects.values():
        _set_worktree(p, canonical_repo(p["path"]))

    # Recovery pass: a worktree whose folder was deleted (and isn't under the
    # conventional .claude/worktrees layout) can't be resolved from its own
    # (now-gone) .git file. Git's repo-side registry still knows its path, so
    # build a worktree->repo index from every discovered repo and re-link any
    # still-unresolved card whose path git recognises as a worktree.
    wt_to_repo: Dict[str, str] = {}
    for repo in {p["canonical_repo"] for p in projects.values()}:
        for wp in _repo_worktree_paths(repo):
            wt_to_repo[wp] = repo
    if wt_to_repo:
        for p in projects.values():
            if not p["is_worktree"]:
                repo = wt_to_repo.get(p["path"].rstrip("/\\"))
                if repo and repo != p["path"]:
                    _set_worktree(p, repo)

    out = list(projects.values())
    if not include_hidden:
        out = [p for p in out if not p["hidden"]]

    # Group the *visible* cards by canonical repo and link worktrees to parents.
    visible_by_path = {p["path"]: p for p in out}
    groups: Dict[str, List[dict]] = {}
    for p in out:
        if p["is_worktree"]:
            groups.setdefault(p["canonical_repo"], []).append(p)

    hidden_set = hidden

    def _aggregate(members: List[dict]) -> dict:
        agg = {"session_count": 0, "subagent_count": 0, "plan_count": 0,
               "configured_subagent_count": 0,
               "tokens": {"input": 0, "output": 0, "cached": 0, "total": 0, "cost": 0.0},
               "agents": set(), "mcp_tools": set(), "worktree_count": 0}
        for m in members:
            agg["session_count"] += m.get("session_count", 0)
            agg["subagent_count"] += m.get("subagent_count", 0)
            agg["plan_count"] += m.get("plan_count", 0)
            agg["configured_subagent_count"] += m.get("configured_subagent_count", 0) or 0
            for k in ("input", "output", "cached", "total"):
                agg["tokens"][k] += m.get("tokens", {}).get(k, 0)
            agg["tokens"]["cost"] += m.get("tokens", {}).get("cost") or 0.0
            agg["agents"].update(m.get("agents", []))
            agg["mcp_tools"].update(m.get("mcp_tools", []))
            if m.get("is_worktree"):
                agg["worktree_count"] += 1
        agg["agents"] = sorted(agg["agents"])
        agg["mcp_tools"] = sorted(agg["mcp_tools"])
        return agg

    synthesized: List[dict] = []
    for repo, children in groups.items():
        children.sort(key=lambda c: c.get("tokens", {}).get("total", 0), reverse=True)
        wt_summaries = [{
            "name": c.get("worktree_name") or c["name"],
            "path": c["path"],
            "session_count": c["session_count"],
            "tokens": c["tokens"],
            "agents": c["agents"],
            "status": c.get("status", "missing"),
        } for c in children]

        parent = visible_by_path.get(repo)
        if parent is None:
            # Repo root has no direct sessions of its own — synthesise a hub
            # card. Skip if the root path is explicitly hidden.
            if repo in hidden_set and not include_hidden:
                continue
            try:
                status = "active" if Path(repo).exists() else "missing"
            except Exception:
                status = "missing"
            parent = {
                "name": (os.path.basename(repo.replace("\\", "/").rstrip("/")) or repo).strip(),
                "path": repo, "session_count": 0, "agents": [], "mcp_tools": [],
                "subagent_count": 0, "plan_count": 0, "configured_subagent_count": 0,
                "tokens": {"input": 0, "output": 0, "cached": 0, "total": 0, "cost": 0.0},
                "plans": [], "artifacts": [], "status": status, "hidden": repo in hidden_set,
                "canonical_repo": repo, "is_worktree": False, "synthesized": True,
            }
            synthesized.append(parent)

        members = [parent] + children
        parent["is_repo_root"] = True
        parent["worktrees"] = wt_summaries
        parent["aggregate"] = _aggregate(members)
        # Surface worktree-published artifacts on the repo-root card too —
        # publishes usually happen from worktree sessions but belong to the repo.
        # Identity is the hosted url for "page" artifacts, the file path for
        # "document" ones.
        seen_keys = {_artifact_key(a) for a in parent.get("artifacts", [])}
        for c in children:
            for a in c.get("artifacts", []):
                key = _artifact_key(a)
                if key and key not in seen_keys:
                    parent.setdefault("artifacts", []).append(a)
                    seen_keys.add(key)
        parent["artifacts"] = _dedupe_artifacts(
            sorted(parent.get("artifacts", []),
                   key=lambda x: str(x.get("timestamp") or ""), reverse=True))
        for c in children:
            c["parent_path"] = repo
            c["parent_name"] = parent["name"]

    out.extend(synthesized)
    return out


def _artifact_key(a: Dict[str, Any]) -> Optional[str]:
    """Identity of one artifact: the hosted url for a published page, the file
    path for a document. Two records sharing this are the same artifact, not two
    of them — a redeploy reuses the url by design."""
    return a.get("url") or a.get("path")


def _dedupe_artifacts(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Collapse artifacts that share an identity, keeping the first seen.

    Callers pass a list already sorted newest-first, so "first" is the most
    recent record and therefore the freshest title/description a later redeploy
    may have changed. Records with no identity at all are kept as-is rather than
    silently dropped.
    """
    seen = set()
    out: List[Dict[str, Any]] = []
    for a in items:
        key = _artifact_key(a)
        if key is None:
            out.append(a)
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(a)
    return out


# ---------------------------------------------------------------------------
# TokenTelemetry config endpoints (aliases + hidden projects)
# ---------------------------------------------------------------------------
class PathPayload(BaseModel):
    path: str


def _invalidate_sessions_cache():
    """Drop the sessions cache so alias/hide changes are reflected immediately."""
    _sessions_cache["data"] = None
    _sessions_cache["at"] = 0.0


@app.get("/config/hidden")
async def get_hidden():
    return sorted(load_hidden())


@app.post("/config/hide")
async def post_hide(payload: PathPayload):
    if not payload.path:
        return {"ok": False, "error": "path required"}
    updated = hide_project(payload.path)
    _invalidate_sessions_cache()
    return {"ok": True, "hidden": sorted(updated)}


@app.post("/config/unhide")
async def post_unhide(payload: PathPayload):
    if not payload.path:
        return {"ok": False, "error": "path required"}
    updated = unhide_project(payload.path)
    _invalidate_sessions_cache()
    return {"ok": True, "hidden": sorted(updated)}


@app.get("/config/update-check")
async def get_update_check():
    """Current update-check state for the Settings toggle.

    `enabled` is the saved preference; `env_forced_off` is true when
    TT_NO_UPDATE_CHECK is set, in which case the toggle is read-only (ops/policy
    override). `effective` is what actually happens (env wins)."""
    pref = bool(load_preferences().get("update_check", True))
    env_off = bool(os.environ.get("TT_NO_UPDATE_CHECK"))
    return {"enabled": pref, "env_forced_off": env_off, "effective": pref and not env_off}


@app.post("/config/update-check")
async def post_update_check(payload: dict = Body(...)):
    """Persist the update-check preference. Body: {"enabled": bool}."""
    from fastapi import HTTPException
    enabled = payload.get("enabled")
    if not isinstance(enabled, bool):
        raise HTTPException(status_code=400, detail="'enabled' must be a boolean")
    save_preferences({"update_check": enabled})
    env_off = bool(os.environ.get("TT_NO_UPDATE_CHECK"))
    return {"enabled": enabled, "env_forced_off": env_off, "effective": enabled and not env_off}


# --- Product telemetry (anonymous, opt-out, content-free) -----------------
import telemetry as _telemetry

# Frontend events we accept through the bridge. Backend-origin events
# (app.launched, trace.summarized) are emitted server-side and not listed here,
# so a remote caller can't spoof them.
_TELEMETRY_CLIENT_EVENTS = {"page.viewed", "analytics.filtered", "feature.used"}


@app.get("/config/telemetry")
async def get_telemetry():
    """Current telemetry state for the Settings toggle. Same shape as
    update-check: `enabled` is the saved preference, `env_forced_off` is true
    when DO_NOT_TRACK / TT_NO_TELEMETRY is set (toggle read-only), `effective`
    is what actually happens (env + CI win). `notice_ack` is true once the
    user has acknowledged the first-run notice (persisted in local prefs)."""
    prefs = load_preferences()
    pref = bool(prefs.get("telemetry", True))
    return {
        "enabled": pref,
        "env_forced_off": _telemetry.env_forced_off(),
        "is_ci": _telemetry._is_ci(),
        "effective": _telemetry.enabled(),
        "notice_ack": bool(prefs.get("telemetry_notice_ack", False)),
    }


@app.post("/config/telemetry")
async def post_telemetry(payload: dict = Body(...)):
    """Persist the telemetry preference. Body: {"enabled": bool}."""
    from fastapi import HTTPException
    enabled = payload.get("enabled")
    if not isinstance(enabled, bool):
        raise HTTPException(status_code=400, detail="'enabled' must be a boolean")
    save_preferences({"telemetry": enabled})
    return {
        "enabled": enabled,
        "env_forced_off": _telemetry.env_forced_off(),
        "is_ci": _telemetry._is_ci(),
        "effective": _telemetry.enabled(),
    }


@app.post("/config/telemetry/ack")
async def post_telemetry_ack():
    """Persist that the first-run notice was acknowledged so it never shows again."""
    save_preferences({"telemetry_notice_ack": True})
    return {"notice_ack": True}


@app.get("/config/telemetry/preview")
async def get_telemetry_preview():
    """Exactly what telemetry would send (synthetic samples + recent real sends)
    + the never-collected list. Powers the transparency panel."""
    return _telemetry.preview()


@app.post("/telemetry/event")
async def post_telemetry_event(payload: dict = Body(...)):
    """Bridge for frontend-origin events. The event name must be in the
    client-events allowlist; props are re-sanitized server-side by telemetry.emit
    regardless, so this endpoint can't be used to exfiltrate anything."""
    event = payload.get("event")
    if not isinstance(event, str) or event not in _TELEMETRY_CLIENT_EVENTS:
        return {"ok": False}
    props = payload.get("props")
    _telemetry.emit(event, props if isinstance(props, dict) else None)
    return {"ok": True}


@app.on_event("startup")
async def _telemetry_startup():
    """Seed the anonymous context once, then emit app.launched. All best-effort —
    a failure here must never block the server from starting."""
    try:
        try:
            cfg = _summaries.load_config()
            backend = cfg.get("backend") if cfg.get("enabled") else "none"
        except Exception:
            backend = "none"
        _telemetry.update_context(
            app_version=(_local_commit() or "unknown")[:12],
            agents=_list_available_agents(),
            summarizer_backend=backend or "none",
        )
        _telemetry.emit("app.launched")
    except Exception:
        pass


@app.get("/config/retention")
async def get_retention():
    """Per-agent transcript-retention info + TT archive opt-ins + storage usage.

    Drives the Settings "Agent history & retention" section: shows each present
    agent's default cleanup window (and the user's real override where we can
    read it), whether TT can archive it, the opt-in state, and how much space
    the durable store is using per tier."""
    import agent_retention
    import history_store
    agents = _list_available_agents()
    return {
        "agents": agent_retention.describe_agents(agents),
        "storage": history_store.storage_stats(),
        "coverage": history_store.coverage(),
    }


@app.post("/config/retention")
async def post_retention(payload: dict = Body(...)):
    """Toggle whether TT keeps full transcripts for an agent past its own
    pruning. Body: {"agent": str, "enabled": bool}."""
    from fastapi import HTTPException
    import agent_retention
    agent = payload.get("agent")
    enabled = payload.get("enabled")
    if not isinstance(agent, str) or not agent:
        raise HTTPException(status_code=400, detail="'agent' is required")
    if not isinstance(enabled, bool):
        raise HTTPException(status_code=400, detail="'enabled' must be a boolean")
    flags = agent_retention.set_archive(agent, enabled)
    # `tier` is the resulting retention level, so a turn-off is reported as
    # "rollup" rather than going unrecorded. Only the tier rides along -- never
    # which agent, and never any count.
    _telemetry.emit("retention.opted_in", {"tier": "full" if enabled else "rollup"})
    return {"ok": True, "archive": flags}


@app.delete("/history/transcripts")
async def delete_history_transcripts(agent: Optional[str] = None,
                                     older_than_days: Optional[int] = None):
    """Purge archived (tier-2) transcript blobs to reclaim space. The core
    rollup and any generated summaries are left intact, so analytics history is
    preserved — only the heavy full-transcript copies are removed."""
    import history_store
    deleted = history_store.delete_transcripts(agent=agent, older_than_days=older_than_days)
    return {"ok": True, "deleted": deleted, "storage": history_store.storage_stats()}


@app.get("/config/power")
async def get_power_config():
    """Power & subscription cost config for local/subscription models.

    `configured` tells the UI whether a power.json exists yet — when false the
    returned values are the shipped defaults and the local-model electricity
    branch is inactive until the user saves. `deviceDefault` is the chip-aware
    wattage detected for this machine (e.g. Apple M5 → 22 W); it's the baseline
    `loadWatts` falls back to when the user hasn't set one, so the UI can show
    "default for your machine" instead of a generic number.
    """
    from power_config import load_power_config, has_user_config, device_default
    cfg = load_power_config()
    return {**cfg, "configured": has_user_config(), "deviceDefault": device_default()}


@app.put("/config/power")
async def put_power_config(payload: dict = Body(...)):
    """Persist power config. Body: {loadWatts?, costPerKwh?, subscriptionEndpoints?, subscriptionModels?}.

    Validation happens in power_config.save_power_config (bad values are skipped,
    never surfaced as raw errors). Returns the full saved config.
    """
    from fastapi import HTTPException
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="body must be a JSON object")
    from power_config import save_power_config
    try:
        cfg = save_power_config(payload)
    except OSError:
        # Disk/permissions issue — keep it human, no stack traces.
        raise HTTPException(status_code=500, detail="Could not save power config to disk.")
    _invalidate_sessions_cache()
    return {**cfg, "configured": True}


@app.get("/config/power/meter")
async def get_power_meter():
    """What real power measurement is possible here, plus a live reading if any.

    `capability` explains the platform situation to the UI (e.g. Apple Silicon on
    AC needs admin). `reading` is a real watts value when a root-free source
    exists (nvidia-smi / on-battery macOS), else null.
    """
    from power_meter import capability, read_power_watts
    return {"capability": capability(), "reading": read_power_watts()}


@app.post("/config/power/calibrate")
async def calibrate_power():
    """Sample real power for a few seconds and return it as a SUGGESTION.

    Does NOT persist — the UI fills the loadWatts field with the value for the
    user to review and Save. When no root-free *measurement* is available (e.g.
    Apple Silicon on AC) we fall back to a chip-aware *estimate* so the field
    still gets a sensible starting value: `{measured: null, estimated: <watts>,
    source, detail, reason}`. When nothing is derivable, `estimated` is null too.
    """
    from power_meter import sample_average_watts, capability, estimated_watts
    sample = sample_average_watts(duration_s=4.0, interval_s=1.0)
    if not sample:
        est = estimated_watts()
        return {
            "measured": None,
            "estimated": est["watts"] if est else None,
            "source": est["source"] if est else None,
            "detail": est.get("detail") if est else None,
            "reason": capability().get("reason"),
        }
    return {
        "measured": sample["watts"], "source": sample["source"],
        "samples": sample.get("samples"),
    }


@app.get("/config/billing")
async def get_billing_config():
    """Per-agent billing mode (how to frame the cost figure for each agent).

    Returns one entry per *detected* agent with its resolved `mode`
    (subscription | api | local | unknown), the `source` of that value
    (user | detected | default), the raw auto-`detected` value (or null), the
    static `default`, and a human `detect_source` note. The cost math is
    unchanged by this — it only drives the UI's label/disclaimer.
    """
    from billing_mode import get_all, MODES
    agents = _list_available_agents()
    return {"agents": get_all(agents), "modes": list(MODES)}


@app.put("/config/billing")
async def put_billing_config(payload: dict = Body(...)):
    """Set or clear one agent's billing-mode override.

    Body: {"agent": "<agent>", "mode": "<mode>" | null}. A null/absent mode
    clears the override and reverts the agent to auto-detection. Invalid input is
    rejected with a plain message (no raw errors).
    """
    from fastapi import HTTPException
    from billing_mode import save_override, get_all, MODES
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="body must be a JSON object")
    agent = payload.get("agent")
    if not isinstance(agent, str) or not agent.strip():
        raise HTTPException(status_code=400, detail="'agent' is required")
    mode = payload.get("mode")
    if mode is not None and mode not in MODES:
        raise HTTPException(status_code=400, detail=f"'mode' must be one of {list(MODES)} or null")
    try:
        save_override(agent.strip(), mode)
    except OSError:
        raise HTTPException(status_code=500, detail="Could not save billing config to disk.")
    _invalidate_sessions_cache()
    return {"agents": get_all(_list_available_agents()), "modes": list(MODES)}


# Feature/experimental flags each agent persists in its own local config. There
# is no shared "experimental mode" across harnesses — each exposes it
# differently (or server-side, or not at all), so we read only the agents with a
# clean, secret-free local signal and surface an allowlist of scalar flags. This
# is read-only and informational; TokenTelemetry never writes these back.
def _scalar(v: Any) -> bool:
    return isinstance(v, (bool, int, float, str)) and not isinstance(v, bytes)


def _agent_feature_flags() -> List[Dict[str, Any]]:
    """Per-agent experimental/feature flags, read from each agent's own config.

    Best-effort and read-only: a missing/corrupt config is simply omitted, never
    raised. Only allowlisted, scalar, non-secret keys are surfaced (no auth
    tokens, no whole-file dumps). Bool flags carry kind="bool" so the UI can show
    an on/off pill; everything else is kind="value".
    """
    out: List[Dict[str, Any]] = []

    def _flag(name: str, value: Any) -> Dict[str, Any]:
        return {"name": name, "value": value,
                "kind": "bool" if isinstance(value, bool) else "value"}

    # Copilot — ~/.copilot/settings.json: a single `experimental` boolean that
    # gates preview features incl. the /every, /loop and /after scheduled prompts.
    cp = HOME / ".copilot" / "settings.json"
    if cp.exists():
        try:
            d = json.loads(cp.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                flags = [_flag(k, d[k]) for k in ("experimental",) if k in d and _scalar(d[k])]
                out.append({
                    "agent": "copilot", "detected": True,
                    "source": "~/.copilot/settings.json",
                    "flags": flags,
                    "note": "Turns on preview features, including the /every, /loop and /after scheduled prompts.",
                    "how_to_enable": "In the Copilot CLI, run /experimental to toggle it (or start it with --experimental). Copilot restarts to apply.",
                    "enable_command": "/experimental",
                    "docs_url": "https://docs.github.com/en/copilot/how-tos/copilot-cli/automate-copilot-cli/schedule-prompts",
                })
        except Exception:
            pass

    # Codex — ~/.codex/config.toml [features]: per-feature booleans (e.g. js_repl).
    cx = CODEX_DIR / "config.toml"
    if cx.exists():
        try:
            import tomllib
            with open(cx, "rb") as f:
                t = tomllib.load(f)
            feats = t.get("features") if isinstance(t, dict) else None
            if isinstance(feats, dict):
                flags = [_flag(k, v) for k, v in feats.items() if _scalar(v)]
                out.append({
                    "agent": "codex", "detected": True,
                    "source": "~/.codex/config.toml  [features]",
                    "flags": flags,
                    "note": "Experimental Codex capabilities, toggled per feature.",
                    "how_to_enable": "Edit ~/.codex/config.toml and set a flag under [features] (e.g. js_repl = true), then restart Codex.",
                    "enable_command": "~/.codex/config.toml  →  [features]",
                    "docs_url": "https://learn.chatgpt.com/docs/config-file/config-reference",
                })
        except Exception:
            pass

    # Claude Code — ~/.claude/settings.json: no single experimental switch, so we
    # surface an allowlist of its individual feature toggles.
    CLAUDE_KEYS = ("enableWorkflows", "effortLevel", "editorMode",
                   "voiceEnabled", "agentPushNotifEnabled")
    cl = CLAUDE_DIR / "settings.json"
    if cl.exists():
        try:
            d = json.loads(cl.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                flags = [_flag(k, d[k]) for k in CLAUDE_KEYS if k in d and _scalar(d[k])]
                if flags:
                    out.append({
                        "agent": "claude", "detected": True,
                        "source": "~/.claude/settings.json",
                        "flags": flags,
                        "note": "Claude Code has no single experimental switch; these are its individual feature toggles.",
                        "how_to_enable": "In Claude Code run /config (or /config <key>=<value> on v2.1.181+), or edit ~/.claude/settings.json.",
                        "enable_command": "/config",
                        "docs_url": "https://code.claude.com/docs/en/settings",
                    })
        except Exception:
            pass

    return out


# Agents that DO have experimental/preview features but store the toggle
# somewhere TokenTelemetry can't honestly read (an opaque local state store or
# server-side), so we name them explicitly rather than silently omitting them —
# absence would otherwise read as "we forgot", not "not exposed locally".
_FEATURES_NOT_DETECTABLE = [
    {"agent": "antigravity",
     "reason": "Its Scheduled Tasks and preview features live in an opaque local state store (state.vscdb) / server-side, not a readable flag."},
    {"agent": "cursor",
     "reason": "Automations and preview features are gated in Cursor's cloud / opaque store, with no local flag."},
]


@app.get("/config/agent-features")
async def get_agent_features():
    """Experimental/feature flags each agent stores in its own local config.

    `agents` are the ones with a clean, locally-readable signal (Copilot, Codex,
    Claude Code). `not_detectable` names agents that HAVE such features but gate
    them where we can't honestly read them (Antigravity, Cursor). Any other agent
    simply has no experimental/feature-flag concept in local config. An absent or
    not_detectable agent means "not exposed locally", never "off". Read-only.
    """
    detected = _agent_feature_flags()
    present = {a["agent"] for a in detected}
    not_detectable = [x for x in _FEATURES_NOT_DETECTABLE if x["agent"] not in present]
    return {"agents": detected, "not_detectable": not_detectable}


@app.get("/config/billing-route")
async def get_billing_route_config():
    """Drain-priority billing routes per agent: which credit *bucket* pays, and
    in what order, split by task type (interactive vs programmatic).

    For each detected agent this returns the full ordered bucket list plus the
    resolved `routes.{interactive,programmatic}` (active bucket, marginal-cost
    flag, and whether the active bucket is a capped pool to warn on). The agent's
    resolved billing `mode` is threaded in so a user-marked `local` agent routes
    to the electricity bucket, and each agent's persisted *plan* (set via PUT)
    sizes its pools — plan vocabularies are per-provider, so there is no global
    plan knob. Date-gated policies (Anthropic's June-15 SDK split) flip on the
    real clock. This drives the Settings drain-order view; it does not change
    cost math on its own. `as_of` is when the provider snapshot was last
    verified — the UI shows it as a staleness disclaimer.
    """
    from billing_mode import get_all
    from billing_route import (
        get_route_overview, load_plans, TASK_TYPES, CHARGES,
        DEFAULT_PLAN, SNAPSHOT_AS_OF,
    )
    agents = _list_available_agents()
    modes = get_all(agents)
    plans = load_plans()
    overview = {
        a: get_route_overview(
            a,
            plan=plans.get(a, DEFAULT_PLAN),
            mode=modes.get(a, {}).get("mode"),
        )
        for a in agents
    }
    return {
        "agents": overview,
        "task_types": list(TASK_TYPES),
        "charges": list(CHARGES),
        "as_of": SNAPSHOT_AS_OF,
    }


@app.put("/config/billing-route")
async def put_billing_route_config(payload: dict = Body(...)):
    """Set or clear one agent's plan tier (sizes its credit pools).

    Body: {"agent": "<agent>", "plan": "<plan>" | null}. A null/absent plan
    clears the choice and reverts the agent to its provider's default tier.
    Plans are validated against that agent's own vocabulary (e.g. "max5x" is
    Anthropic-only). Invalid input is rejected with a plain message.
    """
    from fastapi import HTTPException
    from billing_route import save_plan, AGENT_PLANS
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="body must be a JSON object")
    agent = payload.get("agent")
    if not isinstance(agent, str) or not agent.strip():
        raise HTTPException(status_code=400, detail="'agent' is required")
    agent = agent.strip()
    plan = payload.get("plan")
    valid = AGENT_PLANS.get(agent, ())
    if plan is not None and plan not in valid:
        raise HTTPException(
            status_code=400,
            detail=f"'plan' for {agent} must be one of {list(valid)} or null",
        )
    try:
        save_plan(agent, plan)
    except OSError:
        raise HTTPException(status_code=500, detail="Could not save plan to disk.")
    return await get_billing_route_config()


@app.get("/config/aliases")
async def get_aliases():
    return list_aliases()


@app.post("/config/aliases")
async def post_aliases(aliases: Dict[str, str]):
    # One-way, no chains, no self-reference. Reject invalid payloads.
    cleaned: Dict[str, str] = {}
    for k, v in aliases.items():
        if not isinstance(k, str) or not isinstance(v, str): continue
        if not k or not v or k == v: continue
        if v in aliases: continue  # chain
        cleaned[k] = v
    save_aliases(cleaned)
    _invalidate_sessions_cache()
    return {"ok": True, "aliases": cleaned}


# ---------------------------------------------------------------------------
# Budgets (observational — see harness_config for the storage model)
#
# A budget is evaluated by windowing the parsed sessions to the budget's
# period, filtering by the budget's filter object, and summing cost (usd) or
# total tokens. We reuse get_sessions_cached() — no log re-read. All windowing
# is in LOCAL time so "this month" matches the by_day analytics buckets.
# ---------------------------------------------------------------------------

def _budget_window(period: str, now_local: datetime):
    """Return (start, reset_at) as local-tz datetimes. reset_at is None for
    rolling windows (they have no fixed reset)."""
    from datetime import timedelta
    if period == "weekly":
        start = (now_local - timedelta(days=now_local.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=7)
    if period == "rolling_30d":
        return now_local - timedelta(days=30), None
    # monthly (default)
    start = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        reset = start.replace(year=start.year + 1, month=1)
    else:
        reset = start.replace(month=start.month + 1)
    return start, reset


def _session_matches_filters(s: Dict[str, Any], filters: Dict[str, str]) -> bool:
    """A session matches iff every present filter key equals the session's value.
    Empty filters ({}) match everything (global budget)."""
    if "project" in filters and \
            canonical_project(s.get("project")) != canonical_project(filters["project"]):
        # Canonical on both sides: budgets saved before project paths were
        # canonicalised may use another separator style than sessions do now.
        return False
    if "agent" in filters and s.get("agent") != filters["agent"]:
        return False
    if "model" in filters and (s.get("model") or "") != filters["model"]:
        return False
    # Hermes profile scope. Sessions from the default home carry no
    # hermes_profile key, so "default" matches them explicitly.
    if "hermes_profile" in filters and \
            (s.get("hermes_profile") or "default") != filters["hermes_profile"]:
        return False
    return True


def _compute_budget_status(budget: Dict[str, Any], sessions: List[Dict[str, Any]],
                           now_local: datetime) -> Dict[str, Any]:
    start, reset = _budget_window(budget["period"], now_local)
    filters = budget.get("filters") or {}
    limit_type = budget["limit_type"]
    limit_value = budget["limit_value"]

    used = 0.0
    sessions_in_window = 0
    per_agent: Dict[str, Dict[str, float]] = {}
    for s in sessions:
        ts = s.get("timestamp")
        if ts is None:
            continue
        try:
            ts_local = ts.astimezone()
        except Exception:
            continue
        if ts_local < start:
            continue
        if not _session_matches_filters(s, filters):
            continue
        cost = float(s.get("cost", 0.0) or 0.0)
        toks = int((s.get("tokens") or {}).get("total", 0) or 0)
        used += cost if limit_type == "usd" else toks
        sessions_in_window += 1
        a = s.get("agent", "unknown")
        bucket = per_agent.setdefault(a, {"cost": 0.0, "tokens": 0.0})
        bucket["cost"] += cost
        bucket["tokens"] += toks

    fraction = (used / limit_value) if limit_value > 0 else 0.0
    # Highest crossed threshold (sorted ascending in storage).
    alert_level = None
    for t in budget.get("thresholds", []):
        if fraction >= t:
            alert_level = t

    # Stable period bucket for notification de-duplication. Calendar periods key
    # off their (fixed) boundary date; rolling_30d has no natural boundary, so we
    # bucket by *today* — a rolling alert re-fires at most once per day.
    if budget["period"] == "rolling_30d":
        period_key = now_local.strftime("%Y-%m-%d")
    else:
        period_key = start.strftime("%Y-%m-%d")

    return {
        **budget,
        "used": round(used, 6) if limit_type == "usd" else int(used),
        "fraction": round(fraction, 4),
        "alert_level": alert_level,
        "sessions_in_window": sessions_in_window,
        "window_start": start.isoformat(),
        "period_key": period_key,
        "reset_at": reset.isoformat() if reset else None,
        "breakdown_by_agent": {
            a: {"cost": round(v["cost"], 6), "tokens": int(v["tokens"])}
            for a, v in sorted(per_agent.items(), key=lambda kv: kv[1]["cost"], reverse=True)
        },
    }


async def _budget_statuses() -> List[Dict[str, Any]]:
    budgets = load_budgets()
    if not budgets:
        return []
    sessions = await get_sessions_cached()
    now_local = datetime.now(timezone.utc).astimezone()
    statuses = [_compute_budget_status(b, sessions, now_local) for b in budgets]
    _emit_budget_notifications(statuses)
    return statuses


def _scope_label(filters: Dict[str, str]) -> str:
    """Human label for a budget scope, e.g. 'Claude · my-app' or 'my-app'."""
    proj = filters.get("project", "").rstrip("/").split("/")[-1] if filters.get("project") else None
    agent = filters.get("agent")
    if agent and proj:
        return f"{agent} · {proj}"
    return agent or proj or "Global"


def _fmt_usd(v: float) -> str:
    """Format a dollar amount: cents under $1, whole dollars at/above (with
    thousands separators). Keeps small budgets like $0.50 from showing as $0."""
    if abs(v) < 1:
        return f"${v:.2f}"
    return f"${v:,.0f}"


def _emit_budget_notifications(statuses: List[Dict[str, Any]]) -> None:
    """For every budget that has crossed a threshold, record a notification.

    Idempotent: notif.emit() de-dupes on a stable key combining the budget id,
    the current period window, and the crossed threshold — so each real
    threshold-crossing produces exactly one notification per period.
    """
    for s in statuses:
        level = s.get("alert_level")
        if level is None:
            continue
        filters = s.get("filters") or {}
        scope = _scope_label(filters)
        pct = round(s.get("fraction", 0) * 100)
        over = s.get("fraction", 0) >= 1
        if s.get("limit_type") == "usd":
            # Sub-dollar limits/spend need cents; otherwise whole dollars read cleaner.
            used_s = _fmt_usd(s["used"])
            limit_s = _fmt_usd(s["limit_value"])
        else:
            used_s = f"{int(s['used']):,} tok"
            limit_s = f"{int(s['limit_value']):,} tok"
        href = (
            f"/projects/{quote(filters['project'], safe='')}/insights"
            if filters.get("project") else "/analytics"
        )
        notif.emit(
            kind="budget_alert",
            dedup_key=f"budget:{s['id']}:{s.get('period_key')}:{level}",
            title=f"Budget {'exceeded' if over else 'alert'}: {scope}",
            severity="over" if over else "warn",
            body=f"{used_s} / {limit_s} ({pct}%)",
            href=href,
        )


@app.get("/budgets")
async def get_budgets():
    """Return every budget with its current usage, fraction, and alert level."""
    return {"budgets": await _budget_statuses()}


# ---------------------------------------------------------------------------
# Notification center (see notifications.py for the storage model)
# ---------------------------------------------------------------------------

def _notif_ids(payload: Any) -> Optional[List[int]]:
    """Extract an optional id list from a request body. Missing/empty -> None
    (meaning 'apply to all'), so POST {} acts on everything."""
    if isinstance(payload, dict):
        ids = payload.get("ids")
        if isinstance(ids, list) and ids:
            try:
                return [int(i) for i in ids]
            except (TypeError, ValueError):
                return None
    return None


@app.get("/notifications")
async def get_notifications():
    """Live (non-cleared) notifications, newest first, plus unread_count and
    the to_toast subset the frontend surfaces once."""
    # Refresh budget-derived notifications before reading the store.
    await _budget_statuses()
    return notif.list_live()


@app.post("/notifications/toasted")
async def post_notifications_toasted(payload: Any = Body(default=None)):
    return {"ok": True, "updated": notif.mark_toasted(_notif_ids(payload))}


@app.post("/notifications/read")
async def post_notifications_read(payload: Any = Body(default=None)):
    return {"ok": True, "updated": notif.mark_read(_notif_ids(payload))}


@app.post("/notifications/clear")
async def post_notifications_clear(payload: Any = Body(default=None)):
    return {"ok": True, "updated": notif.clear(_notif_ids(payload))}


@app.put("/budgets")
async def put_budgets(payload: Any = Body(...)):
    """Replace the full budget set. Accepts {"budgets": [...]} or a bare list.
    Validation/sanitisation happens in harness_config.save_budgets."""
    items = payload.get("budgets") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        items = []
    save_budgets(items)
    # No session-cache invalidation needed: budgets don't change parsed sessions.
    return {"ok": True, "budgets": await _budget_statuses()}


# def _quality_summary(edit_turns: int, retry_turns: int, measured_sessions: int) -> Dict[str, Any]:
#     if edit_turns > 0:
#         retry_rate = retry_turns / edit_turns
#         one_shot_rate = 1.0 - retry_rate
#     else:
#         retry_rate = None
#         one_shot_rate = None
#     return {
#         "edit_turns": edit_turns,
#         "retry_turns": retry_turns,
#         "one_shot_rate": one_shot_rate,
#         "retry_rate": retry_rate,
#         "measured_sessions": measured_sessions,
#     }


def _cache_hit_pct(input_tokens: int, cached_tokens: int) -> Optional[float]:
    """Return cache hit ratio as 0-100, matching the Hermes overlay's scale.

    `cached_tokens` must be the CUMULATIVE cache-read sum across turns
    (`_cached_sum` for Claude-style scanners), never the per-session
    high-water-mark `cached` field — HWM/(cumulative input) understates the
    rate more the longer the session runs.
    """
    denom = input_tokens + cached_tokens
    if denom <= 0:
        return None
    return round((cached_tokens / denom) * 100, 1)


def _bucket_key(ts: datetime, granularity: str) -> str:
    """Local-time bucket label for a session timestamp. ``day`` keeps the
    existing %Y-%m-%d key; ``week`` collapses to that week's ISO Monday; ``month``
    to the first of the month. Always local, matching the original day bucket."""
    d = ts.astimezone()
    if granularity == "week":
        monday = d - timedelta(days=d.weekday())
        return monday.strftime("%Y-%m-%d")
    if granularity == "month":
        return d.strftime("%Y-%m-01")
    return d.strftime("%Y-%m-%d")


def _date_bound(value: Optional[str], *, end: bool) -> Optional[str]:
    """Turn a 'YYYY-MM-DD' (or full ISO) filter value into a UTC-ISO bound that
    compares correctly against the store's UTC ``last_ts``. A bare date becomes
    local start-of-day (``end=False``) or end-of-day (``end=True``)."""
    if not value:
        return None
    v = value.strip()
    try:
        if "T" in v:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        else:
            d = datetime.fromisoformat(v).date()
            t = _dtime(23, 59, 59, 999999) if end else _dtime(0, 0, 0, 0)
            dt = datetime.combine(d, t)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.astimezone()  # interpret bare value in local time
    return dt.astimezone(timezone.utc).isoformat()


def _session_in_filters(s: Dict[str, Any], from_b: Optional[str], to_b: Optional[str],
                        agents: List[str], models: List[str], projects: List[str]) -> bool:
    """Apply the same window + allow-list filters to a live session dict that the
    store applies in SQL, so merged live rows respect the selected view."""
    if agents and s.get("agent") not in agents:
        return False
    if models and s.get("model") not in models:
        return False
    if projects and s.get("project") not in projects:
        return False
    ts = s.get("timestamp")
    if isinstance(ts, datetime) and (from_b or to_b):
        iso = ts.astimezone(timezone.utc).isoformat()
        if from_b and iso < from_b:
            return False
        if to_b and iso > to_b:
            return False
    return True


@app.get("/analytics")
async def get_analytics(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    granularity: str = Query("day"),
    agents: List[str] = Query(default=[]),
    models: List[str] = Query(default=[]),
    projects: List[str] = Query(default=[]),
):
    import history_store
    from power_config import (
        is_local_session, load_power_config, default_tok_per_sec_for_model, co2_for_session,
    )
    from insights import energy_wh, cloud_equiv_cost, savings_vs_cloud
    pc = load_power_config()
    load_watts = pc.get("loadWatts", 80)
    ref_model = pc.get("referenceCloudModel", "claude-sonnet-4-6")
    if granularity not in ("day", "week", "month"):
        granularity = "day"

    # Build the working set from the durable store (full history, filtered in
    # SQL) merged with the live scan (freshest in-flight sessions). The live
    # scan only matters for a window that reaches today, so a purely-historical
    # query is served entirely from SQLite — no file scan.
    from_b = _date_bound(from_, end=False)
    to_b = _date_bound(to, end=True)
    stored = history_store.query(from_b, to_b, agents, models, projects)
    merged: Dict[tuple, Dict[str, Any]] = {(s["agent"], s["id"]): s for s in stored}
    today_local = datetime.now().astimezone().strftime("%Y-%m-%d")
    window_includes_today = (to_b is None) or (to is None) or (to >= today_local)
    if window_includes_today:
        for s in await get_sessions_cached():
            if _session_in_filters(s, from_b, to_b, agents, models, projects):
                merged[(s.get("agent"), s.get("id"))] = s  # live wins over stored
    sessions = list(merged.values())
    by_agent = {}; by_day = {}; by_model = {}
    for s in sessions:
        agent = s["agent"]
        if agent not in by_agent:
            by_agent[agent] = {"input": 0, "output": 0, "cached": 0, "cache_reads": 0, "total": 0, "cost": 0.0,
                               "energy_wh": 0.0, "savings_usd": 0.0, "co2_g": 0.0, "session_count": 0}
        st = s.get("tokens", {})
        # None for an unpriced session; feeds three aggregates plus
        # savings_vs_cloud() below, all of which need a number.
        scost = s.get("cost") or 0.0
        # Local insights — energy, cloud savings, CO2 — only for local sessions.
        energy = savings = co2 = 0.0
        if is_local_session(model_name=s.get("model"), endpoint=s.get("endpoint"),
                            provider=s.get("provider"), billing_mode=s.get("billing_mode"), config=pc):
            tps = s.get("tok_per_sec")
            if not tps or tps <= 0:
                tps = default_tok_per_sec_for_model(s.get("model"))
            energy = energy_wh(st.get("output", 0), load_watts=load_watts, tok_per_sec=tps)
            cloud_cost = cloud_equiv_cost(ref_model, st.get("input", 0), st.get("output", 0), st.get("cached", 0))
            savings = savings_vs_cloud(scost, cloud_cost)
            co2 = co2_for_session(st.get("output", 0), config=pc, tok_per_sec=tps)
        for k in ["input", "output", "cached", "total"]: by_agent[agent][k] += st.get(k, 0)
        # Cumulative cache reads for the hit-rate metric. Claude-style scanners
        # keep `cached` as a per-session high-water mark (unique prefix size) and
        # the per-turn read sum in `_cached_sum`; mixing the HWM with cumulative
        # `input` badly understates the hit rate on long sessions. Agents without
        # `_cached_sum` fall back to `cached` (prior behavior).
        by_agent[agent]["cache_reads"] += st.get("_cached_sum") or st.get("cached", 0) or 0
        by_agent[agent]["cost"] += scost
        by_agent[agent]["energy_wh"] += energy
        by_agent[agent]["savings_usd"] += savings
        by_agent[agent]["co2_g"] += co2
        by_agent[agent]["session_count"] += 1
        model_name = s.get("model") or f"{agent} (unknown)"
        if model_name not in by_model:
            by_model[model_name] = {"input": 0, "output": 0, "cached": 0, "total": 0, "cost": 0.0,
                                    "energy_wh": 0.0, "savings_usd": 0.0, "co2_g": 0.0,
                                    "session_count": 0, "agent": agent}
        for k in ["input", "output", "cached", "total"]: by_model[model_name][k] += st.get(k, 0)
        by_model[model_name]["cost"] += scost
        by_model[model_name]["energy_wh"] += energy
        by_model[model_name]["savings_usd"] += savings
        by_model[model_name]["co2_g"] += co2
        by_model[model_name]["session_count"] += 1
        # Bucket by LOCAL day, not UTC.
        day = _bucket_key(s["timestamp"], granularity)
        if day not in by_day:
            by_day[day] = {"total": 0, "input": 0, "output": 0, "cached": 0, "cost": 0.0,
                           "energy_wh": 0.0, "savings_usd": 0.0, "co2_g": 0.0}
        for k in ["input", "output", "cached", "total"]: by_day[day][k] += st.get(k, 0)
        by_day[day]["cost"] += scost
        by_day[day]["energy_wh"] += energy
        by_day[day]["savings_usd"] += savings
        by_day[day]["co2_g"] += co2
    for agent, row in by_agent.items():
        row["cache_hit_pct"] = _cache_hit_pct(row["input"], row["cache_reads"])
        # agg = quality_by_agent.get(agent)
        # if agg:
        #     row["quality"] = _quality_summary(agg["edit_turns"], agg["retry_turns"], agg["measured_sessions"])
        # else:
        #     row["quality"] = _quality_summary(0, 0, 0)
    sorted_days = sorted([{"date": d, **v} for d, v in by_day.items()], key=lambda x: x["date"])
    total_input = sum(a["input"] for a in by_agent.values())
    total_output = sum(a["output"] for a in by_agent.values())
    total_cached = sum(a["cached"] for a in by_agent.values())
    total_cache_reads = sum(a["cache_reads"] for a in by_agent.values())

    # Ecosystem usage: skills, MCP servers, subagent types. New keys only — the
    # existing by_agent/by_day/by_model/total stay byte-identical (no silent
    # historical changes). Delegated usage is exposed as its OWN bucket, never
    # folded into the per-agent sums: claude subagent transcripts aren't
    # sessions (counted nowhere else), while opencode/hermes children already
    # appear as sessions above — adding parent-side sums would double-count.
    by_skill: Dict[str, Dict[str, Any]] = {}
    by_mcp_server: Dict[str, Dict[str, Any]] = {}
    by_subagent_type: Dict[str, Dict[str, Any]] = {}
    # delegated_*: usage that exists NOWHERE else (claude subagent transcripts).
    # linked_child_*: child sessions spawned by a parent — their tokens are
    # already in by_agent/by_day/total above; surfaced here as an attribution
    # view, never added on top.
    delegation_totals: Dict[str, Any] = {
        "delegated_tokens": 0, "delegated_cost": 0.0,
        "sessions_with_spawns": 0,
        "linked_children": 0, "linked_child_tokens": 0, "linked_child_cost": 0.0,
        "by_agent": {},
    }
    # Recurring loops (/loop): attribution-only view. A loop session is already
    # an ordinary session in by_agent/by_day/total, so loop_tokens/loop_cost are
    # a VIEW, never re-summed into totals (same discipline as linked_child_*).
    by_loop: Dict[str, Dict[str, Any]] = {}
    loops: Dict[str, Any] = {
        "total_loops": 0, "active_loops": 0, "expired_loops": 0, "cancelled_loops": 0,
        "loop_sessions": 0, "total_iterations": 0, "loop_tokens": 0, "loop_cost": 0.0,
    }

    # Child sessions are looked up per (agent, id) so grok by_type rows can
    # attribute each child's tokens to its subagent type.
    sess_by_key = {(s.get("agent"), s.get("id")): s for s in sessions}

    def _subagent_row(t: str) -> Dict[str, Any]:
        return by_subagent_type.setdefault(t, {
            "spawns": 0, "tokens": 0, "cost": 0.0, "session_count": 0,
            "tokens_recorded": False, "agents": []})

    def _deleg_agent_row(agent: str) -> Dict[str, Any]:
        return delegation_totals["by_agent"].setdefault(agent, {
            "parents": 0, "spawns": 0, "children": 0,
            "child_tokens": 0, "child_cost": 0.0,
            "delegated_tokens": 0, "delegated_cost": 0.0})

    for s in sessions:
        agent = s.get("agent")
        lp = s.get("loop")
        if isinstance(lp, dict) and lp.get("is_loop"):
            st = lp.get("state")
            loops["total_loops"] += 1
            loops["loop_sessions"] += 1
            if st == "active": loops["active_loops"] += 1
            elif st == "expired": loops["expired_loops"] += 1
            elif st == "cancelled": loops["cancelled_loops"] += 1
            loops["total_iterations"] += lp.get("iterations", 0) or 0
            # Footprint = the loop's OWN fire-response turns, not the whole session.
            tok = lp.get("footprint_tokens", 0) or 0
            cost = lp.get("footprint_cost", 0) or 0
            session_tok = (s.get("tokens") or {}).get("total", 0) or 0
            loops["loop_tokens"] += tok
            loops["loop_cost"] = round(loops["loop_cost"] + cost, 6)
            key = lp.get("job_id") or s.get("id")
            by_loop[key] = {
                "label": lp.get("prompt_preview") or "(loop)",
                "mode": lp.get("mode"), "cadence": lp.get("cadence"),
                "state": st, "expired_reason": lp.get("expired_reason"),
                "iterations": lp.get("iterations", 0) or 0,
                "tokens": tok, "cost": cost,
                "session_tokens": session_tok, "session_cost": s.get("cost") or 0,
                "agent": agent, "session_id": s.get("id"),
                "job_id": lp.get("job_id"), "last_fired": lp.get("last_fired"),
                "expires_at": lp.get("expires_at"),
                "next_fire_at": lp.get("next_fire_at"),
            }
        for sk in s.get("skills_used") or []:
            row = by_skill.setdefault(sk["name"], {"invocations": 0, "session_count": 0, "agents": []})
            row["invocations"] += sk["count"]
            row["session_count"] += 1
            if agent not in row["agents"]:
                row["agents"].append(agent)
        for server, tools in (s.get("mcp_usage") or {}).items():
            row = by_mcp_server.setdefault(server, {"calls": 0, "tools": {}, "session_count": 0, "agents": []})
            row["session_count"] += 1
            if agent not in row["agents"]:
                row["agents"].append(agent)
            for tool, n in tools.items():
                row["calls"] += n
                row["tools"][tool] = row["tools"].get(tool, 0) + n

        deleg = s.get("delegation") or {}
        spawns_here = deleg.get("spawn_count") or deleg.get("linked_children") or 0
        if spawns_here:
            delegation_totals["sessions_with_spawns"] += 1
            arow = _deleg_agent_row(agent)
            arow["parents"] += 1
            arow["spawns"] += spawns_here
        for t, d in (deleg.get("by_type") or {}).items():
            row = _subagent_row(t)
            row["spawns"] += d.get("count", 0)
            row["session_count"] += 1
            if agent not in row["agents"]:
                row["agents"].append(agent)
            # claude: per-type totals come straight from subagent transcripts.
            if d.get("total") or d.get("cost"):
                row["tokens"] += d.get("total", 0)
                row["cost"] = round(row["cost"] + (d.get("cost") or 0), 6)
                row["tokens_recorded"] = True
            # grok: attribute each child SESSION's tokens to the spawning type.
            for cid in d.get("child_session_ids") or []:
                child = sess_by_key.get((agent, cid))
                if child is None:
                    continue
                row["tokens"] += (child.get("tokens") or {}).get("total", 0)
                row["cost"] = round(row["cost"] + (child.get("cost") or 0), 6)
                row["tokens_recorded"] = True
        # codex children carry their role; attribute the child session directly.
        si = s.get("subagent_info")
        if s.get("parent_session_id") and isinstance(si, dict) and si.get("role"):
            row = _subagent_row(si["role"])
            row["spawns"] += 1
            if agent not in row["agents"]:
                row["agents"].append(agent)
            row["tokens"] += (s.get("tokens") or {}).get("total", 0)
            row["cost"] = round(row["cost"] + (s.get("cost") or 0), 6)
            row["tokens_recorded"] = True

        if deleg.get("tokens_recorded") and deleg.get("delegated_total"):
            delegation_totals["delegated_tokens"] += deleg["delegated_total"]
            delegation_totals["delegated_cost"] = round(
                delegation_totals["delegated_cost"] + (s.get("delegated_cost") or 0), 6)
            arow = _deleg_agent_row(agent)
            arow["delegated_tokens"] += deleg["delegated_total"]
            arow["delegated_cost"] = round(arow["delegated_cost"] + (s.get("delegated_cost") or 0), 6)
        if s.get("parent_session_id"):
            delegation_totals["linked_children"] += 1
            delegation_totals["linked_child_tokens"] += (s.get("tokens") or {}).get("total", 0)
            delegation_totals["linked_child_cost"] = round(
                delegation_totals["linked_child_cost"] + (s.get("cost") or 0), 6)
            arow = _deleg_agent_row(agent)
            arow["children"] += 1
            arow["child_tokens"] += (s.get("tokens") or {}).get("total", 0)
            arow["child_cost"] = round(arow["child_cost"] + (s.get("cost") or 0), 6)

    return {
        "by_agent": by_agent,
        "by_day": sorted_days,
        "by_model": by_model,
        "by_skill": by_skill,
        "by_mcp_server": by_mcp_server,
        "by_subagent_type": by_subagent_type,
        "by_loop": by_loop,
        "loops": loops,
        "delegation": delegation_totals,
        "total": {
            "input": total_input,
            "output": total_output,
            "cached": total_cached,
            "total": sum(a["total"] for a in by_agent.values()),
            "cost": sum(a["cost"] for a in by_agent.values()),
            "energy_wh": sum(a["energy_wh"] for a in by_agent.values()),
            "savings_usd": sum(a["savings_usd"] for a in by_agent.values()),
            "co2_g": sum(a["co2_g"] for a in by_agent.values()),
            "cache_hit_pct": _cache_hit_pct(total_input, total_cache_reads),
        },
        "coverage": history_store.coverage(),
        "granularity": granularity,
        "pricing_updated": PRICING_UPDATED,
        "pricing_overlay_updated": PRICING_OVERLAY_UPDATED,
    }

def _parse_skill_md(p: Path):
    """Read SKILL.md frontmatter; return {name, description}."""
    try:
        text = p.read_text(errors="ignore")
    except Exception: return None
    
    name = p.parent.name
    description = ""
    
    if text.startswith("---"):
        end = text.find("---", 3)
        if end > 0:
            try:
                frontmatter = yaml.safe_load(text[3:end])
                if isinstance(frontmatter, dict):
                    if frontmatter.get("name"):
                        name = str(frontmatter["name"])
                    if frontmatter.get("description"):
                        description = str(frontmatter["description"])
            except Exception:
                # Fallback to manual line parsing if YAML is slightly malformed
                for line in text[3:end].splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        k = k.strip().lower(); v = v.strip().strip('"').strip("'")
                        if k == "name": name = v
                        elif k == "description": description = v
                        
    return {"name": name, "description": (description or "")[:500]}

def _collect_skills(base: Path, scope: str, agent: str):
    out = []
    # If the base folder itself looks like a skills folder (e.g. skills-cursor), scan it directly
    # otherwise look for a 'skills' subfolder.
    skills_dir = base
    if not (base / "SKILL.md").exists() and (base / "skills").exists():
        skills_dir = base / "skills"
    elif not base.exists():
        return out
        
    for skill_md in skills_dir.glob("*/SKILL.md"):
        s = _parse_skill_md(skill_md)
        if s:
            out.append({**s, "scope": scope, "agent": agent, "source": str(skill_md)})
    
    # Check for deeper nested skills (common in plugin structures)
    for skill_md in skills_dir.glob("*/skills/*/SKILL.md"):
        s = _parse_skill_md(skill_md)
        if s:
            out.append({**s, "scope": scope, "agent": agent, "source": str(skill_md)})
    return out

def _read_json(p: Path):
    try: return json.loads(p.read_text())
    except Exception: return None

def _mcps_from_claude_settings(p: Path, scope: str):
    d = _read_json(p) or {}
    # Claude stores servers in ~/.claude.json (projects) or .mcp.json
    servers = d.get("mcpServers") or d.get("servers") or {}
    return [{"name": n, "scope": scope, "agent": "claude", "command": (v.get("command") if isinstance(v, dict) else None), "type": (v.get("type") if isinstance(v, dict) else None), "source": str(p)} for n, v in servers.items()] if isinstance(servers, dict) else []

def _mcps_from_json(p: Path, scope: str, agent: str):
    d = _read_json(p) or {}
    servers = d.get("mcpServers") or d.get("servers") or {}
    if not isinstance(servers, dict): return []
    out = []
    for n, v in servers.items():
        if isinstance(v, dict):
            out.append({"name": n, "scope": scope, "agent": agent, "command": v.get("command"), "url": v.get("url"), "type": v.get("type"), "source": str(p)})
    return out

def _mcps_from_codex_toml(p: Path, scope: str):
    if not p.exists(): return []
    try: txt = p.read_text()
    except Exception: return []
    out = []
    current = None
    for line in txt.splitlines():
        s = line.strip()
        if s.startswith("[mcp_servers."):
            current = {"name": s[len("[mcp_servers."):].rstrip("]").strip('"'), "scope": scope, "agent": "codex", "source": str(p)}
            out.append(current)
        elif current and "=" in s and not s.startswith("["):
            k, v = s.split("=", 1)
            current[k.strip()] = v.strip().strip('"')
        elif s.startswith("["):
            current = None
    return out

def _collect_subagents(base: Path, scope: str, agent: str):
    """Claude Code subagents: *.md files under agents/ with frontmatter."""
    out = []
    d = base / "agents"
    if not d.exists(): return out
    for md in d.rglob("*.md"):
        try: txt = md.read_text(errors="ignore")
        except Exception: continue
        name = md.stem
        description = ""
        tools = ""
        model = ""
        if txt.startswith("---"):
            end = txt.find("---", 3)
            if end > 0:
                try:
                    fm = yaml.safe_load(txt[3:end])
                    if isinstance(fm, dict):
                        if fm.get("name"): name = str(fm["name"])
                        if fm.get("description"): description = str(fm["description"])
                        if fm.get("tools"): tools = str(fm["tools"])
                        if fm.get("model"): model = str(fm["model"])
                except Exception:
                    for line in txt[3:end].splitlines():
                        if ":" in line:
                            k, v = line.split(":", 1)
                            k = k.strip().lower(); v = v.strip().strip('"').strip("'")
                            if k == "name": name = v
                            elif k == "description": description = v
                            elif k == "tools": tools = v
                            elif k == "model": model = v
        out.append({
            "name": name, "description": description[:300], "tools": tools, "model": model,
            "scope": scope, "agent": agent, "source": str(md),
        })
    return out

def _collect_commands(base: Path, scope: str, agent: str):
    """Slash commands: *.md files under commands/ (Claude) or prompts/ (Codex)."""
    out = []
    for sub in ["commands", "prompts"]:
        d = base / sub
        if not d.exists(): continue
        for md in d.rglob("*.md"):
            try:
                txt = md.read_text(errors="ignore")
            except Exception: continue
            name = md.stem
            description = ""
            if txt.startswith("---"):
                end = txt.find("---", 3)
                if end > 0:
                    try:
                        fm = yaml.safe_load(txt[3:end])
                        if isinstance(fm, dict) and fm.get("description"):
                            description = str(fm["description"])
                    except Exception:
                        for line in txt[3:end].splitlines():
                            if ":" in line:
                                k, v = line.split(":", 1)
                                if k.strip().lower() == "description":
                                    description = v.strip().strip('"').strip("'")
            out.append({"name": name, "description": description[:200], "scope": scope, "agent": agent, "source": str(md)})
    return out

def _memory_preview(p: Path, scope: str, agent: str):
    try: txt = p.read_text(errors="ignore")
    except Exception: return None
    return {"scope": scope, "agent": agent, "path": str(p), "name": p.name, "preview": txt[:2000], "truncated": len(txt) > 2000, "size": len(txt)}

# ---- Plugin/extension collection (v1) ---------------------------------------
# Each harness exposes a "plugin"/"extension" surface in its own way. We
# normalize to: {name, version, description, scope, agent, source, installPath,
# enabled, marketplace, components}. Failures return [] — never raise.

ANTIGRAVITY_EXT_DIR = HOME / ".antigravity" / "extensions"
VSCODE_EXT_DIR = HOME / ".vscode" / "extensions"
GEMINI_EXT_DIR = GEMINI_DIR / "extensions"
QWEN_EXT_DIR = QWEN_DIR / "extensions"
CLAUDE_INSTALLED_PLUGINS = CLAUDE_DIR / "plugins" / "installed_plugins.json"
CODEX_PLUGIN_CACHE = CODEX_DIR / "plugins" / "cache"

# Chat-related contributes keys we consider "Copilot/Antigravity plugin-shaped".
_VSCODE_CHAT_KEYS = (
    "chatParticipants", "languageModelTools", "chatModes", "chatAgents",
    "chatPromptFiles", "chatSkills", "languageModelToolSets",
    "languageModelChatProviders",
)

def _claude_plugin_ref(p: Path) -> Optional[str]:
    """Extract '<plugin>@<marketplace>' from a Claude plugin source path.
    Handles both .../plugins/cache/<mp>/<plugin>/<ver>/... and
    .../plugins/marketplaces/<mp>/plugins/<plugin>/... layouts.
    """
    try:
        parts = p.parts
        i = parts.index("plugins")
        sub = parts[i + 1]
        if sub == "cache" and len(parts) >= i + 4:
            return f"{parts[i + 3]}@{parts[i + 2]}"
        if sub == "marketplaces" and len(parts) >= i + 5 and parts[i + 3] == "plugins":
            return f"{parts[i + 4]}@{parts[i + 2]}"
    except (ValueError, IndexError):
        pass
    return None

def _tag_plugin_refs(items: List[dict], plugins: List[dict]) -> None:
    """Stamp `pluginRef` on any item whose source path is inside a plugin's
    installPath. Longest-prefix match wins. In-place; idempotent (won't clobber
    existing pluginRef set inline by the Claude plugin-bundled loops)."""
    if not plugins or not items:
        return
    paths = sorted(
        ((p["installPath"], f"{p['name']}@{p.get('marketplace') or p.get('agent')}")
         for p in plugins if p.get("installPath")),
        key=lambda kv: -len(kv[0]),
    )
    for it in items:
        if it.get("pluginRef"): continue
        src = it.get("source") or ""
        for ip, ref in paths:
            if ip and src.startswith(ip):
                it["pluginRef"] = ref
                break

def _collect_plugins_vscode_style(ext_dir: Path, scope: str, agent: str, marketplace: str) -> List[dict]:
    """VS Code-fork extensions (Copilot via ~/.vscode/extensions, Antigravity
    via ~/.antigravity/extensions). Filtered to chat-relevant contributions.
    """
    if not ext_dir.exists(): return []
    enabled_set: Optional[Set[str]] = None
    enabled_file = ext_dir / "extensions.json"
    if enabled_file.exists():
        arr = _read_json(enabled_file)
        if isinstance(arr, list):
            enabled_set = set()
            for e in arr:
                if isinstance(e, dict):
                    ident = (e.get("identifier") or {}).get("id")
                    if isinstance(ident, str): enabled_set.add(ident.lower())
    out = []
    try: entries = list(ext_dir.iterdir())
    except Exception: return []
    for d in entries:
        if not d.is_dir(): continue
        pkg = _read_json(d / "package.json")
        if not isinstance(pkg, dict): continue
        c = pkg.get("contributes") or {}
        components = [k for k in _VSCODE_CHAT_KEYS if isinstance(c, dict) and c.get(k)]
        if not components: continue
        publisher = pkg.get("publisher") or ""
        name = pkg.get("name") or d.name
        full = f"{publisher}.{name}" if publisher else name
        out.append({
            "name": full,
            "version": pkg.get("version") or "",
            "description": (pkg.get("description") or "")[:300],
            "scope": scope,
            "agent": agent,
            "source": str(d / "package.json"),
            "installPath": str(d),
            "enabled": (enabled_set is None) or (full.lower() in enabled_set),
            "marketplace": marketplace,
            "components": components,
        })
    return out

def _collect_plugins_gemini_style(ext_root: Path, scope: str, agent: str,
                                  manifest_names=("gemini-extension.json",)) -> List[dict]:
    """Gemini CLI extensions (also covers Qwen Code's extension layout)."""
    if not ext_root.exists(): return []
    enablement: Dict[str, dict] = {}
    enab_file = ext_root / "extension-enablement.json"
    if enab_file.exists():
        d = _read_json(enab_file)
        if isinstance(d, dict): enablement = d
    out = []
    try: entries = list(ext_root.iterdir())
    except Exception: return []
    for ext_dir in entries:
        if not ext_dir.is_dir(): continue
        manifest = next((ext_dir / n for n in manifest_names if (ext_dir / n).exists()), None)
        if not manifest: continue
        d = _read_json(manifest)
        if not isinstance(d, dict): continue
        name = d.get("name") or ext_dir.name
        components = [k for k in ("mcpServers", "contextFileName", "commands", "excludeTools") if d.get(k)]
        ent = enablement.get(name)
        enabled = True
        if isinstance(ent, dict):
            enabled = bool(ent.get("overrides")) or bool(ent.get("enabled", True))
        out.append({
            "name": name,
            "version": d.get("version") or "",
            "description": (d.get("description") or "")[:300],
            "scope": scope,
            "agent": agent,
            "source": str(manifest),
            "installPath": str(ext_dir),
            "enabled": enabled,
            "marketplace": None,
            "components": components,
        })
    return out

def _collect_plugins_claude(scope: str, project: Optional[Path] = None) -> List[dict]:
    """Read Claude's installed_plugins.json registry."""
    if not CLAUDE_INSTALLED_PLUGINS.exists(): return []
    d = _read_json(CLAUDE_INSTALLED_PLUGINS)
    if not isinstance(d, dict): return []
    plugins = d.get("plugins") or {}
    if not isinstance(plugins, dict): return []
    out = []
    for full_name, entries in plugins.items():
        if "@" not in full_name: continue
        plugin_name, marketplace = full_name.split("@", 1)
        if not isinstance(entries, list): continue
        for e in entries:
            if not isinstance(e, dict): continue
            entry_scope = e.get("scope")
            our_scope = "user" if entry_scope == "user" else "project"
            if scope != our_scope: continue
            if our_scope == "project":
                if not project or e.get("projectPath") != str(project): continue
            install_path = e.get("installPath") or ""
            description = ""
            manifest = Path(install_path) / ".claude-plugin" / "plugin.json" if install_path else None
            if manifest and manifest.exists():
                m = _read_json(manifest)
                if isinstance(m, dict):
                    description = (m.get("description") or "")[:300]
            comp = []
            ip = Path(install_path) if install_path else None
            if ip and ip.exists():
                for sub in ("skills", "commands", "agents", "hooks", "mcp", "prompts"):
                    if (ip / sub).exists(): comp.append(sub)
            out.append({
                "name": plugin_name,
                "version": e.get("version") or "",
                "description": description,
                "scope": our_scope,
                "agent": "claude",
                "source": str(CLAUDE_INSTALLED_PLUGINS),
                "installPath": install_path,
                "enabled": True,
                "marketplace": marketplace,
                "components": comp,
            })
    return out

def _collect_plugins_codex(scope: str) -> List[dict]:
    """Codex bundled plugins under ~/.codex/plugins/cache/<mp>/<plugin>/<ver>/.
    No manifest; metadata is path-derived."""
    if scope != "user" or not CODEX_PLUGIN_CACHE.exists(): return []
    out = []
    try: marketplaces = list(CODEX_PLUGIN_CACHE.iterdir())
    except Exception: return []
    for mp in marketplaces:
        if not mp.is_dir(): continue
        try: plugins = list(mp.iterdir())
        except Exception: continue
        for plugin in plugins:
            if not plugin.is_dir(): continue
            try: versions = [v for v in plugin.iterdir() if v.is_dir()]
            except Exception: continue
            if not versions: continue
            ver_dir = sorted(versions, key=lambda v: v.name)[-1]
            out.append({
                "name": plugin.name,
                "version": ver_dir.name,
                "description": "",
                "scope": "user",
                "agent": "codex",
                "source": str(ver_dir),
                "installPath": str(ver_dir),
                "enabled": True,
                "marketplace": mp.name,
                "components": [],
            })
    return out

def _collect_plugins_cursor(scope: str, project: Optional[Path] = None) -> List[dict]:
    return []  # TODO v1.1: Cursor plugin layout still in flux

def _collect_plugins_opencode(scope: str, project: Optional[Path] = None) -> List[dict]:
    return []  # TODO v1.1: OpenCode plugin layout still in flux

def _collect_all_plugins(project: Optional[Path]) -> List[dict]:
    plugins: List[dict] = []
    # User scope
    plugins += _collect_plugins_claude("user")
    plugins += _collect_plugins_codex("user")
    plugins += _collect_plugins_gemini_style(GEMINI_EXT_DIR, "user", "gemini")
    plugins += _collect_plugins_gemini_style(QWEN_EXT_DIR, "user", "qwen",
                                             ("qwen-extension.json", "gemini-extension.json"))
    plugins += _collect_plugins_vscode_style(ANTIGRAVITY_EXT_DIR, "user", "antigravity", "antigravity")
    plugins += _collect_plugins_vscode_style(VSCODE_EXT_DIR, "user", "copilot", "vscode")
    plugins += _collect_plugins_cursor("user")
    plugins += _collect_plugins_opencode("user")
    # Project scope
    if project:
        plugins += _collect_plugins_claude("project", project)
        plugins += _collect_plugins_gemini_style(project / ".gemini" / "extensions", "project", "gemini")
        plugins += _collect_plugins_gemini_style(project / ".qwen" / "extensions", "project", "qwen",
                                                 ("qwen-extension.json", "gemini-extension.json"))
        plugins += _collect_plugins_cursor("project", project)
        plugins += _collect_plugins_opencode("project", project)
    # Dedupe by (name, scope, agent)
    seen: Set[tuple] = set(); deduped = []
    for p in plugins:
        key = (p.get("name"), p.get("scope"), p.get("agent"))
        if key in seen: continue
        seen.add(key); deduped.append(p)
    return deduped

def _project_safe_roots() -> List[Path]:
    """Directories a `?project=` path is allowed to resolve inside.

    Defaults to the user's home (where agents and their per-project config
    live in practice). Power users whose code lives elsewhere (external
    volumes, /opt, …) can extend this via TT_PROJECT_ROOTS — an os-pathsep
    separated list of additional roots.
    """
    roots = [HOME]
    extra = os.environ.get("TT_PROJECT_ROOTS")
    if extra:
        roots += [Path(p).expanduser() for p in extra.split(os.pathsep) if p.strip()]
    return roots


def _project_within_safe_roots(project: str) -> bool:
    """True iff `project` resolves inside an allowed root (#54).

    Resolution collapses symlinks and `..`, so neither `?project=/etc` nor a
    `../../` escape nor a symlink can point the project scope at files outside
    the user's own tree.
    """
    try:
        resolved = Path(project).resolve()
    except (OSError, RuntimeError):
        return False
    return any(resolved.is_relative_to(r.resolve()) for r in _project_safe_roots())


@app.get("/config")
async def get_config(project: Optional[str] = None):
    """Return skills, MCPs, and memory files for user scope + optional project scope."""
    skills: List[dict] = []
    mcps: List[dict] = []
    memory: List[dict] = []
    commands: List[dict] = []
    subagents: List[dict] = []

    # ---- USER scope ----
    # Claude: direct skills + plugin-bundled (dedupe by skill name)
    skills += _collect_skills(CLAUDE_DIR, "user", "claude")
    if CLAUDE_DIR.exists():
        seen_names = set()
        for skill_md in CLAUDE_DIR.glob("plugins/**/skills/*/SKILL.md"):
            if "/cache/" in str(skill_md): continue  # skip versioned caches; marketplaces/installed preferred
            s = _parse_skill_md(skill_md)
            if s and s["name"] not in seen_names:
                seen_names.add(s["name"])
                row = {**s, "scope": "user", "agent": "claude", "source": str(skill_md)}
                ref = _claude_plugin_ref(skill_md)
                if ref: row["pluginRef"] = ref
                skills.append(row)
    for p in [CLAUDE_DIR / "settings.json", Path(HOME) / ".claude.json"]:
        mcps += _mcps_from_claude_settings(p, "user")
    claude_md = CLAUDE_DIR / "CLAUDE.md"
    m = _memory_preview(claude_md, "user", "claude") if claude_md.exists() else None
    if m: memory.append(m)

    commands += _collect_commands(CLAUDE_DIR, "user", "claude")
    subagents += _collect_subagents(CLAUDE_DIR, "user", "claude")
    if CLAUDE_DIR.exists():
        seen_cmds = set(c["name"] for c in commands)
        for md in CLAUDE_DIR.glob("plugins/**/commands/*.md"):
            if "/cache/" in str(md): continue
            name = md.stem
            if name in seen_cmds: continue
            seen_cmds.add(name)
            try: txt = md.read_text(errors="ignore")
            except Exception: continue
            description = ""
            if txt.startswith("---"):
                end = txt.find("---", 3)
                if end > 0:
                    for line in txt[3:end].splitlines():
                        if ":" in line:
                            k, v = line.split(":", 1)
                            if k.strip().lower() == "description":
                                description = v.strip().strip('"').strip("'")
            row = {"name": name, "description": description[:200], "scope": "user", "agent": "claude", "source": str(md)}
            ref = _claude_plugin_ref(md)
            if ref: row["pluginRef"] = ref
            commands.append(row)

    # Codex
    mcps += _mcps_from_codex_toml(CODEX_DIR / "config.toml", "user")
    commands += _collect_commands(CODEX_DIR, "user", "codex")
    codex_agents = CODEX_DIR / "AGENTS.md"
    m = _memory_preview(codex_agents, "user", "codex") if codex_agents.exists() else None
    if m: memory.append(m)

    # Cursor
    mcps += _mcps_from_json(CURSOR_DIR / "mcp.json", "user", "cursor")

    # Gemini
    mcps += _mcps_from_json(GEMINI_DIR / "settings.json", "user", "gemini")
    skills += _collect_skills(GEMINI_DIR, "user", "gemini")

    # Qwen
    skills += _collect_skills(QWEN_DIR, "user", "qwen")

    # ---- PROJECT scope ----
    project_valid = False
    if project and _project_within_safe_roots(project):
        proj = Path(project)
        if proj.exists() and proj.is_dir():
            project_valid = True
            # Claude
            skills += _collect_skills(proj / ".claude", "project", "claude")
            commands += _collect_commands(proj / ".claude", "project", "claude")
            commands += _collect_commands(proj / ".codex", "project", "codex")
            subagents += _collect_subagents(proj / ".claude", "project", "claude")
            for p in [proj / ".claude" / "settings.json", proj / ".claude" / "settings.local.json", proj / ".mcp.json"]:
                mcps += _mcps_from_claude_settings(p, "project")
            for fname in ["CLAUDE.md", "AGENTS.md"]:
                fp = proj / fname
                m = _memory_preview(fp, "project", "claude" if fname == "CLAUDE.md" else "codex") if fp.exists() else None
                if m: memory.append(m)

            # Cursor
            mcps += _mcps_from_json(proj / ".cursor" / "mcp.json", "project", "cursor")
            skills += _collect_skills(proj / ".cursor" / "skills-cursor", "project", "cursor")
            subagents += _collect_subagents(proj / ".cursor", "project", "cursor")

            # Generic .agents
            skills += _collect_skills(proj / ".agents", "project", "agents")
            subagents += _collect_subagents(proj / ".agents", "project", "agents")

            # Gemini
            mcps += _mcps_from_json(proj / ".gemini" / "settings.json", "project", "gemini")
            skills += _collect_skills(proj / ".gemini", "project", "gemini")

            # Qwen
            skills += _collect_skills(proj / ".qwen", "project", "qwen")

    # Dedupe skills by (name, scope)
    seen_skills = set(); deduped_skills = []
    for s in skills:
        key = (s.get("name"), s.get("scope"))
        if key in seen_skills: continue
        seen_skills.add(key); deduped_skills.append(s)

    # Dedupe MCPs by (name, scope, agent)
    seen = set(); deduped = []
    for m in mcps:
        key = (m.get("name"), m.get("scope"), m.get("agent"))
        if key in seen: continue
        seen.add(key); deduped.append(m)

    # Plugins (project arg already validated above)
    plugins = _collect_all_plugins(Path(project) if project_valid else None)

    # Stamp pluginRef on items whose source falls inside a plugin's installPath.
    # Inline-set refs (Claude plugin-bundled blocks) are preserved by _tag_plugin_refs.
    _tag_plugin_refs(deduped_skills, plugins)
    _tag_plugin_refs(commands, plugins)
    _tag_plugin_refs(subagents, plugins)
    _tag_plugin_refs(deduped, plugins)

    return {
        "project": project,
        "project_valid": project_valid,
        "skills": deduped_skills,
        "mcps": deduped,
        "memory": memory,
        "commands": commands,
        "subagents": subagents,
        "plugins": plugins,
        "counts": {
            "skills": len(deduped_skills),
            "mcps": len(deduped),
            "memory_files": len(memory),
            "commands": len(commands),
            "subagents": len(subagents),
            "plugins": len(plugins),
        },
    }

# --------------------------------------------------------------------------- #
# Trace summaries
# --------------------------------------------------------------------------- #
from fastapi import Body, HTTPException
from summarizers import get_summarizer, available_summarizers, SummarizerError, KNOWN_BACKENDS
import summaries as _summaries

async def _session_meta(session_id: str, agent: str):
    for s in await get_sessions_cached():
        if s["id"] == session_id and (not agent or s["agent"] == agent):
            t = s.get("tokens") or {}
            return {
                "agent": s["agent"], "project": s.get("project"), "model": s.get("model"),
                "input": t.get("input", 0), "output": t.get("output", 0),
                "total": t.get("total", 0), "cost": s.get("cost", 0.0),
            }
    return None

@app.get("/summarizer/available")
async def summarizer_available():
    return {"backends": [
        {"name": s.name, "display_name": s.display_name} for s in available_summarizers()
    ]}

@app.get("/config/summarizer")
async def get_summarizer_config():
    return _summaries.load_config()

@app.put("/config/summarizer")
async def put_summarizer_config(cfg: dict = Body(...)):
    # Reject an unknown backend up front rather than persisting garbage that
    # silently disables every future summarizer call (#57). Validated against
    # the live registry so all real backends (gemini/antigravity/qwen/
    # openai_compat/…) stay accepted — not a stale hardcoded list.
    backend = cfg.get("backend") or None
    if backend is not None and backend not in KNOWN_BACKENDS:
        raise HTTPException(
            status_code=400,
            detail=f"unknown summarizer backend {backend!r}; expected one of {sorted(KNOWN_BACKENDS)}",
        )
    saved = _summaries.save_config(cfg)
    try:
        _telemetry.update_context(
            summarizer_backend=(saved.get("backend") if saved.get("enabled") else "none") or "none"
        )
    except Exception:
        pass
    return saved


@app.get("/summarizer/ollama/models")
async def list_ollama_models():
    """Enumerate the local Ollama model registry. Used by the settings UI to
    let the user pick which model summarizes their traces."""
    from summarizers.ollama import list_installed_models
    return {"models": list_installed_models()}


@app.get("/summarizer/codex/models")
async def list_codex_models():
    """Curated cheaper-tier OpenAI models for users without Pro/Plus or with
    limited API access. Static list — the Codex CLI doesn't expose enumerable
    model discovery."""
    from summarizers.codex import SUGGESTED_MODELS
    return {"models": SUGGESTED_MODELS}


@app.post("/summarizer/openai-compat/test")
async def test_openai_compat(cfg: dict = Body(...)):
    """Ping the configured OpenAI-compatible endpoint with a trivial prompt so
    the settings UI can confirm the server is reachable before saving. Accepts
    the same shape as the config (top-level ``model`` + ``openai_compat`` block,
    or a bare openai_compat dict)."""
    from summarizers.openai_compat import OpenAICompatSummarizer
    from summarizers.errors import classify as _classify_err

    options = cfg.get("openai_compat") if isinstance(cfg.get("openai_compat"), dict) else cfg
    sm = OpenAICompatSummarizer(model=cfg.get("model"), config=options)
    try:
        sample = sm.summarize("Reply with the single word: ok", timeout=30)
        return {"ok": True, "sample": sample[:200], "endpoint": sm.endpoint}
    except SummarizerError as e:
        return {
            "ok": False,
            "error": str(e),
            "error_info": _classify_err(str(e), backend_name="openai_compat"),
        }


@app.get("/sessions/{session_id}/summary")
async def get_summary(session_id: str):
    cached = _summaries.get_cached(session_id)
    return {"summary": cached}

@app.post("/sessions/{session_id}/summary")
async def make_summary(session_id: str, agent: str, force: bool = False):
    detail = await get_session_detail(session_id, agent)
    if isinstance(detail, dict) and detail.get("error"):
        raise HTTPException(status_code=404, detail=detail.get("error", "session not found"))
    events = _summaries.normalize_detail(detail)
    if not events:
        raise HTTPException(status_code=422, detail="no trace content to summarize")

    chash = _summaries.content_hash(session_id, events)
    cached = _summaries.get_cached(session_id)
    if cached and not force and cached.get("content_hash") == chash and cached.get("narrative"):
        return {"summary": {**cached, "stale": False}}

    meta = await _session_meta(session_id, agent) or {"agent": agent}
    brief = _summaries.condense_trace(events, meta)

    cfg = _summaries.load_config()
    backend_name = cfg.get("backend")
    narrative = None
    gen_error = None
    if cfg.get("enabled") and backend_name:
        sm = get_summarizer(backend_name, cfg.get("model"), cfg.get("openai_compat"))
        if sm and sm.is_available():
            try:
                raw = sm.summarize(_summaries.build_prompt(brief))
                narrative = _summaries.parse_narrative(raw)
            except SummarizerError as e:
                gen_error = str(e)
        else:
            gen_error = f"summarizer '{backend_name}' is not available"

    if narrative is None and cached and cached.get("narrative"):
        narrative = cached["narrative"]

    result = _summaries.store(
        session_id, meta.get("agent", agent), chash,
        backend_name or "", cfg.get("model"),
        brief, narrative or {}, 0.0,
    )
    error_info = None
    if gen_error:
        from summarizers.errors import classify as _classify_err
        error_info = _classify_err(gen_error, backend_name=backend_name or "")
    try:
        _telemetry.emit("trace.summarized", {
            "backend": backend_name or "none",
            "outcome": "error" if gen_error else ("ok" if narrative else "empty"),
        })
    except Exception:
        pass
    return {"summary": {**result, "stale": False}, "error": gen_error, "error_info": error_info}

@app.post("/summaries/recent")
async def summarize_recent(limit: int = 20):
    sessions = await get_sessions_cached()
    sessions = sorted(sessions, key=lambda s: s.get("timestamp") or "", reverse=True)[:limit]
    done = skipped = failed = 0
    for s in sessions:
        try:
            res = await make_summary(s["id"], s["agent"], force=False)
            if res.get("error"):
                failed += 1
            elif res["summary"].get("narrative"):
                done += 1
            else:
                skipped += 1
        except HTTPException:
            failed += 1
    return {"requested": len(sessions), "summarized": done, "skipped": skipped, "failed": failed}

if __name__ == "__main__":
    import uvicorn
    import logging

    # Redact the remote-access token from uvicorn's access log. `?token=` is
    # how artifact <img>/<a> loads authenticate (see _presented_token above —
    # they can't set an Authorization header), so without this the token
    # lands in plain sight in every access-log line, which persists under
    # systemd/journald/docker.
    #
    # uvicorn.access records carry a positional args tuple
    # (client_addr, method, full_path, http_version, status_code); the query
    # string lives in full_path (index 2) — see uvicorn.logging.AccessFormatter.
    # addFilter here (before uvicorn.run() below) works because uvicorn's
    # default logging config sets disable_existing_loggers=False and doesn't
    # touch existing filters, so this filter survives uvicorn's own
    # logging.config.dictConfig() call.
    _TOKEN_QS_RE = re.compile(r"([?&]token=)[^&\s\"']+")

    class _TokenRedactingFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            args = record.args
            if isinstance(args, tuple) and len(args) > 2 and isinstance(args[2], str):
                redacted = _TOKEN_QS_RE.sub(r"\1<redacted>", args[2])
                if redacted != args[2]:
                    record.args = args[:2] + (redacted,) + args[3:]
            return True

    logging.getLogger("uvicorn.access").addFilter(_TokenRedactingFilter())

    # Port resolution order: --port CLI arg → TT_API_PORT env var → 8000.
    # bin/cli.js passes --port; running the file directly (uvicorn / python)
    # honors the env var so devs can override without editing args.
    def _resolve_port() -> int:
        argv = sys.argv[1:]
        for i, arg in enumerate(argv):
            if arg == "--port" and i + 1 < len(argv):
                try: return int(argv[i + 1])
                except ValueError: pass
            if arg.startswith("--port="):
                try: return int(arg.split("=", 1)[1])
                except ValueError: pass
        env_port = os.environ.get("TT_API_PORT")
        if env_port:
            try: return int(env_port)
            except ValueError: pass
        return 8000

    # Host resolution order: --host CLI arg → TT_HOST env var → 127.0.0.1.
    # Default stays loopback; set 0.0.0.0 (or a specific interface IP) to expose
    # the API for remote/tailnet access. Pair with TT_ALLOWED_ORIGINS for CORS.
    def _resolve_host() -> str:
        argv = sys.argv[1:]
        for i, arg in enumerate(argv):
            if arg == "--host" and i + 1 < len(argv):
                return argv[i + 1]
            if arg.startswith("--host="):
                return arg.split("=", 1)[1]
        return os.environ.get("TT_HOST") or "127.0.0.1"

    uvicorn.run(app, host=_resolve_host(), port=_resolve_port())
