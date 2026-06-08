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
DEFAULT_COST_PER_KWH = 0.15
DEFAULT_SUBSCRIPTION_ENDPOINTS: List[str] = []

DEFAULTS: Dict[str, Any] = {
    "loadWatts": DEFAULT_LOAD_WATTS,
    "costPerKwh": DEFAULT_COST_PER_KWH,
    "subscriptionEndpoints": list(DEFAULT_SUBSCRIPTION_ENDPOINTS),
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
    lw_ok = isinstance(lw, (int, float)) and not isinstance(lw, bool) and lw > 0
    cpk_ok = isinstance(cpk, (int, float)) and not isinstance(cpk, bool) and cpk >= 0
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
    if isinstance(lw, (int, float)) and not isinstance(lw, bool) and lw > 0:
        config["loadWatts"] = int(lw)

    cpk = raw.get("costPerKwh")
    if isinstance(cpk, (int, float)) and not isinstance(cpk, bool) and cpk >= 0:
        config["costPerKwh"] = float(cpk)

    eps = raw.get("subscriptionEndpoints")
    if isinstance(eps, list):
        config["subscriptionEndpoints"] = [
            e.strip() for e in eps if isinstance(e, str) and e.strip()
        ]

    return config


def save_power_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Merge validated ``updates`` over the current config and persist it.

    Returns the full config after the merge. Values that fail validation are
    skipped so a bad payload can't corrupt a setting.
    """
    config = load_power_config()

    lw = updates.get("loadWatts")
    if isinstance(lw, (int, float)) and not isinstance(lw, bool) and lw > 0:
        config["loadWatts"] = int(lw)

    cpk = updates.get("costPerKwh")
    if isinstance(cpk, (int, float)) and not isinstance(cpk, bool) and cpk >= 0:
        config["costPerKwh"] = float(cpk)

    eps = updates.get("subscriptionEndpoints")
    if isinstance(eps, list):
        config["subscriptionEndpoints"] = [
            e.strip() for e in eps if isinstance(e, str) and e.strip()
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
