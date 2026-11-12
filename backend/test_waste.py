"""Tests for waste detection Tier 1 (docs/design/waste-detection.md).

Covers extract_signals on the Claude-shaped and normalized event shapes plus
the Codex rollout reader, each flag rule at its boundary, null-vs-zero
behaviour, and the GET /waste summary arithmetic.

Run: pytest backend/test_waste.py
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import main  # noqa: E402
import waste  # noqa: E402


# --------------------------------------------------------------------------- #
# Event builders
# --------------------------------------------------------------------------- #
def c_user(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def c_call(name, call_id, msg_id=None, usage=None, **inp):
    msg = {"role": "assistant", "content": [{"type": "tool_use", "id": call_id, "name": name, "input": inp}]}
    if msg_id:
        msg["id"] = msg_id
    if usage:
        msg["usage"] = usage
    return {"type": "assistant", "message": msg}


def c_result(call_id, is_error=None):
    block = {"type": "tool_result", "tool_use_id": call_id, "content": "x"}
    if is_error is not None:
        block["is_error"] = is_error
    return {"type": "user", "message": {"role": "user", "content": [block]}}


def n_call(tool, call_id=None, **args):
    p = {"tool": tool, "args": args}
    if call_id:
        p["callID"] = call_id
    return {"type": "tool_call", "payload": p}


def n_result(call_id, is_error=None):
    p = {"callID": call_id, "content": "x"}
    if is_error is not None:
        p["is_error"] = is_error
    return {"type": "tool_result", "payload": p}


def sess(agent="claude", sid="s1", cost=1.0, total=1000, **kw):
    s = {"id": sid, "agent": agent, "project": "/Users/dev/app", "cost": cost,
         "timestamp": datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc),
         "tokens": {"input": 100, "output": 10, "cached": 0, "total": total}}
    s.update(kw)
    return s


# --------------------------------------------------------------------------- #
# extract_signals
# --------------------------------------------------------------------------- #
def test_retry_run_of_five_counts_four_claude_shape():
    evs = [c_user("fix the build")]
    evs += [c_call("Bash", f"t{i}", command="npm test") for i in range(5)]
    evs += [c_call("Bash", "t9", command="npm run lint")]
    sig = waste.extract_signals(evs, sess())
    assert sig["tool_calls"] == 6
    assert sig["retry_calls"] == 4


def test_retry_run_of_two_counts_zero_and_arg_order_is_irrelevant():
    evs = [n_call("bash", "a", command="ls", cwd="/Users/dev/app"),
           n_call("bash", "b", cwd="/Users/dev/app", command="ls"),
           n_call("bash", "c", command="pwd"),
           n_call("bash", "d", command="pwd")]
    sig = waste.extract_signals(evs, sess(agent="hermes"))
    assert sig["retry_calls"] == 0
    # Same args in a different key order hash the same (run of 3 counts 2).
    evs.insert(1, n_call("bash", "e", cwd="/Users/dev/app", command="ls"))
    assert waste.extract_signals(evs, sess(agent="hermes"))["retry_calls"] == 2


def test_arg_hash_is_stable_canonical_digest():
    h1 = waste.arg_hash({"b": 1, "a": [1, 2]})
    h2 = waste.arg_hash('{"a": [1, 2], "b": 1}')
    assert h1 == h2 and len(h1) == 16
    assert waste.arg_hash({"a": 1}) != waste.arg_hash({"a": 2})
    assert waste.arg_hash(None) is None


def test_reread_broken_by_intervening_edit():
    p = "/Users/dev/app/src/main.py"
    evs = [c_call("Read", "r1", file_path=p),
           c_call("Read", "r2", file_path=p),          # re-read
           c_call("Edit", "e1", file_path=p, old_string="a", new_string="b"),
           c_call("Read", "r3", file_path=p),          # after edit: not a re-read
           c_call("Read", "r4", file_path=p)]          # re-read again
    sig = waste.extract_signals(evs, sess())
    assert sig["reread_calls"] == 2
    assert sig["edit_calls"] == 1


def test_reread_different_ranges_are_not_rereads():
    p = "/Users/dev/app/big.log"
    evs = [c_call("Read", "r1", file_path=p, offset=0, limit=100),
           c_call("Read", "r2", file_path=p, offset=100, limit=100),
           c_call("Read", "r3", file_path=p, offset=0, limit=100)]
    assert waste.extract_signals(evs, sess())["reread_calls"] == 1


def test_tool_errors_use_explicit_flags_only():
    evs = [c_call("Bash", "t1", command="a"), c_result("t1", is_error=True),
           c_call("Bash", "t2", command="b"),
           # Output text that looks like an error but carries no flag.
           {"type": "user", "message": {"role": "user", "content": [
               {"type": "tool_result", "tool_use_id": "t2", "content": "Error: Traceback failed"}]}},
           c_call("Bash", "t3", command="c"), c_result("t3", is_error=False)]
    sig = waste.extract_signals(evs, sess())
    assert sig["tool_errors"] == 1


def test_tool_errors_null_for_agent_without_flags():
    evs = [n_call("terminal", "a", command="x"), n_result("a")]
    sig = waste.extract_signals(evs, sess(agent="hermes"))
    assert sig["tool_errors"] is None
    assert sig["tool_calls"] == 1


def test_tool_errors_derived_from_flag_on_unlisted_agent():
    evs = [n_call("x", "a", q=1), n_result("a", is_error=True)]
    assert waste.extract_signals(evs, sess(agent="newagent"))["tool_errors"] == 1


def test_opencode_state_status_counts_but_hermes_state_is_ignored():
    def oc(cid, status):
        return {"type": "tool_call", "payload": {"tool": "bash", "callID": cid,
                                                 "state": {"status": status, "input": {"command": cid}}}}
    evs = [oc("a", "completed"), oc("b", "error"), oc("c", "completed")]
    assert waste.extract_signals(evs, sess(agent="opencode"))["tool_errors"] == 1
    hermes = [{"type": "tool_call", "payload": {"tool": "t", "args": {"x": 1}, "callID": "a", "state": "completed"}}]
    assert waste.extract_signals(hermes, sess(agent="hermes"))["tool_errors"] is None


def test_usage_dedupe_by_message_id_and_context_growth():
    def u(n):
        return {"input_tokens": 1, "cache_read_input_tokens": n, "cache_creation_input_tokens": 0}
    evs = []
    sizes = [100, 100, 200, 200, 300, 300, 400, 400]
    for i, n in enumerate(sizes):
        evs.append(c_call("Bash", f"t{i}", msg_id=f"m{i}", usage=u(n), command=str(i)))
        # Continuation record repeating the same id and usage: counted once.
        evs.append({"type": "assistant", "message": {"id": f"m{i}", "role": "assistant", "usage": u(n),
                                                     "content": [{"type": "text", "text": "..."}]}})
    sig = waste.extract_signals(evs, sess())
    assert sig["usage_turns"] == 8
    # first quarter mean 101, last quarter mean 401
    assert sig["context_growth"] == round(401 / 101, 2)


def test_context_growth_null_under_eight_turns():
    evs = [c_call("Bash", f"t{i}", msg_id=f"m{i}", usage={"input_tokens": 10 * (i + 1)}, command=str(i))
           for i in range(7)]
    sig = waste.extract_signals(evs, sess())
    assert sig["usage_turns"] == 7
    assert sig["context_growth"] is None


def test_context_growth_null_without_per_turn_usage():
    evs = [n_call("terminal", str(i), command=str(i)) for i in range(20)]
    assert waste.extract_signals(evs, sess(agent="hermes"))["context_growth"] is None


def test_user_turns_skip_tool_results_and_system_markup():
    evs = [c_user("first ask"),
           c_user("<system-reminder>ignore</system-reminder>"),
           c_result("t1"),
           {"type": "user", "isMeta": True, "message": {"role": "user", "content": "meta"}},
           c_user("second ask"),
           {"type": "user", "message": {"role": "user", "content": "<user_query>cursor ask</user_query>"}}]
    assert waste.extract_signals(evs, sess())["user_turns"] == 3


def test_null_vs_zero():
    # Agent whose parser records calls: zero calls means zero, not unknown.
    sig = waste.extract_signals([c_user("hi")], sess())
    assert sig["tool_calls"] == 0 and sig["retry_calls"] == 0 and sig["reread_calls"] == 0
    assert sig["edit_calls"] == 0 and sig["tool_errors"] == 0
    # Agent whose parser emits no tool events: unknown, not clean.
    sig = waste.extract_signals([{"type": "user", "payload": {"content": "hi"}}], sess(agent="cline"))
    assert sig["tool_calls"] == 0
    assert sig["retry_calls"] is None and sig["reread_calls"] is None
    assert sig["edit_calls"] is None and sig["tool_errors"] is None
    # Calls recorded without arguments: retries and rereads unknown.
    sig = waste.extract_signals([{"type": "tool_call", "payload": {"tool": "bash", "args": None}}] * 4,
                                sess(agent="muse"))
    assert sig["tool_calls"] == 4 and sig["retry_calls"] is None and sig["reread_calls"] is None
    # No user message found at all: turns unknown.
    assert sig["user_turns"] is None


def test_antigravity_cli_detail_passes_claude_shaped_messages_through():
    detail = {"kind": "antigravity_cli", "messages": [
        {"type": "user", "role": "user", "message": {"role": "user", "content": [{"type": "text", "text": "go"}]}},
        {"type": "assistant", "role": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "c1", "name": "view_file", "input": {"AbsolutePath": "/Users/dev/app/a.py"}}]}},
        {"type": "assistant", "role": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "c2", "name": "view_file", "input": {"AbsolutePath": "/Users/dev/app/a.py"}}]}},
    ]}
    # Transcript-path traces carry call ids, so identical neighbours are real calls.
    sig = waste.extract_signals(waste.events_from_detail(detail), sess(agent="antigravity"))
    assert sig["tool_calls"] == 2 and sig["reread_calls"] == 1 and sig["user_turns"] == 1


def test_gemini_cancelled_is_not_an_error():
    detail = {"messages": [
        {"type": "user", "content": "go"},
        {"type": "gemini", "id": "g1", "tokens": {"input": 50}, "toolCalls": [
            {"id": "a", "name": "run_shell_command", "args": {"command": "x"}, "status": "error"},
            {"id": "b", "name": "run_shell_command", "args": {"command": "y"}, "status": "cancelled"},
            {"id": "c", "name": "read_file", "args": {"path": "/Users/dev/app/a"}, "status": "success"}]},
    ]}
    sig = waste.extract_signals(waste.events_from_detail(detail), sess(agent="gemini"))
    assert sig["tool_calls"] == 3 and sig["tool_errors"] == 1 and sig["usage_turns"] == 1


def test_codex_rollout_reader():
    def ri(**p):
        return {"type": "response_item", "payload": p}

    def em(**p):
        return {"type": "event_msg", "payload": p}
    evs = [
        ri(type="message", role="user", content=[{"type": "input_text", "text": "<environment_context>"}]),
        em(type="user_message", message="do it"),
        ri(type="custom_tool_call", name="exec", call_id="c1", input="run('ls')", status="completed"),
        ri(type="custom_tool_call", name="exec", call_id="c2", input="run('ls')", status="completed"),
        ri(type="custom_tool_call", name="exec", call_id="c3", input="run('ls')", status="completed"),
        ri(type="function_call", name="apply_patch", call_id="c4", arguments='{"input": "*** Begin Patch"}'),
        em(type="item_completed", item={"type": "CommandExecution", "id": "i1", "status": "failed"}),
        em(type="item_completed", item={"type": "CommandExecution", "id": "i2", "status": "completed"}),
        {"type": "token_usage_record", "payload": {"response_id": "r1", "usage": {"input_tokens": 500, "cached_input_tokens": 400}}},
        {"type": "token_usage_record", "payload": {"response_id": "r1", "usage": {"input_tokens": 500, "cached_input_tokens": 400}}},
    ]
    sig = waste.extract_signals(evs, sess(agent="codex"))
    assert sig["user_turns"] == 1
    assert sig["tool_calls"] == 4
    assert sig["retry_calls"] == 2
    assert sig["tool_errors"] == 1
    assert sig["edit_calls"] == 1
    assert sig["reread_calls"] is None
    assert sig["usage_turns"] == 1


def test_extract_accepts_a_generator():
    def gen():
        yield c_user("hi")
        for i in range(3):
            yield c_call("Bash", f"t{i}", command="x")
    assert waste.extract_signals(gen(), sess())["retry_calls"] == 2


# --------------------------------------------------------------------------- #
# Flags at their boundaries
# --------------------------------------------------------------------------- #
CTX = {"median_cost": 1.0, "cache_agents": {"claude"}}


def base_sig(**kw):
    s = {"user_turns": 2, "tool_calls": 5, "tool_errors": 0, "retry_calls": 0, "reread_calls": 0,
         "edit_calls": 1, "cache_hit_pct": 90.0, "context_growth": 1.0, "usage_turns": 8}
    s.update(kw)
    return s


def test_flag_tool_failures_boundary():
    assert "tool_failures" in waste.flags_for(base_sig(tool_calls=10, tool_errors=2), sess(), CTX)
    assert "tool_failures" not in waste.flags_for(base_sig(tool_calls=10, tool_errors=1), sess(), CTX)
    assert "tool_failures" not in waste.flags_for(base_sig(tool_calls=9, tool_errors=9), sess(), CTX)
    assert "tool_failures" not in waste.flags_for(base_sig(tool_calls=50, tool_errors=None), sess(), CTX)


def test_flag_retry_and_rereads_boundary():
    assert "retry_loop" in waste.flags_for(base_sig(retry_calls=3), sess(), CTX)
    assert "retry_loop" not in waste.flags_for(base_sig(retry_calls=2), sess(), CTX)
    assert "retry_loop" not in waste.flags_for(base_sig(retry_calls=None), sess(), CTX)
    assert "rereads" in waste.flags_for(base_sig(reread_calls=5), sess(), CTX)
    assert "rereads" not in waste.flags_for(base_sig(reread_calls=4), sess(), CTX)
    assert "rereads" not in waste.flags_for(base_sig(reread_calls=None), sess(), CTX)


def test_flag_context_bloat_boundary():
    assert "context_bloat" in waste.flags_for(base_sig(context_growth=5.0), sess(), CTX)
    assert "context_bloat" not in waste.flags_for(base_sig(context_growth=4.99), sess(), CTX)
    assert "context_bloat" not in waste.flags_for(base_sig(context_growth=None), sess(), CTX)


def test_flag_low_cache_boundary():
    big = sess(tokens={"input": 150_000, "cached": 50_000, "output": 0, "total": 200_000})
    assert "low_cache" in waste.flags_for(base_sig(cache_hit_pct=29.9), big, CTX)
    assert "low_cache" not in waste.flags_for(base_sig(cache_hit_pct=30.0), big, CTX)
    small = sess(tokens={"input": 150_000, "cached": 49_999, "output": 0, "total": 199_999})
    assert "low_cache" not in waste.flags_for(base_sig(cache_hit_pct=10.0), small, CTX)
    # Agent that never reports cache reads.
    other = dict(big, agent="hermes")
    assert "low_cache" not in waste.flags_for(base_sig(cache_hit_pct=0.0), other, CTX)


def test_flag_no_artifact_boundary():
    sig = base_sig(tool_calls=30, edit_calls=0)
    assert "no_artifact" in waste.flags_for(sig, sess(cost=1.0), CTX)
    assert "no_artifact" not in waste.flags_for(sig, sess(cost=0.99), CTX)
    assert "no_artifact" not in waste.flags_for(base_sig(tool_calls=29, edit_calls=0), sess(), CTX)
    assert "no_artifact" not in waste.flags_for(base_sig(tool_calls=30, edit_calls=1), sess(), CTX)
    assert "no_artifact" not in waste.flags_for(base_sig(tool_calls=30, edit_calls=None), sess(), CTX)
    assert "no_artifact" not in waste.flags_for(sig, sess(artifacts=[{"name": "a"}]), CTX)
    assert "no_artifact" not in waste.flags_for(sig, sess(published_artifacts=[{"url": "x"}]), CTX)
    # A zero-cost session never qualifies, even when the median is zero.
    assert "no_artifact" not in waste.flags_for(sig, sess(cost=0.0), {**CTX, "median_cost": 0.0})


# --------------------------------------------------------------------------- #
# Endpoint
# --------------------------------------------------------------------------- #
@pytest.fixture
def waste_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKENTELEMETRY_DATA_DIR", str(tmp_path))
    kicked = []
    monkeypatch.setattr(main, "_waste_kick", lambda pending: kicked.append(list(pending)))
    return kicked


def _run_waste(**kw):
    params = {"from_": None, "from_alt": None, "to": None, "agents": [], "projects": []}
    params.update(kw)
    return asyncio.run(main.get_waste(**params))


def test_endpoint_summary_arithmetic(waste_env, monkeypatch):
    now = datetime.now(timezone.utc)
    sessions = [
        sess("claude", "a", cost=4.0, timestamp=now),
        sess("claude", "b", cost=None, timestamp=now - timedelta(hours=1)),
        sess("hermes", "c", cost=2.5, timestamp=now - timedelta(hours=2)),
        sess("claude", "d", cost=1.0, timestamp=now - timedelta(hours=3)),   # pending
        sess("hermes", "e", cost=0.5, timestamp=now - timedelta(hours=4)),   # failed
        sess("claude", "stub", cost=0.0, total=0, stub=True, timestamp=now),  # excluded
    ]

    async def fake_sessions(fresh=False):
        return sessions
    monkeypatch.setattr(main, "get_sessions_cached", fake_sessions)

    store = main._waste_store()
    by_id = {s["id"]: s for s in sessions}
    store.put("claude", "a", waste.cache_key(by_id["a"]),
              signals=base_sig(tool_calls=20, tool_errors=5, retry_calls=3, user_turns=4))
    store.put("claude", "b", waste.cache_key(by_id["b"]),
              signals=base_sig(tool_calls=10, tool_errors=3, user_turns=2, reread_calls=6))
    store.put("hermes", "c", waste.cache_key(by_id["c"]),
              signals=base_sig(tool_calls=12, tool_errors=None, retry_calls=None, reread_calls=None,
                               user_turns=None, usage_turns=0, context_growth=None))
    store.put("hermes", "e", waste.cache_key(by_id["e"]), failed="LookupError")

    out = _run_waste()
    s = out["summary"]
    assert s["sessions"] == 5
    assert s["analysed"] + s["pending"] == s["sessions"]
    assert s["pending"] == 1 and s["failed"] == 1
    assert [p["id"] for p in waste_env[0]] == ["d"]

    flagged = {r["id"]: r for r in out["sessions"]}
    assert set(flagged) == {"a", "b"}
    assert flagged["a"]["flags"] == ["tool_failures", "retry_loop"]
    assert flagged["b"]["cost"] == 0.0  # None cost treated as 0
    assert s["flagged_cost"] == pytest.approx(sum(r["cost"] for r in out["sessions"]))
    assert s["flagged_sessions"] == 2
    assert s["total_cost"] == pytest.approx(8.0)
    # Errors only over sessions that can record them: (5 + 3) / (20 + 10).
    assert s["failure_rate"] == pytest.approx(8 / 30, abs=1e-4)
    assert s["tool_calls"] == 42 and s["tool_errors"] == 8
    assert s["retry_calls"] == 3 and s["reread_calls"] == 6
    assert s["turns_per_session"] == 3.0
    assert s["cost_per_turn"] == pytest.approx(4.0 / 6)
    assert s["cost_per_session"] == pytest.approx(8.0 / 5)
    assert out["sessions"][0]["id"] == "a"  # highest cost first

    agents = {a["agent"]: a for a in out["by_agent"]}
    assert agents["hermes"]["failure_rate"] is None
    assert agents["hermes"]["retry_calls"] is None
    assert agents["hermes"]["capabilities"]["tool_errors"] is False
    assert agents["claude"]["capabilities"]["tool_errors"] is True
    assert agents["claude"]["sessions"] == 3 and agents["claude"]["analysed"] == 2
    flags = {f["flag"]: f for f in out["by_flag"]}
    assert flags["retry_loop"]["sessions"] == 1 and flags["retry_loop"]["cost"] == pytest.approx(4.0)
    assert flags["rereads"]["sessions"] == 1
    assert out["thresholds"] == waste.THRESHOLDS


def test_endpoint_filters_and_stale_entries(waste_env, monkeypatch):
    now = datetime.now(timezone.utc)
    s_old = sess("claude", "old", timestamp=now - timedelta(days=40))
    s_new = sess("hermes", "new", timestamp=now)

    async def fake_sessions(fresh=False):
        return [s_old, s_new]
    monkeypatch.setattr(main, "get_sessions_cached", fake_sessions)
    store = main._waste_store()
    # Key from before the session grew: stale, so it counts as pending.
    store.put("hermes", "new", ["2000-01-01T00:00:00", 1, waste.WASTE_VERSION], signals=base_sig())

    out = _run_waste(agents=["hermes"])
    assert out["summary"]["sessions"] == 1 and out["summary"]["pending"] == 1
    since = (now - timedelta(days=7)).astimezone().strftime("%Y-%m-%d")
    out = _run_waste(from_=since)
    assert out["summary"]["sessions"] == 1
    assert out["by_agent"][0]["agent"] == "hermes"


def test_endpoint_empty(waste_env, monkeypatch):
    async def fake_sessions(fresh=False):
        return []
    monkeypatch.setattr(main, "get_sessions_cached", fake_sessions)
    out = _run_waste()
    assert out["summary"]["sessions"] == 0 and out["summary"]["failure_rate"] is None
    assert out["sessions"] == [] and not waste_env


def test_store_roundtrip_and_version(tmp_path):
    path = str(tmp_path / "w" / "signals.json")
    st = waste.SignalStore(path)
    st.put("claude", "x", ["t", 1, waste.WASTE_VERSION], signals={"tool_calls": 3})
    st.flush()
    st2 = waste.SignalStore(path)
    assert st2.lookup("claude", "x", ["t", 1, waste.WASTE_VERSION]) == {"tool_calls": 3}
    assert st2.lookup("claude", "x", ["t", 2, waste.WASTE_VERSION]) is None
    with open(path) as f:
        assert "tool_calls" in f.read()


def test_route_accepts_from_and_from_underscore():
    # The spec writes `from_=`; /analytics uses `from`. Both must bind.
    route = next(r for r in main.app.routes if getattr(r, "path", None) == "/waste")
    aliases = {p.alias for p in route.dependant.query_params}
    assert {"from", "from_", "to", "agents", "projects"} <= aliases


def test_worker_tolerates_a_failing_session(tmp_path, monkeypatch):
    import time
    store = waste.SignalStore(str(tmp_path / "signals.json"))
    monkeypatch.setattr(main, "_waste_store", lambda: store)

    def fake_events(s, idx):
        if s["id"] == "bad":
            raise ValueError("corrupt transcript")
        return [c_user("hi"), c_call("Bash", "t1", command="x")]
    monkeypatch.setattr(main, "_waste_events", fake_events)
    now = datetime.now(timezone.utc)
    batch = [sess("hermes", "good1", timestamp=now), sess("hermes", "bad", timestamp=now - timedelta(minutes=1)),
             sess("hermes", "good2", timestamp=now - timedelta(minutes=2))]
    main._waste_kick(batch)
    deadline = time.time() + 5
    while time.time() < deadline:
        got = [store.lookup(s["agent"], s["id"], waste.cache_key(s)) for s in batch]
        if all(g is not None for g in got):
            break
        time.sleep(0.02)
    assert got[0]["tool_calls"] == 1 and got[2]["tool_calls"] == 1
    assert got[1] == {"failed": "ValueError"}


def test_antigravity_sqlite_echo_pairs_collapse():
    def ag(name, **inp):
        return {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": name, "input": inp}]}}
    p = "/Users/dev/app/a.py"
    # Each call appears twice (reasoning step, then execution step).
    evs = [ag("view_file", AbsolutePath=p), ag("view_file", AbsolutePath=p),
           ag("run_command", CommandLine="make"), ag("run_command", CommandLine="make"),
           ag("view_file", AbsolutePath=p), ag("view_file", AbsolutePath=p)]
    sig = waste.extract_signals(evs, sess(agent="antigravity"))
    assert sig["tool_calls"] == 3 and sig["reread_calls"] == 1 and sig["retry_calls"] == 0
    # Three real identical calls, each echoed: a run of 3 counts 2.
    evs = [ag("run_command", CommandLine="make")] * 6
    assert waste.extract_signals(evs, sess(agent="antigravity"))["retry_calls"] == 2


def test_poll_tools_are_not_retries_and_do_not_break_runs():
    evs = [c_call("BashOutput", f"p{i}", bash_id="1") for i in range(6)]
    assert waste.extract_signals(evs, sess())["retry_calls"] == 0
    evs = [c_call("Bash", "a", command="x"), c_call("BashOutput", "p", bash_id="1"),
           c_call("Bash", "b", command="x"), c_call("Bash", "c", command="x")]
    assert waste.extract_signals(evs, sess())["retry_calls"] == 2


def test_prompt_after_injected_markup_counts_as_a_turn():
    evs = [c_user("<system-reminder>context</system-reminder>\nplease fix the test"),
           c_user("<command-name>/model</command-name><command-args></command-args>"),
           c_user("<local-command-stdout>ok</local-command-stdout>"),
           c_user("<user_input>cline ask</user_input>")]
    assert waste.extract_signals(evs, sess())["user_turns"] == 2


def test_eligible_includes_tool_only_sessions():
    assert waste.eligible(sess(total=0, tool_counts={"Read": 3}))
    assert not waste.eligible(sess(total=0))
    assert not waste.eligible(sess(stub=True))


# --------------------------------------------------------------------------- #
# Read-image endpoint: the session's own transcript is the allow-list.
# --------------------------------------------------------------------------- #
def _image_env(tmp_path, monkeypatch, read_path):
    s = {"id": "s-img", "agent": "opencode", "project": str(tmp_path), "timestamp": None,
         "tokens": {"total": 10}, "cost": 0.0}

    async def fake_sessions(fresh=False):
        return [s]

    monkeypatch.setattr(main, "get_sessions_cached", fake_sessions)
    monkeypatch.setattr(main, "_waste_path_index", lambda batch: {})
    monkeypatch.setattr(main, "_waste_events", lambda sess, idx: [
        {"type": "tool_call", "payload": {"tool": "Read", "args": {"file_path": read_path}, "callID": "c1"}}])
    main._WASTE_READ_PATHS.clear()


def _img(path):
    return asyncio.run(main.get_session_read_image("s-img", agent="opencode", path=path))


def test_read_image_serves_only_what_the_session_read(tmp_path, monkeypatch):
    shot = tmp_path / "shot.png"
    shot.write_bytes(b"\x89PNG\r\n")
    other = tmp_path / "other.png"
    other.write_bytes(b"\x89PNG\r\n")
    secret = tmp_path / "notes.txt"
    secret.write_text("x")
    _image_env(tmp_path, monkeypatch, str(shot))

    assert Path(_img(str(shot)).path) == shot.resolve()
    for denied in (str(other), str(secret), str(tmp_path / "sub" / ".." / "shot.png"), str(tmp_path / "gone.png")):
        with pytest.raises(main.HTTPException) as e:
            _img(denied)
        assert e.value.status_code == 404


def test_read_image_rejects_symlink_to_non_image(tmp_path, monkeypatch):
    secret = tmp_path / "notes.txt"
    secret.write_text("x")
    link = tmp_path / "link.png"
    link.symlink_to(secret)
    _image_env(tmp_path, monkeypatch, str(link))
    with pytest.raises(main.HTTPException) as e:
        _img(str(link))
    assert e.value.status_code == 404

