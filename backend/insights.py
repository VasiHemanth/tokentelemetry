"""Local-model insight helpers: energy, cloud savings, efficiency, session enrich.

Used by ``GET /analytics`` and session-list enrichment. Never raises on bad input
— callers get zeros / None so a malformed session can't break the dashboard.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


def energy_wh(
    output_tokens: int,
    *,
    load_watts: float,
    tok_per_sec: float,
) -> float:
    """Compute energy consumed in watt-hours for generating tokens locally."""
    if output_tokens <= 0 or load_watts <= 0 or tok_per_sec <= 0:
        return 0.0
    # Wh = (output_tokens / tok_per_sec) * load_watts / 3600
    gen_seconds = output_tokens / tok_per_sec
    return (gen_seconds * load_watts) / 3600.0


def gen_seconds(output_tokens: int, tok_per_sec: float) -> float:
    """Wall-clock generation seconds from output tokens and throughput."""
    if output_tokens <= 0 or tok_per_sec <= 0:
        return 0.0
    return output_tokens / tok_per_sec


def cloud_equiv_cost(
    model_reference: str,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
) -> float:
    """Compute the equivalent cost on a reference cloud model."""
    from pricing import calculate_cost
    # No provider/endpoint/billing_mode so the cloud pricing table always wins.
    return calculate_cost(
        model_name=model_reference,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        provider=None,
        endpoint=None,
        billing_mode=None,
    )


def savings_vs_cloud(local_cost: float, cloud_cost: float) -> float:
    """Compute USD savings of local generation vs cloud, clamped at 0."""
    return max(0.0, cloud_cost - local_cost)


def wh_per_1m_tokens(energy_wh_total: float, output_tokens: int) -> Optional[float]:
    """Energy efficiency: watt-hours per 1M output tokens. None if no output."""
    if output_tokens <= 0 or energy_wh_total < 0:
        return None
    return (energy_wh_total / output_tokens) * 1_000_000.0


def cost_per_1m_tokens(cost_usd: float, output_tokens: int) -> Optional[float]:
    """Electricity USD per 1M output tokens. None if no output."""
    if output_tokens <= 0 or cost_usd < 0:
        return None
    return (cost_usd / output_tokens) * 1_000_000.0


def resolve_tok_per_sec(
    measured: Optional[float],
    model: Optional[str],
) -> Tuple[float, str]:
    """Return (tok_per_sec, source) where source is 'measured' or 'estimated'."""
    if isinstance(measured, (int, float)) and not isinstance(measured, bool) and measured > 0:
        return float(measured), "measured"
    from power_config import default_tok_per_sec_for_model
    return float(default_tok_per_sec_for_model(model)), "estimated"


def tok_per_sec_from_duration(
    output_tokens: int,
    duration_ms: Optional[float],
    *,
    min_ms: float = 50.0,
) -> Optional[float]:
    """Derive tok/s from wall-clock duration. None when inputs are unusable.

    ``min_ms`` rejects near-zero durations that would explode the rate.
    Whole-session duration includes tool time, so this is a lower bound on
    pure-decode speed — still better than a size heuristic when present.
    """
    if output_tokens <= 0 or duration_ms is None:
        return None
    try:
        ms = float(duration_ms)
    except (TypeError, ValueError):
        return None
    if ms < min_ms:
        return None
    return output_tokens / (ms / 1000.0)


def local_metrics_for_session(
    session: Dict[str, Any],
    *,
    config: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Build a local-insight payload for one session, or None if not local.

    Keys: is_local, tok_per_sec, tok_per_sec_source, gen_seconds, energy_wh,
    co2_g, electricity_cost, cloud_equiv_cost, savings_usd, wh_per_1m_output,
    cost_per_1m_output, load_watts, reference_cloud_model.
    """
    from power_config import (
        is_local_session,
        load_power_config,
        co2_for_session,
        electricity_cost,
    )

    if config is None:
        config = load_power_config()

    model = session.get("model")
    if not is_local_session(
        model_name=model,
        endpoint=session.get("endpoint"),
        provider=session.get("provider"),
        billing_mode=session.get("billing_mode"),
        config=config,
    ):
        return None

    tokens = session.get("tokens") or {}
    out_tok = int(tokens.get("output") or 0)
    in_tok = int(tokens.get("input") or 0)
    cached = int(tokens.get("cached") or 0)
    tps, tps_src = resolve_tok_per_sec(session.get("tok_per_sec"), model)
    load_watts = float(config.get("loadWatts") or 0)
    e_wh = energy_wh(out_tok, load_watts=load_watts, tok_per_sec=tps)
    e_cost = electricity_cost(out_tok, config=config, tok_per_sec=tps)
    # Prefer the session's already-computed local cost when present (scan path).
    local_cost = session.get("cost")
    if not isinstance(local_cost, (int, float)) or local_cost < 0:
        local_cost = e_cost
    else:
        local_cost = float(local_cost)
    ref = config.get("referenceCloudModel") or "claude-sonnet-4-6"
    cloud = cloud_equiv_cost(ref, in_tok, out_tok, cached)
    savings = savings_vs_cloud(local_cost, cloud)
    co2 = co2_for_session(out_tok, config=config, tok_per_sec=tps)
    return {
        "is_local": True,
        "tok_per_sec": round(tps, 3),
        "tok_per_sec_source": tps_src,
        "gen_seconds": round(gen_seconds(out_tok, tps), 3),
        "energy_wh": round(e_wh, 6),
        "co2_g": round(co2, 6),
        "electricity_cost": round(e_cost, 8),
        "cloud_equiv_cost": round(cloud, 6),
        "savings_usd": round(savings, 6),
        "wh_per_1m_output": (
            round(wh_per_1m_tokens(e_wh, out_tok), 4)
            if out_tok > 0 else None
        ),
        "cost_per_1m_output": (
            round(cost_per_1m_tokens(local_cost, out_tok), 6)
            if out_tok > 0 else None
        ),
        "load_watts": load_watts,
        "reference_cloud_model": ref,
    }


def efficiency_row(
    *,
    output_tokens: int,
    energy_wh_total: float,
    cost_usd: float,
    tok_per_sec_sum: float,
    tok_per_sec_n: int,
) -> Dict[str, Any]:
    """Aggregate efficiency fields for a model/agent bucket."""
    avg_tps = (tok_per_sec_sum / tok_per_sec_n) if tok_per_sec_n > 0 else None
    return {
        "wh_per_1m_output": (
            round(wh_per_1m_tokens(energy_wh_total, output_tokens), 4)
            if output_tokens > 0 else None
        ),
        "cost_per_1m_output": (
            round(cost_per_1m_tokens(cost_usd, output_tokens), 6)
            if output_tokens > 0 else None
        ),
        "avg_tok_per_sec": round(avg_tps, 3) if avg_tps is not None else None,
        "tok_per_sec_samples": tok_per_sec_n,
    }
