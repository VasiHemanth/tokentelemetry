"""Route-level tests for recall v2 (settings, index, hybrid search, Ask).

Route coroutines are awaited directly (httpx's TestClient is not installed).
"""
import asyncio
import hashlib
import json
import math
import os
import re
import sys
import threading
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(__file__))
import main  # noqa: E402
import recall  # noqa: E402
import recall_index as ri  # noqa: E402


def _hash_vec(text, dims=64):
    v = [0.0] * dims
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        v[int(hashlib.md5(w.encode()).hexdigest(), 16) % dims] += 1.0
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n else v


class FakeEmbedder:
    dims = 64
    model = "fake-embed"
    gate = None  # optional threading.Event that blocks embed_documents

    def embed_documents(self, texts):
        if self.gate is not None:
            self.gate.wait(5)
        return [_hash_vec(t) for t in texts]

    def embed_query(self, text):
        return _hash_vec(text)

    def probe(self):
        return {"reachable": True, "version": "0.0.0", "model_installed": True, "error": None}


def dt(day):
    return datetime(2026, 11, day, tzinfo=timezone.utc)


def sess(agent, sid, day, project="/r/app"):
    return {"agent": agent, "id": sid, "project": project, "timestamp": dt(day),
            "display": f"prompt {sid}", "model": "m", "tokens": {"total": 1}, "cost": 1.0}


def chunk(idx, text, kind="assistant", turn=1):
    return {"idx": idx, "turn": turn, "kind": kind, "text": text}


SESSIONS = [sess("codex", "c1", 3), sess("claude", "a1", 2)]
TABLE = {
    ("codex", "c1"): [chunk(0, "we wired the planner classifier with langgraph routing")],
    ("claude", "a1"): [chunk(0, "thumbnail renderer crashed on large images")],
}


class FakeRequest:
    """Disconnects after `after` is_disconnected() calls (None = never)."""

    def __init__(self, after=None):
        self.after = after
        self.calls = 0

    async def is_disconnected(self):
        self.calls += 1
        return self.after is not None and self.calls > self.after


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(recall, "repo_resolver", None)
    monkeypatch.setattr(ri, "settings_path", lambda: tmp_path / "recall.json")
    monkeypatch.setattr(ri, "index_path", lambda: tmp_path / "recall_index.db")
    monkeypatch.setattr(main, "_recall_store", None)
    monkeypatch.setattr(main, "_recall_job", None)

    async def fake_sessions():
        return SESSIONS

    monkeypatch.setattr(main, "get_sessions_cached", fake_sessions)
    monkeypatch.setattr(main, "_recall_load_chunks",
                        lambda agent, sid: (TABLE[(agent, sid)], "live") if (agent, sid) in TABLE else None)
    emb = FakeEmbedder()
    monkeypatch.setattr(main, "_recall_embedder", lambda sem: emb)
    yield emb


def run(coro):
    return asyncio.run(coro)


def enable():
    run(main.recall_put_settings({"semantic": {"enabled": True, "default_mode": "keyword", "model": "fake-embed"}}))


def build_index(project=None):
    status = run(main.recall_index_start({"project": project}))
    main._recall_job.wait(10)
    return status


# ------------------------------------------------------------ settings

def test_settings_get_defaults_and_put_roundtrip():
    got = run(main.recall_get_settings())
    assert got["semantic"]["enabled"] is False
    assert got["semantic"]["model"] == ri.DEFAULT_MODEL
    assert got["ollama"]["reachable"] is True
    assert got["index"]["chunks"] == 0

    put = run(main.recall_put_settings({"semantic": {"enabled": True, "model": "other-embed"}}))
    assert put["semantic"]["enabled"] is True and put["semantic"]["model"] == "other-embed"
    assert run(main.recall_get_settings())["semantic"]["model"] == "other-embed"


@pytest.mark.parametrize("url", ["http://example.com:11434", "http://localhost.evil.com", "http://127.0.0.1@evil.com"])
def test_settings_put_rejects_non_loopback(url):
    with pytest.raises(HTTPException) as e:
        run(main.recall_put_settings({"semantic": {"ollama_url": url}}))
    assert e.value.status_code == 400
    assert run(main.recall_get_settings())["semantic"]["ollama_url"] == ri.DEFAULT_URL


def test_settings_put_rejects_empty_model():
    with pytest.raises(HTTPException) as e:
        run(main.recall_put_settings({"semantic": {"model": "  "}}))
    assert e.value.status_code == 400


# ------------------------------------------------------------ search mode

@pytest.mark.parametrize("mode", ["semantic", "hybrid", "nonsense"])
def test_search_mode_400_when_disabled_or_bad(mode):
    with pytest.raises(HTTPException) as e:
        run(main.recall_search(q="planner", mode=mode))
    assert e.value.status_code == 400


def test_search_default_is_keyword_when_disabled():
    res = run(main.recall_search(q="planner", project="app"))
    assert res["coverage"]["semantic"] == {"mode": "keyword"}
    assert [h["id"] for h in res["hits"]] == ["c1"]


def test_index_requires_enabled():
    with pytest.raises(HTTPException) as e:
        run(main.recall_index_start({}))
    assert e.value.status_code == 400


def test_hybrid_end_to_end_through_routes():
    enable()
    start = run(main.recall_index_start({"project": "app"}))
    assert start["state"] == "running" and start["project"]["name"] == "app"
    main._recall_job.wait(10)
    st = run(main.recall_index_status())
    assert st["state"] == "done" and st["sessions_done"] == 2 and st["chunks_embedded"] == 2
    assert run(main.recall_get_settings())["index"]["chunks"] == 2

    # Paraphrase-free query that only the vector side can rank next to the
    # keyword side: "classifier" hits c1 by keyword; hybrid must tag it.
    res = run(main.recall_search(q="planner classifier", project="app", mode="hybrid"))
    sem = res["coverage"]["semantic"]
    assert sem["mode"] == "hybrid" and sem["indexed_sessions"] == 2 and sem["unindexed_sessions"] == 0
    top = res["hits"][0]
    assert top["id"] == "c1" and top["match"] == "both"

    # Pure semantic mode still works through the same route.
    sres = run(main.recall_search(q="planner classifier", project="app", mode="semantic"))
    assert sres["hits"] and all(h["match"] in ("semantic", "both") for h in sres["hits"])


def test_default_mode_from_settings_applies():
    enable()
    run(main.recall_put_settings({"semantic": {"default_mode": "hybrid"}}))
    build_index()
    res = run(main.recall_search(q="planner", project="app"))
    assert res["coverage"]["semantic"]["mode"] == "hybrid"
    res = run(main.recall_search(q="planner", project="app", mode="keyword"))
    assert res["coverage"]["semantic"] == {"mode": "keyword"}


def test_unindexed_sessions_fall_back_to_keyword():
    enable()
    res = run(main.recall_search(q="planner", project="app", mode="hybrid"))
    assert res["coverage"]["semantic"]["unindexed_sessions"] == 2
    assert [h["id"] for h in res["hits"]] == ["c1"] and res["hits"][0]["match"] == "keyword"


def test_index_409_while_running_and_unknown_project_400(env):
    enable()
    env.gate = threading.Event()
    try:
        first = run(main.recall_index_start({}))
        assert first["state"] == "running"
        busy = run(main.recall_index_start({}))
        assert busy.status_code == 409
        assert json.loads(busy.body)["state"] == "running"
    finally:
        env.gate.set()
    main._recall_job.wait(10)
    with pytest.raises(HTTPException) as e:
        run(main.recall_index_start({"project": "no-such-project"}))
    assert e.value.status_code == 400


# ------------------------------------------------------------ ask

class FakeSm:
    name = "fake"

    def is_available(self):
        return True


def reply(action, args, thought="t"):
    return json.dumps({"thought": thought, "action": action, "args": args})


@pytest.fixture
def ask_env(monkeypatch):
    calls = []
    script = []

    def fake_llm(sm, prompt):
        calls.append(prompt)
        item = script[min(len(calls) - 1, len(script) - 1)]
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(main._recall_summaries, "load_config",
                        lambda: {"enabled": True, "backend": "fake", "model": None})
    monkeypatch.setattr(main, "get_summarizer", lambda *a, **k: FakeSm())
    monkeypatch.setattr(main._recall_summaries, "ask_untrusted", fake_llm)
    return calls, script


async def collect(resp, request=None):
    out = []
    async for raw in resp.body_iterator:
        out.append(json.loads(raw))
    return out


def ask(body, request=None):
    async def go():
        resp = await main.recall_ask(request or FakeRequest(), body)
        return resp, await collect(resp)
    return asyncio.run(go())


def test_ask_validation_and_409(ask_env, monkeypatch):
    for bad in ({}, {"question": ""}, {"question": "   "}, {"question": "x" * 1001}, {"question": 5}):
        with pytest.raises(HTTPException) as e:
            run(main.recall_ask(FakeRequest(), bad))
        assert e.value.status_code == 400
    monkeypatch.setattr(main._recall_summaries, "load_config", lambda: {"enabled": False, "backend": None})
    with pytest.raises(HTTPException) as e:
        run(main.recall_ask(FakeRequest(), {"question": "why?"}))
    assert e.value.status_code == 409 and "AI summaries are off" in e.value.detail


def test_ask_streams_status_steps_answer(ask_env):
    calls, script = ask_env
    script += [
        reply("search", {"query": "classifier planner"}),
        reply("answer", {"answer": "The planner uses a classifier [S1].", "citations": ["S1"]}),
    ]
    resp, events = ask({"question": "How is the planner wired?", "project": "app"})
    assert resp.media_type == "application/x-ndjson"
    assert resp.headers["cache-control"] == "no-cache"
    assert resp.headers["x-accel-buffering"] == "no"
    types = [e["type"] for e in events]
    assert types[0] == "status" and types[-1] == "answer"
    assert events[0]["summarizer"] == "fake" and events[0]["project"]["name"] == "app"
    assert events[0]["mode"] == "keyword"
    assert types[1:3] == ["step", "observation"] and events[1]["n"] == 0
    assert "step" in types[3:] and "observation" in types[3:]
    ans = events[-1]
    assert ans["citations"][0]["agent"] == "codex" and ans["citations"][0]["id"] == "c1"
    assert len(calls) == 2
    # Evidence reaches the model fenced.
    assert "<untrusted_session_data>" in calls[0]


def test_ask_summarizer_error_becomes_classified_error_event(ask_env):
    calls, script = ask_env
    script.append(main.SummarizerError("HTTP 500 from provider: boom"))
    _, events = ask({"question": "anything about planner?", "project": "app"})
    assert events[-1]["type"] == "error"
    info = events[-1]["error_info"]
    assert {"category", "title", "message", "hint"} <= set(info)
    assert "Traceback" not in json.dumps(events[-1])


def test_ask_disconnect_stops_llm_calls(ask_env):
    calls, script = ask_env
    script.append(reply("search", {"query": "planner"}))  # never answers
    # Client goes away after the status, step 0 and its observation.
    resp, events = ask({"question": "keep searching the planner", "project": "app"},
                       request=FakeRequest(after=1))
    assert [e["type"] for e in events][:3] == ["status", "step", "observation"]
    assert not any(e["type"] == "answer" for e in events)
    assert len(calls) <= 1
    n = len(calls)
    # Nothing keeps calling the model afterwards.
    import time
    time.sleep(0.5)
    assert len(calls) == n


def test_ask_tools_stay_inside_the_users_scope(ask_env):
    calls, script = ask_env
    script += [
        reply("read_session", {"agent": "claude", "session_id": "a1"}),
        reply("search", {"query": "planner", "agent": "claude"}),
        reply("answer", {"answer": "done", "citations": []}),
    ]
    _, events = ask({"question": "How is the planner wired?", "project": "app", "agent": "codex"})
    obs = [e for e in events if e["type"] == "observation"]
    assert any(e["n"] == 1 and "read failed" in e["summary"] for e in obs), obs
    # The refused read never put the claude session's text in front of the model.
    assert not any("S2" in e.get("sessions", []) for e in obs)
    # The model asked to search claude; the user limited the question to codex.
    later = [e for e in obs if e["n"] >= 2]
    assert later and "claude" not in later[0]["summary"], later
