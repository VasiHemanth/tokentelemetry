"""Date-banded rates: price tokens at the rate in force when they were generated.

A provider that reprices does not reprice the past. Correcting a table without
this would rewrite every historical session at today's rate — which is what
fixing DeepSeek (#303) did before these bands existed, overstating a pre-August
Flash session by 2.2x and a pre-August Pro session by 4x.

Covered here: the band boundaries themselves, the invariant that the newest band
matches the live table (so the two can't drift on the next repricing), and the
timestamp coercion that decides which side of a boundary a session lands on.
"""

from datetime import datetime, timezone

import pricing
from pricing import PRICING, PRICING_BY_PROVIDER, calculate_cost

MTOK = 1_000_000
DEEPSEEK_CUTOVER = "2026-08-16T16:00:00Z"


# --- the invariant that keeps the bands honest -----------------------------

def test_newest_band_matches_the_live_flat_table():
    for model, bands in pricing.PRICING_HISTORY.items():
        newest = bands[-1][1]
        assert PRICING[model] == newest, (
            f"{model}: table {PRICING[model]} != newest band {newest}. "
            "A repricing must add a band AND update the table."
        )


def test_newest_band_matches_the_live_provider_table():
    for key, bands in pricing.PRICING_BY_PROVIDER_HISTORY.items():
        if key in PRICING_BY_PROVIDER:
            assert PRICING_BY_PROVIDER[key] == bands[-1][1], key


def test_bands_are_sorted_ascending():
    for model, bands in pricing.PRICING_HISTORY.items():
        starts = [pricing._as_utc(b[0]) for b in bands]
        assert starts == sorted(starts), model


def test_no_at_is_unchanged_behaviour():
    """Omitting `at` must price at current rates, exactly as before."""
    for model in pricing.PRICING_HISTORY:
        assert calculate_cost(model, MTOK, MTOK) == calculate_cost(
            model, MTOK, MTOK, at=datetime.now(timezone.utc)
        )


# --- boundaries -------------------------------------------------------------

def test_deepseek_boundary_is_inclusive_from_the_cutover_instant():
    before = calculate_cost("deepseek-v4-flash", 0, MTOK, at="2026-08-16T15:59:59Z")
    at_it = calculate_cost("deepseek-v4-flash", 0, MTOK, at=DEEPSEEK_CUTOVER)
    after = calculate_cost("deepseek-v4-flash", 0, MTOK, at="2026-08-16T16:00:01Z")
    assert before == 0.28
    assert at_it == 0.66, "the cutover instant itself is the NEW rate"
    assert after == 0.66


def test_deepseek_pro_pre_cut_uses_the_promotional_price():
    """V4-Pro's pre-cut band is $0.435/$0.87, not the $1.74/$3.48 list.

    Pro launched at list under a 75% promotion that was extended past its stated
    31 May deadline and stayed the effective price until the repricing. Billing
    list would overstate every pre-August Pro session by 4x.
    """
    assert calculate_cost("deepseek-v4-pro", MTOK, 0, at="2026-07-01T00:00:00Z") == 0.435
    assert calculate_cost("deepseek-v4-pro", MTOK, 0, at="2026-08-25T00:00:00Z") == 0.66


def test_gpt56_two_cuts_land_on_their_own_dates():
    # Terra and Luna were cut 2026-07-30; Sol was not touched until 2026-08-22.
    assert calculate_cost("gpt-5.6-terra", 0, MTOK, at="2026-07-29T00:00:00Z") == 15.00
    assert calculate_cost("gpt-5.6-terra", 0, MTOK, at="2026-07-31T00:00:00Z") == 12.00
    assert calculate_cost("gpt-5.6-luna", 0, MTOK, at="2026-07-29T00:00:00Z") == 6.00
    assert calculate_cost("gpt-5.6-luna", 0, MTOK, at="2026-07-31T00:00:00Z") == 1.20
    # Sol still at the old rate on the day Terra/Luna moved.
    assert calculate_cost("gpt-5.6-sol", 0, MTOK, at="2026-07-31T00:00:00Z") == 30.00
    assert calculate_cost("gpt-5.6-sol", 0, MTOK, at="2026-08-23T00:00:00Z") == 20.00


def test_timestamp_older_than_every_band_uses_the_earliest():
    assert calculate_cost("deepseek-v4-flash", 0, MTOK, at="2019-01-01T00:00:00Z") == 0.28


def test_provider_qualified_lookup_is_also_banded():
    """Passing provider must not bypass the historical rate."""
    for prov, model in (("deepseek", "deepseek-v4-pro"), ("openai", "gpt-5.6-luna")):
        old = calculate_cost(model, 0, MTOK, provider=prov, at="2026-07-01T00:00:00Z")
        new = calculate_cost(model, 0, MTOK, provider=prov, at="2026-08-25T00:00:00Z")
        assert old != new, (prov, model)


# --- timestamp coercion -----------------------------------------------------

def test_naive_datetime_is_treated_as_utc():
    """Session timestamps arrive both aware and naive from a dozen harnesses."""
    naive = datetime(2026, 7, 1, 12, 0, 0)
    aware = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert calculate_cost("deepseek-v4-flash", 0, MTOK, at=naive) == \
           calculate_cost("deepseek-v4-flash", 0, MTOK, at=aware)


def test_non_utc_offset_is_converted_not_ignored():
    """21:00+07:00 is 14:00Z — before the 16:00Z cutover, despite the later clock."""
    assert calculate_cost("deepseek-v4-flash", 0, MTOK, at="2026-08-16T21:00:00+07:00") == 0.28


def test_day_string_is_accepted():
    """tokens_by_day passes a 'YYYY-MM-DD' key."""
    assert calculate_cost("deepseek-v4-flash", 0, MTOK, at="2026-07-01") == 0.28


def test_unparseable_at_falls_back_to_current_rates():
    for bad in ("", "not-a-date", 12345, None):
        assert calculate_cost("deepseek-v4-flash", 0, MTOK, at=bad) == 0.66


def test_unbanded_model_ignores_at():
    """Only models that actually repriced are affected."""
    a = calculate_cost("claude-sonnet-4-6", 0, MTOK)
    b = calculate_cost("claude-sonnet-4-6", 0, MTOK, at="2019-01-01T00:00:00Z")
    assert a == b


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            fn()
    print("All tests passed!")
