"""
git_context.py — Git Integration

Attaches git context to sessions by running lightweight subprocess calls.
Finds the commit that was HEAD at (or before) the session's timestamp.

Cached per (normalized_path, date_string) with a 5-minute TTL so repeated
calls for sessions in the same project+day hit the cache instead of git.

Returned per session (attached as session["git_info"]):
  is_git          True if the project is inside a git work-tree
  branch          current branch name (or HEAD-detached SHA)
  commit_sha      short SHA of the commit closest to session time
  commit_sha_full full 40-char SHA
  commit_msg      first line of the commit message
  commit_author   author name
  commit_time     ISO timestamp of the commit
  files_changed   number of files touched in that commit
  lines_added     total insertions
  lines_deleted   total deletions

No external dependencies — pure stdlib (subprocess, pathlib, datetime).
"""

import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

# Resolve git binary once at import time so we don't depend on PATH being
# complete inside background-launched processes (common on Windows).
_GIT_EXE = shutil.which("git") or "git"

# Well-known Windows install locations as fallback
if _GIT_EXE == "git":
    for _candidate in [
        r"C:\Program Files\Git\cmd\git.exe",
        r"C:\Program Files (x86)\Git\cmd\git.exe",
    ]:
        if Path(_candidate).exists():
            _GIT_EXE = _candidate
            break

# ── Path normalisation ────────────────────────────────────────────────────────

def _normalise(path: str) -> str:
    """Convert POSIX-style git paths like /c:/foo to Windows C:\\foo."""
    if not path:
        return path
    # /c:/Users/... → C:\Users\...
    m = re.match(r'^/([a-zA-Z]):(/.*)', path)
    if m:
        drive = m.group(1).upper()
        rest = m.group(2).replace("/", "\\")
        return f"{drive}:{rest}"
    return path


# ── Subprocess helper ─────────────────────────────────────────────────────────

def _git(cwd: str, *args: str, timeout: int = 5) -> str:
    """Run a git command in cwd and return stdout. Returns '' on any error."""
    try:
        result = subprocess.run(
            [_GIT_EXE, "-C", cwd, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


# ── Cache ─────────────────────────────────────────────────────────────────────

_CACHE: dict[tuple, dict] = {}
_CACHE_TS: dict[tuple, float] = {}
_TTL = 300  # 5 minutes
_MAX_ENTRIES = 500


def _cache_key(path: str, date_str: str) -> tuple:
    return (path, date_str)


def _cache_get(key: tuple) -> Optional[dict]:
    if key not in _CACHE:
        return None
    if time.time() - _CACHE_TS[key] > _TTL:
        del _CACHE[key]
        del _CACHE_TS[key]
        return None
    return _CACHE[key]


def _cache_set(key: tuple, value: dict) -> None:
    if len(_CACHE) >= _MAX_ENTRIES:
        # evict oldest
        oldest = min(_CACHE_TS, key=lambda k: _CACHE_TS[k])
        del _CACHE[oldest]
        del _CACHE_TS[oldest]
    _CACHE[key] = value
    _CACHE_TS[key] = time.time()


# ── Not-a-git-repo sentinel ───────────────────────────────────────────────────

_NOT_GIT = {
    "is_git": False,
    "branch": None,
    "commit_sha": None,
    "commit_sha_full": None,
    "commit_msg": None,
    "commit_author": None,
    "commit_time": None,
    "files_changed": 0,
    "lines_added": 0,
    "lines_deleted": 0,
}


# ── Main entry point ──────────────────────────────────────────────────────────

def get_git_info(project: str, timestamp: Optional[str] = None) -> dict:
    """
    Return git context for a session.

    Parameters
    ----------
    project   : project directory path (may be POSIX-style /c:/...)
    timestamp : ISO 8601 timestamp of the session (used to find the right commit)

    Returns
    -------
    dict with keys described in module docstring.
    """
    path = _normalise(project or "")
    if not path or not Path(path).exists():
        return _NOT_GIT

    # Date portion of timestamp → cache granularity is one day per project
    # timestamp may be a datetime object or an ISO string
    if hasattr(timestamp, "isoformat"):
        timestamp = timestamp.isoformat()
    date_str = (timestamp or "")[:10] or "current"
    key = _cache_key(path, date_str)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    # Check if inside a git work-tree
    inside = _git(path, "rev-parse", "--is-inside-work-tree")
    if inside != "true":
        result = dict(_NOT_GIT)
        _cache_set(key, result)
        return result

    # Get branch
    branch = _git(path, "branch", "--show-current") or \
             _git(path, "rev-parse", "--short", "HEAD")

    # Find commit at or before the session timestamp
    if timestamp and len(timestamp) >= 19:
        # Normalize to git-acceptable format
        iso_ts = timestamp[:19].replace("T", " ")
        log_out = _git(
            path,
            "log",
            f"--before={iso_ts}",
            "-1",
            "--format=%H|%h|%s|%aI|%an",
        )
    else:
        log_out = ""

    # Fall back to current HEAD if no commit found before timestamp
    if not log_out:
        log_out = _git(path, "log", "-1", "--format=%H|%h|%s|%aI|%an")

    if not log_out:
        result = {**_NOT_GIT, "is_git": True, "branch": branch}
        _cache_set(key, result)
        return result

    parts = log_out.split("|", 4)
    full_sha   = parts[0] if len(parts) > 0 else ""
    short_sha  = parts[1] if len(parts) > 1 else full_sha[:7]
    msg        = parts[2] if len(parts) > 2 else ""
    commit_ts  = parts[3] if len(parts) > 3 else ""
    author     = parts[4] if len(parts) > 4 else ""

    # Diff stats for that commit: lines added / deleted / files changed
    # diff-tree --numstat -r outputs: sha\nadded\tdeleted\tfile\n...
    files_changed = 0
    lines_added = 0
    lines_deleted = 0

    if full_sha:
        numstat = _git(path, "diff-tree", "--numstat", "-r", full_sha)
        for line in numstat.splitlines():
            cols = line.split("\t")
            if len(cols) >= 2 and cols[0].lstrip("-").isdigit():
                try:
                    lines_added   += int(cols[0]) if cols[0] != "-" else 0
                    lines_deleted += int(cols[1]) if cols[1] != "-" else 0
                    files_changed += 1
                except ValueError:
                    pass

    result = {
        "is_git":          True,
        "branch":          branch or None,
        "commit_sha":      short_sha or None,
        "commit_sha_full": full_sha or None,
        "commit_msg":      msg or None,
        "commit_author":   author or None,
        "commit_time":     commit_ts or None,
        "files_changed":   files_changed,
        "lines_added":     lines_added,
        "lines_deleted":   lines_deleted,
    }
    _cache_set(key, result)
    return result


# ── Git summary across sessions ───────────────────────────────────────────────

def git_summary(sessions: list[dict]) -> dict:
    """
    Aggregate git context across all sessions, grouped by project.

    Returns
    -------
    {
      "projects": [
        {
          "project":      str,
          "branch":       str | null,
          "session_count": int,
          "total_files_changed": int,
          "total_lines_added":   int,
          "total_lines_deleted": int,
          "net_lines":           int,   # added - deleted
          "latest_commit_sha":   str | null,
          "latest_commit_msg":   str | null,
          "latest_commit_time":  str | null,
          "avg_files_per_session": float,
        }
      ],
      "total_lines_added":   int,
      "total_lines_deleted": int,
      "total_files_changed": int,
      "git_sessions":        int,     # sessions that are inside a git repo
      "non_git_sessions":    int,
    }
    """
    from collections import defaultdict

    buckets: dict[str, dict] = {}

    for s in sessions:
        gi = s.get("git_info")
        if not gi or not gi.get("is_git"):
            continue
        proj = s.get("project", "")
        if proj not in buckets:
            buckets[proj] = {
                "project":          proj,
                "branch":           gi.get("branch"),
                "sessions":         [],
                "files_changed":    0,
                "lines_added":      0,
                "lines_deleted":    0,
                "latest_commit_sha":  None,
                "latest_commit_msg":  None,
                "latest_commit_time": None,
            }
        b = buckets[proj]
        b["sessions"].append(s)
        b["files_changed"] += gi.get("files_changed", 0)
        b["lines_added"]   += gi.get("lines_added", 0)
        b["lines_deleted"] += gi.get("lines_deleted", 0)

        # Track latest commit
        ct = gi.get("commit_time") or ""
        if ct and (not b["latest_commit_time"] or ct > b["latest_commit_time"]):
            b["latest_commit_time"] = ct
            b["latest_commit_sha"]  = gi.get("commit_sha")
            b["latest_commit_msg"]  = gi.get("commit_msg")
        # Keep most recent branch
        if gi.get("branch"):
            b["branch"] = gi["branch"]

    projects = []
    total_added = total_deleted = total_files = 0
    git_sessions = 0

    for proj, b in sorted(buckets.items(), key=lambda x: -len(x[1]["sessions"])):
        n = len(b["sessions"])
        git_sessions += n
        total_added   += b["lines_added"]
        total_deleted += b["lines_deleted"]
        total_files   += b["files_changed"]
        projects.append({
            "project":              proj,
            "branch":               b["branch"],
            "session_count":        n,
            "total_files_changed":  b["files_changed"],
            "total_lines_added":    b["lines_added"],
            "total_lines_deleted":  b["lines_deleted"],
            "net_lines":            b["lines_added"] - b["lines_deleted"],
            "latest_commit_sha":    b["latest_commit_sha"],
            "latest_commit_msg":    b["latest_commit_msg"],
            "latest_commit_time":   b["latest_commit_time"],
            "avg_files_per_session": round(b["files_changed"] / n, 1) if n else 0,
        })

    non_git = len(sessions) - git_sessions

    return {
        "projects":            projects,
        "total_lines_added":   total_added,
        "total_lines_deleted": total_deleted,
        "total_files_changed": total_files,
        "git_sessions":        git_sessions,
        "non_git_sessions":    non_git,
    }
