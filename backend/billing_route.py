"""Drain-priority billing routes: which credit *bucket* pays for a session.

``billing_mode.py`` answers a coarse question — "how should we *frame* this
agent's cost?" (subscription / api / local / unknown). That single label is no
longer enough, because as of mid-2026 every major provider bills a single agent
through **multiple buckets with a drain order**, and *which* bucket pays depends
on the **task type** (interactive vs programmatic). The flat label literally
can't represent this — it would call all Claude usage "subscription" → $0, while
a ``claude -p`` loop silently drains a separate, capped, no-fallback credit pool.

This module encodes, per agent, an ordered list of buckets and resolves the
**active bucket** for a given task type. It changes no cost math by itself; it
tells the caller (and the UI) *which* bucket is being drained, what the user's
marginal cost is while it's active, and when a capped pool is about to run dry.

Provider facts baked in below are a **snapshot** (see ``SNAPSHOT_AS_OF``) and
are wrong the moment a provider changes terms — re-verify against current
provider docs before trusting the numbers. Policies with a future effective
date are date-gated (e.g. Anthropic's June 15 2026 Agent-SDK split): resolution
takes ``today`` and only routes through a bucket once its policy is in force.

Key concepts
------------
``charges`` — what the *user* pays at the margin while this bucket is active:
  - ``included``     — already paid via the subscription/credit pool → marginal $0.
  - ``api_rate``     — billed at API list price (paygo, or pool-overflow).
  - ``electricity``  — local hardware; priced by ``power_config`` (not here).

``pool_usd`` — size of a prepaid pool *measured at API rates* (e.g. Anthropic's
  Agent-SDK credit: $20 Pro / $100 Max-5x / $200 Max-20x). Even when ``charges``
  is ``included`` (marginal $0), API-rate value still accrues against this cap so
  the UI can warn before it empties. ``None`` = no metered dollar cap.

``pool_requests`` — request-count cap for pools metered in calls, not dollars
  (Gemini CLI's 1,000 requests/day free tier). ``pool_period`` says how often it
  resets (``"day"`` / ``"month"``).

``no_spillover`` — when a pool is exhausted, requests **stop**; there is no
  automatic fall-through to the next bucket unless the user opts into overflow.
  (Anthropic's June-15 split is the canonical case: no rollover, no auto-paygo.)

``task_types`` — which task types route to this bucket: ``("interactive",)``,
  ``("programmatic",)``, or both.

Bucket resolution itself is pure (no I/O). The only I/O here is the explicit
per-agent *plan* persistence (``load_plans`` / ``save_plan`` →
``~/.tokentelemetry/billing_plans.json``), which mirrors billing_mode's
override file and never raises on missing/malformed data.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from tt_paths import data_dir

# When the provider facts below were last verified against live sources.
# Surfaced in API payloads so the UI can disclaim staleness.
SNAPSHOT_AS_OF = "2026-06-11"

# Task types a session can be. "interactive" = a human at a terminal/editor;
# "programmatic" = headless/automated (claude -p, Agent SDK, GitHub Actions,
# codex app-server, CI). Default to interactive when unknown — it's the
# conservative, common case and never over-reports a separate metered pool.
TASK_TYPES = ("interactive", "programmatic")
DEFAULT_TASK_TYPE = "interactive"

CHARGES = ("included", "api_rate", "electricity")

DEFAULT_PLAN = "default"

# Anthropic's Agent-SDK billing split: announced May 13 2026, in force from
# June 15 2026. Before this date programmatic usage still draws subscription
# limits; from this date it draws the separate SDK credit pool.
ANTHROPIC_SDK_SPLIT_DATE = _dt.date(2026, 6, 15)

# Plan vocabularies are PER-PROVIDER — "max5x" means nothing to Cursor and
# "ultra" nothing to Anthropic. Used to validate persisted plan choices.
AGENT_PLANS: Dict[str, Tuple[str, ...]] = {
    "claude": ("pro", "max5x", "max20x"),
    "copilot": ("pro_plus", "business", "enterprise"),
    "cursor": ("pro", "pro_plus", "ultra"),
}


def _bucket(
    id: str,
    label: str,
    charges: str,
    task_types: Tuple[str, ...],
    *,
    pool_usd: Optional[float] = None,
    pool_requests: Optional[int] = None,
    pool_period: Optional[str] = None,
    no_spillover: bool = False,
    note: str = "",
) -> Dict[str, Any]:
    return {
        "id": id,
        "label": label,
        "charges": charges,
        "task_types": list(task_types),
        "pool_usd": pool_usd,
        "pool_requests": pool_requests,
        "pool_period": pool_period,
        "no_spillover": no_spillover,
        "note": note,
    }


# Per-plan Agent-SDK credit pool for Anthropic (USD/month, measured at API
# rates). Pro $20 / Max-5x $100 / Max-20x $200.
# https://thenewstack.io/anthropic-agent-sdk-credits/
_ANTHROPIC_SDK_POOL = {"default": 20.0, "pro": 20.0, "max5x": 100.0, "max20x": 200.0}

# GitHub Copilot moved to usage-based AI Credits on June 1 2026 (1 credit =
# $0.01). Monthly included credit ≈ plan price for Pro+/Business/Enterprise.
# https://github.blog/news-insights/company-news/github-copilot-is-moving-to-usage-based-billing/
_COPILOT_POOL = {"default": 39.0, "pro_plus": 39.0, "business": 19.0, "enterprise": 39.0}

# Cursor's included credit pool equals the subscription value
# ($20 Pro / $60 Pro+ / $200 Ultra). https://www.vantage.sh/blog/cursor-pricing-explained
_CURSOR_POOL = {"default": 20.0, "pro": 20.0, "pro_plus": 60.0, "ultra": 200.0}


def _today(today: Optional[_dt.date]) -> _dt.date:
    return today or _dt.date.today()


# ---------------------------------------------------------------------------
# Per-agent bucket definitions (drain order, top = drains first).
#
# Each builder takes (plan, today) so pool sizes can vary by tier and policies
# with a future effective date only kick in once in force. Order is the
# *priority* order; resolution filters by task type, then takes the first match.
# ---------------------------------------------------------------------------
def _anthropic_buckets(plan: str, today: _dt.date) -> List[Dict[str, Any]]:
    sdk_pool = _ANTHROPIC_SDK_POOL.get(plan, _ANTHROPIC_SDK_POOL["default"])

    if today < ANTHROPIC_SDK_SPLIT_DATE:
        # Pre-split: one subscription pool covers interactive AND programmatic.
        # The note pre-warns about the upcoming change so users aren't surprised.
        return [
            _bucket(
                "subscription", "Subscription limits", "included",
                ("interactive", "programmatic"),
                no_spillover=True,
                note=(f"Until {ANTHROPIC_SDK_SPLIT_DATE.isoformat()} all Claude "
                      "usage draws your plan's limits. From that date, claude -p "
                      "/ Agent SDK / GitHub Actions move to a separate "
                      f"${sdk_pool:.0f}/mo SDK credit pool with no auto-fallback."),
            ),
        ]

    return [
        # Programmatic drains the separate Agent-SDK credit pool FIRST and only.
        _bucket(
            "sdk_credit", "Agent SDK credit", "included", ("programmatic",),
            pool_usd=sdk_pool, pool_period="month", no_spillover=True,
            note=("claude -p / Agent SDK / GitHub Actions draw a separate "
                  f"${sdk_pool:.0f}/mo pool, billed at API rates. No rollover, "
                  "no auto-fallback — automation stops at $0 unless overflow "
                  "billing is enabled."),
        ),
        # Overflow paygo for programmatic, only reached if the user opted in.
        _bucket(
            "api_overflow", "Usage credits / API key", "api_rate", ("programmatic",),
            note="Pay-as-you-go overflow once the SDK credit pool is empty (opt-in).",
        ),
        # Interactive use draws normal subscription limits — separate, no spillover.
        _bucket(
            "subscription", "Subscription limits", "included", ("interactive",),
            no_spillover=True,
            note=("Interactive Claude Code / chat / Cowork draw your plan's "
                  "usage limits — unaffected by the Agent-SDK split."),
        ),
    ]


def _codex_buckets(plan: str, today: _dt.date) -> List[Dict[str, Any]]:
    # One ChatGPT subscription OAuth bucket covers BOTH interactive Codex CLI and
    # programmatic codex app-server. Bills against plan-included usage, then
    # purchased credits. https://developers.openai.com/codex/pricing
    return [
        _bucket(
            "subscription", "ChatGPT subscription", "included",
            ("interactive", "programmatic"),
            note=("One ChatGPT plan covers both interactive Codex CLI and the "
                  "programmatic app-server — no separate SDK credit."),
        ),
        _bucket(
            "api_paygo", "Purchased credits / API", "api_rate",
            ("interactive", "programmatic"),
            note="Per-token API rates once plan-included usage is spent.",
        ),
    ]


def _gemini_buckets(plan: str, today: _dt.date) -> List[Dict[str, Any]]:
    # Gemini CLI: generous free tier capped by REQUEST COUNT (not dollars),
    # then API paygo. https://www.termdock.com/en/blog/free-ai-cli-tools-ranked
    return [
        _bucket(
            "free_tier", "Free tier", "included", ("interactive", "programmatic"),
            pool_requests=1000, pool_period="day",
            note="1,000 free model requests per day; Google absorbs the compute.",
        ),
        _bucket(
            "api_paygo", "API key", "api_rate", ("interactive", "programmatic"),
            note="Per-token API rates beyond the free quota.",
        ),
    ]


def _copilot_buckets(plan: str, today: _dt.date) -> List[Dict[str, Any]]:
    pool = _COPILOT_POOL.get(plan, _COPILOT_POOL["default"])
    return [
        # Completions are unlimited/free and never touch credits — model that as
        # an always-on included bucket for interactive completion-style use.
        _bucket(
            "completions", "Code completions", "included", ("interactive",),
            note="Inline completions & next-edit suggestions stay free/unlimited.",
        ),
        _bucket(
            "ai_credits", "Monthly AI credits", "included",
            ("interactive", "programmatic"),
            pool_usd=pool, pool_period="month",
            note=(f"Chat / agents / Copilot CLI consume a ${pool:.0f}/mo AI-credit "
                  "pool (1 credit = $0.01)."),
        ),
        _bucket(
            "usage_overage", "Usage-based overage", "api_rate",
            ("interactive", "programmatic"),
            note="Metered overage once monthly AI credits are spent.",
        ),
    ]


def _cursor_buckets(plan: str, today: _dt.date) -> List[Dict[str, Any]]:
    pool = _CURSOR_POOL.get(plan, _CURSOR_POOL["default"])
    return [
        # Auto / Composer agentic mode is unlimited on paid plans → included, no cap.
        _bucket(
            "auto_mode", "Auto / Composer (unlimited)", "included",
            ("interactive", "programmatic"),
            note="Auto and Composer agentic coding are unlimited on paid plans.",
        ),
        _bucket(
            "included_credits", "Included model credits", "included",
            ("interactive", "programmatic"),
            pool_usd=pool, pool_period="month",
            note=(f"Premium models burn a ${pool:.0f}/mo credit pool (equal to your "
                  "subscription), priced by model + context."),
        ),
        _bucket(
            "usage_overage", "Usage-based overage", "api_rate",
            ("interactive", "programmatic"),
            note="Metered overage once included model credits are spent.",
        ),
    ]


def _api_only_buckets(plan: str, today: _dt.date) -> List[Dict[str, Any]]:
    # Grok (xAI key), Hermes (provider keys), OpenCode (BYO key): pure paygo.
    return [
        _bucket(
            "api_paygo", "API key", "api_rate", ("interactive", "programmatic"),
            note="Pay-per-token on your own API key — the estimate approximates "
                 "your bill.",
        ),
    ]


def _local_buckets(plan: str, today: _dt.date) -> List[Dict[str, Any]]:
    return [
        _bucket(
            "electricity", "Local electricity", "electricity",
            ("interactive", "programmatic"),
            note="Self-hosted; priced by power_config (watts × time × tariff), "
                 "not an API charge.",
        ),
    ]


# agent → builder. Agents absent here fall back by billing-mode (see resolve).
_AGENT_BUILDERS = {
    "claude": _anthropic_buckets,
    "codex": _codex_buckets,
    "gemini": _gemini_buckets,
    "copilot": _copilot_buckets,
    "cursor": _cursor_buckets,
    "grok": _api_only_buckets,
    "hermes": _api_only_buckets,
    "opencode": _api_only_buckets,
}

# Fallback builders keyed by coarse billing-mode for agents without a bespoke
# bucket table (keeps the engine total — every agent resolves to *something*).
_MODE_FALLBACK = {
    "subscription": lambda plan, today: [
        _bucket("subscription", "Subscription", "included",
                ("interactive", "programmatic"),
                note="Flat monthly plan — marginal per-call cost is $0."),
    ],
    "api": _api_only_buckets,
    "local": _local_buckets,
    "unknown": lambda plan, today: [
        _bucket("unknown", "Unknown", "api_rate", ("interactive", "programmatic"),
                note="Billing not determined; figure shown at API list price."),
    ],
}


def buckets_for(
    agent: str,
    plan: str = DEFAULT_PLAN,
    mode: Optional[str] = None,
    today: Optional[_dt.date] = None,
) -> List[Dict[str, Any]]:
    """Full ordered bucket list for an agent (all task types), drain order.

    ``mode`` (a billing_mode value) is used only as a fallback for agents that
    have no bespoke table — it never overrides a bespoke one, *except* that a
    user who marks any agent ``local`` gets the electricity bucket (local
    re-pricing always wins, mirroring billing_mode's contract). ``today``
    date-gates policies that aren't in force yet (tests pass it explicitly;
    callers default to the real date so behavior flips automatically).
    """
    t = _today(today)
    if mode == "local":
        return _local_buckets(plan, t)
    builder = _AGENT_BUILDERS.get(agent)
    if builder is not None:
        return builder(plan, t)
    return _MODE_FALLBACK.get(mode or "unknown", _MODE_FALLBACK["unknown"])(plan, t)


def resolve_billing_route(
    agent: str,
    task_type: str = DEFAULT_TASK_TYPE,
    plan: str = DEFAULT_PLAN,
    mode: Optional[str] = None,
    today: Optional[_dt.date] = None,
) -> Dict[str, Any]:
    """Resolve the drain route for one (agent, task_type).

    Returns::

        {
          "agent": str,
          "task_type": "interactive" | "programmatic",
          "buckets": [ <bucket>, ... ],   # drain order, filtered to this task type
          "active": <bucket> | None,      # first bucket = what pays right now
          "charges": "included"|"api_rate"|"electricity"|None,  # active bucket's basis
          "marginal_cost_zero": bool,     # True iff the active bucket is `included`
                                          # (already paid; `electricity` is its own
                                          # non-API estimate and stays False)
          "capped": bool,                 # active bucket has a metered pool to warn on
        }

    Never raises; an unknown task type collapses to the default.
    """
    if task_type not in TASK_TYPES:
        task_type = DEFAULT_TASK_TYPE

    ordered = [b for b in buckets_for(agent, plan, mode, today)
               if task_type in b["task_types"]]
    active = ordered[0] if ordered else None
    charges = active["charges"] if active else None

    return {
        "agent": agent,
        "task_type": task_type,
        "plan": plan,
        "buckets": ordered,
        "active": active,
        "charges": charges,
        "marginal_cost_zero": charges == "included",
        "capped": bool(active and (active.get("pool_usd") is not None
                                   or active.get("pool_requests") is not None)),
    }


# Word-boundary patterns for programmatic entrypoints. Matched as whole tokens
# (split on space / slash / underscore / hyphen), NOT substrings — "interactions"
# must not match "actions", "claude-pro" must not match "-p", "pencil" not "ci".
_PROGRAMMATIC_TOKEN_RE = re.compile(
    r"(?:^|[\s/_-])"
    r"(p|print|headless|sdk|app-?server|github-?actions?|actions?|ci|cron|automation)"
    r"(?=$|[\s/_-])"
)


def classify_task_type(
    *,
    headless: Optional[bool] = None,
    source: Optional[str] = None,
) -> str:
    """Best-effort, conservative task-type classifier.

    Returns ``"programmatic"`` only on a clear signal (an explicit headless flag,
    or a source string containing a known automation entrypoint as a whole
    token); otherwise ``"interactive"``. Mirrors billing_mode's detectors:
    prefer the safe, common default over an over-eager guess that would surface
    a scary metered pool.
    """
    if headless is True:
        return "programmatic"
    s = (source or "").lower()
    if s and _PROGRAMMATIC_TOKEN_RE.search(s):
        return "programmatic"
    return "interactive"


# ---------------------------------------------------------------------------
# Per-agent plan persistence (~/.tokentelemetry/billing_plans.json:
# {"<agent>": "<plan>"}). Separate file from billing.json so the flat
# {agent: mode} schema there stays untouched/back-compatible.
# ---------------------------------------------------------------------------
def _plans_path() -> Path:
    return data_dir() / "billing_plans.json"


def load_plans() -> Dict[str, str]:
    """User-chosen plan per agent, validated against AGENT_PLANS.
    Missing/garbage file → empty dict (everyone on DEFAULT_PLAN)."""
    try:
        with open(_plans_path(), "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        str(a): p
        for a, p in raw.items()
        if isinstance(a, str) and p in AGENT_PLANS.get(a, ())
    }


def save_plan(agent: str, plan: Optional[str]) -> Dict[str, str]:
    """Set (or, with plan=None, clear) one agent's plan. Returns the full map.

    Invalid plans for that agent are rejected by the caller (endpoint) against
    AGENT_PLANS — here we trust ``plan`` is validated or None.
    """
    plans = load_plans()
    if plan is None:
        plans.pop(agent, None)
    else:
        plans[agent] = plan

    path = _plans_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(plans, f, indent=2)
    os.replace(tmp, path)
    return plans


def get_route_overview(
    agent: str,
    plan: str = DEFAULT_PLAN,
    mode: Optional[str] = None,
    today: Optional[_dt.date] = None,
) -> Dict[str, Any]:
    """Both task-type routes for an agent plus the full bucket list — the shape
    the Settings UI consumes to render the drain order and pool warnings."""
    return {
        "agent": agent,
        "plan": plan,
        "plans": list(AGENT_PLANS.get(agent, ())),
        "buckets": buckets_for(agent, plan, mode, today),
        "routes": {
            tt: resolve_billing_route(agent, tt, plan, mode, today)
            for tt in TASK_TYPES
        },
    }
