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

import os
import re
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


def _looks_like_path(s: str) -> bool:
    """True when ``s`` is a path (has a separator), not a bare command name."""
    return os.sep in s or (os.altsep is not None and os.altsep in s)


def _binary_override(binary: str) -> str:
    """Location override for a CLI, via env ``TT_<BINARY>_BIN``. "" when unset.

    Enterprise / locked-down VDI installs often can't put the coding CLI on PATH
    (redirected profile, per-user install under Documents, an npm shim in a
    non-PATH dir) even though the binary runs fine when launched by full path.
    Setting e.g. ``TT_CLAUDE_BIN=C:\\Users\\me\\Documents\\claude.exe`` (or
    ``TT_OLLAMA_BIN`` / ``TT_CODEX_BIN`` / …, keyed on the adapter's ``binary``)
    makes both the availability probe and the actual summarize call use that
    path. A bare name is still PATH-resolved; a full/relative path is used as-is.
    """
    if not binary:
        return ""
    key = "TT_" + re.sub(r"[^A-Z0-9]+", "_", binary.upper()) + "_BIN"
    return os.environ.get(key, "").strip()


def _resolve_executable(name: str) -> str:
    """Resolve a bare CLI name to its full path on PATH, honouring PATHEXT.

    On Windows the coding CLIs are installed by npm as batch shims
    (``claude.cmd``, ``codex.cmd``, …) — there is no ``.exe``. ``shutil.which``
    finds them because it consults ``PATHEXT``, but a bare-name
    ``subprocess.run(["claude", …])`` with ``shell=False`` goes straight to
    Win32 ``CreateProcess``, which only appends ``.exe`` and so raises
    ``FileNotFoundError`` / ``[WinError 2]`` even though the CLI works in the
    shell. Handing subprocess the fully-resolved ``…\\claude.cmd`` path launches
    correctly (CreateProcess runs the batch shim by full path). On macOS/Linux
    ``which`` just returns the plain executable path, so this is a no-op there.

    Falls back to the original name when nothing is found, so the existing
    "failed to launch" error still surfaces with the same wording.

    A ``TT_<NAME>_BIN`` override wins over PATH resolution — a full/relative path
    is launched as-is (CreateProcess runs ``.exe``/``.cmd`` by full path), a bare
    override name is still PATH-resolved.
    """
    override = _binary_override(name)
    if override:
        return override if _looks_like_path(override) else (shutil.which(override) or override)
    return shutil.which(name) or name


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
    # Keep the friendly name for error messages; launch with the resolved path.
    name = cmd[0] if cmd else ""
    if cmd:
        cmd = [_resolve_executable(cmd[0]), *cmd[1:]]
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
        raise SummarizerError(f"{name} timed out after {timeout}s") from e
    except (OSError, ValueError) as e:
        raise SummarizerError(f"failed to launch {name}: {e}") from e

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
        raise SummarizerError(f"{name} exited {proc.returncode}: {err}")
    if not out:
        raise SummarizerError(f"{name} produced no output")
    return out


class BaseSummarizer(ABC):
    """One adapter per CLI. ``name`` matches the agent key in the registry."""

    name: str = ""
    display_name: str = ""
    binary: str = ""

    def is_available(self) -> bool:
        """True iff the CLI can be launched — on PATH, or via a TT_<BIN>_BIN override.

        The override lets a locked-down install expose a CLI that works but isn't
        on PATH (see ``_binary_override``); a path override must point at an
        existing file, a bare-name override must resolve on PATH.
        """
        if not self.binary:
            return False
        override = _binary_override(self.binary)
        if override:
            if _looks_like_path(override):
                return Path(override).is_file()
            return shutil.which(override) is not None
        return shutil.which(self.binary) is not None

    @abstractmethod
    def summarize(self, prompt: str, *, timeout: int = 120) -> str:
        """Send ``prompt`` to the CLI headlessly and return the model's text."""
        raise NotImplementedError
