"""Custom ``NSView`` rendering for the menu-bar quota cards.

The text menu (``render._row_menu_item``) can only ever be one line of glyphs
per row, so a unicode bar is as close to a progress meter as it gets. This
module draws the real thing: a rounded card per provider, a plan badge, a drawn
track-and-fill bar per window, and an optional sparkline, in the TokenTelemetry
palette.

Two layers, deliberately separated the same way ``render`` splits spec from
rumps:

* the ``*_height`` / ``layout_*`` functions are pure arithmetic with NO macOS
  imports, so the sizing that decides whether a card is clipped is unit-testable
  on any platform;
* the view classes are built lazily inside functions, so importing this module
  on Linux or Windows never touches Cocoa.

Every view is attached with ``NSMenuItem.setView_``. A view-backed item draws
its own content and, unlike an attributed title, is not truncated by the menu's
own text layout -- which is what makes the reference layout possible at all.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger("tokentelemetry.menubar.cards")

# --- geometry (pure, no AppKit) ----------------------------------------------
# Widths and heights are fixed rather than measured. A menu item must report its
# size BEFORE the menu opens, so anything derived from live text metrics would
# have to guess anyway; fixed rows keep every card aligned to the same grid.

WIDTH = 300.0

OUTER_PAD_X = 10.0
CARD_PAD = 10.0

HEADER_H = 24.0          # provider name + plan badge
ROW_LABEL_H = 16.0       # "Weekly"
BAR_H = 6.0
BAR_GAP = 6.0            # between label and bar, and bar and meta
ROW_META_H = 15.0        # "81% left" / "Resets in 1d 16h"
ROW_GAP = 12.0           # between one window and the next
BALANCE_H = 18.0         # a one-line amount row
SPARK_H = 26.0
SPARK_GAP = 8.0
FOOTER_H = 26.0

CORNER = 8.0
BAR_CORNER = 3.0


def row_height(row: Dict[str, Any]) -> float:
    """Height of one row inside a card."""
    if row.get("type") == "balance":
        return BALANCE_H
    return ROW_LABEL_H + BAR_GAP + BAR_H + BAR_GAP + ROW_META_H


def card_height(section: Dict[str, Any]) -> float:
    """Total height of one provider card, including its header and sparkline.

    Returned to the menu as the item's height, so an error here shows up as a
    clipped or padded card rather than an exception.
    """
    rows: Sequence[Dict[str, Any]] = section.get("rows") or ()
    inner = sum(row_height(r) for r in rows)
    if len(rows) > 1:
        inner += ROW_GAP * (len(rows) - 1)
    if section.get("trend"):
        inner += SPARK_GAP + SPARK_H
    return HEADER_H + CARD_PAD + inner + CARD_PAD


def footer_height() -> float:
    return FOOTER_H


def layout_rows(section: Dict[str, Any]) -> List[Tuple[Dict[str, Any], float]]:
    """Each row paired with its top offset inside the card view (flipped coords)."""
    y = HEADER_H + CARD_PAD
    placed: List[Tuple[Dict[str, Any], float]] = []
    for index, row in enumerate(section.get("rows") or ()):
        if index:
            y += ROW_GAP
        placed.append((row, y))
        y += row_height(row)
    return placed


def spark_top(section: Dict[str, Any]) -> Optional[float]:
    """Top offset of the sparkline, or None when the card has no trend."""
    if not section.get("trend"):
        return None
    return card_height(section) - CARD_PAD - SPARK_H


def spark_bars(values: Sequence[float], count: int = 24) -> List[float]:
    """Normalize a trend series to ``count`` bars in 0..1.

    Scaled against the series' own max, not against 100, because a window that
    only ever moves between 60% and 70% would otherwise draw as a flat line and
    hide exactly the variation the chart exists to show. An all-zero series
    stays flat rather than dividing by zero.
    """
    points = [max(0.0, min(100.0, float(v))) for v in values or ()]
    if not points:
        return []
    if len(points) > count:
        # Keep the most recent window; the left edge is the oldest sample.
        points = points[-count:]
    peak = max(points)
    if peak <= 0:
        return [0.0] * len(points)
    return [p / peak for p in points]


# --- palette ------------------------------------------------------------------
# Mirrors frontend/src/app/globals.css. Menus follow the system appearance, so
# both themes are carried and chosen at draw time.

_DARK = {
    "panel": (0x11, 0x14, 0x1A), "sunken": (0x07, 0x09, 0x0D),
    "border": (0xFF, 0xFF, 0xFF), "border_alpha": 0.10,
    "fg": (0xE8, 0xEA, 0xF0), "muted": (0x9A, 0xA1, 0xAD), "dim": (0x5F, 0x66, 0x75),
    "ok": (0x60, 0xA5, 0xFA), "warn": (0xFC, 0xD3, 0x4D), "crit": (0xFD, 0xA4, 0xAF),
    "badge_bg_alpha": 0.10,
}
_LIGHT = {
    "panel": (0xFB, 0xFB, 0xFD), "sunken": (0xE8, 0xEA, 0xF0),
    "border": (0x0F, 0x17, 0x2A), "border_alpha": 0.10,
    "fg": (0x1A, 0x1F, 0x2B), "muted": (0x4B, 0x55, 0x66), "dim": (0x6B, 0x74, 0x88),
    "ok": (0x25, 0x63, 0xEB), "warn": (0xB4, 0x53, 0x09), "crit": (0xBE, 0x12, 0x3C),
    "badge_bg_alpha": 0.08,
}


def palette(dark: bool) -> Dict[str, Any]:
    return _DARK if dark else _LIGHT


def _color(rgb: Tuple[int, int, int], alpha: float = 1.0):
    from AppKit import NSColor
    r, g, b = rgb
    return NSColor.colorWithSRGBRed_green_blue_alpha_(r / 255.0, g / 255.0, b / 255.0, alpha)


def _severity_key(severity: Optional[str]) -> str:
    return severity if severity in ("ok", "warn", "crit") else "ok"


def _is_dark(view: Any) -> bool:
    """Best-effort appearance probe; defaults to dark on any failure."""
    try:
        name = view.effectiveAppearance().bestMatchFromAppearancesWithNames_(
            ["NSAppearanceNameAqua", "NSAppearanceNameDarkAqua"])
        return str(name) == "NSAppearanceNameDarkAqua"
    except Exception:  # pragma: no cover - appearance API is best-effort
        return True


def _draw_text(text: str, x: float, y: float, size: float, color: Any,
               bold: bool = False, right_edge: Optional[float] = None) -> None:
    from AppKit import (NSFont, NSFontAttributeName, NSForegroundColorAttributeName)
    from Foundation import NSAttributedString, NSMakePoint

    if not text:
        return
    font = NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size)
    attrs = {NSFontAttributeName: font, NSForegroundColorAttributeName: color}
    string = NSAttributedString.alloc().initWithString_attributes_(text, attrs)
    if right_edge is not None:
        x = right_edge - string.size().width
    string.drawAtPoint_(NSMakePoint(x, y))


def _rounded(x: float, y: float, w: float, h: float, radius: float):
    from AppKit import NSBezierPath
    from Foundation import NSMakeRect
    return NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(x, y, max(0.0, w), max(0.0, h)), radius, radius)


def _draw_card_body(view: Any, section: Dict[str, Any], width: float) -> None:
    """Paint one provider card. Flipped coordinates: y grows downward."""
    pal = palette(_is_dark(view))
    inner_w = width - (OUTER_PAD_X * 2)
    total_h = card_height(section)

    # Header sits ABOVE the card surface, like the reference: the provider name
    # labels the card rather than living inside it.
    name = section.get("provider_name") or section.get("title") or ""
    _draw_text(name, OUTER_PAD_X, 3.0, 13.0, _color(pal["fg"]), bold=True)
    plan = section.get("plan")
    if plan:
        from Foundation import NSAttributedString
        name_width = _text_width(name, 13.0, True)
        _draw_text(plan, OUTER_PAD_X + name_width + 7.0, 5.0, 10.5,
                   _color(pal["muted"]))

    card_y = HEADER_H
    card_h = total_h - HEADER_H
    _color(pal["panel"]).setFill()
    _rounded(OUTER_PAD_X, card_y, inner_w, card_h, CORNER).fill()
    _color(pal["border"], pal["border_alpha"]).setStroke()
    path = _rounded(OUTER_PAD_X, card_y, inner_w, card_h, CORNER)
    path.setLineWidth_(1.0)
    path.stroke()

    left = OUTER_PAD_X + CARD_PAD
    right = OUTER_PAD_X + inner_w - CARD_PAD
    content_w = right - left

    for row, top in layout_rows(section):
        if row.get("type") == "balance":
            _draw_text(row.get("label", ""), left, top, 11.5, _color(pal["muted"]))
            _draw_text(str(row.get("value") or ""), left, top, 11.5,
                       _color(pal["fg"]), bold=True, right_edge=right)
            continue

        accent = _color(pal[_severity_key(row.get("severity"))])
        _draw_text(row.get("label", ""), left, top, 11.5, _color(pal["fg"]), bold=True)

        bar_y = top + ROW_LABEL_H + BAR_GAP
        _color(pal["sunken"]).setFill()
        _rounded(left, bar_y, content_w, BAR_H, BAR_CORNER).fill()
        filled = content_w * _fill_fraction(row)
        if filled > 0:
            accent.setFill()
            _rounded(left, bar_y, filled, BAR_H, BAR_CORNER).fill()

        meta_y = bar_y + BAR_H + BAR_GAP
        _draw_text(str(row.get("right") or ""), left, meta_y, 10.5, accent, bold=True)
        resets = row.get("resets")
        if resets:
            _draw_text(str(resets), left, meta_y, 10.5, _color(pal["dim"]),
                       right_edge=right)

    top = spark_top(section)
    if top is not None:
        _draw_spark(section.get("trend") or (), left, top, content_w, pal)


def _fill_fraction(row: Dict[str, Any]) -> float:
    """How much of the track to paint, from the unicode bar the spec carries.

    Reusing the spec's bar keeps the drawn meter and the text fallback in exact
    agreement; deriving a second percentage here is how the two drift apart.
    """
    bar = row.get("bar") or ""
    if not bar:
        return 0.0
    filled = sum(1 for ch in bar if ch == "▰")
    return max(0.0, min(1.0, filled / float(len(bar))))


def _draw_spark(values: Sequence[float], x: float, y: float, width: float,
                pal: Dict[str, Any]) -> None:
    bars = spark_bars(values)
    if not bars:
        return
    gap = 2.0
    bar_w = max(1.0, (width - gap * (len(bars) - 1)) / len(bars))
    accent = _color(pal["ok"], 0.85)
    track = _color(pal["sunken"])
    for index, value in enumerate(bars):
        bx = x + index * (bar_w + gap)
        track.setFill()
        _rounded(bx, y, bar_w, SPARK_H, 1.5).fill()
        h = max(1.5, SPARK_H * value)
        accent.setFill()
        # Flipped coordinates: grow the bar upward from the baseline.
        _rounded(bx, y + (SPARK_H - h), bar_w, h, 1.5).fill()


def _text_width(text: str, size: float, bold: bool) -> float:
    from AppKit import NSFont, NSFontAttributeName
    from Foundation import NSAttributedString
    font = NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size)
    string = NSAttributedString.alloc().initWithString_attributes_(
        text, {NSFontAttributeName: font})
    return float(string.size().width)


def _draw_footer_body(view: Any, spec: Dict[str, Any], width: float) -> None:
    pal = palette(_is_dark(view))
    left = OUTER_PAD_X + CARD_PAD
    right = width - OUTER_PAD_X - CARD_PAD
    _draw_text(str(spec.get("version") or ""), left, 7.0, 10.0, _color(pal["dim"]))
    _draw_text(str(spec.get("next_update") or ""), left, 7.0, 10.0,
               _color(pal["dim"]), right_edge=right)


_CLASSES: Dict[str, Any] = {}


def _view_classes():
    """Define the two NSView subclasses once, on first use.

    Built lazily so this module imports cleanly without PyObjC. Both views are
    flipped so layout arithmetic reads top-down, matching the pure functions.
    """
    if _CLASSES:
        return _CLASSES
    from AppKit import NSView

    class TTQuotaCardView(NSView):
        def isFlipped(self):
            return True

        def drawRect_(self, rect):
            section = getattr(self, "_tt_section", None)
            if not section:
                return
            try:
                _draw_card_body(self, section, float(self.frame().size.width))
            except Exception as exc:  # pragma: no cover - drawing is best-effort
                logger.debug("menubar card draw failed: %s", exc)

    class TTFooterView(NSView):
        def isFlipped(self):
            return True

        def drawRect_(self, rect):
            spec = getattr(self, "_tt_footer", None)
            if not spec:
                return
            try:
                _draw_footer_body(self, spec, float(self.frame().size.width))
            except Exception as exc:  # pragma: no cover - drawing is best-effort
                logger.debug("menubar footer draw failed: %s", exc)

    _CLASSES["card"] = TTQuotaCardView
    _CLASSES["footer"] = TTFooterView
    return _CLASSES


def build_card_view(section: Dict[str, Any], width: float = WIDTH):
    """An NSView drawing one provider card, sized for ``NSMenuItem.setView_``."""
    from Foundation import NSMakeRect
    cls = _view_classes()["card"]
    view = cls.alloc().initWithFrame_(NSMakeRect(0, 0, width, card_height(section)))
    view._tt_section = section
    return view


def build_footer_view(spec: Dict[str, Any], width: float = WIDTH):
    """An NSView drawing the version / next-update line under the cards."""
    from Foundation import NSMakeRect
    cls = _view_classes()["footer"]
    view = cls.alloc().initWithFrame_(NSMakeRect(0, 0, width, footer_height()))
    view._tt_footer = spec
    return view
