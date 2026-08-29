"""DeepSeek V4 direct pricing (issue #303).

DeepSeek repriced on 2026-08-16; the curated tables still carried the pre-repricing
rates, so every direct DeepSeek session was billed at ~45% of actual. These tests
pin the documented OFF-PEAK rates and guard the two structural traps that let the
staleness hide:

1. The flat table and the provider-keyed table must agree. models.dev ships
   ("deepseek", "deepseek-v4-pro") at $0.435/$0.87, and the bundled overlay only
   yields to an inline entry. Without inline tuples the same model priced 4x apart
   depending on whether the caller passed a provider — which is exactly what
   issue #304's fix would have unmasked.
2. vision-exp must resolve to its own entry, not to a fuzzy prefix hit on
   deepseek-v4-flash.

Rates: https://api-docs.deepseek.com/quick_start/pricing
"""

import pricing
from pricing import PRICING, PRICING_BY_PROVIDER, calculate_cost

MTOK = 1_000_000

# Documented off-peak rates per 1M tokens. Peak (01:00-04:00 / 06:00-10:00 UTC,
# Mon-Fri) is exactly 2x these; calculate_cost has no timestamp so we bill off-peak.
OFFPEAK = {
    "deepseek-v4-flash":            {"in": 0.22, "out": 0.66, "cached_read": 0.007},
    "deepseek-v4-flash-vision-exp": {"in": 0.22, "out": 0.66, "cached_read": 0.007},
    "deepseek-chat":                {"in": 0.22, "out": 0.66, "cached_read": 0.007},
    "deepseek-reasoner":            {"in": 0.22, "out": 0.66, "cached_read": 0.007},
    "deepseek-v4-pro":              {"in": 0.66, "out": 1.98, "cached_read": 0.022},
}


def test_flat_table_matches_official_offpeak():
    for model, rates in OFFPEAK.items():
        assert PRICING[model] == rates, f"{model}: {PRICING[model]} != {rates}"


def test_provider_keyed_matches_flat():
    """A DeepSeek model must cost the same whether or not the caller knows the provider.

    This is the #303/#304 interaction guard: the scanners in #304 started passing
    provider="deepseek", which routes the lookup through PRICING_BY_PROVIDER. If
    that table falls back to the models.dev overlay the cost silently drops 4x.
    """
    for model, rates in OFFPEAK.items():
        assert PRICING_BY_PROVIDER[("deepseek", model)] == rates
        without = calculate_cost(model, MTOK, MTOK)
        with_prov = calculate_cost(model, MTOK, MTOK, provider="deepseek")
        assert without == with_prov, f"{model}: {without} vs {with_prov}"


def test_vision_exp_is_explicit_not_a_fuzzy_hit():
    """vision-exp resolves to its own key, not to deepseek-v4-flash by substring.

    _fuzzy_key_matches only rejects a *dotted* version suffix, so "-vision-exp"
    matches "deepseek-v4-flash" and would price any future flash-* variant at
    flash's rate regardless of what it actually costs.
    """
    assert "deepseek-v4-flash-vision-exp" in PRICING
    # The fuzzy path would still match; the point is we never reach it.
    assert pricing._fuzzy_key_matches("deepseek-v4-flash", "deepseek-v4-flash-vision-exp")


def test_pro_is_not_the_pre_repricing_rate():
    """Regression: the stale $1.74/$3.48 must not come back."""
    assert PRICING["deepseek-v4-pro"]["in"] != 1.74
    assert PRICING["deepseek-v4-pro"]["out"] != 3.48
    # Nor the models.dev value the overlay would supply.
    assert PRICING_BY_PROVIDER[("deepseek", "deepseek-v4-pro")]["in"] != 0.435


def test_reported_case_from_issue_303():
    """The exact session in the report: 5,369 in / 13,615 out, all cache-miss."""
    cost = calculate_cost("deepseek-v4-flash-vision-exp", 5369, 13615, 0, provider="deepseek")
    expected = (5369 * 0.22 + 13615 * 0.66) / MTOK  # $0.010167
    assert abs(cost - expected) < 1e-9, f"{cost} != {expected}"


def test_overlay_does_not_clobber_curated_date():
    """PRICING_UPDATED describes the inline table, not the models.dev snapshot.

    The overlay used to overwrite it, so a three-month-stale curated rate was
    reported to the UI under the snapshot's fresh date.
    """
    assert pricing.PRICING_UPDATED == "2026-08-29"
    if pricing.PRICING_OVERLAY_UPDATED is not None:
        assert pricing.PRICING_OVERLAY_UPDATED != pricing.PRICING_UPDATED


if __name__ == "__main__":
    test_flat_table_matches_official_offpeak()
    test_provider_keyed_matches_flat()
    test_vision_exp_is_explicit_not_a_fuzzy_hit()
    test_pro_is_not_the_pre_repricing_rate()
    test_reported_case_from_issue_303()
    test_overlay_does_not_clobber_curated_date()
    print("All tests passed!")
