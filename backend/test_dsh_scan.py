"""Tests for DeepSeek Harness (DSH) session scanning.

DSH (npm @deepseek-ai/dsh, binary `dsh`) writes one zstd-compressed JSONL per
session under ~/.dsh/sessions/<slugged-cwd>/<id>/session.jsonl.zstd. Event
shapes here (header fields, assistant/chunk usage samples, assistant/message
usage, request/context, tool/call) are verified against real on-disk DSH
output, not guessed from docs.

Run: pytest backend/test_dsh_scan.py -q
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import main  # noqa: E402

zstandard = pytest.importorskip("zstandard")


def _write_dsh_session(sessions_dir, workspace_slug, session_id, header_extra,
                        events, project="/Users/dev/project"):
    """Write one zstd-compressed session.jsonl under sessions_dir/<workspace_slug>/<id>/.

    `header_extra` merges into the required {type:"session", id, cwd,
    createdAt, delegationDepth, agentPreset} header. `events` is a list of
    {type, data, time} dicts appended after the header.
    """
    header = {
        "type": "session", "version": 0, "id": session_id, "cwd": project,
        "createdAt": 1786806413737, "delegationDepth": 0, "agentPreset": "standard",
    }
    header.update(header_extra)
    lines = [json.dumps(header)] + [json.dumps(e) for e in events]
    text = "\n".join(lines) + "\n"

    sess_dir = sessions_dir / workspace_slug / session_id
    sess_dir.mkdir(parents=True, exist_ok=True)
    path = sess_dir / "session.jsonl.zstd"
    path.write_bytes(zstandard.ZstdCompressor().compress(text.encode("utf-8")))
    return path


def _usage_events(turn, step, in_t, out_t, provider="cerebras", model="zai-glm-4.7",
                   base_time=1786850753000, duplicate_in_message=True):
    """One (turn,step)'s worth of events: request/context + assistant/chunk usage,
    optionally followed by an assistant/message carrying the SAME sample again
    (as real DSH does) -- callers use duplicate_in_message to prove dedup fires."""
    out = [
        {"type": "request/context", "seq": 1, "time": base_time,
         "data": {"provider": provider, "model": model, "contextWindow": 131072}},
        {"type": "assistant/chunk", "seq": 2, "time": base_time + 1,
         "data": {"turn": turn, "step": step,
                  "chunk": {"type": "usage", "usage": {"inputTokens": in_t, "outputTokens": out_t}}}},
    ]
    if duplicate_in_message:
        out.append({
            "type": "assistant/message", "seq": 3, "time": base_time + 2,
            "data": {"turn": turn, "step": step, "usage": {"inputTokens": in_t, "outputTokens": out_t},
                     "message": {"source": {"provider": provider, "model": model}}},
        })
    out.append({"type": "step/end", "seq": 4, "time": base_time + 3, "data": {"turn": turn, "step": step}})
    return out


@pytest.fixture
def scan_env(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DSH_SESSIONS_DIR", tmp_path / "dsh_sessions")
    monkeypatch.setattr(main, "PROJECT_ALIASES_FILE", tmp_path / "aliases.json")
    return tmp_path


def test_missing_sessions_dir_returns_empty(scan_env):
    assert main._scan_dsh_sessions() == []


def test_usage_dedup_does_not_double_count(scan_env):
    """assistant/chunk and assistant/message repeat the SAME (turn,step) usage
    sample -- the scanner must not sum both, only the deduped total."""
    events = _usage_events(turn=1, step=1, in_t=1000, out_t=200, duplicate_in_message=True)
    _write_dsh_session(scan_env / "dsh_sessions", "--proj--", "session-abc", {}, events)

    out = main._scan_dsh_sessions()
    assert len(out) == 1
    tokens = out[0]["tokens"]
    assert tokens["input"] == 1000
    assert tokens["output"] == 200
    assert tokens["total"] == 1200


def test_maps_project_model_provider_and_cost(scan_env):
    events = _usage_events(turn=1, step=1, in_t=500, out_t=100, provider="cerebras", model="zai-glm-4.7")
    _write_dsh_session(scan_env / "dsh_sessions", "--proj--", "session-abc", {}, events,
                        project="/Users/dev/myproject")

    out = main._scan_dsh_sessions()
    assert len(out) == 1
    sess = out[0]
    assert sess["agent"] == "dsh"
    assert sess["id"] == "session-abc"
    assert sess["project"] == "/Users/dev/myproject"
    assert sess["model"] == "zai-glm-4.7"
    assert sess["provider"] == "cerebras"
    assert sess["tokens"]["input"] == 500
    assert sess["cost"] > 0


def test_mixed_provider_session_prices_each_segment(scan_env):
    """One session spanning a local ollama call and a paid cerebras call must
    price each (turn,step) with its own provider, not one rate for the whole
    session -- real DSH sessions do span providers mid-conversation."""
    events = (
        _usage_events(turn=1, step=1, in_t=1000, out_t=100, provider="ollama",
                      model="deepseek-v4-flash:cloud", base_time=1000)
        + _usage_events(turn=2, step=1, in_t=2000, out_t=300, provider="cerebras",
                        model="zai-glm-4.7", base_time=2000)
    )
    _write_dsh_session(scan_env / "dsh_sessions", "--proj--", "session-mixed", {}, events)

    out = main._scan_dsh_sessions()
    assert len(out) == 1
    sess = out[0]
    assert sess["tokens"]["input"] == 3000
    assert sess["tokens"]["output"] == 400
    # local ollama segment is priced by electricity (near-zero, not the cerebras
    # per-token rate applied to all 3000 input tokens) -- so cost must be well
    # under what a flat cerebras-only price would give.
    cerebras_only_upper_bound = main.calculate_cost("zai-glm-4.7", 3000, 400, 0, provider="cerebras")
    assert sess["cost"] < cerebras_only_upper_bound
    assert sess["model"] == "zai-glm-4.7"  # last model used


def test_subagent_children_fold_into_parent_delegation(scan_env):
    parent_events = _usage_events(turn=1, step=1, in_t=100, out_t=20)
    _write_dsh_session(scan_env / "dsh_sessions", "--proj--", "session-parent", {}, parent_events)

    child_events = _usage_events(turn=1, step=1, in_t=50, out_t=10, provider="cerebras", model="zai-glm-4.7")
    _write_dsh_session(
        scan_env / "dsh_sessions", "--proj--", "child-uuid-1",
        {"origin": "subagent", "parentSession": "session-parent", "delegationDepth": 1},
        child_events,
    )

    out = main._scan_dsh_sessions()
    ids = {s["id"] for s in out}
    assert ids == {"session-parent"}, "subagent child must not appear as its own top-level session"

    parent = out[0]
    deleg = parent["delegation"]
    assert deleg["supported"] is True
    assert deleg["tokens_recorded"] is True
    assert deleg["spawn_count"] == 1
    assert deleg["subagents"][0]["agent_id"] == "child-uuid-1"
    assert deleg["subagents"][0]["tokens"]["input"] == 50
    assert deleg["delegated_total"] == 50 + 10


def test_fork_without_origin_stays_standalone(scan_env):
    """A session- prefixed id with a parentSession but no origin (DSH's
    'fork' shape) has no verified rollup semantics -- must surface as its
    own top-level session, not silently folded or dropped."""
    parent_events = _usage_events(turn=1, step=1, in_t=100, out_t=20)
    _write_dsh_session(scan_env / "dsh_sessions", "--proj--", "session-parent", {}, parent_events)

    fork_events = _usage_events(turn=1, step=1, in_t=30, out_t=5)
    _write_dsh_session(
        scan_env / "dsh_sessions", "--proj--", "session-fork-1",
        {"parentSession": "session-parent"},  # no "origin" key -- the fork shape
        fork_events,
    )

    out = main._scan_dsh_sessions()
    ids = {s["id"] for s in out}
    assert ids == {"session-parent", "session-fork-1"}


def test_errored_turn_with_no_usage_yields_zero_tokens(scan_env):
    """A turn that errors before any usage event fires (e.g. DSH's own
    403/context-window errors) must not crash the scanner or fabricate cost."""
    events = [
        {"type": "request/context", "seq": 1, "time": 1000,
         "data": {"provider": "ollama", "model": "deepseek-v4-flash:cloud", "contextWindow": 262144}},
        {"type": "turn/end", "seq": 2, "time": 1001,
         "data": {"turn": 1, "reason": {"kind": "error", "error": {"message": "403", "code": "AUTH"}}}},
    ]
    _write_dsh_session(scan_env / "dsh_sessions", "--proj--", "session-err", {}, events)

    out = main._scan_dsh_sessions()
    assert len(out) == 1
    assert out[0]["tokens"]["total"] == 0
    assert out[0]["cost"] == 0.0


def test_tool_calls_counted(scan_env):
    events = _usage_events(turn=1, step=1, in_t=10, out_t=5) + [
        {"type": "tool/call", "seq": 5, "time": 1786850753010,
         "data": {"turn": 1, "step": 1, "callId": "c1", "name": "bash", "arguments": "{}"}},
        {"type": "tool/call", "seq": 6, "time": 1786850753011,
         "data": {"turn": 1, "step": 1, "callId": "c2", "name": "bash", "arguments": "{}"}},
    ]
    _write_dsh_session(scan_env / "dsh_sessions", "--proj--", "session-tools", {}, events)

    out = main._scan_dsh_sessions()
    assert out[0]["tool_counts"] == {"bash": 2}


# ---------------------------------------------------------------------------
# Trace (get_session_detail)
# ---------------------------------------------------------------------------

def test_trace_normalizes_messages_tools_and_reasoning(scan_env):
    """DSH events must come back in the shared Claude-shaped trace contract so
    the existing EventCard renderer handles them unchanged."""
    events = [
        {"type": "user/message", "seq": 1, "time": 1000,
         "data": {"role": "user", "source": {"kind": "user"},
                  "content": [{"type": "text", "text": "hello there"}]}},
        {"type": "assistant/message", "seq": 2, "time": 2000,
         "data": {"turn": 1, "step": 1, "message": {"role": "assistant", "source": {"provider": "cerebras", "model": "zai-glm-4.7"},
                  "content": [{"type": "reasoning", "text": "thinking it over"},
                              {"type": "text", "text": "hi back"}]}}},
        {"type": "tool/call", "seq": 3, "time": 3000,
         "data": {"turn": 1, "step": 1, "callId": "c1", "name": "bash",
                  "arguments": '{"command":"ls"}'}},
        {"type": "tool/result", "seq": 4, "time": 4000,
         "data": {"turn": 1, "step": 1, "message": {
             "role": "user", "source": {"kind": "tool", "callId": "c1"},
             "content": [{"type": "tool-result", "toolCallId": "c1", "isError": False,
                          "content": [{"type": "text", "text": "file1.txt"}]}]}}},
    ]
    path = _write_dsh_session(scan_env / "dsh_sessions", "--proj--", "session-trace", {}, events)

    trace = main._dsh_trace_events(path)
    assert [e["type"] for e in trace] == ["user", "assistant", "assistant", "user"]

    assert trace[0]["message"]["content"][0]["text"] == "hello there"

    blocks = trace[1]["message"]["content"]
    assert blocks[0] == {"type": "thinking", "thinking": "thinking it over"}
    assert blocks[1] == {"type": "text", "text": "hi back"}

    tool_use = trace[2]["message"]["content"][0]
    assert tool_use["type"] == "tool_use"
    assert tool_use["id"] == "c1"
    assert tool_use["name"] == "bash"
    assert tool_use["input"] == {"command": "ls"}  # DSH stores args as a JSON string

    tool_result = trace[3]["message"]["content"][0]
    assert tool_result["type"] == "tool_result"
    assert tool_result["tool_use_id"] == "c1"  # must pair with the tool_use above
    assert tool_result["content"] == "file1.txt"

    assert [e["normalized_timestamp"] for e in trace] == [1000, 2000, 3000, 4000]


def test_trace_drops_plugin_injected_user_messages(scan_env):
    """DSH splices runtime-context/skill-catalog snapshots in as user-role
    messages; only source.kind == "user" is a real human turn."""
    events = [
        {"type": "user/message", "seq": 1, "time": 1000,
         "data": {"role": "user", "source": {"kind": "plugin", "plugin": "@deepseek-ai/dsh-system-prompt"},
                  "content": [{"type": "text", "text": "Current runtime context snapshot..."}]}},
        {"type": "user/message", "seq": 2, "time": 1100,
         "data": {"role": "user", "source": {"kind": "skill-catalog"},
                  "content": [{"type": "text", "text": "<system-reminder>skills</system-reminder>"}]}},
        {"type": "user/message", "seq": 3, "time": 1200,
         "data": {"role": "user", "source": {"kind": "user"},
                  "content": [{"type": "text", "text": "the real question"}]}},
    ]
    path = _write_dsh_session(scan_env / "dsh_sessions", "--proj--", "session-inject", {}, events)

    trace = main._dsh_trace_events(path)
    assert len(trace) == 1
    assert trace[0]["message"]["content"][0]["text"] == "the real question"


def test_session_detail_dispatches_dsh(scan_env):
    """agent="dsh" must resolve through get_session_detail rather than falling
    through to the {"error": "Invalid agent"} tail of the dispatch chain."""
    events = [
        {"type": "user/message", "seq": 1, "time": 1000,
         "data": {"role": "user", "source": {"kind": "user"},
                  "content": [{"type": "text", "text": "trace me"}]}},
    ]
    _write_dsh_session(scan_env / "dsh_sessions", "--proj--", "session-detail", {}, events)

    import asyncio
    result = asyncio.run(main.get_session_detail("session-detail", "dsh"))
    assert isinstance(result, list)
    assert result[0]["message"]["content"][0]["text"] == "trace me"


def test_session_detail_dsh_unknown_id_is_not_found(scan_env):
    import asyncio
    result = asyncio.run(main.get_session_detail("session-nope", "dsh"))
    assert result == {"error": "Not found"}


# ---------------------------------------------------------------------------
# Runtime capabilities
#
# DSH resolves skills/plugins/tools dynamically at run time, so a session's real
# capability set is only knowable from its own log. Two sessions in the SAME
# workspace legitimately differ (verified on real data: the "cordis" preset
# session had 8 skills / 32 tools where "standard" sessions had 6 / 25), which
# is exactly why a filesystem scan must never be used to describe a DSH run.
# ---------------------------------------------------------------------------

def test_captures_runtime_skill_catalog_from_session_log(scan_env):
    events = _usage_events(turn=1, step=1, in_t=10, out_t=5) + [
        {"type": "user/message", "seq": 9, "time": 1786850753020,
         "data": {"role": "user",
                  "source": {"kind": "skill-catalog", "form": "catalog", "entries": [
                      {"name": "find-skills", "description": "Discover and install agent skills"},
                      {"name": "cordis-plugin-development", "description": "Create dynamic Cordis plugins"},
                  ]},
                  "content": [{"type": "text", "text": "<system-reminder>catalog</system-reminder>"}]}},
    ]
    _write_dsh_session(scan_env / "dsh_sessions", "--proj--", "session-skills", {}, events)

    out = main._scan_dsh_sessions()
    catalog = out[0]["dsh"]["skills_catalog"]
    assert [s["name"] for s in catalog] == ["cordis-plugin-development", "find-skills"]  # sorted
    assert catalog[0]["description"] == "Create dynamic Cordis plugins"


def test_captures_runtime_tool_list_and_providers(scan_env):
    events = [
        {"type": "request/context", "seq": 1, "time": 1000,
         "data": {"provider": "ollama", "model": "deepseek-v4-flash:cloud"}},
        {"type": "request/header", "seq": 2, "time": 1001,
         "data": {"header": {"config": {"provider": "ollama", "model": "deepseek-v4-flash:cloud"},
                             "tools": [{"name": "bash"}, {"name": "skill"}, {"name": "subagent"}]}}},
        {"type": "request/context", "seq": 3, "time": 2000,
         "data": {"provider": "cerebras", "model": "zai-glm-4.7"}},
        {"type": "request/header", "seq": 4, "time": 2001,
         "data": {"header": {"config": {"provider": "cerebras", "model": "zai-glm-4.7"},
                             "tools": [{"name": "bash"}, {"name": "web_search"}]}}},
    ]
    _write_dsh_session(scan_env / "dsh_sessions", "--proj--", "session-tools-rt", {}, events)

    dsh = main._scan_dsh_sessions()[0]["dsh"]
    # union across requests, de-duped and sorted
    assert dsh["tools_available"] == ["bash", "skill", "subagent", "web_search"]
    assert dsh["providers_used"] == ["ollama", "cerebras"]


def test_skill_catalog_is_per_session_not_global(scan_env):
    """Two sessions in one workspace must report their OWN catalogs."""
    base = _usage_events(turn=1, step=1, in_t=10, out_t=5)
    _write_dsh_session(scan_env / "dsh_sessions", "--proj--", "session-a", {}, base + [
        {"type": "user/message", "seq": 9, "time": 1786850753020,
         "data": {"role": "user", "content": [],
                  "source": {"kind": "skill-catalog", "entries": [{"name": "only-in-a"}]}}},
    ])
    _write_dsh_session(scan_env / "dsh_sessions", "--proj--", "session-b", {}, base + [
        {"type": "user/message", "seq": 9, "time": 1786850753020,
         "data": {"role": "user", "content": [],
                  "source": {"kind": "skill-catalog", "entries": [
                      {"name": "only-in-b"}, {"name": "shared"}]}}},
    ])

    by_id = {s["id"]: s for s in main._scan_dsh_sessions()}
    assert [s["name"] for s in by_id["session-a"]["dsh"]["skills_catalog"]] == ["only-in-a"]
    assert [s["name"] for s in by_id["session-b"]["dsh"]["skills_catalog"]] == ["only-in-b", "shared"]


def test_skill_catalog_absent_when_log_records_none(scan_env):
    """No catalog in the log means we report nothing -- never a fallback to
    whatever another agent has installed on disk."""
    events = _usage_events(turn=1, step=1, in_t=10, out_t=5)
    _write_dsh_session(scan_env / "dsh_sessions", "--proj--", "session-nocat", {}, events)

    dsh = main._scan_dsh_sessions()[0]["dsh"]
    assert dsh["skills_catalog"] == []


def test_effective_preset_follows_midsession_switch(scan_env):
    """DSH can swap agent presets at run time, and the preset decides which
    skills/tools load. The header only records the STARTING preset, so the
    effective one must come from the agent-preset/selected event chain."""
    events = [
        {"type": "agent-preset/selected", "seq": 3, "time": 1100,
         "data": {"agentPreset": "cordis"}},
    ] + _usage_events(turn=1, step=1, in_t=10, out_t=5)
    _write_dsh_session(scan_env / "dsh_sessions", "--proj--", "session-preset",
                       {"agentPreset": "standard"}, events)

    dsh = main._scan_dsh_sessions()[0]["dsh"]
    assert dsh["agent_preset"] == "cordis", "must report the effective preset, not the header's"
    assert dsh["preset_chain"] == ["standard", "cordis"]


def test_preset_chain_without_switch_is_just_the_header(scan_env):
    events = _usage_events(turn=1, step=1, in_t=10, out_t=5)
    _write_dsh_session(scan_env / "dsh_sessions", "--proj--", "session-nopreset",
                       {"agentPreset": "standard"}, events)

    dsh = main._scan_dsh_sessions()[0]["dsh"]
    assert dsh["agent_preset"] == "standard"
    assert dsh["preset_chain"] == ["standard"]
