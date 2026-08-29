"""The pre-push hooks must judge the branch actually being pushed.

Both hooks resolved the repository from their OWN cwd, which is the session's
project directory. For a push issued from a git worktree (`cd <worktree> &&
git push`) that is a different checkout on a different branch — so a clean
`fix:` branch was denied because the session's directory happened to sit on an
unrelated branch carrying a `feat:` commit, and the reviewer hook would have
reviewed that unrelated diff.
"""

import importlib.util
import os
import subprocess
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


def test_end_to_end_worktree_push_is_allowed(tmp_path):
    """The exact case that was denied: a fix-only worktree branch, pushed while
    the session's directory sits on a feat: branch with no UPDATE.json."""
    def git(*a, cwd):
        subprocess.run(["git", *a], cwd=cwd, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    repo = tmp_path / "repo"
    repo.mkdir()
    git("init", "-q", "-b", "main", cwd=repo)
    git("config", "user.email", "t@e.st", cwd=repo)
    git("config", "user.name", "t", cwd=repo)
    (repo / "UPDATE.json").write_text("{}")
    git("add", "-A", cwd=repo)
    git("commit", "-qm", "chore: init", cwd=repo)
    # Stand in for origin/main.
    git("branch", "origin/main", cwd=repo)

    # Session directory sits on a feat: branch that never touched UPDATE.json.
    git("checkout", "-q", "-b", "feat/session", cwd=repo)
    (repo / "other.txt").write_text("x")
    git("add", "-A", cwd=repo)
    git("commit", "-qm", "feat: something user facing", cwd=repo)

    # The worktree we actually push: fix: only.
    wt = tmp_path / "wt"
    git("worktree", "add", "-q", "-b", "fix/thing", str(wt), "origin/main", cwd=repo)
    (wt / "f.txt").write_text("y")
    git("add", "-A", cwd=wt)
    git("commit", "-qm", "fix: a bug", cwd=wt)

    # Resolution picks the worktree...
    assert H.resolve_push_cwd(f"cd {wt} && git push", str(repo)) == str(wt)
    # ...and that branch carries no feat:, so the hook's own rule allows it.
    log = H._git("log", "origin/main..HEAD", "--pretty=format:%s", cwd=str(wt)) or ""
    assert "feat:" not in log
    # The session branch, judged by mistake before, does carry one.
    log_session = H._git("log", "origin/main..HEAD", "--pretty=format:%s", cwd=str(repo)) or ""
    assert "feat:" in log_session


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn) and "tmp_path" not in fn.__code__.co_varnames:
            fn()
    print("All tests passed!")
