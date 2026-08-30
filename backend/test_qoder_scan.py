"""Tests for Qoder session scanning.

Qoder (Alibaba) writes Claude-Code-shaped JSONL under
~/.qoder/projects/<slugged-cwd>/<session-uuid>.jsonl, with child transcripts a
level deeper in <session-uuid>/subagents/. Record shapes here (the zeroed usage
block, `credits`, workspace-directories, origin.kind, the attachment types) are
taken from real on-disk Qoder output, not guessed from docs.

The behaviour worth pinning is that Qoder records NO token counts at all and
bills in credits: a scanner that silently reports zero looks identical to one
that failed, so several of these tests exist to keep the difference visible.

Run: pytest backend/test_qoder_scan.py -q
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import main  # noqa: E402


def _usage(credits, billable=True, ratio=0.0268):
    """Qoder's usage block: Anthropic-shaped, every token counter zero."""
    return {
        "input_tokens": 0, "output_tokens": 0,
        "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
        "server_tool_use": {"web_search_requests": 0, "web_fetch_requests": 0},
        "service_tier": "standard", "credits": credits,
        "original_credits": credits * 2, "billable": billable,
        "context_usage_ratio": ratio, "request_id": "req-1",
    }


def _user(text, uuid="u1", human=True, ts="2026-08-29T19:58:40.055Z"):
    row = {
        "type": "user", "uuid": uuid, "timestamp": ts, "sessionId": "SID",
        "cwd": "/Users/dev/repo", "gitBranch": "main", "version": "1.1.31",
        "isSidechain": False, "entrypoint": "cli", "userType": "external",
        "message": {"role": "user", "content": [{"type": "text", "text": text}]},
    }
    if human:
        row["origin"] = {"kind": "human"}
        row["humanInput"] = {"text": text}
    return row


def _assistant(credits, uuid="a1", blocks=None, model="qmodel_38max",
               ts="2026-08-29T19:58:50.418Z"):
    return {
        "type": "assistant", "uuid": uuid, "timestamp": ts, "sessionId": "SID",
        "cwd": "/Users/dev/repo", "gitBranch": "main", "version": "1.1.31",
        "isSidechain": False, "entrypoint": "cli",
        "message": {"role": "assistant", "model": model,
                    "content": blocks if blocks is not None else [
                        {"type": "text", "text": "ok"}],
                    "usage": _usage(credits)},
    }


def _write_session(projects, slug, session_id, rows):
    d = projects / slug
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{session_id}.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def _write_subagent(projects, slug, session_id, name, rows, meta):
    d = projects / slug / session_id / "subagents"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    (d / f"{name}.meta.json").write_text(json.dumps(meta), encoding="utf-8")


@pytest.fixture()
def qoder(tmp_path, monkeypatch):
    """A Qoder root with the scan pointed at it and no IDE database."""
    root = tmp_path / ".qoder"
    projects = root / "projects"
    projects.mkdir(parents=True)
    monkeypatch.setattr(main, "QODER_DIR", root)
    monkeypatch.setattr(main, "QODER_PROJECTS_DIR", projects)
    monkeypatch.setattr(main, "QODER_IDE_DIR", tmp_path / "no-ide")
    return projects


def test_no_projects_directory_scans_nothing(tmp_path, monkeypatch):
    """The installer creates ~/.qoder before the first session exists."""
    monkeypatch.setattr(main, "QODER_PROJECTS_DIR", tmp_path / "nope")
    assert main._scan_qoder_sessions() == []


def test_credits_are_summed_and_tokens_stay_zero(qoder):
    """Qoder's spend is credits; the token total must be an honest zero.

    Reporting a fabricated token count would be worse than zero -- there is
    nothing on disk to derive one from.
    """
    _write_session(qoder, "-Users-dev-repo", "SID", [
        {"type": "workspace-directories", "sessionId": "SID",
         "directories": ["/Users/dev/repo"]},
        _user("fix the build"),
        _assistant(1.25),
        _assistant(0.75, uuid="a2"),
    ])
    sessions = main._scan_qoder_sessions()
    assert len(sessions) == 1
    s = sessions[0]
    assert s["agent"] == "qoder" and s["id"] == "SID"
    assert s["tokens"]["total"] == 0
    assert s["cost"] == 0.0
    assert s["qoder"]["credits"] == 2.0
    assert s["qoder"]["original_credits"] == 4.0
    assert s["qoder"]["billable_turns"] == 2
    assert s["qoder"]["assistant_turns"] == 2
    assert s["qoder"]["cli_version"] == "1.1.31"
    assert s["model"] == "qmodel_38max"
    assert s["provider"] == "qoder"


def test_subagent_transcripts_are_not_counted_as_sessions(qoder):
    """The bug this guards: a recursive glob returns children as sessions.

    Two transcripts on disk under one session is ONE session with two
    delegated children, not three sessions.
    """
    _write_session(qoder, "-Users-dev-repo", "SID", [
        _user("do the thing"), _assistant(3.0)])
    _write_subagent(qoder, "-Users-dev-repo", "SID", "agent-a-1",
                    [_assistant(2.0, uuid="k1")],
                    {"agentType": "general-purpose", "toolUseId": "call_1",
                     "description": "Map the architecture"})
    _write_subagent(qoder, "-Users-dev-repo", "SID", "agent-a-2",
                    [_assistant(1.5, uuid="k2")],
                    {"agentType": "general-purpose", "toolUseId": "call_2",
                     "description": "Find repeated work"})

    sessions = main._scan_qoder_sessions()
    assert len(sessions) == 1, "children are not top-level sessions"

    deleg = sessions[0]["delegation"]
    assert deleg["supported"] is True
    assert deleg["spawn_count"] == 2
    # Credits, not tokens -- the spend is real but Qoder denominates it
    # differently, and claiming tokens were recorded would be a lie.
    assert deleg["tokens_recorded"] is False
    assert deleg["delegated_credits"] == 3.5
    assert deleg["delegated_total"] == 0
    assert {s["description"] for s in deleg["subagents"]} == {
        "Map the architecture", "Find repeated work"}
    assert sessions[0]["qoder"]["total_credits"] == 6.5


def test_each_subagent_gets_a_distinct_id(qoder):
    """Children carry the PARENT's sessionId, so the in-record id is identical
    for every spawn. Using it made two children collide -- the UI rendered them
    under one React key and they were indistinguishable. The filename, which
    encodes the agent type and a per-spawn hash, is the only unique handle.
    """
    _write_session(qoder, "-Users-dev-repo", "SID", [_assistant(1.0)])
    for name, desc in (("agent-a-first", "one"), ("agent-a-second", "two")):
        _write_subagent(qoder, "-Users-dev-repo", "SID", name,
                        [_assistant(1.0, uuid=name)],
                        {"agentType": "general-purpose", "description": desc})

    (sess,) = main._scan_qoder_sessions()
    ids = [s["agent_id"] for s in sess["delegation"]["subagents"]]
    assert len(set(ids)) == 2, f"subagent ids must be unique, got {ids}"
    assert "SID" not in ids, "the parent's session id is not a child's id"


def test_sidechain_transcript_at_root_is_skipped(qoder):
    """Belt and braces: the records flag a child even if one is misplaced."""
    rows = [_assistant(1.0)]
    rows[0]["isSidechain"] = True
    _write_session(qoder, "-Users-dev-repo", "CHILD", rows)
    assert main._scan_qoder_sessions() == []


def test_project_comes_from_records_not_the_directory_slug(qoder):
    """Qoder's slug is lossy: it replaces "/" with "-" without escaping the
    dashes already in the path, so "-Users-dev-Qoder-2026-08-30-abc" has
    several valid readings. The cwd in the records is the only sound source."""
    _write_session(qoder, "-Users-dev-Qoder-2026-08-30-abc", "SID", [
        {"type": "workspace-directories", "sessionId": "SID",
         "directories": ["/Users/dev/Qoder/2026-08-30/abc"]},
        _assistant(1.0),
    ])
    (sess,) = main._scan_qoder_sessions()
    assert sess["project"] == "/Users/dev/repo", "cwd on the record wins"


def test_workspace_directories_supplies_the_project_when_no_cwd(qoder):
    header = {"type": "workspace-directories", "sessionId": "SID",
              "directories": ["/Users/dev/from-header"]}
    turn = _assistant(1.0)
    turn.pop("cwd")
    _write_session(qoder, "-slug", "SID", [header, turn])
    (sess,) = main._scan_qoder_sessions()
    assert sess["project"] == "/Users/dev/from-header"


def test_trace_strips_the_injected_system_reminder(qoder):
    """Qoder prepends a plugin block to the opening prompt. Rendered verbatim
    it shows the harness's own instructions as the user's words."""
    injected = ("<system-reminder>\nPrefer the skills below.\n</system-reminder>\n\n"
                "what does this repo do")
    path = _write_session(qoder, "-Users-dev-repo", "SID", [
        _user(injected), _assistant(1.0)])

    events = main._qoder_trace_events(path)
    first = next(e for e in events if e["message"]["role"] == "user")
    text = first["message"]["content"][0]["text"]
    assert "<system-reminder>" not in text
    assert text == "what does this repo do"


def test_trace_keeps_tool_results_and_drops_harness_injections(qoder):
    """A tool_result arrives as a `user` record with no human origin. Dropping
    every non-human user record would leave each tool_use unpaired."""
    tool_use = _assistant(1.0, blocks=[
        {"type": "tool_use", "id": "t1", "name": "Read", "input": {}}])
    result = {
        "type": "user", "uuid": "r1", "timestamp": "2026-08-29T19:59:00.000Z",
        "sessionId": "SID", "isSidechain": False,
        "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "file body"}]},
    }
    injection = {
        "type": "user", "uuid": "r2", "timestamp": "2026-08-29T19:59:01.000Z",
        "sessionId": "SID", "isSidechain": False,
        "message": {"role": "user", "content": [
            {"type": "text", "text": "harness noise"}]},
    }
    path = _write_session(qoder, "-Users-dev-repo", "SID", [
        _user("read it"), tool_use, result, injection])

    events = main._qoder_trace_events(path)
    kinds = [b["type"] for e in events for b in e["message"]["content"]]
    assert "tool_result" in kinds, "results must survive or tool calls dangle"
    assert "harness noise" not in json.dumps(events)


def test_trace_drops_attachment_records(qoder):
    """Attachments are harness-injected context. The renderer displays
    Event.attachment, so passing one through shows the prompt as conversation."""
    attachment = {
        "type": "attachment", "uuid": "at1", "sessionId": "SID",
        "timestamp": "2026-08-29T19:58:45.000Z", "isSidechain": False,
        "attachment": {"type": "skill_listing", "skillCount": 2,
                       "names": ["alpha", "beta"],
                       "content": "SECRET-LOOKING SKILL DOC BODY"},
    }
    path = _write_session(qoder, "-Users-dev-repo", "SID", [
        _user("hi"), attachment, _assistant(1.0)])

    events = main._qoder_trace_events(path)
    assert "SECRET-LOOKING SKILL DOC BODY" not in json.dumps(events)
    assert all(e["type"] in ("user", "assistant") for e in events)


def test_attachments_record_availability_not_usage(qoder):
    """The skill catalogue is injected whether or not a skill is ever used, so
    it must not be reported as skills_used."""
    attachment = {
        "type": "attachment", "uuid": "at1", "sessionId": "SID",
        "timestamp": "2026-08-29T19:58:45.000Z", "isSidechain": False,
        "attachment": {"type": "skill_listing", "skillCount": 2,
                       "names": ["alpha", "beta"], "content": "..."},
    }
    servers = {
        "type": "attachment", "uuid": "at2", "sessionId": "SID",
        "timestamp": "2026-08-29T19:58:46.000Z", "isSidechain": False,
        "attachment": {"type": "critical_system_reminder",
                       "serverNames": ["browser-use"], "content": "..."},
    }
    _write_session(qoder, "-Users-dev-repo", "SID", [
        _user("hi"), attachment, servers, _assistant(1.0)])

    (sess,) = main._scan_qoder_sessions()
    assert sess["qoder"]["skills_available"] == ["alpha", "beta"]
    assert sess["qoder"]["mcp_servers"] == ["browser-use"]
    assert "skills_used" not in sess, "available is not the same as used"


def test_unknown_attachment_types_are_ignored(qoder):
    """Allowlist, not denylist: an unrecognised attachment may carry a file
    body, and the safe default is to drop it."""
    unknown = {
        "type": "attachment", "uuid": "at1", "sessionId": "SID",
        "timestamp": "2026-08-29T19:58:45.000Z", "isSidechain": False,
        "attachment": {"type": "pasted_file", "path": "/Users/dev/.env",
                       "content": "API_KEY=sk-should-never-appear"},
    }
    path = _write_session(qoder, "-Users-dev-repo", "SID", [
        _user("hi"), unknown, _assistant(1.0)])

    (sess,) = main._scan_qoder_sessions()
    assert "sk-should-never-appear" not in json.dumps(sess, default=str)
    assert "sk-should-never-appear" not in json.dumps(main._qoder_trace_events(path))


def test_tool_calls_are_counted(qoder):
    _write_session(qoder, "-Users-dev-repo", "SID", [
        _user("go"),
        _assistant(1.0, blocks=[
            {"type": "tool_use", "id": "t1", "name": "Read", "input": {}},
            {"type": "tool_use", "id": "t2", "name": "Read", "input": {}}]),
        _assistant(1.0, uuid="a2", blocks=[
            {"type": "tool_use", "id": "t3", "name": "Bash", "input": {}}]),
    ])
    (sess,) = main._scan_qoder_sessions()
    assert sess["tool_counts"] == {"Read": 2, "Bash": 1}


def test_torn_final_line_does_not_break_a_live_session(qoder):
    """A session being appended to while we read it ends mid-JSON."""
    d = qoder / "-Users-dev-repo"
    d.mkdir(parents=True)
    good = json.dumps(_assistant(2.0))
    (d / "SID.jsonl").write_text(good + "\n" + '{"type":"assist', encoding="utf-8")
    (sess,) = main._scan_qoder_sessions()
    assert sess["qoder"]["credits"] == 2.0


def test_display_falls_back_when_the_ide_database_is_absent(qoder):
    """Titles come from the IDE mirror; without it the first prompt is used."""
    _write_session(qoder, "-Users-dev-repo", "SID", [
        _user("summarise the migration plan"), _assistant(1.0)])
    (sess,) = main._scan_qoder_sessions()
    assert sess["display"] == "summarise the migration plan"


def _write_ide_db(path, rows):
    """A minimal stand-in for the IDE's mirror database."""
    import sqlite3
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE chat_sessions (session_id TEXT PRIMARY KEY, title TEXT, "
                 "session_kind TEXT, product_mode TEXT, archived INTEGER, deleted_at TIMESTAMP)")
    conn.execute("CREATE TABLE chat_session_messages (session_id TEXT, message_id TEXT, "
                 "payload_json TEXT)")
    for sid, title in rows:
        conn.execute("INSERT INTO chat_sessions VALUES (?,?,'standard','coding',0,NULL)",
                     (sid, title))
        conn.execute("INSERT INTO chat_session_messages VALUES (?,?,?)",
                     (sid, "m1", json.dumps({"role": "assistant", "durationMs": 1234})))
    conn.commit()
    conn.close()


def test_ide_database_supplies_the_session_title(tmp_path, monkeypatch):
    """The IDE mirrors the same sessions and is the only source of a real
    title; the JSONL has nothing but the first prompt."""
    root = tmp_path / ".qoder"
    projects = root / "projects"
    projects.mkdir(parents=True)
    ide = tmp_path / "ide"
    monkeypatch.setattr(main, "QODER_DIR", root)
    monkeypatch.setattr(main, "QODER_PROJECTS_DIR", projects)
    monkeypatch.setattr(main, "QODER_IDE_DIR", ide)

    _write_session(projects, "-Users-dev-repo", "SID", [
        _user("a very long rambling first prompt nobody would pick as a title"),
        _assistant(1.0)])
    _write_ide_db(ide / "main.sqlite", [("SID", "Fix the flaky test")])

    (sess,) = main._scan_qoder_sessions()
    assert sess["display"] == "Fix the flaky test"
    assert sess["qoder"]["duration_ms"] == 1234
    assert sess["qoder"]["turn_count"] == 1
    assert sess["qoder"]["session_kind"] == "standard"


def test_ide_database_never_adds_sessions_of_its_own(tmp_path, monkeypatch):
    """The DB is a projection of the same sessions. A row with no transcript
    must not become a session, or every session would be counted twice the
    day Qoder changes how it writes them."""
    root = tmp_path / ".qoder"
    projects = root / "projects"
    projects.mkdir(parents=True)
    ide = tmp_path / "ide"
    monkeypatch.setattr(main, "QODER_DIR", root)
    monkeypatch.setattr(main, "QODER_PROJECTS_DIR", projects)
    monkeypatch.setattr(main, "QODER_IDE_DIR", ide)

    _write_session(projects, "-Users-dev-repo", "SID", [_assistant(1.0)])
    _write_ide_db(ide / "main.sqlite",
                  [("SID", "Real one"), ("GHOST", "No transcript")])

    sessions = main._scan_qoder_sessions()
    assert [s["id"] for s in sessions] == ["SID"]


def test_long_first_prompt_is_truncated_for_the_title(qoder):
    """Qoder titles a thread with the user's whole first message."""
    _write_session(qoder, "-Users-dev-repo", "SID", [
        _user("x" * 400), _assistant(1.0)])
    (sess,) = main._scan_qoder_sessions()
    assert len(sess["display"]) == 120 and sess["display"].endswith("...")


def test_session_file_lookup_rejects_traversal(qoder):
    _write_session(qoder, "-Users-dev-repo", "SID", [_assistant(1.0)])
    assert main._qoder_session_file("SID") is not None
    assert main._qoder_session_file("../../etc/passwd") is None
    assert main._qoder_session_file("") is None
