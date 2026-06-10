"""
anomaly.py — Anomaly Detection

Flags sessions that are statistical outliers using z-scores across three
dimensions: cost, efficiency, and token count.

Anomaly types
-------------
  cost_spike        z_cost > 2.0   — session cost far above your norm
  efficiency_crash  z_eff  < -2.0  — session scored far below your norm
  token_overflow    z_tok  > 2.5   — session consumed far more tokens than usual
  waste             cost > 5× median AND efficiency < 10  — expensive and useless

No external dependencies — pure stdlib.
"""

import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional


def _stats(values: list[float]) -> tuple[float, float]:
    """Return (mean, std_dev). Returns (0, 0) if fewer than 2 values."""
    n = len(values)
    if n < 2:
        return (values[0] if values else 0.0), 0.0
    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / n
    return mean, math.sqrt(variance)


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def detect_anomalies(sessions: list[dict]) -> dict:
    """
    Detect outlier sessions and return a feed of anomalies.

    Returns
    -------
    {
      "anomalies": [
        {
          "session_id":  str,
          "agent":       str,
          "model":       str | null,
          "project":     str,
          "timestamp":   str,
          "type":        "cost_spike" | "efficiency_crash" | "token_overflow" | "waste",
          "severity":    "warning" | "critical",
          "value":       float,          # the anomalous metric value
          "baseline":    float,          # mean value for that metric
          "z_score":     float | null,
          "detail":      str,            # human-readable description
        },
        ...                              # sorted by severity then z_score desc
      ],
      "total_anomalies":  int,
      "sessions_checked": int,
      "baseline": {
        "mean_cost":      float,
        "mean_efficiency": float,
        "mean_tokens":    float,
        "median_cost":    float,
      }
    }
    """
    costs  = [float(s["cost"])             for s in sessions if s.get("cost") not in (None, 0)]
    effs   = [float(s["efficiency"])       for s in sessions if s.get("efficiency") is not None]
    tokens = [float((s.get("tokens") or {}).get("total", 0))
              for s in sessions if (s.get("tokens") or {}).get("total", 0) > 0]

    if len(costs) < 3 or len(effs) < 3:
        return {
            "anomalies": [],
            "total_anomalies": 0,
            "sessions_checked": len(sessions),
            "baseline": {},
        }

    mean_c, std_c = _stats(costs)
    mean_e, std_e = _stats(effs)
    mean_t, std_t = _stats(tokens) if len(tokens) >= 3 else (0.0, 0.0)
    median_c      = _median(costs)

    anomalies: list[dict] = []

    for s in sessions:
        sid     = s.get("id", "")
        agent   = s.get("agent", "")
        model   = s.get("model")
        project = s.get("project", "")
        ts      = s.get("timestamp")
        ts_str  = ts.isoformat() if hasattr(ts, "isoformat") else str(ts or "")

        cost  = s.get("cost")
        eff   = s.get("efficiency")
        tok   = (s.get("tokens") or {}).get("total", 0)

        base = dict(session_id=sid, agent=agent, model=model, project=project, timestamp=ts_str)

        # Cost spike
        if cost is not None and float(cost) > 0 and std_c > 0:
            z = (float(cost) - mean_c) / std_c
            if z > 2.0:
                anomalies.append({**base,
                    "type":     "cost_spike",
                    "severity": "critical" if z > 3.0 else "warning",
                    "value":    round(float(cost), 4),
                    "baseline": round(mean_c, 4),
                    "z_score":  round(z, 2),
                    "detail":   f"Cost ${float(cost):.2f} is {z:.1f}σ above your ${mean_c:.2f} mean",
                })

        # Efficiency crash
        if eff is not None and std_e > 0:
            z = (float(eff) - mean_e) / std_e
            if z < -2.0:
                anomalies.append({**base,
                    "type":     "efficiency_crash",
                    "severity": "critical" if z < -3.0 else "warning",
                    "value":    round(float(eff), 1),
                    "baseline": round(mean_e, 1),
                    "z_score":  round(z, 2),
                    "detail":   f"Efficiency {float(eff):.1f} is {abs(z):.1f}σ below your {mean_e:.1f} mean",
                })

        # Token overflow
        if tok > 0 and mean_t > 0 and std_t > 0:
            z = (float(tok) - mean_t) / std_t
            if z > 2.5:
                anomalies.append({**base,
                    "type":     "token_overflow",
                    "severity": "critical" if z > 4.0 else "warning",
                    "value":    int(tok),
                    "baseline": round(mean_t),
                    "z_score":  round(z, 2),
                    "detail":   f"{int(tok):,} tokens is {z:.1f}σ above your {int(mean_t):,} mean",
                })

        # Waste: cost > 5× median AND efficiency < 10
        if cost is not None and float(cost) > 5 * median_c and eff is not None and float(eff) < 10:
            if not any(a["session_id"] == sid and a["type"] == "waste" for a in anomalies):
                anomalies.append({**base,
                    "type":     "waste",
                    "severity": "critical",
                    "value":    round(float(cost), 4),
                    "baseline": round(median_c, 4),
                    "z_score":  None,
                    "detail":   f"${float(cost):.2f} spent for only {float(eff):.1f} efficiency — high cost, no output",
                })

    # Sort: critical first, then by z_score desc (or value for waste)
    def _sort_key(a):
        sev = 0 if a["severity"] == "critical" else 1
        z   = -(a["z_score"] or 0)
        return (sev, z)

    anomalies.sort(key=_sort_key)

    return {
        "anomalies":         anomalies,
        "total_anomalies":   len(anomalies),
        "sessions_checked":  len(sessions),
        "baseline": {
            "mean_cost":       round(mean_c, 4),
            "mean_efficiency": round(mean_e, 1),
            "mean_tokens":     round(mean_t),
            "median_cost":     round(median_c, 4),
        },
    }
