"""Tests for _collect_memory(): every coding agent's memory / instruction files
for a project, labelled with the agent that reads them."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import main  # noqa: E402


def _w(p: Path, text: str = "x") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def _home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "home"
    monkeypatch.setattr(main, "HOME", home)
    monkeypatch.setattr(main, "CLAUDE_DIR", home / ".claude")
    monkeypatch.setattr(main, "CODEX_DIR", home / ".codex")
    monkeypatch.setattr(main, "GEMINI_DIR", home / ".gemini")
    monkeypatch.setattr(main, "QWEN_DIR", home / ".qwen")
    monkeypatch.setattr(main, "HERMES_DIR", home / ".hermes")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    return home


def test_claude_project_key_matches_claude_code_encoding():
    assert main._claude_project_key(Path("/Users/dev/code/app")) == "-Users-dev-code-app"
    assert (main._claude_project_key(Path("/Users/dev/app/.claude/worktrees/x"))
            == "-Users-dev-app--claude-worktrees-x")


def test_user_scope_memory_per_agent(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _w(home / ".claude" / "CLAUDE.md")
    _w(home / ".gemini" / "GEMINI.md")
    _w(home / ".hermes" / "memories" / "MEMORY.md")
    _w(home / ".hermes" / "SOUL.md")
    _w(home / ".config" / "opencode" / "AGENTS.md")
    _w(home / ".codex" / "AGENTS.md")
    rows = main._collect_memory(None)
    got = {(r["agent"], r["name"]) for r in rows}
    assert got == {("claude", "CLAUDE.md"), ("gemini", "GEMINI.md"),
                   ("hermes", "MEMORY.md"), ("hermes", "SOUL.md"),
                   ("opencode", "AGENTS.md (OpenCode global)"), ("codex", "AGENTS.md")}
    assert all(r["scope"] == "user" for r in rows)
    # ~/.codex/AGENTS.md is Codex's own global file, not the shared convention.
    assert all("agents" not in r for r in rows)


def test_project_memory_from_every_agent(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    proj = tmp_path / "work" / "app"
    _w(proj / "CLAUDE.md")
    _w(proj / ".claude" / "CLAUDE.md")
    _w(proj / "CLAUDE.local.md")
    _w(proj / "AGENTS.md")
    _w(proj / "GEMINI.md")
    _w(proj / "frontend" / "CLAUDE.md")
    _w(proj / "frontend" / "AGENTS.md")
    _w(proj / ".github" / "copilot-instructions.md")
    _w(proj / ".cursor" / "rules" / "style.mdc")
    # Worktrees and dependencies are copies, never the project's own memory.
    _w(proj / ".claude" / "worktrees" / "feat" / "CLAUDE.md")
    _w(proj / "node_modules" / "pkg" / "AGENTS.md")
    # Claude Code auto memory lives under ~/.claude/projects/<key>/memory.
    auto = home / ".claude" / "projects" / main._claude_project_key(proj) / "memory"
    _w(auto / "MEMORY.md", "- [a](a.md)")
    _w(auto / "a.md")
    _w(auto / "b.md")

    rows = [r for r in main._collect_memory(proj) if r["scope"] == "project"]
    by_name = {r["name"]: r for r in rows}
    assert set(by_name) == {
        "MEMORY.md (auto memory)", ".claude/CLAUDE.md", "CLAUDE.local.md",
        ".github/copilot-instructions.md", ".cursor/rules/style.mdc",
        "CLAUDE.md", "AGENTS.md", "GEMINI.md", "frontend/CLAUDE.md", "frontend/AGENTS.md",
    }
    assert by_name["MEMORY.md (auto memory)"]["agent"] == "claude"
    assert by_name["MEMORY.md (auto memory)"]["note_count"] == 2
    assert by_name["GEMINI.md"]["agent"] == "gemini"
    assert by_name[".cursor/rules/style.mdc"]["agent"] == "cursor"
    assert by_name[".github/copilot-instructions.md"]["agent"] == "copilot"
    # AGENTS.md is shared: every reader is listed, `agent` stays codex.
    assert by_name["AGENTS.md"]["agent"] == "codex"
    assert by_name["AGENTS.md"]["agents"] == ["codex", "cursor", "opencode", "copilot"]
    assert "agents" not in by_name["CLAUDE.md"]


def test_nested_walk_is_depth_limited_and_capped(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    proj = tmp_path / "app"
    _w(proj / "a" / "b" / "CLAUDE.md")            # depth 2: found
    _w(proj / "a" / "b" / "c" / "d" / "CLAUDE.md")  # depth 4: past the limit
    names = {r["name"] for r in main._collect_memory(proj)}
    assert "a/b/CLAUDE.md" in names
    assert "a/b/c/d/CLAUDE.md" not in names

    for i in range(main._MEMORY_MAX_FILES + 10):
        _w(proj / f"pkg{i:03d}" / "AGENTS.md")
    assert len(main._collect_memory(proj)) == main._MEMORY_MAX_FILES
