"""GLM-5.3 pricing regression: ZCode emits raw modelIDs like GLM-5.3-Flash.

Before this, pricing_data.json had no glm-5.3 entries, so calculate_cost fell
through to PRICING["_default"] and mispriced every ZCode session. Rates follow
Z.ai's official list prices, corroborated by LiteLLM and the major
aggregators (models.dev's zai section currently lists a half-price tier).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import pricing  # noqa: E402


def test_glm_5_3_entries_exist():
    assert "glm-5.3-flash" in pricing.PRICING
    assert "glm-5.3" in pricing.PRICING


def test_glm_5_3_flash_billed_at_its_own_input_rate():
    rate = pricing.PRICING["glm-5.3-flash"]["in"]
    assert pricing.calculate_cost("GLM-5.3-Flash", 1_000_000, 0) == pytest.approx(rate)


def test_glm_5_3_flash_not_default_rated():
    default_in = pricing.PRICING["_default"]["in"]
    assert pricing.PRICING["glm-5.3-flash"]["in"] != default_in


def test_cache_read_uses_cached_rate():
    e = pricing.PRICING["glm-5.3-flash"]
    cost = pricing.calculate_cost("GLM-5.3-Flash", 1_000_000, 0, cached_tokens=1_000_000)
    assert cost == pytest.approx(e["in"] + e["cached_read"])


def test_glm_5_3_billed_at_its_own_input_rate():
    rate = pricing.PRICING["glm-5.3"]["in"]
    assert pricing.calculate_cost("GLM-5.3", 1_000_000, 0) == pytest.approx(rate)
