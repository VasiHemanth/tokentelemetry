"""Tests for the durable history store (issue #83 / discussion #27).

The store is what lets analytics outlive the agents' own transcript pruning, so
these pin the behaviours the feature depends on: idempotent upserts (a growing
session updates one row, never duplicates), absent-marking that flags pruned
sessions without deleting them, tiered deletes that free transcript space while
keeping the core rollup, and SQL-side date/allow-list filtering.

No pytest in the venv — run directly:  python backend/test_history_store.py
"""
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

_VAR = "TOKENTELEMETRY_DATA_DIR"


def _fresh_store():
    """Point the store at a brand-new tmp dir and return the (reimported) module."""
    d = tempfile.mkdtemp(prefix="tt-hist-")
    os.environ[_VAR] = d
    import importlib
    import history_store
    importlib.reload(history_store)
    return history_store


def _session(sid="s1", agent="claude", ts=None, total=17, **kw):
    ts = ts or datetime.now(timezone.utc)
    s = {
        "id": sid, "agent": agent, "project": "/p", "model": "claude-opus-4-8",
        "provider": None, "endpoint": None, "billing_mode": None, "timestamp": ts,
        "tokens": {"input": 10, "output": 5, "cached": 2, "total": total},
        "cost": 0.01, "tok_per_sec": 40,
    }
    s.update(kw)
    return s


def test_upsert_is_idempotent_and_updates_growing_session():
    h = _fresh_store()
    h.upsert_sessions([_session(total=17)])
    h.upsert_sessions([_session(total=31, tokens={"input": 20, "output": 9, "cached": 2, "total": 31})])
    rows = h.query()
    assert len(rows) == 1, f"expected 1 row, got {len(rows)}"
    assert rows[0]["tokens"]["total"] == 31, "row should reflect the latest scan"


def test_mark_absent_flags_without_deleting():
    h = _fresh_store()
    h.upsert_sessions([_session()])
    h.mark_absent(set())  # nothing seen this scan -> the row is now off-disk
    rows = h.query()
    assert len(rows) == 1, "mark_absent must never delete the rollup"
    assert rows[0]["source_present"] is False


def test_ecosystem_roundtrips():
    h = _fresh_store()
    h.upsert_sessions([_session(skills_used=[{"name": "x", "count": 2}],
                                delegation={"spawn_count": 3})])
    r = h.query()[0]
    assert r.get("skills_used") == [{"name": "x", "count": 2}]
    assert r.get("delegation") == {"spawn_count": 3}


def test_transcript_delete_keeps_rollup_and_summary():
    h = _fresh_store()
    h.upsert_sessions([_session()])
    h.put_transcript("claude", "s1", "full transcript text")
    h.put_summary("claude", "s1", "a short summary")
    assert h.get_transcript("claude", "s1") == "full transcript text"
    deleted = h.delete_transcripts(agent="claude")
    assert deleted == 1
    assert h.get_transcript("claude", "s1") is None, "blob should be gone"
    assert h.get_summary("claude", "s1") == "a short summary", "summary must survive"
    r = h.query()[0]
    assert r["transcript_archived"] is False
    assert r["summary_present"] is True
    assert r["tokens"]["total"] == 17, "core rollup must survive the purge"


def test_date_and_allowlist_filters():
    h = _fresh_store()
    old = datetime.now(timezone.utc) - timedelta(days=10)
    new = datetime.now(timezone.utc)
    h.upsert_sessions([
        _session("old", agent="claude", ts=old),
        _session("new", agent="codex", ts=new, model="gpt-5"),
    ])
    # Date window: only the last 3 days.
    frm = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    recent = h.query(from_=frm)
    assert {r["id"] for r in recent} == {"new"}, "from_ must exclude the old row"
    # Agent allow-list.
    assert {r["id"] for r in h.query(agents=["claude"])} == {"old"}
    # Model allow-list.
    assert {r["id"] for r in h.query(models=["gpt-5"])} == {"new"}
    # Empty list == no filter (All).
    assert len(h.query(agents=[])) == 2


def test_storage_and_coverage():
    h = _fresh_store()
    h.upsert_sessions([_session("a"), _session("b", agent="codex")])
    h.put_transcript("claude", "a", "x" * 500)
    cov = h.coverage()
    assert cov["total_sessions"] == 2
    assert cov["earliest"] is not None
    stats = h.storage_stats()
    assert stats["by_agent"]["claude"]["sessions"] == 1
    assert stats["by_agent"]["claude"]["transcripts"] == 1
    assert stats["transcript_bytes"] > 0


def test_mark_absent_skips_rows_upserted_by_newer_scan():
    """U13: mark_absent must not clobber rows that a concurrent newer scan
    upserted after the older scan began.

    Scenario: scan A and scan B fire concurrently. Scan B sees session s2
    (new); scan A does not. Both submit persist jobs to a thread executor.
    If scan B's upsert runs first and then scan A's mark_absent fires, s2
    must remain source_present=1 — scan A started before s2 existed."""
    import time as _time
    h = _fresh_store()

    scan_a_started = datetime.now(timezone.utc).isoformat()

    # Simulate scan B's upsert running AFTER scan A started.
    _time.sleep(0.01)  # ensure last_seen_at > scan_a_started
    h.upsert_sessions([_session("s1"), _session("s2")])

    # Scan A's mark_absent: only saw s1, started before s2 was upserted.
    h.mark_absent({("claude", "s1")}, scan_started_at=scan_a_started)

    rows = {r["id"]: r for r in h.query()}
    assert rows["s1"]["source_present"] is True, "s1 was seen by scan A"
    assert rows["s2"]["source_present"] is True, (
        "s2 was upserted by a newer scan after scan_a_started; mark_absent must not touch it"
    )


def test_mark_absent_does_clear_genuinely_absent_rows():
    """Rows that were NOT seen by any scan since scan_started_at must still be
    marked absent. Only rows with last_seen_at >= scan_started_at are protected."""
    import time as _time
    h = _fresh_store()

    # Persist s_old before scan A starts.
    h.upsert_sessions([_session("s_old")])

    _time.sleep(0.01)
    scan_a_started = datetime.now(timezone.utc).isoformat()
    _time.sleep(0.01)

    # Scan A sees only s_new (s_old was deleted between scans).
    h.upsert_sessions([_session("s_new")])
    h.mark_absent({("claude", "s_new")}, scan_started_at=scan_a_started)

    rows = {r["id"]: r for r in h.query()}
    assert rows["s_new"]["source_present"] is True
    assert rows["s_old"]["source_present"] is False, (
        "s_old last_seen_at < scan_a_started so it must be marked absent"
    )


def test_bucket_key_day_week_month():
    # _bucket_key lives in the analytics endpoint module; import lazily so a
    # missing FastAPI dep degrades to a skip rather than a hard failure.
    try:
        import main
    except Exception as e:  # noqa: BLE001
        print(f"SKIP  bucket_key (main not importable: {e})")
        return
    d = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)  # a Wednesday
    assert main._bucket_key(d, "day").endswith("-10")
    # Week collapses to that week's Monday (the 8th, local time).
    assert main._bucket_key(d, "week")[:7] == "2026-06"
    assert main._bucket_key(d, "month").endswith("-01")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {t.__name__}: {e!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
