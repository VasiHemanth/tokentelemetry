"""Tests for Copilot CLI token extraction/merge (_grab_token_fields,
_copilot_cli_tokens_from_metrics, _merge_copilot_cli_tokens).

Copilot's session.shutdown.modelMetrics / session.usage_record report
usage.inputTokens as GROSS (net input + cacheReadTokens + cacheWriteTokens —
verifiable against the sibling tokenDetails breakdown). Extraction returns
this raw, un-netted data with per-field presence (None = never reported,
distinct from an explicit 0); the gross-input/cache netting and the
rollup-vs-fallback field selection both happen exactly once, in
_merge_copilot_cli_tokens, after every source (shutdown rollup, live
session.usage_record rollup, per-message scan) has been combined — doing
either earlier, per-source, either double-bills cache traffic reported by a
different source than the one netted, or overwrites an explicit zero with a
fallback estimate.

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


def test_extraction_is_raw_gross_not_netted():
    # _copilot_cli_tokens_from_metrics no longer nets cache traffic out of
    # input itself — that's deferred to _merge_copilot_cli_tokens, once, after
    # all sources are combined (see module docstring). This function's job is
    # just faithful raw extraction.
    tot = main._copilot_cli_tokens_from_metrics(REAL_METRICS)
    assert tot == {
        "input": 63219,        # gross, NOT netted against cache traffic here
        "output": 1365,
        "cached": 34516,       # reads only
        "cache_creation": 28676,  # writes split out, billed at write rate
    }


def test_reasoning_tokens_not_counted_as_input():
    tot = main._copilot_cli_tokens_from_metrics(
        {"usage": {"inputTokens": 100, "outputTokens": 50, "reasoningTokens": 999}})
    assert tot["input"] == 100
    assert tot["output"] == 50


def test_simple_prompt_completion_shape_unchanged():
    tot = main._copilot_cli_tokens_from_metrics(
        {"gpt-x": {"promptTokens": 120, "completionTokens": 30}})
    assert tot["input"] == 120
    assert tot["output"] == 30
    assert tot["cached"] is None and tot["cache_creation"] is None


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
    tot = {"input": None, "output": None, "cached": None, "cache_creation": None}
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
    tot = {"input": None, "output": None, "cached": None, "cache_creation": None}
    found = main._grab_token_fields({"outputTokens": 42}, tot)
    assert found is True
    assert tot["output"] == 42


def test_grab_token_fields_nothing_found():
    tot = {"input": None, "output": None, "cached": None, "cache_creation": None}
    found = main._grab_token_fields({"model": "x", "content": "hello"}, tot)
    assert found is False
    assert tot == {"input": None, "output": None, "cached": None, "cache_creation": None}


def test_grab_token_fields_preserves_explicit_zero():
    # An explicitly reported 0 must be distinguishable from "never reported"
    # (None) so the merge step doesn't treat it as missing and overwrite it
    # with a fallback — a field that's genuinely 0 stays 0, not None.
    tot = {"input": None, "output": None, "cached": None, "cache_creation": None}
    found = main._grab_token_fields({"inputTokens": 0, "outputTokens": 5}, tot)
    assert found is True
    assert tot["input"] == 0
    assert tot["output"] == 5
    assert tot["cached"] is None  # genuinely never reported


# Real shape of a live (not-yet-shutdown) session's `session.usage_record.data.usage`
# — captured from ~/.copilot/session-state, trimmed to the fields relevant to
# this test. One of these is emitted per model call/turn; a long-running
# session with no clean shutdown can have hundreds of them, and
# _copilot_cli_tokens_from_metrics sums the recognized fields across all of
# them (same rollup logic as a shutdown's modelMetrics).
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
    tot = {"input": None, "output": None, "cached": None, "cache_creation": None}
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
    assert tot["input"] == 172152  # gross, un-netted — netting happens in the merge step


def test_merge_nets_gross_input_against_combined_cache_once():
    # gross input 63219 minus cache traffic 34516+28676=63192, nets to 27 —
    # matches tokenDetails's net input.tokenCount for REAL_METRICS above.
    tot = main._copilot_cli_tokens_from_metrics(REAL_METRICS)
    tokens = main._merge_copilot_cli_tokens(tot, None, {}, in_estimate=0)
    assert tokens["input"] == 27
    assert tokens["output"] == 1365
    assert tokens["cached"] == 34516
    assert tokens["cache_creation"] == 28676


def test_merge_shutdown_wins_per_field_over_live_usage():
    shutdown_rollup = {"input": None, "output": 20, "cached": None, "cache_creation": None}
    usage_rollup = {"input": 100, "output": 999, "cached": 60, "cache_creation": 0}
    msg_tot = {"input": None, "output": None, "cached": None, "cache_creation": None}
    tokens = main._merge_copilot_cli_tokens(shutdown_rollup, usage_rollup, msg_tot, in_estimate=0)
    # output comes from shutdown (it reported it); input/cached/cache_creation
    # fall through to the live usage rollup since shutdown left them unreported.
    assert tokens["output"] == 20
    # gross input (100) nets against the combined cache (60+0=60) exactly once,
    # after merging — not discarded just because shutdown had *a* value for output.
    assert tokens["input"] == 40
    assert tokens["cached"] == 60
    assert tokens["cache_creation"] == 0


def test_merge_does_not_double_bill_cache_from_a_different_source():
    # Regression for the PR #448 review finding: a partial shutdown rollup
    # reporting only input/output, with the live usage rollup separately
    # reporting cache traffic. The combined input must net against the
    # combined cache total, not stay at the un-netted gross value just because
    # the cache counters came from a different source than the input did.
    shutdown_rollup = {"input": 100, "output": 20, "cached": None, "cache_creation": None}
    usage_rollup = {"input": None, "output": None, "cached": 60, "cache_creation": 0}
    msg_tot = {"input": None, "output": None, "cached": None, "cache_creation": None}
    tokens = main._merge_copilot_cli_tokens(shutdown_rollup, usage_rollup, msg_tot, in_estimate=0)
    assert tokens["input"] == 40   # 100 - 60, not 100
    assert tokens["cached"] == 60
    assert tokens["output"] == 20


def test_merge_preserves_explicit_zero_input_after_normalization():
    # Regression for the PR #448 review finding: 100 gross input tokens and
    # 100 cache-read tokens correctly net to 0 — merging with a nonzero prompt
    # estimate must NOT override that explicit, correctly-computed zero.
    shutdown_rollup = {"input": 100, "output": 5, "cached": 100, "cache_creation": None}
    tokens = main._merge_copilot_cli_tokens(shutdown_rollup, None, {}, in_estimate=10)
    assert tokens["input"] == 0


def test_merge_fills_gaps_field_by_field_when_rollup_partial():
    # A Copilot CLI version/shape where the rollup only reported output, but
    # the per-message scan (or char estimate, for input) picked up the rest —
    # neither method should blank out data the other one found.
    shutdown_rollup = {"input": None, "output": 50, "cached": None, "cache_creation": None}
    msg_tot = {"input": None, "output": None, "cached": 7, "cache_creation": 3}
    tokens = main._merge_copilot_cli_tokens(shutdown_rollup, None, msg_tot, in_estimate=200)
    assert tokens["output"] == 50       # from shutdown rollup
    assert tokens["cached"] == 7        # from per-message scan
    assert tokens["cache_creation"] == 3
    # Regression for the PR #448 second-review finding: the char-count
    # estimate only ever counts user-message text, never cached context, so
    # it's already net — it must NOT be reduced by cache traffic found
    # elsewhere (that would understate input/cost for a prompt that also used
    # a lot of cache). Netting only applies to a source that actually
    # reported a gross input counter, which no source did here.
    assert tokens["input"] == 200


def test_merge_nets_a_reported_input_even_when_cache_comes_from_elsewhere():
    # Unlike the char-count estimate (see test above), an input counter that
    # WAS reported (by any of the three sources) is gross by definition and
    # must still be netted against the combined cache total.
    shutdown_rollup = {"input": 50, "output": None, "cached": None, "cache_creation": None}
    msg_tot = {"input": None, "output": None, "cached": 7, "cache_creation": 3}
    tokens = main._merge_copilot_cli_tokens(shutdown_rollup, None, msg_tot, in_estimate=200)
    assert tokens["input"] == 40  # 50 - (7 + 3), not the unrelated 200 estimate


def test_merge_with_no_rollup_falls_back_entirely_to_per_message():
    tokens = main._merge_copilot_cli_tokens(
        None, None, {"input": None, "output": 15, "cached": None, "cache_creation": None}, in_estimate=40)
    assert tokens == {"input": 40, "output": 15, "cached": 0, "cache_creation": 0, "total": 55}


def test_merge_guards_against_negative_input_regardless_of_source():
    # Cache traffic larger than the selected input must not drive input
    # negative, whichever source each field ultimately came from.
    shutdown_rollup = {"input": 10, "output": 1, "cached": None, "cache_creation": None}
    usage_rollup = {"input": None, "output": None, "cached": 200, "cache_creation": 100}
    tokens = main._merge_copilot_cli_tokens(shutdown_rollup, usage_rollup, {}, in_estimate=0)
    assert tokens["input"] == 10  # subtraction guarded off, not -290
    assert tokens["cached"] == 200
    assert tokens["cache_creation"] == 100


def test_grab_token_fields_ignores_booleans():
    # bool is a subclass of int in Python — a stray boolean flag whose name
    # happens to match (e.g. a future "cacheReadTokens": true malformed
    # payload) must not be counted as a token value.
    tot = {"input": None, "output": None, "cached": None, "cache_creation": None}
    found = main._grab_token_fields({"outputTokens": True, "cacheReadTokens": False}, tot)
    assert found is False
    assert tot == {"input": None, "output": None, "cached": None, "cache_creation": None}


def test_copilot_cli_tokens_from_metrics_tolerates_garbage_list_entries():
    # A metrics/usage_records list can contain non-dict junk (a future shape
    # emitting a stray string/None alongside real entries) — must not crash,
    # and must still extract the real entries.
    tot = main._copilot_cli_tokens_from_metrics(
        [{"inputTokens": 10, "outputTokens": 2}, None, "garbage", 42, {"outputTokens": 3}])
    assert tot["input"] == 10
    assert tot["output"] == 5


def test_copilot_cli_tokens_from_metrics_empty_list_returns_none():
    assert main._copilot_cli_tokens_from_metrics([]) is None


# ---------------------------------------------------------------------------
# End-to-end: _parse_copilot_cli_session_events against synthetic events.jsonl
# rows, covering different Copilot CLI versions/shapes in one place.
# ---------------------------------------------------------------------------

def _event(evtype, data, ts):
    return {"type": evtype, "data": data, "timestamp": ts}


def test_end_to_end_old_cli_format_shutdown_only_no_usage_records():
    # Backward compatibility: the format Copilot CLI used before #448 (and
    # before session.usage_record existed at all) — no per-turn usage events,
    # just a single session.shutdown.modelMetrics rollup at the end. This is
    # the shape the original PR author's "retro-compatible by design" claim
    # needs to hold for.
    rows = [
        _event("session.start", {"context": {"cwd": "/old/project"}, "startTime": "2026-01-01T00:00:00Z"},
               "2026-01-01T00:00:00Z"),
        _event("user.message", {"content": "fix the bug"}, "2026-01-01T00:00:01Z"),
        _event("assistant.message", {"model": "gpt-4o", "content": "done"}, "2026-01-01T00:00:02Z"),
        _event("session.shutdown", {"modelMetrics": {
            "gpt-4o": {"usage": {"inputTokens": 500, "outputTokens": 80,
                                  "cacheReadTokens": 100, "cacheWriteTokens": 0}},
        }}, "2026-01-01T00:00:03Z"),
    ]
    parsed = main._parse_copilot_cli_session_events(rows, fallback_ts="2026-01-01T00:00:03Z")
    assert parsed["project_path"] == "/old/project"
    assert parsed["model"] == "gpt-4o"
    assert parsed["tokens"]["input"] == 400   # 500 gross - 100 cache
    assert parsed["tokens"]["output"] == 80
    assert parsed["tokens"]["cached"] == 100


def test_end_to_end_very_old_cli_format_flat_output_tokens_on_message():
    # An even older/simpler hypothetical shape (what the original bug report
    # assumed before real data was inspected): assistant.message carries a
    # flat outputTokens field directly, and there's no shutdown/usage_record
    # at all (process killed, or a version predating both). Must still
    # recover output via the per-message scan + char-count input estimate.
    rows = [
        _event("user.message", {"content": "a" * 40}, "2026-01-01T00:00:00Z"),  # ~10 token estimate
        _event("assistant.message", {"model": "claude-3", "outputTokens": 25}, "2026-01-01T00:00:01Z"),
        _event("assistant.message", {"model": "claude-3", "outputTokens": 15}, "2026-01-01T00:00:02Z"),
    ]
    parsed = main._parse_copilot_cli_session_events(rows, fallback_ts="2026-01-01T00:00:02Z")
    assert parsed["model"] == "claude-3"
    assert parsed["tokens"]["output"] == 40  # 25 + 15, summed across messages
    assert parsed["tokens"]["input"] == 10   # 40 chars // 4, no cache to net out
    assert parsed["tokens"]["cached"] == 0


def test_end_to_end_live_session_usage_record_only_no_shutdown():
    # The real-world bug this whole fix addresses: a still-running (or
    # killed) CLI session with only session.usage_record events, no shutdown.
    rows = [
        _event("session.start", {"context": {"cwd": "/live/project"}}, "2026-01-01T00:00:00Z"),
        _event("user.message", {"content": "go"}, "2026-01-01T00:00:01Z"),
        _event("assistant.message", {"model": "claude-sonnet-5.5"}, "2026-01-01T00:00:02Z"),
        _event("session.usage_record", {"usage": {
            "model": "claude-sonnet-5.5", "inputTokens": 1000, "outputTokens": 50,
            "cacheReadTokens": 200, "cacheWriteTokens": 100,
            "maxPromptTokens": 200000, "maxOutputTokens": 128000,  # must be ignored
        }}, "2026-01-01T00:00:03Z"),
        _event("session.usage_record", {"usage": {
            "model": "claude-sonnet-5.5", "inputTokens": 1300, "outputTokens": 40,
            "cacheReadTokens": 250, "cacheWriteTokens": 50,
        }}, "2026-01-01T00:00:04Z"),
    ]
    parsed = main._parse_copilot_cli_session_events(rows, fallback_ts="2026-01-01T00:00:04Z")
    assert parsed["project_path"] == "/live/project"
    assert parsed["tokens"]["output"] == 90        # 50 + 40
    assert parsed["tokens"]["cached"] == 450       # 200 + 250
    assert parsed["tokens"]["cache_creation"] == 150  # 100 + 50
    assert parsed["tokens"]["input"] == 1700       # (1000+1300) - (450+150)


def test_end_to_end_model_switch_tracked_in_models_used():
    rows = [
        _event("assistant.message", {"model": "gpt-4o"}, "2026-01-01T00:00:00Z"),
        _event("session.model_change", {"newModel": "claude-sonnet-5"}, "2026-01-01T00:00:01Z"),
        _event("assistant.message", {"model": "claude-sonnet-5"}, "2026-01-01T00:00:02Z"),
    ]
    parsed = main._parse_copilot_cli_session_events(rows, fallback_ts="2026-01-01T00:00:02Z")
    assert parsed["model"] == "gpt-4o"  # first-seen model wins as the primary label
    assert parsed["models_used"] == ["gpt-4o", "claude-sonnet-5"]


def test_end_to_end_malformed_rows_do_not_crash():
    # Rows missing "data" or "type" entirely (truncated/corrupted JSONL line
    # recovered as a bare dict by _load_copilot_cli_events) must be skipped
    # gracefully rather than raising.
    rows = [{}, {"type": "assistant.message"}, {"type": "session.usage_record", "data": {}},
            _event("user.message", {"content": "hi"}, "2026-01-01T00:00:00Z")]
    parsed = main._parse_copilot_cli_session_events(rows, fallback_ts="2026-01-01T00:00:00Z")
    assert parsed["tokens"]["input"] == 0  # "hi" // 4 == 0, no crash
    assert parsed["model"] is None


def test_end_to_end_no_events_at_all_falls_back_to_zero_and_timestamp():
    parsed = main._parse_copilot_cli_session_events([], fallback_ts="2026-01-01T00:00:00Z")
    assert parsed["timestamp"] == "2026-01-01T00:00:00Z"
    assert parsed["tokens"] == {"input": 0, "output": 0, "cached": 0, "cache_creation": 0, "total": 0}
    assert parsed["project_path"] == "unknown"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
