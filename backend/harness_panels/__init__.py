"""Per-agent harness panels.

The session scan tells you what every agent has in common: sessions, tokens,
cost. This package covers what each one keeps that the others don't — Codex's
cron schedules, Claude's background-job fleet, Copilot's premium-request billing
units, Grok's credit balance.

One endpoint serves all of them (`GET /agents/{agent}/panel`) returning a
uniform document, so a single frontend renderer draws any agent and adding an
agent is backend-only work. See `base.panel` for the document shape.

Scope is the agents listed in `website/content/docs/supported-agents.mdx`.
Modules are added here as they're built; an agent with no module simply reports
`installed: false` and its dashboard tile stays inert, which is the correct
behaviour rather than a gap.

Panels are built lazily when a user opens an agent page — never during the
session scan, which is already ~30 CPU-seconds behind a short cache.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict

from . import claude, codex, copilot, grok
from .base import not_installed

logger = logging.getLogger("tokentelemetry.harness_panels")

# agent key -> builder. Keys match frontend/src/lib/agents.ts.
BUILDERS: Dict[str, Callable[[], Dict[str, Any]]] = {
    "claude": claude.build,
    "codex": codex.build,
    "copilot": copilot.build,
    "grok": grok.build,
}

# Agents TokenTelemetry supports and scans for sessions, but which have no panel
# module yet. Listed explicitly so "no panel" is a known state rather than a
# silent miss, and so the frontend can tell "not built yet" from "not installed".
PLANNED = (
    "gemini", "antigravity", "qwen", "vibe", "cursor", "opencode", "cline",
    "smallcode", "pi", "muse", "prime", "dsh",
)

# Hermes already has its own richer sub-dashboard at /hermes/*; routing it here
# would duplicate that work with a thinner view.
EXCLUDED = ("hermes",)


def has_panel(agent: str) -> bool:
    return agent in BUILDERS


# Panels are dominated by directory sizing — ~/.claude is 182k files, so a cold
# build is hundreds of milliseconds even with scandir. Nothing here changes
# second to second, and the tile summary needs every agent at once, so a short
# process-local TTL turns a page open plus its tile refresh into one build.
# Deliberately in-memory: this is a derived view, not state worth persisting.
_TTL_SEC = 60.0
_cache: Dict[str, tuple[float, Dict[str, Any]]] = {}


def build_panel(agent: str, *, fresh: bool = False) -> Dict[str, Any]:
    """Build one agent's panel. Never raises — a broken extractor yields
    `installed: false` rather than a 500 that takes the agent page down."""
    builder = BUILDERS.get(agent)
    if builder is None:
        doc = not_installed(agent)
        doc["planned"] = agent in PLANNED
        return doc

    now = time.monotonic()
    if not fresh:
        hit = _cache.get(agent)
        if hit and (now - hit[0]) < _TTL_SEC:
            return hit[1]
    try:
        doc = builder()
    except Exception:
        logger.warning("panel build failed for %s", agent, exc_info=True)
        doc = not_installed(agent)
    _cache[agent] = (now, doc)
    return doc


def invalidate() -> None:
    """Drop cached panels. Called by the existing /cache/invalidate endpoint."""
    _cache.clear()


def panel_summary() -> Dict[str, int]:
    """Section count per agent, for the dashboard tiles.

    Lets the home page show "6 panels" on a tile and link only agents that have
    something behind them. Rides the same TTL cache as the agent pages, so
    opening an agent warms its tile and vice versa.
    """
    out: Dict[str, int] = {}
    for agent in BUILDERS:
        doc = build_panel(agent)
        if doc.get("installed"):
            out[agent] = len(doc.get("sections") or [])
    return out
