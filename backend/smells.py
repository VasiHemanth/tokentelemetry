"""
smells.py — AI Smell Detector

Rule-based detection of inefficient or problematic AI usage patterns.
All checks run over the parsed session dict and return a list of warnings.

Smells detected:
  context_rot      — session > 200 turns (context quality degrades)
  loop_trap        — same bash/tool command failing repeatedly (agent stuck)
  tool_thrash      — same file read many times (should be pinned as context)
  high_error_rate  — error count > 20% of turns
  massive_session  — total tokens > 2M (consider chunking the task)
"""

from typing import Any


# ── thresholds (easy to tune) ────────────────────────────────────────────────
CONTEXT_ROT_TURNS    = 200
LOOP_TRAP_REPEATS    = 8      # same tool+input hash N times in a row
TOOL_THRASH_READS    = 25     # same file read across whole session
HIGH_ERROR_THRESHOLD = 0.20   # error_count / turns
MASSIVE_TOKEN_LIMIT  = 2_000_000


def detect_smells(session: dict) -> list[dict[str, Any]]:
    """
    Returns a list of smell dicts:
      { "type": str, "title": str, "detail": str, "severity": "warning"|"critical" }
    Empty list = clean session.
    """
    warnings: list[dict[str, Any]] = []

    tokens     = session.get("tokens") or {}
    turns      = session.get("turns") or 0
    errors     = session.get("error_count") or 0
    total_tok  = tokens.get("total") or 0
    tool_calls = session.get("tool_calls_detail") or []   # list of {name, input_hash}
    file_reads = session.get("file_read_paths") or []     # list of path strings

    # 1. Context rot
    if turns > CONTEXT_ROT_TURNS:
        warnings.append({
            "type":     "context_rot",
            "title":    f"Context rot ({turns} turns)",
            "detail":   (
                f"This session ran for {turns} turns. "
                "Context quality typically degrades past 200 turns — "
                "consider breaking long tasks into focused sub-sessions."
            ),
            "severity": "warning" if turns < 400 else "critical",
        })

    # 2. Loop trap — consecutive repeated (tool, input_hash) pairs
    if tool_calls:
        max_streak = _max_consecutive_repeat(
            [(t.get("name", ""), t.get("input_hash", "")) for t in tool_calls]
        )
        if max_streak >= LOOP_TRAP_REPEATS:
            warnings.append({
                "type":     "loop_trap",
                "title":    f"Possible loop trap ({max_streak}× repeated tool call)",
                "detail":   (
                    f"The same tool was called with identical input {max_streak} times "
                    "consecutively. The agent may be stuck — manual intervention or a "
                    "clearer prompt may be needed."
                ),
                "severity": "critical",
            })

    # 3. Tool thrash — same file read many times
    if file_reads:
        from collections import Counter
        counts = Counter(file_reads)
        thrashed = [(f, n) for f, n in counts.items() if n >= TOOL_THRASH_READS]
        for fpath, n in sorted(thrashed, key=lambda x: -x[1])[:3]:
            short = fpath.replace("\\", "/").split("/")[-1]
            warnings.append({
                "type":     "tool_thrash",
                "title":    f'Tool thrash on "{short}" ({n}× reads)',
                "detail":   (
                    f'"{fpath}" was read {n} times. '
                    "Adding it to the agent context at session start would reduce "
                    "redundant reads and save tokens."
                ),
                "severity": "warning",
            })

    # 4. High error rate
    if turns > 5 and errors > 0:
        rate = errors / turns
        if rate >= HIGH_ERROR_THRESHOLD:
            warnings.append({
                "type":     "high_error_rate",
                "title":    f"High error rate ({errors} errors / {turns} turns = {rate:.0%})",
                "detail":   (
                    f"{errors} tool errors occurred across {turns} turns ({rate:.0%}). "
                    "This often indicates a mismatch between the agent's assumptions "
                    "and the actual environment. Check tool permissions and paths."
                ),
                "severity": "warning" if rate < 0.4 else "critical",
            })

    # 5. Massive session
    if total_tok > MASSIVE_TOKEN_LIMIT:
        m = total_tok / 1_000_000
        warnings.append({
            "type":     "massive_session",
            "title":    f"Massive session ({m:.1f}M tokens)",
            "detail":   (
                f"This session consumed {m:.1f}M tokens. "
                "Breaking large tasks into smaller focused sessions improves "
                "model accuracy and reduces cost."
            ),
            "severity": "warning" if total_tok < 5_000_000 else "critical",
        })

    return warnings


def _max_consecutive_repeat(items: list) -> int:
    """Return the longest run of identical consecutive items."""
    if not items:
        return 0
    max_run = current_run = 1
    for i in range(1, len(items)):
        if items[i] == items[i - 1]:
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 1
    return max_run
