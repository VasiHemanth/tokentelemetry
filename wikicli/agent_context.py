#!/usr/bin/env python3
"""agent_context.py: install/refresh the wiki pointer block in CLAUDE.md and AGENTS.md.

Usage:
    python3 scripts/agent_context.py <project-dir> (--check | --write)
        [--wiki docs/wiki] [--targets a.md,b.md] [--json]

Writes a short, stable block between marker comments so coding agents that
read CLAUDE.md / AGENTS.md learn the compiled wiki exists and route reads
through it. Idempotent: an existing block is replaced in place; user content
outside the markers is never touched.

The block is a pointer, not a copy: no page counts, no SHAs (those churn every
compile and live in manifest.json). Content only changes when the plugin's
template changes, so prompt-cache prefixes stay stable across compiles.

Default targets ("auto"): AGENTS.md (created if missing; it is the
cross-agent convention file), plus CLAUDE.md at the project root or
.claude/CLAUDE.md, whichever exists (never both, root wins; neither is
created, pass --targets to force one).

Exit codes: 0 = ok / up to date, 1 = --check found work to do, 2 = error.
"""
# decision: BUILD-SPEC exit convention is ok/findings/error. For --write a
# successful apply exits 0 (the work is done, nothing is pending); only
# --check uses 1 to signal "blocks missing or stale".

import argparse
import json
import os
import re
import sys

MARKER_START = "<!-- tokentelemetry-brain:start -->"
MARKER_END = "<!-- tokentelemetry-brain:end -->"

BLOCK_TEMPLATE = """{start}
## Project wiki (compiled second brain)

This project has a compiled knowledge wiki at `{wiki}/`. It is a CACHE of
the codebase: pages route you to answers fast; the CODE stays authoritative.

Protocol before using any page:
- Run `python3 {wiki}/status.py <page-id>` (e.g. `subsystems/scanner`).
- FRESH: answer from the page.
- STALE / TAMPERED: do NOT trust the page body. Read the source files it
  lists, answer from CODE, then re-run with `--note` to queue a refresh.
- UNVERIFIABLE: treat the page as hints; verify against source first.
`python3 {wiki}/status.py` with no args reports the whole wiki.

Rules:
- `{wiki}/index.md` maps every page; use it to route.
- Code outranks the wiki, always: never change code to match a wiki page,
  and never hand-edit wiki pages. A stale wiki never blocks work — answer
  from source and move on.
- Refreshing is optional batched maintenance: `/brain ingest` (Claude Code)
  sweeps `{wiki}/raw/` including the notes status.py queues. In a harness
  without `/brain`, drop a note file into `{wiki}/raw/` and keep working.
{end}"""

BLOCK_RE = re.compile(
    re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END),
    re.DOTALL,
)


def render_block(wiki_rel):
    return BLOCK_TEMPLATE.format(start=MARKER_START, end=MARKER_END,
                                 wiki=wiki_rel.rstrip("/"))


def resolve_targets(project_dir, targets_arg):
    """Return list of (rel_path, create_if_missing)."""
    if targets_arg:
        return [(t.strip(), True) for t in targets_arg.split(",") if t.strip()]
    targets = [("AGENTS.md", True)]
    if os.path.isfile(os.path.join(project_dir, "CLAUDE.md")):
        targets.append(("CLAUDE.md", False))
    elif os.path.isfile(os.path.join(project_dir, ".claude", "CLAUDE.md")):
        targets.append((os.path.join(".claude", "CLAUDE.md"), False))
    return targets


def inspect(path, block):
    """Status for one file: ok | stale | no-block | missing | broken-markers."""
    if not os.path.isfile(path):
        return "missing", None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        return "error", str(e)
    has_start = MARKER_START in text
    has_end = MARKER_END in text
    if has_start != has_end:
        return "broken-markers", text
    if not has_start:
        return "no-block", text
    current = BLOCK_RE.search(text)
    if current and current.group(0) == block:
        return "ok", text
    return "stale", text


def apply_write(path, status, text, block, create):
    """Returns action taken: created | updated | appended | skipped."""
    if status == "missing":
        if not create:
            return "skipped (file absent, not creating)"
        with open(path, "w", encoding="utf-8") as f:
            f.write(block + "\n")
        return "created"
    if status == "no-block":
        joined = text.rstrip("\n") + ("\n\n" if text.strip() else "") + block + "\n"
        with open(path, "w", encoding="utf-8") as f:
            f.write(joined)
        return "appended"
    if status == "stale":
        with open(path, "w", encoding="utf-8") as f:
            f.write(BLOCK_RE.sub(block, text, count=1))
        return "updated"
    return "unchanged"


def main():
    parser = argparse.ArgumentParser(
        description="Install/refresh the wiki pointer block in CLAUDE.md / AGENTS.md."
    )
    parser.add_argument("project_dir", help="project root")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true",
                      help="report per-target status, write nothing")
    mode.add_argument("--write", action="store_true",
                      help="create/append/update blocks")
    parser.add_argument("--wiki", default="docs/wiki",
                        help="wiki path relative to project root (default docs/wiki)")
    parser.add_argument("--targets", default=None,
                        help="comma-separated target files relative to project "
                             "root (default: AGENTS.md + existing CLAUDE.md)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    project_dir = os.path.abspath(args.project_dir)
    if not os.path.isdir(project_dir):
        print(f"error: not a directory: {args.project_dir}", file=sys.stderr)
        return 2

    block = render_block(args.wiki)
    results = []
    pending = 0
    for rel, create in resolve_targets(project_dir, args.targets):
        path = os.path.join(project_dir, rel)
        if os.path.commonpath([project_dir, os.path.abspath(path)]) != project_dir:
            print(f"error: target escapes project dir: {rel}", file=sys.stderr)
            return 2
        status, text = inspect(path, block)
        if status == "error":
            print(f"error: {rel}: {text}", file=sys.stderr)
            return 2
        if status == "broken-markers":
            # One marker without its pair: never rewrite blind, a human has to
            # untangle it. Reported, not fatal for the other targets.
            results.append({"target": rel, "status": status,
                            "action": "manual fix needed (unpaired marker)"})
            pending += 1
            continue
        if args.write:
            action = apply_write(path, status, text, block, create)
        else:
            action = None
            if not (status == "ok" or (status == "missing" and not create)):
                pending += 1
        results.append({"target": rel, "status": status, "action": action})

    if args.json:
        print(json.dumps({"project": project_dir, "wiki": args.wiki,
                          "results": results}, indent=2))
    else:
        for r in results:
            line = f"{r['target']}: {r['status']}"
            if r["action"]:
                line += f" -> {r['action']}"
            print(line)

    if args.check and pending:
        return 1
    if any(r["status"] == "broken-markers" for r in results):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
