import base64
import json
import os
import re

import pytest

import recall_sources as rs

# Fake secrets are built by concatenation so no secret-shaped literal sits in the file.
TOK = "gh" + "p_" + "A1b2C3d4" * 5
KEY = "sk" + "-" + "Zy9Xw8Vu7" * 4
BEARER = "Bear" + "er " + "tok" + "en1234567890abcdef"
PWD = "hunter" + "2" * 6
SECRETS = [TOK, KEY, BEARER, PWD, "q9w8e7r6t5y4", "urlkey" + "123456789", "u" + "ser:" + "pw" + "x" * 8]


def w(p, text="x", binary=False):
    p.parent.mkdir(parents=True, exist_ok=True)
    if binary:
        p.write_bytes(text)
    else:
        p.write_text(text, encoding="utf-8")
    return p


@pytest.fixture
def tree(tmp_path):
    home = tmp_path / "home"
    proj = tmp_path / "work" / "app"
    home.mkdir()
    proj.mkdir(parents=True)
    return home, proj


def run(tree, sessions=(), images=True, env=None):
    home, proj = tree
    return rs.discover(str(proj), list(sessions), home=home, env=env if env is not None else {}, images=images)


def by_id(res):
    return {d["doc_id"]: d for d in res["documents"]}


def texts(res):
    out = []
    for d in res["documents"]:
        out.append(json.dumps(d))
        if d.get("abs_path") and d["type"] != "image":
            try:
                out.append(open(d["abs_path"], encoding="utf-8").read())
            except OSError:
                pass
    return "\n".join(out)


# --------------------------------------------------------------- never index

def test_is_never_index():
    for p in ["/h/.claude/.credentials.json", "/h/.claude/paste-cache/a.txt", "/h/.claude/file-history/s/x.md",
              "/h/.codex/auth.json", "/h/.codex/history.jsonl", "/h/.gemini/oauth_creds.json",
              "/h/.gemini/tmp/abc/shell_history", "/h/.qwen/settings.json.orig", "/h/app/.env", "/h/app/.env.local",
              "/h/.cline/data/settings/providers.json", "/h/x/credentials.yaml", "/h/.copilot/auth-token.json"]:
        assert rs.is_never_index(p), p
    for p in ["/h/app/README.md", "/h/credentials_test_dir/readme.md", "/h/.claude/skills/a/SKILL.md"]:
        assert not rs.is_never_index(p), p


def test_never_index_files_present_are_skipped(tree):
    home, proj = tree
    w(home / ".claude" / ".credentials.json", '{"a": 1}')
    w(home / ".claude" / "paste-cache" / "h.md", "pasted " + KEY)
    w(home / ".claude" / "file-history" / "s" / "n.md", "snap")
    w(home / ".codex" / "auth.json", "{}")
    w(home / ".qwen" / "settings.json.orig", '{"mcpServers": {"x": {"command": "a"}}}')
    w(proj / ".env.md", "KEY=" + KEY)
    w(proj / "credentials.md", "secret")
    w(proj / "notes.md.orig", "orig")
    w(proj / "README.md", "hello")
    res = run(tree, [{"id": "s1", "mcp_tools": ["mcp__x__t"]}])
    ids = by_id(res)
    assert "markdown:repo:project:README.md" in ids
    blob = texts(res)
    assert KEY not in blob
    assert not any("credentials" in d["source"]["path"] or ".env" in d["source"]["path"] or "paste-cache" in d["source"]["path"]
                   for d in res["documents"])
    assert res["skipped"].get("never_index", 0) >= 2
    assert not any(d["type"] == "mcp" for d in res["documents"])  # .orig backup is never parsed


# ------------------------------------------------------------------ claude

def test_claude_skills_commands_agents_plans(tree):
    home, proj = tree
    w(proj / ".claude" / "skills" / "local-skill" / "SKILL.md", "---\nname: local-skill\n---\nbody")
    w(home / ".claude" / "skills" / "used-skill" / "SKILL.md", "u")
    w(home / ".claude" / "skills" / "unused-skill" / "SKILL.md", "n")
    w(home / ".claude" / "commands" / "git" / "ship.md", "ship")
    w(home / ".claude" / "commands" / "other.md", "other")
    w(proj / ".claude" / "commands" / "deploy.md", "deploy")
    w(proj / ".claude" / "agents" / "reviewer.md", "r")
    w(home / ".claude" / "agents" / "explorer.md", "e")
    w(home / ".claude" / "agents" / "idle.md", "i")
    w(home / ".claude" / "plans" / "wobbly-plan.md", "plan")
    w(home / ".claude" / "plans" / "other-plan.md", "plan2")
    w(home / ".claude" / "CLAUDE.md", "global rules")
    w(proj / "CLAUDE.md", "project rules")
    w(proj / ".claude" / "rules" / "style.md", "style")
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(proj))
    w(home / ".claude" / "projects" / slug / "memory" / "MEMORY.md", "mem")
    w(home / ".claude" / "projects" / (slug + "x") / "memory" / "MEMORY.md", "other project")
    sessions = [{"id": "s1", "agent": "claude", "skills_used": [{"name": "used-skill", "count": 2}, {"name": "git:ship", "count": 1}],
                 "delegation": {"by_type": {"explorer": {"count": 1}}}, "plans": [{"path": "/x/y/wobbly-plan.md"}]}]
    res = run(tree, sessions)
    ids = by_id(res)
    assert "skill:claude:project:.claude/skills/local-skill/SKILL.md" in ids
    assert "skill:claude:user:.claude/skills/used-skill/SKILL.md" in ids
    assert not any("unused-skill" in i for i in ids)
    assert "command:claude:user:.claude/commands/git/ship.md" in ids
    assert not any(i.endswith(":other") for i in ids)
    assert "command:claude:project:deploy" in ids
    assert "agent:claude:project:reviewer" in ids and "agent:claude:user:.claude/agents/explorer.md" in ids
    assert "agent:claude:user:.claude/agents/idle.md" not in ids
    assert "artifact:claude:user:.claude/plans/wobbly-plan.md" in ids
    assert not any("other-plan" in i for i in ids)
    assert "markdown:claude:user:.claude/CLAUDE.md" in ids
    assert "markdown:claude:project:CLAUDE.md" in ids
    assert any(i.startswith("markdown:claude:user:.claude/projects/") and i.endswith("MEMORY.md") for i in ids)
    assert not any(slug + "x" in d["source"]["path"] for d in res["documents"])
    assert res["skipped"]["unused_user_item"] >= 3
    sk = ids["skill:claude:user:.claude/skills/used-skill/SKILL.md"]
    assert sk["source"]["path"] == "~/.claude/skills/used-skill/SKILL.md"
    assert sk["cheap_fp"] and sk["agent"] == "claude" and sk["scope"] == "user" and sk["type"] == "skill"
    # stable ids across runs
    assert [d["doc_id"] for d in run(tree, sessions)["documents"]] == [d["doc_id"] for d in res["documents"]]


def test_claude_plugin_skill_used_by_namespaced_name(tree):
    home, _ = tree
    w(home / ".claude" / "plugins" / "cache" / "mk" / "pl" / "1.0" / "skills" / "brain" / "SKILL.md", "b")
    w(home / ".claude" / "plugins" / "cache" / "mk" / "pl" / "1.0" / "skills" / "lint" / "SKILL.md", "l")
    res = run(tree, [{"id": "s", "skills_used": [{"name": "pl:brain"}]}])
    titles = {d["title"] for d in res["documents"] if d["type"] == "skill"}
    assert titles == {"brain"}


def test_claude_mcp_all_sources_strip_secrets(tree):
    home, proj = tree
    w(proj / ".mcp.json", json.dumps({"mcpServers": {
        "github": {"command": "npx", "args": ["-y", "gh-mcp", "--token", TOK, "--api-key=" + KEY, "--port", "8080"],
                   "env": {"GITHUB_TOKEN": TOK}},
        "remote": {"type": "http", "url": "https://api.example.com/mcp/q9w8e7r6t5y4?key=urlkey123456789",
                   "headers": {"Authorization": BEARER}},
        "withinfo": {"url": "https://u" + "ser:" + "pw" + "x" * 8 + "@host.example.com:8443/p"},
        "dockerish": {"command": "docker", "args": ["run", "-e", "API_PASSWORD=" + PWD, "-H", BEARER, "img", "FOO_TOKEN=" + TOK, "--name=ok"]},
    }}))
    w(home / ".claude.json", json.dumps({
        "oauthAccount": {"emailAddress": "a@b.c"},
        "mcpServers": {"usedsrv": {"command": "srv", "env": {"K": KEY}}, "idlesrv": {"command": "idle"}},
        "projects": {str(proj): {"mcpServers": {"localsrv": {"command": "loc", "args": ["--secret", PWD]}}},
                     "/elsewhere": {"mcpServers": {"nope": {"command": "n"}}}}}))
    sessions = [{"id": "s", "mcp_usage": {"usedsrv": {"do_thing": 3}}, "tool_counts": {"mcp__github__list": 1}}]
    res = run(tree, sessions)
    mcp = {d["title"]: d for d in res["documents"] if d["type"] == "mcp"}
    assert set(mcp) == {"github", "remote", "withinfo", "dockerish", "usedsrv", "localsrv"}
    assert mcp["usedsrv"]["scope"] == "user" and mcp["localsrv"]["scope"] == "project"
    assert "do_thing" in mcp["usedsrv"]["text"]
    blob = texts(res)
    for s in SECRETS + [TOK, KEY, PWD]:
        assert s not in blob, s
    assert "MCP server github (claude, project): transport stdio, command npx -y gh-mcp --port 8080" in mcp["github"]["text"]
    assert "url https://api.example.com" in mcp["remote"]["text"] and "key=" not in mcp["remote"]["text"]
    assert "host.example.com:8443" in mcp["withinfo"]["text"]
    assert "--name=ok" in mcp["dockerish"]["text"]
    assert "idlesrv" not in blob and "nope" not in blob
    # a .mcp.json shared by several agents yields one document per server
    assert sum(1 for d in res["documents"] if d["type"] == "mcp" and d["title"] == "github") == 1


def test_strip_secrets_unit():
    cfg = {"command": "node", "args": ["srv.js", "--password", "p", "--auth=zz", "--region", "eu",
                                         "A" * 40, "https://h.example.com/x?token=abc", "/abs/path/to/file"],
           "env": {"A": "b"}, "headers": {"X": "y"}, "includeTools": ["t1"]}
    out = rs.strip_secrets(cfg)
    assert out["args"] == ["srv.js", "--region", "eu", "https://h.example.com", "/abs/path/to/file"]
    assert out["tools"] == ["t1"] and out["transport"] == "stdio"
    assert "env" not in out and "headers" not in out
    assert rs.strip_secrets({"command": ["bun", "x", "--token", "t"]})["args"] == ["x"]
    assert rs.strip_secrets("junk")["transport"] == "unknown"


# ------------------------------------------------------------------ codex

def test_codex_toml_mcp_skills_and_images(tree):
    home, proj = tree
    w(home / ".codex" / "config.toml",
      '[mcp_servers.gh]\ncommand = "npx"\nargs = ["gh", "--token", "' + TOK + '"]\nbearer_token = "' + BEARER + '"\n'
      '[mcp_servers.gh.env]\nGITHUB_TOKEN = "' + TOK + '"\n'
      '[mcp_servers.web]\nurl = "https://x.example.com/mcp?api_key=' + KEY + '"\n'
      '[mcp_servers.web.http_headers]\nAuthorization = "' + BEARER + '"\n')
    w(home / ".codex" / "skills" / "tdd" / "SKILL.md", "t")
    w(home / ".codex" / "prompts" / "fix.md", "f")
    w(home / ".codex" / "agents" / "helper.toml", "name='h'")
    w(home / ".codex" / "AGENTS.md", "g")
    w(home / ".codex" / "memories" / "m.md", "mem")
    w(proj / "AGENTS.md", "a")
    w(proj / ".agents" / "skills" / "pskill" / "SKILL.md", "p")
    png = bytes([0x89]) + b"PNG" + b"\0" * 10
    w(home / ".codex" / "generated_images" / "sess-1" / "a.png", png, binary=True)
    w(home / ".codex" / "generated_images" / "sess-2" / "b.png", png, binary=True)
    w(home / ".codex" / "auth.json", "{}")
    sessions = [{"id": "sess-1", "agent": "codex", "mcp_tools": ["mcp__gh__list_prs"], "skills_used": [{"name": "tdd"}]}]
    res = run(tree, sessions)
    ids = by_id(res)
    assert "skill:codex:user:.codex/skills/tdd/SKILL.md" in ids and "skill:codex:project:.agents/skills/pskill/SKILL.md" in ids
    assert "markdown:codex:user:.codex/AGENTS.md" in ids and "markdown:codex:project:AGENTS.md" in ids
    assert "markdown:codex:user:.codex/memories/m.md" in ids
    mcp = {d["title"]: d for d in res["documents"] if d["type"] == "mcp"}
    assert set(mcp) == {"gh"}                      # web unused by sessions
    assert "list_prs" in mcp["gh"]["text"]
    assert not any(d["type"] == "command" for d in res["documents"])  # fix unused
    imgs = [d for d in res["documents"] if d["type"] == "image"]
    assert len(imgs) == 1 and imgs[0]["session_id"] == "sess-1" and imgs[0]["mime"] == "image/png"
    assert res["skipped"].get("unlinked_image") == 1
    blob = texts(res)
    for s in (TOK, KEY, BEARER):
        assert s not in blob
    res2 = run(tree, sessions + [{"id": "s3", "mcp_tools": ["mcp__web__q"]}], images=False)
    assert not any(d["type"] == "image" for d in res2["documents"])
    web = [d for d in res2["documents"] if d["title"] == "web"][0]
    assert KEY not in web["text"] and "https://x.example.com" in web["text"]


# ------------------------------------------------------------ antigravity

def test_antigravity_brain_images_and_mcp(tree):
    home, proj = tree
    base = home / ".gemini" / "antigravity"
    w(base / "brain" / "conv-1" / "implementation_plan.md", "plan")
    w(base / "brain" / "conv-1" / "implementation_plan.md.metadata.json", "{}")
    w(base / "brain" / "conv-1" / "shot.png", b"\x89PNG\0", binary=True)
    w(base / "brain" / "conv-2" / "task.md", "other conv")
    w(home / ".gemini" / "antigravity-backup" / "brain" / "conv-1" / "dup.md", "backup")
    w(base / "mcp_config.json", json.dumps({"mcpServers": {"fs": {"command": "fs", "args": ["--key", KEY], "env": {"A": KEY}, "serverUrl": "https://s.example.com/x?k=1"}}}))
    w(base / "mcp_config.json.bak", json.dumps({"mcpServers": {"bak": {"command": "b"}}}))
    w(base / "skills" / "agy-skill" / "SKILL.md", "s")
    w(proj / ".agents" / "rules" / "r.md", "rule")
    res = run(tree, [{"id": "conv-1", "agent": "antigravity", "mcp_tools": ["mcp__fs__read"], "skills_used": [{"name": "agy-skill"}]}])
    ids = by_id(res)
    assert "artifact:antigravity:user:.gemini/antigravity/brain/conv-1/implementation_plan.md" in ids
    assert not any("conv-2" in i or "backup" in i or "dup.md" in i for i in ids)
    assert any(d["type"] == "image" and d["title"] == "shot.png" for d in res["documents"])
    assert not any(d["title"] == "bak" for d in res["documents"])
    fs = [d for d in res["documents"] if d["type"] == "mcp" and d["title"] == "fs"][0]
    assert KEY not in fs["text"] and "s.example.com" in fs["text"]
    assert "skill:antigravity:user:" + [i for i in ids if i.endswith("skills/agy-skill/SKILL.md") and i.startswith("skill:antigravity:user:")][0].split(":user:")[1] in ids
    assert any(i.startswith("markdown:") and i.endswith(".agents/rules/r.md") for i in ids)
    assert res["skipped"]["unlinked_artifact"] >= 1


# ------------------------------------------------------------------ cursor

def test_cursor_rules_skills_mcp(tree):
    home, proj = tree
    w(proj / ".cursor" / "rules" / "style.mdc", "---\nalwaysApply: true\n---\nuse tabs")
    w(proj / ".cursorrules", "legacy")
    w(proj / ".cursor" / "skills" / "cs" / "SKILL.md", "s")
    w(proj / ".cursor" / "mcp.json", json.dumps({"mcpServers": {"p": {"command": "c", "env": {"K": KEY}}}}))
    w(home / ".cursor" / "mcp.json", json.dumps({"mcpServers": {"g": {"url": "https://g.example.com/mcp", "headers": {"Authorization": BEARER}}}}))
    w(home / ".cursor" / "agents" / "ca.md", "a")
    res = run(tree, [{"id": "s", "agent": "cursor", "mcp_tools": ["mcp__g__x"], "subagents": [{"agent_type": "ca"}]}])
    ids = by_id(res)
    assert "markdown:cursor:project:.cursor/rules/style.mdc" in ids
    assert "markdown:cursor:project:.cursorrules" in ids
    assert "skill:cursor:project:.cursor/skills/cs/SKILL.md" in ids
    assert "agent:cursor:user:.cursor/agents/ca.md" in ids
    titles = {d["title"] for d in res["documents"] if d["type"] == "mcp"}
    assert titles == {"p", "g"}
    assert KEY not in texts(res) and BEARER not in texts(res)


# ---------------------------------------------------------------- opencode

def test_opencode_jsonc_mcp_and_xdg(tree):
    home, proj = tree
    w(home / "xdg" / "opencode" / "opencode.jsonc",
      '// comment\n{"mcp": {"ctx": {"type": "local", "command": ["npx", "ctx", "--token", "' + TOK + '"],\n'
      '"environment": {"A": "' + KEY + '"}, /* c */ "enabled": true,},\n'
      '"rem": {"type": "remote", "url": "https://r.example.com/s?x=1", "headers": {"Authorization": "' + BEARER + '"}}}}')
    w(home / "xdg" / "opencode" / "skills" / "oc" / "SKILL.md", "s")
    w(home / "xdg" / "opencode" / "AGENTS.md", "g")
    w(proj / ".opencode" / "agents" / "oa.md", "a")
    w(proj / ".opencode" / "plans" / "p.md", "plan")
    res = run(tree, [{"id": "s", "mcp_usage": {"ctx": {"t": 1}, "rem": {"t": 1}}, "skills_used": [{"name": "oc"}]}],
              env={"XDG_CONFIG_HOME": str(home / "xdg")})
    ids = by_id(res)
    assert {d["title"] for d in res["documents"] if d["type"] == "mcp"} == {"ctx", "rem"}
    assert "skill:opencode:user:xdg/opencode/skills/oc/SKILL.md" in ids and "agent:opencode:project:oa" in ids
    assert "artifact:opencode:project:.opencode/plans/p.md" in ids
    blob = texts(res)
    assert TOK not in blob and KEY not in blob and BEARER not in blob
    ctx = [d for d in res["documents"] if d["title"] == "ctx"][0]
    assert "command npx ctx" in ctx["text"] and "transport stdio" in ctx["text"]


# ------------------------------------------------------------------ gemini

def test_gemini_commands_instr_mcp_tmp(tree):
    import hashlib
    home, proj = tree
    w(proj / "GEMINI.md", "g")
    w(proj / ".gemini" / "commands" / "git" / "commit.toml", 'prompt = "x"')
    w(proj / ".gemini" / "settings.json", json.dumps({"mcpServers": {"pg": {"command": "pg", "env": {"P": PWD}, "includeTools": ["q"]}}}))
    w(home / ".gemini" / "GEMINI.md", "global")
    w(home / ".gemini" / "oauth_creds.json", '{"t": "x"}')
    h = hashlib.sha256(str(proj.resolve()).encode()).hexdigest()
    w(home / ".gemini" / "tmp" / h / "plans" / "plan.md", "plan")
    w(home / ".gemini" / "tmp" / h / "shell_history", "export " + KEY)
    w(home / ".gemini" / "tmp" / h / "images" / "clip.png", b"\x89PNG\0", binary=True)
    res = run(tree)
    ids = by_id(res)
    assert "markdown:gemini:project:GEMINI.md" in ids and "markdown:gemini:user:.gemini/GEMINI.md" in ids
    assert "command:gemini:project:git:commit" in ids
    assert any(d["type"] == "artifact" and d["title"] == "plan.md" for d in res["documents"])
    assert any(d["type"] == "image" and d["title"] == "clip.png" for d in res["documents"])
    pg = [d for d in res["documents"] if d["type"] == "mcp"][0]
    assert "tools: q" in pg["text"] and PWD not in pg["text"]
    assert KEY not in texts(res)


# ------------------------------------------------------------ project walk

def test_walk_excludes_worktrees_symlinks_source_and_large(tree, tmp_path):
    home, proj = tree
    w(proj / "README.md", "r")
    w(proj / "docs" / "guide.mdx", "g")
    w(proj / "src" / "main.py", "print(1)")
    w(proj / "src" / "app.ts", "export {}")
    w(proj / "src" / "NOTES.md", "n")
    w(proj / "node_modules" / "pkg" / "README.md", "dep")
    w(proj / ".venv" / "lib" / "x.md", "v")
    w(proj / "dist" / "out.md", "d")
    w(proj / ".claude" / "worktrees" / "copy" / "README.md", "dup")
    w(proj / ".claude" / "worktrees" / "copy" / "CLAUDE.md", "dup")
    w(proj / ".worktrees" / "w" / "A.md", "dup")
    w(proj / ".gitignore", "generated/\n*.log\n# c\n")
    w(proj / "generated" / "g.md", "gen")
    w(proj / "big.md", "x" * (1_000_000 + 10))
    outside = tmp_path / "outside"
    w(outside / "secret.md", "outside " + KEY)
    os.symlink(outside, proj / "linkdir")
    os.symlink(proj, proj / "docs" / "loop")
    os.symlink(outside / "secret.md", proj / "linkfile.md")
    res = run(tree)
    paths = {d["source"]["path"] for d in res["documents"]}
    rels = {os.path.relpath(d["abs_path"], proj).replace(os.sep, "/") for d in res["documents"]}
    assert rels == {"README.md", "docs/guide.mdx", "src/NOTES.md"}
    assert KEY not in texts(res)
    assert res["skipped"]["too_large"] == 1
    assert res["skipped"]["nested_worktree"] >= 2
    assert res["skipped"]["symlink_outside"] >= 1
    assert not any(p.endswith((".py", ".ts")) for p in paths)


def test_walk_cap_2000(tree):
    home, proj = tree
    for i in range(2010):
        w(proj / "d" / f"f{i:04d}.md", "x")
    res = run(tree)
    assert len(res["documents"]) == 2000
    assert res["skipped"]["md_cap"] == 10


def test_fingerprint_changes_with_file(tree):
    home, proj = tree
    f = w(proj / "README.md", "one")
    a = by_id(run(tree))["markdown:repo:project:README.md"]
    f.write_text("a longer body", encoding="utf-8")
    os.utime(f, (a["mtime"] + 5, a["mtime"] + 5))
    b = by_id(run(tree))["markdown:repo:project:README.md"]
    assert a["cheap_fp"] != b["cheap_fp"] and b["size"] == len("a longer body")


def test_missing_everything_never_raises(tree):
    res = rs.discover("/no/such/project", [{"id": 1}, "junk", None], home=tree[0], env={}, images=True)
    assert res["documents"] == [] and res["skipped"].get("missing", 0) > 0
    bad = tree[1] / ".mcp.json"
    w(bad, "{not json")
    assert run(tree)["skipped"]["parse_error"] >= 1


# -------------------------------------------------------- misc agent layouts

def test_assorted_agents(tree):
    home, proj = tree
    w(home / ".kimi-code" / "skills" / "ks" / "SKILL.md", "s")
    w(home / ".kimi-code" / "mcp.json", json.dumps({"mcpServers": {"k": {"command": "k"}}}))
    w(home / ".vibe" / "agents" / "va.toml", "x=1")
    w(home / ".vibe" / "config.toml", '[[mcp_servers]]\nname = "vm"\ncommand = "vm"\nargs = ["--api-key", "' + KEY + '"]\n')
    w(home / ".hermes" / "skills" / "cat" / "hs" / "SKILL.md", "s")
    w(home / ".hermes" / "memories" / "MEMORY.md", "m")
    w(home / ".hermes" / "config.yaml", "mcp_servers:\n  hm:\n    command: hm\n    env:\n      T: " + KEY + "\n")
    w(home / ".qoder" / "AGENTS.md", "q")
    w(proj / ".clinerules", "rules file")
    w(proj / "memory-bank" / "ctx.md", "bank")
    w(proj / ".smallcode" / "skills" / "sc" / "SKILL.md", "s")
    w(proj / ".github" / "copilot-instructions.md", "ci")
    w(proj / ".github" / "prompts" / "p.prompt.md", "pp")
    w(proj / ".qwen" / "commands" / "q.toml", 'prompt="x"')
    sessions = [{"id": "s", "skills_used": [{"name": "ks"}, {"name": "hs"}],
                 "mcp_tools": ["mcp__k__a", "mcp__vm__b", "mcp__hm__c"], "subagents": ["va"]}]
    res = run(tree, sessions)
    ids = by_id(res)
    for want in ["skill:kimi:user:.kimi-code/skills/ks/SKILL.md", "agent:vibe:user:.vibe/agents/va.toml", "skill:hermes:user:.hermes/skills/cat/hs/SKILL.md", "markdown:hermes:user:.hermes/memories/MEMORY.md",
                 "markdown:qoder:user:.qoder/AGENTS.md", "markdown:cline:project:.clinerules", "markdown:cline:project:memory-bank/ctx.md",
                 "skill:smallcode:project:.smallcode/skills/sc/SKILL.md", "markdown:copilot:project:.github/copilot-instructions.md",
                 "command:qwen:project:q"]:
        assert want in ids, want
    assert {d["title"] for d in res["documents"] if d["type"] == "mcp"} == {"k", "vm", "hm"}
    assert KEY not in texts(res)
    assert any(d["type"] == "command" and d["title"] == "p.prompt" for d in res["documents"])


# ------------------------------------------------------------- inline images

def test_extract_inline_images():
    raw = b"\x89PNG\r\n" + b"1" * 20
    good = {"type": "user", "message": {"role": "user", "content": [
        {"type": "text", "text": "look"},
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(raw).decode()}}]}}
    nested = {"type": "user", "message": {"content": [{"type": "tool_result", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(b"jpg").decode()}}]}]}}
    bad = [
        {"message": {"content": "just text"}},
        {"message": {"content": [{"type": "image", "source": {"type": "url", "url": "http://x"}}]}},
        {"message": {"content": [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "!!notb64"}}]}},
        {"message": {"content": [{"type": "image", "source": {"type": "base64", "media_type": "application/pdf", "data": "QQ=="}}]}},
        {"type": "response_item", "payload": {"type": "input_image", "image_url": "data:image/png;base64,AAAA"}},
        "not json", 5, None,
    ]
    out = rs.extract_inline_images([bad[0], good, bad[1], nested] + bad[2:])
    assert out == [(raw, "image/png", 1), (b"jpg", "image/jpeg", 3)]
    assert rs.extract_inline_images(bad) == []
    assert rs.extract_inline_images(None) == []


# ------------------------------------------------------------ review fixes

def test_strip_args_flag_equals_values():
    tail = "Zk93jd8sk29" + "dKSLw0pQmz7"
    sig = "Abcdef123xyz"
    opaque = "a1B2c3D4" * 5
    out = rs._strip_args(["-y", "mcp-remote", "--url=https://mcp.example.com/api/mcp/s/" + tail + "/sse",
                          "--endpoint=https://h.example/v1?sig=" + sig, "--name=" + opaque, "--port=8080",
                          "--path=/opt/some/long/dir/name/that/is/long/enough/abc"])
    blob = " ".join(out)
    for bad in (tail, sig, opaque):
        assert bad not in blob
    assert "--url=https://mcp.example.com" in out and "--endpoint=https://h.example" in out
    assert "--port=8080" in out and "--path=/opt/some/long/dir/name/that/is/long/enough/abc" in out
    text = rs.render_mcp("r", "claude", "user", {"command": "npx", "args": ["--hdr=" + BEARER]})
    assert BEARER not in text and "tok" + "en1234567890abcdef" not in text


def test_claude_slug_underscore_and_space(tree, tmp_path):
    home = tmp_path / "home"
    proj = tmp_path / "work" / "education_video app"
    proj.mkdir(parents=True)
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(os.path.realpath(proj)))
    assert "_" not in slug and " " not in slug
    w(home / ".claude" / "projects" / slug / "memory" / "MEMORY.md", "mem")
    res = rs.discover(str(proj), [], home=home, env={}, images=False)
    assert any(d["doc_id"].startswith("markdown:claude:user:.claude/projects/") for d in res["documents"])
    assert rs._claude_slug("/Users/dev/code/education_video") == "-Users-dev-code-education-video"


def test_same_named_user_skills_stay_distinct(tree):
    home, _ = tree
    w(home / ".claude" / "skills" / "x" / "SKILL.md", "one")
    w(home / ".claude" / "plugins" / "cache" / "mk" / "pl" / "1.0" / "skills" / "x" / "SKILL.md", "two")
    res = run(tree, [{"id": "s", "agent": "claude", "skills_used": [{"name": "x"}]}])
    docs = [d for d in res["documents"] if d["type"] == "skill" and d["title"] == "x"]
    assert len(docs) == 2 and len({d["doc_id"] for d in docs}) == 2


def test_user_scope_gating_is_per_agent(tree):
    home, _ = tree
    w(home / ".claude" / "skills" / "deploy" / "SKILL.md", "c")
    w(home / ".codex" / "skills" / "deploy" / "SKILL.md", "x")
    w(home / ".claude.json", json.dumps({"mcpServers": {"gh": {"command": "a"}}}))
    w(home / ".codex" / "config.toml", '[mcp_servers.gh]\ncommand = "a"\n')
    res = run(tree, [{"id": "s", "agent": "claude", "skills_used": [{"name": "deploy"}], "mcp_tools": ["mcp__gh__list"]}])
    ids = by_id(res)
    assert "skill:claude:user:.claude/skills/deploy/SKILL.md" in ids
    assert not any(i.startswith("skill:codex:") for i in ids)
    assert any(i.startswith("mcp:claude:") for i in ids)
    assert not any(i.startswith("mcp:codex:") for i in ids)
    # sessions without an agent field cannot be attributed, so they count for every agent
    res2 = run(tree, [{"id": "s", "skills_used": [{"name": "deploy"}]}])
    assert any(i.startswith("skill:codex:") for i in by_id(res2))
