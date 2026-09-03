"""Tests for the menu-bar card geometry, width and labelling.

A menu item must report its height BEFORE the menu opens, so the sizing here is
pure arithmetic with no AppKit dependency, and an error shows up as a clipped
card rather than an exception. Covers:
  - a window is TWO lines, which is what keeps a six-provider menu on screen
  - card_height accounts for header, rows and gaps
  - layout_rows offsets never overlap
  - panel_width scales with the display and stays inside a readable band
  - the drawn fill is derived from the same unicode bar the text menu shows
  - brand tint and monogram fall back rather than raising on an unknown agent

Run: pytest backend/test_menubar_cards.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from menubar import cards  # noqa: E402


def _bar_row(label="Weekly", bar="▰▰▰▰▱▱▱▱▱▱", severity="ok", resets="Resets in 1d 16h"):
    return {"type": "bar", "label": label, "bar": bar, "right": "40% left",
            "resets": resets, "severity": severity}


def _section(rows):
    return {"type": "section", "provider_id": "claude", "provider_name": "Claude Code",
            "plan": "Pro", "rows": rows}


def test_a_window_is_two_lines_not_three():
    """Length is the constraint: six signed-in providers is six cards.

    The label and its remaining-percentage share one line and the meter is the
    next, which is roughly half the height of a stacked layout.
    """
    assert cards.row_height(_bar_row()) == cards.ROW_LABEL_H + cards.BAR_GAP + cards.BAR_H
    # A third stacked line would push a six-provider menu off a laptop screen.
    assert cards.row_height(_bar_row()) < 30


def test_card_height_grows_by_exactly_one_row_and_gap():
    one = cards.card_height(_section([_bar_row()]))
    two = cards.card_height(_section([_bar_row(), _bar_row("Session")]))

    assert two - one == cards.row_height(_bar_row()) + cards.ROW_GAP


def test_a_balance_row_is_shorter_than_a_window():
    """An amount is one line; a window needs a label line and a meter."""
    balance = {"type": "balance", "label": "Extra usage", "value": "$25", "severity": None}
    assert cards.row_height(balance) == cards.BALANCE_H
    assert cards.row_height(balance) < cards.row_height(_bar_row())


def test_layout_rows_are_ordered_and_never_overlap():
    rows = [_bar_row(), {"type": "balance", "label": "Extra", "value": "$1"}, _bar_row("Session")]
    placed = cards.layout_rows(_section(rows))

    assert [row["label"] for row, _ in placed] == ["Weekly", "Extra", "Session"]
    tops = [top for _, top in placed]
    assert tops == sorted(tops)
    for (row, top), (_, next_top) in zip(placed, placed[1:]):
        assert top + cards.row_height(row) <= next_top
    last_row, last_top = placed[-1]
    assert (last_top + cards.row_height(last_row)
            <= cards.card_height(_section(rows)) - cards.CARD_PAD)


def test_panel_width_scales_with_the_display_and_stays_readable():
    """Narrower truncates provider names; wider reads as a window, not a menu."""
    laptop = cards.panel_width(1512.0)
    external = cards.panel_width(2560.0)

    assert cards.MIN_WIDTH <= laptop <= cards.MAX_WIDTH
    assert cards.MIN_WIDTH <= external <= cards.MAX_WIDTH
    assert external >= laptop
    # Extremes clamp rather than producing an unusable panel.
    assert cards.panel_width(800.0) == cards.MIN_WIDTH
    assert cards.panel_width(6016.0) == cards.MAX_WIDTH


def test_panel_width_falls_back_when_no_screen_can_be_read():
    assert cards.panel_width(None) == cards.WIDTH
    assert cards.panel_width(0) == cards.WIDTH


def test_meta_text_joins_the_percentage_and_a_shortened_reset():
    """"Resets in" repeats on every row, so only the duration is kept."""
    assert cards.meta_text(_bar_row()) == "40% left · 1d 16h"
    assert cards.meta_text(_bar_row(resets=None)) == "40% left"
    assert cards.compact_resets("Resets in 5h") == "5h"
    assert cards.compact_resets(None) == ""
    # An unrecognised wording is passed through rather than mangled.
    assert cards.compact_resets("tomorrow") == "tomorrow"


def test_fill_fraction_comes_from_the_same_bar_the_text_menu_shows():
    """Deriving a second percentage here is how the drawn and text bars drift."""
    assert cards._fill_fraction({"bar": "▰▰▰▰▰▱▱▱▱▱"}) == 0.5
    assert cards._fill_fraction({"bar": "▱▱▱▱▱▱▱▱▱▱"}) == 0.0
    assert cards._fill_fraction({"bar": "▰▰▰▰▰▰▰▰▰▰"}) == 1.0
    assert cards._fill_fraction({"bar": ""}) == 0.0
    assert cards._fill_fraction({}) == 0.0

    from menubar.render import _unicode_bar
    assert cards._fill_fraction({"bar": _unicode_bar(70.0)}) == 0.7


def test_brand_tints_mirror_the_dashboard_and_fall_back_safely():
    assert cards.agent_color("claude") == (0xF9, 0x73, 0x16)
    assert cards.agent_color("Codex") == (0xA8, 0x55, 0xF7)
    # An agent added to the backend before this map is a neutral mark, not a crash.
    assert cards.agent_color("brand-new-agent") == cards.AGENT_FALLBACK
    assert cards.agent_color(None) == cards.AGENT_FALLBACK


def test_every_supported_harness_gets_a_distinct_mark():
    """A duplicate mark in one panel labels the wrong provider.

    No derivable rule works: five harnesses begin with C, and first-two-letters
    collides Codex with Copilot. Hence the curated map, pinned here.
    """
    marks = list(cards.AGENT_MARK.values())
    assert len(set(marks)) == len(marks), marks
    assert all(len(m) == 2 for m in marks)
    # The whole point: the C-cluster stays separable.
    assert {cards.agent_monogram(a, None) for a in
            ("claude", "codex", "cursor", "copilot", "cline")} == {"CC", "CX", "CU", "CP", "CL"}


def test_an_unmapped_agent_still_gets_a_readable_mark():
    """An agent added to the backend before this map must not draw a blank."""
    assert cards.agent_monogram("brand-new", "Brand New") == "BN"
    assert cards.agent_monogram("solo", "Solo") == "SO"
    assert cards.agent_monogram(None, None) == "?"
    assert cards.agent_monogram("", "  ") == "?"


def test_the_panel_is_light_in_both_appearances():
    """A dark card inside a light macOS menu reads as a foreign element."""
    assert cards.palette(dark=True) is cards.palette(dark=False)
    assert cards.palette()["panel"] == (0xFB, 0xFB, 0xFD)


def test_severity_falls_back_to_ok_for_unknown_values():
    assert cards._severity_key(None) == "ok"
    assert cards._severity_key("nonsense") == "ok"
    assert cards._severity_key("crit") == "crit"


def test_every_severity_has_a_colour_to_code_the_bar_with():
    pal = cards.palette()
    for severity in ("ok", "warn", "crit"):
        assert pal[cards._severity_key(severity)]
    assert pal["ok"] != pal["warn"] != pal["crit"]
