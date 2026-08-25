"""Single source of truth for where TokenTelemetry stores its config + state.

By default everything lives in ``~/.tokentelemetry/``. Two environment variables
let a user relocate it — handy for keeping the system drive clear, isolating
dev-tool state on a secondary drive, or pinning the path in tests:

  - ``TOKENTELEMETRY_DATA_DIR``  Absolute override of the data directory itself.
        Used verbatim: set it to ``D:\\dev\\tt-data`` (or ``/mnt/data/tt``) and
        that exact folder becomes the store — no ``.tokentelemetry`` suffix is
        appended. Highest precedence. This is the knob most users want.
  - ``TOKENTELEMETRY_HOME``      Override of the *home* directory; the usual
        ``.tokentelemetry`` subfolder is still appended underneath it. This is a
        pre-existing convention already honoured by the power/billing config and
        the test suite, kept for backward compatibility.

Resolution is lazy — the environment is read on every call — so a process that
exports the variable before launching the backend gets the right path, and tests
can monkeypatch it per-case. The directory is never created here: callers create
it lazily on first write (see ``harness_config._ensure_dir`` and friends), so a
read never materialises an empty folder in the wrong place.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

# The conventional folder name appended under the user's home (or under
# TOKENTELEMETRY_HOME). Not appended when TOKENTELEMETRY_DATA_DIR is used.
DEFAULT_DIRNAME = ".tokentelemetry"

# Windows-shaped path prefixes: a drive letter (`C:`) or a UNC root (`\\`).
_WIN_PATH_RE = re.compile(r"^(?:[A-Za-z]:|\\\\)")


def canonical_project(path: str | None) -> str | None:
    """Fold separator variants of the same folder into one project identity.

    Agent CLIs log cwd in their own style — some emit ``C:\\a\\b``, others
    ``C:/a/b``, a few mix both — and grouping compared those strings verbatim,
    so one real folder could surface as several project cards on Windows.
    Windows-shaped paths (drive-letter or UNC prefix) are unified to forward
    slashes; every path loses trailing separators. A backslash inside a POSIX
    path is a legal filename character there, so it is never rewritten.

    Not folded on purpose: letter case (``C:\\Repo`` vs ``c:/repo`` stay
    distinct — folding would merge different directories on case-sensitive
    filesystems). Non-path values ("unknown", agent sentinels, ``None``,
    ``""``) pass through unchanged.
    """
    if not isinstance(path, str) or not path:
        return path
    if _WIN_PATH_RE.match(path):
        path = path.replace("\\", "/")
    trimmed = path.rstrip("/")
    # A lone "/" or "//" must not collapse to "".
    return trimmed if trimmed else path


def data_dir() -> Path:
    """Resolve the TokenTelemetry data directory.

    Precedence (first match wins):
      1. ``TOKENTELEMETRY_DATA_DIR`` — used verbatim (``~`` expanded).
      2. ``TOKENTELEMETRY_HOME`` — ``<that>/.tokentelemetry``.
      3. ``~/.tokentelemetry``.
    """
    explicit = os.environ.get("TOKENTELEMETRY_DATA_DIR")
    if explicit and explicit.strip():
        return Path(explicit).expanduser()
    home = os.environ.get("TOKENTELEMETRY_HOME")
    base = Path(home).expanduser() if home and home.strip() else Path.home()
    return base / DEFAULT_DIRNAME
