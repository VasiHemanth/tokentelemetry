"""Provider reaches calculate_cost from the Codex and Cline scanners (issue #304).

Both scanners already held the routing signal and dropped it on the floor: Codex
captures ``sess["_provider"]`` from the rollout's session_meta, Cline reads a
``provider`` column out of sessions.db. Neither passed it, so cost never reached
the provider-keyed table, the subscription branch, or the local-electricity
branch — the three things provider exists to select.

These tests pin the wiring at the source level (the call sites actually pass it)
and the behaviour at the pricing level (passing it changes the answer in the
ways it should).
"""

import json
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path

import pricing
from pricing import calculate_cost

MAIN = (Path(__file__).parent / "main.py").read_text()
MTOK = 1_000_000


def _call_site(pattern: str) -> str:
    m = re.search(pattern, MAIN, re.S)
    assert m, f"call site not found: {pattern}"
    return m.group(0)


def test_codex_turn_cost_passes_provider():
    # Anchored on the Codex-only comment: the Claude scanner has a near-identical
    # call two thousand lines up, and a looser pattern matches that one instead.
    site = _call_site(
        r'# Codex/OpenAI usage has no cache-write field.*?sess\["cost"\] = calculate_cost\([^\n]*\)'
    )
    assert 'provider=sess.get("_provider")' in site, site


def test_codex_daily_cost_passes_provider():
    site = _call_site(r'"cost": calculate_cost\(model_for_cost[^\n]*\)')
    assert 'provider=sess.get("_provider")' in site, site


def test_codex_model_slot_no_longer_falls_back_to_provider():
    """A provider id must never be passed as a model.

    `model_for_cost = sess.get("model") or sess.get("_provider")` put "openai" /
    "deepseek" into the model argument, where it fuzzy-matched or hit _default.
    """
    assert 'model_for_cost = sess.get("model") or sess.get("_provider")' not in MAIN
    assert 'model_for_cost = sess.get("model")' in MAIN


def test_cline_cli_cost_passes_provider():
    # Tolerate further kwargs after provider= (the call also carries at=).
    site = _call_site(r'tokens\["cost"\] = calculate_cost\(model, tokens\["input"\], tokens\["output"\], tokens\["cached"\], provider=row\["provider"\][^\n]*\)')
    assert 'provider=row["provider"]' in site


def test_provider_changes_the_rate_when_tables_differ():
    """together marks up deepseek-v4-pro; dropping provider silently bills direct."""
    direct = calculate_cost("deepseek-v4-pro", MTOK, 0)
    marked_up = calculate_cost("deepseek-v4-pro", MTOK, 0, provider="together")
    assert marked_up > direct, (marked_up, direct)


@contextmanager
def _power_config(cfg: dict):
    """Run the block with power.json set to ``cfg``.

    Pins TOKENTELEMETRY_DATA_DIR, not TOKENTELEMETRY_HOME. DATA_DIR wins in
    tt_paths.data_dir(), and several test modules in this suite set it and never
    restore it — so a HOME-based fixture passes alone and fails in a full run,
    silently reading the developer's real ~/.tokentelemetry/power.json.
    """
    tmp = tempfile.mkdtemp()
    (Path(tmp) / "power.json").write_text(json.dumps(cfg), encoding="utf-8")
    prev_dd = os.environ.get("TOKENTELEMETRY_DATA_DIR")
    prev_home = os.environ.get("TOKENTELEMETRY_HOME")
    os.environ["TOKENTELEMETRY_DATA_DIR"] = tmp
    os.environ.pop("TOKENTELEMETRY_HOME", None)
    try:
        yield
    finally:
        for k, v in (("TOKENTELEMETRY_DATA_DIR", prev_dd), ("TOKENTELEMETRY_HOME", prev_home)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_subscription_provider_prices_at_zero():
    """cline-pass is flat monthly; sessions.db has no endpoint to match on."""
    with _power_config({"subscriptionProviders": ["cline-pass"]}):
        assert calculate_cost("deepseek-v4-pro", MTOK, MTOK, provider="cline-pass") == 0.0
        # A different provider on the same model is unaffected.
        assert calculate_cost("deepseek-v4-pro", MTOK, MTOK, provider="deepseek") > 0


def test_subscription_provider_is_exact_not_substring():
    """`cline` configured must not swallow `cline-pass` (provider ids collide)."""
    with _power_config({"subscriptionProviders": ["cline"]}):
        assert calculate_cost("deepseek-v4-pro", MTOK, MTOK, provider="cline") == 0.0
        assert calculate_cost("deepseek-v4-pro", MTOK, MTOK, provider="cline-pass") > 0


def test_local_provider_prices_by_electricity_not_cloud_rates():
    """Cline's own db reports provider='ollama'; that must not bill at cloud rates."""
    cloud = calculate_cost("deepseek-v4-pro", 0, MTOK)
    local = calculate_cost("deepseek-v4-pro", 0, MTOK, provider="ollama")
    assert local < cloud, (local, cloud)


def test_cache_version_bumped_for_repricing():
    """Cached sessions store a computed cost, so a rate change must invalidate them."""
    import scan_cache
    assert scan_cache.CACHE_VERSION >= 9


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            fn()
    print("All tests passed!")
