"""The pricing divergence report (issue #303).

Guards the detection property the script relies on: because the overlay only
inserts keys the inline table does not already hold, any key whose merged value
differs from the raw overlay value must be an inline entry that shadowed it.
"""

import json
from pathlib import Path

import pricing
import pricing_divergence as pd

DATA = json.loads((Path(pd.__file__).parent / "pricing_data.json").read_text(encoding="utf-8"))


def test_rel_diff_treats_missing_as_incomparable():
    """A missing cached_read is a data gap, not a 100% divergence."""
    assert pd._rel_diff(None, 1.0) is None
    assert pd._rel_diff(1.0, None) is None
    assert pd._rel_diff(0.0, 0.0) == 0.0
    assert pd._rel_diff(1.0, 1.0) == 0.0
    assert pd._rel_diff(1.0, 2.0) == 50.0
    assert pd._rel_diff(2.0, 1.0) == 50.0


def test_every_reported_key_is_actually_shadowed():
    """No overlay-injected key can appear: those are equal by construction."""
    sep = pricing._PROVIDER_SEP
    for row in pd.find_divergences():
        if row["table"] == "flat":
            assert row["key"].lower().strip() in pricing.PRICING
        else:
            prov, model = row["key"].split("/", 1)
            assert (prov.lower().strip(), model.lower().strip()) in pricing.PRICING_BY_PROVIDER
        assert row["pct"] > 0


def test_report_is_sorted_worst_first():
    pcts = [r["pct"] for r in pd.find_divergences()]
    assert pcts == sorted(pcts, reverse=True)


def test_detects_a_planted_divergence():
    """A curated entry that disagrees with the overlay must be reported."""
    key = next(
        (k for k, v in (DATA.get("pricing") or {}).items()
         if isinstance(v, dict) and isinstance(v.get("in"), (int, float)) and v["in"] > 0),
        None,
    )
    assert key, "no usable overlay entry to plant against"
    k = key.lower().strip()
    prev = pricing.PRICING.get(k)
    pricing.PRICING[k] = {"in": DATA["pricing"][key]["in"] * 10, "out": 1.0, "cached_read": None}
    try:
        assert any(r["key"] == key for r in pd.find_divergences())
    finally:
        if prev is None:
            pricing.PRICING.pop(k, None)
        else:
            pricing.PRICING[k] = prev


def test_agreeing_layers_are_not_reported():
    """The known gap, pinned so it is a decision and not a surprise.

    deepseek-v4-flash was stale in BOTH layers at $0.14/$0.28. This check
    compares the layers to each other, so it cannot see that.
    """
    key = next(
        (k for k, v in (DATA.get("pricing") or {}).items()
         if isinstance(v, dict) and pricing.PRICING.get(k.lower().strip()) == v),
        None,
    )
    if key:
        assert not any(r["key"] == key for r in pd.find_divergences())


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            fn()
    print("All tests passed!")
