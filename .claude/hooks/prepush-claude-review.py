#!/usr/bin/env python3
"""PreToolUse hook: run a local Claude review of `origin/main..HEAD` before a
`git push` / `gh pr create`, and block the push if the review flags a
high-severity regression.

Why this exists (issue #91): the remote-access feature shipped fast, without a
maintainer review pass, and merged vulnerable/unused dependencies plus a real
exposure question (the auth token never guarded the Next.js dev server). A
deterministic `npm audit` CI gate catches *known* CVEs, but not "this looks like
an auth bypass" / "this dep is unused" / "this widens the remote surface". That
judgement is what a reviewer provides — so this hook spends ~30s of local Claude
time on every push to a main-bound branch and surfaces the same kind of findings
*before* the code leaves the machine.

Design choices:
- **Fail OPEN.** If the `claude` CLI is missing, the diff is empty/huge, the
  review times out, or its output can't be parsed, the push is ALLOWED. A flaky
  reviewer must never become a hard blocker on legit work. Only an explicit
  `"verdict": "block"` denies.
- **Local only.** Uses the maintainer's own `claude` CLI — no CI secret, no
  per-PR cloud cost. Catches *your* pushes (which is exactly the gap #91 came
  from); contributor PRs are covered by the separate `security-audit.yml` gate.
- **Reuses** the push-detection + git helpers from `enforce-update-json.py`
  (imported, not duplicated) so both hooks agree on what "a push" is.
- Exits 0 always; block decisions travel via the JSON payload, matching the
  sibling hook's contract.

Bypass with `--no-hooks` for that session (e.g. an urgent hotfix).
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from typing import List, Optional


# --- Reuse the sibling hook's battle-tested push detection / git helpers ------
# Importing is side-effect free: enforce-update-json.py only defines functions
# under an `if __name__ == "__main__"` guard.
_HERE = os.path.dirname(os.path.abspath(__file__))


def _load_sibling():
    path = os.path.join(_HERE, "enforce-update-json.py")
    spec = importlib.util.spec_from_file_location("enforce_update_json", path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:
        return None
    return mod


_SIB = _load_sibling()


# File extensions whose changes are worth a review. Pure docs/markdown/asset
# churn is skipped so the hook stays quiet on non-code pushes.
_CODE_SUFFIXES = (
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".json", ".sh", ".bash", ".zsh", ".yml", ".yaml", ".toml",
    ".rs",
)
# Manifests are always interesting (this is how #91's vuln deps slipped in).
_ALWAYS_REVIEW = ("package.json", "requirements.txt", "pyproject.toml")

_MAX_DIFF_CHARS = 60_000   # cap prompt size → bounded latency/cost
_REVIEW_TIMEOUT = 150      # seconds; on timeout we fail open


def _allow() -> None:
    sys.exit(0)


def _deny(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def _git(*args: str, cwd: Optional[str] = None, timeout: int = 10) -> Optional[str]:
    if _SIB is not None:
        return _SIB._git(*args, cwd=cwd, timeout=timeout)
    try:
        out = subprocess.check_output(
            ["git", *args], stderr=subprocess.DEVNULL, cwd=cwd, timeout=timeout
        )
        return out.decode("utf-8", errors="replace").strip()
    except Exception:
        return None


def _is_push(command: str) -> bool:
    if _SIB is not None:
        return _SIB._command_contains_push(command)
    # Conservative fallback if the sibling failed to load.
    return "push" in command.split()


REVIEW_PROMPT = """\
You are a strict pre-push reviewer for the TokenTelemetry repo. A unified git \
diff of `origin/main..HEAD` is below. Review ONLY this diff. Look specifically \
for regressions that a fast-moving maintainer would miss:

1. Dependency hygiene: newly added npm/python deps that are unused, unnecessary, \
   or carry known vulnerabilities (e.g. a left-over runtime dep, an unpinned or \
   downgraded version). Issue #91 was exactly this.
2. Remote-exposure / auth regressions: anything that widens what is reachable \
   when the app runs with `--host`/remote access, weakens `RemoteAuthMiddleware` \
   or the loopback exemption, or exposes the Next.js dev server / an endpoint \
   without the token gate.
3. Secrets or credentials committed in the diff.
4. Obvious security bugs: command/shell injection, path traversal, SSRF, unsafe \
   deserialization.

Be conservative about blocking — only block on a HIGH-confidence, genuinely \
risky finding, not style or nits. Respond with ONE line of strict minified JSON \
and nothing else:
{"verdict":"pass"|"block","summary":"<=200 chars","findings":["<short finding>", ...]}

DIFF:
"""


def _run_review(diff: str) -> Optional[dict]:
    """Invoke the local claude CLI in headless print mode. Returns the parsed
    verdict dict, or None on any failure (→ caller fails open)."""
    claude = shutil.which("claude")
    if not claude:
        return None
    prompt = REVIEW_PROMPT + diff
    try:
        proc = subprocess.run(
            [claude, "-p", prompt],
            capture_output=True, text=True, timeout=_REVIEW_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    out = (proc.stdout or "").strip()
    # The model may wrap the JSON in prose/fences; extract the first {...} blob.
    m = re.search(r"\{.*\}", out, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or "verdict" not in data:
        return None
    return data


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        _allow()

    command = (payload.get("tool_input") or {}).get("command") or ""
    if not command or not _is_push(command):
        _allow()

    # Avoid recursion: never review from inside a nested headless review.
    if os.environ.get("TT_PREPUSH_REVIEW_RUNNING"):
        _allow()

    repo_root = _git("rev-parse", "--show-toplevel")
    if not repo_root:
        _allow()

    branch = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=repo_root)
    if branch in (None, "main", "master", "HEAD"):
        _allow()

    subprocess.run(
        ["git", "fetch", "origin", "main", "--quiet"],
        cwd=repo_root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=15,
    )

    base_ref = None
    for candidate in ("origin/main", "main"):
        if subprocess.run(
            ["git", "rev-parse", "--verify", candidate],
            cwd=repo_root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode == 0:
            base_ref = candidate
            break
    if not base_ref:
        _allow()

    changed = (_git("diff", "--name-only", f"{base_ref}...HEAD", cwd=repo_root) or "").splitlines()
    relevant = [
        f for f in changed
        if f.endswith(_CODE_SUFFIXES) or os.path.basename(f) in _ALWAYS_REVIEW
    ]
    if not relevant:
        _allow()  # docs/asset-only push — nothing for the reviewer to weigh in on

    diff = _git("diff", f"{base_ref}...HEAD", "--", *relevant, cwd=repo_root, timeout=20) or ""
    if not diff.strip():
        _allow()
    truncated = len(diff) > _MAX_DIFF_CHARS
    if truncated:
        diff = diff[:_MAX_DIFF_CHARS] + "\n…[diff truncated for review]…\n"

    os.environ["TT_PREPUSH_REVIEW_RUNNING"] = "1"
    verdict = _run_review(diff)
    if not verdict:
        _allow()  # reviewer unavailable / unparseable → fail open

    if str(verdict.get("verdict", "")).lower() == "block":
        findings = verdict.get("findings") or []
        summary = str(verdict.get("summary") or "review flagged a high-risk change")
        bullets = "\n".join(f"  • {str(f)[:200]}" for f in findings[:6]) or "  • (no detail)"
        _deny(
            "Pre-push Claude review flagged this change:\n"
            f"{summary}\n{bullets}\n\n"
            "Address the findings, or re-run with `--no-hooks` to bypass "
            "(e.g. urgent hotfix / false positive)."
        )

    _allow()


if __name__ == "__main__":
    main()
