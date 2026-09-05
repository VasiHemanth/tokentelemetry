"""Tool-result failure detection for the trace UI and the condensed brief.

A real Hermes session (155 events, 54/54 tool calls logged `ok`, exactly ONE
genuine failure) reported "ERR 2" in the trace header and "ERRORS (8)" in the
brief. Two detectors disagreed and both were wrong: the header matched the bare
word "exception" anywhere in an event, the brief matched "error" anywhere in a
tool-result body. Neither is a statement about whether the call failed.

The bodies below are the shapes that actually caused it — a tool catalogue that
documents its error codes, a tool-search result, and scraped page text. They are
kept verbatim in spirit so the substring approach can't come back unnoticed.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import summaries  # noqa: E402


# Bodies that merely MENTION failure. None of these is a failed call.
NOT_ERRORS = [
    # Tool-search results: the query list and the catalogue both contain the
    # word "error" deep inside, far from the first line.
    json.dumps({"queries": ["terminal command run shell inspect files",
                            "read write patch files in workspace"],
                "total_available": 42,
                "note": "returns an error object when the tool is unknown"}),
    json.dumps({"tools": {"mcp__agentbrowser__tabs_list": {
        "description": "List open browser tabs. Returns an error if the "
                       "browser is not running.",
        "parameters": {"type": "object"}}}}),
    # Scraped page content. Wrapped, not JSON, and may quote anything.
    '<untrusted_tool_result source="mcp__agentbrowser__read_page">\n'
    'The following content was retrieved. Handling exceptions is covered in '
    'section 4, and common errors are listed below.\n',
    '<untrusted_tool_result source="mcp__agentbrowser__eval_js">\n'
    'undefined\n',
    # An ordinary successful result that happens to discuss failure.
    "Wrote 3 files. No errors were reported during the build.",
    # Truncated JSON: one long line, so a text scan would match anything in it.
    '{"tools": {"cronjob_manage": {"description": "error handling for jobs',
]

# Bodies that ARE failures.
ERRORS = [
    json.dumps({"error": "'terminal' is not a deferrable tool. If it appears "
                         "in the model-facing tools list already, call it "
                         "directly instead of deferring it."}),
    "Error: ENOENT: no such file or directory, open '/tmp/missing.txt'",
    "Traceback (most recent call last):\n  File \"x.py\", line 1\nValueError: bad",
    "failed to connect to the gateway after 3 attempts",
    "Permission denied: cannot write to /etc/hosts",
]


@pytest.mark.parametrize("body", NOT_ERRORS)
def test_mentioning_failure_is_not_failing(body):
    assert summaries.is_tool_error({}, body) is False


@pytest.mark.parametrize("body", ERRORS)
def test_real_failures_are_detected(body):
    assert summaries.is_tool_error({}, body) is True


def test_explicit_flag_always_wins():
    """An agent that marks its own failures is trusted over any text heuristic."""
    assert summaries.is_tool_error({"is_error": True}, "totally fine output") is True


def test_empty_body_is_not_an_error():
    assert summaries.is_tool_error({}, "") is False
    assert summaries.is_tool_error({}, "   \n ") is False


def test_json_error_key_must_be_non_empty():
    """`{"error": null}` and `{"error": ""}` are how tools say "no error"."""
    assert summaries.is_tool_error({}, json.dumps({"error": None})) is False
    assert summaries.is_tool_error({}, json.dumps({"error": ""})) is False
    assert summaries.is_tool_error({}, json.dumps({"error": "boom"})) is True


def test_condenser_counts_one_error_for_the_reported_shape():
    """End-to-end: the mix that reported 8 errors must report exactly 1.

    Also asserts the header and the brief now agree, since both read the same
    is_error flag once a trace builder has stamped it.
    """
    events = [{"type": "tool_result", "payload": {"tool": "t", "content": b}}
              for b in NOT_ERRORS]
    events.append({"type": "tool_result",
                   "payload": {"tool": "terminal", "content": ERRORS[0]}})

    brief = summaries.condense_trace(events, {"agent": "hermes"})
    assert len(brief["errors"]) == 1
    assert "not a deferrable tool" in brief["errors"][0]

    # What the trace header counts, once the builder stamps is_error.
    stamped = []
    for ev in events:
        payload = dict(ev["payload"])
        if summaries.is_tool_error(payload, payload["content"]):
            payload["is_error"] = True
        stamped.append({**ev, "payload": payload})
    header = sum(1 for ev in stamped
                 if '"is_error":true' in json.dumps(ev).lower().replace(" ", ""))
    assert header == len(brief["errors"]) == 1


def test_brief_carries_a_version_so_stale_briefs_are_recomputed():
    """Without this, a corrected brief never reaches a session already cached."""
    brief = summaries.condense_trace([], {"agent": "hermes"})
    assert brief["_v"] == summaries.BRIEF_VERSION

    # The version participates in the cache key, so bumping it invalidates rows
    # cached under the old rules even when the trace itself has not changed.
    events = [{"type": "user", "payload": {"content": "hi"}, "timestamp": 1}]
    baseline = summaries.content_hash("s1", events)
    original = summaries.BRIEF_VERSION
    try:
        summaries.BRIEF_VERSION = original + 1
        assert summaries.content_hash("s1", events) != baseline
    finally:
        summaries.BRIEF_VERSION = original
