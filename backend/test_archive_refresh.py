"""The transcript archive copies only what changed, and never loses data.

Before this fix every opted-in transcript was re-read and re-compressed on
every scan, changed or not, and a truncated or rotated source would replace a
fuller archived copy. Now a transcript is copied when it changed since its
last copy (once the session goes quiet, or daily while it stays active), and a
much smaller copy never replaces a larger one.
"""
import os
import time

import pytest

import main


DAY = 24 * 60 * 60


# ------------------------------------------------------------- the decision

@pytest.mark.parametrize("now,mtime,archived_at,due", [
    (1_000_000, 900_000, None, True),                     # never archived
    (1_000_000, 900_000, 950_000, False),                 # unchanged since the copy
    (1_000_000, 960_000, 950_000, True),                  # grew, quiet for 40000 s
    (1_000_000, 999_900, 999_000, False),                 # grew, still active, copy is fresh
    (1_000_000, 999_900, 1_000_000 - DAY - 1, True),      # still active, copy over a day old
])
def test_archive_due(now, mtime, archived_at, due):
    assert main._archive_due(now, mtime, archived_at) is due


# ------------------------------------------------------------- end to end

@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKENTELEMETRY_DATA_DIR", str(tmp_path / "data"))
    import importlib
    import history_store
    importlib.reload(history_store)
    transcript = tmp_path / "s1.jsonl"
    monkeypatch.setattr(main, "_resolve_transcript_path", lambda agent, sid: transcript)
    import agent_retention
    monkeypatch.setattr(agent_retention, "archive_enabled", lambda agent: agent == "claude")
    return history_store, transcript


def _write(path, lines, age_s):
    path.write_text("".join(f'{{"n": {i}, "text": "turn {i} ' + "x" * 200 + '"}\n' for i in range(lines)))
    t = time.time() - age_s
    os.utime(path, (t, t))


def _archive():
    main._archive_opted_in_transcripts([{"agent": "claude", "id": "s1"}])


def test_first_scan_archives_and_growth_is_copied_once_quiet(env):
    hs, path = env
    _write(path, 10, age_s=3600)
    _archive()
    assert hs.get_transcript("claude", "s1").count("\n") == 10

    # The session grows and goes quiet: the next scan refreshes the copy.
    _write(path, 25, age_s=0)
    t = time.time() + 1  # the file changed after the copy
    os.utime(path, (t, t))
    _archive()
    assert hs.get_transcript("claude", "s1").count("\n") == 10, "still active: no copy yet"

    later = time.time() + main.ARCHIVE_IDLE_SEC + 5
    real = time.time
    try:
        main._time.time = lambda: later
        _archive()
    finally:
        main._time.time = real
    assert hs.get_transcript("claude", "s1").count("\n") == 25


def test_active_session_is_refreshed_daily(env, monkeypatch):
    hs, path = env
    _write(path, 10, age_s=3600)
    _archive()
    _write(path, 30, age_s=0)
    now = time.time()
    # Pretend the copy is older than a day while the session is still being written.
    meta = hs.archive_meta()
    old = meta[("claude", "s1")]
    monkeypatch.setattr(hs, "archive_meta", lambda: {("claude", "s1"): {**old, "archived_at": "2000-01-01T00:00:00+00:00"}})
    monkeypatch.setattr(main._time, "time", lambda: now)
    _archive()
    assert hs.get_transcript("claude", "s1").count("\n") == 30


def test_truncated_source_never_replaces_a_fuller_copy(env, monkeypatch):
    hs, path = env
    _write(path, 200, age_s=3600)
    _archive()
    _write(path, 3, age_s=0)  # rotated or truncated, but newer
    t = time.time() + 1
    os.utime(path, (t, t))
    monkeypatch.setattr(main._time, "time", lambda: t + main.ARCHIVE_IDLE_SEC + 5)
    _archive()
    assert hs.get_transcript("claude", "s1").count("\n") == 200


def test_unchanged_transcript_is_not_reread(env, monkeypatch):
    hs, path = env
    _write(path, 10, age_s=3600)
    _archive()
    reads = []
    real_open = main._open_maybe_zst
    monkeypatch.setattr(main, "_open_maybe_zst", lambda p: (reads.append(p), real_open(p))[1])
    _archive()
    assert reads == [], "an unchanged transcript must not be read or compressed again"


def test_opted_out_agent_is_never_archived(env):
    hs, path = env
    _write(path, 5, age_s=3600)
    main._archive_opted_in_transcripts([{"agent": "codex", "id": "s1"}])
    assert hs.get_transcript("codex", "s1") is None
