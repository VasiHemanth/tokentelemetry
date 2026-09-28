"""Tests for `telemetry.mark_active()` -- the `app.active` recurring-user
signal that counts real returning installs WITHOUT any install id.

Dates are frozen by passing `today=` directly (mark_active's only test hook),
so these are deterministic regardless of when they run. The network is
stubbed (`telemetry._post`) so nothing ever leaves the machine.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

import telemetry

ACTIVITY_FILE = telemetry._ACTIVITY_FILENAME


@pytest.fixture(autouse=True)
def _stub_network_and_sent(monkeypatch):
    # Never let a background thread make a real HTTP call from a test run.
    monkeypatch.setattr(telemetry, "_post", lambda payload: None)
    # `enabled()` reads the real preferences.json (harness_config freezes
    # PREFERENCES_FILE at import, so pointing TOKENTELEMETRY_DATA_DIR at
    # tmp_path does not redirect it) and short-circuits on any CI-ish env var
    # or DO_NOT_TRACK/TT_NO_TELEMETRY the *developer's own shell* happens to
    # export. Neither may leak into whether these tests see telemetry as on.
    # Force the preference on and clear every env-off signal here; individual
    # tests that want the "off" behavior set these back explicitly.
    monkeypatch.setattr(telemetry, "load_preferences", lambda: {"telemetry": True})
    for var in (*telemetry._CI_ENV, "DO_NOT_TRACK", "TT_NO_TELEMETRY"):
        monkeypatch.delenv(var, raising=False)
    telemetry._SENT.clear()
    yield
    telemetry._SENT.clear()


@pytest.fixture
def tt_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKENTELEMETRY_DATA_DIR", str(tmp_path))
    return tmp_path


def _state(tmp_path: Path) -> dict:
    return json.loads((tmp_path / ACTIVITY_FILE).read_text(encoding="utf-8"))


def _last_sent_props() -> dict:
    assert telemetry._SENT, "expected app.active to have been emitted"
    return telemetry._SENT[-1]["props"]


def _touch(path: Path, day: date) -> None:
    path.write_text("{}", encoding="utf-8")
    ts = datetime(day.year, day.month, day.day, 12, 0, 0).timestamp()
    os.utime(path, (ts, ts))


# --- first activity, ever -----------------------------------------------

def test_first_ever_is_new_and_age_0d(tt_data_dir):
    today = date(2026, 6, 15)
    props = telemetry.mark_active(today=today)

    assert props == {
        "install_age": "0d",
        "gap": "new",
        "freq_28d": "1",
        "first_in_week": 1,
        "first_in_month": 1,
    }
    assert _last_sent_props() == props

    state = _state(tt_data_dir)
    assert state == {
        "first_seen": "2026-06-15",
        "last_active": "2026-06-15",
        "recent_days": ["2026-06-15"],
        "first_seen_inferred": False,
    }


# --- backfill from an existing (pre-feature) install ---------------------

def test_existing_data_dir_backfills_as_upgraded(tt_data_dir):
    today = date(2026, 6, 15)
    _touch(tt_data_dir / "preferences.json", today - timedelta(days=10))

    props = telemetry.mark_active(today=today)

    assert props["gap"] == "upgraded"
    assert props["install_age"] == "7-29d"  # 10 days old
    state = _state(tt_data_dir)
    assert state["first_seen"] == "2026-06-05"
    assert state["first_seen_inferred"] is True


def test_no_existing_files_is_new_not_upgraded(tt_data_dir):
    # Empty data dir (no preferences/cache files at all) -> genuinely new.
    props = telemetry.mark_active(today=date(2026, 6, 15))
    assert props["gap"] == "new"
    assert _state(tt_data_dir)["first_seen_inferred"] is False


def test_files_written_today_do_not_count_as_a_prior_install(tt_data_dir):
    # A brand-new install's OWN first-run writes (rollup DB, VERSION,
    # preferences.json from earlier dashboard fetches in this same session)
    # land in the data dir before the first UI event reaches mark_active().
    # Those must not be mistaken for evidence of a pre-existing install --
    # only a file strictly older than today proves that.
    today = date(2026, 6, 15)
    _touch(tt_data_dir / "preferences.json", today)  # same day, not older

    props = telemetry.mark_active(today=today)

    assert props["gap"] == "new"
    assert props["install_age"] == "0d"
    assert _state(tt_data_dir)["first_seen_inferred"] is False


# --- once per local day ---------------------------------------------------

def test_same_day_twice_emits_once(tt_data_dir):
    today = date(2026, 6, 15)
    first = telemetry.mark_active(today=today)
    assert first is not None
    sent_after_first = len(telemetry._SENT)

    second = telemetry.mark_active(today=today)
    assert second is None
    assert len(telemetry._SENT) == sent_after_first  # nothing new emitted


# --- day-over-day gap + frequency progression -----------------------------

def test_next_day_gap_and_freq_progression(tt_data_dir):
    d0 = date(2026, 6, 1)
    telemetry.mark_active(today=d0)

    p1 = telemetry.mark_active(today=d0 + timedelta(days=1))
    assert p1["gap"] == "1d"
    assert p1["freq_28d"] == "2-4"

    p2 = telemetry.mark_active(today=d0 + timedelta(days=2))
    assert p2["freq_28d"] == "2-4"

    p3 = telemetry.mark_active(today=d0 + timedelta(days=3))
    assert p3["freq_28d"] == "2-4"

    p4 = telemetry.mark_active(today=d0 + timedelta(days=4))
    assert p4["freq_28d"] == "5-12"  # 5th distinct active day


def test_larger_gap_buckets(tt_data_dir):
    d0 = date(2026, 1, 1)
    telemetry.mark_active(today=d0)
    p = telemetry.mark_active(today=d0 + timedelta(days=5))
    assert p["gap"] == "2-7d"

    p = telemetry.mark_active(today=d0 + timedelta(days=20))
    assert p["gap"] == "8-30d"

    p = telemetry.mark_active(today=d0 + timedelta(days=90))
    assert p["gap"] == "30d+"


# --- week / month boundary flags ------------------------------------------

def test_first_in_week_and_month_flags(tt_data_dir):
    d_mon = date(2026, 6, 1)  # a Monday
    p_mon = telemetry.mark_active(today=d_mon)
    assert p_mon["first_in_week"] == 1
    assert p_mon["first_in_month"] == 1

    p_tue = telemetry.mark_active(today=d_mon + timedelta(days=1))
    assert p_tue["first_in_week"] == 0
    assert p_tue["first_in_month"] == 0

    p_next_week = telemetry.mark_active(today=d_mon + timedelta(days=7))
    assert p_next_week["first_in_week"] == 1
    assert p_next_week["first_in_month"] == 0  # still June

    p_next_month = telemetry.mark_active(today=date(2026, 7, 1))
    assert p_next_month["first_in_week"] == 1
    assert p_next_month["first_in_month"] == 1


def test_month_flag_not_repeated_past_the_28_day_window(tt_data_dir):
    # Active on the 1st, then not again until the 31st: the 1st has aged out of
    # recent_days, but it is the same month, so MAU must not count it twice.
    telemetry.mark_active(today=date(2026, 7, 1))
    p = telemetry.mark_active(today=date(2026, 7, 31))
    assert p["first_in_month"] == 0
    assert p["freq_28d"] == "1"


# --- disabled / env-off -----------------------------------------------------

@pytest.mark.parametrize("env_var", ["DO_NOT_TRACK", "TT_NO_TELEMETRY"])
def test_env_off_writes_no_file_and_emits_nothing(tt_data_dir, monkeypatch, env_var):
    monkeypatch.setenv(env_var, "1")
    result = telemetry.mark_active(today=date(2026, 6, 15))
    assert result is None
    assert not (tt_data_dir / ACTIVITY_FILE).exists()
    assert len(telemetry._SENT) == 0


def test_preference_off_writes_no_file(tt_data_dir, monkeypatch):
    monkeypatch.setattr(telemetry, "load_preferences", lambda: {"telemetry": False})
    result = telemetry.mark_active(today=date(2026, 6, 15))
    assert result is None
    assert not (tt_data_dir / ACTIVITY_FILE).exists()
    assert len(telemetry._SENT) == 0


def test_ci_writes_no_file(tt_data_dir, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    result = telemetry.mark_active(today=date(2026, 6, 15))
    assert result is None
    assert not (tt_data_dir / ACTIVITY_FILE).exists()


# --- corrupt state file -----------------------------------------------------

def test_corrupt_state_file_is_treated_as_missing(tt_data_dir):
    (tt_data_dir / ACTIVITY_FILE).write_text("{not valid json", encoding="utf-8")

    props = telemetry.mark_active(today=date(2026, 6, 15))

    # The corrupt activity file itself must not count as "existing data" to
    # infer first_seen from (it's excluded from the mtime scan), so with
    # nothing else in the dir this is genuinely first-ever.
    assert props["gap"] == "new"
    state = _state(tt_data_dir)
    assert state["last_active"] == "2026-06-15"  # overwritten with valid state


# --- privacy: no context props, unknown props dropped -----------------------

def test_payload_excludes_context_props(tt_data_dir):
    telemetry.update_context(agents=["claude", "codex"], summarizer_backend="ollama")
    try:
        telemetry.mark_active(today=date(2026, 6, 15))
        props = telemetry._SENT[-1]["props"]
        assert set(props) == {"install_age", "gap", "freq_28d", "first_in_week", "first_in_month"}
        assert "agents" not in props
        assert "agent_count" not in props
        assert "summarizer_backend" not in props
    finally:
        telemetry.update_context(agents=[], summarizer_backend="none")


def test_unknown_props_are_dropped_and_off_enum_collapses_to_other():
    out = telemetry._sanitize_props("app.active", {
        "install_age": "0d",
        "gap": "new",
        "freq_28d": "1",
        "first_in_week": 1,
        "first_in_month": 0,
        "path": "/etc/passwd",
        "evil": "haxx",
    })
    assert out == {
        "install_age": "0d", "gap": "new", "freq_28d": "1",
        "first_in_week": 1, "first_in_month": 0,
    }

    out2 = telemetry._sanitize_props("app.active", {
        "install_age": "999d", "gap": "made-up", "freq_28d": "lots",
    })
    assert out2 == {"install_age": "other", "gap": "other", "freq_28d": "other"}


def test_app_active_declared_in_event_props_and_enums():
    assert "app.active" in telemetry._EVENT_PROPS
    for key in ("install_age", "gap", "freq_28d"):
        assert key in telemetry._ENUMS, f"{key} must be enum-controlled"


def test_build_event_for_app_active_has_no_context_props():
    payload = telemetry.build_event("app.active", {
        "install_age": "0d", "gap": "new", "freq_28d": "1",
        "first_in_week": 1, "first_in_month": 1,
    })
    assert "agents" not in payload["props"]
    assert "agent_count" not in payload["props"]
    assert "summarizer_backend" not in payload["props"]
    # systemProps are unaffected -- still present as normal.
    assert "sdkVersion" in payload["systemProps"]
