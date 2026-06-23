"""Guardrail: telemetry payloads are content-free by construction.

This is the test that lets us honestly say "anonymous." If someone later adds a
careless emit() with a path, prompt, or project name in the props, these assertions
fail. The allowlist + enum + safe-scalar pipeline in telemetry.py must drop
everything that isn't an explicitly-named, benign field.
"""
from __future__ import annotations

import json

import telemetry


# Things that must NEVER appear anywhere in a serialized payload.
SENSITIVE = [
    "/Users/hemanth/secret-project",
    "C:\\Users\\me\\repo",
    "vasih462@gmail.com",
    "my-private-repo-name",
    "Why did that Codex run cost $4.20?",
    "sk-ant-supersecrettoken",
    "$4.20",
]

# A subset the SCALAR layer alone must reject (contains '/', '\\', '@', space, or
# '$'). Slug-shaped strings like "my-private-repo-name" intentionally pass the
# scalar charset — they're caught one layer up by the key-allowlist + enum, which
# is what `test_unknown_keys_are_dropped` / `test_enum_values_...` cover.
SCALAR_REJECTS = [
    "/Users/hemanth/secret-project",
    "C:\\Users\\me\\repo",
    "vasih462@gmail.com",
    "Why did that Codex run cost $4.20?",
    "$4.20",
]


def _blob(payload) -> str:
    return json.dumps(payload).lower()


def test_unknown_keys_are_dropped():
    out = telemetry._sanitize_props("page.viewed", {
        "route": "analytics",
        "path": "/Users/hemanth/secret-project",   # not allowlisted
        "repo": "my-private-repo-name",             # not allowlisted
        "prompt": "Why did that Codex run cost $4.20?",
    })
    assert out == {"route": "analytics"}


def test_safe_scalar_rejects_paths_emails_and_freetext():
    for bad in SCALAR_REJECTS:
        assert telemetry._safe_scalar(bad) is None, f"leaked: {bad!r}"
    # benign enum-shaped tokens survive
    assert telemetry._safe_scalar("local-only") == "local-only"
    assert telemetry._safe_scalar("ollama") == "ollama"


def test_enum_values_outside_the_set_become_other():
    out = telemetry._sanitize_props("analytics.filtered", {"dimension": "secret_custom_value"})
    assert out == {"dimension": "other"}
    out2 = telemetry._sanitize_props("trace.summarized", {"backend": "ollama", "outcome": "ok"})
    assert out2 == {"backend": "ollama", "outcome": "ok"}


def test_build_event_never_contains_sensitive_content():
    # Even a maliciously-stuffed props dict produces a clean payload.
    payload = telemetry.build_event("page.viewed", {
        "route": "/Users/hemanth/secret-project",   # path in a real field → enum → "other"
        "leaked_path": "/Users/hemanth/secret-project",
        "email": "vasih462@gmail.com",
        "prompt": "Why did that Codex run cost $4.20?",
    })
    blob = _blob(payload)
    for s in SENSITIVE:
        assert s.lower() not in blob, f"payload leaked {s!r}: {payload}"
    assert payload["props"]["route"] == "other"


def test_budget_feature_labels_survive_but_values_cannot():
    # The two budget adoption/conversion labels are allowlisted enum values.
    for label in ("budgets", "budget-set"):
        out = telemetry._sanitize_props("feature.used", {"name": label})
        assert out == {"name": label}
    # A made-up label collapses to "other" — never the raw string.
    assert telemetry._sanitize_props("feature.used", {"name": "budget-$150"}) == {"name": "other"}
    # A budget limit/amount stuffed into props can never leak: "limit_value"
    # isn't an allowlisted key for feature.used, so it's dropped entirely.
    out = telemetry._sanitize_props("feature.used", {"name": "budget-set", "limit_value": 150})
    assert out == {"name": "budget-set"}
    payload = telemetry.build_event("feature.used", {"name": "budget-set", "limit_value": 150, "currency": "usd"})
    assert "150" not in _blob(payload)


def test_unknown_event_name_is_bucketed():
    payload = telemetry.build_event("evil.exfiltrate", {"x": "/etc/passwd"})
    assert payload["eventName"] == "other"
    assert "/etc/passwd" not in _blob(payload)


def test_unknown_agents_are_bucketed(monkeypatch):
    telemetry.update_context(agents=["claude", "codex", "my-internal-secret-agent"])
    ctx = telemetry._context_props()
    assert "claude" in ctx["agents"] and "codex" in ctx["agents"]
    assert "my-internal-secret-agent" not in ctx["agents"]
    assert "other-agent" in ctx["agents"]
    assert ctx["agent_count"] == 3


def test_do_not_track_forces_off(monkeypatch):
    monkeypatch.setenv("DO_NOT_TRACK", "1")
    assert telemetry.env_forced_off() is True
    assert telemetry.enabled() is False


def test_tt_no_telemetry_forces_off(monkeypatch):
    monkeypatch.setenv("TT_NO_TELEMETRY", "1")
    assert telemetry.env_forced_off() is True
    assert telemetry.enabled() is False


def test_ci_does_not_emit(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert telemetry._is_ci() is True
    assert telemetry.enabled() is False


def test_emit_is_noop_when_disabled(monkeypatch):
    monkeypatch.setenv("DO_NOT_TRACK", "1")
    before = len(telemetry._SENT)
    telemetry.emit("page.viewed", {"route": "analytics"})
    assert len(telemetry._SENT) == before  # nothing recorded, nothing sent


def test_sample_payloads_cover_every_event():
    samples = telemetry.sample_payloads()
    names = {s["eventName"] for s in samples}
    assert names == set(telemetry._EVENT_PROPS.keys())
