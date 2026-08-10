"""Tests for the local, no-agent-file-write resource monitor."""

import resource_monitor as monitor


def test_health_snapshot_is_persisted_and_contains_only_aggregate_process_data(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKENTELEMETRY_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(monitor, "collect_snapshot", lambda: {
        "timestamp": 1_700_000_000,
        "memory_total_bytes": 16_000,
        "memory_available_bytes": 6_000,
        "wired_bytes": 2_000,
        "agent_rss_bytes": 1_500,
        "active_agent_count": 1,
        "process_count": 90,
        "agents": ["claude"],
    })

    result = monitor.record_and_build_health()

    assert result["current"]["agent_rss_bytes"] == 1_500
    assert result["current"]["agents"] == ["claude"]
    assert result["baseline"]["agent_rss_bytes"]["state"] == "learning"
    assert len(result["series"]) == 1
    assert (tmp_path / "resources.db").exists()
