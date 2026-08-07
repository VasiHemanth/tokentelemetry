"""Focused contract tests for the paginated Hermes session explorer API."""

import asyncio
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import main  # noqa: E402


def _session(
    session_id: str,
    *,
    timestamp: str,
    project: str = "/workspace/app",
    source: str = "cli",
    model: str = "claude-sonnet-4-6",
    display: str = "Investigate traces",
    tokens: int = 100,
    cost: float = 0.01,
) -> dict:
    return {
        "id": session_id,
        "agent": "hermes",
        "project": project,
        "timestamp": datetime.fromisoformat(timestamp).replace(tzinfo=timezone.utc),
        "display": display,
        "source_subtype": source,
        "model": model,
        "tokens": {"input": tokens, "output": 0, "cached": 0, "total": tokens},
        "cost": cost,
    }


@pytest.fixture
def hermes_sessions(monkeypatch):
    sessions = [
        _session(
            "h-new",
            timestamp="2026-08-07T12:00:00",
            project="/workspace/app",
            source="gateway",
            model="gpt-5.2-codex",
            display="Fix trace replication",
            tokens=500,
            cost=0.50,
        ),
        _session(
            "h-middle",
            timestamp="2026-08-07T11:00:00",
            project="/workspace/docs",
            source="cli",
            display="Update the docs",
            tokens=200,
            cost=0.20,
        ),
        _session(
            "h-old",
            timestamp="2026-08-07T10:00:00",
            project="/workspace/app",
            source="cli",
            display="Review Hermes sessions",
            tokens=100,
            cost=0.10,
        ),
    ]

    async def fake_sessions(fresh: bool = False):
        return sessions

    monkeypatch.setattr(main, "get_sessions_cached", fake_sessions)
    return sessions


def _run(coro):
    return asyncio.run(coro)


def test_hermes_sessions_paginates_and_reports_metadata(hermes_sessions):
    result = _run(main.hermes_sessions(page=2, page_size=2, sort="newest"))

    assert [session["id"] for session in result["sessions"]] == ["h-old"]
    assert result["pagination"] == {
        "page": 2,
        "page_size": 2,
        "total": 3,
        "total_pages": 2,
    }


def test_hermes_sessions_filters_search_project_source_and_model(hermes_sessions):
    result = _run(
        main.hermes_sessions(
            search="replication",
            project="/workspace/app",
            source="gateway",
            model="codex",
            page=1,
            page_size=50,
        )
    )

    assert [session["id"] for session in result["sessions"]] == ["h-new"]
    assert result["sessions"][0]["source"] == "gateway"
    assert result["pagination"]["total"] == 1


def test_hermes_sessions_supports_oldest_and_cost_ordering(hermes_sessions):
    oldest = _run(main.hermes_sessions(sort="oldest", page=1, page_size=50))
    by_cost = _run(main.hermes_sessions(sort="cost_desc", page=1, page_size=50))

    assert [session["id"] for session in oldest["sessions"]] == [
        "h-old", "h-middle", "h-new"
    ]
    assert [session["id"] for session in by_cost["sessions"]] == [
        "h-new", "h-middle", "h-old"
    ]


def test_hermes_sessions_returns_empty_page_for_no_matches(hermes_sessions):
    result = _run(main.hermes_sessions(search="does-not-exist", page=1, page_size=50))

    assert result["sessions"] == []
    assert result["pagination"] == {
        "page": 1,
        "page_size": 50,
        "total": 0,
        "total_pages": 0,
    }
