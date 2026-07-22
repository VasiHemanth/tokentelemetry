"""Tests for OpenCode data-dir resolution (discussion #170).

Before this, TokenTelemetry only ever looked at ``~/.local/share/opencode/
opencode.db``, so a relocated or non-Linux OpenCode install was silently
invisible. These tests pin the candidate-probing behaviour: env override,
``$XDG_DATA_HOME``, per-OS defaults, priority, and the fall-back-to-canonical
when nothing exists yet.
"""

import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import main  # noqa: E402


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
