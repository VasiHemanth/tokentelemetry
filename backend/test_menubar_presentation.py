"""Unit tests for the headless menu-bar quota presentation model."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from menubar.presentation import build_menu_presentation, percent_left_text, resets_in_text


def test_presentation_selects_the_global_worst_window_with_stable_ties():
    presentation = build_menu_presentation({
        "schema": "tokentelemetry.quotas.v1",
        "providers": {
            "zeta": {
                "displayName": "Zeta",
                "plan": "Pro",
                "resources": {
                    "weekly": {"kind": "consumption", "unit": "percent", "used": 90, "limit": 100},
                },
            },
            "alpha": {
                "displayName": "Alpha",
                "resources": {
                    "monthly": {"kind": "consumption", "unit": "percent", "used": 90, "limit": 100},
                    "session": {"kind": "consumption", "unit": "percent", "used": 90, "limit": 100},
                },
            },
        },
        "capabilities": {},
        "errors": [],
    })

    assert presentation.state == "ready"
    assert presentation.title == "◔ 90%"
    assert presentation.severity == "crit"
    assert presentation.worst_window is not None
    assert (presentation.worst_window.provider_id, presentation.worst_window.resource_id) == ("alpha", "monthly")
    assert [(row.provider_id, row.resource_id, row.text) for row in presentation.rows] == [
        ("alpha", "monthly", "90% used"),
        ("alpha", "session", "90% used"),
        ("zeta", "weekly", "90% used"),
    ]


def test_presentation_clamps_percentage_and_formats_limit_reached_rows():
    presentation = build_menu_presentation({
        "providers": {
            "codex": {
                "displayName": "Codex",
                "plan": "Plus",
                "resources": {
                    "session": {"kind": "consumption", "unit": "percent", "used": 120, "limit": 100},
                    "credits": {"kind": "balance", "unit": "credits", "available": 5},
                },
            },
        },
        "capabilities": {},
        "errors": [],
    })

    assert presentation.title == "◔ 100%"
    session = next(row for row in presentation.rows if row.resource_id == "session")
    assert session.provider_name == "Codex"
    assert session.plan == "Plus"
    assert session.resource_label == "Session"
    assert session.text == "Limit reached"
    assert session.pct == 100


def test_presentation_uses_the_shared_warning_threshold_for_each_window():
    presentation = build_menu_presentation({
        "providers": {
            "claude": {
                "displayName": "Claude Code",
                "resources": {
                    "session": {"kind": "consumption", "unit": "percent", "used": 75, "limit": 100},
                },
            },
        },
        "capabilities": {},
        "errors": [],
    })

    assert presentation.severity == "warn"
    assert presentation.rows[0].severity == "warn"


def test_presentation_counts_not_supported_agents_without_treating_them_as_failures():
    presentation = build_menu_presentation({
        "providers": {},
        "capabilities": {
            "pi": {"displayName": "Pi", "state": "notSupported"},
            "muse": {"displayName": "Muse Code", "state": "notSupported"},
            "codex": {"displayName": "Codex", "state": "notSignedIn"},
        },
        "errors": [],
    })

    assert presentation.state == "no_data"
    assert presentation.title == "◔ No quota data"
    assert presentation.not_supported_count == 2
    assert presentation.failure_message is None


def test_presentation_distinguishes_loading_and_collection_failure_states():
    loading = build_menu_presentation(None, loading=True)
    failed = build_menu_presentation(None, failure="Could not refresh quota data.")

    assert (loading.state, loading.title, loading.failure_message) == ("loading", "◔ Loading…", None)
    assert (failed.state, failed.title, failed.failure_message) == (
        "failure", "◔ Quota unavailable", "Could not refresh quota data.",
    )


def test_presentation_adds_left_percent_resets_and_balance_amount_fields():
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)
    presentation = build_menu_presentation({
        "providers": {
            "codex": {
                "displayName": "Codex",
                "plan": "Plus",
                "resources": {
                    "weekly": {
                        "kind": "consumption", "unit": "percent", "used": 81, "limit": 100,
                        "resetsAt": (now + timedelta(days=1, hours=16)).isoformat(),
                    },
                    "session": {
                        "kind": "consumption", "unit": "percent", "used": 60, "limit": 100,
                        "resetsAt": (now + timedelta(hours=5)).isoformat(),
                    },
                    "extraUsage": {"kind": "spend", "unit": "usd", "used": 24.8},
                },
            },
        },
        "capabilities": {},
        "errors": [],
    }, now=now)

    weekly = next(row for row in presentation.rows if row.resource_id == "weekly")
    assert weekly.pct_left_text == "19% left"
    assert weekly.resets_text == "Resets in 1d 16h"

    session = next(row for row in presentation.rows if row.resource_id == "session")
    assert session.pct_left_text == "40% left"
    assert session.resets_text == "Resets in 5h 0m"

    extra = next(row for row in presentation.rows if row.resource_id == "extraUsage")
    assert extra.is_balance is True
    assert extra.amount_text == "$25 used"
    assert extra.pct_left_text is None
    assert extra.text == "$25 used"


def test_percent_left_text_and_resets_in_text_helpers():
    from datetime import datetime, timezone

    assert percent_left_text(90.0) == "10% left"
    assert percent_left_text(100.0) == "0% left"
    now = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)
    assert resets_in_text("2026-09-02T04:00:00Z", now=now) == "Resets in 1d 16h"
    assert resets_in_text("2026-08-31T17:00:00Z", now=now) == "Resets in 5h 0m"
    assert resets_in_text("2026-08-31T11:00:00Z", now=now) == "Resets now"
    assert resets_in_text(None, now=now) is None
    assert resets_in_text("garbage", now=now) is None
