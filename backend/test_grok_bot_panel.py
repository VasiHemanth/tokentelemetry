"""Grok Bot desktop-app panel sections.

Grok Bot is a separate product from the `grok` CLI, with its own stores:

  ~/.grokbot/                      local executor state (no usage data)
  <Electron userData>/Grok Bot/    app state + sand-client-persistence slices

The persistence directory also holds transcript slices with raw conversation
text. These tests pin the contract that only the weekly-usage and roster slices
are opened, and that nothing surfaces message content.

Run: pytest backend/test_grok_bot_panel.py -q
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from harness_panels import base as base_panel
from harness_panels import grok as grok_panel


ACCOUNT = "sand.client.slice.account.github|user_01TESTACCOUNT"


def _blob_name(key: str) -> str:
    return base64.b32encode(key.encode()).decode().lower().rstrip("=") + ".blob"


def _write_slice(root: Path, key: str, value: dict) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / _blob_name(key)
    path.write_text(json.dumps({"schemaVersion": 1, "value": value}), encoding="utf-8")
    return path


@pytest.fixture
def bot_env(tmp_path, monkeypatch):
    """CLI absent, both bot stores present, quota service redirected to tmp."""
    cli = tmp_path / ".grok"
    bot = tmp_path / ".grokbot"
    app = tmp_path / "Grok Bot"
    slices = app / "sand-client-persistence"
    bot.mkdir()
    slices.mkdir(parents=True)

    monkeypatch.setattr(grok_panel, "GROK_DIR", cli)
    monkeypatch.setattr(grok_panel, "UNIFIED_LOG", cli / "logs" / "unified.jsonl")
    monkeypatch.setattr(grok_panel, "GROK_BOT_DIR", bot)
    monkeypatch.setattr(grok_panel, "GROK_BOT_APP_DIR", app)
    monkeypatch.setattr(grok_panel, "GROK_BOT_SLICES_DIR", slices)
    monkeypatch.setattr(grok_panel, "GROK_BOT_LOG", bot / "local-exec-daemon.log")
    monkeypatch.setattr(grok_panel, "GROK_BOT_COMPUTER_USE_DIR", tmp_path / "cu")

    data = tmp_path / "tt-data"
    data.mkdir()
    monkeypatch.setattr(base_panel, "data_dir", lambda: data)
    return {"cli": cli, "bot": bot, "app": app, "slices": slices, "data": data}


def _usage_slice(env, pct: float = 4.4) -> Path:
    read_ms = 1792947717609
    return _write_slice(env["slices"], ACCOUNT + ".weekly-usage.cache", {
        "kind": "present",
        "reading": {
            "usage": {
                "percentUsed": pct,
                "nextResetMs": 1793513837964,
                "grokPlanLabel": "SuperGrok",
                "onDemand": None,
                "hasNonZeroIncludedLimit": True,
                "isTeamSeat": False,
            },
            "readAtMs": read_ms,
        },
        "expiresAtMs": 1793034117609,
    })


def _roster_slice(env) -> Path:
    return _write_slice(env["slices"], ACCOUNT + ".roster.last-roster", {
        "rows": [
            {"id": "b1", "name": "Content Creator", "isGroup": False,
             "lastActivityAt": 1792947000000, "unreadCount": 0,
             "lastEntry": {"kind": "text", "text": "PRIVATE MESSAGE TEXT"}},
            {"id": "b2", "name": "Content Analytics", "isGroup": False,
             "lastActivityAt": 1792950000000, "unreadCount": 4,
             "lastEntry": {"kind": "text", "text": "ALSO PRIVATE"}},
            {"id": "g1", "name": "Tokentelemetry", "isGroup": True,
             "lastActivityAt": 1792900000000, "unreadCount": 0,
             "memberIds": ["b1", "b2"]},
        ],
    })


def _bot_section(doc, title):
    return next(s for s in doc["sections"] if s["title"] == title)


def test_bot_only_machine_still_reports_a_panel(bot_env):
    _usage_slice(bot_env)
    doc = grok_panel.build(with_disk=False)

    assert doc["installed"] is True
    assert doc["root"].endswith(".grokbot")
    assert not any(s.get("kind") == "memory" for s in doc["not_available"])


def test_neither_store_means_not_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(grok_panel, "GROK_DIR", tmp_path / "nope-cli")
    monkeypatch.setattr(grok_panel, "GROK_BOT_DIR", tmp_path / "nope-bot")
    monkeypatch.setattr(grok_panel, "GROK_BOT_APP_DIR", tmp_path / "nope-app")
    assert grok_panel.build(with_disk=False)["installed"] is False


def test_weekly_usage_slice_becomes_the_meter(bot_env):
    _usage_slice(bot_env)
    doc = grok_panel.build(with_disk=False)

    usage = _bot_section(doc, "Grok Bot plan usage")
    assert usage["kind"] == "meter"
    assert usage["meters"][0]["pct"] == 4.4
    assert usage["meters"][0]["resets_at"].startswith("2026-11-01")
    assert any(f["label"] == "Plan" and f["value"] == "SuperGrok"
               for f in usage["fields"])


def test_bot_and_live_meters_are_reported_separately(bot_env):
    """The CLI and the desktop app can be on different billing windows.

    On this machine the live quota resets Oct 30 (1% used) while the app's
    cache resets Nov 1 (4.4% used), so merging them would invent a number.
    """
    _usage_slice(bot_env)
    (bot_env["data"] / "quotas.json").write_text(json.dumps({
        "providers": {"grok": {
            "fetchedAt": "2026-10-22T17:27:17+00:00",
            "resources": {"weekly": {
                "used": 20.0, "limit": 100.0,
                "resetsAt": "2026-10-23T15:52:37+00:00",
            }},
            "plan": "SuperGrok",
        }},
    }), encoding="utf-8")

    doc = grok_panel.build(with_disk=False)
    meters = {s["title"]: s["meters"][0]["pct"]
              for s in doc["sections"] if s["kind"] == "meter"}

    assert meters == {"Plan usage": 20.0, "Grok Bot plan usage": 4.4}


def test_live_quota_is_not_hidden_by_a_newer_bot_meter(bot_env):
    _usage_slice(bot_env)
    (bot_env["data"] / "quotas.json").write_text(json.dumps({
        "providers": {"grok": {
            "fetchedAt": "2099-01-01T00:00:00+00:00",
            "resources": {"weekly": {
                "used": 12.0, "limit": 100.0,
                "resetsAt": "2099-01-08T00:00:00+00:00",
            }},
            "plan": "SuperGrok",
        }},
    }), encoding="utf-8")

    doc = grok_panel.build(with_disk=False)
    meters = {s["title"]: s["meters"][0]["pct"]
              for s in doc["sections"] if s["kind"] == "meter"}

    assert meters == {"Plan usage": 12.0, "Grok Bot plan usage": 4.4}


def test_newer_bot_meter_supersedes_stale_cli_billing_record(bot_env):
    """The CLI log is only written when `grok` runs; the bot cache is fresher."""
    _usage_slice(bot_env)
    (bot_env["cli"] / "logs").mkdir(parents=True)
    (bot_env["cli"] / "logs" / "unified.jsonl").write_text(json.dumps({
        "msg": grok_panel.BILLING_MSG,
        "ts": "2026-10-17T09:48:34.801Z",
        "ctx": {"config": {"creditUsagePercent": 14.0,
                           "currentPeriod": {"type": "USAGE_PERIOD_TYPE_WEEKLY",
                                             "end": "2026-10-23T15:52:37Z"}},
                "subscriptionTier": "SuperGrok"},
    }) + "\n", encoding="utf-8")
    usage = bot_env["slices"] / _blob_name(ACCOUNT + ".weekly-usage.cache")
    stamp = 1792947717  # 2026-10-25, after the CLI record
    os.utime(usage, (stamp, stamp))

    doc = grok_panel.build(with_disk=False)
    titles = [s["title"] for s in doc["sections"] if s["kind"] == "meter"]

    assert titles == ["Grok Bot plan usage"]


def test_roster_rows_are_sorted_and_never_include_message_text(bot_env):
    _roster_slice(bot_env)
    doc = grok_panel.build(with_disk=False)

    roster = _bot_section(doc, "Bot agents")
    assert [r[0] for r in roster["rows"]] == [
        "Content Analytics", "Content Creator", "Tokentelemetry"]
    assert roster["rows"][0][3] == 4
    assert roster["rows"][2][1] == "group"
    serialized = json.dumps(doc)
    assert "PRIVATE MESSAGE TEXT" not in serialized
    assert "ALSO PRIVATE" not in serialized


def test_transcript_slices_are_never_opened(bot_env):
    """A transcript is the same file format in the same directory.

    Its value shape is different (entries, not rows/reading), and it holds raw
    text. Nothing about the panel may pull it in.
    """
    _write_slice(bot_env["slices"], ACCOUNT + ".transcript.replicas.abc", {
        "entries": [{"kind": "message", "role": "user",
                     "content": "TRANSCRIPT SECRET"}],
        "epochHint": 1,
    })
    doc = grok_panel.build(with_disk=False)
    assert "TRANSCRIPT SECRET" not in json.dumps(doc)
    assert grok_panel._bot_slices().get("usage") is None
    assert grok_panel._bot_slices().get("roster") is None


def test_executor_state_and_outages(bot_env):
    now_ms = int(time.time() * 1000)
    (bot_env["app"] / "desktop-status.json").write_text(json.dumps({
        "appVersion": "0.75.8", "signedIn": True,
    }), encoding="utf-8")
    (bot_env["bot"] / "local-exec-daemon.json").write_text(json.dumps({
        "pid": 4321, "startedAt": now_ms - 60_000, "servingAt": now_ms,
        "inflightCount": 0,
    }), encoding="utf-8")
    (bot_env["bot"] / "local-exec-daemon.log").write_text(
        '{"event":"sand.local_exec_daemon.watch_outage","outcome":"reconnected"}\n'
        "[user-computer-watch] 2026-10-26T00:12:02.530Z connected after 306 ms out (attempts 1)\n",
        encoding="utf-8")

    doc = grok_panel.build(with_disk=False)
    executor = _bot_section(doc, "Local executor")
    fields = {f["label"]: f["value"] for f in executor["fields"]}

    assert fields["Executor"] == "running"
    assert fields["App version"] == "0.75.8"
    assert fields["In flight"] == 0
    assert fields["Recent watch outages"] == 1
    assert fields["Last reconnect"].startswith("2026-10-26T00:12:02")


def test_storage_section_counts_both_stores(bot_env):
    (bot_env["bot"] / "local-exec-daemon.log").write_bytes(b"x" * 2048)
    doc = grok_panel.build(with_disk=False)
    storage = _bot_section(doc, "Grok Bot storage")
    locations = [row[0] for row in storage["rows"]]
    assert any(".grokbot" in loc for loc in locations)
    assert any("Grok Bot" in loc for loc in locations)


def test_blob_key_decodes_to_the_storage_key():
    key = ACCOUNT + ".weekly-usage.cache"
    assert grok_panel._blob_key(_blob_name(key)) == key
    assert grok_panel._blob_key("not-a-blob") is None
    assert grok_panel._blob_key("!!!!.blob") is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
