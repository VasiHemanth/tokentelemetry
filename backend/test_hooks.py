"""Pre-push hook tests.

Focus: the hooks must judge the branch the push actually comes from. Both
resolved the repo from their own process cwd (the session's project root),
so any push out of a git worktree was evaluated against an unrelated branch.
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parents[1] / ".claude" / "hooks"
_ENFORCE = _HOOKS / "enforce-update-json.py"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hook = _load("enforce_update_json", _ENFORCE)


# --- resolve_push_cwd ---------------------------------------------------------

def test_plain_push_uses_payload_cwd():
    assert hook.resolve_push_cwd("git push", "/repo/wt") == "/repo/wt"


def test_cd_prefix_wins_over_payload_cwd():
    assert hook.resolve_push_cwd("cd /repo/wt && git push", "/repo") == "/repo/wt"


def test_relative_cd_composes_against_payload_cwd():
    assert hook.resolve_push_cwd("cd sub && git push", "/repo") == "/repo/sub"


def test_chained_relative_cds_compose():
    assert hook.resolve_push_cwd("cd a && cd b && git push", "/repo") == "/repo/a/b"


def test_git_dash_c_beats_cd():
    assert hook.resolve_push_cwd("cd /elsewhere && git -C /repo/wt push", "/repo") == "/repo/wt"


def test_git_dash_c_relative_resolves_against_current():
    assert hook.resolve_push_cwd("cd /repo && git -C wt push", "/other") == "/repo/wt"


def test_cd_after_the_push_is_ignored():
    assert hook.resolve_push_cwd("git push && cd /elsewhere", "/repo") == "/repo"


def test_unknown_cd_forms_fall_back():
    # `cd -` and `cd ~` are not resolvable to a concrete path here.
    assert hook.resolve_push_cwd("cd - && git push", "/repo") == "/repo"
    assert hook.resolve_push_cwd("cd ~/x && git push", "/repo") == "/repo"


def test_no_payload_cwd_returns_none():
    assert hook.resolve_push_cwd("git push", None) is None


def test_push_detection_unchanged():
    assert hook._command_contains_push("git push")
    assert hook._command_contains_push("cd /x && git push -u origin b")
    assert hook._command_contains_push("gh pr create --fill")
    assert not hook._command_contains_push('echo "git push"')
    assert not hook._command_contains_push("git status")


# --- end to end: run the hook the way Claude Code runs it ---------------------

def _git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


def _run_hook(command, payload_cwd, hook_cwd):
    """Invoke the hook as a subprocess with a PreToolUse payload on stdin."""
    payload = {"hook_event_name": "PreToolUse", "cwd": payload_cwd,
               "tool_name": "Bash", "tool_input": {"command": command}}
    p = subprocess.run([sys.executable, str(_ENFORCE)], input=json.dumps(payload),
                       cwd=hook_cwd, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr          # hook contract: always exit 0
    if not p.stdout.strip():
        return "allow"
    decision = json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"]
    return decision


@pytest.fixture
def repo(tmp_path):
    """A repo whose `main` has an origin, plus a `feat:` branch missing
    UPDATE.json — the shape that makes the hook deny."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], check=True)
    root = tmp_path / "work"
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    env = [("user.email", "t@example.com"), ("user.name", "t"), ("commit.gpgsign", "false")]
    for k, v in env:
        _git("config", k, v, cwd=root)
    (root / "UPDATE.json").write_text('{"releases": []}\n')
    (root / "app.py").write_text("x = 1\n")
    _git("add", "-A", cwd=root)
    _git("commit", "-qm", "chore: base", cwd=root)
    _git("remote", "add", "origin", str(origin), cwd=root)
    _git("push", "-q", "origin", "main", cwd=root)

    # Project root sits on a feat: branch with no UPDATE.json change -> deny.
    _git("checkout", "-qb", "feat/noisy", cwd=root)
    (root / "app.py").write_text("x = 2\n")
    _git("commit", "-qam", "feat: something user facing", cwd=root)
    return root


def test_denies_feat_branch_without_update_json(repo):
    assert _run_hook("git push", str(repo), str(repo)) == "deny"


def test_allows_when_update_json_is_touched(repo, tmp_path):
    (repo / "UPDATE.json").write_text('{"releases": [{"tag": "2026-08-22"}]}\n')
    _git("commit", "-qam", "feat: with release note", cwd=repo)
    assert _run_hook("git push", str(repo), str(repo)) == "allow"


def test_worktree_push_is_judged_on_its_own_branch(repo, tmp_path):
    """The regression. A fix-only worktree must not inherit the project
    root's feat: branch verdict."""
    wt = tmp_path / "wt"
    _git("worktree", "add", "-q", "-b", "fix/only", str(wt), "main", cwd=repo)
    (wt / "app.py").write_text("x = 3\n")
    _git("commit", "-qam", "fix: a fix only branch", cwd=wt)

    # Hook process cwd is the project root (on the denying feat: branch),
    # exactly as Claude Code invokes it.
    assert _run_hook(f"cd {wt} && git push", str(repo), str(repo)) == "allow"
    assert _run_hook(f"git -C {wt} push", str(repo), str(repo)) == "allow"
    # And the payload cwd route, i.e. after EnterWorktree.
    assert _run_hook("git push", str(wt), str(repo)) == "allow"


def test_worktree_feat_branch_still_denied(repo, tmp_path):
    """The fix must not let a real feat: worktree through."""
    wt = tmp_path / "wt2"
    _git("worktree", "add", "-q", "-b", "feat/real", str(wt), "main", cwd=repo)
    (wt / "app.py").write_text("x = 4\n")
    _git("commit", "-qam", "feat: shipped something", cwd=wt)
    assert _run_hook(f"cd {wt} && git push", str(repo), str(repo)) == "deny"


def test_main_branch_is_always_allowed(repo, tmp_path):
    wt = tmp_path / "wt3"
    _git("worktree", "add", "-q", str(wt), "main", cwd=repo)
    assert _run_hook(f"cd {wt} && git push", str(repo), str(repo)) == "allow"
