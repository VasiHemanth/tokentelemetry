"""Claude 5 generation pricing (from #250's pricing half).

claude-sonnet-5 was billed at $3.00/$15.00 — Sonnet 4.6's price — against a real
rate of $2.00/$10.00, a uniform 1.5x overcharge on every component.

Two things made it invisible:

1. No curated inline entry existed for any Claude 5 model, so the whole
   generation resolved through the models.dev overlay unchallenged. The
   divergence report (#309) compares the two layers, so a model present in only
   one of them produces no row.
2. The overlay contradicts itself. Its flat `claude-sonnet-5` said $3/$15 while
   its `("anthropic", "claude-sonnet-5")` said the correct $2/$10 — so the cost
   depended on whether the scanner happened to pass a provider.

Rates: https://docs.claude.com/en/docs/about-claude/pricing
"""

import pricing
from pricing import PRICING, PRICING_BY_PROVIDER, calculate_cost

MTOK = 1_000_000

CLAUDE_5 = {
    "claude-fable-5":  {"in": 10.00, "out": 50.00, "cached_read": 1.00},
    "claude-mythos-5": {"in": 10.00, "out": 50.00, "cached_read": 1.00},
    "claude-opus-5":   {"in": 5.00,  "out": 25.00, "cached_read": 0.50},
    "claude-opus-4-8": {"in": 5.00,  "out": 25.00, "cached_read": 0.50},
    "claude-sonnet-5": {"in": 2.00,  "out": 10.00, "cached_read": 0.20},
}


def test_flat_table_matches_published_rates():
    for model, rates in CLAUDE_5.items():
        assert PRICING[model] == rates, f"{model}: {PRICING[model]} != {rates}"


def test_provider_keyed_matches_flat():
    """Cost must not depend on whether the caller knew the provider.

    This is the actual bug: the overlay's flat and anthropic-keyed Sonnet 5
    entries disagreed by 1.5x, so two identical sessions priced differently
    based on whether the scanner supplied a provider.
    """
    for model, rates in CLAUDE_5.items():
        assert PRICING_BY_PROVIDER[("anthropic", model)] == rates
        without = calculate_cost(model, MTOK, MTOK)
        with_prov = calculate_cost(model, MTOK, MTOK, provider="anthropic")
        assert without == with_prov, f"{model}: {without} vs {with_prov}"


def test_sonnet_5_is_not_sonnet_4_6s_price():
    """Regression: the $3/$15 carry-forward must not come back."""
    assert PRICING["claude-sonnet-5"]["in"] != 3.00
    assert PRICING["claude-sonnet-5"]["out"] != 15.00
    # Sonnet 4.6 legitimately IS $3/$15 — the two must stay distinct.
    assert PRICING["claude-sonnet-4-6"] == {"in": 3.00, "out": 15.00, "cached_read": 0.30}


def test_cached_read_is_explicit_not_derived():
    """A None cached_read makes calculate_cost derive in_rate * 0.1.

    That fallback is a ratio, so it silently inherits a wrong input rate. With
    the old $3.00 input it produced $0.30/MTok instead of $0.20 — and on a
    cache-heavy workload that derived rate dominates the bill, not the headline
    output price.
    """
    for model, rates in CLAUDE_5.items():
        assert PRICING[model]["cached_read"] is not None, model
        assert PRICING[model]["cached_read"] == rates["in"] * 0.1


def test_no_claude_5_model_falls_through_to_default():
    default = PRICING["_default"]
    for model in CLAUDE_5:
        assert PRICING[model] != default, model


def test_measured_overcharge_is_a_uniform_1_5x():
    """Every component was off by the same multiple, so totals scaled uniformly.

    89 real sessions on this machine billed $344.16 against a true $229.44.
    """
    old = {"in": 3.00, "out": 15.00, "cached_read": 0.30}
    new = PRICING["claude-sonnet-5"]
    for field in ("in", "out", "cached_read"):
        # Tolerance, not equality: 0.3 / 0.2 is 1.4999999999999998 in binary float.
        assert abs(old[field] / new[field] - 1.5) < 1e-9, field


def test_cache_version_bumped_for_repricing():
    """Cached sessions store a computed cost, so a rate change must invalidate them."""
    import scan_cache
    assert scan_cache.CACHE_VERSION >= 10


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            fn()
    print("All tests passed!")
