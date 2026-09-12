"""A failed summarization must not mark the stale narrative as fresh (#352).

When generation fails on a trace that has grown, `make_summary` falls back to
the previously stored narrative. That fallback is correct: showing the earlier
summary beats showing nothing. What must not happen is re-storing it under the
NEW content hash, because that hash mismatch is the only signal that makes a
later call regenerate. Overwriting it marks a stale summary fresh permanently:
every subsequent request short-circuits at the cache check and the summarizer
is never called again, even after it recovers.

Run: pytest backend/test_summary_stale_fallback.py -q
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import summaries  # noqa: E402
import main  # noqa: E402

SESSION = "sess-352"
AGENT = "claude"


def _events(count: int):
    """content_hash keys off len(events) and the last timestamp, so growing the
    list is what makes a trace look changed."""
    return [
        {"type": "user", "normalized_timestamp": "2026-09-10T00:%02d:00Z" % i}
        for i in range(count)
    ]


@pytest.fixture
def summary_db(tmp_path, monkeypatch):
    monkeypatch.setattr(summaries, "_DB_PATH", tmp_path / "summaries.db")
    return tmp_path


def _wire(monkeypatch, events, *, summarizer_works: bool, headline: str = "fresh"):
    async def _detail(session_id, agent):
        return events

    async def _meta(session_id, agent):
        return {"agent": agent}

    class _Stub:
        def is_available(self):
            return True

        def summarize(self, prompt):
            if not summarizer_works:
                raise main.SummarizerError("backend is down")
            return '{"intent_outcome": "%s"}' % headline

    monkeypatch.setattr(main, "get_session_detail", _detail)
    monkeypatch.setattr(main, "_session_meta", _meta)
    monkeypatch.setattr(main, "get_summarizer", lambda *a, **k: _Stub())
    monkeypatch.setattr(summaries, "load_config", lambda: {
        "enabled": True, "backend": "stub", "model": "test-model",
    })


def _summarize(force: bool = False):
    return asyncio.run(main.make_summary(SESSION, agent=AGENT, force=force))


def test_a_failed_regeneration_leaves_the_row_on_its_old_hash(summary_db, monkeypatch):
    # 1. A short trace summarizes fine.
    _wire(monkeypatch, _events(3), summarizer_works=True, headline="three events")
    first = _summarize()
    old_hash = first["summary"]["content_hash"]
    assert first["summary"]["narrative"]["intent_outcome"] == "three events"
    assert first["summary"]["stale"] is False

    # 2. The trace grows and the summarizer is down.
    _wire(monkeypatch, _events(10), summarizer_works=False)
    second = _summarize()

    # The old narrative is still served, which is the correct fallback.
    assert second["error"]
    assert second["summary"]["narrative"]["intent_outcome"] == "three events"
    # ...but it is labelled honestly, and the row keeps its ORIGINAL hash so a
    # later attempt still sees the content as changed.
    assert second["summary"]["stale"] is True
    assert second["summary"]["content_hash"] == old_hash
    assert summaries.get_cached(SESSION)["content_hash"] == old_hash


def test_the_summary_regenerates_once_the_backend_recovers(summary_db, monkeypatch):
    _wire(monkeypatch, _events(3), summarizer_works=True, headline="three events")
    _summarize()

    _wire(monkeypatch, _events(10), summarizer_works=False)
    _summarize()

    # Backend recovers. Without the fix the cached hash already equalled the
    # grown trace's hash, so this call short-circuited and returned the stale
    # narrative forever. No force=True, no user action.
    _wire(monkeypatch, _events(10), summarizer_works=True, headline="ten events")
    third = _summarize()

    assert third["error"] is None
    assert third["summary"]["narrative"]["intent_outcome"] == "ten events"
    assert third["summary"]["stale"] is False


def test_a_successful_summary_of_an_unchanged_trace_still_stores_normally(summary_db, monkeypatch):
    """The fix must only skip the store on the stale-fallback path."""
    _wire(monkeypatch, _events(5), summarizer_works=True, headline="five events")
    first = _summarize()

    _wire(monkeypatch, _events(5), summarizer_works=True, headline="regenerated")
    forced = _summarize(force=True)

    assert forced["summary"]["stale"] is False
    assert forced["summary"]["content_hash"] == first["summary"]["content_hash"]
    assert forced["summary"]["narrative"]["intent_outcome"] == "regenerated"
    assert summaries.get_cached(SESSION)["narrative"]["intent_outcome"] == "regenerated"


def test_a_failure_with_no_cached_narrative_at_all_still_stores(summary_db, monkeypatch):
    """Nothing to fall back to, so the empty row is written as before and the
    next attempt retries (the cache gate requires a truthy narrative)."""
    _wire(monkeypatch, _events(4), summarizer_works=False)
    result = _summarize()

    assert result["error"]
    assert result["summary"]["stale"] is False
    assert summaries.get_cached(SESSION) is not None
