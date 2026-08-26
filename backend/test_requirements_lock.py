"""Guard that requirements.lock stays consistent with requirements.txt.

bin/cli.js installs from requirements.lock whenever it exists and carries
hashes, falling back to requirements.txt only for checkouts predating the lock.
So requirements.txt is a statement of intent and the lock is what users
actually get. When the two drift, the drift is silent: the install succeeds and
ships the wrong thing.

Both failure modes have happened or are pending:

* A dep present in requirements.txt but absent from the lock is never
  installed. `zstandard` was added for the DeepSeek Harness scanner without
  regenerating the lock, so every venv built from the lock lacked it.
  `_dsh_read_events` treats ImportError as "skip this session", so the
  dashboard reported zero DSH sessions rather than erroring.
* A dep pinned in the lock at a version the specifier excludes ships that
  excluded version. Bumping a floor in requirements.txt without regenerating
  the lock does exactly this, and nothing downstream notices.

Regenerate with the command recorded in the lock's own header:
    uv pip compile --universal --generate-hashes --python-version 3.9 \
        backend/requirements.txt -o backend/requirements.lock

A lock uv generated is consistent by construction: given a specifier it cannot
satisfy on some supported Python it fails to resolve rather than emitting a
violating pin. These tests therefore catch hand-edits and stale locks, which is
where the real risk is.

Known gap: extras are not checked. Dropping `[standard]` from uvicorn would
pass both tests.

Run: pytest backend/test_requirements_lock.py -q
"""
import os
import re

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

HERE = os.path.dirname(__file__)
REQ = os.path.join(HERE, "requirements.txt")
LOCK = os.path.join(HERE, "requirements.lock")

# A lock line pins one version and may carry an environment marker:
#   zstandard==0.25.0 \
#   uvicorn==0.51.0 ; python_full_version >= '3.10' \
_PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;\\]+)\s*(?:;\s*(.*?))?\s*\\?$")


def _direct_requirements():
    """Parsed requirements.txt entries, keyed by canonical name."""
    reqs = {}
    with open(REQ, encoding="utf-8") as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip()
            # Skip blanks and pip's own flags (-r, --index-url, ...).
            if not line or line.startswith("-"):
                continue
            req = Requirement(line)
            reqs[canonicalize_name(req.name)] = req
    return reqs


def _locked_pins():
    """Every pin in the lock as {canonical name: [(version, marker), ...]}.

    A universal lock pins one name more than once when a marker splits it
    across Python versions, so the value is a list. Both tests read this one
    parser: if its regex ever stops matching a line, the coverage test below
    fails loudly rather than the version test passing on an empty list.
    """
    pins = {}
    with open(LOCK, encoding="utf-8") as fh:
        for line in fh:
            m = _PIN.match(line.rstrip("\n"))
            if m:
                name, version, marker = m.group(1), m.group(2), m.group(3) or ""
                pins.setdefault(canonicalize_name(name), []).append((version, marker))
    return pins


def test_lock_covers_every_direct_requirement():
    missing = sorted(set(_direct_requirements()) - set(_locked_pins()))
    assert not missing, (
        "requirements.txt lists {} that requirements.lock does not pin: {}. "
        "The lock is what bin/cli.js installs, so these would never reach a "
        "venv. Regenerate the lock (see this module's docstring)."
        .format("a dep" if len(missing) == 1 else "deps", ", ".join(missing))
    )


def test_locked_versions_satisfy_their_specifiers():
    """Every pinned version must satisfy the specifier that declared it.

    Catches the reverse of the missing-dep case: a floor raised in
    requirements.txt while the lock still pins the version below it. The
    install succeeds, so only this check surfaces the mismatch.
    """
    pins = _locked_pins()
    violations = []
    for name, req in sorted(_direct_requirements().items()):
        for version, marker in pins.get(name, []):
            if Version(version) not in req.specifier:
                violations.append(
                    "{} requires {} but the lock pins {}{}".format(
                        name,
                        req.specifier or "any version",
                        version,
                        " (for {})".format(marker) if marker else "",
                    )
                )
    assert not violations, (
        "requirements.lock pins versions requirements.txt excludes:\n  {}\n"
        "bin/cli.js installs the lock, so these versions are what users get. "
        "Regenerate the lock (see this module's docstring). If regeneration "
        "fails as unsatisfiable, the requested floor is incompatible with the "
        "Python floor the lock is compiled for."
        .format("\n  ".join(violations))
    )


def test_lock_is_hash_pinned():
    """cli.js only prefers the lock when it carries hashes; without them it
    silently falls back to requirements.txt and this guard would be moot."""
    with open(LOCK, encoding="utf-8") as fh:
        assert "--hash=" in fh.read(), "requirements.lock carries no hashes"
