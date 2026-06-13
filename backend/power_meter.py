"""Real-as-possible hardware power measurement for local-model electricity cost.

The electricity estimate needs an *actual* power draw, not a guessed wattage.
This module reads real power where the OS allows it **without root**, and is
honest (via `confidence`) when it can't:

Source priority (each returns watts or None):
  1. ``nvidia-smi`` — NVIDIA GPU draw. No root. confidence="measured".
  2. macOS battery discharge (``ioreg`` Voltage×InstantAmperage). No root, but
     only meaningful **on battery** (on AC the battery current is ~0).
     confidence="measured" (whole-system, not just the accelerator).
  3. None → the caller falls back to the user's configured/calibrated
     ``loadWatts`` (confidence="configured" or "estimated").

Hard constraint: we **never invoke sudo**. On Apple Silicon on AC power there is
no root-free way to read package/GPU power (``powermetrics`` is root-only), so we
return None there and surface that to the UI rather than fabricating a number.

A user who wants real Apple-Silicon numbers can run ``sudo powermetrics`` (or a
power meter) themselves and enter/confirm the value via calibration — TT will not
silently escalate privileges.
"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional


def _run(cmd: List[str], timeout: float = 3.0) -> Optional[str]:
    """Run a command, return stdout or None. Never raises."""
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
        return out.stdout if out.returncode == 0 else None
    except Exception:
        return None


def _nvidia_smi_watts() -> Optional[float]:
    """Total GPU draw across NVIDIA cards, in watts. No root required."""
    if not shutil.which("nvidia-smi"):
        return None
    out = _run([
        "nvidia-smi", "--query-gpu=power.draw",
        "--format=csv,noheader,nounits",
    ])
    if not out:
        return None
    total = 0.0
    found = False
    for line in out.splitlines():
        line = line.strip()
        try:
            total += float(line)
            found = True
        except ValueError:
            continue
    return total if found else None


def _macos_battery_watts() -> Optional[float]:
    """Whole-system power from battery discharge (W = |A| × V). No root.

    Only meaningful while running ON BATTERY — on AC the battery current is ~0,
    so we return None and let the caller use a configured wattage instead.
    """
    if platform.system() != "Darwin":
        return None
    out = _run(["ioreg", "-r", "-c", "AppleSmartBattery"])
    if not out:
        return None
    # Quotes are optional, but a preceding alphanumeric boundary is required so we
    # don't match the standalone keys inside longer ones — e.g. AppleRaw*External
    # *Connected*, Maximum*Pack*Voltage*, Soc1*Voltage*, Cell*Voltage*. ioreg quotes
    # top-level keys; tolerating the unquoted form too just makes us version/format
    # robust without those collisions.
    external = re.search(r'(?<![A-Za-z0-9])"?ExternalConnected"?\s*=\s*(Yes|No)', out)
    if external and external.group(1) == "Yes":
        return None  # on AC → battery current ~0, not a usable signal
    amp = re.search(r'(?<![A-Za-z0-9])"?InstantAmperage"?\s*=\s*(-?\d+)', out)
    volt = re.search(r'(?<![A-Za-z0-9])"?Voltage"?\s*=\s*(\d+)', out)
    if not amp or not volt:
        return None
    # InstantAmperage is a signed value often stored as an unsigned 64-bit int —
    # e.g. discharge shows up as 18446744073709551334 (= -282 mA in two's
    # complement). Decode it before taking the magnitude, or we'd compute a
    # nonsensical quintillion-watt figure.
    raw = int(amp.group(1))
    if raw >= 2 ** 63:
        raw -= 2 ** 64
    milliamps = abs(raw)
    millivolts = int(volt.group(1))
    watts = (milliamps / 1000.0) * (millivolts / 1000.0)
    return watts if watts > 0 else None


# ---------------------------------------------------------------------------
# Apple Silicon estimated default (userspace, no root)
# ---------------------------------------------------------------------------
# There is no root-free way to MEASURE watts on Apple Silicon (powermetrics is
# root-only; on AC the battery current is ~0). But the chip itself is readable in
# userspace via sysctl + system_profiler. We use that to seed a far better
# DEFAULT than the generic 80 W: a laptop M-series package under sustained
# inference draws ~20-45 W, so 80 W overestimates electricity cost by ~2x on the
# machines most likely to run local models. This is an ESTIMATE
# (confidence="estimated"), never a measurement — the user overrides it if they
# know their real draw. Cf. llama-swap discussion #814.

# Typical whole-package draw (watts) under sustained inference load by chip tier.
# Deliberately mid-range, conservative ballpark figures — they exist so the
# default isn't wildly wrong for Apple Silicon, not to claim precision.
_APPLE_TIER_WATTS = {
    "ultra": 120.0,
    "max": 65.0,
    "pro": 35.0,
    "base": 22.0,
}

_APPLE_BRAND_RE = re.compile(r"\bApple\s+M(\d+)\s*(Pro|Max|Ultra)?\b", re.IGNORECASE)


def _apple_silicon_chip(with_gpu_cores: bool = True) -> Optional[Dict[str, Any]]:
    """Identify the Apple Silicon chip from userspace (no root). None if not AS.

    Returns ``{chip, generation, tier, gpu_cores}`` where ``tier`` is one of
    base/pro/max/ultra and ``gpu_cores`` may be None if unreadable. The wattage
    only needs ``tier`` (from the fast sysctl call); ``with_gpu_cores=False``
    skips the slower ``system_profiler`` call used purely for the human label.
    """
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        return None
    brand = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
    if not brand:
        return None
    m = _APPLE_BRAND_RE.search(brand.strip())
    if not m:
        return None
    tier = (m.group(2) or "base").lower()
    chip = " ".join(m.group(0).split())  # normalise internal whitespace
    # GPU core count (userspace) — refines the human label only, not the wattage.
    gpu_cores: Optional[int] = None
    if with_gpu_cores:
        sp = _run(["system_profiler", "SPDisplaysDataType"], timeout=5.0)
        if sp:
            cm = re.search(r"Total Number of Cores:\s*(\d+)", sp)
            if cm:
                gpu_cores = int(cm.group(1))
    return {
        "chip": chip,
        "generation": int(m.group(1)),
        "tier": tier,
        "gpu_cores": gpu_cores,
    }


def estimated_watts(with_detail: bool = True) -> Optional[Dict[str, Any]]:
    """A best-effort DEFAULT wattage when no real reading is possible.

    On Apple Silicon, derived from the (userspace-readable) chip tier; elsewhere
    None. Always ``confidence="estimated"`` — a starting point the user reviews
    and overrides, not a measurement. Returns
    ``{watts, source, confidence, detail}`` or None. ``with_detail=False`` skips
    the slower GPU-core lookup when only the wattage is needed (hot path).
    """
    chip = _apple_silicon_chip(with_gpu_cores=with_detail)
    if not chip:
        return None
    watts = _APPLE_TIER_WATTS.get(chip["tier"], _APPLE_TIER_WATTS["base"])
    cores = chip.get("gpu_cores")
    label = chip["chip"] + (f" ({cores}-core GPU)" if cores else "")
    return {
        "watts": watts,
        "source": "apple-silicon-default",
        "confidence": "estimated",
        "detail": label,
    }


# A personal machine's draw under inference load realistically sits well under
# this. Anything outside (0, MAX] is treated as a bad reading and discarded — a
# guard against parsing glitches (e.g. unsigned battery counters) reaching cost.
MAX_PLAUSIBLE_WATTS = 2000.0


def _sane(watts: Optional[float]) -> Optional[float]:
    if watts is None:
        return None
    return watts if 0 < watts <= MAX_PLAUSIBLE_WATTS else None


def read_power_watts() -> Optional[Dict[str, Any]]:
    """Best available *real* power reading, or None if none is available.

    Returns ``{"watts": float, "source": str, "confidence": "measured"}`` or None.
    Implausible values (≤0 or > MAX_PLAUSIBLE_WATTS) are discarded as None.
    """
    w = _sane(_nvidia_smi_watts())
    if w is not None:
        return {"watts": round(w, 1), "source": "nvidia-smi", "confidence": "measured"}
    w = _sane(_macos_battery_watts())
    if w is not None:
        return {"watts": round(w, 1), "source": "macos-battery", "confidence": "measured"}
    return None


def sample_average_watts(duration_s: float = 5.0, interval_s: float = 1.0) -> Optional[Dict[str, Any]]:
    """Average several real readings — used by the calibration flow.

    Returns the averaged ``{watts, source, confidence, samples}`` or None when no
    real source is available (e.g. Apple Silicon on AC).
    """
    readings: List[float] = []
    source: Optional[str] = None
    deadline = time.monotonic() + max(0.0, duration_s)
    while time.monotonic() < deadline:
        r = read_power_watts()
        if r is None:
            break
        readings.append(r["watts"])
        source = r["source"]
        time.sleep(max(0.05, interval_s))
    if not readings:
        return None
    return {
        "watts": round(sum(readings) / len(readings), 1),
        "source": source,
        "confidence": "measured",
        "samples": len(readings),
    }


def capability() -> Dict[str, Any]:
    """Describe what real measurement is possible here, so the UI can explain it.

    ``available`` = a root-free real reading is possible right now. ``reason``
    is a short, user-facing explanation when it isn't.
    """
    system = platform.system()
    if shutil.which("nvidia-smi"):
        return {
            "available": True, "method": "nvidia-smi", "system": system,
            "reason": "NVIDIA GPU power read directly (no admin needed).",
        }
    if system == "Darwin":
        on_ac = True
        out = _run(["ioreg", "-r", "-c", "AppleSmartBattery"])
        if out:
            m = re.search(r'(?<![A-Za-z0-9])"?ExternalConnected"?\s*=\s*(Yes|No)', out)
            on_ac = not (m and m.group(1) == "No")
        # No measurement on AC, but we can still suggest a chip-aware default.
        est = estimated_watts() if on_ac else None
        cap = {
            "available": not on_ac,
            "method": "macos-battery" if not on_ac else None,
            "system": system,
            "reason": (
                "On battery: whole-system power is read from the battery."
                if not on_ac else
                "On Apple Silicon, accurate GPU power needs admin (powermetrics). "
                "Unplug to read battery-based power, or use the chip-based estimate below."
            ),
        }
        if est:
            cap["estimated"] = est
        return cap
    est = estimated_watts()
    cap = {
        "available": False, "method": None, "system": system,
        "reason": "No root-free power source detected; set a wattage manually.",
    }
    if est:
        cap["estimated"] = est
    return cap
