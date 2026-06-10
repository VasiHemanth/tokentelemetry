"""
trends.py — Session Trends Intelligence

Buckets sessions by calendar day and computes efficiency time-series data
so the dashboard can show whether you're improving, steady, or declining.

No external dependencies — pure stdlib.

Returned shape
--------------
{
  "days": [
    {
      "date":          "2026-05-20",      # YYYY-MM-DD
      "avg_efficiency": 73.4,
      "session_count":  3,
      "total_tokens":   245000,
      "best":           89.1,
      "worst":          52.0,
      "rolling_7d":     68.2,             # null for first 6 days with data
    },
    ...                                   # sorted ascending by date (last 60 days)
  ],
  "trend":           "improving",         # improving | steady | declining
  "trend_delta":     +8.3,               # last-7d avg minus prior-7d avg
  "overall_avg":     65.7,
  "current_streak":  4,                   # consecutive days ending today with avg >= 60
  "best_day":        { "date": "2026-05-28", "avg_efficiency": 89.1 },
  "worst_day":       { "date": "2026-05-12", "avg_efficiency": 21.0 },
  "total_sessions":  47,
  "days_with_data":  22,
  "week_over_week":  +8.3,               # same as trend_delta, convenience alias
}
"""

from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _date_str(ts) -> Optional[str]:
    """Extract YYYY-MM-DD from a session timestamp (datetime or ISO string)."""
    if ts is None:
        return None
    if hasattr(ts, "strftime"):
        return ts.strftime("%Y-%m-%d")
    try:
        s = str(ts)
        return s[:10] if len(s) >= 10 else None
    except Exception:
        return None


def compute_trends(sessions: list[dict], days: int = 60) -> dict:
    """
    Compute daily efficiency trends over the last `days` calendar days.

    Parameters
    ----------
    sessions : enriched session dicts (must have 'efficiency' and 'timestamp')
    days     : how many calendar days back to include (default 60)
    """
    today = datetime.now(timezone.utc).date()
    cutoff = today - timedelta(days=days - 1)

    # Bucket: date_str -> list of efficiency scores + token totals
    buckets: dict[str, dict] = defaultdict(lambda: {
        "scores": [],
        "tokens": 0,
    })

    for s in sessions:
        eff = s.get("efficiency")
        if eff is None:
            continue
        date_s = _date_str(s.get("timestamp"))
        if not date_s:
            continue
        try:
            d = datetime.strptime(date_s, "%Y-%m-%d").date()
        except Exception:
            continue
        if d < cutoff or d > today:
            continue
        b = buckets[date_s]
        b["scores"].append(float(eff))
        tok = s.get("tokens")
        if isinstance(tok, dict):
            b["tokens"] += int(tok.get("total", 0))

    # Build ordered list of all days in range (including empty days)
    day_list = []
    for i in range(days):
        d = cutoff + timedelta(days=i)
        day_list.append(d.strftime("%Y-%m-%d"))

    # Build per-day rows (only include days that have data)
    rows_with_data = []
    for date_s in day_list:
        b = buckets.get(date_s)
        if not b or not b["scores"]:
            continue
        scores = b["scores"]
        rows_with_data.append({
            "date":           date_s,
            "avg_efficiency": round(sum(scores) / len(scores), 1),
            "session_count":  len(scores),
            "total_tokens":   b["tokens"],
            "best":           round(max(scores), 1),
            "worst":          round(min(scores), 1),
            "rolling_7d":     None,  # filled in below
        })

    # Compute 7-day rolling average (over days that have data, looking back by
    # calendar date rather than by row index so gaps don't skew the window).
    date_to_avg = {r["date"]: r["avg_efficiency"] for r in rows_with_data}
    for row in rows_with_data:
        d = datetime.strptime(row["date"], "%Y-%m-%d").date()
        window = []
        for j in range(7):
            past = (d - timedelta(days=j)).strftime("%Y-%m-%d")
            if past in date_to_avg:
                window.append(date_to_avg[past])
        row["rolling_7d"] = round(sum(window) / len(window), 1) if window else None

    # Trend: compare last 7 data-days vs prior 7 data-days
    recent_7 = [r["avg_efficiency"] for r in rows_with_data[-7:]]
    prior_7  = [r["avg_efficiency"] for r in rows_with_data[-14:-7]]
    recent_avg = sum(recent_7) / len(recent_7) if recent_7 else None
    prior_avg  = sum(prior_7)  / len(prior_7)  if prior_7  else None

    if recent_avg is not None and prior_avg is not None:
        delta = round(recent_avg - prior_avg, 1)
        if delta >= 5:
            trend = "improving"
        elif delta <= -5:
            trend = "declining"
        else:
            trend = "steady"
    else:
        delta = 0.0
        trend = "steady"

    # Current streak: consecutive most-recent days with avg_efficiency >= 60
    streak = 0
    for row in reversed(rows_with_data):
        if row["avg_efficiency"] >= 60:
            streak += 1
        else:
            break

    # Best / worst days
    best_day  = max(rows_with_data, key=lambda r: r["avg_efficiency"], default=None)
    worst_day = min(rows_with_data, key=lambda r: r["avg_efficiency"], default=None)

    all_scores = [r["avg_efficiency"] for r in rows_with_data]
    overall_avg = round(sum(all_scores) / len(all_scores), 1) if all_scores else None
    total_sessions = sum(r["session_count"] for r in rows_with_data)

    return {
        "days":           rows_with_data,
        "trend":          trend,
        "trend_delta":    delta,
        "week_over_week": delta,
        "overall_avg":    overall_avg,
        "current_streak": streak,
        "best_day":       {"date": best_day["date"],  "avg_efficiency": best_day["avg_efficiency"]}  if best_day  else None,
        "worst_day":      {"date": worst_day["date"], "avg_efficiency": worst_day["avg_efficiency"]} if worst_day else None,
        "total_sessions": total_sessions,
        "days_with_data": len(rows_with_data),
    }
