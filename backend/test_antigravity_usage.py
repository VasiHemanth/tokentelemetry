"""Tests for Antigravity's recorded token usage (antigravity_usage.py) and the scan
paths that use it.

Antigravity keeps each conversation as ~/.gemini/antigravity*/conversations/<id>.db,
whose gen_metadata table holds one protobuf row per model call. These tests build
those rows byte for byte, so the field mapping is pinned independently of any real
store: 1.4.{1,2} system prompt + input, 1.4.3 output, 1.4.5 cache reads, 1.19 model
id, 1.21 label, 1.9.4.1 timestamp (or steps.metadata 1.1 on newer builds).

Run: python -m pytest backend/test_antigravity_usage.py
"""
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import antigravity_usage as au  # noqa: E402
import main  # noqa: E402

T0 = 1_789_000_000  # 2026-09-10T00:26:40Z
DAY0 = datetime.fromtimestamp(T0, tz=timezone.utc).strftime("%Y-%m-%d")


# --- protobuf builders ---------------------------------------------------------

def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        byte = n & 0x7F
        n >>= 7
        out.append(byte | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _int(num: int, value: int) -> bytes:
    return _varint(num << 3) + _varint(value)


def _bytes(num: int, value) -> bytes:
    value = value.encode() if isinstance(value, str) else value
    return _varint((num << 3) | 2) + _varint(len(value)) + value


def gen_blob(model=None, label=None, sp=0, inp=0, out=0, cache=0, ts=None) -> bytes:
    usage = _int(1, sp) + _int(2, inp) + _int(3, out) + _int(5, cache)
    event = b""
    if model:
        event += _bytes(19, model)
    if label:
        event += _bytes(21, label)
    event += _bytes(4, usage)
    if ts:
        event += _bytes(9, _bytes(4, _int(1, ts)))
    return _bytes(1, event)


def step_meta(ts: int) -> bytes:
    return _bytes(1, _int(1, ts))


def make_db(path: Path, rows, step_metadata=True):
    """rows: [(gen_blob, step_metadata_blob_or_None)], idx = position."""
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE gen_metadata (idx integer PRIMARY KEY, data blob, size integer DEFAULT 0)")
    if step_metadata:
        con.execute("CREATE TABLE steps (idx integer, step_type integer, metadata blob, step_payload blob)")
    else:
        con.execute("CREATE TABLE steps (idx integer, step_payload blob)")
    for i, (blob, meta) in enumerate(rows):
        con.execute("INSERT INTO gen_metadata (idx, data) VALUES (?, ?)", (i, blob))
        if step_metadata:
            con.execute("INSERT INTO steps (idx, metadata) VALUES (?, ?)", (i, meta))
    con.commit()
    con.close()


def known(name: str) -> bool:
    return main._antigravity_price_known(name)


# --- decoding --------------------------------------------------------------------

def test_decode_maps_usage_fields_and_bills_system_prompt_as_input():
    e = au.decode_generation(gen_blob("gemini-3.8-flash", sp=1_318, inp=6_998, out=129, cache=20_380, ts=T0))
    assert e == {"model_id": "gemini-3.8-flash", "label": None,
                 "input": 8_316, "output": 129, "cached": 20_380, "ts": T0}


def test_decode_dates_a_call_from_step_metadata_when_timing_is_absent():
    blob = gen_blob("gemini-3.8-flash", inp=10, out=1)
    assert au.decode_generation(blob) is None, "no timestamp at all must be dropped, not dated from mtime"
    assert au.decode_generation(blob, step_meta(T0))["ts"] == T0


def test_decode_skips_prompt_context_records_but_keeps_labelled_ones():
    # No model, no label, nothing generated: bookkeeping, not a call.
    assert au.decode_generation(gen_blob(sp=1_298, ts=T0)) is None
    # A labelled record carrying only the system prompt is a real (tiny) call.
    labelled = au.decode_generation(gen_blob(label="Gemini 3.1 Pro (Low)", sp=1_298, ts=T0))
    assert labelled["input"] == 1_298
    # Garbage never raises.
    assert au.decode_generation(b"\xff\xff\xff") is None
    assert au.decode_generation(b"") is None


# --- model naming ----------------------------------------------------------------

@pytest.mark.parametrize("model_id,label,expected", [
    # A concrete id the pricing table knows wins.
    ("gemini-3.8-flash", None, "gemini-3.8-flash"),
    # Placeholder ids defer to the label naming the model that served the turn.
    ("gemini-pro-default", "Gemini 3.1 Pro (High)", "gemini-3.1-pro"),
    ("gemini-pro-default", None, "gemini-3.1-pro"),
    # An internal alias always shipped with a Gemini 3.5 Flash label. Fuzzy
    # matching would price it as gemini-3-flash, at a sixth of the rate.
    ("gemini-3-flash-a", "Gemini 3.5 Flash (High)", "gemini-3.5-flash"),
    # Effort and tier variants bill as the base model.
    ("gemini-3.1-pro-low", "Gemini 3.1 Pro (Low)", "gemini-3.1-pro"),
    ("gemini-3.7-flash-tiered", None, "gemini-3.7-flash"),
    # Claude labels put the tier before the version.
    ("claude-opus-4-6-thinking", "Claude Opus 4.6 (Thinking)", "claude-opus-4-6"),
    (None, "Claude Opus 4.6 (Thinking)", "claude-opus-4-6"),
    (None, None, None),
])
def test_canonical_model(model_id, label, expected):
    assert au.canonical_model(model_id, label, known) == expected


def test_canonical_model_never_emits_a_bare_vendor_name():
    # "gemini" alone fuzzy-matches a generic rate in the pricing table.
    assert au.canonical_model("gemini-default", None, known) is None
    assert au.canonical_model(None, "Gemini Something", known) is None


def test_label_versions_keep_gemini_dots_and_use_claude_dashes():
    # The table also holds dashed Gemini keys ("gemini-3-1-pro") priced at zero.
    assert au._from_label("Gemini 3.1 Pro (High)") == "gemini-3.1-pro"
    assert au._from_label("Claude Sonnet 4.5") == "claude-sonnet-4-5"


# --- one database ----------------------------------------------------------------

def test_read_usage_buckets_by_model_and_day_and_skips_oversized_rows(tmp_path):
    db = tmp_path / "antigravity-cli" / "conversations" / "sid.db"
    huge = gen_blob("gemini-3.8-flash", inp=1, ts=T0) + b"\x00" * (au.MAX_BLOB_BYTES + 1)
    make_db(db, [
        (gen_blob("gemini-3.8-flash", inp=100, out=10, cache=1_000, ts=T0), None),
        (gen_blob("gemini-3.8-flash", inp=50, out=5, ts=T0 + 60), None),
        (gen_blob("gemini-pro-default", "Gemini 3.1 Pro (High)", inp=7, out=3), step_meta(T0 + 86_400)),
        (huge, None),
        (gen_blob(sp=1_298, ts=T0), None),  # prompt-context record
    ])
    usage = au.read_usage(db)
    assert usage["calls"] == 3
    assert usage["oversized"] == 1
    assert usage["first_ts"] == T0 and usage["last_ts"] == T0 + 86_400
    flash = [b for b in usage["buckets"] if b["model_id"] == "gemini-3.8-flash"]
    assert flash == [{"model_id": "gemini-3.8-flash", "label": None, "day": DAY0,
                      "input": 150, "output": 15, "cached": 1_000, "calls": 2}]


def test_read_usage_sees_a_live_session_still_in_the_wal(tmp_path):
    """A running session appends to <id>.db-wal before anything reaches <id>.db."""
    db = tmp_path / "conversations" / "live.db"
    make_db(db, [(gen_blob("gemini-3.8-flash", inp=1, ts=T0), None)])
    writer = sqlite3.connect(db)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("PRAGMA wal_autocheckpoint=0")
    writer.execute("INSERT INTO gen_metadata (idx, data) VALUES (1, ?)",
                   (gen_blob("gemini-3.8-flash", inp=2, ts=T0),))
    writer.commit()
    try:
        assert Path(str(db) + "-wal").stat().st_size > 0
        assert au.read_usage(db)["calls"] == 2
        assert au.source_mtime(db) >= db.stat().st_mtime
    finally:
        writer.close()


def test_read_usage_returns_none_without_gen_metadata(tmp_path):
    db = tmp_path / "old.db"
    sqlite3.connect(db).execute("CREATE TABLE other (x)").connection.close()
    assert au.read_usage(db) is None
    assert au.read_usage(tmp_path / "missing.db") is None


def test_summarize_prices_each_bucket_and_never_prices_an_unnamed_call():
    usage = {"buckets": [
        {"model_id": "gemini-3.8-flash", "label": None, "day": DAY0,
         "input": 1_000_000, "output": 0, "cached": 0, "calls": 1},
        {"model_id": None, "label": None, "day": DAY0,
         "input": 500, "output": 0, "cached": 0, "calls": 1},
    ]}
    calls = []

    def price(model, inp, out, cached, day):
        calls.append((model, inp, out, cached, day))
        return 1.25

    s = au.summarize(usage, price, known)
    assert calls == [("gemini-3.8-flash", 1_000_000, 0, 0, DAY0)]
    assert s["cost"] == 1.25
    assert s["tokens"]["total"] == 1_000_500
    assert s["unpriced_tokens"] == 500
    assert s["model"] == "gemini-3.8-flash"


def test_conversation_files_skips_the_backup_mirror(tmp_path):
    for store in ("antigravity", "antigravity-cli", "antigravity-backup"):
        make_db(tmp_path / store / "conversations" / f"{store}-only.db", [])
    make_db(tmp_path / "antigravity-backup" / "conversations" / "shared.db", [])
    found = au.conversation_files(tmp_path)
    assert set(found) == {"antigravity-only", "antigravity-cli-only"}


# --- the scan --------------------------------------------------------------------

def _summary_db(store: Path, rows):
    store.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(store / "conversation_summaries.db")
    con.execute("CREATE TABLE conversation_summaries (conversation_id text, title text, preview text,"
                " step_count integer, workspace_uris text, last_modified_time text)")
    con.executemany("INSERT INTO conversation_summaries VALUES (?,?,?,?,?,?)", rows)
    con.commit()
    con.close()


def _scan(gem: Path, data: Path):
    """Run the full session scan with Antigravity pointed at `gem` and every
    other agent at an empty directory."""
    nowhere = gem.parent / "nowhere"
    saved = {}
    for attr in dir(main):
        if not (attr.endswith(("_DIR", "_DIRS", "_BASE", "_STORAGE")) and attr.isupper()):
            continue
        val = getattr(main, attr)
        if isinstance(val, Path):
            saved[attr] = val
            setattr(main, attr, nowhere)
        elif isinstance(val, list) and val and all(isinstance(v, Path) for v in val):
            saved[attr] = val
            setattr(main, attr, [nowhere])
    sources = [(gem / "antigravity-cli" / "brain", "cli"), (gem / "antigravity-ide" / "brain", "ide"),
               (gem / "antigravity" / "brain", "app")]
    saved.setdefault("GEMINI_DIR", main.GEMINI_DIR)
    saved["ANTIGRAVITY_BRAIN_SOURCES"] = main.ANTIGRAVITY_BRAIN_SOURCES
    saved["ANTIGRAVITY_BRAIN_DIRS"] = main.ANTIGRAVITY_BRAIN_DIRS
    saved["ANTIGRAVITY_CLI_DIR"] = main.ANTIGRAVITY_CLI_DIR
    main.GEMINI_DIR = gem
    main.ANTIGRAVITY_BRAIN_SOURCES = sources
    main.ANTIGRAVITY_BRAIN_DIRS = [d for d, _ in sources]
    main.ANTIGRAVITY_CLI_DIR = gem / "antigravity-cli"
    prior = os.environ.get("TOKENTELEMETRY_DATA_DIR")
    os.environ["TOKENTELEMETRY_DATA_DIR"] = str(data)
    try:
        return [s for s in main._scan_sessions_sync() if s.get("agent") == "antigravity"]
    finally:
        for attr, val in saved.items():
            setattr(main, attr, val)
        if prior is None:
            os.environ.pop("TOKENTELEMETRY_DATA_DIR", None)
        else:
            os.environ["TOKENTELEMETRY_DATA_DIR"] = prior


def _transcript_session(brain: Path, sid: str):
    logs = brain / sid / ".system_generated" / "logs"
    logs.mkdir(parents=True)
    (logs / "transcript.jsonl").write_text(
        json.dumps({"source": "USER", "content": "x" * 400}) + "\n", encoding="utf-8")


def test_scan_finds_antigravity_without_gemini_cli_history():
    """No ~/.gemini/projects.json (the Gemini CLI's file) must not hide Antigravity.

    The dedup set was created only inside the Gemini branch, so on a machine
    without Gemini CLI history every brain/ session raised NameError and was
    silently skipped.
    """
    with tempfile.TemporaryDirectory() as d:
        gem = Path(d) / "gemini"
        _transcript_session(gem / "antigravity-cli" / "brain", "brain-only")
        assert not (gem / "projects.json").exists()
        ids = [s["id"] for s in _scan(gem, Path(d) / "data")]
        assert ids == ["brain-only"]


def test_scan_replaces_estimates_with_recorded_usage_and_adds_db_only_sessions():
    with tempfile.TemporaryDirectory() as d:
        gem = Path(d) / "gemini"
        cli = gem / "antigravity-cli"
        # Has a brain/ transcript (so it used to be a characters/4 estimate at $0)
        # and a database recording the real calls.
        _transcript_session(cli / "brain", "estimated")
        make_db(cli / "conversations" / "estimated.db", [
            (gen_blob("gemini-3.8-flash", inp=1_000_000, out=100_000, cache=2_000_000, ts=T0), None)])
        # A database and nothing in brain/: invisible before.
        make_db(gem / "antigravity-ide" / "conversations" / "db-only.db", [
            (gen_blob("gemini-pro-default", "Gemini 3.1 Pro (High)", inp=10_000, out=500), step_meta(T0))])

        by_id = {s["id"]: s for s in _scan(gem, Path(d) / "data")}

        est = by_id["estimated"]
        assert est["tokens"]["input"] == 1_000_000
        assert est["tokens"]["output"] == 100_000
        assert est["tokens"]["cached"] == 2_000_000
        assert est["tokens"]["total"] == 3_100_000
        assert est["model"] == "gemini-3.8-flash"
        expected = main.calculate_cost("gemini-3.8-flash", 1_000_000, 100_000, 2_000_000, at=DAY0)
        assert est["cost"] == pytest.approx(expected) and est["cost"] > 0
        assert est["timestamp"] == datetime.fromtimestamp(T0, tz=timezone.utc)

        only = by_id["db-only"]
        assert only["tokens"]["total"] == 10_500
        assert only["model"] == "gemini-3.1-pro"
        assert only["antigravity_source"] == "ide"
        assert only["cost"] > 0


def test_scan_lists_indexed_pb_sessions_with_unknown_usage():
    """Older .pb sessions have no readable usage but are real: Antigravity's own
    index lists them with a title, a workspace and a step count."""
    with tempfile.TemporaryDirectory() as d:
        gem = Path(d) / "gemini"
        _summary_db(gem / "antigravity", [
            ("old-pb", "Building Product Demo Video", "", 12,
             json.dumps(["file:///Users/dev/code/demo"]), "2026-05-31T10:00:00Z"),
            ("empty", "", "", 0, "[]", "2026-05-31T10:00:00Z"),
        ])
        (gem / "antigravity" / "conversations").mkdir(parents=True)
        (gem / "antigravity" / "conversations" / "old-pb.pb").write_bytes(b"\x00")

        by_id = {s["id"]: s for s in _scan(gem, Path(d) / "data")}
        assert set(by_id) == {"old-pb"}, "a zero-step entry is not a session"
        s = by_id["old-pb"]
        assert s["project"] == "/Users/dev/code/demo"
        assert s["tokens"]["total"] == 0 and s["cost"] == 0.0
        assert s["antigravity_source"] == "app"
