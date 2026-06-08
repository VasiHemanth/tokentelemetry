import pytest
from power_config import (
    co2_grams,
    co2_for_session,
    load_power_config,
    save_power_config,
    MAX_CARBON_INTENSITY,
    DEFAULT_CARBON_INTENSITY,
)

def test_co2_grams_formula():
    # 1 kWh * 400 g/kWh = 400g
    assert co2_grams(1.0, intensity=400.0) == 400.0
    # 0.5 kWh * 100 g/kWh = 50g
    assert co2_grams(0.5, intensity=100.0) == 50.0
    # negative inputs return 0
    assert co2_grams(-1.0, intensity=400.0) == 0.0
    assert co2_grams(1.0, intensity=-100.0) == 0.0

def test_co2_intensity_validation(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKENTELEMETRY_HOME", str(tmp_path))
    
    # Save a valid intensity
    cfg = save_power_config({"gridCarbonIntensity": 500})
    assert cfg["gridCarbonIntensity"] == 500
    
    # Save an invalid (over ceiling) intensity - should be ignored
    cfg = save_power_config({"gridCarbonIntensity": MAX_CARBON_INTENSITY + 1})
    assert cfg["gridCarbonIntensity"] == 500  # Remains 500
    
    # Save a garbage intensity - should be ignored
    cfg = save_power_config({"gridCarbonIntensity": "garbage"})
    assert cfg["gridCarbonIntensity"] == 500

def test_co2_for_session_local(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKENTELEMETRY_HOME", str(tmp_path))
    save_power_config({"loadWatts": 100, "gridCarbonIntensity": 360})
    
    # 3600 output tokens at 30 tok/sec = 120 seconds
    # 100W for 120 seconds = 12000 Ws = 12000 / 3_600_000 kWh = 0.003333... kWh
    # 0.00333... kWh * 360 g/kWh = 1.2 grams
    co2 = co2_for_session(3600, tok_per_sec=30)
    assert abs(co2 - 1.2) < 0.0001
    
    # Non-positive inputs
    assert co2_for_session(-10) == 0.0
    assert co2_for_session(100, tok_per_sec=-5) == 0.0
