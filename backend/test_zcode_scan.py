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
                         (f"{spec['id']}-p{j}", spec["id"], data.get("_mid", f"{spec['id']}-m0"),
                          ts, json.dumps(data)))
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
