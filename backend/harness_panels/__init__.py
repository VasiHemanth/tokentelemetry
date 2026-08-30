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

from . import claude, clis, codex, copilot, grok, hermes, ides
from .base import not_installed

logger = logging.getLogger("tokentelemetry.harness_panels")

# agent key -> builder. Keys match frontend/src/lib/agents.ts, and cover every
# agent in website/content/docs/supported-agents.mdx.
BUILDERS: Dict[str, Callable[..., Dict[str, Any]]] = {
    "claude": claude.build,
    "codex": codex.build,
    "copilot": copilot.build,
    "grok": grok.build,
    "gemini": ides.build_gemini,
    "antigravity": ides.build_antigravity,
    "cursor": ides.build_cursor,
    "qwen": clis.build_qwen,
    "opencode": clis.build_opencode,
    "cline": clis.build_cline,
    "vibe": clis.build_vibe,
    "muse": clis.build_muse,
    "prime": clis.build_prime,
    "pi": clis.build_pi,
    "dsh": clis.build_dsh,
    "qoder": clis.build_qoder,
    "smallcode": clis.build_smallcode,
    "hermes": hermes.build_hermes,
}

# Every supported agent now has an extractor, so nothing is merely planned.
# Kept as a named empty tuple rather than deleted: the frontend distinguishes
# "installed: false, planned: true" (we support it, no panel yet) from a plain
# "not installed", and a future agent should land here before it lands above.
PLANNED: tuple[str, ...] = ()

# Nothing is excluded. Hermes has a panel of its own now, but a narrow one:
# it carries only what its /hermes/* pages do not already show, and links
# out to them via the panel's `dashboard` field rather than restating them.
EXCLUDED: tuple[str, ...] = ()


def has_panel(agent: str) -> bool:
    return agent in BUILDERS


# Panels are dominated by directory sizing — ~/.claude is 182k files, so a cold
# build is hundreds of milliseconds even with scandir. Nothing here changes
# second to second, and the tile summary needs every agent at once, so a short
# process-local TTL turns a page open plus its tile refresh into one build.
# Deliberately in-memory: this is a derived view, not state worth persisting.
_TTL_SEC = 60.0
_cache: Dict[str, tuple[float, Dict[str, Any]]] = {}


def build_panel(agent: str, *, fresh: bool = False,
                with_disk: bool = True) -> Dict[str, Any]:
    """Build one agent's panel. Never raises — a broken extractor yields
    `installed: false` rather than a 500 that takes the agent page down.

    `with_disk=False` skips directory sizing, which is the expensive half of a
    build (~/.claude is 182k files). The tile summary only needs a section
    count, so it takes the cheap path; the agent page takes the full one. The
    two are cached separately because a disk-less document must never be served
    to a page that renders the disk card.
    """
    builder = BUILDERS.get(agent)
    if builder is None:
        doc = not_installed(agent)
        doc["planned"] = agent in PLANNED
        return doc

    key = agent if with_disk else f"{agent}:nodisk"
    now = time.monotonic()
    if not fresh:
        hit = _cache.get(key)
        if hit and (now - hit[0]) < _TTL_SEC:
            return hit[1]
    try:
        doc = builder(with_disk=with_disk)
    except Exception:
        logger.warning("panel build failed for %s", agent, exc_info=True)
        doc = not_installed(agent)
    _cache[key] = (now, doc)
    return doc


def invalidate() -> None:
    """Drop cached panels. Called by the existing /cache/invalidate endpoint."""
    _cache.clear()


def panel_summary() -> Dict[str, int]:
    """Section count per agent, for the dashboard tiles.

    This runs on the dashboard — the first page a user sees — so it skips disk
    sizing entirely. With it, summarising every agent meant walking a few
    hundred thousand files before the landing page could paint.
    """
    out: Dict[str, int] = {}
    for agent in BUILDERS:
        doc = build_panel(agent, with_disk=False)
        if doc.get("installed"):
            out[agent] = len(doc.get("sections") or [])
    return out
