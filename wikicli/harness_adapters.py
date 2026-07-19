#!/usr/bin/env python3
"""harness_adapters.py: per-harness session locators/parsers for session_scan.

Each adapter answers, for one coding agent's session store: which sessions
belong to <project-dir>, and what STRUCTURAL SIGNALS does each contain. The
signal schema is identical across harnesses (see Acc.result) so the
session-miner consumes one shape regardless of source.

PRIVACY BOUNDARY (design D2, BUILD-SPEC rule 3) holds for every adapter:
only tool names, file paths, error flags, timestamps, and token counts are
emitted. Message text, thinking text, prompts, and tool outputs are never
read into the result.

Codex exception (maintainer-approved 2026-07-06): Codex records its tools as
shell command strings, so path signals require parsing those strings. The
command text is tokenized IN MEMORY and only the extracted path tokens are
emitted; the command string itself never appears in any output. The same
rule covers grok's run_terminal_command arguments. This is the single spot
where command text is touched; do not extend it to transcript prose.

Store roots are module-level constants so tests can monkeypatch them
(the same fixture pattern TokenTelemetry's backend tests use).

Verified against real stores on 2026-07-06; the format notes on each adapter
say what was checked. When a harness changes its format, fix the adapter AND
its fixture in tests/.
"""

import hashlib
import json
import os
import re
import shlex
import sqlite3
import urllib.parse
from pathlib import Path

HOME = Path(os.path.expanduser("~"))

CLAUDE_PROJECTS_ROOT = HOME / ".claude" / "projects"
CODEX_SESSIONS_ROOT = HOME / ".codex" / "sessions"
OPENCODE_DB = HOME / ".local" / "share" / "opencode" / "opencode.db"
QWEN_PROJECTS_ROOT = HOME / ".qwen" / "projects"
GEMINI_TMP_ROOT = HOME / ".gemini" / "tmp"           # antigravity chats
CLINE_DB = HOME / ".cline" / "data" / "db" / "sessions.db"
GROK_SESSIONS_ROOT = HOME / ".grok" / "sessions"
COPILOT_STATE_ROOT = HOME / ".copilot" / "session-state"
HERMES_ROOT = HOME / ".hermes"
VIBE_SESSIONS_ROOT = HOME / ".vibe" / "logs" / "session"
# smallcode traces are project-local (<project>/.smallcode/traces); no root.

# How many store files an expensive locate() may probe before giving up.
# Codex keeps one global tree for every project, so attribution means opening
# files; this bounds the worst case.
PROBE_CAP = 500

_URL_RE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.I)
_EXT_TOKEN_RE = re.compile(r"^[\w.@%+-]+\.[A-Za-z0-9]{1,8}$")


# ---------------------------------------------------------------------------
# shared accumulator + path helpers
# ---------------------------------------------------------------------------

class Acc:
    """Per-session structural-signal accumulator shared by all adapters.

    Adapters call tool_event() in transcript order (loop detection relies on
    it), tokens()/error()/ts() as the format exposes them, then result().
    """

    def __init__(self):
        self.first_ts = None
        self.last_ts = None
        self.tool_counts = {}
        self.read_paths = {}
        self.file_paths = {}
        self.error_count = 0
        self.tokens = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
        self._loop_runs = {}
        self._cur_sig = None
        self._cur_len = 0

    def ts(self, value):
        if not isinstance(value, str) or not value:
            return
        if self.first_ts is None or value < self.first_ts:
            self.first_ts = value
        if self.last_ts is None or value > self.last_ts:
            self.last_ts = value

    def tokens_add(self, inp=0, out=0, cache_read=0, cache_creation=0):
        self.tokens["input"] += int(inp or 0)
        self.tokens["output"] += int(out or 0)
        self.tokens["cache_read"] += int(cache_read or 0)
        self.tokens["cache_creation"] += int(cache_creation or 0)

    def tokens_set(self, inp=0, out=0, cache_read=0, cache_creation=0):
        self.tokens = {
            "input": int(inp or 0), "output": int(out or 0),
            "cache_read": int(cache_read or 0),
            "cache_creation": int(cache_creation or 0),
        }

    def error(self):
        self.error_count += 1

    def _flush_run(self):
        if self._cur_sig is not None and self._cur_len >= 2:
            self._loop_runs[self._cur_sig] = (
                self._loop_runs.get(self._cur_sig, 0) + self._cur_len)
        self._cur_sig = None
        self._cur_len = 0

    def tool_event(self, name, paths=(), read=False, track_files=False):
        """One tool call. paths: extracted path strings (possibly empty).
        read: counts toward the re-read signal. track_files: counts toward
        file co-occurrence (read/edit/write-shaped tools)."""
        name = name or "?"
        self.tool_counts[name] = self.tool_counts.get(name, 0) + 1
        for p in paths:
            if read:
                self.read_paths[p] = self.read_paths.get(p, 0) + 1
            if track_files:
                self.file_paths[p] = self.file_paths.get(p, 0) + 1
        # Loop signature over the first path only (matches the claude scanner:
        # one signature per call). Path-less calls break any current run.
        sig = (name, paths[0]) if paths else None
        if sig is not None and sig == self._cur_sig:
            self._cur_len += 1
        else:
            self._flush_run()
            if sig is not None:
                self._cur_sig = sig
                self._cur_len = 1

    def result(self, session_id):
        self._flush_run()
        return {
            "session_id": session_id,
            "first_ts": self.first_ts,
            "last_ts": self.last_ts,
            "tool_counts": dict(self.tool_counts),
            "read_paths": dict(self.read_paths),
            "file_paths": dict(self.file_paths),
            "error_count": self.error_count,
            "tokens": self.tokens,
            "token_total": sum(self.tokens.values()),
            "loops": [
                {"tool": t, "path": p, "count": n}
                for (t, p), n in sorted(self._loop_runs.items(),
                                        key=lambda kv: -kv[1])
            ],
        }


def encode_claude_dir(project_path):
    """Claude Code's (and Qwen's) project-dir munging: every non-alphanumeric
    character in the absolute path becomes '-'. Verified against real dirs in
    both ~/.claude/projects and ~/.qwen/projects."""
    return re.sub(r"[^A-Za-z0-9]", "-", project_path)


def _looks_like_path(tok):
    if not isinstance(tok, str) or not tok or len(tok) > 512:
        return False
    if _URL_RE.match(tok):
        return False
    return "/" in tok or bool(_EXT_TOKEN_RE.match(tok))


def paths_from_value(value, base_dir=None, cap=8):
    """Harvest path-looking strings from a structured tool-args value
    (dict/list/str, recursively). Relative candidates resolve against
    base_dir when given. Returns at most cap paths, order-preserving."""
    out = []

    def walk(v):
        if len(out) >= cap:
            return
        if isinstance(v, str):
            if _looks_like_path(v) and "\n" not in v:
                p = v
                if base_dir and not os.path.isabs(p):
                    p = os.path.normpath(os.path.join(base_dir, p))
                if p not in out:
                    out.append(p)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)

    walk(value)
    return out


def paths_from_shell(cmd, workdir=None, project_dir=None, cap=8):
    """Extract path tokens from a shell command string (codex/grok).

    The string is tokenized in memory; ONLY the path tokens leave this
    function (maintainer-approved exception, see module docstring). Kept
    tokens must resolve under project_dir, or be absolute paths that exist —
    that filter is what keeps shell noise (regexes, URLs, prose args) out of
    the signals."""
    if not isinstance(cmd, str) or not cmd:
        return []
    try:
        toks = shlex.split(cmd)
    except ValueError:
        toks = cmd.split()
    out = []
    for tok in toks:
        if len(out) >= cap:
            break
        tok = tok.strip("'\";,")
        if tok.startswith("-") or not _looks_like_path(tok):
            continue
        p = tok
        if not os.path.isabs(p):
            base = workdir or project_dir
            if not base:
                continue
            p = os.path.normpath(os.path.join(base, p))
        under_project = bool(project_dir) and (
            p == project_dir or p.startswith(project_dir.rstrip("/") + "/"))
        if under_project or (os.path.isabs(p) and os.path.exists(p)):
            if p not in out:
                out.append(p)
    return out


_SHELL_READ_CMDS = {"cat", "head", "tail", "less", "more", "sed", "awk",
                    "rg", "grep", "bat", "wc", "ls"}


def _shell_is_read(cmd):
    """True when a shell command's first word is a file-reading tool, so its
    extracted paths count toward the re-read signal (same rule every
    shell-recording harness shares)."""
    if isinstance(cmd, list):
        cmd = " ".join(str(c) for c in cmd)
    if not isinstance(cmd, str) or not cmd.strip():
        return False
    return os.path.basename(cmd.strip().split()[0]) in _SHELL_READ_CMDS


def _read_verb(name, extra=()):
    n = (name or "").lower()
    return ("read" in n or "view" in n or "cat" in n or "glob" in n
            or "list" in n or n in extra)


def _write_verb(name, extra=()):
    n = (name or "").lower()
    return ("write" in n or "edit" in n or "patch" in n or "replace" in n
            or "create" in n or n in extra)


def _under(path, project_dir):
    return path == project_dir or path.startswith(project_dir.rstrip("/") + "/")


def _sqlite_ro(path):
    uri = f"file:{path}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True, timeout=1.0)
    conn.row_factory = sqlite3.Row
    return conn


def _json_file(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return json.load(fh)
    except Exception:
        return None


def _mtime_sorted(paths, limit):
    paths = [p for p in paths if p.is_file()]
    paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return paths[:limit]


# ---------------------------------------------------------------------------
# claude — ~/.claude/projects/<encoded>/<uuid>.jsonl
# Format: JSONL events; assistant events carry message.usage +
# message.content[].tool_use with structured inputs. Full signals.
# ---------------------------------------------------------------------------

_CLAUDE_FILE_TOOLS = {"Read", "Edit", "Write", "Grep", "Glob"}
_CLAUDE_PATH_KEYS = ("file_path", "path", "pattern")


def claude_locate(project_dir, limit):
    d = CLAUDE_PROJECTS_ROOT / encode_claude_dir(project_dir)
    if not d.is_dir():
        return []
    return _mtime_sorted(list(d.glob("*.jsonl")), limit)


def claude_scan(ref, project_dir):
    acc = Acc()
    sid = ref.stem
    try:
        with open(ref, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if not isinstance(d, dict):
                    continue
                if not sid and d.get("sessionId"):
                    sid = d["sessionId"]
                acc.ts(d.get("timestamp"))
                mtype = d.get("type")
                msg = d.get("message") if isinstance(d.get("message"), dict) else {}
                if mtype == "assistant":
                    usage = msg.get("usage")
                    if isinstance(usage, dict):
                        acc.tokens_add(usage.get("input_tokens"),
                                       usage.get("output_tokens"),
                                       usage.get("cache_read_input_tokens"),
                                       usage.get("cache_creation_input_tokens"))
                    for item in msg.get("content", []) or []:
                        if not isinstance(item, dict) or item.get("type") != "tool_use":
                            continue
                        name = item.get("name") or "?"
                        inp = item.get("input") or {}
                        sig = None
                        if name in _CLAUDE_FILE_TOOLS and isinstance(inp, dict):
                            for k in _CLAUDE_PATH_KEYS:
                                v = inp.get(k)
                                if isinstance(v, str) and v:
                                    sig = v
                                    break
                        acc.tool_event(
                            name, paths=[sig] if sig else (),
                            read=(name == "Read"),
                            track_files=name in ("Read", "Edit", "Write"))
                elif mtype == "user":
                    content = msg.get("content")
                    if isinstance(content, list):
                        for item in content:
                            if (isinstance(item, dict)
                                    and item.get("type") == "tool_result"
                                    and item.get("is_error")):
                                acc.error()
    except Exception:
        return None
    return acc.result(sid)


# ---------------------------------------------------------------------------
# codex — ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl (one global tree)
# Format (verified): type=session_meta payload.cwd; response_item/
# function_call name=exec_command arguments='{"cmd": "...", "workdir": ...}';
# event_msg/token_count payload.info.total_token_usage is CUMULATIVE (input
# includes cached; last event wins). Paths come from the cmd string via
# paths_from_shell (approved exception).
# ---------------------------------------------------------------------------

_CODEX_PATCH_RE = re.compile(r"\*\*\* (?:Add|Update|Delete) File: (.+)")


def _codex_meta_cwd(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for _ in range(5):
                line = fh.readline()
                if not line:
                    break
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("type") == "session_meta":
                    p = d.get("payload") or {}
                    return p.get("cwd") or (p.get("payload") or {}).get("cwd")
    except Exception:
        pass
    return None


def codex_locate(project_dir, limit):
    if not CODEX_SESSIONS_ROOT.is_dir():
        return []
    files = list(CODEX_SESSIONS_ROOT.rglob("rollout-*.jsonl"))
    files = _mtime_sorted(files, PROBE_CAP)
    out = []
    for f in files:
        cwd = _codex_meta_cwd(f)
        if cwd and _under(cwd, project_dir):
            out.append(f)
            if len(out) >= limit:
                break
    return out


def codex_scan(ref, project_dir):
    acc = Acc()
    sid = None
    last_totals = None
    workdir = None
    try:
        with open(ref, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                acc.ts(d.get("timestamp"))
                p = d.get("payload") or {}
                pt = p.get("type")
                if d.get("type") == "session_meta":
                    sid = p.get("id") or sid
                    workdir = p.get("cwd") or (p.get("payload") or {}).get("cwd")
                elif pt == "function_call":
                    name = p.get("name") or "?"
                    try:
                        args = json.loads(p.get("arguments") or "{}")
                    except Exception:
                        args = {}
                    paths, read, track = [], False, False
                    if name in ("exec_command", "shell", "local_shell"):
                        cmd = args.get("cmd") or args.get("command")
                        if isinstance(cmd, list):
                            cmd = " ".join(str(c) for c in cmd)
                        wd = args.get("workdir") or workdir
                        paths = paths_from_shell(cmd, wd, project_dir)
                        read = _shell_is_read(cmd)
                        track = read
                    elif name == "apply_patch":
                        blob = args.get("input") or args.get("patch") or ""
                        if isinstance(blob, str):
                            for m in _CODEX_PATCH_RE.finditer(blob):
                                q = m.group(1).strip()
                                if not os.path.isabs(q):
                                    q = os.path.normpath(os.path.join(
                                        workdir or project_dir, q))
                                paths.append(q)
                        track = True
                    else:
                        paths = paths_from_value(args, base_dir=workdir)
                        read = _read_verb(name)
                        track = read or _write_verb(name)
                    acc.tool_event(name, paths=paths, read=read, track_files=track)
                elif pt == "token_count":
                    info = (p.get("info") or {})
                    tot = info.get("total_token_usage")
                    if isinstance(tot, dict):
                        last_totals = tot
    except Exception:
        return None
    if last_totals:
        cached = int(last_totals.get("cached_input_tokens") or 0)
        inp = max(0, int(last_totals.get("input_tokens") or 0) - cached)
        acc.tokens_set(inp, last_totals.get("output_tokens"), cached, 0)
    if not sid:
        parts = ref.stem.split("-")
        sid = "-".join(parts[-5:]) if len(parts) >= 6 else ref.stem
    return acc.result(sid)


# ---------------------------------------------------------------------------
# opencode — ~/.local/share/opencode/opencode.db (SQLite)
# Format (verified): session(id, directory, time_created/updated epoch-ms,
# tokens_*); part.data JSON: type='tool', tool name, state.input structured
# (filePath etc.). Full signals; tokens pre-aggregated on the session row.
# ---------------------------------------------------------------------------

def opencode_locate(project_dir, limit):
    if not OPENCODE_DB.exists():
        return []
    try:
        conn = _sqlite_ro(OPENCODE_DB)
        try:
            rows = conn.execute(
                "SELECT id, directory, time_created, time_updated,"
                "       tokens_input, tokens_output, tokens_cache_read,"
                "       tokens_cache_write"
                "  FROM session ORDER BY time_updated DESC").fetchall()
        finally:
            conn.close()
    except Exception:
        return []
    out = []
    for r in rows:
        if r["directory"] and _under(r["directory"], project_dir):
            out.append(dict(r))
            if len(out) >= limit:
                break
    return out


def _epoch_iso(ms):
    try:
        import datetime as _dt
        return _dt.datetime.fromtimestamp(
            float(ms) / 1000.0, tz=_dt.timezone.utc).isoformat()
    except Exception:
        return None


def opencode_scan(ref, project_dir):
    acc = Acc()
    acc.ts(_epoch_iso(ref.get("time_created")))
    acc.ts(_epoch_iso(ref.get("time_updated")))
    acc.tokens_set(ref.get("tokens_input"), ref.get("tokens_output"),
                   ref.get("tokens_cache_read"), ref.get("tokens_cache_write"))
    try:
        conn = _sqlite_ro(OPENCODE_DB)
        try:
            rows = conn.execute(
                "SELECT data FROM part WHERE session_id=? ORDER BY id",
                (ref["id"],)).fetchall()
        finally:
            conn.close()
    except Exception:
        rows = []
    for (data,) in rows:
        try:
            d = json.loads(data)
        except Exception:
            continue
        if not isinstance(d, dict) or d.get("type") != "tool":
            continue
        name = d.get("tool") or "?"
        state = d.get("state") if isinstance(d.get("state"), dict) else {}
        inp = state.get("input") if isinstance(state.get("input"), dict) else {}
        if name == "bash":
            paths = paths_from_shell(inp.get("command"),
                                     project_dir, project_dir)
            read = _shell_is_read(inp.get("command"))
        else:
            paths = paths_from_value(inp, base_dir=project_dir)
            read = _read_verb(name)
        if state.get("status") == "error":
            acc.error()
        acc.tool_event(name, paths=paths, read=read,
                       track_files=read or _write_verb(name))
    return acc.result(ref["id"])


# ---------------------------------------------------------------------------
# qwen — ~/.qwen/projects/<claude-style-encoding>/chats/<sid>.jsonl
# Format (verified): JSONL, cwd on events; assistant message.parts[]
# .functionCall{name, args{absolute_path,...}}; usageMetadata per assistant
# event (promptTokenCount INCLUDES cachedContentTokenCount). Full signals.
# ---------------------------------------------------------------------------

def qwen_locate(project_dir, limit):
    d = QWEN_PROJECTS_ROOT / encode_claude_dir(project_dir) / "chats"
    if not d.is_dir():
        return []
    return _mtime_sorted(list(d.glob("*.jsonl")), limit)


def qwen_scan(ref, project_dir):
    acc = Acc()
    sid = ref.stem
    try:
        with open(ref, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                acc.ts(d.get("timestamp"))
                if d.get("sessionId"):
                    sid = d["sessionId"]
                m = d.get("message") if isinstance(d.get("message"), dict) else {}
                usage = d.get("usageMetadata") or m.get("usageMetadata")
                if isinstance(usage, dict):
                    cached = int(usage.get("cachedContentTokenCount") or 0)
                    prompt = int(usage.get("promptTokenCount") or 0)
                    out = (int(usage.get("candidatesTokenCount") or 0)
                           + int(usage.get("thoughtsTokenCount") or 0))
                    acc.tokens_add(max(0, prompt - cached), out, cached, 0)
                for part in (m.get("parts") or []):
                    if not isinstance(part, dict):
                        continue
                    fc = part.get("functionCall")
                    if not isinstance(fc, dict):
                        continue
                    name = fc.get("name") or "?"
                    paths = paths_from_value(fc.get("args") or {},
                                             base_dir=project_dir)
                    read = _read_verb(name, extra=("read_file",
                                                   "read_many_files"))
                    acc.tool_event(name, paths=paths, read=read,
                                   track_files=read or _write_verb(name))
    except Exception:
        return None
    return acc.result(sid)


# ---------------------------------------------------------------------------
# antigravity — ~/.gemini/tmp/<sha256(project)>/chats/*.json
# Format (verified): {sessionId, projectHash, startTime, lastUpdated,
# messages[{id,timestamp,type,content}]}. No tool calls, no usage in this
# store; the CLI's conversations/*.db is protobuf (not parsed here).
# Capability: presence/timestamps only — honest zeros elsewhere.
# ---------------------------------------------------------------------------

def antigravity_locate(project_dir, limit):
    h = hashlib.sha256(project_dir.encode()).hexdigest()
    d = GEMINI_TMP_ROOT / h / "chats"
    if not d.is_dir():
        return []
    return _mtime_sorted(list(d.glob("*.json")), limit)


def antigravity_scan(ref, project_dir):
    d = _json_file(ref)
    if not isinstance(d, dict):
        return None
    acc = Acc()
    for k in ("startTime", "lastUpdated"):
        v = d.get(k)
        acc.ts(v if isinstance(v, str) else (str(v) if v else None))
    for msg in (d.get("messages") or []):
        if isinstance(msg, dict):
            v = msg.get("timestamp")
            acc.ts(v if isinstance(v, str) else (str(v) if v else None))
    return acc.result(d.get("sessionId") or ref.stem)


# ---------------------------------------------------------------------------
# cline — ~/.cline/data/db/sessions.db + per-session messages JSON
# Format (verified): sessions(session_id, cwd, workspace_root, started_at,
# ended_at, metadata_json{usage|aggregateUsage}, messages_path). Transcript:
# {messages: [...]} with OpenAI-style assistant tool_calls. Full signals.
# ---------------------------------------------------------------------------

def cline_locate(project_dir, limit):
    if not CLINE_DB.exists():
        return []
    try:
        conn = _sqlite_ro(CLINE_DB)
        try:
            rows = conn.execute("SELECT * FROM sessions").fetchall()
        finally:
            conn.close()
    except Exception:
        return []
    out = []
    for r in rows:
        d = dict(r)
        cwd = d.get("cwd") or d.get("workspace_root") or ""
        if cwd and _under(cwd, project_dir):
            out.append(d)
    out.sort(key=lambda d: str(d.get("started_at") or ""), reverse=True)
    return out[:limit]


def _cline_usage(meta):
    for key in ("aggregateUsage", "usage"):
        u = meta.get(key)
        if isinstance(u, dict) and any(u.values()):
            return u
    return {}


def cline_scan(ref, project_dir):
    acc = Acc()
    acc.ts(str(ref.get("started_at") or "") or None)
    acc.ts(str(ref.get("ended_at") or "") or None)
    try:
        meta = json.loads(ref.get("metadata_json") or "{}")
    except Exception:
        meta = {}
    u = _cline_usage(meta if isinstance(meta, dict) else {})
    acc.tokens_set(
        u.get("inputTokens") or u.get("tokensIn"),
        u.get("outputTokens") or u.get("tokensOut"),
        u.get("cacheReadTokens") or u.get("cacheReads"),
        u.get("cacheWriteTokens") or u.get("cacheWrites"))
    mp = ref.get("messages_path")
    msgs = []
    if mp and os.path.exists(mp):
        t = _json_file(mp)
        if isinstance(t, dict):
            msgs = t.get("messages") or []
        elif isinstance(t, list):
            msgs = t
    metrics_sum = {"inputTokens": 0, "outputTokens": 0,
                   "cacheReadTokens": 0, "cacheWriteTokens": 0}
    for m in msgs:
        if not isinstance(m, dict):
            continue
        met = m.get("metrics")
        if isinstance(met, dict):
            for k in metrics_sum:
                metrics_sum[k] += int(met.get(k) or 0)
        # OpenAI-style tool_calls on the message...
        for tc in (m.get("tool_calls") or []):
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") if isinstance(tc.get("function"), dict) else tc
            name = fn.get("name") or tc.get("name") or "?"
            raw = fn.get("arguments")
            try:
                args = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except Exception:
                args = {}
            paths = paths_from_value(args, base_dir=project_dir)
            read = _read_verb(name)
            acc.tool_event(name, paths=paths, read=read,
                           track_files=read or _write_verb(name))
        # ...and Claude-style typed blocks in content (verified transcript
        # shape: content is a list of {type: thinking|text|tool_use, ...}).
        content = m.get("content")
        if isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    name = b.get("name") or "?"
                    paths = paths_from_value(b.get("input") or {},
                                             base_dir=project_dir)
                    read = _read_verb(name)
                    acc.tool_event(name, paths=paths, read=read,
                                   track_files=read or _write_verb(name))
    # DB usage rows are all-zero for some providers (observed with ollama);
    # fall back to summing per-message metrics, mirroring TT's parser.
    if sum(acc.tokens.values()) == 0 and any(metrics_sum.values()):
        acc.tokens_set(metrics_sum["inputTokens"], metrics_sum["outputTokens"],
                       metrics_sum["cacheReadTokens"],
                       metrics_sum["cacheWriteTokens"])
    return acc.result(str(ref.get("session_id")))


# ---------------------------------------------------------------------------
# grok — ~/.grok/sessions/<urlencoded-project>/<sid>/chat_history.jsonl
# Format (verified): entries role in {user, assistant, reasoning,
# tool_result, ...}; assistant entries carry tool_calls[{name, arguments}]
# where arguments for run_terminal_command hold a command string (approved
# shell extraction). No usage fields observed → tokens stay zero.
# ---------------------------------------------------------------------------

def grok_locate(project_dir, limit):
    d = GROK_SESSIONS_ROOT / urllib.parse.quote(project_dir, safe="")
    if not d.is_dir():
        return []
    hist = [p / "chat_history.jsonl" for p in d.iterdir() if p.is_dir()]
    return _mtime_sorted([p for p in hist if p.exists()], limit)


def grok_scan(ref, project_dir):
    acc = Acc()
    sid = ref.parent.name
    try:
        with open(ref, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                acc.ts(d.get("timestamp"))
                if d.get("role") == "tool_result" and d.get("is_error"):
                    acc.error()
                for tc in (d.get("tool_calls") or []):
                    if not isinstance(tc, dict):
                        continue
                    name = tc.get("name") or "?"
                    raw = tc.get("arguments")
                    try:
                        args = json.loads(raw) if isinstance(raw, str) else (raw or {})
                    except Exception:
                        args = {}
                    if name in ("run_terminal_command", "bash", "shell"):
                        cmd = args.get("command") or args.get("cmd")
                        paths = paths_from_shell(cmd, project_dir, project_dir)
                        read = _shell_is_read(cmd)
                    else:
                        paths = paths_from_value(args, base_dir=project_dir)
                        read = _read_verb(name)
                    acc.tool_event(name, paths=paths, read=read,
                                   track_files=read or _write_verb(name))
    except Exception:
        return None
    return acc.result(sid)


# ---------------------------------------------------------------------------
# copilot-cli — ~/.copilot/session-state/<sid>/events.jsonl
# Format (verified): session.start data.context.cwd; tool.execution_start
# data{toolName, arguments{...}}. No usage events observed → tokens zero.
# ---------------------------------------------------------------------------

def copilot_locate(project_dir, limit):
    if not COPILOT_STATE_ROOT.is_dir():
        return []
    out = []
    dirs = sorted(COPILOT_STATE_ROOT.iterdir(),
                  key=lambda p: p.stat().st_mtime if p.exists() else 0,
                  reverse=True)
    for sdir in dirs[:PROBE_CAP]:
        ev = sdir / "events.jsonl"
        if not ev.exists():
            continue
        cwd = None
        try:
            with open(ev, "r", encoding="utf-8", errors="replace") as fh:
                for _ in range(3):
                    line = fh.readline()
                    if not line:
                        break
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    if d.get("type") == "session.start":
                        cwd = ((d.get("data") or {}).get("context") or {}).get("cwd")
                        break
        except Exception:
            continue
        if cwd and _under(cwd, project_dir):
            out.append(ev)
            if len(out) >= limit:
                break
    return out


def copilot_scan(ref, project_dir):
    acc = Acc()
    sid = ref.parent.name
    try:
        with open(ref, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                acc.ts(d.get("timestamp"))
                if d.get("type") == "tool.execution_start":
                    data = d.get("data") or {}
                    name = data.get("toolName") or "?"
                    args = data.get("arguments") or {}
                    if name in ("bash", "run_in_terminal", "shell"):
                        cmd = args.get("command") if isinstance(args, dict) else None
                        paths = paths_from_shell(cmd, project_dir, project_dir)
                        read = _shell_is_read(cmd)
                    else:
                        paths = paths_from_value(args, base_dir=project_dir)
                        read = _read_verb(name)
                    acc.tool_event(name, paths=paths, read=read,
                                   track_files=read or _write_verb(name))
                elif d.get("type") == "tool.execution_complete":
                    if (d.get("data") or {}).get("error"):
                        acc.error()
    except Exception:
        return None
    return acc.result(sid)


# ---------------------------------------------------------------------------
# hermes — ~/.hermes/state.db (+ profiles/*/state.db), SQLite
# Format (verified): sessions(id, cwd, started_at, ended_at, input_tokens,
# output_tokens, cache_read_tokens, cache_write_tokens, ...); messages(
# session_id, role, tool_calls JSON, tool_name). Tokens pre-aggregated.
# ---------------------------------------------------------------------------

def _hermes_dbs():
    dbs = []
    root = HERMES_ROOT / "state.db"
    if root.exists():
        dbs.append(root)
    prof = HERMES_ROOT / "profiles"
    if prof.is_dir():
        for p in prof.iterdir():
            db = p / "state.db"
            if db.exists():
                dbs.append(db)
    return dbs


def hermes_locate(project_dir, limit):
    out = []
    for db in _hermes_dbs():
        try:
            conn = _sqlite_ro(db)
            try:
                rows = conn.execute(
                    "SELECT id, cwd, started_at, ended_at, input_tokens,"
                    "       output_tokens, cache_read_tokens, cache_write_tokens"
                    "  FROM sessions ORDER BY started_at DESC").fetchall()
            finally:
                conn.close()
        except Exception:
            continue
        for r in rows:
            d = dict(r)
            if d.get("cwd") and _under(d["cwd"], project_dir):
                d["_db"] = str(db)
                out.append(d)
    out.sort(key=lambda d: str(d.get("started_at") or ""), reverse=True)
    return out[:limit]


def hermes_scan(ref, project_dir):
    acc = Acc()
    acc.ts(str(ref.get("started_at") or "") or None)
    acc.ts(str(ref.get("ended_at") or "") or None)
    acc.tokens_set(ref.get("input_tokens"), ref.get("output_tokens"),
                   ref.get("cache_read_tokens"), ref.get("cache_write_tokens"))
    try:
        conn = _sqlite_ro(ref["_db"])
        try:
            rows = conn.execute(
                "SELECT role, tool_calls, tool_name FROM messages"
                " WHERE session_id=? ORDER BY id", (ref["id"],)).fetchall()
        finally:
            conn.close()
    except Exception:
        rows = []
    for r in rows:
        raw = r["tool_calls"]
        if not raw:
            continue
        try:
            tcs = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            continue
        for tc in (tcs or []):
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") if isinstance(tc.get("function"), dict) else tc
            name = fn.get("name") or tc.get("name") or r["tool_name"] or "?"
            raw_args = fn.get("arguments")
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            except Exception:
                args = {}
            paths = paths_from_value(args, base_dir=project_dir)
            read = _read_verb(name)
            acc.tool_event(name, paths=paths, read=read,
                           track_files=read or _write_verb(name))
    return acc.result(str(ref["id"]))


# ---------------------------------------------------------------------------
# smallcode — <project>/.smallcode/traces/*.json (project-local)
# Format (from TokenTelemetry's verified parser): {id, model, startedAt,
# endedAt, steps[{type:'tool_call', name, args}], tokens{prompt,completion}}.
# ---------------------------------------------------------------------------

def smallcode_locate(project_dir, limit):
    d = Path(project_dir) / ".smallcode" / "traces"
    if not d.is_dir():
        return []
    return _mtime_sorted(list(d.glob("*.json")), limit)


def smallcode_scan(ref, project_dir):
    t = _json_file(ref)
    if not isinstance(t, dict):
        return None
    acc = Acc()
    acc.ts(str(t.get("startedAt") or "") or None)
    acc.ts(str(t.get("endedAt") or "") or None)
    tok = t.get("tokens") or {}
    acc.tokens_set(tok.get("prompt"), tok.get("completion"), 0, 0)
    for step in (t.get("steps") or []):
        if not isinstance(step, dict) or step.get("type") != "tool_call":
            continue
        name = step.get("name") or "?"
        paths = paths_from_value(step.get("args") or {}, base_dir=project_dir)
        read = _read_verb(name)
        acc.tool_event(name, paths=paths, read=read,
                       track_files=read or _write_verb(name))
    return acc.result(t.get("id") or ref.stem)


# ---------------------------------------------------------------------------
# vibe — ~/.vibe/logs/session/*.json
# Format (verified): {metadata{session_id, start_time, end_time,
# environment: "<python-repr>", stats: "<python-repr>"}, messages[{role,
# content}]}. Messages carry no tool calls; stats repr holds token counts.
# Capability: tokens only. repr parsing uses ast.literal_eval (stdlib).
# ---------------------------------------------------------------------------

def _vibe_repr(v):
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        try:
            import ast
            d = ast.literal_eval(v)
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}
    return {}


def vibe_locate(project_dir, limit):
    if not VIBE_SESSIONS_ROOT.is_dir():
        return []
    out = []
    for f in _mtime_sorted(list(VIBE_SESSIONS_ROOT.glob("*.json")), PROBE_CAP):
        d = _json_file(f)
        meta = (d.get("metadata") or {}) if isinstance(d, dict) else {}
        env = _vibe_repr(meta.get("environment"))
        wd = env.get("working_directory")
        if wd and _under(wd, project_dir):
            out.append(f)
            if len(out) >= limit:
                break
    return out


def vibe_scan(ref, project_dir):
    d = _json_file(ref)
    if d is None:
        return None
    meta = (d.get("metadata") or {}) if isinstance(d, dict) else {}
    acc = Acc()
    acc.ts(str(meta.get("start_time") or "") or None)
    acc.ts(str(meta.get("end_time") or "") or None)
    stats = _vibe_repr(meta.get("stats"))
    acc.tokens_set(stats.get("session_prompt_tokens"),
                   stats.get("session_completion_tokens"), 0, 0)
    return acc.result(str(meta.get("session_id") or ref.stem))


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------
# capability: "full"   = tools + paths + tokens
#             "partial" = tools + paths, tokens missing in the store
#             "tokens" = token totals only
#             "presence" = session existence/timestamps only
ADAPTERS = {
    "claude": {"capability": "full", "locate": claude_locate, "scan": claude_scan},
    "codex": {"capability": "full", "locate": codex_locate, "scan": codex_scan},
    "opencode": {"capability": "full", "locate": opencode_locate, "scan": opencode_scan},
    "qwen": {"capability": "full", "locate": qwen_locate, "scan": qwen_scan},
    "cline": {"capability": "full", "locate": cline_locate, "scan": cline_scan},
    "hermes": {"capability": "full", "locate": hermes_locate, "scan": hermes_scan},
    "smallcode": {"capability": "full", "locate": smallcode_locate, "scan": smallcode_scan},
    "grok": {"capability": "partial", "locate": grok_locate, "scan": grok_scan},
    "copilot": {"capability": "partial", "locate": copilot_locate, "scan": copilot_scan},
    "vibe": {"capability": "tokens", "locate": vibe_locate, "scan": vibe_scan},
    "antigravity": {"capability": "presence", "locate": antigravity_locate, "scan": antigravity_scan},
}
# gemini (the discontinued CLI) is deliberately absent: legacy store, no new
# sessions since 2026-06-18. Add an adapter here + a fixture in tests/ when a
# new harness lands; docs/HARNESS-ADAPTERS.md has the checklist.
