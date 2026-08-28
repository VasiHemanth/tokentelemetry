"""Panel tests for the remaining supported agents.

Split from test_harness_panels.py, which covers the shared helpers and the four
densest harnesses. Everything here runs against synthetic directories in
tmp_path — a test that only passes on a machine with a given agent installed is
worse than no test.

Each extractor reads its paths from `harness_panels.paths`, so tests patch that
module rather than $HOME: the constants resolve at import time and patching the
environment afterwards would have no effect.

Three properties are asserted throughout, because they are the ones a
regression would quietly break: no prompt body reaches the panel, no credential
value does either, and a missing directory degrades to `installed: false`
instead of raising.
"""
from __future__ import annotations

import builtins
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import harness_panels
from harness_panels import claude as claude_panel, clis, codex as codex_panel
from harness_panels import copilot as copilot_panel, grok as grok_panel, ides
from harness_panels import hermes as hermes_panel
from harness_panels import paths as hp_paths


def test_every_supported_agent_has_a_builder():
    """Scope check: every agent in supported-agents.mdx, Hermes included."""
    supported = {
        "claude", "codex", "gemini", "antigravity", "qwen", "vibe", "cursor",
        "copilot", "opencode", "grok", "cline", "smallcode", "pi", "muse",
        "prime", "dsh", "hermes",
    }
    assert supported == set(harness_panels.BUILDERS), (
        "every supported agent needs an extractor; "
        f"missing={supported - set(harness_panels.BUILDERS)} "
        f"unexpected={set(harness_panels.BUILDERS) - supported}"
    )
    assert harness_panels.EXCLUDED == ()


# --- Qwen -------------------------------------------------------------------

def test_qwen_todos_and_permissions(tmp_path, monkeypatch):
    root = tmp_path / ".qwen"
    (root / "todos").mkdir(parents=True)
    (root / "todos" / "s1.json").write_text(json.dumps({
        "sessionId": "s1",
        "todos": [{"content": "ship it", "id": "1", "status": "pending"},
                  {"content": "done thing", "id": "2", "status": "completed"}],
    }), encoding="utf-8")
    (root / "settings.json").write_text(json.dumps({
        "permissions": {"allow": ["Bash(ls:*)", "Bash(git:*)"]},
        "security": {"auth": {"selectedType": "oauth"}},
    }), encoding="utf-8")
    monkeypatch.setattr(hp_paths, "QWEN_DIR", root)

    doc = clis.build_qwen()
    todos = next(s for s in doc["sections"] if s["kind"] == "todos")
    assert todos["total"] == 2
    assert todos["count"] == 1, "only the pending one is open"
    perms = next(s for s in doc["sections"] if s["kind"] == "permissions")
    assert {f["label"]: f["value"] for f in perms["fields"]}["Auto-approved commands"] == 2


def test_qwen_todo_headline_falls_back_when_none_open(tmp_path, monkeypatch):
    """With nothing open, the headline must not read "0 of 2".

    Passing count=None lets `section` derive it from the rows, so count equals
    total and the frontend renders a single number rather than a ratio that
    looks like "no todos exist".
    """
    root = tmp_path / ".qwen"
    (root / "todos").mkdir(parents=True)
    (root / "todos" / "s.json").write_text(json.dumps({
        "todos": [{"content": "a", "status": "completed"},
                  {"content": "b", "status": "completed"}]}), encoding="utf-8")
    monkeypatch.setattr(hp_paths, "QWEN_DIR", root)

    todos = next(s for s in clis.build_qwen()["sections"] if s["kind"] == "todos")
    assert todos["total"] == 2
    assert todos["count"] == todos["total"], \
        "count must collapse to the total so the headline is one number"
    assert "0 still open" in todos["note"], "the note still states the open count"


# --- Cline ------------------------------------------------------------------

def test_cline_exit_codes(tmp_path, monkeypatch):
    root = tmp_path / ".cline"
    for name, code, teams in (("a", 0, False), ("b", 1, True)):
        d = root / "data" / "sessions" / f"178_{name}"
        d.mkdir(parents=True)
        (d / f"178_{name}.json").write_text(json.dumps({
            "session_id": name, "cwd": "/tmp/myrepo", "model": "sonnet",
            "provider": "anthropic", "status": "ended", "exit_code": code,
            "enable_teams": teams, "prompt": "PRIVATE PROMPT",
            "started_at": "2026-08-01T00:00:00Z",
        }), encoding="utf-8")
    monkeypatch.setattr(hp_paths, "CLINE_DIR", root)

    doc = clis.build_cline()
    runs = next(s for s in doc["sections"] if s["title"] == "Runs")
    assert runs["total"] == 2
    results = {r[4] for r in runs["rows"]}
    assert "ok" in results, "exit_code 0 must render as success, not as a bare 0"
    assert "exit 1" in results
    assert runs["severity"] == "warn"
    assert "PRIVATE PROMPT" not in json.dumps(doc)


def test_cline_empty_cron_is_named(tmp_path, monkeypatch):
    root = tmp_path / ".cline"
    (root / "cron").mkdir(parents=True)
    monkeypatch.setattr(hp_paths, "CLINE_DIR", root)
    assert "schedules" in {n["kind"] for n in clis.build_cline()["not_available"]}


# --- Vibe -------------------------------------------------------------------

def test_vibe_flags_failing_auth(tmp_path, monkeypatch):
    root = tmp_path / ".vibe"
    root.mkdir()
    (root / "vibe.log").write_text(
        "INFO config loaded\n"
        "INFO POST https://api.mistral.ai/v1/chat/completions 200\n"
        "ERROR POST https://api.mistral.ai/v1/chat/completions 401\n",
        encoding="utf-8")
    monkeypatch.setattr(hp_paths, "VIBE_DIR", root)

    health = next(s for s in clis.build_vibe()["sections"]
                  if s["title"] == "Connection health")
    assert health["severity"] == "crit"
    by = {f["label"]: f for f in health["fields"]}
    assert by["Last API status"]["value"] == 401
    assert by["Last API status"]["severity"] == "crit"


def test_vibe_healthy_auth_not_flagged(tmp_path, monkeypatch):
    root = tmp_path / ".vibe"
    root.mkdir()
    (root / "vibe.log").write_text(
        "INFO POST https://api.mistral.ai/v1/chat/completions 200\n", encoding="utf-8")
    monkeypatch.setattr(hp_paths, "VIBE_DIR", root)
    health = next(s for s in clis.build_vibe()["sections"]
                  if s["title"] == "Connection health")
    assert health["severity"] == "ok"


def test_vibe_never_opens_dotenv(tmp_path, monkeypatch):
    """The API key sits at the harness root, not under a credentials/ dir."""
    root = tmp_path / ".vibe"
    root.mkdir()
    (root / ".env").write_text("MISTRAL_API_KEY=sk-super-secret-value-1234567890\n",
                               encoding="utf-8")
    (root / "vibe.log").write_text("INFO 200\n", encoding="utf-8")
    monkeypatch.setattr(hp_paths, "VIBE_DIR", root)
    assert "sk-super-secret" not in json.dumps(clis.build_vibe())


# --- Muse -------------------------------------------------------------------

def test_muse_session_index(tmp_path, monkeypatch):
    root = tmp_path / "muse"
    root.mkdir()
    con = sqlite3.connect(root / "session-index.db")
    con.executescript("""
        CREATE TABLE sessions (session_id TEXT PRIMARY KEY, session_stream_id TEXT,
          session_dir TEXT, session_log_path TEXT, layout TEXT, workspace_root TEXT,
          workspace_key TEXT, provider_id TEXT, model_id TEXT, git_branch TEXT,
          title TEXT NOT NULL, first_user_prompt TEXT, search_text TEXT NOT NULL,
          created_at_us INT, updated_at_us INT, prompt_count INT NOT NULL DEFAULT 0,
          status TEXT NOT NULL, status_rank INT NOT NULL, source_fingerprint TEXT,
          indexed_at_us INT NOT NULL, latest_segment_terminated INT NOT NULL DEFAULT 0);
        INSERT INTO sessions (session_id, title, first_user_prompt, search_text,
                              provider_id, model_id, git_branch, prompt_count,
                              status, status_rank, indexed_at_us, updated_at_us)
        VALUES ('s1','Fix the parser','SECRET PROMPT BODY','x','meta','muse-1',
                'main', 7, 'idle', 0, 1, 1787000000000000);
    """)
    con.commit(); con.close()
    monkeypatch.setattr(hp_paths, "MUSE_DIR", root)
    monkeypatch.setattr(hp_paths, "MUSE_SESSIONS_DIR", root / "sessions")

    doc = clis.build_muse()
    sess = next(s for s in doc["sections"] if s["title"] == "Sessions")
    assert sess["total"] == 1
    assert sess["rows"][0][0] == "Fix the parser"
    assert sess["rows"][0][4] == 7, "prompt_count"
    assert "SECRET PROMPT BODY" not in json.dumps(doc)


# --- Prime ------------------------------------------------------------------

def test_prime_kernel_state(tmp_path, monkeypatch):
    root = tmp_path / "agent"
    d = root / "session-artifacts" / "sess1"
    d.mkdir(parents=True)
    (d / "kernel-state.json").write_text(json.dumps({
        "version": "1", "savedNames": ["df", "model", "tokenizer"],
        "bytes": 4096, "pythonVersion": "3.11.2", "timestamp": 1787000000,
    }), encoding="utf-8")
    # The sidecar pickle must never be loaded; junk here would explode if it were.
    (d / "kernel-state.dill").write_bytes(b"\x80\x04not-a-real-pickle")
    monkeypatch.setattr(hp_paths, "PRIME_DIR", root)
    monkeypatch.setattr(hp_paths, "PRIME_SESSIONS_DIR", root / "sessions")

    ck = next(s for s in clis.build_prime()["sections"]
              if s["title"] == "Persisted kernel state")
    assert ck["rows"][0][1] == 3, "three variables carried across turns"
    assert "df" in ck["rows"][0][2]


# --- pi ---------------------------------------------------------------------

def test_pi_mcp_and_trust(tmp_path, monkeypatch):
    root = tmp_path / "agent"
    root.mkdir(parents=True)
    (root / "mcp.json").write_text(json.dumps({
        "mcpServers": {"github": {"command": "npx", "args": ["-y", "server-github"],
                                  "env": {"TOKEN": "ghp_should_never_appear_here"}}}
    }), encoding="utf-8")
    (root / "trust.json").write_text(json.dumps({"/a": True, "/b": True, "/c": False}),
                                     encoding="utf-8")
    monkeypatch.setattr(hp_paths, "PI_DIR", root)

    doc = clis.build_pi()
    mcp = next(s for s in doc["sections"] if s["title"] == "MCP servers")
    assert mcp["rows"][0][0] == "github"
    perms = next(s for s in doc["sections"] if s["kind"] == "permissions")
    assert {f["label"]: f["value"] for f in perms["fields"]}["Trusted directories"] == 2
    assert "ghp_should_never_appear_here" not in json.dumps(doc), \
        "MCP env values can hold tokens and must not be emitted"


# --- DSH --------------------------------------------------------------------

def test_dsh_profiles_and_workspaces(tmp_path, monkeypatch):
    root = tmp_path / ".dsh"
    (root / "profiles" / "web").mkdir(parents=True)
    (root / "profiles" / "web" / "cordis.yml").write_text("[]", encoding="utf-8")
    (root / "profiles" / "node_modules").mkdir(parents=True)
    (root / "storages").mkdir(parents=True)
    (root / "storages" / "workspace.json").write_text(json.dumps({
        "tables": {"workspaces": {"w1": {"path": "/tmp/repo", "title": "My repo",
                                         "sessionIds": ["a", "b"],
                                         "updatedAt": 1787000000000}}}
    }), encoding="utf-8")
    monkeypatch.setattr(hp_paths, "DSH_DIR", root)

    doc = clis.build_dsh()
    prof = next(s for s in doc["sections"] if s["title"] == "Sandbox profiles")
    names = {r[0] for r in prof["rows"]}
    assert "web" in names
    assert "node_modules" not in names, "bundled deps are not a sandbox profile"
    ws = next(s for s in doc["sections"] if s["title"] == "Workspaces")
    assert ws["rows"][0][0] == "My repo" and ws["rows"][0][1] == 2
    # zstandard is a declared dependency, so nothing should be flagged missing.
    assert not [n for n in doc["not_available"] if n["kind"] == "sessions"]


def test_dsh_explains_zero_sessions_without_zstandard(tmp_path, monkeypatch):
    """A missing codec must name itself, not just yield zero.

    Without `zstandard` the scanner skips DSH transcripts silently, so the agent
    shows sessions on disk and none counted. Nothing on screen explained the
    gap; this pins that it now does, and quotes the real file count.
    """
    root = tmp_path / ".dsh"
    sess = root / "sessions" / "slug" / "session-1"
    sess.mkdir(parents=True)
    (sess / "session.jsonl.zstd").write_bytes(b"\x28\xb5\x2f\xfd")
    monkeypatch.setattr(hp_paths, "DSH_DIR", root)

    real_import = builtins.__import__

    def no_zstd(name, *a, **kw):
        if name == "zstandard":
            raise ImportError("No module named 'zstandard'")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", no_zstd)
    doc = clis.build_dsh()

    note = next(n for n in doc["not_available"] if n["kind"] == "sessions")
    assert "zstandard" in note["reason"]
    assert "1 session file " in note["reason"], "singular, and the real count"
    assert "start.sh" in note["reason"], "tell the user what to actually do"


# --- Gemini -----------------------------------------------------------------

def test_gemini_trust_and_project_resolver(tmp_path, monkeypatch):
    root = tmp_path / ".gemini"
    (root / "history" / "myrepo").mkdir(parents=True)
    (root / "history" / "myrepo" / ".project_root").write_text(
        "/Users/dev/Documents/myrepo\n", encoding="utf-8")
    (root / "trustedFolders.json").write_text(
        json.dumps({"/a": "TRUST_FOLDER", "/b": "TRUST_FOLDER"}), encoding="utf-8")
    (root / "config").mkdir(parents=True)
    (root / "config" / "mcp_config.json").write_text(
        json.dumps({"mcpServers": {"chrome": {}}}), encoding="utf-8")
    monkeypatch.setattr(hp_paths, "GEMINI_DIR", root)

    doc = ides.build_gemini()
    perms = next(s for s in doc["sections"] if s["kind"] == "permissions")
    assert {f["label"]: f["value"] for f in perms["fields"]}["Trusted folders"] == 2
    projects = next(s for s in doc["sections"] if s["title"] == "Known projects")
    assert projects["rows"][0] == ["myrepo", "myrepo"]
    assert doc["disk"] is None, \
        "~/.gemini is mostly Antigravity and a browser profile; don't bill the CLI for it"


# --- Antigravity ------------------------------------------------------------

_AG_SCHEMA = """
    CREATE TABLE conversation_summaries (conversation_id TEXT PRIMARY KEY,
      title TEXT NOT NULL DEFAULT "", preview TEXT NOT NULL DEFAULT "",
      step_count INTEGER NOT NULL DEFAULT 0, last_modified_time datetime NOT NULL,
      workspace_uris TEXT NOT NULL, status TEXT NOT NULL DEFAULT "",
      source TEXT NOT NULL DEFAULT "", project_id TEXT NOT NULL DEFAULT "",
      agent_name TEXT NOT NULL DEFAULT "",
      parent_conversation_id TEXT NOT NULL DEFAULT "",
      nesting_depth INTEGER NOT NULL DEFAULT 0,
      battle_id TEXT NOT NULL DEFAULT "",
      winning_conversation_id TEXT NOT NULL DEFAULT "",
      not_fully_idle numeric NOT NULL DEFAULT false,
      killed numeric NOT NULL DEFAULT false,
      last_user_input_time datetime NOT NULL,
      last_user_input_step_index INTEGER NOT NULL DEFAULT -1,
      app_data_dir TEXT NOT NULL DEFAULT "");
"""


def test_antigravity_battles_and_surface_labels(tmp_path, monkeypatch):
    cli = tmp_path / "antigravity-cli"
    cli.mkdir(parents=True)
    con = sqlite3.connect(cli / "conversation_summaries.db")
    con.executescript(_AG_SCHEMA + """
        INSERT INTO conversation_summaries
          (conversation_id,title,step_count,last_modified_time,workspace_uris,
           status,agent_name,battle_id,winning_conversation_id,killed,last_user_input_time)
        VALUES ('c1','Attempt one',5,'2026-08-01','file:///tmp/repo','idle','agy','b1','c2',0,'2026-08-01'),
               ('c2','Attempt two',7,'2026-08-01','file:///tmp/repo','idle','agy','b1','c2',0,'2026-08-01'),
               ('c3','Solo run',3,'2026-08-01','file:///tmp/repo','idle','agy','','',1,'2026-08-01');
    """)
    con.commit(); con.close()
    monkeypatch.setattr(hp_paths, "ANTIGRAVITY_SURFACES", [(cli, "cli")])
    monkeypatch.setattr(hp_paths, "GEMINI_DIR", tmp_path)

    doc = ides.build_antigravity(with_disk=False)
    convo = next(s for s in doc["sections"] if s["title"] == "Conversations")
    assert convo["total"] == 3
    # Look up by column name: empty columns are dropped, so positions shift.
    recs = [dict(zip(convo["columns"], r)) for r in convo["rows"]]
    assert all(r["Surface"] == "cli" for r in recs), "rows carry their surface label"
    assert any(r["Status"] == "killed" for r in recs)

    battles = next(s for s in doc["sections"] if s["title"] == "Agent battles")
    assert battles["count"] == 1
    statuses = {c["status"] for c in battles["tree"][0]["children"]}
    assert statuses == {"winner", "attempt"}


def test_antigravity_uses_preview_and_parses_workspace_uri(tmp_path, monkeypatch):
    """Regression, from live data: `title` is empty on all 131 real rows.

    `preview` carries the label. `workspace_uris` is a JSON array of file://
    URIs, so splitting the raw string on "/" left a trailing `"]` on the name.
    """
    cli = tmp_path / "antigravity-cli"
    cli.mkdir(parents=True)
    con = sqlite3.connect(cli / "conversation_summaries.db")
    con.executescript(_AG_SCHEMA + """
        INSERT INTO conversation_summaries
          (conversation_id,title,preview,step_count,last_modified_time,
           workspace_uris,status,agent_name,last_user_input_time)
        VALUES ('c1','','Integrating Coding Agent Features',9,'2026-08-01',
                '["file:///Users/dev/Documents/Developer/tokentelemetry"]','','','2026-08-01');
    """)
    con.commit(); con.close()
    monkeypatch.setattr(hp_paths, "ANTIGRAVITY_SURFACES", [(cli, "cli")])
    monkeypatch.setattr(hp_paths, "GEMINI_DIR", tmp_path)

    convo = next(s for s in ides.build_antigravity(with_disk=False)["sections"]
                 if s["title"] == "Conversations")
    row = dict(zip(convo["columns"], convo["rows"][0]))
    assert row["Title"] == "Integrating Coding Agent Features"
    assert row["Workspace"] == "tokentelemetry", \
        'the JSON array wrapper must be parsed, not left as tokentelemetry"]'
    # agent_name and status are empty on every row, so those columns are dropped
    # rather than rendered as a wall of em dashes.
    assert "Agent" not in convo["columns"] and "Status" not in convo["columns"]


def test_antigravity_surfaces_are_not_merged(tmp_path, monkeypatch):
    """Three surfaces share a layout; merging them double-counts a conversation."""
    surfaces = []
    for label in ("cli", "ide"):
        d = tmp_path / f"antigravity-{label}"
        d.mkdir(parents=True)
        con = sqlite3.connect(d / "conversation_summaries.db")
        con.executescript(_AG_SCHEMA + f"""
            INSERT INTO conversation_summaries
              (conversation_id,title,step_count,last_modified_time,workspace_uris,
               status,last_user_input_time)
            VALUES ('shared','Same conversation',1,'2026-08-01','','idle','2026-08-01');
        """)
        con.commit(); con.close()
        surfaces.append((d, label))
    monkeypatch.setattr(hp_paths, "ANTIGRAVITY_SURFACES", surfaces)
    monkeypatch.setattr(hp_paths, "GEMINI_DIR", tmp_path)

    convo = next(s for s in ides.build_antigravity(with_disk=False)["sections"]
                 if s["title"] == "Conversations")
    labels = sorted(r[1] for r in convo["rows"])
    assert labels == ["cli", "ide"], "each surface reports separately, labelled"


# --- Cursor -----------------------------------------------------------------

_CURSOR_SCHEMA = """
    CREATE TABLE scored_commits (commitHash TEXT NOT NULL, branchName TEXT NOT NULL,
      scoredAt INTEGER NOT NULL, linesAdded INTEGER, linesDeleted INTEGER,
      tabLinesAdded INTEGER, tabLinesDeleted INTEGER, composerLinesAdded INTEGER,
      composerLinesDeleted INTEGER, humanLinesAdded INTEGER, humanLinesDeleted INTEGER,
      blankLinesAdded INTEGER, blankLinesDeleted INTEGER, commitMessage TEXT,
      commitDate TEXT, v1AiPercentage TEXT, v2AiPercentage TEXT,
      PRIMARY KEY (commitHash, branchName));
"""


def test_cursor_ai_percentage_empty_state(tmp_path, monkeypatch):
    root = tmp_path / ".cursor"
    (root / "ai-tracking").mkdir(parents=True)
    con = sqlite3.connect(root / "ai-tracking" / "ai-code-tracking.db")
    con.executescript(_CURSOR_SCHEMA)
    con.commit(); con.close()
    monkeypatch.setattr(hp_paths, "CURSOR_DIR", root)

    sec = next(s for s in ides.build_cursor(with_disk=False)["sections"]
               if s["title"] == "AI-authored code")
    assert sec["rows"] == [] and sec["empty_reason"], \
        "an empty scorer is a state to explain, not a section to hide"


def test_cursor_ai_percentage_populated(tmp_path, monkeypatch):
    root = tmp_path / ".cursor"
    (root / "ai-tracking").mkdir(parents=True)
    con = sqlite3.connect(root / "ai-tracking" / "ai-code-tracking.db")
    con.executescript(_CURSOR_SCHEMA + """
        INSERT INTO scored_commits VALUES
          ('abc','main',1,100,10,30,0,50,0,20,10,0,0,'add parser','2026-08-01','70','80');
    """)
    con.commit(); con.close()
    monkeypatch.setattr(hp_paths, "CURSOR_DIR", root)

    sec = next(s for s in ides.build_cursor(with_disk=False)["sections"]
               if s["title"] == "AI-authored code")
    row = sec["rows"][0]
    assert row[2] == 100 and row[3] == 20 and row[4] == 80, \
        "By-Cursor is tab + composer lines"
    assert row[5] == "80", "the v2 percentage wins over v1"


# --- SmallCode --------------------------------------------------------------

def test_smallcode_absent_without_roots(monkeypatch):
    monkeypatch.setattr(hp_paths, "smallcode_roots", lambda: [])
    doc = clis.build_smallcode()
    assert doc["installed"] is False
    assert doc["planned"] is False, \
        "SmallCode is project-local; absence means no roots configured, not 'coming soon'"


def test_smallcode_reads_project_traces(tmp_path, monkeypatch):
    repo = tmp_path / "myrepo"
    traces = repo / ".smallcode" / "traces"
    traces.mkdir(parents=True)
    (traces / "run-abc.json").write_text(json.dumps({
        "name": "gemma load", "model": "gemma-3", "steps": [{}, {}, {}],
    }), encoding="utf-8")
    monkeypatch.setattr(hp_paths, "smallcode_roots", lambda: [repo])

    sec = next(s for s in clis.build_smallcode()["sections"] if s["title"] == "Traces")
    assert sec["rows"][0][:4] == ["gemma load", "gemma-3", 3, "myrepo"]


# --- every agent ------------------------------------------------------------

@pytest.mark.parametrize("agent", sorted(harness_panels.BUILDERS))
def test_missing_directory_yields_not_installed(agent, tmp_path, monkeypatch):
    """Every extractor degrades to not-installed rather than raising."""
    absent = tmp_path / "absent"
    for name in ("CLAUDE_DIR", "CODEX_DIR", "COPILOT_DIR", "GROK_DIR", "GEMINI_DIR",
                 "QWEN_DIR", "VIBE_DIR", "CURSOR_DIR", "PI_DIR", "DSH_DIR",
                 "CLINE_DIR", "MUSE_DIR", "PRIME_DIR", "HERMES_DIR"):
        monkeypatch.setattr(hp_paths, name, absent, raising=False)
    monkeypatch.setattr(hp_paths, "ANTIGRAVITY_SURFACES", [], raising=False)
    monkeypatch.setattr(hp_paths, "smallcode_roots", lambda: [], raising=False)
    monkeypatch.setattr(hp_paths, "opencode_data_dir", lambda: absent, raising=False)
    # The four original modules hold their own constants.
    for mod, attr in ((codex_panel, "CODEX_DIR"), (claude_panel, "CLAUDE_DIR"),
                      (copilot_panel, "COPILOT_DIR"), (grok_panel, "GROK_DIR")):
        monkeypatch.setattr(mod, attr, absent, raising=False)
    monkeypatch.setattr(claude_panel, "CLAUDE_JSON", absent / "x.json", raising=False)
    monkeypatch.setattr(copilot_panel, "STORE_DB", absent / "x.db", raising=False)
    monkeypatch.setattr(grok_panel, "UNIFIED_LOG", absent / "x.jsonl", raising=False)

    doc = harness_panels.BUILDERS[agent]()
    assert doc["installed"] is False
    assert doc["sections"] == []


# --- Hermes -----------------------------------------------------------------

def test_hermes_billing_processes_and_dashboard_link(tmp_path, monkeypatch):
    """Hermes carries only what /hermes/* doesn't, and hands off to it."""
    root = tmp_path / ".hermes"
    root.mkdir(parents=True)
    con = sqlite3.connect(root / "state.db")
    con.execute(
        "CREATE TABLE session_model_usage (session_id TEXT, model TEXT, "
        "billing_provider TEXT, billing_mode TEXT, api_call_count INT, "
        "input_tokens INT, output_tokens INT, cache_read_tokens INT, "
        "cache_write_tokens INT, reasoning_tokens INT, "
        "estimated_cost_usd REAL, actual_cost_usd REAL, cost_status TEXT)")
    con.executemany(
        "INSERT INTO session_model_usage VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", [
            ("s1", "gpt-5.4", "openai-codex", "subscription_included",
             10, 100, 20, 400, 0, 7, 0.0, 0.0, "included"),
            # An empty billing_mode is how Hermes records "not stated"; it must
            # not render as a blank cell.
            ("s2", "grok-4.3", "xai-oauth", "",
             5, 50, 10, 0, 0, 0, 0.0, 0.0, "unknown"),
        ])
    con.commit()
    con.close()

    (root / "spawn-ledger.json").write_text(json.dumps([
        {"pid": 4242, "purpose": "serve", "install": "abc123",
         "create_time": 1787748401.8,
         "argv": "/Users/dev/.hermes/hermes-agent/main.py serve"},
    ]), encoding="utf-8")
    (root / "auth.json").write_text("{}", encoding="utf-8")
    (root / ".env").write_text("KEY=sk-should-never-be-read", encoding="utf-8")

    monkeypatch.setattr(hp_paths, "HERMES_DIR", root)
    doc = hermes_panel.build_hermes(with_disk=False)
    flat = json.dumps(doc)

    assert doc["dashboard"]["href"] == "/hermes", "must hand off to its own page"

    bill = next(s for s in doc["sections"] if s["title"] == "Billing by provider")
    assert "not stated" in {r[1] for r in bill["rows"]}
    assert "$0.00" in bill["note"], "a fully subscription-routed install says so"

    procs = next(s for s in doc["sections"] if s["title"] == "Registered processes")
    assert procs["rows"][0][1] == 4242
    assert "argv" not in flat and "hermes-agent/main.py" not in flat, \
        "command lines carry absolute paths and must not be surfaced"

    sec = next(s for s in doc["sections"] if s["title"] == "Credential stores")
    assert "auth.json" in json.dumps(sec) and ".env" in json.dumps(sec)
    assert "sk-should-never-be-read" not in flat, "credential values are never read"
