from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
import os
import re
import json
import yaml
import sqlite3
from pathlib import Path
from typing import List, Optional, Dict, Any, Set
from pydantic import BaseModel
from datetime import datetime, timezone
from urllib.parse import unquote

from harness_config import (
    load_aliases, apply_alias,
    load_hidden, hide_project, unhide_project,
    list_aliases, save_aliases,
    load_preferences, save_preferences,
)

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
    is present (caller then falls back to the per-message estimate)."""
    if not isinstance(metrics, (dict, list)):
        return None
    tot = {"input": 0, "output": 0, "cached": 0}
    found = False

    def grab(obj):
        nonlocal found
        if isinstance(obj, dict):
            for k, v in obj.items():
                kl = str(k).lower()
                if isinstance(v, (int, float)) and not isinstance(v, bool) and "token" in kl:
                    if "cache" in kl:
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
    return tot if found else None

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
# port (the user can pass --port to start.sh / bin/cli.js). Origins are still
# locked to loopback — only localhost/127.0.0.1 on any port are accepted.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
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
HF_DIR = HOME / ".cache/huggingface"
OPENCODE_DB = HOME / ".local/share/opencode/opencode.db"
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
PROJECT_ALIASES_FILE = HOME / ".tokentelemetry" / "aliases.json"

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
    tf = sess_dir / ".system_generated" / "logs" / "transcript.jsonl"
    if not tf.exists():
        tf = sess_dir / ".system_generated" / "logs" / "transcript_full.jsonl"
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
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
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
    # quality: QualityMetrics = QualityMetrics()

# EDIT_TOOLS: Set[str] = {"Edit", "MultiEdit", "Write", "NotebookEdit"}

def _hermes_dbs() -> List[Path]:
    dbs: List[Path] = []
    if HERMES_DB.exists():
        dbs.append(HERMES_DB)
    if HERMES_PROFILES_DIR.is_dir():
        for p in HERMES_PROFILES_DIR.glob("*/state.db"):
            if p.exists():
                dbs.append(p)
    return dbs


_HERMES_CWD_RE = re.compile(r"\[(\d{8}_\d{6}_[a-f0-9]+)\][^\n]*cwd=([^\s,)]+)")

# Structured agent.log lines we parse (per HERMES_INTERNALS.md §2.3)
_HERMES_LOG_TS = r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+"
_HERMES_SID = r"\[(\d{8}_\d{6}_[a-f0-9]+)\]"
_HERMES_API_CALL_RE = re.compile(
    _HERMES_LOG_TS + r"[^\n]*?" + _HERMES_SID + r"[^\n]*?"
    r"API call #(\d+): model=(\S+) provider=(\S+) in=(\d+) out=(\d+) total=(\d+) "
    r"latency=([\d.]+)s(?: cache=(\d+)/(\d+) \((\d+)%\))?"
)
_HERMES_TOOL_DONE_RE = re.compile(
    _HERMES_LOG_TS + r"[^\n]*?" + _HERMES_SID + r"[^\n]*?"
    r"tool (\S+) completed \(([\d.]+)s, (\d+) chars\)"
)
_HERMES_TOOL_FAIL_RE = re.compile(
    _HERMES_LOG_TS + r"[^\n]*?" + _HERMES_SID + r"[^\n]*?"
    r"tool (\S+) failed \(([\d.]+)s\): (.+?)$"
)


def _parse_hermes_log_ts(s: str) -> Optional[datetime]:
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _hermes_log_summary(session_id: str) -> Dict[str, Any]:
    """Parse ~/.hermes/logs/agent.log for one session.

    Returns:
      api_calls: list of {ts, n, model, provider, in, out, total, latency_s, cache_hit_pct?, cache_read?}
      tool_calls: list of {ts, tool, duration_s, chars?, status, error?}
      model_journey: distinct models in temporal order
      summary: {api_call_count, total_latency_s, avg_latency_s, cache_hit_pct, models_used}
    """
    log_path = HERMES_DIR / "logs" / "agent.log"
    if not log_path.exists():
        return {"api_calls": [], "tool_calls": [], "model_journey": [], "summary": None}
    api_calls: List[Dict[str, Any]] = []
    tool_calls: List[Dict[str, Any]] = []
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if session_id not in line:
                    continue
                m = _HERMES_API_CALL_RE.search(line)
                if m:
                    ts = _parse_hermes_log_ts(m.group(1))
                    api_calls.append({
                        "ts": ts.isoformat() if ts else None,
                        "n": int(m.group(3)),
                        "model": m.group(4),
                        "provider": m.group(5),
                        "input": int(m.group(6)),
                        "output": int(m.group(7)),
                        "total": int(m.group(8)),
                        "latency_s": float(m.group(9)),
                        "cache_read": int(m.group(10)) if m.group(10) else None,
                        "cache_prompt": int(m.group(11)) if m.group(11) else None,
                        "cache_hit_pct": int(m.group(12)) if m.group(12) else None,
                    })
                    continue
                m = _HERMES_TOOL_DONE_RE.search(line)
                if m:
                    ts = _parse_hermes_log_ts(m.group(1))
                    tool_calls.append({
                        "ts": ts.isoformat() if ts else None,
                        "tool": m.group(3),
                        "duration_s": float(m.group(4)),
                        "chars": int(m.group(5)),
                        "status": "ok",
                    })
                    continue
                m = _HERMES_TOOL_FAIL_RE.search(line)
                if m:
                    ts = _parse_hermes_log_ts(m.group(1))
                    tool_calls.append({
                        "ts": ts.isoformat() if ts else None,
                        "tool": m.group(3),
                        "duration_s": float(m.group(4)),
                        "status": "error",
                        "error": m.group(5)[:200],
                    })
    except Exception:
        pass

    # Model journey — distinct models in temporal order
    journey: List[str] = []
    for c in api_calls:
        if not journey or journey[-1] != c["model"]:
            journey.append(c["model"])

    if api_calls:
        total_lat = sum(c["latency_s"] for c in api_calls)
        cache_pcts = [c["cache_hit_pct"] for c in api_calls if c.get("cache_hit_pct") is not None]
        summary = {
            "api_call_count": len(api_calls),
            "total_latency_s": round(total_lat, 2),
            "avg_latency_s": round(total_lat / len(api_calls), 2),
            "cache_hit_pct": round(sum(cache_pcts) / len(cache_pcts)) if cache_pcts else None,
            "models_used": sorted({c["model"] for c in api_calls}),
            "providers_used": sorted({c["provider"] for c in api_calls}),
        }
    else:
        summary = None
    return {
        "api_calls": api_calls,
        "tool_calls": tool_calls,
        "model_journey": journey,
        "summary": summary,
    }


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
            uri = f"file:{db_path}?mode=ro"
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


@app.get("/hermes/profiles")
async def hermes_profiles():
    """List available profiles."""
    if not HERMES_PROFILES_DIR.exists():
        return {"profiles": []}
    profiles = []
    for p in HERMES_PROFILES_DIR.iterdir():
        if p.is_dir():
            profiles.append({"name": p.name})
    return {"profiles": profiles}


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


@app.get("/sessions/{session_id}/hermes-overlay")
async def hermes_session_overlay(session_id: str):
    """Per-session overlay derived from agent.log + memory tool calls."""
    log = _hermes_log_summary(session_id)
    mem = _hermes_memory_io(session_id)
    return {
        "session_id": session_id,
        "performance": log["summary"],
        "api_calls": log["api_calls"],
        "tool_calls": log["tool_calls"],
        "model_journey": log["model_journey"],
        "memory_io": mem,
    }


def _hermes_cwd_by_session() -> Dict[str, str]:
    """Recover per-session cwd from ~/.hermes/logs/agent.log.

    Hermes doesn't persist cwd in its schema (it's a portable agent — no project
    concept). The cwd surfaces only as a side effect when the `terminal` tool
    initializes a sandbox. We parse the log line and attribute the *first* cwd
    seen per session id. Sessions that never invoked the terminal stay 'unknown'.
    Fidelity: inferred.
    """
    log_path = HERMES_DIR / "logs" / "agent.log"
    if not log_path.exists():
        return {}
    out: Dict[str, str] = {}
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
        return out
    return out


def _hermes_gateway_state() -> Dict[str, Any]:
    """Read ~/.hermes/gateway_state.json + gateway.pid. Both are optional.

    Returns dict with keys: state (str), pid (int|None), pid_alive (bool),
    active_agents (int), platforms (list[{name, state, error_code}]),
    updated_at (iso str|None). All-NULL if no gateway file present.
    """
    state_path = HERMES_DIR / "gateway_state.json"
    pid_path = HERMES_DIR / "gateway.pid"
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


def _hermes_cron_jobs() -> List[Dict[str, Any]]:
    """Read ~/.hermes/cron/jobs.json — Hermes's scheduled-job registry.

    Annotates each job with `at_risk` when next_run_at is past now (grace window
    applied per Hermes's own rule: daily=2h, hourly=30m, 10min=5m). Hermes itself
    fast-forwards past these but doesn't expose them — so we flag them.
    """
    jobs_path = HERMES_DIR / "cron" / "jobs.json"
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


# --------------------------------------------------------------------------- #
# Update checker — compares local git HEAD to remote main, pulls curated
# highlights from UPDATE.json at the repo root. The "What's new" banner in
# the dashboard renders only when behind=true.
# --------------------------------------------------------------------------- #
import subprocess as _subprocess
import time as _upd_time
import urllib.request as _urlreq

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TT_HOME = HOME / ".tokentelemetry"
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
        if age > _UPDATE_CACHE_TTL:
            return None
        return cached
    except Exception:
        return None


def _write_cache(payload: Dict[str, Any]) -> None:
    try:
        _TT_HOME.mkdir(parents=True, exist_ok=True)
        payload = {**payload, "fetched_at": _upd_time.time()}
        with open(_UPDATE_CACHE, "w", encoding="utf-8") as f:
            json.dump(payload, f)
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
        if not latest_sha:
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
    base["behind"] = bool(latest) and latest != current
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
    # if OLLAMA_DIR.exists(): agents.append("ollama")
    return agents


@app.get("/agents")
async def get_available_agents():
    return _list_available_agents()

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


def _scan_grok_sessions() -> List[Dict[str, Any]]:
    """Scan Grok Build sessions under ~/.grok/sessions/.

    Produces the standard TokenTelemetry session record with rich Grok-specific forensics.
    """
    if not GROK_SESSIONS_DIR.exists():
        return []

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

            # Token forensics. Grok exposes no prompt/completion split anywhere, so we
            # use signals.contextTokensUsed (the measured context footprint) when present,
            # falling back to the max cumulative totalTokens scanned from updates.jsonl.
            tokens = {"input": 0, "output": 0, "cached": 0, "total": 0}
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

            # Grok exposes no prompt/completion split; the agentic context is overwhelmingly
            # fed-in tool/file content, so we attribute the measured context footprint to input
            # rather than fabricating a 50/50 guess. Cost is therefore a lower-bound estimate.
            tokens["total"] = total
            tokens["input"] = total
            tokens["output"] = 0
            tokens["cached"] = 0

            # Grok Build exposes only a single context-footprint total (no cache-write field); nothing to pass.
            tokens["cost"] = calculate_cost(model, tokens.get("input", 0), tokens.get("output", 0), tokens.get("cached", 0))

            # Prefer signals.modelsUsed for the model when available.
            models_used = signals.get("modelsUsed")
            if isinstance(models_used, list) and models_used:
                model = summary.get("current_model_id") or models_used[0] or model

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
            out.append(sess)

    return out


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
            "model": None, "artifacts": [],
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
                                "model": None, "artifacts": [],
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
                            uc = data.get("message", {}).get("content")
                            if isinstance(uc, str) and uc.strip():
                                sess["display"] = uc.strip()[:120]
                    if sess["project"] != "unknown" and sess.get("display"):
                        break
        except Exception: pass

    # Sort by recency (newest first) BEFORE truncating — insertion-order
    # slicing previously dropped genuinely recent sessions when totals
    # exceeded 100.
    if claude_sessions:
        for sid, sess in sorted(claude_sessions.items(), key=lambda kv: kv[1]["timestamp"], reverse=True)[:100]:
            session_file = claude_file_map.get(sid)
            if session_file:
                # Discover Claude Project Memory artifacts
                try:
                    memory_dir = session_file.parent.parent / "memory"
                    if memory_dir.exists():
                        for mf in memory_dir.glob("*.md"):
                            sess["artifacts"].append({"name": mf.name, "path": str(mf), "type": "document"})
                except Exception: pass

                # pending_edit_tool_ids: Set[str] = set()  # quality signals (commented out)
                # prior_edit_failed = False
                try:
                    with open(session_file, "r", encoding="utf-8", errors="replace") as f:
                        for line in f:
                            try:
                                data = json.loads(line)
                            except Exception: continue
                            if data.get("type") == "assistant":
                                msg = data.get("message", {})
                                m = msg.get("model")
                                if m and m != "<synthetic>" and not sess.get("model"):
                                    sess["model"] = m
                                usage = msg.get("usage", {})
                                if usage:
                                    cr = usage.get("cache_read_input_tokens", 0) or 0
                                    cc = usage.get("cache_creation_input_tokens", 0) or 0
                                    sess["tokens"]["input"]  += usage.get("input_tokens", 0) or 0
                                    sess["tokens"]["output"] += usage.get("output_tokens", 0) or 0
                                    # cached = unique cached-prefix size (high-water-mark), NOT per-turn sum
                                    sess["tokens"]["cached"] = max(sess["tokens"]["cached"], cr)
                                    sess["tokens"]["_cached_sum"] = sess["tokens"].get("_cached_sum", 0) + cr
                                    # cache_creation (write) IS billed per event → cumulative, like input.
                                    sess["tokens"]["cache_creation"] = sess["tokens"].get("cache_creation", 0) + cc
                                sess["tokens"]["total"] = sess["tokens"]["input"] + sess["tokens"]["output"] + sess["tokens"]["cached"]
                                sess["cost"] = calculate_cost(sess.get("model"), sess["tokens"]["input"], sess["tokens"]["output"], sess["tokens"]["cached"], cache_creation_tokens=sess["tokens"].get("cache_creation", 0))
                                for item in msg.get("content", []):
                                    if item.get("type") == "tool_use":
                                        tool = item.get("name")
                                        if tool not in sess["mcp_tools"]: sess["mcp_tools"].append(tool)
                                        if tool == "ExitPlanMode":
                                            plan_text = (item.get("input") or {}).get("plan") or ""
                                            if plan_text:
                                                sess["has_plan"] = True
                                                sess["plans"].append({"session_id": sid, "agent": "claude", "timestamp": sess["timestamp"], "content": plan_text})
                                    if item.get("type") == "thinking":
                                        t_text = item.get("thinking", "")
                                        if "plan" in t_text.lower() and len(t_text) > 100:
                                            sess["has_plan"] = True
                                            sess["plans"].append({"session_id": sid, "agent": "claude", "timestamp": sess["timestamp"], "content": t_text})
                                # Quality signals (edit/retry tracking) commented out:
                                # if this_turn_edit_ids:
                                #     sess["quality"]["edit_turns"] += 1
                                #     if prior_edit_failed:
                                #         sess["quality"]["retry_turns"] += 1
                                #     pending_edit_tool_ids = this_turn_edit_ids
                                #     prior_edit_failed = False
                            if data.get("type") == "user":
                                u_msg = data.get("message", {})
                                u_content = u_msg.get("content", "")
                                if "/plan" in str(u_content):
                                    sess["has_plan"] = True
                                # Quality signals (retry chain tracking) commented out:
                                # if isinstance(u_content, list):
                                #     for it in u_content:
                                #         if isinstance(it, dict) and it.get("type") == "tool_result":
                                #             if it.get("tool_use_id") in pending_edit_tool_ids and it.get("is_error"):
                                #                 prior_edit_failed = True
                                # else:
                                #     prior_edit_failed = False
                                #     pending_edit_tool_ids = set()
                except Exception: continue
        sessions.extend(claude_sessions.values())
    # 2. Codex
    codex_index = CODEX_DIR / "session_index.jsonl"
    if codex_index.exists():
        codex_sessions = {}
        # Pre-index Codex rollout files
        codex_file_map = {}
        try:
            for f in (CODEX_DIR / "sessions").rglob("rollout-*.jsonl"):
                # stem: rollout-2025-10-21T16-55-35-019a0684-74e3-7423-af75-41c73aab7d68
                # sid: 019a0684-74e3-7423-af75-41c73aab7d68
                parts = f.stem.split("-")
                if len(parts) >= 6:
                    sid = "-".join(parts[-5:])
                    codex_file_map[sid] = f
        except Exception: pass

        try:
            with open(codex_index, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        data = json.loads(line); sid = data.get("id")
                        if not sid: continue
                        ts = _aware(datetime.fromisoformat(data.get("updated_at").replace('Z', '+00:00'))) if data.get("updated_at") else _file_mtime_utc(codex_index)
                        if sid not in codex_sessions or ts > codex_sessions[sid]["timestamp"]:
                            codex_sessions[sid] = {"id": sid, "agent": "codex", "project": "unknown", "timestamp": ts, "text": data.get("thread_name"), "tokens": {"input": 0, "output": 0, "cached": 0, "total": 0}, "mcp_tools": [], "has_plan": False, "plans": [], "model": None, "artifacts": []}
                    except Exception: continue
        except Exception: pass
        
        # Process the 100 most recent sessions
        for sid, sess in sorted(codex_sessions.items(), key=lambda kv: kv[1]["timestamp"], reverse=True)[:100]:
            rollout_file = codex_file_map.get(sid)
            if rollout_file:
                try:
                    with open(rollout_file, "r", encoding="utf-8", errors="replace") as f:
                        for line in f:
                            try:
                                data = json.loads(line)
                            except Exception: continue
                            if data.get("type") == "session_meta":
                                sess["project"] = apply_alias(data["payload"].get("cwd", "unknown"))
                                if not sess.get("model") and data["payload"].get("model"):
                                    sess["model"] = data["payload"].get("model")
                                if not sess.get("_provider"):
                                    sess["_provider"] = data["payload"].get("model_provider")
                            if data.get("type") == "turn_context" and not sess.get("model"):
                                sess["model"] = data.get("payload", {}).get("model")
                            if data.get("type") == "event_msg":
                                usage = ((data.get("payload") or {}).get("info") or {}).get("total_token_usage") or {}
                                if usage:
                                    # OpenAI/Codex semantics differ from Anthropic:
                                    #   input_tokens is the GROSS input — it already includes cached_input_tokens.
                                    #   total_tokens = input_tokens + output_tokens (cached is a breakdown, not an
                                    #   independent bucket). Reasoning is typically already in output_tokens for
                                    #   Chat-Completions-style APIs; we add reasoning explicitly only if the record's
                                    #   total_tokens doesn't already account for it.
                                    gross_input = usage.get("input_tokens", 0) or 0
                                    cached      = usage.get("cached_input_tokens", 0) or 0
                                    output      = usage.get("output_tokens", 0) or 0
                                    reasoning   = usage.get("reasoning_output_tokens", 0) or 0
                                    total_record = usage.get("total_tokens", 0) or 0
                                    net_input   = max(0, gross_input - cached)
                                    # If total_tokens > gross_input + output, the API is reporting reasoning as
                                    # extra (not folded into output_tokens). Otherwise reasoning is implicit.
                                    output_billable = output + (reasoning if total_record > gross_input + output else 0)

                                    sess["tokens"]["input"]  = max(sess["tokens"]["input"],  net_input)
                                    sess["tokens"]["cached"] = max(sess["tokens"]["cached"], cached)
                                    sess["tokens"]["output"] = max(sess["tokens"]["output"], output_billable)
                                    sess["tokens"]["total"]  = sess["tokens"]["input"] + sess["tokens"]["cached"] + sess["tokens"]["output"]
                                    # Codex/OpenAI usage has no cache-write field (only cached read); nothing to pass.
                                    sess["cost"] = calculate_cost(sess.get("model"), sess["tokens"]["input"], sess["tokens"]["output"], sess["tokens"]["cached"])
                            if data.get("type") == "response_item":
                                if data.get("payload", {}).get("type") == "function_call":
                                    tool = data["payload"].get("name")
                                    if tool not in sess["mcp_tools"]: sess["mcp_tools"].append(tool)
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
        for s in codex_sessions.values():
            if not s.get("model") and s.get("_provider"):
                s["model"] = s["_provider"]
            s.pop("_provider", None)
        sessions.extend(codex_sessions.values())

    # 3 & 7. Gemini & Antigravity
    gemini_projects_file = GEMINI_DIR / "projects.json"
    if gemini_projects_file.exists():
        try:
            with open(gemini_projects_file, "r") as f:
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
                    for _cf in _cd.glob("*.json"):
                        try:
                            _all_chat_sids.add(json.loads(_cf.read_text(encoding="utf-8", errors="replace")).get("sessionId") or "")
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
                    for cf in chat_dir.glob("*.json"):
                        try:
                            with open(cf, "r", encoding="utf-8", errors="replace") as f:
                                data = json.load(f); sid = data.get("sessionId")
                                if not sid: continue
                                # kind="main" means Gemini CLI; absent/other means Antigravity
                                session_kind = data.get("kind")
                                effective_agent = agent_type if session_kind == "main" else "antigravity"
                                ts = _aware(datetime.fromisoformat(data.get("lastUpdated").replace('Z', '+00:00'))) if data.get("lastUpdated") else _file_mtime_utc(cf)
                                tokens = {"input": 0, "output": 0, "cached": 0, "total": 0}
                                mcp_tools = []; has_plan = False; first_msg = ""; plans = []
                                has_user = False
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
                                tokens["cost"] = calculate_cost(model, tokens["input"], tokens["output"], tokens["cached"])
                                if sid in _seen_antigravity: continue
                                _seen_antigravity.add(sid)
                                sessions.append({"id": sid, "agent": effective_agent, "project": project_path, "timestamp": ts, "display": first_msg[:100], "tokens": tokens, "mcp_tools": mcp_tools, "has_plan": has_plan, "plans": plans, "model": model, "artifacts": artifacts, "antigravity_source": _ag_surface.get(sid), "cost": tokens["cost"]})
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
                # Scan for base documents as artifacts
                for fname in ("task.md", "implementation_plan.md", "walkthrough.md"):
                    fp = sess_dir / fname
                    mp = sess_dir / f"{fname}.metadata.json"
                    if fp.exists():
                        artifacts.append({"name": fname, "path": str(fp), "type": "document"})
                        try: 
                            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                                body = f.read()
                        except Exception: body = ""
                        if fname == "task.md": task = body
                        elif fname == "implementation_plan.md": plan = body
                        else: walkthrough = body
                    if mp.exists():
                        try:
                            md = json.loads(mp.read_text(encoding="utf-8", errors="replace"))
                            updated = md.get("updatedAt")
                            if updated:
                                ts = _aware(datetime.fromisoformat(updated.replace("Z", "+00:00")))
                                if latest_ts is None or ts > latest_ts: latest_ts = ts
                        except Exception: pass
                
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
                display = (first_line or "Antigravity session")[:100]
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
                        artifacts = []
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
                                        tokens["input"]  += usage.get("input_tokens", 0) or 0
                                        tokens["output"] += usage.get("output_tokens", 0) or 0
                                        tokens["cached"] = max(tokens["cached"], cr)
                                        tokens["_cached_sum"] = tokens.get("_cached_sum", 0) + cr
                                        # cache_creation (write) IS billed per event → cumulative, like input.
                                        tokens["cache_creation"] = tokens.get("cache_creation", 0) + cc
                                        for item in data.get("message", {}).get("content", []):
                                            if item.get("type") == "tool_use":
                                                if item.get("name") not in mcp_tools: mcp_tools.append(item.get("name"))
                                            if item.get("type") == "thinking":
                                                t_text = item.get("thinking", "")
                                                if "plan" in t_text.lower() and len(t_text) > 100:
                                                    has_plan = True
                                                    plans.append({"session_id": sid, "agent": "qwen", "timestamp": last_ts, "content": t_text})
                                except Exception: continue
                        tokens["total"] = tokens["input"] + tokens["output"] + tokens["cached"]
                        tokens["cost"] = calculate_cost(model, tokens["input"], tokens["output"], tokens["cached"], cache_creation_tokens=tokens.get("cache_creation", 0))
                        sessions.append({"id": sid, "agent": "qwen", "project": project_path, "timestamp": last_ts, "display": first_msg[:100], "tokens": tokens, "mcp_tools": mcp_tools, "has_plan": has_plan, "plans": plans, "model": model, "artifacts": artifacts, "cost": tokens["cost"]})
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
                    tokens["cost"] = calculate_cost(model, tokens["input"], tokens["output"], tokens["cached"])
                    sessions.append({"id": sid, "agent": "vibe", "project": project_path, "timestamp": ts, "display": f"Vibe Session {sid[:8]}", "tokens": tokens, "mcp_tools": list(set(mcp_tools)), "has_plan": False, "plans": [], "model": model, "artifacts": [], "cost": tokens["cost"]})
            except Exception: continue

    # 6. Cursor
    if CURSOR_DIR.exists():
        cursor_map = {}
        if CURSOR_STORAGE.exists():
            for ws in CURSOR_STORAGE.glob("*/workspace.json"):
                try:
                    with open(ws, "r") as f:
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
                                            tokens["input"]  += usage.get("input_tokens", 0) or 0
                                            tokens["output"] += usage.get("output_tokens", 0) or 0
                                            tokens["cached"] = max(tokens["cached"], cr)
                                            tokens["_cached_sum"] = tokens.get("_cached_sum", 0) + cr
                                            # cache_creation (write) IS billed per event → cumulative, like input.
                                            tokens["cache_creation"] = tokens.get("cache_creation", 0) + cc
                                            for item in msg.get("content", []) if isinstance(msg.get("content"), list) else []:
                                                if item.get("type") == "tool_use":
                                                    name = item.get("name")
                                                    if name not in mcp_tools: mcp_tools.append(name)
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
                                tokens["cost"] = calculate_cost(model, tokens["input"], tokens["output"], tokens["cached"], cache_creation_tokens=tokens.get("cache_creation", 0))
                                sessions.append({"id": sid, "agent": "cursor", "project": project_path, "timestamp": mtime, "display": first_msg[:100], "tokens": tokens, "mcp_tools": mcp_tools, "subagents": subagents, "has_plan": has_plan, "plans": plans, "model": model, "artifacts": artifacts, "cost": tokens["cost"]})
                            except Exception: continue

    # 7. Copilot
    if VSCODE_STORAGE.exists():
        for ws_folder in VSCODE_STORAGE.glob("*/chatSessions"):
            try:
                workspace_json = ws_folder.parent / "workspace.json"
                project_path = "unknown"
                if workspace_json.exists():
                    with open(workspace_json, "r") as f:
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
                        tokens["cost"] = calculate_cost(model, tokens["input"], tokens["output"], tokens["cached"])
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
                # Copilot CLI modelMetrics has no distinct cache-write field; nothing to pass.
                tokens["cost"] = calculate_cost(model, tokens["input"], tokens["output"], tokens["cached"])
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

    # 8. OpenCode (SQLite: session / message / part)
    if OPENCODE_DB.exists():
        try:
            # immutable=1 so we don't block the live TUI process's write lock
            uri = f"file:{OPENCODE_DB}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=1.0)
            conn.row_factory = sqlite3.Row
            try:
                # Some OpenCode versions added a session-level `model` column
                # (e.g. the github-copilot provider stores the model only there,
                # not on assistant messages — see issue #39). Detect it so we can
                # fall back to it, without breaking older schemas that lack it.
                try:
                    _sess_cols = {r[1] for r in conn.execute("PRAGMA table_info(session)")}
                except Exception:
                    _sess_cols = set()
                _has_sess_model = "model" in _sess_cols
                rows = conn.execute("SELECT id, directory, title, time_created, time_updated FROM session").fetchall()
                for srow in rows:
                    sid = srow["id"]
                    ts = datetime.fromtimestamp((srow["time_updated"] or srow["time_created"] or 0) / 1000, tz=timezone.utc)
                    tokens = {"input": 0, "output": 0, "cached": 0, "total": 0}
                    model = None
                    models_used: List[str] = []   # distinct models, in first-seen order (#39)
                    first_user = ""
                    mcp_tools: List[str] = []
                    has_plan = False
                    plans: List[Dict[str, Any]] = []
                    # Model + tokens from assistant messages
                    for mrow in conn.execute("SELECT data FROM message WHERE session_id=? ORDER BY time_created", (sid,)):
                        try:
                            mdata = json.loads(mrow["data"] or "{}")
                        except Exception: continue
                        if mdata.get("role") == "assistant":
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
                            txt = pdata.get("text") or ""
                            if txt: first_user = txt
                        if ptype == "tool":
                            tname = pdata.get("tool")
                            if tname and tname not in mcp_tools: mcp_tools.append(tname)
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
                    tokens["cost"] = calculate_cost(model, tokens["input"], tokens["output"], tokens["cached"], cache_creation_tokens=tokens.get("cache_creation", 0))
                    project_path = srow["directory"] or "unknown"
                    title = srow["title"] or ""
                    display = (first_user or title)[:100]
                    # Todos (opencode's plan-like artifact)
                    todo_rows = conn.execute("SELECT content, status FROM todo WHERE session_id=? ORDER BY position", (sid,)).fetchall()
                    if todo_rows:
                        has_plan = True
                        plan_text = "\n".join(f"- [{r['status']}] {r['content']}" for r in todo_rows)
                        plans.append({"session_id": sid, "agent": "opencode", "timestamp": ts, "content": plan_text})
                    sessions.append({
                        "id": sid, "agent": "opencode", "project": apply_alias(srow["directory"] or "unknown"), "timestamp": ts,
                        "display": display, "tokens": tokens, "mcp_tools": mcp_tools,
                        "has_plan": has_plan, "plans": plans, "model": model,
                        "models_used": models_used, "artifacts": [],
                        "cost": tokens["cost"],
                    })
            finally:
                conn.close()
        except Exception:
            pass

    # 8. Grok Build (xAI) — rich per-session directory with events, updates, chat history
    sessions.extend(_scan_grok_sessions())

    # 9. Hermes Agent (SQLite: sessions / messages, pre-aggregated tokens)
    hermes_cwd_map = _hermes_cwd_by_session() if _hermes_dbs() else {}
    for db_path in _hermes_dbs():
        try:
            uri = f"file:{db_path}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=1.0)
            conn.row_factory = sqlite3.Row
            try:
                # billing_base_url is newer; older Hermes DBs may lack it. Select
                # it only when present so the whole scan doesn't fail on legacy
                # schemas (the outer try/except would otherwise drop all sessions).
                _cols = {r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()}
                _base_url_col = "billing_base_url" if "billing_base_url" in _cols else "NULL AS billing_base_url"
                srows = conn.execute(
                    "SELECT id, source, model, parent_session_id, started_at, ended_at, "
                    "input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, "
                    "reasoning_tokens, estimated_cost_usd, actual_cost_usd, title, "
                    f"billing_provider, {_base_url_col}, end_reason "
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
                    if cost is None:
                        cost = calculate_cost(
                            model, in_t, out_t, cached,
                            provider=srow["billing_provider"],
                            cache_creation_tokens=cache_write,
                            endpoint=srow["billing_base_url"],
                        )
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
                    # Distinct tool names used in this session
                    mcp_tools = [r[0] for r in conn.execute(
                        "SELECT DISTINCT tool_name FROM messages "
                        "WHERE session_id=? AND tool_name IS NOT NULL AND tool_name != ''",
                        (sid,)).fetchall()]
                    cwd = hermes_cwd_map.get(sid)
                    sessions.append({
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
                    })
            finally:
                conn.close()
        except Exception:
            pass

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
from pricing import calculate_cost, PRICING, PRICING_UPDATED
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
    return await get_sessions_cached(fresh=fresh)


@app.get("/pricing")
async def get_pricing():
    """Return the static pricing table and the date it was last refreshed."""
    return {"updated": PRICING_UPDATED, "models": PRICING}


@app.get("/artifacts")
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
    return {"ok": True}


@app.get("/sessions/{session_id}")
async def get_session_detail(session_id: str, agent: str):
    if agent == "claude":
        files = list(CLAUDE_DIR.glob(f"projects/**/{session_id}.jsonl")) or list(CLAUDE_DIR.glob(f"sessions/{session_id}.json"))
        if not files: return {"error": "Not found"}
        events = []
        with open(files[0], "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    # Add a normalized_timestamp for waterfall
                    if data.get("timestamp"):
                        try:
                            ts = _aware(datetime.fromisoformat(data["timestamp"].replace('Z', '+00:00')))
                            data["normalized_timestamp"] = ts.timestamp() * 1000
                        except Exception: pass
                    events.append(data)
                except Exception: continue
        return events
    elif agent == "codex":
        files = list(CODEX_DIR.glob(f"sessions/**/rollout-*{session_id}*.jsonl"))
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

    elif agent in ["gemini", "antigravity"]:
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
        files = list((GEMINI_DIR / "tmp").glob(f"**/chats/session-*{session_id[:8]}*.json")) or list((GEMINI_DIR / "tmp").glob(f"**/chats/*{session_id}*.json"))
        if files:
            with open(files[0], "r", encoding="utf-8", errors="replace") as f:
                data = json.load(f)
                # Add normalized_timestamp to messages
                for msg in data.get("messages", []):
                    if msg.get("timestamp"):
                        try:
                            ts = _aware(datetime.fromisoformat(msg["timestamp"].replace('Z', '+00:00')))
                            msg["normalized_timestamp"] = ts.timestamp() * 1000
                        except Exception: pass
                return data
        # Antigravity log-only sessions: synthesize messages from the per-tmp-dir
        # logs.json that records every user/assistant turn with its sessionId.
        if agent == "antigravity":
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
        if not OPENCODE_DB.exists(): return {"error": "Not found"}
        uri = f"file:{OPENCODE_DB}?mode=ro"
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
                # step-start / step-finish are lifecycle markers; skip in trace
            return events
        finally:
            conn.close()
    elif agent == "hermes":
        for db_path in _hermes_dbs():
            try:
                uri = f"file:{db_path}?mode=ro"
                conn = sqlite3.connect(uri, uri=True, timeout=1.0)
                conn.row_factory = sqlite3.Row
                try:
                    srow = conn.execute("SELECT id FROM sessions WHERE id=?", (session_id,)).fetchone()
                    if not srow:
                        continue
                    events: List[Dict[str, Any]] = []
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

@app.get("/projects")
async def get_projects(include_hidden: bool = False):
    sessions = await get_sessions_cached(); projects = {}
    hidden = load_hidden()
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
            projects[proj] = {"name": proj_name, "path": proj, "session_count": 0, "agents": set(), "mcp_tools": set(), "subagent_count": 0, "plan_count": 0, "tokens": {"input": 0, "output": 0, "cached": 0, "total": 0, "cost": 0.0}, "plans": []}
        projects[proj]["session_count"] += 1; projects[proj]["agents"].add(s["agent"])
        for t in s.get("mcp_tools", []): projects[proj]["mcp_tools"].add(t)
        if s.get("has_plan"): projects[proj]["plan_count"] += 1
        projects[proj]["subagent_count"] += len(s.get("subagents", []))
        st = s.get("tokens", {})
        for k in ["input", "output", "cached", "total"]: projects[proj]["tokens"][k] += st.get(k, 0)
        projects[proj]["tokens"]["cost"] += s.get("cost", 0.0)
        projects[proj]["plans"].extend(s.get("plans", []))
    for p in projects.values():
        p["agents"] = list(p["agents"])
        p["mcp_tools"] = list(p["mcp_tools"])
        p["plans"] = sorted(p["plans"], key=lambda x: str(x["timestamp"]), reverse=True)
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
    out = list(projects.values())
    if not include_hidden:
        out = [p for p in out if not p["hidden"]]
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


@app.get("/config/power")
async def get_power_config():
    """Power & subscription cost config for local/subscription models.

    `configured` tells the UI whether a power.json exists yet — when false the
    returned values are the shipped defaults and the local-model electricity
    branch is inactive until the user saves.
    """
    from power_config import load_power_config, has_user_config
    cfg = load_power_config()
    return {**cfg, "configured": has_user_config()}


@app.put("/config/power")
async def put_power_config(payload: dict = Body(...)):
    """Persist power config. Body: {loadWatts?, costPerKwh?, subscriptionEndpoints?}.

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
    """Return cache hit ratio as 0-100, matching the Hermes overlay's scale."""
    denom = input_tokens + cached_tokens
    if denom <= 0:
        return None
    return round((cached_tokens / denom) * 100, 1)


@app.get("/analytics")
async def get_analytics():
    sessions = await get_sessions_cached(); by_agent = {}; by_day = {}; by_model = {}
    # quality_by_agent: Dict[str, Dict[str, int]] = {}
    # total_edit_turns = 0
    # total_retry_turns = 0
    # total_measured_sessions = 0
    for s in sessions:
        agent = s["agent"]
        if agent not in by_agent: by_agent[agent] = {"input": 0, "output": 0, "cached": 0, "total": 0, "cost": 0.0, "session_count": 0}
        st = s.get("tokens", {})
        scost = s.get("cost", 0.0)
        for k in ["input", "output", "cached", "total"]: by_agent[agent][k] += st.get(k, 0)
        by_agent[agent]["cost"] += scost
        by_agent[agent]["session_count"] += 1
        model_name = s.get("model") or f"{agent} (unknown)"
        if model_name not in by_model:
            by_model[model_name] = {"input": 0, "output": 0, "cached": 0, "total": 0, "cost": 0.0, "session_count": 0, "agent": agent}
        for k in ["input", "output", "cached", "total"]: by_model[model_name][k] += st.get(k, 0)
        by_model[model_name]["cost"] += scost
        by_model[model_name]["session_count"] += 1
        # Bucket by LOCAL day, not UTC — a 9pm-PT session shouldn't land on the
        # next day just because the timestamp crossed midnight UTC.
        day = s["timestamp"].astimezone().strftime("%Y-%m-%d")
        if day not in by_day: by_day[day] = {"total": 0, "input": 0, "output": 0, "cached": 0, "cost": 0.0}
        for k in ["input", "output", "cached", "total"]: by_day[day][k] += st.get(k, 0)
        by_day[day]["cost"] += scost
        # q = s.get("quality") or {}
        # if q.get("measured"):
        #     agg = quality_by_agent.setdefault(agent, {"edit_turns": 0, "retry_turns": 0, "measured_sessions": 0})
        #     agg["edit_turns"] += q.get("edit_turns", 0)
        #     agg["retry_turns"] += q.get("retry_turns", 0)
        #     agg["measured_sessions"] += 1
        #     total_edit_turns += q.get("edit_turns", 0)
        #     total_retry_turns += q.get("retry_turns", 0)
        #     total_measured_sessions += 1
    for agent, row in by_agent.items():
        row["cache_hit_pct"] = _cache_hit_pct(row["input"], row["cached"])
        # agg = quality_by_agent.get(agent)
        # if agg:
        #     row["quality"] = _quality_summary(agg["edit_turns"], agg["retry_turns"], agg["measured_sessions"])
        # else:
        #     row["quality"] = _quality_summary(0, 0, 0)
    sorted_days = sorted([{"date": d, **v} for d, v in by_day.items()], key=lambda x: x["date"])
    total_input = sum(a["input"] for a in by_agent.values())
    total_output = sum(a["output"] for a in by_agent.values())
    total_cached = sum(a["cached"] for a in by_agent.values())
    return {
        "by_agent": by_agent,
        "by_day": sorted_days,
        "by_model": by_model,
        "total": {
            "input": total_input,
            "output": total_output,
            "cached": total_cached,
            "total": sum(a["total"] for a in by_agent.values()),
            "cost": sum(a["cost"] for a in by_agent.values()),
            "cache_hit_pct": _cache_hit_pct(total_input, total_cached),
            # "quality": _quality_summary(total_edit_turns, total_retry_turns, total_measured_sessions),
        },
        "pricing_updated": PRICING_UPDATED,
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
    return _summaries.save_config(cfg)


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

    uvicorn.run(app, host="127.0.0.1", port=_resolve_port())
