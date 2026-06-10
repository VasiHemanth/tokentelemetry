"""
recommendations.py — AI Recommendations Engine

Cross-references all intelligence modules (cost, time, prompt DNA, smells,
tool footprint, trends) to generate specific, actionable text recommendations.

Each recommendation has:
  category  — cost | quality | timing | prompt | tools | health
  priority  — high | medium | low
  title     — short headline
  detail    — actionable sentence with concrete numbers
  impact    — estimated efficiency gain or cost saving (if computable)

No external dependencies — pure stdlib.
"""

from collections import defaultdict
from typing import Optional

# Lazy imports at call time to avoid circular deps
def _run_analysis(sessions: list[dict]) -> dict:
    from prompt_analysis   import analyse_prompt_dna, extract_features
    from model_comparison  import compare_models
    from cost_intel        import analyse_cost
    from time_intel        import analyse_time
    from tool_footprint    import analyse_tool_footprint
    from trends            import compute_trends
    from smells            import detect_smells

    # Attach features / smells if not already on the sessions
    enriched = []
    for s in sessions:
        s2 = dict(s)
        if "task_type" not in s2 or "prompt_features" not in s2:
            try:
                feats = extract_features(s2)
                s2["task_type"]       = feats.pop("task_type", s2.get("task_type", "other"))
                s2["prompt_features"] = feats
            except Exception:
                pass
        if "smells" not in s2:
            try:
                s2["smells"] = detect_smells(s2)
            except Exception:
                s2["smells"] = []
        enriched.append(s2)

    return {
        "dna":   analyse_prompt_dna(enriched),
        "cost":  analyse_cost(enriched),
        "time":  analyse_time(enriched),
        "tools": analyse_tool_footprint(enriched),
        "trend": compute_trends(enriched, days=30),
        "model": compare_models(enriched),
        "sessions": enriched,
    }


def generate_recommendations(sessions: list[dict]) -> dict:
    """
    Generate actionable recommendations by cross-referencing all modules.

    Returns
    -------
    {
      "recommendations": [
        {
          "id":       str,                  # stable slug
          "category": "cost"|"quality"|"timing"|"prompt"|"tools"|"health",
          "priority": "high"|"medium"|"low",
          "title":    str,
          "detail":   str,
          "impact":   str | null,           # e.g. "Save ~$8/session" or "+12 pts efficiency"
        },
        ...                                 # sorted by priority (high first)
      ],
      "total":         int,
      "high_count":    int,
      "medium_count":  int,
      "low_count":     int,
    }
    """
    if len(sessions) < 5:
        return {"recommendations": [], "total": 0, "high_count": 0, "medium_count": 0, "low_count": 0}

    try:
        data = _run_analysis(sessions)
    except Exception:
        return {"recommendations": [], "total": 0, "high_count": 0, "medium_count": 0, "low_count": 0}

    recs: list[dict] = []

    def add(id_, category, priority, title, detail, impact=None):
        recs.append(dict(id=id_, category=category, priority=priority,
                         title=title, detail=detail, impact=impact))

    # ── Cost recommendations ───────────────────────────────────────────────
    cost_data  = data["cost"]
    by_model   = cost_data.get("by_model", [])
    valid_models = [m for m in by_model if m.get("cost_per_eff_pt") and m["session_count"] >= 2]

    if len(valid_models) >= 2:
        best  = valid_models[0]
        worst = valid_models[-1]
        ratio = (worst["cost_per_eff_pt"] or 1) / (best["cost_per_eff_pt"] or 1)
        if ratio >= 5:
            saving = round((worst["avg_cost"] - best["avg_cost"]), 2)
            add("cost_model_switch", "cost", "high",
                f"Replace {worst['model']} — {ratio:.0f}× worse value",
                f"{worst['model']} costs ${worst['cost_per_eff_pt']:.3f}/eff-pt vs "
                f"${best['cost_per_eff_pt']:.3f}/eff-pt for {best['model']}. "
                f"Switch for similar tasks to save ~${abs(saving):.2f}/session.",
                impact=f"Save ~${abs(saving):.2f}/session" if saving > 0 else None)

    wasteful = cost_data.get("wasteful", [])
    if len(wasteful) >= 3:
        models_wasted = list({w["model"] for w in wasteful[:3]})
        total_wasted  = sum(w["cost"] for w in wasteful[:5])
        add("cost_wasteful", "cost", "high" if total_wasted > 20 else "medium",
            f"${total_wasted:.2f} spent on low-efficiency sessions",
            f"Your top 5 expensive flops (avg efficiency {sum(w['efficiency'] for w in wasteful[:5])/5:.1f}) "
            f"cost ${total_wasted:.2f} total. "
            f"Review what went wrong in these {', '.join(models_wasted[:2])} sessions.",
            impact=f"Recover ~${total_wasted:.2f}")

    cache_tiers = cost_data.get("cache_tiers", [])
    high_cache  = next((t for t in cache_tiers if "80" in t["tier"]), None)
    low_cache   = next((t for t in cache_tiers if "0–20" in t["tier"] or "0-20" in t["tier"]), None)
    if high_cache and low_cache and low_cache["avg_efficiency"] > high_cache["avg_efficiency"] + 15:
        add("cost_cache_insight", "cost", "low",
            "Low-cache sessions score higher — they're your deep work",
            f"Sessions with 0–20% cache hit average {low_cache['avg_efficiency']:.0f} efficiency "
            f"vs {high_cache['avg_efficiency']:.0f} for 80–100% cached. "
            f"High-cache sessions are likely quick edits — optimise deep work sessions for quality.",
            impact=None)

    # ── Quality / prompt recommendations ──────────────────────────────────
    dna = data["dna"]
    top_neg = dna.get("top_negative", [])
    top_pos = dna.get("top_positive", [])

    for feat in top_neg[:2]:
        r_abs = abs(feat.get("r", 0))
        if r_abs >= 0.3:
            impact_pts = round(r_abs * 50)
            add(f"prompt_avoid_{feat['feature']}", "prompt",
                "high" if r_abs >= 0.5 else "medium",
                f"Avoid '{feat['label']}' prompts",
                feat.get("insight", f"Sessions with '{feat['label']}' score lower on efficiency."),
                impact=f"+{impact_pts} pts efficiency on average")

    for feat in top_pos[:1]:
        r_abs = abs(feat.get("r", 0))
        if r_abs >= 0.3:
            add(f"prompt_boost_{feat['feature']}", "prompt", "medium",
                f"More '{feat['label']}' prompts",
                feat.get("insight", f"Sessions with '{feat['label']}' score higher."),
                impact=f"+{round(r_abs * 40)} pts efficiency")

    # ── Timing recommendations ─────────────────────────────────────────────
    time_data  = data["time"]
    peak_hour  = time_data.get("peak_hour")
    worst_hour = time_data.get("worst_hour")
    overall_eff = dna.get("sessions_analysed") and None  # placeholder
    sessions_list = data["sessions"]
    all_effs = [float(s["efficiency"]) for s in sessions_list if s.get("efficiency") is not None]
    overall_avg = round(sum(all_effs) / len(all_effs), 1) if all_effs else 50

    if peak_hour and peak_hour["session_count"] >= 2:
        diff = peak_hour["avg_efficiency"] - overall_avg
        if diff >= 15:
            add("timing_peak_hour", "timing", "medium",
                f"Schedule deep work at {peak_hour['label']}",
                f"Sessions starting at {peak_hour['label']} average {peak_hour['avg_efficiency']:.1f} efficiency "
                f"— {diff:.0f} pts above your {overall_avg:.1f} overall mean. "
                f"Block this time for complex tasks.",
                impact=f"+{diff:.0f} pts efficiency")

    if worst_hour and worst_hour["session_count"] >= 2 and worst_hour["avg_efficiency"] < 20:
        add("timing_avoid_hour", "timing", "low",
            f"Avoid starting sessions at {worst_hour['label']}",
            f"Sessions at {worst_hour['label']} average only {worst_hour['avg_efficiency']:.1f} efficiency. "
            f"Consider wrapping up rather than starting new tasks at this hour.",
            impact=None)

    peak_dow = time_data.get("peak_dow")
    worst_dow = time_data.get("worst_dow")
    if peak_dow and peak_dow["session_count"] >= 2 and worst_dow and worst_dow["session_count"] >= 2:
        diff = peak_dow["avg_efficiency"] - worst_dow["avg_efficiency"]
        if diff >= 20:
            add("timing_best_day", "timing", "low",
                f"{peak_dow['label']} is your best day (+{diff:.0f} pts over {worst_dow['label']})",
                f"{peak_dow['label']} sessions average {peak_dow['avg_efficiency']:.1f} vs "
                f"{worst_dow['avg_efficiency']:.1f} on {worst_dow['label']}.",
                impact=None)

    # ── Tool recommendations ───────────────────────────────────────────────
    tools_data   = data["tools"]
    by_size      = tools_data.get("by_size", [])
    optimal_range = tools_data.get("optimal_range")

    if len(by_size) >= 2:
        lean    = next((b for b in by_size if b["label"] == "lean"),    None)
        bloated = next((b for b in by_size if b["label"] == "bloated"), None)
        heavy   = next((b for b in by_size if b["label"] == "heavy"),   None)
        best_sz = max(by_size, key=lambda b: b["avg_efficiency"])
        worst_sz = min(by_size, key=lambda b: b["avg_efficiency"])
        diff = best_sz["avg_efficiency"] - worst_sz["avg_efficiency"]
        if diff >= 20 and best_sz["bucket"] != worst_sz["bucket"]:
            add("tools_optimal_size", "tools", "medium",
                f"Optimal toolset size: {best_sz['bucket']} tools ({best_sz['label']})",
                f"Sessions with {best_sz['bucket']} tools average {best_sz['avg_efficiency']:.1f} efficiency "
                f"vs {worst_sz['avg_efficiency']:.1f} for {worst_sz['bucket']} — "
                f"a {diff:.0f}-pt gap. Aim for {best_sz['label']} tool configurations.",
                impact=f"+{diff:.0f} pts efficiency")

    # ── Health / trend recommendations ─────────────────────────────────────
    trend_data = data["trend"]
    trend = trend_data.get("trend")
    delta = trend_data.get("trend_delta", 0)

    if trend == "declining" and delta <= -10:
        add("health_declining", "health", "high",
            f"Efficiency declining — down {abs(delta):.1f} pts week-over-week",
            f"Your 7-day average has dropped {abs(delta):.1f} pts vs the prior week. "
            f"Review recent sessions for common smell patterns (context rot, loop traps).",
            impact=None)
    elif trend == "improving" and delta >= 10:
        add("health_improving", "health", "low",
            f"Efficiency improving — up {delta:.1f} pts week-over-week",
            f"Your recent sessions average {delta:.1f} pts higher than the prior week. "
            f"Keep up the current patterns.",
            impact=f"+{delta:.1f} pts WoW")

    # ── Smell recommendations ──────────────────────────────────────────────
    from smells import detect_smells as _detect_smells
    smell_counts: dict[str, int] = defaultdict(int)
    for s in sessions:
        for sm in (s.get("smells") or []):
            smell_counts[sm.get("type", "")] += 1

    if smell_counts:
        top_smell, top_count = max(smell_counts.items(), key=lambda x: x[1])
        pct = round(top_count / max(len(sessions), 1) * 100)
        smell_labels = {
            "context_rot":   "Context rot — sessions accumulating too much old context",
            "loop_trap":     "Loop traps — repeated similar patterns without progress",
            "tool_thrash":   "Tool thrash — excessive tool retries",
            "high_error":    "High error rate",
            "massive_session": "Oversized sessions",
        }
        if pct >= 20:
            add(f"smell_{top_smell}", "health", "medium",
                f"{smell_labels.get(top_smell, top_smell)} in {pct}% of sessions",
                f"'{smell_labels.get(top_smell, top_smell)}' was detected in {top_count} of your "
                f"{len(sessions)} sessions ({pct}%). This pattern correlates with lower efficiency.",
                impact=None)

    # Sort: high → medium → low
    priority_order = {"high": 0, "medium": 1, "low": 2}
    recs.sort(key=lambda r: priority_order.get(r["priority"], 3))

    counts = {"high": 0, "medium": 0, "low": 0}
    for r in recs:
        counts[r["priority"]] = counts.get(r["priority"], 0) + 1

    return {
        "recommendations": recs,
        "total":        len(recs),
        "high_count":   counts["high"],
        "medium_count": counts["medium"],
        "low_count":    counts["low"],
    }
