"""Tests for per-agent harness panels.

Everything here runs against synthetic directories in tmp_path, never the
developer's real ~/.codex or ~/.claude — a test that passes only on a machine
with a particular agent installed is worse than no test.

The extractors read module-level path constants, so each test monkeypatches the
constant rather than $HOME: patching $HOME wouldn't help, because the constants
are resolved at import time.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import harness_panels
from harness_panels import base, claude as claude_panel, codex as codex_panel
from harness_panels import copilot as copilot_panel, grok as grok_panel


# --- base helpers -----------------------------------------------------------

@pytest.mark.parametrize("rule,expected", [
    ("RRULE:FREQ=WEEKLY;BYHOUR=16;BYMINUTE=0;BYDAY=FR", "Every Friday at 16:00"),
    ("RRULE:FREQ=HOURLY;INTERVAL=1", "Every hour"),
    ("RRULE:FREQ=HOURLY;INTERVAL=6", "Every 6 hours"),
    ("RRULE:FREQ=DAILY;BYHOUR=9;BYMINUTE=30", "Every day at 09:30"),
    ("FREQ=WEEKLY;BYDAY=MO,WE", "Every Monday, Wednesday"),
])
def test_rrule_human(rule, expected):
    assert base.rrule_human(rule) == expected


def test_rrule_unknown_falls_back_to_raw():
    """An unrecognised rule must show the raw string, not a confident wrong guess."""
    weird = "RRULE:FREQ=SECONDLY;BYSECOND=30"
    assert base.rrule_human(weird) == weird


def test_rrule_empty():
    assert base.rrule_human("") == ""


def test_iso_ms_handles_both_units():
    """Codex mixes epoch seconds and milliseconds across columns of one table."""
    secs = base.iso_ms(1_700_000_000)
    millis = base.iso_ms(1_700_000_000_000)
    assert secs is not None and millis is not None
    assert secs[:10] == millis[:10]          # same calendar day
    assert base.iso_ms(0) is None
    assert base.iso_ms(None) is None
    assert base.iso_ms("nonsense") is None


def test_dir_size_reports_incompleteness(tmp_path):
    """A truncated total must be labelled, never returned as if it were final."""
    for i in range(10):
        (tmp_path / f"f{i}").write_bytes(b"x" * 100)
    total, complete = base.dir_size(tmp_path)
    assert total == 1000 and complete is True

    capped, complete = base.dir_size(tmp_path, cap=4)
    assert complete is False
    assert capped < total


def test_dir_size_does_not_follow_symlinks(tmp_path):
    """A harness that links to a shared store must not claim those bytes."""
    real = tmp_path / "real"
    real.mkdir()
    (real / "big").write_bytes(b"y" * 5000)
    home = tmp_path / "home"
    home.mkdir()
    (home / "small").write_bytes(b"z" * 10)
    (home / "link").symlink_to(real)

    total, complete = base.dir_size(home)
    assert complete is True
    assert total == 10, "symlinked directory contents must not be counted"


def test_ro_sqlite_cannot_write(tmp_path):
    db = tmp_path / "x.db"
    sqlite3.connect(db).executescript("CREATE TABLE t(a); INSERT INTO t VALUES (1);")
    conn = base.ro_sqlite(db)
    assert conn is not None
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO t VALUES (2)")
    conn.close()


def test_ro_sqlite_missing_file(tmp_path):
    assert base.ro_sqlite(tmp_path / "nope.db") is None


def test_meter_clamps_and_grades():
    assert base.meter("x", 150).get("pct") == 100.0
    assert base.meter("x", -5).get("pct") == 0.0
    assert base.meter("x", 10)["severity"] == "ok"
    assert base.meter("x", 75)["severity"] == "warn"
    assert base.meter("x", 95)["severity"] == "crit"


def test_safe_swallows_failure():
    def boom():
        raise RuntimeError("nope")
    assert base.safe(boom, "test") is None


def test_preview_trims_and_collapses():
    assert base.preview(None) == "—"
    assert base.preview("   ") == "—"
    assert base.preview("hello   world") == "hello world"
    assert base.preview("a\nb\nc") == "a b c", "newlines must collapse, not survive"

    long = "x" * 500
    out = base.preview(long)
    assert len(out) == base.PREVIEW_CHARS
    assert out.endswith("…")


def test_preview_caps_codex_style_prompt_titles():
    """Regression: Codex titles a thread with the user's whole first message.

    Untrimmed, a `title` column became a transcript dump complete with pasted
    absolute paths — found by grepping a live panel response.
    """
    prompt = (
        "Review /Users/someone/Documents/Developer/proj and the public site. "
        "Propose three distinct product approaches that use the paper's findings. "
        "For each: target user problem, the data we already collect, what we would "
        "need to add, and a rough build estimate in days. Do not edit files."
    )
    out = base.preview(prompt)
    assert len(out) <= base.PREVIEW_CHARS
    assert "Do not edit files" not in out, "the tail of a long prompt must be cut"


# --- codex ------------------------------------------------------------------

def _codex_home(tmp_path: Path) -> Path:
    root = tmp_path / ".codex"
    (root / "automations" / "weekly").mkdir(parents=True)
    (root / "automations" / "weekly" / "automation.toml").write_text(
        'version = 1\n'
        'id = "weekly"\n'
        'kind = "cron"\n'
        'name = "Weekly review"\n'
        'prompt = "secret prompt text"\n'
        'status = "ACTIVE"\n'
        'rrule = "RRULE:FREQ=WEEKLY;BYHOUR=16;BYMINUTE=0;BYDAY=FR"\n'
        'model = "gpt-5.6"\n'
        'cwds = ["/tmp/myrepo"]\n',
        encoding="utf-8")
    (root / "config.toml").write_text(
        'approval_policy = "never"\n'
        'sandbox_mode = "danger-full-access"\n'
        '[projects."/a"]\ntrust_level = "trusted"\n'
        '[projects."/b"]\ntrust_level = "trusted"\n'
        '[projects."/c"]\ntrust_level = "ask"\n',
        encoding="utf-8")
    return root


def test_codex_schedules(tmp_path, monkeypatch):
    root = _codex_home(tmp_path)
    monkeypatch.setattr(codex_panel, "CODEX_DIR", root)

    doc = codex_panel.build()
    assert doc["installed"] is True

    sched = next(s for s in doc["sections"] if s["kind"] == "schedules")
    assert sched["count"] == 1
    row = sched["rows"][0]
    assert row[0] == "Weekly review"
    assert row[1] == "Every Friday at 16:00"
    assert row[4] == "myrepo", "project column should be the repo leaf, not the full path"

    # The prompt is the user's own words and must never reach the panel.
    assert "secret prompt text" not in json.dumps(doc)


def test_codex_security_flags_risk(tmp_path, monkeypatch):
    root = _codex_home(tmp_path)
    monkeypatch.setattr(codex_panel, "CODEX_DIR", root)

    sec = next(s for s in codex_panel.build()["sections"] if s["kind"] == "permissions")
    assert sec["severity"] == "crit", "never + danger-full-access is the risky combination"

    by_label = {f["label"]: f for f in sec["fields"]}
    assert by_label["Approval policy"]["severity"] == "crit"
    assert by_label["Sandbox mode"]["severity"] == "crit"
    assert by_label["Trusted projects"]["value"] == 2, "only trust_level=trusted counts"


def test_codex_safe_config_is_not_flagged(tmp_path, monkeypatch):
    root = tmp_path / ".codex"
    root.mkdir()
    (root / "config.toml").write_text(
        'approval_policy = "on-request"\nsandbox_mode = "workspace-write"\n',
        encoding="utf-8")
    monkeypatch.setattr(codex_panel, "CODEX_DIR", root)

    sec = next(s for s in codex_panel.build()["sections"] if s["kind"] == "permissions")
    assert sec["severity"] == "ok"
    assert all(f.get("severity") is None for f in sec["fields"])


def test_codex_threads_and_spawn_edges(tmp_path, monkeypatch):
    root = tmp_path / ".codex"
    root.mkdir()
    db = root / "state_5.sqlite"
    con = sqlite3.connect(db)
    con.executescript("""
        CREATE TABLE threads (id TEXT PRIMARY KEY, rollout_path TEXT, created_at INT,
          updated_at INT, source TEXT, model_provider TEXT, cwd TEXT, title TEXT,
          sandbox_policy TEXT, approval_mode TEXT, tokens_used INT, has_user_event INT,
          archived INT DEFAULT 0, archived_at INT, git_sha TEXT, git_branch TEXT,
          git_origin_url TEXT, cli_version TEXT, first_user_message TEXT,
          agent_nickname TEXT, agent_role TEXT, memory_mode TEXT, model TEXT,
          reasoning_effort TEXT, agent_path TEXT, created_at_ms INT, updated_at_ms INT,
          name TEXT);
        INSERT INTO threads (id, title, name, model, reasoning_effort, tokens_used,
                             git_branch, archived, updated_at, updated_at_ms)
          VALUES ('p','Parent','Parent','gpt-5.6','high',4200,'main',0,100,100000),
                 ('c','Child','Child','gpt-5.6','low',900,'main',0,90,90000);
        CREATE TABLE thread_spawn_edges (parent_thread_id TEXT, child_thread_id TEXT
          PRIMARY KEY, status TEXT);
        INSERT INTO thread_spawn_edges VALUES ('p','c','done');
    """)
    con.commit(); con.close()
    monkeypatch.setattr(codex_panel, "CODEX_DIR", root)

    doc = codex_panel.build()
    table = next(s for s in doc["sections"] if s["title"] == "Threads")
    assert table["total"] == 2
    assert table["rows"][0][0] == "Parent"
    assert table["rows"][0][5] == 1, "parent should show one spawn"

    tree = next(s for s in doc["sections"] if s["kind"] == "tree")
    assert tree["tree"][0]["label"] == "Parent"
    assert tree["tree"][0]["children"][0]["label"] == "Child"


def test_codex_empty_goals_becomes_not_available(tmp_path, monkeypatch):
    """An empty-but-real store should be named, not silently dropped."""
    root = tmp_path / ".codex"
    root.mkdir()
    con = sqlite3.connect(root / "goals_1.sqlite")
    con.executescript("""
        CREATE TABLE thread_goals (thread_id TEXT PRIMARY KEY, goal_id TEXT,
          objective TEXT, status TEXT, token_budget INT, tokens_used INT DEFAULT 0,
          time_used_seconds INT DEFAULT 0, created_at_ms INT, updated_at_ms INT);
    """)
    con.commit(); con.close()
    monkeypatch.setattr(codex_panel, "CODEX_DIR", root)

    kinds = {na["kind"] for na in codex_panel.build()["not_available"]}
    assert "quota" in kinds


def test_codex_not_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(codex_panel, "CODEX_DIR", tmp_path / "absent")
    doc = codex_panel.build()
    assert doc == {"agent": "codex", "installed": False,
                   "sections": [], "not_available": []}


def test_codex_survives_malformed_config(tmp_path, monkeypatch):
    """Bad TOML should drop one section, not the page."""
    root = _codex_home(tmp_path)
    (root / "config.toml").write_text("this is not [ valid toml", encoding="utf-8")
    monkeypatch.setattr(codex_panel, "CODEX_DIR", root)

    doc = codex_panel.build()
    assert doc["installed"] is True
    assert any(s["kind"] == "schedules" for s in doc["sections"])
    assert not any(s["kind"] == "permissions" for s in doc["sections"])


# --- claude -----------------------------------------------------------------

def test_claude_quota_meter(tmp_path, monkeypatch):
    root = tmp_path / ".claude"
    root.mkdir()
    cfg = tmp_path / ".claude.json"
    cfg.write_text(json.dumps({
        "cachedUsageUtilization": {
            "fetchedAtMs": 1_700_000_000_000,
            "accountUuid": "SHOULD-NOT-APPEAR",
            "utilization": {
                "five_hour": {"utilization": 47, "resets_at": "2026-08-27T12:00:00Z",
                              "used_dollars": 23.5, "limit_dollars": 50},
                "seven_day": {"utilization": 23, "resets_at": "2026-08-30T09:30:00Z"},
            },
        },
        "skillUsage": {"brain": {"usageCount": 41, "lastUsedAt": "2026-08-25T00:00:00Z"}},
    }), encoding="utf-8")
    monkeypatch.setattr(claude_panel, "CLAUDE_DIR", root)
    monkeypatch.setattr(claude_panel, "CLAUDE_JSON", cfg)

    doc = claude_panel.build()
    quota = next(s for s in doc["sections"] if s["kind"] == "meter")
    labels = {m["label"]: m for m in quota["meters"]}
    assert labels["5-hour window"]["pct"] == 47.0
    assert "23.50" in labels["5-hour window"]["detail"]
    # A window with no dollar figures must omit `detail` entirely rather than
    # rendering an empty or half-filled "of $" string.
    assert "detail" not in labels["7-day window"]

    # accountUuid identifies the user and has no business in a panel.
    assert "SHOULD-NOT-APPEAR" not in json.dumps(doc)

    adoption = next(s for s in doc["sections"] if s["title"] == "Feature adoption")
    assert adoption["rows"][0][0] == "brain"


def test_claude_adoption_converts_epoch_ms_last_used(tmp_path, monkeypatch):
    """Regression: lastUsedAt is epoch ms, not ISO — raw it rendered as "—"."""
    root = tmp_path / ".claude"
    root.mkdir()
    cfg = tmp_path / ".claude.json"
    cfg.write_text(json.dumps({
        "skillUsage": {"init": {"usageCount": 4, "lastUsedAt": 1775024284742}},
    }), encoding="utf-8")
    monkeypatch.setattr(claude_panel, "CLAUDE_DIR", root)
    monkeypatch.setattr(claude_panel, "CLAUDE_JSON", cfg)

    adoption = next(s for s in claude_panel.build()["sections"]
                    if s["title"] == "Feature adoption")
    last_used = adoption["rows"][0][3]
    assert isinstance(last_used, str) and last_used.startswith("2026-"), last_used


def test_claude_jobs_and_live_detection(tmp_path, monkeypatch):
    root = tmp_path / ".claude"
    jobs = root / "jobs"
    for name, state, live in (("alpha", "done", False), ("beta", "working", True)):
        d = jobs / name
        d.mkdir(parents=True)
        (d / "state.json").write_text(json.dumps({
            "name": name, "state": state, "tokens": 100,
            "cwd": "/tmp/myrepo", "updatedAt": f"2026-08-2{1 if live else 0}T00:00:00Z",
            "children": [{"id": "272", "kind": "pr"}] if not live else [],
        }), encoding="utf-8")
    (root / "daemon").mkdir(parents=True)
    (root / "daemon" / "roster.json").write_text(
        json.dumps({"workers": {"beta": {"pid": 1}}}), encoding="utf-8")
    (tmp_path / ".claude.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(claude_panel, "CLAUDE_DIR", root)
    monkeypatch.setattr(claude_panel, "CLAUDE_JSON", tmp_path / ".claude.json")

    section = next(s for s in claude_panel.build()["sections"] if s["kind"] == "jobs")
    assert section["total"] == 2
    assert section["count"] == 1, "one job has a live worker"
    assert section["rows"][0][0] == "beta", "live jobs sort first"
    assert section["rows"][0][6] is True
    assert "pr #272" in section["rows"][1][4]


def test_claude_job_dir_without_state_is_skipped(tmp_path, monkeypatch):
    """47 job dirs exist on the author's machine but only 33 have state.json."""
    root = tmp_path / ".claude"
    (root / "jobs" / "empty").mkdir(parents=True)
    good = root / "jobs" / "good"
    good.mkdir()
    (good / "state.json").write_text(json.dumps({"name": "g", "state": "done"}),
                                     encoding="utf-8")
    (tmp_path / ".claude.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(claude_panel, "CLAUDE_DIR", root)
    monkeypatch.setattr(claude_panel, "CLAUDE_JSON", tmp_path / ".claude.json")

    section = next(s for s in claude_panel.build()["sections"] if s["kind"] == "jobs")
    assert section["total"] == 1


def test_claude_workflows_ignore_subagent_metadata(tmp_path, monkeypatch):
    """Regression: subagents/workflows/wf_*/agent-*.meta.json are NOT runs.

    Counting them inflated 45 real runs to 512 in an earlier draft.
    """
    root = tmp_path / ".claude"
    session = root / "projects" / "-proj" / "sess"
    (session / "workflows").mkdir(parents=True)
    (session / "workflows" / "wf_real.json").write_text(json.dumps({
        "workflowName": "reconcile", "status": "completed", "agentCount": 6,
        "totalTokens": 264769, "totalToolCalls": 51, "durationMs": 637029,
        "timestamp": "2026-08-20T00:00:00Z",
    }), encoding="utf-8")
    decoy = session / "subagents" / "workflows" / "wf_real"
    decoy.mkdir(parents=True)
    (decoy / "agent-abc.meta.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".claude.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(claude_panel, "CLAUDE_DIR", root)
    monkeypatch.setattr(claude_panel, "CLAUDE_JSON", tmp_path / ".claude.json")

    wf = next(s for s in claude_panel.build()["sections"] if s["title"] == "Workflows")
    assert wf["total"] == 1, "only wf_*.json directly under <session>/workflows counts"
    assert wf["rows"][0][0] == "reconcile"


def test_claude_reclaimable_names_job_scratch(tmp_path, monkeypatch):
    root = tmp_path / ".claude"
    tmpdir = root / "jobs" / "alpha" / "tmp"
    tmpdir.mkdir(parents=True)
    (tmpdir / "clone.bin").write_bytes(b"x" * 4096)
    (root / "jobs" / "alpha" / "state.json").write_text(
        json.dumps({"name": "a", "state": "done"}), encoding="utf-8")
    (tmp_path / ".claude.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(claude_panel, "CLAUDE_DIR", root)
    monkeypatch.setattr(claude_panel, "CLAUDE_JSON", tmp_path / ".claude.json")

    disk = claude_panel.build()["disk"]
    assert disk["reclaimable_bytes"] == 4096
    assert "jobs/*/tmp" in disk["reclaimable_note"]


# --- copilot ----------------------------------------------------------------

def _copilot_home(tmp_path: Path) -> Path:
    root = tmp_path / ".copilot"
    root.mkdir()
    con = sqlite3.connect(root / "session-store.db")
    con.executescript("""
        CREATE TABLE sessions (id TEXT PRIMARY KEY, cwd TEXT, repository TEXT,
          host_type TEXT, branch TEXT, summary TEXT, created_at TEXT, updated_at TEXT);
        INSERT INTO sessions VALUES ('s1','/tmp/r','octo/repo','cli','main','x','t','t');
        CREATE TABLE turns (id INTEGER PRIMARY KEY, session_id TEXT, turn_index INT,
          user_message TEXT, assistant_response TEXT, timestamp TEXT);
        INSERT INTO turns VALUES (1,'s1',0,'PRIVATE PROMPT','PRIVATE ANSWER','t');
        CREATE TABLE checkpoints (id INTEGER PRIMARY KEY, session_id TEXT,
          checkpoint_number INT, title TEXT, overview TEXT, history TEXT,
          work_done TEXT, technical_details TEXT, important_files TEXT,
          next_steps TEXT, created_at TEXT);
        CREATE TABLE assistant_usage_events (
          id INTEGER PRIMARY KEY, session_id TEXT, turn_index INT, agent_id TEXT,
          parent_tool_call_id TEXT, model TEXT NOT NULL, input_tokens INT,
          output_tokens INT, cache_read_tokens INT, cache_write_tokens INT,
          reasoning_tokens INT, total_nano_aiu INT, request_multiplier REAL,
          duration_ms INT, time_to_first_token_ms REAL, inter_token_latency_ms REAL,
          initiator TEXT, api_endpoint TEXT, reasoning_effort TEXT, finish_reason TEXT,
          content_filter_triggered INT, token_details_json TEXT, created_at TEXT);
        INSERT INTO assistant_usage_events
          (session_id, model, input_tokens, output_tokens, cache_read_tokens,
           reasoning_tokens, total_nano_aiu, request_multiplier, duration_ms,
           time_to_first_token_ms, inter_token_latency_ms, finish_reason, created_at)
        VALUES
          ('s1','claude-opus-5',18204,1982,14880,642,1500000000,0.33,5000,840,25.0,'stop','t'),
          ('s1','gpt-5.4',9110,744,0,0,500000000,0.0,3000,1200,0.44,'stop','t');
    """)
    con.commit(); con.close()
    return root


def test_copilot_aiu_and_multiplier(tmp_path, monkeypatch):
    root = _copilot_home(tmp_path)
    monkeypatch.setattr(copilot_panel, "COPILOT_DIR", root)
    monkeypatch.setattr(copilot_panel, "STORE_DB", root / "session-store.db")

    doc = copilot_panel.build()
    summary = next(s for s in doc["sections"] if s["title"] == "Premium request usage")
    by_label = {f["label"]: f["value"] for f in summary["fields"]}
    # 1.5e9 + 0.5e9 nano-AIU = 2.0 AIU
    assert by_label["Billed units (AIU)"] == "2.000"
    assert by_label["Requests"] == 2
    # Zero multipliers are excluded from the average, so it is 0.33 not 0.165.
    assert "×0.33" in by_label["Multiplier"]


def test_copilot_suppresses_implausible_token_rate(tmp_path, monkeypatch):
    """A 0.44 ms inter-token gap would render as 2,272 tok/s. Suppress it."""
    root = _copilot_home(tmp_path)
    monkeypatch.setattr(copilot_panel, "COPILOT_DIR", root)
    monkeypatch.setattr(copilot_panel, "STORE_DB", root / "session-store.db")

    detail = next(s for s in copilot_panel.build()["sections"]
                  if s["title"] == "Per-request detail")
    rates = [r[7] for r in detail["rows"]]
    assert 40.0 in rates, "25 ms/token is a real 40 tok/s and must survive"
    assert None in rates, "sub-millisecond gaps must be suppressed, not shown"
    assert not any(isinstance(v, float) and v > 1000 for v in rates)


def test_copilot_never_returns_prompt_text(tmp_path, monkeypatch):
    root = _copilot_home(tmp_path)
    monkeypatch.setattr(copilot_panel, "COPILOT_DIR", root)
    monkeypatch.setattr(copilot_panel, "STORE_DB", root / "session-store.db")

    blob = json.dumps(copilot_panel.build())
    assert "PRIVATE PROMPT" not in blob
    assert "PRIVATE ANSWER" not in blob


def test_copilot_empty_checkpoints_is_a_state(tmp_path, monkeypatch):
    root = _copilot_home(tmp_path)
    monkeypatch.setattr(copilot_panel, "COPILOT_DIR", root)
    monkeypatch.setattr(copilot_panel, "STORE_DB", root / "session-store.db")

    ck = next(s for s in copilot_panel.build()["sections"] if s["title"] == "Checkpoints")
    assert ck["rows"] == []
    assert ck["empty_reason"], "empty must be explained, not hidden"


def test_copilot_tolerates_invalid_config_json(tmp_path, monkeypatch):
    """~/.copilot/config.json is not valid JSON on real installs."""
    root = _copilot_home(tmp_path)
    (root / "config.json").write_text("not json at all", encoding="utf-8")
    monkeypatch.setattr(copilot_panel, "COPILOT_DIR", root)
    monkeypatch.setattr(copilot_panel, "STORE_DB", root / "session-store.db")

    assert copilot_panel.build()["installed"] is True


# --- grok -------------------------------------------------------------------

def test_grok_credits_reads_newest_record(tmp_path, monkeypatch):
    root = tmp_path / ".grok"
    (root / "logs").mkdir(parents=True)
    lines = [
        json.dumps({"msg": "shell.turn.inference_done", "ctx": {}}),
        json.dumps({"msg": grok_panel.BILLING_MSG, "ts": "2026-08-01T00:00:00Z",
                    "ctx": {"config": {"creditUsagePercent": 12.0,
                                       "currentPeriod": {"type": "USAGE_PERIOD_TYPE_WEEKLY",
                                                         "end": "2026-08-07T00:00:00Z"}},
                            "subscriptionTier": "Old"}}),
        json.dumps({"msg": grok_panel.BILLING_MSG, "ts": "2026-08-26T00:00:00Z",
                    "ctx": {"config": {"creditUsagePercent": 52.0,
                                       "currentPeriod": {"type": "USAGE_PERIOD_TYPE_WEEKLY",
                                                         "end": "2026-08-28T00:00:00Z"}},
                            "subscriptionTier": "SuperGrok"}}),
    ]
    (root / "logs" / "unified.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    monkeypatch.setattr(grok_panel, "GROK_DIR", root)
    monkeypatch.setattr(grok_panel, "UNIFIED_LOG", root / "logs" / "unified.jsonl")

    credits = next(s for s in grok_panel.build()["sections"] if s["kind"] == "meter")
    assert credits["meters"][0]["pct"] == 52.0, "newest record wins, not the first"
    assert credits["meters"][0]["resets_at"] == "2026-08-28T00:00:00Z"
    assert any(f["value"] == "SuperGrok" for f in credits["fields"])


def test_grok_no_billing_record(tmp_path, monkeypatch):
    root = tmp_path / ".grok"
    (root / "logs").mkdir(parents=True)
    (root / "logs" / "unified.jsonl").write_text(
        json.dumps({"msg": "shell.turn.inference_done"}) + "\n", encoding="utf-8")
    monkeypatch.setattr(grok_panel, "GROK_DIR", root)
    monkeypatch.setattr(grok_panel, "UNIFIED_LOG", root / "logs" / "unified.jsonl")

    assert not any(s["kind"] == "meter" for s in grok_panel.build()["sections"])


def test_grok_tail_reads_only_the_end(tmp_path):
    """The credit scan must not cost more as the log grows."""
    f = tmp_path / "big.jsonl"
    f.write_text("\n".join(f'{{"n":{i}}}' for i in range(50_000)) + "\n", encoding="utf-8")
    got = list(base_tail(f, 2000))
    assert got, "should yield something"
    assert '"n":49999' in got[0], "first yielded line is the last line of the file"


def base_tail(path, max_bytes):
    return grok_panel._tail_lines(path, max_bytes=max_bytes)


def test_grok_plugin_jobs(tmp_path, monkeypatch):
    root = tmp_path / ".grok"
    g = root / "cc-plugin" / "jobs" / "grp"
    g.mkdir(parents=True)
    (g / "job-1.json").write_text(json.dumps({
        "id": "1", "kind": "rescue", "status": "completed", "model": "grok-4",
        "prompt": "PRIVATE", "startedAt": "2026-08-01T00:00:00Z",
        "finishedAt": "2026-08-01T00:05:00Z",
    }), encoding="utf-8")
    monkeypatch.setattr(grok_panel, "GROK_DIR", root)
    monkeypatch.setattr(grok_panel, "UNIFIED_LOG", root / "logs" / "unified.jsonl")

    doc = grok_panel.build()
    jobs = next(s for s in doc["sections"] if s["kind"] == "jobs")
    assert jobs["total"] == 1
    assert jobs["count"] == 0, "completed jobs are not running"
    assert "PRIVATE" not in json.dumps(doc)


def _grok_job(root: Path, name: str, status: str) -> None:
    g = root / "cc-plugin" / "jobs" / "grp"
    g.mkdir(parents=True, exist_ok=True)
    (g / f"job-{name}.json").write_text(json.dumps({
        "id": name, "kind": "rescue", "status": status,
        "startedAt": "2026-08-01T00:00:00Z",
    }), encoding="utf-8")


def test_grok_finished_is_terminal_not_running(tmp_path, monkeypatch):
    """Regression: Grok writes "finished", not "completed".

    Matching only on "completed" reported all six finished jobs as still
    running — the live UI showed "6 of 14" for a store with nothing in flight.
    """
    root = tmp_path / ".grok"
    for i in range(6):
        _grok_job(root, f"f{i}", "finished")
    for i in range(8):
        _grok_job(root, f"x{i}", "failed")
    monkeypatch.setattr(grok_panel, "GROK_DIR", root)
    monkeypatch.setattr(grok_panel, "UNIFIED_LOG", root / "logs" / "unified.jsonl")

    jobs = next(s for s in grok_panel.build()["sections"] if s["kind"] == "jobs")
    assert jobs["total"] == 14
    # Nothing in flight, so the headline becomes the failure count.
    assert jobs["count"] == 8
    assert jobs["severity"] == "warn"
    assert "8 of 14 failed" in jobs["note"]


def test_grok_unknown_status_counts_as_running(tmp_path, monkeypatch):
    """An unrecognised status must surface, not be silently treated as done."""
    root = tmp_path / ".grok"
    _grok_job(root, "a", "finished")
    _grok_job(root, "b", "some-new-status")
    monkeypatch.setattr(grok_panel, "GROK_DIR", root)
    monkeypatch.setattr(grok_panel, "UNIFIED_LOG", root / "logs" / "unified.jsonl")

    jobs = next(s for s in grok_panel.build()["sections"] if s["kind"] == "jobs")
    assert jobs["count"] == 1, "the unknown status should read as in flight"


# --- registry ---------------------------------------------------------------

def test_unknown_agent_is_planned_not_missing():
    doc = harness_panels.build_panel("qwen")
    assert doc["installed"] is False and doc["planned"] is True


def test_unsupported_agent_is_not_planned():
    doc = harness_panels.build_panel("definitely-not-an-agent")
    assert doc["installed"] is False and doc.get("planned") is False


def test_hermes_is_excluded_from_panels():
    """Hermes has its own richer /hermes/* dashboard."""
    assert not harness_panels.has_panel("hermes")
    assert "hermes" not in harness_panels.PLANNED


def test_builder_exception_does_not_propagate(monkeypatch):
    def boom():
        raise RuntimeError("extractor blew up")
    monkeypatch.setitem(harness_panels.BUILDERS, "codex", boom)
    harness_panels.invalidate()
    doc = harness_panels.build_panel("codex", fresh=True)
    assert doc["installed"] is False
    harness_panels.invalidate()


def test_cache_returns_same_object(monkeypatch):
    calls = {"n": 0}

    def counting():
        calls["n"] += 1
        return {"agent": "codex", "installed": True, "sections": [], "not_available": []}

    monkeypatch.setitem(harness_panels.BUILDERS, "codex", counting)
    harness_panels.invalidate()
    harness_panels.build_panel("codex")
    harness_panels.build_panel("codex")
    assert calls["n"] == 1, "second read should be served from cache"
    harness_panels.build_panel("codex", fresh=True)
    assert calls["n"] == 2, "fresh=True must bypass the cache"
    harness_panels.invalidate()
