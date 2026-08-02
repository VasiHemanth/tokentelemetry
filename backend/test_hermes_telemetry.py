"""Tests for the Hermes telemetry rollup (GET /hermes/telemetry) and its index.

Covers the three things this feature can get quietly wrong:
  - ROTATION ORDER. agent.log.1 is OLDER than agent.log; a lexical sort reverses
    it and corrupts model_journey / the api_calls sequence.
  - CAPTURE vs ZERO. A session whose log lines rotated away has NO latency; the
    payload must say "not_captured", never 0.
  - OUTCOME SEMANTICS. An end_reason we don't recognise must land in "unknown"
    with its raw string preserved, never be folded into "completed".

Run: pytest backend/test_hermes_telemetry.py
"""
import asyncio
import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import hermes_telemetry as ht  # noqa: E402
import main  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

_SCHEMA = (
    "CREATE TABLE sessions (id TEXT, source TEXT, model TEXT, "
    "parent_session_id TEXT, started_at INT, ended_at INT, "
    "input_tokens INT, output_tokens INT, cache_read_tokens INT, "
    "cache_write_tokens INT, reasoning_tokens INT, "
    "estimated_cost_usd REAL, actual_cost_usd REAL, title TEXT, "
    "billing_provider TEXT, billing_base_url TEXT, "
    "cost_status TEXT, cost_source TEXT, end_reason TEXT)"
)

# Real Hermes session-id shape — the agent.log regexes require it.
SID_SPAN = "20260101_000000_aaaa1111"   # calls in agent.log.1 AND agent.log
SID_ROTATED = "20260102_000000_bbbb2222"  # calls ONLY in the rotated file
SID_DARK = "20260103_000000_cccc3333"   # no log lines anywhere


def _make_db(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute(_SCHEMA)
    con.execute("CREATE TABLE messages (session_id TEXT, role TEXT, content TEXT, "
                "timestamp INT, tool_name TEXT)")
    con.executemany(
        "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()


def _row(sid, *, model="claude-sonnet-4-6", source="cli", est=None, actual=None,
         cost_status=None, cost_source=None, end_reason=None, tokens=(1000, 500),
         provider="anthropic", base_url=None):
    return (sid, source, model, None, 1750000000, 1750000100,
            tokens[0], tokens[1], 0, 0, 0, est, actual, "t",
            provider, base_url, cost_status, cost_source, end_reason)


def _isolate_other_agents(tmp_path, monkeypatch):
    """Point every non-Hermes source at empty paths so a scan sees Hermes only."""
    missing = tmp_path / "missing"
    for attr in ("CODEX_DIR", "GEMINI_DIR", "QWEN_DIR", "VIBE_DIR", "OLLAMA_DIR",
                 "GROK_SESSIONS_DIR", "VSCODE_STORAGE", "CURSOR_STORAGE",
                 "COPILOT_CLI_DIR", "ANTIGRAVITY_BRAIN_DIR", "ANTIGRAVITY_CLI_DIR",
                 "PI_SESSIONS_DIR"):
        monkeypatch.setattr(main, attr, missing / attr.lower())
    monkeypatch.setattr(main, "ANTIGRAVITY_BRAIN_SOURCES", [])
    monkeypatch.setattr(main, "ANTIGRAVITY_BRAIN_DIRS", [])
    monkeypatch.setattr(main, "_antigravity_cli_meta", lambda *a, **k: {})
    monkeypatch.setattr(main, "CLAUDE_DIR", missing / "claude")
    monkeypatch.setattr(main, "CURSOR_DIR", missing / "cursor")
    monkeypatch.setattr(main, "OPENCODE_DB", missing / "opencode.db")
    monkeypatch.setattr(main, "CLINE_DIR", missing / "cline")
    monkeypatch.setattr(main, "CLINE_VSCODE_DIR", missing / "cline-vscode")
    # SmallCode traces are project-local and its roots are derived from the
    # projects other agents reported, so killing Cline also empties this —
    # but only if no extra roots are configured.
    monkeypatch.setattr(main, "SMALLCODE_EXTRA_ROOTS", [])
    monkeypatch.setattr(main, "PROJECT_ALIASES_FILE", tmp_path / "aliases.json")
    monkeypatch.setenv("TOKENTELEMETRY_DATA_DIR", str(tmp_path / "tt_data"))


def _api_line(ts, sid, n, model, latency, provider="anthropic"):
    return (f"{ts},123 INFO [{sid}] API call #{n}: model={model} "
            f"provider={provider} in=50 out=20 total=70 latency={latency}s\n")


def _tool_ok(ts, sid, tool, dur):
    return f"{ts},000 INFO [{sid}] tool {tool} completed ({dur}s, 42 chars)\n"


def _tool_fail(ts, sid, tool, dur):
    return f"{ts},000 INFO [{sid}] tool {tool} failed ({dur}s): boom\n"


@pytest.fixture
def hermes_home(tmp_path, monkeypatch):
    """A Hermes home with a rotated + current agent.log and a 3-session DB.

    The rotated file (agent.log.1) is OLDER and carries model "alpha-1"; the
    current file carries "omega-9". A reversed read order therefore produces
    model_journey ["omega-9", "alpha-1"] and fails loudly.
    """
    ht.clear_cache()
    _isolate_other_agents(tmp_path, monkeypatch)
    home = tmp_path / ".hermes"
    (home / "logs").mkdir(parents=True)
    monkeypatch.setattr(main, "HERMES_DIR", home)
    monkeypatch.setattr(main, "HERMES_DB", home / "state.db")
    monkeypatch.setattr(main, "HERMES_PROFILES_DIR", home / "profiles")

    _make_db(home / "state.db", [
        # provider-reported (actual cost present)
        _row(SID_SPAN, actual=0.25, est=0.30, end_reason="cli_close"),
        # provider-estimated (estimate present, cost_source trustworthy)
        _row(SID_ROTATED, est=0.42, cost_source="api", end_reason="compression"),
        # tt-computed (no cost at all -> priced from tokens)
        _row(SID_DARK, end_reason="quantum_collapse"),
    ])

    # OLDER rotation: alpha-1 calls, earlier wall-clock.
    (home / "logs" / "agent.log.1").write_text(
        _api_line("2026-01-01 00:00:01", SID_SPAN, 1, "alpha-1", 1.0)
        + _api_line("2026-01-01 00:00:02", SID_SPAN, 2, "alpha-1", 3.0)
        + _api_line("2026-01-02 00:00:01", SID_ROTATED, 1, "alpha-1", 5.0)
        + _tool_ok("2026-01-01 00:00:03", SID_SPAN, "bash", 1.0)
        + _tool_fail("2026-01-01 00:00:04", SID_SPAN, "web", 2.0),
        encoding="utf-8")
    # CURRENT log: omega-9 calls, later wall-clock.
    (home / "logs" / "agent.log").write_text(
        _api_line("2026-01-05 00:00:01", SID_SPAN, 3, "omega-9", 9.0)
        + _tool_ok("2026-01-05 00:00:02", SID_SPAN, "bash", 3.0)
        + _tool_ok("2026-01-05 00:00:03", SID_SPAN, "bash", 2.0)
        + _tool_fail("2026-01-05 00:00:04", SID_SPAN, "web", 4.0)
        + _tool_fail("2026-01-05 00:00:05", SID_SPAN, "web", 6.0),
        encoding="utf-8")
    # A compressed rotation must be ignored, not decompressed.
    (home / "logs" / "agent.log.2.gz").write_bytes(b"\x1f\x8b\x08 not real gzip")
    yield home
    ht.clear_cache()


# --------------------------------------------------------------------------- #
# Rotation order
# --------------------------------------------------------------------------- #

def test_log_files_in_chronological_order(hermes_home):
    names = [p.name for p in ht.log_files_in_order(hermes_home)]
    # Oldest rotation first, current log last; .gz never read.
    assert names == ["agent.log.1", "agent.log"]


def test_rotation_order_is_generic(tmp_path):
    ht.clear_cache()
    logs = tmp_path / "logs"
    logs.mkdir()
    for n in ("agent.log", "agent.log.1", "agent.log.2", "agent.log.10",
              "agent.log.3.gz", "other.log"):
        (logs / n).write_text("", encoding="utf-8")
    assert [p.name for p in ht.log_files_in_order(tmp_path)] == [
        "agent.log.10", "agent.log.2", "agent.log.1", "agent.log"]


def test_spanning_session_merges_in_true_chronological_order(hermes_home):
    log = main._hermes_log_summary(SID_SPAN)
    assert [c["model"] for c in log["api_calls"]] == ["alpha-1", "alpha-1", "omega-9"]
    assert [c["n"] for c in log["api_calls"]] == [1, 2, 3]
    # A reversed read order would give ["omega-9", "alpha-1"].
    assert log["model_journey"] == ["alpha-1", "omega-9"]
    assert log["summary"]["api_call_count"] == 3
    assert log["summary"]["total_latency_s"] == 13.0
    assert log["log_coverage"] == "captured"


def test_session_only_in_rotated_file_is_captured(hermes_home):
    log = main._hermes_log_summary(SID_ROTATED)
    assert log["summary"] is not None
    assert log["summary"]["api_call_count"] == 1
    assert log["summary"]["total_latency_s"] == 5.0
    assert log["log_coverage"] == "captured"


def test_session_with_no_log_lines_is_not_captured(hermes_home):
    log = main._hermes_log_summary(SID_DARK)
    # "not captured" is NOT zero — summary must be absent, not a zeroed dict.
    assert log["summary"] is None
    assert log["log_coverage"] == "not_captured"
    assert log["api_calls"] == []

    overlay = _run(main.hermes_session_overlay(SID_DARK))
    assert overlay["performance"] is None
    assert overlay["log_coverage"] == "not_captured"
    assert overlay["performance"] != 0

    captured = _run(main.hermes_session_overlay(SID_SPAN))
    assert captured["log_coverage"] == "captured"
    assert captured["performance"]["log_coverage"] == "captured"


# --------------------------------------------------------------------------- #
# Cache invalidation
# --------------------------------------------------------------------------- #

def test_index_cache_hits_then_refreshes_on_change(hermes_home):
    idx1, files1 = ht.get_log_index(hermes_home)
    idx2, _ = ht.get_log_index(hermes_home)
    assert idx1 is idx2                      # cached: same object, no re-parse
    assert files1 == ["agent.log.1", "agent.log"]

    log = hermes_home / "logs" / "agent.log"
    with open(log, "a", encoding="utf-8") as f:
        f.write(_api_line("2026-01-06 00:00:01", SID_DARK, 1, "omega-9", 2.0))
    # Some filesystems have coarse mtime; nudge it so the test can't false-pass
    # on size alone being the only signal.
    st = log.stat()
    os.utime(log, (st.st_atime + 5, st.st_mtime + 5))

    idx3, _ = ht.get_log_index(hermes_home)
    assert idx3 is not idx1
    assert len(idx3[SID_DARK]["api_calls"]) == 1

    # A brand-new rotation also invalidates.
    (hermes_home / "logs" / "agent.log.2").write_text(
        _api_line("2025-12-01 00:00:01", SID_DARK, 1, "ancient-0", 1.0), encoding="utf-8")
    idx4, files4 = ht.get_log_index(hermes_home)
    assert idx4 is not idx3
    assert files4 == ["agent.log.2", "agent.log.1", "agent.log"]
    assert [c["model"] for c in idx4[SID_DARK]["api_calls"]] == ["ancient-0", "omega-9"]


def test_missing_logs_dir_is_silent(tmp_path):
    ht.clear_cache()
    index, files = ht.get_log_index(tmp_path / "nope")
    assert index == {} and files == []


# --------------------------------------------------------------------------- #
# Outcome taxonomy
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("raw,bucket", [
    ("cli_close", "completed"),
    ("compression", "continued"),
    ("resumed_other", "continued"),
    ("idle_timeout", "timed_out"),
    ("ws_disconnect", "interrupted"),
    ("session_reset", "reset"),
    (None, "unknown"),
    ("", "unknown"),
    ("   ", "unknown"),
    # Upstream itself treats these as carrying no outcome — they must not be
    # forced into a bucket.
    ("agent_close", "unknown"),
    ("ws_orphan_reap", "unknown"),
    ("orphaned_compression", "unknown"),
])
def test_classify_end_reason(raw, bucket):
    assert ht.classify_end_reason(raw) == bucket


def test_unmapped_end_reason_is_unknown_never_completed():
    assert ht.classify_end_reason("quantum_collapse") == "unknown"
    assert ht.classify_end_reason("quantum_collapse") != "completed"
    assert ht.normalize_end_reason_raw("quantum_collapse") == "quantum_collapse"
    assert ht.normalize_end_reason_raw(None) is None
    assert ht.normalize_end_reason_raw("") is None


def test_scan_sets_outcome_and_raw(hermes_home):
    by_id = {s["id"]: s for s in main._scan_sessions_sync() if s["agent"] == "hermes"}
    assert by_id[SID_SPAN]["outcome"] == "completed"
    assert by_id[SID_SPAN]["outcome_raw"] == "cli_close"
    assert by_id[SID_ROTATED]["outcome"] == "continued"
    assert by_id[SID_DARK]["outcome"] == "unknown"
    assert by_id[SID_DARK]["outcome_raw"] == "quantum_collapse"


# --------------------------------------------------------------------------- #
# Percentiles
# --------------------------------------------------------------------------- #

def test_unknown_bucket_can_exceed_unknown_raw(tmp_path, monkeypatch):
    """Two ways to be "unknown": a NULL end_reason (no raw to show) and an
    unmapped string (raw preserved). They share the bucket, so
    sum(unknown_raw counts) <= buckets["unknown"].count BY DESIGN."""
    ht.clear_cache()
    _isolate_other_agents(tmp_path, monkeypatch)
    home = tmp_path / ".hermes"
    monkeypatch.setattr(main, "HERMES_DIR", home)
    monkeypatch.setattr(main, "HERMES_DB", home / "state.db")
    monkeypatch.setattr(main, "HERMES_PROFILES_DIR", home / "profiles")
    _make_db(home / "state.db", [
        _row("20260401_000000_1111aaaa", end_reason=None),
        _row("20260401_000000_2222bbbb", end_reason="quantum_collapse"),
        _row("20260401_000000_3333cccc", end_reason="quantum_collapse"),
        _row("20260401_000000_4444dddd", end_reason="cli_close"),
    ])
    t = _telemetry(monkeypatch)
    buckets = {b["outcome"]: b for b in t["outcomes"]["buckets"]}
    assert buckets["unknown"]["count"] == 3
    assert t["outcomes"]["unknown_raw"] == [{"raw": "quantum_collapse", "count": 2}]
    assert sum(r["count"] for r in t["outcomes"]["unknown_raw"]) <= buckets["unknown"]["count"]
    # The whole point: an unrecognised string is never a completion.
    assert buckets["completed"]["count"] == 1
    assert t["outcomes"]["completion_rate"] == 0.25


def test_percentile_edge_cases():
    assert ht.percentile([], 0.5) is None
    assert ht.percentile([], 0.95) is None
    assert ht.percentile([7.5], 0.5) == 7.5
    assert ht.percentile([7.5], 0.95) == 7.5
    # Nearest-rank: p50 of 1..4 is the 2nd value; p95 of 1..100 is the 95th.
    assert ht.percentile([1, 2, 3, 4], 0.5) == 2.0
    assert ht.percentile(list(range(1, 101)), 0.95) == 95.0
    assert ht.percentile(list(range(1, 101)), 0.5) == 50.0
    assert ht.percentile([4, 1, 3, 2], 0.95) == 4.0   # unsorted input
    assert ht.percentile([None, 2.0, None], 0.5) == 2.0


# --------------------------------------------------------------------------- #
# Cost status
# --------------------------------------------------------------------------- #

def test_cost_statuses(tmp_path, monkeypatch):
    """provider-reported / provider-estimated / tt-computed / unpriced.

    (`zero-marginal` has its own tests below.)
    """
    ht.clear_cache()
    _isolate_other_agents(tmp_path, monkeypatch)
    # Decouple from the developer's real ~/.tokentelemetry/power.json: adding a
    # subscription model there must not flip 3333cccc from tt-computed.
    import power_config
    monkeypatch.setattr(power_config, "is_subscription_model", lambda m: False)
    monkeypatch.setattr(power_config, "is_local_session", lambda *a, **k: False)
    home = tmp_path / ".hermes"
    monkeypatch.setattr(main, "HERMES_DIR", home)
    monkeypatch.setattr(main, "HERMES_DB", home / "state.db")
    monkeypatch.setattr(main, "HERMES_PROFILES_DIR", home / "profiles")
    _make_db(home / "state.db", [
        _row("20260201_000000_1111aaaa", actual=0.25, est=0.30),
        _row("20260201_000000_2222bbbb", est=0.42, cost_source="api"),
        # Hermes's untrustworthy 0.0 (issue #176) -> re-priced by TT.
        _row("20260201_000000_3333cccc", est=0.0, cost_status="unknown",
             cost_source="none", tokens=(115184, 21102)),
        # Nothing to price: no cost, no tokens -> must stay None, never 0.0.
        _row("20260201_000000_4444dddd", tokens=(0, 0)),
    ])
    by_id = {s["id"]: s for s in main._scan_sessions_sync() if s["agent"] == "hermes"}

    assert by_id["20260201_000000_1111aaaa"]["cost_status"] == "provider-reported"
    assert by_id["20260201_000000_1111aaaa"]["cost"] == 0.25
    assert by_id["20260201_000000_2222bbbb"]["cost_status"] == "provider-estimated"
    assert by_id["20260201_000000_2222bbbb"]["cost"] == 0.42
    assert by_id["20260201_000000_3333cccc"]["cost_status"] == "tt-computed"
    assert by_id["20260201_000000_3333cccc"]["cost"] > 0
    unpriced = by_id["20260201_000000_4444dddd"]
    assert unpriced["cost_status"] == "unpriced"
    assert unpriced["cost"] is None          # NOT 0.0
    assert unpriced["tokens"]["cost"] is None


def test_subscription_zero_is_zero_marginal_not_tt_computed(tmp_path, monkeypatch):
    """A flat-subscription session legitimately costs $0 — priced, not unpriced.

    It must NOT read as `tt-computed`: that status means "TT priced these tokens
    and the answer is this dollar figure", so a tt-computed 0.0 renders as
    "API equiv. $0.00 · priced by TokenTelemetry" — a claim that the API
    equivalent of the tokens is zero. It isn't; the marginal cost is.
    """
    ht.clear_cache()
    _isolate_other_agents(tmp_path, monkeypatch)
    home = tmp_path / ".hermes"
    monkeypatch.setattr(main, "HERMES_DIR", home)
    monkeypatch.setattr(main, "HERMES_DB", home / "state.db")
    monkeypatch.setattr(main, "HERMES_PROFILES_DIR", home / "profiles")
    _make_db(home / "state.db", [
        _row("20260301_000000_5555eeee", model="sub-model", tokens=(1000, 500)),
    ])
    import power_config
    monkeypatch.setattr(power_config, "is_subscription_model", lambda m: m == "sub-model")
    by_id = {s["id"]: s for s in main._scan_sessions_sync() if s["agent"] == "hermes"}
    row = by_id["20260301_000000_5555eeee"]
    assert row["cost"] == 0.0                 # deliberate zero, preserved
    assert row["tokens"]["cost"] == 0.0
    assert row["cost_status"] == "zero-marginal"


# --------------------------------------------------------------------------- #
# Endpoint payload
# --------------------------------------------------------------------------- #

def _telemetry(monkeypatch):
    sessions = main._scan_sessions_sync()

    async def _fake(fresh: bool = False):
        return sessions
    monkeypatch.setattr(main, "get_sessions_cached", _fake)
    return _run(main.hermes_telemetry())


def test_telemetry_unavailable_without_a_db(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "HERMES_DIR", tmp_path / "nope")
    monkeypatch.setattr(main, "HERMES_DB", tmp_path / "nope" / "state.db")
    monkeypatch.setattr(main, "HERMES_PROFILES_DIR", tmp_path / "nope" / "profiles")
    assert _run(main.hermes_telemetry()) == {"available": False}


def test_telemetry_payload(hermes_home, monkeypatch):
    t = _telemetry(monkeypatch)
    assert t["available"] is True
    assert t["session_count"] == 3

    # --- outcomes
    o = t["outcomes"]
    buckets = {b["outcome"]: b for b in o["buckets"]}
    assert buckets["completed"]["count"] == 1
    assert buckets["completed"]["pct"] == 33.3
    assert buckets["continued"]["count"] == 1
    assert buckets["unknown"]["count"] == 1
    assert "quantum_collapse" not in [b["outcome"] for b in o["buckets"]]
    assert o["unknown_raw"] == [{"raw": "quantum_collapse", "count": 1}]
    assert o["completion_rate"] == round(1 / 3, 3)
    assert sum(b["count"] for b in o["buckets"]) == t["session_count"]
    src = {r["source"]: r for r in o["by_source"]}
    assert src["cli"]["total"] == 3
    assert src["cli"]["buckets"] == {"completed": 1, "continued": 1, "unknown": 1}
    assert sum(r["total"] for r in o["by_model"]) == t["session_count"]

    # --- cost
    c = t["cost"]
    assert set(c["confidence"]) == {"provider-reported", "provider-estimated",
                                    "tt-computed", "zero-marginal", "unpriced"}
    assert c["confidence"]["provider-reported"] == 1
    assert c["confidence"]["provider-estimated"] == 1
    assert c["confidence"]["tt-computed"] == 1
    assert sum(c["confidence"].values()) == t["session_count"]
    assert c["usd_by_confidence"]["provider-reported"] == 0.25
    assert c["usd_by_confidence"]["provider-estimated"] == 0.42
    assert abs(c["total_usd"] - sum(c["usd_by_confidence"].values())) < 0.002

    # --- latency: 4 calls over 2 sessions (1.0, 3.0, 9.0 and 5.0)
    lat = t["latency"]
    assert lat["captured_sessions"] == 2
    assert lat["uncaptured_sessions"] == 1
    assert lat["captured_sessions"] + lat["uncaptured_sessions"] == t["session_count"]
    assert lat["api_calls"] == 4
    assert lat["avg_s"] == 4.5
    assert lat["p50_s"] == 3.0      # nearest-rank of [1,3,5,9]
    assert lat["p95_s"] == 9.0
    by_model = {r["model"]: r for r in lat["by_model"]}
    assert by_model["alpha-1"]["calls"] == 3
    assert by_model["alpha-1"]["avg_s"] == 3.0
    assert by_model["omega-9"]["calls"] == 1
    assert by_model["omega-9"]["p95_s"] == 9.0
    assert [r["calls"] for r in lat["by_model"]] == sorted(
        [r["calls"] for r in lat["by_model"]], reverse=True)

    # --- tools: bash 3 calls 0 fails, web 3 calls 3 fails
    tl = t["tools"]
    assert tl["captured"] is True
    top = {r["tool"]: r for r in tl["top_by_calls"]}
    assert top["bash"]["calls"] == 3 and top["bash"]["failures"] == 0
    assert top["bash"]["failure_rate"] == 0.0
    assert top["bash"]["avg_duration_s"] == 2.0
    assert top["web"]["calls"] == 3 and top["web"]["failures"] == 3
    assert tl["top_by_failure_rate"][0]["tool"] == "web"
    assert tl["top_by_failure_rate"][0]["failure_rate"] == 1.0

    # --- log coverage
    lc = t["log_coverage"]
    assert lc["files_read"] == ["agent.log.1", "agent.log"]
    assert lc["sessions_with_log"] == lat["captured_sessions"]
    assert lc["sessions_total"] == t["session_count"]


def test_low_volume_tools_excluded_from_failure_rate(hermes_home, monkeypatch):
    """A 1-call 100%-failure tool is noise: counted, but never a 'top failure'."""
    with open(hermes_home / "logs" / "agent.log", "a", encoding="utf-8") as f:
        f.write(_tool_fail("2026-01-05 00:00:09", SID_SPAN, "flaky_once", 1.0))
    ht.clear_cache()
    t = _telemetry(monkeypatch)
    assert "flaky_once" in {r["tool"] for r in t["tools"]["top_by_calls"]}
    assert "flaky_once" not in {r["tool"] for r in t["tools"]["top_by_failure_rate"]}


def test_empty_db_reports_available_with_null_latency(tmp_path, monkeypatch):
    """An empty profile DB (the user really has one) must not divide by zero."""
    ht.clear_cache()
    _isolate_other_agents(tmp_path, monkeypatch)
    home = tmp_path / ".hermes"
    monkeypatch.setattr(main, "HERMES_DIR", home)
    monkeypatch.setattr(main, "HERMES_DB", home / "state.db")
    monkeypatch.setattr(main, "HERMES_PROFILES_DIR", home / "profiles")
    _make_db(home / "state.db", [])
    # A profile home with a DB but no logs/ dir at all.
    _make_db(home / "profiles" / "founder" / "state.db", [])

    t = _telemetry(monkeypatch)
    assert t["available"] is True
    assert t["session_count"] == 0
    assert t["outcomes"]["buckets"] == []
    assert t["outcomes"]["unknown_raw"] == []
    assert t["outcomes"]["completion_rate"] == 0.0
    assert t["latency"]["avg_s"] is None
    assert t["latency"]["p50_s"] is None
    assert t["latency"]["p95_s"] is None
    assert t["latency"]["api_calls"] == 0
    assert t["tools"] == {"captured": False, "top_by_calls": [], "top_by_failure_rate": []}
    assert t["log_coverage"]["files_read"] == []
    assert t["cost"]["total_usd"] == 0.0


def test_profile_logs_are_labelled_and_scoped(tmp_path, monkeypatch):
    """A profile's sessions live in its own log; merged files_read stays unambiguous."""
    ht.clear_cache()
    _isolate_other_agents(tmp_path, monkeypatch)
    home = tmp_path / ".hermes"
    (home / "logs").mkdir(parents=True)
    monkeypatch.setattr(main, "HERMES_DIR", home)
    monkeypatch.setattr(main, "HERMES_DB", home / "state.db")
    monkeypatch.setattr(main, "HERMES_PROFILES_DIR", home / "profiles")
    _make_db(home / "state.db", [_row(SID_SPAN, end_reason="cli_close")])
    _make_db(home / "profiles" / "coder" / "state.db",
             [_row(SID_ROTATED, end_reason="cli_close")])
    (home / "logs" / "agent.log").write_text(
        _api_line("2026-01-01 00:00:01", SID_SPAN, 1, "alpha-1", 1.0), encoding="utf-8")
    plogs = home / "profiles" / "coder" / "logs"
    plogs.mkdir(parents=True)
    (plogs / "agent.log").write_text(
        _api_line("2026-01-02 00:00:01", SID_ROTATED, 1, "beta-2", 2.0), encoding="utf-8")

    # Per-session lookup stays home-scoped: the root log knows nothing of the
    # profile's session.
    assert main._hermes_log_summary(SID_ROTATED)["summary"] is None
    assert main._hermes_log_summary(SID_ROTATED, "coder")["summary"]["api_call_count"] == 1

    t = _telemetry(monkeypatch)
    assert t["log_coverage"]["files_read"] == ["agent.log", "coder/agent.log"]
    assert t["latency"]["captured_sessions"] == 2
    assert t["latency"]["api_calls"] == 2


def test_stale_log_sessions_are_not_counted(hermes_home, monkeypatch):
    """Log lines for a session that no longer exists in any DB are ignored."""
    with open(hermes_home / "logs" / "agent.log", "a", encoding="utf-8") as f:
        f.write(_api_line("2026-01-09 00:00:01", "20261231_000000_deadbeef", 1,
                          "ghost-0", 99.0))
    ht.clear_cache()
    t = _telemetry(monkeypatch)
    assert t["session_count"] == 3
    assert t["latency"]["api_calls"] == 4          # not 5
    assert "ghost-0" not in {r["model"] for r in t["latency"]["by_model"]}


def test_payload_is_json_serializable(hermes_home, monkeypatch):
    import json
    t = _telemetry(monkeypatch)
    json.dumps(t)   # no datetimes / Paths / sets leak into the response
    for key in ("available", "session_count", "outcomes", "cost", "latency",
                "tools", "log_coverage"):
        assert key in t
    assert set(t) == {"available", "session_count", "outcomes", "cost", "latency",
                      "tools", "log_coverage"}


# --------------------------------------------------------------------------- #
# Unpriced cost (None) must not break the aggregates that CONSUME it
#
# `cost` is None — not 0.0 — for a session TT cannot price, and the key EXISTS
# on the dict, so `s.get("cost", 0.0)` returns None and every `+=` downstream
# raises TypeError. The whole /projects and /analytics pages 500'd on a single
# tokenless Hermes row. These tests pin the two aggregation paths.
# --------------------------------------------------------------------------- #

def _mixed_priced_home(tmp_path, monkeypatch):
    """A Hermes DB with one priceable session and one that must stay None."""
    ht.clear_cache()
    _isolate_other_agents(tmp_path, monkeypatch)
    home = tmp_path / ".hermes"
    monkeypatch.setattr(main, "HERMES_DIR", home)
    monkeypatch.setattr(main, "HERMES_DB", home / "state.db")
    monkeypatch.setattr(main, "HERMES_PROFILES_DIR", home / "profiles")
    _make_db(home / "state.db", [
        # Priced by TT from tokens.
        _row("20260401_000000_1111aaaa", tokens=(115184, 21102),
             end_reason="cli_close"),
        # No tokens, no cost anywhere -> cost is None.
        _row("20260401_000000_2222bbbb", tokens=(0, 0), end_reason="cli_close"),
    ])
    sessions = main._scan_sessions_sync()
    by_id = {s["id"]: s for s in sessions}
    assert by_id["20260401_000000_2222bbbb"]["cost"] is None   # the trigger
    priced = by_id["20260401_000000_1111aaaa"]["cost"]
    assert isinstance(priced, float) and priced > 0

    async def _fake(fresh: bool = False):
        return sessions
    monkeypatch.setattr(main, "get_sessions_cached", _fake)
    return sessions, priced


def test_projects_aggregation_survives_an_unpriced_session(tmp_path, monkeypatch):
    sessions, priced = _mixed_priced_home(tmp_path, monkeypatch)
    projects = _run(main.get_projects())
    # Both sessions have no cwd -> one "unknown" project card holding both.
    card = next(p for p in projects if p["path"] == "unknown")
    assert card["session_count"] == 2
    assert card["tokens"]["cost"] == pytest.approx(priced)   # priced only
    assert card["tokens"]["input"] == 115184


def test_analytics_by_agent_survives_an_unpriced_session(tmp_path, monkeypatch):
    sessions, priced = _mixed_priced_home(tmp_path, monkeypatch)
    a = _run(main.get_analytics(from_=None, to=None, granularity="day",
                                agents=[], models=[], projects=[]))
    row = a["by_agent"]["hermes"]
    assert row["session_count"] == 2
    assert row["cost"] == pytest.approx(priced)              # priced only
    # by_model / by_day walk the same variable and must be intact too.
    assert sum(m["cost"] for m in a["by_model"].values()) == pytest.approx(priced)
    assert sum(d["cost"] for d in a["by_day"]) == pytest.approx(priced)


# --------------------------------------------------------------------------- #
# Zero failures is not a failure ranking
# --------------------------------------------------------------------------- #

def test_no_failures_means_an_empty_failure_rate_list(hermes_home, monkeypatch):
    """Plenty of calls, zero errors -> [], never N rows reading "0.0%"."""
    (hermes_home / "logs" / "agent.log.1").write_text(
        _api_line("2026-01-01 00:00:01", SID_SPAN, 1, "alpha-1", 1.0), encoding="utf-8")
    (hermes_home / "logs" / "agent.log").write_text(
        "".join(_tool_ok("2026-01-05 00:00:0%d" % (i % 10), SID_SPAN, "terminal", 1.0)
                for i in range(55))
        + "".join(_tool_ok("2026-01-05 00:00:0%d" % (i % 10), SID_SPAN, "read_file", 1.0)
                  for i in range(12)),
        encoding="utf-8")
    ht.clear_cache()
    t = _telemetry(monkeypatch)
    tl = t["tools"]
    assert tl["captured"] is True
    top = {r["tool"]: r for r in tl["top_by_calls"]}
    assert top["terminal"]["calls"] == 55 and top["terminal"]["failures"] == 0
    assert tl["top_by_failure_rate"] == []


def test_failure_rate_list_still_ranks_real_failures(hermes_home, monkeypatch):
    """The `failures > 0` filter must not evict a tool that actually failed."""
    t = _telemetry(monkeypatch)
    fails = {r["tool"]: r for r in t["tools"]["top_by_failure_rate"]}
    assert set(fails) == {"web"}          # bash has 3 calls but 0 failures
    assert fails["web"]["failures"] == 3


# --------------------------------------------------------------------------- #
# Subscription-included qualifier on the aggregate cost
# --------------------------------------------------------------------------- #

def test_subscription_included_usd_sums_only_included_sessions(tmp_path, monkeypatch):
    """Hermes cost_status='included' == flat-plan; $0 marginal to the user.

    TT still prices those sessions (that's the API-equivalent figure), so
    `total_usd` alone is not honest about what was actually spent. The included
    subtotal lets the UI qualify it.
    """
    ht.clear_cache()
    _isolate_other_agents(tmp_path, monkeypatch)
    home = tmp_path / ".hermes"
    monkeypatch.setattr(main, "HERMES_DIR", home)
    monkeypatch.setattr(main, "HERMES_DB", home / "state.db")
    monkeypatch.setattr(main, "HERMES_PROFILES_DIR", home / "profiles")
    _make_db(home / "state.db", [
        # Flat-plan sessions (Hermes's own status), re-priced by TT per #176.
        _row("20260501_000000_1111aaaa", est=0.0, cost_status="included",
             cost_source="none", tokens=(116295, 8982)),
        _row("20260501_000000_2222bbbb", est=0.0, cost_status="included",
             cost_source="none", tokens=(278448, 20893)),
        # Not included: pay-as-you-go, same re-pricing path.
        _row("20260501_000000_3333cccc", est=0.0, cost_status="unknown",
             cost_source="none", tokens=(115184, 21102)),
        # Not included and unpriceable -> contributes nothing to either figure.
        _row("20260501_000000_4444dddd", tokens=(0, 0)),
    ])
    sessions = main._scan_sessions_sync()
    by_id = {s["id"]: s for s in sessions}
    assert by_id["20260501_000000_1111aaaa"]["_hermes_cost_status"] == "included"
    assert by_id["20260501_000000_3333cccc"]["_hermes_cost_status"] == "unknown"

    t = _telemetry(monkeypatch)
    c = t["cost"]
    expected_included = round(by_id["20260501_000000_1111aaaa"]["cost"]
                              + by_id["20260501_000000_2222bbbb"]["cost"], 3)
    assert expected_included > 0
    assert c["subscription_included_usd"] == expected_included
    assert c["total_usd"] == round(expected_included
                                   + by_id["20260501_000000_3333cccc"]["cost"], 3)
    assert c["subscription_included_usd"] < c["total_usd"]


def test_subscription_included_usd_is_zero_without_included_sessions(hermes_home,
                                                                     monkeypatch):
    t = _telemetry(monkeypatch)
    assert t["cost"]["subscription_included_usd"] == 0.0
    assert t["cost"]["total_usd"] > 0


# --------------------------------------------------------------------------- #
# zero-marginal: a priced, genuinely-free session is not a priced-at-zero one
# --------------------------------------------------------------------------- #

def _zero_marginal_home(tmp_path, monkeypatch, rows, *, local=False, sub_models=()):
    """Hermes home whose sessions all price to a deliberate $0."""
    ht.clear_cache()
    _isolate_other_agents(tmp_path, monkeypatch)
    home = tmp_path / ".hermes"
    monkeypatch.setattr(main, "HERMES_DIR", home)
    monkeypatch.setattr(main, "HERMES_DB", home / "state.db")
    monkeypatch.setattr(main, "HERMES_PROFILES_DIR", home / "profiles")
    import power_config
    monkeypatch.setattr(power_config, "is_subscription_model",
                        lambda m: m in sub_models)
    monkeypatch.setattr(power_config, "is_local_session", lambda *a, **k: local)
    # Deterministic power config: the developer's real ~/.tokentelemetry/power.json
    # must not decide whether a local session prices to zero.
    monkeypatch.setattr(power_config, "load_power_config",
                        lambda: {"loadWatts": 22, "costPerKwh": 0.0})
    _make_db(home / "state.db", rows)
    return home


def test_local_model_session_is_zero_marginal(tmp_path, monkeypatch):
    """A local model costs electricity, not API dollars — and with no electricity
    rate configured that is a genuine $0, which is a FINDING, not a price."""
    _zero_marginal_home(tmp_path, monkeypatch,
                        [_row("20260601_000000_1111aaaa", model="qwen3-coder:30b",
                              provider="ollama",
                              base_url="http://localhost:11434")],
                        local=True)
    row = [s for s in main._scan_sessions_sync() if s["agent"] == "hermes"][0]
    assert row["cost"] == 0.0                  # true marginal cost, kept
    assert row["cost"] is not None             # NOT nulled into "unpriced"
    assert row["cost_status"] == "zero-marginal"


def test_local_model_with_a_real_electricity_rate_is_still_tt_computed(tmp_path,
                                                                      monkeypatch):
    """Guard the other side: a nonzero electricity figure IS a computed price."""
    _zero_marginal_home(tmp_path, monkeypatch,
                        [_row("20260601_000000_4444eeee", model="qwen3-coder:30b",
                              provider="ollama",
                              base_url="http://localhost:11434")],
                        local=True)
    import power_config
    monkeypatch.setattr(power_config, "load_power_config",
                        lambda: {"loadWatts": 22, "costPerKwh": 0.2})
    row = [s for s in main._scan_sessions_sync() if s["agent"] == "hermes"][0]
    assert row["cost"] > 0
    assert row["cost_status"] == "tt-computed"


def test_local_session_with_no_tokens_is_unpriced_not_zero_marginal(tmp_path,
                                                                    monkeypatch):
    """The empty-session trap: with 0 tokens there was nothing to price, so
    "local model, therefore $0 marginal" is a claim we did not earn. Unpriced
    must win over deliberate-zero whenever the session recorded no tokens,
    otherwise one aborted Ollama run reads as a positive free-run finding."""
    _zero_marginal_home(tmp_path, monkeypatch,
                        [_row("20260601_000000_5555ffff", model="qwen3-coder:30b",
                              provider="ollama",
                              base_url="http://localhost:11434",
                              tokens=(0, 0))],
                        local=True)
    row = [s for s in main._scan_sessions_sync() if s["agent"] == "hermes"][0]
    assert row["tokens"]["total"] == 0
    assert row["cost"] is None                 # "not captured", never $0.00
    assert row["cost_status"] == "unpriced"
    assert row["cost_status"] != "zero-marginal"


def test_subscription_session_with_no_tokens_is_unpriced(tmp_path, monkeypatch):
    """Same trap on the subscription side: a flat-fee model still needs tokens
    before we can say anything about what it cost."""
    _zero_marginal_home(tmp_path, monkeypatch,
                        [_row("20260601_000000_6666aaaa", model="gpt-5.4",
                              tokens=(0, 0))],
                        sub_models={"gpt-5.4"})
    row = [s for s in main._scan_sessions_sync() if s["agent"] == "hermes"][0]
    assert row["cost"] is None
    assert row["cost_status"] == "unpriced"


def test_zero_marginal_is_not_counted_as_tt_computed(tmp_path, monkeypatch):
    _zero_marginal_home(tmp_path, monkeypatch,
                        [_row("20260601_000000_2222bbbb", model="gpt-5.4")],
                        sub_models={"gpt-5.4"})
    t = _telemetry(monkeypatch)
    c = t["cost"]
    assert c["confidence"]["zero-marginal"] == 1
    assert c["confidence"]["tt-computed"] == 0
    assert c["usd_by_confidence"]["tt-computed"] == 0.0


def test_all_zero_marginal_reports_zero_without_claiming_a_price(tmp_path, monkeypatch):
    """The exact case that used to render a bare, confident "API equiv. $0.00".

    Every session prices to a deliberate zero, so total_usd is 0.0 — but the
    payload now says WHY: all N sessions are zero-marginal, none tt-computed.
    """
    rows = [_row(f"2026060{i}_000000_{i}{i}{i}{i}cccc", model="gpt-5.4")
            for i in range(1, 5)]
    _zero_marginal_home(tmp_path, monkeypatch, rows, sub_models={"gpt-5.4"})
    sessions = [s for s in main._scan_sessions_sync() if s["agent"] == "hermes"]
    assert len(sessions) == 4
    assert all(s["cost"] == 0.0 for s in sessions)

    t = _telemetry(monkeypatch)
    c = t["cost"]
    assert c["confidence"]["zero-marginal"] == 4
    assert c["confidence"]["tt-computed"] == 0
    assert c["confidence"]["unpriced"] == 0
    assert c["total_usd"] == 0.0
    assert c["usd_by_confidence"]["zero-marginal"] == 0.0
    # Hermes never claimed these were flat-plan; the inference is TT's own, so
    # the provider-claim subtotal stays untouched.
    assert c["subscription_included_usd"] == 0.0


def test_confidence_dicts_are_total_not_sparse(tmp_path, monkeypatch):
    """All five keys present in both dicts, even for empty buckets.

    A sparse dict makes the frontend guess whether a missing key means zero or
    means the backend is older than the key.
    """
    _zero_marginal_home(tmp_path, monkeypatch,
                        [_row("20260601_000000_3333dddd", model="gpt-5.4")],
                        sub_models={"gpt-5.4"})
    c = _telemetry(monkeypatch)["cost"]
    expected = ["provider-reported", "provider-estimated", "tt-computed",
                "zero-marginal", "unpriced"]
    assert list(c["confidence"]) == expected          # order too, not just membership
    assert list(c["usd_by_confidence"]) == expected
    assert set(ht.COST_STATUSES) == set(expected)
    assert sum(c["confidence"].values()) == 1


def test_empty_status_buckets_survive_an_empty_session_set():
    c = ht._cost([])
    assert c["confidence"] == {k: 0 for k in ht.COST_STATUSES}
    assert c["usd_by_confidence"] == {k: 0.0 for k in ht.COST_STATUSES}
    assert c["total_usd"] == 0.0


# --------------------------------------------------------------------------- #
# EMPTY_ENTRY is shared state — it must be unmutatable
# --------------------------------------------------------------------------- #

def test_empty_entry_cannot_be_mutated_through_a_caller():
    """One append on the shared fallback would leak into every other session."""
    with pytest.raises(TypeError):
        ht.EMPTY_ENTRY["api_calls"] = [{"model": "poison"}]
    with pytest.raises(AttributeError):
        ht.EMPTY_ENTRY["api_calls"].append({"model": "poison"})
    with pytest.raises(AttributeError):
        ht.EMPTY_ENTRY["tool_calls"].append({"tool": "poison"})
    assert ht.EMPTY_ENTRY == {"api_calls": (), "tool_calls": ()}


def test_missing_session_overlay_gets_a_fresh_empty_list(tmp_path, monkeypatch):
    """The overlay a caller receives is its own list, not the shared fallback."""
    monkeypatch.setattr(main, "HERMES_DIR", tmp_path / "nope")
    a = main._hermes_log_summary("20260101_000000_aaaa1111")
    b = main._hermes_log_summary("20260101_000000_bbbb2222")
    assert a["api_calls"] == [] and a["tool_calls"] == []
    a["api_calls"].append({"model": "poison"})
    assert b["api_calls"] == []
    assert ht.EMPTY_ENTRY["api_calls"] == ()


def test_by_model_outcomes_are_capped_at_the_ten_largest():
    """Model names are open-set; the payload must stay bounded."""
    sessions = []
    for i in range(15):
        for _ in range(i + 1):               # model-i has i+1 sessions
            sessions.append({"model": f"model-{i:02d}", "source_subtype": "cli",
                             "outcome": "completed"})
    o = ht._outcomes(sessions)
    assert len(o["by_model"]) == ht.BY_MODEL_LIMIT
    assert o["models_total"] == 15
    # The ten LARGEST, biggest first — not the first ten seen.
    assert [r["model"] for r in o["by_model"]] == [f"model-{i:02d}"
                                                   for i in range(14, 4, -1)]
    assert [r["total"] for r in o["by_model"]] == list(range(15, 5, -1))
    # by_source is a small closed-ish set and stays complete.
    assert len(o["by_source"]) == 1 and o["by_source"][0]["total"] == len(sessions)
