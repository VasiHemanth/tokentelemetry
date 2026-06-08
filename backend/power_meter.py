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
        return {
            "available": not on_ac,
            "method": "macos-battery" if not on_ac else None,
            "system": system,
            "reason": (
                "On battery: whole-system power is read from the battery."
                if not on_ac else
                "On Apple Silicon, accurate GPU power needs admin (powermetrics). "
                "Unplug to read battery-based power, or set/calibrate a wattage manually."
            ),
        }
    return {
        "available": False, "method": None, "system": system,
        "reason": "No root-free power source detected; set a wattage manually.",
    }
