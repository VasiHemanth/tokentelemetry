"""The pre-push hooks must judge the branch actually being pushed.

Both hooks resolved the repository from their OWN cwd, which is the session's
project directory. For a push issued from a git worktree (`cd <worktree> &&
git push`) that is a different checkout on a different branch — so a clean
`fix:` branch was denied because the session's directory happened to sit on an
unrelated branch carrying a `feat:` commit, and the reviewer hook would have
reviewed that unrelated diff.
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "enforce-update-json.py"


def _load():
    spec = importlib.util.spec_from_file_location("enforce_update_json", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


H = _load()


def _dirs():
    """A base dir with two subdirectories, standing in for repo + worktree."""
    tmp = tempfile.mkdtemp()
    base = os.path.join(tmp, "repo")
    wt = os.path.join(tmp, "worktree")
    os.makedirs(base)
    os.makedirs(wt)
    return base, wt


def _git(*args: str, cwd: Path) -> str:
    """Run git in an isolated test repository."""
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _run_hook(command: str, payload_cwd: Path, hook_cwd: Path) -> str:
    """Invoke the guard exactly as Claude Code's PreToolUse hook does."""
    payload = {
        "hook_event_name": "PreToolUse",
        "cwd": str(payload_cwd),
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        cwd=hook_cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    if not result.stdout.strip():
        return "allow"
    return json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"]


def _make_repo(tmp_path: Path) -> Path:
    """Create the branch shape that used to mislead the guard hook."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], check=True)
    root = tmp_path / "work"
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    for key, value in (
        ("user.email", "t@example.com"),
        ("user.name", "t"),
        ("commit.gpgsign", "false"),
    ):
        _git("config", key, value, cwd=root)
    (root / "UPDATE.json").write_text('{"releases": []}\n')
    (root / "app.py").write_text("x = 1\n")
    _git("add", "-A", cwd=root)
    _git("commit", "-qm", "chore: base", cwd=root)
    _git("remote", "add", "origin", str(origin), cwd=root)
    _git("push", "-q", "origin", "main", cwd=root)

    # The session directory is deliberately on a feature branch that should
    # be denied; worktree tests prove its state is not accidentally reused.
    _git("checkout", "-qb", "feat/noisy", cwd=root)
    (root / "app.py").write_text("x = 2\n")
    _git("commit", "-qam", "feat: something user facing", cwd=root)
    return root


def test_cd_prefix_is_followed():
    base, wt = _dirs()
    assert H.resolve_push_cwd(f"cd {wt} && git push -u origin br", base) == wt


def test_plain_push_stays_in_base():
    base, _ = _dirs()
    assert H.resolve_push_cwd("git push -u origin br", base) == base


def test_git_dash_c_is_honoured():
    base, wt = _dirs()
    assert H.resolve_push_cwd(f"git -C {wt} push origin br", base) == wt
    assert H.resolve_push_cwd(f"git -C{wt} push origin br", base) == wt


def test_relative_cd_resolves_against_base():
    base, wt = _dirs()
    rel = os.path.relpath(wt, base)
    assert H.resolve_push_cwd(f"cd {rel} && git push", base) == wt


def test_last_cd_before_the_push_wins():
    base, wt = _dirs()
    other = os.path.join(os.path.dirname(base), "other")
    os.makedirs(other, exist_ok=True)
    assert H.resolve_push_cwd(f"cd {other} && cd {wt} && git push", base) == wt


def test_cd_after_the_push_is_ignored():
    """Only directories entered BEFORE the push affect it."""
    base, wt = _dirs()
    assert H.resolve_push_cwd(f"git push && cd {wt}", base) == base


def test_nonexistent_directory_falls_back_to_base():
    """A bad path must not silently skip the gate."""
    base, _ = _dirs()
    assert H.resolve_push_cwd("cd /no/such/dir/anywhere && git push", base) == base


def test_cd_dash_is_ignored():
    base, wt = _dirs()
    assert H.resolve_push_cwd(f"cd {wt} && cd - && git push", base) == wt


def test_unparseable_command_falls_back_to_base():
    base, _ = _dirs()
    assert H.resolve_push_cwd('cd "unterminated && git push', base) == base


def test_push_detection_unchanged():
    assert H._command_contains_push("git push")
    assert H._command_contains_push("cd /x && git push -u origin branch")
    assert H._command_contains_push("gh pr create --fill")
    assert not H._command_contains_push('echo "git push"')
    assert not H._command_contains_push("git status")


def test_denies_feature_branch_without_update_json():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(Path(tmp))
        assert _run_hook("git push", repo, repo) == "deny"


def test_allows_feature_branch_when_update_json_changed():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(Path(tmp))
        (repo / "UPDATE.json").write_text('{"releases": [{"tag": "2026-08-22"}]}\n')
        _git("commit", "-am", "feat: with release note", cwd=repo)
        assert _run_hook("git push", repo, repo) == "allow"


def test_worktree_fix_branch_is_judged_on_its_own_branch():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(Path(tmp))
        worktree = Path(tmp) / "fix-worktree"
        _git("worktree", "add", "-q", "-b", "fix/only", str(worktree), "main", cwd=repo)
        (worktree / "app.py").write_text("x = 3\n")
        _git("commit", "-am", "fix: a fix-only branch", cwd=worktree)

        assert _run_hook(f"cd {worktree} && git push", repo, repo) == "allow"
        assert _run_hook(f"git -C {worktree} push", repo, repo) == "allow"
        assert _run_hook("git push", worktree, repo) == "allow"


def test_worktree_feature_branch_without_update_json_is_denied():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(Path(tmp))
        worktree = Path(tmp) / "feature-worktree"
        _git("worktree", "add", "-q", "-b", "feat/real", str(worktree), "main", cwd=repo)
        (worktree / "app.py").write_text("x = 4\n")
        _git("commit", "-am", "feat: shipped something", cwd=worktree)

        assert _run_hook(f"cd {worktree} && git push", repo, repo) == "deny"


def test_main_worktree_is_always_allowed():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(Path(tmp))
        worktree = Path(tmp) / "main-worktree"
        _git("worktree", "add", "-q", str(worktree), "main", cwd=repo)

        assert _run_hook(f"cd {worktree} && git push", repo, repo) == "allow"


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            fn()
    print("All tests passed!")
