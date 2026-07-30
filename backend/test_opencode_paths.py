"""Tests for OpenCode data-dir + DB-filename resolution (discussion #170).

Before this, TokenTelemetry only ever looked at ``~/.local/share/opencode/
opencode.db``, so an OpenCode install was silently invisible if it was
relocated, non-Linux, or — the actual cause endorama hit — built for a release
channel other than `latest`/`beta`, which names the file
``opencode-<channel>.db`` (a Nix `stable` build writes ``opencode-stable.db``).

These tests pin both halves: the directory probing (env override,
``$XDG_DATA_HOME``, per-OS defaults, priority, fall-back-to-canonical) and the
filename globbing (channel suffixes found, sidecars ignored, every DB scanned).
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


def _clear_oc_env(monkeypatch):
    monkeypatch.delenv("OPENCODE_DATA_DIR", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)


def _mk_db(path: Path):
    """Create a minimal opencode.db with a session table at ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE session(id TEXT)")
    conn.commit()
    conn.close()


def test_candidates_always_include_xdg_default(monkeypatch):
    _clear_oc_env(monkeypatch)
    cands = main._opencode_db_candidates()
    assert main.HOME / ".local/share/opencode/opencode.db" in cands


def test_env_override_is_first_candidate(monkeypatch):
    _clear_oc_env(monkeypatch)
    monkeypatch.setenv("OPENCODE_DATA_DIR", "/opt/oc-data")
    cands = main._opencode_db_candidates()
    assert cands[0] == Path("/opt/oc-data/opencode.db")


def test_xdg_data_home_is_probed(monkeypatch):
    _clear_oc_env(monkeypatch)
    monkeypatch.setenv("XDG_DATA_HOME", "/xdg")
    cands = main._opencode_db_candidates()
    assert Path("/xdg/opencode/opencode.db") in cands


def test_windows_probes_appdata_and_localappdata(monkeypatch):
    _clear_oc_env(monkeypatch)
    monkeypatch.setattr(main.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", r"C:\\Users\\dev\\AppData\\Roaming")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\\Users\\dev\\AppData\\Local")
    cands = main._opencode_db_candidates()
    assert Path(r"C:\\Users\\dev\\AppData\\Roaming") / "opencode" / "opencode.db" in cands
    assert Path(r"C:\\Users\\dev\\AppData\\Local") / "opencode" / "opencode.db" in cands


def test_candidates_are_deduped(monkeypatch):
    _clear_oc_env(monkeypatch)
    cands = main._opencode_db_candidates()
    assert len(cands) == len(set(cands))


def test_path_picks_existing_env_db(monkeypatch, tmp_path):
    _clear_oc_env(monkeypatch)
    db = tmp_path / "custom" / "opencode.db"
    _mk_db(db)
    monkeypatch.setenv("OPENCODE_DATA_DIR", str(tmp_path / "custom"))
    assert main._opencode_db_path() == db


def test_env_override_wins_over_xdg(monkeypatch, tmp_path):
    _clear_oc_env(monkeypatch)
    env_db = tmp_path / "env" / "opencode.db"
    xdg_db = tmp_path / "xdg" / "opencode" / "opencode.db"
    _mk_db(env_db)
    _mk_db(xdg_db)
    monkeypatch.setenv("OPENCODE_DATA_DIR", str(tmp_path / "env"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert main._opencode_db_path() == env_db


def test_path_falls_back_to_canonical_when_nothing_exists(monkeypatch, tmp_path):
    _clear_oc_env(monkeypatch)
    # Point HOME at an empty dir so no candidate exists on disk.
    monkeypatch.setattr(main, "HOME", tmp_path)
    got = main._opencode_db_path()
    assert got == tmp_path / ".local/share/opencode/opencode.db"


# --- Release-channel DB filenames ------------------------------------------
# OpenCode's getChannelPath(): `latest`/`beta` (or OPENCODE_DISABLE_CHANNEL_DB)
# → "opencode.db"; anything else → f"opencode-{channel}.db". The channel string
# is arbitrary, so detection has to glob rather than match a known list.


def _make_scannable_db(path: Path, *session_ids, wal: bool = False,
                       leave_open: bool = False):
    """An OpenCode DB with enough schema for _scan_sessions_sync to read it.

    ``leave_open`` returns the writer connection instead of closing it. That
    matters for the WAL case: closing the last connection checkpoints and
    deletes the ``-wal`` file, so a closed WAL database is indistinguishable
    from a rollback-journal one and the test would prove nothing. Callers must
    close it themselves.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    if wal:
        con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE session (id TEXT, project_id TEXT, parent_id TEXT, "
                "directory TEXT, title TEXT, time_created INT, time_updated INT)")
    con.execute("CREATE TABLE message (session_id TEXT, time_created INT, data TEXT)")
    con.execute("CREATE TABLE part (session_id TEXT, time_created INT, data TEXT)")
    now = 1750000000000
    for sid in session_ids:
        con.execute("INSERT INTO session VALUES (?, 'p', NULL, '/tmp/x', ?, ?, ?)",
                    (sid, sid, now, now))
        con.execute("INSERT INTO message VALUES (?, ?, ?)", (sid, now, json.dumps(
            {"role": "assistant", "modelID": "gpt-5.2-codex", "providerID": "openai"})))
        con.execute("INSERT INTO part VALUES (?, ?, ?)", (sid, now, json.dumps(
            {"type": "step-finish",
             "tokens": {"input": 11, "output": 6, "cache": {"read": 0, "write": 0}}})))
    con.commit()
    if leave_open:
        return con
    con.close()
    return None


def test_channel_suffixed_db_is_a_candidate(monkeypatch, tmp_path):
    """A `stable`-channel install writes opencode-stable.db, not opencode.db."""
    _clear_oc_env(monkeypatch)
    _mk_db(tmp_path / "opencode-stable.db")
    found = main._opencode_dbs_in(tmp_path)
    assert tmp_path / "opencode-stable.db" in found
    # Canonical name is still offered first even though it doesn't exist here.
    assert found[0] == tmp_path / "opencode.db"


def test_path_resolves_channel_only_install(monkeypatch, tmp_path):
    """endorama's exact environment: the ONLY db present is channel-suffixed."""
    _clear_oc_env(monkeypatch)
    db = tmp_path / "opencode-stable.db"
    _mk_db(db)
    monkeypatch.setenv("OPENCODE_DATA_DIR", str(tmp_path))
    assert main._opencode_db_path() == db


def test_wal_sidecars_are_not_mistaken_for_dbs(monkeypatch, tmp_path):
    """`ls` shows opencode-stable.db{,-shm,-wal}; only the .db is a candidate."""
    _clear_oc_env(monkeypatch)
    _mk_db(tmp_path / "opencode-stable.db")
    (tmp_path / "opencode-stable.db-shm").write_bytes(b"")
    (tmp_path / "opencode-stable.db-wal").write_bytes(b"")
    found = main._opencode_dbs_in(tmp_path)
    assert all(str(p).endswith(".db") for p in found)
    assert len(found) == 2  # canonical + stable, no sidecars


def test_canonical_db_stays_first_when_both_exist(monkeypatch, tmp_path):
    _clear_oc_env(monkeypatch)
    _mk_db(tmp_path / "opencode.db")
    _mk_db(tmp_path / "opencode-stable.db")
    monkeypatch.setenv("OPENCODE_DATA_DIR", str(tmp_path))
    assert main._opencode_db_path() == tmp_path / "opencode.db"


def test_scan_reads_channel_only_db(scan_env):
    """The end-to-end symptom: sessions exist but the agent shows nothing."""
    _make_scannable_db(scan_env / "opencode-stable.db", "ses_stable")
    got = [s for s in main._scan_sessions_sync() if s["agent"] == "opencode"]
    assert [s["id"] for s in got] == ["ses_stable"]
    assert got[0]["tokens"]["input"] == 11


def test_scan_reads_channel_db_with_live_wal(scan_env):
    """WAL is OpenCode's journal mode, and the TUI holds the DB open while you
    use it — which is when you'd check the dashboard. Keep a writer connected
    so the -wal/-shm sidecars endorama saw are actually present during the
    scan, and assert the read-only scan still returns the rows."""
    db = scan_env / "opencode-stable.db"
    con = _make_scannable_db(db, "ses_wal", wal=True, leave_open=True)
    try:
        assert db.with_name(db.name + "-wal").exists(), "no live -wal to test against"
        got = [s for s in main._scan_sessions_sync() if s["agent"] == "opencode"]
        assert [s["id"] for s in got] == ["ses_wal"]
    finally:
        con.close()


def test_scan_merges_every_channel_db(scan_env):
    """Channel-switchers keep several DBs; show them all, each session once."""
    _make_scannable_db(scan_env / "opencode.db", "ses_latest")
    _make_scannable_db(scan_env / "opencode-stable.db", "ses_stable", "ses_dupe")
    _make_scannable_db(scan_env / "opencode-nightly.db", "ses_dupe")
    ids = [s["id"] for s in main._scan_sessions_sync() if s["agent"] == "opencode"]
    assert sorted(ids) == ["ses_dupe", "ses_latest", "ses_stable"]
    assert len(ids) == len(set(ids)), "a session present in two DBs was counted twice"


def test_detail_lookup_finds_session_in_channel_db(scan_env):
    """Otherwise the list populates but clicking a session 404s."""
    _make_scannable_db(scan_env / "opencode.db", "ses_latest")
    _make_scannable_db(scan_env / "opencode-stable.db", "ses_stable")
    assert main._opencode_db_for_session("ses_stable") == scan_env / "opencode-stable.db"
    assert main._opencode_db_for_session("ses_latest") == scan_env / "opencode.db"
    assert main._opencode_db_for_session("ses_nope") is None
