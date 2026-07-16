"""Tests for /loop telemetry — see backend/main.py loop detection + lifecycle.

Covers:
  - _cron_to_seconds(): coarse cadence for the 5-field cron shapes we emit.
  - _annotate_loop_lifecycle(): the wall-clock state machine (cancelled ->
    one-shot-done -> cron-7d-expired -> stale -> active -> unknown), asserting
    state/active/expired_reason and that expires_at is set for recurring crons.
  - Detection: a real Claude scan builds sess["loop"] from a CronCreate
    tool_use, its job-id-carrying tool_result, and re-injected fires.

Run: pytest backend/test_loops.py
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import main  # noqa: E402

UTC = timezone.utc


# --- _cron_to_seconds -------------------------------------------------------

@pytest.mark.parametrize("cron,expected", [
    ("13 * * * *", 3600),     # hourly at minute 13
    ("*/5 * * * *", 300),     # every 5 minutes
    ("0 */2 * * *", 7200),    # every 2 hours
    ("30 9 * * *", 86400),    # daily at 09:30
    ("garbage", None),        # not a 5-field cron -> unknown cadence
])
def test_cron_to_seconds(cron, expected):
    assert main._cron_to_seconds(cron) == expected


# --- _annotate_loop_lifecycle state machine ---------------------------------

NOW = datetime(2026, 7, 16, tzinfo=UTC)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _loop_session(**loop_kw):
    loop = {"is_loop": True, "mode": "fixed_cron", "cadence": "* * * * *",
            "cadence_seconds": 3600, "recurring": True, "job_id": "abc123",
            "source_signal": "CronCreate", "prompt_preview": "do X",
            "created_at": None, "last_fired": None, "iterations": 0,
            "cancelled": False, "cancelled_at": None}
    loop.update(loop_kw)
    return {"id": loop_kw.get("_id", "s"), "agent": "claude", "loop": loop}


def test_lifecycle_cancelled():
    s = _loop_session(cancelled=True, cancelled_at=_iso(NOW - timedelta(hours=1)))
    main._annotate_loop_lifecycle([s], NOW)
    lp = s["loop"]
    assert lp["state"] == "cancelled"
    assert lp["active"] is False
    assert lp["expired_reason"] == "cancelled"


def test_lifecycle_cron_expired_7d():
    # Recurring fixed_cron created 8 days ago: past the Claude 7-day ceiling.
    created = NOW - timedelta(days=8)
    s = _loop_session(mode="fixed_cron", recurring=True, created_at=_iso(created))
    main._annotate_loop_lifecycle([s], NOW)
    lp = s["loop"]
    assert lp["state"] == "expired"
    assert lp["active"] is False
    assert lp["expired_reason"] == "cron_expired_7d"
    # expires_at is set for recurring fixed_cron loops (created + 7d).
    assert lp["expires_at"] == _iso(created + timedelta(days=7))


def test_lifecycle_one_shot_completed():
    # One-shot (recurring False) that has already fired once.
    s = _loop_session(recurring=False, iterations=1,
                      created_at=_iso(NOW - timedelta(hours=2)))
    main._annotate_loop_lifecycle([s], NOW)
    lp = s["loop"]
    assert lp["state"] == "expired"
    assert lp["active"] is False
    assert lp["expired_reason"] == "one_shot_completed"
    # Not a recurring fixed_cron -> no 7-day window.
    assert lp["expires_at"] is None


def test_lifecycle_active():
    created = NOW - timedelta(minutes=10)
    last = NOW - timedelta(minutes=5)
    s = _loop_session(mode="fixed_cron", recurring=True, cadence_seconds=3600,
                      created_at=_iso(created), last_fired=_iso(last))
    main._annotate_loop_lifecycle([s], NOW)
    lp = s["loop"]
    assert lp["state"] == "active"
    assert lp["active"] is True
    assert lp["expired_reason"] is None
    assert lp["expires_at"] == _iso(created + timedelta(days=7))


def test_lifecycle_stale_session_ended():
    # Recurring cron whose last fire is 3 days ago — well past the cadence
    # grace window, but created recently enough not to hit the 7-day ceiling.
    created = NOW - timedelta(days=3)
    last = NOW - timedelta(days=3)
    s = _loop_session(mode="fixed_cron", recurring=True, cadence_seconds=3600,
                      created_at=_iso(created), last_fired=_iso(last))
    main._annotate_loop_lifecycle([s], NOW)
    lp = s["loop"]
    assert lp["state"] == "expired"
    assert lp["active"] is False
    assert lp["expired_reason"] == "stale_session_ended"
    assert lp["expires_at"] == _iso(created + timedelta(days=7))


def test_lifecycle_unknown_dynamic():
    # Dynamic loop, no bound cadence and no fires yet -> unknown (never faked
    # active). No created_at, so no expires_at either.
    s = _loop_session(mode="dynamic", cadence="self-paced", cadence_seconds=None,
                      created_at=None, last_fired=None)
    main._annotate_loop_lifecycle([s], NOW)
    lp = s["loop"]
    assert lp["state"] == "unknown"
    assert lp["active"] is False
    assert lp["expired_reason"] is None
    assert lp["expires_at"] is None


def test_lifecycle_skips_non_loop_sessions():
    # Sessions without a loop dict are left untouched.
    s = {"id": "x", "agent": "claude"}
    main._annotate_loop_lifecycle([s, {"id": "y", "loop": {"is_loop": False}}], NOW)
    assert "state" not in s.get("loop", {}) if s.get("loop") else True


# --- detection via the real scan --------------------------------------------

LOOP_SID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
PROJ = "-tmp-loop"


@pytest.fixture
def scan_env(tmp_path, monkeypatch):
    """Point every agent store at empty tmp paths so the scan is hermetic —
    only the Claude tree we build under tmp_path/.claude is discovered."""
    missing = tmp_path / "missing"
    for attr in ("CODEX_DIR", "GEMINI_DIR", "QWEN_DIR", "VIBE_DIR", "OLLAMA_DIR",
                 "GROK_SESSIONS_DIR", "VSCODE_STORAGE", "CURSOR_STORAGE",
                 "COPILOT_CLI_DIR", "ANTIGRAVITY_BRAIN_DIR", "ANTIGRAVITY_CLI_DIR",
                 "HERMES_DIR", "PI_SESSIONS_DIR"):
        monkeypatch.setattr(main, attr, missing / attr.lower())
    monkeypatch.setattr(main, "ANTIGRAVITY_BRAIN_SOURCES", [])
    monkeypatch.setattr(main, "ANTIGRAVITY_BRAIN_DIRS", [])
    monkeypatch.setattr(main, "_antigravity_cli_meta", lambda *a, **k: {})
    monkeypatch.setattr(main, "CLAUDE_DIR", tmp_path / ".claude")
    monkeypatch.setattr(main, "CURSOR_DIR", tmp_path / ".cursor")
    monkeypatch.setattr(main, "OPENCODE_DB", tmp_path / "opencode.db")
    monkeypatch.setattr(main, "HERMES_DB", tmp_path / "hermes-state.db")
    monkeypatch.setattr(main, "HERMES_PROFILES_DIR", missing / "hermes-profiles")
    monkeypatch.setattr(main, "PROJECT_ALIASES_FILE", tmp_path / "aliases.json")
    monkeypatch.setenv("TOKENTELEMETRY_DATA_DIR", str(tmp_path / "tt_data"))
    return tmp_path


def _make_loop_tree(claude_dir, sid=LOOP_SID):
    """A Claude session that ran /loop: the user prompt, an assistant turn
    whose content carries a CronCreate tool_use, the tool_result that reports
    the scheduled job id, then one re-injected fire of the loop prompt."""
    proj = claude_dir / "projects" / PROJ
    proj.mkdir(parents=True, exist_ok=True)
    lines = [
        {"type": "user", "timestamp": "2026-07-16T00:00:00Z", "cwd": "/tmp/loop",
         "message": {"role": "user", "content": "/loop 7 * * * * do X"}},
        {"type": "assistant", "timestamp": "2026-07-16T00:00:01Z",
         "message": {"model": "claude-opus-4-8",
                     "usage": {"input_tokens": 10, "output_tokens": 5},
                     "content": [{"type": "tool_use", "name": "CronCreate", "id": "tu1",
                                  "input": {"cron": "7 * * * *", "recurring": True,
                                            "prompt": "do X"}}]}},
        {"type": "user", "timestamp": "2026-07-16T00:00:02Z",
         "message": {"role": "user", "content": [
             {"type": "tool_result", "tool_use_id": "tu1",
              "content": "Scheduled recurring job abc123 (runs at 7 * * * *)"}]}},
        {"type": "user", "timestamp": "2026-07-16T01:00:00Z",
         "message": {"role": "user", "content": "do X"}},
    ]
    (proj / f"{sid}.jsonl").write_text(
        "".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
    return proj / f"{sid}.jsonl"


def test_scan_builds_loop_field(scan_env):
    _make_loop_tree(scan_env / ".claude")
    sessions = [s for s in main._scan_sessions_sync()
                if s["agent"] == "claude" and s["id"] == LOOP_SID]
    assert len(sessions) == 1
    lp = sessions[0]["loop"]
    assert lp["is_loop"] is True
    assert lp["mode"] == "fixed_cron"
    assert lp["cadence"] == "7 * * * *"
    assert lp["job_id"] == "abc123"
    assert lp["cadence_seconds"] == 3600
    assert lp["recurring"] is True
    assert lp["source_signal"] == "CronCreate"
    # The re-injected "do X" user turn is counted as one fire.
    assert lp["iterations"] >= 1


def test_scan_non_loop_session_has_no_loop_field(scan_env):
    proj = (scan_env / ".claude") / "projects" / PROJ
    proj.mkdir(parents=True, exist_ok=True)
    sid = "11111111-1111-1111-1111-111111111111"
    (proj / f"{sid}.jsonl").write_text(
        json.dumps({"type": "user", "timestamp": "2026-07-16T00:00:00Z",
                    "cwd": "/tmp/loop",
                    "message": {"role": "user", "content": "hi"}}) + "\n",
        encoding="utf-8")
    s = [s for s in main._scan_sessions_sync() if s["id"] == sid][0]
    assert "loop" not in s


FOOT_SID = "cccccccc-cccc-cccc-cccc-cccccccccccc"


def test_scan_loop_footprint_only_counts_fire_turns(scan_env):
    """The loop's footprint = usage from its fire-response turns ONLY, never the
    whole session. A tool_result echoing the prompt is not a fire; a genuine
    non-loop turn's usage is excluded and must not be attributed to the loop."""
    proj = (scan_env / ".claude") / "projects" / PROJ
    proj.mkdir(parents=True, exist_ok=True)
    lines = [
        {"type": "user", "timestamp": "2026-07-16T00:00:00Z", "cwd": "/tmp/loop",
         "message": {"role": "user", "content": "/loop 7 * * * * do X"}},
        # Setup turn (usage 10/5) — span not open yet, must NOT be attributed.
        {"type": "assistant", "timestamp": "2026-07-16T00:00:01Z",
         "message": {"model": "claude-opus-4-8",
                     "usage": {"input_tokens": 10, "output_tokens": 5},
                     "content": [{"type": "tool_use", "name": "CronCreate", "id": "tu1",
                                  "input": {"cron": "7 * * * *", "recurring": True,
                                            "prompt": "do X"}}]}},
        {"type": "user", "timestamp": "2026-07-16T00:00:02Z",
         "message": {"role": "user", "content": [
             {"type": "tool_result", "tool_use_id": "tu1",
              "content": "Scheduled recurring job abc123 (runs at 7 * * * *)"}]}},
        # A tool_result that ECHOES the prompt "do X" — must NOT be a fire.
        {"type": "user", "timestamp": "2026-07-16T00:30:00Z",
         "message": {"role": "user", "content": [
             {"type": "tool_result", "tool_use_id": "tu9", "content": "grep found: do X"}]}},
        # Real fire — opens the span.
        {"type": "user", "timestamp": "2026-07-16T01:00:00Z",
         "message": {"role": "user", "content": "do X"}},
        # Fire response (usage 100/50) — MUST be attributed to the loop.
        {"type": "assistant", "timestamp": "2026-07-16T01:00:01Z",
         "message": {"model": "claude-opus-4-8",
                     "usage": {"input_tokens": 100, "output_tokens": 50},
                     "content": [{"type": "text", "text": "here is X"}]}},
        # Genuine non-loop user turn — closes the span.
        {"type": "user", "timestamp": "2026-07-16T02:00:00Z",
         "message": {"role": "user", "content": "now do something completely unrelated"}},
        # Non-loop response (usage 1000/500) — MUST NOT be attributed.
        {"type": "assistant", "timestamp": "2026-07-16T02:00:01Z",
         "message": {"model": "claude-opus-4-8",
                     "usage": {"input_tokens": 1000, "output_tokens": 500},
                     "content": [{"type": "text", "text": "done"}]}},
    ]
    (proj / f"{FOOT_SID}.jsonl").write_text(
        "".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
    s = [s for s in main._scan_sessions_sync() if s["id"] == FOOT_SID][0]
    lp = s["loop"]
    # Footprint = ONLY the fire response's input+output (100+50), not the setup
    # turn (10+5), not the unrelated turn (1000+500).
    assert lp["footprint_tokens"] == 150
    assert lp["footprint_cost"] > 0
    # Always <= the whole session.
    assert lp["footprint_tokens"] < s["tokens"]["total"]
    assert lp["footprint_cost"] <= (s.get("cost") or 0) + 1e-9
    # The tool_result echoing "do X" was NOT counted as a fire.
    assert lp["iterations"] == 1
