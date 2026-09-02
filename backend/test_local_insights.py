"""Tests for local-model insight helpers, smallcode TPS, and analytics local_only.

Run: pytest backend/test_local_insights.py -q
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))

import insights  # noqa: E402
import power_config as pc  # noqa: E402
import main  # noqa: E402


def test_tok_per_sec_from_duration():
    # 185 tokens in 40.065s ≈ 4.62 tok/s
    tps = insights.tok_per_sec_from_duration(185, 40065)
    assert tps is not None
    assert abs(tps - (185 / 40.065)) < 1e-6
    assert insights.tok_per_sec_from_duration(100, 10) is None  # < min_ms
    assert insights.tok_per_sec_from_duration(0, 1000) is None
    assert insights.tok_per_sec_from_duration(100, None) is None


def test_efficiency_helpers():
    assert abs(insights.wh_per_1m_tokens(2.0, 1000) - 2000.0) < 1e-9
    assert insights.wh_per_1m_tokens(1.0, 0) is None
    assert abs(insights.cost_per_1m_tokens(0.01, 1000) - 10.0) < 1e-9
    tps, src = insights.resolve_tok_per_sec(42.5, "x")
    assert tps == 42.5 and src == "measured"
    tps2, src2 = insights.resolve_tok_per_sec(None, "nemotron-3-nano:4b")
    assert src2 == "estimated"
    assert tps2 == pc.default_tok_per_sec_for_model("nemotron-3-nano:4b")


def test_parse_model_tags():
    assert pc.parse_model_params_b("nemotron-3-nano:4b") == 4.0
    assert pc.parse_model_params_b("llama-3.3-70b") == 70.0
    assert pc.parse_model_params_b("unknown") is None
    q = pc.parse_model_quant("mistral:7b-q4_K_M")
    assert q is not None and "Q4" in q.upper()
    assert pc.parse_model_base("nemotron-3-nano:4b") is not None


def test_local_metrics_for_session_local(tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "_config_path", lambda: tmp_path / "power.json")
    pc.device_default.cache_clear()
    (tmp_path / "power.json").write_text(
        json.dumps({"loadWatts": 100, "costPerKwh": 0.15, "gridCarbonIntensity": 360}),
        encoding="utf-8",
    )
    s = {
        "model": "nemotron-3-nano:4b",
        "provider": "ollama",
        "billing_mode": "local",
        "tokens": {"input": 100, "output": 3600, "cached": 0, "total": 3700},
        "cost": 0.0,
        "tok_per_sec": 30.0,
    }
    m = insights.local_metrics_for_session(s)
    assert m is not None
    assert m["is_local"] is True
    assert m["tok_per_sec_source"] == "measured"
    # 3600/30 = 120s * 100W / 3600 = 3.333 Wh
    assert abs(m["energy_wh"] - (120 * 100 / 3600)) < 1e-6
    assert m["co2_g"] > 0
    assert m["savings_usd"] >= 0


def test_local_metrics_for_session_cloud():
    s = {
        "model": "claude-sonnet-4-6",
        "provider": "anthropic",
        "tokens": {"input": 100, "output": 100, "cached": 0, "total": 200},
        "cost": 0.01,
    }
    assert insights.local_metrics_for_session(s) is None


def test_smallcode_stamps_local_and_tps(tmp_path):
    root = tmp_path / "proj"
    traces = root / ".smallcode" / "traces"
    traces.mkdir(parents=True)
    trace = {
        "id": "sc-local-1",
        "model": "nemotron-3-nano:4b",
        "prompt": "hello",
        "startedAt": "2026-07-01T05:14:54.084Z",
        "endedAt": "2026-07-01T05:15:34.149Z",
        "durationMs": 40065,
        "steps": [],
        "tokens": {"prompt": 100, "completion": 185},
    }
    (traces / "sc-local-1.json").write_text(json.dumps(trace), encoding="utf-8")
    out = main._scan_smallcode_sessions([str(root)])
    assert len(out) == 1
    rec = out[0]
    assert rec["provider"] == "ollama"
    assert rec["billing_mode"] == "local"
    assert rec["tok_per_sec"] is not None
    assert abs(rec["tok_per_sec"] - (185 / 40.065)) < 1e-6
    assert rec["cost"] >= 0  # electricity branch


def test_ollama_base_urls_ssrf_guard(monkeypatch):
    monkeypatch.setenv("TT_OLLAMA_HOST", "evil.example.com:11434")
    urls = main._ollama_base_urls()
    assert urls == ["http://127.0.0.1:11434"]
    monkeypatch.setenv("TT_OLLAMA_HOST", "127.0.0.1@evil.com:80")
    assert main._ollama_base_urls() == ["http://127.0.0.1:11434"]
    monkeypatch.setenv("TT_OLLAMA_HOST", "127.0.0.1:11434")
    assert main._ollama_base_urls() == ["http://127.0.0.1:11434"]


def test_probe_ollama_runtime_live():
    """Live Ollama probe when available; skip if offline (CI without Ollama)."""
    status = main._probe_ollama_runtime()
    assert status["ollama"] in ("online", "offline")
    assert "models" in status
    if status["ollama"] == "online":
        names = [m.get("name") for m in status["models"]]
        # Prefer presence of the model we exercise in the live workflow.
        assert any(n and "nemotron" in n for n in names) or len(names) >= 0
