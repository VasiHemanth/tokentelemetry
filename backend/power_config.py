"""Power & subscription cost configuration for local / subscription models.

The flat per-token pricing table in ``pricing.py`` is wrong for two classes of
models:

1. **Local models** (ollama / llama.cpp / vLLM running on your own hardware).
   There is no API bill — the real marginal cost is electricity. We approximate
   it from the machine's draw under load (``loadWatts``), your electricity tariff
   (``costPerKwh``), and how long the generation ran.

2. **Flat subscriptions** (Ollama Cloud Pro, a proxied/self-hosted gateway you
   pay for monthly, etc.). These are billed per month, not per token, so the
   per-call cost is 0 — the monthly fee is tracked separately, outside this
   tool's per-session accounting.

Config lives at ``~/.tokentelemetry/power.json``::

    {
      "loadWatts": 80,
      "costPerKwh": 0.15,
      "subscriptionEndpoints": ["https://ollama.com", "http://localhost:11434"]
    }

This module never raises on a missing or malformed file — it falls back to the
shipped defaults so cost accounting keeps working out of the box.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
# 80 W is a reasonable steady-state draw for a laptop / small desktop GPU under
# inference load; 0.15 USD/kWh is roughly the US residential average. These are
# intentionally conservative so the electricity estimate is in the right ballpark
# without claiming false precision.
DEFAULT_LOAD_WATTS = 80
# Hard ceiling: anything above this is rejected as garbage (e.g. a misparsed
# unsigned battery counter), so it can never reach the cost math.
MAX_LOAD_WATTS = 10000
DEFAULT_COST_PER_KWH = 0.15
# A realistic electricity tariff is well under this; reject absurd values so a
# fat-fingered or garbage rate can't blow up the electricity estimate.
MAX_COST_PER_KWH = 100.0
DEFAULT_SUBSCRIPTION_ENDPOINTS: List[str] = []
# Extra endpoints (beyond loopback) the user runs models on locally, e.g. a LAN
# box at http://192.168.1.50:11434. Loopback is always treated as local.
DEFAULT_LOCAL_ENDPOINTS: List[str] = []

DEFAULTS: Dict[str, Any] = {
    "loadWatts": DEFAULT_LOAD_WATTS,
    "costPerKwh": DEFAULT_COST_PER_KWH,
    "subscriptionEndpoints": list(DEFAULT_SUBSCRIPTION_ENDPOINTS),
    "localEndpoints": list(DEFAULT_LOCAL_ENDPOINTS),
}

# Provider ids that always denote local/self-hosted inference (no API bill).
LOCAL_PROVIDERS = {
    "ollama", "lmstudio", "lm-studio", "llama.cpp", "llamacpp", "llama-cpp",
    "vllm", "localai", "local-ai", "jan", "gpt4all", "koboldcpp", "local",
}

# Assumed local-inference throughput when we don't have a measured rate. Used to
# convert output tokens into a wall-clock generation time for the electricity
# estimate. 30 tok/s is a sane mid-range figure for a 7B-13B model on consumer
# hardware; callers that know the real throughput should pass it in.
DEFAULT_TOK_PER_SEC = 30.0


def _config_path() -> Path:
    home = Path(os.environ.get("TOKENTELEMETRY_HOME") or Path.home())
    return home / ".tokentelemetry" / "power.json"


def has_user_config() -> bool:
    """True if the user has written a power.json at all (any field)."""
    return _config_path().exists()


def local_power_enabled() -> bool:
    """True only if the user explicitly set a power figure (loadWatts/costPerKwh).

    The local-model electricity branch in ``pricing.calculate_cost`` keys off
    this, NOT merely ``has_user_config``. Otherwise a user who configured only
    ``subscriptionEndpoints`` would have every *unknown cloud* model silently
    re-priced as near-zero electricity instead of the ``_default`` per-token
    rate — under-reporting real API spend. We require an explicit power figure
    on disk so electricity pricing is opt-in independently of subscriptions.
    """
    path = _config_path()
    if not path.exists():
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return False
    if not isinstance(raw, dict):
        return False
    lw = raw.get("loadWatts")
    cpk = raw.get("costPerKwh")
    lw_ok = isinstance(lw, (int, float)) and not isinstance(lw, bool) and 0 < lw <= MAX_LOAD_WATTS
    cpk_ok = isinstance(cpk, (int, float)) and not isinstance(cpk, bool) and 0 <= cpk <= MAX_COST_PER_KWH
    return bool(lw_ok or cpk_ok)


def load_power_config() -> Dict[str, Any]:
    """Return power config with defaults filled in for missing/invalid fields.

    Never raises: a missing or malformed file yields the shipped defaults. Each
    field is validated independently, so one bad value can't discard the rest of
    a valid file.
    """
    config = dict(DEFAULTS)
    config["subscriptionEndpoints"] = list(DEFAULT_SUBSCRIPTION_ENDPOINTS)

    path = _config_path()
    if not path.exists():
        return config
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return config
    if not isinstance(raw, dict):
        return config

    lw = raw.get("loadWatts")
    if isinstance(lw, (int, float)) and not isinstance(lw, bool) and 0 < lw <= MAX_LOAD_WATTS:
        config["loadWatts"] = int(lw)

    cpk = raw.get("costPerKwh")
    if isinstance(cpk, (int, float)) and not isinstance(cpk, bool) and 0 <= cpk <= MAX_COST_PER_KWH:
        config["costPerKwh"] = float(cpk)

    eps = raw.get("subscriptionEndpoints")
    if isinstance(eps, list):
        config["subscriptionEndpoints"] = [
            e.strip() for e in eps if isinstance(e, str) and e.strip()
        ]

    leps = raw.get("localEndpoints")
    if isinstance(leps, list):
        config["localEndpoints"] = [
            e.strip() for e in leps if isinstance(e, str) and e.strip()
        ]

    return config


def save_power_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Merge validated ``updates`` over the current config and persist it.

    Returns the full config after the merge. Values that fail validation are
    skipped so a bad payload can't corrupt a setting.
    """
    config = load_power_config()

    lw = updates.get("loadWatts")
    if isinstance(lw, (int, float)) and not isinstance(lw, bool) and 0 < lw <= MAX_LOAD_WATTS:
        config["loadWatts"] = int(lw)

    cpk = updates.get("costPerKwh")
    if isinstance(cpk, (int, float)) and not isinstance(cpk, bool) and 0 <= cpk <= MAX_COST_PER_KWH:
        config["costPerKwh"] = float(cpk)

    eps = updates.get("subscriptionEndpoints")
    if isinstance(eps, list):
        config["subscriptionEndpoints"] = [
            e.strip() for e in eps if isinstance(e, str) and e.strip()
        ]

    leps = updates.get("localEndpoints")
    if isinstance(leps, list):
        config["localEndpoints"] = [
            e.strip() for e in leps if isinstance(e, str) and e.strip()
        ]

    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    os.replace(tmp, path)
    return config


def is_subscription_endpoint(
    endpoint: Optional[str], config: Optional[Dict[str, Any]] = None
) -> bool:
    """True if ``endpoint`` matches a configured flat-subscription endpoint.

    Matching is case-insensitive and substring-based in either direction so a
    configured host (``https://ollama.com``) matches a fuller request URL
    (``https://ollama.com/api/chat``) and vice-versa.
    """
    if not endpoint:
        return False
    if config is None:
        config = load_power_config()
    ep = endpoint.lower().strip()
    for sub in config.get("subscriptionEndpoints", []):
        s = sub.lower().strip()
        if not s:
            continue
        if s in ep or ep in s:
            return True
    return False


_LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]")


def _strip_scheme(url: str) -> str:
    """Drop a leading scheme so 'http://host:port/x' and 'host:port' compare equal."""
    return url.split("://", 1)[1] if "://" in url else url


def _is_loopback(endpoint: str) -> bool:
    host = _strip_scheme(endpoint.lower()).split("/", 1)[0]
    return any(host == h or host.startswith(h + ":") for h in _LOOPBACK_HOSTS)


def is_local_session(
    model_name: Optional[str] = None,
    endpoint: Optional[str] = None,
    provider: Optional[str] = None,
    billing_mode: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> bool:
    """True if a session is self-hosted/local (priced by electricity, not API).

    Confirmed-local signals, any of which wins over the pricing table (so a local
    ``llama-3.3-70b`` is NOT billed at cloud rates):
      1. the agent is set to ``local`` billing mode by the user
      2. the request endpoint is loopback or a user-listed local endpoint
      3. the provider id is a known local runtime (ollama, lmstudio, vllm, …)
    """
    if billing_mode == "local":
        return True
    if endpoint:
        if _is_loopback(endpoint):
            return True
        if config is None:
            config = load_power_config()
        # Match on host[:port], scheme-insensitive — a user who lists
        # http://192.168.1.50:11434 should still match an https request to it.
        ep = _strip_scheme(endpoint.lower().strip())
        for le in config.get("localEndpoints", []):
            s = _strip_scheme(le.lower().strip())
            if s and (s in ep or ep in s):
                return True
    if provider and provider.lower().strip() in LOCAL_PROVIDERS:
        return True
    return False


# Rough single-stream throughput by parameter count, for consumer hardware. Used
# only as a fallback when we have no MEASURED rate (e.g. Hermes logs per-call
# latency; calibration measures the real machine). Ballpark — the figure carries
# low confidence and exists so a 4B isn't costed like a 70B.
_TOK_PER_SEC_BY_PARAMS = [
    (1, 150.0), (4, 90.0), (8, 70.0), (14, 50.0),
    (34, 30.0), (70, 18.0), (float("inf"), 10.0),
]
_PARAM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*b\b", re.IGNORECASE)


def default_tok_per_sec_for_model(model: Optional[str]) -> float:
    """Best-effort default throughput from a model's parameter count in its name.

    e.g. ``nemotron-3-nano:4b`` → ~90 tok/s, ``llama-3.3-70b`` → ~18. Falls back
    to ``DEFAULT_TOK_PER_SEC`` when no size is parseable.
    """
    if not model:
        return DEFAULT_TOK_PER_SEC
    m = _PARAM_RE.search(str(model))
    if not m:
        return DEFAULT_TOK_PER_SEC
    try:
        params_b = float(m.group(1))
    except ValueError:
        return DEFAULT_TOK_PER_SEC
    for ceiling, rate in _TOK_PER_SEC_BY_PARAMS:
        if params_b <= ceiling:
            return rate
    return DEFAULT_TOK_PER_SEC


def electricity_cost(
    output_tokens: int,
    config: Optional[Dict[str, Any]] = None,
    tok_per_sec: float = DEFAULT_TOK_PER_SEC,
) -> float:
    """Estimate the electricity cost (USD) of generating ``output_tokens`` locally.

    cost = generation_seconds * watts / 3_600_000 (Wh->kWh per second) * costPerKwh

    where generation_seconds = output_tokens / tok_per_sec. Returns 0.0 for
    non-positive inputs. ``tok_per_sec`` defaults to a conservative local-inference
    throughput; pass a measured value when available.
    """
    if config is None:
        config = load_power_config()
    if output_tokens <= 0 or not tok_per_sec or tok_per_sec <= 0:
        return 0.0
    watts = config.get("loadWatts", DEFAULT_LOAD_WATTS)
    cost_per_kwh = config.get("costPerKwh", DEFAULT_COST_PER_KWH)
    gen_seconds = output_tokens / tok_per_sec
    # watts * seconds = watt-seconds (joules); /3_600_000 converts Wh->kWh and
    # seconds->hours in one shot (3600 s/h * 1000 Wh/kWh).
    kwh = (watts * gen_seconds) / 3_600_000
    return kwh * cost_per_kwh
