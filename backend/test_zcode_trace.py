"""Session-detail (trace) + delegation endpoint tests for agent="zcode"."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import main  # noqa: E402
from test_zcode_scan import _mk_zcode_db, _step_finish  # noqa: E402


def _seed_trace_db(db: Path):
    _mk_zcode_db(db, sessions=[{
        "id": "sess_t", "directory": "D:\\p", "title": "T",
        "messages": [
            ({"role": "user"}, 1000),
            ({"role": "assistant", "modelID": "GLM-5.3-Flash"}, 1100),
        ],
        "parts": [
            ({"type": "text", "text": "hello"}, 1000),
            ({"type": "reasoning", "text": "thinking...", "_mid": "sess_t-m1"}, 1050),
            ({"type": "tool", "tool": "Read", "callID": "c9", "state": {},
              "_mid": "sess_t-m1"}, 1100),
            (_step_finish(10, 5, 0), 1150),
            ({"type": "text", "text": "hi!", "_mid": "sess_t-m1"}, 1200),
        ],
    }])


def test_zcode_detail_events_match_opencode_contract(tmp_path, monkeypatch):
    db = tmp_path / "db.sqlite"
    _seed_trace_db(db)
    monkeypatch.setattr(main, "_zcode_dbs", lambda: [db])
    result = asyncio.run(main.get_session_detail("sess_t", "zcode"))
    kinds = [e["type"] for e in result]
    assert kinds == ["user", "assistant_thinking", "tool_call", "assistant"]
    # step-finish is not an event; its tokens attach to the last prior event.
    assert result[2]["payload"]["tool"] == "Read"
    assert result[2]["tokens"]["input"] == 10
    assert result[3]["payload"]["content"] == "hi!"


def test_zcode_detail_missing_session(tmp_path, monkeypatch):
    db = tmp_path / "db.sqlite"
    _seed_trace_db(db)
    monkeypatch.setattr(main, "_zcode_dbs", lambda: [db])
    assert asyncio.run(main.get_session_detail("nope", "zcode")) == {"error": "Not found"}


def test_zcode_delegation_endpoint(tmp_path, monkeypatch):
    db = tmp_path / "db.sqlite"
    _mk_zcode_db(db, sessions=[
        {"id": "p", "directory": "D:\\p", "title": "P"},
        {"id": "c1", "directory": "D:\\p", "title": "C1", "parent_id": "p"},
        {"id": "c2", "directory": "D:\\p", "title": "C2", "parent_id": "p"},
    ])
    monkeypatch.setattr(main, "_zcode_dbs", lambda: [db])
    result = asyncio.run(main.session_delegation("p", "zcode"))
    assert result == {"supported": True, "tokens_recorded": False,
                      "parent_session_id": None,
                      "child_session_ids": ["c1", "c2"], "linked_children": 2}
