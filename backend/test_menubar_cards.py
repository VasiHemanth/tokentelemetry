"""Tests for the menu-bar card geometry and sparkline scaling.

A menu item must report its height BEFORE the menu opens, so the sizing here is
pure arithmetic with no AppKit dependency, and an error shows up as a clipped
card rather than an exception. Covers:
  - card_height accounts for header, rows, gaps and the optional sparkline
  - layout_rows offsets never overlap
  - spark_bars scales to the series' own max, not to 100
  - the drawn fill is derived from the same unicode bar the text menu shows

Run: pytest backend/test_menubar_cards.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from menubar import cards  # noqa: E402


def _bar_row(label="Weekly", bar="▰▰▰▰▰▰▰▰▱▱", severity="ok"):
    return {"type": "bar", "label": label, "bar": bar, "right": "81% left",
            "resets": "Resets in 1d 16h", "severity": severity}


def _section(rows, trend=None):
    return {"type": "section", "provider_name": "Claude", "plan": "Team 5x",
            "rows": rows, "trend": trend}


def test_card_height_grows_with_rows_gaps_and_the_sparkline():
    one = cards.card_height(_section([_bar_row()]))
    two = cards.card_height(_section([_bar_row(), _bar_row("Session")]))

    # A second row costs exactly one row plus one inter-row gap.
    assert two - one == cards.row_height(_bar_row()) + cards.ROW_GAP

    charted = cards.card_height(_section([_bar_row()], trend=[10.0, 20.0]))
    assert charted - one == cards.SPARK_GAP + cards.SPARK_H


def test_a_balance_row_is_shorter_than_a_window():
    """An amount is one line; a window needs a label, a bar and a meta line."""
    balance = {"type": "balance", "label": "Extra usage", "value": "$25", "severity": None}
    assert cards.row_height(balance) < cards.row_height(_bar_row())
    assert cards.row_height(balance) == cards.BALANCE_H


def test_layout_rows_are_ordered_and_never_overlap():
    rows = [_bar_row(), {"type": "balance", "label": "Extra", "value": "$1"}, _bar_row("Session")]
    placed = cards.layout_rows(_section(rows))

    assert [row["label"] for row, _ in placed] == ["Weekly", "Extra", "Session"]
    tops = [top for _, top in placed]
    assert tops == sorted(tops)
    for (row, top), (_, next_top) in zip(placed, placed[1:]):
        assert top + cards.row_height(row) <= next_top
    # The last row must fit inside the card, above its bottom padding.
    last_row, last_top = placed[-1]
    assert last_top + cards.row_height(last_row) <= cards.card_height(_section(rows)) - cards.CARD_PAD


def test_spark_top_is_none_without_a_trend_and_inside_the_card_with_one():
    assert cards.spark_top(_section([_bar_row()])) is None

    section = _section([_bar_row()], trend=[1.0, 2.0])
    top = cards.spark_top(section)
    assert top is not None
    assert top + cards.SPARK_H <= cards.card_height(section)


def test_spark_bars_scale_to_the_series_own_max():
    """A window that only moves between 60 and 70 must not draw as a flat line.

    Scaling against 100 would flatten exactly the variation the chart exists to
    show, so the peak sample defines full height.
    """
    bars = cards.spark_bars([60.0, 65.0, 70.0])

    assert bars[-1] == 1.0
    assert bars[0] < bars[1] < bars[2]


def test_spark_bars_keep_the_most_recent_window():
    bars = cards.spark_bars([float(v) for v in range(100)], count=5)

    assert len(bars) == 5
    # Oldest of the kept samples is on the left, newest full-height on the right.
    assert bars[-1] == 1.0
    assert bars == sorted(bars)


def test_spark_bars_handle_empty_and_all_zero_series():
    assert cards.spark_bars([]) == []
    assert cards.spark_bars(None) == []
    assert cards.spark_bars([0.0, 0.0]) == [0.0, 0.0]


def test_fill_fraction_comes_from_the_same_bar_the_text_menu_shows():
    """Deriving a second percentage here is how the drawn and text bars drift."""
    assert cards._fill_fraction({"bar": "▰▰▰▰▰▱▱▱▱▱"}) == 0.5
    assert cards._fill_fraction({"bar": "▱▱▱▱▱▱▱▱▱▱"}) == 0.0
    assert cards._fill_fraction({"bar": "▰▰▰▰▰▰▰▰▰▰"}) == 1.0
    assert cards._fill_fraction({"bar": ""}) == 0.0
    assert cards._fill_fraction({}) == 0.0
    # Matches the unicode bar the text renderer builds, cell for cell.
    from menubar.render import _unicode_bar
    assert cards._fill_fraction({"bar": _unicode_bar(70.0)}) == 0.7


def test_both_palettes_define_every_colour_the_card_draws():
    required = {"panel", "sunken", "border", "border_alpha", "fg", "muted",
                "dim", "ok", "warn", "crit"}
    for dark in (True, False):
        assert required <= set(cards.palette(dark))


def test_severity_falls_back_to_ok_for_unknown_values():
    assert cards._severity_key(None) == "ok"
    assert cards._severity_key("nonsense") == "ok"
    assert cards._severity_key("crit") == "crit"
