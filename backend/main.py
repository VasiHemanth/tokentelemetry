from fastapi import FastAPI
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

app = FastAPI(title="TokenTelemetry API")

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3002",
    ],
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

# Specialized storage paths
VSCODE_STORAGE = VSCODE_BASE / "User/workspaceStorage"
CURSOR_STORAGE = CURSOR_BASE / "User/workspaceStorage"
ANTIGRAVITY_BRAIN_DIR = GEMINI_DIR / "antigravity" / "brain"
PROJECT_ALIASES_FILE = HOME / ".tokentelemetry" / "aliases.json"

def _load_project_aliases() -> Dict[str, str]:
    # Ensure directory exists
    PROJECT_ALIASES_FILE.parent.mkdir(parents=True, exist_ok=True)
    if PROJECT_ALIASES_FILE.exists():
        try:
            with open(PROJECT_ALIASES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {}

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
            
    return "Antigravity / unassigned"

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
                    except: continue
                    if not isinstance(tcs, list): continue
                    for tc in tcs:
                        fn = (tc or {}).get("function") or {}
                        if (fn.get("name") or tc.get("name")) != "memory":
                            continue
                        args_raw = fn.get("arguments") or "{}"
                        try:
                            args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
                        except: continue
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
            # Cheap liveness check — kill(pid, 0) raises if no such process
            if out["pid"]:
                try:
                    os.kill(out["pid"], 0)
                    out["pid_alive"] = True
                except (ProcessLookupError, PermissionError, OSError):
                    out["pid_alive"] = False
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
        out.append({
            "id": j.get("id"),
            "name": j.get("name"),
            "schedule": sched,
            "last_run_at": j.get("last_run_at"),
            "next_run_at": j.get("next_run_at"),
            "last_status": j.get("last_status"),
            "last_error": j.get("last_error"),
            "at_risk": at_risk,
        })
    return out


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


@app.get("/")
async def root():
    return {"message": "TokenTelemetry API is running"}

@app.get("/agents")
async def get_available_agents():
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
    if VSCODE_STORAGE.exists(): agents.append("copilot")
    if OPENCODE_DB.exists(): agents.append("opencode")
    if _hermes_dbs(): agents.append("hermes")
    # if OLLAMA_DIR.exists(): agents.append("ollama")
    return agents

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

def _scan_sessions_sync():
    sessions = []
    aliases = _load_project_aliases()

    def apply_alias(path: str) -> str:
        return aliases.get(path, path)

    # 1. Claude
    claude_history = CLAUDE_DIR / "history.jsonl"
    if claude_history.exists():
        claude_sessions = {}
        # Pre-index Claude session files to avoid recursive glob in loop
        claude_file_map = {}
        try:
            for p_dir in (CLAUDE_DIR / "projects").iterdir():
                if p_dir.is_dir():
                    for f in p_dir.glob("*.jsonl"):
                        claude_file_map[f.stem] = f
        except: pass

        try:
            with open(claude_history, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        sid = data.get("sessionId")
                        if not sid: continue
                        ts = datetime.fromtimestamp(data.get("timestamp") / 1000, tz=timezone.utc) if data.get("timestamp") else _now()
                        if sid not in claude_sessions or ts > claude_sessions[sid]["timestamp"]:
                            claude_sessions[sid] = {"id": sid, "agent": "claude", "project": apply_alias(data.get("project", "unknown")), "timestamp": ts, "display": data.get("display"), "tokens": {"input": 0, "output": 0, "cached": 0, "total": 0}, "mcp_tools": [], "has_plan": False, "plans": [], "model": None, "artifacts": []}
                    except: continue
        except: pass

        for sid, sess in list(claude_sessions.items())[:100]:
            session_file = claude_file_map.get(sid)
            if session_file:
                # Discover Claude Project Memory artifacts
                try:
                    memory_dir = session_file.parent.parent / "memory"
                    if memory_dir.exists():
                        for mf in memory_dir.glob("*.md"):
                            sess["artifacts"].append({"name": mf.name, "path": str(mf), "type": "document"})
                except: pass

                # pending_edit_tool_ids: Set[str] = set()  # quality signals (commented out)
                # prior_edit_failed = False
                try:
                    with open(session_file, "r", encoding="utf-8", errors="replace") as f:
                        for line in f:
                            try:
                                data = json.loads(line)
                            except: continue
                            if data.get("type") == "assistant":
                                msg = data.get("message", {})
                                m = msg.get("model")
                                if m and m != "<synthetic>" and not sess.get("model"):
                                    sess["model"] = m
                                usage = msg.get("usage", {})
                                if usage:
                                    sess["tokens"]["input"] += usage.get("input_tokens", 0)
                                    sess["tokens"]["output"] += usage.get("output_tokens", 0)
                                    sess["tokens"]["cached"] += usage.get("cache_read_input_tokens", 0)
                                sess["tokens"]["total"] = sess["tokens"]["input"] + sess["tokens"]["output"] + sess["tokens"]["cached"]
                                sess["cost"] = calculate_cost(sess.get("model"), sess["tokens"]["input"], sess["tokens"]["output"], sess["tokens"]["cached"])
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
                except: continue
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
        except: pass

        try:
            with open(codex_index, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        data = json.loads(line); sid = data.get("id")
                        if not sid: continue
                        ts = _aware(datetime.fromisoformat(data.get("updated_at").replace('Z', '+00:00'))) if data.get("updated_at") else _now()
                        if sid not in codex_sessions or ts > codex_sessions[sid]["timestamp"]:
                            codex_sessions[sid] = {"id": sid, "agent": "codex", "project": "unknown", "timestamp": ts, "text": data.get("thread_name"), "tokens": {"input": 0, "output": 0, "cached": 0, "total": 0}, "mcp_tools": [], "has_plan": False, "plans": [], "model": None, "artifacts": []}
                    except: continue
        except: pass
        
        # Process the 100 most recent sessions
        for sid, sess in list(codex_sessions.items())[-100:]:
            rollout_file = codex_file_map.get(sid)
            if rollout_file:
                try:
                    with open(rollout_file, "r", encoding="utf-8", errors="replace") as f:
                        for line in f:
                            try:
                                data = json.loads(line)
                            except: continue
                            if data.get("type") == "session_meta":
                                sess["project"] = apply_alias(data["payload"].get("cwd", "unknown"))
                                if not sess.get("model") and data["payload"].get("model"):
                                    sess["model"] = data["payload"].get("model")
                                if not sess.get("_provider"):
                                    sess["_provider"] = data["payload"].get("model_provider")
                            if data.get("type") == "turn_context" and not sess.get("model"):
                                sess["model"] = data.get("payload", {}).get("model")
                            if data.get("type") == "event_msg":
                                usage = data.get("payload", {}).get("info", {}).get("total_token_usage", {})
                                if usage:
                                    sess["tokens"]["input"] = max(sess["tokens"]["input"], usage.get("input_tokens", 0))
                                    sess["tokens"]["output"] = max(sess["tokens"]["output"], usage.get("output_tokens", 0))
                                    sess["tokens"]["cached"] = max(sess["tokens"]["cached"], usage.get("cached_input_tokens", 0))
                                    sess["tokens"]["total"] = sess["tokens"]["input"] + sess["tokens"]["output"] + sess["tokens"]["cached"]
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
                                        except: pass
                except: pass
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
                except: pass

            # Pre-collect all chat session IDs globally to prevent cross-dir duplicates in logs.json
            _all_chat_sids: set = set()
            for _td in (GEMINI_DIR / "tmp").glob("*"):
                _cd = _td / "chats"
                if _cd.is_dir():
                    for _cf in _cd.glob("*.json"):
                        try:
                            _all_chat_sids.add(json.loads(_cf.read_text(encoding="utf-8", errors="replace")).get("sessionId") or "")
                        except: pass
            _all_log_sids: set = set()  # tracks log-only sessions added, prevents cross-dir duplication

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
                                ts = _aware(datetime.fromisoformat(data.get("lastUpdated").replace('Z', '+00:00'))) if data.get("lastUpdated") else _now()
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
                                                    except: plan_text = f"(plan stored at {pp})"
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
                                except: pass

                                tokens["cost"] = calculate_cost(model, tokens["input"], tokens["output"], tokens["cached"])
                                sessions.append({"id": sid, "agent": effective_agent, "project": project_path, "timestamp": ts, "display": first_msg[:100], "tokens": tokens, "mcp_tools": mcp_tools, "has_plan": has_plan, "plans": plans, "model": model, "artifacts": artifacts, "cost": tokens["cost"]})
                        except: continue
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
                            if not _msgs or _lsid in _all_log_sids: continue
                            _first_msg = _msgs[0].get("message", "")
                            _last_ts_str = _session_last_ts.get(_lsid, "")
                            try: _lts = _aware(datetime.fromisoformat(_last_ts_str.replace('Z', '+00:00')))
                            except: _lts = _now()
                            _plans = []; _has_plan = False
                            _plan_dir = tmp_dir / _lsid / "plans"
                            if _plan_dir.exists():
                                for _pf in sorted(_plan_dir.glob("*.md")):
                                    try:
                                        _pt = _pf.read_text(encoding="utf-8", errors="replace")
                                        _has_plan = True
                                        _plans.append({"session_id": _lsid, "agent": "antigravity", "timestamp": _lts, "content": _pt})
                                    except: pass
                            _tkns = {"input": 0, "output": 0, "cached": 0, "total": 0, "cost": 0.0}
                            sessions.append({"id": _lsid, "agent": "antigravity", "project": project_path, "timestamp": _lts, "display": _first_msg[:100], "tokens": _tkns, "mcp_tools": [], "has_plan": _has_plan, "plans": _plans, "model": None, "artifacts": [], "cost": 0.0})
                            _all_log_sids.add(_lsid)
                    except: pass
        except: pass

    # 3b. Antigravity brain/ folder — richer per-session artifacts (task/plan/walkthrough)
    if ANTIGRAVITY_BRAIN_DIR.exists():
        for sess_dir in ANTIGRAVITY_BRAIN_DIR.iterdir():
            try:
                if not sess_dir.is_dir(): continue
                sid = sess_dir.name
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
                        except: body = ""
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
                        except: pass
                
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
                except: pass

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
                except: pass

                if not (task or plan or walkthrough or artifacts): continue
                project = apply_alias(_antigravity_infer_project((task or "") + "\n" + (plan or "")))
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
                    "tokens": {"input": 0, "output": 0, "cached": 0, "total": 0},
                    "mcp_tools": [],
                    "has_plan": bool(plan),
                    "plans": plans,
                    "model": "gemini (antigravity)",
                    "artifacts": artifacts
                })
            except: continue

    # 4. Qwen
    if QWEN_DIR.exists():
        for pd in QWEN_DIR.glob("projects/*"):
            if pd.is_dir():
                for cf in pd.glob("chats/*.jsonl"):
                    try:
                        sid = cf.stem; mcp_tools = []; has_plan = False; first_msg = ""; plans = []
                        tokens = {"input": 0, "output": 0, "cached": 0, "total": 0}
                        project_path = "unknown"; last_ts = _now(); model = None
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
                                        tokens["input"] += usage.get("input_tokens", 0); tokens["output"] += usage.get("output_tokens", 0)
                                        tokens["cached"] += usage.get("cache_read_input_tokens", 0)
                                        for item in data.get("message", {}).get("content", []):
                                            if item.get("type") == "tool_use":
                                                if item.get("name") not in mcp_tools: mcp_tools.append(item.get("name"))
                                            if item.get("type") == "thinking":
                                                t_text = item.get("thinking", "")
                                                if "plan" in t_text.lower() and len(t_text) > 100:
                                                    has_plan = True
                                                    plans.append({"session_id": sid, "agent": "qwen", "timestamp": last_ts, "content": t_text})
                                except: continue
                        tokens["total"] = tokens["input"] + tokens["output"] + tokens["cached"]
                        tokens["cost"] = calculate_cost(model, tokens["input"], tokens["output"], tokens["cached"])
                        sessions.append({"id": sid, "agent": "qwen", "project": project_path, "timestamp": last_ts, "display": first_msg[:100], "tokens": tokens, "mcp_tools": mcp_tools, "has_plan": has_plan, "plans": plans, "model": model, "artifacts": artifacts, "cost": tokens["cost"]})
                    except: continue

    # 5. Vibe
    if VIBE_DIR.exists():
        for cf in (VIBE_DIR / "logs" / "session").glob("*.json"):
            try:
                with open(cf, "r", encoding="utf-8", errors="replace") as f:
                    data = json.load(f); meta = data.get("metadata", {}); sid = meta.get("session_id")
                    if not sid: continue
                    ts = _aware(datetime.fromisoformat(meta.get("start_time"))) if meta.get("start_time") else _now()
                    stats = meta.get("stats", {})
                    tokens = {"input": stats.get("session_prompt_tokens", 0), "output": stats.get("session_completion_tokens", 0), "cached": stats.get("context_tokens", 0), "total": stats.get("session_total_llm_tokens", 0)}
                    mcp_tools = [t.get("function", {}).get("name") for t in meta.get("tools_available", []) if t.get("function", {}).get("name")]
                    model = meta.get("agent_config", {}).get("active_model")
                    project_path = apply_alias(meta.get("environment", {}).get("working_directory", "unknown"))
                    sessions.append({"id": sid, "agent": "vibe", "project": project_path, "timestamp": ts, "display": f"Vibe Session {sid[:8]}", "tokens": tokens, "mcp_tools": list(set(mcp_tools)), "has_plan": False, "plans": [], "model": model, "artifacts": []})
            except: continue

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
                except: continue

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
                        except: pass

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
                                        except: continue
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
                                            tokens["input"] += usage.get("input_tokens", 0)
                                            tokens["output"] += usage.get("output_tokens", 0)
                                            tokens["cached"] += usage.get("cache_read_input_tokens", 0)
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
                                tokens["cost"] = calculate_cost(model, tokens["input"], tokens["output"], tokens["cached"])
                                sessions.append({"id": sid, "agent": "cursor", "project": project_path, "timestamp": mtime, "display": first_msg[:100], "tokens": tokens, "mcp_tools": mcp_tools, "subagents": subagents, "has_plan": has_plan, "plans": plans, "model": model, "artifacts": artifacts, "cost": tokens["cost"]})
                            except: continue

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
                for cf in ws_folder.glob("*.json"):
                    try:
                        with open(cf, "r", encoding="utf-8", errors="replace") as f:
                            data = json.load(f); sid = cf.stem; tokens = {"input": 0, "output": 0, "cached": 0, "total": 0}
                            first_msg = ""; plans = []; model = None
                            
                            # Fallback to creation date if no requests
                            creation_ts = data.get("creationDate") or data.get("timestamp")
                            last_ts = datetime.fromtimestamp(creation_ts / 1000, tz=timezone.utc) if isinstance(creation_ts, (int, float)) else _now()
                            
                            for req in data.get("requests", []):
                                if not first_msg: first_msg = req.get("message", {}).get("text", "")
                                if req.get("modelId") and not model:
                                    model = req.get("modelId").split("/")[-1]
                                if req.get("timestamp"):
                                    ts_val = req.get("timestamp")
                                    if isinstance(ts_val, (int, float)): 
                                        req_ts = datetime.fromtimestamp(ts_val / 1000, tz=timezone.utc)
                                        if req_ts > last_ts: last_ts = req_ts
                                if "thinking" in req:
                                    tokens["total"] += req["thinking"].get("tokens", 0)
                                    t_text = req["thinking"].get("text", "")
                                    if "plan" in t_text.lower() and len(t_text) > 100:
                                        plans.append({"session_id": sid, "agent": "copilot", "timestamp": last_ts, "content": t_text})
                                if "response" in req:
                                    for part in req["response"]: tokens["total"] += part.get("tokens", 0)
                            tokens["cost"] = calculate_cost(model, tokens["input"], tokens["output"], tokens["cached"])
                            sessions.append({"id": sid, "agent": "copilot", "project": project_path, "timestamp": last_ts, "display": first_msg[:100], "tokens": tokens, "mcp_tools": [], "has_plan": len(plans) > 0, "plans": plans, "model": model, "artifacts": [], "cost": tokens["cost"]})
                    except: continue
            except: continue

    # 8. OpenCode (SQLite: session / message / part)
    if OPENCODE_DB.exists():
        try:
            # immutable=1 so we don't block the live TUI process's write lock
            uri = f"file:{OPENCODE_DB}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=1.0)
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute("SELECT id, directory, title, time_created, time_updated FROM session").fetchall()
                for srow in rows:
                    sid = srow["id"]
                    ts = datetime.fromtimestamp((srow["time_updated"] or srow["time_created"] or 0) / 1000, tz=timezone.utc)
                    tokens = {"input": 0, "output": 0, "cached": 0, "total": 0}
                    model = None
                    first_user = ""
                    mcp_tools: List[str] = []
                    has_plan = False
                    plans: List[Dict[str, Any]] = []
                    # Model + tokens from assistant messages
                    for mrow in conn.execute("SELECT data FROM message WHERE session_id=? ORDER BY time_created", (sid,)):
                        try:
                            mdata = json.loads(mrow["data"] or "{}")
                        except: continue
                        if mdata.get("role") == "assistant":
                            if not model:
                                mi = mdata.get("model") or {}
                                model = mi.get("modelID") or mi.get("providerID")
                            if mdata.get("mode") == "plan":
                                has_plan = True
                    # Parts: first user text, tool names, token totals from step-finish
                    for prow in conn.execute("SELECT data FROM part WHERE session_id=? ORDER BY time_created", (sid,)):
                        try:
                            pdata = json.loads(prow["data"] or "{}")
                        except: continue
                        ptype = pdata.get("type")
                        if ptype == "text" and not first_user:
                            txt = pdata.get("text") or ""
                            if txt: first_user = txt
                        if ptype == "tool":
                            tname = pdata.get("tool")
                            if tname and tname not in mcp_tools: mcp_tools.append(tname)
                        if ptype == "step-finish":
                            tk = pdata.get("tokens") or {}
                            tokens["input"] += tk.get("input", 0) or 0
                            tokens["output"] += tk.get("output", 0) or 0
                            cache = tk.get("cache") or {}
                            tokens["cached"] += (cache.get("read", 0) or 0) + (cache.get("write", 0) or 0)
                    tokens["total"] = tokens["input"] + tokens["output"] + tokens["cached"]
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
                        "has_plan": has_plan, "plans": plans, "model": model, "artifacts": []
                    })
            finally:
                conn.close()
        except Exception:
            pass

    # 9. Hermes Agent (SQLite: sessions / messages, pre-aggregated tokens)
    hermes_cwd_map = _hermes_cwd_by_session() if _hermes_dbs() else {}
    for db_path in _hermes_dbs():
        try:
            uri = f"file:{db_path}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=1.0)
            conn.row_factory = sqlite3.Row
            try:
                srows = conn.execute(
                    "SELECT id, source, model, parent_session_id, started_at, ended_at, "
                    "input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, "
                    "reasoning_tokens, estimated_cost_usd, actual_cost_usd, title, "
                    "billing_provider, end_reason "
                    "FROM sessions"
                ).fetchall()
                for srow in srows:
                    sid = srow["id"]
                    ts_unix = srow["ended_at"] or srow["started_at"] or 0
                    ts = datetime.fromtimestamp(ts_unix, tz=timezone.utc)
                    in_t  = srow["input_tokens"] or 0
                    out_t = srow["output_tokens"] or 0
                    reas  = srow["reasoning_tokens"] or 0
                    cached = (srow["cache_read_tokens"] or 0) + (srow["cache_write_tokens"] or 0)
                    # Hermes does NOT price reasoning_tokens (verified). Keep them
                    # separate so we can surface MiMo-style silent-waste sessions.
                    tokens = {"input": in_t, "output": out_t, "cached": cached,
                              "reasoning": reas,
                              "total": in_t + out_t + cached + reas}
                    # Anomaly: reasoning dominates output AND is non-trivial in absolute terms.
                    # Cf. MiMo thinking-mode silent-waste (Hermes issue #27325).
                    cost_anomaly = bool(reas > 5000 and reas > out_t)
                    model = srow["model"]
                    # Prefer Hermes's own cost (it knows exotic models we may not price)
                    cost = srow["actual_cost_usd"] if srow["actual_cost_usd"] is not None else srow["estimated_cost_usd"]
                    if cost is None:
                        cost = calculate_cost(model, in_t, out_t, cached, provider=srow["billing_provider"])
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
    # Security: only serve files from known agent directories
    allowed = [CLAUDE_DIR, CODEX_DIR, GEMINI_DIR, QWEN_DIR, VIBE_DIR, CURSOR_DIR, VSCODE_BASE, CURSOR_BASE]
    is_safe = False
    for a in allowed:
        try:
            if p.resolve().is_relative_to(a.resolve()):
                is_safe = True; break
        except: continue

    if not is_safe or not p.exists() or not p.is_file():
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Unauthorized or not found")

    return FileResponse(path)


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
                        except: pass
                    events.append(data)
                except: continue
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
                        except: pass
                    events.append(data)
                except: continue
        return events
    elif agent in ["gemini", "antigravity"]:
        # Antigravity brain-based session (has no .json file; synthesize from markdown artifacts)
        brain_dir = ANTIGRAVITY_BRAIN_DIR / session_id
        if agent == "antigravity" and brain_dir.is_dir():
            messages = []
            base_ts = None
            try: base_ts = brain_dir.stat().st_mtime * 1000
            except: base_ts = 0
            for i, (fname, role, label) in enumerate([
                ("task.md", "user", "User task"),
                ("implementation_plan.md", "gemini", "Implementation plan"),
                ("walkthrough.md", "gemini", "Walkthrough"),
            ]):
                fp = brain_dir / fname
                if not fp.exists(): continue
                try: body = fp.read_text(errors="ignore")
                except: continue
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
                        except: pass
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
                        except: pass
                    events.append(data)
                except: continue
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
                except: continue
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
                    except: pass
                events.append(evt)
            return events
    elif agent == "cursor":
        files = list((CURSOR_DIR / "projects").glob(f"**/agent-transcripts/{session_id}/{session_id}.jsonl"))
        if not files: return {"error": "Not found"}
        events = []
        base_ts = None
        try: base_ts = files[0].stat().st_mtime * 1000
        except: base_ts = 0
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
                except: continue
        return events
    elif agent == "copilot":
        files = list(VSCODE_STORAGE.glob(f"**/chatSessions/{session_id}.json"))
        if not files: return {"error": "Not found"}
        with open(files[0], "r", encoding="utf-8", errors="replace") as f:
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
                except: md = {}
                role_by_msg[mrow["id"]] = md.get("role") or "assistant"
            events: List[Dict[str, Any]] = []
            for prow in conn.execute("SELECT message_id, time_created, data FROM part WHERE session_id=? ORDER BY time_created", (session_id,)):
                try:
                    p = json.loads(prow["data"] or "{}")
                except: continue
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
                                except: tcs = []
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
                                            except: args = args_raw
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
        if proj not in projects:
            projects[proj] = {"name": proj.split("/")[-1], "path": proj, "session_count": 0, "agents": set(), "mcp_tools": set(), "subagent_count": 0, "plan_count": 0, "tokens": {"input": 0, "output": 0, "cached": 0, "total": 0, "cost": 0.0}, "plans": []}
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
        except: pass
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
    denom = input_tokens + cached_tokens
    if denom <= 0:
        return None
    return cached_tokens / denom


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
        day = s["timestamp"].strftime("%Y-%m-%d")
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
    except: return None
    
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
            except:
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
    except: return None

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
    except: return []
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
        except: continue
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
                except:
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
            except: continue
            name = md.stem
            description = ""
            if txt.startswith("---"):
                end = txt.find("---", 3)
                if end > 0:
                    try:
                        fm = yaml.safe_load(txt[3:end])
                        if isinstance(fm, dict) and fm.get("description"):
                            description = str(fm["description"])
                    except:
                        for line in txt[3:end].splitlines():
                            if ":" in line:
                                k, v = line.split(":", 1)
                                if k.strip().lower() == "description":
                                    description = v.strip().strip('"').strip("'")
            out.append({"name": name, "description": description[:200], "scope": scope, "agent": agent, "source": str(md)})
    return out

def _memory_preview(p: Path, scope: str, agent: str):
    try: txt = p.read_text(errors="ignore")
    except: return None
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
    except: return []
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
    except: return []
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
    except: return []
    for mp in marketplaces:
        if not mp.is_dir(): continue
        try: plugins = list(mp.iterdir())
        except: continue
        for plugin in plugins:
            if not plugin.is_dir(): continue
            try: versions = [v for v in plugin.iterdir() if v.is_dir()]
            except: continue
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
            except: continue
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
    if project:
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
