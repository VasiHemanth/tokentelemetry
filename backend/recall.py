"""Cross-harness recall: project grouping, session listing and transcript search.

Everything here is pure. The caller passes the session list and a transcript
loader, so tests use fakes and the HTTP layer in main.py owns I/O. Design:
docs/design/cross-harness-recall.md.

A loader is ``load_chunks(agent, session_id) -> (chunks, source) | None`` where
``chunks`` come from ``summaries.build_chunks`` and ``source`` is ``"live"`` or
``"archive"``. ``None`` means the transcript could not be read.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import summaries
from redact import redact
from tt_paths import canonical_project

UNASSIGNED = "Antigravity / unassigned"
MAX_CHUNKS_PER_SESSION = 20000
DEFAULT_BUDGET_S = 20.0
TITLE_MAX = 160
SNIPPET_MAX = 600
# How much of each tool result recall indexes (summaries keep one line).
RESULT_CHARS = 8000
CHUNK_KINDS = ("user", "assistant", "tool", "result")

# Fallback fold for worktree paths whose .git file is gone (deleted worktree)
# or that canonical_repo cannot resolve. Matches the worktree root or any
# subdirectory of it.
_WORKTREE_RE = re.compile(r"/(?:\.claude/worktrees|\.codex/worktrees|\.grok/worktrees|\.worktrees)/[^/]+(?:/.*)?$")
_KEY_BEGIN = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_KEY_END = re.compile(r"-----END [A-Z ]*PRIVATE KEY-----")
_BUDGET_CHECK_EVERY = 2000

# Set by main.py to `canonical_repo`, the same worktree-to-repo fold the
# /projects cards use, so both pages agree on what a project is. Tests leave it
# None and get the path-only fold.
repo_resolver: Optional[Callable[[str], str]] = None
_PHRASE_RE = re.compile(r'"([^"]+)"')

Loader = Callable[[str, str], Optional[Tuple[List[Dict[str, Any]], str]]]

MODES = ("keyword", "semantic", "hybrid")
RRF_K = 60
# Bump when the chunking or embedding input changes so old vectors go stale.
INDEX_VERSION = 1


@dataclass
class Semantic:
    """Callables search() uses for vector ranking. Built by the HTTP layer so
    this module stays free of I/O.

    ``is_current(agent, id, fingerprint)`` says whether the stored vectors for a
    session match its current chunks. ``rank(query, allowed)`` returns
    ``(agent, id, idx, cosine)`` for the best chunks among ``allowed`` sessions.
    """
    model: str
    is_current: Callable[[str, str, str], bool]
    rank: Callable[[str, set], List[Tuple[str, str, int, float]]]


# ---------------------------------------------------------------- projects

def project_key(path: Optional[str], unassigned: str = UNASSIGNED) -> Optional[str]:
    """Grouping identity for a session's cwd, or None when it has no project."""
    if not isinstance(path, str) or not path.strip() or path == unassigned:
        return None
    canon = canonical_project(path)
    if not canon:
        return None
    if repo_resolver is not None:
        try:
            resolved = repo_resolver(canon)
        except Exception:  # noqa: BLE001 - a filesystem hiccup must not drop the session
            resolved = None
        if resolved:
            canon = canonical_project(resolved) or canon
    folded = _WORKTREE_RE.sub("", canon)
    return folded or canon


def project_name(key: Optional[str]) -> Optional[str]:
    if not key:
        return None
    return key.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] or key


def match_project(keys: Iterable[str], query: Optional[str]) -> Optional[str]:
    """Resolve a user-supplied project string to one of ``keys``.

    Order: exact key, basename equal (case-insensitive), basename substring.
    Within a tier the first key wins, so pass keys newest-activity first.
    """
    if not query or not query.strip():
        return None
    q = query.strip()
    ql = q.lower()
    keys = [k for k in keys if k]
    canon_q = canonical_project(q)
    for k in keys:
        if k == q or k == canon_q:
            return k
    for k in keys:
        if (project_name(k) or "").lower() == ql:
            return k
    for k in keys:
        if ql in (project_name(k) or "").lower():
            return k
    return None


# ---------------------------------------------------------------- codex

_CODEX_INJECTED = ("# AGENTS.md instructions", "<environment_context>", "<user_instructions>",
                   "<permissions instructions>")

def _codex_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    parts: List[str] = []
    for b in content or []:
        if isinstance(b, dict) and isinstance(b.get("text"), str):
            parts.append(b["text"])
    return "\n".join(p for p in parts if p)


def codex_to_message_events(events: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rewrite Codex rollout records into the message shape ``build_chunks`` reads.

    Codex stores turns as ``response_item`` records (``message``,
    ``function_call``, ``custom_tool_call``, their ``*_output`` and
    ``reasoning``), none of which match the ``message.{role,content}`` shape
    the chunker understands, so a Codex trace otherwise yields no chunks at
    all. ``event_msg`` records mirror the same content and are skipped.
    """
    out: List[Dict[str, Any]] = []

    def msg(role: str, content: Any) -> None:
        out.append({"type": role, "message": {"role": role, "content": content}})

    for ev in events:
        if not isinstance(ev, dict) or ev.get("type") != "response_item":
            continue
        p = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
        kind = p.get("type")
        if kind == "message":
            role = p.get("role")
            if role in ("user", "assistant"):
                text = _codex_text(p.get("content"))
                # Codex injects AGENTS.md and environment context as user
                # messages; they are setup, not something the user asked.
                if role == "user" and text.lstrip().startswith(_CODEX_INJECTED):
                    continue
                if text.strip():
                    msg(role, [{"type": "text", "text": text}])
        elif kind == "reasoning":
            text = _codex_text(p.get("summary")) or _codex_text(p.get("content"))
            if text.strip():
                msg("assistant", [{"type": "text", "text": text}])
        elif kind in ("function_call", "custom_tool_call", "local_shell_call"):
            raw = p.get("arguments") if kind == "function_call" else (p.get("input") or p.get("action"))
            inp: Any = raw
            if isinstance(raw, str):
                try:
                    inp = json.loads(raw)
                except ValueError:
                    inp = {"input": raw}
            if not isinstance(inp, dict):
                inp = {"input": inp}
            msg("assistant", [{"type": "tool_use", "name": p.get("name") or kind, "input": inp}])
        elif kind in ("function_call_output", "custom_tool_call_output", "local_shell_call_output"):
            body = p.get("output")
            if isinstance(body, dict):
                body = body.get("content") or body.get("output") or json.dumps(body)
            if body:
                msg("user", [{"type": "tool_result", "content": str(body)}])
    return out


# ---------------------------------------------------------------- helpers

def _to_dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        secs = value / 1000.0 if value > 1e11 else float(value)
        try:
            return datetime.fromtimestamp(secs, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    elif isinstance(value, str) and value.strip():
        s = value.strip()
        if s.endswith(("Z", "z")):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        # Naive values are local time (a bare date is a local day boundary).
        dt = dt.astimezone()
    return dt.astimezone(timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def parse_since(since: Optional[str]) -> Optional[datetime]:
    if since is None or not str(since).strip():
        return None
    dt = _to_dt(str(since))
    if dt is None:
        raise ValueError("since must be an ISO date or datetime")
    return dt


def parse_agents(agents: Any) -> Optional[set]:
    if agents is None:
        return None
    if isinstance(agents, str):
        agents = agents.split(",")
    out = {str(a).strip().lower() for a in agents if str(a).strip()}
    return out or None


def mask_key_continuations(chunks: Sequence[Dict[str, Any]]) -> Dict[int, str]:
    """Texts to use in place of chunks that continue a private key.

    ``build_chunks`` cuts long text into ~600-char pieces, so a PEM block can
    span several chunks and only the first carries the BEGIN line ``redact``
    keys on. Walk the chunks in order and mask everything from a chunk's start
    up to the END marker (or the whole chunk) while inside an open key.
    Returns ``{position: masked_text}`` for affected chunks only.
    """
    out: Dict[int, str] = {}
    open_key = False
    for i, c in enumerate(chunks):
        text = str(c.get("text") or "")
        if open_key:
            end = _KEY_END.search(text)
            if end is None:
                out[i] = "[REDACTED:private_key]"
                continue
            text = "[REDACTED:private_key]" + text[end.end():]
            out[i] = text
            open_key = False
        last_begin = None
        for m in _KEY_BEGIN.finditer(text):
            last_begin = m
        if last_begin is not None and not _KEY_END.search(text, last_begin.end()):
            open_key = True
    return out


def _redacted_texts(chunks: Sequence[Dict[str, Any]], masked: Dict[int, str]) -> List[str]:
    return [redact(masked.get(i, str(c.get("text") or ""))) for i, c in enumerate(chunks)]


def index_view(chunks: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Chunks as recall sees them (newest MAX_CHUNKS_PER_SESSION) and their
    redacted texts. The index builder and search both go through this so the
    fingerprints agree."""
    if len(chunks) > MAX_CHUNKS_PER_SESSION:
        chunks = chunks[-MAX_CHUNKS_PER_SESSION:]
    return chunks, _redacted_texts(chunks, mask_key_continuations(chunks))


def fingerprint_texts(texts: Sequence[str]) -> str:
    h = hashlib.sha256()
    h.update("\x1e".join(texts).encode("utf-8", "replace"))
    h.update(f"|{RESULT_CHARS}|{INDEX_VERSION}".encode())
    return h.hexdigest()


def session_fingerprint(chunks: List[Dict[str, Any]]) -> str:
    return fingerprint_texts(index_view(chunks)[1])


def _norm_ws(text: str) -> str:
    return " ".join(text.lower().split())


def _collapse(text: Any, limit: int) -> str:
    return " ".join(redact(text).split())[:limit]


def _num(v: Any) -> float:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def _session_cost(s: Dict[str, Any]) -> float:
    return _num(s.get("cost")) + _num(s.get("delegated_cost"))


def _meta(s: Dict[str, Any], unassigned: str = UNASSIGNED) -> Dict[str, Any]:
    key = project_key(s.get("project"), unassigned)
    last = _to_dt(s.get("timestamp") or s.get("last_ts"))
    start = _to_dt(s.get("started_at") or s.get("start_ts")) or last
    tokens = s.get("tokens")
    total = tokens.get("total") if isinstance(tokens, dict) else tokens
    return {
        "agent": s.get("agent"),
        "id": s.get("id"),
        "project_key": key,
        "project": project_name(key),
        "title": _collapse(s.get("display") or s.get("title") or "", TITLE_MAX),
        "model": s.get("model"),
        "start_ts": _iso(start),
        "last_ts": _iso(last),
        "tokens": int(_num(total)),
        "cost": round(_session_cost(s), 4),
        "source_present": True,
        "_last": last,
    }


def _public(m: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in m.items() if not k.startswith("_")}


_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


def _newest_first(metas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(metas, key=lambda m: m["_last"] or _EPOCH, reverse=True)


def _select(
    sessions: Sequence[Dict[str, Any]],
    project: Optional[str],
    agents: Any,
    since: Optional[str],
    unassigned: str = UNASSIGNED,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """Filter sessions. Returns (matched project or None, newest-first metas).
    A project filter that matches nothing yields no sessions."""
    metas = _newest_first([_meta(s, unassigned) for s in sessions if s.get("id") and s.get("agent")])
    proj = None
    if project and project.strip():
        key = match_project(dict.fromkeys(m["project_key"] for m in metas if m["project_key"]), project)
        if key is None:
            return None, []
        proj = {"key": key, "name": project_name(key)}
        metas = [m for m in metas if m["project_key"] == key]
    want = parse_agents(agents)
    if want:
        metas = [m for m in metas if (m["agent"] or "").lower() in want]
    cutoff = parse_since(since)
    if cutoff:
        metas = [m for m in metas if m["_last"] and m["_last"] >= cutoff]
    return proj, metas


# ---------------------------------------------------------------- listings

def list_projects(sessions: Sequence[Dict[str, Any]], unassigned: str = UNASSIGNED) -> Dict[str, Any]:
    groups: Dict[str, Dict[str, Any]] = {}
    for s in sessions:
        m = _meta(s, unassigned)
        key = m["project_key"]
        if not key:
            continue
        g = groups.setdefault(
            key, {"key": key, "name": m["project"], "agents": set(), "session_count": 0, "cost": 0.0, "_last": None})
        g["agents"].add(m["agent"])
        g["session_count"] += 1
        g["cost"] += _session_cost(s)
        if m["_last"] and (g["_last"] is None or m["_last"] > g["_last"]):
            g["_last"] = m["_last"]
    out = []
    for g in sorted(groups.values(), key=lambda g: g["_last"] or _EPOCH, reverse=True):
        out.append({
            "key": g["key"], "name": g["name"],
            "agents": sorted(a for a in g["agents"] if a),
            "session_count": g["session_count"],
            "cost": round(g["cost"], 4),
            "last_ts": _iso(g["_last"]),
        })
    return {"projects": out}


def list_sessions(
    sessions: Sequence[Dict[str, Any]],
    project: Optional[str] = None,
    agents: Any = None,
    since: Optional[str] = None,
    limit: int = 50,
    unassigned: str = UNASSIGNED,
) -> Dict[str, Any]:
    proj, metas = _select(sessions, project, agents, since, unassigned)
    return {
        "project": proj,
        "sessions": [_public(m) for m in metas[:limit]],
        "total": len(metas),
    }


# ---------------------------------------------------------------- search

def parse_query(q: str) -> Tuple[List[str], List[str]]:
    """Split a query into (terms, required phrases)."""
    # Whitespace is normalized so a phrase still matches across a line wrap.
    phrases = [_norm_ws(p) for p in _PHRASE_RE.findall(q) if p.strip()]
    rest = _PHRASE_RE.sub(" ", q)
    # Phrase words also count as terms so they contribute to the score.
    terms = list(dict.fromkeys(summaries._tokens(rest) + [t for p in phrases for t in summaries._tokens(p)]))
    return terms, phrases


def _title_from(chunks: List[Dict[str, Any]], fallback: str) -> str:
    for c in chunks:
        if c.get("kind") == "user" and str(c.get("text") or "").strip():
            return _collapse(c["text"], TITLE_MAX)
    return fallback


def _rrf(*rankings: Sequence[Tuple[Any, ...]]) -> Dict[Tuple[Any, ...], float]:
    """Reciprocal rank fusion over ranked key lists (best first, 1-based)."""
    out: Dict[Tuple[Any, ...], float] = {}
    for ranking in rankings:
        for rank, key in enumerate(ranking, 1):
            out[key] = out.get(key, 0.0) + 1.0 / (RRF_K + rank)
    return out


def search(
    sessions: Sequence[Dict[str, Any]],
    load_chunks: Loader,
    q: str,
    project: Optional[str] = None,
    agents: Any = None,
    since: Optional[str] = None,
    limit: int = 20,
    max_sessions: int = 60,
    budget_s: float = DEFAULT_BUDGET_S,
    clock: Callable[[], float] = time.monotonic,
    unassigned: str = UNASSIGNED,
    mode: str = "keyword",
    semantic: Optional[Semantic] = None,
) -> Dict[str, Any]:
    if mode not in MODES:
        raise ValueError("mode must be keyword, semantic or hybrid")
    if mode != "keyword" and semantic is None:
        raise ValueError("semantic search is not enabled")
    terms, phrases = parse_query(q)
    if not terms and not phrases:
        raise ValueError("q has no searchable terms")
    proj, metas = _select(sessions, project, agents, since, unassigned)
    candidates = len(metas)
    capped = metas[:max_sessions]
    use_kw = mode != "semantic"
    use_sem = mode != "keyword"

    started = clock()
    timed_out = False
    unreadable = 0
    truncated = 0
    # (meta, source, title, keyword candidates, {idx: (chunk, text)} when the
    # session's vectors are current, else None)
    opened: List[Tuple[Dict[str, Any], str, str, List[Tuple[Dict[str, Any], set, str]],
                       Optional[Dict[Any, Tuple[Dict[str, Any], str]]]]] = []
    n_chunks = 0
    df: Counter = Counter()
    q_terms = set(terms)

    for m in capped:
        if clock() - started > budget_s:
            timed_out = True
            break
        try:
            loaded = load_chunks(m["agent"], m["id"])
        except Exception:  # noqa: BLE001 - one bad transcript must not fail the search
            loaded = None
        if loaded is None:
            unreadable += 1
            continue
        chunks, source = loaded
        title = _title_from(chunks, m["title"])
        if len(chunks) > MAX_CHUNKS_PER_SESSION:
            chunks = chunks[-MAX_CHUNKS_PER_SESSION:]
            truncated += 1
        masked = mask_key_continuations(chunks)
        sem_view: Optional[Dict[Any, Tuple[Dict[str, Any], str]]] = None
        if use_sem and semantic is not None:
            texts = _redacted_texts(chunks, masked)
            try:
                current = bool(semantic.is_current(m["agent"], m["id"], fingerprint_texts(texts)))
            except Exception:  # noqa: BLE001 - an unreadable index means keyword only
                current = False
            if current:
                sem_view = {c.get("idx", 0): (c, texts[i]) for i, c in enumerate(chunks)}
        cands: List[Tuple[Dict[str, Any], set, str]] = []
        for pos, c in enumerate(chunks if use_kw else ()):
            if pos and pos % _BUDGET_CHECK_EVERY == 0 and clock() - started > budget_s:
                timed_out = True
                break
            text = masked.get(pos, str(c.get("text") or ""))
            n_chunks += 1
            present = q_terms.intersection(summaries._tokens(text))
            low = _norm_ws(text) if phrases else ""
            if present or phrases:
                if phrases and not all(p in low for p in phrases):
                    for t in present:
                        df[t] += 1
                    continue
                for t in present:
                    df[t] += 1
                cands.append((c, present, text))
        opened.append((m, source, title, cands, sem_view))
        if timed_out:
            break

    def make_hit(m: Dict[str, Any], source: str, title: str, c: Dict[str, Any], text: str,
                 score: float, match: str) -> Dict[str, Any]:
        return {
            "agent": m["agent"], "id": m["id"], "project": m["project"], "title": title,
            "model": m["model"], "last_ts": m["last_ts"], "cost": m["cost"],
            "turn": c.get("turn"), "kind": c.get("kind"),
            "snippet": _collapse(text, SNIPPET_MAX),
            "score": score, "match": match, "source": source,
            "_last": m["_last"], "_idx": c.get("idx", 0),
        }

    # Keyword ranking, best first, as (hit, key).
    kw: List[Tuple[Dict[str, Any], Tuple[Any, ...]]] = []
    for m, source, title, cands, _ in opened:
        for c, present, text in cands:
            score = sum(math.log(1 + n_chunks / df[t]) for t in present)
            if score <= 0:
                if not phrases:
                    continue
                score = 0.5 * len(phrases)
            kw.append((make_hit(m, source, title, c, text, round(score, 2), "keyword"),
                       (m["agent"], m["id"], c.get("idx", 0))))

    def order(h: Dict[str, Any]) -> Tuple[Any, ...]:
        return (-h["score"], -(h["_last"] or _EPOCH).timestamp(), h["_idx"])

    kw.sort(key=lambda t: order(t[0]))

    sem_hits: List[Tuple[Dict[str, Any], Tuple[Any, ...]]] = []
    sem_error: Optional[str] = None
    indexed = [o for o in opened if o[4] is not None]
    if use_sem and semantic is not None and indexed:
        views = {(o[0]["agent"], o[0]["id"]): o for o in indexed}
        try:
            ranked = semantic.rank(q, set(views))
        except Exception as e:  # noqa: BLE001 - Ollama down must not take keyword search with it
            ranked = []
            sem_error = str(e) or e.__class__.__name__
        for agent, sid, idx, cos in sorted(ranked, key=lambda r: -r[3]):
            o = views.get((agent, sid))
            if o is None or o[4] is None or idx not in o[4]:
                continue
            c, text = o[4][idx]
            sem_hits.append((make_hit(o[0], o[1], o[2], c, text, round(float(cos), 4), "semantic"),
                             (agent, sid, idx)))

    if mode == "keyword":
        hits = [h for h, _ in kw]
    elif mode == "semantic":
        hits = [h for h, _ in sem_hits]
    else:
        fused = _rrf([k for _, k in kw], [k for _, k in sem_hits])
        pool: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
        kw_keys = {k for _, k in kw}
        sem_keys = {k for _, k in sem_hits}
        for h, k in kw + sem_hits:
            pool.setdefault(k, h)
        hits = []
        for k, h in pool.items():
            h["score"] = round(fused[k], 4)
            if k in kw_keys and k in sem_keys:
                h["match"] = "both"
            hits.append(h)
    hits.sort(key=order)
    by_agent: Counter = Counter(h["agent"] for h in hits)
    for h in hits:
        del h["_last"], h["_idx"]

    skipped = candidates - len(opened) - unreadable
    reason = "timeout" if timed_out else ("max_sessions" if candidates > len(capped) else None)
    coverage: Dict[str, Any] = {
        "candidates": candidates,
        "sessions_scanned": len(opened),
        "sessions_skipped": skipped,
        "skipped_reason": reason if skipped else None,
        "unreadable": unreadable,
        "truncated": truncated,
        "timed_out": timed_out,
        "agents_scanned": sorted({o[0]["agent"] for o in opened if o[0]["agent"]}),
    }
    if use_sem and semantic is not None:
        coverage["semantic"] = {"mode": mode, "model": semantic.model,
                                "indexed_sessions": len(indexed),
                                "unindexed_sessions": len(opened) - len(indexed)}
        if sem_error:
            # Hybrid already degraded to keyword-only hits; say why.
            coverage["semantic"]["error"] = sem_error
    else:
        coverage["semantic"] = {"mode": "keyword"}
    return {
        "query": q,
        "project": proj,
        "hits": hits[:limit],
        "by_agent": dict(by_agent),
        "coverage": coverage,
    }


# ---------------------------------------------------------------- reading

def read_session(
    meta: Optional[Dict[str, Any]],
    chunks: List[Dict[str, Any]],
    source: str,
    agent: str,
    session_id: str,
    offset: int = 0,
    limit: int = 80,
    kinds: Any = None,
    unassigned: str = UNASSIGNED,
) -> Dict[str, Any]:
    """Page through one session's chunks. ``offset`` is a chunk ``idx``."""
    m = _meta(meta, unassigned) if meta else None
    if isinstance(kinds, str):
        kinds = kinds.split(",")
    want = {k.strip().lower() for k in (kinds or []) if k.strip()}
    bad = want - set(CHUNK_KINDS)
    if bad:
        raise ValueError(f"unknown kinds: {', '.join(sorted(bad))}")
    masked = mask_key_continuations(chunks)
    pool = [(pos, c) for pos, c in enumerate(chunks)
            if c.get("idx", 0) >= offset and (not want or c.get("kind") in want)]
    page = pool[:limit]
    nxt = pool[limit][1]["idx"] if len(pool) > limit else None
    fallback_title = m["title"] if m else ""
    return {
        "agent": agent,
        "id": session_id,
        "project": m["project"] if m else None,
        "title": _title_from(chunks, fallback_title),
        "model": m["model"] if m else None,
        "cost": m["cost"] if m else None,
        "source": source,
        "total_chunks": len(chunks),
        "offset": offset,
        "next_offset": nxt,
        "chunks": [
            {"idx": c.get("idx"), "turn": c.get("turn"), "kind": c.get("kind"),
             "text": redact(masked.get(pos, c.get("text")))}
            for pos, c in page
        ],
    }
