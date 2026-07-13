"""Tests for native session scanning of Cline and SmallCode.

SmallCode traces are PROJECT-LOCAL (<project>/.smallcode/traces/<id>.json) —
see testdata/cline_smallcode/smallcode/8fadca50.json for the verified shape.
Cline writes to TWO stores: a CLI SQLite db (~/.cline/data/db/sessions.db,
verified in testdata/cline_smallcode/cline_cli/) and a VS Code extension JSON
store (globalStorage/saoudrizwan.claude-dev/state/taskHistory.json — not
installed on the machine this was written on, so that parser sticks to the
documented HistoryItem shape only).

Run: pytest backend/test_cline_smallcode.py -q
"""
import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import main  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------

def _write_smallcode_trace(root: Path, trace_id="8fadca50", prompt_tokens=8331,
                            completion_tokens=185) -> Path:
    """Write a trace matching testdata/cline_smallcode/smallcode/8fadca50.json."""
    traces_dir = root / ".smallcode" / "traces"
    traces_dir.mkdir(parents=True, exist_ok=True)
    trace = {
        "id": trace_id,
        "model": "nemotron-3-nano:4b",
        "prompt": "Fix the bug in math.py: add() should return a+b not a-b. Edit the file.",
        "startedAt": "2026-07-01T05:14:54.084Z",
        "steps": [
            {"type": "tool_call", "name": "read_file", "args": {"path": "math.py"},
             "result": "math.py (3 lines)", "durationMs": 4, "timestamp": 1782882900675},
            {"type": "tool_call", "name": "patch", "args": {"path": "math.py"},
             "result": "Patched math.py", "durationMs": 5, "timestamp": 1782882908174},
            {"type": "tool_call", "name": "read_file", "args": {"path": "math.py"},
             "result": "math.py (3 lines)", "durationMs": 1, "timestamp": 1782882925975},
        ],
        "tokens": {"prompt": prompt_tokens, "completion": completion_tokens},
        "endedAt": "2026-07-01T05:15:34.149Z",
        "durationMs": 40065,
    }
    (traces_dir / f"{trace_id}.json").write_text(json.dumps(trace), encoding="utf-8")
    return root


def _build_cline_cli_db(db_path: Path, session_id: str, *, workspace_root: str,
                         aggregate_usage=None, usage=None, total_cost=0,
                         messages_path=None, model="claude-sonnet-4-6",
                         provider="anthropic", prompt="Fix math.py so add returns a+b"):
    """Build a tmp sessions.db with the real Cline CLI schema (columns verified
    against testdata/cline_smallcode/cline_cli/sessions.db)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE sessions (session_id TEXT, started_at TEXT, ended_at TEXT, "
        "exit_code INTEGER, status TEXT, provider TEXT, model TEXT, cwd TEXT, "
        "workspace_root TEXT, prompt TEXT, metadata_json TEXT, messages_path TEXT)"
    )
    metadata = {"title": prompt, "totalCost": total_cost}
    if aggregate_usage is not None:
        metadata["aggregateUsage"] = aggregate_usage
    if usage is not None:
        metadata["usage"] = usage
    conn.execute(
        "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (session_id, "2026-07-01T05:15:01.949Z", "2026-07-01T05:15:22.428Z", 0,
         "completed", provider, model, workspace_root, workspace_root, prompt,
         json.dumps(metadata), str(messages_path) if messages_path else None),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def scan_env(tmp_path, monkeypatch):
    """Point every agent store at a nonexistent dir under tmp_path so a full
    _scan_sessions_sync() run is hermetic (mirrors test_delegation.py's
    scan_env — this module doesn't import it since it's private there)."""
    missing = tmp_path / "missing"
    for attr in ("CODEX_DIR", "GEMINI_DIR", "QWEN_DIR", "VIBE_DIR", "OLLAMA_DIR",
                 "GROK_SESSIONS_DIR", "VSCODE_STORAGE", "CURSOR_STORAGE",
                 "COPILOT_CLI_DIR", "ANTIGRAVITY_BRAIN_DIR", "ANTIGRAVITY_CLI_DIR",
                 "HERMES_DIR", "PI_SESSIONS_DIR"):
        monkeypatch.setattr(main, attr, missing / attr.lower())
    monkeypatch.setattr(main, "ANTIGRAVITY_BRAIN_SOURCES", [])
    monkeypatch.setattr(main, "ANTIGRAVITY_BRAIN_DIRS", [])
    monkeypatch.setattr(main, "_antigravity_cli_meta", lambda *a, **k: {})
    monkeypatch.setattr(main, "CLAUDE_DIR", missing / "claude")
    monkeypatch.setattr(main, "CURSOR_DIR", missing / "cursor")
    monkeypatch.setattr(main, "OPENCODE_DB", missing / "opencode.db")
    monkeypatch.setattr(main, "HERMES_DB", missing / "hermes-state.db")
    monkeypatch.setattr(main, "HERMES_PROFILES_DIR", missing / "hermes-profiles")
    monkeypatch.setattr(main, "PROJECT_ALIASES_FILE", tmp_path / "aliases.json")
    monkeypatch.setattr(main, "CLINE_DIR", missing / "cline")
    monkeypatch.setattr(main, "CLINE_VSCODE_DIR", missing / "cline-vscode")
    monkeypatch.setattr(main, "SMALLCODE_EXTRA_ROOTS", [])
    return tmp_path


# ---------------------------------------------------------------------------
# SmallCode
# ---------------------------------------------------------------------------

def test_split_roots_env_pathsep_and_comma():
    value = f"/a/b{os.pathsep}/c/d,/e/f"
    assert main._split_roots_env(value) == ["/a/b", "/c/d", "/e/f"]
    assert main._split_roots_env(None) == []
    assert main._split_roots_env("") == []


def test_scan_smallcode_sessions_maps_fields(tmp_path):
    root = _write_smallcode_trace(tmp_path / "proj")
    out = main._scan_smallcode_sessions([str(root)])
    assert len(out) == 1
    rec = out[0]
    assert rec["agent"] == "smallcode"
    assert rec["id"] == "8fadca50"
    assert rec["project"] == str(root)
    assert rec["model"] == "nemotron-3-nano:4b"
    assert rec["tokens"]["input"] == 8331
    assert rec["tokens"]["output"] == 185
    assert rec["tokens"]["cached"] == 0
    assert rec["tokens"]["total"] == 8331 + 185
    assert rec["display"].startswith("Fix the bug in math.py")
    assert set(rec["mcp_tools"]) == {"read_file", "patch"}
    assert rec["artifacts"][0]["path"].endswith("8fadca50.json")
    assert rec["cost"] == rec["tokens"]["cost"]
    assert rec["has_plan"] is False
    assert rec["plans"] == []


def test_scan_smallcode_sessions_skips_missing_and_nonproject_roots(tmp_path):
    missing = tmp_path / "does-not-exist"
    assert main._scan_smallcode_sessions([str(missing), "unknown", ""]) == []


def test_smallcode_reuses_known_project_roots(scan_env, monkeypatch):
    """SmallCode has no home-dir store; the scanner must discover roots from
    projects other agents already ran in (union'd with the extra-roots env)."""
    proj = scan_env / "cli-proj"
    _write_smallcode_trace(proj, trace_id="reuse-1")

    cline_dir = scan_env / ".cline"
    monkeypatch.setattr(main, "CLINE_DIR", cline_dir)
    db = cline_dir / "data" / "db" / "sessions.db"
    _build_cline_cli_db(
        db, "cli-sess", workspace_root=str(proj),
        aggregate_usage={"inputTokens": 5, "outputTokens": 2, "cacheReadTokens": 0,
                          "cacheWriteTokens": 0, "totalCost": 0},
        total_cost=0,
    )

    sessions = main._scan_sessions_sync()
    smallcode = [s for s in sessions if s["agent"] == "smallcode"]
    assert len(smallcode) == 1
    assert smallcode[0]["id"] == "reuse-1"
    assert smallcode[0]["project"] == str(proj)


def test_smallcode_extra_roots_env(scan_env, monkeypatch):
    """TT_SMALLCODE_ROOTS (surfaced as main.SMALLCODE_EXTRA_ROOTS) must be
    scanned even when no other agent ever touched that project."""
    extra = scan_env / "extra-proj"
    _write_smallcode_trace(extra, trace_id="extra-1")
    monkeypatch.setattr(main, "SMALLCODE_EXTRA_ROOTS", [str(extra)])

    sessions = main._scan_sessions_sync()
    smallcode = [s for s in sessions if s["agent"] == "smallcode"]
    assert len(smallcode) == 1
    assert smallcode[0]["id"] == "extra-1"
    assert smallcode[0]["project"] == str(extra)


def test_session_detail_smallcode(tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    _write_smallcode_trace(proj, trace_id="detail-1")
    monkeypatch.setattr(main, "SMALLCODE_EXTRA_ROOTS", [str(proj)])
    monkeypatch.setattr(main, "_sessions_cache", {"data": None, "at": 0.0, "building": False})

    result = asyncio.run(main.get_session_detail("detail-1", "smallcode"))
    assert isinstance(result, list)
    assert result[0]["type"] == "user"
    tool_calls = [e for e in result if e["type"] == "tool_call"]
    assert len(tool_calls) == 3
    assert tool_calls[0]["payload"]["tool"] == "read_file"


# ---------------------------------------------------------------------------
# Cline — CLI SQLite store
# ---------------------------------------------------------------------------

def test_scan_cline_cli_uses_aggregate_usage(tmp_path, monkeypatch):
    cline_dir = tmp_path / ".cline"
    monkeypatch.setattr(main, "CLINE_DIR", cline_dir)
    monkeypatch.setattr(main, "CLINE_VSCODE_DIR", tmp_path / "missing-vscode")
    db = cline_dir / "data" / "db" / "sessions.db"
    _build_cline_cli_db(
        db, "sess-agg", workspace_root=str(tmp_path / "proj"),
        aggregate_usage={"inputTokens": 500, "outputTokens": 120, "cacheReadTokens": 30,
                          "cacheWriteTokens": 0, "totalCost": 0.05},
        total_cost=0.05,
    )

    out = main._scan_cline_sessions()
    assert len(out) == 1
    rec = out[0]
    assert rec["agent"] == "cline"
    assert rec["id"] == "sess-agg"
    assert rec["project"] == str(tmp_path / "proj")
    assert rec["tokens"]["input"] == 500
    assert rec["tokens"]["output"] == 120
    assert rec["tokens"]["cached"] == 30
    assert rec["tokens"]["total"] == 620
    assert rec["cost"] == pytest.approx(0.05)
    assert rec["cline"]["source"] == "cli"
    assert rec["cline"]["provider"] == "anthropic"


def test_scan_cline_cli_falls_back_to_messages_metrics(tmp_path, monkeypatch):
    """When aggregateUsage AND usage are both all-zero, sum metrics from the
    messages_path transcript instead (verified fallback shape)."""
    cline_dir = tmp_path / ".cline"
    monkeypatch.setattr(main, "CLINE_DIR", cline_dir)
    monkeypatch.setattr(main, "CLINE_VSCODE_DIR", tmp_path / "missing-vscode")

    messages_path = tmp_path / "messages" / "sess-fallback.messages.json"
    messages_path.parent.mkdir(parents=True, exist_ok=True)
    messages_path.write_text(json.dumps({
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "hi"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "ok"}],
             "metrics": {"inputTokens": 200, "outputTokens": 50, "cacheReadTokens": 10}},
            {"role": "assistant", "content": [{"type": "text", "text": "more"}],
             "metrics": {"inputTokens": 20, "outputTokens": 5, "cacheReadTokens": 0}},
        ]
    }), encoding="utf-8")

    db = cline_dir / "data" / "db" / "sessions.db"
    zero_usage = {"inputTokens": 0, "outputTokens": 0, "cacheReadTokens": 0,
                  "cacheWriteTokens": 0, "totalCost": 0}
    _build_cline_cli_db(
        db, "sess-fallback", workspace_root=str(tmp_path / "proj"),
        aggregate_usage=zero_usage, usage=zero_usage, total_cost=0,
        messages_path=messages_path,
    )

    out = main._scan_cline_sessions()
    assert len(out) == 1
    rec = out[0]
    assert rec["tokens"]["input"] == 220
    assert rec["tokens"]["output"] == 55
    assert rec["tokens"]["cached"] == 10
    # cost falls back to calculate_cost since metadata totalCost is 0.
    expected_cost = main.calculate_cost("claude-sonnet-4-6", 220, 55, 10)
    assert rec["cost"] == expected_cost


def test_session_detail_cline_cli(tmp_path, monkeypatch):
    cline_dir = tmp_path / ".cline"
    monkeypatch.setattr(main, "CLINE_DIR", cline_dir)
    monkeypatch.setattr(main, "CLINE_VSCODE_DIR", tmp_path / "missing-vscode")

    messages_path = tmp_path / "sess-detail.messages.json"
    messages_path.write_text(json.dumps({"messages": [
        {"role": "user", "content": [{"type": "text", "text": "hello"}], "ts": 1},
        {"role": "assistant", "content": [{"type": "text", "text": "hi there"}], "ts": 2},
    ]}), encoding="utf-8")

    db = cline_dir / "data" / "db" / "sessions.db"
    _build_cline_cli_db(db, "sess-detail", workspace_root=str(tmp_path / "proj"),
                         messages_path=messages_path)

    result = asyncio.run(main.get_session_detail("sess-detail", "cline"))
    assert isinstance(result, list)
    assert result[0]["type"] == "user"
    assert result[0]["payload"]["content"] == "hello"
    assert result[1]["type"] == "assistant"
    assert result[1]["payload"]["content"] == "hi there"


# ---------------------------------------------------------------------------
# Cline — VS Code extension store
# ---------------------------------------------------------------------------

def test_scan_cline_vscode_maps_and_dedupes_against_cli(tmp_path, monkeypatch):
    cline_dir = tmp_path / ".cline"
    vscode_dir = tmp_path / "vscode-cline"
    monkeypatch.setattr(main, "CLINE_DIR", cline_dir)
    monkeypatch.setattr(main, "CLINE_VSCODE_DIR", vscode_dir)

    # CLI row for id "dup-id" — must win over the VS Code row with the same id.
    db = cline_dir / "data" / "db" / "sessions.db"
    _build_cline_cli_db(
        db, "dup-id", workspace_root=str(tmp_path / "cli-proj"),
        aggregate_usage={"inputTokens": 10, "outputTokens": 5, "cacheReadTokens": 0,
                          "cacheWriteTokens": 0, "totalCost": 0.01},
        total_cost=0.01,
    )

    state_dir = vscode_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    history = [
        {"id": "vsc-task-1", "ts": 1782882901945, "task": "Refactor the parser",
         "tokensIn": 1000, "tokensOut": 300, "cacheWrites": 40, "cacheReads": 60,
         "totalCost": 0.12, "size": 4096},
        {"id": "dup-id", "ts": 1782882901945, "task": "Should be shadowed by the CLI row",
         "tokensIn": 999999, "tokensOut": 999999, "cacheWrites": 0, "cacheReads": 0,
         "totalCost": 99.0, "size": 1},
    ]
    (state_dir / "taskHistory.json").write_text(json.dumps(history), encoding="utf-8")

    out = main._scan_cline_sessions()
    by_id = {r["id"]: r for r in out}
    assert set(by_id) == {"dup-id", "vsc-task-1"}

    # CLI row wins for the duplicate id — VS Code's inflated numbers are dropped.
    assert by_id["dup-id"]["cline"]["source"] == "cli"
    assert by_id["dup-id"]["tokens"]["input"] == 10

    vsc = by_id["vsc-task-1"]
    assert vsc["agent"] == "cline"
    assert vsc["cline"]["source"] == "vscode"
    assert vsc["tokens"]["input"] == 1000
    assert vsc["tokens"]["output"] == 300
    assert vsc["tokens"]["cached"] == 60
    assert vsc["cost"] == pytest.approx(0.12)
    assert vsc["display"] == "Refactor the parser"


def _build_cline_db_with_subagents(db_path, *, parent_id, child_id,
                                   parent_usage, parent_aggregate, child_usage):
    """Cline schema WITH the subagent columns (is_subagent, parent_session_id).

    A parent that spawned a subagent: the child is its own row, and the
    parent's aggregateUsage already SUMS the child in.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE sessions (session_id TEXT, started_at TEXT, ended_at TEXT, "
        "exit_code INTEGER, status TEXT, provider TEXT, model TEXT, cwd TEXT, "
        "workspace_root TEXT, prompt TEXT, metadata_json TEXT, messages_path TEXT, "
        "is_subagent INTEGER, parent_session_id TEXT, agent_id TEXT, team_name TEXT)"
    )

    def ins(sid, is_sub, parent, usage, aggregate):
        meta = {"title": "t", "totalCost": 0, "usage": usage}
        if aggregate is not None:
            meta["aggregateUsage"] = aggregate
        conn.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (sid, "2026-07-01T05:15:01.949Z", "2026-07-01T05:15:22.428Z", 0,
             "completed", "anthropic", "claude-sonnet-4-6", "/w", "/w", "p",
             json.dumps(meta), None, is_sub, parent, "agent-x", "team-1"),
        )

    ins(parent_id, 0, None, parent_usage, parent_aggregate)
    ins(child_id, 1, parent_id, child_usage, child_usage)
    conn.commit()
    conn.close()


def test_cline_subagent_no_double_count_and_links_parent(tmp_path, monkeypatch):
    cline_dir = tmp_path / ".cline"
    db = cline_dir / "data" / "db" / "sessions.db"
    # Parent OWN usage 100/20; aggregate (parent+child) 150/30; child 50/10.
    _build_cline_db_with_subagents(
        db, parent_id="P", child_id="C",
        parent_usage={"inputTokens": 100, "outputTokens": 20, "cacheReadTokens": 0},
        parent_aggregate={"inputTokens": 150, "outputTokens": 30, "cacheReadTokens": 0},
        child_usage={"inputTokens": 50, "outputTokens": 10, "cacheReadTokens": 0},
    )
    monkeypatch.setattr(main, "CLINE_DIR", cline_dir)
    monkeypatch.setattr(main, "CLINE_VSCODE_DIR", tmp_path / "no-vscode")

    recs = {r["id"]: r for r in main._scan_cline_sessions()}
    assert set(recs) == {"P", "C"}

    # Parent billed on its OWN usage, NOT the aggregate — otherwise the child
    # (counted as its own row) would be double-counted.
    assert recs["P"]["tokens"]["input"] == 100
    assert recs["P"]["tokens"]["output"] == 20
    assert recs["P"]["cline"]["spawned_children"] is True

    # Child counted on its own usage and linked back to the parent.
    assert recs["C"]["tokens"]["input"] == 50
    assert recs["C"]["parent_session_id"] == "P"
    assert recs["C"]["is_subagent"] is True

    # Sum across the two rows equals the aggregate the parent reported (150/30).
    assert sum(r["tokens"]["input"] for r in recs.values()) == 150
    assert sum(r["tokens"]["output"] for r in recs.values()) == 30

    assert "cline" in main._DELEGATION_CAPABLE_AGENTS


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
