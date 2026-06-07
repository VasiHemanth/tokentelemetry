"""Tests for Antigravity CLI (`agy`) session enrichment and /artifacts safety.

`agy` saves each session under ~/.gemini/antigravity-cli/ as
conversations/<uuid>.db (SQLite; newer) or <uuid>.pb (protobuf; older), plus a
flat history.jsonl prompt log. The brain/ scanner only reads derived markdown,
so we recover the real model name (from the SQLite trajectory) and the exact
project cwd (from history.jsonl). These tests pin that behaviour and the
/artifacts allow-list hardening.

No pytest in the venv — run directly:  python backend/test_antigravity_cli.py
(also importable by pytest if installed).
"""
import asyncio
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import main  # noqa: E402
from fastapi import HTTPException  # noqa: E402


def _make_cli_dir(root: Path) -> Path:
    """Build a synthetic antigravity-cli store: one .db session, one .pb-only."""
    conv = root / "conversations"
    conv.mkdir(parents=True)
    # history.jsonl: last-wins per conversationId; tolerate junk + missing fields.
    # sid-db's history workspace must LOSE to the .db-derived project below.
    (root / "history.jsonl").write_text(
        json.dumps({"conversationId": "sid-db", "workspace": "/proj/stale-history"}) + "\n"
        + "this is not json\n"
        + json.dumps({"display": "no conversation id"}) + "\n"
        + json.dumps({"conversationId": "sid-pb", "workspace": "/proj/beta"}) + "\n"
        + json.dumps({"conversationId": "sid-chat", "workspace": "/proj/from-history"}) + "\n",
        encoding="utf-8",
    )

    def _make_db(name, gen_blobs, step_blobs):
        db = conv / name
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE gen_metadata (idx integer, data blob)")
        for i, b in enumerate(gen_blobs):
            con.execute("INSERT INTO gen_metadata VALUES (?,?)", (i, b))
        con.execute("CREATE TABLE steps (idx integer, step_payload blob)")
        for i, b in enumerate(step_blobs):
            con.execute("INSERT INTO steps VALUES (?,?)", (i, b))
        con.commit()
        con.close()

    # sid-db: model in gen_metadata (+ prose noise); workspace in tool-call Cwd,
    # appearing more often than a one-off side path so it's the most common.
    _make_db(
        "sid-db.db",
        [b"\x0aGemini 3.1 Pro (High)\x12 Gemini API) prose \x1aClaude Code",
         b"xxGemini 3.1 Pro (High)yy", None],
        [b'{"Cwd":"/work/realproj","toolAction":"x"}',
         b'{"SearchPath":"/work/realproj","Query":"y"}',
         b'{"Cwd":"/work/realproj"}',
         b'{"AbsolutePath":"/work/other/one-off.py"}', None],
    )
    # sid-chat: a pure research session — its only path is under the agent's own
    # ~/.gemini home, so the .db yields no project; history.jsonl fills it.
    _make_db(
        "sid-chat.db",
        [None],
        [(b'{"Cwd":"' + str(main.GEMINI_DIR).encode() + b'/antigravity-cli/scratch"}'),
         b'{"Query":"how do tariffs work"}'],
    )
    # .pb-only session: no model and no extractable cwd -> project from history.
    (conv / "sid-pb.pb").write_bytes(b"raw protobuf bytes with no model or path")
    return root


def test_cli_meta_prefers_db_project_over_history():
    with tempfile.TemporaryDirectory() as d:
        cli = _make_cli_dir(Path(d))
        meta = main._antigravity_cli_meta(cli)
        # .db workspace (permanent) wins over the rolling history.jsonl entry.
        assert meta["sid-db"]["project"] == "/work/realproj"
        assert meta["sid-db"]["model"] == "Gemini 3.1 Pro (High)"


def test_cli_meta_history_fallback_and_internal_paths_ignored():
    with tempfile.TemporaryDirectory() as d:
        cli = _make_cli_dir(Path(d))
        meta = main._antigravity_cli_meta(cli)
        # .pb session has no .db signal -> project comes from history.jsonl.
        assert meta["sid-pb"]["project"] == "/proj/beta"
        assert "model" not in meta["sid-pb"]
        # Research session: ~/.gemini-internal cwd ignored, so history fills it
        # rather than the session being mislabeled with the agent's own path.
        assert meta["sid-chat"]["project"] == "/proj/from-history"


def test_db_meta_regex_and_error_handling():
    # Strict model pattern must not match prose like "Gemini API" or skill names.
    assert main._AG_MODEL_DISPLAY_RE.findall(b"Gemini API) into web apps; Claude Code") == []
    with tempfile.TemporaryDirectory() as d:
        bad = Path(d) / "corrupt.db"
        bad.write_bytes(b"this is not a sqlite database")
        assert main._antigravity_db_meta(bad) == {"model": None, "project": None}
        # Missing dir must yield an empty map, never raise.
        assert main._antigravity_cli_meta(Path(d) / "does-not-exist") == {}


def test_projects_excludes_unassigned_sentinel():
    # The Antigravity "unassigned" bucket must never render as a project card,
    # while real workspaces still do. Sessions themselves remain in /sessions.
    async def fake_sessions():
        common = {"agent": "antigravity", "mcp_tools": [], "subagents": [],
                  "tokens": {}, "cost": 0.0, "plans": [], "has_plan": False}
        return [
            {"project": "/Users/me/Documents/Developer/realproj", **common},
            {"project": main.ANTIGRAVITY_UNASSIGNED, **common},
            {"project": main.ANTIGRAVITY_UNASSIGNED, **common},
        ]
    orig = main.get_sessions_cached
    main.get_sessions_cached = fake_sessions
    try:
        out = asyncio.run(main.get_projects())
    finally:
        main.get_sessions_cached = orig
    paths = [p["path"] for p in out]
    assert main.ANTIGRAVITY_UNASSIGNED not in paths
    assert "/Users/me/Documents/Developer/realproj" in paths


def _call_artifact(path):
    try:
        resp = asyncio.run(main.get_artifact(path))
        return ("ok", getattr(resp, "path", None))
    except HTTPException as e:
        return ("denied", e.status_code)


def test_artifacts_rejects_symlink_escape_and_outside_paths():
    # Outside the allow-list -> 403.
    assert _call_artifact("/etc/hosts")[0] == "denied"
    # Symlink planted inside an allowed dir but pointing out -> 403 (resolved check).
    evil = main.CLAUDE_DIR / "tt_symlink_escape_test"
    try:
        if not evil.exists():
            os.symlink("/etc", evil)
        assert _call_artifact(str(evil / "hosts"))[0] == "denied"
    finally:
        try:
            evil.unlink()
        except OSError:
            pass


def test_artifacts_serves_legit_under_allowlist():
    with tempfile.TemporaryDirectory() as d:
        # GEMINI_DIR is on the allow-list; create a file under it via the real root.
        f = main.GEMINI_DIR / "tt_artifact_serve_test.txt"
        try:
            f.write_text("hello")
            status, served = _call_artifact(str(f))
            assert status == "ok"
            assert served == str(f.resolve())  # serves the resolved path
        finally:
            try:
                f.unlink()
            except OSError:
                pass


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
