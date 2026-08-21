"""Tests for Codex Goal Mode (`/goal`) telemetry.

Mirrors test_loops.py: build throwaway SQLite DBs on disk, then assert on what
`codex_goals.read_goals` returns. The cases that matter are the ones that keep
the feature HONEST (never invent a status, never show a confident zero for a
field the agent cannot record) and the ones that survive Codex's real-world
oddity of shipping two goal DBs at different migration levels.
"""
import sqlite3
from pathlib import Path

import pytest

import codex_goals


# --- helpers ---------------------------------------------------------------

V1_SCHEMA = """
CREATE TABLE thread_goals (
    thread_id TEXT, goal_id TEXT, objective TEXT, status TEXT,
    token_budget INTEGER, tokens_used INTEGER, time_used_seconds INTEGER,
    created_at_ms INTEGER, updated_at_ms INTEGER
);
"""

V2_EXTRA = "CREATE TABLE thread_goal_continuation_deferrals (thread_id TEXT);"


def make_db(path: Path, rows=(), *, v2=False, deferrals=()):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(V1_SCHEMA)
    if v2:
        con.executescript(V2_EXTRA)
        con.executemany("INSERT INTO thread_goal_continuation_deferrals VALUES (?)",
                        [(t,) for t in deferrals])
    con.executemany("INSERT INTO thread_goals VALUES (?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()


def row(thread="t1", goal="g1", objective="ship it", status="active",
        budget=None, used=1000, secs=60, created=1_781_336_283_882,
        updated=1_781_342_475_254):
    return (thread, goal, objective, status, budget, used, secs, created, updated)


@pytest.fixture
def codex_dir(tmp_path):
    return tmp_path / ".codex"


# --- basic mapping ---------------------------------------------------------

def test_reads_a_goal_and_reports_native_counts(codex_dir):
    make_db(codex_dir / "goals_1.sqlite", [row(used=270359, secs=2615)])
    goals = codex_goals.read_goals(codex_dir)
    assert list(goals) == ["t1"]
    g = goals["t1"][0]
    assert g["source"] == "codex"
    assert g["tokens"] == 270359
    assert g["duration_seconds"] == 2615
    assert g["cost_basis"] == "native"
    # Codex wrote the status down, so we must not label it a guess.
    assert g["state_source"] == "reported"


def test_timestamps_become_aware_utc_iso(codex_dir):
    make_db(codex_dir / "goals_1.sqlite", [row()])
    g = codex_goals.read_goals(codex_dir)["t1"][0]
    assert g["created_at"].startswith("2026-06-13T07:38:03")
    assert g["created_at"].endswith("+00:00")


@pytest.mark.parametrize("raw,expected", [
    ("active", "active"), ("running", "active"), ("in_progress", "active"),
    ("paused", "paused"), ("complete", "complete"), ("completed", "complete"),
    ("blocked", "blocked"), ("ACTIVE", "active"), ("  paused ", "paused"),
])
def test_status_vocabulary_is_normalised(codex_dir, raw, expected):
    make_db(codex_dir / "goals_1.sqlite", [row(status=raw)])
    assert codex_goals.read_goals(codex_dir)["t1"][0]["state"] == expected


def test_unknown_status_is_not_guessed_but_raw_is_kept(codex_dir):
    """A status we don't recognise must degrade to "unknown", never to a
    plausible-looking "active"."""
    make_db(codex_dir / "goals_1.sqlite", [row(status="hibernating")])
    g = codex_goals.read_goals(codex_dir)["t1"][0]
    assert g["state"] == "unknown"
    assert g["evidence"]["status_raw"] == "hibernating"


def test_objective_is_truncated_and_flagged(codex_dir):
    make_db(codex_dir / "goals_1.sqlite", [row(objective="x" * 500)])
    g = codex_goals.read_goals(codex_dir)["t1"][0]
    assert len(g["objective"]) == codex_goals.OBJECTIVE_MAX
    assert g["objective_truncated"] is True


def test_short_objective_not_flagged_truncated(codex_dir):
    make_db(codex_dir / "goals_1.sqlite", [row(objective="short")])
    assert codex_goals.read_goals(codex_dir)["t1"][0]["objective_truncated"] is False


# --- the two-DB / migration-level trap -------------------------------------

def test_populated_db_wins_over_empty_one_regardless_of_path(codex_dir):
    """Codex leaves an empty newer-schema DB beside a populated older one, so
    neither "first path" nor "newest schema" picks correctly."""
    make_db(codex_dir / "sqlite" / "goals_1.sqlite", [row(goal="real")])
    make_db(codex_dir / "goals_1.sqlite", [], v2=True)
    goals = codex_goals.read_goals(codex_dir)
    assert goals["t1"][0]["goal_id"] == "real"


def test_populated_db_wins_in_the_other_arrangement(codex_dir):
    make_db(codex_dir / "sqlite" / "goals_1.sqlite", [])
    make_db(codex_dir / "goals_1.sqlite", [row(goal="real")], v2=True)
    assert codex_goals.read_goals(codex_dir)["t1"][0]["goal_id"] == "real"


def test_v1_db_yields_null_deferrals_not_zero(codex_dir):
    """None means "this Codex build cannot record deferrals"; 0 would be a
    confident claim the agent never made."""
    make_db(codex_dir / "goals_1.sqlite", [row()])
    assert codex_goals.read_goals(codex_dir)["t1"][0]["evidence"]["deferrals"] is None


def test_v2_db_counts_deferrals(codex_dir):
    make_db(codex_dir / "goals_1.sqlite", [row()], v2=True,
            deferrals=["t1", "t1", "other"])
    assert codex_goals.read_goals(codex_dir)["t1"][0]["evidence"]["deferrals"] == 2


def test_v2_db_reports_zero_deferrals_when_table_is_empty(codex_dir):
    make_db(codex_dir / "goals_1.sqlite", [row()], v2=True)
    assert codex_goals.read_goals(codex_dir)["t1"][0]["evidence"]["deferrals"] == 0


# --- robustness: reads never raise -----------------------------------------

def test_missing_dir_yields_no_goals(tmp_path):
    assert codex_goals.read_goals(tmp_path / "nope") == {}


def test_db_without_goals_table_yields_no_goals(codex_dir):
    codex_dir.mkdir(parents=True)
    con = sqlite3.connect(codex_dir / "goals_1.sqlite")
    con.executescript("CREATE TABLE unrelated (x INTEGER);")
    con.close()
    assert codex_goals.read_goals(codex_dir) == {}


def test_garbage_file_yields_no_goals(codex_dir):
    codex_dir.mkdir(parents=True)
    (codex_dir / "goals_1.sqlite").write_bytes(b"not a database at all")
    assert codex_goals.read_goals(codex_dir) == {}


def test_null_and_bad_values_do_not_raise(codex_dir):
    make_db(codex_dir / "goals_1.sqlite", [
        ("t1", None, None, None, None, None, None, None, None),
        ("t2", "g", "o", "active", "notanint", "notanint", "x", "y", "z"),
    ])
    goals = codex_goals.read_goals(codex_dir)
    assert goals["t1"][0]["tokens"] is None
    assert goals["t1"][0]["state"] == "unknown"
    assert goals["t1"][0]["created_at"] is None
    assert goals["t2"][0]["tokens"] is None


def test_rows_without_thread_id_are_dropped(codex_dir):
    make_db(codex_dir / "goals_1.sqlite", [row(thread=None), row(thread="t2")])
    assert list(codex_goals.read_goals(codex_dir)) == ["t2"]


# --- multiple goals --------------------------------------------------------

def test_multiple_goals_on_one_thread_are_ordered_oldest_first(codex_dir):
    make_db(codex_dir / "goals_1.sqlite", [
        row(goal="second", created=2_000_000_000_000),
        row(goal="first", created=1_000_000_000_000),
    ])
    ids = [g["goal_id"] for g in codex_goals.read_goals(codex_dir)["t1"]]
    assert ids == ["first", "second"]


def test_goals_split_across_threads(codex_dir):
    make_db(codex_dir / "goals_1.sqlite", [row(thread="a"), row(thread="b")])
    goals = codex_goals.read_goals(codex_dir)
    assert set(goals) == {"a", "b"}
    assert len(goals["a"]) == 1


# --- the honesty invariant -------------------------------------------------

def test_every_goal_declares_a_known_state_and_reported_source(codex_dir):
    allowed = {"active", "paused", "complete", "blocked", "unknown"}
    make_db(codex_dir / "goals_1.sqlite", [
        row(thread=f"t{i}", status=s)
        for i, s in enumerate(["active", "paused", "complete", "blocked",
                               "weird", None, ""])
    ])
    for goals in codex_goals.read_goals(codex_dir).values():
        for g in goals:
            assert g["state"] in allowed
            assert g["state_source"] == "reported"
            assert g["cost_basis"] == "native"


# ===========================================================================
# Claude Code / Grok / Antigravity — the inferred agents.
#
# These have no first-class goal store, so the tests below are mostly about
# what the parser must REFUSE to conclude.
# ===========================================================================
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import main  # noqa: E402

ARM = ('A session-scoped Stop hook is now active with condition: "{cond}". '
       "Briefly acknowledge the goal, then immediately start working toward it.")
GOAL_SID = "11111111-2222-3333-4444-555555555555"


@pytest.fixture
def scan_env(tmp_path, monkeypatch):
    """Hermetic scan: every agent store points at empty tmp paths, so only the
    Claude tree we build is discovered."""
    missing = tmp_path / "missing"
    for attr in ("CODEX_DIR", "GEMINI_DIR", "QWEN_DIR", "VIBE_DIR", "OLLAMA_DIR",
                 "GROK_SESSIONS_DIR", "GROK_UNIFIED_LOG", "VSCODE_STORAGE", "CURSOR_STORAGE",
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


def claude_session(tmp_path, lines, sid=GOAL_SID):
    proj = tmp_path / ".claude" / "projects" / "-tmp-goal"
    proj.mkdir(parents=True, exist_ok=True)
    (proj / f"{sid}.jsonl").write_text(
        "".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")


def scan_goals(sid=GOAL_SID):
    for s in main._scan_sessions_sync():
        if s.get("id") == sid:
            return s.get("goals") or []
    return []


def arm_rec(cond="finish the migration", ts="2026-07-20T00:00:00Z"):
    return {"type": "user", "timestamp": ts, "cwd": "/tmp/goal",
            "message": {"role": "user", "content": ARM.format(cond=cond)}}


def block_rec(ts, cond="finish the migration"):
    return {"type": "user", "timestamp": ts,
            "message": {"role": "user", "content": f"Stop hook feedback:\n[{cond}]"}}


def assistant_rec(ts, inp=100, out=50):
    return {"type": "assistant", "timestamp": ts,
            "message": {"model": "claude-opus-4-8",
                        "usage": {"input_tokens": inp, "output_tokens": out},
                        "content": []}}


# --- Claude: arming -------------------------------------------------------

def test_claude_arm_is_detected(scan_env):
    claude_session(scan_env, [arm_rec()])
    goals = scan_goals()
    assert len(goals) == 1
    assert goals[0]["source"] == "claude"
    assert goals[0]["state"] == "armed"
    assert goals[0]["state_source"] == "inferred"
    assert goals[0]["objective"].startswith("finish the migration")


def test_claude_compaction_replay_does_not_double_count(scan_env):
    """A compacted transcript replays the arm at a second line with an
    identical timestamp; that is one goal, not two."""
    a = arm_rec()
    claude_session(scan_env, [a, assistant_rec("2026-07-20T00:00:01Z"), a])
    assert len(scan_goals()) == 1


def test_claude_two_different_goals_are_two_records(scan_env):
    claude_session(scan_env, [
        arm_rec("first goal", "2026-07-20T00:00:00Z"),
        arm_rec("second goal", "2026-07-20T01:00:00Z"),
    ])
    goals = scan_goals()
    assert len(goals) == 2
    assert goals[0]["objective"].startswith("first goal")
    assert goals[1]["objective"].startswith("second goal")


# --- Claude: the false-positive classes -----------------------------------

def test_claude_tool_result_quoting_the_marker_is_not_a_goal(scan_env):
    """A session that greps its own transcript sees these strings in a
    tool_result. That is evidence of research, not of a goal."""
    claude_session(scan_env, [{
        "type": "user", "timestamp": "2026-07-20T00:00:00Z", "cwd": "/tmp/goal",
        "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1",
             "content": ARM.format(cond="not a real goal")}]}}])
    assert scan_goals() == []


def test_claude_assistant_prose_is_not_a_block(scan_env):
    """Writing ABOUT the feature must not register as having run it — this
    exact false positive was 2 of 17 blocks machine-wide during research."""
    claude_session(scan_env, [
        arm_rec(),
        {"type": "assistant", "timestamp": "2026-07-20T00:00:01Z",
         "message": {"model": "claude-opus-4-8", "usage": {},
                     "content": [{"type": "text",
                                  "text": "Stop hook feedback: is how blocks appear."}]}},
    ])
    goals = scan_goals()
    assert goals[0]["evidence"]["blocks"] == 0
    assert goals[0]["state"] == "armed"


def test_claude_blocks_without_an_arm_are_ignored(scan_env):
    """A user-configured Stop hook can block without any /goal involved."""
    claude_session(scan_env, [block_rec("2026-07-20T00:00:00Z")])
    assert scan_goals() == []


# --- Claude: blocks, bursts, the cap --------------------------------------

def test_claude_blocks_flip_state_and_are_counted(scan_env):
    claude_session(scan_env, [
        arm_rec(),
        block_rec("2026-07-20T00:10:00Z"),
        block_rec("2026-07-20T00:10:30Z"),
    ])
    g = scan_goals()[0]
    assert g["state"] == "blocked"
    assert g["evidence"]["blocks"] == 2


def test_claude_burst_grouping_matches_the_documented_cap(scan_env):
    """8 blocks inside the burst window is the cap firing; a gap longer than
    the window starts a new run instead of inflating the first."""
    recs = [arm_rec()]
    for i in range(8):                       # 20s apart -> one burst of 8
        recs.append(block_rec(f"2026-07-20T00:{10 + (i * 20) // 60:02d}:{(i * 20) % 60:02d}Z"))
    recs.append(block_rec("2026-07-20T01:00:00Z"))   # far later -> its own run
    claude_session(scan_env, recs)
    g = scan_goals()[0]
    assert g["evidence"]["block_bursts"] == [8, 1]
    assert g["evidence"]["cap_hit"] is True


def test_claude_seven_blocks_do_not_report_the_cap(scan_env):
    recs = [arm_rec()]
    for i in range(7):
        recs.append(block_rec(f"2026-07-20T00:{10 + (i * 20) // 60:02d}:{(i * 20) % 60:02d}Z"))
    claude_session(scan_env, recs)
    g = scan_goals()[0]
    assert g["evidence"]["block_bursts"] == [7]
    assert g["evidence"]["cap_hit"] is False


def test_claude_goal_is_never_complete(scan_env):
    """Claude emits no terminal event, so no input may yield "complete"."""
    claude_session(scan_env, [
        arm_rec(),
        block_rec("2026-07-20T00:10:00Z"),
        {"type": "user", "timestamp": "2026-07-20T00:20:00Z",
         "message": {"role": "user", "content": "thanks, the goal is met, all done"}},
    ])
    assert scan_goals()[0]["state"] in ("armed", "blocked", "unknown")


def test_claude_blocks_attach_to_the_goal_that_was_live(scan_env):
    claude_session(scan_env, [
        arm_rec("first goal", "2026-07-20T00:00:00Z"),
        block_rec("2026-07-20T00:05:00Z"),
        arm_rec("second goal", "2026-07-20T01:00:00Z"),
        block_rec("2026-07-20T01:05:00Z"),
        block_rec("2026-07-20T01:05:30Z"),
    ])
    goals = scan_goals()
    assert goals[0]["evidence"]["blocks"] == 1
    assert goals[1]["evidence"]["blocks"] == 2


# --- Claude: attributed cost ----------------------------------------------

def test_claude_only_post_block_turns_are_attributed(scan_env):
    """Work before the first block is ordinary session cost; only turns that
    ran BECAUSE a stop was blocked belong to the goal."""
    claude_session(scan_env, [
        arm_rec(),
        assistant_rec("2026-07-20T00:01:00Z", inp=9000, out=9000),   # before any block
        block_rec("2026-07-20T00:10:00Z"),
        assistant_rec("2026-07-20T00:10:05Z", inp=100, out=50),      # caused by the block
    ])
    g = scan_goals()[0]
    assert g["tokens"] == 150
    assert g["cost_basis"] == "attributed_turns"


def test_claude_user_reply_closes_the_attributed_span(scan_env):
    claude_session(scan_env, [
        arm_rec(),
        block_rec("2026-07-20T00:10:00Z"),
        assistant_rec("2026-07-20T00:10:05Z", inp=100, out=50),
        {"type": "user", "timestamp": "2026-07-20T00:11:00Z",
         "message": {"role": "user", "content": "actually, do something else"}},
        assistant_rec("2026-07-20T00:11:05Z", inp=7000, out=7000),   # not the goal's
    ])
    assert scan_goals()[0]["tokens"] == 150


def test_claude_armed_goal_with_no_blocks_has_no_attributed_tokens(scan_env):
    claude_session(scan_env, [arm_rec(), assistant_rec("2026-07-20T00:01:00Z")])
    assert scan_goals()[0]["tokens"] is None


# --- Grok -----------------------------------------------------------------

def write_grok(tmp_path, calls):
    d = tmp_path / "grok-session"
    d.mkdir(parents=True, exist_ok=True)
    lines = [{"type": "assistant", "tool_calls": [
        {"id": f"c{i}", "name": "update_goal", "arguments": json.dumps(a)}]}
        for i, a in enumerate(calls)]
    (d / main.GROK_CHAT_HISTORY).write_text(
        "".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
    return d


def test_grok_requires_the_tool_in_the_toolset(tmp_path):
    """Gate: "tool available" is not "tool called". Skipping this check is what
    turned 1,808 candidate files into 88 real invocations during research."""
    d = write_grok(tmp_path, [{"message": "working"}])
    assert main._grok_goal_detect(d, [], None, None) is None


def test_grok_checkpoints_are_counted(tmp_path):
    d = write_grok(tmp_path, [{"message": "step one"}, {"message": "step two"}])
    g = main._grok_goal_detect(d, ["update_goal"], "t0", "t1")
    assert g["evidence"]["checkpoints"] == 2
    assert g["evidence"]["latest_message"] == "step two"


def test_grok_completed_flag_yields_complete(tmp_path):
    d = write_grok(tmp_path, [{"message": "a"}, {"completed": True, "message": "done"}])
    g = main._grok_goal_detect(d, ["update_goal"], None, None)
    assert g["state"] == "complete"
    assert g["evidence"]["completed"] is True


def test_grok_without_completion_is_unknown_not_active(tmp_path):
    """An ended session that never reported completion is genuinely unknown;
    calling it "active" would assert something the data does not support."""
    d = write_grok(tmp_path, [{"message": "still going"}])
    assert main._grok_goal_detect(d, ["update_goal"], None, None)["state"] == "unknown"


def test_grok_objective_is_not_faked_from_a_progress_message(tmp_path):
    d = write_grok(tmp_path, [{"message": "Starting the migration"}])
    g = main._grok_goal_detect(d, ["update_goal"], None, None)
    assert g["objective"] is None
    assert g["evidence"]["objective_recoverable"] is False
    assert g["cost_basis"] == "session"
    assert g["tokens"] is None


def test_grok_missing_file_is_survivable(tmp_path):
    assert main._grok_goal_detect(tmp_path / "nope", ["update_goal"], None, None) is None


# --- Antigravity ----------------------------------------------------------

def write_ag(tmp_path, requests):
    p = tmp_path / "transcript.jsonl"
    p.write_text("".join(
        json.dumps({"role": "user",
                    "content": f"<USER_REQUEST>\n/goal {r}/goal\n</USER_REQUEST>"}) + "\n"
        for r in requests), encoding="utf-8")
    return p


def test_antigravity_marker_is_parsed(tmp_path):
    goals = main._antigravity_goal_detect(write_ag(tmp_path, ["fix the build"]))
    assert len(goals) == 1
    assert goals[0]["source"] == "antigravity"
    assert "fix the build" in goals[0]["objective"]
    assert goals[0]["state"] == "unknown"
    assert goals[0]["evidence"]["marker_only"] is True


def test_antigravity_repeated_marker_is_deduped(tmp_path):
    assert len(main._antigravity_goal_detect(
        write_ag(tmp_path, ["fix the build", "fix the build"]))) == 1


def test_antigravity_no_marker_yields_nothing(tmp_path):
    p = tmp_path / "transcript.jsonl"
    p.write_text(json.dumps({"content": "just a normal message"}) + "\n", encoding="utf-8")
    assert main._antigravity_goal_detect(p) == []


def test_antigravity_missing_file_is_survivable(tmp_path):
    assert main._antigravity_goal_detect(tmp_path / "nope.jsonl") == []


# --- cross-agent invariants -----------------------------------------------

def test_no_inferred_agent_ever_claims_native_cost(tmp_path):
    """cost_basis "native" means the agent counted the tokens itself. Only
    Codex may claim it; the rest must not, or the numbers get summed."""
    d = write_grok(tmp_path, [{"message": "x"}])
    assert main._grok_goal_detect(d, ["update_goal"], None, None)["cost_basis"] == "session"
    ag = main._antigravity_goal_detect(write_ag(tmp_path, ["y"]))
    assert ag[0]["cost_basis"] == "session"
