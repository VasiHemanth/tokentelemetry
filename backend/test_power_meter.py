"""Tests for the userspace Apple-Silicon power estimate in power_meter.

These cover the pure parsing + tier→watts logic deterministically by mocking the
subprocess calls, so they pass on any platform (CI is usually Linux).
"""

import power_meter as pm


def _patch_apple(monkeypatch, brand, gpu_cores=None, arm=True):
    """Make power_meter look like an Apple Silicon box returning `brand`."""
    monkeypatch.setattr(pm.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(pm.platform, "machine", lambda: "arm64" if arm else "x86_64")

    def fake_run(cmd, timeout=3.0):
        if cmd[:2] == ["sysctl", "-n"]:
            return brand
        if cmd[0] == "system_profiler":
            return f"  Total Number of Cores: {gpu_cores}\n" if gpu_cores else ""
        return None

    monkeypatch.setattr(pm, "_run", fake_run)


def test_chip_base(monkeypatch):
    _patch_apple(monkeypatch, "Apple M5", gpu_cores=10)
    chip = pm._apple_silicon_chip()
    assert chip == {"chip": "Apple M5", "generation": 5, "tier": "base", "gpu_cores": 10}


def test_chip_tiers(monkeypatch):
    for brand, tier in [
        ("Apple M3 Pro", "pro"),
        ("Apple M3 Max", "max"),
        ("Apple M2 Ultra", "ultra"),
        ("Apple M1", "base"),
    ]:
        _patch_apple(monkeypatch, brand)
        assert pm._apple_silicon_chip()["tier"] == tier


def test_estimated_watts_by_tier(monkeypatch):
    cases = [
        ("Apple M5", 22.0),
        ("Apple M4 Pro", 35.0),
        ("Apple M3 Max", 65.0),
        ("Apple M2 Ultra", 120.0),
    ]
    for brand, watts in cases:
        _patch_apple(monkeypatch, brand)
        est = pm.estimated_watts()
        assert est["watts"] == watts
        assert est["source"] == "apple-silicon-default"
        assert est["confidence"] == "estimated"


def test_estimated_watts_label_includes_cores(monkeypatch):
    _patch_apple(monkeypatch, "Apple M5", gpu_cores=10)
    assert pm.estimated_watts()["detail"] == "Apple M5 (10-core GPU)"


def test_estimated_watts_label_without_cores(monkeypatch):
    _patch_apple(monkeypatch, "Apple M5", gpu_cores=None)
    assert pm.estimated_watts()["detail"] == "Apple M5"


def test_not_apple_silicon_returns_none(monkeypatch):
    # Intel mac → not arm64 → no chip estimate.
    _patch_apple(monkeypatch, "Apple M5", arm=True, gpu_cores=8)
    monkeypatch.setattr(pm.platform, "machine", lambda: "x86_64")
    assert pm._apple_silicon_chip() is None
    assert pm.estimated_watts() is None


def test_linux_returns_none(monkeypatch):
    monkeypatch.setattr(pm.platform, "system", lambda: "Linux")
    monkeypatch.setattr(pm.platform, "machine", lambda: "x86_64")
    assert pm.estimated_watts() is None


def test_unparseable_brand_returns_none(monkeypatch):
    _patch_apple(monkeypatch, "Some Unknown CPU")
    assert pm._apple_silicon_chip() is None


def test_capability_includes_estimate_on_ac(monkeypatch):
    """Apple Silicon on AC: no measurement, but a chip estimate is offered."""
    monkeypatch.setattr(pm.shutil, "which", lambda _: None)  # no nvidia-smi
    monkeypatch.setattr(pm.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(pm.platform, "machine", lambda: "arm64")

    def fake_run(cmd, timeout=3.0):
        if cmd[:2] == ["ioreg", "-r"]:
            return 'ExternalConnected = Yes\n'  # on AC
        if cmd[:2] == ["sysctl", "-n"]:
            return "Apple M5"
        if cmd[0] == "system_profiler":
            return "Total Number of Cores: 10\n"
        return None

    monkeypatch.setattr(pm, "_run", fake_run)
    cap = pm.capability()
    assert cap["available"] is False
    assert cap["estimated"]["watts"] == 22.0
    assert cap["estimated"]["detail"] == "Apple M5 (10-core GPU)"
