"""Summarizer backends.

A summarizer turns a condensed trace brief into a natural-language summary by
shelling out to a coding CLI the user already has installed and authenticated.
This keeps TokenTelemetry's "no signup, no key, 100% local-first" promise — we
borrow the agent the user is already running rather than shipping our own key.

Each adapter only needs to know how to invoke its CLI headlessly and pull the
text back out. Heavy lifting (condensing, prompting, caching) lives in
``summaries.py``; adapters stay thin.
"""
from __future__ import annotations

import shutil
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from tt_paths import data_dir


class SummarizerError(Exception):
    """Raised when a backend is unavailable or the CLI call fails/﻿times out.

    Always non-fatal to the caller: a missing summary must never block the
    trace view.
    """


# CLIs that log their own sessions (codex/gemini/qwen) are run from here so the
# ingest layer can recognise and skip TokenTelemetry's own summarizer calls,
# rather than surfacing them as phantom traces in the user's stats.
SUMMARIZER_CWD = data_dir() / "summarizer"


def _ensure_cwd() -> str:
    SUMMARIZER_CWD.mkdir(parents=True, exist_ok=True)
    return str(SUMMARIZER_CWD)


def run_cli(
    cmd: list[str],
    *,
    stdin: Optional[str] = None,
    cwd: Optional[str] = None,
    timeout: int = 120,
) -> str:
    """Run a CLI to completion and return stdout, or raise SummarizerError.

    stdout is returned even on a non-zero exit when it is non-empty — some CLIs
    print a usable result and then exit non-zero on a teardown warning.
    """
    try:
        proc = subprocess.run(
            cmd,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
    except subprocess.TimeoutExpired as e:
        raise SummarizerError(f"{cmd[0]} timed out after {timeout}s") from e
    except (OSError, ValueError) as e:
        raise SummarizerError(f"failed to launch {cmd[0]}: {e}") from e

    out = (proc.stdout or "").strip()
    if proc.returncode != 0 and not out:
        # Some CLIs (codex, claude) echo the entire prompt back to stderr as
        # part of their banner before failing. The actual cause is always at
        # the END of stderr, not the start — so prefer ERROR/error lines if
        # present, else tail the last 2000 chars.
        stderr = (proc.stderr or "").strip()
        err_lines = [ln for ln in stderr.splitlines() if "ERROR" in ln]
        if err_lines:
            err = "\n".join(err_lines[-5:])[:2000]
        else:
            err = stderr[-2000:] if len(stderr) > 2000 else stderr
        raise SummarizerError(f"{cmd[0]} exited {proc.returncode}: {err}")
    if not out:
        raise SummarizerError(f"{cmd[0]} produced no output")
    return out


class BaseSummarizer(ABC):
    """One adapter per CLI. ``name`` matches the agent key in the registry."""

    name: str = ""
    display_name: str = ""
    binary: str = ""

    def is_available(self) -> bool:
        """True iff the CLI is installed and on PATH."""
        return self.binary != "" and shutil.which(self.binary) is not None

    @abstractmethod
    def summarize(self, prompt: str, *, timeout: int = 120) -> str:
        """Send ``prompt`` to the CLI headlessly and return the model's text."""
        raise NotImplementedError
