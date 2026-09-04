"""Unit tests for the headless menu-spec builder (no rumps / AppKit)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from menubar.presentation import build_menu_presentation
from menubar.render import menu_spec, row_spec, _unicode_bar


def test_unicode_bar_scales_across_cells():
    assert _unicode_bar(0) == "▱▱▱▱▱▱▱▱▱▱"
    assert _unicode_bar(100) == "▰▰▰▰▰▰▰▰▰▰"
    assert _unicode_bar(50) == "▰▰▰▰▰▱▱▱▱▱"


def test_menu_spec_groups_windows_under_provider_headers_and_appends_actions():
    presentation = build_menu_presentation({
        "providers": {
            "codex": {
                "displayName": "Codex",
                "plan": "Plus",
                "resources": {
                    "weekly": {"kind": "consumption", "unit": "percent", "used": 81, "limit": 100},
                    "extraUsage": {"kind": "spend", "unit": "usd", "used": 25},
                },
            },
            "claude": {
                "displayName": "Claude Code",
                "plan": "Pro",
                "resources": {
                    "session": {"kind": "consumption", "unit": "percent", "used": 60, "limit": 100},
                },
            },
        },
        "capabilities": {
            "pi": {"displayName": "Pi", "state": "notSupported"},
            "muse": {"displayName": "Muse Code", "state": "notSupported"},
        },
        "errors": [],
    })

    spec = menu_spec(presentation, launch_checked=False)

    sections = [item for item in spec if item["type"] == "section"]
    assert [s["title"] for s in sections] == ["Claude Code  Pro", "Codex  Plus"]

    # Row shape: a consumption window is a bar; an amount is a balance.
    claude = next(s for s in sections if s["title"].startswith("Claude Code"))
    # The bar fills by what is LEFT, matching the caption beside it: 60% used
    # leaves 40%, so four of ten cells are filled.
    assert claude["rows"] == [{
        "type": "bar", "label": "Session", "bar": "▰▰▰▰▱▱▱▱▱▱",
        "right": "40% left", "resets": None, "severity": "ok",
    }]

    codex_rows = next(s for s in sections if s["title"].startswith("Codex"))["rows"]
    by_type = {row["type"]: row for row in codex_rows}
    assert by_type["bar"]["right"] == "19% left"
    assert by_type["balance"] == {"type": "balance", "label": "Extra usage", "value": "$25 used", "severity": None}

    # Notes, separators and the footer actions are appended in order.
    assert {"type": "note", "text": "2 agents with no live quota"} in spec
    kinds = [item.get("kind") for item in spec if item["type"] == "action"]
    assert kinds == ["open", "refresh", "launch", "quit"]
    # Footer tail: separators around the action block (before open, before quit).
    action_index = [i for i, item in enumerate(spec) if item["type"] == "action"]
    assert spec[action_index[0] - 1]["type"] == "separator"
    assert [spec[i]["kind"] for i in action_index] == ["open", "refresh", "launch", "quit"]
    assert spec[action_index[-1] - 1]["type"] == "separator"
    assert spec[-1] == {"type": "action", "title": "Quit", "kind": "quit", "checked": False}


def test_row_spec_marks_balance_and_consumption():
    presentation = build_menu_presentation({
        "providers": {
            "x": {
                "displayName": "X",
                "plan": None,
                "resources": {
                    "session": {"kind": "consumption", "unit": "percent", "used": 90, "limit": 100},
                    "extraUsage": {"kind": "spend", "unit": "usd", "used": 12},
                },
            },
        },
        "capabilities": {},
        "errors": [],
    })
    rows = presentation.rows
    specs = {row_spec(row)["type"]: row_spec(row) for row in rows}
    bar = specs["bar"]
    balance = specs["balance"]
    assert bar["type"] == "bar" and bar["right"] == "10% left"
    # A nearly exhausted window draws a nearly EMPTY bar, so the meter and its
    # caption say the same thing. An exhausted one would draw empty entirely.
    assert bar["bar"] == "▰▱▱▱▱▱▱▱▱▱"
    assert bar["severity"] == "crit"
    assert balance["type"] == "balance" and balance["value"] == "$12 used"


def _card_presentation():
    """One provider with two windows, for the card-oriented spec fields."""
    return build_menu_presentation({
        "providers": {
            "claude": {
                "displayName": "Claude Code", "plan": "Pro",
                "resources": {
                    "session": {"kind": "consumption", "unit": "percent", "used": 60, "limit": 100},
                    "weekly": {"kind": "consumption", "unit": "percent", "used": 20, "limit": 100},
                },
            },
        },
        "capabilities": {},
        "errors": [],
    })


def test_sections_carry_the_parts_a_card_needs_without_changing_the_title():
    """The card sets the plan as its own badge, so it needs the pieces apart.

    `title` stays the single combined string the text renderer has always used.
    """
    section = next(s for s in menu_spec(_card_presentation(), launch_checked=False)
                   if s["type"] == "section")

    assert section["title"] == "Claude Code  Pro"
    assert section["provider_id"] == "claude"
    assert section["provider_name"] == "Claude Code"
    assert section["plan"] == "Pro"


def test_the_footer_sits_above_the_action_block():
    """Placing it here keeps the menu tail (separator, actions, Quit last) intact."""
    spec = menu_spec(_card_presentation(), launch_checked=False,
                     footer={"version": "TokenTelemetry 1.0.0",
                             "next_update": "Updates every 60s"})

    footer_index = next(i for i, item in enumerate(spec) if item["type"] == "footer")
    first_action = next(i for i, item in enumerate(spec) if item["type"] == "action")
    assert footer_index < first_action
    assert spec[footer_index]["version"] == "TokenTelemetry 1.0.0"
    assert spec[-1]["kind"] == "quit"


def test_no_footer_item_when_none_is_supplied():
    spec = menu_spec(_card_presentation(), launch_checked=False)
    assert not any(item["type"] == "footer" for item in spec)

