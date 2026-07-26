"""Tests for Codex Goal Mode (`/goal`) telemetry.

Mirrors test_loops.py: build throwaway SQLite DBs on disk, then assert on what
`codex_goals.read_goals` returns. The cases that matter are the ones that keep
the feature HONEST (never invent a status, never show a confident zero for a
field the agent cannot record) and the ones that survive Codex's real-world
oddity of shipping two goal DBs at different migration levels.
"""
import sqlite3
from pathlib import Path

import pytest

import codex_goals


# --- helpers ---------------------------------------------------------------

V1_SCHEMA = """
CREATE TABLE thread_goals (
    thread_id TEXT, goal_id TEXT, objective TEXT, status TEXT,
    token_budget INTEGER, tokens_used INTEGER, time_used_seconds INTEGER,
    created_at_ms INTEGER, updated_at_ms INTEGER
);
"""

V2_EXTRA = "CREATE TABLE thread_goal_continuation_deferrals (thread_id TEXT);"


def make_db(path: Path, rows=(), *, v2=False, deferrals=()):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(V1_SCHEMA)
    if v2:
        con.executescript(V2_EXTRA)
        con.executemany("INSERT INTO thread_goal_continuation_deferrals VALUES (?)",
                        [(t,) for t in deferrals])
    con.executemany("INSERT INTO thread_goals VALUES (?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()


def row(thread="t1", goal="g1", objective="ship it", status="active",
        budget=None, used=1000, secs=60, created=1_781_336_283_882,
        updated=1_781_342_475_254):
    return (thread, goal, objective, status, budget, used, secs, created, updated)


@pytest.fixture
def codex_dir(tmp_path):
    return tmp_path / ".codex"


# --- basic mapping ---------------------------------------------------------

def test_reads_a_goal_and_reports_native_counts(codex_dir):
    make_db(codex_dir / "goals_1.sqlite", [row(used=270359, secs=2615)])
    goals = codex_goals.read_goals(codex_dir)
    assert list(goals) == ["t1"]
    g = goals["t1"][0]
    assert g["source"] == "codex"
    assert g["tokens"] == 270359
    assert g["duration_seconds"] == 2615
    assert g["cost_basis"] == "native"
    # Codex wrote the status down, so we must not label it a guess.
    assert g["state_source"] == "reported"


def test_timestamps_become_aware_utc_iso(codex_dir):
    make_db(codex_dir / "goals_1.sqlite", [row()])
    g = codex_goals.read_goals(codex_dir)["t1"][0]
    assert g["created_at"].startswith("2026-06-13T07:38:03")
    assert g["created_at"].endswith("+00:00")


@pytest.mark.parametrize("raw,expected", [
    ("active", "active"), ("running", "active"), ("in_progress", "active"),
    ("paused", "paused"), ("complete", "complete"), ("completed", "complete"),
    ("blocked", "blocked"), ("ACTIVE", "active"), ("  paused ", "paused"),
])
def test_status_vocabulary_is_normalised(codex_dir, raw, expected):
    make_db(codex_dir / "goals_1.sqlite", [row(status=raw)])
    assert codex_goals.read_goals(codex_dir)["t1"][0]["state"] == expected


def test_unknown_status_is_not_guessed_but_raw_is_kept(codex_dir):
    """A status we don't recognise must degrade to "unknown", never to a
    plausible-looking "active"."""
    make_db(codex_dir / "goals_1.sqlite", [row(status="hibernating")])
    g = codex_goals.read_goals(codex_dir)["t1"][0]
    assert g["state"] == "unknown"
    assert g["evidence"]["status_raw"] == "hibernating"


def test_objective_is_truncated_and_flagged(codex_dir):
    make_db(codex_dir / "goals_1.sqlite", [row(objective="x" * 500)])
    g = codex_goals.read_goals(codex_dir)["t1"][0]
    assert len(g["objective"]) == codex_goals.OBJECTIVE_MAX
    assert g["objective_truncated"] is True


def test_short_objective_not_flagged_truncated(codex_dir):
    make_db(codex_dir / "goals_1.sqlite", [row(objective="short")])
    assert codex_goals.read_goals(codex_dir)["t1"][0]["objective_truncated"] is False


# --- the two-DB / migration-level trap -------------------------------------

def test_populated_db_wins_over_empty_one_regardless_of_path(codex_dir):
    """Codex leaves an empty newer-schema DB beside a populated older one, so
    neither "first path" nor "newest schema" picks correctly."""
    make_db(codex_dir / "sqlite" / "goals_1.sqlite", [row(goal="real")])
    make_db(codex_dir / "goals_1.sqlite", [], v2=True)
    goals = codex_goals.read_goals(codex_dir)
    assert goals["t1"][0]["goal_id"] == "real"


def test_populated_db_wins_in_the_other_arrangement(codex_dir):
    make_db(codex_dir / "sqlite" / "goals_1.sqlite", [])
    make_db(codex_dir / "goals_1.sqlite", [row(goal="real")], v2=True)
    assert codex_goals.read_goals(codex_dir)["t1"][0]["goal_id"] == "real"


def test_v1_db_yields_null_deferrals_not_zero(codex_dir):
    """None means "this Codex build cannot record deferrals"; 0 would be a
    confident claim the agent never made."""
    make_db(codex_dir / "goals_1.sqlite", [row()])
    assert codex_goals.read_goals(codex_dir)["t1"][0]["evidence"]["deferrals"] is None


def test_v2_db_counts_deferrals(codex_dir):
    make_db(codex_dir / "goals_1.sqlite", [row()], v2=True,
            deferrals=["t1", "t1", "other"])
    assert codex_goals.read_goals(codex_dir)["t1"][0]["evidence"]["deferrals"] == 2


def test_v2_db_reports_zero_deferrals_when_table_is_empty(codex_dir):
    make_db(codex_dir / "goals_1.sqlite", [row()], v2=True)
    assert codex_goals.read_goals(codex_dir)["t1"][0]["evidence"]["deferrals"] == 0


# --- robustness: reads never raise -----------------------------------------

def test_missing_dir_yields_no_goals(tmp_path):
    assert codex_goals.read_goals(tmp_path / "nope") == {}


def test_db_without_goals_table_yields_no_goals(codex_dir):
    codex_dir.mkdir(parents=True)
    con = sqlite3.connect(codex_dir / "goals_1.sqlite")
    con.executescript("CREATE TABLE unrelated (x INTEGER);")
    con.close()
    assert codex_goals.read_goals(codex_dir) == {}


def test_garbage_file_yields_no_goals(codex_dir):
    codex_dir.mkdir(parents=True)
    (codex_dir / "goals_1.sqlite").write_bytes(b"not a database at all")
    assert codex_goals.read_goals(codex_dir) == {}


def test_null_and_bad_values_do_not_raise(codex_dir):
    make_db(codex_dir / "goals_1.sqlite", [
        ("t1", None, None, None, None, None, None, None, None),
        ("t2", "g", "o", "active", "notanint", "notanint", "x", "y", "z"),
    ])
    goals = codex_goals.read_goals(codex_dir)
    assert goals["t1"][0]["tokens"] is None
    assert goals["t1"][0]["state"] == "unknown"
    assert goals["t1"][0]["created_at"] is None
    assert goals["t2"][0]["tokens"] is None


def test_rows_without_thread_id_are_dropped(codex_dir):
    make_db(codex_dir / "goals_1.sqlite", [row(thread=None), row(thread="t2")])
    assert list(codex_goals.read_goals(codex_dir)) == ["t2"]


# --- multiple goals --------------------------------------------------------

def test_multiple_goals_on_one_thread_are_ordered_oldest_first(codex_dir):
    make_db(codex_dir / "goals_1.sqlite", [
        row(goal="second", created=2_000_000_000_000),
        row(goal="first", created=1_000_000_000_000),
    ])
    ids = [g["goal_id"] for g in codex_goals.read_goals(codex_dir)["t1"]]
    assert ids == ["first", "second"]


def test_goals_split_across_threads(codex_dir):
    make_db(codex_dir / "goals_1.sqlite", [row(thread="a"), row(thread="b")])
    goals = codex_goals.read_goals(codex_dir)
    assert set(goals) == {"a", "b"}
    assert len(goals["a"]) == 1


# --- the honesty invariant -------------------------------------------------

def test_every_goal_declares_a_known_state_and_reported_source(codex_dir):
    allowed = {"active", "paused", "complete", "blocked", "unknown"}
    make_db(codex_dir / "goals_1.sqlite", [
        row(thread=f"t{i}", status=s)
        for i, s in enumerate(["active", "paused", "complete", "blocked",
                               "weird", None, ""])
    ])
    for goals in codex_goals.read_goals(codex_dir).values():
        for g in goals:
            assert g["state"] in allowed
            assert g["state_source"] == "reported"
            assert g["cost_basis"] == "native"
