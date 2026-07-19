#!/usr/bin/env python3
"""Conformance tests for scripts/harness_adapters.py.

Each test builds a tiny synthetic store in a tmp dir (mirroring the real
layout verified on 2026-07-06), monkeypatches the adapter's module-level
root constant, and checks locate() attribution + scan() signals. When a
harness changes its on-disk format, the matching test is where the drift
shows up.

Run: python3 -m unittest discover -s tests -v   (stdlib only)
"""

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness_adapters as ha  # noqa: E402
import session_scan  # noqa: E402

PROJECT = "/tmp/tt-fixture-project"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ha-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def patch(self, name, value):
        old = getattr(ha, name)
        setattr(ha, name, value)
        self.addCleanup(setattr, ha, name, old)


class TestHelpers(Base):
    def test_paths_from_shell_keeps_project_paths_only(self):
        cmd = "sed -n '1,50p' src/main.py && cat /etc/hosts | grep -v '^#'"
        paths = ha.paths_from_shell(cmd, PROJECT, PROJECT)
        self.assertIn(f"{PROJECT}/src/main.py", paths)
        # /etc/hosts exists but the command text itself must never leak
        for p in paths:
            self.assertNotIn("grep", p)

    def test_paths_from_value_recurses_and_resolves(self):
        args = {"absolute_path": f"{PROJECT}/a.py",
                "nested": {"file": "b/c.ts"}, "count": 3,
                "url": "https://example.com/x.py"}
        paths = ha.paths_from_value(args, base_dir=PROJECT)
        self.assertIn(f"{PROJECT}/a.py", paths)
        self.assertIn(f"{PROJECT}/b/c.ts", paths)
        self.assertFalse(any(p.startswith("https://") for p in paths))

    def test_acc_loop_and_reread(self):
        acc = ha.Acc()
        for _ in range(3):
            acc.tool_event("Read", [f"{PROJECT}/x.py"], read=True,
                           track_files=True)
        acc.tool_event("Bash")  # path-less call breaks the run
        r = acc.result("s1")
        self.assertEqual(r["read_paths"][f"{PROJECT}/x.py"], 3)
        self.assertEqual(r["loops"][0]["count"], 3)


class TestClaude(Base):
    def test_locate_and_scan(self):
        root = self.tmp / "projects"
        d = root / ha.encode_claude_dir(PROJECT)
        d.mkdir(parents=True)
        events = [
            {"type": "assistant", "timestamp": "2026-07-01T00:00:00Z",
             "message": {"usage": {"input_tokens": 10, "output_tokens": 5,
                                   "cache_read_input_tokens": 100,
                                   "cache_creation_input_tokens": 7},
                         "content": [
                             {"type": "tool_use", "name": "Read",
                              "input": {"file_path": f"{PROJECT}/a.py"}},
                             {"type": "tool_use", "name": "Read",
                              "input": {"file_path": f"{PROJECT}/a.py"}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "is_error": True}]}},
        ]
        with open(d / "abc.jsonl", "w") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")
        self.patch("CLAUDE_PROJECTS_ROOT", root)
        refs = ha.claude_locate(PROJECT, 10)
        self.assertEqual(len(refs), 1)
        s = ha.claude_scan(refs[0], PROJECT)
        self.assertEqual(s["session_id"], "abc")
        self.assertEqual(s["tokens"], {"input": 10, "output": 5,
                                       "cache_read": 100, "cache_creation": 7})
        self.assertEqual(s["read_paths"][f"{PROJECT}/a.py"], 2)
        self.assertEqual(s["error_count"], 1)
        self.assertEqual(s["loops"][0]["count"], 2)


class TestCodex(Base):
    def _write_rollout(self, path, cwd):
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            {"type": "session_meta", "timestamp": "2026-07-01T00:00:00Z",
             "payload": {"id": "sess-1", "cwd": cwd}},
            {"type": "response_item", "payload": {
                "type": "function_call", "name": "exec_command",
                "arguments": json.dumps(
                    {"cmd": "cat src/app.py", "workdir": cwd})}},
            {"type": "response_item", "payload": {
                "type": "function_call", "name": "apply_patch",
                "arguments": json.dumps(
                    {"input": "*** Update File: src/app.py\n@@ -1 +1 @@"})}},
            {"type": "event_msg", "payload": {
                "type": "token_count", "info": {"total_token_usage": {
                    "input_tokens": 120, "cached_input_tokens": 100,
                    "output_tokens": 30}}}},
        ]
        with open(path, "w") as f:
            for e in lines:
                f.write(json.dumps(e) + "\n")

    def test_attribution_and_shell_paths(self):
        root = self.tmp / "sessions"
        self._write_rollout(root / "2026/07/01/rollout-2026-07-01T00-00-00-aa-bb-cc-dd-ee.jsonl", PROJECT)
        self._write_rollout(root / "2026/07/01/rollout-2026-07-01T00-00-01-ff-gg-hh-ii-jj.jsonl", "/somewhere/else")
        self.patch("CODEX_SESSIONS_ROOT", root)
        refs = ha.codex_locate(PROJECT, 10)
        self.assertEqual(len(refs), 1)  # the other cwd is excluded
        s = ha.codex_scan(refs[0], PROJECT)
        self.assertEqual(s["session_id"], "sess-1")
        # cat = read-ish; path extracted from cmd string, resolved to project
        self.assertEqual(s["read_paths"][f"{PROJECT}/src/app.py"], 1)
        # apply_patch marker path tracked as file touch
        self.assertEqual(s["file_paths"][f"{PROJECT}/src/app.py"], 2)
        # cumulative token event: input excludes cached
        self.assertEqual(s["tokens"], {"input": 20, "output": 30,
                                       "cache_read": 100, "cache_creation": 0})
        # the command text itself must never appear anywhere in the result
        self.assertNotIn("cat", json.dumps(s["read_paths"]) + json.dumps(s["loops"]))


class TestOpencode(Base):
    def test_locate_and_scan(self):
        db = self.tmp / "opencode.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE session (id TEXT, directory TEXT,"
                     " time_created INT, time_updated INT, tokens_input INT,"
                     " tokens_output INT, tokens_cache_read INT,"
                     " tokens_cache_write INT)")
        conn.execute("CREATE TABLE part (id INTEGER PRIMARY KEY,"
                     " session_id TEXT, data TEXT)")
        conn.execute("INSERT INTO session VALUES ('s1', ?, 1751000000000,"
                     " 1751000060000, 50, 20, 400, 0)", (PROJECT,))
        conn.execute("INSERT INTO session VALUES ('s2', '/other', 1, 2, 9, 9, 0, 0)")
        conn.execute("INSERT INTO part (session_id, data) VALUES ('s1', ?)",
                     (json.dumps({"type": "tool", "tool": "read",
                                  "state": {"status": "completed",
                                            "input": {"filePath": f"{PROJECT}/x.ts"}}}),))
        conn.execute("INSERT INTO part (session_id, data) VALUES ('s1', ?)",
                     (json.dumps({"type": "tool", "tool": "bash",
                                  "state": {"status": "error",
                                            "input": {"command": "ls src/"}}}),))
        conn.commit()
        conn.close()
        self.patch("OPENCODE_DB", db)
        refs = ha.opencode_locate(PROJECT, 10)
        self.assertEqual([r["id"] for r in refs], ["s1"])
        s = ha.opencode_scan(refs[0], PROJECT)
        self.assertEqual(s["tokens"]["input"], 50)
        self.assertEqual(s["read_paths"][f"{PROJECT}/x.ts"], 1)
        self.assertEqual(s["error_count"], 1)
        self.assertEqual(s["tool_counts"], {"read": 1, "bash": 1})


class TestQwen(Base):
    def test_scan(self):
        d = self.tmp / ha.encode_claude_dir(PROJECT) / "chats"
        d.mkdir(parents=True)
        events = [
            {"type": "assistant", "sessionId": "q1",
             "timestamp": "2026-07-01T00:00:00Z",
             "message": {"parts": [
                 {"functionCall": {"name": "read_file",
                                   "args": {"absolute_path": f"{PROJECT}/m.py"}}}]},
             "usageMetadata": {"promptTokenCount": 100,
                               "candidatesTokenCount": 10,
                               "thoughtsTokenCount": 2,
                               "cachedContentTokenCount": 60}},
        ]
        with open(d / "q1.jsonl", "w") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")
        self.patch("QWEN_PROJECTS_ROOT", self.tmp)
        refs = ha.qwen_locate(PROJECT, 10)
        s = ha.qwen_scan(refs[0], PROJECT)
        self.assertEqual(s["tokens"], {"input": 40, "output": 12,
                                       "cache_read": 60, "cache_creation": 0})
        self.assertEqual(s["read_paths"][f"{PROJECT}/m.py"], 1)


class TestCline(Base):
    def test_scan_blocks_and_metrics_fallback(self):
        db = self.tmp / "sessions.db"
        msgs = self.tmp / "m.json"
        json.dump({"messages": [
            {"role": "assistant",
             "metrics": {"inputTokens": 11, "outputTokens": 4,
                         "cacheReadTokens": 0, "cacheWriteTokens": 0},
             "content": [{"type": "tool_use", "name": "read_file",
                          "input": {"path": "math.py"}}]},
        ]}, open(msgs, "w"))
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE sessions (session_id TEXT, cwd TEXT,"
                     " workspace_root TEXT, started_at TEXT, ended_at TEXT,"
                     " metadata_json TEXT, messages_path TEXT)")
        conn.execute("INSERT INTO sessions VALUES ('c1', ?, ?, '2026-07-01',"
                     " '2026-07-01', ?, ?)",
                     (PROJECT, PROJECT,
                      json.dumps({"usage": {"inputTokens": 0, "outputTokens": 0}}),
                      str(msgs)))
        conn.commit()
        conn.close()
        self.patch("CLINE_DB", db)
        refs = ha.cline_locate(PROJECT, 10)
        s = ha.cline_scan(refs[0], PROJECT)
        self.assertEqual(s["tokens"]["input"], 11)  # metrics fallback
        self.assertEqual(s["read_paths"][f"{PROJECT}/math.py"], 1)


class TestGrok(Base):
    def test_urlencoded_dir_and_shell_extraction(self):
        d = self.tmp / urllib.parse.quote(PROJECT, safe="") / "sess-1"
        d.mkdir(parents=True)
        with open(d / "chat_history.jsonl", "w") as f:
            f.write(json.dumps({"role": "assistant", "tool_calls": [
                {"name": "run_terminal_command",
                 "arguments": json.dumps({"command": f"cat {PROJECT}/prov/data.yml"})}]}) + "\n")
            f.write(json.dumps({"role": "tool_result", "is_error": True}) + "\n")
        self.patch("GROK_SESSIONS_ROOT", self.tmp)
        refs = ha.grok_locate(PROJECT, 10)
        self.assertEqual(len(refs), 1)
        s = ha.grok_scan(refs[0], PROJECT)
        self.assertEqual(s["session_id"], "sess-1")
        # cat is read-shaped: the extracted path feeds the re-read signal
        self.assertEqual(s["read_paths"][f"{PROJECT}/prov/data.yml"], 1)
        self.assertEqual(s["error_count"], 1)
        self.assertEqual(s["tool_counts"]["run_terminal_command"], 1)


class TestCopilot(Base):
    def test_locate_by_cwd_and_tools(self):
        d = self.tmp / "sess-9"
        d.mkdir(parents=True)
        with open(d / "events.jsonl", "w") as f:
            f.write(json.dumps({"type": "session.start",
                                "data": {"context": {"cwd": PROJECT}}}) + "\n")
            f.write(json.dumps({"type": "tool.execution_start",
                                "data": {"toolName": "view",
                                         "arguments": {"path": f"{PROJECT}/z.go"}}}) + "\n")
        self.patch("COPILOT_STATE_ROOT", self.tmp)
        refs = ha.copilot_locate(PROJECT, 10)
        self.assertEqual(len(refs), 1)
        s = ha.copilot_scan(refs[0], PROJECT)
        self.assertEqual(s["read_paths"][f"{PROJECT}/z.go"], 1)


class TestHermes(Base):
    def test_null_cwd_excluded(self):
        db = self.tmp / "state.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE sessions (id TEXT, cwd TEXT, started_at TEXT,"
                     " ended_at TEXT, input_tokens INT, output_tokens INT,"
                     " cache_read_tokens INT, cache_write_tokens INT)")
        conn.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY,"
                     " session_id TEXT, role TEXT, tool_calls TEXT, tool_name TEXT)")
        conn.execute("INSERT INTO sessions VALUES ('h1', ?, 't', 't', 7, 3, 0, 0)",
                     (PROJECT,))
        conn.execute("INSERT INTO sessions VALUES ('h2', NULL, 't', 't', 9, 9, 0, 0)")
        conn.execute("INSERT INTO messages (session_id, role, tool_calls, tool_name)"
                     " VALUES ('h1', 'assistant', ?, NULL)",
                     (json.dumps([{"function": {"name": "read_file",
                                                "arguments": json.dumps({"path": f"{PROJECT}/h.rs"})}}]),))
        conn.commit()
        conn.close()
        self.patch("HERMES_ROOT", self.tmp)
        refs = ha.hermes_locate(PROJECT, 10)
        self.assertEqual([r["id"] for r in refs], ["h1"])  # null cwd excluded
        s = ha.hermes_scan(refs[0], PROJECT)
        self.assertEqual(s["tokens"]["input"], 7)
        self.assertEqual(s["read_paths"][f"{PROJECT}/h.rs"], 1)


class TestSmallcodeVibeAntigravity(Base):
    def test_smallcode_project_local(self):
        proj = self.tmp / "proj"
        traces = proj / ".smallcode" / "traces"
        traces.mkdir(parents=True)
        json.dump({"id": "t1", "startedAt": "2026-07-01T00:00:00Z",
                   "tokens": {"prompt": 5, "completion": 2},
                   "steps": [{"type": "tool_call", "name": "read_file",
                              "args": {"path": "a.c"}}]},
                  open(traces / "t1.json", "w"))
        refs = ha.smallcode_locate(str(proj), 10)
        s = ha.smallcode_scan(refs[0], str(proj))
        self.assertEqual(s["tokens"]["input"], 5)
        self.assertEqual(s["read_paths"][f"{proj}/a.c"], 1)

    def test_vibe_repr_metadata(self):
        d = self.tmp / "session"
        d.mkdir(parents=True)
        json.dump({"metadata": {
            "session_id": "v1", "start_time": "2026-07-01T00:00:00",
            "environment": repr({"working_directory": PROJECT}),
            "stats": repr({"session_prompt_tokens": 42,
                           "session_completion_tokens": 6})},
            "messages": []}, open(d / "s.json", "w"))
        self.patch("VIBE_SESSIONS_ROOT", d)
        refs = ha.vibe_locate(PROJECT, 10)
        self.assertEqual(len(refs), 1)
        s = ha.vibe_scan(refs[0], PROJECT)
        self.assertEqual(s["tokens"], {"input": 42, "output": 6,
                                       "cache_read": 0, "cache_creation": 0})

    def test_antigravity_hash_dir(self):
        import hashlib
        h = hashlib.sha256(PROJECT.encode()).hexdigest()
        d = self.tmp / h / "chats"
        d.mkdir(parents=True)
        json.dump({"sessionId": "ag1", "startTime": "2026-07-01T00:00:00Z",
                   "lastUpdated": "2026-07-01T01:00:00Z", "messages": []},
                  open(d / "c.json", "w"))
        self.patch("GEMINI_TMP_ROOT", self.tmp)
        refs = ha.antigravity_locate(PROJECT, 10)
        s = ha.antigravity_scan(refs[0], PROJECT)
        self.assertEqual(s["session_id"], "ag1")
        self.assertEqual(s["token_total"], 0)  # honest zeros


class TestSessionScanCLI(Base):
    def test_unknown_harness_exits_2(self):
        rc = session_scan.main([PROJECT, "--harness", "nope"])
        self.assertEqual(rc, 2)

    def test_harness_list_and_schema(self):
        # empty stores: still a successful scan with the full schema
        self.patch("CLAUDE_PROJECTS_ROOT", self.tmp / "none")
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = session_scan.main([PROJECT, "--harness", "claude", "--json"])
        self.assertEqual(rc, 0)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["harness"], "claude")
        self.assertIn("by_harness", out["aggregate"])
        self.assertEqual(out["capabilities"], {"claude": "full"})


if __name__ == "__main__":
    unittest.main()
