"""Per-agent billing mode: how to *frame* the cost figure for each coding agent.

TokenTelemetry always estimates cost at **API list prices**. That number is the
right universal unit for comparing sessions, but what it *means* to a user
depends on how they pay for that agent:

- ``subscription`` — flat monthly fee (Claude Pro/Max, Copilot, Cursor, …). The
  figure is an *API-list-price equivalent*, NOT their bill; their real spend is
  a fixed fee and usually much lower.
- ``api`` — pay-per-token (an API key). The figure *approximates their bill*
  (still an estimate — tiers, batch/cache discounts and overage rates skew it).
- ``local`` — self-hosted (ollama/llama.cpp/vLLM). Priced by electricity in
  ``power_config``; the dollar figure is a power estimate, not an API charge.
- ``unknown`` — we couldn't tell and the user hasn't said.

Crucially this only changes the **label/disclaimer**, never the math (except
``local``, which ``pricing.calculate_cost`` already re-prices via power_config).

Resolution order for an agent's mode:
  1. an explicit user override in ``~/.tokentelemetry/billing.json`` (always wins)
  2. best-effort auto-detection from the agent's own auth/config on disk
  3. a sensible static default

Auto-detection is intentionally conservative: a detector returns ``None`` (→
fall through to the default) unless it finds a clear signal. It only ever reads
key *names* / file *existence* / env vars — never secret values.

This module never raises on missing/malformed files.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

MODES = ("subscription", "api", "local", "unknown")

# Static fallback when no override and no detection signal exists.
DEFAULT_MODES: Dict[str, str] = {
    "claude": "subscription",      # Mac OAuth token lives in Keychain (unreadable)
    "codex": "subscription",
    "gemini": "subscription",
    "qwen": "subscription",
    "copilot": "subscription",     # GitHub flat plan (premium-request overage aside)
    "cursor": "subscription",
    "antigravity": "subscription", # Google account
    "grok": "api",                 # xAI API key
    "hermes": "api",               # autonomous; runs on provider keys
    "opencode": "api",             # bring-your-own-key
    "vibe": "unknown",
}

# Human-readable note on where a detected value came from (shown in Settings so
# the inference is transparent and contestable).
DETECT_SOURCE: Dict[str, str] = {
    "claude": "ANTHROPIC_API_KEY env var",
    "codex": "~/.codex/auth.json",
    "gemini": "~/.gemini/oauth_creds.json + API-key env",
    "qwen": "~/.qwen/oauth_creds.json + API-key env",
}


def _home(home: Optional[Path]) -> Path:
    return home or Path.home()


def _read_json(path: Path) -> Optional[dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Per-agent detectors. Each returns "subscription" | "api" | None (= unsure).
# ---------------------------------------------------------------------------
def _detect_codex(home: Path) -> Optional[str]:
    """Codex writes an explicit ``auth_mode`` to ~/.codex/auth.json."""
    d = _read_json(home / ".codex" / "auth.json")
    if d is None:
        return None
    if d.get("OPENAI_API_KEY"):  # non-empty key string → pay-per-token
        return "api"
    mode = str(d.get("auth_mode", "")).lower()
    if "api" in mode or "key" in mode:
        return "api"
    if mode in ("chatgpt", "oauth") or d.get("tokens"):
        return "subscription"
    return None


def _detect_claude(home: Path) -> Optional[str]:
    """On macOS the subscription OAuth token is in Keychain, not a file — so we
    can only *positively* detect the API case from an env key. No key → unsure,
    fall back to the (subscription) default."""
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return "api"
    return None


def _detect_oauth_dir(home: Path, subdir: str, api_env_keys: tuple) -> Optional[str]:
    """Gemini/Qwen: an API-key env var means pay-per-token; otherwise the
    presence of oauth_creds.json means a logged-in (subscription/free) account."""
    if any(os.environ.get(k) for k in api_env_keys):
        return "api"
    if (home / subdir / "oauth_creds.json").exists():
        return "subscription"
    return None


def _detect_gemini(home: Path) -> Optional[str]:
    return _detect_oauth_dir(home, ".gemini", ("GEMINI_API_KEY", "GOOGLE_API_KEY"))


def _detect_qwen(home: Path) -> Optional[str]:
    return _detect_oauth_dir(home, ".qwen", ("DASHSCOPE_API_KEY", "QWEN_API_KEY"))


_DETECTORS: Dict[str, Callable[[Path], Optional[str]]] = {
    "codex": _detect_codex,
    "claude": _detect_claude,
    "gemini": _detect_gemini,
    "qwen": _detect_qwen,
}


def detect_mode(agent: str, home: Optional[Path] = None) -> Optional[str]:
    """Best-effort auto-detected mode for an agent, or None if no clear signal."""
    fn = _DETECTORS.get(agent)
    if not fn:
        return None
    try:
        result = fn(_home(home))
    except Exception:
        return None
    return result if result in MODES else None


# ---------------------------------------------------------------------------
# User overrides (~/.tokentelemetry/billing.json: {"<agent>": "<mode>"})
# ---------------------------------------------------------------------------
def _overrides_path() -> Path:
    home = Path(os.environ.get("TOKENTELEMETRY_HOME") or Path.home())
    return home / ".tokentelemetry" / "billing.json"


def load_overrides() -> Dict[str, str]:
    """User-chosen modes, validated. Missing/garbage file → empty dict."""
    raw = _read_json(_overrides_path())
    if not raw:
        return {}
    return {
        str(a): m
        for a, m in raw.items()
        if isinstance(a, str) and m in MODES
    }


def save_override(agent: str, mode: Optional[str]) -> Dict[str, str]:
    """Set (or, with mode=None, clear) one agent's override. Returns the full map.

    Clearing reverts that agent to auto-detection. Invalid modes are rejected by
    the caller (endpoint) — here we trust ``mode`` is validated or None.
    """
    overrides = load_overrides()
    if mode is None:
        overrides.pop(agent, None)
    else:
        overrides[agent] = mode

    path = _overrides_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(overrides, f, indent=2)
    os.replace(tmp, path)
    return overrides


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------
def get_mode(agent: str, home: Optional[Path] = None) -> Dict[str, Any]:
    """Resolve an agent's effective billing mode and how we arrived at it.

    Returns ``{mode, source, detected, default, detect_source}`` where ``source``
    is ``"user"`` | ``"detected"`` | ``"default"``.
    """
    overrides = load_overrides()
    detected = detect_mode(agent, home)
    default = DEFAULT_MODES.get(agent, "unknown")

    if agent in overrides:
        source, mode = "user", overrides[agent]
    elif detected:
        source, mode = "detected", detected
    else:
        source, mode = "default", default

    return {
        "mode": mode,
        "source": source,
        "detected": detected,
        "default": default,
        "detect_source": DETECT_SOURCE.get(agent),
    }


def get_all(agents: List[str], home: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    return {a: get_mode(a, home) for a in agents}
