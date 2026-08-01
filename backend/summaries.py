"""Trace summarization: condense → prompt → cache.

The condenser distills a raw trace into a small, deterministic brief (intent,
actions, errors, cost). That brief is useful on its own and is also what we
feed the LLM — never the full multi-MB trace — keeping the call cheap, fast,
and consistent across backends.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from tt_paths import data_dir

TT_HOME = data_dir()
_DB_PATH = TT_HOME / "summaries.db"
_CONFIG_PATH = TT_HOME / "summarizer.json"

# Tool names whose input names a file we should record as "touched".
_FILE_TOOLS = {
    "edit", "write", "read", "notebookedit", "create_file", "str_replace",
    "write_file", "read_file", "replace", "read_many_files",  # gemini/qwen
}
_FILE_KEYS = ("file_path", "path", "filename", "file")
_ERROR_MARKERS = ("error", "traceback", "exception", "failed", "fatal", "cannot ")


# --------------------------------------------------------------------------- #
# Detail normalization
#
# get_session_detail returns different shapes per agent: most return a flat list
# of event dicts, but gemini/antigravity return {"sessionId", "messages":[...]}.
# We flatten everything to the generic event list the condenser understands.
# --------------------------------------------------------------------------- #
def normalize_detail(detail: Any) -> List[Dict[str, Any]]:
    if isinstance(detail, list):
        return detail
    if isinstance(detail, dict):
        msgs = detail.get("messages")
        if isinstance(msgs, list):
            return _gemini_messages_to_events(msgs)
    return []


def _gemini_messages_to_events(msgs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for m in msgs:
        if not isinstance(m, dict):
            continue
        mtype = m.get("type")
        content = m.get("content")
        ts = m.get("normalized_timestamp")
        if mtype == "user":
            if isinstance(content, list):
                content = " ".join(
                    str(b.get("text") or "") for b in content if isinstance(b, dict)
                ).strip()
            out.append({"type": "user", "payload": {"content": content or ""}, "normalized_timestamp": ts})
        elif mtype == "gemini":
            if isinstance(content, str) and content.strip():
                out.append({"type": "assistant", "payload": {"content": content}, "normalized_timestamp": ts})
            for tc in (m.get("toolCalls") or []):
                if not isinstance(tc, dict):
                    continue
                out.append({
                    "type": "tool_call",
                    "payload": {"tool": tc.get("name"), "args": tc.get("args") or {}},
                    "normalized_timestamp": ts,
                })
                if tc.get("status") and tc.get("status") != "success":
                    out.append({
                        "type": "tool_result",
                        "payload": {"tool": tc.get("name"), "content": str(tc.get("result"))[:200], "is_error": True},
                        "normalized_timestamp": ts,
                    })
        # 'info' and other lifecycle messages are skipped.
    return out


# --------------------------------------------------------------------------- #
# Condenser
# --------------------------------------------------------------------------- #
def _content_of(ev: Dict[str, Any]) -> tuple[Optional[str], Any]:
    """Return (role, content) handling both trace shapes.

    Claude passes raw JSONL (``message.{role,content}``); modular providers use
    the normalized ``payload.content`` with the role implied by ``type``.
    """
    msg = ev.get("message")
    if isinstance(msg, dict):
        return msg.get("role"), msg.get("content")
    etype = ev.get("type")
    payload = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
    role = {"user": "user", "assistant": "assistant", "tool_result": "tool"}.get(etype, etype)
    return role, payload.get("content") or payload.get("text")


def _text_blocks(content: Any) -> str:
    """Flatten a string or list-of-blocks into plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict) and b.get("type") in (None, "text"):
                parts.append(str(b.get("text") or ""))
            elif isinstance(b, str):
                parts.append(b)
        return "\n".join(p for p in parts if p)
    return ""


def _file_from_input(inp: Dict[str, Any]) -> Optional[str]:
    for k in _FILE_KEYS:
        v = inp.get(k)
        if isinstance(v, str) and v:
            return v
    return None


def condense_trace(events: List[Dict[str, Any]], meta: Dict[str, Any]) -> Dict[str, Any]:
    """Distill a trace into a compact, deterministic brief."""
    intent = ""
    final_text = ""
    user_turns = 0
    tools: Counter = Counter()
    files: list[str] = []
    commands: list[str] = []
    errors: list[str] = []

    for ev in events:
        etype = ev.get("type")
        role, content = _content_of(ev)

        if role == "user":
            txt = _text_blocks(content).strip()
            # Skip tool-result echoes and system reminders that masquerade as user turns.
            if txt and not txt.startswith("<") and "tool_result" not in txt[:40]:
                user_turns += 1
                if not intent:
                    intent = txt[:600]

        elif role == "assistant":
            txt = _text_blocks(content).strip()
            if txt:
                final_text = txt[:600]
            # Claude tool_use blocks live inside assistant content.
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        _record_tool(b.get("name"), b.get("input") or {}, tools, files, commands)

        elif etype == "tool_call":
            payload = ev.get("payload") or {}
            _record_tool(payload.get("tool"), payload.get("args") or {}, tools, files, commands)

        elif etype == "tool_result" or role == "tool":
            payload = ev.get("payload") or {}
            body = _text_blocks(content) or str(payload.get("content") or "")
            low = body.lower()
            if payload.get("is_error") or any(m in low for m in _ERROR_MARKERS):
                snippet = body.strip().splitlines()[0][:160] if body.strip() else "(error)"
                if snippet and snippet not in errors:
                    errors.append(snippet)

    return {
        "intent": intent,
        "final_text": final_text,
        "user_turns": user_turns,
        "tools": dict(tools.most_common()),
        "files": _dedupe(files)[:40],
        "commands": commands[:30],
        "errors": errors[:15],
        "tokens": {
            "input": meta.get("input_tokens") or meta.get("input") or 0,
            "output": meta.get("output_tokens") or meta.get("output") or 0,
            "total": meta.get("total_tokens") or meta.get("total") or 0,
        },
        "cost": meta.get("cost") or 0.0,
        "model": meta.get("model"),
        "agent": meta.get("agent"),
        "project": meta.get("project"),
    }


def _record_tool(name: Any, inp: Dict[str, Any], tools: Counter, files: list, commands: list) -> None:
    if not name:
        return
    name = str(name)
    tools[name] += 1
    if not isinstance(inp, dict):
        return
    if name.lower() in _FILE_TOOLS:
        f = _file_from_input(inp)
        if f:
            files.append(f)
    cmd = inp.get("command")
    if isinstance(cmd, str) and cmd.strip():
        commands.append(cmd.strip().splitlines()[0][:160])


def _dedupe(items: list) -> list:
    seen, out = set(), []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


# --------------------------------------------------------------------------- #
# Prompt
# --------------------------------------------------------------------------- #
_PROMPT_HEADER = """You are summarizing one coding-agent session for an observability dashboard.
You are given a structured brief (not the full transcript). Respond with ONLY a
JSON object, no markdown fence, exactly this shape:

{
  "intent_outcome": "<1-2 sentences: what the session set out to do and whether it succeeded>",
  "actions": ["<concrete action taken>", "..."],
  "efficiency": "<1 sentence reading the token/cost picture: efficient? wasteful retries? expensive steps?>",
  "notable": ["<errors, dead-ends, course-corrections, or interesting moments>", "..."]
}

Keep it tight and factual. Base everything on the brief below.

BRIEF:
"""


def build_prompt(brief: Dict[str, Any]) -> str:
    return _PROMPT_HEADER + json.dumps(brief, indent=2, default=str)


def parse_narrative(raw: str) -> Dict[str, Any]:
    """Extract the JSON narrative from model output, tolerating stray prose/fences."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text
        text = text.lstrip("json").strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Last resort: keep the raw text as the outcome so the user sees something.
        return {"intent_outcome": raw.strip()[:800], "actions": [], "efficiency": "", "notable": []}
    return {
        "intent_outcome": str(data.get("intent_outcome") or ""),
        "actions": [str(a) for a in (data.get("actions") or []) if a],
        "efficiency": str(data.get("efficiency") or ""),
        "notable": [str(n) for n in (data.get("notable") or []) if n],
    }


# --------------------------------------------------------------------------- #
# Content hash — detects when a trace has grown so we re-summarize.
# --------------------------------------------------------------------------- #
def content_hash(session_id: str, events: List[Dict[str, Any]]) -> str:
    last_ts = ""
    if events:
        last = events[-1]
        last_ts = str(last.get("normalized_timestamp") or last.get("timestamp") or "")
    sig = f"{session_id}:{len(events)}:{last_ts}"
    return hashlib.sha1(sig.encode()).hexdigest()


# --------------------------------------------------------------------------- #
# Cache (SQLite)
# --------------------------------------------------------------------------- #
def _conn() -> sqlite3.Connection:
    TT_HOME.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """CREATE TABLE IF NOT EXISTS summaries (
                session_id   TEXT PRIMARY KEY,
                agent        TEXT,
                content_hash TEXT,
                backend      TEXT,
                model        TEXT,
                brief_json   TEXT,
                narrative_json TEXT,
                summary_cost REAL,
                generated_at TEXT
            )"""
        )
        return conn
    except Exception:
        # The DDL can fail on a corrupt DB, a read-only dir, or an incompatible
        # schema. Close the just-opened handle before propagating so repeated
        # failures don't leak file descriptors until the OS limit is hit (#52).
        conn.close()
        raise


def get_cached(session_id: str) -> Optional[Dict[str, Any]]:
    try:
        conn = _conn()
        try:
            row = conn.execute(
                "SELECT * FROM summaries WHERE session_id=?", (session_id,)
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    if not row:
        return None
    return _row_to_dict(row)


def store(
    session_id: str,
    agent: str,
    chash: str,
    backend: str,
    model: Optional[str],
    brief: Dict[str, Any],
    narrative: Dict[str, Any],
    summary_cost: float,
) -> Dict[str, Any]:
    generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn = _conn()
    try:
        conn.execute(
            """INSERT INTO summaries
               (session_id, agent, content_hash, backend, model,
                brief_json, narrative_json, summary_cost, generated_at)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(session_id) DO UPDATE SET
                 agent=excluded.agent, content_hash=excluded.content_hash,
                 backend=excluded.backend, model=excluded.model,
                 brief_json=excluded.brief_json, narrative_json=excluded.narrative_json,
                 summary_cost=excluded.summary_cost, generated_at=excluded.generated_at""",
            (
                session_id, agent, chash, backend, model,
                json.dumps(brief, default=str), json.dumps(narrative),
                summary_cost, generated_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "session_id": session_id, "agent": agent, "content_hash": chash,
        "backend": backend, "model": model, "brief": brief, "narrative": narrative,
        "summary_cost": summary_cost, "generated_at": generated_at, "stale": False,
    }


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "session_id": row["session_id"],
        "agent": row["agent"],
        "content_hash": row["content_hash"],
        "backend": row["backend"],
        "model": row["model"],
        "brief": json.loads(row["brief_json"]) if row["brief_json"] else {},
        "narrative": json.loads(row["narrative_json"]) if row["narrative_json"] else None,
        "summary_cost": row["summary_cost"],
        "generated_at": row["generated_at"],
    }


# --------------------------------------------------------------------------- #
# Config — which backend summarizes, persisted in ~/.tokentelemetry.
# --------------------------------------------------------------------------- #
def _coerce_openai_compat(raw: Any) -> Dict[str, Any]:
    """Merge a user-supplied openai_compat sub-config over the canonical
    defaults, coercing each field to its expected type. Unknown keys are
    dropped so the persisted file stays clean."""
    from summarizers.openai_compat import default_config

    defaults = default_config()
    merged = dict(defaults)
    if isinstance(raw, dict):
        for key, default in defaults.items():
            if key not in raw or raw[key] is None:
                continue
            val = raw[key]
            try:
                if isinstance(default, bool):
                    merged[key] = bool(val)
                elif isinstance(default, int) and not isinstance(default, bool):
                    merged[key] = int(val)
                elif isinstance(default, float):
                    merged[key] = float(val)
                else:
                    merged[key] = str(val)
            except (TypeError, ValueError):
                merged[key] = default
    return merged


def load_config() -> Dict[str, Any]:
    try:
        return json.loads(_CONFIG_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {"enabled": False, "backend": None, "model": None}


def save_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    TT_HOME.mkdir(parents=True, exist_ok=True)
    out: Dict[str, Any] = {
        "enabled": bool(cfg.get("enabled")),
        "backend": cfg.get("backend") or None,
        "model": cfg.get("model") or None,
    }
    # Persist the openai_compat sub-config whenever it's supplied — keeping it
    # around even when another backend is active means the user's endpoint /
    # tuning survives a backend switch.
    if cfg.get("openai_compat") is not None or out["backend"] == "openai_compat":
        out["openai_compat"] = _coerce_openai_compat(cfg.get("openai_compat"))
    _CONFIG_PATH.write_text(json.dumps(out, indent=2))
    return out
