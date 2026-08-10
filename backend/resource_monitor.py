"""Small, local host-impact monitor used by the System Impact dashboard.

It deliberately retains aggregates only: no command lines, paths, prompts, or
process identifiers are stored.  A future native collector can write the same
SQLite schema at higher fidelity without changing the read API.
"""
from __future__ import annotations

import os
import platform
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List

from resource_baselines import assess_personal_baseline
from tt_paths import data_dir

_AGENT_MARKERS = {
    "claude": ("claude", "claude-code"),
    "codex": ("codex", "openai-codex"),
}
_SERIES_LIMIT = 360


def _db_path() -> Path:
    return data_dir() / "resources.db"


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), timeout=2.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS host_samples (
            timestamp INTEGER PRIMARY KEY,
            memory_total_bytes INTEGER NOT NULL,
            memory_available_bytes INTEGER,
            wired_bytes INTEGER,
            agent_rss_bytes INTEGER NOT NULL,
            active_agent_count INTEGER NOT NULL,
            process_count INTEGER NOT NULL,
            agents_json TEXT NOT NULL
        )
        """
    )
    return con


def _memory_total_bytes() -> int:
    try:
        return int(os.sysconf("SC_PAGE_SIZE")) * int(os.sysconf("SC_PHYS_PAGES"))
    except (AttributeError, OSError, ValueError):
        return 0


def _linux_memory() -> Dict[str, int | None]:
    fields: Dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, value = line.split(":", 1)
            fields[key] = int(value.strip().split()[0]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return {"available": fields.get("MemAvailable"), "wired": None}


def _macos_memory() -> Dict[str, int | None]:
    """Read aggregate VM counters without privileges; failures stay visible as N/A."""
    try:
        out = subprocess.run(
            ["vm_stat"], capture_output=True, text=True, timeout=2.0, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {"available": None, "wired": None}
    page_size = 4096
    values: Dict[str, int] = {}
    for line in out.splitlines():
        if "page size of" in line:
            try:
                page_size = int(line.split("page size of", 1)[1].split("bytes", 1)[0].strip())
            except (IndexError, ValueError):
                pass
        if ":" not in line:
            continue
        name, raw = line.split(":", 1)
        try:
            values[name.strip()] = int(raw.strip().rstrip("."))
        except ValueError:
            continue
    available_pages = values.get("Pages free", 0) + values.get("Pages inactive", 0)
    wired_pages = values.get("Pages wired down", 0)
    return {
        "available": available_pages * page_size if available_pages else None,
        "wired": wired_pages * page_size if wired_pages else None,
    }


def _agent_processes() -> tuple[int, int, List[str]]:
    """Return aggregate RSS and agent names without retaining process details."""
    if os.name == "nt":
        return 0, 0, []  # Native collector will replace this conservative fallback.
    try:
        out = subprocess.run(
            ["ps", "-axo", "rss=,comm=,args="], capture_output=True, text=True,
            timeout=2.0, check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return 0, 0, []
    rss_bytes = 0
    names: set[str] = set()
    for line in out.splitlines():
        parts = line.strip().split(maxsplit=2)
        if len(parts) < 2:
            continue
        try:
            rss_kib = int(parts[0])
        except ValueError:
            continue
        searchable = " ".join(parts[1:]).lower()
        for agent, markers in _AGENT_MARKERS.items():
            if any(marker in searchable for marker in markers):
                names.add(agent)
                rss_bytes += rss_kib * 1024
                break
    return rss_bytes, len(names), sorted(names)


def _process_count() -> int:
    if os.name == "nt":
        return 0
    try:
        return max(0, len(subprocess.run(
            ["ps", "-ax"], capture_output=True, text=True, timeout=2.0, check=False
        ).stdout.splitlines()) - 1)
    except (OSError, subprocess.SubprocessError):
        return 0


def collect_snapshot() -> Dict[str, Any]:
    """Collect one local aggregate sample without inspecting agent file contents."""
    system = platform.system()
    memory = _macos_memory() if system == "Darwin" else _linux_memory() if system == "Linux" else {"available": None, "wired": None}
    rss, agent_count, agents = _agent_processes()
    return {
        "timestamp": int(time.time()),
        "memory_total_bytes": _memory_total_bytes(),
        "memory_available_bytes": memory["available"],
        "wired_bytes": memory["wired"],
        "agent_rss_bytes": rss,
        "active_agent_count": agent_count,
        "process_count": _process_count(),
        "agents": agents,
    }


def _baseline_rows(con: sqlite3.Connection, active_agent_count: int) -> List[sqlite3.Row]:
    return con.execute(
        """
        SELECT * FROM host_samples
        WHERE active_agent_count BETWEEN ? AND ?
        ORDER BY timestamp DESC LIMIT 1000
        """,
        (max(0, active_agent_count - 1), active_agent_count + 1),
    ).fetchall()


def record_and_build_health() -> Dict[str, Any]:
    """Persist a current observation and return its local-history explanation."""
    sample = collect_snapshot()
    con = _connect()
    try:
        comparable = _baseline_rows(con, sample["active_agent_count"])
        agent_baseline = assess_personal_baseline(
            sample["agent_rss_bytes"], [row["agent_rss_bytes"] for row in comparable]
        )
        available_baseline = assess_personal_baseline(
            sample["memory_available_bytes"] or 0,
            [row["memory_available_bytes"] or 0 for row in comparable],
        )
        con.execute(
            """
            INSERT OR REPLACE INTO host_samples VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sample["timestamp"], sample["memory_total_bytes"], sample["memory_available_bytes"],
                sample["wired_bytes"], sample["agent_rss_bytes"], sample["active_agent_count"],
                sample["process_count"], ",".join(sample["agents"]),
            ),
        )
        con.execute(
            "DELETE FROM host_samples WHERE timestamp < ?",
            (sample["timestamp"] - (30 * 24 * 60 * 60),),
        )
        con.commit()
        rows = con.execute(
            "SELECT * FROM host_samples ORDER BY timestamp DESC LIMIT ?", (_SERIES_LIMIT,)
        ).fetchall()
    finally:
        con.close()

    series = [
        {
            "timestamp": row["timestamp"],
            "memory_available_bytes": row["memory_available_bytes"],
            "wired_bytes": row["wired_bytes"],
            "agent_rss_bytes": row["agent_rss_bytes"],
            "active_agent_count": row["active_agent_count"],
            "process_count": row["process_count"],
        }
        for row in reversed(rows)
    ]
    return {
        "current": sample,
        "series": series,
        "baseline": {
            "agent_rss_bytes": agent_baseline,
            "memory_available_bytes": available_baseline,
            "comparison": "same active-agent count, plus or minus one",
            "scope": "local machine only",
        },
        "collector": {"kind": "backend-local-sampler", "sampling": "on dashboard refresh", "network": "none"},
    }
