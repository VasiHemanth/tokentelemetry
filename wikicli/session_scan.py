#!/usr/bin/env python3
"""session_scan.py: locate a project's coding-agent session logs across every
supported harness and emit STRUCTURAL SIGNALS ONLY for the session-miner
subagent (design D2).

Harnesses are pluggable: scripts/harness_adapters.py holds one locate+parse
adapter per agent (claude, codex, opencode, qwen, cline, hermes, smallcode,
grok, copilot, vibe, antigravity), each tagged with a capability level
("full" / "partial" / "tokens" / "presence") describing which signal classes
that store can honestly provide. The signal schema is identical across
harnesses; each session carries a "harness" field and the aggregate includes
a per-harness breakdown.

PRIVACY BOUNDARY (design D2, BUILD-SPEC rule 3). Only structural metadata is
extracted:
  - session id, harness, first/last timestamps
  - per-tool-name call counts
  - file paths taken from tool INPUTS (these name the user's own files)
  - is_error FLAG counts where the store exposes one (the boolean only)
  - repeated identical consecutive tool calls (loop signatures)
  - token totals as the store records them

It NEVER emits message text, thinking text, user prompts, tool_result
content, or any data value. One approved exception (maintainer, 2026-07-06):
harnesses that record tools as shell strings (codex, grok's terminal tool)
have those strings tokenized IN MEMORY to extract file-path tokens; only the
paths are emitted, never the command text. Do not extend content extraction
beyond that.

Usage:
  python3 scripts/session_scan.py <project-dir> [--harness all]
                                  [--limit 30] [--json]

--harness accepts "all" (default), one name, or a comma list.
--limit is per harness (newest N sessions by recency).

Exit codes: 0 = scanned ok (signals emitted, possibly empty), 2 = error
(bad args / unknown harness).
# decision: no exit-1 "findings" state, a scan has no pass/fail; empty result
# is still a successful scan. Follows BUILD-SPEC rule 2's 0/2 for this script.
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict

try:
    # package invocation: python3 -m wikicli.session_scan (how bin/cli.js runs it)
    from .harness_adapters import ADAPTERS, encode_claude_dir
except ImportError:
    # direct invocation: python3 wikicli/session_scan.py
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from harness_adapters import ADAPTERS, encode_claude_dir  # noqa: E402


def aggregate(sessions):
    """Roll per-session signals up across the scanned set (all harnesses)."""
    reread_count = Counter()
    reread_sessions = defaultdict(set)
    loop_count = Counter()
    loop_sessions = defaultdict(set)
    tool_totals = Counter()
    tokens = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
    errors = 0
    by_harness = {}

    for s in sessions:
        sid = s["session_id"]
        h = s["harness"]
        hb = by_harness.setdefault(h, {"session_count": 0, "token_total": 0,
                                       "tool_calls": 0})
        hb["session_count"] += 1
        hb["token_total"] += s["token_total"]
        hb["tool_calls"] += sum(s["tool_counts"].values())
        for path, n in s["read_paths"].items():
            reread_count[path] += n
            reread_sessions[path].add((h, sid))
        for lp in s["loops"]:
            key = (lp["tool"], lp["path"])
            loop_count[key] += lp["count"]
            loop_sessions[key].add((h, sid))
        for name, n in s["tool_counts"].items():
            tool_totals[name] += n
        for k in tokens:
            tokens[k] += s["tokens"][k]
        errors += s["error_count"]

    top_reread = [
        {"path": p, "read_count": n, "session_count": len(reread_sessions[p])}
        for p, n in reread_count.most_common()
        if n >= 2  # "re-read" = read more than once
    ]
    loops = [
        {"tool": t, "path": p, "count": n,
         "session_count": len(loop_sessions[(t, p)])}
        for (t, p), n in loop_count.most_common()
    ]
    return {
        "session_count": len(sessions),
        "by_harness": by_harness,
        "top_reread_files": top_reread,
        "loop_signatures": loops,
        "tool_call_mix": dict(tool_totals.most_common()),
        "tokens": tokens,
        "token_total": sum(tokens.values()),
        "error_result_count": errors,
    }


def build_result(project_dir, harnesses, sessions, limit):
    per_session = [
        {
            "session_id": s["session_id"],
            "harness": s["harness"],
            "capability": s["capability"],
            "first_ts": s["first_ts"],
            "last_ts": s["last_ts"],
            "tool_counts": s["tool_counts"],
            "file_paths": s["file_paths"],
            "error_result_count": s["error_count"],
            "token_total": s["token_total"],
            "loop_signatures": s["loops"],
        }
        for s in sessions
    ]
    return {
        "harness": ",".join(harnesses),
        "project_dir": project_dir,
        "encoded_dir": encode_claude_dir(project_dir),
        "limit": limit,
        "capabilities": {h: ADAPTERS[h]["capability"] for h in harnesses},
        "aggregate": aggregate(sessions) if sessions else {
            "session_count": 0, "by_harness": {}, "top_reread_files": [],
            "loop_signatures": [], "tool_call_mix": {},
            "tokens": {"input": 0, "output": 0, "cache_read": 0,
                       "cache_creation": 0},
            "token_total": 0, "error_result_count": 0,
        },
        "sessions": per_session,
    }


def render_human(result):
    out = []
    agg = result["aggregate"]
    out.append("session_scan (structural signals only)")
    out.append(f"project:   {result['project_dir']}")
    out.append(f"harnesses: {result['harness']}")
    out.append(f"scanned:   {agg['session_count']} session(s), "
               f"limit {result['limit']}/harness")
    if agg["session_count"] == 0:
        out.append("")
        out.append("No sessions found for this project in any scanned harness.")
        return "\n".join(out)

    if agg["by_harness"]:
        out.append("")
        out.append("by harness (sessions | tool calls | tokens | capability)")
        for h, hb in sorted(agg["by_harness"].items(),
                            key=lambda kv: -kv[1]["session_count"]):
            cap = result["capabilities"].get(h, "?")
            out.append(f"  {hb['session_count']:>4} | {hb['tool_calls']:>5} | "
                       f"{hb['token_total']:>12,} | {cap:<8} {h}")

    t = agg["tokens"]
    out.append("")
    out.append("totals")
    out.append(f"  tokens: {agg['token_total']:,} "
               f"(in {t['input']:,} / out {t['output']:,} / "
               f"cache_read {t['cache_read']:,} / cache_write {t['cache_creation']:,})")
    out.append(f"  tool_result errors (flag only): {agg['error_result_count']}")

    mix = agg["tool_call_mix"]
    if mix:
        out.append("")
        out.append("tool call mix")
        for name, n in list(mix.items())[:12]:
            out.append(f"  {n:>5}  {name}")

    if agg["top_reread_files"]:
        out.append("")
        out.append("top re-read files (path | reads | sessions)")
        for r in agg["top_reread_files"][:15]:
            out.append(f"  {r['read_count']:>4} | {r['session_count']:>2} | {r['path']}")

    if agg["loop_signatures"]:
        out.append("")
        out.append("loop signatures (repeated consecutive identical calls)")
        for lp in agg["loop_signatures"][:15]:
            out.append(f"  {lp['count']:>4} x  {lp['tool']}  {lp['path']}")

    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Locate a project's coding-agent session logs across all "
                    "supported harnesses and emit structural signals only "
                    "(no transcript content).")
    ap.add_argument("project_dir", help="Absolute or relative path to the project.")
    ap.add_argument("--harness", default="all",
                    help="'all' (default), one harness name, or a comma list. "
                         f"Known: {', '.join(sorted(ADAPTERS))}.")
    ap.add_argument("--limit", type=int, default=30,
                    help="Parse the newest N sessions per harness (default 30).")
    ap.add_argument("--json", action="store_true", dest="as_json",
                    help="Emit the full structured result as JSON.")
    args = ap.parse_args(argv)

    if args.limit <= 0:
        print("error: --limit must be positive", file=sys.stderr)
        return 2

    if args.harness.strip().lower() == "all":
        harnesses = sorted(ADAPTERS)
    else:
        harnesses = [h.strip() for h in args.harness.split(",") if h.strip()]
        unknown = [h for h in harnesses if h not in ADAPTERS]
        if unknown:
            print(f"error: unknown harness(es): {', '.join(unknown)}. "
                  f"Known: {', '.join(sorted(ADAPTERS))}", file=sys.stderr)
            return 2

    project_dir = os.path.abspath(os.path.expanduser(args.project_dir))

    sessions = []
    for h in harnesses:
        adapter = ADAPTERS[h]
        try:
            refs = adapter["locate"](project_dir, args.limit)
        except Exception:
            continue  # a broken store never fails the whole scan
        for ref in refs:
            try:
                s = adapter["scan"](ref, project_dir)
            except Exception:
                s = None
            if s is not None:
                s["harness"] = h
                s["capability"] = adapter["capability"]
                sessions.append(s)

    result = build_result(project_dir, harnesses, sessions, args.limit)

    if args.as_json:
        print(json.dumps(result, indent=2))
    else:
        print(render_human(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
