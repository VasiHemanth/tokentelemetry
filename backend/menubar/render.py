"""Build a macOS menu item tree from a :class:`MenubarPresentation`.

Two layers, deliberately separated:

* :func:`menu_spec` turns a presentation into pure, headless data (a list of
  ``section`` / ``bar`` / ``balance`` / ``note`` / ``action`` dictionaries) with
  no macOS imports. This is what the tests exercise and what keeps the wording
  and worst-window choice in one rumps-free place.
* :func:`build_rumps_menu` turns that spec into ``rumps.MenuItem`` objects.
  Progress rows render a unicode bar plus the remaining percentage, colored via
  an attributed title when AppKit is available (best-effort, wrapped so any
  error falls back to plain text). No custom ``NSView`` drawing is required, so
  the menu cannot break rendering if a color fails.

``rumps`` is imported inside the functions, never at module import, so this
module stays importable on Linux/Windows.
"""

from __future__ import annotations

import logging
from functools import partial
from typing import Any, Dict, List, Optional

from menubar.presentation import MenuBarPresentation

logger = logging.getLogger("tokentelemetry.menubar.render")

_ACTION_KINDS = {"open", "refresh", "launch", "quit"}

_BAR_CELLS = 10
_FILLED = "▰"
_TRACK = "▱"


def menu_spec(presentation: MenuBarPresentation, launch_checked: Optional[bool] = None,
              trend: Optional[Dict[str, Any]] = None,
              footer: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Render a presentation into a headless menu spec.

    Each top-level entry is one of:
      ``{"type": "section", "title": str, "rows": [...]}``
      ``{"type": "note", "text": str}``
      ``{"type": "separator"}``
      ``{"type": "action", "title": str, "kind": "open|refresh|launch|quit",
        "checked": bool}``

    ``rows`` entries are ``bar`` (a consumption window with a progress bar) or
    ``balance`` (an amount). Bar rows carry ``label``, ``bar`` (unicode), ``right``
    (remaining percentage), ``resets`` and ``severity``; balance rows carry
    ``label`` and ``value``.

    ``launch_checked`` is the installed-LAunchAgent state; when omitted it is
    read from the real LaunchAgents directory, letting callers (and tests) pin
    the checkmark deterministically.
    """

    items: List[Dict[str, Any]] = []
    for section in _sections(presentation.rows):
        source_rows = section["rows"]
        section["rows"] = [row_spec(row) for row in source_rows]
        # Attach the trend to the section rather than to each row: the card draws
        # ONE sparkline per provider, from its most significant window, the same
        # way the reference does. Picking per row would draw a chart per bar.
        section["trend"] = _section_trend(source_rows, trend)
        items.append(section)
    if presentation.not_supported_count:
        items.append({"type": "note", "text": _not_supported_text(presentation.not_supported_count)})
    # Sits directly under the cards and ABOVE the action block, which is both
    # where the reference puts it and what keeps the menu's tail (separator,
    # actions, Quit last) unchanged for anything that depends on that order.
    if footer:
        items.append({"type": "footer", **footer})
    items.append({"type": "separator"})
    items.append(_action("Open dashboard", "open", checked=False))
    items.append(_action("Refresh now", "refresh", checked=False))
    checked = _launch_checked() if launch_checked is None else launch_checked
    items.append(_action("Launch at login  ✓" if checked else "Launch at login", "launch", checked=checked))
    items.append({"type": "separator"})
    items.append(_action("Quit", "quit", checked=False))
    return items


def row_spec(row: Any) -> Dict[str, Any]:
    """Convert a presentation row into a bar (consumption) or balance spec."""
    if row.is_balance:
        return {"type": "balance", "label": row.resource_label, "value": row.amount_text or row.text,
                "severity": None}
    pct = row.pct if row.pct is not None else 0.0
    return {
        "type": "bar",
        "label": row.resource_label,
        # Filled by what is LEFT, not by what is used, because the caption
        # rendered beside it says "N% left". Filling by consumption put a
        # six-tenths bar next to the words "40% left"; as a drawn meter sitting
        # directly under that caption the contradiction is unmissable. A
        # exhausted window is now an empty bar, which is also what a "Limit
        # reached" row should look like.
        "bar": _unicode_bar(100.0 - pct),
        "right": row.pct_left_text or row.text,
        "resets": row.resets_text,
        "severity": row.severity or "ok",
    }


def _action(title: str, kind: str, checked: bool) -> Dict[str, Any]:
    assert kind in _ACTION_KINDS
    return {"type": "action", "title": title, "kind": kind, "checked": checked}


def _unicode_bar(pct: float) -> str:
    cells = int(round(max(0.0, min(100.0, float(pct))) / 100.0 * _BAR_CELLS))
    return (_FILLED * cells) + (_TRACK * (_BAR_CELLS - cells))


def _launch_checked() -> bool:
    from menubar import launch_agent
    return launch_agent.is_installed()


def _sections(rows: Any) -> List[Dict[str, Any]]:
    """Group presentation rows into sections under a provider header."""
    sections: List[Dict[str, Any]] = []
    current_id: Optional[str] = None
    current_header: Optional[Dict[str, Any]] = None
    current_rows: List[Any] = []

    def flush() -> None:
        if current_header is not None and current_rows:
            current_header["rows"] = current_rows
            sections.append(current_header)

    for row in rows:
        if row.provider_id != current_id:
            flush()
            current_id = row.provider_id
            title = row.provider_name + (f"  {row.plan}" if row.plan else "")
            # `title` stays the single combined string the text renderer has
            # always used. The card renderer needs the parts separately so it can
            # set the plan as its own badge, so both are carried.
            current_header = {"type": "section", "title": title, "rows": [],
                              "provider_id": row.provider_id,
                              "provider_name": row.provider_name,
                              "plan": row.plan}
            current_rows = []
        current_rows.append(row)
    flush()
    return sections


def _section_trend(source_rows: List[Any], trend: Optional[Dict[str, Any]]) -> Optional[List[float]]:
    """The sparkline series for a provider card, or None when there is none.

    Chooses the window closest to its ceiling, matching the headline the menu
    bar title already shows, so the chart and the title never describe different
    windows. Balance rows are skipped: an amount has no percentage to plot.
    """
    if not trend:
        return None
    from menubar import history

    best_row, best_pct = None, -1.0
    for row in source_rows:
        if getattr(row, "is_balance", False) or getattr(row, "pct", None) is None:
            continue
        if float(row.pct) > best_pct:
            best_row, best_pct = row, float(row.pct)
    if best_row is None:
        return None
    return history.trend_for(trend, best_row.provider_id, best_row.resource_id)


def _not_supported_text(count: int) -> str:
    return "1 agent with no live quota" if count == 1 else f"{count} agents with no live quota"


def _row_text(row: Dict[str, Any]) -> str:
    """Plain-text rendering used both directly and as a fallback."""
    label = row.get("label", "")
    if row.get("type") == "balance":
        value = row.get("value", "")
        return f"{label}    {value}"
    bar = row.get("bar", "")
    right = row.get("right", "")
    resets = row.get("resets")
    suffix = f"  ·  {resets}" if resets else ""
    return f"{label}    {bar}  {right}{suffix}"


def _colorized_title(row: Dict[str, Any]) -> Any:
    """Attributed title with the remaining-percentage colored by severity."""
    from AppKit import (NSColor, NSFont, NSFontAttributeName,
                        NSForegroundColorAttributeName)
    from Foundation import NSMutableAttributedString

    attr = NSMutableAttributedString.alloc().initWithString_("")

    def append(value: str, color: Any, size: float, bold: bool) -> None:
        if not value:
            return
        seg = NSMutableAttributedString.alloc().initWithString_(value)
        seg.addAttribute_value_range_(NSFontAttributeName, _font(size, bold), (0, len(value)))
        seg.addAttribute_value_range_(NSForegroundColorAttributeName, color, (0, len(value)))
        attr.appendAttributedString_(seg)

    label = row.get("label", "")
    append(label, NSColor.labelColor(), 12, False)
    append("    ", NSColor.labelColor(), 12, False)
    if row.get("type") == "balance":
        append(row.get("value", ""), NSColor.secondaryLabelColor(), 12, False)
    else:
        color = _severity_nscolor(row.get("severity"))
        append(row.get("bar", ""), color, 12, False)
        append("  ", NSColor.labelColor(), 12, False)
        append(row.get("right", ""), color, 12, True)
        if row.get("resets"):
            append(f"  ·  {row['resets']}", NSColor.tertiaryLabelColor(), 10, False)
    return attr


def _font(size: float, bold: bool):
    from AppKit import NSFont
    return NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size)


def _severity_nscolor(severity: Optional[str]):
    from AppKit import NSColor
    palette = {
        "ok": NSColor.colorWithSRGBRed_green_blue_alpha_(0x60 / 255, 0xA5 / 255, 0xFA / 255, 1.0),
        "warn": NSColor.colorWithSRGBRed_green_blue_alpha_(0xFC / 255, 0xD3 / 255, 0x4D / 255, 1.0),
        "crit": NSColor.colorWithSRGBRed_green_blue_alpha_(0xFD / 255, 0xA4 / 255, 0xAF / 255, 1.0),
    }
    return palette.get(severity or "ok")


# --- rumps layer --------------------------------------------------------------
# Imported lazily so this module stays importable on any platform.

def build_rumps_menu(presentation: MenuBarPresentation, handler: Any = None,
                     launch_checked: Optional[bool] = None,
                     trend: Optional[Dict[str, Any]] = None,
                     footer: Optional[Dict[str, Any]] = None) -> List[Any]:
    """Return a list of rumps menu items for a presentation.

    Each entry is a ``rumps.MenuItem`` or ``None`` (meaning a separator). Rows
    default to plain text; an attributed (colored) title is applied best-effort.
    ``handler`` is called as ``handler(kind, sender)`` for the ``open`` /
    ``refresh`` / ``launch`` actions; the ``quit`` action always calls
    :func:`rumps.quit_application`.
    """
    import rumps

    def build(item_spec: Dict[str, Any]):
        kind = item_spec.get("type")
        if kind == "separator":
            return None
        if kind == "action":
            item = rumps.MenuItem(item_spec["title"])
            if item_spec["kind"] == "quit":
                item.set_callback(rumps.quit_application)
            elif handler is not None:
                item.set_callback(partial(handler, item_spec["kind"]))
            return item
        if kind == "note":
            return rumps.MenuItem(item_spec["text"])
        if kind == "footer":
            item = rumps.MenuItem("")
            if _attach_footer_view(item, item_spec):
                return item
            # Falls back to text rather than None: None means "separator" to the
            # loop below, which would silently turn a failed footer into a rule.
            version = item_spec.get("version") or ""
            nxt = item_spec.get("next_update") or ""
            return rumps.MenuItem(f"{version}   {nxt}".strip())
        if kind == "section":
            parent = rumps.MenuItem(item_spec["title"])
            # A drawn card replaces the submenu entirely. If the view cannot be
            # built (no PyObjC, a drawing error, a future macOS change), the
            # original nested text rows are still attached below, so the menu
            # degrades to exactly what it rendered before rather than to nothing.
            if _attach_card_view(parent, item_spec):
                return parent
            for row in item_spec.get("rows", []):
                parent.add(_row_menu_item(row))
            return parent
        return None

    items: List[Any] = []
    for item_spec in menu_spec(presentation, launch_checked=launch_checked,
                               trend=trend, footer=footer):
        built = build(item_spec)
        items.append(rumps.separator if built is None else built)
    return items


def _row_menu_item(row: Dict[str, Any]):
    import rumps

    item = rumps.MenuItem(_row_text(row))
    colored = _try_colorized_title(row)
    if colored is not None:
        item._menuitem.setAttributedTitle_(colored)
    return item


def _try_colorized_title(row: Dict[str, Any]):
    try:
        return _colorized_title(row)
    except Exception:  # pragma: no cover — color is best-effort
        return None


def _attach_card_view(item: Any, section: Dict[str, Any]) -> bool:
    """Give a provider item a drawn card view. False means "keep the text rows"."""
    try:
        from menubar import cards
        item._menuitem.setView_(cards.build_card_view(section))
        return True
    except Exception as exc:  # pragma: no cover — view drawing is best-effort
        logger.debug("menubar card view unavailable (%s); using text rows", exc)
        return False


def _attach_footer_view(item: Any, spec: Dict[str, Any]) -> bool:
    try:
        from menubar import cards
        item._menuitem.setView_(cards.build_footer_view(spec))
        return True
    except Exception as exc:  # pragma: no cover — view drawing is best-effort
        logger.debug("menubar footer view unavailable (%s); using text", exc)
        return False
