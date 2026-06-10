"""
project_health.py — Project Health Score

Computes a composite 0–100 health score per project by aggregating
efficiency, smell rate, recent trend, and cost efficiency signals.

Grade bands
-----------
  A  80–100   Excellent
  B  60–79    Good
  C  40–59    Fair
  D  20–39    Needs attention
  F   0–19    Critical

No external dependencies — pure stdlib.
"""

from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional


def _grade(score: float) -> str:
    if score >= 80: return "A"
    if score >= 60: return "B"
    if score >= 40: return "C"
    if score >= 20: return "D"
    return "F"


def _date_str(ts) -> Optional[str]:
    if ts is None:
        return None
    if hasattr(ts, "strftime"):
        return ts.strftime("%Y-%m-%d")
    try:
        return str(ts)[:10]
    except Exception:
        return None


def compute_project_health(sessions: list[dict]) -> dict:
    """
    Compute per-project composite health scores.

    Returns
    -------
    {
      "projects": [
        {
          "project":           str,
          "session_count":     int,
          "health_score":      float,      # 0–100 composite
          "grade":             "A"|"B"|"C"|"D"|"F",
          "avg_efficiency":    float,
          "smell_rate":        float,      # 0–100 (% sessions with smells)
          "recent_efficiency": float|null, # last 7 days avg
          "trend":             "up"|"flat"|"down"|null,
          "cost_per_eff_pt":   float|null,
          "components": {
            "efficiency":    float,        # 0–100 sub-score
            "smell_free":    float,        # 0–100 sub-score
            "recent_trend":  float,        # 0–100 sub-score
            "cost_value":    float,        # 0–100 sub-score
          }
        },
        ...                                # sorted by health_score desc
      ],
      "total_projects":   int,
      "healthy_projects": int,             # grade A or B
      "at_risk_projects": int,             # grade D or F
    }
    """
    today = datetime.now(timezone.utc).date()
    cutoff_recent = today - timedelta(days=7)

    # Bucket per project
    buckets: dict[str, dict] = defaultdict(lambda: {
        "effs":         [],
        "smells":       [],       # list of bool (has_smell)
        "recent_effs":  [],
        "older_effs":   [],
        "costs":        [],
    })

    for s in sessions:
        proj = s.get("project", "")
        if not proj:
            continue
        eff = s.get("efficiency")
        if eff is None:
            continue

        eff_f = float(eff)
        b = buckets[proj]
        b["effs"].append(eff_f)

        has_smell = bool(s.get("smells"))
        b["smells"].append(has_smell)

        # recent vs older split
        ds = _date_str(s.get("timestamp"))
        try:
            d = datetime.strptime(ds, "%Y-%m-%d").date() if ds else None
        except Exception:
            d = None

        if d and d >= cutoff_recent:
            b["recent_effs"].append(eff_f)
        else:
            b["older_effs"].append(eff_f)

        cost = s.get("cost")
        if cost is not None and float(cost) > 0:
            b["costs"].append(float(cost))

    # Collect per-model cost_per_eff_pt across all sessions for normalisation
    all_cpp = []
    proj_cpp_raw: dict[str, Optional[float]] = {}
    for proj, b in buckets.items():
        if b["costs"] and b["effs"]:
            avg_c = sum(b["costs"]) / len(b["costs"])
            avg_e = sum(b["effs"]) / len(b["effs"])
            cpp   = avg_c / avg_e if avg_e > 0 else None
            proj_cpp_raw[proj] = cpp
            if cpp is not None:
                all_cpp.append(cpp)
        else:
            proj_cpp_raw[proj] = None

    max_cpp = max(all_cpp) if all_cpp else 1.0

    projects = []
    for proj, b in buckets.items():
        n = len(b["effs"])
        if n == 0:
            continue

        avg_eff   = sum(b["effs"]) / n
        smell_rate = round(sum(b["smells"]) / n * 100, 1) if b["smells"] else 0.0

        recent_avg = (sum(b["recent_effs"]) / len(b["recent_effs"])
                      if b["recent_effs"] else None)
        older_avg  = (sum(b["older_effs"])  / len(b["older_effs"])
                      if b["older_effs"]  else None)

        if recent_avg is not None and older_avg is not None:
            diff = recent_avg - older_avg
            trend = "up" if diff >= 5 else "down" if diff <= -5 else "flat"
        elif recent_avg is not None:
            trend = "flat"
        else:
            trend = None

        cpp = proj_cpp_raw.get(proj)

        # ── Sub-scores (each 0–100) ────────────────────────────────────────
        # 1. Efficiency score: direct 0-100
        c_eff = avg_eff

        # 2. Smell-free: 100 - smell_rate
        c_smell = 100 - smell_rate

        # 3. Recent trend:
        #    recent > older+5 → 80–100, equal ±5 → 50, recent < older-5 → 0–40
        if recent_avg is not None and older_avg is not None:
            ratio = (recent_avg - older_avg) / max(older_avg, 1) * 100
            c_trend = max(0, min(100, 50 + ratio * 2))
        elif recent_avg is not None:
            c_trend = min(100, recent_avg)
        else:
            c_trend = 50.0  # neutral if no recent data

        # 4. Cost value: lower cpp = higher score; cpp=0 (no cost data) → neutral 60
        if cpp is not None and max_cpp > 0:
            c_cost = max(0, 100 - (cpp / max_cpp * 100))
        else:
            c_cost = 60.0

        # Weights
        health_score = round(
            c_eff   * 0.40 +
            c_smell * 0.25 +
            c_trend * 0.20 +
            c_cost  * 0.15,
            1,
        )

        projects.append({
            "project":           proj,
            "session_count":     n,
            "health_score":      health_score,
            "grade":             _grade(health_score),
            "avg_efficiency":    round(avg_eff, 1),
            "smell_rate":        smell_rate,
            "recent_efficiency": round(recent_avg, 1) if recent_avg is not None else None,
            "trend":             trend,
            "cost_per_eff_pt":   round(cpp, 6) if cpp is not None else None,
            "components": {
                "efficiency":   round(c_eff, 1),
                "smell_free":   round(c_smell, 1),
                "recent_trend": round(c_trend, 1),
                "cost_value":   round(c_cost, 1),
            },
        })

    projects.sort(key=lambda p: -p["health_score"])

    healthy = sum(1 for p in projects if p["grade"] in ("A", "B"))
    at_risk = sum(1 for p in projects if p["grade"] in ("D", "F"))

    return {
        "projects":         projects,
        "total_projects":   len(projects),
        "healthy_projects": healthy,
        "at_risk_projects": at_risk,
    }
