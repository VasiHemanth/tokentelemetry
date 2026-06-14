"""
time_intel.py — Time Intelligence

Analyses when sessions are most efficient by bucketing on hour-of-day and
day-of-week, then surfaces peak windows and productivity patterns.

No external dependencies — pure stdlib.

Returned shape
--------------
{
  "by_hour": [
    {
      "hour":           9,              # 0–23 (UTC hour of session start)
      "label":          "9 AM",
      "avg_efficiency": 74.2,
      "session_count":  5,
      "total_tokens":   183000,
    },
    ...                                 # only hours that have at least one session
  ],
  "by_dow": [
    {
      "dow":            0,              # 0=Mon … 6=Sun
      "label":          "Mon",
      "avg_efficiency": 68.1,
      "session_count":  8,
      "total_tokens":   310000,
    },
    ...
  ],
  "peak_hour":   { "hour": 9, "label": "9 AM",  "avg_efficiency": 74.2 },
  "worst_hour":  { "hour": 23, "label": "11 PM", "avg_efficiency": 18.0 },
  "peak_dow":    { "dow": 1, "label": "Tue",     "avg_efficiency": 79.0 },
  "worst_dow":   { "dow": 5, "label": "Sat",     "avg_efficiency": 22.0 },
  "peak_period": "morning",             # morning | afternoon | evening | night
  "sessions_analysed": 44,
  "sessions_skipped":   3,             # no timestamp or no efficiency
}
"""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

_DOW_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

_HOUR_FMT = {
    0: "12 AM", 1: "1 AM",  2: "2 AM",  3: "3 AM",  4: "4 AM",  5: "5 AM",
    6: "6 AM",  7: "7 AM",  8: "8 AM",  9: "9 AM",  10: "10 AM", 11: "11 AM",
    12: "12 PM", 13: "1 PM", 14: "2 PM", 15: "3 PM", 16: "4 PM", 17: "5 PM",
    18: "6 PM", 19: "7 PM", 20: "8 PM", 21: "9 PM", 22: "10 PM", 23: "11 PM",
}


def _period(hour: int) -> str:
    if 5 <= hour < 12:   return "morning"
    if 12 <= hour < 17:  return "afternoon"
    if 17 <= hour < 21:  return "evening"
    return "night"


def _parse_ts(ts) -> Optional[datetime]:
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    try:
        s = str(ts)
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def analyse_time(sessions: list[dict]) -> dict:
    hour_buckets: dict[int, dict] = defaultdict(lambda: {"scores": [], "tokens": 0})
    dow_buckets:  dict[int, dict] = defaultdict(lambda: {"scores": [], "tokens": 0})

    analysed = 0
    skipped  = 0

    for s in sessions:
        eff = s.get("efficiency")
        if eff is None:
            skipped += 1
            continue
        dt = _parse_ts(s.get("timestamp"))
        if dt is None:
            skipped += 1
            continue

        hour = dt.hour
        dow  = dt.weekday()   # 0=Mon
        tok  = s.get("tokens")
        total_tok = int(tok.get("total", 0)) if isinstance(tok, dict) else 0

        hour_buckets[hour]["scores"].append(float(eff))
        hour_buckets[hour]["tokens"] += total_tok
        dow_buckets[dow]["scores"].append(float(eff))
        dow_buckets[dow]["tokens"] += total_tok
        analysed += 1

    def _row_hour(h: int) -> dict:
        b = hour_buckets[h]
        avg = round(sum(b["scores"]) / len(b["scores"]), 1)
        return {
            "hour":           h,
            "label":          _HOUR_FMT[h],
            "avg_efficiency": avg,
            "session_count":  len(b["scores"]),
            "total_tokens":   b["tokens"],
        }

    def _row_dow(d: int) -> dict:
        b = dow_buckets[d]
        avg = round(sum(b["scores"]) / len(b["scores"]), 1)
        return {
            "dow":            d,
            "label":          _DOW_LABELS[d],
            "avg_efficiency": avg,
            "session_count":  len(b["scores"]),
            "total_tokens":   b["tokens"],
        }

    by_hour = sorted([_row_hour(h) for h in hour_buckets], key=lambda r: r["hour"])
    by_dow  = sorted([_row_dow(d)  for d in dow_buckets],  key=lambda r: r["dow"])

    peak_hour  = max(by_hour, key=lambda r: r["avg_efficiency"], default=None) if by_hour else None
    worst_hour = min(by_hour, key=lambda r: r["avg_efficiency"], default=None) if by_hour else None
    peak_dow   = max(by_dow,  key=lambda r: r["avg_efficiency"], default=None) if by_dow  else None
    worst_dow  = min(by_dow,  key=lambda r: r["avg_efficiency"], default=None) if by_dow  else None

    # Peak period — weighted average efficiency per period
    period_scores: dict[str, list] = defaultdict(list)
    for row in by_hour:
        period_scores[_period(row["hour"])].extend(
            [row["avg_efficiency"]] * row["session_count"]
        )
    best_period = max(
        period_scores,
        key=lambda p: sum(period_scores[p]) / len(period_scores[p]) if period_scores[p] else 0,
        default="morning",
    ) if period_scores else "morning"

    return {
        "by_hour":            by_hour,
        "by_dow":             by_dow,
        "peak_hour":          peak_hour,
        "worst_hour":         worst_hour,
        "peak_dow":           peak_dow,
        "worst_dow":          worst_dow,
        "peak_period":        best_period,
        "sessions_analysed":  analysed,
        "sessions_skipped":   skipped,
    }
