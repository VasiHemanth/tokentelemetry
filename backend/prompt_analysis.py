"""
prompt_analysis.py — Prompt DNA

Extracts structural and semantic features from session prompts and
correlates them with efficiency scores to surface what makes sessions
good or bad.

No external dependencies — pure stdlib.

Features extracted per session:
  msg_length        character count of first message
  word_count        approximate word count
  has_file_ref      @ mentions or path strings
  has_code_block    triple-backtick fenced code
  has_markdown      # headers or bullet lists
  has_numbered_steps   lines like "1. ", "2. "
  has_question      ends with ?
  is_vague          very short (< 60 chars), no file refs
  is_detailed       > 300 chars
  has_context_link  references previous session / last time / above
  task_type         build | fix | analyze | refactor | explain | review | other
"""

import re
import math
from typing import Optional


# ── Task type patterns ───────────────────────────────────────────────────────

_TASK_PATTERNS: list[tuple[str, str]] = [
    ("fix",      r"\b(fix|bug|error|crash|broken|issue|wrong|fail|not work)\b"),
    ("build",    r"\b(build|create|make|implement|add|write|develop|set up|setup|generate)\b"),
    ("refactor", r"\b(refactor|clean|improve|optimis|optimiz|restructure|rewrite|simplif)\b"),
    ("analyze",  r"\b(analyz|analyse|review|check|inspect|audit|understand|explain|why|how does)\b"),
    ("test",     r"\b(test|spec|coverage|unit test|integration|e2e|assert)\b"),
    ("deploy",   r"\b(deploy|release|publish|ship|push|ci|cd|pipeline)\b"),
]


def classify_task(text: str) -> str:
    """Return the dominant task type for a message."""
    lower = text.lower()
    for task, pattern in _TASK_PATTERNS:
        if re.search(pattern, lower):
            return task
    return "other"


# ── Feature extraction ───────────────────────────────────────────────────────

def extract_features(msg: str) -> dict:
    """Extract a dict of boolean / numeric features from a prompt string."""
    if not msg or not msg.strip():
        return _empty_features()

    msg = msg.strip()
    lower = msg.lower()

    msg_length   = len(msg)
    word_count   = len(msg.split())

    has_file_ref      = bool(re.search(r'[@\\\/][^\s]{3,}', msg) or
                              re.search(r'\b\w+\.\w{2,4}\b', msg))
    has_code_block    = "```" in msg
    has_markdown      = bool(re.search(r'^#{1,3}\s', msg, re.MULTILINE) or
                              re.search(r'^[-*]\s', msg, re.MULTILINE))
    has_numbered_steps = bool(re.search(r'^\d+[\.\)]\s', msg, re.MULTILINE))
    has_question      = msg.rstrip().endswith("?")
    is_vague          = msg_length < 60 and not has_file_ref and not has_code_block
    is_detailed       = msg_length > 300
    has_context_link  = bool(re.search(
        r'\b(previous|last session|last time|above|earlier|follow.?up|continue|handoff)\b',
        lower
    ))

    return {
        "msg_length":        msg_length,
        "word_count":        word_count,
        "has_file_ref":      int(has_file_ref),
        "has_code_block":    int(has_code_block),
        "has_markdown":      int(has_markdown),
        "has_numbered_steps": int(has_numbered_steps),
        "has_question":      int(has_question),
        "is_vague":          int(is_vague),
        "is_detailed":       int(is_detailed),
        "has_context_link":  int(has_context_link),
        "task_type":         classify_task(msg),
    }


def _empty_features() -> dict:
    return {
        "msg_length": 0, "word_count": 0,
        "has_file_ref": 0, "has_code_block": 0, "has_markdown": 0,
        "has_numbered_steps": 0, "has_question": 0,
        "is_vague": 0, "is_detailed": 0, "has_context_link": 0,
        "task_type": "other",
    }


# ── Pearson correlation (no scipy) ────────────────────────────────────────────

def _pearson(xs: list[float], ys: list[float]) -> float:
    """Return Pearson r for two equal-length lists. Returns 0 if undefined."""
    n = len(xs)
    if n < 3:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num   = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - mx) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - my) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return 0.0
    return num / (den_x * den_y)


# ── Main analysis ─────────────────────────────────────────────────────────────

_NUMERIC_FEATURES = [
    "msg_length", "word_count", "has_file_ref", "has_code_block",
    "has_markdown", "has_numbered_steps", "has_question",
    "is_vague", "is_detailed", "has_context_link",
]

_FEATURE_LABELS = {
    "msg_length":        "Long prompt",
    "word_count":        "High word count",
    "has_file_ref":      "References a file or path",
    "has_code_block":    "Includes a code block",
    "has_markdown":      "Uses markdown headers/bullets",
    "has_numbered_steps": "Uses numbered steps",
    "has_question":      "Ends with a question",
    "is_vague":          "Vague / short prompt",
    "is_detailed":       "Detailed prompt (>300 chars)",
    "has_context_link":  "References a previous session",
}


def analyse_prompt_dna(sessions: list[dict]) -> dict:
    """
    Run Prompt DNA analysis over a list of sessions.

    Returns:
    {
      "sessions_analysed": int,
      "sessions_skipped":  int,     # no prompt text or no efficiency score
      "correlations": [             # sorted by |r|, strongest first
        { "feature": str, "label": str, "r": float,
          "direction": "positive"|"negative",
          "insight": str }
      ],
      "by_task_type": {             # avg efficiency per task type
        "build": { "avg_efficiency": float, "count": int },
        ...
      },
      "top_positive":  [...],       # top 3 positive correlates
      "top_negative":  [...],       # top 3 negative correlates
    }
    """
    rows: list[tuple[dict, float]] = []

    for s in sessions:
        score = s.get("efficiency")
        if score is None:
            continue
        msg = (s.get("display") or s.get("text") or "").strip()
        if not msg:
            continue
        rows.append((extract_features(msg), score))

    skipped = len(sessions) - len(rows)

    if len(rows) < 3:
        return {
            "sessions_analysed": len(rows),
            "sessions_skipped":  skipped,
            "correlations":      [],
            "by_task_type":      {},
            "top_positive":      [],
            "top_negative":      [],
            "note": "Not enough sessions with both a prompt and an efficiency score to compute correlations (need ≥ 3).",
        }

    # Compute Pearson r for each numeric feature vs efficiency
    efficiency_vals = [r for _, r in rows]
    correlations = []
    for feat in _NUMERIC_FEATURES:
        feat_vals = [f[feat] for f, _ in rows]
        r = round(_pearson(feat_vals, efficiency_vals), 3)
        if abs(r) < 0.05:          # ignore noise
            continue
        direction = "positive" if r > 0 else "negative"
        label = _FEATURE_LABELS[feat]
        insight = _make_insight(feat, r, rows)
        correlations.append({
            "feature":   feat,
            "label":     label,
            "r":         r,
            "direction": direction,
            "insight":   insight,
        })

    correlations.sort(key=lambda x: -abs(x["r"]))

    # Per-task-type breakdown
    task_buckets: dict[str, list[float]] = {}
    for feats, score in rows:
        tt = feats["task_type"]
        task_buckets.setdefault(tt, []).append(score)

    by_task_type = {
        tt: {
            "avg_efficiency": round(sum(scores) / len(scores), 1),
            "count":          len(scores),
        }
        for tt, scores in sorted(task_buckets.items(), key=lambda x: -sum(x[1]) / len(x[1]))
    }

    top_positive = [c for c in correlations if c["direction"] == "positive"][:3]
    top_negative = [c for c in correlations if c["direction"] == "negative"][:3]

    return {
        "sessions_analysed": len(rows),
        "sessions_skipped":  skipped,
        "correlations":      correlations,
        "by_task_type":      by_task_type,
        "top_positive":      top_positive,
        "top_negative":      top_negative,
    }


def _make_insight(feat: str, r: float, rows: list[tuple[dict, float]]) -> str:
    """Generate a one-line human insight for a feature correlation."""
    present   = [score for feats, score in rows if feats[feat]]
    absent    = [score for feats, score in rows if not feats[feat]]
    avg_p = sum(present) / len(present) if present else 0
    avg_a = sum(absent)  / len(absent)  if absent  else 0
    diff  = abs(avg_p - avg_a)
    label = _FEATURE_LABELS[feat]

    if r > 0:
        return (
            f"Sessions with '{label.lower()}' score {diff:.1f} pts higher on average "
            f"({avg_p:.1f} vs {avg_a:.1f})."
        )
    else:
        return (
            f"Sessions with '{label.lower()}' score {diff:.1f} pts lower on average "
            f"({avg_p:.1f} vs {avg_a:.1f})."
        )
