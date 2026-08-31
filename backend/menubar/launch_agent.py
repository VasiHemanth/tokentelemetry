"""Headless helpers for the macOS menu-bar LaunchAgent.

Everything here is importable on any platform and never imports ``rumps`` or
talks to Cocoa. The module builds a plist and the ``launchctl`` command lines,
and shells out only through an injectable ``run`` callable so tests can capture
commands without touching the real launchd.

The agent is written to ``~/Library/LaunchAgents/com.tokentelemetry.menubar.plist``
and is never installed automatically: ``enable`` / ``disable`` are called only
from the menu item, so a tool only adds itself to login items when asked.
"""

from __future__ import annotations

import os
import plistlib
import subprocess
from pathlib import Path
from typing import Any, Callable, List, Mapping, Optional, Sequence, Union

LABEL = "com.tokentelemetry.menubar"
PLIST_FILENAME = f"{LABEL}.plist"

PathLike = Union[Path, str]


def agent_dir(home: Optional[PathLike] = None) -> Path:
    """The LaunchAgents directory, defaulting to the current user's home."""
    return Path(home) / "Library" / "LaunchAgents" if home else Path.home() / "Library" / "LaunchAgents"


def plist_path(home: Optional[PathLike] = None) -> Path:
    """Absolute path to this app's LaunchAgent plist."""
    return agent_dir(home) / PLIST_FILENAME


def build_plist(
    program_args: Sequence[str],
    data_dir: PathLike,
    env: Optional[Mapping[str, str]] = None,
) -> dict:
    """The plist dictionary, with absolute program arguments and log paths."""
    logs = Path(data_dir) / "logs"
    return {
        "Label": LABEL,
        "ProgramArguments": [str(arg) for arg in program_args],
        "RunAtLoad": True,
        "StandardOutPath": str(logs / "menubar.out.log"),
        "StandardErrorPath": str(logs / "menubar.err.log"),
        "EnvironmentVariables": {str(key): str(value) for key, value in (env or {}).items()},
    }


def render_plist(plist: Mapping[str, Any]) -> bytes:
    """Serialize a plist dictionary to XML bytes."""
    return plistlib.dumps(dict(plist), sort_keys=False)


def write_plist(
    program_args: Sequence[str],
    data_dir: PathLike,
    env: Optional[Mapping[str, str]] = None,
    home: Optional[PathLike] = None,
) -> Path:
    """Write the plist (creating the LaunchAgents dir) and return its path."""
    path = plist_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(render_plist(build_plist(program_args, data_dir, env)))
    return path


def remove_plist(home: Optional[PathLike] = None) -> None:
    """Delete the plist if present."""
    plist_path(home).unlink(missing_ok=True)


def is_installed(home: Optional[PathLike] = None) -> bool:
    """Whether the LaunchAgent plist currently exists."""
    return plist_path(home).exists()


def _uid(uid: Optional[int]) -> int:
    return os.getuid() if uid is None else uid


def bootstrap_command(plist: PathLike, uid: Optional[int] = None) -> List[str]:
    """launchctl bootstrap into the user's GUI domain."""
    return ["launchctl", "bootstrap", f"gui/{_uid(uid)}", str(plist)]


def bootout_command(uid: Optional[int] = None) -> List[str]:
    """launchctl bootout of the user's GUI domain."""
    return ["launchctl", "bootout", f"gui/{_uid(uid)}/{LABEL}"]


def print_command(uid: Optional[int] = None) -> List[str]:
    """launchctl print, used to check whether the agent is loaded."""
    return ["launchctl", "print", f"gui/{_uid(uid)}/{LABEL}"]


def enable(
    program_args: Sequence[str],
    data_dir: PathLike,
    env: Optional[Mapping[str, str]] = None,
    home: Optional[PathLike] = None,
    uid: Optional[int] = None,
    run: Callable[..., Any] = subprocess.run,
) -> Path:
    """Install the plist and bootstrap it with launchd.

    Returns the plist path. ``run`` is injectable so tests can capture the
    launchctl invocation instead of touching the real launchd.
    """
    path = write_plist(program_args, data_dir, env, home)
    run(bootstrap_command(path, uid), check=True)
    return path


def disable(
    home: Optional[PathLike] = None,
    uid: Optional[int] = None,
    run: Callable[..., Any] = subprocess.run,
) -> None:
    """Boot the agent out of launchd and remove the plist.

    The bootout is best-effort (the agent may not be loaded), but the plist is
    always removed so launchd will not start it again at next login.
    """
    run(bootout_command(uid), check=False)
    remove_plist(home)
