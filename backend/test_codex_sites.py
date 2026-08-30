"""Regression tests for Codex Sites published from a Codex session.

Run: pytest backend/test_codex_sites.py
"""
import asyncio
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import main  # noqa: E402


SID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
SITE_URL = "https://agentic-evaluation-plan.workspace.chatgpt.site"


def _jl(**data):
    return json.dumps(data) + "\n"


def _write_codex_session(codex_dir, records):
    transcript = (
        codex_dir
        / "sessions"
        / "2026"
        / "07"
        / "20"
        / f"rollout-2026-07-20T10-00-00-{SID}.jsonl"
    )
    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.write_text("".join(records), encoding="utf-8")


@pytest.fixture
def scan_env(tmp_path, monkeypatch):
    missing = tmp_path / "missing"
    for attr in (
        "CLAUDE_DIR", "GEMINI_DIR", "QWEN_DIR", "VIBE_DIR", "OLLAMA_DIR",
        "GROK_SESSIONS_DIR", "GROK_UNIFIED_LOG", "VSCODE_STORAGE", "CURSOR_STORAGE",
        "COPILOT_CLI_DIR", "ANTIGRAVITY_BRAIN_DIR", "ANTIGRAVITY_CLI_DIR",
        "HERMES_DIR", "PI_SESSIONS_DIR",
    ):
        monkeypatch.setattr(main, attr, missing / attr.lower())
    monkeypatch.setattr(main, "ANTIGRAVITY_BRAIN_SOURCES", [])
    monkeypatch.setattr(main, "ANTIGRAVITY_BRAIN_DIRS", [])
    monkeypatch.setattr(main, "_antigravity_cli_meta", lambda *args, **kwargs: {})
    monkeypatch.setattr(main, "CODEX_DIR", tmp_path / ".codex")
    monkeypatch.setattr(main, "CURSOR_DIR", tmp_path / ".cursor")
    monkeypatch.setattr(main, "OPENCODE_DB", tmp_path / "opencode.db")
    monkeypatch.setattr(main, "HERMES_DB", tmp_path / "hermes-state.db")
    monkeypatch.setattr(main, "HERMES_PROFILES_DIR", missing / "hermes-profiles")
    monkeypatch.setattr(main, "PROJECT_ALIASES_FILE", tmp_path / "aliases.json")
    monkeypatch.setenv("TOKENTELEMETRY_DATA_DIR", str(tmp_path / "tt_data"))
    return tmp_path


def _codex_session(scan_env):
    return next(s for s in main._scan_sessions_sync() if s["agent"] == "codex")


def _site_create_call():
    return _jl(
        type="response_item",
        timestamp="2026-07-20T10:01:00Z",
        payload={
            "type": "custom_tool_call",
            "call_id": "site-create",
            "name": "exec",
            "input": (
                "const result = await tools.mcp__codex_apps__sites_create_site({"
                " title: 'Agentic Evaluation Plan', slug: 'agentic-evaluation-plan',"
                " description: 'Evidence-first evaluator plan.' });"
            ),
        },
    )


def _site_deployment_call():
    return _jl(
        type="response_item",
        timestamp="2026-07-20T10:02:00Z",
        payload={
            "type": "custom_tool_call",
            "call_id": "site-status",
            "name": "exec",
            "input": (
                "const result = await tools.mcp__codex_apps__sites_get_deployment_status({"
                " project_id: projectId, deployment_id: deploymentId });"
            ),
        },
    )


def _site_output(call_id, timestamp, text):
    return _jl(
        type="response_item",
        timestamp=timestamp,
        payload={
            "type": "custom_tool_call_output",
            "call_id": call_id,
            "output": [{"type": "text", "text": text}],
        },
    )


def _base_records():
    return [
        _jl(
            type="session_meta",
            timestamp="2026-07-20T10:00:00Z",
            payload={"cwd": "/tmp/codex-site-project", "model": "gpt-5.6"},
        ),
        _jl(
            type="event_msg",
            timestamp="2026-07-20T10:00:01Z",
            payload={"type": "user_message", "message": "Publish the plan as a Site"},
        ),
    ]


def test_deployed_codex_site_is_a_published_artifact(scan_env):
    _write_codex_session(scan_env / ".codex", _base_records() + [
        _site_create_call(),
        _site_output("site-create", "2026-07-20T10:01:02Z", '{"id":"appgprj_example"}'),
        _site_deployment_call(),
        _site_output("site-status", "2026-07-20T10:02:05Z", json.dumps({"status": "succeeded", "url": SITE_URL})),
    ])

    artifact = _codex_session(scan_env)["published_artifacts"][0]

    assert artifact == {
        "kind": "site",
        "url": SITE_URL,
        "title": "Agentic Evaluation Plan",
        "description": "Evidence-first evaluator plan.",
        "session_id": SID,
        "agent": "codex",
        "timestamp": "2026-07-20T10:02:05Z",
    }


def test_native_codex_sites_event_is_a_published_artifact(scan_env):
    native_records = _base_records() + [
        _jl(
            type="event_msg",
            timestamp="2026-07-20T10:01:00Z",
            payload={"type": "item_completed", "item": {
                "type": "McpToolCall", "appName": "Sites", "tool": "sites.create_site",
                "status": "completed", "arguments": {
                    "title": "Native Site", "description": "Captured from the Sites connector.",
                }, "result": {"structuredContent": {"id": "appgprj_example"}},
            }},
        ),
        _jl(
            type="event_msg",
            timestamp="2026-07-20T10:02:05Z",
            payload={"type": "item_completed", "item": {
                "type": "McpToolCall", "appName": "Sites", "tool": "sites.get_deployment_status",
                "status": "completed", "arguments": {"deployment_id": "appgdep_example"},
                "result": {"structuredContent": {"status": "succeeded", "url": SITE_URL}},
            }},
        ),
    ]
    _write_codex_session(scan_env / ".codex", native_records)

    artifact = _codex_session(scan_env)["published_artifacts"][0]

    assert artifact["kind"] == "site"
    assert artifact["title"] == "Native Site"
    assert artifact["description"] == "Captured from the Sites connector."
    assert artifact["url"] == SITE_URL


def test_only_sites_tool_output_can_create_a_codex_site_artifact(scan_env):
    _write_codex_session(scan_env / ".codex", _base_records() + [
        _jl(
            type="event_msg",
            timestamp="2026-07-20T10:01:00Z",
            payload={"type": "user_message", "message": f"Do not publish {SITE_URL}"},
        ),
    ])

    assert "published_artifacts" not in _codex_session(scan_env)


def test_codex_site_artifacts_survive_cache_and_project_rollup(scan_env, monkeypatch):
    _write_codex_session(scan_env / ".codex", _base_records() + [
        _site_create_call(),
        _site_deployment_call(),
        _site_output("site-status", "2026-07-20T10:02:05Z", json.dumps({"url": SITE_URL})),
    ])
    session = _codex_session(scan_env)
    payload = main._codex_cache_payload(session)
    restored = {"plans": []}
    main._apply_codex_cache_hit(restored, json.loads(json.dumps(payload)))
    assert restored["published_artifacts"] == session["published_artifacts"]

    async def fake_cached(fresh=False):
        return [session]

    monkeypatch.setattr(main, "get_sessions_cached", fake_cached)
    monkeypatch.setattr(main, "load_hidden", lambda: set())
    project = asyncio.run(main.get_projects())[0]
    assert project["artifacts"][0]["kind"] == "site"
    assert project["artifacts"][0]["url"] == SITE_URL
