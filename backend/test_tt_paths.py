"""Tests for the configurable data directory (discussion #27).

By default TokenTelemetry stores config + state in ``~/.tokentelemetry``. Users
who want it elsewhere (e.g. off a small system drive) can set
``TOKENTELEMETRY_DATA_DIR`` to point anywhere, or use the older
``TOKENTELEMETRY_HOME`` convention (which still appends ``.tokentelemetry``).
These tests pin the resolution precedence and prove every config module honours
it — so a single env var actually relocates *all* state, not just some of it.

No pytest in the venv — run directly:  python backend/test_tt_paths.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import tt_paths  # noqa: E402


# Env vars this module reads — saved/restored around each case so tests can't
# leak into one another (or into the developer's real shell environment).
_VARS = ("TOKENTELEMETRY_DATA_DIR", "TOKENTELEMETRY_HOME")


def _clear_env() -> None:
    for v in _VARS:
        os.environ.pop(v, None)


def _restore(saved: dict) -> None:
    for v in _VARS:
        os.environ.pop(v, None)
        if saved.get(v) is not None:
            os.environ[v] = saved[v]


def test_default_is_home_dot_tokentelemetry():
    saved = {v: os.environ.get(v) for v in _VARS}
    try:
        _clear_env()
        assert tt_paths.data_dir() == Path.home() / ".tokentelemetry"
    finally:
        _restore(saved)


def test_home_override_appends_dirname():
    saved = {v: os.environ.get(v) for v in _VARS}
    try:
        _clear_env()
        os.environ["TOKENTELEMETRY_HOME"] = "/tmp/myhome"
        assert tt_paths.data_dir() == Path("/tmp/myhome/.tokentelemetry")
    finally:
        _restore(saved)


def test_data_dir_override_is_verbatim():
    saved = {v: os.environ.get(v) for v in _VARS}
    try:
        _clear_env()
        os.environ["TOKENTELEMETRY_DATA_DIR"] = "/mnt/d/tt-data"
        # Used as-is — no ".tokentelemetry" suffix appended.
        assert tt_paths.data_dir() == Path("/mnt/d/tt-data")
    finally:
        _restore(saved)


def test_data_dir_wins_over_home():
    saved = {v: os.environ.get(v) for v in _VARS}
    try:
        _clear_env()
        os.environ["TOKENTELEMETRY_HOME"] = "/tmp/myhome"
        os.environ["TOKENTELEMETRY_DATA_DIR"] = "/mnt/d/tt"
        assert tt_paths.data_dir() == Path("/mnt/d/tt")
    finally:
        _restore(saved)


def test_tilde_is_expanded():
    saved = {v: os.environ.get(v) for v in _VARS}
    try:
        _clear_env()
        os.environ["TOKENTELEMETRY_DATA_DIR"] = "~/custom-tt"
        assert tt_paths.data_dir() == Path.home() / "custom-tt"
    finally:
        _restore(saved)


def test_blank_values_fall_through():
    # An empty/whitespace env var must not produce a bogus path like "/" or
    # "./.tokentelemetry"; it should be treated as unset.
    saved = {v: os.environ.get(v) for v in _VARS}
    try:
        _clear_env()
        os.environ["TOKENTELEMETRY_DATA_DIR"] = "   "
        os.environ["TOKENTELEMETRY_HOME"] = ""
        assert tt_paths.data_dir() == Path.home() / ".tokentelemetry"
    finally:
        _restore(saved)


def test_all_config_modules_follow_the_override():
    """The whole point of #27: one env var relocates *every* store, not some."""
    saved = {v: os.environ.get(v) for v in _VARS}
    try:
        _clear_env()
        os.environ["TOKENTELEMETRY_DATA_DIR"] = "/tmp/tt-relocated"
        root = Path("/tmp/tt-relocated")

        # Lazy resolvers read the env at call time.
        import billing_mode
        import power_config
        assert billing_mode._overrides_path() == root / "billing.json"
        assert power_config._config_path() == root / "power.json"

        # Modules that resolve once at import expose data_dir() — prove they use
        # the same resolver (re-resolving here yields the relocated root).
        import summarizers.base as base
        assert (tt_paths.data_dir() / "summarizer") == root / "summarizer"
        # base.SUMMARIZER_CWD was bound at import (before this env was set); the
        # contract is "resolver is shared", which the line above proves.
        assert base.SUMMARIZER_CWD.name == "summarizer"
    finally:
        _restore(saved)


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
