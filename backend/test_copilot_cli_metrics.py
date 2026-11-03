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


def test_grab_token_fields_finds_nested_usage_shape():
    # Per-message assistant.message payloads report usage the same nested way
    # modelMetrics does (see REAL_METRICS above) — NOT a flat `outputTokens`
    # key on the event. The old per-message fallback only ever read
    # `d.get("outputTokens")`, so it silently stayed 0 for every message on a
    # session lacking a clean session.shutdown (output AND cached always-zero
    # bug). _grab_token_fields must recurse into the nested shape to recover it.
    tot = {"input": 0, "output": 0, "cached": 0, "cache_creation": 0}
    found = main._grab_token_fields(
        {"model": "claude-haiku-4.5", "usage": {
            "inputTokens": 500, "outputTokens": 120,
            "cacheReadTokens": 80, "cacheWriteTokens": 20,
        }},
        tot,
    )
    assert found is True
    assert tot["output"] == 120
    assert tot["cached"] == 80
    assert tot["cache_creation"] == 20


def test_grab_token_fields_flat_shape_still_works():
    tot = {"input": 0, "output": 0, "cached": 0, "cache_creation": 0}
    found = main._grab_token_fields({"outputTokens": 42}, tot)
    assert found is True
    assert tot["output"] == 42


def test_grab_token_fields_nothing_found():
    tot = {"input": 0, "output": 0, "cached": 0, "cache_creation": 0}
    found = main._grab_token_fields({"model": "x", "content": "hello"}, tot)
    assert found is False
    assert tot == {"input": 0, "output": 0, "cached": 0, "cache_creation": 0}


# Real shape of a live (not-yet-shutdown) session's `session.usage_record.data.usage`
# — captured from ~/.copilot/session-state, trimmed to the fields relevant to
# this test. One of these is emitted per model call/turn; a long-running
# session with no clean shutdown can have hundreds of them, and
# _copilot_cli_tokens_from_metrics sums the recognized fields across all of
# them (same rollup+netting logic as a shutdown's modelMetrics).
REAL_USAGE_RECORD = {
    "model": "claude-sonnet-5.5",
    "inputTokens": 86076,
    "outputTokens": 603,
    "cacheReadTokens": 21429,
    "cacheWriteTokens": 64643,
    "reasoningTokens": 0,
    "cost": 1.0,
    "duration": 5204,
    "timeToFirstTokenMs": 1732.3383,
    "interTokenLatencyMs": 21.0227484848485,  # contains "token"+"in" — must NOT be counted as input
    "maxPromptTokens": 200000,  # static context-window limit — must NOT be counted as input
    "maxOutputTokens": 128000,  # static context-window limit — must NOT be counted as output
    "toolTokenCount": 14299,  # unrelated tool-definition metric — must NOT be counted
    "copilotUsage": {
        "tokenDetails": [
            {"tokenCount": 4, "tokenType": "input"},
            {"tokenCount": 21429, "tokenType": "cache_read"},
            {"tokenCount": 64643, "tokenType": "cache_write"},
            {"tokenCount": 603, "tokenType": "output"},
        ],
    },
}


def test_live_usage_record_ignores_lookalike_token_fields():
    # A looser substring-on-"token" match (an earlier version of this code)
    # sweeps up maxPromptTokens/maxOutputTokens/interTokenLatencyMs/
    # toolTokenCount/tokenDetails[].tokenCount too, inflating a real 480-call
    # session's output from ~400K to ~18M tokens. Only the exact known field
    # names may be counted.
    tot = {"input": 0, "output": 0, "cached": 0, "cache_creation": 0}
    found = main._grab_token_fields(REAL_USAGE_RECORD, tot)
    assert found is True
    assert tot == {"input": 86076, "output": 603, "cached": 21429, "cache_creation": 64643}


def test_usage_record_rollup_across_many_turns():
    # Simulate a session with no session.shutdown event (still running / killed
    # abruptly) whose only usage signal is a sequence of session.usage_record
    # events — the real-world case behind the output/cached always-zero bug.
    records = [REAL_USAGE_RECORD, REAL_USAGE_RECORD]
    tot = main._copilot_cli_tokens_from_metrics(records)
    assert tot["output"] == 1206
    assert tot["cached"] == 42858
    assert tot["cache_creation"] == 129286
    # gross input (172152) minus cache traffic (172144) nets to 8
    assert tot["input"] == 8


def test_merge_prefers_rollup_over_per_message_fallback():
    rollup = {"input": 10, "output": 20, "cached": 30, "cache_creation": 5}
    msg_tot = {"input": 999, "output": 999, "cached": 999, "cache_creation": 999}
    tokens = main._merge_copilot_cli_tokens(rollup, msg_tot, in_estimate=111)
    assert tokens["input"] == 10 and tokens["output"] == 20
    assert tokens["cached"] == 30 and tokens["cache_creation"] == 5
    assert tokens["total"] == 60


def test_merge_fills_gaps_field_by_field_when_rollup_partial():
    # A Copilot CLI version/shape where the rollup only reported output, but
    # the per-message scan (or char estimate, for input) picked up the rest —
    # neither method should blank out data the other one found.
    rollup = {"output": 50}
    msg_tot = {"input": 0, "output": 0, "cached": 7, "cache_creation": 3}
    tokens = main._merge_copilot_cli_tokens(rollup, msg_tot, in_estimate=200)
    assert tokens["output"] == 50       # from rollup
    assert tokens["cached"] == 7        # from per-message scan
    assert tokens["cache_creation"] == 3
    # char-count estimate (200) minus the cache traffic found via the
    # per-message scan (7 + 3 = 10), same gross-input netting as the rollup.
    assert tokens["input"] == 190


def test_merge_with_no_rollup_falls_back_entirely_to_per_message():
    tokens = main._merge_copilot_cli_tokens(
        None, {"input": 0, "output": 15, "cached": 0, "cache_creation": 0}, in_estimate=40)
    assert tokens == {"input": 40, "output": 15, "cached": 0, "cache_creation": 0, "total": 55}


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
