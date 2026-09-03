"""Custom ``NSView`` rendering for the menu-bar quota cards.

The text menu (``render._row_menu_item``) can only ever be one line of glyphs
per row, so a unicode bar is as close to a progress meter as it gets. This
module draws the real thing: a compact card per provider, a brand mark, a plan
badge, and a drawn track-and-fill meter per window, in the TokenTelemetry
palette.

Two layers, deliberately separated the same way ``render`` splits spec from
rumps:

* the ``*_height`` / ``layout_*`` / ``panel_width`` functions are pure
  arithmetic with NO macOS imports, so the sizing that decides whether a card is
  clipped is unit-testable on any platform;
* the view classes are built lazily inside functions, so importing this module
  on Linux or Windows never touches Cocoa.

Every view is attached with ``NSMenuItem.setView_``. A view-backed item draws
its own content and, unlike an attributed title, is not truncated by the menu's
own text layout -- which is what makes this layout possible at all.

LENGTH IS A FEATURE CONSTRAINT. A menu that runs past the bottom of the screen
is unusable, and a user with six signed-in providers has six cards. Each window
is therefore TWO lines, not three: the label and its remaining-percentage share
one line, the meter is the next, and the reset time rides on the first line
after the percentage. That is roughly half the height of a stacked layout and
is the single biggest reason the panel fits.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger("tokentelemetry.menubar.cards")

# --- geometry (pure, no AppKit) ----------------------------------------------
# Heights are fixed rather than measured. A menu item must report its size
# BEFORE the menu opens, so anything derived from live text metrics would be a
# guess anyway; fixed rows keep every card aligned to the same grid.

# Width adapts to the display (see panel_width). These bound it: narrower than
# MIN truncates provider names, wider than MAX looks like a window rather than a
# menu, and neither extreme is worth allowing on an unusual screen.
MIN_WIDTH = 260.0
MAX_WIDTH = 360.0
WIDTH = 300.0  # fallback when no screen can be read

OUTER_PAD_X = 8.0
CARD_PAD = 9.0

ICON_W = 21.0            # brand mark beside the provider name (fits two letters)
ICON_H = 14.0
HEADER_H = 16.0          # provider name row, drawn INSIDE the card (see below)
HEADER_GAP = 7.0
ROW_LABEL_H = 14.0       # "Weekly" and "81% left · 1d 16h" share this line
BAR_GAP = 4.0
BAR_H = 5.0
ROW_GAP = 9.0
BALANCE_H = 16.0
CARD_GAP = 6.0

CORNER = 7.0
BAR_CORNER = 2.5
ICON_CORNER = 4.0


def panel_width(screen_width: Optional[float] = None) -> float:
    """Panel width for a display, clamped to the readable band.

    Scaled from the screen so the panel is not a postage stamp on a large
    display nor half the width of a small laptop. ``None`` (no screen readable)
    falls back to the fixed default rather than raising.
    """
    if not screen_width or screen_width <= 0:
        return WIDTH
    return max(MIN_WIDTH, min(MAX_WIDTH, round(float(screen_width) * 0.19)))


def row_height(row: Dict[str, Any]) -> float:
    """Height of one row inside a card."""
    if row.get("type") == "balance":
        return BALANCE_H
    return ROW_LABEL_H + BAR_GAP + BAR_H


def card_height(section: Dict[str, Any]) -> float:
    """Total height of one provider card, header included.

    The header is INSIDE the card. It used to sit above it, drawn straight onto
    the menu's own background -- which follows the system appearance, not this
    palette, so on a dark menu every provider name rendered near-black on near-
    black and disappeared. Keeping every drawn pixel on a surface this module
    paints itself removes the dependency entirely.
    """
    rows: Sequence[Dict[str, Any]] = section.get("rows") or ()
    inner = sum(row_height(r) for r in rows)
    if len(rows) > 1:
        inner += ROW_GAP * (len(rows) - 1)
    return CARD_PAD + HEADER_H + HEADER_GAP + inner + CARD_PAD


def layout_rows(section: Dict[str, Any]) -> List[Tuple[Dict[str, Any], float]]:
    """Each row paired with its top offset inside the card view (flipped coords)."""
    y = CARD_PAD + HEADER_H + HEADER_GAP
    placed: List[Tuple[Dict[str, Any], float]] = []
    for index, row in enumerate(section.get("rows") or ()):
        if index:
            y += ROW_GAP
        placed.append((row, y))
        y += row_height(row)
    return placed


def compact_resets(resets: Optional[str]) -> str:
    """"Resets in 1d 16h" -> "1d 16h".

    The word "Resets" is repeated on every row of every card, so it costs width
    on the one line that is already carrying two values. The remaining duration
    is the part that differs.
    """
    if not resets:
        return ""
    text = str(resets).strip()
    for prefix in ("Resets in ", "Resets "):
        if text.startswith(prefix):
            return text[len(prefix):]
    return text


def meta_text(row: Dict[str, Any]) -> str:
    """The right-hand value on a window's first line: "81% left · 1d 16h"."""
    right = str(row.get("right") or "")
    resets = compact_resets(row.get("resets"))
    if right and resets:
        return f"{right} · {resets}"
    return right or resets


# --- palette ------------------------------------------------------------------
# Mirrors frontend/src/app/globals.css.

_LIGHT = {
    "panel": (0xFB, 0xFB, 0xFD), "sunken": (0xE8, 0xEA, 0xF0),
    "border": (0x0F, 0x17, 0x2A), "border_alpha": 0.10,
    "fg": (0x1A, 0x1F, 0x2B), "muted": (0x4B, 0x55, 0x66), "dim": (0x6B, 0x74, 0x88),
    "ok": (0x25, 0x63, 0xEB), "warn": (0xB4, 0x53, 0x09), "crit": (0xBE, 0x12, 0x3C),
}
_DARK = {
    "panel": (0x11, 0x14, 0x1A), "sunken": (0x07, 0x09, 0x0D),
    "border": (0xFF, 0xFF, 0xFF), "border_alpha": 0.10,
    "fg": (0xE8, 0xEA, 0xF0), "muted": (0x9A, 0xA1, 0xAD), "dim": (0x5F, 0x66, 0x75),
    "ok": (0x60, 0xA5, 0xFA), "warn": (0xFC, 0xD3, 0x4D), "crit": (0xFD, 0xA4, 0xAF),
}

# The panel is deliberately light in both appearances. macOS menus are a light
# surface by default and a dark card inside one reads as a foreign element; the
# dark palette is kept so switching back is a one-line change, not a rewrite.
FORCE_LIGHT = True


def palette(dark: bool = False) -> Dict[str, Any]:
    if FORCE_LIGHT:
        return _LIGHT
    return _DARK if dark else _LIGHT


# Brand tints, mirroring frontend/src/lib/agents.ts so a provider is the same
# colour in the menu as on the dashboard. Only the harnesses that can report a
# live quota need an entry; anything else falls back to the neutral slate.
AGENT_HEX = {
    "claude": (0xF9, 0x73, 0x16), "codex": (0xA8, 0x55, 0xF7),
    "gemini": (0x06, 0xB6, 0xD4), "antigravity": (0x10, 0xB9, 0x81),
    "qwen": (0x3B, 0x82, 0xF6), "vibe": (0xF4, 0x72, 0xB6),
    "cursor": (0x60, 0xA5, 0xFA), "copilot": (0x63, 0x66, 0xF1),
    "opencode": (0xF5, 0x9E, 0x0B), "hermes": (0xEA, 0xB3, 0x08),
    "grok": (0x71, 0x71, 0x7A), "cline": (0x7C, 0x3A, 0xED),
    "smallcode": (0x0D, 0x94, 0x88), "pi": (0x71, 0x71, 0x7A),
    "muse": (0x25, 0x63, 0xEB), "prime": (0x84, 0xA3, 0x0C),
    "dsh": (0x4D, 0x6B, 0xFE), "qoder": (0x71, 0x71, 0x7A),
}
AGENT_FALLBACK = (0x64, 0x74, 0x8B)


def agent_color(provider_id: Optional[str]) -> Tuple[int, int, int]:
    return AGENT_HEX.get((provider_id or "").lower(), AGENT_FALLBACK)


# Curated two-letter marks, because no derivable rule separates these names:
# Claude/Codex/Cursor/Copilot/Cline all begin with C, and first-two-letters
# collides Codex with Copilot ("CO"). Every entry here is unique by
# construction and pinned by a test.
AGENT_MARK = {
    "claude": "CC", "codex": "CX", "cursor": "CU", "copilot": "CP",
    "opencode": "OC", "grok": "GK", "gemini": "GM", "antigravity": "AG",
    "qwen": "QW", "vibe": "VB", "hermes": "HM", "cline": "CL",
    "smallcode": "SC", "pi": "PI", "muse": "MU", "prime": "PR",
    "dsh": "DS", "qoder": "QO",
}


def agent_monogram(provider_id: Optional[str], provider_name: Optional[str]) -> str:
    """A two-letter mark standing in for the harness logo.

    The dashboard draws real marks from a React icon package that a native
    NSView cannot use, and copying vendor logo artwork into this repo is a
    licensing question rather than a drawing one.

    TWO letters, not one, and curated rather than derived: five supported
    harnesses begin with C, so a single initial identifies nothing, and taking
    the first two letters makes Codex and Copilot both "CO". An agent added to
    the backend before this map still gets a readable mark from the fallback.
    """
    known = AGENT_MARK.get((provider_id or "").lower())
    if known:
        return known
    source = (provider_name or provider_id or "").strip()
    if not source:
        return "?"
    words = [w for w in source.split() if w]
    if len(words) >= 2:
        return (words[0][:1] + words[1][:1]).upper()
    return words[0][:2].upper()


def _color(rgb: Tuple[int, int, int], alpha: float = 1.0):
    from AppKit import NSColor
    r, g, b = rgb
    return NSColor.colorWithSRGBRed_green_blue_alpha_(r / 255.0, g / 255.0, b / 255.0, alpha)


def _severity_key(severity: Optional[str]) -> str:
    return severity if severity in ("ok", "warn", "crit") else "ok"


def _draw_text(text: str, x: float, y: float, size: float, color: Any,
               bold: bool = False, right_edge: Optional[float] = None) -> None:
    from AppKit import NSFont, NSFontAttributeName, NSForegroundColorAttributeName
    from Foundation import NSAttributedString, NSMakePoint

    if not text:
        return
    font = NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size)
    attrs = {NSFontAttributeName: font, NSForegroundColorAttributeName: color}
    string = NSAttributedString.alloc().initWithString_attributes_(text, attrs)
    if right_edge is not None:
        x = right_edge - string.size().width
    string.drawAtPoint_(NSMakePoint(x, y))


def _text_width(text: str, size: float, bold: bool) -> float:
    from AppKit import NSFont, NSFontAttributeName
    from Foundation import NSAttributedString
    font = NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size)
    string = NSAttributedString.alloc().initWithString_attributes_(
        text, {NSFontAttributeName: font})
    return float(string.size().width)


def _rounded(x: float, y: float, w: float, h: float, radius: float):
    from AppKit import NSBezierPath
    from Foundation import NSMakeRect
    return NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(x, y, max(0.0, w), max(0.0, h)), radius, radius)


def _draw_brand_mark(provider_id: Optional[str], provider_name: Optional[str],
                     x: float, y: float) -> None:
    tint = agent_color(provider_id)
    _color(tint, 0.16).setFill()
    _rounded(x, y, ICON_W, ICON_H, ICON_CORNER).fill()
    letters = agent_monogram(provider_id, provider_name)
    width = _text_width(letters, 8.5, True)
    _draw_text(letters, x + (ICON_W - width) / 2.0, y + 1.5, 8.5, _color(tint), bold=True)


def _draw_card_body(view: Any, section: Dict[str, Any], width: float) -> None:
    """Paint one provider card. Flipped coordinates: y grows downward."""
    pal = palette()
    inner_w = width - (OUTER_PAD_X * 2)
    total_h = card_height(section)

    # The card surface is painted FIRST and spans the whole view, so everything
    # after this draws onto a colour this module controls rather than onto the
    # menu's own background.
    _color(pal["panel"]).setFill()
    _rounded(OUTER_PAD_X, 0.0, inner_w, total_h, CORNER).fill()
    path = _rounded(OUTER_PAD_X, 0.0, inner_w, total_h, CORNER)
    _color(pal["border"], pal["border_alpha"]).setStroke()
    path.setLineWidth_(1.0)
    path.stroke()

    left = OUTER_PAD_X + CARD_PAD
    right = OUTER_PAD_X + inner_w - CARD_PAD
    content_w = right - left

    provider_id = section.get("provider_id")
    name = section.get("provider_name") or section.get("title") or ""
    _draw_brand_mark(provider_id, name, left, CARD_PAD + 1.0)
    text_x = left + ICON_W + 6.0
    _draw_text(name, text_x, CARD_PAD, 12.0, _color(pal["fg"]), bold=True)
    plan = section.get("plan")
    if plan:
        _draw_text(plan, text_x + _text_width(name, 12.0, True) + 6.0,
                   CARD_PAD + 1.5, 9.5, _color(pal["dim"]))

    for row, top in layout_rows(section):
        if row.get("type") == "balance":
            _draw_text(row.get("label", ""), left, top, 10.5, _color(pal["muted"]))
            _draw_text(str(row.get("value") or ""), left, top, 10.5,
                       _color(pal["fg"]), bold=True, right_edge=right)
            continue

        # Colour codes the meter by how close the window is to its ceiling,
        # using the dashboard's own thresholds, so amber and red mean the same
        # thing in both places.
        accent = _color(pal[_severity_key(row.get("severity"))])
        _draw_text(row.get("label", ""), left, top, 10.5, _color(pal["fg"]), bold=True)
        _draw_text(meta_text(row), left, top, 10.0, accent, bold=True, right_edge=right)

        bar_y = top + ROW_LABEL_H + BAR_GAP
        _color(pal["sunken"]).setFill()
        _rounded(left, bar_y, content_w, BAR_H, BAR_CORNER).fill()
        filled = content_w * _fill_fraction(row)
        if filled > 0:
            accent.setFill()
            _rounded(left, bar_y, filled, BAR_H, BAR_CORNER).fill()


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

    _CLASSES["card"] = TTQuotaCardView
    return _CLASSES


def screen_width() -> Optional[float]:
    """Width of the main display in points, or None when it cannot be read."""
    try:
        from AppKit import NSScreen
        screen = NSScreen.mainScreen()
        return float(screen.frame().size.width) if screen else None
    except Exception:  # pragma: no cover - screen probe is best-effort
        return None


def current_width() -> float:
    return panel_width(screen_width())


def build_card_view(section: Dict[str, Any], width: Optional[float] = None):
    """An NSView drawing one provider card, sized for ``NSMenuItem.setView_``."""
    from Foundation import NSMakeRect
    width = current_width() if width is None else width
    cls = _view_classes()["card"]
    view = cls.alloc().initWithFrame_(
        NSMakeRect(0, 0, width, card_height(section) + CARD_GAP))
    view._tt_section = section
    return view
