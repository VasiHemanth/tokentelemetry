"""
model_comparison.py — Multi-Model Comparison

Groups sessions by model name and computes efficiency and token statistics,
optionally filtered to a single task type.

No external dependencies — pure stdlib.

Returned per model:
  model              exact model name string from the session
  agent              agent key (claude, codex, copilot, ...)
  session_count      number of sessions with an efficiency score
  avg_efficiency     mean efficiency score (0–100)
  median_efficiency  median efficiency score
  p75_efficiency     75th-percentile efficiency score
  best_efficiency    highest single session score
  total_tokens       sum of all token counts
  avg_tokens         average tokens per session
  task_breakdown     { task_type: { count, avg_efficiency } }
"""

import math
from collections import defaultdict
from typing import Optional


# ── helpers ──────────────────────────────────────────────────────────────────

def _median(vals: list[float]) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def _percentile(vals: list[float], p: float) -> float:
    """Return the p-th percentile of vals (0–100). Linear interpolation."""
    if not vals:
        return 0.0
    s = sorted(vals)
    n = len(s)
    idx = (p / 100.0) * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return s[lo] + frac * (s[hi] - s[lo])


# ── main ─────────────────────────────────────────────────────────────────────

_TASK_ORDER = ["fix", "build", "refactor", "analyze", "test", "deploy", "other"]


def compare_models(
    sessions: list[dict],
    task_type: Optional[str] = None,
) -> dict:
    """
    Compute per-model efficiency stats.

    Parameters
    ----------
    sessions   : list of session dicts (already enriched with efficiency + task_type)
    task_type  : if provided, restrict to sessions whose task_type matches

    Returns
    -------
    {
      "task_type_filter": str | null,
      "models_compared":  int,
      "sessions_used":    int,
      "sessions_skipped": int,
      "models": [
        {
          "model":           str,
          "agent":           str,
          "session_count":   int,
          "avg_efficiency":  float,
          "median_efficiency": float,
          "p75_efficiency":  float,
          "best_efficiency": float,
          "total_tokens":    int,
          "avg_tokens":      int,
          "task_breakdown":  { task_type: { "count": int, "avg_efficiency": float } }
        },
        ...                             # sorted by avg_efficiency descending
      ],
      "task_types_available": [str]     # all task types seen in the full dataset
    }
    """
    # Collect all task types before filtering
    all_task_types: set[str] = set()
    for s in sessions:
        tt = s.get("task_type") or "other"
        all_task_types.add(tt)

    task_types_available = [t for t in _TASK_ORDER if t in all_task_types] + \
                           sorted(all_task_types - set(_TASK_ORDER))

    # Buckets: model_name → { agent, efficiency_scores, token_counts, task_buckets }
    buckets: dict[str, dict] = {}
    sessions_used = 0
    sessions_skipped = 0

    for s in sessions:
        model = s.get("model")
        if not model:
            sessions_skipped += 1
            continue

        eff = s.get("efficiency")
        if eff is None:
            sessions_skipped += 1
            continue

        tt = s.get("task_type") or "other"
        if task_type and task_type != "all" and tt != task_type:
            sessions_skipped += 1
            continue

        sessions_used += 1
        if model not in buckets:
            buckets[model] = {
                "agent":      s.get("agent", "unknown"),
                "efficiency": [],
                "tokens":     [],
                "tasks":      defaultdict(list),
            }
        b = buckets[model]
        b["efficiency"].append(float(eff))
        b["tokens"].append(int(s.get("tokens", {}).get("total", 0) if s.get("tokens") else 0))
        b["tasks"][tt].append(float(eff))

    if not buckets:
        return {
            "task_type_filter":      task_type,
            "models_compared":       0,
            "sessions_used":         sessions_used,
            "sessions_skipped":      sessions_skipped,
            "models":                [],
            "task_types_available":  task_types_available,
            "note": "No sessions with both a model name and an efficiency score found.",
        }

    models = []
    for model, b in buckets.items():
        scores = b["efficiency"]
        tokens = b["tokens"]
        task_breakdown = {}
        for tt, effs in sorted(b["tasks"].items()):
            task_breakdown[tt] = {
                "count":          len(effs),
                "avg_efficiency": round(sum(effs) / len(effs), 1),
            }

        models.append({
            "model":             model,
            "agent":             b["agent"],
            "session_count":     len(scores),
            "avg_efficiency":    round(sum(scores) / len(scores), 1),
            "median_efficiency": round(_median(scores), 1),
            "p75_efficiency":    round(_percentile(scores, 75), 1),
            "best_efficiency":   round(max(scores), 1),
            "total_tokens":      sum(tokens),
            "avg_tokens":        round(sum(tokens) / len(tokens)) if tokens else 0,
            "task_breakdown":    task_breakdown,
        })

    models.sort(key=lambda m: -m["avg_efficiency"])

    return {
        "task_type_filter":     task_type,
        "models_compared":      len(models),
        "sessions_used":        sessions_used,
        "sessions_skipped":     sessions_skipped,
        "models":               models,
        "task_types_available": task_types_available,
    }
