"""Tests for native session scanning of Kimi Code (Moonshot AI, binary `kimi`).

Kimi Code stores one directory per session under
    ~/.kimi/sessions/<workdir-hash>/<session-uuid>/
with the event stream in wire.jsonl and the title in state.json. wire.jsonl
opens with {"type":"metadata","protocol_version":...}, then
{"timestamp": <epoch float>, "message": {"type", "payload"}} rows. Token usage
rides on StatusUpdate payloads (payload.token_usage = {input_other, output,
input_cache_read, input_cache_creation}), de-duped by payload.message_id. The
model comes from ~/.kimi/config.toml's default_model; the project from
~/.kimi/kimi.json's work_dirs registry. ~/.kimi/credentials/ holds OAuth tokens
and is never read; all fixtures below are synthetic.

Run: pytest backend/test_kimi_scan.py -q
"""
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import main  # noqa: E402
from pricing import calculate_cost  # noqa: E402

SID = "11111111-2222-3333-4444-555555555555"
PROJECT = "/home/dev/proj-alpha"
MODEL = "kimi-k2.6"


# ---------------------------------------------------------------------------
# Fixture builders — mirror the real wire.jsonl / state.json / kimi.json shapes.
# ---------------------------------------------------------------------------

def _status(message_id, ts, *, input_other, output, cache_read=0, cache_creation=0):
    return {"timestamp": ts, "message": {"type": "StatusUpdate", "payload": {
        "message_id": message_id,
        "token_usage": {"input_other": input_other, "output": output,
                        "input_cache_read": cache_read,
                        "input_cache_creation": cache_creation}}}}


def _write_kimi_home(root: Path, *, sid=SID, project=PROJECT, model=MODEL,
                     duplicate_status=True, with_state=True, with_wire=True):
    """Write a synthetic ~/.kimi tree: kimi.json registry, config.toml, and one
    session with two StatusUpdates (the second pair repeating the first
    message_id to prove de-dupe fires)."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "kimi.json").write_text(json.dumps({"work_dirs": [
        {"path": project, "kaos": "local", "last_session_id": sid},
    ]}), encoding="utf-8")
    (root / "config.toml").write_text(
        f'default_model = "{model}"\n\n[loop_control]\nmax_steps_per_turn = 100\n',
        encoding="utf-8")

    sess = root / "sessions" / "deadbeefhash" / sid
    sess.mkdir(parents=True, exist_ok=True)
    if with_state:
        (sess / "state.json").write_text(json.dumps({
            "custom_title": "Refactor the scanner", "session_id": sid,
        }), encoding="utf-8")
    if with_wire:
        rows = [
            {"type": "metadata", "protocol_version": "1.8"},
            {"timestamp": 1786800000.0, "message": {"type": "TurnBegin", "payload": {
                "user_input": [{"type": "text", "text": "fallback prompt text"}]}}},
            _status("chatcmpl-aaa", 1786800001.0, input_other=2965, output=185,
                    cache_read=100, cache_creation=50),
            _status("chatcmpl-bbb", 1786800005.0, input_other=500, output=42,
                    cache_read=200, cache_creation=0),
        ]
        if duplicate_status:
            # The same usage sample re-sent under the SAME message_id must not
            # double-count.
            rows.append(_status("chatcmpl-aaa", 1786800006.0, input_other=2965,
                                output=185, cache_read=100, cache_creation=50))
        rows.append({"timestamp": 1786800010.0, "message": {"type": "TurnEnd", "payload": {}}})
        (sess / "wire.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return sess


@pytest.fixture
def kimi_home(tmp_path, monkeypatch):
    root = tmp_path / ".kimi"
    monkeypatch.setattr(main, "KIMI_DIR", root)
    monkeypatch.setattr(main, "KIMI_SESSIONS_DIR", root / "sessions")
    monkeypatch.setattr(main, "_load_project_aliases", lambda: {})
    return root


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------

def test_scan_kimi_maps_tokens_cost_display_and_project(kimi_home):
    _write_kimi_home(kimi_home)
    out = main._scan_kimi_sessions()
    assert len(out) == 1
    s = out[0]
    assert s["agent"] == "kimi"
    assert s["id"] == SID
    assert s["project"] == PROJECT
    assert s["model"] == MODEL
    assert s["display"] == "Refactor the scanner", \
        "state.json custom_title beats the first-prompt fallback"

    tk = s["tokens"]
    assert tk["input"] == 2965 + 500
    assert tk["output"] == 185 + 42
    assert tk["cached"] == 100 + 200
    assert tk["cache_creation"] == 50
    assert tk["total"] == tk["input"] + tk["output"] + tk["cached"] + tk["cache_creation"]

    expected = calculate_cost(MODEL, 2965 + 500, 185 + 42, 100 + 200,
                              cache_creation_tokens=50, at=s["timestamp"])
    assert expected > 0
    assert s["cost"] == pytest.approx(expected)
    assert s["tokens"]["cost"] == pytest.approx(expected)


def test_scan_kimi_dedupes_status_updates_by_message_id(kimi_home):
    _write_kimi_home(kimi_home, duplicate_status=True)
    s = main._scan_kimi_sessions()[0]
    # Without de-dupe the first sample would count twice.
    assert s["tokens"]["input"] == 2965 + 500
    assert s["kimi"]["num_status_updates"] == 2


def test_scan_kimi_display_falls_back_to_first_user_text(kimi_home):
    _write_kimi_home(kimi_home, with_state=False)
    s = main._scan_kimi_sessions()[0]
    assert s["display"] == "fallback prompt text"


def test_scan_kimi_model_falls_back_to_kimi_for_coding(kimi_home):
    _write_kimi_home(kimi_home)
    (kimi_home / "config.toml").write_text("[loop_control]\n", encoding="utf-8")
    s = main._scan_kimi_sessions()[0]
    assert s["model"] == "kimi-for-coding"


def test_scan_kimi_model_resolves_display_id_through_models_table(kimi_home):
    _write_kimi_home(kimi_home)
    (kimi_home / "config.toml").write_text(
        'default_model = "kimi-code/kimi-for-coding"\n\n'
        '[models."kimi-code/kimi-for-coding"]\nmodel = "kimi-for-coding"\n',
        encoding="utf-8")
    s = main._scan_kimi_sessions()[0]
    assert s["model"] == "kimi-for-coding"


def test_scan_kimi_ignores_malformed_models_config(kimi_home):
    """A valid but wrongly typed TOML table must not prevent session scans."""
    _write_kimi_home(kimi_home)
    (kimi_home / "config.toml").write_text(
        'default_model = "kimi-code/kimi-for-coding"\nmodels = ["bad"]\n',
        encoding="utf-8")

    assert main._scan_kimi_sessions()[0]["model"] == "kimi-code/kimi-for-coding"


def test_scan_kimi_missing_dir_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "KIMI_DIR", tmp_path / "nope")
    monkeypatch.setattr(main, "KIMI_SESSIONS_DIR", tmp_path / "nope" / "sessions")
    assert main._scan_kimi_sessions() == []


def test_scan_kimi_skips_empty_and_malformed_session_dirs(kimi_home):
    _write_kimi_home(kimi_home)
    # Empty session dir (no wire.jsonl) — skipped, not an error.
    (kimi_home / "sessions" / "hash2" / "empty-session").mkdir(parents=True)
    # wire.jsonl full of garbage lines — tokens stay zero, never raises.
    bad = kimi_home / "sessions" / "hash3" / "bad-session"
    bad.mkdir(parents=True)
    (bad / "wire.jsonl").write_text("{not json\n\n[1,2]\n", encoding="utf-8")

    out = main._scan_kimi_sessions()
    by_id = {s["id"]: s for s in out}
    assert SID in by_id
    assert "empty-session" not in by_id
    assert by_id["bad-session"]["tokens"]["total"] == 0


def test_scan_kimi_skips_corrupt_lines(kimi_home):
    sess = _write_kimi_home(kimi_home)
    wire = sess / "wire.jsonl"
    good = wire.read_text().splitlines()
    good.insert(3, "{not json at all")
    wire.write_text("\n".join(good) + "\n", encoding="utf-8")
    out = main._scan_kimi_sessions()
    assert len(out) == 1
    assert out[0]["tokens"]["input"] > 0


def test_scan_kimi_session_without_registry_entry_is_unknown_project(kimi_home):
    """kimi.json only links each work dir's LAST session; any other session's
    project can't be recovered from the hashed bucket name."""
    _write_kimi_home(kimi_home)
    (kimi_home / "kimi.json").write_text(json.dumps({"work_dirs": []}),
                                         encoding="utf-8")
    s = main._scan_kimi_sessions()[0]
    assert s["project"] == "unknown"


def test_scan_kimi_maps_hashed_bucket_to_registered_project(kimi_home):
    sess = _write_kimi_home(kimi_home)
    bucket = kimi_home / "sessions" / hashlib.md5(PROJECT.encode()).hexdigest()
    bucket.mkdir()
    sess.rename(bucket / SID)
    (kimi_home / "kimi.json").write_text(json.dumps({"work_dirs": [
        {"path": PROJECT, "kaos": "local", "last_session_id": None},
    ]}), encoding="utf-8")

    assert main._scan_kimi_sessions()[0]["project"] == PROJECT


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def test_kimi_detected_when_sessions_dir_exists(kimi_home, monkeypatch):
    _write_kimi_home(kimi_home)
    assert "kimi" in main._list_available_agents()

    monkeypatch.setattr(main, "KIMI_SESSIONS_DIR", kimi_home / "gone")
    assert "kimi" not in main._list_available_agents()


# ---------------------------------------------------------------------------
# Session detail trace
# ---------------------------------------------------------------------------

def test_session_detail_kimi_returns_claude_shaped_events(kimi_home):
    _write_kimi_home(kimi_home)
    events = asyncio.run(main.get_session_detail(SID, "kimi"))
    assert isinstance(events, list) and events
    assert all("normalized_timestamp" in e for e in events)
    first = events[0]
    assert first["message"]["role"] == "user"
    assert first["message"]["content"][0]["text"] == "fallback prompt text"


def test_session_detail_kimi_not_found(kimi_home):
    res = asyncio.run(main.get_session_detail("nonexistent-id", "kimi"))
    assert res == {"error": "Not found"}


# ---------------------------------------------------------------------------
# U8: scan cache preserves model at scan time; repricing history on config
# change is the bug this test guards against.
# ---------------------------------------------------------------------------

def test_scan_kimi_cache_preserves_model_across_config_change(kimi_home, tmp_path,
                                                               monkeypatch):
    """U8: a session scanned with model A must still report model A after the
    config changes to model B — the scan cache locks in the model at scan time
    so historical sessions are not retroactively repriced."""
    import scan_cache as sc

    # Point scan_cache at a temp dir so it doesn't touch the real data dir.
    monkeypatch.setattr(sc, "data_dir", lambda: tmp_path / "tt_data")

    _write_kimi_home(kimi_home, model="kimi-k2.6")

    # First scan: wire.jsonl present, model is kimi-k2.6 from config.toml.
    first = main._scan_kimi_sessions()
    assert len(first) == 1
    assert first[0]["model"] == "kimi-k2.6"

    # Now change the config to a different model (simulates user switching).
    (kimi_home / "config.toml").write_text(
        'default_model = "kimi-newer"\n', encoding="utf-8")

    # Second scan: source files unchanged, so cache hit is expected.
    # The session must still report the original model, not the new one.
    second = main._scan_kimi_sessions()
    assert len(second) == 1
    assert second[0]["model"] == "kimi-k2.6", (
        "model must be preserved from cache; config change must not retroactively "
        "reprice existing sessions")


def test_scan_kimi_cache_refreshes_when_wire_changes(kimi_home, tmp_path, monkeypatch):
    """Cache must be invalidated when wire.jsonl is newer than the stored mtime."""
    import os
    import time
    import scan_cache as sc

    monkeypatch.setattr(sc, "data_dir", lambda: tmp_path / "tt_data")

    sess_dir = _write_kimi_home(kimi_home, model="kimi-k2.6")

    # First scan writes the cache.
    first = main._scan_kimi_sessions()
    assert first[0]["tokens"]["input"] == 2965 + 500

    # Append a new StatusUpdate so the session has more tokens.
    wire = sess_dir / "wire.jsonl"
    with open(wire, "a", encoding="utf-8") as f:
        f.write(json.dumps(_status("chatcmpl-ccc", 1786800020.0,
                                   input_other=1000, output=10)) + "\n")
    # Set mtime to 2 seconds in the future — reliable even on 1s-resolution
    # filesystems (HFS+, FAT32) without any sleep.
    future = time.time() + 2.0
    os.utime(wire, (future, future))

    # Second scan must re-parse (cache miss due to newer mtime).
    second = main._scan_kimi_sessions()
    assert second[0]["tokens"]["input"] == 2965 + 500 + 1000, (
        "cache should be invalidated when wire.jsonl is modified")
