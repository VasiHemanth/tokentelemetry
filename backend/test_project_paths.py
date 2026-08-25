"""Regression tests: one real folder must yield ONE /projects card.

Agent CLIs log cwd in their own separator style — some emit `C:\\a\\b`,
others `C:/a/b`, a few mix both — and projects were grouped by exact string,
so a single Windows workspace could surface as duplicate cards. These tests
pin canonicalisation at the scan choke point plus every identity boundary
that reads persisted config (hidden projects, budgets).

Run:  python backend/test_project_paths.py   (no pytest needed)
      pytest backend/test_project_paths.py   (also works)
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import harness_config  # noqa: E402
import main  # noqa: E402
from tt_paths import canonical_project  # noqa: E402

SID_BACKSLASH = "11111111-aaaa-bbbb-cccc-000000000001"
SID_FORWARD = "22222222-aaaa-bbbb-cccc-000000000002"
PROJ_BACKSLASH = "C:\\Users\\dev\\proj"
PROJ_FORWARD = "C:/Users/dev/proj"
CANONICAL = "C:/Users/dev/proj"


def _write_claude_session(claude_dir: Path, sid: str, cwd: str) -> None:
    """Minimal Claude Code transcript whose first line logs `cwd` verbatim."""
    p_dir = claude_dir / "projects" / ("proj-" + sid[:8])
    p_dir.mkdir(parents=True)
    (p_dir / f"{sid}.jsonl").write_text(
        json.dumps({"type": "user", "timestamp": "2026-08-01T10:00:00Z",
                    "cwd": cwd,
                    "message": {"content": "hello"}}) + "\n",
        encoding="utf-8",
    )


def _hermetic(tmp: str):
    """Point every agent store at tmp so the scan reads nothing real.

    Mirrors the `scan_env` fixture used by other suites, minus pytest.
    Returns a restore callable."""
    missing = Path(tmp) / "missing"
    saved_attrs = {}
    paths = {
        "CODEX_DIR": missing / "codex", "GEMINI_DIR": missing / "gemini",
        "QWEN_DIR": missing / "qwen", "VIBE_DIR": missing / "vibe",
        "OLLAMA_DIR": missing / "ollama", "GROK_SESSIONS_DIR": missing / "grok-sessions",
        "GROK_UNIFIED_LOG": missing / "grok-unified.jsonl",
        "VSCODE_STORAGE": missing / "vscode", "CURSOR_STORAGE": missing / "cursor-storage",
        "COPILOT_CLI_DIR": missing / "copilot-cli", "ANTIGRAVITY_BRAIN_DIR": missing / "ag-brain",
        "ANTIGRAVITY_CLI_DIR": missing / "ag-cli", "HERMES_DIR": missing / "hermes",
        "PI_SESSIONS_DIR": missing / "pi", "CLAUDE_DIR": Path(tmp) / ".claude",
        "CURSOR_DIR": Path(tmp) / ".cursor", "OPENCODE_DB": missing / "opencode.db",
        "HERMES_DB": missing / "hermes-state.db",
        "HERMES_PROFILES_DIR": missing / "hermes-profiles",
        "PROJECT_ALIASES_FILE": Path(tmp) / "aliases.json",
        # Stores the published_artifacts scan_env fixture does not patch; on a
        # dev machine they point at real agent data and would slow the scan
        # down (or leak rows in). Assertions filter to our session ids anyway.
        "CLINE_DIR": missing / "cline", "CLINE_VSCODE_DIR": missing / "cline-vscode",
        "MUSE_SESSIONS_DIR": missing / "muse", "PRIME_SESSIONS_DIR": missing / "prime",
        "DSH_SESSIONS_DIR": missing / "dsh",
    }
    for attr, val in paths.items():
        saved_attrs[attr] = getattr(main, attr)
        setattr(main, attr, val)
    for attr in ("ANTIGRAVITY_BRAIN_SOURCES", "ANTIGRAVITY_BRAIN_DIRS"):
        saved_attrs[attr] = getattr(main, attr)
        setattr(main, attr, [])
    saved_attrs["SMALLCODE_EXTRA_ROOTS"] = main.SMALLCODE_EXTRA_ROOTS
    main.SMALLCODE_EXTRA_ROOTS = []
    saved_attrs["_antigravity_cli_meta"] = main._antigravity_cli_meta
    main._antigravity_cli_meta = lambda *a, **k: {}
    saved_env = os.environ.get("TOKENTELEMETRY_DATA_DIR")
    os.environ["TOKENTELEMETRY_DATA_DIR"] = str(Path(tmp) / "tt_data")

    def _restore():
        for attr, val in saved_attrs.items():
            setattr(main, attr, val)
        if saved_env is None:
            os.environ.pop("TOKENTELEMETRY_DATA_DIR", None)
        else:
            os.environ["TOKENTELEMETRY_DATA_DIR"] = saved_env

    return _restore


def _seed_two_separator_variants(claude_dir: Path):
    """Same folder, logged by two sessions with opposite separator styles."""
    _write_claude_session(claude_dir, SID_BACKSLASH, PROJ_BACKSLASH)
    _write_claude_session(claude_dir, SID_FORWARD, PROJ_FORWARD)


# ---------------------------------------------------------------------------
# Pure helper
# ---------------------------------------------------------------------------

def test_canonical_project_folds_windows_separators():
    f = canonical_project
    assert f(PROJ_BACKSLASH) == CANONICAL
    assert f(PROJ_FORWARD) == CANONICAL          # already canonical
    assert f("C:\\Users\\dev\\proj\\") == CANONICAL   # mixed style + trailing sep
    assert f("\\\\server\\share\\proj") == "//server/share/proj"  # UNC


def test_canonical_project_trims_trailing_posix_sep():
    f = canonical_project
    assert f("/tmp/proj/") == "/tmp/proj"
    assert f("/tmp/proj") == "/tmp/proj"


def test_canonical_project_keeps_filesystem_root():
    # A lone separator must not collapse to "" (would corrupt the value).
    f = canonical_project
    assert f("/") == "/"
    assert f("//") == "//"


def test_canonical_project_leaves_posix_backslashes_alone():
    # On POSIX a backslash is a legal filename character — rewriting it into
    # "/" would corrupt a perfectly valid directory into two.
    assert canonical_project("/data/weird\\name") == "/data/weird\\name"


def test_canonical_project_passes_sentinels_through():
    f = canonical_project
    assert f("unknown") == "unknown"
    assert f(main.ANTIGRAVITY_UNASSIGNED) == main.ANTIGRAVITY_UNASSIGNED
    assert f("relative/path") == "relative/path"
    assert f("") == ""
    assert f(None) is None


# ---------------------------------------------------------------------------
# End-to-end: scan + /projects rollup
# ---------------------------------------------------------------------------

def test_scan_folds_separator_variants_into_one_identity():
    with tempfile.TemporaryDirectory() as d:
        restore = _hermetic(d)
        try:
            _seed_two_separator_variants(Path(d) / ".claude")
            mine_ids = {SID_BACKSLASH, SID_FORWARD}
            projs = {s["project"] for s in main._scan_sessions_sync()
                     if s["agent"] == "claude" and s["id"] in mine_ids}
            assert len(projs) == 1, f"separator variants split the project: {projs}"
            assert projs == {CANONICAL}
        finally:
            restore()


def test_separator_variants_yield_single_card():
    with tempfile.TemporaryDirectory() as d:
        restore = _hermetic(d)
        try:
            claude_dir = Path(d) / ".claude"
            _seed_two_separator_variants(claude_dir)
            mine_ids = {SID_BACKSLASH, SID_FORWARD}
            sessions = [s for s in main._scan_sessions_sync()
                        if s["agent"] == "claude" and s["id"] in mine_ids]
            assert len(sessions) == 2

            async def fake_cached(fresh=False):
                return sessions

            saved_cached, saved_hidden = main.get_sessions_cached, main.load_hidden
            main.get_sessions_cached = fake_cached
            main.load_hidden = lambda: set()
            try:
                cards = asyncio.run(main.get_projects())
            finally:
                main.get_sessions_cached = saved_cached
                main.load_hidden = saved_hidden

            assert len(cards) == 1, \
                f"expected one card, got {[c['path'] for c in cards]}"
            card = cards[0]
            assert card["path"] == CANONICAL
            assert card["session_count"] == 2
        finally:
            restore()


def test_hidden_entry_in_other_separator_style_still_hides_card():
    # A project hidden before canonicalisation (backslash form) must keep
    # hiding the now forward-slashed card.
    with tempfile.TemporaryDirectory() as d:
        restore = _hermetic(d)
        try:
            claude_dir = Path(d) / ".claude"
            _seed_two_separator_variants(claude_dir)
            mine_ids = {SID_BACKSLASH, SID_FORWARD}
            sessions = [s for s in main._scan_sessions_sync()
                        if s["agent"] == "claude" and s["id"] in mine_ids]

            async def fake_cached(fresh=False):
                return sessions

            saved_cached, saved_hidden = main.get_sessions_cached, main.load_hidden
            main.get_sessions_cached = fake_cached
            main.load_hidden = lambda: {PROJ_BACKSLASH}
            try:
                # include_hidden=True: the default view drops hidden cards,
                # and we want to assert the flag itself.
                cards = asyncio.run(main.get_projects(include_hidden=True))
            finally:
                main.get_sessions_cached = saved_cached
                main.load_hidden = saved_hidden

            assert len(cards) == 1 and cards[0]["hidden"] is True, cards
        finally:
            restore()


def test_unhide_removes_entries_saved_in_any_separator_style(tmp=None):
    # unhide must rebuild the stored set canonically; an exact-discard would
    # leave a pre-canonicalisation backslash entry stuck forever.
    with tempfile.TemporaryDirectory() as d:
        saved_file = harness_config.HIDDEN_FILE
        harness_config.HIDDEN_FILE = Path(d) / "hidden.json"
        try:
            harness_config.hide_project(PROJ_BACKSLASH)
            harness_config.hide_project("/tmp/other")
            updated = harness_config.unhide_project(PROJ_FORWARD)
            assert updated == {"/tmp/other"}
            assert json.loads(harness_config.HIDDEN_FILE.read_text("utf-8")) == ["/tmp/other"]
        finally:
            harness_config.HIDDEN_FILE = saved_file


def test_hide_stores_canonical_form():
    with tempfile.TemporaryDirectory() as d:
        saved_file = harness_config.HIDDEN_FILE
        harness_config.HIDDEN_FILE = Path(d) / "hidden.json"
        try:
            harness_config.hide_project(PROJ_BACKSLASH)
            assert json.loads(harness_config.HIDDEN_FILE.read_text("utf-8")) == [CANONICAL]
        finally:
            harness_config.HIDDEN_FILE = saved_file


def test_budget_filters_match_across_separator_styles():
    # Budgets created before canonicalisation hold raw-style project paths;
    # they must keep matching canonicalised sessions.
    sess = {"project": CANONICAL, "agent": "claude", "model": "m"}
    assert main._session_matches_filters(sess, {"project": PROJ_BACKSLASH})
    assert main._session_matches_filters(sess, {"project": PROJ_FORWARD})
    assert not main._session_matches_filters(
        {"project": "C:/Users/dev/other", "agent": "claude", "model": "m"},
        {"project": PROJ_FORWARD})


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
