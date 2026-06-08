#!/usr/bin/env python3
"""Dev/CI-only pricing sync — fetches models.dev and regenerates pricing_data.json.

⚠️  This script is the ONLY place in the project that performs outbound network
I/O for pricing, and it is NEVER imported or run on a user machine. TokenTelemetry
is local-first: users get fresh prices through the normal npm/git version update,
not by phoning models.dev at runtime. See backend/pricing.py — it only reads the
bundled, committed pricing_data.json (zero network I/O at import or runtime).

Run manually:

    python backend/pricing_sync.py

Or on a schedule via .github/workflows/pricing-sync.yml, which opens a PR with
the refreshed data so a maintainer can review the diff before it ships.

The output JSON mirrors the structure consumed by pricing.py:

    {
      "updated":  "YYYY-MM-DD",
      "source":   "https://models.dev/api.json",
      "schema":   1,
      "pricing":  { "<model_id_lower>": {"in": .., "out": .., "cached_read": ..}, ... },
      "by_provider": { "<provider_lower>\\u0000<model_id_lower>": {...}, ... }
    }

`by_provider` keys are flattened as "provider\\x00model" because JSON object keys
must be strings; pricing.py splits them back into the (provider, model) tuple
used by PRICING_BY_PROVIDER.
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

MODELS_DEV_URL = "https://models.dev/api.json"
OUTPUT_PATH = Path(__file__).parent / "pricing_data.json"
SCHEMA_VERSION = 1

# Separator used to flatten (provider, model) tuples into JSON string keys.
PROVIDER_SEP = "\x00"

# Map models.dev provider ids → the lowercased provider names TokenTelemetry
# records in sessions.billing_provider (and keys PRICING_BY_PROVIDER on).
PROVIDER_ALIASES = {
    "fireworks-ai": "fireworks",
    "together-ai": "together",
    "togetherai": "together",
}

# Sanity bounds (USD per 1M tokens). Prices outside this range are almost
# certainly a units bug upstream (e.g. per-1K vs per-1M) — drop them rather than
# poison the table.
MIN_RATE = 0.0
MAX_RATE = 10_000.0


def _coerce_rate(value: Any) -> Optional[float]:
    """Return a sane float rate, or None if missing/invalid/out-of-range."""
    if value is None:
        return None
    try:
        rate = float(value)
    except (TypeError, ValueError):
        return None
    if rate < MIN_RATE or rate > MAX_RATE:
        return None
    return rate


def _extract_rates(cost: Dict[str, Any]) -> Optional[Dict[str, Optional[float]]]:
    """Map a models.dev `cost` object to our {in,out,cached_read} shape.

    Requires at least one of input/output to be a valid number; otherwise the
    entry carries no useful pricing and is skipped.
    """
    in_rate = _coerce_rate(cost.get("input"))
    out_rate = _coerce_rate(cost.get("output"))
    if in_rate is None and out_rate is None:
        return None
    return {
        "in": in_rate,
        "out": out_rate,
        "cached_read": _coerce_rate(cost.get("cache_read")),
    }


def fetch_dataset(url: str = MODELS_DEV_URL, timeout: int = 60) -> Dict[str, Any]:
    """Fetch the models.dev dataset. Raises a clear error if offline/bad data."""
    req = urllib.request.Request(url, headers={"User-Agent": "tokentelemetry-pricing-sync"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except (urllib.error.URLError, OSError) as exc:
        raise SystemExit(
            f"ERROR: could not reach {url} ({exc}). "
            "This script is maintainer/CI-only and needs network access; "
            "the existing pricing_data.json is left untouched."
        )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"ERROR: {url} did not return valid JSON: {exc}")
    if not isinstance(data, dict) or not data:
        raise SystemExit(f"ERROR: {url} returned an unexpected/empty payload.")
    return data


def build_pricing(data: Dict[str, Any]) -> Dict[str, Any]:
    """Transform the raw models.dev dataset into our normalized pricing dict."""
    pricing: Dict[str, Dict[str, Optional[float]]] = {}
    by_provider: Dict[str, Dict[str, Optional[float]]] = {}

    for provider_id, provider in sorted(data.items()):
        if not isinstance(provider, dict):
            continue
        prov_key = PROVIDER_ALIASES.get(provider_id.lower(), provider_id.lower())
        for model_id, model in sorted(provider.get("models", {}).items()):
            if not isinstance(model, dict):
                continue
            cost = model.get("cost")
            if not isinstance(cost, dict):
                continue
            rates = _extract_rates(cost)
            if rates is None:
                continue
            mid = str(model_id).lower().strip()
            if not mid:
                continue
            # Flat table: first provider wins for a given bare model id (providers
            # are iterated in sorted order for determinism). Provider-keyed entry
            # always captures the per-provider price.
            pricing.setdefault(mid, rates)
            by_provider[f"{prov_key}{PROVIDER_SEP}{mid}"] = rates

    if not pricing:
        raise SystemExit(
            "ERROR: transformed dataset is empty — refusing to overwrite "
            "pricing_data.json with garbage."
        )

    return {
        "updated": _dt.date.today().isoformat(),
        "source": MODELS_DEV_URL,
        "schema": SCHEMA_VERSION,
        "pricing": pricing,
        "by_provider": by_provider,
    }


def main(argv: Optional[list] = None) -> int:
    data = fetch_dataset()
    result = build_pricing(data)
    OUTPUT_PATH.write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"Wrote {OUTPUT_PATH} — {len(result['pricing'])} models, "
        f"{len(result['by_provider'])} provider-keyed entries "
        f"(source: {result['source']}, updated {result['updated']})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
