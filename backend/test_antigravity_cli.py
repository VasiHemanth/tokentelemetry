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
    (root / "history.jsonl").write_text(
        json.dumps({"conversationId": "sid-db", "workspace": "/proj/alpha"}) + "\n"
        + "this is not json\n"
        + json.dumps({"conversationId": "sid-db", "workspace": "/proj/alpha2"}) + "\n"
        + json.dumps({"display": "no conversation id"}) + "\n"
        + json.dumps({"conversationId": "sid-pb", "workspace": "/proj/beta"}) + "\n",
        encoding="utf-8",
    )
    # .db session with the model embedded in gen_metadata blobs (+ prose noise).
    db = conv / "sid-db.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE gen_metadata (idx integer, data blob)")
    con.execute("INSERT INTO gen_metadata VALUES (?,?)",
                (0, b"\x0aGemini 3.1 Pro (High)\x12 Gemini API) prose \x1aClaude Code"))
    con.execute("INSERT INTO gen_metadata VALUES (?,?)", (1, b"xxGemini 3.1 Pro (High)yy"))
    con.execute("INSERT INTO gen_metadata VALUES (?,?)", (2, None))
    con.commit()
    con.close()
    # .pb-only session: no model embedded -> model unresolved, project still found.
    (conv / "sid-pb.pb").write_bytes(b"raw protobuf bytes with no model display name")
    return root


def test_cli_meta_recovers_model_and_project():
    with tempfile.TemporaryDirectory() as d:
        cli = _make_cli_dir(Path(d))
        meta = main._antigravity_cli_meta(cli)
        assert meta["sid-db"]["project"] == "/proj/alpha2"  # last line wins
        assert meta["sid-db"]["model"] == "Gemini 3.1 Pro (High)"
        assert meta["sid-pb"]["project"] == "/proj/beta"
        assert "model" not in meta["sid-pb"]  # .pb has no embedded display name


def test_model_regex_ignores_prose_and_handles_errors():
    # Strict pattern must not match prose like "Gemini API" or skill names.
    assert main._AG_MODEL_DISPLAY_RE.findall(b"Gemini API) into web apps; Claude Code") == []
    with tempfile.TemporaryDirectory() as d:
        bad = Path(d) / "corrupt.db"
        bad.write_bytes(b"this is not a sqlite database")
        assert main._antigravity_db_model(bad) is None
        # Missing dir must yield an empty map, never raise.
        assert main._antigravity_cli_meta(Path(d) / "does-not-exist") == {}


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
