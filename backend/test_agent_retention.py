"""Tests for per-agent retention metadata + TT archive opt-in flags.

The Settings page surfaces each agent's real cleanup window, so the values must
be correct: Claude Code's is read from the user's own settings.json and falls
back to the documented 30-day default. Also pins the archive opt-in roundtrip.

No pytest in the venv — run directly:  python backend/test_agent_retention.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))

_VAR = "TOKENTELEMETRY_DATA_DIR"


def _fresh_module():
    """Reimport agent_retention against a fresh data dir (RETENTION_FILE is
    resolved at import time)."""
    os.environ[_VAR] = tempfile.mkdtemp(prefix="tt-ret-")
    import importlib
    import agent_retention
    importlib.reload(agent_retention)
    return agent_retention


def test_claude_default_is_30_when_no_settings():
    from pathlib import Path
    ar = _fresh_module()
    ar.HOME = Path(tempfile.mkdtemp(prefix="tt-home-"))  # no ~/.claude/settings.json here
    info = ar.describe_agents(["claude"])["claude"]
    assert info["default_days"] == 30
    assert info["effective_days"] == 30
    assert info["detected_override"] is None


def test_claude_reads_cleanup_period_days_override():
    ar = _fresh_module()
    home = tempfile.mkdtemp(prefix="tt-home-")
    cdir = os.path.join(home, ".claude")
    os.makedirs(cdir)
    with open(os.path.join(cdir, "settings.json"), "w") as f:
        json.dump({"cleanupPeriodDays": 3650}, f)
    from pathlib import Path
    ar.HOME = Path(home)
    info = ar.describe_agents(["claude"])["claude"]
    assert info["detected_override"] == 3650
    assert info["effective_days"] == 3650, "user's real window must win over the default"


def test_codex_has_no_auto_cleanup():
    ar = _fresh_module()
    info = ar.describe_agents(["codex"])["codex"]
    assert info["default_days"] is None
    assert info["effective_days"] is None


def test_archive_optin_roundtrips_and_gates_unarchivable():
    ar = _fresh_module()
    # claude is archivable -> enabling it sticks.
    ar.set_archive("claude", True)
    assert ar.archive_enabled("claude") is True
    ar.set_archive("claude", False)
    assert ar.archive_enabled("claude") is False
    # hermes isn't archivable -> archive_enabled stays False even if flagged.
    ar.set_archive("hermes", True)
    assert ar.archive_enabled("hermes") is False
    assert ar.describe_agents(["hermes"])["hermes"]["archivable"] is False


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
