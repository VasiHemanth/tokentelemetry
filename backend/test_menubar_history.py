"""Tests for the menu-bar sparkline's rolling sample store.

The store exists so the trend chart costs nothing extra: the menu bar already
refreshes every 60s, so each refresh appends one reading. Covers:
  - record() appends and caps each series at MAX_SAMPLES
  - a series absent from a call is left alone, not zero-filled
  - load() rejects corrupt JSON and a stale version instead of raising
  - trend_for() treats a single sample as "no trend"
  - samples_from_presentation() skips balance rows and unresolved windows

Run: pytest backend/test_menubar_history.py
"""
import json
import os
import sys
from dataclasses import dataclass
from typing import Optional

sys.path.insert(0, os.path.dirname(__file__))
from menubar import history  # noqa: E402


@dataclass
class FakeRow:
    provider_id: str
    resource_id: str
    pct: Optional[float]
    is_balance: bool = False


def test_record_appends_and_caps_each_series(tmp_path):
    key = history.series_key("claude", "session")
    for value in range(history.MAX_SAMPLES + 15):
        history.record(tmp_path, {key: float(value % 101)})

    stored = history.load(tmp_path)

    assert len(stored[key]) == history.MAX_SAMPLES
    # The cap drops from the FRONT, so the newest reading survives.
    assert stored[key][-1] == float((history.MAX_SAMPLES + 14) % 101)


def test_a_series_missing_from_a_call_is_left_untouched(tmp_path):
    """A provider that failed to refresh has no reading.

    Zero-filling it would draw a cliff in the sparkline that never happened.
    """
    claude, codex = history.series_key("claude", "session"), history.series_key("codex", "weekly")
    history.record(tmp_path, {claude: 40.0, codex: 10.0})
    history.record(tmp_path, {claude: 55.0})

    stored = history.load(tmp_path)

    assert stored[claude] == [40.0, 55.0]
    assert stored[codex] == [10.0]


def test_values_are_clamped_to_a_percentage(tmp_path):
    key = history.series_key("cursor", "total")
    history.record(tmp_path, {key: 140.0})
    history.record(tmp_path, {key: -20.0})

    assert history.load(tmp_path)[key] == [100.0, 0.0]


def test_load_survives_corrupt_json_and_a_stale_version(tmp_path):
    target = tmp_path / history.FILENAME

    target.write_text("{not json", encoding="utf-8")
    assert history.load(tmp_path) == {}

    target.write_text(json.dumps({"version": history.VERSION + 1,
                                  "series": {"a:b": [1, 2]}}), encoding="utf-8")
    assert history.load(tmp_path) == {}

    # A recognised payload with junk values keeps only the numbers.
    target.write_text(json.dumps({"version": history.VERSION,
                                  "series": {"a:b": [1, "x", None, 2], "c": "nope"}}),
                      encoding="utf-8")
    assert history.load(tmp_path) == {"a:b": [1.0, 2.0]}


def test_load_of_a_missing_file_is_empty_not_an_error(tmp_path):
    assert history.load(tmp_path / "nope") == {}


def test_one_sample_is_not_a_trend():
    """Drawing a single bar would imply a history the store does not have."""
    series = {history.series_key("claude", "session"): [42.0]}
    assert history.trend_for(series, "claude", "session") is None

    series[history.series_key("claude", "session")].append(43.0)
    assert history.trend_for(series, "claude", "session") == [42.0, 43.0]


def test_trend_for_an_unknown_series_is_none():
    assert history.trend_for({}, "nobody", "nothing") is None


def test_samples_skip_balances_and_unresolved_windows():
    rows = [
        FakeRow("claude", "session", 80.0),
        FakeRow("codex", "extraUsage", None, is_balance=True),
        FakeRow("cursor", "total", None),
    ]

    samples = history.samples_from_presentation(rows)

    assert samples == {history.series_key("claude", "session"): 80.0}


def test_samples_from_nothing_is_empty():
    assert history.samples_from_presentation(None) == {}
