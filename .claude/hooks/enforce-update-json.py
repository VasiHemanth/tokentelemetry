#!/usr/bin/env python3
"""PreToolUse hook: block `git push` / `gh pr create` from a non-main branch
when UPDATE.json hasn't been touched in the branch's diff vs origin/main.

Why: every push that lands in main should refresh the dashboard's "what's
new" banner. Without this guard, banners go stale and users on prior
versions see "update available" with no real highlights.

Reads the tool invocation as JSON on stdin (Claude Code's hook contract).
Exits 0 always — block decisions are communicated via the JSON payload to
stdout, not via exit code.

Uses real command-tokenisation (shlex) instead of substring grep so it
doesn't trip on commands like `echo "git push"` or `grep "git push" file`.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from typing import List, Optional


BLOCK_PAYLOAD = {
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": (
            "UPDATE.json wasn't modified on this branch — the in-app update "
            "banner won't have fresh highlights. Add or update an entry in "
            "UPDATE.json (see .claude/CLAUDE.md for the schema) before pushing. "
            "To bypass (e.g. docs-only change), re-run with `--no-hooks`."
        ),
    }
}


def _allow() -> None:
    """Allow the tool call. Hook contract: silent + exit 0."""
    sys.exit(0)


def _deny() -> None:
    """Deny the tool call. Hook contract: structured JSON on stdout + exit 0."""
    print(json.dumps(BLOCK_PAYLOAD))
    sys.exit(0)


def _is_push_subcommand(tokens: List[str]) -> bool:
    """Given a single command's tokens, return True iff it's `git push ...`
    or `gh pr create ...`. Handles common prefixes: env var assignments, `env`,
    `cd <dir> && ...`, and git's global options (`-C`, `--git-dir`)."""
    i = 0
    # Skip leading env assignments (FOO=bar BAR=baz cmd …)
    while i < len(tokens) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[i]):
        i += 1
    if i >= len(tokens):
        return False

    head = tokens[i]

    if head == "git":
        # Walk past git's global options to find the subcommand
        j = i + 1
        while j < len(tokens):
            tok = tokens[j]
            if tok in ("-C", "--git-dir", "--work-tree", "--namespace"):
                j += 2  # takes an argument
            elif tok.startswith("--git-dir=") or tok.startswith("--work-tree=") or tok.startswith("--namespace="):
                j += 1
            elif tok.startswith("-"):
                j += 1  # other flags
            else:
                break
        return j < len(tokens) and tokens[j] == "push"

    if head == "gh":
        # `gh pr create [...]` (no globals worth handling here)
        return len(tokens) >= i + 3 and tokens[i + 1] == "pr" and tokens[i + 2] == "create"

    return False


def _command_contains_push(command_str: str) -> bool:
    """Split on shell chain operators (`&&`, `||`, `;`, `|`) and check if any
    resulting command-fragment is a push/PR-create. Anything inside literal
    strings, comments, or grep patterns is correctly ignored by shlex."""
    # First, get a sane tokenisation; if shlex fails (bad quoting in the
    # caller's command), be permissive and don't block.
    try:
        shlex.split(command_str)
    except ValueError:
        return False

    # Walk through chain operators by splitting on them at the source-text
    # level. shlex strips quoting before we can see operator context, so we
    # need to find the operator positions ourselves while respecting quotes.
    fragments = _split_on_chain_operators(command_str)
    for frag in fragments:
        frag = frag.strip()
        if not frag:
            continue
        try:
            tokens = shlex.split(frag)
        except ValueError:
            continue
        if _is_push_subcommand(tokens):
            return True
    return False


def _split_on_chain_operators(s: str) -> List[str]:
    """Split a shell command line on `;`, `&&`, `||`, `|`, respecting quotes.
    Returns the list of sub-commands."""
    fragments: List[str] = []
    buf: List[str] = []
    i = 0
    n = len(s)
    quote: Optional[str] = None
    while i < n:
        c = s[i]
        if quote:
            buf.append(c)
            if c == quote:
                quote = None
            elif c == "\\" and i + 1 < n:
                # consume escaped char inside double-quote / etc.
                buf.append(s[i + 1])
                i += 1
            i += 1
            continue
        if c in ("'", '"'):
            quote = c
            buf.append(c)
            i += 1
            continue
        # Operators outside quotes
        if c == ";":
            fragments.append("".join(buf))
            buf = []
            i += 1
            continue
        if c == "|" and i + 1 < n and s[i + 1] == "|":
            fragments.append("".join(buf))
            buf = []
            i += 2
            continue
        if c == "&" and i + 1 < n and s[i + 1] == "&":
            fragments.append("".join(buf))
            buf = []
            i += 2
            continue
        if c == "|":  # plain pipe
            fragments.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    if buf:
        fragments.append("".join(buf))
    return fragments


def _git(*args: str, cwd: Optional[str] = None, timeout: int = 10) -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["git", *args],
            stderr=subprocess.DEVNULL,
            cwd=cwd,
            timeout=timeout,
        )
        return out.decode("utf-8", errors="replace").strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        _allow()
        return

    command = (payload.get("tool_input") or {}).get("command") or ""
    if not command:
        _allow()
        return

    if not _command_contains_push(command):
        _allow()
        return

    # It IS a push / PR-create. Now check the branch state.
    repo_root = _git("rev-parse", "--show-toplevel")
    if not repo_root:
        _allow()
        return

    branch = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=repo_root)
    if branch in (None, "main", "master", "HEAD"):
        _allow()
        return

    # Best-effort refresh of origin/main; tolerate offline / unauth.
    subprocess.run(
        ["git", "fetch", "origin", "main", "--quiet"],
        cwd=repo_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=15,
    )

    # Pick a base ref to diff against.
    base_ref: Optional[str] = None
    for candidate in ("origin/main", "main"):
        if subprocess.run(
            ["git", "rev-parse", "--verify", candidate],
            cwd=repo_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode == 0:
            base_ref = candidate
            break
    if not base_ref:
        # No anchor — don't block; user knows their setup.
        _allow()
        return

    # Only enforce when this branch contains at least one `feat:` commit
    # vs main. Pushes that are purely fix:/chore:/docs:/refactor:/etc.
    # don't need a UPDATE.json entry — they aren't user-facing features.
    # Conventional Commits prefix scheme; matches with or without scope and
    # the `!` breaking-change marker.
    log = _git("log", f"{base_ref}..HEAD", "--pretty=format:%s", cwd=repo_root) or ""
    feat_re = re.compile(r"^(feat|feature)(\([^)]+\))?!?:", re.IGNORECASE | re.MULTILINE)
    if not feat_re.search(log):
        _allow()
        return

    changed = _git("diff", "--name-only", f"{base_ref}...HEAD", cwd=repo_root) or ""
    if "UPDATE.json" in changed.splitlines():
        _allow()
        return

    _deny()


if __name__ == "__main__":
    main()
