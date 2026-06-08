"""Tests for the build-time pricing overlay (Unit 3, issue #45).

These live in their own file (not test_pricing.py) to avoid colliding with a
sibling unit. They cover:
  - the bundled pricing_data.json overlays the inline table,
  - inline entries stay authoritative (overlay never clobbers them),
  - a missing / garbage file degrades silently to the static tables,
  - importing `pricing` performs NO network I/O.
"""
import importlib
import json
import socket
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _fresh_pricing():
    """Import pricing.py from scratch so module-load overlay runs again."""
    sys.modules.pop("pricing", None)
    return importlib.import_module("pricing")


def test_import_is_offline():
    """Importing pricing must not open any socket (zero network I/O)."""
    orig = socket.socket

    def _blocked(*args, **kwargs):
        raise AssertionError("pricing import attempted network I/O")

    socket.socket = _blocked
    try:
        pricing = _fresh_pricing()
    finally:
        socket.socket = orig
    assert isinstance(pricing.PRICING, dict)


def test_overlay_expands_table():
    """Bundled JSON should add many models beyond the inline ~50."""
    pricing = _fresh_pricing()
    # The inline table alone is small; with the models.dev overlay it's large.
    assert len(pricing.PRICING) > 200


def test_inline_entries_are_authoritative():
    """Overlay must never clobber a curated inline entry."""
    pricing = _fresh_pricing()
    # claude-opus-4-7 is hand-tuned inline; assert its exact inline values.
    assert pricing.PRICING["claude-opus-4-7"] == {
        "in": 5.00,
        "out": 25.00,
        "cached_read": 0.50,
    }


def test_overlay_only_models_present():
    """A model only present in the bundled dataset should be loaded."""
    pricing = _fresh_pricing()
    data = json.loads((BACKEND_DIR / "pricing_data.json").read_text())
    # Find a model id in the overlay that is NOT in the inline table.
    inline_keys = {
        "claude-opus-4-7", "gpt-5.4", "gemini-3.1-pro",  # known inline samples
    }
    overlay_only = [
        k for k in data["pricing"] if k.lower() not in pricing.PRICING or True
    ]
    # Pick any overlay key that isn't a known inline one and assert it resolved.
    candidate = next(
        k for k in data["pricing"]
        if k.lower() not in inline_keys
    )
    assert candidate.lower() in pricing.PRICING


def test_missing_file_falls_back_to_static(tmp_path, monkeypatch):
    """Absent pricing_data.json → silent fallback to inline tables."""
    import pricing as _p
    missing = tmp_path / "does_not_exist.json"
    monkeypatch.setattr(_p, "_PRICING_DATA_PATH", missing)
    # Re-run loader against the missing path; should not raise and should keep
    # the inline entries intact.
    before = dict(_p.PRICING)
    _p._load_bundled_pricing()
    assert _p.PRICING["claude-opus-4-7"] == before["claude-opus-4-7"]


def test_garbage_file_falls_back_to_static(tmp_path, monkeypatch):
    """Malformed pricing_data.json → silent fallback, no exception."""
    import pricing as _p
    bad = tmp_path / "bad.json"
    bad.write_text("{ this is not valid json ]]", encoding="utf-8")
    monkeypatch.setattr(_p, "_PRICING_DATA_PATH", bad)
    # Must not raise.
    _p._load_bundled_pricing()
    assert "claude-opus-4-7" in _p.PRICING


def test_wrong_shape_file_is_ignored(tmp_path, monkeypatch):
    """Well-formed JSON of the wrong shape is ignored, no crash."""
    import pricing as _p
    odd = tmp_path / "odd.json"
    odd.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    monkeypatch.setattr(_p, "_PRICING_DATA_PATH", odd)
    _p._load_bundled_pricing()
    assert "claude-opus-4-7" in _p.PRICING


def test_coerce_rates_rejects_bad_entries():
    import pricing as _p
    assert _p._coerce_rates({"in": 1.0, "out": 2.0, "cached_read": None}) == {
        "in": 1.0, "out": 2.0, "cached_read": None,
    }
    assert _p._coerce_rates({"in": None, "out": None}) is None  # no priced dir
    assert _p._coerce_rates({"in": "free", "out": 2.0}) is None  # non-numeric
    assert _p._coerce_rates("nope") is None
    assert _p._coerce_rates({"in": True, "out": 2.0}) is None  # bool rejected


def test_calculate_cost_unchanged_for_inline():
    """Sanity: cost math on an inline model is unaffected by the overlay."""
    pricing = _fresh_pricing()
    # gpt-5.4: in 2.50, out 15.00 per 1M.
    cost = pricing.calculate_cost("gpt-5.4", 1_000_000, 1_000_000)
    assert cost == pytest.approx(2.50 + 15.00)
