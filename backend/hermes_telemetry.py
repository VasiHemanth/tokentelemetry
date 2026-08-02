"""Hermes telemetry: agent.log index, outcome taxonomy, aggregate rollup.

Three things live here, all pure functions over injected inputs (no import of
`main`, so tests can monkeypatch `main.HERMES_DIR` freely):

  1. A cached per-home index of ~/.hermes/logs/agent.log* keyed by session id.
     The old per-session scan was O(logfile) per session; with rotated logs and
     an all-sessions consumer that is 22 x 10MB per request. We parse every log
     file ONCE and cache the result against (name, mtime, size) of the file set.

  2. `classify_end_reason()` — the sessions.end_reason -> canonical outcome map.
     Hermes's end_reason column is open-set (the gateway's PATCH endpoint and
     the portability importer both write caller-supplied strings), so anything
     not in the table routes to "unknown" WITH the raw string preserved. It is
     never folded into "completed" — an unmapped value must read as
     "unknown: <raw>" in the UI, not as a success.

  3. `build_telemetry()` — the /hermes/telemetry payload.

Log rotation ordering is a correctness requirement: logrotate writes the OLDEST
content to the HIGHEST numeric suffix, so agent.log.2 precedes agent.log.1
precedes agent.log. A lexical sort gives the reverse and silently corrupts
model_journey and the api_calls sequence.
"""
from __future__ import annotations

import math
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

# --------------------------------------------------------------------------- #
# Outcome taxonomy
# --------------------------------------------------------------------------- #

# The seven canonical buckets. "errored" has no known upstream writer (every
# Hermes end_reason is a lifecycle boundary, not a failure signal) — it stays in
# the vocabulary so the shape is stable, but expect it to always be 0.
OUTCOME_BUCKETS: Tuple[str, ...] = (
    "completed", "interrupted", "timed_out", "continued", "reset", "errored", "unknown",
)

# raw sessions.end_reason -> canonical bucket. Extend by adding a row; every
# unlisted value deliberately falls through to "unknown".
#
# Deliberately NOT mapped, because upstream itself treats them as carrying no
# outcome ("recoverable accidental" reasons that promote_to_session_reset is
# willing to clobber, or a 7-day janitor backfill):
#   agent_close, ws_orphan_reap, orphaned_compression
END_REASON_MAP: Dict[str, str] = {
    # --- completed: an owner closed its own session on a normal exit path
    "cli_close": "completed",
    "cron_complete": "completed",
    "tui_close": "completed",
    # --- continued: work carries on in a child row (lineage link)
    "compression": "continued",
    "branched": "continued",
    "resumed_other": "continued",
    # --- reset: a boundary was deliberately drawn
    "new_session": "reset",
    "session_reset": "reset",
    "session_switch": "reset",
    "daily": "reset",
    "suspended": "reset",
    # --- timed_out: an inactivity / liveness deadline expired
    "idle": "timed_out",
    "idle_timeout": "timed_out",
    "resume_pending_expired": "timed_out",
    # --- interrupted: transport or process died under a live session
    "ws_disconnect": "interrupted",
    "tui_shutdown": "interrupted",
    "lru_evict": "interrupted",
    "compute_host_shutdown": "interrupted",
    "compute_host_orphan": "interrupted",
    "compute_host_sigterm": "interrupted",
    "compute_host_stdin_closed": "interrupted",
}

# Buckets that mean "this session reached its own end deliberately". Used for
# completion_rate; anything else (including unknown) is excluded from the
# numerator, never from the denominator.
_COMPLETED_BUCKET = "completed"


def classify_end_reason(raw: Optional[str]) -> str:
    """Map a raw sessions.end_reason to a canonical bucket.

    NULL / empty -> "unknown". Any string not in END_REASON_MAP -> "unknown"
    (the raw value is preserved by the caller and surfaced separately).
    """
    if raw is None:
        return "unknown"
    key = str(raw).strip()
    if not key:
        return "unknown"
    return END_REASON_MAP.get(key, "unknown")


def normalize_end_reason_raw(raw: Optional[str]) -> Optional[str]:
    """The raw string to keep on a session dict — None for NULL/empty."""
    if raw is None:
        return None
    key = str(raw).strip()
    return key or None


# --------------------------------------------------------------------------- #
# agent.log parsing
# --------------------------------------------------------------------------- #

_LOG_TS = r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+"
_SID = r"\[(\d{8}_\d{6}_[a-f0-9]+)\]"

API_CALL_RE = re.compile(
    _LOG_TS + r"[^\n]*?" + _SID + r"[^\n]*?"
    r"API call #(\d+): model=(\S+) provider=(\S+) in=(\d+) out=(\d+) total=(\d+) "
    r"latency=([\d.]+)s(?: cache=(\d+)/(\d+) \((\d+)%\))?"
)
TOOL_DONE_RE = re.compile(
    _LOG_TS + r"[^\n]*?" + _SID + r"[^\n]*?"
    r"tool (\S+) completed \(([\d.]+)s, (\d+) chars\)"
)
TOOL_FAIL_RE = re.compile(
    _LOG_TS + r"[^\n]*?" + _SID + r"[^\n]*?"
    r"tool (\S+) failed \(([\d.]+)s\): (.+?)$"
)


def parse_log_ts(s: str) -> Optional[datetime]:
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def log_files_in_order(home: Path) -> List[Path]:
    """Every agent.log* under `home`/logs in TRUE CHRONOLOGICAL order.

    logrotate keeps the oldest content at the highest numeric suffix, so
    agent.log.2 -> agent.log.1 -> agent.log. Compressed rotations (.gz) are
    skipped, not decompressed.
    """
    logs = Path(home) / "logs"
    try:
        if not logs.is_dir():
            return []
        entries = list(logs.iterdir())
    except OSError:
        return []
    ranked: List[Tuple[int, Path]] = []
    for p in entries:
        name = p.name
        if name == "agent.log":
            rank = 0
        elif name.startswith("agent.log."):
            suffix = name[len("agent.log."):]
            if not suffix.isdigit():
                continue  # .gz and friends: recorded nowhere, never read
            rank = int(suffix)
        else:
            continue
        try:
            if not p.is_file():
                continue
        except OSError:
            continue
        ranked.append((rank, p))
    # Highest suffix (oldest) first; unsuffixed agent.log (rank 0) last.
    ranked.sort(key=lambda t: (-t[0], t[1].name))
    return [p for _, p in ranked]


def _api_call_from(m: "re.Match[str]") -> Dict[str, Any]:
    ts = parse_log_ts(m.group(1))
    return {
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
    }


def _slot(index: Dict[str, Dict[str, List[Dict[str, Any]]]], sid: str) -> Dict[str, List[Dict[str, Any]]]:
    e = index.get(sid)
    if e is None:
        e = {"api_calls": [], "tool_calls": []}
        index[sid] = e
    return e


def parse_log_file(path: Path, index: Dict[str, Dict[str, List[Dict[str, Any]]]]) -> None:
    """Append every recognised line in `path` into `index` (keyed by session id).

    Appending in file order preserves chronology as long as files are fed in
    the order log_files_in_order() returns. We never sort by parsed timestamp:
    the log's clock is local time that parse_log_ts() stamps as UTC, so the
    timestamps are only trustworthy relative to each other within a file.
    """
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            # Cheap substring gates first — the regexes are the expensive part
            # and >99% of log lines match none of them.
            if "API call #" in line:
                m = API_CALL_RE.search(line)
                if m:
                    _slot(index, m.group(2))["api_calls"].append(_api_call_from(m))
                    continue
            if "completed (" in line:
                m = TOOL_DONE_RE.search(line)
                if m:
                    ts = parse_log_ts(m.group(1))
                    _slot(index, m.group(2))["tool_calls"].append({
                        "ts": ts.isoformat() if ts else None,
                        "tool": m.group(3),
                        "duration_s": float(m.group(4)),
                        "chars": int(m.group(5)),
                        "status": "ok",
                    })
                    continue
            if "failed (" in line:
                m = TOOL_FAIL_RE.search(line)
                if m:
                    ts = parse_log_ts(m.group(1))
                    _slot(index, m.group(2))["tool_calls"].append({
                        "ts": ts.isoformat() if ts else None,
                        "tool": m.group(3),
                        "duration_s": float(m.group(4)),
                        "status": "error",
                        "error": m.group(5)[:200],
                    })


# --------------------------------------------------------------------------- #
# Cached index
# --------------------------------------------------------------------------- #

_CACHE: Dict[str, Tuple[Tuple[Any, ...], Dict[str, Dict[str, List[Dict[str, Any]]]], List[str]]] = {}
_CACHE_LOCK = threading.Lock()

# Shared "no log lines for this session" fallback. It is handed to every caller
# that misses the index, so it must be IMMUTABLE: a single `entry["api_calls"]
# .append(...)` on the shared instance would leak one session's calls into every
# other session's fallback for the life of the process. Frozen mapping + tuples:
# mutating either raises instead of silently corrupting the index. Call sites do
# `entry.get(k) or []`, and an empty tuple is falsy, so they still get a fresh
# mutable list.
EMPTY_ENTRY: Mapping[str, Sequence[Dict[str, Any]]] = MappingProxyType(
    {"api_calls": (), "tool_calls": ()})


def _signature(files: Sequence[Path]) -> Tuple[Any, ...]:
    sig: List[Any] = []
    for p in files:
        try:
            st = p.stat()
            sig.append((p.name, st.st_mtime_ns, st.st_size))
        except OSError:
            sig.append((p.name, None, None))
    return tuple(sig)


def clear_cache() -> None:
    """Drop the whole index cache (tests; not needed in normal operation)."""
    with _CACHE_LOCK:
        _CACHE.clear()


def get_log_index(home: Path) -> Tuple[Dict[str, Dict[str, List[Dict[str, Any]]]], List[str]]:
    """({session_id: {api_calls, tool_calls}}, [filenames read]) for one home.

    Cached per home and invalidated when the (name, mtime, size) tuple over the
    home's agent.log* set changes — so a rotation, an append, or a new rotated
    file all refresh it.
    """
    home = Path(home)
    key = str(home)
    files = log_files_in_order(home)
    sig = _signature(files)
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit is not None and hit[0] == sig:
            return hit[1], hit[2]
    index: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    files_read: List[str] = []
    for path in files:
        try:
            parse_log_file(path, index)
        except Exception:
            continue
        files_read.append(path.name)
    with _CACHE_LOCK:
        _CACHE[key] = (sig, index, files_read)
    return index, files_read


def merge_indexes(
    parts: Iterable[Tuple[Optional[str], Dict[str, Dict[str, List[Dict[str, Any]]]], List[str]]]
) -> Tuple[Dict[str, Dict[str, List[Dict[str, Any]]]], List[str]]:
    """Fold per-home indexes into one. `parts` is (profile, index, files_read).

    Filenames from a profile home are labelled "<profile>/<name>" so a merged
    log_coverage.files_read stays unambiguous.
    """
    merged: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    files: List[str] = []
    for profile, index, files_read in parts:
        for sid, entry in index.items():
            slot = _slot(merged, sid)
            slot["api_calls"].extend(entry.get("api_calls") or [])
            slot["tool_calls"].extend(entry.get("tool_calls") or [])
        for name in files_read:
            files.append(f"{profile}/{name}" if profile else name)
    return merged, files


def model_journey(api_calls: Sequence[Dict[str, Any]]) -> List[str]:
    """Distinct models in temporal order (consecutive duplicates collapsed)."""
    journey: List[str] = []
    for c in api_calls:
        if not journey or journey[-1] != c.get("model"):
            journey.append(c.get("model"))
    return journey


def summarize(api_calls: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Per-session performance summary, or None when nothing was captured."""
    if not api_calls:
        return None
    total_lat = sum(c.get("latency_s") or 0.0 for c in api_calls)
    cache_pcts = [c["cache_hit_pct"] for c in api_calls if c.get("cache_hit_pct") is not None]
    return {
        "api_call_count": len(api_calls),
        "total_latency_s": round(total_lat, 2),
        "avg_latency_s": round(total_lat / len(api_calls), 2),
        "cache_hit_pct": round(sum(cache_pcts) / len(cache_pcts)) if cache_pcts else None,
        "models_used": sorted({c["model"] for c in api_calls}),
        "providers_used": sorted({c["provider"] for c in api_calls}),
        "log_coverage": "captured",
    }


# --------------------------------------------------------------------------- #
# Aggregate rollup
# --------------------------------------------------------------------------- #

# Where the dollar figure TT reports for a session came from, most authoritative
# first. `zero-marginal` is a POSITIVE finding, not a missing one: TT priced the
# session and the answer is genuinely $0 because the model runs locally or the
# model/endpoint is covered by a subscription the user already pays for. Keeping
# it out of `tt-computed` is the whole point: a confident "$0.00 · priced by
# TokenTelemetry" claims the API equivalent of those tokens is zero, when what is
# zero is the MARGINAL cost.
COST_STATUSES: Tuple[str, ...] = (
    "provider-reported", "provider-estimated", "tt-computed",
    "zero-marginal", "unpriced",
)

# Hermes's own sessions.cost_status value for "billed under a flat plan".
# Carried onto the session dict as `_hermes_cost_status` by the scan.
HERMES_INCLUDED_STATUS = "included"


# Outcome rates by model: keep the payload bounded (model names are open-set).
BY_MODEL_LIMIT = 10


def percentile(values: Sequence[float], p: float) -> Optional[float]:
    """Nearest-rank percentile. `p` in [0, 1]. None for an empty sample."""
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    k = math.ceil(p * len(vals))
    if k < 1:
        k = 1
    if k > len(vals):
        k = len(vals)
    return float(vals[k - 1])


def _usd(x: Optional[float]) -> float:
    return round(float(x or 0.0), 3)


def _secs(x: Optional[float]) -> Optional[float]:
    return None if x is None else round(float(x), 3)


def _pct(part: int, whole: int) -> float:
    return round(100.0 * part / whole, 1) if whole else 0.0


def _bucket_counts_payload(counts: Dict[str, int]) -> Dict[str, int]:
    """Only observed buckets, canonical order."""
    return {b: counts[b] for b in OUTCOME_BUCKETS if counts.get(b)}


def _outcomes(sessions: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(sessions)
    counts: Dict[str, int] = {b: 0 for b in OUTCOME_BUCKETS}
    raw_counts: Dict[str, int] = {}
    by_source: Dict[str, Dict[str, int]] = {}
    by_model: Dict[str, Dict[str, int]] = {}
    src_totals: Dict[str, int] = {}
    model_totals: Dict[str, int] = {}

    for s in sessions:
        bucket = s.get("outcome") or "unknown"
        if bucket not in counts:
            counts[bucket] = 0
        counts[bucket] += 1
        if bucket == "unknown":
            raw = s.get("outcome_raw")
            if raw:
                raw_counts[raw] = raw_counts.get(raw, 0) + 1
        src = s.get("source_subtype") or "unknown"
        src_totals[src] = src_totals.get(src, 0) + 1
        by_source.setdefault(src, {})[bucket] = by_source.setdefault(src, {}).get(bucket, 0) + 1
        mdl = s.get("model") or "unknown"
        model_totals[mdl] = model_totals.get(mdl, 0) + 1
        by_model.setdefault(mdl, {})[bucket] = by_model.setdefault(mdl, {}).get(bucket, 0) + 1

    buckets = [
        {"outcome": b, "count": counts[b], "pct": _pct(counts[b], total)}
        for b in OUTCOME_BUCKETS if counts.get(b)
    ]
    buckets.sort(key=lambda d: (-d["count"], OUTCOME_BUCKETS.index(d["outcome"])
                                if d["outcome"] in OUTCOME_BUCKETS else 99))
    unknown_raw = [{"raw": r, "count": c} for r, c in raw_counts.items()]
    unknown_raw.sort(key=lambda d: (-d["count"], d["raw"]))

    def _group(totals: Dict[str, int], grouped: Dict[str, Dict[str, int]], label: str,
               limit: Optional[int] = None):
        out = [
            {label: k, "total": totals[k], "buckets": _bucket_counts_payload(grouped[k])}
            for k in totals
        ]
        out.sort(key=lambda d: (-d["total"], str(d[label])))
        return out if limit is None else out[:limit]

    return {
        "buckets": buckets,
        "unknown_raw": unknown_raw,
        "completion_rate": round(counts.get(_COMPLETED_BUCKET, 0) / total, 3) if total else 0.0,
        # `source` is a small closed-ish set (cli / gateway / …) — never capped.
        "by_source": _group(src_totals, by_source, "source"),
        # Models are unbounded (every proxied model name is its own row). Cap at
        # the 10 largest by session count; `models_total` says how many exist so
        # the UI can say "top 10 of N" instead of implying the list is complete.
        # NOTE: with more than BY_MODEL_LIMIT models, sum(by_model[].total) is
        # LESS than session_count by construction.
        "by_model": _group(model_totals, by_model, "model", BY_MODEL_LIMIT),
        "models_total": len(model_totals),
    }


def _cost(sessions: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    confidence = {k: 0 for k in COST_STATUSES}
    usd = {k: 0.0 for k in COST_STATUSES}
    total = 0.0
    included = 0.0
    for s in sessions:
        status = s.get("cost_status")
        if status not in confidence:
            status = "unpriced"
        confidence[status] += 1
        c = s.get("cost")
        if isinstance(c, (int, float)):
            usd[status] += float(c)
            total += float(c)
            # Hermes flagged the session as billed under a flat plan. TT still
            # prices it (that's the API-equivalent number), but the user paid
            # $0 at the margin, so `total_usd` must be qualifiable.
            if s.get("_hermes_cost_status") == HERMES_INCLUDED_STATUS:
                included += float(c)
    return {
        "total_usd": round(total, 3),
        "subscription_included_usd": _usd(included),
        "confidence": confidence,
        "usd_by_confidence": {k: _usd(v) for k, v in usd.items()},
    }


def _latency(sessions: Sequence[Dict[str, Any]],
             index: Dict[str, Dict[str, List[Dict[str, Any]]]]) -> Dict[str, Any]:
    lats: List[float] = []
    captured = 0
    by_model: Dict[str, List[float]] = {}
    for s in sessions:
        calls = (index.get(s.get("id")) or EMPTY_ENTRY).get("api_calls") or []
        if calls:
            captured += 1
        for c in calls:
            lat = c.get("latency_s")
            if lat is None:
                continue
            lats.append(float(lat))
            by_model.setdefault(c.get("model") or "unknown", []).append(float(lat))

    rows = []
    for model, vals in by_model.items():
        rows.append({
            "model": model,
            "calls": len(vals),
            "avg_s": _secs(sum(vals) / len(vals)) if vals else None,
            "p95_s": _secs(percentile(vals, 0.95)),
        })
    rows.sort(key=lambda d: (-d["calls"], d["model"]))

    return {
        "captured_sessions": captured,
        "uncaptured_sessions": len(sessions) - captured,
        "api_calls": len(lats),
        "avg_s": _secs(sum(lats) / len(lats)) if lats else None,
        "p50_s": _secs(percentile(lats, 0.50)),
        "p95_s": _secs(percentile(lats, 0.95)),
        "by_model": rows,
    }


def _tools(sessions: Sequence[Dict[str, Any]],
           index: Dict[str, Dict[str, List[Dict[str, Any]]]]) -> Dict[str, Any]:
    calls: Dict[str, int] = {}
    fails: Dict[str, int] = {}
    dur: Dict[str, float] = {}
    seen = 0
    for s in sessions:
        for t in (index.get(s.get("id")) or EMPTY_ENTRY).get("tool_calls") or []:
            name = t.get("tool") or "unknown"
            seen += 1
            calls[name] = calls.get(name, 0) + 1
            if t.get("status") == "error":
                fails[name] = fails.get(name, 0) + 1
            dur[name] = dur.get(name, 0.0) + float(t.get("duration_s") or 0.0)

    if not seen:
        return {"captured": False, "top_by_calls": [], "top_by_failure_rate": []}

    rows = []
    for name, n in calls.items():
        f = fails.get(name, 0)
        rows.append({
            "tool": name,
            "calls": n,
            "failures": f,
            "failure_rate": round(f / n, 3) if n else 0.0,
            "avg_duration_s": _secs(dur.get(name, 0.0) / n) if n else None,
        })

    by_calls = sorted(rows, key=lambda d: (-d["calls"], d["tool"]))[:10]
    # A 1-call 100%-failure tool is noise, not a signal — require >= 3 calls.
    # A tool that never failed is not a failure signal at all: without the
    # `failures > 0` filter this list is just top_by_calls with a 0.0% column,
    # ten rows of "highest failure rate: 0.0%". Empty is the honest answer.
    by_fail = sorted(
        [r for r in rows if r["calls"] >= 3 and r["failures"] > 0],
        key=lambda d: (-d["failure_rate"], -d["calls"], d["tool"]),
    )[:10]
    return {"captured": True, "top_by_calls": by_calls, "top_by_failure_rate": by_fail}


def build_telemetry(sessions: Sequence[Dict[str, Any]],
                    index: Dict[str, Dict[str, List[Dict[str, Any]]]],
                    files_read: Sequence[str]) -> Dict[str, Any]:
    """The GET /hermes/telemetry payload for a list of scanned Hermes sessions."""
    sessions = list(sessions)
    latency = _latency(sessions, index)
    return {
        "available": True,
        "session_count": len(sessions),
        "outcomes": _outcomes(sessions),
        "cost": _cost(sessions),
        "latency": latency,
        "tools": _tools(sessions, index),
        "log_coverage": {
            "files_read": list(files_read),
            "sessions_with_log": latency["captured_sessions"],
            "sessions_total": len(sessions),
        },
    }
