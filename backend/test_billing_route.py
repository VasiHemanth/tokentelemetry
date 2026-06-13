"""Tests for the drain-priority billing-route engine (billing_route.py).

Snapshot-of-June-2026 provider rules — these assert the *structure* of the drain
order (which bucket pays first, marginal cost, capped pools, no-spillover,
effective dates), not exact dollar amounts beyond the documented pool sizes.
"""

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import billing_route as br

# Anthropic's split is date-gated; pin both sides of the boundary explicitly so
# these tests don't change meaning as the wall clock crosses June 15 2026.
PRE_SPLIT = dt.date(2026, 6, 14)
POST_SPLIT = dt.date(2026, 6, 15)


# ---------------------------------------------------------------------------
# Anthropic: the canonical June-15 split — interactive vs programmatic diverge,
# but ONLY once the policy is in force.
# ---------------------------------------------------------------------------
def test_anthropic_pre_split_programmatic_still_draws_subscription():
    r = br.resolve_billing_route("claude", "programmatic", today=PRE_SPLIT)
    assert r["active"]["id"] == "subscription"
    assert r["marginal_cost_zero"] is True
    assert r["capped"] is False
    # The pre-warning about the upcoming split is in the note.
    assert "2026-06-15" in r["active"]["note"]


def test_anthropic_interactive_draws_subscription_no_pool():
    r = br.resolve_billing_route("claude", "interactive", today=POST_SPLIT)
    assert r["active"]["id"] == "subscription"
    assert r["charges"] == "included"
    assert r["marginal_cost_zero"] is True
    assert r["capped"] is False
    assert r["active"]["no_spillover"] is True


def test_anthropic_programmatic_drains_sdk_credit_first_post_split():
    r = br.resolve_billing_route("claude", "programmatic", today=POST_SPLIT)
    assert r["active"]["id"] == "sdk_credit"
    # Marginal $0 while the prepaid pool lasts, but it's a *capped* pool we warn on.
    assert r["marginal_cost_zero"] is True
    assert r["capped"] is True
    assert r["active"]["pool_usd"] == 20.0          # Pro default
    assert r["active"]["pool_period"] == "month"
    assert r["active"]["no_spillover"] is True
    # Overflow paygo is the next bucket in drain order for programmatic.
    ids = [b["id"] for b in r["buckets"]]
    assert ids == ["sdk_credit", "api_overflow"]


def test_anthropic_plan_changes_sdk_pool_size():
    assert br.resolve_billing_route(
        "claude", "programmatic", plan="max5x", today=POST_SPLIT
    )["active"]["pool_usd"] == 100.0
    assert br.resolve_billing_route(
        "claude", "programmatic", plan="max20x", today=POST_SPLIT
    )["active"]["pool_usd"] == 200.0


def test_anthropic_interactive_never_sees_sdk_credit():
    r = br.resolve_billing_route("claude", "interactive", today=POST_SPLIT)
    assert all(b["id"] != "sdk_credit" for b in r["buckets"])


# ---------------------------------------------------------------------------
# Codex: ONE subscription bucket covers both task types (no SDK split).
# ---------------------------------------------------------------------------
def test_codex_single_bucket_both_task_types():
    interactive = br.resolve_billing_route("codex", "interactive")
    programmatic = br.resolve_billing_route("codex", "programmatic")
    assert interactive["active"]["id"] == "subscription"
    assert programmatic["active"]["id"] == "subscription"
    assert interactive["marginal_cost_zero"] and programmatic["marginal_cost_zero"]


# ---------------------------------------------------------------------------
# Gemini free tier (request-count cap), Copilot credits, Cursor pools.
# ---------------------------------------------------------------------------
def test_gemini_free_tier_is_request_capped():
    r = br.resolve_billing_route("gemini", "interactive")
    assert r["active"]["id"] == "free_tier"
    # The cap is requests/day, not dollars — and it still counts as capped.
    assert r["active"]["pool_usd"] is None
    assert r["active"]["pool_requests"] == 1000
    assert r["active"]["pool_period"] == "day"
    assert r["capped"] is True
    ids = [b["id"] for b in br.buckets_for("gemini")]
    assert ids == ["free_tier", "api_paygo"]


def test_copilot_completions_free_and_credits_capped():
    r = br.resolve_billing_route("copilot", "interactive")
    # Completions are the first interactive bucket and are free/unlimited.
    assert r["active"]["id"] == "completions"
    # The AI-credit bucket carries a metered pool.
    credits = next(b for b in r["buckets"] if b["id"] == "ai_credits")
    assert credits["pool_usd"] == 39.0


def test_cursor_pool_scales_with_plan():
    assert next(b for b in br.buckets_for("cursor", plan="ultra")
                if b["id"] == "included_credits")["pool_usd"] == 200.0


# ---------------------------------------------------------------------------
# API-only + local + fallbacks.
# ---------------------------------------------------------------------------
def test_api_only_agents_are_paygo():
    for agent in ("grok", "hermes", "opencode"):
        r = br.resolve_billing_route(agent)
        assert r["active"]["id"] == "api_paygo"
        assert r["charges"] == "api_rate"
        assert r["marginal_cost_zero"] is False


def test_local_mode_overrides_to_electricity():
    r = br.resolve_billing_route("claude", "programmatic", mode="local")
    assert r["active"]["id"] == "electricity"
    assert r["charges"] == "electricity"
    # Electricity is not an API charge, so marginal_cost_zero stays False.
    assert r["marginal_cost_zero"] is False


def test_unknown_agent_falls_back_by_mode():
    assert br.resolve_billing_route("weirdtool", mode="subscription")["active"]["id"] == "subscription"
    assert br.resolve_billing_route("weirdtool", mode="api")["active"]["id"] == "api_paygo"
    assert br.resolve_billing_route("weirdtool")["active"]["id"] == "unknown"


# ---------------------------------------------------------------------------
# Robustness + helpers.
# ---------------------------------------------------------------------------
def test_bad_task_type_collapses_to_default():
    r = br.resolve_billing_route("claude", "garbage", today=POST_SPLIT)
    assert r["task_type"] == "interactive"
    assert r["active"]["id"] == "subscription"


def test_classify_task_type_positive_signals():
    assert br.classify_task_type(headless=True) == "programmatic"
    assert br.classify_task_type(source="claude -p") == "programmatic"
    assert br.classify_task_type(source="codex app-server") == "programmatic"
    assert br.classify_task_type(source="github-actions") == "programmatic"
    assert br.classify_task_type(source="agent sdk") == "programmatic"
    assert br.classify_task_type(source="nightly cron job") == "programmatic"


def test_classify_task_type_no_substring_false_positives():
    # Whole-token matching: none of these contain a programmatic token as a word.
    assert br.classify_task_type(source="interactive terminal") == "interactive"
    assert br.classify_task_type(source="interactions panel") == "interactive"  # not "actions"
    assert br.classify_task_type(source="claude-pro session") == "interactive"  # not "-p"
    assert br.classify_task_type(source="pencil sketcher") == "interactive"     # not "ci"
    assert br.classify_task_type(source="printer-friendly view") == "interactive"  # not "print"
    assert br.classify_task_type() == "interactive"


def test_overview_has_both_routes_plans_and_all_buckets():
    ov = br.get_route_overview("claude", today=POST_SPLIT)
    assert set(ov["routes"]) == {"interactive", "programmatic"}
    assert ov["plans"] == ["pro", "max5x", "max20x"]
    # Full bucket list (all task types) is a superset of either single route.
    assert len(ov["buckets"]) >= len(ov["routes"]["programmatic"]["buckets"])


def test_every_known_agent_resolves():
    for agent in ("claude", "codex", "gemini", "copilot", "cursor",
                  "grok", "hermes", "opencode"):
        for tt in br.TASK_TYPES:
            for day in (PRE_SPLIT, POST_SPLIT):
                r = br.resolve_billing_route(agent, tt, today=day)
                assert r["active"] is not None, f"{agent}/{tt}/{day} had no active bucket"
                assert r["charges"] in br.CHARGES


# ---------------------------------------------------------------------------
# Per-agent plan persistence (billing_plans.json).
# ---------------------------------------------------------------------------
@pytest.fixture
def plans_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKENTELEMETRY_HOME", str(tmp_path))
    return tmp_path


def test_plans_roundtrip(plans_home):
    assert br.load_plans() == {}
    assert br.save_plan("claude", "max5x") == {"claude": "max5x"}
    assert br.load_plans() == {"claude": "max5x"}
    # Clearing reverts the agent to the default plan.
    assert br.save_plan("claude", None) == {}
    assert br.load_plans() == {}


def test_plans_invalid_values_dropped_on_load(plans_home):
    # A plan valid for one provider isn't valid for another ("ultra" is Cursor's).
    p = br._plans_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"claude": "ultra", "cursor": "ultra", "x": 3}))
    assert br.load_plans() == {"cursor": "ultra"}


def test_plans_garbage_file_is_empty(plans_home):
    p = br._plans_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not json")
    assert br.load_plans() == {}
