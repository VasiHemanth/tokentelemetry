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
from pathlib import Path

# The conventional folder name appended under the user's home (or under
# TOKENTELEMETRY_HOME). Not appended when TOKENTELEMETRY_DATA_DIR is used.
DEFAULT_DIRNAME = ".tokentelemetry"


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
