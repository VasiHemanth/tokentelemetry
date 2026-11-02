"""Always-on agent evals — wake/silence, schedule drift and inter-agent calls.

For proactive / cron-triggered / peer-triggered agents the eval unit is the
whole trace: did the agent wake when it should, stay silent when it should, did
its schedule actually fire, did a call to another agent resolve. This module
derives those as small ``EvalEvent`` rows from data TT ALREADY scans (the
``sess["loop"]`` dict and ``session_links`` edges) and stores them in the
``eval_events`` sidecar table (history_store v5).

WHY A SIDECAR (same reasoning as ``session_links``)
Folding new fields into the main session scan would force a
``scan_cache.CACHE_VERSION`` bump and re-parse the user's whole history. Eval
events are derived on demand from already-parsed sessions instead.

PRIVACY
Rows hold ids, timings, enums and labels ONLY. Never prompt text, prompt
previews, cwd/paths or token contents. ``_scrub`` enforces an allow-list.

RECORD-ONLY
``evalRecordOnly`` (``~/.tokentelemetry/evals.json``, default true) means events
are written and listed, but MUST NOT feed notifications or automated scoring.
Callers check ``feeds_automation()``. Note: distinct from ``TraceSpan.recordOnly``
(a reader-message flag in the frontend) — do not conflate.

KNOWN GAPS (documented, not papered over)
- Wake/silence decisions are not recorded by any harness today. We emit
  ``source="derived"`` ``wake`` stubs only for loop fires we can see
  (iterations > 0). A *silence* (fired, chose not to act) is indistinguishable
  from a missed fire in current transcripts, so no silence stubs are derived;
  they arrive via ``source="recorded"`` (future harness hook) or human labels.
- Per-fire timestamps: Claude /loop keeps re-injected fire ts in the scanner
  but the session dict only exposes ``last_fired`` + ``iterations``; Grok
  scheduler fires carry no per-record ts (last_fired ≈ last activity). Drift is
  therefore computed for the LAST fire only, against
  ``created_at + iterations * cadence_seconds``.
- Antigravity exposes no loop/cron data in its transcripts today, so nothing is
  derived for it; recorded events for agent="antigravity" are accepted.
- ``human_present`` uses the session's ``last_user_ts`` when present; otherwise
  False (no user turn known within the 30-minute window).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from tt_paths import data_dir

SCHEMA_VERSION = 1
NO_HUMAN_WINDOW_S = 30 * 60
FIRST_HARNESSES = ("grok", "claude", "antigravity")
KINDS = ("wake_decision", "schedule_fire", "agent_call")
SOURCES = ("derived", "recorded", "human_label")

_COMMON = ("id", "agent", "session_id", "ts", "kind", "source", "schema_version")
_ALLOWED = {
    "wake_decision": _COMMON + ("decision", "trigger", "reason", "confidence", "label",
                                "turn_event_index", "job_id"),
    "schedule_fire": _COMMON + ("loop_id", "job_id", "cadence", "expected_at", "actual_at",
                                "drift_s", "missed", "human_present"),
    "agent_call": _COMMON + ("parent_session_id", "parent_span_id", "child_session_id",
                             "msg_id", "channel", "resolved", "latency_ms"),
}
_REASON_MAX = 120  # reason is an enum-ish short code, never free prompt text


# ── config ──────────────────────────────────────────────────────────────────

def _cfg_path() -> Path:
    return data_dir() / "evals.json"


def load_config() -> Dict[str, Any]:
    try:
        raw = json.loads(_cfg_path().read_text())
        return {"evalRecordOnly": bool(raw.get("evalRecordOnly", True))}
    except Exception:
        return {"evalRecordOnly": True}


def save_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    cfg = load_config()
    if isinstance(payload.get("evalRecordOnly"), bool):
        cfg["evalRecordOnly"] = payload["evalRecordOnly"]
    p = _cfg_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2))
    return cfg


def feeds_automation() -> bool:
    """False while record-only: events must not reach notifications/scoring."""
    return not load_config()["evalRecordOnly"]


# ── helpers ─────────────────────────────────────────────────────────────────

def _ts(v: Any) -> Optional[datetime]:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, str) and v:
        try:
            d = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _iso(d: Optional[datetime]) -> Optional[str]:
    return d.astimezone(timezone.utc).isoformat() if d else None


def _eid(*parts: Any) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


def _scrub(ev: Dict[str, Any]) -> Dict[str, Any]:
    allowed = _ALLOWED.get(ev.get("kind"), _COMMON)
    out = {k: ev[k] for k in allowed if k in ev and ev[k] is not None}
    if isinstance(out.get("reason"), str):
        out["reason"] = out["reason"][:_REASON_MAX]
    return out


def make_event(kind: str, agent: str, session_id: str, ts: Any, source: str = "derived",
               **fields: Any) -> Dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"unknown eval kind {kind!r}")
    if source not in SOURCES:
        raise ValueError(f"unknown eval source {source!r}")
    ev = {"kind": kind, "agent": agent, "session_id": session_id,
          "ts": _iso(_ts(ts)) or _iso(datetime.now(timezone.utc)),
          "source": source, "schema_version": SCHEMA_VERSION, **fields}
    ev.setdefault("id", _eid(kind, agent, session_id, source, ev["ts"],
                             fields.get("job_id"), fields.get("msg_id"), fields.get("expected_at")))
    return _scrub(ev)


# ── derivation ──────────────────────────────────────────────────────────────

def derive_schedule_events(sessions: Iterable[Dict[str, Any]], now: Optional[datetime] = None
                           ) -> List[Dict[str, Any]]:
    """schedule_fire (+ derived wake stubs) from each session's ``loop`` dict."""
    now = now or datetime.now(timezone.utc)
    out: List[Dict[str, Any]] = []
    for s in sessions:
        lp = s.get("loop") or {}
        agent = s.get("agent") or ""
        if not lp.get("is_loop") or agent not in FIRST_HARNESSES:
            continue
        sid = str(s.get("id") or "")
        job = lp.get("job_id")
        cad = lp.get("cadence_seconds")
        created = _ts(lp.get("created_at"))
        last = _ts(lp.get("last_fired"))
        iters = int(lp.get("iterations") or 0)
        user_ts = _ts(s.get("last_user_ts"))
        common = dict(loop_id=job, job_id=job, cadence=lp.get("cadence") or None)

        if last and iters > 0:
            expected = created + timedelta(seconds=cad * iters) if (created and cad) else None
            drift = (last - expected).total_seconds() if expected else None
            human = bool(user_ts and abs((last - user_ts).total_seconds()) <= NO_HUMAN_WINDOW_S)
            out.append(make_event("schedule_fire", agent, sid, last, expected_at=_iso(expected),
                                  actual_at=_iso(last), drift_s=drift, missed=False,
                                  human_present=human, **common))
            out.append(make_event("wake_decision", agent, sid, last, decision="wake",
                                  trigger="cron", reason="loop_fire_observed", job_id=job))
        # Missed: recurring, not cancelled, and >2 cadences past the next due time.
        anchor = last or created
        if (lp.get("recurring") and not lp.get("cancelled") and cad and anchor
                and lp.get("state") not in ("expired",)):
            due = anchor + timedelta(seconds=cad)
            if (now - due).total_seconds() > cad:
                out.append(make_event("schedule_fire", agent, sid, due, expected_at=_iso(due),
                                      actual_at=None, drift_s=None, missed=True,
                                      human_present=False, **common))
    return out


def derive_agent_calls(sessions: Iterable[Dict[str, Any]],
                       graph: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """agent_call from subagent parent links and session_links peer edges."""
    out: List[Dict[str, Any]] = []
    for s in sessions:
        parent = s.get("parent_session_id")
        if parent and s.get("agent") in FIRST_HARNESSES:
            out.append(make_event("agent_call", s["agent"], str(parent), s.get("timestamp"),
                                  parent_session_id=str(parent), child_session_id=str(s.get("id")),
                                  channel="subagent", resolved=True))
    for e in (graph or {}).get("edges", []):
        sent, recv = _ts(e.get("sent_at")), _ts(e.get("received_at"))
        lat = int((recv - sent).total_seconds() * 1000) if (sent and recv) else None
        frm = e.get("from_session") or ""
        out.append(make_event("agent_call", "claude", frm, e.get("sent_at") or e.get("received_at"),
                              parent_session_id=frm or None, child_session_id=e.get("to_session"),
                              msg_id=e.get("msg_id"), channel="peer",
                              resolved=bool(e.get("resolved")), latency_ms=lat))
    return out


def derive_all(sessions: List[Dict[str, Any]], graph: Optional[Dict[str, Any]] = None,
               now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    return derive_schedule_events(sessions, now) + derive_agent_calls(sessions, graph)


# ── summary ─────────────────────────────────────────────────────────────────

def _pct(vals: List[float], p: float) -> Optional[float]:
    if not vals:
        return None
    v = sorted(vals)
    return v[min(len(v) - 1, int(round(p * (len(v) - 1))))]


def summarize(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Wake precision/recall from human labels (label = should_wake|should_silence)."""
    tp = fp = fn = 0
    for e in events:
        if e.get("kind") != "wake_decision" or e.get("label") not in ("should_wake", "should_silence"):
            continue
        woke, should = e.get("decision") == "wake", e.get("label") == "should_wake"
        tp += woke and should
        fp += woke and not should
        fn += (not woke) and should
    fires = [e for e in events if e.get("kind") == "schedule_fire"]
    drifts = [abs(e["drift_s"]) for e in fires if isinstance(e.get("drift_s"), (int, float))]
    calls = [e for e in events if e.get("kind") == "agent_call"]
    return {
        "record_only": load_config()["evalRecordOnly"],
        "wake": {"labeled": tp + fp + fn, "tp": tp, "fp": fp, "fn": fn,
                 "precision": tp / (tp + fp) if tp + fp else None,
                 "recall": tp / (tp + fn) if tp + fn else None},
        "schedule": {"fires": len(fires), "missed": sum(1 for e in fires if e.get("missed")),
                     "drift_p50_s": _pct(drifts, 0.5), "drift_p95_s": _pct(drifts, 0.95)},
        "agent_calls": {"total": len(calls),
                        "unresolved": sum(1 for e in calls if not e.get("resolved"))},
    }
