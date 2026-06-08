"""Tests for per-agent billing-mode detection + overrides (billing_mode.py)."""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import billing_mode as bm


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Isolated HOME for both agent-dir detection and the overrides file."""
    monkeypatch.setenv("TOKENTELEMETRY_HOME", str(tmp_path))
    # Clear any real env keys that would leak into detection.
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "GEMINI_API_KEY",
              "GOOGLE_API_KEY", "DASHSCOPE_API_KEY", "QWEN_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    return tmp_path


# --- detection -------------------------------------------------------------
def test_codex_auth_mode_chatgpt_is_subscription(home):
    d = home / ".codex"; d.mkdir()
    (d / "auth.json").write_text(json.dumps(
        {"auth_mode": "chatgpt", "OPENAI_API_KEY": "", "tokens": {"a": 1}}))
    assert bm.detect_mode("codex", home) == "subscription"


def test_codex_api_key_is_api(home):
    d = home / ".codex"; d.mkdir()
    (d / "auth.json").write_text(json.dumps({"OPENAI_API_KEY": "sk-xxx"}))
    assert bm.detect_mode("codex", home) == "api"


def test_codex_missing_file_is_none(home):
    assert bm.detect_mode("codex", home) is None


def test_gemini_oauth_is_subscription(home):
    d = home / ".gemini"; d.mkdir()
    (d / "oauth_creds.json").write_text("{}")
    assert bm.detect_mode("gemini", home) == "subscription"


def test_gemini_api_key_env_wins_over_oauth(home, monkeypatch):
    d = home / ".gemini"; d.mkdir()
    (d / "oauth_creds.json").write_text("{}")
    monkeypatch.setenv("GEMINI_API_KEY", "xxx")
    assert bm.detect_mode("gemini", home) == "api"


def test_qwen_oauth_is_subscription(home):
    d = home / ".qwen"; d.mkdir()
    (d / "oauth_creds.json").write_text("{}")
    assert bm.detect_mode("qwen", home) == "subscription"


def test_claude_env_key_is_api_else_none(home, monkeypatch):
    assert bm.detect_mode("claude", home) is None  # keychain → unsure
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-xxx")
    assert bm.detect_mode("claude", home) == "api"


def test_unknown_agent_has_no_detector(home):
    assert bm.detect_mode("grok", home) is None


# --- resolution order ------------------------------------------------------
def test_default_when_no_signal(home):
    r = bm.get_mode("copilot", home)
    assert r["mode"] == "subscription" and r["source"] == "default"


def test_detected_beats_default(home):
    d = home / ".codex"; d.mkdir()
    (d / "auth.json").write_text(json.dumps({"OPENAI_API_KEY": "sk-xxx"}))
    r = bm.get_mode("codex", home)
    assert r["mode"] == "api" and r["source"] == "detected" and r["detected"] == "api"


def test_user_override_beats_detection(home):
    d = home / ".codex"; d.mkdir()
    (d / "auth.json").write_text(json.dumps({"OPENAI_API_KEY": "sk-xxx"}))  # detects api
    bm.save_override("codex", "subscription")
    r = bm.get_mode("codex", home)
    assert r["mode"] == "subscription" and r["source"] == "user"
    assert r["detected"] == "api"  # detection still reported for transparency


# --- overrides persistence -------------------------------------------------
def test_save_and_clear_override(home):
    bm.save_override("claude", "api")
    assert bm.load_overrides() == {"claude": "api"}
    bm.save_override("claude", None)  # clear → revert to auto
    assert bm.load_overrides() == {}


def test_garbage_overrides_file_is_ignored(home):
    p = home / ".tokentelemetry"; p.mkdir()
    (p / "billing.json").write_text("not json {{{")
    assert bm.load_overrides() == {}


def test_invalid_mode_in_file_is_filtered(home):
    p = home / ".tokentelemetry"; p.mkdir()
    (p / "billing.json").write_text(json.dumps({"claude": "bogus", "codex": "api"}))
    assert bm.load_overrides() == {"codex": "api"}


def test_get_all_covers_each_agent(home):
    agents = ["claude", "codex", "copilot", "grok"]
    allm = bm.get_all(agents, home)
    assert set(allm) == set(agents)
    assert all(allm[a]["mode"] in bm.MODES for a in agents)
