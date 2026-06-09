from insights import energy_wh, cloud_equiv_cost, savings_vs_cloud

def test_energy_wh():
    # 3600 tokens at 30 tok/s = 120 seconds. 120s * 80W / 3600s/h = 2.666... Wh
    result = energy_wh(3600, load_watts=80, tok_per_sec=30)
    assert abs(result - 2.666666) < 1e-5

    # Edge cases
    assert energy_wh(0, load_watts=80, tok_per_sec=30) == 0.0
    assert energy_wh(100, load_watts=0, tok_per_sec=30) == 0.0
    assert energy_wh(100, load_watts=80, tok_per_sec=0) == 0.0

def test_cloud_equiv_cost():
    # Test that it successfully prices at cloud rates for the reference model
    # e.g., claude-sonnet-4-6 -> $3.00/1M in, $15.00/1M out
    cost = cloud_equiv_cost(
        "claude-sonnet-4-6",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cached_tokens=0
    )
    # Should be exactly 18.00
    assert cost == 18.0

def test_savings_vs_cloud():
    # Basic positive savings
    assert savings_vs_cloud(local_cost=1.0, cloud_cost=5.0) == 4.0
    # Negative savings clamped at 0
    assert savings_vs_cloud(local_cost=5.0, cloud_cost=1.0) == 0.0
    # Zero difference
    assert savings_vs_cloud(local_cost=1.0, cloud_cost=1.0) == 0.0
