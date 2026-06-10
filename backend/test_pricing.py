"""Tests for prompt-cache pricing in calculate_cost (issue #68).

Anthropic bills cache-WRITE tokens (cache_creation_input_tokens) at 1.25x the
input rate, distinct from cache-READ tokens (billed at the cheap cached_read
rate). These tests pin that behaviour and guard backward compatibility of the
positional signature.
"""

from pricing import calculate_cost


# claude-sonnet-4-6: in=3.00, out=15.00, cached_read=0.30 (per MTok)
SONNET = "claude-sonnet-4-6"
IN_RATE = 3.00
CACHED_READ_RATE = 0.30
WRITE_RATE = IN_RATE * 1.25  # 3.75

MTOK = 1_000_000


def test_cache_write_priced_at_1_25x_input():
    """1M cache-write tokens cost exactly 1.25x the input rate."""
    cost = calculate_cost(SONNET, 0, 0, 0, cache_creation_tokens=MTOK)
    assert cost == WRITE_RATE  # 3.75
    # Sanity: that's 1.25x what 1M plain input tokens would cost.
    input_only = calculate_cost(SONNET, MTOK, 0, 0)
    assert cost == input_only * 1.25


def test_cache_write_1h_priced_at_2x_input():
    """1h TTL cache-write tokens cost exactly 2x the input rate."""
    cost = calculate_cost(SONNET, 0, 0, 0, cache_creation_tokens=MTOK, cache_creation_1h_tokens=MTOK)
    assert cost == IN_RATE * 2.0
    input_only = calculate_cost(SONNET, MTOK, 0, 0)
    assert cost == input_only * 2.0


def test_cache_read_still_priced_at_cached_read_rate():
    """Cache-read tokens keep using the cached_read rate, not the write rate."""
    cost = calculate_cost(SONNET, 0, 0, MTOK)
    assert cost == CACHED_READ_RATE  # 0.30


def test_cache_write_not_priced_at_read_rate_regression():
    """Regression for #68: writes must NOT be billed at the cheap read rate."""
    write_cost = calculate_cost(SONNET, 0, 0, 0, cache_creation_tokens=MTOK)
    read_cost = calculate_cost(SONNET, 0, 0, MTOK)
    assert write_cost != read_cost
    # The bug under-priced writes ~12.5x; assert we're well above the read rate.
    assert write_cost > read_cost * 10


def test_backward_compat_default_param_unchanged():
    """Omitting cache_creation_tokens gives the same result as before (= 0)."""
    legacy = calculate_cost(SONNET, 1000, 500, 200)
    explicit_zero = calculate_cost(SONNET, 1000, 500, 200, cache_creation_tokens=0)
    assert legacy == explicit_zero


def test_backward_compat_positional_provider_still_works():
    """The new param is last, so existing positional provider calls are intact."""
    with_provider = calculate_cost(SONNET, 1000, 500, 200, "anthropic")
    keyword = calculate_cost(SONNET, 1000, 500, 200, provider="anthropic")
    assert with_provider == keyword


def test_combined_read_and_write():
    """Read and write contribute independently and additively."""
    cost = calculate_cost(SONNET, 0, 0, MTOK, cache_creation_tokens=MTOK)
    expected = CACHED_READ_RATE + WRITE_RATE  # 0.30 + 3.75
    assert cost == expected


def test_cache_write_uses_input_rate_even_without_cached_read_config():
    """When a model lacks an explicit cached_read, write rate still derives from input."""
    # groq llama models have cached_read=None -> read falls back to 0.1x input,
    # but write must still be 1.25x input.
    model = "llama-3.3-70b-versatile"
    in_rate = 0.59
    write = calculate_cost(model, 0, 0, 0, provider="groq", cache_creation_tokens=MTOK)
    assert write == in_rate * 1.25

if __name__ == "__main__":
    test_cache_write_priced_at_1_25x_input()
    test_cache_write_1h_priced_at_2x_input()
    test_cache_read_still_priced_at_cached_read_rate()
    test_cache_write_not_priced_at_read_rate_regression()
    test_backward_compat_default_param_unchanged()
    test_backward_compat_positional_provider_still_works()
    test_combined_read_and_write()
    test_cache_write_uses_input_rate_even_without_cached_read_config()
    print("All tests passed!")
