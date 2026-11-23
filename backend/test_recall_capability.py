import recall_capability as cap

PLAT = {"os": "macOS", "arch": "arm64", "label": "macOS (Apple Silicon)", "host": "dev-mac"}
GB = 1024 ** 3
OK_OLLAMA = {"reachable": True, "version": "0.40.0", "too_old": False, "model_installed": True}


def verdict(**kw):
    base = dict(ollama=OK_OLLAMA, mem={"total": 32 * GB, "available": 16 * GB},
                free_disk=200 * GB, chunks=8000, speed={"seconds": 1.0, "sample": 32}, plat=PLAT)
    base.update(kw)
    return cap.assess(**base)


def test_ready_with_estimate():
    v = verdict()
    assert v["status"] == "ready"
    assert v["estimate"]["seconds"] == 250.0 and "minutes" in v["estimate"]["label"]
    assert v["reasons"] == []


def test_old_ollama_blocks_with_fix():
    v = verdict(ollama={"reachable": True, "version": "0.35.0", "too_old": True})
    assert v["status"] == "blocked"
    r = v["reasons"][0]
    assert r["code"] == "ollama_old" and "0.35.0" in r["text"] and "Update Ollama" in r["fix"]


def test_missing_ollama_names_the_host():
    v = verdict(ollama={"reachable": False})
    assert v["status"] == "blocked" and "dev-mac" in v["reasons"][0]["text"]


def test_low_memory_and_disk_both_reported():
    v = verdict(mem={"total": 8 * GB, "available": GB // 2}, free_disk=GB // 4)
    codes = {r["code"] for r in v["reasons"]}
    assert v["status"] == "blocked" and {"memory", "disk"} <= codes


def test_slow_is_a_choice_not_a_block():
    v = verdict(speed={"seconds": 10.0, "sample": 32}, chunks=8000)  # ~42 min
    assert v["status"] == "slow" and v["reasons"][0]["code"] == "slow"
    assert "Index anyway" in v["reasons"][0]["fix"]


def test_unknown_when_a_probe_fails():
    assert verdict(mem=None)["status"] == "unknown"
    assert verdict(speed=None)["status"] == "unknown"


def test_installed_model_needs_no_model_disk():
    v = verdict(model_installed_bytes=1, free_disk=1 * GB, chunks=1000)
    assert v["status"] == "ready"


def test_speed_test_times_and_survives_failure():
    ticks = iter([0.0, 2.0])
    out = cap.speed_test(lambda texts: None, ["a"] * 40, clock=lambda: next(ticks))
    assert out == {"seconds": 2.0, "sample": 32.0}

    def boom(texts):
        raise RuntimeError("down")
    assert cap.speed_test(boom, ["a"]) is None


def test_real_probes_return_sane_values_or_none():
    m = cap.memory()
    assert m is None or (m["total"] > 0 and 0 <= m["available"] <= m["total"])
    assert cap.platform_info()["os"]
