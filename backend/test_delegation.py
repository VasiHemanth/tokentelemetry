"""Tests for delegation telemetry (subagent attribution) — see DESIGN.md.

Covers:
  - _claude_subagent_usage(): rollup of <sid>/subagents/agent-*.jsonl with
    model-correct per-file costing, meta.json fallbacks, tolerant parsing.
  - _scan_sessions_sync() wiring: delegation summary on claude/cursor sessions,
    parent/child markers for opencode/hermes, count-once invariant (parent
    token fields never absorb delegated usage).
  - /sessions/{id}/delegation overlay endpoint.

Run: pytest backend/test_delegation.py
"""
import asyncio
import json
import os
import sqlite3
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import main  # noqa: E402

SID = "11111111-2222-3333-4444-555555555555"
PROJ = "-tmp-proj"


def _jl(**kw) -> str:
    return json.dumps(kw) + "\n"


def _assistant_line(model="claude-opus-4-8", inp=0, out=0, cache_read=0,
                    cache_creation=0, cache_creation_1h=0, attribution=None,
                    content=None):
    usage = {
        "input_tokens": inp, "output_tokens": out,
        "cache_read_input_tokens": cache_read,
        "cache_creation_input_tokens": cache_creation,
        "cache_creation": {"ephemeral_1h_input_tokens": cache_creation_1h},
    }
    line = {"type": "assistant", "message": {"model": model, "usage": usage, "content": content or []}}
    if attribution:
        line["attributionAgent"] = attribution
    return json.dumps(line) + "\n"


def _tool_use(name, **input_kw):
    return {"type": "tool_use", "name": name, "id": "toolu_x", "input": input_kw}


def make_claude_tree(claude_dir: Path, sid: str = SID, with_subagents: bool = True) -> Path:
    """Parent session + (optionally) three subagents exercising the edge cases."""
    proj = claude_dir / "projects" / PROJ
    proj.mkdir(parents=True, exist_ok=True)
    session_file = proj / f"{sid}.jsonl"
    session_file.write_text(
        _jl(type="user", cwd="/tmp/proj", message={"role": "user", "content": "hi"})
        + _assistant_line(inp=100, out=50, cache_read=1000, cache_creation=200,
                          content=[_tool_use("Bash"), _tool_use("Bash"),
                                   _tool_use("mcp__chrome__navigate"),
                                   _tool_use("mcp__chrome__navigate"),
                                   _tool_use("mcp__chrome__navigate"),
                                   _tool_use("Skill", skill="graphify"),
                                   _tool_use("Skill", skill="graphify")])
        # Slash-command echoes: a real skill (counted) and a built-in (filtered).
        + _jl(type="user", message={"role": "user", "content":
              "<command-name>/code-review</command-name><command-args>high</command-args>"})
        + _jl(type="user", message={"role": "user", "content":
              "<command-name>/model</command-name>"}),
        encoding="utf-8",
    )
    if not with_subagents:
        return session_file
    sub = proj / sid / "subagents"
    sub.mkdir(parents=True)
    # 1) Happy path: meta.json present, Haiku model, cache hwm across two calls,
    #    a <synthetic> line and a truncated trailing line (agent still running).
    (sub / "agent-one.meta.json").write_text(json.dumps(
        {"agentType": "Explore", "description": "look around", "toolUseId": "toolu_1"}))
    (sub / "agent-one.jsonl").write_text(
        _assistant_line(model="claude-haiku-4-5-20251001", inp=10, out=5,
                        cache_read=100, cache_creation=50)
        + _assistant_line(model="claude-haiku-4-5-20251001", inp=20, out=5,
                          cache_read=300, cache_creation=50)
        + _jl(type="assistant", message={"model": "<synthetic>", "content": []})
        + '{"type": "assistant", "message": {"usage": {"input_tok',  # mid-write
        encoding="utf-8",
    )
    # 2) meta.json MISSING → agent_type from attributionAgent on the lines.
    (sub / "agent-two.jsonl").write_text(
        _assistant_line(model="claude-sonnet-4-6", inp=7, out=3, cache_read=40,
                        attribution="general-purpose"),
        encoding="utf-8",
    )
    # 3) meta.json corrupt, no attributionAgent → "unknown".
    (sub / "agent-three.meta.json").write_text("not json at all {")
    (sub / "agent-three.jsonl").write_text(
        _assistant_line(model="claude-opus-4-8", inp=1, out=2),
        encoding="utf-8",
    )
    return session_file


# --- helper unit tests ------------------------------------------------------

def test_sqlite_ro_uri_cross_platform():
    from pathlib import PurePosixPath, PureWindowsPath
    # POSIX: byte-identical to the old f"file:{path}?mode=ro" for plain paths.
    assert main._sqlite_ro_uri(PurePosixPath("/home/u/.hermes/state.db")) == \
        "file:/home/u/.hermes/state.db?mode=ro"
    # Windows: backslashes are NOT URI separators — must be forward-slashed,
    # drive colon kept literal (sqlite's Windows URI parser expects C:/...).
    assert main._sqlite_ro_uri(PureWindowsPath(r"C:\Users\u\state.db")) == \
        "file:C:/Users/u/state.db?mode=ro"
    # URI-special characters get percent-encoded (spaces, '?', '#').
    assert main._sqlite_ro_uri(PurePosixPath("/data/My Files/a?b.db")) == \
        "file:/data/My%20Files/a%3Fb.db?mode=ro"

def test_helper_none_without_subagents(tmp_path):
    sf = make_claude_tree(tmp_path / ".claude", with_subagents=False)
    assert main._claude_subagent_usage(sf, SID) is None


def test_helper_none_with_empty_dir(tmp_path):
    sf = make_claude_tree(tmp_path / ".claude", with_subagents=False)
    (sf.parent / SID / "subagents").mkdir(parents=True)
    assert main._claude_subagent_usage(sf, SID) is None


def test_helper_rollup(tmp_path):
    sf = make_claude_tree(tmp_path / ".claude")
    deleg = main._claude_subagent_usage(sf, SID)
    assert deleg["spawn_count"] == 3
    by_id = {e["agent_id"]: e for e in deleg["subagents"]}
    one = by_id["one"]
    assert one["agent_type"] == "Explore"
    assert one["description"] == "look around"
    assert one["tool_use_id"] == "toolu_1"
    assert one["model"] == "claude-haiku-4-5-20251001"
    # input/output cumulative; cached = high-water-mark (NOT 100+300);
    # cache_creation cumulative. Synthetic + truncated lines ignored.
    assert one["tokens"]["input"] == 30
    assert one["tokens"]["output"] == 10
    assert one["tokens"]["cached"] == 300
    assert one["tokens"]["cache_creation"] == 100
    assert one["tokens"]["total"] == 30 + 10 + 300
    # meta fallbacks
    assert by_id["two"]["agent_type"] == "general-purpose"
    assert by_id["three"]["agent_type"] == "unknown"
    # totals sum across entries
    assert deleg["totals"]["input"] == 30 + 7 + 1
    assert deleg["totals"]["output"] == 10 + 3 + 2
    assert deleg["totals"]["cached"] == 300 + 40 + 0
    assert deleg["cost"] >= 0


def test_helper_costs_with_each_files_own_model(tmp_path, monkeypatch):
    sf = make_claude_tree(tmp_path / ".claude")
    seen = []

    def fake_cost(model, inp, out, cached, **kw):
        seen.append(model)
        return 1.0

    monkeypatch.setattr(main, "calculate_cost", fake_cost)
    deleg = main._claude_subagent_usage(sf, SID)
    assert sorted(seen) == ["claude-haiku-4-5-20251001", "claude-opus-4-8",
                            "claude-sonnet-4-6"]
    assert deleg["cost"] == pytest.approx(3.0)


# --- scanner integration ----------------------------------------------------

@pytest.fixture
def scan_env(tmp_path, monkeypatch):
    """Point every agent store at tmp_path so the scan is hermetic."""
    missing = tmp_path / "missing"
    for attr in ("CODEX_DIR", "GEMINI_DIR", "QWEN_DIR", "VIBE_DIR", "OLLAMA_DIR",
                 "GROK_SESSIONS_DIR", "VSCODE_STORAGE", "CURSOR_STORAGE",
                 "COPILOT_CLI_DIR", "ANTIGRAVITY_BRAIN_DIR", "ANTIGRAVITY_CLI_DIR",
                 "HERMES_DIR"):
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
    return tmp_path


def test_scan_claude_delegation_summary(scan_env):
    make_claude_tree(scan_env / ".claude")
    sessions = [s for s in main._scan_sessions_sync() if s["agent"] == "claude"]
    assert len(sessions) == 1
    s = sessions[0]
    d = s["delegation"]
    assert d["supported"] is True and d["tokens_recorded"] is True
    assert d["spawn_count"] == 3
    assert d["delegated_total"] == (30 + 7 + 1) + (10 + 3 + 2) + (300 + 40)
    # Per-type rollup for analytics: Explore file = 30+10+300 tokens.
    assert d["by_type"]["Explore"] == {"count": 1, "total": 340,
                                       "cost": d["by_type"]["Explore"]["cost"]}
    assert set(d["by_type"]) == {"Explore", "general-purpose", "unknown"}
    assert s["tokens"]["delegated_input"] == 38
    assert s["tokens"]["delegated_output"] == 15
    assert s["tokens"]["delegated_cached"] == 340
    assert s["tokens"]["delegated_cache_creation"] == 100
    assert s["delegated_cost"] >= 0
    # Count-once invariant: the parent's own buckets reflect ONLY the parent file.
    assert s["tokens"]["input"] == 100
    assert s["tokens"]["output"] == 50
    assert s["tokens"]["cached"] == 1000
    assert s["tokens"]["total"] == 100 + 50 + 1000


def test_scan_claude_without_spawns(scan_env):
    make_claude_tree(scan_env / ".claude", with_subagents=False)
    s = [s for s in main._scan_sessions_sync() if s["agent"] == "claude"][0]
    assert s["delegation"]["supported"] is True
    assert s["delegation"]["spawn_count"] == 0
    assert "delegated_input" not in s["tokens"]
    assert "delegated_cost" not in s


def test_scan_cursor_spawn_count_only(scan_env):
    sid = str(uuid.uuid4())
    trans = scan_env / ".cursor" / "projects" / "tmp-proj" / "agent-transcripts" / sid
    trans.mkdir(parents=True)
    (trans / f"{sid}.jsonl").write_text(
        json.dumps({"role": "user", "message": {"content": "do things"}}) + "\n"
        + json.dumps({"role": "assistant", "message": {
            "model": "claude-opus-4-8",
            "usage": {"input_tokens": 9, "output_tokens": 4},
            "content": []}}) + "\n",
        encoding="utf-8",
    )
    subs = trans / "subagents"
    subs.mkdir()
    for _ in range(2):
        # Cursor subagent transcripts carry NO usage fields — count only.
        (subs / f"{uuid.uuid4()}.jsonl").write_text(
            json.dumps({"role": "assistant", "message": {"content": "text"}}) + "\n")
    s = [s for s in main._scan_sessions_sync() if s["agent"] == "cursor"][0]
    assert s["delegation"] == {"supported": True, "tokens_recorded": False,
                               "spawn_count": 2}
    # No invented tokens for cursor spawns.
    assert s["tokens"]["input"] == 9
    assert "delegated_input" not in s["tokens"]


def _make_opencode_db(path: Path):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE session (id TEXT, project_id TEXT, parent_id TEXT, "
                "directory TEXT, title TEXT, time_created INT, time_updated INT)")
    con.execute("CREATE TABLE message (session_id TEXT, time_created INT, data TEXT)")
    con.execute("CREATE TABLE part (session_id TEXT, time_created INT, data TEXT)")
    con.execute("CREATE TABLE todo (session_id TEXT, position INT, content TEXT, status TEXT)")
    now = 1750000000000
    con.execute("INSERT INTO session VALUES ('ses_parent', 'p', NULL, '/tmp/x', 'parent', ?, ?)", (now, now))
    con.execute("INSERT INTO session VALUES ('ses_child', 'p', 'ses_parent', '/tmp/x', 'child', ?, ?)", (now, now))
    for sid in ("ses_parent", "ses_child"):
        con.execute("INSERT INTO message VALUES (?, ?, ?)", (sid, now, json.dumps(
            {"role": "assistant", "modelID": "gpt-5.2-codex", "providerID": "openai"})))
        con.execute("INSERT INTO part VALUES (?, ?, ?)", (sid, now, json.dumps(
            {"type": "step-finish", "tokens": {"input": 11, "output": 6, "cache": {"read": 0, "write": 0}}})))
    con.commit()
    con.close()


def test_scan_opencode_hierarchy(scan_env):
    _make_opencode_db(scan_env / "opencode.db")
    by_id = {s["id"]: s for s in main._scan_sessions_sync() if s["agent"] == "opencode"}
    assert by_id["ses_child"]["parent_session_id"] == "ses_parent"
    assert by_id["ses_parent"]["child_session_ids"] == ["ses_child"]
    assert by_id["ses_parent"]["delegation"] == {"supported": True,
                                                 "tokens_recorded": False,
                                                 "linked_children": 1}
    # Children are full sessions (already counted) — child keeps its own tokens,
    # parent's buckets are NOT inflated.
    assert by_id["ses_child"]["tokens"]["input"] == 11
    assert by_id["ses_parent"]["tokens"]["input"] == 11
    # Child without children of its own: capability marker, no linked_children.
    assert by_id["ses_child"]["delegation"] == {"supported": True}


def _make_hermes_db(path: Path):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE sessions (id TEXT, source TEXT, model TEXT, "
                "parent_session_id TEXT, started_at INT, ended_at INT, "
                "input_tokens INT, output_tokens INT, cache_read_tokens INT, "
                "cache_write_tokens INT, reasoning_tokens INT, "
                "estimated_cost_usd REAL, actual_cost_usd REAL, title TEXT, "
                "billing_provider TEXT, billing_base_url TEXT, end_reason TEXT)")
    con.execute("CREATE TABLE messages (session_id TEXT, role TEXT, content TEXT, "
                "timestamp INT, tool_name TEXT)")
    con.execute("INSERT INTO sessions VALUES ('h_parent', 'cli', 'claude-sonnet-4-6', NULL, "
                "1750000000, 1750000100, 100, 40, 0, 0, 0, 0.01, 0.01, 'parent', "
                "'anthropic', NULL, 'done')")
    con.execute("INSERT INTO sessions VALUES ('h_child', 'cli', 'claude-sonnet-4-6', 'h_parent', "
                "1750000010, 1750000090, 50, 20, 0, 0, 0, 0.005, 0.005, 'child', "
                "'anthropic', NULL, 'done')")
    con.commit()
    con.close()


def test_scan_hermes_hierarchy(scan_env):
    _make_hermes_db(scan_env / "hermes-state.db")
    by_id = {s["id"]: s for s in main._scan_sessions_sync() if s["agent"] == "hermes"}
    assert by_id["h_child"]["parent_session_id"] == "h_parent"
    assert by_id["h_parent"]["child_session_ids"] == ["h_child"]
    assert by_id["h_parent"]["delegation"]["linked_children"] == 1
    assert by_id["h_child"]["delegation"] == {"supported": True}


# --- skills + MCP usage (Phase 2) -------------------------------------------

def test_mcp_usage_from_counts_parses_and_skips_malformed():
    out = main._mcp_usage_from_counts({
        "mcp__chrome__navigate": 3,
        "mcp__chrome__read_page": 1,
        "mcp__jira__search": 2,
        "Bash": 9,             # not MCP
        "mcp__": 1,            # malformed
        "mcp__only-server": 1, # malformed (no tool)
    })
    assert out == {"chrome": {"navigate": 3, "read_page": 1},
                   "jira": {"search": 2}}


def test_mcp_usage_gemini_single_underscore_convention():
    # Real names observed in ~/.gemini chats: servers may contain dashes,
    # tools contain underscores, and some calls carry a default_api: wrapper.
    out = main._mcp_usage_from_counts({
        "mcp_computerUse_execute_action": 10,
        "mcp_local-server_take_snapshot": 9,
        "default_api:mcp_local-server_fill": 36,
        "mcp_blender_execute_blender_code": 8,
        "mcp_github_get_file_contents": 7,
        "run_shell_command": 500,  # not MCP
        "mcp_orphan": 1,           # malformed (no tool part)
    })
    assert out == {
        "computerUse": {"execute_action": 10},
        "local-server": {"take_snapshot": 9, "fill": 36},
        "blender": {"execute_blender_code": 8},
        "github": {"get_file_contents": 7},
    }


def test_scan_claude_skills_and_mcp(scan_env):
    make_claude_tree(scan_env / ".claude")
    s = [s for s in main._scan_sessions_sync() if s["agent"] == "claude"][0]
    # Skill tool ×2 + /code-review echo; /model is a built-in CLI command → filtered.
    assert s["skills_used"] == [{"name": "graphify", "count": 2},
                                {"name": "code-review", "count": 1}]
    assert s["tool_counts"]["Bash"] == 2
    assert s["tool_counts"]["mcp__chrome__navigate"] == 3
    assert s["tool_counts"]["Skill"] == 2
    assert s["mcp_usage"] == {"chrome": {"navigate": 3}}


def test_scan_agents_without_signal_lack_keys(scan_env):
    make_claude_tree(scan_env / ".claude", with_subagents=False)
    _make_hermes_db(scan_env / "hermes-state.db")
    for s in main._scan_sessions_sync():
        if s["agent"] == "hermes":
            # fixture has no tool messages → no invented usage keys
            assert "mcp_usage" not in s and "tool_counts" not in s


# --- /analytics ecosystem aggregates -----------------------------------------

def test_analytics_ecosystem_aggregates(monkeypatch):
    from datetime import datetime, timezone
    base = {"project": "/tmp/x", "timestamp": datetime.now(timezone.utc),
            "tokens": {"input": 10, "output": 5, "cached": 0, "total": 15},
            "cost": 0.01, "model": "claude-opus-4-8", "mcp_tools": []}
    sessions = [
        {**base, "id": "a", "agent": "claude",
         "skills_used": [{"name": "graphify", "count": 2}],
         "mcp_usage": {"chrome": {"navigate": 3}},
         "delegation": {"supported": True, "tokens_recorded": True, "spawn_count": 2,
                        "delegated_total": 500,
                        "by_type": {"Explore": {"count": 2, "total": 500, "cost": 0.2}}},
         "delegated_cost": 0.2},
        {**base, "id": "b", "agent": "claude",
         "skills_used": [{"name": "graphify", "count": 1}],
         "mcp_usage": {"chrome": {"navigate": 1, "find": 2}},
         "delegation": {"supported": True, "tokens_recorded": True, "spawn_count": 0,
                        "delegated_total": 0}},
        # grok: parent's by_type points at the child SESSION, whose tokens are
        # already in totals — attribution only.
        {**base, "id": "gp", "agent": "grok",
         "delegation": {"supported": True, "tokens_recorded": False, "spawn_count": 1,
                        "by_type": {"general-purpose": {"count": 1, "child_session_ids": ["gc"]}}},
         "child_session_ids": ["gc"]},
        {**base, "id": "gc", "agent": "grok", "parent_session_id": "gp",
         "tokens": {"input": 100, "output": 0, "cached": 0, "total": 100}, "cost": 0.05},
        # codex: the child carries its own role.
        {**base, "id": "cp", "agent": "codex",
         "delegation": {"supported": True, "tokens_recorded": False, "linked_children": 1}},
        {**base, "id": "cc", "agent": "codex", "parent_session_id": "cp",
         "subagent_info": {"role": "explorer", "nickname": "Dewey", "depth": 1},
         "tokens": {"input": 60, "output": 10, "cached": 0, "total": 70}, "cost": 0.01},
    ]

    async def fake_sessions(fresh: bool = False):
        return sessions

    monkeypatch.setattr(main, "get_sessions_cached", fake_sessions)
    a = _run(main.get_analytics())
    assert a["by_skill"] == {"graphify": {"invocations": 3, "session_count": 2,
                                          "agents": ["claude"]}}
    assert a["by_mcp_server"] == {"chrome": {"calls": 6, "session_count": 2,
                                             "tools": {"navigate": 4, "find": 2},
                                             "agents": ["claude"]}}
    assert a["by_subagent_type"]["Explore"] == {
        "spawns": 2, "tokens": 500, "cost": 0.2, "session_count": 1,
        "tokens_recorded": True, "agents": ["claude"]}
    # grok type rows attribute the child session's tokens.
    assert a["by_subagent_type"]["general-purpose"]["tokens"] == 100
    assert a["by_subagent_type"]["general-purpose"]["agents"] == ["grok"]
    # codex children aggregate by role with their own session tokens.
    assert a["by_subagent_type"]["explorer"]["spawns"] == 1
    assert a["by_subagent_type"]["explorer"]["tokens"] == 70
    d = a["delegation"]
    assert d["delegated_tokens"] == 500 and d["delegated_cost"] == 0.2
    assert d["sessions_with_spawns"] == 3          # claude a + grok gp + codex cp
    assert d["linked_children"] == 2 and d["linked_child_tokens"] == 170
    assert d["by_agent"]["grok"] == {"parents": 1, "spawns": 1, "children": 1,
                                     "child_tokens": 100, "child_cost": 0.05,
                                     "delegated_tokens": 0, "delegated_cost": 0.0}
    # Existing aggregates unchanged in shape: delegated usage NOT folded in,
    # children counted once as their own sessions.
    assert a["by_agent"]["claude"]["total"] == 30
    assert a["total"]["total"] == 30 + 15 + 100 + 15 + 70


# --- grok / codex / antigravity (probe-verified shapes) ----------------------

GROK_PARENT = "019eb056-455f-7442-bf79-000000000001"
GROK_CHILD = "019eb056-646a-7a03-b3f7-000000000002"


def _make_grok_tree(root: Path):
    """Bucket with a parent session that spawned one subagent (child is a full
    sibling session dir) — mirrors grok 0.2.39 on-disk layout."""
    bucket = root / "%2Ftmp%2Fx"
    for sid, ctx in ((GROK_PARENT, 200), (GROK_CHILD, 100)):
        d = bucket / sid
        d.mkdir(parents=True)
        (d / "summary.json").write_text(json.dumps({
            "created_at": "2026-06-10T07:00:00Z", "updated_at": "2026-06-10T07:01:00Z",
            "generated_title": f"sess {sid[:6]}", "current_model_id": "grok-build",
            "info": {"cwd": "/tmp/x"}}))
        (d / "signals.json").write_text(json.dumps({
            "contextTokensUsed": ctx, "toolsUsed": ["read_file"],
            "modelsUsed": ["grok-build"]}))
    sub = bucket / GROK_PARENT / "subagents" / GROK_CHILD
    sub.mkdir(parents=True)
    (sub / "meta.json").write_text(json.dumps({
        "subagent_id": GROK_CHILD, "parent_session_id": GROK_PARENT,
        "child_session_id": GROK_CHILD, "subagent_type": "general-purpose",
        "description": "Summarize README", "status": "completed",
        "duration_ms": 5898, "tool_calls": 1, "turns": 1,
        "effective_model_id": "grok-build"}))


def test_scan_grok_delegation(scan_env, monkeypatch):
    monkeypatch.setattr(main, "GROK_SESSIONS_DIR", scan_env / "grok-sessions")
    _make_grok_tree(scan_env / "grok-sessions")
    by_id = {s["id"]: s for s in main._scan_sessions_sync() if s["agent"] == "grok"}
    assert by_id[GROK_PARENT]["delegation"] == {
        "supported": True, "tokens_recorded": False, "spawn_count": 1,
        "by_type": {"general-purpose": {"count": 1, "child_session_ids": [GROK_CHILD]}}}
    assert by_id[GROK_PARENT]["child_session_ids"] == [GROK_CHILD]
    assert by_id[GROK_CHILD]["parent_session_id"] == GROK_PARENT
    # Children stand alone token-wise (count-once).
    assert by_id[GROK_CHILD]["tokens"]["total"] == 100
    assert by_id[GROK_PARENT]["tokens"]["total"] == 200


def test_endpoint_grok(scan_env, monkeypatch):
    monkeypatch.setattr(main, "GROK_SESSIONS_DIR", scan_env / "grok-sessions")
    _make_grok_tree(scan_env / "grok-sessions")
    r = _run(main.session_delegation(GROK_PARENT, "grok"))
    assert r["spawn_count"] == 1
    assert r["subagents"][0]["description"] == "Summarize README"
    assert r["subagents"][0]["child_session_id"] == GROK_CHILD
    # Child resolves its parent via the parent's spawn meta.
    r = _run(main.session_delegation(GROK_CHILD, "grok"))
    assert r["parent_session_id"] == GROK_PARENT and r["spawn_count"] == 0


CODEX_PARENT = "019eb056-4eae-7280-8617-000000000001"
CODEX_CHILD = "019eb056-83a6-7fe0-99ce-000000000002"


def _make_codex_tree(codex_dir: Path):
    """Two rollouts, NO session_index.jsonl (codex stopped maintaining it):
    parent (thread_source user) + subagent child with thread_spawn meta."""
    day = codex_dir / "sessions" / "2026" / "06" / "10"
    day.mkdir(parents=True)

    def meta(sid, extra):
        return json.dumps({"timestamp": "2026-06-10T07:01:46.921Z", "type": "session_meta",
                           "payload": {"id": sid, "timestamp": "2026-06-10T07:01:46.798Z",
                                       "cwd": "/tmp/x", "model_provider": "openai",
                                       "cli_version": "0.136.0", **extra}}) + "\n"

    usage = json.dumps({"timestamp": "2026-06-10T07:01:50.000Z", "type": "event_msg",
                        "payload": {"type": "token_count",
                                    "info": {"total_token_usage": {"input_tokens": 50,
                                             "cached_input_tokens": 0, "output_tokens": 20,
                                             "total_tokens": 70}}}}) + "\n"
    prompt = json.dumps({"timestamp": "2026-06-10T07:01:47.000Z", "type": "event_msg",
                         "payload": {"type": "user_message", "message": "probe prompt"}}) + "\n"
    # Skill activation breadcrumb: codex reads the SKILL.md via a tool call
    # (it records no structured skill event — verified on 0.136).
    skill_read = json.dumps({"timestamp": "2026-06-10T07:01:48.000Z", "type": "response_item",
                             "payload": {"type": "function_call", "name": "exec_command",
                                         "arguments": json.dumps({"cmd": [
                                             "cat", "/Users/u/.codex/skills/tt-probe-skill/SKILL.md"]})}}) + "\n"
    (day / f"rollout-2026-06-10T12-31-46-{CODEX_PARENT}.jsonl").write_text(
        meta(CODEX_PARENT, {"thread_source": "user", "source": "exec"}) + prompt + skill_read + usage)
    (day / f"rollout-2026-06-10T12-32-00-{CODEX_CHILD}.jsonl").write_text(
        meta(CODEX_CHILD, {"thread_source": "subagent",
                           "forked_from_id": CODEX_PARENT,
                           "source": {"subagent": {"thread_spawn": {
                               "parent_thread_id": CODEX_PARENT, "depth": 1,
                               "agent_nickname": "Dewey", "agent_role": "explorer"}}}})
        + usage)


def test_scan_codex_discovery_and_linkage(scan_env, monkeypatch):
    codex_dir = scan_env / ".codex"
    monkeypatch.setattr(main, "CODEX_DIR", codex_dir)
    _make_codex_tree(codex_dir)
    by_id = {s["id"]: s for s in main._scan_sessions_sync() if s["agent"] == "codex"}
    # Discovered from rollout files alone — no session_index.jsonl exists.
    assert set(by_id) == {CODEX_PARENT, CODEX_CHILD}
    assert by_id[CODEX_PARENT]["text"] == "probe prompt"
    assert by_id[CODEX_CHILD]["parent_session_id"] == CODEX_PARENT
    assert by_id[CODEX_CHILD]["subagent_info"] == {"role": "explorer",
                                                   "nickname": "Dewey", "depth": 1}
    assert by_id[CODEX_PARENT]["delegation"] == {"supported": True,
                                                 "tokens_recorded": False,
                                                 "linked_children": 1}
    # Skill use recovered from the SKILL.md read breadcrumb.
    assert by_id[CODEX_PARENT]["skills_used"] == [{"name": "tt-probe-skill", "count": 1}]
    # Each thread keeps its own tokens (count-once).
    assert by_id[CODEX_PARENT]["tokens"]["total"] == 70
    assert by_id[CODEX_CHILD]["tokens"]["total"] == 70


def test_endpoint_codex(scan_env, monkeypatch):
    codex_dir = scan_env / ".codex"
    monkeypatch.setattr(main, "CODEX_DIR", codex_dir)
    _make_codex_tree(codex_dir)
    r = _run(main.session_delegation(CODEX_PARENT, "codex"))
    assert r["child_session_ids"] == [CODEX_CHILD]
    assert r["subagents"][0]["agent_role"] == "explorer"
    r = _run(main.session_delegation(CODEX_CHILD, "codex"))
    assert r["parent_session_id"] == CODEX_PARENT
    assert r["subagent_info"]["nickname"] == "Dewey"


def test_antigravity_subagent_children(scan_env, monkeypatch):
    brain = scan_env / "brain"
    parent = "6fd942ec-d61d-4d38-a5d4-a3054d58835f"
    child = "d5361c61-c969-4f95-89b8-942bc99a4c24"
    logs = brain / parent / ".system_generated" / "logs"
    logs.mkdir(parents=True)
    # INVOKE_SUBAGENT content embeds the child id as escaped JSON (verified shape).
    (logs / "transcript.jsonl").write_text(json.dumps({
        "step_index": 6, "source": "MODEL", "type": "INVOKE_SUBAGENT",
        "content": 'Created the following subagents:\n{\n  "conversationId": "%s",\n}' % child,
    }) + "\n")
    monkeypatch.setattr(main, "ANTIGRAVITY_BRAIN_DIRS", [brain])
    assert main._antigravity_subagent_children(parent) == [child]
    # Linkage pass annotates both sides of a synthetic session list.
    sessions = [{"id": parent, "agent": "antigravity"},
                {"id": child, "agent": "antigravity"}]
    main._antigravity_link_subagents(sessions)
    assert sessions[0]["delegation"]["linked_children"] == 1
    assert sessions[1]["parent_session_id"] == parent


# --- /sessions/{id}/delegation endpoint -------------------------------------

def _run(coro):
    return asyncio.run(coro)


def test_endpoint_claude_breakdown(scan_env):
    make_claude_tree(scan_env / ".claude")
    r = _run(main.session_delegation(SID, "claude"))
    assert r["supported"] is True and r["tokens_recorded"] is True
    assert r["spawn_count"] == 3
    assert {e["agent_type"] for e in r["subagents"]} == {"Explore", "general-purpose", "unknown"}


def test_endpoint_claude_no_spawns(scan_env):
    make_claude_tree(scan_env / ".claude", with_subagents=False)
    r = _run(main.session_delegation(SID, "claude"))
    assert r == {"supported": True, "tokens_recorded": True, "spawn_count": 0,
                 "subagents": [], "totals": None, "cost": 0.0}


def test_endpoint_claude_missing_session(scan_env):
    assert _run(main.session_delegation("nope", "claude")) == {"error": "Not found"}


def test_endpoint_cursor(scan_env):
    sid = str(uuid.uuid4())
    trans = scan_env / ".cursor" / "projects" / "tmp-proj" / "agent-transcripts" / sid
    (trans / "subagents").mkdir(parents=True)
    (trans / "subagents" / "abc.jsonl").write_text("{}\n")
    r = _run(main.session_delegation(sid, "cursor"))
    assert r["supported"] is True and r["tokens_recorded"] is False
    assert r["spawn_count"] == 1
    assert r["subagents"][0]["tokens"] is None  # never invented


def test_endpoint_opencode(scan_env):
    _make_opencode_db(scan_env / "opencode.db")
    r = _run(main.session_delegation("ses_parent", "opencode"))
    assert r["child_session_ids"] == ["ses_child"] and r["linked_children"] == 1
    r = _run(main.session_delegation("ses_child", "opencode"))
    assert r["parent_session_id"] == "ses_parent" and r["linked_children"] == 0


def test_endpoint_hermes(scan_env):
    _make_hermes_db(scan_env / "hermes-state.db")
    r = _run(main.session_delegation("h_parent", "hermes"))
    assert r["child_session_ids"] == ["h_child"]


def test_endpoint_unsupported_agent():
    assert _run(main.session_delegation("anything", "gemini")) == {"supported": False}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
