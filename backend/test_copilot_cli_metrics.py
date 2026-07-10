"""Tests for _copilot_cli_tokens_from_metrics (Copilot CLI shutdown rollup).

Copilot's session.shutdown.modelMetrics reports usage.inputTokens as GROSS
(net input + cacheReadTokens + cacheWriteTokens — verifiable against the
sibling tokenDetails breakdown). The old heuristic summed inputTokens AND
both cache counters, double-billing all cache traffic, and its "in" substring
match also swept reasoningTokens (reasonINg) into input.

Run: pytest backend/test_copilot_cli_metrics.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import main  # noqa: E402


# Real shape captured from ~/.copilot/session-state (claude-haiku-4.5):
# tokenDetails proves inputTokens is gross: 27 + 34516 + 28676 = 63219.
REAL_METRICS = {
    "claude-haiku-4.5": {
        "requests": {"count": 3, "cost": 0.33},
        "usage": {
            "inputTokens": 63219,
            "outputTokens": 1365,
            "cacheReadTokens": 34516,
            "cacheWriteTokens": 28676,
            "reasoningTokens": 355,
        },
        "totalNanoAiu": 4614860000,
        "tokenDetails": {
            "input": {"tokenCount": 27},
            "cache_read": {"tokenCount": 34516},
            "cache_write": {"tokenCount": 28676},
            "output": {"tokenCount": 1365},
        },
    }
}


def test_gross_input_nets_out_cache_traffic():
    tot = main._copilot_cli_tokens_from_metrics(REAL_METRICS)
    assert tot == {
        "input": 27,           # 63219 - 34516 - 28676, matches tokenDetails
        "output": 1365,
        "cached": 34516,       # reads only
        "cache_creation": 28676,  # writes split out, billed at write rate
    }


def test_reasoning_tokens_not_counted_as_input():
    tot = main._copilot_cli_tokens_from_metrics(
        {"usage": {"inputTokens": 100, "outputTokens": 50, "reasoningTokens": 999}})
    assert tot["input"] == 100
    assert tot["output"] == 50


def test_net_input_shape_not_driven_negative():
    # A hypothetical future shape reporting NET input alongside cache
    # counters: input (10) < cache traffic (300), so the gross-input
    # subtraction must not fire.
    tot = main._copilot_cli_tokens_from_metrics(
        {"usage": {"inputTokens": 10, "outputTokens": 5,
                   "cacheReadTokens": 200, "cacheWriteTokens": 100}})
    assert tot["input"] == 10
    assert tot["cached"] == 200
    assert tot["cache_creation"] == 100


def test_simple_prompt_completion_shape_unchanged():
    tot = main._copilot_cli_tokens_from_metrics(
        {"gpt-x": {"promptTokens": 120, "completionTokens": 30}})
    assert tot["input"] == 120
    assert tot["output"] == 30
    assert tot["cached"] == 0 and tot["cache_creation"] == 0


def test_unusable_metrics_return_none():
    assert main._copilot_cli_tokens_from_metrics(None) is None
    assert main._copilot_cli_tokens_from_metrics({"requests": {"count": 3}}) is None
    assert main._copilot_cli_tokens_from_metrics("nope") is None


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
