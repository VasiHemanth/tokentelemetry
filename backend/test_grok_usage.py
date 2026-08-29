"""Grok billed usage: unified.jsonl beats the context-window footprint."""

import json
from pathlib import Path

import pytest

import main
from pricing import calculate_cost, calculate_xai_turn_cost, PRICING


SID = "01a0test-0000-0000-0000-000000000001"
SID_NO_LOG = "01a0test-0000-0000-0000-000000000002"


def _inference(sid, prompt, cached, completion, reasoning=0, ts=None):
    return {
        "msg": "shell.turn.inference_done",
        "sid": sid,
        "ctx": {
            "prompt_tokens": prompt,
            "cached_prompt_tokens": cached,
            "completion_tokens": completion,
            "reasoning_tokens": reasoning,
        },
    } | ({"ts": ts} if ts else {})


def _write_log(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _make_session(
    root: Path,
    sid: str,
    ctx: int,
    model="grok-4.6",
    updated_at="2026-08-21T00:01:00Z",
):
    bucket = root / "%2Ftmp%2Fx"
    d = bucket / sid
    d.mkdir(parents=True)
    (d / "summary.json").write_text(json.dumps({
        "created_at": updated_at,
        "updated_at": updated_at,
        "generated_title": f"sess {sid[:8]}",
        "current_model_id": model,
        "info": {"cwd": "/tmp/x"},
    }), encoding="utf-8")
    (d / "signals.json").write_text(json.dumps({
        "contextTokensUsed": ctx,
        "toolsUsed": ["read_file"],
        "modelsUsed": [model],
    }), encoding="utf-8")
    return d


def test_parse_unified_log_aggregates_turns(tmp_path):
    log = tmp_path / "unified.jsonl"
    _write_log(log, [
        {"msg": "noise", "sid": SID},
        _inference(SID, 100, 20, 10, reasoning=7),
        _inference(SID, 250_000, 200_000, 50, reasoning=40),
        _inference("other", 10, 0, 1),
    ])
    by_sid = main._grok_usage_from_unified_log(log)
    row = by_sid[SID]
    assert row["input"] == 80 + 50_000
    assert row["cached"] == 20 + 200_000
    assert row["output"] == 10 + 50
    assert row["reasoning"] == 47
    assert row["turns"] == [(100, 20, 10, None), (250_000, 200_000, 50, None)]
    assert "other" in by_sid


def test_scan_uses_log_usage_not_context(tmp_path, monkeypatch):
    sessions = tmp_path / "sessions"
    log = tmp_path / "unified.jsonl"
    _make_session(sessions, SID, ctx=9_999)
    _write_log(log, [
        _inference(SID, 100, 20, 10),
        _inference(SID, 250_000, 200_000, 50),
    ])
    monkeypatch.setattr(main, "GROK_SESSIONS_DIR", sessions)
    monkeypatch.setattr(main, "GROK_UNIFIED_LOG", log)
    monkeypatch.setattr(main, "PROJECT_ALIASES_FILE", tmp_path / "aliases.json")

    out = {s["id"]: s for s in main._scan_grok_sessions()}
    tok = out[SID]["tokens"]
    assert tok["source"] == "usage"
    assert tok["input"] == 50_080
    assert tok["cached"] == 200_020
    assert tok["output"] == 60
    assert tok["total"] == 50_080 + 60 + 200_020
    expected = (
        calculate_xai_turn_cost("grok-4.6", 100, 10, 20)
        + calculate_xai_turn_cost("grok-4.6", 250_000, 50, 200_000)
    )
    assert tok["cost"] == pytest.approx(expected)
    # Must not keep using the window footprint as Input.
    assert tok["input"] != 9_999


def test_scan_falls_back_to_context_without_log(tmp_path, monkeypatch):
    sessions = tmp_path / "sessions"
    _make_session(sessions, SID_NO_LOG, ctx=1_500)
    monkeypatch.setattr(main, "GROK_SESSIONS_DIR", sessions)
    monkeypatch.setattr(main, "GROK_UNIFIED_LOG", tmp_path / "missing.jsonl")
    monkeypatch.setattr(main, "PROJECT_ALIASES_FILE", tmp_path / "aliases.json")

    out = {s["id"]: s for s in main._scan_grok_sessions()}
    tok = out[SID_NO_LOG]["tokens"]
    assert tok["source"] == "context"
    assert tok["input"] == 1_500
    assert tok["output"] == 0
    assert tok["cached"] == 0
    assert tok["cost"] == pytest.approx(calculate_cost("grok-4.6", 1_500, 0, 0))


def test_grok_4_6_list_rates():
    rates = PRICING["grok-4.6"]
    assert rates["in"] == 2.00
    assert rates["out"] == 6.00
    assert rates["cached_read"] == 0.50
    # Exact lookup — must not fall through to grok-4 ($3/$15).
    assert calculate_cost("grok-4.6", 1_000_000, 0, 0) == pytest.approx(2.00)
    assert calculate_cost("grok-4.6", 0, 1_000_000, 0) == pytest.approx(6.00)
    assert calculate_cost("grok-4.6", 0, 0, 1_000_000) == pytest.approx(0.50)


def test_grok_4_6_not_fuzzy_matched_to_grok_4():
    # A model we have no exact row for, whose name starts with grok-4.X, must
    # not inherit grok-4's $3/$15 just because "grok-4" is a substring.
    assert calculate_cost("grok-4.9-hypothetical", 1_000_000, 0, 0) != 3.00


def test_xai_turn_cost_short_vs_long():
    short = calculate_xai_turn_cost("grok-4.6", 100_000, 1_000, 10_000)
    # 90k uncached * $2 + 1k * $6 + 10k * $0.50 = 0.18 + 0.006 + 0.005 = 0.191
    assert short == pytest.approx(0.191)
    long = calculate_xai_turn_cost("grok-4.6", 200_000, 1_000, 10_000)
    # Same cached/output, more uncached, and 2x rates because prompt hit the cliff.
    base = calculate_cost("grok-4.6", 190_000, 1_000, 10_000)
    assert long == pytest.approx(base * 2)
    assert long > short * 2


def test_grok_build_and_code_fast_follow_xai_cutovers():
    """Retired aliases and generic Build sessions retain their actual rates."""
    # grok-code-fast-1 was retired at noon PT (19:00 UTC) on 2026-05-15 and
    # routed to Grok Build 0.1. https://docs.x.ai/developers/migration/may-15-retirement
    assert calculate_cost(
        "grok-code-fast-1", 1_000_000, 0, 0, at="2026-05-15T18:59:59Z"
    ) == pytest.approx(0.20)
    assert calculate_cost(
        "grok-code-fast-1", 1_000_000, 0, 0, at="2026-05-15T19:00:00Z"
    ) == pytest.approx(1.00)

    # Grok 4.6 became the Grok Build model on 2026-08-12. xAI announced only
    # the date, so pricing bands consistently start at midnight UTC.
    # https://x.ai/news/grok-4-6
    assert calculate_cost("grok-build", 1_000_000, 0, 0, at="2026-08-11T23:59:59Z") == pytest.approx(1.00)
    assert calculate_cost("grok-build", 1_000_000, 0, 0, at="2026-08-12T00:00:00Z") == pytest.approx(2.00)
    assert PRICING["grok-build"] == {"in": 2.00, "out": 6.00, "cached_read": 0.50}
    assert PRICING["grok-build-0.1"] == {"in": 1.00, "out": 2.00, "cached_read": 0.20}
    assert PRICING["grok-code-fast-1"] == {"in": 1.00, "out": 2.00, "cached_read": 0.20}
    # The migration notice names only grok-code-fast-1; don't silently reroute
    # the distinct grok-code-fast alias without a source proving that change.
    assert calculate_cost("grok-code-fast", 1_000_000, 0, 0, at="2026-08-30T00:00:00Z") == pytest.approx(0.20)


def test_scan_prices_each_generic_grok_build_turn_at_its_log_timestamp(tmp_path, monkeypatch):
    sessions = tmp_path / "sessions"
    log = tmp_path / "unified.jsonl"
    _make_session(
        sessions,
        SID,
        ctx=0,
        model="grok-build",
        updated_at="2026-08-12T00:01:00Z",
    )
    _write_log(log, [
        _inference(SID, 100_000, 10_000, 1_000, ts="2026-08-11T23:59:59Z"),
        _inference(SID, 100_000, 10_000, 1_000, ts="2026-08-12T00:00:00Z"),
    ])
    monkeypatch.setattr(main, "GROK_SESSIONS_DIR", sessions)
    monkeypatch.setattr(main, "GROK_UNIFIED_LOG", log)
    monkeypatch.setattr(main, "PROJECT_ALIASES_FILE", tmp_path / "aliases.json")

    sess = {s["id"]: s for s in main._scan_grok_sessions()}[SID]
    assert sess["tokens"]["cost"] == pytest.approx(
        calculate_xai_turn_cost("grok-build", 100_000, 1_000, 10_000, at="2026-08-11T23:59:59Z")
        + calculate_xai_turn_cost("grok-build", 100_000, 1_000, 10_000, at="2026-08-12T00:00:00Z")
    )


def test_model_resolved_before_pricing(tmp_path, monkeypatch):
    """No current_model_id + modelsUsed present must price as the used model.

    The model used to be reassigned from signals.modelsUsed *after* the token
    block, so the session displayed one model and was priced as grok-build.
    """
    sessions = tmp_path / "sessions"
    log = tmp_path / "unified.jsonl"
    d = _make_session(sessions, SID, ctx=9_999, model="grok-4.5")
    summary = json.loads((d / "summary.json").read_text(encoding="utf-8"))
    del summary["current_model_id"]
    (d / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    _write_log(log, [_inference(SID, 100, 20, 10)])
    monkeypatch.setattr(main, "GROK_SESSIONS_DIR", sessions)
    monkeypatch.setattr(main, "GROK_UNIFIED_LOG", log)
    monkeypatch.setattr(main, "PROJECT_ALIASES_FILE", tmp_path / "aliases.json")

    sess = {s["id"]: s for s in main._scan_grok_sessions()}[SID]
    assert sess["model"] == "grok-4.5"
    assert sess["tokens"]["cost"] == pytest.approx(
        calculate_xai_turn_cost("grok-4.5", 100, 10, 20)
    )
    # grok-build's rates would give a different figure; the two must not agree.
    assert sess["tokens"]["cost"] != pytest.approx(
        calculate_xai_turn_cost("grok-build", 100, 10, 20)
    )
