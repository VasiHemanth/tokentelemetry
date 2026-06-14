"""
cost_intel.py — Cost Intelligence

Connects session cost (USD) to efficiency outcomes, exposing which models
and task types deliver the best efficiency per dollar, and how cache usage
affects both cost and quality.

No external dependencies — pure stdlib.

Returned shape
--------------
{
  "by_model": [
    {
      "model":             "claude-sonnet-4-6",
      "agent":             "claude",
      "session_count":     12,
      "avg_cost":          0.42,
      "total_cost":        5.04,
      "avg_efficiency":    71.3,
      "cost_per_eff_pt":   0.0059,    # avg_cost / avg_efficiency (lower = better)
      "avg_cache_hit_pct": 42.1,      # cached / total * 100
    },
    ...                               # sorted by cost_per_eff_pt ascending (best value first)
  ],
  "by_task_type": [
    {
      "task_type":       "build",
      "session_count":   8,
      "avg_cost":        1.21,
      "avg_efficiency":  74.0,
      "cost_per_eff_pt": 0.016,
    },
    ...
  ],
  "cache_tiers": [
    {
      "tier":            "80–100%",
      "avg_efficiency":  72.1,
      "avg_cost":        0.31,
      "session_count":   7,
    },
    ...                               # 5 tiers: 0-20, 20-40, 40-60, 60-80, 80-100
  ],
  "wasteful": [
    {
      "session_id":  "...",
      "model":       "...",
      "cost":        8.40,
      "efficiency":  4.2,
      "task_type":   "other",
      "waste_score": 92.1,            # cost_percentile_rank - efficiency, higher = more wasteful
    },
    ...                               # top-5 worst cost/efficiency ratio sessions
  ],
  "best_value_model":   "claude-sonnet-4-6",   # lowest cost_per_eff_pt with >= 2 sessions
  "total_cost":          47.30,
  "avg_cost_per_session": 1.05,
  "avg_cache_hit_pct":   38.4,
  "sessions_analysed":   45,
  "sessions_skipped":     3,
}
"""

from collections import defaultdict
from typing import Optional


_CACHE_TIERS = [
    (0,  20,  "0–20%"),
    (20, 40,  "20–40%"),
    (40, 60,  "40–60%"),
    (60, 80,  "60–80%"),
    (80, 101, "80–100%"),
]

_TASK_ORDER = ["fix", "build", "refactor", "analyze", "test", "deploy", "other"]


def _cache_hit_pct(tokens: dict) -> Optional[float]:
    total = tokens.get("total", 0)
    if not total:
        return None
    cached = tokens.get("cached", 0)
    return round(cached / total * 100, 1)


def _tier_label(pct: float) -> str:
    for lo, hi, label in _CACHE_TIERS:
        if lo <= pct < hi:
            return label
    return "80–100%"


def analyse_cost(sessions: list[dict]) -> dict:
    model_buckets: dict[str, dict] = defaultdict(lambda: {
        "agent": "unknown",
        "costs": [],
        "efficiencies": [],
        "cache_pcts": [],
    })
    task_buckets: dict[str, dict] = defaultdict(lambda: {
        "costs": [],
        "efficiencies": [],
    })
    tier_buckets: dict[str, dict] = defaultdict(lambda: {
        "efficiencies": [],
        "costs": [],
    })

    all_costs: list[float] = []
    all_cache_pcts: list[float] = []

    # For wasteful detection we need (cost, efficiency, session_id, model, task_type)
    scoreable: list[dict] = []

    analysed = 0
    skipped  = 0

    for s in sessions:
        cost = s.get("cost")
        eff  = s.get("efficiency")

        if cost is None or eff is None:
            skipped += 1
            continue
        if cost <= 0 and eff <= 0:
            skipped += 1
            continue

        cost_f = float(cost)
        eff_f  = float(eff)
        model  = s.get("model") or "unknown"
        agent  = s.get("agent") or "unknown"
        task   = s.get("task_type") or "other"
        tok    = s.get("tokens") or {}
        chit   = _cache_hit_pct(tok)

        model_buckets[model]["agent"] = agent
        model_buckets[model]["costs"].append(cost_f)
        model_buckets[model]["efficiencies"].append(eff_f)
        if chit is not None:
            model_buckets[model]["cache_pcts"].append(chit)

        task_buckets[task]["costs"].append(cost_f)
        task_buckets[task]["efficiencies"].append(eff_f)

        if chit is not None:
            tier = _tier_label(chit)
            tier_buckets[tier]["efficiencies"].append(eff_f)
            tier_buckets[tier]["costs"].append(cost_f)
            all_cache_pcts.append(chit)

        all_costs.append(cost_f)

        scoreable.append({
            "session_id": s.get("id"),
            "model":      model,
            "cost":       round(cost_f, 4),
            "efficiency": eff_f,
            "task_type":  task,
        })
        analysed += 1

    # ── by_model ──────────────────────────────────────────────────────────────
    by_model = []
    for model, b in model_buckets.items():
        costs   = b["costs"]
        effs    = b["efficiencies"]
        cpcts   = b["cache_pcts"]
        avg_c   = sum(costs)   / len(costs)
        avg_e   = sum(effs)    / len(effs)
        cpp     = round(avg_c / avg_e, 6) if avg_e > 0 else None
        by_model.append({
            "model":             model,
            "agent":             b["agent"],
            "session_count":     len(costs),
            "avg_cost":          round(avg_c, 4),
            "total_cost":        round(sum(costs), 4),
            "avg_efficiency":    round(avg_e, 1),
            "cost_per_eff_pt":   cpp,
            "avg_cache_hit_pct": round(sum(cpcts) / len(cpcts), 1) if cpcts else None,
        })
    # Sort best-value (lowest cpp) first; models with cpp=None go last
    by_model.sort(key=lambda r: (r["cost_per_eff_pt"] is None, r["cost_per_eff_pt"] or 9999))

    # ── by_task_type ──────────────────────────────────────────────────────────
    by_task: list[dict] = []
    for task, b in task_buckets.items():
        costs = b["costs"]
        effs  = b["efficiencies"]
        avg_c = sum(costs) / len(costs)
        avg_e = sum(effs)  / len(effs)
        cpp   = round(avg_c / avg_e, 6) if avg_e > 0 else None
        by_task.append({
            "task_type":       task,
            "session_count":   len(costs),
            "avg_cost":        round(avg_c, 4),
            "avg_efficiency":  round(avg_e, 1),
            "cost_per_eff_pt": cpp,
        })
    # canonical task order
    order = {t: i for i, t in enumerate(_TASK_ORDER)}
    by_task.sort(key=lambda r: order.get(r["task_type"], 99))

    # ── cache_tiers ───────────────────────────────────────────────────────────
    cache_tiers = []
    for lo, hi, label in _CACHE_TIERS:
        b = tier_buckets.get(label)
        if not b or not b["efficiencies"]:
            continue
        cache_tiers.append({
            "tier":           label,
            "avg_efficiency": round(sum(b["efficiencies"]) / len(b["efficiencies"]), 1),
            "avg_cost":       round(sum(b["costs"]) / len(b["costs"]), 4),
            "session_count":  len(b["efficiencies"]),
        })

    # ── wasteful sessions ─────────────────────────────────────────────────────
    # waste_score = percentile rank of cost minus efficiency (both 0-100 scale)
    if scoreable:
        n   = len(scoreable)
        sorted_costs = sorted(s["cost"] for s in scoreable)
        cost_pct = {c: round(i / max(n - 1, 1) * 100, 1)
                    for i, c in enumerate(sorted_costs)}
        for s in scoreable:
            s["waste_score"] = round(
                cost_pct.get(s["cost"], 0) - s["efficiency"], 1
            )
        wasteful = sorted(scoreable, key=lambda s: -s["waste_score"])[:5]
    else:
        wasteful = []

    # ── aggregates ────────────────────────────────────────────────────────────
    total_cost         = round(sum(all_costs), 4)
    avg_cost_per_sess  = round(total_cost / analysed, 4) if analysed else 0
    avg_cache_hit_pct  = round(sum(all_cache_pcts) / len(all_cache_pcts), 1) if all_cache_pcts else None

    # best_value_model: lowest cpp, >= 2 sessions
    best_value = next(
        (r["model"] for r in by_model if r["cost_per_eff_pt"] is not None and r["session_count"] >= 2),
        None,
    )

    return {
        "by_model":             by_model,
        "by_task_type":         by_task,
        "cache_tiers":          cache_tiers,
        "wasteful":             wasteful,
        "best_value_model":     best_value,
        "total_cost":           total_cost,
        "avg_cost_per_session": avg_cost_per_sess,
        "avg_cache_hit_pct":    avg_cache_hit_pct,
        "sessions_analysed":    analysed,
        "sessions_skipped":     skipped,
    }
