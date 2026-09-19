"""Tests for the mtime-keyed sidecar parse cache (issue #351).

read_cache used `cached_mtime >= source_mtime` as its freshness test.
`write_cache` always stores `_mtime = source_mtime`, so `>=` only diverges
from `==` when a later source_mtime reading is *smaller* than the one
recorded at write time, i.e. the mtime went backwards (NTP step, NAS/SMB
clock skew). `>=` treats that as still fresh and pins the stale payload
forever; `==` is the only relationship that actually means "unchanged".
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import scan_cache


def _set_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKENTELEMETRY_DATA_DIR", str(tmp_path / "data"))


def test_read_cache_hits_on_unchanged_mtime(tmp_path, monkeypatch):
    _set_data_dir(tmp_path, monkeypatch)
    scan_cache.write_cache("claude", "sess-1", 1000.0, {"total": 3000})
    assert scan_cache.read_cache("claude", "sess-1", 1000.0) == {
        "total": 3000,
        "_mtime": 1000.0,
        "_version": scan_cache.CACHE_VERSION,
    }


def test_read_cache_misses_when_source_advances(tmp_path, monkeypatch):
    _set_data_dir(tmp_path, monkeypatch)
    scan_cache.write_cache("claude", "sess-1", 1000.0, {"total": 3000})
    assert scan_cache.read_cache("claude", "sess-1", 1001.0) is None


def test_read_cache_misses_when_source_mtime_goes_backwards(tmp_path, monkeypatch):
    """Fails on main: a clock correction after write made the cache freeze forever.

    Mirrors the issue's own repro: parse while the mtime source is ahead
    (day+1), then a real append lands after the clock is corrected back, so
    the next read's source_mtime is *smaller* than the recorded one.
    """
    _set_data_dir(tmp_path, monkeypatch)
    day_ahead = 1_000_000.0
    corrected = 900_000.0
    scan_cache.write_cache("claude", "sess-1", day_ahead, {"total": 3000})
    assert scan_cache.read_cache("claude", "sess-1", corrected) is None
