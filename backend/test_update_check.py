"""Tests for the update-check preference + /version gating (issue #64).

The dashboard makes one outbound call — an optional update check to GitHub.
Users must be able to turn it off in-app (a persisted preference) or enforce it
off via the TT_NO_UPDATE_CHECK env var (which wins). These tests pin the
preference store, the gating precedence, and the endpoint contract.

No pytest in the venv — run directly:  python backend/test_update_check.py
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import harness_config  # noqa: E402


def _isolate_prefs() -> None:
    """Point harness_config at a throwaway dir so tests never touch real prefs."""
    d = tempfile.mkdtemp()
    harness_config.HARNESS_DIR = Path(d)
    harness_config.PREFERENCES_FILE = Path(d) / "preferences.json"
    harness_config.VERSION_FILE = Path(d) / "VERSION"


def test_preferences_default_and_roundtrip():
    _isolate_prefs()
    assert harness_config.load_preferences() == {"update_check": True}
    assert harness_config.save_preferences({"update_check": False})["update_check"] is False
    assert harness_config.load_preferences()["update_check"] is False


def test_preferences_rejects_unknown_keys_and_bad_types():
    _isolate_prefs()
    # Unknown keys never persist; wrong-typed values are skipped (stay default).
    saved = harness_config.save_preferences({"bogus": 123, "update_check": "yes"})
    assert "bogus" not in saved
    assert saved["update_check"] is True  # string rejected -> default kept
    # A malformed file degrades to defaults, never raises.
    harness_config.PREFERENCES_FILE.write_text("not valid json {")
    assert harness_config.load_preferences() == {"update_check": True}


def test_version_gating_precedence():
    _isolate_prefs()
    import main
    # main caches the imported symbol; point it at the isolated store too.
    main.load_preferences = harness_config.load_preferences

    os.environ.pop("TT_NO_UPDATE_CHECK", None)
    harness_config.save_preferences({"update_check": True})
    assert main._update_check_enabled() is True

    harness_config.save_preferences({"update_check": False})
    assert main._update_check_enabled() is False

    # Env var wins over an enabled preference.
    harness_config.save_preferences({"update_check": True})
    os.environ["TT_NO_UPDATE_CHECK"] = "1"
    try:
        assert main._update_check_enabled() is False
        # /version short-circuits to a disabled payload (no network).
        v = asyncio.run(main.get_version())
        assert v["source"] == "disabled" and v["behind"] is False
    finally:
        os.environ.pop("TT_NO_UPDATE_CHECK", None)


def test_endpoint_contract():
    _isolate_prefs()
    import main
    main.load_preferences = harness_config.load_preferences
    from fastapi import HTTPException

    os.environ.pop("TT_NO_UPDATE_CHECK", None)
    assert asyncio.run(main.get_update_check()) == {
        "enabled": True, "env_forced_off": False, "effective": True}
    assert asyncio.run(main.post_update_check({"enabled": False})) == {
        "enabled": False, "env_forced_off": False, "effective": False}
    assert asyncio.run(main.get_update_check())["enabled"] is False
    # Non-boolean payload is rejected.
    try:
        asyncio.run(main.post_update_check({"enabled": "nope"}))
        raise AssertionError("expected 400 for non-boolean payload")
    except HTTPException as e:
        assert e.status_code == 400


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
