"""
tool_footprint.py — Tool Footprint Intelligence

Analyses how the number and composition of available tools in a session
correlates with efficiency. Uses the mcp_tools list already stored on
each session object.

Categories
----------
A tool name is classified as:
  core    — Read, Edit, Write, Glob, Grep, Bash, PowerShell (fundamental FS/shell)
  agent   — Agent, Task*, Spawn, SubAgent  (multi-agent orchestration)
  browser — mcp__Claude_in_Chrome__*, mcp__computer-use__*  (UI/browser)
  mcp     — any other mcp__* tool  (third-party MCP integrations)
  meta    — Skill, ToolSearch, Notification*, Schedule*  (harness meta-tools)

No external dependencies — pure stdlib.

Returned shape
--------------
{
  "by_size": [
    {
      "bucket":         "1–5",
      "avg_efficiency": 72.1,
      "session_count":  6,
      "label":          "lean",        # lean | standard | heavy | bloated
    },
    ...
  ],
  "by_category_presence": {
    "core":    { "with": { "avg": 71.2, "n": 30 }, "without": { "avg": 41.0, "n": 14 } },
    "agent":   { "with": ...,  "without": ... },
    "browser": { "with": ...,  "without": ... },
    "mcp":     { "with": ...,  "without": ... },
    "meta":    { "with": ...,  "without": ... },
  },
  "top_tools": [            # tools present in the most sessions
    { "tool": "Bash", "session_count": 38, "avg_efficiency": 65.0 },
    ...                     # top 15
  ],
  "optimal_range": "1–5",   # bucket label with highest avg_efficiency
  "sessions_analysed": 44,
  "sessions_skipped":  3,
}
"""

from collections import defaultdict
from typing import Optional


_CORE_TOOLS  = {"Read", "Edit", "Write", "Glob", "Grep", "Bash", "PowerShell"}
_AGENT_TOOLS = {"Agent", "SubAgent", "Spawn", "TaskCreate", "TaskUpdate",
                "TaskStop", "TaskGet", "TaskList", "TaskOutput"}
_META_TOOLS  = {"Skill", "ToolSearch", "Notification", "ScheduleWakeup",
                "CronCreate", "CronDelete", "CronList", "PushNotification",
                "Monitor", "RemoteTrigger", "EnterPlanMode", "ExitPlanMode"}

_BUCKETS = [
    (1,  5,  "1–5",   "lean"),
    (6,  15, "6–15",  "standard"),
    (16, 30, "16–30", "heavy"),
    (31, 999,"31+",   "bloated"),
]


def _categorise(tool: str) -> str:
    if tool in _CORE_TOOLS:
        return "core"
    if tool in _AGENT_TOOLS:
        return "agent"
    if "computer-use" in tool or "Claude_in_Chrome" in tool:
        return "browser"
    if tool.startswith("mcp__"):
        return "mcp"
    return "meta"


def _bucket_label(n: int) -> tuple[str, str]:
    for lo, hi, label, kind in _BUCKETS:
        if lo <= n <= hi:
            return label, kind
    return "31+", "bloated"


def analyse_tool_footprint(sessions: list[dict]) -> dict:
    size_buckets: dict[str, dict] = {}   # label -> {scores, kind}
    for lo, hi, label, kind in _BUCKETS:
        size_buckets[label] = {"scores": [], "kind": kind}

    # per-tool: {scores: [], count: 0}
    tool_data: dict[str, dict] = defaultdict(lambda: {"scores": [], "count": 0})

    # category presence: { cat: {with: [], without: []} }
    cat_data: dict[str, dict] = {
        c: {"with": [], "without": []}
        for c in ("core", "agent", "browser", "mcp", "meta")
    }

    analysed = 0
    skipped  = 0

    for s in sessions:
        eff = s.get("efficiency")
        if eff is None:
            skipped += 1
            continue
        tools = s.get("mcp_tools") or []
        if not isinstance(tools, list):
            skipped += 1
            continue

        eff_f = float(eff)
        n = len(tools)
        bucket_label, _ = _bucket_label(n)
        size_buckets[bucket_label]["scores"].append(eff_f)

        # per-tool tracking
        seen_cats: set[str] = set()
        for t in tools:
            tool_data[t]["scores"].append(eff_f)
            tool_data[t]["count"] += 1
            seen_cats.add(_categorise(t))

        # category presence
        for cat in cat_data:
            if cat in seen_cats:
                cat_data[cat]["with"].append(eff_f)
            else:
                cat_data[cat]["without"].append(eff_f)

        analysed += 1

    # Build by_size (only non-empty buckets, in order)
    by_size = []
    for lo, hi, label, kind in _BUCKETS:
        b = size_buckets[label]
        if not b["scores"]:
            continue
        by_size.append({
            "bucket":         label,
            "avg_efficiency": round(sum(b["scores"]) / len(b["scores"]), 1),
            "session_count":  len(b["scores"]),
            "label":          kind,
        })

    optimal_range = max(by_size, key=lambda r: r["avg_efficiency"])["bucket"] if by_size else None

    # by_category_presence
    def _stats(scores: list) -> Optional[dict]:
        if not scores:
            return None
        return {"avg": round(sum(scores) / len(scores), 1), "n": len(scores)}

    by_category = {}
    for cat, d in cat_data.items():
        if not d["with"] and not d["without"]:
            continue
        by_category[cat] = {
            "with":    _stats(d["with"]),
            "without": _stats(d["without"]),
        }

    # Top tools by session count, with avg efficiency
    top_tools = sorted(
        [
            {
                "tool":          t,
                "session_count": d["count"],
                "avg_efficiency": round(sum(d["scores"]) / len(d["scores"]), 1) if d["scores"] else 0,
                "category":      _categorise(t),
            }
            for t, d in tool_data.items()
        ],
        key=lambda r: -r["session_count"],
    )[:15]

    return {
        "by_size":              by_size,
        "by_category_presence": by_category,
        "top_tools":            top_tools,
        "optimal_range":        optimal_range,
        "sessions_analysed":    analysed,
        "sessions_skipped":     skipped,
    }
