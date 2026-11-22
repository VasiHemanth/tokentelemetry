"""Can this machine run local semantic search? A quick, dependency-free check.

The Recall and Project pages call this before offering local (Ollama)
semantic search. It answers three questions in plain English:

1. Is Ollama installed, reachable and new enough for the model?
2. Is there enough free memory and disk for the model and the index?
3. How long would indexing this project take here (a short speed test)?

Every probe degrades to "unknown" instead of raising: a check that cannot
run must never block keyword search or the API provider option.

Memory comes from each OS's own source (sysctl/vm_stat on macOS,
/proc/meminfo on Linux, GlobalMemoryStatusEx on Windows) so no new
dependency is needed. When the backend runs on a server, these numbers
describe the server, and the result says which host was checked.
"""
from __future__ import annotations

import ctypes
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Sequence

# Working estimates for embeddinggemma-2:740m through Ollama. Confirmed or
# corrected from the real pull (size) and a loaded model (memory); kept as
# constants so the check and the UI copy stay in one place.
MODEL_RAM_BYTES = 2 * 1024 ** 3
MODEL_DISK_BYTES = 2 * 1024 ** 3
INDEX_BYTES_PER_CHUNK = 256 * 4 + 200   # 256-dim float32 vector + row overhead
SPEED_SAMPLE = 32
SLOW_SECONDS = 30 * 60                   # above this, "slow but possible"


# ---------------------------------------------------------------- memory

def _mac_memory() -> Optional[Dict[str, int]]:
    try:
        total = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True,
                                   text=True, timeout=3).stdout.strip())
        vm = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=3).stdout
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    page = 4096
    m = re.search(r"page size of (\d+) bytes", vm)
    if m:
        page = int(m.group(1))

    def pages(label: str) -> int:
        mm = re.search(r"%s:\s+(\d+)" % re.escape(label), vm)
        return int(mm.group(1)) if mm else 0

    # Free + inactive + purgeable + speculative is what macOS can hand to a
    # new process without swapping, which is what loading a model needs.
    avail = (pages("Pages free") + pages("Pages inactive") + pages("Pages purgeable")
             + pages("Pages speculative")) * page
    return {"total": total, "available": min(avail, total)}


def _linux_memory() -> Optional[Dict[str, int]]:
    try:
        with open("/proc/meminfo", "r", encoding="ascii", errors="ignore") as f:
            info = f.read()
    except OSError:
        return None

    def kb(key: str) -> Optional[int]:
        m = re.search(r"^%s:\s+(\d+)\s+kB" % key, info, re.M)
        return int(m.group(1)) * 1024 if m else None

    total = kb("MemTotal")
    avail = kb("MemAvailable")
    if total is None:
        return None
    if avail is None:  # very old kernels
        avail = (kb("MemFree") or 0) + (kb("Cached") or 0)
    return {"total": total, "available": avail}


def _windows_memory() -> Optional[Dict[str, int]]:
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    try:
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):  # type: ignore[attr-defined]
            return None
        return {"total": int(stat.ullTotalPhys), "available": int(stat.ullAvailPhys)}
    except (AttributeError, OSError):
        return None


def memory() -> Optional[Dict[str, int]]:
    if sys.platform == "darwin":
        return _mac_memory()
    if sys.platform.startswith("linux"):
        return _linux_memory()
    if sys.platform == "win32":
        return _windows_memory()
    return None


def disk_free(path: str) -> Optional[int]:
    try:
        os.makedirs(path, exist_ok=True)
        return int(shutil.disk_usage(path).free)
    except OSError:
        return None


def platform_info() -> Dict[str, str]:
    machine = platform.machine() or "unknown"
    system = {"darwin": "macOS", "win32": "Windows"}.get(sys.platform, platform.system() or sys.platform)
    label = system
    if system == "macOS":
        label = "macOS (Apple Silicon)" if machine in ("arm64", "aarch64") else "macOS (Intel)"
    elif machine:
        label = "%s %s" % (system, machine)
    return {"os": system, "arch": machine, "label": label, "host": socket.gethostname() or "this machine"}


# ---------------------------------------------------------------- verdict

def _gb(n: Optional[int]) -> str:
    return "unknown" if n is None else "%.1f GB" % (n / 1024 ** 3)


def _minutes(seconds: float) -> str:
    if seconds < 90:
        return "about %d seconds" % max(1, round(seconds))
    if seconds < 90 * 60:
        return "about %d minutes" % round(seconds / 60)
    return "about %.1f hours" % (seconds / 3600)


def estimate_seconds(sample_seconds: float, sample_size: int, total_chunks: int) -> float:
    if sample_size <= 0 or sample_seconds <= 0:
        return 0.0
    return sample_seconds / sample_size * max(0, total_chunks)


def assess(
    *,
    ollama: Dict[str, Any],
    mem: Optional[Dict[str, int]],
    free_disk: Optional[int],
    chunks: int,
    speed: Optional[Dict[str, float]],
    plat: Dict[str, str],
    model_installed_bytes: int = 0,
) -> Dict[str, Any]:
    """Combine the probes into one verdict the UI can show as-is.

    ``status`` is ``ready`` (go), ``slow`` (possible, user decides),
    ``blocked`` (cannot run locally now) or ``unknown`` (a probe failed; the
    user may still try). ``reasons`` are plain-English sentences, each with
    the fix the user can apply.
    """
    reasons: List[Dict[str, str]] = []
    blocked = False

    if not ollama.get("reachable"):
        blocked = True
        reasons.append({"code": "ollama_missing",
                        "text": ollama.get("error") or "Ollama is not running on %s." % plat["host"],
                        "fix": "Install or start Ollama (ollama.com/download), or use an embedding API instead."})
    elif ollama.get("too_old"):
        blocked = True
        reasons.append({"code": "ollama_old",
                        "text": "Ollama %s is too old for this model." % (ollama.get("version") or "on this machine"),
                        "fix": "Update Ollama (ollama.com/download), then run the check again."})

    need_disk = 0 if model_installed_bytes else MODEL_DISK_BYTES
    need_disk += INDEX_BYTES_PER_CHUNK * max(0, chunks)
    if free_disk is not None and free_disk < need_disk:
        blocked = True
        reasons.append({"code": "disk",
                        "text": "Only %s of free disk; the model and index need about %s." % (_gb(free_disk), _gb(need_disk)),
                        "fix": "Free up disk space, or use an embedding API instead."})

    if mem is not None and mem.get("available", 0) < MODEL_RAM_BYTES:
        blocked = True
        reasons.append({"code": "memory",
                        "text": "Only %s of free memory; the model needs about %s." % (_gb(mem.get("available")), _gb(MODEL_RAM_BYTES)),
                        "fix": "Close other apps (or local models) and run the check again, or use an embedding API instead."})

    est = None
    if speed and speed.get("seconds") and speed.get("sample"):
        est = estimate_seconds(speed["seconds"], int(speed["sample"]), chunks)

    if blocked:
        status = "blocked"
    elif mem is None or free_disk is None or est is None:
        status = "unknown"
    elif est > SLOW_SECONDS:
        status = "slow"
        reasons.append({"code": "slow",
                        "text": "Indexing this project would take %s on this machine." % _minutes(est),
                        "fix": "Index anyway, use an embedding API, or run TokenTelemetry on a stronger machine."})
    else:
        status = "ready"

    return {
        "status": status,
        "platform": plat,
        "memory": {"total": (mem or {}).get("total"), "available": (mem or {}).get("available"),
                   "needed": MODEL_RAM_BYTES},
        "disk": {"free": free_disk, "needed": need_disk},
        "ollama": {k: ollama.get(k) for k in ("reachable", "version", "too_old", "model_installed")},
        "estimate": None if est is None else {"seconds": round(est, 1), "label": _minutes(est), "chunks": chunks},
        "reasons": reasons,
    }


def speed_test(embed: Callable[[Sequence[str]], Any], sample_texts: Sequence[str],
               clock: Callable[[], float] = time.monotonic) -> Optional[Dict[str, float]]:
    """Embed a small real sample once and time it. Returns None if it fails."""
    texts = list(sample_texts)[:SPEED_SAMPLE]
    if not texts:
        return None
    start = clock()
    try:
        embed(texts)
    except Exception:  # noqa: BLE001 - a failed sample means "unknown", not a crash
        return None
    return {"seconds": max(clock() - start, 1e-6), "sample": float(len(texts))}
