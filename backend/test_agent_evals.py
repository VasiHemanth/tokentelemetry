"""Tests for always-on agent evals (agent_evals.py + history_store v5).

Synthetic fixtures: the repo has no real Grok/Claude /loop/Antigravity loop
transcripts, so loop dicts mirror the shapes main.py builds (see test_loops).
Run: pytest backend/test_agent_evals.py
"""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

import agent_evals
import history_store

UTC = timezone.utc
NOW = datetime(2026, 11, 2, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _tmp_data(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKENTELEMETRY_DATA_DIR", str(tmp_path))


def _loop_sess(agent="claude", sid="s1", **kw):
    lp = {"is_loop": True, "cadence": "0 * * * *", "cadence_seconds": 3600, "recurring": True,
          "job_id": "job1", "prompt_preview": "SECRET PROMPT TEXT",
          "created_at": (NOW - timedelta(hours=3)).isoformat(),
          "last_fired": (NOW - timedelta(minutes=50)).isoformat(),
          "iterations": 2, "cancelled": False}
    lp.update(kw)
    return {"id": sid, "agent": agent, "project": "/home/u/secret", "loop": lp}


def test_schedule_fire_drift_and_wake_stub():
    evs = agent_evals.derive_schedule_events([_loop_sess()], NOW)
    fire = next(e for e in evs if e["kind"] == "schedule_fire")
    # expected = created + 2h = NOW-1h; actual = NOW-50m -> +600s drift
    assert fire["drift_s"] == 600 and fire["missed"] is False and fire["human_present"] is False
    wake = next(e for e in evs if e["kind"] == "wake_decision")
    assert wake["decision"] == "wake" and wake["source"] == "derived"
    assert not any(e.get("missed") for e in evs)


def test_missed_fire_and_harness_filter():
    s = _loop_sess(agent="grok", last_fired=(NOW - timedelta(hours=5)).isoformat())
    evs = agent_evals.derive_schedule_events([s, _loop_sess(agent="cline")], NOW)
    assert {e["agent"] for e in evs} == {"grok"}
    assert any(e["kind"] == "schedule_fire" and e["missed"] for e in evs)


def test_cancelled_loop_never_missed():
    s = _loop_sess(cancelled=True, last_fired=(NOW - timedelta(days=2)).isoformat())
    assert not any(e.get("missed") for e in agent_evals.derive_schedule_events([s], NOW))


def test_privacy_no_prompt_or_paths():
    evs = agent_evals.derive_all([_loop_sess()], None, NOW)
    blob = repr(evs)
    assert "SECRET" not in blob and "/home/u" not in blob


def test_agent_calls_subagent_and_peer():
    sessions = [{"id": "c1", "agent": "claude", "parent_session_id": "p1",
                 "timestamp": NOW.isoformat()}]
    graph = {"edges": [{"msg_id": "m1", "from_session": "a", "to_session": None,
                        "sent_at": NOW.isoformat(), "received_at": None, "resolved": False,
                        "preview": "body text"}]}
    evs = agent_evals.derive_agent_calls(sessions, graph)
    assert [e["channel"] for e in evs] == ["subagent", "peer"]
    assert evs[1]["resolved"] is False and "preview" not in evs[1]


def test_summary_precision_recall():
    mk = lambda d, l, n: agent_evals.make_event("wake_decision", "claude", "s", NOW, "human_label",
                                                decision=d, label=l, reason=n)
    evs = [mk("wake", "should_wake", 1), mk("wake", "should_silence", 2),
           mk("silence", "should_wake", 3), mk("silence", "should_silence", 4)]
    w = agent_evals.summarize(evs)["wake"]
    assert w["precision"] == 0.5 and w["recall"] == 0.5


def test_config_default_record_only_and_persist():
    assert agent_evals.load_config() == {"evalRecordOnly": True}
    assert agent_evals.feeds_automation() is False
    agent_evals.save_config({"evalRecordOnly": False})
    assert agent_evals.feeds_automation() is True


def test_history_store_v5_migration_from_v4(tmp_path):
    db = tmp_path / "history.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE sessions (agent TEXT, id TEXT)")
    con.execute("PRAGMA user_version=4")
    con.commit(); con.close()
    evs = agent_evals.derive_schedule_events([_loop_sess()], NOW)
    assert history_store.upsert_eval_events(evs) == len(evs)
    history_store.upsert_eval_events(evs)  # idempotent
    con = sqlite3.connect(db)
    assert con.execute("PRAGMA user_version").fetchone()[0] == 5
    assert con.execute("SELECT count(*) FROM eval_events").fetchone()[0] == len(evs)
    got = history_store.query_eval_events(kind="schedule_fire", session_id="s1")
    assert len(got) == 1 and got[0]["job_id"] == "job1"
