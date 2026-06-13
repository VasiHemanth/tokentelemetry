"""Tests for power & subscription cost config (Unit 4 / issue #49).

The flat per-token table mis-prices local models (real cost is electricity) and
flat subscriptions (per-call cost is 0, billed monthly). These tests pin:
  - the config store (defaults, malformed-file tolerance, roundtrip),
  - the subscription-endpoint short-circuit in calculate_cost -> 0.0,
  - the local-model electricity branch when a power.json exists,
  - backward compatibility: no config file => unchanged per-token behaviour.

Run with pytest, or directly:  python backend/test_power_config.py
"""
import importlib
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))


def _fresh_modules(home: str):
    """Point power_config at `home` and reload it + pricing so they pick it up."""
    os.environ["TOKENTELEMETRY_HOME"] = home
    import power_config
    import pricing
    importlib.reload(power_config)
    importlib.reload(pricing)
    return power_config, pricing


def _write_power_json(home: str, data: dict) -> None:
    d = Path(home) / ".tokentelemetry"
    d.mkdir(parents=True, exist_ok=True)
    (d / "power.json").write_text(json.dumps(data), encoding="utf-8")


# --------------------------------------------------------------------------
# Config store
# --------------------------------------------------------------------------
def test_defaults_when_no_file():
    with tempfile.TemporaryDirectory() as home:
        pc, _ = _fresh_modules(home)
        cfg = pc.load_power_config()
        # Default wattage is now device-aware (chip estimate where available,
        # else the flat DEFAULT_LOAD_WATTS) — assert against that source of truth.
        assert cfg["loadWatts"] == pc.device_default_watts()
        assert cfg["costPerKwh"] == pc.DEFAULT_COST_PER_KWH
        assert cfg["subscriptionEndpoints"] == []
        assert pc.has_user_config() is False


def test_device_default_drives_loadwatts_when_unset(monkeypatch):
    """A chip-aware estimate becomes the default loadWatts (not the flat 80)."""
    with tempfile.TemporaryDirectory() as home:
        pc, pr = _fresh_modules(home)
        import power_meter
        # Pretend we're on an Apple M-series box → 22 W estimate.
        monkeypatch.setattr(
            power_meter, "estimated_watts",
            lambda with_detail=True: {
                "watts": 22.0, "source": "apple-silicon-default",
                "confidence": "estimated", "detail": "Apple M5 (10-core GPU)",
            },
        )
        pc.device_default.cache_clear()
        assert pc.device_default_watts() == 22
        assert pc.device_default()["detected"] is True
        # No power.json → electricity cost uses the 22 W device default, not 80.
        cfg = pc.load_power_config()
        assert cfg["loadWatts"] == 22
        cost = pc.electricity_cost(900, cfg, tok_per_sec=90.0)  # 10 s of gen
        assert abs(cost - (10 * 22 / 3_600_000 * pc.DEFAULT_COST_PER_KWH)) < 1e-12
        # An explicit power.json value still wins over the device default.
        _write_power_json(home, {"loadWatts": 150})
        pc.device_default.cache_clear()
        assert pc.load_power_config()["loadWatts"] == 150


def test_device_default_falls_back_to_flat_when_no_estimate(monkeypatch):
    with tempfile.TemporaryDirectory() as home:
        pc, _ = _fresh_modules(home)
        import power_meter
        monkeypatch.setattr(power_meter, "estimated_watts", lambda with_detail=True: None)
        pc.device_default.cache_clear()
        assert pc.device_default_watts() == pc.DEFAULT_LOAD_WATTS
        assert pc.device_default()["source"] == "default"
        assert pc.device_default()["detected"] is False


def test_malformed_file_falls_back_to_defaults():
    with tempfile.TemporaryDirectory() as home:
        d = Path(home) / ".tokentelemetry"
        d.mkdir(parents=True)
        (d / "power.json").write_text("{not valid json", encoding="utf-8")
        pc, _ = _fresh_modules(home)
        cfg = pc.load_power_config()  # must not raise
        assert cfg["loadWatts"] == pc.device_default_watts()
        # File exists, so it counts as user-configured even though it's garbage.
        assert pc.has_user_config() is True


def test_partial_and_bad_fields_validated_independently():
    with tempfile.TemporaryDirectory() as home:
        _write_power_json(home, {
            "loadWatts": 120,
            "costPerKwh": "not-a-number",   # bad -> default kept
            "subscriptionEndpoints": ["https://ollama.com", "", 5, "  http://x  "],
        })
        pc, _ = _fresh_modules(home)
        cfg = pc.load_power_config()
        assert cfg["loadWatts"] == 120
        assert cfg["costPerKwh"] == pc.DEFAULT_COST_PER_KWH
        assert cfg["subscriptionEndpoints"] == ["https://ollama.com", "http://x"]


def test_save_roundtrip_and_skips_bad_values():
    with tempfile.TemporaryDirectory() as home:
        pc, _ = _fresh_modules(home)
        saved = pc.save_power_config({
            "loadWatts": 95, "costPerKwh": 0.22,
            "subscriptionEndpoints": ["https://ollama.com"],
        })
        assert saved["loadWatts"] == 95 and saved["costPerKwh"] == 0.22
        assert pc.load_power_config()["loadWatts"] == 95
        # Bad payload can't corrupt existing values.
        again = pc.save_power_config({"loadWatts": -10, "costPerKwh": "x"})
        assert again["loadWatts"] == 95 and again["costPerKwh"] == 0.22


# --------------------------------------------------------------------------
# calculate_cost integration
# --------------------------------------------------------------------------
def test_subscription_endpoint_returns_zero():
    with tempfile.TemporaryDirectory() as home:
        _write_power_json(home, {"subscriptionEndpoints": ["https://ollama.com"]})
        _, pricing = _fresh_modules(home)
        # Even a model with a real rate -> 0 because it's billed monthly.
        cost = pricing.calculate_cost(
            "claude-opus-4-7", 100_000, 50_000,
            endpoint="https://ollama.com/api/chat",
        )
        assert cost == 0.0


def test_subscription_match_is_substring_either_way():
    with tempfile.TemporaryDirectory() as home:
        _write_power_json(home, {"subscriptionEndpoints": ["api.githubcopilot.com"]})
        _, pricing = _fresh_modules(home)
        cost = pricing.calculate_cost(
            "gpt-5.4", 1000, 1000,
            endpoint="https://api.githubcopilot.com",
        )
        assert cost == 0.0


def test_local_model_uses_electricity_when_configured():
    with tempfile.TemporaryDirectory() as home:
        _write_power_json(home, {"loadWatts": 80, "costPerKwh": 0.15})
        pc, pricing = _fresh_modules(home)
        out_tokens = 30_000  # at default 30 tok/s -> 1000s
        cost = pricing.calculate_cost("my-local-llama", 5000, out_tokens)
        # Expected electricity: 1000s * 80W / 3_600_000 * 0.15
        expected = (out_tokens / pc.DEFAULT_TOK_PER_SEC) * 80 / 3_600_000 * 0.15
        assert abs(cost - expected) < 1e-9
        # Sanity: this is far cheaper than the _default per-token rate would be.
        default_rate = pricing.PRICING["_default"]
        per_token = (5000 / 1e6) * default_rate["in"] + (out_tokens / 1e6) * default_rate["out"]
        assert cost < per_token


def test_local_model_respects_custom_tok_per_sec():
    with tempfile.TemporaryDirectory() as home:
        _write_power_json(home, {"loadWatts": 100, "costPerKwh": 0.20})
        _, pricing = _fresh_modules(home)
        out_tokens = 6000
        cost = pricing.calculate_cost(
            "some-unknown-local", 0, out_tokens, tok_per_sec=60.0,
        )
        expected = (out_tokens / 60.0) * 100 / 3_600_000 * 0.20
        assert abs(cost - expected) < 1e-9


def test_subscription_only_config_does_not_electricity_price_unknown_cloud():
    # A user who lists ONLY subscription endpoints must not have unknown CLOUD
    # models silently re-priced as near-zero electricity (that would under-report
    # real API spend). Without an explicit power figure, unknown models still
    # fall through to _default.
    with tempfile.TemporaryDirectory() as home:
        _write_power_json(home, {"subscriptionEndpoints": ["https://ollama.com"]})
        pc, pricing = _fresh_modules(home)
        assert pc.local_power_enabled() is False
        unknown = pricing.calculate_cost("brand-new-cloud-model", 1_000_000, 1_000_000)
        d = pricing.PRICING["_default"]
        assert abs(unknown - (d["in"] + d["out"])) < 1e-9
        # ...but the subscription short-circuit still works for that endpoint.
        assert pricing.calculate_cost(
            "brand-new-cloud-model", 1_000_000, 1_000_000,
            endpoint="https://ollama.com/api/chat",
        ) == 0.0


def test_no_config_file_preserves_per_token_behaviour():
    with tempfile.TemporaryDirectory() as home:
        _, pricing = _fresh_modules(home)  # no power.json written
        # Known model: unchanged.
        known = pricing.calculate_cost("claude-opus-4-7", 1_000_000, 1_000_000)
        assert abs(known - (5.00 + 25.00)) < 1e-9
        # Unknown model: still falls through to _default (NOT electricity).
        unknown = pricing.calculate_cost("totally-unknown-xyz", 1_000_000, 1_000_000)
        d = pricing.PRICING["_default"]
        assert abs(unknown - (d["in"] + d["out"])) < 1e-9
        # An endpoint with no subscription config doesn't zero anything out.
        with_ep = pricing.calculate_cost(
            "claude-opus-4-7", 1_000_000, 0, endpoint="https://api.anthropic.com",
        )
        assert with_ep > 0


if __name__ == "__main__":
    import traceback
    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in funcs:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(funcs) - failed}/{len(funcs)} passed")
    sys.exit(1 if failed else 0)
