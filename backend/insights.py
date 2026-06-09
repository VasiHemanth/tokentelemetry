from typing import Optional

def energy_wh(
    output_tokens: int,
    *,
    load_watts: float,
    tok_per_sec: float
) -> float:
    """Compute energy consumed in watt-hours for generating tokens locally."""
    if output_tokens <= 0 or load_watts <= 0 or tok_per_sec <= 0:
        return 0.0
    # Wh = (output_tokens / tok_per_sec) * load_watts / 3600
    gen_seconds = output_tokens / tok_per_sec
    return (gen_seconds * load_watts) / 3600.0

def cloud_equiv_cost(
    model_reference: str,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0
) -> float:
    """Compute the equivalent cost on a reference cloud model."""
    from pricing import calculate_cost
    # Calculate cost using the reference model and no endpoint/provider to ensure cloud rates.
    return calculate_cost(
        model_name=model_reference,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        provider=None,
        endpoint=None,
        billing_mode=None
    )

def savings_vs_cloud(
    local_cost: float,
    cloud_cost: float
) -> float:
    """Compute USD savings of local generation vs cloud, clamped at 0."""
    savings = cloud_cost - local_cost
    return max(0.0, savings)
