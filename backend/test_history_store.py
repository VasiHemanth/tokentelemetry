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


def test_upsert_recency_guard_rejects_older_scan_data():
    """U14: a non-stub upsert whose last_seen_at is older than the stored row's
    must not overwrite token counts or cost.

    Scenario: scan B (newer) writes total=150 and a future last_seen_at directly
    into the store; then scan A (older, lower last_seen_at from datetime.now())
    tries to upsert total=100. The WHERE guard in the conflict clause must reject
    A's update, leaving total=150 in the DB."""
    import sqlite3 as _sqlite3
    from tt_paths import data_dir as _data_dir

    h = _fresh_store()
    # First write: scan B's data with total=150.
    h.upsert_sessions([_session(total=150, tokens={"input": 100, "output": 45, "cached": 5, "total": 150})])

    # Advance the stored last_seen_at to a time far in the future so that the
    # next upsert (scan A, using datetime.now()) is guaranteed to be "older".
    db_path = _data_dir() / "history.db"
    con = _sqlite3.connect(str(db_path))
    con.execute("UPDATE sessions SET last_seen_at='2099-01-01T00:00:00+00:00' WHERE id='s1'")
    con.commit()
    con.close()

    # Scan A tries to overwrite with stale lower counts.
    h.upsert_sessions([_session(total=100, tokens={"input": 50, "output": 45, "cached": 5, "total": 100})])

    rows = h.query()
    assert len(rows) == 1
    assert rows[0]["tokens"]["total"] == 150, (
        f"older scan must not overwrite newer data; got {rows[0]['tokens']['total']}"
    )


def test_upsert_recency_guard_allows_newer_scan_data():
    """The guard must still allow a newer scan to update an existing row."""
    h = _fresh_store()
    h.upsert_sessions([_session(total=17)])
    # Second upsert has a later datetime.now() — should win.
    h.upsert_sessions([_session(total=31, tokens={"input": 20, "output": 9, "cached": 2, "total": 31})])
    rows = h.query()
    assert rows[0]["tokens"]["total"] == 31, "newer scan must update the row"


def test_upsert_recency_guard_allows_null_last_seen_at():
    """Legacy rows with NULL last_seen_at must always accept an update."""
    import sqlite3 as _sqlite3
    from tt_paths import data_dir as _data_dir

    h = _fresh_store()
    h.upsert_sessions([_session(total=17)])

    db_path = _data_dir() / "history.db"
    con = _sqlite3.connect(str(db_path))
    con.execute("UPDATE sessions SET last_seen_at=NULL WHERE id='s1'")
    con.commit()
    con.close()

    h.upsert_sessions([_session(total=31, tokens={"input": 20, "output": 9, "cached": 2, "total": 31})])
    rows = h.query()
    assert rows[0]["tokens"]["total"] == 31, "NULL last_seen_at must not block the update"


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
