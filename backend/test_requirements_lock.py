"""Guard that requirements.lock covers every direct dep in requirements.txt.

bin/cli.js installs from requirements.lock whenever it exists and carries
hashes, falling back to requirements.txt only for checkouts predating the lock.
So a dep added to requirements.txt without regenerating the lock is never
installed, and the feature that needs it fails at runtime instead of at install
time.

That is not hypothetical: `zstandard` was added for the DeepSeek Harness
scanner but the lock was not regenerated, so every venv built from the lock
lacked it. `_dsh_read_events` treats ImportError as "skip this session", so the
dashboard silently reported zero DSH sessions rather than erroring.

Regenerate with the command recorded in the lock's own header:
    uv pip compile --universal --generate-hashes --python-version 3.9 \
        backend/requirements.txt -o backend/requirements.lock

Run: pytest backend/test_requirements_lock.py -q
"""
import os
import re

HERE = os.path.dirname(__file__)
REQ = os.path.join(HERE, "requirements.txt")
LOCK = os.path.join(HERE, "requirements.lock")

# PEP 503: names compare case-insensitively with runs of -_. collapsed to -.
_SEP = re.compile(r"[-_.]+")


def _canon(name):
    return _SEP.sub("-", name.strip().lower())


def _direct_deps(path):
    """Top-level requirement names, dropping extras, markers and specifiers."""
    names = set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip()
            # Skip blanks and pip's own flags (-r, --index-url, ...).
            if not line or line.startswith("-"):
                continue
            # "uvicorn[standard]>=0.27,<1.0" -> "uvicorn"
            m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", line)
            if m:
                names.add(_canon(m.group(1)))
    return names


def _locked_names(path):
    """Names pinned in the lock. A universal lock may pin one name more than
    once under different environment markers; we only care that it appears."""
    names = set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==", line)
            if m:
                names.add(_canon(m.group(1)))
    return names


def test_lock_covers_every_direct_requirement():
    missing = sorted(_direct_deps(REQ) - _locked_names(LOCK))
    assert not missing, (
        "requirements.txt lists {} that requirements.lock does not pin: {}. "
        "The lock is what bin/cli.js installs, so these would never reach a "
        "venv. Regenerate the lock (see this module's docstring)."
        .format("a dep" if len(missing) == 1 else "deps", ", ".join(missing))
    )


def test_lock_is_hash_pinned():
    """cli.js only prefers the lock when it carries hashes; without them it
    silently falls back to requirements.txt and this guard would be moot."""
    with open(LOCK, encoding="utf-8") as fh:
        assert "--hash=" in fh.read(), "requirements.lock carries no hashes"
