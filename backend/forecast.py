"""
forecast.py — Burn Rate Forecasting

Computes a linear projection of token usage to predict:
  - Tokens on track to be used this calendar month
  - Days until a user-configured token limit is hit
  - Trend direction vs last week

No external deps — uses only stdlib math.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional
import math


# Default subscription limits (tokens/month) — user can override via
# ~/.tokentelemetry/subscription.json (not yet wired, uses defaults for now)
PLAN_LIMITS: dict[str, int] = {
    "claude_pro":      500_000_000,   # ~500M practical limit
    "claude_max":    2_000_000_000,   # 5× Pro
    "codex_plus":      200_000_000,
    "copilot":         100_000_000,
    "api_unlimited":            0,    # 0 = no limit
}

DEFAULT_PLAN = "claude_pro"


def _daily_buckets(sessions: list[dict], days: int = 60) -> dict[str, int]:
    """
    Aggregate total tokens per calendar day (UTC) for the last `days` days.
    Returns { "YYYY-MM-DD": token_count }.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    buckets: dict[str, int] = {}

    for s in sessions:
        ts_raw = s.get("timestamp")
        if not ts_raw:
            continue
        try:
            if isinstance(ts_raw, str):
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            else:
                ts = ts_raw
            if ts < cutoff:
                continue
            day_key = ts.strftime("%Y-%m-%d")
            buckets[day_key] = buckets.get(day_key, 0) + (s.get("tokens", {}).get("total") or 0)
        except Exception:
            continue

    return buckets


def _linear_regression(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """Returns (slope, intercept) for simple linear regression."""
    n = len(xs)
    if n < 2:
        return 0.0, ys[0] if ys else 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num   = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denom = sum((x - mx) ** 2 for x in xs)
    slope = num / denom if denom != 0 else 0.0
    return slope, my - slope * mx


def compute_forecast(
    sessions: list[dict],
    plan: str = DEFAULT_PLAN,
) -> dict:
    """
    Returns a forecast dict:
    {
      "daily_avg_7d":         int,      # avg tokens/day over last 7 days
      "daily_avg_30d":        int,      # avg tokens/day over last 30 days
      "projected_month":      int,      # tokens projected for current calendar month
      "days_until_limit":     int|None, # None if no limit or won't hit
      "trend":                str,      # "accelerating" | "steady" | "slowing"
      "trend_pct":            float,    # % change week-over-week
      "limit":                int,      # configured limit (0 = none)
      "plan":                 str,
      "buckets_30d":          dict,     # { "YYYY-MM-DD": tokens } for charting
    }
    """
    limit = PLAN_LIMITS.get(plan, PLAN_LIMITS[DEFAULT_PLAN])
    buckets_60d = _daily_buckets(sessions, days=60)
    buckets_30d = {k: v for k, v in buckets_60d.items()
                   if k >= (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")}

    # Daily averages
    vals_7d  = _last_n_days_values(buckets_60d, 7)
    vals_30d = _last_n_days_values(buckets_60d, 30)

    avg_7d  = int(sum(vals_7d)  / max(len(vals_7d),  1))
    avg_30d = int(sum(vals_30d) / max(len(vals_30d), 1))

    # Days left in current month
    now = datetime.now(timezone.utc)
    if now.month == 12:
        next_month = now.replace(year=now.year + 1, month=1, day=1)
    else:
        next_month = now.replace(month=now.month + 1, day=1)
    days_left = (next_month - now).days

    # Tokens already used this month
    month_prefix = now.strftime("%Y-%m")
    used_this_month = sum(v for k, v in buckets_60d.items() if k.startswith(month_prefix))

    # Project remaining days at 7d average
    projected_month = used_this_month + avg_7d * days_left

    # Days until limit
    days_until_limit: Optional[int] = None
    if limit > 0 and avg_7d > 0:
        remaining_budget = limit - used_this_month
        if remaining_budget <= 0:
            days_until_limit = 0
        else:
            days_until_limit = max(0, int(remaining_budget / avg_7d))

    # Trend: compare last 7 days vs previous 7 days
    vals_prev7 = _last_n_days_values(buckets_60d, 14, skip=7)
    avg_prev7 = sum(vals_prev7) / max(len(vals_prev7), 1)

    if avg_prev7 > 0:
        trend_pct = ((avg_7d - avg_prev7) / avg_prev7) * 100
    else:
        trend_pct = 0.0

    if trend_pct > 15:
        trend = "accelerating"
    elif trend_pct < -15:
        trend = "slowing"
    else:
        trend = "steady"

    return {
        "daily_avg_7d":     avg_7d,
        "daily_avg_30d":    avg_30d,
        "projected_month":  projected_month,
        "used_this_month":  used_this_month,
        "days_until_limit": days_until_limit,
        "trend":            trend,
        "trend_pct":        round(trend_pct, 1),
        "limit":            limit,
        "plan":             plan,
        "buckets_30d":      buckets_30d,
    }


def _last_n_days_values(buckets: dict[str, int], n: int, skip: int = 0) -> list[int]:
    """Return token values for the `n` days ending `skip` days ago."""
    today = datetime.now(timezone.utc).date()
    result = []
    for i in range(skip, skip + n):
        day = (today - timedelta(days=i + 1)).strftime("%Y-%m-%d")
        result.append(buckets.get(day, 0))
    return result
