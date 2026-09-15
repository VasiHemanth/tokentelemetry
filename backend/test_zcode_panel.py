"""Panel tests for ZCode's telemetry ledger.

Everything runs against a synthetic store in tmp_path. That matters more here
than for most agents: the machine this was written on has a real
`~/.zcode/cli/db/db.sqlite`, and a test that silently read it would pass for the
wrong reason and fail for anyone else.

The panel reads tables the session scan does not (`model_usage`, `turn_usage`,
`tool_usage`, `local_setting`, `workflow_run`), so the properties asserted here
are: the ledger reaches the document, the permission RULE TEXT does not, and a
store that is missing, empty or corrupt degrades rather than raising.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import harness_panels
from harness_panels import paths as hp_paths
from harness_panels import zcode as zcode_panel


SCHEMA = """
CREATE TABLE model_usage (
    id TEXT PRIMARY KEY, session_id TEXT, provider_id TEXT, model_id TEXT,
    variant TEXT, status TEXT, duration_ms INTEGER, time_to_first_token_ms INTEGER,
    retry_count INTEGER, input_tokens INTEGER, output_tokens INTEGER
);
CREATE TABLE turn_usage (
    turn_id TEXT PRIMARY KEY, session_id TEXT, status TEXT, duration_ms INTEGER,
    time_to_first_token_ms INTEGER, model_request_count INTEGER,
    tool_call_count INTEGER, tool_error_count INTEGER, model_retry_count INTEGER,
    context_exceeded INTEGER, cancelled_by_user INTEGER
);
CREATE TABLE tool_usage (
    id TEXT PRIMARY KEY, session_id TEXT, tool_name TEXT, side_effect_scope TEXT,
    read_only INTEGER, destructive INTEGER, approval_status TEXT, status TEXT,
    duration_ms INTEGER, output_bytes INTEGER, truncated INTEGER
);
CREATE TABLE local_setting (
    scope TEXT, scope_id TEXT, namespace TEXT, key TEXT, value TEXT
);
CREATE TABLE workflow_run (
    id TEXT PRIMARY KEY, definition_id TEXT, name TEXT, kind TEXT, status TEXT,
    current_phase TEXT, budget_spent INTEGER, time_created TEXT
);
CREATE TABLE workflow_definition (id TEXT PRIMARY KEY, name TEXT);
"""

# The exact rule shape ZCode writes. `ruleContent` carries a command pattern and
# routinely a project path, which is why the panel reports counts and never the
# text — this fixture is the thing that would leak if that changed.
RULESET = json.dumps({
    "version": 1,
    "allow": [{"ruleContent": "git fetch:*", "toolName": "Bash"},
              {"ruleContent": "/Users/secret-person/private-repo/**", "toolName": "Read"}],
    "deny": [{"ruleContent": "rm -rf:*", "toolName": "Bash"}],
})


def _store(root: Path, *, rows: bool = True, ruleset: bool = True) -> Path:
    db = root / "cli" / "db" / "db.sqlite"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA)
    if rows:
        conn.executemany(
            "INSERT INTO model_usage VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [("m1", "s1", "builtin:zai-start-plan", "GLM-5.3", "high",
              "completed", 15000, 3800, 0, 29570, 191),
             ("m2", "s1", "builtin:zai-start-plan", "GLM-5.3", "high",
              "error", 900, None, 2, 100, 0),
             ("m3", "s1", "builtin:zai-start-plan", "GLM-5.3", "low",
              "completed", 6000, 4200, 0, 500, 40)])
        conn.executemany(
            "INSERT INTO turn_usage VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [("t1", "s1", "completed", 45635, 4027, 5, 5, 0, 0, 0, 0),
             ("t2", "s1", "completed", 46759, 3492, 5, 4, 1, 1, 1, 0)])
        conn.executemany(
            "INSERT INTO tool_usage VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [("x1", "s1", "Bash", "system", 0, 1, "granted", "completed",
              398, 206557, 0),
             ("x2", "s1", "Read", "none", 1, 0, "none", "completed", 12, 370428, 0),
             ("x3", "s1", "Read", "none", 1, 0, "none", "error", 9, 0, 0)])
    if ruleset:
        conn.executemany(
            "INSERT INTO local_setting VALUES (?,?,?,?,?)",
            [("project", "proj_x", "permission", "ruleset", RULESET),
             ("project", "proj_x", "permission", "mode", json.dumps({"mode": "yolo"})),
             ("user", "default", "model", "reasoningLevel",
              json.dumps({"level": "high"}))])
    conn.commit()
    conn.close()
    return db


@pytest.fixture
def zroot(tmp_path, monkeypatch):
    root = tmp_path / ".zcode"
    root.mkdir()
    monkeypatch.setattr(hp_paths, "zcode_dir", lambda: root)
    harness_panels.invalidate()
    return root


def _sections(doc):
    return {s["title"]: s for s in doc["sections"]}


def test_panel_reports_the_ledger_the_session_scan_cannot_see(zroot):
    _store(zroot)
    doc = zcode_panel.build(with_disk=False)
    assert doc["installed"] is True
    titles = _sections(doc)
    assert "Model requests" in titles
    assert "Turn cost and latency" in titles
    assert "Tool calls" in titles


def test_model_requests_split_by_reasoning_level(zroot):
    """The same model at two reasoning levels is two rows, not one.

    Collapsing them would hide the latency difference, which is the only reason
    this section exists rather than deferring to the session view's model list.
    """
    _store(zroot)
    sec = _sections(zcode_panel.build(with_disk=False))["Model requests"]
    levels = {row[1]: row for row in sec["rows"]}
    assert set(levels) == {"high", "low"}
    assert levels["high"][2] == 2 and levels["low"][2] == 1
    # One of the two "high" rows had status != completed.
    assert levels["high"][6] == 1
    assert sec["count"] == 3


def test_disabled_reasoning_renders_as_off_not_blank(zroot):
    """`variant: disabled` is a real setting, not missing data."""
    db = _store(zroot)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO model_usage VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                 ("m4", "s1", "p", "GLM-5.3", "disabled", "completed", 2859,
                  None, 0, 277, 18))
    conn.commit()
    conn.close()
    sec = _sections(zcode_panel.build(with_disk=False))["Model requests"]
    assert "off" in {row[1] for row in sec["rows"]}


def test_context_overflow_raises_the_section_severity(zroot):
    _store(zroot)
    sec = _sections(zcode_panel.build(with_disk=False))["Turn cost and latency"]
    assert sec["severity"] == "warn"
    overflow = next(f for f in sec["fields"] if f["label"] == "Context overflows")
    assert overflow["value"] == 1


def test_tool_section_carries_zcodes_own_safety_labels(zroot):
    _store(zroot)
    sec = _sections(zcode_panel.build(with_disk=False))["Tool calls"]
    by_tool = {row[0]: row for row in sec["rows"]}
    assert by_tool["Bash"][3] == 1, "Bash call was flagged destructive"
    assert by_tool["Read"][2] == 2, "both Read calls were read-only"
    assert by_tool["Read"][7] == 1, "one Read call failed"
    assert sec["severity"] == "warn"


def test_approvals_section_appears_only_when_something_was_gated(zroot):
    _store(zroot)
    assert "Tool approvals" in _sections(zcode_panel.build(with_disk=False))


def test_approvals_section_hidden_when_nothing_was_ever_gated(zroot):
    db = _store(zroot, rows=False)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO tool_usage VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                 ("x9", "s1", "Read", "none", 1, 0, "none", "completed", 5, 10, 0))
    conn.commit()
    conn.close()
    assert "Tool approvals" not in _sections(zcode_panel.build(with_disk=False))


def test_permission_rule_text_never_reaches_the_document(zroot):
    """Counts, not rules. A rule names commands and absolute project paths."""
    _store(zroot)
    doc = zcode_panel.build(with_disk=False)
    blob = json.dumps(doc)
    assert "secret-person" not in blob
    assert "ruleContent" not in blob
    assert "git fetch" not in blob
    assert "rm -rf" not in blob

    sec = _sections(doc)["Permission posture"]
    counts = {f["label"]: f["value"] for f in sec["fields"]}
    assert counts["Allow rules"] == 2
    assert counts["Deny rules"] == 1
    assert counts["Ask rules"] == "—"


def test_unrestricted_mode_is_flagged(zroot):
    _store(zroot)
    sec = _sections(zcode_panel.build(with_disk=False))["Permission posture"]
    mode = next(f for f in sec["fields"] if f["label"] == "Mode")
    assert mode["value"] == "yolo"
    assert mode["severity"] == "warn"
    assert sec["severity"] == "warn"


def test_workflows_say_installed_but_empty_rather_than_vanishing(zroot):
    _store(zroot)
    sec = _sections(zcode_panel.build(with_disk=False))["Workflow runs"]
    assert sec["rows"] == []
    assert "workflows" in sec["empty_reason"].lower()


def test_quota_is_named_as_unavailable_not_silently_omitted(zroot):
    """Absence must read as "not exposed locally", never as an oversight."""
    _store(zroot)
    doc = zcode_panel.build(with_disk=False)
    kinds = {u["kind"] for u in doc["not_available"]}
    assert "quota" in kinds and "schedules" in kinds


def test_missing_root_is_not_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(hp_paths, "zcode_dir", lambda: tmp_path / "nope")
    doc = zcode_panel.build()
    assert doc["installed"] is False and doc["sections"] == []


def test_store_missing_under_a_real_root_still_builds(zroot):
    """The directory exists but ZCode has never run: no sections, no crash."""
    doc = zcode_panel.build(with_disk=False)
    assert doc["installed"] is True
    assert doc["sections"] == []


def test_corrupt_store_degrades_instead_of_raising(zroot):
    db = zroot / "cli" / "db" / "db.sqlite"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_bytes(b"this is not a sqlite database at all")
    doc = zcode_panel.build(with_disk=False)
    assert doc["installed"] is True
    assert doc["sections"] == []


def test_zcode_data_dir_relocates_the_store(tmp_path, monkeypatch):
    """A relocated install must still be found, the way main.py finds it."""
    elsewhere = tmp_path / "relocated"
    elsewhere.mkdir()
    _store(elsewhere)
    monkeypatch.setenv("ZCODE_DATA_DIR", str(elsewhere))
    assert hp_paths.zcode_dir() == elsewhere
    assert hp_paths.zcode_db() == elsewhere / "cli" / "db" / "db.sqlite"
    doc = zcode_panel.build(with_disk=False)
    assert doc["installed"] is True and doc["sections"]


def test_registered_as_a_real_panel_not_a_planned_one(zroot):
    """The registry entry is what makes /agents/zcode/panel serve this."""
    _store(zroot)
    assert harness_panels.has_panel("zcode")
    assert "zcode" not in harness_panels.PLANNED
    doc = harness_panels.build_panel("zcode", fresh=True, with_disk=False)
    assert doc["installed"] is True and doc["sections"]


def test_panel_does_not_restate_token_totals(zroot):
    """Tokens belong to the session scan; two sources would drift apart."""
    _store(zroot)
    doc = zcode_panel.build(with_disk=False)
    labels = {f["label"] for s in doc["sections"] for f in s.get("fields", [])}
    columns = {c for s in doc["sections"] for c in s.get("columns", [])}
    # "Avg first token" is latency, not a count — the ban is on token TOTALS.
    banned = {"input tokens", "output tokens", "total tokens", "cached tokens",
              "cache reads", "tokens used"}
    assert not (banned & {x.lower() for x in labels | columns})
