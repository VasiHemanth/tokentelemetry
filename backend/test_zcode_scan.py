"""Tests for ZCode (Z.ai) support: DB discovery, session scan, trace + delegation.

ZCode stores usage in an OpenCode-family SQLite DB at ~/.zcode/cli/db/db.sqlite.
Schema verified against a live ZCode install; the fixtures below reproduce the
shapes _scan_zcode_sessions consumes.
"""

import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import main  # noqa: E402
from test_delegation import scan_env  # noqa: E402,F401  (hermetic scan fixture)


def _clear_zcode_env(monkeypatch):
    monkeypatch.delenv("ZCODE_DATA_DIR", raising=False)


def _mk_zcode_db(path: Path, sessions=()):
    """Create a minimal ZCode store with the verified schema.

    Each spec: {"id", "directory", "title", "parent_id", "t0", "t1",
    "messages": [(data_dict, ts_ms), ...], "parts": [(data_dict, ts_ms), ...],
    "todos": [(content, status, position), ...]}.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(
        "CREATE TABLE session(id TEXT PRIMARY KEY, directory TEXT, title TEXT,"
        " parent_id TEXT, time_created INTEGER, time_updated INTEGER);"
        " CREATE TABLE message(id TEXT PRIMARY KEY, session_id TEXT,"
        " time_created INTEGER, data TEXT);"
        " CREATE TABLE part(id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT,"
        " time_created INTEGER, data TEXT);"
        " CREATE TABLE todo(session_id TEXT, content TEXT, status TEXT, position INTEGER);"
    )
    for i, spec in enumerate(sessions):
        conn.execute("INSERT INTO session VALUES (?,?,?,?,?,?)",
                     (spec["id"], spec.get("directory"), spec.get("title"),
                      spec.get("parent_id"), spec.get("t0", 1000 + i),
                      spec.get("t1", 2000 + i)))
        for j, (data, ts) in enumerate(spec.get("messages", [])):
            conn.execute("INSERT INTO message VALUES (?,?,?,?)",
                         (f"{spec['id']}-m{j}", spec["id"], ts, json.dumps(data)))
        for j, (data, ts) in enumerate(spec.get("parts", [])):
            conn.execute("INSERT INTO part VALUES (?,?,?,?,?)",
                         (f"{spec['id']}-p{j}", data.get("_mid", f"{spec['id']}-m0"),
                          spec["id"], ts,
                          json.dumps({k: v for k, v in data.items() if k != "_mid"})))
        for content, status, pos in spec.get("todos", []):
            conn.execute("INSERT INTO todo VALUES (?,?,?,?)",
                         (spec["id"], content, status, pos))
    conn.commit()
    conn.close()


def test_default_db_path_is_home_zcode(monkeypatch):
    _clear_zcode_env(monkeypatch)
    assert main.HOME / ".zcode" / "cli" / "db" / "db.sqlite" in main._zcode_db_candidates()


def test_env_override_replaces_root(monkeypatch):
    monkeypatch.setenv("ZCODE_DATA_DIR", "/opt/zc-data")
    assert main._zcode_db_candidates() == [Path("/opt/zc-data/cli/db/db.sqlite")]


def test_agents_lists_zcode_when_db_exists(monkeypatch, tmp_path):
    _clear_zcode_env(monkeypatch)
    db = tmp_path / "cli" / "db" / "db.sqlite"
    _mk_zcode_db(db)
    monkeypatch.setattr(main, "ZCODE_DB", db)
    assert "zcode" in main._list_available_agents()


def test_agents_omit_zcode_without_db(monkeypatch, tmp_path):
    _clear_zcode_env(monkeypatch)
    monkeypatch.setattr(main, "ZCODE_DB", tmp_path / "missing.sqlite")
    assert "zcode" not in main._list_available_agents()


def test_db_for_session_finds_owning_db(monkeypatch, tmp_path):
    db1 = tmp_path / "a" / "db.sqlite"
    db2 = tmp_path / "b" / "db.sqlite"
    _mk_zcode_db(db1, sessions=[{"id": "s1"}])
    _mk_zcode_db(db2, sessions=[{"id": "s2"}])
    monkeypatch.setattr(main, "_zcode_dbs", lambda: [db1, db2])
    assert main._zcode_db_for_session("s2") == db2
    assert main._zcode_db_for_session("missing") is None


GLM_MSG = {"role": "assistant", "modelID": "GLM-5.3-Flash",
           "providerID": "builtin:zai-start-plan"}


def _step_finish(inp, out, cache_read, cache_write=0):
    return {"type": "step-finish",
            "tokens": {"input": inp, "output": out, "reasoning": 0,
                       "cache": {"read": cache_read, "write": cache_write}}}


def _seed_full_session(db: Path):
    _mk_zcode_db(db, sessions=[{
        "id": "sess_1", "directory": "D:\proj\demo", "title": "T",
        "messages": [
            ({"role": "user"}, 1000),
            (dict(GLM_MSG), 1100),
            ({"role": "assistant", "modelID": "GLM-5.3",
              "providerID": "builtin:zai-coding-plan"}, 1200),
        ],
        "parts": [
            ({"type": "text", "text": "fix the login bug"}, 1000),
            ({"type": "tool", "tool": "Bash", "callID": "c1", "state": {}}, 1100),
            (_step_finish(33205, 5079, 26496), 1150),
            ({"type": "text", "text": "done"}, 1200),
            (_step_finish(100, 10, 0, cache_write=25), 1250),
        ],
        "todos": [("write test", "completed", 0)],
    }])


def test_scan_zcode_sessions_full_shape(scan_env, monkeypatch, tmp_path):
    db = tmp_path / "db.sqlite"
    _seed_full_session(db)
    monkeypatch.setattr(main, "ZCODE_DB", db)
    monkeypatch.setattr(main, "calculate_cost", lambda *a, **k: 0.123)
    out = main._scan_zcode_sessions()
    assert len(out) == 1
    s = out[0]
    assert s["agent"] == "zcode"
    assert s["project"] == "D:\proj\demo"
    assert s["model"] == "GLM-5.3-Flash"
    assert s["models_used"] == ["GLM-5.3-Flash", "GLM-5.3"]
    assert s["provider"] == "builtin:zai-start-plan"
    # OpenCode-parity semantics: input/output summed as-is (inclusive of
    # cache-read / reasoning), cached = high-water mark, cache writes cumulative.
    assert s["tokens"]["input"] == 33205 + 100
    assert s["tokens"]["output"] == 5079 + 10
    assert s["tokens"]["cached"] == 26496
    assert s["tokens"]["cache_creation"] == 25
    assert s["tokens"]["total"] == s["tokens"]["input"] + s["tokens"]["output"] + s["tokens"]["cached"]
    assert s["tokens"]["cost"] == 0.123
    assert s["mcp_tools"] == ["Bash"]
    assert s["has_plan"] is True
    assert "write test" in s["plans"][0]["content"]
    assert s["display"].startswith("fix the login bug")
    assert "child_session_ids" not in s


def test_scan_zcode_dedupes_shared_session_ids(scan_env, monkeypatch, tmp_path):
    db1 = tmp_path / "a" / "db.sqlite"
    db2 = tmp_path / "b" / "db.sqlite"
    _seed_full_session(db1)
    _seed_full_session(db2)
    monkeypatch.setattr(main, "_zcode_dbs", lambda: [db1, db2])
    monkeypatch.setattr(main, "calculate_cost", lambda *a, **k: 0.0)
    assert len(main._scan_zcode_sessions()) == 1


def test_scan_zcode_annotates_parent_delegation(scan_env, monkeypatch, tmp_path):
    db = tmp_path / "db.sqlite"
    _mk_zcode_db(db, sessions=[
        {"id": "parent", "directory": "D:\p", "title": "P"},
        {"id": "child", "directory": "D:\p", "title": "C", "parent_id": "parent"},
    ])
    monkeypatch.setattr(main, "ZCODE_DB", db)
    monkeypatch.setattr(main, "calculate_cost", lambda *a, **k: 0.0)
    out = {s["id"]: s for s in main._scan_zcode_sessions()}
    assert out["child"]["parent_session_id"] == "parent"
    assert out["parent"]["child_session_ids"] == ["child"]
    assert out["parent"]["delegation"] == {"supported": True, "tokens_recorded": False,
                                           "linked_children": 1}


def test_scan_zcode_survives_corrupt_db(scan_env, monkeypatch, tmp_path):
    db = tmp_path / "db.sqlite"
    _seed_full_session(db)
    garbage = tmp_path / "garbage.sqlite"
    garbage.write_text("not a db", encoding="utf-8")
    # sqlite3.connect succeeds lazily; the first execute raises DatabaseError,
    # which the scanner's per-DB except must swallow so the good DB still yields
    # its session — one corrupt store must not erase the whole agent.
    monkeypatch.setattr(main, "_zcode_dbs", lambda: [garbage, db])
    monkeypatch.setattr(main, "calculate_cost", lambda *a, **k: 0.0)
    assert len(main._scan_zcode_sessions()) == 1
