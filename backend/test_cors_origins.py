"""Tests for the CORS allowlist pattern.

The allowlist is built from two halves (see main._cors_origin_regex): loopback,
always on and on any port, and the hosts opted in via TT_ALLOWED_ORIGINS for
remote / tailnet access. Both halves accept an origin with no port, because
browsers omit the port from Origin when it is the scheme default. A deployment
behind a proxy on :443 therefore sends "https://box.ts.net" with no port at
all, and there is no configuration a user can write to work around a pattern
that demands one.

Starlette's CORSMiddleware tests the origin with .fullmatch(), so that is what
these tests use.

Run: pytest backend/test_cors_origins.py -q
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import main  # noqa: E402


def allowed(origin: str, monkeypatch, env: str = "") -> bool:
    monkeypatch.setenv("TT_ALLOWED_ORIGINS", env)
    return bool(re.fullmatch(main._cors_origin_regex(), origin))


# --- loopback half ---------------------------------------------------------

@pytest.mark.parametrize("origin", [
    "http://localhost:3000",
    "http://localhost:4500",      # the user can move it with --port
    "http://127.0.0.1:8000",
    "http://[::1]:3000",
])
def test_loopback_is_allowed_on_any_port(origin, monkeypatch):
    assert allowed(origin, monkeypatch)


@pytest.mark.parametrize("origin", [
    "http://localhost",           # default port 80, omitted by the browser
    "https://localhost",          # default port 443, omitted by the browser
    "http://[::1]",
])
def test_loopback_is_allowed_without_a_port(origin, monkeypatch):
    assert allowed(origin, monkeypatch)


def test_loopback_agrees_with_the_auth_gate(monkeypatch):
    """_is_loopback() treats ::1 as loopback, so the allowlist must too.

    The two disagreeing about what "loopback" means is how you end up with an
    origin the auth gate waves through but CORS rejects.
    """
    for host in ("127.0.0.1", "::1", "localhost"):
        assert main._is_loopback(host)
    assert allowed("http://[::1]:3000", monkeypatch)


# --- remote half -----------------------------------------------------------

def test_remote_half_is_absent_by_default(monkeypatch):
    """Default behaviour is loopback-only."""
    monkeypatch.setenv("TT_ALLOWED_ORIGINS", "")
    assert main._remote_origin_regex() is None
    assert not allowed("https://box.ts.net", monkeypatch)


@pytest.mark.parametrize("origin", [
    "https://box.ts.net",         # proxied on :443, no port in Origin
    "http://box.ts.net",          # proxied on :80, no port in Origin
    "https://box.ts.net:8443",    # explicit port
])
def test_configured_host_is_allowed_with_or_without_a_port(origin, monkeypatch):
    assert allowed(origin, monkeypatch, env="box.ts.net")


@pytest.mark.parametrize("entry", [
    "box.ts.net",
    "https://box.ts.net",         # a full origin is the natural thing to write
    "https://box.ts.net/",        # ...possibly with a trailing slash
    "http://box.ts.net:8443/x",   # ...or copied out of the address bar
    "BOX.TS.NET",                 # Origin hosts arrive ASCII-lowercased
    "  box.ts.net  ",
])
def test_entry_spellings_all_resolve_to_the_same_host(entry, monkeypatch):
    assert allowed("https://box.ts.net", monkeypatch, env=entry)


def test_multiple_hosts_and_blank_entries(monkeypatch):
    env = "box.ts.net, ,100.64.0.1,"
    assert allowed("https://box.ts.net", monkeypatch, env=env)
    assert allowed("http://100.64.0.1:3000", monkeypatch, env=env)
    assert not allowed("https://other.ts.net", monkeypatch, env=env)


# --- what must stay rejected ----------------------------------------------

@pytest.mark.parametrize("origin,env", [
    ("https://evil.com",            ""),
    ("http://notlocalhost",         ""),
    ("http://localhost.evil.com",   ""),           # prefix, needs the $ anchor
    ("https://box.ts.net.evil.com", "box.ts.net"),  # suffix, needs the $ anchor
    ("https://sub.box.ts.net",      "box.ts.net"),  # subdomains are not implied
    ("ftp://localhost:3000",        ""),            # scheme is pinned to http(s)
    ("http://localhost:3000/path",  ""),            # an origin carries no path
])
def test_rejected(origin, env, monkeypatch):
    assert not allowed(origin, monkeypatch, env=env)


def test_dots_in_a_configured_host_are_literal(monkeypatch):
    """Without re.escape, the dots would match any character, so allowing
    box.ts.net would also allow an attacker-registered boxXtsYnet."""
    assert not allowed("https://boxXtsYnet", monkeypatch, env="box.ts.net")
    assert not allowed("https://box-ts-net", monkeypatch, env="box.ts.net")


def test_a_configured_host_cannot_inject_pattern_syntax(monkeypatch):
    """The value is user-supplied, so regex metacharacters must not survive."""
    assert not allowed("https://anything", monkeypatch, env=".*")
    assert allowed("https://.*", monkeypatch, env=".*")  # matched literally


# --- entry normalisation ---------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("box.ts.net",                "box.ts.net"),
    ("https://box.ts.net",        "box.ts.net"),
    ("http://box.ts.net/",        "box.ts.net"),
    ("https://box.ts.net:8443",   "box.ts.net"),
    ("https://box.ts.net/a?b=c",  "box.ts.net"),
    ("BOX.TS.NET",                "box.ts.net"),
    ("  box.ts.net  ",            "box.ts.net"),
    ("[::1]:3000",                "[::1]"),
    ("http://[::1]",              "[::1]"),
    ("",                          ""),
    ("   ",                       ""),
])
def test_origin_host_normalisation(raw, expected):
    assert main._origin_host(raw) == expected
