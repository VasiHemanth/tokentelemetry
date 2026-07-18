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


# --- Grok Build scheduler loop (~/.grok/sessions/.../chat_history.jsonl) -----

@pytest.mark.parametrize("text,expected", [
    ("every 2 hours", 7200),
    ("2h", 7200),
    ("every 30 minutes", 1800),
    ("30 minutes", 1800),
    ("60s", 60),
    ("45 seconds", 45),
    ("1 day", 86400),
    ("1d", 86400),
    ("every 5 minutes", 300),
    ("garbage", None),
    (None, None),
])
def test_grok_interval_to_seconds(text, expected):
    assert main._grok_interval_to_seconds(text) == expected


def _grok_fire(prompt="Run /tt-hot-topics-post for Reddit.", task="019f6409a0a1",
               interval="every 2 hours", recurring=True):
    reminder = (f"<user_query>\n<system-reminder>\nThis is a scheduled task execution "
                f"(task {task}, {interval}, {'recurring' if recurring else 'once'}).\n"
                f"</system-reminder>\n\n{prompt}")
    return {"type": "user", "synthetic_reason": "scheduler_fired",
            "content": [{"type": "text", "text": reminder}]}


def _grok_session_dir(tmp_path, *, fires, events=None):
    d = tmp_path / "grok_sess"
    d.mkdir(parents=True, exist_ok=True)
    (d / main.GROK_CHAT_HISTORY).write_text(
        "".join(json.dumps(x) + "\n" for x in fires), encoding="utf-8")
    if events is not None:
        (d / main.GROK_EVENTS).write_text(
            "".join(json.dumps(x) + "\n" for x in events), encoding="utf-8")
    return d


def test_grok_loop_detect_happy_path(tmp_path):
    fires = [_grok_fire() for _ in range(8)]
    events = [
        {"ts": "2026-07-15T04:29:40.384Z", "type": "tool_completed",
         "tool_name": "scheduler_create", "outcome": "success"},
        {"ts": "2026-07-17T18:31:46.026Z", "type": "tool_completed",
         "tool_name": "scheduler_delete", "outcome": "success"},
    ]
    d = _grok_session_dir(tmp_path, fires=fires, events=events)
    lp = main._grok_loop_detect(d, ["scheduler_create", "scheduler_delete"],
                                "2026-07-15T04:00:00Z", "2026-07-15T20:00:00Z")
    assert lp is not None
    assert lp["is_loop"] is True
    assert lp["mode"] == "scheduler"
    assert lp["job_id"] == "019f6409a0a1"
    assert lp["cadence"] == "every 2 hours"
    assert lp["cadence_seconds"] == 7200
    assert lp["iterations"] == 8
    assert lp["recurring"] is True
    assert lp["source_signal"] == "grok_scheduler"
    assert lp["prompt_preview"].startswith("Run /tt-hot-topics-post")
    # created_at comes from the scheduler_create event; cancel from scheduler_delete.
    assert lp["created_at"] == "2026-07-15T04:29:40.384Z"
    assert lp["cancelled"] is True
    assert lp["cancelled_at"] == "2026-07-17T18:31:46.026Z"
    # Grok exposes no per-turn token split -> honest zero footprint (no fabrication).
    assert lp["footprint_tokens"] == 0
    assert lp["footprint_cost"] == 0


def test_grok_loop_detect_gated_on_scheduler_create(tmp_path):
    """No scheduler_create in signals.toolsUsed -> the deeper scan never runs."""
    d = _grok_session_dir(tmp_path, fires=[_grok_fire()])
    assert main._grok_loop_detect(d, ["read_file", "grep"], None, None) is None


def test_grok_loop_detect_ignores_one_shot(tmp_path):
    """A scheduled run marked 'once' (not recurring) is not a loop."""
    d = _grok_session_dir(tmp_path, fires=[_grok_fire(recurring=False)])
    assert main._grok_loop_detect(d, ["scheduler_create"], None, None) is None


def test_grok_loop_detect_requires_a_fire(tmp_path):
    """scheduler_create present but zero firings -> not detected (task id +
    interval only exist in the fire reminder)."""
    d = _grok_session_dir(tmp_path, fires=[
        {"type": "user", "content": [{"type": "text", "text": "ordinary prompt"}]}])
    assert main._grok_loop_detect(d, ["scheduler_create"], None, None) is None


def test_grok_loop_lifecycle_no_7day_cap(tmp_path):
    """A Grok 'scheduler' loop is a fixed interval but NOT a Claude cron, so the
    7-day auto-expiry must not apply — an old, uncancelled one ages to expired
    via cadence staleness, not the cron ceiling."""
    fires = [_grok_fire() for _ in range(3)]
    d = _grok_session_dir(tmp_path, fires=fires)
    lp = main._grok_loop_detect(d, ["scheduler_create"],
                                _iso(NOW - timedelta(days=10)),
                                _iso(NOW - timedelta(days=9)))
    s = {"id": "g", "agent": "grok", "loop": lp}
    main._annotate_loop_lifecycle([s], NOW)
    assert lp["expires_at"] is None                 # no 7-day cap for scheduler mode
    assert lp["state"] == "expired"
    assert lp["expired_reason"] == "stale_session_ended"


# --- Cline "Scheduled Agents" (cron.db) -------------------------------------

def _cline_cron_db(path, *, specs, runs):
    """Build a cron.db with the real (subset) Cline schema and seed rows."""
    import sqlite3 as _sq
    conn = _sq.connect(str(path))
    conn.execute("""CREATE TABLE cron_specs (
        spec_id TEXT PRIMARY KEY, external_id TEXT, source_path TEXT,
        trigger_kind TEXT, enabled INTEGER DEFAULT 1, removed INTEGER DEFAULT 0,
        title TEXT, prompt TEXT, schedule_expr TEXT, last_run_at TEXT,
        next_run_at TEXT, created_at TEXT, updated_at TEXT)""")
    conn.execute("""CREATE TABLE cron_runs (
        run_id TEXT PRIMARY KEY, spec_id TEXT, trigger_kind TEXT, status TEXT,
        session_id TEXT, completed_at TEXT, created_at TEXT)""")
    conn.executemany(
        "INSERT INTO cron_specs (spec_id,external_id,source_path,trigger_kind,enabled,"
        "removed,title,prompt,schedule_expr,last_run_at,next_run_at,created_at,updated_at) "
        "VALUES (:spec_id,:external_id,:source_path,:trigger_kind,:enabled,:removed,:title,"
        ":prompt,:schedule_expr,:last_run_at,:next_run_at,:created_at,:updated_at)", specs)
    conn.executemany(
        "INSERT INTO cron_runs (run_id,spec_id,trigger_kind,status,session_id,completed_at,created_at) "
        "VALUES (:run_id,:spec_id,:trigger_kind,:status,:session_id,:completed_at,:created_at)", runs)
    conn.commit()
    conn.close()


def test_cline_loop_specs_schedule(tmp_path):
    db = tmp_path / "cron.db"
    _cline_cron_db(
        db,
        specs=[{"spec_id": "spec-1", "external_id": "nightly-audit", "source_path": "/w/a.md",
                "trigger_kind": "schedule", "enabled": 1, "removed": 0, "title": "Nightly audit",
                "prompt": "Audit the repo for new TODOs", "schedule_expr": "0 9 * * *",
                "last_run_at": "2026-07-16T09:00:00Z", "next_run_at": "2026-07-17T09:00:00Z",
                "created_at": "2026-07-10T09:00:00Z", "updated_at": "2026-07-16T09:00:00Z"}],
        runs=[
            {"run_id": "r1", "spec_id": "spec-1", "trigger_kind": "schedule", "status": "done",
             "session_id": "sess-old", "completed_at": "2026-07-15T09:00:00Z", "created_at": "2026-07-15T09:00:00Z"},
            {"run_id": "r2", "spec_id": "spec-1", "trigger_kind": "schedule", "status": "done",
             "session_id": "sess-latest", "completed_at": "2026-07-16T09:00:00Z", "created_at": "2026-07-16T09:00:00Z"},
        ],
    )
    loops = main._cline_loop_specs(db)
    # Anchored to the LATEST run's session, not the older one.
    assert set(loops.keys()) == {"sess-latest"}
    lp = loops["sess-latest"]
    assert lp["is_loop"] is True
    assert lp["mode"] == "cron"
    assert lp["job_id"] == "nightly-audit"
    assert lp["cadence"] == "0 9 * * *"
    assert lp["cadence_seconds"] == 86400          # daily
    assert lp["iterations"] == 2                    # both done runs
    assert lp["prompt_preview"].startswith("Audit the repo")
    assert lp["cancelled"] is False
    assert lp["footprint_tokens"] == 0             # each fire is its own counted session


def test_cline_loop_specs_ignores_one_off_and_disabled(tmp_path):
    db = tmp_path / "cron.db"
    _cline_cron_db(
        db,
        specs=[
            {"spec_id": "one", "external_id": "x", "source_path": "/w/1.md", "trigger_kind": "one_off",
             "enabled": 1, "removed": 0, "title": "once", "prompt": "p", "schedule_expr": None,
             "last_run_at": None, "next_run_at": None, "created_at": "2026-07-16T00:00:00Z",
             "updated_at": "2026-07-16T00:00:00Z"},
            {"spec_id": "disabled", "external_id": "y", "source_path": "/w/2.md", "trigger_kind": "schedule",
             "enabled": 0, "removed": 0, "title": "paused", "prompt": "p", "schedule_expr": "0 * * * *",
             "last_run_at": "2026-07-16T00:00:00Z", "next_run_at": None, "created_at": "2026-07-10T00:00:00Z",
             "updated_at": "2026-07-16T00:00:00Z"},
        ],
        runs=[
            {"run_id": "a", "spec_id": "one", "trigger_kind": "one_off", "status": "done",
             "session_id": "s-oneoff", "completed_at": "2026-07-16T00:00:00Z", "created_at": "2026-07-16T00:00:00Z"},
            {"run_id": "b", "spec_id": "disabled", "trigger_kind": "schedule", "status": "done",
             "session_id": "s-disabled", "completed_at": "2026-07-16T00:00:00Z", "created_at": "2026-07-16T00:00:00Z"},
        ],
    )
    loops = main._cline_loop_specs(db)
    # one_off is not a loop; the disabled schedule IS surfaced but marked cancelled.
    assert "s-oneoff" not in loops
    assert "s-disabled" in loops
    assert loops["s-disabled"]["cancelled"] is True


def test_cline_loop_specs_never_fired_has_no_anchor(tmp_path):
    db = tmp_path / "cron.db"
    _cline_cron_db(
        db,
        specs=[{"spec_id": "spec-nf", "external_id": "z", "source_path": "/w/3.md", "trigger_kind": "schedule",
                "enabled": 1, "removed": 0, "title": "never fired", "prompt": "p", "schedule_expr": "0 9 * * *",
                "last_run_at": None, "next_run_at": "2026-07-20T09:00:00Z", "created_at": "2026-07-16T00:00:00Z",
                "updated_at": "2026-07-16T00:00:00Z"}],
        runs=[],
    )
    assert main._cline_loop_specs(db) == {}


def test_cline_loop_specs_missing_db(tmp_path):
    assert main._cline_loop_specs(tmp_path / "nope.db") == {}


def test_cline_scan_attaches_loop_to_anchor_session(tmp_path, monkeypatch):
    """End-to-end: a schedule in cron.db attaches its loop to the matching
    session row from sessions.db, and only that one."""
    import sqlite3 as _sq
    db_dir = tmp_path / "data" / "db"
    db_dir.mkdir(parents=True)
    # Minimal sessions.db with the columns the scanner reads.
    sdb = _sq.connect(str(db_dir / "sessions.db"))
    sdb.execute("""CREATE TABLE sessions (
        session_id TEXT, model TEXT, workspace_root TEXT, cwd TEXT, started_at TEXT,
        metadata_json TEXT, messages_path TEXT, prompt TEXT, provider TEXT, status TEXT,
        is_subagent INTEGER, parent_session_id TEXT, agent_id TEXT, team_name TEXT)""")
    for sid in ("sess-latest", "sess-plain"):
        sdb.execute(
            "INSERT INTO sessions (session_id,model,workspace_root,cwd,started_at,metadata_json,"
            "messages_path,prompt,provider,status,is_subagent,parent_session_id,agent_id,team_name) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (sid, "claude-opus-4-8", "/w", "/w", "2026-07-16T09:00:00Z",
             '{"usage":{"inputTokens":100,"outputTokens":50}}', None, "hi", "anthropic",
             "done", 0, None, None, None))
    sdb.commit(); sdb.close()

    _cline_cron_db(
        db_dir / "cron.db",
        specs=[{"spec_id": "spec-1", "external_id": "nightly", "source_path": "/w/a.md",
                "trigger_kind": "schedule", "enabled": 1, "removed": 0, "title": "Nightly",
                "prompt": "Do the nightly thing", "schedule_expr": "0 9 * * *",
                "last_run_at": "2026-07-16T09:00:00Z", "next_run_at": "2026-07-17T09:00:00Z",
                "created_at": "2026-07-10T09:00:00Z", "updated_at": "2026-07-16T09:00:00Z"}],
        runs=[{"run_id": "r2", "spec_id": "spec-1", "trigger_kind": "schedule", "status": "done",
               "session_id": "sess-latest", "completed_at": "2026-07-16T09:00:00Z",
               "created_at": "2026-07-16T09:00:00Z"}],
    )

    monkeypatch.setattr(main, "CLINE_DIR", tmp_path)
    monkeypatch.setattr(main, "CLINE_VSCODE_DIR", tmp_path / "no_vscode")
    monkeypatch.setattr(main, "_load_project_aliases", lambda: {})
    sessions = {s["id"]: s for s in main._scan_cline_sessions()}
    assert "loop" in sessions["sess-latest"] and sessions["sess-latest"]["loop"]["job_id"] == "nightly"
    assert "loop" not in sessions["sess-plain"]
