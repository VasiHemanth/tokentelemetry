"""Custom focus prompt for session summaries.

Run: pytest backend/test_custom_summary.py -q
"""
import asyncio
import os
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(__file__))
import summaries  # noqa: E402
import main  # noqa: E402

SESSION = "sess-custom"
AGENT = "claude"


def _events(count: int):
    return [
        {
            "type": "user",
            "normalized_timestamp": "2026-09-10T00:%02d:00Z" % i,
            "message": {"role": "user", "content": f"decide thing {i}"},
        }
        for i in range(count)
    ]


class FakeSummarizer:
    def __init__(self, reply="- decided X"):
        self.reply = reply
        self.prompts = []

    def is_available(self):
        return True

    def summarize(self, prompt, *, timeout=120):
        self.prompts.append(prompt)
        return self.reply


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(summaries, "_DB_PATH", tmp_path / "summaries.db")
    monkeypatch.setattr(
        summaries, "load_config", lambda: {"enabled": True, "backend": "claude", "model": None}
    )
    state = {"events": _events(2), "sm": FakeSummarizer()}

    async def fake_detail(sid, agent):
        return state["events"]

    async def fake_meta(sid, agent):
        return {"agent": agent}

    monkeypatch.setattr(main, "get_session_detail", fake_detail)
    monkeypatch.setattr(main, "_session_meta", fake_meta)
    monkeypatch.setattr(main, "get_summarizer", lambda *a, **k: state["sm"])
    return state


def _run(prompt="list decisions", **extra):
    return asyncio.run(main.make_custom_summary(SESSION, AGENT, {"prompt": prompt, **extra}))


def test_prompt_contains_user_instruction_and_messages(env):
    res = _run()
    assert res["item"]["answer"] == "- decided X"
    sent = env["sm"].prompts[0]
    assert "list decisions" in sent
    assert "decide thing 1" in sent  # message excerpts reach the model


def test_same_prompt_same_trace_is_cached(env):
    _run()
    res = _run()
    assert res["cached"] is True
    assert len(env["sm"].prompts) == 1


def test_grown_trace_regenerates(env):
    _run()
    env["events"] = _events(3)
    res = _run()
    assert res["cached"] is False
    assert len(env["sm"].prompts) == 2


def test_distinct_prompts_are_listed_separately(env):
    _run("list decisions")
    _run("list bugs")
    items = summaries.list_custom(SESSION)
    assert {i["prompt"] for i in items} == {"list decisions", "list bugs"}


def test_empty_prompt_rejected(env):
    with pytest.raises(HTTPException) as e:
        _run("   ")
    assert e.value.status_code == 422


def test_prompt_is_length_capped():
    assert len(summaries.clean_custom_prompt("x" * 5000)) == summaries.MAX_CUSTOM_PROMPT_CHARS


def test_disabled_backend_is_409(env, monkeypatch):
    monkeypatch.setattr(summaries, "load_config", lambda: {"enabled": False, "backend": None})
    with pytest.raises(HTTPException) as e:
        _run()
    assert e.value.status_code == 409


def test_backend_failure_returns_error_info_and_stores_nothing(env):
    from summarizers import SummarizerError

    def boom(prompt, *, timeout=120):
        raise SummarizerError("claude timed out after 120s")

    env["sm"].summarize = boom
    res = _run()
    assert res["item"] is None
    assert res["error_info"]["category"] == "timeout"
    assert summaries.list_custom(SESSION) == []
