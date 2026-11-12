"""Waste detection, evaluation Tier 1 (docs/design/waste-detection.md).

Pure logic, stdlib only: per-session signal extraction from a parsed trace,
flag rules, and the `GET /waste` aggregate. main.py owns I/O (finding the
transcript, the background worker) and hands this module event iterables.

Privacy: extracted signals are counts. Tool arguments are hashed in memory
for retry detection and file paths are held in memory for re-read detection;
neither is returned or persisted.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import statistics
import tempfile
import threading
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

# Bump when extraction logic changes the meaning of a stored signal. Part of
# every cache key, so a bump re-extracts lazily. Independent of
# scan_cache.CACHE_VERSION on purpose: a scanner bump must not wipe these.
WASTE_VERSION = 1

THRESHOLDS: Dict[str, float] = {
    "tool_failures_min_calls": 10,
    "tool_failures_rate": 0.20,
    "retry_loop_calls": 3,
    "rereads_calls": 5,
    "context_bloat_growth": 5.0,
    "low_cache_min_tokens": 200_000,
    "low_cache_hit_pct": 30.0,
    "no_artifact_min_calls": 30,
    "retry_run_min": 3,
    "context_growth_min_turns": 8,
}

FLAGS = ("tool_failures", "retry_loop", "rereads", "context_bloat", "low_cache", "no_artifact")

# --------------------------------------------------------------------------- #
# Static capability knowledge, from reading each agent's detail parser in
# main.py. Anything not listed here is only claimed per session when the trace
# itself shows the evidence.
# --------------------------------------------------------------------------- #

# Parsers that emit tool-call events at all. For these a session with zero
# calls really made zero calls; for the rest zero means "not recorded".
CALLS_RECORDED: Set[str] = {
    "claude", "codex", "grok", "pi", "omp", "dsh", "qoder", "kimi",
    "antigravity", "gemini", "muse", "prime", "opencode", "zcode", "hermes",
    "smallcode", "cursor",
}

# Parsers that carry an explicit per-result error flag or status:
#   claude, pi, omp: tool_result.is_error (Claude omits the key when false,
#     so absence of the key cannot be used to derive this)
#   prime: payload.is_error; opencode, zcode: payload.state.status
#   codex: item_completed.item.status / exec_command_end.exit_code
#   gemini: messages[].toolCalls[].status
# Hermes is excluded on purpose: its parser hardcodes state="completed".
ERROR_FLAG_AGENTS: Set[str] = {"claude", "pi", "omp", "prime", "opencode", "zcode", "codex", "gemini"}

# Only these get their state.status honoured (see the Hermes note above).
_STATE_STATUS_AGENTS: Set[str] = {"opencode", "zcode"}

# Codex reads files through shell `exec`; there is no structured path to key on.
NO_STRUCTURED_READS: Set[str] = {"codex"}

# Parsers that keep per-assistant-turn usage on the trace.
PER_TURN_USAGE: Set[str] = {"claude", "codex", "pi", "omp", "prime", "opencode", "zcode", "gemini", "muse"}

CAPABILITY_KEYS = ("tool_errors", "retries", "rereads", "turns", "context_growth", "cache")


def static_capabilities(agent: str) -> Dict[str, bool]:
    """Best guess before any session of `agent` has been analysed. `cache` is
    filled from the session rollups by the caller."""
    calls = agent in CALLS_RECORDED
    return {
        "tool_errors": agent in ERROR_FLAG_AGENTS,
        "retries": calls,
        "rereads": calls and agent not in NO_STRUCTURED_READS,
        "turns": True,
        "context_growth": agent in PER_TURN_USAGE,
        "cache": False,
    }


# --------------------------------------------------------------------------- #
# Tool classification
# --------------------------------------------------------------------------- #
def _norm_tool(name: Any) -> str:
    return "".join(ch for ch in str(name or "").lower() if ch.isalnum())


_READ_TOOLS = {"read", "readfile", "view", "viewfile", "cat"}
# Status polls repeat identical arguments by design; they are neither retries
# nor do they interrupt a run of real retries.
_POLL_TOOLS = {
    "wait", "waitagent", "managetask", "getcommandorsubagentoutput", "readbash",
    "bashoutput", "taskoutput", "process", "readagent", "commandstatus",
    "writestdin",  # Codex: empty writes poll a running command
}
_EDIT_TOOLS = {
    "edit", "multiedit", "write", "writefile", "writetofile", "create", "createfile",
    "strreplace", "strreplacefile", "strreplaceeditor", "strreplacebasededittool",
    "replace", "replacefilecontent", "multireplacefilecontent", "editfile",
    "applypatch", "patch", "notebookedit", "editnotebook", "searchreplace", "insert",
}
_PATH_KEYS = ("file_path", "filePath", "path", "absolute_path", "AbsolutePath", "Path",
              "target_file", "TargetFile", "notebook_path", "filename", "file")
_RANGE_KEYS = ("offset", "limit", "view_range", "StartLine", "EndLine", "start_line",
               "end_line", "line_start", "line_end", "pages")


def _path_of(args: Any) -> Optional[str]:
    if not isinstance(args, dict):
        return None
    for k in _PATH_KEYS:
        v = args.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _range_of(args: Dict[str, Any]) -> Tuple:
    return tuple((k, json.dumps(args[k], sort_keys=True, default=str)) for k in _RANGE_KEYS if k in args)


def _classify(name: str, args: Any) -> str:
    n = _norm_tool(name)
    if n == "strreplaceeditor" and isinstance(args, dict) and args.get("command") == "view":
        return "read"
    if n in _READ_TOOLS:
        return "read"
    if n in _EDIT_TOOLS:
        return "edit"
    return "other"


def arg_hash(args: Any) -> Optional[str]:
    """Stable digest of a call's arguments: canonical JSON with sorted keys.
    JSON-looking strings are parsed first so key order inside them does not
    matter. Only the digest leaves this function."""
    if args is None:
        return None
    if isinstance(args, str):
        s = args.strip()
        if s[:1] in ("{", "["):
            try:
                args = json.loads(s)
            except ValueError:
                pass
    if isinstance(args, str):
        blob = args
    else:
        blob = json.dumps(args, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8", "replace")).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# Usage helpers
# --------------------------------------------------------------------------- #
def _int(v: Any) -> int:
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def prompt_size(u: Any) -> int:
    """Tokens the model read for one turn: the context size, cached or not.
    `input_tokens` alone is the uncached remainder for Anthropic-style usage
    and would make context growth meaningless under caching."""
    if not isinstance(u, dict):
        return 0
    if "prompt_tokens" in u:
        return _int(u.get("prompt_tokens"))
    if "cached_input_tokens" in u:  # OpenAI/Codex: input is already gross
        return _int(u.get("input_tokens"))
    if "input_tokens" in u:  # Anthropic
        return (_int(u.get("input_tokens")) + _int(u.get("cache_read_input_tokens"))
                + _int(u.get("cache_creation_input_tokens")))
    total = _int(u.get("input")) + _int(u.get("cacheRead")) + _int(u.get("cacheWrite"))
    cache = u.get("cache")
    if isinstance(cache, dict):  # OpenCode/ZCode step tokens
        total += _int(cache.get("read")) + _int(cache.get("write"))
    total += _int(u.get("cached")) + _int(u.get("cache_creation"))  # Muse
    return total


def _context_growth(turns: List[int]) -> Optional[float]:
    if len(turns) < THRESHOLDS["context_growth_min_turns"]:
        return None
    q = len(turns) // 4
    first = sum(turns[:q]) / q
    last = sum(turns[-q:]) / q
    if first <= 0:
        return None
    return round(last / first, 2)


def cache_hit_pct(session: Dict[str, Any]) -> Optional[float]:
    """Same formula as /analytics: cumulative cache reads over input + reads."""
    t = session.get("tokens") or {}
    cached = _int(t.get("_cached_sum")) or _int(t.get("cached"))
    denom = _int(t.get("input")) + cached
    if denom <= 0:
        return None
    return round(cached / denom * 100, 1)


# --------------------------------------------------------------------------- #
# Detail normalization
# --------------------------------------------------------------------------- #
# Harnesses that wrap the real prompt in a tag (Cursor/Grok, Cline).
_SYSTEM_TAG_ALLOW = ("<user_query", "<user_input")
_CLOSED_TAG = re.compile(r"<([A-Za-z][\w\-]*)[^>]*>.*?</\1>", re.S)


def _is_real_user_text(txt: Any) -> bool:
    """A typed prompt, not injected markup. Closed tag spans (system
    reminders, command echoes, environment context) are stripped first, so a
    prompt that follows injected context in the same message still counts."""
    if not isinstance(txt, str):
        return False
    t = txt[:50_000].strip()
    if not t:
        return False
    if any(tag in t for tag in _SYSTEM_TAG_ALLOW):
        return True
    rest = _CLOSED_TAG.sub("", t).strip()
    if not rest or rest.startswith("<"):
        return False
    if rest.startswith("[Request interrupted") or rest.startswith("# AGENTS.md"):
        return False
    return True


def _gemini_events(msgs: List[Any]) -> List[Dict[str, Any]]:
    """Gemini chat messages to normalized events. Not summaries.normalize_detail:
    that one marks `cancelled` tool calls as errors and drops per-turn tokens."""
    out: List[Dict[str, Any]] = []
    for i, m in enumerate(msgs):
        if not isinstance(m, dict):
            continue
        mtype = m.get("type")
        if mtype == "user":
            content = m.get("content")
            if isinstance(content, list):
                content = " ".join(str(b.get("text") or "") for b in content if isinstance(b, dict))
            out.append({"type": "user", "payload": {"content": content or ""}})
        elif mtype == "gemini":
            ev: Dict[str, Any] = {"type": "assistant", "payload": {}, "messageID": m.get("id") or f"m{i}"}
            tok = m.get("tokens")
            if isinstance(tok, dict):
                # Gemini's prompt count already includes cached tokens.
                ev["usage"] = {"prompt_tokens": _int(tok.get("input"))}
            out.append(ev)
            for tc in m.get("toolCalls") or []:
                if not isinstance(tc, dict):
                    continue
                out.append({"type": "tool_call", "payload": {"tool": tc.get("name"), "args": tc.get("args"),
                                                             "callID": tc.get("id")}})
                status = tc.get("status")
                if isinstance(status, str):
                    out.append({"type": "tool_result", "payload": {"callID": tc.get("id"),
                                                                   "is_error": status == "error"}})
    return out


def events_from_detail(detail: Any) -> List[Dict[str, Any]]:
    """Flatten a get_session_detail result to an event list.

    Antigravity CLI traces come back as {"messages": [...]} but the messages
    are Claude-shaped, which summaries.normalize_detail would discard, so they
    are passed through. Everything else defers to normalize_detail."""
    if isinstance(detail, dict):
        msgs = detail.get("messages")
        if isinstance(msgs, list):
            if detail.get("kind") == "antigravity_cli":
                return [m for m in msgs if isinstance(m, dict)]
            return _gemini_events(msgs)
    try:
        from summaries import normalize_detail
    except Exception:  # pragma: no cover - summaries is always importable in the app
        return detail if isinstance(detail, list) else []
    return normalize_detail(detail)


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #
class _Acc:
    """Single-pass accumulator so a streamed transcript never sits in memory."""

    def __init__(self, agent: str):
        self.agent = agent
        self.user_turns = 0
        self.calls = 0
        self.args_seen = False
        self.errors = 0
        self.error_flag_seen = False
        self.edits = 0
        self.rereads = 0
        self.retries = 0
        self.read_paths_seen = False
        self._run_key: Optional[Tuple[str, str]] = None
        self._run_len = 0
        self._reads: Dict[str, Set[Tuple]] = {}
        self._call_ids: Set[str] = set()
        self._result_ids: Set[str] = set()
        self._usage_ids: Set[str] = set()
        self.turn_sizes: List[int] = []
        self._ag_last: Optional[Tuple[str, Optional[str]]] = None
        self._ag_last_dup = False
        # Set only by explain(): where each repeat happened. Never cached.
        self.detail: Optional[Dict[str, Any]] = None
        self.live_turn: Optional[int] = None
        self._run_meta: Optional[Dict[str, Any]] = None
        self._call_meta: Dict[str, Dict[str, Any]] = {}
        self._last_meta: Optional[Dict[str, Any]] = None

    def call(self, name: Any, args: Any, call_id: Any = None) -> None:
        if call_id:
            cid = str(call_id)
            if cid in self._call_ids:
                return  # duplicated record
            self._call_ids.add(cid)
        # Some Hermes models wrap the real call as tool_call{name, arguments}.
        if _norm_tool(name) == "toolcall" and isinstance(args, dict) and args.get("name"):
            name, args = args.get("name"), args.get("arguments")
        if isinstance(args, str) and args.strip()[:1] == "{":
            try:
                args = json.loads(args)
            except ValueError:
                pass
        self.calls += 1
        path = _path_of(args)
        meta = {"tool": str(name or ""), "path": path, "call": self.calls,
                "turn": self.live_turn if self.live_turn is not None else self.user_turns}
        self._last_meta = meta
        if self.detail is not None and call_id:
            self._call_meta[str(call_id)] = meta
        h = arg_hash(args)
        if h is not None:
            self.args_seen = True
        key = (_norm_tool(name), h) if h is not None else None
        if key is not None and key[0] in _POLL_TOOLS:
            pass
        elif key is not None and key == self._run_key:
            self._run_len += 1
        else:
            self._close_run()
            self._run_key, self._run_len = key, (1 if key is not None else 0)
            self._run_meta = meta

        kind = _classify(name, args)
        if kind == "edit":
            self.edits += 1
            if path is None:
                self._reads.clear()  # patch with unknown targets: forget all reads
            else:
                self._reads.pop(path, None)
                if self.detail is not None:
                    self.detail["edits"][path] = self.detail["edits"].get(path, 0) + 1
        elif kind == "read" and path is not None:
            self.read_paths_seen = True
            rng = _range_of(args) if isinstance(args, dict) else ()
            seen = self._reads.setdefault(path, set())
            repeat = rng in seen
            if repeat:
                self.rereads += 1
            else:
                seen.add(rng)
            if self.detail is not None:
                self.detail["reads"].setdefault(path, []).append(
                    {"call": meta["call"], "turn": meta["turn"], "repeat": repeat})

    def _close_run(self) -> None:
        if self._run_key is not None and self._run_len >= THRESHOLDS["retry_run_min"]:
            self.retries += self._run_len - 1
            if self.detail is not None and self._run_meta:
                self.detail["retries"].append({**self._run_meta, "count": self._run_len})
        self._run_key, self._run_len = None, 0

    def result(self, call_id: Any, is_error: Any) -> None:
        if call_id:
            cid = str(call_id)
            if cid in self._result_ids:
                return
            self._result_ids.add(cid)
        if isinstance(is_error, bool):
            self.error_flag_seen = True
            if is_error:
                self.errors += 1
                if self.detail is not None:
                    m = self._call_meta.get(str(call_id)) if call_id else None
                    self.detail["errors"].append(dict(m or self._last_meta or {"tool": "", "path": None, "call": None, "turn": None}))

    def usage(self, u: Any, usage_id: Any = None) -> None:
        if usage_id:
            uid = str(usage_id)
            if uid in self._usage_ids:
                return  # Claude repeats a turn's usage on continuation records
            self._usage_ids.add(uid)
        n = prompt_size(u)
        if n > 0:
            self.turn_sizes.append(n)


def _ag_echo(acc: _Acc, b: Dict[str, Any]) -> bool:
    """Antigravity's sqlite trace emits each call twice, once on the reasoning
    step and again on the execution step that follows, with no call id.
    Treat the second of each identical adjacent pair as an echo."""
    key = (_norm_tool(b.get("name")), arg_hash(b.get("input")))
    echo = key == acc._ag_last and not acc._ag_last_dup
    acc._ag_last, acc._ag_last_dup = key, echo
    return echo


def _claude_shaped(ev: Dict[str, Any], msg: Dict[str, Any], acc: _Acc) -> None:
    if ev.get("isMeta") or ev.get("isCompactSummary"):
        return
    role = msg.get("role") or ev.get("type")
    content = msg.get("content")
    if role == "user":
        has_result = False
        texts: List[str] = []
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            for b in content:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_result":
                    has_result = True
                    acc.result(b.get("tool_use_id"), b.get("is_error"))
                elif b.get("type") in (None, "text"):
                    texts.append(str(b.get("text") or ""))
        if not has_result and _is_real_user_text("\n".join(texts)):
            acc.user_turns += 1
    elif role == "assistant":
        if isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    if acc.agent == "antigravity" and not b.get("id") and _ag_echo(acc, b):
                        continue
                    acc.call(b.get("name"), b.get("input"), b.get("id"))
        if isinstance(msg.get("usage"), dict):
            acc.usage(msg["usage"], msg.get("id"))


def _normalized(ev: Dict[str, Any], acc: _Acc) -> None:
    etype = ev.get("type")
    payload = ev.get("payload")
    p = payload if isinstance(payload, dict) else {}
    if etype == "tool_call":
        state = p.get("state") if isinstance(p.get("state"), dict) else {}
        if "args" in p:
            args = p.get("args")
        elif "arguments" in p:
            args = p.get("arguments")
        else:
            args = state.get("input")
        acc.call(p.get("tool"), args, p.get("callID"))
        if acc.agent in _STATE_STATUS_AGENTS and state.get("status") in ("completed", "error"):
            acc.result(p.get("callID"), state.get("status") == "error")
    elif etype == "tool_result":
        acc.result(p.get("callID"), p.get("is_error"))
    elif etype == "tool":  # Vibe (OpenAI-style role messages)
        acc.result(p.get("tool_call_id"), None)
    elif etype == "user":
        txt = p.get("content") if "content" in p else p.get("text")
        if isinstance(txt, list):
            txt = " ".join(str(b.get("text") or "") for b in txt if isinstance(b, dict))
        if _is_real_user_text(txt):
            acc.user_turns += 1
    elif etype == "assistant" and isinstance(p.get("tool_calls"), list):  # Vibe
        for tc in p["tool_calls"]:
            if isinstance(tc, dict):
                fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
                acc.call(fn.get("name") or tc.get("name"), fn.get("arguments"), tc.get("id"))
    usage = ev.get("usage") if isinstance(ev.get("usage"), dict) else ev.get("tokens")
    if not isinstance(usage, dict) and isinstance(p.get("usage"), dict):
        usage = p["usage"]  # Muse usage events
    if isinstance(usage, dict):
        acc.usage(usage, ev.get("messageID"))


class _CodexState:
    def __init__(self) -> None:
        self.user_message = 0
        self.user_item = 0
        self.user_response = 0
        self.file_changes = 0
        self.apply_patch = 0
        self.record_sizes: List[int] = []
        self.count_sizes: List[int] = []
        self._records: Set[str] = set()
        self._last_total: Any = None


_CODEX_CALLS = {"function_call", "custom_tool_call", "local_shell_call", "web_search_call"}


def _codex(ev: Dict[str, Any], acc: _Acc, cx: _CodexState) -> None:
    etype = ev.get("type")
    p = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
    ptype = p.get("type")
    if etype == "response_item":
        if ptype in _CODEX_CALLS:
            name = p.get("name") or ptype.replace("_call", "")
            if "arguments" in p:
                args = p.get("arguments")
            elif "input" in p:
                args = p.get("input")
            else:
                args = p.get("action")
            acc.call(name, args, p.get("call_id") or p.get("id"))
            if _norm_tool(name) == "applypatch":
                cx.apply_patch += 1
        elif ptype == "message" and p.get("role") == "user":
            text = "".join(str(c.get("text") or "") for c in p.get("content") or []
                           if isinstance(c, dict) and c.get("type") == "input_text")
            if _is_real_user_text(text):
                cx.user_response += 1
    elif etype == "event_msg":
        if ptype == "user_message":
            cx.user_message += 1
        elif ptype == "item_completed":
            item = p.get("item") if isinstance(p.get("item"), dict) else {}
            itype = item.get("type")
            if itype == "UserMessage":
                cx.user_item += 1
            elif itype == "FileChange":
                cx.file_changes += 1
            status = item.get("status")
            if status in ("completed", "failed"):
                acc.result(item.get("id"), status == "failed")
        elif ptype == "exec_command_end" and isinstance(p.get("exit_code"), int):
            acc.result(p.get("call_id"), p["exit_code"] != 0)
        elif ptype == "patch_apply_end" and isinstance(p.get("success"), bool):
            acc.result(p.get("call_id"), not p["success"])
        elif ptype == "token_count":
            info = p.get("info") if isinstance(p.get("info"), dict) else {}
            total = json.dumps(info.get("total_token_usage"), sort_keys=True)
            if total != cx._last_total:  # Codex re-emits unchanged counts
                cx._last_total = total
                n = prompt_size(info.get("last_token_usage"))
                if n > 0:
                    cx.count_sizes.append(n)
    elif etype == "token_usage_record":
        rid = p.get("response_id")
        if rid and rid in cx._records:
            return
        if rid:
            cx._records.add(rid)
        n = prompt_size(p.get("usage"))
        if n > 0:
            cx.record_sizes.append(n)


def extract_signals(events: Iterable[Any], session: Dict[str, Any],
                    detail: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Per-session signal dict. A signal the trace cannot support is None.

    `events` may be a generator; it is consumed once."""
    agent = str(session.get("agent") or "")
    acc = _Acc(agent)
    acc.detail = detail
    cx = _CodexState() if agent == "codex" else None
    for ev in events:
        if not isinstance(ev, dict):
            continue
        if cx is not None:
            _codex(ev, acc, cx)
            acc.live_turn = max(cx.user_message, cx.user_item, cx.user_response)
            continue
        msg = ev.get("message")
        if isinstance(msg, dict) and ("content" in msg or "usage" in msg):
            _claude_shaped(ev, msg, acc)
        else:
            _normalized(ev, acc)
    acc._close_run()

    if cx is not None:
        acc.user_turns = cx.user_message or cx.user_item or cx.user_response
        acc.edits = max(cx.apply_patch, cx.file_changes)
        acc.turn_sizes = cx.record_sizes or cx.count_sizes

    calls_supported = agent in CALLS_RECORDED or acc.calls > 0
    args_known = acc.args_seen or (acc.calls == 0 and calls_supported)
    errors_supported = agent in ERROR_FLAG_AGENTS or acc.error_flag_seen

    return {
        "user_turns": acc.user_turns or None,
        "tool_calls": acc.calls,
        # Codex counts failed commands, and one exec call can run several.
        "tool_errors": min(acc.errors, acc.calls) if (errors_supported and calls_supported) else None,
        "retry_calls": acc.retries if args_known else None,
        "reread_calls": acc.rereads if (args_known and agent not in NO_STRUCTURED_READS) else None,
        "edit_calls": acc.edits if calls_supported else None,
        "cache_hit_pct": cache_hit_pct(session),
        "context_growth": _context_growth(acc.turn_sizes),
        "usage_turns": len(acc.turn_sizes),
    }


# --------------------------------------------------------------------------- #
# Flags
# --------------------------------------------------------------------------- #
def _cost(s: Dict[str, Any]) -> float:
    c = s.get("cost")
    return float(c) if isinstance(c, (int, float)) and not isinstance(c, bool) else 0.0


def flags_for(signals: Dict[str, Any], session: Dict[str, Any], context: Dict[str, Any]) -> List[str]:
    """Flag names for one analysed session. A flag whose input is None never
    fires. `context` carries `median_cost` and `cache_agents`."""
    t = context.get("thresholds") or THRESHOLDS
    out: List[str] = []
    calls = signals.get("tool_calls") or 0
    errs = signals.get("tool_errors")
    if errs is not None and calls >= t["tool_failures_min_calls"] and errs / calls >= t["tool_failures_rate"]:
        out.append("tool_failures")
    rc = signals.get("retry_calls")
    if rc is not None and rc >= t["retry_loop_calls"]:
        out.append("retry_loop")
    rr = signals.get("reread_calls")
    if rr is not None and rr >= t["rereads_calls"]:
        out.append("rereads")
    cg = signals.get("context_growth")
    if cg is not None and cg >= t["context_bloat_growth"]:
        out.append("context_bloat")
    if session.get("agent") in (context.get("cache_agents") or ()):
        tok = session.get("tokens") or {}
        cached = _int(tok.get("_cached_sum")) or _int(tok.get("cached"))
        hit = signals.get("cache_hit_pct")
        if (_int(tok.get("input")) + cached >= t["low_cache_min_tokens"]
                and hit is not None and hit < t["low_cache_hit_pct"]):
            out.append("low_cache")
    edits = signals.get("edit_calls")
    cost = _cost(session)
    median = context.get("median_cost") or 0.0
    if (calls >= t["no_artifact_min_calls"] and edits == 0
            and not session.get("artifacts") and not session.get("published_artifacts")
            and cost > 0 and cost >= median):
        out.append("no_artifact")
    return out


# --------------------------------------------------------------------------- #
# Aggregate
# --------------------------------------------------------------------------- #
def eligible(s: Dict[str, Any]) -> bool:
    """Stubs and sessions with neither tokens nor tool calls have nothing to
    analyse and are left out of the view entirely, so `pending` can drain.
    Tool calls alone qualify: Cursor records no usage but its traces still
    show retries and re-reads."""
    return bool(s.get("id")) and bool(s.get("agent")) and not s.get("stub") and (
        _int((s.get("tokens") or {}).get("total")) > 0 or bool(s.get("tool_counts")))


def cache_key(s: Dict[str, Any]) -> List[Any]:
    """Works for sqlite-backed agents with no transcript mtime: a session that
    gains activity changes its timestamp or its token total."""
    ts = s.get("timestamp")
    iso = ts.isoformat() if isinstance(ts, datetime) else str(ts or "")
    return [iso, _int((s.get("tokens") or {}).get("total")), WASTE_VERSION]


def cache_agents(sessions: Iterable[Dict[str, Any]]) -> Set[str]:
    """Agents whose rollups ever report cache reads."""
    out: Set[str] = set()
    for s in sessions:
        t = s.get("tokens") or {}
        if _int(t.get("_cached_sum")) or _int(t.get("cached")):
            out.add(s.get("agent"))
    return out


def _ts_iso(ts: Any) -> str:
    return ts.isoformat() if isinstance(ts, datetime) else str(ts or "")


def _ratio(n: float, d: float, nd: int = 4) -> Optional[float]:
    return round(n / d, nd) if d else None


def aggregate(items: List[Tuple[Dict[str, Any], Optional[Dict[str, Any]]]], *,
              cache_agents: Set[str], thresholds: Dict[str, float] = THRESHOLDS,
              max_sessions: int = 100) -> Dict[str, Any]:
    """Build the `GET /waste` response.

    `items` pairs each in-range session with its store entry: None while
    pending, {"failed": reason} when extraction failed (counted as analysed
    with every signal null), or the signal dict."""
    costs = [_cost(s) for s, _ in items]
    median = statistics.median(costs) if costs else 0.0
    ctx = {"median_cost": median, "cache_agents": cache_agents, "thresholds": thresholds}

    summ = {"sessions": 0, "analysed": 0, "pending": 0, "failed": 0, "total_cost": 0.0,
            "flagged_sessions": 0, "flagged_cost": 0.0, "tool_calls": 0, "tool_errors": 0,
            "retry_calls": 0, "reread_calls": 0, "no_artifact_sessions": 0}
    err_calls = 0
    err_seen = False
    turns = 0
    turn_cost = 0.0
    turn_sessions = 0
    agents: Dict[str, Dict[str, Any]] = {}
    by_flag = {f: {"flag": f, "sessions": 0, "cost": 0.0} for f in FLAGS}
    flagged_rows: List[Dict[str, Any]] = []

    for s, entry in items:
        agent = s.get("agent")
        cost = _cost(s)
        a = agents.setdefault(agent, {
            "agent": agent, "sessions": 0, "analysed": 0, "cost": 0.0,
            "flagged_sessions": 0, "flagged_cost": 0.0,
            "_err": 0, "_err_calls": 0, "_err_seen": False, "_retry": None, "_reread": None,
            "_turns": 0, "_turn_sessions": 0, "_derived": {k: False for k in CAPABILITY_KEYS}, "_ok": 0,
        })
        summ["sessions"] += 1
        summ["total_cost"] += cost
        a["sessions"] += 1
        a["cost"] += cost
        if entry is None:
            summ["pending"] += 1
            continue
        summ["analysed"] += 1
        a["analysed"] += 1
        if entry.get("failed"):
            summ["failed"] += 1
            continue
        sig = entry
        a["_ok"] += 1
        d = a["_derived"]
        calls = sig.get("tool_calls") or 0
        summ["tool_calls"] += calls
        if sig.get("tool_errors") is not None:
            d["tool_errors"] = True
            err_seen = a["_err_seen"] = True
            summ["tool_errors"] += sig["tool_errors"]
            err_calls += calls
            a["_err"] += sig["tool_errors"]
            a["_err_calls"] += calls
        if sig.get("retry_calls") is not None:
            d["retries"] = True
            summ["retry_calls"] += sig["retry_calls"]
            a["_retry"] = (a["_retry"] or 0) + sig["retry_calls"]
        if sig.get("reread_calls") is not None:
            d["rereads"] = True
            summ["reread_calls"] += sig["reread_calls"]
            a["_reread"] = (a["_reread"] or 0) + sig["reread_calls"]
        if sig.get("user_turns") is not None:
            d["turns"] = True
            turns += sig["user_turns"]
            turn_cost += cost
            turn_sessions += 1
            a["_turns"] += sig["user_turns"]
            a["_turn_sessions"] += 1
        if (sig.get("usage_turns") or 0) > 0:
            d["context_growth"] = True

        flags = flags_for(sig, s, ctx)
        if not flags:
            continue
        summ["flagged_sessions"] += 1
        summ["flagged_cost"] += cost
        a["flagged_sessions"] += 1
        a["flagged_cost"] += cost
        for f in flags:
            by_flag[f]["sessions"] += 1
            by_flag[f]["cost"] += cost
        if "no_artifact" in flags:
            summ["no_artifact_sessions"] += 1
        hit = sig.get("cache_hit_pct") if agent in cache_agents else None
        flagged_rows.append({
            "id": s.get("id"), "agent": agent, "project": s.get("project") or "",
            "timestamp": _ts_iso(s.get("timestamp")),
            "display": s.get("display") or s.get("text") or "",
            "model": s.get("model") or "", "cost": round(cost, 6),
            "tokens_total": _int((s.get("tokens") or {}).get("total")),
            "user_turns": sig.get("user_turns"), "tool_calls": calls,
            "tool_errors": sig.get("tool_errors"), "retry_calls": sig.get("retry_calls"),
            "reread_calls": sig.get("reread_calls"), "edit_calls": sig.get("edit_calls"),
            "cache_hit_pct": hit, "context_growth": sig.get("context_growth"),
            "flags": flags,
        })

    flagged_rows.sort(key=lambda r: r["cost"], reverse=True)
    n = summ["sessions"]
    summ["failure_rate"] = _ratio(summ["tool_errors"], err_calls) if err_seen else None
    if err_seen and summ["failure_rate"] is None:
        summ["failure_rate"] = 0.0  # error-capable sessions made no calls
    summ["cost_per_session"] = round(summ["total_cost"] / n, 6) if n else 0.0
    summ["turns_per_session"] = round(turns / turn_sessions, 2) if turn_sessions else 0.0
    summ["cost_per_turn"] = round(turn_cost / turns, 6) if turns else 0.0
    summ["total_cost"] = round(summ["total_cost"], 6)
    summ["flagged_cost"] = round(summ["flagged_cost"], 6)

    by_agent = []
    for a in agents.values():
        caps = dict(a["_derived"]) if a["_ok"] else static_capabilities(a["agent"])
        caps["cache"] = a["agent"] in cache_agents
        row = {
            "agent": a["agent"], "sessions": a["sessions"], "analysed": a["analysed"],
            "cost": round(a["cost"], 6),
            "flagged_sessions": a["flagged_sessions"], "flagged_cost": round(a["flagged_cost"], 6),
            "failure_rate": (_ratio(a["_err"], a["_err_calls"]) or 0.0) if a["_err_seen"] else None,
            "retry_calls": a["_retry"], "reread_calls": a["_reread"],
            "cost_per_session": round(a["cost"] / a["sessions"], 6) if a["sessions"] else 0.0,
            "turns_per_session": round(a["_turns"] / a["_turn_sessions"], 2) if a["_turn_sessions"] else None,
            "capabilities": caps,
        }
        by_agent.append(row)
    by_agent.sort(key=lambda r: r["cost"], reverse=True)
    for f in by_flag.values():
        f["cost"] = round(f["cost"], 6)

    return {
        "summary": summ,
        "by_agent": by_agent,
        "by_flag": list(by_flag.values()),
        "sessions": flagged_rows[:max_sessions],
        "thresholds": dict(thresholds),
    }


# --------------------------------------------------------------------------- #
# Signal store
# --------------------------------------------------------------------------- #
class SignalStore:
    """In-memory map of extracted signals, flushed atomically to one JSON file.

    Not scan_cache: that module hard-checks scan_cache.CACHE_VERSION, so every
    scanner bump would discard these entries. Holds counts only."""

    FLUSH_EVERY = 25

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._entries: Optional[Dict[str, Dict[str, Any]]] = None
        self._dirty = 0

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if self._entries is None:
            entries: Dict[str, Dict[str, Any]] = {}
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and data.get("version") == WASTE_VERSION \
                        and isinstance(data.get("entries"), dict):
                    entries = data["entries"]
            except (OSError, ValueError):
                pass
            self._entries = entries
        return self._entries

    @staticmethod
    def _id(agent: str, sid: str) -> str:
        return f"{agent}\x1f{sid}"

    def lookup(self, agent: str, sid: str, key: List[Any]) -> Optional[Dict[str, Any]]:
        """Signals, a {"failed": reason} marker, or None when missing or stale."""
        with self._lock:
            e = self._load().get(self._id(agent, sid))
        if not isinstance(e, dict) or e.get("k") != key:
            return None
        if e.get("failed"):
            return {"failed": e["failed"]}
        sig = e.get("s")
        return sig if isinstance(sig, dict) else None

    def put(self, agent: str, sid: str, key: List[Any], signals: Optional[Dict[str, Any]] = None,
            failed: Optional[str] = None) -> None:
        entry: Dict[str, Any] = {"k": key}
        if failed:
            entry["failed"] = failed
        else:
            entry["s"] = signals or {}
        with self._lock:
            self._load()[self._id(agent, sid)] = entry
            self._dirty += 1
            due = self._dirty >= self.FLUSH_EVERY
        if due:
            self.flush()

    def flush(self) -> None:
        with self._lock:
            if not self._dirty or self._entries is None:
                return
            blob = json.dumps({"version": WASTE_VERSION, "entries": self._entries}, separators=(",", ":"))
            self._dirty = 0
        tmp = None
        try:
            d = os.path.dirname(self.path)
            os.makedirs(d, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=d, prefix=".waste.", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(blob)
            os.replace(tmp, self.path)
            tmp = None
        except OSError:
            pass
        finally:
            if tmp is not None:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass


def explain(events: Iterable[Any], session: Dict[str, Any]) -> Dict[str, Any]:
    """Where the repeats happened in one session, for display only.

    Computed on demand and never cached: unlike the signal store this carries
    file paths, so it must not be persisted."""
    detail: Dict[str, Any] = {"reads": {}, "edits": {}, "retries": [], "errors": []}
    signals = extract_signals(events, session, detail)
    rereads = []
    for path, hits in detail["reads"].items():
        n = sum(1 for h in hits if h["repeat"])
        if n:
            rereads.append({"path": path, "name": path.replace("\\", "/").rstrip("/").split("/")[-1],
                            "reads": len(hits), "repeats": n,
                            "edits": detail["edits"].get(path, 0), "occurrences": hits[:200]})
    rereads.sort(key=lambda r: (-r["repeats"], r["path"]))
    by_tool: Dict[str, int] = {}
    for e in detail["errors"]:
        by_tool[e.get("tool") or "unknown"] = by_tool.get(e.get("tool") or "unknown", 0) + 1
    return {
        "signals": signals,
        "rereads": rereads[:50],
        "retries": sorted(detail["retries"], key=lambda r: -r["count"])[:50],
        "errors": {"total": len(detail["errors"]),
                   "by_tool": sorted(({"tool": t, "count": c} for t, c in by_tool.items()),
                                     key=lambda x: -x["count"])[:20],
                   "turns": sorted({e["turn"] for e in detail["errors"] if e.get("turn") is not None})[:100]},
    }
