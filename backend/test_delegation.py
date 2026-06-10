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
                    cache_creation=0, cache_creation_1h=0, attribution=None):
    usage = {
        "input_tokens": inp, "output_tokens": out,
        "cache_read_input_tokens": cache_read,
        "cache_creation_input_tokens": cache_creation,
        "cache_creation": {"ephemeral_1h_input_tokens": cache_creation_1h},
    }
    line = {"type": "assistant", "message": {"model": model, "usage": usage, "content": []}}
    if attribution:
        line["attributionAgent"] = attribution
    return json.dumps(line) + "\n"


def make_claude_tree(claude_dir: Path, sid: str = SID, with_subagents: bool = True) -> Path:
    """Parent session + (optionally) three subagents exercising the edge cases."""
    proj = claude_dir / "projects" / PROJ
    proj.mkdir(parents=True, exist_ok=True)
    session_file = proj / f"{sid}.jsonl"
    session_file.write_text(
        _jl(type="user", cwd="/tmp/proj", message={"role": "user", "content": "hi"})
        + _assistant_line(inp=100, out=50, cache_read=1000, cache_creation=200),
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
    assert s["delegation"] == {"supported": True, "tokens_recorded": True,
                               "spawn_count": 3,
                               "delegated_total": (30 + 7 + 1) + (10 + 3 + 2) + (300 + 40)}
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
