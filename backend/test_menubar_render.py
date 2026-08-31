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
    assert claude["rows"] == [{
        "type": "bar", "label": "Session", "bar": "▰▰▰▰▰▰▱▱▱▱",
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
    assert bar["severity"] == "crit"
    assert balance["type"] == "balance" and balance["value"] == "$12 used"
