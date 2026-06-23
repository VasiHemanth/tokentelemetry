"""TokenTelemetry product telemetry — anonymous, opt-out, content-free.

Sends a tiny set of feature-usage events so we can learn which parts of the app
people actually use (see docs/design/product-telemetry.md). It is deliberately
boring and safe:

  - **On by default, one-click off.** Preference ``telemetry`` (default True). A
    first-run notice in the UI tells the user it's on and how to turn it off.
    ``DO_NOT_TRACK`` / ``TT_NO_TELEMETRY`` force it off (policy/CI); CI and
    non-interactive launches never emit (no one to inform).
  - **The app never holds any key.** Events POST to a Cloudflare Worker we run
    (``TT_TELEMETRY_URL``); the Worker writes them to Workers Analytics Engine
    via an account-bound binding — there is no credential anywhere in the
    request path, and nothing to extract from the open-source bundle. See proxy/.
  - **Content-free by construction.** ``_sanitize_props`` keeps ONLY an explicit
    per-event allowlist of keys, each value forced through ``_safe_scalar`` and
    (for controlled fields) an enum. Anything else — paths, prompts, project
    names, free text, costs — is dropped, not sent. ``test_telemetry_redaction``
    is the guardrail that keeps this true.
  - **Best-effort.** Every send is fire-and-forget on a daemon thread with a
    short timeout; all failures are swallowed. Telemetry never slows or breaks
    the app — same fail-open posture as the update check.

There is no persistent user identifier. ``sessionId`` is random per process
launch and is not stored or linked across launches.
"""
from __future__ import annotations

import json
import os
import platform
import threading
import urllib.error
import urllib.request
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

from harness_config import load_preferences

# --------------------------------------------------------------------------
# Where events go. The app ONLY ever talks to this Worker URL — never a data
# store directly, never with a key. Override per-deployment (or point at a local
# endpoint for testing) via TT_TELEMETRY_URL. The Worker (proxy/) writes events
# to Cloudflare Workers Analytics Engine via an account-bound binding; there is
# no credential in the request path.
#
# Currently the live Cloudflare Worker on its workers.dev URL. Once the custom
# domain is attached, switch this to "https://telemetry.tokentelemetry.com/e".
# --------------------------------------------------------------------------
DEFAULT_PROXY_URL = "https://tt-telemetry-proxy.tokentelemetry.workers.dev"


def _proxy_url() -> str:
    """The telemetry sink URL. ``TT_TELEMETRY_URL`` may override it for
    deploy/testing, but only with an https URL (or a localhost http URL for
    local dev) — anything else (file:, gopher:, arbitrary internal http) is
    rejected and we fall back to the default. The payload is always our tiny
    sanitized event, so this is defense-in-depth against an SSRF-style misdirect,
    not a content-leak fix. (Audit AUDIT-grok.md, Med finding.)"""
    override = (os.environ.get("TT_TELEMETRY_URL") or "").strip()
    if override:
        low = override.lower()
        if low.startswith("https://") or low.startswith(("http://localhost", "http://127.0.0.1")):
            return override
        # Unsafe scheme/target — ignore the override, use the trusted default.
    return DEFAULT_PROXY_URL


_SEND_TIMEOUT_S = 3.0
_SDK = "tokentelemetry"

# Random per-process session id. Not persisted, not linked across launches —
# the most privacy-preserving choice (cf. design §6, "minimal or omit").
_SESSION_ID = uuid.uuid4().hex

# Mutable anonymous context, seeded by the backend at startup via
# update_context(). Only the keys below are ever attached to an event.
_CTX: Dict[str, Any] = {
    "app_version": "unknown",
    "summarizer_backend": "none",
    "agents": [],          # list[str] of detected agent names (public product list)
}
_CTX_LOCK = threading.Lock()

# Ring buffer of the exact payloads we actually transmitted, so the UI can show
# "here's what we sent" (transparency). Capped + in-memory only.
_SENT: Deque[Dict[str, Any]] = deque(maxlen=20)

# Last-send health. Telemetry is fire-and-forget, but we keep a tiny, in-memory
# record of how the most recent POST went so the Settings panel (and you) can
# SEE whether the sink is reachable — rather than failures being silently
# swallowed. Never persisted; reset each launch.
_LAST_SEND: Dict[str, Any] = {
    "status": "idle",   # idle | ok | http_error | unreachable
    "code": None,       # HTTP status when the sink answered
    "detail": None,     # short reason on failure (no payload, no PII)
    "at": None,         # ISO timestamp of the attempt
}
_LAST_SEND_LOCK = threading.Lock()


def _record_send(status: str, code: Optional[int] = None,
                 detail: Optional[str] = None) -> None:
    with _LAST_SEND_LOCK:
        _LAST_SEND.update({
            "status": status,
            "code": code,
            "detail": (detail or "")[:120] or None,
            "at": datetime.now(timezone.utc).isoformat(),
        })


# --------------------------------------------------------------------------
# Allowlists — the heart of the content-free guarantee.
# --------------------------------------------------------------------------
# Per-event: the ONLY prop keys that may be sent. Anything else is dropped.
_EVENT_PROPS: Dict[str, set] = {
    "app.launched":       set(),
    "page.viewed":        {"route"},
    "trace.summarized":   {"backend", "outcome"},
    "analytics.filtered": {"dimension"},
    "feature.used":       {"name"},
    "retention.opted_in": {"tier"},
}

# Enum-controlled values. A value outside its set becomes "other" — never the
# raw value — so an unexpected/identifying string can't ride through.
_ENUMS: Dict[str, set] = {
    "route": {
        "dashboard", "analytics", "traces", "projects", "project-detail",
        "hermes", "artifacts", "local-models", "settings", "sessions", "other",
    },
    "dimension": {"agent", "model", "local-only", "day", "other"},
    "outcome": {"ok", "error", "empty", "unavailable", "other"},
    "backend": {"ollama", "claude", "codex", "gemini", "qwen", "openai_compat",
                "antigravity", "none", "other"},
    "name": {
        "plan-library", "project-insights", "delegation-view", "power-cost",
        "billing-mode", "search", "artifact-viewer", "share-stats",
        "hermes-dashboard",
        # Budgets & alerts: "budgets" = opened the editor (adoption),
        # "budget-set" = saved a budget (the configuring action). No limit
        # value/cost ever rides along — only these two enum labels.
        "budgets", "budget-set",
        "other",
    },
    "tier": {"full", "rollup", "other"},
}

# Detected-agent names we recognise — must match _list_available_agents() in
# main.py. Anything else is bucketed as "other-agent" so a custom/identifying
# name can't leak.
_KNOWN_AGENTS = {
    "claude", "codex", "gemini", "antigravity", "qwen", "vibe",
    "cursor", "copilot", "opencode", "hermes", "grok",
}


def _safe_scalar(v: Any) -> Optional[Any]:
    """Coerce a value to a safe primitive, or drop it (None).

    bools/ints/floats pass (numbers clamped to a sane range). Strings pass ONLY
    if short and drawn from a benign charset — no '/', '@', whitespace runs, or
    other shapes that smell like a path, email, or free-text. This is defense in
    depth behind the enum check.
    """
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return max(-1_000_000, min(1_000_000, v))
    if isinstance(v, float):
        return float(max(-1e9, min(1e9, v)))
    if isinstance(v, str):
        s = v.strip()
        if not s or len(s) > 40:
            return None
        # Allowlisted charset: letters, digits, dot, underscore, hyphen only.
        if not all(c.isalnum() or c in "._-" for c in s):
            return None
        return s
    return None


def _sanitize_props(event: str, props: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return only allowlisted, enum-validated, safe-scalar props for ``event``."""
    allowed = _EVENT_PROPS.get(event)
    if not allowed or not props:
        return {}
    out: Dict[str, Any] = {}
    for key in allowed:
        if key not in props:
            continue
        val = _safe_scalar(props[key])
        if key in _ENUMS:
            # Enum keys always emit a value so the event is still counted, but
            # NEVER the raw value: anything unsafe or off-enum collapses to "other".
            out[key] = val if (val is not None and val in _ENUMS[key]) else "other"
        elif val is not None:
            out[key] = val
    return out


def _context_props() -> Dict[str, Any]:
    """The anonymous context attached to every event (already sanitized)."""
    with _CTX_LOCK:
        agents = [a for a in _CTX.get("agents", []) if isinstance(a, str)]
        backend = _CTX.get("summarizer_backend", "none")
    known = sorted({a if a in _KNOWN_AGENTS else "other-agent" for a in agents})
    return {
        "agents": ",".join(known)[:120],
        "agent_count": len(agents),
        "summarizer_backend": backend if backend in _ENUMS["backend"] else "other",
    }


def _system_props() -> Dict[str, Any]:
    with _CTX_LOCK:
        app_version = str(_CTX.get("app_version", "unknown"))[:20]
    return {
        "locale": "en-US",
        "osName": platform.system() or "unknown",
        "osVersion": (platform.release() or "")[:20],
        "deviceModel": platform.machine() or "",   # arch only (arm64/x86_64)
        "isDebug": bool(os.environ.get("TT_TELEMETRY_DEBUG")),
        "appVersion": app_version,
        "sdkVersion": _SDK,
    }


def build_event(event: str, props: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Construct the exact event payload we'd transmit.

    The Worker maps this JSON onto Analytics Engine columns (see proxy/), so the
    shape here is the app-side contract, not a vendor format.

    Pure + side-effect-free, so the preview endpoint can show users precisely
    what leaves the machine — including when telemetry is OFF.
    """
    merged = {**_sanitize_props(event, props), **_context_props()}
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sessionId": _SESSION_ID,
        "eventName": event if event in _EVENT_PROPS else "other",
        "systemProps": _system_props(),
        "props": merged,
    }


# --------------------------------------------------------------------------
# Enable/disable logic — mirrors _update_check_enabled().
# --------------------------------------------------------------------------
_CI_ENV = ("CI", "CONTINUOUS_INTEGRATION", "GITHUB_ACTIONS", "GITLAB_CI",
           "BUILDKITE", "JENKINS_URL", "TT_NON_INTERACTIVE")


def _is_ci() -> bool:
    return any(os.environ.get(k) for k in _CI_ENV)


def env_forced_off() -> bool:
    """True when an env var hard-disables telemetry (toggle becomes read-only)."""
    dnt = (os.environ.get("DO_NOT_TRACK") or "").strip().lower()
    if dnt in ("1", "true", "yes"):
        return True
    return bool(os.environ.get("TT_NO_TELEMETRY"))


def enabled() -> bool:
    """Whether we may actually transmit right now. Fail-safe: off if unsure."""
    if env_forced_off():
        return False
    if _is_ci():
        return False
    try:
        return bool(load_preferences().get("telemetry", True))
    except Exception:
        return False


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------
def update_context(*, app_version: Optional[str] = None,
                   summarizer_backend: Optional[str] = None,
                   agents: Optional[List[str]] = None) -> None:
    """Seed/refresh the anonymous context. Called by the backend at startup and
    when the summarizer config changes. Never raises."""
    with _CTX_LOCK:
        if app_version is not None:
            _CTX["app_version"] = app_version
        if summarizer_backend is not None:
            _CTX["summarizer_backend"] = summarizer_backend
        if agents is not None:
            _CTX["agents"] = list(agents)


def _post(payload: Dict[str, Any]) -> None:
    """Best-effort POST to the Worker. Never raises; records the outcome so the
    Settings panel can show whether the sink is reachable.

    Failure handling, by design:
      - Network down / Cloudflare unreachable / timeout  -> status "unreachable"
      - Worker answered with a non-2xx (e.g. 500/415)     -> status "http_error"
      - 2xx / 204                                          -> status "ok"
    In every case the event is simply dropped (no retry, no disk spool) — the
    app must never block, retry-storm, or surface a telemetry error.
    """
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            _proxy_url(), data=data,
            headers={"Content-Type": "application/json",
                     "User-Agent": "tokentelemetry-telemetry"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=_SEND_TIMEOUT_S)
        code = getattr(resp, "status", None) or resp.getcode()
        resp.close()
        _record_send("ok", code=code)
    except urllib.error.HTTPError as exc:
        # The sink replied, but not 2xx (misconfig, oversize, etc.).
        _record_send("http_error", code=exc.code, detail=exc.reason and str(exc.reason))
    except urllib.error.URLError as exc:
        # DNS/connection/timeout — Cloudflare or the network is unreachable.
        _record_send("unreachable", detail=str(getattr(exc, "reason", exc)))
    except Exception as exc:  # pragma: no cover - defensive catch-all
        _record_send("unreachable", detail=type(exc).__name__)


def emit(event: str, props: Optional[Dict[str, Any]] = None) -> None:
    """Record + best-effort send one event. No-op when disabled. Never raises."""
    if not enabled():
        return
    try:
        payload = build_event(event, props)
        _SENT.append(payload)
        threading.Thread(target=_post, args=(payload,), daemon=True).start()
    except Exception:
        pass


def sample_payloads() -> List[Dict[str, Any]]:
    """One synthetic payload per event type — the full shape, for the preview UI.
    Works regardless of enabled state so users can always inspect what we'd send."""
    samples = {
        "app.launched": None,
        "page.viewed": {"route": "analytics"},
        "trace.summarized": {"backend": "ollama", "outcome": "ok"},
        "analytics.filtered": {"dimension": "local-only"},
        "feature.used": {"name": "plan-library"},
        "retention.opted_in": {"tier": "full"},
    }
    return [build_event(ev, p) for ev, p in samples.items()]


def preview() -> Dict[str, Any]:
    """Everything the Settings 'Usage & privacy' panel needs to be transparent."""
    return {
        "enabled": bool(load_preferences().get("telemetry", True)) if not env_forced_off() else False,
        "env_forced_off": env_forced_off(),
        "is_ci": _is_ci(),
        "effective": enabled(),
        "session_id": _SESSION_ID,
        "never_collected": [
            "prompts", "code", "file or directory paths", "project / repo names",
            "tokens", "costs", "model output", "log content", "IP address",
            "any stable device or user identifier",
        ],
        "events": sorted(_EVENT_PROPS.keys()),
        "sample": sample_payloads(),
        "recent_sent": list(_SENT),
        "last_send": dict(_LAST_SEND),
    }
