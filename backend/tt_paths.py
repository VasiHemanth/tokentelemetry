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
# VS Code on Windows stores file URIs as /c:/... after unquoting.
_VSCODE_WIN_PATH_RE = re.compile(r"^/([A-Za-z]):/")


def canonical_project(path: str | None) -> str | None:
    """Fold separator variants of the same folder into one project identity.

    Agent CLIs log cwd in their own style — some emit ``C:\\a\\b``, others
    ``C:/a/b``, a few mix both — and grouping compared those strings verbatim,
    so one real folder could surface as several project cards on Windows.
    Windows-shaped paths (drive-letter or UNC prefix) are unified to forward
    slashes; every path loses trailing separators. A backslash inside a POSIX
    path is a legal filename character there, so it is never rewritten.

    Exception: VS Code on Windows emits ``file:///c%3A/...`` which
    URL-decodes to ``/c:/...``; the leading slash is stripped and the drive
    letter is uppercased to match what other agents emit (``C:/...``).
    That single normalisation intentionally changes case for that prefix.

    Not folded on purpose: letter case elsewhere (``C:\\Repo`` vs ``c:/repo``
    stay distinct — folding would merge different directories on
    case-sensitive filesystems). Non-path values ("unknown", agent sentinels,
    ``None``, ``""``) pass through unchanged.
    """
    if not isinstance(path, str) or not path:
        return path
    # VS Code on Windows produces file:///c%3A/... which unquotes to /c:/...
    # Strip the spurious leading slash and upcase the drive letter so it
    # matches what Claude Code and other agents emit (C:/...).
    m = _VSCODE_WIN_PATH_RE.match(path)
    if m:
        path = m.group(1).upper() + ":/" + path[len(m.group(0)):]
    if _WIN_PATH_RE.match(path):
        path = path.replace("\\", "/")
    had_trailing_slash = path.endswith("/") or path.endswith("\\")
    trimmed = path.rstrip("/")
    # A lone "/" or "//" must not collapse to "".
    # "C:/" (drive root) must stay "C:/" — "C:" means "current dir on
    # drive C" in Windows, which is semantically different. Only restore
    # the slash when the input actually had one (i.e. this was a root path,
    # not a bare drive specifier).
    if re.match(r"^[A-Za-z]:$", trimmed) and had_trailing_slash:
        return trimmed + "/"
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
