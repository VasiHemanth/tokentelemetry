"""
scoring.py — Agent Efficiency Score

Computes a 0–100 score for a session based on how productively
tokens were used. Higher = more output per token, fewer errors, fewer turns.

Formula:
  output_ratio  = output_tokens / total_tokens      (more output = productive)
  error_penalty = 1 / (1 + errors * 0.15)           (errors hurt)
  turn_penalty  = 1 / (1 + log1p(turns) * 0.18)     (fewer turns = clearer prompts)
  score = output_ratio * error_penalty * turn_penalty * 100
"""

import math
from typing import Optional


def efficiency_score(
    input_tokens: int,
    output_tokens: int,
    total_tokens: int,
    turns: int,
    error_count: int,
) -> Optional[float]:
    """
    Returns a 0.0–100.0 efficiency score, or None if there is not enough data.
    """
    if total_tokens <= 0 or output_tokens < 0:
        return None

    output_ratio  = output_tokens / total_tokens
    error_penalty = 1.0 / (1.0 + max(error_count, 0) * 0.15)
    turn_penalty  = 1.0 / (1.0 + math.log1p(max(turns, 1)) * 0.18)

    raw = output_ratio * error_penalty * turn_penalty * 100.0
    return round(min(max(raw, 0.0), 100.0), 1)


def score_label(score: Optional[float]) -> str:
    """Human-readable label for the score."""
    if score is None:
        return "unknown"
    if score >= 70:
        return "good"
    if score >= 40:
        return "fair"
    return "poor"


def score_session(session: dict) -> Optional[float]:
    """Convenience wrapper — pass a raw session dict from main.py."""
    tokens = session.get("tokens") or {}
    return efficiency_score(
        input_tokens  = tokens.get("input", 0) or 0,
        output_tokens = tokens.get("output", 0) or 0,
        total_tokens  = tokens.get("total", 0) or 0,
        turns         = session.get("turns", 1) or 1,
        error_count   = session.get("error_count", 0) or 0,
    )
